import { useState, useCallback, useEffect } from 'react';
import { Command } from '../../shared/types';

declare global {
  interface Window {
    electronAPI: {
      commands: {
        getAll: () => Promise<{ success: boolean; commands?: Command[] }>;
        execute: (commandId: string) => Promise<{ success: boolean; error?: string }>;
      };
    };
  }
}

interface UseCommandPaletteOptions {
  autoLoad?: boolean;
}

export interface CommandPaletteState {
  isOpen: boolean;
  commands: Command[];
  filteredCommands: Command[];
  recentCommands: string[];
  searchQuery: string;
  selectedIndex: number;
  isLoading: boolean;
  error: string | null;
}

export function useCommandPalette(options: UseCommandPaletteOptions = {}) {
  const { autoLoad = true } = options;

  const [state, setState] = useState<CommandPaletteState>({
    isOpen: false,
    commands: [],
    filteredCommands: [],
    recentCommands: [],
    searchQuery: '',
    selectedIndex: 0,
    isLoading: false,
    error: null,
  });

  // Load commands on mount
  useEffect(() => {
    if (autoLoad) {
      loadCommands();
    }
  }, [autoLoad]);

  const loadCommands = useCallback(async () => {
    if (!window.electronAPI?.commands) {
      // Use fallback commands
      setState(prev => ({
        ...prev,
        commands: getDefaultCommands(),
        filteredCommands: getDefaultCommands(),
      }));
      return;
    }

    setState(prev => ({ ...prev, isLoading: true, error: null }));

    try {
      const result = await window.electronAPI.commands.getAll();

      if (result.success && result.commands) {
        setState(prev => ({
          ...prev,
          commands: result.commands!,
          filteredCommands: result.commands!,
          isLoading: false,
        }));
      } else {
        // Use fallback commands
        setState(prev => ({
          ...prev,
          commands: getDefaultCommands(),
          filteredCommands: getDefaultCommands(),
          isLoading: false,
        }));
      }
    } catch (error) {
      setState(prev => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Failed to load commands',
        isLoading: false,
      }));
    }
  }, []);

  const open = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: true, searchQuery: '', selectedIndex: 0 }));
  }, []);

  const close = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: false, searchQuery: '', selectedIndex: 0 }));
  }, []);

  const toggle = useCallback(() => {
    setState(prev => ({
      ...prev,
      isOpen: !prev.isOpen,
      searchQuery: prev.isOpen ? '' : prev.searchQuery,
      selectedIndex: prev.isOpen ? 0 : prev.selectedIndex,
    }));
  }, []);

  const setSearchQuery = useCallback((query: string) => {
    const filtered = filterCommands(state.commands, query);

    setState(prev => ({
      ...prev,
      searchQuery: query,
      filteredCommands: filtered,
      selectedIndex: 0,
    }));
  }, [state.commands]);

  const setSelectedIndex = useCallback((index: number) => {
    setState(prev => ({
      ...prev,
      selectedIndex: Math.max(0, Math.min(index, prev.filteredCommands.length - 1)),
    }));
  }, []);

  const executeCommand = useCallback(async (commandId: string) => {
    // Add to recent commands
    setState(prev => {
      const recent = [commandId, ...prev.recentCommands.filter(id => id !== commandId)].slice(0, 10);
      return { ...prev, recentCommands: recent };
    });

    if (window.electronAPI?.commands) {
      try {
        const result = await window.electronAPI.commands.execute(commandId);
        if (!result.success) {
          setState(prev => ({ ...prev, error: result.error || 'Command execution failed' }));
          return false;
        }
        return true;
      } catch (error) {
        setState(prev => ({
          ...prev,
          error: error instanceof Error ? error.message : 'Command execution failed',
        }));
        return false;
      }
    }

    // Fallback: execute command directly if not available
    const command = state.commands.find(cmd => cmd.id === commandId);
    if (command) {
      close();
      return true;
    }

    return false;
  }, [state.commands, close]);

  const moveSelection = useCallback((direction: 'up' | 'down') => {
    setState(prev => {
      const maxIndex = prev.filteredCommands.length - 1;
      let newIndex = prev.selectedIndex;

      if (direction === 'up') {
        newIndex = prev.selectedIndex > 0 ? prev.selectedIndex - 1 : maxIndex;
      } else {
        newIndex = prev.selectedIndex < maxIndex ? prev.selectedIndex + 1 : 0;
      }

      return { ...prev, selectedIndex: newIndex };
    });
  }, []);

  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  return {
    ...state,
    open,
    close,
    toggle,
    setSearchQuery,
    setSelectedIndex,
    executeCommand,
    moveSelection,
    loadCommands,
    clearError,
  };
}

// Helper function to filter commands based on query
function filterCommands(commands: Command[], query: string): Command[] {
  if (!query.trim()) {
    return commands;
  }

  const lowerQuery = query.toLowerCase().trim();
  const queryWords = lowerQuery.split(/\s+/);

  return commands.filter(cmd => {
    const label = cmd.label.toLowerCase();
    const category = cmd.category.toLowerCase();
    const id = cmd.id.toLowerCase();

    return queryWords.every(word =>
      label.includes(word) ||
      category.includes(word) ||
      id.includes(word)
    );
  }).sort((a, b) => {
    // Prioritize exact matches
    const aExact = a.label.toLowerCase() === lowerQuery;
    const bExact = b.label.toLowerCase() === lowerQuery;
    if (aExact && !bExact) return -1;
    if (bExact && !aExact) return 1;

    // Then by label match position
    const aIndex = a.label.toLowerCase().indexOf(lowerQuery);
    const bIndex = b.label.toLowerCase().indexOf(lowerQuery);
    if (aIndex !== -1 && bIndex === -1) return -1;
    if (bIndex !== -1 && aIndex === -1) return 1;
    if (aIndex !== -1 && bIndex !== -1 && aIndex < bIndex) return -1;

    return 0;
  });
}

// Default commands when API is not available
function getDefaultCommands(): Command[] {
  return [
    { id: 'file.newFile', label: 'New File', shortcut: 'Ctrl+N', category: 'File' },
    { id: 'file.save', label: 'Save', shortcut: 'Ctrl+S', category: 'File' },
    { id: 'file.saveAll', label: 'Save All', shortcut: 'Ctrl+Shift+S', category: 'File' },
    { id: 'file.close', label: 'Close File', shortcut: 'Ctrl+W', category: 'File' },
    { id: 'edit.undo', label: 'Undo', shortcut: 'Ctrl+Z', category: 'Edit' },
    { id: 'edit.redo', label: 'Redo', shortcut: 'Ctrl+Y', category: 'Edit' },
    { id: 'edit.find', label: 'Find', shortcut: 'Ctrl+F', category: 'Edit' },
    { id: 'edit.replace', label: 'Find and Replace', shortcut: 'Ctrl+H', category: 'Edit' },
    { id: 'view.toggleSidebar', label: 'Toggle Sidebar', shortcut: 'Ctrl+B', category: 'View' },
    { id: 'view.toggleTerminal', label: 'Toggle Terminal', shortcut: 'Ctrl+`', category: 'View' },
    { id: 'ai.reviewCurrentFile', label: 'Review Current File', shortcut: 'Ctrl+Shift+R', category: 'AI' },
    { id: 'ai.fixAllIssues', label: 'Fix All Critical Issues', shortcut: 'Ctrl+Shift+F', category: 'AI' },
    { id: 'settings.open', label: 'Open Settings', shortcut: 'Ctrl+,', category: 'Settings' },
  ];
}

export default useCommandPalette;
