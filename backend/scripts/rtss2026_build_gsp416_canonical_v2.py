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

PROVENANCE_V2 = "regenerated_from_reconstructed_416_scores_and_archived_v2_selection_rule"

POINT_LOW_FALLBACK = "GSP416_LOW_FALLBACK"
POINT_BALANCED = "GSP416_BALANCED"
POINT_LOW_REAR = "GSP416_LOW_REAR"

BASE_ONLY = "BASE_ONLY"
DET_FUSION = "DETERMINISTIC_FUSION"
OLD_GSP = "OLD_GSP416_CANONICAL_C05601"


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


def bool_str(v: bool) -> str:
    return "True" if v else "False"


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
    lane_support_auto = sum(1 for i in range(n) if gt[i] == LABEL_LANE and act[i] != "DEFER")
    turn_support_auto = sum(1 for i in range(n) if gt[i] == LABEL_TURN and act[i] != "DEFER")

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
        "lane_support_auto": lane_support_auto,
        "turn_support_auto": turn_support_auto,
    }


@dataclass
class SweepParams:
    theta_rear: float
    theta_nonrear: float
    theta_margin: float
    conflict_mode: str
    fallback_rule: str


def conflict_formula_text(mode: str) -> str:
    if mode == "A":
        return "baseline_pred != fusion_pred"
    if mode == "B":
        return "baseline_pred == rear_end and fusion_pred != rear_end"
    if mode == "C":
        return "baseline_pred != fusion_pred OR margin_nonrear_minus_rear < theta_margin"
    if mode == "D":
        return "baseline_pred == rear_end and fusion_pred in {lane_change, turn_conflict}"
    if mode == "E":
        return "baseline_pred == rear_end and fusion_nonrear_score > fusion_score_rear"
    if mode == "F":
        return "baseline_pred == rear_end and fusion_pred != rear_end and baseline_score_rear < theta_rear"
    if mode == "G":
        return "baseline_pred != fusion_pred and fusion_nonrear_score < theta_nonrear"
    raise ValueError(f"unknown conflict mode {mode}")


def fallback_formula_text(rule: str) -> str:
    if rule == "A":
        return "defer if uncertain_conflict_only(conflict and (fusion_nonrear_score < theta_nonrear or margin < theta_margin))"
    if rule == "B":
        return "defer if conflict and not boost_gate"
    if rule == "C":
        return "defer if rear_priority_tension and not rear_guard"
    if rule == "D":
        return "defer if conflict and not rear_guard and not boost_gate"
    if rule == "E":
        return "defer rear->nonrear conflict unless (fusion_nonrear_score>=theta_nonrear and margin>=theta_margin)"
    if rule == "F":
        return "defer if conflict and margin_nonrear_minus_rear < theta_margin"
    if rule == "G":
        return "defer if baseline_pred==rear_end and fusion_pred!=rear_end and baseline_score_rear < theta_rear"
    raise ValueError(f"unknown fallback rule {rule}")


def get_conflict_flag(
    mode: str,
    baseline_pred: str,
    fusion_pred: str,
    fusion_nonrear_score: float,
    fusion_score_rear: float,
    margin: float,
    theta_margin: float,
    theta_nonrear: float,
    baseline_score_rear: float,
    theta_rear: float,
) -> bool:
    if mode == "A":
        return baseline_pred != fusion_pred
    if mode == "B":
        return baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR
    if mode == "C":
        return (baseline_pred != fusion_pred) or (margin < theta_margin)
    if mode == "D":
        return baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}
    if mode == "E":
        return baseline_pred == LABEL_REAR and fusion_nonrear_score > fusion_score_rear
    if mode == "F":
        return baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR and baseline_score_rear < theta_rear
    if mode == "G":
        return baseline_pred != fusion_pred and fusion_nonrear_score < theta_nonrear
    raise ValueError(f"unknown conflict mode {mode}")


def get_uncertain_conflict_flag(
    rule: str,
    conflict_flag: bool,
    rear_priority_tension: bool,
    rear_guard: bool,
    boost_gate: bool,
    fusion_nonrear_score: float,
    theta_nonrear: float,
    margin: float,
    theta_margin: float,
    baseline_pred: str,
    fusion_pred: str,
    baseline_score_rear: float,
    theta_rear: float,
) -> bool:
    if rule == "A":
        return conflict_flag and ((fusion_nonrear_score < theta_nonrear) or (margin < theta_margin))
    if rule == "B":
        return conflict_flag and (not boost_gate)
    if rule == "C":
        return rear_priority_tension and (not rear_guard)
    if rule == "D":
        return conflict_flag and (not rear_guard) and (not boost_gate)
    if rule == "E":
        cond = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR
        pass_rel = (fusion_nonrear_score >= theta_nonrear) and (margin >= theta_margin)
        return cond and (not pass_rel)
    if rule == "F":
        return conflict_flag and (margin < theta_margin)
    if rule == "G":
        return baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR and baseline_score_rear < theta_rear
    raise ValueError(f"unknown fallback rule {rule}")


def decide_for_row(row: Dict[str, Any], params: SweepParams) -> Dict[str, Any]:
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

    conflict_flag = get_conflict_flag(
        mode=params.conflict_mode,
        baseline_pred=baseline_pred,
        fusion_pred=fusion_pred,
        fusion_nonrear_score=fusion_nonrear_score,
        fusion_score_rear=fusion_score_rear,
        margin=margin,
        theta_margin=params.theta_margin,
        theta_nonrear=params.theta_nonrear,
        baseline_score_rear=baseline_score_rear,
        theta_rear=params.theta_rear,
    )
    rear_priority_tension = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR
    uncertain_conflict = get_uncertain_conflict_flag(
        rule=params.fallback_rule,
        conflict_flag=conflict_flag,
        rear_priority_tension=rear_priority_tension,
        rear_guard=rear_guard,
        boost_gate=boost_gate,
        fusion_nonrear_score=fusion_nonrear_score,
        theta_nonrear=params.theta_nonrear,
        margin=margin,
        theta_margin=params.theta_margin,
        baseline_pred=baseline_pred,
        fusion_pred=fusion_pred,
        baseline_score_rear=baseline_score_rear,
        theta_rear=params.theta_rear,
    )

    if rear_guard:
        action = "KEEP_BASELINE"
        final_pred = baseline_pred
    elif boost_gate:
        action = "FUSION_BOOST"
        final_pred = fusion_pred
    elif uncertain_conflict:
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
        "conflict_flag": conflict_flag,
        "uncertain_conflict_flag": uncertain_conflict,
        "rear_priority_tension_flag": rear_priority_tension,
        "fusion_nonrear_score": fusion_nonrear_score,
        "fusion_nonrear_pred": fusion_nonrear_pred,
        "margin_nonrear_minus_rear": margin,
    }


def run_policy(rows: List[Dict[str, Any]], params: SweepParams, policy_name: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = decide_for_row(r, params)
        rr = dict(r)
        rr.update(d)
        rr["policy_name"] = policy_name
        out.append(rr)
    return out


def build_base_and_det(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rb: List[Dict[str, Any]] = []
    rd: List[Dict[str, Any]] = []
    for r in rows:
        b = dict(r)
        b["policy_name"] = BASE_ONLY
        b["action"] = "KEEP_BASELINE"
        b["final_pred"] = str(r.get("baseline_pred", "")).strip()
        b["rear_guard_flag"] = False
        b["boost_gate_flag"] = False
        b["conflict_flag"] = False
        b["uncertain_conflict_flag"] = False
        b["rear_priority_tension_flag"] = False
        b["fusion_nonrear_score"] = max(safe_float(r.get("fusion_score_lane", 0.0)), safe_float(r.get("fusion_score_turn", 0.0)))
        b["fusion_nonrear_pred"] = LABEL_LANE if safe_float(r.get("fusion_score_lane", 0.0)) >= safe_float(r.get("fusion_score_turn", 0.0)) else LABEL_TURN
        rb.append(b)

        d = dict(r)
        d["policy_name"] = DET_FUSION
        d["action"] = "FUSION_BOOST"
        d["final_pred"] = str(r.get("fusion_pred", "")).strip()
        d["rear_guard_flag"] = False
        d["boost_gate_flag"] = True
        d["conflict_flag"] = str(r.get("baseline_pred", "")).strip() != str(r.get("fusion_pred", "")).strip()
        d["uncertain_conflict_flag"] = False
        d["rear_priority_tension_flag"] = str(r.get("baseline_pred", "")).strip() == LABEL_REAR and str(r.get("fusion_pred", "")).strip() != LABEL_REAR
        d["fusion_nonrear_score"] = max(safe_float(r.get("fusion_score_lane", 0.0)), safe_float(r.get("fusion_score_turn", 0.0)))
        d["fusion_nonrear_pred"] = LABEL_LANE if safe_float(r.get("fusion_score_lane", 0.0)) >= safe_float(r.get("fusion_score_turn", 0.0)) else LABEL_TURN
        rd.append(d)
    return rb, rd


def sweep_surface(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    theta_rear_grid = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    theta_nonrear_grid = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99]
    theta_margin_grid = [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6]
    conflict_modes = ["A", "B", "C", "D", "E", "F", "G"]
    fallback_rules = ["A", "B", "C", "D", "E", "F", "G"]

    out: List[Dict[str, Any]] = []
    cid = 0
    for tr in theta_rear_grid:
        for tn in theta_nonrear_grid:
            for tm in theta_margin_grid:
                for cm in conflict_modes:
                    for fr in fallback_rules:
                        cid += 1
                        params = SweepParams(
                            theta_rear=tr,
                            theta_nonrear=tn,
                            theta_margin=tm,
                            conflict_mode=cm,
                            fallback_rule=fr,
                        )
                        policy_rows = run_policy(rows, params, policy_name=f"GSP416V2_CANDIDATE_{cid:05d}")
                        m = compute_metrics(policy_rows, pred_key="final_pred", action_key="action")
                        formula = (
                            "rear_guard=(baseline_pred==rear_end and baseline_score_rear>=theta_rear); "
                            "boost_gate=(max(fusion_score_lane,fusion_score_turn)>=theta_nonrear and margin_nonrear_minus_rear>=theta_margin); "
                            f"conflict=({conflict_formula_text(cm)}); "
                            f"defer=({fallback_formula_text(fr)}); "
                            "routing: rear_guard->KEEP | boost_gate->BOOST | defer->DEFER | else KEEP"
                        )
                        out.append(
                            {
                                "candidate_id": f"C{cid:05d}",
                                "theta_rear": tr,
                                "theta_nonrear": tn,
                                "theta_margin": tm,
                                "conflict_mode": cm,
                                "fallback_rule": fr,
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
                                "predicate_formula": formula,
                            }
                        )
    return out


def select_low_fallback(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c
        for c in candidates
        if c["fallback_rate"] > 0.0
        and c["fallback_rate"] <= 0.05
        and c["rear_risk"] <= 0.18
        and c["utility"] > 0.0571
        and c["auto_error"] <= 0.6563
    ]
    feasible = sorted(
        feasible,
        key=lambda c: (-c["utility"], c["rear_risk"], c["fallback_rate"], c["candidate_id"]),
    )
    return feasible, (feasible[0] if feasible else None)


def select_balanced(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c
        for c in candidates
        if c["fallback_rate"] > 0.0
        and c["fallback_rate"] <= 0.15
        and c["rear_risk"] <= 0.15
        and c["utility"] > 0.0571
        and c["auto_error"] <= 0.6563
    ]
    feasible = sorted(
        feasible,
        key=lambda c: (c["rear_risk"], -c["utility"], c["fallback_rate"], c["auto_error"], c["candidate_id"]),
    )
    return feasible, (feasible[0] if feasible else None)


def select_low_rear(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c
        for c in candidates
        if c["fallback_rate"] <= 0.25
        and c["utility"] >= 0.0500
        and c["auto_error"] <= 0.6700
    ]
    feasible = sorted(
        feasible,
        key=lambda c: (c["rear_risk"], -c["utility"], c["fallback_rate"], c["candidate_id"]),
    )
    return feasible, (feasible[0] if feasible else None)


def candidate_to_params(c: Dict[str, Any]) -> SweepParams:
    return SweepParams(
        theta_rear=float(c["theta_rear"]),
        theta_nonrear=float(c["theta_nonrear"]),
        theta_margin=float(c["theta_margin"]),
        conflict_mode=str(c["conflict_mode"]),
        fallback_rule=str(c["fallback_rule"]),
    )


def to_trace_rows(policy_rows: List[Dict[str, Any]], point_name: str, predicate_formula: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in policy_rows:
        gt = str(r.get("gt_type", "")).strip()
        action = str(r.get("action", "")).strip()
        final_pred = str(r.get("final_pred", "")).strip()
        rr = {
            "sample_id": r.get("sample_id", ""),
            "case_id": r.get("case_id", ""),
            "board_id": r.get("board_id", ""),
            "bucket_id": r.get("bucket_id", ""),
            "source_id": r.get("source_id", ""),
            "gt_type": gt,
            "baseline_pred": r.get("baseline_pred", ""),
            "fusion_pred": r.get("fusion_pred", ""),
            "policy_name": point_name,
            "action": action,
            "final_pred": final_pred,
            "is_deferred": bool_str(action == "DEFER"),
            "is_auto": bool_str(action != "DEFER"),
            "is_rear_gt": bool_str(gt == LABEL_REAR),
            "is_lane_gt": bool_str(gt == LABEL_LANE),
            "is_turn_gt": bool_str(gt == LABEL_TURN),
            "is_rear_miss": bool_str(gt == LABEL_REAR and final_pred != LABEL_REAR),
            "is_wrong_auto": bool_str(action != "DEFER" and final_pred != gt),
            "baseline_correct": bool_str(str(r.get("baseline_pred", "")).strip() == gt),
            "fusion_correct": bool_str(str(r.get("fusion_pred", "")).strip() == gt),
            "final_correct": bool_str(final_pred == gt),
            "rear_guard_flag": bool_str(bool(r.get("rear_guard_flag", False))),
            "boost_gate_flag": bool_str(bool(r.get("boost_gate_flag", False))),
            "conflict_flag": bool_str(bool(r.get("conflict_flag", False))),
            "uncertain_conflict_flag": bool_str(bool(r.get("uncertain_conflict_flag", False))),
            "baseline_score_rear": safe_float(r.get("baseline_score_rear", 0.0)),
            "fusion_score_rear": safe_float(r.get("fusion_score_rear", 0.0)),
            "fusion_score_lane": safe_float(r.get("fusion_score_lane", 0.0)),
            "fusion_score_turn": safe_float(r.get("fusion_score_turn", 0.0)),
            "fusion_score_nonrear": safe_float(r.get("fusion_score_nonrear", 0.0)),
            "fusion_nonrear_score": safe_float(r.get("fusion_nonrear_score", 0.0)),
            "margin_nonrear_minus_rear": safe_float(r.get("margin_nonrear_minus_rear", 0.0)),
            "predicate_formula": predicate_formula,
            "provenance": PROVENANCE_V2,
        }
        out.append(rr)
    return out


def write_policy_file(path: Path, point_name: str, params: SweepParams) -> None:
    lines = [
        "#!/usr/bin/env python3",
        f'"""Reproducible policy for {point_name} (non-TS3)."""',
        "",
        "LABEL_REAR = 'rear_end'",
        "LABEL_LANE = 'lane_change'",
        "LABEL_TURN = 'turn_conflict'",
        f"THETA_REAR = {params.theta_rear}",
        f"THETA_NONREAR = {params.theta_nonrear}",
        f"THETA_MARGIN = {params.theta_margin}",
        f"CONFLICT_MODE = '{params.conflict_mode}'",
        f"FALLBACK_RULE = '{params.fallback_rule}'",
        "",
        "def decide(row):",
        "    baseline_pred = str(row['baseline_pred']).strip()",
        "    fusion_pred = str(row['fusion_pred']).strip()",
        "    baseline_score_rear = float(row['baseline_score_rear'])",
        "    fusion_score_rear = float(row['fusion_score_rear'])",
        "    fusion_score_lane = float(row['fusion_score_lane'])",
        "    fusion_score_turn = float(row['fusion_score_turn'])",
        "    fusion_nonrear_score = max(fusion_score_lane, fusion_score_turn)",
        "    margin = float(row.get('margin_nonrear_minus_rear', fusion_nonrear_score - fusion_score_rear))",
        "",
        "    rear_guard = baseline_pred == LABEL_REAR and baseline_score_rear >= THETA_REAR",
        "    boost_gate = fusion_nonrear_score >= THETA_NONREAR and margin >= THETA_MARGIN",
        "",
        "    if CONFLICT_MODE == 'A':",
        "        conflict = baseline_pred != fusion_pred",
        "    elif CONFLICT_MODE == 'B':",
        "        conflict = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR",
        "    elif CONFLICT_MODE == 'C':",
        "        conflict = (baseline_pred != fusion_pred) or (margin < THETA_MARGIN)",
        "    elif CONFLICT_MODE == 'D':",
        "        conflict = baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}",
        "    elif CONFLICT_MODE == 'E':",
        "        conflict = baseline_pred == LABEL_REAR and fusion_nonrear_score > fusion_score_rear",
        "    elif CONFLICT_MODE == 'F':",
        "        conflict = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR and baseline_score_rear < THETA_REAR",
        "    elif CONFLICT_MODE == 'G':",
        "        conflict = baseline_pred != fusion_pred and fusion_nonrear_score < THETA_NONREAR",
        "    else:",
        "        raise ValueError('unknown conflict mode')",
        "",
        "    rear_tension = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR",
        "    if FALLBACK_RULE == 'A':",
        "        uncertain_conflict = conflict and ((fusion_nonrear_score < THETA_NONREAR) or (margin < THETA_MARGIN))",
        "    elif FALLBACK_RULE == 'B':",
        "        uncertain_conflict = conflict and (not boost_gate)",
        "    elif FALLBACK_RULE == 'C':",
        "        uncertain_conflict = rear_tension and (not rear_guard)",
        "    elif FALLBACK_RULE == 'D':",
        "        uncertain_conflict = conflict and (not rear_guard) and (not boost_gate)",
        "    elif FALLBACK_RULE == 'E':",
        "        pass_rel = (fusion_nonrear_score >= THETA_NONREAR) and (margin >= THETA_MARGIN)",
        "        uncertain_conflict = rear_tension and (not pass_rel)",
        "    elif FALLBACK_RULE == 'F':",
        "        uncertain_conflict = conflict and (margin < THETA_MARGIN)",
        "    elif FALLBACK_RULE == 'G':",
        "        uncertain_conflict = baseline_pred == LABEL_REAR and fusion_pred != LABEL_REAR and baseline_score_rear < THETA_REAR",
        "    else:",
        "        raise ValueError('unknown fallback rule')",
        "",
        "    if rear_guard:",
        "        return 'KEEP_BASELINE', baseline_pred",
        "    elif boost_gate:",
        "        return 'FUSION_BOOST', fusion_pred",
        "    elif uncertain_conflict:",
        "        return 'DEFER', baseline_pred",
        "    else:",
        "        return 'KEEP_BASELINE', baseline_pred",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def queue_sim(actions: List[str], arrival_rate: float, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    q = 0
    seq = 0
    q_hist: List[int] = []
    defer_count = 0
    total = 0

    for t in range(duration_sec):
        arrivals = int(math.floor((t + 1) * arrival_rate) - math.floor(t * arrival_rate))
        services = int(math.floor((t + 1) * service_rate) - math.floor(t * service_rate))
        for _ in range(arrivals):
            a = actions[seq % len(actions)]
            seq += 1
            total += 1
            if a == "DEFER":
                q += 1
                defer_count += 1
        q -= min(q, services)
        q_hist.append(q)

    defer_rate = defer_count / total if total else 0.0
    eff = arrival_rate * defer_rate
    if eff > service_rate * 1.05:
        stability = "UNSTABLE"
    elif eff >= service_rate * 0.95:
        stability = "BORDERLINE"
    else:
        stability = "STABLE"
    arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    return {
        "arrival_rate": arrival_rate,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "effective_defer_arrival_rate": eff,
        "max_queue_length": int(np.max(arr)),
        "mean_queue_length": float(np.mean(arr)),
        "p95_queue_length": float(np.quantile(arr, 0.95, method="linear")),
        "p99_queue_length": float(np.quantile(arr, 0.99, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": stability,
    }


def burst_rate(t: int, pattern: str) -> float:
    if pattern == "Constant":
        return 10.0
    if pattern == "Periodic burst":
        return 50.0 if (t % 30) < 5 else 10.0
    if pattern == "Heavy burst":
        return 100.0 if (t % 60) < 10 else 10.0
    raise ValueError(f"unknown pattern {pattern}")


def burst_sim(actions: List[str], pattern: str, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    q = 0
    seq = 0
    q_hist: List[int] = []
    defer_count = 0
    total = 0
    for t in range(duration_sec):
        lam = burst_rate(t, pattern)
        arrivals = int(math.floor((t + 1) * lam) - math.floor(t * lam))
        services = int(math.floor((t + 1) * service_rate) - math.floor(t * service_rate))
        for _ in range(arrivals):
            a = actions[seq % len(actions)]
            seq += 1
            total += 1
            if a == "DEFER":
                q += 1
                defer_count += 1
        q -= min(q, services)
        q_hist.append(q)
    arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    stable = bool(arr[-1] <= np.quantile(arr, 0.5, method="linear")) if len(arr) else True
    if stable and np.max(arr) <= 5:
        flag = "STABLE"
    elif stable:
        flag = "BORDERLINE"
    else:
        flag = "UNSTABLE"
    return {
        "pattern": pattern,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total,
        "defer_count": defer_count,
        "defer_rate": (defer_count / total if total else 0.0),
        "max_queue_length": int(np.max(arr)),
        "mean_queue_length": float(np.mean(arr)),
        "p95_queue_length": float(np.quantile(arr, 0.95, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": flag,
    }


def bootstrap_policy_metrics(rows: List[Dict[str, Any]], B: int, seed: int) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(rows)
    gt = np.array([str(r.get("gt_type", "")).strip() for r in rows], dtype=object)
    pr = np.array([str(r.get("final_pred", "")).strip() for r in rows], dtype=object)
    ac = np.array([str(r.get("action", "")).strip() for r in rows], dtype=object)

    fb = np.zeros(B, dtype=float)
    rr = np.zeros(B, dtype=float)
    ae = np.zeros(B, dtype=float)
    ut = np.zeros(B, dtype=float)

    for i in range(B):
        idx = rng.integers(0, n, size=n)
        sub = [{"gt_type": gt[j], "final_pred": pr[j], "action": ac[j]} for j in idx]
        m = compute_metrics(sub, pred_key="final_pred", action_key="action")
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
    units = sorted({str(r.get(group_field, "")).strip() for r in rows if str(r.get(group_field, "")).strip()})
    out = []
    for u in units:
        sub = [r for r in rows if str(r.get(group_field, "")).strip() != u]
        if not sub:
            continue
        m = compute_metrics(sub, pred_key="final_pred", action_key="action")
        out.append({"left_out_unit": u, "group_field": group_field, **m})
    return out


def bucket_metrics(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets = sorted({str(r.get("bucket_id", "")).strip() for r in rows if str(r.get("bucket_id", "")).strip()})
    out = []
    for b in buckets:
        sub = [r for r in rows if str(r.get("bucket_id", "")).strip() == b]
        m = compute_metrics(sub, pred_key="final_pred", action_key="action")
        out.append({"bucket_id": b, **m})
    return out


def maybe_load_old_gsp_trace(path: Path) -> Optional[List[Dict[str, Any]]]:
    if not path.name or not path.exists() or not path.is_file():
        return None
    rows = read_csv(path)
    need = {"gt_type", "action", "final_pred", "board_id", "bucket_id"}
    if not rows:
        return None
    if not need.issubset(set(rows[0].keys())):
        return None
    for r in rows:
        r["policy_name"] = OLD_GSP
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GSP416 canonical v2 operating points.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--bootstrap_B", type=int, default=5000)
    parser.add_argument("--duration_sec", type=int, default=300)
    parser.add_argument(
        "--old_gsp_trace",
        default="",
    )
    args = parser.parse_args()

    inp = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    base_rows_raw = read_csv(inp)
    base_rows, det_rows = build_base_and_det(base_rows_raw)
    m_base = compute_metrics(base_rows, pred_key="final_pred", action_key="action")
    m_det = compute_metrics(det_rows, pred_key="final_pred", action_key="action")

    candidates = sweep_surface(base_rows_raw)
    write_csv(
        out_dir / "01_v2_sweep_candidates.csv",
        candidates,
        [
            "candidate_id",
            "theta_rear",
            "theta_nonrear",
            "theta_margin",
            "conflict_mode",
            "fallback_rule",
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
            "predicate_formula",
        ],
    )

    feasible_low_fb, pick_low_fb = select_low_fallback(candidates)
    feasible_bal, pick_bal = select_balanced(candidates)
    feasible_low_rear, pick_low_rear = select_low_rear(candidates)

    common_fields = [
        "candidate_id",
        "theta_rear",
        "theta_nonrear",
        "theta_margin",
        "conflict_mode",
        "fallback_rule",
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
        "predicate_formula",
    ]
    write_csv(out_dir / "02_v2_feasible_low_fallback.csv", feasible_low_fb, common_fields)
    write_csv(out_dir / "03_v2_feasible_balanced.csv", feasible_bal, common_fields)
    write_csv(out_dir / "04_v2_feasible_low_rear.csv", feasible_low_rear, common_fields)

    sel_md_lines = [
        "# 05 V2 Selected Points",
        "",
        "## Anchors",
        f"- BASE_ONLY: rear_risk={m_base['rear_risk']:.6f}, auto_error={m_base['auto_error']:.6f}, utility={m_base['utility']:.6f}",
        f"- DETERMINISTIC_FUSION: rear_risk={m_det['rear_risk']:.6f}, auto_error={m_det['auto_error']:.6f}, utility={m_det['utility']:.6f}",
        "",
        "## Selection Results",
    ]
    for title, pick in [
        (POINT_LOW_FALLBACK, pick_low_fb),
        (POINT_BALANCED, pick_bal),
        (POINT_LOW_REAR, pick_low_rear),
    ]:
        if pick is None:
            sel_md_lines.append(f"- {title}: NONE")
        else:
            sel_md_lines.append(
                f"- {title}: {pick['candidate_id']} | fallback={pick['fallback_rate']:.6f}, rear_risk={pick['rear_risk']:.6f}, auto_error={pick['auto_error']:.6f}, utility={pick['utility']:.6f}"
            )
    (out_dir / "05_v2_selected_points.md").write_text("\n".join(sel_md_lines), encoding="utf-8")

    # Materialize selected points
    selected_map: Dict[str, Dict[str, Any]] = {}
    trace_map: Dict[str, List[Dict[str, Any]]] = {}

    for point_name, pick in [
        (POINT_LOW_FALLBACK, pick_low_fb),
        (POINT_BALANCED, pick_bal),
        (POINT_LOW_REAR, pick_low_rear),
    ]:
        if pick is None:
            (out_dir / f"{point_name}_metrics.md").write_text(
                "\n".join(
                    [
                        f"# {point_name} Metrics",
                        "",
                        "- status: NONE (no feasible point under this category constraints).",
                        f"- provenance: {PROVENANCE_V2}",
                    ]
                ),
                encoding="utf-8",
            )
            continue

        params = candidate_to_params(pick)
        policy_rows = run_policy(base_rows_raw, params, policy_name=point_name)
        trace_rows = to_trace_rows(policy_rows, point_name=point_name, predicate_formula=str(pick["predicate_formula"]))

        write_csv(
            out_dir / f"{point_name}_action_trace.csv",
            trace_rows,
            [
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
                "predicate_formula",
                "provenance",
            ],
        )
        write_policy_file(out_dir / f"{point_name}_policy.py", point_name, params)

        m = compute_metrics(policy_rows, pred_key="final_pred", action_key="action")
        (out_dir / f"{point_name}_metrics.md").write_text(
            "\n".join(
                [
                    f"# {point_name} Metrics",
                    "",
                    f"- candidate_id: {pick['candidate_id']}",
                    f"- fallback_rate: {m['fallback_rate']:.6f}",
                    f"- rear_risk: {m['rear_risk']:.6f}",
                    f"- auto_error: {m['auto_error']:.6f}",
                    f"- utility: {m['utility']:.6f}",
                    f"- defer/boost/keep: {m['defer_count']}/{m['boost_count']}/{m['keep_count']}",
                    f"- predicate_formula: {pick['predicate_formula']}",
                    f"- provenance: {PROVENANCE_V2}",
                ]
            ),
            encoding="utf-8",
        )
        selected_map[point_name] = pick
        trace_map[point_name] = trace_rows

    # Build comparison policy set
    policy_rows_for_eval: Dict[str, List[Dict[str, Any]]] = {
        BASE_ONLY: base_rows,
        DET_FUSION: det_rows,
    }
    old_trace = maybe_load_old_gsp_trace(Path(args.old_gsp_trace))
    if old_trace is not None:
        policy_rows_for_eval[OLD_GSP] = old_trace

    for k, v in trace_map.items():
        policy_rows_for_eval[k] = v

    # Queue stress
    queue_rows: List[Dict[str, Any]] = []
    for pname, rows in policy_rows_for_eval.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for lam in [1, 5, 10, 20, 30, 50, 100]:
            for mu in [0.1, 0.5, 1, 2, 5, 10]:
                q = queue_sim(actions, float(lam), float(mu), duration_sec=args.duration_sec)
                queue_rows.append({"policy_name": pname, **q})
    write_csv(
        out_dir / "06_v2_queue_stress_raw.csv",
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
    qsum_lines = ["# 06 V2 Queue Stress Summary", "", "## Policy Summary"]
    for pname in policy_rows_for_eval.keys():
        sub = [r for r in queue_rows if r["policy_name"] == pname]
        stable = sum(1 for r in sub if r["stability_flag"] == "STABLE")
        bord = sum(1 for r in sub if r["stability_flag"] == "BORDERLINE")
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        mean_defer = float(np.mean([r["defer_rate"] for r in sub])) if sub else float("nan")
        qsum_lines.append(f"- {pname}: stable/borderline/unstable={stable}/{bord}/{un}, mean_defer_rate={mean_defer:.6f}")
    (out_dir / "06_v2_queue_stress_summary.md").write_text("\n".join(qsum_lines), encoding="utf-8")

    # Burst stress
    burst_rows: List[Dict[str, Any]] = []
    for pname, rows in policy_rows_for_eval.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for pattern in ["Constant", "Periodic burst", "Heavy burst"]:
            for mu in [0.5, 1, 2, 5]:
                br = burst_sim(actions, pattern=pattern, service_rate=float(mu), duration_sec=args.duration_sec)
                burst_rows.append({"policy_name": pname, **br})
    write_csv(
        out_dir / "07_v2_burst_raw.csv",
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
    bsum_lines = ["# 07 V2 Burst Summary", "", "## Policy Summary"]
    for pname in policy_rows_for_eval.keys():
        sub = [r for r in burst_rows if r["policy_name"] == pname]
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        mx = max((r["max_queue_length"] for r in sub), default=0)
        bsum_lines.append(f"- {pname}: unstable={un}/{len(sub)}, max_queue={mx}")
    (out_dir / "07_v2_burst_summary.md").write_text("\n".join(bsum_lines), encoding="utf-8")

    # Bootstrap + LOBO + bucket
    boot_rows = []
    lobo_rows = []
    bucket_rows = []
    for i, (pname, rows) in enumerate(policy_rows_for_eval.items(), start=1):
        bs = bootstrap_policy_metrics(rows, B=args.bootstrap_B, seed=args.seed + i * 17)
        boot_rows.append({"policy_name": pname, **bs})

        lobo = lobo_metrics(rows, group_field="board_id")
        for r in lobo:
            lobo_rows.append({"policy_name": pname, **r})

        bkt = bucket_metrics(rows)
        for r in bkt:
            bucket_rows.append({"policy_name": pname, **r})

    write_csv(
        out_dir / "08_v2_bootstrap_summary.csv",
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
        out_dir / "08_v2_lobo_board.csv",
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
            "lane_support_auto",
            "turn_support_auto",
        ],
    )
    write_csv(
        out_dir / "08_v2_bucket_summary.csv",
        bucket_rows,
        [
            "policy_name",
            "bucket_id",
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
            "lane_support_auto",
            "turn_support_auto",
        ],
    )
    bs_lines = [
        "# 08 V2 Bootstrap + LOBO Summary",
        "",
        f"- bootstrap_B: {args.bootstrap_B}",
        f"- LOBO group: board_id",
        "",
        "## Bootstrap Means",
    ]
    for r in boot_rows:
        bs_lines.append(
            f"- {r['policy_name']}: fallback={r['fallback_mean']:.6f}, rear_risk={r['rear_risk_mean']:.6f}, auto_error={r['auto_error_mean']:.6f}, utility={r['utility_mean']:.6f}"
        )
    bs_lines.append("")
    bs_lines.append("## LOBO Counts")
    for pname in policy_rows_for_eval.keys():
        n = sum(1 for r in lobo_rows if r["policy_name"] == pname)
        bs_lines.append(f"- {pname}: {n} leave-one-board-out runs")
    (out_dir / "08_v2_bootstrap_lobo_summary.md").write_text("\n".join(bs_lines), encoding="utf-8")

    # Master report
    def pick_line(pick: Optional[Dict[str, Any]], name: str) -> str:
        if pick is None:
            return f"- {name}: NONE"
        return (
            f"- {name}: {pick['candidate_id']} | fallback={pick['fallback_rate']:.6f}, "
            f"rear_risk={pick['rear_risk']:.6f}, auto_error={pick['auto_error']:.6f}, utility={pick['utility']:.6f}"
        )

    report_lines = [
        "# RTSS2026_GSP416_CANONICAL_V2_MASTER_REPORT",
        "",
        "## 1. Why previous C05601 is not main selected point",
        "- previous C05601 had fallback=0 and rear_risk very close to deterministic fusion, so it acts as low-defer diagnostic instead of bounded-automation main point.",
        "",
        "## 2. Whether GSP416_BALANCED was found",
        pick_line(pick_bal, POINT_BALANCED),
        "",
        "## 3. Balanced contract checks",
    ]
    if pick_bal is None:
        report_lines.append("- GSP416_BALANCED: NONE (no feasible candidate under balanced constraints).")
    else:
        report_lines.extend(
            [
                f"- rear_risk <= 0.15: {pick_bal['rear_risk'] <= 0.15}",
                f"- utility > 0.0571: {pick_bal['utility'] > 0.0571}",
                f"- auto_error <= 0.6563: {pick_bal['auto_error'] <= 0.6563}",
                f"- 0 < fallback_rate <= 0.15: {pick_bal['fallback_rate'] > 0 and pick_bal['fallback_rate'] <= 0.15}",
            ]
        )
    report_lines.extend(
        [
            "",
            "## 4. If balanced missing, closest candidate",
        ]
    )
    if feasible_bal:
        best_bal = feasible_bal[0]
        report_lines.append(
            f"- closest balanced-feasible candidate: {best_bal['candidate_id']} | fallback={best_bal['fallback_rate']:.6f}, rear_risk={best_bal['rear_risk']:.6f}, auto_error={best_bal['auto_error']:.6f}, utility={best_bal['utility']:.6f}"
        )
    else:
        report_lines.append("- balanced feasible set is empty; no closest balanced-feasible candidate exists.")
    report_lines.extend(
        [
            "",
            "## 5. Low-fallback and low-rear existence",
            pick_line(pick_low_fb, POINT_LOW_FALLBACK),
            pick_line(pick_low_rear, POINT_LOW_REAR),
            "",
            "## 6. Relationship to historical TS3",
            "- not old TS3, newly rebuilt reproducible guarded operating points.",
            "",
            "## 7. Table V replacement suggestion",
            "- replace historical TS3/TS2/BA2 canonical row with v2 reproducible operating-point trio: LOW_FALLBACK / BALANCED / LOW_REAR (or explicit NONE where unavailable).",
            "",
            "## 8. Comparison anchors",
            f"- BASE_ONLY: rear_risk={m_base['rear_risk']:.6f}, auto_error={m_base['auto_error']:.6f}, utility={m_base['utility']:.6f}",
            f"- DETERMINISTIC_FUSION: rear_risk={m_det['rear_risk']:.6f}, auto_error={m_det['auto_error']:.6f}, utility={m_det['utility']:.6f}",
            f"- old C05601 trace loaded: {old_trace is not None}",
            "",
            "## 9. Claim boundaries",
            "- can claim reproducible guarded operating-surface selection on reconstructed 416.",
            "- cannot claim old TS3 recovery.",
            "- cannot claim N>=1000 generalization from this run.",
        ]
    )
    (out_dir / "RTSS2026_GSP416_CANONICAL_V2_MASTER_REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "selected_low_fallback": (pick_low_fb["candidate_id"] if pick_low_fb else None),
                "selected_balanced": (pick_bal["candidate_id"] if pick_bal else None),
                "selected_low_rear": (pick_low_rear["candidate_id"] if pick_low_rear else None),
                "old_trace_loaded": bool(old_trace is not None),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

