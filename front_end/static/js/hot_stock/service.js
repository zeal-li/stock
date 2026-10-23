/* 热股榜 — 同花顺热榜数据加载与渲染 */

var _hotStockPeriod = 'hour';   // hour=1小时榜 / day=24小时榜
var _hotStockListType = 'normal'; // normal/skyrocket/new_stock/tech/value/trend

var _HOURLY_TYPES = ['normal', 'skyrocket'];

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

function loadHotStock() {
    var wrap = document.getElementById('hotStockList');
    wrap.innerHTML = '<div class="loading">加载中...</div>';

    var url = '/api/hot-stock?list_type=' + _hotStockListType + '&period=' + _hotStockPeriod;
    fetch(url).then(function(r) { return r.json(); }).then(function(res) {
        if (!res.success) {
            wrap.innerHTML = '<div class="loading">' + (res.error || '加载失败') + '</div>';
            return;
        }
        renderHotStock(res.stocks);
    }).catch(function(e) {
        wrap.innerHTML = '<div class="loading">加载失败: ' + e + '</div>';
    });
}

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

function renderHotStock(stocks) {
    var wrap = document.getElementById('hotStockList');
    if (!stocks || !stocks.length) {
        wrap.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }

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
                + '<span class="hot-stock-name">' + s.name + '</span>'
                + '<span class="hot-stock-code">' + s.code + '</span>'
                + pe
                + '<span class="hot-stock-heat"><i class="hot-fire">🔥</i>' + _hotFmtHeat(s.heat) + '热度</span>';
            extra = date ? '<div class="hot-stock-tags">' + date + '</div>' : '';
        } else {
            var chg = _hotFmtChg(s.change_pct);
            line = ''
                + '<span class="hot-stock-name">' + s.name + '</span>'
                + '<span class="hot-stock-code">' + s.code + '</span>'
                + '<span class="hot-stock-chg ' + chg.cls + '">' + chg.text + '</span>'
                + '<span class="hot-stock-heat"><i class="hot-fire">🔥</i>' + _hotFmtHeat(s.heat) + '热度</span>';
            extra = s.analyse
                ? '<div class="hot-stock-analyse" onclick="_hotToggleAnalyse(this)" title="点击展开/收起">' + s.analyse + '</div>'
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
