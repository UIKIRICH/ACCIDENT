#!/usr/bin/env python3
import argparse
import csv
import importlib.util
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


LABEL_REAR = "rear_end"
LABEL_LANE = "lane_change"
LABEL_TURN = "turn_conflict"

PROVENANCE_V4 = "regenerated_from_reconstructed_416_scores_and_archived_v4_selection_rule"

POINT_PRIMARY = "GSP416_PRIMARY"
POINT_SAFE = "GSP416_SAFE"
POINT_YIELD = "GSP416_YIELD"

POINT_V2_LOW_FB = "V2_LOW_FALLBACK"
POINT_V3_CLOSEST = "V3_CLOSEST_CANDIDATE"

BASE_ONLY = "BASE_ONLY"
DET_FUSION = "DETERMINISTIC_FUSION"

ANCHOR_BASE_REAR = 0.0552
ANCHOR_BASE_AUTO = 0.6274
ANCHOR_BASE_UTILITY = 0.0571
ANCHOR_DET_REAR = 0.2000
ANCHOR_DET_AUTO = 0.6563
ANCHOR_DET_UTILITY = 0.1013
ANCHOR_V2_LOWFB_FALLBACK = 0.007212
ANCHOR_V2_LOWFB_REAR = 0.151724
ANCHOR_V2_LOWFB_AUTO = 0.649038
ANCHOR_V2_LOWFB_UTILITY = 0.081651

TR_GRID = [0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]
TRS_GRID = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]
TN_GRID = [0.6, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995]
TMH_GRID = [-0.3, -0.2, -0.1, 0.0, 0.1, 0.2, 0.3]
TMB_GRID = [-0.1, 0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.55, 0.6]

BUCKET_KEYS = [
    "day+intersection",
    "day+straight_road",
    "night+intersection",
    "night+straight_road",
    "other",
]
BOARD_KEYS = ["board36", "board72", "board96", "board102", "board110"]


@dataclass
class SweepParamsV4:
    family_name: str
    theta_rear_hold: float
    theta_rear_soft: float
    theta_nonrear_boost: float
    theta_margin_hold: float
    theta_margin_boost: float
    bucket_config_id: str
    bucket_cfg: Dict[str, Dict[str, float]]
    board_config_id: str
    board_cfg: Dict[str, Dict[str, float]]
    conflict_subtype_mode: str
    fallback_rule: str
    confidence_weak_thr: float
    candidate_id: str


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

    score_primary = (
        3.0 * (utility - ANCHOR_BASE_UTILITY)
        + 2.0 * (ANCHOR_DET_REAR - rear_risk)
        - 1.5 * fallback_rate
        - 1.0 * (auto_error - ANCHOR_BASE_AUTO)
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
        "score_primary": score_primary,
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


def one_step_tighter(grid: List[float], val: float) -> float:
    i = grid.index(val)
    return grid[min(i + 1, len(grid) - 1)]


def one_step_looser(grid: List[float], val: float) -> float:
    i = grid.index(val)
    return grid[max(i - 1, 0)]


def build_bucket_cfg(bucket_config_id: str, tr: float, trs: float, tn: float, tmh: float, tmb: float) -> Dict[str, Dict[str, float]]:
    cfg = {
        k: {
            "theta_rear_hold": tr,
            "theta_rear_soft": trs,
            "theta_nonrear_boost": tn,
            "theta_margin_hold": tmh,
            "theta_margin_boost": tmb,
        }
        for k in BUCKET_KEYS
    }
    if bucket_config_id == "BK0":
        return cfg
    if bucket_config_id == "BK1":
        for k in ["night+intersection", "night+straight_road"]:
            cfg[k]["theta_nonrear_boost"] = one_step_tighter(TN_GRID, tn)
            cfg[k]["theta_margin_boost"] = one_step_tighter(TMB_GRID, tmb)
        for k in ["day+intersection", "night+intersection"]:
            cfg[k]["theta_rear_hold"] = one_step_tighter(TR_GRID, tr)
            cfg[k]["theta_margin_hold"] = one_step_tighter(TMH_GRID, tmh)
        return cfg
    if bucket_config_id == "BK2":
        cfg["day+straight_road"]["theta_nonrear_boost"] = one_step_looser(TN_GRID, tn)
        cfg["day+straight_road"]["theta_margin_boost"] = one_step_looser(TMB_GRID, tmb)
        cfg["night+straight_road"]["theta_nonrear_boost"] = one_step_tighter(TN_GRID, tn)
        return cfg
    if bucket_config_id == "BK3":
        for k in ["day+intersection", "night+intersection"]:
            cfg[k]["theta_nonrear_boost"] = one_step_tighter(TN_GRID, tn)
            cfg[k]["theta_margin_boost"] = one_step_tighter(TMB_GRID, tmb)
            cfg[k]["theta_rear_soft"] = one_step_tighter(TRS_GRID, trs)
        return cfg
    return cfg


def build_board_cfg(board_config_id: str, tr: float, trs: float, tn: float, tmh: float, tmb: float) -> Dict[str, Dict[str, float]]:
    cfg = {
        k: {
            "theta_rear_hold": tr,
            "theta_rear_soft": trs,
            "theta_nonrear_boost": tn,
            "theta_margin_hold": tmh,
            "theta_margin_boost": tmb,
        }
        for k in BOARD_KEYS
    }
    if board_config_id == "SHARED":
        return cfg
    if board_config_id == "ALL_TIGHTER":
        for k in BOARD_KEYS:
            cfg[k]["theta_rear_hold"] = one_step_tighter(TR_GRID, tr)
            cfg[k]["theta_rear_soft"] = one_step_tighter(TRS_GRID, trs)
            cfg[k]["theta_nonrear_boost"] = one_step_tighter(TN_GRID, tn)
            cfg[k]["theta_margin_hold"] = one_step_tighter(TMH_GRID, tmh)
            cfg[k]["theta_margin_boost"] = one_step_tighter(TMB_GRID, tmb)
        return cfg
    if board_config_id == "ALL_LOOSER":
        for k in BOARD_KEYS:
            cfg[k]["theta_rear_hold"] = one_step_looser(TR_GRID, tr)
            cfg[k]["theta_rear_soft"] = one_step_looser(TRS_GRID, trs)
            cfg[k]["theta_nonrear_boost"] = one_step_looser(TN_GRID, tn)
            cfg[k]["theta_margin_hold"] = one_step_looser(TMH_GRID, tmh)
            cfg[k]["theta_margin_boost"] = one_step_looser(TMB_GRID, tmb)
        return cfg

    m = re.match(r"^(board\d+)_(TIGHTER|LOOSER)$", board_config_id)
    if not m:
        return cfg
    b, mode = m.group(1), m.group(2)
    if b not in cfg:
        return cfg
    if mode == "TIGHTER":
        cfg[b]["theta_rear_hold"] = one_step_tighter(TR_GRID, tr)
        cfg[b]["theta_rear_soft"] = one_step_tighter(TRS_GRID, trs)
        cfg[b]["theta_nonrear_boost"] = one_step_tighter(TN_GRID, tn)
        cfg[b]["theta_margin_hold"] = one_step_tighter(TMH_GRID, tmh)
        cfg[b]["theta_margin_boost"] = one_step_tighter(TMB_GRID, tmb)
    else:
        cfg[b]["theta_rear_hold"] = one_step_looser(TR_GRID, tr)
        cfg[b]["theta_rear_soft"] = one_step_looser(TRS_GRID, trs)
        cfg[b]["theta_nonrear_boost"] = one_step_looser(TN_GRID, tn)
        cfg[b]["theta_margin_hold"] = one_step_looser(TMH_GRID, tmh)
        cfg[b]["theta_margin_boost"] = one_step_looser(TMB_GRID, tmb)
    return cfg


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


def get_thresholds(row: Dict[str, Any], p: SweepParamsV4) -> Tuple[float, float, float, float, float]:
    bkt = canonical_bucket(str(row.get("bucket_id", "")))
    brd = str(row.get("board_id", "")).strip().lower()
    bc = p.bucket_cfg.get(bkt, p.bucket_cfg["other"])
    rc = p.board_cfg.get(
        brd,
        {
            "theta_rear_hold": p.theta_rear_hold,
            "theta_rear_soft": p.theta_rear_soft,
            "theta_nonrear_boost": p.theta_nonrear_boost,
            "theta_margin_hold": p.theta_margin_hold,
            "theta_margin_boost": p.theta_margin_boost,
        },
    )

    def clip(v: float, lo: float, hi: float) -> float:
        return float(max(lo, min(hi, v)))

    tr = clip((bc["theta_rear_hold"] + rc["theta_rear_hold"]) / 2.0, TR_GRID[0], TR_GRID[-1])
    trs = clip((bc["theta_rear_soft"] + rc["theta_rear_soft"]) / 2.0, TRS_GRID[0], TRS_GRID[-1])
    tn = clip((bc["theta_nonrear_boost"] + rc["theta_nonrear_boost"]) / 2.0, TN_GRID[0], TN_GRID[-1])
    tmh = clip((bc["theta_margin_hold"] + rc["theta_margin_hold"]) / 2.0, TMH_GRID[0], TMH_GRID[-1])
    tmb = clip((bc["theta_margin_boost"] + rc["theta_margin_boost"]) / 2.0, TMB_GRID[0], TMB_GRID[-1])
    return tr, trs, tn, tmh, tmb


def decide_for_row_v4(row: Dict[str, Any], p: SweepParamsV4) -> Dict[str, Any]:
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

    tr, trs, tn, tmh, tmb = get_thresholds(row, p)

    same_pred_weak = (baseline_pred == fusion_pred) and (max(baseline_score_rear, fusion_nonrear_score) < p.confidence_weak_thr)
    rear_tension = baseline_pred == LABEL_REAR and fusion_pred in {LABEL_LANE, LABEL_TURN}
    nonrear_to_rear = baseline_pred in {LABEL_LANE, LABEL_TURN} and fusion_pred == LABEL_REAR
    lane_turn_swap = (baseline_pred == LABEL_LANE and fusion_pred == LABEL_TURN) or (baseline_pred == LABEL_TURN and fusion_pred == LABEL_LANE)
    cross_class = baseline_pred != fusion_pred
    low_margin_disagreement = cross_class and (margin < tmb)

    subtype = classify_subtype(baseline_pred, fusion_pred, same_pred_weak)

    rear_guard_hard = baseline_pred == LABEL_REAR and baseline_score_rear >= tr
    rear_guard_soft = baseline_pred == LABEL_REAR and baseline_score_rear >= trs

    keep_stage1 = False
    if p.family_name in {"H1", "H3", "H4", "H6"}:
        keep_stage1 = rear_guard_hard or (rear_tension and margin < tmh) or same_pred_weak
    elif p.family_name == "H2":
        keep_stage1 = rear_guard_hard or (rear_tension and rear_guard_soft) or same_pred_weak
    elif p.family_name == "H5":
        keep_stage1 = rear_guard_hard or same_pred_weak
        if p.conflict_subtype_mode == "ON" and subtype in {"same_pred_low_conf", "nonrear_to_rear"} and fusion_score_rear < tn:
            keep_stage1 = True
    elif p.family_name == "H7":
        keep_stage1 = rear_guard_hard or (rear_tension and rear_guard_soft) or same_pred_weak

    boost_gate = fusion_nonrear_score >= tn and margin >= tmb
    if p.family_name == "H2" and rear_tension:
        boost_gate = boost_gate and (fusion_nonrear_score >= max(tn, 0.95)) and (margin >= max(tmb, 0.2))
    if p.family_name == "H7" and rear_tension:
        boost_gate = boost_gate and (baseline_score_rear < trs)

    unresolved = not boost_gate
    conflict_flag = (cross_class or same_pred_weak) if p.conflict_subtype_mode == "ON" else cross_class

    defer_flag = False
    if p.fallback_rule == "A":
        defer_flag = rear_tension and unresolved
    elif p.fallback_rule == "B":
        defer_flag = cross_class and unresolved
    elif p.fallback_rule == "C":
        defer_flag = (rear_tension and unresolved) or low_margin_disagreement
    elif p.fallback_rule == "D":
        bkt = canonical_bucket(str(row.get("bucket_id", "")))
        if bkt in {"night+intersection", "day+intersection"}:
            defer_flag = cross_class and unresolved
        else:
            defer_flag = rear_tension and unresolved
    elif p.fallback_rule == "E":
        brd = str(row.get("board_id", "")).strip().lower()
        if brd in {"board102", "board110"}:
            defer_flag = cross_class and unresolved
        else:
            defer_flag = rear_tension and unresolved
    elif p.fallback_rule == "F":
        defer_flag = (rear_tension and unresolved) or (nonrear_to_rear and fusion_score_rear < tn) or (lane_turn_swap and margin < tmb)
    elif p.fallback_rule == "G":
        defer_flag = (not keep_stage1) and conflict_flag and unresolved
    elif p.fallback_rule == "H":
        defer_flag = rear_tension and (not rear_guard_soft) and unresolved
    else:
        raise ValueError(f"unknown fallback_rule {p.fallback_rule}")

    if p.family_name == "H5" and p.conflict_subtype_mode == "ON":
        if subtype in {"lane_to_turn", "turn_to_lane"} and fusion_nonrear_score >= tn:
            defer_flag = False
        if subtype == "nonrear_to_rear" and fusion_score_rear >= tn:
            defer_flag = False
        if subtype == "rear_to_nonrear" and unresolved:
            defer_flag = True

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


def run_policy_v4(rows: List[Dict[str, Any]], p: SweepParamsV4, policy_name: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        d = decide_for_row_v4(r, p)
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


def v4_predicate_formula(p: SweepParamsV4) -> str:
    return (
        f"family={p.family_name}; "
        f"stage1=keep-priority(rear_hold OR rear_tension_hold OR same_pred_weak); "
        f"stage2=boost_if(fusion_nonrear>=theta_nonrear_boost & margin>=theta_margin_boost); "
        f"fallback_rule={p.fallback_rule}; conflict_subtype_mode={p.conflict_subtype_mode}; "
        f"bucket_config_id={p.bucket_config_id}; board_config_id={p.board_config_id}; "
        f"theta_rear_hold={p.theta_rear_hold}; theta_rear_soft={p.theta_rear_soft}; "
        f"theta_nonrear_boost={p.theta_nonrear_boost}; theta_margin_hold={p.theta_margin_hold}; theta_margin_boost={p.theta_margin_boost}; "
        f"confidence_weak_thr={p.confidence_weak_thr}"
    )


def emit_candidate(rows: List[Dict[str, Any]], p: SweepParamsV4) -> Dict[str, Any]:
    pol = run_policy_v4(rows, p, policy_name=f"GSP416_V4_CANDIDATE_{p.candidate_id}")
    m = compute_metrics(pol, pred_key="final_pred", action_key="action")
    out = {
        "candidate_id": p.candidate_id,
        "family_name": p.family_name,
        "theta_rear_hold": p.theta_rear_hold,
        "theta_rear_soft": p.theta_rear_soft,
        "theta_nonrear_boost": p.theta_nonrear_boost,
        "theta_margin_hold": p.theta_margin_hold,
        "theta_margin_boost": p.theta_margin_boost,
        "bucket_config_id": p.bucket_config_id,
        "board_config_id": p.board_config_id,
        "conflict_subtype_mode": p.conflict_subtype_mode,
        "fallback_rule": p.fallback_rule,
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
        "score_primary": m["score_primary"],
        "predicate_formula": v4_predicate_formula(p),
    }
    out["delta_rear_vs_det"] = ANCHOR_DET_REAR - out["rear_risk"]
    out["delta_util_vs_base"] = out["utility"] - ANCHOR_BASE_UTILITY
    out["delta_rear_vs_v2low"] = ANCHOR_V2_LOWFB_REAR - out["rear_risk"]
    out["delta_util_vs_v2low"] = out["utility"] - ANCHOR_V2_LOWFB_UTILITY
    return out


def sweep_surface_v4(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tr_main = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75]
    trs_main = [0.15, 0.25, 0.35, 0.45, 0.55]
    tn_main = [0.6, 0.8, 0.9, 0.95, 0.99]
    tmh_main = [-0.3, -0.1, 0.1, 0.3]
    tmb_main = [-0.1, 0.1, 0.3, 0.5, 0.6]
    main_families = ["H1", "H2", "H5", "H7"]
    main_fallback = ["A", "C", "F", "G", "H"]
    subtype_modes = ["OFF", "ON"]

    candidates: List[Dict[str, Any]] = []
    cid = 1

    def mk_params(
        fam: str,
        tr: float,
        trs: float,
        tn: float,
        tmh: float,
        tmb: float,
        bcfg: str,
        brcfg: str,
        subtype: str,
        fr: str,
    ) -> SweepParamsV4:
        return SweepParamsV4(
            family_name=fam,
            theta_rear_hold=tr,
            theta_rear_soft=trs,
            theta_nonrear_boost=tn,
            theta_margin_hold=tmh,
            theta_margin_boost=tmb,
            bucket_config_id=bcfg,
            bucket_cfg=build_bucket_cfg(bcfg, tr, trs, tn, tmh, tmb),
            board_config_id=brcfg,
            board_cfg=build_board_cfg(brcfg, tr, trs, tn, tmh, tmb),
            conflict_subtype_mode=subtype,
            fallback_rule=fr,
            confidence_weak_thr=0.6,
            candidate_id=f"C{cid:06d}",
        )

    for fam in main_families:
        for tr in tr_main:
            for trs in trs_main:
                if trs > tr:
                    continue
                for tn in tn_main:
                    for tmh in tmh_main:
                        for tmb in tmb_main:
                            for subtype in subtype_modes:
                                for fr in main_fallback:
                                    p = mk_params(fam, tr, trs, tn, tmh, tmb, "BK0", "SHARED", subtype, fr)
                                    candidates.append(emit_candidate(rows, p))
                                    cid += 1

    promising = [
        c
        for c in candidates
        if c["fallback_rate"] <= 0.08 and c["rear_risk"] <= 0.18 and c["utility"] >= 0.07 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    if promising:
        promising = sorted(promising, key=lambda x: (-x["score_primary"], x["rear_risk"], x["fallback_rate"]))[:500]
    else:
        promising = sorted(candidates, key=lambda x: (x["rear_risk"], -x["utility"], x["fallback_rate"]))[:400]

    def expand_vals(base_vals: List[float], full_grid: List[float]) -> List[float]:
        idxs = set()
        for v in base_vals:
            i = full_grid.index(v)
            idxs.add(i)
            idxs.add(max(0, i - 1))
            idxs.add(min(len(full_grid) - 1, i + 1))
        return [full_grid[i] for i in sorted(idxs)]

    tr_set = sorted({float(c["theta_rear_hold"]) for c in promising})
    trs_set = sorted({float(c["theta_rear_soft"]) for c in promising})
    tn_set = sorted({float(c["theta_nonrear_boost"]) for c in promising})
    tmh_set = sorted({float(c["theta_margin_hold"]) for c in promising})
    tmb_set = sorted({float(c["theta_margin_boost"]) for c in promising})

    tr_local = expand_vals(tr_set, TR_GRID)
    trs_local = expand_vals(trs_set, TRS_GRID)
    tn_local = expand_vals(tn_set, TN_GRID)
    tmh_local = expand_vals(tmh_set, TMH_GRID)
    tmb_local = expand_vals(tmb_set, TMB_GRID)

    local_families = ["H3", "H4", "H6"]
    local_fallback = ["B", "D", "E", "F", "G"]
    bucket_cfgs = ["BK0", "BK1", "BK2", "BK3"]
    board_cfgs = ["SHARED", "ALL_TIGHTER", "ALL_LOOSER"] + [f"{b}_TIGHTER" for b in BOARD_KEYS] + [f"{b}_LOOSER" for b in BOARD_KEYS]

    for fam in local_families:
        for tr in tr_local:
            for trs in trs_local:
                if trs > tr:
                    continue
                for tn in tn_local:
                    for tmh in tmh_local:
                        for tmb in tmb_local:
                            for fr in local_fallback:
                                for bcfg in bucket_cfgs:
                                    for brcfg in board_cfgs:
                                        if fam == "H3" and brcfg != "SHARED":
                                            continue
                                        if fam == "H4" and bcfg != "BK0":
                                            continue
                                        p = mk_params(fam, tr, trs, tn, tmh, tmb, bcfg, brcfg, "ON", fr)
                                        candidates.append(emit_candidate(rows, p))
                                        cid += 1

    return candidates


def select_primary(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c
        for c in candidates
        if c["fallback_rate"] <= 0.05 and c["rear_risk"] <= 0.16 and c["utility"] >= 0.08 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    ranked = sorted(feasible, key=lambda c: (-c["score_primary"], c["rear_risk"], c["fallback_rate"], -c["utility"], c["candidate_id"]))
    return ranked, (ranked[0] if ranked else None)


def select_safe(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c
        for c in candidates
        if c["rear_risk"] <= 0.10 and c["fallback_rate"] <= 0.20 and c["utility"] >= 0.055 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    ranked = sorted(feasible, key=lambda c: (c["rear_risk"], -c["utility"], c["fallback_rate"], c["candidate_id"]))
    return ranked, (ranked[0] if ranked else None)


def select_yield(candidates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    feasible = [
        c
        for c in candidates
        if c["utility"] >= 0.085 and c["rear_risk"] < ANCHOR_DET_REAR and c["fallback_rate"] <= 0.08 and c["auto_error"] <= ANCHOR_DET_AUTO
    ]
    ranked = sorted(feasible, key=lambda c: (-c["utility"], c["rear_risk"], c["fallback_rate"], c["candidate_id"]))
    return ranked, (ranked[0] if ranked else None)


def candidate_to_params_v4(c: Dict[str, Any]) -> SweepParamsV4:
    tr = float(c["theta_rear_hold"])
    trs = float(c["theta_rear_soft"])
    tn = float(c["theta_nonrear_boost"])
    tmh = float(c["theta_margin_hold"])
    tmb = float(c["theta_margin_boost"])
    bcfg = str(c["bucket_config_id"])
    brcfg = str(c["board_config_id"])
    return SweepParamsV4(
        family_name=str(c["family_name"]),
        theta_rear_hold=tr,
        theta_rear_soft=trs,
        theta_nonrear_boost=tn,
        theta_margin_hold=tmh,
        theta_margin_boost=tmb,
        bucket_config_id=bcfg,
        bucket_cfg=build_bucket_cfg(bcfg, tr, trs, tn, tmh, tmb),
        board_config_id=brcfg,
        board_cfg=build_board_cfg(brcfg, tr, trs, tn, tmh, tmb),
        conflict_subtype_mode=str(c.get("conflict_subtype_mode", "ON")),
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
                "conflict_subtype": r.get("conflict_subtype", ""),
                "predicate_formula": predicate_formula,
            }
        )
    return out


def write_policy_file(path: Path, point_name: str, params: SweepParamsV4, predicate_formula: str) -> None:
    lines = [
        "# Auto-generated V4 policy description (reproducible parameters).",
        f"POINT_NAME = '{point_name}'",
        f"FAMILY_NAME = '{params.family_name}'",
        f"THETA_REAR_HOLD = {params.theta_rear_hold}",
        f"THETA_REAR_SOFT = {params.theta_rear_soft}",
        f"THETA_NONREAR_BOOST = {params.theta_nonrear_boost}",
        f"THETA_MARGIN_HOLD = {params.theta_margin_hold}",
        f"THETA_MARGIN_BOOST = {params.theta_margin_boost}",
        f"BUCKET_CONFIG_ID = '{params.bucket_config_id}'",
        f"BOARD_CONFIG_ID = '{params.board_config_id}'",
        f"CONFLICT_SUBTYPE_MODE = '{params.conflict_subtype_mode}'",
        f"FALLBACK_RULE = '{params.fallback_rule}'",
        f"CONFIDENCE_WEAK_THR = {params.confidence_weak_thr}",
        f"PREDICATE_FORMULA = '''{predicate_formula}'''",
        f"PROVENANCE = '{PROVENANCE_V4}'",
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


def burst_rate(t: int, pattern: str) -> float:
    if pattern == "Constant":
        return 10.0
    if pattern == "Periodic burst":
        return 50.0 if (t % 30) < 5 else 10.0
    if pattern == "Heavy burst":
        return 100.0 if (t % 60) < 10 else 10.0
    return 10.0


def burst_sim(actions: List[str], pattern: str, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    queue = 0
    q_hist = []
    defer_count = 0
    total_samples = 0
    idx = 0
    n = len(actions)
    for t in range(duration_sec):
        arrivals = int(round(burst_rate(t, pattern)))
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
        out.append({"left_out_unit": g, "group_field": group_field, **m})
    return out


def load_trace(path: Path, policy_name: str) -> Optional[List[Dict[str, Any]]]:
    if not path.exists():
        return None
    rows = read_csv(path)
    for r in rows:
        r["policy_name"] = policy_name
    return rows


def try_load_v3_closest_trace(
    base_rows_raw: List[Dict[str, Any]],
    v3_script_path: Path,
    v3_candidates_csv: Path,
    v3_report_md: Path,
) -> Tuple[Optional[str], Optional[List[Dict[str, Any]]], Optional[Dict[str, Any]]]:
    if not (v3_script_path.exists() and v3_candidates_csv.exists()):
        return None, None, None

    closest_id = None
    if v3_report_md.exists():
        txt = v3_report_md.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"closest:\s*(C\d+)", txt)
        if m:
            closest_id = m.group(1)

    rows = read_csv(v3_candidates_csv)
    pick = None
    if closest_id is not None:
        for r in rows:
            if str(r.get("candidate_id", "")) == closest_id:
                pick = r
                break

    if pick is None and rows:
        feasible = [r for r in rows if safe_float(r.get("utility", 0.0)) >= 0.070 and safe_float(r.get("fallback_rate", 1.0)) <= 0.05]
        if feasible:
            pick = sorted(feasible, key=lambda x: (safe_float(x.get("rear_risk", 1.0)), safe_float(x.get("fallback_rate", 1.0)), -safe_float(x.get("utility", 0.0))))[0]

    if pick is None:
        return None, None, None

    spec = importlib.util.spec_from_file_location("v3mod", str(v3_script_path))
    if spec is None or spec.loader is None:
        return None, None, None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    params = mod.candidate_to_params_v3(pick)
    pol_rows = mod.run_policy_v3(base_rows_raw, params, policy_name=POINT_V3_CLOSEST)
    return str(pick.get("candidate_id", "")), pol_rows, pick


def write_selected_md(
    path: Path,
    m_base: Dict[str, float],
    m_det: Dict[str, float],
    pick_primary: Optional[Dict[str, Any]],
    pick_safe: Optional[Dict[str, Any]],
    pick_yield: Optional[Dict[str, Any]],
) -> None:
    lines = [
        "# 05 V4 Selected Points",
        "",
        "## Anchors",
        f"- BASE_ONLY: rear_risk={m_base['rear_risk']:.6f}, auto_error={m_base['auto_error']:.6f}, utility={m_base['utility']:.6f}",
        f"- DETERMINISTIC_FUSION: rear_risk={m_det['rear_risk']:.6f}, auto_error={m_det['auto_error']:.6f}, utility={m_det['utility']:.6f}",
        f"- V2 LOW_FALLBACK ref: fallback={ANCHOR_V2_LOWFB_FALLBACK:.6f}, rear_risk={ANCHOR_V2_LOWFB_REAR:.6f}, auto_error={ANCHOR_V2_LOWFB_AUTO:.6f}, utility={ANCHOR_V2_LOWFB_UTILITY:.6f}",
        "",
        "## Picks",
    ]

    def _line(name: str, p: Optional[Dict[str, Any]]) -> str:
        if p is None:
            return f"- {name}: NONE"
        return (
            f"- {name}: {p['candidate_id']} | family={p['family_name']} | "
            f"fallback={p['fallback_rate']:.6f}, rear_risk={p['rear_risk']:.6f}, auto_error={p['auto_error']:.6f}, utility={p['utility']:.6f}, score_primary={p['score_primary']:.6f}"
        )

    lines.append(_line(POINT_PRIMARY, pick_primary))
    lines.append(_line(POINT_SAFE, pick_safe))
    lines.append(_line(POINT_YIELD, pick_yield))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_metrics_md(path: Path, point_name: str, pick: Dict[str, Any], m: Dict[str, float]) -> None:
    lines = [
        f"# {point_name} Metrics",
        "",
        f"- provenance: {PROVENANCE_V4}",
        f"- candidate_id: {pick['candidate_id']}",
        f"- family_name: {pick['family_name']}",
        f"- fallback_rate: {m['fallback_rate']:.6f}",
        f"- rear_risk: {m['rear_risk']:.6f}",
        f"- auto_error: {m['auto_error']:.6f}",
        f"- utility: {m['utility']:.6f}",
        f"- lane_recall: {m['lane_recall']:.6f}",
        f"- turn_recall: {m['turn_recall']:.6f}",
        f"- auto_coverage: {m['auto_coverage']:.6f}",
        f"- score_primary: {m['score_primary']:.6f}",
        f"- predicate_formula: {pick['predicate_formula']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_provenance_md(path: Path, point_name: str, pick: Dict[str, Any]) -> None:
    lines = [
        f"# {point_name} Provenance",
        "",
        f"- provenance: {PROVENANCE_V4}",
        "- selected_by: archived_v4_selection_rule",
        f"- candidate_id: {pick['candidate_id']}",
        f"- family_name: {pick['family_name']}",
        f"- predicate_formula: {pick['predicate_formula']}",
        "- source_base_table: canonical_416_base_table.csv",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="RTSS2026 V4 canonical primary-point search.")
    parser.add_argument("--base_table", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--seed", type=int, default=20260522)
    parser.add_argument("--duration_sec", type=int, default=300)
    parser.add_argument("--bootstrap_B", type=int, default=5000)
    parser.add_argument(
        "--v2_low_fallback_trace",
        type=str,
        default=r"D:\computer code\accident_app\outputs\rtss2026_gsp416_canonical_v2_selection_20260522_115936\GSP416_LOW_FALLBACK_action_trace.csv",
    )
    parser.add_argument(
        "--v3_script",
        type=str,
        default=r"D:\computer code\accident_app\backend\scripts\rtss2026_build_gsp416_canonical_v3_stronger_family.py",
    )
    parser.add_argument(
        "--v3_candidates_csv",
        type=str,
        default=r"D:\computer code\accident_app\outputs\rtss2026_gsp416_canonical_v3_stronger_family_20260522_132819\01_v3_sweep_candidates.csv",
    )
    parser.add_argument(
        "--v3_report_md",
        type=str,
        default=r"D:\computer code\accident_app\outputs\rtss2026_gsp416_canonical_v3_stronger_family_20260522_132819\RTSS2026_GSP416_CANONICAL_V3_STRONGER_FAMILY_MASTER_REPORT.md",
    )
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    base_rows_raw = read_csv(Path(args.base_table))
    base_rows, det_rows = build_base_and_det(base_rows_raw)
    m_base = compute_metrics(base_rows, pred_key="final_pred", action_key="action")
    m_det = compute_metrics(det_rows, pred_key="final_pred", action_key="action")

    candidates = sweep_surface_v4(base_rows_raw)
    fields = [
        "candidate_id",
        "family_name",
        "theta_rear_hold",
        "theta_rear_soft",
        "theta_nonrear_boost",
        "theta_margin_hold",
        "theta_margin_boost",
        "bucket_config_id",
        "board_config_id",
        "conflict_subtype_mode",
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
        "score_primary",
        "delta_rear_vs_det",
        "delta_util_vs_base",
        "delta_rear_vs_v2low",
        "delta_util_vs_v2low",
        "predicate_formula",
    ]
    write_csv(out_dir / "01_v4_sweep_candidates.csv", candidates, fields)

    feas_primary, pick_primary = select_primary(candidates)
    feas_safe, pick_safe = select_safe(candidates)
    feas_yield, pick_yield = select_yield(candidates)
    write_csv(out_dir / "02_v4_feasible_primary.csv", feas_primary, fields)
    write_csv(out_dir / "03_v4_feasible_safe.csv", feas_safe, fields)
    write_csv(out_dir / "04_v4_feasible_yield.csv", feas_yield, fields)
    write_selected_md(out_dir / "05_v4_selected_points.md", m_base, m_det, pick_primary, pick_safe, pick_yield)

    selected_map: Dict[str, List[Dict[str, Any]]] = {BASE_ONLY: base_rows, DET_FUSION: det_rows}
    selected_pick_map: Dict[str, Dict[str, Any]] = {}

    def materialize(point_name: str, pick: Optional[Dict[str, Any]]) -> None:
        if pick is None:
            return
        p = candidate_to_params_v4(pick)
        pol_rows = run_policy_v4(base_rows_raw, p, policy_name=point_name)
        trace_rows = to_trace_rows(pol_rows, point_name=point_name, predicate_formula=str(pick["predicate_formula"]))
        write_csv(out_dir / f"{point_name}_action_trace.csv", trace_rows, list(trace_rows[0].keys()) if trace_rows else [])
        write_policy_file(out_dir / f"{point_name}_policy.py", point_name, p, str(pick["predicate_formula"]))
        m = compute_metrics(pol_rows, pred_key="final_pred", action_key="action")
        write_metrics_md(out_dir / f"{point_name}_metrics.md", point_name, pick, m)
        write_provenance_md(out_dir / f"{point_name}_provenance.md", point_name, pick)
        selected_map[point_name] = pol_rows
        selected_pick_map[point_name] = pick

    materialize(POINT_PRIMARY, pick_primary)
    materialize(POINT_SAFE, pick_safe)
    materialize(POINT_YIELD, pick_yield)

    v2_rows = load_trace(Path(args.v2_low_fallback_trace), POINT_V2_LOW_FB)
    if v2_rows is not None:
        selected_map[POINT_V2_LOW_FB] = v2_rows

    v3_closest_id, v3_rows, v3_pick = try_load_v3_closest_trace(
        base_rows_raw,
        Path(args.v3_script),
        Path(args.v3_candidates_csv),
        Path(args.v3_report_md),
    )
    if v3_rows is not None:
        selected_map[POINT_V3_CLOSEST] = v3_rows
        pred_formula = str(v3_pick.get("predicate_formula", "from_v3_candidate")) if v3_pick else "from_v3_candidate"
        trace_rows = to_trace_rows(v3_rows, point_name=POINT_V3_CLOSEST, predicate_formula=pred_formula)
        write_csv(out_dir / f"{POINT_V3_CLOSEST}_action_trace.csv", trace_rows, list(trace_rows[0].keys()) if trace_rows else [])

    queue_rows: List[Dict[str, Any]] = []
    for pname, rows in selected_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for lam in [1, 5, 10, 20, 30, 50, 100]:
            for mu in [0.1, 0.5, 1, 2, 5, 10]:
                q = queue_sim(actions, float(lam), float(mu), duration_sec=args.duration_sec)
                queue_rows.append({"policy_name": pname, **q})
    write_csv(
        out_dir / "06_v4_queue_stress_raw.csv",
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
    qsum = ["# 06 V4 Queue Stress Summary", ""]
    for pname in selected_map.keys():
        sub = [r for r in queue_rows if r["policy_name"] == pname]
        st = sum(1 for r in sub if r["stability_flag"] == "STABLE")
        bd = sum(1 for r in sub if r["stability_flag"] == "BORDERLINE")
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        qsum.append(f"- {pname}: stable/borderline/unstable={st}/{bd}/{un}")
    (out_dir / "06_v4_queue_stress_summary.md").write_text("\n".join(qsum) + "\n", encoding="utf-8")

    burst_rows: List[Dict[str, Any]] = []
    for pname, rows in selected_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for pattern in ["Constant", "Periodic burst", "Heavy burst"]:
            for mu in [0.5, 1, 2, 5]:
                br = burst_sim(actions, pattern=pattern, service_rate=float(mu), duration_sec=args.duration_sec)
                burst_rows.append({"policy_name": pname, **br})
    write_csv(
        out_dir / "07_v4_burst_raw.csv",
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
    bsum = ["# 07 V4 Burst Summary", ""]
    for pname in selected_map.keys():
        sub = [r for r in burst_rows if r["policy_name"] == pname]
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        bsum.append(f"- {pname}: unstable={un}/{len(sub)}")
    (out_dir / "07_v4_burst_summary.md").write_text("\n".join(bsum) + "\n", encoding="utf-8")

    boot_rows = []
    lobo_rows = []
    for i, (pname, rows) in enumerate(selected_map.items(), start=1):
        bs = bootstrap_policy_metrics(rows, B=args.bootstrap_B, seed=args.seed + i * 97)
        boot_rows.append({"policy_name": pname, **bs})
        for r in lobo_metrics(rows, group_field="board_id"):
            lobo_rows.append({"policy_name": pname, **r})
    write_csv(
        out_dir / "08_v4_bootstrap_summary.csv",
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
        out_dir / "08_v4_lobo_board.csv",
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
        ],
    )
    blines = ["# 08 V4 Bootstrap + LOBO Summary", "", f"- bootstrap_B: {args.bootstrap_B}", ""]
    for r in boot_rows:
        blines.append(
            f"- {r['policy_name']}: fallback={r['fallback_mean']:.6f}, rear_risk={r['rear_risk_mean']:.6f}, auto_error={r['auto_error_mean']:.6f}, utility={r['utility_mean']:.6f}"
        )
    (out_dir / "08_v4_bootstrap_lobo_summary.md").write_text("\n".join(blines) + "\n", encoding="utf-8")

    fam_stats: Dict[str, Dict[str, float]] = {}
    for c in candidates:
        fam = str(c["family_name"])
        if fam not in fam_stats:
            fam_stats[fam] = {"count": 0, "best": -1e9}
        fam_stats[fam]["count"] += 1
        fam_stats[fam]["best"] = max(fam_stats[fam]["best"], float(c["score_primary"]))
    fam_rank = sorted(fam_stats.items(), key=lambda kv: kv[1]["best"], reverse=True)

    bucket_na_best = max((c["score_primary"] for c in candidates if c["bucket_config_id"] == "BK0"), default=float("-inf"))
    bucket_non_na_best = max((c["score_primary"] for c in candidates if c["bucket_config_id"] != "BK0"), default=float("-inf"))
    board_shared_best = max((c["score_primary"] for c in candidates if c["board_config_id"] == "SHARED"), default=float("-inf"))
    board_non_shared_best = max((c["score_primary"] for c in candidates if c["board_config_id"] != "SHARED"), default=float("-inf"))

    primary_better_than_v2 = False
    if pick_primary is not None:
        primary_better_than_v2 = (
            float(pick_primary["rear_risk"]) < ANCHOR_V2_LOWFB_REAR
            and float(pick_primary["utility"]) >= ANCHOR_V2_LOWFB_UTILITY
            and float(pick_primary["fallback_rate"]) <= 0.05
        )

    closest_primary = None
    if pick_primary is None:
        near = [c for c in candidates if c["fallback_rate"] <= 0.08 and c["utility"] >= 0.075 and c["auto_error"] <= ANCHOR_DET_AUTO]
        if near:
            closest_primary = sorted(
                near,
                key=lambda c: (
                    max(0.0, c["fallback_rate"] - 0.05)
                    + max(0.0, c["rear_risk"] - 0.16)
                    + max(0.0, 0.08 - c["utility"]),
                    -c["score_primary"],
                ),
            )[0]

    def pick_line(name: str, pick: Optional[Dict[str, Any]]) -> str:
        if pick is None:
            return f"- {name}: NONE"
        return (
            f"- {name}: {pick['candidate_id']} | family={pick['family_name']} | fallback={pick['fallback_rate']:.6f}, "
            f"rear_risk={pick['rear_risk']:.6f}, auto_error={pick['auto_error']:.6f}, utility={pick['utility']:.6f}, score_primary={pick['score_primary']:.6f}"
        )

    report = [
        "# RTSS2026_GSP416_V4_PRIMARY_SEARCH_MASTER_REPORT",
        "",
        "## 1. GSP416_PRIMARY existence",
        f"- found: {pick_primary is not None}",
        pick_line(POINT_PRIMARY, pick_primary),
        "",
        "## 2. Is PRIMARY better than V2 LOW_FALLBACK",
        f"- better_than_v2_low_fallback: {primary_better_than_v2}",
        "",
        "## 3. SAFE and YIELD availability",
        pick_line(POINT_SAFE, pick_safe),
        pick_line(POINT_YIELD, pick_yield),
        "",
        "## 4. Winning family",
    ]
    for fam, st in fam_rank:
        report.append(f"- {fam}: best_score_primary={st['best']:.6f}, candidate_count={int(st['count'])}")
    report.extend(
        [
            "",
            "## 5. Bucket-aware and Board-aware gain",
            f"- bucket_aware_best_score_primary: {bucket_non_na_best:.6f}",
            f"- non_bucket_best_score_primary: {bucket_na_best:.6f}",
            f"- bucket_aware_has_gain: {bucket_non_na_best > bucket_na_best + 1e-9}",
            f"- board_aware_best_score_primary: {board_non_shared_best:.6f}",
            f"- shared_board_best_score_primary: {board_shared_best:.6f}",
            f"- board_aware_has_gain: {board_non_shared_best > board_shared_best + 1e-9}",
            "",
            "## 6. If PRIMARY missing, closest candidate",
        ]
    )
    if pick_primary is None and closest_primary is not None:
        report.append(
            f"- closest: {closest_primary['candidate_id']} | family={closest_primary['family_name']} | fallback={closest_primary['fallback_rate']:.6f}, rear_risk={closest_primary['rear_risk']:.6f}, auto_error={closest_primary['auto_error']:.6f}, utility={closest_primary['utility']:.6f}"
        )
        report.append(
            f"- gap: dfallback={max(0.0, closest_primary['fallback_rate']-0.05):.6f}, drear={max(0.0, closest_primary['rear_risk']-0.16):.6f}, dutility={max(0.0, 0.08-closest_primary['utility']):.6f}, dauto={max(0.0, closest_primary['auto_error']-0.6563):.6f}"
        )
    elif pick_primary is None:
        report.append("- closest: NONE")
    else:
        report.append("- PRIMARY exists; closest-not-needed")

    report.extend(
        [
            "",
            "## 7. Recommended manuscript primary point",
            f"- recommended: {POINT_PRIMARY if pick_primary is not None else 'keep V2 LOW_FALLBACK as main point'}",
            "",
            "## 8. Comparison set used for system reruns",
            f"- includes BASE_ONLY: {BASE_ONLY in selected_map}",
            f"- includes DETERMINISTIC_FUSION: {DET_FUSION in selected_map}",
            f"- includes V2 LOW_FALLBACK: {POINT_V2_LOW_FB in selected_map}",
            f"- includes V3 closest candidate: {POINT_V3_CLOSEST in selected_map} (id={v3_closest_id})",
            f"- includes GSP416_PRIMARY: {POINT_PRIMARY in selected_map}",
            f"- includes GSP416_SAFE: {POINT_SAFE in selected_map}",
            f"- includes GSP416_YIELD: {POINT_YIELD in selected_map}",
            "",
            "## 9. Claim boundary",
            "- no TS3 recovery attempted.",
            "- all selected points (if any) are newly rebuilt reproducible guarded points from canonical_416_base_table.",
            "- if PRIMARY missing, report NONE explicitly and keep claim conservative.",
        ]
    )
    (out_dir / "RTSS2026_GSP416_V4_PRIMARY_SEARCH_MASTER_REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "n_candidates": len(candidates),
                "selected_primary": (pick_primary["candidate_id"] if pick_primary else None),
                "selected_safe": (pick_safe["candidate_id"] if pick_safe else None),
                "selected_yield": (pick_yield["candidate_id"] if pick_yield else None),
                "has_v2_low_trace": bool(v2_rows is not None),
                "has_v3_closest": bool(v3_rows is not None),
                "v3_closest_id": v3_closest_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
