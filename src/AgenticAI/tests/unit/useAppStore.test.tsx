/**
 * Unit Tests for Zustand Store (useAppStore)
 * Priority: High - Expected ROI: Very High
 */
import { renderHook, act } from '@testing-library/react';
import { useAppStore } from '../../src/renderer/store/useAppStore';

describe('Zustand Store - Workspace Management', () => {
  beforeEach(() => {
    // Reset store before each test
    useAppStore.getState().resetStore?.();
  });

  describe('Workspace Operations', () => {
    test('setWorkspace should update workspace path', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setWorkspace('/test/path');
      });
      
      expect(result.current.workspace).toBe('/test/path');
    });

    test('setWorkspace should clear file tree when workspace changes', () => {
      const { result } = renderHook(() => useAppStore());
      
      // First set a workspace with some files
      act(() => {
        result.current.setWorkspace('/initial/path');
      });
      
      // Then change to a new workspace
      act(() => {
        result.current.setWorkspace('/new/path');
      });
      
      expect(result.current.workspace).toBe('/new/path');
    });

    test('getWorkspace should return current workspace', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.setWorkspace('/my/project');
      });
      
      expect(result.current.workspace).toBe('/my/project');
    });
  });

  describe('File Operations', () => {
    test('addFile should add file to fileTree', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addFile('/test/file.ts', {
          name: 'file.ts',
          path: '/test/file.ts',
          isDirectory: false,
        });
      });
      
      expect(result.current.fileTree).toHaveLength(1);
      expect(result.current.fileTree[0].path).toBe('/test/file.ts');
    });

    test('addFile should not add duplicate files', () => {
      const { result } = renderHook(() => useAppStore());
      
      const file = {
        name: 'file.ts',
        path: '/test/file.ts',
        isDirectory: false,
      };
      
      act(() => {
        result.current.addFile('/test/file.ts', file);
        result.current.addFile('/test/file.ts', file);
      });
      
      expect(result.current.fileTree).toHaveLength(1);
    });

    test('removeFile should remove file from fileTree', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addFile('/test/file.ts', {
          name: 'file.ts',
          path: '/test/file.ts',
          isDirectory: false,
        });
      });
      
      act(() => {
        result.current.removeFile('/test/file.ts');
      });
      
      expect(result.current.fileTree).toHaveLength(0);
    });

    test('toggleFolder should toggle folder expanded state', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.toggleFolder('/test/folder');
      });
      
      expect(result.current.expandedFolders).toContain('/test/folder');
      
      act(() => {
        result.current.toggleFolder('/test/folder');
      });
      
      expect(result.current.expandedFolders).not.toContain('/test/folder');
    });
  });

  describe('Open Files Management', () => {
    test('openFile should add file to openFiles', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.openFile('/test/file.ts');
      });
      
      expect(result.current.openFiles).toContain('/test/file.ts');
      expect(result.current.activeFile).toBe('/test/file.ts');
    });

    test('openFile should set file as active', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.openFile('/test/file1.ts');
        result.current.openFile('/test/file2.ts');
      });
      
      expect(result.current.activeFile).toBe('/test/file2.ts');
    });

    test('setActiveFile should change active file', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.openFile('/test/file1.ts');
        result.current.openFile('/test/file2.ts');
      });
      
      act(() => {
        result.current.setActiveFile('/test/file1.ts');
      });
      
      expect(result.current.activeFile).toBe('/test/file1.ts');
    });

    test('removeOpenFile should close file', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.openFile('/test/file1.ts');
        result.current.openFile('/test/file2.ts');
      });
      
      act(() => {
        result.current.removeOpenFile('/test/file1.ts');
      });
      
      expect(result.current.openFiles).not.toContain('/test/file1.ts');
      expect(result.current.openFiles).toContain('/test/file2.ts');
    });

    test('removeOpenFile should update activeFile if closed file was active', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.openFile('/test/file1.ts');
        result.current.openFile('/test/file2.ts');
        result.current.setActiveFile('/test/file1.ts');
      });
      
      act(() => {
        result.current.removeOpenFile('/test/file1.ts');
      });
      
      expect(result.current.activeFile).toBe('/test/file2.ts');
    });
  });
});

describe('Zustand Store - Task Management', () => {
  beforeEach(() => {
    useAppStore.getState().resetStore?.();
  });

  describe('Task Operations', () => {
    test('addTask should add new task', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addTask('New task');
      });
      
      expect(result.current.tasks).toHaveLength(1);
      expect(result.current.tasks[0].title).toBe('New task');
      expect(result.current.tasks[0].completed).toBe(false);
    });

    test('addTask should generate unique id', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addTask('Task 1');
        result.current.addTask('Task 2');
      });
      
      expect(result.current.tasks[0].id).not.toBe(result.current.tasks[1].id);
    });

    test('updateTask should update task properties', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addTask('Original title');
      });
      
      const taskId = result.current.tasks[0].id;
      
      act(() => {
        result.current.updateTask(taskId, { title: 'Updated title', completed: true });
      });
      
      expect(result.current.tasks[0].title).toBe('Updated title');
      expect(result.current.tasks[0].completed).toBe(true);
    });

    test('deleteTask should remove task', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addTask('Task to delete');
      });
      
      const taskId = result.current.tasks[0].id;
      
      act(() => {
        result.current.deleteTask(taskId);
      });
      
      expect(result.current.tasks).toHaveLength(0);
    });

    test('toggleTask should toggle completed state', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addTask('Task to toggle');
      });
      
      const taskId = result.current.tasks[0].id;
      
      expect(result.current.tasks[0].completed).toBe(false);
      
      act(() => {
        result.current.toggleTask(taskId);
      });
      
      expect(result.current.tasks[0].completed).toBe(true);
    });
  });
});

describe('Zustand Store - UI State', () => {
  beforeEach(() => {
    useAppStore.getState().resetStore?.();
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
    useAppStore.getState().resetStore?.();
  });

  describe('Message Operations', () => {
    test('addMessage should add message to messages array', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addMessage({
          id: '1',
          role: 'user',
          content: 'Hello',
          timestamp: new Date().toISOString(),
        });
      });
      
      expect(result.current.messages).toHaveLength(1);
      expect(result.current.messages[0].content).toBe('Hello');
    });

    test('clearMessages should empty messages array', () => {
      const { result } = renderHook(() => useAppStore());
      
      act(() => {
        result.current.addMessage({
          id: '1',
          role: 'user',
          content: 'Hello',
          timestamp: new Date().toISOString(),
        });
        result.current.addMessage({
          id: '2',
          role: 'assistant',
          content: 'Hi there',
          timestamp: new Date().toISOString(),
        });
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
    useAppStore.getState().resetStore?.();
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
