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
    },
    // 渲染 K 线图，返回 { chart, series, volSeries, maLines, bbLines, observer }
    render: function(el, klinesData, stockCode) {
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';

        var chart = LightweightCharts.createChart(el, {
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

        var series = chart.addCandlestickSeries({
            upColor: '#ef5350', downColor: '#26a69a',
            borderUpColor: '#ef5350', borderDownColor: '#26a69a',
            wickUpColor: '#ef5350', wickDownColor: '#26a69a',
        });
        series.setData(klinesData.map(function(k) {
            return { time: k.time, open: k.open, high: k.high, low: k.low, close: k.close };
        }));

        var volSeries = chart.addHistogramSeries({
            priceFormat: { type: 'volume' }, priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
        volSeries.setData(klinesData.map(function(k) {
            return { time: k.time, value: k.volume, color: k.close >= k.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' };
        }));

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
        chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point || !klinesData) {
                tooltip.style.display = 'none';
                return;
            }
            var k = null, idx = -1;
            var tKey = typeof param.time === 'string' ? param.time :
                       param.time.year ? param.time.year + '-' + String(param.time.month).padStart(2,'0') + '-' + String(param.time.day).padStart(2,'0') : '';
            for (var i = 0; i < klinesData.length; i++) {
                if (klinesData[i].time === tKey) { k = klinesData[i]; idx = i; break; }
            }
            if (!k) { tooltip.style.display = 'none'; return; }
            var prevClose = idx > 0 ? klinesData[idx - 1].close : null;
            var isEtf = stockCode && (stockCode.indexOf('51') === 0 || stockCode.indexOf('15') === 0);
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
        });

        var observer = new ResizeObserver(function() {
            if (chart && el.clientWidth > 0) {
                chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
            }
        });
        observer.observe(el);

        return { chart: chart, series: series, volSeries: volSeries, maLines: maLines, bbLines: bbLines, maVals: maVals, bbVals: bbVals, observer: observer };
    },
    // 获取指标值 HTML
    getIndHTML: function(indicatorMode, maVals, bbVals) {
        if (indicatorMode === 'ma' && maVals) {
            return '<span style="color:#fbbf24;">MA5:' + maVals.ma5 + '</span> <span style="color:#60a5fa;">MA10:' + maVals.ma10 + '</span> <span style="color:#a78bfa;">MA20:' + maVals.ma20 + '</span> <span style="color:#f472b6;">MA30:' + maVals.ma30 + '</span> <span style="color:#34d399;">MA60:' + maVals.ma60 + '</span> <span style="color:#fb923c;">MA120:' + maVals.ma120 + '</span>';
        } else if (indicatorMode === 'bb' && bbVals) {
            return '<span style="color:#ef5350;">UP:' + bbVals.up + '</span> <span style="color:#60a5fa;">MID:' + bbVals.mid + '</span> <span style="color:#26a69a;">LOW:' + bbVals.lo + '</span>';
        }
        return '';
    },
    // 切换指标显示
    switchIndicator: function(mode, maLines, bbLines) {
        for (var i = 0; i < maLines.length; i++) { if (maLines[i]) maLines[i].applyOptions({ visible: mode === 'ma' }); }
        for (var i = 0; i < bbLines.length; i++) { if (bbLines[i]) bbLines[i].applyOptions({ visible: mode === 'bb' }); }
    }
};
