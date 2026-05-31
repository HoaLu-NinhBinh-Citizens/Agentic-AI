import React, { useState, useEffect } from 'react';
import { ScoreTile } from './components/ScoreTile';
import { WorkspaceTree } from './components/WorkspaceTree';
import { EditorPanel } from './components/EditorPanel';
import { StatusBar } from './components/StatusBar';
import { PanelLeftClose, PanelLeft, PanelRightClose, PanelRight } from 'lucide-react';

function App() {
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<string>('');
  const [backendConnected, setBackendConnected] = useState(false);
  const [sidebarVisible, setSidebarVisible] = useState(true);
  const [gitBranch, setGitBranch] = useState('');

  useEffect(() => {
    async function checkBackend() {
      try {
        const backendUrl = await window.electronAPI?.getBackendUrl();
        if (backendUrl) {
          const response = await fetch(`${backendUrl}/health`);
          setBackendConnected(response.ok);
        }
      } catch {
        setBackendConnected(false);
      }
    }
    checkBackend();
    const interval = setInterval(checkBackend, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleFileSelect = (path: string, content: string) => {
    setSelectedFile(path);
    setFileContent(content);
  };

  const handleAppSelect = (appName: string) => {
    console.log('Selected app:', appName);
  };

  const getLanguageFromPath = (path: string): string => {
    const ext = path.substring(path.lastIndexOf('.'));
    const langMap: Record<string, string> = {
      '.py': 'Python',
      '.ts': 'TypeScript',
      '.tsx': 'TypeScript React',
      '.js': 'JavaScript',
      '.jsx': 'JavaScript',
      '.json': 'JSON',
      '.yaml': 'YAML',
      '.yml': 'YAML',
      '.md': 'Markdown',
      '.sh': 'Shell',
      '.bash': 'Bash',
      '.c': 'C',
      '.cpp': 'C++',
      '.h': 'C Header',
      '.rs': 'Rust',
      '.go': 'Go',
      '.html': 'HTML',
      '.xml': 'XML',
      '.css': 'CSS',
      '.txt': 'Plain Text',
    };
    return langMap[ext] || 'Plain Text';
  };

  return (
    <div className="h-screen flex flex-col bg-app-bg text-app-text overflow-hidden">
      {/* Title Bar / Score Tiles */}
      <ScoreTile onAppSelect={handleAppSelect} selectedApp="Cursor" />

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar */}
        <div
          className={`flex-shrink-0 transition-all duration-200 ${
            sidebarVisible ? 'w-64' : 'w-0'
          }`}
        >
          {sidebarVisible && (
            <WorkspaceTree onFileSelect={handleFileSelect} />
          )}
        </div>

        {/* Toggle Sidebar Button */}
        <button
          onClick={() => setSidebarVisible(!sidebarVisible)}
          className="flex-shrink-0 w-6 bg-app-sidebar border-r border-app-border flex items-center justify-center hover:bg-app-panel transition-colors"
          title={sidebarVisible ? 'Hide Sidebar' : 'Show Sidebar'}
        >
          {sidebarVisible ? (
            <PanelLeftClose className="w-4 h-4 text-app-text-dim" />
          ) : (
            <PanelRight className="w-4 h-4 text-app-text-dim" />
          )}
        </button>

        {/* Editor Panel */}
        <div className="flex-1 overflow-hidden">
          <EditorPanel
            filePath={selectedFile || undefined}
            content={fileContent}
            language={selectedFile ? getLanguageFromPath(selectedFile) : undefined}
          />
        </div>
      </div>

      {/* Status Bar */}
      <StatusBar
        filePath={selectedFile?.split(/[/\\]/).pop()}
        language={selectedFile ? getLanguageFromPath(selectedFile) : undefined}
        backendConnected={backendConnected}
        branch={gitBranch}
      />
    </div>
  );
}

export default App;
