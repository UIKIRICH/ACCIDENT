import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


VALID_CLASSES = {"rear_end", "lane_change", "turn_conflict"}


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


def normalize_video(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def build_index(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_sid: Dict[str, Dict[str, Any]] = {}
    by_video: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        sid = str(row.get("sample_id", "")).strip()
        if sid:
            by_sid[sid] = row
        video = normalize_video(row.get("video", ""))
        if video:
            by_video[video] = row
    return by_sid, by_video


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hard sample weights from OOF prediction errors.")
    parser.add_argument("--pred", required=True, help="Prediction jsonl (must contain pred_type, sample_id/video)")
    parser.add_argument("--gt", required=True, help="Ground-truth jsonl (must contain accident_type, sample_id/video)")
    parser.add_argument("--out", required=True, help="Output hard sample jsonl")
    parser.add_argument("--turn-miss-weight", type=float, default=3.0)
    parser.add_argument("--false-turn-weight", type=float, default=2.2)
    parser.add_argument("--other-miss-weight", type=float, default=1.5)
    args = parser.parse_args()

    pred_rows = load_jsonl(Path(args.pred).resolve())
    gt_rows = load_jsonl(Path(args.gt).resolve())
    pred_sid, pred_video = build_index(pred_rows)

    out_rows: List[Dict[str, Any]] = []
    seen = set()
    summary = {
        "matched": 0,
        "turn_miss": 0,
        "false_turn": 0,
        "other_miss": 0,
        "kept": 0,
    }

    for gt in gt_rows:
        gt_type = str(gt.get("accident_type", "")).strip()
        if gt_type not in VALID_CLASSES:
            continue
        sid = str(gt.get("sample_id", "")).strip()
        video = normalize_video(gt.get("video", ""))

        pred: Optional[Dict[str, Any]] = pred_sid.get(sid) if sid else None
        if pred is None and video:
            pred = pred_video.get(video)
        if pred is None:
            continue
        summary["matched"] += 1

        pred_type = str(pred.get("pred_type", "")).strip()
        if pred_type not in VALID_CLASSES or pred_type == gt_type:
            continue

        reason = "other_miss"
        weight = float(args.other_miss_weight)
        if gt_type == "turn_conflict" and pred_type != "turn_conflict":
            reason = "turn_miss"
            weight = float(args.turn_miss_weight)
            summary["turn_miss"] += 1
        elif gt_type in {"rear_end", "lane_change"} and pred_type == "turn_conflict":
            reason = "false_turn"
            weight = float(args.false_turn_weight)
            summary["false_turn"] += 1
        else:
            summary["other_miss"] += 1

        sample_id = sid if sid else video
        if not sample_id or sample_id in seen:
            continue
        seen.add(sample_id)
        out_rows.append(
            {
                "sample_id": sample_id,
                "video": video,
                "gt_type": gt_type,
                "pred_type": pred_type,
                "reason": reason,
                "sample_weight": round(max(1.0, float(weight)), 4),
            }
        )

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in out_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary["kept"] = len(out_rows)
    print(json.dumps({"out": str(out_path), "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

