import * as fs from 'fs';
import * as path from 'path';

export interface SteeringFile {
  name: string;
  file: string;
  content?: string;
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

const STEERING_FILES: SteeringFile[] = [
  { name: 'agents', file: 'AGENTS.md', loaded: false },
  { name: 'claude', file: 'CLAUDE.md', loaded: false },
  { name: 'product', file: 'product.md', loaded: false },
  { name: 'tech', file: 'tech.md', loaded: false },
  { name: 'structure', file: 'structure.md', loaded: false },
  { name: 'requirements', file: 'requirements.md', loaded: false },
];

const CURSOR_RULES_DIR = '.cursor/rules';
const AI_SUPPORT_DIR = '.ai_support';

export class SteeringParser {
  private context: SteeringContext = {};
  private workspacePath: string | null = null;
  private watchers: Map<string, fs.FSWatcher> = new Map();

  setWorkspace(workspacePath: string): void {
    this.workspacePath = workspacePath;
    this.stopWatching();
  }

  getWorkspace(): string | null {
    return this.workspacePath;
  }

  async loadSteeringFiles(): Promise<SteeringContext> {
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

    await this.loadAdditionalSteeringFiles();

    return this.context;
  }

  private async loadAdditionalSteeringFiles(): Promise<void> {
    if (!this.workspacePath) return;

    await this.loadCursorRules();
    await this.loadAiSupportFiles();
    await this.loadWorkspaceFiles();
  }

  private async loadCursorRules(): Promise<void> {
    if (!this.workspacePath) return;
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

  private async loadAiSupportFiles(): Promise<void> {
    if (!this.workspacePath) return;
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

  private async loadWorkspaceFiles(): Promise<void> {
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

  getRelevantContext(query: string): string {
    const queryLower = query.toLowerCase();
    const relevant: string[] = [];

    if (this.context.agents) relevant.push(this.context.agents);
    if (this.context.claude) relevant.push(this.context.claude);

    const keywords: Record<string, (keyof SteeringContext)[]> = {
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

  getFileContent(fileName: string): string | undefined {
    const steering = STEERING_FILES.find(s => s.file === fileName);
    return steering?.content;
  }

  getLoadedFiles(): SteeringFile[] {
    return STEERING_FILES.filter(s => s.loaded);
  }

  watchForChanges(callback: (context: SteeringContext, changedFile: string) => void): void {
    if (!this.workspacePath) return;

    this.stopWatching();

    for (const steering of STEERING_FILES) {
      const filePath = path.join(this.workspacePath, steering.file);
      this.watchFile(filePath, steering.file, callback);
    }

    const cursorRulesPath = path.join(this.workspacePath, CURSOR_RULES_DIR);
    this.watchDirectory(cursorRulesPath, '.mdc', callback);

    const aiSupportPath = path.join(this.workspacePath, AI_SUPPORT_DIR);
    this.watchDirectory(aiSupportPath, '.md', callback);
  }

  private watchFile(
    filePath: string,
    fileName: string,
    callback: (context: SteeringContext, changedFile: string) => void
  ): void {
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

  private watchDirectory(
    dirPath: string,
    extension: string,
    callback: (context: SteeringContext, changedFile: string) => void
  ): void {
    try {
      if (fs.existsSync(dirPath)) {
        const watcher = fs.watch(dirPath, async (_eventType, filename) => {
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

  stopWatching(): void {
    for (const watcher of this.watchers.values()) {
      watcher.close();
    }
    this.watchers.clear();
  }

  async parseMarkdown(markdown: string): Promise<{
    title?: string;
    sections: { heading: string; content: string }[];
    todos: { text: string; checked: boolean }[];
  }> {
    const lines = markdown.split('\n');
    const result = {
      title: '',
      sections: [] as { heading: string; content: string }[],
      todos: [] as { text: string; checked: boolean }[],
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

  extractTasksFromSpec(spec: string): Array<{
    title: string;
    description: string;
    priority: 'high' | 'medium' | 'low';
  }> {
    const parsed = this.parseMarkdownSync(spec);
    const tasks: Array<{ title: string; description: string; priority: 'high' | 'medium' | 'low' }> = [];

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

  private parseMarkdownSync(markdown: string): {
    title?: string;
    sections: { heading: string; content: string }[];
    todos: { text: string; checked: boolean }[];
  } {
    const lines = markdown.split('\n');
    const result = {
      title: undefined as string | undefined,
      sections: [] as { heading: string; content: string }[],
      todos: [] as { text: string; checked: boolean }[],
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

export const steeringParser = new SteeringParser();
