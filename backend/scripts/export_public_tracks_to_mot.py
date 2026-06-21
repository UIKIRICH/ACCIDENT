import argparse
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


def parse_recording_filter(raw: str) -> set:
    raw = (raw or "").strip()
    if not raw:
        return set()
    items = set()
    for x in raw.split(","):
        s = x.strip()
        if not s:
            continue
        items.add(s)
    return items


def iter_track_csvs(data_dir: Path) -> Iterable[Tuple[str, Path]]:
    for p in sorted(data_dir.glob("*_tracks.csv")):
        stem = p.name.replace("_tracks.csv", "")
        yield stem, p


def to_mot_rows_highd(df: pd.DataFrame) -> List[Tuple[int, int, float, float, float, float]]:
    needed = ["frame", "id", "x", "y", "width", "height"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"highD tracks missing column: {c}")

    rows: List[Tuple[int, int, float, float, float, float]] = []
    for _, r in df.iterrows():
        frame = int(r["frame"])
        tid = int(r["id"])
        x = float(r["x"])
        y = float(r["y"])
        w = float(r["width"])
        h = float(r["height"])
        rows.append((frame, tid, x, y, w, h))
    return rows


def to_mot_rows_exid(df: pd.DataFrame) -> List[Tuple[int, int, float, float, float, float]]:
    needed = ["frame", "trackId", "xCenter", "yCenter", "width", "length"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"exiD tracks missing column: {c}")

    rows: List[Tuple[int, int, float, float, float, float]] = []
    for _, r in df.iterrows():
        # exiD frame is zero-based; MOT is one-based.
        frame = int(r["frame"]) + 1
        tid = int(r["trackId"])
        w = float(r["width"])
        h = float(r["length"])
        x = float(r["xCenter"]) - w / 2.0
        y = float(r["yCenter"]) - h / 2.0
        rows.append((frame, tid, x, y, w, h))
    return rows


def write_mot_gt(rows: List[Tuple[int, int, float, float, float, float]], out_txt: Path) -> Dict[str, int]:
    rows_sorted = sorted(rows, key=lambda x: (x[0], x[1]))
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    with out_txt.open("w", encoding="utf-8") as f:
        for frame, tid, x, y, w, h in rows_sorted:
            # MOT gt format: frame,id,x,y,w,h,conf,class,visibility
            f.write(f"{frame},{tid},{x:.6f},{y:.6f},{w:.6f},{h:.6f},1,1,1\n")

    frames = {r[0] for r in rows_sorted}
    ids = {r[1] for r in rows_sorted}
    return {
        "rows": len(rows_sorted),
        "frames": len(frames),
        "tracks": len(ids),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert public trajectory tracks (highD/exiD) to MOT ground-truth txt files."
    )
    parser.add_argument("--dataset", required=True, choices=["highd", "exid"], help="Public dataset schema.")
    parser.add_argument("--data-dir", required=True, help="Directory containing *_tracks.csv files.")
    parser.add_argument("--out-dir", required=True, help="Output directory for MOT gt txt files.")
    parser.add_argument(
        "--recordings",
        default="",
        help="Optional comma-separated recording ids/stems, e.g. 01,02 or 00,01.",
    )
    parser.add_argument(
        "--report-json",
        default="",
        help="Optional output report json path. Default: <out-dir>/export_report.json",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    rec_filter = parse_recording_filter(args.recordings)
    report_path = Path(args.report_json).resolve() if args.report_json else (out_dir / "export_report.json")

    if not data_dir.exists():
        raise FileNotFoundError(f"data-dir not found: {data_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {
        "dataset": args.dataset,
        "data_dir": str(data_dir),
        "out_dir": str(out_dir),
        "recordings_filter": sorted(list(rec_filter)),
        "sequences": {},
    }

    for stem, track_csv in iter_track_csvs(data_dir):
        if rec_filter and stem not in rec_filter:
            continue
        df = pd.read_csv(track_csv)
        if args.dataset == "highd":
            rows = to_mot_rows_highd(df)
            seq_name = f"highd_{stem}"
        else:
            rows = to_mot_rows_exid(df)
            seq_name = f"exid_{stem}"

        out_txt = out_dir / f"{seq_name}.txt"
        stats = write_mot_gt(rows, out_txt)
        stats["source_tracks_csv"] = str(track_csv)
        stats["mot_gt_txt"] = str(out_txt)
        summary["sequences"][seq_name] = stats
        print(f"[DONE] {seq_name}: rows={stats['rows']} frames={stats['frames']} tracks={stats['tracks']}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] report: {report_path}")


if __name__ == "__main__":
    main()

