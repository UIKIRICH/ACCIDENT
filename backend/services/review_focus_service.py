"""
复核辅助服务：实现复核重点识别、优先级评分、补证提示等功能
"""
from typing import List, Dict, Any


def identify_review_focus(case_data: dict) -> List[str]:
    """
    识别复核重点
    
    Args:
        case_data: 案件数据字典，包含以下字段：
            - type_conflict_detected: bool/str
            - evidence_completeness_score: int (0-10)
            - Case Perspective: str
            - ego_vehicle_present: bool
            - yolo_confidence: float
            - qwen_confidence: float
            - yolo_candidate_type: str
            - qwen_candidate_type: str
    
    Returns:
        复核重点列表
    """
    review_focus = []
    
    # 1. 类型冲突检测
    type_conflict = case_data.get("type_conflict_detected")
    if type_conflict == "是" or type_conflict is True:
        review_focus.append("类型冲突")
    
    # 2. 证据不足检测
    evidence_score = case_data.get("evidence_completeness_score", 10)
    if isinstance(evidence_score, (int, float)) and evidence_score < 6:
        review_focus.append("证据不足")
    
    # 3. 视角不完整检测（行车记录仪且自车参与）
    perspective = str(case_data.get("Case Perspective", ""))
    ego_present = case_data.get("ego_vehicle_present", False)
    if "行车记录仪" in perspective and ego_present is True:
        review_focus.append("视角不完整")
    
    # 4. 低置信度检测
    yolo_conf = case_data.get("yolo_confidence", 1.0)
    qwen_conf = case_data.get("qwen_confidence", 1.0)
    if (isinstance(yolo_conf, (int, float)) and yolo_conf < 0.5) or \
       (isinstance(qwen_conf, (int, float)) and qwen_conf < 0.5):
        review_focus.append("低置信度")
    
    # 5. 责任敏感类型检测
    sensitive_types = ["rear_end", "turn_conflict", "lane_change_collision", "side_collision"]
    yolo_type = str(case_data.get("yolo_candidate_type", "")).lower()
    qwen_type = str(case_data.get("qwen_candidate_type", "")).lower()
    accident_type = yolo_type or qwen_type
    if accident_type in sensitive_types:
        review_focus.append("责任敏感")
    
    # 6. 默认情况：证据充分则快速确认
    if not review_focus:
        review_focus.append("快速确认")
    
    return review_focus


def calculate_priority_score(case_data: dict) -> Dict[str, Any]:
    """
    计算复核优先级评分（0-100分）
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        包含 score 和 level 的字典
    """
    score = 30  # 基础分
    
    # 类型冲突：+25分
    type_conflict = case_data.get("type_conflict_detected")
    if type_conflict == "是" or type_conflict is True:
        score += 25
    
    # 证据不足：+20分
    evidence_score = case_data.get("evidence_completeness_score", 10)
    if isinstance(evidence_score, (int, float)) and evidence_score < 6:
        score += 20
    
    # 行车记录仪视角且自车参与：+15分
    perspective = str(case_data.get("Case Perspective", ""))
    ego_present = case_data.get("ego_vehicle_present", False)
    if "行车记录仪" in perspective and ego_present is True:
        score += 15
    
    # 低置信度：+15分
    yolo_conf = case_data.get("yolo_confidence", 1.0)
    qwen_conf = case_data.get("qwen_confidence", 1.0)
    if (isinstance(yolo_conf, (int, float)) and yolo_conf < 0.5) or \
       (isinstance(qwen_conf, (int, float)) and qwen_conf < 0.5):
        score += 15
    
    # 责任敏感类型：+10分
    sensitive_types = ["rear_end", "turn_conflict", "lane_change_collision", "side_collision"]
    yolo_type = str(case_data.get("yolo_candidate_type", "")).lower()
    qwen_type = str(case_data.get("qwen_candidate_type", "")).lower()
    accident_type = yolo_type or qwen_type
    if accident_type in sensitive_types:
        score += 10
    
    # 分数截断
    score = min(score, 100)
    
    # 分级
    if score >= 70:
        level = "高"
    elif score >= 40:
        level = "中"
    else:
        level = "低"
    
    return {"score": score, "level": level}


def generate_evidence_required_items(case_data: dict) -> List[str]:
    """
    生成补证提示列表
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        需要补充的证据列表
    """
    items = []
    
    # 视频缺失
    video_available = case_data.get("video_available", True)
    if video_available == "否" or video_available is False:
        items.append("需要补充事故视频")
    
    # 关键帧缺失
    keyframe_count = case_data.get("keyframe_count", 0)
    if isinstance(keyframe_count, (int, float)) and keyframe_count == 0:
        items.append("需要补充关键碰撞帧")
    
    # 图片缺失
    image_available = case_data.get("image_available", True)
    if image_available == "否" or image_available is False:
        items.append("需要补充现场图片或车损图片")
    
    # 结构化事实缺失
    structured_fact_available = case_data.get("structured_fact_available", True)
    if structured_fact_available == "否" or structured_fact_available is False:
        items.append("需要补充事故描述文本")
    
    # 视角不完整（行车记录仪且无其他视角）
    perspective = str(case_data.get("Case Perspective", ""))
    has_other_view = case_data.get("has_other_view", False)
    if "行车记录仪" in perspective and not has_other_view:
        items.append("建议补充另一视角视频或现场照片")
    
    # 碰撞部位不清
    route_reason = str(case_data.get("route_reason", ""))
    evidence = case_data.get("evidence", {})
    if isinstance(evidence, dict):
        collision_point_clear = evidence.get("collision_point_clear", True)
        if collision_point_clear is False or "碰撞部位" in route_reason:
            items.append("建议补充车损部位图片")
    
    # 默认情况
    if not items:
        items.append("当前证据基本完整，可进入责任推理")
    
    return items


def generate_conflict_summary(case_data: dict) -> Optional[str]:
    """
    生成冲突摘要
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        冲突摘要文本，如果无冲突则返回 None
    """
    type_conflict = case_data.get("type_conflict_detected")
    if type_conflict != "是" and type_conflict is not True:
        return None
    
    # 从 route_reason 中提取冲突信息
    route_reason = str(case_data.get("route_reason", ""))
    if route_reason:
        return f"检测模型与语义校验存在类型冲突：{route_reason}"
    
    # 默认冲突描述
    yolo_type = case_data.get("yolo_candidate_type", "unknown")
    qwen_type = case_data.get("qwen_candidate_type", "unknown")
    return f"检测模型识别为 '{yolo_type}'，千问语义校验识别为 '{qwen_type}'，两者不一致"


def determine_evidence_status(case_data: dict) -> str:
    """
    判断证据状态
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        证据状态：充分 / 有冲突 / 不足
    """
    # 有冲突
    type_conflict = case_data.get("type_conflict_detected")
    if type_conflict == "是" or type_conflict is True:
        return "有冲突"
    
    # 证据不足
    evidence_score = case_data.get("evidence_completeness_score", 10)
    if isinstance(evidence_score, (int, float)) and evidence_score < 6:
        return "不足"
    
    # 默认：充分
    return "充分"


def generate_risk_notes(case_data: dict, review_focus: List[str], priority_level: str) -> str:
    """
    生成风险提示
    
    Args:
        case_data: 案件数据字典
        review_focus: 复核重点列表
        priority_level: 优先级等级（高/中/低）
    
    Returns:
        风险提示文本
    """
    # 高优先级
    if priority_level == "高":
        if "类型冲突" in review_focus:
            return "该案例存在类型冲突，不适合直接快速确认，应进入人工重点复核。"
        elif "证据不足" in review_focus:
            return "该案例证据严重不足，无法进行有效责任认定，需补充关键证据后再审。"
        else:
            return "该案例复杂度较高，建议人工重点复核。"
    
    # 中优先级
    elif priority_level == "中":
        if "视角不完整" in review_focus:
            return "该案例视角受限，可能存在盲区，建议复核时注意画面外信息。"
        elif "低置信度" in review_focus:
            return "该案例检测置信度较低，建议复核时结合其他证据综合判断。"
        else:
            return "该案例存在一定不确定性，建议人工复核确认。"
    
    # 低优先级
    else:
        return "证据充分，可快速确认。"


def map_route_type_to_cn(route_type: str) -> str:
    """
    将路由类型映射为中文
    
    Args:
        route_type: 路由类型（manual_review_required / proceed_to_liability / insufficient_evidence）
    
    Returns:
        中文路由类型
    """
    mapping = {
        "manual_review_required": "重点复核",
        "proceed_to_liability": "快速确认",
        "insufficient_evidence": "补证复核"
    }
    return mapping.get(route_type, "未知")