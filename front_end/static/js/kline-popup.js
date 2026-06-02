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
    var _minuteSeries = null;    // 分时面积图引用
    var _minuteAvgLine = null;   // 均价线引用
    var _minuteVolSeries = null; // 成交量柱引用
    var _minutePreClose = 0;
    var _minuteFrom = 0, _minuteTo = 0;  // 分时窗口固定范围
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
                    '<span style="color:#666;font-size:20px;cursor:pointer;padding:0 6px;line-height:1;" onclick="KlinePopup.close()">✕</span>' +
                '</div>' +
                '<div id="klParams" style="padding:6px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;flex-shrink:0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:11px;color:#8b8b9e;">加载中...</div>' +
                '<div id="klPeriodBar" style="display:none;padding:4px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;flex-shrink:0;align-items:center;gap:6px;font-size:11px;color:#8b8b9e;">' +
                    '<button id="klBtnMinute" onclick="KlinePopup._toggleMinute()" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">分时</button>' +
                    '<button data-p="day" onclick="KlinePopup._switchPeriod(\'day\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#2a2a4e;color:#fff;">日K</button>' +
                    '<button data-p="week" onclick="KlinePopup._switchPeriod(\'week\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">周K</button>' +
                    '<button data-p="month" onclick="KlinePopup._switchPeriod(\'month\')" style="cursor:pointer;font-size:10px;padding:1px 7px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#8b8b9e;">月K</button>' +
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
        var btn = document.getElementById('klBtnMinute');
        var indBar = document.getElementById('klIndBar');

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
        _currentPeriod = p;
        document.getElementById('klBtnMinute').style.background = '#1a1a2e';
        document.getElementById('klBtnMinute').style.color = '#8b8b9e';
        var indBar = document.getElementById('klIndBar');
        indBar.style.display = 'flex';
        indBar.innerHTML = '<select id="klIndSelect" onchange="KlinePopup._switchIndicator(this.value)" style="cursor:pointer;font-size:10px;padding:1px 4px;border:1px solid #2a2a4e;border-radius:3px;background:#1a1a2e;color:#ccc;"><option value="ma">均线</option><option value="bb">布林线</option></select><span id="klIndVals" style="font-size:11px;"></span>';
        // 按钮样式
        var btns = document.querySelectorAll('#klPeriodBar button[data-p]');
        btns.forEach(function(b) {
            var act = b.getAttribute('data-p') === p;
            b.style.background = act ? '#2a2a4e' : '#1a1a2e';
            b.style.color = act ? '#fff' : '#8b8b9e';
        });
        _loadKlineChart();
    }

    function _loadMinuteChart() {
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';
        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket))
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">暂无分时数据</div>'; return; }
                try { _renderMinute(d.data.times, d.data.prices, d.data.volumes || [], d.data.amounts || [], d.data.preClose || 0); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败</div>'; });
    }

    function _loadKlineChart() {
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';
        fetch('/api/stock-kline?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket) + '&period=' + _currentPeriod)
            .then(function(r) { return r.json(); })
            .then(function(kdata) {
                if (!kdata.success || !kdata.data.klines || kdata.data.klines.length === 0) {
                    chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">暂无K线数据</div>';
                    return;
                }
                _klinesData = kdata.data.klines;
                try { _renderChart(kdata.data); var sel = document.getElementById('klIndSelect'); if (sel) sel.value = _indicatorMode; _updateIndVals(); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            })
            .catch(function() { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败</div>'; });
    }

    function _renderMinute(times, prices, volumes, amounts, preClose) {
        var el = document.getElementById('klChart');
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';
        var isUS = _stockMarket === '106';
        var today = new Date(); var base = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() / 1000;
        var fullTimes = times.map(function(t) {
            if (isUS) return new Date(t).getTime() / 1000;
            var parts = t.split(':'); return base + parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60;
        });
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
                    var d = new Date(ts * 1000);
                    var h = d.getHours(), m = d.getMinutes();
                    return (d.getMonth()+1) + '/' + d.getDate() + ' ' + String(h).padStart(2,'0') + ':' + String(m).padStart(2,'0');
                },
            },
            width: el.clientWidth, height: el.clientHeight,
        });

        // 转为涨跌百分比
        var pcts = prices.map(function(p) { return preClose ? ((p - preClose) / preClose * 100) : p; });
        var pctsAvg = preClose ? 0 : 1; // 均价也用百分比

        // 分时线（蓝色面积 + 线）
        _minutePreClose = preClose;
        var series = _chart.addAreaSeries({
            lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)',
            lineWidth: 1.5, priceLineVisible: false,
            priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(2) + '%'; } },
        });
        _minuteSeries = series;
        var data = [];
        for (var i = 0; i < fullTimes.length; i++) data.push({ time: fullTimes[i], value: pcts[i] });
        series.setData(data);

        // 均价线（当日累计平均成本，百分比）
        var avgData = [], avgSum = 0;
        for (var i = 0; i < fullTimes.length; i++) { avgSum += prices[i]; avgData.push({ time: fullTimes[i], value: preClose ? ((avgSum / (i + 1) - preClose) / preClose * 100) : (avgSum / (i + 1)) }); }
        var avgLine = _chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgData);
        _minuteAvgLine = avgLine;

        // 更新指标栏：均价 最新 涨跌值 涨跌幅
        var latestPrice = prices[prices.length - 1], latestAvg = avgData[avgData.length - 1].value;
        var latestChg = preClose ? (latestPrice - preClose) : 0;
        var latestChgPct = preClose ? (latestChg / preClose * 100) : 0;
        var sign = latestChg >= 0 ? '+' : '';
        var chgColor = latestChg >= 0 ? '#ef5350' : '#26a69a';
        var mvEl = document.getElementById('klMinuteVals');
        if (mvEl) {
            mvEl.innerHTML = '<span style="color:#fbbf24;">均价:' + (preClose ? (latestAvg * preClose / 100 + preClose).toFixed(2) : '--') + '</span> ' +
                '<span style="color:#3b82f6;">最新:' + latestPrice.toFixed(2) + '</span> ' +
                '<span style="color:' + chgColor + ';">' + sign + latestChg.toFixed(2) + '</span> ' +
                '<span style="color:' + chgColor + ';">' + sign + latestChgPct.toFixed(2) + '%</span>';
        }

        // 昨收线（0%线）
        var zeroLine = _chart.addLineSeries({ color: '#888', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        zeroLine.setData([{ time: fullTimes[0], value: 0 }, { time: fullTimes[fullTimes.length - 1], value: 0 }]);

        // 成交量柱（红涨绿跌）
        if (volumes && volumes.length > 0) {
            var volSeries = _chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'volume' });
            _chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
            var volData = [];
            for (var i = 0; i < fullTimes.length; i++) {
                var up = i > 0 ? prices[i] >= prices[i - 1] : true;
                volData.push({ time: fullTimes[i], value: volumes[i], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
            }
            volSeries.setData(volData);
            _minuteVolSeries = volSeries;
        }

        // ---- 十字线 tooltip ----
        var tooltip = document.getElementById('klTooltip');
        var mTimes = times, mPrices = prices, mVols = volumes || [], mAmts = amounts || [];
        _chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point) { tooltip.style.display = 'none'; return; }
            var ts = param.time, idx = -1;
            for (var i = 0; i < fullTimes.length; i++) {
                if (fullTimes[i] === ts) { idx = i; break; }
            }
            if (idx < 0 || idx >= mPrices.length) { tooltip.style.display = 'none'; return; }
            var d = new Date(ts * 1000);
            var dateStr = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
            var timeStr = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
            var vol = mVols[idx] || 0;
            var volStr = vol >= 1e8 ? (vol / 1e8).toFixed(2) + '亿股' : vol >= 1e4 ? (vol / 1e4).toFixed(2) + '万股' : vol + '股';
            var amt = mAmts[idx] || 0;
            var amtStr = amt >= 1e8 ? (amt / 1e8).toFixed(2) + '亿' : amt >= 1e4 ? (amt / 1e4).toFixed(2) + '万' : String(amt);
            var pct = preClose ? ((mPrices[idx] - preClose) / preClose * 100) : 0;
            var pctSign = pct >= 0 ? '+' : '';
            var pctColor = pct >= 0 ? '#ef5350' : '#26a69a';
            var avgVal = idx < avgData.length ? avgData[idx].value : null;
            var avgPrice = (avgVal != null && preClose) ? (avgVal * preClose / 100 + preClose) : null;
            tooltip.innerHTML =
                '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">' + dateStr + ' ' + timeStr + '</div>' +
                '<table style="border-spacing:0;">' +
                '<tr><td style="color:#888;padding-right:4px;">价格</td><td><span style="color:#3b82f6;">' + mPrices[idx].toFixed(2) + '</span></td></tr>' +
                '<tr><td style="color:#888;padding-right:4px;">均价</td><td><span style="color:#fbbf24;">' + (avgPrice ? avgPrice.toFixed(2) : '--') + '</span></td></tr>' +
                '<tr><td style="color:#888;padding-right:4px;">涨幅</td><td><span style="color:' + pctColor + ';">' + pctSign + pct.toFixed(2) + '%</span></td></tr>' +
                '<tr><td style="color:#888;padding-right:4px;">成交</td><td><span style="color:#ddd;">' + volStr + '</span></td></tr>' +
                '<tr><td style="color:#888;padding-right:4px;">成交额</td><td><span style="color:#ddd;">' + amtStr + '</span></td></tr>' +
                '</table>';
            tooltip.style.display = 'block';
            var rect = el.getBoundingClientRect();
            var left = param.point.x + 16, top = param.point.y - 10;
            if (left + 120 > rect.width) left = param.point.x - 130;
            if (top + 60 > rect.height) top = rect.height - 70;
            if (top < 0) top = 0;
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
        });

        // 时间范围固定（不随数据增长）
        if (_stockMarket === '106') {
            _minuteFrom = fullTimes[0];
            _minuteTo = _minuteFrom + 6.5 * 3600;
        } else {
            _minuteFrom = base + 9*3600 + 30*60;
            _minuteTo = base + 15*3600;
        }
        _chart.timeScale().setVisibleRange({ from: _minuteFrom, to: _minuteTo });
        _chart.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true, rightOffset: 0 });

        if (_observer) _observer.disconnect();
        _observer = new ResizeObserver(function() {
            if (_chart && el.clientWidth > 0) {
                _chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
            }
        });
        _observer.observe(el);

        // 交易时段 10 秒自动刷新
        if (_minuteTimer) clearInterval(_minuteTimer);
        _minuteTimer = setInterval(_refreshMinuteData, 10000);
    }

    function _refreshMinuteData() {
        if (!_isMinute || !_minuteSeries) return;
        fetch('/api/stock-minute?code=' + encodeURIComponent(_stockCode) + '&market=' + encodeURIComponent(_stockMarket))
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.times || d.data.times.length === 0) return;
                var times = d.data.times, prices = d.data.prices, volumes = d.data.volumes || [], amounts = d.data.amounts || [];
                var preClose = d.data.preClose || _minutePreClose;
                var isUS2 = _stockMarket === '106';
                var today2 = new Date(); var base2 = new Date(today2.getFullYear(), today2.getMonth(), today2.getDate()).getTime() / 1000;
                var fullTimes = times.map(function(t) {
                    if (isUS2) return new Date(t).getTime() / 1000;
                    var pp = t.split(':'); return base2 + parseInt(pp[0]) * 3600 + parseInt(pp[1]) * 60;
                });
                var pcts = prices.map(function(p) { return preClose ? ((p - preClose) / preClose * 100) : p; });

                // 更新分时面积图
                var lineData = [];
                for (var i = 0; i < fullTimes.length; i++) lineData.push({ time: fullTimes[i], value: pcts[i] });
                _minuteSeries.setData(lineData);

                // 更新均价线
                var avgData = [], avgSum = 0;
                for (var i = 0; i < fullTimes.length; i++) { avgSum += prices[i]; avgData.push({ time: fullTimes[i], value: preClose ? ((avgSum / (i + 1) - preClose) / preClose * 100) : (avgSum / (i + 1)) }); }
                if (_minuteAvgLine) _minuteAvgLine.setData(avgData);

                // 更新成交量柱
                if (_minuteVolSeries) {
                    var volData = [];
                    for (var i = 0; i < fullTimes.length; i++) {
                        var up = i > 0 ? prices[i] >= prices[i - 1] : true;
                        volData.push({ time: fullTimes[i], value: volumes[i], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
                    }
                    _minuteVolSeries.setData(volData);
                }
                // 锁定窗口不变
                _chart.timeScale().setVisibleRange({ from: _minuteFrom, to: _minuteTo });
                _chart.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true, rightOffset: 0 });
            })
            .catch(function() {});
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

    function open(code, market, name, extra) {
        extra = extra || {};
        _stockCode = code;
        _stockMarket = market;
        _currentPeriod = 'day';
        _isMinute = false;
        _ensureDOM();
        document.getElementById('klName').textContent = (name || code);
        document.getElementById('klCode').textContent = '(' + code + ')';
        document.getElementById('klPrice').textContent = '';
        document.getElementById('klChange').textContent = '';
        document.getElementById('klParams').innerHTML = '加载中...';

        _overlay.style.display = 'flex';
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        // 并行请求行情 + K线 + 商誉质押 + 量比委比
        var secid = encodeURIComponent(market + '.' + code);
        var pQuote = fetch('/api/stock-quotes?secids=' + secid)
            .then(function(r) { return r.json(); })
            .then(function(d) { return (d.success && d.data[market + '.' + code]) || null; })
            .catch(function() { return null; });

        var pKline = fetch('/api/stock-kline?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
            .then(function(r) { return r.json(); })
            .catch(function() { return { success: false }; });

        var pGoodwill = fetch('/api/goodwill?codes=' + encodeURIComponent(code))
            .then(function(r) { return r.json(); })
            .then(function(d) { return (d.success && d.data[code]) || null; })
            .catch(function() { return null; });

        var pExtra = fetch('/api/stock-extra?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
            .then(function(r) { return r.json(); })
            .then(function(d) { return (d.success ? d.data : null); })
            .catch(function() { return null; });

        Promise.all([pQuote, pKline, pGoodwill, pExtra]).then(function(results) {
            var quote = results[0] || {};
            var kdata = results[1];
            var goodwill = results[2];
            var extra = results[3];
            if (goodwill) quote.goodwill = goodwill;
            if (extra) { quote.volume_ratio = extra.volume_ratio; quote.bid_ratio = extra.bid_ratio; }

            // 先存 K线原始数据
            if (kdata.success && kdata.data.klines && kdata.data.klines.length > 0) {
                _klinesData = kdata.data.klines;
                // 最新一天如果缺成交额/换手（同花顺还没出今天数据），用实时行情补
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
        });
    }

    function close() {
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
        var bar = document.getElementById('klIndBar');
        if (bar) bar.style.display = 'none';
        bar = document.getElementById('klPeriodBar');
        if (bar) bar.style.display = 'none';
    }

    return { open: open, close: close, _switchIndicator: _switchIndicator, _toggleMinute: _toggleMinute, _switchPeriod: _switchPeriod };
})();
