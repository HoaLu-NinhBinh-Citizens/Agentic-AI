/**
 * Git Integration IPC Handlers
 */

const { ipcMain } = require('electron');

let gitIntegration = null;

function setGitIntegration(integration) {
  gitIntegration = integration;
}

function registerGitHandlers() {
  // Get repository info
  ipcMain.handle('git:info', async (_, workspacePath) => {
    if (!gitIntegration) {
      return { isRepo: false, branch: '', branches: [], status: null, remotes: [] };
    }
    try {
      return await gitIntegration.openRepository(workspacePath);
    } catch (error) {
      console.error('Git info error:', error);
      return { isRepo: false, branch: '', branches: [], status: null, remotes: [] };
    }
  });

  // Get git status
  ipcMain.handle('git:status', async () => {
    if (!gitIntegration) return null;
    try {
      return await gitIntegration.getStatus();
    } catch (error) {
      console.error('Git status error:', error);
      return null;
    }
  });

  // Get git log
  ipcMain.handle('git:log', async (_, { workspacePath, limit }) => {
    if (!gitIntegration) return [];
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.getLog(limit);
    } catch (error) {
      console.error('Git log error:', error);
      return [];
    }
  });

  // Stage files
  ipcMain.handle('git:stage', async (_, { workspacePath, files }) => {
    if (!gitIntegration) return false;
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.stage(files);
    } catch (error) {
      console.error('Git stage error:', error);
      return false;
    }
  });

  // Commit changes
  ipcMain.handle('git:commit', async (_, { workspacePath, message }) => {
    if (!gitIntegration) return false;
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.commit(message);
    } catch (error) {
      console.error('Git commit error:', error);
      return false;
    }
  });

  // Checkout branch
  ipcMain.handle('git:checkout', async (_, { workspacePath, branch }) => {
    if (!gitIntegration) return false;
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.checkout(branch);
    } catch (error) {
      console.error('Git checkout error:', error);
      return false;
    }
  });

  // Get diff
  ipcMain.handle('git:diff', async (_, { workspacePath, file }) => {
    if (!gitIntegration) return '';
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.getDiff(file);
    } catch (error) {
      console.error('Git diff error:', error);
      return '';
    }
  });

  // Unstage files
  ipcMain.handle('git:unstage', async (_, { workspacePath, files }) => {
    if (!gitIntegration) return false;
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.unstage(files);
    } catch (error) {
      console.error('Git unstage error:', error);
      return false;
    }
  });

  // Branch operations
  ipcMain.handle('git:branch', async (_, { workspacePath, name, create }) => {
    if (!gitIntegration) return null;
    try {
      await gitIntegration.openRepository(workspacePath);
      if (create && name) {
        return await gitIntegration.createBranch(name);
      }
      return await gitIntegration.getCurrentBranch();
    } catch (error) {
      console.error('Git branch error:', error);
      return null;
    }
  });

  // Discard changes
  ipcMain.handle('git:discard', async (_, { workspacePath, files }) => {
    if (!gitIntegration) return false;
    try {
      await gitIntegration.openRepository(workspacePath);
      return await gitIntegration.discard(files);
    } catch (error) {
      console.error('Git discard error:', error);
      return false;
    }
  });
}

module.exports = {
  registerGitHandlers,
  setGitIntegration,
};
