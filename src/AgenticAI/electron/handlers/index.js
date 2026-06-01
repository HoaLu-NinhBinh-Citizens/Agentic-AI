/**
 * IPC Handlers Index
 * Exports all modularized IPC handlers
 */
const { registerFSHandlers } = require('./fsHandlers');
const { registerAIHandlers } = require('./aiHandlers');
const { registerStorageHandlers } = require('./storageHandlers');
const { registerGitHandlers } = require('./gitHandlers');
const { registerSteeringHandlers } = require('./steeringHandlers');

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
  
  // Storage handlers
  registerStorageHandlers(ipcMain, { storage: services.storage });
  
  // Git handlers
  registerGitHandlers(ipcMain, { gitIntegration: services.gitIntegration });
  
  // Steering handlers
  registerSteeringHandlers(ipcMain, { steeringParser: services.steeringParser });
  
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
