const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

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
// IPC Handlers - AI Service
// ============================================================================
ipcMain.handle('ai:initialize', async (_, config) => {
  if (!aiService) return { success: false, error: 'AI service not available' };
  try {
    aiService.initialize(config);
    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
});

ipcMain.handle('ai:chat', async (_, messages, systemPrompt) => {
  if (!aiService) return { error: 'AI service not available' };
  if (!aiService.isInitialized()) return { error: 'AI not initialized' };
  try {
    const response = await aiService.chat(messages, systemPrompt);
    return { success: true, ...response };
  } catch (error) {
    return { error: error.message };
  }
});

ipcMain.handle('ai:codeReview', async (_, code, language, context) => {
  if (!aiService) return { error: 'AI service not available' };
  if (!aiService.isInitialized()) return { error: 'AI not initialized' };
  try {
    const response = await aiService.codeReview(code, language, context);
    return { success: true, content: response };
  } catch (error) {
    return { error: error.message };
  }
});

ipcMain.handle('ai:generateCode', async (_, spec, existingCode) => {
  if (!aiService) return { error: 'AI service not available' };
  if (!aiService.isInitialized()) return { error: 'AI not initialized' };
  try {
    const response = await aiService.generateCode(spec, existingCode);
    return { success: true, content: response };
  } catch (error) {
    return { error: error.message };
  }
});

ipcMain.handle('ai:isInitialized', async () => {
  return aiService ? aiService.isInitialized() : false;
});

// ============================================================================
// IPC Handlers - Ollama
// ============================================================================
ipcMain.handle('ollama:health', async (_, timeout = 3000) => {
  if (!ollamaClient) {
    return { available: false, error: 'Ollama client not initialized' };
  }
  try {
    return await ollamaClient.healthCheck(timeout, 2);
  } catch (error) {
    return { available: false, error: error.message };
  }
});

ipcMain.handle('ollama:listModels', async () => {
  if (!ollamaClient) return [];
  try {
    return await ollamaClient.listModels();
  } catch (error) {
    console.error('Failed to list models:', error);
    return [];
  }
});

ipcMain.handle('ollama:generate', async (event, options) => {
  if (!ollamaClient) {
    return { error: 'Ollama client not initialized' };
  }
  try {
    const result = await ollamaClient.generate(
      options,
      options.stream !== false ? (chunk) => {
        event.sender.send('ollama:chunk', chunk);
      } : undefined
    );
    return { content: result };
  } catch (error) {
    return { error: error.message };
  }
});

ipcMain.handle('ollama:pullModel', async (event, model) => {
  if (!ollamaClient) {
    return false;
  }
  return new Promise((resolve) => {
    ollamaClient.pullModel(model, (progress) => {
      event.sender.send('ollama:pullProgress', progress);
    }).then(resolve);
  });
});

ipcMain.handle('ollama:getContextLimit', async (_, model) => {
  if (!ollamaClient) return 4096;
  return ollamaClient.getContextLimit(model);
});

// ============================================================================
// IPC Handlers - Steering Parser
// ============================================================================
ipcMain.handle('steering:load', async (_, workspacePath) => {
  if (!steeringParser) return { context: {} };
  try {
    steeringParser.setWorkspace(workspacePath);
    const context = await steeringParser.loadSteeringFiles();
    return { success: true, context };
  } catch (error) {
    return { success: false, error: error.message, context: {} };
  }
});

ipcMain.handle('steering:getContext', async () => {
  if (!steeringParser) return {};
  return steeringParser.getContext();
});

ipcMain.handle('steering:getSystemPrompt', async () => {
  if (!steeringParser) return 'You are a helpful AI coding assistant.';
  return steeringParser.getSystemPrompt();
});

ipcMain.handle('steering:getRelevantContext', async (_, query) => {
  if (!steeringParser) return '';
  return steeringParser.getRelevantContext(query);
});

// ============================================================================
// IPC Handlers - Storage
// ============================================================================
ipcMain.handle('storage:getSettings', async () => {
  if (!storage) return {};
  return storage.getSettings();
});

ipcMain.handle('storage:updateSettings', async (_, updates) => {
  if (!storage) return false;
  storage.updateSettings(updates);
  return true;
});

ipcMain.handle('storage:getAPIKey', async () => {
  if (!storage) return null;
  return storage.getAPIKey();
});

ipcMain.handle('storage:setAPIKey', async (_, key) => {
  if (!storage) return false;
  storage.setAPIKey(key);
  return true;
});

ipcMain.handle('storage:hasAPIKey', async () => {
  if (!storage) return false;
  return storage.hasAPIKey();
});

ipcMain.handle('storage:getWorkspace', async () => {
  if (!storage) return null;
  return storage.getCurrentWorkspace();
});

ipcMain.handle('storage:setWorkspace', async (_, workspacePath) => {
  if (!storage) return false;
  storage.setCurrentWorkspace(workspacePath);
  return true;
});

ipcMain.handle('storage:getTasks', async () => {
  if (!storage) return [];
  return storage.getTasks();
});

ipcMain.handle('storage:saveTasks', async (_, tasks) => {
  if (!storage) return false;
  storage.saveTasks(tasks);
  return true;
});

ipcMain.handle('storage:getChat', async () => {
  if (!storage) return { messages: [], conversationId: null };
  return storage.getChat();
});

ipcMain.handle('storage:saveChat', async (_, messages) => {
  if (!storage) return false;
  storage.saveChat(messages);
  return true;
});

ipcMain.handle('storage:getUIState', async () => {
  if (!storage) return {};
  return storage.getUIState();
});

ipcMain.handle('storage:updateUIState', async (_, updates) => {
  if (!storage) return false;
  storage.updateUIState(updates);
  return true;
});

ipcMain.handle('storage:getOpenFiles', async () => {
  if (!storage) return { files: [], activeFile: null };
  return storage.getOpenFiles();
});

ipcMain.handle('storage:updateOpenFiles', async (_, updates) => {
  if (!storage) return false;
  storage.updateOpenFiles(updates);
  return true;
});

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
// Original File System Handlers (Enhanced)
// ============================================================================

function createWindow() {
  // Initialize Ollama client
  initializeOllamaClient();
  
  // Initialize Phase 3 services
  initializePhase3Services();
  
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

// IPC Handlers
ipcMain.handle('dialog:openDirectory', async () => {
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openDirectory']
  });
  return result.filePaths[0];
});

ipcMain.handle('fs:readDirectory', async (_, dirPath) => {
  try {
    const entries = await fs.promises.readdir(dirPath, { withFileTypes: true });
    return entries.map(entry => ({
      name: entry.name,
      isDirectory: entry.isDirectory(),
      path: path.join(dirPath, entry.name)
    }));
  } catch (error) {
    return [];
  }
});

ipcMain.handle('fs:readFile', async (_, filePath) => {
  try {
    return await fs.promises.readFile(filePath, 'utf-8');
  } catch (error) {
    return null;
  }
});

ipcMain.handle('fs:writeFile', async (_, filePath, content) => {
  try {
    await fs.promises.writeFile(filePath, content, 'utf-8');
    return true;
  } catch (error) {
    return false;
  }
});

ipcMain.handle('fs:createFile', async (_, filePath) => {
  try {
    await fs.promises.writeFile(filePath, '', 'utf-8');
    return true;
  } catch (error) {
    return false;
  }
});

ipcMain.handle('fs:createDirectory', async (_, dirPath) => {
  try {
    await fs.promises.mkdir(dirPath, { recursive: true });
    return true;
  } catch (error) {
    return false;
  }
});

ipcMain.handle('fs:deleteFile', async (_, filePath) => {
  try {
    await fs.promises.unlink(filePath);
    return true;
  } catch (error) {
    return false;
  }
});

ipcMain.handle('fs:rename', async (_, oldPath, newPath) => {
  try {
    await fs.promises.rename(oldPath, newPath);
    return true;
  } catch (error) {
    return false;
  }
});

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
// IPC Handlers - Terminal (Phase 3)
// ============================================================================
ipcMain.handle('terminal:create', async (_, cwd) => {
  if (!terminalManager) {
    return { id: null, error: 'Terminal service not available' };
  }
  try {
    const session = terminalManager.createSession(cwd);
    return { id: session.id };
  } catch (error) {
    return { id: null, error: error.message };
  }
});

ipcMain.handle('terminal:input', async (_, { id, data }) => {
  if (!terminalManager) return;
  const session = terminalManager.getSession(id);
  if (session) {
    session.write(data);
  }
});

ipcMain.handle('terminal:resize', async (_, { id, cols, rows }) => {
  if (!terminalManager) return;
  const session = terminalManager.getSession(id);
  if (session) {
    session.resize(cols, rows);
  }
});

ipcMain.handle('terminal:close', async (_, id) => {
  if (!terminalManager) return false;
  return terminalManager.killSession(id);
});

// ============================================================================
// IPC Handlers - Git Integration (Phase 3)
// ============================================================================
ipcMain.handle('git:info', async (_, workspacePath) => {
  if (!gitIntegration) {
    return { isRepo: false, branch: '', branches: [], status: null, remotes: [] };
  }
  try {
    return await gitIntegration.openRepository(workspacePath);
  } catch (error) {
    console.error('Git info error:', error);
    return { isRepo: false, branch: '', branches: [], status: null, remotes: [] };
  }
});

ipcMain.handle('git:status', async () => {
  if (!gitIntegration) return null;
  try {
    return await gitIntegration.getStatus();
  } catch (error) {
    console.error('Git status error:', error);
    return null;
  }
});

ipcMain.handle('git:log', async (_, { workspacePath, limit }) => {
  if (!gitIntegration) return [];
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.getLog(limit);
  } catch (error) {
    console.error('Git log error:', error);
    return [];
  }
});

ipcMain.handle('git:stage', async (_, { workspacePath, files }) => {
  if (!gitIntegration) return false;
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.stage(files);
  } catch (error) {
    console.error('Git stage error:', error);
    return false;
  }
});

ipcMain.handle('git:commit', async (_, { workspacePath, message }) => {
  if (!gitIntegration) return false;
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.commit(message);
  } catch (error) {
    console.error('Git commit error:', error);
    return false;
  }
});

ipcMain.handle('git:checkout', async (_, { workspacePath, branch }) => {
  if (!gitIntegration) return false;
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.checkout(branch);
  } catch (error) {
    console.error('Git checkout error:', error);
    return false;
  }
});

ipcMain.handle('git:diff', async (_, { workspacePath, file }) => {
  if (!gitIntegration) return '';
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.getDiff(file);
  } catch (error) {
    console.error('Git diff error:', error);
    return '';
  }
});

ipcMain.handle('git:unstage', async (_, { workspacePath, files }) => {
  if (!gitIntegration) return false;
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.unstage(files);
  } catch (error) {
    console.error('Git unstage error:', error);
    return false;
  }
});

ipcMain.handle('git:branch', async (_, { workspacePath, name, create }) => {
  if (!gitIntegration) return null;
  try {
    await gitIntegration.openRepository(workspacePath);
    if (create && name) {
      return await gitIntegration.createBranch(name);
    }
    return await gitIntegration.getCurrentBranch();
  } catch (error) {
    console.error('Git branch error:', error);
    return null;
  }
});

ipcMain.handle('git:discard', async (_, { workspacePath, files }) => {
  if (!gitIntegration) return false;
  try {
    await gitIntegration.openRepository(workspacePath);
    return await gitIntegration.discard(files);
  } catch (error) {
    console.error('Git discard error:', error);
    return false;
  }
});

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
