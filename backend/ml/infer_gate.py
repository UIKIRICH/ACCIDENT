import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import joblib
import pandas as pd
import numpy as np

class EvidenceGate:
    def __init__(self):
        self.model = joblib.load("backend/ml/evidence_gate_model.pkl")
        self.scaler = joblib.load("backend/ml/scaler.pkl")
        self.classes = joblib.load("backend/ml/label_classes.pkl")
        self.feature_order = [
            "view_type", "yolo_conf", "qwen_conf", "type_consistency",
            "est_vehicles", "evidence_score", "conflict_score",
            "missing_evidence", "keyframe_quality"
        ]
    
    def predict(self, features_dict):
        """输入特征字典，返回预测标签、概率和置信度"""
        df = pd.DataFrame([features_dict])[self.feature_order]
        X_scaled = self.scaler.transform(df)
        proba = self.model.predict_proba(X_scaled)[0]
        pred_idx = np.argmax(proba)
        return {
            "label": self.classes[pred_idx],
            "probabilities": {cls: proba[i] for i, cls in enumerate(self.classes)},
            "confidence": float(proba[pred_idx])
        }

if __name__ == "__main__":
    gate = EvidenceGate()
    # 用一个真实案例测试（CASE-001 的特征）
    test_case = {
        "view_type": 1,               # 行车记录仪
        "yolo_conf": 0.6247,
        "qwen_conf": 0.95,
        "type_consistency": 0,        # 冲突
        "est_vehicles": 4,
        "evidence_score": 6,
        "conflict_score": 10,
        "missing_evidence": 0,
        "keyframe_quality": 0.7
    }
    result = gate.predict(test_case)
    print("🔮 预测结果:", result)