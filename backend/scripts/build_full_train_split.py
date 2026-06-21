import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


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


def dump_jsonl(rows: List[Dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build full-train split by unioning all fold train/val rows."
    )
    parser.add_argument(
        "--splits-dir",
        default="outputs/fusion_v3/splits/v3_4_379",
        help="Directory containing fold{i}_train/val.jsonl",
    )
    parser.add_argument(
        "--out-jsonl",
        default="outputs/fusion_v3/splits/v3_4_379/full_train.jsonl",
        help="Output full-train jsonl path",
    )
    args = parser.parse_args()

    splits_dir = Path(args.splits_dir).resolve()
    out_jsonl = Path(args.out_jsonl).resolve()
    if not splits_dir.exists():
        raise FileNotFoundError(f"splits dir not found: {splits_dir}")

    split_files = sorted(splits_dir.glob("fold*_train.jsonl")) + sorted(
        splits_dir.glob("fold*_val.jsonl")
    )
    if not split_files:
        raise RuntimeError(f"no fold split files under {splits_dir}")

    dedup: Dict[str, Dict[str, Any]] = {}
    seen_order: List[str] = []
    for path in split_files:
        rows = load_jsonl(path)
        for row in rows:
            sample_id = str(row.get("sample_id", "")).strip()
            if not sample_id:
                continue
            if sample_id not in dedup:
                dedup[sample_id] = row
                seen_order.append(sample_id)

    merged = [dedup[sid] for sid in seen_order]
    dump_jsonl(merged, out_jsonl)

    type_counter = Counter(str(r.get("accident_type", "")).strip() for r in merged)
    print(
        json.dumps(
            {
                "splits_dir": str(splits_dir),
                "out_jsonl": str(out_jsonl),
                "source_files": [str(p) for p in split_files],
                "n_unique_samples": len(merged),
                "class_counts": dict(type_counter),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

