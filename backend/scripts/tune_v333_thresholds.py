import argparse
import itertools
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


CLASSES = ["rear_end", "lane_change", "turn_conflict"]


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


def normalize_video(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def index_rows(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_sid: Dict[str, Dict[str, Any]] = {}
    by_video: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sid = str(row.get("sample_id", "")).strip()
        if sid:
            by_sid[sid] = row
        video = normalize_video(row.get("video", ""))
        if video:
            by_video[video] = row
    return by_sid, by_video


def precision_recall_f1(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return precision, recall, f1


def evaluate(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    per_class: Dict[str, Dict[str, Any]] = {}
    f1_sum = 0.0
    for cls in CLASSES:
        tp = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cls and yp == cls)
        fp = sum(1 for yt, yp in zip(y_true, y_pred) if yt != cls and yp == cls)
        fn = sum(1 for yt, yp in zip(y_true, y_pred) if yt == cls and yp != cls)
        support = sum(1 for yt in y_true if yt == cls)
        precision, recall, f1 = precision_recall_f1(tp, fp, fn)
        per_class[cls] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        f1_sum += f1
    acc = sum(1 for yt, yp in zip(y_true, y_pred) if yt == yp) / max(1, len(y_true))
    return {
        "accuracy": acc,
        "macro_f1": f1_sum / len(CLASSES),
        "per_class": per_class,
    }


def pick_label(probs: Dict[str, float], turn_thr: float, lane_thr: float, lane_margin: float) -> str:
    p_rear = float(probs.get("rear_end", 0.0))
    p_lane = float(probs.get("lane_change", 0.0))
    p_turn = float(probs.get("turn_conflict", 0.0))
    if p_turn >= turn_thr:
        return "turn_conflict"
    if p_lane >= lane_thr and (p_lane - p_rear) >= lane_margin:
        return "lane_change"
    return "rear_end" if p_rear >= p_lane else "lane_change"


def main() -> None:
    parser = argparse.ArgumentParser(description="Threshold search for v3.3.3 OOF predictions.")
    parser.add_argument("--pred", required=True, help="OOF prediction jsonl")
    parser.add_argument("--gt", required=True, help="OOF GT jsonl")
    parser.add_argument("--out", required=True, help="Output json report path")
    parser.add_argument("--out-pred", default="", help="Optional tuned pred jsonl output")
    parser.add_argument("--target-rear-recall", type=float, default=0.45)
    parser.add_argument("--target-lane-recall", type=float, default=0.45)
    parser.add_argument("--target-turn-recall", type=float, default=0.55)
    parser.add_argument("--penalty-weight", type=float, default=5.0)
    args = parser.parse_args()

    pred_rows = load_jsonl(Path(args.pred).resolve())
    gt_rows = load_jsonl(Path(args.gt).resolve())
    pred_sid, pred_video = index_rows(pred_rows)

    matched: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for gt in gt_rows:
        gt_type = str(gt.get("accident_type", "")).strip()
        if gt_type not in CLASSES:
            continue
        sid = str(gt.get("sample_id", "")).strip()
        video = normalize_video(gt.get("video", ""))
        pred: Optional[Dict[str, Any]] = pred_sid.get(sid) if sid else None
        if pred is None and video:
            pred = pred_video.get(video)
        if pred is None:
            continue
        matched.append((gt, pred))

    turn_grid = [round(x, 3) for x in [0.36 + i * 0.02 for i in range(16)]]   # 0.36~0.66
    lane_grid = [round(x, 3) for x in [0.22 + i * 0.02 for i in range(16)]]   # 0.22~0.52
    margin_grid = [round(x, 3) for x in [-0.08 + i * 0.02 for i in range(16)]]  # -0.08~0.22

    best_obj = -1e9
    best_cfg: Dict[str, float] = {}
    best_metrics: Dict[str, Any] = {}
    best_preds: List[str] = []

    feasible_best_obj = -1e9
    feasible_cfg: Dict[str, float] = {}
    feasible_metrics: Dict[str, Any] = {}
    feasible_preds: List[str] = []

    for t_turn, t_lane, lane_margin in itertools.product(turn_grid, lane_grid, margin_grid):
        y_true: List[str] = []
        y_pred: List[str] = []
        for gt, pred in matched:
            gt_type = str(gt.get("accident_type", "")).strip()
            probs = pred.get("type_probs", {}) if isinstance(pred.get("type_probs", {}), dict) else {}
            y_true.append(gt_type)
            y_pred.append(pick_label(probs, t_turn, t_lane, lane_margin))
        m = evaluate(y_true, y_pred)
        rear_r = float(m["per_class"]["rear_end"]["recall"])
        lane_r = float(m["per_class"]["lane_change"]["recall"])
        turn_r = float(m["per_class"]["turn_conflict"]["recall"])
        deficits = (
            max(0.0, float(args.target_rear_recall) - rear_r)
            + max(0.0, float(args.target_lane_recall) - lane_r)
            + max(0.0, float(args.target_turn_recall) - turn_r)
        )
        objective = float(m["macro_f1"]) - (float(args.penalty_weight) * deficits)
        if objective > best_obj:
            best_obj = objective
            best_cfg = {"turn_thr": t_turn, "lane_thr": t_lane, "lane_margin": lane_margin}
            best_metrics = m
            best_preds = y_pred

        feasible = (
            rear_r >= float(args.target_rear_recall)
            and lane_r >= float(args.target_lane_recall)
            and turn_r >= float(args.target_turn_recall)
        )
        if feasible:
            feasible_obj = float(m["macro_f1"]) + (0.1 * float(m["accuracy"]))
            if feasible_obj > feasible_best_obj:
                feasible_best_obj = feasible_obj
                feasible_cfg = {"turn_thr": t_turn, "lane_thr": t_lane, "lane_margin": lane_margin}
                feasible_metrics = m
                feasible_preds = y_pred

    picked_cfg = feasible_cfg if feasible_cfg else best_cfg
    picked_metrics = feasible_metrics if feasible_metrics else best_metrics
    picked_preds = feasible_preds if feasible_preds else best_preds
    picked_feasible = bool(feasible_cfg)

    out_rows: List[Dict[str, Any]] = []
    for (gt, pred), new_type in zip(matched, picked_preds):
        row = dict(pred)
        row["pred_type"] = new_type
        row["threshold_tuned"] = True
        row["threshold_cfg"] = picked_cfg
        out_rows.append(row)

    report = {
        "n_matched": len(matched),
        "search_grid": {
            "turn_thr": [min(turn_grid), max(turn_grid), len(turn_grid)],
            "lane_thr": [min(lane_grid), max(lane_grid), len(lane_grid)],
            "lane_margin": [min(margin_grid), max(margin_grid), len(margin_grid)],
        },
        "target": {
            "rear_recall": float(args.target_rear_recall),
            "lane_recall": float(args.target_lane_recall),
            "turn_recall": float(args.target_turn_recall),
        },
        "picked_is_feasible": picked_feasible,
        "picked_cfg": picked_cfg,
        "picked_metrics": picked_metrics,
        "fallback_best_objective": best_obj,
    }

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if str(args.out_pred).strip():
        out_pred_path = Path(args.out_pred).resolve()
        out_pred_path.parent.mkdir(parents=True, exist_ok=True)
        with out_pred_path.open("w", encoding="utf-8") as f:
            for row in out_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

