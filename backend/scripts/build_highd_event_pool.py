import argparse
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BuildConfig:
    lane_target: int
    rear_target: int
    neg_target: int
    rear_max_ttc: float
    rear_max_thw: float
    rear_min_score: float
    neg_min_ttc: float
    neg_min_thw: float
    neg_min_frames: int
    seed: int


def parse_recording_range(raw: str) -> List[int]:
    raw = str(raw).strip()
    if not raw:
        raise ValueError("recordings cannot be empty")
    out: List[int] = []
    for token in raw.split(","):
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
    uniq = sorted(set(out))
    if not uniq:
        raise ValueError("no recording parsed")
    return uniq


def safe_float(v: Any) -> Optional[float]:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fv):
        return None
    return fv


def clip01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return float(x)


def normalize_dataset_tag(name: str) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return "dataset"
    out = []
    for ch in raw:
        if ("a" <= ch <= "z") or ("0" <= ch <= "9"):
            out.append(ch)
    return "".join(out) or "dataset"


def as_opt_float(v: Any) -> Optional[float]:
    fv = safe_float(v)
    if fv is None:
        return None
    if fv < 0:
        return None
    return float(fv)


def as_nonneg_float(v: Any) -> float:
    fv = safe_float(v)
    if fv is None:
        return 0.0
    if fv < 0:
        return 0.0
    return float(fv)


def pick_first_column(columns: Iterable[str], candidates: List[str]) -> Optional[str]:
    pool = set(columns)
    for c in candidates:
        if c in pool:
            return c
    return None


def load_meta(meta_csv: Path) -> pd.DataFrame:
    header = pd.read_csv(meta_csv, nrows=0, low_memory=False)
    cols = list(header.columns)
    source_map: Dict[str, Optional[str]] = {
        "id": pick_first_column(cols, ["id", "trackId"]),
        "width": pick_first_column(cols, ["width"]),
        "height": pick_first_column(cols, ["height", "length"]),
        "initialFrame": pick_first_column(cols, ["initialFrame"]),
        "finalFrame": pick_first_column(cols, ["finalFrame"]),
        "numFrames": pick_first_column(cols, ["numFrames"]),
        "class": pick_first_column(cols, ["class"]),
        "drivingDirection": pick_first_column(cols, ["drivingDirection"]),
        "traveledDistance": pick_first_column(cols, ["traveledDistance"]),
        "minXVelocity": pick_first_column(cols, ["minXVelocity"]),
        "maxXVelocity": pick_first_column(cols, ["maxXVelocity"]),
        "meanXVelocity": pick_first_column(cols, ["meanXVelocity"]),
        "minDHW": pick_first_column(cols, ["minDHW"]),
        "minTHW": pick_first_column(cols, ["minTHW"]),
        "minTTC": pick_first_column(cols, ["minTTC"]),
        "numLaneChanges": pick_first_column(cols, ["numLaneChanges"]),
    }
    if source_map["id"] is None:
        raise ValueError(f"meta file missing id/trackId column: {meta_csv}")

    usecols = sorted({v for v in source_map.values() if v is not None})
    raw = pd.read_csv(meta_csv, usecols=usecols, low_memory=False)

    out = pd.DataFrame()
    for target, src in source_map.items():
        if src is None:
            continue
        out[target] = raw[src]

    if "height" not in out.columns:
        out["height"] = 0.0
    if "width" not in out.columns:
        out["width"] = 0.0
    if "initialFrame" not in out.columns:
        out["initialFrame"] = 0
    if "finalFrame" not in out.columns:
        out["finalFrame"] = out["initialFrame"]
    if "numFrames" not in out.columns:
        out["numFrames"] = (out["finalFrame"] - out["initialFrame"] + 1).clip(lower=0)
    if "class" not in out.columns:
        out["class"] = ""
    for c in [
        "drivingDirection",
        "traveledDistance",
        "minXVelocity",
        "maxXVelocity",
        "meanXVelocity",
        "minDHW",
        "minTHW",
        "minTTC",
        "numLaneChanges",
    ]:
        if c not in out.columns:
            out[c] = np.nan

    out["id"] = out["id"].astype(np.int32)
    return out[
        [
            "id",
            "width",
            "height",
            "initialFrame",
            "finalFrame",
            "numFrames",
            "class",
            "drivingDirection",
            "traveledDistance",
            "minXVelocity",
            "maxXVelocity",
            "meanXVelocity",
            "minDHW",
            "minTHW",
            "minTTC",
            "numLaneChanges",
        ]
    ]


def load_track_summary(track_csv: Path) -> pd.DataFrame:
    header = pd.read_csv(track_csv, nrows=0, low_memory=False)
    cols = list(header.columns)
    source_map: Dict[str, Optional[str]] = {
        "frame": pick_first_column(cols, ["frame"]),
        "id": pick_first_column(cols, ["id", "trackId"]),
        "laneId": pick_first_column(cols, ["laneId", "laneletId"]),
        "ttc": pick_first_column(cols, ["ttc", "leadTTC"]),
        "thw": pick_first_column(cols, ["thw", "leadTHW"]),
        "dhw": pick_first_column(cols, ["dhw", "leadDHW"]),
        "xVelocity": pick_first_column(cols, ["xVelocity"]),
        "yVelocity": pick_first_column(cols, ["yVelocity"]),
        "laneChangeRaw": pick_first_column(cols, ["laneChange"]),
    }
    if source_map["frame"] is None or source_map["id"] is None:
        raise ValueError(f"track file missing frame/id columns: {track_csv}")

    usecols = sorted({v for v in source_map.values() if v is not None})
    df = pd.read_csv(track_csv, usecols=usecols, low_memory=False)

    rename: Dict[str, str] = {}
    for target, src in source_map.items():
        if src is not None and src != target:
            rename[src] = target
    if rename:
        df = df.rename(columns=rename)

    if "laneId" not in df.columns:
        df["laneId"] = 0
    if "ttc" not in df.columns:
        df["ttc"] = np.nan
    if "thw" not in df.columns:
        df["thw"] = np.nan
    if "dhw" not in df.columns:
        df["dhw"] = np.nan
    if "xVelocity" not in df.columns:
        df["xVelocity"] = 0.0
    if "yVelocity" not in df.columns:
        df["yVelocity"] = 0.0

    df["frame"] = pd.to_numeric(df["frame"], errors="coerce").fillna(0).astype(np.int32)
    df["id"] = pd.to_numeric(df["id"], errors="coerce").fillna(-1).astype(np.int32)
    df["laneId"] = pd.to_numeric(df["laneId"], errors="coerce").fillna(0).astype(np.int32)
    df["ttc"] = pd.to_numeric(df["ttc"], errors="coerce").astype(np.float32)
    df["thw"] = pd.to_numeric(df["thw"], errors="coerce").astype(np.float32)
    df["dhw"] = pd.to_numeric(df["dhw"], errors="coerce").astype(np.float32)
    df["xVelocity"] = pd.to_numeric(df["xVelocity"], errors="coerce").fillna(0.0).astype(np.float32)
    df["yVelocity"] = pd.to_numeric(df["yVelocity"], errors="coerce").fillna(0.0).astype(np.float32)

    df = df[df["id"] >= 0].copy()
    df = df.sort_values(["id", "frame"], kind="mergesort")

    if "laneChangeRaw" in df.columns:
        lc_raw = pd.to_numeric(df["laneChangeRaw"], errors="coerce").fillna(0.0)
        lane_change_flag = lc_raw > 0
    else:
        prev_lane = df.groupby("id", sort=False)["laneId"].shift(1)
        lane_change_flag = prev_lane.notna() & (df["laneId"] != prev_lane)
    df["lane_change_flag"] = lane_change_flag.astype(bool)

    df["ttc_pos"] = df["ttc"].where(df["ttc"] > 0, np.nan)
    df["thw_pos"] = df["thw"].where(df["thw"] > 0, np.nan)
    df["dhw_pos"] = df["dhw"].where(df["dhw"] > 0, np.nan)
    df["y_abs"] = np.abs(df["yVelocity"].astype(np.float32))

    g = df.groupby("id", sort=False)
    agg = g.agg(
        frame_start=("frame", "min"),
        frame_end=("frame", "max"),
        num_rows=("frame", "size"),
        mean_xVelocity_track=("xVelocity", "mean"),
        max_abs_yVelocity=("y_abs", "max"),
        min_ttc_pos=("ttc_pos", "min"),
        min_thw_pos=("thw_pos", "min"),
        min_dhw_pos=("dhw_pos", "min"),
    )

    lane_change_cnt = g["lane_change_flag"].sum().astype(np.int32)
    first_lc_frame = df.loc[df["lane_change_flag"], ["id", "frame"]].groupby("id", sort=False)["frame"].min()

    ttc_idx = df.loc[df["ttc_pos"].notna()].groupby("id", sort=False)["ttc_pos"].idxmin()
    thw_idx = df.loc[df["thw_pos"].notna()].groupby("id", sort=False)["thw_pos"].idxmin()

    frame_min_ttc = (
        df.loc[ttc_idx, ["id", "frame"]].drop_duplicates(subset=["id"]).set_index("id")["frame"]
        if len(ttc_idx) > 0
        else pd.Series(dtype=np.int32)
    )
    frame_min_thw = (
        df.loc[thw_idx, ["id", "frame"]].drop_duplicates(subset=["id"]).set_index("id")["frame"]
        if len(thw_idx) > 0
        else pd.Series(dtype=np.int32)
    )

    agg["lane_change_count_track"] = lane_change_cnt
    agg["first_lc_frame"] = first_lc_frame
    agg["frame_min_ttc"] = frame_min_ttc
    agg["frame_min_thw"] = frame_min_thw
    agg["duration_frames"] = (agg["frame_end"] - agg["frame_start"] + 1).astype(np.int32)

    return agg.reset_index()


def lane_score(row: Dict[str, Any]) -> float:
    lc = float(max(float(row.get("lane_change_count_track", 0)), float(row.get("numLaneChanges_meta", 0))))
    yv = as_nonneg_float(row.get("max_abs_yVelocity", 0))
    dur = as_nonneg_float(row.get("duration_frames", 0))
    return float(
        0.60 * clip01(lc / 2.0)
        + 0.25 * clip01(yv / 1.5)
        + 0.15 * clip01(dur / 200.0)
    )


def rear_score(row: Dict[str, Any]) -> float:
    ttc = as_opt_float(row.get("min_ttc_eff"))
    thw = as_opt_float(row.get("min_thw_eff"))
    dhw = as_opt_float(row.get("min_dhw_eff"))
    ttc_term = clip01((2.0 - ttc) / 2.0) if ttc is not None else 0.0
    thw_term = clip01((1.2 - thw) / 1.2) if thw is not None else 0.0
    dhw_term = clip01((15.0 - dhw) / 15.0) if dhw is not None else 0.0
    return float(0.55 * ttc_term + 0.35 * thw_term + 0.10 * dhw_term)


def neg_hardness(row: Dict[str, Any]) -> float:
    ttc = as_opt_float(row.get("min_ttc_eff"))
    thw = as_opt_float(row.get("min_thw_eff"))
    if ttc is None and thw is None:
        return 0.0
    ttc_h = 0.0 if ttc is None else clip01((4.0 - ttc) / 2.0)
    thw_h = 0.0 if thw is None else clip01((2.5 - thw) / 1.3)
    return float(0.55 * ttc_h + 0.45 * thw_h)


def make_sample_id(recording_id: int, vehicle_id: int, kind: str, dataset_tag: str) -> str:
    return f"{dataset_tag}_r{recording_id:02d}_id{vehicle_id:05d}_{kind}"


def choose_frame_hint(row: Dict[str, Any], kind: str) -> int:
    if kind == "lane_pos":
        f = row.get("first_lc_frame")
        if f is not None and not (isinstance(f, float) and math.isnan(f)):
            return int(f)
    if kind == "rear_risk_pos":
        f = row.get("frame_min_ttc")
        if f is not None and not (isinstance(f, float) and math.isnan(f)):
            return int(f)
        f = row.get("frame_min_thw")
        if f is not None and not (isinstance(f, float) and math.isnan(f)):
            return int(f)
    fs = int(row.get("frame_start", 0))
    fe = int(row.get("frame_end", fs))
    return int((fs + fe) // 2)


def stratified_pick(
    rows: List[Dict[str, Any]],
    target_n: int,
    score_key: str,
    seed: int,
) -> List[Dict[str, Any]]:
    if target_n <= 0:
        return []
    if len(rows) <= target_n:
        return list(rows)

    rng = np.random.default_rng(seed)
    grouped: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        grouped[int(r["recording_id"])].append(r)

    for rec, items in grouped.items():
        rng.shuffle(items)
        items.sort(key=lambda x: float(x.get(score_key, 0.0)), reverse=True)
        grouped[rec] = items

    recs = sorted(grouped.keys())
    cursors = {r: 0 for r in recs}
    picked: List[Dict[str, Any]] = []
    used = set()

    while len(picked) < target_n:
        progressed = False
        for rec in recs:
            cur = cursors[rec]
            items = grouped[rec]
            while cur < len(items):
                key = items[cur]["_event_key"]
                cur += 1
                if key in used:
                    continue
                used.add(key)
                picked.append(items[cur - 1])
                progressed = True
                break
            cursors[rec] = cur
            if len(picked) >= target_n:
                break
        if not progressed:
            break

    if len(picked) < target_n:
        rest: List[Dict[str, Any]] = []
        for rec in recs:
            for i in range(cursors[rec], len(grouped[rec])):
                r = grouped[rec][i]
                if r["_event_key"] in used:
                    continue
                rest.append(r)
        rest.sort(key=lambda x: float(x.get(score_key, 0.0)), reverse=True)
        need = target_n - len(picked)
        picked.extend(rest[:need])
    return picked


def build_candidates(
    merged: pd.DataFrame,
    recording_id: int,
    cfg: BuildConfig,
    dataset_name: str,
    dataset_tag: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    lane_rows: List[Dict[str, Any]] = []
    rear_rows: List[Dict[str, Any]] = []
    neg_rows: List[Dict[str, Any]] = []

    quick = {
        "tracks_total": int(len(merged)),
        "lane_pos": 0,
        "rear_pos": 0,
        "neg_hard": 0,
    }

    for _, rr in merged.iterrows():
        row = rr.to_dict()
        vehicle_id = int(row["id"])

        meta_lc = as_nonneg_float(row.get("numLaneChanges", 0))
        track_lc = as_nonneg_float(row.get("lane_change_count_track", 0))
        lc_eff = max(meta_lc, track_lc)

        min_ttc_eff = as_opt_float(row.get("min_ttc_pos"))
        if min_ttc_eff is None:
            min_ttc_eff = as_opt_float(row.get("minTTC"))
        min_thw_eff = as_opt_float(row.get("min_thw_pos"))
        if min_thw_eff is None:
            min_thw_eff = as_opt_float(row.get("minTHW"))
        min_dhw_eff = as_opt_float(row.get("min_dhw_pos"))
        if min_dhw_eff is None:
            min_dhw_eff = as_opt_float(row.get("minDHW"))

        base: Dict[str, Any] = {
            "source_dataset": dataset_name,
            "recording_id": int(recording_id),
            "vehicle_id": int(vehicle_id),
            "class": str(row.get("class", "")),
            "driving_direction": int(safe_float(row.get("drivingDirection")) or 0),
            "frame_start": int(row.get("frame_start", row.get("initialFrame", 0))),
            "frame_end": int(row.get("frame_end", row.get("finalFrame", 0))),
            "duration_frames": int(row.get("duration_frames", row.get("numFrames", 0))),
            "mean_x_velocity": round(as_nonneg_float(row.get("meanXVelocity")), 6),
            "max_abs_y_velocity": round(as_nonneg_float(row.get("max_abs_yVelocity")), 6),
            "numLaneChanges_meta": round(meta_lc, 6),
            "lane_change_count_track": int(track_lc),
            "min_ttc_eff": None if min_ttc_eff is None else round(float(min_ttc_eff), 6),
            "min_thw_eff": None if min_thw_eff is None else round(float(min_thw_eff), 6),
            "min_dhw_eff": None if min_dhw_eff is None else round(float(min_dhw_eff), 6),
            "first_lc_frame": None if pd.isna(row.get("first_lc_frame")) else int(row.get("first_lc_frame")),
            "frame_min_ttc": None if pd.isna(row.get("frame_min_ttc")) else int(row.get("frame_min_ttc")),
            "frame_min_thw": None if pd.isna(row.get("frame_min_thw")) else int(row.get("frame_min_thw")),
        }

        work = dict(base)
        work["min_ttc_eff"] = min_ttc_eff
        work["min_thw_eff"] = min_thw_eff
        work["min_dhw_eff"] = min_dhw_eff

        ls = lane_score(work)
        rs = rear_score(work)
        nh = neg_hardness(work)

        has_lane = lc_eff > 0
        rear_cond = (
            (min_ttc_eff is not None and min_ttc_eff <= cfg.rear_max_ttc)
            or (min_thw_eff is not None and min_thw_eff <= cfg.rear_max_thw)
        )
        is_rear = rear_cond and (rs >= cfg.rear_min_score) and (lc_eff == 0)
        neg_safe = (
            (min_ttc_eff is None or min_ttc_eff >= cfg.neg_min_ttc)
            and (min_thw_eff is None or min_thw_eff >= cfg.neg_min_thw)
            and int(work["duration_frames"]) >= cfg.neg_min_frames
            and (lc_eff == 0)
        )

        if has_lane:
            event = dict(base)
            event.update(
                {
                    "sample_id": make_sample_id(recording_id, vehicle_id, "lane", dataset_tag),
                    "candidate_type": "lane_pos",
                    "prefill_accident_type": "lane_change",
                    "prefill_label": "lane_change",
                    "score": round(float(ls), 6),
                    "frame_hint": choose_frame_hint(base, "lane_pos"),
                }
            )
            event["_event_key"] = f"{recording_id}:{vehicle_id}:lane_pos"
            lane_rows.append(event)
            quick["lane_pos"] += 1

        if is_rear:
            event = dict(base)
            event.update(
                {
                    "sample_id": make_sample_id(recording_id, vehicle_id, "rear", dataset_tag),
                    "candidate_type": "rear_risk_pos",
                    "prefill_accident_type": "rear_end",
                    "prefill_label": "rear_end",
                    "score": round(float(rs), 6),
                    "frame_hint": choose_frame_hint(base, "rear_risk_pos"),
                }
            )
            event["_event_key"] = f"{recording_id}:{vehicle_id}:rear_risk_pos"
            rear_rows.append(event)
            quick["rear_pos"] += 1

        if neg_safe:
            event = dict(base)
            event.update(
                {
                    "sample_id": make_sample_id(recording_id, vehicle_id, "neg", dataset_tag),
                    "candidate_type": "hard_neg",
                    "prefill_accident_type": "",
                    "prefill_label": "hard_negative",
                    "score": round(float(nh), 6),
                    "frame_hint": choose_frame_hint(base, "hard_neg"),
                }
            )
            event["_event_key"] = f"{recording_id}:{vehicle_id}:hard_neg"
            neg_rows.append(event)
            quick["neg_hard"] += 1

    return lane_rows, rear_rows, neg_rows, quick


def summarize_by_recording(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
    for r in rows:
        rec = str(r["recording_id"])
        typ = str(r["candidate_type"])
        if rec not in out:
            out[rec] = {"lane_pos": 0, "rear_risk_pos": 0, "hard_neg": 0, "total": 0}
        out[rec][typ] = out[rec].get(typ, 0) + 1
        out[rec]["total"] += 1
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            obj = {k: v for k, v in r.items() if not k.startswith("_")}
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(1024 * 1024)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def build_markdown_summary(report: Dict[str, Any], md_path: Path, dataset_name: str) -> None:
    lines: List[str] = []
    lines.append(f"# {dataset_name} Event Pool Build Summary")
    lines.append("")
    lines.append(f"- run_at: {report['run_at']}")
    lines.append(f"- input_data_dir: {report['input_data_dir']}")
    lines.append(f"- recordings: {report['recordings']}")
    lines.append("")
    lines.append("## Selection Targets")
    lines.append("")
    cfg = report["config"]
    lines.append(f"- lane_target: {cfg['lane_target']}")
    lines.append(f"- rear_target: {cfg['rear_target']}")
    lines.append(f"- neg_target: {cfg['neg_target']}")
    lines.append("")
    lines.append("## Candidate Totals (Before Selection)")
    lines.append("")
    c = report["candidates_total"]
    lines.append(f"- lane_pos: {c['lane_pos']}")
    lines.append(f"- rear_risk_pos: {c['rear_risk_pos']}")
    lines.append(f"- hard_neg: {c['hard_neg']}")
    lines.append("")
    lines.append("## Selected Totals")
    lines.append("")
    s = report["selected_total"]
    lines.append(f"- lane_pos: {s['lane_pos']}")
    lines.append(f"- rear_risk_pos: {s['rear_risk_pos']}")
    lines.append(f"- hard_neg: {s['hard_neg']}")
    lines.append(f"- total: {s['total']}")
    lines.append("")
    lines.append("## Quality Checks")
    lines.append("")
    q = report["quality_checks"]
    lines.append(f"- lane_has_lc_ratio: {q['lane_has_lc_ratio']:.4f}")
    lines.append(f"- rear_ttc_or_thw_risk_ratio: {q['rear_ttc_or_thw_risk_ratio']:.4f}")
    lines.append(f"- neg_safe_ratio: {q['neg_safe_ratio']:.4f}")
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    for k, v in report["outputs"].items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build event pool + quality report + reproducibility checklist.")
    parser.add_argument("--data-dir", default="", help="Directory with XX_tracks.csv / XX_tracksMeta.csv")
    parser.add_argument("--highd-data-dir", default="", help="Legacy alias of --data-dir")
    parser.add_argument("--dataset-name", default="highD", help="Dataset name written to outputs, e.g. highD/exiD")
    parser.add_argument("--recordings", default="1-30", help="Recording ids, e.g. 1-30 or 1,2,3")
    parser.add_argument("--out-event-pool", required=True, help="Output selected event pool jsonl")
    parser.add_argument("--out-quality-report", required=True, help="Output quality report json")
    parser.add_argument("--out-repro-checklist", required=True, help="Output reproducibility checklist json")
    parser.add_argument("--out-summary-md", default="", help="Optional summary markdown")
    parser.add_argument("--lane-target", type=int, default=300)
    parser.add_argument("--rear-target", type=int, default=150)
    parser.add_argument("--neg-target", type=int, default=150)
    parser.add_argument("--rear-max-ttc", type=float, default=2.0)
    parser.add_argument("--rear-max-thw", type=float, default=1.2)
    parser.add_argument("--rear-min-score", type=float, default=0.45)
    parser.add_argument("--neg-min-ttc", type=float, default=4.0)
    parser.add_argument("--neg-min-thw", type=float, default=2.5)
    parser.add_argument("--neg-min-frames", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    raw_data_dir = str(args.data_dir).strip() or str(args.highd_data_dir).strip()
    if not raw_data_dir:
        raise ValueError("missing data directory: pass --data-dir (or legacy --highd-data-dir)")
    data_dir = Path(raw_data_dir).resolve()
    if not data_dir.exists():
        raise FileNotFoundError(f"data-dir not found: {data_dir}")

    dataset_name = str(args.dataset_name).strip() or "dataset"
    dataset_tag = normalize_dataset_tag(dataset_name)

    recs = parse_recording_range(args.recordings)
    cfg = BuildConfig(
        lane_target=int(args.lane_target),
        rear_target=int(args.rear_target),
        neg_target=int(args.neg_target),
        rear_max_ttc=float(args.rear_max_ttc),
        rear_max_thw=float(args.rear_max_thw),
        rear_min_score=float(args.rear_min_score),
        neg_min_ttc=float(args.neg_min_ttc),
        neg_min_thw=float(args.neg_min_thw),
        neg_min_frames=int(args.neg_min_frames),
        seed=int(args.seed),
    )

    all_lane: List[Dict[str, Any]] = []
    all_rear: List[Dict[str, Any]] = []
    all_neg: List[Dict[str, Any]] = []
    input_manifest: List[Dict[str, Any]] = []
    quick_by_recording: Dict[str, Dict[str, int]] = {}

    for rec in recs:
        rec_name = f"{rec:02d}"
        track_csv = data_dir / f"{rec_name}_tracks.csv"
        meta_csv = data_dir / f"{rec_name}_tracksMeta.csv"
        if not track_csv.exists() or not meta_csv.exists():
            raise FileNotFoundError(f"missing track files for recording {rec_name}")

        print(f"[INFO] processing {dataset_name} recording {rec_name} ...")
        meta_df = load_meta(meta_csv)
        track_summary_df = load_track_summary(track_csv)
        merged = meta_df.merge(track_summary_df, on="id", how="left")

        lane_rows, rear_rows, neg_rows, quick = build_candidates(merged, rec, cfg, dataset_name, dataset_tag)
        quick_by_recording[rec_name] = quick
        all_lane.extend(lane_rows)
        all_rear.extend(rear_rows)
        all_neg.extend(neg_rows)

        input_manifest.append(
            {
                "recording_id": rec,
                "tracks_file": str(track_csv),
                "tracks_size": int(track_csv.stat().st_size),
                "tracksMeta_file": str(meta_csv),
                "tracksMeta_size": int(meta_csv.stat().st_size),
            }
        )
        print(
            f"[INFO] rec={rec_name} tracks={quick['tracks_total']} "
            f"lane={quick['lane_pos']} rear={quick['rear_pos']} neg={quick['neg_hard']}"
        )

    lane_sel = stratified_pick(all_lane, cfg.lane_target, "score", cfg.seed + 1)
    rear_sel = stratified_pick(all_rear, cfg.rear_target, "score", cfg.seed + 2)
    neg_sel = stratified_pick(all_neg, cfg.neg_target, "score", cfg.seed + 3)

    selected = lane_sel + rear_sel + neg_sel
    selected.sort(key=lambda x: (int(x["recording_id"]), str(x["candidate_type"]), -float(x["score"]), int(x["vehicle_id"])))

    # Quality checks on selected pool
    lane_ok = 0
    for r in lane_sel:
        if max(float(r.get("numLaneChanges_meta", 0)), float(r.get("lane_change_count_track", 0))) > 0:
            lane_ok += 1
    rear_ok = 0
    for r in rear_sel:
        ttc = as_opt_float(r.get("min_ttc_eff"))
        thw = as_opt_float(r.get("min_thw_eff"))
        if (ttc is not None and ttc <= cfg.rear_max_ttc) or (thw is not None and thw <= cfg.rear_max_thw):
            rear_ok += 1
    neg_ok = 0
    for r in neg_sel:
        ttc = as_opt_float(r.get("min_ttc_eff"))
        thw = as_opt_float(r.get("min_thw_eff"))
        if (ttc is None or ttc >= cfg.neg_min_ttc) and (thw is None or thw >= cfg.neg_min_thw):
            neg_ok += 1

    out_event_pool = Path(args.out_event_pool).resolve()
    out_quality = Path(args.out_quality_report).resolve()
    out_repro = Path(args.out_repro_checklist).resolve()
    out_md = Path(args.out_summary_md).resolve() if str(args.out_summary_md).strip() else None

    write_jsonl(out_event_pool, selected)

    report: Dict[str, Any] = {
        "run_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "dataset_name": dataset_name,
        "input_data_dir": str(data_dir),
        "recordings": recs,
        "config": {
            "lane_target": cfg.lane_target,
            "rear_target": cfg.rear_target,
            "neg_target": cfg.neg_target,
            "rear_max_ttc": cfg.rear_max_ttc,
            "rear_max_thw": cfg.rear_max_thw,
            "rear_min_score": cfg.rear_min_score,
            "neg_min_ttc": cfg.neg_min_ttc,
            "neg_min_thw": cfg.neg_min_thw,
            "neg_min_frames": cfg.neg_min_frames,
            "seed": cfg.seed,
        },
        "quick_by_recording": quick_by_recording,
        "candidates_total": {
            "lane_pos": len(all_lane),
            "rear_risk_pos": len(all_rear),
            "hard_neg": len(all_neg),
        },
        "selected_total": {
            "lane_pos": len(lane_sel),
            "rear_risk_pos": len(rear_sel),
            "hard_neg": len(neg_sel),
            "total": len(selected),
        },
        "selected_by_recording": summarize_by_recording(selected),
        "quality_checks": {
            "lane_has_lc_ratio": float(lane_ok / len(lane_sel)) if lane_sel else 0.0,
            "rear_ttc_or_thw_risk_ratio": float(rear_ok / len(rear_sel)) if rear_sel else 0.0,
            "neg_safe_ratio": float(neg_ok / len(neg_sel)) if neg_sel else 0.0,
        },
        "top_samples": {
            "lane_top5": [
                {"sample_id": r["sample_id"], "recording_id": r["recording_id"], "score": r["score"]}
                for r in sorted(lane_sel, key=lambda x: float(x["score"]), reverse=True)[:5]
            ],
            "rear_top5": [
                {"sample_id": r["sample_id"], "recording_id": r["recording_id"], "score": r["score"]}
                for r in sorted(rear_sel, key=lambda x: float(x["score"]), reverse=True)[:5]
            ],
            "neg_top5": [
                {"sample_id": r["sample_id"], "recording_id": r["recording_id"], "score": r["score"]}
                for r in sorted(neg_sel, key=lambda x: float(x["score"]), reverse=True)[:5]
            ],
        },
        "outputs": {
            "event_pool_jsonl": str(out_event_pool),
            "quality_report_json": str(out_quality),
            "repro_checklist_json": str(out_repro),
        },
    }

    out_quality.parent.mkdir(parents=True, exist_ok=True)
    out_quality.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    repro: Dict[str, Any] = {
        "purpose": f"Rebuild {dataset_name} event pool deterministically",
        "run_at": report["run_at"],
        "rerun_command": (
            "python backend/scripts/build_highd_event_pool.py "
            f"--data-dir \"{data_dir}\" "
            f"--dataset-name \"{dataset_name}\" "
            f"--recordings \"{args.recordings}\" "
            f"--out-event-pool \"{out_event_pool}\" "
            f"--out-quality-report \"{out_quality}\" "
            f"--out-repro-checklist \"{out_repro}\" "
            + (f"--out-summary-md \"{out_md}\" " if out_md else "")
            + f"--lane-target {cfg.lane_target} --rear-target {cfg.rear_target} --neg-target {cfg.neg_target} "
            + f"--rear-max-ttc {cfg.rear_max_ttc} --rear-max-thw {cfg.rear_max_thw} --rear-min-score {cfg.rear_min_score} "
            + f"--neg-min-ttc {cfg.neg_min_ttc} --neg-min-thw {cfg.neg_min_thw} --neg-min-frames {cfg.neg_min_frames} "
            + f"--seed {cfg.seed}"
        ).strip(),
        "inputs": input_manifest,
        "outputs": [
            {
                "path": str(out_event_pool),
                "size": int(out_event_pool.stat().st_size),
                "sha256": sha256_file(out_event_pool),
            },
            {
                "path": str(out_quality),
                "size": int(out_quality.stat().st_size),
                "sha256": sha256_file(out_quality),
            },
        ],
        "selection_targets": {
            "lane_target": cfg.lane_target,
            "rear_target": cfg.rear_target,
            "neg_target": cfg.neg_target,
        },
        "notes": [
            "The selected pool is stratified by recording id and sorted by per-type confidence score.",
            "Use this checklist to verify inputs and output hashes before downstream experiments.",
        ],
    }
    out_repro.parent.mkdir(parents=True, exist_ok=True)
    out_repro.write_text(json.dumps(repro, ensure_ascii=False, indent=2), encoding="utf-8")

    if out_md is not None:
        build_markdown_summary(report, out_md, dataset_name)

    print(
        json.dumps(
            {
                "event_pool": str(out_event_pool),
                "quality_report": str(out_quality),
                "repro_checklist": str(out_repro),
                "selected_total": len(selected),
                "selected_breakdown": report["selected_total"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
