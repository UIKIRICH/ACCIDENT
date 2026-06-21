import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np


Box = Tuple[float, float, float, float]  # x,y,w,h


def parse_line(line: str, default_score: float = 1.0) -> Optional[Tuple[int, Box, float]]:
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) < 6:
        return None
    frame = int(float(parts[0]))
    x = float(parts[2])
    y = float(parts[3])
    w = float(parts[4])
    h = float(parts[5])
    score = float(parts[6]) if len(parts) > 6 else float(default_score)
    return frame, (x, y, w, h), score


def load_mot_det(path: Path, is_gt: bool) -> Dict[int, List[Tuple[Box, float]]]:
    out: Dict[int, List[Tuple[Box, float]]] = {}
    with path.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            rec = parse_line(raw, default_score=1.0)
            if rec is None:
                continue
            frame, box, score = rec
            if is_gt:
                score = 1.0
            out.setdefault(frame, []).append((box, score))
    return out


def iou_xywh(a: Box, b: Box) -> float:
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


def collect_txts(path: Path) -> Dict[str, Path]:
    if path.is_file():
        return {path.stem: path}
    out: Dict[str, Path] = {}
    for p in sorted(path.glob("*.txt")):
        out[p.stem] = p
    return out


def ap_101point(recalls: np.ndarray, precisions: np.ndarray) -> float:
    # COCO-style 101-point interpolation.
    ap_points = []
    for r in np.linspace(0.0, 1.0, 101):
        mask = recalls >= r
        p = float(np.max(precisions[mask])) if np.any(mask) else 0.0
        ap_points.append(p)
    return float(np.mean(ap_points))


def eval_ap_for_iou(
    gt_all: Dict[str, Dict[int, List[Tuple[Box, float]]]],
    pred_all: Dict[str, Dict[int, List[Tuple[Box, float]]]],
    iou_thr: float,
) -> float:
    # Flatten predictions: (score, seq, frame, box)
    preds: List[Tuple[float, str, int, Box]] = []
    total_gt = 0

    for seq, gframes in gt_all.items():
        for frame, gs in gframes.items():
            total_gt += len(gs)

    if total_gt <= 0:
        return 0.0

    for seq, pframes in pred_all.items():
        for frame, ps in pframes.items():
            for box, score in ps:
                preds.append((float(score), seq, int(frame), box))

    preds.sort(key=lambda x: x[0], reverse=True)

    # Per-threshold matching flags.
    gt_used: Dict[Tuple[str, int], List[bool]] = {}
    for seq, gframes in gt_all.items():
        for frame, gs in gframes.items():
            gt_used[(seq, int(frame))] = [False] * len(gs)

    tps = np.zeros(len(preds), dtype=np.float64)
    fps = np.zeros(len(preds), dtype=np.float64)

    for i, (_, seq, frame, pbox) in enumerate(preds):
        g_list = gt_all.get(seq, {}).get(frame, [])
        if not g_list:
            fps[i] = 1.0
            continue

        used = gt_used[(seq, frame)]
        best_j = -1
        best_iou = -1.0
        for j, (gbox, _) in enumerate(g_list):
            if used[j]:
                continue
            v = iou_xywh(pbox, gbox)
            if v > best_iou:
                best_iou = v
                best_j = j

        if best_j >= 0 and best_iou >= iou_thr:
            used[best_j] = True
            tps[i] = 1.0
        else:
            fps[i] = 1.0

    tp_cum = np.cumsum(tps)
    fp_cum = np.cumsum(fps)
    recalls = tp_cum / float(total_gt)
    precisions = tp_cum / np.maximum(tp_cum + fp_cum, 1e-12)
    return ap_101point(recalls, precisions)


def parse_iou_thresholds(raw: str) -> List[float]:
    s = (raw or "").strip().lower()
    if not s:
        return [0.5 + 0.05 * i for i in range(10)]  # 0.50~0.95
    if s == "coco":
        return [0.5 + 0.05 * i for i in range(10)]
    vals = []
    for x in s.split(","):
        x = x.strip()
        if not x:
            continue
        vals.append(float(x))
    return vals


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate detection mAP from MOT-format GT/PRED txt files.")
    parser.add_argument("--gt", required=True, help="GT txt file or directory of txt files.")
    parser.add_argument("--pred", required=True, help="Prediction txt file or directory of txt files.")
    parser.add_argument(
        "--iou-thresholds",
        default="coco",
        help="Comma list (e.g. 0.5,0.75) or 'coco' for 0.50:0.95 step 0.05.",
    )
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

    gt_all: Dict[str, Dict[int, List[Tuple[Box, float]]]] = {}
    pred_all: Dict[str, Dict[int, List[Tuple[Box, float]]]] = {}
    for stem in common:
        gt_all[stem] = load_mot_det(gt_files[stem], is_gt=True)
        pred_all[stem] = load_mot_det(pred_files[stem], is_gt=False)

    iou_thresholds = parse_iou_thresholds(args.iou_thresholds)
    ap_by_iou: Dict[str, float] = {}
    for t in iou_thresholds:
        ap = eval_ap_for_iou(gt_all, pred_all, iou_thr=float(t))
        ap_by_iou[f"{t:.2f}"] = float(ap)
        print(f"[AP] IoU={t:.2f} AP={ap:.6f}")

    map50 = ap_by_iou.get("0.50", float("nan"))
    map50_95 = float(np.mean(list(ap_by_iou.values()))) if ap_by_iou else float("nan")

    report = {
        "task": "det_map_from_mot",
        "gt_input": str(gt_path),
        "pred_input": str(pred_path),
        "sequences": common,
        "iou_thresholds": iou_thresholds,
        "ap_by_iou": ap_by_iou,
        "mAP@0.5": map50,
        "mAP@0.5:0.95": map50_95,
    }

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] mAP@0.5={map50:.6f} mAP@0.5:0.95={map50_95:.6f}")
    print(f"[DONE] report: {out_json}")


if __name__ == "__main__":
    main()

