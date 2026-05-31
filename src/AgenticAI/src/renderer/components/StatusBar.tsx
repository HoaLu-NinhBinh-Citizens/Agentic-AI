import React, { useState, useEffect } from 'react';
import { useAppStore } from '../store/useAppStore';

export const StatusBar: React.FC = () => {
  const { aiConfig, activeFile, cursorPosition } = useAppStore();
  const [gitBranch, setGitBranch] = useState('main');

  useEffect(() => {
    const loadGitBranch = async () => {
      if (window.electronAPI?.gitBranch) {
        const branch = await window.electronAPI.gitBranch();
        if (branch) {
          setGitBranch(branch);
        }
      }
    };
    loadGitBranch();
  }, []);

  const getLanguageFromFile = (file: string | null): string => {
    if (!file) return 'Plain Text';
    const ext = file.split('.').pop()?.toLowerCase();
    const langMap: Record<string, string> = {
      ts: 'TypeScript',
      tsx: 'TypeScript React',
      js: 'JavaScript',
      jsx: 'JavaScript React',
      py: 'Python',
      rs: 'Rust',
      go: 'Go',
      java: 'Java',
      json: 'JSON',
      md: 'Markdown',
      html: 'HTML',
      css: 'CSS',
    };
    return langMap[ext || ''] || 'Plain Text';
  };

  const getProviderDisplay = (): string => {
    if (!aiConfig) return 'AI Not Configured';
    switch (aiConfig.provider) {
      case 'ollama':
        return `Ollama: ${aiConfig.ollamaModel || 'codellama'}`;
      case 'openai':
        return `OpenAI: ${aiConfig.openaiModel || 'gpt-4'}`;
      case 'anthropic':
        return `Anthropic: ${aiConfig.anthropicModel || 'claude-3-5-sonnet'}`;
      default:
        return 'AI Not Configured';
    }
  };

  return (
    <div className="status-bar">
      <div className="status-left">
        <span className="status-item ai-status" title="AI Provider">
          {getProviderDisplay()}
        </span>
        <span className="status-item git-branch" title="Git Branch">
          {gitBranch}
        </span>
      </div>
      <div className="status-right">
        <span className="status-item cursor-position" title="Cursor Position">
          Ln {cursorPosition?.line || 1}, Col {cursorPosition?.column || 1}
        </span>
        <span className="status-item language-mode" title="Language Mode">
          {getLanguageFromFile(activeFile)}
        </span>
        <span className="status-item encoding" title="Encoding">
          UTF-8
        </span>
      </div>
    </div>
  );
};
