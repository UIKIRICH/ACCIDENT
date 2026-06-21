import argparse
import json
import subprocess
import sys
from pathlib import Path


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Finalize filled annotation xlsx into jsonl + normalized outputs."
    )
    parser.add_argument(
        "--input-xlsx",
        default="data/processed/labels_extra_video_annotation.xlsx",
        help="Filled annotation xlsx",
    )
    parser.add_argument(
        "--out-labeled",
        default="data/processed/labels_extra_video_labeled.jsonl",
        help="Output labeled jsonl converted from xlsx",
    )
    parser.add_argument(
        "--out-norm4",
        default="data/processed/labels_extra_video_labeled.norm4.jsonl",
        help="Output normalized 4-class jsonl",
    )
    parser.add_argument(
        "--out-3cls",
        default="data/processed/labels_extra_video_labeled.3cls.jsonl",
        help="Output 3-class subset jsonl",
    )
    parser.add_argument(
        "--out-report",
        default="data/processed/labels_extra_video_labeled.report.json",
        help="Output normalization report",
    )
    parser.add_argument(
        "--sheet",
        default="annotation",
        help="Sheet name",
    )
    parser.add_argument(
        "--fill-empty-as-generic",
        action="store_true",
        help="Map empty accident_type to generic when normalizing",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    input_xlsx = (project_root / args.input_xlsx).resolve()
    out_labeled = (project_root / args.out_labeled).resolve()
    out_norm4 = (project_root / args.out_norm4).resolve()
    out_3cls = (project_root / args.out_3cls).resolve()
    out_report = (project_root / args.out_report).resolve()
    out_labeled.parent.mkdir(parents=True, exist_ok=True)

    xlsx_to_jsonl = (Path(__file__).resolve().parent / "annotation_xlsx_to_jsonl.py").resolve()
    normalize = (Path(__file__).resolve().parent / "normalize_labels.py").resolve()

    cmd_1 = [
        sys.executable,
        str(xlsx_to_jsonl),
        "--input",
        str(input_xlsx),
        "--output",
        str(out_labeled),
        "--sheet",
        str(args.sheet),
    ]
    subprocess.run(cmd_1, check=True)

    cmd_2 = [
        sys.executable,
        str(normalize),
        "--input",
        str(out_labeled),
        "--output",
        str(out_norm4),
        "--out-3cls",
        str(out_3cls),
        "--report",
        str(out_report),
    ]
    if args.fill_empty_as_generic:
        cmd_2.append("--fill-empty-as-generic")
    subprocess.run(cmd_2, check=True)

    rows_labeled = load_jsonl(out_labeled)
    rows_3cls = load_jsonl(out_3cls)
    print(
        json.dumps(
            {
                "input_xlsx": str(input_xlsx),
                "rows_labeled": len(rows_labeled),
                "rows_3cls": len(rows_3cls),
                "out_labeled": str(out_labeled),
                "out_norm4": str(out_norm4),
                "out_3cls": str(out_3cls),
                "out_report": str(out_report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
