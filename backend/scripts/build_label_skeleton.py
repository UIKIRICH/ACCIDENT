from pathlib import Path
import json

# 项目根目录（相对于当前脚本向上两级：scripts -> backend -> project root）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 视频目录
VIDEOS_ROOT = PROJECT_ROOT / "backend" / "videos"

# 输出目录
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 目录名到 split 的映射
# 注意：你的目录叫 var，这里统一映射成 val
SPLIT_MAP = {
    "train": "train",
    "test": "test",
    "var": "val",
    "val": "val",
}

def normalize_rel_path(path: Path, root: Path) -> str:
    """把路径转成相对路径，并统一为 / 分隔符"""
    return path.relative_to(root).as_posix()

def make_sample_id(split: str, video_file: Path) -> str:
    """给每条样本生成稳定的 sample_id"""
    return f"{split}_{video_file.stem}"

def build_record(split: str, video_file: Path):
    """
    生成一条最小字段版 jsonl 记录
    语义字段先留空，后面人工补
    """
    return {
        "sample_id": make_sample_id(split, video_file),
        "split": split,
        "video": normalize_rel_path(video_file, VIDEOS_ROOT),
        "accident_type": "",
        "onset_time": None,
        "impact_time": None,
        "post_time": None,
        "scene_tags": []
    }

def main():
    split_records = {
        "train": [],
        "val": [],
        "test": []
    }

    if not VIDEOS_ROOT.exists():
        raise FileNotFoundError(f"视频目录不存在: {VIDEOS_ROOT}")

    # 扫描 train/test/var/val 子目录
    for subdir in VIDEOS_ROOT.iterdir():
        if not subdir.is_dir():
            continue

        folder_name = subdir.name.lower().strip()
        if folder_name not in SPLIT_MAP:
            print(f"[跳过] 未识别目录: {subdir}")
            continue

        split = SPLIT_MAP[folder_name]
        video_files = sorted(subdir.rglob("*.mp4"))

        print(f"[扫描] {subdir.name} -> split={split}, 视频数={len(video_files)}")

        for video_file in video_files:
            record = build_record(split, video_file)
            split_records[split].append(record)

    # 去重检查：sample_id 不能重复
    all_ids = set()
    for split, records in split_records.items():
        for r in records:
            sid = r["sample_id"]
            if sid in all_ids:
                raise ValueError(f"发现重复 sample_id: {sid}")
            all_ids.add(sid)

    # 写出 jsonl
    output_files = {
        "train": OUTPUT_DIR / "labels_train.jsonl",
        "val": OUTPUT_DIR / "labels_val.jsonl",
        "test": OUTPUT_DIR / "labels_test.jsonl",
    }

    for split, out_path in output_files.items():
        with open(out_path, "w", encoding="utf-8") as f:
            for record in split_records[split]:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"[写出] {out_path}  共 {len(split_records[split])} 条")

    total = sum(len(v) for v in split_records.values())
    print("\n=== 完成 ===")
    print(f"总样本数: {total}")
    print(f"train: {len(split_records['train'])}")
    print(f"val  : {len(split_records['val'])}")
    print(f"test : {len(split_records['test'])}")

if __name__ == "__main__":
    main()