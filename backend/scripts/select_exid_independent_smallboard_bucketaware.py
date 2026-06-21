import argparse
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


THREE_CLS = {"rear_end", "lane_change", "turn_conflict"}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
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


def normalize_text(v: Any) -> str:
    return str(v).replace("\\", "/").strip()


def parse_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                return [s]
        return [s]
    return []


def derive_tags_from_scene_profile(scene_profile: Any, extra_scene_tags: Any) -> List[str]:
    prof = str(scene_profile or "").strip().lower()
    extra = str(extra_scene_tags or "").strip().lower()
    tags: Set[str] = set()
    if "day" in prof:
        tags.add("day")
    if "night" in prof:
        tags.add("night")
    if "rain" in prof:
        tags.add("rain")
    if "intersection" in prof:
        tags.add("intersection")
    if "straight" in prof:
        tags.add("straight_road")
    if "highway" in prof:
        tags.add("highway")
    if "turning" in prof:
        tags.add("turning_scene")
    for tok in extra.replace(";", ",").split(","):
        t = tok.strip().replace("scene_", "")
        if t:
            tags.add(t)
    return sorted(tags)


def scene_bucket(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    is_day = "day" in s
    is_night = "night" in s
    is_straight = ("straight_road" in s) or ("highway" in s)
    is_inter = "intersection" in s
    if is_day and is_straight:
        return "day+straight_road"
    if is_day and is_inter:
        return "day+intersection"
    if is_night and is_straight:
        return "night+straight_road"
    if is_night and is_inter:
        return "night+intersection"
    return "other"


def explainable_other(tags: List[str]) -> bool:
    s = {str(x).strip() for x in tags if str(x).strip()}
    # Enforce explainable other only; avoid untagged/ambiguous default-other.
    return any(k in s for k in {"rain", "urban", "crowded", "occlusion", "turning_scene"})


def other_subscene(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    if "turning_scene" in s or "occlusion" in s:
        return "scope_edge"
    if "rain" in s or "urban" in s or "crowded" in s:
        return "contextual"
    return "other_default"


def resolve_pool_video_to_real_path(video_name: str, videos_root: Path) -> Optional[str]:
    fn = normalize_text(video_name).split("/")[-1]
    if not fn:
        return None
    for sub in ["extra train", "extra val", "extra video", "train", "var", "test"]:
        candidate = videos_root / sub / fn
        if candidate.exists():
            return f"{sub}/{fn}".replace("\\", "/")
    return None


def load_exclude_sets(paths: List[str]) -> Tuple[Set[str], Set[str]]:
    exclude_ids: Set[str] = set()
    exclude_videos: Set[str] = set()
    for raw in paths:
        p = Path(raw).resolve()
        if not p.exists():
            continue
        for r in load_jsonl(p):
            sid = normalize_text(r.get("sample_id", ""))
            vid = normalize_text(r.get("video", ""))
            if sid:
                exclude_ids.add(sid)
            if vid:
                exclude_videos.add(vid)
    return exclude_ids, exclude_videos


def build_reference_maps(
    reference_label_jsonl: List[Path], labels_v3_pool_jsonl: Path
) -> Tuple[
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
    Dict[str, Dict[str, Any]],
]:
    ref_by_sid: Dict[str, Dict[str, Any]] = {}
    ref_by_video: Dict[str, Dict[str, Any]] = {}
    for fp in reference_label_jsonl:
        for r in load_jsonl(fp):
            sid = normalize_text(r.get("sample_id", ""))
            vid = normalize_text(r.get("video", ""))
            typ = normalize_text(r.get("accident_type", ""))
            tags = parse_scene_tags(r.get("scene_tags", []))
            if typ not in THREE_CLS or not tags:
                continue
            payload = {"accident_type": typ, "scene_tags": tags, "source": fp.name}
            if sid and sid not in ref_by_sid:
                ref_by_sid[sid] = payload
            if vid and vid not in ref_by_video:
                ref_by_video[vid] = payload

    pool_by_sid: Dict[str, Dict[str, Any]] = {}
    pool_by_filename: Dict[str, Dict[str, Any]] = {}
    for r in load_jsonl(labels_v3_pool_jsonl):
        sid = normalize_text(r.get("sample_id", ""))
        typ = normalize_text(r.get("accident_type", ""))
        if typ not in THREE_CLS:
            continue
        tags = derive_tags_from_scene_profile(r.get("scene_profile", ""), r.get("extra_scene_tags", ""))
        if not tags:
            continue
        payload = {"accident_type": typ, "scene_tags": tags, "source": labels_v3_pool_jsonl.name}
        if sid and sid not in pool_by_sid:
            pool_by_sid[sid] = payload
        fn = normalize_text(r.get("video", "")).split("/")[-1]
        if fn and fn not in pool_by_filename:
            pool_by_filename[fn] = payload

    return ref_by_sid, ref_by_video, pool_by_sid, pool_by_filename


def recover_label_and_tags(
    active_sid: str,
    active_video: str,
    ref_by_sid: Dict[str, Dict[str, Any]],
    ref_by_video: Dict[str, Dict[str, Any]],
    pool_by_sid: Dict[str, Dict[str, Any]],
    pool_by_filename: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    # 1) direct sid
    if active_sid in ref_by_sid:
        return dict(ref_by_sid[active_sid], match_mode="direct_sid")
    if active_sid in pool_by_sid:
        return dict(pool_by_sid[active_sid], match_mode="direct_sid_pool")

    # 2) active sid tail -> train/val/test sid
    m = re.match(r"^active\d+_\d+_(.+)$", active_sid)
    if m:
        tail = m.group(1)
        for prefix in ["train_", "val_", "test_"]:
            sid2 = f"{prefix}{tail}"
            if sid2 in ref_by_sid:
                return dict(ref_by_sid[sid2], match_mode="tail_sid")
            if sid2 in pool_by_sid:
                return dict(pool_by_sid[sid2], match_mode="tail_sid_pool")

    # 3) direct video path
    if active_video in ref_by_video:
        return dict(ref_by_video[active_video], match_mode="direct_video")

    # 4) filename match to labels_v3_pool
    fn = active_video.split("/")[-1]
    if fn in pool_by_filename:
        return dict(pool_by_filename[fn], match_mode="filename_pool")

    return None


def pick_n(rng: random.Random, rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    arr = list(rows)
    arr.sort(key=lambda x: (str(x.get("sample_id", "")), str(x.get("video", ""))))
    rng.shuffle(arr)
    return arr[: max(0, int(n))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Select independent small board for bucket-aware reconfirm (active pool + recovered tags/labels).")
    parser.add_argument("--active-raw", default="data/processed/labels_active_pool_unseen180_20260504.raw.jsonl")
    parser.add_argument("--videos-root", required=True)
    parser.add_argument(
        "--reference-label-jsonl",
        action="append",
        default=[
            "data/processed/labels_train_external_labeled_20260413_102622.3cls.jsonl",
            "data/processed/labels_extra_train_annotation_labeled_20260510.jsonl",
            "data/processed/labels_extra_val_annotation_labeled_20260505.jsonl",
            "data/processed/labels_extra_video_annotation_labeled_20260505.jsonl",
        ],
    )
    parser.add_argument("--labels-v3-pool-jsonl", default="outputs/fusion_v3/reports/labels_v3_pool_3cls.jsonl")
    parser.add_argument("--exclude-jsonl", action="append", default=[])
    parser.add_argument("--target-n", type=int, default=32)
    parser.add_argument("--seed", type=int, default=20260510)
    parser.add_argument("--q-night-straight", type=int, default=6)
    parser.add_argument("--q-other-explainable", type=int, default=6)
    parser.add_argument("--q-day-straight", type=int, default=10)
    parser.add_argument("--q-day-intersection", type=int, default=10)
    parser.add_argument("--out-labels", required=True)
    parser.add_argument("--out-summary-json", required=True)
    parser.add_argument("--out-pool-audit-jsonl", default="")
    args = parser.parse_args()

    active_raw = Path(args.active_raw).resolve()
    videos_root = Path(args.videos_root).resolve()
    labels_v3_pool_jsonl = Path(args.labels_v3_pool_jsonl).resolve()
    reference_label_jsonl = [Path(x).resolve() for x in (args.reference_label_jsonl or [])]
    out_labels = Path(args.out_labels).resolve()
    out_summary = Path(args.out_summary_json).resolve()
    out_pool_audit = Path(args.out_pool_audit_jsonl).resolve() if args.out_pool_audit_jsonl else None
    rng = random.Random(int(args.seed))

    exclude_ids, exclude_videos = load_exclude_sets(args.exclude_jsonl or [])
    ref_by_sid, ref_by_video, pool_by_sid, pool_by_filename = build_reference_maps(reference_label_jsonl, labels_v3_pool_jsonl)

    recovered_pool: List[Dict[str, Any]] = []
    recover_stats = Counter()
    for r in load_jsonl(active_raw):
        sid = normalize_text(r.get("sample_id", ""))
        vid = normalize_text(r.get("video", ""))
        split = normalize_text(r.get("split", "train")) or "train"
        if not sid or not vid:
            recover_stats["drop_empty_sid_or_video"] += 1
            continue
        if sid in exclude_ids or vid in exclude_videos:
            recover_stats["drop_excluded"] += 1
            continue
        if not (videos_root / vid).exists():
            recover_stats["drop_missing_video"] += 1
            continue
        ref = recover_label_and_tags(
            active_sid=sid,
            active_video=vid,
            ref_by_sid=ref_by_sid,
            ref_by_video=ref_by_video,
            pool_by_sid=pool_by_sid,
            pool_by_filename=pool_by_filename,
        )
        if not ref:
            recover_stats["drop_unmatched_ref"] += 1
            continue
        typ = normalize_text(ref.get("accident_type", ""))
        tags = parse_scene_tags(ref.get("scene_tags", []))
        if typ not in THREE_CLS:
            recover_stats["drop_non3cls"] += 1
            continue
        if not tags:
            recover_stats["drop_empty_tags_after_recover"] += 1
            continue
        b = scene_bucket(tags)
        rec = {
            "sample_id": sid,
            "split": split,
            "video": vid,
            "accident_type": typ,
            "onset_time": None,
            "impact_time": None,
            "post_time": None,
            "scene_tags": tags,
            "_bucket": b,
            "_other_subscene": other_subscene(tags) if b == "other" else "",
            "_match_mode": str(ref.get("match_mode", "")),
            "_label_source": str(ref.get("source", "")),
        }
        recovered_pool.append(rec)
        recover_stats["keep"] += 1

    # Deduplicate by sample_id (active pool should be unique; keep first stable ordering).
    dedup: Dict[str, Dict[str, Any]] = {}
    for r in recovered_pool:
        sid = r["sample_id"]
        if sid not in dedup:
            dedup[sid] = r
    recovered_pool = list(dedup.values())

    # Build 4 target groups.
    g_night = [r for r in recovered_pool if r["_bucket"] == "night+straight_road"]
    g_other = [r for r in recovered_pool if r["_bucket"] == "other" and explainable_other(r.get("scene_tags", []))]
    g_day_straight = [r for r in recovered_pool if r["_bucket"] == "day+straight_road"]
    g_day_inter = [r for r in recovered_pool if r["_bucket"] == "day+intersection"]
    g_night_inter = [r for r in recovered_pool if r["_bucket"] == "night+intersection"]

    requested = {
        "night+straight_road": int(args.q_night_straight),
        "other_explainable": int(args.q_other_explainable),
        "day+straight_road": int(args.q_day_straight),
        "day+intersection": int(args.q_day_intersection),
    }
    available = {
        "night+straight_road": len(g_night),
        "other_explainable": len(g_other),
        "day+straight_road": len(g_day_straight),
        "day+intersection": len(g_day_inter),
        "night+intersection": len(g_night_inter),
    }
    effective = {k: min(int(v), int(available.get(k, 0))) for k, v in requested.items()}
    unmet = {
        k: {"requested": int(requested[k]), "available": int(available.get(k, 0))}
        for k in requested
        if int(available.get(k, 0)) < int(requested[k])
    }

    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()

    # Phase 1: guaranteed quota per target group.
    for key, group in [
        ("night+straight_road", g_night),
        ("other_explainable", g_other),
        ("day+straight_road", g_day_straight),
        ("day+intersection", g_day_inter),
    ]:
        take = int(effective[key])
        for r in pick_n(rng, group, take):
            sid = r["sample_id"]
            if sid in selected_ids:
                continue
            selected.append(r)
            selected_ids.add(sid)

    # Phase 2: fill to target-n with fallback order.
    target_n = int(args.target_n)
    fill_order = [
        g_day_inter,
        g_day_straight,
        g_night_inter,
        g_other,
        g_night,
    ]
    for group in fill_order:
        if len(selected) >= target_n:
            break
        for r in pick_n(rng, [x for x in group if x["sample_id"] not in selected_ids], len(group)):
            if len(selected) >= target_n:
                break
            sid = r["sample_id"]
            if sid in selected_ids:
                continue
            selected.append(r)
            selected_ids.add(sid)

    # Strip helper keys before writing labels.
    out_rows: List[Dict[str, Any]] = []
    for r in selected:
        rr = dict(r)
        rr.pop("_bucket", None)
        rr.pop("_other_subscene", None)
        rr.pop("_match_mode", None)
        rr.pop("_label_source", None)
        out_rows.append(rr)
    write_jsonl(out_labels, out_rows)

    selected_bucket_dist = Counter(scene_bucket(parse_scene_tags(r.get("scene_tags", []))) for r in out_rows)
    selected_class_dist = Counter(str(r.get("accident_type", "")).strip() for r in out_rows)
    selected_split_dist = Counter(str(r.get("split", "")).strip() for r in out_rows)
    selected_match_mode_dist = Counter(r["_match_mode"] for r in selected)
    selected_label_source_dist = Counter(r["_label_source"] for r in selected)
    selected_other_subscene_dist = Counter(r["_other_subscene"] for r in selected if r["_bucket"] == "other")

    summary = {
        "mode": "exid_independent_smallboard_bucketaware_selection",
        "seed": int(args.seed),
        "target_n": int(target_n),
        "selected_n": int(len(out_rows)),
        "requested_quotas": requested,
        "available_pool": available,
        "effective_quotas": effective,
        "unmet_requested_quotas": unmet,
        "selected_bucket_dist": {k: int(v) for k, v in selected_bucket_dist.items()},
        "selected_class_dist": {k: int(v) for k, v in selected_class_dist.items()},
        "selected_split_dist": {k: int(v) for k, v in selected_split_dist.items()},
        "selected_other_subscene_dist": {k: int(v) for k, v in selected_other_subscene_dist.items()},
        "recover_stats": {k: int(v) for k, v in recover_stats.items()},
        "selected_match_mode_dist": {k: int(v) for k, v in selected_match_mode_dist.items()},
        "selected_label_source_dist": {k: int(v) for k, v in selected_label_source_dist.items()},
        "independence": {
            "exclude_ids_n": int(len(exclude_ids)),
            "exclude_videos_n": int(len(exclude_videos)),
            "selected_conflict_with_exclude": False,
        },
        "paths": {
            "active_raw": str(active_raw),
            "labels_v3_pool_jsonl": str(labels_v3_pool_jsonl),
            "out_labels": str(out_labels),
        },
        "gate_readiness_flags": {
            "has_rear_gt_support_expected": bool(selected_class_dist.get("rear_end", 0) > 0),
            "has_lane_gt_support_expected": bool(selected_class_dist.get("lane_change", 0) > 0),
            "night_straight_support_ge_2": bool(selected_bucket_dist.get("night+straight_road", 0) >= 2),
            "other_explainable_support_ge_4": bool(selected_bucket_dist.get("other", 0) >= 4),
        },
    }
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if out_pool_audit is not None:
        out_pool_audit.parent.mkdir(parents=True, exist_ok=True)
        audit_rows: List[Dict[str, Any]] = []
        for r in recovered_pool:
            audit_rows.append(
                {
                    "sample_id": r["sample_id"],
                    "video": r["video"],
                    "accident_type": r["accident_type"],
                    "scene_tags": r["scene_tags"],
                    "scene_bucket": r["_bucket"],
                    "other_subscene": r["_other_subscene"],
                    "match_mode": r["_match_mode"],
                    "label_source": r["_label_source"],
                }
            )
        write_jsonl(out_pool_audit, audit_rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

