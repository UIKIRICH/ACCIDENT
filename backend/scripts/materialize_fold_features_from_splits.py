import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd


def load_videos_from_jsonl(path: Path) -> Set[str]:
    videos: Set[str] = set()
    with path.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            videos.add(str(obj.get("video", "")).strip())
    return videos


def save_subset(df: pd.DataFrame, videos: Set[str], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sel = df[df["video"].astype(str).isin(videos)].copy()
    sel.to_parquet(out_path, index=False)
    return int(len(sel))


def main() -> None:
    parser = argparse.ArgumentParser(description="Materialize per-fold train/val features and meta from all.parquet")
    parser.add_argument("--splits-dir", required=True, help="Directory with fold{i}_train.jsonl and fold{i}_val.jsonl")
    parser.add_argument("--features-all", required=True, help="features_all.parquet")
    parser.add_argument("--meta-all", required=True, help="meta_all.parquet")
    parser.add_argument("--out-dir", required=True, help="Output directory for per-fold files")
    parser.add_argument("--n-splits", type=int, default=5, help="Number of folds")
    parser.add_argument("--report", required=True, help="Output report json")
    args = parser.parse_args()

    splits_dir = Path(args.splits_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    features_all = pd.read_parquet(Path(args.features_all).resolve())
    meta_all = pd.read_parquet(Path(args.meta_all).resolve())

    report: Dict[str, Dict[str, int]] = {}
    for fold in range(int(args.n_splits)):
        train_json = splits_dir / f"fold{fold}_train.jsonl"
        val_json = splits_dir / f"fold{fold}_val.jsonl"
        train_videos = load_videos_from_jsonl(train_json)
        val_videos = load_videos_from_jsonl(val_json)

        feat_train = out_dir / f"features_fold{fold}_train.parquet"
        feat_val = out_dir / f"features_fold{fold}_val.parquet"
        meta_train = out_dir / f"meta_fold{fold}_train.parquet"
        meta_val = out_dir / f"meta_fold{fold}_val.parquet"

        feat_train_rows = save_subset(features_all, train_videos, feat_train)
        feat_val_rows = save_subset(features_all, val_videos, feat_val)
        meta_train_rows = save_subset(meta_all, train_videos, meta_train)
        meta_val_rows = save_subset(meta_all, val_videos, meta_val)

        report[f"fold{fold}"] = {
            "train_videos": int(len(train_videos)),
            "val_videos": int(len(val_videos)),
            "features_train_rows": feat_train_rows,
            "features_val_rows": feat_val_rows,
            "meta_train_rows": meta_train_rows,
            "meta_val_rows": meta_val_rows,
        }
        print(
            f"[DONE] fold{fold} train_videos={len(train_videos)} val_videos={len(val_videos)} "
            f"meta_train={meta_train_rows} meta_val={meta_val_rows}"
        )

    out_report = Path(args.report).resolve()
    out_report.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "splits_dir": str(splits_dir),
        "features_all": str(Path(args.features_all).resolve()),
        "meta_all": str(Path(args.meta_all).resolve()),
        "out_dir": str(out_dir),
        "n_splits": int(args.n_splits),
        "fold_stats": report,
    }
    out_report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] report={out_report}")


if __name__ == "__main__":
    main()
