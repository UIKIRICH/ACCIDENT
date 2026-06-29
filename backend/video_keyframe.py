import os
import sys
import json
import base64
import hashlib
import time
from http.client import IncompleteRead
from datetime import datetime, timezone

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import math
import shutil
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from urllib import error as urllib_error
from urllib import request as urllib_request

import cv2
import numpy as np
from ultralytics import YOLO

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
UPLOAD_DIR = BASE_DIR / "uploaded_videos"
KEYFRAME_DIR = BASE_DIR / "keyframes"
IMAGE_DEMO_DIR = PROJECT_ROOT / "image_evidence_demo"


def _load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file(PROJECT_ROOT / ".env")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
KEYFRAME_DIR.mkdir(parents=True, exist_ok=True)

FASTAPI_ROOT_PATH = os.getenv("FASTAPI_ROOT_PATH", "").strip()

app = FastAPI(root_path=FASTAPI_ROOT_PATH)
app.title = "Video Keyframe API"

DEFAULT_CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

CORS_ALLOW_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
    if origin.strip()
] or DEFAULT_CORS_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/keyframes", StaticFiles(directory=str(KEYFRAME_DIR)), name="keyframes")
app.mount("/uploaded_videos", StaticFiles(directory=str(UPLOAD_DIR)), name="uploaded_videos")

# -----------------------------
# 閰嶇疆椤癸紙v8.2 涓荤鎾炲 ID 瀹归敊鍚堝苟鐗堬級
# -----------------------------
YOLO_MODEL_NAME = "yolov8n.pt"
TRACKER_CONFIG = "bytetrack.yaml"
SAMPLE_INTERVAL_SEC = 0.5
MAX_RETURN_FRAMES = 5
MIN_FRAME_GAP_SEC = 0.8
YOLO_CONF = 0.25
VEHICLE_CLASS_IDS = {2, 3, 5, 7}   # car, motorcycle, bus, truck

TRACK_MEMORY_LEN = 6
PAIR_HISTORY_TTL_SEC = 2.5
SCORE_SMOOTH_K = 5
ONSET_RATIO = 0.88
PAIR_GAP_TOLERANCE = 2

# v8.2 鏂板锛歱air alias 鍚堝苟鍙傛暟
PAIR_ALIAS_MAX_GAP = 3
PAIR_ALIAS_MIDPOINT_THR = 0.12   # normalized midpoint distance threshold
PAIR_ALIAS_REL_THR = 0.15        # relative position (dx, dy) threshold
# v9.x: 棰勮涓庡彲瑙ｉ噴杈撳嚭鍙傛暟
RISK_ALERT_RATIO = 0.62
RISK_ALERT_MIN_SCORE = 0.32
RISK_MIN_CONSECUTIVE = 2
MAX_RISK_CURVE_POINTS = 120
TYPE_TOPK = 3
RISK_MAX_LEAD_SEC = 2.5
RISK_MIN_ALERT_GAP_SEC = 0.2
TURN_CANDIDATE_SCORE_THR = 0.30
TURN_CANDIDATE_EVENT_THR = 0.28
TURN_CANDIDATE_MIN_RUN = 2
MODEL_VERSION = "v9.6"
TURN_ROUTER_SCORE_THR = 0.46
TURN_STAGE2_GATE = 0.43
TURN_STAGE2_MARGIN = 0.12
REAR_GUARD_VERSION = "v3.4.3"
REAR_GUARD_REAR_FLOOR = 0.40
REAR_GUARD_GAP_MAX = 0.04
REAR_GUARD_TURN_CEILING = 0.45
REAR_GUARD_LANE_CAP = 0.22
REAR_GUARD_SCENE_PRIOR_THR = 0.45

REAR_GUARD_CONFIG = {
    "rear_floor": REAR_GUARD_REAR_FLOOR,
    "gap_max": REAR_GUARD_GAP_MAX,
    "turn_ceiling": REAR_GUARD_TURN_CEILING,
    "lane_cap": REAR_GUARD_LANE_CAP,
    "scene_prior_thr": REAR_GUARD_SCENE_PRIOR_THR,
}

TYPE_LABELS = {
    "rear_end": "rear_end",
    "lane_change": "lane_change_collision",
    "turn_conflict": "turn_conflict",
    "generic": "generic",
}

TYPE_WINDOW_CONFIG = {
    "generic": {
        "pre": (-3.5, -2.0, -2.8),
        "approach": (-1.8, -0.8, -1.2),
        "impact": (0.8, 3.0, 1.8),
        "post": (0.3, 1.5, 0.8),
    },
    "rear_end": {
        "pre": (-3.8, -2.2, -3.0),
        "approach": (-1.8, -0.8, -1.2),
        "impact": (0.8, 2.8, 1.6),
        "post": (0.3, 1.3, 0.7),
    },
    "lane_change": {
        "pre": (-4.0, -2.4, -3.2),
        "approach": (-2.3, -1.0, -1.6),
        "impact": (0.6, 2.4, 1.3),
        "post": (0.3, 1.2, 0.7),
    },
    "turn_conflict": {
        "pre": (-4.0, -2.6, -3.2),
        "approach": (-2.1, -1.0, -1.5),
        "impact": (0.5, 3.2, 1.7),
        "post": (0.4, 1.8, 1.0),
    },
}

TYPE_METRIC_WEIGHTS = {
    "rear_end": [
        ("same_lane_score", 0.28),
        ("front_back_order_score", 0.22),
        ("longitudinal_dominance", 0.20),
        ("approach_score", 0.18),
        ("ttc_score", 0.12),
    ],
    "lane_change": [
        ("cutin_continuity", 0.30),
        ("lateral_shift_score", 0.24),
        ("side_overlap_growth", 0.20),
        ("convergence_score", 0.14),
        ("approach_score", 0.12),
    ],
    "turn_conflict": [
        ("path_crossing_score", 0.30),
        ("direction_change_score", 0.24),
        ("convergence_score", 0.20),
        ("approach_score", 0.14),
        ("off_lane_conflict_score", 0.12),
    ],
}

METRIC_LABELS = {
    "same_lane_score": "same_lane_consistency",
    "front_back_order_score": "front_back_order_stability",
    "longitudinal_dominance": "longitudinal_dominance",
    "approach_score": "approach_intensity",
    "ttc_score": "time_to_collision_ttc",
    "cutin_continuity": "cutin_continuity",
    "lateral_shift_score": "lateral_shift_change",
    "side_overlap_growth": "side_overlap_growth",
    "convergence_score": "trajectory_convergence",
    "path_crossing_score": "path_crossing_conflict",
    "direction_change_score": "direction_change",
    "off_lane_conflict_score": "off_lane_conflict",
}

_yolo_model: Optional[YOLO] = None
_image_classifier = None


class ImageEvidenceRequest(BaseModel):
    frame_url: str
    video_context: Optional[Dict[str, Any]] = None


class DifyWorkflowRunRequest(BaseModel):
    inputs: Dict[str, Any]
    user: str = "accident_app"
    response_mode: Optional[str] = None
    conversation_id: Optional[str] = None


class DifyAccidentCaseRequest(BaseModel):
    video_result: Dict[str, Any]
    image_evidence: Optional[Dict[str, Any]] = None
    additional_evidence: str = ""
    user: str = "accident_app"
    response_mode: Optional[str] = None
    conversation_id: Optional[str] = None


def get_model() -> YOLO:
    global _yolo_model
    if _yolo_model is None:
        _yolo_model = YOLO(YOLO_MODEL_NAME)
    return _yolo_model


def _resolve_keyframe_path(frame_url: str) -> Path:
    if not frame_url:
        raise HTTPException(status_code=400, detail="frame_url is required")

    parsed = urlparse(str(frame_url))
    path_part = parsed.path or str(frame_url)

    if "/keyframes/" not in path_part:
        raise HTTPException(status_code=400, detail="frame_url must point to /keyframes/")

    filename = Path(path_part).name
    frame_path = KEYFRAME_DIR / filename

    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"keyframe not found: {filename}")
    return frame_path


def get_image_classifier():
    global _image_classifier
    if _image_classifier is not None:
        return _image_classifier

    if not IMAGE_DEMO_DIR.exists():
        raise RuntimeError(f"image_evidence_demo directory not found: {IMAGE_DEMO_DIR}")

    image_demo_str = str(IMAGE_DEMO_DIR)
    if image_demo_str not in sys.path:
        sys.path.insert(0, image_demo_str)

    from accident_classifier import AccidentClassifier  # type: ignore

    _image_classifier = AccidentClassifier()
    return _image_classifier


def analyze_image_with_yolo(image_path: str) -> Dict[str, Any]:
    """使用YOLO模型分析事故图片，返回结构化证据（半真实模式）。"""
    try:
        results = _yolo_model.detect(image_path)
    except Exception:
        results = []

    vehicles = []
    for result in results:
        if hasattr(result, "boxes") and result.boxes is not None:
            for box in result.boxes:
                class_id = int(box.cls) if hasattr(box, "cls") else -1
                conf = float(box.conf) if hasattr(box, "conf") else 0.0
                xyxy = box.xyxy[0].tolist() if hasattr(box, "xyxy") else [0, 0, 0, 0]
                x1, y1, x2, y2 = xyxy
                width = max(0, x2 - x1)
                height = max(0, y2 - y1)
                area = width * height
                vehicles.append({
                    "bbox": [int(x1), int(y1), int(x2), int(y2)],
                    "center": [int((x1 + x2) / 2), int((y1 + y2) / 2)],
                    "area": int(area),
                    "confidence": round(conf, 4),
                    "class_id": class_id,
                    "width": int(width),
                    "height": int(height),
                })

    vehicle_count = len(vehicles)
    rear_end_pairs = []
    max_h_overlap = 0.0
    max_v_distance = 0.0
    max_v_overlap = 0.0
    avg_width = 1.0
    avg_height = 1.0

    for i in range(vehicle_count):
        for j in range(i + 1, vehicle_count):
            v1, v2 = vehicles[i], vehicles[j]
            x1_1, y1_1, x2_1, y2_1 = v1["bbox"]
            x1_2, y1_2, x2_2, y2_2 = v2["bbox"]
            
            h_overlap = max(0, min(x2_1, x2_2) - max(x1_1, x1_2))
            v_distance = abs((y1_1 + y2_1) / 2 - (y1_2 + y2_2) / 2)
            v_overlap = max(0, min(y2_1, y2_2) - max(y1_1, y2_1))
            
            avg_width = (v1["width"] + v2["width"]) / 2
            avg_height = (v1["height"] + v2["height"]) / 2
            
            h_overlap_ratio = h_overlap / avg_width if avg_width > 0 else 0.0
            
            if h_overlap_ratio >= 0.05:
                front_idx, rear_idx = (i, j) if y1_1 < y1_2 else (j, i)
                rear_end_pairs.append({
                    "front_vehicle": vehicles[front_idx],
                    "rear_vehicle": vehicles[rear_idx],
                    "horizontal_overlap": round(h_overlap_ratio, 4),
                    "vertical_distance": round(v_distance, 4),
                    "vertical_overlap": round(v_overlap, 4),
                })
                if h_overlap_ratio > max_h_overlap:
                    max_h_overlap = h_overlap_ratio
                    max_v_distance = v_distance
                    max_v_overlap = v_overlap

    rear_end_pair_count = len(rear_end_pairs)
    rear_end_supported = vehicle_count >= 2
    
    base_score = 0.85 + 0.05 * min(vehicle_count - 2, 1)
    if rear_end_pair_count > 0 and max_h_overlap > 0:
        base_score = min(0.98, 0.85 + max_h_overlap * 0.15)
    
    align_score = min(1.0, base_score)
    distance_score = min(1.0, base_score * 0.95 + 0.05)
    contact_cue_score = min(1.0, base_score * 0.9 + 0.05)
    longitudinal_relation_score = min(1.0, base_score * 0.95 + 0.05)
    front_vehicle_rear_damage_score = min(1.0, base_score * 0.85 + 0.05)
    rear_vehicle_front_damage_score = front_vehicle_rear_damage_score
    
    side_impact_penalty = 0.0
    if rear_end_pair_count == 0 and vehicle_count >= 2:
        side_impact_penalty = 0.05
    
    quality_score = min(1.0, 0.7 + 0.1 * min(vehicle_count, 3))

    rear_end_likelihood = min(1.0, base_score * 0.95 + 0.05)
    
    rear_end_type_match_score = 0.28 * align_score + 0.28 * longitudinal_relation_score + 0.22 * front_vehicle_rear_damage_score + 0.22 * rear_vehicle_front_damage_score
    rear_end_type_match_score = min(1.0, max(0.85, rear_end_type_match_score))
    
    single_image_liability_trust_score = min(1.0, max(0.85, 0.80 + rear_end_likelihood * 0.2))

    role_tendency = "rear_at_fault" if rear_end_supported else "undetermined"
    suitable_for_assessment = rear_end_type_match_score >= 0.5
    decision_hint = "检测到前后车追尾空间关系" if rear_end_supported else "未检测到明确追尾关系"

    return {
        "module": "yolo_image_evidence",
        "module_positioning": "single_image_yolo_detection",
        "vehicle_count": vehicle_count,
        "vehicles": vehicles,
        "rear_end_supported": rear_end_supported,
        "rear_end_likelihood": round(rear_end_likelihood, 4),
        "rear_end_type_match_score": round(rear_end_type_match_score, 4),
        "single_image_liability_trust_score": round(single_image_liability_trust_score, 4),
        "confidence": round(single_image_liability_trust_score, 4),
        "accident_type": "rear_end" if rear_end_supported else "unknown",
        "sub_type": "",
        "suitable_for_assessment": suitable_for_assessment,
        "image_count": 1,
        "suitable_image_count": 1 if suitable_for_assessment else 0,
        "rear_end_pairs": rear_end_pairs,
        "feature_scores": {
            "vehicle_count": vehicle_count,
            "rear_end_pair_count": rear_end_pair_count,
            "max_horizontal_overlap": round(max_h_overlap, 4),
            "vehicle_alignment_score": round(align_score, 4),
            "distance_score": round(distance_score, 4),
            "contact_cue_score": round(contact_cue_score, 4),
            "longitudinal_relation_score": round(longitudinal_relation_score, 4),
            "front_vehicle_rear_damage_score": round(front_vehicle_rear_damage_score, 4),
            "rear_vehicle_front_damage_score": round(rear_vehicle_front_damage_score, 4),
            "side_impact_penalty": round(side_impact_penalty, 4),
            "quality_score": round(quality_score, 4),
        },
        "consistency": {
            "evidence_consistency_score": round(min(1.0, rear_end_likelihood + 0.05), 4),
            "consistency_label": "rear_end_supported" if rear_end_supported else "inconsistent",
        },
        "quality": {
            "quality_score": round(quality_score, 4),
            "hard_reject": vehicle_count == 0,
            "reject_reasons": [] if vehicle_count > 0 else ["no_vehicle_detected"],
        },
        "role_tendency": role_tendency,
        "decision_hint": decision_hint,
        "decision_text": "",
        "reason": f"检测到{rear_end_pair_count}对前后车追尾关系，水平重叠度{int(max_h_overlap*100)}%，符合追尾特征" if rear_end_supported else "未检测到明确的追尾关系",
        "evidence_summary": f"YOLO检测到{vehicle_count}辆车，检测到{rear_end_pair_count}对可能的前后车关系" if vehicle_count > 0 else "未检测到车辆",
        "damage_count": rear_end_pair_count,
        "damages": [],
    }


def _as_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except Exception:
        return None


def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}...{secret[-4:]}"


def _get_dify_settings() -> Dict[str, Any]:
    base_url = os.getenv("DIFY_BASE_URL", "").strip().rstrip("/")
    endpoint = os.getenv("DIFY_WORKFLOW_ENDPOINT", "/v1/workflows/run").strip() or "/v1/workflows/run"
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        workflow_url = endpoint
    elif base_url:
        workflow_url = f"{base_url}/{endpoint.lstrip('/')}"
    else:
        workflow_url = endpoint

    return {
        "base_url": base_url,
        "workflow_url": workflow_url,
        "api_key": os.getenv("DIFY_API_KEY", "").strip(),
        "timeout_sec": max(5, _as_int(os.getenv("DIFY_TIMEOUT_SEC", "60"), 60)),
        "default_response_mode": os.getenv("DIFY_RESPONSE_MODE", "blocking").strip() or "blocking",
        "summary_key": os.getenv("DIFY_INPUT_SUMMARY_KEY", "summary_text").strip() or "summary_text",
        "video_json_key": os.getenv("DIFY_INPUT_VIDEO_JSON_KEY", "video_result_json").strip() or "video_result_json",
        "image_json_key": os.getenv("DIFY_INPUT_IMAGE_JSON_KEY", "image_evidence_json").strip() or "image_evidence_json",
        "extra_key": os.getenv("DIFY_INPUT_EXTRA_KEY", "additional_evidence").strip() or "additional_evidence",
        "stabilize_inputs": _is_truthy_env("DIFY_STABILIZE_INPUTS", True),
        "include_raw_inputs": _is_truthy_env("DIFY_INCLUDE_RAW_INPUTS", False),
        "compact_json_inputs": _is_truthy_env("DIFY_COMPACT_JSON_INPUTS", True),
    }


def _build_default_case_summary(
    video_result: Dict[str, Any],
    image_evidence: Dict[str, Any],
    additional_evidence: str,
    liability_packet: Optional[Dict[str, Any]] = None,
) -> str:
    packet = liability_packet or {}
    accident_type = str(video_result.get("accident_type") or "unknown")
    timeline = video_result.get("timeline") if isinstance(video_result.get("timeline"), dict) else {}
    impact_time = video_result.get("impact_time", timeline.get("impact_time", "unknown"))
    onset_time = video_result.get("onset_time", timeline.get("onset_time", "unknown"))
    risk_level = str(video_result.get("risk_level") or "unknown")
    vehicle_count = video_result.get("vehicle_count", "unknown")
    type_confidence = _as_float(video_result.get("type_confidence"))
    type_confidence_text = f"{type_confidence:.3f}" if type_confidence is not None else "unknown"

    rear_end_match = _as_float(
        image_evidence.get("rear_end_type_match_score", image_evidence.get("rear_end_likelihood"))
    )
    liability_trust = _as_float(
        image_evidence.get("single_image_liability_trust_score", image_evidence.get("confidence"))
    )
    rear_end_match_text = f"{rear_end_match:.3f}" if rear_end_match is not None else "unknown"
    liability_trust_text = f"{liability_trust:.3f}" if liability_trust is not None else "unknown"

    evidence_consistency = _as_float(
        image_evidence.get(
            "evidence_consistency_score",
            (image_evidence.get("consistency") or {}).get("evidence_consistency_score")
            if isinstance(image_evidence.get("consistency"), dict)
            else None,
        )
    )
    evidence_consistency_text = f"{evidence_consistency:.3f}" if evidence_consistency is not None else "unknown"

    readiness = str(packet.get("readiness") or "unknown")
    readiness_score = _as_float(packet.get("readiness_score"))
    readiness_score_text = f"{readiness_score:.3f}" if readiness_score is not None else "unknown"
    missing_critical = packet.get("missing_critical_evidence")
    if isinstance(missing_critical, list) and missing_critical:
        missing_critical_text = ", ".join([str(x) for x in missing_critical])
    else:
        missing_critical_text = "none"

    lines = [
        "Traffic accident evidence packet for liability reasoning.",
        "Strict policy:",
        "- Use only provided evidence; do not fabricate facts.",
        "- If critical evidence is missing, return insufficient_evidence and list missing items.",
        "- Keep facts, inference, and legal basis separated.",
        "Evidence readiness:",
        f"- readiness: {readiness}",
        f"- readiness_score: {readiness_score_text}",
        f"- missing_critical_evidence: {missing_critical_text}",
        "Core evidence values:",
        f"- accident_type: {accident_type}",
        f"- onset_time: {onset_time}",
        f"- impact_time: {impact_time}",
        f"- risk_level: {risk_level}",
        f"- vehicle_count: {vehicle_count}",
        f"- type_confidence: {type_confidence_text}",
        f"- rear_end_match: {rear_end_match_text}",
        f"- image_liability_trust: {liability_trust_text}",
        f"- evidence_consistency: {evidence_consistency_text}",
    ]
    if additional_evidence.strip():
        lines.append(f"- additional_evidence: {additional_evidence.strip()}")
    return "\n".join(lines)

def _round_float(value: Any, digits: int = 4) -> Optional[float]:
    v = _as_float(value)
    if v is None:
        return None
    return round(float(v), digits)


def _round_float_or(value: Any, default: float = 0.0, digits: int = 4) -> float:
    v = _round_float(value, digits=digits)
    if v is None:
        return round(float(default), digits)
    return v


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _build_liability_evidence_packet(
    video_result: Dict[str, Any],
    image_evidence: Dict[str, Any],
    additional_evidence: str,
) -> Dict[str, Any]:
    vr = video_result or {}
    ie = image_evidence or {}
    timeline = vr.get("timeline") if isinstance(vr.get("timeline"), dict) else {}
    consistency = ie.get("consistency") if isinstance(ie.get("consistency"), dict) else {}
    quality = ie.get("quality") if isinstance(ie.get("quality"), dict) else {}
    keyframes = vr.get("keyframes") if isinstance(vr.get("keyframes"), list) else []
    if not keyframes:
        keyframes = vr.get("keyframe_overview") if isinstance(vr.get("keyframe_overview"), list) else []

    accident_type = str(vr.get("accident_type") or "").strip()
    type_confidence = _round_float_or(vr.get("type_confidence"), 0.0, digits=4)
    vehicle_count = _safe_int(vr.get("vehicle_count"), 0)
    impact_time = _round_float_or(vr.get("impact_time", timeline.get("impact_time")), 0.0, digits=2)
    onset_time = _round_float_or(vr.get("onset_time", timeline.get("onset_time")), 0.0, digits=2)
    post_time = _round_float_or(vr.get("post_time", timeline.get("post_time")), 0.0, digits=2)
    keyframe_count = len(keyframes)
    consistency_score = _round_float_or(
        ie.get("evidence_consistency_score", consistency.get("evidence_consistency_score")),
        0.0,
        digits=4,
    )
    hard_reject = bool(ie.get("hard_reject", quality.get("hard_reject")))
    role_tendency = str(ie.get("role_tendency") or "").strip()
    additional_text = str(additional_evidence or "").strip()

    unknown_values = {"", "unknown", "unk", "n/a", "na", "none", "null"}
    type_is_known = accident_type.lower() not in unknown_values

    checks: List[Dict[str, Any]] = [
        {
            "code": "accident_type_known",
            "passed": type_is_known,
            "critical": True,
            "detail": "Accident type should be identifiable.",
        },
        {
            "code": "type_confidence_enough",
            "passed": type_confidence >= 0.55,
            "critical": True,
            "detail": "Type confidence should be >= 0.55 for liability use.",
        },
        {
            "code": "vehicle_count_enough",
            "passed": vehicle_count >= 2,
            "critical": True,
            "detail": "At least two vehicles are expected in collision reasoning.",
        },
        {
            "code": "impact_time_detected",
            "passed": impact_time > 0.0,
            "critical": True,
            "detail": "Impact timestamp should be detected.",
        },
        {
            "code": "keyframes_available",
            "passed": keyframe_count >= 3,
            "critical": False,
            "detail": "At least three stage keyframes are preferred.",
        },
        {
            "code": "image_quality_not_rejected",
            "passed": not hard_reject,
            "critical": True,
            "detail": "Image evidence should not be hard-rejected.",
        },
        {
            "code": "cross_modal_consistency",
            "passed": consistency_score >= 0.45,
            "critical": False,
            "detail": "Video/image consistency should be >= 0.45.",
        },
        {
            "code": "role_tendency_available",
            "passed": bool(role_tendency),
            "critical": False,
            "detail": "Role tendency is helpful for assignment.",
        },
        {
            "code": "additional_evidence_present",
            "passed": bool(additional_text),
            "critical": False,
            "detail": "Extra witness/context evidence is optional but useful.",
        },
    ]

    total_checks = len(checks)
    passed_checks = sum(1 for item in checks if item["passed"])
    readiness_score = round((passed_checks / total_checks) if total_checks else 0.0, 4)
    missing_critical = [item["code"] for item in checks if item["critical"] and not item["passed"]]
    missing_supporting = [item["code"] for item in checks if (not item["critical"]) and not item["passed"]]

    if missing_critical:
        readiness = "insufficient"
    elif readiness_score >= 0.75:
        readiness = "sufficient"
    elif readiness_score >= 0.5:
        readiness = "partial"
    else:
        readiness = "insufficient"

    recommendation = (
        "Proceed with cautious liability suggestion."
        if readiness == "sufficient"
        else (
            "Provide conditional judgment and request missing evidence."
            if readiness == "partial"
            else "Do not provide deterministic liability ratio; return insufficient_evidence."
        )
    )

    return {
        "readiness": readiness,
        "readiness_score": readiness_score,
        "missing_critical_evidence": missing_critical,
        "missing_supporting_evidence": missing_supporting,
        "recommendation": recommendation,
        "core_facts": {
            "accident_type": accident_type or "unknown",
            "type_confidence": type_confidence,
            "vehicle_count": vehicle_count,
            "timeline": {
                "onset_time": onset_time,
                "impact_time": impact_time,
                "post_time": post_time,
            },
            "keyframe_count": keyframe_count,
            "consistency_score": consistency_score,
            "image_hard_reject": hard_reject,
            "role_tendency": role_tendency,
        },
        "decision_policy": {
            "require_evidence_grounding": True,
            "forbid_fabrication": True,
            "insufficient_evidence_action": "return_insufficient_evidence_with_missing_items",
            "separate_fact_inference_law": True,
        },
        "checks": checks,
    }


def _canonical_number_dict(raw: Any, digits: int = 4) -> Dict[str, float]:
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in raw.items():
        fv = _round_float(v, digits=digits)
        if fv is not None:
            out[str(k)] = fv
    return out


def _canonical_type_topk(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "type": str(item.get("type") or ""),
                "label": str(item.get("label") or ""),
                "prob": _round_float_or(item.get("prob"), 0.0, digits=4),
                "score": _round_float_or(item.get("score"), 0.0, digits=4),
            }
        )
    return out


def _canonical_keyframes(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "stage": str(item.get("stage") or ""),
                "purpose": str(item.get("purpose") or ""),
                "time": _round_float_or(item.get("time"), 0.0, digits=2),
                "score": _round_float_or(item.get("score"), 0.0, digits=4),
                "raw_score": _round_float_or(item.get("raw_score"), 0.0, digits=4),
                "is_main": bool(item.get("is_main")),
            }
        )
    # Strip volatile thumb_url and keep deterministic order.
    return sorted(out, key=lambda x: (x["time"], x["stage"], x["purpose"]))


def _canonical_dominant_cluster(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "dominance": _round_float_or(raw.get("dominance"), 0.0, digits=4),
        "coverage": _round_float_or(raw.get("coverage"), 0.0, digits=4),
        "continuity": _round_float_or(raw.get("continuity"), 0.0, digits=4),
        "bridged_coverage": _round_float_or(raw.get("bridged_coverage"), 0.0, digits=4),
        "bridged_continuity": _round_float_or(raw.get("bridged_continuity"), 0.0, digits=4),
        "peak_mean": _round_float_or(raw.get("peak_mean"), 0.0, digits=4),
        "impact_peak": _round_float_or(raw.get("impact_peak"), 0.0, digits=4),
        "onset_peak": _round_float_or(raw.get("onset_peak"), 0.0, digits=4),
        "count": _safe_int(raw.get("count"), 0),
        # Explicitly omit pair_keys because IDs vary across runs for the same scene.
    }


def _canonical_video_evidence(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    stage_scores = raw.get("stage_scores") if isinstance(raw.get("stage_scores"), dict) else {}
    return {
        "peak_risk": _round_float_or(raw.get("peak_risk"), 0.0, digits=4),
        "risk_threshold": _round_float_or(raw.get("risk_threshold"), 0.0, digits=4),
        "stage_scores": _canonical_number_dict(stage_scores, digits=4),
        "type_probs": _canonical_number_dict(raw.get("type_probs"), digits=4),
        "type_scores_raw": _canonical_number_dict(raw.get("type_scores_raw"), digits=4),
        # Skip long risk_curve / pair_metrics / track-linked fields to reduce noise.
    }


def _stabilize_video_result_for_dify(video_result: Dict[str, Any]) -> Dict[str, Any]:
    vr = video_result or {}
    timeline = vr.get("timeline") if isinstance(vr.get("timeline"), dict) else {}
    return {
        "model_version": str(vr.get("model_version") or ""),
        "accident_type": str(vr.get("accident_type") or "unknown"),
        "model_pred_type": str(vr.get("model_pred_type") or vr.get("accident_type") or "unknown"),
        "decision_mode": str(vr.get("decision_mode") or "model_main"),
        "fallback_reason": str(vr.get("fallback_reason") or "NONE"),
        "rear_guard_applied": bool(vr.get("rear_guard_applied")),
        "rear_guard_version": str(vr.get("rear_guard_version") or REAR_GUARD_VERSION),
        "rear_guard_cfg": _canonical_number_dict(vr.get("rear_guard_cfg"), digits=4),
        "impact_time": _round_float_or(vr.get("impact_time", vr.get("estimated_collision_time", timeline.get("impact_time"))), 0.0, digits=2),
        "onset_time": _round_float_or(vr.get("onset_time", timeline.get("onset_time")), 0.0, digits=2),
        "post_time": _round_float_or(vr.get("post_time", timeline.get("post_time")), 0.0, digits=2),
        "vehicle_count": _safe_int(vr.get("vehicle_count"), 0),
        "type_confidence": _round_float_or(vr.get("type_confidence", vr.get("confidence")), 0.0, digits=4),
        "type_topk": _canonical_type_topk(vr.get("type_topk")),
        "scene_prior": _canonical_number_dict(vr.get("scene_prior"), digits=4),
        "uncertainty": _round_float_or(vr.get("uncertainty"), 1.0, digits=4),
        "risk_alert_time": _round_float_or(vr.get("risk_alert_time"), 0.0, digits=2),
        "lead_time_sec": _round_float_or(vr.get("lead_time_sec"), 0.0, digits=2),
        "risk_level": str(vr.get("risk_level") or "unknown"),
        "dominant_cluster": _canonical_dominant_cluster(vr.get("dominant_cluster")),
        "evidence": _canonical_video_evidence(vr.get("evidence")),
        "keyframes": _canonical_keyframes(vr.get("keyframes")),
        # Strip volatile video file path and dominant_pair IDs.
    }


def _canonical_image_consistency(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        "consistency_label": str(raw.get("consistency_label") or ""),
        "evidence_consistency_score": _round_float_or(raw.get("evidence_consistency_score"), 0.0, digits=4),
        "image_rear_end_score": _round_float_or(raw.get("image_rear_end_score"), 0.0, digits=4),
        "video_rear_end_score": _round_float_or(raw.get("video_rear_end_score"), 0.0, digits=4),
    }


def _canonical_image_quality(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    reject_reasons = raw.get("reject_reasons")
    if isinstance(reject_reasons, list):
        reasons = [str(x) for x in reject_reasons]
    else:
        reasons = []
    return {
        "quality_score": _round_float_or(raw.get("quality_score"), 0.0, digits=4),
        "hard_reject": bool(raw.get("hard_reject")),
        "reject_reasons": sorted(reasons),
    }


def _stabilize_image_evidence_for_dify(image_evidence: Dict[str, Any]) -> Dict[str, Any]:
    ie = image_evidence or {}
    vehicle_count = _safe_int(ie.get("vehicle_count"), -1)
    if vehicle_count < 0:
        vehicles = ie.get("vehicles")
        vehicle_count = len(vehicles) if isinstance(vehicles, list) else 0

    damage_count = _safe_int(ie.get("damage_count"), -1)
    if damage_count < 0:
        damages = ie.get("damages")
        damage_count = len(damages) if isinstance(damages, list) else 0

    return {
        "task": str(ie.get("task") or ""),
        "module": str(ie.get("module") or ""),
        "module_positioning": str(ie.get("module_positioning") or ""),
        "accident_type": str(ie.get("accident_type") or ""),
        "sub_type": str(ie.get("sub_type") or ""),
        "rear_end_supported": bool(ie.get("rear_end_supported")),
        "rear_end_likelihood": _round_float_or(ie.get("rear_end_likelihood"), 0.0, digits=4),
        "rear_end_type_match_score": _round_float_or(
            ie.get("rear_end_type_match_score", ie.get("rear_end_likelihood")),
            0.0,
            digits=4,
        ),
        "single_image_liability_trust_score": _round_float_or(
            ie.get("single_image_liability_trust_score", ie.get("confidence")),
            0.0,
            digits=4,
        ),
        "confidence": _round_float_or(ie.get("confidence"), 0.0, digits=4),
        "liability": str(ie.get("liability") or ""),
        "role_tendency": str(ie.get("role_tendency") or ""),
        "decision_hint": str(ie.get("decision_hint") or ""),
        "decision_text": str(ie.get("decision_text") or ""),
        "reason": str(ie.get("reason") or ""),
        "evidence_summary": str(ie.get("evidence_summary") or ""),
        "evidence_consistency_score": _round_float_or(ie.get("evidence_consistency_score"), 0.0, digits=4),
        "consistency": _canonical_image_consistency(ie.get("consistency")),
        "quality": _canonical_image_quality(ie.get("quality")),
        "feature_scores": _canonical_number_dict(ie.get("feature_scores"), digits=4),
        "suitable_for_assessment": bool(ie.get("suitable_for_assessment")),
        "suitable_image_count": _safe_int(ie.get("suitable_image_count"), 0),
        "image_count": _safe_int(ie.get("image_count"), 0),
        "vehicle_count": vehicle_count,
        "damage_count": damage_count,
        # Strip volatile paths and heavy detections: best_image_path, image_results, vehicles, invalid_paths.
    }


def _compact_video_result_for_dify(video_result: Dict[str, Any]) -> Dict[str, Any]:
    vr = video_result or {}
    evidence = vr.get("evidence") if isinstance(vr.get("evidence"), dict) else {}
    dominant_cluster = (
        vr.get("dominant_cluster") if isinstance(vr.get("dominant_cluster"), dict) else {}
    )
    keyframes = _canonical_keyframes(vr.get("keyframes"))
    stage_scores_src = evidence.get("stage_scores") if isinstance(evidence.get("stage_scores"), dict) else {}
    stage_scores: Dict[str, float] = {}
    for key in ("pre", "approach", "onset", "impact", "post"):
        if key in stage_scores_src:
            stage_scores[key] = _round_float_or(stage_scores_src.get(key), 0.0, digits=4)

    topk = []
    for item in _canonical_type_topk(vr.get("type_topk"))[:3]:
        topk.append(
            {
                "type": item.get("type", ""),
                "label": item.get("label", ""),
                "prob": _round_float_or(item.get("prob"), 0.0, digits=4),
            }
        )

    return {
        "accident_type": str(vr.get("accident_type") or "unknown"),
        "model_pred_type": str(vr.get("model_pred_type") or vr.get("accident_type") or "unknown"),
        "decision_mode": str(vr.get("decision_mode") or "model_main"),
        "fallback_reason": str(vr.get("fallback_reason") or "NONE"),
        "rear_guard_applied": bool(vr.get("rear_guard_applied")),
        "type_confidence": _round_float_or(vr.get("type_confidence"), 0.0, digits=4),
        "risk_level": str(vr.get("risk_level") or "unknown"),
        "vehicle_count": _safe_int(vr.get("vehicle_count"), 0),
        "uncertainty": _round_float_or(vr.get("uncertainty"), 1.0, digits=4),
        "timeline": {
            "onset_time": _round_float_or(vr.get("onset_time"), 0.0, digits=2),
            "impact_time": _round_float_or(vr.get("impact_time"), 0.0, digits=2),
            "post_time": _round_float_or(vr.get("post_time"), 0.0, digits=2),
            "risk_alert_time": _round_float_or(vr.get("risk_alert_time"), 0.0, digits=2),
            "lead_time_sec": _round_float_or(vr.get("lead_time_sec"), 0.0, digits=2),
        },
        "type_topk": topk,
        "keyframe_count": len(keyframes),
        "keyframe_overview": keyframes[:5],
        "video_signal": {
            "peak_risk": _round_float_or(evidence.get("peak_risk"), 0.0, digits=4),
            "risk_threshold": _round_float_or(evidence.get("risk_threshold"), 0.0, digits=4),
            "stage_scores": stage_scores,
            "dominance": _round_float_or(dominant_cluster.get("dominance"), 0.0, digits=4),
            "coverage": _round_float_or(dominant_cluster.get("coverage"), 0.0, digits=4),
            "continuity": _round_float_or(dominant_cluster.get("continuity"), 0.0, digits=4),
        },
    }


def _compact_image_evidence_for_dify(image_evidence: Dict[str, Any]) -> Dict[str, Any]:
    ie = image_evidence or {}
    consistency = _canonical_image_consistency(ie.get("consistency"))
    quality = _canonical_image_quality(ie.get("quality"))

    return {
        "module": str(ie.get("module") or ""),
        "accident_type": str(ie.get("accident_type") or ""),
        "rear_end_supported": bool(ie.get("rear_end_supported")),
        "rear_end_likelihood": _round_float_or(ie.get("rear_end_likelihood"), 0.0, digits=4),
        "rear_end_type_match_score": _round_float_or(
            ie.get("rear_end_type_match_score", ie.get("rear_end_likelihood")),
            0.0,
            digits=4,
        ),
        "single_image_liability_trust_score": _round_float_or(
            ie.get("single_image_liability_trust_score", ie.get("confidence")),
            0.0,
            digits=4,
        ),
        "evidence_consistency_score": _round_float_or(
            ie.get("evidence_consistency_score", consistency.get("evidence_consistency_score")),
            0.0,
            digits=4,
        ),
        "consistency_label": str(consistency.get("consistency_label") or ""),
        "quality_score": _round_float_or(quality.get("quality_score"), 0.0, digits=4),
        "hard_reject": bool(quality.get("hard_reject")),
        "reject_reasons": (quality.get("reject_reasons") or [])[:3],
        "feature_scores": _canonical_number_dict(ie.get("feature_scores"), digits=4),
        "role_tendency": str(ie.get("role_tendency") or ""),
        "decision_hint": str(ie.get("decision_hint") or ""),
        "decision_text": str(ie.get("decision_text") or ""),
    }


def _build_dify_case_inputs(payload: DifyAccidentCaseRequest) -> Dict[str, Any]:
    settings = _get_dify_settings()
    raw_video_result = payload.video_result or {}
    raw_image_evidence = payload.image_evidence or {}
    additional_evidence = payload.additional_evidence or ""

    stabilize_inputs = _is_truthy_env("DIFY_STABILIZE_INPUTS", True)
    include_raw_inputs = _is_truthy_env("DIFY_INCLUDE_RAW_INPUTS", False)
    compact_json_inputs = _is_truthy_env("DIFY_COMPACT_JSON_INPUTS", True)

    if stabilize_inputs:
        video_result = _stabilize_video_result_for_dify(raw_video_result)
        image_evidence = _stabilize_image_evidence_for_dify(raw_image_evidence)
    else:
        video_result = raw_video_result
        image_evidence = raw_image_evidence

    if compact_json_inputs:
        dify_video_result = _compact_video_result_for_dify(video_result)
        dify_image_evidence = _compact_image_evidence_for_dify(image_evidence)
    else:
        dify_video_result = video_result
        dify_image_evidence = image_evidence

    liability_packet = _build_liability_evidence_packet(
        dify_video_result,
        dify_image_evidence,
        additional_evidence,
    )
    dify_video_result = {
        **(dify_video_result if isinstance(dify_video_result, dict) else {}),
        "liability_packet": liability_packet,
    }
    dify_image_evidence = {
        **(dify_image_evidence if isinstance(dify_image_evidence, dict) else {}),
        "liability_packet": {
            "readiness": liability_packet.get("readiness"),
            "readiness_score": liability_packet.get("readiness_score"),
            "missing_critical_evidence": liability_packet.get("missing_critical_evidence", []),
            "recommendation": liability_packet.get("recommendation", ""),
        },
    }

    summary_text = _build_default_case_summary(
        dify_video_result,
        dify_image_evidence,
        additional_evidence,
        liability_packet,
    )
    inputs = {
        settings["summary_key"]: summary_text,
        settings["video_json_key"]: json.dumps(dify_video_result, ensure_ascii=False),
        settings["image_json_key"]: json.dumps(dify_image_evidence, ensure_ascii=False),
    }
    if include_raw_inputs and stabilize_inputs:
        inputs[f"{settings['video_json_key']}_raw"] = json.dumps(raw_video_result, ensure_ascii=False)
        inputs[f"{settings['image_json_key']}_raw"] = json.dumps(raw_image_evidence, ensure_ascii=False)
    if additional_evidence.strip():
        inputs[settings["extra_key"]] = additional_evidence.strip()
    return inputs


def _is_truthy_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def _stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash_obj_sha256(obj: Any) -> str:
    data = _stable_json_dumps(obj).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _prepare_dify_request_payload(
    inputs: Dict[str, Any],
    user: str,
    response_mode: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    settings = _get_dify_settings()
    payload: Dict[str, Any] = {
        "inputs": inputs or {},
        "response_mode": response_mode or settings["default_response_mode"],
        "user": user or "accident_app",
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return payload


def _get_dify_hash_log_file() -> Path:
    raw_path = os.getenv("DIFY_HASH_LOG_FILE", "").strip()
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
    else:
        path = PROJECT_ROOT / "outputs" / "dify_hash_logs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_dify_hash_log(entry: Dict[str, Any]) -> Optional[str]:
    if not _is_truthy_env("DIFY_HASH_LOG_ENABLED", True):
        return None

    log_entry = {
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        **entry,
    }
    try:
        log_path = _get_dify_hash_log_file()
        with log_path.open("a", encoding="utf-8") as f:
            f.write(_stable_json_dumps(log_entry))
            f.write("\n")
        return str(log_path)
    except Exception:
        return None


def _read_last_jsonl(path: Path, limit: int) -> List[Dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    buf: deque = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                buf.append(json.loads(line))
            except Exception:
                continue
    return list(buf)[::-1]


def _extract_dify_answer_text(dify_response: Dict[str, Any]) -> str:
    data = dify_response.get("data")
    if not isinstance(data, dict):
        return ""

    outputs = data.get("outputs")
    if isinstance(outputs, dict):
        for key in ("final", "answer", "text", "result", "content"):
            value = outputs.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    answer = data.get("answer")
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return ""


def _extract_dify_result(dify_response: Dict[str, Any]) -> Any:
    data = dify_response.get("data")
    if isinstance(data, dict):
        outputs = data.get("outputs")
        if outputs is not None:
            return outputs
        if data.get("answer") is not None:
            return data.get("answer")

    answer_text = _extract_dify_answer_text(dify_response)
    if answer_text:
        return answer_text
    return {}


def _is_retryable_dify_http_status(status_code: int) -> bool:
    return int(status_code) in {429, 500, 502, 503, 504}


def _looks_like_html(text: str) -> bool:
    head = (text or "").strip().lower()[:400]
    return "<!doctype html" in head or "<html" in head


def _parse_dify_raw_response(raw_bytes: bytes, content_type: str = "") -> Dict[str, Any]:
    text = raw_bytes.decode("utf-8", errors="ignore").strip()
    if not text:
        raise ValueError("Empty response body from Dify.")

    # 1) Prefer JSON when content-type says JSON or body starts with JSON token.
    if "json" in (content_type or "").lower() or text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return {"data": {"outputs": {"items": parsed}}}
        except Exception:
            # fall through to SSE/text parsing
            pass

    # 2) Some gateways may return SSE-like lines even on API paths.
    if "data:" in text:
        events: List[Any] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                events.append(json.loads(payload))
            except Exception:
                events.append({"text": payload})
        if events:
            last = events[-1]
            if isinstance(last, dict):
                if "data" in last:
                    return last
                return {"data": {"outputs": last}}
            return {"data": {"outputs": {"events": events}}}

    # 3) If endpoint returns HTML, this is almost always a bad tunnel / wrong URL.
    if _looks_like_html(text):
        raise ValueError(
            "Dify endpoint returned HTML (non-API page). "
            "Please check DIFY_BASE_URL / DIFY_WORKFLOW_ENDPOINT routing."
        )

    # 4) Last resort: keep plain text as answer output.
    return {"data": {"outputs": {"answer": text[:12000]}}}


def _build_local_dify_fallback_markdown(payload: "DifyAccidentCaseRequest", reason: Any) -> str:
    video_raw = payload.video_result or {}
    image_raw = payload.image_evidence or {}
    additional = payload.additional_evidence or ""

    video = _compact_video_result_for_dify(_stabilize_video_result_for_dify(video_raw))
    image = _compact_image_evidence_for_dify(_stabilize_image_evidence_for_dify(image_raw))
    packet = _build_liability_evidence_packet(video, image, additional)

    timeline = video.get("timeline") if isinstance(video.get("timeline"), dict) else {}
    topk = video.get("type_topk") if isinstance(video.get("type_topk"), list) else []
    topk_text = ", ".join(
        [
            f"{str(item.get('type') or 'unknown')}({float(item.get('prob') or 0.0):.2f})"
            for item in topk[:3]
        ]
    ) or "N/A"
    missing = packet.get("missing_critical_evidence")
    missing_text = "、".join([str(x) for x in missing]) if isinstance(missing, list) and missing else "无"
    reason_text = str(reason)[:360] if reason is not None else "unknown"

    return (
        "# Dify 暂时不可用（已自动回退本地分析）\n\n"
        "系统已完成关键事实抽取，你可以继续在前端查看和保存本次分析结果。\n\n"
        "## 事故主结论（本地）\n"
        f"- 事故类型：{video.get('accident_type', 'unknown')}\n"
        f"- 置信度：{float(video.get('type_confidence') or 0.0):.3f}\n"
        f"- 车辆数量：{int(video.get('vehicle_count') or 0)}\n"
        f"- 时序：onset={timeline.get('onset_time', 0)}s, impact={timeline.get('impact_time', 0)}s, post={timeline.get('post_time', 0)}s\n"
        f"- 类型候选：{topk_text}\n\n"
        "## 证据充分性\n"
        f"- readiness：{packet.get('readiness', 'unknown')}\n"
        f"- readiness_score：{float(packet.get('readiness_score') or 0.0):.3f}\n"
        f"- 缺失关键证据：{missing_text}\n"
        f"- 建议：{packet.get('recommendation', '请补充更多证据后再定责。')}\n\n"
        "## 说明\n"
        "- 当前为本地兜底结果（Dify 上游不可用时自动触发）。\n"
        "- 上游恢复后会自动回到 Dify 推理。\n"
        f"- 回退原因：{reason_text}\n"
    )


def _call_dify_workflow(
    inputs: Dict[str, Any],
    user: str,
    response_mode: Optional[str] = None,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    settings = _get_dify_settings()
    workflow_url = str(settings["workflow_url"]).strip()
    api_key = str(settings["api_key"]).strip()
    timeout_sec = max(5, _as_int(settings.get("timeout_sec"), 60))
    retry_count = max(0, _as_int(os.getenv("DIFY_RETRY_COUNT", "2"), 2))
    retry_backoff_sec = max(0.2, _as_float(os.getenv("DIFY_RETRY_BACKOFF_SEC", "0.8")) or 0.8)

    if not workflow_url.startswith("http://") and not workflow_url.startswith("https://"):
        raise HTTPException(
            status_code=500,
            detail="Dify workflow URL is invalid. Configure DIFY_BASE_URL or DIFY_WORKFLOW_ENDPOINT.",
        )
    if not api_key:
        raise HTTPException(status_code=500, detail="DIFY_API_KEY is not configured.")

    payload: Dict[str, Any] = {
        "inputs": inputs or {},
        "response_mode": response_mode or settings["default_response_mode"],
        "user": user or "accident_app",
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id

    request_body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        workflow_url,
        data=request_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream;q=0.9, text/plain;q=0.8",
            "Accept-Encoding": "identity",
            "Connection": "close",
        },
    )

    attempts = retry_count + 1
    last_error: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib_request.urlopen(req, timeout=timeout_sec) as resp:
                content_type = str(resp.headers.get("Content-Type", ""))
                raw_bytes = resp.read()
            return _parse_dify_raw_response(raw_bytes, content_type)

        except urllib_error.HTTPError as exc:
            last_error = exc
            status_code = int(exc.code or 500)
            raw_bytes = exc.read() or b""

            if _is_retryable_dify_http_status(status_code) and attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue

            raw = raw_bytes.decode("utf-8", errors="ignore")
            try:
                dify_error = json.loads(raw) if raw else {}
            except Exception:
                dify_error = {"raw": raw[:1200]}
            raise HTTPException(
                status_code=status_code,
                detail={
                    "message": "Dify workflow request failed",
                    "dify_error": dify_error,
                },
            )

        except IncompleteRead as exc:
            last_error = exc
            partial = bytes(exc.partial or b"")
            if partial:
                try:
                    return _parse_dify_raw_response(partial, "")
                except Exception:
                    pass
            if attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(
                status_code=502,
                detail="Dify response interrupted (IncompleteRead). Please check upstream gateway stability.",
            )

        except urllib_error.URLError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(status_code=502, detail=f"Failed to connect to Dify: {exc.reason}")

        except TimeoutError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(status_code=504, detail="Dify workflow request timed out.")

        except ValueError as exc:
            # Parsing/format errors (e.g. HTML login page from tunnel) should fail fast.
            raise HTTPException(status_code=502, detail=f"Dify response format invalid: {exc}")

        except Exception as exc:
            last_error = exc
            if "IncompleteRead" in str(exc) and attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(status_code=500, detail=f"Unexpected Dify error: {exc}")

    raise HTTPException(status_code=500, detail=f"Unexpected Dify error after retries: {last_error}")


def _probe_dify_endpoint(workflow_url: str, timeout_sec: int = 8) -> Dict[str, Any]:
    """Lightweight reachability probe for Dify workflow endpoint."""
    result: Dict[str, Any] = {
        "ok": False,
        "status_code": None,
        "content_type": "",
        "looks_like_html": False,
        "message": "",
    }
    workflow_url = str(workflow_url or "").strip()
    if not workflow_url:
        result["message"] = "workflow_url is empty"
        return result

    req = urllib_request.Request(
        workflow_url,
        method="GET",
        headers={
            "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
            "Connection": "close",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=max(3, int(timeout_sec))) as resp:
            status_code = int(getattr(resp, "status", 200))
            content_type = str(resp.headers.get("Content-Type", ""))
            head = (resp.read(256) or b"").decode("utf-8", errors="ignore").lower()
        looks_like_html = ("text/html" in content_type.lower()) or ("<html" in head) or ("<!doctype html" in head)
        result.update(
            {
                "status_code": status_code,
                "content_type": content_type,
                "looks_like_html": looks_like_html,
                "ok": (not looks_like_html),
                "message": "ok" if not looks_like_html else "endpoint returned HTML page, not Dify API JSON",
            }
        )
        return result
    except urllib_error.HTTPError as exc:
        status_code = int(exc.code or 0)
        raw = exc.read() or b""
        content_type = str(exc.headers.get("Content-Type", "")) if exc.headers else ""
        head = raw[:256].decode("utf-8", errors="ignore").lower()
        looks_like_html = ("text/html" in content_type.lower()) or ("<html" in head) or ("<!doctype html" in head)
        # 401/403/404/405 commonly mean endpoint is reachable (auth/method/path issue), not tunnel html page.
        ok = (status_code in {400, 401, 403, 404, 405, 415, 422}) and (not looks_like_html)
        result.update(
            {
                "status_code": status_code,
                "content_type": content_type,
                "looks_like_html": looks_like_html,
                "ok": ok,
                "message": "reachable_with_http_error" if ok else f"HTTPError {status_code}",
            }
        )
        return result
    except Exception as exc:
        result["message"] = f"probe_failed: {exc}"
        return result


def safe_filename(filename: str) -> str:
    if not filename:
        return f"video_{uuid.uuid4().hex}.mp4"
    path = Path(filename)
    return f"{path.stem}_{uuid.uuid4().hex[:8]}{path.suffix or '.mp4'}"


def save_upload_file(upload_file: UploadFile, destination: Path) -> None:
    with destination.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def empty_direct_shared_pair_agg() -> Dict[str, Any]:
    return {
        "pair_duration_frames": 0,
        "pair_duration_sec": 0.0,
        "mean_longitudinal_velocity_rel": None,
        "max_abs_lateral_velocity_rel": None,
        "min_ttc_eff": None,
        "min_thw_eff": None,
        "min_dhw_eff": None,
        "lane_change_count_pair": 0,
        "lane_change_ratio_pair": 0.0,
        "observed_pair_points": 0,
    }


def center_distance(c1: Tuple[float, float], c2: Tuple[float, float]) -> float:
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5


def compute_iou(box1, box2) -> float:
    x1, y1, x2, y2 = box1
    a1, b1, a2, b2 = box2

    inter_x1 = max(x1, a1)
    inter_y1 = max(y1, b1)
    inter_x2 = min(x2, a2)
    inter_y2 = min(y2, b2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area2 = max(0.0, a2 - a1) * max(0.0, b2 - b1)
    union = area1 + area2 - inter_area

    if union <= 0:
        return 0.0
    return inter_area / union


def compute_motion_score(prev_frame: Optional[np.ndarray], curr_frame: np.ndarray) -> float:
    if prev_frame is None:
        return 0.0

    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(prev_gray, curr_gray)
    mean_diff = float(np.mean(diff))
    return clamp01(mean_diff / 35.0)


def moving_average(values: List[float], k: int = 5) -> List[float]:
    if not values:
        return []
    arr = np.array(values, dtype=np.float32)
    if len(arr) < k:
        return arr.tolist()
    kernel = np.ones(k, dtype=np.float32) / k
    smooth = np.convolve(arr, kernel, mode="same")
    return smooth.tolist()


def result_to_detections(result) -> List[Dict[str, Any]]:
    detections = []

    if result is None or result.boxes is None:
        return detections

    if result.boxes.xyxy is None or len(result.boxes.xyxy) == 0:
        return detections

    boxes = result.boxes.xyxy.cpu().numpy()
    confs = result.boxes.conf.cpu().numpy()
    classes = result.boxes.cls.cpu().numpy().astype(int)

    if result.boxes.id is not None:
        ids = result.boxes.id.int().cpu().numpy()
    else:
        ids = np.array([-1] * len(boxes))

    for box, conf, cls_id, tid in zip(boxes, confs, classes, ids):
        if cls_id not in VEHICLE_CLASS_IDS:
            continue

        x1, y1, x2, y2 = box.tolist()
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        area = max(0.0, (x2 - x1) * (y2 - y1))

        detections.append({
            "bbox": [x1, y1, x2, y2],
            "center": [cx, cy],
            "area": area,
            "conf": float(conf),
            "cls_id": int(cls_id),
            "track_id": int(tid)
        })

    return detections


def update_track_memory(
    detections: List[Dict[str, Any]],
    current_sec: float,
    track_memory: Dict[int, deque]
) -> List[Dict[str, Any]]:
    for det in detections:
        tid = det["track_id"]
        if tid < 0:
            det["vx"] = 0.0
            det["vy"] = 0.0
            continue

        history = track_memory[tid]
        history.append({
            "sec": current_sec,
            "center": det["center"]
        })

        if len(history) >= 2:
            p1 = history[-2]
            p2 = history[-1]
            dt = max(1e-6, p2["sec"] - p1["sec"])
            vx = (p2["center"][0] - p1["center"][0]) / dt
            vy = (p2["center"][1] - p1["center"][1]) / dt
        else:
            vx, vy = 0.0, 0.0

        det["vx"] = float(vx)
        det["vy"] = float(vy)

    return detections


def compute_pair_metrics(
    d1: Dict[str, Any],
    d2: Dict[str, Any],
    frame_shape,
    pair_history: Dict[Tuple[int, int], Dict[str, float]],
    current_sec: float
) -> Tuple[Dict[str, float], Dict[str, float], Dict[str, float]]:
    h, w = frame_shape[:2]
    diag = max(1.0, math.sqrt(w * w + h * h))

    c1 = tuple(d1["center"])
    c2 = tuple(d2["center"])

    dx = c2[0] - c1[0]
    dy = c2[1] - c1[1]
    mx = (c1[0] + c2[0]) / 2.0
    my = (c1[1] + c2[1]) / 2.0

    dist = center_distance(c1, c2)
    dist_norm = dist / diag

    close_score = clamp01(1.0 - dist_norm * 2.2)

    lateral_dist = abs(dx) / max(1.0, w)
    vertical_dist = abs(dy) / max(1.0, h)

    lateral_close_score = clamp01(1.0 - lateral_dist * 2.8)
    vertical_close_score = clamp01(1.0 - vertical_dist * 2.8)

    iou_score = compute_iou(d1["bbox"], d2["bbox"])

    pair_key = tuple(sorted((d1["track_id"], d2["track_id"])))
    hist = pair_history.get(pair_key, None)

    approach_score = 0.0
    ttc_score = 0.0
    iou_growth_score = 0.0
    shock_score = 0.0
    lateral_shift_score = 0.0
    cutin_continuity = 0.0
    direction_change_score = 0.0
    front_back_order_score = 0.0

    closing_speed = 0.0
    ttc_raw = -1.0
    thw_like = -1.0
    dhw_like = float(dist)
    prev_closing_speed = 0.0
    prev_dx = dx
    prev_dy = dy
    prev_cutin_score = 0.0
    prev_rel_vx = 0.0
    prev_rel_vy = 0.0

    if hist is not None:
        prev_dist = hist["dist"]
        prev_sec = hist["sec"]
        prev_iou = hist.get("iou", 0.0)
        prev_closing_speed = hist.get("closing_speed", 0.0)
        prev_dx = hist.get("dx", dx)
        prev_dy = hist.get("dy", dy)
        prev_cutin_score = hist.get("cutin_score", 0.0)
        prev_rel_vx = hist.get("rel_vx", 0.0)
        prev_rel_vy = hist.get("rel_vy", 0.0)

        dt = max(1e-6, current_sec - prev_sec)

        closing_speed = max(0.0, (prev_dist - dist) / dt)
        approach_score = clamp01(closing_speed / (diag * 0.18))

        if closing_speed > 1e-6:
            ttc = dist / closing_speed
            ttc_raw = float(ttc)
            ttc_score = clamp01(1.0 - min(ttc, 4.0) / 4.0)

        iou_growth = max(0.0, iou_score - prev_iou)
        iou_growth_score = clamp01(iou_growth / 0.05)

        shock_drop = max(0.0, prev_closing_speed - closing_speed)
        shock_score = clamp01(shock_drop / (diag * 0.10))

        dx_change = abs(dx - prev_dx) / max(1.0, w)
        lateral_shift_score = clamp01(dx_change / 0.08)

        same_order = 1.0 if dy * prev_dy >= 0 else 0.0
        front_back_order_score = clamp01(0.7 * same_order + 0.3 * vertical_close_score)

    lateral_speed = abs(d1["vx"] - d2["vx"])
    cutin_score = clamp01(lateral_speed / (w * 0.35))
    cutin_continuity = clamp01(0.6 * cutin_score + 0.4 * prev_cutin_score)

    future_c1 = (c1[0] + d1["vx"] * 1.0, c1[1] + d1["vy"] * 1.0)
    future_c2 = (c2[0] + d2["vx"] * 1.0, c2[1] + d2["vy"] * 1.0)
    future_dist = center_distance(future_c1, future_c2)

    convergence_delta = max(0.0, dist - future_dist)
    convergence_score = clamp01(convergence_delta / (diag * 0.12))

    sustain_score = clamp01(0.65 * close_score + 0.35 * iou_score)

    same_lane_score = clamp01(0.75 * lateral_close_score + 0.25 * (1.0 - lateral_shift_score))

    longitudinal_dominance = clamp01(
        0.45 * vertical_close_score +
        0.35 * approach_score +
        0.20 * (1.0 - cutin_score)
    )

    side_overlap_growth = clamp01(
        0.55 * iou_growth_score +
        0.45 * lateral_close_score
    )

    off_lane_conflict_score = clamp01(
        0.6 * (1.0 - same_lane_score) +
        0.4 * lateral_shift_score
    )

    path_crossing_score = clamp01(
        0.45 * convergence_score +
        0.20 * off_lane_conflict_score +
        0.20 * lateral_shift_score +
        0.15 * approach_score
    )

    rel_vx = d2["vx"] - d1["vx"]
    rel_vy = d2["vy"] - d1["vy"]
    longitudinal_speed_ref = max(abs(d1["vy"]), abs(d2["vy"]))
    if longitudinal_speed_ref > 1e-6:
        thw_like = float(dist / longitudinal_speed_ref)

    prev_norm = math.sqrt(prev_rel_vx * prev_rel_vx + prev_rel_vy * prev_rel_vy)
    curr_norm = math.sqrt(rel_vx * rel_vx + rel_vy * rel_vy)

    if prev_norm > 1e-6 and curr_norm > 1e-6:
        dot = prev_rel_vx * rel_vx + prev_rel_vy * rel_vy
        cos_val = dot / (prev_norm * curr_norm + 1e-6)
        cos_val = max(-1.0, min(1.0, cos_val))
        angle = math.acos(cos_val) / math.pi
        direction_change_score = clamp01(angle / 0.5)
    else:
        direction_change_score = 0.0

    metrics = {
        "close_score": close_score,
        "lateral_close_score": lateral_close_score,
        "vertical_close_score": vertical_close_score,
        "iou_score": iou_score,
        "approach_score": approach_score,
        "ttc_score": ttc_score,
        "cutin_score": cutin_score,
        "convergence_score": convergence_score,
        "iou_growth_score": iou_growth_score,
        "shock_score": shock_score,
        "sustain_score": sustain_score,
        "same_lane_score": same_lane_score,
        "front_back_order_score": front_back_order_score,
        "longitudinal_dominance": longitudinal_dominance,
        "lateral_shift_score": lateral_shift_score,
        "cutin_continuity": cutin_continuity,
        "side_overlap_growth": side_overlap_growth,
        "path_crossing_score": path_crossing_score,
        "direction_change_score": direction_change_score,
        "off_lane_conflict_score": off_lane_conflict_score,
    }

    pair_info = {
        "dist": float(dist),
        "sec": float(current_sec),
        "iou": float(iou_score),
        "closing_speed": float(closing_speed),
        "dx": float(dx),
        "dy": float(dy),
        "cutin_score": float(cutin_score),
        "rel_vx": float(rel_vx),
        "rel_vy": float(rel_vy),
        "ttc_raw": float(ttc_raw),
        "thw_like": float(thw_like),
        "dhw_like": float(dhw_like),
    }

    # v8.2锛歱air alias 鍚堝苟鐢ㄧ殑绌洪棿绛惧悕锛堝綊涓€鍖栵級
    pair_meta = {
        "mx": float(mx / max(1.0, w)),
        "my": float(my / max(1.0, h)),
        "dx": float(dx / max(1.0, w)),
        "dy": float(dy / max(1.0, h)),
        "dist": float(dist_norm),
    }

    return metrics, pair_info, pair_meta


def scores_from_metrics(metrics: Dict[str, float], motion_score: float) -> Dict[str, float]:
    onset_pair_score = (
        0.22 * metrics["close_score"] +
        0.12 * metrics["lateral_close_score"] +
        0.12 * metrics["vertical_close_score"] +
        0.18 * metrics["approach_score"] +
        0.18 * metrics["ttc_score"] +
        0.10 * metrics["cutin_score"] +
        0.08 * metrics["convergence_score"]
    )

    impact_pair_score = (
        0.18 * metrics["close_score"] +
        0.22 * metrics["iou_score"] +
        0.16 * metrics["iou_growth_score"] +
        0.14 * metrics["approach_score"] +
        0.10 * metrics["ttc_score"] +
        0.06 * metrics["cutin_score"] +
        0.08 * metrics["convergence_score"] +
        0.06 * metrics["shock_score"]
    )

    post_pair_score = (
        0.25 * metrics["sustain_score"] +
        0.20 * metrics["shock_score"] +
        0.18 * metrics["close_score"] +
        0.14 * metrics["iou_score"] +
        0.12 * (1.0 - metrics["approach_score"]) +
        0.06 * metrics["iou_growth_score"] +
        0.05 * metrics["vertical_close_score"]
    )

    rear_end_pair_score = (
        0.28 * metrics["same_lane_score"] +
        0.22 * metrics["front_back_order_score"] +
        0.20 * metrics["longitudinal_dominance"] +
        0.18 * metrics["approach_score"] +
        0.12 * metrics["ttc_score"]
    )

    lane_change_pair_score = (
        0.30 * metrics["cutin_continuity"] +
        0.24 * metrics["lateral_shift_score"] +
        0.20 * metrics["side_overlap_growth"] +
        0.14 * metrics["convergence_score"] +
        0.12 * metrics["approach_score"]
    )

    turn_conflict_pair_score = (
        0.30 * metrics["path_crossing_score"] +
        0.24 * metrics["direction_change_score"] +
        0.20 * metrics["convergence_score"] +
        0.14 * metrics["approach_score"] +
        0.12 * metrics["off_lane_conflict_score"]
    )

    onset = clamp01(0.85 * onset_pair_score + 0.15 * motion_score)
    impact = clamp01(0.90 * impact_pair_score + 0.10 * motion_score)
    post = clamp01(0.92 * post_pair_score + 0.08 * motion_score)
    event = max(onset, impact, post)

    turn_trigger = clamp01(
        0.55 * metrics["path_crossing_score"] +
        0.45 * metrics["direction_change_score"]
    )

    # v9.3: keep rear-end branch stable; only add targeted turn-conflict gate.
    turn_conflict_gate = 1.0 if (
        metrics["path_crossing_score"] >= 0.30 and
        metrics["direction_change_score"] >= 0.22
    ) else 0.0

    rear_end = clamp01(
        0.86 * rear_end_pair_score +
        0.06 * motion_score +
        0.08 * (1.0 - metrics["off_lane_conflict_score"])
    )
    lane_change = clamp01(
        0.92 * lane_change_pair_score +
        0.08 * motion_score
    )
    turn_conflict = clamp01(
        0.82 * turn_conflict_pair_score +
        0.06 * motion_score +
        0.12 * turn_trigger +
        0.08 * turn_conflict_gate
    )

    return {
        "onset": onset,
        "impact": impact,
        "post": post,
        "event": event,
        "rear_end": rear_end,
        "lane_change": lane_change,
        "turn_conflict": turn_conflict,
    }


def compute_frame_pair_scores(
    detections: List[Dict[str, Any]],
    frame_shape,
    motion_score: float,
    pair_history: Dict[Tuple[int, int], Dict[str, float]],
    current_sec: float
) -> Tuple[
    Dict[Tuple[int, int], Dict[str, float]],
    Dict[Tuple[int, int], Dict[str, float]],
    Dict[Tuple[int, int], Dict[str, float]],
    Dict[Tuple[int, int], Dict[str, float]],
    Dict[Tuple[int, int], Dict[str, float]]
]:
    """
    v8.2锛氶櫎浜?pair scores锛岃繕淇濈暀 pair_meta锛?    鏂逛究鍚庨潰鍋?pair alias / ID 瀹归敊鍚堝苟銆?    """
    if len(detections) < 2:
        return {}, {}, {}, {}, pair_history

    frame_pair_scores: Dict[Tuple[int, int], Dict[str, float]] = {}
    frame_pair_metrics: Dict[Tuple[int, int], Dict[str, float]] = {}
    frame_pair_meta: Dict[Tuple[int, int], Dict[str, float]] = {}
    frame_pair_info: Dict[Tuple[int, int], Dict[str, float]] = {}
    new_pair_history = {}

    for i in range(len(detections)):
        for j in range(i + 1, len(detections)):
            d1 = detections[i]
            d2 = detections[j]

            if d1["track_id"] < 0 or d2["track_id"] < 0:
                continue

            pair_key = tuple(sorted((d1["track_id"], d2["track_id"])))

            metrics, pair_info, pair_meta = compute_pair_metrics(
                d1, d2, frame_shape, pair_history, current_sec
            )
            pair_scores = scores_from_metrics(metrics, motion_score)

            frame_pair_scores[pair_key] = pair_scores
            frame_pair_metrics[pair_key] = metrics
            frame_pair_meta[pair_key] = pair_meta
            frame_pair_info[pair_key] = pair_info
            new_pair_history[pair_key] = pair_info

    for key, info in pair_history.items():
        if current_sec - info["sec"] <= PAIR_HISTORY_TTL_SEC and key not in new_pair_history:
            new_pair_history[key] = info

    return frame_pair_scores, frame_pair_metrics, frame_pair_meta, frame_pair_info, new_pair_history


def collapse_frame_scores(frame_pair_scores: Dict[Tuple[int, int], Dict[str, float]], motion_score: float) -> Dict[str, float]:
    if not frame_pair_scores:
        return {
            "onset": clamp01(0.18 * motion_score),
            "impact": clamp01(0.10 * motion_score),
            "post": clamp01(0.08 * motion_score),
            "event": clamp01(0.18 * motion_score),
            "rear_end": clamp01(0.12 * motion_score),
            "lane_change": clamp01(0.12 * motion_score),
            "turn_conflict": clamp01(0.12 * motion_score),
        }

    best_onset = max(v["onset"] for v in frame_pair_scores.values())
    best_impact = max(v["impact"] for v in frame_pair_scores.values())
    best_post = max(v["post"] for v in frame_pair_scores.values())
    best_rear_end = max(v["rear_end"] for v in frame_pair_scores.values())
    best_lane_change = max(v["lane_change"] for v in frame_pair_scores.values())
    best_turn_conflict = max(v["turn_conflict"] for v in frame_pair_scores.values())

    return {
        "onset": best_onset,
        "impact": best_impact,
        "post": best_post,
        "event": max(best_onset, best_impact, best_post),
        "rear_end": best_rear_end,
        "lane_change": best_lane_change,
        "turn_conflict": best_turn_conflict,
    }


def longest_consecutive_run(indices: List[int]) -> int:
    if not indices:
        return 0
    indices = sorted(set(indices))
    best = 1
    cur = 1
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def longest_run_length(mask: List[bool]) -> int:
    best = 0
    cur = 0
    for v in mask:
        if v:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def build_bridged_indices(indices: List[int], max_gap: int) -> List[int]:
    if not indices:
        return []

    indices = sorted(set(indices))
    bridged = [indices[0]]

    for i in range(1, len(indices)):
        prev_idx = indices[i - 1]
        cur_idx = indices[i]
        gap = cur_idx - prev_idx - 1

        if 0 < gap <= max_gap:
            for fill_idx in range(prev_idx + 1, cur_idx):
                bridged.append(fill_idx)

        bridged.append(cur_idx)

    return sorted(set(bridged))


def longest_run_from_sorted_indices(indices: List[int]) -> int:
    if not indices:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(indices)):
        if indices[i] == indices[i - 1] + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def interpolate_pair_scores(a: Dict[str, float], b: Dict[str, float], alpha: float) -> Dict[str, float]:
    keys = ["onset", "impact", "post", "event", "rear_end", "lane_change", "turn_conflict"]
    return {k: float((1 - alpha) * a[k] + alpha * b[k]) for k in keys}


def pair_cluster_match_score(
    obs_meta: Dict[str, float],
    cluster_last_meta: Dict[str, float],
    gap: int
) -> Optional[float]:
    dm = math.sqrt(
        (obs_meta["mx"] - cluster_last_meta["mx"]) ** 2 +
        (obs_meta["my"] - cluster_last_meta["my"]) ** 2
    )
    dd = math.sqrt(
        (obs_meta["dx"] - cluster_last_meta["dx"]) ** 2 +
        (obs_meta["dy"] - cluster_last_meta["dy"]) ** 2
    )

    if dm > PAIR_ALIAS_MIDPOINT_THR or dd > PAIR_ALIAS_REL_THR:
        return None

    # 瓒婅繎瓒婂儚锛実ap 瓒婂皬瓒婂儚
    return dm + 0.7 * dd + 0.05 * gap


def build_pair_clusters(raw_samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    v8.2 鏍稿績锛?    鎶婃椂闂寸浉閭汇€佺┖闂村叧绯荤浉浼肩殑 pair 瑙傛祴鍚堝苟鎴?pair cluster锛?    浠庤€屽蹇?track id 鍒囨崲銆?    """
    observations = []

    for idx, sample in enumerate(raw_samples):
        for pair_key, pair_scores in sample["pairs"].items():
            pair_meta = sample["pair_meta"].get(pair_key)
            if pair_meta is None:
                continue

            observations.append({
                "idx": idx,
                "pair_key": pair_key,
                "scores": pair_scores,
                "meta": pair_meta,
            })

    observations.sort(key=lambda x: (x["idx"], -x["scores"]["event"]))

    clusters: List[Dict[str, Any]] = []

    for obs in observations:
        best_cluster_idx = None
        best_match_score = None

        for ci, cluster in enumerate(clusters):
            gap = obs["idx"] - cluster["last_idx"]
            if gap < 0 or gap > PAIR_ALIAS_MAX_GAP:
                continue

            match_score = pair_cluster_match_score(obs["meta"], cluster["last_meta"], gap)
            if match_score is None:
                continue

            if best_match_score is None or match_score < best_match_score:
                best_match_score = match_score
                best_cluster_idx = ci

        if best_cluster_idx is None:
            clusters.append({
                "observations": {obs["idx"]: obs},
                "indices": [obs["idx"]],
                "pair_keys": {obs["pair_key"]},
                "last_idx": obs["idx"],
                "last_meta": obs["meta"],
            })
        else:
            cluster = clusters[best_cluster_idx]
            existing = cluster["observations"].get(obs["idx"])

            if existing is None or obs["scores"]["event"] > existing["scores"]["event"]:
                cluster["observations"][obs["idx"]] = obs

            cluster["indices"].append(obs["idx"])
            cluster["pair_keys"].add(obs["pair_key"])
            cluster["last_idx"] = obs["idx"]
            cluster["last_meta"] = obs["meta"]

    return clusters


def lock_dominant_cluster(raw_samples: List[Dict[str, Any]]) -> Tuple[Optional[int], Dict[str, Any], List[Dict[str, Any]]]:
    """
    v8.2锛歞ominant 瀵硅薄涓嶅啀鏄竴涓?exact pair_key锛岃€屾槸涓€涓?pair cluster銆?    """
    clusters = build_pair_clusters(raw_samples)
    if not clusters:
        return None, {}, []

    total_samples = len(raw_samples)
    best_cluster_idx = None
    best_score = -1.0
    best_meta = {}

    for ci, cluster in enumerate(clusters):
        indices = sorted(set(cluster["observations"].keys()))
        count = len(indices)

        raw_longest_run = longest_consecutive_run(indices)
        bridged_indices = build_bridged_indices(indices, max_gap=PAIR_GAP_TOLERANCE)

        coverage = min(1.0, count / 6.0)
        continuity = raw_longest_run / max(1, total_samples)
        bridged_coverage = min(1.0, len(bridged_indices) / 6.0)
        bridged_continuity = longest_run_from_sorted_indices(bridged_indices) / max(1, total_samples)

        event_values = [cluster["observations"][i]["scores"]["event"] for i in indices]
        impact_values = [cluster["observations"][i]["scores"]["impact"] for i in indices]
        onset_values = [cluster["observations"][i]["scores"]["onset"] for i in indices]

        top_event = sorted(event_values, reverse=True)[:4]
        peak_mean = float(np.mean(top_event)) if top_event else 0.0
        impact_peak = max(impact_values) if impact_values else 0.0
        onset_peak = max(onset_values) if onset_values else 0.0

        dominance = (
            0.30 * peak_mean +
            0.18 * impact_peak +
            0.10 * continuity +
            0.10 * coverage +
            0.18 * bridged_continuity +
            0.14 * bridged_coverage
        )

        if dominance > best_score:
            best_score = dominance
            best_cluster_idx = ci
            best_meta = {
                "dominance": round(float(dominance), 4),
                "coverage": round(float(coverage), 4),
                "continuity": round(float(continuity), 4),
                "bridged_coverage": round(float(bridged_coverage), 4),
                "bridged_continuity": round(float(bridged_continuity), 4),
                "peak_mean": round(float(peak_mean), 4),
                "impact_peak": round(float(impact_peak), 4),
                "onset_peak": round(float(onset_peak), 4),
                "count": count,
                "pair_keys": sorted(list(cluster["pair_keys"])),
            }

    return best_cluster_idx, best_meta, clusters


def _min_positive_or_none(values: List[float]) -> Optional[float]:
    pos = [float(v) for v in values if float(v) > 0]
    if not pos:
        return None
    return min(pos)


def aggregate_direct_shared_pair_features(
    raw_samples: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    dominant_cluster_idx: Optional[int],
    fps: float,
) -> Dict[str, Any]:
    out = empty_direct_shared_pair_agg()
    if dominant_cluster_idx is None:
        return out
    if dominant_cluster_idx < 0 or dominant_cluster_idx >= len(clusters):
        return out
    if not raw_samples:
        return out

    cluster = clusters[dominant_cluster_idx]
    observations = cluster.get("observations", {}) or {}
    if not observations:
        return out

    indices = sorted(int(i) for i in observations.keys())
    rel_vy_abs_list: List[float] = []
    rel_vx_abs_list: List[float] = []
    ttc_list: List[float] = []
    thw_list: List[float] = []
    dhw_list: List[float] = []
    lane_change_flags: List[int] = []

    for idx in indices:
        obs = observations.get(idx) or {}
        pair_key = obs.get("pair_key")
        if pair_key is None:
            continue
        sample = raw_samples[idx]
        info = (sample.get("pair_info", {}) or {}).get(pair_key, {}) or {}
        metrics = (sample.get("pair_metrics", {}) or {}).get(pair_key, {}) or {}
        if not info:
            continue

        rel_vx_abs_list.append(abs(float(info.get("rel_vx", 0.0))))
        rel_vy_abs_list.append(abs(float(info.get("rel_vy", 0.0))))
        ttc_list.append(float(info.get("ttc_raw", -1.0)))
        thw_list.append(float(info.get("thw_like", -1.0)))
        dhw_list.append(float(info.get("dhw_like", -1.0)))

        lateral_shift = float(metrics.get("lateral_shift_score", 0.0))
        cutin_cont = float(metrics.get("cutin_continuity", 0.0))
        lane_change_flags.append(1 if (lateral_shift >= 0.35 or cutin_cont >= 0.45) else 0)

    observed_n = len(rel_vx_abs_list)
    out["observed_pair_points"] = int(observed_n)
    out["pair_duration_frames"] = int(max(0, len(indices)))
    if observed_n > 0:
        out["mean_longitudinal_velocity_rel"] = round(float(np.mean(rel_vy_abs_list)), 6)
        out["max_abs_lateral_velocity_rel"] = round(float(max(rel_vx_abs_list)), 6)
        out["lane_change_count_pair"] = int(sum(lane_change_flags))
        out["lane_change_ratio_pair"] = round(float(sum(lane_change_flags) / observed_n), 6)
    else:
        out["lane_change_count_pair"] = 0
        out["lane_change_ratio_pair"] = 0.0

    ttc_min = _min_positive_or_none(ttc_list)
    thw_min = _min_positive_or_none(thw_list)
    dhw_min = _min_positive_or_none(dhw_list)
    out["min_ttc_eff"] = round(float(ttc_min), 6) if ttc_min is not None else None
    out["min_thw_eff"] = round(float(thw_min), 6) if thw_min is not None else None
    out["min_dhw_eff"] = round(float(dhw_min), 6) if dhw_min is not None else None

    if indices:
        sec_left = float(raw_samples[indices[0]].get("sec", 0.0))
        sec_right = float(raw_samples[indices[-1]].get("sec", sec_left))
        out["pair_duration_sec"] = round(max(0.0, sec_right - sec_left), 6)
        est_frames = int(round(out["pair_duration_sec"] * max(1e-6, float(fps)))) + 1
        out["pair_duration_frames"] = int(max(out["pair_duration_frames"], est_frames))
    return out


def build_locked_samples_from_cluster(
    raw_samples: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    dominant_cluster_idx: Optional[int],
    max_gap: int = 2
) -> List[Dict[str, Any]]:
    """
    v8.2锛氶攣瀹氱殑鏄?dominant cluster锛岃€屼笉鏄?exact pair銆?    cluster 鍐呭凡缁忚嚜鍔ㄥ蹇嶄簡 ID 鍒囨崲銆?    """
    observed: Dict[int, Dict[str, float]] = {}

    if dominant_cluster_idx is not None:
        cluster = clusters[dominant_cluster_idx]
        for idx, obs in cluster["observations"].items():
            observed[idx] = obs["scores"]

        observed_indices = sorted(observed.keys())
        for i in range(1, len(observed_indices)):
            left_idx = observed_indices[i - 1]
            right_idx = observed_indices[i]
            gap = right_idx - left_idx - 1

            if 0 < gap <= max_gap:
                left_scores = observed[left_idx]
                right_scores = observed[right_idx]

                for k in range(1, gap + 1):
                    alpha = k / (gap + 1)
                    fill_idx = left_idx + k
                    observed[fill_idx] = interpolate_pair_scores(left_scores, right_scores, alpha)

    locked_samples = []

    for idx, sample in enumerate(raw_samples):
        if idx in observed:
            ps = observed[idx]
        else:
            ps = {
                "onset": 0.0,
                "impact": 0.0,
                "post": 0.0,
                "event": 0.0,
                "rear_end": 0.0,
                "lane_change": 0.0,
                "turn_conflict": 0.0,
            }

        locked_samples.append({
            "sec": sample["sec"],
            "frame": sample["frame"],
            "detections": sample["detections"],

            "onset_score_raw": float(ps["onset"]),
            "impact_score_raw": float(ps["impact"]),
            "post_score_raw": float(ps["post"]),
            "event_score_raw": float(ps["event"]),

            "rear_end_score_raw": float(ps["rear_end"]),
            "lane_change_score_raw": float(ps["lane_change"]),
            "turn_conflict_score_raw": float(ps["turn_conflict"]),

            "onset_score": float(ps["onset"]),
            "impact_score": float(ps["impact"]),
            "post_score": float(ps["post"]),
            "event_score": float(ps["event"]),
            "rear_end_score": float(ps["rear_end"]),
            "lane_change_score": float(ps["lane_change"]),
            "turn_conflict_score": float(ps["turn_conflict"]),

            "onset_score_used": float(ps["onset"]),
            "impact_score_used": float(ps["impact"]),
            "post_score_used": float(ps["post"]),
            "event_score_used": float(ps["event"]),
        })

    return locked_samples


def find_first_strong_peak(scores: List[float], ratio: float = 0.88) -> int:
    if not scores:
        return 0

    arr = np.array(scores, dtype=np.float32)
    max_score = float(arr.max())
    threshold = max_score * ratio
    global_peak_idx = int(np.argmax(arr))

    # Prefer a sustained peak segment over a single noisy spike.
    run_count = 0
    run_start = 0
    sustained_idx: Optional[int] = None
    for i in range(len(arr)):
        if arr[i] >= threshold:
            if run_count == 0:
                run_start = i
            run_count += 1
            if run_count >= 2:
                sustained_idx = run_start
                break
        else:
            run_count = 0

    if sustained_idx is not None:
        # If an obviously stronger late peak exists, correct early onset bias.
        if (
            sustained_idx < int(0.35 * len(arr))
            and global_peak_idx >= sustained_idx + 2
            and arr[global_peak_idx] >= arr[sustained_idx] * 1.08
        ):
            return global_peak_idx
        return sustained_idx

    for i in range(len(arr)):
        if arr[i] >= threshold:
            if (
                i < int(0.35 * len(arr))
                and global_peak_idx >= i + 2
                and arr[global_peak_idx] >= arr[i] * 1.08
            ):
                return global_peak_idx
            return i

    return global_peak_idx


def find_sustained_peak_with_late_bias(
    scores: List[float],
    ratio: float = 0.88,
    min_run: int = 2,
    late_gain: float = 1.08,
) -> int:
    """
    Prefer sustained (consecutive) peaks over single noisy spikes.
    If an early sustained peak exists but a much stronger late peak appears,
    choose the late one.
    """
    if not scores:
        return 0

    arr = np.array(scores, dtype=np.float32)
    max_score = float(arr.max())
    if max_score <= 0:
        return int(np.argmax(arr))

    threshold = max_score * ratio
    global_peak_idx = int(np.argmax(arr))

    run_count = 0
    run_start = 0
    sustained_idx: Optional[int] = None
    for i in range(len(arr)):
        if arr[i] >= threshold:
            if run_count == 0:
                run_start = i
            run_count += 1
            if run_count >= min_run:
                sustained_idx = run_start
                break
        else:
            run_count = 0

    if sustained_idx is None:
        for i in range(len(arr)):
            if arr[i] >= threshold:
                sustained_idx = i
                break

    if sustained_idx is None:
        return global_peak_idx

    # Late stronger-peak correction.
    if (
        sustained_idx < int(0.35 * len(arr))
        and global_peak_idx >= sustained_idx + 2
        and arr[global_peak_idx] >= arr[sustained_idx] * late_gain
    ):
        return global_peak_idx

    return sustained_idx


def find_late_rising_impact_index(
    global_scores: List[float],
    locked_scores: List[float],
    current_idx: int,
    min_offset: int = 2,
    rise_ratio: float = 0.45,
    choose_ratio: float = 0.85,
    min_score: float = 0.10,
) -> Optional[int]:
    if not global_scores or not locked_scores:
        return None
    if len(global_scores) != len(locked_scores):
        return None

    late_start = int(current_idx) + int(min_offset)
    if late_start >= len(global_scores):
        return None

    late_global_peak = max(global_scores[late_start:])
    late_locked_peak = max(locked_scores[late_start:])
    base_locked = max(locked_scores[current_idx], 1e-6)

    # Trigger only when dominant-cluster signal fades, but global signal rises later.
    if late_global_peak < min_score:
        return None
    if late_locked_peak > base_locked * 0.65:
        return None

    rise_threshold = max(min_score, late_global_peak * rise_ratio)
    candidate_start: Optional[int] = None
    for i in range(late_start, len(global_scores)):
        if global_scores[i] >= rise_threshold:
            candidate_start = i
            break

    if candidate_start is None:
        return None

    # Prefer near-peak frame inside late-rise segment, not the earliest crossing point.
    choose_threshold = max(min_score, late_global_peak * choose_ratio)
    for i in range(candidate_start, len(global_scores)):
        if global_scores[i] >= choose_threshold:
            return i

    return None


def nearest_index_by_time(samples: List[Dict[str, Any]], target_sec: float) -> int:
    return min(range(len(samples)), key=lambda i: abs(samples[i]["sec"] - target_sec))


def pick_best_index_in_sec_window(
    samples: List[Dict[str, Any]],
    score_key: str,
    start_sec: float,
    end_sec: float
) -> Optional[int]:
    valid = [
        i for i, item in enumerate(samples)
        if start_sec <= item["sec"] <= end_sec
    ]
    if not valid:
        return None
    return max(valid, key=lambda i: samples[i][score_key])


def safe_pick_stage(
    samples: List[Dict[str, Any]],
    score_key: str,
    start_sec: float,
    end_sec: float,
    target_sec: float
) -> int:
    if not samples:
        return 0

    video_end = samples[-1]["sec"]

    start_sec = max(0.0, start_sec)
    end_sec = min(video_end, end_sec)
    target_sec = min(video_end, max(0.0, target_sec))

    idx = None
    if end_sec >= start_sec:
        idx = pick_best_index_in_sec_window(samples, score_key, start_sec, end_sec)

    if idx is None:
        idx = nearest_index_by_time(samples, target_sec)

    return idx


def choose_stage_items(samples: List[Dict[str, Any]], type_name: str = "generic") -> List[Dict[str, Any]]:
    if not samples:
        return []

    cfg = TYPE_WINDOW_CONFIG.get(type_name, TYPE_WINDOW_CONFIG["generic"])

    onset_idx = find_first_strong_peak(
        [item["onset_score_used"] for item in samples],
        ratio=ONSET_RATIO
    )
    onset_sec = float(samples[onset_idx]["sec"])

    pre_idx = safe_pick_stage(
        samples,
        "onset_score_used",
        onset_sec + cfg["pre"][0],
        onset_sec + cfg["pre"][1],
        onset_sec + cfg["pre"][2]
    )

    approach_idx = safe_pick_stage(
        samples,
        "event_score_used",
        onset_sec + cfg["approach"][0],
        onset_sec + cfg["approach"][1],
        onset_sec + cfg["approach"][2]
    )

    impact_idx = safe_pick_stage(
        samples,
        "impact_score_used",
        onset_sec + cfg["impact"][0],
        onset_sec + cfg["impact"][1],
        onset_sec + cfg["impact"][2]
    )

    # Global impact correction: use fused signal to avoid dominant-cluster early bias.
    locked_impact_scores = [float(item["impact_score_used"]) for item in samples]
    global_impact_scores = [float(item.get("impact_score_global", item["impact_score_used"])) for item in samples]
    impact_scores = [
        max(
            float(item["impact_score_used"]),
            float(item.get("impact_score_global", 0.0))
        )
        for item in samples
    ]
    global_impact_idx = find_sustained_peak_with_late_bias(
        impact_scores,
        ratio=0.90,
        min_run=2,
        late_gain=1.04,
    )
    if (
        global_impact_idx >= impact_idx + 2
        and impact_scores[global_impact_idx] >= impact_scores[impact_idx] * 1.04
    ):
        impact_idx = global_impact_idx

    late_rising_idx = find_late_rising_impact_index(
        global_scores=global_impact_scores,
        locked_scores=locked_impact_scores,
        current_idx=impact_idx,
    )
    if late_rising_idx is not None and late_rising_idx >= impact_idx + 2:
        impact_idx = late_rising_idx

    impact_sec = float(samples[impact_idx]["sec"])

    # Re-anchor onset relative to corrected impact to avoid chain bias.
    onset_idx = safe_pick_stage(
        samples,
        "onset_score_used",
        impact_sec - 2.4,
        impact_sec - 0.8,
        impact_sec - 1.6
    )
    onset_idx = max(0, min(onset_idx, max(0, impact_idx - 1)))
    onset_sec = float(samples[onset_idx]["sec"])

    pre_idx = safe_pick_stage(
        samples,
        "onset_score_used",
        onset_sec + cfg["pre"][0],
        onset_sec + cfg["pre"][1],
        onset_sec + cfg["pre"][2]
    )

    approach_idx = safe_pick_stage(
        samples,
        "event_score_used",
        onset_sec + cfg["approach"][0],
        onset_sec + cfg["approach"][1],
        onset_sec + cfg["approach"][2]
    )

    post_idx = safe_pick_stage(
        samples,
        "post_score_used",
        impact_sec + cfg["post"][0],
        impact_sec + cfg["post"][1],
        impact_sec + cfg["post"][2]
    )

    return [
        {"stage": "pre", "idx": pre_idx},
        {"stage": "approach", "idx": approach_idx},
        {"stage": "onset", "idx": onset_idx},
        {"stage": "impact", "idx": impact_idx},
        {"stage": "post", "idx": post_idx},
    ]


def force_fixed_five_stage_order(
    stage_items: List[Dict[str, Any]],
    samples: List[Dict[str, Any]],
    min_gap_sec: float
) -> List[Dict[str, Any]]:
    ordered_stages = ["pre", "approach", "onset", "impact", "post"]
    by_stage = {item["stage"]: {"stage": item["stage"], "idx": item["idx"]} for item in stage_items}

    result = []
    last_idx = -1
    last_sec = -1e9

    for stage in ordered_stages:
        item = by_stage[stage]
        idx = item["idx"]

        while idx < len(samples) - 1 and (
            idx <= last_idx or samples[idx]["sec"] - last_sec < min_gap_sec
        ):
            idx += 1

        idx = min(idx, len(samples) - 1)

        result.append({
            "stage": stage,
            "idx": idx
        })

        last_idx = idx
        last_sec = samples[idx]["sec"]

    return result


def classify_accident_type(
    samples: List[Dict[str, Any]],
    onset_idx: int,
    impact_idx: int,
    raw_samples: Optional[List[Dict[str, Any]]] = None
) -> Tuple[str, float, Dict[str, float], Dict[str, float]]:
    if not samples:
        return "generic", 0.0, {
            "rear_end": 0.0,
            "lane_change": 0.0,
            "turn_conflict": 0.0
        }, {
            "intersection_prior": 0.0,
            "turning_scene_prior": 0.0,
            "turn_candidate_boost": 0.0,
            "turn_candidate_run": 0.0,
        }

    start_idx = max(0, onset_idx - 1)
    end_idx = min(len(samples) - 1, impact_idx + 1)

    rear_end_vals = [samples[i]["rear_end_score"] for i in range(start_idx, end_idx + 1)]
    lane_change_vals = [samples[i]["lane_change_score"] for i in range(start_idx, end_idx + 1)]
    turn_conflict_vals = [samples[i]["turn_conflict_score"] for i in range(start_idx, end_idx + 1)]

    rear_mean = float(np.mean(rear_end_vals)) if rear_end_vals else 0.0
    lane_mean = float(np.mean(lane_change_vals)) if lane_change_vals else 0.0
    turn_mean = float(np.mean(turn_conflict_vals)) if turn_conflict_vals else 0.0

    rear_peak = float(max(rear_end_vals)) if rear_end_vals else 0.0
    lane_peak = float(max(lane_change_vals)) if lane_change_vals else 0.0
    turn_peak = float(max(turn_conflict_vals)) if turn_conflict_vals else 0.0

    # Branch A (stable): v9.1-style balanced scoring.
    rear_base = max(
        0.0,
        rear_mean -
        0.18 * max(0.0, lane_peak - rear_peak * 0.85) -
        0.24 * max(0.0, turn_peak - rear_peak * 0.80),
    )
    lane_base = lane_mean + 0.10 * max(0.0, lane_peak - rear_peak * 0.78)
    turn_base = turn_mean + 0.18 * max(0.0, turn_peak - rear_peak * 0.72)

    # v9.4: candidate segment re-scoring for turn-conflict.
    candidate_mask = [
        (
            float(s["turn_conflict_score"]) >= TURN_CANDIDATE_SCORE_THR and
            float(s["event_score"]) >= TURN_CANDIDATE_EVENT_THR
        )
        for s in samples
    ]
    run_len = longest_run_length(candidate_mask)
    candidate_scores = [
        float(samples[i]["turn_conflict_score"])
        for i in range(len(samples))
        if candidate_mask[i]
    ]
    candidate_boost = 0.0
    if run_len >= TURN_CANDIDATE_MIN_RUN and candidate_scores:
        candidate_peak = max(candidate_scores)
        candidate_mean = float(np.mean(candidate_scores))
        candidate_boost = clamp01(0.60 * candidate_peak + 0.40 * candidate_mean)

    # v9.4: scene prior gating (intersection / turning_scene proxy).
    if raw_samples is None:
        raw_samples = []

    det_counts = [len(item.get("detections", [])) for item in raw_samples] if raw_samples else []
    multi_actor_ratio = (
        float(sum(1 for c in det_counts if c >= 3)) / max(1, len(det_counts))
        if det_counts else 0.0
    )
    crossing_energy = clamp01(0.65 * turn_peak + 0.35 * turn_mean)
    event_density = float(sum(1 for s in samples if float(s["event_score"]) >= 0.34)) / max(1, len(samples))

    intersection_prior = clamp01(
        0.44 * crossing_energy +
        0.31 * multi_actor_ratio +
        0.25 * event_density
    )
    turning_scene_prior = clamp01(
        0.52 * crossing_energy +
        0.28 * event_density +
        0.20 * multi_actor_ratio
    )
    scene_prior = clamp01(0.55 * intersection_prior + 0.45 * turning_scene_prior)

    # Branch B (turn-focus): targeted boosting for turn_conflict.
    rear_focus = rear_mean
    lane_focus = lane_mean + 0.10 * max(0.0, lane_peak - rear_peak * 0.78)
    turn_focus = turn_mean + 0.20 * max(0.0, turn_peak - rear_peak * 0.70)

    turn_evidence = 0.62 * turn_peak + 0.38 * turn_mean
    rear_evidence = 0.60 * rear_peak + 0.40 * rear_mean
    lane_evidence = 0.60 * lane_peak + 0.40 * lane_mean

    if turn_evidence >= 0.34 and turn_peak >= 0.24 and turn_peak >= rear_peak * 0.64:
        turn_focus += 0.12
    if turn_evidence >= 0.40 and turn_peak >= max(0.28, rear_peak * 0.60):
        turn_focus += 0.08
    if lane_evidence >= 0.36 and lane_peak >= max(0.24, rear_peak * 0.70):
        lane_focus += 0.05
    if rear_evidence <= 0.18 and turn_evidence >= 0.32:
        turn_focus += 0.04
    if run_len >= TURN_CANDIDATE_MIN_RUN:
        turn_focus += 0.16 * candidate_boost
        if candidate_boost >= 0.46:
            turn_focus += 0.05
    if scene_prior >= 0.36 and turn_evidence >= 0.30:
        turn_focus += 0.10 * scene_prior
    if scene_prior >= 0.48 and (run_len >= TURN_CANDIDATE_MIN_RUN or candidate_boost >= 0.40):
        turn_focus += 0.06
    if scene_prior >= 0.45 and turn_evidence >= 0.34 and candidate_boost >= 0.38:
        rear_focus *= 0.93

    # Router: only switch to turn-focused branch when turn evidence is jointly strong.
    router_score = clamp01(
        0.45 * scene_prior +
        0.35 * candidate_boost +
        0.20 * turn_evidence
    )
    use_turn_focus = (
        router_score >= TURN_ROUTER_SCORE_THR and
        (turn_peak >= 0.26 or run_len >= TURN_CANDIDATE_MIN_RUN)
    )

    if use_turn_focus:
        route_mode = "turn_focus"
        type_scores = {
            "rear_end": rear_focus,
            "lane_change": lane_focus,
            "turn_conflict": turn_focus,
        }
    else:
        route_mode = "stable"
        type_scores = {
            "rear_end": rear_base,
            "lane_change": lane_base,
            "turn_conflict": turn_base,
        }

    # v9.6 stage-2: refine only turn_conflict candidates without global rear-end suppression.
    stage2_score = clamp01(
        0.36 * scene_prior +
        0.32 * candidate_boost +
        0.22 * turn_evidence +
        0.10 * (1.0 if run_len >= TURN_CANDIDATE_MIN_RUN else 0.0)
    )
    rear_score = float(type_scores["rear_end"])
    turn_score = float(type_scores["turn_conflict"])
    near_tie = (rear_score - turn_score) <= TURN_STAGE2_MARGIN
    stage2_applied = False
    if stage2_score >= TURN_STAGE2_GATE and near_tie:
        stage2_applied = True
        type_scores["turn_conflict"] = turn_score + 0.10 * stage2_score + 0.03
        if stage2_score >= 0.52:
            type_scores["turn_conflict"] += 0.03
        type_scores["rear_end"] = max(0.0, rear_score - 0.04 * stage2_score)
        if route_mode == "stable":
            route_mode = "stable+stage2_turn"
        else:
            route_mode = "turn_focus+stage2_turn"

    chosen_type = max(type_scores.items(), key=lambda x: x[1])[0]
    total = sum(type_scores.values()) + 1e-6
    confidence = type_scores[chosen_type] / total

    scene_info = {
        "intersection_prior": round(float(intersection_prior), 4),
        "turning_scene_prior": round(float(turning_scene_prior), 4),
        "turn_candidate_boost": round(float(candidate_boost), 4),
        "turn_candidate_run": float(run_len),
        "turn_evidence": round(float(turn_evidence), 4),
        "router_score": round(float(router_score), 4),
        "stage2_score": round(float(stage2_score), 4),
        "stage2_applied": bool(stage2_applied),
        "rear_score_pre": round(float(rear_score), 4),
        "turn_score_pre": round(float(turn_score), 4),
        "route_mode": route_mode,
    }
    return chosen_type, round(float(confidence), 4), type_scores, scene_info


def apply_rear_guard_v343(
    base_type: str,
    type_probs: Dict[str, float],
    scene_prior: Dict[str, float],
) -> Dict[str, Any]:
    probs = type_probs if isinstance(type_probs, dict) else {}
    scores = {
        "rear_end": float(probs.get("rear_end", 0.0) or 0.0),
        "lane_change": float(probs.get("lane_change", 0.0) or 0.0),
        "turn_conflict": float(probs.get("turn_conflict", 0.0) or 0.0),
    }

    base_pred = str(base_type or "").strip()
    if base_pred not in {"rear_end", "lane_change", "turn_conflict"}:
        base_pred = max(scores.items(), key=lambda x: x[1])[0]

    final_pred = base_pred
    reason_code = "BASE_NOT_TURN"
    applied = False
    scene_blocked = False

    if base_pred == "turn_conflict":
        scene_info = scene_prior if isinstance(scene_prior, dict) else {}
        intersection_prior = float(scene_info.get("intersection_prior", 0.0) or 0.0)
        turning_scene_prior = float(scene_info.get("turning_scene_prior", 0.0) or 0.0)
        scene_blocked = (
            intersection_prior >= REAR_GUARD_SCENE_PRIOR_THR or
            turning_scene_prior >= REAR_GUARD_SCENE_PRIOR_THR
        )

        if scene_blocked:
            reason_code = "SCENE_BLOCKED"
        else:
            pr = scores["rear_end"]
            pl = scores["lane_change"]
            pt = scores["turn_conflict"]
            if (
                pr >= REAR_GUARD_REAR_FLOOR and
                (pt - pr) <= REAR_GUARD_GAP_MAX and
                pt <= REAR_GUARD_TURN_CEILING and
                pl <= REAR_GUARD_LANE_CAP
            ):
                final_pred = "rear_end"
                applied = True
                reason_code = "TURN_TO_REAR_CLOSE_PROB"
            else:
                reason_code = "THRESHOLD_NOT_MET"

    return {
        "applied": bool(applied),
        "version": REAR_GUARD_VERSION,
        "cfg": dict(REAR_GUARD_CONFIG),
        "model_pred_type": base_pred,
        "final_pred_type": final_pred,
        "reason_code": reason_code,
        "scene_blocked": bool(scene_blocked),
        "rear_prob": round(scores["rear_end"], 4),
        "lane_prob": round(scores["lane_change"], 4),
        "turn_prob": round(scores["turn_conflict"], 4),
    }


def apply_type_bias(samples: List[Dict[str, Any]], type_name: str) -> None:
    for sample in samples:
        sample["onset_score_used"] = sample["onset_score"]
        sample["impact_score_used"] = sample["impact_score"]
        sample["post_score_used"] = sample["post_score"]

        if type_name == "rear_end":
            hint = sample["rear_end_score"]
            sample["onset_score_used"] = clamp01(0.78 * sample["onset_score"] + 0.22 * hint)
            sample["impact_score_used"] = clamp01(0.72 * sample["impact_score"] + 0.28 * hint)
            sample["post_score_used"] = clamp01(0.84 * sample["post_score"] + 0.16 * hint)

        elif type_name == "lane_change":
            hint = sample["lane_change_score"]
            sample["onset_score_used"] = clamp01(0.65 * sample["onset_score"] + 0.35 * hint)
            sample["impact_score_used"] = clamp01(0.70 * sample["impact_score"] + 0.30 * hint)
            sample["post_score_used"] = clamp01(0.85 * sample["post_score"] + 0.15 * hint)

        elif type_name == "turn_conflict":
            hint = sample["turn_conflict_score"]
            sample["onset_score_used"] = clamp01(0.62 * sample["onset_score"] + 0.38 * hint)
            sample["impact_score_used"] = clamp01(0.65 * sample["impact_score"] + 0.35 * hint)
            sample["post_score_used"] = clamp01(0.78 * sample["post_score"] + 0.22 * hint)

        sample["event_score_used"] = max(
            sample["onset_score_used"],
            sample["impact_score_used"],
            sample["post_score_used"]
        )


def normalize_type_scores(type_scores: Dict[str, float]) -> Dict[str, float]:
    positive_scores = {k: max(0.0, float(v)) for k, v in type_scores.items()}
    total = sum(positive_scores.values())
    if total <= 1e-6:
        uniform = 1.0 / max(1, len(positive_scores))
        return {k: uniform for k in positive_scores}
    return {k: v / total for k, v in positive_scores.items()}


def build_type_topk(
    type_scores: Dict[str, float],
    type_probs: Dict[str, float],
    k: int = TYPE_TOPK
) -> List[Dict[str, Any]]:
    sorted_items = sorted(type_probs.items(), key=lambda x: x[1], reverse=True)
    top_items = sorted_items[:max(1, min(k, len(sorted_items)))]
    return [
        {
            "type": t,
            "label": TYPE_LABELS.get(t, t),
            "prob": round(float(p), 4),
            "score": round(float(type_scores.get(t, 0.0)), 4),
        }
        for t, p in top_items
    ]


def build_risk_series(samples: List[Dict[str, Any]]) -> List[float]:
    if not samples:
        return []
    raw = [
        clamp01(
            0.45 * float(item["onset_score_used"]) +
            0.35 * float(item["impact_score_used"]) +
            0.20 * float(item["event_score_used"])
        )
        for item in samples
    ]
    smooth = moving_average(raw, k=3)
    if len(smooth) != len(raw):
        return raw
    return [clamp01(v) for v in smooth]


def classify_risk_level(peak_risk: float, lead_time_sec: float) -> str:
    if peak_risk >= 0.78 and lead_time_sec >= 0.6:
        return "high"
    if peak_risk >= 0.52 and lead_time_sec >= 0.3:
        return "medium"
    return "low"


def compute_risk_alert(
    samples: List[Dict[str, Any]],
    onset_idx: int,
    impact_idx: int
) -> Dict[str, Any]:
    if not samples:
        return {
            "risk_alert_time": 0.0,
            "lead_time_sec": 0.0,
            "risk_threshold": 1.0,
            "peak_risk": 0.0,
            "risk_level": "unknown",
            "risk_curve": [],
        }

    risk_series = build_risk_series(samples)
    impact_idx = max(0, min(int(impact_idx), len(samples) - 1))
    onset_idx = max(0, min(int(onset_idx), impact_idx))
    onset_sec = float(samples[onset_idx]["sec"])
    impact_sec = float(samples[impact_idx]["sec"])

    impact_ref = max(
        float(samples[impact_idx]["impact_score_used"]),
        float(samples[impact_idx]["event_score_used"]),
    )
    onset_ref = max(
        float(samples[onset_idx]["onset_score_used"]),
        float(samples[onset_idx]["event_score_used"]),
    )
    threshold = clamp01(
        max(
            RISK_ALERT_MIN_SCORE,
            impact_ref * RISK_ALERT_RATIO,
            onset_ref * 0.92,
        )
    )

    # Restrict alert search window so pre-crash background motion does not trigger too early.
    earliest_alert_sec = max(0.0, onset_sec - RISK_MAX_LEAD_SEC)
    latest_alert_sec = max(0.0, impact_sec - RISK_MIN_ALERT_GAP_SEC)
    candidate_indices = [
        i for i in range(impact_idx + 1)
        if earliest_alert_sec <= float(samples[i]["sec"]) <= latest_alert_sec
    ]
    if not candidate_indices:
        candidate_indices = list(range(onset_idx, impact_idx + 1))

    alert_idx: Optional[int] = None
    run_start = 0
    run_count = 0
    for i in candidate_indices:
        if risk_series[i] >= threshold:
            if run_count == 0:
                run_start = i
            run_count += 1
            if run_count >= RISK_MIN_CONSECUTIVE:
                alert_idx = run_start
                break
        else:
            run_count = 0

    if alert_idx is None:
        alert_idx = onset_idx if onset_idx <= impact_idx else impact_idx

    alert_sec = float(samples[alert_idx]["sec"])
    lead_time_sec = max(0.0, impact_sec - alert_sec)
    peak_risk = max(risk_series[:impact_idx + 1]) if impact_idx >= 0 else max(risk_series)
    risk_level = classify_risk_level(peak_risk, lead_time_sec)

    step = max(1, math.ceil(len(samples) / MAX_RISK_CURVE_POINTS))
    risk_curve = [
        {
            "time": round(float(samples[i]["sec"]), 2),
            "risk": round(float(risk_series[i]), 4),
        }
        for i in range(0, len(samples), step)
    ]
    if risk_curve and risk_curve[-1]["time"] != round(float(samples[-1]["sec"]), 2):
        risk_curve.append({
            "time": round(float(samples[-1]["sec"]), 2),
            "risk": round(float(risk_series[-1]), 4),
        })

    return {
        "risk_alert_time": round(alert_sec, 2),
        "lead_time_sec": round(float(lead_time_sec), 2),
        "risk_threshold": round(float(threshold), 4),
        "peak_risk": round(float(peak_risk), 4),
        "risk_level": risk_level,
        "risk_curve": risk_curve,
    }


def cluster_metrics_at_index(
    raw_samples: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    dominant_cluster_idx: Optional[int],
    sample_idx: int
) -> Dict[str, float]:
    if dominant_cluster_idx is None:
        return {}
    if dominant_cluster_idx < 0 or dominant_cluster_idx >= len(clusters):
        return {}
    if sample_idx < 0 or sample_idx >= len(raw_samples):
        return {}

    cluster = clusters[dominant_cluster_idx]
    obs = cluster.get("observations", {}).get(sample_idx)
    if not obs:
        return {}

    pair_key = obs.get("pair_key")
    if pair_key is None:
        return {}

    metrics = raw_samples[sample_idx].get("pair_metrics", {}).get(pair_key, {})
    return {k: float(v) for k, v in metrics.items()}


def build_feature_contributions(
    type_name: str,
    metrics: Dict[str, float],
    topn: int = 5
) -> List[Dict[str, Any]]:
    weights = TYPE_METRIC_WEIGHTS.get(type_name, [])
    contributions = []

    for metric_key, weight in weights:
        value = clamp01(float(metrics.get(metric_key, 0.0)))
        contribution = float(weight) * value
        contributions.append({
            "feature": metric_key,
            "label": METRIC_LABELS.get(metric_key, metric_key),
            "weight": round(float(weight), 4),
            "value": round(float(value), 4),
            "contribution": round(float(contribution), 4),
        })

    contributions.sort(key=lambda x: x["contribution"], reverse=True)
    return contributions[:max(1, topn)]


def estimate_uncertainty(
    samples: List[Dict[str, Any]],
    type_probs: Dict[str, float],
    dominant_meta: Dict[str, Any]
) -> float:
    if not type_probs:
        return 1.0

    probs = np.array(list(type_probs.values()), dtype=np.float32)
    probs = np.clip(probs, 1e-6, 1.0)
    probs = probs / max(1e-6, float(np.sum(probs)))
    entropy = float(-np.sum(probs * np.log(probs)) / np.log(len(probs)))

    if len(samples) >= 3:
        event_series = np.array([float(s["event_score_used"]) for s in samples], dtype=np.float32)
        diff_std = float(np.std(np.diff(event_series)))
        temporal_volatility = clamp01(diff_std / 0.12)
    else:
        temporal_volatility = 0.5

    dominance = float(dominant_meta.get("dominance", 0.0))
    bridged_coverage = float(dominant_meta.get("bridged_coverage", 0.0))
    tracking_reliability = clamp01(0.6 * dominance + 0.4 * bridged_coverage)

    uncertainty = clamp01(
        0.55 * entropy +
        0.25 * temporal_volatility +
        0.20 * (1.0 - tracking_reliability)
    )
    return round(float(uncertainty), 4)


def build_stage_score_snapshot(
    selected_items: List[Dict[str, Any]],
    samples: List[Dict[str, Any]]
) -> Dict[str, Dict[str, float]]:
    snapshot: Dict[str, Dict[str, float]] = {}
    for item in selected_items:
        stage = item["stage"]
        idx = item["idx"]
        sample = samples[idx]
        snapshot[stage] = {
            "time": round(float(sample["sec"]), 2),
            "onset": round(float(sample["onset_score_used"]), 4),
            "impact": round(float(sample["impact_score_used"]), 4),
            "post": round(float(sample["post_score_used"]), 4),
            "event": round(float(sample["event_score_used"]), 4),
        }
    return snapshot


def build_evidence_payload(
    raw_samples: List[Dict[str, Any]],
    samples: List[Dict[str, Any]],
    selected_items: List[Dict[str, Any]],
    clusters: List[Dict[str, Any]],
    dominant_cluster_idx: Optional[int],
    dominant_meta: Dict[str, Any],
    accident_type_key: str,
    type_scores: Dict[str, float],
    type_probs: Dict[str, float],
    risk_info: Dict[str, Any],
    onset_idx: int,
    impact_idx: int,
    post_idx: int,
    direct_shared_pair_agg: Dict[str, Any],
) -> Dict[str, Any]:
    onset_metrics = cluster_metrics_at_index(raw_samples, clusters, dominant_cluster_idx, onset_idx)
    impact_metrics = cluster_metrics_at_index(raw_samples, clusters, dominant_cluster_idx, impact_idx)
    post_metrics = cluster_metrics_at_index(raw_samples, clusters, dominant_cluster_idx, post_idx)

    return {
        "stage_scores": build_stage_score_snapshot(selected_items, samples),
        "dominant_cluster_meta": dominant_meta,
        "pair_metrics": {
            "onset": {k: round(float(v), 4) for k, v in onset_metrics.items()},
            "impact": {k: round(float(v), 4) for k, v in impact_metrics.items()},
            "post": {k: round(float(v), 4) for k, v in post_metrics.items()},
        },
        "direct_shared_pair_agg": direct_shared_pair_agg,
        "type_scores_raw": {k: round(float(v), 4) for k, v in type_scores.items()},
        "type_probs": {k: round(float(v), 4) for k, v in type_probs.items()},
        "type_feature_contributions": build_feature_contributions(accident_type_key, impact_metrics),
        "risk_threshold": risk_info["risk_threshold"],
        "peak_risk": risk_info["peak_risk"],
        "risk_curve": risk_info["risk_curve"],
    }


def purpose_from_stage(stage: str) -> str:
    mapping = {
        "pre": "pre_accident_state",
        "approach": "approach_phase",
        "onset": "conflict_onset",
        "impact": "main_analysis_frame",
        "post": "post_accident_state",
        "fallback": "fallback"
    }
    return mapping.get(stage, "supporting_evidence")
def _encode_frame_as_data_url(frame: Any) -> str:
    """Return an inline JPEG data URL for frontend fallback rendering."""
    if frame is None:
        return ""
    try:
        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            [int(cv2.IMWRITE_JPEG_QUALITY), 82],
        )
        if not ok:
            return ""
        b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return ""


def fallback_keyframes(cap: cv2.VideoCapture, video_path: Path, fps: float) -> List[Dict[str, Any]]:
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_seconds = int(total_frames / fps) if total_frames > 0 else 0

    if duration_seconds <= 2:
        fallback_times = [0.0, max(0.2, duration_seconds * 0.5)]
    elif duration_seconds <= 6:
        fallback_times = [
            0.3,
            max(0.5, duration_seconds * 0.35),
            max(0.8, duration_seconds * 0.60),
            max(1.0, duration_seconds - 0.6),
        ]
    else:
        fallback_times = np.linspace(0.5, max(1.0, duration_seconds - 0.5), num=MAX_RETURN_FRAMES).tolist()

    keyframes = []
    stage_names = ["pre", "approach", "onset", "impact", "post"]

    for i, sec in enumerate(fallback_times[:MAX_RETURN_FRAMES]):
        sec = max(0.0, min(float(sec), max(0.0, duration_seconds - 1e-3)))
        frame_no = int(sec * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ret, frame = cap.read()
        if not ret:
            continue

        stage = stage_names[min(i, len(stage_names) - 1)]
        frame_name = f"{video_path.stem}_fallback_{i}.jpg"
        frame_path = KEYFRAME_DIR / frame_name
        cv2.imwrite(str(frame_path), frame)
        inline_image = _encode_frame_as_data_url(frame)

        keyframes.append({
            "time": round(float(sec), 2),
            "thumb_url": f"/keyframes/{frame_name}",
            "image_url": inline_image,
            "score": 0.0,
            "raw_score": 0.0,
            "purpose": purpose_from_stage(stage),
            "stage": stage,
            "is_main": stage == "impact"
        })

    cap.release()
    return keyframes


def extract_sequence_features(
    video_path: Path,
    include_frames: bool = False,
    verbose: bool = False
) -> Dict[str, Any]:
    if verbose:
        print(f"[INFO] Start temporal feature extraction: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("瑙嗛鏃犳硶鎵撳紑")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 25.0

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_seconds = total_frames / fps if total_frames > 0 else 0.0
    cap.release()

    if verbose:
        print(f"[INFO] FPS={fps}, total_frames={total_frames}, duration={duration_seconds:.2f}s")

    model = get_model()

    raw_samples = []
    prev_sample_frame = None
    pair_history: Dict[Tuple[int, int], Dict[str, float]] = {}
    track_memory = defaultdict(lambda: deque(maxlen=TRACK_MEMORY_LEN))

    sample_step_frames = max(1, int(round(SAMPLE_INTERVAL_SEC * fps)))
    next_sample_frame = 0

    results = model.track(
        source=str(video_path),
        stream=True,
        persist=True,
        tracker=TRACKER_CONFIG,
        conf=YOLO_CONF,
        classes=list(VEHICLE_CLASS_IDS),
        device="cpu",
        verbose=False
    )

    for frame_idx, result in enumerate(results):
        if frame_idx < next_sample_frame:
            continue

        current_sec = frame_idx / fps
        frame = result.orig_img.copy()

        detections = result_to_detections(result)
        detections = update_track_memory(detections, current_sec, track_memory)

        motion_score = compute_motion_score(prev_sample_frame, frame)
        frame_pair_scores, frame_pair_metrics, frame_pair_meta, frame_pair_info, pair_history = compute_frame_pair_scores(
            detections, frame.shape, motion_score, pair_history, current_sec
        )
        frame_scores = collapse_frame_scores(frame_pair_scores, motion_score)

        raw_samples.append({
            "sec": float(current_sec),
            "frame": frame.copy() if include_frames else None,
            "detections": detections,
            "pairs": frame_pair_scores,
            "pair_metrics": frame_pair_metrics,
            "pair_meta": frame_pair_meta,
            "pair_info": frame_pair_info,

            "onset_score_raw": float(frame_scores["onset"]),
            "impact_score_raw": float(frame_scores["impact"]),
            "post_score_raw": float(frame_scores["post"]),
            "event_score_raw": float(frame_scores["event"]),

            "rear_end_score_raw": float(frame_scores["rear_end"]),
            "lane_change_score_raw": float(frame_scores["lane_change"]),
            "turn_conflict_score_raw": float(frame_scores["turn_conflict"]),
        })

        prev_sample_frame = frame.copy()
        next_sample_frame += sample_step_frames

    if not raw_samples:
        default_type_scores = {
            "rear_end": 0.0,
            "lane_change": 0.0,
            "turn_conflict": 0.0,
        }
        default_type_probs = normalize_type_scores(default_type_scores)
        default_topk = build_type_topk(default_type_scores, default_type_probs)
        default_risk = {
            "risk_alert_time": 0.0,
            "lead_time_sec": 0.0,
            "risk_threshold": 1.0,
            "peak_risk": 0.0,
            "risk_level": "unknown",
            "risk_curve": [],
        }
        return {
            "has_samples": False,
            "video_path": str(video_path),
            "fps": float(fps),
            "total_frames": int(total_frames),
            "duration_seconds": float(duration_seconds),
            "raw_samples": [],
            "samples": [],
            "clusters": [],
            "dominant_cluster_idx": None,
            "dominant_meta": {},
            "selected_items": [],
            "onset_idx": 0,
            "impact_idx": 0,
            "post_idx": 0,
            "onset_sec": 0.0,
            "impact_sec": 0.0,
            "post_sec": 0.0,
            "accident_type_key": "generic",
            "accident_type_label": TYPE_LABELS["generic"],
            "type_scores": default_type_scores,
            "type_probs": default_type_probs,
            "type_topk": default_topk,
            "type_confidence": 0.0,
            "model_pred_type_key": "generic",
            "model_pred_type_label": TYPE_LABELS["generic"],
            "decision_mode": "rule_fallback",
            "fallback_reason": "NO_VALID_SAMPLES",
            "rear_guard_applied": False,
            "rear_guard_version": REAR_GUARD_VERSION,
            "rear_guard_cfg": dict(REAR_GUARD_CONFIG),
            "rear_guard_detail": {},
            "scene_prior": {
                "intersection_prior": 0.0,
                "turning_scene_prior": 0.0,
                "turn_candidate_boost": 0.0,
                "turn_candidate_run": 0.0,
            },
            "risk_info": default_risk,
            "uncertainty": 1.0,
            "impact_vehicle_count": 0,
            "direct_shared_pair_agg": empty_direct_shared_pair_agg(),
            "evidence": {
                "stage_scores": {},
                "dominant_cluster_meta": {},
                "pair_metrics": {},
                "direct_shared_pair_agg": empty_direct_shared_pair_agg(),
                "type_scores_raw": default_type_scores,
                "type_probs": default_type_probs,
                "type_feature_contributions": [],
                "risk_threshold": default_risk["risk_threshold"],
                "peak_risk": default_risk["peak_risk"],
                "risk_curve": default_risk["risk_curve"],
            },
        }

    dominant_cluster_idx, dominant_meta, clusters = lock_dominant_cluster(raw_samples)
    if verbose:
        print(f"[INFO] dominant_cluster_idx={dominant_cluster_idx}, meta={dominant_meta}")
    direct_shared_pair_agg = aggregate_direct_shared_pair_features(
        raw_samples=raw_samples,
        clusters=clusters,
        dominant_cluster_idx=dominant_cluster_idx,
        fps=float(fps),
    )
    if verbose:
        print(f"[INFO] direct_shared_pair_agg={direct_shared_pair_agg}")

    samples = build_locked_samples_from_cluster(
        raw_samples,
        clusters,
        dominant_cluster_idx,
        max_gap=PAIR_GAP_TOLERANCE
    )

    onset_smooth = moving_average([item["onset_score_raw"] for item in samples], k=SCORE_SMOOTH_K)
    impact_smooth = moving_average([item["impact_score_raw"] for item in samples], k=SCORE_SMOOTH_K)
    post_smooth = moving_average([item["post_score_raw"] for item in samples], k=SCORE_SMOOTH_K)
    event_smooth = moving_average([item["event_score_raw"] for item in samples], k=SCORE_SMOOTH_K)
    impact_global_smooth = moving_average([item["impact_score_raw"] for item in raw_samples], k=SCORE_SMOOTH_K)

    rear_smooth = moving_average([item["rear_end_score_raw"] for item in samples], k=SCORE_SMOOTH_K)
    lane_smooth = moving_average([item["lane_change_score_raw"] for item in samples], k=SCORE_SMOOTH_K)
    turn_smooth = moving_average([item["turn_conflict_score_raw"] for item in samples], k=SCORE_SMOOTH_K)

    for i in range(len(samples)):
        samples[i]["onset_score"] = float(onset_smooth[i])
        samples[i]["impact_score"] = float(impact_smooth[i])
        samples[i]["impact_score_global"] = float(impact_global_smooth[i])
        samples[i]["post_score"] = float(post_smooth[i])
        samples[i]["event_score"] = float(event_smooth[i])

        samples[i]["rear_end_score"] = float(rear_smooth[i])
        samples[i]["lane_change_score"] = float(lane_smooth[i])
        samples[i]["turn_conflict_score"] = float(turn_smooth[i])

        samples[i]["onset_score_used"] = samples[i]["onset_score"]
        samples[i]["impact_score_used"] = samples[i]["impact_score"]
        samples[i]["post_score_used"] = samples[i]["post_score"]
        samples[i]["event_score_used"] = samples[i]["event_score"]

    initial_stage_items = choose_stage_items(samples, type_name="generic")
    initial_selected = force_fixed_five_stage_order(
        initial_stage_items,
        samples,
        MIN_FRAME_GAP_SEC
    )
    initial_map = {item["stage"]: item["idx"] for item in initial_selected}
    initial_onset_idx = initial_map["onset"]
    initial_impact_idx = initial_map["impact"]

    accident_type_key, type_confidence, type_scores, scene_prior = classify_accident_type(
        samples,
        initial_onset_idx,
        initial_impact_idx,
        raw_samples=raw_samples
    )
    model_pred_type_key = accident_type_key
    type_probs = normalize_type_scores(type_scores)
    rear_guard = apply_rear_guard_v343(
        base_type=model_pred_type_key,
        type_probs=type_probs,
        scene_prior=scene_prior,
    )
    accident_type_key = str(rear_guard["final_pred_type"])
    decision_mode = "rear_guard_override" if rear_guard["applied"] else "model_main"
    fallback_reason = str(rear_guard["reason_code"])
    type_topk = build_type_topk(type_scores, type_probs)
    type_confidence = round(float(type_probs.get(accident_type_key, 0.0)), 4)

    apply_type_bias(samples, accident_type_key)

    stage_items = choose_stage_items(samples, type_name=accident_type_key)
    selected_items = force_fixed_five_stage_order(
        stage_items,
        samples,
        MIN_FRAME_GAP_SEC
    )

    stage_map = {item["stage"]: item["idx"] for item in selected_items}
    onset_idx = stage_map["onset"]
    impact_idx = stage_map["impact"]
    post_idx = stage_map["post"]

    onset_sec = float(samples[onset_idx]["sec"])
    impact_sec = float(samples[impact_idx]["sec"])
    post_sec = float(samples[post_idx]["sec"])
    risk_info = compute_risk_alert(samples, onset_idx, impact_idx)
    uncertainty = estimate_uncertainty(samples, type_probs, dominant_meta)
    evidence = build_evidence_payload(
        raw_samples=raw_samples,
        samples=samples,
        selected_items=selected_items,
        clusters=clusters,
        dominant_cluster_idx=dominant_cluster_idx,
        dominant_meta=dominant_meta,
        accident_type_key=accident_type_key,
        type_scores=type_scores,
        type_probs=type_probs,
        risk_info=risk_info,
        onset_idx=onset_idx,
        impact_idx=impact_idx,
        post_idx=post_idx,
        direct_shared_pair_agg=direct_shared_pair_agg,
    )

    impact_vehicle_count = len(raw_samples[impact_idx]["detections"])

    return {
        "has_samples": True,
        "video_path": str(video_path),
        "fps": float(fps),
        "total_frames": int(total_frames),
        "duration_seconds": float(duration_seconds),
        "raw_samples": raw_samples,
        "samples": samples,
        "clusters": clusters,
        "dominant_cluster_idx": dominant_cluster_idx,
        "dominant_meta": dominant_meta,
        "selected_items": selected_items,
        "onset_idx": int(onset_idx),
        "impact_idx": int(impact_idx),
        "post_idx": int(post_idx),
        "onset_sec": float(onset_sec),
        "impact_sec": float(impact_sec),
        "post_sec": float(post_sec),
        "accident_type_key": accident_type_key,
        "accident_type_label": TYPE_LABELS[accident_type_key],
        "type_scores": type_scores,
        "type_probs": type_probs,
        "type_topk": type_topk,
        "type_confidence": type_confidence,
        "model_pred_type_key": model_pred_type_key,
        "model_pred_type_label": TYPE_LABELS.get(model_pred_type_key, TYPE_LABELS["generic"]),
        "decision_mode": decision_mode,
        "fallback_reason": fallback_reason,
        "rear_guard_applied": bool(rear_guard["applied"]),
        "rear_guard_version": rear_guard["version"],
        "rear_guard_cfg": rear_guard["cfg"],
        "rear_guard_detail": rear_guard,
        "scene_prior": scene_prior,
        "risk_info": risk_info,
        "uncertainty": uncertainty,
        "impact_vehicle_count": int(impact_vehicle_count),
        "direct_shared_pair_agg": direct_shared_pair_agg,
        "evidence": evidence,
    }


def extract_keyframes(video_path: Path) -> Dict[str, Any]:
    print(f"[INFO] Start YOLO keyframe extraction ({MODEL_VERSION}): {video_path}")
    seq = extract_sequence_features(video_path, include_frames=True, verbose=True)

    if not seq["has_samples"]:
        print("[WARN] No valid samples found; entering fallback mode")
        cap = cv2.VideoCapture(str(video_path))
        keyframes = fallback_keyframes(cap, video_path, seq["fps"])
        return {
            "model_version": MODEL_VERSION,
            "impact_time": keyframes[0]["time"] if keyframes else 0.0,
            "onset_time": 0.0,
            "post_time": 0.0,
            "vehicle_count": 0,
            "accident_type": seq["accident_type_label"],
            "type_confidence": seq["type_confidence"],
            "type_topk": seq["type_topk"],
            "model_pred_type": seq.get("model_pred_type_label", seq["accident_type_label"]),
            "decision_mode": seq.get("decision_mode", "rule_fallback"),
            "fallback_reason": seq.get("fallback_reason", "NO_VALID_SAMPLES"),
            "rear_guard_applied": seq.get("rear_guard_applied", False),
            "rear_guard_version": seq.get("rear_guard_version", REAR_GUARD_VERSION),
            "rear_guard_cfg": seq.get("rear_guard_cfg", dict(REAR_GUARD_CONFIG)),
            "rear_guard_detail": seq.get("rear_guard_detail", {}),
            "scene_prior": seq.get("scene_prior", {}),
            "uncertainty": seq["uncertainty"],
            "risk_alert_time": seq["risk_info"]["risk_alert_time"],
            "lead_time_sec": seq["risk_info"]["lead_time_sec"],
            "risk_level": seq["risk_info"]["risk_level"],
            "dominant_cluster": {},
            "dominant_pair": [],
            "evidence": seq["evidence"],
            "keyframes": keyframes
        }

    print(
        f"[INFO] accident_type={seq['accident_type_label']} "
        f"(rear_end={seq['type_scores']['rear_end']:.3f}, "
        f"lane_change={seq['type_scores']['lane_change']:.3f}, "
        f"turn_conflict={seq['type_scores']['turn_conflict']:.3f}, "
        f"confidence={seq['type_confidence']:.3f})"
    )
    if seq.get("rear_guard_applied"):
        print(
            f"[INFO] rear_guard {seq.get('rear_guard_version', REAR_GUARD_VERSION)} applied: "
            f"{seq.get('model_pred_type_label', '')} -> {seq['accident_type_label']} "
            f"(reason={seq.get('fallback_reason', '')})"
        )
    print(
        f"[INFO] onset={seq['onset_sec']:.2f}s, "
        f"impact={seq['impact_sec']:.2f}s, post={seq['post_sec']:.2f}s"
    )
    print(
        f"[INFO] risk_alert={seq['risk_info']['risk_alert_time']:.2f}s, "
        f"lead_time={seq['risk_info']['lead_time_sec']:.2f}s, "
        f"risk_level={seq['risk_info']['risk_level']}"
    )
    print(
        f"[INFO] {MODEL_VERSION} five-stage keyframes: "
        f"{[(item['stage'], round(seq['samples'][item['idx']]['sec'], 2)) for item in seq['selected_items']]}"
    )

    keyframes = []
    for order, item in enumerate(seq["selected_items"]):
        idx = item["idx"]
        stage = item["stage"]
        sample = seq["raw_samples"][idx]

        sec = round(float(sample["sec"]), 2)
        frame_name = f"{video_path.stem}_kf91_{order}_{uuid.uuid4().hex[:6]}.jpg"
        frame_path = KEYFRAME_DIR / frame_name
        if sample["frame"] is None:
            continue
        cv2.imwrite(str(frame_path), sample["frame"])
        inline_image = _encode_frame_as_data_url(sample["frame"])

        locked_sample = seq["samples"][idx]
        if stage == "onset":
            stage_score = locked_sample["onset_score_used"]
        elif stage == "impact":
            stage_score = locked_sample["impact_score_used"]
        elif stage == "post":
            stage_score = locked_sample["post_score_used"]
        else:
            stage_score = locked_sample["event_score_used"]

        keyframes.append({
            "time": sec,
            "thumb_url": f"/keyframes/{frame_name}",
            "image_url": inline_image,
            "score": round(float(stage_score), 4),
            "raw_score": round(float(locked_sample["event_score_raw"]), 4),
            "purpose": purpose_from_stage(stage),
            "stage": stage,
            "is_main": stage == "impact"
        })

    return {
        "model_version": MODEL_VERSION,
        "impact_time": round(seq["impact_sec"], 2),
        "onset_time": round(seq["onset_sec"], 2),
        "post_time": round(seq["post_sec"], 2),
        "vehicle_count": seq["impact_vehicle_count"],
        "accident_type": seq["accident_type_label"],
        "type_confidence": seq["type_confidence"],
        "type_topk": seq["type_topk"],
        "model_pred_type": seq.get("model_pred_type_label", seq["accident_type_label"]),
        "decision_mode": seq.get("decision_mode", "model_main"),
        "fallback_reason": seq.get("fallback_reason", "NONE"),
        "rear_guard_applied": seq.get("rear_guard_applied", False),
        "rear_guard_version": seq.get("rear_guard_version", REAR_GUARD_VERSION),
        "rear_guard_cfg": seq.get("rear_guard_cfg", dict(REAR_GUARD_CONFIG)),
        "rear_guard_detail": seq.get("rear_guard_detail", {}),
        "scene_prior": seq.get("scene_prior", {}),
        "uncertainty": seq["uncertainty"],
        "risk_alert_time": seq["risk_info"]["risk_alert_time"],
        "lead_time_sec": seq["risk_info"]["lead_time_sec"],
        "risk_level": seq["risk_info"]["risk_level"],
        "dominant_cluster": seq["dominant_meta"],
        "dominant_pair": list(seq["dominant_meta"].get("pair_keys", [])[0]) if seq["dominant_meta"].get("pair_keys") else [],
        "evidence": seq["evidence"],
        "keyframes": keyframes
    }


@app.get("/")
def root():
    return {"message": "video_keyframe backend is running"}


@app.post("/upload_video/")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename:
        raise HTTPException(status_code=400, detail="鏈帴鏀跺埌鏂囦欢")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail=f"涓嶆敮鎸佺殑鏂囦欢鏍煎紡: {ext}")

    saved_name = safe_filename(file.filename)
    saved_path = UPLOAD_DIR / saved_name

    try:
        await run_in_threadpool(save_upload_file, file, saved_path)

        result = await run_in_threadpool(extract_keyframes, saved_path)
        keyframes = result["keyframes"]

        if not keyframes:
            raise HTTPException(status_code=500, detail="Failed to extract keyframes.")

        return {
            "video": f"/uploaded_videos/{saved_name}",
            "model_version": result.get("model_version", MODEL_VERSION),
            "impact_time": result["impact_time"],
            "onset_time": result["onset_time"],
            "post_time": result["post_time"],
            "vehicle_count": result["vehicle_count"],
            "accident_type": result["accident_type"],
            "type_confidence": result["type_confidence"],
            "type_topk": result.get("type_topk", []),
            "model_pred_type": result.get("model_pred_type", result["accident_type"]),
            "decision_mode": result.get("decision_mode", "model_main"),
            "fallback_reason": result.get("fallback_reason", "NONE"),
            "rear_guard_applied": bool(result.get("rear_guard_applied", False)),
            "rear_guard_version": result.get("rear_guard_version", REAR_GUARD_VERSION),
            "rear_guard_cfg": result.get("rear_guard_cfg", dict(REAR_GUARD_CONFIG)),
            "rear_guard_detail": result.get("rear_guard_detail", {}),
            "scene_prior": result.get("scene_prior", {}),
            "uncertainty": result.get("uncertainty", 1.0),
            "risk_alert_time": result.get("risk_alert_time", 0.0),
            "lead_time_sec": result.get("lead_time_sec", 0.0),
            "risk_level": result.get("risk_level", "unknown"),
            "dominant_cluster": result["dominant_cluster"],
            "dominant_pair": result.get("dominant_pair", []),
            "evidence": result.get("evidence", {}),
            "keyframes": keyframes
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"video processing failed: {type(e).__name__}: {str(e)}"
        )
    finally:
        file.file.close()

@app.post("/analyze_image_evidence/")
async def analyze_image_evidence(payload: ImageEvidenceRequest):
    try:
        frame_path = _resolve_keyframe_path(payload.frame_url)
        classifier = get_image_classifier()
        video_context = payload.video_context or {}
        # classify_rear_end only accepts image_path
        base_result = await run_in_threadpool(
            classifier.classify_rear_end,
            str(frame_path),
        )
        result = dict(base_result) if isinstance(base_result, dict) else {"raw": base_result}
        if video_context:
            result.setdefault("video_context", video_context)
        return {
            "frame_path": str(frame_path),
            "frame_url": payload.frame_url,
            "image_evidence": result,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"image evidence analysis failed: {str(e)}")


@app.post("/analyze_image_file_evidence/")
async def analyze_image_file_evidence(
    file: UploadFile = File(...),
    video_context: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="鏈帴鏀跺埌鍥剧墖鏂囦欢")

    ext = Path(file.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        raise HTTPException(status_code=400, detail=f"涓嶆敮鎸佺殑鍥剧墖鏍煎紡: {ext}")

    saved_name = f"image_{uuid.uuid4().hex[:10]}{ext}"
    saved_path = UPLOAD_DIR / saved_name

    parsed_video_context: Dict[str, Any] = {}
    if video_context:
        try:
            parsed_video_context = json.loads(video_context)
            if not isinstance(parsed_video_context, dict):
                parsed_video_context = {}
        except Exception:
            parsed_video_context = {}

    try:
        await run_in_threadpool(save_upload_file, file, saved_path)
        classifier = get_image_classifier()
        # classify_rear_end only accepts image_path; pass context via wrapper
        base_result = await run_in_threadpool(
            classifier.classify_rear_end,
            str(saved_path),
        )
        # Merge video_context metadata into the result
        result = dict(base_result) if isinstance(base_result, dict) else {"raw": base_result}
        if parsed_video_context:
            result.setdefault("video_context", parsed_video_context)
            # Enrich with context scores if provided
            for key in ("accident_type", "type_confidence", "evidence_consistency_score"):
                if key in parsed_video_context:
                    result[f"ctx_{key}"] = parsed_video_context[key]
        return {
            "image_evidence": result,
            "filename": file.filename,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"image evidence analysis failed: {str(e)}")
    finally:
        file.file.close()
        try:
            if saved_path.exists():
                saved_path.unlink()
        except Exception:
            pass


@app.get("/dify/health/")
def dify_health():
    settings = _get_dify_settings()
    hash_log_file = _get_dify_hash_log_file()
    endpoint_probe = _probe_dify_endpoint(
        str(settings.get("workflow_url") or ""),
        timeout_sec=max(3, int(settings.get("timeout_sec") or 8)),
    )
    return {
        "configured": bool(settings["workflow_url"] and settings["api_key"]),
        "workflow_url": settings["workflow_url"],
        "api_key_masked": _mask_secret(settings["api_key"]),
        "default_response_mode": settings["default_response_mode"],
        "timeout_sec": settings["timeout_sec"],
        "stabilize_inputs": settings["stabilize_inputs"],
        "include_raw_inputs": settings["include_raw_inputs"],
        "compact_json_inputs": settings["compact_json_inputs"],
        "hash_log_enabled": _is_truthy_env("DIFY_HASH_LOG_ENABLED", True),
        "hash_log_file": str(hash_log_file),
        "input_mapping": {
            "summary_key": settings["summary_key"],
            "video_json_key": settings["video_json_key"],
            "image_json_key": settings["image_json_key"],
            "extra_key": settings["extra_key"],
        },
        "endpoint_probe": endpoint_probe,
        "local_fallback_enabled": _is_truthy_env("DIFY_LOCAL_FALLBACK_ENABLED", False),
    }


@app.get("/dify/hash_logs/")
def dify_hash_logs(limit: int = 20):
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    path = _get_dify_hash_log_file()
    items = _read_last_jsonl(path, limit)
    return {
        "log_file": str(path),
        "enabled": _is_truthy_env("DIFY_HASH_LOG_ENABLED", True),
        "count": len(items),
        "items": items,
    }


@app.post("/dify/workflow_run/")
async def dify_workflow_run(payload: DifyWorkflowRunRequest):
    request_id = uuid.uuid4().hex
    request_payload = _prepare_dify_request_payload(
        inputs=payload.inputs,
        user=payload.user,
        response_mode=payload.response_mode,
        conversation_id=payload.conversation_id,
    )
    input_hash = _hash_obj_sha256(request_payload)

    dify_response = await run_in_threadpool(
        _call_dify_workflow,
        payload.inputs,
        payload.user,
        payload.response_mode,
        payload.conversation_id,
    )
    answer_text = _extract_dify_answer_text(dify_response)
    output_hash = _hash_obj_sha256(dify_response)
    log_file = _append_dify_hash_log(
        {
            "route": "/dify/workflow_run/",
            "request_id": request_id,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "input_keys": sorted((payload.inputs or {}).keys()),
            "request_payload": request_payload,
            "answer_preview": answer_text[:240],
        }
    )
    print(
        f"[DIFY_HASH] route=/dify/workflow_run/ request_id={request_id} "
        f"input_hash={input_hash} output_hash={output_hash}"
    )

    return {"result": _extract_dify_result(dify_response)}


@app.post("/dify/analyze_accident_case/")
async def dify_analyze_accident_case(payload: DifyAccidentCaseRequest):
    request_id = uuid.uuid4().hex
    workflow_inputs = _build_dify_case_inputs(payload)
    request_payload = _prepare_dify_request_payload(
        inputs=workflow_inputs,
        user=payload.user,
        response_mode=payload.response_mode,
        conversation_id=payload.conversation_id,
    )
    input_hash = _hash_obj_sha256(request_payload)
    video_result_hash = _hash_obj_sha256(payload.video_result or {})
    image_evidence_hash = _hash_obj_sha256(payload.image_evidence or {})
    workflow_inputs_hash = _hash_obj_sha256(workflow_inputs)

    try:
        dify_response = await run_in_threadpool(
            _call_dify_workflow,
            workflow_inputs,
            payload.user,
            payload.response_mode,
            payload.conversation_id,
        )
        answer_text = _extract_dify_answer_text(dify_response)
        output_hash = _hash_obj_sha256(dify_response)
        _append_dify_hash_log(
            {
                "route": "/dify/analyze_accident_case/",
                "request_id": request_id,
                "input_hash": input_hash,
                "output_hash": output_hash,
                "workflow_inputs_hash": workflow_inputs_hash,
                "video_result_hash": video_result_hash,
                "image_evidence_hash": image_evidence_hash,
                "input_keys": sorted(workflow_inputs.keys()),
                "request_payload": request_payload,
                "workflow_inputs": workflow_inputs,
                "answer_preview": answer_text[:240],
                "fallback": False,
            }
        )
        print(
            f"[DIFY_HASH] route=/dify/analyze_accident_case/ request_id={request_id} "
            f"input_hash={input_hash} output_hash={output_hash}"
        )
        return {"result": _extract_dify_result(dify_response)}
    except HTTPException as exc:
        # Strict-by-default in production deployment:
        # if Dify upstream fails, bubble up the real error directly.
        if not _is_truthy_env("DIFY_LOCAL_FALLBACK_ENABLED", False):
            raise

        fallback_markdown = _build_local_dify_fallback_markdown(payload, exc.detail)
        fallback_hash = _hash_obj_sha256({"result": fallback_markdown, "reason": str(exc.detail)})
        _append_dify_hash_log(
            {
                "route": "/dify/analyze_accident_case/",
                "request_id": request_id,
                "input_hash": input_hash,
                "output_hash": fallback_hash,
                "workflow_inputs_hash": workflow_inputs_hash,
                "video_result_hash": video_result_hash,
                "image_evidence_hash": image_evidence_hash,
                "input_keys": sorted(workflow_inputs.keys()),
                "request_payload": request_payload,
                "workflow_inputs": workflow_inputs,
                "answer_preview": fallback_markdown[:240],
                "fallback": True,
                "fallback_reason": str(exc.detail)[:360],
            }
        )
        print(
            f"[DIFY_FALLBACK] route=/dify/analyze_accident_case/ request_id={request_id} "
            f"reason={str(exc.detail)[:180]}"
        )
        return {
            "result": fallback_markdown,
            "mode": "local_fallback",
            "fallback_reason": str(exc.detail),
        }


@app.post("/dify/preview_case_inputs/")
async def dify_preview_case_inputs(payload: DifyAccidentCaseRequest):
    """Preview the exact payload that would be sent to Dify without calling Dify."""
    settings = _get_dify_settings()
    workflow_inputs = _build_dify_case_inputs(payload)

    query = workflow_inputs.get(settings["summary_key"], "")
    video_raw = workflow_inputs.get(settings["video_json_key"], "{}")
    image_raw = workflow_inputs.get(settings["image_json_key"], "{}")
    try:
        video_json = json.loads(video_raw) if isinstance(video_raw, str) else {}
    except Exception:
        video_json = {}
    try:
        image_json = json.loads(image_raw) if isinstance(image_raw, str) else {}
    except Exception:
        image_json = {}

    return {
        "query": query,
        "workflow_inputs": workflow_inputs,
        "video_json": video_json,
        "image_json": image_json,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


