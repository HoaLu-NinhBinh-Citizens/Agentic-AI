import React, { useState, useEffect, useCallback } from 'react';
import clsx from 'clsx';
import {
  Folder,
  FolderOpen,
  File,
  FileCode,
  FileText,
  ChevronRight,
  ChevronDown,
  RefreshCw,
} from 'lucide-react';

interface FileNode {
  name: string;
  path: string;
  isDir: boolean;
  children?: FileNode[];
}

interface WorkspaceTreeProps {
  onFileSelect?: (path: string, content: string) => void;
  workspaceRoot?: string;
}

const IGNORED_DIRS = new Set([
  '__pycache__', '.git', '.venv', 'venv', 'node_modules',
  '.idea', '.vscode', 'dist', 'build', '.pytest_cache',
  '.mypy_cache', '.ruff_cache', '.tox', 'htmlcov', '.next',
]);

const FILE_ICONS: Record<string, React.ReactNode> = {
  '.py': <FileCode className="w-4 h-4 text-yellow-400" />,
  '.ts': <FileCode className="w-4 h-4 text-blue-400" />,
  '.tsx': <FileCode className="w-4 h-4 text-blue-400" />,
  '.js': <FileCode className="w-4 h-4 text-yellow-300" />,
  '.jsx': <FileCode className="w-4 h-4 text-yellow-300" />,
  '.rs': <FileCode className="w-4 h-4 text-orange-400" />,
  '.go': <FileCode className="w-4 h-4 text-cyan-400" />,
  '.c': <FileCode className="w-4 h-4 text-green-400" />,
  '.cpp': <FileCode className="w-4 h-4 text-green-400" />,
  '.h': <FileCode className="w-4 h-4 text-purple-400" />,
  '.json': <FileCode className="w-4 h-4 text-amber-400" />,
  '.yaml': <FileCode className="w-4 h-4 text-pink-400" />,
  '.yml': <FileCode className="w-4 h-4 text-pink-400" />,
  '.md': <FileText className="w-4 h-4 text-gray-400" />,
  '.txt': <FileText className="w-4 h-4 text-gray-400" />,
};

function getFileIcon(filename: string): React.ReactNode {
  const ext = filename.substring(filename.lastIndexOf('.'));
  return FILE_ICONS[ext] || <File className="w-4 h-4 text-app-text-dim" />;
}

function TreeNode({
  node,
  depth,
  expandedPaths,
  selectedPath,
  onToggle,
  onSelect,
}: {
  node: FileNode;
  depth: number;
  expandedPaths: Set<string>;
  selectedPath: string | null;
  onToggle: (path: string) => void;
  onSelect: (node: FileNode) => void;
}) {
  const isExpanded = expandedPaths.has(node.path);
  const isSelected = selectedPath === node.path;

  const handleClick = async () => {
    if (node.isDir) {
      onToggle(node.path);
    } else {
      onSelect(node);
    }
  };

  return (
    <div>
      <button
        onClick={handleClick}
        className={clsx(
          'flex items-center gap-1 w-full px-2 py-1 text-sm rounded hover:bg-app-panel transition-colors text-left',
          isSelected && 'bg-app-selection text-app-accent'
        )}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
      >
        {node.isDir ? (
          <>
            {isExpanded ? (
              <ChevronDown className="w-3 h-3 text-app-text-dim" />
            ) : (
              <ChevronRight className="w-3 h-3 text-app-text-dim" />
            )}
            {isExpanded ? (
              <FolderOpen className="w-4 h-4 text-app-accent-yellow" />
            ) : (
              <Folder className="w-4 h-4 text-app-accent-yellow" />
            )}
          </>
        ) : (
          <>
            <span className="w-3" />
            {getFileIcon(node.name)}
          </>
        )}
        <span className="truncate text-app-text">{node.name}</span>
      </button>
      {node.isDir && isExpanded && node.children && (
        <div>
          {node.children.map((child) => (
            <TreeNode
              key={child.path}
              node={child}
              depth={depth + 1}
              expandedPaths={expandedPaths}
              selectedPath={selectedPath}
              onToggle={onToggle}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function WorkspaceTree({ onFileSelect, workspaceRoot }: WorkspaceTreeProps) {
  const [rootNode, setRootNode] = useState<FileNode | null>(null);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDirectory = useCallback(async (path: string): Promise<FileNode[]> => {
    try {
      const response = await window.electronAPI?.readDir(path);
      if (!response) return [];
      
      return response
        .filter((item: { name: string; isDir: boolean }) => {
          if (item.isDir) return !IGNORED_DIRS.has(item.name) && !item.name.startsWith('.');
          return !item.name.startsWith('.');
        })
        .sort((a: { name: string; isDir: boolean }, b: { name: string; isDir: boolean }) => {
          if (a.isDir !== b.isDir) return a.isDir ? -1 : 1;
          return a.name.localeCompare(b.name);
        })
        .map((item: { name: string; isDir: boolean; path: string }) => ({
          ...item,
          children: item.isDir ? undefined : undefined,
        }));
    } catch (err) {
      console.error('Error loading directory:', err);
      return [];
    }
  }, []);

  const loadTree = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const rootPath = workspaceRoot || await window.electronAPI?.getWorkspacePath() || '.';
      const children = await loadDirectory(rootPath);
      setRootNode({
        name: rootPath.split(/[/\\]/).pop() || 'workspace',
        path: rootPath,
        isDir: true,
        children,
      });
      setExpandedPaths(new Set([rootPath]));
    } catch (err) {
      setError('Failed to load workspace');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [workspaceRoot, loadDirectory]);

  useEffect(() => {
    loadTree();
  }, [loadTree]);

  const handleToggle = async (path: string) => {
    const newExpanded = new Set(expandedPaths);
    if (newExpanded.has(path)) {
      newExpanded.delete(path);
    } else {
      newExpanded.add(path);
      // Load children if not already loaded
      if (rootNode) {
        const updateNode = (node: FileNode): FileNode => {
          if (node.path === path && node.isDir && !node.children) {
            return { ...node };
          }
          if (node.children) {
            return {
              ...node,
              children: node.children.map(updateNode),
            };
          }
          return node;
        };
        // Trigger children load
        const children = await loadDirectory(path);
        const updateNodeWithChildren = (node: FileNode): FileNode => {
          if (node.path === path) {
            return { ...node, children };
          }
          if (node.children) {
            return {
              ...node,
              children: node.children.map(updateNodeWithChildren),
            };
          }
          return node;
        };
        setRootNode(prev => prev ? updateNodeWithChildren(prev) : null);
      }
    }
    setExpandedPaths(newExpanded);
  };

  const handleSelect = async (node: FileNode) => {
    if (node.isDir) return;
    setSelectedPath(node.path);
    try {
      const content = await window.electronAPI?.readFile(node.path);
      onFileSelect?.(node.path, content || '');
    } catch (err) {
      console.error('Error reading file:', err);
      onFileSelect?.(node.path, 'Error reading file');
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-app-text-dim">
        <RefreshCw className="w-5 h-5 animate-spin mr-2" />
        Loading workspace...
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4 text-app-accent-red text-sm">
        {error}
        <button
          onClick={loadTree}
          className="ml-2 underline hover:no-underline"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-app-sidebar">
      <div className="flex items-center justify-between px-3 py-2 border-b border-app-border">
        <span className="text-xs font-semibold text-app-text-dim uppercase tracking-wider">
          Explorer
        </span>
        <button
          onClick={loadTree}
          className="p-1 rounded hover:bg-app-panel text-app-text-dim hover:text-app-text transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-1">
        {rootNode && (
          <TreeNode
            node={rootNode}
            depth={0}
            expandedPaths={expandedPaths}
            selectedPath={selectedPath}
            onToggle={handleToggle}
            onSelect={handleSelect}
          />
        )}
      </div>
    </div>
  );
}
