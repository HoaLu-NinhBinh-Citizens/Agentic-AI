/**
 * Mock implementation of ElectronBridge for testing
 */

import { ElectronBridge, FileEntry, GitStatus, GitLogEntry, ChatMessage, AIResponse, UIState, AppSettings, SteeringContext } from '../../src/services/electronBridge';

export class MockElectronBridge implements ElectronBridge {
  // File System
  openDirectory = jest.fn().mockResolvedValue('/test/workspace');
  readDirectory = jest.fn().mockResolvedValue<FileEntry[]>([
    { name: 'src', path: '/test/workspace/src', isDirectory: true },
    { name: 'package.json', path: '/test/workspace/package.json', isDirectory: false },
  ]);
  readFile = jest.fn().mockResolvedValue('// test file content');
  writeFile = jest.fn().mockResolvedValue(true);
  createFile = jest.fn().mockResolvedValue(true);
  createDirectory = jest.fn().mockResolvedValue(true);
  deleteFile = jest.fn().mockResolvedValue(true);
  
  // Git
  gitStatus = jest.fn().mockResolvedValue<GitStatus>({
    modified: ['src/index.ts'],
    staged: [],
    created: ['src/new.ts'],
    deleted: [],
    not_added: [],
    current: 'main',
    tracking: 'origin/main',
  });
  gitBranch = jest.fn().mockResolvedValue('feature/test');
  gitCommit = jest.fn().mockResolvedValue('abc1234567890');
  gitStage = jest.fn().mockResolvedValue(true);
  gitUnstage = jest.fn().mockResolvedValue(true);
  gitCheckout = jest.fn().mockResolvedValue(true);
  gitDiscard = jest.fn().mockResolvedValue(true);
  gitLog = jest.fn().mockResolvedValue<GitLogEntry[]>([
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
    chat: jest.fn().mockResolvedValue<AIResponse>({ content: 'Mock AI response', error: null }),
    generateCode: jest.fn().mockResolvedValue<AIResponse>({ content: 'function test() {}', error: null }),
    codeReview: jest.fn().mockResolvedValue<AIResponse>({ content: 'No issues found', error: null }),
    explainCode: jest.fn().mockResolvedValue<AIResponse>({ content: 'This function does X', error: null }),
  };
  
  // Storage
  storage = {
    getWorkspace: jest.fn().mockResolvedValue<{ path: string } | null>({ path: '/test/workspace' }),
    setWorkspace: jest.fn().mockResolvedValue(true),
    updateUIState: jest.fn().mockResolvedValue(true),
    updateOpenFiles: jest.fn().mockResolvedValue(true),
    getUIState: jest.fn().mockResolvedValue<UIState>({ expandedFolders: [], openFiles: [] }),
  };
  
  // Steering
  steering = {
    load: jest.fn().mockResolvedValue<{ success: boolean; context: SteeringContext }>({
      success: true,
      context: { agents: '# Agents\nTest agents content', claude: '# Claude\nTest claude content' },
    }),
    save: jest.fn().mockResolvedValue(true),
  };
  
  // Settings
  getSettings = jest.fn().mockResolvedValue<AppSettings | null>({
    aiProvider: 'ollama',
    ollamaEndpoint: 'http://localhost:11434',
    ollamaModel: 'codellama',
  });
  saveSettings = jest.fn().mockResolvedValue(true);
  
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

  setReadDirectoryResult(entries: FileEntry[]): void {
    this.readDirectory = jest.fn().mockResolvedValue(entries);
  }

  setReadFileResult(content: string | null): void {
    this.readFile = jest.fn().mockResolvedValue(content);
  }

  setGitStatusResult(status: GitStatus): void {
    this.gitStatus = jest.fn().mockResolvedValue(status);
  }

  setAIResponse(response: AIResponse): void {
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
