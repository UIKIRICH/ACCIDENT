"""
复核辅助服务：整合所有复核辅助功能
"""
from typing import Dict, Any, Optional
from datetime import datetime

from backend.models.review_assist import ReviewAssistResult
from backend.services.review_focus_service import (
    identify_review_focus,
    calculate_priority_score,
    generate_evidence_required_items,
    generate_conflict_summary,
    determine_evidence_status,
    generate_risk_notes,
    map_route_type_to_cn
)


def generate_review_assist(case_id: str, case_data: dict) -> Dict[str, Any]:
    """
    生成复核辅助结果
    
    Args:
        case_id: 案件ID
        case_data: 案件数据字典
    
    Returns:
        复核辅助结果字典
    """
    # 1. 识别复核重点
    review_focus = identify_review_focus(case_data)
    
    # 2. 计算优先级评分
    priority_result = calculate_priority_score(case_data)
    review_priority_score = priority_result["score"]
    review_priority_level = priority_result["level"]
    
    # 3. 生成补证提示
    evidence_required_items = generate_evidence_required_items(case_data)
    
    # 4. 生成冲突摘要
    conflict_summary = generate_conflict_summary(case_data)
    
    # 5. 判断证据状态
    evidence_status = determine_evidence_status(case_data)
    
    # 6. 生成风险提示
    risk_notes = generate_risk_notes(case_data, review_focus, review_priority_level)
    
    # 7. 确定路由类型
    route_type = case_data.get("system_route", "manual_review_required")
    route_type_cn = map_route_type_to_cn(route_type)
    
    # 8. 构建结果
    now = datetime.now()
    result = {
        "case_id": case_id,
        "route_type": route_type,
        "route_type_cn": route_type_cn,
        "review_focus": review_focus,
        "review_priority_score": review_priority_score,
        "review_priority_level": review_priority_level,
        "conflict_summary": conflict_summary,
        "evidence_status": evidence_status,
        "evidence_required_items": evidence_required_items,
        "risk_notes": risk_notes,
        "created_at": now,
        "updated_at": now
    }
    
    return result


def get_review_assist_from_fused_evidence(case_id: str, fused_packet: dict) -> Optional[Dict[str, Any]]:
    """
    从融合证据包中提取或生成复核辅助结果
    
    Args:
        case_id: 案件ID
        fused_packet: 融合证据包
    
    Returns:
        复核辅助结果字典，如果无法生成则返回 None
    """
    if not fused_packet:
        return None
    
    try:
        # 从融合证据包中提取关键字段
        camera_context = fused_packet.get("camera_context", {})
        fusion_result = fused_packet.get("fusion_result", {})
        qwen_check = fused_packet.get("qwen_semantic_check", {})
        
        # 构建 case_data
        case_data = {
            "system_route": "manual_review_required" if fusion_result.get("manual_review_required") else "proceed_to_liability",
            "type_conflict_detected": fusion_result.get("conflict_detected", False),
            "evidence_completeness_score": 8 if not fusion_result.get("manual_review_required") else 4,
            "Case Perspective": camera_context.get("camera_view", "unknown"),
            "ego_vehicle_present": camera_context.get("ego_vehicle_present", False),
            "yolo_confidence": fusion_result.get("detector_output", {}).get("detector_type_confidence", 0.0),
            "qwen_confidence": qwen_check.get("semantic_confidence", 0.0),
            "yolo_candidate_type": fusion_result.get("detector_output", {}).get("candidate_accident_type_from_detector", "unknown"),
            "qwen_candidate_type": qwen_check.get("semantic_accident_type_from_qwen", "unknown"),
            "route_reason": fusion_result.get("status_reason", ""),
            "video_available": True,
            "keyframe_count": 5,  # 假设有关键帧
            "image_available": True,
            "structured_fact_available": True,
            "has_other_view": False,
            "evidence": {}
        }
        
        # 生成复核辅助结果
        return generate_review_assist(case_id, case_data)
    
    except Exception as e:
        print(f"[WARN] 从融合证据包生成复核辅助结果失败: {e}")
        return None