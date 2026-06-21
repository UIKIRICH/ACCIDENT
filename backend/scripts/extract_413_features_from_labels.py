import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import pandas as pd


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no} invalid json: {exc}") from exc
    return rows


def safe_str(v: Any) -> str:
    return str(v).strip()


def resolve_video_path(videos_root: Path, video_ref: str) -> Path:
    p = Path(video_ref)
    if p.is_absolute():
        return p
    return (videos_root / p).resolve()


def extract_pixel_features(video_path: Path, num_frames: int = 32) -> Optional[np.ndarray]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return None
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return None

    idxs = np.linspace(0, total_frames - 1, num_frames, dtype=int)
    vals: List[float] = []
    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            vals.append(0.0)
            continue
        frame = cv2.resize(frame, (224, 224))
        vals.append(float(frame.mean()))
    cap.release()
    return np.array(vals, dtype=np.float32)


def extract_optical_features(video_path: Path, num_frames: int = 32) -> np.ndarray:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return np.zeros((341,), dtype=np.float32)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames < 2:
        cap.release()
        return np.zeros((341,), dtype=np.float32)

    idxs = np.linspace(0, total_frames - 1, num_frames, dtype=int)

    cap.set(cv2.CAP_PROP_POS_FRAMES, int(idxs[0]))
    ok, prev = cap.read()
    if not ok:
        cap.release()
        return np.zeros((341,), dtype=np.float32)
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    prev_gray = cv2.resize(prev_gray, (224, 224))

    feats: List[float] = []
    for idx in idxs[1:]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, curr = cap.read()
        if not ok:
            break
        curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
        curr_gray = cv2.resize(curr_gray, (224, 224))

        flow = cv2.calcOpticalFlowFarneback(
            prev_gray,
            curr_gray,
            None,
            pyr_scale=0.5,
            levels=3,
            winsize=15,
            iterations=3,
            poly_n=5,
            poly_sigma=1.2,
            flags=0,
        )
        # NOTE: Keep this block exactly aligned with the historical training
        # extractor used to build full_features_with_id.csv:
        # [mean_mag, std_mag, mean_angle, angle_hist_8bins]
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        hist_angle, _ = np.histogram(ang, bins=8, range=(0, 2 * np.pi))
        hist_angle = hist_angle / (hist_angle.sum() + 1e-6)

        feats.extend(
            [
                float(np.mean(mag)),
                float(np.std(mag)),
                float(np.mean(ang)),
                *[float(x) for x in hist_angle.tolist()],
            ]
        )
        prev_gray = curr_gray

    cap.release()
    expected = 31 * 11
    if len(feats) < expected:
        feats.extend([0.0] * (expected - len(feats)))
    return np.array(feats[:expected], dtype=np.float32)


def extract_vehicle_features(
    video_path: Path,
    yolo_model: Any,
    num_frames: int = 8,
) -> np.ndarray:
    if yolo_model is None:
        return np.zeros((40,), dtype=np.float32)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return np.zeros((40,), dtype=np.float32)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return np.zeros((40,), dtype=np.float32)

    idxs = np.linspace(0, total_frames - 1, num_frames, dtype=int)
    vals: List[float] = []

    for idx in idxs:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok:
            vals.extend([0.0, 0.0, 0.0, 0.0, 0.0])
            continue

        rs = yolo_model(frame, verbose=False, conf=0.3)
        cars: List[Dict[str, float]] = []
        for r in rs:
            boxes = getattr(r, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                cls_id = int(box.cls[0])
                name = str(yolo_model.names[cls_id])
                if name not in {"car", "truck", "bus"}:
                    continue
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cars.append(
                    {
                        "x": float((x1 + x2) * 0.5),
                        "y": float((y1 + y2) * 0.5),
                        "w": float(x2 - x1),
                        "h": float(y2 - y1),
                    }
                )

        n = float(len(cars))
        if cars:
            avg_x = float(np.mean([v["x"] for v in cars]))
            avg_y = float(np.mean([v["y"] for v in cars]))
            avg_w = float(np.mean([v["w"] for v in cars]))
            avg_h = float(np.mean([v["h"] for v in cars]))
        else:
            avg_x = avg_y = avg_w = avg_h = 0.0
        vals.extend([n, avg_x, avg_y, avg_w, avg_h])

    cap.release()
    if len(vals) < 40:
        vals.extend([0.0] * (40 - len(vals)))
    return np.array(vals[:40], dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract 413-dim features from labels jsonl.")
    parser.add_argument("--labels", required=True, help="labels jsonl path")
    parser.add_argument("--videos-root", default="backend/videos", help="videos root directory")
    parser.add_argument("--out-csv", required=True, help="output feature csv path")
    parser.add_argument("--yolo-model", default="yolov8n.pt", help="YOLO model path")
    parser.add_argument("--no-yolo", action="store_true", help="disable yolo vehicle features")
    parser.add_argument("--limit", type=int, default=0, help="optional sample limit")
    args = parser.parse_args()

    labels_path = Path(args.labels).resolve()
    videos_root = Path(args.videos_root).resolve()
    out_csv = Path(args.out_csv).resolve()
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    rows = load_jsonl(labels_path)
    if args.limit > 0:
        rows = rows[: int(args.limit)]

    yolo_model = None
    if not args.no_yolo:
        try:
            from ultralytics import YOLO

            yolo_model = YOLO(str(Path(args.yolo_model).resolve()))
        except Exception as exc:
            print(f"[WARN] YOLO unavailable, fallback to zero vehicle features: {exc}")
            yolo_model = None

    out_rows: List[Dict[str, Any]] = []
    missing = 0
    failed = 0

    for i, row in enumerate(rows, start=1):
        sample_id = safe_str(row.get("sample_id", ""))
        video_ref = safe_str(row.get("video", ""))
        if not sample_id or not video_ref:
            failed += 1
            continue
        video_path = resolve_video_path(videos_root, video_ref)
        if not video_path.exists():
            print(f"[WARN] missing video: {video_path}")
            missing += 1
            continue

        pixel = extract_pixel_features(video_path, num_frames=32)
        if pixel is None:
            failed += 1
            continue
        optical = extract_optical_features(video_path, num_frames=32)
        vehicle = extract_vehicle_features(video_path, yolo_model=yolo_model, num_frames=8)
        feat = np.concatenate([pixel, optical, vehicle], axis=0)
        if feat.size != 413:
            failed += 1
            print(f"[WARN] feature dim mismatch for {sample_id}: {feat.size}")
            continue

        out: Dict[str, Any] = {
            "sample_id": sample_id,
            "video": video_ref.replace("\\", "/"),
            "accident_type": safe_str(row.get("accident_type", "")),
        }
        for k, v in enumerate(feat.tolist()):
            out[f"feature_{k}"] = float(v)
        out_rows.append(out)
        print(f"[INFO] ({i}/{len(rows)}) done {sample_id}")

    df = pd.DataFrame(out_rows)
    df.to_csv(out_csv, index=False)
    print(
        json.dumps(
            {
                "labels": str(labels_path),
                "videos_root": str(videos_root),
                "out_csv": str(out_csv),
                "total_labels": len(rows),
                "written_rows": len(out_rows),
                "missing_video": missing,
                "failed_rows": failed,
                "feature_dim": 413,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
