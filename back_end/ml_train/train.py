"""ML 训练脚本：从 stock_lib.db 读取日K线 → 生成特征+标签 → 训练 XGBoost → 保存模型

用法：
    cd back_end
    python -m ml_train.train

参数可调整以下常量：
    FORWARD_DAYS  未来N天涨幅阈值
    RISE_THRESHOLD 正样本阈值（涨幅超过才标记为1）
    TRAIN_CUTOFF  训练/测试按此日期切分
"""

import os
import sys
import math
import csv
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import classification_report, roc_auc_score, precision_recall_fscore_support
import joblib

# 将 back_end 加入 sys.path，确保可以 import 项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml_train.features import extract_features

# ===== 训练参数 =====
FORWARD_DAYS = 3           # 标签：未来 N 个交易日
RISE_THRESHOLD = 0.05      # 涨幅超过 5% 标记为正样本
TRAIN_CUTOFF = '2025-03-01'  # 此日期前的样本用作训练，之后用作测试
MIN_KLINES = 180           # 最少需要 180 根日K线（120根特征窗口 + 最大前视）
MAX_TRAIN_SAMPLES = 200000 # 训练样本上限（避免内存爆炸）

# ===== 路径 =====
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'stock_lib.db')
MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ml_train')
MODEL_PATH = os.path.join(MODEL_DIR, 'model.pkl')
FEATURE_NAMES_PATH = os.path.join(MODEL_DIR, 'feature_names.txt')


def _kline_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_stock_list():
    """获取沪深A股列表（有日K数据的）"""
    conn = _kline_conn()
    rows = conn.execute(
        '''SELECT DISTINCT s.code, s.name
           FROM market_stock_list s
           INNER JOIN stock_klines k ON s.code = k.code AND s.market = k.market
           WHERE s.market = 'hs_main' AND k.period = 'daily'
           GROUP BY s.code
           HAVING COUNT(*) >= ?''',
        (MIN_KLINES,)
    ).fetchall()
    conn.close()
    return [(r['code'], r['name']) for r in rows]


def get_klines(code):
    """读取一只股票的日K线（按时间升序）"""
    conn = _kline_conn()
    rows = conn.execute(
        'SELECT date, open, high, low, close, volume, amount FROM stock_klines '
        'WHERE code=? AND market=? AND period=? ORDER BY date ASC',
        (code, 'hs_main', 'daily')
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def generate_samples(klines):
    """对一只股票的所有交易日，滑动窗口生成训练样本

    klines: 按时间升序的日K线列表

    返回: [(features_dict, label, date), ...]
      features_dict: 特征字典
      label: 0/1
    """
    if len(klines) < MIN_KLINES:
        return []

    samples = []
    lookback = 120  # 特征计算窗口
    for i in range(lookback, len(klines) - FORWARD_DAYS):
        # 特征窗口: [i-lookback, i)  共 lookback 根K线
        feat_klines = klines[i - lookback:i]
        features = extract_features(feat_klines)
        if features is None:
            continue

        # 标签：未来 FORWARD_DAYS 天的涨跌幅
        future_close = klines[i + FORWARD_DAYS]['close']
        current_close = klines[i - 1]['close']
        ret = (future_close / current_close - 1) if current_close > 0 else 0
        label = 1 if ret > RISE_THRESHOLD else 0

        samples.append((features, label, klines[i - 1]['date']))

    return samples


def train():
    """主训练流程"""
    print(f"=== ML策略训练 ===")
    print(f"  DB: {DB_PATH}")
    print(f"  前视天数: {FORWARD_DAYS}天")
    print(f"  涨幅阈值: {RISE_THRESHOLD*100}%")
    print(f"  训练/测试切分: {TRAIN_CUTOFF}")
    print()

    # --- 1. 获取股票列表 ---
    stocks = get_stock_list()
    print(f"符合条件的股票: {len(stocks)} 只（日K线 >= {MIN_KLINES}根）")

    # --- 2. 生成样本 ---
    all_train_samples = []
    all_test_samples = []

    for idx, (code, name) in enumerate(stocks):
        try:
            klines = get_klines(code)
            samples = generate_samples(klines)

            for feat, label, date in samples:
                if date < TRAIN_CUTOFF:
                    all_train_samples.append((feat, label))
                else:
                    all_test_samples.append((feat, label))

        except Exception as e:
            print(f"  [跳过] {code} {name}: {e}")
            continue

        if (idx + 1) % 500 == 0:
            print(f"  进度: {idx+1}/{len(stocks)}, 训练样本: {len(all_train_samples)}, 测试样本: {len(all_test_samples)}")

        # 内存保护
        if len(all_train_samples) >= MAX_TRAIN_SAMPLES:
            print(f"  训练样本数已达上限 {MAX_TRAIN_SAMPLES}，停止收集")
            break

    print(f"\n  训练样本: {len(all_train_samples)}")
    print(f"  测试样本: {len(all_test_samples)}")

    if len(all_train_samples) < 500:
        print("错误: 训练样本不足 500 条，无法训练")
        return

    # --- 3. 获取特征名列表并转 DataFrame ---
    # 从第一个样本提取特征名（保持顺序）
    feature_names = list(all_train_samples[0][0].keys())
    print(f"  特征维度: {len(feature_names)}")

    X_train = np.array([[s[0][k] for k in feature_names] for s in all_train_samples], dtype=np.float32)
    y_train = np.array([s[1] for s in all_train_samples], dtype=np.int32)

    # 处理测试集
    if all_test_samples:
        X_test = np.array([[s[0][k] for k in feature_names] for s in all_test_samples], dtype=np.float32)
        y_test = np.array([s[1] for s in all_test_samples], dtype=np.int32)
    else:
        X_test = None
        y_test = None

    # --- 4. 正负样本比例 ---
    pos_ratio = y_train.mean()
    neg_count = (1 - y_train).sum()
    pos_count = y_train.sum()
    print(f"  正样本 (>{RISE_THRESHOLD*100}%): {int(pos_count)} ({pos_ratio*100:.1f}%)")
    print(f"  负样本: {int(neg_count)} ({(1-pos_ratio)*100:.1f}%)")

    scale_pos_weight = neg_count / pos_count if pos_count > 0 else 1.0
    print(f"  scale_pos_weight: {scale_pos_weight:.2f}")

    # --- 5. 训练 XGBoost ---
    print("\n开始训练 XGBoost ...")
    model = XGBClassifier(
        n_estimators=200,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        objective='binary:logistic',
        eval_metric='auc',
        random_state=42,
        n_jobs=-1,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_train, y_train)] + ([(X_test, y_test)] if X_test is not None else []),
        verbose=20,
    )

    # --- 6. 评估 ---
    train_pred = model.predict(X_train)
    train_proba = model.predict_proba(X_train)[:, 1]
    train_auc = roc_auc_score(y_train, train_proba)
    train_p, train_r, train_f1, _ = precision_recall_fscore_support(y_train, train_pred, average='binary', zero_division=0)
    print("\n=== 训练集评估 ===")
    print(classification_report(y_train, train_pred, target_names=['不涨', '涨']))
    print(f"  AUC: {train_auc:.4f}")

    test_auc = None
    test_p = test_r = test_f1 = None
    if X_test is not None:
        print("\n=== 测试集评估 ===")
        test_pred = model.predict(X_test)
        test_proba = model.predict_proba(X_test)[:, 1]
        test_auc = roc_auc_score(y_test, test_proba)
        test_p, test_r, test_f1, _ = precision_recall_fscore_support(y_test, test_pred, average='binary', zero_division=0)
        print(classification_report(y_test, test_pred, target_names=['不涨', '涨']))
        print(f"  AUC: {test_auc:.4f}")

    # --- 7. 特征重要性 ---
    print("\n=== 特征重要性 Top 20 ===")
    importances = model.feature_importances_
    feat_imp = sorted(zip(feature_names, importances), key=lambda x: x[1], reverse=True)
    for i, (name, imp) in enumerate(feat_imp[:20]):
        print(f"  {i+1:2d}. {name:25s} {imp:.4f}")

    # --- 8. 保存模型（只保留最优） ---
    os.makedirs(MODEL_DIR, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M')

    # 本次核心指标：优先用测试 AUC，没有测试集则用训练 AUC
    new_score = test_auc if test_auc is not None else train_auc
    metric_name = '测试AUC' if test_auc is not None else '训练AUC'

    # 读取旧最优模型的得分
    old_score = None
    old_ts = None
    if os.path.exists(MODEL_PATH):
        old_bundle = joblib.load(MODEL_PATH)
        old_meta = old_bundle['meta']
        old_score = old_meta.get('best_score', None)
        old_ts = old_meta.get('train_ts', None)

    # 模型数据
    bundle = {
        'model': model,
        'feature_names': feature_names,
        'meta': {
            'forward_days': FORWARD_DAYS,
            'rise_threshold': RISE_THRESHOLD,
            'train_cutoff': TRAIN_CUTOFF,
            'train_samples': len(all_train_samples),
            'test_samples': len(all_test_samples),
            'positive_ratio': float(pos_ratio),
            'best_score': max(new_score, old_score or 0),
            'train_auc': float(train_auc),
            'test_auc': float(test_auc) if test_auc is not None else None,
            'metric_name': metric_name,
            'train_ts': ts,
        }
    }

    # 判断是否替换
    replaced = False
    if old_score is None:
        replaced = True
        print(f"\n首次训练，{metric_name}={new_score:.4f} → 设为当前最优")
    elif new_score > old_score:
        # 旧的最优归档（只保留被淘汰的"前最优"）
        archive_path = os.path.join(MODEL_DIR, f'model_{old_ts}.pkl')
        joblib.dump(old_bundle, archive_path)
        print(f"\n前最优已归档: model_{old_ts}.pkl  ({metric_name}={old_score:.4f})")
        replaced = True
        print(f"新最优: {old_score:.4f} → {new_score:.4f}  (+{new_score-old_score:.4f})")
    else:
        print(f"\n{metric_name}={new_score:.4f} <= 当前最优 {old_score:.4f} → 已丢弃")

    if replaced:
        joblib.dump(bundle, MODEL_PATH)
        print(f"最优模型已更新: {MODEL_PATH}")
    else:
        print(f"最优模型未变: {MODEL_PATH}")

    # 保存特征名
    with open(FEATURE_NAMES_PATH, 'w', encoding='utf-8') as f:
        f.write('\n'.join(feature_names))

    # --- 训练记录 CSV（记录每次训练，标记是否替换） ---
    history_path = os.path.join(MODEL_DIR, 'training_history.csv')
    file_exists = os.path.exists(history_path)
    with open(history_path, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(['时间', '阈值', '训练样本', '测试样本', '正样本占比',
                             '训练AUC', '训练Precision', '训练Recall', '训练F1',
                             '测试AUC', '测试Precision', '测试Recall', '测试F1', '是否最优'])
        writer.writerow([
            ts, f'{RISE_THRESHOLD*100:.0f}%',
            len(all_train_samples), len(all_test_samples), f'{pos_ratio*100:.1f}%',
            f'{train_auc:.4f}', f'{train_p:.4f}', f'{train_r:.4f}', f'{train_f1:.4f}',
            f'{test_auc:.4f}' if test_auc is not None else '-',
            f'{test_p:.4f}' if test_p is not None else '-',
            f'{test_r:.4f}' if test_r is not None else '-',
            f'{test_f1:.4f}' if test_f1 is not None else '-',
            '是' if replaced else '否',
        ])
    print(f"训练记录已追加: {history_path}")


if __name__ == '__main__':
    train()
