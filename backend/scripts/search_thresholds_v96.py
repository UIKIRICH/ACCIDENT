import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


CLASSES = ["rear_end", "lane_change", "turn_conflict"]


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def macro_f1(y_true: List[str], y_pred: List[str]) -> float:
    f1s: List[float] = []
    for c in CLASSES:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1s.append(f1)
    return sum(f1s) / len(f1s) if f1s else 0.0


def class_recall(y_true: List[str], y_pred: List[str], cls: str) -> float:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)
    return tp / (tp + fn) if (tp + fn) else 0.0


def class_precision(y_true: List[str], y_pred: List[str], cls: str) -> float:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
    return tp / (tp + fp) if (tp + fp) else 0.0


def choose_type_with_thresholds(
    row: Dict[str, Any],
    turn_prob_thr: float,
    turn_stage2_thr: float,
    turn_margin: float,
    lane_prob_thr: float,
    lane_margin: float,
) -> str:
    probs = row.get("type_probs", {}) or {}
    rear = safe_float(probs.get("rear_end", 0.0))
    lane = safe_float(probs.get("lane_change", 0.0))
    turn = safe_float(probs.get("turn_conflict", 0.0))

    scene_prior = row.get("scene_prior", {}) or {}
    stage2 = safe_float(scene_prior.get("stage2_score", 0.0), 0.0)

    if turn >= turn_prob_thr and stage2 >= turn_stage2_thr and (turn - rear) >= -turn_margin:
        return "turn_conflict"
    if lane >= lane_prob_thr and (lane - rear) >= lane_margin and lane >= turn:
        return "lane_change"
    if rear >= lane and rear >= turn:
        return "rear_end"
    return "lane_change" if lane >= turn else "turn_conflict"


def main() -> None:
    parser = argparse.ArgumentParser(description="Threshold search for v9.6 router predictions.")
    parser.add_argument("--pred", required=True, help="Prediction jsonl (with scene_prior/stage2_score)")
    parser.add_argument("--gt", required=True, help="Ground-truth 3-class jsonl")
    parser.add_argument("--out-report", required=True, help="Output report json")
    parser.add_argument("--out-pred", required=True, help="Output tuned pred jsonl")
    args = parser.parse_args()

    pred_rows = load_jsonl(Path(args.pred).resolve())
    gt_rows = load_jsonl(Path(args.gt).resolve())
    gt_map = {normalize_video_key(r["video"]): r for r in gt_rows}
    pred_map = {normalize_video_key(r["video"]): r for r in pred_rows}
    keys = sorted(set(gt_map.keys()) & set(pred_map.keys()))

    y_true = [str(gt_map[k]["accident_type"]) for k in keys]

    best = None
    best_pred_types: List[str] = []

    for turn_prob_thr in [0.30, 0.33, 0.36, 0.39, 0.42]:
        for turn_stage2_thr in [0.34, 0.38, 0.42, 0.46, 0.50]:
            for turn_margin in [0.02, 0.05, 0.08, 0.12, 0.16]:
                for lane_prob_thr in [0.30, 0.33, 0.36]:
                    for lane_margin in [0.00, 0.03, 0.06]:
                        y_pred: List[str] = []
                        for k in keys:
                            y_pred.append(
                                choose_type_with_thresholds(
                                    pred_map[k],
                                    turn_prob_thr=turn_prob_thr,
                                    turn_stage2_thr=turn_stage2_thr,
                                    turn_margin=turn_margin,
                                    lane_prob_thr=lane_prob_thr,
                                    lane_margin=lane_margin,
                                )
                            )
                        mf1 = macro_f1(y_true, y_pred)
                        tr = class_recall(y_true, y_pred, "turn_conflict")
                        rp = class_precision(y_true, y_pred, "rear_end")
                        score = 0.70 * mf1 + 0.30 * tr
                        # Keep rear-end precision from collapsing.
                        if rp < 0.30:
                            score -= 0.06

                        candidate = {
                            "score": score,
                            "macro_f1": mf1,
                            "turn_recall": tr,
                            "rear_end_precision": rp,
                            "turn_prob_thr": turn_prob_thr,
                            "turn_stage2_thr": turn_stage2_thr,
                            "turn_margin": turn_margin,
                            "lane_prob_thr": lane_prob_thr,
                            "lane_margin": lane_margin,
                        }

                        if best is None or candidate["score"] > best["score"]:
                            best = candidate
                            best_pred_types = y_pred

    assert best is not None

    tuned_rows: List[Dict[str, Any]] = []
    for k, pred_type in zip(keys, best_pred_types):
        row = dict(pred_map[k])
        row["pred_type"] = pred_type
        row["threshold_tuned"] = True
        tuned_rows.append(row)

    out_pred = Path(args.out_pred).resolve()
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    with out_pred.open("w", encoding="utf-8") as f:
        for r in tuned_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    out_report = Path(args.out_report).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "best": best,
        "n_samples": len(keys),
        "pred_in": str(Path(args.pred).resolve()),
        "gt_in": str(Path(args.gt).resolve()),
        "pred_out": str(out_pred),
        "objective": "0.70*macro_f1 + 0.30*turn_recall - rear_precision_penalty",
    }
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

