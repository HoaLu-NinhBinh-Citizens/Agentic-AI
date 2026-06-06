import React, { useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { useAppStore } from '../store/useAppStore';
import { useInlineCompletion } from '../hooks/useInlineCompletion';
import { FiX, FiFolder } from 'react-icons/fi';

interface EditorPanelProps {
  onMount?: (editor: any) => void;
}

export const EditorPanel: React.FC<EditorPanelProps> = ({ onMount }) => {
  const {
    activeFile,
    openFiles,
    setActiveFile,
    removeOpenFile,
    setCursorPosition,
    recentWorkspaces,
  } = useAppStore();

  const [content, setContent] = useState<string>('');
  const [isDirty, setIsDirty] = useState(false);
  const [monacoInstance, setMonacoInstance] = useState<any>(null);

  const getLanguageFromPath = (path: string | null): string => {
    if (!path) return 'plaintext';
    const ext = path.split('.').pop()?.toLowerCase();
    const langMap: Record<string, string> = {
      'ts': 'typescript', 'tsx': 'typescript',
      'js': 'javascript', 'jsx': 'javascript',
      'py': 'python', 'json': 'json',
      'md': 'markdown', 'css': 'css', 'html': 'html'
    };
    return langMap[ext || ''] || 'plaintext';
  };

  const currentLanguage = getLanguageFromPath(activeFile);

  // Register AI ghost-text inline completion for the active language
  useInlineCompletion(monacoInstance, currentLanguage, {
    enabled: true,
    debounceMs: 350,
  });

  useEffect(() => {
    const loadFile = async () => {
      if (activeFile && window.electronAPI) {
        const fileContent = await window.electronAPI.readFile(activeFile);
        setContent(fileContent || '');
        setIsDirty(false);
      }
    };
    loadFile();
  }, [activeFile]);

  const handleEditorChange = (value: string | undefined) => {
    setContent(value || '');
    setIsDirty(true);
  };

  const handleEditorMount = (editor: any, monaco: any) => {
    setMonacoInstance(monaco);
    editor.onDidChangeCursorPosition((e: any) => {
      setCursorPosition({
        line: e.position.lineNumber,
        column: e.position.column,
      });
    });
    if (onMount) {
      onMount(editor);
    }
  };

  const handleSave = async () => {
    if (activeFile && window.electronAPI) {
      await window.electronAPI.writeFile(activeFile, content);
      setIsDirty(false);
    }
  };

  const handleOpenFolder = () => {
    window.electronAPI?.openDirectory();
  };

  const handleOpenRecent = (path: string): void => {
    if (window.electronAPI) {
      window.electronAPI.openDirectory().then(() => {
        console.log('Opened directory:', path);
      });
    }
  };

  const getFileName = (path: string) => path.split(/[/\\]/).pop() || path;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [content, activeFile]);

  return (
    <div className="editor-panel">
      {openFiles.length > 0 && (
        <div className="editor-tabs">
          {openFiles.map(file => (
            <div
              key={file}
              className={`editor-tab ${file === activeFile ? 'active' : ''}`}
              onClick={() => setActiveFile(file)}
            >
              <span>{getFileName(file)}</span>
              {file === activeFile && isDirty && <span className="dirty-indicator">●</span>}
              <button
                className="close-tab"
                onClick={(e) => { e.stopPropagation(); removeOpenFile(file); }}
              >
                <FiX />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="editor-content">
        {activeFile ? (
          <Editor
            height="100%"
            language={currentLanguage}
            value={content}
            onChange={handleEditorChange}
            onMount={handleEditorMount}
            theme="vs-dark"
            options={{
              fontSize: 14,
              fontFamily: 'Fira Code, Consolas, monospace',
              minimap: { enabled: true },
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              domReadOnly: false,
              cursorBlinking: 'smooth',
              cursorStyle: 'line',
              wordWrap: 'on',
              folding: true,
              renderLineHighlight: 'all',
              inlineSuggest: { enabled: true },
              suggest: { preview: true },
              scrollbar: {
                vertical: 'visible',
                horizontal: 'visible',
                useShadows: false,
                verticalScrollbarSize: 10,
                horizontalScrollbarSize: 10
              }
            }}
          />
        ) : (
          <div className="welcome-screen">
            <div className="welcome-content">
              <h1 className="welcome-title">AgenticAI</h1>
              <p className="welcome-subtitle">Open a folder to start coding</p>
              <button className="open-folder-btn" onClick={handleOpenFolder}>
                <FiFolder />
                <span>Open Folder</span>
              </button>

              {recentWorkspaces && recentWorkspaces.length > 0 && (
                <div className="recent-workspaces">
                  <h3>Recent Workspaces</h3>
                  <ul>
                    {recentWorkspaces.slice(0, 5).map((ws: string, idx: number) => (
                      <li key={idx} onClick={() => handleOpenRecent(ws)}>
                        <FiFolder />
                        <span>{ws}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
