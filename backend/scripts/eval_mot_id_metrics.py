import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    from scipy.optimize import linear_sum_assignment  # type: ignore
except Exception:
    linear_sum_assignment = None


Det = Tuple[int, Tuple[float, float, float, float], float]  # (id, (x,y,w,h), score/conf)


def parse_line_to_det(line: str, default_score: float = 1.0) -> Optional[Tuple[int, int, float, float, float, float, float]]:
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) < 6:
        return None
    frame = int(float(parts[0]))
    tid = int(float(parts[1]))
    x = float(parts[2])
    y = float(parts[3])
    w = float(parts[4])
    h = float(parts[5])
    score = float(parts[6]) if len(parts) > 6 else float(default_score)
    return frame, tid, x, y, w, h, score


def load_mot(path: Path, is_gt: bool) -> Dict[int, List[Det]]:
    out: Dict[int, List[Det]] = {}
    with path.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            rec = parse_line_to_det(raw, default_score=1.0)
            if rec is None:
                continue
            frame, tid, x, y, w, h, score = rec
            if is_gt:
                score = 1.0
            out.setdefault(frame, []).append((tid, (x, y, w, h), score))
    return out


def iou_xywh(a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    ix1 = max(ax, bx)
    iy1 = max(ay, by)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    union = aw * ah + bw * bh - inter
    if union <= 0:
        return 0.0
    return inter / union


def greedy_match(iou_mat: np.ndarray, iou_thr: float) -> List[Tuple[int, int]]:
    pairs: List[Tuple[int, int, float]] = []
    for i in range(iou_mat.shape[0]):
        for j in range(iou_mat.shape[1]):
            v = float(iou_mat[i, j])
            if v >= iou_thr:
                pairs.append((i, j, v))
    pairs.sort(key=lambda x: x[2], reverse=True)
    used_i = set()
    used_j = set()
    matched: List[Tuple[int, int]] = []
    for i, j, _ in pairs:
        if i in used_i or j in used_j:
            continue
        used_i.add(i)
        used_j.add(j)
        matched.append((i, j))
    return matched


def hungarian_match(iou_mat: np.ndarray, iou_thr: float) -> List[Tuple[int, int]]:
    if iou_mat.size == 0:
        return []

    if linear_sum_assignment is None:
        return greedy_match(iou_mat, iou_thr)

    # Minimize cost = 1 - IoU; suppress invalid matches with large constant.
    cost = np.ones_like(iou_mat, dtype=np.float64) * 1e6
    valid = iou_mat >= iou_thr
    cost[valid] = 1.0 - iou_mat[valid]
    row_ind, col_ind = linear_sum_assignment(cost)
    out: List[Tuple[int, int]] = []
    for r, c in zip(row_ind.tolist(), col_ind.tolist()):
        if r < iou_mat.shape[0] and c < iou_mat.shape[1] and iou_mat[r, c] >= iou_thr:
            out.append((r, c))
    return out


def collect_txts(path: Path) -> Dict[str, Path]:
    if path.is_file():
        return {path.stem: path}
    out: Dict[str, Path] = {}
    for p in sorted(path.glob("*.txt")):
        out[p.stem] = p
    return out


def best_id_mapping(pair_counts: Dict[Tuple[int, int], int]) -> Tuple[int, Dict[int, int]]:
    if not pair_counts:
        return 0, {}
    gt_ids = sorted({k[0] for k in pair_counts.keys()})
    pr_ids = sorted({k[1] for k in pair_counts.keys()})
    gi = {g: i for i, g in enumerate(gt_ids)}
    pj = {p: j for j, p in enumerate(pr_ids)}

    mat = np.zeros((len(gt_ids), len(pr_ids)), dtype=np.int64)
    for (g, p), v in pair_counts.items():
        mat[gi[g], pj[p]] = int(v)

    if linear_sum_assignment is None:
        used_c = set()
        mapping: Dict[int, int] = {}
        total = 0
        for r in np.argsort(-mat.max(axis=1)):
            c = int(np.argmax(mat[r]))
            if c in used_c:
                continue
            v = int(mat[r, c])
            if v <= 0:
                continue
            used_c.add(c)
            g = gt_ids[r]
            p = pr_ids[c]
            mapping[g] = p
            total += v
        return total, mapping

    row_ind, col_ind = linear_sum_assignment(-mat.astype(np.float64))
    total = 0
    mapping: Dict[int, int] = {}
    for r, c in zip(row_ind.tolist(), col_ind.tolist()):
        v = int(mat[r, c])
        if v <= 0:
            continue
        g = gt_ids[r]
        p = pr_ids[c]
        mapping[g] = p
        total += v
    return total, mapping


def eval_sequence(gt_frames: Dict[int, List[Det]], pred_frames: Dict[int, List[Det]], iou_thr: float) -> Dict[str, float]:
    frames = sorted(set(gt_frames.keys()) | set(pred_frames.keys()))
    total_gt = sum(len(gt_frames.get(f, [])) for f in frames)
    total_pred = sum(len(pred_frames.get(f, [])) for f in frames)

    fn = 0
    fp = 0
    idsw = 0
    pair_counts: Dict[Tuple[int, int], int] = {}
    last_pred_by_gt: Dict[int, int] = {}

    for frame in frames:
        g = gt_frames.get(frame, [])
        p = pred_frames.get(frame, [])
        if not g and not p:
            continue

        iou_mat = np.zeros((len(g), len(p)), dtype=np.float64)
        for i, (_, gb, _) in enumerate(g):
            for j, (_, pb, _) in enumerate(p):
                iou_mat[i, j] = iou_xywh(gb, pb)

        matches = hungarian_match(iou_mat, iou_thr)
        matched_g = set()
        matched_p = set()

        for gi, pj in matches:
            matched_g.add(gi)
            matched_p.add(pj)
            gt_id = g[gi][0]
            pr_id = p[pj][0]
            pair_counts[(gt_id, pr_id)] = pair_counts.get((gt_id, pr_id), 0) + 1

            prev = last_pred_by_gt.get(gt_id)
            if prev is not None and prev != pr_id:
                idsw += 1
            last_pred_by_gt[gt_id] = pr_id

        fn += (len(g) - len(matched_g))
        fp += (len(p) - len(matched_p))

    idtp, _ = best_id_mapping(pair_counts)
    idfn = total_gt - idtp
    idfp = total_pred - idtp

    mota = 1.0 - ((fn + fp + idsw) / total_gt) if total_gt > 0 else 0.0
    idf1 = (2.0 * idtp) / (2.0 * idtp + idfp + idfn) if (2 * idtp + idfp + idfn) > 0 else 0.0
    idp = idtp / (idtp + idfp) if (idtp + idfp) > 0 else 0.0
    idr = idtp / (idtp + idfn) if (idtp + idfn) > 0 else 0.0

    return {
        "gt_det_total": float(total_gt),
        "pred_det_total": float(total_pred),
        "FN": float(fn),
        "FP": float(fp),
        "IDSW": float(idsw),
        "IDTP": float(idtp),
        "IDFP": float(idfp),
        "IDFN": float(idfn),
        "MOTA": float(mota),
        "IDF1": float(idf1),
        "IDP": float(idp),
        "IDR": float(idr),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MOT metrics (IDF1 / MOTA) from MOT txt files.")
    parser.add_argument("--gt", required=True, help="GT MOT txt file or directory of txt files.")
    parser.add_argument("--pred", required=True, help="Pred MOT txt file or directory of txt files.")
    parser.add_argument("--iou-thr", type=float, default=0.5, help="IoU threshold for frame matching.")
    parser.add_argument("--out-json", required=True, help="Output report json.")
    args = parser.parse_args()

    gt_path = Path(args.gt).resolve()
    pred_path = Path(args.pred).resolve()
    out_json = Path(args.out_json).resolve()

    gt_files = collect_txts(gt_path)
    pred_files = collect_txts(pred_path)
    common = sorted(set(gt_files.keys()) & set(pred_files.keys()))
    if not common:
        raise RuntimeError("No common sequence stems between GT and PRED.")

    report = {
        "task": "mot_id_metrics",
        "iou_thr": float(args.iou_thr),
        "gt_input": str(gt_path),
        "pred_input": str(pred_path),
        "sequences": {},
    }

    agg = {
        "gt_det_total": 0.0,
        "pred_det_total": 0.0,
        "FN": 0.0,
        "FP": 0.0,
        "IDSW": 0.0,
        "IDTP": 0.0,
        "IDFP": 0.0,
        "IDFN": 0.0,
    }

    for stem in common:
        gt_frames = load_mot(gt_files[stem], is_gt=True)
        pr_frames = load_mot(pred_files[stem], is_gt=False)
        m = eval_sequence(gt_frames, pr_frames, iou_thr=float(args.iou_thr))
        report["sequences"][stem] = m
        print(f"[SEQ] {stem} MOTA={m['MOTA']:.6f} IDF1={m['IDF1']:.6f}")
        for k in agg:
            agg[k] += float(m[k])

    gt_total = agg["gt_det_total"]
    idtp = agg["IDTP"]
    idfp = agg["IDFP"]
    idfn = agg["IDFN"]
    mota = 1.0 - ((agg["FN"] + agg["FP"] + agg["IDSW"]) / gt_total) if gt_total > 0 else 0.0
    idf1 = (2.0 * idtp) / (2.0 * idtp + idfp + idfn) if (2 * idtp + idfp + idfn) > 0 else 0.0
    idp = idtp / (idtp + idfp) if (idtp + idfp) > 0 else 0.0
    idr = idtp / (idtp + idfn) if (idtp + idfn) > 0 else 0.0

    report["overall"] = {
        **agg,
        "MOTA": mota,
        "IDF1": idf1,
        "IDP": idp,
        "IDR": idr,
        "num_sequences": len(common),
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] overall MOTA={mota:.6f} IDF1={idf1:.6f}")
    print(f"[DONE] report: {out_json}")


if __name__ == "__main__":
    main()

