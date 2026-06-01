// ==================== 通用 K 线弹窗 ====================
// 使用：KlinePopup.open(code, market, name, extra)
//       extra.price / extra.pct / extra.change / extra.pe / extra.pb（可选）

var KlinePopup = (function() {
    var _chart = null, _volChart = null, _overlay = null, _series = null, _volSeries = null;
    var _stockName = '', _stockCode = '';

    function _color(up) { return { up: '#ef5350', down: '#26a69a', borderUp: '#ef5350', borderDown: '#26a69a', wickUp: '#ef5350', wickDown: '#26a69a' }; }

    // ---- 创建弹窗 DOM ----
    function _ensureDOM() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.id = 'klineOverlay';
        _overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:100;justify-content:center;align-items:center;';
        _overlay.onclick = function(e) { if (e.target === _overlay) close(); };

        _overlay.innerHTML =
            '<div style="width:1050px;max-width:96vw;height:650px;max-height:88vh;background:#1e1e2e;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,0.5);">' +
                // 标题栏
                '<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 18px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;">' +
                    '<div style="display:flex;align-items:center;gap:12px;">' +
                        '<span id="klName" style="font-size:18px;color:#fff;font-weight:600;"></span>' +
                        '<span id="klCode" style="font-size:13px;color:#888;"></span>' +
                        '<span id="klPrice" style="font-size:20px;font-weight:bold;"></span>' +
                        '<span id="klPct" style="font-size:13px;"></span>' +
                    '</div>' +
                    '<span style="color:#666;font-size:22px;cursor:pointer;padding:0 8px;line-height:1;" onclick="KlinePopup.close()">✕</span>' +
                '</div>' +
                // 图表区
                '<div id="klChart" style="flex:1;position:relative;overflow:hidden;"></div>' +
            '</div>';
        document.body.appendChild(_overlay);
    }

    function _fmtPct(v) { if (v == null) return ''; var n = parseFloat(v); return (n >= 0 ? '+' : '') + n.toFixed(2) + '%'; }

    // ---- 渲染图表 ----
    function _renderChart(data) {
        var el = document.getElementById('klChart');
        el.innerHTML = '';

        _chart = LightweightCharts.createChart(el, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 0 }, rightPriceScale: { borderColor: '#2a2a4e', scaleMargins: { top: 0.1, bottom: 0.3 } },
            timeScale: { borderColor: '#2a2a4e', timeVisible: false },
            width: el.clientWidth, height: el.clientHeight,
        });

        // 蜡烛图
        var candleData = data.klines.map(function(k) {
            return { time: k.time, open: k.open, high: k.high, low: k.low, close: k.close };
        });
        _series = _chart.addCandlestickSeries({
            upColor: '#ef5350', downColor: '#26a69a',
            borderUpColor: '#ef5350', borderDownColor: '#26a69a',
            wickUpColor: '#ef5350', wickDownColor: '#26a69a',
        });
        _series.setData(candleData);

        // 成交量（独立 priceScale）
        var volData = data.klines.map(function(k) {
            var color = k.close >= k.open ? 'rgba(239,83,80,0.5)' : 'rgba(38,166,154,0.5)';
            return { time: k.time, value: k.volume, color: color };
        });
        _volSeries = _chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });
        _chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.85, bottom: 0 },
            visible: false,
        });
        _volSeries.setData(volData);

        _chart.timeScale().fitContent();
    }

    // ---- 公开方法 ----
    function open(code, market, name, extra) {
        extra = extra || {};
        _stockName = name || code;
        _stockCode = code;

        _ensureDOM();
        document.getElementById('klName').textContent = name || code;
        document.getElementById('klCode').textContent = code;
        var priceEl = document.getElementById('klPrice');
        var pctEl = document.getElementById('klPct');

        if (extra.price && extra.price !== '-') {
            var chg = extra.change || '-', pct = extra.pct || '-';
            var isUp = chg.startsWith('+') || parseFloat(chg) > 0;
            var isDown = chg.startsWith('-') || parseFloat(chg) < 0;
            var clr = isUp ? '#ef5350' : isDown ? '#26a69a' : '#8b8b9e';
            priceEl.textContent = extra.price + (extra.pe ? '  PE:' + extra.pe : '') + (extra.pb ? ' PB:' + extra.pb : '');
            priceEl.style.color = clr;
            pctEl.textContent = chg + ' ' + pct;
            pctEl.style.color = clr;
        } else {
            priceEl.textContent = '';
            pctEl.textContent = '';
        }

        _overlay.style.display = 'flex';
        var chartEl = document.getElementById('klChart');
        chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">加载中...</div>';

        fetch('/api/stock-kline?code=' + encodeURIComponent(code) + '&market=' + encodeURIComponent(market))
            .then(function(r) { return r.json(); })
            .then(function(d) {
                if (!d.success || !d.data.klines || d.data.klines.length === 0) {
                    chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#8b8b9e;font-size:14px;">暂无K线数据</div>';
                    return;
                }
                try {
                    _renderChart(d.data);
                } catch(e) {
                    chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>';
                }
            })
            .catch(function(e) {
                chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败: ' + (e.message || e) + '</div>';
            });
    }

    function close() {
        if (_chart) { _chart.remove(); _chart = null; _series = null; _volSeries = null; }
        if (_overlay) _overlay.style.display = 'none';
    }

    return { open: open, close: close };
})();
