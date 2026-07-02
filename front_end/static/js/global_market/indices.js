/** 全球市场 - 全球指数渲染（数据由 global-commodities 接口统一返回） */

function renderGlobalIndices(list) {
    var container = document.getElementById('globalIndexGrid');
    if (!container) return;
    if (!list || list.length === 0) {
        container.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }
    var html = '';
    list.forEach(function(item) {
        if (item.gap) {
            html += '<div class="commodity-item commodity-gap"></div>';
            return;
        }
        var changeStr = item.change || '-';
        var changeClass = '';
        if (changeStr.startsWith('+')) {
            changeClass = 'up';
        } else if (changeStr.startsWith('-')) {
            changeClass = 'down';
        }

        html += '<div class="commodity-item">';
        html += '  <div class="commodity-name">' + (item.name || '-') + '</div>';
        html += '  <div class="commodity-price ' + changeClass + '">' + (item.price || '-') + '</div>';
        html += '  <div class="commodity-changes">';
        html += '    <span class="' + changeClass + '">' + (item.change_value || '-') + '</span>';
        html += '    <span class="' + changeClass + '"> ' + (item.change || '-') + '</span>';
        html += '  </div>';
        html += '</div>';
    });
    container.innerHTML = html;
}
