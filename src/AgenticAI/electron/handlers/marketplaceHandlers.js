/**
 * Extension Marketplace IPC Handlers
 * 
 * Provides IPC bridge between renderer and marketplace service:
 * - marketplace:search — Search extensions
 * - marketplace:popular — Get popular extensions
 * - marketplace:details — Get extension details
 * - marketplace:install — Install extension
 * - marketplace:uninstall — Uninstall extension
 * - marketplace:installed — List installed extensions
 */

const {
  searchExtensions,
  getPopularExtensions,
  getExtensionDetails,
  installExtension,
  uninstallExtension,
  listInstalledExtensions,
} = require('../services/extensionMarketplace.cjs');

function registerMarketplaceHandlers(ipcMain, mainWindow) {
  console.log('[Marketplace Handler] Registering marketplace IPC handlers...');

  ipcMain.handle('marketplace:search', async (_event, { query, limit }) => {
    return await searchExtensions(query || '', limit || 20);
  });

  ipcMain.handle('marketplace:popular', async () => {
    return await getPopularExtensions();
  });

  ipcMain.handle('marketplace:details', async (_event, { namespace, name }) => {
    return await getExtensionDetails(namespace, name);
  });

  ipcMain.handle('marketplace:install', async (_event, { namespace, name }) => {
    const result = await installExtension(namespace, name, (progress) => {
      // Send progress to renderer
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('marketplace:install-progress', {
          extensionId: `${namespace}.${name}`,
          progress,
        });
      }
    });
    return result;
  });

  ipcMain.handle('marketplace:uninstall', async (_event, { extensionId }) => {
    return uninstallExtension(extensionId);
  });

  ipcMain.handle('marketplace:installed', async () => {
    return listInstalledExtensions();
  });

  console.log('[Marketplace Handler] Marketplace IPC handlers registered');
}

module.exports = { registerMarketplaceHandlers };
