/** 异动中心 - 前端服务 */
var abnormalCurrentTab = 'prediction';
var abnormalCalcHistory = [];
var abnormalCalcActiveRequestId = 0;

// 外部数据源 unusual_type 到可读描述的映射
var UNUSUAL_TYPE_MAP = {
    '规则7': '连续30日内收盘价偏离累计达-70%'
};

function formatUnusualType(raw) {
    if (!raw) return '';
    return UNUSUAL_TYPE_MAP[raw] || raw;
}

// ===== 页面入口 =====
function loadAbnormalCenter() {
    loadAbnormalTabs();
    loadAbnormalCalcHistory();
    if (abnormalCurrentTab === 'prediction') loadPrediction();
    else if (abnormalCurrentTab === 'monitor') loadMonitor();
}

function loadAbnormalTabs() {
    var html =
        '<div class="tabs" style="margin-bottom:16px;">' +
        '<button class="tab-btn' + (abnormalCurrentTab === 'prediction' ? ' active' : '') + '" onclick="switchAbnormalTab(\'prediction\')">📈 异动预测</button>' +
        '<button class="tab-btn' + (abnormalCurrentTab === 'monitor' ? ' active' : '') + '" onclick="switchAbnormalTab(\'monitor\')">🔍 异动监控</button>' +
        '<button class="tab-btn' + (abnormalCurrentTab === 'calculator' ? ' active' : '') + '" onclick="switchAbnormalTab(\'calculator\')">🧮 异动分析器</button>' +
        '</div>' +
        '<div id="abnormalTabContent"></div>';
    document.getElementById('abnormal-main').innerHTML = html;
}

function switchAbnormalTab(tab) {
    abnormalCurrentTab = tab;
    loadAbnormalTabs();
    if (tab === 'prediction') loadPrediction();
    else if (tab === 'monitor') loadMonitor();
    else if (tab === 'calculator') loadCalculator();
}

// ==================== Tab 1: 异动预测 ====================

function loadPrediction() {
    var container = document.getElementById('abnormalTabContent');
    if (!container) return;
    container.innerHTML = '<div class="loading">正在加载异动预测...</div>';

    fetch('/api/abnormal/prediction')
        .then(function(r) { return r.json(); })
        .then(function(resp) {
            if (!resp.success) {
                container.innerHTML = '<div class="error">' + (resp.error || '加载失败') + '</div>';
                return;
            }
            var list = resp.data || [];
            if (!list.length) {
                container.innerHTML = '<div class="index-card" style="text-align:center;color:#888;padding:40px;">暂无预测数据</div>';
                return;
            }

            // 分组：今日 / 次日 / 未标记
            var groups = { '今日': [], '次日': [], '未标记': [] };
            list.forEach(function(item) {
                if (item.is_today) groups['今日'].push(item);
                else if (item.is_nextday) groups['次日'].push(item);
                else groups['未标记'].push(item);
            });

            var html = '';
            var groupOrder = ['今日', '次日', '未标记'];
            groupOrder.forEach(function(mark) {
                var items = groups[mark];
                if (!items.length) return;
                html += '<div class="index-card" style="margin-bottom:12px;">';
                html += '<h3 style="margin-bottom:12px;color:#e94560;">' + mark + '（' + items.length + '只）</h3>';
                html += '<div class="data-table"><table><thead><tr>' +
                    '<th>代码</th><th>名称</th><th>最新涨幅</th>' +
                    '<th>累计偏离</th><th>剩余触发</th><th>触发条件</th>' +
                    '<th>已用天数</th><th>状态</th>' +
                    '</tr></thead><tbody>';

                items.forEach(function(item) {
                    var statusClass = '';
                    var statusText = '';
                    if (item.is_happen) { statusClass = 'change-up'; statusText = '已触发'; }
                    else if (item.is_today) { statusClass = 'change-up'; statusText = '今日关注'; }
                    else if (item.is_nextday) { statusClass = ''; statusText = '次日关注'; }
                    else { statusText = '监控中'; }

                    html += '<tr onclick="showAbnormalStockKline(\'' + item.code + '\',\'' + (item.market || '') + '\',\'' + (item.name || '').replace(/'/g, '\\\'') + '\')" style="cursor:pointer;">' +
                        '<td>' + item.code + '</td>' +
                        '<td>' + (item.name || '') + '</td>' +
                        '<td class="' + (item.change_rate > 0 ? 'change-up' : 'change-down') + '">' + (item.change_rate > 0 ? '+' : '') + (item.change_rate != null ? item.change_rate.toFixed(2) + '%' : '-') + '</td>' +
                        '<td>' + (item.deviation_value != null ? item.deviation_value.toFixed(2) + '%' : '-') + '</td>' +
                        '<td class="' + (item.change_rate_target != null && item.change_rate_target < 3 ? 'change-up' : '') + '">' + (item.change_rate_target != null ? item.change_rate_target.toFixed(2) + '%' : '-') + '</td>' +
                        '<td style="font-size:11px;color:#888;">' + formatUnusualType(item.unusual_type) + '</td>' +
                        '<td>' + (item.max_days || '-') + '天</td>' +
                        '<td class="' + statusClass + '">' + statusText + '</td>' +
                        '</tr>';
                });

                html += '</tbody></table></div></div>';
            });

            container.innerHTML = html;
        })
        .catch(function(err) {
            container.innerHTML = '<div class="error">网络错误: ' + err.message + '</div>';
        });
}


// ==================== Tab 2: 异动监控 ====================

function loadMonitor() {
    var container = document.getElementById('abnormalTabContent');
    if (!container) return;
    container.innerHTML = '<div class="loading">正在加载异动监控...</div>';

    fetch('/api/abnormal/monitor')
        .then(function(r) { return r.json(); })
        .then(function(resp) {
            if (!resp.success) {
                container.innerHTML = '<div class="error">' + (resp.error || '加载失败') + '</div>';
                return;
            }
            var list = resp.data || [];
            var stats = resp.stats || {};

            if (!list.length) {
                container.innerHTML = '<div class="index-card" style="text-align:center;color:#888;padding:40px;">暂无监控数据</div>';
                return;
            }

            // 统计卡片
            var statsHtml = '';
            if (Object.keys(stats).length) {
                statsHtml = '<div class="stats-cards" style="margin-bottom:16px;">' +
                    '<div class="stat-card"><h3>风险警示</h3><div class="value" style="color:#e94560;">' + (stats.risk_warning || 0) + '</div></div>' +
                    '<div class="stat-card"><h3>严重异动</h3><div class="value" style="color:#ff6b6b;">' + (stats.severe_abnormal || 0) + '</div></div>' +
                    '<div class="stat-card"><h3>监控总数</h3><div class="value">' + (stats.total || 0) + '</div></div>' +
                    '</div>';
            }

            var html = statsHtml + '<div class="index-card"><div class="data-table"><table><thead><tr>' +
                '<th>代码</th><th>名称</th><th>类型</th><th>起始日</th>' +
                '<th>截止日</th><th>剩余天数</th><th>异动原因</th>' +
                '</tr></thead><tbody>';

            list.forEach(function(item) {
                var typeBadge = item.monitor_type === 'severe_abnormal'
                    ? '<span style="color:#ff6b6b;font-weight:bold;">严重异动</span>'
                    : '<span style="color:#f0a500;">风险警示</span>';

                var remainingStyle = item.remaining_days <= 3
                    ? 'color:#e94560;font-weight:bold;' : '';

                html += '<tr onclick="showAbnormalStockKline(\'' + item.code + '\',\'' + (item.market || '') + '\',\'' + (item.name || '').replace(/'/g, '\\\'') + '\')" style="cursor:pointer;">' +
                    '<td>' + item.code + '</td>' +
                    '<td>' + (item.name || '') + '</td>' +
                    '<td>' + typeBadge + '</td>' +
                    '<td>' + (item.monitor_start_date || '-') + '</td>' +
                    '<td>' + (item.monitor_end_date || '-') + '</td>' +
                    '<td style="' + remainingStyle + '">' + (item.remaining_days != null ? item.remaining_days + '天' : '-') + '</td>' +
                    '<td style="font-size:11px;color:#888;">' + (item.unusual_reason_type || (item.monitor_type === 'risk_warning' ? '交易所风险警示' : '')) + '</td>' +
                    '</tr>';
            });

            html += '</tbody></table></div></div>';
            container.innerHTML = html;
        })
        .catch(function(err) {
            container.innerHTML = '<div class="error">网络错误: ' + err.message + '</div>';
        });
}


// ==================== Tab 3: 异动分析器（计算器） ====================

function loadAbnormalCalcHistory() {
    try {
        var raw = localStorage.getItem('abnormal-calc-history-v1');
        abnormalCalcHistory = raw ? JSON.parse(raw) : [];
    } catch(e) {
        abnormalCalcHistory = [];
    }
}

function saveAbnormalCalcHistory() {
    try {
        localStorage.setItem('abnormal-calc-history-v1', JSON.stringify(abnormalCalcHistory.slice(0, 10)));
    } catch(e) {}
}

function loadCalculator() {
    var container = document.getElementById('abnormalTabContent');
    if (!container) return;

    var historyTags = '';
    if (abnormalCalcHistory.length) {
        historyTags = '<div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:6px;">' +
            '<span style="color:#666;font-size:12px;">最近搜索:</span>';
        abnormalCalcHistory.slice(0, 10).forEach(function(s) {
            historyTags += '<span class="refresh-btn" style="padding:3px 10px;font-size:11px;background:#0f3460;" onclick="runAnalyze(\'' + s.code + '\',\'' + (s.market || '') + '\',\'' + (s.name || '') + '\')">' + (s.name || s.code) + '</span>';
        });
        historyTags += '</div>';
    }

    container.innerHTML =
        '<div class="index-card" style="max-width:600px;margin:0 auto;">' +
        '<div style="display:flex;gap:10px;margin-bottom:12px;">' +
        '<input id="abnormalCalcInput" type="text" autocomplete="off" placeholder="输入股票名称或代码..." ' +
        'style="flex:1;padding:10px 14px;border:1px solid #0f3460;border-radius:8px;background:#1a1a2e;color:#fff;font-size:14px;outline:none;" ' +
        'onkeydown="if(event.key===\'Enter\')runAnalyzeFromInput()" ' +
        'oninput="abnormalCalcSearch()" ' +
        'onfocus="abnormalCalcSearch()" ' +
        'onblur="setTimeout(function(){var el=document.getElementById(\'abnormalCalcResults\');if(el)el.innerHTML=\'\';},300)">' +
        '<button class="refresh-btn" onclick="runAnalyzeFromInput()" style="white-space:nowrap;">分析</button>' +
        '</div>' +
        '<div id="abnormalCalcResults" style="margin-bottom:8px;"></div>' +
        historyTags +
        '<div id="abnormalCalcOutput"></div>' +
        '</div>';
}

function abnormalCalcSearch() {
    var q = (document.getElementById('abnormalCalcInput') || {}).value || '';
    if (q.length < 1) {
        document.getElementById('abnormalCalcResults').innerHTML = '';
        return;
    }
    fetch('/api/search-stock?q=' + encodeURIComponent(q))
        .then(function(r) { return r.json(); })
        .then(function(resp) {
            var list = resp.data || [];
            if (!list.length) { document.getElementById('abnormalCalcResults').innerHTML = ''; return; }
            var html = '';
            list.slice(0, 8).forEach(function(s) {
                html += '<div style="padding:6px 12px;cursor:pointer;border-bottom:1px solid #0f3460;" ' +
                    'onmousedown="runAnalyze(\'' + s.code + '\',\'' + (s.market || '') + '\',\'' + (s.name || '') + '\')">' +
                    '<span style="color:#ccc;">' + s.code + '</span> ' +
                    '<span style="color:#fff;">' + (s.name || '') + '</span>' +
                    '</div>';
            });
            document.getElementById('abnormalCalcResults').innerHTML = html;
        })
        .catch(function() {});
}

function runAnalyzeFromInput() {
    var input = document.getElementById('abnormalCalcInput');
    if (!input || !input.value.trim()) return;
    runAnalyze(input.value.trim(), '', '');
}

function runAnalyze(code, market, name) {
    var output = document.getElementById('abnormalCalcOutput');
    if (!output) return;
    output.innerHTML = '<div class="loading">正在分析 ' + code + '...</div>';

    var reqId = ++abnormalCalcActiveRequestId;

    var formData = new FormData();
    formData.append('code', code);
    if (market) formData.append('market', market);

    fetch('/api/abnormal/analyze', { method: 'POST', body: formData })
        .then(function(r) { return r.json(); })
        .then(function(resp) {
            if (reqId !== abnormalCalcActiveRequestId) return;
            if (!resp.success) {
                output.innerHTML = '<div class="error">' + (resp.error || '分析失败') + '</div>';
                return;
            }
            var d = resp.data;
            // 更新搜索历史
            abnormalCalcHistory = abnormalCalcHistory.filter(function(s) { return s.code !== d.code; });
            abnormalCalcHistory.unshift({ code: d.code, name: d.name, market: d.market });
            abnormalCalcHistory = abnormalCalcHistory.slice(0, 10);
            saveAbnormalCalcHistory();

            var warningsHtml = '';
            if (d.warnings && d.warnings.length) {
                warningsHtml = '<div style="background:#2a1a1a;border:1px solid #e94560;border-radius:6px;padding:10px 14px;margin-bottom:12px;">' +
                    '<div style="font-size:12px;color:#e94560;margin-bottom:6px;">⚠ 风险提示</div>' +
                    d.warnings.map(function(w) { return '<div style="font-size:12px;color:#ff9999;margin:3px 0;">• ' + w + '</div>'; }).join('') +
                    '</div>';
            }

            var w = d.regular_abnormal ? d.regular_abnormal.window || {} : {};

            var html = '<div style="margin-top:12px;">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
                '<div>' +
                '<span style="font-size:20px;font-weight:bold;color:#fff;">' + (d.name || d.code) + '</span>' +
                '<span style="font-size:13px;color:#888;margin-left:8px;">' + d.code + '</span>' +
                '</div>' +
                '<div style="text-align:right;">' +
                '<div style="font-size:22px;font-weight:bold;">' + (d.latest_close != null ? d.latest_close.toFixed(2) : '-') + '</div>' +
                '<div class="' + (d.change_pct >= 0 ? 'change-up' : 'change-down') + '" style="font-size:14px;">' + (d.change_pct >= 0 ? '+' : '') + (d.change_pct != null ? d.change_pct.toFixed(2) + '%' : '-') + '</div>' +
                '</div></div>' +
                warningsHtml +
                '<div class="stats-cards" style="margin-bottom:12px;">' +
                '<div class="stat-card"><h3>5日涨跌</h3><div class="value ' + (w.pct_5d >= 0 ? 'positive' : 'negative') + '">' + (w.pct_5d != null ? (w.pct_5d >= 0 ? '+' : '') + w.pct_5d.toFixed(2) + '%' : '-') + '</div></div>' +
                '<div class="stat-card"><h3>10日涨跌</h3><div class="value ' + (w.pct_10d >= 0 ? 'positive' : 'negative') + '">' + (w.pct_10d != null ? (w.pct_10d >= 0 ? '+' : '') + w.pct_10d.toFixed(2) + '%' : '-') + '</div></div>' +
                '<div class="stat-card"><h3>20日涨跌</h3><div class="value ' + (w.pct_20d >= 0 ? 'positive' : 'negative') + '">' + (w.pct_20d != null ? (w.pct_20d >= 0 ? '+' : '') + w.pct_20d.toFixed(2) + '%' : '-') + '</div></div>' +
                '<div class="stat-card"><h3>20日振幅</h3><div class="value">' + (w.amplitude_20d != null ? w.amplitude_20d.toFixed(2) + '%' : '-') + '</div></div>' +
                '</div>' +

                '<div class="stats-cards" style="margin-bottom:12px;">' +
                '<div class="stat-card"><h3>偏离10日线</h3><div class="value ' + (w.ma10 ? (d.latest_close >= w.ma10 ? 'positive' : 'negative') : '') + '">' +
                (d.limit_up_projection && d.limit_up_projection.current ? (d.limit_up_projection.current.deviation_10d >= 0 ? '+' : '') + d.limit_up_projection.current.deviation_10d.toFixed(2) + '%' : '-') +
                '</div></div>' +
                '<div class="stat-card"><h3>偏离30日线</h3><div class="value ' + (w.ma30 ? (d.latest_close >= w.ma30 ? 'positive' : 'negative') : '') + '">' +
                (d.limit_up_projection && d.limit_up_projection.current ? (d.limit_up_projection.current.deviation_30d >= 0 ? '+' : '') + d.limit_up_projection.current.deviation_30d.toFixed(2) + '%' : '-') +
                '</div></div>' +
                '<div class="stat-card"><h3>20日高点回撤</h3><div class="value">' + (w.drawdown_20d != null ? w.drawdown_20d.toFixed(2) + '%' : '-') + '</div></div>' +
                '<div class="stat-card"><h3>连续' + (w.consecutive_dir === 'up' ? '上涨' : '下跌') + '</h3><div class="value ' + (w.consecutive_dir === 'up' ? 'positive' : 'negative') + '">' + (w.consecutive_days != null ? w.consecutive_days + '天' : '-') + '</div></div>' +
                '</div>' +

                '<div class="stats-cards">' +
                '<div class="stat-card"><h3>10日均价</h3><div class="value">' + (w.ma10 != null ? w.ma10.toFixed(2) : '-') + '</div></div>' +
                '<div class="stat-card"><h3>30日均价</h3><div class="value">' + (w.ma30 != null ? w.ma30.toFixed(2) : '-') + '</div></div>' +
                '<div class="stat-card"><h3>涨停价</h3><div class="value positive">' + (d.limit_up_projection ? d.limit_up_projection.limit_up_price.toFixed(2) : '-') + '</div></div>' +
                '<div class="stat-card"><h3>跌停价</h3><div class="value negative">' + (d.limit_up_projection ? d.limit_up_projection.limit_down_price.toFixed(2) : '-') + '</div></div>' +
                '</div>' +
                '</div>';

            output.innerHTML = html;
        })
        .catch(function(err) {
            if (reqId !== abnormalCalcActiveRequestId) return;
            output.innerHTML = '<div class="error">网络错误: ' + err.message + '</div>';
        });
}

// ===== K线弹窗（点击股票查看） =====

function showAbnormalStockKline(code, market, name) {
    name = name || '';
    var mkt = '';
    if (market === 'sh' || market === '1' || market === '2') mkt = '1';
    else if (market === 'sz' || market === '0') mkt = '0';
    else mkt = market;

    if (typeof KlinePopup !== 'undefined' && KlinePopup.open) {
        KlinePopup.open(code, mkt, name);
    }
}
