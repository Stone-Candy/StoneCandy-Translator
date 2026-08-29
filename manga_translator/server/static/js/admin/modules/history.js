// 历史记录模块 - 用户列表 + 相册详情
class HistoryModule {
    constructor(app) {
        this.app = app;
        this.allRecords = [];
        this.userStats = {}; // 用户统计信息
    }
    
    async load() {
        await this.loadHistory();
    }
    
    async loadHistory() {
        const container = document.getElementById('history-table-body');
        if (!container) return;
        
        try {
            // 获取所有历史
            const resp = await fetch(`/api/history/admin/all?limit=1000&offset=0`, {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const data = await resp.json();
                this.allRecords = data.history || [];
                this.calculateUserStats();
                this.renderUserList();
            }
        } catch (e) {
            console.error('Failed to load history:', e);
            container.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#ef4444;">加载失败</td></tr>';
        }
    }
    
    calculateUserStats() {
        this.userStats = {};
        
        this.allRecords.forEach(record => {
            const userId = record.user_id || '未知用户';
            if (!this.userStats[userId]) {
                this.userStats[userId] = {
                    count: 0,
                    totalFiles: 0,
                    totalSize: 0,
                    lastActivity: null,
                    sessions: []
                };
            }
            
            const stats = this.userStats[userId];
            stats.count++;
            stats.totalFiles += record.file_count || 0;
            stats.totalSize += record.total_size || 0;
            stats.sessions.push(record);
            
            const timestamp = new Date(record.timestamp);
            if (!stats.lastActivity || timestamp > stats.lastActivity) {
                stats.lastActivity = timestamp;
            }
        });
    }
    
    renderUserList() {
        const tbody = document.getElementById('history-table-body');
        const pagination = document.getElementById('history-pagination');
        
        if (!tbody) return;
        
        // 修改表头
        const thead = tbody.closest('table')?.querySelector('thead');
        if (thead) {
            thead.innerHTML = '<tr><th>用户</th><th>翻译次数</th><th>文件数</th><th>总大小</th><th>最后活动</th><th>操作</th></tr>';
        }
        
        const users = Object.entries(this.userStats).sort((a, b) => {
            // 按最后活动时间排序
            return (b[1].lastActivity || 0) - (a[1].lastActivity || 0);
        });
        
        if (users.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;">暂无历史记录</td></tr>';
            if (pagination) pagination.innerHTML = '';
            return;
        }
        
        tbody.innerHTML = users.map(([userId, stats]) => `
            <tr>
                <td><strong>👤 ${userId}</strong></td>
                <td>${stats.count} 次</td>
                <td>${stats.totalFiles} 个</td>
                <td>${this.formatSize(stats.totalSize)}</td>
                <td>${stats.lastActivity ? stats.lastActivity.toLocaleString() : '-'}</td>
                <td>
                    <button class="btn btn-primary btn-sm" onclick="historyModule.viewUserGallery('${userId}')">📷 查看相册</button>
                    <button class="btn btn-danger btn-sm" onclick="historyModule.deleteUserHistory('${userId}')">🗑 删除全部</button>
                </td>
            </tr>
        `).join('');
        
        if (pagination) {
            pagination.innerHTML = `<span style="color:#666;">共 ${users.length} 个用户，${this.allRecords.length} 条记录</span>`;
        }
    }
    
    formatSize(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        let i = 0;
        while (bytes >= 1024 && i < units.length - 1) {
            bytes /= 1024;
            i++;
        }
        return bytes.toFixed(1) + ' ' + units[i];
    }
    
    // 查看用户相册 - 复用用户端的相册风格
    viewUserGallery(userId) {
        const userRecords = this.userStats[userId]?.sessions || [];
        
        if (userRecords.length === 0) {
            alert('该用户没有历史记录');
            return;
        }
        
        // 创建相册弹窗
        const modal = document.createElement('div');
        modal.id = 'admin-user-gallery-modal';
        modal.style.cssText = `
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.8);z-index:10000;
            display:flex;flex-direction:column;
        `;
        
        modal.innerHTML = `
            <div style="background:#fff;padding:15px 20px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid #ddd;">
                <h3 style="margin:0;font-size:18px;">📷 ${userId} 的翻译历史 (${userRecords.length} 条)</h3>
                <div style="display:flex;gap:10px;align-items:center;">
                    <span id="admin-gallery-selection-info" style="font-size:13px;color:#666;"></span>
                    <button id="admin-gallery-download-selected" class="btn btn-secondary btn-sm" style="display:none;">下载选中</button>
                    <button id="admin-gallery-delete-selected" class="btn btn-danger btn-sm" style="display:none;">删除选中</button>
                    <button id="admin-gallery-download-all" class="btn btn-secondary btn-sm">下载全部</button>
                    <button style="background:none;border:none;font-size:24px;cursor:pointer;padding:0 5px;" onclick="document.getElementById('admin-user-gallery-modal').remove()">×</button>
                </div>
            </div>
            <div style="flex:1;overflow-y:auto;padding:20px;background:#f5f5f5;">
                <div id="admin-gallery-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:15px;"></div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        // 保存当前用户和选中状态
        this.currentGalleryUser = userId;
        this.gallerySelectedItems = new Set();
        
        // 绑定事件
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.remove(); });
        document.getElementById('admin-gallery-download-all').onclick = () => this.downloadUserHistory(userId);
        document.getElementById('admin-gallery-download-selected').onclick = () => this.downloadGallerySelected();
        document.getElementById('admin-gallery-delete-selected').onclick = () => this.deleteGallerySelected();
        
        // 渲染相册内容
        this.renderUserGalleryItems(userRecords);
    }
    
    renderUserGalleryItems(records) {
        const grid = document.getElementById('admin-gallery-grid');
        if (!grid) return;
        
        grid.innerHTML = '';
        
        // 按日期分组
        const groupedByDate = {};
        records.forEach(item => {
            const date = new Date(item.timestamp).toLocaleDateString();
            if (!groupedByDate[date]) groupedByDate[date] = [];
            groupedByDate[date].push(item);
        });
        
        // 渲染每个日期组
        for (const [date, items] of Object.entries(groupedByDate)) {
            const dateHeader = document.createElement('div');
            dateHeader.style.cssText = 'grid-column:1/-1;font-size:14px;font-weight:bold;color:#333;padding:10px 0 5px;border-bottom:1px solid #ddd;margin-bottom:10px;';
            dateHeader.textContent = date;
            grid.appendChild(dateHeader);
            
            for (const item of items) {
                const card = this.createGalleryCard(item);
                grid.appendChild(card);
            }
        }
    }

    
    createGalleryCard(item) {
        const card = document.createElement('div');
        card.className = 'gallery-card';
        card.dataset.token = item.session_token;
        card.style.cssText = `
            background:#fff;border-radius:8px;overflow:hidden;
            box-shadow:0 2px 8px rgba(0,0,0,0.1);cursor:pointer;
            transition:transform 0.2s,box-shadow 0.2s;position:relative;
        `;
        
        const timestamp = new Date(item.timestamp).toLocaleTimeString();
        const fileCount = item.file_count || 1;
        const files = item.metadata?.files || [];
        
        card.innerHTML = `
            <div style="position:absolute;top:8px;left:8px;z-index:1;">
                <input type="checkbox" data-token="${item.session_token}" style="width:18px;height:18px;cursor:pointer;">
            </div>
            <div class="thumbnail-container" data-token="${item.session_token}" style="height:150px;background:#eee;display:flex;align-items:center;justify-content:center;overflow:hidden;">
                <span style="color:#999;">加载中...</span>
            </div>
            <div style="padding:10px;">
                <div style="font-size:12px;color:#333;">${timestamp}</div>
                <div style="font-size:11px;color:#888;margin-top:3px;">${fileCount} 个文件</div>
                <div style="display:flex;gap:5px;margin-top:8px;">
                    <button class="gallery-view-btn btn btn-secondary btn-sm" style="flex:1;padding:4px 8px;font-size:11px;">查看</button>
                    <button class="gallery-download-btn btn btn-secondary btn-sm" style="flex:1;padding:4px 8px;font-size:11px;">下载</button>
                    <button class="gallery-delete-btn btn btn-danger btn-sm" style="padding:4px 8px;font-size:11px;">🗑</button>
                </div>
            </div>
        `;
        
        // 悬停效果
        card.addEventListener('mouseenter', () => {
            card.style.transform = 'translateY(-3px)';
            card.style.boxShadow = '0 4px 15px rgba(0,0,0,0.15)';
        });
        card.addEventListener('mouseleave', () => {
            card.style.transform = '';
            card.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
        });
        
        // 复选框事件
        const checkbox = card.querySelector('input[type="checkbox"]');
        checkbox.addEventListener('change', (e) => {
            e.stopPropagation();
            if (checkbox.checked) {
                this.gallerySelectedItems.add(item.session_token);
            } else {
                this.gallerySelectedItems.delete(item.session_token);
            }
            this.updateGallerySelectionInfo();
        });
        
        // 按钮事件
        card.querySelector('.gallery-view-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.viewHistoryImages(item.session_token);
        });
        
        card.querySelector('.gallery-download-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.downloadHistoryItem(item.session_token);
        });
        
        card.querySelector('.gallery-delete-btn').addEventListener('click', async (e) => {
            e.stopPropagation();
            if (confirm('确定要删除这条翻译历史吗？')) {
                await this.deleteHistoryItem(item.session_token);
                card.remove();
            }
        });
        
        // 异步加载缩略图 - 直接传递容器元素
        const thumbContainer = card.querySelector('.thumbnail-container');
        this.loadThumbnail(item.session_token, files.length > 0 ? files[0] : null, thumbContainer);
        
        return card;
    }
    
    async loadThumbnail(sessionToken, filename, container) {
        if (!container) return;
        
        try {
            // 如果没有文件名，先获取会话详情
            if (!filename) {
                const detailResp = await fetch(`/api/history/${sessionToken}`, {
                    headers: { 'X-Session-Token': this.app.sessionToken }
                });
                if (detailResp.ok) {
                    const data = await detailResp.json();
                    const files = data.session?.files || [];
                    if (files.length > 0) {
                        filename = files[0].split('/').pop().split('\\').pop();
                    }
                }
            }
            
            if (!filename) {
                container.innerHTML = '<span style="color:#999;">无预览</span>';
                return;
            }
            
            const resp = await fetch(`/api/history/${sessionToken}/file/${filename}`, {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                const blob = await resp.blob();
                const url = URL.createObjectURL(blob);
                const img = document.createElement('img');
                img.src = url;
                img.style.cssText = 'max-width:100%;max-height:100%;object-fit:contain;';
                img.onload = () => URL.revokeObjectURL(url);
                container.innerHTML = '';
                container.appendChild(img);
            } else {
                container.innerHTML = '<span style="color:#999;">加载失败</span>';
            }
        } catch (e) {
            container.innerHTML = '<span style="color:#999;">加载失败</span>';
        }
    }
    
    updateGallerySelectionInfo() {
        const info = document.getElementById('admin-gallery-selection-info');
        const downloadBtn = document.getElementById('admin-gallery-download-selected');
        const deleteBtn = document.getElementById('admin-gallery-delete-selected');
        
        if (this.gallerySelectedItems.size > 0) {
            if (info) info.textContent = `已选择 ${this.gallerySelectedItems.size} 项`;
            if (downloadBtn) downloadBtn.style.display = 'inline-block';
            if (deleteBtn) deleteBtn.style.display = 'inline-block';
        } else {
            if (info) info.textContent = '';
            if (downloadBtn) downloadBtn.style.display = 'none';
            if (deleteBtn) deleteBtn.style.display = 'none';
        }
    }
    
    // 查看图片
    async viewHistoryImages(sessionToken) {
        try {
            const resp = await fetch(`/api/history/${sessionToken}`, {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (!resp.ok) {
                alert('获取详情失败');
                return;
            }
            
            const data = await resp.json();
            const session = data.session;
            
            if (!session || !session.files || session.files.length === 0) {
                alert('没有可显示的图片');
                return;
            }
            
            this.showImageViewer(sessionToken, session.files);
        } catch (e) {
            alert('获取详情失败');
        }
    }
    
    showImageViewer(sessionToken, files) {
        let currentIndex = 0;
        
        const viewer = document.createElement('div');
        viewer.id = 'admin-image-viewer';
        viewer.style.cssText = `
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.95);z-index:10001;
            display:flex;flex-direction:column;align-items:center;justify-content:center;
        `;
        
        viewer.innerHTML = `
            <button style="position:absolute;top:15px;right:20px;background:none;border:none;color:#fff;font-size:30px;cursor:pointer;">×</button>
            <button id="viewer-prev" style="position:absolute;left:20px;top:50%;transform:translateY(-50%);background:rgba(255,255,255,0.2);border:none;color:#fff;font-size:30px;cursor:pointer;padding:10px 15px;border-radius:5px;">‹</button>
            <button id="viewer-next" style="position:absolute;right:20px;top:50%;transform:translateY(-50%);background:rgba(255,255,255,0.2);border:none;color:#fff;font-size:30px;cursor:pointer;padding:10px 15px;border-radius:5px;">›</button>
            <img id="viewer-image" style="max-width:90%;max-height:80%;object-fit:contain;">
            <div id="viewer-info" style="color:#fff;margin-top:15px;font-size:14px;"></div>
            <button class="btn btn-secondary" style="margin-top:10px;">下载此图片</button>
        `;
        
        document.body.appendChild(viewer);
        
        const showImage = async (index) => {
            currentIndex = index;
            const filePath = files[index];
            const filename = filePath.split('/').pop().split('\\').pop();
            document.getElementById('viewer-info').textContent = `${index + 1} / ${files.length} - ${filename}`;
            
            try {
                const resp = await fetch(`/api/history/${sessionToken}/file/${filename}`, {
                    headers: { 'X-Session-Token': this.app.sessionToken }
                });
                if (resp.ok) {
                    const blob = await resp.blob();
                    const url = URL.createObjectURL(blob);
                    const img = document.getElementById('viewer-image');
                    if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
                    img.dataset.url = url;
                    img.src = url;
                }
            } catch (e) {}
        };
        
        showImage(0);
        
        viewer.querySelector('button').onclick = () => viewer.remove();
        viewer.onclick = (e) => { if (e.target === viewer) viewer.remove(); };
        document.getElementById('viewer-prev').onclick = () => showImage((currentIndex - 1 + files.length) % files.length);
        document.getElementById('viewer-next').onclick = () => showImage((currentIndex + 1) % files.length);
        
        viewer.querySelector('.btn-secondary').onclick = async () => {
            const filePath = files[currentIndex];
            const filename = filePath.split('/').pop().split('\\').pop();
            try {
                const ticket = await this.requestDownloadTicket(
                    `/api/history/${sessionToken}/file/${encodeURIComponent(filename)}/download-ticket`
                );
                this.triggerDownload(ticket.url, ticket.filename || filename);
            } catch (e) {}
        };
        
        document.addEventListener('keydown', function handler(e) {
            if (!document.getElementById('admin-image-viewer')) {
                document.removeEventListener('keydown', handler);
                return;
            }
            if (e.key === 'Escape') viewer.remove();
            if (e.key === 'ArrowLeft') showImage((currentIndex - 1 + files.length) % files.length);
            if (e.key === 'ArrowRight') showImage((currentIndex + 1) % files.length);
        });
    }

    async requestDownloadTicket(path, body = null) {
        const options = {
            method: 'POST',
            headers: { 'X-Session-Token': this.app.sessionToken }
        };
        if (body !== null) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }

        const resp = await fetch(path, options);
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
            throw new Error(data.detail || '获取下载链接失败');
        }
        return data;
    }

    triggerDownload(url, filename) {
        const a = document.createElement('a');
        a.href = url;
        if (filename) {
            a.download = filename;
        }
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    buildZipFilename(zipName) {
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        return `${zipName}_${timestamp}.zip`;
    }
    
    // 下载单个历史项
    async downloadHistoryItem(sessionToken) {
        try {
            const resp = await fetch(`/api/history/${sessionToken}`, {
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (!resp.ok) return;
            
            const data = await resp.json();
            const session = data.session;
            
            if (!session?.files?.length) {
                alert('没有可下载的文件');
                return;
            }
            
            if (session.files.length === 1) {
                const filename = session.files[0].split('/').pop().split('\\').pop();
                const ticket = await this.requestDownloadTicket(
                    `/api/history/${sessionToken}/file/${encodeURIComponent(filename)}/download-ticket`
                );
                this.triggerDownload(ticket.url, ticket.filename || filename);
            } else {
                const ticket = await this.requestDownloadTicket(
                    `/api/history/${sessionToken}/download-ticket`
                );
                this.triggerDownload(ticket.url, ticket.filename);
            }
        } catch (e) {
            alert('下载失败');
        }
    }
    
    // 下载选中的
    async downloadGallerySelected() {
        if (this.gallerySelectedItems.size === 0) return;
        await this.downloadAsZip(Array.from(this.gallerySelectedItems), 'history_selected');
    }
    
    // 下载用户全部历史
    async downloadUserHistory(userId) {
        const tokens = this.userStats[userId]?.sessions.map(s => s.session_token) || [];
        if (tokens.length === 0) return;
        await this.downloadAsZip(tokens, `history_${userId}`);
    }
    
    // 打包下载
    async downloadAsZip(tokens, zipName) {
        const info = document.getElementById('admin-gallery-selection-info');
        if (info) info.textContent = `正在准备 ${tokens.length} 个会话的下载...`;

        try {
            const ticket = await this.requestDownloadTicket('/api/history/batch-download-ticket', {
                session_tokens: tokens,
                filename: this.buildZipFilename(zipName)
            });
            this.triggerDownload(ticket.url, ticket.filename);
            if (info) info.textContent = '下载已开始';
        } catch (e) {
            alert('下载失败');
            if (info) info.textContent = '';
            return;
        }

        if (info) {
            setTimeout(() => {
                if (info.textContent === '下载已开始') {
                    info.textContent = '';
                }
            }, 3000);
        }
    }
    
    // 删除单个历史项
    async deleteHistoryItem(sessionToken) {
        try {
            const resp = await fetch(`/api/history/${sessionToken}`, {
                method: 'DELETE',
                headers: { 'X-Session-Token': this.app.sessionToken }
            });
            
            if (resp.ok) {
                this.allRecords = this.allRecords.filter(r => r.session_token !== sessionToken);
                this.calculateUserStats();
                this.gallerySelectedItems?.delete(sessionToken);
                return true;
            }
        } catch (e) {}
        return false;
    }
    
    // 删除选中的
    async deleteGallerySelected() {
        if (this.gallerySelectedItems.size === 0) return;
        if (!confirm(`确定删除选中的 ${this.gallerySelectedItems.size} 条记录？`)) return;
        
        for (const token of this.gallerySelectedItems) {
            await this.deleteHistoryItem(token);
            document.querySelector(`.gallery-card[data-token="${token}"]`)?.remove();
        }
        
        this.gallerySelectedItems.clear();
        this.updateGallerySelectionInfo();
        this.renderUserList(); // 更新用户列表统计
    }
    
    // 删除用户全部历史
    async deleteUserHistory(userId) {
        const tokens = this.userStats[userId]?.sessions.map(s => s.session_token) || [];
        if (tokens.length === 0) return;
        if (!confirm(`确定删除 ${userId} 的全部 ${tokens.length} 条历史记录？`)) return;
        
        for (const token of tokens) {
            await this.deleteHistoryItem(token);
        }
        
        this.renderUserList();
        alert(`已删除 ${userId} 的全部历史记录`);
    }
    
    async clearHistory() {
        if (!confirm('确定清空所有历史记录？此操作不可恢复！')) return;
        
        for (const record of this.allRecords) {
            await this.deleteHistoryItem(record.session_token);
        }
        
        this.allRecords = [];
        this.userStats = {};
        this.renderUserList();
    }
}

window.HistoryModule = HistoryModule;
