import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


FEATURES = [
    "duration_frames",
    "mean_x_velocity",
    "max_abs_y_velocity",
    "lane_change_count_track",
    "min_ttc_eff_capped",
    "min_thw_eff_capped",
    "ttc_missing",
    "thw_missing",
]


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


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


def safe_float(v: Any, default: float = np.nan) -> float:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(fv):
        return float(default)
    return float(fv)


def cap_or_nan(v: Any, cap: float) -> float:
    fv = safe_float(v, np.nan)
    if not np.isfinite(fv):
        return np.nan
    if fv < 0:
        return np.nan
    return float(min(fv, cap))


def parse_scene_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return []
        if s.startswith("[") and s.endswith("]"):
            try:
                arr = json.loads(s)
                if isinstance(arr, list):
                    return [str(x).strip() for x in arr if str(x).strip()]
            except Exception:
                return [s]
        return [s]
    return []


def scene_bucket(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    is_day = "day" in s
    is_night = "night" in s
    is_straight = "straight_road" in s
    is_inter = "intersection" in s
    if is_day and is_straight:
        return "day+straight_road"
    if is_day and is_inter:
        return "day+intersection"
    if is_night and is_straight:
        return "night+straight_road"
    if is_night and is_inter:
        return "night+intersection"
    return "other"


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def source_row_to_features(r: Dict[str, Any]) -> Dict[str, float]:
    ttc = cap_or_nan(r.get("min_ttc_eff"), cap=20.0)
    thw = cap_or_nan(r.get("min_thw_eff"), cap=10.0)
    return {
        "duration_frames": safe_float(r.get("duration_frames"), np.nan),
        "mean_x_velocity": safe_float(r.get("mean_x_velocity"), np.nan),
        "max_abs_y_velocity": safe_float(r.get("max_abs_y_velocity"), np.nan),
        "lane_change_count_track": safe_float(r.get("lane_change_count_track"), np.nan),
        "min_ttc_eff_capped": ttc,
        "min_thw_eff_capped": thw,
        "ttc_missing": 1.0 if not np.isfinite(ttc) else 0.0,
        "thw_missing": 1.0 if not np.isfinite(thw) else 0.0,
    }


def board_row_to_features(r: Dict[str, Any]) -> Dict[str, float]:
    ttc = cap_or_nan(r.get("min_ttc_eff"), cap=20.0)
    thw = cap_or_nan(r.get("min_thw_eff"), cap=10.0)
    return {
        "duration_frames": safe_float(r.get("pair_duration_frames"), np.nan),
        "mean_x_velocity": safe_float(r.get("mean_longitudinal_velocity_rel"), np.nan),
        "max_abs_y_velocity": safe_float(r.get("max_abs_lateral_velocity_rel"), np.nan),
        "lane_change_count_track": safe_float(r.get("lane_change_count_pair"), np.nan),
        "min_ttc_eff_capped": ttc,
        "min_thw_eff_capped": thw,
        "ttc_missing": 1.0 if not np.isfinite(ttc) else 0.0,
        "thw_missing": 1.0 if not np.isfinite(thw) else 0.0,
    }


def train_lane_rear_bridge(
    source_rows: List[Dict[str, Any]],
    train_recs: List[int],
    val_recs: List[int],
    test_recs: List[int],
    lr_random_seed: int = 42,
) -> Tuple[Pipeline, Dict[str, Any]]:
    train_set = set(int(x) for x in train_recs)
    val_set = set(int(x) for x in val_recs)
    test_set = set(int(x) for x in test_recs)

    work: List[Dict[str, Any]] = []
    for r in source_rows:
        c = str(r.get("candidate_type", "")).strip()
        if c not in {"lane_pos", "rear_risk_pos"}:
            continue
        rec = int(safe_float(r.get("recording_id"), -1))
        y = 1 if c == "lane_pos" else 0
        feat = source_row_to_features(r)
        feat["recording_id"] = rec
        feat["y"] = y
        work.append(feat)

    if not work:
        raise RuntimeError("no lane_pos/rear_risk_pos rows in source event pool")

    df = pd.DataFrame(work)
    x = df[FEATURES].to_numpy(dtype=np.float32)
    y = df["y"].to_numpy(dtype=np.int64)
    rec = df["recording_id"].to_numpy(dtype=np.int64)

    tr_mask = np.array([int(r) in train_set for r in rec], dtype=bool)
    va_mask = np.array([int(r) in val_set for r in rec], dtype=bool)
    te_mask = np.array([int(r) in test_set for r in rec], dtype=bool)

    xtr, ytr = x[tr_mask], y[tr_mask]
    xva, yva = x[va_mask], y[va_mask]
    xte, yte = x[te_mask], y[te_mask]
    if len(xtr) == 0 or len(xva) == 0 or len(xte) == 0:
        raise RuntimeError("empty split in source bridge training")
    if len(np.unique(ytr)) < 2 or len(np.unique(yva)) < 2 or len(np.unique(yte)) < 2:
        raise RuntimeError("split needs both lane/rear classes")

    clf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=1.0, class_weight="balanced", solver="liblinear", max_iter=3000, random_state=int(lr_random_seed))),
        ]
    )
    clf.fit(xtr, ytr)

    p_tr = clf.predict_proba(xtr)[:, 1]
    p_va = clf.predict_proba(xva)[:, 1]
    p_te = clf.predict_proba(xte)[:, 1]

    def auc(y_true: np.ndarray, p: np.ndarray) -> float:
        if len(np.unique(y_true)) < 2:
            return 0.0
        return float(roc_auc_score(y_true, p))

    stats = {
        "n_train": int(len(xtr)),
        "n_val": int(len(xva)),
        "n_test": int(len(xte)),
        "auc_train": round(auc(ytr, p_tr), 6),
        "auc_val": round(auc(yva, p_va), 6),
        "auc_test": round(auc(yte, p_te), 6),
        "lr_random_seed": int(lr_random_seed),
        "features": FEATURES,
    }
    return clf, stats


def compute_metrics(rows: List[Dict[str, Any]], use_patch_pred: bool) -> Dict[str, float]:
    cls = ["rear_end", "lane_change", "turn_conflict"]
    y_true = [str(r["gt_type"]).strip() for r in rows]
    y_pred = [str(r["pred_type_patch"] if use_patch_pred else r["pred_type"]).strip() for r in rows]
    n = len(y_true)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0
    f1s = []
    per: Dict[str, Dict[str, float]] = {}
    for c in cls:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        pr = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * pr * rc / (pr + rc) if (pr + rc) else 0.0
        per[c] = {"precision": pr, "recall": rc, "f1": f1}
        f1s.append(f1)
    return {
        "accuracy": float(acc),
        "macro_f1": float(sum(f1s) / len(f1s)) if f1s else 0.0,
        "rear_recall": float(per["rear_end"]["recall"]),
        "lane_recall": float(per["lane_change"]["recall"]),
        "turn_recall": float(per["turn_conflict"]["recall"]),
    }


def eval_board(rows: List[Dict[str, Any]], rescue_thr: float, lane_thr: float) -> Dict[str, Any]:
    lane_fn_rear = [r for r in rows if r["gt_type"] == "lane_change" and r["pred_type"] == "rear_end"]
    rear_gt = [r for r in rows if r["gt_type"] == "rear_end"]
    day_straight_lane_fn_rear = [r for r in lane_fn_rear if scene_bucket(r["scene_tags"]) == "day+straight_road"]

    rescueable = [r for r in lane_fn_rear if r["lane_score"] >= rescue_thr]
    day_straight_rescueable = [r for r in day_straight_lane_fn_rear if r["lane_score"] >= rescue_thr]
    day_straight_lane_over_rear = [r for r in day_straight_lane_fn_rear if r["lane_score"] > r["rear_score"]]

    changed = sum(1 for r in rows if r["pred_type_patch"] != r["pred_type"])
    # strict rear stealing: only samples that were rear before patch and got rewritten away.
    rear_steal = sum(
        1
        for r in rear_gt
        if str(r["pred_type"]).strip() == "rear_end" and str(r["pred_type_patch"]).strip() != "rear_end"
    )
    rear_already_nonrear_before = sum(
        1
        for r in rear_gt
        if str(r["pred_type"]).strip() != "rear_end"
    )
    rear_steal_ratio = (rear_steal / len(rear_gt)) if rear_gt else 0.0

    base_m = compute_metrics(rows, use_patch_pred=False)
    patch_m = compute_metrics(rows, use_patch_pred=True)

    return {
        "n": int(len(rows)),
        "lane_fn_rear_n": int(len(lane_fn_rear)),
        "rear_gt_n": int(len(rear_gt)),
        "rescueable_n": int(len(rescueable)),
        "rescueable_ratio": float((len(rescueable) / len(lane_fn_rear)) if lane_fn_rear else 0.0),
        "day_straight_lane_fn_rear_n": int(len(day_straight_lane_fn_rear)),
        "day_straight_rescueable_n": int(len(day_straight_rescueable)),
        "day_straight_lane_over_rear_n": int(len(day_straight_lane_over_rear)),
        "changed_n": int(changed),
        "rear_steal_n": int(rear_steal),
        "rear_already_nonrear_before_n": int(rear_already_nonrear_before),
        "rear_steal_ratio": float(rear_steal_ratio),
        "base_metrics": base_m,
        "patch_metrics": patch_m,
        "delta_metrics": {
            "accuracy": patch_m["accuracy"] - base_m["accuracy"],
            "macro_f1": patch_m["macro_f1"] - base_m["macro_f1"],
            "rear_recall": patch_m["rear_recall"] - base_m["rear_recall"],
            "lane_recall": patch_m["lane_recall"] - base_m["lane_recall"],
            "turn_recall": patch_m["turn_recall"] - base_m["turn_recall"],
        },
        "lane_thr": float(lane_thr),
        "rescue_thr": float(rescue_thr),
    }


def run_one_board(board_rows: List[Dict[str, Any]], clf: Pipeline, rescue_thr: float, lane_thr: float) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    work: List[Dict[str, Any]] = []
    x_rows: List[List[float]] = []
    for r in board_rows:
        feat = board_row_to_features(r)
        x_rows.append([feat[k] for k in FEATURES])
        gt = str(r.get("accident_type", "")).strip()
        pred = str(r.get("pred_type_key", "")).strip()
        tags = parse_scene_tags(r.get("scene_tags", []))
        work.append(
            {
                "sample_id": str(r.get("sample_id", "")).strip(),
                "video": str(r.get("video", "")).strip(),
                "gt_type": gt,
                "pred_type": pred,
                "scene_tags": tags,
            }
        )
    x = np.array(x_rows, dtype=np.float32)
    lane_prob = clf.predict_proba(x)[:, 1]

    scored: List[Dict[str, Any]] = []
    for b, p in zip(work, lane_prob):
        lane_s = clip01(float(p))
        rear_s = 1.0 - lane_s
        pred_patch = b["pred_type"]
        if b["pred_type"] in {"rear_end", "lane_change"} and lane_s >= lane_thr and lane_s > rear_s:
            pred_patch = "lane_change"
        rr = dict(b)
        rr["lane_score"] = round(lane_s, 6)
        rr["rear_score"] = round(rear_s, 6)
        rr["pred_type_patch"] = pred_patch
        scored.append(rr)

    stats = eval_board(scored, rescue_thr=rescue_thr, lane_thr=lane_thr)
    return scored, stats


def aggregate(boards: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    bvals = list(boards.values())
    rescueable_total = int(sum(b["rescueable_n"] for b in bvals))
    changed_total = int(sum(b["changed_n"] for b in bvals))
    rear_gt_total = int(sum(b["rear_gt_n"] for b in bvals))
    rear_steal_total = int(sum(b["rear_steal_n"] for b in bvals))
    rear_steal_ratio_total = (rear_steal_total / rear_gt_total) if rear_gt_total else 0.0
    day_straight_lane_over_rear_total = int(sum(b["day_straight_lane_over_rear_n"] for b in bvals))
    day_straight_rescueable_total = int(sum(b["day_straight_rescueable_n"] for b in bvals))

    return {
        "rescueable_total": rescueable_total,
        "changed_total": changed_total,
        "rear_gt_total": rear_gt_total,
        "rear_steal_total": rear_steal_total,
        "rear_steal_ratio_total": float(rear_steal_ratio_total),
        "day_straight_lane_over_rear_total": day_straight_lane_over_rear_total,
        "day_straight_rescueable_total": day_straight_rescueable_total,
        "delta_macro_f1_mean": float(mean([b["delta_metrics"]["macro_f1"] for b in bvals])) if bvals else 0.0,
        "delta_lane_recall_mean": float(mean([b["delta_metrics"]["lane_recall"] for b in bvals])) if bvals else 0.0,
        "delta_rear_recall_mean": float(mean([b["delta_metrics"]["rear_recall"] for b in bvals])) if bvals else 0.0,
    }


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Step4 minimal readonly bridge revalidation on new direct-shared features.")
    parser.add_argument("--source-name", required=True, help="highD / exiD")
    parser.add_argument("--source-learnability-report", required=True)
    parser.add_argument("--board-152", required=True)
    parser.add_argument("--board-30", required=True)
    parser.add_argument("--board-24", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--rescue-thr", type=float, default=0.56)
    parser.add_argument("--lane-thr", type=float, default=0.58)
    parser.add_argument("--lr-random-seed", type=int, default=42)
    parser.add_argument(
        "--board-order",
        default="board152,board30,board24",
        help="Permutation of board152,board30,board24",
    )
    parser.add_argument(
        "--scored-tag",
        default="",
        help="Optional suffix tag for scored jsonl outputs, e.g. seed73_order3024152",
    )
    args = parser.parse_args()

    rep = load_json(Path(args.source_learnability_report).resolve())
    pool_path = Path(str(rep.get("event_pool", "")).strip()).resolve()
    if not pool_path.exists():
        raise FileNotFoundError(f"event_pool not found from learnability report: {pool_path}")

    split = rep.get("split", {}) or {}
    train_recs = list(split.get("train_recordings", []))
    val_recs = list(split.get("val_recordings", []))
    test_recs = list(split.get("test_recordings", []))
    if not train_recs or not val_recs or not test_recs:
        raise RuntimeError("split train/val/test recordings missing in learnability report")

    source_rows = load_jsonl(pool_path)
    clf, bridge_stats = train_lane_rear_bridge(
        source_rows=source_rows,
        train_recs=train_recs,
        val_recs=val_recs,
        test_recs=test_recs,
        lr_random_seed=int(args.lr_random_seed),
    )

    rows_152 = load_jsonl(Path(args.board_152).resolve())
    rows_30 = load_jsonl(Path(args.board_30).resolve())
    rows_24 = load_jsonl(Path(args.board_24).resolve())
    order = [x.strip() for x in str(args.board_order).split(",") if x.strip()]
    allowed = {"board152", "board30", "board24"}
    if set(order) != allowed or len(order) != 3:
        raise ValueError(f"--board-order must be permutation of board152,board30,board24. got={order}")

    board_data = {
        "board152": rows_152,
        "board30": rows_30,
        "board24": rows_24,
    }
    scored_map: Dict[str, List[Dict[str, Any]]] = {}
    stats_map: Dict[str, Dict[str, Any]] = {}
    for b in order:
        scored_b, stats_b = run_one_board(
            board_data[b],
            clf,
            rescue_thr=float(args.rescue_thr),
            lane_thr=float(args.lane_thr),
        )
        scored_map[b] = scored_b
        stats_map[b] = stats_b

    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    tag = str(args.scored_tag).strip()
    suf = f".{tag}" if tag else ""

    write_jsonl(out_json.parent / f"{args.source_name}_board152.step4_scored{suf}.jsonl", scored_map["board152"])
    write_jsonl(out_json.parent / f"{args.source_name}_board30.step4_scored{suf}.jsonl", scored_map["board30"])
    write_jsonl(out_json.parent / f"{args.source_name}_board24.step4_scored{suf}.jsonl", scored_map["board24"])

    by_board = {
        "board152": stats_map["board152"],
        "board30": stats_map["board30"],
        "board24": stats_map["board24"],
    }
    ag = aggregate(by_board)
    report = {
        "mode": "step4_min_readonly_revalidation",
        "source_name": str(args.source_name),
        "source_event_pool": str(pool_path),
        "source_learnability_report": str(Path(args.source_learnability_report).resolve()),
        "bridge_train_stats": bridge_stats,
        "config": {
            "rescue_thr": float(args.rescue_thr),
            "lane_thr": float(args.lane_thr),
            "lr_random_seed": int(args.lr_random_seed),
            "board_order": order,
            "scored_tag": tag,
            "features": FEATURES,
        },
        "by_board": by_board,
        "aggregate": ag,
        "step4_core_checks": {
            "rescueable_total_gt_0": bool(ag["rescueable_total"] > 0),
            "changed_total_gt_0": bool(ag["changed_total"] > 0),
            "rear_steal_ratio_controlled_lt_10pct": bool(ag["rear_steal_ratio_total"] < 0.10),
            "day_straight_lane_score_over_rear_nonzero": bool(ag["day_straight_lane_over_rear_total"] > 0),
        },
    }

    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append(f"# Step4 Minimal Readonly Revalidation ({args.source_name})")
    lines.append("")
    lines.append("## Core Checks")
    for k, v in report["step4_core_checks"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Aggregate")
    lines.append(f"- rescueable_total: {ag['rescueable_total']}")
    lines.append(f"- changed_total: {ag['changed_total']}")
    lines.append(f"- rear_steal_ratio_total: {ag['rear_steal_ratio_total']:.6f}")
    lines.append(f"- day_straight_lane_over_rear_total: {ag['day_straight_lane_over_rear_total']}")
    lines.append(f"- day_straight_rescueable_total: {ag['day_straight_rescueable_total']}")
    lines.append(f"- delta_macro_f1_mean: {ag['delta_macro_f1_mean']:+.6f}")
    lines.append(f"- delta_lane_recall_mean: {ag['delta_lane_recall_mean']:+.6f}")
    lines.append(f"- delta_rear_recall_mean: {ag['delta_rear_recall_mean']:+.6f}")
    lines.append("")
    lines.append("## By Board")
    for b in ["board152", "board30", "board24"]:
        s = by_board[b]
        lines.append(f"- {b}: rescueable={s['rescueable_n']}, changed={s['changed_n']}, rear_steal_ratio={s['rear_steal_ratio']:.6f}, day_straight_lane_over_rear={s['day_straight_lane_over_rear_n']}")
    lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "out_json": str(out_json),
                "out_md": str(out_md),
                "aggregate": ag,
                "step4_core_checks": report["step4_core_checks"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
