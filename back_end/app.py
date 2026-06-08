"""鑫多多 - 股票行情仪表盘"""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests

from common import REQUEST_PROXIES
from common.utils import is_etf, fmt, fmt_pct, fmt_volume, fmt_amount, fmt_cap
from common.finance import get_goodwill
from money_flow.market import get_major_indices, get_sh000001_minute_data, get_index_minute_data
from money_flow.fund_flow import get_market_fund_flow
from money_flow.fear_index import get_fear_index
from money_flow.risk_index import get_risk_index
from money_flow.margin import get_margin_trading
from money_flow.storage import start_major_indices_poller
from stock_pick.service import search_stock as do_search
from watchlist.service import get_all, add, remove as wl_remove
import logging
logger = logging.getLogger(__name__)
from technical_screen.service import run_ascending_channel_async, get_scan_status

import sys as _sys, os as _os
if getattr(_sys, 'frozen', False):
    # PyInstaller exe 模式
    base = _sys._MEIPASS
    app = Flask(__name__, template_folder=_os.path.join(base, 'front_end', 'templates'), static_folder=_os.path.join(base, 'front_end', 'static'))
else:
    app = Flask(__name__, template_folder='../front_end/templates', static_folder='../front_end/static')
CORS(app)


# ==================== 页面 ====================

@app.route('/')
def index():
    return render_template('index.html')


# ==================== 行情数据 ====================

@app.route('/api/major-indices')
def major_indices():
    return jsonify(get_major_indices())

@app.route('/api/sh000001-minute')
def sh000001_minute():
    return jsonify(get_sh000001_minute_data())


# ==================== 成交额 ====================

@app.route('/api/index-minute')
def index_minute():
    return jsonify(get_index_minute_data())

@app.route('/api/turnover-minute')
def turnover_minute():
    return jsonify(get_index_minute_data())


# ==================== 资金流 & 指数 ====================

@app.route('/api/market-fund-flow')
def market_fund_flow():
    return jsonify(get_market_fund_flow())

@app.route('/api/fear-index')
def fear_index():
    return jsonify(get_fear_index())

@app.route('/api/risk-index')
def risk_index():
    return jsonify(get_risk_index())

@app.route('/api/margin-trading')
def margin_trading():
    return jsonify(get_margin_trading())


# ==================== 搜索 ====================

@app.route('/api/goodwill')
def goodwill():
    codes = request.args.get('codes', '').split(',')
    codes = [c.strip() for c in codes if c.strip()]
    if not codes:
        return jsonify({'success': False, 'data': {}})
    return jsonify({'success': True, 'data': get_goodwill(codes)})

@app.route('/api/search-stock')
def search_stock():
    return jsonify(do_search(request.args.get('q', '')))


# ==================== 自选股 ====================

@app.route('/api/watchlist', methods=['GET'])
def watchlist_get():
    rows = get_all()
    return jsonify({'success': True, 'data': [{'code': r[0], 'market': r[1], 'created_at': r[2], 'added_price': r[3]} for r in rows]})

@app.route('/api/watchlist', methods=['POST'])
def watchlist_add():
    code = request.form.get('code', '').strip()
    market = request.form.get('market', '').strip()
    added_price = request.form.get('added_price', '').strip()
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    add(code, market, added_price)
    return jsonify({'success': True})

@app.route('/api/watchlist/<code>', methods=['DELETE'])
def watchlist_remove(code):
    market = request.args.get('market', '')
    if not market:
        return jsonify({'success': False, 'error': '缺少 market 参数'})
    wl_remove(code, market)
    return jsonify({'success': True})

@app.route('/api/stock-quotes')
def stock_quotes():
    """批量获取股票实时行情"""
    secids = request.args.get('secids', '')
    if not secids:
        return jsonify({'success': False, 'data': {}})
    try:
        url = "https://push2delay.eastmoney.com/api/qt/ulist.np/get"
        params = {
            'fltt': 2, 'invt': 2,
            # f115=市盈率TTM(滚动市盈率), f15=最高, f16=最低, f17=今开, f18=昨收, f38=总股本, f39=流通股本
            'fields': 'f2,f3,f4,f5,f6,f7,f8,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f38,f39,f100,f115',
            'secids': secids,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/',
        }
        r = requests.get(url, params=params, headers=headers, timeout=8, proxies=REQUEST_PROXIES)
        diff = (r.json().get('data') or {}).get('diff') or []
        result = {}
        for row in diff:
            key = f"{row.get('f13', '')}.{row.get('f12', '')}"
            if row.get('f12'):
                # ETF 价格/涨跌额显示三位小数
                etf = is_etf(row.get('f12'), row.get('f13'))
                # 只取滚动市盈率TTM(f115)，没有则显示-
                pe = row.get('f115')
                result[key] = {
                    'name': row.get('f14', ''),
                    'price': fmt(row.get('f2'), etf),
                    'pct': fmt_pct(row.get('f3')),
                    'change': fmt(row.get('f4'), etf),
                    'volume': fmt_volume(row.get('f5'), row.get('f13')),
                    'amount': fmt_amount(row.get('f6')),
                    'amount_raw': row.get('f6'),
                    'amplitude': fmt_pct(row.get('f7')),
                    'turnover': fmt_pct(row.get('f8')),
                    'turnover_raw': row.get('f8'),
                    'pe': fmt(pe),
                    'pb': fmt(row.get('f23')),
                    'high': fmt(row.get('f15'), etf),
                    'low': fmt(row.get('f16'), etf),
                    'open': fmt(row.get('f17'), etf),
                    'pre_close': fmt(row.get('f18'), etf),
                    'total_cap': fmt_cap(row.get('f20')),
                    'float_cap': fmt_cap(row.get('f21')),
                    'total_shares': fmt_cap(row.get('f38')),
                    'float_shares': fmt_cap(row.get('f39')),
                    'industry': row.get('f100', '').replace('、', '·') if row.get('f100') else '',
                }
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'data': {}})


# ==================== 个股补充 ====================

@app.route('/api/stock-extra')
def stock_extra():
    """量比/委比（ulist.np/get 的 fltt=2 不支持，需单独请求）"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/get"
        params = {
            'secid': f"{market}.{code}",
            'fields': 'f50,f191',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        r = requests.get(url, params=params, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/',
        }, timeout=8, proxies=REQUEST_PROXIES)
        d = (r.json().get('data') or {})
        vr = d.get('f50')
        br = d.get('f191')
        if market not in ('1', '2', '0', '90'): br = None
        return jsonify({
            'success': True,
            'data': {
                'volume_ratio': round(float(vr) / 100, 2) if vr is not None and vr != '-' else '-',
                'bid_ratio': (str(round(br / 100, 2)) + '%') if br is not None and br != '-' else '-',
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==================== 概念题材 ====================

@app.route('/api/stock-concepts')
def stock_concepts():
    """股票核心概念题材"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    if market not in ('0', '1', '2', '90'):
        return jsonify({'success': True, 'data': []})
    try:
        prefix = {'0': 'SZ', '1': 'SH', '2': 'SH'}.get(str(market), 'SZ')
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/CoreConception/PageAjax?code={prefix}{code}"
        r = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://emweb.eastmoney.com/',
        }, timeout=10, proxies=REQUEST_PROXIES)
        d = r.json()
        hxtc = d.get('hxtc', [])
        # 取核心题材关键词，排除"经营范围"和KEYWORD==KEY_CLASSIF的占位标签
        keywords = [x.get('KEYWORD', '') for x in hxtc
                    if x.get('KEY_CLASSIF') != '经营范围'
                    and x.get('KEYWORD', '') != x.get('KEY_CLASSIF', '')]
        return jsonify({'success': True, 'data': keywords})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==================== 主营构成（东方财富） ====================

@app.route('/api/stock-biz-comp')
def stock_biz_comp():
    """股票主营构成（按产品分类，取最新报告期）"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        prefix = {'0': 'SZ', '1': 'SH', '2': 'SH'}.get(str(market), 'SZ')
        url = f"https://emweb.securities.eastmoney.com/PC_HSF10/BusinessAnalysis/PageAjax?code={prefix}{code}"
        r = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://emweb.eastmoney.com/',
        }, timeout=10, proxies=REQUEST_PROXIES)
        data = r.json()
        zygcfx = data.get('zygcfx', [])
        if not zygcfx:
            return jsonify({'success': True, 'data': []})

        # 取最新报告期的产品分类(MAINOP_TYPE='2'，注意是字符串比较)
        products = [x for x in zygcfx if x.get('MAINOP_TYPE') == '2']
        if not products:
            return jsonify({'success': True, 'data': []})

        # 按报告期递减排序，取最新
        products.sort(key=lambda x: str(x.get('REPORT_DATE', '')), reverse=True)
        latest_date = str(products[0].get('REPORT_DATE', ''))

        result = []
        for p in products:
            if str(p.get('REPORT_DATE', '')) != latest_date:
                continue
            name = (p.get('ITEM_NAME') or '').strip()
            # 过滤掉"合计""内部抵消""其他(补充)"等无意义项
            if not name or '抵消' in name or '合计' in name:
                continue
            income = p.get('MAIN_BUSINESS_INCOME')
            ratio = p.get('MBI_RATIO')
            gross = p.get('GROSS_RPOFIT_RATIO')
            result.append({
                'name': name,
                'income': _fmt_biz_income(income),
                'income_ratio': f"{float(ratio) * 100:.2f}%" if ratio is not None else '-',
                'gross_profit': f"{float(gross) * 100:.2f}%" if gross is not None and gross != '-' else '-',
            })
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


def _fmt_biz_income(v):
    """格式化营收金额：1402亿 / 452.3亿 / 33.42亿"""
    if v is None or v == '-' or v == '':
        return '-'
    try:
        v = float(v)
        if v >= 1e12:
            return f"{v / 1e12:.2f}万亿"
        if v >= 1e8:
            return f"{v / 1e8:.2f}亿"
        return f"{v / 1e4:.2f}万"
    except Exception:
        return str(v)


# ==================== 分时 ====================

@app.route('/api/stock-minute')
def stock_minute():
    """股票分时走势（单日用东财 push2delay，多日用新浪 5分钟K线）"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    days = int(request.args.get('days', '1'))
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        if days <= 1:
            # 单日：东财 push2delay trends2
            url = "https://push2delay.eastmoney.com/api/qt/stock/trends2/get"
            params = {
                'secid': f"{market}.{code}",
                'fields1': 'f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13',
                'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58',
                'ndays': 1,
            }
            r = requests.get(url, params=params,
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'},
                timeout=10, proxies=REQUEST_PROXIES,
            )
            d = r.json()
            trends = (d.get('data') or {}).get('trends') or []
            pre_close = (d.get('data') or {}).get('preClose', 0)
            times, prices, volumes, amounts = [], [], [], []
            prevVol = prevAmt = 0
            for t in trends:
                parts = t.split(',')
                if len(parts) >= 2:
                    full_tm = parts[0]
                    tm = full_tm.split(' ')[-1] if ' ' in full_tm else full_tm
                    if market in ('0','1','2','90','116'):
                        if tm < '09:30': continue
                    times.append(full_tm if market == '106' else tm)
                    prices.append(float(parts[1]))
                    curVol = int(float(parts[5])) if len(parts) > 5 and parts[5] else 0
                    curAmt = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                    diffVol = max(0, curVol - prevVol)
                    if market in ('0', '1', '2', '90'): diffVol *= 100
                    volumes.append(diffVol)
                    amounts.append(max(0, curAmt - prevAmt))
                    prevVol = curVol; prevAmt = curAmt
        elif market in ('116', '106'):
            # 港股/美股多日：Yahoo Finance 5分钟K线
            import os as _os2, datetime as _dt2
            from datetime import timezone as _tz, timedelta as _td
            _old_no2 = _os2.environ.pop('no_proxy', None)
            _old_NO2 = _os2.environ.pop('NO_PROXY', None)
            try:
                if market == '116':
                    symbol = str(int(code)).zfill(4) + '.HK'
                    _yh_tz = _tz(_td(hours=8))  # UTC+8
                else:
                    symbol = code
                    _yh_tz = _tz(_td(hours=-5))  # 美股冬令时 UTC-5

                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=5m"
                r_yh = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                result = (r_yh.json().get('chart', {}).get('result') or [None])[0]
                if not result:
                    return jsonify({'success': False, 'error': '无数据'})

                yh_ts = result.get('timestamp') or []
                yh_quotes = (result.get('indicators', {}).get('quote') or [None])[0]
                if not yh_quotes:
                    return jsonify({'success': False, 'error': '无数据'})

                raw_points = []
                for i, ts in enumerate(yh_ts):
                    c = yh_quotes['close'][i]
                    v = yh_quotes['volume'][i]
                    if c is None:
                        continue
                    dt = _dt2.datetime.fromtimestamp(ts, tz=_yh_tz)
                    raw_points.append({
                        'date': dt.strftime('%Y-%m-%d'),
                        'time': dt.strftime('%H:%M'),
                        'price': round(float(c), 3),
                        'volume': int(v or 0)
                    })

                if not raw_points:
                    return jsonify({'success': False, 'error': '无数据'})

                # 按日期去重排序，取最近 days 个交易日
                all_dates = []
                seen_dates = set()
                for p in raw_points:
                    if p['date'] not in seen_dates:
                        all_dates.append(p['date'])
                        seen_dates.add(p['date'])
                keep_dates = set(all_dates[-days:])

                # preClose：最后一个非保留日的收盘价
                pre_close = 0
                for p in reversed(raw_points):
                    if p['date'] not in keep_dates:
                        pre_close = p['price']
                        break

                times, prices, volumes, amounts = [], [], [], []
                for p in raw_points:
                    if p['date'] not in keep_dates:
                        continue
                    times.append(p['date'] + ' ' + p['time'])
                    prices.append(p['price'])
                    volumes.append(p['volume'])
                    amounts.append(round(p['price'] * p['volume'], 2))
            finally:
                if _old_no2 is not None: _os2.environ['no_proxy'] = _old_no2
                if _old_NO2 is not None: _os2.environ['NO_PROXY'] = _old_NO2
        else:
            # 多日：A股 新浪 5分钟K线
            prefix = 'sh' if market in ('1', '2') else 'sz' if market in ('0', '90') else None
            if not prefix:
                return jsonify({'success': False, 'error': '该市场暂不支持多日分时'})

            sina_prefix = 'sh' if prefix == 'sh' else 'sz'
            sina_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_prefix}{code}&scale=5&datalen={days*60}"
            sr = requests.get(sina_url,
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'},
                timeout=15,
            )
            srows = sr.json()
            times, prices, volumes, amounts = [], [], [], []
            pre_close = 0
            if isinstance(srows, list) and len(srows) > 0:
                # 先收集所有日期，取最后 days 个
                all_dates = []
                for row in srows:
                    dt = row.get('day', '')
                    if dt:
                        ds = dt.split(' ')[0]
                        if not all_dates or all_dates[-1] != ds:
                            all_dates.append(ds)
                keep_dates = set(all_dates[-days:])
                # preClose: 最近一天的前一日收盘价
                prev_close = 0
                for row in srows:
                    dt = row.get('day', '')
                    close_v = float(row.get('close', 0))
                    if not dt or not close_v: continue
                    ds = dt.split(' ')[0]
                    if ds not in keep_dates:
                        prev_close = close_v  # 不断覆盖为最后一个非保留日的收盘价
                pre_close = prev_close
                for row in srows:
                    dt = row.get('day', '')
                    close_v = row.get('close', 0)
                    vol_v = row.get('volume', 0)
                    if not dt or not close_v: continue
                    if dt.split(' ')[0] not in keep_dates: continue
                    if ':' in dt and dt.count(':') == 2:
                        dt = dt[:dt.rfind(':')]
                    price = float(close_v)
                    vol = int(float(vol_v)) if vol_v else 0
                    if market in ('0', '1', '2', '90'): vol *= 100  # 手→股
                    times.append(dt)
                    prices.append(price)
                    volumes.append(vol)
                    amounts.append(round(price * vol, 2))  # 成交额=价格×成交量
        return jsonify({'success': True, 'data': {'times': times, 'prices': prices, 'volumes': volumes, 'amounts': amounts, 'preClose': pre_close, 'days': days}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== K线 ====================

@app.route('/api/stock-kline')
def stock_kline():
    """股票K线（日K/周K/月K）"""
    import re, json, datetime as _dt
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    period = request.args.get('period', 'day')  # day / week / month
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
        rows = []

        # Tencent/Yahoo 周期映射
        tx_period = {'day': 'day', 'week': 'week', 'month': 'month'}.get(period, 'day')
        tx_key = 'qfq' + tx_period
        yh_intv = {'day': '1d', 'week': '1wk', 'month': '1mo'}.get(period, '1d')

        if market in ('1', '2', '0', '90'):
            prefix = 'sh' if market in ('1', '2') else 'sz'
            param = f"{prefix}{code},{tx_period},,,800,qfq"
            r = requests.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
                           params={'param': param},
                           headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.qq.com/'},
                           timeout=10, proxies=REQUEST_PROXIES)
            jd = r.json()
            jd_data = (jd.get('data') or {}).get(f"{prefix}{code}", {})
            klines = jd_data.get(tx_key) or jd_data.get(tx_period) or []

            # 同花顺（成交额/换手率）
            extra = {}
            try:
                r2 = requests.get(f"https://d.10jqka.com.cn/v2/line/hs_{code}/01/last.js",
                                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.10jqka.com.cn/'},
                                timeout=8, proxies=REQUEST_PROXIES)
                text = r2.text
                s = text.find('(') + 1; e = text.rfind(')')
                ths = json.loads(text[s:e]) if s > 0 and e > s else {}
                for line in ths.get('data', '').split(';'):
                    parts = line.split(',')
                    if len(parts) >= 8:
                        d = parts[0]
                        extra[d[:4] + '-' + d[4:6] + '-' + d[6:8]] = {
                            'amount': float(parts[6]), 'turnover': round(float(parts[7]), 2)
                        }
            except: pass

            for k in klines:
                if len(k) >= 6:
                    row = {
                        'time': k[0],
                        'open': float(k[1]), 'close': float(k[2]),
                        'high': float(k[3]), 'low': float(k[4]),
                        'volume': int(float(k[5])),
                    }
                    ex = extra.get(k[0])
                    if ex:
                        row['amount'] = ex['amount']
                        row['turnover'] = ex['turnover']
                    rows.append(row)
        elif market in ('116', '106'):
            # 港股/美股 → 本地 DB（由 sync 提前拉取），无缓存时再走 Yahoo
            from market_db.db import detail_klines_get
            db_rows = detail_klines_get(code, market, tx_period, limit=800)
            if db_rows:
                for k in db_rows:
                    rows.append({
                        'time': k['date'][:4] + '-' + k['date'][4:6] + '-' + k['date'][6:8],
                        'open': k['open'], 'close': k['close'],
                        'high': k['high'], 'low': k['low'],
                        'volume': int(k['volume']),
                        'amount': k['amount'],
                    })
            else:
                # 本地无数据，实时拉 Yahoo
                import os as _os
                _old_no = _os.environ.pop('no_proxy', None)
                _old_NO = _os.environ.pop('NO_PROXY', None)
                try:
                    if market == '116':
                        symbol = str(int(code)).zfill(4) + '.HK'
                    else:
                        symbol = code
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1y&interval={yh_intv}"
                    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    result = (r.json().get('chart', {}).get('result') or [None])[0]
                    if not result:
                        return jsonify({'success': False, 'error': '无数据'})
                    timestamps = result.get('timestamp') or []
                    quotes = (result.get('indicators', {}).get('quote') or [None])[0]
                    if not quotes:
                        return jsonify({'success': False, 'error': '无数据'})
                    for i, ts in enumerate(timestamps):
                        o = quotes['open'][i]
                        if o is None:
                            continue
                        dt = _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc)
                        rows.append({
                            'time': dt.strftime('%Y-%m-%d'),
                            'open': round(float(o), 3),
                            'close': round(float(quotes['close'][i] or 0), 3),
                            'high': round(float(quotes['high'][i] or 0), 3),
                            'low': round(float(quotes['low'][i] or 0), 3),
                            'volume': int(quotes['volume'][i] or 0),
                            'amount': 0,
                        })
                finally:
                    if _old_no is not None: _os.environ['no_proxy'] = _old_no
                    if _old_NO is not None: _os.environ['NO_PROXY'] = _old_NO
        else:
            return jsonify({'success': False, 'error': '暂不支持该市场K线'})

        return jsonify({'success': True, 'data': {'name': code, 'code': code, 'market': market, 'klines': rows}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== 技术选股 ====================

@app.route('/api/technical/ascending-channel', methods=['POST'])
def technical_ascending_channel_start():
    """启动扫描"""
    market = request.args.get('market', '')
    result = run_ascending_channel_async(market=market)
    return jsonify(result)

@app.route('/api/technical/ascending-channel/status')
def technical_ascending_channel_status():
    """查询扫描进度"""
    return jsonify(get_scan_status())


# ==================== 市场数据库 ====================

@app.route('/api/market-db/init/cancel', methods=['POST'])
def market_db_init_cancel():
    from market_db.sync import cancel_init
    result = cancel_init()
    return jsonify(result)

@app.route('/api/market-db/init/<seg_key>', methods=['POST'])
def market_db_init(seg_key):
    from market_db.sync import init_segment
    result = init_segment(seg_key)
    return jsonify(result)

@app.route('/api/market-db/clear/<seg_key>', methods=['POST'])
def market_db_clear(seg_key):
    from market_db.sync import clear_market
    result = clear_market(seg_key)
    return jsonify(result)

@app.route('/api/market-db/init/status')
def market_db_init_status():
    from market_db.sync import get_init_status
    return jsonify(get_init_status())

@app.route('/api/market-db/segments')
def market_db_segments():
    from market_db.sync import get_segments_info
    return jsonify(get_segments_info())

@app.route('/api/market-db/status')
def market_db_status():
    from market_db.db import list_stocks_all, detail_info_all
    list_count = len(list_stocks_all())
    detail_count = len(detail_info_all())
    return jsonify({'list_stocks': list_count, 'detail_stocks': detail_count})


# ==================== 公司公告 ====================

def _collect_target_codes():
    """收集自选股+选股代码"""
    wl_rows = get_all()
    wl_codes = {r[0] for r in wl_rows}
    pick_codes_raw = request.args.get('codes', '').split(',')
    pick_codes = {c.strip() for c in pick_codes_raw if c.strip()}
    return wl_codes | pick_codes


@app.route('/api/announcements')
def announcements_list():
    """获取自选股+选股列表中股票的公司公告（东方财富，最近15天）"""
    try:
        target_codes = _collect_target_codes()
        if not target_codes:
            return jsonify({'success': True, 'data': []})

        from datetime import datetime as _dt, timedelta
        cutoff = (_dt.now() - timedelta(days=15)).strftime('%Y-%m-%d')

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/',
        }
        result = []
        for page in (1, 2):
            params = {
                'page_size': 200,
                'page_index': page,
                'ann_type': 'SHA,CYB,SZA,BJA,INV',
                'client_source': 'web',
                'f_node': 0,
                'stock_list': ','.join(sorted(target_codes)),
            }
            r = requests.get('https://np-anotice-stock.eastmoney.com/api/security/ann',
                            params=params, headers=headers, timeout=15, proxies=REQUEST_PROXIES)
            data = r.json()
            items = (data.get('data') or {}).get('list') or []
            if not items:
                break
            for item in items:
                codes = item.get('codes', [])
                code_info = codes[0] if codes else {}
                columns = item.get('columns', [])
                col_info = columns[0] if columns else {}
                notice_date = (item.get('notice_date') or '')[:10]
                if notice_date < cutoff:
                    continue  # 超出15天范围，跳过
                result.append({
                    'code': code_info.get('stock_code', ''),
                    'name': code_info.get('short_name', ''),
                    'title': item.get('title', ''),
                    'notice_date': notice_date,
                    'column_name': col_info.get('column_name', ''),
                    'art_code': item.get('art_code', ''),
                    'art_url': f"https://data.eastmoney.com/notices/detail/{code_info.get('stock_code', '')}/{item.get('art_code', '')}.html",
                })
            # 如果当前页最后一条已超出15天，不必再翻页
            last_item = items[-1]
            last_date = (last_item.get('notice_date') or '')[:10]
            if last_date < cutoff:
                break

        # 同一股票放一起，按每组最新公告日排序（降序），组内也按日期降序
        newest = {}
        for r in result:
            code = str(r.get('code', ''))
            d = r.get('notice_date', '0000-00-00')
            if code not in newest or d > newest[code]:
                newest[code] = d
        result.sort(key=lambda r: (newest.get(str(r.get('code', '')), '0000-00-00'), r.get('notice_date', '0000-00-00')), reverse=True)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"获取公告失败: {e}")
        return jsonify({'success': False, 'error': str(e)})


# ==================== 解禁列表 ====================

@app.route('/api/lifting')
def lifting_list():
    """获取自选股+选股列表中股票的限售股解禁信息"""
    try:
        target_codes = _collect_target_codes()
        if not target_codes:
            return jsonify({'success': True, 'data': []})

        # ③ 从 adata 获取近一个月全市场解禁数据
        import adata
        df = adata.sentiment.stock_lifting_last_month()
        if df is None or df.empty:
            return jsonify({'success': True, 'data': []})

        df = df.where(df.notna(), None)
        all_records = df.to_dict(orient='records')

        # ④ 只保留自选/选股列表中的股票
        result = [r for r in all_records if str(r.get('stock_code', '')) in target_codes]
        # ⑤ 同一股票放一起，按每组最早解禁日排序，组内按日期升序
        earliest = {}
        for r in result:
            code = str(r.get('stock_code', ''))
            d = r.get('lift_date', '9999-99-99')
            if code not in earliest or d < earliest[code]:
                earliest[code] = d
        result.sort(key=lambda r: (earliest.get(str(r.get('stock_code', '')), '9999-99-99'), r.get('lift_date', '9999-99-99')))
        return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"获取解禁列表失败: {e}")
        return jsonify({'success': False, 'error': str(e)})


# ==================== 启动 ====================

if __name__ == '__main__':
    start_major_indices_poller()  # 启动后台指数行情轮询
    from market_db.sync import start_startup_sync
    import threading
    threading.Timer(2.0, start_startup_sync).start()  # 延迟 2s，等 Flask 启动完
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
