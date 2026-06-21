import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def parse_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [str(x).strip() for x in obj if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [s]


def parse_grid(raw: str) -> List[float]:
    vals: List[float] = []
    for x in str(raw).split(","):
        s = x.strip()
        if not s:
            continue
        vals.append(float(s))
    if not vals:
        raise ValueError("empty threshold grid")
    return vals


def base_turn_rear_pick(type_probs: Dict[str, Any]) -> str:
    pr = safe_float(type_probs.get("rear_end", 0.0))
    pt = safe_float(type_probs.get("turn_conflict", 0.0))
    return "rear_end" if pr >= pt else "turn_conflict"


def apply_rear_guard(
    pred_type: str,
    type_probs: Dict[str, Any],
    scene_tags: List[str],
    rear_floor: float,
    gap_max: float,
    turn_ceiling: float,
    lane_cap: float,
) -> Tuple[str, bool]:
    if pred_type != "turn_conflict":
        return pred_type, False
    tags = {str(x).strip() for x in scene_tags if str(x).strip()}
    if "intersection" in tags or "turning_scene" in tags:
        return pred_type, False
    pr = safe_float(type_probs.get("rear_end", 0.0))
    pl = safe_float(type_probs.get("lane_change", 0.0))
    pt = safe_float(type_probs.get("turn_conflict", 0.0))
    if pr >= rear_floor and (pt - pr) <= gap_max and pt <= turn_ceiling and pl <= lane_cap:
        return "rear_end", True
    return pred_type, False


def evaluate_rows(
    y_true: List[str],
    y_pred: List[str],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "accuracy": 0.0,
        "macro_f1": 0.0,
        "per_class": {},
    }
    if not y_true:
        return out
    n = len(y_true)
    out["accuracy"] = float(sum(1 for t, p in zip(y_true, y_pred) if t == p) / n)

    f1s: List[float] = []
    for c in CLASSES:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        out["per_class"][c] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "support": int(sum(1 for t in y_true if t == c)),
        }
        f1s.append(float(f1))
    out["macro_f1"] = float(sum(f1s) / len(f1s)) if f1s else 0.0
    return out


def build_pred_for_threshold(
    main_rows: List[Dict[str, Any]],
    lane_prob_map: Dict[str, float],
    thr: float,
    rear_floor: float,
    gap_max: float,
    turn_ceiling: float,
    lane_cap: float,
) -> List[Dict[str, Any]]:
    out_rows: List[Dict[str, Any]] = []
    for r in main_rows:
        out = dict(r)
        vkey = normalize_video_key(r.get("video", ""))
        lp = float(lane_prob_map.get(vkey, 0.0))
        probs = r.get("type_probs", {}) or {}
        scene_tags = parse_scene_tags(r.get("scene_tags", []))

        lane_applied = lp >= thr
        if lane_applied:
            pred = "lane_change"
            route_mode = "lane_expert_priority"
        else:
            pred = base_turn_rear_pick(probs)
            route_mode = "rear_turn_main"
        pred2, rear_applied = apply_rear_guard(
            pred_type=pred,
            type_probs=probs,
            scene_tags=scene_tags,
            rear_floor=float(rear_floor),
            gap_max=float(gap_max),
            turn_ceiling=float(turn_ceiling),
            lane_cap=float(lane_cap),
        )
        out["pred_type"] = pred2
        out["lane_expert_prob"] = round(lp, 6)
        out["lane_expert_thr"] = round(float(thr), 6)
        out["lane_expert_applied"] = bool(lane_applied)
        out["lane_route_mode"] = route_mode
        out["rear_guard_applied"] = bool(rear_applied)
        out_rows.append(out)
    return out_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply lane expert priority routing then rear-guard.")
    parser.add_argument("--main-pred", required=True, help="Main raw prediction jsonl (with type_probs)")
    parser.add_argument("--lane-prob", required=True, help="Lane expert probability jsonl (video + lane_expert_prob)")
    parser.add_argument("--gt", required=True, help="GT labels jsonl for threshold tuning")
    parser.add_argument("--out-pred", required=True, help="Output prediction jsonl")
    parser.add_argument("--out-report", required=True, help="Output report json")
    parser.add_argument("--lane-thr-grid", default="0.30,0.35,0.40,0.45,0.50,0.55,0.60,0.65")
    parser.add_argument("--lane-recall-floor", type=float, default=-1.0, help="Optional lane recall floor for feasible selection")
    parser.add_argument("--rear-floor", type=float, default=0.30)
    parser.add_argument("--gap-max", type=float, default=0.14)
    parser.add_argument("--turn-ceiling", type=float, default=0.50)
    parser.add_argument("--lane-cap", type=float, default=0.28)
    args = parser.parse_args()

    main_pred_path = Path(args.main_pred).resolve()
    lane_prob_path = Path(args.lane_prob).resolve()
    gt_path = Path(args.gt).resolve()
    out_pred = Path(args.out_pred).resolve()
    out_report = Path(args.out_report).resolve()
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    out_report.parent.mkdir(parents=True, exist_ok=True)

    main_rows = load_jsonl(main_pred_path)
    lane_rows = load_jsonl(lane_prob_path)
    gt_rows = load_jsonl(gt_path)
    thr_grid = parse_grid(args.lane_thr_grid)

    main_map = {normalize_video_key(r.get("video", "")): r for r in main_rows}
    lane_map = {normalize_video_key(r.get("video", "")): safe_float(r.get("lane_expert_prob", 0.0), 0.0) for r in lane_rows}
    gt_map = {
        normalize_video_key(r.get("video", "")): str(r.get("accident_type", "")).strip()
        for r in gt_rows
        if str(r.get("accident_type", "")).strip() in CLASSES
    }
    keys = sorted(set(main_map.keys()) & set(gt_map.keys()))
    if not keys:
        raise RuntimeError("No matched samples between main pred and gt.")

    trials: List[Dict[str, Any]] = []
    best_any: Dict[str, Any] = {}
    best_feasible: Dict[str, Any] = {}
    for thr in thr_grid:
        pred_rows = build_pred_for_threshold(
            main_rows=[main_map[k] for k in keys],
            lane_prob_map=lane_map,
            thr=float(thr),
            rear_floor=float(args.rear_floor),
            gap_max=float(args.gap_max),
            turn_ceiling=float(args.turn_ceiling),
            lane_cap=float(args.lane_cap),
        )
        y_true = [gt_map[k] for k in keys]
        y_pred = [str(r.get("pred_type", "")) for r in pred_rows]
        m = evaluate_rows(y_true, y_pred)
        lane_recall = float(m["per_class"]["lane_change"]["recall"])
        row = {
            "lane_thr": float(thr),
            "accuracy": float(m["accuracy"]),
            "macro_f1": float(m["macro_f1"]),
            "lane_recall": lane_recall,
            "rear_recall": float(m["per_class"]["rear_end"]["recall"]),
            "turn_recall": float(m["per_class"]["turn_conflict"]["recall"]),
            "metrics": m,
            "pred_rows": pred_rows,
        }
        trials.append(row)
        if not best_any or row["macro_f1"] > best_any["macro_f1"]:
            best_any = row
        if args.lane_recall_floor >= 0.0 and lane_recall >= float(args.lane_recall_floor):
            if not best_feasible or row["macro_f1"] > best_feasible["macro_f1"]:
                best_feasible = row

    chosen = best_feasible if best_feasible else best_any
    chosen_pred_rows = chosen["pred_rows"]

    with out_pred.open("w", encoding="utf-8") as f:
        for r in chosen_pred_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "main_pred_in": str(main_pred_path),
        "lane_prob_in": str(lane_prob_path),
        "gt_in": str(gt_path),
        "n_matched": int(len(keys)),
        "lane_thr_grid": [float(x) for x in thr_grid],
        "selection_mode": "best_feasible_by_lane_recall_then_macro_f1" if args.lane_recall_floor >= 0.0 else "best_macro_f1",
        "lane_recall_floor": float(args.lane_recall_floor),
        "rear_guard_cfg": {
            "rear_floor": float(args.rear_floor),
            "gap_max": float(args.gap_max),
            "turn_ceiling": float(args.turn_ceiling),
            "lane_cap": float(args.lane_cap),
        },
        "best_any": {
            "lane_thr": float(best_any["lane_thr"]),
            "accuracy": round(float(best_any["accuracy"]), 6),
            "macro_f1": round(float(best_any["macro_f1"]), 6),
            "lane_recall": round(float(best_any["lane_recall"]), 6),
            "rear_recall": round(float(best_any["rear_recall"]), 6),
            "turn_recall": round(float(best_any["turn_recall"]), 6),
        },
        "best_feasible": None,
        "chosen": {
            "lane_thr": float(chosen["lane_thr"]),
            "accuracy": round(float(chosen["accuracy"]), 6),
            "macro_f1": round(float(chosen["macro_f1"]), 6),
            "lane_recall": round(float(chosen["lane_recall"]), 6),
            "rear_recall": round(float(chosen["rear_recall"]), 6),
            "turn_recall": round(float(chosen["turn_recall"]), 6),
        },
        "trials": [
            {
                "lane_thr": float(x["lane_thr"]),
                "accuracy": round(float(x["accuracy"]), 6),
                "macro_f1": round(float(x["macro_f1"]), 6),
                "lane_recall": round(float(x["lane_recall"]), 6),
                "rear_recall": round(float(x["rear_recall"]), 6),
                "turn_recall": round(float(x["turn_recall"]), 6),
            }
            for x in trials
        ],
        "out_pred": str(out_pred),
    }
    if best_feasible:
        report["best_feasible"] = {
            "lane_thr": float(best_feasible["lane_thr"]),
            "accuracy": round(float(best_feasible["accuracy"]), 6),
            "macro_f1": round(float(best_feasible["macro_f1"]), 6),
            "lane_recall": round(float(best_feasible["lane_recall"]), 6),
            "rear_recall": round(float(best_feasible["rear_recall"]), 6),
            "turn_recall": round(float(best_feasible["turn_recall"]), 6),
        }

    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

