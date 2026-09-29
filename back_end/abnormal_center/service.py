"""异动中心 - 数据服务层"""
import datetime
import logging
import threading
import time

from common.http import get_json, get_tx_kline
from common.utils import is_a_share_trading_day, is_market_opened, get_market_hours
from common.cache import cached_singleflight
from abnormal_center.storage import (
    prediction_get, prediction_set, monitor_get, monitor_set, cleanup_old_data,
)

logger = logging.getLogger(__name__)

PREDICTION_API = 'https://stock.quicktiny.cn/api/ladder/exchange-monitor/prediction'
MONITOR_API = 'https://stock.quicktiny.cn/api/ladder/exchange-monitor/list?type=all'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}

# 盘中数据缓存 TTL（秒）：30 分钟
_CACHE_TTL = 30 * 60

# 每日 17:00 固化任务
_AUTO_UPDATE_TIME = (17, 0)


def _latest_trading_date() -> str:
    """返回最近一个A股交易日（YYYY-MM-DD）"""
    d = datetime.date.today()
    while not is_a_share_trading_day(d):
        d -= datetime.timedelta(days=1)
    return d.strftime('%Y-%m-%d')


def _updated_after_close(updated_at) -> bool:
    """判断 updated_at 是否在 A股收盘时间之后（缓存是否为收盘后落盘）。

    收盘后落盘的数据已定格，即使超过 TTL 也直接返回缓存，不再请求数据源。
    """
    hours = get_market_hours('hs_main')
    if not hours:
        return False
    close_min = hours[2] * 60 + hours[3]
    dt = datetime.datetime.fromtimestamp(updated_at)
    return dt.hour * 60 + dt.minute >= close_min


def _fetch_prediction_raw():
    """直接请求 quicktiny 异动预测，返回 (data, count)。失败抛异常。"""
    data = get_json(PREDICTION_API, headers=HEADERS, timeout=15)
    if not data.get('success'):
        raise RuntimeError('API返回失败')
    return data['data'], data.get('count', len(data['data']))


def _fetch_prediction(trade_date):
    """带 single-flight 合并的预测取数：30 分钟内并发请求只打一次源，其余等待同一结果。"""
    return cached_singleflight(f'abnormal-prediction-{trade_date}', _fetch_prediction_raw, ttl=_CACHE_TTL)


def _fetch_monitor_raw():
    """直接请求 quicktiny 异动监控，返回 (data, stats)。失败抛异常。"""
    data = get_json(MONITOR_API, headers=HEADERS, timeout=15)
    if not data.get('success'):
        raise RuntimeError('API返回失败')
    return data['data'], data.get('stats', {})


def _fetch_monitor(trade_date):
    """带 single-flight 合并的监控取数：30 分钟内并发请求只打一次源，其余等待同一结果。"""
    return cached_singleflight(f'abnormal-monitor-{trade_date}', _fetch_monitor_raw, ttl=_CACHE_TTL)


def get_prediction(date=None):
    """获取异动预测列表（接近异常波动阈值的股票，按交易日归档 + 盘中 30 分钟缓存）。

    - date 为空时取最近一个交易日；
    - 非今天的日期：数据已固化，有缓存直接返回；无缓存返回空（不请求历史日期）；
    - 今天的日期：盘中 30 分钟内直接返回缓存，超过 30 分钟重新请求 quicktiny 并落库。
    """
    trade_date = date or _latest_trading_date()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    cached = prediction_get(trade_date)
    if cached:
        data, updated_at = cached
        # 非今天的数据已固化，直接返回（不做 TTL 判断）
        if trade_date != today_str:
            return {'success': True, 'date': trade_date, 'data': data, 'count': len(data)}
        # 今天的数据：30 分钟内直接返回缓存
        if time.time() - updated_at < _CACHE_TTL:
            return {'success': True, 'date': trade_date, 'data': data, 'count': len(data)}
        # 超过 30 分钟：但若缓存是收盘后落盘的，数据已定格，直接返回缓存
        if _updated_after_close(updated_at):
            return {'success': True, 'date': trade_date, 'data': data, 'count': len(data)}
        # 盘中落盘的缓存过期 → 继续往下重新请求

    # 无缓存或今天缓存已过期：仅最近交易日才实时请求，更早的历史日期不请求
    if trade_date != _latest_trading_date():
        return {'success': True, 'date': trade_date, 'data': [], 'count': 0, 'empty': True}

    # 最近交易日即今天，且今天尚未开盘 → 数据源暂无当日数据，不请求直接返回空
    if trade_date == today_str and not is_market_opened('0'):
        return {'success': True, 'date': trade_date, 'data': [], 'count': 0, 'empty': True}

    try:
        data, count = _fetch_prediction(trade_date)
    except Exception as e:
        logger.error(f"获取异动预测失败: {e}")
        return {'success': False, 'error': str(e)}

    if data:
        prediction_set(trade_date, data)
    return {'success': True, 'date': trade_date, 'data': data, 'count': count}


def get_monitor(date=None):
    """获取异动监控列表（已触发异常波动的股票，按交易日归档 + 盘中 30 分钟缓存）。

    缓存逻辑同 get_prediction。
    """
    trade_date = date or _latest_trading_date()
    today_str = datetime.date.today().strftime('%Y-%m-%d')

    cached = monitor_get(trade_date)
    if cached:
        data, stats, updated_at = cached
        if trade_date != today_str:
            return {'success': True, 'date': trade_date, 'data': data, 'stats': stats}
        if time.time() - updated_at < _CACHE_TTL:
            return {'success': True, 'date': trade_date, 'data': data, 'stats': stats}
        if _updated_after_close(updated_at):
            return {'success': True, 'date': trade_date, 'data': data, 'stats': stats}

    if trade_date != _latest_trading_date():
        return {'success': True, 'date': trade_date, 'data': [], 'stats': {}, 'empty': True}

    if trade_date == today_str and not is_market_opened('0'):
        return {'success': True, 'date': trade_date, 'data': [], 'stats': {}, 'empty': True}

    try:
        data, stats = _fetch_monitor(trade_date)
    except Exception as e:
        logger.error(f"获取异动监控失败: {e}")
        return {'success': False, 'error': str(e)}

    if data:
        monitor_set(trade_date, data, stats)
    return {'success': True, 'date': trade_date, 'data': data, 'stats': stats}


def analyze_stock(code, market=''):
    """异动分析器：对单只股票做简易异常分析"""
    if not code:
        return {'success': False, 'error': '缺少股票代码'}

    try:
        # 获取股票K线数据用于分析
        from common.utils import is_etf

        # 确定市场
        if not market:
            code_str = str(code)
            if code_str.startswith(('6', '9')):
                market = '1'
            elif code_str.startswith(('0', '3')):
                market = '0'
            elif code_str.startswith(('4', '8')):
                market = '0'
            else:
                return {'success': False, 'error': '无法判断市场，请提供market参数'}

        # 拉取K线（最近80天，统一走 common.http.get_tx_kline）
        prefix = 'sh' if market in ('1', '2') else 'sz'
        kline = get_tx_kline(f"{prefix}{code}", 80, 'qfq')
        klines = kline['rows']

        if not klines:
            return {'success': False, 'error': '无法获取K线数据'}

        # 解析K线
        closes = []
        highs = []
        lows = []
        dates = []
        for k in klines:
            dates.append(k['date'])
            closes.append(k['close'])
            highs.append(k['high'])
            lows.append(k['low'])

        if len(closes) < 5:
            return {'success': False, 'error': 'K线数据不足'}

        name = kline['name'] or code

        # ---- 分析项 ----
        warnings = []
        latest_close = closes[-1]
        prev_close = closes[-2] if len(closes) > 1 else latest_close
        change_pct = round((latest_close - prev_close) / prev_close * 100, 2)

        # 1) 近期涨跌幅分析
        pct_5d = round((closes[-1] - closes[-min(5, len(closes))]) / closes[-min(5, len(closes))] * 100, 2)
        pct_10d = round((closes[-1] - closes[-min(10, len(closes))]) / closes[-min(10, len(closes))] * 100, 2)
        pct_20d = round((closes[-1] - closes[-min(20, len(closes))]) / closes[-min(20, len(closes))] * 100, 2)

        # 2) 振幅分析
        high_20d = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        low_20d = min(lows[-20:]) if len(lows) >= 20 else min(lows)
        amplitude_20d = round((high_20d - low_20d) / low_20d * 100, 2)
        drawdown_20d = round((high_20d - latest_close) / high_20d * 100, 2)

        # 3) 偏离度分析（10日均价 / 30日均价）
        ma10 = round(sum(closes[-10:]) / min(10, len(closes[-10:])), 2) if len(closes) >= 10 else latest_close
        ma30 = round(sum(closes[-30:]) / min(30, len(closes[-30:])), 2) if len(closes) >= 30 else latest_close
        dev_10d = round((latest_close - ma10) / ma10 * 100, 2)
        dev_30d = round((latest_close - ma30) / ma30 * 100, 2)

        # 4) 连续涨/跌天数
        consecutive_days = 0
        direction = 'up' if change_pct >= 0 else 'down'
        for i in range(len(closes) - 1, 0, -1):
            diff = closes[i] - closes[i - 1]
            if (direction == 'up' and diff >= 0) or (direction == 'down' and diff <= 0):
                consecutive_days += 1
            else:
                break

        # 生成警告
        if abs(pct_5d) > 20:
            warnings.append(f'近5日涨跌{pct_5d}%，波动剧烈')
        if abs(dev_10d) > 10:
            warnings.append(f'偏离10日均线{dev_10d}%，短期偏离大')
        if abs(dev_30d) > 20:
            warnings.append(f'偏离30日均线{dev_30d}%，中长期偏离大')
        if amplitude_20d > 30:
            warnings.append(f'近20日振幅{amplitude_20d}%，振幅过大')
        if consecutive_days >= 5:
            warnings.append(f'连续{consecutive_days}天{"上涨" if direction == "up" else "下跌"}，注意变盘风险')
        if drawdown_20d > 20:
            warnings.append(f'从20日高点回撤{drawdown_20d}%，回撤较大')

        # 涨停板测算（A股主板10%，科创/创业板20%）
        if market in ('1', '2') and not code.startswith('68'):
            limit_pct = 10
        elif code.startswith(('30', '68')):
            limit_pct = 20
        else:
            limit_pct = 10

        limit_up_price = round(latest_close * (1 + limit_pct / 100), 2)
        limit_down_price = round(latest_close * (1 - limit_pct / 100), 2)

        return {
            'success': True,
            'data': {
                'code': code,
                'name': name if isinstance(name, str) else str(name),
                'market': market,
                'latest_close': latest_close,
                'change_pct': change_pct,
                'warnings': warnings,
                'regular_abnormal': {
                    'window': {
                        'pct_5d': pct_5d,
                        'pct_10d': pct_10d,
                        'pct_20d': pct_20d,
                        'amplitude_20d': amplitude_20d,
                        'drawdown_20d': drawdown_20d,
                        'consecutive_days': consecutive_days,
                        'consecutive_dir': direction,
                        'ma10': ma10,
                        'ma30': ma30,
                    }
                },
                'limit_up_projection': {
                    'daily_limit_pct': limit_pct,
                    'limit_up_price': limit_up_price,
                    'limit_down_price': limit_down_price,
                    'current': {
                        'deviation_10d': dev_10d,
                        'deviation_30d': dev_30d,
                        'change_pct': change_pct,
                    }
                }
            }
        }
    except Exception as e:
        logger.error(f"异动分析失败: {e}")
        return {'success': False, 'error': str(e)}


# =========== 定时任务：每日 17:00 清理 + 落库 ===========

_auto_next_update = None   # 下一次 17:00 任务时刻


def _next_update_time(base):
    """返回 base 当天 17:00；若已过则返回次日 17:00"""
    cand = base.replace(hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
                        second=0, microsecond=0)
    if cand <= base:
        cand = (base + datetime.timedelta(days=1)).replace(
            hour=_AUTO_UPDATE_TIME[0], minute=_AUTO_UPDATE_TIME[1],
            second=0, microsecond=0)
    return cand


def _run_daily_update():
    """每日 17:00 任务：清理过期数据，并落库当天异动预测 + 监控数据。

    收盘后客户端请求不会再重新抓取（updated_at 收盘后直接返回缓存），
    所以 17:00 无条件全量抓取一次，把盘中快照覆盖为收盘最终数据。
    """
    cleanup_old_data()

    today = datetime.date.today()
    if not is_a_share_trading_day(today):
        print(f'[abnormal_center] 17:00 任务跳过: {today} 非A股交易日')
        return
    trade_date = today.strftime('%Y-%m-%d')

    # 注意：17:00 固化必须绕过 single-flight 缓存，强制打源，把盘中快照覆盖为收盘最终数据
    try:
        data, count = _fetch_prediction_raw()
        if data:
            prediction_set(trade_date, data)
        print(f'[abnormal_center] 17:00 落库预测: {trade_date}，{count} 条')
    except Exception as e:
        print(f'[abnormal_center] 17:00 落库预测失败: {trade_date} - {e}')

    try:
        data, stats = _fetch_monitor_raw()
        if data:
            monitor_set(trade_date, data, stats)
        print(f'[abnormal_center] 17:00 落库监控: {trade_date}，{len(data)} 条')
    except Exception as e:
        print(f'[abnormal_center] 17:00 落库监控失败: {trade_date} - {e}')


def check_abnormal_center_update():
    """异动中心定时检测：由公共秒级调度器每秒调用一次，每日 17:00 触发固化。

    固化任务要请求两次数据源，放到独立线程执行，避免阻塞调度器。
    """
    global _auto_next_update
    now_dt = datetime.datetime.now()
    if now_dt >= _auto_next_update:
        _auto_next_update = _next_update_time(now_dt)
        threading.Thread(target=_run_daily_update, daemon=True, name='abnormal-center-daily').start()


def init_abnormal_center_update():
    """初始化异动中心定时任务，返回检测函数供公共调度器注册（由 app.py 启动时调用）。"""
    global _auto_next_update
    now_dt = datetime.datetime.now()
    _auto_next_update = _next_update_time(now_dt)
    print(f'[abnormal_center] 定时任务已初始化（17:00 固化下次: {_auto_next_update:%Y-%m-%d %H:%M}）')
    return check_abnormal_center_update
