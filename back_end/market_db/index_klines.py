"""上证指数日K线 — 独立存储 + 按需同步

stock_klines 以 (code, market, period, date) 为主键，而 000001 在 hs_main 下是
平安银行，不能当指数使用。指数因此单独存为 market='index'、code='000001'，
既避开个股代码冲突，也不会被市场分段/退市清理逻辑误删。

数据源：同花顺 v4（sh_1A0001），与 K 线弹窗、自助复盘同源。

对外只暴露 get_index_daily_klines()：
- 优先读库；数据缺失、过期或还没覆盖当日K线时，补齐最近 N 年并刷新当年；
- 同步失败直接抛异常，绝不静默回退到 000001 个股数据（否则大盘对比特征
  会被悄悄污染，这类错误在模型指标上很难看出来）。
"""
import datetime
import threading
import time

from common.http import get_ths_klines
from common.utils import is_a_share_trading_day
from market_db.db import (
    klines_get, klines_replace_daily, klines_years, stock_info_get,
)

INDEX_CODE = '000001'
INDEX_MARKET = 'index'
INDEX_NAME = '上证指数'
THS_SYMBOL = 'sh_1A0001'

_HISTORY_YEARS = 5          # 与个股全量同步的 5 年窗口保持一致
_REFRESH_TTL = 30 * 60      # 盘中数据最长复用 30 分钟
_MIN_BARS = 180             # 训练/策略所需的最少日K根数（120 特征窗口 + 前视）

_lock = threading.Lock()


def _latest_rows(limit=5000):
    """读取库内日K（按日期升序）"""
    return klines_get(INDEX_CODE, INDEX_MARKET, 'daily', limit=limit)


def _ts_epoch(ts):
    """'YYYY-MM-DD HH:MM:SS' → epoch 秒；格式异常按“从未同步”处理"""
    try:
        return time.mktime(time.strptime(ts, '%Y-%m-%d %H:%M:%S'))
    except (TypeError, ValueError):
        return 0.0


def _needs_refresh(rows, ts):
    """判断是否需要重新拉取。

    - 无数据 / 无时间戳 → 需要；
    - 交易日 09:30 之后库里还没有当日K线 → 需要（缺当日会让大盘对比特征退化为 0）；
    - 距上次同步超过 TTL → 需要。
    """
    if not rows or not ts:
        return True
    now = datetime.datetime.now()
    today = now.date()
    try:
        trading_day = is_a_share_trading_day(today)
    except Exception:
        # 节假日库未覆盖当年时降级为“仅看周末”，与前端交易日判断的降级策略一致
        trading_day = today.weekday() < 5
    if trading_day and (now.hour, now.minute) >= (9, 30):
        if rows[-1]['date'] < today.strftime('%Y%m%d'):
            return True
    return time.time() - _ts_epoch(ts) > _REFRESH_TTL


def _fetch_year(year):
    """拉取同花顺某年指数日K → stock_klines 行元组"""
    raw = get_ths_klines(THS_SYMBOL, 'day', year)
    rows = []
    for k in raw:
        close = k.get('close') or 0
        if close <= 0:
            continue
        rows.append((
            INDEX_CODE, INDEX_MARKET, 'daily', k['date'],
            k.get('open') or close, k.get('high') or close, k.get('low') or close,
            close, k.get('volume') or 0, k.get('amount') or 0, k.get('turnover') or 0,
        ))
    return rows


def _sync():
    """补齐最近 N 年缺失年份，并刷新当年（覆盖当日盘中K线）"""
    current_year = datetime.datetime.now().year
    wanted = set(range(current_year - _HISTORY_YEARS + 1, current_year + 1))
    existing = klines_years(INDEX_CODE, INDEX_MARKET, 'daily')
    years = sorted(wanted - existing, reverse=True)
    if current_year not in years:
        years.insert(0, current_year)  # 当年始终刷新，拿到最新交易日

    # 首次加载必须补齐全部年份：训练样本覆盖 5 年，缺早期指数会让这些样本的
    # 大盘对比特征变成 0，训练集/测试集分布不一致。
    strict = not existing
    rows = []
    for year in years:
        try:
            rows.extend(_fetch_year(year))
        except Exception as e:
            if strict:
                raise RuntimeError(f'上证指数日K首次同步失败（{year} 年）: {e}') from e
            print(f'[index] {year} 年上证指数日K拉取失败: {e}')

    if not rows:
        if existing:
            return  # 已有历史数据，本次刷新失败不覆盖
        raise RuntimeError('上证指数日K同步失败：同花顺未返回数据')

    # 按日期去重并保持升序（跨年文件理论上不重叠，防御性处理）
    dedup = {r[3]: r for r in rows}
    rows = [dedup[d] for d in sorted(dedup)]

    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    klines_replace_daily(INDEX_CODE, INDEX_MARKET, INDEX_NAME, rows, ts)
    print(f'[index] 上证指数日K同步完成: {len(rows)} 条，最新 {rows[-1][3]}')


def get_index_daily_klines(min_bars=_MIN_BARS):
    """上证指数日K线（按日期升序），供 ML 训练 / 技术选股的大盘对比特征使用。

    数据不足 min_bars 根或同步后仍没覆盖最新交易日时抛 RuntimeError，
    调用方应让本次训练/扫描失败，而不是拿错误/缺失的指数数据继续算特征。
    """
    with _lock:
        rows = _latest_rows()
        info = stock_info_get(INDEX_CODE, INDEX_MARKET)
        ts = info.get('daily_ts') if info else None
        if _needs_refresh(rows, ts):
            _sync()
            rows = _latest_rows()
            info = stock_info_get(INDEX_CODE, INDEX_MARKET)
            ts = info.get('daily_ts') if info else None
            if _needs_refresh(rows, ts):
                raise RuntimeError('上证指数日K同步后仍未覆盖最新交易日，请检查同花顺数据源')

    if len(rows) < min_bars:
        raise RuntimeError(
            f'上证指数日K不足 {min_bars} 根（当前 {len(rows)} 根），无法计算大盘对比特征')
    return rows
