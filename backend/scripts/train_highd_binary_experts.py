import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


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


def parse_range(raw: str) -> List[int]:
    out: List[int] = []
    for token in str(raw).split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            start = int(a.strip())
            end = int(b.strip())
            if end < start:
                raise ValueError(f"bad range: {token}")
            out.extend(list(range(start, end + 1)))
        else:
            out.append(int(token))
    out = sorted(set(out))
    if not out:
        raise ValueError(f"empty range: {raw}")
    return out


def safe_float(v: Any, default: float = np.nan) -> float:
    try:
        fv = float(v)
        if not np.isfinite(fv):
            return float(default)
        return float(fv)
    except (TypeError, ValueError):
        return float(default)


def cap_or_nan(v: Any, cap: float) -> float:
    fv = safe_float(v, default=np.nan)
    if not np.isfinite(fv):
        return np.nan
    if fv < 0:
        return np.nan
    return float(min(fv, cap))


def auc_safe(y_true: np.ndarray, y_prob: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return 0.0
    return float(roc_auc_score(y_true, y_prob))


def cls_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
    p, r, f1, _ = precision_recall_fscore_support(y_true, y_pred, average="binary", zero_division=0)
    acc = accuracy_score(y_true, y_pred)
    return {
        "accuracy": float(acc),
        "precision": float(p),
        "recall": float(r),
        "f1": float(f1),
    }


@dataclass(frozen=True)
class SplitConfig:
    train_recs: Tuple[int, ...]
    val_recs: Tuple[int, ...]
    test_recs: Tuple[int, ...]


def split_name(rec: int, cfg: SplitConfig) -> str:
    if rec in cfg.train_recs:
        return "train"
    if rec in cfg.val_recs:
        return "val"
    if rec in cfg.test_recs:
        return "test"
    return "other"


def make_feature_row(r: Dict[str, Any]) -> Dict[str, Any]:
    cls = str(r.get("class", "")).strip().lower()
    min_ttc = cap_or_nan(r.get("min_ttc_eff"), cap=20.0)
    min_thw = cap_or_nan(r.get("min_thw_eff"), cap=10.0)
    min_dhw = cap_or_nan(r.get("min_dhw_eff"), cap=200.0)
    out = {
        "sample_id": str(r.get("sample_id", "")).strip(),
        "recording_id": int(r.get("recording_id")),
        "candidate_type": str(r.get("candidate_type", "")).strip(),
        "duration_frames": safe_float(r.get("duration_frames"), 0.0),
        "mean_x_velocity": safe_float(r.get("mean_x_velocity"), 0.0),
        "max_abs_y_velocity": safe_float(r.get("max_abs_y_velocity"), 0.0),
        "num_lane_changes_meta": safe_float(r.get("numLaneChanges_meta"), 0.0),
        "lane_change_count_track": safe_float(r.get("lane_change_count_track"), 0.0),
        "driving_direction": safe_float(r.get("driving_direction"), 0.0),
        "min_ttc_eff_capped": min_ttc,
        "min_thw_eff_capped": min_thw,
        "min_dhw_eff_capped": min_dhw,
        "ttc_missing": 1.0 if not np.isfinite(min_ttc) else 0.0,
        "thw_missing": 1.0 if not np.isfinite(min_thw) else 0.0,
        "dhw_missing": 1.0 if not np.isfinite(min_dhw) else 0.0,
        "is_car": 1.0 if cls == "car" else 0.0,
        "is_truck": 1.0 if cls == "truck" else 0.0,
    }
    return out


def run_one_expert(
    df: pd.DataFrame,
    feature_cols: List[str],
    split_cfg: SplitConfig,
    positive_type: str,
    seed: int,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    work = df.copy()
    work["split"] = work["recording_id"].map(lambda x: split_name(int(x), split_cfg))
    work = work[work["split"].isin(["train", "val", "test"])].copy()
    work["y"] = (work["candidate_type"] == positive_type).astype(int)

    tr = work[work["split"] == "train"]
    va = work[work["split"] == "val"]
    te = work[work["split"] == "test"]

    xtr = tr[feature_cols].to_numpy(dtype=np.float32)
    ytr = tr["y"].to_numpy(dtype=np.int64)
    xva = va[feature_cols].to_numpy(dtype=np.float32)
    yva = va["y"].to_numpy(dtype=np.int64)
    xte = te[feature_cols].to_numpy(dtype=np.float32)
    yte = te["y"].to_numpy(dtype=np.int64)

    clf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "lr",
                LogisticRegression(
                    C=1.0,
                    class_weight="balanced",
                    solver="liblinear",
                    max_iter=3000,
                    random_state=int(seed),
                ),
            ),
        ]
    )
    clf.fit(xtr, ytr)

    ptr = clf.predict_proba(xtr)[:, 1]
    pva = clf.predict_proba(xva)[:, 1]
    pte = clf.predict_proba(xte)[:, 1]

    yhat_tr = (ptr >= 0.5).astype(np.int64)
    yhat_va = (pva >= 0.5).astype(np.int64)
    yhat_te = (pte >= 0.5).astype(np.int64)

    result = {
        "positive_type": positive_type,
        "n_train": int(len(tr)),
        "n_val": int(len(va)),
        "n_test": int(len(te)),
        "pos_train": int(ytr.sum()),
        "pos_val": int(yva.sum()),
        "pos_test": int(yte.sum()),
        "auc_train": round(auc_safe(ytr, ptr), 6),
        "auc_val": round(auc_safe(yva, pva), 6),
        "auc_test": round(auc_safe(yte, pte), 6),
        "metrics_train_at_05": {k: round(v, 6) for k, v in cls_metrics(ytr, yhat_tr).items()},
        "metrics_val_at_05": {k: round(v, 6) for k, v in cls_metrics(yva, yhat_va).items()},
        "metrics_test_at_05": {k: round(v, 6) for k, v in cls_metrics(yte, yhat_te).items()},
    }

    pred_df = work[["sample_id", "recording_id", "candidate_type", "split", "y"]].copy()
    pred_df["prob"] = np.concatenate([ptr, pva, pte], axis=0)
    pred_df["pred_at_05"] = (pred_df["prob"].to_numpy() >= 0.5).astype(int)
    pred_df["expert"] = positive_type
    return result, pred_df


def main() -> None:
    parser = argparse.ArgumentParser(description="Train highD lane/rear binary experts on fixed recording split.")
    parser.add_argument("--event-pool", required=True, help="highd_event_pool_selected_*.jsonl")
    parser.add_argument("--train-recordings", default="1-20")
    parser.add_argument("--val-recordings", default="21-25")
    parser.add_argument("--test-recordings", default="26-30")
    parser.add_argument("--out-report", required=True, help="Output report json")
    parser.add_argument("--out-pred", required=True, help="Output predictions jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    rows = load_jsonl(Path(args.event_pool).resolve())
    if not rows:
        raise RuntimeError("event pool is empty")

    df = pd.DataFrame([make_feature_row(r) for r in rows])
    feature_cols = [
        "duration_frames",
        "mean_x_velocity",
        "max_abs_y_velocity",
        "num_lane_changes_meta",
        "lane_change_count_track",
        "driving_direction",
        "min_ttc_eff_capped",
        "min_thw_eff_capped",
        "min_dhw_eff_capped",
        "ttc_missing",
        "thw_missing",
        "dhw_missing",
        "is_car",
        "is_truck",
    ]

    split_cfg = SplitConfig(
        train_recs=tuple(parse_range(args.train_recordings)),
        val_recs=tuple(parse_range(args.val_recordings)),
        test_recs=tuple(parse_range(args.test_recordings)),
    )

    lane_result, lane_pred = run_one_expert(
        df=df,
        feature_cols=feature_cols,
        split_cfg=split_cfg,
        positive_type="lane_pos",
        seed=int(args.seed),
    )
    rear_result, rear_pred = run_one_expert(
        df=df,
        feature_cols=feature_cols,
        split_cfg=split_cfg,
        positive_type="rear_risk_pos",
        seed=int(args.seed),
    )

    lane_pass = lane_result["auc_val"] >= 0.85
    rear_pass = rear_result["auc_val"] >= 0.80
    overall_pass = lane_pass and rear_pass

    report = {
        "event_pool": str(Path(args.event_pool).resolve()),
        "split": {
            "train_recordings": list(split_cfg.train_recs),
            "val_recordings": list(split_cfg.val_recs),
            "test_recordings": list(split_cfg.test_recs),
        },
        "features": feature_cols,
        "lane_expert": lane_result,
        "rear_expert": rear_result,
        "gates": {
            "lane_auc_val_threshold": 0.85,
            "rear_auc_val_threshold": 0.80,
            "lane_pass": bool(lane_pass),
            "rear_pass": bool(rear_pass),
            "overall_pass": bool(overall_pass),
        },
        "decision": "PASS_LEARNABLE" if overall_pass else "FAIL_STOP_PUBLIC_POOL_ROUTE",
        "note": "This is a learnability check on highD event-pool pseudo labels only; not yet integrated into main system.",
    }

    out_report = Path(args.out_report).resolve()
    out_pred = Path(args.out_pred).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    pred = pd.concat([lane_pred, rear_pred], axis=0, ignore_index=True)
    with out_pred.open("w", encoding="utf-8") as f:
        for _, row in pred.iterrows():
            f.write(
                json.dumps(
                    {
                        "sample_id": str(row["sample_id"]),
                        "recording_id": int(row["recording_id"]),
                        "candidate_type": str(row["candidate_type"]),
                        "split": str(row["split"]),
                        "expert": str(row["expert"]),
                        "gt_binary": int(row["y"]),
                        "prob": round(float(row["prob"]), 6),
                        "pred_at_05": int(row["pred_at_05"]),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
