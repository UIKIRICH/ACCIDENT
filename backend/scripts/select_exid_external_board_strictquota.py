import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set


ALLOWED_TYPES = {"rear_end", "lane_change", "turn_conflict"}


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


def scene_bucket(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    is_day = "day" in s
    is_night = "night" in s
    is_straight = "straight_road" in s
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


def pick_n(rng: random.Random, rows: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    rows2 = list(rows)
    rows2.sort(key=lambda x: str(x.get("sample_id", "")))
    rng.shuffle(rows2)
    return rows2[: max(0, int(n))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Select one strict-quota independent exiD external board from local labeled pools.")
    parser.add_argument("--videos-root", required=True)
    parser.add_argument("--source-dir", default="data/processed")
    parser.add_argument("--target-n", type=int, default=110)
    parser.add_argument("--seed", type=int, default=20260509)
    parser.add_argument("--q-day-straight", type=int, default=25)
    parser.add_argument("--q-day-intersection", type=int, default=25)
    parser.add_argument("--q-night-straight", type=int, default=20)
    parser.add_argument("--q-other", type=int, default=15)
    parser.add_argument("--exclude-jsonl", action="append", default=[])
    parser.add_argument("--out-labels", required=True)
    parser.add_argument("--out-summary", required=True)
    parser.add_argument("--out-pool-audit", default="")
    args = parser.parse_args()

    videos_root = Path(args.videos_root).resolve()
    source_dir = Path(args.source_dir).resolve()
    out_labels = Path(args.out_labels).resolve()
    out_summary = Path(args.out_summary).resolve()
    out_pool_audit = Path(args.out_pool_audit).resolve() if args.out_pool_audit else None

    exclude_ids = load_exclude_ids(args.exclude_jsonl or [])
    rng = random.Random(int(args.seed))

    # Keep same broad scope as previous external-board rounds: 3cls-like pools + 378 supplement.
    source_files = sorted(source_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    candidate_files = [p for p in source_files if (".3cls" in p.name.lower()) or ("supp_378" in p.name.lower())]

    pool: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    counters = Counter()

    for fp in candidate_files:
        try:
            rows = load_jsonl(fp)
        except Exception:
            continue
        for r in rows:
            sid = str(r.get("sample_id", "")).strip()
            if not sid:
                counters["drop_empty_sid"] += 1
                continue
            if sid in seen:
                counters["drop_duplicate_sid"] += 1
                continue
            if sid in exclude_ids:
                counters["drop_excluded_sid"] += 1
                continue
            typ = str(r.get("accident_type", "")).strip()
            if typ not in ALLOWED_TYPES:
                counters["drop_non3cls"] += 1
                continue
            tags = parse_scene_tags(r.get("scene_tags", []))
            if not tags:
                counters["drop_empty_scene_tags"] += 1
                continue
            video = str(r.get("video", "")).strip().replace("\\", "/")
            if not video:
                counters["drop_empty_video"] += 1
                continue
            video_path = (videos_root / video).resolve()
            if not video_path.exists():
                counters["drop_missing_video"] += 1
                continue
            bucket = scene_bucket(tags)
            rec = dict(r)
            rec["sample_id"] = sid
            rec["video"] = video
            rec["accident_type"] = typ
            rec["scene_tags"] = tags
            rec["_bucket"] = bucket
            rec["_source_file"] = fp.name
            pool.append(rec)
            seen.add(sid)
            counters["keep"] += 1

    avail = Counter(r["_bucket"] for r in pool)
    requested = {
        "day+straight_road": int(args.q_day_straight),
        "day+intersection": int(args.q_day_intersection),
        "night+straight_road": int(args.q_night_straight),
        "other": int(args.q_other),
    }
    effective = {k: min(v, int(avail.get(k, 0))) for k, v in requested.items()}
    unmet = {k: {"requested": int(requested[k]), "available": int(avail.get(k, 0))} for k in requested if avail.get(k, 0) < requested[k]}

    by_bucket: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in pool:
        by_bucket[r["_bucket"]].append(r)

    selected: List[Dict[str, Any]] = []
    selected_ids: Set[str] = set()

    # Phase 1: quota guarantees (max feasible if strict requested cannot be met).
    for b in ["day+straight_road", "day+intersection", "night+straight_road", "other"]:
        take = int(effective.get(b, 0))
        chunk = pick_n(rng, by_bucket.get(b, []), take)
        for r in chunk:
            sid = r["sample_id"]
            if sid in selected_ids:
                continue
            selected.append(r)
            selected_ids.add(sid)

    # Phase 2: fill to target using stable bucket cycle.
    target_n = int(args.target_n)
    fill_order = ["day+straight_road", "day+intersection", "night+intersection", "other", "night+straight_road"]
    leftovers: Dict[str, List[Dict[str, Any]]] = {}
    for b in fill_order:
        cands = [r for r in by_bucket.get(b, []) if r["sample_id"] not in selected_ids]
        cands.sort(key=lambda x: str(x.get("sample_id", "")))
        rng.shuffle(cands)
        leftovers[b] = cands

    while len(selected) < target_n:
        moved = False
        for b in fill_order:
            if len(selected) >= target_n:
                break
            arr = leftovers.get(b, [])
            while arr:
                r = arr.pop()
                sid = r["sample_id"]
                if sid in selected_ids:
                    continue
                selected.append(r)
                selected_ids.add(sid)
                moved = True
                break
        if not moved:
            break

    # Prepare label output (remove internal helper fields)
    out_rows: List[Dict[str, Any]] = []
    for r in selected:
        rr = dict(r)
        rr.pop("_bucket", None)
        rr.pop("_source_file", None)
        out_rows.append(rr)

    out_labels.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_labels, out_rows)

    bucket_dist = Counter(scene_bucket(parse_scene_tags(r.get("scene_tags", []))) for r in out_rows)
    class_dist = Counter(str(r.get("accident_type", "")).strip() for r in out_rows)
    split_dist = Counter(str(r.get("split", "")).strip() for r in out_rows)
    source_file_dist = Counter(str(r.get("_source_file", "")).strip() for r in selected)

    summary: Dict[str, Any] = {
        "selected_n": int(len(out_rows)),
        "target_n": int(target_n),
        "seed": int(args.seed),
        "videos_root": str(videos_root),
        "source_dir": str(source_dir),
        "candidate_files_n": int(len(candidate_files)),
        "exclude_ids_n": int(len(exclude_ids)),
        "pool_n_after_filters": int(len(pool)),
        "pool_bucket_dist": {k: int(v) for k, v in avail.items()},
        "requested_quotas": requested,
        "effective_quotas": effective,
        "unmet_requested_quotas": unmet,
        "bucket_dist": {k: int(v) for k, v in bucket_dist.items()},
        "class_dist": {k: int(v) for k, v in class_dist.items()},
        "split_dist": {k: int(v) for k, v in split_dist.items()},
        "source_file_dist": {k: int(v) for k, v in source_file_dist.items()},
        "filter_counters": {k: int(v) for k, v in counters.items()},
        "board_path": str(out_labels),
        "independent_vs_exclude_set": True,
    }
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    if out_pool_audit is not None:
        out_pool_audit.parent.mkdir(parents=True, exist_ok=True)
        audit_rows: List[Dict[str, Any]] = []
        for r in pool:
            audit_rows.append(
                {
                    "sample_id": r["sample_id"],
                    "video": r["video"],
                    "accident_type": r["accident_type"],
                    "scene_tags": r.get("scene_tags", []),
                    "scene_bucket": r["_bucket"],
                    "source_file": r["_source_file"],
                }
            )
        write_jsonl(out_pool_audit, audit_rows)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
