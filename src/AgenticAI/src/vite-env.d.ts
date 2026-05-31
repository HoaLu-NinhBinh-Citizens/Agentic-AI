/// <reference types="vite/client" />

interface AIConfig {
  provider: 'openai' | 'anthropic';
  apiKey: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
}

interface ChatMessage {
  role: 'user' | 'assistant';
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
    aiProvider: 'openai' | 'anthropic';
    aiModel?: string;
    maxTokens: number;
    temperature: number;
    fontSize: number;
    autoSave: boolean;
    autoSaveDelay: number;
  }>;
  updateSettings: (updates: Record<string, unknown>) => Promise<boolean>;
  getAPIKey: () => Promise<string | undefined>;
  setAPIKey: (key: string) => Promise<boolean>;
  hasAPIKey: () => Promise<boolean>;
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
  };
}
