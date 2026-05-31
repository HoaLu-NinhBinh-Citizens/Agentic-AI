import React, { useEffect, useRef, useCallback, useState } from 'react';
import hljs from 'highlight.js/lib/core';
import python from 'highlight.js/lib/languages/python';
import typescript from 'highlight.js/lib/languages/typescript';
import javascript from 'highlight.js/lib/languages/javascript';
import json from 'highlight.js/lib/languages/json';
import yaml from 'highlight.js/lib/languages/yaml';
import markdown from 'highlight.js/lib/languages/markdown';
import bash from 'highlight.js/lib/languages/bash';
import c from 'highlight.js/lib/languages/c';
import rust from 'highlight.js/lib/languages/rust';
import go from 'highlight.js/lib/languages/go';
import xml from 'highlight.js/lib/languages/xml';
import css from 'highlight.js/lib/languages/css';
import 'highlight.js/styles/github-dark.css';

hljs.registerLanguage('python', python);
hljs.registerLanguage('typescript', typescript);
hljs.registerLanguage('tsx', typescript);
hljs.registerLanguage('javascript', javascript);
hljs.registerLanguage('json', json);
hljs.registerLanguage('yaml', yaml);
hljs.registerLanguage('markdown', markdown);
hljs.registerLanguage('bash', bash);
hljs.registerLanguage('c', c);
hljs.registerLanguage('cpp', c);
hljs.registerLanguage('rust', rust);
hljs.registerLanguage('go', go);
hljs.registerLanguage('xml', xml);
hljs.registerLanguage('html', xml);
hljs.registerLanguage('css', css);

interface EditorPanelProps {
  filePath?: string;
  content?: string;
  language?: string;
  onChange?: (content: string) => void;
  onSave?: () => void;
}

function getLanguageFromPath(path: string): string {
  const ext = path.substring(path.lastIndexOf('.'));
  const langMap: Record<string, string> = {
    '.py': 'python',
    '.ts': 'typescript',
    '.tsx': 'tsx',
    '.js': 'javascript',
    '.jsx': 'javascript',
    '.json': 'json',
    '.yaml': 'yaml',
    '.yml': 'yaml',
    '.md': 'markdown',
    '.sh': 'bash',
    '.bash': 'bash',
    '.c': 'c',
    '.cpp': 'cpp',
    '.h': 'c',
    '.rs': 'rust',
    '.go': 'go',
    '.html': 'html',
    '.xml': 'xml',
    '.css': 'css',
  };
  return langMap[ext] || 'plaintext';
}

export function EditorPanel({ filePath, content = '', language, onChange, onSave }: EditorPanelProps) {
  const codeRef = useRef<HTMLElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(content);

  // Update highlight when content changes
  useEffect(() => {
    if (codeRef.current && content) {
      codeRef.current.removeAttribute('data-highlighted');
      codeRef.current.innerHTML = hljs.highlightAuto(content).value;
    }
  }, [content]);

  // Sync edit content
  useEffect(() => {
    setEditContent(content);
  }, [content]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        if (isEditing && onSave) {
          onSave();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isEditing, onSave]);

  const handleDoubleClick = useCallback(() => {
    if (filePath) {
      setIsEditing(true);
    }
  }, [filePath]);

  const handleBlur = useCallback(() => {
    if (isEditing && editContent !== content) {
      onChange?.(editContent);
    }
    setIsEditing(false);
  }, [isEditing, editContent, content, onChange]);

  const handleTextareaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newContent = e.target.value;
    setEditContent(newContent);
    
    // Update highlighted code
    if (codeRef.current) {
      codeRef.current.innerHTML = hljs.highlightAuto(newContent).value;
    }
  };

  if (!filePath) {
    return (
      <div className="h-full flex items-center justify-center bg-app-bg">
        <div className="text-center text-app-text-dim">
          <div className="text-4xl mb-4 opacity-50">📄</div>
          <p className="text-lg">Select a file to view</p>
          <p className="text-sm mt-2">Click on a file in the explorer to open it</p>
        </div>
      </div>
    );
  }

  const displayLang = language || getLanguageFromPath(filePath);
  const lines = content.split('\n');
  const fileName = filePath.split(/[/\\]/).pop() || filePath;

  return (
    <div className="h-full flex flex-col bg-app-bg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-app-panel border-b border-app-border">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-app-text">{fileName}</span>
          <span className="text-xs text-app-text-dim bg-app-bg px-2 py-0.5 rounded">
            {displayLang}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-app-text-dim">{lines.length} lines</span>
          {onChange && (
            <button
              onClick={() => setIsEditing(!isEditing)}
              className="text-xs text-app-accent hover:underline"
            >
              {isEditing ? 'Preview' : 'Edit'}
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto relative">
        {isEditing ? (
          // Editable textarea
          <div className="h-full flex">
            <div className="flex-shrink-0 py-3 pr-4 pl-4 text-right select-none bg-app-bg border-r border-app-border">
              <pre className="text-app-text-dim leading-6">
                {editContent.split('\n').map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </pre>
            </div>
            <textarea
              ref={textareaRef}
              value={editContent}
              onChange={handleTextareaChange}
              onBlur={handleBlur}
              className="flex-1 py-3 pl-4 pr-4 bg-app-bg text-app-text font-mono text-sm leading-6 resize-none focus:outline-none"
              spellCheck={false}
            />
          </div>
        ) : (
          // Read-only with syntax highlighting
          <div 
            className="flex min-h-full font-mono text-sm cursor-text"
            onDoubleClick={handleDoubleClick}
          >
            <div className="flex-shrink-0 py-3 pr-4 pl-4 text-right select-none bg-app-bg border-r border-app-border">
              <pre className="text-app-text-dim leading-6">
                {lines.map((_, i) => (
                  <div key={i}>{i + 1}</div>
                ))}
              </pre>
            </div>
            <pre className="flex-1 py-3 pl-4 pr-4 overflow-x-auto bg-app-bg">
              <code
                ref={codeRef}
                className={`language-${displayLang} text-app-text leading-6`}
              >
                {content}
              </code>
            </pre>
          </div>
        )}
      </div>

      {/* Edit Mode Indicator */}
      {isEditing && (
        <div className="px-4 py-2 bg-app-accent/20 border-t border-app-accent text-xs text-app-accent">
          Editing mode - Press ESC or click outside to save • Ctrl+S to save
        </div>
      )}
    </div>
  );
}
