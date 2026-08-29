// 服务器配置模块
class ConfigModule {
    constructor(app) {
        this.app = app;
    }
    
    async load() {
        await this.loadGroups();  // 先加载用户组列表
        await this.loadServerConfig();
        await this.loadServerFonts();
        await this.loadServerPrompts();
    }
    
    async loadGroups() {
        // 加载用户组列表，用于填充下拉框
        try {
            const resp = await fetch('/api/admin/groups', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                // API返回的是数组格式: groups: [{id, name, ...}, ...]
                this.groups = data.groups || [];
                this.populateGroupSelect();
            }
        } catch (e) {
            console.error('Failed to load groups:', e);
            this.groups = [];
        }
    }
    
    populateGroupSelect() {
        const select = document.getElementById('config-register-default-group');
        if (!select) return;
        
        // 清空现有选项
        select.innerHTML = '';
        
        // 添加用户组选项（排除admin组）
        // groups是数组格式: [{id, name, description, ...}, ...]
        for (const group of this.groups) {
            if (group.id === 'admin') continue;  // 不允许注册用户直接加入管理员组
            
            const option = document.createElement('option');
            option.value = group.id;
            option.textContent = `${group.name || group.id} (${group.id})`;
            select.appendChild(option);
        }
        
        // 如果没有可用的组，添加默认选项
        if (select.options.length === 0) {
            const option = document.createElement('option');
            option.value = 'default';
            option.textContent = '默认用户组 (default)';
            select.appendChild(option);
        }
    }
    
    async loadServerConfig() {
        try {
            const resp = await fetch('/admin/settings', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const settings = await resp.json();
                this.fillServerConfig(settings);
            }
        } catch (e) {
            console.error('Failed to load server config:', e);
        }
    }
    
    fillServerConfig(settings) {
        // 基本设置
        document.getElementById('config-server-name').value = settings.server_name || 'Manga Translator';
        document.getElementById('config-max-concurrent').value = settings.max_concurrent_tasks || 3;
        document.getElementById('config-task-timeout').value = settings.task_timeout || 300;
        
        // 注册设置（支持新旧两种格式）
        const registrationConfig = settings.registration || {};
        const allowRegister = registrationConfig.enabled || settings.allow_register || false;
        document.getElementById('config-allow-register').checked = allowRegister;
        
        // 注册默认用户组（下拉框）
        const defaultGroupSelect = document.getElementById('config-register-default-group');
        if (defaultGroupSelect && defaultGroupSelect.options.length > 0) {
            const savedGroup = registrationConfig.default_group || 'default';
            // 确保选项存在，否则选择第一个有效选项
            const hasOption = Array.from(defaultGroupSelect.options).some(opt => opt.value === savedGroup);
            if (hasOption) {
                defaultGroupSelect.value = savedGroup;
            } else {
                // 如果保存的值无效，默认选择 'default' 或第一个选项
                const defaultOption = Array.from(defaultGroupSelect.options).find(opt => opt.value === 'default');
                defaultGroupSelect.value = defaultOption ? 'default' : defaultGroupSelect.options[0].value;
            }
        }
        
        // 文件设置
        document.getElementById('config-max-file-size').value = settings.max_file_size || 10;
        document.getElementById('config-allowed-formats').value = (settings.allowed_formats || ['jpg', 'png', 'webp']).join(', ');
        document.getElementById('config-max-batch-size').value = settings.max_batch_size || 20;
    }
    
    async saveServerConfig() {
        // 获取注册默认用户组
        const defaultGroupInput = document.getElementById('config-register-default-group');
        const defaultGroup = defaultGroupInput ? defaultGroupInput.value.trim() || 'default' : 'default';
        
        const settings = {
            server_name: document.getElementById('config-server-name').value,
            max_concurrent_tasks: parseInt(document.getElementById('config-max-concurrent').value) || 3,
            task_timeout: parseInt(document.getElementById('config-task-timeout').value) || 300,
            // 使用新的注册配置结构
            registration: {
                enabled: document.getElementById('config-allow-register').checked,
                default_group: defaultGroup,
                require_approval: false
            },
            max_file_size: parseInt(document.getElementById('config-max-file-size').value) || 10,
            allowed_formats: document.getElementById('config-allowed-formats').value.split(',').map(s => s.trim()),
            max_batch_size: parseInt(document.getElementById('config-max-batch-size').value) || 20
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
                alert('服务器配置已保存！');
            } else {
                throw new Error('保存失败');
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
    }
    
    // ========== 服务器字体管理 ==========
    async loadServerFonts() {
        const container = document.getElementById('server-font-list');
        if (!container) return;
        
        try {
            const resp = await fetch('/fonts', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const fonts = await resp.json();
                this.renderServerFonts(fonts);
            }
        } catch (e) {
            container.innerHTML = '<p style="color:#ef4444;">加载失败</p>';
        }
    }
    
    renderServerFonts(fonts) {
        const container = document.getElementById('server-font-list');
        if (!container) return;
        
        if (fonts.length === 0) {
            container.innerHTML = '<p style="color:#6b7280;">暂无服务器字体</p>';
            return;
        }
        
        container.innerHTML = fonts.map(font => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:#f9fafb;border-radius:6px;">
                <span style="font-family:monospace;">${font}</span>
                <button class="btn btn-danger btn-sm" onclick="configModule.deleteServerFont('${font}')">删除</button>
            </div>
        `).join('');
    }
    
    async uploadServerFont(input) {
        const file = input.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const resp = await fetch('/upload/font', {
                method: 'POST',
                headers: { 'X-Session-Token': this.app.sessionToken },
                body: formData
            });
            
            if (resp.ok) {
                alert('字体上传成功！');
                await this.loadServerFonts();
            } else {
                const error = await resp.text();
                alert('上传失败: ' + error);
            }
        } catch (e) {
            alert('上传失败: ' + e.message);
        }
        
        input.value = '';
    }
    
    async deleteServerFont(filename) {
        if (!confirm(`确定要删除字体 "${filename}" 吗？`)) return;
        
        try {
            const resp = await fetch(`/fonts/${encodeURIComponent(filename)}`, {
                method: 'DELETE',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                alert('字体删除成功！');
                await this.loadServerFonts();
            } else {
                const error = await resp.text();
                alert('删除失败: ' + error);
            }
        } catch (e) {
            alert('删除失败: ' + e.message);
        }
    }
    
    // ========== 服务器提示词管理 ==========
    async loadServerPrompts() {
        const container = document.getElementById('server-prompt-list');
        if (!container) return;
        
        try {
            const resp = await fetch('/prompts', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const prompts = await resp.json();
                this.renderServerPrompts(prompts);
            }
        } catch (e) {
            container.innerHTML = '<p style="color:#ef4444;">加载失败</p>';
        }
    }
    
    renderServerPrompts(prompts) {
        const container = document.getElementById('server-prompt-list');
        if (!container) return;
        
        if (prompts.length === 0) {
            container.innerHTML = '<p style="color:#6b7280;">暂无服务器提示词</p>';
            return;
        }
        
        container.innerHTML = prompts.map(prompt => `
            <div style="display:flex;justify-content:space-between;align-items:center;padding:10px;background:#f9fafb;border-radius:6px;">
                <span style="font-family:monospace;">${prompt}</span>
                <div style="display:flex;gap:8px;">
                    <button class="btn btn-secondary btn-sm" onclick="configModule.viewServerPrompt('${prompt}')">查看</button>
                    <button class="btn btn-danger btn-sm" onclick="configModule.deleteServerPrompt('${prompt}')">删除</button>
                </div>
            </div>
        `).join('');
    }
    
    async viewServerPrompt(filename) {
        try {
            const resp = await fetch(`/prompts/${encodeURIComponent(filename)}`, {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (!resp.ok) {
                throw new Error('获取提示词内容失败');
            }
            
            const data = await resp.json();
            
            // 创建弹窗显示内容
            const modal = document.createElement('div');
            modal.className = 'modal-overlay';
            modal.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;';
            
            // 格式化 JSON 内容
            let formattedContent = data.content;
            try {
                const jsonObj = JSON.parse(data.content);
                formattedContent = JSON.stringify(jsonObj, null, 2);
            } catch (e) {
                // 如果不是有效的 JSON，保持原样
            }
            
            modal.innerHTML = `
                <div style="background:white;border-radius:12px;max-width:800px;width:90%;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 25px 50px -12px rgba(0,0,0,0.25);">
                    <div style="padding:20px;border-bottom:1px solid #e5e7eb;display:flex;justify-content:space-between;align-items:center;">
                        <h3 style="margin:0;font-size:18px;">提示词内容: ${filename}</h3>
                        <button onclick="this.closest('.modal-overlay').remove()" style="background:none;border:none;font-size:24px;cursor:pointer;color:#6b7280;">&times;</button>
                    </div>
                    <div style="padding:20px;overflow:auto;flex:1;">
                        <pre style="background:#f3f4f6;padding:16px;border-radius:8px;overflow:auto;margin:0;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-all;">${this.escapeHtml(formattedContent)}</pre>
                    </div>
                    <div style="padding:16px 20px;border-top:1px solid #e5e7eb;text-align:right;">
                        <button class="btn btn-primary" onclick="this.closest('.modal-overlay').remove()">关闭</button>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // 点击背景关闭
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.remove();
            });
        } catch (e) {
            alert('查看失败: ' + e.message);
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    async uploadServerPrompt(input) {
        const file = input.files[0];
        if (!file) return;
        
        const formData = new FormData();
        formData.append('file', file);
        
        try {
            const resp = await fetch('/upload/prompt', {
                method: 'POST',
                headers: { 'X-Session-Token': this.app.sessionToken },
                body: formData
            });
            
            if (resp.ok) {
                alert('提示词上传成功！');
                await this.loadServerPrompts();
            } else {
                const error = await resp.text();
                alert('上传失败: ' + error);
            }
        } catch (e) {
            alert('上传失败: ' + e.message);
        }
        
        input.value = '';
    }
    
    async deleteServerPrompt(filename) {
        if (!confirm(`确定要删除提示词 "${filename}" 吗？`)) return;
        
        try {
            const resp = await fetch(`/prompts/${encodeURIComponent(filename)}`, {
                method: 'DELETE',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                alert('提示词删除成功！');
                await this.loadServerPrompts();
            } else {
                const error = await resp.text();
                alert('删除失败: ' + error);
            }
        } catch (e) {
            alert('删除失败: ' + e.message);
        }
    }
}

window.ConfigModule = ConfigModule;
