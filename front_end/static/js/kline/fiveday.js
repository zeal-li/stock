// ==================== 五日分时图渲染 ====================

var KlineFiveDay = {
    render: function(el, raw, stockCode, stockMarket) {
        el.innerHTML = '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>';

        var times = raw.times, prices = raw.prices, volumes = raw.volumes || [], amounts = raw.amounts || [];
        var isHK = stockMarket === '116', isUS = stockMarket === '106';
        var _isOverseas5D = isHK || isUS;

        var allSlots, tsToDate, dayBasePrice, sortedDates;

        if (_isOverseas5D) {
            var _allSlots = [];
            var _tsToDate = {};
            var _dayBasePrice = {};
            var _sortedDates = [];
            var _seenDates = {};
            for (var i = 0; i < times.length; i++) {
                if (prices[i] == null) continue;
                var parts = times[i].split(' ');
                var date = parts[0], time = parts[1];
                var dp3 = date.split('-'), tp = time.split(':');
                var ts3 = Date.UTC(parseInt(dp3[0]), parseInt(dp3[1]) - 1, parseInt(dp3[2]),
                                  parseInt(tp[0]), parseInt(tp[1])) / 1000;
                if (!_seenDates[date]) {
                    _sortedDates.push(date);
                    _seenDates[date] = true;
                    _dayBasePrice[date] = prices[i];
                }
                _tsToDate[ts3] = date;
                _allSlots.push({ ts: ts3, price: prices[i], vol: volumes[i] || 0, amt: amounts[i] || 0 });
            }
            allSlots = _allSlots; tsToDate = _tsToDate; dayBasePrice = _dayBasePrice; sortedDates = _sortedDates;
        } else {
            var daySlots = {};
            for (var i = 0; i < times.length; i++) {
                if (prices[i] == null) continue;
                var p = times[i].split(' ');
                if (!daySlots[p[0]]) daySlots[p[0]] = {};
                daySlots[p[0]][p[1]] = { price: prices[i], vol: volumes[i] || 0, amt: amounts[i] || 0 };
            }
            sortedDates = Object.keys(daySlots).sort();

            allSlots = [];
            tsToDate = {};
            dayBasePrice = {};

            for (var di = 0; di < sortedDates.length; di++) {
                var ds = sortedDates[di];
                var dp = ds.split('-');
                var base = new Date(parseInt(dp[0]), parseInt(dp[1]) - 1, parseInt(dp[2])).getTime() / 1000;
                var slots = daySlots[ds];
                for (var t = base + 34500; t <= base + 41400; t += 300) {
                    var d2 = new Date(t * 1000);
                    var tk = String(d2.getHours()).padStart(2,'0') + ':' + String(d2.getMinutes()).padStart(2,'0');
                    var s2 = slots[tk];
                    tsToDate[t] = ds;
                    allSlots.push({ ts: t, price: s2 ? s2.price : null, vol: s2 ? s2.vol : 0, amt: s2 ? s2.amt : 0 });
                }
                for (var t = base + 47100; t <= base + 54000; t += 300) {
                    var d2 = new Date(t * 1000);
                    var tk = String(d2.getHours()).padStart(2,'0') + ':' + String(d2.getMinutes()).padStart(2,'0');
                    var s2 = slots[tk];
                    tsToDate[t] = ds;
                    allSlots.push({ ts: t, price: s2 ? s2.price : null, vol: s2 ? s2.vol : 0, amt: s2 ? s2.amt : 0 });
                }
            }

            for (var si = 0; si < allSlots.length; si++) {
                if (allSlots[si].price == null) continue;
                var dk = tsToDate[allSlots[si].ts];
                if (dk && !(dk in dayBasePrice)) dayBasePrice[dk] = allSlots[si].price;
            }
        }

        if (sortedDates.length === 0) { el.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;">无数据</div>'; return null; }

        var chart = LightweightCharts.createChart(el, {
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

        var areaData = [];
        for (var si = 0; si < allSlots.length; si++) {
            if (allSlots[si].price != null) areaData.push({ time: allSlots[si].ts, value: allSlots[si].price });
        }
        var _priceDec = (_isOverseas5D || isETF(stockCode, stockMarket)) ? 3 : 2;
        var areaSeries = chart.addAreaSeries({
            lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)',
            lineWidth: 1.5, priceLineVisible: false,
            priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(_priceDec); } }
        });
        areaSeries.setData(areaData);

        var avgLineData = [], avgSum = 0, avgCnt = 0;
        for (var si = 0; si < allSlots.length; si++) {
            if (allSlots[si].price != null) { avgSum += allSlots[si].price; avgCnt++; }
            avgLineData.push({ time: allSlots[si].ts, value: avgCnt > 0 ? avgSum / avgCnt : null });
        }
        var avgLine = chart.addLineSeries({ color: '#fbbf24', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgLineData);

        var volSeries = chart.addHistogramSeries({ priceFormat: { type: 'volume' }, priceScaleId: 'volume' });
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
        var vd = [];
        for (var si = 0; si < allSlots.length; si++) {
            var s2 = allSlots[si];
            if (s2.price == null) continue;
            var up = si > 0 ? (allSlots[si-1].price != null ? s2.price >= allSlots[si-1].price : true) : true;
            vd.push({ time: s2.ts, value: s2.vol, color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
        }
        volSeries.setData(vd);

        var firstBase = dayBasePrice[sortedDates[0]] || 0;
        var tooltip = document.getElementById('klTooltip');
        chart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point) { tooltip.style.display = 'none'; return; }
            var slot = null, slotIdx = -1;
            for (var si = 0; si < allSlots.length; si++) { if (allSlots[si].ts === param.time) { slot = allSlots[si]; slotIdx = si; break; } }
            if (!slot || slot.price == null) { tooltip.style.display = 'none'; return; }
            var d4 = new Date(param.time * 1000);
            var weekNames = ['周日','周一','周二','周三','周四','周五','周六'];
            var ds2 = d4.getFullYear() + '-' + String(d4.getMonth() + 1).padStart(2,'0') + '-' + String(d4.getDate()).padStart(2,'0') + ' ' + weekNames[d4.getDay()];
            var ts2 = String(d4.getHours()).padStart(2,'0') + ':' + String(d4.getMinutes()).padStart(2,'0');
            var curAvg = avgLineData[slotIdx] ? avgLineData[slotIdx].value : null;
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

        var lastP = null, lastAvg = null;
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

        chart.timeScale().fitContent();
        chart.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true });

        function _drawDayBounds() {
            el.querySelectorAll('.five-day-boundary').forEach(function(b) { b.remove(); });
            for (var di = 0; di < sortedDates.length - 1; di++) {
                var dp2 = sortedDates[di].split('-');
                var dayEndTs;
                if (_isOverseas5D) {
                    dayEndTs = 0;
                    for (var si = 0; si < allSlots.length; si++) {
                        if (tsToDate[allSlots[si].ts] === sortedDates[di] && allSlots[si].ts > dayEndTs) dayEndTs = allSlots[si].ts;
                    }
                } else {
                    dayEndTs = new Date(parseInt(dp2[0]), parseInt(dp2[1]) - 1, parseInt(dp2[2])).getTime() / 1000 + 54000;
                }
                if (!dayEndTs) continue;
                var x = chart.timeScale().timeToCoordinate(dayEndTs);
                if (x == null) continue;
                var line = document.createElement('div');
                line.className = 'five-day-boundary';
                line.style.cssText = 'position:absolute;top:0;bottom:28%;left:' + x + 'px;width:0;border-left:1px dashed rgba(160,100,255,0.6);pointer-events:none;z-index:5;';
                el.appendChild(line);
            }
        }
        requestAnimationFrame(function() { _drawDayBounds(); });

        var observer = new ResizeObserver(function() {
            if (chart && el.clientWidth > 0) chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
            requestAnimationFrame(function() { _drawDayBounds(); });
        });
        observer.observe(el);

        return { chart: chart, areaSeries: areaSeries, volSeries: volSeries, observer: observer };
    }
};
