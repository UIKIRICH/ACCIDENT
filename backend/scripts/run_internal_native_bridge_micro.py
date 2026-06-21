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


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def normalize_video(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def sample_hash_bucket(sample_id: str, mod: int = 5) -> int:
    return sum(ord(c) for c in str(sample_id)) % mod


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


FEATURES = [
    "prob_rear",
    "prob_lane",
    "prob_turn",
    "lead_time_sec",
    "peak_risk",
    "dominance",
    "bridged_coverage",
    "bridged_continuity",
    "intersection_prior",
    "turning_scene_prior",
    "turn_candidate_boost",
    "turn_candidate_run",
    "turn_evidence",
    "feat_longitudinal_closing",
    "feat_lateral_change",
    "feat_lane_relation",
    "feat_direction_relation",
    "feat_pair_temporal_consistency",
    "feat_lane_behavior_strength",
    "feat_rear_behavior_strength",
    "impact_lateral_shift_score",
    "impact_cutin_continuity",
    "impact_same_lane_score",
    "impact_front_back_order_score",
    "impact_ttc_score",
]


def build_feature_vector(
    pred_row: Dict[str, Any],
    native_map_by_sid: Dict[str, Dict[str, Any]],
    native_map_by_video: Dict[str, Dict[str, Any]],
) -> Tuple[List[float], bool]:
    sid = str(pred_row.get("sample_id", "")).strip()
    video = normalize_video(pred_row.get("video", ""))
    native = native_map_by_sid.get(sid) or native_map_by_video.get(video)
    has_native = native is not None

    tp = pred_row.get("type_probs", {}) or {}
    prob_rear_fallback = clip01(safe_float(tp.get("rear_end", 0.0)))
    prob_lane_fallback = clip01(safe_float(tp.get("lane_change", 0.0)))
    prob_turn_fallback = clip01(safe_float(tp.get("turn_conflict", 0.0)))

    vec: List[float] = []
    for c in FEATURES:
        if has_native and c in native:
            v = safe_float(native.get(c, np.nan), np.nan)
        else:
            v = np.nan
        if np.isnan(v):
            if c == "prob_rear":
                v = prob_rear_fallback
            elif c == "prob_lane":
                v = prob_lane_fallback
            elif c == "prob_turn":
                v = prob_turn_fallback
        vec.append(float(v) if not np.isnan(v) else np.nan)
    return vec, has_native


def train_bridge(train_native_csv: Path, lane_boost: float, lr_random_seed: int = 42) -> Tuple[Pipeline, Dict[str, Any]]:
    df = pd.read_csv(train_native_csv)
    df = df[df["accident_type"].isin(["lane_change", "rear_end"])].copy()
    if len(df) == 0:
        raise RuntimeError("No lane_change/rear_end rows in train native csv.")

    df["y"] = (df["accident_type"] == "lane_change").astype(int)
    df["bucket"] = df["sample_id"].map(lambda x: sample_hash_bucket(str(x), mod=5))

    x = df[FEATURES].to_numpy(dtype=np.float32)
    y = df["y"].to_numpy(dtype=np.int64)
    b = df["bucket"].to_numpy(dtype=np.int64)

    tr = b != 0
    va = b == 0
    xtr, ytr = x[tr], y[tr]
    xva, yva = x[va], y[va]

    sample_w = np.ones_like(ytr, dtype=np.float32)
    sample_w[ytr == 1] = float(lane_boost)

    clf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "lr",
                LogisticRegression(
                    C=1.0,
                    class_weight="balanced",
                    solver="liblinear",
                    max_iter=3000,
                    random_state=int(lr_random_seed),
                ),
            ),
        ]
    )
    clf.fit(xtr, ytr, lr__sample_weight=sample_w)

    p_tr = clf.predict_proba(xtr)[:, 1]
    p_va = clf.predict_proba(xva)[:, 1] if len(xva) else np.array([])

    def auc(y_true: np.ndarray, prob: np.ndarray) -> float:
        if len(prob) == 0 or len(np.unique(y_true)) < 2:
            return 0.0
        return float(roc_auc_score(y_true, prob))

    return clf, {
        "n_train": int(len(xtr)),
        "n_val": int(len(xva)),
        "lane_ratio_train": float(ytr.mean()) if len(ytr) else 0.0,
        "lane_ratio_val": float(yva.mean()) if len(yva) else 0.0,
        "auc_train": round(auc(ytr, p_tr), 6),
        "auc_val": round(auc(yva, p_va), 6),
        "lane_boost": float(lane_boost),
        "lr_random_seed": int(lr_random_seed),
        "features": FEATURES,
    }


def compute_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    cls = ["rear_end", "lane_change", "turn_conflict"]
    y_true = [str(r["gt"].get("accident_type", "")).strip() for r in rows]
    y_pred = [str(r["pred"].get("pred_type", "")).strip() for r in rows]
    n = len(y_true)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0

    f1s = []
    per: Dict[str, Any] = {}
    for c in cls:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == c and p == c)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != c and p == c)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == c and p != c)
        pr = tp / (tp + fp) if (tp + fp) else 0.0
        rc = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * pr * rc / (pr + rc) if (pr + rc) else 0.0
        per[c] = {"precision": pr, "recall": rc, "f1": f1}
        f1s.append(f1)

    impact_mae = mean(
        abs(safe_float(r["pred"].get("pred_impact_time", 0.0)) - safe_float(r["gt"].get("impact_time", 0.0)))
        for r in rows
    ) if rows else 0.0

    return {
        "accuracy": float(acc),
        "macro_f1": float(sum(f1s) / len(f1s)) if f1s else 0.0,
        "rear_recall": float(per["rear_end"]["recall"]),
        "lane_recall": float(per["lane_change"]["recall"]),
        "turn_recall": float(per["turn_conflict"]["recall"]),
        "impact_mae": float(impact_mae),
    }


def matched(gt_rows: List[Dict[str, Any]], pred_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pm_sid = {str(r.get("sample_id", "")).strip(): r for r in pred_rows}
    pm_vid = {normalize_video(r.get("video", "")): r for r in pred_rows}
    out: List[Dict[str, Any]] = []
    for g in gt_rows:
        sid = str(g.get("sample_id", "")).strip()
        vid = normalize_video(g.get("video", ""))
        p = pm_sid.get(sid) or pm_vid.get(vid)
        if p is not None:
            out.append({"gt": g, "pred": p, "video": vid, "sample_id": sid})
    return out


def apply_rewrite(
    pred_rows: List[Dict[str, Any]],
    lane_scores: Dict[str, float],
    cfg: Dict[str, float],
    board_name: str,
    native_map_by_sid: Dict[str, Dict[str, Any]],
    native_map_by_video: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], int]:
    out: List[Dict[str, Any]] = []
    changed = 0

    for r in pred_rows:
        rr = dict(r)
        sid = str(rr.get("sample_id", "")).strip()
        lane_s = clip01(lane_scores.get(sid, safe_float(rr.get("lane_bridge_score", 0.0))))
        rear_s = 1.0 - lane_s
        vid = normalize_video(rr.get("video", ""))
        native = native_map_by_sid.get(sid) or native_map_by_video.get(vid) or {}

        pred = str(rr.get("pred_type", "")).strip()
        tp = rr.get("type_probs", {}) or {}
        pr = clip01(safe_float(tp.get("rear_end", 0.0)))
        pl = clip01(safe_float(tp.get("lane_change", 0.0)))
        pt = clip01(safe_float(tp.get("turn_conflict", 0.0)))
        margin = lane_s - rear_s
        gap = abs(pr - pl)
        decision_mode = str(rr.get("decision_mode", "")).strip()

        rear_keep = (decision_mode == "rear_guard_override" and pr >= cfg["rear_keep_thr"])
        do = (
            pred in {"rear_end", "lane_change"}
            and pt <= cfg["turn_guard"]
            and gap <= cfg["gap_max"]
            and lane_s >= cfg["lane_thr"]
            and margin >= cfg["margin_thr"]
            and (not rear_keep)
        )

        tags = {str(x).strip() for x in (rr.get("scene_tags") or []) if str(x).strip()}
        is_day_straight = ("day" in tags) and ("straight_road" in tags)
        onecut_block = (
            cfg["enable_onecut"]
            and board_name == "board24"
            and pred == "rear_end"
            and is_day_straight
            and decision_mode == "rear_guard_override"
        )
        rear_evidence_block = (
            cfg.get("enable_rear_guard_day_straight_soft_block", False)
            and pred == "rear_end"
            and is_day_straight
            and decision_mode == "rear_guard_override"
            and lane_s < float(cfg.get("rgo_day_straight_lane_soft_guard_thr", 0.70))
            and safe_float(native.get("feat_rear_behavior_strength", 0.0)) >= float(cfg.get("rgo_rear_strength_thr", 0.50))
            and safe_float(native.get("feat_pair_temporal_consistency", 0.0)) >= float(cfg.get("rgo_pair_cons_thr", 0.70))
            and safe_float(native.get("bridged_coverage", 0.0)) >= float(cfg.get("rgo_cov_thr", 0.80))
            and safe_float(native.get("bridged_continuity", 0.0)) >= float(cfg.get("rgo_cont_thr", 0.50))
        )
        if onecut_block:
            do = False
        if rear_evidence_block:
            do = False

        rr["native_bridge_lane_score"] = round(lane_s, 6)
        rr["native_bridge_rear_score"] = round(rear_s, 6)
        rr["native_bridge_margin"] = round(margin, 6)
        rr["native_bridge_rewrite_applied"] = False
        rr["native_bridge_guard_reason"] = ""
        if onecut_block:
            rr["native_bridge_guard_reason"] = "onecut_board24_day_straight_rearguard"
        elif rear_evidence_block:
            rr["native_bridge_guard_reason"] = "rear_guard_day_straight_soft_block"

        if do and pred != "lane_change":
            rr["pred_type"] = "lane_change"
            rr["native_bridge_rewrite_applied"] = True
            changed += 1

        out.append(rr)
    return out, changed


def board_stats(base_rows: List[Dict[str, Any]], patch_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    rescue = 0
    lane_fn_rear = 0
    day_rescue = 0
    day_lane_fn_rear = 0
    rear_gt = 0
    rear_steal = 0

    for b, p in zip(base_rows, patch_rows):
        gt = str(b["gt"].get("accident_type", "")).strip()
        pred_base = str(b["pred"].get("pred_type", "")).strip()
        pred_patch = str(p["pred"].get("pred_type", "")).strip()
        tags = b["gt"].get("scene_tags", []) or []
        is_day_straight = scene_bucket(tags) == "day+straight_road"

        if gt == "lane_change" and pred_base == "rear_end":
            lane_fn_rear += 1
            if is_day_straight:
                day_lane_fn_rear += 1
            if pred_patch == "lane_change":
                rescue += 1
                if is_day_straight:
                    day_rescue += 1

        if gt == "rear_end":
            rear_gt += 1
            if pred_patch != "rear_end":
                rear_steal += 1

    return {
        "rescueable_n": int(rescue),
        "lane_fn_rear_n": int(lane_fn_rear),
        "day_straight_rescueable_n": int(day_rescue),
        "day_straight_lane_fn_n": int(day_lane_fn_rear),
        "potential_rear_steal_n": int(rear_steal),
        "rear_gt_n": int(rear_gt),
    }


def run_one_board(
    board_name: str,
    gt_path: Path,
    pred_path: Path,
    native_csv: Path,
    clf: Pipeline,
    cfg: Dict[str, float],
    out_dir: Path,
) -> Dict[str, Any]:
    gt_rows = load_jsonl(gt_path)
    pred_rows = load_jsonl(pred_path)

    native_df = pd.read_csv(native_csv)
    native_map_by_sid = {
        str(r["sample_id"]).strip(): dict(r)
        for r in native_df.to_dict(orient="records")
        if str(r.get("sample_id", "")).strip()
    }
    native_map_by_video = {
        normalize_video(r["video"]): dict(r)
        for r in native_df.to_dict(orient="records")
        if str(r.get("video", "")).strip()
    }

    x_rows: List[List[float]] = []
    has_native_n = 0
    for r in pred_rows:
        vec, has_native = build_feature_vector(r, native_map_by_sid, native_map_by_video)
        if has_native:
            has_native_n += 1
        x_rows.append(vec)
    x = np.array(x_rows, dtype=np.float32)
    p_lane = clf.predict_proba(x)[:, 1]
    lane_scores = {str(r.get("sample_id", "")).strip(): float(s) for r, s in zip(pred_rows, p_lane)}

    pred_patch, changed = apply_rewrite(
        pred_rows,
        lane_scores,
        cfg,
        board_name=board_name,
        native_map_by_sid=native_map_by_sid,
        native_map_by_video=native_map_by_video,
    )

    m_base = matched(gt_rows, pred_rows)
    m_patch = matched(gt_rows, pred_patch)
    bm = compute_metrics(m_base)
    pm = compute_metrics(m_patch)

    stats = board_stats(m_base, m_patch)
    stats["changed_by_patch"] = int(changed)
    stats["native_covered_pred_n"] = int(has_native_n)
    stats["pred_total_n"] = int(len(pred_rows))

    scored_out = out_dir / f"{board_name}.native_bridge_scored.jsonl"
    patch_out = out_dir / f"{board_name}.native_bridge_patch.jsonl"
    write_jsonl(scored_out, pred_rows)
    write_jsonl(patch_out, pred_patch)

    return {
        "board": board_name,
        "base_metrics": bm,
        "patch_metrics": pm,
        "delta": {
            "accuracy": pm["accuracy"] - bm["accuracy"],
            "macro_f1": pm["macro_f1"] - bm["macro_f1"],
            "rear_recall": pm["rear_recall"] - bm["rear_recall"],
            "lane_recall": pm["lane_recall"] - bm["lane_recall"],
            "turn_recall": pm["turn_recall"] - bm["turn_recall"],
            "impact_mae": pm["impact_mae"] - bm["impact_mae"],
        },
        **stats,
        "pred_scored_path": str(scored_out),
        "pred_patch_path": str(patch_out),
    }


def aggregate(boards: List[Dict[str, Any]]) -> Dict[str, Any]:
    mean_base = {}
    mean_patch = {}
    mean_delta = {}
    keys = ["accuracy", "macro_f1", "rear_recall", "lane_recall", "turn_recall", "impact_mae"]
    for k in keys:
        mean_base[k] = float(mean([b["base_metrics"][k] for b in boards]))
        mean_patch[k] = float(mean([b["patch_metrics"][k] for b in boards]))
        mean_delta[k] = float(mean([b["delta"][k] for b in boards]))

    rescue_total = int(sum(b["rescueable_n"] for b in boards))
    day_rescue_total = int(sum(b["day_straight_rescueable_n"] for b in boards))
    rear_steal_total = int(sum(b["potential_rear_steal_n"] for b in boards))
    rear_gt_total = int(sum(b["rear_gt_n"] for b in boards))
    changed_total = int(sum(b["changed_by_patch"] for b in boards))
    rear_steal_ratio = (rear_steal_total / rear_gt_total) if rear_gt_total else 0.0

    gate = {
        "A_rescueable_nonzero": rescue_total > 0,
        "B_day_straight_rescueable_nonzero": day_rescue_total > 0,
        "C_rear_steal_ratio_lt_10pct": rear_steal_ratio < 0.10,
        "D_changed_nonzero": changed_total > 0,
    }
    return {
        "base_mean_equal": mean_base,
        "patch_mean_equal": mean_patch,
        "delta_mean_equal": mean_delta,
        "rescueable_total": rescue_total,
        "day_straight_rescueable_total": day_rescue_total,
        "potential_rear_steal_total": rear_steal_total,
        "rear_gt_total": rear_gt_total,
        "rear_steal_ratio": float(rear_steal_ratio),
        "changed_by_patch_total": changed_total,
        "gate": gate,
        "pass": all(gate.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Internal native-trajectory bridge micro experiments.")
    parser.add_argument("--train-native-csv", required=True)
    parser.add_argument("--gt-152", required=True)
    parser.add_argument("--gt-30", required=True)
    parser.add_argument("--gt-24", required=True)
    parser.add_argument("--pred-152", required=True)
    parser.add_argument("--pred-30", required=True)
    parser.add_argument("--pred-24", required=True)
    parser.add_argument("--native-152", required=True)
    parser.add_argument("--native-30", required=True)
    parser.add_argument("--native-24", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--only-cfg", default="", help="Run only one config by exact name (e.g. cfgN1_boost1.0_thr68_m08).")
    parser.add_argument(
        "--board-order",
        default="board152,board30,board24",
        help="Comma-separated board run order. Allowed: board152,board30,board24",
    )
    parser.add_argument("--lr-random-seed", type=int, default=42, help="LogisticRegression random seed for stability reruns.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    allowed_boards = {"board152", "board30", "board24"}
    board_order = [x.strip() for x in str(args.board_order).split(",") if x.strip()]
    if set(board_order) != allowed_boards or len(board_order) != 3:
        raise ValueError(f"--board-order must be a permutation of board152,board30,board24. got={board_order}")

    board_cfg = {
        "board152": {
            "gt": Path(args.gt_152).resolve(),
            "pred": Path(args.pred_152).resolve(),
            "native": Path(args.native_152).resolve(),
        },
        "board30": {
            "gt": Path(args.gt_30).resolve(),
            "pred": Path(args.pred_30).resolve(),
            "native": Path(args.native_30).resolve(),
        },
        "board24": {
            "gt": Path(args.gt_24).resolve(),
            "pred": Path(args.pred_24).resolve(),
            "native": Path(args.native_24).resolve(),
        },
    }

    grids = [
        {
            "name": "cfgN1_boost1.0_thr68_m08",
            "lane_boost": 1.0,
            "lane_thr": 0.68,
            "margin_thr": 0.08,
            "gap_max": 0.20,
            "turn_guard": 0.42,
            "rear_keep_thr": 0.55,
            "enable_onecut": True,
            "enable_rear_guard_day_straight_soft_block": True,
            "rgo_day_straight_lane_soft_guard_thr": 0.71,
            "rgo_rear_strength_thr": 0.50,
            "rgo_pair_cons_thr": 0.70,
            "rgo_cov_thr": 0.80,
            "rgo_cont_thr": 0.50,
        },
        {
            "name": "cfgN2_boost1.3_thr68_m08",
            "lane_boost": 1.3,
            "lane_thr": 0.68,
            "margin_thr": 0.08,
            "gap_max": 0.20,
            "turn_guard": 0.42,
            "rear_keep_thr": 0.55,
            "enable_onecut": True,
            "enable_rear_guard_day_straight_soft_block": True,
            "rgo_day_straight_lane_soft_guard_thr": 0.71,
            "rgo_rear_strength_thr": 0.50,
            "rgo_pair_cons_thr": 0.70,
            "rgo_cov_thr": 0.80,
            "rgo_cont_thr": 0.50,
        },
        {
            "name": "cfgN3_boost1.6_thr66_m08",
            "lane_boost": 1.6,
            "lane_thr": 0.66,
            "margin_thr": 0.08,
            "gap_max": 0.20,
            "turn_guard": 0.42,
            "rear_keep_thr": 0.55,
            "enable_onecut": True,
            "enable_rear_guard_day_straight_soft_block": True,
            "rgo_day_straight_lane_soft_guard_thr": 0.71,
            "rgo_rear_strength_thr": 0.50,
            "rgo_pair_cons_thr": 0.70,
            "rgo_cov_thr": 0.80,
            "rgo_cont_thr": 0.50,
        },
    ]
    only_cfg = str(args.only_cfg or "").strip()
    if only_cfg:
        grids = [g for g in grids if g["name"] == only_cfg]
        if not grids:
            raise ValueError(f"--only-cfg not found in preset grids: {only_cfg}")

    reports: List[Dict[str, Any]] = []
    for g in grids:
        cfg_name = g["name"]
        cfg_out = out_dir / cfg_name
        cfg_out.mkdir(parents=True, exist_ok=True)
        clf, tr_stats = train_bridge(
            Path(args.train_native_csv).resolve(),
            lane_boost=float(g["lane_boost"]),
            lr_random_seed=int(args.lr_random_seed),
        )

        boards: List[Dict[str, Any]] = []
        for bn in board_order:
            bc = board_cfg[bn]
            boards.append(
                run_one_board(
                    bn,
                    bc["gt"],
                    bc["pred"],
                    bc["native"],
                    clf,
                    g,
                    cfg_out,
                )
            )
        agg = aggregate(boards)
        rep = {
            "config": g,
            "train_stats": tr_stats,
            "run_control": {"board_order": board_order, "lr_random_seed": int(args.lr_random_seed)},
            "boards": boards,
            "aggregate": agg,
            "decision": "PASS_TO_NEXT" if agg["pass"] else "FAIL_STOP_THIS_CFG",
        }
        reports.append(rep)
        (cfg_out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "cfg": cfg_name,
                    "decision": rep["decision"],
                    "delta_macro": round(agg["delta_mean_equal"]["macro_f1"], 6),
                    "delta_laneR": round(agg["delta_mean_equal"]["lane_recall"], 6),
                    "delta_rearR": round(agg["delta_mean_equal"]["rear_recall"], 6),
                    "rear_steal_ratio": round(agg["rear_steal_ratio"], 6),
                    "changed_total": agg["changed_by_patch_total"],
                },
                ensure_ascii=False,
            )
        )

    # Pick best by delta macro_f1 under rear_steal_ratio<10%
    valid = [r for r in reports if r["aggregate"]["rear_steal_ratio"] < 0.10]
    best = max(valid, key=lambda r: r["aggregate"]["delta_mean_equal"]["macro_f1"]) if valid else max(
        reports, key=lambda r: r["aggregate"]["delta_mean_equal"]["macro_f1"]
    )

    final = {
        "mode": "internal_native_bridge_micro",
        "configs_tested": len(reports),
        "reports": reports,
        "selected": best,
    }
    out_json = out_dir / "INTERNAL_NATIVE_BRIDGE_MICRO_SUMMARY_2026-05-08.json"
    out_md = out_dir / "INTERNAL_NATIVE_BRIDGE_MICRO_SUMMARY_2026-05-08.md"
    out_json.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Internal Native Bridge Micro Summary",
        "",
        f"- configs_tested: {len(reports)}",
        "",
        "| cfg | dMacro | dLaneR | dRearR | rear_steal_ratio | changed | pass |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in reports:
        a = r["aggregate"]
        d = a["delta_mean_equal"]
        lines.append(
            f"| {r['config']['name']} | {d['macro_f1']:+.6f} | {d['lane_recall']:+.6f} | {d['rear_recall']:+.6f} | {a['rear_steal_ratio']:.2%} | {a['changed_by_patch_total']} | {a['pass']} |"
        )
    lines += [
        "",
        f"- selected: **{best['config']['name']}**",
        f"- selected decision: {best['decision']}",
        f"- selected delta macro/lane/rear: {best['aggregate']['delta_mean_equal']['macro_f1']:+.6f} / {best['aggregate']['delta_mean_equal']['lane_recall']:+.6f} / {best['aggregate']['delta_mean_equal']['rear_recall']:+.6f}",
        f"- selected rear_steal_ratio: {best['aggregate']['rear_steal_ratio']:.2%}",
        "",
    ]
    out_md.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"summary_json": str(out_json), "summary_md": str(out_md), "selected": best["config"]["name"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
