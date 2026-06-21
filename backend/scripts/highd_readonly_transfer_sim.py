import argparse
import json
from pathlib import Path
from statistics import mean, median
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


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def normalize_video(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def scene_bucket(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    is_day = "day" in s
    is_night = "night" in s
    is_straight = "straight_road" in s
    is_inter = "intersection" in s
    if is_day and is_straight:
        return "day+straight_road"
    if is_day and is_inter:
        return "day+intersection"
    if is_night and is_straight:
        return "night+straight_road"
    if is_night and is_inter:
        return "night+intersection"
    return "other"


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def add_proxy_scores(pred_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in pred_rows:
        rr = dict(r)
        tp = rr.get("type_probs", {}) or {}
        pr = max(0.0, safe_float(tp.get("rear_end", 0.0)))
        pl = max(0.0, safe_float(tp.get("lane_change", 0.0)))
        z = pr + pl
        if z <= 1e-9:
            lane_score = 0.5
            rear_score = 0.5
        else:
            lane_score = pl / z
            rear_score = pr / z
        rr["lane_expert_score"] = round(float(lane_score), 6)
        rr["rear_expert_score"] = round(float(rear_score), 6)
        rr["lane_rear_margin"] = round(float(lane_score - rear_score), 6)
        rr["highd_transfer_mode"] = "readonly_proxy_from_rear_lane_boundary"
        out.append(rr)
    return out


def build_gt_map(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    m: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        m[normalize_video(r.get("video", ""))] = r
    return m


def matched_rows(gt_rows: List[Dict[str, Any]], pred_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pm = {normalize_video(r.get("video", "")): r for r in pred_rows}
    out: List[Dict[str, Any]] = []
    for g in gt_rows:
        v = normalize_video(g.get("video", ""))
        p = pm.get(v)
        if p is None:
            continue
        out.append({"gt": g, "pred": p, "video": v})
    return out


def avg(vals: List[float]) -> float:
    return float(mean(vals)) if vals else 0.0


def compute_simple_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    y_true = [str(x["gt"].get("accident_type", "")).strip() for x in rows]
    y_pred = [str(x["pred"].get("pred_type", "")).strip() for x in rows]
    n = len(y_true)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0

    per_class: Dict[str, Dict[str, float]] = {}
    f1s: List[float] = []
    recalls: Dict[str, float] = {}
    for c in CLASSES:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        per_class[c] = {
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "support": int(sum(1 for t in y_true if t == c)),
        }
        recalls[c] = float(recall)
        f1s.append(float(f1))
    macro = float(sum(f1s) / len(f1s)) if f1s else 0.0

    impact_abs: List[float] = []
    for r in rows:
        gt_imp = safe_float(r["gt"].get("impact_time", 0.0))
        pd_imp = safe_float(r["pred"].get("pred_impact_time", 0.0))
        impact_abs.append(abs(pd_imp - gt_imp))
    impact_mae = avg(impact_abs)

    return {
        "n": int(n),
        "accuracy": float(acc),
        "macro_f1": float(macro),
        "impact_mae": float(impact_mae),
        "per_class": per_class,
        "rear_recall": float(recalls.get("rear_end", 0.0)),
        "lane_recall": float(recalls.get("lane_change", 0.0)),
        "turn_recall": float(recalls.get("turn_conflict", 0.0)),
    }


def analyze_readonly(rows: List[Dict[str, Any]], rescue_thr: float, steal_thr: float) -> Dict[str, Any]:
    lane_fn_rear = [
        r
        for r in rows
        if str(r["gt"].get("accident_type", "")).strip() == "lane_change"
        and str(r["pred"].get("pred_type", "")).strip() == "rear_end"
    ]
    rear_gt = [r for r in rows if str(r["gt"].get("accident_type", "")).strip() == "rear_end"]

    lf_lane_scores = [safe_float(x["pred"].get("lane_expert_score", 0.0)) for x in lane_fn_rear]
    lf_rear_scores = [safe_float(x["pred"].get("rear_expert_score", 0.0)) for x in lane_fn_rear]
    lf_margin = [safe_float(x["pred"].get("lane_rear_margin", 0.0)) for x in lane_fn_rear]
    rescue = [x for x in lane_fn_rear if safe_float(x["pred"].get("lane_expert_score", 0.0)) >= rescue_thr]

    rear_lane_scores = [safe_float(x["pred"].get("lane_expert_score", 0.0)) for x in rear_gt]
    rear_margin = [safe_float(x["pred"].get("lane_rear_margin", 0.0)) for x in rear_gt]
    steal = [x for x in rear_gt if safe_float(x["pred"].get("lane_expert_score", 0.0)) >= steal_thr]

    bucket_names = [
        "day+straight_road",
        "day+intersection",
        "night+straight_road",
        "night+intersection",
    ]
    bucket_out: Dict[str, Any] = {}
    for b in bucket_names:
        br = [r for r in rows if scene_bucket(r["gt"].get("scene_tags", [])) == b]
        if not br:
            bucket_out[b] = {"n": 0}
            continue
        b_lf = [
            r
            for r in br
            if str(r["gt"].get("accident_type", "")).strip() == "lane_change"
            and str(r["pred"].get("pred_type", "")).strip() == "rear_end"
        ]
        b_rear = [r for r in br if str(r["gt"].get("accident_type", "")).strip() == "rear_end"]
        bucket_out[b] = {
            "n": len(br),
            "lane_fn_rear_n": len(b_lf),
            "rear_gt_n": len(b_rear),
            "lane_score_mean_all": avg([safe_float(x["pred"].get("lane_expert_score", 0.0)) for x in br]),
            "rear_score_mean_all": avg([safe_float(x["pred"].get("rear_expert_score", 0.0)) for x in br]),
            "lane_fn_rear_rescueable_n": sum(
                1 for x in b_lf if safe_float(x["pred"].get("lane_expert_score", 0.0)) >= rescue_thr
            ),
            "rear_potential_steal_n": sum(
                1 for x in b_rear if safe_float(x["pred"].get("lane_expert_score", 0.0)) >= steal_thr
            ),
        }

    return {
        "look1_lane_fn_vs_rear": {
            "lane_fn_rear_n": len(lane_fn_rear),
            "lane_score_mean": avg(lf_lane_scores),
            "rear_score_mean": avg(lf_rear_scores),
            "margin_mean": avg(lf_margin),
            "margin_median": float(median(lf_margin)) if lf_margin else 0.0,
            "rescueable_n": len(rescue),
            "rescueable_ratio": (len(rescue) / len(lane_fn_rear)) if lane_fn_rear else 0.0,
        },
        "look2_rear_stealing_risk": {
            "rear_gt_n": len(rear_gt),
            "lane_score_mean": avg(rear_lane_scores),
            "margin_mean": avg(rear_margin),
            "potential_rear_steal_n": len(steal),
            "potential_rear_steal_ratio": (len(steal) / len(rear_gt)) if rear_gt else 0.0,
        },
        "look3_scene_buckets": bucket_out,
    }


def apply_minimal_boundary_patch(
    pred_rows: List[Dict[str, Any]],
    turn_guard_max: float,
    boundary_gap_max: float,
    lane_score_thr: float,
    margin_thr: float,
    rear_prob_cap: float,
) -> Tuple[List[Dict[str, Any]], int]:
    out: List[Dict[str, Any]] = []
    changed = 0
    for r in pred_rows:
        rr = dict(r)
        pred_type = str(rr.get("pred_type", "")).strip()
        tp = rr.get("type_probs", {}) or {}
        pr = safe_float(tp.get("rear_end", 0.0))
        pl = safe_float(tp.get("lane_change", 0.0))
        pt = safe_float(tp.get("turn_conflict", 0.0))
        lane_score = safe_float(rr.get("lane_expert_score", 0.5))
        rear_score = safe_float(rr.get("rear_expert_score", 0.5))
        margin = lane_score - rear_score
        gap = abs(pr - pl)

        apply = (
            pred_type in {"rear_end", "lane_change"}
            and pt <= turn_guard_max
            and gap <= boundary_gap_max
            and lane_score >= lane_score_thr
            and margin >= margin_thr
            and pr <= rear_prob_cap
        )
        if apply and pred_type != "lane_change":
            rr["pred_type"] = "lane_change"
            rr["readonly_boundary_patch_applied"] = True
            changed += 1
        else:
            rr["readonly_boundary_patch_applied"] = False
        out.append(rr)
    return out, changed


def run_board(
    board_name: str,
    gt_path: Path,
    pred_base_path: Path,
    out_dir: Path,
    cfg: Dict[str, float],
) -> Dict[str, Any]:
    gt_rows = load_jsonl(gt_path)
    pred_rows = load_jsonl(pred_base_path)
    pred_scored = add_proxy_scores(pred_rows)

    matched = matched_rows(gt_rows, pred_scored)
    readonly = analyze_readonly(
        matched,
        rescue_thr=float(cfg["rescue_thr"]),
        steal_thr=float(cfg["steal_thr"]),
    )
    base_m = compute_simple_metrics(matched)

    pred_patch, changed = apply_minimal_boundary_patch(
        pred_scored,
        turn_guard_max=float(cfg["turn_guard_max"]),
        boundary_gap_max=float(cfg["boundary_gap_max"]),
        lane_score_thr=float(cfg["lane_score_thr"]),
        margin_thr=float(cfg["margin_thr"]),
        rear_prob_cap=float(cfg["rear_prob_cap"]),
    )
    matched_patch = matched_rows(gt_rows, pred_patch)
    patch_m = compute_simple_metrics(matched_patch)

    scored_path = out_dir / f"{board_name}.readonly_scored.jsonl"
    patch_path = out_dir / f"{board_name}.readonly_patch.jsonl"
    write_jsonl(scored_path, pred_scored)
    write_jsonl(patch_path, pred_patch)

    return {
        "board": board_name,
        "gt_path": str(gt_path),
        "pred_base_path": str(pred_base_path),
        "pred_scored_path": str(scored_path),
        "pred_patch_path": str(patch_path),
        "matched_n": len(matched),
        "readonly_analysis": readonly,
        "base_metrics": base_m,
        "patch_metrics": patch_m,
        "changed_by_patch": int(changed),
        "delta": {
            "macro_f1": patch_m["macro_f1"] - base_m["macro_f1"],
            "lane_recall": patch_m["lane_recall"] - base_m["lane_recall"],
            "rear_recall": patch_m["rear_recall"] - base_m["rear_recall"],
            "impact_mae": patch_m["impact_mae"] - base_m["impact_mae"],
            "accuracy": patch_m["accuracy"] - base_m["accuracy"],
        },
    }


def aggregate_gate(boards: List[Dict[str, Any]]) -> Dict[str, Any]:
    def mavg(key: str, scope: str = "delta") -> float:
        vals = [float(b[scope][key]) for b in boards]
        return sum(vals) / len(vals) if vals else 0.0

    macro = mavg("macro_f1")
    lane = mavg("lane_recall")
    rear = mavg("rear_recall")
    impact = mavg("impact_mae")

    gates = {
        "macro_f1_ge_0p005": macro >= 0.005,
        "lane_recall_ge_0p05": lane >= 0.05,
        "impact_mae_non_regression": impact <= 1e-9,
        "rear_recall_drop_le_0p02": rear >= -0.02,
    }
    overall = all(gates.values())
    return {
        "mean_delta": {
            "macro_f1": macro,
            "lane_recall": lane,
            "rear_recall": rear,
            "impact_mae": impact,
        },
        "gates": gates,
        "overall_pass": overall,
        "decision": "PASS_TO_MINIMAL_INTEGRATION_CANDIDATE" if overall else "FAIL_STOP_AT_READONLY_SIM",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase-2 readonly transfer simulation on 152+30+24.")
    parser.add_argument("--gt-152", required=True)
    parser.add_argument("--gt-30", required=True)
    parser.add_argument("--gt-24", required=True)
    parser.add_argument("--pred-152", required=True)
    parser.add_argument("--pred-30", required=True)
    parser.add_argument("--pred-24", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rescue-thr", type=float, default=0.56)
    parser.add_argument("--steal-thr", type=float, default=0.60)
    parser.add_argument("--turn-guard-max", type=float, default=0.42)
    parser.add_argument("--boundary-gap-max", type=float, default=0.10)
    parser.add_argument("--lane-score-thr", type=float, default=0.56)
    parser.add_argument("--margin-thr", type=float, default=0.08)
    parser.add_argument("--rear-prob-cap", type=float, default=0.45)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "rescue_thr": float(args.rescue_thr),
        "steal_thr": float(args.steal_thr),
        "turn_guard_max": float(args.turn_guard_max),
        "boundary_gap_max": float(args.boundary_gap_max),
        "lane_score_thr": float(args.lane_score_thr),
        "margin_thr": float(args.margin_thr),
        "rear_prob_cap": float(args.rear_prob_cap),
    }

    boards = []
    boards.append(
        run_board(
            "board152",
            gt_path=Path(args.gt_152).resolve(),
            pred_base_path=Path(args.pred_152).resolve(),
            out_dir=out_dir,
            cfg=cfg,
        )
    )
    boards.append(
        run_board(
            "board30",
            gt_path=Path(args.gt_30).resolve(),
            pred_base_path=Path(args.pred_30).resolve(),
            out_dir=out_dir,
            cfg=cfg,
        )
    )
    boards.append(
        run_board(
            "board24",
            gt_path=Path(args.gt_24).resolve(),
            pred_base_path=Path(args.pred_24).resolve(),
            out_dir=out_dir,
            cfg=cfg,
        )
    )

    gate = aggregate_gate(boards)
    report = {
        "mode": "readonly_simulation",
        "note": "No main model change. highD expert scores are proxy scores from rear/lane boundary probabilities due feature-space mismatch.",
        "config": cfg,
        "boards": boards,
        "aggregate": gate,
    }

    report_path = out_dir / "HIGHD_READONLY_TRANSFER_SIM_REPORT_2026-05-07.json"
    md_path = out_dir / "HIGHD_READONLY_TRANSFER_SIM_REPORT_2026-05-07.md"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# highD Readonly Transfer Simulation (152+30+24)")
    lines.append("")
    lines.append("- mode: readonly_simulation")
    lines.append("- note: no main-model change; proxy scores only")
    lines.append("")
    for b in boards:
        lines.append(f"## {b['board']}")
        lines.append(f"- matched_n: {b['matched_n']}")
        lines.append(f"- changed_by_patch: {b['changed_by_patch']}")
        lines.append(
            f"- delta macro/lane/rear/impact: "
            f"{b['delta']['macro_f1']:+.6f} / {b['delta']['lane_recall']:+.6f} / "
            f"{b['delta']['rear_recall']:+.6f} / {b['delta']['impact_mae']:+.6f}"
        )
        l1 = b["readonly_analysis"]["look1_lane_fn_vs_rear"]
        l2 = b["readonly_analysis"]["look2_rear_stealing_risk"]
        lines.append(
            f"- look1 laneFN->rear: n={l1['lane_fn_rear_n']}, rescueable={l1['rescueable_n']} "
            f"({l1['rescueable_ratio']:.2%})"
        )
        lines.append(
            f"- look2 rear steal risk: n={l2['rear_gt_n']}, potential={l2['potential_rear_steal_n']} "
            f"({l2['potential_rear_steal_ratio']:.2%})"
        )
        lines.append("")
    lines.append("## Aggregate Gate")
    g = gate["mean_delta"]
    lines.append(
        f"- mean delta macro/lane/rear/impact: "
        f"{g['macro_f1']:+.6f} / {g['lane_recall']:+.6f} / {g['rear_recall']:+.6f} / {g['impact_mae']:+.6f}"
    )
    lines.append(f"- overall_pass: {gate['overall_pass']}")
    lines.append(f"- decision: {gate['decision']}")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"report": str(report_path), "summary_md": str(md_path), "aggregate": gate}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
