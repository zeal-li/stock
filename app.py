"""鑫多多 - 股票行情仪表盘"""
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

from services.money_flow import get_money_flow_data, get_index_minute_data, get_turnover_day_data
from services.market_data import (
    get_major_indices, get_sh000001_minute_data, get_market_fund_flow,
    get_fear_index, get_risk_index, get_margin_trading,
)
from services.search import search_stock as do_search

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

@app.route('/api/search-stock')
def search_stock():
    return jsonify(do_search(request.args.get('q', '')))


# ==================== 启动 ====================

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
