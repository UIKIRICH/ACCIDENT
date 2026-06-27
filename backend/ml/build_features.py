import pandas as pd
import numpy as np
from sklearn.preprocessing import LabelEncoder
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_and_clean_data(excel_path):
    df = pd.read_excel(excel_path, engine="openpyxl")
    df.columns = df.columns.str.strip()
    column_map = {
        "case_id": "case_id",
        "Case Perspective": "view_type_raw",
        "yolo_confidence": "yolo_conf",
        "qwen_confidence": "qwen_conf",
        "type_conflict_detected": "type_conflict_raw",
        "estimated_involved_vehicle_count": "est_vehicles",
        "evidence_completeness_score": "evidence_score",
        "evidence_conflict_score": "conflict_score",
        "system_route": "system_route",
        "human_review_decision": "human_review",
        "review_time_seconds": "review_time"
    }
    existing_cols = [col for col in column_map.keys() if col in df.columns]
    df_clean = df[existing_cols].rename(columns=column_map)
    df_clean["yolo_conf"] = pd.to_numeric(df_clean["yolo_conf"], errors='coerce').fillna(0.0)
    df_clean["qwen_conf"] = pd.to_numeric(df_clean["qwen_conf"], errors='coerce').fillna(0.0)
    df_clean["est_vehicles"] = pd.to_numeric(df_clean["est_vehicles"], errors='coerce').fillna(1).astype(int)
    df_clean["evidence_score"] = pd.to_numeric(df_clean["evidence_score"], errors='coerce').fillna(0)
    df_clean["conflict_score"] = pd.to_numeric(df_clean["conflict_score"], errors='coerce').fillna(0)
    df_clean["review_time"] = pd.to_numeric(df_clean["review_time"], errors='coerce')
    df_clean["view_type"] = df_clean["view_type_raw"].apply(
        lambda x: 1 if isinstance(x, str) and "行车记录仪" in x else 0
    )
    df_clean["type_consistency"] = df_clean["type_conflict_raw"].apply(
        lambda x: 0 if isinstance(x, str) and "是" in x else 1
    )
    df_clean["missing_evidence"] = (df_clean["evidence_score"] < 6).astype(int)
    df_clean["keyframe_quality"] = 0.7
    return df_clean

def create_labels(df):
    def map_label(route):
        route_str = str(route)
        if "manual_review_required" in route_str:
            return "needs_manual_review"
        elif "insufficient_evidence" in route_str or "证据不足" in route_str:
            return "insufficient_evidence"
        else:
            return "evidence_ready"
    df["label_raw"] = df["system_route"].apply(map_label)
    def refine_label(row):
        if pd.isna(row["human_review"]) or row["human_review"] == "":
            return row["label_raw"]
        if any(kw in str(row["human_review"]) for kw in ["无法", "待定", "不明确"]):
            return "insufficient_evidence"
        return row["label_raw"]
    df["label"] = df.apply(refine_label, axis=1)
    return df

def main():
    excel_path = "事故案例汇总表.xlsx"
    if not os.path.exists(excel_path):
        print(f"错误：找不到 {excel_path}")
        return
    df = load_and_clean_data(excel_path)
    df = create_labels(df)
    feature_cols = [
        "view_type", "yolo_conf", "qwen_conf", "type_consistency",
        "est_vehicles", "evidence_score", "conflict_score",
        "missing_evidence", "keyframe_quality"
    ]
    X = df[feature_cols].copy()
    y_label = df["label"].copy()
    y_target = df["review_time"].copy()
    # 用中位数填充缺失的目标值
    median_val = y_target.median()
    y_target.fillna(median_val, inplace=True)

    le = LabelEncoder()
    y_encoded = le.fit_transform(y_label)

    X.to_csv("backend/ml/features.csv", index=False)
    pd.Series(y_encoded).to_csv("backend/ml/labels_encoded.csv", index=False, header=False)
    pd.Series(le.classes_).to_csv("backend/ml/label_classes.csv", index=False, header=False)
    # 保存目标值（回归标签）
    pd.Series(y_target).to_csv("backend/ml/target_review_time.csv", index=False, header=False)

    print(f"✅ 特征提取完成！共 {len(X)} 条样本")
    print(f"标签分布: {dict(zip(*np.unique(y_label, return_counts=True)))}")
    print(f"目标 review_time 统计: 均值 {y_target.mean():.2f}，中位数 {y_target.median():.2f}")
    print(f"标签编码: {dict(enumerate(le.classes_))}")

if __name__ == "__main__":
    import numpy as np
    main()