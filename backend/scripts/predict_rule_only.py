import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.video_keyframe import extract_sequence_features  # noqa: E402


ALLOWED_TYPES = {"rear_end", "lane_change", "turn_conflict", "generic"}


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


def ensure_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if v is None:
        return []
    return [str(v)]


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def normalize_type_probs(type_probs: Dict[str, Any]) -> Dict[str, float]:
    probs = {k: max(0.0, safe_float(type_probs.get(k, 0.0), 0.0)) for k in ["rear_end", "lane_change", "turn_conflict"]}
    s = sum(probs.values())
    if s <= 1e-9:
        probs = {"rear_end": 0.25, "lane_change": 0.25, "turn_conflict": 0.25}
        s = 0.75
    probs = {k: v / s * 0.95 for k, v in probs.items()}
    probs["generic"] = max(0.0, 1.0 - sum(probs.values()))
    total = sum(probs.values())
    if total <= 1e-9:
        return {"rear_end": 0.25, "lane_change": 0.25, "turn_conflict": 0.25, "generic": 0.25}
    return {k: float(v / total) for k, v in probs.items()}


def choose_pred_type(seq: Dict[str, Any], probs: Dict[str, float]) -> str:
    t = str(seq.get("accident_type_key", "generic"))
    if t in ALLOWED_TYPES:
        return t
    return max(probs.items(), key=lambda x: x[1])[0]


def resolve_video_path(video_ref: str, videos_root: Path) -> Path:
    p = Path(video_ref)
    if p.is_absolute():
        return p
    return videos_root / p


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


def resolve_video_path_with_alias(video_ref: str, videos_root: Path, alias_map: Dict[str, str]) -> Path:
    base = resolve_video_path(video_ref, videos_root)
    if base.exists():
        return base

    ref = str(video_ref).replace("\\", "/").strip()
    if not ref:
        return base
    parts = [x for x in ref.split("/") if x]
    if not parts:
        return base

    head = parts[0]
    mapped_head = alias_map.get(head)
    if not mapped_head:
        return base

    mapped_rel = Path(mapped_head)
    for frag in parts[1:]:
        mapped_rel = mapped_rel / frag
    mapped = videos_root / mapped_rel
    if mapped.exists():
        return mapped
    return base


def build_pred_row(label: Dict[str, Any], seq: Dict[str, Any]) -> Dict[str, Any]:
    probs = normalize_type_probs(seq.get("type_probs", {}))
    pred_type = choose_pred_type(seq, probs)
    selected_items = seq.get("selected_items", [])
    samples = seq.get("samples", [])
    keyframe_times: List[float] = []
    for item in selected_items:
        idx = int(item.get("idx", -1))
        if 0 <= idx < len(samples):
            keyframe_times.append(round(safe_float(samples[idx].get("sec", 0.0), 0.0), 2))

    risk_info = seq.get("risk_info", {}) or {}
    scene_prior = seq.get("scene_prior", {}) or {}
    type_scores = seq.get("type_scores", {}) or {}
    return {
        "video": str(label.get("video", "")),
        "pred_type": pred_type,
        "type_probs": {k: round(float(probs.get(k, 0.0)), 6) for k in ["rear_end", "lane_change", "turn_conflict", "generic"]},
        "type_scores_raw": {
            "rear_end": round(safe_float(type_scores.get("rear_end", 0.0), 0.0), 6),
            "lane_change": round(safe_float(type_scores.get("lane_change", 0.0), 0.0), 6),
            "turn_conflict": round(safe_float(type_scores.get("turn_conflict", 0.0), 0.0), 6),
        },
        "pred_onset_time": round(safe_float(seq.get("onset_sec", 0.0), 0.0), 2),
        "pred_impact_time": round(safe_float(seq.get("impact_sec", 0.0), 0.0), 2),
        "pred_post_time": round(safe_float(seq.get("post_sec", 0.0), 0.0), 2),
        "lead_time_sec": round(safe_float(risk_info.get("lead_time_sec", 0.0), 0.0), 2),
        "risk_score": round(safe_float(risk_info.get("peak_risk", 0.0), 0.0), 6),
        "uncertainty": round(safe_float(seq.get("uncertainty", 1.0), 1.0), 6),
        "keyframe_times": keyframe_times,
        "scene_tags": ensure_scene_tags(label.get("scene_tags")),
        "scene_prior": {
            "intersection_prior": round(safe_float(scene_prior.get("intersection_prior", 0.0), 0.0), 6),
            "turning_scene_prior": round(safe_float(scene_prior.get("turning_scene_prior", 0.0), 0.0), 6),
            "turn_candidate_boost": round(safe_float(scene_prior.get("turn_candidate_boost", 0.0), 0.0), 6),
            "turn_candidate_run": round(safe_float(scene_prior.get("turn_candidate_run", 0.0), 0.0), 6),
            "turn_evidence": round(safe_float(scene_prior.get("turn_evidence", 0.0), 0.0), 6),
            "router_score": round(safe_float(scene_prior.get("router_score", 0.0), 0.0), 6),
            "stage2_score": round(safe_float(scene_prior.get("stage2_score", 0.0), 0.0), 6),
            "stage2_applied": bool(scene_prior.get("stage2_applied", False)),
            "route_mode": str(scene_prior.get("route_mode", "")),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen rule_v9.0 on labeled set and export pred jsonl.")
    parser.add_argument("--labels", required=True, help="Path to labels_*.jsonl")
    parser.add_argument("--videos-root", default="backend/videos", help="Root directory for video files")
    parser.add_argument("--out", required=True, help="Output prediction jsonl path")
    parser.add_argument("--limit", type=int, default=0, help="Optional sample limit for quick smoke run")
    parser.add_argument("--start", type=int, default=0, help="Start index (0-based, inclusive) after loading labels")
    parser.add_argument("--end", type=int, default=0, help="End index (0-based, exclusive); 0 means until end")
    parser.add_argument("--strict-missing", action="store_true", help="Fail when referenced video file does not exist")
    parser.add_argument(
        "--path-alias",
        action="append",
        default=[],
        help="Path alias for first folder token, e.g. lane=不定和变道 (can be repeated)",
    )
    args = parser.parse_args()

    labels_path = Path(args.labels).resolve()
    videos_root = Path(args.videos_root).resolve()
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    all_rows = load_jsonl(labels_path)
    alias_map = parse_path_aliases(args.path_alias or [])
    if alias_map:
        print(f"[INFO] path_alias={alias_map}")
    start = max(0, int(args.start))
    end = int(args.end) if args.end and args.end > 0 else len(all_rows)
    end = max(start, min(end, len(all_rows)))
    rows = all_rows[start:end]
    if args.limit and args.limit > 0:
        rows = rows[: args.limit]

    written = 0
    missing = 0
    sink_to_null = str(args.out).strip().upper() in {"NUL", "-"}
    wf = None
    if not sink_to_null:
        wf = out_path.open("w", encoding="utf-8")

    type_counter: Dict[str, int] = {}
    lead_sum = 0.0
    impact_sum = 0.0
    n_stats = 0
    try:
        for i, label in enumerate(rows, start=1):
            video_ref = str(label.get("video", "")).strip()
            if not video_ref:
                print(f"[WARN] skip line#{i}: empty video field")
                continue

            video_path = resolve_video_path_with_alias(video_ref, videos_root, alias_map)
            if not video_path.exists():
                missing += 1
                msg = f"[WARN] missing video file: {video_path}"
                if args.strict_missing:
                    raise FileNotFoundError(msg)
                print(msg)
                continue

            print(f"[INFO] ({i}/{len(rows)}) infer {video_ref}")
            seq = extract_sequence_features(video_path, include_frames=False, verbose=False)
            pred = build_pred_row(label, seq)
            if wf is not None:
                wf.write(json.dumps(pred, ensure_ascii=False) + "\n")
            written += 1
            t = str(pred.get("pred_type", "generic"))
            type_counter[t] = type_counter.get(t, 0) + 1
            lead_sum += safe_float(pred.get("lead_time_sec", 0.0), 0.0)
            impact_sum += safe_float(pred.get("pred_impact_time", 0.0), 0.0)
            n_stats += 1
    finally:
        if wf is not None:
            wf.close()

    avg_lead = (lead_sum / n_stats) if n_stats else 0.0
    avg_impact = (impact_sum / n_stats) if n_stats else 0.0
    print(f"[DONE] written={written}, missing_video={missing}, out={'NUL' if sink_to_null else out_path}")
    print(f"[SUMMARY] avg_impact={avg_impact:.2f}s avg_lead={avg_lead:.2f}s type_counter={type_counter}")


if __name__ == "__main__":
    main()
