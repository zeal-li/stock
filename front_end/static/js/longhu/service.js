// ==================== 龙虎榜 ====================

function fmtLHB(v, unit) {
    if (v == null) return '--';
    v = Number(v);
    if (unit === 'amt') {
        var w = v / 10000;
        if (Math.abs(w) >= 10000) return (w / 10000).toFixed(2) + '亿';
        return w.toFixed(0) + '万';
    }
    if (unit === 'pct') {
        return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
    }
    if (unit === 'turnover') {
        return v.toFixed(2) + '%';
    }
    if (unit === 'price') {
        return v.toFixed(2);
    }
    return String(v);
}

function getLHBColor(v) {
    if (v == null) return '#888';
    return Number(v) >= 0 ? '#e94560' : '#4ade80';
}

function toggleLHBDetail(idx) {
    var detailRow = document.getElementById('lhb-detail-' + idx);
    if (!detailRow) return;
    if (detailRow.style.display === 'none' || detailRow.style.display === '') {
        var allDetails = document.querySelectorAll('.lhb-detail');
        for (var d = 0; d < allDetails.length; d++) {
            allDetails[d].style.display = 'none';
        }
        detailRow.style.display = 'table-row';
    } else {
        detailRow.style.display = 'none';
    }
}

var lhbCurrentDate = '';
var lhbCurrentTab = 'all';
var _lhbInitialized = false;
var _lhbDateList = null;
var _lhbCurrentData = [];   // 当前日期的全部股票数据（含 buy_seats/sell_seats）

// ==================== 前端分类 ====================

function _classifyStock(row) {
    var buySeats = row.buy_seats || [];
    var sellSeats = row.sell_seats || [];
    var hasJG = buySeats.some(function(s) { return s.name && s.name.indexOf('机构专用') >= 0; }) ||
                sellSeats.some(function(s) { return s.name && s.name.indexOf('机构专用') >= 0; });
    var hasYZ = buySeats.some(function(s) { return s.label; }) ||
                sellSeats.some(function(s) { return s.label; });
    if (hasJG && hasYZ) return 'both';
    if (hasJG) return 'org';
    if (hasYZ) return 'capital';
    return 'other';
}

function _sortLHBList(list) {
    // 排序：净买额/成交额↓ → 涨跌幅↓ → 成交额↓
    list.sort(function(a, b) {
        var ratioA = a.amount_raw ? (a.net_amt / a.amount_raw) : -Infinity;
        var ratioB = b.amount_raw ? (b.net_amt / b.amount_raw) : -Infinity;
        if (ratioB !== ratioA) return ratioB - ratioA;
        var chgA = a.change_pct != null ? a.change_pct : -Infinity;
        var chgB = b.change_pct != null ? b.change_pct : -Infinity;
        if (chgB !== chgA) return chgB - chgA;
        var amtA = a.amount_raw != null ? a.amount_raw : -Infinity;
        var amtB = b.amount_raw != null ? b.amount_raw : -Infinity;
        return amtB - amtA;
    });
}

function _getFilteredList(tab) {
    var list;
    if (tab === 'all') {
        list = _lhbCurrentData.slice();
    } else {
        list = _lhbCurrentData.filter(function(r) {
            return _classifyStock(r) === tab;
        });
    }
    _sortLHBList(list);
    return list;
}

// ==================== 交易日历 ====================

async function fetchTradingDays() {
    var res = await fetch('/api/trading-days?count=30');
    var result = await res.json();
    _lhbDateList = result.data.trading_days;
    return _lhbDateList;
}

function renderLHBDateBar(activeDate) {
    var bar = document.getElementById('lhbDateBar');
    if (!bar || !_lhbDateList) return;

    var html = '';
    for (var i = 0; i < _lhbDateList.length; i++) {
        var date = _lhbDateList[i];
        var mmdd = date.slice(5);  // "MM-DD"
        var cls = (date === activeDate) ? 'lhb-date-btn active' : 'lhb-date-btn';
        html += '<span class="' + cls + '" onclick="selectLHBDate(\'' + date + '\')">' + mmdd + '</span>';
    }
    bar.innerHTML = html;
}

function selectLHBDate(date) {
    lhbCurrentDate = date;
    _resetTabLabels();
    renderLHBDateBar(date);
    loadLonghuBang(date);
}

// ==================== 分类标签 ====================

function selectLHBTab(tab) {
    lhbCurrentTab = tab;
    var tabs = document.querySelectorAll('.lhb-tab');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === tab);
    }
    // 从本地数据筛选渲染，不再请求后端
    _renderCurrentTab();
}

function _renderCurrentTab() {
    var tab = lhbCurrentTab;
    var list = _getFilteredList(tab);
    _updateTabLabel(tab, list.length);
    // 构建显示用的数据（添加 total_buy/total_sell/lhb_type）
    var displayList = list.map(function(r) {
        var totalBuy = 0, totalSell = 0;
        (r.buy_seats || []).forEach(function(s) { totalBuy += s.buy_amt; });
        (r.sell_seats || []).forEach(function(s) { totalSell += s.sell_amt; });
        return {
            code: r.code,
            name: r.name,
            price: r.price,
            change_pct: r.change_pct,
            amount_raw: r.amount_raw,
            net_amt: r.net_amt,
            total_buy: totalBuy,
            total_sell: totalSell,
            lhb_type: _classifyStock(r),
            multi_day: r.multi_day,
            reason: r.reason,
            buy_seats: r.buy_seats,
            sell_seats: r.sell_seats,
            trade_date: r.trade_date,
        };
    });
    renderLonghuTable(displayList, lhbCurrentDate, tab);
}

function _updateAllTabLabels() {
    ['all', 'org', 'capital', 'both'].forEach(function(tab) {
        var list = tab === 'all'
            ? _lhbCurrentData
            : _lhbCurrentData.filter(function(r) { return _classifyStock(r) === tab; });
        _updateTabLabel(tab, list.length);
    });
}

// ==================== 初始化 ====================

async function initLHB() {
    if (_lhbInitialized) return;
    _lhbInitialized = true;

    _lhbDateList = await fetchTradingDays();
    lhbCurrentDate = _lhbDateList[_lhbDateList.length - 1];  // 默认选中最新交易日
    renderLHBDateBar(lhbCurrentDate);
}

// ==================== 表格渲染 ====================

function renderLonghuTable(data, tradeDate, tab) {
    var container = document.getElementById('longhuContent');
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="error">' + (tradeDate || '该日') + ' 暂无龙虎榜数据（非交易日或数据未更新）</div>';
        return;
    }

    var tabLabel = {'all':'全部','org':'机构榜','capital':'游资榜','both':'机构+游资'}[tab] || '';
    var html = '<div style="margin-bottom:8px;font-size:12px;color:#888;">共 <b style="color:#fbbf24;">' + data.length + '</b> 条' + (tabLabel ? '（' + tabLabel + '）' : '') + '</div>';
    html += '<table class="lhb-table">';
    html += '<thead><tr>';
    html += '<th style="width:120px;">股票</th>';
    html += '<th style="width:48px;text-align:center;">市场</th>';
    html += '<th style="width:55px;text-align:right;">现价</th>';
    html += '<th style="width:60px;text-align:right;">涨跌幅</th>';
    html += '<th style="width:85px;text-align:right;">成交额</th>';
    html += '<th style="width:78px;text-align:right;">总买额</th>';
    html += '<th style="width:78px;text-align:right;">总卖额</th>';
    html += '<th style="width:85px;text-align:right;">净买额</th>';
    html += '<th style="min-width:120px;">上榜原因</th>';
    html += '</tr></thead><tbody>';

    for (var i = 0; i < data.length; i++) {
        var row = data[i];
        var netColor = getLHBColor(row.net_amt);
        var changeClass = (row.change_pct != null && Number(row.change_pct) >= 0) ? 'change-up' : 'change-down';

        // 分类标签颜色
        var typeTag = '';
        var typeCls = 'lhb-type-tag';
        if (row.lhb_type === 'org') { typeTag = '机构'; typeCls += ' org'; }
        else if (row.lhb_type === 'capital') { typeTag = '游资'; typeCls += ' capital'; }
        else if (row.lhb_type === 'both') { typeTag = '机构+游资'; typeCls += ' both'; }

        html += '<tr class="lhb-row" onclick="toggleLHBDetail(' + i + ')" style="cursor:pointer;">';
        html += '<td><span class="lhb-stock-name" onclick="event.stopPropagation();KlinePopup.open(\'' + row.code + '\',\'' + guessMarket(row.code) + '\',\'' + (row.name || row.code) + '\')">' + (row.name || row.code) + '</span><span style="color:#888;font-size:11px;margin-left:4px;">' + row.code + '</span>';
        if (typeTag) html += '<span class="' + typeCls + '">' + typeTag + '</span>';
        html += '</td>';
        html += '<td style="text-align:center;color:#888;font-size:11px;">' + getStockType(row.code, guessMarket(row.code)) + '</td>';
        html += '<td style="text-align:right;color:#ccc;">' + fmtLHB(row.price, 'price') + '</td>';
        html += '<td style="text-align:right;" class="' + changeClass + '">' + fmtLHB(row.change_pct, 'pct') + '</td>';
        html += '<td style="text-align:right;color:#888;">' + fmtLHB(row.amount_raw, 'amt') + '</td>';
        html += '<td style="text-align:right;color:#e94560;">' + fmtLHB(row.total_buy, 'amt') + '</td>';
        html += '<td style="text-align:right;color:#4ade80;">' + fmtLHB(row.total_sell, 'amt') + '</td>';
        html += '<td style="text-align:right;color:' + netColor + ';font-weight:bold;">' + fmtLHB(row.net_amt, 'amt') + '</td>';
        html += '<td style="color:#aaa;font-size:12px;">' + (row.reason || '--') + '</td>';
        html += '</tr>';

        // 展开的详情行：买卖席位明细
        html += '<tr class="lhb-detail" id="lhb-detail-' + i + '" style="display:none;">';
        html += '<td colspan="9" style="padding:0;">';
        html += '<div style="display:flex; gap:16px; padding:10px 12px; background:#0d1b33; border-radius:4px; margin:4px 0;">';

        // 买方席位
        html += '<div style="flex:1; min-width:0;">';
        html += '<div style="font-size:12px; font-weight:bold; color:#e94560; margin-bottom:6px;">买入席位</div>';
        html += '<table style="width:100%; font-size:11px; border-collapse:collapse;">';
        html += '<thead><tr style="color:#666; border-bottom:1px solid rgba(255,255,255,0.05);"><th style="text-align:left;padding:2px 4px;">营业部</th><th style="text-align:right;padding:2px 4px;width:50px;">买入</th><th style="text-align:right;padding:2px 4px;width:50px;">卖出</th><th style="text-align:right;padding:2px 4px;width:50px;">净额</th></tr></thead><tbody>';
        var buySeats = row.buy_seats || [];
        for (var bi = 0; bi < buySeats.length; bi++) {
            var bs = buySeats[bi];
            var label = bs.label ? '<span style="color:#fbbf24;font-size:10px;">[' + bs.label + ']</span> ' : '';
            html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">';
            html += '<td style="padding:2px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;" title="' + (bs.name || '') + '">' + label + (bs.name || '--') + '</td>';
            html += '<td style="text-align:right;padding:2px 4px;color:#e94560;">' + fmtLHB(bs.buy_amt, 'amt') + '</td>';
            html += '<td style="text-align:right;padding:2px 4px;color:#4ade80;">' + (bs.sell_amt > 0 ? fmtLHB(bs.sell_amt, 'amt') : '--') + '</td>';
            html += '<td style="text-align:right;padding:2px 4px;color:' + getLHBColor(bs.net_amt) + ';">' + fmtLHB(bs.net_amt, 'amt') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';

        // 卖出席位
        html += '<div style="flex:1; min-width:0;">';
        html += '<div style="font-size:12px; font-weight:bold; color:#4ade80; margin-bottom:6px;">卖出席位</div>';
        html += '<table style="width:100%; font-size:11px; border-collapse:collapse;">';
        html += '<thead><tr style="color:#666; border-bottom:1px solid rgba(255,255,255,0.05);"><th style="text-align:left;padding:2px 4px;">营业部</th><th style="text-align:right;padding:2px 4px;width:50px;">买入</th><th style="text-align:right;padding:2px 4px;width:50px;">卖出</th><th style="text-align:right;padding:2px 4px;width:50px;">净额</th></tr></thead><tbody>';
        var sellSeats = row.sell_seats || [];
        for (var si = 0; si < sellSeats.length; si++) {
            var ss = sellSeats[si];
            var slabel = ss.label ? '<span style="color:#fbbf24;font-size:10px;">[' + ss.label + ']</span> ' : '';
            html += '<tr style="border-bottom:1px solid rgba(255,255,255,0.03);">';
            html += '<td style="padding:2px 4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:200px;" title="' + (ss.name || '') + '">' + slabel + (ss.name || '--') + '</td>';
            html += '<td style="text-align:right;padding:2px 4px;color:#e94560;">' + (ss.buy_amt > 0 ? fmtLHB(ss.buy_amt, 'amt') : '--') + '</td>';
            html += '<td style="text-align:right;padding:2px 4px;color:#4ade80;">' + fmtLHB(ss.sell_amt, 'amt') + '</td>';
            html += '<td style="text-align:right;padding:2px 4px;color:' + getLHBColor(ss.net_amt) + ';">' + fmtLHB(ss.net_amt, 'amt') + '</td>';
            html += '</tr>';
        }
        html += '</tbody></table></div>';

        html += '</div></td></tr>';
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

// ==================== 数据加载（无缓存，每次切日期都请求后端） ====================

async function loadLonghuBang(tradeDate) {
    var container = document.getElementById('longhuContent');
    if (!container) return;

    if (!lhbCurrentDate) await initLHB();
    var isManual = !!tradeDate;
    var date = tradeDate || lhbCurrentDate;
    if (!date) return;

    try {
        var res = await fetch('/api/longhu-bang?date=' + encodeURIComponent(date));
        var result = await res.json();

        if (result.success && result.data && result.data.list.length > 0) {
            _lhbCurrentData = result.data.list;

            if (!isManual && result.data.trade_date !== lhbCurrentDate) {
                lhbCurrentDate = result.data.trade_date;
                renderLHBDateBar(lhbCurrentDate);
            }

            // 更新所有标签计数 + 渲染当前标签
            _updateAllTabLabels();
            _renderCurrentTab();
            return;
        }

        if (isManual) {
            _lhbCurrentData = [];
            container.innerHTML = '<div class="error">' + date + ' 暂无龙虎榜数据</div>';
            return;
        }

        // 首次自动加载无数据 → 往历史回溯
        var parts = date.split('-');
        var d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        for (var i = 0; i < 10; i++) {
            d.setDate(d.getDate() - 1);
            var yyyy = d.getFullYear();
            var mm = String(d.getMonth() + 1).padStart(2, '0');
            var dd = String(d.getDate()).padStart(2, '0');
            var prevDate = yyyy + '-' + mm + '-' + dd;

            var prevRes = await fetch('/api/longhu-bang?date=' + encodeURIComponent(prevDate));
            var prevResult = await prevRes.json();
            if (prevResult.success && prevResult.data && prevResult.data.list.length > 0) {
                lhbCurrentDate = prevDate;
                _lhbCurrentData = prevResult.data.list;
                _updateAllTabLabels();
                renderLHBDateBar(lhbCurrentDate);
                _renderCurrentTab();
                return;
            }
        }
        _lhbCurrentData = [];
        container.innerHTML = '<div class="error">' + date + ' 及此前10日暂无龙虎榜数据</div>';
    } catch (e) {
        console.log('龙虎榜加载失败:', e);
        container.innerHTML = '<div class="error">龙虎榜加载失败</div>';
    }
}

function _updateTabLabel(tab, count) {
    var el = document.querySelector('.lhb-tab[data-tab="' + tab + '"]');
    if (!el) return;
    var label = el.getAttribute('data-label') || el.textContent.split(' (')[0];
    el.setAttribute('data-label', label);
    el.textContent = label + ' (' + count + ')';
}

function _resetTabLabels() {
    var tabs = document.querySelectorAll('.lhb-tab');
    for (var i = 0; i < tabs.length; i++) {
        var label = tabs[i].getAttribute('data-label');
        if (label) tabs[i].textContent = label;
    }
}
