import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


THREE_CLASSES = {"rear_end", "lane_change", "turn_conflict"}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def is_time_valid(row: Dict[str, Any]) -> bool:
    a, b, c = row.get("onset_time"), row.get("impact_time"), row.get("post_time")
    if a is None or b is None or c is None:
        return False
    try:
        a, b, c = float(a), float(b), float(c)
    except (TypeError, ValueError):
        return False
    return a <= b <= c


def split_report(rows: List[Dict[str, Any]], split_name: str) -> Dict[str, Any]:
    total = len(rows)
    type_counter = Counter(str(r.get("accident_type", "")).strip() for r in rows)
    three_rows = [r for r in rows if str(r.get("accident_type", "")).strip() in THREE_CLASSES]
    time_valid = sum(1 for r in three_rows if is_time_valid(r))
    scene_nonempty = sum(1 for r in three_rows if isinstance(r.get("scene_tags"), list) and len(r.get("scene_tags")) > 0)

    return {
        "split": split_name,
        "total_rows": total,
        "three_class_rows": len(three_rows),
        "three_class_ratio": round(len(three_rows) / total, 6) if total else 0.0,
        "three_class_time_valid_rows": time_valid,
        "three_class_scene_tagged_rows": scene_nonempty,
        "type_distribution": dict(type_counter),
        "three_class_distribution": {
            k: int(sum(1 for r in three_rows if str(r.get("accident_type", "")).strip() == k))
            for k in sorted(THREE_CLASSES)
        },
    }


def build_queue(rows: List[Dict[str, Any]], split_name: str, max_rows: int) -> List[Dict[str, Any]]:
    # Prioritize unlabeled / generic rows for annotation.
    queue: List[Dict[str, Any]] = []
    for r in rows:
        t = str(r.get("accident_type", "")).strip()
        if t in THREE_CLASSES:
            continue
        queue.append(
            {
                "split": split_name,
                "sample_id": str(r.get("sample_id", "")),
                "video": str(r.get("video", "")),
                "accident_type": t,
                "onset_time": r.get("onset_time"),
                "impact_time": r.get("impact_time"),
                "post_time": r.get("post_time"),
                "scene_tags": r.get("scene_tags", []),
                "review_status": "todo",
            }
        )
        if len(queue) >= max_rows:
            break
    return queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Report three-class annotation progress and export annotation queue.")
    parser.add_argument("--labels-train", default="data/processed/labels_train.norm4.jsonl")
    parser.add_argument("--labels-val", default="data/processed/labels_val.norm4.jsonl")
    parser.add_argument("--labels-test", default="data/processed/labels_test.norm4.jsonl")
    parser.add_argument("--out-report", default="outputs/eval/annotation_progress.json")
    parser.add_argument("--out-queue", default="data/processed/annotation_queue_train_val.jsonl")
    parser.add_argument("--queue-max", type=int, default=200)
    args = parser.parse_args()

    train_rows = load_jsonl(Path(args.labels_train).resolve())
    val_rows = load_jsonl(Path(args.labels_val).resolve())
    test_rows = load_jsonl(Path(args.labels_test).resolve())

    report = {
        "train": split_report(train_rows, "train"),
        "val": split_report(val_rows, "val"),
        "test": split_report(test_rows, "test"),
    }

    queue_rows = build_queue(val_rows, "val", args.queue_max // 2) + build_queue(train_rows, "train", args.queue_max)
    queue_rows = queue_rows[: args.queue_max]

    out_report = Path(args.out_report).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    out_queue = Path(args.out_queue).resolve()
    out_queue.parent.mkdir(parents=True, exist_ok=True)
    with out_queue.open("w", encoding="utf-8") as f:
        for r in queue_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[DONE] report={out_report}")
    print(f"[DONE] queue={out_queue} rows={len(queue_rows)}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

