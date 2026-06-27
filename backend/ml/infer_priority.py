import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

class PriorityScorer:
    def __init__(self):
        # 完全规则驱动，不加载模型
        pass

    def predict_score(self, features_dict):
        """
        输入特征字典，返回优先级分数 (0~100)
        分数越高，越需要优先复核
        """
        evidence_score = features_dict.get("evidence_score", 0)
        conflict_score = features_dict.get("conflict_score", 0)
        est_vehicles = features_dict.get("est_vehicles", 1)
        yolo_conf = features_dict.get("yolo_conf", 0.5)
        qwen_conf = features_dict.get("qwen_conf", 0.5)
        missing_evidence = features_dict.get("missing_evidence", 0)
        view_type = features_dict.get("view_type", 0)

        score = 0
        score += (10 - evidence_score) * 4          # 证据越低越优先
        score += conflict_score * 1.5               # 冲突越高越优先
        score += est_vehicles * 2                   # 车辆数越多越复杂
        score += (1 - yolo_conf) * 15               # YOLO 置信度低需复核
        score += (1 - qwen_conf) * 10               # 千问置信度低需复核
        if missing_evidence == 1:
            score += 20
        if view_type == 1:
            score += 10

        # 归一化到 0~100（经验范围 0~140）
        priority_score = min(max(score / 1.4, 0), 100)
        return {
            "priority_score": round(priority_score, 1),
            "estimated_review_seconds": None,
            "raw_score": round(score, 1)
        }

_priority_scorer = None
def get_priority_scorer():
    global _priority_scorer
    if _priority_scorer is None:
        _priority_scorer = PriorityScorer()
    return _priority_scorer

if __name__ == "__main__":
    scorer = get_priority_scorer()
    test_case = {
        "view_type": 1,
        "yolo_conf": 0.72,
        "qwen_conf": 0.90,
        "type_consistency": 0,
        "est_vehicles": 3,
        "evidence_score": 8,
        "conflict_score": 10,
        "missing_evidence": 0,
        "keyframe_quality": 0.8
    }
    result = scorer.predict_score(test_case)
    print("🔮 优先级分数:", result)