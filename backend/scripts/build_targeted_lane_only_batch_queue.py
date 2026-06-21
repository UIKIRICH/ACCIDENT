import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

from backend.video_keyframe import extract_sequence_features


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


def resolve_video(video_ref: str, videos_root: Path) -> Optional[Path]:
    ref = str(video_ref).replace("\\", "/").strip()
    if not ref:
        return None
    p = (videos_root / ref).resolve()
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


def quick_luma_stats(video_path: Path, sample_frames: int = 10) -> Tuple[float, float]:
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


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def impact_lane_strength(seq: Dict[str, Any]) -> float:
    pm = (((seq.get("evidence") or {}).get("pair_metrics") or {}).get("impact") or {})
    lateral_shift = safe_float(pm.get("lateral_shift_score", 0.0), 0.0)
    cutin = safe_float(pm.get("cutin_continuity", 0.0), 0.0)
    side_overlap = safe_float(pm.get("side_overlap_growth", 0.0), 0.0)
    return 0.45 * lateral_shift + 0.35 * cutin + 0.20 * side_overlap


def main() -> None:
    parser = argparse.ArgumentParser(description="Build lane-only targeted supplement queue (night+straight + other_explainable).")
    parser.add_argument("--videos-root", required=True)
    parser.add_argument("--active-raw", default="data/processed/labels_active_pool_unseen180_20260504.raw.jsonl")
    parser.add_argument("--night-target", type=int, default=6)
    parser.add_argument("--other-target", type=int, default=4)
    parser.add_argument("--night-shortlist", type=int, default=50)
    parser.add_argument("--other-shortlist", type=int, default=40)
    parser.add_argument("--lane-prob-min", type=float, default=0.28)
    parser.add_argument("--night-luma-max", type=float, default=78.0)
    parser.add_argument("--night-intersection-max", type=float, default=0.45)
    parser.add_argument("--other-turning-min", type=float, default=0.40)
    parser.add_argument("--other-intersection-min", type=float, default=0.55)
    parser.add_argument("--exclude-jsonl", action="append", default=[])
    parser.add_argument("--out-raw-jsonl", required=True)
    parser.add_argument("--out-report", required=True)
    args = parser.parse_args()

    videos_root = Path(args.videos_root).resolve()
    active_raw = Path(args.active_raw).resolve()
    exclude_ids = load_exclude_ids(args.exclude_jsonl or [])

    active = load_jsonl(active_raw)
    candidates: List[Dict[str, Any]] = []
    for r in active:
        sid = str(r.get("sample_id", "")).strip()
        if not sid or sid in exclude_ids:
            continue
        video = str(r.get("video", "")).replace("\\", "/").strip()
        vp = resolve_video(video, videos_root)
        if vp is None:
            continue
        mean_luma, std_luma = quick_luma_stats(vp, sample_frames=8)
        src = str(r.get("source_pool", ""))
        other_pref = 8.0 if ("extra val" in src or "extra video" in src) else 0.0
        other_pref += 4.0 if "extra train" in src else 0.0
        candidates.append(
            {
                "sample_id": sid,
                "split": str(r.get("split", "train")),
                "video": video,
                "video_abs": str(vp),
                "source_pool": src,
                "mean_luma": mean_luma,
                "std_luma": std_luma,
                "night_rank_score": -mean_luma,
                "other_rank_score": other_pref + 0.6 * std_luma - 0.2 * mean_luma,
            }
        )

    # Build shortlists by fast proxy first.
    cand_night = sorted(candidates, key=lambda x: (x["mean_luma"], -x["std_luma"], x["sample_id"]))[: max(1, int(args.night_shortlist))]
    cand_other = sorted(candidates, key=lambda x: (-x["other_rank_score"], x["sample_id"]))[: max(1, int(args.other_shortlist))]

    # Merge shortlist preserving order and uniqueness.
    merged: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for r in cand_night + cand_other:
        sid = r["sample_id"]
        if sid in seen:
            continue
        seen.add(sid)
        merged.append(r)

    print(f"[INFO] pool_after_exclude={len(candidates)} shortlist_eval={len(merged)}")

    night_hits: List[Dict[str, Any]] = []
    other_hits: List[Dict[str, Any]] = []
    eval_fail = 0

    for i, r in enumerate(merged, start=1):
        print(f"[INFO] eval ({i}/{len(merged)}) {r['video']}")
        try:
            seq = extract_sequence_features(Path(r["video_abs"]), include_frames=False, verbose=False)
        except Exception:
            eval_fail += 1
            continue

        probs = (seq.get("type_probs") or {})
        pred = str(seq.get("accident_type_key", "")).strip()
        lane_prob = safe_float(probs.get("lane_change", 0.0), 0.0)
        if lane_prob < float(args.lane_prob_min):
            continue

        sp = (seq.get("scene_prior") or {})
        inter = safe_float(sp.get("intersection_prior", 0.0), 0.0)
        turn = safe_float(sp.get("turning_scene_prior", 0.0), 0.0)
        lane_strength = impact_lane_strength(seq)
        rec = dict(r)
        rec.update(
            {
                "pred_type": pred,
                "prob_lane": lane_prob,
                "intersection_prior": inter,
                "turning_scene_prior": turn,
                "lane_strength": lane_strength,
            }
        )

        is_night_bucket_proxy = (
            rec["mean_luma"] <= float(args.night_luma_max)
            and inter <= float(args.night_intersection_max)
        )
        if is_night_bucket_proxy:
            night_hits.append(rec)
            continue

        is_other_proxy = (
            (turn >= float(args.other_turning_min) or inter >= float(args.other_intersection_min) or rec["std_luma"] >= 40.0)
            and rec["mean_luma"] > (float(args.night_luma_max) - 6.0)
        )
        if is_other_proxy:
            other_hits.append(rec)

    # Score and select final mini-batch.
    night_hits = sorted(
        night_hits,
        key=lambda x: (x["prob_lane"] + 0.6 * x["lane_strength"] + max(0.0, (78.0 - x["mean_luma"]) / 100.0)),
        reverse=True,
    )
    other_hits = sorted(
        other_hits,
        key=lambda x: (x["prob_lane"] + 0.6 * x["lane_strength"] + max(0.0, (x["std_luma"] - 35.0) / 100.0)),
        reverse=True,
    )

    night_take = night_hits[: max(0, int(args.night_target))]
    other_take = other_hits[: max(0, int(args.other_target))]

    out_rows: List[Dict[str, Any]] = []
    for r in night_take:
        out_rows.append(
            {
                "sample_id": r["sample_id"],
                "split": r["split"],
                "video": r["video"],
                "accident_type": "",
                "onset_time": None,
                "impact_time": None,
                "post_time": None,
                "scene_tags": ["night", "straight_road"],
                "notes": (
                    "lane_only_target=night+straight_road "
                    f"prob_lane={r['prob_lane']:.4f} lane_strength={r['lane_strength']:.4f} "
                    f"mean_luma={r['mean_luma']:.2f} std_luma={r['std_luma']:.2f} "
                    f"pred={r['pred_type']} inter={r['intersection_prior']:.4f} turn={r['turning_scene_prior']:.4f}"
                ),
            }
        )
    for r in other_take:
        out_rows.append(
            {
                "sample_id": r["sample_id"],
                "split": r["split"],
                "video": r["video"],
                "accident_type": "",
                "onset_time": None,
                "impact_time": None,
                "post_time": None,
                "scene_tags": ["rain", "urban"],
                "notes": (
                    "lane_only_target=other_explainable "
                    f"prob_lane={r['prob_lane']:.4f} lane_strength={r['lane_strength']:.4f} "
                    f"mean_luma={r['mean_luma']:.2f} std_luma={r['std_luma']:.2f} "
                    f"pred={r['pred_type']} inter={r['intersection_prior']:.4f} turn={r['turning_scene_prior']:.4f}"
                ),
            }
        )

    # Deduplicate final rows by sample_id.
    dedup: Dict[str, Dict[str, Any]] = {}
    for r in out_rows:
        sid = str(r["sample_id"]).strip()
        if sid and sid not in dedup:
            dedup[sid] = r
    out_rows = list(dedup.values())

    out_raw = Path(args.out_raw_jsonl).resolve()
    out_report = Path(args.out_report).resolve()
    write_jsonl(out_raw, out_rows)

    report = {
        "mode": "targeted_lane_only_batch_queue",
        "targets": {"night": int(args.night_target), "other": int(args.other_target)},
        "exclude_ids_n": int(len(exclude_ids)),
        "candidate_pool_n": int(len(candidates)),
        "shortlist_eval_n": int(len(merged)),
        "eval_fail_n": int(eval_fail),
        "hits": {"night_proxy_hits_n": int(len(night_hits)), "other_proxy_hits_n": int(len(other_hits))},
        "selected": {
            "night_n": int(len(night_take)),
            "other_n": int(len(other_take)),
            "total_n": int(len(out_rows)),
        },
        "paths": {"out_raw_jsonl": str(out_raw)},
        "night_top5": [
            {k: v for k, v in x.items() if k in {"sample_id", "video", "source_pool", "prob_lane", "lane_strength", "mean_luma", "std_luma", "pred_type"}}
            for x in night_hits[:5]
        ],
        "other_top5": [
            {k: v for k, v in x.items() if k in {"sample_id", "video", "source_pool", "prob_lane", "lane_strength", "mean_luma", "std_luma", "pred_type"}}
            for x in other_hits[:5]
        ],
    }
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
