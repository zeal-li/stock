/** 全球市场 - 大宗商品行情 */
function loadGlobalCommodities() {
    fetch('/api/global-commodities')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success || !res.data) {
                renderCommodities([]);
                return;
            }
            renderCommodities(res.data);
        })
        .catch(function(e) {
            console.log('全球商品加载失败:', e);
            renderCommodities([]);
        });
}

function renderCommodities(list) {
    var container = document.getElementById('commodityGrid');
    if (!container) return;

    if (!list || list.length === 0) {
        container.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }

    var html = '';
    list.forEach(function(item) {
        var changeClass = '';
        var changeStr = item.change || '-';
        if (changeStr.startsWith('+')) {
            changeClass = 'up';
        } else if (changeStr.startsWith('-')) {
            changeClass = 'down';
        }

        html += '<div class="commodity-item">';
        html += '  <div class="commodity-name">' + (item.name || '-') + '</div>';
        html += '  <div class="commodity-price">' + (item.price || '-') + '</div>';
        html += '  <div class="commodity-changes">';
        html += '    <span class="' + changeClass + '">' + changeStr + '</span>';
        html += '    <span class="' + changeClass + '"> ' + (item.change_pct || '-') + '</span>';
        html += '  </div>';
        html += '</div>';
    });

    container.innerHTML = html;
}
