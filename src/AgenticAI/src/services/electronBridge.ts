/**
 * ElectronBridge - Abstraction layer for Electron IPC communication
 * This interface enables dependency injection and easier testing
 */

export interface FileEntry {
  name: string;
  path: string;
  isDirectory: boolean;
}

export interface GitStatus {
  modified: string[];
  staged: string[];
  created: string[];
  deleted: string[];
  not_added: string[];
  current: string;
  tracking: string;
}

export interface GitLogEntry {
  hash: string;
  date: string;
  message: string;
  author: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface AIResponse {
  content: string;
  error: string | null;
}

export interface UIState {
  expandedFolders: string[];
  openFiles: string[];
}

export interface AppSettings {
  aiProvider: 'ollama' | 'openai' | 'anthropic';
  ollamaEndpoint?: string;
  ollamaModel?: string;
  openaiModel?: string;
  anthropicModel?: string;
}

export interface SteeringContext {
  agents?: string;
  claude?: string;
  product?: string;
  tech?: string;
  structure?: string;
  requirements?: string;
  [key: string]: string | undefined;
}

export interface TerminalAPI {
  write(id: string, data: string): void;
  onData(callback: (id: string, data: string) => void): void;
  resize(id: string, cols: number, rows: number): void;
  clear(id: string): void;
  dispose(id: string): void;
}

export interface AIAPI {
  isInitialized(): Promise<boolean>;
  chat(messages: ChatMessage[]): Promise<AIResponse>;
  generateCode(prompt: string): Promise<AIResponse>;
  codeReview(code: string, file: string): Promise<AIResponse>;
  explainCode(code: string): Promise<AIResponse>;
}

export interface StorageAPI {
  getWorkspace(): Promise<{ path: string } | null>;
  setWorkspace(path: string): Promise<boolean>;
  updateUIState(state: Partial<UIState>): Promise<boolean>;
  updateOpenFiles(files: { files: string[]; activeFile?: string }): Promise<boolean>;
  getUIState(): Promise<UIState>;
}

export interface SteeringAPI {
  load(workspacePath: string): Promise<{ success: boolean; context: SteeringContext }>;
  save?(context: SteeringContext): Promise<boolean>;
}

export interface ElectronBridge {
  // File System
  openDirectory(): Promise<string | null>;
  readDirectory(path: string): Promise<FileEntry[]>;
  readFile(path: string): Promise<string | null>;
  writeFile(path: string, content: string): Promise<boolean>;
  createFile(path: string): Promise<boolean>;
  createDirectory(path: string): Promise<boolean>;
  deleteFile(path: string): Promise<boolean>;
  
  // Git
  gitStatus(): Promise<GitStatus>;
  gitBranch(): Promise<string>;
  gitCommit(message: string): Promise<string>;
  gitStage(files: string[]): Promise<boolean>;
  gitUnstage(files: string[]): Promise<boolean>;
  gitCheckout(branch: string): Promise<boolean>;
  gitDiscard(path: string): Promise<boolean>;
  gitLog(limit?: number): Promise<GitLogEntry[]>;
  gitDiff(path?: string): Promise<string>;
  
  // Terminal
  terminal: TerminalAPI;
  
  // AI
  ai: AIAPI;
  
  // Storage
  storage: StorageAPI;
  
  // Steering
  steering: SteeringAPI;
  
  // Settings
  getSettings(): Promise<AppSettings | null>;
  saveSettings(settings: AppSettings): Promise<boolean>;
  
  // Events
  onFileChange(callback: (path: string) => void): void;
  onGitStatusChange(callback: () => void): void;
}

// Context type for React components
export type ElectronBridgeContext = ElectronBridge | null;
