import argparse
import json
from pathlib import Path
from typing import Dict, List


VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def list_videos(videos_dir: Path) -> List[Path]:
    files = []
    for p in videos_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            files.append(p)
    return sorted(files)


def make_record(video_path: Path, base_dir: Path, split: str) -> Dict:
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
    parser = argparse.ArgumentParser(description="Build annotation jsonl from a video directory.")
    parser.add_argument("--videos-dir", required=True, help="Video folder to scan (e.g. ./backend/videos/train)")
    parser.add_argument("--base-dir", default="", help="Base dir for relative path in `video` field; defaults to parent of videos-dir")
    parser.add_argument("--split", default="train", help="Split name")
    parser.add_argument("--out", required=True, help="Output jsonl path")
    args = parser.parse_args()

    videos_dir = Path(args.videos_dir).resolve()
    if not videos_dir.exists():
        raise FileNotFoundError(f"videos-dir not found: {videos_dir}")
    base_dir = Path(args.base_dir).resolve() if args.base_dir else videos_dir.parent.resolve()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    videos = list_videos(videos_dir)
    records = [make_record(v, base_dir, args.split) for v in videos]

    with out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[DONE] videos={len(videos)} out={out}")


if __name__ == "__main__":
    main()
