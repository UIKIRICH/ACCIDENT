import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


THREE_CLASSES = {"rear_end", "lane_change", "turn_conflict"}


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
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
            rows.append(obj)
    return rows


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def normalize_video(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def canonical_group_key(video_field: str) -> str:
    stem = Path(video_field).stem.lower().strip()
    stem = re.sub(r"_[0-9a-f]{8}$", "", stem)
    stem = re.sub(r"^aug_\d+_", "", stem)
    stem = re.sub(r"[^a-z0-9_]+", "_", stem)
    return stem if stem else "unknown_group"


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def parse_allow_classes(s: str) -> Set[str]:
    out = set()
    for token in str(s).split(","):
        t = token.strip()
        if t:
            out.add(t)
    return out


def collect_test_leakage_sets(test_rows: List[Dict[str, Any]]) -> Tuple[Set[str], Set[str]]:
    test_videos: Set[str] = set()
    test_groups: Set[str] = set()
    for row in test_rows:
        video = normalize_video(row.get("video", ""))
        if not video:
            continue
        test_videos.add(video)
        gid = str(row.get("group_id", "")).strip()
        if not gid:
            gid = canonical_group_key(video)
        test_groups.add(gid)
    return test_videos, test_groups


def row_is_valid_time(row: Dict[str, Any]) -> bool:
    # Keep only rows with legal onset<=impact<=post.
    if row.get("onset_time", None) is None:
        return False
    if row.get("impact_time", None) is None:
        return False
    if row.get("post_time", None) is None:
        return False
    onset = safe_float(row.get("onset_time", 0.0))
    impact = safe_float(row.get("impact_time", 0.0))
    post = safe_float(row.get("post_time", 0.0))
    return onset <= impact <= post


def normalize_scene_tags(row: Dict[str, Any]) -> None:
    tags = row.get("scene_tags", [])
    if isinstance(tags, list):
        row["scene_tags"] = [str(x).strip() for x in tags if str(x).strip()]
        return
    if isinstance(tags, str):
        s = tags.strip()
        if not s:
            row["scene_tags"] = []
            return
        if s.startswith("[") and s.endswith("]"):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    row["scene_tags"] = [str(x).strip() for x in parsed if str(x).strip()]
                    return
            except json.JSONDecodeError:
                pass
        parts = [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]
        row["scene_tags"] = parts
        return
    row["scene_tags"] = []


def normalize_row(row: Dict[str, Any], source_tag: str) -> Dict[str, Any]:
    out = dict(row)
    out["video"] = normalize_video(out.get("video", ""))
    out["accident_type"] = str(out.get("accident_type", "")).strip()
    out["onset_time"] = safe_float(out.get("onset_time", 0.0))
    out["impact_time"] = safe_float(out.get("impact_time", 0.0))
    out["post_time"] = safe_float(out.get("post_time", 0.0))
    sample_id = str(out.get("sample_id", "")).strip()
    if not sample_id:
        sample_id = Path(out["video"]).stem
        out["sample_id"] = sample_id
    gid = str(out.get("group_id", "")).strip()
    if not gid:
        gid = canonical_group_key(out["video"])
        out["group_id"] = gid
    normalize_scene_tags(out)
    if "source_dataset" not in out or not str(out.get("source_dataset", "")).strip():
        out["source_dataset"] = source_tag
    if "split" in out and str(out.get("split", "")).strip().lower() == "test":
        out["split"] = "train"
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge v3.4 train/val pool with strict no-test-leakage guard.")
    parser.add_argument("--base", required=True, help="Base train/val pool jsonl (e.g. high_conf_v3_final.jsonl)")
    parser.add_argument(
        "--supplement",
        required=True,
        nargs="+",
        help="One or more supplement jsonl files (new samples)",
    )
    parser.add_argument("--test", required=True, help="Frozen test jsonl")
    parser.add_argument("--out", required=True, help="Merged train/val pool jsonl output")
    parser.add_argument("--out-report", required=True, help="Merge report json output")
    parser.add_argument(
        "--allow-supplement-classes",
        default="rear_end,lane_change",
        help="Comma separated allowed classes from supplements",
    )
    parser.add_argument(
        "--strict-time-check",
        action="store_true",
        help="Drop rows with illegal onset/impact/post order",
    )
    args = parser.parse_args()

    base_path = Path(args.base).resolve()
    sup_paths = [Path(x).resolve() for x in args.supplement]
    test_path = Path(args.test).resolve()
    out_path = Path(args.out).resolve()
    out_report = Path(args.out_report).resolve()
    allow_supp_classes = parse_allow_classes(args.allow_supplement_classes)

    base_rows_raw = load_jsonl(base_path)
    test_rows = load_jsonl(test_path)
    test_videos, test_groups = collect_test_leakage_sets(test_rows)

    merged: List[Dict[str, Any]] = []
    seen_sid: Set[str] = set()
    seen_video: Set[str] = set()

    report: Dict[str, Any] = {
        "base": str(base_path),
        "supplement": [str(x) for x in sup_paths],
        "test": str(test_path),
        "allow_supplement_classes": sorted(list(allow_supp_classes)),
        "strict_time_check": bool(args.strict_time_check),
        "base_rows_input": len(base_rows_raw),
        "base_rows_kept": 0,
        "supplement_rows_input": 0,
        "supplement_rows_kept": 0,
        "drop_counts": {
            "non_3class": 0,
            "invalid_time": 0,
            "test_video_overlap": 0,
            "test_group_overlap": 0,
            "duplicate_sample_id": 0,
            "duplicate_video": 0,
            "supplement_class_filtered": 0,
            "missing_video": 0,
        },
        "class_counts_output": {},
        "rows_output": 0,
    }

    for row in base_rows_raw:
        r = normalize_row(row, source_tag="BASE_V3")
        if not r["video"]:
            report["drop_counts"]["missing_video"] += 1
            continue
        cls = r["accident_type"]
        if cls not in THREE_CLASSES:
            report["drop_counts"]["non_3class"] += 1
            continue
        if args.strict_time_check and not row_is_valid_time(r):
            report["drop_counts"]["invalid_time"] += 1
            continue

        sid = str(r.get("sample_id", "")).strip()
        video = r["video"]
        if sid in seen_sid:
            report["drop_counts"]["duplicate_sample_id"] += 1
            continue
        if video in seen_video:
            report["drop_counts"]["duplicate_video"] += 1
            continue
        seen_sid.add(sid)
        seen_video.add(video)
        merged.append(r)

    report["base_rows_kept"] = len(merged)

    for sp in sup_paths:
        sup_rows_raw = load_jsonl(sp)
        report["supplement_rows_input"] += len(sup_rows_raw)
        for row in sup_rows_raw:
            r = normalize_row(row, source_tag=f"SUPPLEMENT_V34::{sp.stem}")
            if not r["video"]:
                report["drop_counts"]["missing_video"] += 1
                continue
            cls = r["accident_type"]
            if cls not in THREE_CLASSES:
                report["drop_counts"]["non_3class"] += 1
                continue
            if cls not in allow_supp_classes:
                report["drop_counts"]["supplement_class_filtered"] += 1
                continue
            if args.strict_time_check and not row_is_valid_time(r):
                report["drop_counts"]["invalid_time"] += 1
                continue

            video = r["video"]
            gid = str(r.get("group_id", "")).strip() or canonical_group_key(video)
            if video in test_videos:
                report["drop_counts"]["test_video_overlap"] += 1
                continue
            if gid in test_groups:
                report["drop_counts"]["test_group_overlap"] += 1
                continue

            sid = str(r.get("sample_id", "")).strip()
            if sid in seen_sid:
                report["drop_counts"]["duplicate_sample_id"] += 1
                continue
            if video in seen_video:
                report["drop_counts"]["duplicate_video"] += 1
                continue
            seen_sid.add(sid)
            seen_video.add(video)
            merged.append(r)
            report["supplement_rows_kept"] += 1

    merged = sorted(merged, key=lambda x: str(x.get("sample_id", "")))
    dump_jsonl(out_path, merged)

    class_counts: Dict[str, int] = {k: 0 for k in sorted(THREE_CLASSES)}
    for r in merged:
        cls = str(r.get("accident_type", "")).strip()
        if cls in class_counts:
            class_counts[cls] += 1
    report["class_counts_output"] = class_counts
    report["rows_output"] = len(merged)
    report["out"] = str(out_path)

    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

