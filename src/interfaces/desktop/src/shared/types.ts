// ============================================
// AgenticAI - Shared Types
// ============================================

// File System Types
export interface FileItem {
  name: string;
  path: string;
  isDir: boolean;
  children?: FileItem[];
}

export interface FileNode extends FileItem {
  expanded?: boolean;
  children?: FileNode[];
}

// Task & Spec Types
export type TaskStatus = 'todo' | 'doing' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical';

export interface Task {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  createdAt: number;
  updatedAt: number;
  tags?: string[];
  assignee?: string;
}

export interface Spec {
  id: string;
  title: string;
  description: string;
  requirements: string[];
  createdAt: number;
  updatedAt: number;
}

export interface ImplementationPlan {
  id: string;
  specId: string;
  title: string;
  steps: PlanStep[];
  createdAt: number;
}

export interface PlanStep {
  id: string;
  order: number;
  title: string;
  description: string;
  taskIds: string[];
  status: 'pending' | 'in_progress' | 'completed';
}

// Chat Types
export type MessageRole = 'user' | 'assistant' | 'system';

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  attachments?: FileAttachment[];
  isStreaming?: boolean;
}

export interface FileAttachment {
  path: string;
  name: string;
  type: string;
}

// AI Agent Types
export interface AIContext {
  workspacePath: string;
  steeringFiles: SteeringFile[];
  currentSpec?: Spec;
  currentTasks: Task[];
  openFiles: string[];
}

export interface SteeringFile {
  name: string;
  path: string;
  content: string;
}

export interface AIResponse {
  message: string;
  tasks?: Partial<Task>[];
  codeSnippets?: CodeSnippet[];
  suggestions?: string[];
}

export interface CodeSnippet {
  language: string;
  code: string;
  filePath?: string;
  action?: 'create' | 'modify' | 'delete';
}

// Editor Types
export interface EditorTab {
  id: string;
  path: string;
  name: string;
  content: string;
  language: string;
  modified: boolean;
}

// Panel Types
export type PanelType = 'spec' | 'tasks' | 'plan';

export interface PanelState {
  visible: boolean;
  type: PanelType;
}

// Command Palette
export interface Command {
  id: string;
  label: string;
  shortcut?: string;
  action: () => void;
  category: string;
}

// Electron API
export interface ElectronAPI {
  // Backend
  getBackendUrl: () => Promise<string>;
  getWorkspacePath: () => Promise<string>;
  openExternal: (url: string) => Promise<void>;
  
  // File System
  readFile: (path: string) => Promise<string>;
  readDir: (path: string) => Promise<FileItem[]>;
  writeFile: (path: string, content: string) => Promise<void>;
  createDirectory: (path: string) => Promise<void>;
  deleteFile: (path: string) => Promise<void>;
  renameFile: (oldPath: string, newPath: string) => Promise<void>;
  
  // AI Agent
  sendToAI: (message: string, context: AIContext) => Promise<AIResponse>;
  getSteeringFiles: () => Promise<SteeringFile[]>;
  
  // Tasks
  loadSpec: () => Promise<Spec | null>;
  saveSpec: (spec: Spec) => Promise<void>;
  loadTasks: () => Promise<Task[]>;
  saveTasks: (tasks: Task[]) => Promise<void>;
  
  // Events
  onBackendStatus: (callback: (status: 'connected' | 'disconnected') => void) => void;
  onFileChange: (callback: (path: string) => void) => void;
}

declare global {
  interface Window {
    electronAPI: ElectronAPI;
  }
}
