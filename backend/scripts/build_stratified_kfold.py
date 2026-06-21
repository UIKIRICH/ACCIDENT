import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


TARGET_CLASSES = {"rear_end", "lane_change", "turn_conflict"}


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            obj = json.loads(line)
            obj["_line_no"] = line_no
            rows.append(obj)
    return rows


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def scene_signature(scene_tags: Any) -> str:
    if not isinstance(scene_tags, list):
        return "_no_scene"
    tags = sorted({str(x).strip() for x in scene_tags if str(x).strip()})
    if not tags:
        return "_no_scene"
    return "+".join(tags)


def strat_key(row: Dict[str, Any]) -> str:
    t = str(row.get("accident_type", "")).strip()
    return f"{t}|{scene_signature(row.get('scene_tags'))}"


def quality_row(row: Dict[str, Any], fold_id: int) -> Dict[str, Any]:
    out = dict(row)
    out.pop("_line_no", None)
    out["fold_id"] = int(fold_id)
    out["strat_key"] = strat_key(row)
    return out


def alloc_folds(rows: List[Dict[str, Any]], n_splits: int, seed: int) -> List[Dict[str, Any]]:
    by_strata: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_strata[strat_key(row)].append(row)

    rng = random.Random(seed)
    out: List[Dict[str, Any]] = []
    for key in sorted(by_strata.keys()):
        group = by_strata[key]
        group_sorted = sorted(
            group,
            key=lambda r: (
                str(r.get("video", "")),
                str(r.get("sample_id", "")),
                int(r.get("_line_no", 0)),
            ),
        )
        rng.shuffle(group_sorted)
        for idx, row in enumerate(group_sorted):
            fold_id = idx % n_splits
            out.append(quality_row(row, fold_id))
    return out


def fold_stats(rows: List[Dict[str, Any]], n_splits: int) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "n_total": len(rows),
        "n_splits": n_splits,
        "folds": {},
        "global_type_distribution": {},
        "global_scene_top10": {},
    }

    type_global = Counter(str(r.get("accident_type", "")).strip() for r in rows)
    stats["global_type_distribution"] = dict(type_global)

    scene_global: Counter[str] = Counter()
    for r in rows:
        tags = r.get("scene_tags", [])
        if not isinstance(tags, list):
            tags = []
        for t in tags:
            scene_global[str(t)] += 1
    stats["global_scene_top10"] = dict(scene_global.most_common(10))

    for fold in range(n_splits):
        val_rows = [r for r in rows if int(r.get("fold_id", -1)) == fold]
        train_rows = [r for r in rows if int(r.get("fold_id", -1)) != fold]
        fold_obj: Dict[str, Any] = {
            "val_rows": len(val_rows),
            "train_rows": len(train_rows),
            "val_type_distribution": dict(Counter(str(r.get("accident_type", "")).strip() for r in val_rows)),
            "train_type_distribution": dict(Counter(str(r.get("accident_type", "")).strip() for r in train_rows)),
        }
        stats["folds"][str(fold)] = fold_obj
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build stratified K-fold split using accident_type + scene_tags signature."
    )
    parser.add_argument("--input", required=True, help="Input labels jsonl (recommended 3cls relaxed)")
    parser.add_argument("--out-dir", required=True, help="Output directory for fold label files")
    parser.add_argument("--n-splits", type=int, default=5, help="Number of folds")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--prefix", default="train_ext_relaxed3cls", help="Output file prefix")
    parser.add_argument("--report", required=True, help="Output report json path")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve()
    report_path = Path(args.report).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_jsonl(input_path)
    rows = [r for r in rows if str(r.get("accident_type", "")).strip() in TARGET_CLASSES]
    if len(rows) < args.n_splits:
        raise ValueError("Not enough rows for requested n_splits")

    assigned = alloc_folds(rows, n_splits=int(args.n_splits), seed=int(args.seed))

    assign_path = out_dir / f"{args.prefix}.fold_assignments.jsonl"
    dump_jsonl(assign_path, assigned)

    for fold in range(int(args.n_splits)):
        val_rows = [r for r in assigned if int(r["fold_id"]) == fold]
        train_rows = [r for r in assigned if int(r["fold_id"]) != fold]
        for r in val_rows:
            r["split"] = "val"
        for r in train_rows:
            r["split"] = "train"

        dump_jsonl(out_dir / f"{args.prefix}.fold{fold}.val.jsonl", val_rows)
        dump_jsonl(out_dir / f"{args.prefix}.fold{fold}.train.jsonl", train_rows)

    report = {
        "input": str(input_path),
        "out_dir": str(out_dir),
        "assignments_file": str(assign_path),
        "n_splits": int(args.n_splits),
        "seed": int(args.seed),
        "prefix": str(args.prefix),
        "stats": fold_stats(assigned, int(args.n_splits)),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] assignments={assign_path}")
    for fold in range(int(args.n_splits)):
        print(f"[DONE] fold{fold} train/val jsonl written in {out_dir}")
    print(f"[DONE] report={report_path}")
    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
