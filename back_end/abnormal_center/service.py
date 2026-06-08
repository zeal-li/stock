"""异动中心 - 数据服务层"""
import requests
import logging
from common import REQUEST_PROXIES

logger = logging.getLogger(__name__)

PREDICTION_API = 'https://stock.quicktiny.cn/api/ladder/exchange-monitor/prediction'
MONITOR_API = 'https://stock.quicktiny.cn/api/ladder/exchange-monitor/list?type=all'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
}


def get_prediction():
    """获取异动预测列表（接近异常波动阈值的股票）"""
    try:
        r = requests.get(PREDICTION_API, headers=HEADERS, timeout=15, proxies=REQUEST_PROXIES)
        data = r.json()
        if data.get('success'):
            return {'success': True, 'data': data['data'], 'count': data.get('count', len(data['data']))}
        return {'success': False, 'error': 'API返回失败'}
    except Exception as e:
        logger.error(f"获取异动预测失败: {e}")
        return {'success': False, 'error': str(e)}


def get_monitor():
    """获取异动监控列表（已触发异常波动的股票）"""
    try:
        r = requests.get(MONITOR_API, headers=HEADERS, timeout=15, proxies=REQUEST_PROXIES)
        data = r.json()
        if data.get('success'):
            return {
                'success': True,
                'data': data['data'],
                'stats': data.get('stats', {}),
            }
        return {'success': False, 'error': 'API返回失败'}
    except Exception as e:
        logger.error(f"获取异动监控失败: {e}")
        return {'success': False, 'error': str(e)}


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

        # 拉取K线（最近80天）
        kline_url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        prefix = 'sh' if market in ('1', '2') else 'sz'
        params = {'param': f"{prefix}{code},day,,,80,qfq"}
        r = requests.get(kline_url, params=params,
                         headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com/'},
                         timeout=10, proxies=REQUEST_PROXIES)
        jd = r.json()
        jd_data = (jd.get('data') or {}).get(f"{prefix}{code}", {})
        klines = jd_data.get('qfqday') or jd_data.get('day') or []

        if not klines:
            return {'success': False, 'error': '无法获取K线数据'}

        # 解析K线
        closes = []
        highs = []
        lows = []
        dates = []
        for k in klines:
            if len(k) >= 6:
                dates.append(k[0])
                closes.append(float(k[2]))
                highs.append(float(k[3]))
                lows.append(float(k[4]))

        if len(closes) < 5:
            return {'success': False, 'error': 'K线数据不足'}

        name = jd_data.get('qt', {}).get(f"{prefix}{code}", [None, ''])[1] if isinstance(jd_data.get('qt', {}).get(f"{prefix}{code}"), list) else code

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
