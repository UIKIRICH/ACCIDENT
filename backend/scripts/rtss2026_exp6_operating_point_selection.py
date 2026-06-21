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


def eval_metrics(rows: List[Dict[str, Any]], pred_key: str) -> Dict[str, float]:
    gt = [str(r.get('gt_type', '')).strip() for r in rows]
    pr = [str(r.get(pred_key, '')).strip() for r in rows]
    n = len(gt)
    if n == 0:
        return {'rear_risk': float('nan'), 'auto_error': float('nan'), 'lane_recall': float('nan'), 'turn_recall': float('nan'), 'utility': float('nan')}

    rear_idx = [i for i, g in enumerate(gt) if g == 'rear_end']
    rear_miss = sum(1 for i in rear_idx if pr[i] != 'rear_end')
    rear_risk = rear_miss / len(rear_idx) if rear_idx else float('nan')

    auto_error = sum(1 for g, p in zip(gt, pr) if g != p) / n

    def recall(c: str) -> float:
        idx = [i for i, g in enumerate(gt) if g == c]
        if not idx:
            return float('nan')
        return sum(1 for i in idx if pr[i] == c) / len(idx)

    lane_r = recall('lane_change')
    turn_r = recall('turn_conflict')
    utility = 0.5 * lane_r + 0.5 * turn_r if not (math.isnan(lane_r) or math.isnan(turn_r)) else float('nan')

    return {'rear_risk': rear_risk, 'auto_error': auto_error, 'lane_recall': lane_r, 'turn_recall': turn_r, 'utility': utility}


def main() -> None:
    parser = argparse.ArgumentParser(description='RTSS2026 Exp6: operating-point selection rule formalization.')
    parser.add_argument('--input', required=True, help='exp5_large_replay_metrics.csv')
    parser.add_argument('--output_dir', required=True)
    parser.add_argument('--seed', type=int, default=20260521)
    parser.add_argument('--policy', default='ALL')
    parser.add_argument('--repeat', type=int, default=0)
    parser.add_argument('--duration_sec', type=int, default=0)
    args = parser.parse_args()

    metrics_path = Path(args.input).resolve()
    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = read_csv(metrics_path)
    if not rows:
        raise RuntimeError(f'No rows in {metrics_path}')

    # map variant_name + synthetic tuple labels (for reproducible selection table)
    tuple_map = {
        'GUARDED_TS3': 'src=0.4|ssc=0.6|c=0.98|m=0.55',
        'GUARDED_TS2': 'src=0.2|ssc=0.8|c=0.99|m=0.35',
        'GUARDED_BA2': 'src=0.3|ssc=0.7|c=0.97|m=0.45',
        'BASE_ONLY': 'baseline_locked',
        'DETERMINISTIC_FUSION': 'deterministic_replace',
        'CONFIDENCE_ONLY_BASELINE': 'conf_only',
        'BUDGET_MATCHED_CONF_BASELINE': 'budget_matched_conf',
    }

    # candidate table
    candidates: List[Dict[str, Any]] = []
    for r in rows:
        name = r['policy_name']
        candidates.append({
            'variant_name': name,
            'tuple_or_thresholds': tuple_map.get(name, 'NA'),
            'fallback_rate': float(r['fallback_rate']),
            'rear_risk': float(r['rear_risk']),
            'auto_error': float(r['auto_error']),
            'utility': float(r['utility']),
            'lane_recall': float(r['lane_recall']),
            'turn_recall': float(r['turn_recall']),
            'auto_coverage': float(r['auto_coverage']),
            'selection_status': 'candidate',
        })

    # anchors
    det = next((c for c in candidates if c['variant_name'] == 'DETERMINISTIC_FUSION'), None)
    base = next((c for c in candidates if c['variant_name'] == 'BASE_ONLY'), None)
    if det is None or base is None:
        raise RuntimeError('Need BASE_ONLY and DETERMINISTIC_FUSION in candidate table')

    det_rr = float(det['rear_risk'])
    base_ut = float(base['utility'])

    # Rule A: Balanced Low-Fallback Contract
    a_pool = [c for c in candidates if (c['rear_risk'] < det_rr and c['utility'] > base_ut and c['fallback_rate'] <= 0.02)]
    # fallback too strict might yield none under current data; use deterministic fallback to note failure
    rule_a_pick = None
    if a_pool:
        a_pool = sorted(a_pool, key=lambda c: (c['fallback_rate'], -c['utility'], c['rear_risk']))
        rule_a_pick = a_pool[0]

    # Rule B: Low-Rear Endpoint (with utility >= baseline*0.95)
    ub = base_ut * 0.95
    b_pool = [c for c in candidates if c['utility'] >= ub]
    rule_b_pick = None
    if b_pool:
        b_pool = sorted(b_pool, key=lambda c: (c['rear_risk'], c['fallback_rate'], -c['utility']))
        rule_b_pick = b_pool[0]

    # Rule C for multiple beta
    betas = [0.01, 0.02, 0.05, 0.10, 0.20]
    rule_c_rows: List[Dict[str, Any]] = []
    for beta in betas:
        c_pool = [c for c in candidates if c['fallback_rate'] <= beta and c['rear_risk'] < det_rr]
        if c_pool:
            c_pool = sorted(c_pool, key=lambda c: (-c['utility'], c['rear_risk'], c['fallback_rate']))
            pick = c_pool[0]
            rule_c_rows.append({
                'rule_name': 'Rule_C_Capacity_Constrained_Selection',
                'beta': beta,
                'selected_variant': pick['variant_name'],
                'selected_fallback_rate': pick['fallback_rate'],
                'selected_rear_risk': pick['rear_risk'],
                'selected_utility': pick['utility'],
                'selection_reason': 'max utility under fallback<=beta and rear_risk<deterministic',
            })
        else:
            rule_c_rows.append({
                'rule_name': 'Rule_C_Capacity_Constrained_Selection',
                'beta': beta,
                'selected_variant': 'NONE',
                'selected_fallback_rate': 'NA',
                'selected_rear_risk': 'NA',
                'selected_utility': 'NA',
                'selection_reason': 'no candidate satisfies constraints',
            })

    # selection summary rows
    sel_rows: List[Dict[str, Any]] = []
    if rule_a_pick is not None:
        sel_rows.append({
            'rule_name': 'Rule_A_Balanced_Low_Fallback_Contract',
            'beta': 'NA',
            'selected_variant': rule_a_pick['variant_name'],
            'selected_fallback_rate': rule_a_pick['fallback_rate'],
            'selected_rear_risk': rule_a_pick['rear_risk'],
            'selected_utility': rule_a_pick['utility'],
            'selection_reason': 'min fallback then max utility then min rear risk',
        })
    else:
        sel_rows.append({
            'rule_name': 'Rule_A_Balanced_Low_Fallback_Contract',
            'beta': 'NA',
            'selected_variant': 'NONE',
            'selected_fallback_rate': 'NA',
            'selected_rear_risk': 'NA',
            'selected_utility': 'NA',
            'selection_reason': 'no candidate meets fallback<=0.02 + utility>baseline + rear_risk<deterministic',
        })

    if rule_b_pick is not None:
        sel_rows.append({
            'rule_name': 'Rule_B_Low_Rear_Endpoint',
            'beta': 'NA',
            'selected_variant': rule_b_pick['variant_name'],
            'selected_fallback_rate': rule_b_pick['fallback_rate'],
            'selected_rear_risk': rule_b_pick['rear_risk'],
            'selected_utility': rule_b_pick['utility'],
            'selection_reason': 'min rear risk with utility floor',
        })
    else:
        sel_rows.append({
            'rule_name': 'Rule_B_Low_Rear_Endpoint',
            'beta': 'NA',
            'selected_variant': 'NONE',
            'selected_fallback_rate': 'NA',
            'selected_rear_risk': 'NA',
            'selected_utility': 'NA',
            'selection_reason': 'no candidate meets utility floor',
        })

    sel_rows.extend(rule_c_rows)

    # update selection_status tags
    selected_names = {r['selected_variant'] for r in sel_rows if r['selected_variant'] not in {'NONE', ''}}
    for c in candidates:
        if c['variant_name'] in selected_names:
            c['selection_status'] = 'selected_by_rule'

    candidate_csv = out_dir / 'exp6_candidate_points.csv'
    write_csv(candidate_csv, candidates, [
        'variant_name','tuple_or_thresholds','fallback_rate','rear_risk','auto_error','utility',
        'lane_recall','turn_recall','auto_coverage','selection_status'
    ])

    selection_csv = out_dir / 'exp6_selection_results.csv'
    write_csv(selection_csv, sel_rows, [
        'rule_name','beta','selected_variant','selected_fallback_rate','selected_rear_risk','selected_utility','selection_reason'
    ])

    # frontier plot
    x = np.array([c['fallback_rate'] for c in candidates], dtype=float)
    y = np.array([c['rear_risk'] for c in candidates], dtype=float)
    u = np.array([c['utility'] for c in candidates], dtype=float)

    plt.figure(figsize=(6.8, 4.8), dpi=220)
    sc = plt.scatter(x, y, c=u, cmap='plasma', s=85)
    for c in candidates:
        mark = '*' if c['selection_status'] == 'selected_by_rule' else 'o'
        plt.scatter([c['fallback_rate']], [c['rear_risk']], s=95 if mark == '*' else 0, marker=mark, edgecolors='black', facecolors='none')
        plt.annotate(c['variant_name'], (c['fallback_rate'], c['rear_risk']), fontsize=7, xytext=(4, 4), textcoords='offset points')
    plt.colorbar(sc, label='utility')
    plt.xlabel('fallback_rate')
    plt.ylabel('rear_risk')
    plt.title('Operating-Point Frontier and Rule-based Selections')
    plt.grid(True, alpha=0.25)
    plt.tight_layout()
    plt.savefig(out_dir / 'exp6_selection_frontier.png', dpi=220)
    plt.close()

    # summary md
    md = []
    md.append('# Exp6 Operating-Point Selection Rule')
    md.append('')
    md.append('## Purpose')
    md.append('Formalize operating-point selection to avoid post-hoc hand-picking.')
    md.append('')
    md.append('## Inputs')
    md.append(f'- candidate_metrics: `{metrics_path}`')
    md.append('')
    md.append('## Rule Outcomes')
    for r in sel_rows:
        md.append(f"- {r['rule_name']} (beta={r['beta']}): `{r['selected_variant']}` | reason: {r['selection_reason']}")
    md.append('')

    ts3_selected = any(r['selected_variant'] == 'GUARDED_TS3' for r in sel_rows)
    ts2_selected = any(r['selected_variant'] == 'GUARDED_TS2' for r in sel_rows)

    md.append('## Interpretation')
    md.append(f"- TS3 selected by at least one fixed rule: {'YES' if ts3_selected else 'NO'}")
    md.append(f"- TS2 selected by low-rear endpoint rule: {'YES' if ts2_selected else 'NO'}")
    md.append('- No claim of unique global optimum; selection is contract-facing and rule-constrained.')

    (out_dir / 'exp6_selection_summary.md').write_text('\n'.join(md), encoding='utf-8')

    print(json.dumps({'status':'ok','candidate_n':len(candidates),'selection_rows':len(sel_rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
