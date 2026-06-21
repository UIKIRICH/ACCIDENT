import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


DEFAULT_TYPE_CLASSES = ["rear_end", "lane_change", "turn_conflict", "generic"]

REQUIRED_GT_FIELDS = {
    "video",
    "accident_type",
    "onset_time",
    "impact_time",
    "post_time",
    "scene_tags",
}

REQUIRED_PRED_FIELDS = {
    "video",
    "pred_type",
    "type_probs",
    "pred_onset_time",
    "pred_impact_time",
    "pred_post_time",
    "lead_time_sec",
    "risk_score",
    "uncertainty",
    "keyframe_times",
    "scene_tags",
}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
            rows.append(obj)
    return rows


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def ensure_list(v: Any) -> List[Any]:
    if isinstance(v, list):
        return v
    if v is None:
        return []
    return [v]


def validate_gt_rows(rows: Iterable[Dict[str, Any]], path: Path) -> None:
    for i, row in enumerate(rows, start=1):
        missing = [k for k in REQUIRED_GT_FIELDS if k not in row]
        if missing:
            raise ValueError(f"{path}:{i} missing gt fields: {', '.join(missing)}")


def validate_pred_rows(rows: Iterable[Dict[str, Any]], path: Path, classes: List[str]) -> None:
    for i, row in enumerate(rows, start=1):
        missing = [k for k in REQUIRED_PRED_FIELDS if k not in row]
        if missing:
            raise ValueError(f"{path}:{i} missing pred fields: {', '.join(missing)}")

        if not isinstance(row["type_probs"], dict):
            raise ValueError(f"{path}:{i} field type_probs must be an object")

        probs = row["type_probs"]
        for c in classes:
            if c not in probs:
                raise ValueError(f"{path}:{i} type_probs missing class key: {c}")

        if not isinstance(row["keyframe_times"], list):
            raise ValueError(f"{path}:{i} keyframe_times must be an array")
        if not isinstance(row["scene_tags"], list):
            raise ValueError(f"{path}:{i} scene_tags must be an array")


def parse_classes(raw: str) -> List[str]:
    if not raw.strip():
        return list(DEFAULT_TYPE_CLASSES)
    classes = [x.strip() for x in raw.split(",") if x.strip()]
    if not classes:
        return list(DEFAULT_TYPE_CLASSES)
    return classes


def build_index(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    idx: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        idx[normalize_video_key(r["video"])] = r
    return idx


def macro_f1(y_true: List[str], y_pred: List[str], classes: List[str]) -> Tuple[float, Dict[str, Dict[str, float]]]:
    out: Dict[str, Dict[str, float]] = {}
    f1s: List[float] = []

    for c in classes:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)

        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0

        out[c] = {
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "support": int(sum(1 for t in y_true if t == c)),
        }
        f1s.append(f1)

    return (sum(f1s) / len(f1s) if f1s else 0.0), out


def build_confusion_matrix(y_true: List[str], y_pred: List[str], classes: List[str]) -> Dict[str, Any]:
    matrix: Dict[str, Dict[str, int]] = {
        t: {p: 0 for p in classes} for t in classes
    }
    for t, p in zip(y_true, y_pred):
        if t in matrix and p in matrix[t]:
            matrix[t][p] += 1

    normalized: Dict[str, Dict[str, float]] = {}
    for t in classes:
        row_total = sum(matrix[t].values())
        if row_total <= 0:
            normalized[t] = {p: 0.0 for p in classes}
        else:
            normalized[t] = {
                p: round(matrix[t][p] / row_total, 6) for p in classes
            }
    return {
        "classes": classes,
        "counts": matrix,
        "row_normalized": normalized,
    }


def mae(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def calc_keyframe_hit_at_k(pred_keyframes: List[float], target_time: float, k: int, tol_sec: float) -> int:
    topk = pred_keyframes[: max(1, k)]
    if any(abs(t - target_time) <= tol_sec for t in topk):
        return 1
    return 0


def ece_multiclass(y_true: List[str], rows_pred: List[Dict[str, Any]], bins: int = 10) -> float:
    if not y_true or not rows_pred:
        return 0.0

    bucket_total = [0] * bins
    bucket_conf_sum = [0.0] * bins
    bucket_acc_sum = [0.0] * bins

    for gt, row in zip(y_true, rows_pred):
        probs = row["type_probs"]
        pred = str(row["pred_type"])
        conf = safe_float(probs.get(pred, 0.0), 0.0)
        conf = max(0.0, min(1.0, conf))
        acc = 1.0 if pred == gt else 0.0
        b = min(bins - 1, int(conf * bins))
        bucket_total[b] += 1
        bucket_conf_sum[b] += conf
        bucket_acc_sum[b] += acc

    n = len(y_true)
    ece = 0.0
    for b in range(bins):
        if bucket_total[b] == 0:
            continue
        avg_conf = bucket_conf_sum[b] / bucket_total[b]
        avg_acc = bucket_acc_sum[b] / bucket_total[b]
        ece += (bucket_total[b] / n) * abs(avg_acc - avg_conf)
    return ece


def compute_metrics(
    gt_rows: List[Dict[str, Any]],
    pred_rows: List[Dict[str, Any]],
    classes: List[str],
    keyframe_k: int,
    keyframe_tol_sec: float,
) -> Dict[str, Any]:
    gt_map = build_index(gt_rows)
    pred_map = build_index(pred_rows)

    videos_common = sorted(set(gt_map.keys()) & set(pred_map.keys()))
    videos_missing_pred = sorted(set(gt_map.keys()) - set(pred_map.keys()))
    videos_extra_pred = sorted(set(pred_map.keys()) - set(gt_map.keys()))

    y_true: List[str] = []
    y_pred: List[str] = []
    matched_pred_rows: List[Dict[str, Any]] = []

    onset_abs_err: List[float] = []
    impact_abs_err: List[float] = []
    post_abs_err: List[float] = []
    lead_time_vals: List[float] = []
    keyframe_hits: List[int] = []
    keyframe_min_abs_err: List[float] = []

    for v in videos_common:
        g = gt_map[v]
        p = pred_map[v]

        gt_type = str(g["accident_type"])
        pred_type = str(p["pred_type"])
        y_true.append(gt_type)
        y_pred.append(pred_type)
        matched_pred_rows.append(p)

        gt_onset = safe_float(g["onset_time"], 0.0)
        gt_impact = safe_float(g["impact_time"], 0.0)
        gt_post = safe_float(g["post_time"], 0.0)
        pred_onset = safe_float(p["pred_onset_time"], 0.0)
        pred_impact = safe_float(p["pred_impact_time"], 0.0)
        pred_post = safe_float(p["pred_post_time"], 0.0)

        onset_abs_err.append(abs(pred_onset - gt_onset))
        impact_abs_err.append(abs(pred_impact - gt_impact))
        post_abs_err.append(abs(pred_post - gt_post))

        lead_time_vals.append(max(0.0, safe_float(p["lead_time_sec"], 0.0)))

        pred_kf = [safe_float(x, 0.0) for x in ensure_list(p.get("keyframe_times", []))]
        keyframe_hits.append(calc_keyframe_hit_at_k(pred_kf, gt_impact, keyframe_k, keyframe_tol_sec))
        if pred_kf:
            keyframe_min_abs_err.append(min(abs(t - gt_impact) for t in pred_kf[: max(1, keyframe_k)]))
        else:
            keyframe_min_abs_err.append(float("inf"))

    macro, class_metrics = macro_f1(y_true, y_pred, classes)
    confusion = build_confusion_matrix(y_true, y_pred, classes)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true) if y_true else 0.0
    ece = ece_multiclass(y_true, matched_pred_rows, bins=10)

    finite_kf_err = [x for x in keyframe_min_abs_err if math.isfinite(x)]

    return {
        "n_gt": len(gt_rows),
        "n_pred": len(pred_rows),
        "n_matched": len(videos_common),
        "missing_pred_count": len(videos_missing_pred),
        "extra_pred_count": len(videos_extra_pred),
        "missing_pred_videos": videos_missing_pred,
        "extra_pred_videos": videos_extra_pred,
        "type_f1_macro": round(macro, 6),
        "type_accuracy": round(acc, 6),
        "type_class_metrics": class_metrics,
        "type_confusion_matrix": confusion,
        "onset_time_mae": round(mae(onset_abs_err), 6),
        "impact_time_mae": round(mae(impact_abs_err), 6),
        "post_time_mae": round(mae(post_abs_err), 6),
        "lead_time_mean": round(mae(lead_time_vals), 6),
        f"keyframe_hit_at_{keyframe_k}": round(mae([float(x) for x in keyframe_hits]), 6),
        f"keyframe_min_abs_err_at_{keyframe_k}": round(mae(finite_kf_err), 6) if finite_kf_err else None,
        "ece_10bin": round(ece, 6),
    }


def group_rows_by_tag(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        tags = [str(x) for x in ensure_list(row.get("scene_tags", []))]
        if not tags:
            tags = ["_no_tag"]
        for tag in tags:
            groups.setdefault(tag, []).append(row)
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate prediction jsonl against ground-truth jsonl.")
    parser.add_argument("--pred", required=True, help="Prediction jsonl path")
    parser.add_argument("--gt", required=True, help="Ground-truth labels jsonl path")
    parser.add_argument("--out", required=True, help="Output metrics json path")
    parser.add_argument("--group-by", default="", choices=["", "scene_tags"], help="Optional grouped metrics")
    parser.add_argument(
        "--classes",
        default="",
        help="Comma-separated class list for main metrics, e.g. rear_end,lane_change,turn_conflict",
    )
    parser.add_argument("--keyframe-k", type=int, default=5, help="K for keyframe hit@K")
    parser.add_argument("--keyframe-tol-sec", type=float, default=0.5, help="Hit tolerance around gt impact time")
    args = parser.parse_args()

    pred_path = Path(args.pred).resolve()
    gt_path = Path(args.gt).resolve()
    out_path = Path(args.out).resolve()

    gt_rows = load_jsonl(gt_path)
    pred_rows = load_jsonl(pred_path)
    eval_classes = parse_classes(args.classes)

    validate_gt_rows(gt_rows, gt_path)
    validate_pred_rows(pred_rows, pred_path, DEFAULT_TYPE_CLASSES)

    main_metrics = compute_metrics(
        gt_rows=gt_rows,
        pred_rows=pred_rows,
        classes=eval_classes,
        keyframe_k=args.keyframe_k,
        keyframe_tol_sec=args.keyframe_tol_sec,
    )

    result: Dict[str, Any] = {
        "format_version": "eval_v1",
        "pred_path": str(pred_path),
        "gt_path": str(gt_path),
        "keyframe_k": int(args.keyframe_k),
        "keyframe_tol_sec": float(args.keyframe_tol_sec),
        "eval_classes": eval_classes,
        "required_pred_fields": sorted(list(REQUIRED_PRED_FIELDS)),
        "required_gt_fields": sorted(list(REQUIRED_GT_FIELDS)),
        "metrics": main_metrics,
    }

    if args.group_by == "scene_tags":
        grouped: Dict[str, Any] = {}
        gt_by_tag = group_rows_by_tag(gt_rows)
        for tag, gt_subset in gt_by_tag.items():
            grouped[tag] = compute_metrics(
                gt_rows=gt_subset,
                pred_rows=pred_rows,
                classes=eval_classes,
                keyframe_k=args.keyframe_k,
                keyframe_tol_sec=args.keyframe_tol_sec,
            )
        result["grouped_metrics"] = {"scene_tags": grouped}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] metrics saved: {out_path}")
    print(json.dumps(result["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
