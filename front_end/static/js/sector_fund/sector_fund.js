/** 板块资金流向 — 行业/概念板块主力流入/流出排行 + 板块成分股 */
var _sectorFundData = null;
var _sectorFundType = 'concept';
var _currentSectorCode = null;
var _currentSectorName = null;

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
    // 切换时关闭股票池面板
    closeStockPool();
    document.querySelectorAll('.sector-tab').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-type') === type);
    });
    renderCurrentSectorTab();
}

function renderCurrentSectorTab() {
    if (!_sectorFundData) return;
    var data = _sectorFundData[_sectorFundType] || {};
    renderSectorTable('sectorInflowTable', data.inflow || [], true);
    renderSectorTable('sectorOutflowTable', data.outflow || [], false);
}

function showStockPool(sectorCode, sectorName) {
    _currentSectorCode = sectorCode;
    _currentSectorName = sectorName;

    var panel = document.getElementById('stockPoolPanel');
    var titleEl = document.getElementById('stockPoolTitle');
    if (!panel || !titleEl) return;

    titleEl.textContent = sectorName + ' — 成分股';
    panel.style.display = 'block';
    document.getElementById('stockPoolTableWrap').innerHTML = '<div class="loading">加载中...</div>';

    fetch('/api/sector-stocks?code=' + encodeURIComponent(sectorCode))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                document.getElementById('stockPoolTableWrap').innerHTML = '<div class="loading">暂无数据</div>';
                return;
            }
            renderStockPoolTable(res.stocks || [], res.total || 0);
        })
        .catch(function(e) {
            console.log('板块成分股加载失败:', e);
            document.getElementById('stockPoolTableWrap').innerHTML = '<div class="loading">加载失败</div>';
        });
}

function closeStockPool() {
    var panel = document.getElementById('stockPoolPanel');
    if (panel) panel.style.display = 'none';
    _currentSectorCode = null;
    _currentSectorName = null;
}

function renderStockPoolTable(list, total) {
    var wrap = document.getElementById('stockPoolTableWrap');
    if (!wrap) return;

    if (!list || list.length === 0) {
        wrap.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }

    var countInfo = total > list.length ? '（显示前' + list.length + '只，共' + total + '只）' : '（共' + list.length + '只）';

    var html = '<div class="stock-pool-count">' + countInfo + '</div>';
    html += '<table class="sector-fund-table stock-pool-table">';
    html += '<thead><tr>';
    html += '<th>#</th>';
    html += '<th>名称</th>';
    html += '<th>涨跌幅</th>';
    html += '<th>最新价</th>';
    html += '<th>主力净流入</th>';
    html += '<th>换手率</th>';
    html += '<th>振幅</th>';
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

        html += '<tr onclick="openStockDetail(\'' + item.code + '\',\'' + item.market + '\')" style="cursor:pointer">';
        html += '<td>' + (idx + 1) + '</td>';
        html += '<td class="col-name">' + (item.name || '-') + '</td>';
        html += '<td class="' + cls + '">' + pct + '</td>';
        html += '<td>' + (item.price || '-') + '</td>';
        html += '<td class="' + mainCls + '">' + mainNet + '</td>';
        html += '<td>' + (item.turnover || '-') + '</td>';
        html += '<td>' + (item.amplitude || '-') + '</td>';
        html += '</tr>';
    });

    html += '</tbody></table>';
    wrap.innerHTML = html;
}

function openStockDetail(code, market) {
    // 跳转到个股详情页（复用现有搜索逻辑）
    if (typeof showStockDetail === 'function') {
        showStockDetail(code, market);
    }
}

function renderSectorTable(containerId, list, isInflow) {
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

        var sectorCode = item.sector_code || '';
        var sectorName = item.name || '';

        html += '<tr onclick="showStockPool(\'' + sectorCode + '\',\'' + sectorName + '\')" style="cursor:pointer"';
        if (_currentSectorCode === sectorCode) {
            html += ' class="sector-row-active"';
        }
        html += '>';
        html += '<td>' + (idx + 1) + '</td>';
        html += '<td class="col-name">' + sectorName + '</td>';
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
