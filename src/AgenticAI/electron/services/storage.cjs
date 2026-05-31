'use strict';

const Store = require('electron-store');
const path = require('path');

const defaultSettings = {
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

const defaultUIState = {
  sidebarWidth: 240,
  taskPanelWidth: 300,
  chatPanelWidth: 320,
  terminalHeight: 200,
  activePanel: 'files',
  expandedFolders: [],
};

const defaultOpenFiles = {
  files: [],
  activeFile: null,
};

const defaultChat = {
  messages: [],
  conversationId: null,
};

const defaultEditorState = {};

class StorageService {
  constructor() {
    this.store = new Store({
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

  getSettings() {
    return this.store.get('settings');
  }

  updateSettings(updates) {
    const current = this.getSettings();
    this.store.set('settings', { ...current, ...updates });
  }

  getAPIKey() {
    return this.store.get('settings').aiApiKey;
  }

  setAPIKey(key) {
    const settings = this.getSettings();
    settings.aiApiKey = key;
    this.store.set('settings', settings);
  }

  hasAPIKey() {
    const key = this.getAPIKey();
    return !!key && key.length > 0;
  }

  clearAPIKey() {
    const settings = this.getSettings();
    settings.aiApiKey = undefined;
    this.store.set('settings', settings);
  }

  getCurrentWorkspace() {
    return this.store.get('currentWorkspace');
  }

  setCurrentWorkspace(workspacePath) {
    const name = path.basename(workspacePath);
    const workspace = {
      path: workspacePath,
      name,
      lastOpened: new Date().toISOString(),
    };
    this.store.set('currentWorkspace', workspace);
    this._addToRecentWorkspaces(workspace);
  }

  getRecentWorkspaces() {
    return this.store.get('recentWorkspaces');
  }

  clearRecentWorkspaces() {
    this.store.set('recentWorkspaces', []);
  }

  _addToRecentWorkspaces(workspace) {
    const recent = this.getRecentWorkspaces();
    const filtered = recent.filter(w => w.path !== workspace.path);
    const updated = [workspace, ...filtered].slice(0, 10);
    this.store.set('recentWorkspaces', updated);
  }

  getUIState() {
    return this.store.get('uiState');
  }

  updateUIState(updates) {
    const current = this.getUIState();
    this.store.set('uiState', { ...current, ...updates });
  }

  addExpandedFolder(folderPath) {
    const uiState = this.getUIState();
    if (!uiState.expandedFolders.includes(folderPath)) {
      uiState.expandedFolders.push(folderPath);
      this.store.set('uiState', uiState);
    }
  }

  removeExpandedFolder(folderPath) {
    const uiState = this.getUIState();
    uiState.expandedFolders = uiState.expandedFolders.filter(p => p !== folderPath);
    this.store.set('uiState', uiState);
  }

  getOpenFiles() {
    return this.store.get('openFiles');
  }

  updateOpenFiles(updates) {
    const current = this.getOpenFiles();
    this.store.set('openFiles', { ...current, ...updates });
  }

  getTasks() {
    return this.store.get('tasks');
  }

  saveTasks(tasks) {
    this.store.set('tasks', tasks);
  }

  addTask(task) {
    const tasks = this.getTasks();
    tasks.push(task);
    this.saveTasks(tasks);
  }

  updateTask(id, updates) {
    const tasks = this.getTasks();
    const index = tasks.findIndex(t => t.id === id);
    if (index !== -1) {
      tasks[index] = { ...tasks[index], ...updates };
      this.saveTasks(tasks);
    }
  }

  deleteTask(id) {
    const tasks = this.getTasks().filter(t => t.id !== id);
    this.saveTasks(tasks);
  }

  getSpecs() {
    return this.store.get('specs');
  }

  saveSpec(spec) {
    const specs = this.getSpecs();
    const index = specs.findIndex(s => s.id === spec.id);
    if (index !== -1) {
      specs[index] = spec;
    } else {
      specs.push(spec);
    }
    this.store.set('specs', specs);
  }

  deleteSpec(id) {
    const specs = this.getSpecs().filter(s => s.id !== id);
    this.store.set('specs', specs);
  }

  getChat() {
    return this.store.get('chat');
  }

  saveChat(messages) {
    const chat = this.getChat();
    chat.messages = messages;
    this.store.set('chat', chat);
  }

  addChatMessage(message) {
    const chat = this.getChat();
    chat.messages.push(message);
    this.store.set('chat', chat);
  }

  clearChat() {
    this.store.set('chat', { messages: [], conversationId: null });
  }

  getEditorState() {
    return this.store.get('editorState');
  }

  getFileEditorState(filePath) {
    const state = this.getEditorState();
    return state[filePath];
  }

  saveFileEditorState(filePath, fileState) {
    const state = this.getEditorState();
    state[filePath] = fileState;
    this.store.set('editorState', state);
  }

  removeFileEditorState(filePath) {
    const state = this.getEditorState();
    delete state[filePath];
    this.store.set('editorState', state);
  }

  clearFileEditorState() {
    this.store.set('editorState', {});
  }

  exportData() {
    return this.store.store;
  }

  importData(data) {
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

  clearAll() {
    this.store.clear();
  }

  getStorePath() {
    return this.store.path;
  }

  resetToDefaults() {
    this.store.set('settings', defaultSettings);
    this.store.set('uiState', defaultUIState);
    this.store.set('openFiles', defaultOpenFiles);
    this.store.set('tasks', []);
    this.store.set('specs', []);
    this.store.set('chat', defaultChat);
    this.store.set('editorState', defaultEditorState);
  }
}

module.exports = { storage: new StorageService(), StorageService };
