import React, { useState, useEffect } from 'react';
import './App.css';
import { ActivityBar } from './components/ActivityBar';
import { Sidebar } from './components/Sidebar';
import { EditorPanel } from './components/Editor';
import { TaskPanel } from './components/TaskPanel';
import { ChatPanel } from './components/ChatPanel';
import { StatusBar } from './components/StatusBar';
import { CommandPalette } from './components/CommandPalette';
import { SettingsPanel } from './components/SettingsPanel';
import { TerminalPanel } from './components/TerminalPanel';
import { GitPanel } from './components/GitPanel';
import { SearchPanel } from './components/SearchPanel';
import { NexusLanding } from './components/NexusLanding';
import { ProcessPanel, ProcessLog } from './components/ProcessPanel';
import { InlineDiffView, DiffHunk } from './components/InlineDiffView';
import { TitleBar } from './components/TitleBar';
import { ExtensionsPanel } from './components/ExtensionsPanel';
import { useAppStore } from './store/useAppStore';

const App: React.FC = () => {
  const {
    activeSidebarView,
    setActiveSidebarView,
    isTerminalOpen,
    setTerminalOpen,
    isSettingsOpen,
    setSettingsOpen,
    activeFile,
    isLandingVisible,
    setLandingVisible,
  } = useAppStore();

  const [isCommandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [processes, setProcesses] = useState<ProcessLog[]>([]);
  const [diffHunks, setDiffHunks] = useState<DiffHunk[]>([]);

  // Global keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ctrl+Shift+P - Command Palette
      if (e.ctrlKey && e.shiftKey && (e.key === 'P' || e.key.toLowerCase() === 'p')) {
        e.preventDefault();
        setCommandPaletteOpen(true);
      }
      // Escape to close modals
      if (e.key === 'Escape') {
        setCommandPaletteOpen(false);
      }
      // Ctrl+` - Toggle Terminal
      if (e.ctrlKey && e.key === '`') {
        e.preventDefault();
        setTerminalOpen(!isTerminalOpen);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isTerminalOpen, setTerminalOpen]);

  // Diff hunk handlers
  const handleAcceptHunk = (id: string) => {
    setDiffHunks(prev => prev.map(h => h.id === id ? { ...h, status: 'accepted' as const } : h));
  };

  const handleRejectHunk = (id: string) => {
    setDiffHunks(prev => prev.map(h => h.id === id ? { ...h, status: 'rejected' as const } : h));
  };

  const handleAcceptAll = () => {
    setDiffHunks(prev => prev.map(h => ({ ...h, status: 'accepted' as const })));
  };

  const handleRejectAll = () => {
    setDiffHunks(prev => prev.map(h => ({ ...h, status: 'rejected' as const })));
  };

  const renderSidebarContent = () => {
    switch (activeSidebarView) {
      case 'explorer':
        return <Sidebar />;
      case 'search':
        return <SearchPanel />;
      case 'git':
        return <GitPanel />;
      case 'extensions':
        return <ExtensionsPanel />;
      case 'terminal':
        return <div className="terminal-sidebar"><TerminalPanel isOpen={true} onClose={() => setTerminalOpen(false)} onMinimize={() => setTerminalOpen(false)} /></div>;
      default:
        return <Sidebar />;
    }
  };

  const renderMainContent = () => {
    if (isLandingVisible) {
      return <NexusLanding onLaunchStudio={() => setLandingVisible(false)} />;
    }
    return (
      <>
        <ActivityBar />
        <div className="sidebar-container">
          {renderSidebarContent()}
        </div>
        <div className="editor-area">
          <EditorPanel />
          {isTerminalOpen && (
            <TerminalPanel
              isOpen={isTerminalOpen}
              onClose={() => setTerminalOpen(false)}
              onMinimize={() => setTerminalOpen(false)}
            />
          )}
        </div>
        <div className="right-panels">
          <ProcessPanel 
            processes={processes}
            onClear={() => setProcesses([])}
          />
          <InlineDiffView
            hunks={diffHunks}
            onAcceptHunk={handleAcceptHunk}
            onRejectHunk={handleRejectHunk}
            onAcceptAll={handleAcceptAll}
            onRejectAll={handleRejectAll}
            onViewAll={() => {}}
          />
          <ChatPanel />
        </div>
        <StatusBar />
      </>
    );
  };

  return (
    <div className="app-container">
      <TitleBar />
      {renderMainContent()}

      {/* Modals - Always render, visible when isLandingVisible is false */}
      {!isLandingVisible && (
        <CommandPalette
          isOpen={isCommandPaletteOpen}
          onClose={() => setCommandPaletteOpen(false)}
          onOpenFolder={() => {
            window.electronAPI?.openDirectory();
            setCommandPaletteOpen(false);
          }}
          onOpenSettings={() => {
            setSettingsOpen(true);
            setCommandPaletteOpen(false);
          }}
          onRunCodeReview={() => {
            console.log('Running code review on:', activeFile);
            setCommandPaletteOpen(false);
          }}
          onToggleTerminal={() => {
            setTerminalOpen(!isTerminalOpen);
            setCommandPaletteOpen(false);
          }}
          onShowGit={() => {
            setActiveSidebarView('git');
            setCommandPaletteOpen(false);
          }}
          onClearChat={() => {
            useAppStore.getState().clearMessages();
            setCommandPaletteOpen(false);
          }}
        />
      )}

      <SettingsPanel 
        isOpen={isSettingsOpen} 
        onClose={() => setSettingsOpen(false)} 
      />
    </div>
  );
};

export default App;
