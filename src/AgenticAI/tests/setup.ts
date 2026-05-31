import '@testing-library/jest-dom';

// Create mock lazily to ensure window is available
let mockElectronAPI: Record<string, unknown> | null = null;

function getMockElectronAPI() {
  if (!mockElectronAPI) {
    mockElectronAPI = {
      platform: 'win32',
      openDirectory: jest.fn().mockResolvedValue(null),
      readDirectory: jest.fn().mockResolvedValue([]),
      readFile: jest.fn().mockResolvedValue(''),
      writeFile: jest.fn().mockResolvedValue(true),
      createFile: jest.fn().mockResolvedValue(true),
      createDirectory: jest.fn().mockResolvedValue(true),
      deleteFile: jest.fn().mockResolvedValue(true),
      gitStatus: jest.fn().mockResolvedValue({
        modified: [],
        staged: [],
        created: [],
        deleted: [],
        not_added: [],
        current: 'main',
        tracking: 'origin/main'
      }),
      gitBranch: jest.fn().mockResolvedValue('main'),
      gitCommit: jest.fn().mockResolvedValue(true),
      gitStage: jest.fn().mockResolvedValue(true),
      gitUnstage: jest.fn().mockResolvedValue(true),
      gitCheckout: jest.fn().mockResolvedValue(true),
      gitDiscard: jest.fn().mockResolvedValue(true),
      gitLog: jest.fn().mockResolvedValue([]),
      gitDiff: jest.fn().mockResolvedValue(''),
      terminal: {
        write: jest.fn(),
        onData: jest.fn(),
        resize: jest.fn(),
        clear: jest.fn(),
        dispose: jest.fn()
      },
      ai: {
        chat: jest.fn().mockResolvedValue({ content: 'Mock AI response', error: null }),
        isInitialized: jest.fn().mockResolvedValue(true),
        codeReview: jest.fn().mockResolvedValue('Mock code review'),
        generateCode: jest.fn().mockResolvedValue('Mock generated code'),
        explainCode: jest.fn().mockResolvedValue('Mock code explanation')
      },
      storage: {
        getWorkspace: jest.fn().mockResolvedValue(null),
        setWorkspace: jest.fn().mockResolvedValue(true),
        updateUIState: jest.fn().mockResolvedValue(true),
        updateOpenFiles: jest.fn().mockResolvedValue(true),
        getUIState: jest.fn().mockResolvedValue({ expandedFolders: [], openFiles: [] }),
        getSettings: jest.fn().mockResolvedValue(null),
        saveSettings: jest.fn().mockResolvedValue(true)
      },
      steering: {
        load: jest.fn().mockResolvedValue({ success: false, context: {} }),
        save: jest.fn().mockResolvedValue(true)
      },
      codeAnalyzer: {
        analyze: jest.fn().mockResolvedValue({ functions: [], imports: [], exports: [], complexity: 0, issues: [] }),
        getFunctions: jest.fn().mockResolvedValue([]),
        getImports: jest.fn().mockResolvedValue([])
      },
      onFileChange: jest.fn(),
      onGitStatusChange: jest.fn(),
      showContextMenu: jest.fn(),
      minimizeWindow: jest.fn(),
      maximizeWindow: jest.fn(),
      closeWindow: jest.fn(),
      isMaximized: jest.fn().mockResolvedValue(false)
    };
  }
  return mockElectronAPI;
}

// Extend Window interface
declare global {
  interface Window {
    electronAPI: Record<string, unknown>;
  }
}

// Set up global mock in beforeAll to ensure jsdom is ready
beforeAll(() => {
  window.electronAPI = getMockElectronAPI();
});

// Mock React hooks
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    if (typeof args[0] === 'string') {
      const msg = args[0];
      if (
        msg.includes('ReactDOM.render is no longer supported') ||
        msg.includes('An update to') ||
        msg.includes('not wrapped in act')
      ) {
        return;
      }
    }
    originalError.call(console, ...args);
  };
});

afterAll(() => {
  console.error = originalError;
});

// Reset mocks before each test
beforeEach(() => {
  jest.clearAllMocks();
  // Reset mock implementations to defaults
  mockElectronAPI = null;
  window.electronAPI = getMockElectronAPI();
  
  // Mock scrollIntoView for refs (used by ChatPanel)
  if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
    Element.prototype.scrollIntoView = jest.fn();
  }
});
