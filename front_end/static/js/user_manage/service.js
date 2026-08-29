// ==================== 用户管理 ====================

function loadUserManageList() {
    var container = document.getElementById('userManageContent');
    if (!container) return;

    container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">加载中...</div>';

    fetch('/api/auth/users')
        .then(function(res) { return res.json(); })
        .then(function(data) {
            if (data.success) {
                renderUserManageList(data.data, data.current_user_type);
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

// 生成操作链接：登录用户权限类型大于目标用户时可点击，否则置灰
function _userActionLink(canOperate, text, onclick) {
    if (canOperate) {
        return '<span style="color:#4d9fff;cursor:pointer;margin-right:14px;" onclick="' + onclick + '">' + text + '</span>';
    }
    return '<span style="color:#555;cursor:not-allowed;margin-right:14px;" title="权限不足">' + text + '</span>';
}

function renderUserManageList(users, currentUserType) {
    var container = document.getElementById('userManageContent');
    if (!container) return;

    if (!users || users.length === 0) {
        container.innerHTML = '<div style="text-align:center;color:#888;padding:40px;">暂无用户</div>';
        return;
    }

    var html = '<div class="data-table"><table><thead><tr>' +
        '<th>ID</th><th>用户名</th><th>用户类型</th><th>创建时间</th><th>操作</th>' +
        '</tr></thead><tbody>';

    for (var i = 0; i < users.length; i++) {
        var u = users[i];
        var typeName = getUserTypeName(u.user_type);
        var canOperate = currentUserType > u.user_type;
        html += '<tr>' +
            '<td style="color:#888;">' + u.id + '</td>' +
            '<td>' + u.username + '</td>' +
            '<td>' + (typeName || u.user_type) + '</td>' +
            '<td style="white-space:nowrap;color:#888;">' + _formatTime(u.create_time) + '</td>' +
            '<td style="white-space:nowrap;">' +
            _userActionLink(canOperate, '修改密码', "showResetPwdModal(" + u.id + ",'" + u.username + "')") +
            _userActionLink(canOperate, '删除', "deleteUser(" + u.id + ",'" + u.username + "')") +
            '</td>' +
            '</tr>';
    }
    html += '</tbody></table></div>';
    container.innerHTML = html;
}

// ---- 重置密码 ----
var _resetPwdTargetId = null;

function showResetPwdModal(userId, username) {
    _resetPwdTargetId = userId;
    document.getElementById('resetPwdTarget').innerText = username;
    document.getElementById('resetNewPassword').value = '';
    document.getElementById('resetConfirmPassword').value = '';
    document.getElementById('resetPwdMsg').innerText = '';
    document.getElementById('resetPwdModal').style.display = 'flex';
    document.getElementById('resetNewPassword').focus();
}

function closeResetPwdModal() {
    document.getElementById('resetPwdModal').style.display = 'none';
    _resetPwdTargetId = null;
}

function submitResetPwd() {
    var newPwd = document.getElementById('resetNewPassword').value;
    var confirmPwd = document.getElementById('resetConfirmPassword').value;
    var msgEl = document.getElementById('resetPwdMsg');
    var error = validatePassword(newPwd);
    if (error) { msgEl.innerText = error; return; }
    if (newPwd !== confirmPwd) { msgEl.innerText = '两次输入的新密码不一致'; return; }

    var body = new URLSearchParams();
    body.append('new_password', newPwd);
    fetch('/api/auth/users/' + _resetPwdTargetId + '/password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString()
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.success) {
            closeResetPwdModal();
            alert(data.message || '密码修改成功');
        } else {
            msgEl.innerText = data.error || '修改失败';
        }
    })
    .catch(function() {
        msgEl.innerText = '网络错误，请稍后重试';
    });
}

// ---- 删除用户 ----
function deleteUser(userId, username) {
    if (!confirm('确定删除用户「' + username + '」吗？此操作不可恢复！')) return;
    fetch('/api/auth/users/' + userId + '/delete', { method: 'POST' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.success) {
                alert(data.message || '删除成功');
                loadUserManageList();
            } else {
                alert(data.error || '删除失败');
            }
        })
        .catch(function() {
            alert('网络错误，请稍后重试');
        });
}
