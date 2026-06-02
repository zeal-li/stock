// ==================== 通用 K 线弹窗 ====================
// 使用：KlinePopup.open(code, market, name)
//       弹窗内部自己请求行情和K线数据

var KlinePopup = (function() {
    var _chart = null, _overlay = null, _series = null, _volSeries = null;
    var _observer = null;
    var _klinesData = null;
    var _stockCode = '';

    // ---- 创建弹窗 DOM ----
    function _ensureDOM() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.id = 'klineOverlay';
        _overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:100;justify-content:center;align-items:center;';
        _overlay.onclick = function(e) { if (e.target === _overlay) close(); };

        _overlay.innerHTML =
            '<div style="width:1160px;max-width:98vw;height:620px;max-height:88vh;background:#1e1e2e;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,0.5);">' +
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
                '<div id="klChart" style="flex:1;min-height:0;position:relative;overflow:hidden;">' +
                    '<div id="klTooltip" style="display:none;position:absolute;z-index:10;pointer-events:none;background:rgba(26,26,46,0.95);border:1px solid #2a2a4e;border-radius:6px;padding:8px 10px;font-size:12px;line-height:1.7;color:#ccc;white-space:nowrap;box-shadow:0 4px 12px rgba(0,0,0,0.4);"></div>' +
                '</div>' +
            '</div>';
        document.body.appendChild(_overlay);
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
                return;
            }
            try { _renderChart(kdata.data); }
            catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
        });
    }

    function close() {
        if (_observer) { _observer.disconnect(); _observer = null; }
        if (_chart) { _chart.remove(); _chart = null; _series = null; _volSeries = null; }
        if (_overlay) _overlay.style.display = 'none';
        _klinesData = null;
    }

    return { open: open, close: close };
})();
