"""鑫多多 - 股票行情仪表盘"""
from flask import Flask, jsonify, render_template, request, session, g
from flask_cors import CORS
import requests
import json
import re

from common import REQUEST_PROXIES
from common.utils import is_etf, fmt, fmt_pct, fmt_volume, fmt_amount, fmt_cap, is_market_opened, guess_market, \
    is_a_share, is_overseas, is_hk, is_us, adjust_volume, to_yahoo_symbol, SINA_PREFIX, EM_F10_PREFIX, THS_PREFIX, to_em_market
from common.finance import get_goodwill
from money_flow.market import get_major_indices, get_sh000001_minute_data, get_index_minute_data
from money_flow.fund_flow import get_market_fund_flow
from money_flow.fear_index import get_fear_index
from money_flow.risk_index import get_risk_index
from money_flow.margin import get_margin_trading
from longhu_bang.service import get_longhu_bang, init_longhu_bang_update
from global_market.commodities import get_global_commodities
from global_market.forex import get_forex_rates
from sector_fund.service import get_sector_fund, get_sector_stocks, get_etf_stocks
from money_flow.storage import start_major_indices_poller
from market_db.sync import init_market_db_update
from stock_pick.service import search_stock as do_search
from watchlist.service import get_all, add, remove as wl_remove, update_price, reorder
from watchlist.service import etf_get_all, etf_add, etf_remove, etf_reorder
from watchlist.service import holdings_get_all, holdings_add, holdings_remove, holdings_update, holdings_reorder
import logging
logger = logging.getLogger(__name__)
from technical_screen.service import run_scan_async, get_scan_status, get_strategies
from abnormal_center.service import get_prediction, get_monitor, analyze_stock
from market_news.service import get_hot_list

import sys as _sys, os as _os
if getattr(_sys, 'frozen', False):
    # PyInstaller exe 模式
    base = _sys._MEIPASS
    app = Flask(__name__, template_folder=_os.path.join(base, 'front_end', 'templates'), static_folder=_os.path.join(base, 'front_end', 'static'))
else:
    app = Flask(__name__, template_folder='../front_end/templates', static_folder='../front_end/static')
CORS(app)
# session 签名密钥：服务器启动时初始化（读库或生成并持久化），避免硬编码、重启后登录态不失效
from auth.service import init_secret_key
app.secret_key = init_secret_key()
# 会话过期时间：30 天（浏览器关闭后 session cookie 仍保留，30 天内无需重新登录）
from datetime import timedelta
app.permanent_session_lifetime = timedelta(days=30)


# ==================== 页面 ====================

@app.route('/')
def index():
    return render_template('index.html')


# ==================== 认证 ====================

@app.before_request
def _require_login():
    """除认证接口和静态资源外，所有请求需先登录"""
    g.user = session.get('user')
    g.user_id = session.get('user_id')
    if g.user:
        # 校验会话版本号：密码修改后版本 +1，旧登录态立即失效
        from auth.service import get_session_version
        current_version = get_session_version(g.user)
        if current_version is not None and session.get('session_version') == current_version:
            return
        session.clear()
        g.user = None
        g.user_id = None
    path = request.path
    # 放行登录页、注册/登录/会话接口（注意：/ 不放行，未登录访问首页应直接返回登录页，避免先闪主界面）
    if path in ('/login', '/api/auth/register', '/api/auth/login', '/api/auth/session'):
        return
    if path.startswith('/static/'):
        return
    # 未登录：页面请求返回登录页，API 请求返回 401
    if path.startswith('/api/'):
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    return render_template('login.html')


@app.route('/login')
def login_page():
    return render_template('login.html')


@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    from auth.service import register
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    success, message = register(username, password)
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    from auth.service import login, get_user_id
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    success, message, user_type, session_version = login(username, password)
    if success:
        session['user'] = username
        session['user_type'] = user_type
        session['user_id'] = get_user_id(username)
        session['session_version'] = session_version
        session.permanent = True
        return jsonify({'success': True, 'message': message, 'username': username,
                        'user_type': user_type})
    return jsonify({'success': False, 'error': message})


@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    session.pop('user', None)
    return jsonify({'success': True})


@app.route('/api/auth/change-password', methods=['POST'])
def auth_change_password():
    from auth.service import change_password
    username = session.get('user')
    if not username:
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    old_password = request.form.get('old_password', '')
    new_password = request.form.get('new_password', '')
    success, message = change_password(username, old_password, new_password)
    if success:
        session.clear()
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message})


@app.route('/api/auth/session')
def auth_session():
    user = session.get('user')
    if user:
        user_type = session.get('user_type', 0)
        return jsonify({'success': True, 'logged_in': True, 'username': user,
                        'user_type': user_type})
    return jsonify({'success': True, 'logged_in': False})


@app.route('/api/auth/me')
def auth_me():
    from auth.service import get_user
    username = session.get('user')
    if not username:
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    user = get_user(username)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'})
    return jsonify({'success': True, 'data': user})


@app.route('/api/auth/delete-account', methods=['POST'])
def auth_delete_account():
    from auth.service import get_user, get_user_id, delete_user
    username = session.get('user')
    if not username:
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    user = get_user(username)
    if not user:
        return jsonify({'success': False, 'error': '用户不存在'})
    # root 为系统用户，不允许注销
    if user['user_type'] == 101:
        return jsonify({'success': False, 'error': 'root 为系统用户，不允许注销'})
    user_id = get_user_id(username)
    if not user_id:
        return jsonify({'success': False, 'error': '用户不存在'})
    success, message = delete_user(user_id)
    if success:
        session.clear()
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message})


@app.route('/api/system/config')
def system_config():
    """系统设置：返回 config.db 中的配置项（当前为 secret_key），仅 root 可访问"""
    from common.utils import USER_TYPE_ROOT
    if session.get('user_type') != USER_TYPE_ROOT:
        return jsonify({'success': False, 'error': '权限不足', 'code': 403}), 403
    from auth.service import get_app_config
    return jsonify({'success': True, 'data': get_app_config()})


@app.route('/api/system/secret-key/reset', methods=['POST'])
def system_secret_key_reset():
    """重置 secret_key：生成新密钥，所有已登录用户将失效需重新登录，仅 root 可操作"""
    from common.utils import USER_TYPE_ROOT
    if session.get('user_type') != USER_TYPE_ROOT:
        return jsonify({'success': False, 'error': '权限不足', 'code': 403}), 403
    from auth.service import reset_secret_key
    new_key = reset_secret_key()
    app.secret_key = new_key
    session.clear()
    return jsonify({'success': True, 'data': {'secret_key': new_key}})


@app.route('/api/system/register-toggle', methods=['POST'])
def system_register_toggle():
    """切换新用户注册开关，仅 root 可操作"""
    from common.utils import USER_TYPE_ROOT
    if session.get('user_type') != USER_TYPE_ROOT:
        return jsonify({'success': False, 'error': '权限不足', 'code': 403}), 403
    enabled = request.form.get('enabled', '')
    if enabled not in ('0', '1'):
        return jsonify({'success': False, 'error': '参数不合法'})
    from auth.service import set_register_enabled
    set_register_enabled(enabled == '1')
    return jsonify({'success': True, 'data': {'register_enabled': enabled == '1'}})


@app.route('/api/auth/users')
def auth_users():
    from auth.service import get_all_users
    return jsonify({'success': True, 'data': get_all_users()})


@app.route('/api/auth/users/<int:user_id>/password', methods=['POST'])
def auth_user_reset_password(user_id):
    from auth.service import get_user_by_id, reset_password
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'error': '用户不存在'})
    if session.get('user_type', 0) <= target['user_type']:
        return jsonify({'success': False, 'error': '权限不足'}), 403
    new_password = request.form.get('new_password', '')
    success, message = reset_password(user_id, new_password)
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message})


@app.route('/api/auth/users/<int:user_id>/delete', methods=['POST'])
def auth_user_delete(user_id):
    from auth.service import get_user_by_id, delete_user
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'error': '用户不存在'})
    if session.get('user_type', 0) <= target['user_type']:
        return jsonify({'success': False, 'error': '权限不足'}), 403
    success, message = delete_user(user_id)
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message})


@app.route('/api/auth/users/<int:user_id>/user-type', methods=['POST'])
def auth_user_update_type(user_id):
    from auth.service import get_user_by_id, update_user_type
    from common.utils import USER_TYPE_NORMAL, USER_TYPE_ADMIN, USER_TYPE_ROOT
    user = session.get('user')
    if not user:
        return jsonify({'success': False, 'error': '未登录', 'code': 401}), 401
    target = get_user_by_id(user_id)
    if not target:
        return jsonify({'success': False, 'error': '用户不存在'})
    current_user_type = session.get('user_type', 0)
    if current_user_type <= target['user_type']:
        return jsonify({'success': False, 'error': '权限不足'}), 403
    try:
        new_user_type = int(request.form.get('user_type', ''))
    except ValueError:
        return jsonify({'success': False, 'error': '用户类型不合法'})
    if new_user_type not in (USER_TYPE_NORMAL, USER_TYPE_ADMIN, USER_TYPE_ROOT) \
            or new_user_type >= current_user_type:
        return jsonify({'success': False, 'error': '权限不足'}), 403
    success, message = update_user_type(user_id, new_user_type)
    if success:
        return jsonify({'success': True, 'message': message})
    return jsonify({'success': False, 'error': message})


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


@app.route('/api/market-news')
def market_news():
    return jsonify(get_hot_list())


@app.route('/api/longhu-bang')
def longhu_bang():
    """龙虎榜每日明细，返回当天全部数据，前端负责分类筛选和排序"""
    trade_date = request.args.get('date', '').strip()
    return jsonify(get_longhu_bang(trade_date or None))


@app.route('/api/global-commodities')
def global_commodities():
    """全球大宗商品实时行情"""
    return jsonify(get_global_commodities())


@app.route('/api/global-forex')
def global_forex():
    """全球外汇汇率实时行情"""
    return jsonify(get_forex_rates())


@app.route('/api/sector-fund')
def sector_fund():
    """板块资金流向排行"""
    sector_type = request.args.get('type', 'concept').strip()
    period = request.args.get('period', 'today').strip()
    return jsonify(get_sector_fund(sector_type, period))


@app.route('/api/sector-stocks')
def sector_stocks():
    """板块成分股列表"""
    sector_code = request.args.get('code', '').strip()
    return jsonify(get_sector_stocks(sector_code))


@app.route('/api/etf-stocks')
def etf_stocks():
    """ETF成分股列表"""
    code = request.args.get('code', '').strip()
    market = request.args.get('market', '').strip()
    return jsonify(get_etf_stocks(code, market))


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
    rows = get_all(g.user_id)
    return jsonify({'success': True, 'data': [{'code': r[0], 'market': r[1], 'created_at': r[2], 'added_price': r[3]} for r in rows]})

@app.route('/api/watchlist', methods=['POST'])
def watchlist_add():
    code = request.form.get('code', '').strip()
    market = request.form.get('market', '').strip()
    added_price = request.form.get('added_price', '').strip()
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    add(g.user_id, code, market, added_price)
    return jsonify({'success': True})

@app.route('/api/watchlist/<code>', methods=['DELETE'])
def watchlist_remove(code):
    market = request.args.get('market', '')
    if not market:
        return jsonify({'success': False, 'error': '缺少 market 参数'})
    wl_remove(g.user_id, code, market)
    return jsonify({'success': True})

@app.route('/api/watchlist/<code>', methods=['PUT'])
def watchlist_update(code):
    market = request.form.get('market', '').strip()
    added_price = request.form.get('added_price', '').strip()
    if not market:
        return jsonify({'success': False, 'error': '缺少 market 参数'})
    update_price(g.user_id, code, market, added_price)
    return jsonify({'success': True})


@app.route('/api/watchlist/reorder', methods=['POST'])
def watchlist_reorder_route():
    """批量更新自选股排序"""
    import json as _json
    items_raw = request.form.get('items', '').strip()
    if not items_raw:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        items = _json.loads(items_raw)
        reorder(g.user_id, items)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==================== 场内ETF ====================

@app.route('/api/etf', methods=['GET'])
def etf_get():
    rows = etf_get_all(g.user_id)
    return jsonify({'success': True, 'data': [{'code': r[0], 'market': r[1], 'created_at': r[2]} for r in rows]})

@app.route('/api/etf', methods=['POST'])
def etf_add_route():
    code = request.form.get('code', '').strip()
    market = request.form.get('market', '').strip()
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    etf_add(g.user_id, code, market)
    return jsonify({'success': True})

@app.route('/api/etf/<code>', methods=['DELETE'])
def etf_remove_route(code):
    market = request.args.get('market', '')
    if not market:
        return jsonify({'success': False, 'error': '缺少 market 参数'})
    etf_remove(g.user_id, code, market)
    return jsonify({'success': True})



@app.route('/api/etf/reorder', methods=['POST'])
def etf_reorder_route():
    """批量更新场内ETF排序"""
    import json as _json
    items_raw = request.form.get('items', '').strip()
    if not items_raw:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        items = _json.loads(items_raw)
        etf_reorder(g.user_id, items)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==================== 持仓股 ====================

@app.route('/api/holdings', methods=['GET'])
def holdings_get():
    rows = holdings_get_all(g.user_id)
    return jsonify({'success': True, 'data': [{'code': r[0], 'market': r[1], 'created_at': r[2], 'hold_price': r[3], 'hold_qty': r[4]} for r in rows]})

@app.route('/api/holdings', methods=['POST'])
def holdings_add_route():
    code = request.form.get('code', '').strip()
    market = request.form.get('market', '').strip()
    hold_price = request.form.get('hold_price', '').strip()
    hold_qty = request.form.get('hold_qty', '').strip()
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    holdings_add(g.user_id, code, market, hold_price, hold_qty)
    return jsonify({'success': True})

@app.route('/api/holdings/<code>', methods=['DELETE'])
def holdings_remove_route(code):
    market = request.args.get('market', '')
    if not market:
        return jsonify({'success': False, 'error': '缺少 market 参数'})
    holdings_remove(g.user_id, code, market)
    return jsonify({'success': True})

@app.route('/api/holdings/<code>', methods=['PUT'])
def holdings_update_route(code):
    market = request.form.get('market', '').strip()
    hold_price = request.form.get('hold_price')
    hold_qty = request.form.get('hold_qty')
    if not market:
        return jsonify({'success': False, 'error': '缺少 market 参数'})
    holdings_update(g.user_id, code, market, hold_price, hold_qty)
    return jsonify({'success': True})


@app.route('/api/holdings/reorder', methods=['POST'])
def holdings_reorder_route():
    """批量更新持仓股排序"""
    import json as _json
    items_raw = request.form.get('items', '').strip()
    if not items_raw:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        items = _json.loads(items_raw)
        holdings_reorder(g.user_id, items)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/stock-quotes')
def stock_quotes():
    """批量获取股票实时行情"""
    secids = request.args.get('secids', '')
    if not secids:
        return jsonify({'success': False, 'data': {}})
    try:
        # 东方财富把北交所归为 market=0，请求时映射，但返回 key 用原始 market
        _code_orig_market = {}
        _mapped = []
        for s in secids.split(','):
            s = s.strip()
            if not s:
                continue
            parts = s.split('.', 1)
            if len(parts) == 2:
                _code_orig_market[parts[1]] = parts[0]
                if parts[0] == '2':
                    _mapped.append(f"0.{parts[1]}")
                else:
                    _mapped.append(s)
        secids = ','.join(_mapped)
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
        # 收集所有 ETF 代码，用于批量获取溢价率
        etf_codes = []
        for row in diff:
            code = row.get('f12', '')
            if not code:
                continue
            orig_mkt = _code_orig_market.get(code, str(row.get('f13', '')))
            key = f"{orig_mkt}.{code}"
            # ETF 价格/涨跌额显示三位小数
            etf = is_etf(code, orig_mkt)
            # 只取滚动市盈率TTM(f115)，没有则显示-
            pe = row.get('f115')
            result[key] = {
                'name': row.get('f14', ''),
                'price': fmt(row.get('f2'), etf),
                'pct': fmt_pct(row.get('f3')),
                'change': fmt(row.get('f4'), etf),
                'volume': fmt_volume(row.get('f5'), orig_mkt),
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
                # ETF 价格原始值，用于后续溢价率计算
                '_price_raw': float(row.get('f2')) if etf and row.get('f2') not in (None, '-', '') else None,
            }
            if etf and row.get('f2') not in (None, '-', ''):
                etf_codes.append((key, code))
        # 为 ETF 并发获取最新净值，计算溢价率
        if etf_codes:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            def _fetch_etf_nav(etf_code):
                try:
                    r_nav = requests.get(
                        'https://api.fund.eastmoney.com/f10/lsjz',
                        params={'callback': 'jQuery', 'fundCode': etf_code, 'pageIndex': 1, 'pageSize': 1},
                        headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://fundf10.eastmoney.com/'},
                        timeout=5
                    )
                    json_str = re.sub(r'^jQuery\(|\)$', '', r_nav.text)
                    data = json.loads(json_str)
                    nav_list = (data.get('Data') or {}).get('LSJZList') or []
                    if nav_list:
                        return float(nav_list[0]['DWJZ'])
                except Exception:
                    pass
                return None
            nav_map = {}
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(_fetch_etf_nav, c): k for k, c in etf_codes}
                for future in as_completed(futures):
                    k = futures[future]
                    nav = future.result()
                    if nav is not None:
                        nav_map[k] = nav
            # 计算溢价率: (最新价 / 单位净值 - 1) * 100
            for key, price_raw in [(k, result[k]['_price_raw']) for k in result if result[k].get('_price_raw') is not None]:
                nav = nav_map.get(key)
                if nav and nav > 0:
                    result[key]['premium_rate'] = round((price_raw / nav - 1) * 100, 2)
                else:
                    result[key]['premium_rate'] = None
            # 清理内部字段
            for k in result:
                result[k].pop('_price_raw', None)
        else:
            for k in result:
                result[k].pop('_price_raw', None)
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'data': {}})


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
            'secid': f"{to_em_market(market)}.{code}",
            'fields': 'f50,f191',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        r = requests.get(url, params=params, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/',
        }, timeout=8, proxies=REQUEST_PROXIES)
        d = (r.json().get('data') or {})
        vr = d.get('f50')
        br = d.get('f191')
        if not is_a_share(market): br = None
        return jsonify({'success': True,
            'data': {
                'volume_ratio': round(float(vr) / 100, 2) if vr is not None and vr != '-' else '-',
                'bid_ratio': (str(round(br / 100, 2)) + '%') if br is not None and br != '-' else '-',
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/stock-depth')
def stock_depth():
    """五档买卖挂单（仅A股，数据源：新浪财经）"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    if not is_a_share(market):
        return jsonify({'success': False, 'error': '仅支持A股'})
    try:
        prefix = 'sh' if str(market) in ('1', '2') else 'sz'
        url = f"https://hq.sinajs.cn/list={prefix}{code}"
        r = requests.get(url, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/',
        }, timeout=8, proxies=REQUEST_PROXIES)
        r.encoding = 'gbk'
        raw = r.text
        if not raw or '=""' in raw:
            return jsonify({'success': True, 'data': {'bids': [], 'asks': []}})
        # 解析：字段 10-29 为买一量/买一价 ... 买五量/买五价, 卖一量/卖一价 ... 卖五量/卖五价
        parts = raw.split('"')[1].split(',')
        def _p(idx):
            v = parts[idx] if idx < len(parts) else ''
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        def _v(idx):
            v = parts[idx] if idx < len(parts) else ''
            try:
                return int(float(v))
            except (ValueError, TypeError):
                return 0
        return jsonify({
            'success': True,
            'data': {
                'bids': [
                    {'price': _p(11), 'volume': _v(10)},
                    {'price': _p(13), 'volume': _v(12)},
                    {'price': _p(15), 'volume': _v(14)},
                    {'price': _p(17), 'volume': _v(16)},
                    {'price': _p(19), 'volume': _v(18)},
                ],
                'asks': [
                    {'price': _p(21), 'volume': _v(20)},
                    {'price': _p(23), 'volume': _v(22)},
                    {'price': _p(25), 'volume': _v(24)},
                    {'price': _p(27), 'volume': _v(26)},
                    {'price': _p(29), 'volume': _v(28)},
                ],
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/stock-trade-detail')
def stock_trade_detail():
    """逐笔成交明细（仅A股，数据源：东方财富）"""
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    if not is_a_share(market):
        return jsonify({'success': False, 'error': '仅支持A股'})
    try:
        url = "https://push2delay.eastmoney.com/api/qt/stock/details/get"
        params = {
            'secid': f"{to_em_market(market)}.{code}",
            'fields1': 'f1,f2,f3,f4',
            'fields2': 'f51,f52,f53,f54,f55',
            'pos': '-0',
            'wbp2u': '|0|0|0|web',
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        }
        r = requests.get(url, params=params, headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/',
        }, timeout=8, proxies=REQUEST_PROXIES)
        details = (r.json().get('data') or {}).get('details') or []
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
        return jsonify({'success': True, 'data': trades})
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
    if not is_a_share(market):
        return jsonify({'success': True, 'data': []})
    try:
        prefix = EM_F10_PREFIX.get(str(market), 'SZ')
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
        prefix = EM_F10_PREFIX.get(str(market), 'SZ')
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
                'secid': f"{to_em_market(market)}.{code}",
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
            # 先按原始顺序收集所有数据点
            raw_points = []
            prevAmt = 0
            for t in trends:
                parts = t.split(',')
                if len(parts) >= 2:
                    full_tm = parts[0]
                    tm = full_tm.split(' ')[-1] if ' ' in full_tm else full_tm
                    if is_a_share(market) or is_hk(market):
                        if tm < '09:30': continue
                    curVol = int(float(parts[5])) if len(parts) > 5 and parts[5] else 0
                    curAmt = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                    raw_points.append({
                        'tm': tm,
                        'full_tm': full_tm,
                        'price': float(parts[1]),
                        'vol': curVol,       # f56 是每分钟增量，不差值
                        'amt': curAmt,       # f57 也是每分钟增量
                    })


            # 按分钟聚合：同一分钟的多条数据合并 vol/amt，价格取最后一条
            times, prices, volumes, amounts = [], [], [], []
            i = 0
            while i < len(raw_points):
                p = raw_points[i]
                minute_key = p['tm'][:5]  # "HH:MM"
                agg_vol = p['vol']
                agg_amt = p['amt']
                last_price = p['price']
                j = i + 1
                while j < len(raw_points) and raw_points[j]['tm'][:5] == minute_key:
                    agg_vol += raw_points[j]['vol']
                    agg_amt += raw_points[j]['amt']
                    last_price = raw_points[j]['price']
                    j += 1
                if is_a_share(market):
                    agg_vol = adjust_volume(agg_vol, market)
                times.append(p['full_tm'] if is_us(market) else minute_key)
                prices.append(last_price)
                volumes.append(agg_vol)
                amounts.append(agg_amt)
                i = j
        elif is_overseas(market):
            # 港股/美股多日：Yahoo Finance 5分钟K线
            import os as _os2, datetime as _dt2
            from datetime import timezone as _tz, timedelta as _td
            _old_no2 = _os2.environ.pop('no_proxy', None)
            _old_NO2 = _os2.environ.pop('NO_PROXY', None)
            try:
                symbol = to_yahoo_symbol(code, market)
                _yh_tz = _tz(_td(hours=8)) if is_hk(market) else _tz(_td(hours=-5))  # HK UTC+8 / 美股 UTC-5

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
            # 多日：A股 新浪 5分钟K线（多日分时图新浪API仅支持 sh/sz）
            if not is_a_share(market):
                return jsonify({'success': False, 'error': '该市场暂不支持多日分时'})
            sina_prefix = 'sh' if str(market) in ('1', '2') else 'sz'
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
                    vol = adjust_volume(float(vol_v) if vol_v else 0, market)
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
    """股票K线（日K/周K/月K/分钟K线）"""
    import re, json, datetime as _dt
    code = request.args.get('code', '')
    market = request.args.get('market', '')
    period = request.args.get('period', 'day')  # day / week / month / 1min / 5min / 15min / 30min / 60min / 120min
    if not code or not market:
        return jsonify({'success': False, 'error': '缺少参数'})
    try:
        rows = []

        # 分钟K线：A股 1min→东财，5/15/30/60min→新浪，120min→新浪60min合成，港股美股→Yahoo
        _SINA_SCALE = {'5min': 5, '15min': 15, '30min': 30, '60min': 60}
        _SINA_DATALEN = {'5min': 240, '15min': 240, '30min': 240, '60min': 240}
        _YAHOO_RANGE_INTV = {
            '1min': ('5d', '1m'), '5min': ('1mo', '5m'),
            '15min': ('1mo', '15m'), '30min': ('3mo', '30m'),
            '60min': ('3mo', '60m'), '120min': ('6mo', '2h'),
        }
        if period in ('1min', '5min', '15min', '30min', '60min', '120min'):
            yh_range, yh_intv = _YAHOO_RANGE_INTV[period]
            # A股 1min → 东财push2delay（固定240条，刚好1天，够用且快）
            if is_a_share(market) and period == '1min':
                url = "https://push2delay.eastmoney.com/api/qt/stock/kline/get"
                params = {
                    'secid': f"{to_em_market(market)}.{code}",
                    'klt': '1',
                    'fqt': '1', 'beg': '0', 'end': '20500101', 'lmt': '240',
                    'fields1': 'f1,f2,f3,f4,f5,f6',
                    'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
                }
                r = requests.get(url, params=params,
                    headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://quote.eastmoney.com/'},
                    timeout=10, proxies=REQUEST_PROXIES)
                d = r.json()
                klines = (d.get('data') or {}).get('klines') or []
                tz_cn = _dt.timezone(_dt.timedelta(hours=8))
                for line in klines:
                    parts = line.split(',')
                    if len(parts) < 6:
                        continue
                    dt_str = parts[0]
                    o = float(parts[1]) if parts[1] else 0
                    c = float(parts[2]) if parts[2] else 0
                    h = float(parts[3]) if parts[3] else 0
                    l = float(parts[4]) if parts[4] else 0
                    vol = int(float(parts[5]) if parts[5] else 0)
                    amt = float(parts[6]) if len(parts) > 6 and parts[6] else 0
                    if c <= 0:
                        continue
                    if o <= 0: o = c
                    if h <= 0: h = c
                    if l <= 0: l = c
                    dt_obj = _dt.datetime.strptime(dt_str, '%Y-%m-%d %H:%M').replace(tzinfo=tz_cn)
                    rows.append({
                        'time': int(dt_obj.timestamp()),
                        'open': o, 'close': c,
                        'high': h, 'low': l,
                        'volume': vol * 100,
                        'amount': amt,
                        'turnover': round(float(parts[10]) if len(parts) > 10 and parts[10] else 0, 2),
                    })
            # A股 5/15/30/60min → 新浪
            elif market in SINA_PREFIX and period in _SINA_SCALE:
                sina_sym = SINA_PREFIX[market] + code
                sina_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_sym}&scale={_SINA_SCALE[period]}&ma=no&datalen={_SINA_DATALEN[period]}"
                r_sina = requests.get(sina_url,
                    headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'},
                    timeout=10, proxies=REQUEST_PROXIES)
                d_sina = r_sina.json()
                if not d_sina or not isinstance(d_sina, list):
                    return jsonify({'success': False, 'error': '暂无分钟K线数据'})
                tz_cn = _dt.timezone(_dt.timedelta(hours=8))
                for bar in d_sina:
                    dt_str = bar.get('day', '')
                    if not dt_str:
                        continue
                    o = float(bar.get('open') or 0)
                    c = float(bar.get('close') or 0)
                    h = float(bar.get('high') or 0)
                    l = float(bar.get('low') or 0)
                    vol = int(float(bar.get('volume') or 0))
                    if c <= 0:
                        continue
                    if o <= 0: o = c
                    if h <= 0: h = c
                    if l <= 0: l = c
                    dt_obj = _dt.datetime.strptime(dt_str[:16], '%Y-%m-%d %H:%M').replace(tzinfo=tz_cn)
                    rows.append({
                        'time': int(dt_obj.timestamp()),
                        'open': o, 'close': c,
                        'high': h, 'low': l,
                        'volume': vol,
                        'amount': 0,
                    })
            # A股 120min → 新浪 60min 两两合并合成
            elif market in SINA_PREFIX and period == '120min':
                sina_sym = SINA_PREFIX[market] + code
                sina_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_sym}&scale=60&ma=no&datalen=480"
                r_sina = requests.get(sina_url,
                    headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'},
                    timeout=10, proxies=REQUEST_PROXIES)
                d_sina = r_sina.json()
                if not d_sina or not isinstance(d_sina, list) or len(d_sina) < 2:
                    return jsonify({'success': False, 'error': '暂无120分钟K线数据'})
                tz_cn = _dt.timezone(_dt.timedelta(hours=8))
                bars_60 = []
                for bar in d_sina:
                    dt_str = bar.get('day', '')
                    if not dt_str:
                        continue
                    o = float(bar.get('open') or 0)
                    c = float(bar.get('close') or 0)
                    h = float(bar.get('high') or 0)
                    l = float(bar.get('low') or 0)
                    vol = int(float(bar.get('volume') or 0))
                    if c <= 0:
                        continue
                    if o <= 0: o = c
                    if h <= 0: h = c
                    if l <= 0: l = c
                    dt_obj = _dt.datetime.strptime(dt_str[:16], '%Y-%m-%d %H:%M').replace(tzinfo=tz_cn)
                    bars_60.append({'time': int(dt_obj.timestamp()), 'open': o, 'close': c, 'high': h, 'low': l, 'volume': vol})
                i = 0
                while i + 1 < len(bars_60):
                    t1, t2 = bars_60[i]['time'], bars_60[i + 1]['time']
                    if t2 - t1 > 5400:
                        i += 1
                        continue
                    rows.append({
                        'time': t1,
                        'open': bars_60[i]['open'],
                        'close': bars_60[i + 1]['close'],
                        'high': max(bars_60[i]['high'], bars_60[i + 1]['high']),
                        'low': min(bars_60[i]['low'], bars_60[i + 1]['low']),
                        'volume': bars_60[i]['volume'] + bars_60[i + 1]['volume'],
                        'amount': 0,
                    })
                    i += 2
            elif is_overseas(market):
                # 港股/美股用 Yahoo Finance 分钟K线
                import os as _os
                _old_no = _os.environ.pop('no_proxy', None)
                _old_NO = _os.environ.pop('NO_PROXY', None)
                try:
                    symbol = to_yahoo_symbol(code, market)
                    yh_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range={yh_range}&interval={yh_intv}"
                    r_yh = requests.get(yh_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
                    result = (r_yh.json().get('chart', {}).get('result') or [None])[0]
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
                        rows.append({
                            'time': int(ts),
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
                return jsonify({'success': False, 'error': '暂不支持该市场分钟K线'})
            rows.sort(key=lambda r: r['time'])
            return jsonify({'success': True, 'data': {'name': code, 'code': code, 'market': market, 'klines': rows, 'isMinuteKline': True}})

        tx_period = {'day': 'day', 'week': 'week', 'month': 'month'}.get(period, 'day')
        yh_intv = {'day': '1d', 'week': '1wk', 'month': '1mo'}.get(period, '1d')

        # 债券（沪债 11xxxx / 深债 12xxxx）用新浪 K 线 API，同花顺不支持债券
        if code[:2] in ('11', '12'):
            _SINA_SCALE_BOND = {'day': 240, 'week': 1200, 'month': 6000}
            sina_scale = _SINA_SCALE_BOND.get(period, 240)
            sina_prefix = SINA_PREFIX.get(str(market), 'sz')
            sina_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_prefix}{code}&scale={sina_scale}&ma=no&datalen=800"
            r_sina = requests.get(sina_url,
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'},
                timeout=10, proxies=REQUEST_PROXIES)
            d_sina = r_sina.json()
            if d_sina and isinstance(d_sina, list):
                for bar in d_sina:
                    dt_str = bar.get('day', '')
                    if not dt_str:
                        continue
                    o = float(bar.get('open') or 0)
                    c = float(bar.get('close') or 0)
                    h = float(bar.get('high') or 0)
                    l = float(bar.get('low') or 0)
                    vol = int(float(bar.get('volume') or 0))
                    if c <= 0:
                        continue
                    if o <= 0: o = c
                    if h <= 0: h = c
                    if l <= 0: l = c
                    rows.append({
                        'time': dt_str,
                        'open': o, 'close': c,
                        'high': h, 'low': l,
                        'volume': vol,
                        'amount': 0,
                    })
            rows.sort(key=lambda r: r['time'])
        elif str(market) == '2':
            # 北交所 K 线：同花顺不支持，走新浪
            _SINA_SCALE = {'day': 240, 'week': 1200, 'month': 6000}
            sina_scale = _SINA_SCALE.get(period, 240)
            sina_prefix = SINA_PREFIX.get('2', 'bj')
            sina_url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sina_prefix}{code}&scale={sina_scale}&ma=no&datalen=800"
            r_sina = requests.get(sina_url,
                headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'},
                timeout=10, proxies=REQUEST_PROXIES)
            d_sina = r_sina.json()
            if d_sina and isinstance(d_sina, list):
                for bar in d_sina:
                    dt_str = bar.get('day', '')
                    if not dt_str:
                        continue
                    o = float(bar.get('open') or 0)
                    c = float(bar.get('close') or 0)
                    h = float(bar.get('high') or 0)
                    l = float(bar.get('low') or 0)
                    vol = int(float(bar.get('volume') or 0))
                    if c <= 0:
                        continue
                    if o <= 0: o = c
                    if h <= 0: h = c
                    if l <= 0: l = c
                    rows.append({
                        'time': dt_str,
                        'open': o, 'close': c,
                        'high': h, 'low': l,
                        'volume': vol,
                        'amount': 0,
                    })
            rows.sort(key=lambda r: r['time'])
        elif is_a_share(market):
            # A 股日/周/月K：优先读本地 K 线库（stock_klines），缺失年份才向同花顺请求，
            # 拉到的数据回写库，下次直接读库。交易日当天/当周/当月的未完结K线不入库。
            import time as _time
            from chinese_calendar import is_workday
            from market_db.db import klines_years, klines_get_by_years, stock_info_get, stock_info_sync_atomic, market_get
            from market_db.sync import _code_to_segment

            # seg_key 按"代码前缀"归类，与 sync.py 写库时一致。不能用 _MARKET_TO_SEG[market]，
            # 因为前端 market 代码对 ETF/创业/科创 与 sync.py 分段不一致（如 159xxx 前端 market='0' 但属 hs_etf）
            seg_key = _code_to_segment(code)

            db_period = {'day': 'daily', 'week': 'weekly', 'month': 'monthly'}[period]
            ths_period_code = {'day': '01', 'week': '11', 'month': '21'}[period]
            current_year = _dt.datetime.now().year
            today = _dt.date.today()
            today_str = today.strftime('%Y%m%d')
            today_is_trading = is_workday(today)
            # 最近交易日（从今天往前找第一个 is_workday）
            _d = today
            while not is_workday(_d):
                _d = _d - _dt.timedelta(days=1)
            latest_trading = _d.strftime('%Y%m%d')

            # 市场是否已在技术选股页加载（stock_market 有记录）；seg_key 为空（如北交所）或未加载时不读/写库
            market_loaded = bool(seg_key) and market_get(seg_key) is not None

            ths_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.10jqka.com.cn/',
            }
            ths_prefix = THS_PREFIX.get(str(market), 'sh')

            # 单年份拉取：失败重试（同一数据源，非多源兜底）。
            # 返回 None 表示请求失败（需重试）；返回 '' 表示该年份确实无数据（正常跳过）。
            # 404 也视为该年无数据（如 ETF 上市前的年份），返回 ''。
            def _fetch_year(y, retries=3):
                url = f"https://d.10jqka.com.cn/v4/line/{ths_prefix}_{code}/{ths_period_code}/{y}.js"
                last_err = None
                for attempt in range(retries + 1):
                    try:
                        r = requests.get(url, headers=ths_headers, timeout=10, proxies=REQUEST_PROXIES)
                        if r.status_code == 404:
                            return ''
                        if r.status_code == 200:
                            text = r.text
                            s = text.find('(') + 1; e = text.rfind(')')
                            if s > 0 and e > s:
                                jd = json.loads(text[s:e])
                                return jd.get('data', '')
                            last_err = '响应格式异常'
                        else:
                            last_err = f'HTTP {r.status_code}'
                    except Exception as ex:
                        last_err = str(ex)
                    # 失败统一退避后再重试（502/504/格式异常/网络异常都走这里）
                    if attempt < retries:
                        _time.sleep(0.3)
                print(f'[stock-kline] {code} {period} 年份 {y} 拉取失败: {last_err}')
                return None

            # 解析同花顺年文件 raw 字符串 → [{date, open, high, low, close, volume, amount, turnover}]
            def _parse_year_raw(raw):
                out = []
                seen = set()
                for line in raw.split(';'):
                    parts = line.split(',')
                    if len(parts) < 8:
                        continue
                    d = parts[0]
                    if d in seen:
                        continue
                    seen.add(d)
                    c = float(parts[4]) if parts[4] else 0
                    if c <= 0:
                        continue
                    o = float(parts[1]) if parts[1] else 0
                    h = float(parts[2]) if parts[2] else 0
                    l = float(parts[3]) if parts[3] else 0
                    # 开/高/低为空或为 0 时，用收盘价补上（同花顺当天可能只有收盘价）
                    if o <= 0:
                        o = c
                    if h <= 0:
                        h = c
                    if l <= 0:
                        l = c
                    out.append({
                        'date': d,
                        'open': o, 'high': h, 'low': l, 'close': c,
                        'volume': int(float(parts[5]) if parts[5] else 0),
                        'amount': float(parts[6]) if parts[6] else 0,
                        'turnover': round(float(parts[7]) if parts[7] else 0, 2),
                    })
                return out

            # 判断某条K线是否属于当前未完结周期（仅当年文件、今天交易日时为 True）
            def _is_unfinished(d_str):
                if not today_is_trading:
                    return False
                if db_period == 'daily':
                    return d_str == today_str
                if db_period == 'weekly':
                    k_iso = _dt.datetime.strptime(d_str, '%Y%m%d').isocalendar()[:2]
                    return k_iso == today.isocalendar()[:2]
                if db_period == 'monthly':
                    return d_str[:6] == today_str[:6]
                return False

            # 1. 查库已有年份（市场未加载时库本就空，跳过查询）
            have_years = klines_years(code, seg_key, db_period) if market_loaded else set()
            # 库里最早年份：早于它的年份是上市前（无数据），不再重复请求
            min_year = min((int(y) for y in have_years), default=None)

            # 2. 历史缺失年份（< 当年）需拉取；当年按交易日判断是否需刷新
            target_years = list(range(current_year, current_year - 10, -1))
            miss_hist = [y for y in target_years
                         if y < current_year and str(y) not in have_years
                         and (min_year is None or y >= min_year)]

            info = stock_info_get(code, seg_key) if market_loaded else None
            ts_col = {'daily': 'daily_ts', 'weekly': 'weekly_ts', 'monthly': 'monthly_ts'}[db_period]
            last_ts = (info or {}).get(ts_col) or ''
            last_ts_date = last_ts[:10].replace('-', '') if last_ts else ''
            # 市场未加载 → 总拉当年取实时K线；今天交易日 → 总拉当年；否则仅当落后于最近交易日才拉
            if not market_loaded or today_is_trading:
                need_current = True
            else:
                need_current = last_ts_date < latest_trading

            years_to_fetch = miss_hist + ([current_year] if need_current else [])

            # 3. 拉取缺失年份 + 当年（若需要）
            fetched = {}  # {year: [parsed rows]}
            for y in years_to_fetch:
                raw = _fetch_year(y)
                if raw is None:
                    # 该年份请求失败（重试耗尽），数据已不完整，整体返回失败，避免把残缺K线给前端
                    return jsonify({'success': False, 'error': f'年份 {y} K线拉取失败，请稍后重试'})
                if raw:
                    fetched[y] = _parse_year_raw(raw)
                _time.sleep(0.1)  # 串行间隔，避免同花顺限流

            # 4. 回写库（仅当市场已加载）：剔除未完结周期后入库 + 更新 stock_info 时间戳
            if market_loaded:
                new_rows = []
                for y, parsed in fetched.items():
                    for p in parsed:
                        if _is_unfinished(p['date']):
                            continue
                        new_rows.append((code, seg_key, db_period, p['date'],
                                         p['open'], p['high'], p['low'], p['close'],
                                         p['volume'], p['amount'], p['turnover']))
                if new_rows:
                    period_dates = {db_period: _dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    stock_info_sync_atomic(code, seg_key, None, new_rows, period_dates)

            # 5. 组装返回
            def _row_from(p):
                d = p['date']
                return {
                    'time': d[:4] + '-' + d[4:6] + '-' + d[6:8],
                    'open': p['open'], 'close': p['close'],
                    'high': p['high'], 'low': p['low'],
                    'volume': p['volume'],
                    'amount': p['amount'],
                    'turnover': p['turnover'],
                }

            if market_loaded:
                # 读库（已含历史已有 + 本次新入的已完结数据）
                read_years = {str(y) for y in target_years}
                db_dates = set()
                for k in klines_get_by_years(code, seg_key, db_period, read_years):
                    d = k['date']
                    db_dates.add(d)
                    rows.append({
                        'time': d[:4] + '-' + d[4:6] + '-' + d[6:8],
                        'open': k['open'], 'close': k['close'],
                        'high': k['high'], 'low': k['low'],
                        'volume': int(k['volume']),
                        'amount': k['amount'],
                        'turnover': k['turnover'],
                    })
                # 补本次拉到的未完结K线（今天/本周/本月，不入库但返回前端）
                # 仅当今天交易日且已开盘才补；库里已有该日期则跳过（避免与 sync 写入重复）
                if current_year in fetched and today_is_trading and is_market_opened(market):
                    for p in fetched[current_year]:
                        if _is_unfinished(p['date']) and p['date'] not in db_dates:
                            rows.append(_row_from(p))
            else:
                # 市场未加载：直接用本次拉取的数据返回（不写库）
                for y in sorted(fetched.keys()):
                    for p in fetched[y]:
                        # 跳过今天未开盘的假K线（保留原行为）
                        if p['date'] == today_str and not is_market_opened(market):
                            continue
                        rows.append(_row_from(p))
            rows.sort(key=lambda r: r['time'])
        elif is_overseas(market):
            # 港股/美股 → 本地 DB（由 sync 提前拉取），无缓存时再走 Yahoo
            from market_db.db import klines_get
            db_rows = klines_get(code, market, tx_period, limit=800)
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
                    symbol = to_yahoo_symbol(code, market)
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

@app.route('/api/technical/strategies')
def technical_strategies():
    """返回可用策略列表"""
    return jsonify({'success': True, 'data': get_strategies()})

@app.route('/api/technical/ascending-channel', methods=['POST'])
def technical_ascending_channel_start():
    """启动扫描（strategy 支持逗号分隔多个策略，如 strategy=ascending_channel,extreme_shrink_doji）"""
    market = request.args.get('market', '')
    strategy_raw = request.args.get('strategy', '')
    strategy_keys = [s.strip() for s in strategy_raw.split(',') if s.strip()]
    result = run_scan_async(strategy_keys, market=market)
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

@app.route('/api/market-db/update/<seg_key>', methods=['POST'])
def market_db_update(seg_key):
    from market_db.sync import update_market
    result = update_market(seg_key)
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
    from market_db.db import stock_list_all, stock_info_all
    list_count = len(stock_list_all())
    kline_count = len(stock_info_all())
    return jsonify({'list_stocks': list_count, 'detail_stocks': kline_count})


# ==================== 交易日历 ====================

@app.route('/api/is-trading-day')
def is_trading_day():
    """判断今天是否为A股交易日（排除周末和法定节假日）"""
    import datetime as _dt
    today = _dt.date.today()
    try:
        from chinese_calendar import is_workday
        result = is_workday(today)
    except ImportError:
        result = today.weekday() < 5
    return jsonify({'date': today.isoformat(), 'is_trading_day': result})


@app.route('/api/trading-days')
def trading_days():
    """返回最近N个A股交易日（排除周末和法定节假日）"""
    import datetime as _dt
    from chinese_calendar import is_workday
    count = request.args.get('count', 15, type=int)

    dates = []
    d = _dt.date.today()
    while len(dates) < count:
        if is_workday(d):
            dates.append(d.isoformat())
        d = d - _dt.timedelta(days=1)
    dates.reverse()
    return jsonify({'success': True, 'data': {'trading_days': dates}})


# ==================== 公司公告 ====================


def _collect_target_codes():
    """收集自选股+持仓股+选股代码"""
    wl_rows = get_all(g.user_id)
    wl_codes = {r[0] for r in wl_rows}
    holdings_rows = holdings_get_all(g.user_id)
    holdings_codes = {r[0] for r in holdings_rows}
    pick_codes_raw = request.args.get('codes', '').split(',')
    pick_codes = {c.strip() for c in pick_codes_raw if c.strip()}
    return wl_codes | holdings_codes | pick_codes


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
                code_val = code_info.get('stock_code', '')
                result.append({
                    'code': code_val,
                    'market': guess_market(code_val),
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


# ==================== 业绩披露 ====================

def _stock_f10_url(code):
    """根据股票代码构造东方财富F10链接"""
    prefix = 'SH' if code.startswith(('6', '9')) else 'SZ'
    return f'https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code={prefix}{code}&color=r'


def _report_period_type(date_str):
    """根据报告期日期返回类型：2025年年报/2026年一季报 等"""
    if not date_str:
        return ''
    d = str(date_str)[:10]
    year = d[:4] if len(d) >= 4 else ''
    if '-12-31' in d:
        return f'{year}年年报'
    if '-06-30' in d:
        return f'{year}年半年报'
    if '-03-31' in d:
        return f'{year}年一季报'
    if '-09-30' in d:
        return f'{year}年三季报'
    return ''


@app.route('/api/earnings')
def earnings_list():
    """获取自选股+选股列表中股票的业绩报告（东方财富：业绩预告 + 业绩快报 + 业绩报表）"""
    try:
        target_codes = _collect_target_codes()
        if not target_codes:
            return jsonify({'success': True, 'data': []})

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://data.eastmoney.com/',
        }
        code_list_str = ','.join(f'"{c}"' for c in sorted(target_codes))

        from datetime import datetime as _dt
        this_year = _dt.now().year
        # 覆盖最近 3 个完整财年（当年 + 前两年）
        start_year = this_year - 2
        cutoff = f'{start_year}-01-01'
        rpt_dates = []
        for y in range(start_year, this_year + 1):
            for md in ('03-31', '06-30', '09-30', '12-31'):
                rpt_dates.append(f'{y}-{md}')
        rpt_dates_str = ','.join(f'"{d}"' for d in rpt_dates)

        result = []

        # ① 业绩预告
        params1 = {
            'reportName': 'RPT_PUBLIC_OP_NEWPREDICT',
            'columns': 'SECURITY_CODE,SECURITY_NAME_ABBR,NOTICE_DATE,REPORT_DATE,PREDICT_TYPE,PREDICT_AMT_LOWER,PREDICT_AMT_UPPER,PREYEAR_SAME_PERIOD,PREDICT_CONTENT',
            'filter': f'(SECURITY_CODE in ({code_list_str}))',
            'pageSize': 500,
            'pageNumber': 1,
            'sortColumns': 'NOTICE_DATE',
            'sortTypes': '-1',
        }
        r1 = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get',
                         params=params1, headers=headers, timeout=15, proxies=REQUEST_PROXIES)
        data1 = r1.json()
        items1 = (data1.get('result') or {}).get('data') or []

        # 过滤掉"每股收益"行；同(code,report_date)只保留一条
        seen = set()
        for item in items1:
            code = str(item.get('SECURITY_CODE', ''))
            if code not in target_codes:
                continue
            notice_date = (str(item.get('NOTICE_DATE') or ''))[:10]
            if not notice_date or notice_date < cutoff:
                continue
            report_date = (str(item.get('REPORT_DATE') or ''))[:10]
            if not report_date or report_date < cutoff:
                continue
            content = str(item.get('PREDICT_CONTENT') or '')
            key = (code, report_date)
            if key in seen:
                continue
            # 跳过每股收益(EPS)类预告
            if '每股收益' in content:
                continue
            seen.add(key)
            period = _report_period_type(report_date)
            result.append({
                'code': code,
                'market': guess_market(code),
                'name': str(item.get('SECURITY_NAME_ABBR') or ''),
                'row_type': '业绩预告',
                'sub_type': str(item.get('PREDICT_TYPE') or ''),
                'notice_date': notice_date,
                'report_date': report_date,
                'period': period,
                'profit_lower': item.get('PREDICT_AMT_LOWER'),
                'profit_upper': item.get('PREDICT_AMT_UPPER'),
                'last_profit': item.get('PREYEAR_SAME_PERIOD'),
                'content': content,
                'detail_url': _stock_f10_url(code) + '#/yjyg',
            })

        # ② 业绩快报
        params2 = {
            'reportName': 'RPT_FCI_PERFORMANCEE',
            'columns': 'SECURITY_CODE,SECURITY_NAME_ABBR,REPORT_DATE,UPDATE_DATE,BASIC_EPS,PARENT_NETPROFIT,TOTAL_OPERATE_INCOME,YSTZ,JLRTBZCL',
            'filter': f'(SECURITY_CODE in ({code_list_str})) AND (REPORT_DATE in ({rpt_dates_str}))',
            'pageSize': 500,
            'pageNumber': 1,
            'sortColumns': 'UPDATE_DATE',
            'sortTypes': '-1',
        }
        r2 = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get',
                         params=params2, headers=headers, timeout=15, proxies=REQUEST_PROXIES)
        data2 = r2.json()
        items2 = (data2.get('result') or {}).get('data') or []

        seen2 = set()
        for item in items2:
            code = str(item.get('SECURITY_CODE', ''))
            if code not in target_codes:
                continue
            update_date = (str(item.get('UPDATE_DATE') or ''))[:10]
            if not update_date:
                continue
            report_date = (str(item.get('REPORT_DATE') or ''))[:10]
            if report_date < cutoff:
                continue
            key = (code, report_date)
            if key in seen2:
                continue
            seen2.add(key)
            period = _report_period_type(report_date)
            result.append({
                'code': code,
                'market': guess_market(code),
                'name': str(item.get('SECURITY_NAME_ABBR') or ''),
                'row_type': '业绩快报',
                'sub_type': period,
                'notice_date': update_date,
                'report_date': report_date,
                'period': period,
                'eps': item.get('BASIC_EPS'),
                'profit': item.get('PARENT_NETPROFIT'),
                'revenue': item.get('TOTAL_OPERATE_INCOME'),
                'revenue_yoy': item.get('YSTZ'),
                'profit_yoy': item.get('JLRTBZCL'),
                'detail_url': _stock_f10_url(code) + '#/cwfx',
            })

        # ③ 业绩报表
        params3 = {
            'reportName': 'RPT_LICO_FN_CPD',
            'columns': 'SECURITY_CODE,SECURITY_NAME_ABBR,REPORTDATE,UPDATE_DATE,BASIC_EPS,PARENT_NETPROFIT,TOTAL_OPERATE_INCOME,YSTZ,SJLTZ',
            'filter': f'(SECURITY_CODE in ({code_list_str})) AND (REPORTDATE in ({rpt_dates_str}))',
            'pageSize': 500,
            'pageNumber': 1,
            'sortColumns': 'REPORTDATE',
            'sortTypes': '-1',
        }
        r3 = requests.get('https://datacenter-web.eastmoney.com/api/data/v1/get',
                         params=params3, headers=headers, timeout=15, proxies=REQUEST_PROXIES)
        data3 = r3.json()
        items3 = (data3.get('result') or {}).get('data') or []

        seen3 = set()
        for item in items3:
            code = str(item.get('SECURITY_CODE', ''))
            if code not in target_codes:
                continue
            reportdate = (str(item.get('REPORTDATE') or ''))[:10]
            if not reportdate or reportdate < cutoff:
                continue
            key = (code, reportdate)
            if key in seen3:
                continue
            seen3.add(key)
            update_date = (str(item.get('UPDATE_DATE') or ''))[:10]
            period = _report_period_type(reportdate)
            result.append({
                'code': code,
                'market': guess_market(code),
                'name': str(item.get('SECURITY_NAME_ABBR') or ''),
                'row_type': '业绩报表',
                'sub_type': period,
                'notice_date': update_date,
                'report_date': reportdate,
                'period': period,
                'eps': item.get('BASIC_EPS'),
                'profit': item.get('PARENT_NETPROFIT'),
                'revenue': item.get('TOTAL_OPERATE_INCOME'),
                'revenue_yoy': item.get('YSTZ'),
                'profit_yoy': item.get('SJLTZ'),
                'detail_url': _stock_f10_url(code) + '#/cwfx',
            })

        # 按股票分组排序（同股票聚在一起，按最新报告期降序），组内按报告期降序
        from collections import defaultdict
        groups = defaultdict(list)
        for r_item in result:
            groups[r_item['code']].append(r_item)
        sorted_codes = sorted(groups, key=lambda c: max(r['report_date'] for r in groups[c]), reverse=True)
        result = []
        for code in sorted_codes:
            result.extend(sorted(groups[code], key=lambda r: r['report_date'], reverse=True))

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"获取业绩披露失败: {e}")
        return jsonify({'success': False, 'error': str(e)})


# ==================== 异动中心 ====================

@app.route('/api/abnormal/prediction')
def abnormal_prediction():
    """异动预测：接近异常波动阈值的股票"""
    return jsonify(get_prediction())

@app.route('/api/abnormal/monitor')
def abnormal_monitor():
    """异动监控：已被交易所重点监控的股票"""
    return jsonify(get_monitor())

@app.route('/api/abnormal/analyze', methods=['POST'])
def abnormal_analyze():
    """异动分析器：单只股票异常分析"""
    code = request.form.get('code', '').strip()
    market = request.form.get('market', '').strip()
    return jsonify(analyze_stock(code, market))


# ==================== 公共秒级调度器 ====================
# 统一秒级定时器：每秒 tick 一次，依次调用所有已注册的检测函数。
# 后续任何需要定时执行的逻辑，只需写一个"检测一次"的函数并 register_scheduler_check 注册，
# 无需再为每个定时功能单独开线程。

import threading
import time

_scheduler_checks = []


def register_scheduler_check(fn):
    """注册一个定时检测函数。调度器每秒调用一次该函数。"""
    _scheduler_checks.append(fn)


def _scheduler_loop():
    """公共秒级定时器：每秒 sleep 一次，依次执行所有注册的检测函数"""
    while True:
        time.sleep(1)
        for fn in _scheduler_checks:
            try:
                fn()
            except Exception as e:
                print(f'[scheduler] 检测函数 {fn.__name__} 异常: {type(e).__name__}: {e}')


def start_scheduler():
    """启动公共秒级调度器守护线程，并注册所有内置定时检测"""
    register_scheduler_check(init_market_db_update())  # K线库每日自动更新检测
    register_scheduler_check(init_longhu_bang_update())      # 龙虎榜库每日跨天清理检测
    threading.Thread(target=_scheduler_loop, daemon=True, name='scheduler').start()
    print('[scheduler] 公共秒级调度器已启动')


# ==================== 启动 ====================

if __name__ == '__main__':
    start_major_indices_poller()  # 启动后台指数行情轮询
    start_scheduler()             # 启动公共秒级调度器
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5000)
