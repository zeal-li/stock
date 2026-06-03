"""鑫多多 - 股票行情仪表盘"""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests

from services import REQUEST_PROXIES
from services.money_flow import get_index_minute_data, get_turnover_day_data
from services.market_data import (
    get_major_indices, get_sh000001_minute_data, get_market_fund_flow,
    get_fear_index, get_risk_index, get_margin_trading,
)
from services.search import search_stock as do_search
from services.finance import get_goodwill

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

@app.route('/api/turnover-day')
def turnover_day():
    return jsonify(get_turnover_day_data())


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

def _is_etf(code, market):
    """判断是否为ETF（沪市51xxxx，深市15xxxx）"""
    c = str(code) if code else ''
    m = str(market) if market else ''
    if m in ('1', '2') and c[:2] == '51':
        return True
    if m == '0' and c[:2] == '15':
        return True
    return False

def _fmt(v, is_etf=False):
    if v is None or v == '-' or v == '': return '-'
    try: return f"{float(v):.3f}" if is_etf else f"{float(v):.2f}"
    except: return str(v)

def _fmt_pct(v):
    if v is None or v == '-' or v == '': return '-'
    try: return f"{float(v):.2f}%"
    except: return str(v)

def _fmt_volume(v, market=None):
    if v is None or v == '-' or v == '': return '-'
    try:
        v = float(v)
        market = str(market) if market is not None else ''
        # A股(沪0/1,深0,北90)成交量单位是手，1手=100股；港股美股等已是股
        if market in ('0', '1', '2', '90'):
            v *= 100
        if v >= 1e8: return f"{v/1e8:.2f}亿股"
        if v >= 1e4: return f"{v/1e4:.2f}万股"
        return f"{v:.0f}股"
    except: return str(v)

def _fmt_amount(v):
    if v is None or v == '-' or v == '': return '-'
    try:
        v = float(v)
        if v >= 1e8: return f"{v/1e8:.2f}亿"
        if v >= 1e4: return f"{v/1e4:.2f}万"
        return f"{v:.0f}"
    except: return str(v)

def _fmt_cap(v):
    if v is None or v == '-' or v == '': return '-'
    try:
        v = float(v)
        if v >= 1e12: return f"{v/1e12:.2f}万亿"
        if v >= 1e8: return f"{v/1e8:.2f}亿"
        return f"{v/1e4:.2f}万"
    except: return str(v)


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
            # f9=动态市盈率(原PE), f115=市盈率TTM(滚动市盈率,同花顺默认), f162=静态市盈率
            # f15=最高, f16=最低, f17=今开, f18=昨收, f38=总股本, f39=流通股本
            'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f12,f13,f14,f15,f16,f17,f18,f20,f21,f23,f38,f39,f115,f162',
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
                is_etf = _is_etf(row.get('f12'), row.get('f13'))
                # PE TTM(滚动市盈率)优先,更稳定,与同花顺一致;若没有则用动态市盈率(f9)
                pe = row.get('f115')  # 只取 TTM
                result[key] = {
                    'name': row.get('f14', ''),
                    'price': _fmt(row.get('f2'), is_etf),
                    'pct': _fmt_pct(row.get('f3')),
                    'change': _fmt(row.get('f4'), is_etf),
                    'volume': _fmt_volume(row.get('f5'), row.get('f13')),
                    'amount': _fmt_amount(row.get('f6')),
                    'amount_raw': row.get('f6'),
                    'amplitude': _fmt_pct(row.get('f7')),
                    'turnover': _fmt_pct(row.get('f8')),
                    'turnover_raw': row.get('f8'),
                    'pe': _fmt(pe),
                    'pb': _fmt(row.get('f23')),
                    'high': _fmt(row.get('f15'), is_etf),
                    'low': _fmt(row.get('f16'), is_etf),
                    'open': _fmt(row.get('f17'), is_etf),
                    'pre_close': _fmt(row.get('f18'), is_etf),
                    'total_cap': _fmt_cap(row.get('f20')),
                    'float_cap': _fmt_cap(row.get('f21')),
                    'total_shares': _fmt_cap(row.get('f38')),
                    'float_shares': _fmt_cap(row.get('f39')),
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

# ==================== 分时 ====================

@app.route('/api/stock-minute')
def stock_minute():
    """股票分时走势"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
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
                # 按市场过滤盘前数据
                if market in ('0','1','2','90','116'):
                    if tm < '09:30': continue
                # 美股返回完整日期时间（跨天），A/港股只返回时间
                times.append(full_tm if market == '106' else tm)
                prices.append(float(parts[1]))
                curVol = int(float(parts[5])) if len(parts) > 5 and parts[5] else 0
                curAmt = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                diffVol = max(0, curVol - prevVol)
                if market in ('0', '1', '2', '90'): diffVol *= 100  # A股手转股
                volumes.append(diffVol)
                amounts.append(max(0, curAmt - prevAmt))
                prevVol = curVol; prevAmt = curAmt
        return jsonify({'success': True, 'data': {'times': times, 'prices': prices, 'volumes': volumes, 'amounts': amounts, 'preClose': pre_close}})
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
            param = f"{prefix}{code},{tx_period},,,360,qfq"
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
            # 港股/美股 → Yahoo Finance（需走系统代理，不能 no_proxy）
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
                    })
            finally:
                if _old_no is not None: _os.environ['no_proxy'] = _old_no
                if _old_NO is not None: _os.environ['NO_PROXY'] = _old_NO
        else:
            return jsonify({'success': False, 'error': '暂不支持该市场K线'})

        return jsonify({'success': True, 'data': {'name': code, 'code': code, 'market': market, 'klines': rows}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ==================== 启动 ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
