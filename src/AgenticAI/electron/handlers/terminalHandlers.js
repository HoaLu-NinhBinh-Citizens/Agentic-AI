/**
 * Terminal IPC Handlers
 */

const { ipcMain } = require('electron');

let terminalManager = null;

function setTerminalManager(manager) {
  terminalManager = manager;
}

function registerTerminalHandlers() {
  // Create terminal session
  ipcMain.handle('terminal:create', async (_, cwd) => {
    if (!terminalManager) {
      return { id: null, error: 'Terminal service not available' };
    }
    try {
      const session = terminalManager.createSession(cwd);
      return { id: session.id };
    } catch (error) {
      return { id: null, error: error.message };
    }
  });

  // Send input to terminal
  ipcMain.handle('terminal:input', async (_, { id, data }) => {
    if (!terminalManager) return;
    const session = terminalManager.getSession(id);
    if (session) {
      session.write(data);
    }
  });

  // Resize terminal
  ipcMain.handle('terminal:resize', async (_, { id, cols, rows }) => {
    if (!terminalManager) return;
    const session = terminalManager.getSession(id);
    if (session) {
      session.resize(cols, rows);
    }
  });

  // Close terminal
  ipcMain.handle('terminal:close', async (_, id) => {
    if (!terminalManager) return false;
    return terminalManager.killSession(id);
  });
}

module.exports = {
  registerTerminalHandlers,
  setTerminalManager,
};
