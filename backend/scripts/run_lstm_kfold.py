import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


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


def parse_scene_tags(row: Dict[str, Any]) -> List[str]:
    tags: List[str] = []
    scene_tags = row.get("scene_tags", None)
    if isinstance(scene_tags, list):
        tags.extend([str(x).strip() for x in scene_tags if str(x).strip()])
    elif isinstance(scene_tags, str) and scene_tags.strip():
        tags.append(scene_tags.strip())

    scene_profile = str(row.get("scene_profile", "")).strip()
    if scene_profile and scene_profile.lower() != "custom":
        tags.append(scene_profile)

    extra_scene_tags = str(row.get("extra_scene_tags", "")).strip()
    if extra_scene_tags:
        for token in extra_scene_tags.replace(";", ",").split(","):
            t = token.strip()
            if t:
                tags.append(t)

    out: List[str] = []
    seen = set()
    for t in tags:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def write_jsonl(rows: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def mean_std(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {"mean": 0.0, "std": 0.0}
    m = sum(vals) / len(vals)
    v = sum((x - m) ** 2 for x in vals) / len(vals)
    return {"mean": float(m), "std": float(v ** 0.5)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BiLSTM+Attention classification on grouped K-fold splits.")
    parser.add_argument("--feature-csv", required=True, help="Feature CSV with sample_id + feature_*")
    parser.add_argument("--splits-dir", required=True, help="Directory with fold{i}_train/val.jsonl")
    parser.add_argument("--checkpoints-dir", required=True)
    parser.add_argument("--preds-dir", required=True)
    parser.add_argument("--reports-dir", required=True)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--seq-len", type=int, default=0, help="0=auto infer from feature_dim")
    parser.add_argument("--hidden-size", type=int, default=64)
    parser.add_argument("--num-layers", type=int, default=1)
    parser.add_argument("--dropout", type=float, default=0.2)
    parser.add_argument("--mlp-hidden", type=int, default=64)
    parser.add_argument("--loss-type", choices=["ce", "focal"], default="focal")
    parser.add_argument("--focal-gamma", type=float, default=2.0)
    parser.add_argument("--no-class-weight", action="store_true")
    parser.add_argument("--class-weight-alpha", type=float, default=0.0)
    parser.add_argument("--class-weight-floor", type=float, default=0.0)
    parser.add_argument("--turn-weight-boost", type=float, default=1.0)
    parser.add_argument("--dual-turn-head", action="store_true")
    parser.add_argument("--turn-bin-loss-weight", type=float, default=0.4)
    parser.add_argument("--turn-fuse-alpha", type=float, default=0.6)
    parser.add_argument("--hard-samples", default="", help="Optional hard sample weights jsonl")
    parser.add_argument("--hard-sample-boost", type=float, default=1.0)
    parser.add_argument("--turn-router-min-prob", type=float, default=0.0)
    parser.add_argument("--turn-router-margin", type=float, default=0.0)
    parser.add_argument("--selection-mode", choices=["macro_f1", "macro_plus_min_recall"], default="macro_f1")
    parser.add_argument("--selection-min-recall-weight", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--rule-preds-dir", default="", help="Optional directory containing pred_rule_fold{i}.jsonl")
    parser.add_argument(
        "--rule-pred-oof",
        default="",
        help="Optional fallback rule prediction jsonl (e.g., pred_rule_oof_v3.jsonl) used when fold file is missing",
    )
    parser.add_argument("--use-gt-timing-fallback", action="store_true")
    parser.add_argument("--eval-classes", default="rear_end,lane_change,turn_conflict")
    parser.add_argument("--skip-eval", action="store_true")
    args = parser.parse_args()

    splits_dir = Path(args.splits_dir).resolve()
    ckpt_dir = Path(args.checkpoints_dir).resolve()
    preds_dir = Path(args.preds_dir).resolve()
    reports_dir = Path(args.reports_dir).resolve()
    feature_csv = Path(args.feature_csv).resolve()
    rule_preds_dir = Path(args.rule_preds_dir).resolve() if str(args.rule_preds_dir).strip() else None
    rule_pred_oof = Path(args.rule_pred_oof).resolve() if str(args.rule_pred_oof).strip() else None
    hard_samples = Path(args.hard_samples).resolve() if str(args.hard_samples).strip() else None
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    preds_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    train_script = (Path(__file__).resolve().parent / "train_lstm_kfold.py").resolve()
    eval_script = (Path(__file__).resolve().parent / "eval_metrics.py").resolve()
    if not train_script.exists():
        raise FileNotFoundError(train_script)

    fold_metrics: Dict[str, Dict[str, Any]] = {}
    acc_vals: List[float] = []
    f1_vals: List[float] = []

    for fold in range(int(args.n_splits)):
        fold_train = splits_dir / f"fold{fold}_train.jsonl"
        fold_val = splits_dir / f"fold{fold}_val.jsonl"
        if not fold_train.exists() or not fold_val.exists():
            raise FileNotFoundError(f"Missing split file for fold={fold}")

        fold_ckpt = ckpt_dir / f"fold{fold}_lstm_best.pt"
        fold_pred = preds_dir / f"pred_lstm_fold{fold}.jsonl"
        fold_metrics_path = reports_dir / f"train_metrics_fold{fold}.json"
        fold_log = reports_dir / f"train_log_fold{fold}.json"
        fold_rule_pred = rule_preds_dir / f"pred_rule_fold{fold}.jsonl" if rule_preds_dir else None

        cmd = [
            sys.executable,
            str(train_script),
            "--feature-csv",
            str(feature_csv),
            "--train-split",
            str(fold_train),
            "--val-split",
            str(fold_val),
            "--out-ckpt",
            str(fold_ckpt),
            "--out-metrics",
            str(fold_metrics_path),
            "--out-val-pred",
            str(fold_pred),
            "--out-train-log",
            str(fold_log),
            "--seq-len",
            str(int(args.seq_len)),
            "--hidden-size",
            str(int(args.hidden_size)),
            "--num-layers",
            str(int(args.num_layers)),
            "--dropout",
            str(float(args.dropout)),
            "--mlp-hidden",
            str(int(args.mlp_hidden)),
            "--epochs",
            str(int(args.epochs)),
            "--patience",
            str(int(args.patience)),
            "--batch-size",
            str(int(args.batch_size)),
            "--lr",
            str(float(args.lr)),
            "--weight-decay",
            str(float(args.weight_decay)),
            "--loss-type",
            str(args.loss_type),
            "--focal-gamma",
            str(float(args.focal_gamma)),
            "--class-weight-alpha",
            str(float(args.class_weight_alpha)),
            "--class-weight-floor",
            str(float(args.class_weight_floor)),
            "--turn-weight-boost",
            str(float(args.turn_weight_boost)),
            "--turn-bin-loss-weight",
            str(float(args.turn_bin_loss_weight)),
            "--turn-fuse-alpha",
            str(float(args.turn_fuse_alpha)),
            "--hard-sample-boost",
            str(float(args.hard_sample_boost)),
            "--turn-router-min-prob",
            str(float(args.turn_router_min_prob)),
            "--turn-router-margin",
            str(float(args.turn_router_margin)),
            "--selection-mode",
            str(args.selection_mode),
            "--selection-min-recall-weight",
            str(float(args.selection_min_recall_weight)),
            "--seed",
            str(int(args.seed)),
        ]
        if args.no_class_weight:
            cmd.append("--no-class-weight")
        if args.use_gt_timing_fallback:
            cmd.append("--use-gt-timing-fallback")
        if args.dual_turn_head:
            cmd.append("--dual-turn-head")
        if hard_samples is not None and hard_samples.exists():
            cmd.extend(["--hard-samples", str(hard_samples)])
        if fold_rule_pred is not None and fold_rule_pred.exists():
            cmd.extend(["--rule-pred", str(fold_rule_pred)])
        elif rule_pred_oof is not None and rule_pred_oof.exists():
            cmd.extend(["--rule-pred", str(rule_pred_oof)])

        print(f"[RUN] fold{fold}")
        subprocess.run(cmd, check=True)

        m = json.loads(fold_metrics_path.read_text(encoding="utf-8"))
        fold_metrics[f"fold{fold}"] = m
        acc_vals.append(float(m.get("val_accuracy", 0.0)))
        f1_vals.append(float(m.get("val_macro_f1", 0.0)))
        print(
            f"[DONE] fold{fold} val_acc={m.get('val_accuracy')} "
            f"val_macro_f1={m.get('val_macro_f1')} best_epoch={m.get('best_epoch')}"
        )

    # Merge OOF predictions
    merged_pred_rows: List[Dict[str, Any]] = []
    for fold in range(int(args.n_splits)):
        fold_pred = preds_dir / f"pred_lstm_fold{fold}.jsonl"
        if fold_pred.exists():
            merged_pred_rows.extend(load_jsonl(fold_pred))
    pred_oof = preds_dir / "pred_lstm_oof.jsonl"
    write_jsonl(merged_pred_rows, pred_oof)

    # Build GT OOF jsonl from val split files for unified evaluation
    gt_rows: List[Dict[str, Any]] = []
    for fold in range(int(args.n_splits)):
        fold_val = splits_dir / f"fold{fold}_val.jsonl"
        for r in load_jsonl(fold_val):
            accident_type = str(r.get("accident_type", "")).strip()
            if accident_type not in CLASS_NAMES:
                continue
            gt_rows.append(
                {
                    "sample_id": str(r.get("sample_id", "")).strip(),
                    "video": normalize_video_key(r.get("video", "")),
                    "accident_type": accident_type,
                    "onset_time": float(r.get("onset_time", 0.0)),
                    "impact_time": float(r.get("impact_time", 0.0)),
                    "post_time": float(r.get("post_time", 0.0)),
                    "scene_tags": parse_scene_tags(r),
                }
            )
    gt_oof = reports_dir / "labels_lstm_oof_gt.jsonl"
    write_jsonl(gt_rows, gt_oof)

    summary = {
        "model": "bilstm_attention_v33",
        "feature_csv": str(feature_csv),
        "splits_dir": str(splits_dir),
        "checkpoints_dir": str(ckpt_dir),
        "preds_dir": str(preds_dir),
        "reports_dir": str(reports_dir),
        "n_splits": int(args.n_splits),
        "seed": int(args.seed),
        "epochs_max": int(args.epochs),
        "patience": int(args.patience),
        "batch_size": int(args.batch_size),
        "lr": float(args.lr),
        "weight_decay": float(args.weight_decay),
        "seq_len": int(args.seq_len),
        "hidden_size": int(args.hidden_size),
        "num_layers": int(args.num_layers),
        "dropout": float(args.dropout),
        "mlp_hidden": int(args.mlp_hidden),
        "loss_type": str(args.loss_type),
        "focal_gamma": float(args.focal_gamma),
        "class_weight_enabled": bool(not args.no_class_weight),
        "class_weight_alpha": float(args.class_weight_alpha),
        "class_weight_floor": float(args.class_weight_floor),
        "turn_weight_boost": float(args.turn_weight_boost),
        "dual_turn_head": bool(args.dual_turn_head),
        "turn_bin_loss_weight": float(args.turn_bin_loss_weight),
        "turn_fuse_alpha": float(args.turn_fuse_alpha),
        "hard_samples": str(hard_samples) if hard_samples else "",
        "hard_sample_boost": float(args.hard_sample_boost),
        "turn_router_min_prob": float(args.turn_router_min_prob),
        "turn_router_margin": float(args.turn_router_margin),
        "selection_mode": str(args.selection_mode),
        "selection_min_recall_weight": float(args.selection_min_recall_weight),
        "rule_preds_dir": str(rule_preds_dir) if rule_preds_dir else "",
        "rule_pred_oof": str(rule_pred_oof) if rule_pred_oof else "",
        "use_gt_timing_fallback": bool(args.use_gt_timing_fallback),
        "fold_metrics": fold_metrics,
        "val_accuracy": mean_std(acc_vals),
        "val_macro_f1": mean_std(f1_vals),
        "pred_oof": str(pred_oof),
        "gt_oof": str(gt_oof),
    }
    out_summary = reports_dir / "lstm_kfold_summary.json"
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] summary={out_summary}")

    if not args.skip_eval and eval_script.exists():
        out_eval = reports_dir / "main_metrics_lstm_oof.json"
        cmd_eval = [
            sys.executable,
            str(eval_script),
            "--pred",
            str(pred_oof),
            "--gt",
            str(gt_oof),
            "--out",
            str(out_eval),
            "--group-by",
            "scene_tags",
            "--classes",
            str(args.eval_classes),
        ]
        subprocess.run(cmd_eval, check=True)
        print(f"[DONE] eval={out_eval}")


if __name__ == "__main__":
    main()
