/**
 * ElectronBridge - Dependency Injection for Electron API
 * 
 * This abstraction layer allows components to be tested without
 * direct coupling to window.electronAPI.
 * 
 * Usage:
 *   import { electronBridge } from '@/services/electronBridge';
 *   await electronBridge.readFile('/path/to/file');
 */

export interface ElectronBridge {
  // Dialog
  openDirectory(): Promise<string | null>;
  
  // File System
  readDirectory(path: string): Promise<FileEntry[]>;
  readFile(path: string): Promise<string>;
  writeFile(path: string, content: string): Promise<void>;
  createFile(path: string): Promise<void>;
  createDirectory(path: string): Promise<void>;
  deleteFile(path: string): Promise<void>;
  rename(oldPath: string, newPath: string): Promise<void>;
  
  // AI Service
  ai: {
    initialize(config: AIConfig): Promise<{ success: boolean; error?: string }>;
    chat(messages: ChatMessage[], systemPrompt?: string): Promise<AIResponse>;
    codeReview(code: string, language: string, context?: string): Promise<AIResponse>;
    generateCode(spec: string, existingCode?: string): Promise<AIResponse>;
    isInitialized(): Promise<boolean>;
  };
  
  // Steering Parser
  steering: {
    load(workspacePath: string): Promise<void>;
    getContext(): Promise<SteeringContext>;
    getSystemPrompt(): Promise<string>;
    getRelevantContext(query: string): Promise<string[]>;
  };
  
  // Storage
  storage: {
    getSettings(): Promise<Settings>;
    updateSettings(updates: Partial<Settings>): Promise<void>;
    getAPIKey(): Promise<string | null>;
    setAPIKey(key: string): Promise<void>;
    hasAPIKey(): Promise<boolean>;
    getWorkspace(): Promise<string | null>;
    setWorkspace(path: string): Promise<void>;
    getTasks(): Promise<Task[]>;
    saveTasks(tasks: Task[]): Promise<void>;
    getChat(): Promise<ChatMessage[]>;
    saveChat(messages: ChatMessage[]): Promise<void>;
    getUIState(): Promise<UIState>;
    updateUIState(updates: Partial<UIState>): Promise<void>;
    getOpenFiles(): Promise<string[]>;
    updateOpenFiles(files: string[]): Promise<void>;
  };
  
  // Code Analysis
  code: {
    analyze(filePath: string, content: string): Promise<AnalysisResult>;
    review(filePath: string, content: string): Promise<ReviewIssue[]>;
    applyFix(fix: Fix): Promise<ApplyResult>;
    applyMultipleFixes(fixes: Fix[]): Promise<ApplyResult[]>;
  };
  
  // Terminal
  terminal: {
    create(cwd?: string): Promise<string>;
    input(id: string, data: string): Promise<void>;
    resize(id: string, cols: number, rows: number): Promise<void>;
    close(id: string): Promise<void>;
    onOutput(id: string, callback: (output: string) => void): void;
  };
  
  // Git
  git: {
    info(workspacePath: string): Promise<GitInfo>;
    status(): Promise<GitStatus[]>;
    log(workspacePath: string, limit?: number): Promise<GitLogEntry[]>;
    stage(files: string[]): Promise<void>;
    unstage(files: string[]): Promise<void>;
    commit(message: string): Promise<void>;
    checkout(branch: string): Promise<void>;
    branch(name: string, create?: boolean): Promise<GitBranch[]>;
    diff(file?: string): Promise<string>;
    discard(files: string[]): Promise<void>;
  };
  
  // Search
  search(options: SearchOptions): Promise<SearchResult[]>;
  
  // App
  app: {
    minimize(): Promise<void>;
    maximize(): Promise<void>;
    close(): Promise<void>;
    getVersion(): Promise<string>;
  };
}

// Type definitions
export interface FileEntry {
  name: string;
  path: string;
  isDirectory: boolean;
  size: number;
  modified: number;
}

export interface AIConfig {
  provider: 'openai' | 'anthropic' | 'ollama';
  apiKey?: string;
  model?: string;
  baseUrl?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface AIResponse {
  success?: boolean;
  content?: string;
  error?: string;
}

export interface SteeringContext {
  projectType?: string;
  language?: string;
  framework?: string;
  [key: string]: unknown;
}

export interface Settings {
  theme: 'light' | 'dark';
  fontSize: number;
  fontFamily: string;
  tabSize: number;
  wordWrap: boolean;
  minimap: boolean;
  autoSave: boolean;
  [key: string]: unknown;
}

export interface Task {
  id: string;
  title: string;
  description?: string;
  completed: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface UIState {
  sidebarWidth: number;
  rightPanelWidth: number;
  terminalHeight: number;
  [key: string]: unknown;
}

export interface AnalysisResult {
  symbols: Symbol[];
  imports: Import[];
  exports: Export[];
  errors: SyntaxError[];
}

export interface Symbol {
  name: string;
  kind: 'function' | 'class' | 'variable' | 'type' | 'interface';
  location: Location;
  scope: string;
}

export interface Import {
  source: string;
  imported: string[];
  isDefault: boolean;
}

export interface Export {
  name: string;
  exportedAs: string;
  isDefault: boolean;
}

export interface Location {
  start: Position;
  end: Position;
}

export interface Position {
  line: number;
  column: number;
}

export interface SyntaxError {
  message: string;
  location: Location;
  severity: 'error' | 'warning';
}

export interface ReviewIssue {
  id: string;
  type: 'security' | 'quality' | 'style' | 'performance';
  severity: 'error' | 'warning' | 'info';
  message: string;
  location: Location;
  rule?: string;
  fix?: Fix;
}

export interface Fix {
  type: string;
  description: string;
  original: string;
  replacement: string;
  location: Location;
}

export interface ApplyResult {
  success: boolean;
  applied: boolean;
  error?: string;
}

export interface GitInfo {
  branch: string;
  remote: string | null;
  root: string;
}

export interface GitStatus {
  path: string;
  index: string;
  workingDir: string;
  isNew: boolean;
  isModified: boolean;
  isDeleted: boolean;
  isRenamed: boolean;
}

export interface GitLogEntry {
  hash: string;
  date: string;
  message: string;
  author: string;
}

export interface GitBranch {
  name: string;
  current: boolean;
  remote: boolean;
}

export interface SearchOptions {
  query: string;
  path?: string;
  include?: string[];
  exclude?: string[];
  caseSensitive?: boolean;
  wholeWord?: boolean;
  useRegex?: boolean;
}

export interface SearchResult {
  path: string;
  line: number;
  column: number;
  match: string;
  context: string;
}

// Factory function to create bridge
function createElectronBridge(): ElectronBridge {
  const api = window.electronAPI;
  
  return {
    // Dialog
    openDirectory: () => api.openDirectory(),
    
    // File System
    readDirectory: (path) => api.readDirectory(path),
    readFile: (path) => api.readFile(path),
    writeFile: (path, content) => api.writeFile(path, content),
    createFile: (path) => api.createFile(path),
    createDirectory: (path) => api.createDirectory(path),
    deleteFile: (path) => api.deleteFile(path),
    rename: (oldPath, newPath) => api.rename(oldPath, newPath),
    
    // AI
    ai: {
      initialize: (config) => api.ai.initialize(config),
      chat: (messages, systemPrompt) => api.ai.chat(messages, systemPrompt),
      codeReview: (code, language, context) => api.ai.codeReview(code, language, context),
      generateCode: (spec, existingCode) => api.ai.generateCode(spec, existingCode),
      isInitialized: () => api.ai.isInitialized(),
    },
    
    // Steering
    steering: {
      load: (workspacePath) => api.steering.load(workspacePath),
      getContext: () => api.steering.getContext(),
      getSystemPrompt: () => api.steering.getSystemPrompt(),
      getRelevantContext: (query) => api.steering.getRelevantContext(query),
    },
    
    // Storage
    storage: {
      getSettings: () => api.storage.getSettings(),
      updateSettings: (updates) => api.storage.updateSettings(updates),
      getAPIKey: () => api.storage.getAPIKey(),
      setAPIKey: (key) => api.storage.setAPIKey(key),
      hasAPIKey: () => api.storage.hasAPIKey(),
      getWorkspace: () => api.storage.getWorkspace(),
      setWorkspace: (path) => api.storage.setWorkspace(path),
      getTasks: () => api.storage.getTasks(),
      saveTasks: (tasks) => api.storage.saveTasks(tasks),
      getChat: () => api.storage.getChat(),
      saveChat: (messages) => api.storage.saveChat(messages),
      getUIState: () => api.storage.getUIState(),
      updateUIState: (updates) => api.storage.updateUIState(updates),
      getOpenFiles: () => api.storage.getOpenFiles(),
      updateOpenFiles: (files) => api.storage.updateOpenFiles(files),
    },
    
    // Code
    code: {
      analyze: (filePath, content) => api.code.analyze(filePath, content),
      review: (filePath, content) => api.code.review(filePath, content),
      applyFix: (fix) => api.code.applyFix(fix),
      applyMultipleFixes: (fixes) => api.code.applyMultipleFixes(fixes),
    },
    
    // Terminal
    terminal: {
      create: (cwd) => api.terminal.create(cwd),
      input: (id, data) => api.terminal.input(id, data),
      resize: (id, cols, rows) => api.terminal.resize(id, cols, rows),
      close: (id) => api.terminal.close(id),
      onOutput: (id, callback) => api.terminal.onOutput(id, callback),
    },
    
    // Git
    git: {
      info: (workspacePath) => api.git.info(workspacePath),
      status: () => api.git.status(),
      log: (workspacePath, limit) => api.git.log(workspacePath, limit),
      stage: (files) => api.git.stage(files),
      unstage: (files) => api.git.unstage(files),
      commit: (message) => api.git.commit(message),
      checkout: (branch) => api.git.checkout(branch),
      branch: (name, create) => api.git.branch(name, create),
      diff: (file) => api.git.diff(file),
      discard: (files) => api.git.discard(files),
    },
    
    // Search
    search: (options) => api.search(options),
    
    // App
    app: {
      minimize: () => api.app.minimize(),
      maximize: () => api.app.maximize(),
      close: () => api.app.close(),
      getVersion: () => api.app.getVersion(),
    },
  };
}

// Singleton instance
export const electronBridge = createElectronBridge();

// For testing - allow mock injection
let _bridge: ElectronBridge | null = null;

export function setElectronBridge(bridge: ElectronBridge): void {
  _bridge = bridge;
}

export function getElectronBridge(): ElectronBridge {
  if (_bridge) {
    return _bridge;
  }
  return electronBridge;
}

export default electronBridge;
