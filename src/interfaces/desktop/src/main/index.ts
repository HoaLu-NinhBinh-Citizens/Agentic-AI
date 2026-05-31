import { app, BrowserWindow, ipcMain, shell, dialog, Menu } from 'electron';
import { join, dirname, basename } from 'path';
import { spawn, ChildProcess } from 'child_process';
import { readFile, readdir, writeFile, mkdir, unlink, rename } from 'fs/promises';
import { existsSync } from 'fs';
import * as net from 'net';
import * as fs from 'fs';

// ============================================
// AgenticAI - Main Process
// ============================================

const isDev = !app.isPackaged;
let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

const BACKEND_HOST = '127.0.0.1';
const BACKEND_PORT = 8001;

// ============================================
// Steering Files
// ============================================

const STEERING_FILE_NAMES = [
  'AGENTS.md',
  'CLAUDE.md',
  'product.md',
  'tech.md',
  'structure.md',
  'requirements.md',
];

async function getSteeringFiles(workspacePath: string): Promise<Array<{ name: string; path: string; content: string }>> {
  const files: Array<{ name: string; path: string; content: string }> = [];
  
  for (const fileName of STEERING_FILE_NAMES) {
    const possiblePaths = [
      join(workspacePath, fileName),
      join(workspacePath, '.ai_support', fileName),
      join(workspacePath, '.cursor', fileName),
      join(workspacePath, '.kiro', fileName),
    ];
    
    for (const filePath of possiblePaths) {
      try {
        if (existsSync(filePath)) {
          const content = await readFile(filePath, 'utf-8');
          files.push({ name: fileName, path: filePath, content });
          break;
        }
      } catch {
        // File doesn't exist, skip
      }
    }
  }
  
  return files;
}

// ============================================
// AI Agent (Mock Implementation)
// ============================================

interface AIContext {
  workspacePath: string;
  steeringFiles: Array<{ name: string; path: string; content: string }>;
  currentSpec?: { title: string; description: string };
  currentTasks: Array<{ id: string; title: string; status: string }>;
  openFiles: string[];
}

async function processAIMessage(message: string, context: AIContext): Promise<{
  message: string;
  tasks?: Array<{ title: string; description?: string; priority: string }>;
  codeSnippets?: Array<{ language: string; code: string; filePath?: string }>;
}> {
  const lowerMsg = message.toLowerCase();
  
  // Generate AI response based on message content
  let response = '';
  let tasks: Array<{ title: string; description?: string; priority: string }> | undefined;
  let codeSnippets: Array<{ language: string; code: string; filePath?: string }> | undefined;
  
  // Context summary
  const steeringSummary = context.steeringFiles.length > 0
    ? `\nTôi đã đọc ${context.steeringFiles.length} steering files: ${context.steeringFiles.map(f => f.name).join(', ')}`
    : '\nChưa tìm thấy steering files trong workspace.';
  
  // Analyze user message and respond
  if (lowerMsg.includes('tạo') || lowerMsg.includes('create') || lowerMsg.includes('viết')) {
    response = `Tôi sẽ giúp bạn tạo mã.${steeringSummary}`;
    
    // Generate code based on keywords
    if (lowerMsg.includes('function') || lowerMsg.includes('hàm')) {
      codeSnippets = [{
        language: 'typescript',
        code: `// Auto-generated function\n// TODO: Replace with actual implementation\n\nexport async function ${extractName(message)}() {\n  // Your implementation here\n  console.log('Function called');\n}`,
        filePath: 'src/generated/function.ts',
      }];
    }
  } else if (lowerMsg.includes('task') || lowerMsg.includes('công việc') || lowerMsg.includes('todo')) {
    response = `Tôi sẽ phân tích và tạo task list.${steeringSummary}`;
    
    // Generate task breakdown
    tasks = [
      { title: 'Phân tích yêu cầu', description: 'Đọc và hiểu spec hiện tại', priority: 'high' },
      { title: 'Thiết kế kiến trúc', description: 'Thiết kế module và interface', priority: 'high' },
      { title: 'Implement core features', description: 'Viết code cho các features chính', priority: 'medium' },
      { title: 'Viết unit tests', description: 'Tạo test coverage', priority: 'medium' },
      { title: 'Review và optimize', description: 'Kiểm tra code quality', priority: 'low' },
    ];
  } else if (lowerMsg.includes('spec') || lowerMsg.includes('yêu cầu')) {
    response = `Tôi đã đọc steering files và sẵn sàng hỗ trợ.${steeringSummary}`;
    response += `\n\n## Spec hiện tại:\n- **Workspace**: ${context.workspacePath}`;
    if (context.currentSpec) {
      response += `\n- **Title**: ${context.currentSpec.title}`;
      response += `\n- **Description**: ${context.currentSpec.description}`;
    }
    response += `\n- **Tasks**: ${context.currentTasks.length} công việc`;
  } else if (lowerMsg.includes('file') || lowerMsg.includes('tệp')) {
    response = `Tôi có thể giúp bạn quản lý files.${steeringSummary}`;
    response += `\n\n**Files đang mở**: ${context.openFiles.length} files`;
  } else {
    // Default response with context
    response = `Tôi đã hiểu: "${message}"${steeringSummary}`;
    response += `\n\n**Workspace**: ${context.workspacePath}`;
    response += `\n**Steering Files**: ${context.steeringFiles.length} files đã đọc`;
    response += `\n**Tasks**: ${context.currentTasks.length} công việc`;
    response += `\n\nTôi có thể giúp bạn:\n- 📝 Tạo và quản lý spec/tasks\n- 💻 Viết code theo yêu cầu\n- 🔍 Phân tích codebase\n- 🐛 Debug và fix lỗi\n- 📖 Đọc và tổng hợp steering files`;
  }
  
  return { message: response, tasks, codeSnippets };
}

function extractName(message: string): string {
  const match = message.match(/(?:tạo|create|viết)?\s*(?:function|hàm)?\s*(\w+)/i);
  return match ? match[1] : 'newFunction';
}

// ============================================
// Spec & Task Storage
// ============================================

function getKiroPath(workspacePath: string): string {
  return join(workspacePath, '.kiro');
}

async function ensureKiroDir(workspacePath: string): Promise<void> {
  const kiroPath = getKiroPath(workspacePath);
  if (!existsSync(kiroPath)) {
    await mkdir(kiroPath, { recursive: true });
  }
}

async function loadSpec(workspacePath: string): Promise<{ id: string; title: string; description: string; requirements: string[] } | null> {
  try {
    const specPath = join(getKiroPath(workspacePath), 'spec.json');
    if (existsSync(specPath)) {
      const content = await readFile(specPath, 'utf-8');
      return JSON.parse(content);
    }
  } catch {
    // File doesn't exist or invalid JSON
  }
  return null;
}

async function saveSpec(workspacePath: string, spec: { id: string; title: string; description: string; requirements: string[] }): Promise<void> {
  await ensureKiroDir(workspacePath);
  const specPath = join(getKiroPath(workspacePath), 'spec.json');
  await writeFile(specPath, JSON.stringify(spec, null, 2), 'utf-8');
}

async function loadTasks(workspacePath: string): Promise<Array<{ id: string; title: string; description?: string; status: string; priority: string }>> {
  try {
    const tasksPath = join(getKiroPath(workspacePath), 'tasks.json');
    if (existsSync(tasksPath)) {
      const content = await readFile(tasksPath, 'utf-8');
      return JSON.parse(content);
    }
  } catch {
    // File doesn't exist or invalid JSON
  }
  return [];
}

async function saveTasks(workspacePath: string, tasks: Array<{ id: string; title: string; description?: string; status: string; priority: string }>): Promise<void> {
  await ensureKiroDir(workspacePath);
  const tasksPath = join(getKiroPath(workspacePath), 'tasks.json');
  await writeFile(tasksPath, JSON.stringify(tasks, null, 2), 'utf-8');
}

// ============================================
// Backend Server
// ============================================

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

// ============================================
// Window Management
// ============================================

function createMenu(): void {
  const template: Electron.MenuItemConstructorOptions[] = [
    {
      label: 'File',
      submenu: [
        { label: 'New File', accelerator: 'CmdOrCtrl+N', click: () => mainWindow?.webContents.send('menu-action', 'new-file') },
        { label: 'Open File...', accelerator: 'CmdOrCtrl+O', click: () => mainWindow?.webContents.send('menu-action', 'open-file') },
        { type: 'separator' },
        { label: 'Save', accelerator: 'CmdOrCtrl+S', click: () => mainWindow?.webContents.send('menu-action', 'save') },
        { type: 'separator' },
        { role: 'quit' },
      ],
    },
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        { role: 'selectAll' },
      ],
    },
    {
      label: 'View',
      submenu: [
        { label: 'Toggle Sidebar', accelerator: 'CmdOrCtrl+B', click: () => mainWindow?.webContents.send('menu-action', 'toggle-sidebar') },
        { label: 'Toggle Task Panel', accelerator: 'CmdOrCtrl+Shift+T', click: () => mainWindow?.webContents.send('menu-action', 'toggle-task-panel') },
        { label: 'Toggle Chat', accelerator: 'CmdOrCtrl+Shift+C', click: () => mainWindow?.webContents.send('menu-action', 'toggle-chat') },
        { type: 'separator' },
        { role: 'reload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    {
      label: 'AI',
      submenu: [
        { label: 'New Spec', accelerator: 'CmdOrCtrl+Shift+N', click: () => mainWindow?.webContents.send('menu-action', 'new-spec') },
        { label: 'Generate Tasks', click: () => mainWindow?.webContents.send('menu-action', 'generate-tasks') },
        { type: 'separator' },
        { label: 'Read Steering Files', click: () => mainWindow?.webContents.send('menu-action', 'read-steering') },
      ],
    },
    {
      label: 'Help',
      submenu: [
        { label: 'About AgenticAI', click: () => {
          dialog.showMessageBox(mainWindow!, {
            type: 'info',
            title: 'About AgenticAI',
            message: 'AgenticAI v1.0.0',
            detail: 'AI-powered coding assistant like Cursor + Kiro\n\nBuilt with Electron + React + TypeScript',
          });
        }},
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1000,
    minHeight: 700,
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

// ============================================
// IPC Handlers
// ============================================

function setupIPCHandlers(): void {
  // Backend
  ipcMain.handle('get-backend-url', () => `http://${BACKEND_HOST}:${BACKEND_PORT}`);
  
  ipcMain.handle('get-workspace-path', () => {
    return isDev
      ? join(__dirname, '../../../../../../../')
      : join(process.resourcesPath, '..');
  });
  
  ipcMain.handle('open-external', async (_, url: string) => {
    await shell.openExternal(url);
  });

  // File System
  ipcMain.handle('read-file', async (_, filePath: string) => {
    try {
      return await readFile(filePath, 'utf-8');
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

  ipcMain.handle('write-file', async (_, filePath: string, content: string) => {
    try {
      await writeFile(filePath, content, 'utf-8');
    } catch (error) {
      console.error('Error writing file:', error);
      throw error;
    }
  });

  ipcMain.handle('create-directory', async (_, dirPath: string) => {
    try {
      await mkdir(dirPath, { recursive: true });
    } catch (error) {
      console.error('Error creating directory:', error);
      throw error;
    }
  });

  ipcMain.handle('delete-file', async (_, filePath: string) => {
    try {
      await unlink(filePath);
    } catch (error) {
      console.error('Error deleting file:', error);
      throw error;
    }
  });

  ipcMain.handle('rename-file', async (_, oldPath: string, newPath: string) => {
    try {
      await rename(oldPath, newPath);
    } catch (error) {
      console.error('Error renaming file:', error);
      throw error;
    }
  });

  // AI Agent
  ipcMain.handle('get-steering-files', async () => {
    const workspacePath = isDev
      ? join(__dirname, '../../../../../../../')
      : join(process.resourcesPath, '..');
    return await getSteeringFiles(workspacePath);
  });

  ipcMain.handle('send-to-ai', async (_, message: string, context: AIContext) => {
    return await processAIMessage(message, context);
  });

  // Spec & Tasks
  ipcMain.handle('load-spec', async () => {
    const workspacePath = isDev
      ? join(__dirname, '../../../../../../../')
      : join(process.resourcesPath, '..');
    return await loadSpec(workspacePath);
  });

  ipcMain.handle('save-spec', async (_, spec) => {
    const workspacePath = isDev
      ? join(__dirname, '../../../../../../../')
      : join(process.resourcesPath, '..');
    await saveSpec(workspacePath, spec);
  });

  ipcMain.handle('load-tasks', async () => {
    const workspacePath = isDev
      ? join(__dirname, '../../../../../../../')
      : join(process.resourcesPath, '..');
    return await loadTasks(workspacePath);
  });

  ipcMain.handle('save-tasks', async (_, tasks) => {
    const workspacePath = isDev
      ? join(__dirname, '../../../../../../../')
      : join(process.resourcesPath, '..');
    await saveTasks(workspacePath, tasks);
  });

  // File Dialogs
  ipcMain.handle('show-open-dialog', async (_, options) => {
    return await dialog.showOpenDialog(mainWindow!, options);
  });

  ipcMain.handle('show-save-dialog', async (_, options) => {
    return await dialog.showSaveDialog(mainWindow!, options);
  });
}

// ============================================
// App Lifecycle
// ============================================

app.whenReady().then(async () => {
  console.log('[Main] Starting AgenticAI...');
  
  setupIPCHandlers();
  createMenu();
  
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
