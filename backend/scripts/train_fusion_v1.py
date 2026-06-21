import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F


CLASS_NAMES = ["rear_end", "lane_change", "turn_conflict"]
CLASS_TO_ID = {k: i for i, k in enumerate(CLASS_NAMES)}


def parse_json_dict(v: Any) -> Dict[str, Any]:
    if isinstance(v, dict):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return json.loads(v)
        except json.JSONDecodeError:
            return {}
    return {}


def parse_json_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if isinstance(v, str) and v.strip():
        try:
            x = json.loads(v)
            return x if isinstance(x, list) else []
        except json.JSONDecodeError:
            return []
    return []


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def featurize_row(row: pd.Series) -> np.ndarray:
    probs = parse_json_dict(row.get("pred_type_probs", "{}"))
    scores = parse_json_dict(row.get("pred_type_scores", "{}"))
    dominant = parse_json_dict(row.get("dominant_meta", "{}"))
    scene_prior = parse_json_dict(row.get("scene_prior", "{}"))
    scene_tags = parse_json_list(row.get("scene_tags", "[]"))

    rear_prob = safe_float(probs.get("rear_end", 0.0))
    lane_prob = safe_float(probs.get("lane_change", 0.0))
    turn_prob = safe_float(probs.get("turn_conflict", 0.0))
    rear_score = safe_float(scores.get("rear_end", 0.0))
    lane_score = safe_float(scores.get("lane_change", 0.0))
    turn_score = safe_float(scores.get("turn_conflict", 0.0))

    scene_intersection_prior = safe_float(
        row.get("scene_prior_intersection", scene_prior.get("intersection_prior", 0.0))
    )
    scene_turning_prior = safe_float(
        row.get("scene_prior_turning_scene", scene_prior.get("turning_scene_prior", 0.0))
    )
    scene_turn_boost = safe_float(
        row.get("scene_prior_turn_candidate_boost", scene_prior.get("turn_candidate_boost", 0.0))
    )
    scene_turn_run = safe_float(
        row.get("scene_prior_turn_candidate_run", scene_prior.get("turn_candidate_run", 0.0))
    )
    scene_turn_evidence = safe_float(
        row.get("scene_prior_turn_evidence", scene_prior.get("turn_evidence", 0.0))
    )
    scene_router_score = safe_float(
        row.get("scene_prior_router_score", scene_prior.get("router_score", 0.0))
    )
    scene_stage2_score = safe_float(
        row.get("scene_prior_stage2_score", scene_prior.get("stage2_score", 0.0))
    )
    scene_stage2_applied = safe_float(
        row.get("scene_prior_stage2_applied", 1.0 if scene_prior.get("stage2_applied", False) else 0.0)
    )

    f = [
        rear_prob,
        lane_prob,
        turn_prob,
        rear_score,
        lane_score,
        turn_score,
        lane_prob - rear_prob,
        lane_prob - turn_prob,
        turn_prob - rear_prob,
        lane_score - rear_score,
        lane_score - turn_score,
        turn_score - rear_score,
        safe_float(row.get("pred_type_confidence", 0.0)),
        safe_float(row.get("risk_alert_time", 0.0)),
        safe_float(row.get("lead_time_sec", 0.0)),
        safe_float(row.get("uncertainty", 1.0)),
        safe_float(row.get("pred_onset_time", 0.0)),
        safe_float(row.get("pred_impact_time", 0.0)),
        safe_float(row.get("pred_post_time", 0.0)),
        safe_float(row.get("duration_seconds", 0.0)),
        safe_float(row.get("fps", 0.0)),
        safe_float(row.get("num_steps", 0.0)),
        safe_float(dominant.get("dominance", 0.0)),
        safe_float(dominant.get("coverage", 0.0)),
        safe_float(dominant.get("continuity", 0.0)),
        safe_float(dominant.get("bridged_coverage", 0.0)),
        safe_float(dominant.get("bridged_continuity", 0.0)),
        safe_float(dominant.get("peak_mean", 0.0)),
        safe_float(dominant.get("onset_peak", 0.0)),
        safe_float(dominant.get("impact_peak", 0.0)),
        safe_float(dominant.get("count", 0.0)),
        scene_intersection_prior,
        scene_turning_prior,
        scene_turn_boost,
        scene_turn_run,
        scene_turn_evidence,
        scene_router_score,
        scene_stage2_score,
        scene_stage2_applied,
        1.0 if "intersection" in scene_tags else 0.0,
        1.0 if "turning_scene" in scene_tags else 0.0,
        1.0 if "night" in scene_tags else 0.0,
        1.0 if "rain" in scene_tags else 0.0,
    ]
    return np.array(f, dtype=np.float32)


def build_xy(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    rows = []
    labels = []
    videos = []
    for _, r in df.iterrows():
        y = str(r.get("gt_accident_type", ""))
        if y not in CLASS_TO_ID:
            continue
        rows.append(featurize_row(r))
        labels.append(CLASS_TO_ID[y])
        videos.append(str(r.get("video", "")))
    if not rows:
        return np.zeros((0, 1), dtype=np.float32), np.zeros((0,), dtype=np.int64), []
    return np.stack(rows), np.array(labels, dtype=np.int64), videos


def build_eval_context_rows(df: pd.DataFrame) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        y = str(r.get("gt_accident_type", ""))
        if y not in CLASS_TO_ID:
            continue
        onset = safe_float(r.get("pred_onset_time", 0.0))
        impact = safe_float(r.get("pred_impact_time", 0.0))
        post = safe_float(r.get("pred_post_time", 0.0))
        keyframe_times = [round(float(x), 2) for x in [onset, impact, post] if float(x) >= 0.0]
        out.append(
            {
                "video": str(r.get("video", "")),
                "pred_onset_time": onset,
                "pred_impact_time": impact,
                "pred_post_time": post,
                "lead_time_sec": max(0.0, safe_float(r.get("lead_time_sec", 0.0))),
                "uncertainty": safe_float(r.get("uncertainty", 1.0)),
                "scene_tags": [str(x) for x in parse_json_list(r.get("scene_tags", "[]"))],
                "keyframe_times": keyframe_times,
            }
        )
    return out


class FusionMLP(nn.Module):
    def __init__(self, in_dim: int, hidden: int = 64) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(hidden, hidden),
            nn.ReLU(),
            nn.Linear(hidden, len(CLASS_NAMES)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    f1s: List[float] = []
    for c in range(len(CLASS_NAMES)):
        tp = np.sum((y_true == c) & (y_pred == c))
        fp = np.sum((y_true != c) & (y_pred == c))
        fn = np.sum((y_true == c) & (y_pred != c))
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        f1s.append(float(f))
    return float(sum(f1s) / len(f1s)) if f1s else 0.0


class FocalLoss(nn.Module):
    def __init__(self, alpha: torch.Tensor, gamma: float = 2.0) -> None:
        super().__init__()
        self.alpha = alpha
        self.gamma = float(gamma)

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_raw = F.cross_entropy(logits, targets, reduction="none")
        pt = torch.exp(-ce_raw).clamp(min=1e-8, max=1.0)
        alpha_t = self.alpha[targets]
        loss = alpha_t * ((1.0 - pt) ** self.gamma) * ce_raw
        return loss.mean()


def main() -> None:
    parser = argparse.ArgumentParser(description="Train fusion v1 model from exported meta features.")
    parser.add_argument("--train-meta", required=True, help="meta_train.parquet")
    parser.add_argument("--val-meta", required=True, help="meta_val.parquet")
    parser.add_argument("--out-ckpt", required=True, help="Output model checkpoint .pt")
    parser.add_argument("--out-metrics", required=True, help="Output metrics json")
    parser.add_argument("--out-val-pred", required=True, help="Output val prediction jsonl")
    parser.add_argument("--out-train-log", default="", help="Optional output train log json")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=30, help="Early stopping patience on val macro-F1")
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--loss-type", choices=["ce", "focal"], default="ce", help="Classification loss type")
    parser.add_argument("--focal-gamma", type=float, default=2.0, help="Gamma for focal loss")
    parser.add_argument("--no-class-weight", action="store_true", help="Disable inverse-frequency class weighting")
    parser.add_argument(
        "--class-weights-override",
        default="",
        help="Optional comma-separated explicit class weights in CLASS_NAMES order: rear_end,lane_change,turn_conflict",
    )
    args = parser.parse_args()

    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    train_df = pd.read_parquet(Path(args.train_meta).resolve())
    val_df = pd.read_parquet(Path(args.val_meta).resolve())

    x_train, y_train, _ = build_xy(train_df)
    x_val, y_val, val_videos = build_xy(val_df)
    val_eval_context = build_eval_context_rows(val_df)

    if len(x_train) == 0 or len(x_val) == 0:
        raise RuntimeError("No 3-class labeled samples in train/val meta. Please finish annotation first.")
    if len(val_eval_context) != len(val_videos):
        raise RuntimeError("Validation context rows mismatch; please check meta export consistency.")

    mu = x_train.mean(axis=0, keepdims=True)
    std = x_train.std(axis=0, keepdims=True) + 1e-6
    x_train = (x_train - mu) / std
    x_val = (x_val - mu) / std

    device = torch.device("cpu")
    model = FusionMLP(x_train.shape[1]).to(device)
    cls_counts = np.bincount(y_train, minlength=len(CLASS_NAMES)).astype(np.float32)
    class_weight_source = "inverse_freq"
    if args.no_class_weight:
        class_weight_source = "disabled_all_ones"
        cls_weights = np.ones(len(CLASS_NAMES), dtype=np.float32)
    elif str(args.class_weights_override).strip():
        class_weight_source = "explicit_override"
        raw = [x.strip() for x in str(args.class_weights_override).split(",") if x.strip()]
        if len(raw) != len(CLASS_NAMES):
            raise ValueError(
                f"--class-weights-override expects {len(CLASS_NAMES)} values in order {CLASS_NAMES}, got {len(raw)}"
            )
        try:
            cls_weights = np.array([float(x) for x in raw], dtype=np.float32)
        except ValueError as exc:
            raise ValueError("--class-weights-override contains non-numeric values") from exc
        if np.any(cls_weights <= 0):
            raise ValueError("--class-weights-override values must all be > 0")
    else:
        cls_weights = cls_counts.sum() / np.maximum(cls_counts, 1.0)
        cls_weights = cls_weights / cls_weights.mean()
    cls_weight_tensor = torch.tensor(cls_weights, dtype=torch.float32, device=device)
    if args.loss_type == "focal":
        criterion = FocalLoss(alpha=cls_weight_tensor, gamma=float(args.focal_gamma))
    else:
        criterion = nn.CrossEntropyLoss(weight=cls_weight_tensor)
    optimizer = optim.Adam(model.parameters(), lr=args.lr)

    xtr = torch.tensor(x_train, dtype=torch.float32, device=device)
    ytr = torch.tensor(y_train, dtype=torch.long, device=device)
    xva = torch.tensor(x_val, dtype=torch.float32, device=device)

    best_state = None
    best_f1 = -1.0
    best_epoch = -1
    epochs_no_improve = 0
    history: List[Dict[str, Any]] = []
    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        logits = model(xtr)
        loss = criterion(logits, ytr)
        loss.backward()
        optimizer.step()

        model.eval()
        with torch.no_grad():
            val_logits = model(xva).cpu().numpy()
            val_pred = np.argmax(val_logits, axis=1)
            f1 = macro_f1(y_val, val_pred)
            train_loss = float(loss.item())
            improved = bool(f1 > best_f1)
            history.append(
                {
                    "epoch": int(epoch),
                    "train_loss": round(train_loss, 8),
                    "val_macro_f1": round(float(f1), 8),
                    "improved": improved,
                }
            )
            if f1 > best_f1:
                best_f1 = f1
                best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
                best_epoch = epoch
                epochs_no_improve = 0
            else:
                epochs_no_improve += 1

        if args.patience > 0 and epochs_no_improve >= args.patience:
            break

    assert best_state is not None
    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        logits = model(xva).cpu().numpy()
        probs = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = probs / probs.sum(axis=1, keepdims=True)
        pred = np.argmax(probs, axis=1)

    acc = float(np.mean(pred == y_val))
    f1 = macro_f1(y_val, pred)

    ckpt = {
        "model_state_dict": model.state_dict(),
        "feature_mean": mu.tolist(),
        "feature_std": std.tolist(),
        "class_names": CLASS_NAMES,
        "model_name": "fusion_v1_mlp",
    }
    out_ckpt = Path(args.out_ckpt).resolve()
    out_ckpt.parent.mkdir(parents=True, exist_ok=True)
    torch.save(ckpt, out_ckpt)

    out_pred = Path(args.out_val_pred).resolve()
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    with out_pred.open("w", encoding="utf-8") as f:
        for i in range(len(val_videos)):
            type_probs = {
                "rear_end": round(float(probs[i][0]), 6),
                "lane_change": round(float(probs[i][1]), 6),
                "turn_conflict": round(float(probs[i][2]), 6),
                "generic": 0.0,
            }
            ctx = val_eval_context[i]
            row = {
                "video": ctx["video"],
                "pred_type": CLASS_NAMES[int(pred[i])],
                "type_probs": type_probs,
                "pred_onset_time": round(float(ctx["pred_onset_time"]), 2),
                "pred_impact_time": round(float(ctx["pred_impact_time"]), 2),
                "pred_post_time": round(float(ctx["pred_post_time"]), 2),
                "lead_time_sec": round(float(ctx["lead_time_sec"]), 2),
                "risk_score": round(float(max(type_probs["rear_end"], type_probs["lane_change"], type_probs["turn_conflict"])), 6),
                "uncertainty": round(float(ctx["uncertainty"]), 6),
                "keyframe_times": ctx["keyframe_times"],
                "scene_tags": ctx["scene_tags"],
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    metrics = {
        "model": "fusion_v1_mlp",
        "n_train": int(len(y_train)),
        "n_val": int(len(y_val)),
        "val_accuracy": round(acc, 6),
        "val_macro_f1": round(f1, 6),
        "best_epoch": int(best_epoch),
        "epochs_ran": int(len(history)),
        "patience": int(args.patience),
        "seed": int(args.seed),
        "loss_type": str(args.loss_type),
        "focal_gamma": float(args.focal_gamma),
        "class_weights": [round(float(x), 6) for x in cls_weights.tolist()],
        "class_weight_enabled": bool(not args.no_class_weight),
        "class_weight_source": class_weight_source,
        "class_weights_override_raw": str(args.class_weights_override),
        "class_counts_train": {CLASS_NAMES[i]: int(cls_counts[i]) for i in range(len(CLASS_NAMES))},
        "train_meta": str(Path(args.train_meta).resolve()),
        "val_meta": str(Path(args.val_meta).resolve()),
        "checkpoint": str(out_ckpt),
    }
    out_metrics = Path(args.out_metrics).resolve()
    out_metrics.parent.mkdir(parents=True, exist_ok=True)
    out_metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    if str(args.out_train_log).strip():
        out_log = Path(args.out_train_log).resolve()
        out_log.parent.mkdir(parents=True, exist_ok=True)
        train_log_obj = {
            "model": "fusion_v1_mlp",
            "seed": int(args.seed),
            "lr": float(args.lr),
            "epochs_max": int(args.epochs),
            "patience": int(args.patience),
            "loss_type": str(args.loss_type),
            "focal_gamma": float(args.focal_gamma),
            "class_weight_enabled": bool(not args.no_class_weight),
            "class_weight_source": class_weight_source,
            "class_weights_override_raw": str(args.class_weights_override),
            "class_weights": [round(float(x), 6) for x in cls_weights.tolist()],
            "best_epoch": int(best_epoch),
            "best_val_macro_f1": round(float(best_f1), 8),
            "history": history,
        }
        out_log.write_text(json.dumps(train_log_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
