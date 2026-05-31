import React, { useEffect, useCallback } from 'react';
import { FiFolder, FiFolderPlus, FiFile, FiChevronRight, FiChevronDown, FiFilePlus } from 'react-icons/fi';
import { useAppStore } from '../store/useAppStore';
import { FileNode } from '../../shared/types';

export const Sidebar: React.FC = () => {
  const { 
    workspacePath, 
    setWorkspacePath, 
    files, 
    setFiles, 
    toggleFolder,
    setActiveFile,
    addOpenFile,
    expandedFolders 
  } = useAppStore();

  const openDirectory = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.openDirectory();
      if (path) {
        setWorkspacePath(path);
        await window.electronAPI.storage.setWorkspace(path);
        loadDirectory(path);
        loadSteeringContext(path);
      }
    }
  };

  const loadDirectory = async (dirPath: string) => {
    if (window.electronAPI) {
      const entries = await window.electronAPI.readDirectory(dirPath);
      const fileTree = buildFileTree(entries, dirPath);
      setFiles(fileTree);
    }
  };

  const loadSteeringContext = async (dirPath: string) => {
    if (window.electronAPI?.steering) {
      const result = await window.electronAPI.steering.load(dirPath);
      if (result.success && result.context) {
        useAppStore.getState().setSteeringContext(result.context);
      }
    }
  };

  const buildFileTree = (entries: {name: string, path: string, isDirectory: boolean}[], _basePath: string): FileNode[] => {
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

  const handleFileClick = useCallback(async (node: FileNode) => {
    const willBeOpen = !node.isOpen;
    
    if (node.isDirectory) {
      if (willBeOpen && (!node.children || node.children.length === 0)) {
        const entries = await window.electronAPI?.readDirectory(node.path);
        const children = buildFileTree(entries || [], node.path);
        setFiles(updateChildren(files, node.path, children));
      }
      
      toggleFolder(node.path);
      
      if (window.electronAPI?.storage) {
        if (willBeOpen) {
          window.electronAPI.storage.updateUIState({
            expandedFolders: [...expandedFolders, node.path]
          });
        } else {
          window.electronAPI.storage.updateUIState({
            expandedFolders: expandedFolders.filter(p => p !== node.path)
          });
        }
      }
    } else {
      setActiveFile(node.path);
      addOpenFile(node.path);
      
      if (window.electronAPI?.storage) {
        const openFiles = useAppStore.getState().openFiles;
        window.electronAPI.storage.updateOpenFiles({
          files: openFiles,
          activeFile: node.path
        });
      }
    }
  }, [files, expandedFolders, toggleFolder, setFiles, setActiveFile, addOpenFile]);

  const updateChildren = (nodes: FileNode[], parentPath: string, children: FileNode[]): FileNode[] => {
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

  const createNewFile = async () => {
    if (workspacePath && window.electronAPI) {
      const name = prompt('Enter file name:');
      if (name) {
        const filePath = `${workspacePath}/${name}`;
        await window.electronAPI.createFile(filePath);
        loadDirectory(workspacePath);
      }
    }
  };

  const createNewFolder = async () => {
    if (workspacePath && window.electronAPI) {
      const name = prompt('Enter folder name:');
      if (name) {
        const folderPath = `${workspacePath}/${name}`;
        await window.electronAPI.createDirectory(folderPath);
        loadDirectory(workspacePath);
      }
    }
  };

  useEffect(() => {
    const restoreWorkspace = async () => {
      if (window.electronAPI?.storage) {
        const workspace = await window.electronAPI.storage.getWorkspace();
        if (workspace?.path) {
          setWorkspacePath(workspace.path);
          loadDirectory(workspace.path);
          loadSteeringContext(workspace.path);
        }
      }
    };
    restoreWorkspace();
  }, []);

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <span>Explorer</span>
        <div className="sidebar-actions">
          <button onClick={createNewFile} title="New File"><FiFilePlus /></button>
          <button onClick={createNewFolder} title="New Folder"><FiFolderPlus /></button>
        </div>
      </div>
      
      {!workspacePath ? (
        <div className="open-folder">
          <button onClick={openDirectory}>Open Folder</button>
        </div>
      ) : (
        <div className="file-tree">
          {files.map(node => (
            <FileTreeNode key={node.path} node={node} depth={0} onClick={handleFileClick} />
          ))}
        </div>
      )}
    </div>
  );
};

const FileTreeNode: React.FC<{node: FileNode; depth: number; onClick: (node: FileNode) => void}> = ({ node, depth, onClick }) => {
  return (
    <div>
      <div 
        className="file-tree-item" 
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={() => onClick(node)}
      >
        {node.isDirectory && (
          node.isOpen ? <FiChevronDown /> : <FiChevronRight />
        )}
        {node.isDirectory ? <FiFolder /> : <FiFile />}
        <span className="file-name">{node.name}</span>
      </div>
      {node.isDirectory && node.isOpen && node.children && (
        <div className="file-tree-children">
          {node.children.map(child => (
            <FileTreeNode key={child.path} node={child} depth={depth + 1} onClick={onClick} />
          ))}
        </div>
      )}
    </div>
  );
};
