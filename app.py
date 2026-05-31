"""鑫多多 - 股票行情仪表盘"""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import requests

from services import REQUEST_PROXIES
from services.money_flow import get_money_flow_data, get_index_minute_data, get_turnover_day_data
from services.market_data import (
    get_major_indices, get_sh000001_minute_data, get_market_fund_flow,
    get_fear_index, get_risk_index, get_margin_trading,
)
from services.search import search_stock as do_search
from services.finance import get_goodwill

app = Flask(__name__)
CORS(app)


# ==================== 页面 ====================

@app.route('/')
def index():
    return render_template('index.html')


# ==================== 资金流向 ====================

@app.route('/api/money-flow/<flow_type>')
def money_flow_type(flow_type):
    return jsonify(get_money_flow_data(flow_type))

@app.route('/api/money-flow')
def money_flow():
    return jsonify(get_money_flow_data('concept'))


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

def _fmt(v):
    if v is None or v == '-' or v == '': return '-'
    try: return f"{float(v):.2f}"
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
            'fields': 'f2,f3,f4,f5,f6,f7,f8,f9,f12,f13,f14,f20,f21,f23',
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
                result[key] = {
                    'name': row.get('f14', ''),
                    'price': _fmt(row.get('f2')),
                    'pct': _fmt_pct(row.get('f3')),
                    'change': _fmt(row.get('f4')),
                    'volume': _fmt_volume(row.get('f5'), row.get('f13')),
                    'amount': _fmt_amount(row.get('f6')),
                    'amplitude': _fmt_pct(row.get('f7')),
                    'turnover': _fmt_pct(row.get('f8')),
                    'pe': _fmt(row.get('f9')),
                    'pb': _fmt(row.get('f23')),
                    'total_cap': _fmt_cap(row.get('f20')),
                    'float_cap': _fmt_cap(row.get('f21')),
                }
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'data': {}})


# ==================== 启动 ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
