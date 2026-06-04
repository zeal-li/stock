// ==================== 通用 K 线弹窗 ====================
// 使用：KlinePopup.open(code, market, name)
//       弹窗内部自己请求行情和K线数据

var KlinePopup = (function() {
    var _chart = null, _overlay = null, _series = null, _volSeries = null;
    var _observer = null;
    var _klinesData = null;
    var _stockCode = '';
    var _stockMarket = '';
    var _indicatorMode = 'ma';   // ma | bb
    var _currentPeriod = 'day';  // day | week | month
    var _isMinute = false;       // 是否分时模式
    var _minuteTimer = null;
    var _headerTimer = null;     // 头部行情刷新定时器
    var _minuteSeries = null;    // 分时面积图引用
    var _minuteAvgLine = null;   // 均价线引用
    var _minuteVolSeries = null; // 成交量柱引用
    var _minutePreClose = 0;
    var _minuteFrom = 0, _minuteTo = 0;  // 分时窗口固定范围
    var _fiveDayAreaSeries = null;   // 五日面积线
    var _fiveDayVolSeries = null;    // 五日成交量柱
    var _fiveDayPreClose = 0;        // 最新日昨收
    var _fiveDayRaw = null;          // 原始API数据，用于刷新最新一天
    var _fiveDayTimer = null;        // 五日刷新定时器
    var _maLines = [];
    var _bbLines = [];
    var _maVals = null;  // {ma5, ma10, ma20, ma60}
    var _bbVals = null;  // {up, mid, lo}

    // ---- 指标计算 ----
    function _calcSMA(data, period) {
        var r = [];
        for (var i = period - 1; i < data.length; i++) {
            var s = 0;
            for (var j = i - period + 1; j <= i; j++) s += data[j].close;
            r.push({ time: data[i].time, value: s / period });
        }
        return r;
    }
    function _calcBB(data) {
        var ma20 = _calcSMA(data, 20), up = [], mid = [], lo = [];
        for (var i = 0; i < ma20.length; i++) {
            var m = ma20[i];
            mid.push({ time: m.time, value: m.value });
            var idx = i + 19; // 在原始 data 中的索引
            var s = 0, n = 0;
            for (var j = Math.max(0, idx - 19); j <= idx; j++) { s += Math.pow(data[j].close - m.value, 2); n++; }
            var std = Math.sqrt(s / n);
            up.push({ time: m.time, value: m.value + 2 * std });
            lo.push({ time: m.time, value: m.value - 2 * std });
        }
        return { up: up, mid: mid, lo: lo };
    }

    // ---- 创建弹窗 DOM ----
    function _ensureDOM() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.id = 'klineOverlay';
        _overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:100;justify-content:center;align-items:center;';
        _overlay.onclick = function(e) { if (e.target === _overlay) close(); };

        _overlay.innerHTML =
            '<div style="width:1400px;max-width:98vw;height:720px;max-height:92vh;background:#1e1e2e;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,0.5);">' +
                '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:10px 16px 6px;background:#1a1a2e;flex-shrink:0;">' +
                    '<div style="display:flex;align-items:baseline;gap:8px;">' +
                        '<span id="klName" style="font-size:17px;color:#fff;font-weight:600;"></span>' +
                        '<span id="klCode" style="font-size:17px;color:#888;"></span>' +
                        '<span id="klPrice" style="font-size:14px;"></span>' +
                        '<span id="klChange" style="font-size:13px;"></span>' +
                    '</div>' +
                    '<div style="display:flex;align-items:center;gap:10px;">' +
                    '<span id="klWatchlistBtn" style="cursor:pointer;font-size:13px;padding:0 6px;line-height:1;white-space:nowrap;" onclick="KlinePopup._toggleWatchlist()"></span>' +
                    '<span style="color:#666;font-size:20px;cursor:pointer;padding:0 6px;line-height:1;" onclick="KlinePopup.close()">✕</span>' +
                    '</div>' +
                '</div>' +
                '<div id="klParams" style="padding:6px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;flex-shrink:0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:11px;color:#8b8b9e;">加载中...</div>' +
                '<div id="klPeriodBar" style="display:none;padding:4px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;flex-shrink:0;align-items:center;gap:6px;font-size:11px;color:#8b8b9e;">' +
                    '<button id="klBtnMinute" onclick="KlinePopup._toggleMinute()" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">分时</button>' +
                    '<button data-p="day" onclick="KlinePopup._switchPeriod(\'day\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#2a2a4e;color:#fff;">日K</button>' +
                    '<button data-p="week" onclick="KlinePopup._switchPeriod(\'week\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">周K</button>' +
                    '<button data-p="month" onclick="KlinePopup._switchPeriod(\'month\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">月K</button>' +
                    '<button data-p="5day" onclick="KlinePopup._switchPeriod(\'5day\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">五日</button>' +
                '</div>' +
                '<div id="klIndBar" style="display:none;padding:4px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;flex-shrink:0;align-items:center;gap:8px;font-size:11px;color:#8b8b9e;">' +
                    '<select id="klIndSelect" onchange="KlinePopup._switchIndicator(this.value)" style="cursor:pointer;font-size:10px;padding:1px 4px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#ccc;">' +
                        '<option value="ma">均线</option>' +
                        '<option value="bb">布林线</option>' +
                    '</select>' +
                    '<span id="klIndVals" style="font-size:11px;"></span>' +
                '</div>' +
                '<div id="klChart" style="flex:1;min-height:0;position:relative;overflow:hidden;">' +
                    '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>' +
                '</div>' +
            '</div>';
        document.body.appendChild(_overlay);
    }

    // ---- 分时 / 周期 切换 ----
    function _toggleMinute() {
        _isMinute = !_isMinute;
        if (_fiveDayTimer) { clearInterval(_fiveDayTimer); _fiveDayTimer = null; }
        var btn = document.getElementById('klBtnMinute');
        var indBar = document.getElementById('klIndBar');
        // 五日按钮还原
        var btn5d = document.querySelector('#klPeriodBar button[data-p="5day"]');
        if (btn5d) { btn5d.style.background = '#1a1a2e'; btn5d.style.color = '#8b8b9e'; }

        if (_isMinute) {
            btn.style.background = '#2a2a4e'; btn.style.color = '#fff';
            indBar.style.display = 'flex';
            indBar.innerHTML = '<span id="klMinuteVals" style="font-size:11px;color:#8b8b9e;"></span>';
            _loadMinuteChart();
        } else {
            btn.style.background = '#1a1a2e'; btn.style.color = '#8b8b9e';
            indBar.style.display = 'flex';
            indBar.innerHTML = '<select id="klIndSelect" onchange="KlinePopup._switchIndicator(this.value)"><option value="ma">均线</option><option value="bb">布林线</option></select><span id="klIndVals" style="font-size:11px;"></span>';
            _loadKlineChart();
            if (_minuteTimer) { clearInterval(_minuteTimer); _minuteTimer = null; }
        }
    }

    function _switchPeriod(p) {
        _isMinute = false;
        if (_minuteTimer) { clearInterval(_minuteTimer); _minuteTimer = null; }
        if (_fiveDayTimer) { clearInterval(_fiveDayTimer); _fiveDayTimer = null; }
        _currentPeriod = p;
        document.getElementById('klBtnMinute').style.background = '#1a1a2e';
        document.getElementById('klBtnMinute').style.color = '#8b8b9e';
        // 按钮样式
        var btns = document.querySelectorAll('#klPeriodBar button[data-p]');
        btns.forEach(function(b) {
            var act = b.getAttribute('data-p') === p;
            b.style.background = act ? '#2a2a4e' : '#1a1a2e';
            b.style.color = act ? '#fff' : '#8b8b9e';
        });
        var indBar = document.getElementById('klIndBar');

        if (p === '5day') {
            indBar.style.display = 'flex';
            indBar.innerHTML = '<span id="kl5DayVals" style="font-size:11px;color:#8b8b9e;"></span>';
            _loadFiveDayMinute();
            return;
        }

        indBar.style.display = 'flex';
        indBar.innerHTML = '<select id="klIndSelect" onchange="KlinePopup._switchIndicator(this.value)" style="cursor:pointer;font-size:10px;padding:1px 4px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#ccc;"><option value="ma">均线</option><option value="bb">布林线</option></select><span id="klIndVals" style="font-size:11px;"></span>';
        _loadKlineChart();
    }

    function _loadMinuteChart() {
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        var cached = _getCachedMinute();
        if (cached && !isMarketTradingTime(_stockMarket)) {
            try { _renderMinute(cached.times, cached.prices, cached.volumes || [], cached.amounts || [], cached.preClose || 0); }
            catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            return;
        }

        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket))
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">暂无分时数据</div>'; return; }
                _setCachedMinute(d.data);
                try { _renderMinute(d.data.times, d.data.prices, d.data.volumes || [], d.data.amounts || [], d.data.preClose || 0); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败</div>'; });
    }

    // ---- K线数据缓存（localStorage，总结构体 kl_cache） ----
    var KL_CACHE_KEY = 'kl_cache';

    function _getAllKlineCache() {
        try {
            var raw = localStorage.getItem(KL_CACHE_KEY);
            return raw ? JSON.parse(raw) : {};
        } catch(e) {}
        return {};
    }
    function _saveAllKlineCache(cache) {
        try { localStorage.setItem(KL_CACHE_KEY, JSON.stringify(cache)); } catch(e) {}
    }
    function _getCachedKlines(period) {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock[period] && stock[period].length > 0) ? stock[period] : null;
    }
    function _setCachedKlines(period, data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode][period] = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    // 跨天：删整个 kl_cache
    function _clearAllKlineCache() {
        try {
            var today = new Date().toISOString().slice(0, 10);
            var all = _getAllKlineCache();
            if (all._date !== today) {
                localStorage.removeItem(KL_CACHE_KEY);
            }
        } catch(e) {}
    }

    // 关闭弹窗时：开盘期间清K线+分时+行情+量比，商誉保留
    function _maybeClearCurrentKlines() {
        if (isMarketTradingTime(_stockMarket)) {
            try {
                var all = _getAllKlineCache();
                if (all[_stockCode]) {
                    delete all[_stockCode].day;
                    delete all[_stockCode].week;
                    delete all[_stockCode].month;
                    delete all[_stockCode].minute;
                    delete all[_stockCode].fiveday;
                    delete all[_stockCode].extra;
                    delete all[_stockCode].quotes;
                }
                all._date = new Date().toISOString().slice(0, 10);
                _saveAllKlineCache(all);
            } catch(e) {}
        }
    }

    // 商誉/质押缓存
    function _getCachedGoodwill() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.goodwill) ? stock.goodwill : null;
    }
    function _setCachedGoodwill(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].goodwill = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    // 量比/委比缓存
    function _getCachedExtra() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.extra) ? stock.extra : null;
    }
    function _setCachedExtra(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].extra = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    // 行情缓存
    function _getCachedQuotes() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.quotes) ? stock.quotes : null;
    }
    function _setCachedQuotes(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].quotes = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    // 分时数据缓存
    function _getCachedMinute() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.minute) ? stock.minute : null;
    }
    function _setCachedMinute(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].minute = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    // 五日分时缓存
    function _getCachedFiveDay() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.fiveday) ? stock.fiveday : null;
    }
    function _setCachedFiveDay(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].fiveday = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    function _loadKlineChart() {
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        // 先查缓存
        var cached = _getCachedKlines(_currentPeriod);
        if (cached) {
            _klinesData = cached;
            try { _renderChart({klines: _klinesData}); var sel2 = document.getElementById('klIndSelect'); if (sel2) sel2.value = _indicatorMode; _updateIndVals(); }
            catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            return;
        }

        fetch('/api/stock-kline?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket) + '&period=' + _currentPeriod)
            .then(function(r) { return r.json(); })
            .then(function(kdata) {
                if (!kdata.success || !kdata.data.klines || kdata.data.klines.length === 0) {
                    chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">暂无K线数据</div>';
                    return;
                }
                _klinesData = kdata.data.klines;
                _setCachedKlines(_currentPeriod, _klinesData);
                try { _renderChart(kdata.data); var sel = document.getElementById('klIndSelect'); if (sel) sel.value = _indicatorMode; _updateIndVals(); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败</div>'; });
    }

    function _loadFiveDayMinute() {
        _currentPeriod = '5day';
        if (_minuteTimer) { clearInterval(_minuteTimer); _minuteTimer = null; }
        if (_fiveDayTimer) { clearInterval(_fiveDayTimer); _fiveDayTimer = null; }
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">加载中...</div>';

        var cached = _getCachedFiveDay();
        if (cached && !isMarketTradingTime(_stockMarket)) {
            _fiveDayRaw = cached;
            _fiveDayPreClose = cached.preClose || 0;
            try { _renderFiveDayMinute(); } catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;">渲染失败: ' + e.message + '</div>'; }
            return;
        }

        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket) + '&days=5')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">暂无数据</div>'; return; }
                _fiveDayRaw = d.data;
                _fiveDayPreClose = d.data.preClose || 0;
                _setCachedFiveDay(d.data);
                try { _renderFiveDayMinute(); } catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;">渲染失败: ' + e.message + '</div>'; }
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;">请求失败</div>'; });
    }

    function _renderFiveDayMinute() {
        var el = document.getElementById('klChart');
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';

        var raw = _fiveDayRaw;
        var times = raw.times, prices = raw.prices, volumes = raw.volumes || [], amounts = raw.amounts || [];
        var isHK = _stockMarket === '116', isUS = _stockMarket === '106';
        var _isOverseas5D = isHK || isUS;  // 港股/美股五日模式

        if (_isOverseas5D) {
            // 港股/美股：直接用 Yahoo Finance 返回的实际数据点
            var _allSlots = [];
            var _tsToDate = {};
            var _dayBasePrice = {};
            var _sortedDates = [];
            var _seenDates = {};
            for (var i = 0; i < times.length; i++) {
                if (prices[i] == null) continue;
                var parts = times[i].split(' ');
                var date = parts[0], time = parts[1];
                var dp = date.split('-'), tp = time.split(':');
                var ts = Date.UTC(parseInt(dp[0]), parseInt(dp[1]) - 1, parseInt(dp[2]),
                                  parseInt(tp[0]), parseInt(tp[1])) / 1000;
                if (!_seenDates[date]) {
                    _sortedDates.push(date);
                    _seenDates[date] = true;
                    _dayBasePrice[date] = prices[i];
                }
                _tsToDate[ts] = date;
                _allSlots.push({ ts: ts, price: prices[i], vol: volumes[i] || 0, amt: amounts[i] || 0 });
            }
            if (_sortedDates.length === 0) { el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">无数据</div>'; return; }
            var allSlots = _allSlots, tsToDate = _tsToDate, dayBasePrice = _dayBasePrice, sortedDates = _sortedDates;
        } else {
            // A股：按日期分组原始数据，生成标准5分钟槽位
            var daySlots = {};
            for (var i = 0; i < times.length; i++) {
                if (prices[i] == null) continue;
                var p = times[i].split(' ');
                if (!daySlots[p[0]]) daySlots[p[0]] = {};
                daySlots[p[0]][p[1]] = { price: prices[i], vol: volumes[i] || 0, amt: amounts[i] || 0 };
            }
            var sortedDates = Object.keys(daySlots).sort();
            if (sortedDates.length === 0) { el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">无数据</div>'; return; }

            var allSlots = [];
            var tsToDate = {};
            var dayBasePrice = {};

            for (var di = 0; di < sortedDates.length; di++) {
                var ds = sortedDates[di];
                var dp = ds.split('-');
                var base = new Date(parseInt(dp[0]), parseInt(dp[1]) - 1, parseInt(dp[2])).getTime() / 1000;
                var slots = daySlots[ds];
                // 上午 09:35 ~ 11:30（5分钟K线实际数据起止时间）
                for (var t = base + 34500; t <= base + 41400; t += 300) {
                    var d2 = new Date(t * 1000);
                    var tk = String(d2.getHours()).padStart(2,'0') + ':' + String(d2.getMinutes()).padStart(2,'0');
                    var s2 = slots[tk];
                    tsToDate[t] = ds;
                    allSlots.push({ ts: t, price: s2 ? s2.price : null, vol: s2 ? s2.vol : 0, amt: s2 ? s2.amt : 0 });
                }
                // 下午 13:05 ~ 15:00（5分钟K线实际数据起止时间）
                for (var t = base + 47100; t <= base + 54000; t += 300) {
                    var d2 = new Date(t * 1000);
                    var tk = String(d2.getHours()).padStart(2,'0') + ':' + String(d2.getMinutes()).padStart(2,'0');
                    var s2 = slots[tk];
                    tsToDate[t] = ds;
                    allSlots.push({ ts: t, price: s2 ? s2.price : null, vol: s2 ? s2.vol : 0, amt: s2 ? s2.amt : 0 });
                }
            }

            // 计算每日基准价（第一个有效价格，用于算涨跌幅）
            for (var si = 0; si < allSlots.length; si++) {
                if (allSlots[si].price == null) continue;
                var dk = tsToDate[allSlots[si].ts];
                if (dk && !(dk in dayBasePrice)) dayBasePrice[dk] = allSlots[si].price;
            }
        }

        // ---- 创建图表 ----
        _chart = LightweightCharts.createChart(el, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', scaleMargins: { top: 0.08, bottom: 0.28 } },
            handleScroll: false,
            handleScale: { axisPressedMouseMove: false, pinch: false, mouseWheel: false },
            timeScale: {
                borderColor: '#2a2a4e',
                tickMarkFormatter: (function() {
                    var _lastDate = '';
                    return function(ts) {
                        var d3 = new Date(ts * 1000);
                        var label = (d3.getMonth() + 1) + '/' + d3.getDate();
                        if (label === _lastDate) return '';
                        _lastDate = label;
                        return label;
                    };
                })(),
            },
            width: el.clientWidth, height: el.clientHeight,
        });

        // ---- 价格面积线 ----
        var areaData = [];
        for (var si = 0; si < allSlots.length; si++) {
            if (allSlots[si].price != null) areaData.push({ time: allSlots[si].ts, value: allSlots[si].price });
        }
        var _priceDec = _isOverseas5D ? 3 : 2;
        var areaSeries = _chart.addAreaSeries({
            lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)',
            lineWidth: 1.5, priceLineVisible: false,
            priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(_priceDec); } }
        });
        areaSeries.setData(areaData);
        _fiveDayAreaSeries = areaSeries;

        // ---- 五日均价线（五日累计均价） ----
        var avgLineData = [], avgSum = 0, avgCnt = 0;
        for (var si = 0; si < allSlots.length; si++) {
            if (allSlots[si].price != null) { avgSum += allSlots[si].price; avgCnt++; }
            avgLineData.push({ time: allSlots[si].ts, value: avgCnt > 0 ? avgSum / avgCnt : null });
        }
        var avgLine = _chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgLineData);

        // ---- 成交量柱 ----
        var volSeries = _chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'volume' });
        _chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
        var vd = [];
        for (var si = 0; si < allSlots.length; si++) {
            var s2 = allSlots[si];
            if (s2.price == null) continue;
            var up = si > 0 ? (allSlots[si-1].price != null ? s2.price >= allSlots[si-1].price : true) : true;
            vd.push({ time: s2.ts, value: s2.vol, color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
        }
        volSeries.setData(vd);
        _fiveDayVolSeries = volSeries;

        // ---- 十字线 tooltip ----
        var firstBase = dayBasePrice[sortedDates[0]] || 0;  // 五日首日基准价
        var tooltip = document.getElementById('klTooltip');
        _chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point) { tooltip.style.display = 'none'; return; }
            var slot = null, slotIdx = -1;
            for (var si = 0; si < allSlots.length; si++) { if (allSlots[si].ts === param.time) { slot = allSlots[si]; slotIdx = si; break; } }
            if (!slot || slot.price == null) { tooltip.style.display = 'none'; return; }
            var d4 = new Date(param.time * 1000);
            var weekNames = ['周日','周一','周二','周三','周四','周五','周六'];
            var ds2 = d4.getFullYear() + '-' + String(d4.getMonth() + 1).padStart(2,'0') + '-' + String(d4.getDate()).padStart(2,'0') + ' ' + weekNames[d4.getDay()];
            var ts2 = String(d4.getHours()).padStart(2,'0') + ':' + String(d4.getMinutes()).padStart(2,'0');
            // 五日累计均价
            var curAvg = avgLineData[slotIdx] ? avgLineData[slotIdx].value : null;
            // 涨跌幅：相对五日首日第一个价
            var chgPct = firstBase ? (slot.price - firstBase) / firstBase * 100 : 0;
            var chgSign = chgPct >= 0 ? '+' : '', chgColor = chgPct >= 0 ? '#ef5350' : '#26a69a';
            var volStr = slot.vol >= 1e8 ? (slot.vol/1e8).toFixed(2)+'亿' : slot.vol >= 1e4 ? (slot.vol/1e4).toFixed(2)+'万' : String(slot.vol);
            var amtStr = slot.amt >= 1e8 ? (slot.amt/1e8).toFixed(2)+'亿' : slot.amt >= 1e4 ? (slot.amt/1e4).toFixed(2)+'万' : String(slot.amt);
            tooltip.innerHTML = '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">'+ds2+' '+ts2+'</div><table style="border-spacing:0;">'+
                '<tr><td style="color:#888;">价格</td><td><span style="color:#3b82f6;">'+slot.price.toFixed(_priceDec)+'</span></td></tr>'+
                '<tr><td style="color:#888;">均价</td><td><span style="color:#fbbf24;">'+(curAvg != null ? curAvg.toFixed(_priceDec) : '--')+'</span></td></tr>'+
                '<tr><td style="color:#888;">涨幅</td><td><span style="color:'+chgColor+';">'+chgSign+chgPct.toFixed(2)+'%</span></td></tr>'+
                '<tr><td style="color:#888;">成交</td><td><span style="color:#ddd;">'+volStr+'</span></td></tr>'+
                '<tr><td style="color:#888;">成交额</td><td><span style="color:#ddd;">'+amtStr+'</span></td></tr></table>';
            tooltip.style.display = 'block';
            var rect = el.getBoundingClientRect();
            var l = param.point.x + 16, tp = param.point.y - 10;
            if (l + 120 > rect.width) l = param.point.x - 130;
            if (tp + 80 > rect.height) tp = rect.height - 90;
            if (tp < 0) tp = 0;
            tooltip.style.left = l + 'px'; tooltip.style.top = tp + 'px';
        });

        // ---- 底部指标栏 ----
        var lastP = null, lastAvg = null;
        var firstBase = dayBasePrice[sortedDates[0]] || 0;  // 五日首日基准
        for (var li = allSlots.length - 1; li >= 0; li--) {
            if (allSlots[li].price != null) { lastP = allSlots[li].price; break; }
        }
        for (var ai = avgLineData.length - 1; ai >= 0; ai--) {
            if (avgLineData[ai].value != null) { lastAvg = avgLineData[ai].value; break; }
        }
        if (lastP != null && firstBase) {
            var lChg = lastP - firstBase, lChgPct = firstBase ? lChg / firstBase * 100 : 0;
            var lc = lChg >= 0 ? '#ef5350' : '#26a69a', ls2 = lChg >= 0 ? '+' : '';
            var m5v = document.getElementById('kl5DayVals');
            if (m5v) m5v.innerHTML = '<span style="color:#fbbf24;">均价:'+(lastAvg != null ? lastAvg.toFixed(_priceDec):'--')+'</span> <span style="color:#3b82f6;">最新:'+lastP.toFixed(_priceDec)+'</span> <span style="color:'+lc+';">'+ls2+lChg.toFixed(2)+'</span> <span style="color:'+lc+';">'+ls2+lChgPct.toFixed(2)+'%</span>';
        }

        _chart.timeScale().fitContent();
        _chart.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true });

        // ---- 绘制日间分隔竖虚线 ----
        function _drawDayBounds() {
            el.querySelectorAll('.five-day-boundary').forEach(function(b) { b.remove(); });
            for (var di = 0; di < sortedDates.length - 1; di++) {
                var dp2 = sortedDates[di].split('-');
                var dayEndTs;
                if (_isOverseas5D) {
                    // 港股/美股：用该日期最后一个数据点的时间
                    dayEndTs = 0;
                    for (var si = 0; si < allSlots.length; si++) {
                        if (tsToDate[allSlots[si].ts] === sortedDates[di] && allSlots[si].ts > dayEndTs) {
                            dayEndTs = allSlots[si].ts;
                        }
                    }
                } else {
                    // A股：固定15:00（匹配最后5分钟K线）
                    dayEndTs = new Date(parseInt(dp2[0]), parseInt(dp2[1]) - 1, parseInt(dp2[2])).getTime() / 1000 + 54000;
                }
                if (!dayEndTs) continue;
                var x = _chart.timeScale().timeToCoordinate(dayEndTs);
                if (x == null) continue;
                var line = document.createElement('div');
                line.className = 'five-day-boundary';
                line.style.cssText = 'position:absolute;top:0;bottom:28%;left:' + x + 'px;width:0;border-left:1px dashed rgba(160,100,255,0.6);pointer-events:none;z-index:5;';
                el.appendChild(line);
            }
        }
        requestAnimationFrame(function() { _drawDayBounds(); });

        if (_observer) _observer.disconnect();
        _observer = new ResizeObserver(function() {
            if (_chart && el.clientWidth > 0) _chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
            requestAnimationFrame(function() { _drawDayBounds(); });
        });
        _observer.observe(el);

        // 交易时段每10s刷新五日图
        if (_fiveDayTimer) clearInterval(_fiveDayTimer);
        _fiveDayTimer = setInterval(_refreshFiveDayData, 60000);
    }

    function _refreshFiveDayData() {
        if (_currentPeriod !== '5day' || !_fiveDayAreaSeries) return;
        if (!isMarketTradingTime(_stockMarket)) return;
        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket) + '&days=5')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) return;
                _fiveDayRaw = d.data;
                _fiveDayPreClose = d.data.preClose || 0;
                _setCachedFiveDay(d.data);
                try { _renderFiveDayMinute(); } catch(e) {}
            })
            .catch(function() {});
    }

    function _renderMinute(times, prices, volumes, amounts, preClose) {
        var el = document.getElementById('klChart');
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';
        var isUS = _stockMarket === '106', isHK = _stockMarket === '116';
        var today = new Date(); var base = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() / 1000;
        var fullTimes = times.map(function(t) {
            if (isUS) return new Date(t).getTime() / 1000;
            var parts = t.split(':'); return base + parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60;
        });
        _minutePreClose = preClose;

        var pcts = prices.map(function(p) { return preClose ? ((p - preClose) / preClose * 100) : p; });

        // 填充空数据到整个时段
        if (isUS) { _minuteFrom = fullTimes[0]; _minuteTo = _minuteFrom + 6.5 * 3600; }
        else if (isHK) { _minuteFrom = base + 9*3600 + 30*60; _minuteTo = base + 16*3600; }
        else { _minuteFrom = base + 9*3600 + 30*60; _minuteTo = base + 15*3600; }
        var allT = [], allP = [], allV = [], allA = [], di = 0;
        var lunchAStart = base + 11*3600 + 31*60, lunchAEnd = base + 13*3600;
        var lunchHKStart = base + 12*3600 + 1*60, lunchHKEnd = base + 13*3600;
        for (var t = _minuteFrom; t <= _minuteTo; t += 60) {
            // 跳过午休 A股:11:31-13:00  港股:12:01-13:00
            if (!isUS && ((!isHK && t >= lunchAStart && t <= lunchAEnd) || (isHK && t >= lunchHKStart && t <= lunchHKEnd))) continue;
            allT.push(t);
            if (di < fullTimes.length && fullTimes[di] >= t - 30 && fullTimes[di] <= t + 30) {
                allP.push(pcts[di]); allV.push(volumes[di]); allA.push(amounts[di]); di++;
            } else { allP.push(null); allV.push(null); allA.push(null); }
        }

        _chart = LightweightCharts.createChart(el, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', scaleMargins: { top: 0.08, bottom: 0.28 } },
            handleScroll: { vertTouchDrag: false, horzTouchDrag: false },
            handleScale: { axisPressedMouseMove: false, pinch: false, mouseWheel: false },
            timeScale: {
                borderColor: '#2a2a4e', timeVisible: true, secondsVisible: false,
                tickMarkFormatter: function(ts) {
                    var d = new Date(ts * 1000), h = d.getHours(), m = d.getMinutes();
                    if (isUS) return (d.getMonth()+1)+'/'+d.getDate()+' '+String(h).padStart(2,'0')+':'+String(m).padStart(2,'0');
                    return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0');
                },
            },
            width: el.clientWidth, height: el.clientHeight,
        });

        // 找最后有效数据索引，两条线都只画到那里
        var lastValidIdx = -1;
        for (var vi = allP.length - 1; vi >= 0; vi--) { if (allP[vi] != null) { lastValidIdx = vi; break; } }

        // 蓝色面积线
        var series = _chart.addAreaSeries({ lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)', lineWidth: 1.5, priceLineVisible: false, priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(2) + '%'; } } });
        _minuteSeries = series;
        var lineData = []; for (var i = 0; i <= lastValidIdx; i++) lineData.push({ time: allT[i], value: allP[i] });
        series.setData(lineData);

        // 均价线
        var avgData = [], avgSum = 0, avgN = 0;
        for (var i = 0; i <= lastValidIdx; i++) {
            if (allP[i] != null) { avgSum += prices[Math.min(avgN, prices.length - 1)]; avgN++; }
            avgData.push({ time: allT[i], value: allP[i] != null ? (avgN > 0 ? (preClose ? ((avgSum / avgN - preClose) / preClose * 100) : (avgSum / avgN)) : null) : null });
        }
        var avgLine = _chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgData);
        _minuteAvgLine = avgLine;

        // 昨收0%线
        var zLine = _chart.addLineSeries({ color: '#888', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        zLine.setData([{ time: _minuteFrom, value: 0 }, { time: _minuteTo, value: 0 }]);

        // 成交量柱
        if (volumes && volumes.length > 0) {
            var volSeries = _chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'volume' });
            _chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
            var vd = [];
            for (var i = 0; i < allT.length; i++) {
                var up = (i > 0 && allP[i] != null && allP[i-1] != null) ? allP[i] >= allP[i-1] : true;
                vd.push({ time: allT[i], value: allV[i], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
            }
            volSeries.setData(vd);
            _minuteVolSeries = volSeries;
        }

        // 游标
        var tooltip = document.getElementById('klTooltip');
        _chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point) { tooltip.style.display = 'none'; return; }
            var idx = -1;
            for (var i = 0; i < allT.length; i++) { if (allT[i] === param.time) { idx = i; break; } }
            if (idx < 0 || allP[idx] == null) { tooltip.style.display = 'none'; return; }
            var rawIdx = 0; for (var ri = 0; ri <= idx; ri++) { if (allP[ri] != null) rawIdx++; } rawIdx--;
            var d = new Date(param.time * 1000);
            var ds = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
            var ts = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
            var pr = prices[rawIdx], vl = volumes[rawIdx] || 0, am = amounts[rawIdx] || 0;
            var vs = vl >= 1e8 ? (vl/1e8).toFixed(2)+'亿股' : vl >= 1e4 ? (vl/1e4).toFixed(2)+'万股' : vl+'股';
            var as = am >= 1e8 ? (am/1e8).toFixed(2)+'亿' : am >= 1e4 ? (am/1e4).toFixed(2)+'万' : String(am);
            var pc = (pr - preClose) / preClose * 100, pcs = pc >= 0 ? '+' : '', pcc = pc >= 0 ? '#ef5350' : '#26a69a';
            var av = idx < avgData.length ? avgData[idx].value : null;
            var ap = (av != null && preClose) ? (av * preClose / 100 + preClose) : null;
            tooltip.innerHTML = '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">'+ds+' '+ts+'</div><table style="border-spacing:0;">'+
                '<tr><td style="color:#888;">价格</td><td><span style="color:#3b82f6;">'+pr.toFixed(2)+'</span></td></tr>'+
                '<tr><td style="color:#888;">均价</td><td><span style="color:#fbbf24;">'+(ap?ap.toFixed(2):'--')+'</span></td></tr>'+
                '<tr><td style="color:#888;">涨幅</td><td><span style="color:'+pcc+';">'+pcs+pc.toFixed(2)+'%</span></td></tr>'+
                '<tr><td style="color:#888;">成交</td><td><span style="color:#ddd;">'+vs+'</span></td></tr>'+
                '<tr><td style="color:#888;">成交额</td><td><span style="color:#ddd;">'+as+'</span></td></tr></table>';
            tooltip.style.display = 'block';
            var rect = el.getBoundingClientRect();
            var l = param.point.x + 16, tp = param.point.y - 10;
            if (l + 120 > rect.width) l = param.point.x - 130;
            if (tp + 60 > rect.height) tp = rect.height - 70;
            if (tp < 0) tp = 0;
            tooltip.style.left = l + 'px'; tooltip.style.top = tp + 'px';
        });

        // 标题栏信息（取最后一个有效数据）
        var lastP = prices[prices.length - 1], lastAvgV = null;
        for (var ai = avgData.length - 1; ai >= 0; ai--) { if (avgData[ai].value != null) { lastAvgV = avgData[ai].value; break; } }
        var lChg = preClose ? lastP - preClose : 0, lChgPct = preClose ? lChg / preClose * 100 : 0;
        var ls = lChg >= 0 ? '+' : '', lc = lChg >= 0 ? '#ef5350' : '#26a69a';
        var mv = document.getElementById('klMinuteVals');
        if (mv) mv.innerHTML = '<span style="color:#fbbf24;">均价:'+(preClose ? (lastAvgV*preClose/100+preClose).toFixed(2):'--')+'</span> <span style="color:#3b82f6;">最新:'+lastP.toFixed(2)+'</span> <span style="color:'+lc+';">'+ls+lChg.toFixed(2)+'</span> <span style="color:'+lc+';">'+ls+lChgPct.toFixed(2)+'%</span>';

        _chart.timeScale().fitContent();
        _chart.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true });

        if (_observer) _observer.disconnect();
        _observer = new ResizeObserver(function() { if (_chart && el.clientWidth > 0) _chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }); });
        _observer.observe(el);

        // 10秒刷新
        if (_minuteTimer) clearInterval(_minuteTimer);
        _minuteTimer = setInterval(_refreshMinuteData, 60000);
    }

    function _refreshMinuteData() {
        if (!_isMinute || !_minuteSeries) return;
        if (!isMarketTradingTime(_stockMarket)) return;
        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket))
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) return;
                var times = d.data.times, prices = d.data.prices, volumes = d.data.volumes || [], amounts = d.data.amounts || [];
                var preClose = d.data.preClose || _minutePreClose;
                var isUS2 = _stockMarket === '106', isHK2 = _stockMarket === '116';
                var today2 = new Date(); var base2 = new Date(today2.getFullYear(), today2.getMonth(), today2.getDate()).getTime() / 1000;
                var rawTimes = times.map(function(t) {
                    if (isUS2) return new Date(t).getTime() / 1000;
                    var pp = t.split(':'); return base2 + parseInt(pp[0]) * 3600 + parseInt(pp[1]) * 60;
                });
                var pcts = prices.map(function(p) { return preClose ? ((p - preClose) / preClose * 100) : p; });

                var rAllT = [], rAllP = [], rAllV = [], rAllA = [];
                var lAS = base2 + 11*3600 + 31*60, lAE = base2 + 13*3600;
                var lHS = base2 + 12*3600 + 1*60, lHE = base2 + 13*3600;
                var ri = 0;
                for (var t2 = _minuteFrom; t2 <= _minuteTo; t2 += 60) {
                    if (!isUS2 && ((!isHK2 && t2 >= lAS && t2 <= lAE) || (isHK2 && t2 >= lHS && t2 <= lHE))) continue;
                    rAllT.push(t2);
                    if (ri < rawTimes.length && rawTimes[ri] >= t2 - 30 && rawTimes[ri] <= t2 + 30) {
                        rAllP.push(pcts[ri] != null ? pcts[ri] : null);
                        rAllV.push(volumes[ri] != null ? volumes[ri] : 0);
                        rAllA.push(amounts[ri] != null ? amounts[ri] : 0);
                        ri++;
                    } else { rAllP.push(null); rAllV.push(null); rAllA.push(null); }
                }
                // 找最后有效索引
                var lvi = -1;
                for (var vi2 = rAllP.length - 1; vi2 >= 0; vi2--) { if (rAllP[vi2] != null) { lvi = vi2; break; } }
                // 更新分时面积图
                var lineData = [];
                for (var i = 0; i <= lvi; i++) lineData.push({ time: rAllT[i], value: rAllP[i] });
                _minuteSeries.setData(lineData);
                // 更新均价线
                var avgData = [], avgSum = 0, avgN = 0;
                for (var i = 0; i <= lvi; i++) {
                    if (rAllP[i] != null) { avgSum += prices[Math.min(avgN, prices.length - 1)]; avgN++; }
                    avgData.push({ time: rAllT[i], value: rAllP[i] != null ? (avgN > 0 ? (preClose ? ((avgSum / avgN - preClose) / preClose * 100) : (avgSum / avgN)) : null) : null });
                }
                if (_minuteAvgLine) _minuteAvgLine.setData(avgData);
                // 更新成交量柱
                if (_minuteVolSeries) {
                    var volData = [];
                    for (var i = 0; i < rAllT.length; i++) {
                        var prevP2 = i > 0 ? rAllP[i - 1] : rAllP[i];
                        var up = prevP2 != null && rAllP[i] != null ? rAllP[i] >= prevP2 : true;
                        volData.push({ time: rAllT[i], value: rAllV[i], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
                    }
                    _minuteVolSeries.setData(volData);
                }
            })
            .catch(function() {});
    }

    // 定时刷新头部行情（最新价/涨跌幅/成交量等），所有模式共用
    function _refreshHeaderData() {
        if (!isMarketTradingTime(_stockMarket)) return;
        var market = _stockMarket, code = _stockCode;
        var secid = encodeURIComponent(market + '.' + code);
        var pQuote = fetch('/api/stock-quotes?secids=' + secid)
            .then(function(r) { return r.json(); })
            .then(function(d) { return (d.success && d.data[market + '.' + code]) || null; })
            .catch(function() { return null; });
        var pExtra = fetch('/api/stock-extra?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
            .then(function(r) { return r.json(); })
            .then(function(d) { return (d.success ? d.data : null); })
            .catch(function() { return null; });
        Promise.all([pQuote, pExtra]).then(function(results) {
            var quote = results[0];
            if (!quote) return;
            var extra = results[1];
            if (extra) { quote.volume_ratio = extra.volume_ratio; quote.bid_ratio = extra.bid_ratio; }
            // 合并缓存中的商誉
            var cachedGw = _getCachedGoodwill();
            if (cachedGw) quote.goodwill = cachedGw;
            try { _fillHeader(quote); } catch(e) {}
        });
    }

    // ---- 指标切换 ----
    function _switchIndicator(mode) {
        _indicatorMode = mode;
        document.getElementById('klIndSelect').value = mode;
        for (var i = 0; i < _maLines.length; i++) { if (_maLines[i]) _maLines[i].applyOptions({ visible: mode === 'ma' }); }
        for (var i = 0; i < _bbLines.length; i++) { if (_bbLines[i]) _bbLines[i].applyOptions({ visible: mode === 'bb' }); }
        _updateIndVals();
    }
    function _updateIndVals() {
        var el = document.getElementById('klIndVals');
        if (!el) return;
        if (_indicatorMode === 'ma' && _maVals) {
            el.innerHTML = '<span style="color:#fbbf24;">MA5:' + _maVals.ma5 + '</span> <span style="color:#60a5fa;">MA10:' + _maVals.ma10 + '</span> <span style="color:#a78bfa;">MA20:' + _maVals.ma20 + '</span> <span style="color:#f472b6;">MA30:' + _maVals.ma30 + '</span> <span style="color:#34d399;">MA60:' + _maVals.ma60 + '</span> <span style="color:#fb923c;">MA120:' + _maVals.ma120 + '</span>';
        } else if (_indicatorMode === 'bb' && _bbVals) {
            el.innerHTML = '<span style="color:#ef5350;">UP:' + _bbVals.up + '</span> <span style="color:#60a5fa;">MID:' + _bbVals.mid + '</span> <span style="color:#26a69a;">LOW:' + _bbVals.lo + '</span>';
        } else {
            el.innerHTML = '';
        }
    }

    // ---- 格式化十字线提示 ----
    function _tooltipText(k, prevClose) {
        var chg = prevClose ? (k.close - prevClose) : 0;
        var chgPct = (prevClose && prevClose !== 0) ? (chg / prevClose * 100) : 0;
        var sign = chg >= 0 ? '+' : '';
        var color = chg >= 0 ? '#ef5350' : '#26a69a';
        var volStr = k.volume >= 1e8 ? (k.volume / 1e8).toFixed(2) + '亿' :
                     k.volume >= 1e4 ? (k.volume / 1e4).toFixed(2) + '万' : String(k.volume);
        var amtStr = k.amount ? (k.amount >= 1e8 ? (k.amount / 1e8).toFixed(2) + '亿' : (k.amount / 1e4).toFixed(2) + '万') : '--';
        var tDec = (_stockCode && (_stockCode.startsWith('51') || _stockCode.startsWith('15'))) ? 3 : 2;
        var n = function(v) { return '<span style="color:#ddd;">' + v.toFixed(tDec) + '</span>'; };
        var row = function(l, v, r, rv) {
            return '<tr><td style="color:#888;padding-right:4px;">' + l + '</td><td>' + v + '</td>' +
                   '<td style="color:#888;padding:0 4px;">' + r + '</td><td>' + rv + '</td></tr>';
        };
        return (
            '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">' + k.time + '</div>' +
            '<table style="border-spacing:0;">' +
                row('高', '<span style="color:#ef5350;">' + k.high.toFixed(tDec) + '</span>',
                    '低', '<span style="color:#26a69a;">' + k.low.toFixed(tDec) + '</span>') +
                row('开', n(k.open), '收', '<span style="color:' + color + ';">' + k.close.toFixed(tDec) + '</span>') +
                row('涨跌额', '<span style="color:' + color + ';">' + sign + chg.toFixed(tDec) + '</span>',
                    '涨跌幅', '<span style="color:' + color + ';">' + sign + chgPct.toFixed(2) + '%</span>') +
                row('量', '<span style="color:#ddd;">' + volStr + '</span>',
                    '额', '<span style="color:' + (k.amount ? '#ddd' : '#888') + ';">' + amtStr + '</span>') +
                (k.turnover != null ? row('换手', '<span style="color:#ddd;">' + k.turnover.toFixed(2) + '%</span>', '', '') : '') +
            '</table>'
        );
    }

    // ---- 渲染图表 ----
    function _renderChart(data) {
        var el = document.getElementById('klChart');
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';

        _klinesData = data.klines;

        _chart = LightweightCharts.createChart(el, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', scaleMargins: { top: 0.08, bottom: 0.28 } },
            timeScale: {
                borderColor: '#2a2a4e', timeVisible: true, secondsVisible: false,
                tickMarkFormatter: function(time) {
                    var y, m, d;
                    if (typeof time === 'number') {
                        var dt = new Date(time * 1000);
                        y = dt.getFullYear(); m = dt.getMonth() + 1; d = dt.getDate();
                    } else if (time && time.year) {
                        y = time.year; m = time.month; d = time.day;
                    } else if (typeof time === 'string') {
                        return time;
                    } else {
                        return '';
                    }
                    return y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
                },
            },
            width: el.clientWidth, height: el.clientHeight,
        });

        _series = _chart.addCandlestickSeries({
            upColor: '#ef5350', downColor: '#26a69a',
            borderUpColor: '#ef5350', borderDownColor: '#26a69a',
            wickUpColor: '#ef5350', wickDownColor: '#26a69a',
        });
        _series.setData(data.klines.map(function(k) {
            return { time: k.time, open: k.open, high: k.high, low: k.low, close: k.close };
        }));

        _volSeries = _chart.addHistogramSeries({
            priceFormat: { type: 'volume' }, priceScaleId: 'volume',
        });
        _chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
        _volSeries.setData(data.klines.map(function(k) {
            return { time: k.time, value: k.volume, color: k.close >= k.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' };
        }));

        // ---- 均线 MA5/10/20/30/60/120 ----
        var maC = ['#fbbf24', '#60a5fa', '#a78bfa', '#f472b6', '#34d399', '#fb923c'];
        var maP = [5, 10, 20, 30, 60, 120];
        var maData = [];
        _maLines = [];
        for (var mi = 0; mi < maP.length; mi++) {
            var md = _calcSMA(data.klines, maP[mi]);
            maData.push(md);
            var line = _chart.addLineSeries({ color: maC[mi], lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
            line.setData(md);
            _maLines.push(line);
        }
        var lastMA = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        _maVals = {
            ma5: lastMA(maData[0]), ma10: lastMA(maData[1]),
            ma20: lastMA(maData[2]), ma30: lastMA(maData[3]),
            ma60: lastMA(maData[4]), ma120: lastMA(maData[5]),
        };

        // ---- 布林线（默认隐藏）：黄上轨 / 蓝中轨 / 紫下轨 ----
        _bbLines = [];
        var bb = _calcBB(data.klines);
        var lastBB = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        _bbVals = { up: lastBB(bb.up), mid: lastBB(bb.mid), lo: lastBB(bb.lo) };
        [{v: bb.up, d: true, c: '#ef5350'}, {v: bb.mid, d: false, c: '#60a5fa'}, {v: bb.lo, d: true, c: '#26a69a'}].forEach(function(x) {
            var line = _chart.addLineSeries({ color: x.c, lineWidth: 1, lineStyle: x.d ? 2 : 0, priceLineVisible: false, lastValueVisible: false, visible: false });
            line.setData(x.v);
            _bbLines.push(line);
        });

        // ---- 十字线 tooltip ----
        var tooltip = document.getElementById('klTooltip');
        _chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point || !_klinesData) {
                tooltip.style.display = 'none';
                return;
            }
            var k = null, idx = -1;
            var tKey = typeof param.time === 'string' ? param.time :
                       param.time.year ? param.time.year + '-' + String(param.time.month).padStart(2,'0') + '-' + String(param.time.day).padStart(2,'0') : '';
            for (var i = 0; i < _klinesData.length; i++) {
                if (_klinesData[i].time === tKey) { k = _klinesData[i]; idx = i; break; }
            }
            if (!k) { tooltip.style.display = 'none'; return; }
            var prevClose = idx > 0 ? _klinesData[idx - 1].close : null;

            tooltip.innerHTML = _tooltipText(k, prevClose);
            tooltip.style.display = 'block';
            var rect = el.getBoundingClientRect();
            var left = param.point.x + 16;
            var top = param.point.y - 10;
            if (left + 160 > rect.width) left = param.point.x - 170;
            if (top + 180 > rect.height) top = rect.height - 190;
            if (top < 0) top = 0;
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        });

        _chart.timeScale().fitContent();

        if (_observer) _observer.disconnect();
        _observer = new ResizeObserver(function() {
            if (_chart && el.clientWidth > 0) {
                _chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
            }
        });
        _observer.observe(el);
    }

    // ---- 填充头部信息 ----
    function _fillHeader(quote) {
        var priceEl = document.getElementById('klPrice');
        var chgEl = document.getElementById('klChange');
        var paramsEl = document.getElementById('klParams');

        if (!quote || !quote.price || quote.price === '-') {
            priceEl.textContent = ''; chgEl.textContent = ''; paramsEl.innerHTML = '--'; return;
        }
        var chg = quote.change || '', pct = quote.pct || '';
        var isUp = chg.startsWith('+') || parseFloat(chg) > 0;
        var isDown = chg.startsWith('-') || parseFloat(chg) < 0;
        var color = isUp ? '#ef5350' : isDown ? '#26a69a' : '#8b8b9e';
        priceEl.textContent = quote.price;
        priceEl.style.color = color;
        chgEl.textContent = chg + '  ' + pct;
        chgEl.style.color = color;

        // 双行数据面板
        function v(val) { return (val && val !== '-') ? '<span style="color:#ccc;">' + val + '</span>' : '<span style="color:#555;">--</span>'; }
        function cell(label, value) { return '<span style="white-space:nowrap;"><span style="color:#8b8b9e;">' + label + '</span> ' + v(value) + '</span>'; }

        var latest = (_klinesData && _klinesData.length > 0) ? _klinesData[_klinesData.length - 1] : null;
        var isEtf = _stockCode && (_stockCode.startsWith('51') || _stockCode.startsWith('15'));
        var fixVal = function(val, qv) { return isEtf ? parseFloat(qv) : (val != null ? val : null); };

        // 相对昨收上色
        var pcNum = (quote.pre_close && quote.pre_close !== '-') ? parseFloat(quote.pre_close) : null;
        function cmpColor(val) {
            if (val == null || pcNum == null || isNaN(pcNum) || isNaN(val)) return '#ccc';
            if (val > pcNum) return '#ef5350';
            if (val < pcNum) return '#26a69a';
            return '#ccc';
        }
        function ohlcCell(label, qv) {
            var val = fixVal(latest ? (label === '高' ? latest.high : label === '低' ? latest.low : latest.open) : null, qv);
            var display = (val != null && !isNaN(val)) ? val.toFixed(isEtf ? 3 : 2) : null;
            var clr = cmpColor(val);
            return '<span style="white-space:nowrap;"><span style="color:#8b8b9e;">' + label + '</span> <span style="color:' + clr + ';">' + (display || '--') + '</span></span>';
        }
        var gw = quote.goodwill || {};

        // 计算涨停跌停
        var limitUp = null, limitDown = null;
        if (quote.pre_close && quote.pre_close !== '-') {
            var pc = parseFloat(quote.pre_close);
            if (!isNaN(pc) && pc > 0) {
                var rate = _stockCode ? _limitRate(_stockCode) : 0.1;
                var limDec = isEtf ? 3 : 2;
                limitUp = (pc * (1 + rate)).toFixed(limDec);
                limitDown = (pc * (1 - rate)).toFixed(limDec);
            }
        }

        paramsEl.innerHTML =
            '<div style="display:grid;grid-template-columns:repeat(10,auto);column-gap:12px;row-gap:2px;justify-content:start;">' +
                ohlcCell('高', quote.high) +
                cell('涨停', limitUp ? '<span style="color:#ef5350;">' + limitUp + '</span>' : null) +
                ohlcCell('今开', quote.open) +
                cell('成交量', quote.volume) +
                cell('换手', quote.turnover) +
                cell('量比', (function(){ var v = parseFloat(quote.volume_ratio); if (isNaN(v)) return null; var c = v > 1 ? '#ef5350' : v < 1 ? '#26a69a' : '#ccc'; return '<span style="color:' + c + ';">' + v.toFixed(2) + '</span>'; })()) +
                cell('市盈', quote.pe) +
                cell('总股本', quote.total_shares) +
                cell('总市值', quote.total_cap) +
                cell('质押率', gw.pld != null ? gw.pld.toFixed(2) + '%' : null) +
                ohlcCell('低', quote.low) +
                cell('跌停', limitDown ? '<span style="color:#26a69a;">' + limitDown + '</span>' : null) +
                cell('昨收', quote.pre_close) +
                cell('成交额', quote.amount) +
                cell('振幅', quote.amplitude) +
                cell('委比', (function(){ var v = parseFloat(quote.bid_ratio); if (isNaN(v)) return null; var c = v > 0 ? '#ef5350' : v < 0 ? '#26a69a' : '#ccc'; return '<span style="color:' + c + ';">' + v.toFixed(2) + '%</span>'; })()) +
                cell('市净', quote.pb) +
                cell('流通股', quote.float_shares) +
                cell('流通值', quote.float_cap) +
                cell('商誉率', gw.gw != null ? gw.gw.toFixed(2) + '%' : null) +
            '</div>';
    }

    // ---- 公开方法 ----
    function _limitRate(code) {
        var c = String(code);
        if (/^30[04]/.test(c) || /^68/.test(c)) return 0.20;
        if (/^8[34]|^43|^87|^88/.test(c)) return 0.30;  // 北交所/新三板
        if (/^90/.test(c)) return 0.30;
        return 0.10;
    }

    function _updateWatchlistBtn() {
        var btn = document.getElementById('klWatchlistBtn');
        if (!btn) return;
        var inList = (typeof watchlistStocks !== 'undefined') && watchlistStocks.some(function(s) { return s.code === _stockCode; });
        btn.textContent = inList ? '🗑 删自选' : '⭐ 加自选';
        btn.style.color = inList ? '#e94560' : '#fbbf24';
    }

    function open(code, market, name, extra) {
        extra = extra || {};
        _stockCode = code;
        _stockMarket = market;
        _clearAllKlineCache();  // 跨天清全部K线缓存
        _currentPeriod = 'day';
        _isMinute = false;
        _ensureDOM();
        // 重置周期按钮样式
        var pBtns = document.querySelectorAll('#klPeriodBar button[data-p]');
        pBtns.forEach(function(b) {
            var act = b.getAttribute('data-p') === 'day';
            b.style.background = act ? '#2a2a4e' : '#1a1a2e';
            b.style.color = act ? '#fff' : '#8b8b9e';
        });
        // 重置分时按钮
        var minBtn = document.getElementById('klBtnMinute');
        if (minBtn) { minBtn.style.background = '#1a1a2e'; minBtn.style.color = '#8b8b9e'; }
        _updateWatchlistBtn();
        document.getElementById('klName').textContent = (name || code);
        document.getElementById('klCode').textContent = '(' + code + ') ' + getStockType(code, market);
        document.getElementById('klPrice').textContent = '';
        document.getElementById('klChange').textContent = '';
        document.getElementById('klParams').innerHTML = '加载中...';

        // 重置指标栏为默认 K 线模式（防止上次分时模式的 innerHTML 残留）
        var indBar = document.getElementById('klIndBar');
        if (indBar) indBar.innerHTML = '<select id="klIndSelect" onchange="KlinePopup._switchIndicator(this.value)" style="cursor:pointer;font-size:10px;padding:1px 4px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#ccc;"><option value="ma">均线</option><option value="bb">布林线</option></select><span id="klIndVals" style="font-size:11px;"></span>';

        _overlay.style.display = 'flex';
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        // 并行请求行情 + K线 + 商誉质押 + 量比委比
        var secid = encodeURIComponent(market + '.' + code);
        var cachedQt = _getCachedQuotes();
        var pQuote = cachedQt
            ? Promise.resolve(cachedQt)
            : fetch('/api/stock-quotes?secids=' + secid)
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var qt = (d.success && d.data[market + '.' + code]) || null;
                    if (qt) _setCachedQuotes(qt);
                    return qt;
                })
                .catch(function() { return null; });

        var pKline;
        var cachedDay = _getCachedKlines('day');
        if (cachedDay) {
            pKline = Promise.resolve({ success: true, data: { klines: cachedDay } });
        } else {
            pKline = fetch('/api/stock-kline?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
                .then(function(r) { return r.json(); })
                .then(function(kd) { if (kd.success && kd.data && kd.data.klines) _setCachedKlines('day', kd.data.klines); return kd; })
                .catch(function() { return { success: false }; });
        }

        var cachedGw = _getCachedGoodwill();
        var pGoodwill = cachedGw
            ? Promise.resolve(cachedGw)
            : fetch('/api/goodwill?codes=' + encodeURIComponent(code))
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var gw = (d.success && d.data[code]) || null;
                    if (gw) _setCachedGoodwill(gw);
                    return gw;
                })
                .catch(function() { return null; });

        var cachedEt = _getCachedExtra();
        var pExtra = cachedEt
            ? Promise.resolve(cachedEt)
            : fetch('/api/stock-extra?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var et = (d.success ? d.data : null);
                    if (et) _setCachedExtra(et);
                    return et;
                })
                .catch(function() { return null; });

        Promise.all([pQuote, pKline, pGoodwill, pExtra]).then(function(results) {
            var quote = results[0] || {};
            var kdata = results[1];
            var goodwill = results[2];
            var extra = results[3];
            if (goodwill) quote.goodwill = goodwill;
            if (extra) { quote.volume_ratio = extra.volume_ratio; quote.bid_ratio = extra.bid_ratio; }

            if (kdata.success && kdata.data.klines && kdata.data.klines.length > 0) {
                _klinesData = kdata.data.klines;
                var last = _klinesData[_klinesData.length - 1];
                if (quote) {
                    if (last.amount == null && quote.amount_raw != null && quote.amount_raw !== '-') last.amount = parseFloat(quote.amount_raw);
                    if (last.turnover == null && quote.turnover_raw != null && quote.turnover_raw !== '-') last.turnover = parseFloat(quote.turnover_raw);
                }
            }

            try { _fillHeader(quote); }
            catch(e) { document.getElementById('klParams').innerHTML = '<span style="color:#ef5350;">头部渲染失败: ' + (e.message || e) + '</span>'; }

            if (!_klinesData) {
                chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">暂无K线数据</div>';
            } else {
                try { _renderChart(kdata.data); var sel = document.getElementById('klIndSelect'); if (sel) sel.value = _indicatorMode; _updateIndVals(); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            }
            document.getElementById('klPeriodBar').style.display = 'flex';
            document.getElementById('klIndBar').style.display = _klinesData ? 'flex' : 'none';
            // 启动头部行情定时刷新
            if (_headerTimer) clearInterval(_headerTimer);
            _headerTimer = setInterval(_refreshHeaderData, 10000);
        });
    }

    function close() {
        _maybeClearCurrentKlines();
        if (_headerTimer) { clearInterval(_headerTimer); _headerTimer = null; }
        if (_observer) { _observer.disconnect(); _observer = null; }
        if (_chart) { _chart.remove(); _chart = null; _series = null; _volSeries = null; }
        if (_overlay) _overlay.style.display = 'none';
        _klinesData = null;
        _maLines = [];
        _bbLines = [];
        _maVals = null;
        _bbVals = null;
        _isMinute = false;
        if (_minuteTimer) { clearInterval(_minuteTimer); _minuteTimer = null; }
        if (_fiveDayTimer) { clearInterval(_fiveDayTimer); _fiveDayTimer = null; }
        _fiveDayAreaSeries = null;
        _fiveDayVolSeries = null;
        _fiveDayRaw = null;
        var bar = document.getElementById('klIndBar');
        if (bar) bar.style.display = 'none';
        bar = document.getElementById('klPeriodBar');
        if (bar) bar.style.display = 'none';
    }

    return { open: open, close: close, _switchIndicator: _switchIndicator, _toggleMinute: _toggleMinute, _switchPeriod: _switchPeriod, _toggleWatchlist: function() { if (typeof watchlistStocks === 'undefined' || typeof watchlistPickStock !== 'function') return; var found = watchlistStocks.find(function(s) { return s.code === _stockCode; }); if (found) { watchlistRemoveStock(_stockCode, _stockMarket); } else { watchlistPickStock(_stockCode, _stockMarket); } _updateWatchlistBtn(); }, _updateWatchlistBtn: _updateWatchlistBtn };
})();
