# AgenticAI - Comprehensive Evaluation & Roadmap

**Document Version:** 1.0  
**Date:** May 31, 2026  
**Target:** Make AgenticAI competitive with Cursor IDE

---

## Executive Summary

AgenticAI is a promising Electron + React + TypeScript desktop IDE with solid foundational UI. Currently at **~30%** of Cursor's feature set. This roadmap outlines a 3-phase plan to reach **~85%** feature parity, focusing on real AI integration, code intelligence, and essential IDE features.

---

## 1. Current State Analysis

### 1.1 What's Working Well

| Feature | Status | Notes |
|---------|--------|-------|
| **Electron Setup** | ✅ Good | Proper main/preload/renderer separation, contextIsolation enabled |
| **UI Layout** | ✅ Good | 4-panel layout (Sidebar, Editor, Tasks, Chat) with dark theme |
| **File Tree** | ✅ Good | Recursive directory reading, sorting, expand/collapse |
| **Monaco Editor** | ✅ Good | Syntax highlighting, tabs, dirty indicator, Ctrl+S save |
| **Task Management** | ✅ Good | CRUD operations, status filtering, priority colors |
| **Chat Panel UI** | ✅ Good | Message history, loading states, welcome screen |
| **IPC System** | ✅ Good | Proper fs operations, dialog integration |
| **Zustand Store** | ✅ Good | Clean state management with proper types |
| **CSS Styling** | ✅ Good | CSS variables, VS Code-like dark theme |

### 1.2 What's Missing or Broken

| Issue | Severity | Description |
|-------|----------|-------------|
| **Mock AI Only** | 🔴 Critical | ChatPanel uses hardcoded `generateAIResponse()` - no real LLM |
| **No Persistence** | 🔴 Critical | App state lost on reload (workspace, files, tasks) |
| **toggleFolder Bug** | 🟡 Medium | `toggleFolder` doesn't properly update `isOpen` state recursively |
| **No Steering Parser** | 🔴 Critical | `steeringContext` is empty - not reading AGENTS.md, CLAUDE.md, etc. |
| **No Terminal** | 🟠 High | Cursor's integrated terminal (xterm.js) missing |
| **No Git Integration** | 🟠 High | No diff view, file history, branch switching |
| **No Search** | 🟠 High | No global search (ripgrep integration) |
| **No Command Palette** | 🟠 High | Ctrl+Shift+P command palette missing |
| **No Code Review** | 🟠 High | Mock responses, no AST parsing |
| **No Auto-fix** | 🟠 High | Cannot apply AI-suggested changes automatically |
| **No Extensions** | 🟡 Medium | No plugin/extension system |
| **No Terminal IPC** | 🟡 Medium | No way to send terminal commands from UI |
| **Incomplete File Ops** | 🟡 Medium | No rename, delete in context menu |
| **No Settings** | 🟡 Medium | No preferences panel, API key config |
| **Performance Issues** | 🟡 Medium | Large directories may block UI |

### 1.3 Bug Detail: toggleFolder

```typescript
// Current: toggleFolderInTree only toggles the exact path match
// Missing: Recursive children update when parent is opened
function toggleFolderInTree(files: FileNode[], path: string): FileNode[] {
  return files.map(node => {
    if (node.path === path) {
      return { ...node, isOpen: !node.isOpen }; // Only toggles this node
    }
    if (node.children) {
      return { ...node, children: toggleFolderInTree(node.children, path) };
    }
    return node;
  });
}
```

**Fix needed:** When folder is opened for first time, children must be loaded and rendered.

---

## 2. Scoring Matrix (0-100%)

### Current Score: 30/100

| Category | Score | Cursor Parity | Key Gaps |
|----------|-------|---------------|----------|
| **UI & Layout** | 75% | 85% | No command palette, no activity bar, no status bar |
| **File System & Editor** | 55% | 90% | No diff view, no git decorations, no rename in tree |
| **Task/Spec Management** | 60% | 70% | Spec parsing incomplete, no AI task breakdown |
| **AI Chat & Code Review** | 10% | 100% | Mock only, no AST, no real API |
| **Extensibility & Integration** | 5% | 80% | No terminal, no git, no search, no extensions |

### Detailed Breakdown

```
UI & Layout (75/100)
├── ✅ Dark theme                     [15/15] Complete
├── ✅ 4-panel layout                 [15/15] Complete
├── ✅ Monaco Editor                  [15/15] Complete
├── ✅ File tree with icons           [12/15] Missing file type icons
├── 🟡 Keyboard shortcuts             [8/15] Only Ctrl+S works
├── 🟡 Responsive panels              [5/10] No resize, no collapse
└── 🟠 Command palette                [5/15] Not implemented

File System & Editor (55/100)
├── ✅ Read/write files               [15/15] Complete
├── ✅ Directory navigation           [12/15] toggleFolder bug
├── ✅ Syntax highlighting            [12/15] Basic languages only
├── 🟡 Multi-tab editing             [8/15] No split view
├── 🟠 Git decorations                [0/15] Not implemented
└── 🟠 Diff view                      [0/15] Not implemented

Task/Spec Management (60/100)
├── ✅ Task CRUD                      [15/15] Complete
├── ✅ Status filtering               [12/15] Complete
├── 🟡 Spec markdown display          [10/15] Basic rendering
├── 🟡 Task priority                  [8/15] Visual only
├── 🟠 AI task breakdown              [0/15] Not implemented
└── 🟠 Task dependencies             [0/15] Not implemented

AI Chat & Code Review (10/100)
├── ✅ Message UI                     [10/15] Complete
├── 🔴 Real LLM integration           [0/20] Mock only
├── 🔴 Steering file parsing          [0/20] Not implemented
├── 🟠 AST-based code review           [0/20] Not implemented
├── 🟠 Auto-fix capability             [0/15] Not implemented
└── 🟠 Code suggestions inline        [0/15] Not implemented

Extensibility & Integration (5/100)
├── 🔴 Terminal (xterm.js)            [0/20] Not implemented
├── 🔴 Git integration                 [0/20] Not implemented
├── 🔴 Search (ripgrep)               [0/20] Not implemented
├── 🟡 Extensions API                  [0/15] Not implemented
└── 🟡 Settings/preferences           [0/15] Not implemented
```

---

## 3. Three-Phase Roadmap

### Phase 1: MVP - Real AI + Persistence (Target: 50%)

**Duration:** 2-3 weeks  
**Goal:** Replace mock AI with real LLM, add persistence, fix critical bugs

#### Files to Create

| File | Purpose | Priority |
|------|---------|----------|
| `src/main-process/aiService.ts` | Real OpenAI/Claude API integration | 🔴 Critical |
| `src/main-process/steeringParser.ts` | Parse AGENTS.md, CLAUDE.md, etc. | 🔴 Critical |
| `src/main-process/storage.ts` | electron-store persistence | 🔴 Critical |
| `src/main-process/steeringParser.ts` | Steering files parser | 🔴 Critical |
| `src/shared/constants.ts` | API endpoints, config | 🟡 Medium |
| `src/renderer/hooks/useAI.ts` | AI service hook | 🟡 Medium |

#### Files to Modify

| File | Change | Priority |
|------|--------|----------|
| `electron/main.js` | Add IPC handlers for AI, storage | 🔴 Critical |
| `electron/preload.js` | Expose AI & storage APIs | 🔴 Critical |
| `src/renderer/store/useAppStore.ts` | Add persistence middleware | 🔴 Critical |
| `src/renderer/components/Sidebar.tsx` | Fix toggleFolder bug | 🟡 Medium |
| `src/renderer/components/ChatPanel.tsx` | Connect to real AI service | 🔴 Critical |

#### npm Packages for Phase 1

```json
{
  "dependencies": {
    "openai": "^4.20.0",
    "@anthropic-ai/sdk": "^0.10.0",
    "electron-store": "^8.1.0"
  }
}
```

#### Code Samples

See Section 4 below for complete implementation examples.

---

### Phase 2: Code Review + Auto-fix (Target: 70%)

**Duration:** 3-4 weeks  
**Goal:** AST parsing, AI-powered code review, automated fixes

#### Files to Create

| File | Purpose | Priority |
|------|---------|----------|
| `src/main-process/codeAnalyzer.ts` | Babel/TS AST parsing | 🟠 High |
| `src/main-process/detectors/` | Security, quality, style detectors | 🟠 High |
| `src/main-process/fixEngine.ts` | Apply AI-suggested fixes | 🟠 High |
| `src/main-process/commandPalette.ts` | Ctrl+Shift+P command palette | 🟠 High |
| `src/renderer/components/CommandPalette.tsx` | Command palette UI | 🟠 High |
| `src/renderer/components/CodeReviewPanel.tsx` | Review results display | 🟠 High |
| `src/main-process/streaming.ts` | Server-Sent Events for streaming | 🟠 High |

#### Files to Modify

| File | Change | Priority |
|------|--------|----------|
| `electron/main.js` | Add code analysis IPC handlers | 🟠 High |
| `src/renderer/components/Editor.tsx` | Add inline decorations, quick fixes | 🟠 High |
| `src/renderer/components/ChatPanel.tsx` | Add code selection context | 🟠 High |

#### npm Packages for Phase 2

```json
{
  "dependencies": {
    "@babel/parser": "^7.23.0",
    "@babel/traverse": "^7.23.0",
    "@babel/generator": "^7.23.0",
    "@babel/types": "^7.23.0",
    "@typescript-eslint/parser": "^6.15.0",
    "@typescript-eslint/visitor-keys": "^6.15.0",
    "cmdk": "^0.2.0"
  }
}
```

#### AI Detector Examples

```typescript
// Security: SQL Injection detection
function detectSQLInjection(code: string): Issue[] {
  const patterns = [
    /\bSELECT\b.*\+\s*['"`]/i,
    /\bINSERT\b.*\+\s*['"`]/i,
    /\bUPDATE\b.*\+\s*['"`]/i,
    /`\$\{.*\}`/g,  // Template literal with user input
  ];
  // Return detected issues with line numbers
}

// Quality: Function length check
function detectLongFunctions(ast: AST): Issue[] {
  return ast.body
    .filter(node => node.type === 'FunctionDeclaration')
    .filter(fn => fn.body.body.length > MAX_FUNCTION_LINES)
    .map(fn => ({
      type: 'QUAL001',
      severity: 'warning',
      message: `Function ${fn.id?.name} has ${fn.body.body.length} lines (max: ${MAX_FUNCTION_LINES})`,
      line: fn.loc.start.line
    }));
}
```

---

### Phase 3: Near-Cursor Parity (Target: 85%)

**Duration:** 4-6 weeks  
**Goal:** Terminal, Git, Search, Extensions, Performance

#### Files to Create

| File | Purpose | Priority |
|------|---------|----------|
| `src/main-process/terminal.ts` | node-pty integration | 🟠 High |
| `src/renderer/components/Terminal.tsx` | xterm.js terminal panel | 🟠 High |
| `src/main-process/gitService.ts` | simple-git integration | 🟠 High |
| `src/renderer/components/GitPanel.tsx` | Git status, diff, history | 🟠 High |
| `src/main-process/searchService.ts` | ripgrep integration | 🟠 High |
| `src/renderer/components/SearchPanel.tsx` | Global search UI | 🟠 High |
| `src/main-process/extensionHost.ts` | Extension API host | 🟡 Medium |
| `src/main-process/pluginManager.ts` | Extension loader | 🟡 Medium |
| `src/main-process/settingsManager.ts` | Settings persistence | 🟡 Medium |
| `src/renderer/components/SettingsPanel.tsx` | Preferences UI | 🟡 Medium |

#### Files to Modify

| File | Change | Priority |
|------|--------|----------|
| `electron/main.js` | Terminal process management | 🟠 High |
| `src/renderer/App.tsx` | Add terminal panel, settings | 🟠 High |
| `src/renderer/store/useAppStore.ts` | Terminal state management | 🟡 Medium |

#### npm Packages for Phase 3

```json
{
  "dependencies": {
    "node-pty": "^1.0.0",
    "xterm": "^5.3.0",
    "xterm-addon-fit": "^0.8.0",
    "xterm-addon-web-links": "^0.9.0",
    "simple-git": "^3.21.0",
    "ripgrep": "^0.4.0"
  },
  "devDependencies": {
    "electron-rebuild": "^3.2.9"
  }
}
```

#### Terminal Integration Architecture

```typescript
// Main process: node-pty spawn
import * as pty from 'node-pty';

const terminals = new Map<string, pty.IPty>();

ipcMain.handle('terminal:create', (_, id: string, shell: string) => {
  const ptyProcess = pty.spawn(shell, [], {
    name: 'xterm-256color',
    cols: 80,
    rows: 30,
    cwd: process.env.HOME,
    env: process.env as { [key: string]: string }
  });
  
  ptyProcess.onData((data) => {
    mainWindow.webContents.send(`terminal:data:${id}`, data);
  });
  
  terminals.set(id, ptyProcess);
  return true;
});

ipcMain.handle('terminal:write', (_, id: string, data: string) => {
  terminals.get(id)?.write(data);
});

ipcMain.handle('terminal:resize', (_, id: string, cols: number, rows: number) => {
  terminals.get(id)?.resize(cols, rows);
});

ipcMain.handle('terminal:kill', (_, id: string) => {
  terminals.get(id)?.kill();
  terminals.delete(id);
});
```

---

## 4. Phase 1 Code Examples

### 4.1 AI Service (`src/main-process/aiService.ts`)

```typescript
import { OpenAI } from 'openai';
import { Anthropic } from '@anthropic-ai/sdk';

export type AIProvider = 'openai' | 'anthropic';

export interface AIConfig {
  provider: AIProvider;
  apiKey: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

export interface AIResponse {
  content: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model: string;
}

export class AIService {
  private openai: OpenAI | null = null;
  private anthropic: Anthropic | null = null;
  private config: AIConfig | null = null;

  initialize(config: AIConfig): void {
    this.config = config;
    
    if (config.provider === 'openai') {
      this.openai = new OpenAI({ apiKey: config.apiKey });
    } else if (config.provider === 'anthropic') {
      this.anthropic = new Anthropic({ apiKey: config.apiKey });
    }
  }

  isInitialized(): boolean {
    return this.config !== null;
  }

  getConfig(): AIConfig | null {
    return this.config;
  }

  async chat(
    messages: ChatMessage[],
    systemPrompt?: string,
    onChunk?: (chunk: string) => void
  ): Promise<AIResponse> {
    if (!this.config) {
      throw new Error('AI service not initialized. Call initialize() first.');
    }

    const allMessages: ChatMessage[] = [];
    
    if (systemPrompt) {
      allMessages.push({ role: 'system', content: systemPrompt });
    }
    allMessages.push(...messages);

    if (this.config.provider === 'openai' && this.openai) {
      return this.chatOpenAI(allMessages, onChunk);
    } else if (this.config.provider === 'anthropic' && this.anthropic) {
      return this.chatAnthropic(allMessages, onChunk);
    }

    throw new Error(`Unknown provider: ${this.config.provider}`);
  }

  private async chatOpenAI(
    messages: ChatMessage[],
    onChunk?: (chunk: string) => void
  ): Promise<AIResponse> {
    const stream = await this.openai!.chat.completions.create({
      model: this.config!.model || 'gpt-4',
      messages: messages as any,
      temperature: this.config!.temperature ?? 0.7,
      max_tokens: this.config!.maxTokens ?? 4096,
      stream: true,
    });

    let fullContent = '';
    let usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content || '';
      if (delta) {
        fullContent += delta;
        onChunk?.(delta);
      }
      if (chunk.usage) {
        usage = {
          promptTokens: chunk.usage.prompt_tokens || 0,
          completionTokens: chunk.usage.completion_tokens || 0,
          totalTokens: chunk.usage.total_tokens || 0,
        };
      }
    }

    return { content: fullContent, usage, model: this.config!.model || 'gpt-4' };
  }

  private async chatAnthropic(
    messages: ChatMessage[],
    onChunk?: (chunk: string) => void
  ): Promise<AIResponse> {
    const systemMessage = messages.find(m => m.role === 'system');
    const userMessages = messages.filter(m => m.role !== 'system');

    const stream = await this.anthropic!.messages.stream({
      model: this.config!.model || 'claude-3-5-sonnet-20241022',
      max_tokens: this.config!.maxTokens ?? 4096,
      temperature: this.config!.temperature ?? 0.7,
      system: systemMessage?.content,
      messages: userMessages as any,
    });

    let fullContent = '';
    
    for await (const chunk of stream) {
      if (chunk.type === 'content_block_delta' && chunk.type === 'content_block_delta') {
        if ('text' in chunk.delta) {
          fullContent += chunk.delta.text;
          onChunk?.(chunk.delta.text);
        }
      }
    }

    const usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    return { content: fullContent, usage, model: this.config!.model || 'claude-3-5-sonnet' };
  }

  async codeReview(code: string, language: string, context?: string): Promise<string> {
    const systemPrompt = `You are an expert code reviewer. Analyze the provided code and return a JSON review with:
{
  "issues": [
    {
      "type": "SEC|QUAL|PERF|STYLE",
      "severity": "error|warning|info",
      "line": number,
      "message": "description",
      "suggestion": "optional fix"
    }
  ],
  "summary": "overall assessment"
}

Languages: ${language}
Context: ${context || 'No additional context'}`;

    const response = await this.chat([
      { role: 'user', content: `Review this code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], systemPrompt);

    return response.content;
  }

  async generateCode(spec: string, existingCode?: string): Promise<string> {
    const systemPrompt = `You are an expert software engineer. Generate code based on the specification. Return ONLY the code with minimal explanation.`;

    const userMessage = existingCode
      ? `Modify this existing code:\n\n\`\`\`\n${existingCode}\n\`\`\`\n\nTo meet this specification:\n\n${spec}`
      : `Generate code for this specification:\n\n${spec}`;

    const response = await this.chat([{ role: 'user', content: userMessage }], systemPrompt);
    return response.content;
  }

  async explainCode(code: string, language: string): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Explain this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], 'You are a helpful code assistant that explains code clearly.');
    return response.content;
  }
}

export const aiService = new AIService();
```

### 4.2 Steering Parser (`src/main-process/steeringParser.ts`)

```typescript
import * as fs from 'fs';
import * as path from 'path';

export interface SteeringFile {
  name: string;
  path: string;
  content: string;
  loaded: boolean;
}

export interface SteeringContext {
  agents?: string;
  claude?: string;
  product?: string;
  tech?: string;
  structure?: string;
  requirements?: string;
  [key: string]: string | undefined;
}

const STEERING_FILES = [
  { name: 'agents', file: 'AGENTS.md' },
  { name: 'claude', file: 'CLAUDE.md' },
  { name: 'product', file: 'product.md' },
  { name: 'tech', file: 'tech.md' },
  { name: 'structure', file: 'structure.md' },
  { name: 'requirements', file: 'requirements.md' },
];

const ADDITIONAL_STEERING_PATTERNS = [
  '.cursor/rules/*.mdc',
  '.ai_support/**/*.md',
  '.kiro/**/*.md',
];

export class SteeringParser {
  private context: SteeringContext = {};
  private workspacePath: string | null = null;
  private watchers: Map<string, fs.FSWatcher> = new Map();

  setWorkspace(workspacePath: string): void {
    this.workspacePath = workspacePath;
    this.stopWatching();
  }

  async loadSteeringFiles(): Promise<SteeringContext> {
    if (!this.workspacePath) {
      console.warn('No workspace path set');
      return {};
    }

    this.context = {};

    for (const steering of STEERING_FILES) {
      const filePath = path.join(this.workspacePath, steering.file);
      try {
        const content = await fs.promises.readFile(filePath, 'utf-8');
        this.context[steering.name] = content;
      } catch {
        this.context[steering.name] = undefined;
      }
    }

    // Load additional steering files from patterns
    await this.loadAdditionalSteeringFiles();

    return this.context;
  }

  private async loadAdditionalSteeringFiles(): Promise<void> {
    if (!this.workspacePath) return;

    // Load .cursor/rules/*.mdc files
    const cursorRulesPath = path.join(this.workspacePath, '.cursor', 'rules');
    try {
      const ruleFiles = await fs.promises.readdir(cursorRulesPath);
      const mdcFiles = ruleFiles.filter(f => f.endsWith('.mdc'));
      
      for (const file of mdcFiles) {
        const filePath = path.join(cursorRulesPath, file);
        try {
          const content = await fs.promises.readFile(filePath, 'utf-8');
          const key = `cursor_rules_${file.replace('.mdc', '')}`;
          this.context[key] = content;
        } catch {
          // Ignore errors
        }
      }
    } catch {
      // Directory doesn't exist
    }

    // Load workspace-specific files
    const workspaceFiles = ['SPEC.md', 'README.md', 'CONTRIBUTING.md'];
    for (const file of workspaceFiles) {
      const filePath = path.join(this.workspacePath, file);
      try {
        const content = await fs.promises.readFile(filePath, 'utf-8');
        const key = file.toLowerCase().replace('.md', '');
        this.context[key] = content;
      } catch {
        // Ignore errors
      }
    }
  }

  getContext(): SteeringContext {
    return { ...this.context };
  }

  getSystemPrompt(): string {
    const parts: string[] = [];

    if (this.context.agents) {
      parts.push('## AGENTS.md\n' + this.context.agents);
    }
    if (this.context.claude) {
      parts.push('## CLAUDE.md\n' + this.context.claude);
    }
    if (this.context.product) {
      parts.push('## Product Specification\n' + this.context.product);
    }
    if (this.context.tech) {
      parts.push('## Technical Specification\n' + this.context.tech);
    }
    if (this.context.structure) {
      parts.push('## Project Structure\n' + this.context.structure);
    }
    if (this.context.requirements) {
      parts.push('## Requirements\n' + this.context.requirements);
    }

    // Add cursor rules
    for (const [key, value] of Object.entries(this.context)) {
      if (key.startsWith('cursor_rules_') && value) {
        parts.push(`## ${key}\n${value}`);
      }
    }

    if (parts.length === 0) {
      return 'You are a helpful AI coding assistant.';
    }

    return parts.join('\n\n---\n\n');
  }

  getRelevantContext(query: string): string {
    // Simple keyword-based context selection
    const queryLower = query.toLowerCase();
    const relevant: string[] = [];

    // Always include agents and claude
    if (this.context.agents) relevant.push(this.context.agents);
    if (this.context.claude) relevant.push(this.context.claude);

    // Add relevant context based on keywords
    const keywords: Record<string, string[]> = {
      security: ['product', 'tech'],
      architecture: ['structure', 'tech'],
      database: ['tech', 'structure'],
      api: ['tech', 'structure'],
      ui: ['product', 'tech'],
      test: ['requirements', 'tech'],
      deploy: ['product', 'tech'],
    };

    for (const [keyword, contexts] of Object.entries(keywords)) {
      if (queryLower.includes(keyword)) {
        for (const ctx of contexts) {
          if (this.context[ctx] && !relevant.includes(this.context[ctx])) {
            relevant.push(this.context[ctx]);
          }
        }
      }
    }

    return relevant.join('\n\n---\n\n');
  }

  watchForChanges(callback: (context: SteeringContext) => void): void {
    if (!this.workspacePath) return;

    this.stopWatching();

    for (const steering of STEERING_FILES) {
      const filePath = path.join(this.workspacePath, steering.file);
      try {
        const watcher = fs.watch(filePath, async () => {
          await this.loadSteeringFiles();
          callback(this.context);
        });
        this.watchers.set(steering.file, watcher);
      } catch {
        // File doesn't exist
      }
    }
  }

  stopWatching(): void {
    for (const watcher of this.watchers.values()) {
      watcher.close();
    }
    this.watchers.clear();
  }
}

export const steeringParser = new SteeringParser();
```

### 4.3 Storage Service (`src/main-process/storage.ts`)

```typescript
import Store from 'electron-store';
import * as fs from 'fs';
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
  activePanel: 'files' | 'search' | 'git' | 'extensions';
}

export interface StoredOpenFiles {
  files: string[];
  activeFile: string | null;
}

export interface StoredTasks {
  tasks: StoredTask[];
  specs: StoredSpec[];
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

interface StoreSchema {
  settings: StoredSettings;
  recentWorkspaces: StoredWorkspace[];
  currentWorkspace: StoredWorkspace | null;
  uiState: StoredUIState;
  openFiles: StoredOpenFiles;
  tasks: StoredTasks;
  chat: StoredChat;
}

const defaultSettings: StoredSettings = {
  aiProvider: 'openai',
  aiApiKey: undefined,
  aiModel: 'gpt-4',
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
};

const defaultOpenFiles: StoredOpenFiles = {
  files: [],
  activeFile: null,
};

const defaultTasks: StoredTasks = {
  tasks: [],
  specs: [],
};

const defaultChat: StoredChat = {
  messages: [],
  conversationId: null,
};

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
        tasks: defaultTasks,
        chat: defaultChat,
      },
      schema: {
        settings: {
          type: 'object',
          properties: {
            aiProvider: { type: 'string', enum: ['openai', 'anthropic'] },
            aiApiKey: { type: 'string' },
            aiModel: { type: 'string' },
            theme: { type: 'string', enum: ['dark', 'light'] },
            fontSize: { type: 'number', minimum: 8, maximum: 24 },
            fontFamily: { type: 'string' },
            tabSize: { type: 'number', minimum: 1, maximum: 8 },
            autoSave: { type: 'boolean' },
            autoSaveDelay: { type: 'number' },
          },
        },
        recentWorkspaces: {
          type: 'array',
          items: {
            type: 'object',
            properties: {
              path: { type: 'string' },
              name: { type: 'string' },
              lastOpened: { type: 'string' },
            },
          },
        },
      },
    });
  }

  // Settings
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
    this.updateSettings({ aiApiKey: key });
  }

  // Workspace
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

  private addToRecentWorkspaces(workspace: StoredWorkspace): void {
    const recent = this.getRecentWorkspaces();
    const filtered = recent.filter(w => w.path !== workspace.path);
    const updated = [workspace, ...filtered].slice(0, 10); // Keep last 10
    this.store.set('recentWorkspaces', updated);
  }

  // UI State
  getUIState(): StoredUIState {
    return this.store.get('uiState');
  }

  updateUIState(updates: Partial<StoredUIState>): void {
    const current = this.getUIState();
    this.store.set('uiState', { ...current, ...updates });
  }

  // Open Files
  getOpenFiles(): StoredOpenFiles {
    return this.store.get('openFiles');
  }

  updateOpenFiles(updates: Partial<StoredOpenFiles>): void {
    const current = this.getOpenFiles();
    this.store.set('openFiles', { ...current, ...updates });
  }

  // Tasks
  getTasks(): StoredTasks {
    return this.store.get('tasks');
  }

  saveTasks(tasks: StoredTask[]): void {
    const current = this.getTasks();
    this.store.set('tasks', { ...current, tasks });
  }

  saveSpecs(specs: StoredSpec[]): void {
    const current = this.getTasks();
    this.store.set('tasks', { ...current, specs });
  }

  addTask(task: StoredTask): void {
    const tasks = this.getTasks().tasks;
    tasks.push(task);
    this.saveTasks(tasks);
  }

  updateTask(id: string, updates: Partial<StoredTask>): void {
    const tasks = this.getTasks().tasks;
    const index = tasks.findIndex(t => t.id === id);
    if (index !== -1) {
      tasks[index] = { ...tasks[index], ...updates };
      this.saveTasks(tasks);
    }
  }

  deleteTask(id: string): void {
    const tasks = this.getTasks().tasks.filter(t => t.id !== id);
    this.saveTasks(tasks);
  }

  // Chat
  getChat(): StoredChat {
    return this.store.get('chat');
  }

  saveChat(messages: ChatMessage[]): void {
    const current = this.getChat();
    this.store.set('chat', { ...current, messages });
  }

  addChatMessage(message: ChatMessage): void {
    const chat = this.getChat();
    chat.messages.push(message);
    this.store.set('chat', chat);
  }

  clearChat(): void {
    this.store.set('chat', { messages: [], conversationId: null });
  }

  // Persistence helpers
  exportData(): Record<string, unknown> {
    return this.store.store;
  }

  importData(data: Record<string, unknown>): void {
    for (const [key, value] of Object.entries(data)) {
      this.store.set(key as any, value as any);
    }
  }

  clearAll(): void {
    this.store.clear();
  }

  getStorePath(): string {
    return this.store.path;
  }
}

export const storage = new StorageService();
```

---

## 5. Risk Assessment

### Phase 1 Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| API key security | High | High | Encrypt keys, never log them |
| Rate limiting | Medium | Medium | Implement retry with backoff |
| Steering file complexity | Medium | Low | Graceful degradation |
| Context window overflow | Medium | High | Truncate old messages |

### Phase 2 Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| AST parsing edge cases | High | Medium | Comprehensive test suite |
| Fix application breaking code | Medium | High | Always create backup, allow undo |
| Performance with large files | Medium | Medium | Web Workers for analysis |

### Phase 3 Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Terminal PTY issues | High | Medium | Fallback to WebContainers |
| Git conflicts | Medium | Medium | Clear conflict markers UI |
| Extension security | Medium | High | Sandboxed execution |

---

## 6. Projected Score After Roadmap

| Phase | Target Score | Key Achievements |
|-------|-------------|------------------|
| **Phase 1** | 50% | Real AI, persistence, bug fixes |
| **Phase 2** | 70% | Code review, auto-fix, command palette |
| **Phase 3** | 85% | Terminal, Git, Search, Extensions |

### Final Score Breakdown (Target: 85/100)

```
UI & Layout: 90/100
├── + Command palette (Ctrl+Shift+P)
├── + Resizable panels
└── + Activity bar + Status bar

File System: 85/100
├── + Git decorations
├── + Diff view
└── + Better file icons

Task/Spec: 80/100
├── + AI task breakdown
└── + Task dependencies

AI Chat: 75/100
├── + Real LLM integration
├── + Code selection context
├── + Streaming responses
└── - Still not full code completion

Extensibility: 75/100
├── + Terminal integration
├── + Git panel
├── + Global search
└── + Extension API (basic)
```

---

## 7. Implementation Priority Order

### Week 1-2: Foundation
1. ✅ Fix `toggleFolder` bug in Sidebar
2. ✅ Integrate `electron-store` for persistence
3. ✅ Create `aiService.ts` with OpenAI/Anthropic support
4. ✅ Create `steeringParser.ts`
5. ✅ Connect ChatPanel to real AI service

### Week 3-4: Polish
1. ✅ Add settings panel for API key configuration
2. ✅ Persist workspace, files, tasks across sessions
3. ✅ Load steering context on workspace open
4. ✅ Error handling and retry logic

### Week 5-8: Phase 2
1. ✅ Babel AST parsing setup
2. ✅ Security detector implementation
3. ✅ Quality detector implementation
4. ✅ Command palette UI
5. ✅ AI-powered code suggestions

### Week 9-14: Phase 3
1. ✅ Terminal integration (node-pty + xterm.js)
2. ✅ Git integration (simple-git)
3. ✅ Search integration (ripgrep)
4. ✅ Extension system foundation
5. ✅ Settings/preferences panel

---

## 8. Appendix: File Structure After Implementation

```
AgenticAI/
├── package.json
├── electron/
│   ├── main.js          # Extended with AI, storage, terminal IPC
│   ├── preload.js       # Extended API surface
│   └── ipc/
│       ├── ai.ts
│       ├── storage.ts
│       ├── terminal.ts
│       ├── git.ts
│       └── search.ts
├── src/
│   ├── main-process/
│   │   ├── aiService.ts         # NEW
│   │   ├── steeringParser.ts    # NEW
│   │   ├── storage.ts          # NEW
│   │   ├── codeAnalyzer.ts      # NEW (Phase 2)
│   │   ├── commandPalette.ts    # NEW (Phase 2)
│   │   ├── terminal.ts          # NEW (Phase 3)
│   │   ├── gitService.ts       # NEW (Phase 3)
│   │   └── searchService.ts     # NEW (Phase 3)
│   ├── renderer/
│   │   ├── components/
│   │   │   ├── Sidebar.tsx      # Fixed toggleFolder
│   │   │   ├── Editor.tsx      # Enhanced
│   │   │   ├── ChatPanel.tsx   # Connected to AI
│   │   │   ├── TaskPanel.tsx   # Enhanced
│   │   │   ├── CommandPalette.tsx  # NEW (Phase 2)
│   │   │   ├── Terminal.tsx    # NEW (Phase 3)
│   │   │   ├── GitPanel.tsx    # NEW (Phase 3)
│   │   │   ├── SearchPanel.tsx # NEW (Phase 3)
│   │   │   └── Settings.tsx    # NEW (Phase 3)
│   │   ├── hooks/
│   │   │   ├── useAI.ts        # NEW
│   │   │   ├── useTerminal.ts  # NEW (Phase 3)
│   │   │   └── useGit.ts       # NEW (Phase 3)
│   │   └── store/
│   │       └── useAppStore.ts  # Enhanced with persistence
│   └── shared/
│       ├── types.ts
│       └── constants.ts         # NEW
└── dist/
```

---

*Document generated: May 31, 2026*  
*Maintainer: AgenticAI Team*
