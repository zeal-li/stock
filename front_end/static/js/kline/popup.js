// ==================== 通用 K 线弹窗 ====================
// 使用：KlinePopup.open(code, market, name)
//       弹窗内部自己请求行情和K线数据

var KlinePopup = (function() {
    var _chart = null, _overlay = null, _series = null, _volSeries = null;
    var _observer = null;
    var _klinesData = null;
    var _stockCode = '';
    var _stockMarket = '';
    var _quoteData = null;       // 最新行情数据，用于补全/覆盖当日K线
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
                        '<span id="klConcept" style="font-size:11px;color:#c0a060;"></span>' +
                    '</div>' +
                    '<div style="display:flex;align-items:center;gap:10px;">' +
                    '<span id="klWatchlistBtn" style="cursor:pointer;font-size:13px;padding:0 6px;line-height:1;white-space:nowrap;" onclick="KlinePopup._toggleWatchlist()"></span>' +
                    '<span style="color:#666;font-size:20px;cursor:pointer;padding:0 6px;line-height:1;" onclick="KlinePopup.close()">✕</span>' +
                    '</div>' +
                '</div>' +
                '<div id="klBizComp" style="padding:2px 16px 4px;background:#1a1a2e;flex-shrink:0;font-size:11px;color:#ccc;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;"></div>' +
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
        var _tStart = Date.now();
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        var cached = _getCachedMinute();
        if (cached && !isMarketTradingTime(_stockMarket)) {
            try { _renderMinute(cached.times, cached.prices, cached.volumes || [], cached.amounts || [], cached.preClose || 0); }
            catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            console.log('[弹窗] ' + _stockCode + ' _loadMinuteChart 缓存命中, 耗时 ' + (Date.now() - _tStart) + 'ms');
            return;
        }

        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket))
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">暂无分时数据</div>'; console.log('[弹窗] ' + _stockCode + ' _loadMinuteChart 无数据, 耗时 ' + (Date.now() - _tStart) + 'ms'); return; }
                _setCachedMinute(d.data);
                try { _renderMinute(d.data.times, d.data.prices, d.data.volumes || [], d.data.amounts || [], d.data.preClose || 0); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
                console.log('[弹窗] ' + _stockCode + ' _loadMinuteChart 完成, 耗时 ' + (Date.now() - _tStart) + 'ms');
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

    // 关闭弹窗时：开盘期间清K线+分时+行情+量比，商誉/主营构成/概念题材保留（不常变）
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

    // 主营构成缓存（不常变）
    function _getCachedBizComp() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.bizcomp) ? stock.bizcomp : null;
    }
    function _setCachedBizComp(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].bizcomp = data;
        all._date = new Date().toISOString().slice(0, 10);
        _saveAllKlineCache(all);
    }

    // 概念题材缓存（不常变）
    function _getCachedConcepts() {
        var all = _getAllKlineCache();
        var stock = all[_stockCode];
        return (stock && stock.concepts) ? stock.concepts : null;
    }
    function _setCachedConcepts(data) {
        var all = _getAllKlineCache();
        if (!all[_stockCode]) all[_stockCode] = {};
        all[_stockCode].concepts = data;
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

    // K线请求，失败自动重试（最多 attempts 次，每次间隔 delayMs）
    function _fetchKlineWithRetry(url, attempts, delayMs) {
        var _firstAttempt = true;
        return _fetchKlineOnce(url).catch(function() {
            if (attempts <= 1) {
                return { success: false };
            }
            console.log('[弹窗] ' + _stockCode + ' K线第1次尝试失败, ' + delayMs + 'ms后重试...');
            return new Promise(function(resolve) {
                setTimeout(function() {
                    resolve(_fetchKlineWithRetry(url, attempts - 1, delayMs));
                }, delayMs);
            });
        });
    }

    function _fetchKlineOnce(url) {
        return fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(kd) {
                if (kd.success && kd.data && kd.data.klines) {
                    _setCachedKlines(_currentPeriod, kd.data.klines);
                }
                return kd;
            });
    }

    function _loadKlineChart() {
        var _tStart = Date.now();
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        // 先查缓存
        var cached = _getCachedKlines(_currentPeriod);
        if (cached) {
            _klinesData = cached;
            try { _renderChart({klines: _klinesData}); var sel2 = document.getElementById('klIndSelect'); if (sel2) sel2.value = _indicatorMode; _switchIndicator(_indicatorMode); }
            catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            console.log('[弹窗] ' + _stockCode + ' _loadKlineChart(' + _currentPeriod + ') 缓存命中, 耗时 ' + (Date.now() - _tStart) + 'ms');
            return;
        }

        fetch('/api/stock-kline?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket) + '&period=' + _currentPeriod)
            .then(function(r) { return r.json(); })
            .then(function(kdata) {
                if (!kdata.success || !kdata.data.klines || kdata.data.klines.length === 0) {
                    chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">暂无K线数据</div>';
                    console.log('[弹窗] ' + _stockCode + ' _loadKlineChart(' + _currentPeriod + ') 无数据, 耗时 ' + (Date.now() - _tStart) + 'ms');
                    return;
                }
                _klinesData = kdata.data.klines;
                _setCachedKlines(_currentPeriod, _klinesData);
                try { _renderChart(kdata.data); var sel = document.getElementById('klIndSelect'); if (sel) sel.value = _indicatorMode; _switchIndicator(_indicatorMode); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
                console.log('[弹窗] ' + _stockCode + ' _loadKlineChart(' + _currentPeriod + ') 完成, 耗时 ' + (Date.now() - _tStart) + 'ms');
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败</div>'; });
    }

    function _loadFiveDayMinute() {
        var _tStart = Date.now();
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
            console.log('[弹窗] ' + _stockCode + ' _loadFiveDayMinute 缓存命中, 耗时 ' + (Date.now() - _tStart) + 'ms');
            return;
        }

        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket) + '&days=5')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">暂无数据</div>'; console.log('[弹窗] ' + _stockCode + ' _loadFiveDayMinute 无数据, 耗时 ' + (Date.now() - _tStart) + 'ms'); return; }
                _fiveDayRaw = d.data;
                _fiveDayPreClose = d.data.preClose || 0;
                _setCachedFiveDay(d.data);
                try { _renderFiveDayMinute(); } catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;">渲染失败: ' + e.message + '</div>'; }
                console.log('[弹窗] ' + _stockCode + ' _loadFiveDayMinute 完成, 耗时 ' + (Date.now() - _tStart) + 'ms');
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;">请求失败</div>'; });
    }

    function _renderFiveDayMinute() {
        var el = document.getElementById('klChart');
        if (_observer) _observer.disconnect();
        var result = KlineFiveDay.render(el, _fiveDayRaw, _stockMarket);
        if (!result) return;
        _chart = result.chart;
        _fiveDayAreaSeries = result.areaSeries;
        _fiveDayVolSeries = result.volSeries;
        _observer = result.observer;
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
        if (_observer) _observer.disconnect();
        _minutePreClose = preClose;
        var result = KlineMinute.render(el, times, prices, volumes, amounts, preClose, _stockMarket, _stockCode);
        _chart = result.chart;
        _minuteSeries = result.series;
        _minuteAvgLine = result.avgLine;
        _minuteVolSeries = result.volSeries;
        _minuteFrom = result.minuteFrom;
        _minuteTo = result.minuteTo;
        _observer = result.observer;
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
        KlineChartUtils.switchIndicator(mode, _maLines, _bbLines);
        _updateIndVals();
    }
    function _updateIndVals() {
        var el = document.getElementById('klIndVals');
        if (el) el.innerHTML = KlineChartUtils.getIndHTML(_indicatorMode, _maVals, _bbVals);
    }

    // ---- 渲染图表 ----
    function _renderChart(data) {
        _klinesData = data.klines;
        // 渲染前用行情数据覆盖/插入今日K线（同花顺日K当天数据可能缺失或不完整）
        // 非交易日不注入，避免显示无意义的今日K线
        if (_quoteData && _klinesData && _klinesData.length > 0 && isTradingDay(_stockMarket)) {
            var today = new Date();
            var todayStr = today.getFullYear() + '-' +
                           String(today.getMonth() + 1).padStart(2, '0') + '-' +
                           String(today.getDate()).padStart(2, '0');
            var p = parseFloat;
            var todayK = {
                time: todayStr,
                open: p(_quoteData.open),
                high: p(_quoteData.high),
                low: p(_quoteData.low),
                close: p(_quoteData.price),
                volume: _parseVolAmt(_quoteData.volume),
                amount: _quoteData.amount_raw != null && _quoteData.amount_raw !== '-' ? p(_quoteData.amount_raw) : _parseVolAmt(_quoteData.amount),
                turnover: _quoteData.turnover_raw != null && _quoteData.turnover_raw !== '-' ? p(_quoteData.turnover_raw) : null,
            };
            var last = _klinesData[_klinesData.length - 1];
            if (last.time === todayStr) {
                _klinesData[_klinesData.length - 1] = todayK;
            } else {
                _klinesData.push(todayK);
            }
        }
        var el = document.getElementById('klChart');
        if (_observer) _observer.disconnect();
        var result = KlineChartUtils.render(el, _klinesData, _stockCode, _stockMarket);
        _chart = result.chart;
        _series = result.series;
        _volSeries = result.volSeries;
        _maLines = result.maLines;
        _bbLines = result.bbLines;
        _maVals = result.maVals;
        _bbVals = result.bbVals;
        _observer = result.observer;
        // 初始显示最近一年，右留空3个月，让最新K线在窗口偏左位置
        if (_klinesData && _klinesData.length > 0) {
            var lastT = _klinesData[_klinesData.length - 1].time;
            var parts = lastT.split('-');
            var oneYearAgo = (parseInt(parts[0]) - 1) + '-' + parts[1] + '-' + parts[2];
            // 找一年前对应的数据索引
            var fromIdx = 0;
            for (var i = 0; i < _klinesData.length; i++) {
                if (_klinesData[i].time >= oneYearAgo) { fromIdx = i; break; }
            }
            // 右边多留约20%空白，让最新K线不贴边
            var visibleBars = _klinesData.length - fromIdx;
            var rightPad = Math.round(visibleBars * 0.2);
            _chart.timeScale().setVisibleLogicalRange({ from: fromIdx, to: _klinesData.length - 1 + rightPad });
        }
    }

    // ---- 填充主营构成 ----
    function _fillBizComp(data) {
        var el = document.getElementById('klBizComp');
        if (!data || data.length === 0) {
            if (el) el.textContent = '';
            return;
        }
        var parts = [];
        for (var i = 0; i < data.length; i++) {
            var p = data[i];
            parts.push(p.name + p.income + '/' + p.gross_profit);
        }
        if (el) el.textContent = parts.join('  ');
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
        var isEtf = isETF(_stockCode, _stockMarket);
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
    // 解析行情 API 返回的成交量/成交额格式化字符串为数值（如 "11.25亿股"→1125000000, "4556.99万"→45569900）
    function _parseVolAmt(str) {
        if (!str || str === '-') return 0;
        var v = parseFloat(str);
        if (isNaN(v)) return 0;
        if (str.indexOf('亿') >= 0) return v * 1e8;
        if (str.indexOf('万') >= 0) return v * 1e4;
        return v;
    }

    function _limitRate(code) {
        var c = String(code);
        if (/^30[04]/.test(c) || /^68/.test(c)) return 0.20;
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
        var _openStart = Date.now();
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
        document.getElementById('klConcept').textContent = '';
        document.getElementById('klParams').innerHTML = '加载中...';
        document.getElementById('klBizComp').textContent = '';

        // 重置指标栏为默认 K 线模式（防止上次分时模式的 innerHTML 残留）
        var indBar = document.getElementById('klIndBar');
        if (indBar) indBar.innerHTML = '<select id="klIndSelect" onchange="KlinePopup._switchIndicator(this.value)" style="cursor:pointer;font-size:10px;padding:1px 4px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#ccc;"><option value="ma">均线</option><option value="bb">布林线</option></select><span id="klIndVals" style="font-size:11px;"></span>';

        _overlay.style.display = 'flex';
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        // 并行请求行情 + K线 + 商誉质押 + 量比委比
        var secid = encodeURIComponent(market + '.' + code);
        var cachedQt = _getCachedQuotes();
        var _tQuote = Date.now();
        var pQuote = (cachedQt
            ? Promise.resolve(cachedQt)
            : fetch('/api/stock-quotes?secids=' + secid)
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var qt = (d.success && d.data[market + '.' + code]) || null;
                    if (qt) _setCachedQuotes(qt);
                    return qt;
                })
                .catch(function() { return null; }))
            .then(function(r) { console.log('[弹窗] ' + code + ' stock-quotes 耗时 ' + (Date.now() - _tQuote) + 'ms' + (cachedQt ? ' (缓存)' : '')); return r; });

        var _tKline = Date.now();
        var pKline;
        var cachedDay = _getCachedKlines('day');
        if (cachedDay) {
            pKline = Promise.resolve({ success: true, data: { klines: cachedDay } }).then(function(r) { console.log('[弹窗] ' + code + ' stock-kline 耗时 ' + (Date.now() - _tKline) + 'ms (缓存)'); return r; });
        } else {
            // 浏览器同源连接上限（6个）可能被 open() 的并发请求 + 页面轮询占满，
            // 失败后等 1.5s 让其他请求释放连接，最多重试 3 次。
            var klineUrl = '/api/stock-kline?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market);
            pKline = _fetchKlineWithRetry(klineUrl, 3, 1500).then(function(r) { console.log('[弹窗] ' + code + ' stock-kline 耗时 ' + (Date.now() - _tKline) + 'ms'); return r; });
        }

        var _tGW = Date.now();
        var cachedGw = _getCachedGoodwill();
        var pGoodwill = (cachedGw
            ? Promise.resolve(cachedGw)
            : fetch('/api/goodwill?codes=' + encodeURIComponent(code))
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var gw = (d.success && d.data[code]) || null;
                    if (gw) _setCachedGoodwill(gw);
                    return gw;
                })
                .catch(function() { return null; }))
            .then(function(r) { console.log('[弹窗] ' + code + ' goodwill 耗时 ' + (Date.now() - _tGW) + 'ms' + (cachedGw ? ' (缓存)' : '')); return r; });

        var _tExtra = Date.now();
        var cachedEt = _getCachedExtra();
        var pExtra = (cachedEt
            ? Promise.resolve(cachedEt)
            : fetch('/api/stock-extra?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
                .then(function(r) { return r.json(); })
                .then(function(d) {
                    var et = (d.success ? d.data : null);
                    if (et) _setCachedExtra(et);
                    return et;
                })
                .catch(function() { return null; }))
            .then(function(r) { console.log('[弹窗] ' + code + ' stock-extra 耗时 ' + (Date.now() - _tExtra) + 'ms' + (cachedEt ? ' (缓存)' : '')); return r; });

        // ETF/LOF/基金 没有主营构成和题材概念，直接返回空
        var stockType = getStockType(code, market);
        var isFund = stockType.indexOf('ETF') >= 0 || stockType.indexOf('基') >= 0;

        var _tBiz = Date.now();
        var cachedBiz = _getCachedBizComp();
        var pBizComp = isFund ? Promise.resolve([])
            : (cachedBiz ? Promise.resolve(cachedBiz)
            : fetch('/api/stock-biz-comp?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
            .then(function(r) { return r.json(); })
            .then(function(d) { var r = d.success ? d.data : []; _setCachedBizComp(r); return r; })
            .catch(function() { return []; }))
            .then(function(r) { console.log('[弹窗] ' + code + ' stock-biz-comp 耗时 ' + (Date.now() - _tBiz) + 'ms' + (isFund ? ' (跳过)' : cachedBiz ? ' (缓存)' : '')); return r; });

        var _tConcept = Date.now();
        var cachedCpt = _getCachedConcepts();
        var pConcept = isFund ? Promise.resolve([])
            : (cachedCpt ? Promise.resolve(cachedCpt)
            : fetch('/api/stock-concepts?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
            .then(function(r) { return r.json(); })
            .then(function(d) { var r = d.success ? d.data : []; _setCachedConcepts(r); return r; })
            .catch(function() { return []; }))
            .then(function(r) { console.log('[弹窗] ' + code + ' stock-concepts 耗时 ' + (Date.now() - _tConcept) + 'ms' + (isFund ? ' (跳过)' : cachedCpt ? ' (缓存)' : '')); return r; });

        Promise.all([pQuote, pKline, pGoodwill, pExtra, pBizComp, pConcept]).then(function(results) {
            console.log('[弹窗] ' + code + ' === 全部请求完成, 总耗时 ' + (Date.now() - _openStart) + 'ms ===');
            var _tRender = Date.now();
            var quote = results[0] || {};
            var kdata = results[1];
            var goodwill = results[2];
            var extra = results[3];
            var bizComp = results[4];
            var concepts = results[5];

            // 显示概念题材（取前2个）
            var ce = document.getElementById('klConcept');
            if (ce && concepts && concepts.length > 0) {
                ce.textContent = concepts.slice(0, 2).join(' | ');
            }
            if (goodwill) quote.goodwill = goodwill;
            if (extra) { quote.volume_ratio = extra.volume_ratio; quote.bid_ratio = extra.bid_ratio; }
            _quoteData = (quote && quote.price && quote.price !== '-') ? quote : null;

            _fillBizComp(bizComp);

            if (kdata.success && kdata.data.klines && kdata.data.klines.length > 0) {
                _klinesData = kdata.data.klines;
            }

            try { _fillHeader(quote); }
            catch(e) { document.getElementById('klParams').innerHTML = '<span style="color:#ef5350;">头部渲染失败: ' + (e.message || e) + '</span>'; }

            if (!_klinesData) {
                chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">暂无K线数据</div>';
            } else {
                try { _renderChart(kdata.data); var sel = document.getElementById('klIndSelect'); if (sel) sel.value = _indicatorMode; _switchIndicator(_indicatorMode); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            }
            document.getElementById('klPeriodBar').style.display = 'flex';
            document.getElementById('klIndBar').style.display = _klinesData ? 'flex' : 'none';
            // 启动头部行情定时刷新
            if (_headerTimer) clearInterval(_headerTimer);
            _headerTimer = setInterval(_refreshHeaderData, 10000);
            console.log('[弹窗] ' + code + ' 渲染完成, 渲染耗时 ' + (Date.now() - _tRender) + 'ms, 从打开到渲染总耗时 ' + (Date.now() - _openStart) + 'ms');
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

    return { open: open, close: close, _switchIndicator: _switchIndicator, _toggleMinute: _toggleMinute, _switchPeriod: _switchPeriod, _toggleWatchlist: async function() { if (typeof watchlistStocks === 'undefined' || typeof watchlistPickStock !== 'function') return; var found = watchlistStocks.find(function(s) { return s.code === _stockCode; }); if (found) { watchlistRemoveStock(_stockCode, _stockMarket); } else { await watchlistPickStock(_stockCode, _stockMarket); } _updateWatchlistBtn(); }, _updateWatchlistBtn: _updateWatchlistBtn };
})();
