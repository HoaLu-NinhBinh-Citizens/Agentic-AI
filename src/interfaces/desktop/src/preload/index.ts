import { contextBridge, ipcRenderer } from 'electron';

// ============================================
// AgenticAI - Preload Bridge
// ============================================

interface FileItem {
  name: string;
  path: string;
  isDir: boolean;
}

interface SteeringFile {
  name: string;
  path: string;
  content: string;
}

interface AIContext {
  workspacePath: string;
  steeringFiles: SteeringFile[];
  currentSpec?: { title: string; description: string };
  currentTasks: Array<{ id: string; title: string; status: string }>;
  openFiles: string[];
}

interface AIResponse {
  message: string;
  tasks?: Array<{ title: string; description?: string; priority: string }>;
  codeSnippets?: Array<{ language: string; code: string; filePath?: string }>;
}

interface ElectronAPI {
  // Backend
  getBackendUrl: () => Promise<string>;
  getWorkspacePath: () => Promise<string>;
  openExternal: (url: string) => Promise<void>;
  
  // File System
  readFile: (path: string) => Promise<string>;
  readDir: (path: string) => Promise<FileItem[]>;
  writeFile: (path: string, content: string) => Promise<void>;
  createDirectory: (path: string) => Promise<void>;
  deleteFile: (path: string) => Promise<void>;
  renameFile: (oldPath: string, newPath: string) => Promise<void>;
  
  // AI Agent
  sendToAI: (message: string, context: AIContext) => Promise<AIResponse>;
  getSteeringFiles: () => Promise<SteeringFile[]>;
  
  // Spec & Tasks
  loadSpec: () => Promise<{ id: string; title: string; description: string; requirements: string[] } | null>;
  saveSpec: (spec: { id: string; title: string; description: string; requirements: string[] }) => Promise<void>;
  loadTasks: () => Promise<Array<{ id: string; title: string; description?: string; status: string; priority: string }>>;
  saveTasks: (tasks: Array<{ id: string; title: string; description?: string; status: string; priority: string }>) => Promise<void>;
  
  // Dialogs
  showOpenDialog: (options: Electron.OpenDialogOptions) => Promise<Electron.OpenDialogReturnValue>;
  showSaveDialog: (options: Electron.SaveDialogOptions) => Promise<Electron.SaveDialogReturnValue>;
  
  // Events
  onMenuAction: (callback: (action: string) => void) => void;
  onBackendStatus: (callback: (status: 'connected' | 'disconnected') => void) => void;
  onFileChange: (callback: (path: string) => void) => void;
}

const electronAPI: ElectronAPI = {
  // Backend
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  getWorkspacePath: () => ipcRenderer.invoke('get-workspace-path'),
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),
  
  // File System
  readFile: (path: string) => ipcRenderer.invoke('read-file', path),
  readDir: (path: string) => ipcRenderer.invoke('read-dir', path) as Promise<FileItem[]>,
  writeFile: (path: string, content: string) => ipcRenderer.invoke('write-file', path, content),
  createDirectory: (path: string) => ipcRenderer.invoke('create-directory', path),
  deleteFile: (path: string) => ipcRenderer.invoke('delete-file', path),
  renameFile: (oldPath: string, newPath: string) => ipcRenderer.invoke('rename-file', oldPath, newPath),
  
  // AI Agent
  sendToAI: (message: string, context: AIContext) => ipcRenderer.invoke('send-to-ai', message, context),
  getSteeringFiles: () => ipcRenderer.invoke('get-steering-files') as Promise<SteeringFile[]>,
  
  // Spec & Tasks
  loadSpec: () => ipcRenderer.invoke('load-spec'),
  saveSpec: (spec) => ipcRenderer.invoke('save-spec', spec),
  loadTasks: () => ipcRenderer.invoke('load-tasks'),
  saveTasks: (tasks) => ipcRenderer.invoke('save-tasks', tasks),
  
  // Dialogs
  showOpenDialog: (options) => ipcRenderer.invoke('show-open-dialog', options),
  showSaveDialog: (options) => ipcRenderer.invoke('show-save-dialog', options),
  
  // Events
  onMenuAction: (callback) => {
    ipcRenderer.on('menu-action', (_, action) => callback(action));
  },
  onBackendStatus: (callback) => {
    ipcRenderer.on('backend-status', (_, status) => callback(status));
  },
  onFileChange: (callback) => {
    ipcRenderer.on('file-change', (_, path) => callback(path));
  },
};

contextBridge.exposeInMainWorld('electronAPI', electronAPI);

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
