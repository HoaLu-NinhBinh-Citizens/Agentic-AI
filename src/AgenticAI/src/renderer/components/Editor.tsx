import React, { useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { useAppStore } from '../store/useAppStore';
import { FiX } from 'react-icons/fi';

export const EditorPanel: React.FC = () => {
  const { 
    activeFile, 
    openFiles, 
    setActiveFile, 
    removeOpenFile,
    workspacePath 
  } = useAppStore();
  
  const [content, setContent] = useState<string>('');
  const [isDirty, setIsDirty] = useState(false);

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

  const handleSave = async () => {
    if (activeFile && window.electronAPI) {
      await window.electronAPI.writeFile(activeFile, content);
      setIsDirty(false);
    }
  };

  const getFileName = (path: string) => path.split(/[/\\]/).pop() || path;
  
  const getLanguage = (path: string) => {
    const ext = path.split('.').pop()?.toLowerCase();
    const langMap: Record<string, string> = {
      'ts': 'typescript', 'tsx': 'typescript',
      'js': 'javascript', 'jsx': 'javascript',
      'py': 'python', 'json': 'json',
      'md': 'markdown', 'css': 'css', 'html': 'html'
    };
    return langMap[ext || ''] || 'plaintext';
  };

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
            language={getLanguage(activeFile)}
            value={content}
            onChange={handleEditorChange}
            theme="vs-dark"
            options={{
              fontSize: 14,
              fontFamily: 'Fira Code, Consolas, monospace',
              minimap: { enabled: true },
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true
            }}
          />
        ) : (
          <div className="no-file-open">
            <h2>AgenticAI</h2>
            <p>Open a folder and select a file to start editing</p>
          </div>
        )}
      </div>
    </div>
  );
};
