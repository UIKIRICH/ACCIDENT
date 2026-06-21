import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


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


def other_subscene(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    if "turning_scene" in s or "occlusion" in s:
        return "other_scope_edge"
    if "rain" in s or "crowded" in s or "urban" in s:
        return "other_contextual"
    return "other_default"


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


def eval_patch(rows: List[Dict[str, Any]], patch_key: str) -> Dict[str, Any]:
    base = compute_metrics(rows, "pred_type")
    patch = compute_metrics(rows, patch_key)
    lane_fn_rear = [r for r in rows if r["gt_type"] == "lane_change" and r["pred_type"] == "rear_end"]
    rear_gt = [r for r in rows if r["gt_type"] == "rear_end"]
    rescueable = [r for r in lane_fn_rear if str(r[patch_key]).strip() == "lane_change"]
    changed = [r for r in rows if str(r[patch_key]).strip() != str(r["pred_type"]).strip()]
    rear_steal = [
        r for r in rear_gt
        if str(r["pred_type"]).strip() == "rear_end" and str(r[patch_key]).strip() != "rear_end"
    ]
    out = {
        "n": int(len(rows)),
        "lane_fn_rear_n": int(len(lane_fn_rear)),
        "rear_gt_n": int(len(rear_gt)),
        "rescueable_total": int(len(rescueable)),
        "changed_total": int(len(changed)),
        "rear_steal_total": int(len(rear_steal)),
        "rear_steal_ratio": float((len(rear_steal) / len(rear_gt)) if rear_gt else 0.0),
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
    return out


def strict_rear_steal_ratio(rows: List[Dict[str, Any]], patch_key: str) -> Dict[str, Any]:
    rear_gt = [r for r in rows if str(r.get("gt_type", "")).strip() == "rear_end"]
    rear_steal = [
        r for r in rear_gt
        if str(r.get("pred_type", "")).strip() == "rear_end" and str(r.get(patch_key, "")).strip() != "rear_end"
    ]
    return {
        "rear_gt_n": int(len(rear_gt)),
        "rear_steal_n": int(len(rear_steal)),
        "rear_steal_ratio": float((len(rear_steal) / len(rear_gt)) if rear_gt else 0.0),
    }


def pick_bucket_cfg(bucket: str, tags: List[str], cfg: Dict[str, Dict[str, float]]) -> Dict[str, float]:
    if bucket == "day+straight_road":
        return cfg["day+straight_road"]
    if bucket == "night+straight_road":
        return cfg["night+straight_road"]
    if bucket == "day+intersection":
        return cfg["day+intersection"]
    if bucket == "other":
        sub = other_subscene(tags)
        return cfg[sub]
    return cfg["fallback"]


def apply_bucket_aware(rows: List[Dict[str, Any]], cfg: Dict[str, Dict[str, float]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in rows:
        rr = dict(r)
        pred = str(rr.get("pred_type", "")).strip()
        lane_s = safe_float(rr.get("lane_score", 0.0), 0.0)
        rear_s = safe_float(rr.get("rear_score", 0.0), 0.0)
        margin = lane_s - rear_s
        tags = parse_scene_tags(rr.get("scene_tags", []))
        bucket = scene_bucket(tags)
        bcfg = pick_bucket_cfg(bucket, tags, cfg)
        prob_rear = safe_float(rr.get("prob_rear", 0.0), 0.0)
        rear_strength = safe_float(rr.get("feat_rear_behavior_strength", 0.0), 0.0)
        pair_cons = safe_float(rr.get("feat_pair_temporal_consistency", 0.0), 0.0)

        do_rewrite = False
        if pred in {"rear_end", "lane_change"}:
            do_rewrite = lane_s >= float(bcfg["lane_thr"]) and margin >= float(bcfg["margin_thr"])

        if do_rewrite and pred == "rear_end":
            if lane_s < float(bcfg["lane_thr"]) + float(bcfg["just_over_eps"]):
                do_rewrite = False

        if do_rewrite and pred == "rear_end":
            if prob_rear >= float(bcfg["rear_prob_keep_thr"]):
                do_rewrite = False

        if do_rewrite and pred == "rear_end":
            if rear_strength >= float(bcfg["rear_strength_thr"]) and pair_cons >= float(bcfg["pair_cons_thr"]):
                do_rewrite = False

        rr["pred_type_patch_bucketaware"] = "lane_change" if do_rewrite else pred
        rr["rewrite_applied_bucketaware"] = bool(do_rewrite and pred != "lane_change")
        rr["scene_bucket"] = bucket
        rr["other_subscene"] = other_subscene(tags) if bucket == "other" else ""
        out.append(rr)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate one bucket-aware constraint version vs v4_refine on one scored board.")
    parser.add_argument("--scored-jsonl", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    parser.add_argument("--out-patched-jsonl", required=True)
    parser.add_argument("--day-straight-pair-cons-thr", type=float, default=0.65)
    args = parser.parse_args()

    rows = load_jsonl(Path(args.scored_jsonl).resolve())
    if not rows:
        raise RuntimeError("empty scored board")

    cfg = {
        # Stable bucket: allow rescue, keep rear guard similar to v4_refine.
        "day+straight_road": {
            "lane_thr": 0.72,
            "margin_thr": 0.46,
            "just_over_eps": 0.06,
            "rear_prob_keep_thr": 0.55,
            "rear_strength_thr": 0.45,
            "pair_cons_thr": float(args.day_straight_pair_cons_thr),
        },
        # Scarce high-risk bucket: stronger rear keep.
        "night+straight_road": {
            "lane_thr": 0.76,
            "margin_thr": 0.54,
            "just_over_eps": 0.08,
            "rear_prob_keep_thr": 0.52,
            "rear_strength_thr": 0.34,
            "pair_cons_thr": 0.60,
        },
        # Mixed bucket: medium conservative.
        "day+intersection": {
            "lane_thr": 0.74,
            "margin_thr": 0.50,
            "just_over_eps": 0.07,
            "rear_prob_keep_thr": 0.56,
            "rear_strength_thr": 0.40,
            "pair_cons_thr": 0.62,
        },
        # Scope-edge other subclasses: default conservative.
        "other_scope_edge": {
            "lane_thr": 0.79,
            "margin_thr": 0.58,
            "just_over_eps": 0.08,
            "rear_prob_keep_thr": 0.50,
            "rear_strength_thr": 0.34,
            "pair_cons_thr": 0.60,
        },
        "other_contextual": {
            "lane_thr": 0.77,
            "margin_thr": 0.56,
            "just_over_eps": 0.08,
            "rear_prob_keep_thr": 0.52,
            "rear_strength_thr": 0.36,
            "pair_cons_thr": 0.61,
        },
        "other_default": {
            "lane_thr": 0.78,
            "margin_thr": 0.57,
            "just_over_eps": 0.08,
            "rear_prob_keep_thr": 0.51,
            "rear_strength_thr": 0.35,
            "pair_cons_thr": 0.60,
        },
        "fallback": {
            "lane_thr": 0.77,
            "margin_thr": 0.56,
            "just_over_eps": 0.08,
            "rear_prob_keep_thr": 0.52,
            "rear_strength_thr": 0.36,
            "pair_cons_thr": 0.61,
        },
    }

    patched_rows = apply_bucket_aware(rows, cfg)

    # v4_refine from incoming scored jsonl uses pred_type_patch
    v4_refine = eval_patch(patched_rows, "pred_type_patch")
    bucket_aware = eval_patch(patched_rows, "pred_type_patch_bucketaware")

    night_rows = [r for r in patched_rows if str(r.get("scene_bucket", "")) == "night+straight_road"]
    other_rows = [r for r in patched_rows if str(r.get("scene_bucket", "")) == "other"]
    ds_rows = [r for r in patched_rows if str(r.get("scene_bucket", "")) == "day+straight_road"]
    ds_lane_fn_rear = [r for r in ds_rows if str(r.get("gt_type", "")) == "lane_change" and str(r.get("pred_type", "")) == "rear_end"]
    ds_rescue_bucketaware = [r for r in ds_lane_fn_rear if str(r.get("pred_type_patch_bucketaware", "")) == "lane_change"]
    ds_rescue_v4 = [r for r in ds_lane_fn_rear if str(r.get("pred_type_patch", "")) == "lane_change"]

    bucket_focus = {
        "night+straight_road": {
            "v4_refine": strict_rear_steal_ratio(night_rows, "pred_type_patch"),
            "bucket_aware": strict_rear_steal_ratio(night_rows, "pred_type_patch_bucketaware"),
            "n": int(len(night_rows)),
        },
        "other": {
            "v4_refine": strict_rear_steal_ratio(other_rows, "pred_type_patch"),
            "bucket_aware": strict_rear_steal_ratio(other_rows, "pred_type_patch_bucketaware"),
            "n": int(len(other_rows)),
        },
        "day+straight_road": {
            "lane_fn_rear_n": int(len(ds_lane_fn_rear)),
            "v4_refine_rescueable_n": int(len(ds_rescue_v4)),
            "bucket_aware_rescueable_n": int(len(ds_rescue_bucketaware)),
        },
    }

    comparison = {
        "overall_rear_steal_ratio": {
            "v4_refine": v4_refine["rear_steal_ratio"],
            "bucket_aware": bucket_aware["rear_steal_ratio"],
            "delta_bucketaware_minus_v4refine": bucket_aware["rear_steal_ratio"] - v4_refine["rear_steal_ratio"],
        },
        "overall_rescueable_total": {
            "v4_refine": v4_refine["rescueable_total"],
            "bucket_aware": bucket_aware["rescueable_total"],
            "delta_bucketaware_minus_v4refine": bucket_aware["rescueable_total"] - v4_refine["rescueable_total"],
        },
        "overall_dLaneR": {
            "v4_refine": v4_refine["delta_metrics"]["lane_recall"],
            "bucket_aware": bucket_aware["delta_metrics"]["lane_recall"],
            "delta_bucketaware_minus_v4refine": bucket_aware["delta_metrics"]["lane_recall"] - v4_refine["delta_metrics"]["lane_recall"],
        },
        "overall_dMacro": {
            "v4_refine": v4_refine["delta_metrics"]["macro_f1"],
            "bucket_aware": bucket_aware["delta_metrics"]["macro_f1"],
            "delta_bucketaware_minus_v4refine": bucket_aware["delta_metrics"]["macro_f1"] - v4_refine["delta_metrics"]["macro_f1"],
        },
    }

    day_straight_rescue_check = (
        None
        if bucket_focus["day+straight_road"]["lane_fn_rear_n"] == 0
        else bucket_focus["day+straight_road"]["bucket_aware_rescueable_n"] > 0
    )

    checks = {
        "rear_not_rebound_vs_v4_refine": bucket_aware["rear_steal_ratio"] <= v4_refine["rear_steal_ratio"],
        "night_rear_not_rebound_vs_v4_refine": bucket_focus["night+straight_road"]["bucket_aware"]["rear_steal_ratio"]
        <= bucket_focus["night+straight_road"]["v4_refine"]["rear_steal_ratio"],
        "other_rear_not_rebound_vs_v4_refine": bucket_focus["other"]["bucket_aware"]["rear_steal_ratio"]
        <= bucket_focus["other"]["v4_refine"]["rear_steal_ratio"],
        "lane_rescue_nonzero": bucket_aware["rescueable_total"] > 0,
        "day_straight_rescue_not_dead": day_straight_rescue_check,
        "dLaneR_positive": bucket_aware["delta_metrics"]["lane_recall"] > 0.0,
        "dMacro_non_negative": bucket_aware["delta_metrics"]["macro_f1"] >= 0.0,
    }

    report = {
        "mode": "exid_bucket_aware_single_variant_diagnostic",
        "constraint_variant_name": "bucket_aware_v1_small_explainable",
        "source_scored_jsonl": str(Path(args.scored_jsonl).resolve()),
        "board_n": int(len(rows)),
        "bucket_aware_config": cfg,
        "v4_refine_eval": v4_refine,
        "bucket_aware_eval": bucket_aware,
        "focus_bucket_metrics": bucket_focus,
        "comparison": comparison,
        "checks": checks,
    }

    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()
    out_patched = Path(args.out_patched_jsonl).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_patched.parent.mkdir(parents=True, exist_ok=True)

    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with out_patched.open("w", encoding="utf-8") as f:
        for r in patched_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    md_lines = [
        "# exiD Bucket-aware Constraint Single Run",
        "",
        "## Overall",
        f"- rear_steal_ratio: v4_refine={v4_refine['rear_steal_ratio']:.6f} -> bucket_aware={bucket_aware['rear_steal_ratio']:.6f}",
        f"- rescueable_total: v4_refine={v4_refine['rescueable_total']} -> bucket_aware={bucket_aware['rescueable_total']}",
        f"- dLaneR: v4_refine={v4_refine['delta_metrics']['lane_recall']:+.6f} -> bucket_aware={bucket_aware['delta_metrics']['lane_recall']:+.6f}",
        f"- dMacro: v4_refine={v4_refine['delta_metrics']['macro_f1']:+.6f} -> bucket_aware={bucket_aware['delta_metrics']['macro_f1']:+.6f}",
        "",
        "## Focus Buckets",
        f"- night+straight rear_steal_ratio: v4_refine={bucket_focus['night+straight_road']['v4_refine']['rear_steal_ratio']:.6f}, bucket_aware={bucket_focus['night+straight_road']['bucket_aware']['rear_steal_ratio']:.6f}",
        f"- other rear_steal_ratio: v4_refine={bucket_focus['other']['v4_refine']['rear_steal_ratio']:.6f}, bucket_aware={bucket_focus['other']['bucket_aware']['rear_steal_ratio']:.6f}",
        f"- day+straight rescueable: v4_refine={bucket_focus['day+straight_road']['v4_refine_rescueable_n']}, bucket_aware={bucket_focus['day+straight_road']['bucket_aware_rescueable_n']}",
        "",
        "## Checks",
    ]
    for k, v in checks.items():
        md_lines.append(f"- {k}: {v}")
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "out_json": str(out_json),
                "out_md": str(out_md),
                "out_patched_jsonl": str(out_patched),
                "overall": {
                    "v4_refine": {
                        "rear_steal_ratio": v4_refine["rear_steal_ratio"],
                        "rescueable_total": v4_refine["rescueable_total"],
                        "dLaneR": v4_refine["delta_metrics"]["lane_recall"],
                        "dMacro": v4_refine["delta_metrics"]["macro_f1"],
                    },
                    "bucket_aware": {
                        "rear_steal_ratio": bucket_aware["rear_steal_ratio"],
                        "rescueable_total": bucket_aware["rescueable_total"],
                        "dLaneR": bucket_aware["delta_metrics"]["lane_recall"],
                        "dMacro": bucket_aware["delta_metrics"]["macro_f1"],
                    },
                },
                "focus": bucket_focus,
                "checks": checks,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
