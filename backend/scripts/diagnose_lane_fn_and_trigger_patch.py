import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Tuple


CLASSES = ["rear_end", "lane_change", "turn_conflict"]


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


def dump_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def normalize_video_key(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def parse_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None:
        return []
    s = str(v).strip()
    if not s:
        return []
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [str(x).strip() for x in obj if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [s]


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def class_metrics(y_true: List[str], y_pred: List[str], cls: str) -> Dict[str, float]:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p == cls)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t != cls and p == cls)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == cls and p != cls)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "support": int(sum(1 for t in y_true if t == cls)),
    }


def eval_basic(y_true: List[str], y_pred: List[str]) -> Dict[str, Any]:
    n = len(y_true)
    acc = (sum(1 for t, p in zip(y_true, y_pred) if t == p) / n) if n else 0.0
    per_class = {c: class_metrics(y_true, y_pred, c) for c in CLASSES}
    macro = sum(per_class[c]["f1"] for c in CLASSES) / len(CLASSES) if CLASSES else 0.0
    return {
        "n": n,
        "accuracy": acc,
        "macro_f1": macro,
        "rear_recall": per_class["rear_end"]["recall"],
        "lane_recall": per_class["lane_change"]["recall"],
        "turn_recall": per_class["turn_conflict"]["recall"],
        "per_class": per_class,
    }


def lane_fn_rootcause(rows_gt: List[Dict[str, Any]], rows_pred: List[Dict[str, Any]]) -> Dict[str, Any]:
    gt_map = {normalize_video_key(r.get("video", "")): r for r in rows_gt}
    pred_map = {normalize_video_key(r.get("video", "")): r for r in rows_pred}
    keys = sorted(set(gt_map.keys()) & set(pred_map.keys()))

    lane_rows: List[Dict[str, Any]] = []
    lane_fn_rows: List[Dict[str, Any]] = []

    for k in keys:
        gt = gt_map[k]
        pred = pred_map[k]
        gt_type = str(gt.get("accident_type", "")).strip()
        if gt_type != "lane_change":
            continue
        lane_rows.append({"gt": gt, "pred": pred, "video": k})
        if str(pred.get("pred_type", "")).strip() != "lane_change":
            lane_fn_rows.append({"gt": gt, "pred": pred, "video": k})

    fn_pred_dist = Counter(str(x["pred"].get("pred_type", "")).strip() for x in lane_fn_rows)
    scene_combo = Counter()
    scene_tag = Counter()
    rear_guard_applied = Counter()

    lane_prob_vals: List[float] = []
    rear_minus_lane_vals: List[float] = []
    turn_minus_lane_vals: List[float] = []
    lane_prob_bucket = Counter()
    rl_gap_bucket = Counter()
    tl_gap_bucket = Counter()

    for x in lane_fn_rows:
        pred = x["pred"]
        tags = parse_scene_tags(pred.get("scene_tags", []))
        combo = "|".join(sorted(tags)) if tags else "<none>"
        scene_combo[combo] += 1
        for t in tags:
            scene_tag[t] += 1

        rg = bool(pred.get("rear_guard_applied", False))
        rear_guard_applied["true" if rg else "false"] += 1

        probs = pred.get("type_probs", {}) or {}
        pr = safe_float(probs.get("rear_end", 0.0), 0.0)
        pl = safe_float(probs.get("lane_change", 0.0), 0.0)
        pt = safe_float(probs.get("turn_conflict", 0.0), 0.0)
        lane_prob_vals.append(pl)
        rear_minus_lane_vals.append(pr - pl)
        turn_minus_lane_vals.append(pt - pl)

        if pl < 0.24:
            lane_prob_bucket["<0.24"] += 1
        elif pl < 0.27:
            lane_prob_bucket["0.24-0.27"] += 1
        elif pl < 0.30:
            lane_prob_bucket["0.27-0.30"] += 1
        else:
            lane_prob_bucket[">=0.30"] += 1

        rl = pr - pl
        if rl < 0.05:
            rl_gap_bucket["<0.05"] += 1
        elif rl < 0.08:
            rl_gap_bucket["0.05-0.08"] += 1
        elif rl < 0.11:
            rl_gap_bucket["0.08-0.11"] += 1
        else:
            rl_gap_bucket[">=0.11"] += 1

        tl = pt - pl
        if tl < 0.05:
            tl_gap_bucket["<0.05"] += 1
        elif tl < 0.08:
            tl_gap_bucket["0.05-0.08"] += 1
        elif tl < 0.11:
            tl_gap_bucket["0.08-0.11"] += 1
        else:
            tl_gap_bucket[">=0.11"] += 1

    lane_total = len(lane_rows)
    fn_total = len(lane_fn_rows)
    lane_recall = (lane_total - fn_total) / lane_total if lane_total else 0.0

    def stats(vals: List[float]) -> Dict[str, float]:
        if not vals:
            return {"mean": 0.0, "min": 0.0, "max": 0.0}
        return {"mean": sum(vals) / len(vals), "min": min(vals), "max": max(vals)}

    return {
        "lane_gt_total": lane_total,
        "lane_fn_total": fn_total,
        "lane_recall": lane_recall,
        "fn_pred_type_dist": dict(fn_pred_dist),
        "rear_guard_applied_dist": dict(rear_guard_applied),
        "scene_combo_top20": scene_combo.most_common(20),
        "scene_tag_top20": scene_tag.most_common(20),
        "lane_prob_bucket": dict(lane_prob_bucket),
        "rear_minus_lane_bucket": dict(rl_gap_bucket),
        "turn_minus_lane_bucket": dict(tl_gap_bucket),
        "lane_prob_stats": stats(lane_prob_vals),
        "rear_minus_lane_stats": stats(rear_minus_lane_vals),
        "turn_minus_lane_stats": stats(turn_minus_lane_vals),
    }


def should_flip_to_lane(row: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    pred_type = str(row.get("pred_type", "")).strip()
    if pred_type not in {"rear_end", "turn_conflict"}:
        return False
    tags = set(parse_scene_tags(row.get("scene_tags", [])))
    if cfg.get("require_day", False) and "day" not in tags:
        return False
    if cfg.get("require_straight_road", False) and "straight_road" not in tags:
        return False
    if cfg.get("block_turning_scene", True) and "turning_scene" in tags:
        return False
    if cfg.get("require_rear_guard_applied", False) and not bool(row.get("rear_guard_applied", False)):
        return False

    probs = row.get("type_probs", {}) or {}
    pr = safe_float(probs.get("rear_end", 0.0), 0.0)
    pl = safe_float(probs.get("lane_change", 0.0), 0.0)
    pt = safe_float(probs.get("turn_conflict", 0.0), 0.0)

    if pl < float(cfg["lane_prob_thr"]):
        return False
    if (pl - pr) < float(cfg["lane_minus_rear_min"]):
        return False
    if (pl - pt) < float(cfg["lane_minus_turn_min"]):
        return False
    if pr > float(cfg["rear_prob_max"]):
        return False
    if pt > float(cfg["turn_prob_max"]):
        return False
    return True


def maybe_rollback_to_rear(row: Dict[str, Any], cfg: Dict[str, Any]) -> bool:
    probs = row.get("type_probs", {}) or {}
    pr = safe_float(probs.get("rear_end", 0.0), 0.0)
    pl = safe_float(probs.get("lane_change", 0.0), 0.0)
    if pr >= float(cfg["rear_lock_prob"]) and (pr - pl) >= float(cfg["rear_lock_gap_min"]):
        return True
    return False


def apply_trigger_patch(rows_pred: List[Dict[str, Any]], cfg: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    out: List[Dict[str, Any]] = []
    flips = 0
    rollbacks = 0
    for r in rows_pred:
        x = dict(r)
        x["lane_trigger_applied"] = False
        x["lane_trigger_cfg_name"] = cfg["name"]

        if should_flip_to_lane(x, cfg):
            x["pred_type"] = "lane_change"
            x["lane_trigger_applied"] = True
            flips += 1
            if maybe_rollback_to_rear(x, cfg):
                x["pred_type"] = "rear_end"
                x["lane_trigger_applied"] = False
                rollbacks += 1
        out.append(x)
    return out, {"flips": flips, "rollbacks": rollbacks}


def eval_board(rows_gt: List[Dict[str, Any]], rows_pred: List[Dict[str, Any]]) -> Dict[str, Any]:
    gt_map = {normalize_video_key(r.get("video", "")): r for r in rows_gt}
    pred_map = {normalize_video_key(r.get("video", "")): r for r in rows_pred}
    keys = sorted(set(gt_map.keys()) & set(pred_map.keys()))
    y_true = [str(gt_map[k].get("accident_type", "")).strip() for k in keys]
    y_pred = [str(pred_map[k].get("pred_type", "")).strip() for k in keys]
    return eval_basic(y_true, y_pred)


def mean_metrics(ms: List[Dict[str, Any]]) -> Dict[str, float]:
    if not ms:
        return {"accuracy": 0.0, "macro_f1": 0.0, "rear_recall": 0.0, "lane_recall": 0.0, "turn_recall": 0.0}
    k = ["accuracy", "macro_f1", "rear_recall", "lane_recall", "turn_recall"]
    return {kk: sum(float(m[kk]) for m in ms) / len(ms) for kk in k}


def default_cfgs() -> List[Dict[str, Any]]:
    return [
        {
            "name": "lane_patch_c1_tight",
            "lane_prob_thr": 0.288,
            "lane_minus_rear_min": -0.060,
            "lane_minus_turn_min": -0.095,
            "rear_prob_max": 0.350,
            "turn_prob_max": 0.390,
            "rear_lock_prob": 0.366,
            "rear_lock_gap_min": 0.065,
            "require_day": True,
            "require_straight_road": True,
            "block_turning_scene": True,
            "require_rear_guard_applied": False,
        },
        {
            "name": "lane_patch_c2_mid",
            "lane_prob_thr": 0.282,
            "lane_minus_rear_min": -0.072,
            "lane_minus_turn_min": -0.105,
            "rear_prob_max": 0.355,
            "turn_prob_max": 0.402,
            "rear_lock_prob": 0.364,
            "rear_lock_gap_min": 0.060,
            "require_day": True,
            "require_straight_road": True,
            "block_turning_scene": True,
            "require_rear_guard_applied": False,
        },
        {
            "name": "lane_patch_c3_rg_only",
            "lane_prob_thr": 0.279,
            "lane_minus_rear_min": -0.080,
            "lane_minus_turn_min": -0.110,
            "rear_prob_max": 0.357,
            "turn_prob_max": 0.405,
            "rear_lock_prob": 0.360,
            "rear_lock_gap_min": 0.055,
            "require_day": True,
            "require_straight_road": True,
            "block_turning_scene": True,
            "require_rear_guard_applied": True,
        },
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Lane FN bucket diagnosis + no-retrain trigger patch micro check.")
    parser.add_argument("--pred-152", required=True)
    parser.add_argument("--gt-152", required=True)
    parser.add_argument("--pred-board30", default="")
    parser.add_argument("--gt-board30", default="")
    parser.add_argument("--pred-board24", default="")
    parser.add_argument("--gt-board24", default="")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows_pred_152 = load_jsonl(Path(args.pred_152).resolve())
    rows_gt_152 = load_jsonl(Path(args.gt_152).resolve())

    rows_pred_30: List[Dict[str, Any]] = []
    rows_gt_30: List[Dict[str, Any]] = []
    rows_pred_24: List[Dict[str, Any]] = []
    rows_gt_24: List[Dict[str, Any]] = []
    if str(args.pred_board30).strip() and str(args.gt_board30).strip():
        rows_pred_30 = load_jsonl(Path(args.pred_board30).resolve())
        rows_gt_30 = load_jsonl(Path(args.gt_board30).resolve())
    if str(args.pred_board24).strip() and str(args.gt_board24).strip():
        rows_pred_24 = load_jsonl(Path(args.pred_board24).resolve())
        rows_gt_24 = load_jsonl(Path(args.gt_board24).resolve())

    rootcause = lane_fn_rootcause(rows_gt_152, rows_pred_152)
    (out_dir / "lane_fn_rootcause_152.json").write_text(
        json.dumps(rootcause, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    baseline_152 = eval_board(rows_gt_152, rows_pred_152)
    baseline_30 = eval_board(rows_gt_30, rows_pred_30) if rows_gt_30 and rows_pred_30 else None
    baseline_24 = eval_board(rows_gt_24, rows_pred_24) if rows_gt_24 and rows_pred_24 else None

    trials: List[Dict[str, Any]] = []
    for cfg in default_cfgs():
        p152, c152 = apply_trigger_patch(rows_pred_152, cfg)
        m152 = eval_board(rows_gt_152, p152)

        boards_m = [m152]
        board_metrics: Dict[str, Any] = {"board152": m152}
        patched_outputs: Dict[str, str] = {}
        p152_path = out_dir / f"pred_{cfg['name']}_board152.jsonl"
        dump_jsonl(p152_path, p152)
        patched_outputs["board152"] = str(p152_path)

        if rows_gt_30 and rows_pred_30:
            p30, _ = apply_trigger_patch(rows_pred_30, cfg)
            m30 = eval_board(rows_gt_30, p30)
            boards_m.append(m30)
            board_metrics["board30"] = m30
            p30_path = out_dir / f"pred_{cfg['name']}_board30.jsonl"
            dump_jsonl(p30_path, p30)
            patched_outputs["board30"] = str(p30_path)

        if rows_gt_24 and rows_pred_24:
            p24, _ = apply_trigger_patch(rows_pred_24, cfg)
            m24 = eval_board(rows_gt_24, p24)
            boards_m.append(m24)
            board_metrics["board24"] = m24
            p24_path = out_dir / f"pred_{cfg['name']}_board24.jsonl"
            dump_jsonl(p24_path, p24)
            patched_outputs["board24"] = str(p24_path)

        mean_m = mean_metrics(boards_m)
        base_mean = mean_metrics(
            [x for x in [baseline_152, baseline_30, baseline_24] if x is not None]
        )
        delta = {
            "accuracy": mean_m["accuracy"] - base_mean["accuracy"],
            "macro_f1": mean_m["macro_f1"] - base_mean["macro_f1"],
            "rear_recall": mean_m["rear_recall"] - base_mean["rear_recall"],
            "lane_recall": mean_m["lane_recall"] - base_mean["lane_recall"],
            "turn_recall": mean_m["turn_recall"] - base_mean["turn_recall"],
        }
        score = (
            delta["macro_f1"]
            + 0.35 * delta["lane_recall"]
            - max(0.0, -delta["rear_recall"]) * 0.55
        )
        trials.append(
            {
                "cfg": cfg,
                "apply_count": c152,
                "board_metrics": board_metrics,
                "mean": mean_m,
                "delta_vs_baseline_mean": delta,
                "score": score,
                "patched_outputs": patched_outputs,
            }
        )

    trials_sorted = sorted(trials, key=lambda x: x["score"], reverse=True)
    best = trials_sorted[0] if trials_sorted else None

    summary = {
        "baseline": {
            "board152": baseline_152,
            "board30": baseline_30,
            "board24": baseline_24,
            "mean_equal_weight": mean_metrics(
                [x for x in [baseline_152, baseline_30, baseline_24] if x is not None]
            ),
        },
        "lane_fn_rootcause_152": rootcause,
        "trials_ranked": trials_sorted,
        "recommended": best["cfg"]["name"] if best else "",
        "decision_hint": "NO_PROMOTE_IF_MACRO_NOT_UP_OR_REAR_DROP_TOO_MUCH",
    }
    summary_path = out_dir / "LANE_FN_TRIGGER_PATCH_DIAG_SUMMARY_2026-05-06.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = []
    md_lines.append("# Lane FN Rootcause + Trigger Patch (No Retrain)")
    md_lines.append("")
    md_lines.append("## Baseline Mean (Equal Weight)")
    bmean = summary["baseline"]["mean_equal_weight"]
    md_lines.append(
        f"- accuracy={bmean['accuracy']:.6f}, macro-F1={bmean['macro_f1']:.6f}, rearR={bmean['rear_recall']:.6f}, laneR={bmean['lane_recall']:.6f}, turnR={bmean['turn_recall']:.6f}"
    )
    md_lines.append("")
    md_lines.append("## Lane FN Rootcause (152)")
    md_lines.append(
        f"- lane_gt={rootcause['lane_gt_total']}, lane_fn={rootcause['lane_fn_total']}, lane_recall={rootcause['lane_recall']:.6f}"
    )
    md_lines.append(f"- fn_pred_type_dist={rootcause['fn_pred_type_dist']}")
    md_lines.append(f"- rear_guard_applied_dist={rootcause['rear_guard_applied_dist']}")
    md_lines.append(f"- scene_combo_top20={rootcause['scene_combo_top20'][:5]}")
    md_lines.append("")
    md_lines.append("## Trial Ranking")
    for i, t in enumerate(trials_sorted, start=1):
        d = t["delta_vs_baseline_mean"]
        md_lines.append(
            f"{i}. {t['cfg']['name']}: d_macro={d['macro_f1']:+.6f}, d_laneR={d['lane_recall']:+.6f}, d_rearR={d['rear_recall']:+.6f}, score={t['score']:+.6f}, flips152={t['apply_count']['flips']}, rollback152={t['apply_count']['rollbacks']}"
        )
    md_lines.append("")
    md_lines.append("## Recommended")
    md_lines.append(f"- {summary['recommended']}")
    md_lines.append(f"- summary_json={summary_path}")
    (out_dir / "LANE_FN_TRIGGER_PATCH_DIAG_SUMMARY_2026-05-06.md").write_text(
        "\n".join(md_lines), encoding="utf-8"
    )

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
