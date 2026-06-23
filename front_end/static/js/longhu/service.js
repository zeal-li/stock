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

function renderLonghuTable(data, tradeDate) {
    var dateEl = document.getElementById('lhbPageDate');
    if (dateEl) dateEl.textContent = tradeDate || '';

    var container = document.getElementById('longhuContent');
    if (!data || data.length === 0) {
        container.innerHTML = '<div class="error">今日暂无龙虎榜数据（非交易日或数据未更新）</div>';
        return;
    }

    var html = '<table class="lhb-table">';
    html += '<thead><tr>';
    html += '<th style="width:130px;">股票</th>';
    html += '<th style="width:60px;text-align:right;">收盘价</th>';
    html += '<th style="width:65px;text-align:right;">涨跌幅</th>';
    html += '<th style="width:80px;text-align:right;">净买额</th>';
    html += '<th style="width:80px;text-align:right;">买入额</th>';
    html += '<th style="width:80px;text-align:right;">卖出额</th>';
    html += '<th style="width:60px;text-align:right;">换手率</th>';
    html += '<th style="min-width:160px;">上榜原因</th>';
    html += '</tr></thead><tbody>';

    for (var i = 0; i < data.length; i++) {
        var row = data[i];
        var netColor = getLHBColor(row.net_amt);
        var changeClass = (row.change_pct != null && Number(row.change_pct) >= 0) ? 'change-up' : 'change-down';

        html += '<tr class="lhb-row" onclick="toggleLHBDetail(' + i + ')" style="cursor:pointer;">';
        html += '<td><span class="lhb-stock-name" onclick="event.stopPropagation();KlinePopup.open(\'' + row.code + '\',\'' + (row.code.startsWith('6') ? '1' : '0') + '\',\'' + (row.name || row.code) + '\')">' + (row.name || row.code) + '</span><span style="color:#888;font-size:11px;margin-left:4px;">' + row.code + '</span></td>';
        html += '<td style="text-align:right;color:#ccc;">' + fmtLHB(row.price, 'price') + '</td>';
        html += '<td style="text-align:right;" class="' + changeClass + '">' + fmtLHB(row.change_pct, 'pct') + '</td>';
        html += '<td style="text-align:right;color:' + netColor + ';font-weight:bold;">' + fmtLHB(row.net_amt, 'amt') + '</td>';
        html += '<td style="text-align:right;color:#e94560;">' + fmtLHB(row.buy_amt, 'amt') + '</td>';
        html += '<td style="text-align:right;color:#4ade80;">' + fmtLHB(row.sell_amt, 'amt') + '</td>';
        html += '<td style="text-align:right;color:#888;">' + fmtLHB(row.turnover_rate, 'turnover') + '</td>';
        html += '<td style="color:#aaa;font-size:12px;">' + (row.reason || '--') + '</td>';
        html += '</tr>';

        // 展开的详情行：席位数量 + 上榜后表现
        html += '<tr class="lhb-detail" id="lhb-detail-' + i + '" style="display:none;">';
        html += '<td colspan="8" style="padding:0;">';
        html += '<div style="display:flex; gap:20px; padding:10px 15px; background:#0d1b33; border-radius:4px; margin:4px 0;">';

        // 买卖席位统计
        html += '<div style="flex:1;">';
        html += '<div style="font-size:12px; font-weight:bold; color:#fbbf24; margin-bottom:6px;">席位统计</div>';
        html += '<div style="font-size:11px; color:#ccc; line-height:2;">';
        html += '<span style="color:#888;">买席位: </span><span style="color:#e94560;">' + (row.buy_seat_count != null ? row.buy_seat_count + '个' : '--') + '</span>&nbsp;&nbsp;';
        html += '<span style="color:#888;">卖席位: </span><span style="color:#4ade80;">' + (row.sell_seat_count != null ? row.sell_seat_count + '个' : '--') + '</span><br>';
        html += '<span style="color:#888;">净买额占比: </span><span style="color:#ccc;">' + (row.ratio != null ? (row.ratio * 100).toFixed(2) + '%' : '--') + '</span>&nbsp;&nbsp;';
        html += '<span style="color:#888;">流通市值: </span><span style="color:#ccc;">' + (row.free_cap != null ? row.free_cap + '亿' : '--') + '</span>&nbsp;&nbsp;';
        html += '<span style="color:#888;">市场: </span><span style="color:#ccc;">' + (row.market || '--') + '</span>';
        html += '</div></div>';

        // 上榜后表现
        html += '<div style="flex:1;">';
        html += '<div style="font-size:12px; font-weight:bold; color:#60a5fa; margin-bottom:6px;">上榜后表现</div>';
        html += '<table style="width:100%; font-size:11px; border-collapse:collapse;">';
        html += '<thead><tr style="color:#888; border-bottom:1px solid rgba(255,255,255,0.05);">';
        html += '<th style="padding:3px 4px;text-align:center;">T+1</th><th style="padding:3px 4px;text-align:center;">T+2</th><th style="padding:3px 4px;text-align:center;">T+3</th><th style="padding:3px 4px;text-align:center;">T+5</th><th style="padding:3px 4px;text-align:center;">T+10</th>';
        html += '</tr></thead><tbody><tr>';
        html += '<td style="padding:3px 4px;text-align:center;color:' + getLHBColor(row.d1_return) + ';">' + fmtLHB(row.d1_return, 'pct') + '</td>';
        html += '<td style="padding:3px 4px;text-align:center;color:' + getLHBColor(row.d2_return) + ';">' + fmtLHB(row.d2_return, 'pct') + '</td>';
        html += '<td style="padding:3px 4px;text-align:center;color:' + getLHBColor(row.d3_return) + ';">' + fmtLHB(row.d3_return, 'pct') + '</td>';
        html += '<td style="padding:3px 4px;text-align:center;color:' + getLHBColor(row.d5_return) + ';">' + fmtLHB(row.d5_return, 'pct') + '</td>';
        html += '<td style="padding:3px 4px;text-align:center;color:' + getLHBColor(row.d10_return) + ';">' + fmtLHB(row.d10_return, 'pct') + '</td>';
        html += '</tr></tbody></table></div>';

        html += '</div></td></tr>';
    }

    html += '</tbody></table>';
    container.innerHTML = html;
}

async function loadLonghuBang() {
    var container = document.getElementById('longhuContent');
    if (!container) return;

    try {
        var res = await fetch('/api/longhu-bang');
        var result = await res.json();

        if (result.success && result.data) {
            renderLonghuTable(result.data.list, result.data.trade_date);
        } else {
            container.innerHTML = '<div class="error">暂无龙虎榜数据</div>';
            document.getElementById('lhbPageDate').textContent = '';
        }
    } catch (e) {
        console.log('龙虎榜加载失败:', e);
        container.innerHTML = '<div class="error">龙虎榜加载失败</div>';
    }
}
