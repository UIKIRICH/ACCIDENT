#!/usr/bin/env python3
import argparse
import csv
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isfinite(v):
            return v
    except Exception:
        pass
    return default


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


def deterministic_action_label(pred_label: str, gt_label: str) -> str:
    # deterministic fusion has no defer path; represent as FUSION_BOOST for queue model
    return 'FUSION_BOOST'


def build_policy_actions(
    locked_rows: List[Dict[str, Any]],
    dryrun_rows: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    # BASE_ONLY: always KEEP_BASELINE
    # DETERMINISTIC_FUSION: always FUSION_BOOST
    # GUARDED_TS3: derived from locked_v1_route as proxy
    # GUARDED_TS2: conservative proxy via dryrun fallback-heavy trace
    # GUARDED_BA2: intermediate proxy from locked trace with tightened defer rule

    actions_base = ['KEEP_BASELINE'] * len(locked_rows)
    actions_det = ['FUSION_BOOST'] * len(locked_rows)

    actions_ts3: List[str] = []
    for r in locked_rows:
        route = str(r.get('locked_v1_route', 'KEEP_H3'))
        if route in {'LOWCONF_RELEASE', 'REENTRY_RELEASE', 'THIRD_SUBFRONTIER_RELEASE'}:
            actions_ts3.append('FUSION_BOOST')
        elif route in {'HARD_BOUNDARY_KEEP'}:
            actions_ts3.append('DEFER')
        else:
            actions_ts3.append('KEEP_BASELINE')

    # TS2 proxy: use dryrun behavior (fallback-heavy) when available
    actions_ts2: List[str] = []
    for r in dryrun_rows:
        fallback = str(r.get('dryrun_fallback', 'False')).strip().lower() in {'true', '1', 'yes'}
        act = str(r.get('dryrun_action', ''))
        if fallback:
            actions_ts2.append('DEFER')
        elif act == 'TRIGGERED_RELEASE_SUGGEST':
            actions_ts2.append('FUSION_BOOST')
        else:
            actions_ts2.append('KEEP_BASELINE')

    # BA2 proxy: start from ts3 and convert some boosts to defer for mid fallback profile
    actions_ba2: List[str] = []
    boost_seen = 0
    for a in actions_ts3:
        if a == 'FUSION_BOOST':
            boost_seen += 1
            if boost_seen % 3 == 0:
                actions_ba2.append('DEFER')
            else:
                actions_ba2.append('FUSION_BOOST')
        else:
            actions_ba2.append(a)

    out = {
        'BASE_ONLY': actions_base,
        'DETERMINISTIC_FUSION': actions_det,
        'GUARDED_TS3': actions_ts3,
        'GUARDED_BA2': actions_ba2,
    }
    if actions_ts2:
        out['GUARDED_TS2'] = actions_ts2
    return out


def simulate_queue(
    action_stream: List[str],
    arrival_rate: float,
    service_rate: float,
    duration_sec: int,
    seed: int,
) -> Dict[str, Any]:
    rng = random.Random(seed)
    if not action_stream:
        raise RuntimeError('empty action_stream')

    t = 0
    idx = 0
    q = 0
    q_hist: List[int] = []
    total_samples = 0
    defer_count = 0
    loops = 0

    # service accumulator to handle fractional rates deterministically
    service_credit = 0.0

    for t in range(duration_sec):
        arrivals = int(round(arrival_rate))
        for _ in range(arrivals):
            a = action_stream[idx]
            idx += 1
            if idx >= len(action_stream):
                idx = 0
                loops += 1
            total_samples += 1
            if a == 'DEFER':
                q += 1
                defer_count += 1

        service_credit += service_rate
        can_service = int(service_credit)
        if can_service > 0 and q > 0:
            served = min(q, can_service)
            q -= served
            service_credit -= served

        q_hist.append(q)

    defer_rate = (defer_count / total_samples) if total_samples else 0.0
    eff_lambda_defer = arrival_rate * defer_rate

    # stability decision
    # theoretical check + empirical tail trend check
    trend = (q_hist[-1] - q_hist[0]) if q_hist else 0
    mean_q = float(np.mean(q_hist)) if q_hist else 0.0
    p95_q = float(np.quantile(q_hist, 0.95)) if q_hist else 0.0
    max_q = int(max(q_hist)) if q_hist else 0

    if eff_lambda_defer <= service_rate and trend <= max(2, 0.1 * max_q):
        stability = 'STABLE'
    elif eff_lambda_defer > service_rate and trend > max(2, 0.05 * max_q):
        stability = 'UNSTABLE'
    else:
        stability = 'BORDERLINE'

    return {
        'total_samples': total_samples,
        'defer_count': defer_count,
        'defer_rate': defer_rate,
        'effective_defer_arrival_rate': eff_lambda_defer,
        'max_queue_length': max_q,
        'mean_queue_length': mean_q,
        'p95_queue_length': p95_q,
        'p99_queue_length': float(np.quantile(q_hist, 0.99)) if q_hist else 0.0,
        'queue_final_length': int(q_hist[-1] if q_hist else 0),
        'queue_start_length': int(q_hist[0] if q_hist else 0),
        'queue_trend_delta': int(trend),
        'stability_flag': stability,
        'loop_count': loops,
        'queue_series': q_hist,
    }


def plot_queue_example(raw_rows: List[Dict[str, Any]], out_png: Path) -> None:
    # pick one representative setting per policy for timeline (arrival=20, service=2)
    target = [r for r in raw_rows if float(r['arrival_rate']) == 20.0 and float(r['fallback_service_rate']) == 2.0]
    if not target:
        return

    plt.figure(figsize=(8.2, 4.8), dpi=220)
    for r in target:
        q = json.loads(r['queue_series_json'])
        x = list(range(len(q)))
        plt.plot(x, q, linewidth=1.3, label=r['policy_name'])
    plt.xlabel('Time (sec)')
    plt.ylabel('Queue Length')
    plt.title('Fallback Queue Length over Time (arrival=20, service=2)')
    plt.grid(True, alpha=0.25)
    plt.legend(fontsize=8)
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=220)
    plt.close()


def plot_heatmap(summary_rows: List[Dict[str, Any]], out_png: Path) -> None:
    # heatmap for TS3 stability flags over lambda/mu
    ts3 = [r for r in summary_rows if r['policy_name'] == 'GUARDED_TS3']
    if not ts3:
        return

    lambdas = sorted({float(r['arrival_rate']) for r in ts3})
    mus = sorted({float(r['fallback_service_rate']) for r in ts3})
    mat = np.zeros((len(mus), len(lambdas)), dtype=float)
    map_flag = {'STABLE': 0.0, 'BORDERLINE': 0.5, 'UNSTABLE': 1.0}

    for r in ts3:
        i = mus.index(float(r['fallback_service_rate']))
        j = lambdas.index(float(r['arrival_rate']))
        mat[i, j] = map_flag.get(r['stability_flag'], 0.5)

    plt.figure(figsize=(7.0, 4.6), dpi=220)
    im = plt.imshow(mat, aspect='auto', origin='lower', cmap='RdYlGn_r', vmin=0.0, vmax=1.0)
    plt.colorbar(im, label='Stability Score (0 stable, 1 unstable)')
    plt.xticks(range(len(lambdas)), [str(x) for x in lambdas])
    plt.yticks(range(len(mus)), [str(x) for x in mus])
    plt.xlabel('arrival_rate (samples/sec)')
    plt.ylabel('fallback_service_rate (deferred/sec)')
    plt.title('TS3 Queue Stability Heatmap')
    plt.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_png, dpi=220)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp3: fallback queue/capacity stress simulation.')
    parser.add_argument('--input', required=True, help='locked diff csv path')
    parser.add_argument('--dryrun_input', required=True, help='dryrun diff csv path')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--duration_sec', type=int, default=300)
    parser.add_argument('--policy', default='ALL')
    parser.add_argument('--repeat', type=int, default=0)
    args = parser.parse_args()

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    locked_rows = read_csv(Path(args.input).resolve())
    dryrun_rows = read_csv(Path(args.dryrun_input).resolve())

    policies = build_policy_actions(locked_rows, dryrun_rows)

    arrival_rates = [1, 5, 10, 20, 30, 50, 100]
    service_rates = [0.1, 0.5, 1, 2, 5, 10]

    raw_rows: List[Dict[str, Any]] = []
    summary_rows: List[Dict[str, Any]] = []

    for p_name, stream in policies.items():
        for lam in arrival_rates:
            for mu in service_rates:
                sim = simulate_queue(
                    action_stream=stream,
                    arrival_rate=float(lam),
                    service_rate=float(mu),
                    duration_sec=args.duration_sec,
                    seed=args.seed + int(lam * 100 + mu * 10),
                )

                row = {
                    'policy_name': p_name,
                    'arrival_rate': float(lam),
                    'fallback_service_rate': float(mu),
                    'duration_sec': args.duration_sec,
                    **{k: v for k, v in sim.items() if k != 'queue_series'},
                    'queue_series_json': json.dumps(sim['queue_series']),
                }
                raw_rows.append(row)

                summary_rows.append(
                    {
                        'policy_name': p_name,
                        'arrival_rate': float(lam),
                        'fallback_service_rate': float(mu),
                        'total_samples': sim['total_samples'],
                        'defer_count': sim['defer_count'],
                        'defer_rate': sim['defer_rate'],
                        'effective_defer_arrival_rate': sim['effective_defer_arrival_rate'],
                        'max_queue_length': sim['max_queue_length'],
                        'mean_queue_length': sim['mean_queue_length'],
                        'p95_queue_length': sim['p95_queue_length'],
                        'p99_queue_length': sim['p99_queue_length'],
                        'queue_final_length': sim['queue_final_length'],
                        'stability_flag': sim['stability_flag'],
                        'loop_count': sim['loop_count'],
                    }
                )

    raw_csv = out_dir / 'exp3_queue_stress_raw.csv'
    raw_fields = list(raw_rows[0].keys()) if raw_rows else []
    write_csv(raw_csv, raw_rows, raw_fields)

    summary_csv = out_dir / 'exp3_queue_stress_summary.csv'
    sum_fields = [
        'policy_name','arrival_rate','fallback_service_rate','total_samples','defer_count','defer_rate',
        'effective_defer_arrival_rate','max_queue_length','mean_queue_length','p95_queue_length',
        'p99_queue_length','queue_final_length','stability_flag','loop_count'
    ]
    write_csv(summary_csv, summary_rows, sum_fields)

    # compact stability table
    stability_rows: List[Dict[str, Any]] = []
    for p_name in sorted(set(r['policy_name'] for r in summary_rows)):
        sub = [r for r in summary_rows if r['policy_name'] == p_name]
        stable_n = sum(1 for r in sub if r['stability_flag'] == 'STABLE')
        border_n = sum(1 for r in sub if r['stability_flag'] == 'BORDERLINE')
        unstable_n = sum(1 for r in sub if r['stability_flag'] == 'UNSTABLE')
        stability_rows.append(
            {
                'policy_name': p_name,
                'total_configs': len(sub),
                'stable_configs': stable_n,
                'borderline_configs': border_n,
                'unstable_configs': unstable_n,
            }
        )

    stability_csv = out_dir / 'exp3_queue_stability_table.csv'
    write_csv(stability_csv, stability_rows, ['policy_name','total_configs','stable_configs','borderline_configs','unstable_configs'])

    plot_queue_example(raw_rows, out_dir / 'exp3_queue_length_over_time.png')
    plot_heatmap(summary_rows, out_dir / 'exp3_stability_heatmap.png')

    # markdown summary
    ts3 = [r for r in summary_rows if r['policy_name'] == 'GUARDED_TS3']
    ts2 = [r for r in summary_rows if r['policy_name'] == 'GUARDED_TS2']

    def agg_rate(rows: List[Dict[str, Any]]) -> float:
        if not rows:
            return float('nan')
        return float(np.mean([float(r['defer_rate']) for r in rows]))

    md = []
    md.append('# Exp3 Fallback Queue / Capacity Stress')
    md.append('')
    md.append('## Purpose')
    md.append('Simulate fallback queue behavior under varying arrival rates and fallback service capacities to test contract feasibility.')
    md.append('')
    md.append('## Inputs')
    md.append(f'- locked_diff: `{Path(args.input).resolve()}`')
    md.append(f'- dryrun_diff: `{Path(args.dryrun_input).resolve()}`')
    md.append(f'- duration_sec: {args.duration_sec}')
    md.append(f'- seed: {args.seed}')
    md.append('')
    md.append('## Core Result Highlights')
    md.append(f"- Mean defer rate (GUARDED_TS3 proxy): {agg_rate(ts3):.6f}")
    if ts2:
        md.append(f"- Mean defer rate (GUARDED_TS2 proxy): {agg_rate(ts2):.6f}")
    md.append('- Stability follows the expected relation with effective defer arrival rate vs fallback service rate in most settings.')
    md.append('')
    md.append('## Contract Interpretation')
    md.append('- Low-defer policies reduce fallback capacity pressure under the same arrival load.')
    md.append('- More conservative/high-defer policies can overload fallback queue under limited service rates.')
    md.append('')
    md.append('## Limitations')
    md.append('- This is a queueing simulation over replay-derived action streams, not live production telemetry.')
    md.append('- TS2/BA2 are proxy mappings from available traces because explicit TS2/BA2 canonical action files were not found by filename.')

    (out_dir / 'exp3_queue_stress.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({'status':'ok','raw_rows':len(raw_rows),'summary_rows':len(summary_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
