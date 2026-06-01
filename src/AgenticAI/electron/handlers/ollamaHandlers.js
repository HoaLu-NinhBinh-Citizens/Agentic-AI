/**
 * IPC Handler: Ollama
 * Handles all Ollama operations with validation
 */
const { z } = require('zod');

// Validation schemas
const healthCheckSchema = z.object({
  timeout: z.number().optional(),
});

const generateSchema = z.object({
  prompt: z.string(),
  model: z.string().optional(),
  stream: z.boolean().optional(),
  options: z.record(z.unknown()).optional(),
});

const pullModelSchema = z.string().min(1);

const contextLimitSchema = z.string().min(1).optional();

// Error handler helper
function handleError(error, context) {
  console.error(`[Ollama Handler] ${context}:`, error);
  return { error: error.message };
}

// IPC Handlers
function registerOllamaHandlers(ipcMain, { ollamaClient }) {
  // Health Check
  ipcMain.handle('ollama:health', async (_, timeout = 3000) => {
    try {
      const validated = healthCheckSchema.parse({ timeout });
      if (!ollamaClient) {
        return { available: false, error: 'Ollama client not initialized' };
      }
      return await ollamaClient.healthCheck(validated.timeout, 2);
    } catch (error) {
      return { available: false, error: error.message };
    }
  });

  // List Models
  ipcMain.handle('ollama:listModels', async () => {
    try {
      if (!ollamaClient) return [];
      return await ollamaClient.listModels();
    } catch (error) {
      console.error('[Ollama Handler] Failed to list models:', error);
      return [];
    }
  });

  // Generate
  ipcMain.handle('ollama:generate', async (event, options) => {
    try {
      const validated = generateSchema.parse(options);
      if (!ollamaClient) {
        return { error: 'Ollama client not initialized' };
      }
      const result = await ollamaClient.generate(
        validated,
        validated.stream !== false ? (chunk) => {
          event.sender.send('ollama:chunk', chunk);
        } : undefined
      );
      return { content: result };
    } catch (error) {
      return { error: error.message };
    }
  });

  // Pull Model
  ipcMain.handle('ollama:pullModel', async (event, model) => {
    try {
      const validated = pullModelSchema.parse(model);
      if (!ollamaClient) {
        return false;
      }
      return new Promise((resolve) => {
        ollamaClient.pullModel(validated, (progress) => {
          event.sender.send('ollama:pullProgress', progress);
        }).then(resolve);
      });
    } catch (error) {
      console.error('[Ollama Handler] Failed to pull model:', error);
      return false;
    }
  });

  // Get Context Limit
  ipcMain.handle('ollama:getContextLimit', async (_, model) => {
    try {
      const validated = contextLimitSchema.optional().parse(model);
      if (!ollamaClient) return 4096;
      return ollamaClient.getContextLimit(validated);
    } catch (error) {
      return 4096;
    }
  });

  console.log('[Ollama Handler] Registered all Ollama handlers with Zod validation');
}

module.exports = { registerOllamaHandlers };
