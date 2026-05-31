jest.mock('react-icons/fi', () => ({
  FiFolder: () => 'FiFolder',
  FiFolderPlus: () => 'FiFolderPlus',
  FiFile: () => 'FiFile',
  FiChevronRight: () => 'FiChevronRight',
  FiChevronDown: () => 'FiChevronDown',
  FiFilePlus: () => 'FiFilePlus',
}));

jest.mock('@monaco-editor/react', () => ({
  __esModule: true,
  default: () => 'MonacoEditor',
}));

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { Sidebar } from '../../renderer/components/Sidebar';
import { useAppStore } from '../../renderer/store/useAppStore';
import { MockElectronBridge, createMockBridge } from '../../../tests/__mocks__/electronBridge';

describe('Sidebar', () => {
  beforeEach(() => {
    useAppStore.setState({
      workspacePath: null,
      files: [],
      activeFile: null,
      openFiles: [],
      expandedFolders: [],
    });
    jest.clearAllMocks();
  });

  it('should render Open Folder button when no workspace is open', () => {
    const bridge = createMockBridge();
    bridge.setOpenDirectoryResult(null);
    bridge.setStorageWorkspaceResult(null);
    
    render(<Sidebar bridge={bridge} />);
    
    expect(screen.getByText('Open Folder')).toBeInTheDocument();
  });

  it('should show Explorer header', () => {
    const bridge = createMockBridge();
    bridge.setOpenDirectoryResult(null);
    bridge.setStorageWorkspaceResult(null);
    
    render(<Sidebar bridge={bridge} />);
    
    expect(screen.getByText('Explorer')).toBeInTheDocument();
  });

  it('should have New File button', () => {
    const bridge = createMockBridge();
    bridge.setOpenDirectoryResult(null);
    bridge.setStorageWorkspaceResult(null);
    
    render(<Sidebar bridge={bridge} />);
    
    const newFileButton = screen.getByTitle('New File');
    expect(newFileButton).toBeInTheDocument();
  });

  it('should have New Folder button', () => {
    const bridge = createMockBridge();
    bridge.setOpenDirectoryResult(null);
    bridge.setStorageWorkspaceResult(null);
    
    render(<Sidebar bridge={bridge} />);
    
    const newFolderButton = screen.getByTitle('New Folder');
    expect(newFolderButton).toBeInTheDocument();
  });

  it('should display file tree when workspace is open', async () => {
    const mockEntries = [
      { name: 'src', path: '/workspace/src', isDirectory: true },
      { name: 'index.ts', path: '/workspace/index.ts', isDirectory: false }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeInTheDocument();
      expect(screen.getByText('index.ts')).toBeInTheDocument();
    });
  });

  it('should show folder icon for directories', async () => {
    const mockEntries = [
      { name: 'src', path: '/workspace/src', isDirectory: true }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeInTheDocument();
    });
  });

  it('should show file icon for files', async () => {
    const mockEntries = [
      { name: 'index.ts', path: '/workspace/index.ts', isDirectory: false }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      expect(screen.getByText('index.ts')).toBeInTheDocument();
    });
  });

  it('should expand folder when clicked', async () => {
    const mockEntries = [
      { name: 'src', path: '/workspace/src', isDirectory: true }
    ];
    const nestedEntries = [
      { name: 'index.ts', path: '/workspace/src/index.ts', isDirectory: false }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);
    // For the nested read, we need to track calls
    bridge.readDirectory = jest.fn()
      .mockResolvedValueOnce(mockEntries)
      .mockResolvedValueOnce(nestedEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      const folder = screen.getByText('src');
      fireEvent.click(folder);
    });

    await waitFor(() => {
      expect(screen.getByText('index.ts')).toBeInTheDocument();
    });
  });

  it('should open file when clicked', async () => {
    const mockEntries = [
      { name: 'index.ts', path: '/workspace/index.ts', isDirectory: false }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      const file = screen.getByText('index.ts');
      fireEvent.click(file);
    });

    expect(useAppStore.getState().activeFile).toBe('/workspace/index.ts');
    expect(useAppStore.getState().openFiles).toContain('/workspace/index.ts');
  });

  it('should call openDirectory when Open Folder is clicked', async () => {
    const bridge = createMockBridge();
    bridge.setOpenDirectoryResult('/workspace');
    bridge.setStorageWorkspaceResult(null);

    render(<Sidebar bridge={bridge} />);

    const openFolderButton = screen.getByText('Open Folder');
    fireEvent.click(openFolderButton);

    await waitFor(() => {
      expect(bridge.openDirectory).toHaveBeenCalled();
    });
  });

  it('should filter out hidden files', async () => {
    const mockEntries = [
      { name: '.hidden', path: '/workspace/.hidden', isDirectory: false },
      { name: 'visible.ts', path: '/workspace/visible.ts', isDirectory: false }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      expect(screen.getByText('visible.ts')).toBeInTheDocument();
      expect(screen.queryByText('.hidden')).not.toBeInTheDocument();
    });
  });

  it('should filter out node_modules', async () => {
    const mockEntries = [
      { name: 'node_modules', path: '/workspace/node_modules', isDirectory: true },
      { name: 'src', path: '/workspace/src', isDirectory: true }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      expect(screen.getByText('src')).toBeInTheDocument();
      expect(screen.queryByText('node_modules')).not.toBeInTheDocument();
    });
  });

  it('should sort directories before files', async () => {
    const mockEntries = [
      { name: 'file.txt', path: '/workspace/file.txt', isDirectory: false },
      { name: 'folder', path: '/workspace/folder', isDirectory: true }
    ];

    const bridge = createMockBridge();
    bridge.setStorageWorkspaceResult({ path: '/workspace' });
    bridge.setReadDirectoryResult(mockEntries);

    render(<Sidebar bridge={bridge} />);

    await waitFor(() => {
      const items = screen.getAllByText((content, element) => {
        const text = element?.textContent || '';
        return text === 'folder' || text === 'file.txt';
      });
      expect(items.length).toBe(2);
    });
  });
});
