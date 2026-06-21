import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np


THREE_CLS = {"rear_end", "lane_change", "turn_conflict"}


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


def scene_profile_to_tags(scene_profile: str, extra_scene_tags: str) -> List[str]:
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


def bucket_from_tags(tags: List[str]) -> str:
    s = set(tags)
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


def is_other_explainable(tags: List[str], scene_profile: str) -> bool:
    s = set(tags)
    p = str(scene_profile or "").lower()
    if any(k in s for k in ["rain", "urban", "crowded", "occlusion", "turning_scene"]):
        return True
    return any(k in p for k in ["rain", "urban", "crowded", "occlusion", "turning"])


def resolve_video_for_pool(video_name: str, videos_root: Path) -> Optional[Path]:
    """labels_v3_pool video is mostly bare filename; map to likely folders first."""
    raw = str(video_name).replace("\\", "/").strip()
    p = Path(raw)
    direct = (videos_root / p).resolve()
    if direct.exists():
        return direct

    fn = p.name
    for sub in ["extra train", "extra val", "extra video", "train", "var", "test"]:
        cand = (videos_root / sub / fn).resolve()
        if cand.exists():
            return cand
    return None


def resolve_video_direct(video_ref: str, videos_root: Path) -> Optional[Path]:
    raw = str(video_ref).replace("\\", "/").strip()
    if not raw:
        return None
    p = (videos_root / raw).resolve()
    if p.exists():
        return p
    return None


def load_exclude_ids(paths: List[str]) -> Set[str]:
    out: Set[str] = set()
    for raw in paths:
        p = Path(raw).resolve()
        if not p.exists():
            continue
        for r in load_jsonl(p):
            sid = str(r.get("sample_id", "")).strip()
            if sid:
                out.add(sid)
    return out


def quick_video_stats(video_path: Path, sample_frames: int = 10) -> Tuple[float, float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 255.0, 0.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return 255.0, 0.0
    idxs = np.linspace(0, max(0, total - 1), num=max(2, sample_frames), dtype=np.int32)
    means: List[float] = []
    stds: List[float] = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        means.append(float(np.mean(gray)))
        stds.append(float(np.std(gray)))
    cap.release()
    if not means:
        return 255.0, 0.0
    return float(np.mean(means)), float(np.mean(stds))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build targeted independent supplement queue for scarce buckets.")
    parser.add_argument("--videos-root", required=True)
    parser.add_argument("--active-raw", default="data/processed/labels_active_pool_unseen180_20260504.raw.jsonl")
    parser.add_argument("--labels-v3-pool", default="outputs/fusion_v3/reports/labels_v3_pool_3cls.jsonl")
    parser.add_argument("--target-night", type=int, default=20)
    parser.add_argument("--target-other", type=int, default=15)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument("--exclude-jsonl", action="append", default=[])
    parser.add_argument("--out-direct-labeled", required=True)
    parser.add_argument("--out-to-annotate-raw", required=True)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    rng = random.Random(int(args.seed))
    videos_root = Path(args.videos_root).resolve()
    active_raw = Path(args.active_raw).resolve()
    labels_v3_pool = Path(args.labels_v3_pool).resolve()

    exclude_ids = load_exclude_ids(args.exclude_jsonl or [])

    # Step A: direct labeled (independent, already has 3cls labels + scene hints)
    direct_rows: List[Dict[str, Any]] = []
    for r in load_jsonl(labels_v3_pool):
        sid = str(r.get("sample_id", "")).strip()
        if not sid or sid in exclude_ids:
            continue
        typ = str(r.get("accident_type", "")).strip()
        if typ not in THREE_CLS:
            continue
        vp = resolve_video_for_pool(str(r.get("video", "")), videos_root)
        if vp is None:
            continue
        tags = scene_profile_to_tags(str(r.get("scene_profile", "")), str(r.get("extra_scene_tags", "")))
        b = bucket_from_tags(tags)
        # Keep only two targeted buckets:
        # 1) night+straight_road
        # 2) other_explainable (must be true "other", not day/night straight/intersection buckets)
        is_target_other = (b == "other") and is_other_explainable(tags, str(r.get("scene_profile", "")))
        if b != "night+straight_road" and not is_target_other:
            continue

        direct_rows.append(
            {
                "sample_id": sid,
                "split": "train",
                "video": str(vp.relative_to(videos_root)).replace("\\", "/"),
                "accident_type": typ,
                "onset_time": r.get("onset_time", None),
                "impact_time": r.get("impact_time", None),
                "post_time": r.get("post_time", None),
                "scene_tags": tags,
                "notes": "targeted_direct_labeled_from_labels_v3_pool",
                "_target_bucket": "night+straight_road" if b == "night+straight_road" else "other_explainable",
            }
        )

    # De-dup by sample_id
    tmp: Dict[str, Dict[str, Any]] = {}
    for r in direct_rows:
        sid = r["sample_id"]
        if sid not in tmp:
            tmp[sid] = r
    direct_rows = list(tmp.values())

    direct_night = [r for r in direct_rows if r["_target_bucket"] == "night+straight_road"]
    direct_other = [r for r in direct_rows if r["_target_bucket"] == "other_explainable"]
    direct_night.sort(key=lambda x: x["sample_id"])
    direct_other.sort(key=lambda x: x["sample_id"])

    # Keep all direct scarce rows; they are already tiny.
    selected_direct = direct_night + direct_other
    write_jsonl(Path(args.out_direct_labeled).resolve(), selected_direct)

    direct_night_n = len(direct_night)
    direct_other_n = len(direct_other)

    # Step B: to-annotate supplement from active raw
    need_night = max(0, int(args.target_night) - direct_night_n)
    need_other = max(0, int(args.target_other) - direct_other_n)

    active_rows = load_jsonl(active_raw)
    candidates: List[Dict[str, Any]] = []

    # Also exclude those that already appear in direct rows (tail-match friendly).
    direct_sid_set = {r["sample_id"] for r in selected_direct}

    for r in active_rows:
        sid = str(r.get("sample_id", "")).strip()
        if not sid or sid in exclude_ids:
            continue
        # skip rows that already have direct labeled counterpart
        tail_match = re.match(r"^active\d+_\d+_(.+)$", sid)
        if tail_match:
            tail = tail_match.group(1)
            if ("train_" + tail) in direct_sid_set:
                continue
        vp = resolve_video_direct(str(r.get("video", "")), videos_root)
        if vp is None:
            continue
        candidates.append(
            {
                "sample_id": sid,
                "split": str(r.get("split", "train")),
                "video": str(r.get("video", "")).replace("\\", "/"),
                "source_pool": str(r.get("source_pool", "")),
                "video_abs": str(vp),
            }
        )

    # Night proxy scoring by brightness/contrast.
    scored: List[Dict[str, Any]] = []
    for row in candidates:
        mean_luma, std_luma = quick_video_stats(Path(row["video_abs"]), sample_frames=10)
        night_score = max(0.0, 85.0 - mean_luma) + 0.35 * max(0.0, 35.0 - std_luma)
        scored.append({**row, "mean_luma": round(mean_luma, 3), "std_luma": round(std_luma, 3), "night_score": round(night_score, 3)})

    # Night candidates
    scored_night = sorted(scored, key=lambda x: (-float(x["night_score"]), float(x["mean_luma"]), x["sample_id"]))
    selected_night = scored_night[:need_night]
    used_ids = {r["sample_id"] for r in selected_night}

    # Other explainable proxy: prefer non-train source pools and mid/high complexity.
    # This is intentionally a candidate queue (human annotation required).
    rest = [r for r in scored if r["sample_id"] not in used_ids]
    for r in rest:
        src = str(r.get("source_pool", ""))
        src_bonus = 1.0 if ("extra" in src or "video" in src or "val" in src) else 0.0
        complexity = float(r["std_luma"])
        # Encourage non-night ambiguous scenes for explainable other auditing.
        r["other_proxy_score"] = round(src_bonus * 10.0 + abs(complexity - 38.0), 3)
    rest_sorted = sorted(rest, key=lambda x: (-float(x["other_proxy_score"]), x["sample_id"]))
    selected_other = rest_sorted[:need_other]

    annotate_rows: List[Dict[str, Any]] = []
    for r in selected_night:
        annotate_rows.append(
            {
                "sample_id": r["sample_id"],
                "split": r["split"],
                "video": r["video"],
                "accident_type": "",
                "onset_time": None,
                "impact_time": None,
                "post_time": None,
                "scene_tags": ["night", "straight_road"],
                "notes": f"targeted_queue_candidate=night+straight_road mean_luma={r['mean_luma']} std_luma={r['std_luma']} score={r['night_score']}",
            }
        )
    for r in selected_other:
        annotate_rows.append(
            {
                "sample_id": r["sample_id"],
                "split": r["split"],
                "video": r["video"],
                "accident_type": "",
                "onset_time": None,
                "impact_time": None,
                "post_time": None,
                "scene_tags": ["day", "intersection", "turning_scene"],
                "notes": f"targeted_queue_candidate=other_explainable source_pool={r.get('source_pool','')} mean_luma={r['mean_luma']} std_luma={r['std_luma']} proxy={r.get('other_proxy_score',0.0)}",
            }
        )

    # Shuffle for annotation neutrality, but deterministic.
    annotate_rows_sorted = sorted(annotate_rows, key=lambda x: x["sample_id"])
    rng.shuffle(annotate_rows_sorted)
    write_jsonl(Path(args.out_to_annotate_raw).resolve(), annotate_rows_sorted)

    report = {
        "mode": "targeted_independent_supplement_queue",
        "seed": int(args.seed),
        "targets": {"night+straight_road": int(args.target_night), "other_explainable": int(args.target_other)},
        "exclude_ids_n": int(len(exclude_ids)),
        "direct_labeled_available": {
            "night+straight_road": int(direct_night_n),
            "other_explainable": int(direct_other_n),
            "total": int(len(selected_direct)),
            "path": str(Path(args.out_direct_labeled).resolve()),
        },
        "need_after_direct": {"night+straight_road": int(need_night), "other_explainable": int(need_other)},
        "annotation_queue_generated": {
            "night+straight_road": int(len(selected_night)),
            "other_explainable": int(len(selected_other)),
            "total": int(len(annotate_rows_sorted)),
            "path": str(Path(args.out_to_annotate_raw).resolve()),
        },
        "active_pool_n": int(len(active_rows)),
        "active_candidates_after_exclude_n": int(len(candidates)),
        "night_proxy_top5": [
            {k: v for k, v in r.items() if k in {"sample_id", "video", "source_pool", "mean_luma", "std_luma", "night_score"}}
            for r in scored_night[:5]
        ],
    }
    out_report = Path(args.out_report).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
