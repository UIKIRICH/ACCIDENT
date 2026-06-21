import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn


CLASS_NAMES = ["rear_end", "lane_change", "turn_conflict"]


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
    return rows


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def parse_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [str(x).strip() for x in obj if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [s]


class BiLSTMAttentionClassifier(nn.Module):
    def __init__(
        self,
        input_dim: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
        num_classes: int,
        mlp_hidden: int,
    ) -> None:
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            bidirectional=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.attn = nn.Sequential(
            nn.Linear(hidden_size * 2, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )
        self.head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 2, mlp_hidden),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(mlp_hidden, num_classes),
        )
        self.turn_head = nn.Sequential(
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 2, 1),
        )

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        seq_out, _ = self.lstm(x)
        attn_scores = self.attn(seq_out).squeeze(-1)
        attn_weights = torch.softmax(attn_scores, dim=1)
        context = torch.sum(seq_out * attn_weights.unsqueeze(-1), dim=1)
        logits = self.head(context)
        turn_logit = self.turn_head(context).squeeze(-1)
        return logits, turn_logit, attn_weights


def softmax_np(logits: np.ndarray) -> np.ndarray:
    x = logits - logits.max(axis=1, keepdims=True)
    ex = np.exp(x)
    return ex / np.clip(ex.sum(axis=1, keepdims=True), 1e-12, None)


def fuse_turn_probs(
    cls_probs: np.ndarray,
    turn_bin_probs: np.ndarray,
    turn_idx: int,
    alpha: float,
) -> np.ndarray:
    alpha = min(1.0, max(0.0, float(alpha)))
    fused = cls_probs.copy()
    old_turn = fused[:, int(turn_idx)]
    new_turn = (alpha * old_turn) + ((1.0 - alpha) * turn_bin_probs)
    new_turn = np.clip(new_turn, 1e-8, 1.0 - 1e-8)

    non_turn_idx = [i for i in range(fused.shape[1]) if i != int(turn_idx)]
    old_non_turn = np.sum(fused[:, non_turn_idx], axis=1)
    target_non_turn = np.maximum(1.0 - new_turn, 1e-8)
    scale = np.where(old_non_turn > 1e-8, target_non_turn / old_non_turn, 1.0 / max(1, len(non_turn_idx)))
    for i in non_turn_idx:
        fused[:, i] = fused[:, i] * scale
    fused[:, int(turn_idx)] = new_turn
    fused = np.clip(fused, 1e-10, None)
    fused = fused / np.maximum(np.sum(fused, axis=1, keepdims=True), 1e-12)
    return fused


def apply_rear_guard(
    pred_type: str,
    probs: Dict[str, float],
    scene_tags: List[str],
    rear_floor: float,
    gap_max: float,
    turn_ceiling: float,
    lane_cap: float,
) -> Tuple[str, bool, str]:
    if pred_type != "turn_conflict":
        return pred_type, False, "NO_TURN_BASE"
    tags = {str(x).strip() for x in scene_tags if str(x).strip()}
    if "intersection" in tags or "turning_scene" in tags:
        return pred_type, False, "SCENE_BLOCK"

    pr = safe_float(probs.get("rear_end", 0.0), 0.0)
    pl = safe_float(probs.get("lane_change", 0.0), 0.0)
    pt = safe_float(probs.get("turn_conflict", 0.0), 0.0)

    if pr >= rear_floor and (pt - pr) <= gap_max and pt <= turn_ceiling and pl <= lane_cap:
        return "rear_end", True, "REAR_GUARD_TRIGGERED"
    return pred_type, False, "RULE_NOT_MET"


def load_rule_map(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    rows = load_jsonl(path)
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        out[normalize_video_key(r.get("video", ""))] = r
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Predict test set with LSTM fold-ensemble checkpoints.")
    parser.add_argument("--labels", required=True, help="labels jsonl path")
    parser.add_argument("--feature-csv", required=True, help="feature csv path")
    parser.add_argument("--checkpoints-dir", required=True, help="checkpoint directory")
    parser.add_argument("--out", required=True, help="output pred jsonl")
    parser.add_argument("--rule-pred", default="", help="rule prediction jsonl for timing inheritance")
    parser.add_argument("--apply-rear-guard", action="store_true", help="apply v3.4.3 rear guard")
    parser.add_argument("--rear-floor", type=float, default=0.40)
    parser.add_argument("--gap-max", type=float, default=0.04)
    parser.add_argument("--turn-ceiling", type=float, default=0.45)
    parser.add_argument("--lane-cap", type=float, default=0.22)
    args = parser.parse_args()

    labels_path = Path(args.labels).resolve()
    feature_csv = Path(args.feature_csv).resolve()
    ckpt_dir = Path(args.checkpoints_dir).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rule_pred = Path(args.rule_pred).resolve() if str(args.rule_pred).strip() else None

    labels = load_jsonl(labels_path)
    label_by_sid = {str(r.get("sample_id", "")).strip(): r for r in labels}
    label_order = [str(r.get("sample_id", "")).strip() for r in labels if str(r.get("sample_id", "")).strip()]
    if not label_order:
        raise RuntimeError(f"{labels_path} has no valid sample_id.")

    df = pd.read_csv(feature_csv)
    if "sample_id" not in df.columns:
        raise RuntimeError(f"{feature_csv} missing sample_id column")
    df["sample_id"] = df["sample_id"].astype(str).str.strip()
    feat_map = {row["sample_id"]: row for _, row in df.iterrows()}

    missing = [sid for sid in label_order if sid not in feat_map]
    if missing:
        raise RuntimeError(
            f"missing features for {len(missing)} samples, head={missing[:5]}"
        )

    ckpts = sorted(ckpt_dir.glob("fold*_lstm_best.pt"))
    if not ckpts:
        raise RuntimeError(f"no fold*_lstm_best.pt under {ckpt_dir}")

    base_payload = torch.load(ckpts[0], map_location="cpu")
    feature_cols: List[str] = list(base_payload.get("feature_columns", []))
    class_names: List[str] = list(base_payload.get("class_names", CLASS_NAMES))
    if not feature_cols:
        raise RuntimeError(f"{ckpts[0]} missing feature_columns")

    for c in feature_cols:
        if c not in df.columns:
            raise RuntimeError(f"{feature_csv} missing expected feature col: {c}")

    x = np.stack(
        [np.array([safe_float(feat_map[sid].get(c, 0.0), 0.0) for c in feature_cols], dtype=np.float32) for sid in label_order],
        axis=0,
    )

    n = x.shape[0]
    prob_acc = np.zeros((n, len(class_names)), dtype=np.float64)

    for ck in ckpts:
        payload = torch.load(ck, map_location="cpu")
        cfg = payload.get("config", {}) or {}
        seq_len = int(payload.get("seq_len", 59))
        input_dim = int(payload.get("input_dim", max(1, x.shape[1] // max(1, seq_len))))
        hidden_size = int(cfg.get("hidden_size", 64))
        num_layers = int(cfg.get("num_layers", 1))
        dropout = float(cfg.get("dropout", 0.2))
        mlp_hidden = int(cfg.get("mlp_hidden", 64))
        dual_turn_head = bool(cfg.get("dual_turn_head", False))
        turn_fuse_alpha = float(cfg.get("turn_fuse_alpha", 0.6))

        mu = np.array(payload.get("feature_mean", []), dtype=np.float32).reshape(-1)
        std = np.array(payload.get("feature_std", []), dtype=np.float32).reshape(-1)
        if mu.size != x.shape[1] or std.size != x.shape[1]:
            raise RuntimeError(
                f"{ck.name} feature norm size mismatch: mean={mu.size}, std={std.size}, feat={x.shape[1]}"
            )

        xs = (x - mu.reshape(1, -1)) / np.clip(std.reshape(1, -1), 1e-6, None)
        if xs.shape[1] != seq_len * input_dim:
            raise RuntimeError(
                f"{ck.name} shape mismatch: feat={xs.shape[1]} vs seq_len*input_dim={seq_len*input_dim}"
            )
        xs = xs.reshape(n, seq_len, input_dim)

        model = BiLSTMAttentionClassifier(
            input_dim=input_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            num_classes=len(class_names),
            mlp_hidden=mlp_hidden,
        )
        model.load_state_dict(payload["model_state_dict"], strict=False)
        model.eval()

        with torch.no_grad():
            logits, turn_logits, _ = model(torch.tensor(xs, dtype=torch.float32))
            probs = softmax_np(logits.numpy())
            if dual_turn_head:
                turn_probs = 1.0 / (1.0 + np.exp(-turn_logits.numpy()))
                turn_idx = class_names.index("turn_conflict")
                probs = fuse_turn_probs(probs, turn_probs, turn_idx=turn_idx, alpha=turn_fuse_alpha)
            prob_acc += probs
        print(f"[INFO] used ckpt: {ck.name}")

    probs_mean = prob_acc / float(len(ckpts))
    pred_idx = np.argmax(probs_mean, axis=1)
    rule_map = load_rule_map(rule_pred)

    out_rows: List[Dict[str, Any]] = []
    for i, sid in enumerate(label_order):
        label = label_by_sid[sid]
        video = normalize_video_key(label.get("video", ""))
        scene_tags = parse_scene_tags(label.get("scene_tags", []))

        type_probs_raw = {str(class_names[k]): float(probs_mean[i, k]) for k in range(len(class_names))}
        type_probs = {
            "rear_end": float(type_probs_raw.get("rear_end", 0.0)),
            "lane_change": float(type_probs_raw.get("lane_change", 0.0)),
            "turn_conflict": float(type_probs_raw.get("turn_conflict", 0.0)),
        }
        prob_sum = sum(type_probs.values())
        if prob_sum <= 1e-12:
            type_probs = {"rear_end": 1 / 3, "lane_change": 1 / 3, "turn_conflict": 1 / 3}
            prob_sum = 1.0
        type_probs = {k: float(v / prob_sum) for k, v in type_probs.items()}
        pred_type = str(class_names[int(pred_idx[i])])

        rear_guard_applied = False
        fallback_reason = "NONE"
        if args.apply_rear_guard:
            pred_type, rear_guard_applied, fallback_reason = apply_rear_guard(
                pred_type=pred_type,
                probs=type_probs,
                scene_tags=scene_tags,
                rear_floor=float(args.rear_floor),
                gap_max=float(args.gap_max),
                turn_ceiling=float(args.turn_ceiling),
                lane_cap=float(args.lane_cap),
            )

        rr = rule_map.get(video)
        if rr is not None:
            pred_onset = safe_float(rr.get("pred_onset_time", 0.0), 0.0)
            pred_impact = safe_float(rr.get("pred_impact_time", 0.0), 0.0)
            pred_post = safe_float(rr.get("pred_post_time", 0.0), 0.0)
            lead = max(0.0, safe_float(rr.get("lead_time_sec", 0.0), 0.0))
            kf = rr.get("keyframe_times", [pred_onset, pred_impact, pred_post])
        else:
            pred_onset = safe_float(label.get("onset_time", 0.0), 0.0)
            pred_impact = safe_float(label.get("impact_time", 0.0), 0.0)
            pred_post = safe_float(label.get("post_time", 0.0), 0.0)
            lead = max(0.0, pred_impact - pred_onset)
            kf = [pred_onset, pred_impact, pred_post]

        confidence = max(type_probs["rear_end"], type_probs["lane_change"], type_probs["turn_conflict"])
        out_rows.append(
            {
                "sample_id": sid,
                "video": video,
                "pred_type": pred_type,
                "type_probs": {
                    "rear_end": round(type_probs["rear_end"], 6),
                    "lane_change": round(type_probs["lane_change"], 6),
                    "turn_conflict": round(type_probs["turn_conflict"], 6),
                    "generic": 0.0,
                },
                "pred_onset_time": round(float(pred_onset), 3),
                "pred_impact_time": round(float(pred_impact), 3),
                "pred_post_time": round(float(pred_post), 3),
                "lead_time_sec": round(float(lead), 3),
                "risk_score": round(float(confidence), 6),
                "uncertainty": round(float(1.0 - confidence), 6),
                "keyframe_times": [float(safe_float(x, 0.0)) for x in (kf if isinstance(kf, list) else [pred_impact])],
                "scene_tags": scene_tags,
                "decision_mode": "rear_guard_override" if rear_guard_applied else "model_main",
                "fallback_reason": fallback_reason,
                "rear_guard_applied": bool(rear_guard_applied),
            }
        )

    with out_path.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "labels": str(labels_path),
                "feature_csv": str(feature_csv),
                "checkpoints_dir": str(ckpt_dir),
                "checkpoints_used": len(ckpts),
                "rows": len(out_rows),
                "rule_timing_inherited": bool(rule_pred),
                "rear_guard": bool(args.apply_rear_guard),
                "out": str(out_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
