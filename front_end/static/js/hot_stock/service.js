/* 热股榜 — 同花顺热榜数据加载与渲染（按日期切换，切换榜单时请求一次） */

var _hotStockPeriod = 'hour';     // hour=1小时榜 / day=24小时榜
var _hotStockListType = 'normal'; // normal/skyrocket/new_stock/tech/value/trend
var _hotStockDate = '';           // 当前选中日期（自然日，默认今天）
var _hotStockDateList = null;     // 最近30个自然日
var _hotStockInitialized = false;

var _HOURLY_TYPES = ['normal', 'skyrocket'];

// ==================== 日期栏 ====================

async function fetchHotStockDates() {
    var res = await fetch('/api/hot-stock-dates?count=30');
    var result = await res.json();
    _hotStockDateList = result.data.dates;
    return _hotStockDateList;
}

function renderHotStockDateBar(activeDate) {
    var bar = document.getElementById('hotStockDateBar');
    if (!bar || !_hotStockDateList) return;
    var html = '';
    for (var i = 0; i < _hotStockDateList.length; i++) {
        var date = _hotStockDateList[i];
        var mmdd = date.slice(5);  // "MM-DD"
        var cls = (date === activeDate) ? 'lhb-date-btn active' : 'lhb-date-btn';
        html += '<span class="' + cls + '" onclick="selectHotStockDate(\'' + date + '\')">' + mmdd + '</span>';
    }
    bar.innerHTML = html;
}

function selectHotStockDate(date) {
    if (_hotStockDate === date) return;
    _hotStockDate = date;
    renderHotStockDateBar(date);
    loadHotStock();
}

async function initHotStock() {
    if (_hotStockInitialized) return;
    _hotStockInitialized = true;
    _hotStockDateList = await fetchHotStockDates();
    _hotStockDate = _hotStockDateList[_hotStockDateList.length - 1];  // 默认最新自然日（今天）
    renderHotStockDateBar(_hotStockDate);
}

// ==================== 榜单 / 周期切换 ====================

function _syncHotStockTabs() {
    document.querySelectorAll('#page-hot-stock .hot-type-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-list-type') === _hotStockListType);
    });
    // 只有小时榜类型显示 1小时/24小时 切换
    var hourly = _HOURLY_TYPES.indexOf(_hotStockListType) >= 0;
    var periodTabs = document.getElementById('hotPeriodTabs');
    if (periodTabs) periodTabs.style.display = hourly ? '' : 'none';
    document.querySelectorAll('#page-hot-stock .hot-period-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-period') === _hotStockPeriod);
    });
}

function switchHotListType(listType) {
    if (_hotStockListType === listType) return;
    _hotStockListType = listType;
    _syncHotStockTabs();
    loadHotStock();
}

function switchHotStockPeriod(period) {
    if (_hotStockPeriod === period) return;
    _hotStockPeriod = period;
    _syncHotStockTabs();
    loadHotStock();
}

// ==================== 加载 ====================

function loadHotStock() {
    if (!_hotStockInitialized) {
        initHotStock().then(function() { _doLoadHotStock(); });
        return;
    }
    _doLoadHotStock();
}

function _doLoadHotStock() {
    var wrap = document.getElementById('hotStockList');
    wrap.innerHTML = '<div class="loading">加载中...</div>';

    var url = '/api/hot-stock?list_type=' + _hotStockListType
        + '&period=' + _hotStockPeriod
        + '&date=' + encodeURIComponent(_hotStockDate);
    fetch(url).then(function(r) { return r.json(); }).then(function(res) {
        if (!res.success) {
            wrap.innerHTML = '<div class="loading">' + (res.error || '加载失败') + '</div>';
            return;
        }
        if (res.empty) {
            wrap.innerHTML = '<div class="loading">暂无该日数据</div>';
            return;
        }
        renderHotStock(res.stocks);
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
    return '<span class="hot-stock-name" onclick="KlinePopup.open(\'' + s.code + '\',\'' + guessMarket(s.code) + '\',\'' + name + '\')">' + s.name + '</span>';
}

function renderHotStock(stocks) {
    var wrap = document.getElementById('hotStockList');
    if (!stocks || !stocks.length) {
        wrap.innerHTML = '<div class="loading">暂无该日数据</div>';
        return;
    }

    // 缓存当前榜单，供异动解读弹窗按 code 取数
    _hotStockCache = {};
    stocks.forEach(function(s) { _hotStockCache[s.code] = s; });

    var isNewStock = _hotStockListType === 'new_stock';
    var html = '';

    stocks.forEach(function(s) {
        var rank = s.rank || '';
        var rankCls = rank >= 1 && rank <= 3 ? ' hot-rank-' + rank : '';
        var tags = _hotTagsHtml(s);

        var line;
        var extra = '';
        if (isNewStock) {
            var pe = s.pe != null ? '<span class="hot-stock-pe">PE ' + s.pe + '</span>' : '';
            var date = s.order_date ? '<span class="hot-stock-meta">上市 ' + _hotFmtDate(s.order_date) + '</span>' : '';
            line = ''
                + _hotNameHtml(s)
                + '<span class="hot-stock-code">' + s.code + '</span>'
                + pe
                + '<span class="hot-stock-analyse-btn" onclick="HotStockAnalyse.open(\'' + s.code + '\')">异动解读</span>'
                + '<span class="hot-stock-heat"><i class="hot-fire">🔥</i>' + _hotFmtHeat(s.heat) + '热度</span>';
            extra = date ? '<div class="hot-stock-tags">' + date + '</div>' : '';
        } else {
            var chg = _hotFmtChg(s.change_pct);
            line = ''
                + _hotNameHtml(s)
                + '<span class="hot-stock-code">' + s.code + '</span>'
                + '<span class="hot-stock-chg ' + chg.cls + '">' + chg.text + '</span>'
                + '<span class="hot-stock-analyse-btn" onclick="HotStockAnalyse.open(\'' + s.code + '\')">异动解读</span>'
                + '<span class="hot-stock-heat"><i class="hot-fire">🔥</i>' + _hotFmtHeat(s.heat) + '热度</span>';
            extra = s.analyse
                ? '<div class="hot-stock-analyse expanded" onclick="_hotToggleAnalyse(this)" title="点击展开/收起">' + s.analyse + '</div>'
                : '';
        }

        html += ''
            + '<div class="hot-stock-item">'
            +   '<div class="hot-stock-rank' + rankCls + '">' + rank + '</div>'
            +   '<div class="hot-stock-main">'
            +     '<div class="hot-stock-line">' + line + '</div>'
            +     (tags ? '<div class="hot-stock-tags">' + tags + '</div>' : '')
            +     extra
            +   '</div>'
            + '</div>';
    });

    wrap.innerHTML = html;
}

// ==================== 异动解读弹窗 ====================
// 榜单项「异动解读」按钮 → 弹窗显示同花顺解读（analyse）+ 技术面异动分析
var _hotStockCache = {};  // code -> 当前榜单 stock 对象

var HotStockAnalyse = (function() {
    var _overlay = null;
    var _activeCode = '';

    function _ensureDOM() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.id = 'hotStockAnalyseOverlay';
        _overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.7);z-index:200;justify-content:center;align-items:center;';
        _overlay.onclick = function(e) { if (e.target === _overlay) close(); };
        document.body.appendChild(_overlay);
    }

    function open(code) {
        var s = _hotStockCache[code];
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
                        (s.change_pct != null ? '<span class="hot-stock-chg ' + chg.cls + '">' + chg.text + '</span>' : '') +
                        '<span style="font-size:12px;color:#e0a94a;">🔥' + _hotFmtHeat(s.heat) + '热度</span>' +
                    '</div>' +
                    '<span style="color:#666;font-size:20px;cursor:pointer;padding:0 4px;line-height:1;" onclick="HotStockAnalyse.close()">✕</span>' +
                '</div>' +
                '<div class="hot-stock-analyse-body" style="padding:14px 18px;overflow-y:auto;flex:1;">' +
                    (tags ? '<div class="hot-stock-tags" style="margin-top:0;">' + tags + '</div>' : '') +
                    '<div style="margin-top:16px;border-top:1px solid #2a2a4e;padding-top:12px;">' +
                        '<div style="font-size:13px;color:#6bb1ff;margin-bottom:10px;">📊 技术面异动分析</div>' +
                        '<div id="hotStockAnalyseTech" style="color:#8b8b9e;font-size:13px;">加载中...</div>' +
                    '</div>' +
                    '<div style="margin-top:16px;border-top:1px solid #2a2a4e;padding-top:12px;">' +
                        '<div style="font-size:13px;color:#e0a94a;margin-bottom:10px;">📌 异动解读</div>' +
                        '<div id="hotStockAnalyseAnomaly" style="color:#8b8b9e;font-size:13px;">加载中...</div>' +
                    '</div>' +
                '</div>' +
            '</div>';
        _overlay.style.display = 'flex';

        _loadTech(code);
        _loadAnomaly(code);
    }

    function _loadTech(code) {
        var el = document.getElementById('hotStockAnalyseTech');
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

    // ---- 异动解读（前端 localStorage 缓存，1 小时有效） ----
    var _ANOMALY_CACHE_KEY = 'hot_stock_anomaly_cache';
    var _ANOMALY_CACHE_TTL = 3600;  // 秒

    function _getAnomalyCache(code) {
        try {
            var all = JSON.parse(localStorage.getItem(_ANOMALY_CACHE_KEY) || '{}');
            return all[code] || null;
        } catch (e) { return null; }
    }

    function _setAnomalyCache(code, items) {
        try {
            var all = JSON.parse(localStorage.getItem(_ANOMALY_CACHE_KEY) || '{}');
            all[code] = { ts: Math.floor(Date.now() / 1000), items: items };
            localStorage.setItem(_ANOMALY_CACHE_KEY, JSON.stringify(all));
        } catch (e) {}
    }

    function _renderAnomaly(el, items, code) {
        if (code !== _activeCode) return;
        if (!items || !items.length) {
            el.innerHTML = '<div style="color:#666;">暂无异动解读记录</div>';
            return;
        }
        el.innerHTML = items.map(_anomalyItemHtml).join('');
    }

    function _loadAnomaly(code) {
        var el = document.getElementById('hotStockAnalyseAnomaly');
        if (!el) return;

        // 先查前端缓存：1 小时内有效，直接渲染不请求后端
        var cached = _getAnomalyCache(code);
        if (cached && cached.items && (Math.floor(Date.now() / 1000) - cached.ts) < _ANOMALY_CACHE_TTL) {
            _renderAnomaly(el, cached.items, code);
            return;
        }

        fetch('/api/hot-stock-anomaly?code=' + encodeURIComponent(code)
            + '&market=' + encodeURIComponent(guessMarket(code)))
            .then(function(r) { return r.json(); })
            .then(function(resp) {
                if (code !== _activeCode) return;
                if (!resp.success) {
                    el.innerHTML = '<div style="color:#8b8b9e;">' + (resp.error || '加载失败') + '</div>';
                    return;
                }
                var items = resp.items || [];
                // 空结果不缓存，避免 1 小时内都拿不到新数据
                if (items.length) {
                    _setAnomalyCache(code, items);
                }
                _renderAnomaly(el, items, code);
            })
            .catch(function() {
                if (code !== _activeCode) return;
                el.innerHTML = '<div style="color:#ef5350;">请求失败</div>';
            });
    }

    function _anomalyTagCls(tag) {
        if (tag.indexOf('涨停') >= 0 || tag.indexOf('大涨') >= 0 || tag.indexOf('拉升') >= 0) return 'change-up';
        if (tag.indexOf('大跌') >= 0 || tag.indexOf('跌停') >= 0 || tag.indexOf('跳水') >= 0) return 'change-down';
        return '';
    }

    function _anomalyItemHtml(it) {
        var tagCls = _anomalyTagCls(it.tag);
        var tagHtml = it.tag
            ? '<span class="' + tagCls + '" style="font-size:11px;' + (tagCls ? '' : 'color:#8b8b9e;') + '">【' + it.tag + '】</span>'
            : '';
        var html = '<div style="margin-bottom:14px;">' +
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">' +
                '<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:#3b4a6b;flex-shrink:0;"></span>' +
                '<span style="font-size:12px;color:#8b8b9e;">' + (it.date || '') + '</span>' +
                tagHtml +
            '</div>';
        if (it.title) {
            html += '<div style="font-size:14px;color:#fff;font-weight:600;margin-bottom:4px;">' + it.title + '</div>';
        }
        if (it.reason) {
            html += '<div style="font-size:12px;color:#8b8b9e;line-height:1.7;white-space:pre-line;">' + it.reason + '</div>';
        }
        html += '</div>';
        return html;
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
