"""
统一门控控制器：融合规则门控和 ML 模型预测
"""
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

# 导入 ML 模型
sys.path.insert(0, str(Path(__file__).parent.parent))  # 添加项目根目录
try:
    from backend.ml.infer_gate import EvidenceGate
    _ml_available = True
except ImportError as e:
    print(f"[WARN] ML 模型加载失败: {e}")
    _ml_available = False


class EvidenceGateController:
    """统一门控控制器"""
    
    def __init__(self):
        """初始化控制器，加载 ML 模型"""
        self.ml_gate = None
        if _ml_available:
            try:
                self.ml_gate = EvidenceGate()
                print("[INFO] 门控控制器: ML 模型加载成功")
            except Exception as e:
                print(f"[WARN] 门控控制器: ML 模型加载失败: {e}")
        else:
            print("[WARN] 门控控制器: ML 模块不可用，将仅使用规则门控")
    
    def rule_based_gate(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        规则门控：实现三类门控机制
        
        Args:
            case_data: 包含以下字段的字典
                - view_type: int (1=行车记录仪, 2=路边, 3=监控)
                - visible_vehicle_count: int
                - type_conflict: bool
                - evidence_score: int (0-10)
                - missing_evidence: list
                - keyframe_quality: float (0-1)
        
        Returns:
            规则门控结果字典
        """
        # 初始化触发标志
        compensation_triggered = False
        conflict_triggered = False
        insufficient_triggered = False
        
        # 提取字段
        view_type = case_data.get("view_type", 0)
        visible_vehicle_count = int(case_data.get("visible_vehicle_count", 0))
        type_conflict = bool(case_data.get("type_conflict", False))
        evidence_score = int(case_data.get("evidence_score", 0))
        missing_evidence = case_data.get("missing_evidence", [])
        keyframe_quality = float(case_data.get("keyframe_quality", 0.0))
        
        # 计算估计车辆数
        estimated_vehicles = visible_vehicle_count
        if view_type == 1:  # 行车记录仪视角
            compensation_triggered = True
            estimated_vehicles = visible_vehicle_count + 1
        
        # 冲突型门控
        if type_conflict:
            conflict_triggered = True
        
        # 证据不足型门控
        if (evidence_score < 5 or 
            len(missing_evidence) > 0 or 
            keyframe_quality < 0.3):
            insufficient_triggered = True
        
        # 规则状态判定（按优先级）
        if insufficient_triggered:
            rule_status = "insufficient_evidence"
        elif conflict_triggered:
            rule_status = "needs_manual_review"
        else:
            rule_status = "evidence_ready"
        
        return {
            "rule_status": rule_status,
            "compensation_triggered": compensation_triggered,
            "conflict_triggered": conflict_triggered,
            "insufficient_triggered": insufficient_triggered,
            "estimated_vehicles": estimated_vehicles,
            "details": {
                "view_type": view_type,
                "visible_vehicle_count": visible_vehicle_count,
                "type_conflict": type_conflict,
                "evidence_score": evidence_score,
                "missing_evidence_count": len(missing_evidence),
                "keyframe_quality": keyframe_quality
            }
        }
    
    def get_gate_decision(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取最终门控决策（融合规则和 ML 模型）
        
        Args:
            case_data: 案件数据字典
        
        Returns:
            门控决策结果
        """
        # 1. 规则门控
        rule_result = self.rule_based_gate(case_data)
        rule_status = rule_result["rule_status"]
        
        # 2. ML 模型预测
        ml_prediction = None
        if self.ml_gate is not None:
            try:
                # 构建特征字典
                features = {
                    "view_type": case_data.get("view_type", 0),
                    "yolo_conf": float(case_data.get("yolo_conf", 0.0)),
                    "qwen_conf": float(case_data.get("qwen_conf", 0.0)),
                    "type_consistency": float(case_data.get("type_consistency", 0.0)),
                    "est_vehicles": rule_result["estimated_vehicles"],
                    "evidence_score": int(case_data.get("evidence_score", 0)),
                    "conflict_score": float(case_data.get("conflict_score", 0.0)),
                    "missing_evidence": len(case_data.get("missing_evidence", [])),
                    "keyframe_quality": float(case_data.get("keyframe_quality", 0.0))
                }
                
                ml_result = self.ml_gate.predict(features)
                ml_prediction = {
                    "label": ml_result["label"],
                    "confidence": ml_result["confidence"],
                    "probabilities": ml_result["probabilities"]
                }
            except Exception as e:
                print(f"[WARN] ML 预测失败: {e}")
                ml_prediction = None
        
        # 3. 融合决策
        final_status = rule_status
        
        if ml_prediction:
            ml_label = ml_prediction["label"]
            ml_confidence = ml_prediction["confidence"]
            
            # 保守降级策略：
            # - 如果规则为 evidence_ready，但 ML 预测为 needs_manual_review 或 insufficient_evidence
            # - 且 ML 置信度 >= 0.6，则降级为 needs_manual_review
            if (rule_status == "evidence_ready" and 
                ml_label in ("needs_manual_review", "insufficient_evidence") and
                ml_confidence >= 0.6):
                final_status = "needs_manual_review"
        else:
            ml_label = "unknown"
            ml_confidence = 0.0
        
        # 4. 构建返回结果
        return {
            "final_status": final_status,
            "rule_status": rule_status,
            "ml_prediction": ml_prediction,
            "details": {
                "compensation_triggered": rule_result["compensation_triggered"],
                "conflict_triggered": rule_result["conflict_triggered"],
                "insufficient_triggered": rule_result["insufficient_triggered"],
                "estimated_vehicles": rule_result["estimated_vehicles"],
                "view_type": rule_result["details"]["view_type"],
                "visible_vehicle_count": rule_result["details"]["visible_vehicle_count"],
                "type_conflict": rule_result["details"]["type_conflict"],
                "evidence_score": rule_result["details"]["evidence_score"],
                "missing_evidence_count": rule_result["details"]["missing_evidence_count"],
                "keyframe_quality": rule_result["details"]["keyframe_quality"]
            }
        }


# 单例模式
_gate_controller = None

def get_gate_controller() -> EvidenceGateController:
    """获取门控控制器单例"""
    global _gate_controller
    if _gate_controller is None:
        _gate_controller = EvidenceGateController()
    return _gate_controller


if __name__ == "__main__":
    # 测试
    controller = get_gate_controller()
    
    # 测试案例1：行车记录仪，无冲突，证据充分
    test1 = {
        "view_type": 1,
        "visible_vehicle_count": 2,
        "type_conflict": False,
        "evidence_score": 8,
        "missing_evidence": [],
        "keyframe_quality": 0.8,
        "yolo_conf": 0.75,
        "qwen_conf": 0.85,
        "type_consistency": 1.0,
        "conflict_score": 0.0
    }
    result1 = controller.get_gate_decision(test1)
    print("测试案例1:", result1)
    
    # 测试案例2：监控视角，有冲突
    test2 = {
        "view_type": 3,
        "visible_vehicle_count": 3,
        "type_conflict": True,
        "evidence_score": 6,
        "missing_evidence": ["碰撞部位"],
        "keyframe_quality": 0.6,
        "yolo_conf": 0.65,
        "qwen_conf": 0.70,
        "type_consistency": 0.0,
        "conflict_score": 8.0
    }
    result2 = controller.get_gate_decision(test2)
    print("测试案例2:", result2)
    
    # 测试案例3：证据不足
    test3 = {
        "view_type": 2,
        "visible_vehicle_count": 1,
        "type_conflict": False,
        "evidence_score": 3,
        "missing_evidence": ["碰撞部位", "双方车辆关系"],
        "keyframe_quality": 0.2,
        "yolo_conf": 0.55,
        "qwen_conf": 0.60,
        "type_consistency": 0.5,
        "conflict_score": 2.0
    }
    result3 = controller.get_gate_decision(test3)
    print("测试案例3:", result3)