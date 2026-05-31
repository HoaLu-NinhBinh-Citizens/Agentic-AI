/**
 * IPC Handlers Index
 * 
 * Unified module that exports all handler registration functions
 * and provides a convenient registerAll function.
 */

const { registerFsHandlers, setMainWindow } = require('./fsHandlers');
const { registerGitHandlers, setGitIntegration } = require('./gitHandlers');
const { registerAIHandlers, setAIService, setOllamaClient, setSteeringParser } = require('./aiHandlers');
const { registerTerminalHandlers, setTerminalManager } = require('./terminalHandlers');
const { registerStorageHandlers, setStorage } = require('./storageHandlers');

/**
 * Register all IPC handlers
 * @param {Object} services - Object containing all service instances
 * @param {Object} services.mainWindow - Main Electron window
 * @param {Object} services.gitIntegration - Git integration service
 * @param {Object} services.aiService - AI service
 * @param {Object} services.ollamaClient - Ollama client
 * @param {Object} services.steeringParser - Steering parser
 * @param {Object} services.terminalManager - Terminal manager
 * @param {Object} services.storage - Storage service
 */
function registerAllHandlers(services) {
  const {
    mainWindow,
    gitIntegration,
    aiService,
    ollamaClient,
    steeringParser,
    terminalManager,
    storage,
  } = services;

  // Set dependencies for each handler module
  setMainWindow(mainWindow);
  setGitIntegration(gitIntegration);
  setAIService(aiService);
  setOllamaClient(ollamaClient);
  setSteeringParser(steeringParser);
  setTerminalManager(terminalManager);
  setStorage(storage);

  // Register all handlers
  registerFsHandlers();
  registerGitHandlers();
  registerAIHandlers();
  registerTerminalHandlers();
  registerStorageHandlers();

  console.log('[Main] All IPC handlers registered successfully');
}

module.exports = {
  // Individual handler registration
  registerFsHandlers,
  registerGitHandlers,
  registerAIHandlers,
  registerTerminalHandlers,
  registerStorageHandlers,
  
  // Individual setter functions
  setMainWindow,
  setGitIntegration,
  setAIService,
  setOllamaClient,
  setSteeringParser,
  setTerminalManager,
  setStorage,
  
  // Unified registration
  registerAllHandlers,
};
