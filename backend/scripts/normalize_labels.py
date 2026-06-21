import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


TYPE_MAP = {
    "rear_end": "rear_end",
    "lane_change": "lane_change",
    "lane_change_collision": "lane_change",
    "turn_conflict": "turn_conflict",
    "side_collision": "generic",
    "single_vehicle": "generic",
    "head_on": "generic",
    "other": "generic",
    "uncertain": "generic",
    "generic": "generic",
}

FOUR_CLASSES = ["rear_end", "lane_change", "turn_conflict", "generic"]
THREE_CLASSES = ["rear_end", "lane_change", "turn_conflict"]


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def normalize_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if v is None:
        return []
    return [str(v)]


def normalize_row(row: Dict[str, Any], fill_empty_as_generic: bool) -> Dict[str, Any]:
    out = dict(row)
    raw_type = str(out.get("accident_type", "")).strip()
    if raw_type == "" and fill_empty_as_generic:
        out["accident_type"] = "generic"
    else:
        out["accident_type"] = TYPE_MAP.get(raw_type, "generic" if fill_empty_as_generic else raw_type)
    out["scene_tags"] = normalize_scene_tags(out.get("scene_tags"))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize labels into 4-class taxonomy and export 3-class subset.")
    parser.add_argument("--input", required=True, help="Input labels jsonl")
    parser.add_argument("--output", required=True, help="Output normalized labels jsonl")
    parser.add_argument("--out-3cls", required=True, help="Output 3-class subset jsonl")
    parser.add_argument("--report", required=True, help="Output report json")
    parser.add_argument("--fill-empty-as-generic", action="store_true", help="Map empty accident_type to generic")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    out3_path = Path(args.out_3cls).resolve()
    report_path = Path(args.report).resolve()

    rows = load_jsonl(input_path)
    before = Counter(str(r.get("accident_type", "")) for r in rows)
    norm_rows = [normalize_row(r, args.fill_empty_as_generic) for r in rows]
    after = Counter(str(r.get("accident_type", "")) for r in norm_rows)

    rows_3cls = [r for r in norm_rows if r.get("accident_type") in THREE_CLASSES]
    unlabeled_count = sum(1 for r in rows if str(r.get("accident_type", "")).strip() == "")

    dump_jsonl(output_path, norm_rows)
    dump_jsonl(out3_path, rows_3cls)

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "output_3cls": str(out3_path),
        "total_rows": len(rows),
        "unlabeled_in_input": unlabeled_count,
        "before_type_distribution": dict(before),
        "after_type_distribution": dict(after),
        "four_classes": FOUR_CLASSES,
        "three_classes": THREE_CLASSES,
        "three_class_rows": len(rows_3cls),
        "fill_empty_as_generic": bool(args.fill_empty_as_generic),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] normalized: {output_path}")
    print(f"[DONE] 3-class subset: {out3_path}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

