// ==================== 自选股 ====================

var watchlistStocks = [];

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
