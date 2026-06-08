// ==================== 公共接口 ====================

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

// 股票类型判断
function getStockType(code, market) {
    const c = (code || '').toString();
    const m = (market || '').toString();
    if (m === '1' || m === '2') {
        if (/^688/.test(c)) return '科创';
        if (/^60[0135]/.test(c)) return '沪A';
        if (/^51|^56|^58/.test(c)) return '沪ETF';
        if (/^5/.test(c)) return '沪基';
        if (/^11/.test(c)) return '沪债';
        return '沪市';
    }
    if (m === '0') {
        if (/^30[01]/.test(c)) return '创业';
        if (/^00[0-3]|^002|^003/.test(c)) return '深A';
        if (/^159/.test(c)) return '深ETF';
        if (/^1[6-8]/.test(c)) return '深基';
        if (/^12/.test(c)) return '深债';
        return '深市';
    }
    if (m === '90') return '北交所';
    if (m === '116') return '港股';
    if (m === '106') return '美股';
    if (/^1[0-5]/.test(m) && parseInt(m) >= 105) return '境外';
    return '';
}
