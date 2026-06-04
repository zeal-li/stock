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

// 股票对象工厂（默认值均为 '-'）
function createStock(code, name, market, goodwill) {
    return { code, name, market, goodwill: goodwill || null,
        price: '-', pct: '-', change: '-', pe: '-', pb: '-',
        high: '-', low: '-', open: '-', pre_close: '-',
        total_shares: '-', float_shares: '-',
        turnover: '-', amplitude: '-', volume: '-', amount: '-',
        total_cap: '-', float_cap: '-',
    };
}

function loadPickedStocks() {
    try {
        let stocks = null;
        const raw = JSON.parse(localStorage.getItem('stockCache') || 'null');
        if (raw && raw.stocks) {
            const expired = raw.date !== getToday();
            stocks = raw.stocks.map(s => createStock(s.code, s.code, s.market,
                (!expired && s.gw !== undefined && s.pld !== undefined) ? {gw: s.gw, pld: s.pld} : null
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
        if (pickedStocks.length > 0) {
            renderPicked();
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
