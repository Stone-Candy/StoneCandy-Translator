// 公告管理模块
class AnnouncementModule {
    constructor(app) {
        this.app = app;
    }
    
    async load() {
        await this.loadAnnouncement();
    }
    
    async loadAnnouncement() {
        try {
            const resp = await fetch('/announcement');
            
            if (resp.ok) {
                const data = await resp.json();
                this.fillAnnouncementForm(data);
            }
        } catch (e) {
            console.error('Failed to load announcement:', e);
        }
    }
    
    fillAnnouncementForm(data) {
        document.getElementById('announcement-enabled').checked = data.enabled || false;
        document.getElementById('announcement-type').value = data.type || 'info';
        document.getElementById('announcement-message').value = data.message || '';
        
        // 更新预览
        this.updatePreview();
    }
    
    updatePreview() {
        const enabled = document.getElementById('announcement-enabled').checked;
        const type = document.getElementById('announcement-type').value;
        const message = document.getElementById('announcement-message').value;
        
        const preview = document.getElementById('announcement-preview');
        if (!preview) return;
        
        if (!enabled || !message) {
            preview.style.display = 'none';
            return;
        }
        
        const colors = {
            'info': { bg: '#dbeafe', text: '#1d4ed8', border: '#3b82f6' },
            'warning': { bg: '#fef3c7', text: '#d97706', border: '#f59e0b' },
            'error': { bg: '#fee2e2', text: '#dc2626', border: '#ef4444' }
        };
        
        const color = colors[type] || colors.info;
        preview.style.display = 'block';
        preview.style.backgroundColor = color.bg;
        preview.style.color = color.text;
        preview.style.borderLeft = `4px solid ${color.border}`;
        preview.style.padding = '12px 16px';
        preview.style.borderRadius = '6px';
        preview.style.marginTop = '16px';
        preview.textContent = message;
    }
    
    async saveAnnouncement() {
        const data = {
            enabled: document.getElementById('announcement-enabled').checked,
            type: document.getElementById('announcement-type').value,
            message: document.getElementById('announcement-message').value
        };
        
        try {
            const resp = await fetch('/admin/announcement', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify(data)
            });
            
            if (resp.ok) {
                alert('公告已保存！');
            } else {
                throw new Error('保存失败');
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
    }
    
    clearAnnouncement() {
        document.getElementById('announcement-enabled').checked = false;
        document.getElementById('announcement-message').value = '';
        this.updatePreview();
    }
}

window.AnnouncementModule = AnnouncementModule;
