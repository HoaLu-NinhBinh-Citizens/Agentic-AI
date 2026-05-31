import Store from 'electron-store';
import * as path from 'path';

export interface StoredWorkspace {
  path: string;
  name: string;
  lastOpened: string;
}

export interface StoredSettings {
  aiProvider: 'openai' | 'anthropic';
  aiApiKey?: string;
  aiModel?: string;
  maxTokens: number;
  temperature: number;
  theme: 'dark' | 'light';
  fontSize: number;
  fontFamily: string;
  tabSize: number;
  autoSave: boolean;
  autoSaveDelay: number;
}

export interface StoredUIState {
  sidebarWidth: number;
  taskPanelWidth: number;
  chatPanelWidth: number;
  terminalHeight: number;
  activePanel: 'files' | 'search' | 'git' | 'extensions' | 'tasks';
  expandedFolders: string[];
}

export interface StoredOpenFiles {
  files: string[];
  activeFile: string | null;
}

export interface StoredTask {
  id: string;
  title: string;
  description?: string;
  status: 'todo' | 'doing' | 'done';
  priority: 'low' | 'medium' | 'high';
  createdAt: string;
  completedAt?: string;
}

export interface StoredSpec {
  id: string;
  title: string;
  content: string;
  tasks: StoredTask[];
  createdAt: string;
  updatedAt: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

export interface StoredChat {
  messages: ChatMessage[];
  conversationId: string | null;
}

export interface EditorState {
  cursorPosition?: { line: number; column: number };
  scrollPosition?: { top: number; left: number };
}

export interface FileEditorState {
  content?: string;
  cursorPosition?: { line: number; column: number };
  scrollPosition?: { top: number; left: number };
}

export interface StoredEditorState {
  [filePath: string]: FileEditorState;
}

interface StoreSchema {
  settings: StoredSettings;
  recentWorkspaces: StoredWorkspace[];
  currentWorkspace: StoredWorkspace | null;
  uiState: StoredUIState;
  openFiles: StoredOpenFiles;
  tasks: StoredTask[];
  specs: StoredSpec[];
  chat: StoredChat;
  editorState: StoredEditorState;
}

const defaultSettings: StoredSettings = {
  aiProvider: 'openai',
  aiApiKey: undefined,
  aiModel: 'gpt-4',
  maxTokens: 4096,
  temperature: 0.7,
  theme: 'dark',
  fontSize: 14,
  fontFamily: 'Fira Code, Consolas, monospace',
  tabSize: 2,
  autoSave: true,
  autoSaveDelay: 1000,
};

const defaultUIState: StoredUIState = {
  sidebarWidth: 240,
  taskPanelWidth: 300,
  chatPanelWidth: 320,
  terminalHeight: 200,
  activePanel: 'files',
  expandedFolders: [],
};

const defaultOpenFiles: StoredOpenFiles = {
  files: [],
  activeFile: null,
};

const defaultChat: StoredChat = {
  messages: [],
  conversationId: null,
};

const defaultEditorState: StoredEditorState = {};

class StorageService {
  private store: Store<StoreSchema>;

  constructor() {
    this.store = new Store<StoreSchema>({
      name: 'agentic-ai-config',
      defaults: {
        settings: defaultSettings,
        recentWorkspaces: [],
        currentWorkspace: null,
        uiState: defaultUIState,
        openFiles: defaultOpenFiles,
        tasks: [],
        specs: [],
        chat: defaultChat,
        editorState: defaultEditorState,
      },
    });
  }

  getSettings(): StoredSettings {
    return this.store.get('settings');
  }

  updateSettings(updates: Partial<StoredSettings>): void {
    const current = this.getSettings();
    this.store.set('settings', { ...current, ...updates });
  }

  getAPIKey(): string | undefined {
    return this.store.get('settings').aiApiKey;
  }

  setAPIKey(key: string): void {
    const settings = this.getSettings();
    settings.aiApiKey = key;
    this.store.set('settings', settings);
  }

  hasAPIKey(): boolean {
    const key = this.getAPIKey();
    return !!key && key.length > 0;
  }

  clearAPIKey(): void {
    const settings = this.getSettings();
    settings.aiApiKey = undefined;
    this.store.set('settings', settings);
  }

  getCurrentWorkspace(): StoredWorkspace | null {
    return this.store.get('currentWorkspace');
  }

  setCurrentWorkspace(workspacePath: string): void {
    const name = path.basename(workspacePath);
    const workspace: StoredWorkspace = {
      path: workspacePath,
      name,
      lastOpened: new Date().toISOString(),
    };
    this.store.set('currentWorkspace', workspace);
    this.addToRecentWorkspaces(workspace);
  }

  getRecentWorkspaces(): StoredWorkspace[] {
    return this.store.get('recentWorkspaces');
  }

  clearRecentWorkspaces(): void {
    this.store.set('recentWorkspaces', []);
  }

  private addToRecentWorkspaces(workspace: StoredWorkspace): void {
    const recent = this.getRecentWorkspaces();
    const filtered = recent.filter(w => w.path !== workspace.path);
    const updated = [workspace, ...filtered].slice(0, 10);
    this.store.set('recentWorkspaces', updated);
  }

  getUIState(): StoredUIState {
    return this.store.get('uiState');
  }

  updateUIState(updates: Partial<StoredUIState>): void {
    const current = this.getUIState();
    this.store.set('uiState', { ...current, ...updates });
  }

  addExpandedFolder(folderPath: string): void {
    const uiState = this.getUIState();
    if (!uiState.expandedFolders.includes(folderPath)) {
      uiState.expandedFolders.push(folderPath);
      this.store.set('uiState', uiState);
    }
  }

  removeExpandedFolder(folderPath: string): void {
    const uiState = this.getUIState();
    uiState.expandedFolders = uiState.expandedFolders.filter(p => p !== folderPath);
    this.store.set('uiState', uiState);
  }

  getOpenFiles(): StoredOpenFiles {
    return this.store.get('openFiles');
  }

  updateOpenFiles(updates: Partial<StoredOpenFiles>): void {
    const current = this.getOpenFiles();
    this.store.set('openFiles', { ...current, ...updates });
  }

  getTasks(): StoredTask[] {
    return this.store.get('tasks');
  }

  saveTasks(tasks: StoredTask[]): void {
    this.store.set('tasks', tasks);
  }

  addTask(task: StoredTask): void {
    const tasks = this.getTasks();
    tasks.push(task);
    this.saveTasks(tasks);
  }

  updateTask(id: string, updates: Partial<StoredTask>): void {
    const tasks = this.getTasks();
    const index = tasks.findIndex(t => t.id === id);
    if (index !== -1) {
      tasks[index] = { ...tasks[index], ...updates };
      this.saveTasks(tasks);
    }
  }

  deleteTask(id: string): void {
    const tasks = this.getTasks().filter(t => t.id !== id);
    this.saveTasks(tasks);
  }

  getSpecs(): StoredSpec[] {
    return this.store.get('specs');
  }

  saveSpec(spec: StoredSpec): void {
    const specs = this.getSpecs();
    const index = specs.findIndex(s => s.id === spec.id);
    if (index !== -1) {
      specs[index] = spec;
    } else {
      specs.push(spec);
    }
    this.store.set('specs', specs);
  }

  deleteSpec(id: string): void {
    const specs = this.getSpecs().filter(s => s.id !== id);
    this.store.set('specs', specs);
  }

  getChat(): StoredChat {
    return this.store.get('chat');
  }

  saveChat(messages: ChatMessage[]): void {
    const chat = this.getChat();
    chat.messages = messages;
    this.store.set('chat', chat);
  }

  addChatMessage(message: ChatMessage): void {
    const chat = this.getChat();
    chat.messages.push(message);
    this.store.set('chat', chat);
  }

  clearChat(): void {
    this.store.set('chat', { messages: [], conversationId: null });
  }

  getEditorState(): StoredEditorState {
    return this.store.get('editorState');
  }

  getFileEditorState(filePath: string): FileEditorState | undefined {
    const state = this.getEditorState();
    return state[filePath];
  }

  saveFileEditorState(filePath: string, fileState: FileEditorState): void {
    const state = this.getEditorState();
    state[filePath] = fileState;
    this.store.set('editorState', state);
  }

  removeFileEditorState(filePath: string): void {
    const state = this.getEditorState();
    delete state[filePath];
    this.store.set('editorState', state);
  }

  clearFileEditorState(): void {
    this.store.set('editorState', {});
  }

  exportData(): StoreSchema {
    return this.store.store;
  }

  importData(data: Partial<StoreSchema>): void {
    if (data.settings) this.store.set('settings', data.settings);
    if (data.recentWorkspaces) this.store.set('recentWorkspaces', data.recentWorkspaces);
    if (data.currentWorkspace) this.store.set('currentWorkspace', data.currentWorkspace);
    if (data.uiState) this.store.set('uiState', data.uiState);
    if (data.openFiles) this.store.set('openFiles', data.openFiles);
    if (data.tasks) this.store.set('tasks', data.tasks);
    if (data.specs) this.store.set('specs', data.specs);
    if (data.chat) this.store.set('chat', data.chat);
    if (data.editorState) this.store.set('editorState', data.editorState);
  }

  clearAll(): void {
    this.store.clear();
  }

  getStorePath(): string {
    return this.store.path;
  }

  resetToDefaults(): void {
    this.store.set('settings', defaultSettings);
    this.store.set('uiState', defaultUIState);
    this.store.set('openFiles', defaultOpenFiles);
    this.store.set('tasks', []);
    this.store.set('specs', []);
    this.store.set('chat', defaultChat);
    this.store.set('editorState', defaultEditorState);
  }
}

export const storage = new StorageService();
