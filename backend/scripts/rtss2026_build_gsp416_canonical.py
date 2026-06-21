#!/usr/bin/env python3
import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np


LABEL_REAR = "rear_end"
LABEL_LANE = "lane_change"
LABEL_TURN = "turn_conflict"

POLICY_BASE = "BASE_ONLY"
POLICY_DET = "DETERMINISTIC_FUSION"
POLICY_GSP = "GSP416_CANONICAL"


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def read_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def class_recall(gt: List[str], pred: List[str], target: str) -> float:
    idx = [i for i, g in enumerate(gt) if g == target]
    if not idx:
        return float("nan")
    return sum(1 for i in idx if pred[i] == target) / len(idx)


def eval_metrics(rows: List[Dict[str, Any]], pred_key: str, action_key: str) -> Dict[str, float]:
    n = len(rows)
    gt = [str(r.get("gt_type", "")).strip() for r in rows]
    pred = [str(r.get(pred_key, "")).strip() for r in rows]
    act = [str(r.get(action_key, "")).strip() for r in rows]

    rear_idx = [i for i, g in enumerate(gt) if g == LABEL_REAR]
    rear_risk = sum(1 for i in rear_idx if pred[i] != LABEL_REAR) / len(rear_idx) if rear_idx else float("nan")
    auto_error = sum(1 for g, p in zip(gt, pred) if g != p) / n if n else float("nan")
    lane_recall = class_recall(gt, pred, LABEL_LANE)
    turn_recall = class_recall(gt, pred, LABEL_TURN)
    utility = 0.5 * lane_recall + 0.5 * turn_recall if not (math.isnan(lane_recall) or math.isnan(turn_recall)) else float("nan")

    defer_count = sum(1 for a in act if a == "DEFER")
    boost_count = sum(1 for a in act if a == "FUSION_BOOST")
    keep_count = sum(1 for a in act if a == "KEEP_BASELINE")
    fallback_rate = defer_count / n if n else float("nan")
    auto_coverage = 1.0 - fallback_rate if n else float("nan")

    rear_support_auto = sum(1 for i in range(n) if gt[i] == LABEL_REAR and act[i] != "DEFER")
    lane_support_auto = sum(1 for i in range(n) if gt[i] == LABEL_LANE and act[i] != "DEFER")
    turn_support_auto = sum(1 for i in range(n) if gt[i] == LABEL_TURN and act[i] != "DEFER")

    return {
        "N": n,
        "fallback_rate": fallback_rate,
        "defer_count": defer_count,
        "boost_count": boost_count,
        "keep_count": keep_count,
        "auto_coverage": auto_coverage,
        "rear_risk": rear_risk,
        "auto_error": auto_error,
        "lane_recall": lane_recall,
        "turn_recall": turn_recall,
        "utility": utility,
        "rear_support_auto": rear_support_auto,
        "lane_support_auto": lane_support_auto,
        "turn_support_auto": turn_support_auto,
    }


@dataclass
class PolicyParams:
    theta_rear: float
    theta_nonrear: float
    theta_margin: float
    conflict_mode: str
    fallback_rule: str


def conflict_flag_for_mode(
    mode: str,
    baseline_pred: str,
    fusion_pred: str,
    fusion_nonrear_pred: str,
    margin_nonrear_minus_rear: float,
    theta_margin: float,
) -> bool:
    if mode == "A":
        return baseline_pred != fusion_pred
    if mode == "B":
        return baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR
    if mode == "C":
        return (baseline_pred != fusion_pred) or (margin_nonrear_minus_rear < theta_margin)
    if mode == "D":
        return baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}
    if mode == "E":
        return (
            (fusion_nonrear_pred in {LABEL_LANE, LABEL_TURN} and baseline_pred == LABEL_REAR)
            or ((baseline_pred != fusion_pred) and margin_nonrear_minus_rear < theta_margin)
        )
    raise ValueError(f"unknown conflict mode: {mode}")


def decide_row(row: Dict[str, Any], params: PolicyParams) -> Dict[str, Any]:
    baseline_pred = str(row.get("baseline_pred", "")).strip()
    fusion_pred = str(row.get("fusion_pred", "")).strip()
    baseline_score_rear = safe_float(row.get("baseline_score_rear", 0.0))
    fusion_score_rear = safe_float(row.get("fusion_score_rear", 0.0))
    fusion_score_lane = safe_float(row.get("fusion_score_lane", 0.0))
    fusion_score_turn = safe_float(row.get("fusion_score_turn", 0.0))

    fusion_nonrear_score = max(fusion_score_lane, fusion_score_turn)
    fusion_nonrear_pred = LABEL_LANE if fusion_score_lane >= fusion_score_turn else LABEL_TURN
    margin = safe_float(row.get("margin_nonrear_minus_rear", fusion_nonrear_score - fusion_score_rear))

    rear_guard = baseline_pred == LABEL_REAR and baseline_score_rear >= params.theta_rear
    boost_gate = fusion_nonrear_score >= params.theta_nonrear and margin >= params.theta_margin

    conflict = conflict_flag_for_mode(
        params.conflict_mode,
        baseline_pred=baseline_pred,
        fusion_pred=fusion_pred,
        fusion_nonrear_pred=fusion_nonrear_pred,
        margin_nonrear_minus_rear=margin,
        theta_margin=params.theta_margin,
    )
    uncertain_conflict = conflict and ((fusion_nonrear_score < params.theta_nonrear) or (margin < params.theta_margin))

    rear_priority_tension = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR

    if params.fallback_rule == "A":
        defer_condition = uncertain_conflict
        fallback_formula = "defer = uncertain_conflict"
    elif params.fallback_rule == "B":
        defer_condition = conflict and (not boost_gate)
        fallback_formula = "defer = conflict and not boost_gate"
    elif params.fallback_rule == "C":
        defer_condition = rear_priority_tension and (not rear_guard)
        fallback_formula = "defer = rear_priority_tension and not rear_guard"
    elif params.fallback_rule == "D":
        defer_condition = conflict and (not boost_gate) and (not rear_guard)
        fallback_formula = "defer = conflict and not boost_gate and not rear_guard"
    else:
        raise ValueError(f"unknown fallback rule: {params.fallback_rule}")

    if rear_guard:
        action = "KEEP_BASELINE"
        final_pred = baseline_pred
    elif boost_gate:
        action = "FUSION_BOOST"
        final_pred = fusion_pred
    elif defer_condition:
        action = "DEFER"
        final_pred = baseline_pred
    else:
        action = "KEEP_BASELINE"
        final_pred = baseline_pred

    return {
        "action": action,
        "final_pred": final_pred,
        "rear_guard_flag": rear_guard,
        "boost_gate_flag": boost_gate,
        "conflict_flag": conflict,
        "uncertain_conflict_flag": uncertain_conflict,
        "rear_priority_tension_flag": rear_priority_tension,
        "fusion_nonrear_score": fusion_nonrear_score,
        "fusion_nonrear_pred": fusion_nonrear_pred,
        "margin_nonrear_minus_rear": margin,
        "fallback_formula": fallback_formula,
    }


def attach_policy(rows: List[Dict[str, Any]], params: PolicyParams, policy_name: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = decide_row(r, params)
        merged = dict(r)
        merged.update(d)
        merged["policy_name"] = policy_name
        out.append(merged)
    return out


def build_baselines(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    base_rows: List[Dict[str, Any]] = []
    det_rows: List[Dict[str, Any]] = []
    for r in rows:
        rb = dict(r)
        rb["action"] = "KEEP_BASELINE"
        rb["final_pred"] = str(r.get("baseline_pred", "")).strip()
        rb["policy_name"] = POLICY_BASE
        rb["rear_guard_flag"] = False
        rb["boost_gate_flag"] = False
        rb["conflict_flag"] = False
        rb["uncertain_conflict_flag"] = False
        rb["rear_priority_tension_flag"] = False
        rb["fusion_nonrear_score"] = max(safe_float(r.get("fusion_score_lane", 0.0)), safe_float(r.get("fusion_score_turn", 0.0)))
        rb["fusion_nonrear_pred"] = LABEL_LANE if safe_float(r.get("fusion_score_lane", 0.0)) >= safe_float(r.get("fusion_score_turn", 0.0)) else LABEL_TURN
        rb["margin_nonrear_minus_rear"] = safe_float(r.get("margin_nonrear_minus_rear", 0.0))
        base_rows.append(rb)

        rd = dict(r)
        rd["action"] = "FUSION_BOOST"
        rd["final_pred"] = str(r.get("fusion_pred", "")).strip()
        rd["policy_name"] = POLICY_DET
        rd["rear_guard_flag"] = False
        rd["boost_gate_flag"] = True
        rd["conflict_flag"] = str(r.get("baseline_pred", "")).strip() != str(r.get("fusion_pred", "")).strip()
        rd["uncertain_conflict_flag"] = False
        rd["rear_priority_tension_flag"] = str(r.get("baseline_pred", "")).strip() == LABEL_REAR and str(r.get("fusion_pred", "")).strip() != LABEL_REAR
        rd["fusion_nonrear_score"] = max(safe_float(r.get("fusion_score_lane", 0.0)), safe_float(r.get("fusion_score_turn", 0.0)))
        rd["fusion_nonrear_pred"] = LABEL_LANE if safe_float(r.get("fusion_score_lane", 0.0)) >= safe_float(r.get("fusion_score_turn", 0.0)) else LABEL_TURN
        rd["margin_nonrear_minus_rear"] = safe_float(r.get("margin_nonrear_minus_rear", 0.0))
        det_rows.append(rd)

    return base_rows, det_rows


def sweep_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    theta_rear_grid = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    theta_nonrear_grid = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98]
    theta_margin_grid = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6]
    conflict_modes = ["A", "B", "C", "D", "E"]
    fallback_rules = ["A", "B", "C", "D"]

    candidates: List[Dict[str, Any]] = []
    cid = 0
    for tr in theta_rear_grid:
        for tn in theta_nonrear_grid:
            for tm in theta_margin_grid:
                for cm in conflict_modes:
                    for fr in fallback_rules:
                        cid += 1
                        params = PolicyParams(
                            theta_rear=tr,
                            theta_nonrear=tn,
                            theta_margin=tm,
                            conflict_mode=cm,
                            fallback_rule=fr,
                        )
                        pr = attach_policy(rows, params, policy_name=f"GSP416_CANDIDATE_{cid:05d}")
                        for r in pr:
                            r["pred"] = r["final_pred"]
                        m = eval_metrics(pr, pred_key="final_pred", action_key="action")

                        rear_guard_formula = "baseline_pred==rear_end and baseline_score_rear>=theta_rear"
                        boost_gate_formula = "max(fusion_score_lane,fusion_score_turn)>=theta_nonrear and margin_nonrear_minus_rear>=theta_margin"
                        if cm == "A":
                            conflict_formula = "baseline_pred != fusion_pred"
                        elif cm == "B":
                            conflict_formula = "baseline_pred==rear_end and fusion_pred!=rear_end"
                        elif cm == "C":
                            conflict_formula = "baseline_pred!=fusion_pred OR margin_nonrear_minus_rear<theta_margin"
                        elif cm == "D":
                            conflict_formula = "baseline_pred==rear_end and fusion_pred in {lane_change,turn_conflict}"
                        else:
                            conflict_formula = "fusion_nonrear_pred nonrear with rear-priority tension or low-margin disagreement"

                        candidates.append(
                            {
                                "candidate_id": f"C{cid:05d}",
                                "policy_name": f"GSP416_CANDIDATE_{cid:05d}",
                                "theta_rear": tr,
                                "theta_nonrear": tn,
                                "theta_margin": tm,
                                "conflict_mode": cm,
                                "fallback_rule": fr,
                                "rear_guard_formula": rear_guard_formula,
                                "boost_gate_formula": boost_gate_formula,
                                "conflict_formula": conflict_formula,
                                "fallback_formula": pr[0]["fallback_formula"] if pr else "",
                                **m,
                            }
                        )
    return candidates


def select_point(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    # Fixed contract constants from prompt.
    det_rear_risk = 0.2000
    det_auto_error = 0.6563
    base_utility = 0.0571

    feasible = [
        c
        for c in candidates
        if c["rear_risk"] < det_rear_risk
        and c["utility"] > base_utility
        and c["auto_error"] <= det_auto_error
    ]

    fallback_cap = None
    for cap in [0.05, 0.10, 0.20]:
        sub = [c for c in feasible if c["fallback_rate"] <= cap]
        if sub:
            fallback_cap = cap
            feasible = sub
            break

    if fallback_cap is None:
        return [], {}, "NO_FEASIBLE_POINT_UNDER_FALLBACK_CAP_0p20"

    feasible_sorted = sorted(
        feasible,
        key=lambda c: (
            c["fallback_rate"],
            -c["utility"],
            c["rear_risk"],
            c["auto_error"],
            -c["auto_coverage"],
        ),
    )
    return feasible_sorted, feasible_sorted[0], f"FALLBACK_CAP_{fallback_cap:.2f}"


def to_trace_rows(policy_rows: List[Dict[str, Any]], policy_name: str, provenance: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in policy_rows:
        gt = str(r.get("gt_type", "")).strip()
        final_pred = str(r.get("final_pred", "")).strip()
        action = str(r.get("action", "")).strip()
        rr = {
            "sample_id": r.get("sample_id", ""),
            "case_id": r.get("case_id", ""),
            "board_id": r.get("board_id", ""),
            "bucket_id": r.get("bucket_id", ""),
            "source_id": r.get("source_id", ""),
            "gt_type": gt,
            "baseline_pred": r.get("baseline_pred", ""),
            "fusion_pred": r.get("fusion_pred", ""),
            "policy_name": policy_name,
            "action": action,
            "final_pred": final_pred,
            "is_deferred": action == "DEFER",
            "is_auto": action != "DEFER",
            "is_rear_gt": gt == LABEL_REAR,
            "is_lane_gt": gt == LABEL_LANE,
            "is_turn_gt": gt == LABEL_TURN,
            "is_rear_miss": (gt == LABEL_REAR and final_pred != LABEL_REAR),
            "is_wrong_auto": (action != "DEFER" and final_pred != gt),
            "baseline_correct": str(r.get("baseline_pred", "")).strip() == gt,
            "fusion_correct": str(r.get("fusion_pred", "")).strip() == gt,
            "final_correct": final_pred == gt,
            "rear_guard_flag": bool(r.get("rear_guard_flag", False)),
            "boost_gate_flag": bool(r.get("boost_gate_flag", False)),
            "conflict_flag": bool(r.get("conflict_flag", False)),
            "uncertain_conflict_flag": bool(r.get("uncertain_conflict_flag", False)),
            "baseline_score_rear": safe_float(r.get("baseline_score_rear", 0.0)),
            "fusion_score_rear": safe_float(r.get("fusion_score_rear", 0.0)),
            "fusion_score_lane": safe_float(r.get("fusion_score_lane", 0.0)),
            "fusion_score_turn": safe_float(r.get("fusion_score_turn", 0.0)),
            "fusion_score_nonrear": safe_float(r.get("fusion_score_nonrear", 0.0)),
            "fusion_nonrear_score": safe_float(r.get("fusion_nonrear_score", 0.0)),
            "margin_nonrear_minus_rear": safe_float(r.get("margin_nonrear_minus_rear", 0.0)),
            "provenance": provenance,
        }
        out.append(rr)
    return out


def queue_simulation(
    actions: List[str],
    arrival_rate: float,
    service_rate: float,
    duration_sec: int,
) -> Dict[str, Any]:
    queue = 0
    seq_idx = 0
    q_hist: List[int] = []
    defer_count = 0
    total_samples = 0

    for t in range(duration_sec):
        arrivals = int(math.floor((t + 1) * arrival_rate) - math.floor(t * arrival_rate))
        services = int(math.floor((t + 1) * service_rate) - math.floor(t * service_rate))

        for _ in range(arrivals):
            a = actions[seq_idx % len(actions)]
            seq_idx += 1
            total_samples += 1
            if a == "DEFER":
                queue += 1
                defer_count += 1

        serve = min(queue, services)
        queue -= serve
        q_hist.append(queue)

    defer_rate = defer_count / total_samples if total_samples else 0.0
    effective = arrival_rate * defer_rate
    if effective > service_rate * 1.05:
        stability = "UNSTABLE"
    elif effective >= service_rate * 0.95:
        stability = "BORDERLINE"
    else:
        stability = "STABLE"

    q_arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    return {
        "arrival_rate": arrival_rate,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total_samples,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "effective_defer_arrival_rate": effective,
        "max_queue_length": int(np.max(q_arr)),
        "mean_queue_length": float(np.mean(q_arr)),
        "p95_queue_length": float(np.quantile(q_arr, 0.95, method="linear")),
        "p99_queue_length": float(np.quantile(q_arr, 0.99, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": stability,
    }


def arrival_rate_for_pattern(t: int, pattern: str) -> float:
    if pattern == "Constant":
        return 10.0
    if pattern == "Periodic burst":
        return 50.0 if (t % 30) < 5 else 10.0
    if pattern == "Heavy burst":
        return 100.0 if (t % 60) < 10 else 10.0
    raise ValueError(f"unknown pattern {pattern}")


def burst_simulation(
    actions: List[str],
    pattern: str,
    service_rate: float,
    duration_sec: int,
) -> Dict[str, Any]:
    queue = 0
    seq_idx = 0
    q_hist: List[int] = []
    defer_count = 0
    total_samples = 0

    for t in range(duration_sec):
        lam = arrival_rate_for_pattern(t, pattern)
        arrivals = int(math.floor((t + 1) * lam) - math.floor(t * lam))
        services = int(math.floor((t + 1) * service_rate) - math.floor(t * service_rate))

        for _ in range(arrivals):
            a = actions[seq_idx % len(actions)]
            seq_idx += 1
            total_samples += 1
            if a == "DEFER":
                queue += 1
                defer_count += 1

        queue -= min(queue, services)
        q_hist.append(queue)

    q_arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    defer_rate = defer_count / total_samples if total_samples else 0.0

    # Recovery check after burst windows.
    stable = (q_arr[-1] <= np.quantile(q_arr, 0.5, method="linear")) if len(q_arr) else True
    if stable and np.max(q_arr) <= 5:
        stability = "STABLE"
    elif stable:
        stability = "BORDERLINE"
    else:
        stability = "UNSTABLE"

    return {
        "pattern": pattern,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total_samples,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "max_queue_length": int(np.max(q_arr)),
        "mean_queue_length": float(np.mean(q_arr)),
        "p95_queue_length": float(np.quantile(q_arr, 0.95, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": stability,
    }


def bootstrap_metrics(trace_rows: List[Dict[str, Any]], B: int, seed: int) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    rng = np.random.default_rng(seed)
    n = len(trace_rows)
    gt = np.array([str(r.get("gt_type", "")).strip() for r in trace_rows], dtype=object)
    pr = np.array([str(r.get("final_pred", "")).strip() for r in trace_rows], dtype=object)
    ac = np.array([str(r.get("action", "")).strip() for r in trace_rows], dtype=object)

    raw: List[Dict[str, float]] = []
    for _ in range(B):
        idx = rng.integers(0, n, size=n)
        g = gt[idx].tolist()
        p = pr[idx].tolist()
        a = ac[idx].tolist()
        rows = [{"gt_type": gg, "final_pred": pp, "action": aa} for gg, pp, aa in zip(g, p, a)]
        m = eval_metrics(rows, pred_key="final_pred", action_key="action")
        raw.append(
            {
                "fallback_rate": m["fallback_rate"],
                "rear_risk": m["rear_risk"],
                "auto_error": m["auto_error"],
                "utility": m["utility"],
            }
        )

    arr_fb = np.array([r["fallback_rate"] for r in raw], dtype=float)
    arr_rr = np.array([r["rear_risk"] for r in raw], dtype=float)
    arr_ae = np.array([r["auto_error"] for r in raw], dtype=float)
    arr_ut = np.array([r["utility"] for r in raw], dtype=float)

    summary = {
        "fallback_mean": float(np.mean(arr_fb)),
        "fallback_median": float(np.median(arr_fb)),
        "fallback_p05": float(np.quantile(arr_fb, 0.05, method="linear")),
        "fallback_p95": float(np.quantile(arr_fb, 0.95, method="linear")),
        "rear_risk_mean": float(np.mean(arr_rr)),
        "rear_risk_median": float(np.median(arr_rr)),
        "rear_risk_p05": float(np.quantile(arr_rr, 0.05, method="linear")),
        "rear_risk_p95": float(np.quantile(arr_rr, 0.95, method="linear")),
        "auto_error_mean": float(np.mean(arr_ae)),
        "auto_error_median": float(np.median(arr_ae)),
        "utility_mean": float(np.mean(arr_ut)),
        "utility_median": float(np.median(arr_ut)),
        "utility_p05": float(np.quantile(arr_ut, 0.05, method="linear")),
        "utility_p95": float(np.quantile(arr_ut, 0.95, method="linear")),
    }
    return raw, summary


def lobo_by_group(trace_rows: List[Dict[str, Any]], group_field: str) -> List[Dict[str, Any]]:
    units = sorted({str(r.get(group_field, "")).strip() for r in trace_rows if str(r.get(group_field, "")).strip()})
    out: List[Dict[str, Any]] = []
    for u in units:
        sub = [r for r in trace_rows if str(r.get(group_field, "")).strip() != u]
        if not sub:
            continue
        m = eval_metrics(sub, pred_key="final_pred", action_key="action")
        out.append(
            {
                "group_field": group_field,
                "left_out_unit": u,
                "N_remaining": len(sub),
                **m,
            }
        )
    return out


def bucket_summary(trace_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets = sorted({str(r.get("bucket_id", "")).strip() for r in trace_rows if str(r.get("bucket_id", "")).strip()})
    rows: List[Dict[str, Any]] = []
    for b in buckets:
        sub = [r for r in trace_rows if str(r.get("bucket_id", "")).strip() == b]
        m = eval_metrics(sub, pred_key="final_pred", action_key="action")
        rows.append({"bucket_id": b, **m})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GSP416 canonical point from reconstructed 416 base table.")
    parser.add_argument("--input", required=True, help="canonical_416_base_table.csv")
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--bootstrap_B", type=int, default=5000)
    parser.add_argument("--duration_sec", type=int, default=300)
    args = parser.parse_args()

    inp = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    base_rows_raw = read_csv(inp)
    base_rows, det_rows = build_baselines(base_rows_raw)

    # Anchors
    m_base = eval_metrics(base_rows, pred_key="final_pred", action_key="action")
    m_det = eval_metrics(det_rows, pred_key="final_pred", action_key="action")

    # Sweep and select
    candidates = sweep_candidates(base_rows_raw)
    cand_csv = out_dir / "01_gsp416_sweep_candidates.csv"
    write_csv(
        cand_csv,
        candidates,
        [
            "candidate_id",
            "policy_name",
            "theta_rear",
            "theta_nonrear",
            "theta_margin",
            "conflict_mode",
            "fallback_rule",
            "rear_guard_formula",
            "boost_gate_formula",
            "conflict_formula",
            "fallback_formula",
            "N",
            "fallback_rate",
            "defer_count",
            "boost_count",
            "keep_count",
            "auto_coverage",
            "rear_risk",
            "auto_error",
            "lane_recall",
            "turn_recall",
            "utility",
            "rear_support_auto",
            "lane_support_auto",
            "turn_support_auto",
        ],
    )

    feasible_sorted, selected, selection_stage = select_point(candidates)
    feas_csv = out_dir / "02_gsp416_feasible_points.csv"
    if feasible_sorted:
        write_csv(
            feas_csv,
            feasible_sorted,
            [
                "candidate_id",
                "policy_name",
                "theta_rear",
                "theta_nonrear",
                "theta_margin",
                "conflict_mode",
                "fallback_rule",
                "rear_guard_formula",
                "boost_gate_formula",
                "conflict_formula",
                "fallback_formula",
                "N",
                "fallback_rate",
                "defer_count",
                "boost_count",
                "keep_count",
                "auto_coverage",
                "rear_risk",
                "auto_error",
                "lane_recall",
                "turn_recall",
                "utility",
                "rear_support_auto",
                "lane_support_auto",
                "turn_support_auto",
            ],
        )
    else:
        write_csv(
            feas_csv,
            [],
            [
                "candidate_id",
                "policy_name",
                "theta_rear",
                "theta_nonrear",
                "theta_margin",
                "conflict_mode",
                "fallback_rule",
                "rear_guard_formula",
                "boost_gate_formula",
                "conflict_formula",
                "fallback_formula",
                "N",
                "fallback_rate",
                "defer_count",
                "boost_count",
                "keep_count",
                "auto_coverage",
                "rear_risk",
                "auto_error",
                "lane_recall",
                "turn_recall",
                "utility",
                "rear_support_auto",
                "lane_support_auto",
                "turn_support_auto",
            ],
        )

    sel_md = out_dir / "03_gsp416_selected_point.md"
    if not selected:
        sel_md.write_text(
            "\n".join(
                [
                    "# GSP416 Selected Point",
                    "",
                    "- No feasible point under fallback cap <= 0.20.",
                    f"- selection_stage: {selection_stage}",
                ]
            ),
            encoding="utf-8",
        )
        return

    params = PolicyParams(
        theta_rear=float(selected["theta_rear"]),
        theta_nonrear=float(selected["theta_nonrear"]),
        theta_margin=float(selected["theta_margin"]),
        conflict_mode=str(selected["conflict_mode"]),
        fallback_rule=str(selected["fallback_rule"]),
    )
    gsp_rows = attach_policy(base_rows_raw, params, policy_name=POLICY_GSP)
    gsp_trace = to_trace_rows(
        gsp_rows,
        policy_name=POLICY_GSP,
        provenance="regenerated_from_reconstructed_416_scores_and_archived_selection_rule",
    )

    trace_csv = out_dir / "GSP416_CANONICAL_action_trace.csv"
    trace_fields = [
        "sample_id",
        "case_id",
        "board_id",
        "bucket_id",
        "source_id",
        "gt_type",
        "baseline_pred",
        "fusion_pred",
        "policy_name",
        "action",
        "final_pred",
        "is_deferred",
        "is_auto",
        "is_rear_gt",
        "is_lane_gt",
        "is_turn_gt",
        "is_rear_miss",
        "is_wrong_auto",
        "baseline_correct",
        "fusion_correct",
        "final_correct",
        "rear_guard_flag",
        "boost_gate_flag",
        "conflict_flag",
        "uncertain_conflict_flag",
        "baseline_score_rear",
        "fusion_score_rear",
        "fusion_score_lane",
        "fusion_score_turn",
        "fusion_score_nonrear",
        "fusion_nonrear_score",
        "margin_nonrear_minus_rear",
        "provenance",
    ]
    write_csv(trace_csv, gsp_trace, trace_fields)

    # Selected point explanation
    sel_lines = [
        "# GSP416 Selected Point",
        "",
        f"- policy_name: {POLICY_GSP}",
        f"- selected candidate: {selected['candidate_id']}",
        f"- selection_stage: {selection_stage}",
        "",
        "## Parameters",
        f"- theta_rear: {params.theta_rear}",
        f"- theta_nonrear: {params.theta_nonrear}",
        f"- theta_margin: {params.theta_margin}",
        f"- conflict_mode: {params.conflict_mode}",
        f"- fallback_rule: {params.fallback_rule}",
        "",
        "## Predicate Skeleton",
        "- rear_guard: baseline_pred==rear_end and baseline_score_rear>=theta_rear",
        "- boost_gate: max(fusion_score_lane,fusion_score_turn)>=theta_nonrear and margin_nonrear_minus_rear>=theta_margin",
        "- routing: rear_guard->KEEP, boost_gate->FUSION_BOOST, defer_rule->DEFER, else KEEP",
        "",
        "## Selected Metrics",
        f"- fallback_rate: {selected['fallback_rate']:.6f}",
        f"- defer_count / boost_count / keep_count: {selected['defer_count']} / {selected['boost_count']} / {selected['keep_count']}",
        f"- rear_risk: {selected['rear_risk']:.6f}",
        f"- auto_error: {selected['auto_error']:.6f}",
        f"- utility: {selected['utility']:.6f}",
        f"- auto_coverage: {selected['auto_coverage']:.6f}",
        "",
        "## Contract Checks",
        f"- rear_risk < 0.2000: {selected['rear_risk'] < 0.2}",
        f"- utility > 0.0571: {selected['utility'] > 0.0571}",
        f"- auto_error <= 0.6563: {selected['auto_error'] <= 0.6563}",
    ]
    sel_md.write_text("\n".join(sel_lines), encoding="utf-8")

    # Policy file
    policy_py = out_dir / "GSP416_CANONICAL_policy.py"
    policy_py.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                '"""GSP416_CANONICAL policy (fully reproducible, non-TS3)."""',
                "",
                "LABEL_REAR = 'rear_end'",
                "LABEL_LANE = 'lane_change'",
                "LABEL_TURN = 'turn_conflict'",
                "",
                f"THETA_REAR = {params.theta_rear}",
                f"THETA_NONREAR = {params.theta_nonrear}",
                f"THETA_MARGIN = {params.theta_margin}",
                f"CONFLICT_MODE = '{params.conflict_mode}'",
                f"FALLBACK_RULE = '{params.fallback_rule}'",
                "",
                "def decide(row):",
                "    baseline_pred = str(row['baseline_pred']).strip()",
                "    fusion_pred = str(row['fusion_pred']).strip()",
                "    b_rear = float(row['baseline_score_rear'])",
                "    f_rear = float(row['fusion_score_rear'])",
                "    f_lane = float(row['fusion_score_lane'])",
                "    f_turn = float(row['fusion_score_turn'])",
                "    f_nonrear = max(f_lane, f_turn)",
                "    margin = float(row.get('margin_nonrear_minus_rear', f_nonrear - f_rear))",
                "    f_nonrear_pred = LABEL_LANE if f_lane >= f_turn else LABEL_TURN",
                "",
                "    rear_guard = baseline_pred == LABEL_REAR and b_rear >= THETA_REAR",
                "    boost_gate = f_nonrear >= THETA_NONREAR and margin >= THETA_MARGIN",
                "",
                "    if CONFLICT_MODE == 'A':",
                "        conflict = baseline_pred != fusion_pred",
                "    elif CONFLICT_MODE == 'B':",
                "        conflict = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR",
                "    elif CONFLICT_MODE == 'C':",
                "        conflict = (baseline_pred != fusion_pred) or (margin < THETA_MARGIN)",
                "    elif CONFLICT_MODE == 'D':",
                "        conflict = baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}",
                "    else:",
                "        conflict = (f_nonrear_pred in {LABEL_LANE, LABEL_TURN} and baseline_pred == LABEL_REAR) or ((baseline_pred != fusion_pred) and margin < THETA_MARGIN)",
                "",
                "    uncertain_conflict = conflict and ((f_nonrear < THETA_NONREAR) or (margin < THETA_MARGIN))",
                "    rear_tension = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR",
                "",
                "    if FALLBACK_RULE == 'A':",
                "        defer = uncertain_conflict",
                "    elif FALLBACK_RULE == 'B':",
                "        defer = conflict and (not boost_gate)",
                "    elif FALLBACK_RULE == 'C':",
                "        defer = rear_tension and (not rear_guard)",
                "    else:",
                "        defer = conflict and (not boost_gate) and (not rear_guard)",
                "",
                "    if rear_guard:",
                "        return 'KEEP_BASELINE', baseline_pred",
                "    if boost_gate:",
                "        return 'FUSION_BOOST', fusion_pred",
                "    if defer:",
                "        return 'DEFER', baseline_pred",
                "    return 'KEEP_BASELINE', baseline_pred",
                "",
            ]
        ),
        encoding="utf-8",
    )

    # Validation CSV
    m_gsp = eval_metrics(gsp_rows, pred_key="final_pred", action_key="action")
    val_rows = [
        {
            "policy_name": POLICY_BASE,
            "rear_risk": m_base["rear_risk"],
            "auto_error": m_base["auto_error"],
            "utility": m_base["utility"],
            "fallback_rate": m_base["fallback_rate"],
            "defer_count": m_base["defer_count"],
            "boost_count": m_base["boost_count"],
            "keep_count": m_base["keep_count"],
            "contract_rear_lt_0p2": m_base["rear_risk"] < 0.2,
            "contract_utility_gt_0p0571": m_base["utility"] > 0.0571,
            "contract_auto_err_le_0p6563": m_base["auto_error"] <= 0.6563,
        },
        {
            "policy_name": POLICY_DET,
            "rear_risk": m_det["rear_risk"],
            "auto_error": m_det["auto_error"],
            "utility": m_det["utility"],
            "fallback_rate": m_det["fallback_rate"],
            "defer_count": m_det["defer_count"],
            "boost_count": m_det["boost_count"],
            "keep_count": m_det["keep_count"],
            "contract_rear_lt_0p2": m_det["rear_risk"] < 0.2,
            "contract_utility_gt_0p0571": m_det["utility"] > 0.0571,
            "contract_auto_err_le_0p6563": m_det["auto_error"] <= 0.6563,
        },
        {
            "policy_name": POLICY_GSP,
            "rear_risk": m_gsp["rear_risk"],
            "auto_error": m_gsp["auto_error"],
            "utility": m_gsp["utility"],
            "fallback_rate": m_gsp["fallback_rate"],
            "defer_count": m_gsp["defer_count"],
            "boost_count": m_gsp["boost_count"],
            "keep_count": m_gsp["keep_count"],
            "contract_rear_lt_0p2": m_gsp["rear_risk"] < 0.2,
            "contract_utility_gt_0p0571": m_gsp["utility"] > 0.0571,
            "contract_auto_err_le_0p6563": m_gsp["auto_error"] <= 0.6563,
        },
    ]
    write_csv(
        out_dir / "GSP416_CANONICAL_metrics_validation.csv",
        val_rows,
        [
            "policy_name",
            "rear_risk",
            "auto_error",
            "utility",
            "fallback_rate",
            "defer_count",
            "boost_count",
            "keep_count",
            "contract_rear_lt_0p2",
            "contract_utility_gt_0p0571",
            "contract_auto_err_le_0p6563",
        ],
    )

    # Repro command
    repro = out_dir / "GSP416_CANONICAL_repro_command.txt"
    repro.write_text(
        "python backend/scripts/rtss2026_build_gsp416_canonical.py "
        f"--input \"{inp}\" "
        f"--output_dir \"{out_dir}\" "
        f"--seed {args.seed} --bootstrap_B {args.bootstrap_B} --duration_sec {args.duration_sec}\n",
        encoding="utf-8",
    )

    prov = out_dir / "GSP416_CANONICAL_provenance.md"
    prov.write_text(
        "\n".join(
            [
                "# GSP416_CANONICAL Provenance",
                "",
                "- provenance: regenerated_from_reconstructed_416_scores_and_archived_selection_rule",
                f"- input_base_table: `{inp}`",
                "- old TS3 status: original TS3 locked policy is not recoverable from current workspace.",
                "- this point is newly selected via fixed sweep + deterministic selection rule.",
            ]
        ),
        encoding="utf-8",
    )

    # Queue stress
    actions_gsp = [str(r["action"]) for r in gsp_rows]
    actions_base = [str(r["action"]) for r in base_rows]
    actions_det = [str(r["action"]) for r in det_rows]

    queue_rows: List[Dict[str, Any]] = []
    for policy_name, actions in [
        (POLICY_GSP, actions_gsp),
        (POLICY_BASE, actions_base),
        (POLICY_DET, actions_det),
    ]:
        for lam in [1, 5, 10, 20, 30, 50, 100]:
            for mu in [0.1, 0.5, 1, 2, 5, 10]:
                r = queue_simulation(actions, float(lam), float(mu), duration_sec=args.duration_sec)
                queue_rows.append({"policy_name": policy_name, **r})

    write_csv(
        out_dir / "04_gsp416_queue_stress_raw.csv",
        queue_rows,
        [
            "policy_name",
            "arrival_rate",
            "fallback_service_rate",
            "duration_sec",
            "total_samples",
            "defer_count",
            "defer_rate",
            "effective_defer_arrival_rate",
            "max_queue_length",
            "mean_queue_length",
            "p95_queue_length",
            "p99_queue_length",
            "queue_final_length",
            "stability_flag",
        ],
    )

    queue_gsp = [r for r in queue_rows if r["policy_name"] == POLICY_GSP]
    stable_n = sum(1 for r in queue_gsp if r["stability_flag"] == "STABLE")
    border_n = sum(1 for r in queue_gsp if r["stability_flag"] == "BORDERLINE")
    unstable_n = sum(1 for r in queue_gsp if r["stability_flag"] == "UNSTABLE")
    (out_dir / "04_gsp416_queue_stress_summary.md").write_text(
        "\n".join(
            [
                "# 04 GSP416 Queue Stress Summary",
                "",
                "## Purpose",
                "- Evaluate fallback-capacity feasibility under lambda/mu stress for GSP416 canonical routing.",
                "",
                "## Input",
                f"- action trace: `{trace_csv}`",
                "",
                "## Result Summary (GSP416_CANONICAL)",
                f"- tested settings: {len(queue_gsp)}",
                f"- stable / borderline / unstable: {stable_n} / {border_n} / {unstable_n}",
                f"- mean defer_rate across settings: {float(np.mean([r['defer_rate'] for r in queue_gsp])):.6f}",
                "",
                "## Limitation",
                "- queue simulation is deterministic arrival/service replay, not platform-certified real deployment queue telemetry.",
            ]
        ),
        encoding="utf-8",
    )

    # Burst stress
    burst_rows: List[Dict[str, Any]] = []
    for pattern in ["Constant", "Periodic burst", "Heavy burst"]:
        for mu in [0.5, 1, 2, 5]:
            r = burst_simulation(actions_gsp, pattern=pattern, service_rate=float(mu), duration_sec=args.duration_sec)
            burst_rows.append({"policy_name": POLICY_GSP, **r})

    write_csv(
        out_dir / "05_gsp416_burst_raw.csv",
        burst_rows,
        [
            "policy_name",
            "pattern",
            "fallback_service_rate",
            "duration_sec",
            "total_samples",
            "defer_count",
            "defer_rate",
            "max_queue_length",
            "mean_queue_length",
            "p95_queue_length",
            "queue_final_length",
            "stability_flag",
        ],
    )

    (out_dir / "05_gsp416_burst_summary.md").write_text(
        "\n".join(
            [
                "# 05 GSP416 Burst Summary",
                "",
                "## Purpose",
                "- Evaluate fallback queue behavior under bursty arrivals.",
                "",
                "## Input",
                f"- action trace: `{trace_csv}`",
                "",
                "## Result Summary",
                f"- tested settings: {len(burst_rows)}",
                f"- unstable settings: {sum(1 for r in burst_rows if r['stability_flag'] == 'UNSTABLE')}",
                f"- max observed queue: {max(r['max_queue_length'] for r in burst_rows)}",
                "",
                "## Limitation",
                "- burst shape is synthetic pattern replay; does not claim universal deployment burst envelope.",
            ]
        ),
        encoding="utf-8",
    )

    # Bootstrap + LOBO
    bs_raw, bs_summary = bootstrap_metrics(gsp_trace, B=args.bootstrap_B, seed=args.seed)
    bs_rows = []
    for i, r in enumerate(bs_raw, start=1):
        bs_rows.append({"bootstrap_id": i, **r})
    write_csv(
        out_dir / "06_gsp416_bootstrap_raw.csv",
        bs_rows,
        ["bootstrap_id", "fallback_rate", "rear_risk", "auto_error", "utility"],
    )
    write_csv(
        out_dir / "06_gsp416_bootstrap_summary.csv",
        [bs_summary],
        list(bs_summary.keys()),
    )

    lobo_board_rows = lobo_by_group(gsp_trace, "board_id")
    write_csv(
        out_dir / "06_gsp416_lobo_board.csv",
        lobo_board_rows,
        [
            "group_field",
            "left_out_unit",
            "N_remaining",
            "N",
            "fallback_rate",
            "defer_count",
            "boost_count",
            "keep_count",
            "auto_coverage",
            "rear_risk",
            "auto_error",
            "lane_recall",
            "turn_recall",
            "utility",
            "rear_support_auto",
            "lane_support_auto",
            "turn_support_auto",
        ],
    )

    bucket_rows = bucket_summary(gsp_trace)
    write_csv(
        out_dir / "06_gsp416_bucket_summary.csv",
        bucket_rows,
        [
            "bucket_id",
            "N",
            "fallback_rate",
            "defer_count",
            "boost_count",
            "keep_count",
            "auto_coverage",
            "rear_risk",
            "auto_error",
            "lane_recall",
            "turn_recall",
            "utility",
            "rear_support_auto",
            "lane_support_auto",
            "turn_support_auto",
        ],
    )

    (out_dir / "06_gsp416_bootstrap_lobo_summary.md").write_text(
        "\n".join(
            [
                "# 06 GSP416 Bootstrap and LOBO Summary",
                "",
                "## Purpose",
                "- Assess stability on reconstructed 416 via bootstrap and leave-one-board-out.",
                "",
                "## Input",
                f"- action trace: `{trace_csv}`",
                f"- bootstrap_B: {args.bootstrap_B}",
                "",
                "## Bootstrap Summary",
                f"- fallback mean/p05/p95: {bs_summary['fallback_mean']:.6f} / {bs_summary['fallback_p05']:.6f} / {bs_summary['fallback_p95']:.6f}",
                f"- rear_risk mean/p05/p95: {bs_summary['rear_risk_mean']:.6f} / {bs_summary['rear_risk_p05']:.6f} / {bs_summary['rear_risk_p95']:.6f}",
                f"- utility mean/p05/p95: {bs_summary['utility_mean']:.6f} / {bs_summary['utility_p05']:.6f} / {bs_summary['utility_p95']:.6f}",
                "",
                "## LOBO by board_id",
                f"- number of leave-one-board-out runs: {len(lobo_board_rows)}",
                f"- board ids observed: {sorted({str(r.get('board_id','')).strip() for r in gsp_trace})}",
                "",
                "## Bucket-level Summary",
                f"- bucket count: {len(bucket_rows)}",
                "",
                "## Limitation",
                "- all analyses are on reconstructed 416 board and do not establish N>=1000 generalization.",
            ]
        ),
        encoding="utf-8",
    )

    # Master report
    report = out_dir / "RTSS2026_GSP416_CANONICAL_MASTER_REPORT.md"
    report_lines = [
        "# RTSS2026 GSP416 CANONICAL MASTER REPORT",
        "",
        "## 1. Why Old TS3 Recovery Was Stopped",
        "- original TS3 locked policy is not recoverable from current workspace; hence a new canonical point is rebuilt from reconstructed 416 scores with fixed rule.",
        "",
        "## 2. How GSP416_CANONICAL Was Generated",
        f"- input: `{inp}`",
        "- three-action guarded routing (KEEP_BASELINE, FUSION_BOOST, DEFER) with explicit rear_guard / boost_gate / conflict / fallback rules.",
        "- exhaustive interpretable sweep over theta_rear, theta_nonrear, theta_margin, conflict_mode, fallback_rule.",
        "- deterministic selection order: min fallback -> max utility -> min rear risk -> min auto error -> max auto coverage.",
        "",
        "## 3. Contract Satisfaction",
        f"- rear_risk ({m_gsp['rear_risk']:.6f}) < 0.2000: {m_gsp['rear_risk'] < 0.2}",
        f"- utility ({m_gsp['utility']:.6f}) > 0.0571: {m_gsp['utility'] > 0.0571}",
        f"- auto_error ({m_gsp['auto_error']:.6f}) <= 0.6563: {m_gsp['auto_error'] <= 0.6563}",
        "",
        "## 4. Action Mix",
        f"- fallback_rate: {m_gsp['fallback_rate']:.6f}",
        f"- boost / defer / keep: {m_gsp['boost_count']} / {m_gsp['defer_count']} / {m_gsp['keep_count']}",
        "",
        "## 5. System Re-run Results",
        f"- queue stress settings: {len(queue_gsp)} (stable={stable_n}, borderline={border_n}, unstable={unstable_n})",
        f"- burst settings: {len(burst_rows)} (unstable={sum(1 for r in burst_rows if r['stability_flag']=='UNSTABLE')})",
        f"- bootstrap B: {args.bootstrap_B}",
        f"- LOBO by board_id runs: {len(lobo_board_rows)}",
        "",
        "## 6. Comparison vs BASE_ONLY and DETERMINISTIC_FUSION",
        f"- BASE_ONLY: rear_risk={m_base['rear_risk']:.6f}, auto_error={m_base['auto_error']:.6f}, utility={m_base['utility']:.6f}, fallback={m_base['fallback_rate']:.6f}",
        f"- DETERMINISTIC_FUSION: rear_risk={m_det['rear_risk']:.6f}, auto_error={m_det['auto_error']:.6f}, utility={m_det['utility']:.6f}, fallback={m_det['fallback_rate']:.6f}",
        f"- GSP416_CANONICAL: rear_risk={m_gsp['rear_risk']:.6f}, auto_error={m_gsp['auto_error']:.6f}, utility={m_gsp['utility']:.6f}, fallback={m_gsp['fallback_rate']:.6f}",
        "",
        "## 7. Paper Replacement Guidance (Old Table V)",
        "- Replace unrecoverable TS3/TS2/BA2 canonical claims with GSP416_CANONICAL as reproducible selected point on reconstructed 416.",
        "- Keep explicit statement that historical TS3 is non-recoverable in current workspace and is no longer used as canonical evidence.",
        "",
        "## 8. Claims That Can Be Upgraded",
        "- fully reproducible guarded selected point construction on 416 reconstructed board.",
        "- auditable selection rule and action-level trace generation.",
        "- queue/burst/bootstrap/LOBO evidence on the new canonical selected point.",
        "",
        "## 9. Claims Still Not Allowed",
        "- no N>=1000 generalization claim from this run.",
        "- no recovered-original-TS3 claim.",
        "- no cross-dataset SOTA claim.",
    ]
    report.write_text("\n".join(report_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "selected_candidate": selected["candidate_id"],
                "gsp_metrics": m_gsp,
                "selection_stage": selection_stage,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
