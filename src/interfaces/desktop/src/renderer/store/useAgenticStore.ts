import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';

// ============================================
// AgenticAI - Zustand Store
// ============================================

// Types
export type TaskStatus = 'todo' | 'doing' | 'done';
export type TaskPriority = 'low' | 'medium' | 'high' | 'critical';
export type PanelType = 'spec' | 'tasks' | 'plan';
export type MessageRole = 'user' | 'assistant' | 'system';

export interface Task {
  id: string;
  title: string;
  description?: string;
  status: TaskStatus;
  priority: TaskPriority;
  createdAt: number;
  updatedAt: number;
  tags?: string[];
}

export interface Spec {
  id: string;
  title: string;
  description: string;
  requirements: string[];
  createdAt: number;
  updatedAt: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  timestamp: number;
  isStreaming?: boolean;
}

export interface EditorTab {
  id: string;
  path: string;
  name: string;
  content: string;
  language: string;
  modified: boolean;
}

export interface SteeringFile {
  name: string;
  path: string;
  content: string;
}

// Store Interface
interface AgenticStore {
  // Workspace
  workspacePath: string;
  setWorkspacePath: (path: string) => void;
  
  // Steering Files
  steeringFiles: SteeringFile[];
  setSteeringFiles: (files: SteeringFile[]) => void;
  
  // Spec
  currentSpec: Spec | null;
  setCurrentSpec: (spec: Spec | null) => void;
  updateSpec: (updates: Partial<Spec>) => void;
  
  // Tasks
  tasks: Task[];
  setTasks: (tasks: Task[]) => void;
  addTask: (task: Omit<Task, 'id' | 'createdAt' | 'updatedAt'>) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  deleteTask: (id: string) => void;
  toggleTaskStatus: (id: string) => void;
  
  // Chat
  messages: ChatMessage[];
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void;
  updateMessage: (id: string, updates: Partial<ChatMessage>) => void;
  clearMessages: () => void;
  
  // Editor
  activeTabId: string | null;
  tabs: EditorTab[];
  openFile: (path: string, content: string) => void;
  closeTab: (id: string) => void;
  setActiveTab: (id: string) => void;
  updateTabContent: (id: string, content: string) => void;
  updateTabModified: (id: string, modified: boolean) => void;
  
  // UI State
  sidebarVisible: boolean;
  toggleSidebar: () => void;
  rightPanelVisible: boolean;
  toggleRightPanel: () => void;
  activeRightPanel: PanelType;
  setActiveRightPanel: (panel: PanelType) => void;
  
  // Backend
  backendConnected: boolean;
  setBackendConnected: (connected: boolean) => void;
  
  // Command Palette
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
}

// Helper
function getLanguageFromPath(path: string): string {
  const ext = path.substring(path.lastIndexOf('.'));
  const langMap: Record<string, string> = {
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'tsx',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.md': 'markdown',
    '.sh': 'bash',
    '.c': 'c',
    '.cpp': 'cpp',
    '.h': 'c',
    '.rs': 'rust',
    '.go': 'go',
    '.html': 'html',
    '.css': 'css',
  };
  return langMap[ext] || 'plaintext';
}

// Create Store
export const useAgenticStore = create<AgenticStore>((set, get) => ({
  // Workspace
  workspacePath: '',
  setWorkspacePath: (path) => set({ workspacePath: path }),
  
  // Steering Files
  steeringFiles: [],
  setSteeringFiles: (files) => set({ steeringFiles: files }),
  
  // Spec
  currentSpec: null,
  setCurrentSpec: (spec) => set({ currentSpec: spec }),
  updateSpec: (updates) => set((state) => ({
    currentSpec: state.currentSpec ? {
      ...state.currentSpec,
      ...updates,
      updatedAt: Date.now(),
    } : null,
  })),
  
  // Tasks
  tasks: [],
  setTasks: (tasks) => set({ tasks }),
  addTask: (task) => set((state) => ({
    tasks: [
      ...state.tasks,
      {
        ...task,
        id: uuidv4(),
        createdAt: Date.now(),
        updatedAt: Date.now(),
      },
    ],
  })),
  updateTask: (id, updates) => set((state) => ({
    tasks: state.tasks.map((t) =>
      t.id === id ? { ...t, ...updates, updatedAt: Date.now() } : t
    ),
  })),
  deleteTask: (id) => set((state) => ({
    tasks: state.tasks.filter((t) => t.id !== id),
  })),
  toggleTaskStatus: (id) => set((state) => ({
    tasks: state.tasks.map((t) => {
      if (t.id !== id) return t;
      const nextStatus: Record<TaskStatus, TaskStatus> = {
        todo: 'doing',
        doing: 'done',
        done: 'todo',
      };
      return { ...t, status: nextStatus[t.status], updatedAt: Date.now() };
    }),
  })),
  
  // Chat
  messages: [],
  addMessage: (message) => set((state) => ({
    messages: [
      ...state.messages,
      {
        ...message,
        id: uuidv4(),
        timestamp: Date.now(),
      },
    ],
  })),
  updateMessage: (id, updates) => set((state) => ({
    messages: state.messages.map((m) =>
      m.id === id ? { ...m, ...updates } : m
    ),
  })),
  clearMessages: () => set({ messages: [] }),
  
  // Editor
  activeTabId: null,
  tabs: [],
  openFile: (path, content) => {
    const state = get();
    const existingTab = state.tabs.find((t) => t.path === path);
    
    if (existingTab) {
      set({ activeTabId: existingTab.id });
    } else {
      const newTab: EditorTab = {
        id: uuidv4(),
        path,
        name: path.split(/[/\\]/).pop() || path,
        content,
        language: getLanguageFromPath(path),
        modified: false,
      };
      set((state) => ({
        tabs: [...state.tabs, newTab],
        activeTabId: newTab.id,
      }));
    }
  },
  closeTab: (id) => set((state) => {
    const tabIndex = state.tabs.findIndex((t) => t.id === id);
    const newTabs = state.tabs.filter((t) => t.id !== id);
    let newActiveId = state.activeTabId;
    
    if (state.activeTabId === id && newTabs.length > 0) {
      const newIndex = Math.min(tabIndex, newTabs.length - 1);
      newActiveId = newTabs[newIndex].id;
    } else if (newTabs.length === 0) {
      newActiveId = null;
    }
    
    return { tabs: newTabs, activeTabId: newActiveId };
  }),
  setActiveTab: (id) => set({ activeTabId: id }),
  updateTabContent: (id, content) => set((state) => ({
    tabs: state.tabs.map((t) =>
      t.id === id ? { ...t, content, modified: true } : t
    ),
  })),
  updateTabModified: (id, modified) => set((state) => ({
    tabs: state.tabs.map((t) =>
      t.id === id ? { ...t, modified } : t
    ),
  })),
  
  // UI State
  sidebarVisible: true,
  toggleSidebar: () => set((state) => ({ sidebarVisible: !state.sidebarVisible })),
  rightPanelVisible: true,
  toggleRightPanel: () => set((state) => ({ rightPanelVisible: !state.rightPanelVisible })),
  activeRightPanel: 'tasks',
  setActiveRightPanel: (panel) => set({ activeRightPanel: panel }),
  
  // Backend
  backendConnected: false,
  setBackendConnected: (connected) => set({ backendConnected: connected }),
  
  // Command Palette
  commandPaletteOpen: false,
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
}));

// Selectors
export const selectTasksByStatus = (status: TaskStatus) => (state: AgenticStore) =>
  state.tasks.filter((t) => t.status === status);

export const selectTaskStats = (state: AgenticStore) => ({
  total: state.tasks.length,
  todo: state.tasks.filter((t) => t.status === 'todo').length,
  doing: state.tasks.filter((t) => t.status === 'doing').length,
  done: state.tasks.filter((t) => t.status === 'done').length,
});

export const selectActiveTab = (state: AgenticStore) =>
  state.tabs.find((t) => t.id === state.activeTabId);
