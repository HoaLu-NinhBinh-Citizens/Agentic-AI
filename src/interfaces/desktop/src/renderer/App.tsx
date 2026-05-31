import React, { useState, useEffect, useCallback } from 'react';
import clsx from 'clsx';
import {
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
  Search,
  Command,
  X,
} from 'lucide-react';
import { WorkspaceTree } from './components/WorkspaceTree';
import { EditorPanel } from './components/EditorPanel';
import { TaskPanel } from './components/TaskPanel';
import { ChatPanel } from './components/ChatPanel';
import { StatusBar } from './components/StatusBar';
import { useAgenticStore, selectActiveTab } from './store/useAgenticStore';

// ============================================
// Command Palette Component
// ============================================

interface CommandItem {
  id: string;
  label: string;
  shortcut?: string;
  action: () => void;
}

function CommandPalette({ isOpen, onClose }: { isOpen: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const {
    toggleSidebar,
    toggleRightPanel,
    setActiveRightPanel,
    addMessage,
    setShowTaskForm,
  } = useAgenticStore();

  const commands: CommandItem[] = [
    { id: 'toggle-sidebar', label: 'Toggle Sidebar', shortcut: 'Ctrl+B', action: () => { toggleSidebar(); onClose(); } },
    { id: 'toggle-chat', label: 'Toggle Chat Panel', shortcut: 'Ctrl+Shift+C', action: () => { toggleRightPanel(); onClose(); } },
    { id: 'show-tasks', label: 'Show Tasks Panel', shortcut: 'Ctrl+Shift+T', action: () => { setActiveRightPanel('tasks'); onClose(); } },
    { id: 'show-spec', label: 'Show Spec Panel', shortcut: 'Ctrl+Shift+S', action: () => { setActiveRightPanel('spec'); onClose(); } },
    { id: 'show-plan', label: 'Show Plan Panel', action: () => { setActiveRightPanel('plan'); onClose(); } },
    { id: 'new-task', label: 'New Task', shortcut: 'Ctrl+T', action: () => { setActiveRightPanel('tasks'); /* setShowTaskForm(true); */ onClose(); } },
    { id: 'chat-help', label: 'Ask AI for Help', shortcut: 'Ctrl+/', action: () => { addMessage({ role: 'user', content: 'Tôi cần giúp đỡ với...' }); onClose(); } },
  ];

  const filteredCommands = commands.filter((cmd) =>
    cmd.label.toLowerCase().includes(query.toLowerCase())
  );

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === 'Escape') {
        onClose();
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, filteredCommands.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter' && filteredCommands[selectedIndex]) {
        e.preventDefault();
        filteredCommands[selectedIndex].action();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, filteredCommands, selectedIndex, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-lg bg-app-sidebar border border-app-border rounded-lg shadow-2xl overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-app-border">
          <Search className="w-5 h-5 text-app-text-dim" />
          <input
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelectedIndex(0); }}
            placeholder="Type a command..."
            className="flex-1 bg-transparent text-app-text placeholder:text-app-text-dim focus:outline-none"
            autoFocus
          />
          <kbd className="px-1.5 py-0.5 text-xs bg-app-panel rounded text-app-text-dim">ESC</kbd>
        </div>
        <div className="max-h-80 overflow-y-auto py-2">
          {filteredCommands.length === 0 ? (
            <div className="px-4 py-8 text-center text-app-text-dim">No commands found</div>
          ) : (
            filteredCommands.map((cmd, idx) => (
              <button
                key={cmd.id}
                onClick={cmd.action}
                className={clsx(
                  'flex items-center justify-between w-full px-4 py-2 text-sm transition-colors',
                  idx === selectedIndex ? 'bg-app-panel text-app-text' : 'text-app-text-dim hover:bg-app-panel/50 hover:text-app-text'
                )}
              >
                <span>{cmd.label}</span>
                {cmd.shortcut && (
                  <kbd className="px-1.5 py-0.5 text-xs bg-app-bg rounded text-app-text-dim">{cmd.shortcut}</kbd>
                )}
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================
// App Component
// ============================================

function App() {
  const {
    sidebarVisible,
    toggleSidebar,
    rightPanelVisible,
    toggleRightPanel,
    activeRightPanel,
    setActiveRightPanel,
    commandPaletteOpen,
    setCommandPaletteOpen,
    backendConnected,
    setBackendConnected,
    setWorkspacePath,
    setSteeringFiles,
    workspacePath,
    tabs,
    activeTabId,
    openFile,
    updateTabContent,
    closeTab,
    setActiveTab,
  } = useAgenticStore();

  const activeTab = useAgenticStore(selectActiveTab);

  // Initialize workspace
  useEffect(() => {
    async function init() {
      try {
        // Get workspace path
        const path = await window.electronAPI?.getWorkspacePath();
        if (path) {
          setWorkspacePath(path);
        }

        // Load steering files
        const files = await window.electronAPI?.getSteeringFiles();
        if (files) {
          setSteeringFiles(files);
        }

        // Check backend connection
        const backendUrl = await window.electronAPI?.getBackendUrl();
        if (backendUrl) {
          try {
            const response = await fetch(`${backendUrl}/health`);
            setBackendConnected(response.ok);
          } catch {
            setBackendConnected(false);
          }
        }
      } catch (error) {
        console.error('Init error:', error);
      }
    }
    init();
  }, [setWorkspacePath, setSteeringFiles, setBackendConnected]);

  // Handle menu actions from main process
  useEffect(() => {
    window.electronAPI?.onMenuAction((action) => {
      switch (action) {
        case 'toggle-sidebar':
          toggleSidebar();
          break;
        case 'toggle-task-panel':
          setActiveRightPanel('tasks');
          toggleRightPanel();
          break;
        case 'toggle-chat':
          setActiveRightPanel('chat');
          toggleRightPanel();
          break;
        case 'toggle-chat-panel':
          toggleRightPanel();
          break;
        case 'new-spec':
          setActiveRightPanel('spec');
          break;
        case 'read-steering':
          setActiveRightPanel('tasks');
          break;
      }
    });
  }, [toggleSidebar, toggleRightPanel, setActiveRightPanel]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Command palette
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'p') {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      // Toggle sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        toggleSidebar();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [toggleSidebar, setCommandPaletteOpen]);

  // Handle file selection from workspace tree
  const handleFileSelect = async (path: string, content: string) => {
    openFile(path, content);
  };

  // Handle file save
  const handleSave = useCallback(async () => {
    if (!activeTab || !activeTab.modified) return;

    try {
      await window.electronAPI?.writeFile(activeTab.path, activeTab.content);
      // Mark as saved (modified: false)
      const tabId = activeTab.id;
      // We need to update the store to mark as not modified
    } catch (error) {
      console.error('Save error:', error);
    }
  }, [activeTab]);

  return (
    <div className="h-screen flex flex-col bg-app-bg text-app-text overflow-hidden">
      {/* Command Palette */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
      />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar - Explorer */}
        <div
          className={clsx(
            'flex-shrink-0 transition-all duration-200',
            sidebarVisible ? 'w-64' : 'w-0'
          )}
        >
          {sidebarVisible && <WorkspaceTree onFileSelect={handleFileSelect} />}
        </div>

        {/* Toggle Sidebar Button */}
        <button
          onClick={toggleSidebar}
          className="flex-shrink-0 w-6 bg-app-sidebar border-r border-app-border flex items-center justify-center hover:bg-app-panel transition-colors z-10"
          title={sidebarVisible ? 'Hide Sidebar (Ctrl+B)' : 'Show Sidebar (Ctrl+B)'}
        >
          {sidebarVisible ? (
            <PanelLeftClose className="w-4 h-4 text-app-text-dim" />
          ) : (
            <PanelLeft className="w-4 h-4 text-app-text-dim" />
          )}
        </button>

        {/* Editor Area with Tabs */}
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Editor Tabs */}
          {tabs.length > 0 && (
            <div className="flex items-center bg-app-panel border-b border-app-border overflow-x-auto">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={clsx(
                    'flex items-center gap-2 px-4 py-2 text-sm border-r border-app-border transition-colors group',
                    tab.id === activeTabId
                      ? 'bg-app-bg text-app-text'
                      : 'bg-app-panel text-app-text-dim hover:bg-app-bg hover:text-app-text'
                  )}
                >
                  <span className={clsx(tab.modified && 'w-2 h-2 rounded-full bg-app-accent')} />
                  <span className="truncate max-w-32">{tab.name}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(tab.id);
                    }}
                    className="p-0.5 rounded hover:bg-app-panel opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </button>
              ))}
            </div>
          )}

          {/* Editor Content */}
          <div className="flex-1 overflow-hidden">
            {activeTab ? (
              <EditorPanel
                filePath={activeTab.path}
                content={activeTab.content}
                language={activeTab.language}
                onChange={(content) => updateTabContent(activeTab.id, content)}
                onSave={handleSave}
              />
            ) : (
              <div className="h-full flex items-center justify-center bg-app-bg">
                <div className="text-center">
                  <Command className="w-16 h-16 mx-auto mb-4 text-app-text-dim opacity-30" />
                  <h2 className="text-xl font-semibold text-app-text mb-2">AgenticAI</h2>
                  <p className="text-sm text-app-text-dim mb-4">Select a file to edit or start chatting</p>
                  <div className="flex items-center justify-center gap-4 text-xs text-app-text-dim">
                    <span><kbd className="px-1.5 py-0.5 bg-app-panel rounded">Ctrl+P</kbd> Command Palette</span>
                    <span><kbd className="px-1.5 py-0.5 bg-app-panel rounded">Ctrl+B</kbd> Toggle Sidebar</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel Toggle */}
        <button
          onClick={toggleRightPanel}
          className="flex-shrink-0 w-6 bg-app-sidebar border-l border-app-border flex items-center justify-center hover:bg-app-panel transition-colors z-10"
          title={rightPanelVisible ? 'Hide Panel' : 'Show Panel'}
        >
          {rightPanelVisible ? (
            <PanelRightClose className="w-4 h-4 text-app-text-dim" />
          ) : (
            <PanelRight className="w-4 h-4 text-app-text-dim" />
          )}
        </button>

        {/* Right Panel - Task & Chat */}
        <div
          className={clsx(
            'flex-shrink-0 transition-all duration-200',
            rightPanelVisible ? 'w-80' : 'w-0'
          )}
        >
          {rightPanelVisible && (
            <div className="h-full flex flex-col">
              {/* Panel Type Toggle */}
              <div className="flex border-b border-app-border">
                <button
                  onClick={() => setActiveRightPanel('tasks')}
                  className={clsx(
                    'flex-1 py-2 text-xs font-medium transition-colors',
                    activeRightPanel === 'tasks'
                      ? 'bg-app-panel text-app-accent border-b-2 border-app-accent'
                      : 'bg-app-sidebar text-app-text-dim hover:text-app-text'
                  )}
                >
                  Tasks
                </button>
                <button
                  onClick={() => setActiveRightPanel('spec')}
                  className={clsx(
                    'flex-1 py-2 text-xs font-medium transition-colors',
                    activeRightPanel === 'spec'
                      ? 'bg-app-panel text-app-accent border-b-2 border-app-accent'
                      : 'bg-app-sidebar text-app-text-dim hover:text-app-text'
                  )}
                >
                  Spec
                </button>
                <button
                  onClick={() => setActiveRightPanel('chat')}
                  className={clsx(
                    'flex-1 py-2 text-xs font-medium transition-colors',
                    activeRightPanel === 'chat'
                      ? 'bg-app-panel text-app-accent border-b-2 border-app-accent'
                      : 'bg-app-sidebar text-app-text-dim hover:text-app-text'
                  )}
                >
                  Chat
                </button>
              </div>

              {/* Panel Content */}
              <div className="flex-1 overflow-hidden">
                {activeRightPanel === 'tasks' || activeRightPanel === 'spec' ? (
                  <TaskPanel />
                ) : (
                  <ChatPanel />
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Status Bar */}
      <StatusBar
        filePath={activeTab?.name}
        language={activeTab?.language}
        backendConnected={backendConnected}
        branch=""
      />
    </div>
  );
}

export default App;
