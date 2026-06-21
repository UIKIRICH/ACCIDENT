import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Tuple


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


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


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


def compute_metrics(rows: List[Dict[str, Any]], key: str) -> Dict[str, float]:
    cls = ["rear_end", "lane_change", "turn_conflict"]
    y_true = [str(r["gt_type"]).strip() for r in rows]
    y_pred = [str(r[key]).strip() for r in rows]
    n = len(y_true)
    acc = sum(1 for t, p in zip(y_true, y_pred) if t == p) / n if n else 0.0
    f1s: List[float] = []
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


def apply_variant(rows: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rr = dict(r)
        pred = str(rr["pred_type"]).strip()
        gt = str(rr["gt_type"]).strip()
        lane_s = safe_float(rr["lane_score"], 0.0)
        rear_s = safe_float(rr["rear_score"], 0.0)
        margin = lane_s - rear_s

        tags = parse_scene_tags(rr.get("scene_tags", []))
        bucket = scene_bucket(tags)
        is_day_straight = bucket == "day+straight_road"
        prob_rear = safe_float(rr.get("prob_rear", 0.0), 0.0)
        rear_strength = safe_float(rr.get("feat_rear_behavior_strength", 0.0), 0.0)
        pair_cons = safe_float(rr.get("feat_pair_temporal_consistency", 0.0), 0.0)

        do_rewrite = False
        if pred in {"rear_end", "lane_change"}:
            do_rewrite = lane_s >= float(cfg["lane_thr"]) and margin >= float(cfg["margin_thr"])

        # Just-over-line second check
        if do_rewrite and pred == "rear_end":
            if lane_s < float(cfg["lane_thr"]) + float(cfg["just_over_eps"]):
                do_rewrite = False

        # day+straight rear keep
        if do_rewrite and pred == "rear_end" and is_day_straight:
            if prob_rear >= float(cfg["day_straight_rear_prob_keep_thr"]):
                do_rewrite = False

        # rear strong evidence soft block
        if do_rewrite and pred == "rear_end" and bool(cfg["enable_rear_strength_block"]):
            if rear_strength >= float(cfg["rear_strength_thr"]) and pair_cons >= float(cfg["pair_cons_thr"]):
                do_rewrite = False

        rr["pred_type_patch"] = "lane_change" if do_rewrite else pred
        rr["rewrite_applied"] = bool(do_rewrite and pred != "lane_change")
        rr["gt_type"] = gt
        rr["scene_bucket"] = bucket
        out.append(rr)
    return out


def eval_one_board(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    base = compute_metrics(rows, "pred_type")
    patch = compute_metrics(rows, "pred_type_patch")

    lane_fn_rear = [r for r in rows if r["gt_type"] == "lane_change" and r["pred_type"] == "rear_end"]
    rear_gt = [r for r in rows if r["gt_type"] == "rear_end"]
    rescueable = [r for r in lane_fn_rear if r["pred_type_patch"] == "lane_change"]
    changed = [r for r in rows if r["pred_type_patch"] != r["pred_type"]]
    # strict rear stealing: only count rear samples that were rear before patch
    # and got rewritten away from rear by this patch.
    rear_steal = [
        r for r in rear_gt
        if str(r["pred_type"]).strip() == "rear_end" and str(r["pred_type_patch"]).strip() != "rear_end"
    ]
    rear_already_nonrear_before = [
        r for r in rear_gt
        if str(r["pred_type"]).strip() != "rear_end"
    ]

    ds_lane_fn_rear = [r for r in lane_fn_rear if r["scene_bucket"] == "day+straight_road"]
    ds_rescue = [r for r in ds_lane_fn_rear if r["pred_type_patch"] == "lane_change"]
    ds_lane_over_rear = [r for r in ds_lane_fn_rear if safe_float(r["lane_score"], 0.0) > safe_float(r["rear_score"], 0.0)]

    return {
        "n": int(len(rows)),
        "lane_fn_rear_n": int(len(lane_fn_rear)),
        "rear_gt_n": int(len(rear_gt)),
        "rescueable_n": int(len(rescueable)),
        "changed_n": int(len(changed)),
        "rear_steal_n": int(len(rear_steal)),
        "rear_already_nonrear_before_n": int(len(rear_already_nonrear_before)),
        "rear_steal_ratio": float((len(rear_steal) / len(rear_gt)) if rear_gt else 0.0),
        "day_straight_lane_fn_rear_n": int(len(ds_lane_fn_rear)),
        "day_straight_rescueable_n": int(len(ds_rescue)),
        "day_straight_lane_over_rear_n": int(len(ds_lane_over_rear)),
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


def aggregate(by_board: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    bs = list(by_board.values())
    rescueable_total = int(sum(b["rescueable_n"] for b in bs))
    changed_total = int(sum(b["changed_n"] for b in bs))
    rear_gt_total = int(sum(b["rear_gt_n"] for b in bs))
    rear_steal_total = int(sum(b["rear_steal_n"] for b in bs))
    rear_steal_ratio_total = (rear_steal_total / rear_gt_total) if rear_gt_total else 0.0
    day_straight_lane_over_rear_total = int(sum(b["day_straight_lane_over_rear_n"] for b in bs))
    day_straight_rescueable_total = int(sum(b["day_straight_rescueable_n"] for b in bs))
    return {
        "rescueable_total": rescueable_total,
        "changed_total": changed_total,
        "rear_gt_total": rear_gt_total,
        "rear_steal_total": rear_steal_total,
        "rear_steal_ratio_total": float(rear_steal_ratio_total),
        "day_straight_lane_over_rear_total": day_straight_lane_over_rear_total,
        "day_straight_rescueable_total": day_straight_rescueable_total,
        "delta_macro_f1_mean": float(mean([b["delta_metrics"]["macro_f1"] for b in bs])) if bs else 0.0,
        "delta_lane_recall_mean": float(mean([b["delta_metrics"]["lane_recall"] for b in bs])) if bs else 0.0,
        "delta_rear_recall_mean": float(mean([b["delta_metrics"]["rear_recall"] for b in bs])) if bs else 0.0,
    }


def load_board_with_meta(scored_path: Path, native_path: Path) -> List[Dict[str, Any]]:
    scored = load_jsonl(scored_path)
    native = load_jsonl(native_path)
    meta_by_sid: Dict[str, Dict[str, Any]] = {}
    for r in native:
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            meta_by_sid[sid] = r

    out: List[Dict[str, Any]] = []
    for r in scored:
        sid = str(r.get("sample_id", "")).strip()
        meta = meta_by_sid.get(sid, {})
        rr = dict(r)
        rr["prob_rear"] = safe_float(meta.get("prob_rear", 0.0), 0.0)
        rr["feat_rear_behavior_strength"] = safe_float(meta.get("feat_rear_behavior_strength", 0.0), 0.0)
        rr["feat_pair_temporal_consistency"] = safe_float(meta.get("feat_pair_temporal_consistency", 0.0), 0.0)
        out.append(rr)
    return out


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_md(path: Path, payload: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# exiD Step4 Constraint Microgrid")
    lines.append("")
    for v in payload["variants"]:
        name = v["name"]
        ag = v["aggregate"]
        checks = v["checks"]
        lines.append(f"## {name}")
        lines.append(f"- rescueable_total: {ag['rescueable_total']}")
        lines.append(f"- changed_total: {ag['changed_total']}")
        lines.append(f"- rear_steal_ratio_total: {ag['rear_steal_ratio_total']:.6f}")
        lines.append(f"- delta_macro_f1_mean: {ag['delta_macro_f1_mean']:+.6f}")
        lines.append(f"- delta_lane_recall_mean: {ag['delta_lane_recall_mean']:+.6f}")
        lines.append(f"- delta_rear_recall_mean: {ag['delta_rear_recall_mean']:+.6f}")
        lines.append(f"- day_straight_lane_over_rear_total: {ag['day_straight_lane_over_rear_total']}")
        lines.append(f"- checks: {checks}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="exiD Step4 super-small constraint grid (no retrain).")
    parser.add_argument("--scored-152", required=True)
    parser.add_argument("--scored-30", required=True)
    parser.add_argument("--scored-24", required=True)
    parser.add_argument("--native-152", required=True)
    parser.add_argument("--native-30", required=True)
    parser.add_argument("--native-24", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument(
        "--variant-preset",
        default="base",
        choices=["base", "v4_refine"],
        help="base: original 4 variants; v4_refine: only 3 variants around v4 for final tightening",
    )
    args = parser.parse_args()

    board152 = load_board_with_meta(Path(args.scored_152).resolve(), Path(args.native_152).resolve())
    board30 = load_board_with_meta(Path(args.scored_30).resolve(), Path(args.native_30).resolve())
    board24 = load_board_with_meta(Path(args.scored_24).resolve(), Path(args.native_24).resolve())

    if args.variant_preset == "base":
        variants = [
            {
                "name": "v1_light",
                "lane_thr": 0.66,
                "margin_thr": 0.30,
                "just_over_eps": 0.03,
                "day_straight_rear_prob_keep_thr": 0.75,
                "enable_rear_strength_block": False,
                "rear_strength_thr": 0.55,
                "pair_cons_thr": 0.75,
            },
            {
                "name": "v2_mid",
                "lane_thr": 0.68,
                "margin_thr": 0.36,
                "just_over_eps": 0.04,
                "day_straight_rear_prob_keep_thr": 0.70,
                "enable_rear_strength_block": True,
                "rear_strength_thr": 0.55,
                "pair_cons_thr": 0.75,
            },
            {
                "name": "v3_mid_plus_ds_guard",
                "lane_thr": 0.70,
                "margin_thr": 0.40,
                "just_over_eps": 0.05,
                "day_straight_rear_prob_keep_thr": 0.65,
                "enable_rear_strength_block": True,
                "rear_strength_thr": 0.50,
                "pair_cons_thr": 0.70,
            },
            {
                "name": "v4_strong",
                "lane_thr": 0.72,
                "margin_thr": 0.44,
                "just_over_eps": 0.06,
                "day_straight_rear_prob_keep_thr": 0.60,
                "enable_rear_strength_block": True,
                "rear_strength_thr": 0.45,
                "pair_cons_thr": 0.65,
            },
        ]
    else:
        # v4_refine: only 3 tiny moves around v4 (no expansion, no retrain)
        variants = [
            {
                "name": "v4A_margin_up",
                "lane_thr": 0.72,
                "margin_thr": 0.46,
                "just_over_eps": 0.06,
                "day_straight_rear_prob_keep_thr": 0.60,
                "enable_rear_strength_block": True,
                "rear_strength_thr": 0.45,
                "pair_cons_thr": 0.65,
            },
            {
                "name": "v4B_lane_thr_up",
                "lane_thr": 0.73,
                "margin_thr": 0.44,
                "just_over_eps": 0.06,
                "day_straight_rear_prob_keep_thr": 0.60,
                "enable_rear_strength_block": True,
                "rear_strength_thr": 0.45,
                "pair_cons_thr": 0.65,
            },
            {
                "name": "v4C_daystraight_keep_up",
                "lane_thr": 0.72,
                "margin_thr": 0.44,
                "just_over_eps": 0.06,
                "day_straight_rear_prob_keep_thr": 0.58,
                "enable_rear_strength_block": True,
                "rear_strength_thr": 0.45,
                "pair_cons_thr": 0.65,
            },
        ]

    out_variants: List[Dict[str, Any]] = []
    for cfg in variants:
        b152 = apply_variant(board152, cfg)
        b30 = apply_variant(board30, cfg)
        b24 = apply_variant(board24, cfg)
        by_board = {
            "board152": eval_one_board(b152),
            "board30": eval_one_board(b30),
            "board24": eval_one_board(b24),
        }
        ag = aggregate(by_board)
        checks = {
            "rescueable_total_gt_0": ag["rescueable_total"] > 0,
            "changed_total_gt_0": ag["changed_total"] > 0,
            "rear_steal_ratio_lt_10pct": ag["rear_steal_ratio_total"] < 0.10,
            "delta_macro_f1_non_negative": ag["delta_macro_f1_mean"] >= 0.0,
            "day_straight_lane_over_rear_nonzero": ag["day_straight_lane_over_rear_total"] > 0,
        }
        out_variants.append(
            {
                "name": cfg["name"],
                "config": cfg,
                "by_board": by_board,
                "aggregate": ag,
                "checks": checks,
            }
        )

    # choose by lexicographic goal: rear_steal_ratio asc, then delta_macro_f1 desc
    best = sorted(
        out_variants,
        key=lambda x: (x["aggregate"]["rear_steal_ratio_total"], -x["aggregate"]["delta_macro_f1_mean"]),
    )[0]

    payload = {
        "mode": "exid_step4_constraint_microgrid_no_retrain",
        "variants": out_variants,
        "selected_by_rule": {
            "rule": "min rear_steal_ratio_total, tie-break max delta_macro_f1_mean",
            "selected_name": best["name"],
        },
    }
    write_json(Path(args.out_json).resolve(), payload)
    write_md(Path(args.out_md).resolve(), payload)
    print(json.dumps({"out_json": str(Path(args.out_json).resolve()), "out_md": str(Path(args.out_md).resolve()), "selected": best["name"], "selected_aggregate": best["aggregate"], "selected_checks": best["checks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
