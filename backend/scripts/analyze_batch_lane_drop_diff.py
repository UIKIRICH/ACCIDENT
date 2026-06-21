import argparse
import json
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List, Tuple

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


def get_gt_map(path: Path) -> Dict[str, Dict[str, Any]]:
    rows = load_jsonl(path)
    m: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            m[sid] = r
    return m


def get_pred_map(path: Path) -> Dict[str, Dict[str, Any]]:
    rows = load_jsonl(path)
    m: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        sid = str(r.get("sample_id", "")).strip()
        if sid:
            m[sid] = r
    return m


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze why batch lane injection caused dLaneR rollback.")
    parser.add_argument("--batch-native-csv", required=True)
    parser.add_argument("--main-native-pre-csv", required=True)
    parser.add_argument("--board-native-152", required=True)
    parser.add_argument("--board-native-30", required=True)
    parser.add_argument("--board-native-24", required=True)
    parser.add_argument("--gt-152", required=True)
    parser.add_argument("--gt-30", required=True)
    parser.add_argument("--gt-24", required=True)
    parser.add_argument("--pre-scored-152", required=True)
    parser.add_argument("--pre-scored-30", required=True)
    parser.add_argument("--pre-scored-24", required=True)
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

    # Category 1 / 3: batch20 profile and feature strength
    batch20 = pd.read_csv(Path(args.batch_native_csv).resolve())
    main_pre = pd.read_csv(Path(args.main_native_pre_csv).resolve())
    main_pre_lane = main_pre[main_pre["accident_type"] == "lane_change"].copy()

    batch20["scene_tags_list"] = batch20["scene_tags"].apply(lambda s: json.loads(s) if isinstance(s, str) and s.startswith("[") else [])
    batch20["scene_bucket"] = batch20["scene_tags_list"].apply(scene_bucket)

    cat1 = {
        "n_batch20": int(len(batch20)),
        "scene_bucket_dist": batch20["scene_bucket"].value_counts().to_dict(),
        "completeness_stats": {
            "bridged_coverage": stats_dict(batch20["bridged_coverage"].tolist()),
            "bridged_continuity": stats_dict(batch20["bridged_continuity"].tolist()),
            "pair_count": stats_dict(batch20["pair_count"].tolist()),
            "feat_pair_temporal_consistency": stats_dict(batch20["feat_pair_temporal_consistency"].tolist()),
        },
    }

    focus_feats = [
        "feat_lane_behavior_strength",
        "feat_lateral_change",
        "feat_lane_relation",
        "feat_pair_temporal_consistency",
    ]
    cat3: Dict[str, Any] = {}
    for f in focus_feats:
        bvals = batch20[f].tolist()
        pvals = main_pre_lane[f].tolist()
        p25 = float(pd.Series(pvals).quantile(0.25)) if pvals else 0.0
        p50 = float(pd.Series(pvals).quantile(0.50)) if pvals else 0.0
        cat3[f] = {
            "batch20": stats_dict(bvals),
            "main_pre_lane": stats_dict(pvals),
            "delta_mean_batch20_minus_prelane": float(mean(bvals) - mean(pvals)) if bvals and pvals else 0.0,
            "batch20_low_ratio_lt_prelane_p25": float(sum(1 for x in bvals if x < p25) / len(bvals)) if bvals else 0.0,
            "batch20_ge_prelane_p50_ratio": float(sum(1 for x in bvals if x >= p50) / len(bvals)) if bvals else 0.0,
        }

    # Category 2 / 4: boundary shift and rescue cluster mismatch
    boards = [
        {
            "name": "board152",
            "gt": Path(args.gt_152).resolve(),
            "pre_scored": Path(args.pre_scored_152).resolve(),
            "pre_patch": Path(args.pre_patch_152).resolve(),
            "post_patch": Path(args.post_patch_152).resolve(),
            "native": Path(args.board_native_152).resolve(),
        },
        {
            "name": "board30",
            "gt": Path(args.gt_30).resolve(),
            "pre_scored": Path(args.pre_scored_30).resolve(),
            "pre_patch": Path(args.pre_patch_30).resolve(),
            "post_patch": Path(args.post_patch_30).resolve(),
            "native": Path(args.board_native_30).resolve(),
        },
        {
            "name": "board24",
            "gt": Path(args.gt_24).resolve(),
            "pre_scored": Path(args.pre_scored_24).resolve(),
            "pre_patch": Path(args.pre_patch_24).resolve(),
            "post_patch": Path(args.post_patch_24).resolve(),
            "native": Path(args.board_native_24).resolve(),
        },
    ]

    lane_fn_diff_rows: List[Dict[str, Any]] = []
    rescueable_pre_ids: List[Tuple[str, str]] = []  # (board,sid)

    for b in boards:
        gt_map = get_gt_map(b["gt"])
        pre_scored = get_pred_map(b["pre_scored"])
        pre_patch = get_pred_map(b["pre_patch"])
        post_patch = get_pred_map(b["post_patch"])

        for sid, g in gt_map.items():
            gt_type = str(g.get("accident_type", "")).strip()
            pb = pre_scored.get(sid)
            pp = pre_patch.get(sid)
            qp = post_patch.get(sid)
            if pb is None or pp is None or qp is None:
                continue
            pred_base = str(pb.get("pred_type", "")).strip()
            if not (gt_type == "lane_change" and pred_base == "rear_end"):
                continue

            pre_lane = safe_float(pp.get("native_bridge_lane_score", 0.0))
            pre_rear = safe_float(pp.get("native_bridge_rear_score", 0.0))
            post_lane = safe_float(qp.get("native_bridge_lane_score", 0.0))
            post_rear = safe_float(qp.get("native_bridge_rear_score", 0.0))
            pre_margin = pre_lane - pre_rear
            post_margin = post_lane - post_rear
            pre_rw = bool(pp.get("native_bridge_rewrite_applied", False))
            post_rw = bool(qp.get("native_bridge_rewrite_applied", False))
            tags = g.get("scene_tags", []) or []

            if pre_rw:
                rescueable_pre_ids.append((b["name"], sid))

            if pre_rw and (not post_rw):
                shift = "dropped_rescue"
            elif (not pre_rw) and post_rw:
                shift = "gained_rescue"
            else:
                shift = "unchanged"

            lane_fn_diff_rows.append(
                {
                    "board": b["name"],
                    "sample_id": sid,
                    "video": g.get("video", ""),
                    "scene_bucket": scene_bucket(tags),
                    "scene_tags": json.dumps(tags, ensure_ascii=False),
                    "pre_lane_score": pre_lane,
                    "post_lane_score": post_lane,
                    "delta_lane_score": post_lane - pre_lane,
                    "pre_margin": pre_margin,
                    "post_margin": post_margin,
                    "delta_margin": post_margin - pre_margin,
                    "pre_rewrite": pre_rw,
                    "post_rewrite": post_rw,
                    "shift_type": shift,
                }
            )

    lane_fn_df = pd.DataFrame(lane_fn_diff_rows)
    lane_fn_df.sort_values(["shift_type", "board", "delta_margin"], ascending=[True, True, True], inplace=True)
    lane_fn_csv = out_dir / "batch1_lane_fn_boundary_diff_list.csv"
    lane_fn_df.to_csv(lane_fn_csv, index=False, encoding="utf-8-sig")

    cat2 = {
        "lane_fn_pool_n": int(len(lane_fn_df)),
        "pre_rewrite_n": int((lane_fn_df["pre_rewrite"] == True).sum()),
        "post_rewrite_n": int((lane_fn_df["post_rewrite"] == True).sum()),
        "dropped_rescue_n": int((lane_fn_df["shift_type"] == "dropped_rescue").sum()),
        "gained_rescue_n": int((lane_fn_df["shift_type"] == "gained_rescue").sum()),
        "score_dist_pre": {
            "lane_score": stats_dict(lane_fn_df["pre_lane_score"].tolist()),
            "margin": stats_dict(lane_fn_df["pre_margin"].tolist()),
        },
        "score_dist_post": {
            "lane_score": stats_dict(lane_fn_df["post_lane_score"].tolist()),
            "margin": stats_dict(lane_fn_df["post_margin"].tolist()),
        },
        "delta_score_dist": {
            "delta_lane_score": stats_dict(lane_fn_df["delta_lane_score"].tolist()),
            "delta_margin": stats_dict(lane_fn_df["delta_margin"].tolist()),
        },
        "dropped_scene_bucket_dist": lane_fn_df[lane_fn_df["shift_type"] == "dropped_rescue"]["scene_bucket"].value_counts().to_dict(),
    }

    # Category 4: mismatch between batch20 and "rescueable cluster" (pre)
    # Build rescue feature frame from board native csv by sample_id
    rescue_ids = {(bd, sid) for bd, sid in rescueable_pre_ids}
    rescue_feat_rows: List[Dict[str, Any]] = []
    for b in boards:
        bname = b["name"]
        nat = pd.read_csv(b["native"])
        if "scene_tags" in nat.columns:
            nat["scene_tags_list"] = nat["scene_tags"].apply(lambda s: json.loads(s) if isinstance(s, str) and s.startswith("[") else [])
            nat["scene_bucket"] = nat["scene_tags_list"].apply(scene_bucket)
        for _, r in nat.iterrows():
            sid = str(r.get("sample_id", "")).strip()
            if (bname, sid) in rescue_ids:
                rescue_feat_rows.append(dict(r))
    rescue_df = pd.DataFrame(rescue_feat_rows)

    mismatch: Dict[str, Any] = {
        "rescue_cluster_n_pre": int(len(rescue_df)),
        "batch20_n": int(len(batch20)),
        "scene_bucket_rescue_pre": rescue_df["scene_bucket"].value_counts().to_dict() if len(rescue_df) else {},
        "scene_bucket_batch20": batch20["scene_bucket"].value_counts().to_dict(),
    }
    feat_cmp: Dict[str, Any] = {}
    if len(rescue_df):
        for f in focus_feats:
            rv = rescue_df[f].tolist()
            bv = batch20[f].tolist()
            feat_cmp[f] = {
                "rescue_pre": stats_dict(rv),
                "batch20": stats_dict(bv),
                "delta_mean_batch20_minus_rescue_pre": float(mean(bv) - mean(rv)) if bv and rv else 0.0,
            }
    mismatch["feature_compare"] = feat_cmp

    # Save JSON
    final = {
        "category1_batch20_type_profile": cat1,
        "category2_boundary_conservative_shift": cat2,
        "category3_batch20_native_strength": cat3,
        "category4_batch20_vs_rescue_cluster_mismatch": mismatch,
        "artifacts": {
            "lane_fn_diff_csv": str(lane_fn_csv),
        },
    }
    json_out = out_dir / "BATCH1_LANER_ROLLBACK_DIFF_AUDIT_2026-05-08.json"
    json_out.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save markdown board
    md: List[str] = []
    md.append("# Batch1 LaneR Rollback Diff Audit")
    md.append("")
    md.append("## Category 1: What kind of lane are these 20?")
    md.append(f"- batch20 size: {cat1['n_batch20']}")
    md.append(f"- scene bucket dist: {cat1['scene_bucket_dist']}")
    md.append(f"- completeness (feat_pair_temporal_consistency mean): {cat1['completeness_stats']['feat_pair_temporal_consistency']['mean']:.6f}")
    md.append("")
    md.append("## Category 2: Did boundary become more conservative?")
    md.append(f"- lane FN pool n: {cat2['lane_fn_pool_n']}")
    md.append(f"- pre rescueable n: {cat2['pre_rewrite_n']}")
    md.append(f"- post rescueable n: {cat2['post_rewrite_n']}")
    md.append(f"- dropped rescue n: {cat2['dropped_rescue_n']}")
    md.append(f"- gained rescue n: {cat2['gained_rescue_n']}")
    md.append(f"- pre margin mean -> post margin mean: {cat2['score_dist_pre']['margin']['mean']:.6f} -> {cat2['score_dist_post']['margin']['mean']:.6f}")
    md.append(f"- dropped scene bucket dist: {cat2['dropped_scene_bucket_dist']}")
    md.append("")
    md.append("## Category 3: Are these 20 strong in native evidence?")
    for f in focus_feats:
        x = cat3[f]
        md.append(
            f"- {f}: batch20 mean={x['batch20']['mean']:.6f}, pre-lane mean={x['main_pre_lane']['mean']:.6f}, delta={x['delta_mean_batch20_minus_prelane']:+.6f}, low_ratio(<pre_p25)={x['batch20_low_ratio_lt_prelane_p25']:.2%}"
        )
    md.append("")
    md.append("## Category 4: Are batch20 and rescue cluster mismatched?")
    md.append(f"- rescue cluster n (pre): {mismatch['rescue_cluster_n_pre']}")
    md.append(f"- rescue scene dist: {mismatch['scene_bucket_rescue_pre']}")
    md.append(f"- batch20 scene dist: {mismatch['scene_bucket_batch20']}")
    if feat_cmp:
        for f in focus_feats:
            y = feat_cmp[f]
            md.append(
                f"- {f}: batch20 vs rescue mean delta = {y['delta_mean_batch20_minus_rescue_pre']:+.6f}"
            )
    md.append("")
    md.append("## Artifact")
    md.append(f"- lane FN sample-level diff list: `{lane_fn_csv}`")
    md.append("")
    md_out = out_dir / "BATCH1_LANER_ROLLBACK_DIFF_AUDIT_2026-05-08.md"
    md_out.write_text("\n".join(md) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "json": str(json_out),
                "md": str(md_out),
                "lane_fn_diff_csv": str(lane_fn_csv),
                "dropped_rescue_n": cat2["dropped_rescue_n"],
                "pre_rewrite_n": cat2["pre_rewrite_n"],
                "post_rewrite_n": cat2["post_rewrite_n"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
