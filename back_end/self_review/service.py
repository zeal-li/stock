"""自助复盘 - 主要指数复盘分析

功能：
1. 主要指数（上证/深证成指/创业板指/沪深300/科创50/中证500）行情一览（MA5/MA20/MA60）
2. 指数同频共振或分化研判
3. 关键点位、重要压力位/支撑位（20日高低点、60日区间、MA5/MA20/MA60）
4. 全市场上涨家数比例（市场宽度）
5. 两市总成交额变化（市场温度，量能相对近期均量判断）
6. 开盘首小时量价结构（放量上攻/滞涨/下跌）
7. 上证日内形态（下探回升/支撑验证）
8. 市场情绪（涨停/跌停/连板高度/连板梯队）
9. 资金面（两融余额趋势 + 行业板块主力资金流向）
10. 复盘总结 + 次日预案（数据交叉验证、背离信号、观察清单、关键信号）

数据源约定（单一数据源，不做多源串行兜底）：
- 指数实时行情 + 涨跌家数：东方财富 ulist
- 指数日K（压力/支撑/均线计算）：同花顺 v4/line 日K（近120交易日，与 K线弹窗同源）
- 两市总成交额（今日/昨日）+ 逐分钟累计：money_flow 轮询缓存的同花顺成交额分时
- 近期量能基准（近5日两市成交额）：同花顺 v4/line 指数日K（上证指数+深证综指成交额相加）
- 上证分时走势（开盘首小时价格、日内形态）：money_flow 轮询缓存
- 涨停/跌停/连板：东方财富涨停池/跌停池（push2ex，按复盘目标交易日取数）
- 两融余额：money_flow 轮询缓存（沪深交易所）
- 行业板块主力资金：sector_fund 模块缓存（东方财富 clist）
核心环节（指数行情/日K）取不到数据即整体报错返回；新增的补充维度
（首小时量价/情绪/资金）取不到则对应字段置空并在前端标注，不拼接替代数据。
"""
import datetime
import json
import time
import traceback
import requests
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from common import REQUEST_PROXIES
from common.utils import is_a_trading_time, is_etf
from money_flow.storage import db_get, _EM_HEADERS, _EM_UT, _SH_MINUTE_KEY, _TURNOVER_MINUTE_KEY

# 主要指数 → 同花顺证券代码（日K数据源，与 K线弹窗同源）
_THS_SYMBOLS = {
    '1.000001': 'sh_1A0001',   # 上证指数
    '0.399001': 'sz_399001',   # 深证成指
    '0.399006': 'sz_399006',   # 创业板指
    '1.000300': 'sh_1B0300',   # 沪深300
    '1.000688': 'sh_1B0688',   # 科创50
    '0.399905': 'sh_1B0905',   # 中证500
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

# 量能基准：近 N 个已收盘交易日的两市成交额均量（相对比较，不做绝对阈值）
_TURNOVER_RECENT_N = 5

# 同花顺 v4/line 指数日K：上证指数 + 深证综指 成交额相加 = 两市总成交额
_THS_INDEX_DAILY = (
    ('sh', '1A0001'),   # 上证指数（沪市全市场成交额）
    ('sz', '399106'),   # 深证综指（深市全市场成交额）
)

# 情绪数据：东方财富涨停池 / 跌停池（与行情同为东方财富单一数据源）
_ZT_POOL_URL = 'https://push2ex.eastmoney.com/getTopicZTPool'
_DT_POOL_URL = 'https://push2ex.eastmoney.com/getTopicDTPool'
_EM_ZT_UT = '7eea3edcaed734bea9cbfc24409ed989'

# 开盘首小时区间判定（分钟序列按 HH:MM 字符串比较即可）
_OPEN_HOUR_END = '10:30'


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


_THS_KLINE_URL = 'https://d.10jqka.com.cn/v4/line/{symbol}/01/{year}.js'
_THS_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.10jqka.com.cn/',
}


def _fetch_kline(symbol, min_bars=120):
    """同花顺 v4/line 日K：最近若干交易日（日期/收盘/最高/最低/成交量），与 K线弹窗同源。
    symbol 如 sh_1A0001 / sz_399001 / sh_600519；502/504 为限流，失败重试 3 次。
    最多回看 3 年，凑够 min_bars 根即停（默认 120；120日周期等更长窗口由调用方调大）。
    返回 {dates, closes, highs, lows, volumes}，均按日期升序。"""
    year = datetime.datetime.now().year
    dates, closes, highs, lows, volumes = [], [], [], [], []
    for y in range(year, year - 3, -1):  # 最多回看 3 年，凑够 min_bars 根即停
        raw = None
        for attempt in range(4):
            try:
                r = requests.get(_THS_KLINE_URL.format(symbol=symbol, year=y),
                                 headers=_THS_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
                if r.status_code == 404:
                    raw = ''
                    break
                if r.status_code == 200:
                    text = r.text
                    s, e = text.find('(') + 1, text.rfind(')')
                    if s > 0 and e > s:
                        raw = json.loads(text[s:e]).get('data', '')
                        break
            except Exception:
                pass
            if attempt < 3:
                time.sleep(0.3)
        if raw is None:
            raise RuntimeError(f'同花顺日K获取失败: {symbol}（{y}年）')

        y_dates, y_closes, y_highs, y_lows, y_vols = [], [], [], [], []
        for line in raw.split(';'):
            parts = line.split(',')
            if len(parts) < 5:
                continue
            close = _num(parts[4])  # 同花顺字段: date,open,high,low,close,volume,amount
            high = _num(parts[2])
            low = _num(parts[3])
            if close is None or close <= 0:
                continue
            # 同花顺对部分指数当日行可能只给收盘价（如沪深300/中证500盘中），
            # 开/高低缺失或为0时用收盘价补齐，与 K线弹窗解析一致，避免当日行被跳过
            if high is None or high <= 0:
                high = close
            if low is None or low <= 0:
                low = close
            y_dates.append(str(parts[0]))
            y_closes.append(close)
            y_highs.append(high)
            y_lows.append(low)
            y_vols.append(_num(parts[5]) if len(parts) > 5 else None)
        dates = y_dates + dates       # 更早年份插到最前，保证整体按日期升序
        closes = y_closes + closes
        highs = y_highs + highs
        lows = y_lows + lows
        volumes = y_vols + volumes
        if len(closes) >= min_bars:
            break
    if len(closes) < 20:
        raise RuntimeError(f'日K数据不足: {symbol}（仅 {len(closes)} 根）')
    return {'dates': dates, 'closes': closes, 'highs': highs, 'lows': lows, 'volumes': volumes}


def _fetch_all_klines():
    """并行抓取全部指数日K"""
    kline_map = {}
    with ThreadPoolExecutor(max_workers=len(MAJOR_INDICES)) as pool:
        futs = {pool.submit(_fetch_kline, _THS_SYMBOLS[s['secid']]): s for s in MAJOR_INDICES}
        for fut in futs:
            kline_map[futs[fut]['secid']] = fut.result()
    return kline_map


def _stock_ths_symbol(code, market):
    """股票代码 → 同花顺证券代码（market: 1=沪 0=深 2=北交所，北交所按沪前缀近似）"""
    prefix = 'sh' if market in ('1', '2') else 'sz'
    return f'{prefix}_{code}'


def _fetch_stock_quotes(stocks):
    """东财 ulist 批量获取股票实时行情，返回 {原始secid: {name, price, change_pct, ...}}"""
    code_orig_market = {s['code']: s['market'] for s in stocks}
    secids = ','.join(f"{'0' if s['market'] == '2' else s['market']}.{s['code']}" for s in stocks)
    url = 'https://push2delay.eastmoney.com/api/qt/ulist.np/get'
    params = {
        'fltt': 2, 'invt': 2, 'ut': _EM_UT,
        'fields': 'f2,f3,f4,f12,f13,f14,f15,f16,f17,f18',
        'secids': secids,
    }
    r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    body = json.loads(r.content.decode('utf-8', 'replace'))
    diff = ((body.get('data') or {}).get('diff')) or []
    quote_map = {}
    for row in diff:
        code = str(row.get('f12') or '').strip()
        if not code or code not in code_orig_market:
            continue
        secid = f"{code_orig_market[code]}.{code}"
        quote_map[secid] = {
            'name': str(row.get('f14') or ''),
            'price': _num(row.get('f2')),
            'change_pct': _num(row.get('f3')),
            'change_val': _num(row.get('f4')),
            'open': _num(row.get('f17')),
            'high': _num(row.get('f15')),
            'low': _num(row.get('f16')),
            'pre_close': _num(row.get('f18')),
        }
    return quote_map


# ==================== 自选股 压力/支撑（收盘价×成交量 成交密集区） ====================
# 旧模型用近N日最高/最低价（Donchian 极值），会把盘中瞬时影线与盘中未收盘的
# 当日K线当压力支撑，横盘时点位漂移、趋势中又失真。自选股改用：
#   1) 收盘价定区（不用影线极值）；
#   2) 收盘价按振幅聚成“成交密集区”（区带而非单点）；
#   3) 成交量加权 → 真实换手筹码带（中枢=区内成交量加权收盘价）；
#   4) 结论文本带趋势状态：趋势市中密集区为“突破/跌破确认位”，震荡市中才是硬压硬支；
#   5) 盘中剔除尚未收盘的当日K线，只统计已定型交易日。
# 单一数据源：行情=东财 ulist，日K=同花顺 v4/line，二者同属一只标的同一份记录，不做串行兜底。

_SR_WINDOWS = (20, 60, 120)        # 压力/支撑周期
_SR_ZONE_TOL_RATIO = 0.5           # 密集区聚类容差 = 窗口日均振幅 × 0.5（收盘价差在此内视为同一带）
_SR_ZONE_SPAN_RATIO = 2.0          # 单个密集区收盘价跨度上限 = 日均振幅 × 2（防慢牛/慢熊漂移伪密集）
_SR_NEAR_PCT = 1.5                 # 现价与密集区中枢距离 <= 1.5% 视为“贴近”，进入顶部关键位提醒
_BOLL_PERIOD = 20                  # 布林带周期（日/周均为 20）
_BOLL_STD = 2.0                    # 布林带标准差倍数


def _drop_incomplete_bar(k):
    """剔除尚未收盘的当日K线（盘中 THS 当日行是滚动未定型数据，会污染近N日密集区）。
    当日 15:00 前且末根K线日期=今天才剔除；收盘后 THS 当日行已定型则保留。
    非当日数据（休市/盘后复盘）原样返回。"""
    dates = k.get('dates') or []
    if not dates:
        return k
    now = datetime.datetime.now()
    if str(dates[-1]) == now.strftime('%Y%m%d') and now.hour * 60 + now.minute < 15 * 60:
        return {key: vals[:-1] for key, vals in k.items()}
    return k


def _sr_zones(closes, highs, lows, volumes, n):
    """把近 n 根已收盘K线按收盘价聚合成“成交密集区”（真实换手成本带）。
    相邻收盘价差 <= 日均振幅一半 → 并入同一区；且单区收盘价总跨度 <= 日均振幅×2，
    防止长时间缓涨/缓跌被误并成一个伪密集区。区内权重=成交量合计
    （同花顺日K volume 字段，个别行无量时按 1 根计，不引入其它数据源）。
    返回按中枢价升序的 [{'lo','hi','center','vol','bars'}]；
    已收盘K线不足 n 根时返回 []（该周期不计算）。"""
    if len(closes) < n:
        return []
    seg = list(zip(closes[-n:], highs[-n:], lows[-n:], volumes[-n:]))
    amps = [h - l for _, h, l, _ in seg if h and l and h > l]
    if amps:
        day_amp = sum(amps) / len(amps)
    else:
        cs = [c for c, _, _, _ in seg]
        day_amp = (max(cs) - min(cs)) * 0.02
    if day_amp <= 0:
        day_amp = 0.0
    tol = day_amp * _SR_ZONE_TOL_RATIO
    span_limit = day_amp * _SR_ZONE_SPAN_RATIO

    zones = []
    for c, _, _, v in sorted(seg, key=lambda x: x[0]):
        w = float(v) if v and v > 0 else 1.0
        if zones and tol > 0:
            last = zones[-1]
            if c - last['hi'] <= tol and c - last['lo'] <= span_limit:
                last['csum'] += c * w
                last['wsum'] += w
                last['vol'] += w
                last['hi'] = c
                last['bars'] += 1
                continue
        zones.append({'lo': c, 'hi': c, 'csum': c * w, 'wsum': w, 'vol': w, 'bars': 1})
    return [{'lo': z['lo'], 'hi': z['hi'],
             'center': z['csum'] / z['wsum'], 'vol': z['vol'], 'bars': z['bars']}
            for z in zones]


def _sr_nearest(zones, price):
    """现价上/下方最近密集区：above=中枢>=现价且离现价最近；below=中枢<现价且离现价最近。
    返回 (above_zone, below_zone)，缺省 None。"""
    above = below = None
    for z in zones:
        if z['center'] >= price:
            if above is None or z['center'] < above['center']:
                above = z
        else:
            if below is None or z['center'] > below['center']:
                below = z
    return above, below


def _vwap_close(closes, volumes):
    """区间成交量加权收盘均价（近N日平均成本）。volume 缺失/为零时按 1 根计（等权）。"""
    wsum = csum = 0.0
    for c, v in zip(closes, volumes):
        w = float(v) if v and v > 0 else 1.0
        wsum += w
        csum += c * w
    return csum / wsum if wsum > 0 else None


def _trend_info(closes):
    """近段趋势状态（用于结论文本的状态感知）：up/down/range + 净涨跌幅%。
    观察窗口取最近约20个已收盘交易日，数据不足 10 根返回 range/None。"""
    if len(closes) < 10:
        return 'range', None
    seg = closes[-(min(20, len(closes) - 1) + 1):]
    base = seg[0]
    if not base:
        return 'range', None
    net = (seg[-1] - base) / base * 100
    up = sum(1 for i in range(1, len(seg)) if seg[i] > seg[i - 1])
    ratio = up / (len(seg) - 1)
    if net >= 3 and ratio >= 0.6:
        return 'up', net
    if net <= -3 and ratio <= 0.4:
        return 'down', net
    return 'range', net


def _weekly_closes(dates, closes):
    """把日K按 ISO 周聚合为每周收盘价（每周最后一个交易日的收盘价），按时间升序返回列表。"""
    weekly = {}
    for d, c in zip(dates, closes):
        dt = datetime.datetime.strptime(str(d), '%Y%m%d')
        iso = dt.isocalendar()
        weekly[(iso[0], iso[1])] = c  # 同周内更晚交易日的收盘价覆盖
    return [weekly[k] for k in sorted(weekly.keys())]


def _bollinger(closes, period=20, num_std=2.0):
    """布林带（收盘价）：返回 (upper, mid, lower)。数据不足 period 根返回 (None, None, None)。"""
    if not closes or len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / period
    var = sum((c - mid) ** 2 for c in window) / period
    std = var ** 0.5
    return mid + num_std * std, mid, mid - num_std * std


def _stock_levels(s, q, k, decimals=None):
    """单只自选股/ETF：收盘价×成交量 成交密集区压力/支撑。
    返回行数据：price/change_pct/change_val、pressure_20~120/support_20~120、
    conclusion（状态感知文本）、near/hint（贴近提醒，供顶部关键点位汇总）。
    decimals 缺省时按标的本身判断：is_etf → 三位小数（场内基金价格保留三位），否则两位。"""
    def fmt(v):
        return _fmt_price(v, decimals)

    code = s['code']
    if decimals is None:
        decimals = 3 if is_etf(code, s['market']) else 2
    price = q['price']
    name = q.get('name') or code
    k = _drop_incomplete_bar(k)
    closes = k['closes']
    highs = k['highs']
    lows = k['lows']
    volumes = k['volumes']

    # ---- 布林带（日/周） ----
    daily_u, daily_m, daily_l = _bollinger(closes, _BOLL_PERIOD, _BOLL_STD)
    weekly_u, weekly_m, weekly_l = _bollinger(_weekly_closes(k['dates'], closes), _BOLL_PERIOD, _BOLL_STD)

    wins = []
    for n in _SR_WINDOWS:
        zones = _sr_zones(closes, highs, lows, volumes, n)
        above, below = _sr_nearest(zones, price)
        wins.append({'n': n, 'zones': zones, 'above': above, 'below': below})

    # ---- 行文本（筹码密集区 + 趋势/成本状态） ----
    def in_zone(z):
        return z is not None and z['lo'] <= price <= z['hi']

    levels = []     # 每周期结构化关键点位（前端渲染数值颜色/涨跌幅）
    for w in wins:
        n = w['n']
        zones, above, below = w['zones'], w['above'], w['below']
        if not zones:
            continue  # 数据不足该周期
        # 现价所在密集区：优先现价落在其内的区
        if above and in_zone(above):
            zin = above
        elif below and in_zone(below):
            zin = below
        else:
            zin = None

        lv = {'n': n, 'lo': None, 'hi': None, 'center': None,
              'note': None, 'pressure': None, 'support': None}
        if zin is not None:
            # 现价位于密集区内
            lv['lo'] = round(zin['lo'], decimals)
            lv['hi'] = round(zin['hi'], decimals)
            lv['center'] = round(zin['center'], decimals)
            if below is None:
                lv['note'] = '跌破该区下沿前下方暂无密集支撑'
            elif above is None:
                lv['note'] = '突破该区上沿后上方暂无密集压力'
            else:
                lv['note'] = '现价正处于该密集区内'
        else:
            # 现价不在任何密集区内：取离现价最近的区，并给出压力/支撑点位
            if above and below:
                zin = above if (above['center'] - price) <= (price - below['center']) else below
                lv['lo'] = round(zin['lo'], decimals)
                lv['hi'] = round(zin['hi'], decimals)
                lv['center'] = round(zin['center'], decimals)
                lv['pressure'] = round(above['center'], decimals)
                lv['support'] = round(below['center'], decimals)
            elif above:
                lv['lo'] = round(above['lo'], decimals)
                lv['hi'] = round(above['hi'], decimals)
                lv['center'] = round(above['center'], decimals)
                lv['note'] = '现价已跌破全部成交密集区，其下暂无密集支撑'
            elif below:
                lv['lo'] = round(below['lo'], decimals)
                lv['hi'] = round(below['hi'], decimals)
                lv['center'] = round(below['center'], decimals)
                lv['note'] = '现价已升破全部成交密集区，上方暂无近端压力'
            else:
                continue
        levels.append(lv)

    tail_parts = []  # 趋势 + 成本整体总结（纯文本）
    state, net = _trend_info(closes)
    if net is not None:
        if state == 'up':
            tail_parts.append(f'近20日趋势上行（净{net:+.1f}%），趋势市中上方密集区压力多为突破确认位、'
                              f'下方密集区回踩可低吸，勿因恐高而中途下车。')
        elif state == 'down':
            tail_parts.append(f'近20日趋势下行（净{net:+.1f}%），弱势中下方支撑有效性弱、易被跌破，'
                              f'反抽密集区宜减仓而非抄底。')
        else:
            tail_parts.append(f'近20日震荡整理（净{net:+.1f}%），密集区上下沿有效性强，适合区间高抛低吸。')

    m = min(60, len(closes))
    cost = _vwap_close(closes[-m:], volumes[-m:]) if closes else None
    if cost is not None:
        delta = (price - cost) / cost * 100
        tail_parts.append(f'近{m}日成交量加权均价（平均成本）{fmt(cost)}，现价较其'
                          f'{("高" if delta >= 0 else "低")} {abs(delta):.1f}%，'
                          f'持仓筹码多数{"浮盈" if delta >= 0 else "浮亏"}。')

    # ---- 行字段 ----
    item = {
        'code': code,
        'market': s['market'],
        'name': name,
        'price': round(price, decimals),
        'change_pct': round(q['change_pct'], 2) if q['change_pct'] is not None else None,
        'change_val': round(q['change_val'], decimals) if q['change_val'] is not None else None,
        'boll_daily': {
            'upper': None if daily_u is None else round(daily_u, decimals),
            'mid': None if daily_m is None else round(daily_m, decimals),
            'lower': None if daily_l is None else round(daily_l, decimals),
        },
        'boll_weekly': {
            'upper': None if weekly_u is None else round(weekly_u, decimals),
            'mid': None if weekly_m is None else round(weekly_m, decimals),
            'lower': None if weekly_l is None else round(weekly_l, decimals),
        },
    }
    for w in wins:
        n = w['n']
        above, below = w['above'], w['below']
        # 压力列：现价上方最近密集区中枢；若上方无带且现价位于下方带内部
        # （已突破到该带上半部），则取该带上沿作压力参考。
        if above:
            item[f'pressure_{n}'] = round(above['center'], decimals)
        elif below and below['lo'] <= price <= below['hi']:
            item[f'pressure_{n}'] = round(below['hi'], decimals)
        else:
            item[f'pressure_{n}'] = None
        # 支撑列：现价下方最近密集区中枢；若下方无带且现价位于上方带内部
        # （价格已在带内、中枢在其上方），则取该带下沿作支撑参考（跌破下沿才破位）。
        if below:
            item[f'support_{n}'] = round(below['center'], decimals)
        elif above and above['lo'] <= price <= above['hi']:
            item[f'support_{n}'] = round(above['lo'], decimals)
        else:
            item[f'support_{n}'] = None

    # ---- 贴近任一周期压力/支撑（顶部关键点位提醒用） ----
    best = None  # (dist_pct, kind, n, zone)
    for w in wins:
        above, below = w['above'], w['below']
        if above is not None and above['center'] > price:
            d = (above['center'] - price) / price * 100
            if d <= _SR_NEAR_PCT and (best is None or d < best[0]):
                best = (d, 'pressure', w['n'], above)
        if below is not None and below['center'] < price:
            d = (price - below['center']) / price * 100
            if d <= _SR_NEAR_PCT and (best is None or d < best[0]):
                best = (d, 'support', w['n'], below)
    if best:
        d, kind, n, z = best
        if kind == 'pressure':
            item['hint'] = (f'现价 {fmt(price)}，贴近{n}日成交密集区压力 {fmt(z["center"])}'
                            f'（距 +{d:.1f}%），放量突破则打开空间，受阻则回踩')
        else:
            item['hint'] = (f'现价 {fmt(price)}，贴近{n}日成交密集区支撑 {fmt(z["center"])}'
                            f'（距 -{d:.1f}%），守住可低吸，跌破则下看更远密集区')
    item['near'] = best[1] if best else None
    item['levels'] = levels
    item['conclusion'] = ' '.join(tail_parts) if tail_parts else '暂无足够已收盘K线计算关键点位。'
    return item


def _analyze_stocks(stocks, decimals=None):
    """自选股关键点位分析（收盘价×成交量 成交密集区压力/支撑，20/60/120日）。
    decimals 缺省时逐标的判断：is_etf → 三位小数，否则两位（与分组无关）。
    单一数据源：行情=东财 ulist，日K=同花顺 v4/line；任一缺失该股整行跳过。"""
    if not stocks:
        return []
    quote_map = _fetch_stock_quotes(stocks)
    symbols = {s['code']: _stock_ths_symbol(s['code'], s['market']) for s in stocks}

    kline_map = {}
    with ThreadPoolExecutor(max_workers=min(8, len(stocks))) as pool:
        # 拉取根数留足裕量：盘中 _drop_incomplete_bar 会剔除当日未定型K线，
        # 须保证剔除后仍 >= 最大周期窗口（120日）。
        need_bars = _SR_WINDOWS[-1] + 20
        futs = {pool.submit(_fetch_kline, symbols[s['code']], need_bars): s for s in stocks}
        for fut in futs:
            s = futs[fut]
            try:
                kline_map[s['code']] = fut.result()
            except Exception as e:
                print(f'[self-review] {s["code"]} 日K获取失败: {e}')
                kline_map[s['code']] = None

    items = []
    for s in stocks:
        secid = f"{s['market']}.{s['code']}"
        q = quote_map.get(secid)
        k = kline_map.get(s['code'])
        if q is None or q.get('price') is None or k is None:
            continue  # 行情或日K任一缺失 → 整行跳过，不做任何修补
        try:
            items.append(_stock_levels(s, q, k, decimals))
        except Exception as e:
            print(f'[self-review] {s["code"]} 关键点位计算失败: {e}')
    return items


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
    tday = _cache_trade_day(meta)
    return {
        'day': tday.strftime('%Y-%m-%d') if tday else None,
        'today': round(today_yi, 2),
        'yesterday': round(yesterday_yi, 2),
        'change': round(change_yi, 2),
        'change_pct': round(change_pct, 2) if change_pct is not None else None,
    }


def _fetch_recent_turnover(n=_TURNOVER_RECENT_N):
    """近期两市成交额（亿）：同花顺 v4/line 指数日K（上证指数+深证综指成交额相加）。
    返回按日期升序的 [(date_str, 亿元)]，最多 n+1 项（多取一项以便区分当日）。"""
    year = datetime.datetime.now().year
    daily = {}
    for y in (year, year - 1):
        for market, code in _THS_INDEX_DAILY:
            symbol = f'{market}_{code}'
            raw = None
            for attempt in range(4):
                try:
                    r = requests.get(_THS_KLINE_URL.format(symbol=symbol, year=y),
                                     headers=_THS_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
                    if r.status_code == 404:
                        raw = ''
                        break
                    if r.status_code == 200:
                        text = r.text
                        s, e = text.find('(') + 1, text.rfind(')')
                        if s > 0 and e > s:
                            raw = json.loads(text[s:e]).get('data', '')
                            break
                except Exception:
                    pass
                if attempt < 3:
                    time.sleep(0.3)
            if raw is None:
                raise RuntimeError(f'同花顺指数日K获取失败: {symbol}（{y}年）')
            for line in raw.split(';'):
                parts = line.split(',')
                if len(parts) < 7:
                    continue
                amount = _num(parts[6])
                if amount is None or amount <= 0:
                    continue
                daily[parts[0]] = daily.get(parts[0], 0.0) + amount / 1e8
        if len(daily) >= n + 1:
            break
    if not daily:
        return []
    dates = sorted(daily)
    return [(f'{d[:4]}-{d[4:6]}-{d[6:8]}', round(daily[d], 2)) for d in dates[-(n + 1):]]


def _fetch_sh_minute(row=None):
    """上证指数分时，来源 money_flow 轮询缓存（东财 trends2）。row 可复用已查询的缓存。"""
    if row is None:
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
    tday = _cache_trade_day(meta)
    return {
        'day': tday.strftime('%Y-%m-%d') if tday else None,
        'times': times,
        'prices': prices,
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
    if q['price'] is None:
        raise RuntimeError(f'{spec["name"]} 实时价缺失')
    close = q['price']
    decimals = spec.get('decimals', 2)

    n20 = min(20, len(highs))
    n60 = min(60, len(highs))
    high_20 = max(highs[-n20:])
    low_20 = min(lows[-n20:])
    high_60 = max(highs[-n60:])
    low_60 = min(lows[-n60:])
    ma5 = _sma(closes, 5)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    span = high_60 - low_60
    pos_pct = round((close - low_60) / span * 100, 1) if span > 0 else 50.0

    return {
        'code': spec['code'],
        'secid': spec['secid'],
        'name': q.get('name') or spec['name'],
        'price': round(close, decimals),
        'change_pct': round(q['change_pct'], 2) if q['change_pct'] is not None else None,
        'change_val': round(q['change_val'], 2) if q['change_val'] is not None else None,
        'open': round(q['open'], 2) if q['open'] is not None else None,
        'high': round(q['high'], 2) if q['high'] is not None else None,
        'low': round(q['low'], 2) if q['low'] is not None else None,
        'pre_close': round(q['pre_close'], 2) if q['pre_close'] is not None else None,
        'ma5': round(ma5, decimals) if ma5 is not None else None,
        'ma20': round(ma20, decimals) if ma20 is not None else None,
        'ma60': round(ma60, decimals) if ma60 is not None else None,
        'high_20': round(high_20, decimals),
        'low_20': round(low_20, decimals),
        'high_60': round(high_60, decimals),
        'low_60': round(low_60, decimals),
        'pos_pct': pos_pct,
    }


# ==================== 分析研判 ====================

def _analyze_synergy(indices):
    """指数同频共振 / 分化研判"""
    pct_of = {it['name']: it['change_pct'] for it in indices if it['change_pct'] is not None}
    missing = [it['name'] for it in indices if it['change_pct'] is None]
    if not pct_of:
        return {'mode': '数据缺失', 'up': [], 'down': [], 'flat': [],
                'summary': '主要指数涨跌幅数据均缺失，暂无法进行共振研判。'}
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
        if sh is not None and cyb is not None and sh >= 0.05 and cyb <= -0.5:
            summary += '上证与创业板方向背离，指数加权参考意义下降，当前更适合重个股、轻指数。'
        elif sh is not None and cyb is not None and sh <= -0.5 and cyb >= 0.05:
            summary += '上证偏弱而创业板走强，资金弃权重、抱成长，局部做多力量仍在。'
    if missing:
        summary += '、'.join(missing) + '涨跌幅数据缺失，未纳入研判。'
    return {'mode': mode, 'up': up, 'down': down, 'flat': flat, 'summary': summary}


# 贴近关键位的距离比例（0.3%）：现价在 20 日高点/低点 ±0.3% 内视为"贴近"
_NEAR_RATIO = 0.003


def _fmt_price(v, decimals=None):
    """价格显示：decimals 指定时按指定小数位；否则 >=100 整数（指数），>=10 一位，<10 两位"""
    if v is None:
        return '--'
    if decimals is not None:
        return f'{v:.{decimals}f}'
    if abs(v) >= 100:
        return f'{v:.0f}'
    if abs(v) >= 10:
        return f'{v:.1f}'
    return f'{v:.2f}'


def _level_conclusion(it, decimals=2):
    """单只标的关键点位/压力支撑小结（指数/股票/ETF 通用，decimals 控制价格小数位）"""
    def fmt(v):
        return _fmt_price(v, decimals)
    close = it['price']
    h20, l20 = it['high_20'], it['low_20']
    h60, l60 = it['high_60'], it['low_60']
    ma5, ma20, ma60 = it['ma5'], it['ma20'], it['ma60']
    parts = []
    parts.append(f'近60日区间 {fmt(l60)} ~ {fmt(h60)}，现价位于区间 {it["pos_pct"]:.0f}% 分位。')

    near_ratio = _NEAR_RATIO  # 视为"贴近"的距离比例
    if close >= h20:
        if h60 > close:
            parts.append(f'已刷新近20日高点 {fmt(h20)}，上方直接压力看60日高点 {fmt(h60)}（+{(h60 - close) / close * 100:.1f}%）。')
        else:
            parts.append(f'已刷新近20日乃至60日高点，上方无明显近端套牢压力，趋势偏强。')
    elif close >= h20 * (1 - near_ratio):
        parts.append(f'现价紧贴20日高点压力 {fmt(h20)}（距 {+((h20 - close) / close * 100):.1f}%），放量突破则打开上行空间，受阻则回踩。')
    else:
        parts.append(f'上方压力：近20日高点 {fmt(h20)}（距现价 +{(h20 - close) / close * 100:.1f}%）。')

    if close <= l20:
        if l60 < close:
            parts.append(f'已跌破近20日低点 {fmt(l20)}，下方关键支撑下移至60日低点 {fmt(l60)}（距现价 -{(close - l60) / close * 100:.1f}%）。')
        else:
            parts.append(f'现价已创近60日新低，下行趋势中未见明确支撑，等待企稳信号。')
    elif close <= l20 * (1 + near_ratio):
        parts.append(f'现价正逼近20日低点支撑 {fmt(l20)}（距 -{(close - l20) / close * 100:.1f}%），该支撑正被考验，守住则短线止跌。')
    else:
        parts.append(f'下方支撑：近20日低点 {fmt(l20)}（距现价 -{(close - l20) / close * 100:.1f}%）。')

    ma_texts = []
    if ma5 is not None:
        ma_texts.append(f'5日线 {fmt(ma5)}（现价{"站上" if close >= ma5 else "跌破"}）')
    if ma20 is not None:
        ma_texts.append(f'20日线 {fmt(ma20)}（现价{"站上" if close >= ma20 else "跌破"}）')
    if ma60 is not None:
        ma_texts.append(f'60日线 {fmt(ma60)}（现价{"站上" if close >= ma60 else "跌破"}）')
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


def _analyze_turnover(turnover, recent, indices):
    """两市成交额变化与市场温度：量能活跃与否相对近期均量判断"""
    if turnover is None:
        return None
    change_pct = turnover['change_pct']
    today = turnover['today']
    today_day = turnover.get('day')

    # 量能基准：近 N 个已收盘交易日均量（排除当日）
    if today_day is None:
        base_vals = [v for _, v in recent[:-1]]
    else:
        base_vals = [v for d, v in recent if d < today_day]
    base_vals = base_vals[-_TURNOVER_RECENT_N:]

    if base_vals:
        base = sum(base_vals) / len(base_vals)
        ratio = today / base
        delta_pct = (ratio - 1) * 100
        if ratio >= 1.2:
            band = f'两市成交额 {today:.0f} 亿，较近{len(base_vals)}日均量 {base:.0f} 亿放量 +{delta_pct:.0f}%'
            band_tag = '活跃'
        elif ratio <= 0.8:
            band = f'两市成交额 {today:.0f} 亿，较近{len(base_vals)}日均量 {base:.0f} 亿缩量 {delta_pct:.0f}%'
            band_tag = '偏低'
        else:
            band = f'两市成交额 {today:.0f} 亿，与近{len(base_vals)}日均量 {base:.0f} 亿基本相当（{delta_pct:+.0f}%）'
            band_tag = '正常'
    else:
        band = f'两市成交额 {today:.0f} 亿'
        band_tag = '正常'

    valid = [it['change_pct'] for it in indices if it['change_pct'] is not None]
    if not valid:
        return dict(turnover, band=band_tag,
                    conclusion=f'{band}，指数涨跌幅数据缺失，暂无法判断量价配合方向。')

    avg_pct = sum(valid) / len(valid)
    up = avg_pct >= 0.05
    down = avg_pct <= -0.05

    if change_pct is None:
        conclusion = f'{band}，暂无昨日对比数据。'
    elif change_pct >= 15 and up:
        conclusion = (f'{band}，较昨日放量 +{change_pct:.1f}%，'
                      f'量价齐升、增量资金进场明显，市场温度显著回升。')
    elif change_pct >= 15 and down:
        conclusion = (f'{band}，较昨日放量 +{change_pct:.1f}%，'
                      f'放量下跌意味着抛压沉重，市场温度偏冷，谨慎抄底。')
    elif change_pct <= -10 and up:
        conclusion = (f'{band}，较昨日缩量 {change_pct:.1f}%，'
                      f'缩量上涨表明拉升缺少增量配合，持续性存疑。')
    elif change_pct <= -10 and down:
        conclusion = (f'{band}，较昨日缩量 {change_pct:.1f}%，'
                      f'缩量回调说明抛压有所衰竭，关注止跌企稳信号。')
    else:
        conclusion = (f'{band}，较昨日变动 {change_pct:+.1f}%，'
                      f'量能基本平稳，市场温度中性，方向取决于后续放量选择。')
    return dict(turnover, band=band_tag, conclusion=conclusion)


def _seg_pct(prices, times, start, end):
    """分时某时段 [start, end]（HH:MM）内的涨跌幅（时段首尾价格），数据不足返回 None"""
    s = e = None
    for t, p in zip(times, prices):
        if start <= t <= end:
            if s is None:
                s = p
            e = p
    if s is None or e is None or not s:
        return None
    return (e - s) / s * 100


def _analyze_minute(minute, sh_item):
    """上证日内形态：下探回升/支撑验证"""
    if minute is None or sh_item is None:
        return None
    prices = minute['prices']
    times = minute['times']

    # 开/高/低/收/昨收/涨跌幅以 ulist 实时行情为准（与主要指数复盘一致），
    # 分时序列仅用于定位日内高低点出现的时间。
    open_price = sh_item.get('open')
    high = sh_item.get('high')
    low = sh_item.get('low')
    close = sh_item.get('price')
    pre_close = sh_item.get('pre_close')
    change_pct = sh_item.get('change_pct')

    # 关键价格缺失时退回分时序列推算
    if high is None or low is None or close is None or pre_close is None:
        if len(prices) < 30 or len(times) < len(prices):
            return None
    if high is None:
        high = max(prices)
    if low is None:
        low = min(prices)
    if close is None:
        close = prices[-1]
    if open_price is None:
        open_price = prices[0]
    if pre_close is None:
        pre_close = minute.get('pre_close')
    if close is None or pre_close is None or low is None or high is None:
        return None
    if open_price is None:
        open_price = close
    if change_pct is None:
        change_pct = (close - pre_close) / pre_close * 100 if pre_close else 0.0

    # 定位日内高低点出现时间（取与权威值最接近的分时点）
    high_time = '--'
    low_time = '--'
    if len(prices) >= 30 and len(times) >= len(prices):
        hi = min(range(len(prices)), key=lambda i: abs(prices[i] - high))
        high_time = times[hi] if hi < len(times) else '--'
        li = min(range(len(prices)), key=lambda i: abs(prices[i] - low))
        low_time = times[li] if li < len(times) else '--'

    open_pct = (open_price - pre_close) / pre_close * 100 if pre_close else 0.0
    down_from_pre = (low - pre_close) / pre_close * 100 if pre_close else 0.0
    rebound = (close - low) / low * 100 if low else 0.0
    high_pct = (high - pre_close) / pre_close * 100 if pre_close else 0.0
    low_pct = (low - pre_close) / pre_close * 100 if pre_close else 0.0
    # 当日振幅（相对昨收）、最大盘中反弹（低→高）、收盘/开盘在日内区间的位置（0=最低 100=最高）
    amplitude = (high - low) / pre_close * 100 if pre_close else 0.0
    max_rebound = (high - low) / low * 100 if low else 0.0
    close_pos = (close - low) / (high - low) * 100 if high > low else 50.0
    open_pos = (open_price - low) / (high - low) * 100 if high > low else 50.0

    # 第一维度：方向（收盘定势）
    if change_pct >= 0.05:
        direction = '收阳'
    elif change_pct <= -0.05:
        direction = '收阴'
    else:
        direction = '平盘'

    # 高低点出现先后（决定 V 型还是倒 V/A 字）
    low_first = low_time != '--' and high_time != '--' and low_time <= high_time

    # 第三维度：关键时段涨跌
    early = _seg_pct(prices, times, '09:30', '10:00')   # 早盘半小时
    noon = _seg_pct(prices, times, '13:00', '13:30')    # 午后开盘
    tail = _seg_pct(prices, times, '14:50', '15:00')    # 尾盘

    text = ''
    form = ''

    # 第二维度：核心形态
    if high <= low or amplitude < 0.3:
        form = '横盘窄幅震荡'
        text += f'全天振幅仅 {amplitude:.2f}%，横盘窄幅震荡（{direction}），多空均无力打破僵局，属垃圾时间，宜观望。'
    elif open_pos < 30 and close_pos >= 75 and low_first:
        form = '单边上攻'
        text += (f'单边上攻形态：开盘即见低点（约{low_time}），随后逐级走高，'
                 f'收盘贴近全日最高（区间 {close_pos:.0f}% 分位），趋势型强势，持股最佳形态。')
    elif open_pos > 70 and close_pos <= 25 and not low_first:
        form = '单边下杀'
        text += (f'单边下杀形态：开盘即见高点（约{high_time}），随后逐级走低，'
                 f'收盘贴近全日最低（区间 {close_pos:.0f}% 分位），趋势型弱势，严禁抄底，宜空仓/止损。')
    elif low_first and low_time <= '11:30' and close_pos >= 70:
        form = 'V型反转'
        text += (f'V型反转（深V）：{low_time} 前后急速下探见底，午后拉升收复失地，'
                 f'收盘 {close_pos:.0f}% 分位，日内见底信号，短线转强。')
    elif not low_first and high_time <= '11:00' and close_pos <= 30:
        form = '倒V（A字杀）'
        text += (f'倒V（A字杀）：早盘诱多冲高（约{high_time}见顶），午后急速跳水，'
                 f'收盘 {close_pos:.0f}% 分位，套牢追高者，日内见顶信号，杀伤力较大。')
    elif amplitude >= 1.2 and 33 <= close_pos < 66:
        form = '宽幅N字震荡'
        text += (f'宽幅N字震荡：盘中多次涨跌交替（振幅 {amplitude:.2f}%），收盘回到区间中段，'
                 f'洗盘特征明显，关键看二次低点/高点是否抬高。')
    else:
        form = '震荡'
        if close_pos >= 66:
            text += f'收盘位于日内区间 {close_pos:.0f}% 分位（高位区），自低点回升 {rebound:.2f}%，承接有力，下方支撑经受住了考验。'
        elif close_pos < 33:
            text += f'收盘位于日内区间 {close_pos:.0f}% 分位（低位区），自低点仅回升 {rebound:.2f}%，走势偏弱，支撑有效性仍待确认。'
        else:
            text += f'收盘位于日内区间 {close_pos:.0f}% 分位（中位区），多空拉锯，支撑有效性一般，方向仍需观察。'

    # 时段要点（第三维度补充）
    seg_notes = []
    if early is not None and abs(early) >= 0.3:
        seg_notes.append(f'早盘半小时{"高开高走" if early >= 0 else "低开低走"}（{early:+.2f}%），全天定调{"偏强" if early >= 0 else "偏弱"}')
    if noon is not None and abs(noon) >= 0.3:
        seg_notes.append(f'午后开盘{"拉升" if noon >= 0 else "跳水"}（{noon:+.2f}%），出现{"向上" if noon >= 0 else "向下"}变盘')
    if tail is not None and abs(tail) >= 0.2:
        seg_notes.append(f'尾盘{"偷袭拉升" if tail >= 0 else "砸尾盘"}（{tail:+.2f}%）')
    if seg_notes:
        text += '时段要点：' + '；'.join(seg_notes) + '。'

    # 20日低点联动
    l20 = sh_item['low_20']
    if l20 is not None:
        near = abs(low - l20) / l20 <= 0.008
        if near:
            text += f'日内低点与近20日低点 {l20:.0f} 基本重合，关键点位支撑被确认。'
        elif low < l20 * 0.99:
            text += f'日内低点已跌破近20日低点 {l20:.0f}，回升属于超跌反抽，该位后市或转为压力。'
    return {
        'high': round(high, 2),
        'high_time': high_time,
        'high_pct': round(high_pct, 2),
        'low': round(low, 2),
        'low_time': low_time,
        'low_pct': round(low_pct, 2),
        'open': round(open_price, 2),
        'open_pct': round(open_pct, 2),
        'close': round(close, 2),
        'pre_close': round(pre_close, 2),
        'change_pct': round(change_pct, 2),
        'rebound': round(rebound, 2),
        'down_from_pre': round(down_from_pre, 2),
        'amplitude': round(amplitude, 2),
        'max_rebound': round(max_rebound, 2),
        'close_pos': round(close_pos, 1),
        'form': form,
        'direction': direction,
        'day': minute.get('day'),
        'conclusion': text,
    }


# ==================== 目标交易日 ====================

def _is_workday(d):
    """是否为工作日（法定节假日处理跟随项目 chinese_calendar 约定）"""
    try:
        from chinese_calendar import is_workday
        return is_workday(d)
    except ImportError:
        return d.weekday() < 5


def _target_trade_day():
    """复盘目标交易日：盘中（>=09:30）取当日；盘前/非交易日取最近已收盘交易日"""
    now = datetime.datetime.now()
    d = now.date()
    while not _is_workday(d):
        d -= datetime.timedelta(days=1)
    # 盘前（今天尚未开盘）：今日数据未生成，回退到上一交易日
    if d == now.date() and now.hour * 60 + now.minute < 9 * 60 + 30:
        d -= datetime.timedelta(days=1)
        while not _is_workday(d):
            d -= datetime.timedelta(days=1)
    return d


def _cache_trade_day(meta):
    """分时缓存的时间戳 meta → 缓存内容所属交易日(date)。
    money_flow 轮询仅在交易时段写入 meta=当日；周末重启补抓会用非交易日时间戳
    覆盖内容仍为最近交易日的缓存，因此非工作日时间戳需回溯到最近工作日。"""
    d_str = _meta_day(meta)
    if not d_str:
        return None
    try:
        d = datetime.datetime.strptime(d_str, '%Y-%m-%d').date()
    except ValueError:
        return None
    while not _is_workday(d):
        d -= datetime.timedelta(days=1)
    return d


# ==================== 开盘首小时量价 ====================

def _cum_cutoff(times, values, hhmm):
    """分钟序列（累计值）中取时间点 <= hhmm 的最后一个值，找不到返回 None"""
    last = None
    for t, v in zip(times, values):
        if t <= hhmm:
            last = v
        else:
            break
    return last


def _analyze_open_hour(day):
    """开盘首小时量价结构：两市逐分钟累计成交额 + 上证分时价格。
    数据要求为复盘目标交易日的当日缓存，缺当日数据返回 None。"""
    trow = db_get(_TURNOVER_MINUTE_KEY)
    mrow = db_get(_SH_MINUTE_KEY)
    if not trow or not mrow:
        return None
    tdata = (trow[0].get('data') or {})
    mdata = (mrow[0].get('data') or {})
    t_times = tdata.get('times') or []
    t_vals = tdata.get('turnovers') or []
    p_times = mdata.get('times') or []
    p_vals = mdata.get('prices') or []
    if not t_times or len(t_times) != len(t_vals) or not p_times or len(p_times) != len(p_vals):
        return None
    day_str = day.strftime('%Y-%m-%d')
    if _cache_trade_day(trow[1]) != day or _cache_trade_day(mrow[1]) != day:
        return None  # 缓存不是目标交易日当天数据（如轮询尚未产出当日数据）

    cum_open = _cum_cutoff(t_times, t_vals, _OPEN_HOUR_END)
    if cum_open is None:
        return None
    cum_now = t_vals[-1]
    complete = t_times[-1] >= _OPEN_HOUR_END and p_times[-1] >= _OPEN_HOUR_END
    ratio = cum_open / cum_now * 100 if cum_now else 0.0

    open_price = p_vals[0]
    p_at_cut = _cum_cutoff(p_times, p_vals, _OPEN_HOUR_END)
    if p_at_cut is None:
        return None
    pre_close = _num(mdata.get('preClose'))
    sh_pct = (p_at_cut - open_price) / open_price * 100 if open_price else None
    sh_vs_pre = (p_at_cut - pre_close) / pre_close * 100 if pre_close else None

    head = (f'开盘首小时（09:30-10:30）两市成交 {cum_open:.0f} 亿，约占当日累计成交 {ratio:.0f}%'
            if complete else
            f'截至 {t_times[-1]} 两市成交 {cum_open:.0f} 亿（当日累计 {cum_now:.0f} 亿，首小时尚未结束）')
    if sh_pct is not None:
        head += f'；同期上证相对开盘{("上涨" if sh_pct >= 0 else "下跌")}{abs(sh_pct):.2f}%'

    if not complete:
        verdict = '开盘首小时尚未走完，当前量价仅作参考，暂不构成全天判断依据。'
    elif sh_pct is None:
        verdict = '开盘一小时量价结构因分时价格缺失暂无法完整研判，仅作参考。'
    elif ratio >= 36:
        # 量能高度集中于早盘：开盘一小时已占全天三成六以上，资金早盘剧烈换手
        if sh_pct >= 0.3:
            verdict = '开盘一小时量能高度前置且指数同步走强，属放量上攻，但早盘天量换手后需提防午后承接不足。'
        elif sh_pct > -0.3:
            verdict = '开盘一小时量能高度前置但指数滞涨（相对开盘涨幅不足0.3%），放量滞涨、谨防冲高回落。'
        else:
            verdict = '开盘一小时量能高度前置且指数下挫，放量下跌、资金早盘集中出逃，日内整体承压，谨慎抄底。'
    elif ratio >= 24:
        if sh_pct >= 0.3:
            verdict = '开盘一小时量价齐升，早盘买盘活跃、量能配合良好，短线强度较好。'
        elif sh_pct <= -0.3:
            verdict = '开盘一小时放量下跌，资金早盘流出偏多，日内情绪偏弱，等待企稳信号。'
        else:
            verdict = '开盘一小时量价基本平稳，未出现明显方向性信号，按常态应对即可。'
    else:
        verdict = '早盘成交相对清淡、观望情绪浓，量能不足以支撑方向选择，等待放量确认。'

    return {
        'day': day_str,
        'complete': complete,
        'open_amt': round(cum_open, 0),
        'total_now': round(cum_now, 0),
        'ratio': round(ratio, 1),
        'sh_pct': round(sh_pct, 2) if sh_pct is not None else None,
        'sh_vs_pre': round(sh_vs_pre, 2) if sh_vs_pre is not None else None,
        'verdict': verdict,
        'conclusion': head + '。' + verdict,
    }


# ==================== 市场情绪（涨停/跌停/连板） ====================

def _fetch_limit_pool(url, sort, day_str, label):
    """东财涨停池/跌停池单次抓取，返回规整后的 pool 列表"""
    params = {
        'ut': _EM_ZT_UT, 'dpt': 'wz.ztzt',
        'Pageindex': '0', 'pagesize': '6000',
        'sort': sort, 'date': day_str,
    }
    r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=10, proxies=REQUEST_PROXIES)
    body = r.json()
    data = body.get('data') or None
    if data is None:
        raise RuntimeError(f'{label}数据为空（东财 {url}）')
    pool = data.get('pool') or []
    rows = []
    for x in pool:
        name = str(x.get('n') or '')
        code = str(x.get('c') or '')
        if not code:
            continue
        rows.append({
            'code': code,
            'name': name,
            'market': x.get('m'),
            'lbc': int(x.get('lbc') or 1),
            'industry': str(x.get('hybk') or ''),
        })
    return rows


def _is_st_name(name):
    """涨停/跌停统计口径：名称含 ST / 退 记为风险股，单独计数"""
    return 'ST' in name.upper() or '退' in name


def _analyze_sentiment(day):
    """市场情绪：涨停/跌停家数、最高连板、连板梯队与断层研判"""
    day_str = day.strftime('%Y%m%d')
    zt = _fetch_limit_pool(_ZT_POOL_URL, 'fbt:asc', day_str, '涨停池')
    dt = _fetch_limit_pool(_DT_POOL_URL, 'fund:asc', day_str, '跌停池')

    zt_st = sum(1 for x in zt if _is_st_name(x['name']))
    dt_st = sum(1 for x in dt if _is_st_name(x['name']))
    zt_clean = [x for x in zt if not _is_st_name(x['name'])]
    dt_clean = [x for x in dt if not _is_st_name(x['name'])]

    ladder = Counter()
    for x in zt_clean:
        if x['lbc'] >= 2:
            ladder[x['lbc']] += 1
    max_lb = max((x['lbc'] for x in zt_clean), default=0)
    ladder_list = sorted(ladder.items(), reverse=True)

    # 连板高标（次日风向标）：3板及以上，按连板高度降序
    leaders = [
        {'name': x['name'], 'lbc': x['lbc'], 'industry': x['industry']}
        for x in sorted((x for x in zt_clean if x['lbc'] >= 3), key=lambda x: -x['lbc'])[:8]
    ]

    # 连板梯队断层检测（自2板至最高板之间若有缺失即为断层）
    gaps = []
    if max_lb >= 3:
        for h in range(2, max_lb):
            if h not in ladder:
                gaps.append(h)

    total_zt, total_dt = len(zt), len(dt)
    parts = [f'涨停 {total_zt} 家（非ST {len(zt_clean)}）', f'跌停 {total_dt} 家（非ST {len(dt_clean)}）']

    if zt_clean:
        temp_parts = []
        if len(zt_clean) >= 60:
            temp_parts.append('涨停家数显著偏高，情绪亢奋，但需警惕过热后的退潮风险')
        elif len(zt_clean) >= 35:
            temp_parts.append('涨停家数维持高位，赚钱效应较好，情绪偏暖')
        elif len(zt_clean) >= 15:
            temp_parts.append('涨停家数中等，局部热点存在，但扩散度一般')
        else:
            temp_parts.append('涨停家数稀少，市场缺乏做多主线，情绪偏冷')
        if total_dt >= 20:
            temp_parts.append('跌停家数较多，亏钱效应与恐慌情绪并存')
        elif total_dt >= 10:
            temp_parts.append('跌停家数偏多，弱势股亏钱效应开始显现')
        if max_lb >= 4:
            temp_parts.append(f'最高 {max_lb} 连板，短线高度打开、资金接力意愿强')
        elif max_lb == 0:
            temp_parts.append('无涨停个股，市场情绪冰点')
        elif max_lb <= 2:
            temp_parts.append(f'连板高度仅 {max_lb} 板，接力资金谨慎，多为首板博弈')
        if ladder_list:
            ladder_text = '、'.join(f'{h}板{v}家' for h, v in ladder_list)
            if gaps:
                temp_parts.append(f'连板梯队【{ladder_text}】存在断层（{"/".join(map(str, gaps))}板空缺），接力链条不完整，谨防高度压制')
            else:
                temp_parts.append(f'连板梯队【{ladder_text}】衔接完整，做多梯队健康')
        text = '，'.join(temp_parts) + '。'
    else:
        text = '全市场无涨停个股（剔除ST），做多力量缺失；若跌停亦多则恐慌情绪占主导。'

    return {
        'day': day.strftime('%Y-%m-%d'),
        'zt_total': total_zt,
        'zt_clean': len(zt_clean),
        'zt_st': zt_st,
        'dt_total': total_dt,
        'dt_clean': len(dt_clean),
        'dt_st': dt_st,
        'max_lb': max_lb,
        'ladder': [{'h': h, 'count': v} for h, v in ladder_list],
        'gaps': gaps,
        'leaders': leaders,
        'conclusion': '；'.join(parts) + '。' + text,
    }


# ==================== 资金面（两融 + 板块主力资金） ====================

def _parse_yi(s):
    """' +19.98亿' / '-1.2万' / '-3' → 亿为单位的数值，解析失败返回 None"""
    if not s:
        return None
    s = str(s).strip()
    neg = s.startswith('-')
    body = s.lstrip('+-').strip()
    if not body:
        return None
    try:
        if body.endswith('万亿'):
            val = float(body[:-2]) * 10000
        elif body.endswith('亿'):
            val = float(body[:-1])
        elif body.endswith('万'):
            val = float(body[:-1]) / 10000
        else:
            val = float(body)
        return -val if neg else val
    except ValueError:
        return None


def _analyze_funds(day):
    """资金面：两融余额趋势（杠杆方向）+ 行业板块主力净流入/流出（资金主线）"""
    result = {}
    parts = []

    # 1. 两融（money_flow 轮询缓存，沪深交易所，T+1 数据）
    mrow = db_get('margin_trading')
    if mrow:
        md = (mrow[0].get('data') or {})
        latest_total = md.get('latest_total')
        if latest_total is not None:
            date_full = None
            latest_date = md.get('latest_date')
            if latest_date and len(str(latest_date)) >= 5:
                mmdd = str(latest_date)[-5:]  # 'MM-DD'
                year = day.year
                # 数据日期不可能晚于复盘日；若 MM-DD 在复盘日之后说明跨年，年份减一
                if (day.month, day.day) < (int(mmdd[:2]), int(mmdd[3:])):
                    year -= 1
                date_full = f'{year}-{mmdd}'
            margin = {
                'date': date_full,
                'latest_total': round(latest_total, 0),
                'fin_bal_5d': md.get('fin_bal_5d'),
                'fin_bal_10d': md.get('fin_bal_10d'),
                'fin_buy_heat': md.get('fin_buy_heat'),
            }
            result['margin'] = margin
            f5 = margin['fin_bal_5d']
            f10 = margin['fin_bal_10d']
            if f5 is not None:
                if f5 >= 1:
                    trend = f'两融余额 {latest_total:.0f} 亿，5日变化 {f5:+.2f}%，杠杆资金趋势性加仓、风险偏好回升'
                elif f5 <= -1:
                    trend = f'两融余额 {latest_total:.0f} 亿，5日变化 {f5:+.2f}%，杠杆资金持续去化、风险偏好收缩'
                else:
                    trend = f'两融余额 {latest_total:.0f} 亿，5日变化 {f5:+.2f}%，杠杆资金基本平稳'
            else:
                trend = f'两融余额 {latest_total:.0f} 亿'
            if f10 is not None:
                trend += f'（10日 {f10:+.2f}%）'
            if margin['fin_buy_heat'] is not None:
                heat = margin['fin_buy_heat']
                trend += f'，融资买入较20日均值{("活跃 " if heat >= 20 else ("偏淡 " if heat <= -20 else "接近 "))}{heat:+.0f}%'
            parts.append(trend + '。')

    # 2. 行业板块主力资金流向（sector_fund 模块，东方财富 clist 实时缓存）
    from sector_fund.service import get_sector_fund
    sf = get_sector_fund('industry', 'today')
    if sf.get('success'):
        inflow = sf.get('inflow') or []
        outflow = sf.get('outflow') or []
        in_top = []
        for it in inflow[:5]:
            v = _parse_yi(it.get('main_net'))
            if v is None:
                continue
            in_top.append({'name': it.get('name', ''), 'val': v})
        out_top = []
        for it in outflow[:5]:
            v = _parse_yi(it.get('main_net'))
            if v is None:
                continue
            out_top.append({'name': it.get('name', ''), 'val': v})
        if in_top or out_top:
            result['sector'] = {'in_top': in_top, 'out_top': out_top}
            in_text = '、'.join(f'{x["name"]}{x["val"]:+.1f}亿' for x in in_top[:3]) or '无'
            out_text = '、'.join(f'{x["name"]}{x["val"]:+.1f}亿' for x in out_top[:3]) or '无'
            parts.append(f'行业主力净流入居前：{in_text}；净流出居前：{out_text}。')

    if not result:
        return None
    return dict(result, day=day.strftime('%Y-%m-%d'), conclusion=' '.join(parts))


# ==================== 复盘总结 + 次日预案 ====================

def _build_plan(synergy, breadth, turnover, sentiment, funds):
    """复盘总结 + 次日预案：数据交叉验证判断市场真实状态，制定次日观察清单与关键信号。
    核心：数据之间的背离才是最有价值的信号（如指数涨但涨跌比<1、缩量、炸板率高等）。"""
    divergences = []

    mode = synergy['mode'] if synergy else None
    up_names = synergy['up'] if synergy else []
    down_names = synergy['down'] if synergy else []
    red_ratio = breadth['red_ratio'] if breadth else None
    band = turnover['band'] if turnover else None
    zt_clean = sentiment['zt_clean'] if sentiment else 0
    dt_clean = sentiment['dt_clean'] if sentiment else 0
    gaps = sentiment['gaps'] if sentiment else []

    bull = bool(up_names) and not down_names
    bear = bool(down_names) and not up_names
    split = bool(up_names) and bool(down_names)

    # 背离信号：数据之间的背离才是最有价值的信号
    if bull and red_ratio is not None and red_ratio < 45:
        divergences.append(f'指数普涨但红盘率仅 {red_ratio:.0f}%，权重护盘、个股普跌，属典型"假涨"，次日追高易被套。')
    if bull and band == '偏低':
        divergences.append('指数上涨但量能低于近期均量，属"缩量虚涨"，缺增量配合，持续性存疑。')
    if bear and red_ratio is not None and red_ratio >= 50:
        divergences.append(f'指数普跌但红盘率仍有 {red_ratio:.0f}%，个股强于指数，资金弃权重抱题材，结构性机会仍在。')
    if bear and band == '活跃':
        divergences.append('指数下跌但量能高于近期均量，属"放量下跌"，抛压沉重，次日谨防惯性低开。')
    if zt_clean >= 35 and gaps:
        divergences.append(f'涨停 {zt_clean} 家但连板梯队断层（{"/".join(map(str, gaps))}板空缺），情绪亢奋与接力不足并存，谨防高度压制。')
    if zt_clean >= 35 and dt_clean >= 10:
        divergences.append(f'涨停 {zt_clean} 家、跌停 {dt_clean} 家并存，多空分歧巨大，属典型分歧市，宜快进快出。')
    if red_ratio is not None and red_ratio >= 55 and dt_clean >= 10:
        divergences.append(f'红盘率 {red_ratio:.0f}% 却仍有 {dt_clean} 家跌停，赚钱与亏钱效应并存，结构严重分化。')

    # 观察清单：主线板块 / 回避板块 / 风向标个股
    sector = (funds or {}).get('sector')
    watch_sectors = [x['name'] for x in (sector.get('in_top') or [])[:3]] if sector else []
    avoid_sectors = [x['name'] for x in (sector.get('out_top') or [])[:3]] if sector else []
    leaders = sentiment['leaders'] if sentiment else []

    # 次日关键信号
    attack = []
    if dt_clean >= 10:
        attack.append('开盘30分钟跌停家数收敛至10家以内')
    attack.append('红盘率回升至50%以上且不再走低')
    if leaders:
        attack.append('风向标高标（' + '、'.join(l['name'] for l in leaders[:3]) + '）不被核按钮')
    if band == '偏低':
        attack.append('量能不再萎缩（最好温和放大）')
    attack_text = ('、'.join(attack) + '，可考虑轻仓试错参与；否则继续观望。') if attack else '暂缺明确进攻信号，等待放量企稳确认。'

    watch = []
    if dt_clean >= 10:
        watch.append('开盘跌停家数快速扩散（>10家）')
    if leaders:
        watch.append('连板高标批量断板或炸板')
    watch.append('红盘率持续走低')
    watch.append('量能继续萎缩')
    watch_text = '、'.join(watch) + '，则观望为主、严控仓位。'

    # 市场状态一句话
    if bull and red_ratio is not None and red_ratio >= 55:
        state = '普涨且赚钱效应较好，市场处于进攻区间，次日关注量能能否延续。'
    elif bull:
        state = '指数普涨但个股/量能配合一般，需警惕假涨，次日不宜盲目追高。'
    elif bear:
        state = '指数普跌、情绪偏弱，次日重点观察能否止跌企稳，不宜逆势抄底。'
    elif split:
        state = '指数分化、结构行情，重个股轻指数，围绕主线板块博弈。'
    else:
        state = '方向不明、多空平衡，等待放量选择方向，以观望为主。'

    return {
        'state': state,
        'divergences': divergences,
        'watch_sectors': watch_sectors,
        'avoid_sectors': avoid_sectors,
        'leaders': leaders,
        'attack': attack_text,
        'watch': watch_text,
    }


# ==================== 主入口 ====================

def run_review():
    """执行一次自助复盘，返回结构化数据与逐项分析结论"""
    try:
        target_day = _target_trade_day()
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
        try:
            recent_turnover = _fetch_recent_turnover()
        except Exception as e:
            print(f'[self-review] recent_turnover 获取失败: {e}')
            recent_turnover = []
        turnover_analysis = _analyze_turnover(turnover, recent_turnover, indices)

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

        # 补充维度：单源取数，失败/无数据则置空，不影响核心复盘结果
        try:
            open_hour_analysis = _analyze_open_hour(target_day)
        except Exception as e:
            print(f'[self-review] open_hour 分析失败: {e}')
            open_hour_analysis = None
        try:
            sentiment_analysis = _analyze_sentiment(target_day)
        except Exception as e:
            print(f'[self-review] sentiment 分析失败: {e}')
            sentiment_analysis = None
        try:
            funds_analysis = _analyze_funds(target_day)
        except Exception as e:
            print(f'[self-review] funds 分析失败: {e}')
            funds_analysis = None

        plan = _build_plan(synergy, breadth, turnover_analysis, sentiment_analysis, funds_analysis)

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
                'day': target_day.strftime('%Y-%m-%d'),
                'indices': indices,
                'breadth': breadth,
                'turnover': turnover_analysis,
                'open_hour': open_hour_analysis,
                'minute': minute_analysis,
                'synergy': synergy,
                'levels': levels,
                'sentiment': sentiment_analysis,
                'funds': funds_analysis,
                'plan': plan,
            },
        }
    except Exception as e:
        return {'success': False, 'error': f'复盘失败: {e}'}


def run_stock_review(user_id):
    """自选复盘：自选股/场内ETF/持仓股 关键点位分析（复用指数复盘逻辑）"""
    from watchlist.service import get_all, etf_get_all, holdings_get_all
    wl = get_all(user_id)
    etf = etf_get_all(user_id)
    hold = holdings_get_all(user_id)

    groups = [
        ('watchlist', '自选股', [{'code': r[0], 'market': r[1]} for r in wl]),
        ('etf', '场内ETF', [{'code': r[0], 'market': r[1]} for r in etf]),
        ('holdings', '持仓股', [{'code': r[0], 'market': r[1]} for r in hold]),
    ]

    data = {}
    summary = {'pressure': [], 'support': []}
    try:
        for key, label, stocks in groups:
            items = _analyze_stocks(stocks)  # 小数位逐标的按 is_etf 判断，与分组无关
            data[key] = {'label': label, 'items': items}
            for it in items:
                if it.get('near') == 'pressure':
                    summary['pressure'].append({
                        'name': it['name'], 'group': label, 'price': it['price'],
                        'hint': it['hint'], 'code': it['code'], 'market': it['market'],
                    })
                elif it.get('near') == 'support':
                    summary['support'].append({
                        'name': it['name'], 'group': label, 'price': it['price'],
                        'hint': it['hint'], 'code': it['code'], 'market': it['market'],
                    })
    except Exception:
        # 行情/日K源等内部异常：显式报错（success:false + 具体原因）而不是让 Flask
        # 返回 HTML 500 错误页；完整 traceback 保留在服务端控制台便于定位
        traceback.print_exc()
        return {'success': False, 'error': '自选复盘执行失败，请查看服务端控制台详细日志'}

    now = datetime.datetime.now()
    return {
        'success': True,
        'data': {
            'update_time': now.strftime('%Y-%m-%d %H:%M:%S'),
            'day': _target_trade_day().strftime('%Y-%m-%d'),
            'groups': data,
            'summary': summary,
        },
    }
