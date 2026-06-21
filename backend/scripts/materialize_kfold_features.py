import argparse
import json
from pathlib import Path
from typing import Dict, List, Set

import pandas as pd


def load_label_videos(path: Path) -> Set[str]:
    vids: Set[str] = set()
    with path.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            vids.add(str(obj.get("video", "")).strip())
    return vids


def select_and_write(
    features_df: pd.DataFrame,
    meta_df: pd.DataFrame,
    videos: Set[str],
    out_features: Path,
    out_meta: Path,
) -> Dict[str, int]:
    fsel = features_df[features_df["video"].astype(str).isin(videos)].copy()
    msel = meta_df[meta_df["video"].astype(str).isin(videos)].copy()
    out_features.parent.mkdir(parents=True, exist_ok=True)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    fsel.to_parquet(out_features, index=False)
    msel.to_parquet(out_meta, index=False)
    return {
        "videos": int(len(videos)),
        "feature_rows": int(len(fsel)),
        "meta_rows": int(len(msel)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize per-fold train/val feature parquet from all-features parquet."
    )
    parser.add_argument("--fold-dir", required=True, help="Directory containing *.fold{i}.train/val.jsonl")
    parser.add_argument("--prefix", required=True, help="Fold file prefix")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--features-all", required=True, help="features_all.parquet")
    parser.add_argument("--meta-all", required=True, help="meta_all.parquet")
    parser.add_argument("--out-dir", required=True, help="Output directory for per-fold parquet")
    parser.add_argument("--report", required=True, help="Output report json")
    args = parser.parse_args()

    fold_dir = Path(args.fold_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    report_path = Path(args.report).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    features_all = Path(args.features_all).resolve()
    meta_all = Path(args.meta_all).resolve()
    features_df = pd.read_parquet(features_all)
    meta_df = pd.read_parquet(meta_all)

    report: Dict[str, Dict[str, int]] = {}
    for fold in range(int(args.n_splits)):
        train_json = fold_dir / f"{args.prefix}.fold{fold}.train.jsonl"
        val_json = fold_dir / f"{args.prefix}.fold{fold}.val.jsonl"
        train_videos = load_label_videos(train_json)
        val_videos = load_label_videos(val_json)

        fold_out = out_dir / f"fold{fold}"
        train_feat = fold_out / "features_train.parquet"
        train_meta = fold_out / "meta_train.parquet"
        val_feat = fold_out / "features_val.parquet"
        val_meta = fold_out / "meta_val.parquet"

        train_stat = select_and_write(features_df, meta_df, train_videos, train_feat, train_meta)
        val_stat = select_and_write(features_df, meta_df, val_videos, val_feat, val_meta)

        report[f"fold{fold}"] = {
            "train_videos": train_stat["videos"],
            "train_feature_rows": train_stat["feature_rows"],
            "train_meta_rows": train_stat["meta_rows"],
            "val_videos": val_stat["videos"],
            "val_feature_rows": val_stat["feature_rows"],
            "val_meta_rows": val_stat["meta_rows"],
        }

        print(
            f"[DONE] fold{fold}: train_videos={train_stat['videos']} val_videos={val_stat['videos']} "
            f"train_meta={train_stat['meta_rows']} val_meta={val_stat['meta_rows']}"
        )

    full_report = {
        "fold_dir": str(fold_dir),
        "prefix": str(args.prefix),
        "n_splits": int(args.n_splits),
        "features_all": str(features_all),
        "meta_all": str(meta_all),
        "out_dir": str(out_dir),
        "fold_stats": report,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(full_report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] report={report_path}")


if __name__ == "__main__":
    main()
