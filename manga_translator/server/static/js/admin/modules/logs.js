// 系统日志模块
class LogsModule {
    constructor(app) {
        this.app = app;
        this.autoScroll = true;
        this.logLevel = 'all';
        this.sessionFilter = ''; // 会话ID过滤
        this.refreshInterval = null;
    }
    
    async load() {
        await this.loadLogs();
        // 启动自动刷新（每5秒）
        this.startAutoRefresh();
    }
    
    startAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
        }
        this.refreshInterval = setInterval(() => {
            if (this.autoScroll) {
                this.loadLogs();
            }
        }, 5000);
    }
    
    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }
    
    async loadLogs() {
        const container = document.getElementById('logs-container');
        if (!container) return;
        
        try {
            let url = `/admin/logs?level=${this.logLevel}&limit=200`;
            if (this.sessionFilter) {
                url += `&session_id=${encodeURIComponent(this.sessionFilter)}`;
            }
            
            const resp = await fetch(url, {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                this.renderLogs(data.logs || []);
            }
        } catch (e) {
            console.error('Failed to load logs:', e);
            container.innerHTML = '<div style="color:#ef4444;padding:20px;">加载日志失败</div>';
        }
    }
    
    renderLogs(logs) {
        const container = document.getElementById('logs-container');
        if (logs.length === 0) {
            container.innerHTML = '<div style="color:#6b7280;padding:20px;text-align:center;">暂无日志</div>';
            return;
        }
        
        container.innerHTML = logs.map(log => {
            const levelClass = {
                'DEBUG': 'log-debug',
                'INFO': 'log-info',
                'WARNING': 'log-warning',
                'ERROR': 'log-error',
                'CRITICAL': 'log-critical'
            }[log.level] || 'log-info';
            
            // 格式化时间戳
            let timeStr = '';
            if (log.timestamp) {
                try {
                    const date = new Date(log.timestamp);
                    timeStr = date.toLocaleString('zh-CN', {
                        hour12: false,
                        year: 'numeric',
                        month: '2-digit',
                        day: '2-digit',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit'
                    });
                } catch (e) {
                    timeStr = log.timestamp;
                }
            }
            
            // 会话ID标签
            const sessionTag = log.session_id 
                ? `<span class="log-session" title="${log.session_id}" onclick="window.adminApp?.logsModule?.filterBySession('${log.session_id}')">[${log.session_id.substring(0, 8)}]</span>` 
                : '';
            
            return `
                <div class="log-entry ${levelClass}">
                    <span class="log-time">${timeStr}</span>
                    <span class="log-level">[${log.level}]</span>
                    ${sessionTag}
                    <span class="log-message">${this.escapeHtml(log.message)}</span>
                </div>
            `;
        }).join('');
        
        if (this.autoScroll) {
            container.scrollTop = container.scrollHeight;
        }
    }
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    filterLogs(level) {
        this.logLevel = level;
        this.loadLogs();
    }
    
    filterBySession(sessionId) {
        this.sessionFilter = sessionId;
        // 更新UI显示当前过滤的会话
        const filterInput = document.getElementById('session-filter-input');
        if (filterInput) {
            filterInput.value = sessionId;
        }
        this.loadLogs();
    }
    
    clearSessionFilter() {
        this.sessionFilter = '';
        const filterInput = document.getElementById('session-filter-input');
        if (filterInput) {
            filterInput.value = '';
        }
        this.loadLogs();
    }
    
    toggleAutoScroll() {
        this.autoScroll = !this.autoScroll;
        const btn = document.getElementById('auto-scroll-btn');
        if (btn) {
            btn.textContent = this.autoScroll ? '⏸ 暂停滚动' : '▶ 自动滚动';
        }
    }
    
    async clearLogs() {
        if (!confirm('确定要清空所有日志吗？')) return;
        
        try {
            await fetch('/admin/logs/clear', {
                method: 'POST',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            this.loadLogs();
        } catch (e) {
            alert('清空失败: ' + e.message);
        }
    }
    
    async downloadLogs() {
        try {
            const resp = await fetch('/admin/logs/export', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `logs_${new Date().toISOString().slice(0,10)}.txt`;
            a.click();
            URL.revokeObjectURL(url);
        } catch (e) {
            alert('下载失败: ' + e.message);
        }
    }
    
    // 清理资源
    destroy() {
        this.stopAutoRefresh();
    }
}

window.LogsModule = LogsModule;
