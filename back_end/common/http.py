"""统一数据源请求层（所有外部 HTTP 请求的唯一入口）

分层：
1. 请求原语：get_response / get_text / get_json / get_jsonp
   - 统一走 common.HTTP_SESSION（连接池复用、禁用系统代理）
   - 单一职责：成功返回数据；失败直接抛 HttpError 或底层异常，不做多源兜底
2. 各数据源标准请求头：HEADERS_*（换源/调整伪装只需改这里）
3. 固定字段名的数据接口：get_realtime_quotes_ulist / get_ths_klines / get_sina_klines /
   get_em_kline / get_em_trends / get_em_trade_details / get_em_stock_fields /
   get_etf_nav / get_sina_hq / get_tx_kline / get_yahoo_chart / em_datacenter_get
   - 返回字段名在本文件内固定为统一契约；换数据源时只改这里的请求和解析，
     业务代码（路由/服务层）不需要跟着改字段名
"""
import datetime
import json
import os
import re
import threading

from . import HTTP_SESSION, BROWSER_HEADERS

# ==================== 异常 ====================


class HttpError(Exception):
    """HTTP 请求失败（非 200 / 响应格式异常）"""


# ==================== 请求头（各数据源标准伪装头） ====================

_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'

HEADERS_SINA = {**BROWSER_HEADERS, 'Referer': 'https://finance.sina.com.cn/'}
HEADERS_EM_DATA = {'User-Agent': _UA, 'Referer': 'https://data.eastmoney.com/'}
HEADERS_EM_QUOTE = {'User-Agent': _UA, 'Referer': 'https://quote.eastmoney.com/'}
HEADERS_EM_F10 = {'User-Agent': _UA, 'Referer': 'https://emweb.eastmoney.com/'}
HEADERS_EM_FUND = {'User-Agent': _UA, 'Referer': 'https://fundf10.eastmoney.com/'}
HEADERS_THS = {'User-Agent': _UA, 'Referer': 'https://www.10jqka.com.cn/'}
HEADERS_THS_LONGHU = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    'Referer': 'https://data.10jqka.com.cn/market/longhu/',
}
HEADERS_TX = {'User-Agent': _UA, 'Referer': 'https://finance.qq.com/'}
HEADERS_YAHOO = {'User-Agent': _UA}

# 东财通用 token
EM_UT = 'bd1d9ddb04089700cf9c27f6f7426281'


# ==================== 请求原语 ====================


def get_response(url, params=None, headers=None, timeout=10):
    """GET → requests.Response（需要自判 status_code / 二进制内容时用）"""
    return HTTP_SESSION.get(url, params=params, headers=headers, timeout=timeout)


def get_text(url, params=None, headers=None, timeout=10, encoding=None):
    """GET → 响应文本；非 200 抛 HttpError"""
    r = get_response(url, params=params, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise HttpError(f'HTTP {r.status_code}: {url}')
    if encoding:
        r.encoding = encoding
    return r.text


def get_json(url, params=None, headers=None, timeout=10):
    """GET → 解析后的 JSON；非 200 抛 HttpError，坏 JSON 抛 ValueError"""
    r = get_response(url, params=params, headers=headers, timeout=timeout)
    if r.status_code != 200:
        raise HttpError(f'HTTP {r.status_code}: {url}')
    return r.json()


def get_jsonp(url, params=None, headers=None, timeout=10):
    """GET → 去掉 jQuery 回调包裹后的 JSON"""
    text = get_text(url, params=params, headers=headers, timeout=timeout)
    return json.loads(re.sub(r'^[^(]*\(|\)$', '', text.strip()))


# ==================== 通用解析 ====================


def _num(v):
    """数值字段转 float；None / '' / '-' 返回 None"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s == '-':
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ==================== 固定字段名的数据接口 ====================
#
# 以下每个接口的返回字段名即对外契约，业务代码只消费这些字段；
# 换数据源时只改本节内的 URL / 参数 / 解析逻辑。


# ---- 实时行情（东方财富 ulist）----

_EM_ULIST_URL = 'https://push2delay.eastmoney.com/api/qt/ulist.np/get'
_ULIST_FIELDS = ('f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f15,f16,f17,f18,'
                 'f20,f21,f23,f38,f39,f100,f104,f105,f106,f115')


def get_realtime_quotes_ulist(secids):
    """批量实时行情（东财 ulist）→ {secid: 行情dict}（数值型，展示格式化由调用方做）。

    行情dict 固定字段（全部为 float|None，除 code/market/name/industry 外）：
      code, market, name, price, pct, change, volume, amount, amplitude, turnover,
      pe, pb, high, low, open, pre_close, total_cap, float_cap, total_shares,
      float_shares, industry, rise, fall, flat
    rise/fall/flat（涨/跌/平家数）仅指数有意义。无数据的 secid 不在返回中。
    """
    params = {'fltt': 2, 'invt': 2, 'fields': _ULIST_FIELDS,
              'secids': secids, 'ut': EM_UT}
    body = get_json(_EM_ULIST_URL, params=params, headers=HEADERS_EM_DATA, timeout=8)
    diff = (body.get('data') or {}).get('diff') or []
    result = {}
    for row in diff:
        code = str(row.get('f12') or '').strip()
        mkt = row.get('f13')
        if not code or mkt is None or str(mkt) == '':
            continue
        result[f"{mkt}.{code}"] = {
            'code': code,                          # 股票代码（f12）
            'market': str(mkt),                    # 市场标识（f13：0深/1沪/2北/90板块/116港/105-107美）
            'name': str(row.get('f14') or ''),     # 名称（f14）
            'price': _num(row.get('f2')),          # 最新价（f2，元）
            'pct': _num(row.get('f3')),            # 涨跌幅（f3，%）
            'change': _num(row.get('f4')),         # 涨跌额（f4，元）
            'volume': _num(row.get('f5')),         # 成交量（f5，手）
            'amount': _num(row.get('f6')),         # 成交额（f6，元）
            'amplitude': _num(row.get('f7')),      # 振幅（f7，%）
            'turnover': _num(row.get('f8')),       # 换手率（f8，%）
            'pe': _num(row.get('f115')),           # 市盈率TTM（f115）
            'pb': _num(row.get('f23')),            # 市净率（f23）
            'high': _num(row.get('f15')),          # 最高价（f15，元）
            'low': _num(row.get('f16')),           # 最低价（f16，元）
            'open': _num(row.get('f17')),          # 今开（f17，元）
            'pre_close': _num(row.get('f18')),     # 昨收（f18，元）
            'total_cap': _num(row.get('f20')),     # 总市值（f20，元）
            'float_cap': _num(row.get('f21')),     # 流通市值（f21，元）
            'total_shares': _num(row.get('f38')),  # 总股本（f38，股）
            'float_shares': _num(row.get('f39')),  # 流通股本（f39，股）
            'industry': str(row.get('f100') or '').replace('、', '·'),  # 所属行业（f100）
            'rise': _num(row.get('f104')),         # 上涨家数（f104，仅指数）
            'fall': _num(row.get('f105')),         # 下跌家数（f105，仅指数）
            'flat': _num(row.get('f106')),         # 平盘家数（f106，仅指数）
        }
    return result


# ---- 实时行情：腾讯 qt.gtimg.cn / 新浪 hq.sinajs.cn ----
# 契约同 get_realtime_quotes_ulist（23 字段），业务侧换源时只需改调用的函数名。

_TX_GTIMG_PREFIX = {'1': 'sh', '0': 'sz', '2': 'bj', '90': 'sz',
                    '116': 'hk', '105': 'us', '106': 'us', '107': 'us'}
_SINA_HQ_PREFIX = {'1': 'sh', '0': 'sz', '2': 'bj', '90': 'sz'}


def _secids_to_codes(secids, prefix_map):
    """东财 secids（market.code）→ {源原生code: secid}。"""
    mapping = {}
    for s in secids.split(','):
        s = s.strip()
        if '.' not in s:
            continue
        mkt, code = s.split('.', 1)
        prefix = prefix_map.get(mkt)
        if not prefix:
            continue
        if mkt == '116':  # 港股代码补零到 5 位
            code = code.zfill(5)
        elif mkt in ('105', '106', '107'):  # 美股：新浪 gb_ 小写，腾讯 us 大写
            code = code.lower() if prefix.startswith('gb') else code.upper()
        mapping[f'{prefix}{code}'] = s
    return mapping


def get_realtime_quotes_gtimg(secids):
    """批量实时行情（腾讯 qt.gtimg.cn）→ {secid: 行情dict}，字段契约同 get_realtime_quotes_ulist。

    腾讯无 industry / rise / fall / flat / total_shares / float_shares，这些字段为 None / ''。
    单位对齐东财：volume 手、amount 万元→元、total_cap/float_cap 亿元→元。
    """
    mapping = _secids_to_codes(secids, _TX_GTIMG_PREFIX)
    if not mapping:
        return {}
    text = get_text('https://qt.gtimg.cn/q=' + ','.join(mapping),
                    headers=HEADERS_TX, timeout=8, encoding='gbk')
    result = {}
    for line in text.strip().split('\n'):
        if '="' not in line:
            continue
        gt_code = line.split('="')[0].split('v_')[-1].strip()
        secid = mapping.get(gt_code)
        if not secid:
            continue
        parts = line.split('="')[1].rstrip('";').split('~')
        if len(parts) < 6:
            continue

        def _g(i):
            return _num(parts[i]) if i < len(parts) else None

        amount = _g(37)        # 成交额（万元）
        float_cap = _g(44)     # 流通市值（亿元）
        total_cap = _g(45)     # 总市值（亿元）
        result[secid] = {
            'code': parts[2] or secid.split('.', 1)[1],  # 股票代码（~2）
            'market': secid.split('.', 1)[0],            # 市场标识（f13 转来）
            'name': parts[1],                            # 名称（~1）
            'price': _g(3),                              # 最新价（~3，元）
            'pct': _g(32),                               # 涨跌幅（~32，%）
            'change': _g(31),                            # 涨跌额（~31，元）
            'volume': _g(6),                             # 成交量（~6，手）
            'amount': amount * 1e4 if amount is not None else None,  # 成交额（~37，万元→元）
            'amplitude': _g(43),                         # 振幅（~43，%）
            'turnover': _g(38),                          # 换手率（~38，%）
            'pe': _g(39),                                # 市盈率TTM（~39）
            'pb': _g(46),                                # 市净率（~46）
            'high': _g(33),                              # 最高价（~33，元）
            'low': _g(34),                               # 最低价（~34，元）
            'open': _g(5),                               # 今开（~5，元）
            'pre_close': _g(4),                          # 昨收（~4，元）
            'total_cap': total_cap * 1e8 if total_cap is not None else None,  # 总市值（~45，亿元→元）
            'float_cap': float_cap * 1e8 if float_cap is not None else None,  # 流通市值（~44，亿元→元）
            'total_shares': None,                        # 总股本（腾讯无）
            'float_shares': None,                        # 流通股本（腾讯无）
            'industry': '',                              # 所属行业（腾讯无）
            'rise': None,                                # 上涨家数（腾讯无）
            'fall': None,                                # 下跌家数（腾讯无）
            'flat': None,                                # 平盘家数（腾讯无）
        }
    return result


def get_realtime_quotes_sina(secids):
    """批量实时行情（新浪 hq.sinajs.cn）→ {secid: 行情dict}，字段契约同 get_realtime_quotes_ulist。

    仅支持 A 股（沪/深/北/板块）。新浪仅有名称/今开/昨收/现价/最高/最低/量/额，
    涨跌额与涨跌幅由现价-昨收自算；振幅/换手/市盈率/市净率/市值/股本/行业/涨跌家数为 None / ''。
    单位对齐东财：volume 股→手，amount 为元。
    """
    mapping = _secids_to_codes(secids, _SINA_HQ_PREFIX)
    if not mapping:
        return {}
    hq = get_sina_hq(list(mapping))
    result = {}
    for sina_code, payload in hq.items():
        secid = mapping.get(sina_code)
        if not secid:
            continue
        parts = payload.split(',')
        if len(parts) < 6:
            continue
        price = _num(parts[3])
        pre_close = _num(parts[2])
        change = round(price - pre_close, 2) if (price is not None and pre_close) else None
        pct = round((price - pre_close) / pre_close * 100, 2) if (price is not None and pre_close) else None
        volume = _num(parts[8]) if len(parts) > 8 else None
        result[secid] = {
            'code': secid.split('.', 1)[1],              # 股票代码
            'market': secid.split('.', 1)[0],            # 市场标识（f13 转来）
            'name': parts[0],                            # 名称（idx0）
            'price': price,                              # 最新价（idx3，元）
            'pct': pct,                                  # 涨跌幅（现价-昨收，%）
            'change': change,                            # 涨跌额（现价-昨收，元）
            'volume': volume / 100 if volume is not None else None,  # 成交量（idx8，股→手）
            'amount': _num(parts[9]) if len(parts) > 9 else None,    # 成交额（idx9，元）
            'amplitude': None,                           # 振幅（新浪无）
            'turnover': None,                            # 换手率（新浪无）
            'pe': None,                                  # 市盈率TTM（新浪无）
            'pb': None,                                  # 市净率（新浪无）
            'high': _num(parts[4]),                      # 最高价（idx4，元）
            'low': _num(parts[5]),                       # 最低价（idx5，元）
            'open': _num(parts[1]),                      # 今开（idx1，元）
            'pre_close': pre_close,                      # 昨收（idx2，元）
            'total_cap': None,                           # 总市值（新浪无）
            'float_cap': None,                           # 流通市值（新浪无）
            'total_shares': None,                        # 总股本（新浪无）
            'float_shares': None,                        # 流通股本（新浪无）
            'industry': '',                              # 所属行业（新浪无）
            'rise': None,                                # 上涨家数（新浪无）
            'fall': None,                                # 下跌家数（新浪无）
            'flat': None,                                # 平盘家数（新浪无）
        }
    return result


# ---- 同花顺 v4 年K线 ----

_THS_KLINE_URL = 'https://d.10jqka.com.cn/v4/line/{symbol}/{period_code}/{year}.js'
_THS_PERIOD = {'day': '01', 'week': '11', 'month': '21'}


def _parse_ths_raw(raw):
    """同花顺年文件 raw → [{date, open, high, low, close, volume, amount, turnover}]"""
    rows = []
    seen = set()
    for line in raw.split(';'):
        parts = line.split(',')
        if len(parts) < 5:
            continue
        date = parts[0]
        if not date or date in seen:
            continue
        seen.add(date)
        close = _num(parts[4])
        if close is None or close <= 0:
            continue
        o = _num(parts[1]) if len(parts) > 1 else None
        h = _num(parts[2]) if len(parts) > 2 else None
        l = _num(parts[3]) if len(parts) > 3 else None
        # 同花顺部分行只给收盘价（如指数盘中当日行），开/高/低缺失或为0时用收盘价补齐
        if o is None or o <= 0:
            o = close
        if h is None or h <= 0:
            h = close
        if l is None or l <= 0:
            l = close
        volume = _num(parts[5]) if len(parts) > 5 else None
        amount = _num(parts[6]) if len(parts) > 6 else None
        turnover = _num(parts[7]) if len(parts) > 7 else None
        rows.append({
            'date': date,  # YYYYMMDD
            'open': o,
            'high': h,
            'low': l,
            'close': close,
            'volume': volume or 0.0,
            'amount': amount or 0.0,
            'turnover': round(turnover, 2) if turnover is not None else 0.0,
        })
    return rows


def get_ths_klines(symbol, period='day', year=None, retries=3):
    """同花顺 v4 年K线文件 → [K线row]（固定字段见 _parse_ths_raw）。

    symbol 形如 sh_600519 / sz_399001 / sh_1A0001（指数）。
    period: day / week / month。
    返回 None 表示请求失败（同源重试耗尽）；404 或空文件 → []（该年无数据）。
    """
    period_code = _THS_PERIOD.get(period)
    if period_code is None:
        raise ValueError(f'不支持的K线周期: {period}')
    if year is None:
        year = datetime.datetime.now().year
    url = _THS_KLINE_URL.format(symbol=symbol, period_code=period_code, year=year)
    import time as _time
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = get_response(url, headers=HEADERS_THS, timeout=10)
            if r.status_code == 404:
                return []
            if r.status_code == 200:
                text = r.text
                s, e = text.find('(') + 1, text.rfind(')')
                if s > 0 and e > s:
                    return _parse_ths_raw(json.loads(text[s:e]).get('data', ''))
                last_err = '响应格式异常'
            else:
                last_err = f'HTTP {r.status_code}'
        except Exception as ex:
            last_err = str(ex)
        if attempt < retries:
            _time.sleep(0.3)
    raise RuntimeError(f'同花顺年K线拉取失败（已重试{retries}次）: {symbol} {year}年 {period}: {last_err}')


# ---- 新浪K线（分钟/日/周/月）----

_SINA_KLINE_URL = ('https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/'
                   'CN_MarketData.getKLineData?symbol={symbol}&scale={scale}&ma=no&datalen={datalen}')


def get_sina_klines(symbol, scale, datalen):
    """新浪K线 → [{datetime, open, high, low, close, volume}]（volume 为 float，单位随市场）。

    scale 为分钟数（5/15/30/60）或 240(日)/1200(周)/6000(月)；无数据返回 []。
    """
    url = _SINA_KLINE_URL.format(symbol=symbol, scale=scale, datalen=datalen)
    body = get_json(url, headers=HEADERS_SINA, timeout=15)
    if not isinstance(body, list):
        return []
    rows = []
    for bar in body:
        dt = bar.get('day', '')
        if not dt:
            continue
        rows.append({
            'datetime': dt,
            'open': float(bar.get('open') or 0),
            'high': float(bar.get('high') or 0),
            'low': float(bar.get('low') or 0),
            'close': float(bar.get('close') or 0),
            'volume': float(bar.get('volume') or 0),
        })
    return rows


# ---- 新浪 hq 实时行情（原始文本协议）----


def get_sina_hq(codes):
    """新浪 hq 实时行情 → {code: 逗号分隔原始字段串}（gbk 解码）。

    codes 为列表或单个代码（如 'sh600519' / 'hf_XAU'）；无数据的 code 不在返回中。
    各标的字段顺序不同（股票/外汇/商品），由调用方按标的类型解析。
    """
    if isinstance(codes, str):
        codes = [codes]
    text = get_text('https://hq.sinajs.cn/list=' + ','.join(codes),
                    headers=HEADERS_SINA, timeout=10, encoding='gbk')
    result = {}
    for line in text.strip().split('\n'):
        if '="' not in line:
            continue
        left, _, right = line.partition('="')
        payload = right.rstrip('";').rstrip('";\r')
        if not payload:
            continue
        code = left.split('hq_str_')[-1].strip()
        if code:
            result[code] = payload
    return result


# ---- 东方财富 分时 / 分钟K线 / 逐笔 / 单标的字段 ----


def get_em_trends(secid):
    """东财 trends2 单日分时 → {name, pre_close, points}。

    points 固定字段：time(HH:MM), full_time(原始含日期), price, volume, amount（分钟增量）。
    """
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
        'ndays': 1,
    }
    body = get_json('https://push2delay.eastmoney.com/api/qt/stock/trends2/get',
                    params=params, headers=HEADERS_EM_QUOTE, timeout=10)
    d = body.get('data') or {}
    points = []
    for t in d.get('trends') or []:
        parts = t.split(',')
        if len(parts) < 2:
            continue
        full_tm = parts[0]
        tm = full_tm.split(' ')[-1] if ' ' in full_tm else full_tm
        points.append({
            'time': tm,
            'full_time': full_tm,
            'price': float(parts[1]),
            'volume': float(parts[5]) if len(parts) > 5 and parts[5] else 0.0,
            'amount': float(parts[6]) if len(parts) > 6 and parts[6] else 0.0,
        })
    return {'name': str(d.get('name') or ''), 'pre_close': d.get('preClose', 0), 'points': points}


def get_em_kline(secid, klt, lmt=240):
    """东财分钟K线 → [{datetime, open, high, low, close, volume, amount, turnover}]。

    klt 为分钟数（1/5/15/30/60）；volume 已乘100转为股。无数据返回 []。
    """
    params = {
        'secid': secid, 'klt': str(klt), 'fqt': '1',
        'beg': '0', 'end': '20500101', 'lmt': str(lmt),
        'fields1': 'f1,f2,f3,f4,f5,f6',
        'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
    }
    body = get_json('https://push2delay.eastmoney.com/api/qt/stock/kline/get',
                    params=params, headers=HEADERS_EM_QUOTE, timeout=10)
    klines = (body.get('data') or {}).get('klines') or []
    rows = []
    for line in klines:
        parts = line.split(',')
        if len(parts) < 6:
            continue
        c = float(parts[2]) if parts[2] else 0
        if c <= 0:
            continue
        o = float(parts[1]) if parts[1] else 0
        h = float(parts[3]) if parts[3] else 0
        l = float(parts[4]) if parts[4] else 0
        if o <= 0: o = c
        if h <= 0: h = c
        if l <= 0: l = c
        rows.append({
            'datetime': parts[0],
            'open': o, 'close': c, 'high': h, 'low': l,
            'volume': int(float(parts[5]) if parts[5] else 0) * 100,
            'amount': float(parts[6]) if len(parts) > 6 and parts[6] else 0.0,
            'turnover': round(float(parts[10]) if len(parts) > 10 and parts[10] else 0, 2),
        })
    return rows


def get_em_trade_details(secid):
    """东财逐笔成交 → [{time, price, volume, side}]（side: 1买 2卖 0中性）"""
    params = {
        'secid': secid,
        'fields1': 'f1,f2,f3,f4',
        'fields2': 'f51,f52,f53,f54,f55',
        'pos': '-0',
        'wbp2u': '|0|0|0|web',
        'ut': EM_UT,
    }
    body = get_json('https://push2delay.eastmoney.com/api/qt/stock/details/get',
                    params=params, headers=HEADERS_EM_DATA, timeout=8)
    details = (body.get('data') or {}).get('details') or []
    trades = []
    for item in details:
        parts = item.split(',')
        if len(parts) < 5:
            continue
        side = int(parts[4]) if parts[4].isdigit() else 0
        trades.append({
            'time': parts[0],
            'price': float(parts[1]),
            'volume': int(float(parts[2])),
            'side': side,
        })
    return trades


def get_em_stock_fields(secid, fields):
    """东财 stock/get 指定原始字段 → {字段名: 原始值}（f50 量比 / f191 委比 等）"""
    params = {'secid': secid, 'fields': fields, 'ut': EM_UT}
    body = get_json('https://push2delay.eastmoney.com/api/qt/stock/get',
                    params=params, headers=HEADERS_EM_DATA, timeout=8)
    return body.get('data') or {}


# ---- 东方财富 F10 / 基金 ----


def get_etf_nav(fund_code):
    """东财基金最新单位净值 → float；无数据返回 None"""
    body = get_jsonp('https://api.fund.eastmoney.com/f10/lsjz',
                     params={'callback': 'jQuery', 'fundCode': fund_code,
                             'pageIndex': 1, 'pageSize': 1},
                     headers=HEADERS_EM_FUND, timeout=5)
    nav_list = (body.get('Data') or {}).get('LSJZList') or []
    if nav_list:
        return float(nav_list[0]['DWJZ'])
    return None


def em_datacenter_get(report_name, columns, filter_=None, page_size=500,
                      page_number=1, sort_columns=None, sort_types='-1'):
    """东财 datacenter 报表接口 → 行列表（行内为接口原始列名）"""
    params = {
        'reportName': report_name,
        'columns': columns,
        'pageSize': page_size,
        'pageNumber': page_number,
    }
    if filter_ is not None:
        params['filter'] = filter_
    if sort_columns:
        params['sortColumns'] = sort_columns
        params['sortTypes'] = sort_types
    body = get_json('https://datacenter-web.eastmoney.com/api/data/v1/get',
                    params=params, headers=HEADERS_EM_DATA, timeout=15)
    return (body.get('result') or {}).get('data') or []


# ---- 腾讯日K ----


def get_tx_kline(symbol, count, fq='qfq'):
    """腾讯日K → {name, rows: [{date, open, close, high, low, volume}]}（按日期升序）。

    symbol 如 sh000001 / sz399001 / sz000001。
    """
    body = get_json('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get',
                    params={'param': f'{symbol},day,,,{count},{fq}'},
                    headers=HEADERS_TX, timeout=10)
    d = (body.get('data') or {}).get(symbol, {})
    klines = d.get('qfqday') or d.get('day') or []
    name = ''
    qt_row = (d.get('qt') or {}).get(symbol)
    if isinstance(qt_row, list) and len(qt_row) > 1:
        name = str(qt_row[1] or '')
    rows = []
    for k in klines:
        if len(k) < 6:
            continue
        rows.append({
            'date': k[0],
            'open': float(k[1]),
            'close': float(k[2]),
            'high': float(k[3]),
            'low': float(k[4]),
            'volume': float(k[5]),
        })
    return {'name': name, 'rows': rows}


# ---- Yahoo Finance ----

_yahoo_env_lock = threading.Lock()


def get_yahoo_chart(symbol, range_, interval):
    """Yahoo chart 接口 → {timestamps, open, high, low, close, volume} 或 None（无数据）。

    Yahoo 直连受限，common/__init__ 已全局禁用代理；请求期间临时恢复 no_proxy
    环境变量，走系统代理（与原各调用点的处理一致）。非 200（非404）抛 HttpError。
    """
    url = f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
    with _yahoo_env_lock:
        old_no = os.environ.pop('no_proxy', None)
        old_NO = os.environ.pop('NO_PROXY', None)
        try:
            r = get_response(url, params={'range': range_, 'interval': interval},
                             headers=HEADERS_YAHOO, timeout=15)
        finally:
            if old_no is not None:
                os.environ['no_proxy'] = old_no
            if old_NO is not None:
                os.environ['NO_PROXY'] = old_NO
    if r.status_code == 404:
        return None
    if r.status_code != 200:
        raise HttpError(f'Yahoo HTTP {r.status_code}: {url}')
    results = (r.json().get('chart', {}) or {}).get('result') or []
    result = results[0] if results else None
    if not result:
        return None
    quotes = (result.get('indicators', {}).get('quote') or [None])[0]
    timestamps = result.get('timestamp') or []
    if not quotes or not timestamps:
        return None
    return {
        'timestamps': timestamps,
        'open': quotes.get('open') or [],
        'high': quotes.get('high') or [],
        'low': quotes.get('low') or [],
        'close': quotes.get('close') or [],
        'volume': quotes.get('volume') or [],
    }
