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


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def parse_grid(raw: str) -> List[float]:
    vals = [x.strip() for x in str(raw).split(",") if x.strip()]
    return [float(x) for x in vals]


def metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    per_class: Dict[str, Dict[str, float]] = {}
    f1_sum = 0.0
    for c in CLASSES:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        support = sum(1 for t in y_true if t == c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[c] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "support": int(support),
        }
        f1_sum += f1
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / max(1, len(y_true))
    return {
        "accuracy": float(acc),
        "macro_f1": float(f1_sum / len(CLASSES)),
        "per_class": per_class,
    }


def argmax_type(row: Dict[str, Any]) -> str:
    probs = row.get("type_probs", {}) if isinstance(row.get("type_probs", {}), dict) else {}
    pr = safe_float(probs.get("rear_end", 0.0))
    pl = safe_float(probs.get("lane_change", 0.0))
    pt = safe_float(probs.get("turn_conflict", 0.0))
    return max([("rear_end", pr), ("lane_change", pl), ("turn_conflict", pt)], key=lambda x: x[1])[0]


def tune_pick(
    pred_row: Dict[str, Any],
    scene_tags: List[str],
    rear_floor: float,
    gap_max: float,
    turn_ceiling: float,
    lane_cap: float,
) -> str:
    base_pred = str(pred_row.get("pred_type", "")).strip()
    if base_pred not in CLASSES:
        base_pred = argmax_type(pred_row)
    if base_pred != "turn_conflict":
        return base_pred

    probs = pred_row.get("type_probs", {}) if isinstance(pred_row.get("type_probs", {}), dict) else {}
    pr = safe_float(probs.get("rear_end", 0.0))
    pl = safe_float(probs.get("lane_change", 0.0))
    pt = safe_float(probs.get("turn_conflict", 0.0))
    tags = {str(x).strip() for x in (scene_tags or []) if str(x).strip()}

    # v3.4.3 lightweight rear guard:
    # Only consider flipping turn->rear on non-intersection/non-turning scenes,
    # and only when probabilities are close.
    if "intersection" in tags or "turning_scene" in tags:
        return base_pred
    if pr >= rear_floor and (pt - pr) <= gap_max and pt <= turn_ceiling and pl <= lane_cap:
        return "rear_end"
    return base_pred


def main() -> None:
    parser = argparse.ArgumentParser(description="v3.4.3 rear guard threshold tuning (no retrain).")
    parser.add_argument("--pred", required=True, help="Input OOF pred jsonl")
    parser.add_argument("--gt", required=True, help="Input OOF gt jsonl")
    parser.add_argument("--out-report", required=True, help="Output tuning report json")
    parser.add_argument("--out-pred", required=True, help="Output tuned pred jsonl")
    parser.add_argument("--rear-floor-grid", default="0.30,0.32,0.34,0.36,0.38,0.40,0.42")
    parser.add_argument("--gap-max-grid", default="0.02,0.04,0.06,0.08,0.10,0.12,0.14")
    parser.add_argument("--turn-ceiling-grid", default="0.42,0.45,0.48,0.50,0.52,0.55,0.58,0.60")
    parser.add_argument("--lane-cap-grid", default="0.22,0.25,0.28,0.30,0.32,0.35")
    parser.add_argument("--max-turn-drop", type=float, default=0.03)
    parser.add_argument("--max-lane-drop", type=float, default=0.005)
    parser.add_argument("--rear-weight", type=float, default=0.15, help="Objective bonus on rear recall")
    args = parser.parse_args()

    pred_rows = load_jsonl(Path(args.pred).resolve())
    gt_rows = load_jsonl(Path(args.gt).resolve())

    pred_by_sid: Dict[str, Dict[str, Any]] = {}
    pred_by_video: Dict[str, Dict[str, Any]] = {}
    for r in pred_rows:
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            pred_by_sid[sid] = r
        v = normalize_video_key(r.get("video", ""))
        if v:
            pred_by_video[v] = r

    matched: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for gt in gt_rows:
        gt_type = str(gt.get("accident_type", "")).strip()
        if gt_type not in CLASSES:
            continue
        sid = str(gt.get("sample_id", "")).strip()
        video = normalize_video_key(gt.get("video", ""))
        pred = pred_by_sid.get(sid) if sid else None
        if pred is None and video:
            pred = pred_by_video.get(video)
        if pred is None:
            continue
        matched.append((gt, pred))

    if not matched:
        raise RuntimeError("No matched samples between pred and gt.")

    y_true = [str(gt.get("accident_type", "")).strip() for gt, _ in matched]
    y_base = []
    for gt, pred in matched:
        p = str(pred.get("pred_type", "")).strip()
        y_base.append(p if p in CLASSES else argmax_type(pred))
    base_m = metrics(y_true, y_base)

    rear_grid = parse_grid(args.rear_floor_grid)
    gap_grid = parse_grid(args.gap_max_grid)
    turn_ceiling_grid = parse_grid(args.turn_ceiling_grid)
    lane_cap_grid = parse_grid(args.lane_cap_grid)

    feasible_best: Optional[Dict[str, Any]] = None
    feasible_pred: List[str] = []
    fallback_best: Optional[Dict[str, Any]] = None
    fallback_pred: List[str] = []

    for rear_floor, gap_max, turn_ceiling, lane_cap in itertools.product(
        rear_grid, gap_grid, turn_ceiling_grid, lane_cap_grid
    ):
        y_hat: List[str] = []
        for gt, pred in matched:
            tags = gt.get("scene_tags", [])
            if not isinstance(tags, list):
                tags = []
            y_hat.append(
                tune_pick(
                    pred_row=pred,
                    scene_tags=tags,
                    rear_floor=float(rear_floor),
                    gap_max=float(gap_max),
                    turn_ceiling=float(turn_ceiling),
                    lane_cap=float(lane_cap),
                )
            )
        m = metrics(y_true, y_hat)
        rear_r = float(m["per_class"]["rear_end"]["recall"])
        lane_r = float(m["per_class"]["lane_change"]["recall"])
        turn_r = float(m["per_class"]["turn_conflict"]["recall"])
        score = float(m["macro_f1"]) + (float(args.rear_weight) * rear_r)

        if fallback_best is None or score > float(fallback_best["score"]):
            fallback_best = {
                "score": score,
                "cfg": {
                    "rear_floor": float(rear_floor),
                    "gap_max": float(gap_max),
                    "turn_ceiling": float(turn_ceiling),
                    "lane_cap": float(lane_cap),
                },
                "metrics": m,
            }
            fallback_pred = y_hat

        lane_drop = float(base_m["per_class"]["lane_change"]["recall"]) - lane_r
        turn_drop = float(base_m["per_class"]["turn_conflict"]["recall"]) - turn_r
        feasible = (lane_drop <= float(args.max_lane_drop)) and (turn_drop <= float(args.max_turn_drop))
        if feasible:
            if feasible_best is None or score > float(feasible_best["score"]):
                feasible_best = {
                    "score": score,
                    "cfg": {
                        "rear_floor": float(rear_floor),
                        "gap_max": float(gap_max),
                        "turn_ceiling": float(turn_ceiling),
                        "lane_cap": float(lane_cap),
                    },
                    "metrics": m,
                    "lane_drop": lane_drop,
                    "turn_drop": turn_drop,
                }
                feasible_pred = y_hat

    chosen = feasible_best if feasible_best is not None else fallback_best
    chosen_pred = feasible_pred if feasible_best is not None else fallback_pred
    assert chosen is not None

    # write tuned prediction rows (same order as original pred file)
    tuned_map: Dict[str, str] = {}
    for (gt, pred), new_type in zip(matched, chosen_pred):
        sid = str(gt.get("sample_id", "")).strip()
        key = sid if sid else normalize_video_key(gt.get("video", ""))
        tuned_map[key] = new_type

    out_rows: List[Dict[str, Any]] = []
    for row in pred_rows:
        out = dict(row)
        sid = str(out.get("sample_id", "")).strip()
        video = normalize_video_key(out.get("video", ""))
        key = sid if sid else video
        if key in tuned_map:
            out["pred_type"] = tuned_map[key]
            out["rear_guard_tuned"] = True
            out["rear_guard_version"] = "v3.4.3"
            out["rear_guard_cfg"] = chosen["cfg"]
        out_rows.append(out)

    out_pred = Path(args.out_pred).resolve()
    out_pred.parent.mkdir(parents=True, exist_ok=True)
    with out_pred.open("w", encoding="utf-8") as f:
        for r in out_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    report = {
        "version": "v3.4.3_rear_guard",
        "n_matched": len(matched),
        "objective": "macro_f1 + rear_weight*rear_recall",
        "constraints": {
            "max_turn_drop": float(args.max_turn_drop),
            "max_lane_drop": float(args.max_lane_drop),
            "rear_weight": float(args.rear_weight),
        },
        "base": base_m,
        "chosen_is_feasible": feasible_best is not None,
        "chosen": chosen,
        "delta_vs_base": {
            "accuracy": float(chosen["metrics"]["accuracy"]) - float(base_m["accuracy"]),
            "macro_f1": float(chosen["metrics"]["macro_f1"]) - float(base_m["macro_f1"]),
            "rear_recall": float(chosen["metrics"]["per_class"]["rear_end"]["recall"])
            - float(base_m["per_class"]["rear_end"]["recall"]),
            "lane_recall": float(chosen["metrics"]["per_class"]["lane_change"]["recall"])
            - float(base_m["per_class"]["lane_change"]["recall"]),
            "turn_recall": float(chosen["metrics"]["per_class"]["turn_conflict"]["recall"])
            - float(base_m["per_class"]["turn_conflict"]["recall"]),
        },
        "pred_in": str(Path(args.pred).resolve()),
        "pred_out": str(out_pred),
        "gt_in": str(Path(args.gt).resolve()),
    }

    out_report = Path(args.out_report).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
