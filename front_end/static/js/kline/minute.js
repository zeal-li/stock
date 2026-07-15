// ==================== 分时图渲染（3 面板：分时线 + 量 + MACD） ====================

var KlineMinute = {
    render: function(el, times, prices, volumes, amounts, preClose, stockMarket, stockCode) {
        el.innerHTML = '<style>#klChart a{display:none !important;}</style>';
        var priceDec = isETF(stockCode, stockMarket) ? 3 : 2;
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

        // ---- 构建 MACD 输入：用绝对价格前向填充（午休等空槽位填充，但未来空槽位不填充） ----
        function _buildMacdInput(allT2, allP2, prices2) {
            var data = [], lastPrice = null, rawCount = 0;
            for (var i = 0; i < allT2.length; i++) {
                if (allP2[i] != null) {
                    lastPrice = prices2[Math.min(rawCount, prices2.length - 1)];
                    rawCount++;
                } else if (rawCount >= prices2.length) {
                    // 所有真实数据已消费完毕，后续全是未来空槽位，不再填充
                    break;
                }
                if (lastPrice != null) {
                    data.push({ time: allT2[i], close: lastPrice });
                }
            }
            return data;
        }
        var macdInput = _buildMacdInput(allT, allP, prices);
        var macd = KlineChartUtils.calcMACD(macdInput, 12, 26, 9);

        var tickFmt = function(ts) {
            var d = new Date(ts * 1000), h = d.getHours(), m = d.getMinutes();
            if (isUS) return (d.getMonth()+1)+'/'+d.getDate()+' '+String(h).padStart(2,'0')+':'+String(m).padStart(2,'0');
            return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0');
        };

        var subBase = {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 1 },
            rightPriceScale: { borderColor: '#2a2a4e', minimumWidth: 84, scaleMargins: { top: 0.05, bottom: 0.02 } },
            timeScale: { borderColor: '#2a2a4e', visible: false },
            handleScroll: { vertTouchDrag: false, horzTouchDrag: false, pressedMouseMove: false, mouseWheel: false },
            handleScale: { axisPressedMouseMove: false, pinch: false, mouseWheel: false },
        };

        // 生成自定义时间刻度（30 分钟间隔，跳过午休）
        var customTicks = [];
        var tickStep = 30 * 60; // 30分钟
        for (var tt = minuteFrom; tt <= minuteTo; tt += tickStep) {
            if (!isUS && ((!isHK && tt >= lunchAStart && tt <= lunchAEnd) || (isHK && tt >= lunchHKStart && tt <= lunchHKEnd))) continue;
            customTicks.push({ time: tt });
        }

        // ---- DOM 结构 ----
        el.innerHTML +=
            '<div style="display:flex;flex-direction:column;height:100%;">' +
                // 主图（分时线 + 均价线）
                '<div id="mnMainWrap" style="flex:3;min-height:0;position:relative;">' +
                    '<div id="mnMainCanvas" style="width:100%;height:100%;"></div>' +
                    '<div id="mnTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>' +
                '</div>' +
                // 成交量指标栏
                '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">VOL <span id="mnVolTip"></span></div>' +
                // 成交量图
                '<div id="mnVolWrap" style="flex:1;min-height:0;position:relative;">' +
                    '<div id="mnVolCanvas" style="width:100%;height:100%;"></div>' +
                '</div>' +
                // MACD 指标栏
                '<div style="flex-shrink:0;padding:2px 7px;font-size:11px;line-height:18px;color:#8b8b9e;white-space:nowrap;border-top:1px solid #2a2a4e;background:#1e1e2e;">' +
                    'MACD(12,26,9) <span id="mnMacdTip"></span>' +
                '</div>' +
                // MACD 图（最下面，显示时间轴）
                '<div id="mnMacdWrap" style="flex:1;min-height:0;position:relative;">' +
                    '<div id="mnMacdCanvas" style="width:100%;height:100%;"></div>' +
                '</div>' +
            '</div>';

        // ---- 3 个 chart 实例 ----
        var mainCanvas = document.getElementById('mnMainCanvas');
        var volCanvas = document.getElementById('mnVolCanvas');
        var macdCanvas = document.getElementById('mnMacdCanvas');

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

        // ---- 主图：分时面积线 + 均价线 + 零线 ----
        var lastValidIdx = -1;
        for (var vi = allP.length - 1; vi >= 0; vi--) { if (allP[vi] != null) { lastValidIdx = vi; break; } }

        var series = mainChart.addAreaSeries({
            lineColor: '#3b82f6', topColor: 'rgba(59,130,246,0.25)', bottomColor: 'rgba(59,130,246,0.02)',
            lineWidth: 1.5, priceLineVisible: false,
            priceFormat: { type: 'custom', formatter: function(v) { return v.toFixed(2) + '%'; } }
        });
        var lineData = []; for (var i = 0; i <= lastValidIdx; i++) lineData.push({ time: allT[i], value: allP[i] });
        series.setData(lineData);

        var avgData = [], avgSum = 0, avgN = 0;
        for (var i = 0; i <= lastValidIdx; i++) {
            if (allP[i] != null) { avgSum += prices[Math.min(avgN, prices.length - 1)]; avgN++; }
            avgData.push({ time: allT[i], value: allP[i] != null ? (avgN > 0 ? (preClose ? ((avgSum / avgN - preClose) / preClose * 100) : (avgSum / avgN)) : null) : null });
        }
        var avgLine = mainChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        avgLine.setData(avgData);

        var zLine = mainChart.addLineSeries({ color: '#888', lineWidth: 1, lineStyle: 2, priceLineVisible: false, lastValueVisible: false });
        zLine.setData([{ time: minuteFrom, value: 0 }, { time: minuteTo, value: 0 }]);

        // ---- 成交量图 ----
        var volSeries = volChart.addHistogramSeries({ priceFormat: { type: 'volume' }, lastValueVisible: false, priceLineVisible: false });
        var vd = [];
        for (var i = 0; i < allT.length; i++) {
            if (allP[i] == null) continue;  // 跳过无数据的空槽位
            var up = (i > 0 && allP[i] != null && allP[i-1] != null) ? allP[i] >= allP[i-1] : true;
            vd.push({ time: allT[i], value: allV[i], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
        }
        volSeries.setData(vd);

        // ---- 成交量均线 ----
        var volData = [];
        for (var i = 0; i < allT.length; i++) {
            if (allV[i] != null) volData.push({ time: allT[i], close: allV[i] });
        }
        var volMA5 = KlineChartUtils.calcSMA(volData, 5);
        var volMA10 = KlineChartUtils.calcSMA(volData, 10);
        var volMA5Line = volChart.addLineSeries({ color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        volMA5Line.setData(volMA5);
        var volMA10Line = volChart.addLineSeries({ color: '#60a5fa', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
        volMA10Line.setData(volMA10);

        function _fmtMinuteVol(v) {
            if (v == null || isNaN(v) || v <= 0) return '--';
            return v >= 1e8 ? (v / 1e8).toFixed(2) + '亿股' : v >= 1e4 ? (v / 1e4).toFixed(2) + '万股' : v + '股';
        }

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
                        } else if (tc === mainChart && series) {
                            targetSeries = series;
                            targetPrice = _findCrossPrice(lineData, param.time);
                        }
                        if (targetSeries) tc.setCrosshairPosition(targetPrice, param.time, targetSeries);
                    }
                });
                // 非主图触发时手动更新指标栏和游标
                if (c !== mainChart) _updateMinuteTips(param.time, param.point);
                _crosshairSyncLock = false;
            });
        });

        var tooltip = document.getElementById('mnTooltip');
        var mainWrap = document.getElementById('mnMainWrap');

        function _updateMinuteTips(time, point) {
            if (!time) {
                tooltip.style.display = 'none';
                _resetMinuteTips();
                return;
            }
            var idx = -1;
            for (var i = 0; i < allT.length; i++) { if (allT[i] === time) { idx = i; break; } }
            if (idx < 0 || allP[idx] == null) {
                tooltip.style.display = 'none';
                _resetMinuteTips();
                return;
            }
            var rawIdx = 0; for (var ri = 0; ri <= idx; ri++) { if (allP[ri] != null) rawIdx++; } rawIdx--;
            var d = new Date(time * 1000);
            var ds = d.getFullYear() + '-' + String(d.getMonth()+1).padStart(2,'0') + '-' + String(d.getDate()).padStart(2,'0');
            var ts = String(d.getHours()).padStart(2,'0') + ':' + String(d.getMinutes()).padStart(2,'0');
            var pr = prices[rawIdx], vl = volumes[rawIdx] || 0, am = amounts[rawIdx] || 0;
            var vs = vl >= 1e8 ? (vl/1e8).toFixed(2)+'亿股' : vl >= 1e4 ? (vl/1e4).toFixed(2)+'万股' : vl+'股';
            var as = am >= 1e8 ? (am/1e8).toFixed(2)+'亿' : am >= 1e4 ? (am/1e4).toFixed(2)+'万' : String(am);
            var pc = (pr - preClose) / preClose * 100, pcs = pc >= 0 ? '+' : '', pcc = pc >= 0 ? '#ef5350' : '#26a69a';
            var av = idx < avgData.length ? avgData[idx].value : null;
            var ap = (av != null && preClose) ? (av * preClose / 100 + preClose) : null;

            // 游标
            tooltip.innerHTML = '<div style="font-weight:600;color:#fff;margin-bottom:4px;text-align:center;">'+ds+' '+ts+'</div><table style="border-spacing:0;">'+
                '<tr><td style="color:#888;">价格</td><td><span style="color:#3b82f6;">'+pr.toFixed(priceDec)+'</span></td></tr>'+
                '<tr><td style="color:#888;">均价</td><td><span style="color:#fbbf24;">'+(ap?ap.toFixed(priceDec):'--')+'</span></td></tr>'+
                '<tr><td style="color:#888;">涨幅</td><td><span style="color:'+pcc+';">'+pcs+pc.toFixed(2)+'%</span></td></tr>'+
                '<tr><td style="color:#888;">成交</td><td><span style="color:#ddd;">'+vs+'</span></td></tr>'+
                '<tr><td style="color:#888;">成交额</td><td><span style="color:#ddd;">'+as+'</span></td></tr></table>';
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

            // 指标栏
            var vt = document.getElementById('mnVolTip');
            if (vt) {
                var m5v = (rawIdx >= 4 && rawIdx - 4 < volMA5.length) ? volMA5[rawIdx - 4].value : null;
                var m10v = (rawIdx >= 9 && rawIdx - 9 < volMA10.length) ? volMA10[rawIdx - 9].value : null;
                vt.innerHTML = '<span style="color:#ddd;">量:'+vs+'</span> <span style="color:#fbbf24;">M5:'+_fmtMinuteVol(m5v)+'</span> <span style="color:#60a5fa;">M10:'+_fmtMinuteVol(m10v)+'</span> <span style="color:#ddd;">额:'+as+'</span>';
            }
            var mt = document.getElementById('mnMacdTip');
            if (mt) {
                var macdIdx = macd.macd.length - 1;
                for (var mi = 0; mi < macd.macd.length; mi++) {
                    if (macd.macd[mi].time === time || (isUS && Math.abs(macd.macd[mi].time - time) < 120)) { macdIdx = mi; break; }
                }
                var macdVal = macd.macd[Math.min(macdIdx, macd.macd.length - 1)];
                var difVal = macd.dif[Math.min(macdIdx, macd.dif.length - 1)];
                var deaVal = macd.dea[Math.min(macdIdx, macd.dea.length - 1)];
                mt.innerHTML = '<span style="color:'+(macdVal.value>=0?'#ef5350':'#26a69a')+';">MACD:'+macdVal.value.toFixed(3)+'</span> <span style="color:#ffffff;">DIFF:'+difVal.value.toFixed(3)+'</span> <span style="color:#fbbf24;">DEA:'+deaVal.value.toFixed(3)+'</span>';
            }
        }

        function _resetMinuteTips() {
            var vt2 = document.getElementById('mnVolTip');
            if (vt2) {
                var lastM5 = volMA5.length > 0 ? volMA5[volMA5.length - 1].value : null;
                var lastM10 = volMA10.length > 0 ? volMA10[volMA10.length - 1].value : null;
                vt2.innerHTML = '<span style="color:#ddd;">量:--</span> <span style="color:#fbbf24;">M5:'+_fmtMinuteVol(lastM5)+'</span> <span style="color:#60a5fa;">M10:'+_fmtMinuteVol(lastM10)+'</span> <span style="color:#ddd;">额:--</span>';
            }
            var mt2 = document.getElementById('mnMacdTip');
            if (mt2) mt2.innerHTML = '<span style="color:'+(macd.macd[macd.macd.length-1].value>=0?'#ef5350':'#26a69a')+';">MACD:'+macd.macd[macd.macd.length-1].value.toFixed(3)+'</span> <span style="color:#ffffff;">DIFF:'+macd.dif[macd.dif.length-1].value.toFixed(3)+'</span> <span style="color:#fbbf24;">DEA:'+macd.dea[macd.dea.length-1].value.toFixed(3)+'</span>';
        }

        mainChart.subscribeCrosshairMove(function(param) {
            if (!param.time || !param.point) { _updateMinuteTips(null); return; }
            _updateMinuteTips(param.time, param.point);
        });

        // 初始指标栏
        _resetMinuteTips();

        // 底部统计
        var lastP = prices[prices.length - 1], lastAvgV = null;
        for (var ai = avgData.length - 1; ai >= 0; ai--) { if (avgData[ai].value != null) { lastAvgV = avgData[ai].value; break; } }
        var lChg = preClose ? lastP - preClose : 0, lChgPct = preClose ? lChg / preClose * 100 : 0;
        var ls = lChg >= 0 ? '+' : '', lc = lChg >= 0 ? '#ef5350' : '#26a69a';
        var mv = document.getElementById('klMinuteVals');
        if (mv) mv.innerHTML = '<span style="color:#fbbf24;">均价:'+(preClose ? (lastAvgV*preClose/100+preClose).toFixed(priceDec):'--')+'</span> <span style="color:#3b82f6;">最新:'+lastP.toFixed(priceDec)+'</span> <span style="color:'+lc+';">'+ls+lChg.toFixed(priceDec)+'</span> <span style="color:'+lc+';">'+ls+lChgPct.toFixed(2)+'%</span>';

        // ---- 固定时间轴范围：全时段隐形线撑开 fitContent，折线只在已有数据区域绘制 ----
        // 主图：全时段隐形线
        var _fullRangeData = [];
        for (var _i = 0; _i < allT.length; _i++) _fullRangeData.push({ time: allT[_i], value: 0 });
        mainChart.addLineSeries({ lineWidth: 1, color: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(_fullRangeData);
        // 成交量图：全时段隐形线
        volChart.addLineSeries({ lineWidth: 1, color: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(_fullRangeData);
        // MACD 图：全时段隐形线
        macdChart.addLineSeries({ lineWidth: 1, color: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false })
            .setData(_fullRangeData);

        var canvases = [mainCanvas, volCanvas, macdCanvas];
        var charts = [mainChart, volChart, macdChart];
        mainChart.timeScale().fitContent();
        allCharts.forEach(function(c) {
            c.timeScale().applyOptions({ fixLeftEdge: true, fixRightEdge: true });
        });
        var observer = new ResizeObserver(function() {
            for (var i = 0; i < canvases.length; i++) {
                if (charts[i] && canvases[i].clientWidth > 0) {
                    charts[i].applyOptions({ width: canvases[i].clientWidth, height: canvases[i].clientHeight });
                }
            }
        });
        canvases.forEach(function(c) { observer.observe(c); });

        // ---- updateData：定时刷新后更新所有闭包变量，确保游标能命中新数据点 ----
        function updateData(newTimes, newPrices, newVolumes, newAmounts, newPreClose) {
            // 重算 allT / allP / allV / allA
            var isUS2 = stockMarket === '106', isHK2 = stockMarket === '116';
            var today2 = new Date(); var base2 = new Date(today2.getFullYear(), today2.getMonth(), today2.getDate()).getTime() / 1000;
            var rawTs = newTimes.map(function(t) {
                if (isUS2) return new Date(t).getTime() / 1000;
                var pp = t.split(':'); return base2 + parseInt(pp[0]) * 3600 + parseInt(pp[1]) * 60;
            });
            var pcts2 = newPrices.map(function(p) { return newPreClose ? ((p - newPreClose) / newPreClose * 100) : p; });

            var newAllT = [], newAllP = [], newAllV = [], newAllA = [], di2 = 0;
            for (var t2 = minuteFrom; t2 <= minuteTo; t2 += 60) {
                if (!isUS2 && ((!isHK2 && t2 >= lunchAStart && t2 <= lunchAEnd) || (isHK2 && t2 >= lunchHKStart && t2 <= lunchHKEnd))) continue;
                newAllT.push(t2);
                if (di2 < rawTs.length && rawTs[di2] >= t2 - 30 && rawTs[di2] <= t2 + 30) {
                    newAllP.push(pcts2[di2] != null ? pcts2[di2] : null);
                    newAllV.push(newVolumes[di2] != null ? newVolumes[di2] : 0);
                    newAllA.push(newAmounts[di2] != null ? newAmounts[di2] : 0);
                    di2++;
                } else { newAllP.push(null); newAllV.push(null); newAllA.push(null); }
            }
            // 更新闭包引用
            allT = newAllT; allP = newAllP; allV = newAllV; allA = newAllA;
            prices = newPrices; volumes = newVolumes; amounts = newAmounts; preClose = newPreClose;

            // 更新 lineData（十字线同步用）
            lineData = [];
            var lvi2 = -1;
            for (var vi3 = allP.length - 1; vi3 >= 0; vi3--) { if (allP[vi3] != null) { lvi2 = vi3; break; } }
            for (var ii = 0; ii <= lvi2; ii++) lineData.push({ time: allT[ii], value: allP[ii] });

            // 更新 vd（十字线同步用）
            vd = [];
            for (var ii2 = 0; ii2 < allT.length; ii2++) {
                if (allP[ii2] == null) continue;
                var up = (ii2 > 0 && allP[ii2] != null && allP[ii2-1] != null) ? allP[ii2] >= allP[ii2-1] : true;
                vd.push({ time: allT[ii2], value: allV[ii2], color: up ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' });
            }

            // 更新 avgData
            avgData = []; var as2 = 0, an2 = 0;
            for (var ii3 = 0; ii3 <= lvi2; ii3++) {
                if (allP[ii3] != null) { as2 += prices[Math.min(an2, prices.length - 1)]; an2++; }
                avgData.push({ time: allT[ii3], value: allP[ii3] != null ? (an2 > 0 ? (preClose ? ((as2 / an2 - preClose) / preClose * 100) : (as2 / an2)) : null) : null });
            }

            // 更新 volMA5 / volMA10
            var vd2 = [];
            for (var ii4 = 0; ii4 < allT.length; ii4++) { if (allV[ii4] != null) vd2.push({ time: allT[ii4], close: allV[ii4] }); }
            volMA5 = KlineChartUtils.calcSMA(vd2, 5);
            volMA10 = KlineChartUtils.calcSMA(vd2, 10);

            // 更新 macd
            var mi = _buildMacdInput(allT, allP, prices);
            macd = KlineChartUtils.calcMACD(mi, 12, 26, 9);

            // 更新底部统计
            var lp2 = prices[prices.length - 1], lav2 = null;
            for (var ai2 = avgData.length - 1; ai2 >= 0; ai2--) { if (avgData[ai2].value != null) { lav2 = avgData[ai2].value; break; } }
            var lChg2 = preClose ? lp2 - preClose : 0, lChgPct2 = preClose ? lChg2 / preClose * 100 : 0;
            var ls2 = lChg2 >= 0 ? '+' : '', lc2 = lChg2 >= 0 ? '#ef5350' : '#26a69a';
            var mv2 = document.getElementById('klMinuteVals');
            if (mv2) mv2.innerHTML = '<span style="color:#fbbf24;">均价:'+(preClose ? (lav2*preClose/100+preClose).toFixed(priceDec):'--')+'</span> <span style="color:#3b82f6;">最新:'+lp2.toFixed(priceDec)+'</span> <span style="color:'+lc2+';">'+ls2+lChg2.toFixed(priceDec)+'</span> <span style="color:'+lc2+';">'+ls2+lChgPct2.toFixed(2)+'%</span>';
        }

        return {
            chart: mainChart, charts: charts,
            series: series, avgLine: avgLine, volSeries: volSeries,
            macdLines: [{ s: macdHist, k: 'macd' }, { s: difLine, k: 'dif' }, { s: deaLine, k: 'dea' }],
            macd: macd,
            minuteFrom: minuteFrom, minuteTo: minuteTo,
            allT: allT, allP: allP, allV: allV, allA: allA,
            avgData: avgData, preClose: preClose,
            observer: observer,
            _buildMacdInput: _buildMacdInput,
            priceDec: priceDec,
            updateData: updateData,
        };
    }
};
