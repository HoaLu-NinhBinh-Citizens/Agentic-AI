export interface FileNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: FileNode[];
  isOpen?: boolean;
}

export interface Task {
  id: string;
  title: string;
  description?: string;
  status: 'todo' | 'doing' | 'done';
  priority: 'low' | 'medium' | 'high';
  createdAt: string;
  completedAt?: string;
}

export interface Spec {
  id: string;
  title: string;
  content: string;
  tasks: Task[];
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface SteeringContext {
  agents?: string;
  claude?: string;
  product?: string;
  tech?: string;
  structure?: string;
}

// ============================================================================
// Code Analysis Types
// ============================================================================

export interface CodeIssue {
  id: string;
  severity: 'error' | 'warning' | 'info';
  rule: string;
  message: string;
  line: number;
  column?: number;
  fix?: FixSuggestion;
}

export interface FixSuggestion {
  original: string;
  replacement: string;
  description: string;
}

export interface FunctionInfo {
  name: string;
  startLine: number;
  endLine: number;
  params: string[];
  async: boolean;
  complexity: number;
}

export interface ImportInfo {
  source: string;
  imported: string[];
  startLine: number;
}

export interface ExportInfo {
  name: string;
  type: 'function' | 'class' | 'variable' | 'default';
  startLine: number;
}

export interface AnalysisResult {
  functions: FunctionInfo[];
  imports: ImportInfo[];
  exports: ExportInfo[];
  complexity: number;
  issues: CodeIssue[];
}

export interface CodeReviewResult {
  filePath: string;
  analysis: AnalysisResult;
  securityIssues: CodeIssue[];
  totalIssues: number;
  errorCount: number;
  warningCount: number;
  infoCount: number;
}

// ============================================================================
// Command Palette Types
// ============================================================================

export interface Command {
  id: string;
  label: string;
  shortcut?: string;
  category: string;
  icon?: string;
}

export interface CommandExecutionResult {
  success: boolean;
  error?: string;
  output?: unknown;
}

// ============================================================================
// Fix Types
// ============================================================================

export interface Fix {
  file: string;
  original: string;
  replacement: string;
  explanation: string;
}

export interface FixResult {
  success: boolean;
  applied: Fix[];
  failed: Fix[];
  errors: string[];
}

// ============================================================================
// Git Types (Phase 3)
// ============================================================================

export interface GitStatus {
  modified: string[];
  staged: string[];
  created: string[];
  deleted: string[];
  not_added: string[];
  current: string;
  tracking: string | null;
}

export interface GitInfo {
  isRepo: boolean;
  branch: string;
  branches: string[];
  status: GitStatus | null;
  remotes: string[];
}

export interface CommitInfo {
  hash: string;
  message: string;
  author: string;
  date: string;
}

// ============================================================================
// Search Types (Phase 3)
// ============================================================================

export interface SearchResult {
  file: string;
  line: number;
  column: number;
  match: string;
  context: string;
}

export interface SearchOptions {
  query: string;
  path: string;
  caseSensitive?: boolean;
  wholeWord?: boolean;
  regex?: boolean;
  include?: string[];
  exclude?: string[];
  maxResults?: number;
}

// ============================================================================
// Extension Types (Phase 3)
// ============================================================================

export interface Extension {
  id: string;
  name: string;
  version: string;
  description?: string;
  author?: string;
  main: string;
  contributions?: ExtensionContributions;
}

export interface ExtensionContributions {
  commands?: Array<{
    command: string;
    title: string;
    category?: string;
  }>;
  menus?: Array<{
    command: string;
    where: string;
  }>;
  detectors?: Array<{
    id: string;
    name: string;
    pattern: string;
  }>;
  views?: Array<{
    id: string;
    name: string;
    type: 'list' | 'webview';
  }>;
}

export interface DetectorResult {
  severity: 'error' | 'warning' | 'info';
  message: string;
  line: number;
  rule: string;
}

export interface AppState {
  workspacePath: string | null;
  files: FileNode[];
  activeFile: string | null;
  openFiles: string[];
  spec: Spec | null;
  tasks: Task[];
  messages: ChatMessage[];
  steeringContext: SteeringContext;
}

// ============================================================================
// Ollama Types
// ============================================================================

export interface OllamaModel {
  name: string;
  modified_at: string;
  size: number;
}

export interface OllamaHealthStatus {
  available: boolean;
  error?: string;
  latencyMs?: number;
}

export interface PullProgress {
  status: string;
  digest?: string;
  total?: number;
  completed?: number;
  percent?: number;
}

export interface OllamaGenerateOptions {
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
}

// ============================================================================
// AI Provider Config Types
// ============================================================================

export type AIProvider = 'ollama' | 'openai' | 'anthropic';

export interface AIProviderConfig {
  provider: AIProvider;
  ollamaEndpoint?: string;
  ollamaModel?: string;
  ollamaTemperature?: number;
  openaiApiKey?: string;
  openaiModel?: string;
  anthropicApiKey?: string;
  anthropicModel?: string;
}

// ============================================================================
// Git API Types (Phase 3)
// ============================================================================

export interface GitAPI {
  info: (workspacePath: string) => Promise<GitInfo>;
  status: () => Promise<GitStatus | null>;
  log: (workspacePath: string, limit?: number) => Promise<CommitInfo[]>;
  stage: (workspacePath: string, files: string[]) => Promise<boolean>;
  unstage: (workspacePath: string, files: string[]) => Promise<boolean>;
  commit: (workspacePath: string, message: string) => Promise<boolean>;
  checkout: (workspacePath: string, branch: string) => Promise<boolean>;
  branch: (workspacePath: string, name?: string, create?: boolean) => Promise<string | null>;
  diff: (workspacePath: string, file?: string) => Promise<string>;
  discard: (workspacePath: string, files: string[]) => Promise<boolean>;
}
