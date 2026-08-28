// ==================== 用户管理 ====================

function loadUserManageList() {
    var container = document.getElementById('userManageContent');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">加载中...</div>';

    fetch('/api/auth/users')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderUserManageList(data.data);
            } else {
                container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">' + (data.error || '获取失败') + '</div>';
            }
        })
        .catch(function() {
            container.innerHTML = '<div style="text-align:center;color:#e94560;padding:40px;">网络错误</div>';
        });
}

function _formatTime(ts) {
    if (!ts) return '-';
    var d = new Date(ts * 1000);
    function pad(n) { return n < 10 ? '0' + n : n; }
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) +
        ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}

function renderUserManageList(users) {
    var container = document.getElementById('userManageContent');
    if (!container) return;

    if (!users || users.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">暂无用户</div>';
        return;
    }

    var html = '<div class="data-table"><table><thead><tr>' +
        '<th>ID</th><th>用户名</th><th>用户类型</th><th>创建时间</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < users.length; i++) {
        var u = users[i];
        var typeName = getUserTypeName(u.user_type);
        html += '<tr>' +
            '<td style="color:#888;">' + u.id + '</td>' +
            '<td>' + u.username + '</td>' +
            '<td>' + (typeName || u.user_type) + '</td>' +
            '<td style="white-space:nowrap;color:#888;">' + _formatTime(u.create_time) + '</td>' +
            '</tr>';
    }
    html += '</tbody></table></div>';
    container.innerHTML = html;
}
