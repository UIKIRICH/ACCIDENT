import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_recall_fscore_support, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
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


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def is_lane(accident_type: Any) -> int:
    return 1 if str(accident_type).strip() == "lane_change" else 0


def parse_folds(raw: str) -> List[int]:
    out: List[int] = []
    for x in str(raw).split(","):
        s = x.strip()
        if not s:
            continue
        out.append(int(s))
    if not out:
        raise ValueError("--folds is empty")
    return out


def build_xy(
    feat_df: pd.DataFrame,
    split_rows: List[Dict[str, Any]],
    feature_cols: List[str],
) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]], int]:
    rows_meta: List[Dict[str, Any]] = []
    miss = 0
    for r in split_rows:
        sid = str(r.get("sample_id", "")).strip()
        if not sid:
            continue
        if sid not in feat_df.index:
            miss += 1
            continue
        rows_meta.append(
            {
                "sample_id": sid,
                "video": normalize_video_key(r.get("video", "")),
                "accident_type": str(r.get("accident_type", "")).strip(),
            }
        )

    if not rows_meta:
        return (
            np.zeros((0, len(feature_cols)), dtype=np.float32),
            np.zeros((0,), dtype=np.int64),
            [],
            miss,
        )

    sids = [x["sample_id"] for x in rows_meta]
    x = feat_df.loc[sids, feature_cols].to_numpy(dtype=np.float32)
    y = np.array([is_lane(xm["accident_type"]) for xm in rows_meta], dtype=np.int64)
    return x, y, rows_meta, miss


def safe_auc(y_true: np.ndarray, y_prob: np.ndarray) -> float:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Train lane-vs-nonlane expert on selected folds.")
    parser.add_argument("--feature-csv", required=True, help="Feature CSV with sample_id and feature_* columns")
    parser.add_argument("--splits-dir", required=True, help="Directory containing fold{i}_train.jsonl/fold{i}_val.jsonl")
    parser.add_argument("--folds", default="0,1,2", help="Comma-separated folds, e.g. 0,1,2")
    parser.add_argument("--out-oof", required=True, help="Output OOF lane probability jsonl")
    parser.add_argument("--out-report", required=True, help="Output training report json")
    parser.add_argument("--out-model-dir", default="", help="Optional output directory for fold models (.joblib)")
    parser.add_argument("--dev-feature-csv", default="", help="Optional dev feature CSV")
    parser.add_argument("--dev-labels", default="", help="Optional dev labels jsonl (must include sample_id/video)")
    parser.add_argument("--out-dev", default="", help="Optional output dev lane probability jsonl")
    parser.add_argument("--c", type=float, default=1.0, help="LogisticRegression C")
    parser.add_argument("--max-iter", type=int, default=2000, help="LogisticRegression max_iter")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    feature_csv = Path(args.feature_csv).resolve()
    splits_dir = Path(args.splits_dir).resolve()
    out_oof = Path(args.out_oof).resolve()
    out_report = Path(args.out_report).resolve()
    out_model_dir = Path(args.out_model_dir).resolve() if str(args.out_model_dir).strip() else None
    dev_feature_csv = Path(args.dev_feature_csv).resolve() if str(args.dev_feature_csv).strip() else None
    dev_labels = Path(args.dev_labels).resolve() if str(args.dev_labels).strip() else None
    out_dev = Path(args.out_dev).resolve() if str(args.out_dev).strip() else None
    folds = parse_folds(args.folds)

    out_oof.parent.mkdir(parents=True, exist_ok=True)
    out_report.parent.mkdir(parents=True, exist_ok=True)
    if out_model_dir is not None:
        out_model_dir.mkdir(parents=True, exist_ok=True)
    if out_dev is not None:
        out_dev.parent.mkdir(parents=True, exist_ok=True)

    feat_df = pd.read_csv(feature_csv)
    if "sample_id" not in feat_df.columns:
        raise RuntimeError(f"{feature_csv} missing sample_id")
    feature_cols = [c for c in feat_df.columns if c.startswith("feature_")]
    if not feature_cols:
        raise RuntimeError(f"{feature_csv} has no feature_* columns")
    feat_df["sample_id"] = feat_df["sample_id"].astype(str).str.strip()
    feat_df = feat_df.drop_duplicates(subset=["sample_id"]).set_index("sample_id", drop=False)

    fold_reports: List[Dict[str, Any]] = []
    oof_rows: List[Dict[str, Any]] = []
    model_paths: List[Path] = []

    for fold in folds:
        train_split = splits_dir / f"fold{fold}_train.jsonl"
        val_split = splits_dir / f"fold{fold}_val.jsonl"
        train_rows = load_jsonl(train_split)
        val_rows = load_jsonl(val_split)

        xtr, ytr, tr_meta, tr_miss = build_xy(feat_df, train_rows, feature_cols)
        xva, yva, va_meta, va_miss = build_xy(feat_df, val_rows, feature_cols)
        if len(xtr) == 0 or len(xva) == 0:
            raise RuntimeError(f"fold{fold} has empty train/val after feature alignment")

        clf = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                (
                    "lr",
                    LogisticRegression(
                        C=float(args.c),
                        class_weight="balanced",
                        max_iter=int(args.max_iter),
                        random_state=int(args.seed),
                        solver="liblinear",
                    ),
                ),
            ]
        )
        clf.fit(xtr, ytr)
        pva = clf.predict_proba(xva)[:, 1]
        yhat = (pva >= 0.5).astype(np.int64)

        auc = safe_auc(yva, pva)
        m = cls_metrics(yva, yhat)
        fold_reports.append(
            {
                "fold": int(fold),
                "n_train": int(len(xtr)),
                "n_val": int(len(xva)),
                "n_train_lane": int(ytr.sum()),
                "n_val_lane": int(yva.sum()),
                "missing_train_feature": int(tr_miss),
                "missing_val_feature": int(va_miss),
                "val_auc": round(float(auc), 6),
                "val_accuracy_at_05": round(float(m["accuracy"]), 6),
                "val_precision_at_05": round(float(m["precision"]), 6),
                "val_recall_at_05": round(float(m["recall"]), 6),
                "val_f1_at_05": round(float(m["f1"]), 6),
            }
        )

        for i, meta in enumerate(va_meta):
            oof_rows.append(
                {
                    "sample_id": meta["sample_id"],
                    "video": meta["video"],
                    "gt_accident_type": meta["accident_type"],
                    "gt_lane_binary": int(is_lane(meta["accident_type"])),
                    "lane_expert_prob": round(float(pva[i]), 6),
                    "fold": int(fold),
                }
            )

        if out_model_dir is not None:
            mp = out_model_dir / f"fold{fold}_lane_expert_lr.joblib"
            joblib.dump({"model": clf, "feature_columns": feature_cols, "fold": int(fold)}, mp)
            model_paths.append(mp)

    oof_rows_sorted = sorted(oof_rows, key=lambda x: x["video"])
    with out_oof.open("w", encoding="utf-8") as f:
        for r in oof_rows_sorted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    oof_y = np.array([int(r["gt_lane_binary"]) for r in oof_rows_sorted], dtype=np.int64)
    oof_p = np.array([float(r["lane_expert_prob"]) for r in oof_rows_sorted], dtype=np.float64)
    oof_pred = (oof_p >= 0.5).astype(np.int64)
    oof_auc = safe_auc(oof_y, oof_p)
    oof_m = cls_metrics(oof_y, oof_pred)

    dev_summary: Dict[str, Any] = {}
    if dev_feature_csv is not None and dev_labels is not None and out_dev is not None:
        if out_model_dir is None:
            raise RuntimeError("dev prediction requires --out-model-dir to load fold models")
        dev_df = pd.read_csv(dev_feature_csv)
        dev_df["sample_id"] = dev_df["sample_id"].astype(str).str.strip()
        dev_df = dev_df.drop_duplicates(subset=["sample_id"]).set_index("sample_id", drop=False)
        dev_rows = load_jsonl(dev_labels)
        dev_meta = []
        dev_miss = 0
        for r in dev_rows:
            sid = str(r.get("sample_id", "")).strip()
            if not sid:
                continue
            if sid not in dev_df.index:
                dev_miss += 1
                continue
            dev_meta.append(
                {
                    "sample_id": sid,
                    "video": normalize_video_key(r.get("video", "")),
                    "accident_type": str(r.get("accident_type", "")).strip(),
                }
            )
        if not dev_meta:
            raise RuntimeError("dev set empty after feature alignment")
        dev_sids = [x["sample_id"] for x in dev_meta]
        xdev = dev_df.loc[dev_sids, feature_cols].to_numpy(dtype=np.float32)
        all_probs = []
        for mp in model_paths:
            payload = joblib.load(mp)
            model = payload["model"]
            all_probs.append(model.predict_proba(xdev)[:, 1])
        pdev = np.mean(np.stack(all_probs, axis=0), axis=0)
        ydev = np.array([is_lane(x["accident_type"]) for x in dev_meta], dtype=np.int64)
        yhat = (pdev >= 0.5).astype(np.int64)
        dev_auc = safe_auc(ydev, pdev)
        dev_m = cls_metrics(ydev, yhat)

        with out_dev.open("w", encoding="utf-8") as f:
            for i, meta in enumerate(dev_meta):
                f.write(
                    json.dumps(
                        {
                            "sample_id": meta["sample_id"],
                            "video": meta["video"],
                            "gt_accident_type": meta["accident_type"],
                            "gt_lane_binary": int(is_lane(meta["accident_type"])),
                            "lane_expert_prob": round(float(pdev[i]), 6),
                            "ensemble_models": len(all_probs),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        dev_summary = {
            "rows": int(len(dev_meta)),
            "missing_feature": int(dev_miss),
            "auc": round(float(dev_auc), 6),
            "accuracy_at_05": round(float(dev_m["accuracy"]), 6),
            "precision_at_05": round(float(dev_m["precision"]), 6),
            "recall_at_05": round(float(dev_m["recall"]), 6),
            "f1_at_05": round(float(dev_m["f1"]), 6),
            "out_dev": str(out_dev),
        }

    report = {
        "feature_csv": str(feature_csv),
        "splits_dir": str(splits_dir),
        "folds": [int(x) for x in folds],
        "feature_dim": int(len(feature_cols)),
        "model": "LogisticRegression(class_weight=balanced, solver=liblinear)",
        "params": {
            "C": float(args.c),
            "max_iter": int(args.max_iter),
            "seed": int(args.seed),
        },
        "fold_reports": fold_reports,
        "oof_summary": {
            "rows": int(len(oof_rows_sorted)),
            "auc": round(float(oof_auc), 6),
            "accuracy_at_05": round(float(oof_m["accuracy"]), 6),
            "precision_at_05": round(float(oof_m["precision"]), 6),
            "recall_at_05": round(float(oof_m["recall"]), 6),
            "f1_at_05": round(float(oof_m["f1"]), 6),
            "out_oof": str(out_oof),
        },
        "dev_summary": dev_summary,
        "model_paths": [str(x) for x in model_paths],
    }
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
