import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


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


def is_missing_value(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def get_value(row: Dict[str, Any], key: str) -> Any:
    if "." not in key:
        return row.get(key)
    cur: Any = row
    for part in key.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def flatten_fields(rows: List[Dict[str, Any]]) -> List[str]:
    keys = set()
    tp_keys = set()
    for r in rows:
        keys.update(r.keys())
        tp = r.get("type_probs")
        if isinstance(tp, dict):
            tp_keys.update(tp.keys())
    for k in tp_keys:
        keys.add(f"type_probs.{k}")
    return sorted(keys)


def non_missing_ratio(rows: List[Dict[str, Any]], key: str) -> float:
    if not rows:
        return 0.0
    non_missing = 0
    for r in rows:
        v = get_value(r, key)
        if not is_missing_value(v):
            non_missing += 1
    return non_missing / len(rows)


def choose_best_field(rows: List[Dict[str, Any]], keys: List[str]) -> Optional[Dict[str, Any]]:
    best_key: Optional[str] = None
    best_ratio = -1.0
    for key in keys:
        ratio = non_missing_ratio(rows, key)
        if ratio > best_ratio:
            best_ratio = ratio
            best_key = key
    if best_key is None:
        return None
    return {"key": best_key, "non_missing_ratio": round(best_ratio, 6)}


def build_alignment_for_source(
    source_name: str,
    source_features: List[str],
    board_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    # direct_candidates: semantically shared trajectory features.
    # approx_candidates: weak proxies when direct shared is not available.
    specs: Dict[str, Dict[str, Any]] = {
        "duration_frames": {
            "semantic": "pair duration in frames",
            "direct_candidates": ["pair_duration_frames"],
            "approx_candidates": ["pred_onset_time", "pred_impact_time", "pred_post_time", "keyframe_times"],
            "note_direct": "shared through pair_duration_frames",
            "note_approx": "only event timing proxy",
            "note_missing": "no duration-like field found",
        },
        "mean_x_velocity": {
            "semantic": "relative longitudinal velocity",
            "direct_candidates": ["mean_longitudinal_velocity_rel"],
            "approx_candidates": [],
            "note_direct": "shared through mean_longitudinal_velocity_rel",
            "note_approx": "",
            "note_missing": "no direct longitudinal velocity field",
        },
        "max_abs_y_velocity": {
            "semantic": "max abs lateral velocity",
            "direct_candidates": ["max_abs_lateral_velocity_rel"],
            "approx_candidates": ["type_probs.lane_change"],
            "note_direct": "shared through max_abs_lateral_velocity_rel",
            "note_approx": "lane probability is only a weak proxy",
            "note_missing": "no lateral movement field",
        },
        "num_lane_changes_meta": {
            "semantic": "lane change count (meta)",
            "direct_candidates": [],
            "approx_candidates": ["lane_change_count_pair", "type_probs.lane_change"],
            "note_direct": "",
            "note_approx": "pair-level count exists but not meta-track exact definition",
            "note_missing": "no lane-change count field",
        },
        "lane_change_count_track": {
            "semantic": "lane change count (track)",
            "direct_candidates": ["lane_change_count_pair"],
            "approx_candidates": ["type_probs.lane_change"],
            "note_direct": "shared through lane_change_count_pair",
            "note_approx": "lane probability only",
            "note_missing": "no track-like lane-change count",
        },
        "driving_direction": {
            "semantic": "driving direction",
            "direct_candidates": [],
            "approx_candidates": [],
            "note_direct": "",
            "note_approx": "",
            "note_missing": "direction field not exported in current board features",
        },
        "min_ttc_eff_capped": {
            "semantic": "min TTC (capped in source expert)",
            "direct_candidates": ["min_ttc_eff"],
            "approx_candidates": ["risk_score", "lead_time_sec", "type_probs.rear_end"],
            "note_direct": "shared through min_ttc_eff (cap can be applied later)",
            "note_approx": "risk/lead-time is only proxy",
            "note_missing": "no TTC field",
        },
        "min_thw_eff_capped": {
            "semantic": "min THW (capped in source expert)",
            "direct_candidates": ["min_thw_eff"],
            "approx_candidates": ["risk_score", "lead_time_sec", "type_probs.rear_end"],
            "note_direct": "shared through min_thw_eff (cap can be applied later)",
            "note_approx": "risk/lead-time is only proxy",
            "note_missing": "no THW field",
        },
        "min_dhw_eff_capped": {
            "semantic": "min DHW (capped in source expert)",
            "direct_candidates": [],
            "approx_candidates": ["risk_score", "type_probs.rear_end"],
            "note_direct": "",
            "note_approx": "rear risk only proxy",
            "note_missing": "no DHW field in current 6-feature export",
        },
        "ttc_missing": {
            "semantic": "TTC missing flag",
            "direct_candidates": ["min_ttc_eff"],
            "approx_candidates": [],
            "note_direct": "can be derived from min_ttc_eff nullability",
            "note_approx": "",
            "note_missing": "no TTC field to derive missing flag",
        },
        "thw_missing": {
            "semantic": "THW missing flag",
            "direct_candidates": ["min_thw_eff"],
            "approx_candidates": [],
            "note_direct": "can be derived from min_thw_eff nullability",
            "note_approx": "",
            "note_missing": "no THW field to derive missing flag",
        },
        "dhw_missing": {
            "semantic": "DHW missing flag",
            "direct_candidates": [],
            "approx_candidates": [],
            "note_direct": "",
            "note_approx": "",
            "note_missing": "no DHW field to derive missing flag",
        },
        "is_car": {
            "semantic": "vehicle class flag: car",
            "direct_candidates": [],
            "approx_candidates": [],
            "note_direct": "",
            "note_approx": "",
            "note_missing": "vehicle class not exported",
        },
        "is_truck": {
            "semantic": "vehicle class flag: truck",
            "direct_candidates": [],
            "approx_candidates": [],
            "note_direct": "",
            "note_approx": "",
            "note_missing": "vehicle class not exported",
        },
    }

    rows: List[Dict[str, Any]] = []
    for feat in source_features:
        spec = specs.get(feat)
        if spec is None:
            rows.append(
                {
                    "a_feature": feat,
                    "semantic": "unknown",
                    "status": "missing",
                    "matched_field": None,
                    "matched_non_missing_ratio": 0.0,
                    "note": "feature not in alignment spec",
                }
            )
            continue

        best_direct = choose_best_field(board_rows, spec["direct_candidates"])
        if best_direct and best_direct["non_missing_ratio"] > 0.0:
            rows.append(
                {
                    "a_feature": feat,
                    "semantic": spec["semantic"],
                    "status": "direct_shared",
                    "matched_field": best_direct["key"],
                    "matched_non_missing_ratio": best_direct["non_missing_ratio"],
                    "note": spec["note_direct"],
                }
            )
            continue

        best_approx = choose_best_field(board_rows, spec["approx_candidates"])
        if best_approx and best_approx["non_missing_ratio"] > 0.0:
            rows.append(
                {
                    "a_feature": feat,
                    "semantic": spec["semantic"],
                    "status": "approx_only",
                    "matched_field": best_approx["key"],
                    "matched_non_missing_ratio": best_approx["non_missing_ratio"],
                    "note": spec["note_approx"],
                }
            )
            continue

        rows.append(
            {
                "a_feature": feat,
                "semantic": spec["semantic"],
                "status": "missing",
                "matched_field": None,
                "matched_non_missing_ratio": 0.0,
                "note": spec["note_missing"],
            }
        )

    n_total = len(rows)
    n_direct = sum(1 for r in rows if r["status"] == "direct_shared")
    n_approx = sum(1 for r in rows if r["status"] == "approx_only")
    n_missing = sum(1 for r in rows if r["status"] == "missing")
    summary = {
        "n_A_features": n_total,
        "direct_shared": n_direct,
        "approx_only": n_approx,
        "missing": n_missing,
        "direct_ratio": round((n_direct / n_total) if n_total else 0.0, 6),
        "approx_or_better_ratio": round(((n_direct + n_approx) / n_total) if n_total else 0.0, 6),
        "bridge_fullness_score": round(((n_direct + 0.5 * n_approx) / n_total) if n_total else 0.0, 6),
    }

    return {
        "source": source_name,
        "summary": summary,
        "A_source_expert_features": source_features,
        "C_alignment_table": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Step3 public bridge alignment re-audit with direct-shared native features.")
    parser.add_argument("--highd-learnability-report", required=True)
    parser.add_argument("--exid-learnability-report", required=True)
    parser.add_argument("--board-152", required=True)
    parser.add_argument("--board-30", required=True)
    parser.add_argument("--board-24", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    highd_rep = load_json(Path(args.highd_learnability_report).resolve())
    exid_rep = load_json(Path(args.exid_learnability_report).resolve())

    rows_152 = load_jsonl(Path(args.board_152).resolve())
    rows_30 = load_jsonl(Path(args.board_30).resolve())
    rows_24 = load_jsonl(Path(args.board_24).resolve())
    board_rows = rows_152 + rows_30 + rows_24

    b_fields = flatten_fields(board_rows)

    highd_features = list(highd_rep.get("features", []))
    exid_features = list(exid_rep.get("features", []))
    if not highd_features:
        raise RuntimeError("highD learnability report has empty features")
    if not exid_features:
        raise RuntimeError("exiD learnability report has empty features")

    highd_align = build_alignment_for_source("highD", highd_features, board_rows)
    exid_align = build_alignment_for_source("exiD", exid_features, board_rows)

    report = {
        "mode": "step3_public_bridge_alignment_reaudit",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "inputs": {
            "highd_learnability_report": str(Path(args.highd_learnability_report).resolve()),
            "exid_learnability_report": str(Path(args.exid_learnability_report).resolve()),
            "board_152": str(Path(args.board_152).resolve()),
            "board_30": str(Path(args.board_30).resolve()),
            "board_24": str(Path(args.board_24).resolve()),
        },
        "board_rows_total": len(board_rows),
        "B_current_board_fields": b_fields,
        "by_source": {
            "highD": highd_align,
            "exiD": exid_align,
        },
        "diagnosis": {
            "previous_baseline_direct_shared": 0,
            "question_answered": "Is direct shared still zero?",
            "highd_direct_shared_now": highd_align["summary"]["direct_shared"],
            "exid_direct_shared_now": exid_align["summary"]["direct_shared"],
            "conclusion": (
                "direct_shared is no longer zero"
                if (highd_align["summary"]["direct_shared"] > 0 or exid_align["summary"]["direct_shared"] > 0)
                else "direct_shared remains zero"
            ),
        },
    }

    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# Step3 Public Bridge Alignment Re-Audit")
    lines.append("")
    lines.append("## Core Answer")
    lines.append(f"- highD direct_shared: {highd_align['summary']['direct_shared']}")
    lines.append(f"- exiD direct_shared: {exid_align['summary']['direct_shared']}")
    lines.append(f"- conclusion: {report['diagnosis']['conclusion']}")
    lines.append("")
    lines.append("## Summary")
    for src, payload in [("highD", highd_align), ("exiD", exid_align)]:
        s = payload["summary"]
        lines.append(f"- {src}: direct={s['direct_shared']}, approx={s['approx_only']}, missing={s['missing']}, bridge_fullness={s['bridge_fullness_score']}")
    lines.append("")
    lines.append("## Alignment Table (highD)")
    lines.append("")
    lines.append("| feature | status | matched_field | non_missing_ratio | note |")
    lines.append("|---|---|---|---:|---|")
    for r in highd_align["C_alignment_table"]:
        field = r["matched_field"] if r["matched_field"] is not None else "(none)"
        lines.append(f"| {r['a_feature']} | {r['status']} | {field} | {r['matched_non_missing_ratio']:.6f} | {r['note']} |")
    lines.append("")
    lines.append("## Alignment Table (exiD)")
    lines.append("")
    lines.append("| feature | status | matched_field | non_missing_ratio | note |")
    lines.append("|---|---|---|---:|---|")
    for r in exid_align["C_alignment_table"]:
        field = r["matched_field"] if r["matched_field"] is not None else "(none)"
        lines.append(f"| {r['a_feature']} | {r['status']} | {field} | {r['matched_non_missing_ratio']:.6f} | {r['note']} |")
    lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "out_json": str(out_json),
                "out_md": str(out_md),
                "highD_summary": highd_align["summary"],
                "exiD_summary": exid_align["summary"],
                "conclusion": report["diagnosis"]["conclusion"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
