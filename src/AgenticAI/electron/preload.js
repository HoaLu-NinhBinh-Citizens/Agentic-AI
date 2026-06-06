const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Dialog
  openDirectory: () => ipcRenderer.invoke('dialog:openDirectory'),
  
  // File System
  readDirectory: (path) => ipcRenderer.invoke('fs:readDirectory', path),
  readFile: (path) => ipcRenderer.invoke('fs:readFile', path),
  writeFile: (path, content) => ipcRenderer.invoke('fs:writeFile', path, content),
  createFile: (path) => ipcRenderer.invoke('fs:createFile', path),
  createDirectory: (path) => ipcRenderer.invoke('fs:createDirectory', path),
  deleteFile: (path) => ipcRenderer.invoke('fs:deleteFile', path),
  rename: (oldPath, newPath) => ipcRenderer.invoke('fs:rename', oldPath, newPath),
  
  // AI Service
  ai: {
    initialize: (config) => ipcRenderer.invoke('ai:initialize', config),
    chat: (messages, systemPrompt) => ipcRenderer.invoke('ai:chat', messages, systemPrompt),
    codeReview: (code, language, context) => ipcRenderer.invoke('ai:codeReview', code, language, context),
    generateCode: (spec, existingCode) => ipcRenderer.invoke('ai:generateCode', spec, existingCode),
    isInitialized: () => ipcRenderer.invoke('ai:isInitialized'),
    complete: (params) => ipcRenderer.invoke('ai:complete', params),
  },
  
  // Steering Parser
  steering: {
    load: (workspacePath) => ipcRenderer.invoke('steering:load', workspacePath),
    getContext: () => ipcRenderer.invoke('steering:getContext'),
    getSystemPrompt: () => ipcRenderer.invoke('steering:getSystemPrompt'),
    getRelevantContext: (query) => ipcRenderer.invoke('steering:getRelevantContext', query),
  },
  
  // Storage
  storage: {
    getSettings: () => ipcRenderer.invoke('storage:getSettings'),
    updateSettings: (updates) => ipcRenderer.invoke('storage:updateSettings', updates),
    getAPIKey: () => ipcRenderer.invoke('storage:getAPIKey'),
    setAPIKey: (key) => ipcRenderer.invoke('storage:setAPIKey', key),
    hasAPIKey: () => ipcRenderer.invoke('storage:hasAPIKey'),
    getWorkspace: () => ipcRenderer.invoke('storage:getWorkspace'),
    setWorkspace: (path) => ipcRenderer.invoke('storage:setWorkspace', path),
    getTasks: () => ipcRenderer.invoke('storage:getTasks'),
    saveTasks: (tasks) => ipcRenderer.invoke('storage:saveTasks', tasks),
    getChat: () => ipcRenderer.invoke('storage:getChat'),
    saveChat: (messages) => ipcRenderer.invoke('storage:saveChat', messages),
    getUIState: () => ipcRenderer.invoke('storage:getUIState'),
    updateUIState: (updates) => ipcRenderer.invoke('storage:updateUIState', updates),
    getOpenFiles: () => ipcRenderer.invoke('storage:getOpenFiles'),
    updateOpenFiles: (updates) => ipcRenderer.invoke('storage:updateOpenFiles', updates),
  },

  // Code Analysis (Phase 2)
  code: {
    analyze: (filePath, content) => ipcRenderer.invoke('code:analyze', { filePath, content }),
    review: (filePath, content) => ipcRenderer.invoke('code:review', { filePath, content }),
    applyFix: (fix) => ipcRenderer.invoke('fix:apply', fix),
    applyMultipleFixes: (fixes) => ipcRenderer.invoke('fix:applyMultiple', fixes),
  },

  // Command Palette (Phase 2)
  commands: {
    getAll: () => ipcRenderer.invoke('commands:getAll'),
    execute: (commandId) => ipcRenderer.invoke('commands:execute', commandId),
  },

  // Terminal (Phase 3)
  terminal: {
    create: (cwd) => ipcRenderer.invoke('terminal:create', cwd),
    input: (id, data) => ipcRenderer.invoke('terminal:input', { id, data }),
    resize: (id, cols, rows) => ipcRenderer.invoke('terminal:resize', { id, cols, rows }),
    close: (id) => ipcRenderer.invoke('terminal:close', id),
    onOutput: (id, callback) => {
      ipcRenderer.on(`terminal:output:${id}`, (_, output) => callback(output));
    },
  },
  terminalCreate: () => ipcRenderer.invoke('terminal:create'),
  terminalInput: (id, data) => ipcRenderer.invoke('terminal:input', { id, data }),
  terminalClose: (id) => ipcRenderer.invoke('terminal:close', id),
  terminalOnOutput: (id, callback) => {
    ipcRenderer.on(`terminal:output:${id}`, (_, output) => callback(output));
  },
  
  // Git Integration (Phase 3)
  git: {
    info: (workspacePath) => ipcRenderer.invoke('git:info', workspacePath),
    status: () => ipcRenderer.invoke('git:status'),
    log: (workspacePath, limit) => ipcRenderer.invoke('git:log', { workspacePath, limit }),
    stage: (workspacePath, files) => ipcRenderer.invoke('git:stage', { workspacePath, files }),
    unstage: (workspacePath, files) => ipcRenderer.invoke('git:unstage', { workspacePath, files }),
    commit: (workspacePath, message) => ipcRenderer.invoke('git:commit', { workspacePath, message }),
    checkout: (workspacePath, branch) => ipcRenderer.invoke('git:checkout', { workspacePath, branch }),
    branch: (workspacePath, name, create) => ipcRenderer.invoke('git:branch', { workspacePath, name, create }),
    diff: (workspacePath, file) => ipcRenderer.invoke('git:diff', { workspacePath, file }),
    discard: (workspacePath, files) => ipcRenderer.invoke('git:discard', { workspacePath, files }),
  },
  gitInfo: (workspacePath) => ipcRenderer.invoke('git:info', workspacePath),
  gitLog: (workspacePath, limit) => ipcRenderer.invoke('git:log', { workspacePath, limit }),
  gitStage: (workspacePath, files) => ipcRenderer.invoke('git:stage', { workspacePath, files }),
  gitCommit: (workspacePath, message) => ipcRenderer.invoke('git:commit', { workspacePath, message }),
  gitCheckout: (workspacePath, branch) => ipcRenderer.invoke('git:checkout', { workspacePath, branch }),
  
  // Search (Phase 3)
  search: (options) => ipcRenderer.invoke('search:query', options),
  
  // Extension System (Phase 3)
  extension: {
    load: (extension) => ipcRenderer.invoke('extension:load', extension),
    unload: (id) => ipcRenderer.invoke('extension:unload', id),
    list: () => ipcRenderer.invoke('extension:list'),
    runDetector: (id, code, context) => ipcRenderer.invoke('extension:runDetector', { id, code, context }),
    runAllDetectors: (code, context) => ipcRenderer.invoke('extension:runAllDetectors', { code, context }),
    executeCommand: (id, args) => ipcRenderer.invoke('extension:executeCommand', { id, args }),
  },
  
  // Ollama
  ollamaHealth: (timeout) => ipcRenderer.invoke('ollama:health', timeout),
  ollamaListModels: () => ipcRenderer.invoke('ollama:listModels'),
  ollamaGenerate: (options) => ipcRenderer.invoke('ollama:generate', options),
  ollamaPullModel: (model, onProgress) => {
    if (onProgress) {
      ipcRenderer.on('ollama:pullProgress', (_, progress) => onProgress(progress));
    }
    return ipcRenderer.invoke('ollama:pullModel', model);
  },
  ollamaGetContextLimit: (model) => ipcRenderer.invoke('ollama:getContextLimit', model),
  ollamaOnChunk: (callback) => {
    ipcRenderer.on('ollama:chunk', (_, chunk) => callback(chunk));
  },
  
  // App
  app: {
    minimize: () => ipcRenderer.invoke('app:minimize'),
    maximize: () => ipcRenderer.invoke('app:maximize'),
    close: () => ipcRenderer.invoke('app:close'),
    getVersion: () => ipcRenderer.invoke('app:getVersion'),
  },

  // Extension Marketplace
  marketplace: {
    search: (query, limit) => ipcRenderer.invoke('marketplace:search', { query, limit }),
    popular: () => ipcRenderer.invoke('marketplace:popular'),
    details: (namespace, name) => ipcRenderer.invoke('marketplace:details', { namespace, name }),
    install: (namespace, name) => ipcRenderer.invoke('marketplace:install', { namespace, name }),
    uninstall: (extensionId) => ipcRenderer.invoke('marketplace:uninstall', { extensionId }),
    installed: () => ipcRenderer.invoke('marketplace:installed'),
    onInstallProgress: (callback) => {
      ipcRenderer.on('marketplace:install-progress', (_, data) => callback(data));
    },
  },

  // AI Agent (MCP) - Python Agent Integration
  aiAgent: {
    // Connection
    connect: (options) => ipcRenderer.invoke('aiAgent:connect', options),
    disconnect: () => ipcRenderer.invoke('aiAgent:disconnect'),
    status: () => ipcRenderer.invoke('aiAgent:status'),

    // Tools
    listTools: () => ipcRenderer.invoke('aiAgent:listTools'),
    callTool: (name, args) => ipcRenderer.invoke('aiAgent:callTool', { name, arguments: args }),

    // Hardware tools
    hardware: {
      validate: (config) => ipcRenderer.invoke('aiAgent:hardware:validate', config),
      planInit: (params) => ipcRenderer.invoke('aiAgent:hardware:planInit', params),
      reason: (params) => ipcRenderer.invoke('aiAgent:hardware:reason', params),
    },

    // Firmware tools
    firmware: {
      analyze: (params) => ipcRenderer.invoke('aiAgent:firmware:analyze', params),
      debug: (params) => ipcRenderer.invoke('aiAgent:firmware:debug', params),
      generateCode: (params) => ipcRenderer.invoke('aiAgent:firmware:generateCode', params),
    },

    // Knowledge tools
    knowledge: {
      query: (params) => ipcRenderer.invoke('aiAgent:knowledge:query', params),
      crossValidate: (params) => ipcRenderer.invoke('aiAgent:knowledge:crossValidate', params),
    },

    // Resources
    listResources: () => ipcRenderer.invoke('aiAgent:listResources'),
    readResource: (uri) => ipcRenderer.invoke('aiAgent:readResource', uri),

    // Prompts
    listPrompts: () => ipcRenderer.invoke('aiAgent:listPrompts'),
    getPrompt: (name, args) => ipcRenderer.invoke('aiAgent:getPrompt', { name, arguments: args }),

    // Events
    subscribe: (eventName, channel) => ipcRenderer.invoke('aiAgent:subscribe', { eventName, channel }),
    unsubscribe: (eventName) => ipcRenderer.invoke('aiAgent:unsubscribe', { eventName }),
    onEvent: (channel, callback) => {
      ipcRenderer.on(`aiAgent:event:${channel}`, (_, event) => callback(event));
    },
  },
});
