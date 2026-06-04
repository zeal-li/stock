// ==================== 图表 & 资金流向 ====================

// 股票类型判断（公共）
function getStockType(code, market) {
    const c = (code || '').toString();
    const m = (market || '').toString();
    if (m === '1' || m === '2') {
        if (/^68/.test(c)) return '科创';
        if (/^60|^900/.test(c)) return '沪A';
        if (/^51[0-9]/.test(c)) return '沪ETF';
        if (/^5[0-9]/.test(c)) return '沪基';
        if (/^11/.test(c)) return '沪债';
        return '沪市';
    }
    if (m === '0') {
        if (/^30[04]/.test(c)) return '创业';
        if (/^00[024]|^002|^003/.test(c)) return '深A';
        if (/^15[0-9]/.test(c)) return '深ETF';
        if (/^1[0-9]/.test(c)) return '深基';
        if (/^12/.test(c)) return '深债';
        return '深市';
    }
    if (m === '90') return '北交所';
    if (m === '116') return '港股';
    if (m === '106') return '美股';
    if (/^1[0-5]/.test(m) && parseInt(m) >= 105) return '境外';
    return '';
}

function generateFlowSlots() {
    const slots = [];
    for (let h = 9, m = 30; h < 12; ) {
        slots.push(String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0'));
        m++;
        if (m >= 60) { h++; m -= 60; }
        if (h === 11 && m > 30) break;
    }
    for (let h = 13, m = 0; h < 15 || (h === 15 && m === 0); ) {
        slots.push(String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0'));
        m++;
        if (m >= 60) { h++; m -= 60; }
        if (h === 15 && m > 0) break;
    }
    return slots;
}

function mapToSlots(fullSlots, dataTimes, dataValues) {
    const result = new Array(fullSlots.length).fill(null);
    const indexMap = {};
    for (let i = 0; i < fullSlots.length; i++) {
        indexMap[fullSlots[i]] = i;
    }
    for (let i = 0; i < dataTimes.length; i++) {
        const idx = indexMap[dataTimes[i]];
        if (idx !== undefined && idx >= 0) {
            result[idx] = dataValues[i];
        }
    }
    return result;
}

// 同 mapToSlots，但 13:00 若无数据则用 11:30 的值填充，避免午休折线断开
function mapAndFill(fullSlots, dataTimes, dataValues) {
    const result = mapToSlots(fullSlots, dataTimes, dataValues);
    const idx13 = fullSlots.indexOf('13:00');
    if (idx13 > 0 && result[idx13] === null) {
        for (let i = idx13 - 1; i >= 0; i--) {
            if (result[i] !== null) {
                result[idx13] = result[i];
                break;
            }
        }
    }
    return result;
}

function getFearSummary(score) {
    if (score <= 30) return '市场情绪平稳，无明显恐慌信号。';
    if (score <= 50) return '市场出现轻度恐慌，需关注后续走势。';
    if (score <= 65) return '恐慌情绪明显，短线抛压加大。';
    if (score <= 80) return '市场高度恐慌，资金避险情绪浓厚。';
    return '市场极度恐慌，可能出现非理性抛售。';
}

function getRiskSummary(score) {
    if (score <= 20) return '市场低风险区间，可适当积极布局。';
    if (score <= 40) return '市场风险较低，注意仓位管理。';
    if (score <= 60) return '市场中等风险，建议控制仓位、择优参与。';
    if (score <= 80) return '市场风险较高，建议谨慎操作。';
    return '市场高风险，建议降低仓位、规避风险。';
}

function formatTurnover(value) {
    if (value >= 10000) {
        return (value / 10000).toFixed(2) + '万亿';
    }
    return value.toFixed(2) + '亿';
}

async function loadIndexWithChart() {
    const indexCard = document.getElementById('index-card');
    indexCard.innerHTML = '<div class="loading">正在加载上证指数...</div>';

    try {
        const indexRes = await fetch('/api/major-indices');
        const indexResult = await indexRes.json();

        let indexData = null, indexDataSZ = null;
        if (indexResult.success && indexResult.data.length > 0) {
            indexData = indexResult.data[0];
            if (indexResult.data.length > 1) indexDataSZ = indexResult.data[1];
        }

        if (!indexData) {
            indexCard.innerHTML = '<div class="error">暂无指数数据</div>';
            return;
        }

        const isUp = indexData.change.startsWith('+');
        const changeClass = isUp ? 'up' : 'down';
        const lineColor = isUp ? '#e94560' : '#4ade80';
        const gradientColor = isUp ? 'rgba(233, 69, 96, 0.2)' : 'rgba(74, 222, 128, 0.2)';

        // 深证
        var szName = indexDataSZ ? '深证' : '';
        var szIsUp = indexDataSZ && indexDataSZ.change.startsWith('+');
        var szColor = szIsUp ? '#e94560' : '#4ade80';
        var szChangeClass = szIsUp ? 'up' : 'down';

        indexCard.innerHTML = `
                <div class="index-header">
                    <div class="index-info">
                        <span class="index-name">上证</span>
                        <span class="index-price index-sh-price" style="color: ${lineColor};">${indexData.price}</span>
                        <span class="index-change index-sh-change ${changeClass}">${indexData.change} ${indexData.change_value}</span>
                        ` + (indexDataSZ ? `
                        <span class="index-name">${szName}</span>
                        <span class="index-price index-sz-price" style="color: ${szColor};">${indexDataSZ.price}</span>
                        <span class="index-change index-sz-change ${szChangeClass}">${indexDataSZ.change} ${indexDataSZ.change_value}</span>
                        ` : '') + `
                        <span id="marketBreadth" style="font-size: 12px; color: #888;"></span>
                    </div>
                </div>
                <div style="display: flex; gap: 15px; font-size: 13px; color: #888; margin-bottom: 6px;">
                    <span id="headerTurnover">加载中...</span>
                    <span id="headerFlow"></span>
                </div>
                <div style="display: flex; gap: 15px;">
                    <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px;">
                        <div class="chart-box" style="position:relative;">
                            <canvas id="minuteChart"></canvas>
                            <div id="minuteLoading" style="position:absolute;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;color:#888;font-size:14px;pointer-events:none;">加载中...</div>
                            <div class="chart-title">分时走势</div>
                        </div>
                        <div class="chart-box">
                            <canvas id="turnoverChart"></canvas>
                            <div class="chart-title">大盘净资金流入</div>
                        </div>
                        <div class="chart-box">
                            <canvas id="marginChart"></canvas>
                            <div class="chart-title">融资融券</div>
                        </div>
                    </div>
                    <div style="width: 220px; min-width: 220px; display: flex; flex-direction: column;">
                        <div class="index-card" style="height: 100%; padding: 18px; display: flex; flex-direction: column;">
                            <div class="chart-title" style="margin-bottom: 12px;">市场风险指数</div>
                            <div id="riskIndex" style="display: flex; flex-direction: column; align-items: center; flex: 1;">
                                <div class="loading">加载中...</div>
                            </div>
                        </div>
                    </div>
                    <div style="width: 220px; min-width: 220px; display: flex; flex-direction: column;">
                        <div class="index-card" style="height: 100%; padding: 18px; display: flex; flex-direction: column;">
                            <div class="chart-title" style="margin-bottom: 12px;">市场恐慌指数</div>
                            <div id="fearIndex" style="display: flex; flex-direction: column; align-items: center; flex: 1;">
                                <div class="loading">加载中...</div>
                            </div>
                        </div>
                    </div>
                </div>
            `;

        // 成交额 header（独立容器，互不覆盖）
        fetch('/api/turnover-minute')
            .then(res => res.json())
            .then(turnoverResult => {
                var el = document.getElementById('headerTurnover');
                if (!el) return;
                if (turnoverResult.success && turnoverResult.data.header && turnoverResult.data.header.turnover) {
                    var th = turnoverResult.data.header;
                    var todayT = th.turnover / 100000000;
                    var yesterdayT = th.turnover_pre / 100000000;
                    var chg = th.turnover_change / 100000000;
                    var chgPct = yesterdayT ? (chg / yesterdayT * 100) : 0;
                    el.innerHTML = '<span>当日成交额: <span id="todayTurnover" style="color:#fff;">' + todayT.toFixed(2) + '亿</span></span> ' +
                        '<span>昨日成交额: <span id="yesterdayTurnover" style="color:#fff;">' + yesterdayT.toFixed(2) + '亿</span></span> ' +
                        '<span>较昨日变动: <span id="turnoverChange" style="color:' + (chg >= 0 ? '#e94560' : '#4ade80') + ';">' + (chg >= 0 ? '+' : '') + chg.toFixed(2) + '亿 (' + (chgPct >= 0 ? '+' : '') + chgPct.toFixed(1) + '%)</span></span>';
                } else {
                    el.textContent = '暂无成交额数据';
                }
            })
            .catch(err => console.log('成交额数据加载失败:', err));

        // 资金流 header + 图表（独立容器，互不覆盖）
        fetch('/api/market-fund-flow')
            .then(res => res.json())
            .then(flowResult => {
                var flowTimes = [];
                var flows = [];
                var flowsMid = [];
                var flowsSmall = [];
                var totalFlow = 0;

                if (flowResult.success && flowResult.data.times) {
                    fullFlowSlots = generateFlowSlots();
                    flowTimes = fullFlowSlots;
                    flows = mapAndFill(fullFlowSlots, flowResult.data.times, flowResult.data.flows);
                    flowsMid = mapAndFill(fullFlowSlots, flowResult.data.times, flowResult.data.flows_mid || []);
                    flowsSmall = mapAndFill(fullFlowSlots, flowResult.data.times, flowResult.data.flows_small || []);
                    totalFlow = flowResult.data.flows.length > 0 ? flowResult.data.flows[flowResult.data.flows.length - 1] : 0;
                }

                var hf = document.getElementById('headerFlow');
                if (hf && flowResult.success) {
                    var flowColor = totalFlow >= 0 ? '#e94560' : '#4ade80';
                    hf.innerHTML = '<span>大盘资金净流入: <span id="netFlowValue" style="color:' + flowColor + ';">' + (totalFlow >= 0 ? '+' : '') + totalFlow.toFixed(2) + '亿</span></span>';
                }

                const ctxTurnover = document.getElementById('turnoverChart').getContext('2d');
            if (turnoverChart) turnoverChart.destroy();

            turnoverChart = new Chart(ctxTurnover, {
                    type: 'line',
                    data: {
                        labels: flowTimes,
                        datasets: [{
                            data: flows,
                            borderColor: '#fbbf24',
                            backgroundColor: function(context) {
                                const chart = context.chart;
                                const ctx = chart.ctx;
                                const gradient = ctx.createLinearGradient(0, 0, 0, 180);
                                gradient.addColorStop(0, 'rgba(233, 69, 96, 0.25)');
                                gradient.addColorStop(0.5, 'rgba(233, 69, 96, 0.05)');
                                gradient.addColorStop(0.5, 'rgba(74, 222, 128, 0.05)');
                                gradient.addColorStop(1, 'rgba(74, 222, 128, 0.25)');
                                return gradient;
                            },
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: true
                        }, {
                            data: flowsMid,
                            borderColor: '#a78bfa',
                            backgroundColor: 'transparent',
                            borderWidth: 1.5,
                            borderDash: [3, 5],
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: false
                        }, {
                            data: flowsSmall,
                            borderColor: '#60a5fa',
                            backgroundColor: 'transparent',
                            borderWidth: 1.5,
                            borderDash: [4, 3],
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: false
                        }, {
                            data: Array(flowTimes.length).fill(0),
                            borderColor: 'rgba(255,255,255,0.3)',
                            borderWidth: 1,
                            borderDash: [4, 4],
                            pointRadius: 0,
                            fill: false
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: { padding: { left: 10, right: 10 } },
                        plugins: {
                            legend: { display: false },
                            tooltip: {
                                mode: 'index', intersect: false,
                                backgroundColor: '#16213e', titleColor: '#fff', bodyColor: '#ddd', borderColor: '#0f3460', borderWidth: 1,
                                callbacks: { label: function(context) { const v = context.raw; if (context.datasetIndex === 3) return ''; const labels = ['大盘资金', '中单', '散户']; return labels[context.datasetIndex] + ': ' + (v >= 0 ? '+' : '') + v.toFixed(2) + '亿'; } }
                            }
                        },
                        scales: {
                            x: { grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888', autoSkip: false, maxRotation: 0, font: { size: 10 }, callback: function(value, index) { const label = this.getLabelForValue(value); if (!label) return ''; if (label === '11:30') return ''; if (label === '09:30' || label === '13:00' || label === '15:00') return label; const parts = label.split(':'); const h = parseInt(parts[0]); const min = parseInt(parts[1]); if (h < 12) return ((min + 30) % 20 === 0) ? label : ''; else return (min % 20 === 0) ? label : ''; } } },
                            y: { grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888', font: { size: 10 }, callback: function(value) { return value.toFixed(2) + '亿'; } }, afterFit: function(scale) { scale.width = 65; } }
                        },
                        interaction: { mode: 'index', intersect: false }
                    }
                });
            // 让 0 刻度在 Y 轴中间，综合主力/中单/散户三条线的范围
            var _fm = function(arr) { var f = arr.filter(function(v) { return v != null; }); return f.length > 0 ? Math.max.apply(null, f) : 0; };
            var _fn = function(arr) { var f = arr.filter(function(v) { return v != null; }); return f.length > 0 ? Math.min.apply(null, f) : 0; };
            var maxAbs = Math.max(
                Math.abs(_fm(flows)), Math.abs(_fn(flows)),
                Math.abs(_fm(flowsMid)), Math.abs(_fn(flowsMid)),
                Math.abs(_fm(flowsSmall)), Math.abs(_fn(flowsSmall)),
                1
            );
            turnoverChart.options.scales.y.min = -maxAbs;
            turnoverChart.options.scales.y.max = maxAbs;
            turnoverChart.update();
            })
            .catch(err => console.log('资金流数据加载失败:', err));

        fetch('/api/margin-trading')
            .then(res => res.json())
            .then(marginResult => {
                const ctxMargin = document.getElementById('marginChart').getContext('2d');
                if (marginChart) marginChart.destroy();

                let marginDates = [];
                let rzBalances = [];
                let rqBalances = [];
                let totalBalances = [];
                let buyAmounts = [];

                if (marginResult.success && marginResult.data.dates) {
                    marginDates = marginResult.data.dates;
                    rzBalances = marginResult.data.rz_balances;
                    rqBalances = marginResult.data.rq_balances;
                    totalBalances = marginResult.data.total_balances;
                    buyAmounts = marginResult.data.buy_amounts;
                }

                marginChart = new Chart(ctxMargin, {
                    type: 'line',
                    data: {
                        labels: marginDates,
                        datasets: [{
                            label: '两融余额',
                            data: totalBalances,
                            borderColor: '#fbbf24',
                            backgroundColor: 'rgba(251,191,36,0.08)',
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: true,
                            yAxisID: 'y'
                        }, {
                            label: '融资余额',
                            data: rzBalances,
                            borderColor: '#e94560',
                            backgroundColor: 'transparent',
                            borderWidth: 2,
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: false,
                            yAxisID: 'y'
                        }, {
                            label: '融券余额',
                            data: rqBalances,
                            borderColor: '#4ade80',
                            backgroundColor: 'transparent',
                            borderWidth: 1.5,
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: false,
                            yAxisID: 'y1'
                        }, {
                            label: '融资买入额',
                            data: buyAmounts,
                            borderColor: '#60a5fa',
                            backgroundColor: 'transparent',
                            borderWidth: 1.5,
                            borderDash: [4, 3],
                            pointRadius: 0,
                            pointHoverRadius: 3,
                            tension: 0.3,
                            fill: false,
                            yAxisID: 'y1'
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        layout: { padding: { left: 10, right: 10 } },
                        plugins: {
                            legend: { display: true, position: 'top', labels: { color: '#888', font: { size: 10 }, boxWidth: 12, padding: 5 } },
                            tooltip: {
                                mode: 'index', intersect: false,
                                backgroundColor: '#16213e', titleColor: '#fff', bodyColor: '#ddd', borderColor: '#0f3460', borderWidth: 1,
                                callbacks: { label: ctx => ctx.dataset.label + ': ' + ctx.raw.toFixed(2) + '亿' }
                            }
                        },
                        scales: {
                            x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888', font: { size: 10 }, maxTicksLimit: 14 } },
                            y: {
                                type: 'linear', position: 'left',
                                grid: { color: 'rgba(255,255,255,0.1)' },
                                ticks: { color: '#e94560', font: { size: 10 }, callback: v => (v / 10000).toFixed(2) + '万亿' },
                                afterFit: function(scale) { scale.width = 65; }
                            },
                            y1: {
                                type: 'linear', position: 'right',
                                grid: { display: false },
                                ticks: { color: '#4ade80', font: { size: 10 }, callback: v => v.toFixed(0) + '亿' },
                                afterFit: function(scale) { scale.width = 50; }
                            }
                        },
                        interaction: { mode: 'index', intersect: false }
                    }
                });
            })
            .catch(err => console.log('融资融券数据加载失败:', err));

        fetch('/api/fear-index')
            .then(res => res.json())
            .then(fearResult => {
                const fearDiv = document.getElementById('fearIndex');
                if (fearResult.success && fearResult.data) {
                    const d = fearResult.data;
                    const breadthDiv = document.getElementById('marketBreadth');
                    if (breadthDiv) {
                        breadthDiv.innerHTML = `涨<span style="color:#e94560;">${d.rise}</span> 跌<span style="color:#4ade80;">${d.fall}</span> 平<span style="color:#888;">${d.flat}</span>`;
                    }
                    const fMetrics = '<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.08); font-size:11px; color:#666; line-height:1.7;">' +
                        '<div>沪深指数平均涨跌: <span id="fear-avg-change" style="color:#ccc;">' + (d.avg_index_change != null ? (d.avg_index_change >= 0 ? '+' : '') + d.avg_index_change.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>30分钟最大跌速: <span id="fear-max-drop" style="color:#ccc;">' + (d.max_30m_drop != null ? d.max_30m_drop.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>日内最大回撤: <span id="fear-max-dd" style="color:#ccc;">' + (d.max_drawdown != null ? d.max_drawdown.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>上证振幅: <span id="fear-amplitude" style="color:#ccc;">' + (d.amplitude != null ? d.amplitude.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>全A红盘率: <span id="fear-red-ratio" style="color:#ccc;">' + (d.red_ratio != null ? d.red_ratio.toFixed(1) + '%' : '--') + '</span></div>' +
                        '<div>下跌家数占比: <span id="fear-down-ratio" style="color:#ccc;">' + (d.down_ratio != null ? d.down_ratio.toFixed(1) + '%' : '--') + '</span></div>' +
                        '<div>主力资金净流入: <span id="fear-main-net" style="color:#ccc;">' + (d.main_net != null ? (d.main_net >= 0 ? '+' : '') + d.main_net.toFixed(2) + '亿' : '--') + '</span></div>' +
                        '<div>从低点反弹: <span id="fear-rebound" style="color:#ccc;">' + (d.rebound != null ? (d.rebound >= 0 ? '+' : '') + d.rebound.toFixed(2) + '%' : '--') + '</span></div>' +
                        '</div>' + fearExplain;
                    fearDiv.innerHTML = `
                        <div id="fearScore" style="font-size:28px; font-weight:bold; color:${d.color}; margin-bottom:5px;">${d.score}</div>
                        <div id="fearLevel" style="font-size:14px; color:${d.color}; margin-bottom:8px;">${d.level}</div>
                        <div style="width:100%; position:relative; margin-bottom:6px;">
                            <div style="width:100%; height:12px; border-radius:6px; background: linear-gradient(to right, #4ade80 0%, #86efac 30%, #fbbf24 50%, #f97316 70%, #e94560 100%);"></div>
                            <div id="fearPointer" style="position:absolute; top:-3px; left:${d.score}%; width:4px; height:18px; background:#fff; border-radius:2px; transform:translateX(-50%); box-shadow:0 0 6px rgba(255,255,255,0.5);"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; width:100%; font-size:10px; color:#666; margin-bottom:10px;">
                            <span>贪婪</span><span>中性</span><span>恐慌</span>
                        </div>
                        <div id="fearConclusion" style="font-size:12px; color:#aaa; margin-bottom:0; line-height:1.5;">${getFearSummary(d.score)}</div>
                        <div id="fearMetrics">${fMetrics}</div>
                    `;
                } else {
                    fearDiv.innerHTML = '<div class="error">暂无数据</div>';
                }
            })
            .catch(err => console.log('恐慌指数加载失败:', err));

        fetch('/api/risk-index')
            .then(res => res.json())
            .then(riskResult => {
                const riskDiv = document.getElementById('riskIndex');
                if (riskResult.success && riskResult.data) {
                    const d = riskResult.data;
                    const rMetrics = '<div style="margin-top:12px; padding-top:10px; border-top:1px solid rgba(255,255,255,0.08); font-size:11px; color:#666; line-height:1.7;">' +
                        '<div>融资余额5日变化: <span id="risk-fin-bal-5d" style="color:#ccc;">' + (d.fin_bal_5d != null ? (d.fin_bal_5d >= 0 ? '+' : '') + d.fin_bal_5d.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>两融余额10日变化: <span id="risk-fin-bal-10d" style="color:#ccc;">' + (d.fin_bal_10d != null ? (d.fin_bal_10d >= 0 ? '+' : '') + d.fin_bal_10d.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>融资买入活跃度: <span id="risk-fin-buy-heat" style="color:#ccc;">' + (d.fin_buy_heat != null ? (d.fin_buy_heat >= 0 ? '+' : '') + d.fin_buy_heat.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>沪深5日涨跌: <span id="risk-idx-5d" style="color:#ccc;">' + (d.idx_5d != null ? (d.idx_5d >= 0 ? '+' : '') + d.idx_5d.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>沪深10日涨跌: <span id="risk-idx-10d" style="color:#ccc;">' + (d.idx_10d != null ? (d.idx_10d >= 0 ? '+' : '') + d.idx_10d.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>20日最大回撤: <span id="risk-idx-20d-dd" style="color:#ccc;">' + (d.idx_20d_dd != null ? d.idx_20d_dd.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>10日波动率: <span id="risk-volatility" style="color:#ccc;">' + (d.volatility != null ? d.volatility.toFixed(2) + '%' : '--') + '</span></div>' +
                        '<div>情绪面因子: <span id="risk-panic-score" style="color:#ccc;">' + (d.panic_score_in != null ? d.panic_score_in.toFixed(1) + '分' : '--') + '</span></div>' +
                        '<div>涨跌结构因子: <span id="risk-limit-score" style="color:#ccc;">' + (d.limit_score_in != null ? d.limit_score_in.toFixed(1) + '分' : '--') + '</span></div>' +
                        '</div>' + riskExplain;
                    riskDiv.innerHTML = `
                        <div id="riskScore" style="font-size:28px; font-weight:bold; color:${d.color}; margin-bottom:5px;">${d.score}</div>
                        <div id="riskLevel" style="font-size:14px; color:${d.color}; margin-bottom:8px;">${d.level}</div>
                        <div style="width:100%; position:relative; margin-bottom:6px;">
                            <div style="width:100%; height:12px; border-radius:6px; background: linear-gradient(to right, #4ade80 0%, #86efac 30%, #fbbf24 50%, #f97316 70%, #e94560 100%);"></div>
                            <div id="riskPointer" style="position:absolute; top:-3px; left:${d.score}%; width:4px; height:18px; background:#fff; border-radius:2px; transform:translateX(-50%); box-shadow:0 0 6px rgba(255,255,255,0.5);"></div>
                        </div>
                        <div style="display:flex; justify-content:space-between; width:100%; font-size:10px; color:#666; margin-bottom:10px;">
                            <span>低风险</span><span>中风险</span><span>高风险</span>
                        </div>
                        <div id="riskConclusion" style="font-size:12px; color:#aaa; margin-bottom:0; line-height:1.5;">${getRiskSummary(d.score)}</div>
                        <div id="riskMetrics">${rMetrics}</div>
                    `;
                } else {
                    riskDiv.innerHTML = '<div class="error">暂无数据</div>';
                }
            })
            .catch(err => console.log('风险指数加载失败:', err));

        fetch('/api/sh000001-minute')
            .then(res => res.json())
            .then(minuteResult => {
                const minuteLoading = document.getElementById('minuteLoading');
                if (minuteResult.success && minuteResult.data.times && minuteResult.data.prices && minuteResult.data.times.length > 0) {
                    fullMinuteSlots = generateFlowSlots();
                    const times = fullMinuteSlots;
                    const prices = mapAndFill(fullMinuteSlots, minuteResult.data.times, minuteResult.data.prices);
                    const preClose = minuteResult.data.preClose || 0;

                    // 以昨收为中线，计算上下范围
                    let maxDev = 0;
                    minuteResult.data.prices.forEach(p => { const d = Math.abs(p - preClose); if (d > maxDev) maxDev = d; });
                    maxDev = Math.max(maxDev * 1.15, preClose * 0.005);
                    const yMin = preClose - maxDev;
                    const yMax = preClose + maxDev;

                    const ctxMinute = document.getElementById('minuteChart').getContext('2d');
                    if (minuteChart) minuteChart.destroy();

                    const gradient = ctxMinute.createLinearGradient(0, 0, 0, 180);
                    gradient.addColorStop(0, gradientColor);
                    gradient.addColorStop(1, 'rgba(26, 26, 46, 0)');

                    minuteChart = new Chart(ctxMinute, {
                        type: 'line',
                        data: {
                            labels: times,
                            datasets: [{
                                data: prices,
                                borderColor: lineColor,
                                backgroundColor: gradient,
                                borderWidth: 2,
                                fill: true,
                                tension: 0.1,
                                pointRadius: 0,
                                pointHoverRadius: 4
                            }, {
                                data: Array(times.length).fill(preClose),
                                borderColor: '#888888',
                                borderWidth: 1,
                                borderDash: [6, 4],
                                pointRadius: 0,
                                pointHoverRadius: 0,
                                fill: false,
                                order: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            layout: { padding: { left: 10, right: 10 } },
                            plugins: {
                                legend: { display: false },
                                tooltip: {
                                    mode: 'index', intersect: false,
                                    callbacks: {
                                        label: function(ctx) {
                                            if (ctx.datasetIndex === 1) return '';
                                            const price = ctx.raw;
                                            const preClose = minuteResult.data.preClose || 0;
                                            const change = price - preClose;
                                            const pct = preClose ? (change / preClose * 100) : 0;
                                            const sign = change >= 0 ? '+' : '';
                                            return [
                                                '指数: ' + price.toFixed(2),
                                                sign + pct.toFixed(2) + '%  ' + sign + change.toFixed(2)
                                            ];
                                        }
                                    }
                                }
                            },
                            scales: {
                                x: { grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888', autoSkip: false, maxRotation: 0, callback: function(value, index) { const label = this.getLabelForValue(value); if (!label) return ''; if (label === '11:30') return ''; if (label === '09:30' || label === '13:00' || label === '15:00') return label; const parts = label.split(':'); const h = parseInt(parts[0]); const min = parseInt(parts[1]); if (h < 12) return ((min + 30) % 20 === 0) ? label : ''; else return (min % 20 === 0) ? label : ''; } } },
                                y: { min: yMin, max: yMax, grid: { color: 'rgba(255, 255, 255, 0.1)' }, ticks: { color: '#888', callback: v => v.toFixed(0) }, afterFit: function(scale) { scale.width = 65; } }
                            },
                            interaction: { mode: 'nearest', axis: 'x', intersect: false }
                        },

                    });
                    if (minuteLoading) minuteLoading.style.display = 'none';
                } else {
                    // 分时数据获取失败
                    if (minuteLoading) minuteLoading.textContent = '暂无分时数据';
                }
            })
            .catch(err => {
                console.log('分时数据加载失败:', err);
                const minuteLoading = document.getElementById('minuteLoading');
                if (minuteLoading) minuteLoading.textContent = '分时数据加载失败';
            });

    } catch (error) {
        indexCard.innerHTML = `<div class="error">指数加载失败</div>`;
    }
}

function generateMockFlowData() {
    const times = [];
    const netFlows = [];

    let cumulative = 0;
    for (let i = 0; i < 46; i++) {
        const hour = i < 19 ? 9 : 13;
        const minute = i < 19 ? 30 + (i * 5) : (i - 19) * 5;
        if (i === 19) {
            times.push('11:30');
            netFlows.push(cumulative);
            continue;
        }
        if (hour === 13 && minute > 55) break;

        const timeStr = `${hour}:${minute.toString().padStart(2, '0')}`;
        times.push(timeStr);

        const change = (Math.random() - 0.5) * 100;
        cumulative += change;
        netFlows.push(Math.round(cumulative));
    }

    return { times, netFlows };
}

async function loadAllData() {
    loadIndexWithChart();
}
