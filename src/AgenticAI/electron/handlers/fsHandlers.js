/**
 * IPC Handler: File System
 * Handles all file system operations with validation
 */
const { z } = require('zod');
const fs = require('fs');
const path = require('path');

// Validation schemas
const readDirectorySchema = z.string().min(1);
const readFileSchema = z.string().min(1);
const writeFileSchema = z.object({
  path: z.string().min(1),
  content: z.string(),
});
const createFileSchema = z.string().min(1);
const createDirectorySchema = z.string().min(1);
const deleteFileSchema = z.string().min(1);
const renameSchema = z.object({
  oldPath: z.string().min(1),
  newPath: z.string().min(1),
});

// Error handler helper
function handleError(error, context) {
  console.error(`[FS Handler] ${context}:`, error);
  return { error: error.message };
}

// IPC Handlers
function registerFSHandlers(ipcMain, mainWindow) {
  // Open Directory Dialog
  ipcMain.handle('dialog:openDirectory', async () => {
    const { dialog } = require('electron');
    const result = await dialog.showOpenDialog(mainWindow, {
      properties: ['openDirectory'],
    });
    return result.filePaths[0] || null;
  });

  // Read Directory
  ipcMain.handle('fs:readDirectory', async (_, dirPath) => {
    try {
      const validated = readDirectorySchema.parse(dirPath);
      const entries = await fs.promises.readdir(validated, { withFileTypes: true });
      return entries.map((entry) => ({
        name: entry.name,
        isDirectory: entry.isDirectory(),
        path: path.join(validated, entry.name),
      }));
    } catch (error) {
      return handleError(error, 'readDirectory');
    }
  });

  // Read File
  ipcMain.handle('fs:readFile', async (_, filePath) => {
    try {
      const validated = readFileSchema.parse(filePath);
      const content = await fs.promises.readFile(validated, 'utf-8');
      return content;
    } catch (error) {
      return handleError(error, 'readFile');
    }
  });

  // Write File
  ipcMain.handle('fs:writeFile', async (_, filePath, content) => {
    try {
      const validated = writeFileSchema.parse({ path: filePath, content });
      await fs.promises.writeFile(validated.path, validated.content, 'utf-8');
      return { success: true };
    } catch (error) {
      return handleError(error, 'writeFile');
    }
  });

  // Create File
  ipcMain.handle('fs:createFile', async (_, filePath) => {
    try {
      const validated = createFileSchema.parse(filePath);
      await fs.promises.writeFile(validated, '', 'utf-8');
      return { success: true };
    } catch (error) {
      return handleError(error, 'createFile');
    }
  });

  // Create Directory
  ipcMain.handle('fs:createDirectory', async (_, dirPath) => {
    try {
      const validated = createDirectorySchema.parse(dirPath);
      await fs.promises.mkdir(validated, { recursive: true });
      return { success: true };
    } catch (error) {
      return handleError(error, 'createDirectory');
    }
  });

  // Delete File
  ipcMain.handle('fs:deleteFile', async (_, filePath) => {
    try {
      const validated = deleteFileSchema.parse(filePath);
      await fs.promises.unlink(validated);
      return { success: true };
    } catch (error) {
      return handleError(error, 'deleteFile');
    }
  });

  // Rename
  ipcMain.handle('fs:rename', async (_, oldPath, newPath) => {
    try {
      const validated = renameSchema.parse({ oldPath, newPath });
      await fs.promises.rename(validated.oldPath, validated.newPath);
      return { success: true };
    } catch (error) {
      return handleError(error, 'rename');
    }
  });

  console.log('[FS Handler] Registered all FS handlers with Zod validation');
}

module.exports = { registerFSHandlers };
