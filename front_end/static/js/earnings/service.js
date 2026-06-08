// ==================== 业绩报告 ====================

// 业绩预告类型颜色
var _PREDICT_COLOR = {
    '预增': '#27ae60', '扭亏': '#27ae60', '续盈': '#27ae60', '略增': '#f1c40f',
    '预减': '#e94560', '首亏': '#e94560', '续亏': '#e94560', '略减': '#e67e22',
    '不确定': '#888',
};

var _PERIOD_COLOR = { '年报': '#e94560', '半年报': '#e67e22', '一季报': '#f1c40f', '三季报': '#f1c40f' };

function _earnColor(rowType, period, subType) {
    if (rowType === '业绩预告') return _PREDICT_COLOR[subType] || '#888';
    return _PERIOD_COLOR[period] || '#888';
}

// 金额格式化（单位：元）
function _fmtYuan(val) {
    if (val == null || val === '' || val === '-') return '-';
    var n = Number(val);
    if (!isFinite(n)) return '-';
    var abs = Math.abs(n);
    if (abs >= 1e8) return (n / 1e8).toFixed(2) + '亿';
    if (abs >= 1e4) return (n / 1e4).toFixed(2) + '万';
    return n.toFixed(2);
}

function _fmtPct(val) {
    if (val == null || val === '' || val === '-') return '-';
    var n = Number(val);
    if (!isFinite(n)) return '-';
    var sign = n >= 0 ? '+' : '';
    return sign + n.toFixed(2) + '%';
}

function _calcChgPct(profit, lastProfit) {
    if (profit == null || profit === '' || profit === '-') return null;
    if (lastProfit == null || lastProfit === '' || lastProfit === '-') return null;
    var p = Number(profit), lp = Number(lastProfit);
    if (!isFinite(p) || !isFinite(lp) || lp === 0) return null;
    return ((p - lp) / Math.abs(lp) * 100);
}

function _earnDetail(r) {
    if (r.row_type === '业绩预告') {
        var profitRange = '-';
        var pl = r.profit_lower, pu = r.profit_upper;
        if (pl != null && pu != null && pl !== '' && pu !== '') {
            profitRange = _fmtYuan(pl) + ' ~ ' + _fmtYuan(pu);
        } else if (pl != null && pl !== '') {
            profitRange = '≥ ' + _fmtYuan(pl);
        } else if (pu != null && pu !== '') {
            profitRange = '≤ ' + _fmtYuan(pu);
        }
        var cl = _calcChgPct(r.profit_lower, r.last_profit);
        var cu = _calcChgPct(r.profit_upper, r.last_profit);
        var chg = '';
        if (cl != null && cu != null && Math.abs(cl - cu) > 0.1) {
            chg = '变动 ' + _fmtPct(Math.min(cl, cu)) + ' ~ ' + _fmtPct(Math.max(cl, cu));
        } else if (cl != null) {
            chg = '变动 ' + _fmtPct(cl);
        }
        var descParts = [];
        if (profitRange !== '-') descParts.push('预计净利 ' + profitRange);
        if (chg) descParts.push('同比' + chg.replace('变动', ''));
        return descParts.length > 0 ? descParts.join('，') : '-';
    }
    // 业绩快报 & 业绩报表
    var parts = [];
    if (r.eps != null && r.eps !== '') parts.push('每股收益 ' + Number(r.eps).toFixed(2) + '元');
    if (r.profit != null && r.profit !== '') parts.push('净利 ' + _fmtYuan(r.profit));
    if (r.revenue != null && r.revenue !== '') parts.push('营收 ' + _fmtYuan(r.revenue));
    if (r.profit_yoy != null && r.profit_yoy !== '') parts.push('净利同比 ' + _fmtPct(r.profit_yoy));
    if (r.revenue_yoy != null && r.revenue_yoy !== '') parts.push('营收同比 ' + _fmtPct(r.revenue_yoy));
    return parts.join(' | ');
}

function loadEarningsList() {
    var container = document.getElementById('earningsContent');
    if (!container) return;

    var wlCodes = [];
    if (typeof watchlistStocks !== 'undefined' && watchlistStocks.length > 0) {
        wlCodes = watchlistStocks.map(function(s) { return s.code; });
    }
    var pickCodes = [];
    if (typeof pickedStocks !== 'undefined' && pickedStocks.length > 0) {
        pickCodes = pickedStocks.map(function(s) { return s.code; });
    }
    var allCodes = wlCodes.concat(pickCodes);
    allCodes = allCodes.filter(function(c, i) { return allCodes.indexOf(c) === i; });

    if (allCodes.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">自选股和选股列表为空，请先添加股票</div>';
        return;
    }

    container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">加载中...</div>';

    fetch('/api/earnings?codes=' + encodeURIComponent(allCodes.join(',')))
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                var code = document.getElementById('earningsStockFilter');
                var filterCode = code ? code.value : '';
                var records = data.data;
                if (filterCode) {
                    records = records.filter(function(r) { return r.code === filterCode; });
                }
                renderEarningsList(records);
            } else {
                container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">' + (data.error || '获取失败') + '</div>';
            }
        })
        .catch(function(e) {
            container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">网络错误</div>';
        });
}

function renderEarningsList(records) {
    var container = document.getElementById('earningsContent');
    if (!container) return;

    if (!records || records.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">暂无业绩报告数据</div>';
        return;
    }

    var html = '<div class="data-table"><table><thead><tr>' +
        '<th>日期</th><th>代码</th><th>名称</th><th>类型</th><th>详情</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < records.length; i++) {
        var r = records[i];
        var color = _earnColor(r.row_type, r.period, r.sub_type);
        var detail = _earnDetail(r);
        var escCode = String(r.code || '').replace(/"/g, '&quot;');
        var escName = String(r.name || '').replace(/"/g, '&quot;');
        // 类型标签：业绩报表·年报 / 业绩预告·半年报·预增
        var typeLabel = r.row_type || '-';
        if (r.period) typeLabel += '·' + r.period;
        if (r.row_type === '业绩预告' && r.sub_type) typeLabel += '·' + r.sub_type;

        html += '<tr>' +
            '<td style="white-space:nowrap;">' + (r.notice_date || '-') + '</td>' +
            '<td style="color:#888;">' + (r.code || '-') + '</td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + escCode + '\',\'1\',\'' + escName + '\')">' + (r.name || '-') + '</span></td>' +
            '<td><span style="color:' + color + ';font-weight:600;">' + typeLabel + '</span></td>' +
            '<td style="max-width:420px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' +
            '<a href="' + (r.detail_url || '#') + '" target="_blank" style="color:#4da6ff;text-decoration:none;" onmouseover="this.style.color=\'#e94560\'" onmouseout="this.style.color=\'#4da6ff\'" title="' + detail.replace(/"/g, '&quot;') + '">' + detail + '</a>' +
            '</td>' +
            '</tr>';
    }
    html += '</tbody></table></div>';
    container.innerHTML = html;
}
