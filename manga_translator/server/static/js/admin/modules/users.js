// 用户管理模块
class UsersModule {
    constructor(app) {
        this.app = app;
        this.users = [];
        this.groups = [];
        this.presets = [];
    }

    async load() {
        await Promise.all([
            this.loadUsers(),
            this.loadGroups(),
            this.loadPresets()
        ]);
    }

    async loadUsers() {
        try {
            const resp = await fetch('/api/admin/users', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            if (resp.ok) {
                const data = await resp.json();
                this.users = Array.isArray(data) ? data : (data.users || []);
                this.renderUsersTable(this.users);
            }
        } catch (e) {
            console.error('Failed to load users:', e);
        }
    }

    async loadGroups() {
        try {
            const resp = await fetch('/api/admin/groups', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            if (resp.ok) {
                const data = await resp.json();
                this.groups = data.groups || [];
            }
        } catch (e) {
            console.error('Failed to load groups:', e);
        }
    }

    async loadPresets() {
        try {
            const resp = await fetch('/api/admin/presets', {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            if (resp.ok) {
                const data = await resp.json();
                this.presets = data.presets || [];
            }
        } catch (e) {
            console.error('Failed to load presets:', e);
        }
    }

    renderUsersTable(users) {
        const tbody = document.getElementById('users-table-body');
        if (!tbody) return;

        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;">暂无用户</td></tr>';
            return;
        }

        tbody.innerHTML = users.map(user => {
            const presetName = user.default_preset_id
                ? (this.presets.find(p => p.id === user.default_preset_id)?.name || '自定义')
                : '继承用户组';
            return `
            <tr>
                <td><strong>${this.escapeHtml(user.username)}</strong></td>
                <td><span class="badge ${user.role === 'admin' ? 'badge-danger' : 'badge-info'}">${user.role || 'user'}</span></td>
                <td>${this.escapeHtml(user.group || 'default')}</td>
                <td><span class="badge badge-secondary" title="API密钥预设">${this.escapeHtml(presetName)}</span></td>
                <td><span class="badge ${user.active !== false ? 'badge-success' : 'badge-warning'}">${user.active !== false ? '活跃' : '禁用'}</span></td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="usersModule.editUser('${user.username}')">编辑</button>
                    ${user.role !== 'admin' ? `<button class="btn btn-danger btn-sm" onclick="usersModule.deleteUser('${user.username}')">删除</button>` : ''}
                </td>
            </tr>
        `}).join('');
    }

    editUser(username) {
        const user = this.users.find(u => u.username === username);
        if (!user) {
            alert('用户不存在');
            return;
        }
        
        this.currentEditUser = user;
        
        // 显示基本信息编辑模态框
        const groupOptions = this.groups.map(g =>
            `<option value="${g.id}" ${g.id === user.group ? 'selected' : ''}>${this.escapeHtml(g.name)}</option>`
        ).join('');

        const presetOptions = this.presets.map(p =>
            `<option value="${p.id}" ${p.id === user.default_preset_id ? 'selected' : ''}>${this.escapeHtml(p.name)}</option>`
        ).join('');

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal" style="max-width:500px;background:#fff;border-radius:8px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
                <div class="modal-header" style="background:linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);color:#fff;border-radius:8px 8px 0 0;">
                    <h3 style="margin:0;">✏️ 编辑用户: ${this.escapeHtml(username)}</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()" style="color:#fff;">×</button>
                </div>
                <div class="modal-body" style="padding:24px;background:#fff;">
                    <div class="form-group">
                        <label class="form-label">新密码</label>
                        <input type="password" class="form-input" id="edit-user-password" placeholder="留空则不修改密码">
                        <small style="color:#6b7280;font-size:12px;">如需修改密码，请输入新密码（至少6位）</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">用户组</label>
                        <select class="form-select" id="edit-user-group" style="width:100%;">
                            ${groupOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">API密钥预设</label>
                        <select class="form-select" id="edit-user-preset" style="width:100%;">
                            <option value="" ${!user.default_preset_id ? 'selected' : ''}>继承用户组设置</option>
                            ${presetOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">角色</label>
                        <select class="form-select" id="edit-user-role" style="width:100%;">
                            <option value="user" ${user.role !== 'admin' ? 'selected' : ''}>普通用户</option>
                            <option value="admin" ${user.role === 'admin' ? 'selected' : ''}>管理员</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label" style="display:flex;align-items:center;gap:8px;">
                            <input type="checkbox" id="edit-user-active" ${user.active !== false ? 'checked' : ''}>
                            账户启用
                        </label>
                    </div>
                    <hr style="margin:16px 0;border:none;border-top:1px solid #e5e7eb;">
                    <button class="btn btn-secondary" style="width:100%;" onclick="usersModule.openPermissionEditor('${username}')">
                        ⚙️ 编辑权限配置（翻译器、参数限制等）
                    </button>
                </div>
                <div class="modal-footer" style="background:#f9fafb;border-radius:0 0 8px 8px;">
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">取消</button>
                    <button class="btn btn-primary" onclick="usersModule.saveUserBasicInfo('${username}')" style="background:linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);border:none;">💾 保存</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }
    
    async saveUserBasicInfo(username) {
        const password = document.getElementById('edit-user-password')?.value;
        const group = document.getElementById('edit-user-group')?.value;
        const role = document.getElementById('edit-user-role')?.value;
        const defaultPresetId = document.getElementById('edit-user-preset')?.value || null;
        const active = document.getElementById('edit-user-active')?.checked;

        // 验证密码长度（如果填写了）
        if (password && password.length < 6) {
            alert('密码至少需要6位');
            return;
        }

        try {
            const updateData = {
                group: group,
                role: role,
                default_preset_id: defaultPresetId,
                is_active: active
            };
            
            // 只有填写了密码才更新
            if (password) {
                updateData.password = password;
            }

            const resp = await fetch(`/api/admin/users/${username}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify(updateData)
            });

            if (resp.ok) {
                document.querySelector('.modal-overlay')?.remove();
                alert('用户信息已保存！');
                this.loadUsers();
            } else {
                const err = await resp.json();
                alert('保存失败: ' + (err.detail || '未知错误'));
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
        this.currentEditUser = null;
    }
    
    openPermissionEditor(username) {
        const user = this.users.find(u => u.username === username);
        if (!user) {
            alert('用户不存在');
            return;
        }
        
        // 关闭基本信息模态框
        document.querySelector('.modal-overlay')?.remove();
        
        this.currentEditUser = user;

        // 使用权限编辑器
        const editor = new PermissionEditor({
            title: `编辑用户权限: ${username}`,
            mode: 'user',
            sessionToken: this.app.sessionToken,
            onSave: (config) => this.saveUserConfig(username, config),
            onCancel: () => { this.currentEditUser = null; }
        });

        // 构建用户配置（包含翻译器和工作流白名单/黑名单）
        const userConfig = {
            ...user.parameter_config || {},
            allowed_translators: user.permissions?.allowed_translators || ['*'],
            denied_translators: user.permissions?.denied_translators || [],
            allowed_ocr: user.permissions?.allowed_ocr || ['*'],
            denied_ocr: user.permissions?.denied_ocr || [],
            allowed_colorizers: user.permissions?.allowed_colorizers || ['*'],
            denied_colorizers: user.permissions?.denied_colorizers || [],
            allowed_renderers: user.permissions?.allowed_renderers || ['*'],
            denied_renderers: user.permissions?.denied_renderers || [],
            allowed_workflows: user.permissions?.allowed_workflows || ['*'],
            denied_workflows: user.permissions?.denied_workflows || []
        };
        // 添加预设ID
        if (user.default_preset_id) {
            userConfig._meta = userConfig._meta || {};
            userConfig._meta.default_preset_id = user.default_preset_id;
        }

        // 获取用户组配置作为基础
        const userGroup = this.groups.find(g => g.id === user.group);
        const groupConfig = {
            ...userGroup?.parameter_config || {},
            allowed_translators: userGroup?.allowed_translators || ['*'],
            denied_translators: userGroup?.denied_translators || [],
            allowed_ocr: userGroup?.allowed_ocr || ['*'],
            denied_ocr: userGroup?.denied_ocr || [],
            allowed_colorizers: userGroup?.allowed_colorizers || ['*'],
            denied_colorizers: userGroup?.denied_colorizers || [],
            allowed_renderers: userGroup?.allowed_renderers || ['*'],
            denied_renderers: userGroup?.denied_renderers || [],
            allowed_workflows: userGroup?.allowed_workflows || ['*'],
            denied_workflows: userGroup?.denied_workflows || []
        };
        
        // 用户组的parameter_config作为上级配置（用于显示继承的禁用状态）
        // 注意：禁用配置可能嵌套在 parameter_config.parameter_config 中
        let parentParamConfig = {};
        if (userGroup?.parameter_config) {
            // 检查是否有嵌套的 parameter_config（禁用配置）
            if (userGroup.parameter_config.parameter_config) {
                parentParamConfig = userGroup.parameter_config.parameter_config;
            } else {
                // 旧格式：直接遍历查找 disabled 字段
                for (const [key, value] of Object.entries(userGroup.parameter_config)) {
                    if (typeof value === 'object' && value !== null && value.disabled !== undefined) {
                        parentParamConfig[key] = value;
                    }
                }
            }
        }
        
        // 用户组的翻译器和工作流配置作为上级配置
        const parentFeatureConfig = {
            allowed_translators: userGroup?.allowed_translators || ['*'],
            denied_translators: userGroup?.denied_translators || [],
            allowed_ocr: userGroup?.allowed_ocr || ['*'],
            denied_ocr: userGroup?.denied_ocr || [],
            allowed_colorizers: userGroup?.allowed_colorizers || ['*'],
            denied_colorizers: userGroup?.denied_colorizers || [],
            allowed_renderers: userGroup?.allowed_renderers || ['*'],
            denied_renderers: userGroup?.denied_renderers || [],
            allowed_workflows: userGroup?.allowed_workflows || ['*'],
            denied_workflows: userGroup?.denied_workflows || []
        };

        // 传递用户组名称
        const groupName = userGroup?.name || user.group || '默认';
        editor.show(userConfig, groupConfig, parentParamConfig, parentFeatureConfig, groupName);
    }
    
    async saveUserConfig(username, config) {
        // 提取预设ID
        const defaultPresetId = config._meta?.default_preset_id || null;
        
        // 提取参数白名单和黑名单
        const allowedParams = config.allowed_parameters || [];
        const deniedParams = config.denied_parameters || [];
        
        // 提取翻译器白名单和黑名单
        const allowedTranslators = config.allowed_translators || ['*'];
        const deniedTranslators = config.denied_translators || [];

        // 提取 OCR / 上色 / 渲染白名单和黑名单
        const allowedOcr = config.allowed_ocr || ['*'];
        const deniedOcr = config.denied_ocr || [];
        const allowedColorizers = config.allowed_colorizers || ['*'];
        const deniedColorizers = config.denied_colorizers || [];
        const allowedRenderers = config.allowed_renderers || ['*'];
        const deniedRenderers = config.denied_renderers || [];
        
        // 提取工作流白名单和黑名单
        const allowedWorkflows = config.allowed_workflows || ['*'];
        const deniedWorkflows = config.denied_workflows || [];
        
        // 清理config
        const paramConfig = { ...config };
        delete paramConfig._meta;
        delete paramConfig.allowed_parameters;
        delete paramConfig.denied_parameters;
        delete paramConfig.allowed_translators;
        delete paramConfig.denied_translators;
        delete paramConfig.allowed_ocr;
        delete paramConfig.denied_ocr;
        delete paramConfig.allowed_colorizers;
        delete paramConfig.denied_colorizers;
        delete paramConfig.allowed_renderers;
        delete paramConfig.denied_renderers;
        delete paramConfig.allowed_workflows;
        delete paramConfig.denied_workflows;

        try {
            // 1. 更新用户基本信息和预设
            const resp = await fetch(`/api/admin/users/${username}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify({
                    parameter_config: paramConfig,
                    default_preset_id: defaultPresetId
                })
            });
            
            // 2. 更新权限（参数、翻译器、工作流的白名单/黑名单）
            const permResp = await fetch(`/api/admin/users/${username}/permissions`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify({
                    allowed_parameters: allowedParams.length > 0 ? allowedParams : ['*'],
                    denied_parameters: deniedParams,
                    allowed_translators: allowedTranslators,
                    denied_translators: deniedTranslators,
                    allowed_ocr: allowedOcr,
                    denied_ocr: deniedOcr,
                    allowed_colorizers: allowedColorizers,
                    denied_colorizers: deniedColorizers,
                    allowed_renderers: allowedRenderers,
                    denied_renderers: deniedRenderers,
                    allowed_workflows: allowedWorkflows,
                    denied_workflows: deniedWorkflows
                })
            });
            
            if (!permResp.ok) {
                const err = await permResp.json();
                console.warn('权限更新失败:', err);
            }

            if (resp.ok) {
                alert('用户配置已保存！');
                this.loadUsers();
            } else {
                const err = await resp.json();
                alert('保存失败: ' + (err.detail || '未知错误'));
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
        this.currentEditUser = null;
    }

    async saveUser(username) {
        const group = document.getElementById('edit-user-group')?.value;
        const role = document.getElementById('edit-user-role')?.value;
        const defaultPresetId = document.getElementById('edit-user-preset')?.value || null;
        const active = document.getElementById('edit-user-active')?.checked;

        try {
            const resp = await fetch(`/api/admin/users/${username}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify({
                    group: group,
                    role: role,
                    default_preset_id: defaultPresetId,
                    active: active
                })
            });

            if (resp.ok) {
                document.querySelector('.modal-overlay')?.remove();
                alert('用户信息已保存！');
                this.loadUsers();
            } else {
                const err = await resp.json();
                alert('保存失败: ' + (err.detail || '未知错误'));
            }
        } catch (e) {
            alert('保存失败: ' + e.message);
        }
    }

    async deleteUser(username) {
        if (!confirm(`确定删除用户 "${username}"?`)) return;

        try {
            const resp = await fetch(`/api/admin/users/${username}`, {
                method: 'DELETE',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });

            if (resp.ok) {
                alert('用户已删除');
                this.loadUsers();
            } else {
                const err = await resp.json();
                alert('删除失败: ' + (err.detail || '未知错误'));
            }
        } catch (e) {
            alert('删除失败: ' + e.message);
        }
    }

    showCreateUserModal() {
        const groupOptions = this.groups.map(g =>
            `<option value="${g.id}" ${g.id === 'default' ? 'selected' : ''}>${this.escapeHtml(g.name)}</option>`
        ).join('');

        const presetOptions = this.presets.map(p =>
            `<option value="${p.id}">${this.escapeHtml(p.name)}</option>`
        ).join('');

        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal" style="max-width:500px;background:#fff;border-radius:8px;box-shadow:0 20px 60px rgba(0,0,0,0.3);">
                <div class="modal-header" style="background:linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);color:#fff;border-radius:8px 8px 0 0;">
                    <h3 style="margin:0;">➕ 创建用户</h3>
                    <button class="modal-close" onclick="this.closest('.modal-overlay').remove()" style="color:#fff;">×</button>
                </div>
                <div class="modal-body" style="padding:24px;background:#fff;">
                    <div class="form-group">
                        <label class="form-label">用户名 <span style="color:#ef4444;">*</span></label>
                        <input type="text" class="form-input" id="new-user-username" placeholder="输入用户名">
                    </div>
                    <div class="form-group">
                        <label class="form-label">密码 <span style="color:#ef4444;">*</span></label>
                        <input type="password" class="form-input" id="new-user-password" placeholder="输入密码（至少6位）" minlength="6">
                        <small style="color:#6b7280;font-size:12px;">密码至少需要6个字符</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">用户组</label>
                        <select class="form-select" id="new-user-group" style="width:100%;">
                            ${groupOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">API密钥预设</label>
                        <select class="form-select" id="new-user-preset" style="width:100%;">
                            <option value="">继承用户组设置</option>
                            ${presetOptions}
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">角色</label>
                        <select class="form-select" id="new-user-role" style="width:100%;">
                            <option value="user">普通用户</option>
                            <option value="admin">管理员</option>
                        </select>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">取消</button>
                    <button class="btn btn-primary" onclick="usersModule.createUser()" style="background:linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);border:none;">✅ 创建</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);
    }

    async createUser() {
        const username = document.getElementById('new-user-username')?.value?.trim();
        const password = document.getElementById('new-user-password')?.value;
        const group = document.getElementById('new-user-group')?.value;
        const role = document.getElementById('new-user-role')?.value;
        const defaultPresetId = document.getElementById('new-user-preset')?.value || null;

        if (!username || !password) {
            alert('请填写用户名和密码');
            return;
        }
        
        if (password.length < 6) {
            alert('密码至少需要6位');
            return;
        }

        try {
            const resp = await fetch('/api/admin/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Session-Token': this.app.sessionToken
                },
                body: JSON.stringify({
                    username: username,
                    password: password,
                    group: group,
                    role: role,
                    default_preset_id: defaultPresetId
                })
            });

            if (resp.ok) {
                document.querySelector('.modal-overlay')?.remove();
                alert('用户创建成功！');
                this.loadUsers();
            } else {
                const err = await resp.json();
                alert('创建失败: ' + (err.detail || '未知错误'));
            }
        } catch (e) {
            alert('创建失败: ' + e.message);
        }
    }

    escapeHtml(str) {
        if (!str) return '';
        return String(str).replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
}

window.UsersModule = UsersModule;
