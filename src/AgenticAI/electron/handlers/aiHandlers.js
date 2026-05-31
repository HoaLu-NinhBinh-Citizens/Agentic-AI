/**
 * AI Service IPC Handlers
 */

const { ipcMain } = require('electron');

let aiService = null;
let ollamaClient = null;
let steeringParser = null;

function setAIService(service) {
  aiService = service;
}

function setOllamaClient(client) {
  ollamaClient = client;
}

function setSteeringParser(parser) {
  steeringParser = parser;
}

function registerAIHandlers() {
  // AI Service handlers
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

  // Ollama handlers
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
    if (!ollamaClient) return false;
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

  // Steering parser handlers
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
}

module.exports = {
  registerAIHandlers,
  setAIService,
  setOllamaClient,
  setSteeringParser,
};
