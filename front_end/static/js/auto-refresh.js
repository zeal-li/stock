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

async function refreshRealtimeData() {
    if (!isInTradingHours()) return;
    try {
        // 更新上证指数价格
        const idxRes = await fetch('/api/major-indices');
        const idxData = await idxRes.json();
        if (idxData.success && idxData.data.length > 0) {
            const d = idxData.data[0];
            const isUp = d.change.startsWith('+');
            const color = isUp ? '#e94560' : '#4ade80';
            const priceEl = document.querySelector('.index-price');
            const changeEl = document.querySelector('.index-change');
            if (priceEl) { priceEl.textContent = d.price; priceEl.style.color = color; }
            if (changeEl) { changeEl.textContent = d.change + ' ' + d.change_value; changeEl.className = 'index-change ' + (isUp ? 'up' : 'down'); }
        }

        // 更新分时走势
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

        // 更新成交额 header (只改文字，不重建 DOM)
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

        // 更新资金流
        const flowRes = await fetch('/api/market-fund-flow');
        const flowData = await flowRes.json();
        if (turnoverChart && flowData.success && flowData.data.times && fullFlowSlots.length > 0) {
            turnoverChart.data.datasets[0].data = mapAndFill(fullFlowSlots, flowData.data.times, flowData.data.flows);
            turnoverChart.data.datasets[1].data = mapAndFill(fullFlowSlots, flowData.data.times, flowData.data.flows_mid || []);
            turnoverChart.data.datasets[2].data = mapAndFill(fullFlowSlots, flowData.data.times, flowData.data.flows_small || []);
            turnoverChart.data.datasets[3].data = Array(fullFlowSlots.length).fill(0);
            turnoverChart.update('none');
            // 更新大盘净流入 (只改文字)
            const flows = flowData.data.flows;
            const totalFlow = flows.length > 0 ? flows[flows.length - 1] : 0;
            const elFlow = document.getElementById('netFlowValue');
            if (elFlow) {
                elFlow.textContent = (totalFlow >= 0 ? '+' : '') + totalFlow.toFixed(2) + '亿';
                elFlow.style.color = totalFlow >= 0 ? '#e94560' : '#4ade80';
            }
        }

        // 更新恐慌/风险指数
        const fearRes = await fetch('/api/fear-index');
        const fearData = await fearRes.json();
        if (fearData.success && fearData.data) {
            const fd = fearData.data;
            const fDiv = document.getElementById('fearIndex');
            if (fDiv) {
                fDiv.querySelector('div:nth-child(1)').textContent = fd.score;
                fDiv.querySelector('div:nth-child(1)').style.color = fd.color;
                fDiv.querySelector('div:nth-child(2)').textContent = fd.level;
                fDiv.querySelector('div:nth-child(2)').style.color = fd.color;
                const ptr = fDiv.querySelector('div[style*="position:absolute"]');
                if (ptr) ptr.style.left = fd.score + '%';
                // 更新总结和指标
                const fConc = document.getElementById('fearConclusion');
                if (fConc) fConc.textContent = getFearSummary(fd.score);
                const fMet = document.getElementById('fearMetrics');
                if (fMet) fMet.innerHTML = '<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.08); font-size:11px; color:#666; line-height:1.7;">' +
                    '<div>沪深指数平均涨跌: <span style="color:#ccc;">' + (fd.avg_index_change != null ? (fd.avg_index_change >= 0 ? '+' : '') + fd.avg_index_change.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>30分钟最大跌速: <span style="color:#ccc;">' + (fd.max_30m_drop != null ? fd.max_30m_drop.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>日内最大回撤: <span style="color:#ccc;">' + (fd.max_drawdown != null ? fd.max_drawdown.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>上证振幅: <span style="color:#ccc;">' + (fd.amplitude != null ? fd.amplitude.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>全A红盘率: <span style="color:#ccc;">' + (fd.red_ratio != null ? fd.red_ratio.toFixed(1) + '%' : '--') + '</span></div>' +
                    '<div>下跌家数占比: <span style="color:#ccc;">' + (fd.down_ratio != null ? fd.down_ratio.toFixed(1) + '%' : '--') + '</span></div>' +
                    '<div>主力资金净流入: <span style="color:#ccc;">' + (fd.main_net != null ? (fd.main_net >= 0 ? '+' : '') + fd.main_net.toFixed(2) + '亿' : '--') + '</span></div>' +
                    '<div>从低点反弹: <span style="color:#ccc;">' + (fd.rebound != null ? (fd.rebound >= 0 ? '+' : '') + fd.rebound.toFixed(2) + '%' : '--') + '</span></div>' +
                    '</div>' + fearExplain;
            }
            // 涨跌数据
            const bDiv = document.getElementById('marketBreadth');
            if (bDiv) bDiv.innerHTML = `涨<span style="color:#e94560;">${fd.rise}</span> 跌<span style="color:#4ade80;">${fd.fall}</span> 平<span style="color:#888;">${fd.flat}</span>`;
        }

        const riskRes = await fetch('/api/risk-index');
        const riskData = await riskRes.json();
        if (riskData.success && riskData.data) {
            const rd = riskData.data;
            const rDiv = document.getElementById('riskIndex');
            if (rDiv && rDiv.children[0]) {
                rDiv.children[0].textContent = rd.score;
                rDiv.children[0].style.color = rd.color;
                if (rDiv.children[1]) { rDiv.children[1].textContent = rd.level; rDiv.children[1].style.color = rd.color; }
                const ptr = rDiv.querySelector('div[style*="position:absolute"]');
                if (ptr) ptr.style.left = rd.score + '%';
                // 更新总结和指标
                const rConc = document.getElementById('riskConclusion');
                if (rConc) rConc.textContent = getRiskSummary(rd.score);
                const rMet = document.getElementById('riskMetrics');
                if (rMet) rMet.innerHTML = '<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.08); font-size:11px; color:#666; line-height:1.7;">' +
                    '<div>融资余额5日变化: <span style="color:#ccc;">' + (rd.fin_bal_5d != null ? (rd.fin_bal_5d >= 0 ? '+' : '') + rd.fin_bal_5d.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>两融余额10日变化: <span style="color:#ccc;">' + (rd.fin_bal_10d != null ? (rd.fin_bal_10d >= 0 ? '+' : '') + rd.fin_bal_10d.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>融资买入活跃度: <span style="color:#ccc;">' + (rd.fin_buy_heat != null ? (rd.fin_buy_heat >= 0 ? '+' : '') + rd.fin_buy_heat.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>沪深5日涨跌: <span style="color:#ccc;">' + (rd.idx_5d != null ? (rd.idx_5d >= 0 ? '+' : '') + rd.idx_5d.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>沪深10日涨跌: <span style="color:#ccc;">' + (rd.idx_10d != null ? (rd.idx_10d >= 0 ? '+' : '') + rd.idx_10d.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>20日最大回撤: <span style="color:#ccc;">' + (rd.idx_20d_dd != null ? rd.idx_20d_dd.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>10日波动率: <span style="color:#ccc;">' + (rd.volatility != null ? rd.volatility.toFixed(2) + '%' : '--') + '</span></div>' +
                    '<div>情绪面因子: <span style="color:#ccc;">' + (rd.panic_score_in != null ? rd.panic_score_in.toFixed(1) + '分' : '--') + '</span></div>' +
                    '<div>涨跌结构因子: <span style="color:#ccc;">' + (rd.limit_score_in != null ? rd.limit_score_in.toFixed(1) + '分' : '--') + '</span></div>' +
                    '</div>' + riskExplain;
            }
        }
    } catch(e) { console.log('Auto refresh error:', e); }
    refreshPickedQuotes();
}
