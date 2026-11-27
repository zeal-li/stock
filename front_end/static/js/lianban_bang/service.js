// ==================== 连板榜 ====================
// 数据源：后端 /api/lianban_bang（东方财富涨停池，按连板数降序）

var _lianbanBangDateList = null;
var _lianbanBangDate = '';
var _lianbanBangTab = 'rank';
var _lianbanBangList = [];   // 当前日期榜单，供两个页签共享渲染
var _lianbanBangCache = {};  // code -> 当前榜单 row（供异动分析弹窗取数）

function fmtLianbanBangAmt(v) {
    if (v == null) return '--';
    v = Number(v);
    if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(0) + '万';
    return String(v);
}

function fmtLianbanBangPct(v) {
    if (v == null) return '--';
    var n = Number(v);
    return (n >= 0 ? '+' : '') + n.toFixed(2) + '%';
}

// ==================== 交易日历 ====================

async function fetchLianbanBangTradingDays() {
    var cache = await getDateLists();
    _lianbanBangDateList = cache.trading_days;
    return _lianbanBangDateList;
}

function renderLianbanBangDateBar(activeDate) {
    var bar = document.getElementById('lianbanBangDateBar');
    if (!bar || !_lianbanBangDateList) return;
    var html = '';
    for (var i = 0; i < _lianbanBangDateList.length; i++) {
        var date = _lianbanBangDateList[i];
        var mmdd = date.slice(5);
        var cls = (date === activeDate) ? 'lhb-date-btn active' : 'lhb-date-btn';
        html += '<span class="' + cls + '" onclick="selectLianbanBangDate(\'' + date + '\')">' + mmdd + '</span>';
    }
    bar.innerHTML = html;
}

function selectLianbanBangDate(date) {
    _lianbanBangDate = date;
    renderLianbanBangDateBar(date);
    loadLianbanBang();
}

// ==================== 初始化 ====================

async function initLianbanBang() {
    var prevLatest = _lianbanBangDateList ? _lianbanBangDateList[_lianbanBangDateList.length - 1] : '';
    _lianbanBangDateList = await fetchLianbanBangTradingDays();
    var latest = _lianbanBangDateList[_lianbanBangDateList.length - 1];
    if (!_lianbanBangDate || _lianbanBangDate === prevLatest) {
        _lianbanBangDate = latest;
    }
    renderLianbanBangDateBar(_lianbanBangDate);
}

// ==================== 页签切换 ====================

function selectLianbanBangTab(tab) {
    _lianbanBangTab = tab;
    var bar = document.getElementById('lianbanBangTabBar');
    if (bar) {
        var tabs = bar.querySelectorAll('.lhb-tab');
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === tab);
        }
    }
    if (_lianbanBangList.length) {
        _renderLianbanBangCurrent();
    } else {
        loadLianbanBang();
    }
}

function _renderLianbanBangCurrent() {
    if (_lianbanBangTab === 'ladder') {
        renderLianbanBangLadder(_lianbanBangList);
    } else {
        renderLianbanBangTable(_lianbanBangList);
    }
}

// ==================== 数据加载 ====================

function loadLianbanBang() {
    _doLoadLianbanBang();
}

function _doLoadLianbanBang() {
    var container = document.getElementById('lianbanBangContent');
    if (!container) return;
    container.innerHTML = '<div class="loading">加载中...</div>';

    fetch('/api/lianban_bang?date=' + encodeURIComponent(_lianbanBangDate))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                container.innerHTML = '<div class="error">' + (res.error || '加载失败') + '</div>';
                return;
            }
            if (!res.list || res.list.length === 0) {
                _lianbanBangList = [];
                container.innerHTML = '<div class="error">暂无该日数据</div>';
                return;
            }
            _lianbanBangList = res.list;
            _renderLianbanBangCurrent();
        })
        .catch(function() {
            container.innerHTML = '<div class="error">连板榜加载失败</div>';
        });
}

// ==================== 表格渲染 ====================

function renderLianbanBangTable(list) {
    var container = document.getElementById('lianbanBangContent');
    _lianbanBangCache = {};
    var html = '<div style="margin-bottom:8px;font-size:12px;color:#888;">共 <b style="color:#fbbf24;">' + list.length + '</b> 只涨停股（按连板数降序）</div>';
    html += '<table class="lhb-table">';
    html += '<thead><tr>';
    html += '<th style="width:70px;text-align:center;">连板</th>';
    html += '<th style="width:120px;">股票</th>';
    html += '<th style="min-width:80px;">行业</th>';
    html += '<th style="width:60px;text-align:right;">现价</th>';
    html += '<th style="width:70px;text-align:right;">涨跌幅</th>';
    html += '<th style="width:80px;text-align:right;">成交额</th>';
    html += '<th style="width:90px;text-align:right;">流通市值</th>';
    html += '<th style="width:70px;text-align:right;">换手率</th>';
    html += '<th style="width:60px;text-align:center;">首封</th>';
    html += '<th style="width:55px;text-align:center;">炸板</th>';
    html += '<th style="width:90px;text-align:right;">封单资金</th>';
    html += '</tr></thead><tbody>';

    for (var i = 0; i < list.length; i++) {
        var row = list[i];
        _lianbanBangCache[row.code] = row;
        var lbc = row.lbc || 1;
        var changeClass = (row.change_pct != null && Number(row.change_pct) >= 0) ? 'change-up' : 'change-down';

        // 连板徽章：红底白字
        var badgeStyle = 'background:#e94560;color:#fff;';
        var lbcText = lbc + '板';
        if (lbc === 1) {
            lbcText = '首板';
        }
        var zttjText = (row.zttj_days != null && row.zttj_ct != null) ? row.zttj_days + '天' + row.zttj_ct + '板' : '';

        html += '<tr class="lhb-row">';
        html += '<td style="text-align:center;">';
        html += '<span style="display:inline-block;min-width:36px;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:700;cursor:pointer;' + badgeStyle + '" onclick="openLianbanBangAnalyse(\'' + row.code + '\')" title="异动分析">' + lbcText + '</span>';
        if (zttjText) html += '<div style="font-size:10px;color:#888;margin-top:2px;">' + zttjText + '</div>';
        html += '</td>';
        html += '<td><span class="lhb-stock-name" onclick="KlinePopup.open(\'' + row.code + '\',\'' + guessMarket(row.code) + '\',\'' + (row.name || row.code) + '\')">' + (row.name || row.code) + '</span><span style="color:#888;font-size:11px;margin-left:4px;">' + row.code + '</span></td>';
        html += '<td style="color:#aaa;font-size:12px;">' + (row.industry || '--') + '</td>';
        html += '<td style="text-align:right;color:#ccc;">' + (row.price != null ? row.price.toFixed(2) : '--') + '</td>';
        html += '<td style="text-align:right;" class="' + changeClass + '">' + fmtLianbanBangPct(row.change_pct) + '</td>';
        html += '<td style="text-align:right;color:#ccc;">' + fmtLianbanBangAmt(row.amount) + '</td>';
        html += '<td style="text-align:right;color:#ccc;">' + fmtLianbanBangAmt(row.float_cap) + '</td>';
        html += '<td style="text-align:right;color:#ccc;">' + (row.turnover != null ? row.turnover.toFixed(2) + '%' : '--') + '</td>';
        html += '<td style="text-align:center;color:#ccc;">' + (row.fbt || '--') + '</td>';
        html += '<td style="text-align:center;color:' + (row.zbc > 0 ? '#e94560' : '#888') + ';">' + (row.zbc || 0) + '</td>';
        html += '<td style="text-align:right;color:#ccc;">' + fmtLianbanBangAmt(row.fund) + '</td>';
        html += '</tr>';
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

// ==================== 连板天梯渲染 ====================

function renderLianbanBangLadder(list) {
    var container = document.getElementById('lianbanBangContent');
    var grouped = {};
    var maxLbc = 0;
    var lbCount = 0;

    for (var i = 0; i < list.length; i++) {
        var row = list[i];
        var lbc = row.lbc || 1;
        if (!grouped[lbc]) grouped[lbc] = [];
        grouped[lbc].push(row);
        if (lbc > 1) lbCount++;
        if (lbc > maxLbc) maxLbc = lbc;
    }

    var tiers = Object.keys(grouped).map(function(k) { return Number(k); }).sort(function(a, b) { return b - a; });
    var dateText = _lianbanBangDate.slice(5).replace('-', '月') + '日';

    var html = '<div class="lb-ladder">';
    html += '<div class="lb-ladder-head">';
    html += '<span class="lb-ladder-date">' + dateText + '</span>';
    html += '<span class="lb-ladder-title">连板天梯</span>';
    html += '<span class="lb-ladder-note">公开数据，仅作参考，不构成投资建议</span>';
    html += '</div>';
    html += '<div class="lb-ladder-summary">涨停 <b>' + list.length + '</b> 家<span class="lb-ladder-sep">·</span>连板 <b>' + lbCount + '</b> 家<span class="lb-ladder-sep">·</span>最高 <b>' + maxLbc + '</b> 板</div>';

    for (var t = 0; t < tiers.length; t++) {
        var level = tiers[t];
        var cards = grouped[level].slice().sort(function(a, b) {
            return String(a.fbt || '').localeCompare(String(b.fbt || ''));
        });
        var zhabanCount = 0;
        var zhabanTimes = 0;
        for (var k = 0; k < cards.length; k++) {
            var times = Number(cards[k].zbc);
            if (times > 0) {
                zhabanCount++;
                zhabanTimes += times;
            }
        }
        var levelName = level === 1 ? '首板' : level + '板';
        var zhabanTitle = zhabanCount > 0 ? '炸板 ' + zhabanCount + ' 家 / 累计 ' + zhabanTimes + ' 次' : '无炸板';
        html += '<div class="lb-ladder-tier">';
        html += '<div class="lb-ladder-tier-label" title="' + zhabanTitle + '">';
        html += '<span class="lb-ladder-tier-name">' + levelName + '</span>';
        html += '<span class="lb-ladder-tier-stat"><b>' + cards.length + '</b>家</span>';
        html += '<span class="lb-ladder-tier-stat' + (zhabanCount > 0 ? ' is-zhaban' : '') + '">炸板 <b>' + zhabanCount + '</b></span>';
        html += '</div>';
        html += '<div class="lb-ladder-tier-cards">';
        for (var j = 0; j < cards.length; j++) {
            var card = cards[j];
            var name = card.name || card.code;
            html += '<div class="lb-ladder-card" title="' + name + ' ' + card.code + '" onclick="KlinePopup.open(\'' + card.code + '\',\'' + guessMarket(card.code) + '\',\'' + name + '\')">';
            html += '<div class="lb-ladder-card-time">' + (card.fbt || '--') + '</div>';
            html += '<div class="lb-ladder-card-name">' + name + '</div>';
            html += '<div class="lb-ladder-card-industry">' + (card.industry || '--') + '</div>';
            html += '<div class="lb-ladder-card-price">现价 <b>' + (card.price != null ? card.price.toFixed(2) : '--') + '</b></div>';
            html += '<div class="lb-ladder-card-turnover">换手 <b>' + (card.turnover != null ? card.turnover.toFixed(2) + '%' : '--') + '</b></div>';
            html += '<div class="lb-ladder-card-cap">流通市值 <b>' + fmtLianbanBangAmt(card.float_cap) + '</b></div>';
            html += '<div class="lb-ladder-card-fund">封单金额 <b>' + fmtLianbanBangAmt(card.fund) + '</b></div>';
            if (card.zbc > 0) {
                html += '<div class="lb-ladder-card-badge" title="炸板 ' + card.zbc + ' 次">炸</div>';
            }
            html += '</div>';
        }
        html += '</div></div>';
    }

    html += '</div>';
    container.innerHTML = html;
}

// ==================== 异动分析弹窗 ====================
// 点击连板徽章 → 复用热股榜的异动分析弹窗（技术面异动分析）

function openLianbanBangAnalyse(code) {
    var row = _lianbanBangCache[code];
    if (!row) return;
    HotstockBangAnalyse.open(code, row);
}
