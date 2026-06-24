// ==================== K 线渲染（日K/周K/月K） ====================

var KlineChartUtils = {
    // MA 计算
    calcSMA: function(data, period) {
        var r = [];
        for (var i = period - 1; i < data.length; i++) {
            var s = 0;
            for (var j = i - period + 1; j <= i; j++) s += data[j].close;
            r.push({ time: data[i].time, value: s / period });
        }
        return r;
    },
    // MACD 计算 (EMA快线, EMA慢线, 信号线周期)
    calcMACD: function(data, fast, slow, signal) {
        fast = fast || 12; slow = slow || 26; signal = signal || 9;
        var kF = 2 / (fast + 1), kS = 2 / (slow + 1), kSig = 2 / (signal + 1);
        var difData = [], deaData = [], macdData = [];
        var eF = data[0].close, eS = data[0].close, dea = 0;
        for (var i = 0; i < data.length; i++) {
            eF = data[i].close * kF + (1 - kF) * eF;
            eS = data[i].close * kS + (1 - kS) * eS;
            var dif = eF - eS;
            difData.push({ time: data[i].time, value: dif });
        }
        dea = difData[0].value;
        for (var i = 0; i < difData.length; i++) {
            dea = difData[i].value * kSig + (1 - kSig) * dea;
            deaData.push({ time: difData[i].time, value: dea });
            macdData.push({ time: difData[i].time, value: (difData[i].value - dea) * 2 });
        }
        return { dif: difData, dea: deaData, macd: macdData };
    },
    // KDJ 计算 (n=RSV周期, m1=K平滑, m2=D平滑)
    calcKDJ: function(data, n, m1, m2) {
        n = n || 9; m1 = m1 || 3; m2 = m2 || 3;
        var kData = [], dData = [], jData = [];
        // 前 n-1 根没有 KDJ 值，填入 null 占位以保持时间轴对齐
        for (var pi = 0; pi < n - 1; pi++) {
            kData.push({ time: data[pi].time, value: null });
            dData.push({ time: data[pi].time, value: null });
            jData.push({ time: data[pi].time, value: null });
        }
        var k = 50, d = 50;
        var a1 = 1 / m1, a2 = 1 / m2;
        for (var i = n - 1; i < data.length; i++) {
            var highN = data[i].high, lowN = data[i].low;
            for (var j = i - n + 1; j <= i; j++) {
                if (data[j].high > highN) highN = data[j].high;
                if (data[j].low < lowN) lowN = data[j].low;
            }
            var rng = highN - lowN;
            var rsv = rng > 0 ? (data[i].close - lowN) / rng * 100 : 50;
            k = (1 - a1) * k + a1 * rsv;
            d = (1 - a2) * d + a2 * k;
            var j = 3 * k - 2 * d;
            kData.push({ time: data[i].time, value: k });
            dData.push({ time: data[i].time, value: d });
            jData.push({ time: data[i].time, value: j });
        }
        return { k: kData, d: dData, j: jData };
    },
    // 布林线计算
    calcBB: function(data) {
        var ma20 = KlineChartUtils.calcSMA(data, 20), up = [], mid = [], lo = [];
        for (var i = 0; i < ma20.length; i++) {
            var m = ma20[i];
            mid.push({ time: m.time, value: m.value });
            var idx = i + 19;
            var s = 0, n = 0;
            for (var j = Math.max(0, idx - 19); j <= idx; j++) { s += Math.pow(data[j].close - m.value, 2); n++; }
            var std = Math.sqrt(s / n);
            up.push({ time: m.time, value: m.value + 2 * std });
            lo.push({ time: m.time, value: m.value - 2 * std });
        }
        return { up: up, mid: mid, lo: lo };
    },
    // 十字线提示文案
    tooltipText: function(k, prevClose, isEtf) {
        var chg = prevClose ? (k.close - prevClose) : 0;
        var chgPct = (prevClose && prevClose !== 0) ? (chg / prevClose * 100) : 0;
        var sign = chg >= 0 ? '+' : '';
        var color = chg >= 0 ? '#ef5350' : '#26a69a';
        var volStr = k.volume >= 1e8 ? (k.volume / 1e8).toFixed(2) + '亿' :
                     k.volume >= 1e4 ? (k.volume / 1e4).toFixed(2) + '万' : String(k.volume);
        var amtStr = k.amount ? (k.amount >= 1e8 ? (k.amount / 1e8).toFixed(2) + '亿' : (k.amount / 1e4).toFixed(2) + '万') : '--';
        var tDec = isEtf ? 3 : 2;
        // 相对前一根K线收盘价上色
        var pc = prevClose && prevClose !== 0 ? prevClose : null;
        var relColor = function(val) {
            if (pc == null) return '#ddd';
            if (val > pc) return '#ef5350';
            if (val < pc) return '#26a69a';
            return '#ddd';
        };
        var relSpan = function(val) {
            return '<span style="color:' + relColor(val) + ';">' + val.toFixed(tDec) + '</span>';
        };
        var row = function(l, v, r, rv) {
            return '<tr><td style="color:#888;padding-right:4px;">' + l + '</td><td>' + v + '</td>' +
                   '<td style="color:#888;padding:0 4px;">' + r + '</td><td>' + rv + '</td></tr>';
        };
        return (
            '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">' + k.time + '</div>' +
            '<table style="border-spacing:0;">' +
                row('高', relSpan(k.high),
                    '低', relSpan(k.low)) +
                row('开', relSpan(k.open), '收', relSpan(k.close)) +
                row('涨跌额', '<span style="color:' + color + ';">' + sign + chg.toFixed(tDec) + '</span>',
                    '涨跌幅', '<span style="color:' + color + ';">' + sign + chgPct.toFixed(2) + '%</span>') +
                row('量', '<span style="color:#ddd;">' + volStr + '</span>',
                    '额', '<span style="color:' + (k.amount ? '#ddd' : '#888') + ';">' + amtStr + '</span>') +
                (k.turnover != null ? row('换手', '<span style="color:#ddd;">' + k.turnover.toFixed(2) + '%</span>', '', '') : '') +
            '</table>'
        );
    },
    // 渲染 K 线图，返回 { chart, series, volSeries, maLines, bbLines, kdjLines, kdjVals, observer }
    render: function(el, klinesData, stockCode, stockMarket, kdjParams, macdParams) {
        kdjParams = kdjParams || { n: 9, m1: 3, m2: 3 };
        macdParams = macdParams || { fast: 12, slow: 26, signal: 9 };
        el.style.display = 'flex';
        el.style.flexDirection = 'column';
        var tickFmt = function(time) {
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
        };
        var subChartBase = {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', minimumWidth: 84, scaleMargins: { top: 0.05, bottom: 0.02 } },
            timeScale: { borderColor: '#2a2a4e', visible: false },
        };

        el.innerHTML =
            '<style>#klChart a{display:none !important;}</style>' +
            // 主图（K线 + 均线/布林线）
            '<div id="klMainWrap" style="flex:3;min-height:0;position:relative;">' +
                '<div id="klMainCanvas" style="width:100%;height:100%;"></div>' +
                '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>' +
            '</div>' +
            // 成交量指标栏
            '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">VOL <span id="volTipVals"></span></div>' +
            // 成交量图
            '<div id="klVolWrap" style="flex:1;min-height:0;position:relative;">' +
                '<div id="klVolCanvas" style="width:100%;height:100%;"></div>' +
            '</div>' +
            // MACD 指标栏
            '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">' +
                'MACD(' +
                '<input id="macdFast" type="text" inputmode="numeric" value="' + macdParams.fast + '" style="pointer-events:auto;width:24px;height:16px;font-size:11px;line-height:16px;background:#2a2a4e;border:1px solid #3a3a6e;color:#ccc;text-align:center;border-radius:2px;padding:0;vertical-align:middle;">' +
                ',<input id="macdSlow" type="text" inputmode="numeric" value="' + macdParams.slow + '" style="pointer-events:auto;width:24px;height:16px;font-size:11px;line-height:16px;background:#2a2a4e;border:1px solid #3a3a6e;color:#ccc;text-align:center;border-radius:2px;padding:0;vertical-align:middle;">' +
                ',<input id="macdSignal" type="text" inputmode="numeric" value="' + macdParams.signal + '" style="pointer-events:auto;width:24px;height:16px;font-size:11px;line-height:16px;background:#2a2a4e;border:1px solid #3a3a6e;color:#ccc;text-align:center;border-radius:2px;padding:0;vertical-align:middle;">' +
                ') <span id="macdTipVals"></span>' +
            '</div>' +
            // MACD 图
            '<div id="klMacdWrap" style="flex:1;min-height:0;position:relative;">' +
                '<div id="klMacdCanvas" style="width:100%;height:100%;"></div>' +
            '</div>' +
            // KDJ 指标栏
            '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">' +
                'KDJ(' +
                '<input id="kdjN" type="text" inputmode="numeric" value="' + kdjParams.n + '" style="pointer-events:auto;width:24px;height:16px;font-size:11px;line-height:16px;background:#2a2a4e;border:1px solid #3a3a6e;color:#ccc;text-align:center;border-radius:2px;padding:0;vertical-align:middle;">' +
                ',<input id="kdjM1" type="text" inputmode="numeric" value="' + kdjParams.m1 + '" style="pointer-events:auto;width:24px;height:16px;font-size:11px;line-height:16px;background:#2a2a4e;border:1px solid #3a3a6e;color:#ccc;text-align:center;border-radius:2px;padding:0;vertical-align:middle;">' +
                ',<input id="kdjM2" type="text" inputmode="numeric" value="' + kdjParams.m2 + '" style="pointer-events:auto;width:24px;height:16px;font-size:11px;line-height:16px;background:#2a2a4e;border:1px solid #3a3a6e;color:#ccc;text-align:center;border-radius:2px;padding:0;vertical-align:middle;">' +
                ') <span id="kdjTipVals"></span>' +
            '</div>' +
            // KDJ 图（最下面，显示时间轴）
            '<div id="klKdjWrap" style="flex:1;min-height:0;position:relative;">' +
                '<div id="klKdjCanvas" style="width:100%;height:100%;"></div>' +
            '</div>';

        // ---- 4 个独立 chart 实例 ----
        var mainCanvas = document.getElementById('klMainCanvas');
        var volCanvas = document.getElementById('klVolCanvas');
        var macdCanvas = document.getElementById('klMacdCanvas');
        var kdjCanvas = document.getElementById('klKdjCanvas');

        var mainChart = LightweightCharts.createChart(mainCanvas, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', minimumWidth: 84, scaleMargins: { top: 0.05, bottom: 0.02 } },
            timeScale: { borderColor: '#2a2a4e', visible: false },
            width: mainCanvas.clientWidth, height: mainCanvas.clientHeight,
        });
        var volChart = LightweightCharts.createChart(volCanvas, Object.assign({}, subChartBase, { width: volCanvas.clientWidth, height: volCanvas.clientHeight }));
        var macdChart = LightweightCharts.createChart(macdCanvas, Object.assign({}, subChartBase, { width: macdCanvas.clientWidth, height: macdCanvas.clientHeight }));
        var kdjChart = LightweightCharts.createChart(kdjCanvas, Object.assign({}, subChartBase, {
            timeScale: { borderColor: '#2a2a4e', timeVisible: true, secondsVisible: false, tickMarkFormatter: tickFmt },
            width: kdjCanvas.clientWidth, height: kdjCanvas.clientHeight,
        }));

        // ---- 同步时间轴 ----
        var _syncLock = false;
        var allCharts = [mainChart, volChart, macdChart, kdjChart];
        allCharts.forEach(function(c) {
            c.timeScale().subscribeVisibleLogicalRangeChange(function(range) {
                if (_syncLock || !range) return;
                _syncLock = true;
                allCharts.forEach(function(tc) {
                    if (tc !== c) tc.timeScale().setVisibleLogicalRange({ from: range.from, to: range.to });
                });
                _syncLock = false;
            });
        });

        // ---- 主图: K线 + 均线 + 布林线 ----
        var series = mainChart.addCandlestickSeries({
            upColor: '#ef5350', downColor: '#26a69a',
            borderUpColor: '#ef5350', borderDownColor: '#26a69a',
            wickUpColor: '#ef5350', wickDownColor: '#26a69a',
        });
        series.setData(klinesData.map(function(k) {
            return { time: k.time, open: k.open, high: k.high, low: k.low, close: k.close };
        }));

        // ---- 成交量图 ----
        var volSeries = volChart.addHistogramSeries({
            priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false,
        });
        volSeries.setData(klinesData.map(function(k) {
            return { time: k.time, value: k.volume, color: k.close >= k.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' };
        }));

        var volMA5 = KlineChartUtils.calcSMA(klinesData.map(function(k) { return { time: k.time, close: k.volume }; }), 5);
        var volMA10 = KlineChartUtils.calcSMA(klinesData.map(function(k) { return { time: k.time, close: k.volume }; }), 10);
        var volMA5Line = volChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        volMA5Line.setData(volMA5);
        var volMA10Line = volChart.addLineSeries({ color: '#60a5fa', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        volMA10Line.setData(volMA10);

        function _fmtVol(v) {
            if (v == null || isNaN(v) || v <= 0) return '--';
            return v >= 1e8 ? (v / 1e8).toFixed(2) + '亿' : (v / 1e4).toFixed(2) + '万';
        }
        function _buildVolValsHTML(vol, m5, m10, turnover) {
            return '<span style="color:#ddd;">量:' + _fmtVol(vol) + '</span> <span style="color:#fbbf24;">M5:' + _fmtVol(m5) + '</span> <span style="color:#60a5fa;">M10:' + _fmtVol(m10) + '</span>' +
                (turnover != null ? ' <span style="color:#8b8b9e;">换手:' + turnover.toFixed(2) + '%</span>' : '');
        }
        function _refreshVolVals(idx) {
            idx = idx !== undefined ? idx : klinesData.length - 1;
            if (idx >= 0 && idx < klinesData.length) {
                var k = klinesData[idx];
                var i5 = idx - 4;
                var i10 = idx - 9;
                var m5 = (i5 >= 0 && i5 < volMA5.length) ? volMA5[i5].value : null;
                var m10 = (i10 >= 0 && i10 < volMA10.length) ? volMA10[i10].value : null;
                document.getElementById('volTipVals').innerHTML = _buildVolValsHTML(k.volume, m5, m10, k.turnover);
            } else {
                document.getElementById('volTipVals').innerHTML = _buildVolValsHTML(null, null, null, null);
            }
        }

        // ---- MACD 图 ----
        var macd = KlineChartUtils.calcMACD(klinesData, macdParams.fast, macdParams.slow, macdParams.signal);
        var lastMACDArr = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(3) : '--'; };
        var macdVals = { dif: lastMACDArr(macd.dif), dea: lastMACDArr(macd.dea), macd: lastMACDArr(macd.macd) };
        var macdLines = [];
        var macdHist = macdChart.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false });
        macdHist.setData(macd.macd.map(function(v) { return { time: v.time, value: v.value, color: v.value >= 0 ? '#ef5350' : '#26a69a' }; }));
        macdLines.push({ s: macdHist, k: 'macd' });
        var difLine = macdChart.addLineSeries({ color: '#ffffff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        difLine.setData(macd.dif); macdLines.push({ s: difLine, k: 'dif' });
        var deaLine = macdChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        deaLine.setData(macd.dea); macdLines.push({ s: deaLine, k: 'dea' });

        function _refreshMacd() {
            var fast = parseInt(document.getElementById('macdFast').value) || macdParams.fast;
            var slow = parseInt(document.getElementById('macdSlow').value) || macdParams.slow;
            var sig = parseInt(document.getElementById('macdSignal').value) || macdParams.signal;
            fast = Math.max(2, Math.min(250, fast));
            slow = Math.max(3, Math.min(250, slow));
            sig = Math.max(1, Math.min(100, sig));
            macd = KlineChartUtils.calcMACD(klinesData, fast, slow, sig);
            macdVals.dif = lastMACDArr(macd.dif); macdVals.dea = lastMACDArr(macd.dea); macdVals.macd = lastMACDArr(macd.macd);
            macdLines.filter(function(x) { return x.k === 'dif'; })[0].s.setData(macd.dif);
            macdLines.filter(function(x) { return x.k === 'dea'; })[0].s.setData(macd.dea);
            macdLines.filter(function(x) { return x.k === 'macd'; })[0].s.setData(macd.macd.map(function(v) { return { time: v.time, value: v.value, color: v.value >= 0 ? '#ef5350' : '#26a69a' }; }));
            _refreshMacdVals();
        }
        document.getElementById('macdFast').addEventListener('change', _refreshMacd);
        document.getElementById('macdSlow').addEventListener('change', _refreshMacd);
        document.getElementById('macdSignal').addEventListener('change', _refreshMacd);

        // ---- KDJ 图 ----
        var kdj = KlineChartUtils.calcKDJ(klinesData, kdjParams.n, kdjParams.m1, kdjParams.m2);
        var lastKDJ = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        var kdjVals = { k: lastKDJ(kdj.k), d: lastKDJ(kdj.d), j: lastKDJ(kdj.j) };
        var kdjLines = [];
        [{v: kdj.k, c: '#ffffff'}, {v: kdj.d, c: '#fbbf24'}, {v: kdj.j, c: '#a78bfa'}].forEach(function(x) {
            var line = kdjChart.addLineSeries({ color: x.c, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
            line.setData(x.v);
            kdjLines.push(line);
        });

        function _buildKdjValsHTML(kVal, dVal, jVal) {
            return '<span style="color:#ffffff;">K:' + kVal + '</span> <span style="color:#fbbf24;">D:' + dVal + '</span> <span style="color:#a78bfa;">J:' + jVal + '</span>';
        }
        function _refreshKdj() {
            var n = parseInt(document.getElementById('kdjN').value) || kdjParams.n;
            var m1 = parseInt(document.getElementById('kdjM1').value) || kdjParams.m1;
            var m2 = parseInt(document.getElementById('kdjM2').value) || kdjParams.m2;
            n = Math.max(2, Math.min(120, n));
            m1 = Math.max(1, Math.min(100, m1));
            m2 = Math.max(1, Math.min(100, m2));
            kdj = KlineChartUtils.calcKDJ(klinesData, n, m1, m2);
            kdjVals.k = lastKDJ(kdj.k); kdjVals.d = lastKDJ(kdj.d); kdjVals.j = lastKDJ(kdj.j);
            [{v: kdj.k, idx: 0}, {v: kdj.d, idx: 1}, {v: kdj.j, idx: 2}].forEach(function(x) {
                kdjLines[x.idx].setData(x.v);
            });
            var tv = document.getElementById('kdjTipVals');
            if (tv) tv.innerHTML = _buildKdjValsHTML(kdjVals.k, kdjVals.d, kdjVals.j);
        }
        document.getElementById('kdjN').addEventListener('change', _refreshKdj);
        document.getElementById('kdjM1').addEventListener('change', _refreshKdj);
        document.getElementById('kdjM2').addEventListener('change', _refreshKdj);

        // ---- 均线（主图）----
        var maC = ['#fbbf24', '#60a5fa', '#a78bfa', '#f472b6', '#34d399', '#fb923c'];
        var maP = [5, 10, 20, 30, 60, 120];
        var maData = [];
        var maLines = [];
        for (var mi = 0; mi < maP.length; mi++) {
            var md = KlineChartUtils.calcSMA(klinesData, maP[mi]);
            maData.push(md);
            var line = mainChart.addLineSeries({ color: maC[mi], lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
            line.setData(md);
            maLines.push(line);
        }
        var lastMA = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        var maVals = {
            ma5: lastMA(maData[0]), ma10: lastMA(maData[1]),
            ma20: lastMA(maData[2]), ma30: lastMA(maData[3]),
            ma60: lastMA(maData[4]), ma120: lastMA(maData[5]),
        };

        // ---- 布林线（主图，默认隐藏）----
        var bbLines = [];
        var bb = KlineChartUtils.calcBB(klinesData);
        var lastBB = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        var bbVals = { up: lastBB(bb.up), mid: lastBB(bb.mid), lo: lastBB(bb.lo) };
        [{v: bb.up, d: true, c: '#ef5350'}, {v: bb.mid, d: false, c: '#60a5fa'}, {v: bb.lo, d: true, c: '#26a69a'}].forEach(function(x) {
            var line = mainChart.addLineSeries({ color: x.c, lineWidth: 1, lineStyle: x.d ? 2 : 0, priceLineVisible: false, lastValueVisible: false, visible: false });
            line.setData(x.v);
            bbLines.push(line);
        });

        // ---- 十字线（主图）----
        var tooltip = document.getElementById('klTooltip');
        var mainWrap = document.getElementById('klMainWrap');
        function _buildMacdValsHTML(difVal, deaVal, macdVal) {
            return '<span style="color:' + (parseFloat(macdVal) >= 0 ? '#ef5350' : '#26a69a') + ';">MACD:' + macdVal + '</span> <span style="color:#ffffff;">DIFF:' + difVal + '</span> <span style="color:#fbbf24;">DEA:' + deaVal + '</span>';
        }
        function _refreshMacdVals() {
            var mi = macd.dif.length - 1;
            if (mi >= 0) {
                document.getElementById('macdTipVals').innerHTML = _buildMacdValsHTML(macd.dif[mi].value.toFixed(3), macd.dea[mi].value.toFixed(3), macd.macd[mi].value.toFixed(3));
            } else {
                document.getElementById('macdTipVals').innerHTML = _buildMacdValsHTML(macdVals.dif, macdVals.dea, macdVals.macd);
            }
        }
        _refreshVolVals();
        document.getElementById('kdjTipVals').innerHTML = _buildKdjValsHTML(kdjVals.k, kdjVals.d, kdjVals.j);
        _refreshMacdVals();

        // ---- 根据时间更新各指标栏数值（VOL/MACD/KDJ）----
        function _updateTipsByTime(time, point) {
            if (!time) {
                tooltip.style.display = 'none';
                _refreshVolVals();
                document.getElementById('kdjTipVals').innerHTML = _buildKdjValsHTML(kdjVals.k, kdjVals.d, kdjVals.j);
                _refreshMacdVals();
                return;
            }
            var idx = -1;
            var tKey = typeof time === 'string' ? time :
                       time.year ? time.year + '-' + String(time.month).padStart(2,'0') + '-' + String(time.day).padStart(2,'0') : '';
            for (var i = 0; i < klinesData.length; i++) {
                if (klinesData[i].time === tKey) { idx = i; break; }
            }
            if (idx >= 0) {
                var k = klinesData[idx];
                var prevClose = idx > 0 ? klinesData[idx - 1].close : null;
                var etf = isETF(stockCode, stockMarket);
                tooltip.innerHTML = KlineChartUtils.tooltipText(k, prevClose, etf);
                tooltip.style.display = 'block';
                var rect = mainWrap.getBoundingClientRect();
                var left, top;
                if (point) {
                    left = point.x + 16;
                    top = point.y - 10;
                } else {
                    // 从副图触发，游标放到主图中间偏上
                    left = rect.width / 2 - 80;
                    top = 10;
                }
                if (left + 160 > rect.width) left = rect.width - 170;
                if (top + 180 > rect.height) top = rect.height - 190;
                if (top < 0) top = 0;
                if (left < 0) left = 0;
                tooltip.style.left = left + 'px';
                tooltip.style.top = top + 'px';
                _refreshVolVals(idx);
                if (idx >= 0 && idx < kdj.k.length && kdj.k[idx].value != null) {
                    document.getElementById('kdjTipVals').innerHTML = _buildKdjValsHTML(kdj.k[idx].value.toFixed(2), kdj.d[idx].value.toFixed(2), kdj.j[idx].value.toFixed(2));
                } else {
                    document.getElementById('kdjTipVals').innerHTML = _buildKdjValsHTML(kdjVals.k, kdjVals.d, kdjVals.j);
                }
                if (idx >= 0 && idx < macd.dif.length) {
                    document.getElementById('macdTipVals').innerHTML = _buildMacdValsHTML(macd.dif[idx].value.toFixed(3), macd.dea[idx].value.toFixed(3), macd.macd[idx].value.toFixed(3));
                } else {
                    _refreshMacdVals();
                }
            } else {
                tooltip.style.display = 'none';
                _refreshVolVals();
                document.getElementById('kdjTipVals').innerHTML = _buildKdjValsHTML(kdjVals.k, kdjVals.d, kdjVals.j);
                _refreshMacdVals();
            }
        }

        // ---- 同步十字光标移动 ----
        var _crosshairSyncLock = false;
        allCharts.forEach(function(c) {
            c.subscribeCrosshairMove(function(param) {
                if (_crosshairSyncLock || !param || param.time === undefined) return;
                _crosshairSyncLock = true;
                allCharts.forEach(function(tc) {
                    if (tc !== c) {
                        var targetSeries = null;
                        if (tc === volChart && volSeries) targetSeries = volSeries;
                        else if (tc === macdChart && macdHist) targetSeries = macdHist;
                        else if (tc === kdjChart && kdjLines && kdjLines.length > 0) targetSeries = kdjLines[0];
                        else if (tc === mainChart && series) targetSeries = series;
                        if (targetSeries) {
                            tc.setCrosshairPosition(null, param.time, targetSeries);
                        }
                    }
                });
                // 鼠标在副图上移动时，setCrosshairPosition 不会触发 subscribeCrosshairMove，
                // 需要手动更新指标栏数值和游标
                if (c !== mainChart) {
                    _updateTipsByTime(param.time, param.point);
                }
                _crosshairSyncLock = false;
            });
        });

        mainChart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point || !klinesData) {
                _updateTipsByTime(null);
                return;
            }
            _updateTipsByTime(param.time, param.point);
        });

        // ---- ResizeObserver ----
        var canvases = [mainCanvas, volCanvas, macdCanvas, kdjCanvas];
        var charts = [mainChart, volChart, macdChart, kdjChart];
        var observer = new ResizeObserver(function() {
            for (var i = 0; i < canvases.length; i++) {
                if (charts[i] && canvases[i].clientWidth > 0) {
                    charts[i].applyOptions({ width: canvases[i].clientWidth, height: canvases[i].clientHeight });
                }
            }
        });
        canvases.forEach(function(c) { observer.observe(c); });

        return { charts: charts, mainChart: mainChart, series: series, volSeries: volSeries, volMALines: [volMA5Line, volMA10Line], maLines: maLines, bbLines: bbLines, volVals: { m5: volMA5, m10: volMA10 }, macdLines: macdLines, macdVals: macdVals, kdjLines: kdjLines, kdjVals: kdjVals, maVals: maVals, bbVals: bbVals, observer: observer };
    },
    // 获取指标值 HTML
    getIndHTML: function(indicatorMode, maVals, bbVals, kdjVals) {
        var html = '';
        if (indicatorMode === 'ma' && maVals) {
            html = '<span style="color:#fbbf24;">MA5:' + maVals.ma5 + '</span> <span style="color:#60a5fa;">MA10:' + maVals.ma10 + '</span> <span style="color:#a78bfa;">MA20:' + maVals.ma20 + '</span> <span style="color:#f472b6;">MA30:' + maVals.ma30 + '</span> <span style="color:#34d399;">MA60:' + maVals.ma60 + '</span> <span style="color:#fb923c;">MA120:' + maVals.ma120 + '</span>';
        } else if (indicatorMode === 'bb' && bbVals) {
            html = '<span style="color:#ef5350;">UP:' + bbVals.up + '</span> <span style="color:#60a5fa;">MID:' + bbVals.mid + '</span> <span style="color:#26a69a;">LOW:' + bbVals.lo + '</span>';
        }
        return html;
    },
    // 切换指标显示
    switchIndicator: function(mode, maLines, bbLines) {
        for (var i = 0; i < maLines.length; i++) { if (maLines[i]) maLines[i].applyOptions({ visible: mode === 'ma' }); }
        for (var i = 0; i < bbLines.length; i++) { if (bbLines[i]) bbLines[i].applyOptions({ visible: mode === 'bb' }); }
    }
};
