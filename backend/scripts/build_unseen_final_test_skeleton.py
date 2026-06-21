import argparse
import json
from pathlib import Path
from typing import Dict, List


def normalize_rel_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def make_unique_sample_id(prefix: str, rel_path: str, used: Dict[str, int]) -> str:
    stem = Path(rel_path).stem
    base = f"{prefix}_{stem}"
    if base not in used:
        used[base] = 1
        return base
    idx = used[base]
    used[base] += 1
    return f"{base}_{idx}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build raw annotation skeleton jsonl for unseen final-test videos."
    )
    parser.add_argument(
        "--videos-root",
        default="backend/videos",
        help="Project video root directory",
    )
    parser.add_argument(
        "--source-dir",
        default="backend/videos/final_test_unseen",
        help="Folder containing unseen final-test mp4 videos",
    )
    parser.add_argument(
        "--out-jsonl",
        default="data/processed/labels_final_test_unseen.raw.jsonl",
        help="Output raw jsonl skeleton",
    )
    parser.add_argument(
        "--sample-prefix",
        default="finaltest",
        help="sample_id prefix",
    )
    args = parser.parse_args()

    videos_root = Path(args.videos_root).resolve()
    source_dir = Path(args.source_dir).resolve()
    out_jsonl = Path(args.out_jsonl).resolve()
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)

    if not videos_root.exists():
        raise FileNotFoundError(f"videos root not found: {videos_root}")
    if not source_dir.exists():
        source_dir.mkdir(parents=True, exist_ok=True)

    mp4s = sorted(source_dir.rglob("*.mp4"))
    used: Dict[str, int] = {}
    rows: List[Dict] = []
    for p in mp4s:
        rel = normalize_rel_path(p, videos_root)
        rows.append(
            {
                "sample_id": make_unique_sample_id(str(args.sample_prefix), rel, used),
                "split": "final_test_unseen",
                "video": rel,
                "accident_type": "",
                "onset_time": None,
                "impact_time": None,
                "post_time": None,
                "scene_tags": [],
                "notes": "",
            }
        )

    with out_jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(
        json.dumps(
            {
                "videos_root": str(videos_root),
                "source_dir": str(source_dir),
                "out_jsonl": str(out_jsonl),
                "n_videos": len(mp4s),
                "n_rows": len(rows),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

