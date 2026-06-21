#!/usr/bin/env python3
import argparse
import csv
import json
import math
import platform
import random
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


DEADLINES_MS_DEFAULT = [0.005, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]


def percentile(sorted_vals: np.ndarray, q: float) -> float:
    if len(sorted_vals) == 0:
        return float('nan')
    return float(np.quantile(sorted_vals, q / 100.0, method='linear'))


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return float(default)


def detect_machine_info() -> Dict[str, Any]:
    info = {
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'python_executable': sys.executable,
        'processor': platform.processor(),
        'machine': platform.machine(),
        'cpu_count': None,
        'memory_total_gb': None,
        'gpu': 'not_detected',
    }
    try:
        import psutil  # type: ignore
        info['cpu_count'] = psutil.cpu_count(logical=True)
        info['memory_total_gb'] = round(psutil.virtual_memory().total / (1024 ** 3), 3)
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader'],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3,
        ).strip()
        if out:
            info['gpu'] = out.splitlines()
    except Exception:
        pass
    return info


@dataclass
class ReplayRow:
    case_id: str
    board_id: str
    gt_type: str
    pred_after_h3: str
    pred_after_locked_v1: str
    locked_v1_route: str


def load_locked_diff(path: Path) -> List[ReplayRow]:
    rows: List[ReplayRow] = []
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(
                ReplayRow(
                    case_id=str(r.get('case_id', '')),
                    board_id=str(r.get('board_id', '')),
                    gt_type=str(r.get('gt_type', '')),
                    pred_after_h3=str(r.get('pred_after_h3', '')),
                    pred_after_locked_v1=str(r.get('pred_after_locked_v1', '')),
                    locked_v1_route=str(r.get('locked_v1_route', 'KEEP_H3')),
                )
            )
    if not rows:
        raise RuntimeError(f'No rows in {path}')
    return rows


def run_timing(
    rows: List[ReplayRow],
    repeat: int,
    warmup: int,
    seed: int,
    preloaded: bool,
) -> List[Dict[str, Any]]:
    random.seed(seed)
    np.random.seed(seed)

    data = rows
    total_iters = len(data) * repeat
    warmup_iters = int(warmup)

    out: List[Dict[str, Any]] = []

    # small fixed dictionaries simulate lookup paths
    base_lookup = {r.case_id: r.pred_after_h3 for r in data}
    fusion_lookup = {r.case_id: r.pred_after_locked_v1 for r in data}

    iter_idx = 0
    for rep in range(repeat):
        for i, r in enumerate(data):
            # T_load_or_fetch
            t0 = time.perf_counter_ns()
            if preloaded:
                _ = data[i]  # preloaded fetch path
            else:
                # emulate minimal record fetch serialization path
                _ = (r.case_id, r.board_id, r.gt_type)
            t1 = time.perf_counter_ns()

            # T_base_replay_lookup
            _b0 = time.perf_counter_ns()
            base_pred = base_lookup.get(r.case_id, '')
            _b1 = time.perf_counter_ns()

            # T_fusion_replay_lookup
            _f0 = time.perf_counter_ns()
            fusion_pred = fusion_lookup.get(r.case_id, '')
            _f1 = time.perf_counter_ns()

            # T_guard
            _g0 = time.perf_counter_ns()
            route = r.locked_v1_route
            if route in {'LOWCONF_RELEASE', 'REENTRY_RELEASE', 'THIRD_SUBFRONTIER_RELEASE'}:
                action = 'FUSION_BOOST'
            elif route in {'HARD_BOUNDARY_KEEP'}:
                action = 'DEFER'
            else:
                action = 'KEEP_BASELINE'
            # tiny predicate touch
            _ = (base_pred != fusion_pred) and (r.gt_type != '')
            _g1 = time.perf_counter_ns()

            # T_route emission
            _r0 = time.perf_counter_ns()
            emitted = action
            _ = hash(emitted)
            _r1 = time.perf_counter_ns()

            t_load_ms = (t1 - t0) / 1e6
            t_base_ms = (_b1 - _b0) / 1e6
            t_fusion_ms = (_f1 - _f0) / 1e6
            t_guard_ms = (_g1 - _g0) / 1e6
            t_route_ms = (_r1 - _r0) / 1e6
            t_total_seq = t_load_ms + t_base_ms + t_fusion_ms + t_guard_ms + t_route_ms
            t_total_par = t_load_ms + max(t_base_ms, t_fusion_ms) + t_guard_ms + t_route_ms

            if iter_idx >= warmup_iters:
                out.append(
                    {
                        'decision_id': len(out) + 1,
                        'rep': rep,
                        'row_idx': i,
                        'case_id': r.case_id,
                        'board_id': r.board_id,
                        'route': route,
                        'action': emitted,
                        'fetch_mode': 'preloaded_fetch' if preloaded else 'on_demand_fetch',
                        'T_load_or_fetch_ms': t_load_ms,
                        'T_base_replay_lookup_ms': t_base_ms,
                        'T_fusion_replay_lookup_ms': t_fusion_ms,
                        'T_guard_ms': t_guard_ms,
                        'T_route_ms': t_route_ms,
                        'T_total_seq_ms': t_total_seq,
                        'T_total_parallel_abstract_ms': t_total_par,
                    }
                )
            iter_idx += 1
    return out


def summarize_timing(vals: np.ndarray) -> Dict[str, float]:
    if len(vals) == 0:
        return {k: float('nan') for k in ['mean', 'median', 'p90', 'p95', 'p99', 'p99_9', 'max', 'std']}
    sv = np.sort(vals)
    return {
        'mean': float(np.mean(vals)),
        'median': float(np.median(vals)),
        'p90': percentile(sv, 90),
        'p95': percentile(sv, 95),
        'p99': percentile(sv, 99),
        'p99_9': percentile(sv, 99.9),
        'max': float(np.max(vals)),
        'std': float(np.std(vals)),
    }


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_deadline_table(raw_rows: List[Dict[str, Any]], deadlines_ms: List[float]) -> List[Dict[str, Any]]:
    seq = np.array([safe_float(r['T_total_seq_ms']) for r in raw_rows], dtype=float)
    par = np.array([safe_float(r['T_total_parallel_abstract_ms']) for r in raw_rows], dtype=float)
    out = []
    for d in deadlines_ms:
        miss_seq = int(np.sum(seq > d))
        miss_par = int(np.sum(par > d))
        total = int(len(seq))
        out.append(
            {
                'deadline_ms': d,
                'total_count': total,
                'miss_count_seq': miss_seq,
                'miss_rate_seq': miss_seq / total if total else float('nan'),
                'miss_count_parallel_abstract': miss_par,
                'miss_rate_parallel_abstract': miss_par / total if total else float('nan'),
            }
        )
    return out


def plot_cdf(seq: np.ndarray, par: np.ndarray, out_png: Path) -> None:
    plt.figure(figsize=(7, 4.5), dpi=220)
    for vals, label in [(seq, 'T_total_seq'), (par, 'T_total_parallel_abstract')]:
        s = np.sort(vals)
        y = np.arange(1, len(s) + 1) / len(s)
        plt.plot(s, y, label=label, linewidth=1.8)
    plt.xlabel('Latency (ms)')
    plt.ylabel('CDF')
    plt.title('End-to-End Decision Latency CDF')
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=220)
    plt.close()


def plot_box(seq: np.ndarray, par: np.ndarray, out_png: Path) -> None:
    plt.figure(figsize=(6.8, 4.2), dpi=220)
    plt.boxplot([seq, par], labels=['T_total_seq', 'T_total_parallel_abstract'], showfliers=False)
    plt.ylabel('Latency (ms)')
    plt.title('End-to-End Decision Latency (Boxplot, no outliers)')
    plt.grid(True, axis='y', alpha=0.25)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=220)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp1: End-to-end timing measurement (replay-based).')
    parser.add_argument('--input', required=True, help='Input locked diff CSV')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--repeat', type=int, default=120)
    parser.add_argument('--warmup', type=int, default=1000)
    parser.add_argument('--preloaded', action='store_true', help='Use preloaded fetch mode')
    parser.add_argument('--policy', default='S16I_LOCKED_V1')
    parser.add_argument('--duration_sec', type=int, default=0, help='Reserved for interface compatibility')
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_locked_diff(input_path)

    raw = run_timing(rows, repeat=args.repeat, warmup=args.warmup, seed=args.seed, preloaded=args.preloaded)

    if len(raw) < 50000:
        raise RuntimeError(f'Insufficient records: {len(raw)} < 50000. Increase repeat.')

    raw_csv = out_dir / 'exp1_timing_raw.csv'
    raw_fields = [
        'decision_id', 'rep', 'row_idx', 'case_id', 'board_id', 'route', 'action', 'fetch_mode',
        'T_load_or_fetch_ms', 'T_base_replay_lookup_ms', 'T_fusion_replay_lookup_ms',
        'T_guard_ms', 'T_route_ms', 'T_total_seq_ms', 'T_total_parallel_abstract_ms'
    ]
    write_csv(raw_csv, raw, raw_fields)

    # summary
    metrics = [
        'T_load_or_fetch_ms', 'T_base_replay_lookup_ms', 'T_fusion_replay_lookup_ms',
        'T_guard_ms', 'T_route_ms', 'T_total_seq_ms', 'T_total_parallel_abstract_ms'
    ]
    summary_rows: List[Dict[str, Any]] = []
    for m in metrics:
        vals = np.array([safe_float(r[m]) for r in raw], dtype=float)
        s = summarize_timing(vals)
        row = {'metric': m}
        row.update(s)
        summary_rows.append(row)

    summary_csv = out_dir / 'exp1_timing_summary.csv'
    write_csv(summary_csv, summary_rows, ['metric', 'mean', 'median', 'p90', 'p95', 'p99', 'p99_9', 'max', 'std'])

    deadlines = DEADLINES_MS_DEFAULT
    miss_rows = build_deadline_table(raw, deadlines)
    miss_csv = out_dir / 'exp1_deadline_miss.csv'
    write_csv(
        miss_csv,
        miss_rows,
        ['deadline_ms', 'total_count', 'miss_count_seq', 'miss_rate_seq', 'miss_count_parallel_abstract', 'miss_rate_parallel_abstract'],
    )

    seq_vals = np.array([safe_float(r['T_total_seq_ms']) for r in raw], dtype=float)
    par_vals = np.array([safe_float(r['T_total_parallel_abstract_ms']) for r in raw], dtype=float)

    plot_cdf(seq_vals, par_vals, out_dir / 'exp1_latency_cdf.png')
    plot_box(seq_vals, par_vals, out_dir / 'exp1_latency_boxplot.png')

    machine = detect_machine_info()

    # summary md
    md = []
    md.append('# Exp1 End-to-End Runtime Timing Summary')
    md.append('')
    md.append('## Purpose')
    md.append('Measurement-based timing of replay-driven guarded admission decision path with stage decomposition.')
    md.append('')
    md.append('## Inputs')
    md.append(f'- input_csv: `{input_path}`')
    md.append(f'- rows: {len(rows)}')
    md.append(f'- repeat: {args.repeat}')
    md.append(f'- warmup_excluded: {args.warmup}')
    md.append(f'- measured_records: {len(raw)}')
    md.append(f'- fetch_mode: {"preloaded_fetch" if args.preloaded else "on_demand_fetch"}')
    md.append('')
    md.append('## Method')
    md.append('- Timing primitive: `time.perf_counter_ns`')
    md.append('- Stages: `T_load_or_fetch`, `T_base_replay_lookup`, `T_fusion_replay_lookup`, `T_guard`, `T_route`')
    md.append('- Aggregates: `T_total_seq` and `T_total_parallel_abstract`')
    md.append('- This is replay-lookup timing, not model inference timing.')
    md.append('')
    md.append('## Machine Info')
    for k, v in machine.items():
        md.append(f'- {k}: {v}')
    md.append('')
    md.append('## Key Results (ms)')
    for row in summary_rows:
        if row['metric'] in {'T_total_seq_ms', 'T_total_parallel_abstract_ms'}:
            md.append(
                f"- {row['metric']}: mean={row['mean']:.6f}, p95={row['p95']:.6f}, p99={row['p99']:.6f}, max={row['max']:.6f}"
            )
    md.append('')
    md.append('## Deadline Miss (selected)')
    for d in [0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]:
        rr = next((x for x in miss_rows if abs(float(x['deadline_ms']) - d) < 1e-12), None)
        if rr:
            md.append(
                f"- D={d} ms: miss_seq={rr['miss_rate_seq']:.6f}, miss_parallel={rr['miss_rate_parallel_abstract']:.6f}"
            )
    md.append('')
    md.append('## Limitations')
    md.append('- Measurement-based only; no WCET certification is claimed.')
    md.append('- Python/OS scheduler jitter may affect ultra-small latency quantiles on Windows.')
    md.append('- Baseline/fusion stages are replay lookups here, not full model inference kernels.')

    (out_dir / 'exp1_timing_summary.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({
        'status': 'ok',
        'out_dir': str(out_dir),
        'raw_records': len(raw),
        'input_rows': len(rows),
        'repeat': args.repeat,
        'warmup': args.warmup,
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
