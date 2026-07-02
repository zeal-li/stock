/** 板块资金流向 — 行业/概念板块主力流入/流出排行 */
var _sectorFundData = null;
var _sectorFundType = 'concept';

function loadSectorFund() {
    fetch('/api/sector-fund')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                if (!_sectorFundData) {
                    renderSectorTable('sectorInflowTable', []);
                    renderSectorTable('sectorOutflowTable', []);
                }
                return;
            }
            _sectorFundData = res;
            renderCurrentSectorTab();
        })
        .catch(function(e) {
            console.log('板块资金加载失败:', e);
            if (!_sectorFundData) {
                renderSectorTable('sectorInflowTable', []);
                renderSectorTable('sectorOutflowTable', []);
            }
        });
}

function switchSectorTab(type) {
    _sectorFundType = type;
    // 更新按钮高亮
    document.querySelectorAll('.sector-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-type') === type);
    });
    renderCurrentSectorTab();
}

function renderCurrentSectorTab() {
    if (!_sectorFundData) return;
    var data = _sectorFundData[_sectorFundType] || {};
    renderSectorTable('sectorInflowTable', data.inflow || []);
    renderSectorTable('sectorOutflowTable', data.outflow || []);
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
