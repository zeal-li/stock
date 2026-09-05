"""自助复盘 - 主要指数复盘分析

功能：
1. 主要指数（上证/深证成指/创业板指/沪深300/科创50/中证500）行情一览
2. 指数同频共振或分化研判
3. 关键点位、重要压力位/支撑位（20日高低点、60日区间、MA20/MA60）
4. 全市场上涨家数比例（市场宽度）
5. 两市总成交额变化（市场温度）
6. 上证日内形态（下探回升/支撑验证）

数据源约定（单一数据源，不做多源串行兜底）：
- 指数实时行情 + 涨跌家数：东方财富 ulist
- 指数日K（压力/支撑计算）：东方财富 kline
- 两市总成交额（今日/昨日）：money_flow 轮询缓存的同花顺成交额分时
- 上证分时走势：money_flow 轮询缓存
任一环节取不到数据即整体报错返回，不拼接替代数据。
"""
import datetime
import json
import time
import requests
from concurrent.futures import ThreadPoolExecutor

from common import REQUEST_PROXIES
from common.utils import is_a_trading_time
from money_flow.storage import db_get, _EM_HEADERS, _EM_UT, _SH_MINUTE_KEY, _TURNOVER_MINUTE_KEY

# 主要指数 → 腾讯证券代码（日K数据源）
_TX_SYMBOLS = {
    '1.000001': 'sh000001',
    '0.399001': 'sz399001',
    '0.399006': 'sz399006',
    '1.000300': 'sh000300',
    '1.000688': 'sh000688',
    '0.399905': 'sh000905',
}

# 复盘覆盖的主要指数（secid: 1=沪 0=深）
MAJOR_INDICES = [
    {'code': '000001', 'secid': '1.000001', 'name': '上证指数'},
    {'code': '399001', 'secid': '0.399001', 'name': '深证成指'},
    {'code': '399006', 'secid': '0.399006', 'name': '创业板指'},
    {'code': '000300', 'secid': '1.000300', 'name': '沪深300'},
    {'code': '000688', 'secid': '1.000688', 'name': '科创50'},
    {'code': '399905', 'secid': '0.399905', 'name': '中证500'},
]

# 市场宽度与两市合计口径（沿用 money_flow：上证综指 + 深证成指市场级统计）
_BREADTH_SECIDS = ('1.000001', '0.399001')


def _num(v):
    """东财 fltt=2 数值字段转 float，' - ' / None / 空串 返回 None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(',', '')
    if not s or s == '-':
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _fmt_pct(v):
    if v is None:
        return '--'
    return ('+' if v >= 0 else '') + f'{v:.2f}%'


# ==================== 数据抓取 ====================

def _fetch_quotes():
    """东财 ulist：主要指数实时行情 + 涨跌家数（f104/f105/f106）"""
    secids = ','.join(s['secid'] for s in MAJOR_INDICES)
    url = 'https://push2delay.eastmoney.com/api/qt/ulist.np/get'
    params = {
        'fltt': 2, 'invt': 2, 'ut': _EM_UT,
        'fields': 'f2,f3,f4,f12,f13,f14,f15,f16,f17,f18,f104,f105,f106',
        'secids': secids,
    }
    r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    body = json.loads(r.content.decode('utf-8', 'replace'))
    diff = ((body.get('data') or {}).get('diff')) or []
    if not diff:
        raise RuntimeError('指数行情获取失败（东财 ulist 返回为空）')

    quote_map = {}
    for row in diff:
        mkt = _num(row.get('f13'))
        code = str(row.get('f12') or '').strip()
        if mkt is None or not code:
            continue
        secid = f"{int(mkt)}.{code}"
        quote_map[secid] = {
            'name': str(row.get('f14') or ''),
            'price': _num(row.get('f2')),
            'change_pct': _num(row.get('f3')),
            'change_val': _num(row.get('f4')),
            'open': _num(row.get('f17')),
            'high': _num(row.get('f15')),
            'low': _num(row.get('f16')),
            'pre_close': _num(row.get('f18')),
            'rise': _num(row.get('f104')),
            'fall': _num(row.get('f105')),
            'flat': _num(row.get('f106')),
        }

    missing = [s['name'] for s in MAJOR_INDICES if s['secid'] not in quote_map]
    if missing:
        raise RuntimeError(f'指数行情缺失: {", ".join(missing)}')
    return quote_map


def _fetch_kline(secid):
    """腾讯日K：近120个交易日（收盘/最高/最低）"""
    symbol = _TX_SYMBOLS.get(secid)
    if not symbol:
        raise RuntimeError(f'不支持的指数 secid: {secid}')
    url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get'
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com/'}
    r = requests.get(url, params={'param': f'{symbol},day,,,120,qfq'},
                     headers=headers, timeout=10, proxies=REQUEST_PROXIES)
    body = r.json()
    jd_data = (body.get('data') or {}).get(symbol, {})
    klines = jd_data.get('qfqday') or jd_data.get('day') or []
    if not klines:
        raise RuntimeError(f'日K获取失败: {secid}')

    closes, highs, lows = [], [], []
    for line in klines:
        if not isinstance(line, (list, tuple)) or len(line) < 5:
            continue
        close = _num(line[2])
        high = _num(line[3])
        low = _num(line[4])
        if close is None or high is None or low is None or close <= 0:
            continue
        closes.append(close)
        highs.append(high)
        lows.append(low)
    if len(closes) < 20:
        raise RuntimeError(f'日K数据不足: {secid}（仅 {len(closes)} 根）')
    return {'closes': closes, 'highs': highs, 'lows': lows}


def _fetch_all_klines():
    """并行抓取全部指数日K"""
    kline_map = {}
    with ThreadPoolExecutor(max_workers=len(MAJOR_INDICES)) as pool:
        futs = {pool.submit(_fetch_kline, s['secid']): s for s in MAJOR_INDICES}
        for fut in futs:
            kline_map[futs[fut]['secid']] = fut.result()
    return kline_map


def _fetch_turnover():
    """两市成交额（今日/昨日/变动），来源 money_flow 缓存（同花顺成交额分时，单位：元）"""
    row = db_get(_TURNOVER_MINUTE_KEY)
    if not row:
        return None
    val, meta = row
    header = ((val.get('data') or {}).get('header')) or {}
    today = _num(header.get('turnover'))
    yesterday = _num(header.get('turnover_pre'))
    if today is None or yesterday is None or yesterday <= 0:
        return None
    today_yi = today / 1e8
    yesterday_yi = yesterday / 1e8
    change_yi = today_yi - yesterday_yi
    change_pct = change_yi / yesterday_yi * 100 if yesterday_yi else None
    day = _meta_day(meta)
    return {
        'day': day,
        'today': round(today_yi, 2),
        'yesterday': round(yesterday_yi, 2),
        'change': round(change_yi, 2),
        'change_pct': round(change_pct, 2) if change_pct is not None else None,
    }


def _fetch_sh_minute():
    """上证指数分时，来源 money_flow 轮询缓存（东财 trends2）"""
    row = db_get(_SH_MINUTE_KEY)
    if not row:
        return None
    val, meta = row
    data = ((val.get('data') or {}))
    times = data.get('times') or []
    prices = data.get('prices') or []
    pre_close = _num(data.get('preClose'))
    if not times or not prices or pre_close is None:
        return None
    return {
        'day': _meta_day(meta),
        'times': times,
        'prices': [p for p in prices if p is not None],
        'pre_close': pre_close,
    }


def _meta_day(meta):
    """缓存 meta（时间戳）转 'YYYY-MM-DD' 字符串"""
    try:
        ts = float(meta)
        return datetime.datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
    except (TypeError, ValueError):
        return None


def _is_recent(meta, days=4):
    """缓存是否在最近 days 天内（周末/盘后仍可复盘最近交易日）"""
    try:
        ts = float(meta)
        return time.time() - ts < days * 86400
    except (TypeError, ValueError):
        return False


# ==================== 指标计算 ====================

def _sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def _build_index_item(spec, q, k):
    """组合单只指数的行情 + 技术位数据"""
    closes = k['closes']
    highs = k['highs']
    lows = k['lows']
    close = q['price'] if q['price'] is not None else closes[-1]

    n20 = min(20, len(highs))
    n60 = min(60, len(highs))
    high_20 = max(highs[-n20:])
    low_20 = min(lows[-n20:])
    high_60 = max(highs[-n60:])
    low_60 = min(lows[-n60:])
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    span = high_60 - low_60
    pos_pct = round((close - low_60) / span * 100, 1) if span > 0 else 50.0

    return {
        'code': spec['code'],
        'secid': spec['secid'],
        'name': q.get('name') or spec['name'],
        'price': round(close, 2),
        'change_pct': round(q['change_pct'], 2) if q['change_pct'] is not None else None,
        'change_val': round(q['change_val'], 2) if q['change_val'] is not None else None,
        'open': round(q['open'], 2) if q['open'] is not None else None,
        'high': round(q['high'], 2) if q['high'] is not None else None,
        'low': round(q['low'], 2) if q['low'] is not None else None,
        'pre_close': round(q['pre_close'], 2) if q['pre_close'] is not None else None,
        'ma20': round(ma20, 2) if ma20 is not None else None,
        'ma60': round(ma60, 2) if ma60 is not None else None,
        'high_20': round(high_20, 2),
        'low_20': round(low_20, 2),
        'high_60': round(high_60, 2),
        'low_60': round(low_60, 2),
        'pos_pct': pos_pct,
    }


# ==================== 分析研判 ====================

def _analyze_synergy(indices):
    """指数同频共振 / 分化研判"""
    pct_of = {it['name']: it['change_pct'] or 0.0 for it in indices}
    up = [n for n, v in pct_of.items() if v >= 0.05]
    down = [n for n, v in pct_of.items() if v <= -0.05]
    flat = [n for n, v in pct_of.items() if -0.05 < v < 0.05]

    def _pct(n):
        return _fmt_pct(pct_of[n])

    if not up and not down:
        mode = '横盘整理'
        summary = '主要指数涨跌幅均落在±0.05%以内，多空基本平衡、方向不明，市场观望情绪较浓，等待方向选择。'
    elif up and not down:
        mode = '同频共振（普涨）'
        top = max(up, key=lambda n: pct_of[n])
        summary = (f'主要指数同步上涨，{top}领涨（{_pct(top)}），权重与题材形成上涨共振，'
                   f'做多情绪一致，增量资金或正在进场。')
        if len(flat) > 0:
            summary += f'其中{"、".join(flat)}基本走平，涨幅略逊。'
    elif down and not up:
        mode = '同频共振（普跌）'
        worst = min(down, key=lambda n: pct_of[n])
        summary = (f'主要指数全线收跌，{worst}跌幅居前（{_pct(worst)}），'
                   f'系统性回调特征明显，场内避险情绪占上风，注意控制回撤风险。')
        if len(flat) > 0:
            summary += f'{"、".join(flat)}相对抗跌，跌幅有限。'
    else:
        mode = '分化'
        up_names = '、'.join(f'{n}（{_pct(n)}）' for n in up)
        down_names = '、'.join(f'{n}（{_pct(n)}）' for n in down)
        summary = f'指数间明显分化：上涨的有 {up_names}；下跌的有 {down_names}。'

        sh = pct_of.get('上证指数')
        cyb = pct_of.get('创业板指')
        hs300 = pct_of.get('沪深300')
        kc50 = pct_of.get('科创50')
        # 权重(沪深300) vs 成长(创业板/科创50)
        growth_avg = [v for v in (cyb, kc50) if v is not None]
        growth = sum(growth_avg) / len(growth_avg) if growth_avg else None
        if growth is not None and hs300 is not None:
            gap = growth - hs300
            if gap >= 0.4:
                summary += '创业板/科创50明显强于沪深300，资金偏向成长与中小盘，题材与个股活跃度提升。'
            elif gap <= -0.4:
                summary += ('权重蓝筹明显强于创业板/科创50，这种"涨权重、杀成长"的背离并非普涨/普跌，'
                            '更多是资金调仓换股、高低切换，注意风格切换带来的结构性风险。')
        if sh is not None and cyb is not None and (sh - cyb) * (abs(cyb) > 0.5 or abs(sh) > 0.5) != 0 and sh >= 0.05 and cyb <= -0.5:
            summary += '上证与创业板方向背离，指数加权参考意义下降，当前更适合重个股、轻指数。'
        elif sh is not None and cyb is not None and sh <= -0.5 and cyb >= 0.05:
            summary += '上证偏弱而创业板走强，资金弃权重、抱成长，局部做多力量仍在。'
    return {'mode': mode, 'up': up, 'down': down, 'flat': flat, 'summary': summary}


def _level_conclusion(it):
    """单只指数的关键点位/压力支撑小结"""
    close = it['price']
    h20, l20 = it['high_20'], it['low_20']
    h60, l60 = it['high_60'], it['low_60']
    ma20, ma60 = it['ma20'], it['ma60']
    parts = []
    parts.append(f'近60日区间 {l60:.0f} ~ {h60:.0f}，现价位于区间 {it["pos_pct"]:.0f}% 分位。')

    near_ratio = 0.003  # 视为"贴近"的距离比例
    if close >= h20:
        if h60 > close:
            parts.append(f'已刷新近20日高点 {h20:.0f}，上方直接压力看60日高点 {h60:.0f}（+{(h60 - close) / close * 100:.1f}%）。')
        else:
            parts.append(f'已刷新近20日乃至60日高点，上方无明显近端套牢压力，趋势偏强。')
    elif close >= h20 * (1 - near_ratio):
        parts.append(f'现价紧贴20日高点压力 {h20:.0f}（距 {+((h20 - close) / close * 100):.1f}%），放量突破则打开上行空间，受阻则回踩。')
    else:
        parts.append(f'上方压力：近20日高点 {h20:.0f}（距现价 +{(h20 - close) / close * 100:.1f}%）。')

    if close <= l20:
        if l60 < close:
            parts.append(f'已跌破近20日低点 {l20:.0f}，下方关键支撑下移至60日低点 {l60:.0f}（距现价 -{(close - l60) / close * 100:.1f}%）。')
        else:
            parts.append(f'现价已创近60日新低，下行趋势中未见明确支撑，等待企稳信号。')
    elif close <= l20 * (1 + near_ratio):
        parts.append(f'现价正逼近20日低点支撑 {l20:.0f}（距 -{(close - l20) / close * 100:.1f}%），该支撑正被考验，守住则短线止跌。')
    else:
        parts.append(f'下方支撑：近20日低点 {l20:.0f}（距现价 -{(close - l20) / close * 100:.1f}%）。')

    ma_texts = []
    if ma20 is not None:
        ma_texts.append(f'20日线 {ma20:.0f}（现价{"站上" if close >= ma20 else "跌破"}）')
    if ma60 is not None:
        ma_texts.append(f'60日线 {ma60:.0f}（现价{"站上" if close >= ma60 else "跌破"}）')
    if ma_texts:
        parts.append('、'.join(ma_texts) + '。')
    return ' '.join(parts)


def _analyze_breadth(quote_map):
    """全市场涨跌家数与市场整体状况"""
    sh = quote_map.get('1.000001')
    sz = quote_map.get('0.399001')
    if sh is None or sz is None:
        return None
    rise = int(round(sh.get('rise') or 0)) + int(round(sz.get('rise') or 0))
    fall = int(round(sh.get('fall') or 0)) + int(round(sz.get('fall') or 0))
    flat = int(round(sh.get('flat') or 0)) + int(round(sz.get('flat') or 0))
    total = rise + fall
    if total <= 0:
        return None
    red_ratio = round(rise / total * 100, 1)
    if red_ratio >= 70:
        conclusion = f'红盘率 {red_ratio:.1f}%，超过七成个股上涨，呈普涨格局，赚钱效应强。'
    elif red_ratio >= 55:
        conclusion = f'红盘率 {red_ratio:.1f}%，上涨家数明显占优，市场整体偏暖，参与性尚可。'
    elif red_ratio >= 45:
        conclusion = f'红盘率 {red_ratio:.1f}%，涨跌家数接近，多空分歧加大，属结构性行情，个股选择比仓位更重要。'
    elif red_ratio >= 30:
        conclusion = f'红盘率 {red_ratio:.1f}%，跌多涨少，亏钱效应扩散，操作上宜控制仓位、谨慎追高。'
    else:
        conclusion = f'红盘率 {red_ratio:.1f}%，市场普跌、情绪低迷，谨防恐慌性杀跌，耐心等待企稳。'
    return {
        'rise': rise, 'fall': fall, 'flat': flat, 'total': total,
        'red_ratio': red_ratio, 'conclusion': conclusion,
    }


def _analyze_turnover(turnover, indices):
    """两市成交额变化与市场温度"""
    if turnover is None:
        return None
    change_pct = turnover['change_pct']
    avg_pct = sum((it['change_pct'] or 0.0) for it in indices) / len(indices)
    up = avg_pct >= 0.05
    down = avg_pct <= -0.05
    if change_pct is None:
        conclusion = f'两市成交额 {turnover["today"]:.0f} 亿，暂无昨日对比数据。'
    elif change_pct >= 15 and up:
        conclusion = (f'两市成交额 {turnover["today"]:.0f} 亿，较昨日放量 +{change_pct:.1f}%，'
                      f'量价齐升、增量资金进场明显，市场温度显著回升。')
    elif change_pct >= 15 and down:
        conclusion = (f'两市成交额 {turnover["today"]:.0f} 亿，较昨日放量 +{change_pct:.1f}%，'
                      f'放量下跌意味着抛压沉重，市场温度偏冷，谨慎抄底。')
    elif change_pct <= -10 and up:
        conclusion = (f'两市成交额 {turnover["today"]:.0f} 亿，较昨日缩量 {change_pct:.1f}%，'
                      f'缩量上涨表明拉升缺少增量配合，持续性存疑。')
    elif change_pct <= -10 and down:
        conclusion = (f'两市成交额 {turnover["today"]:.0f} 亿，较昨日缩量 {change_pct:.1f}%，'
                      f'缩量回调说明抛压有所衰竭，关注止跌企稳信号。')
    else:
        conclusion = (f'两市成交额 {turnover["today"]:.0f} 亿，较昨日变动 {change_pct:+.1f}%，'
                      f'量能基本平稳，市场温度中性，方向取决于后续放量选择。')
    return dict(turnover, conclusion=conclusion)


def _analyze_minute(minute, sh_item):
    """上证日内形态：下探回升/支撑验证"""
    if minute is None or sh_item is None:
        return None
    prices = minute['prices']
    times = minute['times']
    if len(prices) < 30 or len(times) < len(prices):
        return None
    pre_close = minute['pre_close']
    low = min(prices)
    low_idx = prices.index(low)
    low_time = times[low_idx] if low_idx < len(times) else '--'
    high = max(prices)
    close = prices[-1]
    down_from_pre = (low - pre_close) / pre_close * 100 if pre_close else 0.0
    rebound = (close - low) / low * 100 if low else 0.0

    text = f'上证指数日内最高 {high:.2f}、最低 {low:.2f}（约{low_time}），收盘 {close:.2f}（昨收 {pre_close:.2f}）。'

    l20 = sh_item['low_20']
    if rebound < 0.25:
        text += '尾盘仍在日内低位附近，未见有效回升，走势偏弱，日内低点支撑有效性仍待确认。'
    else:
        text += f'盘中自低点回升 {rebound:.2f}%，'
        if down_from_pre <= -0.3:
            text += '呈“下探后回升”形态，'
        text += f'说明 {low:.0f} 一带存在承接买盘，下方支撑经受住了考验。'
        if l20 is not None:
            near = abs(low - l20) / l20 <= 0.008
            if near:
                text += f'且日内低点与近20日低点 {l20:.0f} 基本重合，关键点位支撑被确认，参考意义较强。'
            elif low < l20 * 0.99:
                text += f'不过日内低点已跌破近20日低点 {l20:.0f}，回升属于超跌反抽，该位后市或转为压力。'
    return {
        'high': round(high, 2),
        'low': round(low, 2),
        'low_time': low_time,
        'close': round(close, 2),
        'pre_close': round(pre_close, 2),
        'rebound': round(rebound, 2),
        'down_from_pre': round(down_from_pre, 2),
        'day': minute.get('day'),
        'conclusion': text,
    }


# ==================== 主入口 ====================

def run_review():
    """执行一次自助复盘，返回结构化数据与逐项分析结论"""
    try:
        quote_map = _fetch_quotes()
        kline_map = _fetch_all_klines()

        indices = []
        for spec in MAJOR_INDICES:
            k = kline_map.get(spec['secid'])
            if k is None:
                raise RuntimeError(f'{spec["name"]} 日K数据缺失')
            indices.append(_build_index_item(spec, quote_map[spec['secid']], k))

        breadth = _analyze_breadth(quote_map)

        turnover = _fetch_turnover()
        turnover_analysis = _analyze_turnover(turnover, indices)

        minute_row = db_get(_SH_MINUTE_KEY)
        minute = None
        if minute_row and _is_recent(minute_row[1]):
            minute = _fetch_sh_minute()
        sh_item = next((it for it in indices if it['secid'] == '1.000001'), None)
        minute_analysis = _analyze_minute(minute, sh_item)

        synergy = _analyze_synergy(indices)
        levels = [{
            'code': it['code'],
            'name': it['name'],
            'price': it['price'],
            'conclusion': _level_conclusion(it),
        } for it in indices]

        now = datetime.datetime.now()
        if is_a_trading_time():
            market_status = '盘中'
        elif now.weekday() >= 5:
            market_status = '休市'
        else:
            market_status = '已收盘'

        return {
            'success': True,
            'data': {
                'update_time': now.strftime('%Y-%m-%d %H:%M:%S'),
                'market_status': market_status,
                'indices': indices,
                'breadth': breadth,
                'turnover': turnover_analysis,
                'minute': minute_analysis,
                'synergy': synergy,
                'levels': levels,
            },
        }
    except Exception as e:
        return {'success': False, 'error': f'复盘失败: {e}'}
