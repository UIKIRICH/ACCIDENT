"""
复核辅助服务：整合所有复核辅助功能
内部管理 Excel 数据缓存，提供数据加载和查询接口
"""
import os
import pandas as pd
from typing import Dict, Any, Optional, List
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

# ---------- 全局数据缓存 ----------
_excel_case_data: Dict[str, Dict[str, Any]] = {}
_review_cache: Dict[str, ReviewAssistResult] = {}
_loaded: bool = False

def _standardize_case_fields(case_dict: dict) -> Dict[str, Any]:
    """标准化字段类型"""
    result = {}
    for key, value in case_dict.items():
        key = key.strip()
        if key in ["review_time_seconds", "evidence_completeness_score", 
                   "evidence_conflict_score", "yolo_confidence", 
                   "qwen_confidence", "estimated_involved_vehicle_count"]:
            try:
                value = float(value) if "." in str(value) else int(value)
            except (ValueError, TypeError):
                value = 0
        result[key] = value
    return result

def load_excel_data(file_path: str = "事故案例汇总表.xlsx") -> bool:
    """加载 Excel 数据到内存缓存，以 case_id 为键"""
    global _excel_case_data, _loaded
    try:
        # 处理相对路径
        if not os.path.isabs(file_path):
            if not os.path.exists(file_path):
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                alt_path = os.path.join(base_dir, file_path)
                if os.path.exists(alt_path):
                    file_path = alt_path
                else:
                    cwd_path = os.path.join(os.getcwd(), file_path)
                    if os.path.exists(cwd_path):
                        file_path = cwd_path
        df = pd.read_excel(file_path, engine="openpyxl")
        df.columns = df.columns.str.strip()
        case_dict = {}
        for _, row in df.iterrows():
            case_id = str(row.get("case_id", "")).strip()
            # 跳过表头行（"案例编号"）以及空 ID
            if case_id and case_id != "案例编号":
                case_dict[case_id] = _standardize_case_fields(row.to_dict())
        # 直接重新赋值，避免 clear() 清空后因 update 空字典导致丢失
        _excel_case_data = case_dict
        _loaded = True
        print(f"[INFO] 成功加载 {len(_excel_case_data)} 个案例数据")
        return True
    except FileNotFoundError:
        print(f"[ERROR] 找不到文件: {file_path}")
        return False
    except Exception as e:
        print(f"[ERROR] 加载失败: {e}")
        return False

def ensure_loaded(file_path: str = "事故案例汇总表.xlsx") -> bool:
    """确保数据已加载"""
    global _loaded
    if not _loaded:
        return load_excel_data(file_path)
    return True

def get_case_data(case_id: str) -> Optional[Dict[str, Any]]:
    """根据 case_id 从缓存中获取案例数据"""
    ensure_loaded()
    case_id = case_id.strip()
    
    # 1. 直接精确匹配
    if case_id in _excel_case_data:
        return _excel_case_data[case_id]
    
    # 2. 忽略大小写匹配（并将键转为大写比较）
    case_id_upper = case_id.upper()
    for key, value in _excel_case_data.items():
        # 跳过无效键（如'案例编号'）
        if key.startswith("CASE-") and key.strip().upper() == case_id_upper:
            return value
    
    # 3. 如果还是找不到，打印调试信息
    print(f"[DEBUG] 未找到案例 {case_id}，现有键示例: {list(_excel_case_data.keys())[:10]}")
    return None

def get_all_case_ids() -> List[str]:
    """获取所有案例ID"""
    ensure_loaded()
    return list(_excel_case_data.keys())

def generate_review_assist(case_id: str) -> ReviewAssistResult:
    """生成复核辅助结果"""
    case_data = get_case_data(case_id)
    if not case_data:
        raise ValueError(f"案例 {case_id} 不存在")

    review_focus = identify_review_focus(case_data)
    priority_result = calculate_priority_score(case_data)
    evidence_required_items = generate_evidence_required_items(case_data)
    conflict_summary = generate_conflict_summary(case_data)
    evidence_status = determine_evidence_status(case_data)
    risk_notes = generate_risk_notes(case_data, review_focus, priority_result["level"])
    route_type = case_data.get("system_route", "manual_review_required")
    route_type_cn = map_route_type_to_cn(route_type)
    now = datetime.now()
    result = ReviewAssistResult(
        case_id=case_id,
        route_type=route_type,
        route_type_cn=route_type_cn,
        review_priority_score=priority_result["score"],
        review_priority_level=priority_result["level"],
        review_priority_reason=priority_result["reason"],
        review_focus=review_focus,
        conflict_summary=conflict_summary,
        evidence_status=evidence_status,
        evidence_required_items=evidence_required_items,
        risk_notes=risk_notes,
        created_at=now,
        updated_at=now
    )
    _review_cache[case_id] = result
    return result

def generate_review_assist_from_data(case_id: str, case_data: dict) -> ReviewAssistResult:
    """从传入的 case_data 直接生成复核辅助结果（不依赖全局缓存）"""
    if not case_data:
        raise ValueError(f"案例 {case_id} 数据为空")

    review_focus = identify_review_focus(case_data)
    priority_result = calculate_priority_score(case_data)
    evidence_required_items = generate_evidence_required_items(case_data)
    conflict_summary = generate_conflict_summary(case_data)
    evidence_status = determine_evidence_status(case_data)
    risk_notes = generate_risk_notes(case_data, review_focus, priority_result["level"])
    
    route_type = case_data.get("system_route", "manual_review_required")
    route_type_cn = map_route_type_to_cn(route_type)
    
    now = datetime.now()
    result = ReviewAssistResult(
        case_id=case_id,
        route_type=route_type,
        route_type_cn=route_type_cn,
        review_priority_score=priority_result["score"],
        review_priority_level=priority_result["level"],
        review_priority_reason=priority_result["reason"],
        review_focus=review_focus,
        conflict_summary=conflict_summary,
        evidence_status=evidence_status,
        evidence_required_items=evidence_required_items,
        risk_notes=risk_notes,
        created_at=now,
        updated_at=now
    )
    return result

def get_review_assist(case_id: str) -> Optional[ReviewAssistResult]:
    """查询复核辅助结果"""
    if case_id in _review_cache:
        return _review_cache[case_id]
    try:
        return generate_review_assist(case_id)
    except ValueError:
        return None

def batch_generate(case_ids: List[str]) -> List[ReviewAssistResult]:
    results = []
    for cid in case_ids:
        try:
            results.append(generate_review_assist(cid))
        except Exception as e:
            print(f"[WARN] 生成 {cid} 失败: {e}")
    return results

def get_statistics() -> Dict[str, Any]:
    ensure_loaded()
    if not _review_cache:
        for cid in get_all_case_ids():
            if cid:
                try:
                    generate_review_assist(cid)
                except:
                    pass
    results = list(_review_cache.values())
    total = len(results)
    route_stats = {}
    priority_stats = {}
    focus_stats = {}
    evidence_stats = {}
    report_verify_count = 0
    for r in results:
        route_stats[r.route_type_cn] = route_stats.get(r.route_type_cn, 0) + 1
        priority_stats[r.review_priority_level] = priority_stats.get(r.review_priority_level, 0) + 1
        evidence_stats[r.evidence_status] = evidence_stats.get(r.evidence_status, 0) + 1
        for f in r.review_focus:
            focus_stats[f] = focus_stats.get(f, 0) + 1
        if "报告生成验证" in r.review_focus:
            report_verify_count += 1
    return {
        "total": total,
        "route_type_stats": route_stats,
        "priority_stats": priority_stats,
        "focus_stats": focus_stats,
        "evidence_status_stats": evidence_stats,
        "report_verify_count": report_verify_count
    }