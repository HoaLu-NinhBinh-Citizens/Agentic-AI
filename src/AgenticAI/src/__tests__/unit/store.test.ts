import { useAppStore } from '../../renderer/store/useAppStore';
import { FileNode, Task, Spec, ChatMessage } from '../../shared/types';

describe('useAppStore', () => {
  beforeEach(() => {
    useAppStore.setState({
      workspacePath: null,
      recentWorkspaces: [],
      files: [],
      activeFile: null,
      openFiles: [],
      cursorPosition: null,
      spec: null,
      tasks: [],
      messages: [],
      steeringContext: {},
      expandedFolders: [],
      activeSidebarView: 'explorer',
      isTerminalOpen: false,
      isSettingsOpen: false,
      aiConfig: null,
      ollamaHealth: null,
      ollamaModels: [],
      gitBranch: 'main',
      gitStatus: [],
      gitLoading: false,
      commitMessage: '',
    });
  });

  describe('Workspace State', () => {
    it('should set workspace path', () => {
      const testPath = '/test/workspace';
      useAppStore.getState().setWorkspacePath(testPath);
      expect(useAppStore.getState().workspacePath).toBe(testPath);
    });

    it('should add to recent workspaces', () => {
      const testPath = '/test/workspace';
      useAppStore.getState().addRecentWorkspace(testPath);
      expect(useAppStore.getState().recentWorkspaces).toContain(testPath);
    });

    it('should not duplicate recent workspaces', () => {
      const testPath = '/test/workspace';
      useAppStore.getState().addRecentWorkspace(testPath);
      useAppStore.getState().addRecentWorkspace(testPath);
      const count = useAppStore.getState().recentWorkspaces.filter(p => p === testPath).length;
      expect(count).toBe(1);
    });

    it('should limit recent workspaces to 10', () => {
      for (let i = 0; i < 15; i++) {
        useAppStore.getState().addRecentWorkspace(`/workspace/${i}`);
      }
      expect(useAppStore.getState().recentWorkspaces.length).toBeLessThanOrEqual(10);
    });
  });

  describe('Files State', () => {
    const mockFiles: FileNode[] = [
      {
        name: 'src',
        path: '/test/src',
        isDirectory: true,
        children: [
          { name: 'index.ts', path: '/test/src/index.ts', isDirectory: false }
        ]
      }
    ];

    it('should set files', () => {
      useAppStore.getState().setFiles(mockFiles);
      expect(useAppStore.getState().files).toEqual(mockFiles);
    });

    it('should toggle folder open/close state', () => {
      useAppStore.getState().setFiles(mockFiles);
      useAppStore.getState().toggleFolder('/test/src');
      
      const updatedFiles = useAppStore.getState().files;
      expect(updatedFiles[0].isOpen).toBe(true);
      expect(useAppStore.getState().expandedFolders).toContain('/test/src');
    });

    it('should toggle folder back to closed', () => {
      useAppStore.getState().setFiles(mockFiles);
      useAppStore.getState().toggleFolder('/test/src');
      useAppStore.getState().toggleFolder('/test/src');
      
      const updatedFiles = useAppStore.getState().files;
      expect(updatedFiles[0].isOpen).toBe(false);
      expect(useAppStore.getState().expandedFolders).not.toContain('/test/src');
    });
  });

  describe('Editor State', () => {
    it('should set active file', () => {
      const filePath = '/test/file.ts';
      useAppStore.getState().setActiveFile(filePath);
      expect(useAppStore.getState().activeFile).toBe(filePath);
    });

    it('should add open file', () => {
      const filePath = '/test/file.ts';
      useAppStore.getState().addOpenFile(filePath);
      expect(useAppStore.getState().openFiles).toContain(filePath);
    });

    it('should not duplicate open files', () => {
      const filePath = '/test/file.ts';
      useAppStore.getState().addOpenFile(filePath);
      useAppStore.getState().addOpenFile(filePath);
      expect(useAppStore.getState().openFiles.filter(f => f === filePath).length).toBe(1);
    });

    it('should remove open file', () => {
      const filePath = '/test/file.ts';
      useAppStore.getState().addOpenFile(filePath);
      useAppStore.getState().removeOpenFile(filePath);
      expect(useAppStore.getState().openFiles).not.toContain(filePath);
    });

    it('should set cursor position', () => {
      const position = { line: 10, column: 5 };
      useAppStore.getState().setCursorPosition(position);
      expect(useAppStore.getState().cursorPosition).toEqual(position);
    });

    it('should remove active file when removing open file', () => {
      const filePath = '/test/file.ts';
      useAppStore.getState().addOpenFile(filePath);
      useAppStore.getState().setActiveFile(filePath);
      useAppStore.getState().removeOpenFile(filePath);
      expect(useAppStore.getState().activeFile).toBeNull();
    });
  });

  describe('Tasks State', () => {
    const mockTask: Task = {
      id: '1',
      title: 'Test Task',
      description: 'Test Description',
      status: 'todo',
      priority: 'high',
      createdAt: new Date().toISOString()
    };

    it('should add task', () => {
      useAppStore.getState().addTask(mockTask);
      expect(useAppStore.getState().tasks).toContainEqual(mockTask);
    });

    it('should update task', () => {
      useAppStore.getState().addTask(mockTask);
      useAppStore.getState().updateTask('1', { status: 'doing' });
      
      const updatedTask = useAppStore.getState().tasks.find(t => t.id === '1');
      expect(updatedTask?.status).toBe('doing');
    });

    it('should delete task', () => {
      useAppStore.getState().addTask(mockTask);
      useAppStore.getState().deleteTask('1');
      expect(useAppStore.getState().tasks).not.toContainEqual(mockTask);
    });

    it('should set spec and initialize tasks', () => {
      const mockSpec: Spec = {
        id: 'spec1',
        title: 'Test Spec',
        content: 'Spec content',
        tasks: [mockTask],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      };
      
      useAppStore.getState().setSpec(mockSpec);
      expect(useAppStore.getState().spec).toEqual(mockSpec);
      expect(useAppStore.getState().tasks).toEqual([mockTask]);
    });
  });

  describe('Messages State', () => {
    const mockMessage: ChatMessage = {
      id: '1',
      role: 'user',
      content: 'Hello',
      timestamp: new Date().toISOString()
    };

    it('should add message', () => {
      useAppStore.getState().addMessage(mockMessage);
      expect(useAppStore.getState().messages).toContainEqual(mockMessage);
    });

    it('should clear messages', () => {
      useAppStore.getState().addMessage(mockMessage);
      useAppStore.getState().clearMessages();
      expect(useAppStore.getState().messages).toEqual([]);
    });
  });

  describe('UI State', () => {
    it('should set active sidebar view', () => {
      useAppStore.getState().setActiveSidebarView('git');
      expect(useAppStore.getState().activeSidebarView).toBe('git');
    });

    it('should set terminal open state', () => {
      useAppStore.getState().setTerminalOpen(true);
      expect(useAppStore.getState().isTerminalOpen).toBe(true);
    });

    it('should set settings open state', () => {
      useAppStore.getState().setSettingsOpen(true);
      expect(useAppStore.getState().isSettingsOpen).toBe(true);
    });

    it('should manage expanded folders', () => {
      useAppStore.getState().addExpandedFolder('/test/path');
      expect(useAppStore.getState().expandedFolders).toContain('/test/path');
      
      useAppStore.getState().removeExpandedFolder('/test/path');
      expect(useAppStore.getState().expandedFolders).not.toContain('/test/path');
    });

    it('should not add duplicate expanded folders', () => {
      useAppStore.getState().addExpandedFolder('/test/path');
      useAppStore.getState().addExpandedFolder('/test/path');
      expect(useAppStore.getState().expandedFolders.filter(p => p === '/test/path').length).toBe(1);
    });
  });

  describe('Git State', () => {
    it('should set git branch', () => {
      useAppStore.getState().setGitBranch('feature/test');
      expect(useAppStore.getState().gitBranch).toBe('feature/test');
    });

    it('should set git status', () => {
      const mockStatus = [
        { path: 'file.ts', status: 'modified' as const, staged: true }
      ];
      useAppStore.getState().setGitStatus(mockStatus);
      expect(useAppStore.getState().gitStatus).toEqual(mockStatus);
    });

    it('should set git loading state', () => {
      useAppStore.getState().setGitLoading(true);
      expect(useAppStore.getState().gitLoading).toBe(true);
    });

    it('should set commit message', () => {
      useAppStore.getState().setCommitMessage('test commit');
      expect(useAppStore.getState().commitMessage).toBe('test commit');
    });
  });

  describe('AI Config State', () => {
    it('should set AI config', () => {
      const mockConfig = {
        provider: 'ollama' as const,
        ollamaEndpoint: 'http://localhost:11434',
        ollamaModel: 'codellama'
      };
      useAppStore.getState().setAiConfig(mockConfig);
      expect(useAppStore.getState().aiConfig).toEqual(mockConfig);
    });

    it('should set ollama health status', () => {
      const mockHealth = {
        available: true,
        latencyMs: 50
      };
      useAppStore.getState().setOllamaHealth(mockHealth);
      expect(useAppStore.getState().ollamaHealth).toEqual(mockHealth);
    });

    it('should set ollama models', () => {
      const mockModels = [
        { name: 'codellama', modified_at: '2024-01-01', size: 1000000 }
      ];
      useAppStore.getState().setOllamaModels(mockModels);
      expect(useAppStore.getState().ollamaModels).toEqual(mockModels);
    });
  });
});
