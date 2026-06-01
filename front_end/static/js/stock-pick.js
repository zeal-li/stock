// ==================== 选股 ====================

// 搜索相关状态
var searchTimer = null;
var searchResultsData = [];
var selectedSearchIdx = -1;

// 已选股票
var pickedStocks = [];

// 股票类型判断
function getStockType(code, market) {
    const c = (code || '').toString();
    const m = (market || '').toString();
    // 沪市
    if (m === '1' || m === '2') {
        if (/^68/.test(c)) return '科创';
        if (/^60|^900/.test(c)) return '沪A';
        if (/^51[0-9]/.test(c)) return '沪ETF';
        if (/^5[0-9]/.test(c)) return '沪基';
        if (/^11/.test(c)) return '沪债';
        return '沪市';
    }
    // 深市
    if (m === '0') {
        if (/^30[04]/.test(c)) return '创业';
        if (/^00[024]|^002|^003/.test(c)) return '深A';
        if (/^15[0-9]/.test(c)) return '深ETF';
        if (/^1[0-9]/.test(c)) return '深基';
        if (/^12/.test(c)) return '深债';
        return '深市';
    }
    // 北交所
    if (m === '90') return '北交所';
    if (m === '116') return '港股';
    if (m === '106') return '美股';
    if (/^1[0-5]/.test(m) && parseInt(m) >= 105) return '境外';
    return '';
}

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

function loadPickedStocks() {
    try {
        // 优先读取新版统一缓存
        let stocks = null;
        const raw = JSON.parse(localStorage.getItem('stockCache') || 'null');
        if (raw && raw.stocks) {
            const expired = raw.date !== getToday(); // 跨天→财务数据失效，但股票列表保留
            stocks = raw.stocks.map(s => ({
                code: s.code, name: s.code, market: s.market,
                price: '-', pct: '-', change: '-', pe: '-', pb: '-',
                turnover: '-', amplitude: '-', volume: '-', amount: '-',
                total_cap: '-', float_cap: '-',
                goodwill: (!expired && s.gw !== undefined && s.pld !== undefined) ? {gw: s.gw, pld: s.pld} : null,
            }));
        }
        // 兼容旧格式
        if (!stocks) {
            const saved = JSON.parse(localStorage.getItem('pickedStocks') || '[]');
            stocks = saved.map(s => ({ code: s.code, name: s.code, market: s.market, price: '-', pct: '-', change: '-', pe: '-', pb: '-', turnover: '-', amplitude: '-', volume: '-', amount: '-', total_cap: '-', float_cap: '-', goodwill: null }));
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
    pickedStocks.push({ code, name, market, price: '-', pct: '-', change: '-', pe: '-', pb: '-', turnover: '-', amplitude: '-', volume: '-', amount: '-', total_cap: '-', float_cap: '-', goodwill: null });
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
                    s.amplitude = q.amplitude || '-';
                    s.turnover = q.turnover || '-';
                    s.volume = q.volume || '-';
                    s.amount = q.amount || '-';
                    s.total_cap = q.total_cap || '-';
                    s.float_cap = q.float_cap || '-';
                }
            }
            renderPicked();
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
        if (hitCount > 0) renderPicked();
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
            renderPicked();
        }
    } catch(e) { console.log('商誉/质押加载失败:', e); }
}

function _fmtRate(v) {
    if (v == null || v === '' || v === '-' || v === 0) return '-';
    const n = parseFloat(v);
    if (isNaN(n) || n === 0) return '-';
    return n.toFixed(2) + '%';
}

function renderPicked() {
    const div = document.getElementById('pickedStocks');
    if (pickedStocks.length === 0) { div.innerHTML = ''; return; }
    let html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>涨跌额(幅)</th><th>成交量/额</th><th>总市值/流通市值</th><th>换手/振幅</th><th>PE(TTM)/PB</th><th>商誉率/质押率</th><th></th></tr></thead><tbody>';
    pickedStocks.forEach(s => {
        const type = getStockType(s.code, s.market);
        const chg = s.change || '-';
        const pct = s.pct || '-';
        const isUp = chg.startsWith('+') || parseFloat(chg) > 0;
        const isDown = chg.startsWith('-') || parseFloat(chg) < 0;
        const color = isUp ? '#e94560' : isDown ? '#4ade80' : '#888';
        const chgText = (chg !== '-' && pct !== '-') ? `${chg} (${pct})` : chg;
        html += `<tr>
            <td><span style="color:#888;">${s.code}</span></td>
            <td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open('${s.code}','${s.market}','${s.name}',{price:'${s.price}',pct:'${s.pct}',change:'${s.change}',pe:'${s.pe}',pb:'${s.pb}'})">${s.name}</span></td>
            <td><span style="color:#555;">${type}</span></td>
            <td><span style="color:${color};font-weight:bold;">${s.price}</span></td>
            <td><span style="color:${color};">${chgText}</span></td>
            <td><span style="color:#ddd;">${s.volume !== '-' && s.amount !== '-' ? s.volume + '/' + s.amount : s.volume}</span></td>
            <td><span style="color:#ddd;">${s.total_cap !== '-' && s.float_cap !== '-' ? s.total_cap + '/' + s.float_cap : s.total_cap}</span></td>
            <td><span style="color:#ddd;">${s.turnover !== '-' && s.amplitude !== '-' ? s.turnover + '/' + s.amplitude : s.turnover}</span></td>
            <td><span style="color:#ddd;">${s.pe + '/' + s.pb}</span></td>
            <td><span style="color:#ddd;">${s.goodwill ? _fmtRate(s.goodwill.gw) + '/' + _fmtRate(s.goodwill.pld) : '-'}</span></td>
            <td><span style="color:#e94560;cursor:pointer;font-size:16px;" onclick="removePicked('${s.code}')">&times;</span></td>
        </tr>`;
    });
    html += '</tbody></table></div>';
    div.innerHTML = html;
}
