class BOIIIWDApp {
    constructor() {
        this.currentTab = 'main';
        this.settings = {};
        this.queue = [];
        this.library = [];
        this.statusTimer = null;
        this.init();
    }

    async init() {
        this.setupWindowControls();
        this.setupTabs();
        this.setupEventListeners();
        await this.loadSettings();
        await this.loadLibrary();
        await this.loadQueue();
        this.startStatusUpdater();
        this.showNotification('Application started successfully.', 'success');

        if (window.electronAPI) {
            window.electronAPI.onWorkshopItemSelected((workshopId) => this.handleWorkshopItemSelected(workshopId));
            window.electronAPI.onDownloadResult?.((data) => this.handleDownloadResult(data));
            window.electronAPI.onDownloadError?.((data) => this.handleDownloadError(data));
        }
    }

    async apiCall(method, endpoint, data = null) {
        if (!window.electronAPI) {
            throw new Error('electronAPI bridge is not available');
        }
        const result = await window.electronAPI.apiCall(method, endpoint, data);
        if (!result?.success) {
            const error = new Error(result?.error || result?.data?.message || 'Request failed');
            error.response = result?.data;
            throw error;
        }
        return result.data ?? {};
    }

    handleApiError(error, fallbackMessage) {
        const message = error?.response?.message || error?.response?.error || error?.message || fallbackMessage;
        this.showNotification(message, 'error');
        console.error(fallbackMessage, error);
    }

    setupWindowControls() {
        document.getElementById('minimizeBtn')?.addEventListener('click', () => window.electronAPI?.windowMinimize());
        document.getElementById('maximizeBtn')?.addEventListener('click', () => window.electronAPI?.windowMaximize());
        document.getElementById('closeBtn')?.addEventListener('click', () => window.electronAPI?.windowClose());
    }

    setupTabs() {
        document.querySelectorAll('.nav-item').forEach((item) => {
            item.addEventListener('click', () => this.switchTab(item.dataset.tab));
        });
    }

    switchTab(tabName) {
        document.querySelectorAll('.nav-item').forEach((item) => item.classList.remove('active'));
        const selectedNav = document.querySelector(`[data-tab="${tabName}"]`);
        if (selectedNav) selectedNav.classList.add('active');

        document.querySelectorAll('.tab-content').forEach((panel) => panel.classList.remove('active'));
        const targetPanel = document.getElementById(`${tabName}-tab`);
        if (targetPanel) targetPanel.classList.add('active');

        this.currentTab = tabName;

        if (tabName === 'library') {
            this.loadLibrary();
        } else if (tabName === 'queue') {
            this.loadQueue();
        } else if (tabName === 'settings') {
            this.loadSettings();
        }
    }

    setupEventListeners() {
        document.getElementById('downloadBtn')?.addEventListener('click', () => this.startDownload());
        document.getElementById('stopBtn')?.addEventListener('click', () => this.stopDownload());
        document.getElementById('showInfoBtn')?.addEventListener('click', () => this.showWorkshopInfo());
        document.getElementById('browseWorkshopBtn')?.addEventListener('click', () => this.openSteamWorkshop());

        document.getElementById('addToQueueBtn')?.addEventListener('click', () => this.addToQueue());
        document.getElementById('processQueueBtn')?.addEventListener('click', () => this.processQueue());
        document.getElementById('clearQueueBtn')?.addEventListener('click', () => this.clearQueue());

        document.getElementById('refreshLibraryBtn')?.addEventListener('click', () => this.loadLibrary());
        document.getElementById('fixCompatibilityBtn')?.addEventListener('click', () => this.showCompatibilityModal());
        document.getElementById('librarySearch')?.addEventListener('input', (event) => this.filterLibrary(event.target.value));

        document.getElementById('saveSettingsBtn')?.addEventListener('click', () => this.saveSettings());
        document.getElementById('launchGameBtn')?.addEventListener('click', () => this.launchGame());
        document.getElementById('browseDestinationBtn')?.addEventListener('click', () => this.browseFolder('destination'));
        document.getElementById('browseSteamCMDBtn')?.addEventListener('click', () => this.browseFolder('steamcmd'));

        document.getElementById('closeInfoModal')?.addEventListener('click', () => this.hideModal('workshopInfoModal'));
        document.getElementById('closeCompatibilityModal')?.addEventListener('click', () => this.hideModal('compatibilityModal'));

        document.getElementById('workshopId')?.addEventListener('keypress', (event) => {
            if (event.key === 'Enter') this.startDownload();
        });
    }

    async startDownload() {
        const input = document.getElementById('workshopId');
        const value = input?.value.trim();
        if (!value) {
            this.showNotification('Enter a Workshop ID or link.', 'warning');
            return;
        }
        try {
            const response = await this.apiCall('POST', '/download', { workshop_id: value });
            const message = response.message || `Download started for ID ${value}.`;
            this.showNotification(message, 'success');
            this.updateDownloadUI(true);
        } catch (error) {
            this.handleApiError(error, 'Unable to start the download');
        }
    }

    async stopDownload() {
        try {
            const response = await this.apiCall('POST', '/download/stop');
            this.showNotification(response.message || 'Download stop requested.', 'info');
            this.updateDownloadUI(false);
        } catch (error) {
            this.handleApiError(error, 'Unable to stop the download');
        }
    }

    updateDownloadUI(isDownloading) {
        const downloadBtn = document.getElementById('downloadBtn');
        const stopBtn = document.getElementById('stopBtn');
        if (!downloadBtn || !stopBtn) return;
        downloadBtn.style.display = isDownloading ? 'none' : 'inline-flex';
        stopBtn.style.display = isDownloading ? 'inline-flex' : 'none';
    }

    async showWorkshopInfo(idOverride = null) {
        const input = document.getElementById('workshopId');
        const value = idOverride || input?.value.trim();
        if (!value) {
            this.showNotification('Enter a Workshop ID first.', 'warning');
            return;
        }
        this.showModal('workshopInfoModal');
        const container = document.getElementById('workshopInfoContent');
        if (container) {
            container.innerHTML = '<div class="loading">Fetching workshop details...</div>';
        }
        try {
            const response = await this.apiCall('GET', '/workshop/info', { id: value });
            const info = response.info;
            if (info) {
                this.displayWorkshopInfo(info);
                if (response.warning) {
                    this.showNotification(response.warning, 'warning');
                }
            } else {
                throw new Error('Workshop details were not returned.');
            }
        } catch (error) {
            if (container) {
                container.innerHTML = `<div class="error">${error.response?.message || 'Failed to retrieve workshop info.'}</div>`;
            }
        }
    }

    displayWorkshopInfo(info) {
        const container = document.getElementById('workshopInfoContent');
        if (!container || !info) return;
        const escapeHtml = (value) => (typeof value === 'string'
            ? value
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#39;')
            : value);
        const tags = Array.isArray(info.tags) && info.tags.length
            ? info.tags.map((tag) => escapeHtml(tag)).join(', ')
            : 'None';
        const descriptionRaw = info.description ? escapeHtml(info.description) : '';
        const description = descriptionRaw ? descriptionRaw.replace(/\n/g, '<br>') : 'No description available.';
    const preview = info.preview_url ? `<img class="workshop-preview" src="${escapeHtml(info.preview_url)}" alt="Preview" />` : '';
        const workshopButton = info.workshop_url
            ? `<button class="btn btn-primary" onclick="window.electronAPI?.openExternal('${escapeHtml(info.workshop_url)}')">Open in Steam Workshop</button>`
            : '';
        const localDetails = info.local_path
            ? `<p><strong>Installed Folder:</strong> ${escapeHtml(info.local_path)}</p>`
            : '';
        const sizeOnDisk = info.size_on_disk
            ? `<p><strong>Installed Size:</strong> ${escapeHtml(info.size_on_disk)}</p>`
            : '';
        const folderName = info.folder_name
            ? `<p><strong>Folder Name:</strong> ${escapeHtml(info.folder_name)}</p>`
            : '';

        container.innerHTML = `
            <div class="workshop-info">
                ${preview}
                <h4>${info.title || info.id}</h4>
                <p><strong>ID:</strong> ${info.id}</p>
                <p><strong>File Size:</strong> ${info.file_size || 'Unknown'}</p>
                <p><strong>Created:</strong> ${info.created ? new Date(info.created).toLocaleString() : 'Unknown'}</p>
                <p><strong>Updated:</strong> ${info.updated ? new Date(info.updated).toLocaleString() : 'Unknown'}</p>
                <p><strong>Tags:</strong> ${tags}</p>
                <p><strong>Source:</strong> ${info.source || 'Unknown'}</p>
                ${localDetails}
                ${folderName}
                ${sizeOnDisk}
                <div class="workshop-description"><strong>Description:</strong><p>${description}</p></div>
                <div class="workshop-actions">
                    ${workshopButton || '<span style="opacity:0.7;">No workshop link available for this item.</span>'}
                </div>
            </div>
        `;
    }

    async openSteamWorkshop() {
        try {
            await window.electronAPI?.openSteamWorkshop('311210');
        } catch (error) {
            window.open('https://steamcommunity.com/app/311210/workshop/', '_blank');
        }
    }

    async addToQueue() {
        const textarea = document.getElementById('queueInput');
        const value = textarea?.value.trim();
        if (!value) {
            this.showNotification('Enter at least one Workshop ID.', 'warning');
            return;
        }
        try {
            const response = await this.apiCall('POST', '/queue', { items: value });
            const added = response.added_items || [];
            this.showNotification(`${added.length} item(s) added to the queue.`, 'success');
            if (textarea) textarea.value = '';
            await this.loadQueue();
        } catch (error) {
            this.handleApiError(error, 'Unable to add items to the queue');
        }
    }

    async processQueue() {
        try {
            const response = await this.apiCall('POST', '/queue/process');
            this.showNotification(response.message || 'Queue processing started.', 'success');
        } catch (error) {
            this.handleApiError(error, 'Unable to start queue processing');
        }
    }

    async clearQueue() {
        try {
            const response = await this.apiCall('DELETE', '/queue');
            this.showNotification(response.message || 'Queue cleared.', 'info');
            await this.loadQueue();
        } catch (error) {
            this.handleApiError(error, 'Unable to clear the queue');
        }
    }

    async loadQueue() {
        try {
            const response = await this.apiCall('GET', '/queue');
            this.queue = response.queue || [];
            this.updateQueueUI();
        } catch (error) {
            this.handleApiError(error, 'Unable to load the queue');
        }
    }

    updateQueueUI() {
        const container = document.getElementById('queueItems');
        const counter = document.getElementById('queueCount');
        if (counter) counter.textContent = this.queue.length.toString();
        if (!container) return;
        if (!this.queue.length) {
            container.innerHTML = '<div class="empty-state">No items in queue</div>';
            return;
        }
        container.innerHTML = this.queue
            .map((id) => `
                <div class="queue-item">
                    <span class="queue-item-id">${id}</span>
                    <button class="btn btn-danger btn-small queue-item-remove" onclick="app.removeFromQueue('${id}')">🗑️ Remove</button>
                </div>
            `)
            .join('');
    }

    async removeFromQueue(id) {
        try {
            const response = await this.apiCall('DELETE', `/queue/${id}`);
            this.showNotification(response.message || `Removed ${id} from queue.`, 'info');
            await this.loadQueue();
        } catch (error) {
            this.handleApiError(error, 'Unable to remove the queue item');
        }
    }

    async loadLibrary() {
        try {
            const response = await this.apiCall('GET', '/library');
            this.library = response.items || [];
            this.updateLibraryUI();
        } catch (error) {
            this.handleApiError(error, 'Unable to load the library');
        }
    }

    updateLibraryUI() {
        const container = document.getElementById('libraryItems');
        const counter = document.getElementById('libraryCount');
        if (counter) counter.textContent = this.library.length.toString();
        if (!container) return;
        if (!this.library.length) {
            container.innerHTML = '<div class="empty-state">No mods detected. Refresh after downloading.</div>';
            return;
        }
        container.innerHTML = this.library
            .map((item) => {
                const needsFix = item.needs_fix ? '<span class="warning-pill">Folder mismatch</span>' : '';
                return `
                    <div class="library-item">
                        <div class="library-item-info">
                            <div class="library-item-name">${item.name || item.id}</div>
                            <div class="library-item-details">
                                ID: ${item.id} | Folder: ${item.folder_name} | Type: ${item.type || 'Unknown'} | Size: ${item.size || 'N/A'} ${needsFix}
                            </div>
                        </div>
                        <div class="library-item-actions">
                            <button class="btn btn-info btn-small" onclick="app.showLibraryItemInfo('${item.id}')">ℹ️ Details</button>
                            <button class="btn btn-danger btn-small" onclick="app.removeLibraryItem('${item.id}')">🗑️ Remove</button>
                        </div>
                    </div>
                `;
            })
            .join('');
    }

    filterLibrary(query) {
        const term = (query || '').toLowerCase();
        document.querySelectorAll('.library-item').forEach((item) => {
            const matches = item.textContent.toLowerCase().includes(term);
            item.style.display = matches ? 'flex' : 'none';
        });
    }

    async removeLibraryItem(itemId) {
        if (!confirm(`Remove item ${itemId}?`)) return;
        try {
            const response = await this.apiCall('DELETE', '/library/remove', { item_id: itemId });
            this.showNotification(response.message || 'Item removed.', 'success');
            await this.loadLibrary();
        } catch (error) {
            this.handleApiError(error, 'Unable to remove the item');
        }
    }

    async showLibraryItemInfo(itemId) {
        await this.showWorkshopInfo(itemId);
    }

    async showCompatibilityModal() {
        this.showModal('compatibilityModal');
        await this.loadCompatibilityItems();
    }

    async loadCompatibilityItems() {
        try {
            const response = await this.apiCall('GET', '/library');
            const items = response.items || [];
            this.updateCompatibilityList(items.filter((item) => item.needs_fix));
        } catch (error) {
            this.handleApiError(error, 'Unable to load items for the compatibility fix');
        }
    }

    updateCompatibilityList(items) {
        const container = document.getElementById('compatibilityItemsList');
        if (!container) return;
        if (!items.length) {
            container.innerHTML = '<div class="success-state">All installed maps already use FolderName ✅</div>';
            return;
        }
        container.innerHTML = items
            .map((item) => `
                <div class="compatibility-item">
                    <div class="compatibility-item-info">
                        <div class="mod-name">${item.folder_name}</div>
                        <div class="mod-details">ID: ${item.id} ➜ Expected folder: ${item.expected_folder || 'Unknown'}</div>
                    </div>
                    <button class="btn btn-primary btn-small" id="fix-btn-${item.id}" onclick="app.fixSingleMod('${item.id}')">🔧 Fix</button>
                </div>
            `)
            .join('');
    }

    async fixSingleMod(modId) {
        const button = document.getElementById(`fix-btn-${modId}`);
        if (button) {
            button.disabled = true;
            button.textContent = '⏳ Fixing...';
        }
        try {
            const response = await this.apiCall('POST', '/library/fix-compatibility', { items: [modId] });
            const fixedCount = response.fixed_count ?? 0;
            if (fixedCount > 0) {
                this.showNotification(`Renamed folders for ${fixedCount} item(s).`, 'success');
            } else {
                this.showNotification('No folders required changes.', 'info');
            }
            await this.loadCompatibilityItems();
            await this.loadLibrary();
        } catch (error) {
            this.handleApiError(error, 'Unable to apply the compatibility fix');
        } finally {
            if (button) {
                button.disabled = false;
                button.textContent = '🔧 Fix';
            }
        }
    }

    async loadSettings() {
        try {
            const response = await this.apiCall('GET', '/settings');
            this.settings = response.settings || {};
            this.updateSettingsUI();
        } catch (error) {
            this.handleApiError(error, 'Unable to load settings');
        }
    }

    updateSettingsUI() {
        const map = {
            destinationFolder: 'destination_folder',
            steamcmdPath: 'steamcmd_path',
            gameExecutable: 'game_executable',
            launchParameters: 'launch_parameters',
            appearance: 'appearance',
            scaling: 'scaling',
            continuousDownload: 'continuous_download',
            cleanOnFinish: 'clean_on_finish',
            skipInstalled: 'skip_already_installed',
            showConsole: 'console',
        };
        Object.entries(map).forEach(([elementId, settingKey]) => {
            const element = document.getElementById(elementId);
            if (!element) return;
            const value = this.settings[settingKey];
            if (element.type === 'checkbox') {
                element.checked = value === 'on' || value === true;
            } else {
                element.value = value || '';
            }
        });
    }

    async saveSettings() {
        const payload = {
            destination_folder: document.getElementById('destinationFolder')?.value.trim() || '',
            steamcmd_path: document.getElementById('steamcmdPath')?.value.trim() || '',
            game_executable: document.getElementById('gameExecutable')?.value.trim() || 'BlackOps3',
            launch_parameters: document.getElementById('launchParameters')?.value.trim() || '',
            appearance: document.getElementById('appearance')?.value || 'Dark',
            scaling: document.getElementById('scaling')?.value || '1.0',
            continuous_download: document.getElementById('continuousDownload')?.checked ? 'on' : 'off',
            clean_on_finish: document.getElementById('cleanOnFinish')?.checked ? 'on' : 'off',
            skip_already_installed: document.getElementById('skipInstalled')?.checked ? 'on' : 'off',
            console: document.getElementById('showConsole')?.checked ? 'on' : 'off',
        };
        try {
            const response = await this.apiCall('POST', '/settings', { settings: payload });
            this.showNotification(response.message || 'Settings saved.', 'success');
            this.settings = { ...this.settings, ...payload };
        } catch (error) {
            this.handleApiError(error, 'Unable to save settings');
        }
    }

    async browseFolder(type) {
        if (!window.electronAPI) return;
        const dialogTitle = type === 'destination' ? 'Select Black Ops 3 folder' : 'Select SteamCMD folder';
        const result = await window.electronAPI.showOpenDialog({ properties: ['openDirectory'], title: dialogTitle });
        if (!result.canceled && result.filePaths?.length) {
            const targetField = type === 'destination' ? 'destinationFolder' : 'steamcmdPath';
            const field = document.getElementById(targetField);
            if (field) field.value = result.filePaths[0];
        }
    }

    async launchGame() {
        try {
            const response = await this.apiCall('POST', '/game/launch');
            this.showNotification(response.message || 'Launching Black Ops 3.', 'success');
        } catch (error) {
            this.handleApiError(error, 'Unable to launch the game');
        }
    }

    startStatusUpdater() {
        this.statusTimer = setInterval(async () => {
            try {
                const status = await this.apiCall('GET', '/download/status');
                this.updateStatusUI(status);
            } catch (error) {
                console.debug('Status polling failed:', error?.message);
            }
        }, 1000);
    }

    updateStatusUI(status) {
        if (!status) return;
        const progress = Number(status.progress ?? 0);
        const downloadStatus = document.getElementById('downloadStatus');
        const fileSize = document.getElementById('fileSize');
        const downloadSpeed = document.getElementById('downloadSpeed');
        const progressText = document.getElementById('progressText');
        const progressFill = document.querySelector('.progress-fill');

        if (downloadStatus) {
            const readableStatus = this.getStatusText(status.status);
            const details = [];
            if (status.title) details.push(status.title);
            if (status.message) details.push(status.message);
            const suffix = details.length ? ` - ${details.join(' | ')}` : '';
            downloadStatus.textContent = `Status: ${readableStatus}${suffix}`;
        }
        if (fileSize) fileSize.textContent = `File Size: ${status.file_size || 'Unknown'}`;
        if (downloadSpeed) downloadSpeed.textContent = `Speed: ${status.speed || '0 B/s'}`;
        if (progressText) progressText.textContent = `${Math.round(progress)}%`;
        if (progressFill) progressFill.style.width = `${Math.min(Math.max(progress, 0), 100)}%`;

        this.updateDownloadUI(Boolean(status.downloading));
    }

    getStatusText(state) {
        const dictionary = {
            idle: 'Idle',
            preparing: 'Preparing',
            downloading: 'Downloading',
            installing: 'Installing',
            completed: 'Completed',
            stopped: 'Stopped',
            error: 'Error',
        };
        return dictionary[state] || state || 'Idle';
    }

    showModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.add('show');
    }

    hideModal(id) {
        const modal = document.getElementById(id);
        if (modal) modal.classList.remove('show');
    }

    showNotification(message, type = 'info') {
        const container = document.getElementById('notifications');
        if (!container) return;
        const toast = document.createElement('div');
        toast.className = `notification ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    handleWorkshopItemSelected(workshopId) {
        const field = document.getElementById('workshopId');
        if (field) field.value = workshopId;
        this.switchTab('main');
        this.showNotification(`Item ${workshopId} selected. You can start the download.`, 'info');
    }

    handleDownloadResult(data) {
        const workshopId = data?.workshopId || data?.workshop_id;
        if (workshopId) {
            this.showNotification(`Download finished for ${workshopId}.`, 'success');
            this.loadLibrary();
        }
    }

    handleDownloadError(data) {
        const workshopId = data?.workshopId || data?.workshop_id;
        const error = data?.error || 'Unknown error';
        if (workshopId) {
            this.showNotification(`Download failed for ${workshopId}: ${error}`, 'error');
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.app = new BOIIIWDApp();
});