const { contextBridge, ipcRenderer } = require('electron');

// Expor APIs seguras para o renderer process
contextBridge.exposeInMainWorld('electronAPI', {
  // Chamadas para API
  apiCall: (method, endpoint, data) => 
    ipcRenderer.invoke('api-call', { method, endpoint, data }),

  // Diálogos do sistema
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
  showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),
  showMessageBox: (options) => ipcRenderer.invoke('show-message-box', options),

  // URLs externas
  openExternal: (url) => ipcRenderer.invoke('open-external', url),

  // Informações do app
  getAppInfo: () => ipcRenderer.invoke('get-app-info'),

  // Controles de janela
  windowMinimize: () => ipcRenderer.invoke('window-minimize'),
  windowMaximize: () => ipcRenderer.invoke('window-maximize'),
  windowClose: () => ipcRenderer.invoke('window-close'),

  // Steam Workshop
  openSteamWorkshop: (gameId) => ipcRenderer.invoke('open-steam-workshop', gameId),

  // Event listeners
  onWorkshopItemSelected: (callback) => {
    ipcRenderer.on('workshop-item-selected', (event, workshopId) => {
      callback(workshopId);
    });
  },

  // Novos listeners para download
  onDownloadResult: (callback) => {
    ipcRenderer.on('download-result', (event, data) => {
      callback(data);
    });
  },

  onDownloadError: (callback) => {
    ipcRenderer.on('download-error', (event, data) => {
      callback(data);
    });
  },

  // Remover listeners
  removeAllListeners: (channel) => {
    ipcRenderer.removeAllListeners(channel);
  }
});

console.log('Preload script carregado');