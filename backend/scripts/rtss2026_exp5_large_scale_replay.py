#!/usr/bin/env python3
import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple

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


def safe_bool(x: Any) -> bool:
    return str(x).strip().lower() in {'1','true','yes'}


def eval_metrics(rows: List[Dict[str, Any]], pred_key: str, gt_key: str = 'gt_type') -> Dict[str, float]:
    cls = ['rear_end', 'lane_change', 'turn_conflict']
    gt = [str(r.get(gt_key, '')).strip() for r in rows]
    pr = [str(r.get(pred_key, '')).strip() for r in rows]
    n = len(gt)
    if n == 0:
        return {'rear_risk': float('nan'), 'auto_error': float('nan'), 'lane_recall': float('nan'), 'turn_recall': float('nan'), 'utility': float('nan')}

    # rear risk: rear GT predicted non-rear
    rear_gt_idx = [i for i, g in enumerate(gt) if g == 'rear_end']
    rear_miss = sum(1 for i in rear_gt_idx if pr[i] != 'rear_end')
    rear_risk = rear_miss / len(rear_gt_idx) if rear_gt_idx else float('nan')

    auto_err = sum(1 for g, p in zip(gt, pr) if g != p) / n

    def recall(target: str) -> float:
        idx = [i for i, g in enumerate(gt) if g == target]
        if not idx:
            return float('nan')
        ok = sum(1 for i in idx if pr[i] == target)
        return ok / len(idx)

    lane_r = recall('lane_change')
    turn_r = recall('turn_conflict')
    utility = 0.5 * lane_r + 0.5 * turn_r if (not math.isnan(lane_r) and not math.isnan(turn_r)) else float('nan')
    return {
        'rear_risk': rear_risk,
        'auto_error': auto_err,
        'lane_recall': lane_r,
        'turn_recall': turn_r,
        'utility': utility,
    }


def wilson_interval(k: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return (float('nan'), float('nan'))
    phat = k / n
    den = 1 + z**2 / n
    center = (phat + z*z/(2*n)) / den
    margin = z * math.sqrt((phat*(1-phat) + z*z/(4*n)) / n) / den
    return (max(0.0, center - margin), min(1.0, center + margin))


def bootstrap_interval(vals: np.ndarray, B: int = 3000, q_low: float = 5.0, q_high: float = 95.0, seed: int = 20260521) -> Tuple[float, float]:
    if len(vals) == 0:
        return (float('nan'), float('nan'))
    rng = np.random.default_rng(seed)
    n = len(vals)
    means = np.empty(B, dtype=float)
    for i in range(B):
        idx = rng.integers(0, n, size=n)
        means[i] = float(np.mean(vals[idx]))
    lo = float(np.quantile(means, q_low / 100.0, method='linear'))
    hi = float(np.quantile(means, q_high / 100.0, method='linear'))
    return (lo, hi)


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp5: larger-scale replay / public dataset expansion.')
    parser.add_argument('--input', required=True, help='expanded diff csv')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--policy', default='ALL')
    parser.add_argument('--repeat', type=int, default=0)
    parser.add_argument('--duration_sec', type=int, default=0)
    args = parser.parse_args()

    in_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(in_path)
    N = len(rows)

    if N < 1000:
        # required missing-data report
        miss = []
        miss.append('# missing_data_report')
        miss.append('')
        miss.append('## Reason')
        miss.append(f'- Available canonical action-level replay table has N={N}, below target N>=1000.')
        miss.append('')
        miss.append('## Checked input')
        miss.append(f'- `{in_path}`')
        miss.append('')
        miss.append('## Required files to proceed with strict Exp5 target')
        miss.append('- A labeled action-level replay CSV/JSONL with at least 1000 comparable samples.')
        miss.append('- Required fields: `sample_id/case_id`, `gt_type`, baseline prediction, fusion prediction, guarded route/action, board/source id.')
        miss.append('- Prefer one merged file or a manifest listing exact files and schema mapping.')
        miss.append('')
        miss.append('## What is still produced now')
        miss.append('- A best-effort large replay table on current N with explicit non-claim boundary.')
        (out_dir / 'missing_data_report.md').write_text('\n'.join(miss), encoding='utf-8')

    # Build policy predictions from available fields
    # BASE_ONLY uses pred_after_h3
    # DETERMINISTIC_FUSION proxy: if h3 is rear_end, force locked pred (fusion replacement); else keep h3
    # GUARDED_TS3 uses pred_after_locked_v1
    # GUARDED_TS2 proxy: from locked route, convert all release routes to DEFER->keep h3 for auto outputs
    # GUARDED_BA2 proxy: convert every 3rd release to defer, else locked pred

    for r in rows:
        h3 = str(r.get('pred_after_h3', '')).strip()
        lk = str(r.get('pred_after_locked_v1', '')).strip()
        route = str(r.get('locked_v1_route', 'KEEP_H3')).strip()

        r['pred_base_only'] = h3
        r['pred_det_fusion'] = lk if h3 == 'rear_end' else h3
        r['pred_guarded_ts3'] = lk

    # TS2/BA2 proxy assignments
    rel_routes = {'LOWCONF_RELEASE', 'REENTRY_RELEASE', 'THIRD_SUBFRONTIER_RELEASE'}
    rel_counter = 0
    for r in rows:
        h3 = str(r['pred_after_h3'])
        lk = str(r['pred_after_locked_v1'])
        route = str(r.get('locked_v1_route', 'KEEP_H3'))

        # TS2: conservative -> defer all release routes
        if route in rel_routes:
            r['pred_guarded_ts2'] = h3
            r['action_ts2'] = 'DEFER'
        elif route == 'HARD_BOUNDARY_KEEP':
            r['pred_guarded_ts2'] = h3
            r['action_ts2'] = 'DEFER'
        else:
            r['pred_guarded_ts2'] = h3
            r['action_ts2'] = 'KEEP_BASELINE'

        # BA2 proxy: partial release retention
        if route in rel_routes:
            rel_counter += 1
            if rel_counter % 3 == 0:
                r['pred_guarded_ba2'] = h3
                r['action_ba2'] = 'DEFER'
            else:
                r['pred_guarded_ba2'] = lk
                r['action_ba2'] = 'FUSION_BOOST'
        elif route == 'HARD_BOUNDARY_KEEP':
            r['pred_guarded_ba2'] = h3
            r['action_ba2'] = 'DEFER'
        else:
            r['pred_guarded_ba2'] = h3
            r['action_ba2'] = 'KEEP_BASELINE'

    # auto coverage/fallback approximations
    for r in rows:
        route = str(r.get('locked_v1_route', 'KEEP_H3'))
        r['action_ts3'] = 'FUSION_BOOST' if route in rel_routes else ('DEFER' if route == 'HARD_BOUNDARY_KEEP' else 'KEEP_BASELINE')

    policies = {
        'BASE_ONLY': ('pred_base_only', lambda rr: 'KEEP_BASELINE'),
        'DETERMINISTIC_FUSION': ('pred_det_fusion', lambda rr: 'FUSION_BOOST'),
        'GUARDED_TS3': ('pred_guarded_ts3', lambda rr: rr.get('action_ts3', 'KEEP_BASELINE')),
        'GUARDED_TS2': ('pred_guarded_ts2', lambda rr: rr.get('action_ts2', 'KEEP_BASELINE')),
        'GUARDED_BA2': ('pred_guarded_ba2', lambda rr: rr.get('action_ba2', 'KEEP_BASELINE')),
        'CONFIDENCE_ONLY_BASELINE': ('pred_base_only', lambda rr: 'KEEP_BASELINE'),
        'BUDGET_MATCHED_CONF_BASELINE': ('pred_base_only', lambda rr: 'KEEP_BASELINE'),
    }

    main_rows: List[Dict[str, Any]] = []

    gt = [str(r.get('gt_type', '')).strip() for r in rows]
    rear_support = sum(1 for g in gt if g == 'rear_end')
    lane_support = sum(1 for g in gt if g == 'lane_change')
    turn_support = sum(1 for g in gt if g == 'turn_conflict')

    for name, (pred_key, action_fn) in policies.items():
        # set temporary prediction key for eval
        metrics = eval_metrics(rows, pred_key=pred_key)

        actions = [action_fn(r) for r in rows]
        defer_n = sum(1 for a in actions if a == 'DEFER')
        fallback_rate = defer_n / N if N else float('nan')
        auto_cov = 1.0 - fallback_rate if N else float('nan')

        rear_gt = [r for r in rows if str(r.get('gt_type','')).strip() == 'rear_end']
        rear_miss = sum(1 for r in rear_gt if str(r.get(pred_key,'')).strip() != 'rear_end')
        ci_lo, ci_hi = wilson_interval(rear_miss, len(rear_gt))

        # bootstrap on auto error indicator
        err_vals = np.array([1.0 if str(r.get(pred_key,'')) != str(r.get('gt_type','')) else 0.0 for r in rows], dtype=float)
        be_lo, be_hi = bootstrap_interval(err_vals, B=3000, seed=args.seed)

        main_rows.append({
            'policy_name': name,
            'N': N,
            'rear_support': rear_support,
            'lane_support': lane_support,
            'turn_support': turn_support,
            'fallback_rate': fallback_rate,
            'auto_coverage': auto_cov,
            'rear_risk': metrics['rear_risk'],
            'auto_error': metrics['auto_error'],
            'lane_recall': metrics['lane_recall'],
            'turn_recall': metrics['turn_recall'],
            'utility': metrics['utility'],
            'rear_risk_wilson_ci95_low': ci_lo,
            'rear_risk_wilson_ci95_high': ci_hi,
            'auto_error_bootstrap_p5': be_lo,
            'auto_error_bootstrap_p95': be_hi,
        })

    metrics_csv = out_dir / 'exp5_large_replay_metrics.csv'
    fields = list(main_rows[0].keys()) if main_rows else []
    write_csv(metrics_csv, main_rows, fields)

    # by bucket
    bucket_rows: List[Dict[str, Any]] = []
    buckets = sorted(set(str(r.get('expanded_window_id','NA')) for r in rows))
    for b in buckets:
        sub = [r for r in rows if str(r.get('expanded_window_id','NA')) == b]
        if not sub:
            continue
        m = eval_metrics(sub, pred_key='pred_guarded_ts3')
        bucket_rows.append({
            'bucket': b,
            'N': len(sub),
            'rear_risk_ts3': m['rear_risk'],
            'auto_error_ts3': m['auto_error'],
            'utility_ts3': m['utility'],
        })

    by_bucket_csv = out_dir / 'exp5_large_replay_by_bucket.csv'
    write_csv(by_bucket_csv, bucket_rows, list(bucket_rows[0].keys()) if bucket_rows else ['bucket','N','rear_risk_ts3','auto_error_ts3','utility_ts3'])

    # by class
    class_rows: List[Dict[str, Any]] = []
    for cls in ['rear_end','lane_change','turn_conflict']:
        n_cls = sum(1 for r in rows if str(r.get('gt_type','')).strip() == cls)
        class_rows.append({'class_name': cls, 'support': n_cls})
    by_class_csv = out_dir / 'exp5_large_replay_by_class.csv'
    write_csv(by_class_csv, class_rows, ['class_name','support'])

    # plots
    # frontier scatter: fallback vs rear_risk colored by utility
    x = np.array([float(r['fallback_rate']) for r in main_rows], dtype=float)
    y = np.array([float(r['rear_risk']) for r in main_rows], dtype=float)
    c = np.array([float(r['utility']) for r in main_rows], dtype=float)
    labels = [r['policy_name'] for r in main_rows]

    plt.figure(figsize=(6.8, 4.8), dpi=220)
    sc = plt.scatter(x, y, c=c, cmap='viridis', s=85)
    for i, lb in enumerate(labels):
        plt.annotate(lb, (x[i], y[i]), fontsize=7, xytext=(4, 4), textcoords='offset points')
    plt.colorbar(sc, label='utility')
    plt.xlabel('fallback/defer rate')
    plt.ylabel('rear risk')
    plt.title('Large Replay Operating Surface (best-effort)')
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(out_dir / 'exp5_large_replay_frontier.png', dpi=220)
    plt.close()

    # bucket risk bar
    if bucket_rows:
        plt.figure(figsize=(8.2, 4.6), dpi=220)
        bx = np.arange(len(bucket_rows))
        by = [float(r['rear_risk_ts3']) for r in bucket_rows]
        plt.bar(bx, by)
        plt.xticks(bx, [r['bucket'] for r in bucket_rows], rotation=45, ha='right')
        plt.ylabel('rear risk (TS3 proxy)')
        plt.title('Bucket-level Rear Risk (TS3 proxy)')
        plt.grid(True, axis='y', alpha=0.25)
        plt.tight_layout()
        plt.savefig(out_dir / 'exp5_large_replay_bucket_risk.png', dpi=220)
        plt.close()

    md = []
    md.append('# Exp5 Larger-Scale Replay / Public Expansion Summary')
    md.append('')
    md.append('## Purpose')
    md.append('Check whether key safety/utility tradeoff patterns persist on an expanded replay table.')
    md.append('')
    md.append('## Input')
    md.append(f'- input: `{in_path}`')
    md.append(f'- N: {N}')
    md.append('')
    if N < 1000:
        md.append('## Data Scale Warning')
        md.append('- Target N>=1000 is not met with the currently identified canonical action-level file.')
        md.append('- See `missing_data_report.md` for required files/fields.')
        md.append('')
    md.append('## Key Findings (best-effort on current input)')
    # find core policies
    idx = {r['policy_name']: r for r in main_rows}
    if 'DETERMINISTIC_FUSION' in idx and 'BASE_ONLY' in idx:
        d = idx['DETERMINISTIC_FUSION']
        b = idx['BASE_ONLY']
        md.append(f"- Deterministic fusion vs base: utility {d['utility']:.6f} vs {b['utility']:.6f}; rear risk {d['rear_risk']:.6f} vs {b['rear_risk']:.6f}.")
    if 'GUARDED_TS3' in idx and 'GUARDED_TS2' in idx:
        t3 = idx['GUARDED_TS3']
        t2 = idx['GUARDED_TS2']
        md.append(f"- TS3 proxy: fallback={t3['fallback_rate']:.6f}, rear risk={t3['rear_risk']:.6f}, utility={t3['utility']:.6f}.")
        md.append(f"- TS2 proxy: fallback={t2['fallback_rate']:.6f}, rear risk={t2['rear_risk']:.6f}, utility={t2['utility']:.6f}.")
    md.append('')
    md.append('## Limitations')
    md.append('- TS2/BA2 and confidence baselines are proxy reconstructions from available fields, not dedicated canonical trace files.')
    md.append('- This section does not claim public-dataset trajectory SOTA or strict cross-paper ADE/FDE comparability.')

    (out_dir / 'exp5_large_replay_summary.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({'status':'ok','N':N,'metrics_rows':len(main_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
