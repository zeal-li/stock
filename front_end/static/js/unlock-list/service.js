// ==================== 解禁列表 ====================

var unlockLoading = false;

function _fmtUnlockNum(value) {
    var num = Number(value);
    if (!isFinite(num)) return '-';
    if (num >= 1e8) return (num / 1e8).toFixed(2) + '亿股';
    if (num >= 1e4) return (num / 1e4).toFixed(2) + '万股';
    return num.toFixed(0) + '股';
}

function _fmtUnlockAmount(value) {
    var num = Number(value);
    if (!isFinite(num)) return '-';
    if (Math.abs(num) >= 100000000) {
        return (num / 100000000).toFixed(2) + '亿';
    }
    if (Math.abs(num) >= 10000) {
        return (num / 10000).toFixed(2) + '万';
    }
    return num.toFixed(2);
}

function _fmtUnlockRatio(value) {
    var num = Number(value);
    if (!isFinite(num)) return '-';
    return num.toFixed(2);
}

function loadUnlockList() {
    var container = document.getElementById('unlockListContent');
    if (!container) return;

    // 收集自选股代码
    var wlCodes = [];
    if (typeof watchlistStocks !== 'undefined' && watchlistStocks.length > 0) {
        wlCodes = watchlistStocks.map(function(s) { return s.code; });
    }

    // 收集选股代码
    var pickCodes = [];
    if (typeof pickedStocks !== 'undefined' && pickedStocks.length > 0) {
        pickCodes = pickedStocks.map(function(s) { return s.code; });
    }

    var allCodes = wlCodes.concat(pickCodes);
    allCodes = allCodes.filter(function(c, i) { return allCodes.indexOf(c) === i; }); // 去重

    if (allCodes.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">自选股和选股列表为空，请先添加股票</div>';
        return;
    }

    container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">加载中...</div>';
    unlockLoading = true;
    var btn = document.getElementById('unlockRefreshBtn');
    if (btn) btn.disabled = true;

    fetch('/api/lifting?codes=' + encodeURIComponent(allCodes.join(',')))
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderUnlockList(data.data);
            } else {
                container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">' + (data.error || '获取失败') + '</div>';
            }
        })
        .catch(function(e) {
            container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">网络错误</div>';
        })
        .finally(function() {
            unlockLoading = false;
            if (btn) btn.disabled = false;
        });
}

function renderUnlockList(records) {
    var container = document.getElementById('unlockListContent');
    if (!container) return;

    if (!records || records.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">暂无解禁数据</div>';
        return;
    }

    var html = '<div class="data-table"><table><thead><tr>' +
        '<th>代码</th><th>名称</th><th>解禁日期</th><th>解禁数量</th><th>解禁市值</th><th>解禁比例(%)</th><th>当前价</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < records.length; i++) {
        var r = records[i];
        html += '<tr>' +
            '<td style="color:#888;">' + (r.stock_code || '-') + '</td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + (r.stock_code || '') + '\',\'1\',\'' + (r.short_name || '') + '\')">' + (r.short_name || '-') + '</span></td>' +
            '<td style="color:#ad6800;font-weight:600;">' + (r.lift_date || '-') + '</td>' +
            '<td>' + _fmtUnlockNum(r.volume) + '</td>' +
            '<td>' + _fmtUnlockAmount(r.amount) + '</td>' +
            '<td>' + _fmtUnlockRatio(r.ratio) + '%</td>' +
            '<td>' + (r.price != null ? r.price : '-') + '</td>' +
            '</tr>';
    }
    html += '</tbody></table></div>';
    container.innerHTML = html;
}
