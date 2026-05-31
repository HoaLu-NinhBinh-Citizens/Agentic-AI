import { create } from 'zustand';
import { FileNode, Task, Spec, ChatMessage, SteeringContext, OllamaModel, OllamaHealthStatus, AIProviderConfig } from '../../shared/types';

export type SidebarView = 'explorer' | 'search' | 'git' | 'terminal' | 'settings';

interface CursorPosition {
  line: number;
  column: number;
}

interface AppStore {
  // Workspace
  workspacePath: string | null;
  setWorkspacePath: (path: string | null) => void;
  
  // Files
  files: FileNode[];
  setFiles: (files: FileNode[]) => void;
  toggleFolder: (path: string) => void;
  
  // Editor
  activeFile: string | null;
  openFiles: string[];
  cursorPosition: CursorPosition | null;
  setActiveFile: (path: string | null) => void;
  addOpenFile: (path: string) => void;
  removeOpenFile: (path: string) => void;
  setCursorPosition: (pos: CursorPosition | null) => void;
  
  // Spec & Tasks
  spec: Spec | null;
  tasks: Task[];
  setSpec: (spec: Spec | null) => void;
  addTask: (task: Task) => void;
  updateTask: (id: string, updates: Partial<Task>) => void;
  deleteTask: (id: string) => void;
  
  // Chat
  messages: ChatMessage[];
  addMessage: (message: ChatMessage) => void;
  clearMessages: () => void;
  
  // Steering
  steeringContext: SteeringContext;
  setSteeringContext: (context: SteeringContext) => void;
  
  // UI State - Expanded Folders
  expandedFolders: string[];
  addExpandedFolder: (path: string) => void;
  removeExpandedFolder: (path: string) => void;

  // UI State - Sidebar View
  activeSidebarView: SidebarView;
  setActiveSidebarView: (view: SidebarView) => void;
  
  // UI State - Terminal
  isTerminalOpen: boolean;
  setTerminalOpen: (open: boolean) => void;
  
  // UI State - Settings
  isSettingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;

  // AI Config
  aiConfig: AIProviderConfig | null;
  setAiConfig: (config: AIProviderConfig | null) => void;

  // Ollama state
  ollamaHealth: OllamaHealthStatus | null;
  setOllamaHealth: (status: OllamaHealthStatus | null) => void;
  ollamaModels: OllamaModel[];
  setOllamaModels: (models: OllamaModel[]) => void;
}

export const useAppStore = create<AppStore>((set) => ({
  workspacePath: null,
  setWorkspacePath: (path) => set({ workspacePath: path }),
  
  files: [],
  setFiles: (files) => set({ files }),
  toggleFolder: (path) => set((state) => ({
    files: toggleFolderInTree(state.files, path),
    expandedFolders: state.expandedFolders.includes(path)
      ? state.expandedFolders.filter(p => p !== path)
      : [...state.expandedFolders, path]
  })),
  
  activeFile: null,
  openFiles: [],
  cursorPosition: null,
  setActiveFile: (path) => set({ activeFile: path }),
  addOpenFile: (path) => set((state) => ({
    openFiles: state.openFiles.includes(path) ? state.openFiles : [...state.openFiles, path]
  })),
  removeOpenFile: (path) => set((state) => ({
    openFiles: state.openFiles.filter(f => f !== path),
    activeFile: state.activeFile === path 
      ? state.openFiles.find(f => f !== path) || null 
      : state.activeFile
  })),
  setCursorPosition: (pos) => set({ cursorPosition: pos }),
  
  spec: null,
  tasks: [],
  setSpec: (spec) => set({ spec, tasks: spec?.tasks || [] }),
  addTask: (task) => set((state) => ({ tasks: [...state.tasks, task] })),
  updateTask: (id, updates) => set((state) => ({
    tasks: state.tasks.map(t => t.id === id ? { ...t, ...updates } : t)
  })),
  deleteTask: (id) => set((state) => ({
    tasks: state.tasks.filter(t => t.id !== id)
  })),
  
  messages: [],
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  clearMessages: () => set({ messages: [] }),
  
  steeringContext: {},
  setSteeringContext: (context) => set({ steeringContext: context }),
  
  expandedFolders: [],
  addExpandedFolder: (path) => set((state) => ({
    expandedFolders: state.expandedFolders.includes(path) 
      ? state.expandedFolders 
      : [...state.expandedFolders, path]
  })),
  removeExpandedFolder: (path) => set((state) => ({
    expandedFolders: state.expandedFolders.filter(p => p !== path)
  })),

  // UI State - Sidebar View
  activeSidebarView: 'explorer',
  setActiveSidebarView: (view) => set({ activeSidebarView: view }),
  
  // UI State - Terminal
  isTerminalOpen: false,
  setTerminalOpen: (open) => set({ isTerminalOpen: open }),
  
  // UI State - Settings
  isSettingsOpen: false,
  setSettingsOpen: (open) => set({ isSettingsOpen: open }),

  // AI Config
  aiConfig: null,
  setAiConfig: (config) => set({ aiConfig: config }),

  // Ollama
  ollamaHealth: null,
  setOllamaHealth: (status) => set({ ollamaHealth: status }),
  ollamaModels: [],
  setOllamaModels: (models) => set({ ollamaModels: models }),
}));

function toggleFolderInTree(files: FileNode[], path: string): FileNode[] {
  return files.map(node => {
    if (node.path === path) {
      return { ...node, isOpen: !node.isOpen };
    }
    if (node.children) {
      return { ...node, children: toggleFolderInTree(node.children, path) };
    }
    return node;
  });
}
