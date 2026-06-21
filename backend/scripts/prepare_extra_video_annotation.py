import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def list_videos(videos_dir: Path) -> List[Path]:
    files: List[Path] = []
    for p in videos_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            files.append(p)
    return sorted(files)


def make_record(video_path: Path, base_dir: Path, split: str) -> Dict[str, object]:
    rel = video_path.relative_to(base_dir).as_posix()
    return {
        "sample_id": f"{split}_{video_path.stem}",
        "split": split,
        "video": rel,
        "accident_type": "",
        "onset_time": None,
        "impact_time": None,
        "post_time": None,
        "scene_tags": [],
        "notes": "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare annotation files from extra video folder: raw jsonl + annotation xlsx."
    )
    parser.add_argument(
        "--videos-dir",
        default="backend/videos/extra video",
        help="Video directory to scan",
    )
    parser.add_argument(
        "--base-dir",
        default="backend/videos",
        help="Base directory for relative `video` paths in jsonl",
    )
    parser.add_argument(
        "--split",
        default="train",
        help="Split field value in generated records",
    )
    parser.add_argument(
        "--out-jsonl",
        default="data/processed/labels_extra_video_raw.jsonl",
        help="Output raw jsonl path",
    )
    parser.add_argument(
        "--out-xlsx",
        default="data/processed/labels_extra_video_annotation.xlsx",
        help="Output annotation xlsx path",
    )
    parser.add_argument(
        "--sheet",
        default="annotation",
        help="Excel sheet name",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    videos_dir = (project_root / args.videos_dir).resolve()
    base_dir = (project_root / args.base_dir).resolve()
    out_jsonl = (project_root / args.out_jsonl).resolve()
    out_xlsx = (project_root / args.out_xlsx).resolve()
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)

    if not videos_dir.exists():
        raise FileNotFoundError(f"videos-dir not found: {videos_dir}")
    if not base_dir.exists():
        raise FileNotFoundError(f"base-dir not found: {base_dir}")

    videos = list_videos(videos_dir)
    records = [make_record(v, base_dir, args.split) for v in videos]

    with out_jsonl.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    xlsx_script = (Path(__file__).resolve().parent / "jsonl_to_annotation_xlsx.py").resolve()
    cmd = [
        sys.executable,
        str(xlsx_script),
        "--input",
        str(out_jsonl),
        "--output",
        str(out_xlsx),
        "--sheet",
        str(args.sheet),
    ]
    subprocess.run(cmd, check=True)

    print(
        json.dumps(
            {
                "videos_dir": str(videos_dir),
                "count_videos": len(videos),
                "split": args.split,
                "out_jsonl": str(out_jsonl),
                "out_xlsx": str(out_xlsx),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
