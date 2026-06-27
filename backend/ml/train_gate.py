import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
from sklearn.utils.class_weight import compute_class_weight
from imblearn.over_sampling import SMOTE
import xgboost as xgb
import joblib
import matplotlib.pyplot as plt
import seaborn as sns

def load_data():
    X = pd.read_csv("backend/ml/features.csv")
    y = pd.read_csv("backend/ml/labels_encoded.csv", header=None).squeeze()
    classes = pd.read_csv("backend/ml/label_classes.csv", header=None).squeeze().tolist()
    return X, y, classes

def main():
    X, y, classes = load_data()
    print(f"📊 数据集: {len(X)} 条, {X.shape[1]} 个特征")
    print(f"📊 标签: {classes}")
    
    # 划分训练集和测试集
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # 标准化
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # -------- SMOTE 过采样（解决数据不均衡） --------
   # -------- 自适应过采样（解决数据不均衡） --------
    from collections import Counter
    from imblearn.over_sampling import SMOTE, RandomOverSampler
    
    print("🔄 应用自适应过采样...")
    # 统计训练集各类别样本数
    counter = Counter(y_train)
    min_samples = min(counter.values())
    print(f"   原始训练集标签分布: {dict(counter)}")
    
    if min_samples >= 5:
        # 使用SMOTE，k_neighbors设为min(5, min_samples-1)
        k_neighbors = min(5, min_samples - 1)
        print(f"   使用 SMOTE (k_neighbors={k_neighbors})")
        oversampler = SMOTE(random_state=42, k_neighbors=k_neighbors)
    else:
        # 使用随机过采样
        print(f"   使用 RandomOverSampler (因最小类别样本数 {min_samples} < 5)")
        oversampler = RandomOverSampler(random_state=42)
    
    X_train_res, y_train_res = oversampler.fit_resample(X_train_scaled, y_train)
    print(f"   过采样后训练集大小: {len(X_train_res)} 条")
    print(f"   过采样后标签分布: {dict(zip(*np.unique(y_train_res, return_counts=True)))}")
    # -------- 计算类别权重 --------
    # 方法：用过采样前的 y_train 计算权重，让少数类获得更高权重
    class_weights = compute_class_weight('balanced', classes=np.unique(y_train), y=y_train)
    weight_dict = dict(zip(np.unique(y_train), class_weights))
    print(f"   类别权重: {weight_dict}")
    
    # 将权重转换为样本权重数组（对应过采样后的数据）
    sample_weights = np.array([weight_dict[label] for label in y_train_res])
    
    # -------- 训练 XGBoost --------
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        objective='multi:softprob',
        num_class=len(classes),
        random_state=42,
        eval_metric='mlogloss'
    )
    model.fit(
        X_train_res, y_train_res,
        sample_weight=sample_weights,
        eval_set=[(X_test_scaled, y_test)],
        verbose=False
    )
    
    # -------- 评估 --------
    y_pred = model.predict(X_test_scaled)
    print(f"\n准确率: {accuracy_score(y_test, y_pred):.4f}")
    print("\n分类报告:")
    print(classification_report(y_test, y_pred, target_names=classes, labels=range(len(classes))))
    
    cm = confusion_matrix(y_test, y_pred, labels=range(len(classes)))
    plt.figure(figsize=(8,6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues', xticklabels=classes, yticklabels=classes)
    plt.title('Confusion Matrix (with SMOTE + Class Weights)')
    plt.savefig('backend/ml/confusion_matrix.png', dpi=150, bbox_inches='tight')
    print("✅ 混淆矩阵已保存")
    
    # -------- 保存模型 --------
    joblib.dump(model, "backend/ml/evidence_gate_model.pkl")
    joblib.dump(scaler, "backend/ml/scaler.pkl")
    joblib.dump(classes, "backend/ml/label_classes.pkl")
    print("✅ 模型已保存（含 SMOTE + 类别权重）")

if __name__ == "__main__":
    import numpy as np
    main()