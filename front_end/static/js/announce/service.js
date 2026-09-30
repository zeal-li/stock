// ==================== 公司公告 ====================

// column_code 重要性颜色标记
var _COLOR_MAP = {
    '001001001001001': '#e94560',
    '001001001001002': '#e94560',
    '001002002001001': '#e67e22',
    '001002005001008002': '#e67e22',
    '001002007005': '#e67e22',
    '001002009': '#e67e22',
    '001003002005': '#e67e22',
    '001003001001004': '#f1c40f',
    '001003002001': '#f1c40f',
    '001003003004': '#f1c40f',
    '001003003005': '#27ae60',
    '001002008': '#27ae60',
};

function _announceColor(columnCode) {
    return _COLOR_MAP[columnCode] || '#888';
}

var ANNOUNCE_CACHE_KEY = 'announceCache';
var ANNOUNCE_CACHE_TTL = 2 * 60 * 60 * 1000; // 2 小时

function _announceCacheRead() {
    try {
        var raw = localStorage.getItem(ANNOUNCE_CACHE_KEY);
        if (!raw) return null;
        var obj = JSON.parse(raw);
        if (obj && typeof obj.time === 'number' && Array.isArray(obj.data)) return obj;
    } catch (e) {}
    return null;
}

function _announceCacheWrite(cache) {
    try { localStorage.setItem(ANNOUNCE_CACHE_KEY, JSON.stringify(cache)); } catch (e) {}
}

function loadAnnounceList() {
    var container = document.getElementById('announceContent');
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
        try { localStorage.removeItem(ANNOUNCE_CACHE_KEY); } catch (e) {}
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">自选股和选股列表为空，请先添加股票</div>';
        return;
    }

    // 命中缓存：存在且未失效则不请求，同时清理缓存里多余的股票记录
    var cache = _announceCacheRead();
    if (cache && (Date.now() - cache.time) < ANNOUNCE_CACHE_TTL) {
        var codeSet = {};
        for (var i = 0; i < allCodes.length; i++) codeSet[String(allCodes[i])] = true;
        cache.data = cache.data.filter(function(r) { return codeSet[String(r.code)]; });
        _announceCacheWrite(cache);
        _announceRenderWithFilter(cache.data);
        return;
    }

    container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">加载中...</div>';

    fetch('/api/announcements?codes=' + encodeURIComponent(allCodes.join(',')))
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                _announceCacheWrite({ time: Date.now(), data: data.data });
                _announceRenderWithFilter(data.data);
            } else {
                container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">' + (data.error || '获取失败') + '</div>';
            }
        })
        .catch(function(e) {
            container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">网络错误</div>';
        });
}

function _announceRenderWithFilter(records) {
    var code = document.getElementById('announceStockFilter');
    var filterCode = code ? code.value : '';
    if (filterCode) {
        records = records.filter(function(r) { return String(r.code) === filterCode; });
    }
    renderAnnounceList(records);
}

function renderAnnounceList(records) {
    var container = document.getElementById('announceContent');
    if (!container) return;

    if (!records || records.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">暂无公告数据</div>';
        return;
    }

    var html = '<div class="data-table"><table><thead><tr>' +
        '<th>公告日期</th><th>代码</th><th>名称</th><th>公告类型</th><th>公告标题</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < records.length; i++) {
        var r = records[i];
        var color = _announceColor(r.column_code || '');
        html += '<tr>' +
            '<td style="white-space:nowrap;">' + (r.notice_date || '-') + '</td>' +
            '<td style="color:#888;">' + (r.code || '-') + '</td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + (r.code || '') + '\',\'' + (r.market || '1') + '\',\'' + (r.name || '') + '\')">' + (r.name || '-') + '</span></td>' +
            '<td><span style="color:' + color + ';font-weight:600;">' + (r.column_name || '-') + '</span></td>' +
            '<td><a href="' + (r.art_url || '#') + '" target="_blank" style="color:#fff;text-decoration:none;" onmouseover="this.style.color=\'#e94560\'" onmouseout="this.style.color=\'#fff\'">' + (r.title || '-') + '</a></td>' +
            '</tr>';
    }
    html += '</tbody></table></div>';
    container.innerHTML = html;
}
