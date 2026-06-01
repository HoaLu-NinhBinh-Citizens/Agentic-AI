import '@testing-library/jest-dom';

// Mock window.electronAPI - use 'any' to avoid conflicts with vite-env.d.ts types
const mockElectronAPI = {
  // Dialog
  openDirectory: jest.fn().mockResolvedValue('/test/path'),
  
  // File System
  readDirectory: jest.fn().mockResolvedValue([]),
  readFile: jest.fn().mockResolvedValue(''),
  writeFile: jest.fn().mockResolvedValue(undefined),
  createFile: jest.fn().mockResolvedValue(undefined),
  createDirectory: jest.fn().mockResolvedValue(undefined),
  deleteFile: jest.fn().mockResolvedValue(undefined),
  rename: jest.fn().mockResolvedValue(undefined),
  
  // Legacy Git methods (flat structure)
  gitStatus: jest.fn().mockResolvedValue({
    modified: [],
    staged: [],
    created: [],
    deleted: [],
    not_added: [],
    current: 'main',
    tracking: null,
  }),
  gitBranch: jest.fn().mockResolvedValue('main'),
  gitCommit: jest.fn().mockResolvedValue(true),
  gitStage: jest.fn().mockResolvedValue(true),
  gitUnstage: jest.fn().mockResolvedValue(true),
  gitCheckout: jest.fn().mockResolvedValue(true),
  gitDiscard: jest.fn().mockResolvedValue(true),
  gitLog: jest.fn().mockResolvedValue([]),
  gitDiff: jest.fn().mockResolvedValue(''),
  
  // AI
  ai: {
    initialize: jest.fn().mockResolvedValue({ success: true }),
    chat: jest.fn().mockResolvedValue({ success: true, content: 'Mock response' }),
    codeReview: jest.fn().mockResolvedValue({ success: true }),
    generateCode: jest.fn().mockResolvedValue({ success: true }),
    explainCode: jest.fn().mockResolvedValue({ success: true }),
    isInitialized: jest.fn().mockResolvedValue(true),
  },
  
  // Steering
  steering: {
    load: jest.fn().mockResolvedValue({ success: true, context: {} }),
    getContext: jest.fn().mockResolvedValue({}),
    getSystemPrompt: jest.fn().mockResolvedValue(''),
    getRelevantContext: jest.fn().mockResolvedValue([]),
  },
  
  // Storage
  storage: {
    getSettings: jest.fn().mockResolvedValue({}),
    updateSettings: jest.fn().mockResolvedValue(undefined),
    getAPIKey: jest.fn().mockResolvedValue(null),
    setAPIKey: jest.fn().mockResolvedValue(undefined),
    hasAPIKey: jest.fn().mockResolvedValue(false),
    getWorkspace: jest.fn().mockResolvedValue(null),
    setWorkspace: jest.fn().mockResolvedValue(undefined),
    getTasks: jest.fn().mockResolvedValue([]),
    saveTasks: jest.fn().mockResolvedValue(undefined),
    getChat: jest.fn().mockResolvedValue([]),
    saveChat: jest.fn().mockResolvedValue(undefined),
    getUIState: jest.fn().mockResolvedValue({
      sidebarWidth: 250,
      taskPanelWidth: 300,
      chatPanelWidth: 350,
      terminalHeight: 200,
      activePanel: 'explorer',
      expandedFolders: [],
    }),
    updateUIState: jest.fn().mockResolvedValue(undefined),
    getOpenFiles: jest.fn().mockResolvedValue({ files: [], activeFile: null }),
    updateOpenFiles: jest.fn().mockResolvedValue(undefined),
  },
  
  // Code
  code: {
    analyze: jest.fn().mockResolvedValue({}),
    review: jest.fn().mockResolvedValue([]),
    applyFix: jest.fn().mockResolvedValue({}),
    applyMultipleFixes: jest.fn().mockResolvedValue([]),
  },
  
  // Terminal
  terminal: {
    write: jest.fn(),
    onData: jest.fn(),
    resize: jest.fn(),
    clear: jest.fn(),
    dispose: jest.fn(),
  },
  
  // Git (Phase 3 structured)
  git: {
    info: jest.fn().mockResolvedValue({
      isRepo: true,
      branch: 'main',
      branches: ['main'],
      status: null,
      remotes: [],
    }),
    status: jest.fn().mockResolvedValue(null),
    log: jest.fn().mockResolvedValue([]),
    stage: jest.fn().mockResolvedValue(true),
    unstage: jest.fn().mockResolvedValue(true),
    commit: jest.fn().mockResolvedValue(true),
    checkout: jest.fn().mockResolvedValue(true),
    branch: jest.fn().mockResolvedValue([]),
    diff: jest.fn().mockResolvedValue(''),
    discard: jest.fn().mockResolvedValue(true),
  },
  
  // Search
  search: jest.fn().mockResolvedValue([]),
  
  // Extension
  extension: {
    load: jest.fn().mockResolvedValue(undefined),
    unload: jest.fn().mockResolvedValue(undefined),
    list: jest.fn().mockResolvedValue([]),
    runDetector: jest.fn().mockResolvedValue([]),
    runAllDetectors: jest.fn().mockResolvedValue([]),
    executeCommand: jest.fn().mockResolvedValue(undefined),
  },
  
  // Ollama
  ollamaHealth: jest.fn().mockResolvedValue({ available: false }),
  ollamaListModels: jest.fn().mockResolvedValue([]),
  ollamaGenerate: jest.fn().mockResolvedValue(''),
  ollamaPullModel: jest.fn().mockResolvedValue(true),
  ollamaGetContextLimit: jest.fn().mockResolvedValue(4096),
  ollamaOnChunk: jest.fn(),
  
  // App
  app: {
    minimize: jest.fn(),
    maximize: jest.fn(),
    close: jest.fn(),
    getVersion: jest.fn().mockResolvedValue('1.0.0'),
  },
  
  // Events
  onFileChange: jest.fn(),
  onGitStatusChange: jest.fn(),
  showContextMenu: jest.fn(),
  minimizeWindow: jest.fn(),
  maximizeWindow: jest.fn(),
  closeWindow: jest.fn(),
  isMaximized: jest.fn().mockResolvedValue(false),
};

// Assign mock to window - use type assertion to avoid conflicts
(window as unknown as { electronAPI: typeof mockElectronAPI }).electronAPI = mockElectronAPI;

// Mock electron-store
jest.mock('electron-store', () => {
  return jest.fn().mockImplementation(() => ({
    get: jest.fn(),
    set: jest.fn(),
    has: jest.fn(),
    delete: jest.fn(),
    clear: jest.fn(),
    store: {},
  }));
});

// Mock fs
jest.mock('fs', () => require('memfs').fs);

// Mock scrollIntoView for jsdom
Element.prototype.scrollIntoView = jest.fn();
(window as unknown as { scrollIntoView: jest.Mock }).scrollIntoView = jest.fn();

// Silence console.error in tests unless explicitly needed
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (
      typeof args[0] === 'string' &&
      (args[0].includes('Warning:') || args[0].includes('React does not recognize'))
    ) {
      return;
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});
