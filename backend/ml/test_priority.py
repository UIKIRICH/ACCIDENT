import sys
sys.path.insert(0, '.')
from backend.ml.infer_priority import get_priority_scorer
import pandas as pd

# 读取 Excel 并清理列名（与 build_features.py 保持一致）
df = pd.read_excel('事故案例汇总表.xlsx', engine='openpyxl')
df.columns = df.columns.str.strip()

# 列名映射（与 build_features.py 相同）
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
}
existing_cols = [col for col in column_map.keys() if col in df.columns]
df_clean = df[existing_cols].rename(columns=column_map)

# 转换数值类型
df_clean["yolo_conf"] = pd.to_numeric(df_clean["yolo_conf"], errors='coerce').fillna(0.5)
df_clean["qwen_conf"] = pd.to_numeric(df_clean["qwen_conf"], errors='coerce').fillna(0.5)
df_clean["est_vehicles"] = pd.to_numeric(df_clean["est_vehicles"], errors='coerce').fillna(1).astype(int)
df_clean["evidence_score"] = pd.to_numeric(df_clean["evidence_score"], errors='coerce').fillna(5)
df_clean["conflict_score"] = pd.to_numeric(df_clean["conflict_score"], errors='coerce').fillna(0)
df_clean["view_type"] = df_clean["view_type_raw"].apply(
    lambda x: 1 if isinstance(x, str) and "行车记录仪" in x else 0
)
df_clean["type_consistency"] = df_clean["type_conflict_raw"].apply(
    lambda x: 0 if isinstance(x, str) and "是" in x else 1
)
df_clean["missing_evidence"] = (df_clean["evidence_score"] < 5).astype(int)
df_clean["keyframe_quality"] = 0.7

# 计算优先级分数
scorer = get_priority_scorer()
results = []
for idx, row in df_clean.iterrows():
    features = {
        'view_type': row['view_type'],
        'yolo_conf': row['yolo_conf'],
        'qwen_conf': row['qwen_conf'],
        'type_consistency': row['type_consistency'],
        'est_vehicles': row['est_vehicles'],
        'evidence_score': row['evidence_score'],
        'conflict_score': row['conflict_score'],
        'missing_evidence': row['missing_evidence'],
        'keyframe_quality': row['keyframe_quality']
    }
    result = scorer.predict_score(features)
    results.append((row['case_id'], result['priority_score'], result['raw_score']))

# 按优先级降序排序
results_sorted = sorted(results, key=lambda x: x[1], reverse=True)

print('=== Top 10 最高优先级（最需复核）===')
for i, r in enumerate(results_sorted[:10], 1):
    print(f"{i}. {r[0]}: 优先级分数 {r[1]:.1f} (原始分 {r[2]:.1f})")

print('\n=== Bottom 10 最低优先级（可延后复核）===')
for i, r in enumerate(results_sorted[-10:], 1):
    print(f"{i}. {r[0]}: 优先级分数 {r[1]:.1f} (原始分 {r[2]:.1f})")

print('\n=== 特定案例优先级分数 ===')
for case_id in ['CASE-024', 'CASE-025', 'CASE-042', 'CASE-066']:
    match = [r for r in results if r[0] == case_id]
    if match:
        r = match[0]
        print(f"{case_id}: 优先级分数 {r[1]:.1f} (原始分 {r[2]:.1f})")