import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set


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


def flatten_pred_fields(rows: List[Dict[str, Any]]) -> Set[str]:
    out: Set[str] = set()
    tp_keys: Set[str] = set()
    for r in rows:
        out.update(r.keys())
        tp = r.get("type_probs", {})
        if isinstance(tp, dict):
            tp_keys.update(tp.keys())
    for k in sorted(tp_keys):
        out.add(f"type_probs.{k}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build A/B/C feature alignment report for highD->current boards.")
    parser.add_argument("--pred-152", required=True)
    parser.add_argument("--pred-30", required=True)
    parser.add_argument("--pred-24", required=True)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args()

    pred_rows = []
    for p in [args.pred_152, args.pred_30, args.pred_24]:
        pred_rows.extend(load_jsonl(Path(p).resolve()))
    b_fields = sorted(flatten_pred_fields(pred_rows))

    # A: real features used by highD experts (from train_highd_binary_experts.py)
    a_features = [
        "duration_frames",
        "mean_x_velocity",
        "max_abs_y_velocity",
        "num_lane_changes_meta",
        "lane_change_count_track",
        "driving_direction",
        "min_ttc_eff_capped",
        "min_thw_eff_capped",
        "min_dhw_eff_capped",
        "ttc_missing",
        "thw_missing",
        "dhw_missing",
        "is_car",
        "is_truck",
    ]

    # C: manual alignment judgement based on actual board fields
    align_rows: List[Dict[str, Any]] = [
        {
            "a_feature": "duration_frames",
            "semantic": "轨迹持续帧数/时长",
            "b_candidates": ["pred_onset_time", "pred_impact_time", "pred_post_time", "keyframe_times"],
            "status": "approx_only",
            "note": "可弱近似为事件时间跨度，但不是车辆轨迹时长。",
        },
        {
            "a_feature": "mean_x_velocity",
            "semantic": "纵向速度均值",
            "b_candidates": [],
            "status": "missing",
            "note": "三板无显式速度字段。",
        },
        {
            "a_feature": "max_abs_y_velocity",
            "semantic": "横向速度强度",
            "b_candidates": ["type_probs.lane_change"],
            "status": "approx_only",
            "note": "只能用 lane 概率间接代理，缺真实横向运动量。",
        },
        {
            "a_feature": "num_lane_changes_meta",
            "semantic": "车道变化次数",
            "b_candidates": ["type_probs.lane_change", "rear_guard_applied"],
            "status": "approx_only",
            "note": "没有显式换道计数，只能概率侧近似。",
        },
        {
            "a_feature": "lane_change_count_track",
            "semantic": "轨迹检测到的换道次数",
            "b_candidates": ["type_probs.lane_change"],
            "status": "approx_only",
            "note": "同上，缺轨迹级换道证据。",
        },
        {
            "a_feature": "driving_direction",
            "semantic": "同向/逆向主导方向",
            "b_candidates": [],
            "status": "missing",
            "note": "三板无方向信息。",
        },
        {
            "a_feature": "min_ttc_eff_capped",
            "semantic": "最小 TTC（接近风险）",
            "b_candidates": ["risk_score", "lead_time_sec", "type_probs.rear_end"],
            "status": "approx_only",
            "note": "风险分可弱代理 TTC，但不可反推真实最小TTC。",
        },
        {
            "a_feature": "min_thw_eff_capped",
            "semantic": "最小 THW（车头时距）",
            "b_candidates": ["risk_score", "lead_time_sec", "type_probs.rear_end"],
            "status": "approx_only",
            "note": "同上，仅弱代理。",
        },
        {
            "a_feature": "min_dhw_eff_capped",
            "semantic": "最小 DHW（车间距）",
            "b_candidates": ["risk_score", "type_probs.rear_end"],
            "status": "approx_only",
            "note": "无显式距离字段。",
        },
        {
            "a_feature": "ttc_missing",
            "semantic": "TTC 缺失标记",
            "b_candidates": [],
            "status": "missing",
            "note": "三板无TTC原字段，无法判缺失。",
        },
        {
            "a_feature": "thw_missing",
            "semantic": "THW 缺失标记",
            "b_candidates": [],
            "status": "missing",
            "note": "同上。",
        },
        {
            "a_feature": "dhw_missing",
            "semantic": "DHW 缺失标记",
            "b_candidates": [],
            "status": "missing",
            "note": "同上。",
        },
        {
            "a_feature": "is_car",
            "semantic": "车辆类型-小车",
            "b_candidates": [],
            "status": "missing",
            "note": "三板无 vehicle class 字段。",
        },
        {
            "a_feature": "is_truck",
            "semantic": "车辆类型-卡车",
            "b_candidates": [],
            "status": "missing",
            "note": "三板无 vehicle class 字段。",
        },
    ]

    n_direct = sum(1 for x in align_rows if x["status"] == "direct_shared")
    n_approx = sum(1 for x in align_rows if x["status"] == "approx_only")
    n_missing = sum(1 for x in align_rows if x["status"] == "missing")
    n_total = len(align_rows)

    report = {
        "summary": {
            "n_A_features": n_total,
            "direct_shared": n_direct,
            "approx_only": n_approx,
            "missing": n_missing,
            "direct_ratio": n_direct / n_total if n_total else 0.0,
            "approx_or_better_ratio": (n_direct + n_approx) / n_total if n_total else 0.0,
            "bridge_fullness_score": (n_direct + 0.5 * n_approx) / n_total if n_total else 0.0,
        },
        "A_highd_expert_features": a_features,
        "B_current_board_fields": b_fields,
        "C_alignment_table": align_rows,
        "diagnosis": {
            "root_cause": "input_space_mismatch",
            "conclusion": "highD expert learns well in trajectory space, but current 152+30+24 prediction rows do not carry that space; score backfill degrades to proxy-only.",
            "implication": "Need shared-feature bridge before any meaningful transfer.",
        },
    }

    out_json = Path(args.out_json).resolve()
    out_md = Path(args.out_md).resolve()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: List[str] = []
    lines.append("# highD -> 152+30+24 Feature Alignment Audit")
    lines.append("")
    s = report["summary"]
    lines.append("## Summary")
    lines.append(f"- A特征总数: {s['n_A_features']}")
    lines.append(f"- 直接共享: {s['direct_shared']}")
    lines.append(f"- 可近似映射: {s['approx_only']}")
    lines.append(f"- 完全缺失: {s['missing']}")
    lines.append(f"- bridge_fullness_score: {s['bridge_fullness_score']:.4f}")
    lines.append("")
    lines.append("## A/B/C Alignment Table")
    lines.append("")
    lines.append("| A(highD expert feature) | 语义 | B候选字段 | 判定 | 说明 |")
    lines.append("|---|---|---|---|---|")
    for r in align_rows:
        b = ", ".join(r["b_candidates"]) if r["b_candidates"] else "(none)"
        lines.append(f"| {r['a_feature']} | {r['semantic']} | {b} | {r['status']} | {r['note']} |")
    lines.append("")
    lines.append("## Diagnosis")
    lines.append("")
    lines.append(f"- root_cause: {report['diagnosis']['root_cause']}")
    lines.append(f"- conclusion: {report['diagnosis']['conclusion']}")
    lines.append(f"- implication: {report['diagnosis']['implication']}")
    lines.append("")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"out_json": str(out_json), "out_md": str(out_md), "summary": s}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
