import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def mean_std(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / len(vals)
    v = sum((x - m) ** 2 for x in vals) / len(vals)
    return {"mean": float(m), "std": float(v**0.5)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run fusion training across K folds.")
    parser.add_argument("--features-dir", required=True, help="Directory containing meta_fold{i}_train/val.parquet")
    parser.add_argument("--checkpoints-dir", required=True, help="Output checkpoint directory")
    parser.add_argument("--preds-dir", required=True, help="Output prediction directory")
    parser.add_argument("--reports-dir", required=True, help="Output report directory")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=240)
    parser.add_argument("--patience", type=int, default=40)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--loss-type", choices=["ce", "focal"], default="ce")
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--no-class-weight", action="store_true")
    parser.add_argument("--rule-preds-dir", default="", help="Directory with pred_rule_fold{i}.jsonl for timing inheritance")
    parser.add_argument("--inherit-timing", action="store_true", help="Inherit timing/keyframe fields from rule preds")
    parser.add_argument("--inherit-time-fields", default="pred_onset_time,pred_impact_time,pred_post_time,lead_time_sec,keyframe_times,scene_tags")
    args = parser.parse_args()

    features_dir = Path(args.features_dir).resolve()
    ckpt_dir = Path(args.checkpoints_dir).resolve()
    preds_dir = Path(args.preds_dir).resolve()
    reports_dir = Path(args.reports_dir).resolve()
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    preds_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    train_script = (Path(__file__).resolve().parent / "train_fusion_v1.py").resolve()
    inherit_script = (Path(__file__).resolve().parent / "inherit_rule_timing.py").resolve()
    if not train_script.exists():
        raise FileNotFoundError(train_script)
    if args.inherit_timing and not inherit_script.exists():
        raise FileNotFoundError(inherit_script)

    fold_metrics: Dict[str, Dict[str, Any]] = {}
    fold_acc: List[float] = []
    fold_f1: List[float] = []

    rule_preds_dir = Path(args.rule_preds_dir).resolve() if str(args.rule_preds_dir).strip() else None
    if args.inherit_timing and rule_preds_dir is None:
        raise ValueError("--inherit-timing requires --rule-preds-dir")

    for fold in range(int(args.n_splits)):
        train_meta = features_dir / f"meta_fold{fold}_train.parquet"
        val_meta = features_dir / f"meta_fold{fold}_val.parquet"
        if not train_meta.exists() or not val_meta.exists():
            raise FileNotFoundError(f"Missing fold parquet: fold={fold}")

        out_ckpt = ckpt_dir / f"fold{fold}_best.pt"
        out_pred_raw = preds_dir / f"pred_fusion_fold{fold}_raw.jsonl"
        out_pred_final = preds_dir / f"pred_fusion_fold{fold}.jsonl"
        out_metrics = reports_dir / f"train_metrics_fold{fold}.json"
        out_log = reports_dir / f"train_log_fold{fold}.json"

        cmd = [
            sys.executable,
            str(train_script),
            "--train-meta",
            str(train_meta),
            "--val-meta",
            str(val_meta),
            "--out-ckpt",
            str(out_ckpt),
            "--out-metrics",
            str(out_metrics),
            "--out-val-pred",
            str(out_pred_raw),
            "--out-train-log",
            str(out_log),
            "--epochs",
            str(int(args.epochs)),
            "--patience",
            str(int(args.patience)),
            "--lr",
            str(float(args.lr)),
            "--seed",
            str(int(args.seed)),
            "--loss-type",
            str(args.loss_type),
            "--focal-gamma",
            str(float(args.focal_gamma)),
        ]
        if args.no_class_weight:
            cmd.append("--no-class-weight")
        print(f"[RUN] fold{fold}")
        subprocess.run(cmd, check=True)

        timing_inherited = False
        if args.inherit_timing:
            rule_pred = rule_preds_dir / f"pred_rule_fold{fold}.jsonl"
            inherit_cmd = [
                sys.executable,
                str(inherit_script),
                "--fusion",
                str(out_pred_raw),
                "--rule",
                str(rule_pred),
                "--out",
                str(out_pred_final),
                "--time-fields",
                str(args.inherit_time_fields),
            ]
            subprocess.run(inherit_cmd, check=True)
            timing_inherited = True
        else:
            out_pred_final.write_text(out_pred_raw.read_text(encoding="utf-8"), encoding="utf-8")

        metrics = json.loads(out_metrics.read_text(encoding="utf-8"))
        metrics["pred_file"] = str(out_pred_final.resolve())
        metrics["pred_file_raw"] = str(out_pred_raw.resolve())
        metrics["timing_inherited"] = bool(timing_inherited)
        out_metrics.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        fold_metrics[f"fold{fold}"] = metrics
        fold_acc.append(float(metrics.get("val_accuracy", 0.0)))
        fold_f1.append(float(metrics.get("val_macro_f1", 0.0)))
        print(
            f"[DONE] fold{fold} val_acc={metrics.get('val_accuracy')} "
            f"val_macro_f1={metrics.get('val_macro_f1')} best_epoch={metrics.get('best_epoch')}"
        )

    summary = {
        "n_splits": int(args.n_splits),
        "epochs_max": int(args.epochs),
        "patience": int(args.patience),
        "lr": float(args.lr),
        "seed": int(args.seed),
        "loss_type": str(args.loss_type),
        "focal_gamma": float(args.focal_gamma),
        "class_weight_enabled": bool(not args.no_class_weight),
        "inherit_timing": bool(args.inherit_timing),
        "inherit_time_fields": str(args.inherit_time_fields),
        "rule_preds_dir": str(rule_preds_dir) if rule_preds_dir else "",
        "features_dir": str(features_dir),
        "checkpoints_dir": str(ckpt_dir),
        "preds_dir": str(preds_dir),
        "reports_dir": str(reports_dir),
        "fold_metrics": fold_metrics,
        "val_accuracy": mean_std(fold_acc),
        "val_macro_f1": mean_std(fold_f1),
    }
    out_summary = reports_dir / "fusion_kfold_summary.json"
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] summary={out_summary}")
    print(json.dumps({"val_accuracy": summary["val_accuracy"], "val_macro_f1": summary["val_macro_f1"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
