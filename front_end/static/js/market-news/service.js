// ==================== 市场资讯 - 东方财富全球财经 ====================

var marketNewsLoading = false;
var currentNewsPage = 1;
var pageSize = 40;

function loadMarketNews() {
    var container = document.getElementById('marketNewsContent');
    if (!container) return;

    if (marketNewsLoading) return;
    marketNewsLoading = true;
    currentNewsPage = 1;
    container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">加载中...</div>';

    fetch('/api/market-news')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderMarketNews(data.data);
            } else {
                container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">' + (data.error || '获取失败') + '</div>';
            }
        })
        .catch(function(e) {
            container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">网络错误</div>';
        })
        .finally(function() {
            marketNewsLoading = false;
        });
}

function renderMarketNews(items) {
    var container = document.getElementById('marketNewsContent');
    if (!container) return;

    if (!items || items.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">暂无资讯</div>';
        return;
    }

    var totalPages = Math.ceil(items.length / pageSize);
    var start = (currentNewsPage - 1) * pageSize;
    var end = Math.min(start + pageSize, items.length);
    var pageItems = items.slice(start, end);

    var html = '';

    // 分页导航
    if (totalPages > 1) {
        html += '<div class="news-pager">' +
            '<span class="news-pager-info">共 ' + items.length + ' 条，第 ' + currentNewsPage + '/' + totalPages + ' 页</span>' +
            '<div class="news-pager-btns">';
        for (var p = 1; p <= totalPages; p++) {
            if (p === currentNewsPage) {
                html += '<span class="news-pager-btn active">' + p + '</span>';
            } else {
                html += '<span class="news-pager-btn" onclick="goNewsPage(' + p + ')">' + p + '</span>';
            }
        }
        html += '</div></div>';
    }

    for (var i = 0; i < pageItems.length; i++) {
        var item = pageItems[i];
        var globalIdx = start + i;

        html += '<a href="' + item.url + '" target="_blank" class="news-item">' +
            '<div class="news-body">' +
                '<div class="news-title">' + _escapeHtml(item.title) + '</div>' +
                (item.summary ? '<div class="news-desc">' + _escapeHtml(item.summary) + '</div>' : '') +
                '<div class="news-meta">' + _formatTime(item.time) + '</div>' +
            '</div>' +
        '</a>';
    }

    // 底部分页（超过10页才显示）
    if (totalPages > 1) {
        html += '<div class="news-pager" style="margin-top:12px;">' +
            '<div class="news-pager-btns">';
        var startPage = Math.max(1, currentNewsPage - 4);
        var endPage = Math.min(totalPages, currentNewsPage + 4);
        if (startPage > 1) {
            html += '<span class="news-pager-btn" onclick="goNewsPage(1)">1</span>';
            if (startPage > 2) html += '<span class="news-pager-dot">...</span>';
        }
        for (var q = startPage; q <= endPage; q++) {
            if (q === currentNewsPage) {
                html += '<span class="news-pager-btn active">' + q + '</span>';
            } else {
                html += '<span class="news-pager-btn" onclick="goNewsPage(' + q + ')">' + q + '</span>';
            }
        }
        if (endPage < totalPages) {
            if (endPage < totalPages - 1) html += '<span class="news-pager-dot">...</span>';
            html += '<span class="news-pager-btn" onclick="goNewsPage(' + totalPages + ')">' + totalPages + '</span>';
        }
        html += '</div></div>';
    }

    // 存储全量数据供翻页使用
    container._newsData = items;
    container.innerHTML = html;
}

function goNewsPage(page) {
    var container = document.getElementById('marketNewsContent');
    if (!container || !container._newsData) return;
    currentNewsPage = page;
    renderMarketNews(container._newsData);
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function _formatTime(timeStr) {
    if (!timeStr) return '';
    // 提取时间部分，去掉可能的多余内容
    var match = timeStr.match(/(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(:\d{2})?)/);
    if (match) return match[1];
    return timeStr.substring(0, 19);
}

function _escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
}
