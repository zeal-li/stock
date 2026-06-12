"""prediction.py 回测脚本 — 测试 002585 从 2025-04 至今的预测正确率

逻辑：
  1. 取 002585 所有日 K 线数据
  2. 对 2025-04-01 之后的每个交易日，用该日可见的 K 线计算 prediction
  3. 对比 prediction.direction 与次日实际涨跌
  4. 统计：总体正确率、看涨正确率、看跌正确率、按置信度分段正确率
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'back_end'))

import sqlite3
from technical_screen.strategies.prediction import calc as prediction_calc

DB_PATH = os.path.join(os.path.dirname(__file__), 'back_end', 'data', 'stock_detail_list.db')

CODE = '002585'
MARKET = 'hs_main'


def load_klines():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT date, open, high, low, close, volume FROM klines '
        'WHERE code=? AND market=? AND period=? ORDER BY date ASC',
        (CODE, MARKET, 'daily')
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def main():
    klines = load_klines()
    print(f"002585 日K线总数: {len(klines)}")
    if not klines:
        print("无K线数据，请先同步数据。")
        return

    start_idx = None
    for i, k in enumerate(klines):
        if k['date'] >= '20250401':
            start_idx = i
            break

    if start_idx is None or start_idx < 20:
        print(f"2025-04-01 之前的数据不足 (需要至少 20 天，最早满足日期在索引 {start_idx})")
        return

    total = 0
    correct = 0
    bullish_correct = 0
    bullish_total = 0
    bearish_correct = 0
    bearish_total = 0

    score_buckets = {
        '50-100': {'total': 0, 'correct': 0},
        '30-50':  {'total': 0, 'correct': 0},
        '0-30':   {'total': 0, 'correct': 0},
    }

    results = []

    for i in range(start_idx, len(klines) - 1):
        visible = klines[:i + 1]
        pred = prediction_calc(visible)
        direction = pred['direction']
        score = pred['score']

        today_close = klines[i]['close']
        next_close = klines[i + 1]['close']
        actual_up = next_close > today_close
        actual_down = next_close < today_close

        if today_close == next_close:
            continue

        total += 1
        predicted_up = (direction == 'bullish')
        hit = (predicted_up and actual_up) or (not predicted_up and actual_down)

        if hit:
            correct += 1

        if predicted_up:
            bullish_total += 1
            if hit:
                bullish_correct += 1
        else:
            bearish_total += 1
            if hit:
                bearish_correct += 1

        if score >= 50:
            bucket = '50-100'
        elif score >= 30:
            bucket = '30-50'
        else:
            bucket = '0-30'
        score_buckets[bucket]['total'] += 1
        if hit:
            score_buckets[bucket]['correct'] += 1

        results.append({
            'date': klines[i]['date'],
            'next_date': klines[i + 1]['date'],
            'direction': direction,
            'score': score,
            'actual_up': actual_up,
            'hit': hit,
            'chg_pct': round((next_close - today_close) / today_close * 100, 2),
        })

    # ---- print report ----
    print(f"\n{'='*60}")
    print(f"  002585 prediction.py Backtest Report")
    print(f"  Range: {klines[start_idx]['date'][:4]}-{klines[start_idx]['date'][4:6]}-{klines[start_idx]['date'][6:8]}"
          f" ~ {klines[-1]['date'][:4]}-{klines[-1]['date'][4:6]}-{klines[-1]['date'][6:8]}")
    print(f"{'='*60}")
    print(f"\n  [Overall]")
    print(f"  {'-' * 40}")
    print(f"  Total predictions:  {total}")
    print(f"  Correct:            {correct}")
    print(f"  Accuracy:           {correct/total*100:.1f}%")
    print(f"")
    print(f"  [Bullish Predictions]")
    print(f"  {'-' * 40}")
    print(f"  Bullish predictions: {bullish_total}")
    print(f"  Bullish correct:     {bullish_correct}")
    bull_acc = f"{bullish_correct/bullish_total*100:.1f}%" if bullish_total else "N/A"
    print(f"  Bullish accuracy:    {bull_acc}")
    print(f"")
    print(f"  [Bearish Predictions]")
    print(f"  {'-' * 40}")
    print(f"  Bearish predictions: {bearish_total}")
    print(f"  Bearish correct:     {bearish_correct}")
    bear_acc = f"{bearish_correct/bearish_total*100:.1f}%" if bearish_total else "N/A"
    print(f"  Bearish accuracy:    {bear_acc}")
    print(f"")
    print(f"  [Accuracy by Confidence Level]")
    print(f"  {'-' * 40}")
    for name in ['50-100', '30-50', '0-30']:
        b = score_buckets[name]
        if b['total'] > 0:
            print(f"  Score {name:>6}:  {b['correct']:>3}/{b['total']:<3}  ({b['correct']/b['total']*100:.1f}%)")
        else:
            print(f"  Score {name:>6}:  (no data)")

    print(f"\n  [Monthly Accuracy]")
    print(f"  {'-' * 40}")
    monthly = {}
    for r in results:
        month = r['date'][:6]
        if month not in monthly:
            monthly[month] = {'total': 0, 'correct': 0}
        monthly[month]['total'] += 1
        if r['hit']:
            monthly[month]['correct'] += 1
    for m in sorted(monthly):
        d = monthly[m]
        bar_len = int(d['correct'] / d['total'] * 20)
        bar = '#' * bar_len + '-' * (20 - bar_len)
        print(f"  {m[:4]}-{m[4:]}: {bar} {d['correct']:>3}/{d['total']:<3} ({d['correct']/d['total']*100:.1f}%)")

    print(f"\n{'='*60}\n")


if __name__ == '__main__':
    main()
