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
PROVENANCE_V3 = "regenerated_from_reconstructed_416_scores_and_archived_v3_stronger_family_rule"

POINT_V3_PRIMARY = "GSP416_V3_PRIMARY"
POINT_V3_LOW_FB_PLUS = "GSP416_V3_LOW_FALLBACK_PLUS"
POINT_V3_LOW_REAR_PLUS = "GSP416_V3_LOW_REAR_PLUS"
POINT_V2_LOW_FB = "V2_GSP416_LOW_FALLBACK"
POINT_V2_BAL = "V2_GSP416_BALANCED"
POINT_V2_LOW_REAR = "V2_GSP416_LOW_REAR"

BASE_ONLY = "BASE_ONLY"
DET_FUSION = "DETERMINISTIC_FUSION"
OLD_GSP = "OLD_GSP416_CANONICAL_C05601"

ANCHOR_BASE_UTILITY = 0.0571
ANCHOR_DET_REAR = 0.2000
ANCHOR_DET_AUTO = 0.6563
ANCHOR_V2_LOWFB_FALLBACK = 0.007212
ANCHOR_V2_LOWFB_REAR = 0.151724
ANCHOR_V2_LOWFB_AUTO = 0.649038
ANCHOR_V2_LOWFB_UTILITY = 0.081651
BUCKET_KEYS = [
    "day+intersection",
    "day+straight_road",
    "night+intersection",
    "night+straight_road",
    "other",
]


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
class SweepParamsV3:
    family_name: str
    theta_rear_hold: float
    theta_margin_hold: float
    theta_nonrear_boost: float
    theta_margin_boost: float
    theta_rear_soft: float
    bucket_config_id: str
    bucket_cfg: Dict[str, Dict[str, float]]
    conflict_subtype_mode: str
    fallback_rule: str
    confidence_weak_thr: float
    candidate_id: str


def canonical_bucket(raw_bucket: str) -> str:
    s = (raw_bucket or "").strip().lower()
    s = s.replace(" ", "_")
    if s in {"day+straight_road", "day+straightroad", "day+straight"}:
        return "day+straight_road"
    if s in {"day+intersection"}:
        return "day+intersection"
    if s in {"night+intersection"}:
        return "night+intersection"
    if s in {"night+straight_road", "night+straightroad", "night+straight"}:
        return "night+straight_road"
    return "other"


def build_bucket_cfg(bucket_config_id: str, tr: float, tn: float, tm: float) -> Dict[str, Dict[str, float]]:
    # small, explainable discrete bucket-aware presets
    if bucket_config_id == "NA":
        return {k: {"theta_rear_hold": tr, "theta_nonrear_boost": tn, "theta_margin_boost": tm} for k in BUCKET_KEYS}
    cfg = {k: {"theta_rear_hold": tr, "theta_nonrear_boost": tn, "theta_margin_boost": tm} for k in BUCKET_KEYS}
    # B1: harder night boost, tighter rear hold at intersections
    if bucket_config_id == "B1":
        cfg["night+intersection"]["theta_nonrear_boost"] = min(0.99, tn + 0.05)
        cfg["night+straight_road"]["theta_nonrear_boost"] = min(0.99, tn + 0.05)
        cfg["day+intersection"]["theta_rear_hold"] = min(0.8, tr + 0.1)
        cfg["night+intersection"]["theta_rear_hold"] = min(0.8, tr + 0.1)
    # B2: safer in intersections via larger margin
    elif bucket_config_id == "B2":
        cfg["day+intersection"]["theta_margin_boost"] = min(0.6, tm + 0.1)
        cfg["night+intersection"]["theta_margin_boost"] = min(0.6, tm + 0.1)
        cfg["other"]["theta_nonrear_boost"] = min(0.99, tn + 0.05)
    # B3: straight-road allows easier boost, night keeps strict
    elif bucket_config_id == "B3":
        cfg["day+straight_road"]["theta_nonrear_boost"] = max(0.7, tn - 0.1)
        cfg["day+straight_road"]["theta_margin_boost"] = max(-0.2, tm - 0.1)
        cfg["night+straight_road"]["theta_nonrear_boost"] = min(0.99, tn + 0.05)
    return cfg


def conflict_formula_text(mode: str) -> str:
    if mode == "OFF":
        return "subtype switches off; family default conflict only"
    return "subtype switches on; rear_to_nonrear/nonrear_to_rear/lane_turn/same_pred_weak distinguished"


def fallback_formula_text(rule: str) -> str:
    if rule == "A":
        return "defer unresolved rear_tension only"
    if rule == "B":
        return "defer all unresolved disagreement"
    if rule == "C":
        return "defer rear_tension + lane/turn conflict"
    if rule == "D":
        return "keep same-pred weak; defer cross-class conflict only"
    if rule == "E":
        return "bucket-aware defer policy"
    if rule == "F":
        return "stage2-only defer (minimal defer semantics)"
    raise ValueError(f"unknown fallback rule {rule}")


def classify_subtype(
    baseline_pred: str,
    fusion_pred: str,
    same_pred_weak: bool,
) -> str:
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


def bucket_thresholds(row: Dict[str, Any], p: SweepParamsV3) -> Tuple[float, float, float]:
    b = canonical_bucket(str(row.get("bucket_id", "")))
    cfg = p.bucket_cfg.get(b, p.bucket_cfg["other"])
    return cfg["theta_rear_hold"], cfg["theta_nonrear_boost"], cfg["theta_margin_boost"]


def decide_for_row_v3(row: Dict[str, Any], p: SweepParamsV3) -> Dict[str, Any]:
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

    theta_rear_hold, theta_nonrear_boost, theta_margin_boost = bucket_thresholds(row, p)
    theta_margin_hold = p.theta_margin_hold

    same_pred_weak = (baseline_pred == fusion_pred) and (max(baseline_score_rear, fusion_nonrear_score) < p.confidence_weak_thr)
    rear_tension = baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}
    nonrear_to_rear = baseline_pred in {LABEL_LANE, LABEL_TURN} and fusion_pred == LABEL_REAR
    lane_turn_swap = (baseline_pred == LABEL_LANE and fusion_pred == LABEL_TURN) or (baseline_pred == LABEL_TURN and fusion_pred == LABEL_LANE)
    subtype = classify_subtype(baseline_pred, fusion_pred, same_pred_weak)

    # Stage1 keep-priority / rear-hold semantics
    keep_stage1 = False
    if baseline_pred == LABEL_REAR and baseline_score_rear >= theta_rear_hold:
        keep_stage1 = True
    if rear_tension and margin < theta_margin_hold:
        keep_stage1 = True
    if same_pred_weak:
        keep_stage1 = True
    # F5 refinement: moderate rear keep
    if p.family_name == "F5" and rear_tension and baseline_score_rear >= p.theta_rear_soft:
        keep_stage1 = True
    # F2 stronger rear-priority hold
    if p.family_name == "F2" and rear_tension and baseline_score_rear >= p.theta_rear_soft:
        keep_stage1 = True

    # Stage2 boost gate
    boost_gate = fusion_nonrear_score >= theta_nonrear_boost and margin >= theta_margin_boost
    # F5 refinement: very strong nonrear and very low rear allows boost
    if p.family_name == "F5" and rear_tension and fusion_nonrear_score >= min(0.99, theta_nonrear_boost + 0.02) and baseline_score_rear < p.theta_rear_soft:
        boost_gate = True
    # F2 stricter nonrear evidence under rear tension
    if p.family_name == "F2" and rear_tension:
        boost_gate = boost_gate and (fusion_nonrear_score >= max(theta_nonrear_boost, 0.95))

    unresolved = not boost_gate
    disagreement = baseline_pred != fusion_pred

    # conflict subtype switch can narrow/expand conflict recognition
    if p.conflict_subtype_mode == "OFF":
        conflict_flag = disagreement
    else:
        conflict_flag = disagreement or same_pred_weak

    # fallback / defer semantics
    defer_flag = False
    if p.fallback_rule == "A":
        defer_flag = rear_tension and unresolved
    elif p.fallback_rule == "B":
        defer_flag = disagreement and unresolved
    elif p.fallback_rule == "C":
        defer_flag = (rear_tension and unresolved) or lane_turn_swap
    elif p.fallback_rule == "D":
        defer_flag = disagreement and (subtype != "same_pred_low_conf") and unresolved
    elif p.fallback_rule == "E":
        # bucket-aware defer: tighter at intersections/night
        b = canonical_bucket(str(row.get("bucket_id", "")))
        if b in {"night+intersection", "day+intersection"}:
            defer_flag = disagreement and unresolved
        else:
            defer_flag = rear_tension and unresolved
    elif p.fallback_rule == "F":
        defer_flag = conflict_flag and unresolved and (not keep_stage1)
    else:
        raise ValueError(f"unknown fallback rule {p.fallback_rule}")

    # family F4: disagreement subtype aware adjustments
    if p.family_name == "F4":
        if subtype in {"lane_to_turn", "turn_to_lane"} and fusion_nonrear_score >= theta_nonrear_boost:
            defer_flag = False
        if subtype == "nonrear_to_rear" and fusion_score_rear >= theta_nonrear_boost:
            defer_flag = False
        if subtype == "rear_to_nonrear" and unresolved:
            defer_flag = True

    # final routing
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


def run_policy_v3(rows: List[Dict[str, Any]], p: SweepParamsV3, policy_name: str) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        d = decide_for_row_v3(r, p)
        d["policy_name"] = policy_name
        out.append(d)
    return out


def build_base_and_det(rows: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    base_rows = []
    det_rows = []
    for r in rows:
        rr = dict(r)
        rr["action"] = "KEEP_BASELINE"
        rr["final_pred"] = str(r.get("baseline_pred", "")).strip()
        rr["policy_name"] = BASE_ONLY
        base_rows.append(rr)

        rd = dict(r)
        rd["action"] = "FUSION_BOOST"
        rd["final_pred"] = str(r.get("fusion_pred", "")).strip()
        rd["policy_name"] = DET_FUSION
        det_rows.append(rd)
    return base_rows, det_rows


def v3_predicate_formula(p: SweepParamsV3) -> str:
    return (
        f"family={p.family_name}; "
        f"stage1_keep=(rear>=theta_rear_hold OR rear_tension&margin<theta_margin_hold OR same_pred_weak); "
        f"stage2_boost=(fusion_nonrear>=theta_nonrear_boost & margin>=theta_margin_boost); "
        f"fallback_rule={p.fallback_rule}; conflict_subtype_mode={p.conflict_subtype_mode}; "
        f"bucket_config_id={p.bucket_config_id}; "
        f"theta_rear_hold={p.theta_rear_hold}; theta_margin_hold={p.theta_margin_hold}; "
        f"theta_nonrear_boost={p.theta_nonrear_boost}; theta_margin_boost={p.theta_margin_boost}; "
        f"theta_rear_soft={p.theta_rear_soft}; confidence_weak_thr={p.confidence_weak_thr}"
    )


def sweep_surface_v3(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tr_grid = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    tm_hold_grid = [-0.2, -0.1, 0.0, 0.1, 0.2, 0.3]
    tn_grid = [0.7, 0.8, 0.9, 0.95, 0.98, 0.99]
    tm_boost_grid = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6]
    tr_soft_grid = [0.2, 0.3, 0.4, 0.5, 0.6]

    families = ["F1", "F2", "F5"]  # first pass main search
    # promising region pass
    families_promising = ["F3", "F4"]

    fallback_rules_main = ["A", "B", "D", "F"]
    fallback_rules_promising = ["C", "E"]
    subtype_modes = ["OFF", "ON"]
    bucket_config_main = ["NA"]
    bucket_config_promising = ["NA", "B1", "B2", "B3"]

    candidates: List[Dict[str, Any]] = []
    cid = 1

    def emit(family_name: str, tr: float, tmh: float, tn: float, tmb: float, trs: float, subtype: str, fr: str, bcfg: str, conf_thr: float) -> None:
        nonlocal cid
        p = SweepParamsV3(
            family_name=family_name,
            theta_rear_hold=tr,
            theta_margin_hold=tmh,
            theta_nonrear_boost=tn,
            theta_margin_boost=tmb,
            theta_rear_soft=trs,
            bucket_config_id=bcfg,
            bucket_cfg=build_bucket_cfg(bcfg, tr, tn, tmb),
            conflict_subtype_mode=subtype,
            fallback_rule=fr,
            confidence_weak_thr=conf_thr,
            candidate_id=f"C{cid:05d}",
        )
        pol = run_policy_v3(rows, p, policy_name=f"GSP416_V3_CANDIDATE_{cid:05d}")
        m = compute_metrics(pol, pred_key="final_pred", action_key="action")
        pred_formula = v3_predicate_formula(p)
        candidates.append(
            {
                "candidate_id": p.candidate_id,
                "family_name": p.family_name,
                "theta_rear_hold": p.theta_rear_hold,
                "theta_margin_hold": p.theta_margin_hold,
                "theta_nonrear_boost": p.theta_nonrear_boost,
                "theta_margin_boost": p.theta_margin_boost,
                "theta_rear_soft": p.theta_rear_soft,
                "bucket_config_id": p.bucket_config_id,
                "conflict_subtype_mode": p.conflict_subtype_mode,
                "fallback_rule": p.fallback_rule,
                "N": m["N"],
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
                "predicate_formula": pred_formula,
                "delta_rear_vs_det": ANCHOR_DET_REAR - m["rear_risk"],
                "delta_util_vs_base": m["utility"] - ANCHOR_BASE_UTILITY,
                "delta_util_vs_v2low": m["utility"] - ANCHOR_V2_LOWFB_UTILITY,
                "delta_rear_vs_v2low": ANCHOR_V2_LOWFB_REAR - m["rear_risk"],
            }
        )
        cid += 1

    # Main search (controlled size, explainable)
    for fam in families:
        for tr in tr_grid:
            for tmh in tm_hold_grid:
                for tn in tn_grid:
                    for tmb in tm_boost_grid:
                        for trs in tr_soft_grid:
                            for subtype in subtype_modes:
                                for fr in fallback_rules_main:
                                    emit(fam, tr, tmh, tn, tmb, trs, subtype, fr, "NA", 0.6)

    # Promising region selection from main search
    main_feasible = [
        c for c in candidates
        if c["fallback_rate"] <= 0.06
        and c["rear_risk"] <= 0.17
        and c["utility"] >= 0.065
        and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    # If empty, fallback to top utility-risk blend from all
    if main_feasible:
        top_promising = sorted(main_feasible, key=lambda x: (x["rear_risk"], -x["utility"], x["fallback_rate"]))[:200]
    else:
        top_promising = sorted(candidates, key=lambda x: (x["rear_risk"] - x["utility"], x["fallback_rate"]))[:200]

    # Derive reduced sets for local expansion
    tr_set = sorted({float(c["theta_rear_hold"]) for c in top_promising})[:4]
    tmh_set = sorted({float(c["theta_margin_hold"]) for c in top_promising})[:4]
    tn_set = sorted({float(c["theta_nonrear_boost"]) for c in top_promising})[:4]
    tmb_set = sorted({float(c["theta_margin_boost"]) for c in top_promising})[:4]
    trs_set = sorted({float(c["theta_rear_soft"]) for c in top_promising})[:4]
    if not tr_set:
        tr_set = [0.4, 0.5, 0.6, 0.7]
        tmh_set = [-0.1, 0.0, 0.1, 0.2]
        tn_set = [0.9, 0.95, 0.98, 0.99]
        tmb_set = [0.2, 0.3, 0.4, 0.5]
        trs_set = [0.3, 0.4, 0.5, 0.6]

    # Local stronger family expansion
    for fam in families_promising:
        for tr in tr_set:
            for tmh in tmh_set:
                for tn in tn_set:
                    for tmb in tmb_set:
                        for trs in trs_set:
                            for subtype in ["ON"]:
                                for fr in fallback_rules_promising:
                                    for bcfg in bucket_config_promising:
                                        emit(fam, tr, tmh, tn, tmb, trs, subtype, fr, bcfg, 0.6)

    return candidates


def select_v3_primary(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c for c in candidates
        if c["fallback_rate"] <= 0.03
        and c["rear_risk"] <= 0.14
        and c["utility"] >= 0.070
        and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    if not feasible:
        return [], None
    ranked = sorted(
        feasible,
        key=lambda c: (-(c["delta_rear_vs_det"] + c["delta_util_vs_base"]), c["fallback_rate"], c["auto_error"], c["candidate_id"]),
    )
    return ranked, ranked[0]


def select_v3_low_fallback_plus(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c for c in candidates
        if c["fallback_rate"] <= 0.02
        and c["utility"] >= 0.075
        and c["rear_risk"] < ANCHOR_V2_LOWFB_REAR
        and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    if not feasible:
        return [], None
    ranked = sorted(
        feasible,
        key=lambda c: (c["fallback_rate"], c["rear_risk"], -c["utility"], c["candidate_id"]),
    )
    return ranked, ranked[0]


def select_v3_low_rear_plus(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c for c in candidates
        if c["rear_risk"] <= 0.10
        and c["fallback_rate"] <= 0.20
        and c["utility"] >= 0.055
        and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    if not feasible:
        return [], None
    ranked = sorted(
        feasible,
        key=lambda c: (c["rear_risk"], -c["utility"], c["fallback_rate"], c["candidate_id"]),
    )
    return ranked, ranked[0]


def select_surface_representatives(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    feasible = [c for c in candidates if c["utility"] > ANCHOR_BASE_UTILITY and c["rear_risk"] < ANCHOR_DET_REAR and c["auto_error"] <= ANCHOR_DET_AUTO]
    if not feasible:
        return []
    low_fb = sorted(feasible, key=lambda c: (c["fallback_rate"], c["rear_risk"], -c["utility"]))[0]
    low_rear = sorted(feasible, key=lambda c: (c["rear_risk"], c["fallback_rate"], -c["utility"]))[0]
    balanced = sorted(feasible, key=lambda c: (abs(c["fallback_rate"] - 0.05), abs(c["rear_risk"] - 0.12), -c["utility"]))[0]
    out = []
    for role, c in [("low_fallback_rep", low_fb), ("balanced_rep", balanced), ("low_rear_rep", low_rear)]:
        r = dict(c)
        r["surface_role"] = role
        out.append(r)
    return out


def candidate_to_params_v3(c: Dict[str, Any]) -> SweepParamsV3:
    tr = float(c["theta_rear_hold"])
    tn = float(c["theta_nonrear_boost"])
    tmb = float(c["theta_margin_boost"])
    bcfg = str(c["bucket_config_id"])
    return SweepParamsV3(
        family_name=str(c["family_name"]),
        theta_rear_hold=tr,
        theta_margin_hold=float(c["theta_margin_hold"]),
        theta_nonrear_boost=tn,
        theta_margin_boost=tmb,
        theta_rear_soft=float(c["theta_rear_soft"]),
        bucket_config_id=bcfg,
        bucket_cfg=build_bucket_cfg(bcfg, tr, tn, tmb),
        conflict_subtype_mode=str(c["conflict_subtype_mode"]),
        fallback_rule=str(c["fallback_rule"]),
        confidence_weak_thr=0.6,
        candidate_id=str(c["candidate_id"]),
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
                "predicate_formula": predicate_formula,
            }
        )
    return out


def write_policy_file(path: Path, point_name: str, params: SweepParamsV3) -> None:
    lines = [
        "# Auto-generated V3 policy description (reproducible parameters).",
        f"POINT_NAME = '{point_name}'",
        f"FAMILY_NAME = '{params.family_name}'",
        f"THETA_REAR_HOLD = {params.theta_rear_hold}",
        f"THETA_MARGIN_HOLD = {params.theta_margin_hold}",
        f"THETA_NONREAR_BOOST = {params.theta_nonrear_boost}",
        f"THETA_MARGIN_BOOST = {params.theta_margin_boost}",
        f"THETA_REAR_SOFT = {params.theta_rear_soft}",
        f"BUCKET_CONFIG_ID = '{params.bucket_config_id}'",
        f"CONFLICT_SUBTYPE_MODE = '{params.conflict_subtype_mode}'",
        f"FALLBACK_RULE = '{params.fallback_rule}'",
        f"CONFIDENCE_WEAK_THR = {params.confidence_weak_thr}",
        "",
        "# provenance",
        f"PROVENANCE = '{PROVENANCE_V3}'",
        "",
        "# Refer to backend/scripts/rtss2026_build_gsp416_canonical_v3_stronger_family.py",
        "# function decide_for_row_v3 for exact predicate execution order.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def queue_sim(actions: List[str], arrival_rate: float, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    queue = 0
    q_hist = []
    defer_count = 0
    total_samples = 0
    idx = 0
    n = len(actions)
    for _t in range(duration_sec):
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


def burst_rate(t: int, pattern: str) -> float:
    if pattern == "Constant":
        return 10.0
    if pattern == "Periodic burst":
        if (t % 30) < 5:
            return 50.0
        return 10.0
    if pattern == "Heavy burst":
        if (t % 60) < 10:
            return 100.0
        return 10.0
    return 10.0


def burst_sim(actions: List[str], pattern: str, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    queue = 0
    q_hist = []
    defer_count = 0
    total_samples = 0
    idx = 0
    n = len(actions)
    for t in range(duration_sec):
        lam = burst_rate(t, pattern)
        arrivals = int(round(lam))
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
    arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    stab = "UNSTABLE" if arr[-1] > 200 or np.max(arr) > 300 else ("BORDERLINE" if arr[-1] > 50 else "STABLE")
    return {
        "pattern": pattern,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total_samples,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "max_queue_length": int(np.max(arr)),
        "mean_queue_length": float(np.mean(arr)),
        "p95_queue_length": float(np.quantile(arr, 0.95, method="linear")),
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
        out.append(
            {
                "left_out_unit": g,
                "group_field": group_field,
                **m,
            }
        )
    return out


def bucket_metrics(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    buckets = sorted({str(r.get("bucket_id", "")).strip() for r in rows})
    out = []
    for b in buckets:
        sub = [r for r in rows if str(r.get("bucket_id", "")).strip() == b]
        m = compute_metrics(sub, pred_key="final_pred", action_key="action")
        out.append({"bucket_id": b, **m})
    return out


def load_v2_trace(path: Path, fallback_name: str) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    rows = read_csv(path)
    for r in rows:
        r["policy_name"] = fallback_name
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GSP416 canonical v3 stronger-family operating points.")
    parser.add_argument("--base_table", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--duration_sec", type=int, default=300)
    parser.add_argument("--bootstrap_B", type=int, default=5000)
    parser.add_argument(
        "--v2_low_fallback_trace",
        type=str,
        default="",
    )
    parser.add_argument(
        "--v2_balanced_trace",
        type=str,
        default="",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_rows_raw = read_csv(Path(args.base_table))
    base_rows, det_rows = build_base_and_det(base_rows_raw)
    m_base = compute_metrics(base_rows, pred_key="final_pred", action_key="action")
    m_det = compute_metrics(det_rows, pred_key="final_pred", action_key="action")

    # 1) Sweep V3 stronger family
    candidates = sweep_surface_v3(base_rows_raw)
    write_csv(
        out_dir / "01_v3_sweep_candidates.csv",
        candidates,
        [
            "candidate_id",
            "family_name",
            "theta_rear_hold",
            "theta_margin_hold",
            "theta_nonrear_boost",
            "theta_margin_boost",
            "theta_rear_soft",
            "bucket_config_id",
            "conflict_subtype_mode",
            "fallback_rule",
            "N",
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
            "delta_rear_vs_det",
            "delta_util_vs_base",
            "delta_util_vs_v2low",
            "delta_rear_vs_v2low",
        ],
    )

    # 2) Selection sets
    feas_primary, pick_primary = select_v3_primary(candidates)
    feas_lowfb, pick_lowfb = select_v3_low_fallback_plus(candidates)
    feas_lowrear, pick_lowrear = select_v3_low_rear_plus(candidates)
    surface_reps = select_surface_representatives(candidates)

    write_csv(out_dir / "02_v3_feasible_primary.csv", feas_primary, list(candidates[0].keys()) if candidates else [])
    write_csv(out_dir / "03_v3_feasible_low_fallback_plus.csv", feas_lowfb, list(candidates[0].keys()) if candidates else [])
    write_csv(out_dir / "04_v3_feasible_low_rear_plus.csv", feas_lowrear, list(candidates[0].keys()) if candidates else [])
    write_csv(out_dir / "05_v3_surface_representatives.csv", surface_reps, list(surface_reps[0].keys()) if surface_reps else ["surface_role"])

    # 3) selected summary md
    sel_md = [
        "# 06 V3 Selected Points",
        "",
        "## Anchors",
        f"- BASE_ONLY: rear_risk={m_base['rear_risk']:.6f}, auto_error={m_base['auto_error']:.6f}, utility={m_base['utility']:.6f}",
        f"- DETERMINISTIC_FUSION: rear_risk={m_det['rear_risk']:.6f}, auto_error={m_det['auto_error']:.6f}, utility={m_det['utility']:.6f}",
        f"- V2 LOW_FALLBACK ref: fallback={ANCHOR_V2_LOWFB_FALLBACK:.6f}, rear_risk={ANCHOR_V2_LOWFB_REAR:.6f}, auto_error={ANCHOR_V2_LOWFB_AUTO:.6f}, utility={ANCHOR_V2_LOWFB_UTILITY:.6f}",
        "",
        "## Picks",
    ]
    for nm, pk in [
        (POINT_V3_PRIMARY, pick_primary),
        (POINT_V3_LOW_FB_PLUS, pick_lowfb),
        (POINT_V3_LOW_REAR_PLUS, pick_lowrear),
    ]:
        if pk is None:
            sel_md.append(f"- {nm}: NONE")
        else:
            sel_md.append(
                f"- {nm}: {pk['candidate_id']} | family={pk['family_name']} | fallback={pk['fallback_rate']:.6f}, rear_risk={pk['rear_risk']:.6f}, auto_error={pk['auto_error']:.6f}, utility={pk['utility']:.6f}"
            )
    sel_md.append("")
    sel_md.append("## Surface representatives")
    if not surface_reps:
        sel_md.append("- NONE")
    else:
        for r in surface_reps:
            sel_md.append(
                f"- {r['surface_role']}: {r['candidate_id']} | family={r['family_name']} | fallback={r['fallback_rate']:.6f}, rear_risk={r['rear_risk']:.6f}, utility={r['utility']:.6f}"
            )
    (out_dir / "06_v3_selected_points.md").write_text("\n".join(sel_md), encoding="utf-8")

    # 4) materialize selected traces and policy files
    selected_map: Dict[str, List[Dict[str, Any]]] = {
        BASE_ONLY: base_rows,
        DET_FUSION: det_rows,
    }
    selected_info: Dict[str, Dict[str, Any]] = {}

    def materialize_pick(point_name: str, pick: Optional[Dict[str, Any]]) -> None:
        if pick is None:
            return
        p = candidate_to_params_v3(pick)
        policy_rows = run_policy_v3(base_rows_raw, p, policy_name=point_name)
        trace_rows = to_trace_rows(policy_rows, point_name=point_name, predicate_formula=str(pick["predicate_formula"]))
        write_csv(
            out_dir / f"{point_name}_action_trace.csv",
            trace_rows,
            list(trace_rows[0].keys()) if trace_rows else [],
        )
        write_policy_file(out_dir / f"{point_name}_policy.py", point_name, p)
        m = compute_metrics(policy_rows, pred_key="final_pred", action_key="action")
        mlines = [
            f"# {point_name} Metrics",
            "",
            f"- provenance: {PROVENANCE_V3}",
            f"- family_name: {pick['family_name']}",
            f"- candidate_id: {pick['candidate_id']}",
            f"- fallback_rate: {m['fallback_rate']:.6f}",
            f"- rear_risk: {m['rear_risk']:.6f}",
            f"- auto_error: {m['auto_error']:.6f}",
            f"- utility: {m['utility']:.6f}",
            f"- lane_recall: {m['lane_recall']:.6f}",
            f"- turn_recall: {m['turn_recall']:.6f}",
            f"- auto_coverage: {m['auto_coverage']:.6f}",
            f"- predicate_formula: {pick['predicate_formula']}",
        ]
        (out_dir / f"{point_name}_metrics.md").write_text("\n".join(mlines), encoding="utf-8")
        selected_map[point_name] = policy_rows
        selected_info[point_name] = pick

    materialize_pick(POINT_V3_PRIMARY, pick_primary)
    materialize_pick(POINT_V3_LOW_FB_PLUS, pick_lowfb)
    materialize_pick(POINT_V3_LOW_REAR_PLUS, pick_lowrear)

    # 5) load V2 traces for comparison in system reruns
    v2_low = load_v2_trace(Path(args.v2_low_fallback_trace), POINT_V2_LOW_FB)
    v2_bal = load_v2_trace(Path(args.v2_balanced_trace), POINT_V2_BAL)
    if v2_low:
        selected_map[POINT_V2_LOW_FB] = v2_low
    if v2_bal:
        selected_map[POINT_V2_BAL] = v2_bal

    # 6) queue stress
    queue_rows: List[Dict[str, Any]] = []
    for pname, rows in selected_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for lam in [1, 5, 10, 20, 30, 50, 100]:
            for mu in [0.1, 0.5, 1, 2, 5, 10]:
                q = queue_sim(actions, float(lam), float(mu), duration_sec=args.duration_sec)
                queue_rows.append({"policy_name": pname, **q})
    write_csv(
        out_dir / "07_v3_queue_stress_raw.csv",
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
    qsum = ["# 07 V3 Queue Stress Summary", ""]
    for pname in selected_map.keys():
        sub = [r for r in queue_rows if r["policy_name"] == pname]
        st = sum(1 for r in sub if r["stability_flag"] == "STABLE")
        bd = sum(1 for r in sub if r["stability_flag"] == "BORDERLINE")
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        qsum.append(f"- {pname}: stable/borderline/unstable={st}/{bd}/{un}")
    (out_dir / "07_v3_queue_stress_summary.md").write_text("\n".join(qsum), encoding="utf-8")

    # 7) burst stress
    burst_rows: List[Dict[str, Any]] = []
    for pname, rows in selected_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for pattern in ["Constant", "Periodic burst", "Heavy burst"]:
            for mu in [0.5, 1, 2, 5]:
                br = burst_sim(actions, pattern=pattern, service_rate=float(mu), duration_sec=args.duration_sec)
                burst_rows.append({"policy_name": pname, **br})
    write_csv(
        out_dir / "08_v3_burst_raw.csv",
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
    bsum = ["# 08 V3 Burst Summary", ""]
    for pname in selected_map.keys():
        sub = [r for r in burst_rows if r["policy_name"] == pname]
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        bsum.append(f"- {pname}: unstable={un}/{len(sub)}")
    (out_dir / "08_v3_burst_summary.md").write_text("\n".join(bsum), encoding="utf-8")

    # 8) bootstrap + LOBO + bucket
    boot_rows = []
    lobo_rows = []
    bucket_rows = []
    for i, (pname, rows) in enumerate(selected_map.items(), start=1):
        bs = bootstrap_policy_metrics(rows, B=args.bootstrap_B, seed=args.seed + i * 29)
        boot_rows.append({"policy_name": pname, **bs})
        lobo = lobo_metrics(rows, group_field="board_id")
        for r in lobo:
            lobo_rows.append({"policy_name": pname, **r})
        bkt = bucket_metrics(rows)
        for r in bkt:
            bucket_rows.append({"policy_name": pname, **r})

    write_csv(
        out_dir / "09_v3_bootstrap_summary.csv",
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
        out_dir / "09_v3_lobo_board.csv",
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
        out_dir / "09_v3_bucket_summary.csv",
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
    bslines = ["# 09 V3 Bootstrap + LOBO Summary", "", f"- bootstrap_B: {args.bootstrap_B}", ""]
    for r in boot_rows:
        bslines.append(
            f"- {r['policy_name']}: fallback={r['fallback_mean']:.6f}, rear_risk={r['rear_risk_mean']:.6f}, auto_error={r['auto_error_mean']:.6f}, utility={r['utility_mean']:.6f}"
        )
    (out_dir / "09_v3_bootstrap_lobo_summary.md").write_text("\n".join(bslines), encoding="utf-8")

    # 10) master report
    def pick_line(name: str, pick: Optional[Dict[str, Any]]) -> str:
        if pick is None:
            return f"- {name}: NONE"
        return (
            f"- {name}: {pick['candidate_id']} | family={pick['family_name']} | fallback={pick['fallback_rate']:.6f}, "
            f"rear_risk={pick['rear_risk']:.6f}, auto_error={pick['auto_error']:.6f}, utility={pick['utility']:.6f}"
        )

    best_vs_v2 = sorted(
        [c for c in candidates if c["utility"] >= 0.070 and c["fallback_rate"] <= 0.05],
        key=lambda c: (c["rear_risk"], c["fallback_rate"], -c["utility"]),
    )
    closest = best_vs_v2[0] if best_vs_v2 else None

    fam_agg: Dict[str, Dict[str, float]] = {}
    for c in candidates:
        fam = str(c["family_name"])
        if fam not in fam_agg:
            fam_agg[fam] = {"count": 0, "best_score": -1e9}
        fam_agg[fam]["count"] += 1
        score = (c["delta_rear_vs_det"] + c["delta_util_vs_base"]) - 0.2 * c["fallback_rate"]
        fam_agg[fam]["best_score"] = max(fam_agg[fam]["best_score"], score)
    fam_rank = sorted(fam_agg.items(), key=lambda kv: kv[1]["best_score"], reverse=True)

    has_primary = pick_primary is not None
    report = [
        "# RTSS2026_GSP416_CANONICAL_V3_STRONGER_FAMILY_MASTER_REPORT",
        "",
        "## 1. V3 vs V2 LOW_FALLBACK",
        f"- V3 found point better than V2 LOW_FALLBACK (rear lower with utility>=0.070 and fallback<=0.05): {bool(closest is not None and closest['rear_risk'] < ANCHOR_V2_LOWFB_REAR)}",
        "",
        "## 2. Primary target satisfaction",
        f"- target (fallback<=0.03, rear<=0.14, utility>=0.070, auto_error<=0.6563) found: {has_primary}",
        pick_line(POINT_V3_PRIMARY, pick_primary),
        "",
        "## 3. If missing, closest candidate",
    ]
    if closest is None:
        report.append("- closest candidate: NONE (no candidate with utility>=0.070 and fallback<=0.05).")
    else:
        report.append(
            f"- closest: {closest['candidate_id']} | family={closest['family_name']} | fallback={closest['fallback_rate']:.6f}, rear_risk={closest['rear_risk']:.6f}, auto_error={closest['auto_error']:.6f}, utility={closest['utility']:.6f}"
        )
        report.append(
            f"- gap to primary thresholds: dfb={max(0.0, closest['fallback_rate']-0.03):.6f}, drr={max(0.0, closest['rear_risk']-0.14):.6f}, dut={max(0.0, 0.070-closest['utility']):.6f}, dae={max(0.0, closest['auto_error']-0.6563):.6f}"
        )
    report.extend(
        [
            "",
            "## 4. Family promise ranking",
        ]
    )
    for fam, v in fam_rank:
        report.append(f"- {fam}: best_score={v['best_score']:.6f}, candidate_count={int(v['count'])}")
    report.extend(
        [
            "",
            "## 5. Bucket-aware effect",
        ]
    )
    # simple bucket-aware gain summary
    na_best = max((c["delta_rear_vs_det"] + c["delta_util_vs_base"] for c in candidates if c["bucket_config_id"] == "NA"), default=float("-inf"))
    b_best = max((c["delta_rear_vs_det"] + c["delta_util_vs_base"] for c in candidates if c["bucket_config_id"] != "NA"), default=float("-inf"))
    report.append(f"- best objective non-bucket(NA): {na_best:.6f}")
    report.append(f"- best objective bucket-aware(B1/B2/B3): {b_best:.6f}")
    report.append(f"- bucket-aware clear gain: {b_best > na_best + 1e-9}")
    report.extend(
        [
            "",
            "## 6. Utility gain with controlled rear risk",
            f"- exists candidate with utility>baseline and rear_risk<det: {any(c['utility']>ANCHOR_BASE_UTILITY and c['rear_risk']<ANCHOR_DET_REAR for c in candidates)}",
            "",
            "## 7. Table V replacement implication",
            "- replace historical unrecoverable TS3 row with V3 reproducible selected points and surface representatives.",
            "- all V3 points are newly rebuilt reproducible guarded operating points (not old TS3).",
            "",
            "## 8. Selected points",
            pick_line(POINT_V3_PRIMARY, pick_primary),
            pick_line(POINT_V3_LOW_FB_PLUS, pick_lowfb),
            pick_line(POINT_V3_LOW_REAR_PLUS, pick_lowrear),
            "",
            "## 9. Claim boundary",
            "- can claim reproducible stronger-family operating-surface search on canonical 416 reconstructed base table.",
            "- cannot claim old TS3 recovery.",
            "- cannot claim N>=1000 generalization from this run.",
        ]
    )
    (out_dir / "RTSS2026_GSP416_CANONICAL_V3_STRONGER_FAMILY_MASTER_REPORT.md").write_text("\n".join(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "n_candidates": len(candidates),
                "selected_primary": (pick_primary["candidate_id"] if pick_primary else None),
                "selected_low_fallback_plus": (pick_lowfb["candidate_id"] if pick_lowfb else None),
                "selected_low_rear_plus": (pick_lowrear["candidate_id"] if pick_lowrear else None),
                "has_v2_low_trace": bool(v2_low is not None),
                "has_v2_bal_trace": bool(v2_bal is not None),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
