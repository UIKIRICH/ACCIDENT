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


def eval_metrics(gt: List[str], pred: List[str], actions: List[str]) -> Dict[str, float]:
    n = len(gt)
    rear_idx = [i for i, g in enumerate(gt) if g == 'rear_end']
    rear_risk = (sum(1 for i in rear_idx if pred[i] != 'rear_end') / len(rear_idx)) if rear_idx else float('nan')
    auto_error = sum(1 for g, p in zip(gt, pred) if g != p) / n if n else float('nan')

    def recall(c: str) -> float:
        idx = [i for i, g in enumerate(gt) if g == c]
        if not idx:
            return float('nan')
        return sum(1 for i in idx if pred[i] == c) / len(idx)

    lane_r = recall('lane_change')
    turn_r = recall('turn_conflict')
    utility = 0.5 * lane_r + 0.5 * turn_r if not (math.isnan(lane_r) or math.isnan(turn_r)) else float('nan')

    fallback = sum(1 for a in actions if a == 'DEFER') / n if n else float('nan')
    return {
        'fallback_rate': fallback,
        'rear_risk': rear_risk,
        'utility': utility,
        'auto_error': auto_error,
    }


def nan_summary(arr: np.ndarray) -> Dict[str, float]:
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return {
            'mean': float('nan'),
            'median': float('nan'),
            'p10': float('nan'),
            'p90': float('nan'),
            'p95': float('nan'),
            'valid_fraction': 0.0,
        }
    return {
        'mean': float(np.mean(valid)),
        'median': float(np.median(valid)),
        'p10': float(np.quantile(valid, 0.10, method='linear')),
        'p90': float(np.quantile(valid, 0.90, method='linear')),
        'p95': float(np.quantile(valid, 0.95, method='linear')),
        'valid_fraction': float(valid.size / arr.size),
    }


def bootstrap_metrics(rows: List[Dict[str, Any]], pred_key: str, action_key: str, B: int, seed: int) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    rng = np.random.default_rng(seed)
    n = len(rows)
    gt = np.array([str(r.get('gt_type','')).strip() for r in rows], dtype=object)
    pred = np.array([str(r.get(pred_key,'')).strip() for r in rows], dtype=object)
    act = np.array([str(r.get(action_key,'')).strip() for r in rows], dtype=object)

    out: List[Dict[str, float]] = []
    for _ in range(B):
        idx = rng.integers(0, n, size=n)
        g = gt[idx].tolist()
        p = pred[idx].tolist()
        a = act[idx].tolist()
        out.append(eval_metrics(g, p, a))

    arr_fb = np.array([x['fallback_rate'] for x in out], dtype=float)
    arr_rr = np.array([x['rear_risk'] for x in out], dtype=float)
    arr_ut = np.array([x['utility'] for x in out], dtype=float)

    fb_s = nan_summary(arr_fb)
    rr_s = nan_summary(arr_rr)
    ut_s = nan_summary(arr_ut)
    summary = {
        'fallback_mean': fb_s['mean'],
        'fallback_median': fb_s['median'],
        'fallback_p10': fb_s['p10'],
        'fallback_p90': fb_s['p90'],
        'fallback_p95': fb_s['p95'],
        'rear_mean': rr_s['mean'],
        'rear_median': rr_s['median'],
        'rear_p10': rr_s['p10'],
        'rear_p90': rr_s['p90'],
        'rear_p95': rr_s['p95'],
        'utility_mean': ut_s['mean'],
        'utility_median': ut_s['median'],
        'utility_p10': ut_s['p10'],
        'utility_p90': ut_s['p90'],
        'utility_p95': ut_s['p95'],
        'utility_valid_fraction': ut_s['valid_fraction'],
    }
    return out, summary


def lobo_metrics(rows: List[Dict[str, Any]], pred_key: str, action_key: str, group_field: str) -> List[Dict[str, Any]]:
    boards = sorted({str(r.get(group_field, 'NA')).strip() for r in rows if str(r.get(group_field, 'NA')).strip() not in {'', 'NA', 'None'}})
    out = []
    for b in boards:
        sub = [r for r in rows if str(r.get(group_field, 'NA')).strip() != b]
        if not sub:
            continue
        gt = [str(r.get('gt_type','')).strip() for r in sub]
        pr = [str(r.get(pred_key,'')).strip() for r in sub]
        ac = [str(r.get(action_key,'')).strip() for r in sub]
        m = eval_metrics(gt, pr, ac)
        out.append({'left_out_unit': b, 'lobo_group_field': group_field, **m, 'n_remaining': len(sub)})
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp8: selected-point stability (bootstrap + LOBO).')
    parser.add_argument('--input', required=True, help='expanded diff csv')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--bootstrap_B', type=int, default=5000)
    parser.add_argument('--policy', default='ALL')
    parser.add_argument('--repeat', type=int, default=0)
    parser.add_argument('--duration_sec', type=int, default=0)
    args = parser.parse_args()

    rows = read_csv(Path(args.input).resolve())

    # construct policy predictions/actions
    rel_routes = {'LOWCONF_RELEASE', 'REENTRY_RELEASE', 'THIRD_SUBFRONTIER_RELEASE'}
    rel_counter = 0
    for r in rows:
        h3 = str(r.get('pred_after_h3','')).strip()
        lk = str(r.get('pred_after_locked_v1','')).strip()
        route = str(r.get('locked_v1_route','KEEP_H3')).strip()

        # BASE
        r['pred_BASE_ONLY'] = h3
        r['action_BASE_ONLY'] = 'KEEP_BASELINE'

        # DET
        r['pred_DETERMINISTIC_FUSION'] = lk if h3 == 'rear_end' else h3
        r['action_DETERMINISTIC_FUSION'] = 'FUSION_BOOST'

        # TS3
        r['pred_TS3'] = lk
        if route in rel_routes:
            r['action_TS3'] = 'FUSION_BOOST'
        elif route == 'HARD_BOUNDARY_KEEP':
            r['action_TS3'] = 'DEFER'
        else:
            r['action_TS3'] = 'KEEP_BASELINE'

        # TS2 proxy
        if route in rel_routes or route == 'HARD_BOUNDARY_KEEP':
            r['pred_TS2'] = h3
            r['action_TS2'] = 'DEFER'
        else:
            r['pred_TS2'] = h3
            r['action_TS2'] = 'KEEP_BASELINE'

        # BA2 proxy
        if route in rel_routes:
            rel_counter += 1
            if rel_counter % 3 == 0:
                r['pred_BA2'] = h3
                r['action_BA2'] = 'DEFER'
            else:
                r['pred_BA2'] = lk
                r['action_BA2'] = 'FUSION_BOOST'
        elif route == 'HARD_BOUNDARY_KEEP':
            r['pred_BA2'] = h3
            r['action_BA2'] = 'DEFER'
        else:
            r['pred_BA2'] = h3
            r['action_BA2'] = 'KEEP_BASELINE'

    policies = {
        'TS3': ('pred_TS3', 'action_TS3'),
        'TS2': ('pred_TS2', 'action_TS2'),
        'BA2': ('pred_BA2', 'action_BA2'),
        'DETERMINISTIC_FUSION': ('pred_DETERMINISTIC_FUSION', 'action_DETERMINISTIC_FUSION'),
        'BASE_ONLY': ('pred_BASE_ONLY', 'action_BASE_ONLY'),
    }

    # anchors for probabilities
    gt = [str(r.get('gt_type','')).strip() for r in rows]
    pred_det = [str(r.get('pred_DETERMINISTIC_FUSION','')).strip() for r in rows]
    pred_base = [str(r.get('pred_BASE_ONLY','')).strip() for r in rows]
    act_base = [str(r.get('action_BASE_ONLY','')).strip() for r in rows]
    det_anchor = eval_metrics(gt, pred_det, ['FUSION_BOOST']*len(rows))
    base_anchor = eval_metrics(gt, pred_base, act_base)

    unique_board_ids = sorted({str(r.get('board_id', '')).strip() for r in rows if str(r.get('board_id', '')).strip()})
    unique_holdout_ids = sorted({str(r.get('holdout_window_id', '')).strip() for r in rows if str(r.get('holdout_window_id', '')).strip()})
    unique_expanded_ids = sorted({str(r.get('expanded_window_id', '')).strip() for r in rows if str(r.get('expanded_window_id', '')).strip()})
    lobo_mode = 'none'
    lobo_group_field = 'board_id'
    if len(unique_board_ids) >= 2:
        lobo_mode = 'board_id'
        lobo_group_field = 'board_id'
    elif len(unique_holdout_ids) >= 2:
        lobo_mode = 'holdout_window_id_proxy'
        lobo_group_field = 'holdout_window_id'
    elif len(unique_expanded_ids) >= 2:
        lobo_mode = 'expanded_window_id_proxy'
        lobo_group_field = 'expanded_window_id'

    bootstrap_raw_rows: List[Dict[str, Any]] = []
    bootstrap_summary_rows: List[Dict[str, Any]] = []
    lobo_rows: List[Dict[str, Any]] = []

    for pname, (pk, ak) in policies.items():
        raw, summ = bootstrap_metrics(rows, pred_key=pk, action_key=ak, B=args.bootstrap_B, seed=args.seed + len(pname))

        # add raw rows
        for i, rr in enumerate(raw, start=1):
            bootstrap_raw_rows.append({
                'policy_name': pname,
                'bootstrap_id': i,
                **rr,
            })

        arr_fb = np.array([x['fallback_rate'] for x in raw], dtype=float)
        arr_rr = np.array([x['rear_risk'] for x in raw], dtype=float)
        arr_ut = np.array([x['utility'] for x in raw], dtype=float)

        p_rear_le_det = float(np.mean(arr_rr <= float(det_anchor['rear_risk'])))
        valid_ut = np.isfinite(arr_ut)
        if np.any(valid_ut):
            p_ut_ge_base = float(np.mean(arr_ut[valid_ut] >= float(base_anchor['utility'])))
        else:
            p_ut_ge_base = float('nan')
        anchor_fb = float(np.mean([1.0 if str(r.get(ak,''))=='DEFER' else 0.0 for r in rows]))
        p_fb_close = float(np.mean(np.abs(arr_fb - anchor_fb) <= 0.01))

        bootstrap_summary_rows.append({
            'policy_name': pname,
            'fallback_mean': summ['fallback_mean'],
            'fallback_median': summ['fallback_median'],
            'fallback_p10': summ['fallback_p10'],
            'fallback_p90': summ['fallback_p90'],
            'fallback_p95': summ['fallback_p95'],
            'rear_risk_mean': summ['rear_mean'],
            'rear_risk_median': summ['rear_median'],
            'rear_risk_p10': summ['rear_p10'],
            'rear_risk_p90': summ['rear_p90'],
            'rear_risk_p95': summ['rear_p95'],
            'utility_mean': summ['utility_mean'],
            'utility_median': summ['utility_median'],
            'utility_p10': summ['utility_p10'],
            'utility_p90': summ['utility_p90'],
            'utility_p95': summ['utility_p95'],
            'utility_valid_fraction': summ['utility_valid_fraction'],
            'P_rear_risk_le_deterministic': p_rear_le_det,
            'P_utility_ge_baseline': p_ut_ge_base,
            'P_abs_fallback_minus_anchor_le_0p01': p_fb_close,
            'anchor_fallback': anchor_fb,
            'deterministic_rear_risk_anchor': det_anchor['rear_risk'],
            'baseline_utility_anchor': base_anchor['utility'],
        })

        # LOBO
        if lobo_mode != 'none':
            lobo = lobo_metrics(rows, pred_key=pk, action_key=ak, group_field=lobo_group_field)
            for lr in lobo:
                lobo_rows.append({'policy_name': pname, **lr, 'lobo_mode': lobo_mode})

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_csv = out_dir / 'exp8_bootstrap_raw.csv'
    write_csv(raw_csv, bootstrap_raw_rows, ['policy_name','bootstrap_id','fallback_rate','rear_risk','utility','auto_error'])

    summary_csv = out_dir / 'exp8_bootstrap_summary.csv'
    write_csv(summary_csv, bootstrap_summary_rows, list(bootstrap_summary_rows[0].keys()))

    lobo_csv = out_dir / 'exp8_lobo_summary.csv'
    if lobo_rows:
        write_csv(
            lobo_csv,
            lobo_rows,
            ['policy_name', 'lobo_mode', 'lobo_group_field', 'left_out_unit', 'fallback_rate', 'rear_risk', 'utility', 'auto_error', 'n_remaining']
        )
    else:
        write_csv(
            lobo_csv,
            [],
            ['policy_name', 'lobo_mode', 'lobo_group_field', 'left_out_unit', 'fallback_rate', 'rear_risk', 'utility', 'auto_error', 'n_remaining']
        )

    # plots (TS3/TS2 distributions)
    def plot_dist(policy: str, out_png: Path):
        sub = [r for r in bootstrap_raw_rows if r['policy_name'] == policy]
        if not sub:
            return
        fb = np.array([float(r['fallback_rate']) for r in sub], dtype=float)
        rr = np.array([float(r['rear_risk']) for r in sub], dtype=float)
        ut = np.array([float(r['utility']) for r in sub], dtype=float)

        fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.4), dpi=220)
        axes[0].hist(fb, bins=30)
        axes[0].set_title('fallback')
        axes[1].hist(rr, bins=30)
        axes[1].set_title('rear_risk')
        axes[2].hist(ut, bins=30)
        axes[2].set_title('utility')
        fig.suptitle(f'{policy} bootstrap distributions')
        plt.tight_layout()
        out_png.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_png, dpi=220)
        plt.close()

    plot_dist('TS3', out_dir / 'exp8_ts3_bootstrap_distribution.png')
    plot_dist('TS2', out_dir / 'exp8_ts2_bootstrap_distribution.png')

    # lobo span plot
    lobo_png = out_dir / 'exp8_lobo_metric_spans.png'
    if lobo_rows:
        plt.figure(figsize=(8.6, 4.8), dpi=220)
        policy_names = ['TS3','TS2','BA2','DETERMINISTIC_FUSION','BASE_ONLY']
        for i, p in enumerate(policy_names):
            sub = [r for r in lobo_rows if r['policy_name'] == p]
            if not sub:
                continue
            vals = [float(r['rear_risk']) for r in sub]
            plt.plot([i, i], [min(vals), max(vals)], color='tab:blue', linewidth=2)
            plt.scatter([i]*len(vals), vals, color='tab:blue', s=18)
        plt.xticks(range(len(policy_names)), policy_names, rotation=20)
        plt.ylabel('LOBO rear_risk span')
        plt.title('LOBO Metric Spans by Policy')
        plt.grid(True, axis='y', alpha=0.25)
        plt.tight_layout()
        plt.savefig(lobo_png, dpi=220)
        plt.close()
    else:
        plt.figure(figsize=(8.0, 3.6), dpi=220)
        plt.text(0.5, 0.5, 'LOBO unavailable: only one valid grouping unit in input', ha='center', va='center')
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(lobo_png, dpi=220)
        plt.close()

    md = []
    md.append('# Exp8 Selected-Point Stability')
    md.append('')
    md.append('## Purpose')
    md.append('Quantify selected-point perturbation behavior via bootstrap and LOBO.')
    md.append('')
    md.append('## Input')
    md.append(f'- expanded_diff: `{Path(args.input).resolve()}`')
    md.append(f'- bootstrap_B: {args.bootstrap_B}')
    md.append(f'- lobo_mode: {lobo_mode}')
    if lobo_mode != 'board_id':
        md.append(f'- lobo_group_field: {lobo_group_field} (proxy)')
    md.append('')
    md.append('## TS3 Focus')
    ts3 = next((r for r in bootstrap_summary_rows if r['policy_name'] == 'TS3'), None)
    if ts3:
        md.append(f"- TS3 fallback mean/median/p90: {ts3['fallback_mean']:.6f} / {ts3['fallback_median']:.6f} / {ts3['fallback_p90']:.6f}")
        md.append(f"- TS3 rear risk mean/median/p90: {ts3['rear_risk_mean']:.6f} / {ts3['rear_risk_median']:.6f} / {ts3['rear_risk_p90']:.6f}")
        md.append(f"- TS3 utility mean/median/p90: {ts3['utility_mean']:.6f} / {ts3['utility_median']:.6f} / {ts3['utility_p90']:.6f}")
        md.append(f"- P(rear_risk <= deterministic): {ts3['P_rear_risk_le_deterministic']:.6f}")
        md.append(f"- P(utility >= baseline): {ts3['P_utility_ge_baseline']:.6f}")
        md.append(f"- P(|fallback-anchor|<=0.01): {ts3['P_abs_fallback_minus_anchor_le_0p01']:.6f}")
    md.append('')
    md.append('## Interpretation')
    md.append('- Low fallback and rear-risk relationship can be checked as perturbation-stability signals.')
    md.append('- Utility should be interpreted as around-threshold fluctuation, not uniform above-threshold invariance.')
    md.append('')
    md.append('## Limitations')
    md.append('- TS2/BA2 are proxy reconstructions from available traces; explicit canonical TS2/BA2 action files were not found in frozen reports by filename.')
    if lobo_mode == 'none':
        md.append('- Board-level LOBO is unavailable because only one valid board_id is present in the selected input trace.')
    elif lobo_mode != 'board_id':
        md.append(f'- Board-level LOBO is unavailable in this input; LOBO uses `{lobo_group_field}` as a proxy grouping unit.')

    (out_dir / 'exp8_selected_point_stability.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({'status':'ok','bootstrap_rows':len(bootstrap_raw_rows),'lobo_rows':len(lobo_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
