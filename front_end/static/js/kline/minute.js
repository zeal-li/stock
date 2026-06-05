// ==================== 分时图渲染 ====================

var KlineMinute = {
    render: function(el, times, prices, volumes, amounts, preClose, stockMarket) {
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';
        var isUS = stockMarket === '106', isHK = stockMarket === '116';
        var today = new Date(); var base = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() / 1000;
        var fullTimes = times.map(function(t) {
            if (isUS) return new Date(t).getTime() / 1000;
            var parts = t.split(':'); return base + parseInt(parts[0]) * 3600 + parseInt(parts[1]) * 60;
        });

        var pcts = prices.map(function(p) { return preClose ? ((p - preClose) / preClose * 100) : p; });

        var minuteFrom, minuteTo;
        if (isUS) { minuteFrom = fullTimes[0]; minuteTo = minuteFrom + 6.5 * 3600; }
        else if (isHK) { minuteFrom = base + 9*3600 + 30*60; minuteTo = base + 16*3600; }
        else { minuteFrom = base + 9*3600 + 30*60; minuteTo = base + 15*3600; }
        var allT = [], allP = [], allV = [], allA = [], di = 0;
        var lunchAStart = base + 11*3600 + 31*60, lunchAEnd = base + 13*3600;
        var lunchHKStart = base + 12*3600 + 1*60, lunchHKEnd = base + 13*3600;
        for (var t = minuteFrom; t <= minuteTo; t += 60) {
            if (!isUS && ((!isHK && t >= lunchAStart && t <= lunchAEnd) || (isHK && t >= lunchHKStart && t <= lunchHKEnd))) continue;
            allT.push(t);
            if (di < fullTimes.length && fullTimes[di] >= t - 30 && fullTimes[di] <= t + 30) {
                allP.push(pcts[di]); allV.push(volumes[di]); allA.push(amounts[di]); di++;
            } else { allP.push(null); allV.push(null); allA.push(null); }
        }

        var chart = LightweightCharts.createChart(el, {
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

        var lastValidIdx = -1;
        for (var vi = allP.length - 1; vi >= 0; vi--) { if (allP[vi] != null) { lastValidIdx = vi; break; } }

        var series = chart.addAreaSeries({ lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)', lineWidth: 1.5, priceLineVisible: false, priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(2) + '%'; } } });
        var lineData = []; for (var i = 0; i <= lastValidIdx; i++) lineData.push({ time: allT[i], value: allP[i] });
        series.setData(lineData);

        var avgData = [], avgSum = 0, avgN = 0;
        for (var i = 0; i <= lastValidIdx; i++) {
            if (allP[i] != null) { avgSum += prices[Math.min(avgN, prices.length - 1)]; avgN++; }
            avgData.push({ time: allT[i], value: allP[i] != null ? (avgN > 0 ? (preClose ? ((avgSum / avgN - preClose) / preClose * 100) : (avgSum / avgN)) : null) : null });
        }
        var avgLine = chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgData);

        var zLine = chart.addLineSeries({ color: '#888', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        zLine.setData([{ time: minuteFrom, value: 0 }, { time: minuteTo, value: 0 }]);

        var volSeries = null;
        if (volumes && volumes.length > 0) {
            volSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'volume' });
            chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
            var vd = [];
            for (var i = 0; i < allT.length; i++) {
                var up = (i > 0 && allP[i] != null && allP[i-1] != null) ? allP[i] >= allP[i-1] : true;
                vd.push({ time: allT[i], value: allV[i], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
            }
            volSeries.setData(vd);
        }

        var tooltip = document.getElementById('klTooltip');
        chart.subscribeCrosshairMove(function(param) {
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

        // 底部指标
        var lastP = prices[prices.length - 1], lastAvgV = null;
        for (var ai = avgData.length - 1; ai >= 0; ai--) { if (avgData[ai].value != null) { lastAvgV = avgData[ai].value; break; } }
        var lChg = preClose ? lastP - preClose : 0, lChgPct = preClose ? lChg / preClose * 100 : 0;
        var ls = lChg >= 0 ? '+' : '', lc = lChg >= 0 ? '#ef5350' : '#26a69a';
        var mv = document.getElementById('klMinuteVals');
        if (mv) mv.innerHTML = '<span style="color:#fbbf24;">均价:'+(preClose ? (lastAvgV*preClose/100+preClose).toFixed(2):'--')+'</span> <span style="color:#3b82f6;">最新:'+lastP.toFixed(2)+'</span> <span style="color:'+lc+';">'+ls+lChg.toFixed(2)+'</span> <span style="color:'+lc+';">'+ls+lChgPct.toFixed(2)+'%</span>';

        chart.timeScale().fitContent();
        chart.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true });

        var observer = new ResizeObserver(function() { if (chart && el.clientWidth > 0) chart.applyOptions({ width: el.clientWidth, height: el.clientHeight }); });
        observer.observe(el);

        return { chart: chart, series: series, avgLine: avgLine, volSeries: volSeries, 
                 minuteFrom: minuteFrom, minuteTo: minuteTo, allT: allT, allP: allP, allV: allV, allA: allA,
                 avgData: avgData, preClose: preClose, observer: observer };
    }
};
