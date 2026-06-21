#!/usr/bin/env python3
import argparse
import csv
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


LABEL_REAR = "rear_end"
LABEL_LANE = "lane_change"
LABEL_TURN = "turn_conflict"

PROVENANCE_V4_LOCAL = "regenerated_from_reconstructed_416_scores_and_archived_v4_local_refine_rule"

BASE_ONLY = "BASE_ONLY"
DET_FUSION = "DETERMINISTIC_FUSION"
V2_LOW_FB = "V2_LOW_FALLBACK"
V3_CLOSEST = "V3_C35841"

POINT_PRIMARY = "GSP416_V4_PRIMARY_LOCAL"
POINT_LOW_FB = "GSP416_V4_LOW_FALLBACK_LOCAL"
POINT_LOW_REAR = "GSP416_V4_LOW_REAR_LOCAL"

ANCHOR_BASE_UTILITY = 0.0571
ANCHOR_BASE_AUTO = 0.6274
ANCHOR_DET_REAR = 0.2000
ANCHOR_DET_AUTO = 0.6563

C35841_FB = 0.043269
C35841_REAR = 0.144828
C35841_AUTO = 0.649038
C35841_UTILITY = 0.076749

TR_GRID = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
TN_GRID = [0.7, 0.8, 0.9, 0.95, 0.98, 0.99]
TMH_GRID = [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3]
TMB_GRID = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6]
TRS_GRID = [0.2, 0.3, 0.4, 0.5, 0.6]


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def bool_str(v: bool) -> str:
    return "True" if v else "False"


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


def compute_metrics(rows: List[Dict[str, Any]], pred_key: str, action_key: str) -> Dict[str, float]:
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

    score = (
        2.0 * (utility - ANCHOR_BASE_UTILITY)
        + 2.0 * (ANCHOR_DET_REAR - rear_risk)
        - 1.2 * fallback_rate
        - 0.8 * (auto_error - ANCHOR_BASE_AUTO)
    )

    return {
        "N": n,
        "defer_count": defer_count,
        "boost_count": boost_count,
        "keep_count": keep_count,
        "fallback_rate": fallback_rate,
        "auto_coverage": auto_coverage,
        "rear_risk": rear_risk,
        "auto_error": auto_error,
        "lane_recall": lane_recall,
        "turn_recall": turn_recall,
        "utility": utility,
        "rear_support_auto": rear_support_auto,
        "score_local": score,
    }


def canonical_bucket(raw_bucket: str) -> str:
    s = (raw_bucket or "").strip().lower().replace(" ", "_")
    if s in {"day+straight_road", "day+straightroad", "day+straight"}:
        return "day+straight_road"
    if s == "day+intersection":
        return "day+intersection"
    if s == "night+intersection":
        return "night+intersection"
    if s in {"night+straight_road", "night+straightroad", "night+straight"}:
        return "night+straight_road"
    return "other"


def classify_subtype(baseline_pred: str, fusion_pred: str, same_pred_weak: bool) -> str:
    if baseline_pred == fusion_pred:
        return "same_pred_low_conf" if same_pred_weak else "same_pred"
    if baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}:
        return "rear_to_nonrear"
    if baseline_pred in {LABEL_LANE, LABEL_TURN} and fusion_pred == LABEL_REAR:
        return "nonrear_to_rear"
    if baseline_pred == LABEL_LANE and fusion_pred == LABEL_TURN:
        return "lane_to_turn"
    if baseline_pred == LABEL_TURN and fusion_pred == LABEL_LANE:
        return "turn_to_lane"
    return "cross_other"


def step_tighter(grid: List[float], v: float) -> float:
    i = grid.index(v)
    return grid[min(len(grid) - 1, i + 1)]


@dataclass
class LocalParams:
    candidate_id: str
    family_name: str
    theta_rear_hold: float
    theta_rear_soft: float
    theta_nonrear_boost: float
    theta_margin_hold: float
    theta_margin_boost: float
    conflict_subtype_mode: str
    fallback_rule: str
    refine_mode: str
    bucket_config_id: str
    vulnerable_bucket_1: str
    vulnerable_bucket_2: str
    confidence_weak_thr: float = 0.6


def adjust_bucket_thresholds(bucket: str, p: LocalParams, tn: float, tmb: float) -> Tuple[float, float]:
    # R3: one-step tighter in 1~2 vulnerable buckets
    if p.bucket_config_id == "NA":
        return tn, tmb
    vulnerable = set()
    if p.vulnerable_bucket_1:
        vulnerable.add(p.vulnerable_bucket_1)
    if p.bucket_config_id in {"BT2", "BT12"} and p.vulnerable_bucket_2:
        vulnerable.add(p.vulnerable_bucket_2)
    if p.bucket_config_id == "BT1":
        vulnerable = {p.vulnerable_bucket_1}
    if bucket in vulnerable:
        return step_tighter(TN_GRID, tn), step_tighter(TMB_GRID, tmb)
    return tn, tmb


def decide_for_row_local(row: Dict[str, Any], p: LocalParams) -> Dict[str, Any]:
    baseline_pred = str(row.get("baseline_pred", "")).strip()
    fusion_pred = str(row.get("fusion_pred", "")).strip()
    gt = str(row.get("gt_type", "")).strip()

    baseline_score_rear = safe_float(row.get("baseline_score_rear", 0.0))
    fusion_score_rear = safe_float(row.get("fusion_score_rear", 0.0))
    fusion_score_lane = safe_float(row.get("fusion_score_lane", 0.0))
    fusion_score_turn = safe_float(row.get("fusion_score_turn", 0.0))
    fusion_nonrear_score = max(fusion_score_lane, fusion_score_turn)
    fusion_nonrear_pred = LABEL_LANE if fusion_score_lane >= fusion_score_turn else LABEL_TURN
    margin = safe_float(row.get("margin_nonrear_minus_rear", fusion_nonrear_score - fusion_score_rear))

    b = canonical_bucket(str(row.get("bucket_id", "")))
    tn_eff, tmb_eff = adjust_bucket_thresholds(b, p, p.theta_nonrear_boost, p.theta_margin_boost)
    tr_eff = p.theta_rear_hold
    tmh_eff = p.theta_margin_hold
    trs_eff = p.theta_rear_soft

    same_pred_weak = (baseline_pred == fusion_pred) and (max(baseline_score_rear, fusion_nonrear_score) < p.confidence_weak_thr)
    rear_tension = baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}
    lane_turn_swap = (baseline_pred == LABEL_LANE and fusion_pred == LABEL_TURN) or (baseline_pred == LABEL_TURN and fusion_pred == LABEL_LANE)
    disagreement = baseline_pred != fusion_pred
    subtype = classify_subtype(baseline_pred, fusion_pred, same_pred_weak)

    # F1 base semantics
    keep_stage1 = False
    if baseline_pred == LABEL_REAR and baseline_score_rear >= tr_eff:
        keep_stage1 = True
    if rear_tension and margin < tmh_eff:
        keep_stage1 = True
    if same_pred_weak:
        keep_stage1 = True

    # R2: keep-priority soft override
    if p.refine_mode == "R2" and baseline_pred == LABEL_REAR and baseline_score_rear >= trs_eff:
        keep_stage1 = True

    # R1: rear-tension tighter defer (reduce keep in weak rear-tension cases)
    if p.refine_mode == "R1" and rear_tension:
        weak_rear = baseline_score_rear < max(trs_eff, 0.3)
        weak_nonrear_evidence = (fusion_nonrear_score < tn_eff) or (margin < tmb_eff)
        if weak_rear and weak_nonrear_evidence:
            keep_stage1 = False

    # Stage2 boost gate
    tn_req = tn_eff
    tmb_req = tmb_eff
    # R4: only rear_to_nonrear gets tighter thresholds
    if p.refine_mode == "R4" and subtype == "rear_to_nonrear":
        tn_req = step_tighter(TN_GRID, tn_eff)
        tmb_req = step_tighter(TMB_GRID, tmb_eff)

    boost_gate = fusion_nonrear_score >= tn_req and margin >= tmb_req
    unresolved = not boost_gate

    if p.conflict_subtype_mode == "OFF":
        conflict_flag = disagreement
    else:
        conflict_flag = disagreement or same_pred_weak

    defer_flag = False
    if p.fallback_rule == "A":
        defer_flag = rear_tension and unresolved
    elif p.fallback_rule == "B":
        defer_flag = disagreement and unresolved
    elif p.fallback_rule == "F":
        defer_flag = conflict_flag and unresolved and (not keep_stage1)
    else:
        raise ValueError(f"unknown fallback rule {p.fallback_rule}")

    if keep_stage1:
        action = "KEEP_BASELINE"
        final_pred = baseline_pred
    elif boost_gate:
        action = "FUSION_BOOST"
        final_pred = fusion_pred
    elif defer_flag:
        action = "DEFER"
        final_pred = baseline_pred
    else:
        action = "KEEP_BASELINE"
        final_pred = baseline_pred

    return {
        **row,
        "action": action,
        "final_pred": final_pred,
        "rear_guard_flag": keep_stage1 and baseline_pred == LABEL_REAR,
        "boost_gate_flag": boost_gate,
        "conflict_flag": conflict_flag,
        "uncertain_conflict_flag": defer_flag,
        "conflict_subtype": subtype,
        "is_deferred": bool_str(action == "DEFER"),
        "is_auto": bool_str(action != "DEFER"),
        "is_rear_gt": bool_str(gt == LABEL_REAR),
        "is_lane_gt": bool_str(gt == LABEL_LANE),
        "is_turn_gt": bool_str(gt == LABEL_TURN),
        "is_rear_miss": bool_str(gt == LABEL_REAR and final_pred != LABEL_REAR and action != "DEFER"),
        "is_wrong_auto": bool_str(action != "DEFER" and final_pred != gt),
        "baseline_correct": bool_str(baseline_pred == gt),
        "fusion_correct": bool_str(fusion_pred == gt),
        "final_correct": bool_str(action != "DEFER" and final_pred == gt),
        "fusion_nonrear_score": fusion_nonrear_score,
        "fusion_nonrear_pred": fusion_nonrear_pred,
        "margin_nonrear_minus_rear": margin,
    }


def run_policy_local(rows: List[Dict[str, Any]], p: LocalParams, policy_name: str) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        d = decide_for_row_local(r, p)
        d["policy_name"] = policy_name
        out.append(d)
    return out


def build_base_and_det(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    base_rows = []
    det_rows = []
    for r in rows:
        rb = dict(r)
        rb["action"] = "KEEP_BASELINE"
        rb["final_pred"] = str(r.get("baseline_pred", "")).strip()
        rb["policy_name"] = BASE_ONLY
        base_rows.append(rb)

        rd = dict(r)
        rd["action"] = "FUSION_BOOST"
        rd["final_pred"] = str(r.get("fusion_pred", "")).strip()
        rd["policy_name"] = DET_FUSION
        det_rows.append(rd)
    return base_rows, det_rows


def local_predicate_formula(p: LocalParams) -> str:
    return (
        f"family={p.family_name}; "
        f"theta_rear_hold={p.theta_rear_hold}; theta_rear_soft={p.theta_rear_soft}; "
        f"theta_nonrear_boost={p.theta_nonrear_boost}; theta_margin_hold={p.theta_margin_hold}; theta_margin_boost={p.theta_margin_boost}; "
        f"fallback_rule={p.fallback_rule}; conflict_subtype_mode={p.conflict_subtype_mode}; "
        f"refine_mode={p.refine_mode}; bucket_config_id={p.bucket_config_id}; "
        f"vulnerable_bucket_1={p.vulnerable_bucket_1}; vulnerable_bucket_2={p.vulnerable_bucket_2}; "
        f"R1=rear_tension_tighter_defer; R2=keep_priority_soft_override; R3=bucket_local_one_step_tighter; R4=rear_to_nonrear_subtype_tighter"
    )


def to_trace_rows(policy_rows: List[Dict[str, Any]], point_name: str, predicate_formula: str) -> List[Dict[str, Any]]:
    out = []
    for r in policy_rows:
        out.append(
            {
                "sample_id": r.get("sample_id", ""),
                "case_id": r.get("case_id", r.get("sample_id", "")),
                "board_id": r.get("board_id", ""),
                "bucket_id": r.get("bucket_id", ""),
                "source_id": r.get("source_id", r.get("board_id", "")),
                "gt_type": r.get("gt_type", ""),
                "baseline_pred": r.get("baseline_pred", ""),
                "fusion_pred": r.get("fusion_pred", ""),
                "policy_name": point_name,
                "action": r.get("action", ""),
                "final_pred": r.get("final_pred", ""),
                "is_deferred": r.get("is_deferred", bool_str(str(r.get("action", "")) == "DEFER")),
                "is_auto": r.get("is_auto", bool_str(str(r.get("action", "")) != "DEFER")),
                "is_rear_gt": r.get("is_rear_gt", bool_str(str(r.get("gt_type", "")) == LABEL_REAR)),
                "is_lane_gt": r.get("is_lane_gt", bool_str(str(r.get("gt_type", "")) == LABEL_LANE)),
                "is_turn_gt": r.get("is_turn_gt", bool_str(str(r.get("gt_type", "")) == LABEL_TURN)),
                "is_rear_miss": r.get("is_rear_miss", ""),
                "is_wrong_auto": r.get("is_wrong_auto", ""),
                "baseline_correct": r.get("baseline_correct", ""),
                "fusion_correct": r.get("fusion_correct", ""),
                "final_correct": r.get("final_correct", ""),
                "baseline_score_rear": r.get("baseline_score_rear", ""),
                "fusion_score_rear": r.get("fusion_score_rear", ""),
                "fusion_score_lane": r.get("fusion_score_lane", ""),
                "fusion_score_turn": r.get("fusion_score_turn", ""),
                "fusion_nonrear_score": r.get("fusion_nonrear_score", ""),
                "margin_nonrear_minus_rear": r.get("margin_nonrear_minus_rear", ""),
                "rear_guard_flag": r.get("rear_guard_flag", ""),
                "boost_gate_flag": r.get("boost_gate_flag", ""),
                "conflict_flag": r.get("conflict_flag", ""),
                "uncertain_conflict_flag": r.get("uncertain_conflict_flag", ""),
                "conflict_subtype": r.get("conflict_subtype", ""),
                "predicate_formula": predicate_formula,
            }
        )
    return out


def write_policy_file(path: Path, point_name: str, p: LocalParams) -> None:
    lines = [
        "# Auto-generated V4 local refinement policy parameters",
        f"POINT_NAME = '{point_name}'",
        f"FAMILY_NAME = '{p.family_name}'",
        f"THETA_REAR_HOLD = {p.theta_rear_hold}",
        f"THETA_REAR_SOFT = {p.theta_rear_soft}",
        f"THETA_NONREAR_BOOST = {p.theta_nonrear_boost}",
        f"THETA_MARGIN_HOLD = {p.theta_margin_hold}",
        f"THETA_MARGIN_BOOST = {p.theta_margin_boost}",
        f"CONFLICT_SUBTYPE_MODE = '{p.conflict_subtype_mode}'",
        f"FALLBACK_RULE = '{p.fallback_rule}'",
        f"REFINE_MODE = '{p.refine_mode}'",
        f"BUCKET_CONFIG_ID = '{p.bucket_config_id}'",
        f"VULNERABLE_BUCKET_1 = '{p.vulnerable_bucket_1}'",
        f"VULNERABLE_BUCKET_2 = '{p.vulnerable_bucket_2}'",
        f"CONFIDENCE_WEAK_THR = {p.confidence_weak_thr}",
        "",
        f"PROVENANCE = '{PROVENANCE_V4_LOCAL}'",
        "",
        "# Refer to backend/scripts/rtss2026_build_gsp416_v4_local_refine.py decide_for_row_local()",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def queue_sim(actions: List[str], arrival_rate: float, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    queue = 0
    q_hist = []
    defer_count = 0
    total_samples = 0
    idx = 0
    n = len(actions)
    for _ in range(duration_sec):
        arrivals = int(round(arrival_rate))
        for _ in range(arrivals):
            if n == 0:
                break
            a = actions[idx % n]
            idx += 1
            total_samples += 1
            if a == "DEFER":
                queue += 1
                defer_count += 1
        served = min(queue, int(round(service_rate)))
        queue -= served
        q_hist.append(queue)

    defer_rate = (defer_count / total_samples) if total_samples else 0.0
    eff = arrival_rate * defer_rate
    arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    if eff <= service_rate * 0.95 and (arr[-1] <= max(5.0, np.quantile(arr, 0.95, method="linear"))):
        stab = "STABLE"
    elif eff > service_rate * 1.05:
        stab = "UNSTABLE"
    else:
        stab = "BORDERLINE"
    return {
        "arrival_rate": arrival_rate,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total_samples,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "effective_defer_arrival_rate": eff,
        "max_queue_length": int(np.max(arr)),
        "mean_queue_length": float(np.mean(arr)),
        "p95_queue_length": float(np.quantile(arr, 0.95, method="linear")),
        "p99_queue_length": float(np.quantile(arr, 0.99, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": stab,
    }


def bootstrap_policy_metrics(rows: List[Dict[str, Any]], B: int, seed: int) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(rows)
    fb = np.zeros(B, dtype=float)
    rr = np.zeros(B, dtype=float)
    ae = np.zeros(B, dtype=float)
    ut = np.zeros(B, dtype=float)
    for i in range(B):
        idx = rng.integers(0, n, size=n)
        sample = [rows[int(j)] for j in idx]
        m = compute_metrics(sample, pred_key="final_pred", action_key="action")
        fb[i] = m["fallback_rate"]
        rr[i] = m["rear_risk"]
        ae[i] = m["auto_error"]
        ut[i] = m["utility"]
    return {
        "fallback_mean": float(np.mean(fb)),
        "fallback_p05": float(np.quantile(fb, 0.05, method="linear")),
        "fallback_p95": float(np.quantile(fb, 0.95, method="linear")),
        "rear_risk_mean": float(np.mean(rr)),
        "rear_risk_p05": float(np.quantile(rr, 0.05, method="linear")),
        "rear_risk_p95": float(np.quantile(rr, 0.95, method="linear")),
        "auto_error_mean": float(np.mean(ae)),
        "auto_error_p05": float(np.quantile(ae, 0.05, method="linear")),
        "auto_error_p95": float(np.quantile(ae, 0.95, method="linear")),
        "utility_mean": float(np.mean(ut)),
        "utility_p05": float(np.quantile(ut, 0.05, method="linear")),
        "utility_p95": float(np.quantile(ut, 0.95, method="linear")),
    }


def lobo_metrics(rows: List[Dict[str, Any]], group_field: str) -> List[Dict[str, Any]]:
    groups = sorted({str(r.get(group_field, "")).strip() for r in rows})
    out = []
    for g in groups:
        sub = [r for r in rows if str(r.get(group_field, "")).strip() != g]
        m = compute_metrics(sub, pred_key="final_pred", action_key="action")
        out.append({"left_out_unit": g, "group_field": group_field, **m})
    return out


def get_vulnerable_buckets_from_c35841(base_rows: List[Dict[str, Any]], c35841_row: Dict[str, Any]) -> Tuple[str, str, List[Dict[str, Any]], Dict[str, float]]:
    p = LocalParams(
        candidate_id="C35841",
        family_name=str(c35841_row["family_name"]),
        theta_rear_hold=float(c35841_row["theta_rear_hold"]),
        theta_rear_soft=float(c35841_row["theta_rear_soft"]),
        theta_nonrear_boost=float(c35841_row["theta_nonrear_boost"]),
        theta_margin_hold=float(c35841_row["theta_margin_hold"]),
        theta_margin_boost=float(c35841_row["theta_margin_boost"]),
        conflict_subtype_mode=str(c35841_row["conflict_subtype_mode"]),
        fallback_rule=str(c35841_row["fallback_rule"]),
        refine_mode="NONE",
        bucket_config_id="NA",
        vulnerable_bucket_1="",
        vulnerable_bucket_2="",
    )
    rows = run_policy_local(base_rows, p, policy_name=V3_CLOSEST)
    by_bucket = {}
    for b in sorted({canonical_bucket(str(r.get("bucket_id", ""))) for r in rows}):
        sub = [r for r in rows if canonical_bucket(str(r.get("bucket_id", ""))) == b]
        rear_sub = [r for r in sub if str(r.get("gt_type", "")) == LABEL_REAR]
        if rear_sub:
            rr = sum(1 for r in rear_sub if r.get("action") != "DEFER" and r.get("final_pred") != LABEL_REAR) / len(rear_sub)
        else:
            rr = -1.0
        by_bucket[b] = {"bucket_id": b, "N": len(sub), "rear_support": len(rear_sub), "rear_risk": rr}
    ranked = sorted(by_bucket.values(), key=lambda x: (x["rear_risk"], x["rear_support"]), reverse=True)
    v1 = ranked[0]["bucket_id"] if ranked else "day+intersection"
    v2 = ranked[1]["bucket_id"] if len(ranked) > 1 else "night+intersection"
    return v1, v2, rows, by_bucket


def load_v2_low_trace(path: Path) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    rows = read_csv(path)
    for r in rows:
        r["policy_name"] = V2_LOW_FB
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="RTSS2026 V4 local refinement around V3 C35841.")
    parser.add_argument("--base_table", type=str, required=True)
    parser.add_argument("--v3_candidates_csv", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--duration_sec", type=int, default=300)
    parser.add_argument("--bootstrap_B", type=int, default=5000)
    parser.add_argument("--max_candidates", type=int, default=5000)
    parser.add_argument(
        "--v2_low_fallback_trace",
        type=str,
        default=r"D:\computer code\accident_app\outputs\rtss2026_gsp416_canonical_v2_selection_20260522_115936\GSP416_LOW_FALLBACK_action_trace.csv",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_rows_raw = read_csv(Path(args.base_table))
    base_rows, det_rows = build_base_and_det(base_rows_raw)

    v3_rows = read_csv(Path(args.v3_candidates_csv))
    c35841 = next((r for r in v3_rows if str(r.get("candidate_id", "")) == "C35841"), None)
    if c35841 is None:
        raise RuntimeError("C35841 not found in v3 candidates csv.")

    vulnerable1, vulnerable2, c35841_policy_rows, bucket_stats = get_vulnerable_buckets_from_c35841(base_rows_raw, c35841)
    c35841_metrics = compute_metrics(c35841_policy_rows, pred_key="final_pred", action_key="action")

    # Local neighborhood around C35841 (bounded <=5000)
    tr_set = [0.5, 0.6, 0.7]
    trs_set = [0.2, 0.3]
    tn_set = [0.95, 0.98, 0.99]
    tmh_set = [-0.2, -0.1, 0.0]
    tmb_set = [0.0, 0.1]
    fallback_rules_core = ["A", "B", "F"]
    subtype_set_core = ["OFF"]
    refine_core = ["NONE", "R1", "R2"]
    bucket_core = ["NA"]

    # R3 and R4 focused expansions
    bucket_r3 = ["BT1", "BT2", "BT12"]
    refine_r3 = ["NONE", "R1"]
    subtype_r4 = ["ON"]
    refine_r4 = ["R4"]

    candidates: List[Dict[str, Any]] = []
    cid = 1

    def emit(p: LocalParams) -> None:
        nonlocal cid
        pol = run_policy_local(base_rows_raw, p, policy_name=f"GSP416_V4_LOCAL_CANDIDATE_{p.candidate_id}")
        m = compute_metrics(pol, pred_key="final_pred", action_key="action")
        candidates.append(
            {
                "candidate_id": p.candidate_id,
                "family_name": p.family_name,
                "theta_rear_hold": p.theta_rear_hold,
                "theta_rear_soft": p.theta_rear_soft,
                "theta_nonrear_boost": p.theta_nonrear_boost,
                "theta_margin_hold": p.theta_margin_hold,
                "theta_margin_boost": p.theta_margin_boost,
                "conflict_subtype_mode": p.conflict_subtype_mode,
                "fallback_rule": p.fallback_rule,
                "refine_mode": p.refine_mode,
                "bucket_config_id": p.bucket_config_id,
                "vulnerable_bucket_1": p.vulnerable_bucket_1,
                "vulnerable_bucket_2": p.vulnerable_bucket_2,
                "defer_count": m["defer_count"],
                "boost_count": m["boost_count"],
                "keep_count": m["keep_count"],
                "fallback_rate": m["fallback_rate"],
                "rear_risk": m["rear_risk"],
                "auto_error": m["auto_error"],
                "lane_recall": m["lane_recall"],
                "turn_recall": m["turn_recall"],
                "utility": m["utility"],
                "auto_coverage": m["auto_coverage"],
                "rear_support_auto": m["rear_support_auto"],
                "score_local": m["score_local"],
                "delta_vs_c35841_fallback": m["fallback_rate"] - C35841_FB,
                "delta_vs_c35841_rear": m["rear_risk"] - C35841_REAR,
                "delta_vs_c35841_auto": m["auto_error"] - C35841_AUTO,
                "delta_vs_c35841_utility": m["utility"] - C35841_UTILITY,
                "predicate_formula": local_predicate_formula(p),
            }
        )
        cid += 1

    # Core local search
    for tr in tr_set:
        for trs in trs_set:
            for tn in tn_set:
                for tmh in tmh_set:
                    for tmb in tmb_set:
                        for fr in fallback_rules_core:
                            for st in subtype_set_core:
                                for rf in refine_core:
                                    for bc in bucket_core:
                                        p = LocalParams(
                                            candidate_id=f"LC{cid:05d}",
                                            family_name="F1",
                                            theta_rear_hold=tr,
                                            theta_rear_soft=trs,
                                            theta_nonrear_boost=tn,
                                            theta_margin_hold=tmh,
                                            theta_margin_boost=tmb,
                                            conflict_subtype_mode=st,
                                            fallback_rule=fr,
                                            refine_mode=rf,
                                            bucket_config_id=bc,
                                            vulnerable_bucket_1=vulnerable1,
                                            vulnerable_bucket_2=vulnerable2,
                                        )
                                        emit(p)

    # R3 bucket local one-step tighter
    for tr in tr_set:
        for trs in trs_set:
            for tn in [0.95, 0.98]:
                for tmh in [-0.2, -0.1]:
                    for tmb in [0.0, 0.1]:
                        for fr in fallback_rules_core:
                            for rf in refine_r3:
                                for bc in bucket_r3:
                                    p = LocalParams(
                                        candidate_id=f"LC{cid:05d}",
                                        family_name="F1",
                                        theta_rear_hold=tr,
                                        theta_rear_soft=trs,
                                        theta_nonrear_boost=tn,
                                        theta_margin_hold=tmh,
                                        theta_margin_boost=tmb,
                                        conflict_subtype_mode="OFF",
                                        fallback_rule=fr,
                                        refine_mode=rf,
                                        bucket_config_id=bc,
                                        vulnerable_bucket_1=vulnerable1,
                                        vulnerable_bucket_2=vulnerable2,
                                    )
                                    emit(p)

    # R4 subtype-specific tighter for rear_to_nonrear
    for tr in tr_set:
        for trs in trs_set:
            for tn in tn_set:
                for tmh in [-0.2, -0.1]:
                    for tmb in [0.0, 0.1]:
                        for fr in ["A", "B"]:
                            for bc in ["NA", "BT1", "BT12"]:
                                p = LocalParams(
                                    candidate_id=f"LC{cid:05d}",
                                    family_name="F1",
                                    theta_rear_hold=tr,
                                    theta_rear_soft=trs,
                                    theta_nonrear_boost=tn,
                                    theta_margin_hold=tmh,
                                    theta_margin_boost=tmb,
                                    conflict_subtype_mode="ON",
                                    fallback_rule=fr,
                                    refine_mode="R4",
                                    bucket_config_id=bc,
                                    vulnerable_bucket_1=vulnerable1,
                                    vulnerable_bucket_2=vulnerable2,
                                )
                                emit(p)

    if len(candidates) > args.max_candidates:
        # deterministic truncation by highest local score first, then safer rear/fallback
        candidates = sorted(candidates, key=lambda c: (-c["score_local"], c["rear_risk"], c["fallback_rate"], c["candidate_id"]))[: args.max_candidates]

    # Selection sets
    primary_feasible = [
        c
        for c in candidates
        if c["fallback_rate"] <= 0.04 and c["rear_risk"] <= 0.14 and c["utility"] >= 0.075 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    primary_ranked = sorted(primary_feasible, key=lambda c: (-c["score_local"], c["rear_risk"], c["fallback_rate"], -c["utility"], c["candidate_id"]))
    pick_primary = primary_ranked[0] if primary_ranked else None

    low_fb_feasible = [
        c
        for c in candidates
        if c["fallback_rate"] <= C35841_FB and c["utility"] >= 0.072 and c["rear_risk"] <= 0.15 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    low_fb_ranked = sorted(low_fb_feasible, key=lambda c: (c["fallback_rate"], c["rear_risk"], -c["utility"], c["candidate_id"]))
    pick_low_fb = low_fb_ranked[0] if low_fb_ranked else None

    low_rear_feasible = [
        c
        for c in candidates
        if c["rear_risk"] < C35841_REAR and c["utility"] >= 0.060 and c["fallback_rate"] <= 0.08 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    low_rear_ranked = sorted(low_rear_feasible, key=lambda c: (c["rear_risk"], -c["utility"], c["fallback_rate"], c["candidate_id"]))
    pick_low_rear = low_rear_ranked[0] if low_rear_ranked else None

    fields = [
        "candidate_id",
        "family_name",
        "theta_rear_hold",
        "theta_rear_soft",
        "theta_nonrear_boost",
        "theta_margin_hold",
        "theta_margin_boost",
        "conflict_subtype_mode",
        "fallback_rule",
        "refine_mode",
        "bucket_config_id",
        "vulnerable_bucket_1",
        "vulnerable_bucket_2",
        "defer_count",
        "boost_count",
        "keep_count",
        "fallback_rate",
        "rear_risk",
        "auto_error",
        "lane_recall",
        "turn_recall",
        "utility",
        "auto_coverage",
        "rear_support_auto",
        "score_local",
        "delta_vs_c35841_fallback",
        "delta_vs_c35841_rear",
        "delta_vs_c35841_auto",
        "delta_vs_c35841_utility",
        "predicate_formula",
    ]
    write_csv(out_dir / "01_v4_local_candidates.csv", candidates, fields)
    write_csv(out_dir / "02_v4_local_primary.csv", primary_ranked, fields)
    write_csv(out_dir / "03_v4_local_low_fallback.csv", low_fb_ranked, fields)
    write_csv(out_dir / "04_v4_local_low_rear.csv", low_rear_ranked, fields)

    # Selected points markdown
    sel_md = [
        "# 05 V4 Local Selected Points",
        "",
        "## Anchor",
        f"- V3 C35841: fallback={C35841_FB:.6f}, rear_risk={C35841_REAR:.6f}, auto_error={C35841_AUTO:.6f}, utility={C35841_UTILITY:.6f}",
        "",
        "## Vulnerable Buckets (from C35841)",
    ]
    for b, s in sorted(bucket_stats.items(), key=lambda kv: kv[1]["rear_risk"], reverse=True):
        sel_md.append(f"- {b}: N={s['N']}, rear_support={s['rear_support']}, rear_risk={s['rear_risk']:.6f}")
    sel_md.extend(
        [
            "",
            "## Picks",
            f"- {POINT_PRIMARY}: "
            + (
                "NONE"
                if pick_primary is None
                else f"{pick_primary['candidate_id']} | fallback={pick_primary['fallback_rate']:.6f}, rear_risk={pick_primary['rear_risk']:.6f}, auto_error={pick_primary['auto_error']:.6f}, utility={pick_primary['utility']:.6f}, score={pick_primary['score_local']:.6f}"
            ),
            f"- {POINT_LOW_FB}: "
            + (
                "NONE"
                if pick_low_fb is None
                else f"{pick_low_fb['candidate_id']} | fallback={pick_low_fb['fallback_rate']:.6f}, rear_risk={pick_low_fb['rear_risk']:.6f}, auto_error={pick_low_fb['auto_error']:.6f}, utility={pick_low_fb['utility']:.6f}"
            ),
            f"- {POINT_LOW_REAR}: "
            + (
                "NONE"
                if pick_low_rear is None
                else f"{pick_low_rear['candidate_id']} | fallback={pick_low_rear['fallback_rate']:.6f}, rear_risk={pick_low_rear['rear_risk']:.6f}, auto_error={pick_low_rear['auto_error']:.6f}, utility={pick_low_rear['utility']:.6f}"
            ),
            "",
            f"- total_local_candidates: {len(candidates)}",
            f"- max_candidates_limit: {args.max_candidates}",
        ]
    )
    (out_dir / "05_v4_local_selected_points.md").write_text("\n".join(sel_md) + "\n", encoding="utf-8")

    # Materialize selected traces and policy
    selected_map: Dict[str, List[Dict[str, Any]]] = {
        BASE_ONLY: base_rows,
        DET_FUSION: det_rows,
        V3_CLOSEST: c35841_policy_rows,
    }

    # materialize C35841 trace for completeness in rerun comparison
    c35841_trace = to_trace_rows(c35841_policy_rows, V3_CLOSEST, str(c35841.get("predicate_formula", "")))
    write_csv(out_dir / f"{V3_CLOSEST}_action_trace.csv", c35841_trace, list(c35841_trace[0].keys()) if c35841_trace else [])

    def materialize_pick(point_name: str, pick: Optional[Dict[str, Any]]) -> None:
        if pick is None:
            return
        p = LocalParams(
            candidate_id=str(pick["candidate_id"]),
            family_name=str(pick["family_name"]),
            theta_rear_hold=float(pick["theta_rear_hold"]),
            theta_rear_soft=float(pick["theta_rear_soft"]),
            theta_nonrear_boost=float(pick["theta_nonrear_boost"]),
            theta_margin_hold=float(pick["theta_margin_hold"]),
            theta_margin_boost=float(pick["theta_margin_boost"]),
            conflict_subtype_mode=str(pick["conflict_subtype_mode"]),
            fallback_rule=str(pick["fallback_rule"]),
            refine_mode=str(pick["refine_mode"]),
            bucket_config_id=str(pick["bucket_config_id"]),
            vulnerable_bucket_1=str(pick["vulnerable_bucket_1"]),
            vulnerable_bucket_2=str(pick["vulnerable_bucket_2"]),
        )
        pol = run_policy_local(base_rows_raw, p, policy_name=point_name)
        selected_map[point_name] = pol
        trace_rows = to_trace_rows(pol, point_name, str(pick["predicate_formula"]))
        write_csv(out_dir / f"{point_name}_action_trace.csv", trace_rows, list(trace_rows[0].keys()) if trace_rows else [])
        write_policy_file(out_dir / f"{point_name}_policy.py", point_name, p)
        m = compute_metrics(pol, pred_key="final_pred", action_key="action")
        lines = [
            f"# {point_name} Metrics",
            "",
            f"- provenance: {PROVENANCE_V4_LOCAL}",
            f"- candidate_id: {pick['candidate_id']}",
            f"- fallback_rate: {m['fallback_rate']:.6f}",
            f"- rear_risk: {m['rear_risk']:.6f}",
            f"- auto_error: {m['auto_error']:.6f}",
            f"- utility: {m['utility']:.6f}",
            f"- lane_recall: {m['lane_recall']:.6f}",
            f"- turn_recall: {m['turn_recall']:.6f}",
            f"- auto_coverage: {m['auto_coverage']:.6f}",
            f"- score_local: {m['score_local']:.6f}",
            f"- predicate_formula: {pick['predicate_formula']}",
        ]
        (out_dir / f"{point_name}_metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    materialize_pick(POINT_PRIMARY, pick_primary)
    materialize_pick(POINT_LOW_FB, pick_low_fb)
    materialize_pick(POINT_LOW_REAR, pick_low_rear)

    # load V2 low fallback trace
    v2_low_rows = load_v2_low_trace(Path(args.v2_low_fallback_trace))
    if v2_low_rows is not None:
        selected_map[V2_LOW_FB] = v2_low_rows

    # Queue stress rerun
    queue_rows: List[Dict[str, Any]] = []
    for pname, rows in selected_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for lam in [1, 5, 10, 20, 30, 50, 100]:
            for mu in [0.1, 0.5, 1, 2, 5, 10]:
                q = queue_sim(actions, float(lam), float(mu), duration_sec=args.duration_sec)
                queue_rows.append({"policy_name": pname, **q})
    write_csv(
        out_dir / "06_v4_local_queue_raw.csv",
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
    q_md = ["# 06 V4 Local Queue Summary", ""]
    for pname in selected_map.keys():
        sub = [r for r in queue_rows if r["policy_name"] == pname]
        st = sum(1 for r in sub if r["stability_flag"] == "STABLE")
        bd = sum(1 for r in sub if r["stability_flag"] == "BORDERLINE")
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        q_md.append(f"- {pname}: stable/borderline/unstable={st}/{bd}/{un}")
    (out_dir / "06_v4_local_queue_summary.md").write_text("\n".join(q_md) + "\n", encoding="utf-8")

    # Bootstrap + LOBO rerun
    boot_rows = []
    lobo_rows = []
    for i, (pname, rows) in enumerate(selected_map.items(), start=1):
        bs = bootstrap_policy_metrics(rows, B=args.bootstrap_B, seed=args.seed + i * 43)
        boot_rows.append({"policy_name": pname, **bs})
        lo = lobo_metrics(rows, group_field="board_id")
        for r in lo:
            lobo_rows.append({"policy_name": pname, **r})

    write_csv(
        out_dir / "07_v4_local_bootstrap_summary.csv",
        boot_rows,
        [
            "policy_name",
            "fallback_mean",
            "fallback_p05",
            "fallback_p95",
            "rear_risk_mean",
            "rear_risk_p05",
            "rear_risk_p95",
            "auto_error_mean",
            "auto_error_p05",
            "auto_error_p95",
            "utility_mean",
            "utility_p05",
            "utility_p95",
        ],
    )
    write_csv(
        out_dir / "07_v4_local_lobo_board.csv",
        lobo_rows,
        [
            "policy_name",
            "left_out_unit",
            "group_field",
            "N",
            "defer_count",
            "boost_count",
            "keep_count",
            "fallback_rate",
            "auto_coverage",
            "rear_risk",
            "auto_error",
            "lane_recall",
            "turn_recall",
            "utility",
            "rear_support_auto",
            "score_local",
        ],
    )
    bl = ["# 07 V4 Local Bootstrap + LOBO Summary", "", f"- bootstrap_B: {args.bootstrap_B}", ""]
    for r in boot_rows:
        bl.append(
            f"- {r['policy_name']}: fallback={r['fallback_mean']:.6f}, rear_risk={r['rear_risk_mean']:.6f}, auto_error={r['auto_error_mean']:.6f}, utility={r['utility_mean']:.6f}"
        )
    (out_dir / "07_v4_local_bootstrap_lobo_summary.md").write_text("\n".join(bl) + "\n", encoding="utf-8")

    # Master report
    def line_pick(name: str, pick: Optional[Dict[str, Any]]) -> str:
        if pick is None:
            return f"- {name}: NONE"
        return (
            f"- {name}: {pick['candidate_id']} | fallback={pick['fallback_rate']:.6f}, "
            f"rear_risk={pick['rear_risk']:.6f}, auto_error={pick['auto_error']:.6f}, utility={pick['utility']:.6f}, "
            f"delta_vs_C35841=(fb {pick['delta_vs_c35841_fallback']:+.6f}, rear {pick['delta_vs_c35841_rear']:+.6f}, util {pick['delta_vs_c35841_utility']:+.6f})"
        )

    improved_vs_c35841 = [
        c
        for c in candidates
        if (c["rear_risk"] < C35841_REAR or c["fallback_rate"] < C35841_FB or c["utility"] > C35841_UTILITY)
        and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    closest_primary = None
    if pick_primary is None:
        maybe = [c for c in candidates if c["utility"] >= 0.075 and c["auto_error"] <= ANCHOR_DET_AUTO]
        if maybe:
            closest_primary = sorted(
                maybe,
                key=lambda c: (
                    max(0.0, c["fallback_rate"] - 0.04)
                    + max(0.0, c["rear_risk"] - 0.14)
                    + max(0.0, 0.075 - c["utility"]),
                    -c["score_local"],
                ),
            )[0]

    recommend_stop = False
    recommend_replace_v2 = False
    if pick_primary is None and (pick_low_fb is None and pick_low_rear is None):
        recommend_stop = True
    else:
        # replace only if primary exists and clearly dominates V2 low fallback on risk+utility with controlled fallback
        if pick_primary is not None:
            recommend_replace_v2 = (
                pick_primary["utility"] >= 0.075
                and pick_primary["rear_risk"] <= 0.15
                and pick_primary["fallback_rate"] <= 0.05
                and pick_primary["auto_error"] <= ANCHOR_DET_AUTO
            )
        if not recommend_replace_v2 and pick_low_fb is not None and pick_low_rear is not None:
            if (pick_low_fb["rear_risk"] >= C35841_REAR and pick_low_rear["utility"] < 0.070):
                recommend_stop = True

    report = [
        "# RTSS2026_GSP416_V4_LOCAL_REFINE_MASTER_REPORT",
        "",
        "## 1. Did local refine beat C35841?",
        f"- improved_candidate_exists: {bool(len(improved_vs_c35841) > 0)}",
        f"- local_candidate_count: {len(candidates)}",
        f"- candidate_cap: {args.max_candidates}",
        f"- C35841 reference: fallback={C35841_FB:.6f}, rear_risk={C35841_REAR:.6f}, auto_error={C35841_AUTO:.6f}, utility={C35841_UTILITY:.6f}",
        "",
        "## 2. PRIMARY_LOCAL status",
        line_pick(POINT_PRIMARY, pick_primary),
        "",
        "## 3. Other local points",
        line_pick(POINT_LOW_FB, pick_low_fb),
        line_pick(POINT_LOW_REAR, pick_low_rear),
        "",
        "## 4. If PRIMARY_LOCAL missing, closest candidate",
    ]
    if closest_primary is None:
        report.append("- closest: NONE")
    else:
        report.append(
            f"- closest: {closest_primary['candidate_id']} | fallback={closest_primary['fallback_rate']:.6f}, rear_risk={closest_primary['rear_risk']:.6f}, auto_error={closest_primary['auto_error']:.6f}, utility={closest_primary['utility']:.6f}"
        )
        report.append(
            f"- gap_to_primary: dfallback={max(0.0, closest_primary['fallback_rate']-0.04):.6f}, drear={max(0.0, closest_primary['rear_risk']-0.14):.6f}, dutility={max(0.0, 0.075-closest_primary['utility']):.6f}, dauto={max(0.0, closest_primary['auto_error']-0.6563):.6f}"
        )
    report.extend(
        [
            "",
            "## 5. Replace V2 LOW_FALLBACK as main point?",
            f"- recommendation_replace_v2_low_fallback: {recommend_replace_v2}",
            "",
            "## 6. Should we stop experiments and move to writing?",
            f"- recommendation_stop_and_write: {recommend_stop}",
            "",
            "## 7. Boundaries",
            "- no global large-grid search performed.",
            "- no legacy TS3 recovery attempted.",
            "- no manual point picking outside defined rules.",
        ]
    )
    (out_dir / "RTSS2026_GSP416_V4_LOCAL_REFINE_MASTER_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "vulnerable_buckets": [vulnerable1, vulnerable2],
                "n_candidates": len(candidates),
                "selected_primary": (pick_primary["candidate_id"] if pick_primary else None),
                "selected_low_fallback_local": (pick_low_fb["candidate_id"] if pick_low_fb else None),
                "selected_low_rear_local": (pick_low_rear["candidate_id"] if pick_low_rear else None),
                "has_v2_low_fallback": bool(v2_low_rows is not None),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
