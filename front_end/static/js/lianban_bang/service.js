// ==================== 连板榜 ====================
// 数据源：后端 /api/lianban_bang（东方财富涨停池，按连板数降序）

var _lianbanBangDateList = null;
var _lianbanBangDate = '';
var _lianbanBangInitialized = false;

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
    var res = await fetch('/api/trading-days?count=30');
    var result = await res.json();
    _lianbanBangDateList = result.data.trading_days;
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
    if (_lianbanBangInitialized) return;
    _lianbanBangInitialized = true;
    _lianbanBangDateList = await fetchLianbanBangTradingDays();
    _lianbanBangDate = _lianbanBangDateList[_lianbanBangDateList.length - 1];
    renderLianbanBangDateBar(_lianbanBangDate);
}

// ==================== 数据加载 ====================

function loadLianbanBang() {
    if (!_lianbanBangInitialized) {
        initLianbanBang().then(function() { _doLoadLianbanBang(); });
        return;
    }
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
                container.innerHTML = '<div class="error">暂无该日数据</div>';
                return;
            }
            renderLianbanBangTable(res.list);
        })
        .catch(function() {
            container.innerHTML = '<div class="error">连板榜加载失败</div>';
        });
}

// ==================== 表格渲染 ====================

function renderLianbanBangTable(list) {
    var container = document.getElementById('lianbanBangContent');
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
        html += '<span style="display:inline-block;min-width:36px;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:700;' + badgeStyle + '">' + lbcText + '</span>';
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
