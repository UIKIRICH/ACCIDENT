import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set


TARGET_CLASSES = ["rear_end", "lane_change", "turn_conflict"]


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


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_feature_sample_ids(feature_csv: Path, sample_id_col: str) -> Set[str]:
    sids: Set[str] = set()
    with feature_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or sample_id_col not in reader.fieldnames:
            raise ValueError(f"{feature_csv} missing required column: {sample_id_col}")
        for row in reader:
            sid = str(row.get(sample_id_col, "")).strip()
            if sid:
                sids.add(sid)
    return sids


def class_dist(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    c = Counter(str(r.get("accident_type", "")).strip() for r in rows)
    return {k: int(c.get(k, 0)) for k in TARGET_CLASSES}


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter labels by feature coverage using sample_id.")
    parser.add_argument("--labels", required=True, help="Input labels jsonl")
    parser.add_argument("--feature-csv", required=True, help="Feature csv with sample_id column")
    parser.add_argument("--out-labels", required=True, help="Output filtered labels jsonl")
    parser.add_argument("--out-missing", required=True, help="Output missing labels jsonl")
    parser.add_argument("--out-report", required=True, help="Output report json")
    parser.add_argument("--sample-id-col", default="sample_id", help="Feature csv sample_id column")
    args = parser.parse_args()

    labels_path = Path(args.labels).resolve()
    feature_csv = Path(args.feature_csv).resolve()
    out_labels = Path(args.out_labels).resolve()
    out_missing = Path(args.out_missing).resolve()
    out_report = Path(args.out_report).resolve()

    rows = load_jsonl(labels_path)
    feature_sids = load_feature_sample_ids(feature_csv, sample_id_col=str(args.sample_id_col))

    kept: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    for r in rows:
        sid = str(r.get("sample_id", "")).strip()
        if sid and sid in feature_sids:
            kept.append(r)
        else:
            missing.append(r)

    dump_jsonl(out_labels, kept)
    dump_jsonl(out_missing, missing)

    report = {
        "labels": str(labels_path),
        "feature_csv": str(feature_csv),
        "sample_id_col": str(args.sample_id_col),
        "rows_input": len(rows),
        "rows_kept": len(kept),
        "rows_missing": len(missing),
        "class_dist_input": class_dist(rows),
        "class_dist_kept": class_dist(kept),
        "class_dist_missing": class_dist(missing),
        "out_labels": str(out_labels),
        "out_missing": str(out_missing),
    }
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

