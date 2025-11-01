const { app, BrowserWindow, ipcMain, dialog, shell, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const axios = require('axios');
const fetch = require('node-fetch'); // Para requisições simples

const API_BASE_URL = 'http://127.0.0.1:5000/api';

let mainWindow;
let apiProcess;
const isDev = !app.isPackaged;

const iconCandidates = [
  path.join(__dirname, '..', 'assets', 'icon.png'),
  path.join(__dirname, '..', 'assets', 'icon.ico'),
  path.join(__dirname, '..', '..', 'icon.png'),
  path.join(__dirname, '..', '..', 'icon.ico'),
];
const appIcon = iconCandidates.find((candidate) => {
  try {
    return fs.existsSync(candidate);
  } catch (err) {
    return false;
  }
});

function resolvePythonExecutable() {
  const candidates = [process.env.BOIIIWD_PYTHON, process.env.PYTHON, process.env.PYTHON_PATH];
  for (const candidate of candidates) {
    if (candidate && candidate.trim()) {
      return candidate.trim();
    }
  }
  if (process.platform === 'win32') {
    return 'python';
  }
  return 'python3';
}

function buildBackendCommand(userDataPath) {
  const baseEnv = {
    ...process.env,
    BOIIIWD_DATA_DIR: userDataPath,
  };

  if (isDev) {
    const scriptPath = path.join(__dirname, '..', '..', 'api', 'boiiiwd_api_improved.py');
    return {
      command: resolvePythonExecutable(),
      args: [scriptPath],
      options: {
        cwd: path.dirname(scriptPath),
        env: baseEnv,
      },
    };
  }

  const backendDir = path.join(process.resourcesPath, 'backend');
  const executableName = process.platform === 'win32' ? 'boiiiwd_api.exe' : 'boiiiwd_api';
  const executablePath = path.join(backendDir, executableName);

  return {
    command: executablePath,
    args: [],
    options: {
      cwd: backendDir,
      env: baseEnv,
    },
  };
}

// Função para criar a janela principal
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 920,
    minHeight: 560,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      enableRemoteModule: false,
      preload: path.join(__dirname, 'preload.js')
    },
    icon: appIcon,
    show: false,
    titleBarStyle: 'default'
  });

  // Carregar a UI
  mainWindow.loadFile(path.join(__dirname, '../ui/index.html'));

  // Mostrar quando pronto
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  // Lidar com fechamento
  mainWindow.on('closed', () => {
    mainWindow = null;
    if (apiProcess) {
      apiProcess.kill();
    }
  });

  // Abrir links externos no navegador
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
}

// Função para iniciar o servidor API Python
function startApiServer(userDataPath) {
  return new Promise((resolve, reject) => {
    if (apiProcess) {
      resolve();
      return;
    }

    const backendCommand = buildBackendCommand(userDataPath);

    if (!isDev && !fs.existsSync(backendCommand.command)) {
      reject(new Error(`Backend executable não encontrado em ${backendCommand.command}`));
      return;
    }

    try {
      apiProcess = spawn(backendCommand.command, backendCommand.args, backendCommand.options);
    } catch (error) {
      apiProcess = null;
      reject(error);
      return;
    }

    let settled = false;

    apiProcess.once('spawn', () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    });

    apiProcess.stdout.on('data', (data) => {
      console.log(`[API stdout] ${data}`);
    });

    apiProcess.stderr.on('data', (data) => {
      console.error(`[API stderr] ${data}`);
    });

    apiProcess.on('error', (error) => {
      if (!settled) {
        settled = true;
        reject(error);
      }
      apiProcess = null;
    });

    apiProcess.on('exit', (code, signal) => {
      console.log(`API process finalizado (code=${code}, signal=${signal ?? 'none'})`);
      apiProcess = null;
      if (!settled && code !== 0) {
        settled = true;
        reject(new Error(`Servidor API terminou inesperadamente (code ${code})`));
      }
    });
  });
}

// Função para verificar se a API está rodando
async function waitForApi(maxAttempts = 30) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await axios.get(`${API_BASE_URL}/health`);
      console.log('API está rodando!');
      return true;
    } catch (error) {
      console.log(`Tentativa ${i + 1}: API não está pronta ainda...`);
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
  }
  return false;
}

// Event listeners do Electron
app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);

  // Iniciar servidor API
  console.log('Iniciando servidor API...');
  try {
    const userDataPath = app.getPath('userData');
    await startApiServer(userDataPath);
    const apiReady = await waitForApi();
    
    if (!apiReady) {
      console.warn('API pode não estar funcionando corretamente');
    }
  } catch (error) {
    console.error('Erro ao iniciar API:', error);
  }

  // Criar janela
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    if (apiProcess) {
      apiProcess.kill();
    }
    app.quit();
  }
});

app.on('before-quit', () => {
  if (apiProcess) {
    apiProcess.kill();
  }
});

// IPC Handlers para comunicação com renderer

// Fazer chamadas HTTP para a API
ipcMain.handle('api-call', async (event, { method, endpoint, data }) => {
  try {
    const config = {
      method: method.toLowerCase(),
      url: `${API_BASE_URL}${endpoint}`,
      headers: {
        'Content-Type': 'application/json'
      }
    };

    if (data && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
      config.data = data;
    } else if (data && method === 'GET') {
      config.params = data;
    }

    const response = await axios(config);
    return { success: true, data: response.data };
  } catch (error) {
    console.error('API Call Error:', error);
    return { 
      success: false, 
      error: error.response?.data?.message || error.message 
    };
  }
});

// Abrir diálogos do sistema
ipcMain.handle('show-open-dialog', async (event, options) => {
  const result = await dialog.showOpenDialog(mainWindow, options);
  return result;
});

ipcMain.handle('show-save-dialog', async (event, options) => {
  const result = await dialog.showSaveDialog(mainWindow, options);
  return result;
});

ipcMain.handle('show-message-box', async (event, options) => {
  const result = await dialog.showMessageBox(mainWindow, options);
  return result;
});

// Abrir URL externa
ipcMain.handle('open-external', async (event, url) => {
  shell.openExternal(url);
});

// Obter informações do sistema
ipcMain.handle('get-app-info', async () => {
  return {
    version: app.getVersion(),
    name: app.getName(),
    platform: process.platform,
    arch: process.arch
  };
});

// Controle da janela
ipcMain.handle('window-minimize', () => {
  if (mainWindow) {
    mainWindow.minimize();
  }
});

ipcMain.handle('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.handle('window-close', () => {
  if (mainWindow) {
    mainWindow.close();
  }
});

// Navegador Steam Workshop integrado
ipcMain.handle('open-steam-workshop', async (event, gameId = '311210') => {
  // Criar nova janela para o Steam Workshop
  const workshopWindow = new BrowserWindow({
    width: 1000,
    height: 700,
    parent: mainWindow,
    modal: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'workshop-preload.js')
    }
  });

  const workshopUrl = `https://steamcommunity.com/app/${gameId}/workshop/`;
  workshopWindow.loadURL(workshopUrl);

  workshopWindow.webContents.on('new-window', (event, url) => {
    event.preventDefault();
    
    // Extrair Workshop ID da URL se for um item do workshop
    const workshopIdMatch = url.match(/filedetails\/\?id=(\d+)/);
    if (workshopIdMatch) {
      const workshopId = workshopIdMatch[1];
      
      // Enviar ID para a janela principal
      mainWindow.webContents.send('workshop-item-selected', workshopId);
      
      // Fechar janela do workshop
      workshopWindow.close();
    } else {
      // Abrir outras URLs no navegador externo
      shell.openExternal(url);
    }
  });

  return true;
});

// Listener para itens selecionados no workshop (escolher sem baixar)
ipcMain.on('workshop-item-selected', (event, workshopId) => {
  console.log(`Mod selecionado: ${workshopId}`);
  
  // Notificar janela principal sobre seleção
  if (mainWindow) {
    mainWindow.webContents.send('workshop-item-selected', workshopId);
  }
});

// Listener para download direto de itens do workshop
ipcMain.on('workshop-download-item', (event, workshopId) => {
  console.log(`Download iniciado para mod: ${workshopId}`);
  
  // Fazer requisição para API de download
  fetch(`http://127.0.0.1:5000/api/download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ workshop_id: workshopId })
  })
  .then(response => response.json())
  .then(data => {
    console.log('Download response:', data);
    
    // Notificar janela principal sobre resultado
    if (mainWindow) {
      mainWindow.webContents.send('download-result', { workshopId, result: data });
    }
  })
  .catch(error => {
    console.error('Erro no download:', error);
    
    if (mainWindow) {
      mainWindow.webContents.send('download-error', { workshopId, error: error.message });
    }
  });
});

console.log('Electron main process iniciado');