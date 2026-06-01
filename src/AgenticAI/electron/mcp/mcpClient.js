'use strict';

const { spawn } = require('child_process');
const path = require('path');

/**
 * MCP Client for Electron - Communicates with Python AI Agent via MCP Protocol
 * Uses stdio transport for JSON-RPC communication
 */
class MCPClient {
  constructor() {
    this.process = null;
    this.requestId = 0;
    this.pendingRequests = new Map();
    this.eventHandlers = new Map();
    this.isConnected = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
    this.reconnectDelay = 1000;
    this._buffer = '';
  }

  /**
   * Initialize MCP client and spawn Python agent
   * @param {Object} options - Configuration options
   * @param {string} options.pythonPath - Path to Python interpreter
   * @param {string} options.agentPath - Path to Python agent module
   * @param {string} options.cwd - Working directory
   */
  async connect(options = {}) {
    const {
      pythonPath = 'python',
      agentPath = path.join(__dirname, '../../../src/agentic_ai/__main__.py'),
      cwd = process.cwd(),
    } = options;

    return new Promise((resolve, reject) => {
      try {
        console.log('[MCPClient] Spawning Python agent...');

        this.process = spawn(pythonPath, ['-m', 'src.agentic_ai'], {
          cwd,
          stdio: ['pipe', 'pipe', 'pipe'],
          env: { ...process.env, MCP_STDIO: 'true' },
        });

        let buffer = '';

        this.process.stdout.on('data', (data) => {
          buffer += data.toString();
          this._processBuffer();
        });

        this.process.stderr.on('data', (data) => {
          console.error('[MCPClient] Python stderr:', data.toString().trim());
        });

        this.process.on('error', (error) => {
          console.error('[MCPClient] Process error:', error);
          this.isConnected = false;
          this._emit('error', error);
        });

        this.process.on('exit', (code) => {
          console.log('[MCPClient] Process exited with code:', code);
          this.isConnected = false;
          this._emit('exit', { code });
        });

        // Wait for initialization
        const timeout = setTimeout(() => {
          reject(new Error('MCP client initialization timeout'));
        }, 10000);

        this.once('initialized', () => {
          clearTimeout(timeout);
          this.isConnected = true;
          this.reconnectAttempts = 0;
          console.log('[MCPClient] Connected to Python agent');
          resolve(true);
        });

        this.once('error', (err) => {
          clearTimeout(timeout);
          reject(err);
        });
      } catch (error) {
        reject(error);
      }
    });
  }

  /**
   * Process stdout buffer for complete JSON-RPC messages
   */
  _processBuffer() {
    const lines = this._extractLines();
    for (const line of lines) {
      if (line.trim()) {
        try {
          const message = JSON.parse(line);
          this._handleMessage(message);
        } catch (e) {
          // Ignore non-JSON messages (log output, etc.)
        }
      }
    }
  }

  /**
   * Extract complete lines from buffer
   */
  _extractLines() {
    const lines = this._buffer.split('\n');
    this._buffer = lines.pop() || '';
    return lines;
  }

  /**
   * Handle incoming JSON-RPC message
   */
  _handleMessage(message) {
    if (message.id !== undefined) {
      // Response to a request
      const pending = this.pendingRequests.get(message.id);
      if (pending) {
        this.pendingRequests.delete(message.id);
        if (message.error) {
          pending.reject(new Error(message.error.message || message.error));
        } else {
          pending.resolve(message.result);
        }
      }
    } else if (message.method) {
      // Notification/event from server
      this._emit(message.method, message.params);
    }

    // Handle specific events
    if (message.jsonrpc === '2.0' && message.result?.protocolVersion) {
      this._emit('initialized', message.result);
    }
  }

  /**
   * Send JSON-RPC request to Python agent
   */
  async request(method, params = {}) {
    if (!this.isConnected || !this.process?.stdin) {
      throw new Error('MCP client not connected');
    }

    const id = ++this.requestId;
    const request = {
      jsonrpc: '2.0',
      id,
      method,
      params,
    };

    return new Promise((resolve, reject) => {
      this.pendingRequests.set(id, { resolve, reject });

      const data = JSON.stringify(request) + '\n';
      this.process.stdin.write(data);

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error(`Request ${method} timed out`));
        }
      }, 30000);
    });
  }

  /**
   * Send notification (no response expected)
   */
  notify(method, params = {}) {
    if (!this.isConnected || !this.process?.stdin) {
      console.warn('[MCPClient] Cannot send notification: not connected');
      return;
    }

    const notification = {
      jsonrpc: '2.0',
      method,
      params,
    };

    this.process.stdin.write(JSON.stringify(notification) + '\n');
  }

  /**
   * List available tools from the server
   */
  async listTools() {
    return this.request('tools/list');
  }

  /**
   * Call a specific tool
   */
  async callTool(name, arguments_ = {}) {
    return this.request('tools/call', {
      name,
      arguments: arguments_,
    });
  }

  /**
   * List available resources
   */
  async listResources() {
    return this.request('resources/list');
  }

  /**
   * Read a specific resource
   */
  async readResource(uri) {
    return this.request('resources/read', { uri });
  }

  /**
   * List available prompts
   */
  async listPrompts() {
    return this.request('prompts/list');
  }

  /**
   * Get a specific prompt
   */
  async getPrompt(name, arguments_ = {}) {
    return this.request('prompts/get', {
      name,
      arguments: arguments_,
    });
  }

  /**
   * Subscribe to server-sent events
   */
  on(event, handler) {
    if (!this.eventHandlers.has(event)) {
      this.eventHandlers.set(event, new Set());
    }
    this.eventHandlers.get(event).add(handler);
  }

  /**
   * Unsubscribe from events
   */
  off(event, handler) {
    const handlers = this.eventHandlers.get(event);
    if (handlers) {
      handlers.delete(handler);
    }
  }

  /**
   * Listen for event once
   */
  once(event, handler) {
    const wrappedHandler = (...args) => {
      this.off(event, wrappedHandler);
      handler(...args);
    };
    this.on(event, wrappedHandler);
  }

  /**
   * Emit event to handlers
   */
  _emit(event, data) {
    const handlers = this.eventHandlers.get(event);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(data);
        } catch (e) {
          console.error(`[MCPClient] Event handler error:`, e);
        }
      }
    }
  }

  /**
   * Reconnect to the Python agent
   */
  async reconnect(options = {}) {
    this.disconnect();

    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      throw new Error('Max reconnection attempts reached');
    }

    this.reconnectAttempts++;
    console.log(`[MCPClient] Reconnecting (attempt ${this.reconnectAttempts})...`);

    await new Promise(resolve => setTimeout(resolve, this.reconnectDelay * this.reconnectAttempts));

    return this.connect(options);
  }

  /**
   * Disconnect from the Python agent
   */
  disconnect() {
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
    this.isConnected = false;

    // Reject all pending requests
    for (const [id, pending] of this.pendingRequests) {
      pending.reject(new Error('Connection closed'));
    }
    this.pendingRequests.clear();
  }

  /**
   * Get connection status
   */
  getStatus() {
    return {
      connected: this.isConnected,
      reconnectAttempts: this.reconnectAttempts,
      pendingRequests: this.pendingRequests.size,
    };
  }
}

// Singleton instance
const mcpClient = new MCPClient();

module.exports = { mcpClient, MCPClient };
