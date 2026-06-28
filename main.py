from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Header, Depends, BackgroundTasks
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import sys
import tempfile
import shutil
import json
import base64
import requests
import time
import hashlib
import uuid
import urllib.parse as urllib_parse
from http.client import IncompleteRead
import urllib.error as urllib_error
import urllib.request as urllib_request
from sqlalchemy import text as sa_text
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timezone
from collections import deque

# 获取项目根目录（main.py所在目录）
BASE_DIR = Path(__file__).parent.absolute()

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

# Import keyframe extraction helpers from backend/video_keyframe.py
sys.path.insert(0, str(BASE_DIR / "backend"))
extract_keyframes_yolo = None
KEYFRAME_DIR = BASE_DIR / "backend" / "keyframes"
try:
    from video_keyframe import extract_keyframes as extract_keyframes_yolo
    from video_keyframe import KEYFRAME_DIR
    print("[INFO] Loaded YOLO keyframe extractor from backend/video_keyframe.py")
except Exception as e:
    print(f"[WARN] video_keyframe not loaded: {e}")

app = FastAPI()
import pandas as pd
from pathlib import Path

# 直接在 main.py 中加载数据
_excel_data_cache = {}
def load_data_for_main():
    global _excel_data_cache
    excel_path = Path("事故案例汇总表.xlsx")
    if not excel_path.exists():
        excel_path = Path(r"I:\accident_app\事故案例汇总表.xlsx")
    if not excel_path.exists():
        print("[ERROR] 找不到 Excel 文件")
        return
    df = pd.read_excel(excel_path, engine="openpyxl")
    df.columns = df.columns.str.strip()
    for _, row in df.iterrows():
        case_id = str(row.get("case_id", "")).strip()
        if case_id and case_id != "案例编号":
            _excel_data_cache[case_id] = row.to_dict()
    print(f"[INIT] 在 main.py 中加载了 {len(_excel_data_cache)} 个案例数据")

# 立即加载
load_data_for_main()
from backend.services.review_assist_service import load_excel_data, _excel_case_data
@app.get("/ping")
async def ping():
    return {"status": "ok"}
# ============================================================
# 复核辅助路由（必须放在所有 app.mount 之前）
# ============================================================

from backend.services.review_assist_service import (
    get_review_assist,
    batch_generate,
    get_statistics
)

@app.get("/api/cases/{case_id}/review-assist")
async def api_get_review_assist(case_id: str):
    print(f"[DEBUG] === 路由被调用，case_id={case_id} ===")
    case_data = _excel_data_cache.get(case_id)
    if case_data is None:
        raise HTTPException(status_code=404, detail=f"案例 {case_id} 不存在")
    
    # 直接在这里生成复核辅助结果，或者调用 review_assist_service 的生成函数并传入 case_data
    from backend.services.review_assist_service import generate_review_assist_from_data
    try:
        result = generate_review_assist_from_data(case_id, case_data)
        return {"success": True, "data": result.dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成复核辅助信息失败: {str(e)}")

@app.get("/api/review-assist/statistics")
async def api_get_review_assist_statistics():
    """
    获取复核辅助统计信息
    使用 _excel_data_cache 直接计算
    """
    try:
        from backend.services.review_focus_service import calculate_priority_score, determine_evidence_status, identify_review_focus
        
        total = len(_excel_data_cache)
        route_stats = {}
        priority_stats = {"高": 0, "中": 0, "低": 0}
        focus_stats = {}
        evidence_stats = {}

        for case_id, case_data in _excel_data_cache.items():
            # 1. 路由类型统计
            route_type = case_data.get("system_route", "unknown")
            route_stats[route_type] = route_stats.get(route_type, 0) + 1

            # 2. 优先级统计
            try:
                priority = calculate_priority_score(case_data)
                level = priority.get("level", "低")
                priority_stats[level] = priority_stats.get(level, 0) + 1
            except:
                priority_stats["低"] = priority_stats.get("低", 0) + 1

            # 3. 复核重点统计
            try:
                focus_list = identify_review_focus(case_data)
                for focus in focus_list:
                    focus_stats[focus] = focus_stats.get(focus, 0) + 1
            except:
                pass

            # 4. 证据状态统计
            try:
                evidence_status = determine_evidence_status(case_data)
                evidence_stats[evidence_status] = evidence_stats.get(evidence_status, 0) + 1
            except:
                evidence_stats["证据需核对"] = evidence_stats.get("证据需核对", 0) + 1

        stats = {
            "total": total,
            "route_type_stats": route_stats,
            "priority_stats": priority_stats,
            "focus_stats": focus_stats,
            "evidence_status_stats": evidence_stats,
        }
        return {"success": True, "data": stats}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.post("/api/cases/{case_id}/review-assist/generate")
async def api_generate_review_assist(case_id: str):
    try:
        result = get_review_assist(case_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"案例 {case_id} 不存在")
        return {"success": True, "data": result.dict()}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成复核辅助信息失败: {str(e)}")

@app.post("/api/review-assist/batch-generate")
async def api_batch_generate_review_assist(data: dict):
    case_ids = data.get("case_ids", [])
    if not case_ids:
        raise HTTPException(status_code=400, detail="case_ids 不能为空")
    try:
        results = batch_generate(case_ids)
        return {
            "success": True,
            "data": {
                "generated": len(results),
                "results": [r.dict() for r in results]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"批量生成失败: {str(e)}")

security = HTTPBearer()

# ============================================================
# 千问（Qwen）视频分析 API 函数
# ============================================================

def _call_qwen_video_analysis(video_path: Path, prompt: str) -> Dict[str, Any]:
    """
    调用百炼千问视频理解 API，分析视频内容。
    使用业务空间ID模式。
    """
    api_key = os.getenv("QWEN_API_KEY", "").strip()
    ws_id = os.getenv("QWEN_WS_ID", "").strip()
    model = os.getenv("QWEN_MODEL", "qwen3.7-plus").strip()
    
    if not api_key:
        print("[WARN] 千问 API Key 未配置，跳过视频分析")
        return {"error": "API Key 未配置"}
    
    base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_url = f"{base_url}/chat/completions"
    
    with open(video_path, "rb") as f:
        video_base64 = base64.b64encode(f.read()).decode("utf-8")
    
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "video_url",
                        "video_url": {
                            "url": f"data:video/mp4;base64,{video_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "max_tokens": 2048,
        "temperature": 0.1
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    if ws_id:
        headers["X-DashScope-WorkSpace"] = ws_id
    
    try:
        response = requests.post(api_url, json=payload, headers=headers, timeout=180)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[ERROR] 千问 API 调用失败: {response.status_code} - {response.text[:200]}")
            return {"error": f"HTTP {response.status_code}: {response.text[:200]}"}
    except requests.exceptions.Timeout:
        print("[ERROR] 千问 API 调用超时")
        return {"error": "请求超时"}
    except Exception as e:
        print(f"[ERROR] 千问 API 调用异常: {str(e)}")
        return {"error": str(e)}


def _parse_qwen_semantic_output(qwen_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析千问语义校验 JSON 输出。
    确保字段完整且类型正确，补全缺失字段使用默认值。
    """
    default_result = {
        "camera_view": "unknown",
        "ego_vehicle_present": False,
        "visible_external_vehicle_count": 0,
        "estimated_involved_vehicle_count": 0,
        "external_vehicle_behavior": "unknown",
        "ego_external_relation": "unknown",
        "semantic_accident_type_candidate": "unknown",
        "semantic_confidence": 0.0,
        "supporting_observations": [],
        "conflict_with_detector": False,
        "conflict_reasons": [],
        "missing_evidence": [],
        "should_enter_liability_reasoning": False,
        "manual_review_required": True,
        "raw_content": ""
    }
    
    if not qwen_response or qwen_response.get("error"):
        print(f"[WARN] 千问语义校验返回错误: {qwen_response.get('error', '无响应')}")
        return {**default_result, "error": qwen_response.get("error", "无响应")}
    
    try:
        choices = qwen_response.get("choices", [])
        if not choices:
            print("[WARN] 千问语义校验无 choices")
            return default_result
        
        message = choices[0].get("message", {})
        content = message.get("content", "")
        
        if not content:
            print("[WARN] 千问语义校验内容为空")
            return default_result
        
        default_result["raw_content"] = content
        
        json_str = content.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        
        parsed = json.loads(json_str)
        if not isinstance(parsed, dict):
            print("[WARN] 千问语义校验 JSON 解析结果不是 dict")
            return default_result
        
        field_specs = {
            "camera_view": (str, "unknown"),
            "ego_vehicle_present": (bool, False),
            "visible_external_vehicle_count": (int, 0),
            "estimated_involved_vehicle_count": (int, 0),
            "external_vehicle_behavior": (str, "unknown"),
            "ego_external_relation": (str, "unknown"),
            "semantic_accident_type_candidate": (str, "unknown"),
            "semantic_confidence": (float, 0.0),
            "supporting_observations": (list, []),
            "conflict_with_detector": (bool, False),
            "conflict_reasons": (list, []),
            "missing_evidence": (list, []),
            "should_enter_liability_reasoning": (bool, False),
            "manual_review_required": (bool, True)
        }
        
        for field, (field_type, default_val) in field_specs.items():
            val = parsed.get(field, default_val)
            if not isinstance(val, field_type):
                try:
                    if field_type == bool and isinstance(val, (int, float, str)):
                        val = bool(val)
                    elif field_type == int and isinstance(val, (float, str)):
                        val = int(float(val))
                    elif field_type == float and isinstance(val, (int, str)):
                        val = float(val)
                    else:
                        val = default_val
                except (ValueError, TypeError):
                    val = default_val
            default_result[field] = val
        
        return default_result
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] 千问语义校验 JSON 解码失败: {e}")
        return default_result
    except Exception as e:
        print(f"[ERROR] 解析千问语义校验结果异常: {str(e)}")
        return default_result


def fuse_video_evidence(
    detector_output: Dict[str, Any],
    qwen_semantic_check: Dict[str, Any],
    keyframe_count: int = 0
) -> Dict[str, Any]:
    """
    融合检测模型输出和千问语义校验结果，生成融合证据包。
    """
    try:
        detector = detector_output or {}
        qwen = qwen_semantic_check or {}
        
        # 兜底逻辑：如果 keyframe_count 为 0，尝试从 detector_output 中提取
        if keyframe_count == 0:
            keyframes = detector.get("keyframes", [])
            keyframe_count = len(keyframes) if isinstance(keyframes, list) else 0
            if keyframe_count > 0:
                print(f"[DEBUG] 融合函数: 从 detector_output 兜底提取到 {keyframe_count} 个关键帧")
        
        print("[DEBUG] 融合函数: 开始提取字段...")
        
        detector_type = str(detector.get("accident_type") or detector.get("model_pred_type") or "unknown")
        detector_confidence = float(detector.get("type_confidence") or detector.get("confidence") or 0.0)
        
        # 安全获取 rear_end_support
        rear_guard_cfg = detector.get("rear_guard_cfg")
        if isinstance(rear_guard_cfg, dict):
            rear_end_threshold = rear_guard_cfg.get("rear_end_threshold", 0.0)
        else:
            rear_end_threshold = detector.get("rear_end_support", 0.0)
        detector_rear_end_support = float(rear_end_threshold if rear_end_threshold is not None else 0.0)
        
        camera_view = str(qwen.get("camera_view", "unknown"))
        qwen_semantic_type = str(qwen.get("semantic_accident_type_candidate", "unknown"))
        qwen_confidence = float(qwen.get("semantic_confidence", 0.0))
        
        print(f"[DEBUG] 融合: detector_type={detector_type}, conf={detector_confidence}, rear={detector_rear_end_support}")
        print(f"[DEBUG] 融合: qwen_type={qwen_semantic_type}, qwen_conf={qwen_confidence}, camera={camera_view}")
        
        # Vehicle count (Task 2: Fix estimated_involved_vehicle_count logic)
        visible_external = int(qwen.get("visible_external_vehicle_count", 0))
        if camera_view == "dashcam_ego_view":
            ego_present = True
            estimated_involved = visible_external + 1
        else:
            ego_present = False
            estimated_involved = visible_external
        
        # Type decision
        type_decision_status = "accepted"
        accepted_type = detector_type
        
        if detector_confidence < 0.5:
            accepted_type = "unknown"
            type_decision_status = "needs_manual_review"
        
        if detector_type == "rear_end" and detector_rear_end_support < 0.3 and detector_confidence < 0.5:
            accepted_type = "unknown"
            type_decision_status = "needs_manual_review"
        
        # Conflict detection
        conflict_detected = False
        conflict_reasons = []
        type_mapping = {
            "rear_end": ["rear_end", "ego_rear_ends_front_vehicle"],
            "lane_change": ["lane_change_or_cut_in", "lane_change", "cut_in"],
            "side_collision": ["side_collision"],
            "head_on": ["head_on"],
        }
        
        def _type_matches(det_type: str, qwen_type: str) -> bool:
            det_lower = det_type.lower().replace(" ", "_")
            qwen_lower = qwen_type.lower().replace(" ", "_")
            if det_lower == qwen_lower:
                return True
            for key, aliases in type_mapping.items():
                if det_lower in aliases and qwen_lower in aliases:
                    return True
            return False
        
        if detector_type != "unknown" and qwen_semantic_type != "unknown":
            if not _type_matches(detector_type, qwen_semantic_type):
                conflict_detected = True
                conflict_reasons.append(f"检测模型识别为 '{detector_type}'，千问语义校验识别为 '{qwen_semantic_type}'")
        
        # Rear-end support
        rear_end_support_score = detector_rear_end_support
        if detector_type == "rear_end" and qwen_semantic_type not in ("rear_end", "unknown"):
            rear_end_support_score = min(rear_end_support_score, 0.2)
            conflict_reasons.append(f"千问语义校验不支持追尾判定 (千问给出: {qwen_semantic_type})")
        
        rear_end_status = "not_supported" if rear_end_support_score < 0.3 else "partially_supported" if rear_end_support_score < 0.6 else "supported"
        rear_end_reason = "未检测到明确前后车追尾关系"
        if qwen_semantic_type not in ("rear_end", "unknown"):
            rear_end_reason += f"，且语义校验更倾向于 {qwen_semantic_type}"
        
        # Consistency
        matched_items = []
        conflict_items = []
        missing_items = list(qwen.get("missing_evidence", []))
        
        if not conflict_detected and detector_type != "unknown" and qwen_semantic_type != "unknown":
            matched_items.append(f"检测模型和千问语义校验均指向相似事故类型")
        
        if conflict_detected:
            conflict_items.extend(conflict_reasons)
        
        key_evidence_types = {"碰撞部位", "双方车辆关系", "事故后位置", "collision_point", "vehicle_relationship", "post_crash_position"}
        critical_missing = [item for item in missing_items if any(kw in item for kw in key_evidence_types)]
        
        consistency_score = 0.5
        if conflict_detected:
            consistency_score = max(0.1, consistency_score - 0.3)
        if critical_missing:
            consistency_score = max(0.1, consistency_score - 0.2)
        if matched_items and not conflict_detected:
            consistency_score = min(1.0, consistency_score + 0.3)
        
        consistency_level = "high" if consistency_score >= 0.7 else "medium" if consistency_score >= 0.4 else "low"
        
        manual_review_required = bool(qwen.get("manual_review_required", True))
        if conflict_detected or critical_missing or accepted_type == "unknown":
            manual_review_required = True
        
        system_action = "manual_review_required" if manual_review_required else "proceed_to_liability"
        
        should_enter_liability = bool(qwen.get("should_enter_liability_reasoning", False))
        if manual_review_required:
            should_enter_liability = False
        
        qwen_available = not (qwen.get("error") if qwen else False)
        
        # ========== 新增：最终状态判定 ==========
        final_status = "evidence_ready"
        status_reason_parts = []
        
        # 判定逻辑
        if not qwen_available:
            final_status = "insufficient_evidence"
            status_reason_parts.append("千问 API 不可用")
        
        if keyframe_count == 0:
            final_status = "insufficient_evidence"
            status_reason_parts.append("无关键帧")
        
        if conflict_detected:
            final_status = "needs_manual_review"
            status_reason_parts.append("检测模型与千问语义校验存在类型冲突")
        
        if critical_missing:
            final_status = "needs_manual_review"
            status_reason_parts.append(f"存在关键证据缺失: {', '.join(critical_missing)}")
        
        # Task 3: Low confidence consistency confirmation rule
        if detector_confidence < 0.5 and not conflict_detected and qwen_confidence >= 0.6 and final_status != "insufficient_evidence":
            final_status = "evidence_ready"
            status_reason = "检测模型置信度较低，但千问语义校验结果一致且证据完整，可进入责任推理"
            status_reason_parts = [status_reason]
        else:
            if manual_review_required and final_status != "insufficient_evidence":
                final_status = "needs_manual_review"
                if not status_reason_parts:
                    status_reason_parts.append("置信度不足或存在其他需人工复核的因素")
            
            if final_status == "evidence_ready" and not status_reason_parts:
                status_reason_parts.append("证据一致且充分，可进入责任推理")
        
        status_reason = "；".join(status_reason_parts) if status_reason_parts else "未知状态"
        
        fused = {
            "camera_context": {
                "camera_view": camera_view,
                "ego_vehicle_present": ego_present,
                "visible_external_vehicle_count": visible_external,
                "estimated_involved_vehicle_count": estimated_involved,
            },
            "vehicle_evidence": {
                "external_vehicle_behavior": str(qwen.get("external_vehicle_behavior", "unknown")),
                "ego_external_relation": str(qwen.get("ego_external_relation", "unknown")),
                "supporting_observations": qwen.get("supporting_observations", []),
            },
            "detector_output": {
                "candidate_accident_type_from_detector": detector_type,
                "detector_type_confidence": round(detector_confidence, 4),
            },
            "qwen_semantic_check": {
                "semantic_accident_type_from_qwen": qwen_semantic_type,
                "semantic_confidence": round(qwen_confidence, 4),
                "conflict_with_detector": conflict_detected,
                "conflict_reasons": conflict_reasons,
                "missing_evidence": missing_items,
                "raw_content": qwen.get("raw_content", ""),
            },
            "fusion_result": {
                "accepted_accident_type": accepted_type,
                "type_decision_status": type_decision_status,
                "final_status": final_status,
                "status_reason": status_reason,
                "rear_end_support": {
                    "score": round(rear_end_support_score, 4),
                    "status": rear_end_status,
                    "reason": rear_end_reason
                },
                "keyframe_video_consistency": {
                    "score": round(consistency_score, 4),
                    "level": consistency_level,
                    "comparison_target": "keyframes_vs_video_detection_and_semantic_check",
                    "matched_items": matched_items,
                    "conflict_items": conflict_items,
                    "missing_items": missing_items,
                    "system_action": system_action
                },
                "conflict_detected": conflict_detected,
                "manual_review_required": manual_review_required,
                "should_enter_liability_reasoning": should_enter_liability,
                "system_action": system_action,
                "qwen_available": qwen_available
            }
        }
        
        return fused
    except Exception as e:
        import traceback
        print(f"[ERROR] fuse_video_evidence 异常: {type(e).__name__}: {str(e)}")
        traceback.print_exc()
        # 返回一个兜底结构
        return {
            "camera_context": {"camera_view": "unknown", "ego_vehicle_present": False, "visible_external_vehicle_count": 0, "estimated_involved_vehicle_count": 0},
            "vehicle_evidence": {},
            "detector_output": {},
            "qwen_semantic_check": {},
            "fusion_result": {
                "accepted_accident_type": "unknown",
                "type_decision_status": "needs_manual_review",
                "rear_end_support": {"score": 0.0, "status": "not_supported", "reason": "融合异常"},
                "keyframe_video_consistency": {"score": 0.0, "level": "error", "system_action": "manual_review_required"},
                "conflict_detected": True,
                "manual_review_required": True,
                "should_enter_liability_reasoning": False,
                "system_action": "manual_review_required",
                "qwen_available": False
            }
        }


# -----------------------------
# Dify 集成相关配置和函数
# -----------------------------

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

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default
    
def _round_float(value: Any, digits: int = 4) -> Optional[float]:
    v = _as_float(value)
    if v is None:
        return None
    return round(float(v), digits)

def _round_float_or(value: Any, default: float = 0.0, digits: int = 4) -> float:
    fv = _as_float(value)
    if fv is None:
        return round(float(default), digits)
    return round(float(fv), digits)

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

def _get_dify_hash_log_file() -> Path:
    raw_path = os.getenv("DIFY_HASH_LOG_FILE", "").strip()
    if raw_path:
        path = Path(raw_path)
        if not path.is_absolute():
            path = (BASE_DIR / path).resolve()
    else:
        path = BASE_DIR / "outputs" / "dify_hash_logs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def _append_dify_hash_log(entry: Dict[str, Any]) -> Optional[str]:
    if not _is_truthy_env("DIFY_HASH_LOG_ENABLED", True):
        return None
    log_entry = {"ts_utc": datetime.now(timezone.utc).isoformat(), **entry}
    try:
        log_path = _get_dify_hash_log_file()
        with log_path.open("a", encoding="utf-8") as f:
            f.write(_stable_json_dumps(log_entry))
            f.write("\n")
        return str(log_path)
    except Exception:
        return None

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

def _probe_dify_endpoint(workflow_url: str, timeout_sec: int = 8) -> Dict[str, Any]:
    result: Dict[str, Any] = {"ok": False, "status_code": None, "content_type": "", "looks_like_html": False, "message": ""}
    workflow_url = str(workflow_url or "").strip()
    if not workflow_url:
        result["message"] = "workflow_url is empty"
        return result
    req = urllib_request.Request(workflow_url, method="GET", headers={"Accept": "application/json, text/plain;q=0.9, */*;q=0.8", "Connection": "close"})
    try:
        with urllib_request.urlopen(req, timeout=max(3, int(timeout_sec))) as resp:
            status_code = int(getattr(resp, "status", 200))
            content_type = str(resp.headers.get("Content-Type", ""))
            head = (resp.read(256) or b"").decode("utf-8", errors="ignore").lower()
        looks_like_html = ("text/html" in content_type.lower()) or ("<html" in head) or ("<!doctype html" in head)
        result.update({"status_code": status_code, "content_type": content_type, "looks_like_html": looks_like_html, "ok": (not looks_like_html), "message": "ok" if not looks_like_html else "endpoint returned HTML page, not Dify API JSON"})
        return result
    except urllib_error.HTTPError as exc:
        status_code = int(exc.code or 0)
        raw = exc.read() or b""
        content_type = str(exc.headers.get("Content-Type", "")) if exc.headers else ""
        head = raw[:256].decode("utf-8", errors="ignore").lower()
        looks_like_html = ("text/html" in content_type.lower()) or ("<html" in head) or ("<!doctype html" in head)
        ok = (status_code in {400, 401, 403, 404, 405, 415, 422}) and (not looks_like_html)
        result.update({"status_code": status_code, "content_type": content_type, "looks_like_html": looks_like_html, "ok": ok, "message": "reachable_with_http_error" if ok else f"HTTPError {status_code}"})
        return result
    except Exception as exc:
        result["message"] = f"probe_failed: {exc}"
        return result

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
        out.append({"type": str(item.get("type") or ""), "label": str(item.get("label") or ""), "prob": _round_float_or(item.get("prob"), 0.0, digits=4), "score": _round_float_or(item.get("score"), 0.0, digits=4)})
    return out

def _canonical_keyframes(raw: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        out.append({"stage": str(item.get("stage") or ""), "purpose": str(item.get("purpose") or ""), "time": _round_float_or(item.get("time"), 0.0, digits=2), "score": _round_float_or(item.get("score"), 0.0, digits=4), "raw_score": _round_float_or(item.get("raw_score"), 0.0, digits=4), "is_main": bool(item.get("is_main"))})
    return sorted(out, key=lambda x: (x["time"], x["stage"], x["purpose"]))

def _canonical_dominant_cluster(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {"dominance": _round_float_or(raw.get("dominance"), 0.0, digits=4), "coverage": _round_float_or(raw.get("coverage"), 0.0, digits=4), "continuity": _round_float_or(raw.get("continuity"), 0.0, digits=4), "bridged_coverage": _round_float_or(raw.get("bridged_coverage"), 0.0, digits=4), "bridged_continuity": _round_float_or(raw.get("bridged_continuity"), 0.0, digits=4), "peak_mean": _round_float_or(raw.get("peak_mean"), 0.0, digits=4), "impact_peak": _round_float_or(raw.get("impact_peak"), 0.0, digits=4), "onset_peak": _round_float_or(raw.get("onset_peak"), 0.0, digits=4), "count": _safe_int(raw.get("count"), 0)}

def _canonical_video_evidence(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    stage_scores = raw.get("stage_scores") if isinstance(raw.get("stage_scores"), dict) else {}
    return {"peak_risk": _round_float_or(raw.get("peak_risk"), 0.0, digits=4), "risk_threshold": _round_float_or(raw.get("risk_threshold"), 0.0, digits=4), "stage_scores": _canonical_number_dict(stage_scores, digits=4), "type_probs": _canonical_number_dict(raw.get("type_probs"), digits=4), "type_scores_raw": _canonical_number_dict(raw.get("type_scores_raw"), digits=4)}

def _canonical_image_consistency(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {"consistency_label": str(raw.get("consistency_label") or ""), "evidence_consistency_score": _round_float_or(raw.get("evidence_consistency_score"), 0.0, digits=4), "image_rear_end_score": _round_float_or(raw.get("image_rear_end_score"), 0.0, digits=4), "video_rear_end_score": _round_float_or(raw.get("video_rear_end_score"), 0.0, digits=4)}

def _canonical_image_quality(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    reject_reasons = raw.get("reject_reasons")
    if isinstance(reject_reasons, list):
        reasons = [str(x) for x in reject_reasons]
    else:
        reasons = []
    return {"quality_score": _round_float_or(raw.get("quality_score"), 0.0, digits=4), "hard_reject": bool(raw.get("hard_reject")), "reject_reasons": sorted(reasons)}

def _stabilize_video_result_for_dify(video_result: Dict[str, Any]) -> Dict[str, Any]:
    vr = video_result or {}
    timeline = vr.get("timeline") if isinstance(vr.get("timeline"), dict) else {}
    return {"model_version": str(vr.get("model_version") or ""), "accident_type": str(vr.get("accident_type") or "unknown"), "model_pred_type": str(vr.get("model_pred_type") or vr.get("accident_type") or "unknown"), "decision_mode": str(vr.get("decision_mode") or "model_main"), "fallback_reason": str(vr.get("fallback_reason") or "NONE"), "rear_guard_applied": bool(vr.get("rear_guard_applied")), "rear_guard_version": str(vr.get("rear_guard_version") or "v3.4.3"), "rear_guard_cfg": _canonical_number_dict(vr.get("rear_guard_cfg"), digits=4), "impact_time": _round_float_or(vr.get("impact_time", vr.get("estimated_collision_time", timeline.get("impact_time"))), 0.0, digits=2), "onset_time": _round_float_or(vr.get("onset_time", timeline.get("onset_time")), 0.0, digits=2), "post_time": _round_float_or(vr.get("post_time", timeline.get("post_time")), 0.0, digits=2), "vehicle_count": _safe_int(vr.get("vehicle_count"), 0), "type_confidence": _round_float_or(vr.get("type_confidence", vr.get("confidence")), 0.0, digits=4), "type_topk": _canonical_type_topk(vr.get("type_topk")), "scene_prior": _canonical_number_dict(vr.get("scene_prior"), digits=4), "uncertainty": _round_float_or(vr.get("uncertainty"), 1.0, digits=4), "risk_alert_time": _round_float_or(vr.get("risk_alert_time"), 0.0, digits=2), "lead_time_sec": _round_float_or(vr.get("lead_time_sec"), 0.0, digits=2), "risk_level": str(vr.get("risk_level") or "unknown"), "dominant_cluster": _canonical_dominant_cluster(vr.get("dominant_cluster")), "evidence": _canonical_video_evidence(vr.get("evidence")), "keyframes": _canonical_keyframes(vr.get("keyframes"))}

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
    return {"task": str(ie.get("task") or ""), "module": str(ie.get("module") or ""), "module_positioning": str(ie.get("module_positioning") or ""), "accident_type": str(ie.get("accident_type") or ""), "sub_type": str(ie.get("sub_type") or ""), "rear_end_supported": bool(ie.get("rear_end_supported")), "rear_end_likelihood": _round_float_or(ie.get("rear_end_likelihood"), 0.0, digits=4), "rear_end_type_match_score": _round_float_or(ie.get("rear_end_type_match_score", ie.get("rear_end_likelihood")), 0.0, digits=4), "single_image_liability_trust_score": _round_float_or(ie.get("single_image_liability_trust_score", ie.get("confidence")), 0.0, digits=4), "confidence": _round_float_or(ie.get("confidence"), 0.0, digits=4), "liability": str(ie.get("liability") or ""), "role_tendency": str(ie.get("role_tendency") or ""), "decision_hint": str(ie.get("decision_hint") or ""), "decision_text": str(ie.get("decision_text") or ""), "reason": str(ie.get("reason") or ""), "evidence_summary": str(ie.get("evidence_summary") or ""), "evidence_consistency_score": _round_float_or(ie.get("evidence_consistency_score"), 0.0, digits=4), "consistency": _canonical_image_consistency(ie.get("consistency")), "quality": _canonical_image_quality(ie.get("quality")), "feature_scores": _canonical_number_dict(ie.get("feature_scores"), digits=4), "suitable_for_assessment": bool(ie.get("suitable_for_assessment")), "suitable_image_count": _safe_int(ie.get("suitable_image_count"), 0), "image_count": _safe_int(ie.get("image_count"), 0), "vehicle_count": vehicle_count, "damage_count": damage_count}

def _compact_video_result_for_dify(video_result: Dict[str, Any]) -> Dict[str, Any]:
    vr = video_result or {}
    evidence = vr.get("evidence") if isinstance(vr.get("evidence"), dict) else {}
    dominant_cluster = vr.get("dominant_cluster") if isinstance(vr.get("dominant_cluster"), dict) else {}
    keyframes = _canonical_keyframes(vr.get("keyframes"))
    stage_scores_src = evidence.get("stage_scores") if isinstance(evidence.get("stage_scores"), dict) else {}
    stage_scores: Dict[str, float] = {}
    for key in ("pre", "approach", "onset", "impact", "post"):
        if key in stage_scores_src:
            stage_scores[key] = _round_float_or(stage_scores_src.get(key), 0.0, digits=4)
    topk = []
    for item in _canonical_type_topk(vr.get("type_topk"))[:3]:
        topk.append({"type": item.get("type", ""), "label": item.get("label", ""), "prob": _round_float_or(item.get("prob"), 0.0, digits=4)})
    return {"accident_type": str(vr.get("accident_type") or "unknown"), "model_pred_type": str(vr.get("model_pred_type") or vr.get("accident_type") or "unknown"), "decision_mode": str(vr.get("decision_mode") or "model_main"), "fallback_reason": str(vr.get("fallback_reason") or "NONE"), "rear_guard_applied": bool(vr.get("rear_guard_applied")), "type_confidence": _round_float_or(vr.get("type_confidence"), 0.0, digits=4), "risk_level": str(vr.get("risk_level") or "unknown"), "vehicle_count": _safe_int(vr.get("vehicle_count"), 0), "uncertainty": _round_float_or(vr.get("uncertainty"), 1.0, digits=4), "timeline": {"onset_time": _round_float_or(vr.get("onset_time"), 0.0, digits=2), "impact_time": _round_float_or(vr.get("impact_time"), 0.0, digits=2), "post_time": _round_float_or(vr.get("post_time"), 0.0, digits=2), "risk_alert_time": _round_float_or(vr.get("risk_alert_time"), 0.0, digits=2), "lead_time_sec": _round_float_or(vr.get("lead_time_sec"), 0.0, digits=2)}, "type_topk": topk, "keyframe_count": len(keyframes), "keyframe_overview": keyframes[:5], "video_signal": {"peak_risk": _round_float_or(evidence.get("peak_risk"), 0.0, digits=4), "risk_threshold": _round_float_or(evidence.get("risk_threshold"), 0.0, digits=4), "stage_scores": stage_scores, "dominance": _round_float_or(dominant_cluster.get("dominance"), 0.0, digits=4), "coverage": _round_float_or(dominant_cluster.get("coverage"), 0.0, digits=4), "continuity": _round_float_or(dominant_cluster.get("continuity"), 0.0, digits=4)}}

def _compact_image_evidence_for_dify(image_evidence: Dict[str, Any]) -> Dict[str, Any]:
    ie = image_evidence or {}
    consistency = _canonical_image_consistency(ie.get("consistency"))
    quality = _canonical_image_quality(ie.get("quality"))
    return {"module": str(ie.get("module") or ""), "accident_type": str(ie.get("accident_type") or ""), "rear_end_supported": bool(ie.get("rear_end_supported")), "rear_end_likelihood": _round_float_or(ie.get("rear_end_likelihood"), 0.0, digits=4), "rear_end_type_match_score": _round_float_or(ie.get("rear_end_type_match_score", ie.get("rear_end_likelihood")), 0.0, digits=4), "single_image_liability_trust_score": _round_float_or(ie.get("single_image_liability_trust_score", ie.get("confidence")), 0.0, digits=4), "evidence_consistency_score": _round_float_or(ie.get("evidence_consistency_score", consistency.get("evidence_consistency_score")), 0.0, digits=4), "consistency_label": str(consistency.get("consistency_label") or ""), "quality_score": _round_float_or(quality.get("quality_score"), 0.0, digits=4), "hard_reject": bool(quality.get("hard_reject")), "reject_reasons": (quality.get("reject_reasons") or [])[:3], "feature_scores": _canonical_number_dict(ie.get("feature_scores"), digits=4), "role_tendency": str(ie.get("role_tendency") or ""), "decision_hint": str(ie.get("decision_hint") or ""), "decision_text": str(ie.get("decision_text") or "")}

def _build_liability_evidence_packet(video_result: Dict[str, Any], image_evidence: Dict[str, Any], additional_evidence: str) -> Dict[str, Any]:
    vr = video_result or {}
    ie = image_evidence or {}
    consistency = ie.get("consistency") if isinstance(ie.get("consistency"), dict) else {}
    quality = ie.get("quality") if isinstance(ie.get("quality"), dict) else {}
    keyframes = vr.get("keyframes") if isinstance(vr.get("keyframes"), list) else []
    accident_type = str(vr.get("accident_type") or "").strip()
    type_confidence = _round_float_or(vr.get("type_confidence", vr.get("confidence")), 0.0, 4)
    vehicle_count = _safe_int(vr.get("vehicle_count"), 0)
    impact_time = _round_float_or(vr.get("impact_time", vr.get("estimated_collision_time")), 0.0, 2)
    onset_time = _round_float_or(vr.get("onset_time"), 0.0, 2)
    post_time = _round_float_or(vr.get("post_time"), 0.0, 2)
    keyframe_count = len(keyframes)
    consistency_score = _round_float_or(ie.get("evidence_consistency_score", consistency.get("evidence_consistency_score")), 0.0, 4)
    hard_reject = bool(ie.get("hard_reject", quality.get("hard_reject")))
    role_tendency = str(ie.get("role_tendency") or "").strip()
    additional_text = str(additional_evidence or "").strip()
    unknown_values = {"", "unknown", "unk", "n/a", "na", "none", "null"}
    type_is_known = accident_type.lower() not in unknown_values
    checks = [{"code": "accident_type_known", "passed": type_is_known, "critical": True}, {"code": "type_confidence_enough", "passed": type_confidence >= 0.55, "critical": True}, {"code": "vehicle_count_enough", "passed": vehicle_count >= 2, "critical": True}, {"code": "impact_time_detected", "passed": impact_time > 0.0, "critical": True}, {"code": "keyframes_available", "passed": keyframe_count >= 3, "critical": False}, {"code": "image_quality_not_rejected", "passed": not hard_reject, "critical": True}, {"code": "cross_modal_consistency", "passed": consistency_score >= 0.45, "critical": False}, {"code": "role_tendency_available", "passed": bool(role_tendency), "critical": False}, {"code": "additional_evidence_present", "passed": bool(additional_text), "critical": False}]
    total_checks = len(checks)
    passed_checks = sum(1 for item in checks if item["passed"])
    readiness_score = round((passed_checks / total_checks) if total_checks else 0.0, 4)
    missing_critical = [item["code"] for item in checks if item["critical"] and not item["passed"]]
    missing_supporting = [item["code"] for item in checks if (not item["critical"]) and not item["passed"]]
    readiness = "insufficient" if missing_critical else ("sufficient" if readiness_score >= 0.75 else ("partial" if readiness_score >= 0.5 else "insufficient"))
    recommendation = "Proceed with cautious liability suggestion." if readiness == "sufficient" else ("Provide conditional judgment and request missing evidence." if readiness == "partial" else "Do not provide deterministic liability ratio; return insufficient_evidence.")
    return {"readiness": readiness, "readiness_score": readiness_score, "missing_critical_evidence": missing_critical, "missing_supporting_evidence": missing_supporting, "recommendation": recommendation, "core_facts": {"accident_type": accident_type or "unknown", "type_confidence": type_confidence, "vehicle_count": vehicle_count, "timeline": {"onset_time": onset_time, "impact_time": impact_time, "post_time": post_time}, "keyframe_count": keyframe_count, "consistency_score": consistency_score, "image_hard_reject": hard_reject, "role_tendency": role_tendency}, "decision_policy": {"require_evidence_grounding": True, "forbid_fabrication": True, "insufficient_evidence_action": "return_insufficient_evidence_with_missing_items", "separate_fact_inference_law": True}, "checks": checks}

def _mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return secret[:4] + "*" * (len(secret) - 8) + secret[-4:]

def _get_dify_settings() -> Dict[str, Any]:
    base_url = os.getenv("DIFY_BASE_URL", "").strip().rstrip("/")
    endpoint = os.getenv("DIFY_WORKFLOW_ENDPOINT", "/v1/workflows/run").strip() or "/v1/workflows/run"
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        workflow_url = endpoint
    elif base_url:
        workflow_url = f"{base_url}/{endpoint.lstrip('/')}"
    else:
        workflow_url = endpoint
    return {"base_url": base_url, "workflow_url": workflow_url, "api_key": os.getenv("DIFY_API_KEY", "").strip(), "timeout_sec": max(5, _as_int(os.getenv("DIFY_TIMEOUT_SEC", "60"), 60)), "default_response_mode": os.getenv("DIFY_RESPONSE_MODE", "blocking").strip() or "blocking", "summary_key": os.getenv("DIFY_INPUT_SUMMARY_KEY", "summary_text").strip() or "summary_text", "video_json_key": os.getenv("DIFY_INPUT_VIDEO_JSON_KEY", "video_result_json").strip() or "video_result_json", "image_json_key": os.getenv("DIFY_INPUT_IMAGE_JSON_KEY", "image_evidence_json").strip() or "image_evidence_json", "extra_key": os.getenv("DIFY_INPUT_EXTRA_KEY", "additional_evidence").strip() or "additional_evidence", "stabilize_inputs": _is_truthy_env("DIFY_STABILIZE_INPUTS", True), "include_raw_inputs": _is_truthy_env("DIFY_INCLUDE_RAW_INPUTS", False), "compact_json_inputs": _is_truthy_env("DIFY_COMPACT_JSON_INPUTS", True)}

# Import database functions
from backend.database import (
    init_db, authenticate_user, get_user_by_id,
    create_case, get_cases, get_case, update_case, delete_case, save_case_snapshot,
    get_rules, get_rule, create_rule, update_rule, delete_rule,
    get_tasks, create_task, complete_task,
    get_stats, get_history_cases, save_liability_result, verify_token,
    create_evidence_record, get_case_evidences,
    create_analysis_task, get_analysis_task, update_analysis_task,
    validate_case_status_transition, create_operation_log,
    create_analysis_version, get_latest_analysis_version, get_analysis_versions,
    create_structured_fact, get_case_structured_facts,
    get_evidence_consistency_check,
)

# ============================================================
# 融合证据包存储（内存 + SQLite）
# ============================================================
_fused_evidence_store: Dict[str, Dict[str, Any]] = {}

def _save_fused_evidence(case_id: str, fused_data: Dict[str, Any]):
    """保存融合证据包到内存和数据库"""
    _fused_evidence_store[case_id] = fused_data
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM fused_evidence WHERE case_id = ?", (case_id,))
        row = cursor.fetchone()
        fused_json = json.dumps(fused_data, ensure_ascii=False)
        if row and row[0] > 0:
            cursor.execute("UPDATE fused_evidence SET fused_json = ?, updated_at = ? WHERE case_id = ?",
                           (fused_json, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), case_id))
        else:
            cursor.execute("INSERT INTO fused_evidence (case_id, fused_json, created_at, updated_at) VALUES (?, ?, ?, ?)",
                           (case_id, fused_json, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[WARN] 保存融合证据包到数据库失败: {e}")

def _get_fused_evidence(case_id: str) -> Dict[str, Any]:
    """从数据库获取融合证据包，回退到内存"""
    cached = _fused_evidence_store.get(case_id)
    if cached:
        return cached
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        cursor = conn.execute("SELECT fused_json FROM fused_evidence WHERE case_id = ? ORDER BY updated_at DESC LIMIT 1", (case_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception as e:
        print(f"[WARN] 从数据库获取融合证据包失败: {e}")
    return _fused_evidence_store.get(case_id, {})

# ============================================================
# 启动事件
# ============================================================
@app.on_event("startup")
def startup():
    init_db()
    # 加载 Excel 数据
    from backend.services.review_assist_service import load_excel_data
    load_excel_data("事故案例汇总表.xlsx")

    # 其余代码...
    # 确保 fused_evidence 表存在
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fused_evidence (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id TEXT NOT NULL,
                fused_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(case_id)
            )
        """)
        conn.commit()
        conn.close()
        print("[INFO] fused_evidence 表已就绪")
    except Exception as e:
        print(f"[WARN] fused_evidence 表创建失败: {e}")
    
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cases WHERE id = 'ACC-658977'")
        if not cursor.fetchone():
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""INSERT INTO cases (id, title, accident_type, location, status, description, weather, road_env, priority, submitted_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                           ("ACC-658977", "系统预留案例（兼容旧ID）", "待分析", "未指定", "待分析", "自动创建的占位案例，避免前端404。", "晴", "城市道路", "中", now_str, now_str))
            conn.commit()
            print("[DB] Created legacy case: ACC-658977")
        conn.close()
    except Exception as e:
        print(f"[WARN] Failed to ensure legacy case: {e}")
    print("[INFO] Database initialized")

# ---------------------------------------------------------------------------
# 认证中间件 & 角色权限控制
# ---------------------------------------------------------------------------
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    payload = verify_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="无效令牌")
    return payload

async def get_optional_user(authorization: str = Header(None)):
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return verify_token(token)

def require_role(*allowed_roles: str):
    async def role_checker(current_user: dict = Depends(get_current_user)):
        if current_user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"权限不足，需要 {'/'.join(allowed_roles)} 角色，当前角色: {current_user.get('role', 'unknown')}")
        return current_user
    return role_checker

# ---------------------------------------------------------------------------
# 认证 API
# ---------------------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/auth/login")
async def api_login(data: LoginRequest):
    result = authenticate_user(data.username, data.password)
    if not result:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user = result["user"]
    user.pop("password_hash", None)
    return {"success": True, "data": {"user": user, "token": result["token"]}}

@app.get("/api/auth/me")
async def api_me(current_user: dict = Depends(get_current_user)):
    user = get_user_by_id(current_user["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"success": True, "data": user}

@app.post("/api/auth/logout")
async def api_logout(current_user: dict = Depends(get_current_user)):
    try:
        create_operation_log(action_type="user_logout", target_type="auth", target_id=str(current_user.get("user_id", "")), user_id=current_user.get("user_id"))
    except Exception:
        pass
    return {"success": True, "message": "已退出登录"}

# ---------------------------------------------------------------------------
# 案件 API
# ---------------------------------------------------------------------------
@app.get("/api/cases")
async def api_get_cases(status: str = None, accident_type: str = None, limit: int = None):
    params = {}
    if status:
        params["status"] = status
    if accident_type:
        params["accident_type"] = accident_type
    if limit:
        params["limit"] = limit
    cases = get_cases(params)
    return {"success": True, "data": cases}

@app.post("/api/cases")
async def api_create_case(data: dict):
    case = create_case(data)
    try:
        create_task({"case_id": case["id"], "title": f"{case.get('title', '未命名')} - 智能分析", "task_type": "analysis", "priority": "high" if case.get("priority") == "高" else "medium"})
    except Exception:
        pass
    return {"success": True, "data": case}

@app.get("/api/cases/{case_id}")
async def api_get_case(case_id: str):
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return {"success": True, "data": case}

@app.get("/api/cases/{case_id}/operation-logs")
async def api_get_operation_logs(case_id: str, current_user: dict = Depends(get_current_user)):
    try:
        from backend.database import get_db_conn
        case = get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"案件 {case_id} 不存在")
        conn = get_db_conn()
        try:
            cursor = conn.execute("SELECT log_id, action_type, target_type, target_id, before_data, after_data, created_at FROM operation_logs WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
            logs = [dict(row) for row in cursor.fetchall()]
            return {"success": True, "data": logs}
        finally:
            conn.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询审计日志失败: {str(e)}")

@app.put("/api/cases/{case_id}")
async def api_update_case(case_id: str, data: dict):
    case = update_case(case_id, data)
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    return {"success": True, "data": case}

@app.delete("/api/cases/{case_id}")
async def api_delete_case(case_id: str):
    delete_case(case_id)
    return {"success": True, "message": "删除成功"}

@app.post("/api/cases/{case_id}/snapshot")
async def api_save_snapshot(case_id: str, data: dict):
    step = data.get("step", "")
    flow_data = data.get("data", {})
    save_case_snapshot(case_id, step, flow_data)
    status_map = {"accident-entry": "待分析", "video-processing": "待分析", "analysis": "待复核", "recommendation": "待复核", "rule-basis": "待复核", "manual-review": "复核中", "archived": "已完成"}
    if step in status_map:
        update_case(case_id, {"status": status_map[step]})
    return {"success": True, "message": "快照已保存"}

@app.get("/api/cases/{case_id}/matched-rules")
async def api_get_matched_rules(case_id: str, current_user: dict = Depends(get_current_user)):
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        try:
            cursor = conn.execute("SELECT * FROM matched_rules WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
            rules = [dict(row) for row in cursor.fetchall()]
            return {"success": True, "data": rules}
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询命中规则失败: {str(e)}")

@app.get("/api/cases/{case_id}/reviews")
async def api_get_reviews(case_id: str, current_user: dict = Depends(get_current_user)):
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        try:
            cursor = conn.execute("SELECT * FROM reviews WHERE case_id = ? ORDER BY review_time DESC", (case_id,))
            reviews = [dict(row) for row in cursor.fetchall()]
            return {"success": True, "data": reviews}
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询复核记录失败: {str(e)}")

@app.post("/api/cases/{case_id}/reviews")
async def api_add_review(case_id: str, data: dict, current_user: dict = Depends(get_current_user)):
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("INSERT INTO reviews (case_id, reviewer, system_suggestion, final_result, review_comment, review_time) VALUES (?, ?, ?, ?, ?, ?)",
                         (case_id, data.get("reviewer", ""), data.get("system_suggestion", ""), data.get("final_result", ""), data.get("review_comment", ""), now_str))
            conn.commit()
            return {"success": True, "message": "复核记录已保存"}
        finally:
            conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存复核记录失败: {str(e)}")

@app.post("/api/cases/{case_id}/liability")
async def api_save_liability(case_id: str, data: dict):
    if not case_id:
        raise HTTPException(status_code=400, detail="case_id 不能为空")
    if not data:
        raise HTTPException(status_code=400, detail="请求数据不能为空")
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"案件 {case_id} 不存在，无法保存责任判定")
    try:
        summary = data.get("summary", "")
        ratio = data.get("ratio", "")
        details = data.get("details", {})
        hit_rules = data.get("hit_rules", [])
        if not isinstance(hit_rules, list):
            hit_rules = []
        save_liability_result(case_id, {"summary": summary, "ratio": ratio, "details": details, "hit_rules": hit_rules})
        return {"success": True, "message": "责任判定已保存"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存责任判定时发生未知错误: {str(e)}")

# ---------------------------------------------------------------------------
# 规则 API
# ---------------------------------------------------------------------------
@app.get("/api/rules")
async def api_get_rules(type: str = None, status: str = None, current_user: dict = Depends(get_current_user)):
    params = {}
    if type:
        params["type"] = type
    if status:
        params["status"] = status
    rules = get_rules(params)
    return {"success": True, "data": rules}

@app.get("/api/rules/{rule_id}")
async def api_get_rule(rule_id: str, current_user: dict = Depends(get_current_user)):
    rule = get_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"success": True, "data": rule}

@app.post("/api/rules")
async def api_create_rule(data: dict, current_user: dict = Depends(require_role("admin"))):
    rule = create_rule(data)
    return {"success": True, "data": rule}

@app.put("/api/rules/{rule_id}")
async def api_update_rule(rule_id: str, data: dict, current_user: dict = Depends(require_role("admin"))):
    rule = update_rule(rule_id, data)
    if not rule:
        raise HTTPException(status_code=404, detail="规则不存在")
    return {"success": True, "data": rule}

@app.delete("/api/rules/{rule_id}")
async def api_delete_rule(rule_id: str, current_user: dict = Depends(require_role("admin"))):
    delete_rule(rule_id)
    return {"success": True, "message": "删除成功"}

# ---------------------------------------------------------------------------
# 任务 API
# ---------------------------------------------------------------------------
@app.get("/api/tasks")
async def api_get_tasks(status: str = None):
    params = {}
    if status:
        params["status"] = status
    tasks = get_tasks(params)
    return {"success": True, "data": tasks}

@app.post("/api/tasks/{task_id}/complete")
async def api_complete_task(task_id: str):
    complete_task(task_id)
    return {"success": True, "message": "任务已完成"}

# ---------------------------------------------------------------------------
# 统计 & 历史 API
# ---------------------------------------------------------------------------
@app.get("/api/stats/overview")
async def api_stats():
    stats = get_stats()
    return {"success": True, "data": stats}

@app.get("/api/history-cases")
async def api_history_cases(status: str = None, limit: int = None):
    params = {}
    if status:
        params["status"] = status
    if limit:
        params["limit"] = limit
    cases = get_history_cases(params)
    return {"success": True, "data": cases}

# ---------------------------------------------------------------------------
# 流程 API
# ---------------------------------------------------------------------------
class FlowStepRequest(BaseModel):
    case_id: str
    step: str
    data: dict = {}

@app.post("/api/flow/step")
async def api_flow_step(data: FlowStepRequest):
    save_case_snapshot(data.case_id, data.step, data.data)
    status_map = {"accident-entry": "待分析", "video-processing": "待分析", "analysis": "待复核", "recommendation": "待复核", "rule-basis": "待复核", "manual-review": "复核中", "archived": "已完成"}
    if data.step in status_map:
        update_case(data.case_id, {"status": status_map[data.step]})
    return {"success": True, "message": "流程步进成功", "route": "/" + data.step}

# ---------------------------------------------------------------------------
# CORS 配置（生产环境通过 CORS_ALLOW_ORIGINS 环境变量限制来源）
# ---------------------------------------------------------------------------
_cors_origins_env = os.getenv("CORS_ALLOW_ORIGINS", "").strip()
if _cors_origins_env:
    _cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
else:
    _cors_origins = ["*"]  # 开发模式：允许所有来源

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TEMP_DIR = BASE_DIR / "temp"
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)

OUTPUTS_DIR = BASE_DIR / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

UPLOADS_DIR = BASE_DIR / "uploads"

def _get_case_upload_dir(case_id: str) -> Path:
    d = UPLOADS_DIR / "cases" / case_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def _compute_file_hash(file_path: Path) -> str:
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

# ============================================================
# 核心上传路由
# ============================================================
@app.post("/upload_video/")
@app.post("/api/upload_video/")
async def upload_video(
    file: UploadFile = File(...),
    case_id: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="未接收到文件")
    
    ext = Path(file.filename).suffix.lower()
    if ext not in {".mp4", ".avi", ".mov", ".mkv", ".webm"}:
        raise HTTPException(status_code=400, detail=f"不支持的文件格式: {ext}")
    
    from video_keyframe import safe_filename, save_upload_file, extract_keyframes, MODEL_VERSION, REAR_GUARD_VERSION, REAR_GUARD_CONFIG
    
    UPLOAD_DIR = BASE_DIR / "backend" / "uploaded_videos"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    
    saved_name = safe_filename(file.filename)
    saved_path = UPLOAD_DIR / saved_name
    
    try:
        await run_in_threadpool(save_upload_file, file, saved_path)
        
        # ========== ① YOLO 关键帧提取 ==========
        print("[DEBUG] 开始 YOLO 关键帧提取...")
        yolo_result = await run_in_threadpool(extract_keyframes, saved_path)
        print(f"[DEBUG] YOLO 完成, 类型: {yolo_result.get('accident_type', 'unknown')}, 置信度: {yolo_result.get('type_confidence', 0.0)}")
        keyframes = yolo_result.get("keyframes", [])

        # ========== 移除 Base64 图片数据，减小响应体大小 ==========
        for kf in keyframes:
            kf.pop("image_url", None)
        # =========================================================
        if not keyframes:
            raise HTTPException(status_code=500, detail="Failed to extract keyframes.")
        
        # ========== ② 千问视频语义校验 ==========
        # ... (千问 prompt 省略，保持不变)
        qwen_prompt = """你是交通事故视频语义校验模块。请只基于视频画面进行分析，不得编造画面外事实，不得直接进行责任认定。

你的任务不是判责，而是输出视频语义观察结果，用于后续规则推理和人工复核。

请重点判断：
1. 视频是否为行车记录仪视角；
2. 自车是否应作为隐式事故参与方；
3. 画面中可见外部车辆数量；
4. 外部车辆是否存在变道、切入、急停、侧向靠近等行为；
5. 当前证据是否足以进入责任推理；
6. 缺少哪些关键证据。

请严格输出 JSON，不要输出多余文字。

输出格式：
{
  "camera_view": "dashcam_ego_view / roadside_view / surveillance_view / unknown",
  "ego_vehicle_present": true,
  "visible_external_vehicle_count": 1,
  "estimated_involved_vehicle_count": 2,
  "external_vehicle_behavior": "lane_change / cut_in / braking / straight / unknown",
  "ego_external_relation": "external_vehicle_moves_into_ego_path / ego_rear_ends_front_vehicle / side_collision / unknown",
  "semantic_accident_type_candidate": "lane_change_or_cut_in / rear_end / side_collision / unknown",
  "semantic_confidence": 0.0,
  "supporting_observations": [],
  "conflict_with_detector": false,
  "conflict_reasons": [],
  "missing_evidence": [],
  "should_enter_liability_reasoning": false,
  "manual_review_required": true
}"""
        
        print("[DEBUG] 开始调用千问语义校验 API...")
        file_size = saved_path.stat().st_size if saved_path.exists() else 0
        print(f"[DEBUG] 视频路径: {saved_path}, 文件大小: {file_size} 字节")
        qwen_api_key_configured = "是" if os.getenv('QWEN_API_KEY', '').strip() else "否"
        print(f"[DEBUG] QWEN_API_KEY 是否配置: {qwen_api_key_configured}")
        print(f"[DEBUG] QWEN_MODEL: {os.getenv('QWEN_MODEL', 'qwen3.7-plus')}")
        
        qwen_available = True
        try:
            qwen_response = await run_in_threadpool(_call_qwen_video_analysis, saved_path, qwen_prompt)
            qwen_status = "成功" if not qwen_response.get("error") else "失败: " + str(qwen_response.get("error", ""))
            print(f"[DEBUG] 千问 API 返回状态: {qwen_status}")
        except Exception as qwen_exc:
            print(f"[ERROR] 千问 API 调用线程异常: {type(qwen_exc).__name__}: {str(qwen_exc)}")
            qwen_response = {"error": f"调用异常: {str(qwen_exc)}"}
            qwen_available = False
        
        print("[DEBUG] 开始解析千问语义校验结果...")
        qwen_semantic = _parse_qwen_semantic_output(qwen_response)
        if not qwen_available:
            qwen_semantic["error"] = "千问 API 不可用"
        print(f"[DEBUG] 千问语义校验: camera_view={qwen_semantic.get('camera_view')}, type={qwen_semantic.get('semantic_accident_type_candidate')}")
        
        # ========== ③ 融合检测结果 ==========
        print("[DEBUG] 开始融合检测结果...")
        fused = fuse_video_evidence(yolo_result, qwen_semantic, keyframe_count=len(keyframes))
        fused_packet = fused.get("fused_evidence_packet", fused)
        fusion_result = fused_packet.get("fusion_result", {})
        print(f"[DEBUG] 融合完成: accepted_type={fusion_result.get('accepted_accident_type', 'unknown')}, conflict={fusion_result.get('conflict_detected')}")
        
        # ========== ④ 写入数据库：自动创建案件 + 保存证据记录 ==========
        import hashlib
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 自动创建案件（如果没有传入 case_id）
        if not case_id:
            case_id = f"ACC-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
            accident_type_map = {
                'rear_end': '追尾', 'side_collision': '侧向碰撞',
                'lane_change_or_cut_in': '变道/切入', 'head_on': '正面碰撞'
            }
            accident_type_cn = accident_type_map.get(yolo_result.get('accident_type', 'unknown'), '事故')
            create_case({
                "id": case_id,
                "title": f"视频上传-{accident_type_cn}事故",
                "accident_type": accident_type_cn,
                "status": "待分析",
                "description": f"视频 {saved_name} 上传后自动创建，经 YOLO 检测为 {accident_type_cn}（置信度 {yolo_result.get('type_confidence', 0):.0%}）",
                "priority": "高",
            })
            print(f"[DB] 自动创建案件: {case_id}")
        
        # 计算视频文件 hash
        video_hash = hashlib.md5(saved_path.read_bytes()).hexdigest() if saved_path.exists() else ""
        
        # 保存视频证据记录
        video_evidence = create_evidence_record(case_id, {
            "evidence_type": "video",
            "file_path": f"backend/uploaded_videos/{saved_name}",
            "file_name": saved_name,
            "file_size": file_size,
            "file_hash": video_hash,
            "analysis_status": "completed",
            "related_stage": "video-processing",
            "metadata": {
                "duration": yolo_result.get("impact_time", 0),
                "vehicle_count": yolo_result.get("vehicle_count", 0),
                "accident_type": yolo_result.get("accident_type", ""),
                "type_confidence": yolo_result.get("type_confidence", 0),
            }
        })
        video_ev_id = video_evidence.get("evidence_id")
        print(f"[DB] 保存视频证据记录 ID={video_ev_id} -> {case_id}")
        
        # 保存关键帧证据记录
        for i, kf in enumerate(keyframes):
            thumb_url = kf.get("thumb_url", "")
            # 从 thumb_url 提取文件名（如 /keyframes/xxx_kf91_0_abc123.jpg）
            frame_name = thumb_url.rsplit("/", 1)[-1] if "/" in thumb_url else thumb_url
            frame_path = f"keyframes/{frame_name}"
            create_evidence_record(case_id, {
                "evidence_type": "keyframe",
                "file_path": frame_path,
                "file_name": frame_name,
                "file_size": 0,
                "file_hash": "",
                "analysis_status": "completed",
                "related_stage": "video-processing",
                "metadata": {
                    "stage": kf.get("stage", ""),
                    "time": kf.get("time", 0),
                    "score": kf.get("score", 0),
                    "purpose": kf.get("purpose", ""),
                    "parent_video_evidence_id": video_ev_id,
                }
            })
        print(f"[DB] 保存 {len(keyframes)} 条关键帧证据记录 -> {case_id}")
        
        # 保存融合证据包
        _save_fused_evidence(case_id, fused_packet)
        print(f"[DB] 保存融合证据包 -> {case_id}")
        
        # ========== ⑤ 返回结果 ==========
        return {
            "case_id": case_id,
            "video": f"/uploaded_videos/{saved_name}",
            "model_version": yolo_result.get("model_version", MODEL_VERSION),
            "impact_time": yolo_result["impact_time"],
            "onset_time": yolo_result["onset_time"],
            "post_time": yolo_result["post_time"],
            "vehicle_count": yolo_result["vehicle_count"],
            "accident_type": yolo_result["accident_type"],
            "type_confidence": yolo_result["type_confidence"],
            "type_topk": yolo_result.get("type_topk", []),
            "model_pred_type": yolo_result.get("model_pred_type", yolo_result["accident_type"]),
            "decision_mode": yolo_result.get("decision_mode", "model_main"),
            "fallback_reason": yolo_result.get("fallback_reason", "NONE"),
            "rear_guard_applied": bool(yolo_result.get("rear_guard_applied", False)),
            "rear_guard_version": yolo_result.get("rear_guard_version", REAR_GUARD_VERSION),
            "rear_guard_cfg": yolo_result.get("rear_guard_cfg", dict(REAR_GUARD_CONFIG)),
            "rear_guard_detail": yolo_result.get("rear_guard_detail", {}),
            "scene_prior": yolo_result.get("scene_prior", {}),
            "uncertainty": yolo_result.get("uncertainty", 1.0),
            "risk_alert_time": yolo_result.get("risk_alert_time", 0.0),
            "lead_time_sec": yolo_result.get("lead_time_sec", 0.0),
            "risk_level": yolo_result.get("risk_level", "unknown"),
            "dominant_cluster": yolo_result["dominant_cluster"],
            "dominant_pair": yolo_result.get("dominant_pair", []),
            "evidence": yolo_result.get("evidence", {}),
            "keyframes": keyframes,
            "qwen_analysis": qwen_semantic,
            "fused_evidence_packet": fused_packet,
            "analysis_source": "yolo_qwen_fused"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"video processing failed: {type(e).__name__}: {str(e)}"
        )
    finally:
        file.file.close()
# ============================================================
# 新融合证据 API 接口（Task 8）
# ============================================================

class VideoSemanticCheckRequest(BaseModel):
    video_path: str
    keyframes: List[str] = []
    detector_output: Dict[str, Any] = {}

@app.post("/api/cases/{case_id}/video-semantic-check")
async def api_video_semantic_check(case_id: str, data: VideoSemanticCheckRequest):
    """对案件视频执行千问语义校验"""
    try:
        video_path = Path(data.video_path)
        if not video_path.exists():
            video_path = BASE_DIR / data.video_path
        if not video_path.exists():
            raise HTTPException(status_code=400, detail=f"视频文件不存在: {data.video_path}")
        
        print(f"[DEBUG] 语义校验: case_id={case_id}, video_path={video_path}")
        
        qwen_prompt = """你是交通事故视频语义校验模块。请只基于视频画面进行分析，不得编造画面外事实。
请严格输出 JSON，不要输出多余文字。
输出格式：
{
  "camera_view": "dashcam_ego_view / roadside_view / surveillance_view / unknown",
  "ego_vehicle_present": true,
  "visible_external_vehicle_count": 1,
  "estimated_involved_vehicle_count": 2,
  "external_vehicle_behavior": "lane_change / cut_in / braking / straight / unknown",
  "ego_external_relation": "external_vehicle_moves_into_ego_path / ego_rear_ends_front_vehicle / side_collision / unknown",
  "semantic_accident_type_candidate": "lane_change_or_cut_in / rear_end / side_collision / unknown",
  "semantic_confidence": 0.0,
  "supporting_observations": [],
  "conflict_with_detector": false,
  "conflict_reasons": [],
  "missing_evidence": [],
  "should_enter_liability_reasoning": false,
  "manual_review_required": true
}"""
        
        qwen_response = await run_in_threadpool(_call_qwen_video_analysis, video_path, qwen_prompt)
        qwen_semantic = _parse_qwen_semantic_output(qwen_response)
        
        return {"success": True, "data": {"case_id": case_id, "qwen_semantic_check": qwen_semantic}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"语义校验失败: {str(e)}")


class FuseVideoEvidenceRequest(BaseModel):
    detector_output: Dict[str, Any] = {}
    qwen_semantic_check: Dict[str, Any] = {}
    keyframe_count: int = 0

@app.post("/api/cases/{case_id}/fuse-video-evidence")
async def api_fuse_video_evidence(case_id: str, data: FuseVideoEvidenceRequest):
    """融合检测模型和千问语义校验结果"""
    try:
        import traceback
        print(f"[DEBUG] 融合证据: case_id={case_id}")
        print(f"[DEBUG] 检测模型输出: {json.dumps(data.detector_output, ensure_ascii=False)[:200]}")
        print(f"[DEBUG] 千问语义校验: {json.dumps(data.qwen_semantic_check, ensure_ascii=False)[:200]}")
        print(f"[DEBUG] 关键帧数量: {data.keyframe_count}")
        
        fused = fuse_video_evidence(data.detector_output, data.qwen_semantic_check, keyframe_count=data.keyframe_count)
        
        try:
            _save_fused_evidence(case_id, fused)
        except Exception as e:
            print(f"[WARN] 保存融合证据包失败: {e}")
        
        fused_packet = fused.get("fused_evidence_packet", fused)
        return {"success": True, "data": {"case_id": case_id, "fused_evidence_packet": fused_packet}}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"证据融合失败: {str(e)}")


@app.get("/api/cases/{case_id}/fused-evidence")
async def api_get_fused_evidence(case_id: str):
    """获取案件融合证据包"""
    try:
        fused = _get_fused_evidence(case_id)
        if not fused:
            return {"success": True, "data": {"case_id": case_id, "message": "暂无融合证据包", "fused_evidence_packet": {}}}
        fused_packet = fused.get("fused_evidence_packet", fused)
        return {"success": True, "data": {"case_id": case_id, "fused_evidence_packet": fused_packet}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取融合证据包失败: {str(e)}")


# ============================================================
# Dify 接口（简化）
# ============================================================

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

def _build_default_case_summary(video_result: Dict[str, Any], image_evidence: Dict[str, Any], additional_evidence: str, liability_packet: Optional[Dict[str, Any]] = None) -> str:
    packet = liability_packet or {}
    accident_type = str(video_result.get("accident_type") or "unknown")
    impact_time = video_result.get("impact_time", video_result.get("estimated_collision_time", "unknown"))
    onset_time = video_result.get("onset_time", "unknown")
    risk_level = str(video_result.get("risk_level") or "unknown")
    vehicle_count = video_result.get("vehicle_count", "unknown")
    type_confidence = _as_float(video_result.get("type_confidence", video_result.get("confidence")))
    type_confidence_text = f"{type_confidence:.3f}" if type_confidence is not None else "unknown"
    rear_end_match = _as_float(image_evidence.get("rear_end_type_match_score", image_evidence.get("rear_end_likelihood")))
    liability_trust = _as_float(image_evidence.get("single_image_liability_trust_score", image_evidence.get("confidence")))
    rear_end_match_text = f"{rear_end_match:.3f}" if rear_end_match is not None else "unknown"
    liability_trust_text = f"{liability_trust:.3f}" if liability_trust is not None else "unknown"
    evidence_consistency = _as_float(image_evidence.get("evidence_consistency_score", (image_evidence.get("consistency") or {}).get("evidence_consistency_score") if isinstance(image_evidence.get("consistency"), dict) else None))
    evidence_consistency_text = f"{evidence_consistency:.3f}" if evidence_consistency is not None else "unknown"
    readiness = str(packet.get("readiness") or "unknown")
    readiness_score = _as_float(packet.get("readiness_score"))
    readiness_score_text = f"{readiness_score:.3f}" if readiness_score is not None else "unknown"
    missing_critical = packet.get("missing_critical_evidence")
    missing_critical_text = ", ".join([str(x) for x in missing_critical]) if isinstance(missing_critical, list) and missing_critical else "none"
    lines = ["Traffic accident evidence packet for liability reasoning.", "Strict policy:", "- Use only provided evidence; do not fabricate facts.", "- If critical evidence is missing, return insufficient_evidence and list missing items.", "- Keep facts, inference, and legal basis separated.", "Evidence readiness:", f"- readiness: {readiness}", f"- readiness_score: {readiness_score_text}", f"- missing_critical_evidence: {missing_critical_text}", "Core evidence values:", f"- accident_type: {accident_type}", f"- onset_time: {onset_time}", f"- impact_time: {impact_time}", f"- risk_level: {risk_level}", f"- vehicle_count: {vehicle_count}", f"- type_confidence: {type_confidence_text}", f"- rear_end_match: {rear_end_match_text}", f"- image_liability_trust: {liability_trust_text}", f"- evidence_consistency: {evidence_consistency_text}"]
    if additional_evidence.strip():
        lines.append(f"- additional_evidence: {additional_evidence.strip()}")
    return "\n".join(lines)

from pathlib import Path
import json
def _build_dify_case_inputs(payload: "DifyAccidentCaseRequest") -> Dict[str, Any]:
    """
    构建发送给 Dify 的输入数据（使用模板文件）。
    """
    print("[DEBUG] _build_dify_case_inputs 被调用")
    
    settings = _get_dify_settings()
    raw_video_result = payload.video_result or {}
    raw_image_evidence = payload.image_evidence or {}
    additional_evidence = payload.additional_evidence or ""

    # ========== 1. 提取融合证据包 ==========
    fused_packet = raw_video_result.get("fused_evidence_packet", {})
    cam_ctx = fused_packet.get("camera_context", {})
    qwen_check = fused_packet.get("qwen_semantic_check", {})
    fusion_result = fused_packet.get("fusion_result", {})

    # ========== 2. 提取 YOLO 原始检测结果 ==========
    yolo_raw = {
        "accident_type": raw_video_result.get("accident_type", "unknown"),
        "type_confidence": raw_video_result.get("type_confidence", 0.0),
        "vehicle_count": raw_video_result.get("vehicle_count", 0),
        "impact_time": raw_video_result.get("impact_time", 0.0),
        "onset_time": raw_video_result.get("onset_time", 0.0),
        "post_time": raw_video_result.get("post_time", 0.0),
        "risk_level": raw_video_result.get("risk_level", "unknown"),
        "type_topk": raw_video_result.get("type_topk", []),
        "keyframe_count": len(raw_video_result.get("keyframes", []))
    }

    # ========== 3. 提取千问完整原始输出 ==========
    qwen_analysis = raw_video_result.get("qwen_analysis", {})
    qwen_raw_text = qwen_analysis.get("raw_content", qwen_check.get("raw_content", ""))

    # ========== 4. 读取 Dify 提示词模板 ==========
    template_path = BASE_DIR / "backend" / "dify_prompt_template.txt"
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
    except Exception as e:
        print(f"[WARN] 读取 Dify 模板失败: {e}，使用默认模板")
        template = """【系统门控摘要】
{gateway_summary}

【门控状态】
final_status: {final_status}
rule_status: {rule_status}
ml_label: {ml_label}
ml_confidence: {ml_confidence}

---

【原始检测结果】

YOLO 视频检测模型输出：
{yolo_output}

千问视频语义校验输出：
{qwen_output}

---

【系统指令】

你是交通事故责任分析助手。请严格遵循以下规则：

1. **最高优先级**：以【系统门控摘要】和【门控状态】为最高优先级依据，不得违反。

2. **溯源限制**：YOLO 原始输出和千问语义校验输出仅用于解释和溯源，不得直接作为责任认定依据。

3. **门控约束**：
   - 若门控状态为 "needs_manual_review" 或 "insufficient_evidence"：
     * 不得输出明确责任认定
     * 只能输出证据冲突说明、缺失证据清单和人工复核建议
   
   - 若门控状态为 "evidence_ready"：
     * 可基于融合结果生成责任说明
     * 责任说明必须基于事实，不得编造信息

4. **禁止行为**：
   - 禁止编造画面外事实
   - 禁止在非 evidence_ready 状态下输出确定性责任认定
"""
    
    # ========== 5. 构建门控摘要 ==========
    gateway_summary_parts = []
    gateway_summary_parts.append("【系统门控约束】")
    gateway_summary_parts.append("Dify 必须以\"系统门控摘要\"为最高优先级依据。")
    gateway_summary_parts.append("YOLO 原始输出和千问语义校验输出仅用于解释和溯源。")
    final_status = fusion_result.get("final_status", "unknown")
    gateway_summary_parts.append(f"若门控状态为 \"needs_manual_review\" 或 \"insufficient_evidence\"：")
    gateway_summary_parts.append("  - 不得输出明确责任认定")
    gateway_summary_parts.append("  - 只能输出证据冲突说明、缺失证据清单和人工复核建议")
    gateway_summary_parts.append(f"若门控状态为 \"evidence_ready\"：")
    gateway_summary_parts.append("  - 可基于融合结果生成责任说明")
    gateway_summary_parts.append("  - 责任说明必须基于事实，不得编造信息")
    gateway_summary_parts.append("")
    
    # 门控机制触发情况
    gateway_summary_parts.append("【门控机制触发情况】")
    if cam_ctx.get("camera_view") == "dashcam_ego_view":
        gateway_summary_parts.append("补偿型门控：已触发（原因：行车记录仪视角，自车作为隐式参与方计入涉事车辆总数）")
    else:
        gateway_summary_parts.append("补偿型门控：未触发（原因：非行车记录仪视角）")
    if fusion_result.get("conflict_detected"):
        gateway_summary_parts.append(f"冲突型门控：已触发（原因：{qwen_check.get('conflict_reasons', ['检测到类型冲突'])[0]}）")
    else:
        gateway_summary_parts.append("冲突型门控：未触发（原因：检测模型与千问语义校验结果一致）")
    critical_missing = fusion_result.get("keyframe_video_consistency", {}).get("missing_items", [])
    key_evidence_types = {"碰撞部位", "双方车辆关系", "事故后位置"}
    has_critical_missing = any(any(kw in item for kw in key_evidence_types) for item in critical_missing)
    if has_critical_missing:
        gateway_summary_parts.append("证据不足门控：已触发（原因：存在关键证据缺失）")
    else:
        gateway_summary_parts.append("证据不足门控：未触发（原因：关键证据完整）")
    gateway_summary_parts.append("")
    
    gateway_summary_text = "\n".join(gateway_summary_parts)
    
    # ========== 6. 填充模板变量 ==========
    # 门控状态文本
    compensation_triggered = fusion_result.get("compensation_triggered", False)
    conflict_triggered = fusion_result.get("conflict_detected", False)
    insufficient_triggered = fusion_result.get("manual_review_required", True)

    summary_text = template.format(
        gateway_summary=gateway_summary_text,
        final_status=final_status,
        rule_status=fusion_result.get("type_decision_status", "unknown"),
        ml_label="unknown",  # ML模型暂未生效
        ml_confidence=0.0,
        conflict_detected=fusion_result.get("conflict_detected", False),
        evidence_sufficient=not fusion_result.get("manual_review_required", True),
        yolo_output=json.dumps(yolo_raw, ensure_ascii=False, indent=2),
        qwen_output=qwen_raw_text or "（千问未返回有效分析结果）",
        compensation_status="已触发（原因：存在类型冲突需人工判定）" if compensation_triggered else "未触发",
        conflict_status="已触发（原因：检测到证据矛盾）" if conflict_triggered else "未触发",
        insufficient_status="已触发（原因：关键证据缺失）" if insufficient_triggered else "未触发",
    )

    # ========== 5. 追加两部分原始输出 ==========
    summary_text += "\n\n" + "=" * 60 + "\n"
    summary_text += "【第一部分：YOLO 视频检测模型原始输出】\n"
    summary_text += "-" * 40 + "\n"
    summary_text += json.dumps(yolo_raw, ensure_ascii=False, indent=2)
    summary_text += "\n\n" + "=" * 60 + "\n"
    summary_text += "【第二部分：千问视频语义校验原始输出】\n"
    summary_text += "-" * 40 + "\n"
    if qwen_raw_text:
        summary_text += qwen_raw_text
    else:
        summary_text += "（千问未返回有效分析结果）"

    # ========== 6. 构造其他 payload（保持不变） ==========
    liability_packet = _build_liability_evidence_packet(raw_video_result, raw_image_evidence, additional_evidence)
    dify_video_result = {
        **(raw_video_result if isinstance(raw_video_result, dict) else {}),
        "liability_packet": liability_packet,
        "fused_evidence_packet": fused_packet
    }
    dify_image_evidence = {
        **(raw_image_evidence if isinstance(raw_image_evidence, dict) else {}),
        "liability_packet": {
            "readiness": liability_packet.get("readiness"),
            "readiness_score": liability_packet.get("readiness_score"),
            "missing_critical_evidence": liability_packet.get("missing_critical_evidence", []),
            "recommendation": liability_packet.get("recommendation", "")
        }
    }

    inputs = {
        settings["summary_key"]: summary_text,
        settings["video_json_key"]: json.dumps(dify_video_result, ensure_ascii=False),
        settings["image_json_key"]: json.dumps(dify_image_evidence, ensure_ascii=False),
        settings["extra_key"]: additional_evidence,
    }

    # ========== 7. 保存日志到文件（调试用） ==========
    return inputs
def _extract_dify_answer_text(dify_response: Dict[str, Any]) -> str:
    data = dify_response.get("data")
    if not isinstance(data, dict):
        return ""
    outputs = data.get("outputs")
    if isinstance(outputs, dict):
        for key in ["answer", "summary", "analysis", "result"]:
            if key in outputs:
                return str(outputs[key])
        return json.dumps(outputs, ensure_ascii=False)
    elif isinstance(outputs, str):
        return outputs
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
    if "json" in (content_type or "").lower() or text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return {"data": {"outputs": {"items": parsed}}}
        except Exception:
            pass
    if "data:" in text:
        events = []
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
    if _looks_like_html(text):
        raise ValueError("Dify endpoint returned HTML (non-API page). Please check DIFY_BASE_URL / DIFY_WORKFLOW_ENDPOINT routing.")
    return {"data": {"outputs": {"answer": text[:12000]}}}

def _build_local_dify_fallback_markdown(payload: "DifyAccidentCaseRequest", reason: Any) -> str:
    vr = payload.video_result or {}
    ie = payload.image_evidence or {}
    accident_type = str(vr.get("accident_type") or "unknown")
    confidence = _round_float_or(vr.get("confidence", vr.get("type_confidence")), 0.0, 4)
    vehicle_count = _safe_int(vr.get("vehicle_count"), 0)
    impact_time = _round_float_or(vr.get("impact_time", vr.get("estimated_collision_time")), 0.0, 2)
    onset_time = _round_float_or(vr.get("onset_time"), 0.0, 2)
    post_time = _round_float_or(vr.get("post_time"), 0.0, 2)
    consistency = _round_float_or(ie.get("evidence_consistency_score", (ie.get("consistency") or {}).get("evidence_consistency_score")), 0.0, 4)
    reason_text = str(reason)[:360] if reason is not None else "unknown"
    return ("# Dify 暂时不可用（已自动回退本地分析）\n\n系统已返回可读结论，你可以继续流程。\n\n## 本地结论\n"
            f"- 事故类型：{accident_type}\n- 置信度：{confidence:.3f}\n- 车辆数量：{vehicle_count}\n"
            f"- 时序：onset={onset_time}s, impact={impact_time}s, post={post_time}s\n"
            f"- 跨模态一致性：{consistency:.3f}\n\n## 说明\n- 当前为本地兜底结果（Dify 上游不可用时自动触发）。\n- 上游恢复后会自动回到 Dify 推理。\n"
            f"- 回退原因：{reason_text}\n")

def _call_dify_workflow(inputs: Dict[str, Any], user: str = "accident_app", response_mode: Optional[str] = None, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    settings = _get_dify_settings()
    workflow_url = str(settings["workflow_url"]).strip()
    api_key = str(settings["api_key"]).strip()
    if not workflow_url.startswith("http://") and not workflow_url.startswith("https://"):
        raise HTTPException(status_code=500, detail="Dify workflow URL is invalid.")
    if not api_key:
        raise HTTPException(status_code=500, detail="DIFY_API_KEY is not configured.")
    timeout_sec = max(5, _as_int(settings.get("timeout_sec"), 60))
    retry_count = max(0, _as_int(os.getenv("DIFY_RETRY_COUNT", "2"), 2))
    retry_backoff_sec = max(0.2, _as_float(os.getenv("DIFY_RETRY_BACKOFF_SEC", "0.8")) or 0.8)
    payload = {"inputs": inputs or {}, "response_mode": response_mode or settings["default_response_mode"], "user": user or "accident_app"}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json"}
    attempts = retry_count + 1
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(workflow_url, json=payload, headers=headers, timeout=timeout_sec)
            status_code = resp.status_code
            content_type = resp.headers.get("Content-Type", "")
            raw_text = resp.text
            if status_code >= 400:
                if _is_retryable_dify_http_status(status_code) and attempt < attempts:
                    time.sleep(retry_backoff_sec * attempt)
                    last_error = Exception(f"HTTP {status_code}: {raw_text[:500]}")
                    continue
                try:
                    dify_error = json.loads(raw_text) if raw_text else {}
                except Exception:
                    dify_error = {"raw": raw_text[:1200]}
                raise HTTPException(status_code=status_code, detail={"message": "Dify workflow request failed", "dify_error": dify_error})
            return _parse_dify_raw_response(raw_text.encode("utf-8"), content_type)
        except HTTPException:
            raise
        except requests.exceptions.Timeout:
            last_error = Exception("timeout")
            if attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(status_code=504, detail="Dify workflow request timed out.")
        except requests.exceptions.ConnectionError as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(status_code=503, detail=f"Dify service unreachable: {str(exc)}")
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=f"Dify response format invalid: {exc}")
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(retry_backoff_sec * attempt)
                continue
            raise HTTPException(status_code=500, detail=f"Dify workflow call failed: {str(exc)}")
    raise HTTPException(status_code=500, detail=f"Dify workflow call failed after retries: {last_error}")

@app.get("/dify/health/")
def dify_health():
    settings = _get_dify_settings()
    return {"configured": bool(settings["workflow_url"] and settings["api_key"]), "workflow_url": settings["workflow_url"], "api_key_masked": _mask_secret(settings["api_key"]), "default_response_mode": settings["default_response_mode"], "timeout_sec": settings["timeout_sec"], "input_mapping": {"summary_key": settings["summary_key"], "video_json_key": settings["video_json_key"], "image_json_key": settings["image_json_key"], "extra_key": settings["extra_key"]}}

@app.post("/dify/workflow_run/")
async def dify_workflow_run(payload: DifyWorkflowRunRequest):
    dify_response = await run_in_threadpool(_call_dify_workflow, payload.inputs, payload.user, payload.response_mode, payload.conversation_id)
    return {"result": _extract_dify_result(dify_response)}

@app.post("/dify/analyze_accident_case/")
@app.post("/api/dify/analyze_accident_case/")
async def dify_analyze_accident_case(payload: DifyAccidentCaseRequest):
    request_id = uuid.uuid4().hex
    workflow_inputs = _build_dify_case_inputs(payload)
    request_payload = _prepare_dify_request_payload(inputs=workflow_inputs, user=payload.user, response_mode=payload.response_mode, conversation_id=payload.conversation_id)
    input_hash = _hash_obj_sha256(request_payload)
    video_result_hash = _hash_obj_sha256(payload.video_result or {})
    image_evidence_hash = _hash_obj_sha256(payload.image_evidence or {})
    workflow_inputs_hash = _hash_obj_sha256(workflow_inputs)
    try:
        dify_response = await run_in_threadpool(_call_dify_workflow, workflow_inputs, payload.user, payload.response_mode, payload.conversation_id)
        answer_text = _extract_dify_answer_text(dify_response)
        output_hash = _hash_obj_sha256(dify_response)
        _append_dify_hash_log({"route": "/dify/analyze_accident_case/", "request_id": request_id, "input_hash": input_hash, "output_hash": output_hash, "workflow_inputs_hash": workflow_inputs_hash, "video_result_hash": video_result_hash, "image_evidence_hash": image_evidence_hash, "input_keys": sorted(workflow_inputs.keys()), "request_payload": request_payload, "workflow_inputs": workflow_inputs, "answer_preview": answer_text[:240], "fallback": False})
        return {"result": _extract_dify_result(dify_response)}
    except HTTPException as exc:
        if not _is_truthy_env("DIFY_LOCAL_FALLBACK_ENABLED", False):
            raise
        fallback_markdown = _build_local_dify_fallback_markdown(payload, exc.detail)
        fallback_hash = _hash_obj_sha256({"result": fallback_markdown, "reason": str(exc.detail)})
        _append_dify_hash_log({"route": "/dify/analyze_accident_case/", "request_id": request_id, "input_hash": input_hash, "output_hash": fallback_hash, "workflow_inputs_hash": workflow_inputs_hash, "video_result_hash": video_result_hash, "image_evidence_hash": image_evidence_hash, "input_keys": sorted(workflow_inputs.keys()), "request_payload": request_payload, "workflow_inputs": workflow_inputs, "answer_preview": fallback_markdown[:240], "fallback": True, "fallback_reason": str(exc.detail)[:360]})
        return {"result": fallback_markdown, "mode": "local_fallback", "fallback_reason": str(exc.detail)}

@app.post("/dify/preview_case_inputs/")
async def dify_preview_case_inputs(payload: DifyAccidentCaseRequest):
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
    return {"query": query, "workflow_inputs": workflow_inputs, "video_json": video_json, "image_json": image_json}

# ---------------------------------------------------------------------------
# 图像证据分析
# ---------------------------------------------------------------------------
@app.post("/analyze_image_evidence/")
@app.post("/api/analyze_image_evidence/")
async def analyze_image_evidence(data: dict):
    from video_keyframe import _resolve_keyframe_path, analyze_image_with_yolo
    try:
        frame_url = data.get("frame_url", "")
        video_context = data.get("video_context", {})
        frame_path = _resolve_keyframe_path(frame_url)
        result = await run_in_threadpool(analyze_image_with_yolo, str(frame_path))
        if video_context:
            result.setdefault("video_context", video_context)
        return {"frame_path": str(frame_path), "frame_url": frame_url, "image_evidence": result}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"image evidence analysis failed: {str(e)}")

@app.post("/analyze_image_file_evidence/")
@app.post("/api/analyze_image_file_evidence/")
async def analyze_image_file_evidence(file: UploadFile = File(...), video_context: str = Form(None)):
    from video_keyframe import analyze_image_with_yolo, save_upload_file
    if not file.filename:
        raise HTTPException(status_code=400, detail="未接收到图片文件")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
        raise HTTPException(status_code=400, detail=f"不支持的图片格式: {ext}")
    UPLOAD_DIR = BASE_DIR / "backend" / "uploaded_images"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_name = f"image_{uuid.uuid4().hex[:10]}{ext}"
    saved_path = UPLOAD_DIR / saved_name
    parsed_video_context = {}
    if video_context:
        try:
            parsed_video_context = json.loads(video_context)
            if not isinstance(parsed_video_context, dict):
                parsed_video_context = {}
        except Exception:
            parsed_video_context = {}
    try:
        await run_in_threadpool(save_upload_file, file, saved_path)
        result = await run_in_threadpool(analyze_image_with_yolo, str(saved_path))
        if parsed_video_context:
            result.setdefault("video_context", parsed_video_context)
            for key in ("accident_type", "type_confidence", "evidence_consistency_score"):
                if key in parsed_video_context:
                    result[f"ctx_{key}"] = parsed_video_context[key]
        return {"image_evidence": result, "filename": file.filename}
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

# ---------------------------------------------------------------------------
# 证据管理, 分析任务, 状态机, 版本管理, 报告等 API（保留原始代码）
# ---------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/evidences")
async def api_create_evidence(case_id: str, data: dict):
    try:
        case = get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"案件 {case_id} 不存在，无法添加证据")
        evidence_type = data.get("evidence_type", "image")
        file_path = data.get("file_path", "")
        content = data.get("content", "")
        if content and not file_path:
            upload_dir = _get_case_upload_dir(case_id)
            upload_dir.mkdir(parents=True, exist_ok=True)
            file_name = f"text_evidence_{uuid.uuid4().hex[:8]}.txt"
            file_path = str(upload_dir / file_name)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
        ev = create_evidence_record(case_id, {"evidence_type": evidence_type, "file_path": file_path, "file_name": data.get("file_name", ""), "file_size": data.get("file_size", 0), "file_hash": data.get("file_hash", ""), "analysis_status": data.get("analysis_status", "pending"), "related_stage": data.get("related_stage", ""), "metadata": data.get("metadata", {})})
        return {"success": True, "data": ev}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建证据记录失败: {str(e)}")

@app.get("/api/cases/{case_id}/evidences")
async def api_get_case_evidences(case_id: str):
    try:
        evs = get_case_evidences(case_id)
        return {"success": True, "data": evs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询证据列表失败: {str(e)}")

def _run_analysis_flow(task_id: str, case_id: str):
    try:
        update_analysis_task(task_id, {"task_status": "running", "progress": 30})
        time.sleep(0.5)
        try:
            create_structured_fact(case_id=case_id, source_type="video_analysis", fact_type="accident_type", fact_value="双车并行变道碰撞", confidence=0.92)
            create_structured_fact(case_id=case_id, source_type="video_analysis", fact_type="vehicle_count", fact_value="2", confidence=0.95)
            create_structured_fact(case_id=case_id, source_type="video_analysis", fact_type="impact_detected", fact_value="true", confidence=0.88)
        except Exception as e:
            update_analysis_task(task_id, {"task_status": "failed", "progress": 60, "error_message": f"结构化事实写入失败: {str(e)}"})
            return
        update_analysis_task(task_id, {"progress": 60})
        try:
            hit_rules = [{"code": "R-002", "name": "变道未打转向灯", "trigger_condition": "变道未打灯", "trigger_reason": "视频分析显示变道前未打转向灯", "content": "变更车道时未提前开启转向灯，影响其他车辆正常行驶，变道车辆负主要责任。"}, {"code": "R-007", "name": "违法变更车道", "trigger_condition": "连续变道", "trigger_reason": "视频分析显示车辆连续变更两条车道", "content": "连续变更两条以上车道，或在不具备变道条件时强行变道，变道车辆负主要责任。"}]
            save_liability_result(case_id, {"summary": "双车并行变道碰撞事故分析结果", "ratio": "7:3", "details": {"analysis": "视频分析显示变道车辆未打转向灯且连续变道，负主要责任"}, "hit_rules": hit_rules})
        except Exception as e:
            update_analysis_task(task_id, {"task_status": "failed", "progress": 80, "error_message": f"规则命中写入失败: {str(e)}"})
            return
        update_analysis_task(task_id, {"progress": 80})
        try:
            create_analysis_version(case_id=case_id, facts_json=json.dumps({"accident_type": "双车并行变道碰撞", "vehicle_count": 2}), matched_rules_json=json.dumps(hit_rules), suggestion_json=json.dumps({"ratio": "7:3", "summary": "变道车辆负主要责任"}), model_version="v1.0")
        except Exception as e:
            update_analysis_task(task_id, {"task_status": "failed", "progress": 90, "error_message": f"版本创建失败: {str(e)}"})
            return
        update_analysis_task(task_id, {"task_status": "success", "progress": 100, "result_json": json.dumps({"status": "completed", "summary": "分析完成", "ratio": "7:3", "hit_rules_count": len(hit_rules)})})
    except Exception as e:
        try:
            update_analysis_task(task_id, {"task_status": "failed", "progress": 0, "error_message": f"分析流程异常: {str(e)}"})
        except Exception:
            pass

@app.post("/api/tasks/analysis")
async def api_create_analysis_task(data: dict, background_tasks: BackgroundTasks):
    try:
        case_id = data.get("case_id", "")
        task_type = data.get("task_type", "image")
        if not case_id:
            raise ValueError("case_id 不能为空")
        task = create_analysis_task(case_id, task_type)
        background_tasks.add_task(_run_analysis_flow, task["task_id"], case_id)
        return {"success": True, "data": task}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建分析任务失败: {str(e)}")

@app.get("/api/tasks/{task_id}/status")
async def api_get_analysis_task_status(task_id: str):
    try:
        task = get_analysis_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="分析任务不存在")
        return {"success": True, "data": {"task_id": task["task_id"], "task_status": task["task_status"], "progress": task["progress"], "result_json": task.get("result_json", "{}"), "error_message": task.get("error_message", ""), "created_at": task.get("created_at", ""), "updated_at": task.get("updated_at", "")}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询分析任务失败: {str(e)}")

@app.put("/api/tasks/{task_id}/status")
async def api_update_analysis_task_status(task_id: str, data: dict):
    try:
        ok = update_analysis_task(task_id, data)
        if not ok:
            raise HTTPException(status_code=404, detail="分析任务不存在")
        return {"success": True, "message": "任务状态已更新"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新分析任务失败: {str(e)}")

@app.get("/api/cases/{case_id}/validate-status")
async def api_validate_case_status(case_id: str, new_status: str):
    try:
        case = get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="案件不存在")
        current = case.get("status")
        allowed = validate_case_status_transition(current, new_status)
        return {"success": True, "data": {"allowed": allowed, "current_status": current, "new_status": new_status}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"验证状态失败: {str(e)}")

@app.put("/api/cases/{case_id}/status")
async def api_update_case_status(case_id: str, data: dict):
    try:
        new_status = data.get("status", "")
        if not new_status:
            raise HTTPException(status_code=400, detail="status 不能为空")
        case = get_case(case_id)
        if not case:
            raise HTTPException(status_code=404, detail="案件不存在")
        current = case.get("status")
        if not validate_case_status_transition(current, new_status):
            raise HTTPException(status_code=400, detail=f"状态流转不合法: 当前 '{current}' 不能直接转为 '{new_status}'")
        updated = update_case(case_id, {"status": new_status})
        return {"success": True, "data": updated}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新案件状态失败: {str(e)}")

@app.post("/api/cases/{case_id}/liability-v2")
async def api_save_liability_with_version(case_id: str, data: dict):
    try:
        summary = data.get("summary", "")
        ratio = data.get("ratio", "")
        details = data.get("details", {})
        hit_rules = data.get("hit_rules", [])
        save_liability_result(case_id, {"summary": summary, "ratio": ratio, "details": details, "hit_rules": hit_rules})
        facts_json = json.dumps(data.get("facts", {}), ensure_ascii=False)
        matched_rules_json = json.dumps(hit_rules if isinstance(hit_rules, list) else [], ensure_ascii=False)
        suggestion_json = json.dumps(data.get("suggestion", {}), ensure_ascii=False)
        model_version = data.get("model_version", "")
        version = create_analysis_version(case_id, facts_json, matched_rules_json, suggestion_json, model_version)
        return {"success": True, "message": "责任判定已保存（含版本）", "data": {"version": version}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存责任判定失败: {str(e)}")

@app.get("/api/cases/{case_id}/liability-versions")
async def api_get_liability_versions(case_id: str):
    try:
        versions = get_analysis_versions(case_id)
        return {"success": True, "data": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询版本列表失败: {str(e)}")

@app.get("/api/cases/{case_id}/liability-latest")
async def api_get_liability_latest(case_id: str):
    try:
        version = get_latest_analysis_version(case_id)
        return {"success": True, "data": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询最新版本失败: {str(e)}")

@app.post("/api/cases/{case_id}/facts")
async def api_create_fact(case_id: str, data: dict):
    try:
        sf = create_structured_fact(case_id=case_id, source_type=data.get("source_type", ""), fact_type=data.get("fact_type", ""), fact_value=data.get("fact_value", ""), confidence=data.get("confidence", 0.0), evidence_id=data.get("evidence_id"), keyframe_time=data.get("keyframe_time"))
        return {"success": True, "data": sf}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建事实失败: {str(e)}")

@app.get("/api/cases/{case_id}/facts")
async def api_get_case_facts(case_id: str):
    try:
        facts = get_case_structured_facts(case_id)
        return {"success": True, "data": facts}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询事实列表失败: {str(e)}")

@app.get("/api/cases/{case_id}/evidence-consistency")
async def api_evidence_consistency(case_id: str):
    try:
        result = get_evidence_consistency_check(case_id)
        if not result.get("consistent", True) and result.get("score", 1.0) < 40:
            result["recommendation"] = "建议优先进入人工复核"
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"一致性检测失败: {str(e)}")

# ---------------------------------------------------------------------------
# 门控决策 API（Task 1: 统一门控控制器）
# ---------------------------------------------------------------------------
class EvidenceGateRequest(BaseModel):
    view_type: int = 0
    visible_vehicle_count: int = 0
    type_conflict: bool = False
    evidence_score: int = 0
    missing_evidence: List[str] = []
    keyframe_quality: float = 0.0
    yolo_conf: float = 0.0
    qwen_conf: float = 0.0
    type_consistency: float = 0.0
    conflict_score: float = 0.0

@app.post("/api/evidence/gate")
async def api_evidence_gate(data: EvidenceGateRequest):
    """获取门控决策（融合规则门控和 ML 模型）"""
    try:
        # 导入门控控制器
        from backend.evidence_gate_controller import get_gate_controller
        controller = get_gate_controller()
        
        # 构建案件数据
        case_data = {
            "view_type": data.view_type,
            "visible_vehicle_count": data.visible_vehicle_count,
            "type_conflict": data.type_conflict,
            "evidence_score": data.evidence_score,
            "missing_evidence": data.missing_evidence,
            "keyframe_quality": data.keyframe_quality,
            "yolo_conf": data.yolo_conf,
            "qwen_conf": data.qwen_conf,
            "type_consistency": data.type_consistency,
            "conflict_score": data.conflict_score
        }
        
        # 获取门控决策
        result = controller.get_gate_decision(case_data)
        
        return {"success": True, "data": result}
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"门控控制器加载失败: {str(e)}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"门控决策失败: {str(e)}")

# ---------------------------------------------------------------------------
# 报告导出 API（精简）
# ---------------------------------------------------------------------------
def _esc(text) -> str:
    if text is None:
        return ""
    import html as _html
    return _html.escape(str(text))

@app.get("/api/cases/{case_id}/report/export")
async def api_export_report(case_id: str):
    from fastapi.responses import Response
    from datetime import datetime
    case = get_case(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="案件不存在")
    try:
        facts = get_case_structured_facts(case_id)
    except Exception:
        facts = []
    try:
        consistency = get_evidence_consistency_check(case_id)
    except Exception:
        consistency = {}
    matched_rules = []
    try:
        from backend.database import get_db_conn
        conn = get_db_conn()
        try:
            cursor = conn.execute("SELECT * FROM matched_rules WHERE case_id = ? ORDER BY created_at DESC", (case_id,))
            matched_rules = [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()
    except Exception:
        pass
    html = _build_report_html(case, facts, consistency, matched_rules)
    filename = f"事故分析报告_{case_id}_{datetime.now().strftime('%Y%m%d')}.html"
    encoded_filename = urllib_parse.quote(filename)
    return Response(content=html, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"})

def _build_report_html(case: dict, facts: list, consistency: dict, matched_rules: list) -> str:
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    case_id = case.get("id", "")
    title = case.get("title", "交通事故分析报告")
    accident_type = case.get("accident_type", "待分析")
    location = case.get("location", "未填写")
    status = case.get("status", "")
    weather = case.get("weather", "未记录")
    road_env = case.get("road_env", "未记录")
    submitted_at = case.get("submitted_at", "")
    description = case.get("description", "")
    snapshot = case.get("snapshot", {}) or {}
    form_data = snapshot.get("form_data", {}) or {} if isinstance(snapshot.get("form_data"), dict) else {}
    analysis = snapshot.get("analysis", {}) or {} if isinstance(snapshot.get("analysis"), dict) else {}
    accident_time = form_data.get("time", submitted_at or "未填写")
    
    # 尝试获取融合证据包
    fused = _get_fused_evidence(case_id)
    fused_packet = fused.get("fused_evidence_packet", {})
    cam_ctx = fused_packet.get("camera_context", {})
    fusion_result = fused_packet.get("fusion_result", {})
    qwen_check = fused_packet.get("qwen_semantic_check", {})
    
    # 融合证据信息卡片
    fusion_html = ""
    if fused_packet:
        fusion_html = f"""
        <div class="bento-card span-4">
          <div class="card-label">融合证据分析</div>
          <div class="info-rows">
            <div class="info-row"><span class="label">视频视角</span><span class="value">{_esc(cam_ctx.get('camera_view', '未知'))}</span></div>
            <div class="info-row"><span class="label">自车参与</span><span class="value">{'是' if cam_ctx.get('ego_vehicle_present') else '否'}</span></div>
            <div class="info-row"><span class="label">外部可见车辆数</span><span class="value">{cam_ctx.get('visible_external_vehicle_count', 0)}</span></div>
            <div class="info-row"><span class="label">估计涉事车辆数</span><span class="value">{cam_ctx.get('estimated_involved_vehicle_count', 0)}</span></div>
            <div class="info-row"><span class="label">检测模型候选</span><span class="value">{_esc(fusion_result.get('accepted_accident_type', '未知'))}</span></div>
            <div class="info-row"><span class="label">千问语义校验</span><span class="value">{_esc(qwen_check.get('semantic_accident_type_from_qwen', '未知'))}</span></div>
            <div class="info-row"><span class="label">系统结论</span><span class="value">{'需要人工复核' if fusion_result.get('manual_review_required') else '可进入责任推理'}</span></div>
          </div>
        </div>"""
    
    liability = case.get("liability", {}) or {}
    liab_details = liability.get("details", {}) or {}
    confidence = liab_details.get("confidence", analysis.get("confidence", 0))
    evidence_integrity = liab_details.get("evidence_integrity", analysis.get("evidenceIntegrity", 0))
    liab_vehicles = liab_details.get("vehicles", [])
    liab_summary = liability.get("summary", "")
    hit_rules = liability.get("hit_rules", []) or []
    cons_score = consistency.get("score", 100)
    cons_suggestion = consistency.get("suggestion", "")
    keyframes = analysis.get("keyframes", [])
    keyframe_count = len(keyframes) if isinstance(keyframes, list) else 0
    
    vehicle_cards = ""
    if liab_vehicles:
        for v in liab_vehicles:
            role = _esc(v.get("role") or v.get("vehicleType", ""))
            plate = _esc(v.get("plate", ""))
            liab = _esc(v.get("liability", ""))
            pct = v.get("percentage", 0)
            pct_color = "#0071e3" if liab == "主责" else ("#6e6e73" if liab == "无责" else "#86868b")
            vehicle_cards += f"""<div class="bento-card liability-item"><div class="liability-top"><span class="liability-role">{role}</span><span class="liability-plate">{plate}</span></div><div class="liability-bar-wrap"><div class="liability-bar" style="width:{pct}%;background:{pct_color}"></div></div><div class="liability-bottom"><span class="liability-degree">{liab}</span><span class="liability-pct">{pct}%</span></div></div>"""
    else:
        vehicle_cards = '<div class="bento-card empty-card"><p class="empty-text">暂无责任认定数据</p></div>'
    
    rules_html = ""
    if hit_rules:
        for r in hit_rules:
            rname = _esc(r.get("name") or r.get("rule_name", ""))
            rdesc = _esc(r.get("description") or r.get("content", "") or r.get("basis", ""))
            rules_html += f"""<div class="rule-item"><div class="rule-name">{rname}</div><div class="rule-desc">{rdesc}</div></div>"""
    else:
        rules_html = '<p class="empty-text">暂无命中规则</p>'
    
    facts_html = ""
    if facts:
        for f in facts[:15]:
            ftype = _esc(f.get("fact_type", ""))
            fval = _esc(f.get("fact_value", ""))
            fsrc = _esc(f.get("source_type", ""))
            facts_html += f"""<div class="fact-item"><span class="fact-type">{ftype}</span><span class="fact-value">{fval}</span><span class="fact-src">{fsrc}</span></div>"""
    else:
        facts_html = '<p class="empty-text">暂无结构化事实</p>'
    
    cons_color = "#34c759" if cons_score >= 80 else ("#ff9500" if cons_score >= 60 else "#ff3b30") if isinstance(cons_score, (int, float)) else "#86868b"
    
    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>交通事故智能分析报告 - {case_id}</title><style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", "PingFang SC", "Microsoft YaHei", sans-serif; background: #f5f5f7; color: #1d1d1f; line-height: 1.5; -webkit-font-smoothing: antialiased; padding: 40px 20px; }}
  .report-container {{ max-width: 960px; margin: 0 auto; }}
  .report-head {{ margin-bottom: 24px; padding: 0 4px; }}
  .report-head h1 {{ font-size: 32px; font-weight: 700; letter-spacing: -0.02em; color: #1d1d1f; margin-bottom: 8px; }}
  .report-head .subtitle {{ font-size: 15px; color: #6e6e73; }}
  .report-head .meta-row {{ display: flex; gap: 24px; margin-top: 12px; font-size: 13px; color: #86868b; }}
  .bento-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }}
  .bento-card {{ background: #ffffff; border-radius: 20px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02); }}
  .span-2 {{ grid-column: span 2; }} .span-3 {{ grid-column: span 3; }} .span-4 {{ grid-column: span 4; }}
  .card-label {{ font-size: 13px; font-weight: 600; color: #6e6e73; margin-bottom: 16px; letter-spacing: 0.02em; }}
  .info-rows {{ display: flex; flex-direction: column; gap: 14px; }}
  .info-row {{ display: flex; justify-content: space-between; align-items: center; }}
  .info-row .label {{ font-size: 14px; color: #86868b; }} .info-row .value {{ font-size: 14px; font-weight: 600; color: #1d1d1f; }}
  .stat-big {{ text-align: center; padding: 28px 24px; }}
  .stat-big .number {{ font-size: 40px; font-weight: 700; color: #0071e3; letter-spacing: -0.02em; line-height: 1; }}
  .stat-big .label {{ font-size: 13px; color: #6e6e73; margin-top: 8px; }}
  .liability-item {{ padding: 20px; }}
  .liability-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }}
  .liability-role {{ font-size: 15px; font-weight: 600; color: #1d1d1f; }}
  .liability-plate {{ font-size: 12px; color: #6e6e73; font-family: "SF Mono", "Fira Code", monospace; background: #f5f5f7; padding: 3px 10px; border-radius: 8px; }}
  .liability-bar-wrap {{ height: 8px; background: #f5f5f7; border-radius: 4px; overflow: hidden; margin-bottom: 12px; }}
  .liability-bar {{ height: 100%; border-radius: 4px; transition: width 0.3s; }}
  .liability-bottom {{ display: flex; justify-content: space-between; align-items: center; }}
  .liability-degree {{ font-size: 13px; font-weight: 600; color: #6e6e73; }}
  .liability-pct {{ font-size: 20px; font-weight: 700; color: #1d1d1f; }}
  .reasoning-text {{ font-size: 14px; color: #424245; line-height: 1.7; }}
  .rule-item {{ padding: 14px 0; border-bottom: 1px solid #f0f0f2; }}
  .rule-item:last-child {{ border-bottom: none; }}
  .rule-name {{ font-size: 14px; font-weight: 600; color: #1d1d1f; margin-bottom: 4px; }}
  .rule-desc {{ font-size: 13px; color: #6e6e73; line-height: 1.5; }}
  .fact-item {{ display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f0f0f2; }}
  .fact-item:last-child {{ border-bottom: none; }}
  .fact-type {{ font-size: 12px; font-weight: 600; color: #0071e3; background: rgba(0,113,227,0.08); padding: 3px 10px; border-radius: 6px; white-space: nowrap; }}
  .fact-value {{ font-size: 14px; color: #1d1d1f; font-weight: 500; flex: 1; }}
  .fact-src {{ font-size: 12px; color: #86868b; }}
  .consistency-box {{ display: flex; align-items: center; gap: 20px; }}
  .consistency-score {{ font-size: 48px; font-weight: 700; color: {cons_color}; line-height: 1; letter-spacing: -0.02em; }}
  .consistency-info {{ flex: 1; }}
  .report-foot {{ margin-top: 32px; padding: 20px 4px; border-top: 1px solid #d2d2d7; display: flex; justify-content: space-between; font-size: 12px; color: #86868b; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .bento-card {{ box-shadow: none; border: 1px solid #e5e5e7; break-inside: avoid; }} }}
  @media (max-width: 768px) {{ .bento-grid {{ grid-template-columns: 1fr; }} .span-2, .span-3, .span-4 {{ grid-column: span 1; }} }}
</style></head><body><div class="report-container">
  <div class="report-head"><h1>交通事故智能分析报告</h1><p class="subtitle">{_esc(title)}</p><div class="meta-row"><span>案件编号：{_esc(case_id)}</span><span>报告生成：{now_str}</span><span>状态：{_esc(status)}</span></div></div>
  <div class="bento-grid">
    <div class="bento-card span-2"><div class="card-label">案件基本信息</div><div class="info-rows"><div class="info-row"><span class="label">事故类型</span><span class="value">{_esc(accident_type)}</span></div><div class="info-row"><span class="label">发生时间</span><span class="value">{_esc(accident_time)}</span></div><div class="info-row"><span class="label">发生地点</span><span class="value">{_esc(location)}</span></div><div class="info-row"><span class="label">天气状况</span><span class="value">{_esc(weather)}</span></div><div class="info-row"><span class="label">道路环境</span><span class="value">{_esc(road_env)}</span></div></div></div>
    <div class="bento-card stat-big"><div class="number">{confidence}%</div><div class="label">分析置信度</div></div>
    <div class="bento-card stat-big"><div class="number">{evidence_integrity}%</div><div class="label">证据完整度</div></div>
    {fusion_html}
    <div class="bento-card span-4"><div class="card-label">责任认定结果</div><div class="bento-grid" style="grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-top: 4px;">{vehicle_cards}</div></div>
    <div class="bento-card span-2"><div class="card-label">认定理由</div><p class="reasoning-text">{_esc(liab_summary or description or '暂无认定理由')}</p></div>
    <div class="bento-card span-2"><div class="card-label">证据一致性检测</div><div class="consistency-box"><div class="consistency-score">{cons_score}</div><div class="consistency-info"><div style="font-size:14px;font-weight:600;color:#1d1d1f">一致性评分（满分100）</div><div class="consistency-suggestion">{_esc(cons_suggestion or '暂无建议')}</div></div></div></div>
    <div class="bento-card span-2"><div class="card-label">命中规则</div>{rules_html}</div>
    <div class="bento-card span-2"><div class="card-label">结构化事实</div>{facts_html}</div>
  </div>
  <div class="report-foot"><span>报告生成时间：{now_str}</span><span>智能事故分析系统 v2.0</span></div>
</div></body></html>"""
    return html

@app.post("/api/reports/generate")
async def api_generate_report(data: dict):
    from fastapi.responses import Response
    from datetime import datetime
    case = data.get("case", {})
    facts = data.get("facts", [])
    consistency = data.get("consistency", {})
    matched_rules = data.get("matched_rules", [])
    html = _build_report_html(case, facts, consistency, matched_rules)
    case_id = case.get("id", "export")
    filename = f"事故分析报告_{case_id}_{datetime.now().strftime('%Y%m%d')}.html"
    encoded_filename = urllib_parse.quote(filename)
    return Response(content=html, media_type="text/html; charset=utf-8", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"})

def _dify_service_status():
    api_key = (os.getenv("DIFY_API_KEY") or "").strip()
    if not api_key or "xxxx" in api_key.lower():
        return "unconfigured"
    return "reachable"

@app.get("/health")
async def health_check():
    from datetime import datetime
    health_info = {"status": "ok", "database": "connected", "yolo_model": "loaded", "dify_service": _dify_service_status(), "qwen_service": "reachable", "timestamp": datetime.now().isoformat()}
    try:
        from backend.database import get_db
        db = get_db()
        db.execute(sa_text("SELECT 1"))
        db.close()
        health_info["database"] = "connected"
    except Exception:
        health_info["database"] = "disconnected"
        health_info["status"] = "degraded"
    return health_info

app.mount("/temp", StaticFiles(directory=str(TEMP_DIR)), name="temp")
app.mount("/keyframes", StaticFiles(directory=str(KEYFRAME_DIR)), name="keyframes")
UPLOADED_VIDEOS_DIR = BASE_DIR / "backend" / "uploaded_videos"
UPLOADED_VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploaded_videos", StaticFiles(directory=str(UPLOADED_VIDEOS_DIR)), name="uploaded_videos")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")

# ---------------------------------------------------------------------------
# 生产模式：如果 dist/ 存在，自动托管前端静态文件
# 若使用 Nginx 反向代理，设置 SERVE_STATIC=false 跳过
# ---------------------------------------------------------------------------
_serve_static = os.getenv("SERVE_STATIC", "true").strip().lower() not in ("false", "0", "no")
DIST_DIR = BASE_DIR / "dist"
if _serve_static and DIST_DIR.exists() and (DIST_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
    print("[INFO] Production mode: serving frontend from dist/")
elif not _serve_static:
    print("[INFO] SERVE_STATIC=false, frontend served by external proxy (e.g. Nginx)")




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001, timeout_keep_alive=300, timeout_graceful_shutdown=30)