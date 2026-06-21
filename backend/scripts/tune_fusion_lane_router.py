import argparse
import json
from itertools import product
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


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


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


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


def accuracy(y_true: List[str], y_pred: List[str]) -> float:
    if not y_true:
        return 0.0
    return sum(1 for t, p in zip(y_true, y_pred) if t == p) / len(y_true)


def choose_type(
    row: Dict[str, Any],
    lane_prob_thr: float,
    lane_margin_vs_rear: float,
    lane_margin_vs_turn: float,
    lane_intersection_bonus: float,
) -> str:
    probs = row.get("type_probs", {}) or {}
    rear = safe_float(probs.get("rear_end", 0.0))
    lane = safe_float(probs.get("lane_change", 0.0))
    turn = safe_float(probs.get("turn_conflict", 0.0))
    scene_tags = {str(x) for x in (row.get("scene_tags", []) or [])}

    lane_adj = lane + (lane_intersection_bonus if ("intersection" in scene_tags or "turning_scene" in scene_tags) else 0.0)
    if (
        lane_adj >= lane_prob_thr
        and (lane_adj - rear) >= lane_margin_vs_rear
        and (lane_adj - turn) >= lane_margin_vs_turn
    ):
        return "lane_change"

    if rear >= lane and rear >= turn:
        return "rear_end"
    if turn >= lane:
        return "turn_conflict"
    return "lane_change"


def evaluate(y_true: List[str], y_pred: List[str]) -> Dict[str, float]:
    return {
        "accuracy": accuracy(y_true, y_pred),
        "macro_f1": macro_f1(y_true, y_pred),
        "rear_end_recall": class_recall(y_true, y_pred, "rear_end"),
        "lane_change_recall": class_recall(y_true, y_pred, "lane_change"),
        "turn_conflict_recall": class_recall(y_true, y_pred, "turn_conflict"),
        "rear_end_precision": class_precision(y_true, y_pred, "rear_end"),
        "lane_change_precision": class_precision(y_true, y_pred, "lane_change"),
        "turn_conflict_precision": class_precision(y_true, y_pred, "turn_conflict"),
    }


def lane_confusion_row(y_true: List[str], y_pred: List[str]) -> Dict[str, int]:
    out = {"rear_end": 0, "lane_change": 0, "turn_conflict": 0}
    for t, p in zip(y_true, y_pred):
        if t == "lane_change" and p in out:
            out[p] += 1
    return out


def grid_values(raw: str, cast_type: str) -> List[float]:
    vals = [x.strip() for x in str(raw).split(",") if x.strip()]
    if not vals:
        return []
    if cast_type == "int":
        return [int(x) for x in vals]
    return [float(x) for x in vals]


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune lane_change router thresholds for fusion predictions.")
    parser.add_argument("--pred", required=True, help="Fusion pred jsonl")
    parser.add_argument("--gt", required=True, help="Ground-truth label jsonl")
    parser.add_argument("--out-pred", required=True, help="Output tuned pred jsonl")
    parser.add_argument("--out-report", required=True, help="Output tuning report json")
    parser.add_argument("--lane-prob-grid", default="0.28,0.30,0.32,0.34,0.36,0.38")
    parser.add_argument("--lane-vs-rear-grid", default="-0.06,-0.04,-0.02,0.00,0.02")
    parser.add_argument("--lane-vs-turn-grid", default="-0.06,-0.04,-0.02,0.00,0.02")
    parser.add_argument("--lane-intersection-bonus-grid", default="0.00,0.02,0.04")
    parser.add_argument("--rear-recall-floor", type=float, default=0.66)
    parser.add_argument("--lane-weight", type=float, default=0.35, help="Objective weight for lane recall")
    parser.add_argument("--rear-floor-penalty", type=float, default=0.40, help="Penalty when rear recall < floor")
    args = parser.parse_args()

    pred_rows = load_jsonl(Path(args.pred).resolve())
    gt_rows = load_jsonl(Path(args.gt).resolve())
    pred_map = {normalize_video_key(r.get("video", "")): r for r in pred_rows}
    gt_map = {
        normalize_video_key(r.get("video", "")): r
        for r in gt_rows
        if str(r.get("accident_type", "")) in CLASSES
    }

    keys = sorted(set(pred_map.keys()) & set(gt_map.keys()))
    if not keys:
        raise RuntimeError("No matched samples between pred and gt.")

    y_true = [str(gt_map[k]["accident_type"]) for k in keys]
    baseline_pred = [str(pred_map[k].get("pred_type", "rear_end")) for k in keys]
    baseline_metrics = evaluate(y_true, baseline_pred)
    baseline_lane_row = lane_confusion_row(y_true, baseline_pred)

    lane_prob_grid = grid_values(args.lane_prob_grid, "float")
    lane_vs_rear_grid = grid_values(args.lane_vs_rear_grid, "float")
    lane_vs_turn_grid = grid_values(args.lane_vs_turn_grid, "float")
    lane_bonus_grid = grid_values(args.lane_intersection_bonus_grid, "float")

    best = None
    best_pred_types: List[str] = []
    for lane_prob_thr, lane_vs_rear, lane_vs_turn, lane_bonus in product(
        lane_prob_grid, lane_vs_rear_grid, lane_vs_turn_grid, lane_bonus_grid
    ):
        y_pred: List[str] = []
        for k in keys:
            y_pred.append(
                choose_type(
                    pred_map[k],
                    lane_prob_thr=lane_prob_thr,
                    lane_margin_vs_rear=lane_vs_rear,
                    lane_margin_vs_turn=lane_vs_turn,
                    lane_intersection_bonus=lane_bonus,
                )
            )

        m = evaluate(y_true, y_pred)
        rear_gap = max(0.0, float(args.rear_recall_floor) - m["rear_end_recall"])
        score = m["macro_f1"] + float(args.lane_weight) * m["lane_change_recall"] - float(args.rear_floor_penalty) * rear_gap
        cand = {
            "score": score,
            "lane_prob_thr": lane_prob_thr,
            "lane_margin_vs_rear": lane_vs_rear,
            "lane_margin_vs_turn": lane_vs_turn,
            "lane_intersection_bonus": lane_bonus,
            "metrics": m,
        }
        if best is None or cand["score"] > best["score"]:
            best = cand
            best_pred_types = y_pred

    assert best is not None

    tuned_rows: List[Dict[str, Any]] = []
    tuned_map: Dict[str, str] = {k: p for k, p in zip(keys, best_pred_types)}
    for r in pred_rows:
        v = normalize_video_key(r.get("video", ""))
        out = dict(r)
        if v in tuned_map:
            out["pred_type"] = tuned_map[v]
            out["router_tuned"] = True
            out["router_version"] = "fusion_lane_router_v1"
        tuned_rows.append(out)

    out_pred = Path(args.out_pred).resolve()
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    with out_pred.open("w", encoding="utf-8") as f:
        for r in tuned_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tuned_metrics = evaluate(y_true, best_pred_types)
    tuned_lane_row = lane_confusion_row(y_true, best_pred_types)
    out_report = Path(args.out_report).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "pred_in": str(Path(args.pred).resolve()),
        "gt_in": str(Path(args.gt).resolve()),
        "pred_out": str(out_pred),
        "n_samples": len(keys),
        "objective": {
            "score": "macro_f1 + lane_weight*lane_change_recall - rear_floor_penalty*max(0,rear_recall_floor-rear_recall)",
            "lane_weight": float(args.lane_weight),
            "rear_recall_floor": float(args.rear_recall_floor),
            "rear_floor_penalty": float(args.rear_floor_penalty),
        },
        "search_space": {
            "lane_prob_grid": lane_prob_grid,
            "lane_vs_rear_grid": lane_vs_rear_grid,
            "lane_vs_turn_grid": lane_vs_turn_grid,
            "lane_intersection_bonus_grid": lane_bonus_grid,
            "num_candidates": int(len(lane_prob_grid) * len(lane_vs_rear_grid) * len(lane_vs_turn_grid) * len(lane_bonus_grid)),
        },
        "baseline": {
            "metrics": baseline_metrics,
            "lane_confusion_row": baseline_lane_row,
        },
        "best_params": {
            "lane_prob_thr": best["lane_prob_thr"],
            "lane_margin_vs_rear": best["lane_margin_vs_rear"],
            "lane_margin_vs_turn": best["lane_margin_vs_turn"],
            "lane_intersection_bonus": best["lane_intersection_bonus"],
            "score": best["score"],
        },
        "tuned": {
            "metrics": tuned_metrics,
            "lane_confusion_row": tuned_lane_row,
        },
        "delta": {
            "accuracy": tuned_metrics["accuracy"] - baseline_metrics["accuracy"],
            "macro_f1": tuned_metrics["macro_f1"] - baseline_metrics["macro_f1"],
            "rear_end_recall": tuned_metrics["rear_end_recall"] - baseline_metrics["rear_end_recall"],
            "lane_change_recall": tuned_metrics["lane_change_recall"] - baseline_metrics["lane_change_recall"],
            "turn_conflict_recall": tuned_metrics["turn_conflict_recall"] - baseline_metrics["turn_conflict_recall"],
        },
    }
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
