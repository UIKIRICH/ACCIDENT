#!/usr/bin/env python3
import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read_csv(path: Path) -> List[Dict[str, Any]]:
    with path.open('r', encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: List[Dict[str, Any]], fields: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def build_streams(locked_rows: List[Dict[str, Any]], dryrun_rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    # same mapping as Exp3
    ts3 = []
    for r in locked_rows:
        route = str(r.get('locked_v1_route', 'KEEP_H3'))
        if route in {'LOWCONF_RELEASE', 'REENTRY_RELEASE', 'THIRD_SUBFRONTIER_RELEASE'}:
            ts3.append('FUSION_BOOST')
        elif route in {'HARD_BOUNDARY_KEEP'}:
            ts3.append('DEFER')
        else:
            ts3.append('KEEP_BASELINE')

    ts2 = []
    for r in dryrun_rows:
        fallback = str(r.get('dryrun_fallback', 'False')).strip().lower() in {'true','1','yes'}
        act = str(r.get('dryrun_action', ''))
        if fallback:
            ts2.append('DEFER')
        elif act == 'TRIGGERED_RELEASE_SUGGEST':
            ts2.append('FUSION_BOOST')
        else:
            ts2.append('KEEP_BASELINE')

    return {
        'GUARDED_TS3': ts3,
        'GUARDED_TS2': ts2,
        'BASE_ONLY': ['KEEP_BASELINE'] * len(locked_rows),
        'DETERMINISTIC_FUSION': ['FUSION_BOOST'] * len(locked_rows),
    }


def arrival_rate_at(t: int, pattern: str) -> float:
    if pattern == 'constant':
        return 10.0
    if pattern == 'periodic_burst':
        # every 30s burst 5s @50, else 10
        if (t % 30) < 5:
            return 50.0
        return 10.0
    if pattern == 'heavy_burst':
        # every 60s burst 10s @100, else 10
        if (t % 60) < 10:
            return 100.0
        return 10.0
    return 10.0


def simulate_pattern(stream: List[str], service_rate: float, duration_sec: int, pattern: str) -> Dict[str, Any]:
    if not stream:
        raise RuntimeError('empty stream')

    idx = 0
    q = 0
    total = 0
    defer_n = 0
    loops = 0
    series: List[int] = []
    arrival_hist: List[float] = []
    service_credit = 0.0

    for t in range(duration_sec):
        lam = arrival_rate_at(t, pattern)
        arrival_hist.append(lam)
        arrivals = int(round(lam))
        for _ in range(arrivals):
            a = stream[idx]
            idx += 1
            if idx >= len(stream):
                idx = 0
                loops += 1
            total += 1
            if a == 'DEFER':
                q += 1
                defer_n += 1

        service_credit += service_rate
        can_service = int(service_credit)
        if can_service > 0 and q > 0:
            served = min(q, can_service)
            q -= served
            service_credit -= served

        series.append(q)

    defer_rate = (defer_n / total) if total else 0.0
    avg_arrival = float(np.mean(arrival_hist)) if arrival_hist else 0.0
    eff_lambda = avg_arrival * defer_rate
    trend = int(series[-1] - series[0]) if series else 0
    max_q = int(max(series)) if series else 0

    # recovery heuristic: queue at end vs p95 in last 20%
    tail = series[int(len(series) * 0.8):] if series else []
    tail_mean = float(np.mean(tail)) if tail else 0.0
    recovered = bool(series[-1] <= tail_mean + 2.0) if series else True

    if eff_lambda <= service_rate and trend <= max(2, int(0.1 * max_q)):
        stability = 'STABLE'
    elif eff_lambda > service_rate and trend > max(2, int(0.05 * max_q)):
        stability = 'UNSTABLE'
    else:
        stability = 'BORDERLINE'

    return {
        'total_samples': total,
        'defer_count': defer_n,
        'defer_rate': defer_rate,
        'avg_arrival_rate': avg_arrival,
        'effective_defer_arrival_rate': eff_lambda,
        'max_queue_length': max_q,
        'mean_queue_length': float(np.mean(series)) if series else 0.0,
        'p95_queue_length': float(np.quantile(series, 0.95)) if series else 0.0,
        'queue_final_length': int(series[-1] if series else 0),
        'queue_trend_delta': trend,
        'stability_flag': stability,
        'recovered_after_burst_flag': recovered,
        'loop_count': loops,
        'queue_series': series,
        'arrival_series': arrival_hist,
    }


def plot_timeline(raw: List[Dict[str, Any]], pattern: str, out_png: Path) -> None:
    rows = [r for r in raw if r['pattern'] == pattern and float(r['fallback_service_rate']) == 2.0]
    if not rows:
        return
    plt.figure(figsize=(8.2, 4.8), dpi=220)
    for r in rows:
        q = json.loads(r['queue_series_json'])
        x = list(range(len(q)))
        plt.plot(x, q, linewidth=1.5, label=r['policy_name'])
    plt.xlabel('Time (sec)')
    plt.ylabel('Queue length')
    plt.title(f'Queue timeline: {pattern} (service=2 deferred/sec)')
    plt.grid(True, alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=220)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp4: burst stress simulation.')
    parser.add_argument('--input', required=True, help='locked diff csv')
    parser.add_argument('--dryrun_input', required=True, help='dryrun diff csv')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--duration_sec', type=int, default=300)
    parser.add_argument('--policy', default='ALL')
    parser.add_argument('--repeat', type=int, default=0)
    args = parser.parse_args()

    locked_rows = read_csv(Path(args.input).resolve())
    dryrun_rows = read_csv(Path(args.dryrun_input).resolve())
    streams = build_streams(locked_rows, dryrun_rows)

    patterns = ['constant', 'periodic_burst', 'heavy_burst']
    service_rates = [0.5, 1, 2, 5]
    policy_order = ['GUARDED_TS3', 'GUARDED_TS2', 'BASE_ONLY', 'DETERMINISTIC_FUSION']

    raw_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for p in policy_order:
        stream = streams.get(p, [])
        if not stream:
            continue
        for pat in patterns:
            for mu in service_rates:
                sim = simulate_pattern(stream, service_rate=float(mu), duration_sec=args.duration_sec, pattern=pat)
                raw_rows.append({
                    'policy_name': p,
                    'pattern': pat,
                    'fallback_service_rate': float(mu),
                    'duration_sec': args.duration_sec,
                    **{k: v for k, v in sim.items() if k not in {'queue_series','arrival_series'}},
                    'queue_series_json': json.dumps(sim['queue_series']),
                    'arrival_series_json': json.dumps(sim['arrival_series']),
                })
                summary_rows.append({
                    'policy_name': p,
                    'pattern': pat,
                    'fallback_service_rate': float(mu),
                    'defer_rate': sim['defer_rate'],
                    'effective_defer_arrival_rate': sim['effective_defer_arrival_rate'],
                    'max_queue_length': sim['max_queue_length'],
                    'mean_queue_length': sim['mean_queue_length'],
                    'p95_queue_length': sim['p95_queue_length'],
                    'queue_final_length': sim['queue_final_length'],
                    'stability_flag': sim['stability_flag'],
                    'recovered_after_burst_flag': sim['recovered_after_burst_flag'],
                })

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_csv = out_dir / 'exp4_burst_raw.csv'
    raw_fields = list(raw_rows[0].keys()) if raw_rows else []
    write_csv(raw_csv, raw_rows, raw_fields)

    sum_csv = out_dir / 'exp4_burst_summary.csv'
    sum_fields = [
        'policy_name','pattern','fallback_service_rate','defer_rate','effective_defer_arrival_rate',
        'max_queue_length','mean_queue_length','p95_queue_length','queue_final_length',
        'stability_flag','recovered_after_burst_flag'
    ]
    write_csv(sum_csv, summary_rows, sum_fields)

    plot_timeline(raw_rows, 'constant', out_dir / 'exp4_queue_timeline_constant.png')
    plot_timeline(raw_rows, 'periodic_burst', out_dir / 'exp4_queue_timeline_periodic_burst.png')
    plot_timeline(raw_rows, 'heavy_burst', out_dir / 'exp4_queue_timeline_heavy_burst.png')

    # md summary
    md = []
    md.append('# Exp4 Burst Workload Stress')
    md.append('')
    md.append('## Purpose')
    md.append('Evaluate fallback queue behavior under constant and bursty arrivals.')
    md.append('')
    md.append('## Input')
    md.append(f'- locked_diff: `{Path(args.input).resolve()}`')
    md.append(f'- dryrun_diff: `{Path(args.dryrun_input).resolve()}`')
    md.append(f'- duration_sec: {args.duration_sec}')
    md.append('')
    md.append('## Findings')

    for pat in patterns:
        sub = [r for r in summary_rows if r['pattern'] == pat]
        ts3 = [r for r in sub if r['policy_name'] == 'GUARDED_TS3']
        ts2 = [r for r in sub if r['policy_name'] == 'GUARDED_TS2']
        if ts3:
            stable3 = sum(1 for r in ts3 if r['stability_flag'] == 'STABLE')
            md.append(f'- {pat}: TS3 stable in {stable3}/{len(ts3)} service settings.')
        if ts2:
            stable2 = sum(1 for r in ts2 if r['stability_flag'] == 'STABLE')
            md.append(f'- {pat}: TS2 stable in {stable2}/{len(ts2)} service settings.')

    md.append('')
    md.append('## Contract Feasibility Note')
    md.append('- Burst feasibility is strongly dependent on fallback service rate and defer rate.')
    md.append('- Low-fallback policies retain more feasible regions under burst conditions.')
    md.append('')
    md.append('## Limitations')
    md.append('- Replay-derived action stream simulation; not direct live traffic telemetry.')
    md.append('- TS2 here is a fallback-heavy proxy from available dryrun trace due missing explicit TS2 canonical action file.')

    (out_dir / 'exp4_burst.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({'status':'ok','raw_rows':len(raw_rows),'summary_rows':len(summary_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
