import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set

import pandas as pd


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
    parser = argparse.ArgumentParser(description="Prepare v3.4 feature pool CSV by sample_id alignment.")
    parser.add_argument("--labels", required=True, help="Merged train/val pool jsonl")
    parser.add_argument("--base-feature-csv", required=True, help="Base feature CSV (e.g. full_features_with_id_v332_turn.csv)")
    parser.add_argument(
        "--supp-feature-csv",
        nargs="*",
        default=[],
        help="Optional supplement feature CSV(s), same schema as base. Later files overwrite earlier by sample_id.",
    )
    parser.add_argument("--out-feature-csv", required=True, help="Output aligned feature CSV for v3.4")
    parser.add_argument("--out-report", required=True, help="Output report json")
    args = parser.parse_args()

    labels_path = Path(args.labels).resolve()
    base_csv = Path(args.base_feature_csv).resolve()
    supp_csvs = [Path(x).resolve() for x in args.supp_feature_csv]
    out_csv = Path(args.out_feature_csv).resolve()
    out_report = Path(args.out_report).resolve()

    label_rows = load_jsonl(labels_path)
    label_map: Dict[str, Dict[str, Any]] = {}
    for r in label_rows:
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            label_map[sid] = r
    label_sids: Set[str] = set(label_map.keys())

    frames: List[pd.DataFrame] = []
    base_df = pd.read_csv(base_csv)
    if "sample_id" not in base_df.columns:
        raise RuntimeError(f"{base_csv} missing sample_id")
    frames.append(base_df)
    for sp in supp_csvs:
        if not sp.exists():
            raise FileNotFoundError(sp)
        sdf = pd.read_csv(sp)
        if "sample_id" not in sdf.columns:
            raise RuntimeError(f"{sp} missing sample_id")
        frames.append(sdf)

    merged = pd.concat(frames, ignore_index=True)
    merged["sample_id"] = merged["sample_id"].astype(str).str.strip()
    merged = merged.drop_duplicates(subset=["sample_id"], keep="last")
    aligned = merged[merged["sample_id"].isin(label_sids)].copy()

    # Force accident_type/video to labels side for consistency.
    if "accident_type" in aligned.columns:
        aligned["accident_type"] = aligned["sample_id"].map(
            lambda sid: str(label_map.get(str(sid), {}).get("accident_type", ""))
        )
    if "video" in aligned.columns:
        aligned["video"] = aligned["sample_id"].map(
            lambda sid: str(label_map.get(str(sid), {}).get("video", ""))
        )

    aligned = aligned.sort_values("sample_id").reset_index(drop=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    aligned.to_csv(out_csv, index=False)

    aligned_sids = set(aligned["sample_id"].astype(str).tolist())
    missing = sorted(list(label_sids - aligned_sids))
    report = {
        "labels": str(labels_path),
        "base_feature_csv": str(base_csv),
        "supp_feature_csv": [str(x) for x in supp_csvs],
        "rows_labels": len(label_rows),
        "rows_labels_unique_sid": len(label_sids),
        "rows_output": int(len(aligned)),
        "missing_feature_count": len(missing),
        "missing_sample_ids_head": missing[:50],
        "out_feature_csv": str(out_csv),
    }
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

