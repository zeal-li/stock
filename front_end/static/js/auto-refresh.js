// ==================== 自动刷新 ====================

// 自动刷新：开盘期间每10秒更新实时数据
function isInTradingHours() {
    const now = new Date();
    const day = now.getDay(); // 0=周日, 6=周六
    // 周六日不开市
    if (day === 0 || day === 6) return false;
    const t = now.getHours() * 60 + now.getMinutes();
    return (t >= 540 && t <= 700) || (t >= 770 && t <= 930);
    // 09:00-11:40, 12:50-15:30
}

var _lastMinuteRefresh = 0;  // 上次分时/资金流刷新的时间戳（ms）
var _lastMarginDate = '';     // 上次融资融券刷新的日期

async function refreshRealtimeData() {
    if (!isInTradingHours()) return;

    var onMoneyFlow = currentNavPage === 'money-flow';

    try {
        // ---- 资金流向页：刷新图表 & 恐慌/风险指数 ----
        if (onMoneyFlow) {
            const idxRes = await fetch('/api/major-indices');
            const idxData = await idxRes.json();
            if (idxData.success && idxData.data.length > 0) {
                // 上证
                const d = idxData.data[0];
                const isUp = d.change.startsWith('+');
                const color = isUp ? '#e94560' : '#4ade80';
                const priceEl = document.querySelector('.index-sh-price');
                const changeEl = document.querySelector('.index-sh-change');
                if (priceEl) { priceEl.textContent = d.price; priceEl.style.color = color; }
                if (changeEl) { changeEl.textContent = d.change + ' ' + d.change_value; changeEl.className = 'index-change ' + (isUp ? 'up' : 'down'); }
                // 深证
                if (idxData.data.length > 1) {
                    const d2 = idxData.data[1];
                    const isUp2 = d2.change.startsWith('+');
                    const color2 = isUp2 ? '#e94560' : '#4ade80';
                    const priceEl2 = document.querySelector('.index-sz-price');
                    const changeEl2 = document.querySelector('.index-sz-change');
                    if (priceEl2) { priceEl2.textContent = d2.price; priceEl2.style.color = color2; }
                    if (changeEl2) { changeEl2.textContent = d2.change + ' ' + d2.change_value; changeEl2.className = 'index-change ' + (isUp2 ? 'up' : 'down'); }
                }
            }
            }

            var _doMinuteRefresh = Date.now() - _lastMinuteRefresh >= 60000;
            if (_doMinuteRefresh) {
            const minRes = await fetch('/api/sh000001-minute');
            const minData = await minRes.json();
            if (minuteChart && minData.success && minData.data.times && fullMinuteSlots.length > 0) {
                minuteChart.data.datasets[0].data = mapAndFill(fullMinuteSlots, minData.data.times, minData.data.prices);
                minuteChart.data.datasets[1].data = Array(fullMinuteSlots.length).fill(minData.data.preClose);
                const mPreClose = minData.data.preClose || 0;
                let mMaxDev = 0;
                minData.data.prices.forEach(p => { const d = Math.abs(p - mPreClose); if (d > mMaxDev) mMaxDev = d; });
                mMaxDev = Math.max(mMaxDev * 1.15, mPreClose * 0.005);
                minuteChart.options.scales.y.min = mPreClose - mMaxDev;
                minuteChart.options.scales.y.max = mPreClose + mMaxDev;
                const isUp2 = parseFloat(minData.data.change) >= 0;
                const lc = isUp2 ? '#e94560' : '#4ade80';
                minuteChart.data.datasets[0].borderColor = lc;
                minuteChart.data.datasets[0].backgroundColor = (ctx => { const g = ctx.chart.ctx.createLinearGradient(0,0,0,180); g.addColorStop(0, isUp2 ? 'rgba(233,69,96,0.2)' : 'rgba(74,222,128,0.2)'); g.addColorStop(1, 'rgba(26,26,46,0)'); return g; });
                minuteChart.update('none');
            }
            }

            if (_doMinuteRefresh) {
            const turnoverRes = await fetch('/api/turnover-minute');
            const turnoverData = await turnoverRes.json();
            if (turnoverData.success && turnoverData.data.header && turnoverData.data.header.turnover) {
                const th = turnoverData.data.header;
                const tChange = th.turnover_change / 100000000;
                const elToday = document.getElementById('todayTurnover');
                const elYesterday = document.getElementById('yesterdayTurnover');
                const elChange = document.getElementById('turnoverChange');
                if (elToday) elToday.textContent = (th.turnover / 100000000).toFixed(2) + '亿';
                if (elYesterday) elYesterday.textContent = (th.turnover_pre / 100000000).toFixed(2) + '亿';
                if (elChange) {
                    const tPct = th.turnover_pre ? (tChange / (th.turnover_pre / 100000000) * 100) : 0;
                    elChange.textContent = (tChange >= 0 ? '+' : '') + tChange.toFixed(2) + '亿 (' + (tPct >= 0 ? '+' : '') + tPct.toFixed(1) + '%)';
                    elChange.style.color = tChange >= 0 ? '#e94560' : '#4ade80';
                }
            }
            }

            if (_doMinuteRefresh) {
            const flowRes = await fetch('/api/market-fund-flow');
            const flowData = await flowRes.json();
            if (turnoverChart && flowData.success && flowData.data.times && fullFlowSlots.length > 0) {
                const flows = flowData.data.flows;
                const flowsMid = flowData.data.flows_mid || [];
                const flowsSmall = flowData.data.flows_small || [];
                turnoverChart.data.datasets[0].data = mapAndFill(fullFlowSlots, flowData.data.times, flows);
                turnoverChart.data.datasets[1].data = mapAndFill(fullFlowSlots, flowData.data.times, flowsMid);
                turnoverChart.data.datasets[2].data = mapAndFill(fullFlowSlots, flowData.data.times, flowsSmall);
                turnoverChart.data.datasets[3].data = Array(fullFlowSlots.length).fill(0);
                var _fm = function(arr) { var f = arr.filter(function(v) { return v != null; }); return f.length > 0 ? Math.max.apply(null, f) : 0; };
                var _fn = function(arr) { var f = arr.filter(function(v) { return v != null; }); return f.length > 0 ? Math.min.apply(null, f) : 0; };
                var maxAbs = Math.max(Math.abs(_fm(flows)), Math.abs(_fn(flows)), Math.abs(_fm(flowsMid)), Math.abs(_fn(flowsMid)), Math.abs(_fm(flowsSmall)), Math.abs(_fn(flowsSmall)), 1);
                turnoverChart.options.scales.y.min = -maxAbs;
                turnoverChart.options.scales.y.max = maxAbs;
                turnoverChart.update('none');
                const totalFlow = flows.length > 0 ? flows[flows.length - 1] : 0;
                const elFlow = document.getElementById('netFlowValue');
                if (elFlow) {
                    elFlow.textContent = (totalFlow >= 0 ? '+' : '') + totalFlow.toFixed(2) + '亿';
                    elFlow.style.color = totalFlow >= 0 ? '#e94560' : '#4ade80';
                }
            }
            }
            if (_doMinuteRefresh) _lastMinuteRefresh = Date.now();

            // 融资融券：每天刷新一次
            var _todayStr = new Date().toISOString().slice(0, 10);
            if (_todayStr !== _lastMarginDate) {
                _lastMarginDate = _todayStr;
                const marginRes = await fetch('/api/margin-trading');
                const marginData = await marginRes.json();
                if (marginChart && marginData.success && marginData.data.dates) {
                    marginChart.data.labels = marginData.data.dates;
                    marginChart.data.datasets[0].data = marginData.data.total_balances;
                    marginChart.data.datasets[1].data = marginData.data.rz_balances;
                    marginChart.data.datasets[2].data = marginData.data.rq_balances;
                    marginChart.data.datasets[3].data = marginData.data.buy_amounts;
                    marginChart.update('none');
                }
            }

            if (_doMinuteRefresh) {
            const fearRes = await fetch('/api/fear-index');
            const fearData = await fearRes.json();
            if (fearData.success && fearData.data) {
                const fd = fearData.data;
                var el = document.getElementById('fearScore');
                if (el) { el.textContent = fd.score; el.style.color = fd.color; }
                el = document.getElementById('fearLevel');
                if (el) { el.textContent = fd.level; el.style.color = fd.color; }
                el = document.getElementById('fearPointer');
                if (el) el.style.left = fd.score + '%';
                el = document.getElementById('fearConclusion');
                if (el) el.textContent = getFearSummary(fd.score);
                _setText('fear-avg-change', fd.avg_index_change, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                _setText('fear-max-drop', fd.max_30m_drop, v => v.toFixed(2) + '%');
                _setText('fear-max-dd', fd.max_drawdown, v => v.toFixed(2) + '%');
                _setText('fear-amplitude', fd.amplitude, v => v.toFixed(2) + '%');
                _setText('fear-red-ratio', fd.red_ratio, v => v.toFixed(1) + '%');
                _setText('fear-down-ratio', fd.down_ratio, v => v.toFixed(1) + '%');
                _setText('fear-main-net', fd.main_net, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '亿');
                _setText('fear-rebound', fd.rebound, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                const bDiv = document.getElementById('marketBreadth');
                if (bDiv) bDiv.innerHTML = `涨<span style="color:#e94560;">${fd.rise}</span> 跌<span style="color:#4ade80;">${fd.fall}</span> 平<span style="color:#888;">${fd.flat}</span>`;
            }
            }  // _doMinuteRefresh

            if (_doMinuteRefresh) {
            const riskRes = await fetch('/api/risk-index');
            const riskData = await riskRes.json();
            if (riskData.success && riskData.data) {
                const rd = riskData.data;
                var el = document.getElementById('riskScore');
                if (el) { el.textContent = rd.score; el.style.color = rd.color; }
                el = document.getElementById('riskLevel');
                if (el) { el.textContent = rd.level; el.style.color = rd.color; }
                el = document.getElementById('riskPointer');
                if (el) el.style.left = rd.score + '%';
                el = document.getElementById('riskConclusion');
                if (el) el.textContent = getRiskSummary(rd.score);
                _setText('risk-fin-bal-5d', rd.fin_bal_5d, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                _setText('risk-fin-bal-10d', rd.fin_bal_10d, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                _setText('risk-fin-buy-heat', rd.fin_buy_heat, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                _setText('risk-idx-5d', rd.idx_5d, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                _setText('risk-idx-10d', rd.idx_10d, v => (v >= 0 ? '+' : '') + v.toFixed(2) + '%');
                _setText('risk-idx-20d-dd', rd.idx_20d_dd, v => v.toFixed(2) + '%');
                _setText('risk-volatility', rd.volatility, v => v.toFixed(2) + '%');
                _setText('risk-panic-score', rd.panic_score_in, v => v.toFixed(1) + '分');
                _setText('risk-limit-score', rd.limit_score_in, v => v.toFixed(1) + '分');
            }
            }  // _doMinuteRefresh
        }
    } catch(e) { console.log('Auto refresh error:', e); }

    // ---- 始终刷新：选股列表行情 ----
    refreshPickedQuotes();
}

// 工具：按 id 更新文本，值为 null 时显示 '--'
function _setText(id, value, fmt) {
    var el = document.getElementById(id);
    if (el) el.textContent = (value != null) ? fmt(value) : '--';
}
