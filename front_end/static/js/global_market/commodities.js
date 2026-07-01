/** 全球市场 - 大宗商品行情 */
var _commoditiesEverLoaded = false;

function loadGlobalCommodities() {
    fetch('/api/global-commodities')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success || !res.data) {
                // 刷新或页面切换时 API 异常，不覆盖已有数据，只在从未加载成功时才显示"暂无数据"
                if (!_commoditiesEverLoaded) {
                    renderCommodities([]);
                }
                return;
            }
            _commoditiesEverLoaded = true;
            renderCommodities(res.data);
        })
        .catch(function(e) {
            console.log('全球商品加载失败:', e);
            if (!_commoditiesEverLoaded) {
                renderCommodities([]);
            }
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
        if (item.gap) {
            html += '<div class="commodity-item commodity-gap"></div>';
            return;
        }
        var changeClass = '';
        var changeStr = item.change || '-';
        if (changeStr.startsWith('+')) {
            changeClass = 'up';
        } else if (changeStr.startsWith('-')) {
            changeClass = 'down';
        }

        html += '<div class="commodity-item">';
        html += '  <div class="commodity-name">' + (item.name || '-') + '</div>';
        html += '  <div class="commodity-price ' + changeClass + '">' + (item.price || '-') + '</div>';
        html += '  <div class="commodity-changes">';
        html += '    <span class="' + changeClass + '">' + changeStr + '</span>';
        html += '    <span class="' + changeClass + '"> ' + (item.change_pct || '-') + '</span>';
        html += '  </div>';
        html += '</div>';
    });

    container.innerHTML = html;
}
