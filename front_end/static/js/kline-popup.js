// ==================== 通用 K 线弹窗 ====================
// 使用：KlinePopup.open(code, market, name, extra)
//       extra.price / extra.pct / extra.change / extra.pe / extra.pb（可选）

var KlinePopup = (function() {
    var _chart = null, _overlay = null, _series = null, _volSeries = null;
    var _observer = null;

    // ---- 创建弹窗 DOM ----
    function _ensureDOM() {
        if (_overlay) return;
        _overlay = document.createElement('div');
        _overlay.id = 'klineOverlay';
        _overlay.style.cssText = 'display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.75);z-index:100;justify-content:center;align-items:center;';
        _overlay.onclick = function(e) { if (e.target === _overlay) close(); };

        _overlay.innerHTML =
            '<div style="width:1050px;max-width:96vw;height:620px;max-height:88vh;background:#1e1e2e;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 8px 40px rgba(0,0,0,0.5);">' +
                // 标题栏：名称 (代码) 价格 涨跌
                '<div style="display:flex;justify-content:space-between;align-items:baseline;padding:10px 16px 6px;background:#1a1a2e;flex-shrink:0;">' +
                    '<div style="display:flex;align-items:baseline;gap:8px;">' +
                        '<span id="klName" style="font-size:17px;color:#fff;font-weight:600;"></span>' +
                        '<span id="klCode" style="font-size:17px;color:#888;"></span>' +
                        '<span id="klPrice" style="font-size:14px;"></span>' +
                        '<span id="klChange" style="font-size:13px;"></span>' +
                    '</div>' +
                    '<span style="color:#666;font-size:20px;cursor:pointer;padding:0 6px;line-height:1;" onclick="KlinePopup.close()">✕</span>' +
                '</div>' +
                // 参数行
                '<div id="klParams" style="padding:6px 16px;background:#1a1a2e;border-bottom:1px solid #2a2a4e;flex-shrink:0;display:flex;flex-wrap:wrap;gap:4px 16px;font-size:11px;color:#8b8b9e;"></div>' +
                // 图表区
                '<div id="klChart" style="flex:1;min-height:0;position:relative;overflow:hidden;"></div>' +
            '</div>';
        document.body.appendChild(_overlay);
    }

    // ---- 渲染图表 ----
    function _renderChart(data) {
        var el = document.getElementById('klChart');
        el.innerHTML = '';

        _chart = LightweightCharts.createChart(el, {
            layout: { background: { color: '#1e1e2e' }, textColor: '#8b8b9e' },
            grid: { vertLines: { color: 'rgba(42,42,78,0.5)' }, horzLines: { color: 'rgba(42,42,78,0.5)' } },
            crosshair: { mode: 0 },
            rightPriceScale: { borderColor: '#2a2a4e', scaleMargins: { top: 0.08, bottom: 0.28 } },
            timeScale: { borderColor: '#2a2a4e', timeVisible: false },
            width: el.clientWidth, height: el.clientHeight,
        });

        // 蜡烛图
        _series = _chart.addCandlestickSeries({
            upColor: '#ef5350', downColor: '#26a69a',
            borderUpColor: '#ef5350', borderDownColor: '#26a69a',
            wickUpColor: '#ef5350', wickDownColor: '#26a69a',
        });
        _series.setData(data.klines.map(function(k) {
            return { time: k.time, open: k.open, high: k.high, low: k.low, close: k.close };
        }));

        // 成交量
        _volSeries = _chart.addHistogramSeries({
            priceFormat: { type: 'volume' }, priceScaleId: 'volume',
        });
        _chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.83, bottom: 0 }, visible: false });
        _volSeries.setData(data.klines.map(function(k) {
            return { time: k.time, value: k.volume, color: k.close >= k.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)' };
        }));

        _chart.timeScale().fitContent();

        // ---- 窗口自适应 ----
        if (_observer) _observer.disconnect();
        _observer = new ResizeObserver(function() {
            if (_chart && el.clientWidth > 0) {
                _chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
            }
        });
        _observer.observe(el);
    }

    // ---- 公开方法 ----
    function open(code, market, name, extra) {
        extra = extra || {};

        _ensureDOM();
        document.getElementById('klName').textContent = (name || code);
        document.getElementById('klCode').textContent = '(' + code + ')';

        // 标题行：价格 + 涨跌
        var priceEl = document.getElementById('klPrice');
        var chgEl = document.getElementById('klChange');
        var chgColor = '#8b8b9e';
        if (extra.price && extra.price !== '-') {
            var chg = extra.change || '-', pct = extra.pct || '-';
            var isUp = chg.startsWith('+') || parseFloat(chg) > 0;
            var isDown = chg.startsWith('-') || parseFloat(chg) < 0;
            chgColor = isUp ? '#ef5350' : isDown ? '#26a69a' : '#8b8b9e';
            priceEl.textContent = extra.price;
            priceEl.style.color = chgColor;
            chgEl.textContent = chg + '  ' + pct;
            chgEl.style.color = chgColor;
        } else {
            priceEl.textContent = '';
            chgEl.textContent = '';
        }

        // 参数行
        var params = [];
        function add(label, val) { if (val && val !== '-') params.push(label + ': ' + val); }
        add('总市值', extra.total_cap);
        add('流通市值', extra.float_cap);
        add('市盈(TTM)', extra.pe);
        add('市净率', extra.pb);
        add('成交量', extra.volume);
        add('成交额', extra.amount);
        add('换手', extra.turnover);
        add('振幅', extra.amplitude);
        document.getElementById('klParams').innerHTML = params.map(function(p) {
            return '<span style="white-space:nowrap;">' + p + '</span>';
        }).join('<span style="color:#2a2a4e;">|</span>');

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
                try { _renderChart(d.data); }
                catch(e) { chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">渲染失败: ' + (e.message || e) + '</div>'; }
            })
            .catch(function(e) {
                chartEl.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef5350;font-size:13px;">请求失败: ' + (e.message || e) + '</div>';
            });
    }

    function close() {
        if (_observer) { _observer.disconnect(); _observer = null; }
        if (_chart) { _chart.remove(); _chart = null; _series = null; _volSeries = null; }
        if (_overlay) _overlay.style.display = 'none';
    }

    return { open: open, close: close };
})();
