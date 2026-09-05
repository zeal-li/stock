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
        metaEl.innerHTML = '更新于 <span style="color:#ccc;">' + d.update_time + '</span> · 市场状态：<span style="color:#ccc;">' + d.market_status + '</span>';
    }
    var html = '';
    html += _srIndexTable(d.indices);
    html += _srSynergy(d.synergy);
    html += _srLevels(d.levels);
    html += _srBreadth(d.breadth);
    html += _srTurnover(d.turnover);
    html += _srMinute(d.minute);
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
    return '<div class="index-card" style="padding:16px;margin-bottom:10px;">' + bodyHtml + '</div>';
}

// ---- 主要指数行情 ----

function _srIndexTable(indices) {
    if (!indices || !indices.length) return '';
    var ths = ['指数', '最新价', '涨跌幅', '涨跌额', '今开', '最高', '最低', '20日压力', '20日支撑', 'MA20', '60日分位'];
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
            '<td style="color:#fbbf24;">' + _srNum(it.high_20) + '</td>' +
            '<td style="color:#60a5fa;">' + _srNum(it.low_20) + '</td>' +
            '<td>' + _srNum(it.ma20) + '</td>' +
            '<td>' + (it.pos_pct !== null && it.pos_pct !== undefined ? it.pos_pct.toFixed(0) + '%' : '--') + '</td>' +
            '</tr>';
    });

    var note = '<div style="font-size:11px;color:#666;margin-top:8px;line-height:1.7;">' +
        '20日压力/支撑 = 近20个交易日最高/最低价（含当日），黄色为上方压力、蓝色为下方支撑参考；' +
        '60日分位 = 现价位于近60日最高最低价区间的百分位（越低越接近区间底部）。' +
        '</div>';
    return _srCard('<div class="card-title" style="margin-bottom:10px;">📈 主要指数复盘</div>' +
        '<div class="sector-table-wrap"><table class="sector-fund-table">' + head + '<tbody>' + rows + '</tbody></table></div>' + note);
}

// ---- 指数同频共振 / 分化 ----

function _srSynergy(s) {
    if (!s) return '';
    var chips = '';
    (s.up || []).forEach(function(n) {
        chips += '<span style="display:inline-block;padding:1px 8px;border-radius:3px;font-size:12px;color:#d63850;border:1px solid rgba(214,56,80,0.4);">▲ ' + n + '</span>';
    });
    (s.down || []).forEach(function(n) {
        chips += '<span style="display:inline-block;padding:1px 8px;border-radius:3px;font-size:12px;color:#00b894;border:1px solid rgba(0,184,148,0.4);">▼ ' + n + '</span>';
    });
    (s.flat || []).forEach(function(n) {
        chips += '<span style="display:inline-block;padding:1px 8px;border-radius:3px;font-size:12px;color:#888;border:1px solid rgba(136,136,136,0.35);">— ' + n + '</span>';
    });
    var tagColor = s.mode.indexOf('普涨') >= 0 ? '#d63850' : (s.mode.indexOf('普跌') >= 0 ? '#00b894' : '#fbbf24');
    return _srCard('<div class="card-title" style="margin-bottom:6px;">🔀 指数同频共振 / 分化研判</div>' +
        '<div style="margin-bottom:8px;"><span style="display:inline-block;padding:2px 10px;border-radius:3px;background:' + tagColor + ';color:#fff;font-size:12px;font-weight:600;">' + s.mode + '</span></div>' +
        (chips ? '<div style="margin-bottom:8px;display:flex;flex-wrap:wrap;gap:6px;">' + chips + '</div>' : '') +
        '<div style="font-size:13px;color:#ccc;line-height:1.9;">' + s.summary + '</div>');
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
    return _srCard('<div class="card-title" style="margin-bottom:10px;">🎯 关键点位 · 压力位 / 支撑位</div>' + items);
}

// ---- 市场宽度（涨跌家数比例） ----

function _srBreadth(b) {
    if (!b) return '';
    var ratio = b.red_ratio;
    var barColor = ratio >= 55 ? '#d63850' : (ratio <= 40 ? '#00b894' : '#fbbf24');
    return _srCard('<div class="card-title" style="margin-bottom:10px;">📊 全市场涨跌家数（市场整体状况）</div>' +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:10px;">' +
        '<span style="font-size:13px;color:#8b8b9e;">上涨 <span style="color:#d63850;font-size:15px;font-weight:600;">' + b.rise + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">下跌 <span style="color:#00b894;font-size:15px;font-weight:600;">' + b.fall + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">平盘 <span style="color:#888;font-size:15px;font-weight:600;">' + b.flat + '</span> 家</span>' +
        '<span style="font-size:13px;color:#8b8b9e;">红盘率 <span style="color:' + barColor + ';font-size:15px;font-weight:600;">' + ratio.toFixed(1) + '%</span></span>' +
        '</div>' +
        '<div style="width:100%;height:10px;border-radius:5px;background:rgba(255,255,255,0.08);margin-bottom:10px;position:relative;">' +
        '<div style="width:' + ratio + '%;height:10px;border-radius:5px;background:' + barColor + ';"></div>' +
        '</div>' +
        '<div style="font-size:13px;color:#ccc;line-height:1.9;">' + b.conclusion + '</div>');
}

// ---- 成交额温度 ----

function _srTurnover(t) {
    if (!t) return '';
    var chgCol = _srCol(t.change);
    var rows =
        '<span>当日成交额 <span style="color:#fff;font-weight:600;">' + t.today.toFixed(0) + ' 亿</span></span>' +
        '<span>昨日成交额 <span style="color:#fff;">' + t.yesterday.toFixed(0) + ' 亿</span></span>' +
        '<span>较昨日 <span style="color:' + chgCol + ';">' + _srSigned(t.change) + ' 亿 (' + _srPct(t.change_pct) + ')</span></span>';
    return _srCard('<div class="card-title" style="margin-bottom:10px;">🔥 两市成交额变化（市场温度）</div>' +
        (t.day ? '<div style="font-size:11px;color:#666;margin-bottom:6px;">数据日期：' + t.day + '</div>' : '') +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;font-size:13px;color:#8b8b9e;margin-bottom:8px;">' + rows + '</div>' +
        '<div style="font-size:13px;color:#ccc;line-height:1.9;">' + t.conclusion + '</div>');
}

// ---- 上证日内形态 ----

function _srMinute(m) {
    if (!m) return '';
    return _srCard('<div class="card-title" style="margin-bottom:10px;">🕐 上证指数日内形态（支撑验证）</div>' +
        (m.day ? '<div style="font-size:11px;color:#666;margin-bottom:6px;">数据日期：' + m.day + '</div>' : '') +
        '<div style="display:flex;flex-wrap:wrap;gap:20px;margin-bottom:8px;font-size:13px;color:#8b8b9e;">' +
        '<span>日内最高 <span style="color:#d63850;font-weight:600;">' + _srNum(m.high) + '</span></span>' +
        '<span>日内最低 <span style="color:#00b894;font-weight:600;">' + _srNum(m.low) + '</span>（约' + m.low_time + '）</span>' +
        '<span>自低点回升 <span style="color:' + _srCol(m.rebound) + ';font-weight:600;">' + _srPct(m.rebound) + '</span></span>' +
        '</div>' +
        '<div style="font-size:13px;color:#ccc;line-height:1.9;">' + m.conclusion + '</div>');
}
