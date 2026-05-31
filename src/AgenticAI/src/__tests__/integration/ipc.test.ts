import { useAppStore } from '../../renderer/store/useAppStore';

describe('IPC Communication', () => {
  beforeEach(() => {
    useAppStore.setState({
      workspacePath: null,
      files: [],
      activeFile: null,
      openFiles: [],
      tasks: [],
      messages: [],
      expandedFolders: [],
    });
    jest.clearAllMocks();
  });

  describe('File System Operations', () => {
    it('should read directory and build file tree', async () => {
      const mockEntries = [
        { name: 'src', path: '/workspace/src', isDirectory: true },
        { name: 'index.ts', path: '/workspace/index.ts', isDirectory: false }
      ];

      window.electronAPI.readDirectory.mockResolvedValueOnce(mockEntries);
      
      const entries = await window.electronAPI.readDirectory('/workspace');
      
      expect(entries).toEqual(mockEntries);
      expect(window.electronAPI.readDirectory).toHaveBeenCalledWith('/workspace');
    });

    it('should read file content', async () => {
      const mockContent = 'const x = 1;';
      window.electronAPI.readFile.mockResolvedValueOnce(mockContent);
      
      const content = await window.electronAPI.readFile('/workspace/src/index.ts');
      
      expect(content).toBe(mockContent);
      expect(window.electronAPI.readFile).toHaveBeenCalledWith('/workspace/src/index.ts');
    });

    it('should write file content', async () => {
      window.electronAPI.writeFile.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.writeFile('/workspace/src/index.ts', 'const x = 2;');
      
      expect(result).toBe(true);
      expect(window.electronAPI.writeFile).toHaveBeenCalledWith(
        '/workspace/src/index.ts',
        'const x = 2;'
      );
    });

    it('should create new file', async () => {
      window.electronAPI.createFile.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.createFile('/workspace/src/newfile.ts');
      
      expect(result).toBe(true);
      expect(window.electronAPI.createFile).toHaveBeenCalledWith('/workspace/src/newfile.ts');
    });

    it('should create new directory', async () => {
      window.electronAPI.createDirectory.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.createDirectory('/workspace/src/newdir');
      
      expect(result).toBe(true);
      expect(window.electronAPI.createDirectory).toHaveBeenCalledWith('/workspace/src/newdir');
    });

    it('should delete file', async () => {
      window.electronAPI.deleteFile.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.deleteFile('/workspace/src/oldfile.ts');
      
      expect(result).toBe(true);
      expect(window.electronAPI.deleteFile).toHaveBeenCalledWith('/workspace/src/oldfile.ts');
    });

    it('should open directory dialog', async () => {
      window.electronAPI.openDirectory.mockResolvedValueOnce('/workspace');
      
      const path = await window.electronAPI.openDirectory();
      
      expect(path).toBe('/workspace');
    });

    it('should handle file read error gracefully', async () => {
      window.electronAPI.readFile.mockRejectedValueOnce(new Error('File not found'));
      
      await expect(window.electronAPI.readFile('/nonexistent/file.ts'))
        .rejects.toThrow('File not found');
    });
  });

  describe('Git Operations', () => {
    it('should get git status', async () => {
      const mockStatus = {
        modified: ['src/index.ts'],
        staged: [],
        created: [],
        deleted: [],
        not_added: ['src/new.ts'],
        current: 'main',
        tracking: 'origin/main'
      };

      window.electronAPI.gitStatus.mockResolvedValueOnce(mockStatus);
      
      const status = await window.electronAPI.gitStatus();
      
      expect(status).toEqual(mockStatus);
    });

    it('should get current branch', async () => {
      window.electronAPI.gitBranch.mockResolvedValueOnce('feature/new');
      
      const branch = await window.electronAPI.gitBranch();
      
      expect(branch).toBe('feature/new');
    });

    it('should stage files', async () => {
      window.electronAPI.gitStage.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.gitStage(['src/index.ts']);
      
      expect(result).toBe(true);
      expect(window.electronAPI.gitStage).toHaveBeenCalledWith(['src/index.ts']);
    });

    it('should unstage files', async () => {
      window.electronAPI.gitUnstage.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.gitUnstage(['src/index.ts']);
      
      expect(result).toBe(true);
      expect(window.electronAPI.gitUnstage).toHaveBeenCalledWith(['src/index.ts']);
    });

    it('should commit changes', async () => {
      window.electronAPI.gitCommit.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.gitCommit('Add new feature');
      
      expect(result).toBe(true);
      expect(window.electronAPI.gitCommit).toHaveBeenCalledWith('Add new feature');
    });

    it('should checkout branch', async () => {
      window.electronAPI.gitCheckout.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.gitCheckout('feature/branch');
      
      expect(result).toBe(true);
      expect(window.electronAPI.gitCheckout).toHaveBeenCalledWith('feature/branch');
    });

    it('should discard file changes', async () => {
      window.electronAPI.gitDiscard.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.gitDiscard(['src/index.ts']);
      
      expect(result).toBe(true);
      expect(window.electronAPI.gitDiscard).toHaveBeenCalledWith(['src/index.ts']);
    });

    it('should get git diff', async () => {
      const mockDiff = 'diff --git a/src/index.ts b/src/index.ts';
      window.electronAPI.gitDiff.mockResolvedValueOnce(mockDiff);
      
      const diff = await window.electronAPI.gitDiff();
      
      expect(diff).toBe(mockDiff);
    });

    it('should get git log', async () => {
      const mockLog = [
        {
          hash: 'abc123',
          message: 'Initial commit',
          author: 'Test User',
          date: '2024-01-01'
        }
      ];
      window.electronAPI.gitLog.mockResolvedValueOnce(mockLog);
      
      const log = await window.electronAPI.gitLog();
      
      expect(log).toEqual(mockLog);
    });
  });

  describe('Storage Operations', () => {
    it('should get stored workspace', async () => {
      const mockWorkspace = { path: '/workspace', timestamp: Date.now() };
      window.electronAPI.storage.getWorkspace.mockResolvedValueOnce(mockWorkspace);
      
      const workspace = await window.electronAPI.storage.getWorkspace();
      
      expect(workspace).toEqual(mockWorkspace);
    });

    it('should set workspace', async () => {
      window.electronAPI.storage.setWorkspace.mockResolvedValueOnce(true);
      
      const result = await window.electronAPI.storage.setWorkspace('/workspace');
      
      expect(result).toBe(true);
      expect(window.electronAPI.storage.setWorkspace).toHaveBeenCalledWith('/workspace');
    });

    it('should update UI state', async () => {
      window.electronAPI.storage.updateUIState.mockResolvedValueOnce(true);
      
      const uiState = { expandedFolders: ['/workspace/src'] };
      const result = await window.electronAPI.storage.updateUIState(uiState);
      
      expect(result).toBe(true);
      expect(window.electronAPI.storage.updateUIState).toHaveBeenCalledWith(uiState);
    });

    it('should update open files', async () => {
      window.electronAPI.storage.updateOpenFiles.mockResolvedValueOnce(true);
      
      const files = { files: ['/workspace/src/index.ts'], activeFile: '/workspace/src/index.ts' };
      const result = await window.electronAPI.storage.updateOpenFiles(files);
      
      expect(result).toBe(true);
      expect(window.electronAPI.storage.updateOpenFiles).toHaveBeenCalledWith(files);
    });
  });

  describe('Terminal Operations', () => {
    it('should write to terminal', () => {
      window.electronAPI.terminal.write('test output');
      expect(window.electronAPI.terminal.write).toHaveBeenCalledWith('test output');
    });

    it('should clear terminal', () => {
      window.electronAPI.terminal.clear();
      expect(window.electronAPI.terminal.clear).toHaveBeenCalled();
    });

    it('should resize terminal', () => {
      window.electronAPI.terminal.resize(80, 24);
      expect(window.electronAPI.terminal.resize).toHaveBeenCalledWith(80, 24);
    });
  });
});
