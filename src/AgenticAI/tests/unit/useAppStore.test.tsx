/**
 * Unit Tests for Zustand Store (useAppStore)
 * Priority: High - Expected ROI: Very High
 */
import { renderHook, act } from '@testing-library/react';
import { useAppStore } from '../../src/renderer/store/useAppStore';

describe('Zustand Store - Workspace Management', () => {
  beforeEach(() => {
    // Reset store before each test
    useAppStore.setState({
      workspacePath: null,
      files: [],
      openFiles: [],
      activeFile: null,
      expandedFolders: [],
      tasks: [],
      messages: [],
      steeringContext: {},
    });
  });

  describe('Workspace Operations', () => {
    test('setWorkspacePath should update workspace path', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setWorkspacePath('/test/path');
      });
      
      expect(result.current.workspacePath).toBe('/test/path');
    });

    test('addRecentWorkspace should add workspace to recent list', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addRecentWorkspace('/test/path');
      });
      
      expect(result.current.recentWorkspaces).toContain('/test/path');
    });
  });

  describe('File Operations', () => {
    test('setFiles should update file tree', () => {
      const { result } = renderHook(() => useAppStore());
      
      const files = [
        { name: 'file.ts', path: '/test/file.ts', isDirectory: false, children: [] }
      ];
      
      act(() => {
        result.current.setFiles(files as any);
      });
      
      expect(result.current.files).toHaveLength(1);
    });

    test('toggleFolder should add to expanded folders', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addExpandedFolder('/test/folder');
      });
      
      expect(result.current.expandedFolders).toContain('/test/folder');
    });

    test('toggleFolder should remove from expanded folders', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addExpandedFolder('/test/folder');
      });
      
      act(() => {
        result.current.removeExpandedFolder('/test/folder');
      });
      
      expect(result.current.expandedFolders).not.toContain('/test/folder');
    });
  });

  describe('Open Files Management', () => {
    test('addOpenFile should add file to openFiles', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addOpenFile('/test/file.ts');
      });
      
      expect(result.current.openFiles).toContain('/test/file.ts');
    });

    test('addOpenFile should not duplicate files', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addOpenFile('/test/file.ts');
        result.current.addOpenFile('/test/file.ts');
      });
      
      const count = result.current.openFiles.filter(f => f === '/test/file.ts').length;
      expect(count).toBe(1);
    });

    test('setActiveFile should change active file', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addOpenFile('/test/file1.ts');
        result.current.addOpenFile('/test/file2.ts');
      });
      
      act(() => {
        result.current.setActiveFile('/test/file1.ts');
      });
      
      expect(result.current.activeFile).toBe('/test/file1.ts');
    });

    test('removeOpenFile should close file', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addOpenFile('/test/file1.ts');
        result.current.addOpenFile('/test/file2.ts');
      });
      
      act(() => {
        result.current.removeOpenFile('/test/file1.ts');
      });
      
      expect(result.current.openFiles).not.toContain('/test/file1.ts');
      expect(result.current.openFiles).toContain('/test/file2.ts');
    });
  });
});

describe('Zustand Store - Task Management', () => {
  beforeEach(() => {
    useAppStore.setState({
      tasks: [],
    });
  });

  describe('Task Operations', () => {
    test('addTask should add new task', () => {
      const { result } = renderHook(() => useAppStore());
      
      const task = {
        id: '1',
        title: 'New task',
        description: '',
        completed: false,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      
      act(() => {
        result.current.addTask(task);
      });
      
      expect(result.current.tasks).toHaveLength(1);
      expect(result.current.tasks[0].title).toBe('New task');
      expect(result.current.tasks[0].completed).toBe(false);
    });

    test('updateTask should update task properties', () => {
      const { result } = renderHook(() => useAppStore());
      
      const task = {
        id: '1',
        title: 'Original title',
        description: '',
        completed: false,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      
      act(() => {
        result.current.addTask(task);
      });
      
      act(() => {
        result.current.updateTask('1', { title: 'Updated title', completed: true });
      });
      
      expect(result.current.tasks[0].title).toBe('Updated title');
      expect(result.current.tasks[0].completed).toBe(true);
    });

    test('deleteTask should remove task', () => {
      const { result } = renderHook(() => useAppStore());
      
      const task = {
        id: '1',
        title: 'Task to delete',
        description: '',
        completed: false,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      
      act(() => {
        result.current.addTask(task);
      });
      
      act(() => {
        result.current.deleteTask('1');
      });
      
      expect(result.current.tasks).toHaveLength(0);
    });
  });
});

describe('Zustand Store - UI State', () => {
  beforeEach(() => {
    useAppStore.setState({
      activeSidebarView: 'explorer',
      isTerminalOpen: false,
      isSettingsOpen: false,
    });
  });

  describe('Sidebar Operations', () => {
    test('setActiveSidebarView should change sidebar view', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setActiveSidebarView('git');
      });
      
      expect(result.current.activeSidebarView).toBe('git');
    });
  });

  describe('Terminal Operations', () => {
    test('setTerminalOpen should toggle terminal visibility', () => {
      const { result } = renderHook(() => useAppStore());
      
      expect(result.current.isTerminalOpen).toBe(false);
      
      act(() => {
        result.current.setTerminalOpen(true);
      });
      
      expect(result.current.isTerminalOpen).toBe(true);
    });
  });

  describe('Settings Operations', () => {
    test('setSettingsOpen should toggle settings visibility', () => {
      const { result } = renderHook(() => useAppStore());
      
      expect(result.current.isSettingsOpen).toBe(false);
      
      act(() => {
        result.current.setSettingsOpen(true);
      });
      
      expect(result.current.isSettingsOpen).toBe(true);
    });
  });
});

describe('Zustand Store - Messages', () => {
  beforeEach(() => {
    useAppStore.setState({
      messages: [],
    });
  });

  describe('Message Operations', () => {
    test('addMessage should add message to messages array', () => {
      const { result } = renderHook(() => useAppStore());
      
      const message = {
        id: '1',
        role: 'user' as const,
        content: 'Hello',
        timestamp: new Date().toISOString(),
      };
      
      act(() => {
        result.current.addMessage(message);
      });
      
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].content).toBe('Hello');
    });

    test('clearMessages should empty messages array', () => {
      const { result } = renderHook(() => useAppStore());
      
      const message1 = {
        id: '1',
        role: 'user' as const,
        content: 'Hello',
        timestamp: new Date().toISOString(),
      };
      
      const message2 = {
        id: '2',
        role: 'assistant' as const,
        content: 'Hi there',
        timestamp: new Date().toISOString(),
      };
      
      act(() => {
        result.current.addMessage(message1);
        result.current.addMessage(message2);
      });
      
      act(() => {
        result.current.clearMessages();
      });
      
      expect(result.current.messages).toHaveLength(0);
    });
  });
});

describe('Zustand Store - Steering Context', () => {
  beforeEach(() => {
    useAppStore.setState({
      steeringContext: {},
    });
  });

  describe('Steering Context Operations', () => {
    test('setSteeringContext should update context', () => {
      const { result } = renderHook(() => useAppStore());
      
      const context = {
        projectType: 'electron',
        language: 'typescript',
      };
      
      act(() => {
        result.current.setSteeringContext(context);
      });
      
      expect(result.current.steeringContext).toEqual(context);
    });
  });
});

describe('Zustand Store - AI Config', () => {
  beforeEach(() => {
    useAppStore.setState({
      aiConfig: null,
      ollamaHealth: null,
      ollamaModels: [],
    });
  });

  describe('AI Config Operations', () => {
    test('setAiConfig should update AI configuration', () => {
      const { result } = renderHook(() => useAppStore());
      
      const config = {
        provider: 'openai' as const,
        model: 'gpt-4',
        apiKey: 'test-key',
      };
      
      act(() => {
        result.current.setAiConfig(config);
      });
      
      expect(result.current.aiConfig).toEqual(config);
    });
  });

  describe('Ollama State Operations', () => {
    test('setOllamaHealth should update Ollama health status', () => {
      const { result } = renderHook(() => useAppStore());
      
      const health = {
        available: true,
        responseTime: 100,
      };
      
      act(() => {
        result.current.setOllamaHealth(health as any);
      });
      
      expect(result.current.ollamaHealth).toEqual(health);
    });

    test('setOllamaModels should update available models', () => {
      const { result } = renderHook(() => useAppStore());
      
      const models = [
        { name: 'llama2', size: 4000000000, modified: Date.now() },
      ];
      
      act(() => {
        result.current.setOllamaModels(models as any);
      });
      
      expect(result.current.ollamaModels).toHaveLength(1);
    });
  });
});

describe('Zustand Store - Git State', () => {
  beforeEach(() => {
    useAppStore.setState({
      gitBranch: '',
      gitStatus: [],
      gitLoading: false,
      commitMessage: '',
    });
  });

  describe('Git State Operations', () => {
    test('setGitBranch should update branch name', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setGitBranch('feature/new-feature');
      });
      
      expect(result.current.gitBranch).toBe('feature/new-feature');
    });

    test('setGitStatus should update git status', () => {
      const { result } = renderHook(() => useAppStore());
      
      const status = [
        { path: 'file.ts', status: 'modified' as const, staged: false },
      ];
      
      act(() => {
        result.current.setGitStatus(status);
      });
      
      expect(result.current.gitStatus).toHaveLength(1);
    });

    test('setGitLoading should update loading state', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setGitLoading(true);
      });
      
      expect(result.current.gitLoading).toBe(true);
    });

    test('setCommitMessage should update commit message', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setCommitMessage('feat: add new feature');
      });
      
      expect(result.current.commitMessage).toBe('feat: add new feature');
    });
  });
});

describe('Zustand Store - Cursor Position', () => {
  beforeEach(() => {
    useAppStore.setState({
      cursorPosition: null,
    });
  });

  describe('Cursor Position Operations', () => {
    test('setCursorPosition should update cursor position', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setCursorPosition({ line: 10, column: 5 });
      });
      
      expect(result.current.cursorPosition).toEqual({ line: 10, column: 5 });
    });

    test('setCursorPosition should clear position with null', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setCursorPosition({ line: 10, column: 5 });
      });
      
      act(() => {
        result.current.setCursorPosition(null);
      });
      
      expect(result.current.cursorPosition).toBeNull();
    });
  });
});
