/* 热股榜 — 同花顺热榜数据加载与渲染（按日期切换，切换榜单时请求一次） */

var _hotstockBangPeriod = 'hour';     // hour=1小时榜 / day=24小时榜
var _hotstockBangListType = 'normal'; // normal/skyrocket/new_stock/tech/value/trend
var _hotstockBangDate = '';           // 当前选中日期（自然日，默认今天）
var _hotstockBangDateList = null;     // 最近30个自然日
var _hotstockBangInitialized = false;

var _HOURLY_TYPES = ['normal', 'skyrocket'];

// ==================== 日期栏 ====================

async function fetchHotstockBangDates() {
    var res = await fetch('/api/hotstock-bang-dates?count=30');
    var result = await res.json();
    _hotstockBangDateList = result.data.dates;
    return _hotstockBangDateList;
}

function renderHotstockBangDateBar(activeDate) {
    var bar = document.getElementById('hotstockBangDateBar');
    if (!bar || !_hotstockBangDateList) return;
    var html = '';
    for (var i = 0; i < _hotstockBangDateList.length; i++) {
        var date = _hotstockBangDateList[i];
        var mmdd = date.slice(5);  // "MM-DD"
        var cls = (date === activeDate) ? 'lhb-date-btn active' : 'lhb-date-btn';
        html += '<span class="' + cls + '" onclick="selectHotstockBangDate(\'' + date + '\')">' + mmdd + '</span>';
    }
    bar.innerHTML = html;
}

function selectHotstockBangDate(date) {
    if (_hotstockBangDate === date) return;
    _hotstockBangDate = date;
    renderHotstockBangDateBar(date);
    loadHotstockBang();
}

async function initHotstockBang() {
    if (_hotstockBangInitialized) return;
    _hotstockBangInitialized = true;
    _hotstockBangDateList = await fetchHotstockBangDates();
    _hotstockBangDate = _hotstockBangDateList[_hotstockBangDateList.length - 1];  // 默认最新自然日（今天）
    renderHotstockBangDateBar(_hotstockBangDate);
}

// ==================== 榜单 / 周期切换 ====================

function _syncHotstockBangTabs() {
    document.querySelectorAll('#page-hotstock-bang .hot-type-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-list-type') === _hotstockBangListType);
    });
    // 只有小时榜类型显示 1小时/24小时 切换
    var hourly = _HOURLY_TYPES.indexOf(_hotstockBangListType) >= 0;
    var periodTabs = document.getElementById('hotPeriodTabs');
    if (periodTabs) periodTabs.style.display = hourly ? '' : 'none';
    document.querySelectorAll('#page-hotstock-bang .hot-period-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-period') === _hotstockBangPeriod);
    });
}

function switchHotListType(listType) {
    if (_hotstockBangListType === listType) return;
    _hotstockBangListType = listType;
    _syncHotstockBangTabs();
    loadHotstockBang();
}

function switchHotstockBangPeriod(period) {
    if (_hotstockBangPeriod === period) return;
    _hotstockBangPeriod = period;
    _syncHotstockBangTabs();
    loadHotstockBang();
}

// ==================== 加载 ====================

function loadHotstockBang() {
    if (!_hotstockBangInitialized) {
        initHotstockBang().then(function() { _doLoadHotstockBang(); });
        return;
    }
    _doLoadHotstockBang();
}

function _doLoadHotstockBang() {
    var wrap = document.getElementById('hotstockBangList');
    wrap.innerHTML = '<div class="loading">加载中...</div>';

    var url = '/api/hotstock-bang?list_type=' + _hotstockBangListType
        + '&period=' + _hotstockBangPeriod
        + '&date=' + encodeURIComponent(_hotstockBangDate);
    fetch(url).then(function(r) { return r.json(); }).then(function(res) {
        if (!res.success) {
            wrap.innerHTML = '<div class="loading">' + (res.error || '加载失败') + '</div>';
            return;
        }
        if (res.empty) {
            wrap.innerHTML = '<div class="loading">暂无该日数据</div>';
            return;
        }
        renderHotstockBang(res.stocks);
    }).catch(function(e) {
        wrap.innerHTML = '<div class="loading">加载失败: ' + e + '</div>';
    });
}

// ==================== 渲染 ====================

function _hotFmtHeat(n) {
    if (n == null) return '-';
    if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿';
    if (n >= 1e4) return (n / 1e4).toFixed(1) + '万';
    return String(n);
}

function _hotFmtChg(v) {
    if (v == null) return { text: '-', cls: 'flat' };
    var n = parseFloat(v);
    var sign = n > 0 ? '+' : '';
    return { text: sign + n.toFixed(2) + '%', cls: n > 0 ? 'up' : (n < 0 ? 'down' : 'flat') };
}

function _hotFmtDate(s) {
    if (!s) return '';
    s = String(s);
    if (s.length === 8) return s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8);
    return s;
}

function _hotToggleAnalyse(el) {
    el.classList.toggle('expanded');
}

function _hotTagsHtml(s) {
    var html = '';
    if (s.popularity_tag) html += '<span class="hot-tag hot-tag-pop">' + s.popularity_tag + '</span>';
    if (s.analyse_title) html += '<span class="hot-tag hot-tag-title">' + s.analyse_title + '</span>';
    (s.concept_tags || []).forEach(function(t) {
        html += '<span class="hot-tag">' + t + '</span>';
    });
    return html;
}

function _hotNameHtml(s) {
    var name = (s.name || '').replace(/'/g, "\\'");
    return '<span class="hotstock-bang-name" onclick="KlinePopup.open(\'' + s.code + '\',\'' + guessMarket(s.code) + '\',\'' + name + '\')">' + s.name + '</span>';
}

function renderHotstockBang(stocks) {
    var wrap = document.getElementById('hotstockBangList');
    if (!stocks || !stocks.length) {
        wrap.innerHTML = '<div class="loading">暂无该日数据</div>';
        return;
    }

    // 缓存当前榜单，供技术面分析弹窗按 code 取数
    _hotstockBangCache = {};
    stocks.forEach(function(s) { _hotstockBangCache[s.code] = s; });

    var isNewStock = _hotstockBangListType === 'new_stock';
    var html = '';

    stocks.forEach(function(s) {
        var rank = s.rank || '';
        var rankCls = rank >= 1 && rank <= 3 ? ' hot-rank-' + rank : '';
        var tags = _hotTagsHtml(s);

        var line;
        var extra = '';
        if (isNewStock) {
            var pe = s.pe != null ? '<span class="hotstock-bang-pe">PE ' + s.pe + '</span>' : '';
            var date = s.order_date ? '<span class="hotstock-bang-meta">上市 ' + _hotFmtDate(s.order_date) + '</span>' : '';
            line = ''
                + _hotNameHtml(s)
                + '<span class="hotstock-bang-code">' + s.code + '</span>'
                + pe
                + '<span class="hotstock-bang-analyse-btn" onclick="HotstockBangAnalyse.open(\'' + s.code + '\', s)">异动分析</span>'
                + '<span class="hotstock-bang-analyse-btn" onclick="openHotstockBangDetail(\'' + s.code + '\')">热度详情</span>'
                + '<span class="hotstock-bang-heat"><i class="hot-fire">🔥</i>' + _hotFmtHeat(s.heat) + '热度</span>';
            extra = date ? '<div class="hotstock-bang-tags">' + date + '</div>' : '';
        } else {
            var chg = _hotFmtChg(s.change_pct);
            line = ''
                + _hotNameHtml(s)
                + '<span class="hotstock-bang-code">' + s.code + '</span>'
                + '<span class="hotstock-bang-chg ' + chg.cls + '">' + chg.text + '</span>'
                + '<span class="hotstock-bang-analyse-btn" onclick="HotstockBangAnalyse.open(\'' + s.code + '\', s)">异动分析</span>'
                + '<span class="hotstock-bang-analyse-btn" onclick="openHotstockBangDetail(\'' + s.code + '\')">热度详情</span>'
                + '<span class="hotstock-bang-heat"><i class="hot-fire">🔥</i>' + _hotFmtHeat(s.heat) + '热度</span>';
            extra = s.analyse
                ? '<div class="hotstock-bang-analyse expanded" onclick="_hotToggleAnalyse(this)" title="点击展开/收起">' + s.analyse + '</div>'
                : '';
        }

        html += ''
            + '<div class="hotstock-bang-item">'
            +   '<div class="hotstock-bang-rank' + rankCls + '">' + rank + '</div>'
            +   '<div class="hotstock-bang-main">'
            +     '<div class="hotstock-bang-line">' + line + '</div>'
            +     (tags ? '<div class="hotstock-bang-tags">' + tags + '</div>' : '')
            +     extra
            +   '</div>'
            + '</div>';
    });

    wrap.innerHTML = html;
}

// ==================== 技术面分析弹窗 ====================
// 榜单项「异动分析」按钮 → 弹窗显示技术面异动分析
var _hotstockBangCache = {};  // code -> 当前榜单 stock 对象

var HotstockBangAnalyse = (function() {
    var _overlay = null;
    var _activeCode = '';

    function _ensureDOM() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.id = 'hotstockBangAnalyseOverlay';
        _overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:200;justify-content:center;align-items:center;';
        _overlay.onclick = function(e) { if (e.target === _overlay) close(); };
        document.body.appendChild(_overlay);
    }

    function open(code, stock) {
        var s = stock;
        if (!s) return;
        _ensureDOM();
        _activeCode = code;

        var tags = _hotTagsHtml(s);
        var chg = _hotFmtChg(s.change_pct);

        _overlay.innerHTML =
            '<div style="width:600px;max-width:95vw;max-height:88vh;display:flex;flex-direction:column;background:#1e1e2e;border-radius:12px;overflow:hidden;box-shadow:0 8px 40px rgba(0,0,0,0.5);">' +
                '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:14px 18px 12px;background:#1a1a2e;flex-shrink:0;">' +
                    '<div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">' +
                        '<span style="font-size:18px;color:#fff;font-weight:600;">' + (s.name || '') + '</span>' +
                        '<span style="font-size:13px;color:#888;">' + s.code + '</span>' +
                        (s.change_pct != null ? '<span class="hotstock-bang-chg ' + chg.cls + '">' + chg.text + '</span>' : '') +
                        (s.heat != null ? '<span style="font-size:12px;color:#e0a94a;">🔥' + _hotFmtHeat(s.heat) + '热度</span>' : '') +
                    '</div>' +
                    '<span style="color:#666;font-size:20px;cursor:pointer;padding:0 4px;line-height:1;" onclick="HotstockBangAnalyse.close()">✕</span>' +
                '</div>' +
                '<div class="hotstock-bang-analyse-body" style="padding:14px 18px;overflow-y:auto;flex:1;">' +
                    (tags ? '<div class="hotstock-bang-tags" style="margin-top:0;">' + tags + '</div>' : '') +
                    '<div style="margin-top:16px;border-top:1px solid #2a2a4e;padding-top:12px;">' +
                        '<div style="font-size:13px;color:#6bb1ff;margin-bottom:10px;">📊 技术面异动分析</div>' +
                        '<div id="hotstockBangAnalyseTech" style="color:#8b8b9e;font-size:13px;">加载中...</div>' +
                    '</div>' +
                '</div>' +
            '</div>';
        _overlay.style.display = 'flex';

        _loadTech(code);
    }

    function _loadTech(code) {
        var el = document.getElementById('hotstockBangAnalyseTech');
        if (!el) return;
        var formData = new FormData();
        formData.append('code', code);
        formData.append('market', guessMarket(code));
        fetch('/api/abnormal/analyze', { method: 'POST', body: formData })
            .then(function(r) { return r.json(); })
            .then(function(resp) {
                if (code !== _activeCode) return;
                if (!resp.success || !resp.data) {
                    el.innerHTML = '<div style="color:#8b8b9e;">' + (resp.error || '暂无分析数据') + '</div>';
                    return;
                }
                el.innerHTML = _techHtml(resp.data);
            })
            .catch(function() {
                if (code !== _activeCode) return;
                el.innerHTML = '<div style="color:#ef5350;">分析请求失败</div>';
            });
    }

    function _techHtml(d) {
        var w = (d.regular_abnormal && d.regular_abnormal.window) || {};
        var lu = d.limit_up_projection || {};
        var cur = lu.current || {};

        function pct(v) {
            if (v == null) return '-';
            return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
        }
        function card(label, value, cls) {
            return '<div style="flex:1;min-width:0;">' +
                '<div style="font-size:11px;color:#8b8b9e;margin-bottom:2px;">' + label + '</div>' +
                '<div class="' + (cls || '') + '" style="font-size:14px;' + (cls ? '' : 'color:#ccc;') + '">' + value + '</div>' +
                '</div>';
        }
        function row(cells) {
            return '<div style="display:flex;gap:16px;margin-bottom:12px;">' + cells.join('') + '</div>';
        }

        var warnHtml = '';
        if (d.warnings && d.warnings.length) {
            warnHtml = '<div style="background:#2a1a1a;border:1px solid #e94560;border-radius:6px;padding:10px 12px;margin-bottom:12px;">' +
                '<div style="font-size:12px;color:#e94560;margin-bottom:4px;">⚠ 风险提示</div>' +
                d.warnings.map(function(w2) { return '<div style="font-size:12px;color:#ff9999;margin:2px 0;">• ' + w2 + '</div>'; }).join('') +
                '</div>';
        }

        return warnHtml +
            row([
                card('5日涨跌', pct(w.pct_5d), w.pct_5d >= 0 ? 'change-up' : 'change-down'),
                card('10日涨跌', pct(w.pct_10d), w.pct_10d >= 0 ? 'change-up' : 'change-down'),
                card('20日涨跌', pct(w.pct_20d), w.pct_20d >= 0 ? 'change-up' : 'change-down'),
                card('20日振幅', w.amplitude_20d != null ? w.amplitude_20d.toFixed(2) + '%' : '-')
            ]) +
            row([
                card('偏离10日线', pct(cur.deviation_10d), cur.deviation_10d >= 0 ? 'change-up' : 'change-down'),
                card('偏离30日线', pct(cur.deviation_30d), cur.deviation_30d >= 0 ? 'change-up' : 'change-down'),
                card('20日高点回撤', w.drawdown_20d != null ? w.drawdown_20d.toFixed(2) + '%' : '-'),
                card('连续' + (w.consecutive_dir === 'up' ? '上涨' : '下跌'), w.consecutive_days != null ? w.consecutive_days + '天' : '-', w.consecutive_dir === 'up' ? 'change-up' : 'change-down')
            ]) +
            row([
                card('10日均价', w.ma10 != null ? w.ma10.toFixed(2) : '-'),
                card('30日均价', w.ma30 != null ? w.ma30.toFixed(2) : '-'),
                card('涨停价', lu.limit_up_price != null ? lu.limit_up_price.toFixed(2) : '-', 'change-up'),
                card('跌停价', lu.limit_down_price != null ? lu.limit_down_price.toFixed(2) : '-', 'change-down')
            ]);
    }

    function close() {
        if (_overlay) _overlay.style.display = 'none';
        _activeCode = '';
    }

    return { open: open, close: close };
})();

// ==================== 热度详情 ====================
// 点击打开同花顺热度详情页（ms.10jqka.com.cn/thsHotDetail）

function _thsMarketCode(code) {
    var m = guessMarket(code);
    if (m === '1') return '17';   // 沪市（含科创板）
    if (m === '2') return '151';  // 北交所
    return '33';                   // 深市
}

function openHotstockBangDetail(code) {
    var s = _hotstockBangCache[code];
    if (!s) return;
    var url = 'https://ms.10jqka.com.cn/thsHotDetail/?name=' + encodeURIComponent(s.name || '')
        + '&code=' + encodeURIComponent(code)
        + '&marketCode=' + _thsMarketCode(code);
    window.open(url, '_blank');
}
