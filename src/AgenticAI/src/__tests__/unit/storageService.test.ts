import { storage } from '../../main-process/storage';

describe('StorageService', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('storage singleton', () => {
    it('should export a storage instance', () => {
      expect(storage).toBeDefined();
    });

    it('should have getSettings method', () => {
      expect(typeof storage.getSettings).toBe('function');
    });

    it('should have updateSettings method', () => {
      expect(typeof storage.updateSettings).toBe('function');
    });

    it('should have getRecentWorkspaces method', () => {
      expect(typeof storage.getRecentWorkspaces).toBe('function');
    });

    it('should have getUIState method', () => {
      expect(typeof storage.getUIState).toBe('function');
    });

    it('should have updateUIState method', () => {
      expect(typeof storage.updateUIState).toBe('function');
    });

    it('should have getTasks method', () => {
      expect(typeof storage.getTasks).toBe('function');
    });

    it('should have saveTasks method', () => {
      expect(typeof storage.saveTasks).toBe('function');
    });

    it('should have addTask method', () => {
      expect(typeof storage.addTask).toBe('function');
    });

    it('should have updateTask method', () => {
      expect(typeof storage.updateTask).toBe('function');
    });

    it('should have deleteTask method', () => {
      expect(typeof storage.deleteTask).toBe('function');
    });

    it('should have getOpenFiles method', () => {
      expect(typeof storage.getOpenFiles).toBe('function');
    });

    it('should have updateOpenFiles method', () => {
      expect(typeof storage.updateOpenFiles).toBe('function');
    });

    it('should have clearAll method', () => {
      expect(typeof storage.clearAll).toBe('function');
    });

    it('should have exportData method', () => {
      expect(typeof storage.exportData).toBe('function');
    });

    it('should have getStorePath method', () => {
      expect(typeof storage.getStorePath).toBe('function');
    });
  });

  describe('getSettings', () => {
    it('should return settings from store', () => {
      const settings = storage.getSettings();
      expect(settings).toBeDefined();
      expect(settings).toHaveProperty('theme');
      expect(settings).toHaveProperty('fontSize');
    });
  });

  describe('updateSettings', () => {
    it('should update settings', () => {
      const initialSettings = storage.getSettings();
      
      storage.updateSettings({ theme: 'light' });
      
      const updatedSettings = storage.getSettings();
      expect(updatedSettings.theme).toBe('light');
      
      // Restore original
      storage.updateSettings({ theme: initialSettings.theme });
    });
  });

  describe('getRecentWorkspaces', () => {
    it('should return recent workspaces array', () => {
      const recents = storage.getRecentWorkspaces();
      expect(Array.isArray(recents)).toBe(true);
    });
  });

  describe('getUIState', () => {
    it('should return UI state from store', () => {
      const uiState = storage.getUIState();
      expect(uiState).toBeDefined();
      expect(uiState).toHaveProperty('expandedFolders');
      expect(uiState).toHaveProperty('activePanel');
    });
  });

  describe('updateUIState', () => {
    it('should update UI state', () => {
      const initialState = storage.getUIState();
      const initialWidth = initialState.sidebarWidth;
      
      storage.updateUIState({ sidebarWidth: 300 });
      
      const updatedState = storage.getUIState();
      expect(updatedState.sidebarWidth).toBe(300);
      
      // Restore original
      storage.updateUIState({ sidebarWidth: initialWidth });
    });
  });

  describe('getTasks', () => {
    it('should return tasks array', () => {
      const tasks = storage.getTasks();
      expect(Array.isArray(tasks)).toBe(true);
    });
  });

  describe('saveTasks', () => {
    it('should save tasks to store', () => {
      const testTasks = [
        {
          id: 'test-1',
          title: 'Test Task',
          status: 'todo' as const,
          priority: 'high' as const,
          createdAt: new Date().toISOString(),
        },
      ];

      storage.saveTasks(testTasks);
      
      const retrievedTasks = storage.getTasks();
      expect(retrievedTasks).toEqual(testTasks);
    });
  });

  describe('getOpenFiles', () => {
    it('should return open files object', () => {
      const openFiles = storage.getOpenFiles();
      expect(openFiles).toBeDefined();
      expect(openFiles).toHaveProperty('files');
      expect(openFiles).toHaveProperty('activeFile');
    });
  });

  describe('updateOpenFiles', () => {
    it('should update open files', () => {
      const testFiles = {
        files: ['/test/file1.ts', '/test/file2.ts'],
        activeFile: '/test/file1.ts',
      };

      storage.updateOpenFiles(testFiles);
      
      const updatedFiles = storage.getOpenFiles();
      expect(updatedFiles.files).toEqual(testFiles.files);
    });
  });

  describe('clearAll', () => {
    it('should clear all data from store', () => {
      expect(() => storage.clearAll()).not.toThrow();
    });
  });

  describe('exportData', () => {
    it('should export all stored data', () => {
      const data = storage.exportData();
      expect(data).toBeDefined();
      expect(data).toHaveProperty('settings');
      expect(data).toHaveProperty('uiState');
      expect(data).toHaveProperty('tasks');
    });
  });

  describe('getStorePath', () => {
    it('should return store path', () => {
      const path = storage.getStorePath();
      expect(typeof path).toBe('string');
    });
  });
});
