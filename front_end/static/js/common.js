// ==================== 公共接口 ====================

// 判断是否为场内基金（ETF+LOF），价格显示3位小数
function isETF(code, market) {
    var type = getStockType(code, market);
    return type.indexOf('ETF') >= 0 || type.indexOf('LOF') >= 0;
}

// 清除所有本地缓存数据
function clearAllCaches() {
    try {
        localStorage.removeItem('kl_cache');
        localStorage.removeItem('stockCache');
        localStorage.removeItem('watchlistCache');
        localStorage.removeItem('abnormal-calc-history-v1');
        localStorage.removeItem('stock-search-history-v1');
    } catch(e) {}
    // 刷新页面上的列表（从已空的缓存重新加载）
    try { loadPickedStocks(); } catch(e) {}
    try { loadWatchlistStocks(); } catch(e) {}
}

// ---- 交易日历缓存（由后端 /api/is-trading-day 填充，排除节假日） ----
var _tradingDayResult = null;  // {date: '2026-06-19', is_trading_day: true/false}

function initTradingDayCache() {
    fetch('/api/is-trading-day')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            _tradingDayResult = data;
        })
        .catch(function() {
            _tradingDayResult = null;  // 降级：仅用周末判断
        });
}

// ---- 判断当日是否是交易日 ----
// market: '0','1','2','90'=A股, '116'=港股, '106'=美股
function isTradingDay(market) {
    if (market === '106') {
        // 美股：判断美东时间是否在周一至周五
        var now = new Date();
        var year = now.getUTCFullYear();
        var mar1 = new Date(Date.UTC(year, 2, 1));
        var dstStartDay = 7 + (7 - mar1.getUTCDay());
        if (dstStartDay > 14) dstStartDay -= 7;
        var dstStart = Date.UTC(year, 2, dstStartDay, 7, 0, 0);
        var nov1 = new Date(Date.UTC(year, 10, 1));
        var dstEndDay = 7 - nov1.getUTCDay();
        if (dstEndDay <= 0) dstEndDay += 7;
        var dstEnd = Date.UTC(year, 10, dstEndDay, 6, 0, 0);
        var isDST = now.getTime() >= dstStart && now.getTime() < dstEnd;
        var offset = isDST ? -4 : -5;
        var et = new Date(now.getTime() + offset * 3600000);
        var etDay = et.getUTCDay();
        return etDay !== 0 && etDay !== 6;
    }
    // A股 / 港股：先排除周末
    var now = new Date();
    var day = now.getDay();
    if (day === 0 || day === 6) return false;
    // 港股：周末已排除，其余为交易日
    if (market === '116') return true;
    // A股：叠加后端交易日历（排除法定节假日）
    // 缓存未就绪时不注入，避免在节假日误显示今日K线
    if (_tradingDayResult == null) return false;
    var todayStr = now.getFullYear() + '-' +
                   String(now.getMonth() + 1).padStart(2, '0') + '-' +
                   String(now.getDate()).padStart(2, '0');
    if (_tradingDayResult.date === todayStr) {
        return _tradingDayResult.is_trading_day;
    }
    return false;
}

// ---- 各市场交易时间判断 ----
// market: '0','1','2','90'=A股, '116'=港股, '106'=美股
function isMarketTradingTime(market) {
    if (market === '106') {
        // 美股：美东时间 9:30-16:00，周一至周五
        var now = new Date();
        var year = now.getUTCFullYear();
        // 夏令时：3月第二个周日 2:00 AM ET → 7:00 UTC
        var mar1 = new Date(Date.UTC(year, 2, 1));
        var dstStartDay = 7 + (7 - mar1.getUTCDay());
        if (dstStartDay > 14) dstStartDay -= 7;
        var dstStart = Date.UTC(year, 2, dstStartDay, 7, 0, 0);
        // 冬令时：11月第一个周日 2:00 AM ET → 6:00 UTC
        var nov1 = new Date(Date.UTC(year, 10, 1));
        var dstEndDay = 7 - nov1.getUTCDay();
        if (dstEndDay <= 0) dstEndDay += 7;
        var dstEnd = Date.UTC(year, 10, dstEndDay, 6, 0, 0);
        var isDST = now.getTime() >= dstStart && now.getTime() < dstEnd;
        var offset = isDST ? -4 : -5;
        var et = new Date(now.getTime() + offset * 3600000);
        var etDay = et.getUTCDay();
        if (etDay === 0 || etDay === 6) return false;
        var etMin = et.getUTCHours() * 60 + et.getUTCMinutes();
        return etMin >= 570 && etMin <= 960; // 9:30=570, 16:00=960
    }
    if (market === '116') {
        // 港股：HKT 9:30-12:00, 13:00-16:00，周一至周五
        var now = new Date();
        if (now.getDay() === 0 || now.getDay() === 6) return false;
        var hkMin = now.getHours() * 60 + now.getMinutes();
        return (hkMin >= 570 && hkMin <= 720) || (hkMin >= 780 && hkMin <= 960);
    }
    // A股
    return isInTradingHours();
}

function isInTradingHours() {
    const now = new Date();
    const day = now.getDay(); // 0=周日, 6=周六
    if (day === 0 || day === 6) return false;
    const t = now.getHours() * 60 + now.getMinutes();
    return (t >= 555 && t <= 695) || (t >= 775 && t <= 905);
    // 09:15-11:35, 12:55-15:05
}

// 与后端 is_market_opened 对齐：只要市场已开盘（>=9:30）就为 true
// 用于判断是否可以用实时行情补全今日K线（收盘后同花顺日K延迟更新时需要）
function isMarketOpened(market) {
    if (market === '116') {
        // 港股: >= 9:30, 周一至周五
        const now = new Date();
        if (now.getDay() === 0 || now.getDay() === 6) return false;
        return now.getHours() * 60 + now.getMinutes() >= 570;
    }
    if (market === '106') {
        // 美股: 北京时间 >= 21:30
        const now = new Date();
        if (now.getDay() === 0 || now.getDay() === 6) return false;
        return now.getHours() * 60 + now.getMinutes() >= 1290;
    }
    // A股: >= 9:30, 周一至周五
    const now = new Date();
    if (now.getDay() === 0 || now.getDay() === 6) return false;
    return now.getHours() * 60 + now.getMinutes() >= 570;
}

// 股票类型判断（代码前缀决定类型，market 仅兜底）
function getStockType(code, market) {
    const c = (code || '').toString();
    const m = (market || '').toString();

    // 港股/美股/境外 — market 决定，代码前缀无区分能力
    if (m === '116') return '港股';
    if (m === '106') return '美股';
    if (/^1[0-5]/.test(m) && parseInt(m) >= 105) return '境外';

    // A 股：代码前缀确定类型
    if (/^[48]|^92/.test(c)) return '北交';
    if (/^688/.test(c)) return '科创';
    if (/^60[0135]/.test(c)) return '沪A';
    if (/^30[01]/.test(c)) return '创业';
    if (/^00[0-3]/.test(c)) return '深A';
    if (/^51|^56|^58/.test(c)) return '沪ETF';
    if (/^5/.test(c)) return '沪LOF';
    if (/^11/.test(c)) return '沪债';
    if (/^159/.test(c)) return '深ETF';
    if (/^1[6-8]/.test(c)) return '深LOF';
    if (/^12/.test(c)) return '深债';

    // 代码没匹配到，按 market 兜底
    if (m === '1') return '沪市';
    if (m === '2') return '科创';
    if (m === '0') return '深市';
    return '';
}

