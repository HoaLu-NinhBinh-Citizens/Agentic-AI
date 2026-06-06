/**
 * Extension Marketplace — connects to Open VSX Registry.
 * 
 * Provides:
 * - Search extensions from Open VSX (open-source VS Code marketplace)
 * - Download and install .vsix extensions
 * - List installed extensions
 * - Uninstall extensions
 * 
 * Registry: https://open-vsx.org/api
 */

const https = require('https');
const http = require('http');
const fs = require('fs');
const path = require('path');
const { app } = require('electron');

const OPEN_VSX_API = 'https://open-vsx.org/api';
const EXTENSIONS_DIR = path.join(app?.getPath('userData') || '.', 'extensions');

// Ensure extensions directory exists
if (!fs.existsSync(EXTENSIONS_DIR)) {
  fs.mkdirSync(EXTENSIONS_DIR, { recursive: true });
}

/**
 * Search extensions from Open VSX Registry.
 * @param {string} query - Search query
 * @param {number} limit - Max results (default 20)
 * @returns {Promise<Array>} List of extension results
 */
async function searchExtensions(query, limit = 20) {
  const url = `${OPEN_VSX_API}/-/search?query=${encodeURIComponent(query)}&size=${limit}&sortBy=downloadCount&sortOrder=desc`;

  try {
    const data = await fetchJSON(url);
    if (!data || !data.extensions) return [];

    return data.extensions.map(ext => ({
      id: `${ext.namespace}.${ext.name}`,
      name: ext.displayName || ext.name,
      publisher: ext.namespace,
      description: ext.description || '',
      version: ext.version || '',
      downloads: ext.downloadCount || 0,
      rating: ext.averageRating || 0,
      icon: ext.files?.icon || '',
      categories: ext.categories || [],
      installed: isExtensionInstalled(`${ext.namespace}.${ext.name}`),
    }));
  } catch (error) {
    console.error('[Marketplace] Search failed:', error.message);
    return [];
  }
}

/**
 * Get popular/recommended extensions.
 * @returns {Promise<Array>}
 */
async function getPopularExtensions() {
  return searchExtensions('', 30);
}

/**
 * Get extension details.
 * @param {string} namespace - Publisher namespace
 * @param {string} name - Extension name
 * @returns {Promise<object|null>}
 */
async function getExtensionDetails(namespace, name) {
  const url = `${OPEN_VSX_API}/${namespace}/${name}`;

  try {
    const data = await fetchJSON(url);
    if (!data) return null;

    return {
      id: `${data.namespace}.${data.name}`,
      name: data.displayName || data.name,
      publisher: data.namespace,
      description: data.description || '',
      version: data.version || '',
      downloads: data.downloadCount || 0,
      rating: data.averageRating || 0,
      icon: data.files?.icon || '',
      readme: data.files?.readme || '',
      license: data.license || '',
      repository: data.repository || '',
      downloadUrl: data.files?.download || '',
      categories: data.categories || [],
      engines: data.engines || {},
    };
  } catch (error) {
    console.error('[Marketplace] Get details failed:', error.message);
    return null;
  }
}

/**
 * Install an extension by downloading its .vsix file.
 * @param {string} namespace - Publisher namespace
 * @param {string} name - Extension name
 * @param {function} onProgress - Progress callback (0-100)
 * @returns {Promise<{success: boolean, path?: string, error?: string}>}
 */
async function installExtension(namespace, name, onProgress) {
  try {
    // Get download URL
    const details = await getExtensionDetails(namespace, name);
    if (!details || !details.downloadUrl) {
      return { success: false, error: 'Extension not found or no download available' };
    }

    const extId = `${namespace}.${name}`;
    const extDir = path.join(EXTENSIONS_DIR, extId);
    const vsixPath = path.join(EXTENSIONS_DIR, `${extId}.vsix`);

    // Download .vsix
    if (onProgress) onProgress(10);
    await downloadFile(details.downloadUrl, vsixPath, (percent) => {
      if (onProgress) onProgress(10 + percent * 0.7);
    });

    // Extract .vsix (it's a zip)
    if (onProgress) onProgress(80);
    await extractVsix(vsixPath, extDir);

    // Clean up .vsix
    fs.unlinkSync(vsixPath);

    // Save metadata
    const metaPath = path.join(extDir, 'extension.json');
    fs.writeFileSync(metaPath, JSON.stringify({
      id: extId,
      name: details.name,
      publisher: namespace,
      version: details.version,
      description: details.description,
      installedAt: new Date().toISOString(),
    }, null, 2));

    if (onProgress) onProgress(100);

    console.log(`[Marketplace] Installed: ${extId}@${details.version}`);
    return { success: true, path: extDir };
  } catch (error) {
    console.error('[Marketplace] Install failed:', error.message);
    return { success: false, error: error.message };
  }
}

/**
 * Uninstall an extension.
 * @param {string} extensionId - e.g., "ms-python.python"
 * @returns {{success: boolean, error?: string}}
 */
function uninstallExtension(extensionId) {
  const extDir = path.join(EXTENSIONS_DIR, extensionId);
  if (fs.existsSync(extDir)) {
    fs.rmSync(extDir, { recursive: true, force: true });
    console.log(`[Marketplace] Uninstalled: ${extensionId}`);
    return { success: true };
  }
  return { success: false, error: 'Extension not found' };
}

/**
 * List all installed extensions.
 * @returns {Array}
 */
function listInstalledExtensions() {
  if (!fs.existsSync(EXTENSIONS_DIR)) return [];

  const installed = [];
  const entries = fs.readdirSync(EXTENSIONS_DIR, { withFileTypes: true });

  for (const entry of entries) {
    if (entry.isDirectory()) {
      const metaPath = path.join(EXTENSIONS_DIR, entry.name, 'extension.json');
      if (fs.existsSync(metaPath)) {
        try {
          const meta = JSON.parse(fs.readFileSync(metaPath, 'utf8'));
          installed.push(meta);
        } catch (e) {
          // Skip corrupt metadata
        }
      }
    }
  }

  return installed;
}

/**
 * Check if extension is installed.
 * @param {string} extensionId
 * @returns {boolean}
 */
function isExtensionInstalled(extensionId) {
  const extDir = path.join(EXTENSIONS_DIR, extensionId);
  return fs.existsSync(extDir) && fs.existsSync(path.join(extDir, 'extension.json'));
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function fetchJSON(url) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;
    client.get(url, { headers: { 'User-Agent': 'AgenticAI/1.0' } }, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        return fetchJSON(res.headers.location).then(resolve).catch(reject);
      }
      if (res.statusCode !== 200) {
        reject(new Error(`HTTP ${res.statusCode}`));
        return;
      }

      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch (e) { reject(e); }
      });
    }).on('error', reject);
  });
}

function downloadFile(url, destPath, onProgress) {
  return new Promise((resolve, reject) => {
    const client = url.startsWith('https') ? https : http;

    const request = (currentUrl) => {
      client.get(currentUrl, { headers: { 'User-Agent': 'AgenticAI/1.0' } }, (res) => {
        if (res.statusCode === 301 || res.statusCode === 302) {
          request(res.headers.location);
          return;
        }
        if (res.statusCode !== 200) {
          reject(new Error(`Download failed: HTTP ${res.statusCode}`));
          return;
        }

        const totalSize = parseInt(res.headers['content-length'] || '0', 10);
        let downloaded = 0;
        const file = fs.createWriteStream(destPath);

        res.on('data', chunk => {
          downloaded += chunk.length;
          file.write(chunk);
          if (totalSize > 0 && onProgress) {
            onProgress(Math.round((downloaded / totalSize) * 100));
          }
        });

        res.on('end', () => {
          file.end();
          resolve();
        });

        res.on('error', (err) => {
          file.close();
          fs.unlinkSync(destPath);
          reject(err);
        });
      }).on('error', reject);
    };

    request(url);
  });
}

async function extractVsix(vsixPath, destDir) {
  // .vsix is a zip — use Node's built-in zlib or external unzip
  const { createReadStream } = require('fs');
  const { pipeline } = require('stream/promises');

  // Simple extraction using unzipper-like approach
  // For production, use 'yauzl' or 'extract-zip' package
  // Here we use a child_process approach that works cross-platform
  const { execSync } = require('child_process');

  if (!fs.existsSync(destDir)) {
    fs.mkdirSync(destDir, { recursive: true });
  }

  // Use PowerShell on Windows to extract
  if (process.platform === 'win32') {
    execSync(
      `powershell -Command "Expand-Archive -Path '${vsixPath}' -DestinationPath '${destDir}' -Force"`,
      { timeout: 30000 }
    );
  } else {
    execSync(`unzip -o "${vsixPath}" -d "${destDir}"`, { timeout: 30000 });
  }
}

module.exports = {
  searchExtensions,
  getPopularExtensions,
  getExtensionDetails,
  installExtension,
  uninstallExtension,
  listInstalledExtensions,
  isExtensionInstalled,
  EXTENSIONS_DIR,
};
