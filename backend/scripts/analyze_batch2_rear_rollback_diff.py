import argparse
import ast
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


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


def safe_float(v: Any, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def normalize_video(v: Any) -> str:
    return str(v).strip().replace("\\", "/")


def parse_scene_tags(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    if v is None:
        return []
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return []
        try:
            x = json.loads(s)
            if isinstance(x, list):
                return [str(t).strip() for t in x if str(t).strip()]
        except Exception:
            pass
        try:
            x = ast.literal_eval(s)
            if isinstance(x, list):
                return [str(t).strip() for t in x if str(t).strip()]
        except Exception:
            pass
        return [s]
    return []


def scene_bucket(tags: List[str]) -> str:
    s = {str(x).strip() for x in tags if str(x).strip()}
    if "day" in s and "straight_road" in s:
        return "day+straight_road"
    if "day" in s and "intersection" in s:
        return "day+intersection"
    if "night" in s and "straight_road" in s:
        return "night+straight_road"
    if "night" in s and "intersection" in s:
        return "night+intersection"
    return "other"


def stats_dict(vals: List[float]) -> Dict[str, float]:
    if not vals:
        return {"n": 0, "mean": 0.0, "median": 0.0, "q25": 0.0, "q75": 0.0, "min": 0.0, "max": 0.0}
    s = pd.Series(vals)
    return {
        "n": int(len(vals)),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "q25": float(s.quantile(0.25)),
        "q75": float(s.quantile(0.75)),
        "min": float(s.min()),
        "max": float(s.max()),
    }


def get_map_by_sid(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            out[sid] = r
    return out


def get_map_by_video(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        vid = normalize_video(r.get("video", ""))
        if vid:
            out[vid] = r
    return out


def value_counts(d: pd.Series) -> Dict[str, int]:
    if len(d) == 0:
        return {}
    return {str(k): int(v) for k, v in d.value_counts().to_dict().items()}


def ratio(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return float(num / den)


def resolve_scene_bucket_series(df: pd.DataFrame) -> pd.Series:
    if "scene_bucket" in df.columns:
        sb = df["scene_bucket"].astype(str).str.strip()
        good = sb.isin(
            [
                "day+straight_road",
                "day+intersection",
                "night+straight_road",
                "night+intersection",
                "other",
            ]
        )
        if good.all():
            return sb
    tags_s = df.get("scene_tags", pd.Series(["[]"] * len(df)))
    return tags_s.apply(parse_scene_tags).apply(scene_bucket)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch2 rear rollback audit against batch1 (cfgN1 same protocol).")
    parser.add_argument("--batch1-lane-native-csv", required=True)
    parser.add_argument("--batch2-lane-native-csv", required=True)
    parser.add_argument("--board-native-152", required=True)
    parser.add_argument("--board-native-30", required=True)
    parser.add_argument("--board-native-24", required=True)
    parser.add_argument("--gt-152", required=True)
    parser.add_argument("--gt-30", required=True)
    parser.add_argument("--gt-24", required=True)
    parser.add_argument("--pre-patch-152", required=True)
    parser.add_argument("--pre-patch-30", required=True)
    parser.add_argument("--pre-patch-24", required=True)
    parser.add_argument("--post-patch-152", required=True)
    parser.add_argument("--post-patch-30", required=True)
    parser.add_argument("--post-patch-24", required=True)
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    lane_thr = 0.68
    margin_thr = 0.08
    rear_keep_thr = 0.55

    boards = [
        {
            "name": "board152",
            "gt": Path(args.gt_152).resolve(),
            "native": Path(args.board_native_152).resolve(),
            "pre_patch": Path(args.pre_patch_152).resolve(),
            "post_patch": Path(args.post_patch_152).resolve(),
        },
        {
            "name": "board30",
            "gt": Path(args.gt_30).resolve(),
            "native": Path(args.board_native_30).resolve(),
            "pre_patch": Path(args.pre_patch_30).resolve(),
            "post_patch": Path(args.post_patch_30).resolve(),
        },
        {
            "name": "board24",
            "gt": Path(args.gt_24).resolve(),
            "native": Path(args.board_native_24).resolve(),
            "pre_patch": Path(args.pre_patch_24).resolve(),
            "post_patch": Path(args.post_patch_24).resolve(),
        },
    ]

    focus_feats = [
        "feat_lane_behavior_strength",
        "feat_lateral_change",
        "feat_lane_relation",
        "feat_direction_relation",
    ]
    support_feats = [
        "feat_rear_behavior_strength",
        "feat_pair_temporal_consistency",
        "bridged_coverage",
        "bridged_continuity",
    ]

    affected_rows: List[Dict[str, Any]] = []
    rear_pool_rows: List[Dict[str, Any]] = []

    for b in boards:
        gt_rows = load_jsonl(b["gt"])
        pre_rows = load_jsonl(b["pre_patch"])
        post_rows = load_jsonl(b["post_patch"])
        pre_sid = get_map_by_sid(pre_rows)
        pre_vid = get_map_by_video(pre_rows)
        post_sid = get_map_by_sid(post_rows)
        post_vid = get_map_by_video(post_rows)

        nat_df = pd.read_csv(b["native"])
        nat_sid = {
            str(r["sample_id"]).strip(): dict(r)
            for r in nat_df.to_dict(orient="records")
            if str(r.get("sample_id", "")).strip()
        }
        nat_vid = {
            normalize_video(r.get("video", "")): dict(r)
            for r in nat_df.to_dict(orient="records")
            if str(r.get("video", "")).strip()
        }

        for g in gt_rows:
            gt_type = str(g.get("accident_type", "")).strip()
            if gt_type != "rear_end":
                continue
            sid = str(g.get("sample_id", "")).strip()
            vid = normalize_video(g.get("video", ""))
            pre = pre_sid.get(sid) or pre_vid.get(vid)
            post = post_sid.get(sid) or post_vid.get(vid)
            if pre is None or post is None:
                continue

            tags = parse_scene_tags(g.get("scene_tags", []))
            bucket = scene_bucket(tags)

            pre_pred = str(pre.get("pred_type", "")).strip()
            post_pred = str(post.get("pred_type", "")).strip()
            pre_decision = str(pre.get("decision_mode", "")).strip()
            post_decision = str(post.get("decision_mode", "")).strip()

            pre_lane = safe_float(pre.get("native_bridge_lane_score", 0.0))
            pre_rear = safe_float(pre.get("native_bridge_rear_score", 0.0))
            post_lane = safe_float(post.get("native_bridge_lane_score", 0.0))
            post_rear = safe_float(post.get("native_bridge_rear_score", 0.0))
            pre_margin = pre_lane - pre_rear
            post_margin = post_lane - post_rear

            pre_rw = bool(pre.get("native_bridge_rewrite_applied", False))
            post_rw = bool(post.get("native_bridge_rewrite_applied", False))

            tp_pre = pre.get("type_probs", {}) or {}
            pr = safe_float(tp_pre.get("rear_end", 0.0))
            pl = safe_float(tp_pre.get("lane_change", 0.0))
            pt = safe_float(tp_pre.get("turn_conflict", 0.0))
            gap = abs(pr - pl)

            nat = nat_sid.get(sid) or nat_vid.get(vid) or {}

            pool_row = {
                "board": b["name"],
                "sample_id": sid,
                "video": g.get("video", ""),
                "scene_bucket": bucket,
                "scene_tags": json.dumps(tags, ensure_ascii=False),
                "pre_pred_type": pre_pred,
                "post_pred_type": post_pred,
                "pre_lane_score": pre_lane,
                "post_lane_score": post_lane,
                "pre_margin": pre_margin,
                "post_margin": post_margin,
                "pre_rewrite": pre_rw,
                "post_rewrite": post_rw,
                "pre_decision_mode": pre_decision,
                "post_decision_mode": post_decision,
            }
            rear_pool_rows.append(pool_row)

            # "batch1 still stable -> batch2 starts affected"
            if not (pre_pred == "rear_end" and post_pred != "rear_end"):
                continue

            row = dict(pool_row)
            row["shift_type"] = f"rear_to_{post_pred}" if post_pred else "rear_to_unknown"
            row["is_rear_to_lane"] = bool(post_pred == "lane_change")
            row["delta_lane_score"] = post_lane - pre_lane
            row["delta_margin"] = post_margin - pre_margin
            row["pre_lane_thr_hit"] = bool(pre_lane >= lane_thr)
            row["post_lane_thr_hit"] = bool(post_lane >= lane_thr)
            row["pre_margin_thr_hit"] = bool(pre_margin >= margin_thr)
            row["post_margin_thr_hit"] = bool(post_margin >= margin_thr)
            row["rear_keep_pre"] = bool(pre_decision == "rear_guard_override" and pr >= rear_keep_thr)
            row["rear_keep_post"] = bool(post_decision == "rear_guard_override" and pr >= rear_keep_thr)
            row["prob_rear"] = pr
            row["prob_lane"] = pl
            row["prob_turn"] = pt
            row["prob_gap_abs"] = gap

            for f in focus_feats + support_feats:
                row[f] = safe_float(nat.get(f, 0.0))
            affected_rows.append(row)

    affected_df = pd.DataFrame(affected_rows)
    rear_pool_df = pd.DataFrame(rear_pool_rows)
    if len(affected_df):
        affected_df = affected_df.sort_values(
            ["board", "scene_bucket", "delta_margin", "delta_lane_score"],
            ascending=[True, True, False, False],
        ).reset_index(drop=True)

    affected_csv = out_dir / "batch2_rear_rollback_affected_samples.csv"
    pool_csv = out_dir / "batch2_rear_pool_samples.csv"
    affected_df.to_csv(affected_csv, index=False, encoding="utf-8-sig")
    rear_pool_df.to_csv(pool_csv, index=False, encoding="utf-8-sig")

    # Category 1: which rear samples were pushed to lane / patterns
    pre_stable_pool = rear_pool_df[rear_pool_df["pre_pred_type"] == "rear_end"].copy() if len(rear_pool_df) else pd.DataFrame()
    scene_risk_rows: List[Dict[str, Any]] = []
    if len(pre_stable_pool):
        for sb, g in pre_stable_pool.groupby("scene_bucket"):
            den = int(len(g))
            num = int(len(g[g["post_pred_type"] != "rear_end"]))
            scene_risk_rows.append(
                {
                    "scene_bucket": str(sb),
                    "pre_stable_rear_n": den,
                    "batch2_affected_n": num,
                    "affected_rate": ratio(num, den),
                }
            )
    scene_risk_df = pd.DataFrame(scene_risk_rows).sort_values("affected_rate", ascending=False) if scene_risk_rows else pd.DataFrame()
    scene_risk_csv = out_dir / "batch2_rear_scene_risk_rates.csv"
    scene_risk_df.to_csv(scene_risk_csv, index=False, encoding="utf-8-sig")

    cat1 = {
        "rear_gt_total_matched": int(len(rear_pool_df)),
        "pre_stable_rear_n": int(len(pre_stable_pool)),
        "batch2_newly_affected_n": int(len(affected_df)),
        "rear_to_lane_n": int(affected_df["is_rear_to_lane"].sum()) if len(affected_df) else 0,
        "shift_type_dist": value_counts(affected_df["shift_type"]) if len(affected_df) else {},
        "board_dist": value_counts(affected_df["board"]) if len(affected_df) else {},
        "scene_bucket_dist": value_counts(affected_df["scene_bucket"]) if len(affected_df) else {},
        "pre_decision_mode_dist": value_counts(affected_df["pre_decision_mode"]) if len(affected_df) else {},
        "post_decision_mode_dist": value_counts(affected_df["post_decision_mode"]) if len(affected_df) else {},
        "score_shift": {
            "pre_lane_score": stats_dict(affected_df["pre_lane_score"].tolist()) if len(affected_df) else stats_dict([]),
            "post_lane_score": stats_dict(affected_df["post_lane_score"].tolist()) if len(affected_df) else stats_dict([]),
            "pre_margin": stats_dict(affected_df["pre_margin"].tolist()) if len(affected_df) else stats_dict([]),
            "post_margin": stats_dict(affected_df["post_margin"].tolist()) if len(affected_df) else stats_dict([]),
            "delta_lane_score": stats_dict(affected_df["delta_lane_score"].tolist()) if len(affected_df) else stats_dict([]),
            "delta_margin": stats_dict(affected_df["delta_margin"].tolist()) if len(affected_df) else stats_dict([]),
        },
        "rule_crossing": {
            "pre_lane_thr_hit_n": int(affected_df["pre_lane_thr_hit"].sum()) if len(affected_df) else 0,
            "post_lane_thr_hit_n": int(affected_df["post_lane_thr_hit"].sum()) if len(affected_df) else 0,
            "pre_margin_thr_hit_n": int(affected_df["pre_margin_thr_hit"].sum()) if len(affected_df) else 0,
            "post_margin_thr_hit_n": int(affected_df["post_margin_thr_hit"].sum()) if len(affected_df) else 0,
            "rear_keep_pre_n": int(affected_df["rear_keep_pre"].sum()) if len(affected_df) else 0,
            "rear_keep_post_n": int(affected_df["rear_keep_post"].sum()) if len(affected_df) else 0,
        },
        "scene_risk_rates_over_pre_stable": scene_risk_df.to_dict(orient="records"),
    }

    # Category 2: which batch2 lane features likely overlap and hurt rear
    b1 = pd.read_csv(Path(args.batch1_lane_native_csv).resolve())
    b2 = pd.read_csv(Path(args.batch2_lane_native_csv).resolve())
    b1["scene_bucket"] = resolve_scene_bucket_series(b1)
    b2["scene_bucket"] = resolve_scene_bucket_series(b2)

    cat2_features: Dict[str, Any] = {}
    for f in focus_feats:
        b1v = pd.to_numeric(b1[f], errors="coerce").fillna(0.0).tolist() if f in b1.columns else []
        b2v = pd.to_numeric(b2[f], errors="coerce").fillna(0.0).tolist() if f in b2.columns else []
        rv = pd.to_numeric(affected_df[f], errors="coerce").fillna(0.0).tolist() if len(affected_df) and f in affected_df.columns else []
        b2s = pd.Series(b2v) if b2v else pd.Series(dtype="float64")
        p50 = float(b2s.quantile(0.5)) if len(b2s) else 0.0
        p75 = float(b2s.quantile(0.75)) if len(b2s) else 0.0
        cat2_features[f] = {
            "batch1_lane20": stats_dict(b1v),
            "batch2_lane20": stats_dict(b2v),
            "rear_affected": stats_dict(rv),
            "delta_mean_batch2_minus_batch1": float(mean(b2v) - mean(b1v)) if b1v and b2v else 0.0,
            "rear_affected_ge_batch2_p50_ratio": ratio(sum(1 for x in rv if x >= p50), len(rv)) if rv else 0.0,
            "rear_affected_ge_batch2_p75_ratio": ratio(sum(1 for x in rv if x >= p75), len(rv)) if rv else 0.0,
            "batch2_p50": p50,
            "batch2_p75": p75,
        }

    cat2 = {
        "batch1_scene_bucket_dist": value_counts(b1["scene_bucket"]) if len(b1) else {},
        "batch2_scene_bucket_dist": value_counts(b2["scene_bucket"]) if len(b2) else {},
        "focus_feature_compare": cat2_features,
    }

    # Category 3: does day+intersection addition correlate with rear risk
    b1_n = int(len(b1))
    b2_n = int(len(b2))
    b1_day_inter = int((b1["scene_bucket"] == "day+intersection").sum()) if len(b1) else 0
    b2_day_inter = int((b2["scene_bucket"] == "day+intersection").sum()) if len(b2) else 0
    aff_day_inter = int((affected_df["scene_bucket"] == "day+intersection").sum()) if len(affected_df) else 0
    aff_day_straight = int((affected_df["scene_bucket"] == "day+straight_road").sum()) if len(affected_df) else 0

    pre_stable_day_inter = 0
    pre_stable_day_straight = 0
    if len(pre_stable_pool):
        pre_stable_day_inter = int((pre_stable_pool["scene_bucket"] == "day+intersection").sum())
        pre_stable_day_straight = int((pre_stable_pool["scene_bucket"] == "day+straight_road").sum())

    cat3 = {
        "batch_lane_scene_shift": {
            "batch1_n": b1_n,
            "batch2_n": b2_n,
            "batch1_day_intersection_n": b1_day_inter,
            "batch2_day_intersection_n": b2_day_inter,
            "batch1_day_intersection_ratio": ratio(b1_day_inter, b1_n),
            "batch2_day_intersection_ratio": ratio(b2_day_inter, b2_n),
            "delta_day_intersection_ratio": ratio(b2_day_inter, b2_n) - ratio(b1_day_inter, b1_n),
        },
        "rear_affected_scene_focus": {
            "affected_day_intersection_n": aff_day_inter,
            "affected_day_straight_n": aff_day_straight,
            "affected_day_intersection_ratio": ratio(aff_day_inter, len(affected_df)),
            "affected_day_straight_ratio": ratio(aff_day_straight, len(affected_df)),
        },
        "scene_specific_risk_over_pre_stable": {
            "day_intersection_pre_stable_rear_n": pre_stable_day_inter,
            "day_intersection_affected_n": aff_day_inter,
            "day_intersection_affected_rate": ratio(aff_day_inter, pre_stable_day_inter),
            "day_straight_pre_stable_rear_n": pre_stable_day_straight,
            "day_straight_affected_n": aff_day_straight,
            "day_straight_affected_rate": ratio(aff_day_straight, pre_stable_day_straight),
        },
    }

    final = {
        "category1_rear_newly_affected_pattern": cat1,
        "category2_batch2_feature_overlap_risk": cat2,
        "category3_day_intersection_risk_check": cat3,
        "artifacts": {
            "affected_samples_csv": str(affected_csv),
            "rear_pool_csv": str(pool_csv),
            "scene_risk_csv": str(scene_risk_csv),
        },
    }

    json_out = out_dir / "BATCH2_REAR_ROLLBACK_DIFF_AUDIT_2026-05-08.json"
    md_out = out_dir / "BATCH2_REAR_ROLLBACK_DIFF_AUDIT_2026-05-08.md"
    json_out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    md: List[str] = []
    md.append("# Batch2 Rear Rollback Diff Audit")
    md.append("")
    md.append("## Category 1: Which rear samples became affected in batch2?")
    md.append(f"- rear_gt_total_matched: {cat1['rear_gt_total_matched']}")
    md.append(f"- pre_stable_rear_n: {cat1['pre_stable_rear_n']}")
    md.append(f"- batch2_newly_affected_n: {cat1['batch2_newly_affected_n']}")
    md.append(f"- rear_to_lane_n: {cat1['rear_to_lane_n']}")
    md.append(f"- scene_bucket_dist: {cat1['scene_bucket_dist']}")
    md.append(f"- pre_decision_mode_dist: {cat1['pre_decision_mode_dist']}")
    md.append(f"- post_decision_mode_dist: {cat1['post_decision_mode_dist']}")
    md.append(
        f"- pre_margin_mean -> post_margin_mean: {cat1['score_shift']['pre_margin']['mean']:.6f} -> {cat1['score_shift']['post_margin']['mean']:.6f}"
    )
    md.append("")
    md.append("## Category 2: Which batch2 lane features may overlap and hurt rear?")
    md.append(f"- batch1_scene_bucket_dist: {cat2['batch1_scene_bucket_dist']}")
    md.append(f"- batch2_scene_bucket_dist: {cat2['batch2_scene_bucket_dist']}")
    for f in focus_feats:
        x = cat2["focus_feature_compare"][f]
        md.append(
            f"- {f}: batch1_mean={x['batch1_lane20']['mean']:.6f}, batch2_mean={x['batch2_lane20']['mean']:.6f}, delta={x['delta_mean_batch2_minus_batch1']:+.6f}, rear_affected_ge_batch2_p75={x['rear_affected_ge_batch2_p75_ratio']:.2%}"
        )
    md.append("")
    md.append("## Category 3: Did day+intersection increase correlate with rear risk?")
    y = cat3["batch_lane_scene_shift"]
    z = cat3["scene_specific_risk_over_pre_stable"]
    md.append(
        f"- day+intersection ratio (batch1 -> batch2): {y['batch1_day_intersection_ratio']:.2%} -> {y['batch2_day_intersection_ratio']:.2%} (delta {y['delta_day_intersection_ratio']:+.2%})"
    )
    md.append(
        f"- day+intersection rear affected rate: {z['day_intersection_affected_n']}/{z['day_intersection_pre_stable_rear_n']} = {z['day_intersection_affected_rate']:.2%}"
    )
    md.append(
        f"- day+straight rear affected rate: {z['day_straight_affected_n']}/{z['day_straight_pre_stable_rear_n']} = {z['day_straight_affected_rate']:.2%}"
    )
    md.append("")
    md.append("## Artifacts")
    md.append(f"- affected samples: `{affected_csv}`")
    md.append(f"- rear pool: `{pool_csv}`")
    md.append(f"- scene risk rates: `{scene_risk_csv}`")
    md_out.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "json": str(json_out),
                "md": str(md_out),
                "affected_samples_csv": str(affected_csv),
                "scene_risk_csv": str(scene_risk_csv),
                "newly_affected_n": cat1["batch2_newly_affected_n"],
                "rear_to_lane_n": cat1["rear_to_lane_n"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
