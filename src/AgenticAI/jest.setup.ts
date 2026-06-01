import '@testing-library/jest-dom';

// Mock window.electronAPI
const mockElectronAPI = {
  openDirectory: jest.fn().mockResolvedValue('/test/path'),
  readDirectory: jest.fn().mockResolvedValue([]),
  readFile: jest.fn().mockResolvedValue(''),
  writeFile: jest.fn().mockResolvedValue(undefined),
  createFile: jest.fn().mockResolvedValue(undefined),
  createDirectory: jest.fn().mockResolvedValue(undefined),
  deleteFile: jest.fn().mockResolvedValue(undefined),
  rename: jest.fn().mockResolvedValue(undefined),
  ai: {
    initialize: jest.fn().mockResolvedValue({ success: true }),
    chat: jest.fn().mockResolvedValue({ success: true, content: 'Mock response' }),
    codeReview: jest.fn().mockResolvedValue({ success: true }),
    generateCode: jest.fn().mockResolvedValue({ success: true }),
    isInitialized: jest.fn().mockResolvedValue(true),
  },
  steering: {
    load: jest.fn().mockResolvedValue({}),
    getContext: jest.fn().mockResolvedValue({}),
    getSystemPrompt: jest.fn().mockResolvedValue(''),
    getRelevantContext: jest.fn().mockResolvedValue([]),
  },
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
    getUIState: jest.fn().mockResolvedValue({}),
    updateUIState: jest.fn().mockResolvedValue(undefined),
    getOpenFiles: jest.fn().mockResolvedValue([]),
    updateOpenFiles: jest.fn().mockResolvedValue(undefined),
  },
  code: {
    analyze: jest.fn().mockResolvedValue({}),
    review: jest.fn().mockResolvedValue([]),
    applyFix: jest.fn().mockResolvedValue({}),
    applyMultipleFixes: jest.fn().mockResolvedValue([]),
  },
  commands: {
    getAll: jest.fn().mockResolvedValue([]),
    execute: jest.fn().mockResolvedValue(undefined),
  },
  terminal: {
    create: jest.fn().mockResolvedValue('term-1'),
    input: jest.fn().mockResolvedValue(undefined),
    resize: jest.fn().mockResolvedValue(undefined),
    close: jest.fn().mockResolvedValue(undefined),
  },
  git: {
    info: jest.fn().mockResolvedValue({}),
    status: jest.fn().mockResolvedValue([]),
    log: jest.fn().mockResolvedValue([]),
    stage: jest.fn().mockResolvedValue(undefined),
    unstage: jest.fn().mockResolvedValue(undefined),
    commit: jest.fn().mockResolvedValue(undefined),
    checkout: jest.fn().mockResolvedValue(undefined),
    branch: jest.fn().mockResolvedValue([]),
    diff: jest.fn().mockResolvedValue(''),
    discard: jest.fn().mockResolvedValue(undefined),
  },
  search: jest.fn().mockResolvedValue([]),
  extension: {
    load: jest.fn().mockResolvedValue(undefined),
    unload: jest.fn().mockResolvedValue(undefined),
    list: jest.fn().mockResolvedValue([]),
    runDetector: jest.fn().mockResolvedValue([]),
    runAllDetectors: jest.fn().mockResolvedValue([]),
    executeCommand: jest.fn().mockResolvedValue(undefined),
  },
  ollamaHealth: jest.fn().mockResolvedValue({ available: false }),
  ollamaListModels: jest.fn().mockResolvedValue([]),
  ollamaGenerate: jest.fn().mockResolvedValue(''),
  ollamaPullModel: jest.fn().mockResolvedValue(true),
  ollamaGetContextLimit: jest.fn().mockResolvedValue(4096),
  app: {
    minimize: jest.fn().mockResolvedValue(undefined),
    maximize: jest.fn().mockResolvedValue(undefined),
    close: jest.fn().mockResolvedValue(undefined),
    getVersion: jest.fn().mockResolvedValue('1.0.0'),
  },
};

declare global {
  interface Window {
    electronAPI: typeof mockElectronAPI;
  }
}

window.electronAPI = mockElectronAPI;

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
