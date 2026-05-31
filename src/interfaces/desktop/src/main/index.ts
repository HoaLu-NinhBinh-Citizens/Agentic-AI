import { app, BrowserWindow, ipcMain, shell } from 'electron';
import { join } from 'path';
import { spawn, ChildProcess } from 'child_process';
import { readFile, readdir } from 'fs/promises';
import { existsSync } from 'fs';
import * as net from 'net';

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 8001;

async function waitForBackend(host: string, port: number, timeout = 30000): Promise<boolean> {
  const start = Date.now();
  while (Date.now() - start < timeout) {
    try {
      await new Promise<void>((resolve, reject) => {
        const socket = new net.Socket();
        socket.setTimeout(1000);
        socket.on('connect', () => {
          socket.destroy();
          resolve();
        });
        socket.on('timeout', () => {
          socket.destroy();
          reject(new Error('timeout'));
        });
        socket.on('error', () => {
          socket.destroy();
          reject(new Error('error'));
        });
        socket.connect(port, host);
      });
      return true;
    } catch {
      await new Promise(r => setTimeout(r, 500));
    }
  }
  return false;
}

function startBackend(): void {
  const backendPath = isDev
    ? join(__dirname, '../../../../../../../')
    : join(process.resourcesPath, 'app.asar.unpacked', '..');

  const pythonCmd = process.platform === 'win32' ? 'python' : 'python3';
  
  backendProcess = spawn(pythonCmd, [
    '-m', 'uvicorn',
    'interfaces.server.main:app',
    '--host', BACKEND_HOST,
    '--port', String(BACKEND_PORT),
    '--log-level', 'info',
  ], {
    cwd: backendPath,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  backendProcess.stdout?.on('data', (data: Buffer) => {
    console.log('[Backend]', data.toString().trim());
  });

  backendProcess.stderr?.on('data', (data: Buffer) => {
    console.error('[Backend Error]', data.toString().trim());
  });

  backendProcess.on('exit', (code) => {
    console.log(`[Backend] Process exited with code ${code}`);
  });
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    backgroundColor: '#0d1117',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
    titleBarStyle: 'hiddenInset',
    frame: true,
    show: false,
  });

  mainWindow.once('ready-to-show', () => {
    mainWindow?.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http')) {
      shell.openExternal(url);
    }
    return { action: 'deny' };
  });

  if (isDev) {
    await mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    await mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
  }
}

app.whenReady().then(async () => {
  console.log('[Main] Starting backend server...');
  startBackend();
  
  console.log('[Main] Waiting for backend to be ready...');
  const ready = await waitForBackend(BACKEND_HOST, BACKEND_PORT);
  if (ready) {
    console.log('[Main] Backend is ready');
  } else {
    console.warn('[Main] Backend not ready in time, continuing anyway');
  }

  await createWindow();

  app.on('activate', async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
});

// IPC handlers
ipcMain.handle('get-backend-url', () => {
  return `http://${BACKEND_HOST}:${BACKEND_PORT}`;
});

ipcMain.handle('get-workspace-path', () => {
  return isDev
    ? join(__dirname, '../../../../../../../')
    : join(process.resourcesPath, '..');
});

ipcMain.handle('open-external', async (_, url: string) => {
  await shell.openExternal(url);
});

// File system handlers
ipcMain.handle('read-file', async (_, filePath: string) => {
  try {
    const content = await readFile(filePath, 'utf-8');
    return content;
  } catch (error) {
    console.error('Error reading file:', error);
    throw error;
  }
});

ipcMain.handle('read-dir', async (_, dirPath: string) => {
  try {
    const items = await readdir(dirPath, { withFileTypes: true });
    return items.map((item) => ({
      name: item.name,
      path: join(dirPath, item.name),
      isDir: item.isDirectory(),
    }));
  } catch (error) {
    console.error('Error reading directory:', error);
    throw error;
  }
});
