import argparse
import copy
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
        # Guard against NaN/Inf introduced by mixed feature schemas.
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

    scene_profile = str(row.get("scene_profile", "")).strip()
    if scene_profile and scene_profile.lower() != "custom":
        tags.append(scene_profile)

    extra_scene_tags = str(row.get("extra_scene_tags", "")).strip()
    if extra_scene_tags:
        parts = [p.strip() for p in extra_scene_tags.replace(";", ",").split(",") if p.strip()]
        tags.extend(parts if parts else [extra_scene_tags])

    dedup: List[str] = []
    seen = set()
    for t in tags:
        if not t:
            continue
        if t not in seen:
            seen.add(t)
            dedup.append(t)
    return dedup


def load_rule_pred_map(path: Optional[Path]) -> Dict[str, Dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    rows = load_jsonl(path)
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        out[normalize_video_key(r.get("video", ""))] = r
    return out


def load_hard_sample_weight_map(path: Optional[Path]) -> Dict[str, float]:
    if path is None or not path.exists():
        return {}
    rows = load_jsonl(path)
    out: Dict[str, float] = {}
    for row in rows:
        sample_id = str(row.get("sample_id", "")).strip()
        if not sample_id:
            continue
        w = safe_float(
            row.get(
                "sample_weight",
                row.get("weight", row.get("hard_weight", 1.0)),
            ),
            1.0,
        )
        out[sample_id] = max(1.0, float(w))
    return out


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
    # Blend multiclass turn probability with dedicated turn-vs-nonturn head.
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
        # x: [B, T, D]
        seq_out, _ = self.lstm(x)
        attn_scores = self.attn(seq_out).squeeze(-1)  # [B, T]
        attn_weights = torch.softmax(attn_scores, dim=1)
        context = torch.sum(seq_out * attn_weights.unsqueeze(-1), dim=1)  # [B, 2H]
        logits = self.head(context)
        turn_logit = self.turn_head(context).squeeze(-1)
        return logits, turn_logit, attn_weights


class FocalLoss(nn.Module):
    def __init__(self, class_weights: Optional[torch.Tensor], gamma: float = 2.0, reduction: str = "mean") -> None:
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


def build_records_from_split(
    split_rows: List[Dict[str, Any]],
    feature_map: Dict[str, Dict[str, Any]],
    feature_cols: List[str],
    hard_weight_map: Optional[Dict[str, float]] = None,
    hard_sample_boost: float = 1.0,
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
        hard_w = 1.0
        if hard_weight_map is not None:
            hard_w = float(hard_weight_map.get(sample_id, 1.0))
            if hard_w > 1.0:
                hard_w = hard_w * max(1.0, float(hard_sample_boost))
        records.append(
            {
                "sample_id": sample_id,
                "video": str(row.get("video", sample_id)).strip(),
                "accident_type": accident_type,
                "label_id": CLASS_TO_ID[accident_type],
                "feature": vec,
                "sample_weight": max(1.0, float(hard_w)),
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
    parser = argparse.ArgumentParser(description="Train BiLSTM+Attention on fold split with strict no-leak split.")
    parser.add_argument("--feature-csv", required=True, help="CSV with sample_id/accident_type/feature_* columns")
    parser.add_argument("--train-split", required=True, help="fold{i}_train.jsonl")
    parser.add_argument("--val-split", required=True, help="fold{i}_val.jsonl")
    parser.add_argument("--out-ckpt", required=True, help="Output checkpoint .pt")
    parser.add_argument("--out-metrics", required=True, help="Output metrics json")
    parser.add_argument("--out-val-pred", required=True, help="Output val prediction jsonl")
    parser.add_argument("--out-train-log", default="", help="Optional train log json")
    parser.add_argument("--rule-pred", default="", help="Optional rule prediction jsonl to inherit timing/keyframe fields")
    parser.add_argument("--hard-samples", default="", help="Optional hard sample weight jsonl (from previous OOF)")
    parser.add_argument("--hard-sample-boost", type=float, default=1.0, help="Extra multiplier on hard sample weights")
    parser.add_argument("--use-gt-timing-fallback", action="store_true", help="Use split GT timing if rule pred missing")
    parser.add_argument("--seq-len", type=int, default=0, help="Sequence length for reshaping feature_*; 0=auto")
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--mlp-hidden", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=20)
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
    parser.add_argument(
        "--turn-bin-loss-weight",
        type=float,
        default=0.4,
        help="Loss weight for turn-vs-nonturn BCE auxiliary head.",
    )
    parser.add_argument(
        "--turn-fuse-alpha",
        type=float,
        default=0.6,
        help="Final turn prob = alpha*cls_turn + (1-alpha)*turn_bin.",
    )
    parser.add_argument("--turn-router-min-prob", type=float, default=0.0, help="Route to turn if p_turn >= min_prob.")
    parser.add_argument(
        "--turn-router-margin",
        type=float,
        default=0.0,
        help="Route to turn if max_prob - p_turn <= margin (used with --turn-router-min-prob).",
    )
    parser.add_argument(
        "--selection-mode",
        choices=["macro_f1", "macro_plus_min_recall"],
        default="macro_f1",
        help="Checkpoint selection score.",
    )
    parser.add_argument(
        "--selection-min-recall-weight",
        type=float,
        default=0.5,
        help="Weight for min class recall when selection-mode=macro_plus_min_recall.",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    set_seed(int(args.seed))

    feature_csv = Path(args.feature_csv).resolve()
    train_split = Path(args.train_split).resolve()
    val_split = Path(args.val_split).resolve()
    out_ckpt = Path(args.out_ckpt).resolve()
    out_metrics = Path(args.out_metrics).resolve()
    out_val_pred = Path(args.out_val_pred).resolve()
    out_train_log = Path(args.out_train_log).resolve() if str(args.out_train_log).strip() else None
    rule_pred = Path(args.rule_pred).resolve() if str(args.rule_pred).strip() else None
    hard_samples = Path(args.hard_samples).resolve() if str(args.hard_samples).strip() else None

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

    hard_weight_map = load_hard_sample_weight_map(hard_samples)

    train_rows = load_jsonl(train_split)
    val_rows = load_jsonl(val_split)
    train_records, train_missing_ids = build_records_from_split(
        train_rows,
        feature_map,
        feature_cols,
        hard_weight_map=hard_weight_map,
        hard_sample_boost=float(args.hard_sample_boost),
    )
    val_records, val_missing_ids = build_records_from_split(
        val_rows,
        feature_map,
        feature_cols,
        hard_weight_map=None,
        hard_sample_boost=1.0,
    )

    if not train_records or not val_records:
        raise RuntimeError(
            "No usable train/val samples after joining split with feature CSV. "
            f"train={len(train_records)} val={len(val_records)}"
        )

    x_train_flat = np.stack([r["feature"] for r in train_records]).astype(np.float32)
    x_val_flat = np.stack([r["feature"] for r in val_records]).astype(np.float32)
    y_train = np.array([int(r["label_id"]) for r in train_records], dtype=np.int64)
    y_val = np.array([int(r["label_id"]) for r in val_records], dtype=np.int64)
    y_train_turn = np.array([1.0 if int(r["label_id"]) == CLASS_TO_ID["turn_conflict"] else 0.0 for r in train_records], dtype=np.float32)
    y_val_turn = np.array([1.0 if int(r["label_id"]) == CLASS_TO_ID["turn_conflict"] else 0.0 for r in val_records], dtype=np.float32)
    sample_w_train = np.array([float(r.get("sample_weight", 1.0)) for r in train_records], dtype=np.float32)
    sample_w_val = np.ones(len(val_records), dtype=np.float32)

    mu = x_train_flat.mean(axis=0, keepdims=True)
    std = x_train_flat.std(axis=0, keepdims=True) + 1e-6
    x_train_flat = (x_train_flat - mu) / std
    x_val_flat = (x_val_flat - mu) / std

    seq_len = int(args.seq_len)
    if seq_len <= 0:
        seq_len = infer_seq_len(int(x_train_flat.shape[1]))
    x_train = build_sequence_tensor(x_train_flat, seq_len)
    x_val = build_sequence_tensor(x_val_flat, seq_len)
    input_dim = int(x_train.shape[2])

    train_ds = SequenceDataset(x_train, y_train, y_train_turn, sample_w_train)
    val_ds = SequenceDataset(x_val, y_val, y_val_turn, sample_w_val)
    train_loader = DataLoader(train_ds, batch_size=int(args.batch_size), shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=max(1, int(args.batch_size) * 2), shuffle=False)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = BiLSTMAttentionClassifier(
        input_dim=input_dim,
        hidden_size=int(args.hidden_size),
        num_layers=int(args.num_layers),
        dropout=float(args.dropout),
        num_classes=len(CLASS_NAMES),
        mlp_hidden=int(args.mlp_hidden),
    ).to(device)

    class_counts = np.bincount(y_train, minlength=len(CLASS_NAMES)).astype(np.float32)
    if args.no_class_weight:
        class_weights_np = np.ones(len(CLASS_NAMES), dtype=np.float32)
        class_weights_tensor = None
    else:
        inv_freq = class_counts.sum() / np.maximum(class_counts, 1.0)
        inv_freq = inv_freq / np.maximum(inv_freq.mean(), 1e-6)

        alpha = float(args.class_weight_alpha)
        alpha = min(1.0, max(0.0, alpha))
        class_weights_np = ((1.0 - alpha) * inv_freq) + (alpha * np.ones_like(inv_freq))

        floor_val = max(0.0, float(args.class_weight_floor))
        if floor_val > 0.0:
            class_weights_np = np.maximum(class_weights_np, floor_val)

        turn_idx = CLASS_TO_ID["turn_conflict"]
        turn_boost = max(0.0, float(args.turn_weight_boost))
        class_weights_np[turn_idx] = class_weights_np[turn_idx] * turn_boost

        class_weights_np = class_weights_np / np.maximum(class_weights_np.mean(), 1e-6)
        class_weights_tensor = torch.tensor(class_weights_np, dtype=torch.float32, device=device)

    if str(args.loss_type) == "focal":
        criterion = FocalLoss(class_weights=class_weights_tensor, gamma=float(args.focal_gamma), reduction="none")
    else:
        weight_tensor = None if class_weights_tensor is None else class_weights_tensor
        criterion = nn.CrossEntropyLoss(weight=weight_tensor, reduction="none")

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(args.lr),
        weight_decay=float(args.weight_decay),
    )

    best_state = None
    best_epoch = -1
    best_stats: Dict[str, Any] = {}
    best_val_probs: Optional[np.ndarray] = None
    best_val_pred: Optional[np.ndarray] = None
    history: List[Dict[str, Any]] = []
    epochs_no_improve = 0
    best_score = -1.0

    for epoch in range(1, int(args.epochs) + 1):
        model.train()
        train_loss_acc = 0.0
        train_cls_loss_acc = 0.0
        train_turn_loss_acc = 0.0
        train_n = 0
        for xb, yb, y_turn_b, sample_w_b in train_loader:
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
            train_loss_acc += float(loss.item()) * bs
            train_cls_loss_acc += float(cls_loss.item()) * bs
            train_turn_loss_acc += float(turn_loss.item()) * bs
            train_n += bs

        model.eval()
        val_logits_list: List[np.ndarray] = []
        val_turn_logits_list: List[np.ndarray] = []
        with torch.no_grad():
            for xb, _, _, _ in val_loader:
                xb = xb.to(device)
                logits, turn_logit, _ = model(xb)
                val_logits_list.append(logits.cpu().numpy())
                val_turn_logits_list.append(turn_logit.cpu().numpy())
        val_logits = np.concatenate(val_logits_list, axis=0)
        val_logits = val_logits[: len(y_val)]
        val_logits = val_logits.astype(np.float64)
        val_logits -= np.max(val_logits, axis=1, keepdims=True)
        val_exp = np.exp(val_logits)
        val_cls_probs = val_exp / np.maximum(np.sum(val_exp, axis=1, keepdims=True), 1e-12)
        if args.dual_turn_head:
            val_turn_logits = np.concatenate(val_turn_logits_list, axis=0)[: len(y_val)].astype(np.float64)
            val_turn_probs = 1.0 / (1.0 + np.exp(-val_turn_logits))
            val_probs = fuse_turn_probs(
                val_cls_probs,
                val_turn_probs,
                turn_idx=CLASS_TO_ID["turn_conflict"],
                alpha=float(args.turn_fuse_alpha),
            )
        else:
            val_probs = val_cls_probs

        val_pred_raw = np.argmax(val_probs, axis=1)
        val_pred = apply_turn_router(
            val_probs,
            val_pred_raw,
            turn_idx=CLASS_TO_ID["turn_conflict"],
            min_prob=float(args.turn_router_min_prob),
            margin=float(args.turn_router_margin),
        )
        stats = build_classification_stats(y_val, val_pred)
        recalls = [float(stats["per_class"][c]["recall"]) for c in CLASS_NAMES]
        min_recall = min(recalls) if recalls else 0.0
        if str(args.selection_mode) == "macro_plus_min_recall":
            current_score = float(stats["macro_f1"]) + (float(args.selection_min_recall_weight) * min_recall)
        else:
            current_score = float(stats["macro_f1"])

        train_loss = train_loss_acc / max(1, train_n)
        train_cls_loss = train_cls_loss_acc / max(1, train_n)
        train_turn_loss = train_turn_loss_acc / max(1, train_n)
        current_macro_f1 = float(stats["macro_f1"])
        improved = best_state is None or current_score > float(best_score)
        history.append(
            {
                "epoch": int(epoch),
                "train_loss": round(float(train_loss), 8),
                "train_cls_loss": round(float(train_cls_loss), 8),
                "train_turn_loss": round(float(train_turn_loss), 8),
                "val_accuracy": round(float(stats["accuracy"]), 8),
                "val_macro_f1": round(float(current_macro_f1), 8),
                "val_turn_recall": round(float(stats["per_class"]["turn_conflict"]["recall"]), 8),
                "val_min_recall": round(float(min_recall), 8),
                "selection_score": round(float(current_score), 8),
                "improved": bool(improved),
            }
        )
        if improved:
            best_state = copy.deepcopy(model.state_dict())
            best_epoch = int(epoch)
            best_stats = stats
            best_score = float(current_score)
            best_val_probs = val_probs.copy()
            best_val_pred = val_pred.copy()
            epochs_no_improve = 0
        else:
            epochs_no_improve += 1

        if int(args.patience) > 0 and epochs_no_improve >= int(args.patience):
            break

    if best_state is None or best_val_probs is None or best_val_pred is None:
        raise RuntimeError("Training failed: no best model state captured.")

    model.load_state_dict(best_state)
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

    rule_map = load_rule_pred_map(rule_pred)
    out_val_pred.parent.mkdir(parents=True, exist_ok=True)
    with out_val_pred.open("w", encoding="utf-8") as f:
        for i, rec in enumerate(val_records):
            pred_id = int(best_val_pred[i])
            pred_type = CLASS_NAMES[pred_id]
            p = best_val_probs[i]
            type_probs = {
                "rear_end": round(float(p[0]), 6),
                "lane_change": round(float(p[1]), 6),
                "turn_conflict": round(float(p[2]), 6),
                "generic": 0.0,
            }

            video = normalize_video_key(rec["video"])
            rule_row = rule_map.get(video)
            if rule_row is not None:
                pred_onset = safe_float(rule_row.get("pred_onset_time", 0.0))
                pred_impact = safe_float(rule_row.get("pred_impact_time", 0.0))
                pred_post = safe_float(rule_row.get("pred_post_time", 0.0))
                lead_time = safe_float(rule_row.get("lead_time_sec", 0.0))
                keyframe_times = rule_row.get("keyframe_times", [pred_impact])
                scene_tags = rule_row.get("scene_tags", rec["scene_tags"])
                timing_source = "rule_inherited"
            elif args.use_gt_timing_fallback:
                pred_onset = safe_float(rec["onset_time"], 0.0)
                pred_impact = safe_float(rec["impact_time"], 0.0)
                pred_post = safe_float(rec["post_time"], 0.0)
                lead_time = max(0.0, pred_impact - pred_onset)
                keyframe_times = [round(pred_onset, 2), round(pred_impact, 2), round(pred_post, 2)]
                scene_tags = rec["scene_tags"]
                timing_source = "gt_fallback"
            else:
                pred_onset = 0.0
                pred_impact = 0.0
                pred_post = 0.0
                lead_time = 0.0
                keyframe_times = [0.0]
                scene_tags = rec["scene_tags"]
                timing_source = "zero_fallback"

            out_row = {
                "video": video,
                "pred_type": pred_type,
                "type_probs": type_probs,
                "pred_onset_time": round(float(pred_onset), 3),
                "pred_impact_time": round(float(pred_impact), 3),
                "pred_post_time": round(float(pred_post), 3),
                "lead_time_sec": round(float(max(0.0, lead_time)), 3),
                "risk_score": round(float(max(type_probs["rear_end"], type_probs["lane_change"], type_probs["turn_conflict"])), 6),
                "uncertainty": round(float(1.0 - max(type_probs["rear_end"], type_probs["lane_change"], type_probs["turn_conflict"])), 6),
                "keyframe_times": keyframe_times if isinstance(keyframe_times, list) else [safe_float(pred_impact, 0.0)],
                "scene_tags": scene_tags if isinstance(scene_tags, list) else rec["scene_tags"],
                "sample_id": rec["sample_id"],
                "timing_source": timing_source,
            }
            f.write(json.dumps(out_row, ensure_ascii=False) + "\n")

    metrics_obj: Dict[str, Any] = {
        "model": "bilstm_attention_v33",
        "feature_csv": str(feature_csv),
        "train_split": str(train_split),
        "val_split": str(val_split),
        "rule_pred": str(rule_pred) if rule_pred else "",
        "hard_samples": str(hard_samples) if hard_samples else "",
        "seed": int(args.seed),
        "device": str(device),
        "seq_len": int(seq_len),
        "input_dim": int(input_dim),
        "n_train": int(len(train_records)),
        "n_val": int(len(val_records)),
        "n_train_hard_weighted": int(sum(1 for r in train_records if float(r.get("sample_weight", 1.0)) > 1.0)),
        "train_sample_weight_mean": round(float(np.mean(sample_w_train)), 6),
        "train_sample_weight_max": round(float(np.max(sample_w_train)), 6),
        "n_train_missing_feature": int(len(train_missing_ids)),
        "n_val_missing_feature": int(len(val_missing_ids)),
        "epochs_max": int(args.epochs),
        "epochs_ran": int(len(history)),
        "best_epoch": int(best_epoch),
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
        "hard_sample_boost": float(args.hard_sample_boost),
        "class_weights": [round(float(x), 6) for x in class_weights_np.tolist()],
        "class_counts_train": {CLASS_NAMES[i]: int(class_counts[i]) for i in range(len(CLASS_NAMES))},
        "turn_router_min_prob": float(args.turn_router_min_prob),
        "turn_router_margin": float(args.turn_router_margin),
        "selection_mode": str(args.selection_mode),
        "selection_min_recall_weight": float(args.selection_min_recall_weight),
        "best_selection_score": round(float(best_score), 6),
        "val_accuracy": round(float(best_stats["accuracy"]), 6),
        "val_macro_f1": round(float(best_stats["macro_f1"]), 6),
        "val_per_class": best_stats["per_class"],
        "output_checkpoint": str(out_ckpt),
        "output_val_pred": str(out_val_pred),
    }
    out_metrics.parent.mkdir(parents=True, exist_ok=True)
    out_metrics.write_text(json.dumps(metrics_obj, ensure_ascii=False, indent=2), encoding="utf-8")

    if out_train_log is not None:
        out_train_log.parent.mkdir(parents=True, exist_ok=True)
        out_train_log.write_text(
            json.dumps(
                {
                    "model": "bilstm_attention_v33",
                    "history": history,
                    "best_epoch": int(best_epoch),
                    "best_val_accuracy": round(float(best_stats["accuracy"]), 8),
                    "best_val_macro_f1": round(float(best_stats["macro_f1"]), 8),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    print(json.dumps(metrics_obj, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
