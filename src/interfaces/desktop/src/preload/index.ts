import { contextBridge, ipcRenderer } from 'electron';

export interface FileItem {
  name: string;
  path: string;
  isDir: boolean;
}

export interface ElectronAPI {
  getBackendUrl: () => Promise<string>;
  getWorkspacePath: () => Promise<string>;
  openExternal: (url: string) => Promise<void>;
  readFile: (path: string) => Promise<string>;
  readDir: (path: string) => Promise<FileItem[]>;
  onBackendStatus: (callback: (status: 'connected' | 'disconnected') => void) => void;
}

const electronAPI: ElectronAPI = {
  getBackendUrl: () => ipcRenderer.invoke('get-backend-url'),
  getWorkspacePath: () => ipcRenderer.invoke('get-workspace-path'),
  openExternal: (url: string) => ipcRenderer.invoke('open-external', url),
  readFile: (path: string) => ipcRenderer.invoke('read-file', path),
  readDir: (path: string) => ipcRenderer.invoke('read-dir', path) as Promise<FileItem[]>,
  onBackendStatus: (callback) => {
    ipcRenderer.on('backend-status', (_, status) => callback(status));
  },
};

contextBridge.exposeInMainWorld('electronAPI', electronAPI);

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
