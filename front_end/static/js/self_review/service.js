// ==================== 自助复盘页面 ====================

// 自助复盘通用加载：区分「业务失败 / HTTP 异常 / 响应非 JSON / 网络异常 / 渲染异常」，
// 避免把服务端 500 等真实原因一律误报为“网络异常”。
function _srLoad(url, content, loadingText, manual, render) {
    if (!content) return;
    if (manual) {
        content.innerHTML = '<div class="loading" style="padding:90px 0;">' + loadingText + '</div>';
    }
    fetch(url)
        .then(function(r) {
            if (!r.ok) {
                return r.text().then(function(body) {
                    var err = new Error('HTTP ' + r.status);
                    err.status = r.status;
                    err.body = body;
                    throw err;
                });
            }
            return r.json();
        })
        .then(function(res) {
            if (!res || res.success === false) {
                content.innerHTML = '<div class="error" style="padding:40px 20px;">' + ((res && res.error) || '复盘失败') + '</div>';
                return;
            }
            try {
                render(res.data);
            } catch (e) {
                console.error('[self-review] 数据渲染出错:', e);
                content.innerHTML = '<div class="error" style="padding:40px 20px;">复盘数据渲染出错，请查看浏览器控制台</div>';
            }
        })
        .catch(function(err) {
            if (err && err.status) {
                console.error('[self-review] HTTP ' + err.status, String(err.body || '').slice(0, 500));
                content.innerHTML = '<div class="error" style="padding:40px 20px;">服务异常（HTTP ' + err.status + '），请查看服务端控制台日志</div>';
            } else if (err instanceof SyntaxError) {
                content.innerHTML = '<div class="error" style="padding:40px 20px;">服务响应解析失败，请查看服务端控制台日志</div>';
            } else {
                content.innerHTML = '<div class="error" style="padding:40px 20px;">网络异常，复盘请求失败</div>';
            }
        });
}

function loadSelfReview(manual) {
    _srLoad('/api/self-review', document.getElementById('srContent'),
        '正在获取行情并复盘，请稍候...', manual, renderSelfReview);
}

function renderSelfReview(d) {
    var metaEl = document.getElementById('srMeta');
    if (metaEl) {
        var dayText = d.day ? '复盘交易日 <span style="color:#fbbf24;">' + d.day + '</span> · ' : '';
        metaEl.innerHTML = dayText + '更新于 <span style="color:#ccc;">' + d.update_time + '</span> · 市场状态：<span style="color:#ccc;">' + d.market_status + '</span>';
    }
    var html = '';
    html += _srPlan(d.plan);
    html += _srIntraday(d.minute, d.turnover, d.open_hour);
    html += _srBreadth(d.breadth, d.sentiment);
    html += _srIndexTable(d.indices);
    html += _srLevels(d.levels);
    html += _srSynergy(d.synergy);
    html += _srFunds(d.funds);
    document.getElementById('srContent').innerHTML = html;
}

// ---- 通用格式化（红涨绿跌） ----

function _srCol(v) {
    if (v === null || v === undefined) return '#999';
    if (v > 0) return '#d63850';
    if (v < 0) return '#00b894';
    return '#999';
}

function _srPct(v) {
    if (v === null || v === undefined) return '--';
    return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
}

function _srSigned(v) {
    if (v === null || v === undefined) return '--';
    return (v >= 0 ? '+' : '') + v.toFixed(2);
}

function _srNum(v) {
    if (v === null || v === undefined) return '--';
    return v.toFixed(2);
}

function _srCard(bodyHtml) {
    return '<div class="index-card sr-card">' + bodyHtml + '</div>';
}

// ---- 主要指数行情 ----

function _srIndexTable(indices) {
    if (!indices || !indices.length) return '';
    var ths = ['指数', '最新价', '涨跌幅', '涨跌额', '今开', '最高', '最低', 'MA5', 'MA20', 'MA60', '20日压力', '20日支撑', '60日分位'];
    var head = '<thead><tr>';
    ths.forEach(function(t) { head += '<th>' + t + '</th>'; });
    head += '</tr></thead>';

    var rows = '';
    indices.forEach(function(it) {
        var col = _srCol(it.change_pct);
        rows += '<tr>' +
            '<td class="col-name">' + it.name + '</td>' +
            '<td style="color:' + col + ';font-weight:bold;">' + _srNum(it.price) + '</td>' +
            '<td style="color:' + col + ';">' + _srPct(it.change_pct) + '</td>' +
            '<td style="color:' + col + ';">' + _srSigned(it.change_val) + '</td>' +
            '<td>' + _srNum(it.open) + '</td>' +
            '<td>' + _srNum(it.high) + '</td>' +
            '<td>' + _srNum(it.low) + '</td>' +
            '<td style="color:#c4b5fd;">' + _srNum(it.ma5) + '</td>' +
            '<td style="color:#c4b5fd;">' + _srNum(it.ma20) + '</td>' +
            '<td style="color:#c4b5fd;">' + _srNum(it.ma60) + '</td>' +
            '<td style="color:#fbbf24;">' + _srNum(it.high_20) + '</td>' +
            '<td style="color:#60a5fa;">' + _srNum(it.low_20) + '</td>' +
            '<td>' + (it.pos_pct !== null && it.pos_pct !== undefined ? it.pos_pct.toFixed(0) + '%' : '--') + '</td>' +
            '</tr>';
    });

    var note = '<div class="sr-note">' +
        'MA5/20/60 = 近5/20/60个交易日收盘均价（紫色），现价在均线上方说明该周期持仓多数盈利、抛压小，跌破则套牢盘增多；' +
        '20日压力/支撑 = 近20个交易日最高/最低价（含当日），黄色为上方压力、蓝色为下方支撑参考；' +
        '60日分位 = 现价位于近60日最高最低价区间的百分位（越低越接近区间底部）。' +
        '</div>';
    return _srCard('<div class="card-title sr-title">📈 主要指数复盘</div>' +
        '<div class="sector-table-wrap"><table class="sector-fund-table">' + head + '<tbody>' + rows + '</tbody></table></div>' + note);
}

// ---- 指数同频共振 / 分化 ----

function _srSynergy(s) {
    if (!s) return '';
    var chips = '';
    (s.up || []).forEach(function(n) {
        chips += '<span class="sr-chip" style="color:#d63850;border:1px solid rgba(214,56,80,0.4);">▲ ' + n + '</span>';
    });
    (s.down || []).forEach(function(n) {
        chips += '<span class="sr-chip" style="color:#00b894;border:1px solid rgba(0,184,148,0.4);">▼ ' + n + '</span>';
    });
    (s.flat || []).forEach(function(n) {
        chips += '<span class="sr-chip" style="color:#888;border:1px solid rgba(136,136,136,0.35);">— ' + n + '</span>';
    });
    var tagColor = s.mode.indexOf('普涨') >= 0 ? '#d63850' : (s.mode.indexOf('普跌') >= 0 ? '#00b894' : '#fbbf24');
    return _srCard('<div class="card-title sr-title-sm">🔀 指数同频共振 / 分化研判</div>' +
        '<div style="margin-bottom:8px;"><span style="display:inline-block;padding:2px 10px;border-radius:3px;background:' + tagColor + ';color:#fff;font-size:12px;font-weight:600;">' + s.mode + '</span></div>' +
        (chips ? '<div style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:6px;">' + chips + '</div>' : '') +
        '<div class="sr-conclusion">' + s.summary + '</div>');
}

// ---- 关键点位 / 压力支撑 ----

function _srLevels(levels) {
    if (!levels || !levels.length) return '';
    var items = '';
    levels.forEach(function(lv) {
        items += '<div style="padding:10px 12px;border-bottom:1px solid rgba(255,255,255,0.05);line-height:1.9;">' +
            '<span style="color:#fff;font-weight:600;">' + lv.name + '</span>' +
            ' <span style="color:#fbbf24;font-weight:bold;">' + _srNum(lv.price) + '</span>' +
            ' <span style="color:#8b8b9e;font-size:12px;">' + lv.conclusion + '</span>' +
            '</div>';
    });
    return _srCard('<div class="card-title sr-title">🎯 关键点位 · 压力位 / 支撑位</div>' + items);
}

// ---- 全市场涨跌家数 · 涨停/连板情绪（涨跌家数的极端分布） ----

function _srBreadth(b, s) {
    if (!b) return '';
    var ratio = b.red_ratio;
    var barColor = ratio >= 55 ? '#d63850' : (ratio <= 40 ? '#00b894' : '#fbbf24');
    function _tag(text, color, bg) {
        return '<span class="sr-tag" style="color:' + color + ';background:' + (bg || 'transparent') + ';border:1px solid ' + color + '55;">' + text + '</span>';
    }
    var html = '';
    html += '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:10px;">' +
        '<span style="font-size:13px;color:#8b8b9e;">上涨 <span style="color:#d63850;font-size:15px;font-weight:600;">' + b.rise + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">下跌 <span style="color:#00b894;font-size:15px;font-weight:600;">' + b.fall + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">平盘 <span style="color:#888;font-size:15px;font-weight:600;">' + b.flat + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">红盘率 <span style="color:' + barColor + ';font-size:15px;font-weight:600;">' + ratio.toFixed(1) + '%</span></span>' +
        '</div>' +
        '<div style="width:100%;height:10px;border-radius:5px;background:rgba(255,255,255,0.08);margin-bottom:10px;position:relative;">' +
        '<div style="width:' + ratio + '%;height:10px;border-radius:5px;background:' + barColor + ';"></div>' +
        '</div>';
    if (s) {
        var ztColor = s.zt_clean >= 35 ? '#d63850' : (s.zt_clean >= 15 ? '#fbbf24' : '#00b894');
        var dtColor = s.dt_clean >= 20 ? '#00b894' : (s.dt_clean >= 10 ? '#fbbf24' : '#8b8b9e');
        var chips = '';
        chips += _tag('涨停 ' + s.zt_total + ' 家', ztColor);
        if (s.zt_st) chips += _tag('ST ' + s.zt_st, '#8b8b9e');
        chips += _tag('跌停 ' + s.dt_total + ' 家', dtColor);
        if (s.dt_st) chips += _tag('ST ' + s.dt_st, '#8b8b9e');
        if (s.max_lb >= 1) {
            chips += _tag('最高 ' + s.max_lb + ' 连板', s.max_lb >= 4 ? '#d63850' : (s.max_lb === 3 ? '#fbbf24' : '#60a5fa'));
        }
        (s.ladder || []).forEach(function(l) {
            var c = l.h >= 4 ? '#d63850' : '#fbbf24';
            chips += _tag(l.h + '板×' + l.count + '家', c, 'rgba(255,255,255,0.02)');
        });
        if (s.gaps && s.gaps.length) {
            chips += _tag('梯队断层(' + s.gaps.join('/') + '板空缺)', '#d63850', 'rgba(214,56,80,0.08)');
        }
        html += '<div style="border-top:1px solid rgba(255,255,255,0.07);padding-top:10px;margin-bottom:4px;">' +
            '<div style="font-size:12px;color:#8b8b9e;margin-bottom:4px;">🔥 涨停/连板结构' +
            (s.day ? '<span style="color:#666;font-size:11px;margin-left:6px;">数据日期：' + s.day + '</span>' : '') + '</div>' +
            '<div style="line-height:2;">' + chips + '</div>' +
            '<div class="sr-conclusion" style="margin-top:4px;">' + s.conclusion + '</div>' +
            '</div>';
    }
    html += '<div class="sr-conclusion">' + b.conclusion + '</div>';
    return _srCard('<div class="card-title sr-title">📊 全市场涨跌家数（含涨停/连板情绪）</div>' + html);
}

// ---- 上证日内形态 · 两市成交额（日内量价与温度，含开盘首小时量价结构） ----

function _srIntraday(m, t, oh) {
    if (!m && !t && !oh) return '';
    var html = '';
    // 数据日期（日内形态）
    var day = (m && m.day) || (oh && oh.day) || (t && t.day);
    if (day) html += '<div class="sr-meta">数据日期：' + day + '</div>';
    var rowStyle = 'display:flex;flex-wrap:wrap;gap:20px;font-size:13px;color:#8b8b9e;margin-bottom:8px;';
    function _row(content) {
        return '<div style="' + rowStyle + '">' + content + '</div>';
    }
    if (m) {
        // 第一行：昨收 / 开盘 / 收盘 / 最高 / 最低
        var line1 =
            '<span>昨收 <span style="color:#8b8b9e;font-weight:600;">' + _srNum(m.pre_close) + '</span></span>' +
            '<span>开盘 <span style="color:' + _srCol(m.open_pct) + ';font-weight:600;">' + _srNum(m.open) + '</span>' +
            ' <span style="color:' + _srCol(m.open_pct) + ';font-weight:600;">' + _srPct(m.open_pct) + '</span></span>' +
            '<span>收盘 <span style="color:' + _srCol(m.change_pct) + ';font-weight:600;">' + _srNum(m.close) + '</span>' +
            ' <span style="color:' + _srCol(m.change_pct) + ';font-weight:600;">' + _srPct(m.change_pct) + '</span></span>' +
            '<span>最高 <span style="color:#d63850;font-weight:600;">' + _srNum(m.high) + '</span>' +
            ' <span style="color:' + _srCol(m.high_pct) + ';font-weight:600;">' + _srPct(m.high_pct) + '</span>' +
            (m.high_time ? '<span style="color:#8b8b9e;">（约' + m.high_time + '）</span>' : '') + '</span>' +
            '<span>最低 <span style="color:#00b894;font-weight:600;">' + _srNum(m.low) + '</span>' +
            ' <span style="color:' + _srCol(m.low_pct) + ';font-weight:600;">' + _srPct(m.low_pct) + '</span>' +
            (m.low_time ? '<span style="color:#8b8b9e;">（约' + m.low_time + '）</span>' : '') + '</span>';
        html += _row(line1);
    }
    // 第二行：成交额
    if (t) {
        var chgCol = _srCol(t.change);
        var line2 =
            '<span>昨日成交额 <span style="color:#8b8b9e;">' + t.yesterday.toFixed(0) + ' 亿</span></span>' +
            '<span>当日成交额 <span style="color:' + chgCol + ';font-weight:600;">' + t.today.toFixed(0) + ' 亿</span></span>' +
            '<span>较昨日 <span style="color:' + chgCol + ';">' + _srSigned(t.change) + ' 亿 (' + _srPct(t.change_pct) + ')</span></span>';
        html += _row(line2);
    }
    // 第三行：开盘首小时量价（原「开盘首小时量价结构」卡片数据并入此处）
    if (oh) {
        if (!oh.complete) {
            html += '<div style="font-size:12px;color:#fbbf24;margin-bottom:6px;">首小时尚未结束，以下为盘中实时累计</div>';
        }
        var ratioCol = oh.ratio >= 36 ? '#d63850' : (oh.ratio >= 24 ? '#fbbf24' : '#00b894');
        var line3 =
            '<span>开盘一小时成交 <span style="color:#8b8b9e;font-weight:600;">' + oh.open_amt.toFixed(0) + ' 亿</span></span>' +
            '<span>占当日成交比例 <span style="color:' + ratioCol + ';font-weight:600;">' + oh.ratio.toFixed(0) + '%</span></span>' +
            (oh.sh_pct !== null && oh.sh_pct !== undefined
                ? '<span>同期上证(对开盘) <span style="color:' + _srCol(oh.sh_pct) + ';font-weight:600;">' +
                    (oh.sh_pct >= 0 ? '+' : '') + oh.sh_pct.toFixed(2) + '%</span></span>'
                : '');
        html += _row(line3);
    }
    if (m && m.conclusion) html += '<div class="sr-conclusion">' + m.conclusion + '</div>';
    // 成交量的总结：量能温度结论 + 开盘首小时量价结论
    if (t && t.conclusion) html += '<div class="sr-conclusion">' + t.conclusion + '</div>';
    if (oh && oh.verdict) html += '<div class="sr-conclusion">' + oh.verdict + '</div>';
    return _srCard('<div class="card-title sr-title">🕐 上证日内形态</div>' + html);
}

// ---- 资金面（两融 / 板块主力资金） ----

function _srFunds(f) {
    if (!f) return '';
    function _s(label, value, color) {
        return '<span class="sr-label">' + label +
            ' <span class="sr-value" style="color:' + (color || '#fff') + ';">' + value + '</span></span>';
    }
    function _amtTag(name, val) {
        var c = val >= 0 ? '#d63850' : '#00b894';
        return '<span class="sr-tag" style="color:' + c + ';border:1px solid ' + c + '55;">' + name + ' ' + (val >= 0 ? '+' : '') + val.toFixed(1) + '亿</span>';
    }
    var html = '';
    var mg = f.margin;
    if (mg) {
        var c5 = _srCol(mg.fin_bal_5d);
        var heatCol = (mg.fin_buy_heat !== null && mg.fin_buy_heat !== undefined)
            ? _srCol(mg.fin_buy_heat) : '#8b8b9e';
        var rows = _s('两融余额', mg.latest_total.toFixed(0) + ' 亿') +
            _s('5日变化', (mg.fin_bal_5d !== null && mg.fin_bal_5d !== undefined ? (mg.fin_bal_5d >= 0 ? '+' : '') + mg.fin_bal_5d.toFixed(2) + '%' : '--'), c5) +
            (mg.fin_buy_heat !== null && mg.fin_buy_heat !== undefined
                ? _s('融资买入活跃度', (mg.fin_buy_heat >= 0 ? '+' : '') + mg.fin_buy_heat.toFixed(0) + '% vs 20日均', heatCol)
                : '');
        html += '<div style="margin-bottom:10px;font-size:13px;color:#8b8b9e;">融资融券（杠杆资金）' +
            (mg.date ? '<span style="color:#666;font-size:11px;margin-left:6px;">截至 ' + mg.date + '</span>' : '') + '</div>' +
            '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:8px;">' + rows + '</div>';
    }
    var sec = f.sector;
    if (sec) {
        var inTags = (sec.in_top || []).map(function(x) { return _amtTag(x.name, x.val); }).join('');
        var outTags = (sec.out_top || []).map(function(x) { return _amtTag(x.name, x.val); }).join('');
        html += '<div style="margin-bottom:6px;font-size:13px;color:#8b8b9e;">行业板块主力净流入（今日）</div>' +
            '<div style="margin-bottom:4px;">' + (inTags || '<span style="color:#666;font-size:12px;">无净流入居前板块</span>') + '</div>' +
            '<div style="margin-bottom:8px;">' + (outTags || '<span style="color:#666;font-size:12px;">无净流出居前板块</span>') + '</div>';
    }
    return _srCard('<div class="card-title sr-title">💰 资金面（两融 + 板块流向）</div>' +
        (f.day ? '<div class="sr-meta">数据日期：' + f.day + '</div>' : '') +
        html +
        '<div class="sr-conclusion">' + f.conclusion + '</div>');
}

// ---- 复盘总结 · 次日预案 ----

function _srPlan(p) {
    if (!p) return '';
    var html = '';
    html += '<div style="font-size:14px;color:#fff;line-height:1.8;margin-bottom:10px;">' + p.state + '</div>';

    if (p.divergences && p.divergences.length) {
        var dlist = p.divergences.map(function(x) { return '· ' + x; }).join('<br>');
        html += '<div style="font-size:12px;color:#fbbf24;line-height:1.9;margin-bottom:10px;padding:8px 10px;background:rgba(251,191,36,0.08);border-radius:4px;">⚠️ 背离信号<br>' + dlist + '</div>';
    }

    var watchHtml = '';
    if (p.watch_sectors && p.watch_sectors.length) {
        watchHtml += '<span class="sr-label">主线板块 <span style="color:#d63850;font-weight:600;">' + p.watch_sectors.join('、') + '</span></span>';
    }
    if (p.avoid_sectors && p.avoid_sectors.length) {
        watchHtml += '<span class="sr-label">回避板块 <span style="color:#00b894;font-weight:600;">' + p.avoid_sectors.join('、') + '</span></span>';
    }
    if (p.leaders && p.leaders.length) {
        var l = p.leaders.map(function(x) { return x.name + '(' + x.lbc + '板)'; }).join('、');
        watchHtml += '<span class="sr-label">风向标个股 <span style="color:#fbbf24;font-weight:600;">' + l + '</span></span>';
    }
    if (watchHtml) {
        html += '<div style="display:flex;flex-wrap:wrap;gap:8px 20px;margin-bottom:10px;line-height:2;">' + watchHtml + '</div>';
    }

    html += '<div style="font-size:13px;line-height:1.9;">' +
        '<div style="color:#d63850;font-weight:600;margin-bottom:4px;">🔺 进攻条件</div>' +
        '<div class="sr-conclusion">' + p.attack + '</div>' +
        '<div style="color:#00b894;font-weight:600;margin:10px 0 4px;">🔻 观望条件</div>' +
        '<div class="sr-conclusion">' + p.watch + '</div>' +
        '</div>';

    return _srCard('<div class="card-title sr-title">📋 复盘总结 · 次日预案</div>' + html);
}

// ---- 页签切换 + 自选复盘 ----

var currentReviewTab = 'market';
var stockReviewLoaded = false;

function switchReviewTab(tab) {
    currentReviewTab = tab;
    var tabs = document.querySelectorAll('#page-self-review .sr-tab');
    for (var i = 0; i < tabs.length; i++) {
        if (tabs[i].getAttribute('data-tab') === tab) tabs[i].classList.add('active');
        else tabs[i].classList.remove('active');
    }
    document.getElementById('srContent').style.display = tab === 'market' ? 'block' : 'none';
    document.getElementById('srStockContent').style.display = tab === 'stock' ? 'block' : 'none';
    if (tab === 'stock' && !stockReviewLoaded) {
        loadStockReview(false);
    }
}

function refreshCurrentReview() {
    if (currentReviewTab === 'market') loadSelfReview(true);
    else loadStockReview(true);
}

function loadStockReview(manual) {
    _srLoad('/api/self-review/stocks', document.getElementById('srStockContent'),
        '正在获取自选股并复盘，请稍候...', manual, function(data) {
            stockReviewLoaded = true;
            renderStockReview(data);
        });
}

function renderStockReview(d) {
    var html = '';
    html += _srStockSummary(d.summary);
    var groups = d.groups || {};
    var order = ['watchlist', 'etf', 'holdings'];
    order.forEach(function(key) {
        var g = groups[key];
        if (g) html += _srStockTable(g.label, g.items);
    });
    if (!html) {
        html = '<div class="index-card sr-card"><div style="color:#666;font-size:13px;">暂无自选股 / 场内ETF / 持仓股，请先到「自选股」页面添加。</div></div>';
    }
    document.getElementById('srStockContent').innerHTML = html;
}

function _srStockSummary(summary) {
    var p = (summary && summary.pressure) || [];
    var s = (summary && summary.support) || [];
    if (!p.length && !s.length) return '';
    var html = '';
    if (p.length) {
        var rows = p.map(function(x) {
            return '<div style="line-height:1.9;"><span style="color:#888;">' + x.code + '</span> ' +
                '<span style="cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + x.code + '\',\'' + x.market + '\',\'' + x.name + '\')">' + x.name + '</span>' +
                ' <span style="color:#8b8b9e;font-size:11px;">[' + x.group + ']</span>' +
                ' <span style="color:#888;font-size:12px;">' + x.hint + '</span></div>';
        }).join('');
        html += '<div style="color:#fbbf24;font-weight:600;margin-bottom:6px;">🟡 触及压力位（' + p.length + '）</div>' + rows;
    }
    if (s.length) {
        var rows2 = s.map(function(x) {
            return '<div style="line-height:1.9;"><span style="color:#888;">' + x.code + '</span> ' +
                '<span style="cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + x.code + '\',\'' + x.market + '\',\'' + x.name + '\')">' + x.name + '</span>' +
                ' <span style="color:#8b8b9e;font-size:11px;">[' + x.group + ']</span>' +
                ' <span style="color:#888;font-size:12px;">' + x.hint + '</span></div>';
        }).join('');
        html += '<div style="color:#3b82f6;font-weight:600;margin:10px 0 6px;">🔵 触及支撑位（' + s.length + '）</div>' + rows2;
    }
    return _srCard('<div class="card-title sr-title">🎯 复盘总结·关键点位提醒</div>' + html);
}

function _srStockTable(label, items) {
    if (!items || !items.length) {
        return _srCard('<div class="card-title sr-title">' + label + '</div>' +
            '<div style="color:#666;font-size:13px;">暂无数据</div>');
    }
    function _dec(code, market) {
        return isETF(code, market) ? 3 : 2;  // 复用 common.js 全局 isETF
    }
    function _fmt(v, code, market) {
        return (v === null || v === undefined) ? '--' : v.toFixed(_dec(code, market));
    }
    function _srLevelCell(it) {
        function _pct(val) {
            if (val === null || val === undefined || !it.price) return null;
            return (val - it.price) / it.price * 100;
        }
        function _pctTxt(pct) {
            return (pct === null) ? '' : '(' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)';
        }
        var rows = [20, 60, 120].map(function(n) {
            var sup = it['support_' + n];
            var pre = it['pressure_' + n];
            return '<div style="white-space:nowrap;">' + n + '日 ' +
                '<span style="color:#60a5fa;">' + _fmt(sup, it.code, it.market) + '</span>' + _pctTxt(_pct(sup)) + '~' +
                '<span style="color:#fbbf24;">' + _fmt(pre, it.code, it.market) + '</span>' + _pctTxt(_pct(pre)) + '</div>';
        });
        return '<td style="text-align:left;font-size:12px;color:#8b8b9e;white-space:nowrap;min-width:220px;">' +
            rows.join('') + '</td>';
    }
    function _srBollCell(it) {
        function _pct(val) {
            if (val === null || val === undefined || !it.price) return null;
            return (val - it.price) / it.price * 100;
        }
        function _pctTxt(pct) {
            return (pct === null) ? '' : '(' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)';
        }
        function _row(label, b) {
            if (!b || b.mid === null || b.mid === undefined) {
                return '<div style="white-space:nowrap;">' + label + ' --</div>';
            }
            return '<div style="white-space:nowrap;">' + label + ' ' +
                '<span style="color:#26a69a;">' + _fmt(b.lower, it.code, it.market) + '</span>' + _pctTxt(_pct(b.lower)) + '~' +
                '<span style="color:#60a5fa;">' + _fmt(b.mid, it.code, it.market) + '</span>' + _pctTxt(_pct(b.mid)) + '~' +
                '<span style="color:#ef5350;">' + _fmt(b.upper, it.code, it.market) + '</span>' + _pctTxt(_pct(b.upper)) + '</div>';
        }
        return '<td style="text-align:left;font-size:12px;color:#8b8b9e;white-space:nowrap;min-width:280px;">' +
            _row('日布林', it.boll_daily) +
            _row('周布林', it.boll_weekly) +
            '</td>';
    }
    function _srConclusionCell(it) {
        function _pct(val) {
            if (val === null || val === undefined || !it.price) return null;
            return (val - it.price) / it.price * 100;
        }
        function _pctTxt(pct) {
            return (pct === null) ? '' : '(' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)';
        }
        function _num(v, color) {
            var txt = (v === null || v === undefined) ? '--' : v.toFixed(_dec(it.code, it.market));
            return '<span style="color:' + color + ';">' + txt + '</span>' + _pctTxt(_pct(v));
        }
        var html = '';
        (it.levels || []).forEach(function(lv) {
            html += '<div style="white-space:nowrap;">' + lv.n + '日 筹码密集区 ' +
                _num(lv.lo, '#60a5fa') + '~' + _num(lv.hi, '#fbbf24') + ' 中枢 ' + _num(lv.center, '#c084fc');
            if (lv.note) {
                html += '，' + lv.note;
            } else if (lv.pressure !== null && lv.pressure !== undefined) {
                html += '，上方压力 ' + _num(lv.pressure, '#fbbf24') + '、下方支撑 ' + _num(lv.support, '#60a5fa');
            }
            html += '。</div>';
        });
        if (it.conclusion) {
            html += '<div style="margin-top:2px;white-space:normal;">' + it.conclusion + '</div>';
        }
        return '<td style="text-align:left;font-size:12px;color:#8b8b9e;white-space:normal;min-width:260px;">' + html + '</td>';
    }
    var ths = ['代码', '名称', '现价', '涨跌幅', '支撑/压力', '布林轨', '关键点位'];
    var head = '<thead><tr>';
    ths.forEach(function(t) { head += '<th>' + t + '</th>'; });
    head += '</tr></thead>';
    var rows = '';
    items.forEach(function(it, i) {
        var col = _srCol(it.change_pct);
        rows += '<tr>' +
            '<td style="color:#888;white-space:nowrap;">' + it.code + '</td>' +
            '<td style="text-align:left;white-space:nowrap;"><span style="font-weight:600;color:#eee;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + it.code + '\',\'' + it.market + '\',\'' + it.name + '\')">' + it.name + '</span></td>' +
            '<td style="color:' + col + ';font-weight:bold;">' + _fmt(it.price, it.code, it.market) + '</td>' +
            '<td style="color:' + col + ';">' + _srPct(it.change_pct) + '</td>' +
            _srLevelCell(it) +
            _srBollCell(it) +
            _srConclusionCell(it) +
            '</tr>';
    });
    var note = '<div class="sr-note">' +
        '压力/支撑 = 近对应交易日已收盘K线按收盘价聚合成「成交密集区」，压力为现价上方最近区中枢、支撑为现价下方最近区中枢；' +
        '现价位于某密集区内部时，压力/支撑改取该区上沿/下沿作参考（价格仍在带内、未真正突破/破位）。' +
        '颜色区分：<span style="color:#fbbf24;">黄=压力</span> <span style="color:#60a5fa;">蓝=支撑</span>。' +
        '密集区是以收盘价+成交量计算的真实筹码带（中枢=区内成交量加权收盘价），盘中自动剔除尚未收盘的当日K线。' +
        '显示 -- 表示现价上方/下方均无成交密集区且不在任一密集区内（处于突破/破位状态）；震荡市密集区有效性强，趋势市中仅作回踩/反抽参考。' +
        '</div>';
    return _srCard('<div class="card-title sr-title">' + label + '</div>' +
        '<div class="sector-table-wrap"><table class="sector-fund-table">' + head + '<tbody>' + rows + '</tbody></table></div>' + note);
}
