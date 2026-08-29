// 管理控制台主应用
class AdminApp {
    constructor() {
        this.currentModule = 'dashboard';
        this.sessionToken = localStorage.getItem('session_token');
        this.modules = new Map();
    }
    
    async init() {
        if (!await this.checkAuth()) return;
        this.initUI();
        this.loadDashboardData();
        
        const hash = window.location.hash.slice(1);
        if (hash) this.switchModule(hash);
        
        setInterval(() => this.refreshTasks(), 5000);
    }
    
    async checkAuth() {
        if (!this.sessionToken) {
            window.location.href = '/static/login.html?redirect=/admin';
            return false;
        }
        
        try {
            const resp = await fetch('/auth/check', {
                headers: { 'X-Session-Token': this.sessionToken }
            });
            const data = await resp.json();
            
            if (!data.valid) {
                localStorage.removeItem('session_token');
                window.location.href = '/static/login.html?redirect=/admin';
                return false;
            }
            
            document.getElementById('current-user').textContent = data.user?.username || 'Admin';
            
            if (data.user?.role !== 'admin') {
                alert('您没有管理员权限');
                window.location.href = '/';
                return false;
            }
            return true;
        } catch (e) {
            console.error('Session check failed:', e);
            localStorage.removeItem('session_token');
            window.location.href = '/static/login.html?redirect=/admin';
            return false;
        }
    }
    
    initUI() {
        document.querySelector('.sidebar-toggle').onclick = () => this.toggleSidebar();
        document.querySelector('.mobile-menu-btn').onclick = () => this.toggleMobileMenu();
        document.querySelector('.logout-btn').onclick = () => this.logout();
        
        // 移动端遮罩层点击关闭侧边栏
        const overlay = document.getElementById('mobile-overlay');
        if (overlay) {
            overlay.onclick = () => this.closeMobileMenu();
        }
        
        document.querySelectorAll('.nav-item').forEach(item => {
            item.onclick = () => this.switchModule(item.dataset.module);
        });
        
        if (localStorage.getItem('sidebar-collapsed') === 'true') {
            document.getElementById('sidebar').classList.add('collapsed');
        }
        
        // 监听窗口大小变化，桌面端自动关闭移动端菜单
        window.addEventListener('resize', () => {
            if (window.innerWidth >= 768) {
                this.closeMobileMenu();
            }
        });
    }
    
    switchModule(moduleId) {
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.module === moduleId);
        });
        
        document.querySelectorAll('.module-content').forEach(content => {
            content.classList.toggle('active', content.id === `module-${moduleId}`);
        });
        
        const titles = {
            'dashboard': '仪表盘', 'users': '用户管理', 'groups': '用户组管理',
            'permissions': '权限管理', 'quota': '配额管理', 'sessions': '会话管理',
            'tasks': '任务监控', 'history': '历史记录', 'logs': '系统日志',
            'config': '服务器配置', 'announcement': '公告管理', 'cleanup': '清理管理'
        };
        document.getElementById('page-title').textContent = titles[moduleId] || moduleId;
        document.getElementById('breadcrumb-current').textContent = titles[moduleId] || moduleId;
        
        window.location.hash = moduleId;
        this.currentModule = moduleId;
        this.loadModuleData(moduleId);
        
        // 移动端点击导航项后自动关闭侧边栏
        this.closeMobileMenu();
    }
    
    async loadModuleData(moduleId) {
        const module = this.modules.get(moduleId);
        if (module && module.load) await module.load();
    }
    
    registerModule(id, module) {
        this.modules.set(id, module);
    }
    
    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        sidebar.classList.toggle('collapsed');
        const btn = sidebar.querySelector('.sidebar-toggle');
        btn.textContent = sidebar.classList.contains('collapsed') ? '▶' : '◀';
        localStorage.setItem('sidebar-collapsed', sidebar.classList.contains('collapsed'));
    }
    
    toggleMobileMenu() {
        const sidebar = document.getElementById('sidebar');
        const isOpen = sidebar.classList.contains('mobile-open');
        
        if (isOpen) {
            this.closeMobileMenu();
        } else {
            this.openMobileMenu();
        }
    }
    
    openMobileMenu() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('mobile-overlay');
        
        sidebar.classList.add('mobile-open');
        if (overlay) overlay.classList.add('active');
        
        // 防止背景滚动
        document.body.style.overflow = 'hidden';
    }
    
    closeMobileMenu() {
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('mobile-overlay');
        
        sidebar.classList.remove('mobile-open');
        if (overlay) overlay.classList.remove('active');
        
        // 恢复背景滚动
        document.body.style.overflow = '';
    }
    
    async logout() {
        try {
            await fetch('/auth/logout', {
                method: 'POST',
                headers: { 'X-Session-Token': this.sessionToken }
            });
        } catch (e) {}
        localStorage.removeItem('session_token');
        window.location.href = '/static/login.html';
    }
    
    async loadDashboardData() {
        try {
            const tasksResp = await fetch('/admin/tasks', {
                headers: { 'X-Session-Token': this.sessionToken }
            });
            if (tasksResp.ok) {
                const tasks = await tasksResp.json();
                const count = Array.isArray(tasks) ? tasks.length : Object.keys(tasks).length;
                document.getElementById('stat-tasks').textContent = count;
                this.renderTasksTable(tasks);
            }
            
            // 加载用户数
            const usersResp = await fetch('/api/admin/users', {
                headers: { 'X-Session-Token': this.sessionToken }
            });
            if (usersResp.ok) {
                const data = await usersResp.json();
                // API返回的是数组，不是{users: []}
                const users = Array.isArray(data) ? data : (data.users || []);
                document.getElementById('stat-users').textContent = users.length;
            }
            
            document.getElementById('stat-translations').textContent = '--';
            document.getElementById('stat-storage').textContent = '--';
        } catch (e) {
            console.error('Failed to load dashboard:', e);
        }
    }
    
    renderTasksTable(tasks) {
        const tbody = document.getElementById('tasks-table-body');
        
        // 兼容数组和字典格式
        let taskList;
        if (Array.isArray(tasks)) {
            taskList = tasks.map(t => [t.task_id, t]);
        } else {
            taskList = Object.entries(tasks || {});
        }
        
        if (!taskList || taskList.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;">暂无进行中的任务</td></tr>';
            return;
        }
        tbody.innerHTML = taskList.map(([id, task]) => `
            <tr>
                <td><code style="background:#f3f4f6;padding:2px 6px;border-radius:4px;">${id.slice(0,8)}...</code></td>
                <td>${task.username || '-'}</td>
                <td><span class="badge badge-info">${task.status || 'processing'}</span></td>
                <td>${task.progress || 0}%</td>
                <td>${task.start_time ? new Date(task.start_time).toLocaleString() : '-'}</td>
                <td><button class="btn btn-danger btn-sm" onclick="app.cancelTask('${id}')">取消</button></td>
            </tr>
        `).join('');
    }
    
    refreshTasks() {
        if (this.currentModule === 'dashboard') this.loadDashboardData();
    }
    
    async cancelTask(taskId) {
        if (!confirm('确定要取消此任务吗？')) return;
        try {
            await fetch(`/admin/tasks/${taskId}/cancel`, {
                method: 'POST',
                headers: { 'X-Session-Token': this.sessionToken }
            });
            this.refreshTasks();
        } catch (e) {
            alert('取消失败: ' + e.message);
        }
    }
}

window.AdminApp = AdminApp;
