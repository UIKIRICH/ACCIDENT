import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Set, Tuple

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


def parse_range(raw: str) -> List[int]:
    out: List[int] = []
    for token in str(raw).split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            a, b = token.split("-", 1)
            start = int(a.strip())
            end = int(b.strip())
            if end < start:
                raise ValueError(f"bad range: {token}")
            out.extend(list(range(start, end + 1)))
        else:
            out.append(int(token))
    out = sorted(set(out))
    if not out:
        raise ValueError(f"empty range: {raw}")
    return out


def highd_lane_evidence(r: Dict[str, Any]) -> float:
    lc = max(safe_float(r.get("numLaneChanges_meta", 0.0)), safe_float(r.get("lane_change_count_track", 0.0)))
    yv = safe_float(r.get("max_abs_y_velocity", 0.0))
    return clip01(0.7 * clip01(lc / 2.0) + 0.3 * clip01(yv / 1.2))


def highd_rear_evidence(r: Dict[str, Any]) -> float:
    ttc = safe_float(r.get("min_ttc_eff", 999.0), 999.0)
    thw = safe_float(r.get("min_thw_eff", 999.0), 999.0)
    dhw = safe_float(r.get("min_dhw_eff", 999.0), 999.0)
    ttc_term = clip01((3.0 - ttc) / 3.0) if ttc >= 0 else 0.0
    thw_term = clip01((2.0 - thw) / 2.0) if thw >= 0 else 0.0
    dhw_term = clip01((25.0 - dhw) / 25.0) if dhw >= 0 else 0.0
    return clip01(0.5 * ttc_term + 0.35 * thw_term + 0.15 * dhw_term)


def highd_shared_vec(r: Dict[str, Any]) -> List[float]:
    lane_ev = highd_lane_evidence(r)
    rear_ev = highd_rear_evidence(r)
    gap = abs(lane_ev - rear_ev)
    conf = max(lane_ev, rear_ev)
    sym_margin = lane_ev - rear_ev
    return [lane_ev, rear_ev, gap, conf, sym_margin]


def board_shared_vec(r: Dict[str, Any]) -> List[float]:
    tp = r.get("type_probs", {}) or {}
    lane_ev = clip01(safe_float(tp.get("lane_change", 0.0)))
    rear_ev = clip01(safe_float(tp.get("rear_end", 0.0)))
    gap = abs(lane_ev - rear_ev)
    conf = max(lane_ev, rear_ev)
    sym_margin = lane_ev - rear_ev
    return [lane_ev, rear_ev, gap, conf, sym_margin]


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


def train_bridge(highd_rows: List[Dict[str, Any]], train_set: Set[int], val_set: Set[int], test_set: Set[int]) -> Tuple[Pipeline, Dict[str, Any]]:
    df = pd.DataFrame(highd_rows)
    df = df[df["candidate_type"].isin(["lane_pos", "rear_risk_pos"])].copy()
    if len(df) == 0:
        raise RuntimeError("No lane_pos/rear_risk_pos in highD pool.")

    df["y"] = (df["candidate_type"] == "lane_pos").astype(int)
    df["recording_id"] = df["recording_id"].astype(int)

    x = np.array([highd_shared_vec(r) for r in df.to_dict(orient="records")], dtype=np.float32)
    y = df["y"].to_numpy(dtype=np.int64)
    rec = df["recording_id"].to_numpy(dtype=np.int64)

    tr_mask = np.array([int(r) in train_set for r in rec], dtype=bool)
    va_mask = np.array([int(r) in val_set for r in rec], dtype=bool)
    te_mask = np.array([int(r) in test_set for r in rec], dtype=bool)

    xtr, ytr = x[tr_mask], y[tr_mask]
    xva, yva = x[va_mask], y[va_mask]
    xte, yte = x[te_mask], y[te_mask]

    clf = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            ("lr", LogisticRegression(C=1.0, class_weight="balanced", solver="liblinear", max_iter=2000, random_state=42)),
        ]
    )
    if len(xtr) == 0 or len(xva) == 0 or len(xte) == 0:
        raise RuntimeError("Bridge split has empty train/val/test subset.")
    if len(np.unique(ytr)) < 2 or len(np.unique(yva)) < 2 or len(np.unique(yte)) < 2:
        raise RuntimeError("Bridge split requires both lane/rear classes in train/val/test.")

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
        "features": ["lane_evidence", "rear_evidence", "boundary_gap", "confidence", "lane_minus_rear"],
    }
    return clf, stats


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
    impact_mae = mean(abs(safe_float(r["pred"].get("pred_impact_time", 0.0)) - safe_float(r["gt"].get("impact_time", 0.0))) for r in rows) if rows else 0.0
    return {
        "accuracy": float(acc),
        "macro_f1": float(sum(f1s) / len(f1s)) if f1s else 0.0,
        "rear_recall": float(per["rear_end"]["recall"]),
        "lane_recall": float(per["lane_change"]["recall"]),
        "turn_recall": float(per["turn_conflict"]["recall"]),
        "impact_mae": float(impact_mae),
    }


def matched(gt_rows: List[Dict[str, Any]], pred_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pm = {normalize_video(r.get("video", "")): r for r in pred_rows}
    out = []
    for g in gt_rows:
        v = normalize_video(g.get("video", ""))
        p = pm.get(v)
        if p is not None:
            out.append({"gt": g, "pred": p, "video": v})
    return out


def readonly_analysis(rows: List[Dict[str, Any]], rescue_thr: float, steal_thr: float) -> Dict[str, Any]:
    lane_fn_rear = [r for r in rows if r["gt"].get("accident_type") == "lane_change" and r["pred"].get("pred_type") == "rear_end"]
    rear_gt = [r for r in rows if r["gt"].get("accident_type") == "rear_end"]
    rescue = [r for r in lane_fn_rear if safe_float(r["pred"].get("lane_bridge_score", 0.0)) >= rescue_thr]
    steal = [r for r in rear_gt if safe_float(r["pred"].get("lane_bridge_score", 0.0)) >= steal_thr]

    buckets = {}
    for b in ["day+straight_road", "day+intersection", "night+straight_road", "night+intersection"]:
        br = [r for r in rows if scene_bucket(r["gt"].get("scene_tags", [])) == b]
        b_lf = [r for r in br if r["gt"].get("accident_type") == "lane_change" and r["pred"].get("pred_type") == "rear_end"]
        b_rear = [r for r in br if r["gt"].get("accident_type") == "rear_end"]
        buckets[b] = {
            "n": len(br),
            "lane_fn_rear_n": len(b_lf),
            "rear_gt_n": len(b_rear),
            "lane_fn_rear_rescueable_n": sum(1 for r in b_lf if safe_float(r["pred"].get("lane_bridge_score", 0.0)) >= rescue_thr),
            "rear_potential_steal_n": sum(1 for r in b_rear if safe_float(r["pred"].get("lane_bridge_score", 0.0)) >= steal_thr),
            "lane_bridge_score_mean": float(mean([safe_float(r["pred"].get("lane_bridge_score", 0.0)) for r in br])) if br else 0.0,
            "rear_bridge_score_mean": float(mean([safe_float(r["pred"].get("rear_bridge_score", 0.0)) for r in br])) if br else 0.0,
        }

    margins = [safe_float(r["pred"].get("lane_bridge_score", 0.0)) - safe_float(r["pred"].get("rear_bridge_score", 0.0)) for r in lane_fn_rear]
    rear_margins = [safe_float(r["pred"].get("lane_bridge_score", 0.0)) - safe_float(r["pred"].get("rear_bridge_score", 0.0)) for r in rear_gt]
    return {
        "look1_lane_fn_vs_rear": {
            "lane_fn_rear_n": len(lane_fn_rear),
            "rescueable_n": len(rescue),
            "rescueable_ratio": (len(rescue) / len(lane_fn_rear)) if lane_fn_rear else 0.0,
            "lane_minus_rear_mean": float(mean(margins)) if margins else 0.0,
            "lane_minus_rear_median": float(median(margins)) if margins else 0.0,
        },
        "look2_rear_stealing_risk": {
            "rear_gt_n": len(rear_gt),
            "potential_rear_steal_n": len(steal),
            "potential_rear_steal_ratio": (len(steal) / len(rear_gt)) if rear_gt else 0.0,
            "lane_minus_rear_mean": float(mean(rear_margins)) if rear_margins else 0.0,
        },
        "look3_scene_buckets": buckets,
    }


def apply_patch(pred_rows: List[Dict[str, Any]], lane_thr: float, margin_thr: float, gap_max: float, turn_guard: float) -> Tuple[List[Dict[str, Any]], int]:
    out = []
    changed = 0
    for r in pred_rows:
        rr = dict(r)
        pred = str(rr.get("pred_type", ""))
        tp = rr.get("type_probs", {}) or {}
        pr = safe_float(tp.get("rear_end", 0.0))
        pl = safe_float(tp.get("lane_change", 0.0))
        pt = safe_float(tp.get("turn_conflict", 0.0))
        lane_s = safe_float(rr.get("lane_bridge_score", 0.0))
        rear_s = safe_float(rr.get("rear_bridge_score", 0.0))
        margin = lane_s - rear_s
        gap = abs(pr - pl)
        do = pred in {"rear_end", "lane_change"} and pt <= turn_guard and gap <= gap_max and lane_s >= lane_thr and margin >= margin_thr
        if do and pred != "lane_change":
            rr["pred_type"] = "lane_change"
            rr["shared_bridge_patch_applied"] = True
            changed += 1
        else:
            rr["shared_bridge_patch_applied"] = False
        out.append(rr)
    return out, changed


def add_bridge_scores(pred_rows: List[Dict[str, Any]], bridge: Pipeline) -> List[Dict[str, Any]]:
    x = np.array([board_shared_vec(r) for r in pred_rows], dtype=np.float32)
    p = bridge.predict_proba(x)[:, 1]
    out = []
    for r, ps in zip(pred_rows, p):
        rr = dict(r)
        lane_s = clip01(float(ps))
        rear_s = 1.0 - lane_s
        rr["lane_bridge_score"] = round(lane_s, 6)
        rr["rear_bridge_score"] = round(rear_s, 6)
        rr["bridge_lane_minus_rear"] = round(lane_s - rear_s, 6)
        rr["bridge_mode"] = "shared_feature_bridge"
        out.append(rr)
    return out


def run_board(name: str, gt_path: Path, pred_path: Path, bridge: Pipeline, out_dir: Path, cfg: Dict[str, float]) -> Dict[str, Any]:
    gt_rows = load_jsonl(gt_path)
    pred_base = load_jsonl(pred_path)
    pred_scored = add_bridge_scores(pred_base, bridge)
    m_base = matched(gt_rows, pred_scored)
    ro = readonly_analysis(m_base, rescue_thr=cfg["rescue_thr"], steal_thr=cfg["steal_thr"])
    base_metrics = compute_metrics(m_base)

    pred_patch, changed = apply_patch(
        pred_scored,
        lane_thr=cfg["lane_thr"],
        margin_thr=cfg["margin_thr"],
        gap_max=cfg["gap_max"],
        turn_guard=cfg["turn_guard"],
    )
    m_patch = matched(gt_rows, pred_patch)
    patch_metrics = compute_metrics(m_patch)

    scored_path = out_dir / f"{name}.shared_bridge_scored.jsonl"
    patch_path = out_dir / f"{name}.shared_bridge_patch.jsonl"
    write_jsonl(scored_path, pred_scored)
    write_jsonl(patch_path, pred_patch)
    return {
        "board": name,
        "matched_n": len(m_base),
        "readonly_analysis": ro,
        "base_metrics": base_metrics,
        "patch_metrics": patch_metrics,
        "changed_by_patch": int(changed),
        "delta": {
            "macro_f1": patch_metrics["macro_f1"] - base_metrics["macro_f1"],
            "lane_recall": patch_metrics["lane_recall"] - base_metrics["lane_recall"],
            "rear_recall": patch_metrics["rear_recall"] - base_metrics["rear_recall"],
            "impact_mae": patch_metrics["impact_mae"] - base_metrics["impact_mae"],
            "accuracy": patch_metrics["accuracy"] - base_metrics["accuracy"],
        },
        "pred_scored_path": str(scored_path),
        "pred_patch_path": str(patch_path),
    }


def aggregate(boards: List[Dict[str, Any]]) -> Dict[str, Any]:
    def m(k: str) -> float:
        vals = [b["delta"][k] for b in boards]
        return float(sum(vals) / len(vals)) if vals else 0.0
    macro = m("macro_f1")
    lane = m("lane_recall")
    rear = m("rear_recall")
    impact = m("impact_mae")
    gates = {
        "macro_f1_ge_0p005": macro >= 0.005,
        "lane_recall_ge_0p05": lane >= 0.05,
        "impact_mae_non_regression": impact <= 1e-9,
        "rear_recall_drop_le_0p02": rear >= -0.02,
    }
    return {
        "mean_delta": {"macro_f1": macro, "lane_recall": lane, "rear_recall": rear, "impact_mae": impact},
        "gates": gates,
        "overall_pass": all(gates.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Shared-feature bridge readonly simulation.")
    parser.add_argument("--highd-event-pool", required=True)
    parser.add_argument("--train-recordings", default="1-20")
    parser.add_argument("--val-recordings", default="21-25")
    parser.add_argument("--test-recordings", default="26-30")
    parser.add_argument("--gt-152", required=True)
    parser.add_argument("--gt-30", required=True)
    parser.add_argument("--gt-24", required=True)
    parser.add_argument("--pred-152", required=True)
    parser.add_argument("--pred-30", required=True)
    parser.add_argument("--pred-24", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--rescue-thr", type=float, default=0.56)
    parser.add_argument("--steal-thr", type=float, default=0.60)
    parser.add_argument("--lane-thr", type=float, default=0.58)
    parser.add_argument("--margin-thr", type=float, default=0.10)
    parser.add_argument("--gap-max", type=float, default=0.10)
    parser.add_argument("--turn-guard", type=float, default=0.42)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "rescue_thr": float(args.rescue_thr),
        "steal_thr": float(args.steal_thr),
        "lane_thr": float(args.lane_thr),
        "margin_thr": float(args.margin_thr),
        "gap_max": float(args.gap_max),
        "turn_guard": float(args.turn_guard),
    }

    highd_rows = load_jsonl(Path(args.highd_event_pool).resolve())
    train_set = set(parse_range(args.train_recordings))
    val_set = set(parse_range(args.val_recordings))
    test_set = set(parse_range(args.test_recordings))
    bridge, bridge_stats = train_bridge(highd_rows, train_set, val_set, test_set)

    boards = []
    boards.append(run_board("board152", Path(args.gt_152).resolve(), Path(args.pred_152).resolve(), bridge, out_dir, cfg))
    boards.append(run_board("board30", Path(args.gt_30).resolve(), Path(args.pred_30).resolve(), bridge, out_dir, cfg))
    boards.append(run_board("board24", Path(args.gt_24).resolve(), Path(args.pred_24).resolve(), bridge, out_dir, cfg))
    agg = aggregate(boards)

    report = {
        "mode": "shared_feature_bridge_readonly_sim",
        "bridge_train_stats": bridge_stats,
        "bridge_split": {
            "train_recordings": sorted(train_set),
            "val_recordings": sorted(val_set),
            "test_recordings": sorted(test_set),
        },
        "config": cfg,
        "boards": boards,
        "aggregate": agg,
        "decision": "PASS_TO_NEXT_MINIMAL_INTEGRATION" if agg["overall_pass"] else "FAIL_STOP_SHARED_BRIDGE_ROUTE",
    }
    report_path = out_dir / "HIGHD_SHARED_BRIDGE_READONLY_SIM_2026-05-07.json"
    md_path = out_dir / "HIGHD_SHARED_BRIDGE_READONLY_SIM_2026-05-07.md"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# highD Shared-Feature Bridge Readonly Sim",
        "",
        f"- bridge_auc_val: {bridge_stats['auc_val']:.6f}",
        f"- bridge_auc_test: {bridge_stats['auc_test']:.6f}",
        "",
    ]
    for b in boards:
        lines += [
            f"## {b['board']}",
            f"- changed_by_patch: {b['changed_by_patch']}",
            (
                f"- delta macro/lane/rear/impact: "
                f"{b['delta']['macro_f1']:+.6f} / {b['delta']['lane_recall']:+.6f} / "
                f"{b['delta']['rear_recall']:+.6f} / {b['delta']['impact_mae']:+.6f}"
            ),
            "",
        ]
    lines += [
        "## Aggregate",
        (
            f"- mean delta macro/lane/rear/impact: "
            f"{agg['mean_delta']['macro_f1']:+.6f} / {agg['mean_delta']['lane_recall']:+.6f} / "
            f"{agg['mean_delta']['rear_recall']:+.6f} / {agg['mean_delta']['impact_mae']:+.6f}"
        ),
        f"- gates: {agg['gates']}",
        f"- overall_pass: {agg['overall_pass']}",
        f"- decision: {report['decision']}",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"report": str(report_path), "md": str(md_path), "decision": report["decision"], "aggregate": agg}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
