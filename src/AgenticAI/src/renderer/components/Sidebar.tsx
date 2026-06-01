import React, { useEffect, useCallback, createContext, useContext } from 'react';
import { FiFolder, FiFolderPlus, FiFile, FiChevronRight, FiChevronDown, FiFilePlus } from 'react-icons/fi';
import { useAppStore } from '../store/useAppStore';
import { FileNode } from '../../shared/types';
import { ElectronBridge, electronBridge } from '../../services/electronBridge';

// Context for dependency injection
const ElectronBridgeContext = createContext<ElectronBridge>(electronBridge);
export const useElectronBridge = () => useContext(ElectronBridgeContext);

export interface SidebarProps {
  bridge?: ElectronBridge;
}

export const Sidebar: React.FC<SidebarProps> = ({ bridge }) => {
  const api = bridge || useElectronBridge();
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
    const path = await api.openDirectory();
    if (path) {
      setWorkspacePath(path);
      await api.storage.setWorkspace(path);
      loadDirectory(path);
      loadSteeringContext(path);
    }
  };

  const loadDirectory = async (dirPath: string) => {
    const entries = await api.readDirectory(dirPath);
    const fileTree = buildFileTree(entries, dirPath);
    setFiles(fileTree);
  };

  const loadSteeringContext = async (dirPath: string) => {
    if (api.steering) {
      const result = await api.steering.load(dirPath);
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
        const entries = await api.readDirectory(node.path);
        const children = buildFileTree(entries || [], node.path);
        setFiles(updateChildren(files, node.path, children));
      }
      
      toggleFolder(node.path);
      
      if (willBeOpen) {
        api.storage.updateUIState({
          expandedFolders: [...expandedFolders, node.path]
        });
      } else {
        api.storage.updateUIState({
          expandedFolders: expandedFolders.filter(p => p !== node.path)
        });
      }
    } else {
      setActiveFile(node.path);
      addOpenFile(node.path);
      
      const openFiles = useAppStore.getState().openFiles;
      await api.storage.updateOpenFiles?.({
        files: openFiles,
        activeFile: node.path
      });
    }
  }, [files, expandedFolders, toggleFolder, setFiles, setActiveFile, addOpenFile, api]);

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
    if (workspacePath) {
      const name = prompt('Enter file name:');
      if (name) {
        const filePath = `${workspacePath}/${name}`;
        await api.createFile(filePath);
        loadDirectory(workspacePath);
      }
    }
  };

  const createNewFolder = async () => {
    if (workspacePath) {
      const name = prompt('Enter folder name:');
      if (name) {
        const folderPath = `${workspacePath}/${name}`;
        await api.createDirectory(folderPath);
        loadDirectory(workspacePath);
      }
    }
  };

  useEffect(() => {
    const restoreWorkspace = async () => {
      const workspace = await api.storage.getWorkspace();
      if (workspace?.path) {
        setWorkspacePath(workspace.path);
        loadDirectory(workspace.path);
        loadSteeringContext(workspace.path);
      }
    };
    restoreWorkspace();
  }, []);

  useEffect(() => {
    if (workspacePath && files.length === 0) {
      loadDirectory(workspacePath);
    }
  }, [workspacePath]);

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

interface FileTreeNodeProps {
  node: FileNode;
  depth: number;
  onClick: (node: FileNode) => void;
}

const FileTreeNode: React.FC<FileTreeNodeProps> = ({ node, depth, onClick }) => {
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

export { FileTreeNode };
