// ==================== 五日分时图渲染（3 面板：五日分时 + 量 + MACD） ====================

var KlineFiveDay = {
    render: function(el, raw, stockCode, stockMarket) {
        el.innerHTML = '<style>#klChart a{display:none !important;}</style>';

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

        var _priceDec = (_isOverseas5D || isETF(stockCode, stockMarket)) ? 3 : 2;

        // ---- 构建 MACD 输入：用绝对价格 ----
        var macdInput = [];
        for (var i = 0; i < allSlots.length; i++) {
            if (allSlots[i].price != null) {
                macdInput.push({ time: allSlots[i].ts, close: allSlots[i].price });
            }
        }
        var macd = KlineChartUtils.calcMACD(macdInput, 12, 26, 9);

        // ---- 自定义时间刻度（每天起始时间）----
        var customTicks = [];
        for (var di = 0; di < sortedDates.length; di++) {
            var firstTs = null;
            for (var si = 0; si < allSlots.length; si++) {
                if (tsToDate[allSlots[si].ts] === sortedDates[di] && allSlots[si].price != null) {
                    firstTs = allSlots[si].ts; break;
                }
            }
            if (firstTs != null) customTicks.push({ time: firstTs });
        }

        var tickFmt = function(ts) {
            var d = new Date(ts * 1000);
            return (d.getMonth() + 1) + '/' + d.getDate();
        };

        // ---- 公共 Chart 配置 ----
        var subBase = {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', minimumWidth: 84, scaleMargins: { top: 0.05, bottom: 0.02 } },
            timeScale: { borderColor: '#2a2a4e', visible: false },
            handleScroll: { vertTouchDrag: false, horzTouchDrag: false, pressedMouseMove: false, mouseWheel: false },
            handleScale: { axisPressedMouseMove: false, pinch: false, mouseWheel: false },
        };

        // ---- DOM 结构（3 面板：主图 + 成交量 + MACD）----
        el.innerHTML +=
            '<div style="display:flex;flex-direction:column;height:100%;">' +
                // 主图（五日分时线 + 均价线）
                '<div id="fdMainWrap" style="flex:3;min-height:0;position:relative;">' +
                    '<div id="fdMainCanvas" style="width:100%;height:100%;"></div>' +
                    '<div id="fdTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>' +
                '</div>' +
                // 成交量指标栏
                '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">VOL <span id="fdVolTip"></span></div>' +
                // 成交量图
                '<div id="fdVolWrap" style="flex:1;min-height:0;position:relative;">' +
                    '<div id="fdVolCanvas" style="width:100%;height:100%;"></div>' +
                '</div>' +
                // MACD 指标栏
                '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">' +
                    'MACD(12,26,9) <span id="fdMacdTip"></span>' +
                '</div>' +
                // MACD 图（最下面，显示时间轴）
                '<div id="fdMacdWrap" style="flex:1;min-height:0;position:relative;">' +
                    '<div id="fdMacdCanvas" style="width:100%;height:100%;"></div>' +
                '</div>' +
            '</div>';

        // ---- 3 个 chart 实例 ----
        var mainCanvas = document.getElementById('fdMainCanvas');
        var volCanvas = document.getElementById('fdVolCanvas');
        var macdCanvas = document.getElementById('fdMacdCanvas');

        var mainChart = LightweightCharts.createChart(mainCanvas, Object.assign({}, subBase, {
            rightPriceScale: { borderColor: '#2a2a4e', minimumWidth: 84, scaleMargins: { top: 0.08, bottom: 0.02 } },
            width: mainCanvas.clientWidth, height: mainCanvas.clientHeight,
        }));
        var volChart = LightweightCharts.createChart(volCanvas, Object.assign({}, subBase, {
            width: volCanvas.clientWidth, height: volCanvas.clientHeight,
        }));
        var macdChart = LightweightCharts.createChart(macdCanvas, Object.assign({}, subBase, {
            crosshair: { mode: 1, vertLine: { labelVisible: false } },
            timeScale: { borderColor: '#2a2a4e', timeVisible: true, secondsVisible: false, tickMarkFormatter: tickFmt, ticks: customTicks },
            width: macdCanvas.clientWidth, height: macdCanvas.clientHeight,
        }));

        // ---- 同步时间轴 ----
        var _syncLock = false;
        var allCharts = [mainChart, volChart, macdChart];
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

        // ---- 主图：五日分时面积线 + 均价线 ----
        var lastValidIdx = -1;
        for (var vi = allSlots.length - 1; vi >= 0; vi--) { if (allSlots[vi].price != null) { lastValidIdx = vi; break; } }

        var areaData = [];
        for (var i = 0; i <= lastValidIdx; i++) {
            if (allSlots[i].price != null) areaData.push({ time: allSlots[i].ts, value: allSlots[i].price });
        }
        var areaSeries = mainChart.addAreaSeries({
            lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)',
            lineWidth: 1.5, priceLineVisible: false,
            priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(_priceDec); } }
        });
        areaSeries.setData(areaData);

        var avgLineData = [], avgSum = 0, avgCnt = 0;
        for (var i = 0; i < allSlots.length; i++) {
            if (allSlots[i].price != null) { avgSum += allSlots[i].price; avgCnt++; }
            avgLineData.push({ time: allSlots[i].ts, value: avgCnt > 0 ? avgSum / avgCnt : null });
        }
        var avgLine = mainChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgLineData);

        // ---- 成交量图 ----
        var volSeries = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
        var vd = [];
        for (var i = 0; i < allSlots.length; i++) {
            if (allSlots[i].price == null) continue;
            var up = i > 0 ? (allSlots[i - 1].price != null ? allSlots[i].price >= allSlots[i - 1].price : true) : true;
            vd.push({ time: allSlots[i].ts, value: allSlots[i].vol, color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
        }
        volSeries.setData(vd);

        // ---- 成交量均线 (MA5 / MA10) ----
        var volData = [];
        for (var i = 0; i < allSlots.length; i++) {
            if (allSlots[i].price != null) volData.push({ time: allSlots[i].ts, close: allSlots[i].vol });
        }
        var volMA5 = KlineChartUtils.calcSMA(volData, 5);
        var volMA10 = KlineChartUtils.calcSMA(volData, 10);
        var volMA5Line = volChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        volMA5Line.setData(volMA5);
        var volMA10Line = volChart.addLineSeries({ color: '#60a5fa', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        volMA10Line.setData(volMA10);

        // ---- MACD 图 ----
        var macdHist = macdChart.addHistogramSeries({ lastValueVisible: false, priceLineVisible: false });
        macdHist.setData(macd.macd.map(function(v) { return { time: v.time, value: v.value, color: v.value >= 0 ? '#ef5350' : '#26a69a' }; }));
        var difLine = macdChart.addLineSeries({ color: '#ffffff', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        difLine.setData(macd.dif);
        var deaLine = macdChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        deaLine.setData(macd.dea);

        // ---- 十字线同步 ----
        function _findCrossPrice(arr, time) {
            for (var i = 0; i < arr.length; i++) {
                if (arr[i].time === time) return arr[i].value;
            }
            return null;
        }
        var _crosshairSyncLock = false;
        allCharts.forEach(function(c) {
            c.subscribeCrosshairMove(function(param) {
                if (_crosshairSyncLock || !param || param.time === undefined) return;
                _crosshairSyncLock = true;
                allCharts.forEach(function(tc) {
                    if (tc !== c) {
                        var targetSeries = null;
                        var targetPrice = null;
                        if (tc === volChart && volSeries) {
                            targetSeries = volSeries;
                            targetPrice = _findCrossPrice(vd, param.time);
                        } else if (tc === macdChart && macdHist) {
                            targetSeries = macdHist;
                            targetPrice = _findCrossPrice(macd.macd, param.time);
                        } else if (tc === mainChart && areaSeries) {
                            targetSeries = areaSeries;
                            targetPrice = _findCrossPrice(areaData, param.time);
                        }
                        if (targetSeries) tc.setCrosshairPosition(targetPrice, param.time, targetSeries);
                    }
                });
                if (c !== mainChart) _updateFiveDayTips(param.time, param.point);
                _crosshairSyncLock = false;
            });
        });

        // ---- Tooltip 与指标栏 ----
        var tooltip = document.getElementById('fdTooltip');
        var mainWrap = document.getElementById('fdMainWrap');
        var firstBase = dayBasePrice[sortedDates[0]] || 0;

        function _fmtFiveDayVol(v) {
            if (v == null || isNaN(v) || v <= 0) return '--';
            return v >= 1e8 ? (v / 1e8).toFixed(2) + '亿股' : v >= 1e4 ? (v / 1e4).toFixed(2) + '万股' : v + '股';
        }

        function _updateFiveDayTips(time, point) {
            if (!time) {
                tooltip.style.display = 'none';
                _resetFiveDayTips();
                return;
            }
            var slotIdx = -1;
            for (var i = 0; i < allSlots.length; i++) { if (allSlots[i].ts === time) { slotIdx = i; break; } }
            if (slotIdx < 0 || allSlots[slotIdx].price == null) {
                tooltip.style.display = 'none';
                _resetFiveDayTips();
                return;
            }
            var slot = allSlots[slotIdx];
            var d = new Date(time * 1000);
            var weekNames = ['周日','周一','周二','周三','周四','周五','周六'];
            var ds = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0') + ' ' + weekNames[d.getDay()];
            var ts = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
            var curAvg = avgLineData[slotIdx] ? avgLineData[slotIdx].value : null;
            var chgPct = firstBase ? (slot.price - firstBase) / firstBase * 100 : 0;
            var chgSign = chgPct >= 0 ? '+' : '', chgColor = chgPct >= 0 ? '#ef5350' : '#26a69a';
            var volStr = slot.vol >= 1e8 ? (slot.vol/1e8).toFixed(2)+'亿' : slot.vol >= 1e4 ? (slot.vol/1e4).toFixed(2)+'万' : String(slot.vol);
            var amtStr = slot.amt >= 1e8 ? (slot.amt/1e8).toFixed(2)+'亿' : slot.amt >= 1e4 ? (slot.amt/1e4).toFixed(2)+'万' : String(slot.amt);

            tooltip.innerHTML = '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">'+ds+' '+ts+'</div><table style="border-spacing:0;">'+
                '<tr><td style="color:#888;">价格</td><td><span style="color:#3b82f6;">'+slot.price.toFixed(_priceDec)+'</span></td></tr>'+
                '<tr><td style="color:#888;">均价</td><td><span style="color:#fbbf24;">'+(curAvg != null ? curAvg.toFixed(_priceDec) : '--')+'</span></td></tr>'+
                '<tr><td style="color:#888;">涨幅</td><td><span style="color:'+chgColor+';">'+chgSign+chgPct.toFixed(2)+'%</span></td></tr>'+
                '<tr><td style="color:#888;">成交</td><td><span style="color:#ddd;">'+volStr+'</span></td></tr>'+
                '<tr><td style="color:#888;">成交额</td><td><span style="color:#ddd;">'+amtStr+'</span></td></tr></table>';
            tooltip.style.display = 'block';
            var rect = mainWrap.getBoundingClientRect();
            var left, top;
            if (point) {
                left = point.x + 16; top = point.y - 10;
            } else {
                left = rect.width / 2 - 80; top = 10;
            }
            if (left + 120 > rect.width) left = rect.width - 130;
            if (top + 80 > rect.height) top = rect.height - 90;
            if (top < 0) top = 0;
            if (left < 0) left = 0;
            tooltip.style.left = left + 'px'; tooltip.style.top = top + 'px';

            // VOL 指标栏
            var vt = document.getElementById('fdVolTip');
            if (vt) {
                var rawIdx = 0;
                for (var ri = 0; ri <= slotIdx; ri++) { if (allSlots[ri].price != null) rawIdx++; }
                rawIdx = Math.max(0, rawIdx - 1);
                var m5v = rawIdx >= 4 && rawIdx - 4 < volMA5.length ? volMA5[rawIdx - 4].value : null;
                var m10v = rawIdx >= 9 && rawIdx - 9 < volMA10.length ? volMA10[rawIdx - 9].value : null;
                vt.innerHTML = '<span style="color:#ddd;">量:'+volStr+'</span> <span style="color:#fbbf24;">M5:'+_fmtFiveDayVol(m5v)+'</span> <span style="color:#60a5fa;">M10:'+_fmtFiveDayVol(m10v)+'</span> <span style="color:#ddd;">额:'+amtStr+'</span>';
            }

            // MACD 指标栏
            var mt = document.getElementById('fdMacdTip');
            if (mt) {
                var macdIdx = macd.macd.length - 1;
                for (var mi = 0; mi < macd.macd.length; mi++) {
                    if (macd.macd[mi].time === time) { macdIdx = mi; break; }
                }
                macdIdx = Math.min(macdIdx, macd.macd.length - 1);
                var macdVal = macd.macd[macdIdx];
                var difVal = macd.dif[macdIdx];
                var deaVal = macd.dea[macdIdx];
                mt.innerHTML = '<span style="color:'+(macdVal.value>=0?'#ef5350':'#26a69a')+';">MACD:'+macdVal.value.toFixed(3)+'</span> <span style="color:#ffffff;">DIFF:'+difVal.value.toFixed(3)+'</span> <span style="color:#fbbf24;">DEA:'+deaVal.value.toFixed(3)+'</span>';
            }
        }

        function _resetFiveDayTips() {
            var vt = document.getElementById('fdVolTip');
            if (vt) {
                var lastM5 = volMA5.length > 0 ? volMA5[volMA5.length - 1].value : null;
                var lastM10 = volMA10.length > 0 ? volMA10[volMA10.length - 1].value : null;
                vt.innerHTML = '<span style="color:#ddd;">量:--</span> <span style="color:#fbbf24;">M5:'+_fmtFiveDayVol(lastM5)+'</span> <span style="color:#60a5fa;">M10:'+_fmtFiveDayVol(lastM10)+'</span> <span style="color:#ddd;">额:--</span>';
            }
            var mt = document.getElementById('fdMacdTip');
            if (mt) {
                var lastMacd = macd.macd[macd.macd.length - 1];
                var lastDif = macd.dif[macd.dif.length - 1];
                var lastDea = macd.dea[macd.dea.length - 1];
                mt.innerHTML = '<span style="color:'+(lastMacd.value>=0?'#ef5350':'#26a69a')+';">MACD:'+lastMacd.value.toFixed(3)+'</span> <span style="color:#ffffff;">DIFF:'+lastDif.value.toFixed(3)+'</span> <span style="color:#fbbf24;">DEA:'+lastDea.value.toFixed(3)+'</span>';
            }
        }

        mainChart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point) { _updateFiveDayTips(null); return; }
            _updateFiveDayTips(param.time, param.point);
        });

        // 初始指标栏
        _resetFiveDayTips();

        // ---- 底部统计（kl5DayVals）----
        var lastP = null, lastAvg = null;
        for (var li = allSlots.length - 1; li >= 0; li--) {
            if (allSlots[li].price != null) { lastP = allSlots[li].price; break; }
        }
        for (var ai = avgLineData.length - 1; ai >= 0; ai--) {
            if (avgLineData[ai].value != null) { lastAvg = avgLineData[ai].value; break; }
        }
        if (lastP != null && firstBase) {
            var lChg = lastP - firstBase, lChgPct = firstBase ? lChg / firstBase * 100 : 0;
            var lc = lChg >= 0 ? '#ef5350' : '#26a69a', ls = lChg >= 0 ? '+' : '';
            var m5v = document.getElementById('kl5DayVals');
            if (m5v) m5v.innerHTML = '<span style="color:#fbbf24;">均价:'+(lastAvg != null ? lastAvg.toFixed(_priceDec):'--')+'</span> <span style="color:#3b82f6;">最新:'+lastP.toFixed(_priceDec)+'</span> <span style="color:'+lc+';">'+ls+lChg.toFixed(_priceDec)+'</span> <span style="color:'+lc+';">'+ls+lChgPct.toFixed(2)+'%</span>';
        }

        // ---- 固定时间轴范围：全时段隐形线 ----
        // 主图用实际价格区间内的值，避免 value=0 把 Y 轴拉到底
        var _mainDummyVal = areaData.length > 0 ? areaData[0].value : 0;
        var _mainRangeData = [];
        for (var _i = 0; _i < allSlots.length; _i++) _mainRangeData.push({ time: allSlots[_i].ts, value: _mainDummyVal });
        mainChart.addLineSeries({ lineWidth: 1, color: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(_mainRangeData);
        // 成交量、MACD 图用 value=0 隐形线即可
        var _subRangeData = [];
        for (var _i = 0; _i < allSlots.length; _i++) _subRangeData.push({ time: allSlots[_i].ts, value: 0 });
        volChart.addLineSeries({ lineWidth: 1, color: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(_subRangeData);
        macdChart.addLineSeries({ lineWidth: 1, color: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(_subRangeData);

        mainChart.timeScale().fitContent();
        allCharts.forEach(function(c) {
            c.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true });
        });

        // ---- 日分界虚线（画在主图区域）----
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
                var x = mainChart.timeScale().timeToCoordinate(dayEndTs);
                if (x == null) continue;
                var line = document.createElement('div');
                line.className = 'five-day-boundary';
                line.style.cssText = 'position:absolute;top:0;bottom:0;left:' + x + 'px;width:0;border-left:1px dashed rgba(160,100,255,0.6);pointer-events:none;z-index:5;';
                mainWrap.appendChild(line);
            }
        }
        requestAnimationFrame(function() { _drawDayBounds(); });

        // ---- ResizeObserver ----
        var canvases = [mainCanvas, volCanvas, macdCanvas];
        var charts = [mainChart, volChart, macdChart];
        var observer = new ResizeObserver(function() {
            for (var i = 0; i < canvases.length; i++) {
                if (charts[i] && canvases[i].clientWidth > 0) {
                    charts[i].applyOptions({ width: canvases[i].clientWidth, height: canvases[i].clientHeight });
                }
            }
            requestAnimationFrame(function() { _drawDayBounds(); });
        });
        canvases.forEach(function(c) { observer.observe(c); });

        return {
            chart: mainChart,
            charts: charts,
            areaSeries: areaSeries,
            volSeries: volSeries,
            macdLines: [{ s: macdHist, k: 'macd' }, { s: difLine, k: 'dif' }, { s: deaLine, k: 'dea' }],
            macd: macd,
            observer: observer,
        };
    }
};
