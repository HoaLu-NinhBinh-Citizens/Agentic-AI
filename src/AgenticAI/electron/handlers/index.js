/**
 * IPC Handlers Index
 * Exports all modularized IPC handlers
 */
const { registerFSHandlers } = require('./fsHandlers');
const { registerAIHandlers } = require('./aiHandlers');
const { registerStorageHandlers } = require('./storageHandlers');
const { registerGitHandlers } = require('./gitHandlers');
const { registerSteeringHandlers } = require('./steeringHandlers');
const { registerTerminalHandlers } = require('./terminalHandlers');
const { registerOllamaHandlers } = require('./ollamaHandlers');
const { registerAIAgentHandlers } = require('./aiAgentHandlers');
const { registerMarketplaceHandlers } = require('./marketplaceHandlers');

/**
 * Register all IPC handlers with the main process
 * @param {Electron.IpcMain} ipcMain - The IPC main instance
 * @param {Object} services - All available services
 */
function registerAllHandlers(ipcMain, services, mainWindow) {
  console.log('[Handlers] Registering all IPC handlers...');
  
  // File System handlers
  registerFSHandlers(ipcMain, mainWindow);
  
  // AI handlers
  registerAIHandlers(ipcMain, { aiService: services.aiService });
  
  // Ollama handlers
  registerOllamaHandlers(ipcMain, { ollamaClient: services.ollamaClient });
  
  // Storage handlers
  registerStorageHandlers(ipcMain, { storage: services.storage });
  
  // Git handlers
  registerGitHandlers(ipcMain, { gitIntegration: services.gitIntegration });
  
  // Steering handlers
  registerSteeringHandlers(ipcMain, { steeringParser: services.steeringParser });
  
  // Terminal handlers
  registerTerminalHandlers(ipcMain, { terminalManager: services.terminalManager });

  // AI Agent (MCP) handlers
  registerAIAgentHandlers(ipcMain, { mcpClient: services.mcpClient });

  // Extension Marketplace handlers
  registerMarketplaceHandlers(ipcMain, mainWindow);

  console.log('[Handlers] All IPC handlers registered successfully');
}

module.exports = {
  registerAllHandlers,
  registerFSHandlers,
  registerAIHandlers,
  registerStorageHandlers,
  registerGitHandlers,
  registerSteeringHandlers,
};
