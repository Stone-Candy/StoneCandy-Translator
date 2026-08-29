// 会话管理模块
class SessionsModule {
    constructor(app) {
        this.app = app;
    }
    
    async load() {
        await this.loadSessions();
    }
    
    async loadSessions() {
        const tbody = document.getElementById('sessions-table-body');
        if (!tbody) return;
        
        try {
            const resp = await fetch('/sessions/?all=true', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                this.renderSessions(data.sessions || []);
            }
        } catch (e) {
            console.error('Failed to load sessions:', e);
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#ef4444;">加载失败</td></tr>';
        }
    }
    
    renderSessions(sessions) {
        const tbody = document.getElementById('sessions-table-body');
        
        if (sessions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;">暂无活跃会话</td></tr>';
            return;
        }
        
        tbody.innerHTML = sessions.map(session => {
            const isCurrentSession = session.token === this.app.sessionToken;
            
            return `
                <tr ${isCurrentSession ? 'style="background:#f0fdf4;"' : ''}>
                    <td>
                        <strong>${session.username}</strong>
                        ${isCurrentSession ? '<span class="badge badge-success" style="margin-left:8px;">当前</span>' : ''}
                    </td>
                    <td><code style="background:#f3f4f6;padding:2px 6px;border-radius:4px;">${(session.token || '').slice(0,12)}...</code></td>
                    <td>${session.ip || '-'}</td>
                    <td>${session.user_agent ? session.user_agent.slice(0, 30) + '...' : '-'}</td>
                    <td>${session.created_at ? new Date(session.created_at).toLocaleString() : '-'}</td>
                    <td>
                        ${!isCurrentSession ? 
                            `<button class="btn btn-danger btn-sm" onclick="sessionsModule.revokeSession('${session.token}')">撤销</button>` :
                            '<span style="color:#6b7280;">-</span>'
                        }
                    </td>
                </tr>
            `;
        }).join('');
    }
    
    async revokeSession(token) {
        if (!confirm('确定要撤销此会话吗？该用户将被强制登出。')) return;
        
        try {
            const resp = await fetch(`/sessions/${token}`, {
                method: 'DELETE',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                this.loadSessions();
            } else {
                throw new Error('撤销失败');
            }
        } catch (e) {
            alert('撤销失败: ' + e.message);
        }
    }
    
    async revokeAllSessions() {
        if (!confirm('确定要撤销所有其他会话吗？所有其他用户将被强制登出。')) return;
        
        try {
            const resp = await fetch('/sessions/revoke-all', {
                method: 'POST',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                alert('已撤销所有其他会话');
                this.loadSessions();
            } else {
                throw new Error('操作失败');
            }
        } catch (e) {
            alert('操作失败: ' + e.message);
        }
    }
}

window.SessionsModule = SessionsModule;
