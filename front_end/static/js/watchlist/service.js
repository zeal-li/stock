// ==================== 自选股 ====================

var watchlistStocks = [];

var _currentWatchlistTab = 'watchlist';

function switchWatchlistTab(tab) {
    document.querySelectorAll('#page-watchlist .sector-tab').forEach(function(t) { t.classList.remove('active'); });
    document.querySelectorAll('.watchlist-tab-content').forEach(function(c) { c.classList.remove('active'); });
    document.querySelector('#page-watchlist .sector-tab[data-tab="' + tab + '"]').classList.add('active');
    document.getElementById('watchlist-tab-' + tab).classList.add('active');
    _currentWatchlistTab = tab;
    closeEtfPool();
    // 持仓汇总只在持仓 tab 时显示，且不管有没有数据都显示
    var summaryEl = document.getElementById('holdingsSummary');
    if (summaryEl) summaryEl.style.display = tab === 'holdings' ? 'flex' : 'none';
    if (tab === 'holdings') _holdingsUpdateSummary();
    // 切到新 tab 立即刷新一次行情
    if (tab === 'watchlist') refreshWatchlistQuotes();
    else if (tab === 'etf') refreshEtfQuotes();
    else if (tab === 'holdings') refreshHoldingsQuotes();
}

// ---- 搜索添加 ----
var _wlSearchTimer = null;

function wlDebounceSearch() {
    clearTimeout(_wlSearchTimer);
    _wlSearchTimer = setTimeout(wlSearchStock, 300);
}

function wlSearchKey(e) {
    var items = document.querySelectorAll('#wlSearchResults .watchlist-search-item');
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        _wlSearchHighlight(items, 1);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _wlSearchHighlight(items, -1);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        var sel = document.querySelector('#wlSearchResults .watchlist-search-item.wl-selected');
        if (sel) sel.click();
    } else if (e.key === 'Escape') {
        wlHideResults();
    }
}

var _wlSelectedIdx = -1;
function _wlSearchHighlight(items, dir) {
    _wlSelectedIdx = Math.max(0, Math.min(_wlSelectedIdx + dir, items.length - 1));
    items.forEach(function(it, i) {
        it.classList.toggle('wl-selected', i === _wlSelectedIdx);
        it.style.background = i === _wlSelectedIdx ? '#0f3460' : '#1a1a2e';
    });
}

function wlShowResults() {
    var val = document.getElementById('wlSearchInput').value.trim();
    if (val.length >= 2) {
        var dd = document.getElementById('wlSearchResults');
        if (dd.innerHTML) dd.style.display = 'block';
    }
}

function wlHideResults() {
    document.getElementById('wlSearchResults').style.display = 'none';
    _wlSelectedIdx = -1;
}

async function wlSearchStock() {
    var keyword = document.getElementById('wlSearchInput').value.trim();
    var dd = document.getElementById('wlSearchResults');
    if (!keyword || keyword.length < 2) { dd.innerHTML = ''; dd.style.display = 'none'; _wlSelectedIdx = -1; return; }
    dd.innerHTML = '<div style="text-align:center;color:#888;padding:8px;">搜索中...</div>';
    dd.style.display = 'block';
    try {
        var res = await fetch('/api/search-stock?q=' + encodeURIComponent(keyword));
        var data = await res.json();
        if (data.success && data.data.length > 0) {
            _wlSelectedIdx = -1;
            var html = '';
            data.data.forEach(function(s) {
                var type = getStockType(s.code, s.market);
                html += '<div class="watchlist-search-item" onclick="wlAddStock(\'' + s.code + '\',\'' + (s.name || '').replace(/'/g, '\\\'') + '\',\'' + s.market + '\')">' +
                    '<span class="wl-name">' + s.name + '</span>' +
                    '<span class="wl-code">' + s.code + '</span>' +
                    '<span class="wl-type">' + type + '</span></div>';
            });
            dd.innerHTML = html;
        } else {
            dd.innerHTML = '<div style="text-align:center;color:#666;padding:8px;">未找到相关股票</div>';
        }
    } catch(e) {
        dd.innerHTML = '<div style="text-align:center;color:#e94560;padding:8px;">搜索失败</div>';
    }
}

function wlAddStock(code, name, market) {
    // 判断当前激活的 tab，加入对应分组
    var activeTab = document.querySelector('#page-watchlist .sector-tab.active');
    var tab = activeTab ? activeTab.getAttribute('data-tab') : 'watchlist';
    if (tab === 'watchlist') {
        if (!watchlistStocks.find(function(s) { return s.code === code; })) {
            watchlistPickStock(code, market);
        }
    } else if (tab === 'etf') {
        if (!isETF(code, market)) {
            alert('场内ETF仅支持添加场内基金');
            return;
        }
        if (!etfStocks.find(function(s) { return s.code === code; })) {
            etfPickStock(code, market);
        }
    } else if (tab === 'holdings') {
        if (!holdingsStocks.find(function(s) { return s.code === code; })) {
            holdingsPickStock(code, market);
        }
    }
    // 清空搜索框
    document.getElementById('wlSearchInput').value = '';
    wlHideResults();
}

// 点击外部关闭下拉
document.addEventListener('click', function(e) {
    var box = document.querySelector('.watchlist-search-box');
    if (box && !box.contains(e.target)) wlHideResults();
});

function _joinChgText(s) {
    if (!s.addedPrice || s.price === '-') return '-';
    var ap = parseFloat(s.addedPrice), cp = parseFloat(s.price);
    if (isNaN(ap) || isNaN(cp) || ap === 0) return '-';
    var pct = (cp - ap) / ap * 100;
    var color = pct > 0 ? '#e94560' : (pct < 0 ? '#4ade80' : '#ddd');
    var sign = pct > 0 ? '+' : '';
    return '<span style="color:' + color + ';">' + s.addedPrice + ' / ' + sign + pct.toFixed(2) + '%</span>';
}

function _joinDays(dateStr) {
    if (!dateStr) return '-';
    var d = new Date(), jd = new Date(dateStr);
    return Math.max(0, Math.floor((d - jd) / 86400000)) + '天';
}

function watchlistGetToday() { var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }

function watchlistSaveCache() {
    var stocks = watchlistStocks.map(function(s) { return { code: s.code, market: s.market, gw: s.goodwill ? s.goodwill.gw : undefined, pld: s.goodwill ? s.goodwill.pld : undefined, addedDate: s.addedDate || undefined, addedPrice: s.addedPrice || undefined }; });
    localStorage.setItem('watchlistCache', JSON.stringify({ date: watchlistGetToday(), stocks: stocks }));
}

function loadWatchlistStocks() {
    fetch('/api/watchlist')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) throw new Error('API failed');
            // 读取缓存，仅用于补充商誉/质押等数据
            var cacheMap = {};
            var raw = JSON.parse(localStorage.getItem('watchlistCache') || 'null');
            if (raw && raw.stocks) {
                var expired = raw.date !== watchlistGetToday();
                raw.stocks.forEach(function(s) {
                    if (!expired && s.gw !== undefined && s.pld !== undefined) { cacheMap[s.code] = { gw: s.gw, pld: s.pld }; }
                });
            }
            // 以数据库列表为准，缓存补充数据
            var dbStocks = (data.data || []).map(function(s) {
                var ad = s.created_at ? s.created_at.slice(0, 10) : '';
                var goodwill = cacheMap[s.code] || null;
                return createStock(s.code, s.code, s.market, goodwill, { addedDate: ad, addedPrice: s.added_price || '' });
            });
            watchlistStocks = dbStocks;
            watchlistSaveCache();  // 清理缓存中多余的股票
            watchlistRender();
            if (watchlistStocks.length > 0) {
                refreshWatchlistQuotes();
                refreshWatchlistGoodwill();
            }
        })
        .catch(function() {
            // API 失败时降级到缓存作为兜底
            var raw = JSON.parse(localStorage.getItem('watchlistCache') || 'null');
            if (raw && raw.stocks) {
                var expired = raw.date !== watchlistGetToday();
                watchlistStocks = raw.stocks.map(function(s) {
                    return createStock(s.code, s.code, s.market,
                        (!expired && s.gw !== undefined && s.pld !== undefined) ? { gw: s.gw, pld: s.pld } : null,
                        { addedDate: s.addedDate || '', addedPrice: s.addedPrice || '' });
                });
                watchlistRender();
                if (watchlistStocks.length > 0) {
                    refreshWatchlistQuotes();
                    refreshWatchlistGoodwill();
                }
            }
        });
}

// ---- 增删 ----
var _watchlistPicking = false;
async function watchlistPickStock(code, market) {
    if (_watchlistPicking) return;
    if (watchlistStocks.find(function(s) { return s.code === code; })) return;
    _watchlistPicking = true;
    // 获取加入时的价格
    var addPrice = '';
    try {
        var res = await fetch('/api/stock-quotes?secids=' + encodeURIComponent(market + '.' + code));
        var d = await res.json();
        if (d.success) {
            var q = d.data[market + '.' + code];
            if (q && q.price && q.price !== '-') addPrice = q.price;
        }
    } catch(e) {}
    // 异步持久化到数据库
    var body = 'code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market);
    if (addPrice) body += '&added_price=' + encodeURIComponent(addPrice);
    fetch('/api/watchlist', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body })
        .catch(function() {});
    var info = { addedDate: watchlistGetToday(), addedPrice: addPrice };
    watchlistStocks.push(createStock(code, code, market, null, info));
    watchlistSaveCache();
    watchlistRender();
    refreshWatchlistQuotes();
    refreshWatchlistGoodwill();
    _watchlistPicking = false;
}

function watchlistEditAddedPrice(code, market) {
    var s = watchlistStocks.find(function(x) { return x.code === code; });
    if (!s) return;
    var jcTd = document.querySelector('tr[data-wcode="' + code + '"] .cell-jc');
    if (!jcTd || jcTd.querySelector('input')) return;
    var oldPrice = s.addedPrice || '';
    var confirmed = false;
    function doConfirm() {
        if (confirmed) return;
        confirmed = true;
        var newPrice = input.value.trim();
        s.addedPrice = newPrice;
        watchlistSaveCache();
        fetch('/api/watchlist/' + encodeURIComponent(code), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'market=' + encodeURIComponent(market) + '&added_price=' + encodeURIComponent(newPrice)
        }).catch(function() {});
        jcTd.innerHTML = _joinChgText(s);
    }
    function doCancel() {
        if (confirmed) return;
        confirmed = true;
        jcTd.innerHTML = _joinChgText(s);
    }
    var input = document.createElement('input');
    input.type = 'text';
    input.value = oldPrice;
    input.style.cssText = 'width:70px;background:#1a1a2e;color:#e94560;border:1px solid #e94560;padding:2px 4px;font-size:13px;text-align:center;';
    input.addEventListener('click', function(e) { e.stopPropagation(); });
    input.addEventListener('keydown', function(e) {
        e.stopPropagation();
        if (e.key === 'Enter') { doConfirm(); }
        else if (e.key === 'Escape') { doCancel(); }
    });
    input.addEventListener('blur', function() { doConfirm(); });
    jcTd.innerHTML = '';
    jcTd.appendChild(input);
    input.focus();
    input.select();
}

function watchlistRemoveStock(code, market) {
    // 异步从数据库删除
    fetch('/api/watchlist/' + encodeURIComponent(code) + '?market=' + encodeURIComponent(market), { method: 'DELETE' })
        .catch(function() {});
    watchlistStocks = watchlistStocks.filter(function(s) { return s.code !== code; });
    watchlistSaveCache();
    watchlistRender();
}

// ---- 行情刷新 ----
async function refreshWatchlistQuotes() {
    if (watchlistStocks.length === 0) return;
    var secids = watchlistStocks.map(function(s) { return s.market + '.' + s.code; }).join(',');
    try {
        var res = await fetch('/api/stock-quotes?secids=' + encodeURIComponent(secids));
        var data = await res.json();
        if (data.success) {
            watchlistStocks.forEach(function(s) {
                var q = data.data[s.market + '.' + s.code];
                if (q) {
                    if (q.name) s.name = q.name;
                    s.price = q.price || '-'; s.pct = q.pct || '-'; s.change = q.change || '-';
                    s.pe = q.pe || '-'; s.pb = q.pb || '-';
                    s.high = q.high || '-'; s.low = q.low || '-'; s.open = q.open || '-';
                    s.pre_close = q.pre_close || '-';
                    s.total_shares = q.total_shares || '-'; s.float_shares = q.float_shares || '-';
                    s.amplitude = q.amplitude || '-'; s.turnover = q.turnover || '-';
                    s.volume = q.volume || '-'; s.amount = q.amount || '-';
                    s.total_cap = q.total_cap || '-'; s.float_cap = q.float_cap || '-';
                }
            });
            watchlistUpdatePrices();
        }
    } catch(e) { console.log('自选股报价刷新失败:', e); }
}

async function refreshWatchlistGoodwill() {
    var needCodes = watchlistStocks.filter(function(s) { return !s.goodwill; }).map(function(s) { return s.code; });
    if (needCodes.length === 0) return;
    try {
        var res = await fetch('/api/goodwill?codes=' + encodeURIComponent(needCodes.join(',')));
        var data = await res.json();
        if (data.success) {
            watchlistStocks.forEach(function(s) {
                if (data.data[s.code]) { s.goodwill = data.data[s.code]; }
            });
            watchlistSaveCache();
            watchlistUpdateGoodwill();
        }
    } catch(e) { console.log('自选股商誉/质押加载失败:', e); }
}

// ---- 渲染 ----
function watchlistRender() {
    var div = document.getElementById('watchlistStocks');
    if (watchlistStocks.length === 0) { div.innerHTML = ''; return; }
    var html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>涨跌额(幅)</th><th>成交量/额</th><th>总市值/流通市值</th><th>换手/振幅</th><th>PE(TTM)/PB</th><th>商誉率/质押率</th><th>加选天数</th><th>加选价/涨幅</th><th></th></tr></thead><tbody>';
    watchlistStocks.forEach(function(s) {
        var type = getStockType(s.code, s.market);
        var color = _chgColor(s.change);
        var chgText = _chgText(s.change, s.pct);
        html += '<tr data-wcode="' + s.code + '">' +
            '<td><span style="color:#888;">' + s.code + '</span></td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + s.code + '\',\'' + s.market + '\',\'' + s.name + '\')">' + s.name + '</span></td>' +
            '<td><span style="color:#555;">' + type + '</span></td>' +
            '<td class="cell-price"><span style="color:' + color + ';font-weight:bold;">' + s.price + '</span></td>' +
            '<td class="cell-chg"><span style="color:' + color + ';">' + chgText + '</span></td>' +
            '<td class="cell-vol"><span style="color:#ddd;">' + _pairText(s.volume, s.amount) + '</span></td>' +
            '<td class="cell-cap"><span style="color:#ddd;">' + _pairText(s.total_cap, s.float_cap) + '</span></td>' +
            '<td class="cell-to"><span style="color:#ddd;">' + _pairText(s.turnover, s.amplitude) + '</span></td>' +
            '<td class="cell-pepb"><span style="color:#ddd;">' + s.pe + '/' + s.pb + '</span></td>' +
            '<td class="cell-gw"><span style="color:#ddd;">' + (s.goodwill ? _fmtRate(s.goodwill.gw) + '/' + _fmtRate(s.goodwill.pld) : '-') + '</span></td>' +
            '<td class="cell-jd"><span style="color:#ddd;">' + _joinDays(s.addedDate) + '</span></td>' +
            '<td class="cell-jc" style="cursor:pointer;" onclick="watchlistEditAddedPrice(\'' + s.code + '\',\'' + s.market + '\')" title="点击修改加选价格">' + _joinChgText(s) + '</td>' +
            '<td><span style="color:#e94560;cursor:pointer;font-size:16px;" onclick="watchlistRemoveStock(\'' + s.code + '\',\'' + s.market + '\')">&times;</span></td>' +
        '</tr>';
    });
    html += '</tbody></table></div>';
    div.innerHTML = html;
}

function watchlistUpdatePrices() {
    watchlistStocks.forEach(function(s) {
        var row = document.querySelector('tr[data-wcode="' + s.code + '"]');
        if (!row) return;
        var nameEl = row.cells[1] && row.cells[1].querySelector('span');
        if (nameEl && s.name !== '-' && nameEl.textContent !== s.name) { nameEl.textContent = s.name; nameEl.setAttribute('onclick', "KlinePopup.open('" + s.code + "','" + s.market + "','" + s.name + "')"); }
        var color = _chgColor(s.change);
        _setCell(row, 'cell-price', s.price, color);
        _setCell(row, 'cell-chg', _chgText(s.change, s.pct), color);
        _setCell(row, 'cell-vol', _pairText(s.volume, s.amount), '#ddd');
        _setCell(row, 'cell-cap', _pairText(s.total_cap, s.float_cap), '#ddd');
        _setCell(row, 'cell-to', _pairText(s.turnover, s.amplitude), '#ddd');
        _setCell(row, 'cell-pepb', s.pe + '/' + s.pb, '#ddd');
        var jdTd = row.querySelector('.cell-jd'); if (jdTd) { var jdSp = jdTd.querySelector('span'); if (jdSp) jdSp.textContent = _joinDays(s.addedDate); }
        var jcTd = row.querySelector('.cell-jc'); if (jcTd) jcTd.innerHTML = _joinChgText(s);
    });
}

function watchlistUpdateGoodwill() {
    watchlistStocks.forEach(function(s) {
        var row = document.querySelector('tr[data-wcode="' + s.code + '"]');
        _setCell(row, 'cell-gw', s.goodwill ? _fmtRate(s.goodwill.gw) + '/' + _fmtRate(s.goodwill.pld) : '-', '#ddd');
    });
}


// ==================== 场内ETF ====================

var etfStocks = [];

function loadEtfStocks() {
    fetch('/api/etf')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) throw new Error('API failed');
            etfStocks = (data.data || []).map(function(s) {
                var ad = s.created_at ? s.created_at.slice(0, 10) : '';
                return createStock(s.code, s.code, s.market, null, { addedDate: ad });
            });
            etfRender();
            if (etfStocks.length > 0) refreshEtfQuotes();
        })
        .catch(function() { etfStocks = []; etfRender(); });
}

var _etfPicking = false;
async function etfPickStock(code, market) {
    if (_etfPicking) return;
    if (etfStocks.find(function(s) { return s.code === code; })) return;
    _etfPicking = true;
    fetch('/api/etf', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: 'code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market) })
        .catch(function() {});
    etfStocks.push(createStock(code, code, market, null, {}));
    etfRender();
    refreshEtfQuotes();
    _etfPicking = false;
}

function etfRemoveStock(code, market) {
    fetch('/api/etf/' + encodeURIComponent(code) + '?market=' + encodeURIComponent(market), { method: 'DELETE' })
        .catch(function() {});
    etfStocks = etfStocks.filter(function(s) { return s.code !== code; });
    etfRender();
}

async function refreshEtfQuotes() {
    if (etfStocks.length === 0) return;
    var secids = etfStocks.map(function(s) { return s.market + '.' + s.code; }).join(',');
    try {
        var res = await fetch('/api/stock-quotes?secids=' + encodeURIComponent(secids));
        var data = await res.json();
        if (data.success) {
            etfStocks.forEach(function(s) {
                var q = data.data[s.market + '.' + s.code];
                if (q) {
                    if (q.name) s.name = q.name;
                    s.price = q.price || '-'; s.pct = q.pct || '-'; s.change = q.change || '-';
                    s.amplitude = q.amplitude || '-'; s.turnover = q.turnover || '-';
                    s.volume = q.volume || '-'; s.amount = q.amount || '-';
                    s.total_cap = q.total_cap || '-'; s.float_cap = q.float_cap || '-';
                }
            });
            etfUpdatePrices();
        }
    } catch(e) { console.log('场内ETF报价刷新失败:', e); }
}

function etfRender() {
    var div = document.getElementById('etfContent');
    if (etfStocks.length === 0) { div.innerHTML = ''; return; }
    var html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>涨跌额(幅)</th><th>成交量/额</th><th>总市值/流通市值</th><th>换手/振幅</th><th></th></tr></thead><tbody>';
    etfStocks.forEach(function(s) {
        var type = getStockType(s.code, s.market);
        var color = _chgColor(s.change);
        var chgText = _chgText(s.change, s.pct);
        html += '<tr data-ecode="' + s.code + '" onclick="showEtfPool(event,\'' + s.code + '\',\'' + s.market + '\',\'' + (s.name || '').replace(/'/g, '\\\'') + '\')" style="cursor:pointer">' +
            '<td><span style="color:#888;">' + s.code + '</span></td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="event.stopPropagation();KlinePopup.open(\'' + s.code + '\',\'' + s.market + '\',\'' + s.name + '\')">' + s.name + '</span></td>' +
            '<td><span style="color:#555;">' + type + '</span></td>' +
            '<td class="cell-price"><span style="color:' + color + ';font-weight:bold;">' + s.price + '</span></td>' +
            '<td class="cell-chg"><span style="color:' + color + ';">' + chgText + '</span></td>' +
            '<td class="cell-vol"><span style="color:#ddd;">' + _pairText(s.volume, s.amount) + '</span></td>' +
            '<td class="cell-cap"><span style="color:#ddd;">' + _pairText(s.total_cap, s.float_cap) + '</span></td>' +
            '<td class="cell-to"><span style="color:#ddd;">' + _pairText(s.turnover, s.amplitude) + '</span></td>' +
            '<td><span style="color:#e94560;cursor:pointer;font-size:16px;" onclick="event.stopPropagation();etfRemoveStock(\'' + s.code + '\',\'' + s.market + '\')">&times;</span></td>' +
        '</tr>';
    });
    html += '</tbody></table></div>';
    div.innerHTML = html;
    // 绑定拖拽
    var tbody = div.querySelector('.data-table tbody');
    if (tbody) _dragInit(tbody, etfStocks, 'ecode', '/api/etf/reorder');
}

function etfUpdatePrices() {
    etfStocks.forEach(function(s) {
        var row = document.querySelector('tr[data-ecode="' + s.code + '"]');
        if (!row) return;
        var nameEl = row.cells[1] && row.cells[1].querySelector('span');
        if (nameEl && s.name !== '-' && nameEl.textContent !== s.name) {
            nameEl.textContent = s.name;
            nameEl.setAttribute('onclick', "KlinePopup.open('" + s.code + "','" + s.market + "','" + s.name + "')");
            // 同步更新行的 onclick，让 showEtfPool 拿到最新名称
            row.setAttribute('onclick', "showEtfPool(event,'" + s.code + "','" + s.market + "','" + s.name + "')");
        }
        var color = _chgColor(s.change);
        _setCell(row, 'cell-price', s.price, color);
        _setCell(row, 'cell-chg', _chgText(s.change, s.pct), color);
        _setCell(row, 'cell-vol', _pairText(s.volume, s.amount), '#ddd');
        _setCell(row, 'cell-cap', _pairText(s.total_cap, s.float_cap), '#ddd');
        _setCell(row, 'cell-to', _pairText(s.turnover, s.amplitude), '#ddd');
    });
}


// ==================== ETF持仓股弹窗 ====================

var _currentEtfCode = null;
var _currentEtfMarket = null;

function _positionPoolPanel(panel, clickedRow) {
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var panelW = 380;
    var panelMaxH = vh * 0.8;

    // 确定弹窗右侧位置：尽量贴近右侧，但至少留 20px 给主内容
    var rightPos = 30;
    var leftPos = vw - panelW - rightPos;

    // 确定弹窗垂直位置：尽量与点击行对齐，但不出视口
    var topPos = 20;
    if (clickedRow) {
        var rowRect = clickedRow.getBoundingClientRect();
        topPos = Math.max(10, rowRect.top - 20);
        // 如果弹窗底部会超出视口，往上推
        if (topPos + panelMaxH > vh - 10) {
            topPos = Math.max(10, vh - panelMaxH - 10);
        }
    }

    panel.style.left = leftPos + 'px';
    panel.style.right = 'auto';
    panel.style.top = topPos + 'px';
}

function showEtfPool(e, code, market, name) {
    // 点击名称链接、删除按钮时不触发持仓股弹窗
    if (e && e.target) {
        var target = e.target;
        if (target.closest('span[onclick]') || target.tagName === 'INPUT' || target.closest('.stock-pool-close')) return;
    }
    if (_dragState.isDragging) return;
    _currentEtfCode = code;
    _currentEtfMarket = market;

    var panel = document.getElementById('etfPoolPanel');
    var titleEl = document.getElementById('etfPoolTitle');
    if (!panel || !titleEl) return;

    // 动态定位：根据点击行的视口位置
    var clickedRow = document.querySelector('tr[data-ecode="' + code + '"]');
    _positionPoolPanel(panel, clickedRow);

    titleEl.textContent = code + ' ' + name + ' — 持仓股';
    panel.style.display = 'block';
    document.getElementById('etfPoolTableWrap').innerHTML = '<div class="loading">加载中...</div>';

    fetch('/api/etf-stocks?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                document.getElementById('etfPoolTableWrap').innerHTML = '<div class="loading">暂无数据</div>';
                return;
            }
            renderEtfPoolTable(res.stocks || [], res.total || 0);
        })
        .catch(function(e) {
            console.log('ETF持仓股加载失败:', e);
            document.getElementById('etfPoolTableWrap').innerHTML = '<div class="loading">加载失败</div>';
        });
}

function closeEtfPool() {
    var panel = document.getElementById('etfPoolPanel');
    if (panel) {
        panel.style.display = 'none';
        panel.style.top = '';
        panel.style.left = '';
    }
    _currentEtfCode = null;
    _currentEtfMarket = null;
}

function renderEtfPoolTable(list, total) {
    var wrap = document.getElementById('etfPoolTableWrap');
    if (!wrap) return;

    if (!list || list.length === 0) {
        wrap.innerHTML = '<div class="loading">暂无数据</div>';
        return;
    }

    // 按持仓占比降序排序
    list.sort(function(a, b) {
        var ra = parseFloat((a.ratio || '0').replace('%', ''));
        var rb = parseFloat((b.ratio || '0').replace('%', ''));
        return rb - ra;
    });

    var countInfo = total > list.length ? '（显示前' + list.length + '只，共' + total + '只）' : '（共' + list.length + '只）';

    var html = '<div class="stock-pool-count">' + countInfo + '</div>';
    html += '<table class="sector-fund-table stock-pool-table">';
    html += '<thead><tr>';
    html += '<th>#</th>';
    html += '<th>股票代码</th>';
    html += '<th>股票名称</th>';
    html += '<th>最新价</th>';
    html += '<th>涨跌幅</th>';
    html += '<th>占净值比例</th>';
    html += '</tr></thead>';
    html += '<tbody>';

    list.forEach(function(item, idx) {
        var pct = item.change_pct || '-';
        var cls = '';
        if (typeof pct === 'string') {
            cls = pct.startsWith('+') ? 'up' : (pct.startsWith('-') ? 'down' : '');
        }

        html += '<tr onclick="openStockDetail(\'' + item.code + '\',\'' + item.market + '\',\'' + (item.name || '').replace(/'/g, "\\'") + '\')" style="cursor:pointer">';
        html += '<td>' + (idx + 1) + '</td>';
        html += '<td>' + (item.code || '-') + '</td>';
        html += '<td class="col-name">' + (item.name || '-') + '</td>';
        html += '<td>' + (item.price || '-') + '</td>';
        html += '<td class="' + cls + '">' + pct + '</td>';
        html += '<td>' + (item.ratio || '-') + '</td>';
        html += '</tr>';
    });

    html += '</tbody></table>';
    wrap.innerHTML = html;
}


// ==================== 长按拖拽排序 ====================

var _dragState = {
    timer: null,
    isDragging: false,
    dragRow: null,
    startY: 0,
    placeholder: null,
    stocksArr: null,
    dataAttr: '',
    apiUrl: '',
};

function _dragInit(tbody, stocksArr, dataAttr, apiUrl) {
    var rows = tbody.querySelectorAll('tr');
    rows.forEach(function(row) {
        row.removeEventListener('mousedown', _dragOnDown);
        row.removeEventListener('touchstart', _dragOnDown);
    });
    rows.forEach(function(row) {
        row.addEventListener('mousedown', _dragOnDown);
        row.addEventListener('touchstart', _dragOnDown, { passive: false });
    });
    _dragState.stocksArr = stocksArr;
    _dragState.dataAttr = dataAttr;
    _dragState.apiUrl = apiUrl;
}

function _dragOnDown(e) {
    // 排除可点击元素（删除按钮、加选价格、名称链接）
    if (e.target.closest('span[onclick]') || e.target.tagName === 'INPUT') return;
    clearTimeout(_dragState.timer);
    _dragState.isDragging = false;
    _dragState.dragRow = null;
    _dragState.placeholder = null;

    var y = e.type === 'touchstart' ? e.touches[0].clientY : e.clientY;
    _dragState.startY = y;
    var row = this;
    _dragState.pendingRow = row;
    _dragState.pendingY = y;

    // 长按500ms触发拖拽
    _dragState.timer = setTimeout(function() {
        _dragState.isDragging = true;
        _dragState.dragRow = row;
        row.classList.add('dragging');
        var ph = document.createElement('tr');
        ph.classList.add('drag-placeholder');
        ph.innerHTML = '<td colspan="' + row.cells.length + '" style="height:' + row.offsetHeight + 'px;"></td>';
        row.parentNode.insertBefore(ph, row.nextSibling);
        _dragState.placeholder = ph;
        // 切换监听：从pending切换到drag模式
        if (e.type === 'touchstart') {
            document.removeEventListener('touchmove', _dragOnTouchPending);
            document.removeEventListener('touchend', _dragOnTouchPendingEnd);
            document.addEventListener('touchmove', _dragOnMove, { passive: false });
            document.addEventListener('touchend', _dragOnUp);
        } else {
            document.removeEventListener('mousemove', _dragOnMousePending);
            document.removeEventListener('mouseup', _dragOnMousePendingEnd);
            document.addEventListener('mousemove', _dragOnMove);
            document.addEventListener('mouseup', _dragOnUp);
        }
    }, 500);

    if (e.type === 'touchstart') {
        document.addEventListener('touchmove', _dragOnTouchPending, { passive: false });
        document.addEventListener('touchend', _dragOnTouchPendingEnd);
    } else {
        document.addEventListener('mousemove', _dragOnMousePending);
        document.addEventListener('mouseup', _dragOnMousePendingEnd);
    }
}

// 等待长按触发期间，监听移动（超过阈值则取消长按）
function _dragOnMousePending(e) {
    if (_dragState.isDragging) return; // 已由timer切换监听，忽略
    if (Math.abs(e.clientY - _dragState.pendingY) > 5) {
        clearTimeout(_dragState.timer);
        document.removeEventListener('mousemove', _dragOnMousePending);
        document.removeEventListener('mouseup', _dragOnMousePendingEnd);
    }
}

function _dragOnMousePendingEnd(e) {
    clearTimeout(_dragState.timer);
    document.removeEventListener('mousemove', _dragOnMousePending);
    document.removeEventListener('mouseup', _dragOnMousePendingEnd);
}

function _dragOnTouchPending(e) {
    if (_dragState.isDragging) return; // 已由timer切换监听，忽略
    e.preventDefault(); // 阻止滚动，等长按判定
    var touch = e.touches[0];
    if (Math.abs(touch.clientY - _dragState.pendingY) > 10) {
        clearTimeout(_dragState.timer);
        document.removeEventListener('touchmove', _dragOnTouchPending);
        document.removeEventListener('touchend', _dragOnTouchPendingEnd);
    }
}

function _dragOnTouchPendingEnd(e) {
    clearTimeout(_dragState.timer);
    document.removeEventListener('touchmove', _dragOnTouchPending);
    document.removeEventListener('touchend', _dragOnTouchPendingEnd);
}

function _dragOnMove(e) {
    if (!_dragState.isDragging) return;
    var y = e.type === 'touchmove' ? e.touches[0].clientY : e.clientY;
    if (e.type === 'touchmove') e.preventDefault();

    var row = _dragState.dragRow;
    var tbody = row.parentNode;
    var dy = y - _dragState.startY;
    row.style.transform = 'translateY(' + dy + 'px)';
    row.style.position = 'relative';
    row.style.zIndex = '100';

    var rows = tbody.querySelectorAll('tr:not(.dragging):not(.drag-placeholder)');
    rows.forEach(function(r) { r.classList.remove('drag-over-top', 'drag-over-bottom'); });

    var dragRect = row.getBoundingClientRect();
    var dragCenterY = dragRect.top + dragRect.height / 2;

    for (var i = 0; i < rows.length; i++) {
        var rRect = rows[i].getBoundingClientRect();
        var rCenterY = rRect.top + rRect.height / 2;
        if (dragCenterY < rCenterY) {
            rows[i].classList.add('drag-over-top');
            tbody.insertBefore(_dragState.placeholder, rows[i]);
            break;
        }
        if (i === rows.length - 1) {
            rows[i].classList.add('drag-over-bottom');
            tbody.insertBefore(_dragState.placeholder, rows[i].nextSibling);
        }
    }
}

function _dragOnUp(e) {
    var eventType = e.type === 'touchend' ? 'touchmove' : 'mousemove';
    var endType = e.type === 'touchend' ? 'touchend' : 'mouseup';
    document.removeEventListener(eventType, _dragOnMove);
    document.removeEventListener(endType, _dragOnUp);
    if (!_dragState.isDragging) return;

    _dragState.isDragging = false;
    var row = _dragState.dragRow;
    row.classList.remove('dragging');
    row.style.transform = '';
    row.style.position = '';
    row.style.zIndex = '';

    row.parentNode.querySelectorAll('tr').forEach(function(r) {
        r.classList.remove('drag-over-top', 'drag-over-bottom');
    });

    if (_dragState.placeholder) {
        row.parentNode.insertBefore(row, _dragState.placeholder);
        row.parentNode.removeChild(_dragState.placeholder);
        _dragState.placeholder = null;
    }
    _dragState.dragRow = null;
    _dragSaveOrder();
}

function _dragSaveOrder() {
    // 根据当前 dataAttr 确定容器
    var containerMap = { 'wcode': 'watchlistStocks', 'ecode': 'etfContent', 'hcode': 'holdingsContent' };
    var containerId = containerMap[_dragState.dataAttr];
    var tbody = document.querySelector('#' + containerId + ' .data-table tbody');
    if (!tbody || !_dragState.stocksArr) return;

    var rows = tbody.querySelectorAll('tr');
    var newOrder = [];
    rows.forEach(function(row) {
        var code = row.getAttribute('data-' + _dragState.dataAttr);
        if (!code) return;
        var s = _dragState.stocksArr.find(function(st) { return st.code === code; });
        if (s) newOrder.push(s);
    });

    // 更新数组
    for (var i = 0; i < newOrder.length; i++) {
        _dragState.stocksArr[i] = newOrder[i];
    }

    // 保存到后端
    var items = newOrder.map(function(s, idx) {
        return [s.code, s.market, idx];
    });
    fetch(_dragState.apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'items=' + encodeURIComponent(JSON.stringify(items))
    }).then(function(r) { return r.json(); }).then(function(d) {
        if (!d.success) console.log('排序保存失败:', d.error);
    }).catch(function(e) { console.log('排序保存失败:', e); });

    if (_dragState.dataAttr === 'wcode') watchlistSaveCache();
}

// 在渲染后绑定拖拽
function watchlistRender() {
    var div = document.getElementById('watchlistStocks');
    if (watchlistStocks.length === 0) { div.innerHTML = ''; return; }
    var html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>涨跌额(幅)</th><th>成交量/额</th><th>总市值/流通市值</th><th>换手/振幅</th><th>PE(TTM)/PB</th><th>商誉率/质押率</th><th>加选天数</th><th>加选价/涨幅</th><th></th></tr></thead><tbody>';
    watchlistStocks.forEach(function(s) {
        var type = getStockType(s.code, s.market);
        var color = _chgColor(s.change);
        var chgText = _chgText(s.change, s.pct);
        html += '<tr data-wcode="' + s.code + '">' +
            '<td><span style="color:#888;">' + s.code + '</span></td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + s.code + '\',\'' + s.market + '\',\'' + s.name + '\')">' + s.name + '</span></td>' +
            '<td><span style="color:#555;">' + type + '</span></td>' +
            '<td class="cell-price"><span style="color:' + color + ';font-weight:bold;">' + s.price + '</span></td>' +
            '<td class="cell-chg"><span style="color:' + color + ';">' + chgText + '</span></td>' +
            '<td class="cell-vol"><span style="color:#ddd;">' + _pairText(s.volume, s.amount) + '</span></td>' +
            '<td class="cell-cap"><span style="color:#ddd;">' + _pairText(s.total_cap, s.float_cap) + '</span></td>' +
            '<td class="cell-to"><span style="color:#ddd;">' + _pairText(s.turnover, s.amplitude) + '</span></td>' +
            '<td class="cell-pepb"><span style="color:#ddd;">' + s.pe + '/' + s.pb + '</span></td>' +
            '<td class="cell-gw"><span style="color:#ddd;">' + (s.goodwill ? _fmtRate(s.goodwill.gw) + '/' + _fmtRate(s.goodwill.pld) : '-') + '</span></td>' +
            '<td class="cell-jd"><span style="color:#ddd;">' + _joinDays(s.addedDate) + '</span></td>' +
            '<td class="cell-jc" style="cursor:pointer;" onclick="watchlistEditAddedPrice(\'' + s.code + '\',\'' + s.market + '\')" title="点击修改加选价格">' + _joinChgText(s) + '</td>' +
            '<td><span style="color:#e94560;cursor:pointer;font-size:16px;" onclick="watchlistRemoveStock(\'' + s.code + '\',\'' + s.market + '\')">&times;</span></td>' +
        '</tr>';
    });
    html += '</tbody></table></div>';
    div.innerHTML = html;
    // 绑定拖拽
    var tbody = div.querySelector('.data-table tbody');
    if (tbody) _dragInit(tbody, watchlistStocks, 'wcode', '/api/watchlist/reorder');
}


// ==================== 持仓股 ====================

var holdingsStocks = [];

function _holdingsJoinDays(dateStr) {
    if (!dateStr) return '-';
    var d = new Date(), jd = new Date(dateStr);
    return Math.max(0, Math.floor((d - jd) / 86400000)) + '天';
}

function loadHoldingsStocks() {
    fetch('/api/holdings')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.success) throw new Error('API failed');
            holdingsStocks = (data.data || []).map(function(s) {
                var ad = s.created_at ? s.created_at.slice(0, 10) : '';
                return createStock(s.code, s.code, s.market, null, { addedDate: ad, holdPrice: s.hold_price || '', holdQty: s.hold_qty || '' });
            });
            holdingsRender();
            if (holdingsStocks.length > 0) refreshHoldingsQuotes();
        })
        .catch(function() { holdingsStocks = []; holdingsRender(); });
}

var _holdingsPicking = false;
async function holdingsPickStock(code, market) {
    if (_holdingsPicking) return;
    if (holdingsStocks.find(function(s) { return s.code === code; })) return;
    _holdingsPicking = true;
    var body = 'code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market);
    fetch('/api/holdings', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: body })
        .catch(function() {});
    holdingsStocks.push(createStock(code, code, market, null, { addedDate: watchlistGetToday(), holdPrice: '', holdQty: '' }));
    holdingsRender();
    refreshHoldingsQuotes();
    _holdingsPicking = false;
}

function _holdingsEditField(code, market, field, cellClass, placeholder, paramName) {
    var s = holdingsStocks.find(function(x) { return x.code === code; });
    if (!s) return;
    var td = document.querySelector('tr[data-hcode="' + code + '"] .' + cellClass);
    if (!td || td.querySelector('input')) return;
    var oldValue = s[field] || '';
    var confirmed = false;
    function doConfirm() {
        if (confirmed) return;
        confirmed = true;
        var newValue = input.value.trim();
        s[field] = newValue;
        fetch('/api/holdings/' + encodeURIComponent(code), {
            method: 'PUT',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: 'market=' + encodeURIComponent(market) + '&' + paramName + '=' + encodeURIComponent(newValue)
        }).catch(function() {});
        td.innerHTML = newValue || '<span style="color:#555;">' + placeholder + '</span>';
        // 刷新计算列和汇总
        var row = document.querySelector('tr[data-hcode="' + code + '"]');
        if (row) {
            var hmTd = row.querySelector('.cell-hm'); if (hmTd) hmTd.innerHTML = _holdingsMarketCap(s);
            var haTd = row.querySelector('.cell-ha'); if (haTd) haTd.innerHTML = _holdingsAmount(s);
            var dpTd = row.querySelector('.cell-dp'); if (dpTd) dpTd.innerHTML = _dailyProfit(s);
            var prTd = row.querySelector('.cell-pr'); if (prTd) prTd.innerHTML = _profitRate(s);
            var tpTd = row.querySelector('.cell-tp'); if (tpTd) tpTd.innerHTML = _totalProfit(s);
            var bbTd = row.querySelector('.cell-bb'); if (bbTd) bbTd.innerHTML = _backBreak(s);
        }
        _holdingsUpdateSummary();
    }
    function doCancel() {
        if (confirmed) return;
        confirmed = true;
        td.innerHTML = oldValue || '<span style="color:#555;">' + placeholder + '</span>';
    }
    var input = document.createElement('input');
    input.type = 'text';
    input.value = oldValue;
    input.style.cssText = 'width:70px;background:#1a1a2e;color:#e94560;border:1px solid #e94560;padding:2px 4px;font-size:13px;text-align:center;';
    input.addEventListener('click', function(e) { e.stopPropagation(); });
    input.addEventListener('keydown', function(e) {
        e.stopPropagation();
        if (e.key === 'Enter') { doConfirm(); }
        else if (e.key === 'Escape') { doCancel(); }
    });
    input.addEventListener('blur', function() { doConfirm(); });
    td.innerHTML = '';
    td.appendChild(input);
    input.focus();
    input.select();
}

function holdingsEditHoldPrice(code, market) {
    _holdingsEditField(code, market, 'holdPrice', 'cell-hp', '点击输入', 'hold_price');
}

function holdingsEditHoldQty(code, market) {
    _holdingsEditField(code, market, 'holdQty', 'cell-hq', '点击输入', 'hold_qty');
}

function holdingsRemoveStock(code, market) {
    fetch('/api/holdings/' + encodeURIComponent(code) + '?market=' + encodeURIComponent(market), { method: 'DELETE' })
        .catch(function() {});
    holdingsStocks = holdingsStocks.filter(function(s) { return s.code !== code; });
    holdingsRender();
}

async function refreshHoldingsQuotes() {
    if (holdingsStocks.length === 0) return;
    var secids = holdingsStocks.map(function(s) { return s.market + '.' + s.code; }).join(',');
    try {
        var res = await fetch('/api/stock-quotes?secids=' + encodeURIComponent(secids));
        var data = await res.json();
        if (data.success) {
            holdingsStocks.forEach(function(s) {
                var q = data.data[s.market + '.' + s.code];
                if (q) {
                    if (q.name) s.name = q.name;
                    s.price = q.price || '-'; s.pct = q.pct || '-'; s.change = q.change || '-';
                    s.amplitude = q.amplitude || '-'; s.turnover = q.turnover || '-';
                    s.volume = q.volume || '-'; s.amount = q.amount || '-';
                    s.total_cap = q.total_cap || '-'; s.float_cap = q.float_cap || '-';
                    s.pre_close = q.pre_close || '-';
                }
            });
            holdingsUpdatePrices();
        }
    } catch(e) { console.log('持仓股报价刷新失败:', e); }
}

function holdingsRender() {
    var div = document.getElementById('holdingsContent');
    if (holdingsStocks.length === 0) { div.innerHTML = ''; return; }
    var html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>涨跌额(幅)</th><th>换手/振幅</th><th>持仓天数</th><th>持仓价</th><th>持仓数</th><th>持仓市值</th><th>持仓成本</th><th>当天收益</th><th>收益率</th><th>总收益</th><th>回本涨幅</th><th></th></tr></thead><tbody>';
    holdingsStocks.forEach(function(s) {
        var type = getStockType(s.code, s.market);
        var color = _chgColor(s.change);
        var chgText = _chgText(s.change, s.pct);
        html += '<tr data-hcode="' + s.code + '">' +
            '<td><span style="color:#888;">' + s.code + '</span></td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + s.code + '\',\'' + s.market + '\',\'' + s.name + '\')">' + s.name + '</span></td>' +
            '<td><span style="color:#555;">' + type + '</span></td>' +
            '<td class="cell-price"><span style="color:' + color + ';font-weight:bold;">' + s.price + '</span></td>' +
            '<td class="cell-chg"><span style="color:' + color + ';">' + chgText + '</span></td>' +
            '<td class="cell-to"><span style="color:#ddd;">' + _pairText(s.turnover, s.amplitude) + '</span></td>' +
            '<td class="cell-jd"><span style="color:#ddd;">' + _holdingsJoinDays(s.addedDate) + '</span></td>' +
            '<td class="cell-hp" style="cursor:pointer;" onclick="holdingsEditHoldPrice(\'' + s.code + '\',\'' + s.market + '\')" title="点击输入持仓价">' + (s.holdPrice || '<span style="color:#555;">点击输入</span>') + '</td>' +
            '<td class="cell-hq" style="cursor:pointer;" onclick="holdingsEditHoldQty(\'' + s.code + '\',\'' + s.market + '\')" title="点击输入持仓数">' + (s.holdQty || '<span style="color:#555;">点击输入</span>') + '</td>' +
            '<td class="cell-hm">' + _holdingsMarketCap(s) + '</td>' +
            '<td class="cell-ha">' + _holdingsAmount(s) + '</td>' +
            '<td class="cell-dp">' + _dailyProfit(s) + '</td>' +
            '<td class="cell-pr">' + _profitRate(s) + '</td>' +
            '<td class="cell-tp">' + _totalProfit(s) + '</td>' +
            '<td class="cell-bb">' + _backBreak(s) + '</td>' +
            '<td><span style="color:#e94560;cursor:pointer;font-size:16px;" onclick="holdingsRemoveStock(\'' + s.code + '\',\'' + s.market + '\')">&times;</span></td>' +
        '</tr>';
    });
    html += '</tbody></table></div>';
    div.innerHTML = html;
    // 绑定拖拽
    var tbody = div.querySelector('.data-table tbody');
    if (tbody) _dragInit(tbody, holdingsStocks, 'hcode', '/api/holdings/reorder');
    _holdingsUpdateSummary();
}

function _fmtMoney(v) {
    if (Math.abs(v) >= 10000) return (v / 10000).toFixed(2) + '万';
    return v.toFixed(2);
}

function _holdingsMarketCap(s) {
    // 持仓市值 = 最新价 × 持仓数
    var price = parseFloat(s.price), qty = parseInt(s.holdQty);
    if (isNaN(price) || isNaN(qty) || qty === 0) return '-';
    var v = price * qty;
    return '<span style="color:#ddd;">' + _fmtMoney(v) + '</span>';
}

function _holdingsAmount(s) {
    // 持仓金额 = 持仓价 × 持仓数
    var holdPrice = parseFloat(s.holdPrice), qty = parseInt(s.holdQty);
    if (isNaN(holdPrice) || isNaN(qty) || qty === 0) return '-';
    var v = holdPrice * qty;
    return '<span style="color:#ddd;">' + _fmtMoney(v) + '</span>';
}

function _dailyProfit(s) {
    // 当天收益 = (最新价 - 昨收价) × 持仓数
    var price = parseFloat(s.price), preClose = parseFloat(s.pre_close), qty = parseInt(s.holdQty);
    if (isNaN(price) || isNaN(preClose) || isNaN(qty) || qty === 0) return '-';
    var v = (price - preClose) * qty;
    var color = v > 0 ? '#e94560' : (v < 0 ? '#4ade80' : '#ddd');
    var sign = v > 0 ? '+' : '';
    return '<span style="color:' + color + ';">' + sign + _fmtMoney(v) + '</span>';
}

function _profitRate(s) {
    // 收益率 = (最新价 - 持仓价) / 持仓价 × 100%
    var price = parseFloat(s.price), holdPrice = parseFloat(s.holdPrice);
    if (isNaN(price) || isNaN(holdPrice) || holdPrice === 0) return '-';
    var pct = (price - holdPrice) / holdPrice * 100;
    var color = pct > 0 ? '#e94560' : (pct < 0 ? '#4ade80' : '#ddd');
    var sign = pct > 0 ? '+' : '';
    return '<span style="color:' + color + ';">' + sign + pct.toFixed(2) + '%</span>';
}

function _totalProfit(s) {
    // 总收益 = (最新价 - 持仓价) × 持仓数
    var price = parseFloat(s.price), holdPrice = parseFloat(s.holdPrice), qty = parseInt(s.holdQty);
    if (isNaN(price) || isNaN(holdPrice) || isNaN(qty) || qty === 0) return '-';
    var v = (price - holdPrice) * qty;
    var color = v > 0 ? '#e94560' : (v < 0 ? '#4ade80' : '#ddd');
    var sign = v > 0 ? '+' : '';
    return '<span style="color:' + color + ';">' + sign + _fmtMoney(v) + '</span>';
}

function _backBreak(s) {
    // 回本涨幅 = (持仓价 / 最新价 - 1) × 100%，表示从当前价格涨回成本价所需的百分比
    var price = parseFloat(s.price), holdPrice = parseFloat(s.holdPrice);
    if (isNaN(price) || isNaN(holdPrice) || price <= 0) return '-';
    var v = (holdPrice / price - 1) * 100;
    if (v <= 0.005 && v >= -0.005) return '<span style="color:#ddd;">--</span>';
    var color = v > 0 ? '#e94560' : '#4ade80';
    var sign = v > 0 ? '+' : '';
    return '<span style="color:' + color + ';">' + sign + v.toFixed(2) + '%</span>';
}

function _holdingsUpdateSummary() {
    var dailySum = 0, totalSum = 0, capSum = 0, costSum = 0, yesterdayCapSum = 0;
    holdingsStocks.forEach(function(s) {
        var price = parseFloat(s.price), preClose = parseFloat(s.pre_close), holdPrice = parseFloat(s.holdPrice), qty = parseInt(s.holdQty);
        if (!isNaN(price) && !isNaN(preClose) && !isNaN(qty) && qty !== 0) {
            dailySum += (price - preClose) * qty;
        }
        if (!isNaN(price) && !isNaN(holdPrice) && !isNaN(qty) && qty !== 0) {
            totalSum += (price - holdPrice) * qty;
        }
        if (!isNaN(price) && !isNaN(qty) && qty !== 0) {
            capSum += price * qty;
        }
        if (!isNaN(holdPrice) && !isNaN(qty) && qty !== 0) {
            costSum += holdPrice * qty;
        }
        if (!isNaN(preClose) && !isNaN(qty) && qty !== 0) {
            yesterdayCapSum += preClose * qty;
        }
    });
    var summaryEl = document.getElementById('holdingsSummary');
    if (summaryEl) summaryEl.style.display = _currentWatchlistTab === 'holdings' ? 'flex' : 'none';
    var capEl = document.getElementById('holdingsCapSummary');
    if (capEl) capEl.textContent = _fmtMoney(capSum);
    var costEl = document.getElementById('holdingsCostSummary');
    if (costEl) costEl.textContent = _fmtMoney(costSum);
    var dailyEl = document.getElementById('holdingsDailySummary');
    var totalEl = document.getElementById('holdingsTotalSummary');
    if (dailyEl) {
        var color = dailySum > 0 ? '#e94560' : (dailySum < 0 ? '#4ade80' : '#ddd');
        var sign = dailySum > 0 ? '+' : '';
        var dailyPct = yesterdayCapSum !== 0 ? (dailySum / yesterdayCapSum * 100).toFixed(2) + '%' : '';
        var dailyPctSign = dailySum > 0 ? '+' : '';
        dailyEl.textContent = sign + _fmtMoney(dailySum) + (dailyPct ? '(' + dailyPctSign + dailyPct + ')' : '');
        dailyEl.style.color = color;
    }
    if (totalEl) {
        var color2 = totalSum > 0 ? '#e94560' : (totalSum < 0 ? '#4ade80' : '#ddd');
        var sign2 = totalSum > 0 ? '+' : '';
        var totalPct = costSum !== 0 ? (totalSum / costSum * 100).toFixed(2) + '%' : '';
        var totalPctSign = totalSum > 0 ? '+' : '';
        totalEl.textContent = sign2 + _fmtMoney(totalSum) + (totalPct ? '(' + totalPctSign + totalPct + ')' : '');
        totalEl.style.color = color2;
    }
}

function holdingsUpdatePrices() {
    holdingsStocks.forEach(function(s) {
        var row = document.querySelector('tr[data-hcode="' + s.code + '"]');
        if (!row) return;
        var nameEl = row.cells[1] && row.cells[1].querySelector('span');
        if (nameEl && s.name !== '-' && nameEl.textContent !== s.name) { nameEl.textContent = s.name; nameEl.setAttribute('onclick', "KlinePopup.open('" + s.code + "','" + s.market + "','" + s.name + "')"); }
        var color = _chgColor(s.change);
        _setCell(row, 'cell-price', s.price, color);
        _setCell(row, 'cell-chg', _chgText(s.change, s.pct), color);
        _setCell(row, 'cell-cap', _pairText(s.total_cap, s.float_cap), '#ddd');
        _setCell(row, 'cell-to', _pairText(s.turnover, s.amplitude), '#ddd');
        var jdTd = row.querySelector('.cell-jd'); if (jdTd) { var jdSp = jdTd.querySelector('span'); if (jdSp) jdSp.textContent = _holdingsJoinDays(s.addedDate); }
        var hmTd = row.querySelector('.cell-hm'); if (hmTd) hmTd.innerHTML = _holdingsMarketCap(s);
        var haTd = row.querySelector('.cell-ha'); if (haTd) haTd.innerHTML = _holdingsAmount(s);
        var dpTd = row.querySelector('.cell-dp'); if (dpTd) dpTd.innerHTML = _dailyProfit(s);
        var prTd = row.querySelector('.cell-pr'); if (prTd) prTd.innerHTML = _profitRate(s);
        var tpTd = row.querySelector('.cell-tp'); if (tpTd) tpTd.innerHTML = _totalProfit(s);
        var bbTd = row.querySelector('.cell-bb'); if (bbTd) bbTd.innerHTML = _backBreak(s);
    });
    _holdingsUpdateSummary();
}
