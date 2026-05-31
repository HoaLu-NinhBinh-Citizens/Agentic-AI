/**
 * Storage IPC Handlers
 */

const { ipcMain } = require('electron');

let storage = null;

function setStorage(s) {
  storage = s;
}

function registerStorageHandlers() {
  // Settings handlers
  ipcMain.handle('storage:getSettings', async () => {
    if (!storage) return {};
    return storage.getSettings();
  });

  ipcMain.handle('storage:updateSettings', async (_, updates) => {
    if (!storage) return false;
    storage.updateSettings(updates);
    return true;
  });

  // API key handlers
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

  // Workspace handlers
  ipcMain.handle('storage:getWorkspace', async () => {
    if (!storage) return null;
    return storage.getCurrentWorkspace();
  });

  ipcMain.handle('storage:setWorkspace', async (_, workspacePath) => {
    if (!storage) return false;
    storage.setCurrentWorkspace(workspacePath);
    return true;
  });

  // Task handlers
  ipcMain.handle('storage:getTasks', async () => {
    if (!storage) return [];
    return storage.getTasks();
  });

  ipcMain.handle('storage:saveTasks', async (_, tasks) => {
    if (!storage) return false;
    storage.saveTasks(tasks);
    return true;
  });

  // Chat handlers
  ipcMain.handle('storage:getChat', async () => {
    if (!storage) return { messages: [], conversationId: null };
    return storage.getChat();
  });

  ipcMain.handle('storage:saveChat', async (_, messages) => {
    if (!storage) return false;
    storage.saveChat(messages);
    return true;
  });

  // UI state handlers
  ipcMain.handle('storage:getUIState', async () => {
    if (!storage) return {};
    return storage.getUIState();
  });

  ipcMain.handle('storage:updateUIState', async (_, updates) => {
    if (!storage) return false;
    storage.updateUIState(updates);
    return true;
  });

  // Open files handlers
  ipcMain.handle('storage:getOpenFiles', async () => {
    if (!storage) return { files: [], activeFile: null };
    return storage.getOpenFiles();
  });

  ipcMain.handle('storage:updateOpenFiles', async (_, updates) => {
    if (!storage) return false;
    storage.updateOpenFiles(updates);
    return true;
  });
}

module.exports = {
  registerStorageHandlers,
  setStorage,
};
