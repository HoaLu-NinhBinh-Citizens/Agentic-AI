/**
 * IPC Handler: Storage
 * Handles all storage operations with validation
 */
const { z } = require('zod');

// Validation schemas
const updateSettingsSchema = z.record(z.unknown());
const setAPIKeySchema = z.string().min(1);
const setWorkspaceSchema = z.string().min(1);
const saveTasksSchema = z.array(
  z.object({
    id: z.string(),
    title: z.string(),
    description: z.string().optional(),
    completed: z.boolean(),
    createdAt: z.string(),
    updatedAt: z.string(),
  })
);
const saveChatSchema = z.array(
  z.object({
    id: z.string(),
    role: z.enum(['user', 'assistant', 'system']),
    content: z.string(),
    timestamp: z.string(),
  })
);
const updateUIStateSchema = z.record(z.unknown());
const updateOpenFilesSchema = z.object({
  files: z.array(z.string()),
  activeFile: z.string().nullable().optional(),
});

// Error handler helper
function handleError(error, context) {
  console.error(`[Storage Handler] ${context}:`, error);
  return { error: error.message };
}

// IPC Handlers
function registerStorageHandlers(ipcMain, { storage }) {
  // Get Settings
  ipcMain.handle('storage:getSettings', async () => {
    try {
      if (!storage) return {};
      return storage.getSettings();
    } catch (error) {
      return handleError(error, 'getSettings');
    }
  });

  // Update Settings
  ipcMain.handle('storage:updateSettings', async (_, updates) => {
    try {
      const validated = updateSettingsSchema.parse(updates);
      if (!storage) return false;
      storage.updateSettings(validated);
      return true;
    } catch (error) {
      return handleError(error, 'updateSettings');
    }
  });

  // Get API Key
  ipcMain.handle('storage:getAPIKey', async () => {
    try {
      if (!storage) return null;
      return storage.getAPIKey();
    } catch (error) {
      return handleError(error, 'getAPIKey');
    }
  });

  // Set API Key
  ipcMain.handle('storage:setAPIKey', async (_, key) => {
    try {
      const validated = setAPIKeySchema.parse(key);
      if (!storage) return false;
      storage.setAPIKey(validated);
      return true;
    } catch (error) {
      return handleError(error, 'setAPIKey');
    }
  });

  // Has API Key
  ipcMain.handle('storage:hasAPIKey', async () => {
    try {
      if (!storage) return false;
      return storage.hasAPIKey();
    } catch (error) {
      return handleError(error, 'hasAPIKey');
    }
  });

  // Get Workspace
  ipcMain.handle('storage:getWorkspace', async () => {
    try {
      if (!storage) return null;
      return storage.getCurrentWorkspace();
    } catch (error) {
      return handleError(error, 'getWorkspace');
    }
  });

  // Set Workspace
  ipcMain.handle('storage:setWorkspace', async (_, workspacePath) => {
    try {
      const validated = setWorkspaceSchema.parse(workspacePath);
      if (!storage) return false;
      storage.setCurrentWorkspace(validated);
      return true;
    } catch (error) {
      return handleError(error, 'setWorkspace');
    }
  });

  // Get Tasks
  ipcMain.handle('storage:getTasks', async () => {
    try {
      if (!storage) return [];
      return storage.getTasks();
    } catch (error) {
      return handleError(error, 'getTasks');
    }
  });

  // Save Tasks
  ipcMain.handle('storage:saveTasks', async (_, tasks) => {
    try {
      const validated = saveTasksSchema.parse(tasks);
      if (!storage) return false;
      storage.saveTasks(validated);
      return true;
    } catch (error) {
      return handleError(error, 'saveTasks');
    }
  });

  // Get Chat
  ipcMain.handle('storage:getChat', async () => {
    try {
      if (!storage) return { messages: [], conversationId: null };
      return storage.getChat();
    } catch (error) {
      return handleError(error, 'getChat');
    }
  });

  // Save Chat
  ipcMain.handle('storage:saveChat', async (_, messages) => {
    try {
      const validated = saveChatSchema.parse(messages);
      if (!storage) return false;
      storage.saveChat(validated);
      return true;
    } catch (error) {
      return handleError(error, 'saveChat');
    }
  });

  // Get UI State
  ipcMain.handle('storage:getUIState', async () => {
    try {
      if (!storage) return {};
      return storage.getUIState();
    } catch (error) {
      return handleError(error, 'getUIState');
    }
  });

  // Update UI State
  ipcMain.handle('storage:updateUIState', async (_, updates) => {
    try {
      const validated = updateUIStateSchema.parse(updates);
      if (!storage) return false;
      storage.updateUIState(validated);
      return true;
    } catch (error) {
      return handleError(error, 'updateUIState');
    }
  });

  // Get Open Files
  ipcMain.handle('storage:getOpenFiles', async () => {
    try {
      if (!storage) return { files: [], activeFile: null };
      return storage.getOpenFiles();
    } catch (error) {
      return handleError(error, 'getOpenFiles');
    }
  });

  // Update Open Files
  ipcMain.handle('storage:updateOpenFiles', async (_, updates) => {
    try {
      const validated = updateOpenFilesSchema.parse(updates);
      if (!storage) return false;
      storage.updateOpenFiles(validated);
      return true;
    } catch (error) {
      return handleError(error, 'updateOpenFiles');
    }
  });

  console.log('[Storage Handler] Registered all storage handlers with Zod validation');
}

module.exports = { registerStorageHandlers };
