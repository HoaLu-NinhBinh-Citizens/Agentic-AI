const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');

// Import modular handlers
const { registerAllHandlers } = require('./handlers');
const { mcpClient } = require('./mcp/mcpClient');

// Ollama Client
let ollamaClient = null;

function initializeOllamaClient() {
  try {
    const { ollamaClient: client } = require('./services/ollamaClient.cjs');
    ollamaClient = client;
    console.log('[Main] Ollama client initialized');
  } catch (error) {
    console.error('[Main] Failed to initialize Ollama client:', error);
    // Create a fallback client
    ollamaClient = {
      healthCheck: async () => ({ available: false, error: 'Not initialized' }),
      listModels: async () => [],
      generate: async () => '',
      pullModel: async () => false,
      getContextLimit: () => 4096,
    };
  }
}

// Terminal Manager (Phase 3)
let terminalManager = null;
let gitIntegration = null;
let searchEngine = null;
let extensionSystem = null;

function initializePhase3Services() {
  try {
    const { terminalManager: tm } = require('./services/terminal.cjs');
    const { gitIntegration: gi } = require('./services/gitIntegration.cjs');
    const { searchEngine: se } = require('./services/search.cjs');
    const { extensionSystem: es } = require('./services/extensionSystem.cjs');
    
    terminalManager = tm;
    gitIntegration = gi;
    searchEngine = se;
    extensionSystem = es;
    
    console.log('[Main] Phase 3 services initialized successfully');
  } catch (error) {
    console.error('[Main] Failed to initialize Phase 3 services:', error);
  }
}

// ============================================================================
// AI Service (Phase 1 - Real AI Integration)
// ============================================================================
let aiService = null;
let steeringParser = null;
let storage = null;

function initializeMainServices() {
  try {
    // Dynamic imports for ES modules
    const { aiService: AIService } = require('./services/aiService.cjs');
    const { steeringParser: SteeringParser } = require('./services/steeringParser.cjs');
    const { storage: Storage } = require('./services/storage.cjs');
    
    aiService = AIService;
    steeringParser = SteeringParser;
    storage = Storage;
    
    console.log('[Main] Services initialized successfully');
  } catch (error) {
    console.error('[Main] Failed to initialize services:', error);
  }
}

// ============================================================================
// Window Management
// ============================================================================
ipcMain.handle('app:minimize', () => {
  mainWindow?.minimize();
});

ipcMain.handle('app:maximize', () => {
  if (mainWindow?.isMaximized()) {
    mainWindow.unmaximize();
  } else {
    mainWindow?.maximize();
  }
});

ipcMain.handle('app:close', () => {
  mainWindow?.close();
});

ipcMain.handle('app:getVersion', () => {
  return app.getVersion();
});

// ============================================================================
// Window Creation
// ============================================================================

function createWindow() {
  // Initialize Ollama client
  initializeOllamaClient();
  
  // Initialize Phase 3 services
  initializePhase3Services();
  
  // Initialize main services
  initializeMainServices();
  
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1000,
    minHeight: 600,
    backgroundColor: '#1e1e1e',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    },
    titleBarStyle: 'hiddenInset',
    frame: process.platform === 'darwin' ? true : false
  });

  // Register all IPC handlers
  registerAllHandlers(ipcMain, {
    aiService,
    storage,
    steeringParser,
    gitIntegration,
    terminalManager,
    searchEngine,
    extensionSystem,
    ollamaClient,
    mcpClient,
  }, mainWindow);

  const isDev = !app.isPackaged;
  
  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});

// IPC Handlers are now registered in electron/handlers/index.js

// ============================================================================
// IPC Handlers - Code Analysis (Phase 2)
// ============================================================================
let codeAnalyzer = null;
let fixEngine = null;
let securityDetectors = null;

function initializeCodeAnalysis() {
  try {
    // Import code analyzer
    const codeAnalyzerPath = path.join(__dirname, '../src/main-process/codeAnalyzer');
    const fixEnginePath = path.join(__dirname, '../src/main-process/fixEngine');
    const securityDetectorPath = path.join(__dirname, '../src/main-process/detectors/securityDetector');

    // Use dynamic require for TypeScript transpiled modules
    try {
      codeAnalyzer = require(codeAnalyzerPath);
      fixEngine = require(fixEnginePath);
      securityDetectors = require(securityDetectorPath);
      console.log('[Main] Code analysis modules loaded successfully');
    } catch (requireError) {
      // Fallback: try to create placeholder modules
      console.log('[Main] Creating code analysis modules dynamically...');
      codeAnalyzer = createCodeAnalyzerModule();
      fixEngine = createFixEngineModule();
      securityDetectors = createSecurityDetectorModule();
    }
  } catch (error) {
    console.error('[Main] Failed to initialize code analysis:', error);
    // Create fallback modules
    codeAnalyzer = createCodeAnalyzerModule();
    fixEngine = createFixEngineModule();
    securityDetectors = createSecurityDetectorModule();
  }
}

// Fallback modules when Babel/transpilation is not available
function createCodeAnalyzerModule() {
  return {
    analyzeCode: (code, language) => ({
      functions: [],
      imports: [],
      exports: [],
      complexity: 1,
      issues: [],
    }),
    getLanguageFromExtension: (filename) => {
      const ext = filename.split('.').pop()?.toLowerCase();
      const map = { js: 'javascript', ts: 'typescript', py: 'python' };
      return map[ext] || 'javascript';
    },
  };
}

function createFixEngineModule() {
  return {
    applyFix: async (fix) => {
      try {
        const content = fs.readFileSync(fix.file, 'utf-8');
        const newContent = content.replace(fix.original, fix.replacement);
        fs.writeFileSync(fix.file, newContent, 'utf-8');
        return { success: true };
      } catch (error) {
        return { success: false, error: error.message };
      }
    },
  };
}

function createSecurityDetectorModule() {
  return {
    detectSecurityIssues: (code) => [],
    allSecurityDetectors: [],
  };
}

// Initialize code analysis on startup
initializeCodeAnalysis();

// ============================================================================
// MCP Client (Phase 1 - Python Agent Integration)
// ============================================================================
// mcpClient is already imported at the top of the file from './mcp/mcpClient'
// No additional initialization needed - the singleton is created in mcpClient.js

ipcMain.handle('code:analyze', async (_, { filePath, content }) => {
  try {
    if (!codeAnalyzer) {
      return { error: 'Code analyzer not available' };
    }
    const language = codeAnalyzer.getLanguageFromExtension(filePath);
    const result = codeAnalyzer.analyzeCode(content, language);
    return { success: true, ...result };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('code:review', async (_, { filePath, content }) => {
  try {
    if (!codeAnalyzer) {
      return { error: 'Code analyzer not available' };
    }
    const language = codeAnalyzer.getLanguageFromExtension(filePath);
    const analysis = codeAnalyzer.analyzeCode(content, language);

    // Run security detectors
    const securityIssues = securityDetectors?.detectSecurityIssues?.(content) || [];

    // Combine all issues
    const allIssues = [...analysis.issues, ...securityIssues];

    // Count by severity
    const counts = {
      error: allIssues.filter(i => i.severity === 'error').length,
      warning: allIssues.filter(i => i.severity === 'warning').length,
      info: allIssues.filter(i => i.severity === 'info').length,
    };

    return {
      success: true,
      filePath,
      analysis,
      securityIssues,
      allIssues,
      totalIssues: allIssues.length,
      ...counts,
    };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('fix:apply', async (_, fix) => {
  try {
    if (!fixEngine) {
      return { success: false, error: 'Fix engine not available' };
    }
    return await fixEngine.applyFix(fix);
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('fix:applyMultiple', async (_, fixes) => {
  try {
    if (!fixEngine) {
      return { success: false, error: 'Fix engine not available' };
    }
    return await fixEngine.applyFixes(fixes);
  } catch (error) {
    return { success: false, error: error.message };
  }
});

// ============================================================================
// IPC Handlers - Command Palette
// ============================================================================
ipcMain.handle('commands:getAll', async () => {
  // Return registered commands (loaded from commandPalette module)
  return {
    success: true,
    commands: getRegisteredCommands(),
  };
});

function getRegisteredCommands() {
  // Built-in commands
  return [
    { id: 'file.newFile', label: 'New File', shortcut: 'Ctrl+N', category: 'File' },
    { id: 'file.save', label: 'Save', shortcut: 'Ctrl+S', category: 'File' },
    { id: 'file.saveAll', label: 'Save All', shortcut: 'Ctrl+Shift+S', category: 'File' },
    { id: 'file.close', label: 'Close File', shortcut: 'Ctrl+W', category: 'File' },
    { id: 'edit.undo', label: 'Undo', shortcut: 'Ctrl+Z', category: 'Edit' },
    { id: 'edit.redo', label: 'Redo', shortcut: 'Ctrl+Y', category: 'Edit' },
    { id: 'edit.find', label: 'Find', shortcut: 'Ctrl+F', category: 'Edit' },
    { id: 'edit.replace', label: 'Find and Replace', shortcut: 'Ctrl+H', category: 'Edit' },
    { id: 'view.toggleSidebar', label: 'Toggle Sidebar', shortcut: 'Ctrl+B', category: 'View' },
    { id: 'view.toggleTerminal', label: 'Toggle Terminal', shortcut: 'Ctrl+`', category: 'View' },
    { id: 'ai.reviewCurrentFile', label: 'Review Current File', shortcut: 'Ctrl+Shift+R', category: 'AI' },
    { id: 'ai.fixAllIssues', label: 'Fix All Critical Issues', shortcut: 'Ctrl+Shift+F', category: 'AI' },
    { id: 'settings.open', label: 'Open Settings', shortcut: 'Ctrl+,', category: 'Settings' },
  ];
}

// ============================================================================
// IPC Handlers - Search (Phase 3)
// ============================================================================
ipcMain.handle('search:query', async (_, options) => {
  if (!searchEngine) {
    throw new Error('Search service not available');
  }
  try {
    return await searchEngine.search(options);
  } catch (error) {
    console.error('Search error:', error);
    throw error;
  }
});

// ============================================================================
// IPC Handlers - Extension System (Phase 3)
// ============================================================================
ipcMain.handle('extension:load', async (_, extension) => {
  if (!extensionSystem) return false;
  try {
    return await extensionSystem.loadExtension(extension);
  } catch (error) {
    console.error('Extension load error:', error);
    return false;
  }
});

ipcMain.handle('extension:unload', async (_, id) => {
  if (!extensionSystem) return false;
  return extensionSystem.unloadExtension(id);
});

ipcMain.handle('extension:list', async () => {
  if (!extensionSystem) return [];
  return extensionSystem.getAllExtensions();
});

ipcMain.handle('extension:runDetector', async (_, { id, code, context }) => {
  if (!extensionSystem) return [];
  return extensionSystem.runDetector(id, code, context);
});

ipcMain.handle('extension:runAllDetectors', async (_, { code, context }) => {
  if (!extensionSystem) return [];
  return extensionSystem.runAllDetectors(code, context);
});

ipcMain.handle('extension:executeCommand', async (_, { id, args }) => {
  if (!extensionSystem) throw new Error('Extension system not available');
  return await extensionSystem.executeCommand(id, ...args);
});
