import { create } from 'zustand';
import { FileNode, Task, Spec, ChatMessage, SteeringContext } from '../../shared/types';

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
  setActiveFile: (path: string | null) => void;
  addOpenFile: (path: string) => void;
  removeOpenFile: (path: string) => void;
  
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
}

export const useAppStore = create<AppStore>((set) => ({
  workspacePath: null,
  setWorkspacePath: (path) => set({ workspacePath: path }),
  
  files: [],
  setFiles: (files) => set({ files }),
  toggleFolder: (path) => set((state) => ({
    files: toggleFolderInTree(state.files, path)
  })),
  
  activeFile: null,
  openFiles: [],
  setActiveFile: (path) => set({ activeFile: path }),
  addOpenFile: (path) => set((state) => ({
    openFiles: state.openFiles.includes(path) ? state.openFiles : [...state.openFiles, path]
  })),
  removeOpenFile: (path) => set((state) => ({
    openFiles: state.openFiles.filter(f => f !== path),
    activeFile: state.activeFile === path ? state.openFiles[0] : state.activeFile
  })),
  
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
  setSteeringContext: (context) => set({ steeringContext: context })
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
