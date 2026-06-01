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
// Base Types (Global)
// ============================================================================

interface FileEntry {
  name: string;
  path: string;
  isDirectory: boolean;
}

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

interface AIResponse {
  success?: boolean;
  content?: string;
  error?: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model?: string;
}

interface AIConfig {
  provider: 'ollama' | 'openai' | 'anthropic';
  apiKey?: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
  ollamaEndpoint?: string;
  ollamaModel?: string;
  ollamaTemperature?: number;
  openaiApiKey?: string;
  openaiModel?: string;
  anthropicApiKey?: string;
  anthropicModel?: string;
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

interface UIState {
  sidebarWidth: number;
  taskPanelWidth: number;
  chatPanelWidth: number;
  terminalHeight: number;
  activePanel: string;
  expandedFolders: string[];
}

interface AppSettings {
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
}

interface GitStatus {
  modified: string[];
  staged: string[];
  created: string[];
  deleted: string[];
  not_added: string[];
  current: string;
  tracking: string | null;
}

interface GitLogEntry {
  hash: string;
  message: string;
  author: string;
  date: string;
}

// ============================================================================
// API Interfaces
// ============================================================================

interface StorageAPI {
  getWorkspace(): Promise<{ path: string } | null>;
  setWorkspace(path: string): Promise<boolean>;
  updateUIState(state: Partial<UIState>): Promise<boolean>;
  updateOpenFiles(files: { files: string[]; activeFile?: string }): Promise<boolean>;
  getUIState(): Promise<UIState>;
  getSettings?(): Promise<AppSettings | null>;
  saveSettings?(settings: AppSettings): Promise<boolean>;
  updateSettings?(settings: Partial<AppSettings>): Promise<boolean>;
  getAIConfig?(): Promise<AIConfig | null>;
  setAIConfig?(config: AIConfig): Promise<boolean>;
  getAPIKey?(): Promise<string | undefined>;
  setAPIKey?(key: string): Promise<boolean>;
  hasAPIKey?(): Promise<boolean>;
  getTasks?(): Promise<Array<{
    id: string;
    title: string;
    description?: string;
    status: 'todo' | 'doing' | 'done';
    priority: 'low' | 'medium' | 'high';
    createdAt: string;
    completedAt?: string;
  }>>;
  saveTasks?(tasks: Array<{
    id: string;
    title: string;
    description?: string;
    status: 'todo' | 'doing' | 'done';
    priority: 'low' | 'medium' | 'high';
    createdAt: string;
    completedAt?: string;
  }>): Promise<boolean>;
  getChat?(): Promise<{
    messages: Array<{
      id: string;
      role: 'user' | 'assistant';
      content: string;
      timestamp: string;
    }>;
    conversationId: string | null;
  }>;
  saveChat?(messages: Array<{
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
  }>): Promise<boolean>;
  getOpenFiles?(): Promise<{ files: string[]; activeFile: string | null }>;
  updateOpenFiles?(updates: { files?: string[]; activeFile?: string | null }): Promise<boolean>;
}

interface AIAPI {
  initialize?(config: AIConfig): Promise<{ success: boolean; error?: string }>;
  isInitialized(): Promise<boolean>;
  chat(messages: ChatMessage[]): Promise<AIResponse>;
  generateCode(prompt: string): Promise<AIResponse>;
  codeReview(code: string, file: string): Promise<AIResponse>;
  explainCode(code: string): Promise<AIResponse>;
}

interface SteeringAPI {
  load(workspacePath: string): Promise<{ success?: boolean; context?: SteeringContext; error?: string }>;
  getContext?(): Promise<SteeringContext>;
  getSystemPrompt?(): Promise<string>;
  getRelevantContext?(query: string): Promise<string>;
  save?(context: SteeringContext): Promise<boolean>;
}

interface TerminalAPI {
  write(id: string, data: string): void;
  onData(callback: (id: string, data: string) => void): void;
  resize(id: string, cols: number, rows: number): void;
  clear(id: string): void;
  dispose(id: string): void;
}

interface AppAPI {
  minimize(): void;
  maximize(): void;
  close(): void;
  getVersion(): Promise<string>;
}

interface GitAPI {
  gitBranch?(path?: string): Promise<string>;
  gitInfo?(path: string): Promise<{
    isRepo: boolean;
    branch: string;
    branches: string[];
    status: GitStatus | null;
    remotes: string[];
  }>;
  gitLog?(path: string, count: number): Promise<GitLogEntry[]>;
  gitStage?(path: string, files: string[]): Promise<boolean>;
  gitCommit?(path: string, message: string): Promise<boolean>;
  gitCheckout?(path: string, branch: string): Promise<boolean>;
  // Phase 3 Git operations
  info(workspacePath: string): Promise<{
    isRepo: boolean;
    branch: string;
    branches: string[];
    status: GitStatus | null;
    remotes: string[];
  }>;
  status(): Promise<GitStatus | null>;
  log(workspacePath: string, limit?: number): Promise<GitLogEntry[]>;
  stage(workspacePath: string, files: string[]): Promise<boolean>;
  unstage(workspacePath: string, files: string[]): Promise<boolean>;
  commit(workspacePath: string, message: string): Promise<boolean>;
  checkout(workspacePath: string, branch: string): Promise<boolean>;
  branch(workspacePath: string, name?: string, create?: boolean): Promise<Array<{ name: string; current: boolean; remote: boolean }>>;
  diff(workspacePath: string, file?: string): Promise<string>;
  discard(workspacePath: string, files: string[]): Promise<boolean>;
}

interface SearchAPI {
  search(options: {
    query: string;
    path: string;
    caseSensitive?: boolean;
    wholeWord?: boolean;
    regex?: boolean;
  }): Promise<Array<{
    file: string;
    line: number;
    column: number;
    match: string;
    context: string;
  }>>;
}

// ============================================================================
// AI Agent (MCP) Types
// ============================================================================

interface AIAgentConfig {
  pythonPath?: string;
  agentPath?: string;
  workspace?: string;
}

interface AIAgentStatus {
  connected: boolean;
  reconnectAttempts: number;
  pendingRequests: number;
}

interface MCPTool {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}

interface MCPToolResult {
  content: Array<{
    type: 'text' | 'image';
    text?: string;
    data?: string;
    mimeType?: string;
  }>;
  isError?: boolean;
}

interface MCPResource {
  uri: string;
  name?: string;
  description?: string;
  mimeType?: string;
}

interface MCPPrompt {
  name: string;
  description?: string;
  arguments?: Array<{
    name: string;
    description?: string;
    required?: boolean;
  }>;
}

interface AIAgentEvent {
  event: string;
  data: unknown;
}

interface HardwareValidationRequest {
  chip?: string;
  peripherals?: string[];
  clockConfig?: Record<string, unknown>;
  interrupts?: string[];
}

interface HardwareValidationResult {
  valid: boolean;
  issues: string[];
  warnings: string[];
  suggestions: string[];
}

interface FirmwareAnalysisRequest {
  filePath?: string;
  code?: string;
  language?: string;
  targetChip?: string;
}

interface FirmwareAnalysisResult {
  summary: string;
  issues: string[];
  dependencies: string[];
  registerUsage: string[];
  isrAnalysis?: string[];
  callGraph?: string[];
}

interface AIAgentAPI {
  connect(options?: AIAgentConfig): Promise<{ success: boolean; error?: string }>;
  disconnect(): Promise<{ success: boolean; error?: string }>;
  status(): Promise<AIAgentStatus>;

  listTools(): Promise<{ success: boolean; tools?: MCPTool[]; error?: string }>;
  callTool(name: string, args?: Record<string, unknown>): Promise<{ success: boolean; result?: MCPToolResult; error?: string }>;

  hardware: {
    validate(config: HardwareValidationRequest): Promise<{ success: boolean; result?: HardwareValidationResult; error?: string }>;
    planInit(params: { chip: string; peripheral: string }): Promise<{ success: boolean; result?: unknown; error?: string }>;
    reason(params: { question: string; context?: Record<string, unknown> }): Promise<{ success: boolean; result?: unknown; error?: string }>;
  };

  firmware: {
    analyze(params: FirmwareAnalysisRequest): Promise<{ success: boolean; result?: FirmwareAnalysisResult; error?: string }>;
    debug(params: { code: string; error: string }): Promise<{ success: boolean; result?: unknown; error?: string }>;
    generateCode(params: { spec: string; context?: string }): Promise<{ success: boolean; result?: unknown; error?: string }>;
  };

  knowledge: {
    query(params: { query: string; topK?: number }): Promise<{ success: boolean; result?: unknown; error?: string }>;
    crossValidate(params: Record<string, unknown>): Promise<{ success: boolean; result?: unknown; error?: string }>;
  };

  listResources(): Promise<{ success: boolean; resources?: MCPResource[]; error?: string }>;
  readResource(uri: string): Promise<{ success: boolean; resource?: unknown; error?: string }>;

  listPrompts(): Promise<{ success: boolean; prompts?: MCPPrompt[]; error?: string }>;
  getPrompt(name: string, args?: Record<string, unknown>): Promise<{ success: boolean; prompt?: unknown; error?: string }>;

  subscribe(eventName: string, channel: string): Promise<{ success: boolean; error?: string }>;
  unsubscribe(eventName: string): Promise<{ success: boolean; error?: string }>;
  onEvent(channel: string, callback: (event: AIAgentEvent) => void): void;
}

// ============================================================================
// Window Interface
// ============================================================================

interface Window {
  electronAPI?: {
    openDirectory(): Promise<string | undefined>;
    readDirectory(path: string): Promise<FileEntry[]>;
    readFile(path: string): Promise<string | null>;
    writeFile(path: string, content: string): Promise<boolean>;
    createFile(path: string): Promise<boolean>;
    createDirectory(path: string): Promise<boolean>;
    deleteFile(path: string): Promise<boolean>;
    rename(oldPath: string, newPath: string): Promise<boolean>;
    
    // Legacy Git methods
    gitStatus?(): Promise<GitStatus>;
    gitBranch?(): Promise<string>;
    gitCommit?(message: string): Promise<boolean>;
    gitStage?(files: string[]): Promise<boolean>;
    gitUnstage?(files: string[]): Promise<boolean>;
    gitCheckout?(branch: string): Promise<boolean>;
    gitDiscard?(path: string): Promise<boolean>;
    gitLog?(limit?: number): Promise<GitLogEntry[]>;
    gitDiff?(path?: string): Promise<string>;
    
    // Structured Git API
    git: GitAPI;
    
    // Other APIs
    ai: AIAPI;
    storage: StorageAPI;
    steering?: SteeringAPI;
    terminal: TerminalAPI;
    search?: SearchAPI;
    app?: AppAPI;
    
    // AI Agent (MCP - Python Agent)
    aiAgent?: AIAgentAPI;
    
    // Ollama
    ollamaHealth?(timeout?: number): Promise<OllamaHealthStatus>;
    ollamaListModels?(): Promise<OllamaModel[]>;
    ollamaGenerate?(options: {
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
    }): Promise<{ content?: string; error?: string }>;
    ollamaPullModel?(model: string, onProgress?: (progress: PullProgress) => void): Promise<boolean>;
    ollamaGetContextLimit?(model: string): Promise<number>;
    ollamaOnChunk?(callback: (chunk: string) => void): void;
    
    // Events
    onFileChange(callback: (path: string) => void): void;
    onGitStatusChange(callback: () => void): void;
    showContextMenu?(): void;
    minimizeWindow?(): void;
    maximizeWindow?(): void;
    closeWindow?(): void;
    isMaximized?(): Promise<boolean>;
    
    // Legacy/Extension
    code?: {
      analyze?: (filePath: string, content: string) => Promise<unknown>;
      review?: (filePath: string, content: string) => Promise<unknown[]>;
      applyFix?: (fix: unknown) => Promise<unknown>;
      applyMultipleFixes?: (fixes: unknown[]) => Promise<unknown[]>;
    };
    extension?: {
      load?: () => Promise<void>;
      unload?: () => Promise<void>;
      list?: () => Promise<unknown[]>;
      runDetector?: (name: string) => Promise<unknown[]>;
      runAllDetectors?: () => Promise<unknown[]>;
      executeCommand?: (command: string) => Promise<void>;
    };
    commands?: {
      getAll?: () => Promise<unknown[]>;
      execute?: (command: string) => Promise<void>;
    };
    
    // Direct storage helpers
    storeSet?: (key: string, value: unknown) => Promise<void>;
    storeGet?: (key: string) => Promise<unknown>;
  };
}
