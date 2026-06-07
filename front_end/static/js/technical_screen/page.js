// ==================== 技术选股页面 ====================

var _techPollTimer = null;
var _segData = [];
var _curMarketKey = null;

function _onMarketSelect() {
    var key = document.getElementById('techMarket').value;
    _curMarketKey = key;

    // 切市场 → 清掉旧市场的筛选结果、轮询、两种状态提示
    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
    document.getElementById('techScreenResult').innerHTML = '';
    document.getElementById('techMarketStatus').textContent = '';
    document.getElementById('techScreenStatus').textContent = '';

    if (!key) return;

    // 正在加载的市场切回来时不覆盖状态，轮询还在更新进度条
    if (_initPollTimer && _loadingMarketKey === key) {
        document.getElementById('techLoadBtn').textContent = '终止';
        return;
    }

    // 恢复已存在的轮询（页面刷新后重新识别）
    if (_loadingMarketKey === key) {
        document.getElementById('techLoadBtn').textContent = '终止';
        document.getElementById('techClearBtn').disabled = true;
        return;
    }

    // 切到其他市场，按钮改回"加载"
    document.getElementById('techLoadBtn').textContent = '加载';

    var item = _segData.find(function(s){return s.key === key;});
    var status = document.getElementById('techMarketStatus');
    if (item && item.synced) {
        status.textContent = item.label + '：' + item.kline_count + ' 只';
        status.style.color = '#4ade80';
        document.getElementById('techScreenBtn').disabled = false;
    } else {
        status.textContent = item ? '请先加载 ' + item.label + ' 市场数据' : '未加载';
        status.style.color = '#f97316';
        document.getElementById('techScreenBtn').disabled = true;
    }
}

function _refreshSegments() {
    return fetch('/api/market-db/segments').then(function(r){return r.json()}).then(function(data){
        _segData = data.segments;
        var initRunning = data.init_running;
        var initSegKey = data.init_seg_key;
        var initPhase = data.init_phase;

        var sel = document.getElementById('techMarket');
        var oldVal = _curMarketKey || sel.value;
        sel.innerHTML = '<option value="">-- 选择市场 --</option>';
        data.segments.forEach(function(s){
            var opt = document.createElement('option');
            opt.value = s.key;
            // 正在初始化/加载中的市场，虽未完成但列表已写入，显示特殊标记
            var loading = initRunning && initSegKey === s.key;
            if (loading) {
                opt.textContent = '\u23f3 ' + s.label + ' (加载中...)';
            } else {
                opt.textContent = s.synced ? ('\u2713 ' + s.label) : s.label;
            }
            sel.appendChild(opt);
        });

        // 如果正在加载，恢复加载状态并重启进度条轮询
        if (initRunning && initSegKey) {
            _loadingMarketKey = initSegKey;
            var btn = document.getElementById('techLoadBtn');
            btn.textContent = '终止';
            btn.disabled = false;
            // 清库按钮保持可点击——点清库会自动终止加载
            document.getElementById('techClearBtn').disabled = false;
            _startInitPolling();
        }

        var found = data.segments.find(function(s){return s.key === oldVal;});
        if (found) {
            sel.value = found.key;
            _onMarketSelect();
        } else {
            var firstSynced = data.segments.find(function(s){return s.synced;});
            if (firstSynced) {
                sel.value = firstSynced.key;
                _onMarketSelect();
            }
        }
    }).catch(function(){});
}

_refreshSegments();

var _initPollTimer = null;
var _loadingMarketKey = null;

function _pollInitStatus() {
    var status = document.getElementById('techMarketStatus');
    fetch('/api/market-db/init/status')
        .then(function(r){return r.json()})
        .then(function(s){
            var btn = document.getElementById('techLoadBtn');
            var currentMarket = document.getElementById('techMarket').value;
            var loadingKey = _loadingMarketKey;
            if (s.phase === 'cancelled') {
                clearInterval(_initPollTimer); _initPollTimer = null;
                _loadingMarketKey = null;
                btn.textContent = '加载';
                btn.disabled = false;
                document.getElementById('techClearBtn').disabled = false;
                if (currentMarket === loadingKey) {
                    _refreshSegments().then(function() {
                        status.textContent = '加载已被终止';
                        status.style.color = '#f97316';
                    });
                } else {
                    _refreshSegments();
                }
                return;
            }
            if (s.cancel) {
                if (currentMarket === loadingKey) {
                    status.textContent = '正在终止加载（数据将自动清除）...';
                    status.style.color = '#fbbf24';
                }
                return;
            }
            if (s.running) {
                if (currentMarket === loadingKey) {
                    var bar = '', w = 20, f = Math.floor(w * s.done / s.total);
                    for (var i=0;i<w;i++) bar += i<=f ? '\u2588' : '\u2591';
                    status.textContent = s.phase === 'list' ? '拉取列表...' : ('K线 ' + bar + ' ' + s.done + '/' + s.total);
                }
            } else if (s.phase === 'error') {
                clearInterval(_initPollTimer); _initPollTimer = null;
                _loadingMarketKey = null;
                btn.textContent = '加载';
                btn.disabled = false;
                document.getElementById('techClearBtn').disabled = false;
                _refreshSegments().then(function() {
                    status.textContent = s.error || '加载失败';
                    status.style.color = '#ef4444';
                });
            } else {
                clearInterval(_initPollTimer); _initPollTimer = null;
                _loadingMarketKey = null;
                btn.textContent = '加载';
                if (currentMarket === loadingKey) {
                    document.getElementById('techScreenBtn').disabled = false;
                    _refreshSegments().then(function() {
                        status.textContent = '加载完成，共 ' + s.total + ' 只';
                        status.style.color = '#4ade80';
                    });
                } else {
                    _refreshSegments();
                }
            }
        });
}

function _startInitPolling() {
    if (_initPollTimer) clearInterval(_initPollTimer);
    _initPollTimer = setInterval(_pollInitStatus, 1000);
}

function loadMarket() {
    var sel = document.getElementById('techMarket');
    var key = sel.value;
    if (!key) { alert('请先选择市场'); return; }
    var status = document.getElementById('techMarketStatus');
    var btn = document.getElementById('techLoadBtn');

    // 当前市场正在加载 → 点按钮是"终止"
    if (_initPollTimer && _loadingMarketKey === key) {
        cancelLoad();
        return;
    }

    // 正在加载其他市场：放请求到后端，后端会拒绝，不杀轮询
    if (_initPollTimer && _loadingMarketKey && _loadingMarketKey !== key) {
        fetch('/api/market-db/init/' + key, { method: 'POST' })
            .then(function(r){return r.json()})
            .then(function(){
                var label = _segData.find(function(s){return s.key === _loadingMarketKey;});
                status.textContent = (label ? label.label : _loadingMarketKey) + ' 正在加载中，请等待完成后再加载其他市场';
                status.style.color = '#f97316';
            })
            .catch(function(e){
                status.textContent = '请求出错: ' + e.message;
                status.style.color = '#e94560';
            });
        return;
    }

    // 正常加载流程
    if (_initPollTimer) clearInterval(_initPollTimer);
    _loadingMarketKey = key;
    btn.textContent = '终止';
    status.textContent = '正在拉取列表...';
    status.style.color = '#fbbf24';
    fetch('/api/market-db/init/' + key, { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '已存在';
                status.style.color = '#e94560';
                btn.textContent = '加载';
                _loadingMarketKey = null;
                return;
            }
            _initPollTimer = setInterval(_pollInitStatus, 1000);
        })
        .catch(function(e){
            status.textContent = '请求出错: ' + e.message;
            status.style.color = '#e94560';
            btn.textContent = '加载';
            _loadingMarketKey = null;
        });
}

function cancelLoad() {
    var segItem = _segData.find(function(s){return s.key === _loadingMarketKey;});
    var segLabel = segItem ? segItem.label : _loadingMarketKey;
    if (!confirm('确定要终止【' + segLabel + '】数据加载吗？')) return;
    var status = document.getElementById('techMarketStatus');
    var btn = document.getElementById('techLoadBtn');
    btn.disabled = true;
    status.textContent = '正在终止...';
    status.style.color = '#fbbf24';
    fetch('/api/market-db/init/cancel', { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '终止失败';
                status.style.color = '#e94560';
                btn.disabled = false;
                return;
            }
            // 轮询会检测到 cancelled 状态，自动清理
        })
        .catch(function(e){
            status.textContent = '终止出错: ' + e.message;
            status.style.color = '#e94560';
            btn.disabled = false;
        });
}

function clearMarket() {
    var sel = document.getElementById('techMarket');
    var key = sel.value;
    if (!key) { alert('请先选择市场'); return; }
    var label = sel.options[sel.selectedIndex].textContent.replace(/^[✓✔] /, '');
    if (!confirm('确定要清除【' + label + '】的全部数据吗？\n\n此操作不可撤销，将删除该市场的股票列表、K线数据及同步记录。')) {
        return;
    }

    // 正在加载的市场 → 终止加载即可（取消时已回滚数据），不需要额外清库
    if (_loadingMarketKey === key) {
        if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
        document.getElementById('techScreenResult').innerHTML = '';
        var loadBtnLocal = document.getElementById('techLoadBtn');
        var clearBtnLocal = document.getElementById('techClearBtn');
        var screenBtnLocal = document.getElementById('techScreenBtn');
        loadBtnLocal.disabled = true;
        clearBtnLocal.disabled = true;
        screenBtnLocal.disabled = true;
        var statusEl = document.getElementById('techMarketStatus');
        statusEl.textContent = '正在终止加载...';
        statusEl.style.color = '#fbbf24';
        fetch('/api/market-db/init/cancel', { method: 'POST' })
            .then(function(r){return r.json()})
            .catch(function(){});
        // 轮询会检测到 cancel → cancelled，自动显示状态 + 清理
        return;
    }

    var status = document.getElementById('techMarketStatus');
    var loadBtn = document.getElementById('techLoadBtn');
    var clearBtn = document.getElementById('techClearBtn');
    var screenBtn = document.getElementById('techScreenBtn');

    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }

    status.textContent = '正在清除数据...';
    status.style.color = '#fbbf24';
    loadBtn.disabled = true;
    clearBtn.disabled = true;
    screenBtn.disabled = true;
    document.getElementById('techScreenResult').innerHTML = '';

    fetch('/api/market-db/clear/' + key, { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '清除失败';
                status.style.color = '#e94560';
                loadBtn.disabled = false;
                clearBtn.disabled = false;
                return;
            }
            status.textContent = data.message || '数据已清除';
            status.style.color = '#4ade80';
            loadBtn.disabled = false;
            clearBtn.disabled = false;
            // 刷新下拉选项
            _refreshSegments().then(function() {
                // 清除后当前市场不再有数据，重置选中状态
                sel.value = '';
                _curMarketKey = null;
                status.textContent = (data.message || '数据已清除') + '，请重新加载';
                status.style.color = '#f97316';
            });
        })
        .catch(function(e){
            status.textContent = '清除出错: ' + e.message;
            status.style.color = '#e94560';
            loadBtn.disabled = false;
            clearBtn.disabled = false;
        });
}

function _techRenderTable(data) {
    var html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>价格</th><th>评分</th><th>通道上轨</th><th>通道下轨</th><th>位置%</th><th>通道宽%</th><th>量比</th></tr></thead><tbody>';
    data.forEach(function(s) {
        var d = s.detail || {};
        var c = String(s.code);
        var mk = (/^(6|9|5|11)/.test(c)) ? '1' : '0';
        html += '<tr>' +
            '<td><span style="color:#888;">' + s.code + '</span></td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + s.code + '\',\'' + mk + '\',\'' + s.name + '\')">' + s.name + '</span></td>' +
            '<td><span style="color:#ddd;">' + s.price + '</span></td>' +
            '<td><span style="color:#fbbf24;font-weight:bold;">' + s.score + '</span></td>' +
            '<td><span style="color:#ef5350;">' + d.upper + '</span></td>' +
            '<td><span style="color:#26a69a;">' + d.lower + '</span></td>' +
            '<td><span style="color:#ddd;">' + d.pos + '%</span></td>' +
            '<td><span style="color:#ddd;">' + d.channel_width_pct + '%</span></td>' +
            '<td><span style="color:#ddd;">' + d.vol_ratio + '</span></td>' +
        '</tr>';
    });
    html += '</tbody></table></div>';
    document.getElementById('techScreenResult').innerHTML = html;
}

async function runTechScreen() {
    var status = document.getElementById('techScreenStatus');
    var btn = document.getElementById('techScreenBtn');
    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
    status.textContent = '启动扫描...';
    status.style.color = '#fbbf24';
    btn.disabled = true;
    try {
        var mkt = document.getElementById('techMarket').value;
        var res = await fetch('/api/technical/ascending-channel?market=' + encodeURIComponent(mkt), { method: 'POST' });
        var data = await res.json();
        if (!data.success) { status.textContent = data.error; status.style.color = '#e94560'; btn.disabled = false; return; }
        _techPollTimer = setInterval(async function() {
            try {
                var pr = await fetch('/api/technical/ascending-channel/status');
                var pd = await pr.json();
                if (pd.running) {
                    status.textContent = '扫描中... ' + pd.done + '/' + pd.total + ' | 已找到 ' + pd.results.length + ' 只';
                    _techRenderTable(pd.results);
                } else {
                    clearInterval(_techPollTimer); _techPollTimer = null;
                    status.textContent = '已完成，共找到 ' + pd.results.length + ' 只';
                    status.style.color = '#4ade80';
                    btn.disabled = false;
                    if (pd.results.length > 0) _techRenderTable(pd.results);
                }
            } catch(e) {
                clearInterval(_techPollTimer); _techPollTimer = null;
                status.textContent = '状态查询出错';
                status.style.color = '#e94560';
                btn.disabled = false;
            }
        }, 2000);
    } catch(e) {
        status.textContent = '扫描出错: ' + e.message;
        status.style.color = '#e94560';
        btn.disabled = false;
    }
}
