import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def normalize_video_key(v: Any) -> str:
    s = str(v or "").strip().replace("\\", "/").lower()
    if not s:
        return ""
    return Path(s).name


def build_feature_video_to_sid(
    feature_csv: Path,
    video_col: str,
    sample_id_col: str,
) -> Tuple[Dict[str, str], int]:
    video_to_sid: Dict[str, str] = {}
    ambiguous = 0

    with feature_csv.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"{feature_csv} has no header")
        if video_col not in reader.fieldnames:
            raise ValueError(f"{feature_csv} missing column: {video_col}")
        if sample_id_col not in reader.fieldnames:
            raise ValueError(f"{feature_csv} missing column: {sample_id_col}")

        for row in reader:
            vkey = normalize_video_key(row.get(video_col, ""))
            sid = str(row.get(sample_id_col, "")).strip()
            if not vkey or not sid:
                continue
            prev = video_to_sid.get(vkey)
            if prev is None:
                video_to_sid[vkey] = sid
            elif prev != sid:
                ambiguous += 1
                # Keep first mapping stable.
    return video_to_sid, ambiguous


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Align label sample_id using feature CSV video->sample_id mapping."
    )
    parser.add_argument("--labels-in", required=True, help="Input labels jsonl")
    parser.add_argument("--feature-csv", required=True, help="Feature csv with video and sample_id columns")
    parser.add_argument("--labels-out", required=True, help="Output labels jsonl")
    parser.add_argument("--report", required=True, help="Output report json")
    parser.add_argument("--label-video-field", default="video", help="Label json field name for video")
    parser.add_argument("--video-col", default="video", help="Feature csv video column")
    parser.add_argument("--sample-id-col", default="sample_id", help="Feature csv sample_id column")
    parser.add_argument(
        "--only-when-missing",
        action="store_true",
        help="Only overwrite sample_id when label sample_id is empty",
    )
    args = parser.parse_args()

    labels_in = Path(args.labels_in).resolve()
    feature_csv = Path(args.feature_csv).resolve()
    labels_out = Path(args.labels_out).resolve()
    report_path = Path(args.report).resolve()

    rows = load_jsonl(labels_in)
    video_to_sid, ambiguous = build_feature_video_to_sid(
        feature_csv=feature_csv,
        video_col=str(args.video_col),
        sample_id_col=str(args.sample_id_col),
    )

    matched = 0
    overwritten = 0
    unchanged = 0
    unmatched = 0

    out_rows: List[Dict[str, Any]] = []
    for r in rows:
        out = dict(r)
        vkey = normalize_video_key(out.get(args.label_video_field, ""))
        sid_old = str(out.get("sample_id", "")).strip()
        sid_new = video_to_sid.get(vkey, "")

        if sid_new:
            matched += 1
            if args.only_when_missing and sid_old:
                unchanged += 1
            elif sid_old != sid_new:
                out["sample_id"] = sid_new
                overwritten += 1
            else:
                unchanged += 1
        else:
            unmatched += 1

        out_rows.append(out)

    dump_jsonl(labels_out, out_rows)

    report = {
        "labels_in": str(labels_in),
        "feature_csv": str(feature_csv),
        "labels_out": str(labels_out),
        "rows_input": len(rows),
        "rows_output": len(out_rows),
        "video_keys_in_feature_map": len(video_to_sid),
        "ambiguous_video_keys_in_feature_map": int(ambiguous),
        "matched_video_rows": int(matched),
        "unmatched_video_rows": int(unmatched),
        "sample_id_overwritten": int(overwritten),
        "sample_id_unchanged": int(unchanged),
        "only_when_missing": bool(args.only_when_missing),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

