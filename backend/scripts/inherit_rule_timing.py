import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


DEFAULT_TIME_FIELDS = [
    "pred_onset_time",
    "pred_impact_time",
    "pred_post_time",
    "lead_time_sec",
    "keyframe_times",
    "scene_tags",
]


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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inherit timing/keyframe fields from rule predictions while keeping fusion type outputs."
    )
    parser.add_argument("--fusion", required=True, help="Fusion prediction jsonl")
    parser.add_argument("--rule", required=True, help="Rule prediction jsonl")
    parser.add_argument("--out", required=True, help="Output merged prediction jsonl")
    parser.add_argument(
        "--time-fields",
        default=",".join(DEFAULT_TIME_FIELDS),
        help="Comma-separated fields to inherit from rule",
    )
    args = parser.parse_args()

    fusion_rows = load_jsonl(Path(args.fusion).resolve())
    rule_rows = load_jsonl(Path(args.rule).resolve())
    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fields = [x.strip() for x in str(args.time_fields).split(",") if x.strip()]
    rule_map = {str(r.get("video", "")).strip(): r for r in rule_rows}

    merged: List[Dict[str, Any]] = []
    inherited_rows = 0
    missing_rule_rows = 0
    missing_field_hits = 0

    for f in fusion_rows:
        v = str(f.get("video", "")).strip()
        r = rule_map.get(v)
        out = dict(f)
        if r is None:
            missing_rule_rows += 1
            merged.append(out)
            continue

        inherited_any = False
        for k in fields:
            if k in r:
                out[k] = r[k]
                inherited_any = True
            else:
                missing_field_hits += 1
        if inherited_any:
            inherited_rows += 1
        merged.append(out)

    with out_path.open("w", encoding="utf-8") as wf:
        for row in merged:
            wf.write(json.dumps(row, ensure_ascii=False) + "\n")

    report = {
        "fusion_input": str(Path(args.fusion).resolve()),
        "rule_input": str(Path(args.rule).resolve()),
        "output": str(out_path),
        "rows_fusion": len(fusion_rows),
        "rows_rule": len(rule_rows),
        "rows_output": len(merged),
        "inherited_rows": inherited_rows,
        "missing_rule_rows": missing_rule_rows,
        "missing_field_hits": missing_field_hits,
        "time_fields": fields,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
