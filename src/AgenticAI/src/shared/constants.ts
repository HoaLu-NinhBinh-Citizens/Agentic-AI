export const APP_NAME = 'AgenticAI';
export const APP_VERSION = '1.0.0';

export const DEFAULT_SETTINGS = {
  aiProvider: 'openai' as const,
  aiModel: 'gpt-4',
  maxTokens: 4096,
  temperature: 0.7,
  theme: 'dark' as const,
  fontSize: 14,
  fontFamily: 'Fira Code, Consolas, monospace',
  tabSize: 2,
  autoSave: true,
  autoSaveDelay: 1000,
};

export const SUPPORTED_LANGUAGES = {
  typescript: { ext: ['ts', 'tsx'], monaco: 'typescript' },
  javascript: { ext: ['js', 'jsx'], monaco: 'javascript' },
  python: { ext: ['py'], monaco: 'python' },
  json: { ext: ['json'], monaco: 'json' },
  markdown: { ext: ['md', 'mdx'], monaco: 'markdown' },
  css: { ext: ['css', 'scss', 'less'], monaco: 'css' },
  html: { ext: ['html', 'htm'], monaco: 'html' },
  c: { ext: ['c', 'h'], monaco: 'c' },
  cpp: { ext: ['cpp', 'hpp', 'cc'], monaco: 'cpp' },
  rust: { ext: ['rs'], monaco: 'rust' },
  go: { ext: ['go'], monaco: 'go' },
  java: { ext: ['java'], monaco: 'java' },
  sql: { ext: ['sql'], monaco: 'sql' },
  yaml: { ext: ['yaml', 'yml'], monaco: 'yaml' },
  xml: { ext: ['xml'], monaco: 'xml' },
  shell: { ext: ['sh', 'bash', 'zsh'], monaco: 'shell' },
  powershell: { ext: ['ps1'], monaco: 'powershell' },
} as const;

export const STEERING_FILES = [
  'AGENTS.md',
  'CLAUDE.md',
  'product.md',
  'tech.md',
  'structure.md',
  'requirements.md',
] as const;

export const CURSOR_RULES_PATTERNS = [
  '.cursor/rules/*.mdc',
] as const;

export const IGNORED_DIRECTORIES = [
  'node_modules',
  '.git',
  'dist',
  'build',
  '.next',
  '.nuxt',
  'coverage',
  '.cache',
  '__pycache__',
  '.venv',
  'venv',
  'env',
] as const;

export const IGNORED_FILES = [
  '.DS_Store',
  'Thumbs.db',
  '*.pyc',
  '*.pyo',
  '*.so',
  '*.dll',
  '*.dylib',
] as const;

export const DEFAULT_PANEL_SIZES = {
  sidebar: 240,
  taskPanel: 300,
  chatPanel: 320,
  terminal: 200,
} as const;

export const KEYBOARD_SHORTCUTS = {
  save: { key: 's', ctrl: true },
  openFile: { key: 'o', ctrl: true },
  newFile: { key: 'n', ctrl: true },
  newFolder: { key: 'n', ctrl: true, shift: true },
  closeTab: { key: 'w', ctrl: true },
  find: { key: 'f', ctrl: true },
  replace: { key: 'h', ctrl: true },
  commandPalette: { key: 'p', ctrl: true, shift: true },
  quickOpen: { key: 'p', ctrl: true },
  toggleTerminal: { key: '`', ctrl: true },
  toggleSidebar: { key: 'b', ctrl: true },
  settings: { key: ',', ctrl: true },
} as const;

export const IPC_CHANNELS = {
  // Dialog
  dialogOpenDirectory: 'dialog:openDirectory',

  // File System
  fsReadDirectory: 'fs:readDirectory',
  fsReadFile: 'fs:readFile',
  fsWriteFile: 'fs:writeFile',
  fsCreateFile: 'fs:createFile',
  fsCreateDirectory: 'fs:createDirectory',
  fsDeleteFile: 'fs:deleteFile',
  fsRename: 'fs:rename',

  // AI
  aiInitialize: 'ai:initialize',
  aiChat: 'ai:chat',
  aiCodeReview: 'ai:codeReview',
  aiGenerateCode: 'ai:generateCode',
  aiExplainCode: 'ai:explainCode',
  aiIsInitialized: 'ai:isInitialized',

  // Steering
  steeringLoad: 'steering:load',
  steeringGetContext: 'steering:getContext',
  steeringGetSystemPrompt: 'steering:getSystemPrompt',

  // Storage
  storageGetSettings: 'storage:getSettings',
  storageUpdateSettings: 'storage:updateSettings',
  storageGetAPIKey: 'storage:getAPIKey',
  storageSetAPIKey: 'storage:setAPIKey',
  storageGetWorkspace: 'storage:getWorkspace',
  storageSetWorkspace: 'storage:setWorkspace',
  storageGetOpenFiles: 'storage:getOpenFiles',
  storageUpdateOpenFiles: 'storage:updateOpenFiles',
  storageGetTasks: 'storage:getTasks',
  storageSaveTasks: 'storage:saveTasks',
  storageGetChat: 'storage:getChat',
  storageSaveChat: 'storage:saveChat',
  storageGetUIState: 'storage:getUIState',
  storageUpdateUIState: 'storage:updateUIState',

  // Code Analysis (Phase 2)
  codeAnalyze: 'code:analyze',
  codeReview: 'code:review',
  fixApply: 'fix:apply',
  fixApplyMultiple: 'fix:applyMultiple',

  // Command Palette (Phase 2)
  commandsGetAll: 'commands:getAll',
  commandsExecute: 'commands:execute',

  // App
  appGetVersion: 'app:getVersion',
  appMinimize: 'app:minimize',
  appMaximize: 'app:maximize',
  appClose: 'app:close',
} as const;

export type SupportedLanguage = keyof typeof SUPPORTED_LANGUAGES;
export type IgnoredDirectory = typeof IGNORED_DIRECTORIES[number];
export type IPCChannel = typeof IPC_CHANNELS[keyof typeof IPC_CHANNELS];
