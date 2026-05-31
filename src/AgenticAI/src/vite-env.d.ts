/// <reference types="vite/client" />

// ============================================================================
// Ollama Types
// ============================================================================

interface OllamaModel {
  name: string;
  modified_at: string;
  size: number;
}

interface OllamaHealthStatus {
  available: boolean;
  error?: string;
  latencyMs?: number;
}

interface PullProgress {
  status: string;
  digest?: string;
  total?: number;
  completed?: number;
  percent?: number;
}

// ============================================================================
// AI Types
// ============================================================================

interface AIConfig {
  provider: 'ollama' | 'openai' | 'anthropic';
  apiKey?: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
  // Ollama specific
  ollamaEndpoint?: string;
  ollamaModel?: string;
  ollamaTemperature?: number;
  // OpenAI specific
  openaiApiKey?: string;
  openaiModel?: string;
  // Anthropic specific
  anthropicApiKey?: string;
  anthropicModel?: string;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface AIResponse {
  success?: boolean;
  content?: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model?: string;
  error?: string;
}

interface SteeringContext {
  agents?: string;
  claude?: string;
  product?: string;
  tech?: string;
  structure?: string;
  requirements?: string;
  [key: string]: string | undefined;
}

interface StorageAPI {
  getSettings: () => Promise<{
    aiProvider: 'ollama' | 'openai' | 'anthropic';
    aiModel?: string;
    maxTokens: number;
    temperature: number;
    fontSize: number;
    autoSave: boolean;
    autoSaveDelay: number;
    ollamaEndpoint?: string;
    ollamaModel?: string;
    ollamaTemperature?: number;
    openaiModel?: string;
    anthropicModel?: string;
  }>;
  updateSettings: (updates: Record<string, unknown>) => Promise<boolean>;
  getAPIKey: () => Promise<string | undefined>;
  setAPIKey: (key: string) => Promise<boolean>;
  hasAPIKey: () => Promise<boolean>;
  getAIConfig: () => Promise<AIConfig | undefined>;
  setAIConfig: (config: AIConfig) => Promise<boolean>;
  getWorkspace: () => Promise<{ path: string; name: string; lastOpened: string } | null>;
  setWorkspace: (path: string) => Promise<boolean>;
  getTasks: () => Promise<Array<{
    id: string;
    title: string;
    description?: string;
    status: 'todo' | 'doing' | 'done';
    priority: 'low' | 'medium' | 'high';
    createdAt: string;
    completedAt?: string;
  }>>;
  saveTasks: (tasks: Array<{
    id: string;
    title: string;
    description?: string;
    status: 'todo' | 'doing' | 'done';
    priority: 'low' | 'medium' | 'high';
    createdAt: string;
    completedAt?: string;
  }>) => Promise<boolean>;
  getChat: () => Promise<{
    messages: Array<{
      id: string;
      role: 'user' | 'assistant';
      content: string;
      timestamp: string;
    }>;
    conversationId: string | null;
  }>;
  saveChat: (messages: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
  }>) => Promise<boolean>;
  getUIState: () => Promise<{
    sidebarWidth: number;
    taskPanelWidth: number;
    chatPanelWidth: number;
    terminalHeight: number;
    activePanel: string;
    expandedFolders: string[];
  }>;
  updateUIState: (updates: Record<string, unknown>) => Promise<boolean>;
  getOpenFiles: () => Promise<{ files: string[]; activeFile: string | null }>;
  updateOpenFiles: (updates: { files?: string[]; activeFile?: string | null }) => Promise<boolean>;
}

interface AIAPI {
  initialize: (config: AIConfig) => Promise<{ success: boolean; error?: string }>;
  chat: (messages: ChatMessage[], systemPrompt?: string) => Promise<AIResponse>;
  codeReview: (code: string, language: string, context?: string) => Promise<AIResponse>;
  generateCode: (spec: string, existingCode?: string) => Promise<AIResponse>;
  isInitialized: () => Promise<boolean>;
}

interface SteeringAPI {
  load: (workspacePath: string) => Promise<{ success?: boolean; context?: SteeringContext; error?: string }>;
  getContext: () => Promise<SteeringContext>;
  getSystemPrompt: () => Promise<string>;
  getRelevantContext: (query: string) => Promise<string>;
}

interface AppAPI {
  minimize: () => void;
  maximize: () => void;
  close: () => void;
  getVersion: () => Promise<string>;
}

interface FileEntry {
  name: string;
  path: string;
  isDirectory: boolean;
}

interface GitAPI {
  gitBranch: (path?: string) => Promise<string>;
  gitInfo: (path: string) => Promise<{
    isRepo: boolean;
    branch: string;
    branches: string[];
    status: {
      modified: string[];
      staged: string[];
      created: string[];
      deleted: string[];
      not_added: string[];
      current: string;
      tracking: string | null;
    } | null;
    remotes: string[];
  }>;
  gitLog: (path: string, count: number) => Promise<Array<{
    hash: string;
    message: string;
    author: string;
    date: string;
  }>>;
  gitStage: (path: string, files: string[]) => Promise<boolean>;
  gitCommit: (path: string, message: string) => Promise<boolean>;
  gitCheckout: (path: string, branch: string) => Promise<boolean>;
  // Phase 3 Git operations
  info: (workspacePath: string) => Promise<{
    isRepo: boolean;
    branch: string;
    branches: string[];
    status: {
      modified: string[];
      staged: string[];
      created: string[];
      deleted: string[];
      not_added: string[];
      current: string;
      tracking: string | null;
    } | null;
    remotes: string[];
  }>;
  status: () => Promise<{
    modified: string[];
    staged: string[];
    created: string[];
    deleted: string[];
    not_added: string[];
    current: string;
    tracking: string | null;
  } | null>;
  log: (workspacePath: string, limit?: number) => Promise<Array<{
    hash: string;
    message: string;
    author: string;
    date: string;
  }>>;
  stage: (workspacePath: string, files: string[]) => Promise<boolean>;
  unstage: (workspacePath: string, files: string[]) => Promise<boolean>;
  commit: (workspacePath: string, message: string) => Promise<boolean>;
  checkout: (workspacePath: string, branch: string) => Promise<boolean>;
  branch: (workspacePath: string, name?: string, create?: boolean) => Promise<string | null>;
  diff: (workspacePath: string, file?: string) => Promise<string>;
  discard: (workspacePath: string, files: string[]) => Promise<boolean>;
}

interface SearchAPI {
  search: (options: {
    query: string;
    path: string;
    caseSensitive?: boolean;
    wholeWord?: boolean;
    regex?: boolean;
  }) => Promise<Array<{
    file: string;
    line: number;
    column: number;
    match: string;
    context: string;
  }>>;
}

interface TerminalAPI {
  terminalCreate: () => Promise<{ id: string }>;
  terminalClose: (id: string) => Promise<void>;
  terminalInput: (id: string, data: string) => void;
  terminalOnOutput: (id: string, callback: (output: string) => void) => void;
}

interface Window {
  electronAPI?: {
    openDirectory: () => Promise<string | undefined>;
    readDirectory: (path: string) => Promise<FileEntry[]>;
    readFile: (path: string) => Promise<string | null>;
    writeFile: (path: string, content: string) => Promise<boolean>;
    createFile: (path: string) => Promise<boolean>;
    createDirectory: (path: string) => Promise<boolean>;
    deleteFile: (path: string) => Promise<boolean>;
    rename: (oldPath: string, newPath: string) => Promise<boolean>;
    ai: AIAPI;
    steering: SteeringAPI;
    storage: StorageAPI;
    app: AppAPI;
    git: GitAPI;
    search: SearchAPI;
    terminal: TerminalAPI;
    // Ollama
    ollamaHealth: (timeout?: number) => Promise<OllamaHealthStatus>;
    ollamaListModels: () => Promise<OllamaModel[]>;
    ollamaGenerate: (options: {
      prompt: string;
      system?: string;
      context?: number[];
      stream?: boolean;
      options?: {
        temperature?: number;
        num_predict?: number;
        top_p?: number;
        top_k?: number;
      };
    }) => Promise<{ content?: string; error?: string }>;
    ollamaPullModel: (model: string, onProgress?: (progress: PullProgress) => void) => Promise<boolean>;
    ollamaGetContextLimit: (model: string) => Promise<number>;
    ollamaOnChunk: (callback: (chunk: string) => void) => void;
    // Legacy aliases
    gitBranch?: (path?: string) => Promise<string>;
    gitInfo?: (path: string) => ReturnType<GitAPI['gitInfo']>;
    gitLog?: (path: string, count: number) => ReturnType<GitAPI['gitLog']>;
    gitStage?: (path: string, files: string[]) => ReturnType<GitAPI['gitStage']>;
    gitCommit?: (path: string, message: string) => ReturnType<GitAPI['gitCommit']>;
    gitCheckout?: (path: string, branch: string) => ReturnType<GitAPI['gitCheckout']>;
    // Direct storage helpers
    storeSet?: (key: string, value: unknown) => Promise<void>;
    storeGet?: (key: string) => Promise<unknown>;
  };
}
