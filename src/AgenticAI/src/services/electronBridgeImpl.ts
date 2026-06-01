/**
 * ElectronBridge Implementation
 * 
 * This module provides the implementation of the ElectronBridge interface
 * that delegates to the Electron IPC API.
 */

import type { ElectronBridge } from './electronBridge';

// ============================================================================
// ElectronBridge Implementation
// ============================================================================

export class DefaultElectronBridge implements ElectronBridge {
  private get api() {
    if (!window.electronAPI) {
      throw new Error('Electron API not available');
    }
    return window.electronAPI;
  }

  // Dialog
  async openDirectory(): Promise<string | null> {
    const result = await this.api.openDirectory();
    return result ?? null;
  }

  // File System
  async readDirectory(path: string): Promise<FileEntry[]> {
    return this.api.readDirectory(path);
  }

  async readFile(path: string): Promise<string | null> {
    return this.api.readFile(path);
  }

  async writeFile(path: string, content: string): Promise<void> {
    await this.api.writeFile(path, content);
  }

  async createFile(path: string): Promise<void> {
    await this.api.createFile(path);
  }

  async createDirectory(path: string): Promise<void> {
    await this.api.createDirectory(path);
  }

  async deleteFile(path: string): Promise<void> {
    await this.api.deleteFile(path);
  }

  async rename(oldPath: string, newPath: string): Promise<void> {
    await this.api.rename(oldPath, newPath);
  }

  // Git (legacy flat methods)
  async gitStatus(): Promise<GitStatus> {
    if (this.api.gitStatus) {
      return this.api.gitStatus();
    }
    // Fallback to structured git API
    const status = await this.api.git.status();
    return status || {
      modified: [],
      staged: [],
      created: [],
      deleted: [],
      not_added: [],
      current: '',
      tracking: null,
    };
  }

  async gitBranch(): Promise<string> {
    if (this.api.gitBranch) {
      return this.api.gitBranch();
    }
    const info = await this.api.git.info('');
    return info.branch;
  }

  async gitCommit(message: string): Promise<void> {
    if (this.api.gitCommit) {
      await this.api.gitCommit(message);
    } else {
      await this.api.git.commit('', message);
    }
  }

  async gitStage(files: string[]): Promise<void> {
    if (this.api.gitStage) {
      await this.api.gitStage(files);
    } else {
      await this.api.git.stage('', files);
    }
  }

  async gitUnstage(files: string[]): Promise<void> {
    if (this.api.gitUnstage) {
      await this.api.gitUnstage(files);
    } else {
      await this.api.git.unstage('', files);
    }
  }

  async gitCheckout(branch: string): Promise<void> {
    if (this.api.gitCheckout) {
      await this.api.gitCheckout(branch);
    } else {
      await this.api.git.checkout('', branch);
    }
  }

  async gitDiscard(path: string): Promise<void> {
    if (this.api.gitDiscard) {
      await this.api.gitDiscard(path);
    } else {
      await this.api.git.discard('', [path]);
    }
  }

  async gitLog(limit?: number): Promise<GitLogEntry[]> {
    if (this.api.gitLog) {
      return this.api.gitLog(limit);
    }
    return this.api.git.log('', limit);
  }

  async gitDiff(path?: string): Promise<string> {
    if (this.api.gitDiff) {
      return this.api.gitDiff(path);
    }
    return this.api.git.diff('', path);
  }

  // Terminal
  get terminal(): TerminalAPI {
    return this.api.terminal;
  }

  // AI
  get ai(): AIAPI {
    return this.api.ai;
  }

  // AI Agent (MCP)
  get aiAgent(): AIAgentAPI {
    if (!this.api.aiAgent) {
      return {
        connect: async () => ({ success: false, error: 'AI Agent not available' }),
        disconnect: async () => ({ success: false }),
        status: async () => ({ connected: false, reconnectAttempts: 0, pendingRequests: 0 }),
        listTools: async () => ({ success: false, error: 'AI Agent not available' }),
        callTool: async () => ({ success: false, error: 'AI Agent not available' }),
        hardware: {
          validate: async () => ({ success: false, error: 'AI Agent not available' }),
          planInit: async () => ({ success: false, error: 'AI Agent not available' }),
          reason: async () => ({ success: false, error: 'AI Agent not available' }),
        },
        firmware: {
          analyze: async () => ({ success: false, error: 'AI Agent not available' }),
          debug: async () => ({ success: false, error: 'AI Agent not available' }),
          generateCode: async () => ({ success: false, error: 'AI Agent not available' }),
        },
        knowledge: {
          query: async () => ({ success: false, error: 'AI Agent not available' }),
          crossValidate: async () => ({ success: false, error: 'AI Agent not available' }),
        },
        listResources: async () => ({ success: false, error: 'AI Agent not available' }),
        readResource: async () => ({ success: false, error: 'AI Agent not available' }),
        listPrompts: async () => ({ success: false, error: 'AI Agent not available' }),
        getPrompt: async () => ({ success: false, error: 'AI Agent not available' }),
        subscribe: async () => ({ success: false, error: 'AI Agent not available' }),
        unsubscribe: async () => ({ success: false, error: 'AI Agent not available' }),
        onEvent: () => {},
      };
    }
    return this.api.aiAgent;
  }

  // Storage
  get storage(): StorageAPI {
    return this.api.storage;
  }

  // Steering
  get steering(): SteeringAPI {
    if (!this.api.steering) {
      return {
        load: async () => ({ success: false, context: {} }),
      };
    }
    return this.api.steering;
  }

  // Settings
  async getSettings(): Promise<AppSettings | null> {
    if (this.api.storage.getSettings) {
      return this.api.storage.getSettings() as Promise<AppSettings | null>;
    }
    return null;
  }

  async saveSettings(settings: AppSettings): Promise<void> {
    if (this.api.storage.saveSettings) {
      await this.api.storage.saveSettings(settings);
    }
  }

  // Events
  onFileChange(callback: (path: string) => void): void {
    this.api.onFileChange(callback);
  }

  onGitStatusChange(callback: () => void): void {
    this.api.onGitStatusChange(callback);
  }
}

// ============================================================================
// Singleton export
// ============================================================================

let _bridge: ElectronBridge | null = null;

export const electronBridge = new DefaultElectronBridge();

export function setElectronBridge(bridge: ElectronBridge): void {
  _bridge = bridge;
}

export function getElectronBridge(): ElectronBridge {
  if (_bridge) {
    return _bridge;
  }
  return electronBridge;
}
