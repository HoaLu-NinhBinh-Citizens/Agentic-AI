/**
 * File System IPC Handlers
 */

const fs = require('fs');
const path = require('path');
const { ipcMain, dialog } = require('electron');

let mainWindow = null;

function setMainWindow(window) {
  mainWindow = window;
}

function registerFsHandlers() {
  // Directory picker
  ipcMain.handle('dialog:openDirectory', async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory']
    });
    return result.filePaths[0];
  });

  // Read directory contents
  ipcMain.handle('fs:readDirectory', async (_, dirPath) => {
    try {
      const entries = await fs.promises.readdir(dirPath, { withFileTypes: true });
      return entries.map(entry => ({
        name: entry.name,
        isDirectory: entry.isDirectory(),
        path: path.join(dirPath, entry.name)
      }));
    } catch (error) {
      console.error('Error reading directory:', error);
      return [];
    }
  });

  // Read file contents
  ipcMain.handle('fs:readFile', async (_, filePath) => {
    try {
      return await fs.promises.readFile(filePath, 'utf-8');
    } catch (error) {
      console.error('Error reading file:', error);
      return null;
    }
  });

  // Write file contents
  ipcMain.handle('fs:writeFile', async (_, filePath, content) => {
    try {
      await fs.promises.writeFile(filePath, content, 'utf-8');
      return true;
    } catch (error) {
      console.error('Error writing file:', error);
      return false;
    }
  });

  // Create new file
  ipcMain.handle('fs:createFile', async (_, filePath) => {
    try {
      await fs.promises.writeFile(filePath, '', 'utf-8');
      return true;
    } catch (error) {
      console.error('Error creating file:', error);
      return false;
    }
  });

  // Create directory
  ipcMain.handle('fs:createDirectory', async (_, dirPath) => {
    try {
      await fs.promises.mkdir(dirPath, { recursive: true });
      return true;
    } catch (error) {
      console.error('Error creating directory:', error);
      return false;
    }
  });

  // Delete file
  ipcMain.handle('fs:deleteFile', async (_, filePath) => {
    try {
      await fs.promises.unlink(filePath);
      return true;
    } catch (error) {
      console.error('Error deleting file:', error);
      return false;
    }
  });

  // Rename file
  ipcMain.handle('fs:rename', async (_, oldPath, newPath) => {
    try {
      await fs.promises.rename(oldPath, newPath);
      return true;
    } catch (error) {
      console.error('Error renaming file:', error);
      return false;
    }
  });
}

module.exports = {
  registerFsHandlers,
  setMainWindow,
};
