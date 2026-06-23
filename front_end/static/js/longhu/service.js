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
var _lhbCache = {};   // date -> {all: data, org: data, ...} 缓存避免重复请求

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
    // 切日期时重置标签文字（新日期的计数会由 prefetch 重新设置）
    _resetTabLabels();
    renderLHBDateBar(date);
    loadLonghuBang(date);
}

function selectLHBTab(tab) {
    lhbCurrentTab = tab;
    // 更新 tab 样式
    var tabs = document.querySelectorAll('.lhb-tab');
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].classList.toggle('active', tabs[i].getAttribute('data-tab') === tab);
    }
    loadLonghuBang(lhbCurrentDate);
}

async function initLHB() {
    if (_lhbInitialized) return;
    _lhbInitialized = true;

    _lhbDateList = await fetchTradingDays();
    lhbCurrentDate = _lhbDateList[_lhbDateList.length - 1];  // 默认选中最新交易日
    renderLHBDateBar(lhbCurrentDate);
}

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
        html += '<td><span class="lhb-stock-name" onclick="event.stopPropagation();KlinePopup.open(\'' + row.code + '\',\'' + (row.code.startsWith('6') ? '1' : '0') + '\',\'' + (row.name || row.code) + '\')">' + (row.name || row.code) + '</span><span style="color:#888;font-size:11px;margin-left:4px;">' + row.code + '</span>';
        if (typeTag) html += '<span class="' + typeCls + '">' + typeTag + '</span>';
        html += '</td>';
        html += '<td style="text-align:center;color:#888;font-size:11px;">' + getStockType(row.code, row.code.startsWith('6') ? '1' : '0') + '</td>';
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

async function loadLonghuBang(tradeDate) {
    var container = document.getElementById('longhuContent');
    if (!container) return;

    if (!lhbCurrentDate) await initLHB();
    var isManual = !!tradeDate;               // 手动选择 vs 首次自动加载
    var date = tradeDate || lhbCurrentDate;
    if (!date) return;
    var tab = lhbCurrentTab;

    // 切换标签时优先用缓存
    if (isManual) {
        var cacheKey = date + '|' + tab;
        var cached = _lhbCache[cacheKey];
        if (cached) {
            _updateTabLabel(tab, cached.list.length);
            _prefetchTabCounts(date, tab);  // 恢复其他标签计数（resetTabLabels 清空了）
            renderLonghuTable(cached.list, cached.trade_date, tab);
            return;
        }
    }

    try {
        var res = await fetch('/api/longhu-bang?date=' + encodeURIComponent(date) + '&tab=' + encodeURIComponent(tab));
        var result = await res.json();

        if (result.success && result.data && result.data.list.length > 0) {
            // 缓存结果
            var list = result.data.list;
            _lhbCache[date + '|' + tab] = {list: list, trade_date: result.data.trade_date};
            // 立即更新当前标签计数 + 后台预加载其他标签
            _updateTabLabel(tab, list.length);
            _prefetchTabCounts(date, tab);

            if (!isManual && result.data.trade_date !== lhbCurrentDate) {
                lhbCurrentDate = result.data.trade_date;
                renderLHBDateBar(lhbCurrentDate);
            }
            renderLonghuTable(list, result.data.trade_date, tab);
            return;
        }

        if (isManual) {
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

            var prevRes = await fetch('/api/longhu-bang?date=' + encodeURIComponent(prevDate) + '&tab=' + tab);
            var prevResult = await prevRes.json();
            if (prevResult.success && prevResult.data && prevResult.data.list.length > 0) {
                lhbCurrentDate = prevDate;
                _lhbCache[prevDate + '|' + tab] = {list: prevResult.data.list, trade_date: prevResult.data.trade_date};
                _updateTabLabel(tab, prevResult.data.list.length);
                _prefetchTabCounts(prevDate, tab);
                renderLHBDateBar(lhbCurrentDate);
                renderLonghuTable(prevResult.data.list, prevResult.data.trade_date, tab);
                return;
            }
        }
        container.innerHTML = '<div class="error">' + date + ' 及此前10日暂无龙虎榜数据</div>';
    } catch (e) {
        console.log('龙虎榜加载失败:', e);
        container.innerHTML = '<div class="error">龙虎榜加载失败</div>';
    }
}

// 后台预加载其他 tab，更新标签计数
async function _prefetchTabCounts(date, currentTab) {
    for (var t of ['all', 'org', 'capital', 'both']) {
        if (t === currentTab) continue;
        var cacheKey = date + '|' + t;
        // 已有缓存则直接更新标签，否则请求后端
        if (_lhbCache[cacheKey]) {
            _updateTabLabel(t, _lhbCache[cacheKey].list.length);
            continue;
        }
        try {
            var res = await fetch('/api/longhu-bang?date=' + encodeURIComponent(date) + '&tab=' + encodeURIComponent(t));
            var result = await res.json();
            if (result.success && result.data) {
                _lhbCache[cacheKey] = {list: result.data.list, trade_date: result.data.trade_date};
                _updateTabLabel(t, result.data.list.length);
            }
        } catch (_) {}
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
