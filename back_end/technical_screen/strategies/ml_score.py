"""ML 量化策略 — 使用 XGBoost 模型对股票打分

通过 ml_train/train.py 训练生成 model.pkl 后使用。
没有模型文件时返回 0（策略不可用）。
"""

import os
import joblib

# 模型文件路径
_MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml_train')
_MODEL_PATH = os.path.join(_MODEL_DIR, 'model.pkl')

_bundle = None
_feature_names = None
_model = None


def _load_model():
    """延迟加载模型（首次调用时加载）"""
    global _bundle, _feature_names, _model
    if _model is not None:
        return
    if os.path.exists(_MODEL_PATH):
        _bundle = joblib.load(_MODEL_PATH)
        _feature_names = _bundle['feature_names']
        _model = _bundle['model']


def calc(daily_klines, weekly_klines=None, monthly_klines=None, index_klines=None, lookback=60):
    """
    ML 打分策略：用训练好的 XGBoost 模型评估当前股票

    返回模型预测的"上涨概率 × 100"作为评分
    """
    _load_model()

    if _model is None:
        # 模型不存在，策略不可用
        return 0, {}

    if len(daily_klines) < 120:
        return 0, {}

    # 对齐指数K线到股票K线日期范围
    aligned_idx = None
    if index_klines:
        stock_dates = {k['date'] for k in daily_klines}
        aligned_idx = [k for k in index_klines if k['date'] in stock_dates]

    # 提取特征
    from ml_train.features import extract_features
    features = extract_features(daily_klines, aligned_idx if aligned_idx else None)
    if features is None:
        return 0, {}

    # 转为模型输入格式
    import numpy as np
    X = np.array([[features[k] for k in _feature_names]], dtype=np.float32)

    # 预测上涨概率
    proba = _model.predict_proba(X)[0][1]
    score = round(proba * 100)

    if score <= 0:
        return 0, {}

    detail = {
        'probability': round(proba, 4),
        'model_samples': _bundle['meta'].get('train_samples', '?'),
    }
    return min(score, 100), detail
