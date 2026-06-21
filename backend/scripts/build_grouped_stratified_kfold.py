import argparse
import csv
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


TARGET_CLASSES = ["rear_end", "lane_change", "turn_conflict"]
TARGET_CLASS_SET = set(TARGET_CLASSES)
SCENE_TAGS_FOR_SUMMARY = [
    "day",
    "night",
    "rain",
    "intersection",
    "straight_road",
    "turning_scene",
]


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
            out = dict(row)
            out.pop("_line_no", None)
            f.write(json.dumps(out, ensure_ascii=False) + "\n")


def canonical_group_key(video_field: str) -> str:
    stem = Path(video_field).stem.lower().strip()
    stem = re.sub(r"_[0-9a-f]{8}$", "", stem)
    stem = re.sub(r"^aug_\d+_", "", stem)
    stem = re.sub(r"[^a-z0-9_]+", "_", stem)
    return stem if stem else "unknown_group"


def ensure_group_id(row: Dict[str, Any]) -> str:
    existing = str(row.get("group_id", "")).strip()
    if existing:
        return existing
    video = str(row.get("video", "")).strip()
    gid = canonical_group_key(video)
    row["group_id"] = gid
    return gid


def class_idx(accident_type: str) -> int:
    return TARGET_CLASSES.index(accident_type)


def build_groups(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in rows:
        t = str(row.get("accident_type", "")).strip()
        if t not in TARGET_CLASS_SET:
            continue
        gid = ensure_group_id(row)
        groups[gid].append(row)
    return groups


def group_class_vector(group_rows: List[Dict[str, Any]]) -> List[int]:
    vec = [0, 0, 0]
    for row in group_rows:
        t = str(row.get("accident_type", "")).strip()
        if t in TARGET_CLASS_SET:
            vec[class_idx(t)] += 1
    return vec


def choose_best_fold(
    group_vec: List[int],
    group_size: int,
    fold_class_counts: List[List[int]],
    fold_sizes: List[int],
    target_class_per_fold: List[float],
    target_size_per_fold: float,
) -> int:
    def var(xs: List[float]) -> float:
        if not xs:
            return 0.0
        m = sum(xs) / len(xs)
        return sum((x - m) ** 2 for x in xs) / len(xs)

    best_fold = 0
    best_score = None
    for f in range(len(fold_sizes)):
        tmp_sizes = list(fold_sizes)
        tmp_sizes[f] += group_size

        tmp_counts = [list(x) for x in fold_class_counts]
        for c in range(len(TARGET_CLASSES)):
            tmp_counts[f][c] += group_vec[c]

        cls_term = 0.0
        for c in range(len(TARGET_CLASSES)):
            cls_vals = [tmp_counts[k][c] for k in range(len(tmp_counts))]
            denom = max(1.0, target_class_per_fold[c] ** 2)
            cls_term += var([float(x) for x in cls_vals]) / denom

        size_term = var([float(x) for x in tmp_sizes]) / max(1.0, target_size_per_fold**2)
        score = cls_term + 0.35 * size_term
        if best_score is None or score < best_score - 1e-12:
            best_score = score
            best_fold = f
        elif abs(score - best_score) <= 1e-12:
            if fold_sizes[f] < fold_sizes[best_fold]:
                best_fold = f
    return best_fold


def assign_groups_to_folds(groups: Dict[str, List[Dict[str, Any]]], n_splits: int, seed: int) -> Dict[str, int]:
    rng = random.Random(seed)
    group_items: List[Tuple[str, List[Dict[str, Any]], List[int]]] = []
    total_class = [0, 0, 0]
    total_rows = 0

    for gid, rows in groups.items():
        vec = group_class_vector(rows)
        total_rows += len(rows)
        for i in range(3):
            total_class[i] += vec[i]
        group_items.append((gid, rows, vec))

    # Harder groups first: larger size and more imbalanced class contribution.
    group_items.sort(
        key=lambda x: (
            -len(x[1]),
            -max(x[2]),
            -sum(1 for v in x[2] if v > 0),
            x[0],
        )
    )

    # Shuffle among exact ties to avoid deterministic bias.
    i = 0
    while i < len(group_items):
        j = i + 1
        while j < len(group_items) and (
            len(group_items[j][1]) == len(group_items[i][1])
            and max(group_items[j][2]) == max(group_items[i][2])
            and sum(1 for v in group_items[j][2] if v > 0) == sum(1 for v in group_items[i][2] if v > 0)
        ):
            j += 1
        if j - i > 1:
            block = group_items[i:j]
            rng.shuffle(block)
            group_items[i:j] = block
        i = j

    fold_class_counts = [[0, 0, 0] for _ in range(n_splits)]
    fold_sizes = [0 for _ in range(n_splits)]
    target_class_per_fold = [x / n_splits for x in total_class]
    target_size_per_fold = total_rows / n_splits

    gid_to_fold: Dict[str, int] = {}
    for idx, (gid, rows, vec) in enumerate(group_items):
        # Seed each fold with one group to avoid empty folds.
        if idx < n_splits:
            fold = idx
        else:
            fold = choose_best_fold(
                group_vec=vec,
                group_size=len(rows),
                fold_class_counts=fold_class_counts,
                fold_sizes=fold_sizes,
                target_class_per_fold=target_class_per_fold,
                target_size_per_fold=target_size_per_fold,
            )
        gid_to_fold[gid] = fold
        fold_sizes[fold] += len(rows)
        for c in range(3):
            fold_class_counts[fold][c] += vec[c]

    return gid_to_fold


def summarize_scene(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    out: Counter[str] = Counter()
    for row in rows:
        tags = row.get("scene_tags", [])
        if not isinstance(tags, list):
            continue
        for t in tags:
            ts = str(t).strip()
            if ts in SCENE_TAGS_FOR_SUMMARY:
                out[ts] += 1
    return {k: int(out.get(k, 0)) for k in SCENE_TAGS_FOR_SUMMARY}


def class_distribution(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    c = Counter(str(r.get("accident_type", "")).strip() for r in rows)
    return {k: int(c.get(k, 0)) for k in TARGET_CLASSES}


def leakage_check(folds: Dict[int, List[Dict[str, Any]]]) -> Dict[str, Any]:
    group_to_fold: Dict[str, int] = {}
    leaked_groups: List[str] = []
    for fold_id, rows in folds.items():
        for row in rows:
            gid = str(row.get("group_id", "")).strip()
            if not gid:
                continue
            prev = group_to_fold.get(gid)
            if prev is None:
                group_to_fold[gid] = fold_id
            elif prev != fold_id:
                leaked_groups.append(gid)
    leaked_groups = sorted(set(leaked_groups))
    return {
        "leak_group_count": len(leaked_groups),
        "leak_groups": leaked_groups,
    }


def write_split_summary_csv(path: Path, folds: Dict[int, List[Dict[str, Any]]], all_rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = [
        "fold_id",
        "val_rows",
        "train_rows",
        "val_groups",
        "train_groups",
        "val_rear_end",
        "val_lane_change",
        "val_turn_conflict",
        "train_rear_end",
        "train_lane_change",
        "train_turn_conflict",
    ] + [f"val_{t}" for t in SCENE_TAGS_FOR_SUMMARY] + [f"train_{t}" for t in SCENE_TAGS_FOR_SUMMARY]

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()

        for fold_id in sorted(folds.keys()):
            val_rows = folds[fold_id]
            train_rows = [r for r in all_rows if int(r.get("fold_id", -1)) != fold_id]

            val_cls = class_distribution(val_rows)
            train_cls = class_distribution(train_rows)
            val_scene = summarize_scene(val_rows)
            train_scene = summarize_scene(train_rows)

            row = {
                "fold_id": fold_id,
                "val_rows": len(val_rows),
                "train_rows": len(train_rows),
                "val_groups": len(set(str(r.get("group_id", "")) for r in val_rows)),
                "train_groups": len(set(str(r.get("group_id", "")) for r in train_rows)),
                "val_rear_end": val_cls["rear_end"],
                "val_lane_change": val_cls["lane_change"],
                "val_turn_conflict": val_cls["turn_conflict"],
                "train_rear_end": train_cls["rear_end"],
                "train_lane_change": train_cls["lane_change"],
                "train_turn_conflict": train_cls["turn_conflict"],
            }
            for t in SCENE_TAGS_FOR_SUMMARY:
                row[f"val_{t}"] = val_scene[t]
                row[f"train_{t}"] = train_scene[t]
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Add group_id and build leakage-safe grouped stratified K-fold splits."
    )
    parser.add_argument("--input", required=True, help="Input labels jsonl (recommended high_conf_train)")
    parser.add_argument("--out-with-group", required=True, help="Output labels jsonl with group_id and fold_id")
    parser.add_argument("--out-splits-dir", required=True, help="Output split directory")
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-summary-csv", required=True, help="Split summary csv output")
    parser.add_argument("--out-report-json", required=True, help="Detailed report json output")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    out_with_group = Path(args.out_with_group).resolve()
    out_splits_dir = Path(args.out_splits_dir).resolve()
    out_summary_csv = Path(args.out_summary_csv).resolve()
    out_report_json = Path(args.out_report_json).resolve()

    rows = load_jsonl(input_path)
    rows = [r for r in rows if str(r.get("accident_type", "")).strip() in TARGET_CLASS_SET]
    if len(rows) < args.n_splits:
        raise ValueError(f"rows={len(rows)} < n_splits={args.n_splits}")

    groups = build_groups(rows)
    gid_to_fold = assign_groups_to_folds(groups, n_splits=int(args.n_splits), seed=int(args.seed))

    fold_to_rows: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for gid, grows in groups.items():
        fold_id = int(gid_to_fold[gid])
        for row in grows:
            row["group_id"] = gid
            row["fold_id"] = fold_id
            fold_to_rows[fold_id].append(row)

    # flatten rows in stable order by original line_no
    rows_with_group = sorted(
        [r for folds in fold_to_rows.values() for r in folds],
        key=lambda x: int(x.get("_line_no", 0)),
    )
    dump_jsonl(out_with_group, rows_with_group)

    out_splits_dir.mkdir(parents=True, exist_ok=True)
    for fold in range(int(args.n_splits)):
        val_rows = sorted(
            [dict(r) for r in fold_to_rows.get(fold, [])],
            key=lambda x: int(x.get("_line_no", 0)),
        )
        train_rows = sorted(
            [dict(r) for r in rows_with_group if int(r.get("fold_id", -1)) != fold],
            key=lambda x: int(x.get("_line_no", 0)),
        )
        for r in val_rows:
            r["split"] = "val"
        for r in train_rows:
            r["split"] = "train"

        dump_jsonl(out_splits_dir / f"fold{fold}_val.jsonl", val_rows)
        dump_jsonl(out_splits_dir / f"fold{fold}_train.jsonl", train_rows)

    write_split_summary_csv(out_summary_csv, fold_to_rows, rows_with_group)

    leakage = leakage_check(fold_to_rows)
    group_sizes = [len(v) for v in groups.values()]
    report = {
        "input": str(input_path),
        "rows_used": len(rows_with_group),
        "groups_total": len(groups),
        "group_size_stats": {
            "min": min(group_sizes) if group_sizes else 0,
            "max": max(group_sizes) if group_sizes else 0,
            "mean": round(sum(group_sizes) / len(group_sizes), 4) if group_sizes else 0.0,
        },
        "n_splits": int(args.n_splits),
        "seed": int(args.seed),
        "class_distribution_global": class_distribution(rows_with_group),
        "fold_class_distribution": {
            str(f): class_distribution(fold_to_rows.get(f, [])) for f in range(int(args.n_splits))
        },
        "fold_sizes": {str(f): len(fold_to_rows.get(f, [])) for f in range(int(args.n_splits))},
        "leakage_check": leakage,
        "outputs": {
            "with_group": str(out_with_group),
            "splits_dir": str(out_splits_dir),
            "split_summary_csv": str(out_summary_csv),
        },
    }
    out_report_json.parent.mkdir(parents=True, exist_ok=True)
    out_report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[DONE] with_group={out_with_group} rows={len(rows_with_group)}")
    print(f"[DONE] splits_dir={out_splits_dir}")
    print(f"[DONE] split_summary={out_summary_csv}")
    print(f"[DONE] report={out_report_json}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
