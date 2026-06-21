import argparse
from pathlib import Path
from typing import List, Optional, Set

import numpy as np
from ultralytics import YOLO


def parse_classes(raw: str) -> Optional[Set[int]]:
    s = (raw or "").strip()
    if not s:
        return None
    out = set()
    for x in s.split(","):
        x = x.strip()
        if not x:
            continue
        out.add(int(x))
    return out


def run_one_video(
    model: YOLO,
    video_path: Path,
    out_txt: Path,
    tracker: str,
    imgsz: int,
    conf: float,
    iou: float,
    allowed_classes: Optional[Set[int]],
) -> None:
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    with out_txt.open("w", encoding="utf-8") as f:
        frame_idx = 0
        results = model.track(
            source=str(video_path),
            stream=True,
            persist=True,
            tracker=tracker,
            imgsz=imgsz,
            conf=conf,
            iou=iou,
            verbose=False,
        )
        for res in results:
            frame_idx += 1
            boxes = getattr(res, "boxes", None)
            if boxes is None or boxes.xyxy is None or len(boxes.xyxy) == 0:
                continue

            xyxy = boxes.xyxy.cpu().numpy()
            ids = boxes.id.cpu().numpy().astype(int) if boxes.id is not None else np.full((len(xyxy),), -1, dtype=int)
            scores = boxes.conf.cpu().numpy() if boxes.conf is not None else np.ones((len(xyxy),), dtype=float)
            clss = boxes.cls.cpu().numpy().astype(int) if boxes.cls is not None else np.full((len(xyxy),), -1, dtype=int)

            for i in range(len(xyxy)):
                tid = int(ids[i])
                if tid < 0:
                    continue
                cls = int(clss[i])
                if allowed_classes is not None and cls not in allowed_classes:
                    continue
                x1, y1, x2, y2 = [float(v) for v in xyxy[i].tolist()]
                w = max(0.0, x2 - x1)
                h = max(0.0, y2 - y1)
                score = float(scores[i])
                # MOT prediction format: frame,id,x,y,w,h,score,-1,-1,-1
                f.write(f"{frame_idx},{tid},{x1:.6f},{y1:.6f},{w:.6f},{h:.6f},{score:.6f},-1,-1,-1\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run YOLO + ByteTrack and export MOT prediction txt.")
    parser.add_argument("--video", default="", help="Single video path.")
    parser.add_argument("--videos-dir", default="", help="Batch mode: directory with videos.")
    parser.add_argument("--glob", default="*.mp4", help="Glob under --videos-dir, e.g. *.mp4")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model path/name.")
    parser.add_argument("--tracker", default="bytetrack.yaml", help="Tracker yaml, e.g. bytetrack.yaml")
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument(
        "--classes",
        default="2,3,5,7",
        help="COCO class ids to keep. Default vehicles: 2,3,5,7. Empty means keep all.",
    )
    parser.add_argument("--out-dir", required=True, help="Output directory for MOT prediction txt files.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    videos: List[Path] = []
    if args.video.strip():
        videos.append(Path(args.video).resolve())
    if args.videos_dir.strip():
        root = Path(args.videos_dir).resolve()
        videos.extend(sorted(root.glob(args.glob)))
    videos = [v for v in videos if v.exists() and v.is_file()]

    if not videos:
        raise RuntimeError("No input videos found. Provide --video or --videos-dir.")

    allowed_classes = parse_classes(args.classes)
    model = YOLO(args.model)

    for v in videos:
        out_txt = out_dir / f"{v.stem}.txt"
        print(f"[RUN] {v.name} -> {out_txt.name}")
        run_one_video(
            model=model,
            video_path=v,
            out_txt=out_txt,
            tracker=args.tracker,
            imgsz=int(args.imgsz),
            conf=float(args.conf),
            iou=float(args.iou),
            allowed_classes=allowed_classes,
        )
        print(f"[DONE] {out_txt}")


if __name__ == "__main__":
    main()

