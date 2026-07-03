/** 板块资金流向 — 行业/概念板块主力流入/流出排行 + 板块成分股 */

var _sectorFundType = 'concept';
var _sectorFundPeriod = 'today';
var _currentSectorCode = null;
var _currentSectorName = null;

function loadSectorFund(type, period) {
    _sectorFundType = type || _sectorFundType;
    _sectorFundPeriod = period || _sectorFundPeriod;

    // 仅在容器为空时显示 loading，刷新时保留已有数据避免闪烁
    var inflowEl = document.getElementById('sectorInflowTable');
    var outflowEl = document.getElementById('sectorOutflowTable');
    if (!inflowEl.querySelector('table')) inflowEl.innerHTML = '<div class="loading">加载中...</div>';
    if (!outflowEl.querySelector('table')) outflowEl.innerHTML = '<div class="loading">加载中...</div>';

    var url = '/api/sector-fund?type=' + _sectorFundType + '&period=' + _sectorFundPeriod;
    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                renderSectorTable('sectorInflowTable', []);
                renderSectorTable('sectorOutflowTable', []);
                return;
            }
            renderSectorTable('sectorInflowTable', res.inflow || [], true);
            renderSectorTable('sectorOutflowTable', res.outflow || [], false);
        })
        .catch(function(e) {
            console.log('板块资金加载失败:', e);
            renderSectorTable('sectorInflowTable', []);
            renderSectorTable('sectorOutflowTable', []);
        });
}

function switchSectorTab(type) {
    _sectorFundType = type;
    closeStockPool();
    document.querySelectorAll('.sector-tab[data-type]').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-type') === type);
    });
    loadSectorFund(type, _sectorFundPeriod);
}

function switchSectorPeriod(period) {
    _sectorFundPeriod = period;
    closeStockPool();
    document.querySelectorAll('.sector-tab[data-period]').forEach(function(t) {
        t.classList.toggle('active', t.getAttribute('data-period') === period);
    });
    loadSectorFund(_sectorFundType, period);
}

function showStockPool(sectorCode, sectorName, isInflow) {
    _currentSectorCode = sectorCode;
    _currentSectorName = sectorName;

    var panel = document.getElementById('stockPoolPanel');
    var titleEl = document.getElementById('stockPoolTitle');
    if (!panel || !titleEl) return;

    // 流入表格（左边）→ 面板浮到右边；流出表格（右边）→ 面板浮到左边
    if (isInflow) {
        panel.style.right = '0';
        panel.style.left = 'auto';
    } else {
        panel.style.left = '0';
        panel.style.right = 'auto';
    }

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

        html += '<tr onclick="openStockDetail(\'' + item.code + '\',\'' + item.market + '\',\'' + (item.name || '').replace(/'/g, "\\'") + '\')" style="cursor:pointer">';
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

function openStockDetail(code, market, name) {
    if (typeof KlinePopup !== 'undefined' && KlinePopup.open) {
        KlinePopup.open(code, market, name);
    }
}

function openLeadStockKline(code, name) {
    if (typeof KlinePopup !== 'undefined' && KlinePopup.open) {
        var market = code.startsWith('6') ? '1' : '0';
        KlinePopup.open(code, market, name);
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
    html += '<th>超大单</th>';
    html += '<th>大单</th>';
    html += '<th>中单</th>';
    html += '<th>小单</th>';
    html += '<th>领涨股</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    list.forEach(function(item, idx) {
        var pct = item.change_pct || '-';
        var cls = '';
        if (typeof pct === 'string') {
            cls = pct.startsWith('+') ? 'up' : (pct.startsWith('-') ? 'down' : '');
        }

        function amountCls(val) {
            if (typeof val === 'string') {
                return val.startsWith('+') ? 'up' : (val.startsWith('-') ? 'down' : '');
            }
            return '';
        }

        var mainNet = item.main_net || '-';
        var superNet = item.super_net || '-';
        var bigNet = item.big_net || '-';
        var midNet = item.mid_net || '-';
        var smallNet = item.small_net || '-';

        var sectorCode = item.sector_code || '';
        var sectorName = item.name || '';

        html += '<tr onclick="showStockPool(\'' + sectorCode + '\',\'' + sectorName + '\',' + isInflow + ')" style="cursor:pointer"';
        if (_currentSectorCode === sectorCode) {
            html += ' class="sector-row-active"';
        }
        html += '>';
        html += '<td>' + (idx + 1) + '</td>';
        html += '<td class="col-name ' + cls + '">' + sectorName + '</td>';
        html += '<td class="' + cls + '">' + pct + '</td>';
        html += '<td class="' + amountCls(mainNet) + '">' + mainNet + '</td>';
        html += '<td class="' + amountCls(superNet) + '">' + superNet + '</td>';
        html += '<td class="' + amountCls(bigNet) + '">' + bigNet + '</td>';
        html += '<td class="' + amountCls(midNet) + '">' + midNet + '</td>';
        html += '<td class="' + amountCls(smallNet) + '">' + smallNet + '</td>';
        var leadCode = item.lead_code || '';
        var leadName = item.lead_stock || '';
        if (leadCode && leadName) {
            html += '<td class="col-lead" onclick="event.stopPropagation();openLeadStockKline(\'' + leadCode + '\',\'' + leadName.replace(/'/g, "\\'") + '\')" style="cursor:pointer;" title="点击查看K线">' + leadName + '</td>';
        } else {
            html += '<td class="col-lead">' + (leadName || '-') + '</td>';
        }
        html += '</tr>';
    });

    html += '</tbody></table>';
    container.innerHTML = html;
}
