#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def safe_float(x: Any, default: float = float('nan')) -> float:
    try:
        return float(x)
    except Exception:
        return default


def read_raw(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def compute_table(raw_rows: List[Dict[str, Any]], deadlines_ms: List[float]) -> List[Dict[str, Any]]:
    seq = np.array([safe_float(r.get('T_total_seq_ms', 'nan')) for r in raw_rows], dtype=float)
    par = np.array([safe_float(r.get('T_total_parallel_abstract_ms', 'nan')) for r in raw_rows], dtype=float)

    p99_seq = float(np.quantile(seq, 0.99, method='linear')) if len(seq) else float('nan')
    p99_par = float(np.quantile(par, 0.99, method='linear')) if len(par) else float('nan')

    out = []
    total = int(len(seq))
    for d in deadlines_ms:
        miss_seq = int(np.sum(seq > d))
        miss_par = int(np.sum(par > d))
        out.append({
            'deadline_ms': d,
            'total_count': total,
            'miss_count_seq': miss_seq,
            'miss_rate_seq': (miss_seq / total) if total else float('nan'),
            'miss_count_parallel_abstract': miss_par,
            'miss_rate_parallel_abstract': (miss_par / total) if total else float('nan'),
            'p99_margin_seq': d - p99_seq,
            'p99_margin_parallel': d - p99_par,
        })
    return out


def plot_curve(rows: List[Dict[str, Any]], out_png: Path) -> None:
    ds = [float(r['deadline_ms']) for r in rows]
    ms = [float(r['miss_rate_seq']) for r in rows]
    mp = [float(r['miss_rate_parallel_abstract']) for r in rows]
    plt.figure(figsize=(7.2, 4.5), dpi=220)
    plt.plot(ds, ms, marker='o', linewidth=1.8, label='miss_rate_seq')
    plt.plot(ds, mp, marker='s', linewidth=1.8, label='miss_rate_parallel_abstract')
    plt.xscale('log')
    plt.xlabel('Deadline (ms, log scale)')
    plt.ylabel('Miss Rate')
    plt.title('Deadline Miss Rate vs D_auto')
    plt.grid(True, alpha=0.25)
    plt.legend()
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=220)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp2: Deadline feasibility and tail latency.')
    parser.add_argument('--input', required=True, help='exp1_timing_raw.csv path')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--policy', default='S16I_LOCKED_V1')
    parser.add_argument('--repeat', type=int, default=0)
    parser.add_argument('--duration_sec', type=int, default=0)
    args = parser.parse_args()

    in_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows = read_raw(in_path)
    if not raw_rows:
        raise RuntimeError(f'No rows in {in_path}')

    deadlines = [0.005, 0.01, 0.02, 0.05, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
    table = compute_table(raw_rows, deadlines)

    csv_path = out_dir / 'exp2_deadline_feasibility.csv'
    write_csv(
        csv_path,
        table,
        [
            'deadline_ms','total_count','miss_count_seq','miss_rate_seq',
            'miss_count_parallel_abstract','miss_rate_parallel_abstract',
            'p99_margin_seq','p99_margin_parallel'
        ]
    )

    plot_curve(table, out_dir / 'exp2_deadline_miss_curve.png')

    # concise md
    near_zero = [r for r in table if float(r['miss_rate_seq']) <= 1e-4]
    infeasible = [r for r in table if float(r['miss_rate_seq']) > 1e-3]

    md = []
    md.append('# Exp2 Deadline Feasibility and Tail Latency')
    md.append('')
    md.append('## Purpose')
    md.append('Assess deadline miss rates under candidate `D_auto` values using measurement-based timing from Exp1.')
    md.append('')
    md.append('## Input')
    md.append(f'- raw_timing_csv: `{in_path}`')
    md.append(f'- total_records: {len(raw_rows)}')
    md.append('')
    md.append('## Key Observations')
    if near_zero:
        md.append('- Deadlines with near-zero sequential miss rate (`<=1e-4`): ' + ', '.join([f"{r['deadline_ms']}ms" for r in near_zero]))
    else:
        md.append('- No tested deadlines reached near-zero sequential miss rate threshold (`<=1e-4`).')
    if infeasible:
        md.append('- Deadlines with comparatively high sequential miss rate (`>1e-3`): ' + ', '.join([f"{r['deadline_ms']}ms" for r in infeasible]))
    else:
        md.append('- No tested deadlines exceeded the `1e-3` sequential miss-rate threshold.')
    md.append('')
    md.append('## Boundary')
    md.append('- This is measurement-based feasibility analysis, not certified WCET.')

    (out_dir / 'exp2_deadline_feasibility.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({'status':'ok','rows':len(table),'output':str(csv_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
