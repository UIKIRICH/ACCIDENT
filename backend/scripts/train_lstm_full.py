import argparse
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset


CLASS_NAMES = ["rear_end", "lane_change", "turn_conflict"]
CLASS_TO_ID = {name: i for i, name in enumerate(CLASS_NAMES)}


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        fv = float(v)
        if not np.isfinite(fv):
            return float(default)
        return fv
    except (TypeError, ValueError):
        return float(default)


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


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


def parse_scene_tags(row: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    raw_scene_tags = row.get("scene_tags", None)
    if isinstance(raw_scene_tags, list):
        tags.extend([str(x).strip() for x in raw_scene_tags if str(x).strip()])
    elif isinstance(raw_scene_tags, str) and raw_scene_tags.strip():
        s = raw_scene_tags.strip()
        try:
            parsed = json.loads(s)
            if isinstance(parsed, list):
                tags.extend([str(x).strip() for x in parsed if str(x).strip()])
            else:
                tags.append(s)
        except json.JSONDecodeError:
            parts = [p.strip() for p in s.replace(";", ",").split(",") if p.strip()]
            tags.extend(parts if parts else [s])

    dedup: List[str] = []
    seen = set()
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


def build_classification_stats(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    f1s: List[float] = []
    for cname, cid in CLASS_TO_ID.items():
        tp = int(np.sum((y_true == cid) & (y_pred == cid)))
        fp = int(np.sum((y_true != cid) & (y_pred == cid)))
        fn = int(np.sum((y_true == cid) & (y_pred != cid)))
        tn = int(np.sum((y_true != cid) & (y_pred != cid)))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out[cname] = {
            "support": int(np.sum(y_true == cid)),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "tn": tn,
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
        }
        f1s.append(float(f1))

    acc = float(np.mean(y_true == y_pred)) if len(y_true) else 0.0
    macro_f1 = float(sum(f1s) / len(f1s)) if f1s else 0.0
    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "per_class": out,
    }


def apply_turn_router(
    probs: np.ndarray,
    base_pred: np.ndarray,
    turn_idx: int,
    min_prob: float,
    margin: float,
) -> np.ndarray:
    if probs.ndim != 2 or base_pred.ndim != 1:
        return base_pred
    if min_prob <= 0.0 and margin <= 0.0:
        return base_pred

    routed = base_pred.copy()
    max_probs = np.max(probs, axis=1)
    turn_probs = probs[:, int(turn_idx)]
    mask = (turn_probs >= float(min_prob)) & ((max_probs - turn_probs) <= float(margin))
    routed[mask] = int(turn_idx)
    return routed


def fuse_turn_probs(
    cls_probs: np.ndarray,
    turn_bin_probs: np.ndarray,
    turn_idx: int,
    alpha: float,
) -> np.ndarray:
    if cls_probs.ndim != 2 or turn_bin_probs.ndim != 1:
        return cls_probs
    if cls_probs.shape[0] != turn_bin_probs.shape[0] or cls_probs.shape[1] < 3:
        return cls_probs
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


class SequenceDataset(Dataset):
    def __init__(self, x: np.ndarray, y: np.ndarray, y_turn: np.ndarray, sample_w: np.ndarray) -> None:
        self.x = torch.tensor(x, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)
        self.y_turn = torch.tensor(y_turn, dtype=torch.float32)
        self.sample_w = torch.tensor(sample_w, dtype=torch.float32)

    def __len__(self) -> int:
        return int(self.x.shape[0])

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        return self.x[idx], self.y[idx], self.y_turn[idx], self.sample_w[idx]


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


class FocalLoss(nn.Module):
    def __init__(self, class_weights: Optional[torch.Tensor], gamma: float = 2.0, reduction: str = "none") -> None:
        super().__init__()
        self.class_weights = class_weights
        self.gamma = float(gamma)
        self.reduction = str(reduction)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce = F.cross_entropy(logits, targets, reduction="none")
        pt = torch.exp(-ce).clamp(min=1e-8, max=1.0)
        if self.class_weights is None:
            alpha_t = torch.ones_like(pt)
        else:
            alpha_t = self.class_weights[targets]
        loss = alpha_t * ((1.0 - pt) ** self.gamma) * ce
        if self.reduction == "none":
            return loss
        return loss.mean()


def build_records(
    split_rows: List[Dict[str, Any]],
    feature_map: Dict[str, Dict[str, Any]],
    feature_cols: List[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    records: List[Dict[str, Any]] = []
    missing_ids: List[str] = []
    for row in split_rows:
        sample_id = str(row.get("sample_id", "")).strip()
        if not sample_id:
            continue
        feat_row = feature_map.get(sample_id)
        if feat_row is None:
            missing_ids.append(sample_id)
            continue
        accident_type = str(row.get("accident_type", feat_row.get("accident_type", ""))).strip()
        if accident_type not in CLASS_TO_ID:
            continue
        vec = np.array([safe_float(feat_row.get(c, 0.0)) for c in feature_cols], dtype=np.float32)
        records.append(
            {
                "sample_id": sample_id,
                "video": normalize_video_key(row.get("video", sample_id)),
                "accident_type": accident_type,
                "label_id": CLASS_TO_ID[accident_type],
                "feature": vec,
                "sample_weight": 1.0,
                "scene_tags": parse_scene_tags(row),
                "onset_time": safe_float(row.get("onset_time", 0.0)),
                "impact_time": safe_float(row.get("impact_time", 0.0)),
                "post_time": safe_float(row.get("post_time", 0.0)),
            }
        )
    return records, missing_ids


def build_sequence_tensor(flat_x: np.ndarray, seq_len: int) -> np.ndarray:
    if flat_x.ndim != 2:
        raise ValueError(f"Expected flat feature matrix [N,F], got shape={flat_x.shape}")
    n, f = flat_x.shape
    if seq_len <= 0:
        raise ValueError(f"seq_len must be > 0, got {seq_len}")
    if f % seq_len != 0:
        raise ValueError(f"feature_dim={f} is not divisible by seq_len={seq_len}")
    step_dim = f // seq_len
    return flat_x.reshape(n, seq_len, step_dim)


def infer_seq_len(feature_dim: int) -> int:
    for cand in [59, 32, 16, 8]:
        if feature_dim % cand == 0:
            return cand
    return int(feature_dim)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Train single full-train BiLSTM+Attention model with frozen config (no dev-test tuning)."
    )
    parser.add_argument("--feature-csv", required=True, help="CSV with sample_id/feature_* columns")
    parser.add_argument("--train-jsonl", required=True, help="Full-train jsonl path")
    parser.add_argument("--out-ckpt", required=True, help="Output checkpoint path")
    parser.add_argument("--out-metrics", required=True, help="Output metrics json")
    parser.add_argument("--out-train-log", default="", help="Optional training log json")
    parser.add_argument("--out-train-pred", default="", help="Optional train prediction jsonl")
    parser.add_argument("--seq-len", type=int, default=59, help="Sequence length; 0=auto")
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--mlp-hidden", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--loss-type", choices=["ce", "focal"], default="focal")
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--no-class-weight", action="store_true")
    parser.add_argument("--class-weight-alpha", type=float, default=0.0, help="Blend factor with uniform weights.")
    parser.add_argument("--class-weight-floor", type=float, default=0.0, help="Lower bound for class weights.")
    parser.add_argument("--turn-weight-boost", type=float, default=1.0, help="Extra boost on turn_conflict class.")
    parser.add_argument("--dual-turn-head", action="store_true", help="Enable turn-vs-nonturn auxiliary head.")
    parser.add_argument("--turn-bin-loss-weight", type=float, default=0.4)
    parser.add_argument("--turn-fuse-alpha", type=float, default=0.6)
    parser.add_argument("--turn-router-min-prob", type=float, default=0.0)
    parser.add_argument("--turn-router-margin", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    set_seed(int(args.seed))

    feature_csv = Path(args.feature_csv).resolve()
    train_jsonl = Path(args.train_jsonl).resolve()
    out_ckpt = Path(args.out_ckpt).resolve()
    out_metrics = Path(args.out_metrics).resolve()
    out_train_log = Path(args.out_train_log).resolve() if str(args.out_train_log).strip() else None
    out_train_pred = Path(args.out_train_pred).resolve() if str(args.out_train_pred).strip() else None

    feature_df = pd.read_csv(feature_csv)
    feature_cols = [c for c in feature_df.columns if c.startswith("feature_")]
    if not feature_cols:
        raise RuntimeError(f"No feature_* columns found in {feature_csv}")
    if "sample_id" not in feature_df.columns:
        raise RuntimeError(f"{feature_csv} missing sample_id column")

    feature_map: Dict[str, Dict[str, Any]] = {}
    for _, r in feature_df.iterrows():
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            feature_map[sid] = r.to_dict()

    train_rows = load_jsonl(train_jsonl)
    train_records, train_missing_ids = build_records(train_rows, feature_map, feature_cols)
    if not train_records:
        raise RuntimeError("No usable train samples after joining split with feature CSV.")

    x_flat = np.stack([r["feature"] for r in train_records], axis=0).astype(np.float32)
    y = np.array([r["label_id"] for r in train_records], dtype=np.int64)
    y_turn = (y == CLASS_TO_ID["turn_conflict"]).astype(np.float32)
    sample_w = np.array([safe_float(r.get("sample_weight", 1.0), 1.0) for r in train_records], dtype=np.float32)

    mu = np.mean(x_flat, axis=0)
    std = np.std(x_flat, axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    x_norm = (x_flat - mu.reshape(1, -1)) / std.reshape(1, -1)

    seq_len = int(args.seq_len)
    if seq_len <= 0:
        seq_len = infer_seq_len(int(x_norm.shape[1]))
    x_seq = build_sequence_tensor(x_norm, seq_len)
    input_dim = int(x_seq.shape[2])

    dataset = SequenceDataset(x_seq, y, y_turn, sample_w)
    loader = DataLoader(dataset, batch_size=int(args.batch_size), shuffle=True)

    class_counts = np.bincount(y, minlength=len(CLASS_NAMES)).astype(np.float32)
    class_weights_np = np.ones((len(CLASS_NAMES),), dtype=np.float32)
    if not args.no_class_weight:
        n_total = float(len(y))
        class_weights_np = n_total / (len(CLASS_NAMES) * np.maximum(class_counts, 1.0))
        alpha = float(args.class_weight_alpha)
        if alpha > 0.0:
            class_weights_np = ((1.0 - alpha) * class_weights_np) + (alpha * np.ones_like(class_weights_np))
        floor = float(args.class_weight_floor)
        if floor > 0.0:
            class_weights_np = np.maximum(class_weights_np, floor)
        class_weights_np[CLASS_TO_ID["turn_conflict"]] *= max(1.0, float(args.turn_weight_boost))
    class_weights_t = torch.tensor(class_weights_np, dtype=torch.float32)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = BiLSTMAttentionClassifier(
        input_dim=input_dim,
        hidden_size=int(args.hidden_size),
        num_layers=int(args.num_layers),
        dropout=float(args.dropout),
        num_classes=len(CLASS_NAMES),
        mlp_hidden=int(args.mlp_hidden),
    ).to(device)
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=float(args.lr),
        weight_decay=float(args.weight_decay),
    )
    if str(args.loss_type) == "focal":
        criterion = FocalLoss(
            class_weights=class_weights_t.to(device) if not args.no_class_weight else None,
            gamma=float(args.focal_gamma),
            reduction="none",
        )
    else:
        ce_weight = class_weights_t.to(device) if not args.no_class_weight else None

        def ce_fn(logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
            return F.cross_entropy(logits, targets, weight=ce_weight, reduction="none")

        criterion = ce_fn

    history: List[Dict[str, Any]] = []
    for epoch in range(1, int(args.epochs) + 1):
        model.train()
        loss_acc = 0.0
        cls_loss_acc = 0.0
        turn_loss_acc = 0.0
        n_seen = 0
        for xb, yb, y_turn_b, sample_w_b in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            y_turn_b = y_turn_b.to(device)
            sample_w_b = sample_w_b.to(device)

            optimizer.zero_grad()
            logits, turn_logit, _ = model(xb)
            cls_loss_vec = criterion(logits, yb)
            cls_loss = (cls_loss_vec * sample_w_b).mean()

            if args.dual_turn_head:
                turn_loss_vec = F.binary_cross_entropy_with_logits(turn_logit, y_turn_b, reduction="none")
                turn_loss = (turn_loss_vec * sample_w_b).mean()
            else:
                turn_loss = torch.tensor(0.0, dtype=torch.float32, device=device)

            loss = cls_loss + (float(args.turn_bin_loss_weight) * turn_loss)
            loss.backward()
            optimizer.step()

            bs = int(xb.shape[0])
            n_seen += bs
            loss_acc += float(loss.item()) * bs
            cls_loss_acc += float(cls_loss.item()) * bs
            turn_loss_acc += float(turn_loss.item()) * bs

        row = {
            "epoch": int(epoch),
            "train_loss": round(float(loss_acc / max(1, n_seen)), 8),
            "train_cls_loss": round(float(cls_loss_acc / max(1, n_seen)), 8),
            "train_turn_loss": round(float(turn_loss_acc / max(1, n_seen)), 8),
        }
        history.append(row)
        print(
            f"[EPOCH {epoch:03d}] "
            f"loss={row['train_loss']:.6f} cls={row['train_cls_loss']:.6f} turn={row['train_turn_loss']:.6f}"
        )

    model.eval()
    with torch.no_grad():
        x_all_t = torch.tensor(x_seq, dtype=torch.float32, device=device)
        logits_all, turn_logit_all, _ = model(x_all_t)
        logits_np = logits_all.cpu().numpy().astype(np.float64)
        logits_np -= np.max(logits_np, axis=1, keepdims=True)
        exp_np = np.exp(logits_np)
        cls_probs = exp_np / np.maximum(np.sum(exp_np, axis=1, keepdims=True), 1e-12)
        if args.dual_turn_head:
            turn_prob = 1.0 / (1.0 + np.exp(-turn_logit_all.cpu().numpy().astype(np.float64)))
            probs = fuse_turn_probs(
                cls_probs,
                turn_prob.reshape(-1),
                turn_idx=CLASS_TO_ID["turn_conflict"],
                alpha=float(args.turn_fuse_alpha),
            )
        else:
            probs = cls_probs

    pred_raw = np.argmax(probs, axis=1)
    pred = apply_turn_router(
        probs,
        pred_raw,
        turn_idx=CLASS_TO_ID["turn_conflict"],
        min_prob=float(args.turn_router_min_prob),
        margin=float(args.turn_router_margin),
    )
    train_stats = build_classification_stats(y, pred)

    out_ckpt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "class_names": CLASS_NAMES,
            "feature_columns": feature_cols,
            "seq_len": int(seq_len),
            "input_dim": int(input_dim),
            "feature_mean": mu.astype(np.float32).tolist(),
            "feature_std": std.astype(np.float32).tolist(),
            "config": {
                "hidden_size": int(args.hidden_size),
                "num_layers": int(args.num_layers),
                "dropout": float(args.dropout),
                "mlp_hidden": int(args.mlp_hidden),
                "dual_turn_head": bool(args.dual_turn_head),
                "turn_bin_loss_weight": float(args.turn_bin_loss_weight),
                "turn_fuse_alpha": float(args.turn_fuse_alpha),
            },
        },
        out_ckpt,
    )

    if out_train_pred is not None:
        out_train_pred.parent.mkdir(parents=True, exist_ok=True)
        with out_train_pred.open("w", encoding="utf-8") as f:
            for i, rec in enumerate(train_records):
                p = probs[i]
                pred_id = int(pred[i])
                pred_type = CLASS_NAMES[pred_id]
                out_row = {
                    "video": normalize_video_key(rec["video"]),
                    "pred_type": pred_type,
                    "type_probs": {
                        "rear_end": round(float(p[0]), 6),
                        "lane_change": round(float(p[1]), 6),
                        "turn_conflict": round(float(p[2]), 6),
                        "generic": 0.0,
                    },
                    "pred_onset_time": round(float(rec["onset_time"]), 3),
                    "pred_impact_time": round(float(rec["impact_time"]), 3),
                    "pred_post_time": round(float(rec["post_time"]), 3),
                    "lead_time_sec": round(float(max(0.0, rec["impact_time"] - rec["onset_time"])), 3),
                    "risk_score": round(float(np.max(p)), 6),
                    "uncertainty": round(float(1.0 - np.max(p)), 6),
                    "keyframe_times": [
                        round(float(rec["onset_time"]), 3),
                        round(float(rec["impact_time"]), 3),
                        round(float(rec["post_time"]), 3),
                    ],
                    "scene_tags": rec["scene_tags"],
                    "sample_id": rec["sample_id"],
                    "timing_source": "train_gt",
                }
                f.write(json.dumps(out_row, ensure_ascii=False) + "\n")

    metrics_obj: Dict[str, Any] = {
        "model": "bilstm_attention_v33_full_train",
        "feature_csv": str(feature_csv),
        "train_jsonl": str(train_jsonl),
        "seed": int(args.seed),
        "device": str(device),
        "seq_len": int(seq_len),
        "input_dim": int(input_dim),
        "n_train": int(len(train_records)),
        "n_train_missing_feature": int(len(train_missing_ids)),
        "epochs": int(args.epochs),
        "batch_size": int(args.batch_size),
        "lr": float(args.lr),
        "weight_decay": float(args.weight_decay),
        "loss_type": str(args.loss_type),
        "focal_gamma": float(args.focal_gamma),
        "class_weight_enabled": bool(not args.no_class_weight),
        "class_weight_alpha": float(args.class_weight_alpha),
        "class_weight_floor": float(args.class_weight_floor),
        "turn_weight_boost": float(args.turn_weight_boost),
        "dual_turn_head": bool(args.dual_turn_head),
        "turn_bin_loss_weight": float(args.turn_bin_loss_weight),
        "turn_fuse_alpha": float(args.turn_fuse_alpha),
        "turn_router_min_prob": float(args.turn_router_min_prob),
        "turn_router_margin": float(args.turn_router_margin),
        "class_weights": [round(float(x), 6) for x in class_weights_np.tolist()],
        "class_counts_train": {CLASS_NAMES[i]: int(class_counts[i]) for i in range(len(CLASS_NAMES))},
        "train_accuracy": round(float(train_stats["accuracy"]), 6),
        "train_macro_f1": round(float(train_stats["macro_f1"]), 6),
        "train_per_class": train_stats["per_class"],
        "output_checkpoint": str(out_ckpt),
        "output_train_pred": str(out_train_pred) if out_train_pred else "",
    }
    out_metrics.parent.mkdir(parents=True, exist_ok=True)
    out_metrics.write_text(json.dumps(metrics_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    if out_train_log is not None:
        out_train_log.parent.mkdir(parents=True, exist_ok=True)
        out_train_log.write_text(
            json.dumps(
                {
                    "model": "bilstm_attention_v33_full_train",
                    "history": history,
                    "final_train_accuracy": round(float(train_stats["accuracy"]), 8),
                    "final_train_macro_f1": round(float(train_stats["macro_f1"]), 8),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print(json.dumps(metrics_obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

