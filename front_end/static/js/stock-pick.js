// ==================== 选股 ====================

// 搜索相关状态
var searchTimer = null;
var searchResultsData = [];
var selectedSearchIdx = -1;

// 已选股票
var pickedStocks = [];

// 股票搜索（防抖）
function debounceSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(searchStock, 300);
}

function handleSearchKey(e) {
    const items = document.querySelectorAll('#searchResults .stock-item');
    if (e.key === 'ArrowDown') {
        e.preventDefault();
        selectedSearchIdx = Math.min(selectedSearchIdx + 1, items.length - 1);
        updateSearchHighlight(items);
    } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        selectedSearchIdx = Math.max(selectedSearchIdx - 1, 0);
        updateSearchHighlight(items);
    } else if (e.key === 'Enter') {
        e.preventDefault();
        if (selectedSearchIdx >= 0 && selectedSearchIdx < items.length) {
            items[selectedSearchIdx].click();
        }
    }
}

function updateSearchHighlight(items) {
    items.forEach((item, i) => {
        item.style.background = i === selectedSearchIdx ? '#0f3460' : '#1a1a2e';
        item.style.borderColor = i === selectedSearchIdx ? '#e94560' : '#0f3460';
    });
}

async function searchStock() {
    const keyword = document.getElementById('searchInput').value.trim();
    const resultsDiv = document.getElementById('searchResults');
    if (!keyword) {
        resultsDiv.innerHTML = '<div style="text-align:center;color:#666;padding:12px 15px;">输入股票名称或代码开始搜索</div>';
        searchResultsData = []; selectedSearchIdx = -1;
        return;
    }
    if (keyword.length < 2) return;
    resultsDiv.innerHTML = '<div style="text-align:center;color:#888;padding:12px 15px;">搜索中...</div>';
    try {
        const res = await fetch('/api/search-stock?q=' + encodeURIComponent(keyword));
        const data = await res.json();
        if (data.success && data.data.length > 0) {
            searchResultsData = data.data;
            selectedSearchIdx = -1;
            let html = '<div style="display:flex;flex-direction:column;gap:4px;">';
            data.data.forEach((s, i) => {
                const type = getStockType(s.code, s.market);
                html += `<div class="stock-item" style="display:flex;align-items:center;gap:12px;padding:10px 15px;background:#1a1a2e;border-radius:6px;border:1px solid #0f3460;cursor:pointer;transition:background 0.15s;" onclick="pickStock('${s.code}','${s.name}','${s.market}')">
                    <span style="color:#fff;font-weight:bold;">${s.name}</span>
                    <span style="color:#888;font-size:12px;">${s.code}</span>
                    <span style="color:#555;font-size:12px;">${type}</span>
                </div>`;
            });
            html += '</div>';
            resultsDiv.innerHTML = html;
        } else {
            resultsDiv.innerHTML = '<div style="text-align:center;color:#666;padding:12px 15px;">未找到相关股票</div>';
            searchResultsData = [];
        }
    } catch(e) {
        resultsDiv.innerHTML = '<div style="text-align:center;color:#e94560;padding:12px 15px;">搜索失败</div>';
    }
}

// ========== 统一缓存（代码+商誉率+质押率，localStorage 单个 key） ==========
function getToday() { const d = new Date(); return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }

function saveCache() {
    const stocks = pickedStocks.map(s => ({
        code: s.code, market: s.market,
        gw: s.goodwill ? s.goodwill.gw : undefined,
        pld: s.goodwill ? s.goodwill.pld : undefined,
        addedDate: s.addedDate || undefined,
        addedPrice: s.addedPrice || undefined,
    }));
    localStorage.setItem('stockCache', JSON.stringify({ date: getToday(), stocks }));
}

function loadCache() {
    try {
        const raw = JSON.parse(localStorage.getItem('stockCache') || '{}');
        if (raw.date !== getToday()) return null; // 跨天失效
        return raw;
    } catch(e) { return null; }
}

// 股票对象工厂
function createStock(code, name, market, goodwill, info) {
    info = info || {};
    return { code, name, market, goodwill: goodwill || null,
        price: '-', pct: '-', change: '-', pe: '-', pb: '-',
        high: '-', low: '-', open: '-', pre_close: '-',
        total_shares: '-', float_shares: '-',
        turnover: '-', amplitude: '-', volume: '-', amount: '-',
        total_cap: '-', float_cap: '-',
        addedDate: info.addedDate || '', addedPrice: info.addedPrice || '',
    };
}

function loadPickedStocks() {
    try {
        let stocks = null;
        const raw = JSON.parse(localStorage.getItem('stockCache') || 'null');
        if (raw && raw.stocks) {
            const expired = raw.date !== getToday();
            stocks = raw.stocks.map(s => createStock(s.code, s.code, s.market,
                (!expired && s.gw !== undefined && s.pld !== undefined) ? {gw: s.gw, pld: s.pld} : null,
                { addedDate: s.addedDate || '', addedPrice: s.addedPrice || '' }
            ));
        }
        // 兼容旧格式
        if (!stocks) {
            const saved = JSON.parse(localStorage.getItem('pickedStocks') || '[]');
            stocks = saved.map(s => createStock(s.code, s.code, s.market));
            localStorage.removeItem('pickedStocks');
            localStorage.removeItem('financeCache');
        }
        pickedStocks = stocks;
        renderPicked();
        if (pickedStocks.length > 0) {
            refreshPickedQuotes();
            refreshGoodwill();
        }
    } catch(e) { console.log('恢复自选股失败:', e); }
}

async function pickStock(code, name, market) {
    if (pickedStocks.find(s => s.code === code)) return;
    pickedStocks.push(createStock(code, name, market));
    saveCache();
    document.getElementById('searchInput').value = '';
    document.getElementById('searchResults').innerHTML = '';
    searchResultsData = []; selectedSearchIdx = -1;
    renderPicked();
    refreshPickedQuotes();
    refreshGoodwill();
}

function removePicked(code) {
    pickedStocks = pickedStocks.filter(s => s.code !== code);
    saveCache();
    renderPicked();
}

async function refreshPickedQuotes() {
    if (pickedStocks.length === 0) return;
    const secids = pickedStocks.map(s => s.market + '.' + s.code).join(',');
    try {
        const res = await fetch('/api/stock-quotes?secids=' + encodeURIComponent(secids));
        const data = await res.json();
        if (data.success) {
            for (const s of pickedStocks) {
                const q = data.data[s.market + '.' + s.code];
                if (q) {
                    if (q.name) s.name = q.name;
                    s.price = q.price || '-';
                    s.pct = q.pct || '-';
                    s.change = q.change || '-';
                    s.pe = q.pe || '-';
                    s.pb = q.pb || '-';
                    s.high = q.high || '-';
                    s.low = q.low || '-';
                    s.open = q.open || '-';
                    s.pre_close = q.pre_close || '-';
                    s.total_shares = q.total_shares || '-';
                    s.float_shares = q.float_shares || '-';
                    s.amplitude = q.amplitude || '-';
                    s.turnover = q.turnover || '-';
                    s.volume = q.volume || '-';
                    s.amount = q.amount || '-';
                    s.total_cap = q.total_cap || '-';
                    s.float_cap = q.float_cap || '-';
                }
            }
            updatePickedPrices();  // 仅更新价格列，不重建整个表格
        }
    } catch(e) { console.log('报价刷新失败:', e); }
}

async function refreshGoodwill() {
    const cache = loadCache();
    // 有缓存直接合并
    if (cache && cache.stocks) {
        const gwMap = {};
        cache.stocks.forEach(s => { gwMap[s.code] = {gw: s.gw, pld: s.pld}; });
        let hitCount = 0;
        for (const s of pickedStocks) {
            if (gwMap[s.code] && gwMap[s.code].gw !== undefined) {
                s.goodwill = gwMap[s.code]; hitCount++;
            }
        }
        if (hitCount > 0) updatePickedGoodwill();
    }

    // 只请求未缓存的
    const needCodes = pickedStocks.filter(s => !s.goodwill).map(s => s.code);
    if (needCodes.length === 0) return;

    try {
        const res = await fetch('/api/goodwill?codes=' + encodeURIComponent(needCodes.join(',')));
        const data = await res.json();
        if (data.success) {
            for (const s of pickedStocks) {
                if (data.data[s.code]) {
                    s.goodwill = data.data[s.code];
                }
            }
            saveCache();
            updatePickedGoodwill();
        }
    } catch(e) { console.log('商誉/质押加载失败:', e); }
}

function _fmtRate(v) {
    if (v == null || v === '') return '-';  // null=无数据，显示-
    const n = parseFloat(v);
    if (isNaN(n)) return '-';
    return n.toFixed(2) + '%';  // 0 也正常显示 0.00%
}

function _chgColor(chg) {
    return (chg || '').startsWith('+') || parseFloat(chg) > 0 ? '#e94560' : (chg || '').startsWith('-') || parseFloat(chg) < 0 ? '#4ade80' : '#888';
}

function _chgText(chg, pct) {
    return (chg !== '-' && pct !== '-') ? `${chg} (${pct})` : chg;
}

function _pairText(a, b) {
    return a !== '-' && b !== '-' ? a + '/' + b : a;
}

function _joinDays(dateStr) {
    if (!dateStr) return '-';
    var d = new Date(), jd = new Date(dateStr);
    return Math.max(0, Math.floor((d - jd) / 86400000)) + '天';
}

function _joinChgText(s) {
    if (!s.addedPrice || s.price === '-') return '-';
    var ap = parseFloat(s.addedPrice), cp = parseFloat(s.price);
    if (isNaN(ap) || isNaN(cp) || ap === 0) return '-';
    var pct = (cp - ap) / ap * 100;
    var color = pct >= 0 ? '#e94560' : '#4ade80';
    var sign = pct >= 0 ? '+' : '';
    return '<span style="color:' + color + ';">' + s.addedPrice + ' / ' + sign + pct.toFixed(2) + '%</span>';
}

function renderPicked() {
    const div = document.getElementById('pickedStocks');
    if (pickedStocks.length === 0) { div.innerHTML = ''; return; }
    let html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>涨跌额(幅)</th><th>成交量/额</th><th>总市值/流通市值</th><th>换手/振幅</th><th>PE(TTM)/PB</th><th>商誉率/质押率</th><th></th></tr></thead><tbody>';
    pickedStocks.forEach(s => {
        const type = getStockType(s.code, s.market);
        const color = _chgColor(s.change);
        const chgText = _chgText(s.change, s.pct);
        html += `<tr data-code="${s.code}">
            <td><span style="color:#888;">${s.code}</span></td>
            <td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open('${s.code}','${s.market}','${s.name}')">${s.name}</span></td>
            <td><span style="color:#555;">${type}</span></td>
            <td class="cell-price"><span style="color:${color};font-weight:bold;">${s.price}</span></td>
            <td class="cell-chg"><span style="color:${color};">${chgText}</span></td>
            <td class="cell-vol"><span style="color:#ddd;">${_pairText(s.volume, s.amount)}</span></td>
            <td class="cell-cap"><span style="color:#ddd;">${_pairText(s.total_cap, s.float_cap)}</span></td>
            <td class="cell-to"><span style="color:#ddd;">${_pairText(s.turnover, s.amplitude)}</span></td>
            <td class="cell-pepb"><span style="color:#ddd;">${s.pe + '/' + s.pb}</span></td>
            <td class="cell-gw"><span style="color:#ddd;">${s.goodwill ? _fmtRate(s.goodwill.gw) + '/' + _fmtRate(s.goodwill.pld) : '-'}</span></td>
            <td><span style="color:#e94560;cursor:pointer;font-size:16px;" onclick="removePicked('${s.code}')">&times;</span></td>
        </tr>`;
    });
    html += '</tbody></table></div>';
    div.innerHTML = html;
}

// 增量更新：仅刷新价格相关列（避免全量 innerHTML 重建，消除闪烁）
function updatePickedPrices() {
    pickedStocks.forEach(s => {
        const row = document.querySelector(`tr[data-code="${s.code}"]`);
        if (!row) return;
        // 名称（首次获取后更新）
        const nameEl = row.cells[1] && row.cells[1].querySelector('span');
        if (nameEl && s.name !== '-' && nameEl.textContent !== s.name) { nameEl.textContent = s.name; nameEl.setAttribute('onclick', "KlinePopup.open('" + s.code + "','" + s.market + "','" + s.name + "')"); }
        // 价格 + 涨跌
        const color = _chgColor(s.change);
        _setCell(row, 'cell-price', s.price, color);
        _setCell(row, 'cell-chg', _chgText(s.change, s.pct), color);
        // 成交/市值/换手/PE
        _setCell(row, 'cell-vol', _pairText(s.volume, s.amount), '#ddd');
        _setCell(row, 'cell-cap', _pairText(s.total_cap, s.float_cap), '#ddd');
        _setCell(row, 'cell-to', _pairText(s.turnover, s.amplitude), '#ddd');
        _setCell(row, 'cell-pepb', s.pe + '/' + s.pb, '#ddd');
    });
}

// 增量更新：仅刷新商誉/质押列
function updatePickedGoodwill() {
    pickedStocks.forEach(s => {
        const row = document.querySelector(`tr[data-code="${s.code}"]`);
        _setCell(row, 'cell-gw', s.goodwill ? _fmtRate(s.goodwill.gw) + '/' + _fmtRate(s.goodwill.pld) : '-', '#ddd');
    });
}

function _setCell(row, cls, text, color) {
    const td = row && row.querySelector('.' + cls);
    if (!td) return;
    const span = td.querySelector('span');
    if (span) { span.textContent = text; span.style.color = color; }
}

// ==================== 自选股 ====================

var watchlistStocks = [];

function watchlistGetToday() { var d = new Date(); return d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0'); }

function watchlistSaveCache() {
    var stocks = watchlistStocks.map(function(s) { return { code: s.code, market: s.market, gw: s.goodwill ? s.goodwill.gw : undefined, pld: s.goodwill ? s.goodwill.pld : undefined, addedDate: s.addedDate || undefined, addedPrice: s.addedPrice || undefined }; });
    localStorage.setItem('watchlistCache', JSON.stringify({ date: watchlistGetToday(), stocks: stocks }));
}

function loadWatchlistStocks() {
    // 优先从 localStorage 恢复
    var stocks = null;
    var raw = JSON.parse(localStorage.getItem('watchlistCache') || 'null');
    if (raw && raw.stocks) {
        var expired = raw.date !== watchlistGetToday();
        stocks = raw.stocks.map(function(s) { return createStock(s.code, s.code, s.market, (!expired && s.gw !== undefined && s.pld !== undefined) ? { gw: s.gw, pld: s.pld } : null, { addedDate: s.addedDate || '', addedPrice: s.addedPrice || '' }); });
    }
    watchlistStocks = stocks || [];
    watchlistRender();
    if (watchlistStocks.length > 0) {
        refreshWatchlistQuotes();
        refreshWatchlistGoodwill();
    }
    // 异步从数据库同步（换电脑后首次用）
    if (!stocks) {
        fetch('/api/watchlist')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (!data.success || !data.data.length) return;
                watchlistStocks = data.data.map(function(s) {
                    var ad = s.created_at ? s.created_at.slice(0, 10) : '';
                    return createStock(s.code, s.code, s.market, null, { addedDate: ad, addedPrice: s.added_price || '' });
                });
                watchlistSaveCache();
                if (watchlistStocks.length > 0) {
                    watchlistRender();
                    refreshWatchlistQuotes();
                    refreshWatchlistGoodwill();
                }
            })
            .catch(function() {});
    }
}

// ---- 增删 ----
async function watchlistPickStock(code, market) {
    if (watchlistStocks.find(function(s) { return s.code === code; })) return;
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
            '<td class="cell-jc">' + _joinChgText(s) + '</td>' +
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
