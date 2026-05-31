import { FileNode } from '../../shared/types';

interface DirectoryEntry {
  name: string;
  path: string;
  isDirectory: boolean;
}

describe('File Utilities', () => {
  describe('buildFileTree', () => {
    const buildFileTree = (
      entries: DirectoryEntry[],
      basePath: string,
      expandedFolders: string[] = []
    ): FileNode[] => {
      return entries
        .filter(e => !e.name.startsWith('.') && e.name !== 'node_modules')
        .sort((a, b) => {
          if (a.isDirectory && !b.isDirectory) return -1;
          if (!a.isDirectory && b.isDirectory) return 1;
          return a.name.localeCompare(b.name);
        })
        .map(entry => ({
          name: entry.name,
          path: entry.path,
          isDirectory: entry.isDirectory,
          children: entry.isDirectory ? [] : undefined,
          isOpen: expandedFolders.includes(entry.path)
        }));
    };

    it('should filter out hidden files (starting with .)', () => {
      const entries: DirectoryEntry[] = [
        { name: '.hidden', path: '/test/.hidden', isDirectory: false },
        { name: 'visible.txt', path: '/test/visible.txt', isDirectory: false },
        { name: '.env', path: '/test/.env', isDirectory: false }
      ];
      
      const result = buildFileTree(entries, '/test');
      expect(result.length).toBe(1);
      expect(result[0].name).toBe('visible.txt');
    });

    it('should filter out node_modules', () => {
      const entries: DirectoryEntry[] = [
        { name: 'node_modules', path: '/test/node_modules', isDirectory: true },
        { name: 'src', path: '/test/src', isDirectory: true }
      ];
      
      const result = buildFileTree(entries, '/test');
      expect(result.length).toBe(1);
      expect(result[0].name).toBe('src');
    });

    it('should sort directories before files', () => {
      const entries: DirectoryEntry[] = [
        { name: 'file.txt', path: '/test/file.txt', isDirectory: false },
        { name: 'folder', path: '/test/folder', isDirectory: true },
        { name: 'a.txt', path: '/test/a.txt', isDirectory: false }
      ];
      
      const result = buildFileTree(entries, '/test');
      expect(result[0].name).toBe('folder');
      expect(result[1].name).toBe('a.txt');
      expect(result[2].name).toBe('file.txt');
    });

    it('should sort files alphabetically within their category', () => {
      const entries: DirectoryEntry[] = [
        { name: 'z.txt', path: '/test/z.txt', isDirectory: false },
        { name: 'a.txt', path: '/test/a.txt', isDirectory: false },
        { name: 'm.txt', path: '/test/m.txt', isDirectory: false }
      ];
      
      const result = buildFileTree(entries, '/test');
      expect(result[0].name).toBe('a.txt');
      expect(result[1].name).toBe('m.txt');
      expect(result[2].name).toBe('z.txt');
    });

    it('should set isOpen based on expanded folders', () => {
      const entries: DirectoryEntry[] = [
        { name: 'src', path: '/test/src', isDirectory: true }
      ];
      
      const result = buildFileTree(entries, '/test', ['/test/src']);
      expect(result[0].isOpen).toBe(true);
    });

    it('should set isOpen to false for non-expanded folders', () => {
      const entries: DirectoryEntry[] = [
        { name: 'src', path: '/test/src', isDirectory: true }
      ];
      
      const result = buildFileTree(entries, '/test', []);
      expect(result[0].isOpen).toBe(false);
    });

    it('should add children array for directories', () => {
      const entries: DirectoryEntry[] = [
        { name: 'src', path: '/test/src', isDirectory: true }
      ];
      
      const result = buildFileTree(entries, '/test');
      expect(result[0].children).toEqual([]);
      expect(result[0].isDirectory).toBe(true);
    });

    it('should not have children for files', () => {
      const entries: DirectoryEntry[] = [
        { name: 'index.ts', path: '/test/index.ts', isDirectory: false }
      ];
      
      const result = buildFileTree(entries, '/test');
      expect(result[0].children).toBeUndefined();
      expect(result[0].isDirectory).toBe(false);
    });

    it('should handle empty entries array', () => {
      const result = buildFileTree([], '/test');
      expect(result).toEqual([]);
    });

    it('should preserve path in file nodes', () => {
      const entries: DirectoryEntry[] = [
        { name: 'index.ts', path: '/workspace/src/index.ts', isDirectory: false }
      ];
      
      const result = buildFileTree(entries, '/workspace/src');
      expect(result[0].path).toBe('/workspace/src/index.ts');
    });
  });

  describe('updateChildren', () => {
    const updateChildren = (
      nodes: FileNode[],
      parentPath: string,
      children: FileNode[]
    ): FileNode[] => {
      return nodes.map(node => {
        if (node.path === parentPath) {
          return { ...node, children };
        }
        if (node.children) {
          return { ...node, children: updateChildren(node.children, parentPath, children) };
        }
        return node;
      });
    };

    it('should update children of matching node', () => {
      const nodes: FileNode[] = [
        {
          name: 'src',
          path: '/test/src',
          isDirectory: true,
          children: []
        }
      ];
      
      const children: FileNode[] = [
        { name: 'index.ts', path: '/test/src/index.ts', isDirectory: false }
      ];
      
      const result = updateChildren(nodes, '/test/src', children);
      expect(result[0].children).toEqual(children);
    });

    it('should recursively update nested children', () => {
      const nodes: FileNode[] = [
        {
          name: 'src',
          path: '/test/src',
          isDirectory: true,
          children: [
            {
              name: 'components',
              path: '/test/src/components',
              isDirectory: true,
              children: []
            }
          ]
        }
      ];
      
      const children: FileNode[] = [
        { name: 'Button.tsx', path: '/test/src/components/Button.tsx', isDirectory: false }
      ];
      
      const result = updateChildren(nodes, '/test/src/components', children);
      expect(result[0].children![0].children).toEqual(children);
    });

    it('should return unchanged nodes when no match found', () => {
      const nodes: FileNode[] = [
        { name: 'src', path: '/test/src', isDirectory: true, children: [] }
      ];
      
      const children: FileNode[] = [
        { name: 'index.ts', path: '/test/src/index.ts', isDirectory: false }
      ];
      
      const result = updateChildren(nodes, '/wrong/path', children);
      expect(result).toEqual(nodes);
    });

    it('should handle empty nodes array', () => {
      const children: FileNode[] = [
        { name: 'index.ts', path: '/test/index.ts', isDirectory: false }
      ];
      
      const result = updateChildren([], '/test', children);
      expect(result).toEqual([]);
    });
  });

  describe('path utilities', () => {
    const getFileName = (path: string): string => {
      return path.split(/[/\\]/).pop() || path;
    };

    const getLanguage = (path: string): string => {
      const ext = path.split('.').pop()?.toLowerCase();
      const langMap: Record<string, string> = {
        'ts': 'typescript',
        'tsx': 'typescript',
        'js': 'javascript',
        'jsx': 'javascript',
        'py': 'python',
        'json': 'json',
        'md': 'markdown',
        'css': 'css',
        'html': 'html'
      };
      return langMap[ext || ''] || 'plaintext';
    };

    it('should extract filename from path with forward slashes', () => {
      expect(getFileName('/workspace/src/index.ts')).toBe('index.ts');
    });

    it('should extract filename from path with backslashes', () => {
      expect(getFileName('C:\\Users\\project\\app.js')).toBe('app.js');
    });

    it('should return path itself if no separator found', () => {
      expect(getFileName('filename')).toBe('filename');
    });

    it('should detect TypeScript language', () => {
      expect(getLanguage('/test/file.ts')).toBe('typescript');
      expect(getLanguage('/test/file.tsx')).toBe('typescript');
    });

    it('should detect JavaScript language', () => {
      expect(getLanguage('/test/file.js')).toBe('javascript');
      expect(getLanguage('/test/file.jsx')).toBe('javascript');
    });

    it('should detect Python language', () => {
      expect(getLanguage('/test/file.py')).toBe('python');
    });

    it('should return plaintext for unknown extensions', () => {
      expect(getLanguage('/test/file.xyz')).toBe('plaintext');
    });

    it('should handle paths without extensions', () => {
      expect(getLanguage('/test/filename')).toBe('plaintext');
    });
  });
});
