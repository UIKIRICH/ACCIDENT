import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.video_keyframe import extract_sequence_features  # noqa: E402


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


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def parse_path_aliases(raw_aliases: List[str]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for raw in raw_aliases:
        s = str(raw).strip()
        if not s or "=" not in s:
            continue
        src, dst = s.split("=", 1)
        src = src.strip().replace("\\", "/").strip("/")
        dst = dst.strip().replace("\\", "/").strip("/")
        if src and dst:
            out[src] = dst
    return out


def resolve_video(video_ref: str, videos_root: Path, alias_map: Dict[str, str]) -> Path:
    p = Path(video_ref)
    if p.is_absolute():
        return p
    base = videos_root / p
    if base.exists():
        return base
    ref = str(video_ref).replace("\\", "/").strip()
    parts = [x for x in ref.split("/") if x]
    if not parts:
        return base
    head = parts[0]
    mapped_head = alias_map.get(head)
    if not mapped_head:
        return base
    mapped = videos_root / mapped_head
    for frag in parts[1:]:
        mapped = mapped / frag
    return mapped


def get_stage_metrics(seq: Dict[str, Any], stage: str) -> Dict[str, float]:
    pm = ((seq.get("evidence") or {}).get("pair_metrics") or {}).get(stage) or {}
    return {
        "approach_score": safe_float(pm.get("approach_score", 0.0)),
        "ttc_score": safe_float(pm.get("ttc_score", 0.0)),
        "same_lane_score": safe_float(pm.get("same_lane_score", 0.0)),
        "front_back_order_score": safe_float(pm.get("front_back_order_score", 0.0)),
        "lateral_shift_score": safe_float(pm.get("lateral_shift_score", 0.0)),
        "cutin_continuity": safe_float(pm.get("cutin_continuity", 0.0)),
        "side_overlap_growth": safe_float(pm.get("side_overlap_growth", 0.0)),
        "convergence_score": safe_float(pm.get("convergence_score", 0.0)),
        "direction_change_score": safe_float(pm.get("direction_change_score", 0.0)),
        "path_crossing_score": safe_float(pm.get("path_crossing_score", 0.0)),
        "off_lane_conflict_score": safe_float(pm.get("off_lane_conflict_score", 0.0)),
        "longitudinal_dominance": safe_float(pm.get("longitudinal_dominance", 0.0)),
    }


def extract_row(label: Dict[str, Any], seq: Dict[str, Any], video_ref: str, split: str) -> Dict[str, Any]:
    risk = seq.get("risk_info", {}) or {}
    dom = seq.get("dominant_meta", {}) or {}
    sp = seq.get("scene_prior", {}) or {}
    type_probs = seq.get("type_probs", {}) or {}
    ds = seq.get("direct_shared_pair_agg", {}) or ((seq.get("evidence") or {}).get("direct_shared_pair_agg", {}) or {})

    onset = get_stage_metrics(seq, "onset")
    impact = get_stage_metrics(seq, "impact")
    post = get_stage_metrics(seq, "post")

    def g(m: Dict[str, float], k: str) -> float:
        return safe_float(m.get(k, 0.0))

    row: Dict[str, Any] = {
        "sample_id": str(label.get("sample_id", "")).strip(),
        "video": str(video_ref).replace("\\", "/"),
        "split": split,
        "accident_type": str(label.get("accident_type", "")).strip(),
        "scene_tags": json.dumps(label.get("scene_tags", []), ensure_ascii=False),
        "pred_type_key": str(seq.get("accident_type_key", "")),
        "pred_type_confidence": safe_float(seq.get("type_confidence", 0.0)),
        "prob_rear": safe_float(type_probs.get("rear_end", 0.0)),
        "prob_lane": safe_float(type_probs.get("lane_change", 0.0)),
        "prob_turn": safe_float(type_probs.get("turn_conflict", 0.0)),
        "risk_alert_time": safe_float(risk.get("risk_alert_time", 0.0)),
        "lead_time_sec": safe_float(risk.get("lead_time_sec", 0.0)),
        "peak_risk": safe_float(risk.get("peak_risk", 0.0)),
        "risk_threshold": safe_float(risk.get("risk_threshold", 0.0)),
        "dominance": safe_float(dom.get("dominance", 0.0)),
        "bridged_coverage": safe_float(dom.get("bridged_coverage", 0.0)),
        "bridged_continuity": safe_float(dom.get("bridged_continuity", 0.0)),
        "pair_count": safe_float(dom.get("count", 0.0)),
        "pair_duration_frames": int(safe_float(ds.get("pair_duration_frames", 0))),
        "mean_longitudinal_velocity_rel": ds.get("mean_longitudinal_velocity_rel", None),
        "max_abs_lateral_velocity_rel": ds.get("max_abs_lateral_velocity_rel", None),
        "min_ttc_eff": ds.get("min_ttc_eff", None),
        "min_thw_eff": ds.get("min_thw_eff", None),
        "lane_change_count_pair": int(safe_float(ds.get("lane_change_count_pair", 0))),
        "direct_shared_observed_pair_points": int(safe_float(ds.get("observed_pair_points", 0))),
        "intersection_prior": safe_float(sp.get("intersection_prior", 0.0)),
        "turning_scene_prior": safe_float(sp.get("turning_scene_prior", 0.0)),
        "turn_candidate_boost": safe_float(sp.get("turn_candidate_boost", 0.0)),
        "turn_candidate_run": safe_float(sp.get("turn_candidate_run", 0.0)),
        "turn_evidence": safe_float(sp.get("turn_evidence", 0.0)),
    }

    keys = [
        "approach_score",
        "ttc_score",
        "same_lane_score",
        "front_back_order_score",
        "lateral_shift_score",
        "cutin_continuity",
        "side_overlap_growth",
        "convergence_score",
        "direction_change_score",
        "path_crossing_score",
        "off_lane_conflict_score",
        "longitudinal_dominance",
    ]
    for k in keys:
        row[f"onset_{k}"] = g(onset, k)
        row[f"impact_{k}"] = g(impact, k)
        row[f"post_{k}"] = g(post, k)
        row[f"delta_post_onset_{k}"] = g(post, k) - g(onset, k)
        row[f"delta_impact_onset_{k}"] = g(impact, k) - g(onset, k)

    # Minimal "must-have bridge" composites
    row["feat_longitudinal_closing"] = 0.6 * row["impact_approach_score"] + 0.4 * row["impact_ttc_score"]
    row["feat_lateral_change"] = 0.55 * row["impact_lateral_shift_score"] + 0.45 * row["impact_cutin_continuity"]
    row["feat_lane_relation"] = row["impact_same_lane_score"]
    row["feat_direction_relation"] = row["impact_direction_change_score"]
    row["feat_pair_temporal_consistency"] = 0.5 * row["bridged_coverage"] + 0.5 * row["bridged_continuity"]
    row["feat_lane_behavior_strength"] = 0.4 * row["impact_lateral_shift_score"] + 0.3 * row["impact_cutin_continuity"] + 0.3 * row["impact_side_overlap_growth"]
    row["feat_rear_behavior_strength"] = 0.45 * row["impact_same_lane_score"] + 0.35 * row["impact_front_back_order_score"] + 0.20 * row["impact_ttc_score"]
    return row


def infer_split(label_path: Path, explicit_split: str) -> str:
    if explicit_split:
        return explicit_split
    n = label_path.name.lower()
    if "train" in n:
        return "train"
    if "val" in n:
        return "val"
    if "test" in n:
        return "test"
    if "board" in n:
        return "board"
    return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build native trajectory features from labels by re-running video_keyframe extractor.")
    parser.add_argument("--labels", required=True)
    parser.add_argument("--videos-root", default="backend/videos")
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--out-jsonl", required=True)
    parser.add_argument("--split", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--path-alias", action="append", default=[])
    parser.add_argument("--strict-missing", action="store_true")
    args = parser.parse_args()

    labels_path = Path(args.labels).resolve()
    videos_root = Path(args.videos_root).resolve()
    out_csv = Path(args.out_csv).resolve()
    out_jsonl = Path(args.out_jsonl).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    alias_map = parse_path_aliases(args.path_alias or [])
    rows = load_jsonl(labels_path)
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]
    split = infer_split(labels_path, args.split)

    out_rows: List[Dict[str, Any]] = []
    miss = 0
    fail = 0
    for i, label in enumerate(rows, start=1):
        video_ref = str(label.get("video", "")).strip()
        if not video_ref:
            continue
        video_path = resolve_video(video_ref, videos_root, alias_map)
        if not video_path.exists():
            miss += 1
            msg = f"[WARN] missing video: {video_path}"
            if args.strict_missing:
                raise FileNotFoundError(msg)
            print(msg)
            continue
        print(f"[INFO] ({i}/{len(rows)}) extract {video_ref}")
        try:
            seq = extract_sequence_features(video_path, include_frames=False, verbose=False)
            out_rows.append(extract_row(label, seq, video_ref=video_ref, split=split))
        except Exception as exc:
            fail += 1
            msg = f"[WARN] extract failed: {video_ref} err={exc}"
            if args.strict_missing:
                raise RuntimeError(msg) from exc
            print(msg)

    pd.DataFrame(out_rows).to_csv(out_csv, index=False, encoding="utf-8-sig")
    write_jsonl(out_jsonl, out_rows)
    print(json.dumps({"labels": str(labels_path), "rows": len(out_rows), "missing_video": miss, "extract_failed": fail, "out_csv": str(out_csv), "out_jsonl": str(out_jsonl)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
