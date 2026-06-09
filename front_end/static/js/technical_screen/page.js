// ==================== 技术选股页面 ====================

var _techPollTimer = null;
var _segData = [];
var _curMarketKey = null;
var _strategies = [];
var _curStrategyKeys = [];  // 多选策略 key 数组

function _loadStrategies() {
    return fetch('/api/technical/strategies').then(function(r){return r.json()}).then(function(data){
        _strategies = data.data || [];
        _renderStrategyList();
    }).catch(function(){});
}

function _renderStrategyList() {
    var list = document.getElementById('techStrategyList');
    var html = '';
    _strategies.forEach(function(s) {
        var selected = _curStrategyKeys.indexOf(s.key) >= 0;
        var style = selected ? ' style="background:#fbbf24;color:#000;"' : ' style="background:#1a1a2e;border:1px solid #0f3460;color:#ccc;cursor:pointer;"';
        html += '<span' + style + ' onclick="_toggleStrategy(\'' + s.key + '\')" title="' + s.desc + '">' + s.name + '</span>';
    });
    list.innerHTML = html;
    _renderSelectedTags();
}

function _renderSelectedTags() {
    var el = document.getElementById('techStrategyTags');
    var html = '';
    _curStrategyKeys.forEach(function(key) {
        var s = _strategies.find(function(x){return x.key === key;});
        var name = s ? s.name : key;
        html += '<span class="strategy-tag" style="display:inline-flex;align-items:center;padding:2px 8px;margin:2px;background:#0f3460;border-radius:3px;font-size:12px;color:#fbbf24;">'
            + name
            + '<span style="cursor:pointer;margin-left:4px;color:#888;font-size:11px;" onclick="event.stopPropagation();_removeStrategy(\'' + key + '\');">\u00d7</span>'
            + '</span>';
    });
    el.innerHTML = html;
}

function _toggleStrategy(key) {
    var idx = _curStrategyKeys.indexOf(key);
    if (idx >= 0) {
        _curStrategyKeys.splice(idx, 1);
    } else {
        _curStrategyKeys.push(key);
    }
    document.getElementById('techScreenStatus').textContent = '';
    _renderStrategyList();
    _updateStrategyDisplay();
}

function _removeStrategy(key) {
    var idx = _curStrategyKeys.indexOf(key);
    if (idx >= 0) {
        _curStrategyKeys.splice(idx, 1);
    }
    document.getElementById('techScreenStatus').textContent = '';
    _renderStrategyList();
    _updateStrategyDisplay();
}

function _updateStrategyDisplay() {
    var el = document.getElementById('techStrategyName');
    if (_curStrategyKeys.length > 0) {
        el.style.display = 'block';
        el.innerHTML = '<span style="font-size:11px;color:#8b8b9e;">已选策略（按先后顺序依次筛选）：</span>'
            + _curStrategyKeys.map(function(key, i) {
                var s = _strategies.find(function(x){return x.key === key;});
                var name = s ? s.name : key;
                return '<span style="color:#fbbf24;">' + (i + 1) + '. ' + name + '</span>';
            }).join('<span style="color:#555;margin:0 4px;">→</span>');
    } else {
        el.style.display = 'none';
        el.innerHTML = '';
    }
}

function _selectStrategy(key) {
    _curStrategyKeys = [key];
    var el = document.getElementById('techStrategyName');
    var s = _strategies.find(function(x){return x.key === key;});
    if (!s) return;
    el.innerHTML = '<span>' + s.name + '</span><span style="cursor:pointer;margin-left:4px;color:#888;font-size:12px;" onclick="event.stopPropagation();_clearStrategy();">\u00d7</span>';
    el.style.display = 'inline-flex';
    el.style.alignItems = 'center';
    document.getElementById('techStrategyPicker').style.display = 'none';
    document.getElementById('techScreenStatus').textContent = '';
    _renderStrategyList();
}

function _clearStrategy() {
    _curStrategyKeys = [];
    var el = document.getElementById('techStrategyName');
    el.style.display = 'none';
    el.innerHTML = '';
    document.getElementById('techStrategyTags').innerHTML = '';
    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
    document.getElementById('techScreenResult').innerHTML = '';
    document.getElementById('techScreenStatus').textContent = '';
}

function toggleStrategyPicker() {
    var picker = document.getElementById('techStrategyPicker');
    var isVisible = picker.style.display === 'block';
    picker.style.display = isVisible ? 'none' : 'block';
    if (!isVisible) _renderStrategyList();
}

function _onMarketSelect() {
    var key = document.getElementById('techMarket').value;
    _curMarketKey = key;

    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
    document.getElementById('techScreenResult').innerHTML = '';
    document.getElementById('techMarketStatus').textContent = '';
    document.getElementById('techScreenStatus').textContent = '';

    if (!key) return;

    // 正在加载的市场切回来时不覆盖状态
    if (_initPollTimer && _loadingMarketKey === key) {
        document.getElementById('techLoadBtn').textContent = '终止';
        return;
    }
    // 正在更新的市场切回来时不覆盖状态
    if (_updatePollTimer && _updatingMarketKey === key) {
        document.getElementById('techUpdateBtn').textContent = '取消';
        return;
    }

    // 切到其他市场，恢复按钮
    document.getElementById('techLoadBtn').textContent = '加载';
    document.getElementById('techLoadBtn').disabled = false;
    document.getElementById('techUpdateBtn').textContent = '更新';
    document.getElementById('techUpdateBtn').disabled = false;

    var item = _segData.find(function(s){return s.key === key;});
    var status = document.getElementById('techMarketStatus');
    if (item && item.synced) {
        var tsInfo = item.sync_ts ? ' (更新于 ' + item.sync_ts + ')' : '';
        status.textContent = item.label + '：' + item.kline_count + ' 只' + tsInfo;
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
        var initTaskType = data.init_task_type;

        var sel = document.getElementById('techMarket');
        var oldVal = _curMarketKey || sel.value;
        sel.innerHTML = '<option value="">-- 选择市场 --</option>';
        data.segments.forEach(function(s){
            var opt = document.createElement('option');
            opt.value = s.key;
            var loading = initRunning && initSegKey === s.key;
            if (loading) {
                var verb = initTaskType === 'update' ? '更新中' : '加载中';
                opt.textContent = '\u23f3 ' + s.label + ' (' + verb + '...)';
            } else {
                opt.textContent = s.synced ? ('\u2713 ' + s.label) : s.label;
            }
            sel.appendChild(opt);
        });

        // 恢复运行中任务的状态
        if (initRunning && initSegKey) {
            if (initTaskType === 'update') {
                _updatingMarketKey = initSegKey;
                document.getElementById('techUpdateBtn').textContent = '取消';
                document.getElementById('techUpdateBtn').disabled = false;
                document.getElementById('techLoadBtn').disabled = true;
                _startUpdatePolling();
            } else {
                _loadingMarketKey = initSegKey;
                document.getElementById('techLoadBtn').textContent = '终止';
                document.getElementById('techLoadBtn').disabled = false;
                document.getElementById('techUpdateBtn').disabled = true;
                _startInitPolling();
            }
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
_loadStrategies();

// =========== 加载（初始化）相关 ===========

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
                document.getElementById('techUpdateBtn').disabled = false;
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
                document.getElementById('techUpdateBtn').disabled = false;
                _refreshSegments().then(function() {
                    status.textContent = s.error || '加载失败';
                    status.style.color = '#ef4444';
                });
            } else {
                clearInterval(_initPollTimer); _initPollTimer = null;
                _loadingMarketKey = null;
                btn.textContent = '加载';
                if (currentMarket === loadingKey) {
                    status.textContent = '加载完成，共 ' + s.total + ' 只';
                    status.style.color = '#4ade80';
                    document.getElementById('techScreenBtn').disabled = false;
                }
                _refreshSegments();
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

    // 正在加载其他市场
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

    // 正在更新时不能加载
    if (_updatePollTimer && _updatingMarketKey) {
        status.textContent = '请先等待更新完成或取消更新';
        status.style.color = '#f97316';
        return;
    }

    // 正常加载流程
    if (_initPollTimer) clearInterval(_initPollTimer);
    _loadingMarketKey = key;
    btn.textContent = '终止';
    document.getElementById('techUpdateBtn').disabled = true;
    status.textContent = '正在拉取列表...';
    status.style.color = '#fbbf24';
    fetch('/api/market-db/init/' + key, { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '已存在';
                status.style.color = '#e94560';
                btn.textContent = '加载';
                document.getElementById('techUpdateBtn').disabled = false;
                _loadingMarketKey = null;
                return;
            }
            _initPollTimer = setInterval(_pollInitStatus, 1000);
        })
        .catch(function(e){
            status.textContent = '请求出错: ' + e.message;
            status.style.color = '#e94560';
            btn.textContent = '加载';
            document.getElementById('techUpdateBtn').disabled = false;
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
        })
        .catch(function(e){
            status.textContent = '终止出错: ' + e.message;
            status.style.color = '#e94560';
            btn.disabled = false;
        });
}

// =========== 更新相关 ===========

var _updatePollTimer = null;
var _updatingMarketKey = null;

function _pollUpdateStatus() {
    var status = document.getElementById('techMarketStatus');
    fetch('/api/market-db/init/status')
        .then(function(r){return r.json()})
        .then(function(s){
            var btn = document.getElementById('techUpdateBtn');
            var currentMarket = document.getElementById('techMarket').value;
            var updatingKey = _updatingMarketKey;
            if (s.phase === 'cancelled') {
                clearInterval(_updatePollTimer); _updatePollTimer = null;
                _updatingMarketKey = null;
                btn.textContent = '更新';
                btn.disabled = false;
                document.getElementById('techLoadBtn').disabled = false;
                if (currentMarket === updatingKey) {
                    _refreshSegments().then(function() {
                        status.textContent = '更新已被终止';
                        status.style.color = '#f97316';
                    });
                } else {
                    _refreshSegments();
                }
                return;
            }
            if (s.cancel) {
                if (currentMarket === updatingKey) {
                    status.textContent = '正在终止更新...';
                    status.style.color = '#fbbf24';
                }
                return;
            }
            if (s.running) {
                if (currentMarket === updatingKey) {
                    var bar = '', w = 20, f = Math.floor(w * s.done / s.total);
                    for (var i=0;i<w;i++) bar += i<=f ? '\u2588' : '\u2591';
                    status.textContent = s.phase === 'list' ? '拉取列表...' : ('更新K线 ' + bar + ' ' + s.done + '/' + s.total);
                }
            } else if (s.phase === 'error') {
                clearInterval(_updatePollTimer); _updatePollTimer = null;
                _updatingMarketKey = null;
                btn.textContent = '更新';
                btn.disabled = false;
                document.getElementById('techLoadBtn').disabled = false;
                _refreshSegments().then(function() {
                    status.textContent = s.error || '更新失败';
                    status.style.color = '#ef4444';
                });
            } else {
                clearInterval(_updatePollTimer); _updatePollTimer = null;
                _updatingMarketKey = null;
                btn.textContent = '更新';
                if (currentMarket === updatingKey) {
                    status.textContent = '更新完成，共 ' + s.total + ' 只';
                    status.style.color = '#4ade80';
                    document.getElementById('techScreenBtn').disabled = false;
                }
                _refreshSegments();
            }
        });
}

function _startUpdatePolling() {
    if (_updatePollTimer) clearInterval(_updatePollTimer);
    _updatePollTimer = setInterval(_pollUpdateStatus, 1000);
}

function updateMarket() {
    var sel = document.getElementById('techMarket');
    var key = sel.value;
    if (!key) { alert('请先选择市场'); return; }
    var status = document.getElementById('techMarketStatus');
    var btn = document.getElementById('techUpdateBtn');

    // 当前市场正在更新 → 点按钮是"取消"
    if (_updatePollTimer && _updatingMarketKey === key) {
        cancelUpdate();
        return;
    }

    // 正在更新其他市场
    if (_updatePollTimer && _updatingMarketKey && _updatingMarketKey !== key) {
        status.textContent = '其他市场正在更新中，请等待完成';
        status.style.color = '#f97316';
        return;
    }

    // 正在加载时不能更新
    if (_initPollTimer && _loadingMarketKey) {
        status.textContent = '请先等待加载完成或终止加载';
        status.style.color = '#f97316';
        return;
    }

    // 正常更新流程
    if (_updatePollTimer) clearInterval(_updatePollTimer);
    _updatingMarketKey = key;
    btn.textContent = '取消';
    document.getElementById('techLoadBtn').disabled = true;
    status.textContent = '正在检查更新...';
    status.style.color = '#fbbf24';
    fetch('/api/market-db/update/' + key, { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '更新失败';
                status.style.color = data.error === '数据已是最新，无需更新' ? '#4ade80' : '#e94560';
                btn.textContent = '更新';
                document.getElementById('techLoadBtn').disabled = false;
                _updatingMarketKey = null;
                return;
            }
            _updatePollTimer = setInterval(_pollUpdateStatus, 1000);
        })
        .catch(function(e){
            status.textContent = '请求出错: ' + e.message;
            status.style.color = '#e94560';
            btn.textContent = '更新';
            document.getElementById('techLoadBtn').disabled = false;
            _updatingMarketKey = null;
        });
}

function cancelUpdate() {
    var segItem = _segData.find(function(s){return s.key === _updatingMarketKey;});
    var segLabel = segItem ? segItem.label : _updatingMarketKey;
    if (!confirm('确定要取消【' + segLabel + '】数据更新吗？')) return;
    var status = document.getElementById('techMarketStatus');
    var btn = document.getElementById('techUpdateBtn');
    btn.disabled = true;
    status.textContent = '正在取消更新...';
    status.style.color = '#fbbf24';
    fetch('/api/market-db/init/cancel', { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '取消失败';
                status.style.color = '#e94560';
                btn.disabled = false;
                return;
            }
        })
        .catch(function(e){
            status.textContent = '取消出错: ' + e.message;
            status.style.color = '#e94560';
            btn.disabled = false;
        });
}

// =========== 清库 ===========

function clearMarket() {
    var sel = document.getElementById('techMarket');
    var key = sel.value;
    if (!key) { alert('请先选择市场'); return; }
    var label = sel.options[sel.selectedIndex].textContent.replace(/^[✓✔⏳] /, '').replace(/ \(.*\)/, '');
    if (!confirm('确定要清除【' + label + '】的全部数据吗？\n\n此操作不可撤销，将删除该市场的股票列表、K线数据及同步记录。')) {
        return;
    }

    // 正在加载的市场 → 终止加载
    if (_loadingMarketKey === key) {
        if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
        document.getElementById('techScreenResult').innerHTML = '';
        var loadBtnLocal = document.getElementById('techLoadBtn');
        var clearBtnLocal = document.getElementById('techClearBtn');
        var screenBtnLocal = document.getElementById('techScreenBtn');
        var updateBtnLocal = document.getElementById('techUpdateBtn');
        loadBtnLocal.disabled = true;
        clearBtnLocal.disabled = true;
        screenBtnLocal.disabled = true;
        updateBtnLocal.disabled = true;
        var statusEl = document.getElementById('techMarketStatus');
        statusEl.textContent = '正在终止加载...';
        statusEl.style.color = '#fbbf24';
        fetch('/api/market-db/init/cancel', { method: 'POST' })
            .then(function(r){return r.json()})
            .catch(function(){});
        return;
    }

    // 正在更新的市场 → 取消更新
    if (_updatingMarketKey === key) {
        if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
        document.getElementById('techScreenResult').innerHTML = '';
        var loadBtn2 = document.getElementById('techLoadBtn');
        var clearBtn2 = document.getElementById('techClearBtn');
        var screenBtn2 = document.getElementById('techScreenBtn');
        var updateBtn2 = document.getElementById('techUpdateBtn');
        loadBtn2.disabled = true;
        clearBtn2.disabled = true;
        screenBtn2.disabled = true;
        updateBtn2.disabled = true;
        var statusEl2 = document.getElementById('techMarketStatus');
        statusEl2.textContent = '正在取消更新...';
        statusEl2.style.color = '#fbbf24';
        fetch('/api/market-db/init/cancel', { method: 'POST' })
            .then(function(r){return r.json()})
            .then(function() {
                // 取消完成后再清库
                _doClear(key, sel);
            })
            .catch(function(){});
        return;
    }

    _doClear(key, sel);
}

function _doClear(key, sel) {
    var status = document.getElementById('techMarketStatus');
    var loadBtn = document.getElementById('techLoadBtn');
    var clearBtn = document.getElementById('techClearBtn');
    var screenBtn = document.getElementById('techScreenBtn');
    var updateBtn = document.getElementById('techUpdateBtn');

    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }

    status.textContent = '正在清除数据...';
    status.style.color = '#fbbf24';
    loadBtn.disabled = true;
    clearBtn.disabled = true;
    screenBtn.disabled = true;
    updateBtn.disabled = true;
    document.getElementById('techScreenResult').innerHTML = '';

    fetch('/api/market-db/clear/' + key, { method: 'POST' })
        .then(function(r){return r.json()})
        .then(function(data){
            if (!data.success) {
                status.textContent = data.error || '清除失败';
                status.style.color = '#e94560';
                loadBtn.disabled = false;
                clearBtn.disabled = false;
                updateBtn.disabled = false;
                return;
            }
            status.textContent = data.message || '数据已清除';
            status.style.color = '#4ade80';
            loadBtn.disabled = false;
            clearBtn.disabled = false;
            updateBtn.disabled = false;
            _refreshSegments().then(function() {
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
            updateBtn.disabled = false;
        });
}

// =========== 市场标签（已移除北交所） ===========

var _marketLabels = {
    'sh_main': '沪A', 'sz_main': '深A', 'gem': '创业板', 'star': '科创板',
    'sh_etf': '沪ETF', 'sz_etf': '深ETF', 'hk_main': '港股', 'us_main': '美股'
};

async function _techRenderTable(results) {
    if (!results || results.length === 0) {
        document.getElementById('techScreenResult').innerHTML = '';
        return;
    }
    var quotes = {};
    try {
        var secids = results.map(function(s) { return s.market + '.' + s.code; }).join(',');
        var qr = await fetch('/api/stock-quotes?secids=' + encodeURIComponent(secids));
        var qd = await qr.json();
        if (qd.success) quotes = qd.data;
    } catch(e) {}

    var rowsHtml = '';
    results.forEach(function(s) {
        var c = String(s.code);
        var mk = s.market || '';
        var popupMk = (/^(6|9|5|11)/.test(c)) ? '1' : '0';
        var q = quotes[mk + '.' + c] || {};
        var price = q.price || s.price || '-';
        rowsHtml += '<tr>' +
            '<td><span style="color:#888;">' + c + '</span></td>' +
            '<td><span style="color:#fff;cursor:pointer;text-decoration:underline;" onclick="KlinePopup.open(\'' + c + '\',\'' + popupMk + '\',\'' + s.name + '\')">' + s.name + '</span></td>' +
            '<td><span style="color:#8b8b9e;">' + (_marketLabels[mk] || mk) + '</span></td>' +
            '<td><span style="color:#ddd;">' + price + '</span></td>' +
            '<td><span style="color:#fbbf24;font-weight:bold;">' + s.score + '</span></td>' +
        '</tr>';
    });
    var html = '<div class="data-table"><table><thead><tr><th>代码</th><th>名称</th><th>市场</th><th>最新价</th><th>评分</th></tr></thead><tbody>' + rowsHtml + '</tbody></table></div>';
    document.getElementById('techScreenResult').innerHTML = html;
}

async function runTechScreen() {
    var status = document.getElementById('techScreenStatus');
    var btn = document.getElementById('techScreenBtn');
    if (_curStrategyKeys.length === 0) { status.textContent = '请先选择策略'; status.style.color = '#e94560'; return; }
    if (_techPollTimer) { clearInterval(_techPollTimer); _techPollTimer = null; }
    status.textContent = '启动扫描...';
    status.style.color = '#fbbf24';
    btn.disabled = true;
    try {
        var mkt = document.getElementById('techMarket').value;
        var strategyParam = _curStrategyKeys.join(',');
        var res = await fetch('/api/technical/ascending-channel?market=' + encodeURIComponent(mkt) + '&strategy=' + encodeURIComponent(strategyParam), { method: 'POST' });
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
