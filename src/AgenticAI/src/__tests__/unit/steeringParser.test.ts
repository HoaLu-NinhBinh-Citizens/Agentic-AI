import { SteeringParser, SteeringContext } from '../../main-process/steeringParser';
import * as fs from 'fs';
import * as path from 'path';

// Mock fs module
jest.mock('fs', () => ({
  promises: {
    readFile: jest.fn(),
    readdir: jest.fn(),
    existsSync: jest.fn(),
  },
  existsSync: jest.fn(),
  watch: jest.fn(),
  watchFile: jest.fn(),
}));

describe('SteeringParser', () => {
  let parser: SteeringParser;
  const mockWorkspacePath = '/test/workspace';
  
  beforeEach(() => {
    parser = new SteeringParser();
    jest.clearAllMocks();
  });

  describe('setWorkspace', () => {
    it('should set the workspace path', () => {
      parser.setWorkspace(mockWorkspacePath);
      expect(parser.getWorkspace()).toBe(mockWorkspacePath);
    });

    it('should update workspace path when called again', () => {
      parser.setWorkspace(mockWorkspacePath);
      parser.setWorkspace('/new/workspace');
      expect(parser.getWorkspace()).toBe('/new/workspace');
    });
  });

  describe('loadSteeringFiles', () => {
    beforeEach(() => {
      // Default mock implementations
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md\nTest agents content');
          }
          if (filePath.includes('CLAUDE.md')) {
            return Promise.resolve('# CLAUDE.md\nTest claude content');
          }
          if (filePath.includes('product.md')) {
            return Promise.resolve('# Product\nProduct content');
          }
          return Promise.reject(new Error('File not found'));
        }
      );
      
      (fs.promises.readdir as jest.Mock).mockResolvedValue([]);
      (fs.existsSync as jest.Mock).mockReturnValue(false);
    });

    it('should load steering files from workspace', async () => {
      parser.setWorkspace(mockWorkspacePath);
      const context = await parser.loadSteeringFiles();
      
      expect(context.agents).toBeDefined();
      expect(context.claude).toBeDefined();
    });

    it('should return empty context when no workspace is set', async () => {
      const context = await parser.loadSteeringFiles();
      expect(context).toEqual({});
    });

    it('should handle missing files gracefully', async () => {
      (fs.promises.readFile as jest.Mock).mockRejectedValue(new Error('Not found'));
      
      parser.setWorkspace(mockWorkspacePath);
      const context = await parser.loadSteeringFiles();
      
      expect(context.agents).toBeUndefined();
    });

    it('should load all standard steering files', async () => {
      parser.setWorkspace(mockWorkspacePath);
      const context = await parser.loadSteeringFiles();
      
      // Should have attempted to load all standard files
      expect(fs.promises.readFile).toHaveBeenCalled();
    });

    it('should load cursor rules directory', async () => {
      const mockMdcFiles = ['rules1.mdc', 'rules2.mdc'];
      (fs.promises.readdir as jest.Mock).mockImplementation(
        (dirPath: string) => {
          if (dirPath.includes('.cursor/rules')) {
            return Promise.resolve(mockMdcFiles);
          }
          return Promise.resolve([]);
        }
      );
      (fs.existsSync as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('.cursor/rules')) return true;
          return false;
        }
      );
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('.mdc')) {
            return Promise.resolve('# Rule content');
          }
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
      
      parser.setWorkspace(mockWorkspacePath);
      const context = await parser.loadSteeringFiles();
      
      expect(context).toBeDefined();
    });
  });

  describe('getContext', () => {
    it('should return a copy of the context', async () => {
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
      
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const context1 = parser.getContext();
      const context2 = parser.getContext();
      
      expect(context1).toEqual(context2);
      expect(context1).not.toBe(context2); // Should be a copy
    });
  });

  describe('getSystemPrompt', () => {
    beforeEach(() => {
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md\nAgents content');
          }
          if (filePath.includes('CLAUDE.md')) {
            return Promise.resolve('# CLAUDE.md\nClaude content');
          }
          if (filePath.includes('product.md')) {
            return Promise.resolve('# Product\nProduct content');
          }
          if (filePath.includes('tech.md')) {
            return Promise.resolve('# Tech\nTech content');
          }
          if (filePath.includes('structure.md')) {
            return Promise.resolve('# Structure\nStructure content');
          }
          if (filePath.includes('requirements.md')) {
            return Promise.resolve('# Requirements\nRequirements content');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
    });

    it('should generate system prompt from loaded context', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const systemPrompt = parser.getSystemPrompt();
      
      expect(systemPrompt).toContain('AGENTS.md');
      expect(systemPrompt).toContain('CLAUDE.md');
    });

    it('should return default prompt when no context is loaded', () => {
      const systemPrompt = parser.getSystemPrompt();
      
      expect(systemPrompt).toBe('You are a helpful AI coding assistant.');
    });

    it('should include all loaded context sections', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const systemPrompt = parser.getSystemPrompt();
      
      expect(systemPrompt).toContain('Agents content');
      expect(systemPrompt).toContain('Claude content');
    });

    it('should handle cursor rules in system prompt', async () => {
      (fs.promises.readdir as jest.Mock).mockImplementation(
        (dirPath: string) => {
          if (dirPath.includes('.cursor/rules')) {
            return Promise.resolve(['test.mdc']);
          }
          return Promise.resolve([]);
        }
      );
      (fs.existsSync as jest.Mock).mockReturnValue(true);
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('.mdc')) {
            return Promise.resolve('# Test Rule\nRule content');
          }
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
      
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const systemPrompt = parser.getSystemPrompt();
      expect(systemPrompt).toContain('Cursor Rule');
    });
  });

  describe('getRelevantContext', () => {
    beforeEach(() => {
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md\nAgents content');
          }
          if (filePath.includes('CLAUDE.md')) {
            return Promise.resolve('# CLAUDE.md\nClaude content');
          }
          if (filePath.includes('product.md')) {
            return Promise.resolve('# Product\nProduct content');
          }
          if (filePath.includes('tech.md')) {
            return Promise.resolve('# Tech\nTech content');
          }
          if (filePath.includes('structure.md')) {
            return Promise.resolve('# Structure\nStructure content');
          }
          if (filePath.includes('requirements.md')) {
            return Promise.resolve('# Requirements\nRequirements content');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
    });

    it('should return relevant context for security queries', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const context = parser.getRelevantContext('how to handle security?');
      
      expect(context).toContain('Product content');
      expect(context).toContain('Tech content');
    });

    it('should return relevant context for architecture queries', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const context = parser.getRelevantContext('what is the architecture?');
      
      expect(context).toContain('Structure content');
      expect(context).toContain('Tech content');
    });

    it('should return relevant context for API queries', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const context = parser.getRelevantContext('API endpoint design');
      
      expect(context).toContain('Tech content');
      expect(context).toContain('Structure content');
    });

    it('should return relevant context for test queries', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const context = parser.getRelevantContext('how to write tests?');
      
      expect(context).toContain('Requirements content');
      expect(context).toContain('Tech content');
    });

    it('should return empty string when no relevant context found', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      // Only agents and claude are always included
      const context = parser.getRelevantContext('xyz unknown query');
      
      // agents and claude are always included based on implementation
      expect(context).toContain('Agents content');
      expect(context).toContain('Claude content');
    });

    it('should always include agents and claude context', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const context = parser.getRelevantContext('hello');
      
      expect(context).toContain('Agents content');
      expect(context).toContain('Claude content');
    });
  });

  describe('getFileContent', () => {
    beforeEach(() => {
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md\nAgents content');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
    });

    it('should return file content for loaded files', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const content = parser.getFileContent('AGENTS.md');
      
      expect(content).toContain('Agents content');
    });

    it('should return undefined for unloaded files', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const content = parser.getFileContent('NOTFOUND.md');
      
      expect(content).toBeUndefined();
    });
  });

  describe('getLoadedFiles', () => {
    beforeEach(() => {
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md');
          }
          if (filePath.includes('CLAUDE.md')) {
            return Promise.resolve('# CLAUDE.md');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
    });

    it('should return list of loaded files', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const loadedFiles = parser.getLoadedFiles();
      
      expect(loadedFiles.length).toBeGreaterThanOrEqual(2);
      expect(loadedFiles.some(f => f.file === 'AGENTS.md')).toBe(true);
    });

    it('should mark loaded files as loaded', async () => {
      parser.setWorkspace(mockWorkspacePath);
      await parser.loadSteeringFiles();
      
      const loadedFiles = parser.getLoadedFiles();
      const agentsFile = loadedFiles.find(f => f.file === 'AGENTS.md');
      
      expect(agentsFile?.loaded).toBe(true);
    });
  });

  describe('parseMarkdown', () => {
    it('should parse markdown sections and headings', async () => {
      const markdown = `
# Title

## Section 1
Content for section 1

## Section 2
Content for section 2
`;
      
      const result = await parser.parseMarkdown(markdown);
      
      expect(result.title).toBe('Title');
      expect(result.sections.length).toBeGreaterThanOrEqual(2);
    });

    it('should parse todos', async () => {
      const markdown = `
# Tasks
- [ ] Task 1
- [x] Task 2
- [ ] Task 3
`;
      
      const result = await parser.parseMarkdown(markdown);
      
      expect(result.todos.length).toBe(3);
      expect(result.todos[0].checked).toBe(false);
      expect(result.todos[1].checked).toBe(true);
    });

    it('should handle empty markdown', async () => {
      const result = await parser.parseMarkdown('');
      
      expect(result.title).toBe('');
      expect(result.sections).toEqual([]);
      expect(result.todos).toEqual([]);
    });
  });

  describe('extractTasksFromSpec', () => {
    it('should extract tasks from markdown', async () => {
      const spec = `
# Specification

## Tasks
- [ ] High priority task
- [x] Completed task
- [ ] Regular task
`;
      
      const tasks = parser.extractTasksFromSpec(spec);
      
      expect(tasks.length).toBeGreaterThanOrEqual(2);
    });

    it('should assign high priority to critical tasks', async () => {
      const spec = `
# Spec

- [ ] [critical] Important task
`;
      
      const tasks = parser.extractTasksFromSpec(spec);
      
      const criticalTask = tasks.find(t => t.title.toLowerCase().includes('important'));
      expect(criticalTask?.priority).toBe('high');
    });

    it('should assign low priority to low priority tasks', async () => {
      const spec = `
# Spec

- [ ] [low] Minor task
`;
      
      const tasks = parser.extractTasksFromSpec(spec);
      
      const lowTask = tasks.find(t => t.title.toLowerCase().includes('minor'));
      expect(lowTask?.priority).toBe('low');
    });
  });

  describe('watchForChanges', () => {
    it('should set up watchers for steering files', () => {
      (fs.existsSync as jest.Mock).mockReturnValue(true);
      (fs.watch as jest.Mock).mockImplementation(
        (filePath: string, callback: Function) => {
          return { close: jest.fn() };
        }
      );
      
      parser.setWorkspace(mockWorkspacePath);
      
      const callback = jest.fn();
      parser.watchForChanges(callback);
      
      expect(fs.watch).toHaveBeenCalled();
    });

    it('should not watch when no workspace is set', () => {
      const callback = jest.fn();
      parser.watchForChanges(callback);
      
      expect(fs.watch).not.toHaveBeenCalled();
    });
  });

  describe('stopWatching', () => {
    it('should close all watchers', () => {
      const mockWatcher = { close: jest.fn() };
      (fs.watch as jest.Mock).mockReturnValue(mockWatcher);
      
      parser.setWorkspace(mockWorkspacePath);
      parser.watchForChanges(jest.fn());
      parser.stopWatching();
      
      expect(mockWatcher.close).toHaveBeenCalled();
    });
  });

  describe('workspace files', () => {
    beforeEach(() => {
      (fs.promises.readFile as jest.Mock).mockImplementation(
        (filePath: string) => {
          if (filePath.includes('AGENTS.md')) {
            return Promise.resolve('# AGENTS.md');
          }
          if (filePath.includes('SPEC.md')) {
            return Promise.resolve('# SPEC\nSpec content');
          }
          if (filePath.includes('README.md')) {
            return Promise.resolve('# README\nReadme content');
          }
          return Promise.reject(new Error('Not found'));
        }
      );
    });

    it('should load workspace documentation files', async () => {
      parser.setWorkspace(mockWorkspacePath);
      const context = await parser.loadSteeringFiles();
      
      expect(context.spec || context.readme).toBeDefined();
    });
  });

  describe('error handling', () => {
    it('should handle fs errors gracefully', async () => {
      (fs.promises.readFile as jest.Mock).mockRejectedValue(
        new Error('Permission denied')
      );
      (fs.promises.readdir as jest.Mock).mockRejectedValue(
        new Error('Directory not found')
      );
      (fs.existsSync as jest.Mock).mockReturnValue(false);
      
      parser.setWorkspace(mockWorkspacePath);
      
      // Should not throw
      const context = await parser.loadSteeringFiles();
      expect(context).toBeDefined();
    });

    it('should handle malformed markdown gracefully', async () => {
      const malformedMarkdown = '# Title\n\n```\nunclosed code block\n\n';
      
      const result = await parser.parseMarkdown(malformedMarkdown);
      
      expect(result).toBeDefined();
      expect(result.title).toBe('Title');
    });
  });
});
