#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path
from typing import Any, Dict, List


VALID_POLICIES = {
    "BASE_ONLY",
    "DETERMINISTIC_FUSION",
    "TS3",
    "TS2",
    "BA2",
}


def read_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def as_float(x: Any) -> float:
    try:
        if x is None:
            return float("nan")
        s = str(x).strip()
        if s == "":
            return float("nan")
        return float(s)
    except Exception:
        return float("nan")


def derive_action(policy: str, row: Dict[str, Any]) -> Dict[str, str]:
    gt = str(row.get("gt_type", "")).strip()
    base = str(row.get("baseline_pred", "")).strip()
    fus = str(row.get("fusion_pred", "")).strip()

    if policy == "BASE_ONLY":
        action = "KEEP_BASELINE"
        final_pred = base
        rear_guard_flag = "NA"
        boost_gate_flag = "NA"
        conflict_flag = "NA"
        uncertain_conflict_flag = "NA"
    elif policy == "DETERMINISTIC_FUSION":
        action = "FUSION_BOOST"
        final_pred = fus
        rear_guard_flag = "NA"
        boost_gate_flag = "NA"
        conflict_flag = "NA"
        uncertain_conflict_flag = "NA"
    else:
        raise RuntimeError(
            f"Policy {policy} requires canonical locked policy logic file. "
            "This script intentionally does not guess TS3/TS2/BA2 behavior."
        )

    is_deferred = "1" if action == "DEFER" else "0"
    is_auto = "0" if action == "DEFER" else "1"
    is_rear_gt = "1" if gt == "rear_end" else "0"
    is_lane_gt = "1" if gt == "lane_change" else "0"
    is_turn_gt = "1" if gt == "turn_conflict" else "0"
    is_rear_miss = "1" if (gt == "rear_end" and final_pred != "rear_end") else "0"
    is_wrong_auto = "1" if (action != "DEFER" and final_pred != gt) else "0"
    baseline_correct = "1" if base == gt else "0"
    fusion_correct = "1" if fus == gt else "0"
    final_correct = "1" if final_pred == gt else "0"

    return {
        "policy_name": policy,
        "action": action,
        "final_pred": final_pred,
        "is_deferred": is_deferred,
        "is_auto": is_auto,
        "is_rear_gt": is_rear_gt,
        "is_lane_gt": is_lane_gt,
        "is_turn_gt": is_turn_gt,
        "is_rear_miss": is_rear_miss,
        "is_wrong_auto": is_wrong_auto,
        "baseline_correct": baseline_correct,
        "fusion_correct": fusion_correct,
        "final_correct": final_correct,
        "rear_guard_flag": rear_guard_flag,
        "boost_gate_flag": boost_gate_flag,
        "conflict_flag": conflict_flag,
        "uncertain_conflict_flag": uncertain_conflict_flag,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild canonical action-level trace from canonical base table under locked policy constraints."
    )
    parser.add_argument("--base_table", required=True, help="Path to canonical_416_base_table.csv (or compatible base table).")
    parser.add_argument("--policy", required=True, help="One of BASE_ONLY, DETERMINISTIC_FUSION, TS3, TS2, BA2.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    args = parser.parse_args()

    policy = str(args.policy).strip()
    if policy not in VALID_POLICIES:
        raise SystemExit(f"Unsupported policy: {policy}. Expected one of {sorted(VALID_POLICIES)}")

    base_table = Path(args.base_table).resolve()
    out_csv = Path(args.output).resolve()

    rows = read_csv(base_table)
    if not rows:
        raise SystemExit(f"Empty base table: {base_table}")

    out_rows: List[Dict[str, Any]] = []
    for r in rows:
        core = {
            "sample_id": str(r.get("sample_id", "")).strip(),
            "case_id": str(r.get("case_id", "")).strip() or str(r.get("sample_id", "")).strip(),
            "board_id": str(r.get("board_id", "")).strip(),
            "bucket_id": str(r.get("bucket_id", "")).strip(),
            "source_id": str(r.get("source_id", "")).strip(),
            "gt_type": str(r.get("gt_type", "")).strip(),
            "baseline_pred": str(r.get("baseline_pred", "")).strip(),
            "fusion_pred": str(r.get("fusion_pred", "")).strip(),
            "baseline_score_rear": r.get("baseline_score_rear", ""),
            "fusion_score_rear": r.get("fusion_score_rear", ""),
            "fusion_score_lane": r.get("fusion_score_lane", ""),
            "fusion_score_turn": r.get("fusion_score_turn", ""),
            "fusion_score_nonrear": r.get("fusion_score_nonrear", ""),
            "margin_nonrear_minus_rear": r.get("margin_nonrear_minus_rear", ""),
        }
        derived = derive_action(policy, r)
        core.update(derived)
        out_rows.append(core)

    fields = [
        "sample_id",
        "case_id",
        "board_id",
        "bucket_id",
        "source_id",
        "gt_type",
        "baseline_pred",
        "fusion_pred",
        "policy_name",
        "action",
        "final_pred",
        "is_deferred",
        "is_auto",
        "is_rear_gt",
        "is_lane_gt",
        "is_turn_gt",
        "is_rear_miss",
        "is_wrong_auto",
        "baseline_correct",
        "fusion_correct",
        "final_correct",
        "baseline_score_rear",
        "fusion_score_rear",
        "fusion_score_lane",
        "fusion_score_turn",
        "fusion_score_nonrear",
        "margin_nonrear_minus_rear",
        "rear_guard_flag",
        "boost_gate_flag",
        "conflict_flag",
        "uncertain_conflict_flag",
    ]
    write_csv(out_csv, out_rows, fields)
    print(str(out_csv))
    print(f"rows={len(out_rows)} policy={policy}")


if __name__ == "__main__":
    main()
