// 清理管理模块
class CleanupModule {
    constructor(app) {
        this.app = app;
    }
    
    async load() {
        await this.loadStorageInfo();
        await this.loadCleanupSettings();
    }
    
    async loadStorageInfo() {
        try {
            const resp = await fetch('/admin/storage/info', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                this.renderStorageInfo(data);
            }
        } catch (e) {
            console.error('Failed to load storage info:', e);
        }
    }
    
    renderStorageInfo(data) {
        // 更新存储统计
        document.getElementById('storage-uploads').textContent = this.formatSize(data.uploads_size || 0);
        document.getElementById('storage-results').textContent = this.formatSize(data.results_size || 0);
        document.getElementById('storage-cache').textContent = this.formatSize(data.cache_size || 0);
        document.getElementById('storage-total').textContent = this.formatSize(data.total_size || 0);
        
        // 更新文件数量
        document.getElementById('files-uploads').textContent = data.uploads_count || 0;
        document.getElementById('files-results').textContent = data.results_count || 0;
        document.getElementById('files-cache').textContent = data.cache_count || 0;
    }
    
    formatSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    async loadCleanupSettings() {
        try {
            const resp = await fetch('/admin/settings', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const settings = await resp.json();
                const cleanup = settings.cleanup || {};
                
                document.getElementById('cleanup-auto-enabled').checked = cleanup.auto_cleanup || false;
                document.getElementById('cleanup-interval').value = cleanup.interval_hours || 24;
                document.getElementById('cleanup-max-age').value = cleanup.max_age_days || 7;
                document.getElementById('cleanup-max-size').value = cleanup.max_size_gb || 10;
            }
        } catch (e) {
            console.error('Failed to load cleanup settings:', e);
        }
    }
    
    async saveCleanupSettings() {
        const settings = {
            cleanup: {
                auto_cleanup: document.getElementById('cleanup-auto-enabled').checked,
                interval_hours: parseInt(document.getElementById('cleanup-interval').value) || 24,
                max_age_days: parseInt(document.getElementById('cleanup-max-age').value) || 7,
                max_size_gb: parseInt(document.getElementById('cleanup-max-size').value) || 10
            }
        };
        
        try {
            const resp = await fetch('/admin/settings', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify(settings)
            });
            
            if (resp.ok) {
                alert('清理设置已保存！');
            } else {
                throw new Error('保存失败');
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
    }
    
    async cleanupUploads() {
        if (!confirm('确定要清理上传目录吗？')) return;
        await this.runCleanup('uploads');
    }
    
    async cleanupResults() {
        if (!confirm('确定要清理结果目录吗？')) return;
        await this.runCleanup('results');
    }
    
    async cleanupCache() {
        if (!confirm('确定要清理缓存目录吗？')) return;
        await this.runCleanup('cache');
    }
    
    async cleanupAll() {
        if (!confirm('确定要清理所有临时文件吗？此操作不可恢复！')) return;
        await this.runCleanup('all');
    }
    
    async runCleanup(target) {
        try {
            const resp = await fetch(`/admin/cleanup/${target}`, {
                method: 'POST',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const result = await resp.json();
                alert(`清理完成！释放空间: ${this.formatSize(result.freed_bytes || 0)}`);
                this.loadStorageInfo();
            } else {
                throw new Error('清理失败');
            }
        } catch (e) {
            alert('清理失败: ' + e.message);
        }
    }
}

window.CleanupModule = CleanupModule;
