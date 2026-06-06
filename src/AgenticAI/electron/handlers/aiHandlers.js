/**
 * IPC Handler: AI Service
 * Handles all AI operations with validation
 */
const { z } = require('zod');

// Validation schemas
const initializeSchema = z.object({
  provider: z.enum(['openai', 'anthropic', 'ollama']),
  apiKey: z.string().optional(),
  model: z.string().optional(),
  baseUrl: z.string().optional(),
});

const chatSchema = z.object({
  messages: z.array(
    z.object({
      role: z.enum(['user', 'assistant', 'system']),
      content: z.string(),
    })
  ),
  systemPrompt: z.string().optional(),
});

const codeReviewSchema = z.object({
  code: z.string(),
  language: z.string(),
  context: z.string().optional(),
});

const generateCodeSchema = z.object({
  spec: z.string(),
  existingCode: z.string().optional(),
});

// Error handler helper
function handleError(error, context) {
  console.error(`[AI Handler] ${context}:`, error);
  return { error: error.message };
}

// IPC Handlers
function registerAIHandlers(ipcMain, { aiService }) {
  // Initialize AI
  ipcMain.handle('ai:initialize', async (_, config) => {
    try {
      const validated = initializeSchema.parse(config);
      if (aiService) {
        aiService.initialize(validated);
        return { success: true };
      }
      return { success: false, error: 'AI service not available' };
    } catch (error) {
      return handleError(error, 'initialize');
    }
  });

  // Chat
  ipcMain.handle('ai:chat', async (_, messages, systemPrompt) => {
    try {
      const validated = chatSchema.parse({ messages, systemPrompt });
      if (!aiService) return { error: 'AI service not available' };
      if (!aiService.isInitialized()) return { error: 'AI not initialized' };
      
      const response = await aiService.chat(validated.messages, validated.systemPrompt);
      return { success: true, content: response };
    } catch (error) {
      return handleError(error, 'chat');
    }
  });

  // Code Review
  ipcMain.handle('ai:codeReview', async (_, code, language, context) => {
    try {
      const validated = codeReviewSchema.parse({ code, language, context });
      if (!aiService) return { error: 'AI service not available' };
      if (!aiService.isInitialized()) return { error: 'AI not initialized' };
      
      const response = await aiService.codeReview(
        validated.code,
        validated.language,
        validated.context
      );
      return { success: true, content: response };
    } catch (error) {
      return handleError(error, 'codeReview');
    }
  });

  // Generate Code
  ipcMain.handle('ai:generateCode', async (_, spec, existingCode) => {
    try {
      const validated = generateCodeSchema.parse({ spec, existingCode });
      if (!aiService) return { error: 'AI service not available' };
      if (!aiService.isInitialized()) return { error: 'AI not initialized' };
      
      const response = await aiService.generateCode(validated.spec, validated.existingCode);
      return { success: true, content: response };
    } catch (error) {
      return handleError(error, 'generateCode');
    }
  });

  // Is Initialized
  ipcMain.handle('ai:isInitialized', async () => {
    return aiService ? aiService.isInitialized() : false;
  });

  // Inline Completion (ghost text) — fill-in-the-middle style
  ipcMain.handle('ai:complete', async (_, params) => {
    try {
      const { prefix, suffix, language, maxTokens } = params || {};
      if (!aiService || !aiService.isInitialized()) {
        return { success: false, completion: '' };
      }

      // Build a focused FIM prompt for short, inline completions
      const systemPrompt =
        'You are a code completion engine. Complete the code at the cursor. ' +
        'Return ONLY the code that should be inserted at the cursor position. ' +
        'No explanations, no markdown fences, no repetition of existing code. ' +
        'Keep completions short (usually one line, at most a few lines).';

      const userPrompt =
        `Language: ${language || 'plaintext'}\n` +
        `Complete the code between <CURSOR> markers.\n\n` +
        `${prefix || ''}<CURSOR>${suffix || ''}`;

      const response = await aiService.chat(
        [{ role: 'user', content: userPrompt }],
        systemPrompt
      );

      // Clean up: strip markdown fences if model added them
      let completion = (response || '').trim();
      completion = completion.replace(/^```[\w]*\n?/, '').replace(/\n?```$/, '');

      // Cap length defensively
      const maxLen = (maxTokens || 120) * 4;
      if (completion.length > maxLen) {
        completion = completion.slice(0, maxLen);
      }

      return { success: true, completion };
    } catch (error) {
      console.error('[AI Handler] complete:', error);
      return { success: false, completion: '', error: error.message };
    }
  });

  console.log('[AI Handler] Registered all AI handlers with Zod validation');
}

module.exports = { registerAIHandlers };
