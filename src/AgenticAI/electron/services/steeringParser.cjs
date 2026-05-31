'use strict';

const fs = require('fs');
const path = require('path');

const STEERING_FILES = [
  { name: 'agents', file: 'AGENTS.md', loaded: false },
  { name: 'claude', file: 'CLAUDE.md', loaded: false },
  { name: 'product', file: 'product.md', loaded: false },
  { name: 'tech', file: 'tech.md', loaded: false },
  { name: 'structure', file: 'structure.md', loaded: false },
  { name: 'requirements', file: 'requirements.md', loaded: false },
];

const CURSOR_RULES_DIR = '.cursor/rules';
const AI_SUPPORT_DIR = '.ai_support';
const KIRO_DIR = '.kiro';

class SteeringParser {
  constructor() {
    this.context = {};
    this.workspacePath = null;
    this.watchers = new Map();
  }

  setWorkspace(workspacePath) {
    this.workspacePath = workspacePath;
    this._stopWatching();
  }

  getWorkspace() {
    return this.workspacePath;
  }

  async loadSteeringFiles() {
    if (!this.workspacePath) {
      console.warn('[SteeringParser] No workspace path set');
      return {};
    }

    this.context = {};

    for (const steering of STEERING_FILES) {
      const filePath = path.join(this.workspacePath, steering.file);
      try {
        const content = await fs.promises.readFile(filePath, 'utf-8');
        this.context[steering.name] = content;
        steering.loaded = true;
        steering.content = content;
      } catch {
        this.context[steering.name] = undefined;
        steering.loaded = false;
        steering.content = undefined;
      }
    }

    await this._loadAdditionalSteeringFiles();

    return this.context;
  }

  async _loadAdditionalSteeringFiles() {
    if (!this.workspacePath) return;

    await this._loadCursorRules();
    await this._loadAiSupportFiles();
    await this._loadWorkspaceFiles();
  }

  async _loadCursorRules() {
    const cursorRulesPath = path.join(this.workspacePath, CURSOR_RULES_DIR);
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
          // Ignore errors for individual files
        }
      }
    } catch {
      // Directory doesn't exist, skip
    }
  }

  async _loadAiSupportFiles() {
    const aiSupportPath = path.join(this.workspacePath, AI_SUPPORT_DIR);
    try {
      const files = await fs.promises.readdir(aiSupportPath);
      const mdFiles = files.filter(f => f.endsWith('.md'));

      for (const file of mdFiles) {
        const filePath = path.join(aiSupportPath, file);
        try {
          const content = await fs.promises.readFile(filePath, 'utf-8');
          const key = `ai_support_${file.replace('.md', '')}`;
          this.context[key] = content;
        } catch {
          // Ignore errors
        }
      }
    } catch {
      // Directory doesn't exist, skip
    }
  }

  async _loadWorkspaceFiles() {
    if (!this.workspacePath) return;

    const workspaceFiles = [
      'SPEC.md',
      'README.md',
      'CONTRIBUTING.md',
      'CHANGELOG.md',
    ];

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

  getContext() {
    return { ...this.context };
  }

  getSystemPrompt() {
    const parts = [];

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

    for (const [key, value] of Object.entries(this.context)) {
      if (key.startsWith('cursor_rules_') && value) {
        parts.push(`## Cursor Rule: ${key.replace('cursor_rules_', '')}\n${value}`);
      }
      if (key.startsWith('ai_support_') && value) {
        parts.push(`## AI Support: ${key.replace('ai_support_', '')}\n${value}`);
      }
    }

    if (parts.length === 0) {
      return 'You are a helpful AI coding assistant.';
    }

    return [
      'You are an expert AI coding assistant. Use the following context to guide your responses.',
      '',
      ...parts,
      '',
      '---',
      'End of steering context.',
    ].join('\n\n');
  }

  getRelevantContext(query) {
    const queryLower = query.toLowerCase();
    const relevant = [];

    if (this.context.agents) relevant.push(this.context.agents);
    if (this.context.claude) relevant.push(this.context.claude);

    const keywords = {
      security: ['product', 'tech'],
      architecture: ['structure', 'tech'],
      database: ['tech', 'structure'],
      api: ['tech', 'structure'],
      ui: ['product', 'tech'],
      test: ['requirements', 'tech'],
      deploy: ['product', 'tech'],
      build: ['tech', 'structure'],
      compile: ['tech', 'structure'],
      run: ['tech', 'requirements'],
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

    return relevant.length > 0 ? relevant.join('\n\n---\n\n') : '';
  }

  getFileContent(fileName) {
    const steering = STEERING_FILES.find(s => s.file === fileName);
    return steering?.content;
  }

  getLoadedFiles() {
    return STEERING_FILES.filter(s => s.loaded);
  }

  watchForChanges(callback) {
    if (!this.workspacePath) return;

    this._stopWatching();

    for (const steering of STEERING_FILES) {
      const filePath = path.join(this.workspacePath, steering.file);
      this._watchFile(filePath, steering.file, callback);
    }

    const cursorRulesPath = path.join(this.workspacePath, CURSOR_RULES_DIR);
    this._watchDirectory(cursorRulesPath, '.mdc', callback);

    const aiSupportPath = path.join(this.workspacePath, AI_SUPPORT_DIR);
    this._watchDirectory(aiSupportPath, '.md', callback);
  }

  _watchFile(filePath, fileName, callback) {
    try {
      if (fs.existsSync(filePath)) {
        const watcher = fs.watch(filePath, async () => {
          await this.loadSteeringFiles();
          callback(this.context, fileName);
        });
        this.watchers.set(fileName, watcher);
      }
    } catch {
      // File doesn't exist, skip
    }
  }

  _watchDirectory(dirPath, extension, callback) {
    try {
      if (fs.existsSync(dirPath)) {
        const watcher = fs.watch(dirPath, async (eventType, filename) => {
          if (filename && filename.endsWith(extension)) {
            await this.loadSteeringFiles();
            callback(this.context, filename);
          }
        });
        this.watchers.set(dirPath, watcher);
      }
    } catch {
      // Directory doesn't exist, skip
    }
  }

  _stopWatching() {
    for (const watcher of this.watchers.values()) {
      watcher.close();
    }
    this.watchers.clear();
  }

  parseMarkdown(markdown) {
    const lines = markdown.split('\n');
    const result = {
      title: '',
      sections: [],
      todos: [],
    };

    let currentSection = { heading: '', content: '' };

    for (const line of lines) {
      const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        if (currentSection.heading || currentSection.content) {
          result.sections.push(currentSection);
        }
        currentSection = { heading: headingMatch[2], content: '' };
        if (!result.title) {
          result.title = headingMatch[2];
        }
        continue;
      }

      const todoMatch = line.match(/^[-*]\s+\[([ x])\]\s+(.+)$/);
      if (todoMatch) {
        result.todos.push({
          text: todoMatch[2],
          checked: todoMatch[1] === 'x',
        });
        continue;
      }

      currentSection.content += line + '\n';
    }

    if (currentSection.heading || currentSection.content.trim()) {
      result.sections.push(currentSection);
    }

    return result;
  }

  extractTasksFromSpec(spec) {
    const parsed = this._parseMarkdownSync(spec);
    const tasks = [];

    for (const todo of parsed.todos) {
      const priority = todo.text.toLowerCase().includes('critical') || todo.text.toLowerCase().includes('important')
        ? 'high'
        : todo.text.toLowerCase().includes('low')
        ? 'low'
        : 'medium';

      tasks.push({
        title: todo.text.replace(/\[(critical|important|low)\]/gi, '').trim(),
        description: '',
        priority,
      });
    }

    for (const section of parsed.sections) {
      if (section.heading.toLowerCase().includes('task')) {
        const lines = section.content.split('\n').filter(l => l.trim());
        for (const line of lines) {
          if (line.trim().startsWith('-') || line.trim().startsWith('*')) {
            const text = line.trim().replace(/^[-*]\s*/, '');
            if (!tasks.find(t => t.title === text)) {
              tasks.push({ title: text, description: '', priority: 'medium' });
            }
          }
        }
      }
    }

    return tasks;
  }

  _parseMarkdownSync(markdown) {
    const lines = markdown.split('\n');
    const result = {
      title: undefined,
      sections: [],
      todos: [],
    };

    let currentSection = { heading: '', content: '' };

    for (const line of lines) {
      const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        if (currentSection.heading || currentSection.content) {
          result.sections.push(currentSection);
        }
        currentSection = { heading: headingMatch[2], content: '' };
        if (!result.title) {
          result.title = headingMatch[2];
        }
        continue;
      }

      const todoMatch = line.match(/^[-*]\s+\[([ x])\]\s+(.+)$/);
      if (todoMatch) {
        result.todos.push({
          text: todoMatch[2],
          checked: todoMatch[1] === 'x',
        });
        continue;
      }

      currentSection.content += line + '\n';
    }

    if (currentSection.heading || currentSection.content.trim()) {
      result.sections.push(currentSection);
    }

    return result;
  }
}

module.exports = { steeringParser: new SteeringParser(), SteeringParser };
