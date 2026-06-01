/**
 * IPC Handler: Steering Parser
 * Handles all steering operations with validation
 */
const { z } = require('zod');

// Validation schemas
const loadSteeringSchema = z.string().min(1);
const getRelevantContextSchema = z.string().min(1);

// Error handler helper
function handleError(error, context) {
  console.error(`[Steering Handler] ${context}:`, error);
  return { error: error.message };
}

// IPC Handlers
function registerSteeringHandlers(ipcMain, { steeringParser }) {
  // Load Steering Files
  ipcMain.handle('steering:load', async (_, workspacePath) => {
    try {
      const validated = loadSteeringSchema.parse(workspacePath);
      if (!steeringParser) return { context: {} };
      steeringParser.setWorkspace(validated);
      const context = await steeringParser.loadSteeringFiles();
      return { success: true, context };
    } catch (error) {
      return handleError(error, 'load');
    }
  });

  // Get Context
  ipcMain.handle('steering:getContext', async () => {
    try {
      if (!steeringParser) return {};
      return steeringParser.getContext();
    } catch (error) {
      return handleError(error, 'getContext');
    }
  });

  // Get System Prompt
  ipcMain.handle('steering:getSystemPrompt', async () => {
    try {
      if (!steeringParser) return 'You are a helpful AI coding assistant.';
      return steeringParser.getSystemPrompt();
    } catch (error) {
      return handleError(error, 'getSystemPrompt');
    }
  });

  // Get Relevant Context
  ipcMain.handle('steering:getRelevantContext', async (_, query) => {
    try {
      const validated = getRelevantContextSchema.parse(query);
      if (!steeringParser) return '';
      return steeringParser.getRelevantContext(validated);
    } catch (error) {
      return handleError(error, 'getRelevantContext');
    }
  });

  console.log('[Steering Handler] Registered all steering handlers with Zod validation');
}

module.exports = { registerSteeringHandlers };
