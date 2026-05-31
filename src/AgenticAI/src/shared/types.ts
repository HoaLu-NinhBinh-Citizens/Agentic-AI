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
