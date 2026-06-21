import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.video_keyframe import extract_sequence_features  # noqa: E402


REQUIRED_LABEL_FIELDS = {
    "video",
    "accident_type",
    "onset_time",
    "impact_time",
    "post_time",
    "scene_tags",
}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} JSON decode error: {exc}") from exc
            rows.append(obj)
    return rows


def validate_label_rows(rows: Iterable[Dict[str, Any]], label_path: Path) -> None:
    for idx, row in enumerate(rows, start=1):
        missing = [k for k in REQUIRED_LABEL_FIELDS if k not in row]
        if missing:
            raise ValueError(
                f"{label_path}:{idx} missing required fields: {', '.join(missing)}"
            )


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def infer_split(label_file: Path, explicit_split: str) -> str:
    if explicit_split:
        return explicit_split
    name = label_file.stem.lower()
    if "train" in name:
        return "train"
    if "val" in name:
        return "val"
    if "test" in name:
        return "test"
    return "unknown"


def build_stage_map(selected_items: List[Dict[str, Any]]) -> Dict[int, str]:
    stage_map: Dict[int, str] = {}
    for item in selected_items:
        idx = int(item.get("idx", -1))
        stage = str(item.get("stage", ""))
        if idx >= 0:
            stage_map[idx] = stage
    return stage_map


def convert_scene_tags(scene_tags: Any) -> List[str]:
    if isinstance(scene_tags, list):
        return [str(x) for x in scene_tags]
    if scene_tags is None:
        return []
    return [str(scene_tags)]


def build_feature_rows(
    seq: Dict[str, Any],
    label: Dict[str, Any],
    split: str,
    video_ref: str,
    video_id: str,
    source_dataset: str,
) -> List[Dict[str, Any]]:
    samples = seq.get("samples", [])
    selected_items = seq.get("selected_items", [])
    stage_map = build_stage_map(selected_items)
    scene_tags = convert_scene_tags(label.get("scene_tags", []))
    dominant = seq.get("dominant_meta", {}) or {}
    risk_info = seq.get("risk_info", {}) or {}

    rows: List[Dict[str, Any]] = []
    for sample_idx, s in enumerate(samples):
        row = {
            "video": video_ref,
            "video_id": video_id,
            "split": split,
            "source_dataset": source_dataset,
            "scene_tags": json.dumps(scene_tags, ensure_ascii=False),
            "sample_idx": int(sample_idx),
            "sec": safe_float(s.get("sec", 0.0)),
            "stage_label": stage_map.get(sample_idx, ""),
            "is_selected_stage": int(sample_idx in stage_map),
            "onset_score_raw": safe_float(s.get("onset_score_raw", 0.0)),
            "impact_score_raw": safe_float(s.get("impact_score_raw", 0.0)),
            "post_score_raw": safe_float(s.get("post_score_raw", 0.0)),
            "event_score_raw": safe_float(s.get("event_score_raw", 0.0)),
            "rear_end_score_raw": safe_float(s.get("rear_end_score_raw", 0.0)),
            "lane_change_score_raw": safe_float(s.get("lane_change_score_raw", 0.0)),
            "turn_conflict_score_raw": safe_float(s.get("turn_conflict_score_raw", 0.0)),
            "onset_score": safe_float(s.get("onset_score", 0.0)),
            "impact_score": safe_float(s.get("impact_score", 0.0)),
            "post_score": safe_float(s.get("post_score", 0.0)),
            "event_score": safe_float(s.get("event_score", 0.0)),
            "onset_score_used": safe_float(s.get("onset_score_used", 0.0)),
            "impact_score_used": safe_float(s.get("impact_score_used", 0.0)),
            "post_score_used": safe_float(s.get("post_score_used", 0.0)),
            "event_score_used": safe_float(s.get("event_score_used", 0.0)),
            "dominance": safe_float(dominant.get("dominance", 0.0)),
            "bridged_coverage": safe_float(dominant.get("bridged_coverage", 0.0)),
            "risk_alert_time": safe_float(risk_info.get("risk_alert_time", 0.0)),
            "lead_time_sec": safe_float(risk_info.get("lead_time_sec", 0.0)),
            "risk_threshold": safe_float(risk_info.get("risk_threshold", 0.0)),
            "peak_risk": safe_float(risk_info.get("peak_risk", 0.0)),
            "risk_level": str(risk_info.get("risk_level", "unknown")),
            "uncertainty": safe_float(seq.get("uncertainty", 1.0)),
            "gt_accident_type": str(label.get("accident_type", "generic")),
            "gt_onset_time": safe_float(label.get("onset_time", 0.0)),
            "gt_impact_time": safe_float(label.get("impact_time", 0.0)),
            "gt_post_time": safe_float(label.get("post_time", 0.0)),
        }
        rows.append(row)
    return rows


def build_meta_row(
    seq: Dict[str, Any],
    label: Dict[str, Any],
    split: str,
    video_ref: str,
    video_id: str,
    source_dataset: str,
) -> Dict[str, Any]:
    samples = seq.get("samples", [])
    sample_times = [safe_float(s.get("sec", 0.0)) for s in samples]
    valid_mask = [1] * len(sample_times)
    scene_tags = convert_scene_tags(label.get("scene_tags", []))
    dominant = seq.get("dominant_meta", {}) or {}
    risk_info = seq.get("risk_info", {}) or {}
    scene_prior = seq.get("scene_prior", {}) or {}

    return {
        "video": video_ref,
        "video_id": video_id,
        "split": split,
        "source_dataset": source_dataset,
        "scene_tags": json.dumps(scene_tags, ensure_ascii=False),
        "num_steps": int(len(samples)),
        "sample_times": json.dumps(sample_times, ensure_ascii=False),
        "valid_mask": json.dumps(valid_mask, ensure_ascii=False),
        "has_samples": int(bool(seq.get("has_samples", False))),
        "fps": safe_float(seq.get("fps", 0.0)),
        "duration_seconds": safe_float(seq.get("duration_seconds", 0.0)),
        "pred_type_key": str(seq.get("accident_type_key", "generic")),
        "pred_type_label": str(seq.get("accident_type_label", "待分析")),
        "pred_type_confidence": safe_float(seq.get("type_confidence", 0.0)),
        "pred_type_probs": json.dumps(seq.get("type_probs", {}), ensure_ascii=False),
        "pred_type_scores": json.dumps(seq.get("type_scores", {}), ensure_ascii=False),
        "pred_onset_time": safe_float(seq.get("onset_sec", 0.0)),
        "pred_impact_time": safe_float(seq.get("impact_sec", 0.0)),
        "pred_post_time": safe_float(seq.get("post_sec", 0.0)),
        "risk_alert_time": safe_float(risk_info.get("risk_alert_time", 0.0)),
        "lead_time_sec": safe_float(risk_info.get("lead_time_sec", 0.0)),
        "risk_level": str(risk_info.get("risk_level", "unknown")),
        "uncertainty": safe_float(seq.get("uncertainty", 1.0)),
        "dominant_meta": json.dumps(dominant, ensure_ascii=False),
        "scene_prior": json.dumps(scene_prior, ensure_ascii=False),
        "scene_prior_intersection": safe_float(scene_prior.get("intersection_prior", 0.0)),
        "scene_prior_turning_scene": safe_float(scene_prior.get("turning_scene_prior", 0.0)),
        "scene_prior_turn_candidate_boost": safe_float(scene_prior.get("turn_candidate_boost", 0.0)),
        "scene_prior_turn_candidate_run": safe_float(scene_prior.get("turn_candidate_run", 0.0)),
        "scene_prior_turn_evidence": safe_float(scene_prior.get("turn_evidence", 0.0)),
        "scene_prior_router_score": safe_float(scene_prior.get("router_score", 0.0)),
        "scene_prior_stage2_score": safe_float(scene_prior.get("stage2_score", 0.0)),
        "scene_prior_stage2_applied": int(bool(scene_prior.get("stage2_applied", False))),
        "gt_accident_type": str(label.get("accident_type", "generic")),
        "gt_onset_time": safe_float(label.get("onset_time", 0.0)),
        "gt_impact_time": safe_float(label.get("impact_time", 0.0)),
        "gt_post_time": safe_float(label.get("post_time", 0.0)),
        "keyframe_times_gt": json.dumps(label.get("keyframe_times", []), ensure_ascii=False),
        "note": str(label.get("note", "")),
    }


def write_rows(rows: List[Dict[str, Any]], out_path: Path) -> Tuple[str, int]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix.lower()

    if suffix == ".parquet":
        try:
            import pandas as pd  # type: ignore

            pd.DataFrame(rows).to_parquet(out_path, index=False)
            return "parquet", len(rows)
        except Exception:
            fallback = out_path.with_suffix(".jsonl")
            with fallback.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            return "jsonl_fallback", len(rows)

    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return "jsonl", len(rows)


def resolve_video_path(video_root: Path, video_field: str) -> Path:
    p = Path(video_field)
    if p.is_absolute():
        return p
    return (video_root / p).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(description="Export rule-based temporal features.")
    parser.add_argument("--labels", required=True, help="Path to labels_*.jsonl")
    parser.add_argument("--video-root", default="backend/uploaded_videos", help="Root directory for relative video paths")
    parser.add_argument("--split", default="", help="Optional split name override: train/val/test")
    parser.add_argument("--out-features", required=True, help="Output features file (.parquet or .jsonl)")
    parser.add_argument("--out-meta", required=True, help="Output meta file (.parquet or .jsonl)")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of videos for quick test")
    parser.add_argument("--verbose", action="store_true", help="Print per-video progress")
    args = parser.parse_args()

    label_path = Path(args.labels).resolve()
    video_root = Path(args.video_root).resolve()
    out_features = Path(args.out_features).resolve()
    out_meta = Path(args.out_meta).resolve()

    rows = load_jsonl(label_path)
    validate_label_rows(rows, label_path)
    split = infer_split(label_path, args.split)

    feature_rows: List[Dict[str, Any]] = []
    meta_rows: List[Dict[str, Any]] = []
    processed = 0
    skipped = 0

    for i, row in enumerate(rows, start=1):
        if args.limit > 0 and processed >= args.limit:
            break

        video_ref = str(row["video"])
        video_id = str(row.get("video_id") or Path(video_ref).stem)
        source_dataset = str(row.get("source_dataset", "UNKNOWN"))
        video_path = resolve_video_path(video_root, video_ref)

        if not video_path.exists():
            skipped += 1
            print(f"[WARN] video not found, skip: {video_path}")
            continue

        if args.verbose:
            print(f"[INFO] [{i}/{len(rows)}] export {video_ref}")

        seq = extract_sequence_features(video_path, include_frames=False, verbose=False)
        feature_rows.extend(build_feature_rows(seq, row, split, video_ref, video_id, source_dataset))
        meta_rows.append(build_meta_row(seq, row, split, video_ref, video_id, source_dataset))
        processed += 1

    feature_fmt, feature_n = write_rows(feature_rows, out_features)
    meta_fmt, meta_n = write_rows(meta_rows, out_meta)

    print(
        f"[DONE] split={split}, processed={processed}, skipped={skipped}, "
        f"feature_rows={feature_n} ({feature_fmt}), meta_rows={meta_n} ({meta_fmt})"
    )
    print(f"[OUT] features={out_features}")
    print(f"[OUT] meta={out_meta}")


if __name__ == "__main__":
    main()
