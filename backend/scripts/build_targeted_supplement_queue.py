import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TARGET_CLASSES = {"rear_end", "lane_change"}


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


def idx(rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
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
    parser = argparse.ArgumentParser(description="Build targeted supplement queue for lane/rear hard samples.")
    parser.add_argument("--pred", required=True)
    parser.add_argument("--gt", required=True)
    parser.add_argument("--out-csv", required=True)
    parser.add_argument("--top-k", type=int, default=80)
    args = parser.parse_args()

    pred_rows = load_jsonl(Path(args.pred).resolve())
    gt_rows = load_jsonl(Path(args.gt).resolve())
    pred_sid, pred_video = idx(pred_rows)

    queue: List[Dict[str, Any]] = []
    for gt in gt_rows:
        gt_type = str(gt.get("accident_type", "")).strip()
        if gt_type not in TARGET_CLASSES:
            continue
        sid = str(gt.get("sample_id", "")).strip()
        video = normalize_video(gt.get("video", ""))
        pred: Optional[Dict[str, Any]] = pred_sid.get(sid) if sid else None
        if pred is None and video:
            pred = pred_video.get(video)
        if pred is None:
            continue

        pred_type = str(pred.get("pred_type", "")).strip()
        probs = pred.get("type_probs", {}) if isinstance(pred.get("type_probs", {}), dict) else {}
        p_rear = float(probs.get("rear_end", 0.0))
        p_lane = float(probs.get("lane_change", 0.0))
        p_turn = float(probs.get("turn_conflict", 0.0))
        p_true = p_rear if gt_type == "rear_end" else p_lane
        wrong = int(pred_type != gt_type)
        # Priority: wrong first, then low confidence on true class.
        priority = (10.0 if wrong else 0.0) + (1.0 - p_true)
        queue.append(
            {
                "sample_id": sid,
                "video": video,
                "gt_type": gt_type,
                "pred_type": pred_type,
                "p_rear": round(p_rear, 6),
                "p_lane": round(p_lane, 6),
                "p_turn": round(p_turn, 6),
                "priority": round(priority, 6),
                "scene_tags": json.dumps(gt.get("scene_tags", []), ensure_ascii=False),
            }
        )

    queue.sort(key=lambda x: x["priority"], reverse=True)
    queue = queue[: max(1, int(args.top_k))]

    out_path = Path(args.out_csv).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "video",
                "gt_type",
                "pred_type",
                "p_rear",
                "p_lane",
                "p_turn",
                "priority",
                "scene_tags",
            ],
        )
        writer.writeheader()
        writer.writerows(queue)

    print(json.dumps({"out_csv": str(out_path), "rows": len(queue)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

