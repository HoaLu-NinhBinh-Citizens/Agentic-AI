/**
 * Default implementation of ElectronBridge that delegates to window.electronAPI
 */

import { ElectronBridge, FileEntry, GitStatus, GitLogEntry, ChatMessage, AIResponse, UIState, AppSettings, SteeringContext } from './electronBridge';

declare global {
  interface Window {
    electronAPI: {
      platform?: string;
      openDirectory(): Promise<string | null>;
      readDirectory(path: string): Promise<FileEntry[]>;
      readFile(path: string): Promise<string | null>;
      writeFile(path: string, content: string): Promise<boolean>;
      createFile(path: string): Promise<boolean>;
      createDirectory(path: string): Promise<boolean>;
      deleteFile(path: string): Promise<boolean>;
      gitStatus(): Promise<GitStatus>;
      gitBranch(): Promise<string>;
      gitCommit(message: string): Promise<string>;
      gitStage(files: string[]): Promise<boolean>;
      gitUnstage(files: string[]): Promise<boolean>;
      gitCheckout(branch: string): Promise<boolean>;
      gitDiscard(path: string): Promise<boolean>;
      gitLog(limit?: number): Promise<GitLogEntry[]>;
      gitDiff(path?: string): Promise<string>;
      terminal: {
        write(id: string, data: string): void;
        onData(callback: (id: string, data: string) => void): void;
        resize(id: string, cols: number, rows: number): void;
        clear(id: string): void;
        dispose(id: string): void;
      };
      ai: {
        isInitialized(): Promise<boolean>;
        chat(messages: ChatMessage[]): Promise<AIResponse>;
        generateCode(prompt: string): Promise<AIResponse>;
        codeReview(code: string, file: string): Promise<AIResponse>;
        explainCode(code: string): Promise<AIResponse>;
      };
      storage: {
        getWorkspace(): Promise<{ path: string } | null>;
        setWorkspace(path: string): Promise<boolean>;
        updateUIState(state: Partial<UIState>): Promise<boolean>;
        updateOpenFiles(files: { files: string[]; activeFile?: string }): Promise<boolean>;
        getUIState(): Promise<UIState>;
        getSettings?(): Promise<AppSettings | null>;
        saveSettings?(settings: AppSettings): Promise<boolean>;
      };
      steering?: {
        load(workspacePath: string): Promise<{ success: boolean; context: SteeringContext }>;
        save?(context: SteeringContext): Promise<boolean>;
      };
      onFileChange(callback: (path: string) => void): void;
      onGitStatusChange(callback: () => void): void;
      showContextMenu?(): void;
      minimizeWindow?(): void;
      maximizeWindow?(): void;
      closeWindow?(): void;
      isMaximized?(): Promise<boolean>;
    };
  }
}

export class DefaultElectronBridge implements ElectronBridge {
  private get api() {
    if (!window.electronAPI) {
      throw new Error('Electron API not available');
    }
    return window.electronAPI;
  }

  async openDirectory(): Promise<string | null> {
    return this.api.openDirectory();
  }

  async readDirectory(path: string): Promise<FileEntry[]> {
    return this.api.readDirectory(path);
  }

  async readFile(path: string): Promise<string | null> {
    return this.api.readFile(path);
  }

  async writeFile(path: string, content: string): Promise<boolean> {
    return this.api.writeFile(path, content);
  }

  async createFile(path: string): Promise<boolean> {
    return this.api.createFile(path);
  }

  async createDirectory(path: string): Promise<boolean> {
    return this.api.createDirectory(path);
  }

  async deleteFile(path: string): Promise<boolean> {
    return this.api.deleteFile(path);
  }

  async gitStatus(): Promise<GitStatus> {
    return this.api.gitStatus();
  }

  async gitBranch(): Promise<string> {
    return this.api.gitBranch();
  }

  async gitCommit(message: string): Promise<string> {
    return this.api.gitCommit(message);
  }

  async gitStage(files: string[]): Promise<boolean> {
    return this.api.gitStage(files);
  }

  async gitUnstage(files: string[]): Promise<boolean> {
    return this.api.gitUnstage(files);
  }

  async gitCheckout(branch: string): Promise<boolean> {
    return this.api.gitCheckout(branch);
  }

  async gitDiscard(path: string): Promise<boolean> {
    return this.api.gitDiscard(path);
  }

  async gitLog(limit?: number): Promise<GitLogEntry[]> {
    return this.api.gitLog(limit);
  }

  async gitDiff(path?: string): Promise<string> {
    return this.api.gitDiff(path);
  }

  get terminal() {
    return this.api.terminal;
  }

  get ai() {
    return this.api.ai;
  }

  get storage() {
    return this.api.storage;
  }

  get steering() {
    if (!this.api.steering) {
      return {
        load: async () => ({ success: false, context: {} }),
        save: async () => false,
      };
    }
    return this.api.steering;
  }

  async getSettings(): Promise<AppSettings | null> {
    if (this.api.storage.getSettings) {
      return this.api.storage.getSettings();
    }
    return null;
  }

  async saveSettings(settings: AppSettings): Promise<boolean> {
    if (this.api.storage.saveSettings) {
      return this.api.storage.saveSettings(settings);
    }
    return false;
  }

  onFileChange(callback: (path: string) => void): void {
    this.api.onFileChange(callback);
  }

  onGitStatusChange(callback: () => void): void {
    this.api.onGitStatusChange(callback);
  }
}

// Export singleton instance
export const electronBridge = new DefaultElectronBridge();
