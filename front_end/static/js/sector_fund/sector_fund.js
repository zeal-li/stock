/** 板块资金流向 — 行业/概念板块主力净流入排行 */
var _sectorFundEverLoaded = false;

function loadSectorFund() {
    fetch('/api/sector-fund')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                if (!_sectorFundEverLoaded) {
                    renderSectorTable('industryFundTable', []);
                    renderSectorTable('conceptFundTable', []);
                }
                return;
            }
            _sectorFundEverLoaded = true;
            renderSectorTable('industryFundTable', res.industry || []);
            renderSectorTable('conceptFundTable', res.concept || []);
        })
        .catch(function(e) {
            console.log('板块资金加载失败:', e);
            if (!_sectorFundEverLoaded) {
                renderSectorTable('industryFundTable', []);
                renderSectorTable('conceptFundTable', []);
            }
        });
}

function renderSectorTable(containerId, list) {
    var container = document.getElementById(containerId);
    if (!container) return;

    if (!list || list.length === 0) {
        container.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }

    var html = '<table class="sector-fund-table">';
    html += '<thead><tr>';
    html += '<th>#</th>';
    html += '<th>板块</th>';
    html += '<th>涨跌幅</th>';
    html += '<th>主力净流入</th>';
    html += '<th>主力占比</th>';
    html += '<th>超大单</th>';
    html += '<th>大单</th>';
    html += '<th>领涨股</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    list.forEach(function(item, idx) {
        var pct = item.change_pct || '-';
        var cls = '';
        if (typeof pct === 'string') {
            cls = pct.startsWith('+') ? 'up' : (pct.startsWith('-') ? 'down' : '');
        }

        var mainCls = '';
        var mainNet = item.main_net || '-';
        if (typeof mainNet === 'string') {
            mainCls = mainNet.startsWith('+') ? 'up' : (mainNet.startsWith('-') ? 'down' : '');
        }

        html += '<tr>';
        html += '<td>' + (idx + 1) + '</td>';
        html += '<td class="col-name">' + (item.name || '-') + '</td>';
        html += '<td class="' + cls + '">' + pct + '</td>';
        html += '<td class="' + mainCls + '">' + mainNet + '</td>';
        html += '<td class="' + mainCls + '">' + (item.main_pct || '-') + '</td>';
        html += '<td class="' + (item.super_net && item.super_net.startsWith('+') ? 'up' : (item.super_net && item.super_net.startsWith('-') ? 'down' : '')) + '">' + (item.super_net || '-') + '</td>';
        html += '<td class="' + (item.big_net && item.big_net.startsWith('+') ? 'up' : (item.big_net && item.big_net.startsWith('-') ? 'down' : '')) + '">' + (item.big_net || '-') + '</td>';
        html += '<td class="col-lead">' + (item.lead_stock || '-') + '</td>';
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}
