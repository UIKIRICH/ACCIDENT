"""
复核辅助服务：实现复核重点识别、优先级评分、补证提示等功能
严格按照任务要求实现
"""
from typing import List, Dict, Any


def identify_review_focus(case_data: dict) -> List[str]:
    """
    识别复核重点（可多选）
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        复核重点列表
    """
    review_focus = []
    
    # 1. 模型结论冲突
    type_conflict = _get_str(case_data.get("type_conflict_detected"))
    if type_conflict == "是":
        review_focus.append("模型结论冲突")
    
    # 2. 视角不完整：行车记录仪视角
    perspective = _get_str(case_data.get("Case Perspective"))
    if "行车记录仪" in perspective:
        review_focus.append("视角不完整")
    
    # 3. 责任敏感：事故类型属于追尾、变道碰撞、转弯未让行、侧向碰撞、多车事故
    sensitive_types = ["追尾", "变道碰撞", "转弯未让行", "侧向碰撞", "多车事故"]
    yolo_type = _get_str(case_data.get("yolo_candidate_type"))
    qwen_type = _get_str(case_data.get("qwen_candidate_type"))
    system_route = _get_str(case_data.get("system_route"))
    route_reason = _get_str(case_data.get("route_reason"))
    
    # 检查是否属于责任敏感类型
    accident_type_text = f"{yolo_type} {qwen_type} {system_route} {route_reason}"
    for sensitive_type in sensitive_types:
        if sensitive_type in accident_type_text:
            review_focus.append("责任敏感")
            break
    
    # 多车事故判断
    vehicle_count = case_data.get("estimated_involved_vehicle_count", 0)
    if isinstance(vehicle_count, (int, float)) and vehicle_count > 2:
        if "责任敏感" not in review_focus:
            review_focus.append("责任敏感")
    
    # 4. 证据不足
    evidence_score = case_data.get("evidence_completeness_score")
    if isinstance(evidence_score, (int, float)) and evidence_score < 6:
        review_focus.append("证据不足")
    
    # 5. 低置信度
    yolo_conf = case_data.get("yolo_confidence")
    qwen_conf = case_data.get("qwen_confidence")
    low_conf = False
    if isinstance(yolo_conf, (int, float)) and yolo_conf < 0.5:
        low_conf = True
    if isinstance(qwen_conf, (int, float)) and qwen_conf < 0.5:
        low_conf = True
    if low_conf:
        review_focus.append("低置信度")
    
    # 6. 规则依据需核对：仅在类型冲突时触发（微调）
    if type_conflict == "是":
        review_focus.append("规则依据需核对")
    
    # 7. 报告生成验证
    report_generated = _get_str(case_data.get("report_generated"))
    if report_generated == "否":
        review_focus.append("报告生成验证")
    
    # 8. 快速确认（仅当以上条件均不满足时）
    if not review_focus:
        review_focus.append("快速确认")
    
    return review_focus


def calculate_priority_score(case_data: dict) -> Dict[str, Any]:
    """
    计算复核优先级评分（0-100分）
    微调版本：基础分35，高阈值65，责任敏感+8
    """
    # 提取字段
    type_conflict = _get_str(case_data.get("type_conflict_detected"))
    perspective = _get_str(case_data.get("Case Perspective"))
    human_decision = _get_str(case_data.get("human_review_decision"))
    system_suggestion = _get_str(case_data.get("system_liability_suggestion"))
    report_generated = _get_str(case_data.get("report_generated"))
    route_reason = _get_str(case_data.get("route_reason"))
    evidence_score = case_data.get("evidence_completeness_score")
    yolo_conf = case_data.get("yolo_confidence")
    qwen_conf = case_data.get("qwen_confidence")
    vehicle_count = case_data.get("estimated_involved_vehicle_count", 0)
    system_route = _get_str(case_data.get("system_route"))

    score = 35  # 基础分从30提高到35
    reasons = []

    # ====== 快速确认特殊处理 ======
    if (type_conflict == "否" and 
        isinstance(evidence_score, (int, float)) and evidence_score >= 8 and
        system_route == "proceed_to_liability"):
        score = 20
        reasons.append("快速确认案例，基础分20")
        if "行车记录仪" in perspective:
            score += 5
            reasons.append("行车记录仪视角(+5)")
        if human_decision and system_suggestion and human_decision == system_suggestion:
            score -= 5
            reasons.append("人工结论与系统建议一致(-5)")
        if isinstance(vehicle_count, (int, float)) and vehicle_count > 3:
            score += 5
            reasons.append("多车事故(+5)")
        return {"score": max(0, min(score, 100)), "level": "低" if score < 40 else "中", "reason": "；".join(reasons)}

    # ====== 加分项 ======
    # 1. 模型结论冲突：+20
    if type_conflict == "是":
        score += 20
        reasons.append("模型结论冲突(+20)")

    # 2. 行车记录仪视角：+5
    if "行车记录仪" in perspective:
        score += 5
        reasons.append("行车记录仪视角(+5)")

    # 3. 证据不足：+15
    if isinstance(evidence_score, (int, float)) and evidence_score < 6:
        score += 15
        reasons.append("证据不足(+15)")

    # 4. 责任敏感事故类型：+8（从5提高到8）
    sensitive_types = ["追尾", "变道碰撞", "转弯未让行", "侧向碰撞", "多车事故"]
    yolo_type = _get_str(case_data.get("yolo_candidate_type"))
    qwen_type = _get_str(case_data.get("qwen_candidate_type"))
    accident_type_text = f"{yolo_type} {qwen_type} {system_route} {route_reason}"
    is_sensitive = False
    for sensitive_type in sensitive_types:
        if sensitive_type in accident_type_text:
            is_sensitive = True
            break
    if is_sensitive:
        score += 8
        reasons.append("责任敏感(+8)")

    # 5. 多车事故：+5
    if isinstance(vehicle_count, (int, float)) and vehicle_count > 3:
        score += 5
        reasons.append("多车事故(+5)")

    # 6. 低置信度：阈值<0.4
    if isinstance(yolo_conf, (int, float)) and yolo_conf < 0.4:
        score += 5
        reasons.append("低置信度(+5)")

    # 7. 规则依据需核对：仅在 type_conflict 时加 +5
    if type_conflict == "是":
        score += 5
        reasons.append("规则依据需核对(+5)")

    # 8. 复杂路况：+15
    if "复杂" in route_reason or "多车" in route_reason:
        score += 15
        reasons.append("复杂路况(+15)")

    # 9. 报告生成失败：+10
    if report_generated == "否":
        score += 10
        reasons.append("报告生成失败(+10)")

    # ====== 减分项 ======
    # 1. YOLO与视频语义模型一致：-20
    if type_conflict == "否":
        score -= 20
        reasons.append("YOLO与视频语义模型一致(-20)")

    # 2. 监控视角：-5
    if "交通监控" in perspective:
        score -= 5
        reasons.append("监控视角(-5)")

    # 3. 报告生成成功：-15
    if report_generated == "是":
        score -= 15
        reasons.append("报告生成成功(-15)")

    # 4. 人工复核未修改系统建议：-15
    if human_decision and system_suggestion and human_decision == system_suggestion:
        score -= 15
        reasons.append("人工未修改系统建议(-15)")

    # 限制范围
    score = max(0, min(100, score))

    # 等级划分（高阈值65，中阈值40）
    if score >= 65:
        level = "高"
    elif score >= 40:
        level = "中"
    else:
        level = "低"

    reason_text = "；".join(reasons) if reasons else "基础分35"
    return {"score": score, "level": level, "reason": reason_text}


def generate_evidence_required_items(case_data: dict) -> List[str]:
    """
    生成补证或核对建议列表
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        需要补充的证据列表
    """
    items = []
    
    # 若 video_available == "否" → “需要补充事故视频”
    video_available = _get_str(case_data.get("video_available"))
    if video_available == "否":
        items.append("需要补充事故视频")
    
    # 若 route_reason 含“关键帧”或“关键证据缺失” → “需要补充关键碰撞帧”
    route_reason = _get_str(case_data.get("route_reason"))
    if "关键帧" in route_reason or "关键证据缺失" in route_reason:
        items.append("需要补充关键碰撞帧")
    
    # 若 image_available == "否" → “需要补充现场图片或车损图片”
    image_available = _get_str(case_data.get("image_available"))
    if image_available == "否":
        items.append("需要补充现场图片或车损图片")
    
    # 若 structured_fact_available == "否" → “需要补充事故描述文本”
    structured_fact_available = _get_str(case_data.get("structured_fact_available"))
    if structured_fact_available == "否":
        items.append("需要补充事故描述文本")
    
    # 若行车记录仪视角 → “建议补充另一视角视频或现场照片”
    perspective = _get_str(case_data.get("Case Perspective"))
    if "行车记录仪" in perspective:
        items.append("建议补充另一视角视频或现场照片")
    
    # 若 route_reason 含“碰撞部位”或“接触点” → “建议补充车损部位图片”
    if "碰撞部位" in route_reason or "接触点" in route_reason:
        items.append("建议补充车损部位图片")
    
    # 若 type_conflict_detected == "是" → 额外建议
    type_conflict = _get_str(case_data.get("type_conflict_detected"))
    if type_conflict == "是":
        items.append("建议核对关键帧和车辆行为")
        items.append("建议核对规则依据和结构化事实")
    
    # 若以上无任何项，则默认
    if not items:
        items.append("当前证据基本完整，建议核对规则依据和责任建议")
    
    return items


def generate_conflict_summary(case_data: dict) -> str:
    """
    生成冲突摘要
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        冲突摘要文本
    """
    type_conflict = _get_str(case_data.get("type_conflict_detected"))
    yolo_type = _get_str(case_data.get("yolo_candidate_type"))
    qwen_type = _get_str(case_data.get("qwen_candidate_type"))
    human_decision = _get_str(case_data.get("human_review_decision"))
    system_suggestion = _get_str(case_data.get("system_liability_suggestion"))
    
    # 若类型冲突
    if type_conflict == "是":
        return f"YOLO 初步判定为 {yolo_type or 'unknown'}，视频语义模型 判断为 {qwen_type or 'unknown'}，两者在事故类型上存在差异，建议人工核对关键帧和车辆行为。"
    
    # 若无冲突但人工结论与系统建议不同
    if human_decision and system_suggestion and human_decision != system_suggestion:
        return "YOLO 与视频语义模型 判断基本一致，但人工复核结论与系统责任建议存在差异，建议核对规则依据。"
    
    # 若无冲突且一致
    return "YOLO 与视频语义模型 判断基本一致，建议人工核对规则依据和责任建议。"


def determine_evidence_status(case_data: dict) -> str:
    """
    判断证据状态
    
    Args:
        case_data: 案件数据字典
    
    Returns:
        证据状态：证据充分 / 证据有冲突 / 证据不足 / 证据需核对
    """
    type_conflict = _get_str(case_data.get("type_conflict_detected"))
    evidence_score = case_data.get("evidence_completeness_score")
    
    # 若 type_conflict_detected == "是" → 证据有冲突
    if type_conflict == "是":
        return "证据有冲突"
    
    # 若 evidence_completeness_score < 6 → 证据不足
    if isinstance(evidence_score, (int, float)) and evidence_score < 6:
        return "证据不足"
    
    # 若 type_conflict_detected == "否" 且 evidence_completeness_score >= 6 → 证据充分
    if type_conflict == "否" and isinstance(evidence_score, (int, float)) and evidence_score >= 6:
        return "证据充分"
    
    # 否则 → 证据需核对（兜底）
    return "证据需核对"


def generate_risk_notes(case_data: dict, review_focus: List[str], priority_level: str) -> str:
    """
    根据复核重点组合生成风险提示
    
    Args:
        case_data: 案件数据字典
        review_focus: 复核重点列表
        priority_level: 优先级等级
    
    Returns:
        风险提示文本
    """
    has_model_conflict = "模型结论冲突" in review_focus
    has_incomplete_view = "视角不完整" in review_focus
    has_liability_sensitive = "责任敏感" in review_focus
    has_insufficient_evidence = "证据不足" in review_focus
    has_quick_confirm = "快速确认" in review_focus
    
    # 优先采用模板
    if has_model_conflict and has_liability_sensitive:
        return "该案例存在模型结论冲突和责任敏感因素，建议人工重点复核。"
    
    if has_model_conflict:
        return "该案例存在模型结论冲突，建议人工重点复核。"
    
    if has_incomplete_view:
        return "该案例视角不完整，建议人工核对车辆关系。"
    
    if has_insufficient_evidence:
        return "该案例证据不足，建议补充材料后再复核。"
    
    if has_quick_confirm:
        return "该案例证据清晰，可快速确认，但仍建议人工核对。"
    
    # 其他组合
    parts = []
    if has_model_conflict:
        parts.append("存在模型结论冲突")
    if has_incomplete_view:
        parts.append("视角不完整")
    if has_liability_sensitive:
        parts.append("责任敏感")
    if has_insufficient_evidence:
        parts.append("证据不足")
    
    if parts:
        return f"该案例{', '.join(parts)}，建议人工复核。"
    
    return "该案例需人工复核确认。"


def _get_str(value: Any) -> str:
    """安全转换为字符串"""
    if value is None:
        return ""
    return str(value).strip()


def map_route_type_to_cn(route_type: str) -> str:
    """
    将路由类型映射为中文
    
    Args:
        route_type: 路由类型
    
    Returns:
        中文路由类型
    """
    mapping = {
        "manual_review_required": "重点复核",
        "proceed_to_liability": "快速确认",
        "insufficient_evidence": "补证复核"
    }
    return mapping.get(route_type, "重点复核")