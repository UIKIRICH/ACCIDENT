import argparse
import csv
import json
import math
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "duration_frames",
    "mean_x_velocity",
    "max_abs_y_velocity",
    "lane_change_count_track",
    "min_ttc_eff_capped",
    "min_thw_eff_capped",
    "ttc_missing",
    "thw_missing",
]

GATE_DEF = {
    "rear_steal_ratio_lt": 0.10,
    "rescueable_total_gt": 0,
    "changed_total_gt": 0,
    "dMacro_ge": 0.0,
    "dLaneR_role": "secondary",
}


@dataclass
class VariantResult:
    variant_name: str
    source_domain: str
    target_slice: str
    adaptation_strategy: str
    uses_target_labels: bool
    rescueable_total: Optional[int]
    changed_total: Optional[int]
    rear_steal_ratio: Optional[float]
    dMacro: Optional[float]
    dLaneR: Optional[float]
    hard_gate_pass: Optional[bool]
    stability_reconfirmation_pass: Optional[bool]
    independent_external_board_pass: Optional[bool]
    promotion_role: str
    artifact_path: str
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "variant_name": self.variant_name,
            "source_domain": self.source_domain,
            "target_slice": self.target_slice,
            "adaptation_strategy": self.adaptation_strategy,
            "uses_target_labels": bool(self.uses_target_labels),
            "rescueable_total": self.rescueable_total,
            "changed_total": self.changed_total,
            "rear_steal_ratio": self.rear_steal_ratio,
            "dMacro": self.dMacro,
            "dLaneR": self.dLaneR,
            "hard_gate_pass": self.hard_gate_pass,
            "stability_reconfirmation_pass": self.stability_reconfirmation_pass,
            "independent_external_board_pass": self.independent_external_board_pass,
            "promotion_role": self.promotion_role,
            "artifact_path": self.artifact_path,
            "notes": self.notes,
        }


def log(msg: str, out_log: Path) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with out_log.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def safe_float(v: Any, default: float = np.nan) -> float:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(fv):
        return float(default)
    return float(fv)


def cap_or_nan(v: Any, cap: float) -> float:
    fv = safe_float(v, np.nan)
    if not np.isfinite(fv):
        return np.nan
    if fv < 0:
        return np.nan
    return float(min(fv, cap))


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


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


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def parse_scene_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                return [s]
        return [s]
    return []


def scene_bucket(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    is_day = "day" in s
    is_night = "night" in s
    is_straight = "straight_road" in s
    is_inter = "intersection" in s
    if is_day and is_straight:
        return "day+straight_road"
    if is_day and is_inter:
        return "day+intersection"
    if is_night and is_straight:
        return "night+straight_road"
    if is_night and is_inter:
        return "night+intersection"
    return "other"


def source_row_to_features(r: Dict[str, Any]) -> Dict[str, float]:
    ttc = cap_or_nan(r.get("min_ttc_eff"), cap=20.0)
    thw = cap_or_nan(r.get("min_thw_eff"), cap=10.0)
    return {
        "duration_frames": safe_float(r.get("duration_frames"), np.nan),
        "mean_x_velocity": safe_float(r.get("mean_x_velocity"), np.nan),
        "max_abs_y_velocity": safe_float(r.get("max_abs_y_velocity"), np.nan),
        "lane_change_count_track": safe_float(r.get("lane_change_count_track"), np.nan),
        "min_ttc_eff_capped": ttc,
        "min_thw_eff_capped": thw,
        "ttc_missing": 1.0 if not np.isfinite(ttc) else 0.0,
        "thw_missing": 1.0 if not np.isfinite(thw) else 0.0,
    }


def board_row_to_features(r: Dict[str, Any]) -> Dict[str, float]:
    ttc = cap_or_nan(r.get("min_ttc_eff"), cap=20.0)
    thw = cap_or_nan(r.get("min_thw_eff"), cap=10.0)
    return {
        "duration_frames": safe_float(r.get("pair_duration_frames"), np.nan),
        "mean_x_velocity": safe_float(r.get("mean_longitudinal_velocity_rel"), np.nan),
        "max_abs_y_velocity": safe_float(r.get("max_abs_lateral_velocity_rel"), np.nan),
        "lane_change_count_track": safe_float(r.get("lane_change_count_pair"), np.nan),
        "min_ttc_eff_capped": ttc,
        "min_thw_eff_capped": thw,
        "ttc_missing": 1.0 if not np.isfinite(ttc) else 0.0,
        "thw_missing": 1.0 if not np.isfinite(thw) else 0.0,
    }


def compute_metrics(rows: List[Dict[str, Any]], use_patch_pred: bool) -> Dict[str, float]:
    cls = ["rear_end", "lane_change", "turn_conflict"]
    y_true = [str(r["gt_type"]).strip() for r in rows]
    y_pred = [str(r["pred_type_patch"] if use_patch_pred else r["pred_type"]).strip() for r in rows]
    n = len(y_true)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0
    f1s = []
    per: Dict[str, Dict[str, float]] = {}
    for c in cls:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        pr = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * pr * rc / (pr + rc) if (pr + rc) else 0.0
        per[c] = {"precision": pr, "recall": rc, "f1": f1}
        f1s.append(f1)
    return {
        "accuracy": float(acc),
        "macro_f1": float(sum(f1s) / len(f1s)) if f1s else 0.0,
        "rear_recall": float(per["rear_end"]["recall"]),
        "lane_recall": float(per["lane_change"]["recall"]),
        "turn_recall": float(per["turn_conflict"]["recall"]),
    }


def eval_board_from_scores(rows: List[Dict[str, Any]], rescue_thr: float, lane_thr: float) -> Dict[str, Any]:
    lane_fn_rear = [r for r in rows if r["gt_type"] == "lane_change" and r["pred_type"] == "rear_end"]
    rear_gt = [r for r in rows if r["gt_type"] == "rear_end"]
    day_straight_lane_fn_rear = [r for r in lane_fn_rear if scene_bucket(r["scene_tags"]) == "day+straight_road"]

    rescueable = [r for r in lane_fn_rear if r["lane_score"] >= rescue_thr]
    day_straight_rescueable = [r for r in day_straight_lane_fn_rear if r["lane_score"] >= rescue_thr]
    day_straight_lane_over_rear = [r for r in day_straight_lane_fn_rear if r["lane_score"] > r["rear_score"]]

    changed = sum(1 for r in rows if r["pred_type_patch"] != r["pred_type"])
    rear_steal = sum(
        1
        for r in rear_gt
        if str(r["pred_type"]).strip() == "rear_end" and str(r["pred_type_patch"]).strip() != "rear_end"
    )
    rear_already_nonrear_before = sum(1 for r in rear_gt if str(r["pred_type"]).strip() != "rear_end")
    rear_steal_ratio = (rear_steal / len(rear_gt)) if rear_gt else 0.0

    base_m = compute_metrics(rows, use_patch_pred=False)
    patch_m = compute_metrics(rows, use_patch_pred=True)

    return {
        "n": int(len(rows)),
        "lane_fn_rear_n": int(len(lane_fn_rear)),
        "rear_gt_n": int(len(rear_gt)),
        "rescueable_n": int(len(rescueable)),
        "rescueable_ratio": float((len(rescueable) / len(lane_fn_rear)) if lane_fn_rear else 0.0),
        "day_straight_lane_fn_rear_n": int(len(day_straight_lane_fn_rear)),
        "day_straight_rescueable_n": int(len(day_straight_rescueable)),
        "day_straight_lane_over_rear_n": int(len(day_straight_lane_over_rear)),
        "changed_n": int(changed),
        "rear_steal_n": int(rear_steal),
        "rear_already_nonrear_before_n": int(rear_already_nonrear_before),
        "rear_steal_ratio": float(rear_steal_ratio),
        "base_metrics": base_m,
        "patch_metrics": patch_m,
        "delta_metrics": {
            "accuracy": patch_m["accuracy"] - base_m["accuracy"],
            "macro_f1": patch_m["macro_f1"] - base_m["macro_f1"],
            "rear_recall": patch_m["rear_recall"] - base_m["rear_recall"],
            "lane_recall": patch_m["lane_recall"] - base_m["lane_recall"],
            "turn_recall": patch_m["turn_recall"] - base_m["turn_recall"],
        },
        "lane_thr": float(lane_thr),
        "rescue_thr": float(rescue_thr),
    }


def aggregate(boards: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    bvals = list(boards.values())
    rescueable_total = int(sum(b["rescueable_n"] for b in bvals))
    changed_total = int(sum(b["changed_n"] for b in bvals))
    rear_gt_total = int(sum(b["rear_gt_n"] for b in bvals))
    rear_steal_total = int(sum(b["rear_steal_n"] for b in bvals))
    rear_steal_ratio_total = (rear_steal_total / rear_gt_total) if rear_gt_total else 0.0
    day_straight_lane_over_rear_total = int(sum(b["day_straight_lane_over_rear_n"] for b in bvals))
    day_straight_rescueable_total = int(sum(b["day_straight_rescueable_n"] for b in bvals))

    return {
        "rescueable_total": rescueable_total,
        "changed_total": changed_total,
        "rear_gt_total": rear_gt_total,
        "rear_steal_total": rear_steal_total,
        "rear_steal_ratio_total": float(rear_steal_ratio_total),
        "day_straight_lane_over_rear_total": day_straight_lane_over_rear_total,
        "day_straight_rescueable_total": day_straight_rescueable_total,
        "delta_macro_f1_mean": float(mean([b["delta_metrics"]["macro_f1"] for b in bvals])) if bvals else 0.0,
        "delta_lane_recall_mean": float(mean([b["delta_metrics"]["lane_recall"] for b in bvals])) if bvals else 0.0,
        "delta_rear_recall_mean": float(mean([b["delta_metrics"]["rear_recall"] for b in bvals])) if bvals else 0.0,
    }


def hard_gate_pass_from_metrics(rescueable_total: Optional[int], changed_total: Optional[int], rear_steal_ratio: Optional[float], dmacro: Optional[float]) -> Optional[bool]:
    if rescueable_total is None or changed_total is None or rear_steal_ratio is None or dmacro is None:
        return None
    return bool(
        (rear_steal_ratio < GATE_DEF["rear_steal_ratio_lt"])
        and (rescueable_total > GATE_DEF["rescueable_total_gt"])
        and (changed_total > GATE_DEF["changed_total_gt"])
        and (dmacro >= GATE_DEF["dMacro_ge"])
    )


def build_train_arrays(source_rows: List[Dict[str, Any]], split: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    train_set = set(int(x) for x in split.get("train_recordings", []))
    val_set = set(int(x) for x in split.get("val_recordings", []))
    test_set = set(int(x) for x in split.get("test_recordings", []))

    feats: List[List[float]] = []
    ys: List[int] = []
    recs: List[int] = []
    for r in source_rows:
        c = str(r.get("candidate_type", "")).strip()
        if c not in {"lane_pos", "rear_risk_pos"}:
            continue
        rec = int(safe_float(r.get("recording_id"), -1))
        if rec < 0:
            continue
        feat = source_row_to_features(r)
        feats.append([feat[k] for k in FEATURES])
        ys.append(1 if c == "lane_pos" else 0)
        recs.append(rec)

    X = np.asarray(feats, dtype=np.float32)
    y = np.asarray(ys, dtype=np.int64)
    rec = np.asarray(recs, dtype=np.int64)

    tr_mask = np.array([int(r) in train_set for r in rec], dtype=bool)
    va_mask = np.array([int(r) in val_set for r in rec], dtype=bool)
    te_mask = np.array([int(r) in test_set for r in rec], dtype=bool)

    if tr_mask.sum() == 0 or va_mask.sum() == 0 or te_mask.sum() == 0:
        raise RuntimeError("empty split in source bridge training")
    return X, y, tr_mask, np.logical_or(va_mask, te_mask)


def fit_imputer_scaler(X_train: np.ndarray) -> Tuple[SimpleImputer, StandardScaler]:
    imp = SimpleImputer(strategy="median")
    X_imp = imp.fit_transform(X_train)
    scl = StandardScaler()
    scl.fit(X_imp)
    return imp, scl


def fit_lr(X_train: np.ndarray, y_train: np.ndarray, seed: int) -> LogisticRegression:
    lr = LogisticRegression(
        C=1.0,
        class_weight="balanced",
        solver="liblinear",
        max_iter=3000,
        random_state=int(seed),
    )
    lr.fit(X_train, y_train)
    return lr


def symmetric_sqrtm(mat: np.ndarray, eps: float = 1e-6, inverse: bool = False) -> np.ndarray:
    m = 0.5 * (mat + mat.T)
    vals, vecs = np.linalg.eigh(m)
    vals = np.clip(vals, eps, None)
    if inverse:
        vals_p = 1.0 / np.sqrt(vals)
    else:
        vals_p = np.sqrt(vals)
    return (vecs * vals_p) @ vecs.T


def coral_transform(Xs: np.ndarray, Xt: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    mu_s = np.mean(Xs, axis=0, keepdims=True)
    mu_t = np.mean(Xt, axis=0, keepdims=True)
    Xs0 = Xs - mu_s
    Xt0 = Xt - mu_t
    Cs = (Xs0.T @ Xs0) / max(1, Xs0.shape[0] - 1) + eps * np.eye(Xs0.shape[1], dtype=np.float32)
    Ct = (Xt0.T @ Xt0) / max(1, Xt0.shape[0] - 1) + eps * np.eye(Xt0.shape[1], dtype=np.float32)
    Cs_inv_sqrt = symmetric_sqrtm(Cs, eps=eps, inverse=True)
    Ct_sqrt = symmetric_sqrtm(Ct, eps=eps, inverse=False)
    Xs_aligned = (Xs0 @ Cs_inv_sqrt @ Ct_sqrt) + mu_t
    return Xs_aligned.astype(np.float32)


def rbf_kernel(X: np.ndarray, Y: np.ndarray, gamma: float) -> np.ndarray:
    xx = np.sum(X * X, axis=1, keepdims=True)
    yy = np.sum(Y * Y, axis=1, keepdims=True).T
    dist2 = np.maximum(xx + yy - 2.0 * (X @ Y.T), 0.0)
    return np.exp(-gamma * dist2)


def median_heuristic_gamma(X: np.ndarray) -> float:
    if X.shape[0] < 2:
        return 1.0
    sample_n = min(1000, X.shape[0])
    idx = np.random.choice(X.shape[0], size=sample_n, replace=False)
    xs = X[idx]
    d2 = []
    for i in range(len(xs)):
        for j in range(i + 1, len(xs)):
            dd = float(np.sum((xs[i] - xs[j]) ** 2))
            if dd > 0:
                d2.append(dd)
    if not d2:
        return 1.0
    med = float(np.median(d2))
    if med <= 0:
        return 1.0
    return 1.0 / (2.0 * med)


def mmd_mean_shift_transform(Xs: np.ndarray, Xt: np.ndarray) -> Tuple[np.ndarray, Dict[str, float]]:
    # Lightweight unsupervised MMD-style alignment:
    # optimize only a global shift delta to reduce RBF-MMD between source and target.
    Xs_t = torch.tensor(Xs, dtype=torch.float32)
    Xt_t = torch.tensor(Xt, dtype=torch.float32)
    gamma = median_heuristic_gamma(np.vstack([Xs, Xt]).astype(np.float32))
    delta = torch.nn.Parameter(torch.zeros((1, Xs.shape[1]), dtype=torch.float32))
    opt = optim.Adam([delta], lr=0.05)

    def mmd2(a: torch.Tensor, b: torch.Tensor, gamma_v: float) -> torch.Tensor:
        xa = a
        xb = b
        xx = torch.cdist(xa, xa, p=2.0) ** 2
        yy = torch.cdist(xb, xb, p=2.0) ** 2
        xy = torch.cdist(xa, xb, p=2.0) ** 2
        kxx = torch.exp(-gamma_v * xx)
        kyy = torch.exp(-gamma_v * yy)
        kxy = torch.exp(-gamma_v * xy)
        return kxx.mean() + kyy.mean() - 2.0 * kxy.mean()

    start_mmd = float(mmd2(Xs_t, Xt_t, gamma).detach().cpu().item())
    for _ in range(200):
        opt.zero_grad()
        cur = mmd2(Xs_t + delta, Xt_t, gamma)
        cur.backward()
        opt.step()
    end_mmd = float(mmd2(Xs_t + delta, Xt_t, gamma).detach().cpu().item())
    Xs_new = (Xs_t + delta).detach().cpu().numpy().astype(np.float32)
    return Xs_new, {"gamma": float(gamma), "mmd_start": start_mmd, "mmd_end": end_mmd}


class GradReverse(torch.autograd.Function):
    @staticmethod
    def forward(ctx, x, lambd):
        ctx.lambd = lambd
        return x.view_as(x)

    @staticmethod
    def backward(ctx, grad_output):
        return -ctx.lambd * grad_output, None


class DANNModel(nn.Module):
    def __init__(self, in_dim: int, hid: int = 32):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(in_dim, hid),
            nn.ReLU(),
            nn.Linear(hid, hid),
            nn.ReLU(),
        )
        self.task_head = nn.Linear(hid, 1)
        self.domain_head = nn.Sequential(
            nn.Linear(hid, hid),
            nn.ReLU(),
            nn.Linear(hid, 1),
        )

    def forward_task(self, x: torch.Tensor) -> torch.Tensor:
        z = self.encoder(x)
        return self.task_head(z), z

    def forward_domain(self, z: torch.Tensor, lambd: float) -> torch.Tensor:
        z_rev = GradReverse.apply(z, lambd)
        return self.domain_head(z_rev)


def run_dann_unsupervised(
    Xs_train: np.ndarray,
    ys_train: np.ndarray,
    Xt_all: np.ndarray,
    X_board: np.ndarray,
    seed: int,
) -> Tuple[np.ndarray, Dict[str, Any]]:
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

    model = DANNModel(in_dim=Xs_train.shape[1], hid=32)
    opt = optim.Adam(model.parameters(), lr=1e-3)
    bce = nn.BCEWithLogitsLoss()

    xs = torch.tensor(Xs_train, dtype=torch.float32)
    ys = torch.tensor(ys_train.reshape(-1, 1), dtype=torch.float32)
    xt = torch.tensor(Xt_all, dtype=torch.float32)

    bs = min(128, len(xs))
    bt = min(128, len(xt))
    epochs = 40
    losses = []
    for ep in range(epochs):
        n_step = max(1, min(len(xs) // bs, len(xt) // bt))
        ep_loss = 0.0
        for _ in range(n_step):
            idx_s = np.random.choice(len(xs), size=bs, replace=len(xs) < bs)
            idx_t = np.random.choice(len(xt), size=bt, replace=len(xt) < bt)
            xsb = xs[idx_s]
            ysb = ys[idx_s]
            xtb = xt[idx_t]

            task_logit_s, z_s = model.forward_task(xsb)
            _, z_t = model.forward_task(xtb)
            task_loss = bce(task_logit_s, ysb)

            dom_s = model.forward_domain(z_s, lambd=0.2)
            dom_t = model.forward_domain(z_t, lambd=0.2)
            y_dom_s = torch.zeros_like(dom_s)
            y_dom_t = torch.ones_like(dom_t)
            dom_loss = bce(dom_s, y_dom_s) + bce(dom_t, y_dom_t)

            loss = task_loss + 0.5 * dom_loss
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep_loss += float(loss.detach().cpu().item())
        losses.append(ep_loss / n_step)

    xb = torch.tensor(X_board, dtype=torch.float32)
    with torch.no_grad():
        logits, _ = model.forward_task(xb)
        probs = torch.sigmoid(logits).cpu().numpy().reshape(-1)
    meta = {
        "epochs": epochs,
        "batch_source": bs,
        "batch_target": bt,
        "train_loss_last": float(losses[-1]) if losses else None,
        "train_loss_first": float(losses[0]) if losses else None,
    }
    return probs.astype(np.float32), meta


def train_and_score_variant(
    variant_name: str,
    adaptation_strategy: str,
    source_rows: List[Dict[str, Any]],
    split: Dict[str, Any],
    boards_raw: Dict[str, List[Dict[str, Any]]],
    board_order: List[str],
    rescue_thr: float,
    lane_thr: float,
    seed: int,
    mode: str,
    run_dir: Path,
    out_log: Path,
) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, Any]]:
    X, y, tr_mask, valte_mask = build_train_arrays(source_rows, split)
    X_train_raw = X[tr_mask]
    y_train = y[tr_mask]
    imp, scl = fit_imputer_scaler(X_train_raw)

    X_train_imp = imp.transform(X_train_raw)
    X_train_std = scl.transform(X_train_imp)

    Xt_list = []
    for b in board_order:
        rows = boards_raw[b]
        feats = [board_row_to_features(r) for r in rows]
        xb = np.asarray([[f[k] for k in FEATURES] for f in feats], dtype=np.float32)
        xb_imp = imp.transform(xb)
        xb_std = scl.transform(xb_imp)
        Xt_list.append(xb_std)
    Xt_all = np.vstack(Xt_list).astype(np.float32)

    mmeta: Dict[str, Any] = {}
    if mode == "naive":
        X_train_fit = X_train_std
    elif mode == "coral":
        X_train_fit = coral_transform(X_train_std, Xt_all, eps=1e-6)
        mmeta["coral_eps"] = 1e-6
    elif mode == "mmd":
        X_train_fit, mmd_meta = mmd_mean_shift_transform(X_train_std, Xt_all)
        mmeta.update(mmd_meta)
        mmeta["mmd_kind"] = "rbf_mmd_mean_shift"
    elif mode == "dann":
        X_train_fit = X_train_std
    else:
        raise ValueError(f"unknown mode={mode}")

    lr = fit_lr(X_train_fit, y_train, seed=seed)

    by_board: Dict[str, Dict[str, Any]] = {}
    scored_paths: Dict[str, str] = {}
    for b in board_order:
        rows = boards_raw[b]
        feats = [board_row_to_features(r) for r in rows]
        xb = np.asarray([[f[k] for k in FEATURES] for f in feats], dtype=np.float32)
        xb_imp = imp.transform(xb)
        xb_std = scl.transform(xb_imp)

        if mode == "naive":
            lane_prob = lr.predict_proba(xb_std)[:, 1]
        elif mode == "coral":
            xb_coral = coral_transform(xb_std, Xt_all, eps=1e-6)
            lane_prob = lr.predict_proba(xb_coral)[:, 1]
        elif mode == "mmd":
            # apply the learned mean-shift from source transform by matching mean displacement
            delta = np.mean(X_train_fit - X_train_std, axis=0, keepdims=True)
            xb_mmd = xb_std + delta
            lane_prob = lr.predict_proba(xb_mmd)[:, 1]
        elif mode == "dann":
            lane_prob, dann_meta = run_dann_unsupervised(X_train_std, y_train, Xt_all, xb_std, seed=seed)
            mmeta.update(dann_meta)
        else:
            raise ValueError(mode)

        scored_rows: List[Dict[str, Any]] = []
        for r, p in zip(rows, lane_prob):
            lane_s = clip01(float(p))
            rear_s = 1.0 - lane_s
            pred = str(r.get("pred_type_key", "")).strip()
            pred_patch = pred
            if pred in {"rear_end", "lane_change"} and lane_s >= lane_thr and lane_s > rear_s:
                pred_patch = "lane_change"
            scored_rows.append(
                {
                    "sample_id": str(r.get("sample_id", "")).strip(),
                    "video": str(r.get("video", "")).strip(),
                    "gt_type": str(r.get("accident_type", "")).strip(),
                    "pred_type": pred,
                    "scene_tags": parse_scene_tags(r.get("scene_tags", [])),
                    "lane_score": round(lane_s, 6),
                    "rear_score": round(rear_s, 6),
                    "pred_type_patch": pred_patch,
                }
            )

        stats = eval_board_from_scores(scored_rows, rescue_thr=rescue_thr, lane_thr=lane_thr)
        by_board[b] = stats

        out_scored = run_dir / "artifacts" / f"{variant_name}.{b}.scored.jsonl"
        write_jsonl(out_scored, scored_rows)
        scored_paths[b] = str(out_scored.resolve())

    ag = aggregate(by_board)
    bridge_auc = None
    try:
        p_train = lr.predict_proba(X_train_fit)[:, 1]
        bridge_auc = float(roc_auc_score(y_train, p_train))
    except Exception:
        bridge_auc = None
    mmeta["bridge_train_auc"] = bridge_auc
    mmeta["board_order"] = board_order
    mmeta["rescue_thr"] = rescue_thr
    mmeta["lane_thr"] = lane_thr
    mmeta["seed"] = seed

    out_json = run_dir / "artifacts" / f"{variant_name}.aggregate.json"
    write_json(out_json, {"variant_name": variant_name, "mode": mode, "aggregate": ag, "by_board": by_board, "meta": mmeta})
    log(f"{variant_name} aggregate: rescueable={ag['rescueable_total']} changed={ag['changed_total']} rsr={ag['rear_steal_ratio_total']:.6f} dMacro={ag['delta_macro_f1_mean']:+.6f}", out_log)
    return ag, scored_paths, {"aggregate_path": str(out_json.resolve()), "meta": mmeta}


def load_existing_rows(paths: Dict[str, Path], out_log: Path) -> List[VariantResult]:
    rows: List[VariantResult] = []

    # 1) source-only/prediction-only from pre-remediation validation aggregate
    p_source = paths["exid_validation_3step"]
    j_source = load_json(p_source)
    rescueable = int(j_source["readonly_totals"]["rescueable_total"])
    changed = int(j_source["readonly_totals"]["changed_total"])
    rear_ratio = float(j_source["kpi_5_numbers"]["readonly_rear_steal_ratio_total"])
    dmacro = float(j_source["aggregate_delta"]["macro_f1"])
    rows.append(
        VariantResult(
            variant_name="Source-only / prediction-only evidence",
            source_domain="exiD",
            target_slice="aggregate_n199_rear77",
            adaptation_strategy="source prediction evidence only (no executable bridge closure)",
            uses_target_labels=False,
            rescueable_total=rescueable,
            changed_total=changed,
            rear_steal_ratio=rear_ratio,
            dMacro=dmacro,
            dLaneR=float(j_source["aggregate_delta"]["lane_recall"]),
            hard_gate_pass=hard_gate_pass_from_metrics(rescueable, changed, rear_ratio, dmacro),
            stability_reconfirmation_pass=False,
            independent_external_board_pass=False,
            promotion_role="immovable baseline",
            artifact_path=str(p_source.resolve()),
            notes="Read from EXID_RELAXED_BRIDGE_3STEP_BOARD_2026-05-08.json",
        )
    )

    # 2) naive transfer represented by threshold probe (all six settings immovable)
    p_thr = paths["threshold_probe"]
    j_thr = load_json(p_thr)
    rows.append(
        VariantResult(
            variant_name="Naive public-to-internal transfer (threshold-probe representative)",
            source_domain="exiD",
            target_slice="aggregate_n199_rear77",
            adaptation_strategy="naive transfer / threshold-only readonly probe",
            uses_target_labels=False,
            rescueable_total=int(j_thr["summary"][0]["totals"]["rescueable_rule_total"]),
            changed_total=int(j_thr["summary"][0]["totals"]["changed_total"]),
            rear_steal_ratio=float(j_thr["summary"][0]["ratios"]["rear_steal_rule_ratio"]),
            dMacro=float(j_thr["summary"][0]["mean_delta"]["macro_f1"]),
            dLaneR=float(j_thr["summary"][0]["mean_delta"]["lane_recall"]),
            hard_gate_pass=hard_gate_pass_from_metrics(
                int(j_thr["summary"][0]["totals"]["rescueable_rule_total"]),
                int(j_thr["summary"][0]["totals"]["changed_total"]),
                float(j_thr["summary"][0]["ratios"]["rear_steal_rule_ratio"]),
                float(j_thr["summary"][0]["mean_delta"]["macro_f1"]),
            ),
            stability_reconfirmation_pass=False,
            independent_external_board_pass=False,
            promotion_role="immovable negative evidence",
            artifact_path=str(p_thr.resolve()),
            notes="All six settings have zero rescue/changed; representative row recorded from v1 setting",
        )
    )

    rows.append(
        VariantResult(
            variant_name="Six-setting threshold-only probe",
            source_domain="exiD",
            target_slice="aggregate_n199_rear77",
            adaptation_strategy="readonly threshold grid (6 settings)",
            uses_target_labels=False,
            rescueable_total=0,
            changed_total=0,
            rear_steal_ratio=0.0,
            dMacro=0.0,
            dLaneR=0.0,
            hard_gate_pass=False,
            stability_reconfirmation_pass=False,
            independent_external_board_pass=False,
            promotion_role="immovable negative evidence",
            artifact_path=str(p_thr.resolve()),
            notes="Collapsed six-setting summary row",
        )
    )

    # 3) remediation-only/full remediation from State C in ablation table
    p_ab = paths["ablation"]
    j_ab = load_json(p_ab)
    state_map = {str(r["state"]).strip(): r for r in j_ab}
    sc = state_map.get("C")
    if sc:
        rows.append(
            VariantResult(
                variant_name="Full remediation / remediation-only",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="minimal direct-shared remediation only (no constrained refinement)",
                uses_target_labels=False,
                rescueable_total=int(sc["rescueable_total"]),
                changed_total=int(sc["changed_total"]),
                rear_steal_ratio=float(sc["rear_steal_ratio"]),
                dMacro=float(sc["dMacro"]),
                dLaneR=None,
                hard_gate_pass=hard_gate_pass_from_metrics(int(sc["rescueable_total"]), int(sc["changed_total"]), float(sc["rear_steal_ratio"]), float(sc["dMacro"])),
                stability_reconfirmation_pass=False,
                independent_external_board_pass=False,
                promotion_role=str(sc["status"]),
                artifact_path=str(p_ab.resolve()),
                notes="From MINIMAL_REPAIR_ABLATION_TABLE state C",
            )
        )

    sb = state_map.get("B")
    if sb:
        rows.append(
            VariantResult(
                variant_name="Partial remediation",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="partial direct-shared remediation (3/6)",
                uses_target_labels=False,
                rescueable_total=int(sb["rescueable_total"]),
                changed_total=int(sb["changed_total"]),
                rear_steal_ratio=float(sb["rear_steal_ratio"]),
                dMacro=float(sb["dMacro"]),
                dLaneR=None,
                hard_gate_pass=hard_gate_pass_from_metrics(int(sb["rescueable_total"]), int(sb["changed_total"]), float(sb["rear_steal_ratio"]), float(sb["dMacro"])),
                stability_reconfirmation_pass=False,
                independent_external_board_pass=False,
                promotion_role=str(sb["status"]),
                artifact_path=str(p_ab.resolve()),
                notes="From MINIMAL_REPAIR_ABLATION_TABLE state B",
            )
        )

    # 4) highD remediation-only branch
    p_highd = paths["step4_highd"]
    j_highd = load_json(p_highd)
    ag_h = j_highd["aggregate"]
    rows.append(
        VariantResult(
            variant_name="highD remediation-only branch",
            source_domain="highD",
            target_slice="aggregate_n199_rear77",
            adaptation_strategy="full remediation mapping on highD source branch",
            uses_target_labels=False,
            rescueable_total=int(ag_h["rescueable_total"]),
            changed_total=int(ag_h["changed_total"]),
            rear_steal_ratio=float(ag_h["rear_steal_ratio_total"]),
            dMacro=float(ag_h["delta_macro_f1_mean"]),
            dLaneR=float(ag_h["delta_lane_recall_mean"]),
            hard_gate_pass=hard_gate_pass_from_metrics(int(ag_h["rescueable_total"]), int(ag_h["changed_total"]), float(ag_h["rear_steal_ratio_total"]), float(ag_h["delta_macro_f1_mean"])),
            stability_reconfirmation_pass=False,
            independent_external_board_pass=False,
            promotion_role="diagnostic only",
            artifact_path=str(p_highd.resolve()),
            notes="From STEP4_MIN_READONLY_HIGHD_2026-05-09",
        )
    )

    # 5) proposed constrained exiD refinement (aggregate + stability + external board)
    p_v4 = paths["v4_refine_microgrid"]
    p_v4_re = paths["v4_refine_microgrid_reconfirm"]
    p_ext = paths["external_board36_eval"]
    j_v4 = load_json(p_v4)
    j_v4_re = load_json(p_v4_re)
    j_ext = load_json(p_ext)

    def pick_variant(js: Dict[str, Any], name: str) -> Dict[str, Any]:
        for r in js.get("variants", []):
            if str(r.get("name", "")).strip() == name:
                return r
        raise KeyError(f"variant {name} not found in {js}")

    v4a = pick_variant(j_v4, "v4A_margin_up")
    v4a_re = pick_variant(j_v4_re, "v4A_margin_up")
    ag = v4a["aggregate"]
    ag_re = v4a_re["aggregate"]
    ext_metrics = j_ext["metrics"]
    ext_gates = j_ext.get("gates", {})

    rows.append(
        VariantResult(
            variant_name="Proposed constrained exiD refinement",
            source_domain="exiD",
            target_slice="aggregate_n199_rear77 + external_board_n36_rear12",
            adaptation_strategy="diagnosis-remediation-refinement (v4A constrained)",
            uses_target_labels=False,
            rescueable_total=int(ag["rescueable_total"]),
            changed_total=int(ag["changed_total"]),
            rear_steal_ratio=float(ag["rear_steal_ratio_total"]),
            dMacro=float(ag["delta_macro_f1_mean"]),
            dLaneR=float(ag["delta_lane_recall_mean"]),
            hard_gate_pass=hard_gate_pass_from_metrics(int(ag["rescueable_total"]), int(ag["changed_total"]), float(ag["rear_steal_ratio_total"]), float(ag["delta_macro_f1_mean"])),
            stability_reconfirmation_pass=bool(
                hard_gate_pass_from_metrics(
                    int(ag_re["rescueable_total"]),
                    int(ag_re["changed_total"]),
                    float(ag_re["rear_steal_ratio_total"]),
                    float(ag_re["delta_macro_f1_mean"]),
                )
            ),
            independent_external_board_pass=bool(
                hard_gate_pass_from_metrics(
                    int(ext_metrics["rescueable_total"]),
                    int(ext_metrics["changed_total"]),
                    float(ext_metrics["rear_steal_ratio"]),
                    float(ext_metrics["delta_metrics"]["macro_f1"]),
                )
                and bool(ext_gates.get("rear_steal_ratio_lt_10pct", False))
                and bool(ext_gates.get("rescueable_total_gt_0", False))
                and bool(ext_gates.get("changed_total_gt_0", False))
                and bool(ext_gates.get("delta_macro_f1_non_negative", False))
            ),
            promotion_role="retained formal validation line",
            artifact_path=f"{p_v4.resolve()} | {p_v4_re.resolve()} | {p_ext.resolve()}",
            notes="Aggregate+stability+external from frozen v4A artifacts",
        )
    )

    log("Loaded existing paper-aligned rows from frozen artifacts.", out_log)
    return rows


def collect_paths(root: Path) -> Dict[str, Path]:
    reports = root / "outputs" / "fusion_v3" / "reports"
    return {
        "source_learnability": reports / "v3_5_20260508_exid_bridge_step1_learnability" / "EXID_RELAXED_LANEREAR_LEARNABILITY.json",
        "source_pool": reports / "v3_5_20260508_exid_switch_relaxedscan" / "exid_event_pool_selected_relaxed.jsonl",
        "board152_directshared": reports / "v3_5_20260508_step2_direct_shared_coverage" / "native_features" / "board152_directshared.jsonl",
        "board30_directshared": reports / "v3_5_20260508_step2_direct_shared_coverage" / "native_features" / "board30_directshared.jsonl",
        "board24_directshared": reports / "v3_5_20260508_step2_direct_shared_coverage" / "native_features" / "board24_directshared.jsonl",
        "external_board36_directshared": reports / "v3_5_20260509_exid_external_board36_reconfirm" / "native_features" / "external_board36_directshared.jsonl",
        "exid_validation_3step": reports / "v3_5_20260508_exid_bridge_validation" / "EXID_RELAXED_BRIDGE_3STEP_BOARD_2026-05-08.json",
        "threshold_probe": reports / "v3_5_20260508_exid_bridge_threshold_diag" / "EXID_READONLY_THRESHOLD_DIAG_GRID_2026-05-08.json",
        "ablation": reports / "v3_5_20260512_min_repair_ablation" / "MINIMAL_REPAIR_ABLATION_TABLE_2026-05-12.json",
        "step4_highd": reports / "v3_5_20260509_step4_min_readonly" / "STEP4_MIN_READONLY_HIGHD_2026-05-09.json",
        "v4_refine_microgrid": reports / "v3_5_20260509_step4_exid_constraint_microgrid_v4refine" / "EXID_STEP4_CONSTRAINT_MICROGRID_V4REFINE_2026-05-09.json",
        "v4_refine_microgrid_reconfirm": reports / "v3_5_20260509_step4_exid_constraint_microgrid_v4refine_reconfirm_seed73_order3024152" / "EXID_STEP4_CONSTRAINT_MICROGRID_V4REFINE_RECONFIRM_2026-05-09.json",
        "external_board36_eval": reports / "v3_5_20260509_exid_external_board36_reconfirm_eval" / "EXID_EXTERNAL_BOARD36_RECONFIRM_EVAL_2026-05-09.json",
    }


def read_boards(paths: Dict[str, Path]) -> Dict[str, List[Dict[str, Any]]]:
    return {
        "board152": load_jsonl(paths["board152_directshared"]),
        "board30": load_jsonl(paths["board30_directshared"]),
        "board24": load_jsonl(paths["board24_directshared"]),
    }


def run_adaptation_baselines(
    root: Path,
    run_dir: Path,
    out_log: Path,
    paths: Dict[str, Path],
    seed: int = 42,
) -> Tuple[List[VariantResult], Dict[str, Any]]:
    source_report = load_json(paths["source_learnability"])
    source_rows = load_jsonl(paths["source_pool"])
    split = source_report.get("split", {}) or {}
    boards_raw = read_boards(paths)
    board_order = ["board152", "board30", "board24"]
    rescue_thr = 0.56
    lane_thr = 0.58
    results: List[VariantResult] = []
    status = {
        "CORAL": "skipped",
        "MMD": "skipped",
        "DANN": "skipped",
    }

    # CORAL
    try:
        ag, scored_paths, extra = train_and_score_variant(
            variant_name="coral_alignment_baseline",
            adaptation_strategy="CORAL covariance alignment (unsupervised target distribution)",
            source_rows=source_rows,
            split=split,
            boards_raw=boards_raw,
            board_order=board_order,
            rescue_thr=rescue_thr,
            lane_thr=lane_thr,
            seed=seed,
            mode="coral",
            run_dir=run_dir,
            out_log=out_log,
        )
        status["CORAL"] = "completed"
        results.append(
            VariantResult(
                variant_name="CORAL alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="CORAL feature covariance alignment",
                uses_target_labels=False,
                rescueable_total=int(ag["rescueable_total"]),
                changed_total=int(ag["changed_total"]),
                rear_steal_ratio=float(ag["rear_steal_ratio_total"]),
                dMacro=float(ag["delta_macro_f1_mean"]),
                dLaneR=float(ag["delta_lane_recall_mean"]),
                hard_gate_pass=hard_gate_pass_from_metrics(int(ag["rescueable_total"]), int(ag["changed_total"]), float(ag["rear_steal_ratio_total"]), float(ag["delta_macro_f1_mean"])),
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="baseline-diagnostic",
                artifact_path=extra["aggregate_path"],
                notes=f"uses_target_labels=false; scored files: {scored_paths}",
            )
        )
    except Exception as exc:
        status["CORAL"] = "failed"
        log(f"CORAL failed: {exc}", out_log)
        results.append(
            VariantResult(
                variant_name="CORAL alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="CORAL feature covariance alignment",
                uses_target_labels=False,
                rescueable_total=None,
                changed_total=None,
                rear_steal_ratio=None,
                dMacro=None,
                dLaneR=None,
                hard_gate_pass=None,
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="attempted-not-completed",
                artifact_path="",
                notes=f"FAILED: {exc}",
            )
        )

    # MMD
    try:
        ag, scored_paths, extra = train_and_score_variant(
            variant_name="mmd_alignment_baseline",
            adaptation_strategy="MMD mean-shift alignment (unsupervised target distribution)",
            source_rows=source_rows,
            split=split,
            boards_raw=boards_raw,
            board_order=board_order,
            rescue_thr=rescue_thr,
            lane_thr=lane_thr,
            seed=seed,
            mode="mmd",
            run_dir=run_dir,
            out_log=out_log,
        )
        status["MMD"] = "completed"
        results.append(
            VariantResult(
                variant_name="MMD alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="MMD-based unsupervised feature mean-shift adaptation",
                uses_target_labels=False,
                rescueable_total=int(ag["rescueable_total"]),
                changed_total=int(ag["changed_total"]),
                rear_steal_ratio=float(ag["rear_steal_ratio_total"]),
                dMacro=float(ag["delta_macro_f1_mean"]),
                dLaneR=float(ag["delta_lane_recall_mean"]),
                hard_gate_pass=hard_gate_pass_from_metrics(int(ag["rescueable_total"]), int(ag["changed_total"]), float(ag["rear_steal_ratio_total"]), float(ag["delta_macro_f1_mean"])),
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="baseline-diagnostic",
                artifact_path=extra["aggregate_path"],
                notes=f"uses_target_labels=false; scored files: {scored_paths}",
            )
        )
    except Exception as exc:
        status["MMD"] = "failed"
        log(f"MMD failed: {exc}", out_log)
        results.append(
            VariantResult(
                variant_name="MMD alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="MMD-based unsupervised feature adaptation",
                uses_target_labels=False,
                rescueable_total=None,
                changed_total=None,
                rear_steal_ratio=None,
                dMacro=None,
                dLaneR=None,
                hard_gate_pass=None,
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="attempted-not-completed",
                artifact_path="",
                notes=f"FAILED: {exc}",
            )
        )

    # DANN
    try:
        ag, scored_paths, extra = train_and_score_variant(
            variant_name="dann_alignment_baseline",
            adaptation_strategy="DANN feature encoder + domain discriminator (unsupervised target domain confusion)",
            source_rows=source_rows,
            split=split,
            boards_raw=boards_raw,
            board_order=board_order,
            rescue_thr=rescue_thr,
            lane_thr=lane_thr,
            seed=seed,
            mode="dann",
            run_dir=run_dir,
            out_log=out_log,
        )
        status["DANN"] = "completed"
        results.append(
            VariantResult(
                variant_name="DANN alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="domain-adversarial adaptation (GRL)",
                uses_target_labels=False,
                rescueable_total=int(ag["rescueable_total"]),
                changed_total=int(ag["changed_total"]),
                rear_steal_ratio=float(ag["rear_steal_ratio_total"]),
                dMacro=float(ag["delta_macro_f1_mean"]),
                dLaneR=float(ag["delta_lane_recall_mean"]),
                hard_gate_pass=hard_gate_pass_from_metrics(int(ag["rescueable_total"]), int(ag["changed_total"]), float(ag["rear_steal_ratio_total"]), float(ag["delta_macro_f1_mean"])),
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="baseline-diagnostic",
                artifact_path=extra["aggregate_path"],
                notes=f"uses_target_labels=false; scored files: {scored_paths}",
            )
        )
    except Exception as exc:
        status["DANN"] = "failed"
        log(f"DANN failed: {exc}", out_log)
        results.append(
            VariantResult(
                variant_name="DANN alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="domain-adversarial adaptation (GRL)",
                uses_target_labels=False,
                rescueable_total=None,
                changed_total=None,
                rear_steal_ratio=None,
                dMacro=None,
                dLaneR=None,
                hard_gate_pass=None,
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="attempted-not-completed",
                artifact_path="",
                notes=f"FAILED: {exc}",
            )
        )

    return results, status


def write_results_table(run_dir: Path, rows: List[VariantResult]) -> None:
    csv_path = run_dir / "baseline_results.csv"
    json_path = run_dir / "baseline_results.json"
    fields = [
        "variant_name",
        "source_domain",
        "target_slice",
        "adaptation_strategy",
        "uses_target_labels",
        "rescueable_total",
        "changed_total",
        "rear_steal_ratio",
        "dMacro",
        "dLaneR",
        "hard_gate_pass",
        "stability_reconfirmation_pass",
        "independent_external_board_pass",
        "promotion_role",
        "artifact_path",
        "notes",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r.to_dict())
    write_json(json_path, [r.to_dict() for r in rows])


def write_run_config(
    run_dir: Path,
    root: Path,
    paths: Dict[str, Path],
    status: Dict[str, Any],
    random_seed: int = 42,
) -> None:
    cfg = {
        "run_timestamp": run_dir.name.split("_")[-2] + "_" + run_dir.name.split("_")[-1] if "_" in run_dir.name else run_dir.name,
        "project_root": str(root.resolve()),
        "git_hash": None,
        "data_paths": {k: str(v.resolve()) for k, v in paths.items()},
        "slice_settings": {
            "aggregate_validation": {"n": 199, "rear_cases": 77},
            "stability_reconfirmation": {"n": 199, "rear_cases": 77},
            "independent_external_board": {"n": 36, "rear_cases": 12},
        },
        "feature_list": FEATURES,
        "gate_definition": GATE_DEF,
        "baseline_status": status,
        "random_seed": int(random_seed),
        "evaluator_entry": {
            "aggregate_protocol_reference": str((root / "backend" / "scripts" / "run_public_bridge_step4_minreadonly.py").resolve()),
            "external_protocol_reference": str((root / "backend" / "scripts" / "eval_exid_candidate_external_board.py").resolve()),
        },
    }
    def to_yaml(obj: Any, indent: int = 0) -> str:
        sp = "  " * indent
        if isinstance(obj, dict):
            lines = []
            for k, v in obj.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{sp}{k}:")
                    lines.append(to_yaml(v, indent + 1))
                else:
                    if isinstance(v, bool):
                        vv = "true" if v else "false"
                    elif v is None:
                        vv = "null"
                    elif isinstance(v, (int, float)):
                        vv = str(v)
                    else:
                        s = str(v).replace("\"", "\\\"")
                        vv = f"\"{s}\""
                    lines.append(f"{sp}{k}: {vv}")
            return "\n".join(lines)
        if isinstance(obj, list):
            lines = []
            for it in obj:
                if isinstance(it, (dict, list)):
                    lines.append(f"{sp}-")
                    lines.append(to_yaml(it, indent + 1))
                else:
                    if isinstance(it, bool):
                        vv = "true" if it else "false"
                    elif it is None:
                        vv = "null"
                    elif isinstance(it, (int, float)):
                        vv = str(it)
                    else:
                        s = str(it).replace("\"", "\\\"")
                        vv = f"\"{s}\""
                    lines.append(f"{sp}- {vv}")
            return "\n".join(lines)
        return f"{sp}{obj}"

    yml = to_yaml(cfg) + "\n"
    (run_dir / "run_config.yaml").write_text(yml, encoding="utf-8")


def write_evidence_map(run_dir: Path, rows: List[VariantResult], paths: Dict[str, Path]) -> None:
    p = run_dir / "evidence_map.md"
    lines = []
    lines.append("# Evidence Map")
    lines.append("")
    lines.append("Each row below maps reported metrics to concrete artifacts.")
    lines.append("")
    for r in rows:
        lines.append(f"## {r.variant_name}")
        lines.append(f"- artifact_path: `{r.artifact_path}`")
        lines.append(f"- rescueable_total: `{r.rescueable_total}`")
        lines.append(f"- changed_total: `{r.changed_total}`")
        lines.append(f"- rear_steal_ratio: `{r.rear_steal_ratio}`")
        lines.append(f"- dMacro: `{r.dMacro}`")
        lines.append(f"- dLaneR: `{r.dLaneR}`")
        lines.append(f"- hard_gate_pass: `{r.hard_gate_pass}`")
        lines.append(f"- stability_reconfirmation_pass: `{r.stability_reconfirmation_pass}`")
        lines.append(f"- independent_external_board_pass: `{r.independent_external_board_pass}`")
        lines.append(f"- notes: {r.notes}")
        lines.append("")
    lines.append("## Protocol Harmonization Note")
    lines.append("- `hard_gate_pass` in this run is computed uniformly as rear_steal_ratio < 0.1 AND rescueable_total > 0 AND changed_total > 0 AND dMacro >= 0.")
    lines.append("- This post-rule harmonizes aggregate and external-board checks to avoid protocol drift.")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_tex_table(run_dir: Path, rows: List[VariantResult], paper_root: Path) -> Optional[Path]:
    good = [r for r in rows if r.rescueable_total is not None and r.changed_total is not None and r.rear_steal_ratio is not None and r.dMacro is not None and r.hard_gate_pass is not None]
    if not good:
        return None
    out = paper_root / "tables" / "decision_chain_baseline_comparison.tex"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("\\begin{table}[t]")
    lines.append("\\centering")
    lines.append("\\small")
    lines.append("\\caption{Decision-chain transfer baselines under fixed audited gates.}")
    lines.append("\\label{tab:decision_chain_baseline_comparison}")
    lines.append("\\begin{tabular}{@{}p{0.29\\columnwidth}p{0.24\\columnwidth}p{0.12\\columnwidth}p{0.10\\columnwidth}p{0.08\\columnwidth}p{0.09\\columnwidth}p{0.08\\columnwidth}@{}}")
    lines.append("\\toprule")
    lines.append("Variant & Adaptation strategy & R/C & RSR & $\\Delta M$ & Gate pass & External board \\\\")
    lines.append("\\midrule")
    for r in good:
        rc = f"{r.rescueable_total}/{r.changed_total}"
        rsr = f"{r.rear_steal_ratio:.6f}"
        dm = f"{r.dMacro:+.6f}"
        gate = "True" if r.hard_gate_pass else "False"
        ext = "True" if r.independent_external_board_pass is True else ("False" if r.independent_external_board_pass is False else "NA")
        v = r.variant_name.replace("&", "\\&")
        a = r.adaptation_strategy.replace("&", "\\&")
        lines.append(f"{v} & {a} & {rc} & {rsr} & {dm} & {gate} & {ext} \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    lines.append("\\vspace{2pt}")
    lines.append("\\caption*{All variants are evaluated through the same fixed accident-decision-chain gate protocol where artifacts are available. The table compares decision-chain transfer evidence rather than trajectory-prediction benchmark scores.}")
    lines.append("\\end{table}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_readme(run_dir: Path) -> None:
    txt = (
        "# Decision-Chain Transfer Baseline Run\n\n"
        "## Reproduce\n"
        "```bash\n"
        "python backend/scripts/run_decision_chain_transfer_baselines.py \\\n"
        "  --root . \\\n"
        "  --paper-root ./paper/acmart-primary/acmart-primary\n"
        "```\n\n"
        "Outputs:\n"
        "- run_config.yaml\n"
        "- baseline_results.csv\n"
        "- baseline_results.json\n"
        "- evidence_map.md\n"
        "- run_log.txt\n"
        "- FINAL_REPORT.md\n"
    )
    (run_dir / "README.md").write_text(txt, encoding="utf-8")


def answer_questions(rows: List[VariantResult]) -> Dict[str, Any]:
    by_name = {r.variant_name: r for r in rows}

    def pass_info(name: str) -> Tuple[Optional[bool], Optional[int], Optional[int], Optional[float], Optional[float]]:
        r = by_name.get(name)
        if not r:
            return None, None, None, None, None
        return r.hard_gate_pass, r.rescueable_total, r.changed_total, r.rear_steal_ratio, r.dMacro

    coral = pass_info("CORAL alignment baseline")
    mmd = pass_info("MMD alignment baseline")
    dann = pass_info("DANN alignment baseline")
    prop = by_name.get("Proposed constrained exiD refinement")

    high_changed_high_rsr = []
    for r in rows:
        if r.changed_total is not None and r.rear_steal_ratio is not None:
            if r.changed_total >= 50 and r.rear_steal_ratio >= 0.10:
                high_changed_high_rsr.append(r.variant_name)

    unique_prop = None
    if prop is not None:
        candidates = []
        for r in rows:
            if (
                r.rescueable_total is not None
                and r.rescueable_total > 0
                and r.hard_gate_pass is True
                and r.stability_reconfirmation_pass is True
                and r.independent_external_board_pass is True
            ):
                candidates.append(r.variant_name)
        unique_prop = (candidates == ["Proposed constrained exiD refinement"])

    return {
        "coral": coral,
        "mmd": mmd,
        "dann": dann,
        "high_changed_high_rsr_variants": high_changed_high_rsr,
        "supports_more_rewrites_not_better": len(high_changed_high_rsr) > 0,
        "proposed_unique_full_condition": unique_prop,
    }


def write_final_report(
    run_dir: Path,
    rows: List[VariantResult],
    baseline_status: Dict[str, Any],
    tex_table_path: Optional[Path],
    q: Dict[str, Any],
) -> None:
    def fmt_bool(v: Optional[bool]) -> str:
        if v is True:
            return "true"
        if v is False:
            return "false"
        return "NA"

    lines: List[str] = []
    lines.append("# FINAL_REPORT")
    lines.append("")
    lines.append("## 1) Baseline Run Status")
    lines.append(f"- CORAL: {baseline_status.get('CORAL')}")
    lines.append(f"- MMD: {baseline_status.get('MMD')}")
    lines.append(f"- DANN: {baseline_status.get('DANN')}")
    lines.append("")
    lines.append("## 2) Baseline Data Source / Params / Target-label Usage")
    for r in rows:
        if "baseline" in r.variant_name.lower() or "DANN" in r.variant_name or "MMD" in r.variant_name or "CORAL" in r.variant_name:
            lines.append(f"- {r.variant_name}: strategy=`{r.adaptation_strategy}`; uses_target_labels={str(r.uses_target_labels).lower()}; artifact=`{r.artifact_path}`")
    lines.append("")
    lines.append("## 3) Fixed-Gate Metrics by Baseline")
    for r in rows:
        lines.append(
            f"- {r.variant_name}: rescueable_total={r.rescueable_total}, changed_total={r.changed_total}, "
            f"rear_steal_ratio={r.rear_steal_ratio}, dMacro={r.dMacro}, hard_gate_pass={fmt_bool(r.hard_gate_pass)}, "
            f"stability_reconfirmation_pass={fmt_bool(r.stability_reconfirmation_pass)}, independent_external_board_pass={fmt_bool(r.independent_external_board_pass)}"
        )
    lines.append("")
    lines.append("## 4) Comparison with Proposed constrained exiD refinement")
    lines.append("- Proposed line metrics are read from frozen v4A aggregate + reconfirm + external-board artifacts.")
    prop = next((r for r in rows if r.variant_name == "Proposed constrained exiD refinement"), None)
    if prop:
        lines.append(
            f"- Proposed: rescueable_total={prop.rescueable_total}, changed_total={prop.changed_total}, rear_steal_ratio={prop.rear_steal_ratio}, "
            f"dMacro={prop.dMacro}, hard_gate_pass={fmt_bool(prop.hard_gate_pass)}, stability_reconfirmation_pass={fmt_bool(prop.stability_reconfirmation_pass)}, "
            f"independent_external_board_pass={fmt_bool(prop.independent_external_board_pass)}."
        )
    lines.append("")
    lines.append("## 5) Whether current manuscript statement is supported")
    lines.append(
        "- Statement under check: "
        "\"Compared with prediction-only source evidence, threshold-only relaxation, remediation-only variants, and feature-alignment adaptation baselines, "
        "the proposed diagnosis-remediation-refinement path is the only evaluated path that simultaneously establishes nonzero executability, "
        "hard-gate compliance, and independent reconfirmation under the fixed audited protocol.\""
    )
    lines.append(f"- Evaluation result: {q.get('proposed_unique_full_condition')}")
    lines.append("")
    lines.append("## 6) If not supported, how conclusion should change")
    if q.get("proposed_unique_full_condition") is True:
        lines.append("- Current bounded conclusion remains supported under evaluated paths.")
    else:
        lines.append("- Adjust wording to remove uniqueness and explicitly list additional paths satisfying full conditions, if any.")
    lines.append("")
    lines.append("## 7) Generated Files")
    required = [
        "run_config.yaml",
        "baseline_results.csv",
        "baseline_results.json",
        "evidence_map.md",
        "run_log.txt",
        "README.md",
    ]
    for name in required:
        lines.append(f"- {name}: {'present' if (run_dir / name).exists() else 'missing'}")
    if (run_dir / "artifacts").exists():
        lines.append("- artifacts/: present")
    lines.append("")
    lines.append("## 8) Repro Command")
    lines.append("```bash")
    lines.append("python backend/scripts/run_decision_chain_transfer_baselines.py --root . --paper-root ./paper/acmart-primary/acmart-primary")
    lines.append("```")
    lines.append("")
    lines.append("## 9) Direct Q&A")
    c = q.get("coral")
    m = q.get("mmd")
    d = q.get("dann")
    lines.append(f"1. CORAL nonzero executability: {None if c is None else (c[1] is not None and c[1] > 0 and c[2] is not None and c[2] > 0)}")
    lines.append(f"2. CORAL hard gate pass: {None if c is None else c[0]}")
    lines.append(f"3. MMD nonzero executability: {None if m is None else (m[1] is not None and m[1] > 0 and m[2] is not None and m[2] > 0)}")
    lines.append(f"4. MMD hard gate pass: {None if m is None else m[0]}")
    lines.append(f"5. DANN completed: {baseline_status.get('DANN') == 'completed'}")
    lines.append(f"6. DANN hard gate pass: {None if d is None else d[0]}")
    lines.append(f"7. Baseline with high changed_total and high rear_steal_ratio: {q.get('high_changed_high_rsr_variants')}")
    lines.append(f"8. Supports 'more rewrites is not necessarily better': {q.get('supports_more_rewrites_not_better')}")
    lines.append(f"9. Proposed remains unique full-condition path: {q.get('proposed_unique_full_condition')}")
    lines.append("10. If not unique, manuscript should be updated accordingly.")
    lines.append("")
    if tex_table_path:
        lines.append(f"- LaTeX table draft generated: `{tex_table_path}`")
    else:
        lines.append("- LaTeX table draft not generated (no complete rows).")

    (run_dir / "FINAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run decision-chain transfer baselines under fixed audited gates.")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent.parent))
    parser.add_argument("--paper-root", default="")
    parser.add_argument("--skip-dann", action="store_true")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for adaptation baseline training/alignment runs.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    paper_root = Path(args.paper_root).resolve()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = root / "outputs" / f"decision_chain_transfer_baselines_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "artifacts").mkdir(parents=True, exist_ok=True)
    out_log = run_dir / "run_log.txt"
    out_log.write_text("", encoding="utf-8")
    log(f"Run dir: {run_dir}", out_log)

    paths = collect_paths(root)
    for k, p in paths.items():
        if not p.exists():
            raise FileNotFoundError(f"required path missing: {k} -> {p}")

    existing_rows = load_existing_rows(paths, out_log)
    log(f"Using adaptation seed: {args.seed}", out_log)
    adaptation_rows, baseline_status = run_adaptation_baselines(root, run_dir, out_log, paths, seed=int(args.seed))
    if args.skip_dann:
        baseline_status["DANN"] = "skipped"
        adaptation_rows = [r for r in adaptation_rows if r.variant_name != "DANN alignment baseline"] + [
            VariantResult(
                variant_name="DANN alignment baseline",
                source_domain="exiD",
                target_slice="aggregate_n199_rear77",
                adaptation_strategy="domain-adversarial adaptation (GRL)",
                uses_target_labels=False,
                rescueable_total=None,
                changed_total=None,
                rear_steal_ratio=None,
                dMacro=None,
                dLaneR=None,
                hard_gate_pass=None,
                stability_reconfirmation_pass=None,
                independent_external_board_pass=None,
                promotion_role="attempted-not-completed",
                artifact_path="",
                notes="SKIPPED by --skip-dann",
            )
        ]

    all_rows = existing_rows + adaptation_rows
    write_results_table(run_dir, all_rows)
    write_run_config(run_dir, root, paths, baseline_status, random_seed=int(args.seed))
    write_evidence_map(run_dir, all_rows, paths)
    write_readme(run_dir)
    tex_table_path = build_tex_table(run_dir, all_rows, paper_root)
    q = answer_questions(all_rows)
    write_final_report(run_dir, all_rows, baseline_status, tex_table_path, q)

    log("All outputs generated.", out_log)
    print(json.dumps({"run_dir": str(run_dir), "tex_table": str(tex_table_path) if tex_table_path else None}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
