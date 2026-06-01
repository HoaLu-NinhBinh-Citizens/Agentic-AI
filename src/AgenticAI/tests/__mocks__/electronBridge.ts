/**
 * Mock implementation of ElectronBridge for testing
 */

import type { ElectronBridge } from '../../src/services/electronBridge';

export class MockElectronBridge implements ElectronBridge {
  // Dialog
  openDirectory = jest.fn().mockResolvedValue('/test/workspace');
  
  // File System
  readDirectory = jest.fn().mockResolvedValue([
    { name: 'src', path: '/test/workspace/src', isDirectory: true },
    { name: 'package.json', path: '/test/workspace/package.json', isDirectory: false },
  ]);
  readFile = jest.fn().mockResolvedValue('// test file content');
  writeFile = jest.fn().mockResolvedValue(undefined);
  createFile = jest.fn().mockResolvedValue(undefined);
  createDirectory = jest.fn().mockResolvedValue(undefined);
  deleteFile = jest.fn().mockResolvedValue(undefined);
  rename = jest.fn().mockResolvedValue(undefined);
  
  // Git (legacy flat methods)
  gitStatus = jest.fn().mockResolvedValue({
    modified: ['src/index.ts'],
    staged: [],
    created: ['src/new.ts'],
    deleted: [],
    not_added: [],
    current: 'main',
    tracking: 'origin/main',
  });
  gitBranch = jest.fn().mockResolvedValue('feature/test');
  gitCommit = jest.fn().mockResolvedValue(undefined);
  gitStage = jest.fn().mockResolvedValue(undefined);
  gitUnstage = jest.fn().mockResolvedValue(undefined);
  gitCheckout = jest.fn().mockResolvedValue(undefined);
  gitDiscard = jest.fn().mockResolvedValue(undefined);
  gitLog = jest.fn().mockResolvedValue([
    { hash: 'abc123', date: '2024-01-01', message: 'Initial commit', author: 'Test User' },
  ]);
  gitDiff = jest.fn().mockResolvedValue('+ added line\n- removed line');
  
  // Terminal
  terminal = {
    write: jest.fn(),
    onData: jest.fn(),
    resize: jest.fn(),
    clear: jest.fn(),
    dispose: jest.fn(),
  };
  
  // AI
  ai = {
    isInitialized: jest.fn().mockResolvedValue(true),
    chat: jest.fn().mockResolvedValue({ content: 'Mock AI response', error: undefined }),
    generateCode: jest.fn().mockResolvedValue({ content: 'function test() {}', error: undefined }),
    codeReview: jest.fn().mockResolvedValue({ content: 'No issues found', error: undefined }),
    explainCode: jest.fn().mockResolvedValue({ content: 'This function does X', error: undefined }),
  };
  
  // Storage
  storage = {
    getWorkspace: jest.fn().mockResolvedValue<{ path: string } | null>({ path: '/test/workspace' }),
    setWorkspace: jest.fn().mockResolvedValue(true),
    updateUIState: jest.fn().mockResolvedValue(true),
    updateOpenFiles: jest.fn().mockResolvedValue(true),
    getUIState: jest.fn().mockResolvedValue({
      sidebarWidth: 250,
      taskPanelWidth: 300,
      chatPanelWidth: 350,
      terminalHeight: 200,
      activePanel: 'explorer',
      expandedFolders: [],
    }),
  };
  
  // Steering
  steering = {
    load: jest.fn().mockResolvedValue<{ success: boolean; context: Record<string, string | undefined> }>({
      success: true,
      context: { agents: '# Agents\nTest agents content', claude: '# Claude\nTest claude content' },
    }),
    save: jest.fn().mockResolvedValue(true),
  };
  
  // Settings
  getSettings = jest.fn().mockResolvedValue({
    aiProvider: 'ollama' as const,
    ollamaEndpoint: 'http://localhost:11434',
    ollamaModel: 'codellama',
    maxTokens: 2048,
    temperature: 0.7,
    fontSize: 14,
    autoSave: true,
    autoSaveDelay: 1000,
  });
  saveSettings = jest.fn().mockResolvedValue(undefined);
  
  // Events
  onFileChange = jest.fn();
  onGitStatusChange = jest.fn();

  // Helper methods for testing
  resetAllMocks(): void {
    jest.clearAllMocks();
  }

  setOpenDirectoryResult(path: string | null): void {
    this.openDirectory = jest.fn().mockResolvedValue(path);
  }

  setReadDirectoryResult(entries: Array<{ name: string; path: string; isDirectory: boolean }>): void {
    this.readDirectory = jest.fn().mockResolvedValue(entries);
  }

  setReadFileResult(content: string | null): void {
    this.readFile = jest.fn().mockResolvedValue(content);
  }

  setGitStatusResult(status: { modified: string[]; staged: string[]; created: string[]; deleted: string[]; not_added: string[]; current: string; tracking: string | null }): void {
    this.gitStatus = jest.fn().mockResolvedValue(status);
  }

  setAIResponse(response: { content?: string; error?: string }): void {
    this.ai.chat = jest.fn().mockResolvedValue(response);
  }

  setAIInitialized(initialized: boolean): void {
    this.ai.isInitialized = jest.fn().mockResolvedValue(initialized);
  }

  setStorageWorkspaceResult(workspace: { path: string } | null): void {
    this.storage.getWorkspace = jest.fn().mockResolvedValue(workspace);
  }
}

// Export singleton instance for convenience
export const mockBridge = new MockElectronBridge();

// Helper function to create a custom mock bridge with specific behavior
export function createMockBridge(overrides?: Partial<MockElectronBridge>): MockElectronBridge {
  const bridge = new MockElectronBridge();
  
  if (overrides) {
    Object.assign(bridge, overrides);
  }
  
  return bridge;
}
