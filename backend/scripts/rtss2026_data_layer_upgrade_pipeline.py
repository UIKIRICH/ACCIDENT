#!/usr/bin/env python3
import argparse
import csv
import json
import math
import pickle
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import polars as pl


LABEL_REAR = "rear_end"
LABEL_LANE = "lane_change"
LABEL_TURN = "turn_conflict"
BASE_ONLY = "BASE_ONLY"
DET_FUSION = "DETERMINISTIC_FUSION"


SCAN_EXTS = {".csv", ".json", ".jsonl", ".parquet", ".feather", ".pkl"}
FOCUS_KEYWORDS = [
    "outputs",
    "fusion_v3",
    "frozen",
    "reports",
    "datasets",
    "data",
    "public",
    "replay",
    "scored",
    "source_replay",
    "expanded_generalization",
    "multi_board",
    "all_board",
    "alignment",
]

ID_ALIASES = ["sample_id", "case_id", "id", "row_id", "scenario_id", "clip_id", "video_id", "frame_id"]
GT_ALIASES = ["gt_type", "label", "y", "gt", "ground_truth", "true_label", "class", "true_type"]
BASE_PRED_ALIASES = ["baseline_pred", "pred_base", "y_base", "base_pred", "baseline_output", "pred_type"]
FUSION_PRED_ALIASES = ["fusion_pred", "pred_fusion", "y_fusion", "transfer_pred", "fusion_output", "pred_type_patch"]
BOARD_ALIASES = ["board_id", "board", "source_board", "eval_board", "split_id"]
BUCKET_ALIASES = ["bucket", "bucket_id", "scenario_bucket", "scene_bucket", "context_bucket"]
SOURCE_ALIASES = ["source_id", "source", "dataset", "domain", "source_domain"]

SCORE_HINTS = [
    "score",
    "prob",
    "logit",
    "confidence",
    "margin",
    "rear_score",
    "lane_score",
    "turn_score",
    "nonrear_score",
]


def safe_float(x: Any, d: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return d


def bool_str(v: bool) -> str:
    return "True" if v else "False"


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Normalize fieldnames to the union of all row keys to avoid crashes when
    # candidate rows carry slightly different schemas.
    if rows:
        preferred = [f for f in fields if f]
        preferred_set = set(preferred)
        extras = set()
        for r in rows:
            extras.update(k for k in r.keys() if k and k not in preferred_set)
        fieldnames = preferred + sorted(extras)
    else:
        fieldnames = [f for f in fields if f]
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_csv_rows(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def read_text(path: Path, max_chars: int = 300_000) -> str:
    try:
        t = path.read_text(encoding="utf-8", errors="ignore")
        return t[:max_chars]
    except Exception:
        return ""


def in_focus(path: Path) -> bool:
    s = str(path).lower()
    return any(k in s for k in FOCUS_KEYWORDS)


def lower_colmap(cols: List[str]) -> Dict[str, str]:
    return {str(c).strip().lower(): str(c).strip() for c in cols}


def pick_first(cols_map: Dict[str, str], aliases: List[str]) -> str:
    for a in aliases:
        if a.lower() in cols_map:
            return cols_map[a.lower()]
    return ""


def detect_fields(cols: List[str]) -> Dict[str, Any]:
    cmap = lower_colmap(cols)
    id_col = pick_first(cmap, ID_ALIASES)
    gt_col = pick_first(cmap, GT_ALIASES)
    base_pred_col = pick_first(cmap, BASE_PRED_ALIASES)
    fusion_pred_col = pick_first(cmap, FUSION_PRED_ALIASES)
    board_col = pick_first(cmap, BOARD_ALIASES)
    bucket_col = pick_first(cmap, BUCKET_ALIASES)
    source_col = pick_first(cmap, SOURCE_ALIASES)
    score_cols = []
    for c in cols:
        cl = c.lower()
        if any(h in cl for h in SCORE_HINTS):
            score_cols.append(c)
    has_base_score = any(("baseline" in c.lower() and any(h in c.lower() for h in ["score", "prob", "confidence"])) for c in cols) or ("baseline_score_rear" in cmap)
    has_fusion_score = any((("fusion" in c.lower() or "transfer" in c.lower() or "patch" in c.lower()) and any(h in c.lower() for h in ["score", "prob", "confidence"])) for c in cols) or ("fusion_score_rear" in cmap)
    return {
        "id_col": id_col,
        "gt_col": gt_col,
        "baseline_pred_col": base_pred_col,
        "fusion_pred_col": fusion_pred_col,
        "board_col": board_col,
        "bucket_col": bucket_col,
        "source_col": source_col,
        "score_cols": score_cols,
        "has_base_score": bool(has_base_score),
        "has_fusion_score": bool(has_fusion_score),
    }


def read_head(path: Path, ext: str, n_rows: int = 5000) -> Tuple[Optional[pl.DataFrame], str]:
    try:
        if ext == ".csv":
            df = pl.read_csv(path, n_rows=n_rows, ignore_errors=True)
            return df, ""
        if ext == ".jsonl":
            rows = []
            with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
                for line in f:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        rows.append(json.loads(s))
                    except Exception:
                        continue
                    if len(rows) >= n_rows:
                        break
            if rows:
                return pl.DataFrame(rows), ""
            return pl.DataFrame(), "empty_or_unparsed_jsonl"
        if ext == ".json":
            with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
                obj = json.load(f)
            if isinstance(obj, list):
                return pl.DataFrame(obj[:n_rows]), ""
            if isinstance(obj, dict):
                for _, v in obj.items():
                    if isinstance(v, list):
                        return pl.DataFrame(v[:n_rows]), ""
                return pl.DataFrame([obj]), "json_dict_single_row"
            return pl.DataFrame(), "json_unknown_structure"
        if ext == ".parquet":
            df = pl.read_parquet(path)
            if df.height > n_rows:
                df = df.head(n_rows)
            return df, ""
        if ext == ".feather":
            df = pl.read_ipc(path)
            if df.height > n_rows:
                df = df.head(n_rows)
            return df, ""
        if ext == ".pkl":
            with path.open("rb") as f:
                obj = pickle.load(f)
            if isinstance(obj, list):
                return pl.DataFrame(obj[:n_rows]), ""
            if isinstance(obj, dict):
                try:
                    return pl.DataFrame(obj).head(n_rows), ""
                except Exception:
                    return pl.DataFrame([obj]), "pkl_dict_single_row"
            if isinstance(obj, pl.DataFrame):
                return obj.head(n_rows), ""
            return pl.DataFrame(), f"unsupported_pkl_type:{type(obj).__name__}"
    except Exception as e:
        return None, f"read_error:{type(e).__name__}"
    return None, "unknown_reader_state"


def estimate_rows(path: Path, ext: str, head_df: Optional[pl.DataFrame]) -> int:
    try:
        if ext == ".csv":
            with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
                n = sum(1 for _ in f)
            return max(0, n - 1)
        if ext == ".jsonl":
            with path.open("r", encoding="utf-8-sig", errors="ignore") as f:
                return sum(1 for ln in f if ln.strip())
        if ext in {".parquet", ".feather"}:
            if ext == ".parquet":
                return pl.scan_parquet(path).select(pl.len()).collect().item()
            return pl.scan_ipc(path).select(pl.len()).collect().item()
        if head_df is not None:
            return head_df.height
    except Exception:
        pass
    return head_df.height if head_df is not None else 0


def df_to_key_set(df: pl.DataFrame, col: str, limit: int = 20000) -> set:
    if col == "" or col not in df.columns:
        return set()
    s = df[col].cast(pl.Utf8, strict=False).drop_nulls().unique()
    if s.len() > limit:
        s = s.head(limit)
    return set(s.to_list())


def df_to_comp_set(df: pl.DataFrame, c1: str, c2: str, limit: int = 20000) -> set:
    if c1 == "" or c2 == "" or c1 not in df.columns or c2 not in df.columns:
        return set()
    s = (
        df.select((pl.col(c1).cast(pl.Utf8, strict=False) + pl.lit("||") + pl.col(c2).cast(pl.Utf8, strict=False)).alias("k"))
        .get_column("k")
        .drop_nulls()
        .unique()
    )
    if s.len() > limit:
        s = s.head(limit)
    return set(s.to_list())


def class_recall(gt: List[str], pred: List[str], target: str) -> float:
    idx = [i for i, g in enumerate(gt) if g == target]
    if not idx:
        return float("nan")
    return sum(1 for i in idx if pred[i] == target) / len(idx)


def compute_metrics(rows: List[Dict[str, Any]], pred_key: str, action_key: str) -> Dict[str, float]:
    n = len(rows)
    gt = [str(r.get("gt_type", "")).strip() for r in rows]
    pred = [str(r.get(pred_key, "")).strip() for r in rows]
    act = [str(r.get(action_key, "")).strip() for r in rows]
    rear_idx = [i for i, g in enumerate(gt) if g == LABEL_REAR]
    rear_risk = sum(1 for i in rear_idx if pred[i] != LABEL_REAR) / len(rear_idx) if rear_idx else float("nan")
    auto_error = sum(1 for g, p in zip(gt, pred) if g != p) / n if n else float("nan")
    lane_recall = class_recall(gt, pred, LABEL_LANE)
    turn_recall = class_recall(gt, pred, LABEL_TURN)
    utility = 0.5 * lane_recall + 0.5 * turn_recall if not (math.isnan(lane_recall) or math.isnan(turn_recall)) else float("nan")
    defer_count = sum(1 for a in act if a == "DEFER")
    boost_count = sum(1 for a in act if a == "FUSION_BOOST")
    keep_count = sum(1 for a in act if a == "KEEP_BASELINE")
    fallback_rate = defer_count / n if n else float("nan")
    auto_coverage = 1.0 - fallback_rate if n else float("nan")
    return {
        "N": n,
        "defer_count": defer_count,
        "boost_count": boost_count,
        "keep_count": keep_count,
        "fallback_rate": fallback_rate,
        "auto_coverage": auto_coverage,
        "rear_risk": rear_risk,
        "auto_error": auto_error,
        "lane_recall": lane_recall,
        "turn_recall": turn_recall,
        "utility": utility,
    }


def canonical_label(x: str) -> str:
    s = str(x).strip().lower()
    if s in {"rear_end", "rear", "rearend", "rear-end", "0"}:
        return LABEL_REAR
    if s in {"lane_change", "lane", "lanechange", "1"}:
        return LABEL_LANE
    if s in {"turn_conflict", "turn", "turnconflict", "2"}:
        return LABEL_TURN
    return str(x).strip()


@dataclass
class RulePolicy:
    policy_name: str
    theta_rear_hold: float
    theta_nonrear_boost: float
    theta_margin_boost: float
    theta_soft_keep: float
    defer_mode: str
    bucket_tight: bool


def run_rule_policy(rows: List[Dict[str, Any]], p: RulePolicy) -> List[Dict[str, Any]]:
    out = []
    for r in rows:
        bp = str(r.get("baseline_pred", "")).strip()
        fp = str(r.get("fusion_pred", "")).strip()
        gt = str(r.get("gt_type", "")).strip()
        bsr = safe_float(r.get("baseline_score_rear", np.nan), np.nan)
        fsr = safe_float(r.get("fusion_score_rear", np.nan), np.nan)
        fsl = safe_float(r.get("fusion_score_lane", np.nan), np.nan)
        fst = safe_float(r.get("fusion_score_turn", np.nan), np.nan)

        # fallback for missing lane/turn score
        if math.isnan(fsl) and math.isnan(fst):
            f_nonrear = safe_float(r.get("fusion_score_nonrear", np.nan), np.nan)
        else:
            f_nonrear = np.nanmax([fsl, fst])

        margin = safe_float(r.get("margin_nonrear_minus_rear", f_nonrear - fsr), 0.0)
        rear_tension = bp == LABEL_REAR and fp != LABEL_REAR
        disagreement = bp != fp
        bucket = str(r.get("bucket_id", "")).lower()

        tn = p.theta_nonrear_boost
        tm = p.theta_margin_boost
        if p.bucket_tight and ("night" in bucket or "intersection" in bucket):
            tn = min(0.995, tn + 0.02)
            tm = min(0.6, tm + 0.05)

        keep_guard = (bp == LABEL_REAR and not math.isnan(bsr) and bsr >= p.theta_rear_hold) or (bp == LABEL_REAR and bsr >= p.theta_soft_keep and margin < 0)
        boost_gate = (not math.isnan(f_nonrear)) and (f_nonrear >= tn) and (margin >= tm)

        if p.defer_mode == "rear_tension_only":
            defer_flag = rear_tension and (not boost_gate) and (not keep_guard)
        elif p.defer_mode == "all_disagree":
            defer_flag = disagreement and (not boost_gate) and (not keep_guard)
        else:
            defer_flag = rear_tension and (margin < tm) and (not keep_guard)

        if keep_guard:
            action = "KEEP_BASELINE"
            final_pred = bp
        elif boost_gate:
            action = "FUSION_BOOST"
            final_pred = fp
        elif defer_flag:
            action = "DEFER"
            final_pred = bp
        else:
            action = "KEEP_BASELINE"
            final_pred = bp

        out.append(
            {
                **r,
                "policy_name": p.policy_name,
                "action": action,
                "final_pred": final_pred,
                "is_deferred": bool_str(action == "DEFER"),
                "is_auto": bool_str(action != "DEFER"),
            }
        )
    return out


def queue_sim(actions: List[str], arrival_rate: float, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    queue = 0
    q_hist = []
    defer_count = 0
    total_samples = 0
    idx = 0
    n = len(actions)
    for _ in range(duration_sec):
        arrivals = int(round(arrival_rate))
        for _ in range(arrivals):
            if n == 0:
                break
            a = actions[idx % n]
            idx += 1
            total_samples += 1
            if a == "DEFER":
                queue += 1
                defer_count += 1
        served = min(queue, int(round(service_rate)))
        queue -= served
        q_hist.append(queue)
    defer_rate = defer_count / total_samples if total_samples else 0.0
    eff = arrival_rate * defer_rate
    arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    if eff <= service_rate * 0.95 and arr[-1] <= max(5.0, np.quantile(arr, 0.95, method="linear")):
        stab = "STABLE"
    elif eff > service_rate * 1.05:
        stab = "UNSTABLE"
    else:
        stab = "BORDERLINE"
    return {
        "arrival_rate": arrival_rate,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total_samples,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "effective_defer_arrival_rate": eff,
        "max_queue_length": int(np.max(arr)),
        "mean_queue_length": float(np.mean(arr)),
        "p95_queue_length": float(np.quantile(arr, 0.95, method="linear")),
        "p99_queue_length": float(np.quantile(arr, 0.99, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": stab,
    }


def burst_rate(t: int, pattern: str) -> float:
    if pattern == "Constant":
        return 10.0
    if pattern == "Periodic burst":
        return 50.0 if (t % 30) < 5 else 10.0
    if pattern == "Heavy burst":
        return 100.0 if (t % 60) < 10 else 10.0
    return 10.0


def burst_sim(actions: List[str], pattern: str, service_rate: float, duration_sec: int) -> Dict[str, Any]:
    queue = 0
    q_hist = []
    defer_count = 0
    total_samples = 0
    idx = 0
    n = len(actions)
    for t in range(duration_sec):
        arrivals = int(round(burst_rate(t, pattern)))
        for _ in range(arrivals):
            if n == 0:
                break
            a = actions[idx % n]
            idx += 1
            total_samples += 1
            if a == "DEFER":
                queue += 1
                defer_count += 1
        served = min(queue, int(round(service_rate)))
        queue -= served
        q_hist.append(queue)
    defer_rate = defer_count / total_samples if total_samples else 0.0
    arr = np.array(q_hist, dtype=float) if q_hist else np.array([0.0], dtype=float)
    stab = "UNSTABLE" if arr[-1] > 200 or np.max(arr) > 300 else ("BORDERLINE" if arr[-1] > 50 else "STABLE")
    return {
        "pattern": pattern,
        "fallback_service_rate": service_rate,
        "duration_sec": duration_sec,
        "total_samples": total_samples,
        "defer_count": defer_count,
        "defer_rate": defer_rate,
        "max_queue_length": int(np.max(arr)),
        "mean_queue_length": float(np.mean(arr)),
        "p95_queue_length": float(np.quantile(arr, 0.95, method="linear")),
        "queue_final_length": int(q_hist[-1] if q_hist else 0),
        "stability_flag": stab,
    }


def bootstrap_metrics(rows: List[Dict[str, Any]], B: int, seed: int) -> Dict[str, float]:
    rng = np.random.default_rng(seed)
    n = len(rows)
    fb = np.zeros(B, dtype=float)
    rr = np.zeros(B, dtype=float)
    ae = np.zeros(B, dtype=float)
    ut = np.zeros(B, dtype=float)
    for i in range(B):
        idx = rng.integers(0, n, size=n)
        sample = [rows[int(j)] for j in idx]
        m = compute_metrics(sample, pred_key="final_pred", action_key="action")
        fb[i] = m["fallback_rate"]
        rr[i] = m["rear_risk"]
        ae[i] = m["auto_error"]
        ut[i] = m["utility"]
    return {
        "fallback_mean": float(np.mean(fb)),
        "fallback_p05": float(np.quantile(fb, 0.05, method="linear")),
        "fallback_p95": float(np.quantile(fb, 0.95, method="linear")),
        "rear_risk_mean": float(np.mean(rr)),
        "rear_risk_p05": float(np.quantile(rr, 0.05, method="linear")),
        "rear_risk_p95": float(np.quantile(rr, 0.95, method="linear")),
        "auto_error_mean": float(np.mean(ae)),
        "auto_error_p05": float(np.quantile(ae, 0.05, method="linear")),
        "auto_error_p95": float(np.quantile(ae, 0.95, method="linear")),
        "utility_mean": float(np.mean(ut)),
        "utility_p05": float(np.quantile(ut, 0.05, method="linear")),
        "utility_p95": float(np.quantile(ut, 0.95, method="linear")),
    }


def lobo(rows: List[Dict[str, Any]], group_field: str) -> List[Dict[str, Any]]:
    groups = sorted({str(r.get(group_field, "")).strip() for r in rows if str(r.get(group_field, "")).strip()})
    out = []
    for g in groups:
        sub = [r for r in rows if str(r.get(group_field, "")).strip() != g]
        m = compute_metrics(sub, pred_key="final_pred", action_key="action")
        out.append({"left_out_unit": g, "group_field": group_field, **m})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="RTSS2026 Data Layer Upgrade Pipeline")
    parser.add_argument("--root", type=str, default=r"D:\computer code\accident_app")
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--seed", type=int, default=20260523)
    parser.add_argument("--duration_sec", type=int, default=300)
    parser.add_argument("--bootstrap_B", type=int, default=2000)
    parser.add_argument(
        "--canonical_416",
        type=str,
        default=r"D:\computer code\accident_app\outputs\rtss2026_trace_rebuild_from_sources_20260522_095027\canonical_416_base_table.csv",
    )
    parser.add_argument(
        "--v2_low_fallback_trace",
        type=str,
        default=r"D:\computer code\accident_app\outputs\rtss2026_gsp416_canonical_v2_selection_20260522_115936\GSP416_LOW_FALLBACK_action_trace.csv",
    )
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- Phase 1 ----------------
    inventory_rows: List[Dict[str, Any]] = []
    candidate_meta: List[Dict[str, Any]] = []
    all_files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in SCAN_EXTS and in_focus(p)]

    for p in all_files:
        ext = p.suffix.lower()
        df_head, note = read_head(p, ext)
        if df_head is None:
            cols = []
            row_est = 0
            fields = detect_fields(cols)
            note = note or "unreadable"
        else:
            cols = [str(c) for c in df_head.columns]
            row_est = estimate_rows(p, ext, df_head)
            fields = detect_fields(cols)

        candidate_type = "unknown"
        if row_est >= 500:
            if fields["id_col"] and (fields["gt_col"] or fields["baseline_pred_col"] or fields["fusion_pred_col"]):
                candidate_type = "large_replay_candidate"
            elif fields["score_cols"]:
                candidate_type = "score_asset_candidate"
            else:
                candidate_type = "tabular_candidate"

        inventory_rows.append(
            {
                "file_path": str(p),
                "extension": ext,
                "row_count_est": row_est,
                "col_count": len(cols),
                "columns": ";".join(cols[:200]),
                "id_col": fields["id_col"],
                "gt_col": fields["gt_col"],
                "baseline_pred_col": fields["baseline_pred_col"],
                "fusion_pred_col": fields["fusion_pred_col"],
                "board_col": fields["board_col"],
                "bucket_col": fields["bucket_col"],
                "source_col": fields["source_col"],
                "score_cols": ";".join(fields["score_cols"][:200]),
                "has_base_score": int(fields["has_base_score"]),
                "has_fusion_score": int(fields["has_fusion_score"]),
                "candidate_type": candidate_type,
                "notes": note,
            }
        )

        if row_est >= 500 and df_head is not None:
            candidate_meta.append(
                {
                    "path": p,
                    "ext": ext,
                    "row_count_est": row_est,
                    "df_head": df_head,
                    "fields": fields,
                }
            )

    write_csv(
        out_dir / "01_large_board_asset_inventory.csv",
        inventory_rows,
        [
            "file_path",
            "extension",
            "row_count_est",
            "col_count",
            "columns",
            "id_col",
            "gt_col",
            "baseline_pred_col",
            "fusion_pred_col",
            "board_col",
            "bucket_col",
            "source_col",
            "score_cols",
            "has_base_score",
            "has_fusion_score",
            "candidate_type",
            "notes",
        ],
    )

    join_rows: List[Dict[str, Any]] = []
    key_cache: Dict[int, Dict[str, set]] = {}
    for i, cm in enumerate(candidate_meta):
        dfh = cm["df_head"]
        f = cm["fields"]
        key_cache[i] = {
            "id": df_to_key_set(dfh, f["id_col"]) if f["id_col"] else set(),
            "case": df_to_key_set(dfh, "case_id") if "case_id" in dfh.columns else set(),
            "sample": df_to_key_set(dfh, "sample_id") if "sample_id" in dfh.columns else set(),
            "board_id": df_to_comp_set(dfh, f["board_col"], f["id_col"]) if f["board_col"] and f["id_col"] else set(),
        }

    for i in range(len(candidate_meta)):
        for j in range(i + 1, len(candidate_meta)):
            a = candidate_meta[i]
            b = candidate_meta[j]
            ka = key_cache[i]
            kb = key_cache[j]
            best_key = ""
            best_ov = 0
            best_ratio = 0.0
            for kname in ["id", "case", "sample", "board_id"]:
                sa = ka[kname]
                sb = kb[kname]
                if not sa or not sb:
                    continue
                ov = len(sa & sb)
                if ov <= 0:
                    continue
                ratio = ov / max(1, min(len(sa), len(sb)))
                if ov > best_ov:
                    best_ov = ov
                    best_ratio = ratio
                    best_key = kname
            if best_ov > 0:
                fa = a["fields"]
                fb = b["fields"]
                has_gt = bool(fa["gt_col"] or fb["gt_col"])
                has_bp = bool(fa["baseline_pred_col"] or fb["baseline_pred_col"])
                has_fp = bool(fa["fusion_pred_col"] or fb["fusion_pred_col"])
                has_score = bool((fa["has_base_score"] or fa["has_fusion_score"]) or (fb["has_base_score"] or fb["has_fusion_score"]))
                has_board = bool(fa["board_col"] or fb["board_col"] or fa["source_col"] or fb["source_col"])
                can_action = int(has_gt and has_bp and has_fp and has_score and has_board)
                join_rows.append(
                    {
                        "left_file": str(a["path"]),
                        "right_file": str(b["path"]),
                        "best_join_key": best_key,
                        "overlap_count": best_ov,
                        "overlap_ratio": round(best_ratio, 6),
                        "left_rows_est": a["row_count_est"],
                        "right_rows_est": b["row_count_est"],
                        "can_form_action_level_min_schema": can_action,
                        "left_has_gt": int(bool(fa["gt_col"])),
                        "right_has_gt": int(bool(fb["gt_col"])),
                        "left_has_base_pred": int(bool(fa["baseline_pred_col"])),
                        "right_has_base_pred": int(bool(fb["baseline_pred_col"])),
                        "left_has_fusion_pred": int(bool(fa["fusion_pred_col"])),
                        "right_has_fusion_pred": int(bool(fb["fusion_pred_col"])),
                        "left_has_scores": int(bool(fa["has_base_score"] or fa["has_fusion_score"])),
                        "right_has_scores": int(bool(fb["has_base_score"] or fb["has_fusion_score"])),
                        "left_has_board_or_source": int(bool(fa["board_col"] or fa["source_col"])),
                        "right_has_board_or_source": int(bool(fb["board_col"] or fb["source_col"])),
                    }
                )

    write_csv(
        out_dir / "02_large_board_join_graph.csv",
        join_rows,
        [
            "left_file",
            "right_file",
            "best_join_key",
            "overlap_count",
            "overlap_ratio",
            "left_rows_est",
            "right_rows_est",
            "can_form_action_level_min_schema",
            "left_has_gt",
            "right_has_gt",
            "left_has_base_pred",
            "right_has_base_pred",
            "left_has_fusion_pred",
            "right_has_fusion_pred",
            "left_has_scores",
            "right_has_scores",
            "left_has_board_or_source",
            "right_has_board_or_source",
        ],
    )

    cand_rows = []
    for cm in candidate_meta:
        f = cm["fields"]
        n = cm["row_count_est"]
        score = 0
        score += 4 if n >= 2000 else 3 if n >= 1000 else 2 if n >= 500 else 0
        score += 2 if f["gt_col"] else 0
        score += 2 if f["baseline_pred_col"] else 0
        score += 2 if f["fusion_pred_col"] else 0
        score += 2 if (f["has_base_score"] or f["has_fusion_score"] or len(f["score_cols"]) > 0) else 0
        score += 1 if (f["board_col"] or f["source_col"]) else 0
        score += 1 if f["bucket_col"] else 0
        usable = int(
            bool(
                f["id_col"]
                and f["gt_col"]
                and f["baseline_pred_col"]
                and f["fusion_pred_col"]
                and (f["has_base_score"] or f["has_fusion_score"] or len(f["score_cols"]) > 0)
                and (f["board_col"] or f["source_col"])
            )
        )
        cand_rows.append(
            {
                "file_path": str(cm["path"]),
                "row_count_est": n,
                "id_col": f["id_col"],
                "gt_col": f["gt_col"],
                "baseline_pred_col": f["baseline_pred_col"],
                "fusion_pred_col": f["fusion_pred_col"],
                "board_col": f["board_col"],
                "bucket_col": f["bucket_col"],
                "source_col": f["source_col"],
                "has_base_score": int(f["has_base_score"]),
                "has_fusion_score": int(f["has_fusion_score"]),
                "score_cols": ";".join(f["score_cols"][:80]),
                "candidate_score": score,
                "action_level_usable_directly": usable,
            }
        )
    cand_rows = sorted(cand_rows, key=lambda x: (x["action_level_usable_directly"], x["candidate_score"], x["row_count_est"]), reverse=True)
    write_csv(
        out_dir / "03_large_board_candidates.csv",
        cand_rows,
        [
            "file_path",
            "row_count_est",
            "id_col",
            "gt_col",
            "baseline_pred_col",
            "fusion_pred_col",
            "board_col",
            "bucket_col",
            "source_col",
            "has_base_score",
            "has_fusion_score",
            "score_cols",
            "candidate_score",
            "action_level_usable_directly",
        ],
    )

    # Build canonical large table if possible
    large_base_rows: List[Dict[str, Any]] = []
    large_base_src = None
    for c in cand_rows:
        if c["action_level_usable_directly"] != 1:
            continue
        if c["row_count_est"] < 1000:
            continue
        p = Path(c["file_path"])
        ext = p.suffix.lower()
        df, note = read_head(p, ext, n_rows=max(5000, min(200000, c["row_count_est"])))
        if df is None or df.height == 0:
            continue
        f = detect_fields([str(x) for x in df.columns])
        # full read for text formats
        if ext == ".csv":
            try:
                df = pl.read_csv(p, ignore_errors=True)
            except Exception:
                pass
        elif ext == ".jsonl":
            rows = []
            with p.open("r", encoding="utf-8-sig", errors="ignore") as fh:
                for line in fh:
                    s = line.strip()
                    if not s:
                        continue
                    try:
                        rows.append(json.loads(s))
                    except Exception:
                        continue
            if rows:
                df = pl.DataFrame(rows)
        elif ext == ".json":
            try:
                with p.open("r", encoding="utf-8-sig", errors="ignore") as fh:
                    obj = json.load(fh)
                if isinstance(obj, list):
                    df = pl.DataFrame(obj)
            except Exception:
                pass

        if df is None or df.height == 0:
            continue

        # map score columns (best effort)
        cols_l = lower_colmap([str(x) for x in df.columns])
        def col(k: str) -> str:
            return cols_l.get(k.lower(), "")
        bsr = col("baseline_score_rear") or col("rear_score")
        bsl = col("baseline_score_lane") or col("lane_score")
        bst = col("baseline_score_turn") or col("turn_score")
        fsr = col("fusion_score_rear") or col("rear_score_patch")
        fsl = col("fusion_score_lane") or col("lane_score_patch")
        fst = col("fusion_score_turn") or col("turn_score_patch")

        id_col = f["id_col"]
        gt_col = f["gt_col"]
        bp_col = f["baseline_pred_col"]
        fp_col = f["fusion_pred_col"]
        if not (id_col and gt_col and bp_col and fp_col):
            continue
        for r in df.iter_rows(named=True):
            sid = str(r.get(id_col, "")).strip()
            if sid == "":
                continue
            large_base_rows.append(
                {
                    "sample_id": sid,
                    "case_id": sid,
                    "board_id": str(r.get(f["board_col"], "")).strip() if f["board_col"] else "",
                    "bucket_id": str(r.get(f["bucket_col"], "")).strip() if f["bucket_col"] else "",
                    "source_id": str(r.get(f["source_col"], "")).strip() if f["source_col"] else "",
                    "gt_type": canonical_label(r.get(gt_col, "")),
                    "baseline_pred": canonical_label(r.get(bp_col, "")),
                    "fusion_pred": canonical_label(r.get(fp_col, "")),
                    "baseline_score_rear": r.get(bsr, np.nan) if bsr else np.nan,
                    "baseline_score_lane": r.get(bsl, np.nan) if bsl else np.nan,
                    "baseline_score_turn": r.get(bst, np.nan) if bst else np.nan,
                    "fusion_score_rear": r.get(fsr, np.nan) if fsr else np.nan,
                    "fusion_score_lane": r.get(fsl, np.nan) if fsl else np.nan,
                    "fusion_score_turn": r.get(fst, np.nan) if fst else np.nan,
                    "provenance_source_file": str(p),
                }
            )
        large_base_src = c
        break

    # dedup and validate
    large_rows_dedup: List[Dict[str, Any]] = []
    seen = set()
    for r in large_base_rows:
        k = r["sample_id"]
        if k in seen:
            continue
        seen.add(k)
        if r["source_id"] == "" and r["board_id"] != "":
            r["source_id"] = r["board_id"]
        large_rows_dedup.append(r)

    large_ok = len(large_rows_dedup) >= 1000
    if large_rows_dedup:
        write_csv(
            out_dir / "canonical_large_base_table.csv",
            large_rows_dedup,
            [
                "sample_id",
                "case_id",
                "board_id",
                "bucket_id",
                "source_id",
                "gt_type",
                "baseline_pred",
                "fusion_pred",
                "baseline_score_rear",
                "baseline_score_lane",
                "baseline_score_turn",
                "fusion_score_rear",
                "fusion_score_lane",
                "fusion_score_turn",
                "provenance_source_file",
            ],
        )
        cls = Counter([r["gt_type"] for r in large_rows_dedup])
        boards = len({r["board_id"] for r in large_rows_dedup if r["board_id"] != ""})
        srcs = len({r["source_id"] for r in large_rows_dedup if r["source_id"] != ""})
        val_lines = [
            "# canonical_large_base_table_validation",
            "",
            f"- source_file: `{large_base_src['file_path'] if large_base_src else ''}`",
            f"- N: {len(large_rows_dedup)}",
            f"- unique_boards: {boards}",
            f"- unique_sources: {srcs}",
            f"- class_support: {json.dumps(cls, ensure_ascii=False)}",
            f"- has_full_score_triplet: {all(any(str(r.get(k, '')) != '' for r in large_rows_dedup) for k in ['fusion_score_rear','fusion_score_lane','fusion_score_turn'])}",
            f"- can_enter_policy_routing: {len(large_rows_dedup) > 0}",
            f"- context: {'N>=1000 achieved' if large_ok else 'N<1000'}",
        ]
        (out_dir / "canonical_large_base_table_validation.md").write_text("\n".join(val_lines) + "\n", encoding="utf-8")
    else:
        miss = [
            "# large_board_missing_report",
            "",
            "- No directly usable large action-level table could be built from current assets with N>=1000.",
            "- Required fields for direct build: id + gt + baseline_pred + fusion_pred + score + board/source.",
        ]
        (out_dir / "large_board_missing_report.md").write_text("\n".join(miss) + "\n", encoding="utf-8")

    # md summaries for phase 1
    inv_type = Counter([r["candidate_type"] for r in inventory_rows])
    m1 = [
        "# 01 Large Board Asset Inventory",
        "",
        f"- scanned_files: {len(inventory_rows)}",
        f"- row>=500_candidates: {sum(1 for r in inventory_rows if r['row_count_est'] >= 500)}",
        "",
        "## Candidate Type Counts",
    ]
    for k, v in sorted(inv_type.items()):
        m1.append(f"- {k}: {v}")
    m1.append("")
    m1.append("## Top Large Files")
    top_inv = sorted(inventory_rows, key=lambda x: x["row_count_est"], reverse=True)[:120]
    for r in top_inv:
        m1.append(f"- {r['file_path']} | rows~{r['row_count_est']} | type={r['candidate_type']}")
    (out_dir / "01_large_board_asset_inventory.md").write_text("\n".join(m1) + "\n", encoding="utf-8")

    m2 = ["# 02 Large Board Join Graph", "", f"- pair_edges: {len(join_rows)}", "", "## Top Joinable Pairs"]
    top_j = sorted(join_rows, key=lambda x: (x["can_form_action_level_min_schema"], x["overlap_count"], x["overlap_ratio"]), reverse=True)[:120]
    for r in top_j:
        m2.append(
            f"- {r['left_file']} <-> {r['right_file']} | key={r['best_join_key']} ov={r['overlap_count']} ratio={r['overlap_ratio']} schema_ok={r['can_form_action_level_min_schema']}"
        )
    (out_dir / "02_large_board_join_graph.md").write_text("\n".join(m2) + "\n", encoding="utf-8")

    m3 = ["# 03 Large Board Candidates", "", f"- candidates: {len(cand_rows)}", "", "## Top Scored Candidates"]
    for r in cand_rows[:120]:
        m3.append(
            f"- {r['file_path']} | rows~{r['row_count_est']} | score={r['candidate_score']} | usable={r['action_level_usable_directly']}"
        )
    (out_dir / "03_large_board_candidates.md").write_text("\n".join(m3) + "\n", encoding="utf-8")

    # ---------------- Phase 2 ----------------
    score_inv_rows: List[Dict[str, Any]] = []
    for cm in candidate_meta:
        f = cm["fields"]
        score_inv_rows.append(
            {
                "file_path": str(cm["path"]),
                "row_count_est": cm["row_count_est"],
                "id_col": f["id_col"],
                "has_base_score": int(f["has_base_score"]),
                "has_fusion_score": int(f["has_fusion_score"]),
                "score_cols": ";".join(f["score_cols"][:120]),
                "gt_col": f["gt_col"],
                "baseline_pred_col": f["baseline_pred_col"],
                "fusion_pred_col": f["fusion_pred_col"],
            }
        )
    write_csv(
        out_dir / "04_score_asset_inventory.csv",
        score_inv_rows,
        ["file_path", "row_count_est", "id_col", "has_base_score", "has_fusion_score", "score_cols", "gt_col", "baseline_pred_col", "fusion_pred_col"],
    )

    score_md = [
        "# 04 Score Asset Inventory",
        "",
        f"- total_assets_considered: {len(score_inv_rows)}",
        f"- assets_with_scores: {sum(1 for r in score_inv_rows if r['has_base_score'] or r['has_fusion_score'])}",
    ]
    (out_dir / "04_score_asset_inventory.md").write_text("\n".join(score_md) + "\n", encoding="utf-8")

    # choose working table
    working_rows: List[Dict[str, Any]] = []
    working_context = "416"
    if large_rows_dedup and large_ok:
        working_rows = large_rows_dedup
        working_context = "large"
    else:
        # fallback to canonical_416
        working_rows = read_csv_rows(Path(args.canonical_416))
        working_context = "416_fallback"

    # ensure score columns exist
    for r in working_rows:
        for k in [
            "baseline_score_rear",
            "baseline_score_lane",
            "baseline_score_turn",
            "fusion_score_rear",
            "fusion_score_lane",
            "fusion_score_turn",
        ]:
            if k not in r:
                r[k] = np.nan
        # fallback for source id
        if "source_id" not in r:
            r["source_id"] = r.get("board_id", "")
        if "case_id" not in r:
            r["case_id"] = r.get("sample_id", "")
        if "sample_id" not in r:
            r["sample_id"] = r.get("case_id", "")

    # try score join from candidate assets if missing significant
    missing_before = sum(1 for r in working_rows if str(r.get("fusion_score_rear", "")) in {"", "nan", "None"})
    joined_from = ""
    if missing_before > 0:
        work_map = {str(r.get("sample_id", "")): r for r in working_rows}
        for cm in candidate_meta:
            f = cm["fields"]
            if not f["id_col"]:
                continue
            if not (f["has_base_score"] or f["has_fusion_score"] or len(f["score_cols"]) > 0):
                continue
            dfh = cm["df_head"]
            cols_l = lower_colmap([str(x) for x in dfh.columns])
            id_col = f["id_col"]
            # best effort pick
            bsr = cols_l.get("baseline_score_rear", "") or cols_l.get("rear_score", "")
            bsl = cols_l.get("baseline_score_lane", "") or cols_l.get("lane_score", "")
            bst = cols_l.get("baseline_score_turn", "") or cols_l.get("turn_score", "")
            fsr = cols_l.get("fusion_score_rear", "") or cols_l.get("rear_score_patch", "")
            fsl = cols_l.get("fusion_score_lane", "") or cols_l.get("lane_score_patch", "")
            fst = cols_l.get("fusion_score_turn", "") or cols_l.get("turn_score_patch", "")
            if not any([bsr, bsl, bst, fsr, fsl, fst]):
                continue
            fill = 0
            for rr in dfh.iter_rows(named=True):
                sid = str(rr.get(id_col, "")).strip()
                if sid == "" or sid not in work_map:
                    continue
                wr = work_map[sid]
                if fsr:
                    wr["fusion_score_rear"] = rr.get(fsr, wr.get("fusion_score_rear", np.nan))
                if fsl:
                    wr["fusion_score_lane"] = rr.get(fsl, wr.get("fusion_score_lane", np.nan))
                if fst:
                    wr["fusion_score_turn"] = rr.get(fst, wr.get("fusion_score_turn", np.nan))
                if bsr:
                    wr["baseline_score_rear"] = rr.get(bsr, wr.get("baseline_score_rear", np.nan))
                if bsl:
                    wr["baseline_score_lane"] = rr.get(bsl, wr.get("baseline_score_lane", np.nan))
                if bst:
                    wr["baseline_score_turn"] = rr.get(bst, wr.get("baseline_score_turn", np.nan))
                fill += 1
            if fill > 0:
                joined_from = str(cm["path"])
                working_rows = list(work_map.values())
                break

    missing_after = sum(1 for r in working_rows if str(r.get("fusion_score_rear", "")) in {"", "nan", "None"})
    phase2_lines = [
        "# 05 Score Join / Rerun Report",
        "",
        f"- working_context: {working_context}",
        f"- rows: {len(working_rows)}",
        f"- missing_fusion_score_before: {missing_before}",
        f"- missing_fusion_score_after: {missing_after}",
        f"- joined_from_asset: `{joined_from}`" if joined_from else "- joined_from_asset: none",
        "- model_rerun: not executed (no verified predictor inference chain provided in this phase)",
    ]
    (out_dir / "05_score_join_or_rerun_report.md").write_text("\n".join(phase2_lines) + "\n", encoding="utf-8")

    if len(working_rows) > 0:
        write_csv(
            out_dir / "canonical_large_scored_replay.csv",
            working_rows,
            [
                "sample_id",
                "case_id",
                "gt_type",
                "baseline_pred",
                "fusion_pred",
                "baseline_score_rear",
                "baseline_score_lane",
                "baseline_score_turn",
                "fusion_score_rear",
                "fusion_score_lane",
                "fusion_score_turn",
                "board_id",
                "bucket_id",
                "source_id",
                "provenance_source_file",
            ],
        )
        (out_dir / "canonical_large_scored_replay.md").write_text(
            "\n".join(
                [
                    "# canonical_large_scored_replay",
                    "",
                    f"- context: {working_context}",
                    f"- N: {len(working_rows)}",
                    "- provenance: built from available scored assets and field mapping in this run",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    else:
        (out_dir / "score_rerun_missing_report.md").write_text(
            "\n".join(
                [
                    "# score_rerun_missing_report",
                    "",
                    "- Unable to assemble a working scored replay.",
                    "- Missing either joinable score assets or valid predictor rerun chain.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    # ---------------- Phase 3 ----------------
    feature_rows: List[Dict[str, Any]] = []
    for r in working_rows:
        bsr = safe_float(r.get("baseline_score_rear", np.nan), np.nan)
        bsl = safe_float(r.get("baseline_score_lane", np.nan), np.nan)
        bst = safe_float(r.get("baseline_score_turn", np.nan), np.nan)
        fsr = safe_float(r.get("fusion_score_rear", np.nan), np.nan)
        fsl = safe_float(r.get("fusion_score_lane", np.nan), np.nan)
        fst = safe_float(r.get("fusion_score_turn", np.nan), np.nan)
        bp = str(r.get("baseline_pred", "")).strip()
        fp = str(r.get("fusion_pred", "")).strip()

        b_scores = [x for x in [bsr, bsl, bst] if not math.isnan(x)]
        f_scores = [x for x in [fsr, fsl, fst] if not math.isnan(x)]

        b_top1 = max(b_scores) if b_scores else np.nan
        f_top1 = max(f_scores) if f_scores else np.nan
        b_sorted = sorted(b_scores, reverse=True) if b_scores else []
        f_sorted = sorted(f_scores, reverse=True) if f_scores else []
        b_margin_12 = (b_sorted[0] - b_sorted[1]) if len(b_sorted) >= 2 else np.nan
        f_margin_12 = (f_sorted[0] - f_sorted[1]) if len(f_sorted) >= 2 else np.nan
        f_nonrear = np.nanmax([fsl, fst]) if not (math.isnan(fsl) and math.isnan(fst)) else np.nan
        margin_nr_rear = safe_float(r.get("margin_nonrear_minus_rear", f_nonrear - fsr), np.nan)
        conf_gap = f_top1 - b_top1 if (not math.isnan(f_top1) and not math.isnan(b_top1)) else np.nan

        feature_rows.append(
            {
                "sample_id": r.get("sample_id", ""),
                "case_id": r.get("case_id", r.get("sample_id", "")),
                "board_id": r.get("board_id", ""),
                "bucket_id": r.get("bucket_id", ""),
                "source_id": r.get("source_id", ""),
                "gt_type": r.get("gt_type", ""),
                "baseline_pred": bp,
                "fusion_pred": fp,
                "baseline_score_rear": bsr,
                "baseline_score_lane": bsl,
                "baseline_score_turn": bst,
                "fusion_score_rear": fsr,
                "fusion_score_lane": fsl,
                "fusion_score_turn": fst,
                "fusion_nonrear_max": f_nonrear,
                "fusion_nonrear_argmax": LABEL_LANE if (not math.isnan(fsl) and not math.isnan(fst) and fsl >= fst) else (LABEL_TURN if (not math.isnan(fsl) and not math.isnan(fst)) else ""),
                "margin_nonrear_minus_rear": margin_nr_rear,
                "baseline_top1_conf": b_top1,
                "fusion_top1_conf": f_top1,
                "baseline_fusion_disagree": int(bp != fp),
                "baseline_is_rear": int(bp == LABEL_REAR),
                "fusion_is_rear": int(fp == LABEL_REAR),
                "baseline_margin_top1_top2": b_margin_12,
                "fusion_margin_top1_top2": f_margin_12,
                "rear_tension_flag": int(bp == LABEL_REAR and fp != LABEL_REAR),
                "nonrear_tension_flag": int(bp != LABEL_REAR and fp == LABEL_REAR),
                "lane_turn_conflict_flag": int((bp == LABEL_LANE and fp == LABEL_TURN) or (bp == LABEL_TURN and fp == LABEL_LANE)),
                "confidence_gap": conf_gap,
                "normalized_margin": (margin_nr_rear / (abs(fsr) + 1e-6)) if (not math.isnan(margin_nr_rear) and not math.isnan(fsr)) else np.nan,
            }
        )

    write_csv(
        out_dir / "06_feature_table.csv",
        feature_rows,
        list(feature_rows[0].keys()) if feature_rows else ["sample_id"],
    )
    feature_schema = {
        "context": working_context,
        "N": len(feature_rows),
        "feature_columns": list(feature_rows[0].keys()) if feature_rows else [],
        "note": "interpretable feature set generated from scored replay in this run",
    }
    (out_dir / "06_feature_schema.json").write_text(json.dumps(feature_schema, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "06_feature_table.md").write_text(
        "\n".join(
            [
                "# 06 Feature Table",
                "",
                f"- N: {len(feature_rows)}",
                f"- context: {working_context}",
                "- includes base/fusion scores, margins, tensions, disagreement flags, and board/bucket/source IDs.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # ---------------- Phase 4 ----------------
    # controlled, interpretable search (no huge grid)
    candidate_rows: List[Dict[str, Any]] = []
    policy_rows_map: Dict[str, List[Dict[str, Any]]] = {}
    cidx = 1
    for tr in [0.4, 0.5, 0.6]:
        for tn in [0.9, 0.95, 0.98]:
            for tm in [0.0, 0.1, 0.2]:
                for ts in [0.3, 0.4, 0.5]:
                    for defer_mode in ["rear_tension_only", "all_disagree", "rear_tension_or_margin"]:
                        for bt in [False, True]:
                            pname = f"PF_{cidx:04d}"
                            p = RulePolicy(
                                policy_name=pname,
                                theta_rear_hold=tr,
                                theta_nonrear_boost=tn,
                                theta_margin_boost=tm,
                                theta_soft_keep=ts,
                                defer_mode=defer_mode,
                                bucket_tight=bt,
                            )
                            pol = run_rule_policy(feature_rows, p)
                            m = compute_metrics(pol, pred_key="final_pred", action_key="action")
                            candidate_rows.append(
                                {
                                    "candidate_id": pname,
                                    "method": "rule_based",
                                    "theta_rear_hold": tr,
                                    "theta_nonrear_boost": tn,
                                    "theta_margin_boost": tm,
                                    "theta_soft_keep": ts,
                                    "defer_mode": defer_mode,
                                    "bucket_tight": int(bt),
                                    "fallback_rate": m["fallback_rate"],
                                    "rear_risk": m["rear_risk"],
                                    "auto_error": m["auto_error"],
                                    "utility": m["utility"],
                                    "lane_recall": m["lane_recall"],
                                    "turn_recall": m["turn_recall"],
                                    "auto_coverage": m["auto_coverage"],
                                    "defer_count": m["defer_count"],
                                    "boost_count": m["boost_count"],
                                    "keep_count": m["keep_count"],
                                    "predicate_formula": (
                                        f"if baseline_rear & baseline_score>= {tr} keep; "
                                        f"elif fusion_nonrear>= {tn} and margin>= {tm} boost; "
                                        f"elif defer_mode={defer_mode} defer; else keep; "
                                        f"soft_keep={ts}; bucket_tight={bt}"
                                    ),
                                }
                            )
                            policy_rows_map[pname] = pol
                            cidx += 1

    write_csv(
        out_dir / "07_policy_family_candidates.csv",
        candidate_rows,
        [
            "candidate_id",
            "method",
            "theta_rear_hold",
            "theta_nonrear_boost",
            "theta_margin_boost",
            "theta_soft_keep",
            "defer_mode",
            "bucket_tight",
            "fallback_rate",
            "rear_risk",
            "auto_error",
            "utility",
            "lane_recall",
            "turn_recall",
            "auto_coverage",
            "defer_count",
            "boost_count",
            "keep_count",
            "predicate_formula",
        ],
    )
    (out_dir / "07_policy_family_candidates.md").write_text(
        "\n".join(
            [
                "# 07 Policy Family Candidates",
                "",
                f"- total_candidates: {len(candidate_rows)}",
                "- method: rule-based interpretable family (two-stage rear hold + boost gate + defer mode).",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # ---------------- Phase 5 ----------------
    # anchors under current context
    base_rows = []
    det_rows = []
    for r in feature_rows:
        rb = dict(r)
        rb["action"] = "KEEP_BASELINE"
        rb["final_pred"] = rb["baseline_pred"]
        rb["policy_name"] = BASE_ONLY
        base_rows.append(rb)
        rd = dict(r)
        rd["action"] = "FUSION_BOOST"
        rd["final_pred"] = rd["fusion_pred"]
        rd["policy_name"] = DET_FUSION
        det_rows.append(rd)
    anchor_base = compute_metrics(base_rows, pred_key="final_pred", action_key="action")
    anchor_det = compute_metrics(det_rows, pred_key="final_pred", action_key="action")

    primary_feasible = [
        c
        for c in candidate_rows
        if c["fallback_rate"] <= 0.05
        and c["rear_risk"] <= 0.14
        and c["utility"] >= 0.08
        and c["auto_error"] <= anchor_det["auto_error"]
    ]
    safe_feasible = [
        c
        for c in candidate_rows
        if c["rear_risk"] <= 0.10 and c["utility"] >= anchor_base["utility"] and c["fallback_rate"] <= 0.20
    ]
    yield_feasible = [
        c
        for c in candidate_rows
        if c["utility"] >= 0.085 and c["rear_risk"] < anchor_det["rear_risk"] and c["fallback_rate"] <= 0.08
    ]

    def pick_primary(lst: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not lst:
            return None
        return sorted(
            lst,
            key=lambda c: (
                -(2 * (c["utility"] - anchor_base["utility"]) + 2 * (anchor_det["rear_risk"] - c["rear_risk"]) - 1.2 * c["fallback_rate"] - 0.8 * (c["auto_error"] - anchor_base["auto_error"])),
                c["rear_risk"],
                c["fallback_rate"],
                -c["utility"],
            ),
        )[0]

    def pick_safe(lst: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not lst:
            return None
        return sorted(lst, key=lambda c: (c["rear_risk"], -c["utility"], c["fallback_rate"]))[0]

    def pick_yield(lst: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not lst:
            return None
        return sorted(lst, key=lambda c: (-c["utility"], c["rear_risk"], c["fallback_rate"]))[0]

    pick_p = pick_primary(primary_feasible)
    pick_s = pick_safe(safe_feasible)
    pick_y = pick_yield(yield_feasible)

    selected_rows = []
    for name, pk in [("CANONICAL_PRIMARY_PLUS", pick_p), ("CANONICAL_SAFE_PLUS", pick_s), ("CANONICAL_YIELD_PLUS", pick_y)]:
        if pk is None:
            selected_rows.append({"selected_point": name, "candidate_id": "NONE"})
        else:
            selected_rows.append({"selected_point": name, **pk})

    write_csv(
        out_dir / "08_selected_points.csv",
        selected_rows,
        list(selected_rows[0].keys()) if selected_rows else ["selected_point", "candidate_id"],
    )
    lines_sel = [
        "# 08 Selected Points",
        "",
        f"- context: {working_context}",
        f"- anchor_base: rear={anchor_base['rear_risk']:.6f}, auto_error={anchor_base['auto_error']:.6f}, utility={anchor_base['utility']:.6f}",
        f"- anchor_det: rear={anchor_det['rear_risk']:.6f}, auto_error={anchor_det['auto_error']:.6f}, utility={anchor_det['utility']:.6f}",
        "",
        f"- CANONICAL_PRIMARY_PLUS: {pick_p['candidate_id'] if pick_p else 'NONE'}",
        f"- CANONICAL_SAFE_PLUS: {pick_s['candidate_id'] if pick_s else 'NONE'}",
        f"- CANONICAL_YIELD_PLUS: {pick_y['candidate_id'] if pick_y else 'NONE'}",
    ]
    (out_dir / "08_selected_points.md").write_text("\n".join(lines_sel) + "\n", encoding="utf-8")

    # export selected traces/policies/metrics
    def export_selected(point_name: str, pick: Optional[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        if pick is None:
            return None
        cid = pick["candidate_id"]
        pol = policy_rows_map[cid]
        trace = []
        for r in pol:
            trace.append(
                {
                    "sample_id": r.get("sample_id", ""),
                    "case_id": r.get("case_id", r.get("sample_id", "")),
                    "board_id": r.get("board_id", ""),
                    "bucket_id": r.get("bucket_id", ""),
                    "source_id": r.get("source_id", ""),
                    "gt_type": r.get("gt_type", ""),
                    "baseline_pred": r.get("baseline_pred", ""),
                    "fusion_pred": r.get("fusion_pred", ""),
                    "policy_name": point_name,
                    "action": r.get("action", ""),
                    "final_pred": r.get("final_pred", ""),
                    "is_deferred": r.get("is_deferred", bool_str(str(r.get("action", "")) == "DEFER")),
                    "is_auto": r.get("is_auto", bool_str(str(r.get("action", "")) != "DEFER")),
                    "predicate_formula": pick.get("predicate_formula", ""),
                }
            )
        write_csv(out_dir / f"{point_name}_action_trace.csv", trace, list(trace[0].keys()) if trace else [])
        policy_text = [
            "# auto-generated interpretable policy",
            f"POINT_NAME = '{point_name}'",
            f"CANDIDATE_ID = '{cid}'",
            f"THETA_REAR_HOLD = {pick['theta_rear_hold']}",
            f"THETA_NONREAR_BOOST = {pick['theta_nonrear_boost']}",
            f"THETA_MARGIN_BOOST = {pick['theta_margin_boost']}",
            f"THETA_SOFT_KEEP = {pick['theta_soft_keep']}",
            f"DEFER_MODE = '{pick['defer_mode']}'",
            f"BUCKET_TIGHT = {bool(pick['bucket_tight'])}",
            "",
            f"PROVENANCE = 'regenerated_from_data_layer_upgrade_policy_family'",
            "",
            f"PREDICATE_FORMULA = '''{pick.get('predicate_formula', '')}'''",
        ]
        (out_dir / f"{point_name}_policy.py").write_text("\n".join(policy_text) + "\n", encoding="utf-8")
        m = compute_metrics(pol, pred_key="final_pred", action_key="action")
        md = [
            f"# {point_name} Metrics",
            "",
            f"- candidate_id: {cid}",
            f"- fallback_rate: {m['fallback_rate']:.6f}",
            f"- rear_risk: {m['rear_risk']:.6f}",
            f"- auto_error: {m['auto_error']:.6f}",
            f"- utility: {m['utility']:.6f}",
            f"- lane_recall: {m['lane_recall']:.6f}",
            f"- turn_recall: {m['turn_recall']:.6f}",
        ]
        (out_dir / f"{point_name}_metrics.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        return pol

    pol_primary = export_selected("CANONICAL_PRIMARY_PLUS", pick_p)
    pol_safe = export_selected("CANONICAL_SAFE_PLUS", pick_s)
    pol_yield = export_selected("CANONICAL_YIELD_PLUS", pick_y)

    # ---------------- Phase 6 ----------------
    compare_map: Dict[str, List[Dict[str, Any]]] = {
        BASE_ONLY: base_rows,
        DET_FUSION: det_rows,
    }
    if pol_primary is not None:
        compare_map["CANONICAL_PRIMARY_PLUS"] = pol_primary
    if pol_safe is not None:
        compare_map["CANONICAL_SAFE_PLUS"] = pol_safe
    if pol_yield is not None:
        compare_map["CANONICAL_YIELD_PLUS"] = pol_yield

    # bring V2 low fallback trace if exists
    v2_path = Path(args.v2_low_fallback_trace)
    if v2_path.exists():
        v2_rows = read_csv_rows(v2_path)
        for r in v2_rows:
            r["policy_name"] = "V2_LOW_FALLBACK"
        compare_map["V2_LOW_FALLBACK"] = v2_rows

    q_rows = []
    for pname, rows in compare_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for lam in [1, 5, 10, 20, 30, 50, 100]:
            for mu in [0.1, 0.5, 1, 2, 5, 10]:
                q = queue_sim(actions, float(lam), float(mu), duration_sec=args.duration_sec)
                q_rows.append({"policy_name": pname, **q})
    write_csv(
        out_dir / "09_queue_stress_raw.csv",
        q_rows,
        [
            "policy_name",
            "arrival_rate",
            "fallback_service_rate",
            "duration_sec",
            "total_samples",
            "defer_count",
            "defer_rate",
            "effective_defer_arrival_rate",
            "max_queue_length",
            "mean_queue_length",
            "p95_queue_length",
            "p99_queue_length",
            "queue_final_length",
            "stability_flag",
        ],
    )
    q_md = ["# 09 Queue Stress Summary", ""]
    for pname in compare_map.keys():
        sub = [r for r in q_rows if r["policy_name"] == pname]
        st = sum(1 for r in sub if r["stability_flag"] == "STABLE")
        bd = sum(1 for r in sub if r["stability_flag"] == "BORDERLINE")
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        q_md.append(f"- {pname}: stable/borderline/unstable={st}/{bd}/{un}")
    (out_dir / "09_queue_stress_summary.md").write_text("\n".join(q_md) + "\n", encoding="utf-8")

    b_rows = []
    for pname, rows in compare_map.items():
        actions = [str(r.get("action", "")).strip() for r in rows]
        for pattern in ["Constant", "Periodic burst", "Heavy burst"]:
            for mu in [0.5, 1, 2, 5]:
                b = burst_sim(actions, pattern, service_rate=float(mu), duration_sec=args.duration_sec)
                b_rows.append({"policy_name": pname, **b})
    write_csv(
        out_dir / "10_burst_raw.csv",
        b_rows,
        [
            "policy_name",
            "pattern",
            "fallback_service_rate",
            "duration_sec",
            "total_samples",
            "defer_count",
            "defer_rate",
            "max_queue_length",
            "mean_queue_length",
            "p95_queue_length",
            "queue_final_length",
            "stability_flag",
        ],
    )
    b_md = ["# 10 Burst Summary", ""]
    for pname in compare_map.keys():
        sub = [r for r in b_rows if r["policy_name"] == pname]
        un = sum(1 for r in sub if r["stability_flag"] == "UNSTABLE")
        b_md.append(f"- {pname}: unstable={un}/{len(sub)}")
    (out_dir / "10_burst_summary.md").write_text("\n".join(b_md) + "\n", encoding="utf-8")

    boot_rows = []
    lobo_rows = []
    lobo_source_rows = []
    for i, (pname, rows) in enumerate(compare_map.items(), start=1):
        bs = bootstrap_metrics(rows, B=args.bootstrap_B, seed=args.seed + i * 31)
        boot_rows.append({"policy_name": pname, **bs})
        for r in lobo(rows, "board_id"):
            lobo_rows.append({"policy_name": pname, **r})
        for r in lobo(rows, "source_id"):
            lobo_source_rows.append({"policy_name": pname, **r})

    write_csv(
        out_dir / "11_bootstrap_summary.csv",
        boot_rows,
        [
            "policy_name",
            "fallback_mean",
            "fallback_p05",
            "fallback_p95",
            "rear_risk_mean",
            "rear_risk_p05",
            "rear_risk_p95",
            "auto_error_mean",
            "auto_error_p05",
            "auto_error_p95",
            "utility_mean",
            "utility_p05",
            "utility_p95",
        ],
    )
    write_csv(
        out_dir / "11_lobo_board.csv",
        lobo_rows,
        ["policy_name", "left_out_unit", "group_field", "N", "defer_count", "boost_count", "keep_count", "fallback_rate", "auto_coverage", "rear_risk", "auto_error", "lane_recall", "turn_recall", "utility"],
    )
    write_csv(
        out_dir / "11_lobo_source.csv",
        lobo_source_rows,
        ["policy_name", "left_out_unit", "group_field", "N", "defer_count", "boost_count", "keep_count", "fallback_rate", "auto_coverage", "rear_risk", "auto_error", "lane_recall", "turn_recall", "utility"],
    )
    l_md = ["# 11 Bootstrap / LOBO Summary", "", f"- bootstrap_B: {args.bootstrap_B}", ""]
    for r in boot_rows:
        l_md.append(
            f"- {r['policy_name']}: fallback={r['fallback_mean']:.6f}, rear_risk={r['rear_risk_mean']:.6f}, auto_error={r['auto_error_mean']:.6f}, utility={r['utility_mean']:.6f}"
        )
    (out_dir / "11_bootstrap_lobo_summary.md").write_text("\n".join(l_md) + "\n", encoding="utf-8")

    # ---------------- final report ----------------
    # compare against V2 reference metrics if available
    v2_ref = {"fallback_rate": 0.007212, "rear_risk": 0.151724, "utility": 0.081651, "auto_error": 0.649038}
    best_new = None
    for nm, pk in [("CANONICAL_PRIMARY_PLUS", pick_p), ("CANONICAL_SAFE_PLUS", pick_s), ("CANONICAL_YIELD_PLUS", pick_y)]:
        if pk is None:
            continue
        if best_new is None:
            best_new = (nm, pk)
        else:
            # simple compare by utility then rear
            if pk["utility"] > best_new[1]["utility"]:
                best_new = (nm, pk)

    better_than_v2 = False
    if best_new is not None:
        pk = best_new[1]
        better_than_v2 = (
            (pk["rear_risk"] < v2_ref["rear_risk"] and pk["utility"] >= v2_ref["utility"])
            or (pk["utility"] > v2_ref["utility"] and pk["rear_risk"] <= v2_ref["rear_risk"])
            or (pk["fallback_rate"] < v2_ref["fallback_rate"] and pk["rear_risk"] <= v2_ref["rear_risk"] and pk["utility"] >= v2_ref["utility"])
        )

    success_A = large_ok and (pick_p is not None)
    success_B = better_than_v2

    final_lines = [
        "# RTSS2026_DATA_LAYER_UPGRADE_MASTER_REPORT",
        "",
        "## 1. Canonical board expansion",
        f"- canonical_large_built: {len(large_rows_dedup) > 0}",
        f"- canonical_large_N: {len(large_rows_dedup)}",
        f"- canonical_large_N_ge_1000: {large_ok}",
        "",
        "## 2. Predictor score recovery / rerun",
        f"- score_join_attempted: True",
        f"- score_joined_from_asset: `{joined_from}`" if joined_from else "- score_joined_from_asset: none",
        "- predictor_model_rerun: not executed (no verified model-weight + inference-chain closure in this run)",
        "",
        "## 3. Stronger policy input features",
        f"- feature_table_built: {len(feature_rows) > 0}",
        f"- feature_N: {len(feature_rows)}",
        "",
        "## 4. New selected points",
        f"- CANONICAL_PRIMARY_PLUS: {pick_p['candidate_id'] if pick_p else 'NONE'}",
        f"- CANONICAL_SAFE_PLUS: {pick_s['candidate_id'] if pick_s else 'NONE'}",
        f"- CANONICAL_YIELD_PLUS: {pick_y['candidate_id'] if pick_y else 'NONE'}",
    ]
    if pick_p:
        final_lines.append(
            f"- PRIMARY_PLUS metrics: fallback={pick_p['fallback_rate']:.6f}, rear_risk={pick_p['rear_risk']:.6f}, auto_error={pick_p['auto_error']:.6f}, utility={pick_p['utility']:.6f}"
        )
    final_lines.extend(
        [
            "",
            "## 5. Better than V2 LOW_FALLBACK?",
            f"- better_than_v2_low_fallback: {better_than_v2}",
            "",
            "## 6. Bottleneck diagnosis",
            f"- data_scale_bottleneck: {not large_ok}",
            f"- score_quality_or_coverage_bottleneck: {missing_after > 0}",
            "- feature_expressiveness_bottleneck: possible (rule-based family still limited)",
            "- policy_family_bottleneck: possible (interpreter family constrained by explainability and available signals)",
            "",
            "## 7. Stop criterion",
            f"- success_condition_A: {success_A}",
            f"- success_condition_B: {success_B}",
            "- recommendation: "
            + (
                "continue experiments"
                if (success_A or success_B)
                else "stop experiments and move to writing with current best reproducible evidence"
            ),
            "",
            "## 8. Provenance notes",
            "- No legacy TS3 recovery attempted in this run.",
            "- All new assets in this report are generated from current workspace data and scripts.",
        ]
    )
    (out_dir / "RTSS2026_DATA_LAYER_UPGRADE_MASTER_REPORT.md").write_text("\n".join(final_lines) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "phase1_scanned_files": len(inventory_rows),
                "phase1_large_n": len(large_rows_dedup),
                "phase1_large_ge_1000": large_ok,
                "phase4_candidates": len(candidate_rows),
                "selected_primary": pick_p["candidate_id"] if pick_p else None,
                "selected_safe": pick_s["candidate_id"] if pick_s else None,
                "selected_yield": pick_y["candidate_id"] if pick_y else None,
                "better_than_v2_low_fallback": better_than_v2,
                "recommend_stop": not (success_A or success_B),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
