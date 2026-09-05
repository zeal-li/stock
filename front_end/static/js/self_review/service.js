// ==================== 自助复盘页面 ====================

function loadSelfReview(manual) {
    var content = document.getElementById('srContent');
    if (!content) return;
    if (manual) {
        content.innerHTML = '<div class="loading" style="padding:90px 0;">正在获取行情并复盘，请稍候...</div>';
    }
    fetch('/api/self-review')
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res.success) {
                content.innerHTML = '<div class="error" style="padding:40px 20px;">' + (res.error || '复盘失败') + '</div>';
                return;
            }
            renderSelfReview(res.data);
        })
        .catch(function() {
            content.innerHTML = '<div class="error" style="padding:40px 20px;">网络异常，复盘请求失败</div>';
        });
}

function renderSelfReview(d) {
    var metaEl = document.getElementById('srMeta');
    if (metaEl) {
        var dayText = d.day ? '复盘交易日 <span style="color:#fbbf24;">' + d.day + '</span> · ' : '';
        metaEl.innerHTML = dayText + '更新于 <span style="color:#ccc;">' + d.update_time + '</span> · 市场状态：<span style="color:#ccc;">' + d.market_status + '</span>';
    }
    var html = '';
    html += _srIndexTable(d.indices);
    html += _srLevels(d.levels);
    html += _srSynergy(d.synergy);
    html += _srBreadth(d.breadth);
    html += _srTurnover(d.turnover);
    html += _srOpenHour(d.open_hour);
    html += _srMinute(d.minute);
    html += _srSentiment(d.sentiment);
    html += _srFunds(d.funds);
    html += _srPlan(d.plan);
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

// ---- 市场宽度（涨跌家数比例） ----

function _srBreadth(b) {
    if (!b) return '';
    var ratio = b.red_ratio;
    var barColor = ratio >= 55 ? '#d63850' : (ratio <= 40 ? '#00b894' : '#fbbf24');
    return _srCard('<div class="card-title sr-title">📊 全市场涨跌家数（市场整体状况）</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:10px;">' +
        '<span style="font-size:13px;color:#8b8b9e;">上涨 <span style="color:#d63850;font-size:15px;font-weight:600;">' + b.rise + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">下跌 <span style="color:#00b894;font-size:15px;font-weight:600;">' + b.fall + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">平盘 <span style="color:#888;font-size:15px;font-weight:600;">' + b.flat + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">红盘率 <span style="color:' + barColor + ';font-size:15px;font-weight:600;">' + ratio.toFixed(1) + '%</span></span>' +
        '</div>' +
        '<div style="width:100%;height:10px;border-radius:5px;background:rgba(255,255,255,0.08);margin-bottom:10px;position:relative;">' +
        '<div style="width:' + ratio + '%;height:10px;border-radius:5px;background:' + barColor + ';"></div>' +
        '</div>' +
        '<div class="sr-conclusion">' + b.conclusion + '</div>');
}

// ---- 成交额温度 ----

function _srTurnover(t) {
    if (!t) return '';
    var chgCol = _srCol(t.change);
    var rows =
        '<span>当日成交额 <span style="color:#fff;font-weight:600;">' + t.today.toFixed(0) + ' 亿</span></span>' +
        '<span>昨日成交额 <span style="color:#fff;">' + t.yesterday.toFixed(0) + ' 亿</span></span>' +
        '<span>较昨日 <span style="color:' + chgCol + ';">' + _srSigned(t.change) + ' 亿 (' + _srPct(t.change_pct) + ')</span></span>';
    var bandTag = t.band === '活跃'
        ? '<span style="display:inline-block;margin-left:8px;padding:1px 8px;border-radius:3px;font-size:11px;background:rgba(214,56,80,0.15);color:#d63850;border:1px solid rgba(214,56,80,0.4);vertical-align:2px;">量能活跃（高于近期均量）</span>'
        : (t.band === '偏低' ? '<span style="display:inline-block;margin-left:8px;padding:1px 8px;border-radius:3px;font-size:11px;background:rgba(0,184,148,0.15);color:#00b894;border:1px solid rgba(0,184,148,0.4);vertical-align:2px;">量能偏低（低于近期均量）</span>' : '');
    return _srCard('<div class="card-title sr-title">🔥 两市成交额变化（市场温度）' + bandTag + '</div>' +
        (t.day ? '<div class="sr-meta">数据日期：' + t.day + '</div>' : '') +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;font-size:13px;color:#8b8b9e;margin-bottom:8px;">' + rows + '</div>' +
        '<div class="sr-conclusion">' + t.conclusion + '</div>');
}

// ---- 上证日内形态 ----

function _srMinute(m) {
    if (!m) return '';
    return _srCard('<div class="card-title sr-title">🕐 上证指数日内形态（支撑验证）</div>' +
        (m.day ? '<div class="sr-meta">数据日期：' + m.day + '</div>' : '') +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:8px;font-size:13px;color:#8b8b9e;">' +
        '<span>日内最高 <span style="color:#d63850;font-weight:600;">' + _srNum(m.high) + '</span></span>' +
        '<span>日内最低 <span style="color:#00b894;font-weight:600;">' + _srNum(m.low) + '</span>（约' + m.low_time + '）</span>' +
        '<span>自低点回升 <span style="color:' + _srCol(m.rebound) + ';font-weight:600;">' + _srPct(m.rebound) + '</span></span>' +
        '</div>' +
        '<div class="sr-conclusion">' + m.conclusion + '</div>');
}

// ---- 开盘首小时量价 ----

function _srOpenHour(m) {
    if (!m) return '';
    function _s(label, value, color) {
        return '<span class="sr-label">' + label +
            ' <span class="sr-value" style="color:' + (color || '#fff') + ';">' + value + '</span></span>';
    }
    var ratioCol = m.ratio >= 36 ? '#d63850' : (m.ratio >= 24 ? '#fbbf24' : '#00b894');
    var rows = _s('开盘一小时成交', m.open_amt.toFixed(0) + ' 亿') +
        _s('占当日成交比例', m.ratio.toFixed(0) + '%', ratioCol) +
        _s('当日累计成交', m.total_now.toFixed(0) + ' 亿') +
        (m.sh_pct !== null && m.sh_pct !== undefined
            ? _s('同期上证(对开盘)', (m.sh_pct >= 0 ? '+' : '') + m.sh_pct.toFixed(2) + '%', _srCol(m.sh_pct))
            : '');
    return _srCard('<div class="card-title sr-title">🕘 开盘首小时量价结构</div>' +
        (m.day ? '<div class="sr-meta">数据日期：' + m.day + '</div>' : '') +
        (!m.complete ? '<div style="font-size:12px;color:#fbbf24;margin-bottom:6px;">首小时尚未结束，以下为盘中实时累计</div>' : '') +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:8px;">' + rows + '</div>' +
        '<div class="sr-conclusion">' + m.conclusion + '</div>');
}

// ---- 市场情绪（涨停/跌停/连板） ----

function _srSentiment(s) {
    if (!s) return '';
    function _tag(text, color, bg) {
        return '<span class="sr-tag" style="color:' + color + ';background:' + (bg || 'transparent') + ';border:1px solid ' + color + '55;">' + text + '</span>';
    }
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
    return _srCard('<div class="card-title sr-title">🔥 市场情绪（涨停/连板结构）</div>' +
        (s.day ? '<div class="sr-meta">数据日期：' + s.day + '</div>' : '') +
        '<div style="margin-bottom:8px;line-height:2;">' + chips + '</div>' +
        '<div class="sr-conclusion">' + s.conclusion + '</div>');
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
