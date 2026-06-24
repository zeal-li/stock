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
    // KDJ 计算 (n=9)
    calcKDJ: function(data, n) {
        n = n || 9;
        var kData = [], dData = [], jData = [];
        var k = 50, d = 50;
        for (var i = n - 1; i < data.length; i++) {
            var highN = data[i].high, lowN = data[i].low;
            for (var j = i - n + 1; j <= i; j++) {
                if (data[j].high > highN) highN = data[j].high;
                if (data[j].low < lowN) lowN = data[j].low;
            }
            var rng = highN - lowN;
            var rsv = rng > 0 ? (data[i].close - lowN) / rng * 100 : 50;
            k = 2/3 * k + 1/3 * rsv;
            d = 2/3 * d + 1/3 * k;
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
    render: function(el, klinesData, stockCode, stockMarket) {
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>' +
            '<div id="klKDJTip" style="position:absolute;z-index:9999;pointer-events:none;left:8px;font-size:12px;line-height:1.6;background:rgba(26,26,46,0.88);border-radius:4px;padding:2px 6px;white-space:nowrap;"></div>';

        var chart = LightweightCharts.createChart(el, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', scaleMargins: { top: 0.05, bottom: 0.45 } },
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

        var series = chart.addCandlestickSeries({
            upColor: '#ef5350', downColor: '#26a69a',
            borderUpColor: '#ef5350', borderDownColor: '#26a69a',
            wickUpColor: '#ef5350', wickDownColor: '#26a69a',
        });
        series.setData(klinesData.map(function(k) {
            return { time: k.time, open: k.open, high: k.high, low: k.low, close: k.close };
        }));

        var volSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' }, priceScaleId: 'volume', lastValueVisible: false, priceLineVisible: false,
        });
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.60, bottom: 0.22 }, visible: false });
        volSeries.setData(klinesData.map(function(k) {
            return { time: k.time, value: k.volume, color: k.close >= k.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' };
        }));

        // KDJ 指标（成交量下方）
        var kdj = KlineChartUtils.calcKDJ(klinesData);
        var lastKDJ = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        var kdjVals = { k: lastKDJ(kdj.k), d: lastKDJ(kdj.d), j: lastKDJ(kdj.j) };
        var kdjLines = [];
        [{v: kdj.k, c: '#ffffff', label: 'K'}, {v: kdj.d, c: '#fbbf24', label: 'D'}, {v: kdj.j, c: '#a78bfa', label: 'J'}].forEach(function(x) {
            var line = chart.addLineSeries({ color: x.c, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, priceScaleId: 'kdj' });
            line.setData(x.v);
            kdjLines.push(line);
        });
        chart.priceScale('kdj').applyOptions({ scaleMargins: { top: 0.82, bottom: 0.01 } });

        // 均线
        var maC = ['#fbbf24', '#60a5fa', '#a78bfa', '#f472b6', '#34d399', '#fb923c'];
        var maP = [5, 10, 20, 30, 60, 120];
        var maData = [];
        var maLines = [];
        for (var mi = 0; mi < maP.length; mi++) {
            var md = KlineChartUtils.calcSMA(klinesData, maP[mi]);
            maData.push(md);
            var line = chart.addLineSeries({ color: maC[mi], lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
            line.setData(md);
            maLines.push(line);
        }
        var lastMA = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        var maVals = {
            ma5: lastMA(maData[0]), ma10: lastMA(maData[1]),
            ma20: lastMA(maData[2]), ma30: lastMA(maData[3]),
            ma60: lastMA(maData[4]), ma120: lastMA(maData[5]),
        };

        // 布林线（默认隐藏）
        var bbLines = [];
        var bb = KlineChartUtils.calcBB(klinesData);
        var lastBB = function(arr) { return arr.length > 0 ? arr[arr.length - 1].value.toFixed(2) : '--'; };
        var bbVals = { up: lastBB(bb.up), mid: lastBB(bb.mid), lo: lastBB(bb.lo) };
        [{v: bb.up, d: true, c: '#ef5350'}, {v: bb.mid, d: false, c: '#60a5fa'}, {v: bb.lo, d: true, c: '#26a69a'}].forEach(function(x) {
            var line = chart.addLineSeries({ color: x.c, lineWidth: 1, lineStyle: x.d ? 2 : 0, priceLineVisible: false, lastValueVisible: false, visible: false });
            line.setData(x.v);
            bbLines.push(line);
        });

        // 十字线
        var tooltip = document.getElementById('klTooltip');
        var kdjTip = document.getElementById('klKDJTip');
        // 初始显示最新 KDJ 值
        kdjTip.innerHTML = 'KDJ(9,3,3) <span style="color:#ffffff;">K:' + kdjVals.k + '</span> <span style="color:#fbbf24;">D:' + kdjVals.d + '</span> <span style="color:#a78bfa;">J:' + kdjVals.j + '</span>';
        chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point || !klinesData) {
                tooltip.style.display = 'none';
                // 鼠标离开十字线时恢复最新值
                kdjTip.innerHTML = 'KDJ(9,3,3) <span style="color:#ffffff;">K:' + kdjVals.k + '</span> <span style="color:#fbbf24;">D:' + kdjVals.d + '</span> <span style="color:#a78bfa;">J:' + kdjVals.j + '</span>';
                return;
            }
            var k = null, idx = -1;
            var tKey = typeof param.time === 'string' ? param.time :
                       param.time.year ? param.time.year + '-' + String(param.time.month).padStart(2,'0') + '-' + String(param.time.day).padStart(2,'0') : '';
            for (var i = 0; i < klinesData.length; i++) {
                if (klinesData[i].time === tKey) { k = klinesData[i]; idx = i; break; }
            }
            if (!k) {
                tooltip.style.display = 'none';
                kdjTip.innerHTML = 'KDJ(9,3,3) <span style="color:#ffffff;">K:' + kdjVals.k + '</span> <span style="color:#fbbf24;">D:' + kdjVals.d + '</span> <span style="color:#a78bfa;">J:' + kdjVals.j + '</span>';
                return;
            }
            var prevClose = idx > 0 ? klinesData[idx - 1].close : null;
            var isEtf = isETF(stockCode, stockMarket);
            tooltip.innerHTML = KlineChartUtils.tooltipText(k, prevClose, isEtf);
            tooltip.style.display = 'block';
            var rect = el.getBoundingClientRect();
            var left = param.point.x + 16;
            var top = param.point.y - 10;
            if (left + 160 > rect.width) left = param.point.x - 170;
            if (top + 180 > rect.height) top = rect.height - 190;
            if (top < 0) top = 0;
            tooltip.style.left = left + 'px';
            tooltip.style.top = top + 'px';
            // 更新 KDJ 左上角值
            var kdjIdx = idx - 8;
            if (kdjIdx >= 0 && kdjIdx < kdj.k.length) {
                kdjTip.innerHTML = 'KDJ(9,3,3) <span style="color:#ffffff;">K:' + kdj.k[kdjIdx].value.toFixed(2) + '</span> <span style="color:#fbbf24;">D:' + kdj.d[kdjIdx].value.toFixed(2) + '</span> <span style="color:#a78bfa;">J:' + kdj.j[kdjIdx].value.toFixed(2) + '</span>';
            } else {
                kdjTip.innerHTML = 'KDJ(9,3,3) <span style="color:#ffffff;">K:' + kdjVals.k + '</span> <span style="color:#fbbf24;">D:' + kdjVals.d + '</span> <span style="color:#a78bfa;">J:' + kdjVals.j + '</span>';
            }
        });

        var observer = new ResizeObserver(function() {
            if (chart && el.clientWidth > 0) {
                chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
                // KDJ 标签定位到 KDJ 图表窗格顶部（82% 处）
                var timeScaleH = 28;
                var priceH = el.clientHeight - timeScaleH;
                kdjTip.style.bottom = (timeScaleH + priceH * 0.18 - 2) + 'px';
            }
        });
        observer.observe(el);
        // 初始设置 KDJ 标签位置
        var timeScaleH0 = 28;
        var priceH0 = el.clientHeight - timeScaleH0;
        kdjTip.style.bottom = (timeScaleH0 + priceH0 * 0.18 - 2) + 'px';

        return { chart: chart, series: series, volSeries: volSeries, maLines: maLines, bbLines: bbLines, kdjLines: kdjLines, kdjVals: kdjVals, maVals: maVals, bbVals: bbVals, observer: observer };
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
