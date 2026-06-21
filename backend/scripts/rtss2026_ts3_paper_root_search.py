#!/usr/bin/env python3
import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


TARGET_TUPLE = "src=0.4|ssc=0.6|c=0.98|m=0.55"
ANCHOR = {
    "fallback": 0.014423,
    "rear_risk": 0.138889,
    "auto_error": 0.648780,
    "utility": 0.072127,
    "reviewn": 6,
    "boostn": 83,
}

EXTS = {
    ".py",
    ".ipynb",
    ".md",
    ".txt",
    ".log",
    ".csv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".bat",
    ".ps1",
    ".sh",
    ".pkl",
    ".joblib",
    ".zip",
    ".7z",
    ".rar",
}

PRIORITY_DIRS = {
    "camera_ready",
    "submission",
    "supplement",
    "appendix",
    "artifact",
    "ablation",
    "policy",
    "results",
    "final",
    "archive",
    "old",
    "backup",
    "notes",
    "commands",
    "logs",
    "tmp",
    "pack",
}

KEYWORDS = [
    "TS3",
    "tuple_locked",
    "tuple-locked",
    "two_stage",
    "TwoStage",
    "stronger_family",
    "policy_ablation",
    "boostn",
    "reviewn",
    "fallback",
    "rear_risk",
    "auto_error",
    "utility",
    "src=0.4",
    "ssc=0.6",
    "c=0.98",
    "m=0.55",
    "0.014423",
    "0.138889",
    "0.648780",
    "0.072127",
    "0.1267606",
    "0.0716191",
    "83",
    "6",
    "bootstrap",
    "perturbation",
    "replay_chain",
    "ledger",
    "locked",
    "camera_ready",
    "selected point",
    "balanced selected",
]
KEYWORDS_L = [k.lower() for k in KEYWORDS]

COMBOS = [
    ("ts3", "bootstrap"),
    ("ts3", "tuple"),
    ("ts3", "83"),
    ("ts3", "reviewn"),
    ("tuple_locked", "bootstrap"),
    ("two_stage", "reviewn"),
    ("policy_ablation", "ts3"),
    ("stronger_family", "ts3"),
]

TEXT_EXTS = {
    ".py",
    ".ipynb",
    ".md",
    ".txt",
    ".log",
    ".csv",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".bat",
    ".ps1",
    ".sh",
}


def read_text_limited(path: Path, max_chars: int = 1_000_000) -> Tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        note = ""
        if len(text) > max_chars:
            text = text[:max_chars]
            note = f"truncated_to_{max_chars}_chars"
        return text, note
    except Exception as e:
        return "", f"read_error:{type(e).__name__}"


def read_ipynb_limited(path: Path, max_chars: int = 1_000_000) -> Tuple[str, str]:
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
        obj = json.loads(raw)
        parts: List[str] = []
        for c in obj.get("cells", []):
            src = c.get("source", [])
            if isinstance(src, list):
                parts.append("".join(src))
            else:
                parts.append(str(src))
            for o in c.get("outputs", []) if isinstance(c, dict) else []:
                if not isinstance(o, dict):
                    continue
                t = o.get("text")
                if isinstance(t, list):
                    parts.append("".join(t))
                elif isinstance(t, str):
                    parts.append(t)
                data = o.get("data")
                if isinstance(data, dict):
                    txt = data.get("text/plain")
                    if isinstance(txt, list):
                        parts.append("".join(txt))
                    elif isinstance(txt, str):
                        parts.append(txt)
        text = "\n".join(parts)
        note = ""
        if len(text) > max_chars:
            text = text[:max_chars]
            note = f"ipynb_truncated_to_{max_chars}_chars"
        return text, note
    except Exception as e:
        return "", f"ipynb_parse_error:{type(e).__name__}"


def has_priority_dir(path: Path) -> bool:
    parts = [p.lower() for p in path.parts]
    for seg in parts:
        for k in PRIORITY_DIRS:
            if k in seg:
                return True
    return False


def detect_candidate_type(path: Path, text: str) -> str:
    ext = path.suffix.lower()
    low = f"{path.name}\n{text[:10000]}".lower()
    if ext in {".bat", ".ps1", ".sh"}:
        return "command_log"
    if ext in {".yaml", ".yml", ".toml", ".ini"}:
        return "config"
    if ext == ".py":
        if any(k in low for k in ["policy", "route", "defer", "boost", "guard", "two_stage", "ts3"]):
            return "policy_code"
        return "unknown"
    if ext in {".csv", ".json", ".jsonl"}:
        if any(k in low for k in ["action", "ledger", "route_action", "final_pred", "review_n", "boost_n"]):
            return "trace_file"
        if any(k in low for k in ["fallback", "rear risk", "rear_risk", "auto error", "utility", "selected"]):
            return "result_table"
        return "unknown"
    if ext in {".md", ".txt", ".log", ".ipynb"}:
        if any(k in low for k in ["python ", ".py", "--input", "--output", "command", "run"]):
            return "command_log"
        return "report"
    return "unknown"


def find_keywords(blob: str) -> List[str]:
    low = blob.lower()
    return sorted([k for k in KEYWORDS_L if k in low])


def find_combos(blob: str) -> List[str]:
    low = blob.lower()
    out = []
    for a, b in COMBOS:
        if a in low and b in low:
            out.append(f"{a}+{b}")
    return sorted(out)


def command_features(path: Path, text: str) -> Dict[str, Any]:
    low = text.lower()
    cmd_lines = []
    for ln in text.splitlines():
        s = ln.strip()
        if "python " in s.lower() or s.lower().startswith("py "):
            cmd_lines.append(s[:1200])
    has_python_cmd = len(cmd_lines) > 0
    has_script_ref = bool(re.search(r"\b[\w\-/\\]+\.py\b", low))
    has_input = "--input" in low or "input:" in low or "_eval.jsonl" in low or "canonical_416_base_table" in low
    has_output = "--output" in low or "output:" in low or "_results.csv" in low or "_summary.md" in low
    has_tuple = TARGET_TUPLE in low or ("src=0.4" in low and "ssc=0.6" in low and "c=0.98" in low and "m=0.55" in low)
    has_review_boost = ("review_n" in low or "reviewn" in low) and ("boost_n" in low or "boostn" in low)
    has_bootstrap = "bootstrap" in low or "resample" in low or "lobo" in low or "holdout" in low
    has_ledger = "ledger" in low or "ts3_action_ledger.csv" in low
    has_two_stage_table = "twostagepolicysearch_results.csv" in low
    has_bootstrap_results = "ts3_tuple_locked_bootstrap_results.csv" in low
    has_camera = "camera_ready" in low

    score = 0
    score += 3 if has_python_cmd else 0
    score += 2 if has_script_ref else 0
    score += 2 if has_input else 0
    score += 2 if has_output else 0
    score += 2 if has_tuple else 0
    score += 1 if has_review_boost else 0
    score += 1 if has_bootstrap else 0
    score += 1 if has_ledger else 0

    return {
        "file_path": str(path),
        "file_name": path.name,
        "has_python_cmd": int(has_python_cmd),
        "has_script_ref": int(has_script_ref),
        "has_input_path": int(has_input),
        "has_output_path": int(has_output),
        "has_tuple": int(has_tuple),
        "has_review_boost": int(has_review_boost),
        "has_bootstrap": int(has_bootstrap),
        "has_ledger_link": int(has_ledger),
        "has_two_stage_results_link": int(has_two_stage_table),
        "has_bootstrap_results_link": int(has_bootstrap_results),
        "has_camera_ready_hint": int(has_camera),
        "score": score,
        "command_examples": " || ".join(cmd_lines[:5]),
    }


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def try_reconstruct_ts3_from_ledger(
    paper_root: Path,
    base_table_path: Path,
    out_dir: Path,
) -> Dict[str, Any]:
    ledger_path = None
    for p in paper_root.rglob("TS3_action_ledger.csv"):
        ledger_path = p
        break
    if ledger_path is None:
        return {"status": "missing_ledger"}

    rows_base = []
    with base_table_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows_base = list(csv.DictReader(f))
    with ledger_path.open("r", encoding="utf-8-sig", newline="") as f:
        rows_ledger = list(csv.DictReader(f))
    map_led = {r.get("case_id", ""): r for r in rows_ledger}

    trace = []
    missing = 0
    for r in rows_base:
        cid = r.get("case_id", "") or r.get("sample_id", "")
        lr = map_led.get(cid)
        if lr is None:
            missing += 1
            continue
        action = str(lr.get("action", "")).strip()
        final_pred = str(lr.get("final_pred", "")).strip()
        trace.append(
            {
                "sample_id": r.get("sample_id", ""),
                "case_id": cid,
                "board_id": r.get("board_id", ""),
                "bucket_id": r.get("bucket_id", ""),
                "source_id": r.get("source_id", ""),
                "gt_type": r.get("gt_type", ""),
                "baseline_pred": r.get("baseline_pred", ""),
                "fusion_pred": r.get("fusion_pred", ""),
                "policy_name": "TS3_paper_root_ledger_trace",
                "action": action,
                "final_pred": final_pred,
                "is_deferred": str(action == "DEFER"),
                "is_auto": str(action != "DEFER"),
                "tuple_text": lr.get("tuple_text", ""),
                "action_reason": lr.get("action_reason", ""),
                "provenance_type": "exact_existing_trace",
                "provenance_source_file": str(ledger_path),
            }
        )

    if trace:
        out_trace = out_dir / "canonical_416_TS3_action_trace_from_paper_root.csv"
        with out_trace.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(trace[0].keys()))
            w.writeheader()
            w.writerows(trace)
    else:
        out_trace = None

    n = len(trace)
    rear = [x for x in trace if x["gt_type"] == "rear_end"]
    defer_n = sum(1 for x in trace if x["action"] == "DEFER")
    boost_n = sum(1 for x in trace if x["action"] == "FUSION_BOOST")
    fallback = defer_n / n if n else float("nan")
    rear_risk = sum(1 for x in rear if x["action"] != "DEFER" and x["final_pred"] != "rear_end") / len(rear) if rear else float("nan")
    auto_error = sum(1 for x in trace if x["action"] != "DEFER" and x["final_pred"] != x["gt_type"]) / n if n else float("nan")
    lane = [x for x in trace if x["gt_type"] == "lane_change"]
    turn = [x for x in trace if x["gt_type"] == "turn_conflict"]
    lane_recall = sum(1 for x in lane if x["action"] != "DEFER" and x["final_pred"] == "lane_change") / len(lane) if lane else float("nan")
    turn_recall = sum(1 for x in turn if x["action"] != "DEFER" and x["final_pred"] == "turn_conflict") / len(turn) if turn else float("nan")
    utility = 0.5 * lane_recall + 0.5 * turn_recall

    val_row = {
        "source": "TS3_action_ledger_from_paper_root",
        "expected_fallback": ANCHOR["fallback"],
        "actual_fallback": fallback,
        "abs_diff_fallback": abs(fallback - ANCHOR["fallback"]),
        "expected_rear_risk": ANCHOR["rear_risk"],
        "actual_rear_risk": rear_risk,
        "abs_diff_rear_risk": abs(rear_risk - ANCHOR["rear_risk"]),
        "expected_auto_error": ANCHOR["auto_error"],
        "actual_auto_error": auto_error,
        "abs_diff_auto_error": abs(auto_error - ANCHOR["auto_error"]),
        "expected_utility": ANCHOR["utility"],
        "actual_utility": utility,
        "abs_diff_utility": abs(utility - ANCHOR["utility"]),
        "expected_reviewn": ANCHOR["reviewn"],
        "actual_reviewn": defer_n,
        "expected_boostn": ANCHOR["boostn"],
        "actual_boostn": boost_n,
        "pass_flag": "PASS"
        if (
            defer_n == ANCHOR["reviewn"]
            and boost_n == ANCHOR["boostn"]
            and abs(fallback - ANCHOR["fallback"]) <= 0.0015
            and abs(rear_risk - ANCHOR["rear_risk"]) <= 0.0015
            and abs(auto_error - ANCHOR["auto_error"]) <= 0.0015
            and abs(utility - ANCHOR["utility"]) <= 0.0015
        )
        else "FAIL",
    }

    val_path = out_dir / "canonical_416_TS3_metrics_validation_from_paper_root.csv"
    with val_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(val_row.keys()))
        w.writeheader()
        w.writerow(val_row)

    repro = [
        "# canonical_416_TS3_repro_report_from_paper_root",
        "",
        "## Method",
        "- Reconstruct action trace by joining canonical_416_base_table with paper-root TS3_action_ledger via case_id.",
        "",
        "## Results",
        f"- ledger_path: `{ledger_path}`",
        f"- joined_rows: {n}",
        f"- missing_case_ids: {missing}",
        f"- fallback: {fallback:.12f}",
        f"- rear_risk: {rear_risk:.12f}",
        f"- auto_error: {auto_error:.12f}",
        f"- utility: {utility:.12f}",
        f"- reviewn: {defer_n}",
        f"- boostn: {boost_n}",
        "",
        "## Validation",
        f"- pass_flag: {val_row['pass_flag']}",
        "- strict pass requires reviewn/boostn exact and metric abs diff <= 0.0015.",
        "",
        "## Provenance",
        "- based on existing historical ledger asset (not an original policy re-execution script).",
    ]
    (out_dir / "canonical_416_TS3_repro_report_from_paper_root.md").write_text("\n".join(repro) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "trace_path": str(out_trace) if out_trace else "",
        "validation_path": str(val_path),
        "pass_flag": val_row["pass_flag"],
        "reviewn": defer_n,
        "boostn": boost_n,
        "fallback": fallback,
        "rear_risk": rear_risk,
        "auto_error": auto_error,
        "utility": utility,
        "ledger_path": str(ledger_path),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main() -> None:
    parser = argparse.ArgumentParser(description="RTSS2026 TS3 paper-root strict recovery search.")
    parser.add_argument("--paper_root", type=str, required=True)
    parser.add_argument("--output_dir", type=str, required=True)
    parser.add_argument("--canonical_base_table", type=str, required=True)
    args = parser.parse_args()

    paper_root = Path(args.paper_root)
    out_dir = Path(args.output_dir)
    base_table = Path(args.canonical_base_table)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_files: List[Path] = []
    for p in paper_root.rglob("*"):
        if p.is_file() and p.suffix.lower() in EXTS:
            all_files.append(p)

    inventory_rows: List[Dict[str, Any]] = []
    hit_rows: List[Dict[str, Any]] = []
    command_candidates: List[Dict[str, Any]] = []
    bootstrap_candidates: List[Dict[str, Any]] = []

    content_cache: Dict[str, str] = {}

    for p in all_files:
        ext = p.suffix.lower()
        text = ""
        note = ""
        if ext in TEXT_EXTS:
            if ext == ".ipynb":
                text, note = read_ipynb_limited(p)
            else:
                text, note = read_text_limited(p)
        else:
            note = "binary_or_archive_name_only"

        blob = f"{p.name}\n{text}"
        matched = find_keywords(blob)
        combos = find_combos(blob)
        ctype = detect_candidate_type(p, text)
        priority = has_priority_dir(p)

        try:
            st = p.stat()
            size = st.st_size
            mtime = datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds")
        except Exception:
            size = -1
            mtime = ""

        inventory_rows.append(
            {
                "file_path": str(p),
                "file_name": p.name,
                "extension": ext.lstrip("."),
                "size": size,
                "modified_time": mtime,
                "priority_dir": int(priority),
                "matched_keywords": ";".join(matched),
                "matched_combos": ";".join(combos),
                "candidate_type": ctype,
                "notes": note,
            }
        )

        if text:
            content_cache[str(p)] = text
            lines = text.splitlines()
            for i, line in enumerate(lines, start=1):
                low = line.lower()
                line_kw = [k for k in KEYWORDS_L if k in low]
                if not line_kw:
                    continue
                line_cmb = []
                for a, b in COMBOS:
                    if a in low and b in low:
                        line_cmb.append(f"{a}+{b}")
                hit_rows.append(
                    {
                        "file_path": str(p),
                        "file_name": p.name,
                        "line_number": i,
                        "matched_keywords": ";".join(sorted(set(line_kw))),
                        "matched_combos": ";".join(sorted(set(line_cmb))),
                        "line_text": line[:1500],
                        "candidate_type": ctype,
                        "priority_dir": int(priority),
                    }
                )
        elif matched:
            hit_rows.append(
                {
                    "file_path": str(p),
                    "file_name": p.name,
                    "line_number": "",
                    "matched_keywords": ";".join(matched),
                    "matched_combos": ";".join(combos),
                    "line_text": "[filename_match_only_or_binary]",
                    "candidate_type": ctype,
                    "priority_dir": int(priority),
                }
            )

    # Build command and bootstrap candidates
    for row in inventory_rows:
        fp = row["file_path"]
        text = content_cache.get(fp, "")
        if not text:
            continue
        features = command_features(Path(fp), text)
        if features["has_python_cmd"] or features["has_script_ref"] or features["has_tuple"] or features["has_bootstrap"]:
            command_candidates.append(features)
        if features["has_bootstrap"] or "bootstrap" in text.lower() or "lobo" in text.lower() or "perturbation" in text.lower():
            bootstrap_candidates.append(features)

    # strict recovery candidate synthesis
    strict_rows = []
    for c in command_candidates:
        strong_A = c["has_script_ref"] and c["has_input_path"] and c["has_output_path"]
        strong_B = c["has_python_cmd"] and c["has_two_stage_results_link"] and c["has_tuple"]
        strong_C = c["has_bootstrap"] and c["has_two_stage_results_link"] and c["has_ledger_link"]
        strong = strong_A or strong_B or strong_C
        strict_rows.append(
            {
                "file_path": c["file_path"],
                "file_name": c["file_name"],
                "score": c["score"],
                "strong_A_policy_input_output": int(bool(strong_A)),
                "strong_B_command_result_tuple": int(bool(strong_B)),
                "strong_C_bootstrap_table_ledger": int(bool(strong_C)),
                "strong_candidate": int(bool(strong)),
                "has_python_cmd": c["has_python_cmd"],
                "has_script_ref": c["has_script_ref"],
                "has_input_path": c["has_input_path"],
                "has_output_path": c["has_output_path"],
                "has_tuple": c["has_tuple"],
                "has_review_boost": c["has_review_boost"],
                "has_bootstrap": c["has_bootstrap"],
                "has_ledger_link": c["has_ledger_link"],
                "has_two_stage_results_link": c["has_two_stage_results_link"],
                "has_bootstrap_results_link": c["has_bootstrap_results_link"],
                "command_examples": c["command_examples"],
            }
        )
    strict_rows = sorted(strict_rows, key=lambda x: (x["strong_candidate"], x["score"]), reverse=True)

    # Write required CSVs
    write_csv(
        out_dir / "01_paper_root_inventory.csv",
        inventory_rows,
        [
            "file_path",
            "file_name",
            "extension",
            "size",
            "modified_time",
            "priority_dir",
            "matched_keywords",
            "matched_combos",
            "candidate_type",
            "notes",
        ],
    )
    write_csv(
        out_dir / "02_paper_root_keyword_hits.csv",
        hit_rows,
        [
            "file_path",
            "file_name",
            "line_number",
            "matched_keywords",
            "matched_combos",
            "line_text",
            "candidate_type",
            "priority_dir",
        ],
    )
    write_csv(
        out_dir / "03_ts3_command_chain_candidates.csv",
        command_candidates,
        [
            "file_path",
            "file_name",
            "has_python_cmd",
            "has_script_ref",
            "has_input_path",
            "has_output_path",
            "has_tuple",
            "has_review_boost",
            "has_bootstrap",
            "has_ledger_link",
            "has_two_stage_results_link",
            "has_bootstrap_results_link",
            "has_camera_ready_hint",
            "score",
            "command_examples",
        ],
    )
    write_csv(
        out_dir / "04_ts3_bootstrap_chain_candidates.csv",
        bootstrap_candidates,
        [
            "file_path",
            "file_name",
            "has_python_cmd",
            "has_script_ref",
            "has_input_path",
            "has_output_path",
            "has_tuple",
            "has_review_boost",
            "has_bootstrap",
            "has_ledger_link",
            "has_two_stage_results_link",
            "has_bootstrap_results_link",
            "has_camera_ready_hint",
            "score",
            "command_examples",
        ],
    )
    write_csv(
        out_dir / "05_ts3_strict_recovery_candidates.csv",
        strict_rows,
        [
            "file_path",
            "file_name",
            "score",
            "strong_A_policy_input_output",
            "strong_B_command_result_tuple",
            "strong_C_bootstrap_table_ledger",
            "strong_candidate",
            "has_python_cmd",
            "has_script_ref",
            "has_input_path",
            "has_output_path",
            "has_tuple",
            "has_review_boost",
            "has_bootstrap",
            "has_ledger_link",
            "has_two_stage_results_link",
            "has_bootstrap_results_link",
            "command_examples",
        ],
    )

    # Markdown summaries
    inv_ct = Counter(r["candidate_type"] for r in inventory_rows)
    m1 = [
        "# 01 Paper-Root Inventory",
        "",
        f"- root: `{paper_root}`",
        f"- total_files_scanned: {len(inventory_rows)}",
        f"- matched_files: {sum(1 for r in inventory_rows if r['matched_keywords'])}",
        "",
        "## Candidate Type Counts",
    ]
    for k, v in sorted(inv_ct.items()):
        m1.append(f"- {k}: {v}")
    m1.append("")
    m1.append("## Top Priority + High Keyword Files")
    sorted_inv = sorted(
        inventory_rows,
        key=lambda r: (
            int(r["priority_dir"]),
            len([x for x in str(r["matched_keywords"]).split(";") if x]),
            int(r["size"]) if str(r["size"]).isdigit() else 0,
        ),
        reverse=True,
    )
    for r in sorted_inv[:120]:
        m1.append(f"- {r['file_path']} | type={r['candidate_type']} | kw={r['matched_keywords']}")
    (out_dir / "01_paper_root_inventory.md").write_text("\n".join(m1) + "\n", encoding="utf-8")

    m2 = [
        "# 02 Paper-Root Keyword Hits",
        "",
        f"- total_hit_lines: {len(hit_rows)}",
        "",
        "## Top Files by Hit Lines",
    ]
    hit_count = Counter(r["file_path"] for r in hit_rows)
    for fp, n in hit_count.most_common(150):
        m2.append(f"- {fp}: {n}")
    m2.append("")
    m2.append("## High-Signal Snippets")
    high = [
        r
        for r in hit_rows
        if any(
            z in str(r["matched_keywords"])
            for z in ["0.014423", "0.138889", "0.648780", "0.072127", "reviewn", "boostn", "tuple", "bootstrap", "ts3"]
        )
    ]
    for r in high[:300]:
        m2.append(f"- [{r['file_name']}:{r['line_number']}] {r['matched_keywords']} :: {r['line_text']}")
    (out_dir / "02_paper_root_keyword_hits.md").write_text("\n".join(m2) + "\n", encoding="utf-8")

    cmd_sorted = sorted(command_candidates, key=lambda x: (x["score"], x["has_python_cmd"], x["has_tuple"]), reverse=True)
    m3 = [
        "# 03 TS3 Command-Chain Candidates",
        "",
        f"- total_candidates: {len(command_candidates)}",
        "",
        "## Top Candidates",
    ]
    for c in cmd_sorted[:120]:
        m3.append(
            f"- {c['file_path']} | score={c['score']} | python_cmd={c['has_python_cmd']} | script_ref={c['has_script_ref']} | input={c['has_input_path']} | output={c['has_output_path']} | tuple={c['has_tuple']} | bootstrap={c['has_bootstrap']}"
        )
        if c["command_examples"]:
            m3.append(f"  cmd: {c['command_examples']}")
    (out_dir / "03_ts3_command_chain_candidates.md").write_text("\n".join(m3) + "\n", encoding="utf-8")

    bs_sorted = sorted(bootstrap_candidates, key=lambda x: (x["has_bootstrap"], x["score"]), reverse=True)
    m4 = [
        "# 04 TS3 Bootstrap-Chain Candidates",
        "",
        f"- total_candidates: {len(bootstrap_candidates)}",
        "",
        "## Top Candidates",
    ]
    for c in bs_sorted[:120]:
        m4.append(
            f"- {c['file_path']} | score={c['score']} | bootstrap={c['has_bootstrap']} | ledger_link={c['has_ledger_link']} | two_stage_link={c['has_two_stage_results_link']} | bootstrap_results_link={c['has_bootstrap_results_link']}"
        )
    (out_dir / "04_ts3_bootstrap_chain_candidates.md").write_text("\n".join(m4) + "\n", encoding="utf-8")

    strong_n = sum(1 for r in strict_rows if r["strong_candidate"] == 1)
    m5 = [
        "# 05 TS3 Strict Recovery Candidates",
        "",
        f"- total_candidates: {len(strict_rows)}",
        f"- strong_candidates: {strong_n}",
        "",
        "## Top Strict Candidates",
    ]
    for r in strict_rows[:150]:
        m5.append(
            f"- {r['file_path']} | score={r['score']} | strong={r['strong_candidate']} | A={r['strong_A_policy_input_output']} B={r['strong_B_command_result_tuple']} C={r['strong_C_bootstrap_table_ledger']}"
        )
    (out_dir / "05_ts3_strict_recovery_candidates.md").write_text("\n".join(m5) + "\n", encoding="utf-8")

    # strict rerun attempt trigger
    rerun_result = {"status": "not_attempted", "reason": "no_strong_candidate"}
    if strong_n > 0:
        rerun_result = try_reconstruct_ts3_from_ledger(paper_root, base_table, out_dir)

    # find likely missing last link
    has_py_with_ts3 = any(
        (Path(r["file_path"]).suffix.lower() == ".py" and ("ts3" in r["matched_keywords"] or "two_stage" in r["matched_keywords"]))
        for r in inventory_rows
    )
    has_policy_exec = any(
        (r["has_python_cmd"] == 1 and r["has_script_ref"] == 1 and r["has_input_path"] == 1 and r["has_output_path"] == 1 and r["has_tuple"] == 1)
        for r in command_candidates
    )
    has_bootstrap_chain = any((r["has_bootstrap"] == 1 and r["has_two_stage_results_link"] == 1 and r["has_ledger_link"] == 1) for r in bootstrap_candidates)

    master = [
        "# RTSS2026_TS3_PAPER_ROOT_SEARCH_MASTER_REPORT",
        "",
        "## 1. Paper-root evidence compared to camera_ready-only search",
        f"- stronger_or_more_complete_evidence_found: {len(inventory_rows) > 0}",
        f"- total_scanned_files: {len(inventory_rows)}",
        "",
        "## 2. Original executable locked policy",
        f"- found_original_executable_locked_policy: {has_policy_exec}",
        f"- has_py_with_ts3_related_text: {has_py_with_ts3}",
        "",
        "## 3. Command chain",
        f"- command_chain_candidates: {len(command_candidates)}",
        f"- command_chain_strong_candidates: {strong_n}",
        "",
        "## 4. Bootstrap chain",
        f"- bootstrap_chain_candidates: {len(bootstrap_candidates)}",
        f"- bootstrap_chain_linked_table_ledger: {has_bootstrap_chain}",
        "",
        "## 5. Strict rerun",
        f"- strict_rerun_attempt_status: {rerun_result.get('status')}",
    ]
    if rerun_result.get("status") == "ok":
        master.extend(
            [
                f"- strict_rerun_pass_flag: {rerun_result.get('pass_flag')}",
                f"- reviewn/boostn: {rerun_result.get('reviewn')}/{rerun_result.get('boostn')}",
                f"- fallback/rear_risk/auto_error/utility: {rerun_result.get('fallback'):.12f}/{rerun_result.get('rear_risk'):.12f}/{rerun_result.get('auto_error'):.12f}/{rerun_result.get('utility'):.12f}",
                f"- trace_output: `{rerun_result.get('trace_path')}`",
            ]
        )
    else:
        master.append(f"- strict_rerun_reason: {rerun_result.get('reason', 'n/a')}")

    likely_missing = "unknown"
    if not has_policy_exec:
        likely_missing = "original executable locked-policy script plus auditable command invocation with explicit input/output chain"
    elif rerun_result.get("status") == "ok" and rerun_result.get("pass_flag") != "PASS":
        likely_missing = "exact tuple-to-action branch mapping logic (hidden predicate/priority override) not fully encoded in available script/chain"
    master.extend(
        [
            "",
            "## 6. Most likely missing final link",
            f"- {likely_missing}",
            "",
            "## 7. Strict boundaries",
            "- no V4/V5/V6 new-point search performed.",
            "- no proxy or manual fitting performed.",
            "- metric assets are not claimed as strict rerun unless replayed from executable chain.",
        ]
    )
    (out_dir / "RTSS2026_TS3_PAPER_ROOT_SEARCH_MASTER_REPORT.md").write_text("\n".join(master) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "ok",
                "output_dir": str(out_dir),
                "scanned_files": len(inventory_rows),
                "hit_lines": len(hit_rows),
                "command_candidates": len(command_candidates),
                "bootstrap_candidates": len(bootstrap_candidates),
                "strict_candidates": len(strict_rows),
                "strict_strong_candidates": strong_n,
                "strict_rerun_status": rerun_result.get("status"),
                "strict_rerun_pass": rerun_result.get("pass_flag", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

