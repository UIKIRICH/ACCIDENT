import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


FOUR_CLASSES = {"rear_end", "lane_change", "turn_conflict", "generic"}
THREE_CLASSES = {"rear_end", "lane_change", "turn_conflict"}
ALLOWED_SCENE_TAGS = {
    "day",
    "night",
    "rain",
    "intersection",
    "occlusion",
    "highway",
    "urban",
    "turning_scene",
    "straight_road",
    "crowded",
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
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def to_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def strip_internal(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    out.pop("_line_no", None)
    return out


def analyze_row(
    row: Dict[str, Any],
    max_post_impact_gap_warn: float,
    max_span_warn: float,
    generic_with_times_policy: str,
) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warns: List[str] = []

    accident_type = str(row.get("accident_type", "")).strip()
    video = str(row.get("video", "")).strip()
    scene_tags = row.get("scene_tags", [])

    if accident_type not in FOUR_CLASSES:
        errors.append("invalid_accident_type")
    if not video:
        errors.append("empty_video")

    if not isinstance(scene_tags, list):
        errors.append("scene_tags_not_list")
        scene_tags = []
    else:
        unknown_tags = [str(x) for x in scene_tags if str(x) not in ALLOWED_SCENE_TAGS]
        if unknown_tags:
            warns.append("unknown_scene_tags")
        if len(scene_tags) == 0:
            warns.append("empty_scene_tags")

    onset = to_float(row.get("onset_time"))
    impact = to_float(row.get("impact_time"))
    post = to_float(row.get("post_time"))

    if accident_type in THREE_CLASSES:
        if onset is None or impact is None or post is None:
            errors.append("missing_three_stage_times")
            return errors, warns

        if onset < 0 or impact < 0 or post < 0:
            errors.append("negative_time_value")
        if onset > impact or impact > post:
            errors.append("time_order_invalid")

        if not errors:
            impact_gap = impact - onset
            post_gap = post - impact
            total_span = post - onset

            if impact_gap > 3.0:
                warns.append("large_impact_onset_gap")
            if post_gap > max_post_impact_gap_warn:
                warns.append("large_post_impact_gap")
            if total_span > max_span_warn:
                warns.append("large_total_span")
    else:
        # generic can be no-collision; missing times are allowed.
        has_any_time = onset is not None or impact is not None or post is not None
        if has_any_time and generic_with_times_policy == "warn":
            warns.append("generic_with_times")

    return errors, warns


def main() -> None:
    parser = argparse.ArgumentParser(description="Quality split labels into high_conf, relaxed, and review queue.")
    parser.add_argument("--input", required=True, help="Input normalized labels jsonl")
    parser.add_argument("--out-high-conf-3cls", required=True, help="Output strict high-confidence 3-class jsonl")
    parser.add_argument("--out-relaxed-3cls", required=True, help="Output relaxed 3-class jsonl (errors-free)")
    parser.add_argument("--out-review-queue", required=True, help="Output review queue jsonl")
    parser.add_argument("--out-generic-pool", required=True, help="Output generic pool jsonl")
    parser.add_argument("--report", required=True, help="Output quality report json")
    parser.add_argument("--max-post-impact-gap-warn", type=float, default=10.0)
    parser.add_argument("--max-span-warn", type=float, default=20.0)
    parser.add_argument(
        "--generic-with-times-policy",
        choices=["info", "warn"],
        default="info",
        help="Whether generic rows with time fields should enter warning queue",
    )
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    rows = load_jsonl(input_path)

    high_conf_3cls: List[Dict[str, Any]] = []
    relaxed_3cls: List[Dict[str, Any]] = []
    review_queue: List[Dict[str, Any]] = []
    generic_pool: List[Dict[str, Any]] = []

    error_counter: Counter[str] = Counter()
    warn_counter: Counter[str] = Counter()
    quality_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    quality_by_type: Dict[str, Counter[str]] = defaultdict(Counter)

    for row in rows:
        row_clean = strip_internal(row)
        accident_type = str(row_clean.get("accident_type", "")).strip()
        type_counter[accident_type] += 1

        errors, warns = analyze_row(
            row_clean,
            max_post_impact_gap_warn=float(args.max_post_impact_gap_warn),
            max_span_warn=float(args.max_span_warn),
            generic_with_times_policy=str(args.generic_with_times_policy),
        )

        for e in errors:
            error_counter[e] += 1
        for w in warns:
            warn_counter[w] += 1

        if errors:
            quality = "needs_fix"
        elif warns:
            quality = "review_recommended"
        else:
            quality = "high_conf"
        quality_counter[quality] += 1
        quality_by_type[accident_type][quality] += 1

        if accident_type == "generic":
            generic_pool.append(row_clean)

        if accident_type in THREE_CLASSES and not errors:
            relaxed_3cls.append(row_clean)
            if not warns:
                high_conf_3cls.append(row_clean)

        if errors or warns:
            review_item = dict(row_clean)
            review_item["quality_level"] = quality
            review_item["errors"] = errors
            review_item["warnings"] = warns
            review_queue.append(review_item)

    out_high_conf = Path(args.out_high_conf_3cls).resolve()
    out_relaxed = Path(args.out_relaxed_3cls).resolve()
    out_review = Path(args.out_review_queue).resolve()
    out_generic = Path(args.out_generic_pool).resolve()
    out_report = Path(args.report).resolve()

    dump_jsonl(out_high_conf, high_conf_3cls)
    dump_jsonl(out_relaxed, relaxed_3cls)
    dump_jsonl(out_review, review_queue)
    dump_jsonl(out_generic, generic_pool)

    report = {
        "input": str(input_path),
        "total_rows": len(rows),
        "type_distribution": dict(type_counter),
        "quality_distribution": dict(quality_counter),
        "high_conf_3cls_rows": len(high_conf_3cls),
        "relaxed_3cls_rows": len(relaxed_3cls),
        "generic_pool_rows": len(generic_pool),
        "review_queue_rows": len(review_queue),
        "error_counts": dict(error_counter),
        "warning_counts": dict(warn_counter),
        "quality_by_type": {k: dict(v) for k, v in quality_by_type.items()},
        "thresholds": {
            "max_post_impact_gap_warn": float(args.max_post_impact_gap_warn),
            "max_span_warn": float(args.max_span_warn),
            "generic_with_times_policy": str(args.generic_with_times_policy),
        },
        "outputs": {
            "high_conf_3cls": str(out_high_conf),
            "relaxed_3cls": str(out_relaxed),
            "review_queue": str(out_review),
            "generic_pool": str(out_generic),
        },
    }
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] high_conf_3cls={out_high_conf} rows={len(high_conf_3cls)}")
    print(f"[DONE] relaxed_3cls={out_relaxed} rows={len(relaxed_3cls)}")
    print(f"[DONE] review_queue={out_review} rows={len(review_queue)}")
    print(f"[DONE] generic_pool={out_generic} rows={len(generic_pool)}")
    print(f"[DONE] report={out_report}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
