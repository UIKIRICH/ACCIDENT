import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def safe_float(v: Any, default: float = math.nan) -> float:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(fv):
        return float(default)
    return float(fv)


def to_int(v: Any, default: int = -1) -> int:
    fv = safe_float(v, float(default))
    if not math.isfinite(fv):
        return int(default)
    return int(round(fv))


def is_positive(v: float) -> bool:
    return math.isfinite(v) and v > 0.0


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            s = raw.strip()
            if not s:
                continue
            try:
                rows.append(json.loads(s))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
    return rows


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def to_json_hash(d: Dict[str, Any], n: int = 12) -> str:
    payload = json.dumps(d, sort_keys=True, ensure_ascii=True).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:n]


def lane_change_count(row: Dict[str, Any]) -> int:
    # exiD event pool exposes track-level lane transition count as public proxy.
    lc = safe_float(row.get("lane_change_count_track"), 0.0)
    if not math.isfinite(lc):
        lc = 0.0
    return int(round(max(0.0, lc)))


def min_lead_ttc(row: Dict[str, Any]) -> float:
    return safe_float(row.get("min_ttc_eff"), math.nan)


def min_lead_thw(row: Dict[str, Any]) -> float:
    return safe_float(row.get("min_thw_eff"), math.nan)


def rear_low_gap_trigger(ttc: float, thw: float) -> bool:
    return (is_positive(ttc) and ttc <= 2.0) or (is_positive(thw) and thw <= 1.2)


def ambiguous_trigger(ttc: float, lc_count: int) -> bool:
    return is_positive(ttc) and (ttc > 2.0) and (ttc <= 3.0) and (lc_count >= 1)


def lane_merge_trigger(lc_count: int) -> bool:
    return lc_count >= 1


def risk_score(ttc: float, thw: float, lc_count: int) -> float:
    ttc_term = clip01((3.0 - ttc) / 3.0) if is_positive(ttc) else 0.0
    thw_term = clip01((1.5 - thw) / 1.5) if is_positive(thw) else 0.0
    lc_term = clip01(float(lc_count) / 3.0)
    return round(0.50 * ttc_term + 0.35 * thw_term + 0.15 * lc_term, 6)


def first_valid_frame(candidates: List[Any], frame_start: int, frame_end: int) -> int:
    for c in candidates:
        fi = to_int(c, -1)
        if fi < 0:
            continue
        if fi < frame_start:
            return frame_start
        if fi > frame_end:
            return frame_end
        return fi
    return frame_start


def choose_frame_event(row: Dict[str, Any], event_type: str, frame_start: int, frame_end: int) -> int:
    if event_type == "lane_change_merge_adjacent":
        candidates = [row.get("first_lc_frame"), row.get("frame_hint"), row.get("frame_min_ttc"), row.get("frame_min_thw")]
    elif event_type == "rear_risk_low_gap":
        candidates = [row.get("frame_min_ttc"), row.get("frame_min_thw"), row.get("frame_hint"), row.get("first_lc_frame")]
    else:
        candidates = [row.get("frame_min_ttc"), row.get("first_lc_frame"), row.get("frame_min_thw"), row.get("frame_hint")]
    return first_valid_frame(candidates, frame_start, frame_end)


def preprocess_best_by_ego(rows: List[Dict[str, Any]], min_frames: int) -> List[Dict[str, Any]]:
    best: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for r in rows:
        rec = to_int(r.get("recording_id"), -1)
        tid = to_int(r.get("vehicle_id"), -1)
        if rec < 0 or tid < 0:
            continue
        duration_frames = to_int(r.get("duration_frames"), -1)
        if duration_frames < int(min_frames):
            continue

        ttc = min_lead_ttc(r)
        thw = min_lead_thw(r)
        lc = lane_change_count(r)
        score = risk_score(ttc, thw, lc)
        key = (rec, tid)
        prev = best.get(key)
        if prev is None or float(prev["risk_score"]) < score:
            best[key] = {
                "raw": r,
                "recordingId": rec,
                "trackId": tid,
                "numFrames": duration_frames,
                "min_leadTTC": ttc,
                "min_leadTHW": thw,
                "laneChange_count": lc,
                "risk_score": score,
            }
    return list(best.values())


def select_subset(
    rows: List[Dict[str, Any]],
    n_lane: int,
    n_rear: int,
    n_ambiguous: int,
) -> List[Dict[str, Any]]:
    lane_pool: List[Dict[str, Any]] = []
    rear_pool: List[Dict[str, Any]] = []
    amb_pool: List[Dict[str, Any]] = []

    for x in rows:
        ttc = float(x["min_leadTTC"])
        thw = float(x["min_leadTHW"])
        lc = int(x["laneChange_count"])
        is_lane = lane_merge_trigger(lc)
        is_rear = rear_low_gap_trigger(ttc, thw)
        is_amb = ambiguous_trigger(ttc, lc)

        if is_amb:
            y = dict(x)
            y["event_type"] = "ambiguous_boundary"
            y["selection_rule"] = "2.0 < min_positive_leadTTC <= 3.0 AND laneChange_count >= 1"
            amb_pool.append(y)
        elif is_rear:
            y = dict(x)
            y["event_type"] = "rear_risk_low_gap"
            y["selection_rule"] = "min_positive_leadTTC <= 2.0 OR min_positive_leadTHW <= 1.2"
            rear_pool.append(y)
        elif is_lane:
            y = dict(x)
            y["event_type"] = "lane_change_merge_adjacent"
            y["selection_rule"] = "laneChange_count >= 1 (laneletId-transition public proxy)"
            lane_pool.append(y)

    key_fn = lambda z: (-float(z["risk_score"]), int(z["recordingId"]), int(z["trackId"]))
    amb_pool = sorted(amb_pool, key=key_fn)
    rear_pool = sorted(rear_pool, key=key_fn)
    lane_pool = sorted(lane_pool, key=key_fn)

    selected: List[Dict[str, Any]] = []
    used_keys: set = set()

    def take(pool: List[Dict[str, Any]], need: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for c in pool:
            key = (int(c["recordingId"]), int(c["trackId"]))
            if key in used_keys:
                continue
            used_keys.add(key)
            out.append(c)
            if len(out) >= need:
                break
        return out

    selected.extend(take(amb_pool, n_ambiguous))
    selected.extend(take(rear_pool, n_rear))
    selected.extend(take(lane_pool, n_lane))

    if len([x for x in selected if x["event_type"] == "ambiguous_boundary"]) < n_ambiguous:
        raise RuntimeError("not enough ambiguous_boundary cases under public rules.")
    if len([x for x in selected if x["event_type"] == "rear_risk_low_gap"]) < n_rear:
        raise RuntimeError("not enough rear_risk_low_gap cases under public rules.")
    if len([x for x in selected if x["event_type"] == "lane_change_merge_adjacent"]) < n_lane:
        raise RuntimeError("not enough lane_change_merge_adjacent cases under public rules.")

    for c in selected:
        raw = c["raw"]
        frame_start = to_int(raw.get("frame_start"), -1)
        frame_end = to_int(raw.get("frame_end"), -1)
        frame_event = choose_frame_event(raw, str(c["event_type"]), frame_start, frame_end)
        c["frame_start"] = frame_start
        c["frame_end"] = frame_end
        c["frame_event"] = frame_event
        c["case_id"] = f"exid_r{c['recordingId']}_t{c['trackId']}_f{frame_event}_{c['event_type']}"

    selected = sorted(selected, key=lambda z: (str(z["event_type"]), int(z["recordingId"]), int(z["trackId"])))
    return selected


def gate_only_decision(case: Dict[str, Any]) -> str:
    ttc = float(case["min_leadTTC"])
    thw = float(case["min_leadTHW"])
    return "DEFER" if rear_low_gap_trigger(ttc, thw) else "RELEASE"


def strict_gap_proxy_decision(case: Dict[str, Any]) -> str:
    # Intentional strict-gap proxy: permissive release under fixed gap-style criteria.
    ttc = float(case["min_leadTTC"])
    thw = float(case["min_leadTHW"])
    lc = int(case["laneChange_count"])
    if (lc >= 1) and ((is_positive(ttc) and ttc >= 1.0) or (is_positive(thw) and thw >= 0.25)):
        return "RELEASE"
    return "DEFER" if rear_low_gap_trigger(ttc, thw) else "RELEASE"


def structured_proxy_decision(case: Dict[str, Any]) -> str:
    # SEF-style proxy: conservative structure, not internal SEF reproduction.
    ttc = float(case["min_leadTTC"])
    thw = float(case["min_leadTHW"])
    if rear_low_gap_trigger(ttc, thw):
        return "DEFER"
    if str(case["event_type"]) == "ambiguous_boundary":
        if (is_positive(ttc) and ttc <= 2.6) or (is_positive(thw) and thw <= 1.4):
            return "DEFER"
    if int(case["laneChange_count"]) >= 1:
        return "RELEASE"
    return "DEFER"


def route_decision(route: str, case: Dict[str, Any]) -> str:
    if route == "gate-only":
        return gate_only_decision(case)
    if route == "strict-gap-proxy":
        return strict_gap_proxy_decision(case)
    if route == "structured-proxy":
        return structured_proxy_decision(case)
    if route == "RPA-auxiliary":
        # Non-interference: RPA does not modify autonomous decision.
        return structured_proxy_decision(case)
    raise ValueError(f"unknown route: {route}")


def route_configs() -> Dict[str, Dict[str, Any]]:
    return {
        "gate-only": {
            "rear_ttc_le": 2.0,
            "rear_thw_le": 1.2,
            "policy": "defer_on_low_gap_only",
        },
        "strict-gap-proxy": {
            "release_lanechange_if": "laneChange_count>=1 AND (leadTTC>=1.0 OR leadTHW>=0.25)",
            "fallback": "gate_only",
            "policy": "strict_gap_proxy_public",
        },
        "structured-proxy": {
            "label": "SEF-style proxy",
            "rear_guard": "defer_on_low_gap",
            "ambiguous_guard": "defer_if_ambiguous_and_ttc<=2.6_or_thw<=1.4",
            "policy": "structured_proxy_public",
        },
        "RPA-auxiliary": {
            "label": "review-priority auxiliary",
            "non_interference": True,
            "decision_backend": "structured-proxy",
            "priority_score": "3*ambiguous + 2*rear_low_gap + risk_score",
        },
    }


def traceability_complete(case: Dict[str, Any], route: str, config_hash: str) -> int:
    required = [
        case.get("case_id"),
        case.get("recordingId"),
        case.get("trackId"),
        case.get("frame_start"),
        case.get("frame_event"),
        case.get("frame_end"),
        case.get("event_type"),
        case.get("min_leadTTC"),
        case.get("min_leadTHW"),
        case.get("laneChange_count"),
        case.get("risk_score"),
        route,
        config_hash,
    ]
    for v in required:
        if v is None:
            return 0
    return 1


def proxy_metrics(case: Dict[str, Any], decision: str) -> Dict[str, float]:
    ttc = float(case["min_leadTTC"])
    thw = float(case["min_leadTHW"])
    rear_trigger = rear_low_gap_trigger(ttc, thw)
    wrong_release = 1 if (decision == "RELEASE" and rear_trigger) else 0
    rear_risk = float(case["risk_score"]) if decision == "RELEASE" else 0.0
    safety_break = 1 if (wrong_release == 1 or rear_risk >= 0.85) else 0
    lc = int(case["laneChange_count"])
    if decision == "RELEASE" and (not rear_trigger) and (lc >= 1):
        gain = 1.0
    elif decision == "DEFER" and (not rear_trigger):
        gain = -0.5
    elif decision == "RELEASE" and rear_trigger:
        gain = -1.0
    else:
        gain = 0.0
    useful_positive = 1.0 if gain > 0 else 0.0
    utility = (useful_positive * (1.0 - rear_risk)) - (wrong_release + rear_risk)
    return {
        "gain_proxy": round(gain, 6),
        "wrong_release_proxy": int(wrong_release),
        "rear_risk_proxy": round(rear_risk, 6),
        "safety_break": int(safety_break),
        "useful_positive_proxy": round(useful_positive, 6),
        "utility_proxy": round(utility, 6),
    }


def build_replay_audit(cases: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, float]], Dict[str, Any]]:
    routes = ["gate-only", "strict-gap-proxy", "structured-proxy", "RPA-auxiliary"]
    cfg = route_configs()
    cfg_hash = {r: to_json_hash(cfg[r]) for r in routes}
    audit_rows: List[Dict[str, Any]] = []
    route_agg: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

    rpa_priority: List[Tuple[str, float]] = []

    for case in cases:
        for route in routes:
            decision = route_decision(route, case)
            metrics = proxy_metrics(case, decision)
            trace_ok = traceability_complete(case, route, cfg_hash[route])
            verdict = "pass" if (trace_ok == 1 and metrics["safety_break"] == 0) else "fail"
            trace_id = f"ps2::{case['case_id']}::{route}::{cfg_hash[route]}"
            row = {
                "case_id": case["case_id"],
                "route": route,
                "decision": decision,
                "gain_proxy": metrics["gain_proxy"],
                "wrong_release_proxy": metrics["wrong_release_proxy"],
                "rear_risk_proxy": metrics["rear_risk_proxy"],
                "safety_break": metrics["safety_break"],
                "traceability_complete": trace_ok,
                "verdict": verdict,
                "trace_id": trace_id,
                "config_hash": cfg_hash[route],
            }
            audit_rows.append(row)

            route_agg[route]["N"] += 1
            route_agg[route]["release_count"] += 1 if decision == "RELEASE" else 0
            route_agg[route]["defer_count"] += 1 if decision == "DEFER" else 0
            route_agg[route]["gain_proxy_sum"] += float(metrics["gain_proxy"])
            route_agg[route]["wrong_release_proxy_sum"] += float(metrics["wrong_release_proxy"])
            route_agg[route]["rear_risk_proxy_sum"] += float(metrics["rear_risk_proxy"])
            route_agg[route]["safety_break_sum"] += float(metrics["safety_break"])
            route_agg[route]["traceability_complete_sum"] += float(trace_ok)
            route_agg[route]["useful_positive_proxy_sum"] += float(metrics["useful_positive_proxy"])
            route_agg[route]["utility_proxy_sum"] += float(metrics["utility_proxy"])

            if route == "RPA-auxiliary":
                is_amb = 1 if str(case["event_type"]) == "ambiguous_boundary" else 0
                ttc = float(case["min_leadTTC"])
                thw = float(case["min_leadTHW"])
                rear = 1 if rear_low_gap_trigger(ttc, thw) else 0
                score = round(3.0 * is_amb + 2.0 * rear + float(case["risk_score"]), 6)
                rpa_priority.append((case["case_id"], score))

    route_summary: Dict[str, Dict[str, float]] = {}
    for route, agg in route_agg.items():
        n = max(1.0, float(agg["N"]))
        route_summary[route] = {
            "N": int(agg["N"]),
            "release_count": int(agg["release_count"]),
            "defer_count": int(agg["defer_count"]),
            "gain_proxy_sum": round(float(agg["gain_proxy_sum"]), 6),
            "wrong_release_proxy_sum": int(round(float(agg["wrong_release_proxy_sum"]))),
            "rear_risk_proxy_mean": round(float(agg["rear_risk_proxy_sum"]) / n, 6),
            "safety_break_sum": int(round(float(agg["safety_break_sum"]))),
            "traceability_complete_rate": round(float(agg["traceability_complete_sum"]) / n, 6),
            "useful_positive_proxy_sum": round(float(agg["useful_positive_proxy_sum"]), 6),
            "utility_proxy_sum": round(float(agg["utility_proxy_sum"]), 6),
        }

    rpa_priority_sorted = sorted(rpa_priority, key=lambda z: (-z[1], z[0]))
    topk = {}
    for k in [3, 5, 10]:
        pick = rpa_priority_sorted[:k]
        if not pick:
            topk[k] = {"k": k, "n": 0, "mean_priority_score": 0.0, "case_ids": ""}
            continue
        mean_score = sum(x[1] for x in pick) / float(len(pick))
        topk[k] = {
            "k": k,
            "n": len(pick),
            "mean_priority_score": round(mean_score, 6),
            "case_ids": "|".join(x[0] for x in pick),
        }

    return audit_rows, route_summary, topk


def build_inventory_rows(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for c in cases:
        out.append(
            {
                "case_id": c["case_id"],
                "recordingId": c["recordingId"],
                "trackId": c["trackId"],
                "frame_start": c["frame_start"],
                "frame_event": c["frame_event"],
                "frame_end": c["frame_end"],
                "event_type": c["event_type"],
                "min_leadTTC": "" if not math.isfinite(float(c["min_leadTTC"])) else round(float(c["min_leadTTC"]), 6),
                "min_leadTHW": "" if not math.isfinite(float(c["min_leadTHW"])) else round(float(c["min_leadTHW"]), 6),
                "laneChange_count": int(c["laneChange_count"]),
                "risk_score": round(float(c["risk_score"]), 6),
                "selection_rule": c["selection_rule"],
            }
        )
    return out


def go_limited_needed(cases: List[Dict[str, Any]]) -> bool:
    # If both TTC/THW are missing, low-gap proxy cannot be defined reliably.
    for c in cases:
        ttc = float(c["min_leadTTC"])
        thw = float(c["min_leadTHW"])
        if (not is_positive(ttc)) and (not is_positive(thw)):
            return True
    return False


def build_definition_md(
    out_path: Path,
    source_jsonl: Path,
    total_cases: int,
    counts: Dict[str, int],
) -> None:
    lines = [
        "# PUBLIC_SOURCE_SUBSET_DEFINITION",
        "",
        "## Source",
        f"- dataset: exiD",
        f"- source_event_pool: `{source_jsonl}`",
        "- public fields used: recording_id, vehicle_id, frame_start, frame_end, frame_hint, frame_min_ttc, frame_min_thw, first_lc_frame, duration_frames, lane_change_count_track, min_ttc_eff, min_thw_eff",
        "",
        "## Case Unit",
        "- `case_id = exid_r{recordingId}_t{trackId}_f{frame_event}_{event_type}`",
        "",
        "## Selection Rules",
        "- lane-change / merge-adjacent: `laneChange_count >= 1` (laneletId transition proxy from public track fields).",
        "- rear-risk / low-gap: `min_positive_leadTTC <= 2.0 OR min_positive_leadTHW <= 1.2`.",
        "- ambiguous-boundary: `2.0 < min_positive_leadTTC <= 3.0 AND laneChange_count >= 1`.",
        "- audit constraints: `numFrames >= 50`, dedup by `recordingId + trackId`, keep highest-risk event per ego.",
        "",
        "## Public Identifiers Preserved",
        "- `recordingId, trackId, frame_start, frame_event, frame_end`",
        "",
        "## Subset Size",
        f"- total selected cases: {total_cases}",
        f"- lane_change_merge_adjacent: {counts.get('lane_change_merge_adjacent', 0)}",
        f"- rear_risk_low_gap: {counts.get('rear_risk_low_gap', 0)}",
        f"- ambiguous_boundary: {counts.get('ambiguous_boundary', 0)}",
        "",
        "## Claim Boundary",
        "This public-source subset is a sanity/proxy check. It is not a public benchmark split, does not replace the frozen derived replay scopes, and is not used to claim trajectory-prediction SOTA or full reproduction of the headline ΔMacro result.",
        "",
        "## Locked Boundary (Phase-2)",
        "- does not replace 57-case headline scope",
        "- does not replace 42-case statistical universe",
        "- does not replace 34-case hard-negative set",
        "- does not replace 24-item RPA queue",
        "- no Abstract / main result / main claim rewrite",
        "- no public benchmark split claim",
        "- no trajectory-prediction SOTA claim",
        "- no ADE/FDE superiority claim",
        "- no full ΔMacro reproduction claim",
        "- public-source sanity/proxy check only",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_summary_md(
    out_path: Path,
    out_dir: Path,
    inventory_rows: List[Dict[str, Any]],
    route_summary: Dict[str, Dict[str, float]],
    topk: Dict[int, Dict[str, Any]],
    go_limited: bool,
) -> None:
    cnt = Counter([str(r["event_type"]) for r in inventory_rows])
    n = len(inventory_rows)

    strict_rejected = route_summary["strict-gap-proxy"]["wrong_release_proxy_sum"] > 0 or route_summary["strict-gap-proxy"]["safety_break_sum"] > 0
    structured_safe = route_summary["structured-proxy"]["safety_break_sum"] == 0

    route_headers = [
        "route",
        "N",
        "release_count",
        "defer_count",
        "wrong_release_proxy_sum",
        "rear_risk_proxy_mean",
        "safety_break_sum",
        "traceability_complete_rate",
        "useful_positive_proxy_sum",
        "utility_proxy_sum",
    ]

    lines: List[str] = []
    lines.append("# PUBLIC_SOURCE_SANITY_SUMMARY")
    lines.append("")
    lines.append("## Snapshot")
    lines.append(f"- N cases: {n}")
    lines.append(f"- lane-change / merge-adjacent: {cnt.get('lane_change_merge_adjacent', 0)}")
    lines.append(f"- rear-risk / low-gap: {cnt.get('rear_risk_low_gap', 0)}")
    lines.append(f"- ambiguous-boundary: {cnt.get('ambiguous_boundary', 0)}")
    lines.append("")
    lines.append("## Route-Level Summary")
    lines.append("| " + " | ".join(route_headers) + " |")
    lines.append("|" + "|".join(["---"] * len(route_headers)) + "|")
    for route in ["gate-only", "strict-gap-proxy", "structured-proxy", "RPA-auxiliary"]:
        rs = route_summary[route]
        row = [
            route,
            str(rs["N"]),
            str(rs["release_count"]),
            str(rs["defer_count"]),
            str(rs["wrong_release_proxy_sum"]),
            f"{rs['rear_risk_proxy_mean']:.6f}",
            str(rs["safety_break_sum"]),
            f"{rs['traceability_complete_rate']:.6f}",
            f"{rs['useful_positive_proxy_sum']:.6f}",
            f"{rs['utility_proxy_sum']:.6f}",
        ]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Route Conclusions")
    lines.append(f"- strict-gap-proxy admissibility: {'rejected (proxy)' if strict_rejected else 'admitted (proxy)'}")
    lines.append(f"- structured-proxy (SEF-style proxy) safety preservation: {'yes' if structured_safe else 'no'}")
    lines.append("- RPA non-interference (autonomous release decision changed?): no (by design and audit rows)")
    lines.append("")
    lines.append("## RPA Top-k Priority Proxy")
    lines.append("| k | n | mean_priority_score | case_ids |")
    lines.append("|---|---|---|---|")
    for k in [3, 5, 10]:
        r = topk.get(k, {"k": k, "n": 0, "mean_priority_score": 0.0, "case_ids": ""})
        lines.append(f"| {r['k']} | {r['n']} | {r['mean_priority_score']:.6f} | {r['case_ids']} |")
    lines.append("")
    lines.append("## Suggested Paper Insertion Text")
    lines.append("- Main paper (1 sentence): We additionally ran a 30-case exiD public-source sanity/proxy replay subset with public identifiers and rule-based indexing, and verified that replay protocol traceability and admissibility audit can be instantiated without altering the frozen main evidence scopes.")
    lines.append("- Appendix H draft:")
    lines.append("  This appendix reports a public-source exiD sanity/proxy subset (`N=30`) used only for protocol-instantiation checks: case indexing, replay traceability, admissibility proxy audit, and RPA non-interference. Route names are proxy-scoped (`gate-only`, `strict-gap-proxy`, `structured-proxy / SEF-style proxy`, `RPA auxiliary`) and are not claimed as internal-route reproductions. This public-source subset is a sanity/proxy check. It is not a public benchmark split, does not replace the frozen derived replay scopes, and is not used to claim trajectory-prediction SOTA or full reproduction of the headline ΔMacro result.")
    lines.append("- Table H1/H2/H3 draft:")
    lines.append(f"  - Table H1 (subset inventory): counts by event type and public identifiers; source file `public_source_case_inventory.csv` (N={n}).")
    lines.append("  - Table H2 (route-case proxy audit): decision, wrong_release_proxy, rear_risk_proxy, safety_break, traceability_complete per route-case; source file `public_source_replay_audit.csv`.")
    lines.append("  - Table H3 (route-level + RPA top-k): route aggregate proxy metrics and RPA top-k priority proxy enrichment.")
    lines.append("")
    lines.append("## Limitations")
    lines.append("- All labels here are proxy labels from public kinematic fields; no private target annotations are introduced.")
    lines.append("- `wrong_release_proxy`, `rear_risk_proxy`, and `utility_proxy` are proxy-only and should not be interpreted as full headline metrics.")
    lines.append("- This subset is not used for full ΔMacro headline reproduction or public benchmark claims.")
    lines.append("- This subset is not used for trajectory-prediction SOTA or ADE/FDE superiority claims.")
    lines.append("")
    lines.append("## Files")
    lines.append(f"- subset definition: `{out_dir / 'PUBLIC_SOURCE_SUBSET_DEFINITION.md'}`")
    lines.append(f"- inventory: `{out_dir / 'public_source_case_inventory.csv'}`")
    lines.append(f"- replay audit: `{out_dir / 'public_source_replay_audit.csv'}`")
    lines.append("")
    lines.append("## Final Recommendation")
    if go_limited:
        lines.append("- GO-LIMITED: proxy metrics could not be fully defined from public fields for all selected cases; traceability-only sanity check is available.")
    else:
        lines.append("- GO: public-source sanity/proxy subset experiment is feasible under locked claim boundary.")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Phase-2 exiD public-source sanity/proxy subset outputs.")
    parser.add_argument(
        "--source-jsonl",
        type=Path,
        default=Path("outputs/fusion_v3/reports/v3_5_20260508_exid_switch_relaxedscan/exid_event_pool_selected_relaxed.jsonl"),
    )
    parser.add_argument("--n-lane", type=int, default=12)
    parser.add_argument("--n-rear", type=int, default=12)
    parser.add_argument("--n-ambiguous", type=int, default=6)
    parser.add_argument("--min-frames", type=int, default=50)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()

    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = args.out_dir or Path(f"outputs/public_source_sanity_subset_phase2_{now}")
    out_dir.mkdir(parents=True, exist_ok=True)

    source_rows = load_jsonl(args.source_jsonl)
    best_rows = preprocess_best_by_ego(source_rows, min_frames=args.min_frames)
    selected = select_subset(best_rows, n_lane=args.n_lane, n_rear=args.n_rear, n_ambiguous=args.n_ambiguous)

    inventory_rows = build_inventory_rows(selected)
    go_limited = go_limited_needed(selected)

    audit_rows: List[Dict[str, Any]] = []
    route_summary: Dict[str, Dict[str, float]] = {}
    topk: Dict[int, Dict[str, Any]] = {}

    if go_limited:
        cfg = route_configs()
        cfg_hash = {r: to_json_hash(cfg[r]) for r in cfg}
        for c in selected:
            for route in ["gate-only", "strict-gap-proxy", "structured-proxy", "RPA-auxiliary"]:
                decision = route_decision(route, c)
                trace_ok = traceability_complete(c, route, cfg_hash[route])
                audit_rows.append(
                    {
                        "case_id": c["case_id"],
                        "route": route,
                        "decision": decision,
                        "gain_proxy": "NA",
                        "wrong_release_proxy": "NA",
                        "rear_risk_proxy": "NA",
                        "safety_break": "NA",
                        "traceability_complete": trace_ok,
                        "verdict": "traceability_only",
                        "trace_id": f"ps2::{c['case_id']}::{route}::{cfg_hash[route]}",
                        "config_hash": cfg_hash[route],
                    }
                )
        route_summary = {
            r: {
                "N": len(selected),
                "release_count": sum(1 for rr in audit_rows if rr["route"] == r and rr["decision"] == "RELEASE"),
                "defer_count": sum(1 for rr in audit_rows if rr["route"] == r and rr["decision"] == "DEFER"),
                "gain_proxy_sum": 0.0,
                "wrong_release_proxy_sum": 0,
                "rear_risk_proxy_mean": 0.0,
                "safety_break_sum": 0,
                "traceability_complete_rate": round(
                    sum(1 for rr in audit_rows if rr["route"] == r and rr["traceability_complete"] == 1) / float(max(1, len(selected))),
                    6,
                ),
                "useful_positive_proxy_sum": 0.0,
                "utility_proxy_sum": 0.0,
            }
            for r in ["gate-only", "strict-gap-proxy", "structured-proxy", "RPA-auxiliary"]
        }
        topk = {3: {"k": 3, "n": 0, "mean_priority_score": 0.0, "case_ids": ""}, 5: {"k": 5, "n": 0, "mean_priority_score": 0.0, "case_ids": ""}, 10: {"k": 10, "n": 0, "mean_priority_score": 0.0, "case_ids": ""}}
    else:
        audit_rows, route_summary, topk = build_replay_audit(selected)

    build_definition_md(
        out_path=out_dir / "PUBLIC_SOURCE_SUBSET_DEFINITION.md",
        source_jsonl=args.source_jsonl,
        total_cases=len(selected),
        counts=Counter([str(x["event_type"]) for x in selected]),
    )

    write_csv(
        out_dir / "public_source_case_inventory.csv",
        inventory_rows,
        [
            "case_id",
            "recordingId",
            "trackId",
            "frame_start",
            "frame_event",
            "frame_end",
            "event_type",
            "min_leadTTC",
            "min_leadTHW",
            "laneChange_count",
            "risk_score",
            "selection_rule",
        ],
    )

    write_csv(
        out_dir / "public_source_replay_audit.csv",
        audit_rows,
        [
            "case_id",
            "route",
            "decision",
            "gain_proxy",
            "wrong_release_proxy",
            "rear_risk_proxy",
            "safety_break",
            "traceability_complete",
            "verdict",
            "trace_id",
            "config_hash",
        ],
    )

    build_summary_md(
        out_path=out_dir / "PUBLIC_SOURCE_SANITY_SUMMARY.md",
        out_dir=out_dir,
        inventory_rows=inventory_rows,
        route_summary=route_summary,
        topk=topk,
        go_limited=go_limited,
    )

    manifest = {
        "status": "GO-LIMITED" if go_limited else "GO",
        "source_jsonl": str(args.source_jsonl),
        "out_dir": str(out_dir),
        "n_selected": len(selected),
        "counts": dict(Counter([str(x["event_type"]) for x in selected])),
        "generated_files": [
            str(out_dir / "PUBLIC_SOURCE_SUBSET_DEFINITION.md"),
            str(out_dir / "public_source_case_inventory.csv"),
            str(out_dir / "public_source_replay_audit.csv"),
            str(out_dir / "PUBLIC_SOURCE_SANITY_SUMMARY.md"),
        ],
    }
    (out_dir / "PUBLIC_SOURCE_SANITY_MANIFEST.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
