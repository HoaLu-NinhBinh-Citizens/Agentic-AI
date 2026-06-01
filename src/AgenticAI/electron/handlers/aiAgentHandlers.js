'use strict';

const { mcpClient } = require('../mcp/mcpClient');

/**
 * Register AI Agent handlers for Electron IPC
 * These handlers bridge the Electron app with the Python AI Agent via MCP
 */
function registerAIAgentHandlers(ipcMain, services = {}) {
  console.log('[AIAgentHandlers] Registering AI Agent IPC handlers...');

  // ========================================
  // MCP Connection Management
  // ========================================

  ipcMain.handle('aiAgent:connect', async (_, options = {}) => {
    try {
      const workspace = options.workspace || process.cwd();
      const result = await mcpClient.connect({
        cwd: workspace,
        ...options,
      });
      return { success: true, connected: result };
    } catch (error) {
      console.error('[AIAgentHandlers] Connection error:', error);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:disconnect', async () => {
    try {
      mcpClient.disconnect();
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:status', async () => {
    return mcpClient.getStatus();
  });

  // ========================================
  // MCP Tools (Python Agent Capabilities)
  // ========================================

  ipcMain.handle('aiAgent:listTools', async () => {
    try {
      const tools = await mcpClient.listTools();
      return { success: true, tools };
    } catch (error) {
      console.error('[AIAgentHandlers] List tools error:', error);
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:callTool', async (_, { name, arguments: args = {} }) => {
    try {
      const result = await mcpClient.callTool(name, args);
      return { success: true, result };
    } catch (error) {
      console.error('[AIAgentHandlers] Call tool error:', error);
      return { success: false, error: error.message };
    }
  });

  // ========================================
  // Hardware Tools
  // ========================================

  ipcMain.handle('aiAgent:hardware:validate', async (_, config) => {
    try {
      const result = await mcpClient.callTool('hardware_validate', config);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:hardware:planInit', async (_, params) => {
    try {
      const result = await mcpClient.callTool('plan_hardware_init', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:hardware:reason', async (_, params) => {
    try {
      const result = await mcpClient.callTool('reason_about_hardware', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  // ========================================
  // Firmware Analysis Tools
  // ========================================

  ipcMain.handle('aiAgent:firmware:analyze', async (_, params) => {
    try {
      const result = await mcpClient.callTool('analyze_firmware', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:firmware:debug', async (_, params) => {
    try {
      const result = await mcpClient.callTool('debug_issue', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:firmware:generateCode', async (_, params) => {
    try {
      const result = await mcpClient.callTool('generate_code', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  // ========================================
  // Knowledge Base Tools
  // ========================================

  ipcMain.handle('aiAgent:knowledge:query', async (_, params) => {
    try {
      const result = await mcpClient.callTool('query_knowledge_base', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:knowledge:crossValidate', async (_, params) => {
    try {
      const result = await mcpClient.callTool('cross_validate', params);
      return { success: true, ...result };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  // ========================================
  // Resources
  // ========================================

  ipcMain.handle('aiAgent:listResources', async () => {
    try {
      const resources = await mcpClient.listResources();
      return { success: true, resources };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:readResource', async (_, uri) => {
    try {
      const resource = await mcpClient.readResource(uri);
      return { success: true, resource };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  // ========================================
  // Prompts
  // ========================================

  ipcMain.handle('aiAgent:listPrompts', async () => {
    try {
      const prompts = await mcpClient.listPrompts();
      return { success: true, prompts };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:getPrompt', async (_, { name, arguments: args = {} }) => {
    try {
      const prompt = await mcpClient.getPrompt(name, args);
      return { success: true, prompt };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  // ========================================
  // Event Subscriptions
  // ========================================

  ipcMain.handle('aiAgent:subscribe', async (event, { eventName, channel }) => {
    try {
      mcpClient.on(eventName, (data) => {
        event.sender.send(`aiAgent:event:${channel}`, { event: eventName, data });
      });
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  ipcMain.handle('aiAgent:unsubscribe', async (_, { eventName }) => {
    try {
      mcpClient.off(eventName);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  });

  console.log('[AIAgentHandlers] AI Agent IPC handlers registered');
}

module.exports = {
  registerAIAgentHandlers,
};
