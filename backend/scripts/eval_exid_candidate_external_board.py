import argparse
import json
from pathlib import Path
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


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


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


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


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


def train_bridge(
    source_rows: List[Dict[str, Any]],
    train_recs: List[int],
    val_recs: List[int],
    test_recs: List[int],
    lr_random_seed: int,
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
        feat = source_row_to_features(r)
        feat["y"] = 1 if c == "lane_pos" else 0
        feat["recording_id"] = rec
        work.append(feat)
    if not work:
        raise RuntimeError("empty source lane/rear pool")

    df = pd.DataFrame(work)
    x = df[FEATURES].to_numpy(dtype=np.float32)
    y = df["y"].to_numpy(dtype=np.int64)
    rec = df["recording_id"].to_numpy(dtype=np.int64)

    tr = np.array([int(v) in train_set for v in rec], dtype=bool)
    va = np.array([int(v) in val_set for v in rec], dtype=bool)
    te = np.array([int(v) in test_set for v in rec], dtype=bool)
    xtr, ytr = x[tr], y[tr]
    xva, yva = x[va], y[va]
    xte, yte = x[te], y[te]
    if len(xtr) == 0 or len(xva) == 0 or len(xte) == 0:
        raise RuntimeError("empty split")
    if len(np.unique(ytr)) < 2 or len(np.unique(yva)) < 2 or len(np.unique(yte)) < 2:
        raise RuntimeError("split requires both classes")

    clf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=1.0, class_weight="balanced", solver="liblinear", max_iter=3000, random_state=int(lr_random_seed))),
        ]
    )
    clf.fit(xtr, ytr)

    def auc(y_true: np.ndarray, p: np.ndarray) -> float:
        if len(np.unique(y_true)) < 2:
            return 0.0
        return float(roc_auc_score(y_true, p))

    p_tr = clf.predict_proba(xtr)[:, 1]
    p_va = clf.predict_proba(xva)[:, 1]
    p_te = clf.predict_proba(xte)[:, 1]
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


def compute_metrics(rows: List[Dict[str, Any]], key: str) -> Dict[str, float]:
    cls = ["rear_end", "lane_change", "turn_conflict"]
    y_true = [str(r["gt_type"]).strip() for r in rows]
    y_pred = [str(r[key]).strip() for r in rows]
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


def apply_candidate_patch(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rr = dict(r)
        pred = str(rr["pred_type"]).strip()
        lane_s = safe_float(rr["lane_score"], 0.0)
        rear_s = safe_float(rr["rear_score"], 0.0)
        margin = lane_s - rear_s
        bucket = scene_bucket(rr["scene_tags"])
        is_day_straight = bucket == "day+straight_road"

        prob_rear = safe_float(rr.get("prob_rear", 0.0), 0.0)
        rear_strength = safe_float(rr.get("feat_rear_behavior_strength", 0.0), 0.0)
        pair_cons = safe_float(rr.get("feat_pair_temporal_consistency", 0.0), 0.0)

        do_rewrite = False
        if pred in {"rear_end", "lane_change"}:
            do_rewrite = lane_s >= float(cfg["lane_thr"]) and margin >= float(cfg["margin_thr"])

        if do_rewrite and pred == "rear_end":
            if lane_s < float(cfg["lane_thr"]) + float(cfg["just_over_eps"]):
                do_rewrite = False

        if do_rewrite and pred == "rear_end" and is_day_straight:
            if prob_rear >= float(cfg["day_straight_rear_prob_keep_thr"]):
                do_rewrite = False

        if do_rewrite and pred == "rear_end" and bool(cfg["enable_rear_strength_block"]):
            if rear_strength >= float(cfg["rear_strength_thr"]) and pair_cons >= float(cfg["pair_cons_thr"]):
                do_rewrite = False

        rr["pred_type_patch"] = "lane_change" if do_rewrite else pred
        rr["rewrite_applied"] = bool(do_rewrite and pred != "lane_change")
        rr["scene_bucket"] = bucket
        out.append(rr)
    return out


def eval_external(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = compute_metrics(rows, "pred_type")
    patch = compute_metrics(rows, "pred_type_patch")
    lane_fn_rear = [r for r in rows if r["gt_type"] == "lane_change" and r["pred_type"] == "rear_end"]
    rear_gt = [r for r in rows if r["gt_type"] == "rear_end"]

    rescueable = [r for r in lane_fn_rear if r["pred_type_patch"] == "lane_change"]
    changed = [r for r in rows if r["pred_type_patch"] != r["pred_type"]]
    rear_steal = [
        r for r in rear_gt
        if str(r["pred_type"]).strip() == "rear_end" and str(r["pred_type_patch"]).strip() != "rear_end"
    ]
    rear_already_nonrear_before = [r for r in rear_gt if str(r["pred_type"]).strip() != "rear_end"]

    ds_lane_fn_rear = [r for r in lane_fn_rear if r["scene_bucket"] == "day+straight_road"]
    ds_rescue = [r for r in ds_lane_fn_rear if r["pred_type_patch"] == "lane_change"]
    ds_lane_over_rear = [r for r in ds_lane_fn_rear if safe_float(r["lane_score"], 0.0) > safe_float(r["rear_score"], 0.0)]

    return {
        "n": int(len(rows)),
        "lane_fn_rear_n": int(len(lane_fn_rear)),
        "rear_gt_n": int(len(rear_gt)),
        "rescueable_total": int(len(rescueable)),
        "changed_total": int(len(changed)),
        "rear_steal_total": int(len(rear_steal)),
        "rear_already_nonrear_before_n": int(len(rear_already_nonrear_before)),
        "rear_steal_ratio": float((len(rear_steal) / len(rear_gt)) if rear_gt else 0.0),
        "day_straight_lane_fn_rear_n": int(len(ds_lane_fn_rear)),
        "day_straight_rescueable_total": int(len(ds_rescue)),
        "day_straight_lane_over_rear_total": int(len(ds_lane_over_rear)),
        "base_metrics": base,
        "patch_metrics": patch,
        "delta_metrics": {
            "accuracy": patch["accuracy"] - base["accuracy"],
            "macro_f1": patch["macro_f1"] - base["macro_f1"],
            "rear_recall": patch["rear_recall"] - base["rear_recall"],
            "lane_recall": patch["lane_recall"] - base["lane_recall"],
            "turn_recall": patch["turn_recall"] - base["turn_recall"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate exiD_step4_v4_refine candidate on one independent external board.")
    parser.add_argument("--source-learnability-report", required=True)
    parser.add_argument("--external-board-native-jsonl", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--out-scored-jsonl", required=True)
    parser.add_argument("--lr-random-seed", type=int, default=42)
    parser.add_argument("--cfg-name", default="v4A_margin_up")
    parser.add_argument("--lane-thr", type=float, default=0.72)
    parser.add_argument("--margin-thr", type=float, default=0.46)
    parser.add_argument("--just-over-eps", type=float, default=0.06)
    parser.add_argument("--day-straight-rear-prob-keep-thr", type=float, default=0.60)
    parser.add_argument("--disable-rear-strength-block", action="store_true")
    parser.add_argument("--rear-strength-thr", type=float, default=0.45)
    parser.add_argument("--pair-cons-thr", type=float, default=0.65)
    args = parser.parse_args()

    rep = load_json(Path(args.source_learnability_report).resolve())
    source_pool = Path(str(rep.get("event_pool", "")).strip()).resolve()
    source_rows = load_jsonl(source_pool)
    split = rep.get("split", {}) or {}
    train_recs = list(split.get("train_recordings", []))
    val_recs = list(split.get("val_recordings", []))
    test_recs = list(split.get("test_recordings", []))

    clf, bridge_stats = train_bridge(
        source_rows,
        train_recs=train_recs,
        val_recs=val_recs,
        test_recs=test_recs,
        lr_random_seed=int(args.lr_random_seed),
    )

    ext_rows = load_jsonl(Path(args.external_board_native_jsonl).resolve())
    work: List[Dict[str, Any]] = []
    x_rows: List[List[float]] = []
    for r in ext_rows:
        feat = board_row_to_features(r)
        x_rows.append([feat[k] for k in FEATURES])
        work.append(
            {
                "sample_id": str(r.get("sample_id", "")).strip(),
                "video": str(r.get("video", "")).strip(),
                "gt_type": str(r.get("accident_type", "")).strip(),
                "pred_type": str(r.get("pred_type_key", "")).strip(),
                "scene_tags": parse_scene_tags(r.get("scene_tags", [])),
                "prob_rear": safe_float(r.get("prob_rear", 0.0), 0.0),
                "feat_rear_behavior_strength": safe_float(r.get("feat_rear_behavior_strength", 0.0), 0.0),
                "feat_pair_temporal_consistency": safe_float(r.get("feat_pair_temporal_consistency", 0.0), 0.0),
            }
        )
    x = np.array(x_rows, dtype=np.float32)
    lane_prob = clf.predict_proba(x)[:, 1]
    for rr, p in zip(work, lane_prob):
        lane_s = clip01(float(p))
        rr["lane_score"] = round(lane_s, 6)
        rr["rear_score"] = round(1.0 - lane_s, 6)

    # locked candidate v4A parameters
    cfg = {
        "name": str(args.cfg_name),
        "lane_thr": float(args.lane_thr),
        "margin_thr": float(args.margin_thr),
        "just_over_eps": float(args.just_over_eps),
        "day_straight_rear_prob_keep_thr": float(args.day_straight_rear_prob_keep_thr),
        "enable_rear_strength_block": not bool(args.disable_rear_strength_block),
        "rear_strength_thr": float(args.rear_strength_thr),
        "pair_cons_thr": float(args.pair_cons_thr),
    }
    patched = apply_candidate_patch(work, cfg)
    stats = eval_external(patched)

    checks = {
        "rear_steal_ratio_lt_10pct": stats["rear_steal_ratio"] < 0.10,
        "rescueable_total_gt_0": stats["rescueable_total"] > 0,
        "changed_total_gt_0": stats["changed_total"] > 0,
        "delta_macro_f1_non_negative": stats["delta_metrics"]["macro_f1"] >= 0.0,
    }
    report = {
        "mode": "exid_step4_v4_refine_external_board_reconfirm",
        "candidate": "exiD_step4_v4_refine_candidate",
        "external_board_n": len(patched),
        "source_learnability_report": str(Path(args.source_learnability_report).resolve()),
        "source_event_pool": str(source_pool),
        "bridge_train_stats": bridge_stats,
        "locked_constraint_config": cfg,
        "rear_steal_metric_definition": "strict_rewrite_only",
        "metrics": stats,
        "gates": checks,
        "overall_pass": bool(all(checks.values())),
        "decision": "PASS_EXTERNAL_RECONFIRM" if all(checks.values()) else "FAIL_EXTERNAL_RECONFIRM",
    }

    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()
    out_scored = Path(args.out_scored_jsonl).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_scored.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_jsonl(out_scored, patched)

    lines = [
        "# exiD_step4_v4_refine External Board Reconfirm",
        "",
        f"- external_board_n: {len(patched)}",
        f"- decision: {report['decision']}",
        "",
        "## Core Gates",
        f"- rear_steal_ratio < 10%: {checks['rear_steal_ratio_lt_10pct']} ({stats['rear_steal_ratio']:.6f})",
        f"- rescueable_total > 0: {checks['rescueable_total_gt_0']} ({stats['rescueable_total']})",
        f"- changed_total > 0: {checks['changed_total_gt_0']} ({stats['changed_total']})",
        f"- dMacro >= 0: {checks['delta_macro_f1_non_negative']} ({stats['delta_metrics']['macro_f1']:+.6f})",
        "",
        "## Deltas",
        f"- dMacro: {stats['delta_metrics']['macro_f1']:+.6f}",
        f"- dLaneR: {stats['delta_metrics']['lane_recall']:+.6f}",
        f"- dRearR: {stats['delta_metrics']['rear_recall']:+.6f}",
        "",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "out_json": str(out_json),
                "out_md": str(out_md),
                "out_scored_jsonl": str(out_scored),
                "decision": report["decision"],
                "overall_pass": report["overall_pass"],
                "gates": checks,
                "metrics": {
                    "rear_steal_ratio": stats["rear_steal_ratio"],
                    "rescueable_total": stats["rescueable_total"],
                    "changed_total": stats["changed_total"],
                    "dMacro": stats["delta_metrics"]["macro_f1"],
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
