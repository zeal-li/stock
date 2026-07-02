/** 全球市场 - 全球汇率渲染（数据由 /api/global-forex 接口返回） */
var _forexEverLoaded = false;

function loadGlobalForex() {
    fetch('/api/global-forex')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success || !res.data) {
                if (!_forexEverLoaded) {
                    renderForex([]);
                }
                return;
            }
            _forexEverLoaded = true;
            renderForex(res.data);
        })
        .catch(function(e) {
            console.log('全球汇率加载失败:', e);
            if (!_forexEverLoaded) {
                renderForex([]);
            }
        });
}

function renderForex(list) {
    var container = document.getElementById('forexGrid');
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

        html += '<a href="' + (item.url || '#') + '" target="_blank" class="commodity-link">';
        html += '<div class="commodity-item">';
        html += '  <div class="commodity-name">' + (item.name || '-') + '</div>';
        html += '  <div class="commodity-price ' + changeClass + '">' + (item.price || '-') + '</div>';
        html += '  <div class="commodity-changes">';
        html += '    <span class="' + changeClass + '">' + (item.change || '-') + '</span>';
        html += '    <span class="' + changeClass + '"> ' + (item.change_pct || '-') + '</span>';
        html += '  </div>';
        html += '</div>';
        html += '</a>';
    });

    container.innerHTML = html;
}
