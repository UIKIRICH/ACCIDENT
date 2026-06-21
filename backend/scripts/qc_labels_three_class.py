import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2


TARGET_CLASSES = {"rear_end", "lane_change", "turn_conflict"}
REQUIRED_FIELDS = {
    "sample_id",
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
            obj = json.loads(line)
            obj["_line_no"] = line_no
            rows.append(obj)
    return rows


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            row_copy = dict(row)
            row_copy.pop("_line_no", None)
            f.write(json.dumps(row_copy, ensure_ascii=False) + "\n")


def to_float(v: Any) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_video_duration_sec(video_path: Path) -> Tuple[Optional[float], str]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None, "video_open_failed"
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    total = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    cap.release()
    if fps <= 1e-6 or total <= 0:
        return None, "video_meta_invalid"
    return total / fps, ""


def normalize_scene_tags(v: Any) -> Tuple[List[str], bool]:
    if isinstance(v, list):
        tags = [str(x).strip() for x in v if str(x).strip()]
        return tags, True
    if v in (None, ""):
        return [], False
    return [str(v).strip()], False


def qc_row(
    row: Dict[str, Any],
    video_root: Path,
    max_span_warn_sec: float,
    duration_margin_sec: float,
) -> Tuple[List[str], List[str], Optional[float]]:
    errors: List[str] = []
    warns: List[str] = []

    missing_fields = [k for k in REQUIRED_FIELDS if k not in row]
    if missing_fields:
        errors.append("missing_required_fields")
        return errors, warns, None

    accident_type = str(row.get("accident_type", "")).strip()
    if accident_type not in TARGET_CLASSES:
        warns.append("non_target_class")
        return errors, warns, None

    video_rel = str(row.get("video", "")).strip()
    if not video_rel:
        errors.append("empty_video_path")
        return errors, warns, None

    video_path = Path(video_rel)
    if not video_path.is_absolute():
        video_path = (video_root / video_path).resolve()
    if not video_path.exists():
        errors.append("video_not_found")
        return errors, warns, None

    duration_sec, dur_err = get_video_duration_sec(video_path)
    if duration_sec is None:
        errors.append(dur_err)
        return errors, warns, None

    onset = to_float(row.get("onset_time"))
    impact = to_float(row.get("impact_time"))
    post = to_float(row.get("post_time"))
    if onset is None or impact is None or post is None:
        errors.append("missing_stage_times")
        return errors, warns, duration_sec

    if onset < 0 or impact < 0 or post < 0:
        errors.append("negative_stage_times")
    if not (onset <= impact <= post):
        errors.append("invalid_time_order")

    if post > duration_sec + duration_margin_sec:
        errors.append("post_exceeds_video_duration")
    elif impact > duration_sec + duration_margin_sec or onset > duration_sec + duration_margin_sec:
        errors.append("stage_time_exceeds_video_duration")

    span = post - onset
    if span > max_span_warn_sec:
        warns.append("long_event_span")

    tags, is_list = normalize_scene_tags(row.get("scene_tags"))
    if not is_list:
        warns.append("scene_tags_not_list")
    if len(tags) == 0:
        warns.append("scene_tags_empty")

    return errors, warns, duration_sec


def main() -> None:
    parser = argparse.ArgumentParser(description="QC labels for 3-class training without dropping raw samples.")
    parser.add_argument("--input", required=True, help="Input labels jsonl (recommended norm4)")
    parser.add_argument("--video-root", default="backend/videos", help="Root for relative video path")
    parser.add_argument("--out-high-conf", required=True, help="Output high_conf_train.jsonl")
    parser.add_argument("--out-review", required=True, help="Output review_queue.jsonl")
    parser.add_argument("--out-bad", required=True, help="Output bad_samples.jsonl")
    parser.add_argument("--report", required=True, help="Output qc_report.json")
    parser.add_argument("--max-span-warn-sec", type=float, default=20.0)
    parser.add_argument("--duration-margin-sec", type=float, default=0.3)
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    video_root = Path(args.video_root).resolve()
    rows = load_jsonl(input_path)

    high_conf: List[Dict[str, Any]] = []
    review: List[Dict[str, Any]] = []
    bad: List[Dict[str, Any]] = []

    err_counter: Counter[str] = Counter()
    warn_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()

    for row in rows:
        t = str(row.get("accident_type", "")).strip()
        type_counter[t] += 1

        errors, warns, duration_sec = qc_row(
            row=row,
            video_root=video_root,
            max_span_warn_sec=float(args.max_span_warn_sec),
            duration_margin_sec=float(args.duration_margin_sec),
        )
        for e in errors:
            err_counter[e] += 1
        for w in warns:
            warn_counter[w] += 1

        out_row = dict(row)
        out_row["qc_errors"] = errors
        out_row["qc_warnings"] = warns
        if duration_sec is not None:
            out_row["video_duration_sec"] = round(float(duration_sec), 3)

        if errors:
            bad.append(out_row)
            continue

        if warns:
            review.append(out_row)
            continue

        high_conf.append(out_row)

    out_high = Path(args.out_high_conf).resolve()
    out_review = Path(args.out_review).resolve()
    out_bad = Path(args.out_bad).resolve()
    out_report = Path(args.report).resolve()

    dump_jsonl(out_high, high_conf)
    dump_jsonl(out_review, review)
    dump_jsonl(out_bad, bad)

    report = {
        "input": str(input_path),
        "video_root": str(video_root),
        "total_rows": len(rows),
        "type_distribution": dict(type_counter),
        "high_conf_count": len(high_conf),
        "review_count": len(review),
        "bad_count": len(bad),
        "error_counts": dict(err_counter),
        "warning_counts": dict(warn_counter),
        "thresholds": {
            "max_span_warn_sec": float(args.max_span_warn_sec),
            "duration_margin_sec": float(args.duration_margin_sec),
        },
        "outputs": {
            "high_conf_train": str(out_high),
            "review_queue": str(out_review),
            "bad_samples": str(out_bad),
        },
    }
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] high_conf={out_high} rows={len(high_conf)}")
    print(f"[DONE] review={out_review} rows={len(review)}")
    print(f"[DONE] bad={out_bad} rows={len(bad)}")
    print(f"[DONE] report={out_report}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
