import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { StatusBar } from '../../renderer/components/StatusBar';
import { useAppStore } from '../../renderer/store/useAppStore';

describe('StatusBar', () => {
  beforeEach(() => {
    useAppStore.setState({
      aiConfig: null,
      activeFile: null,
      cursorPosition: null,
    });
    jest.clearAllMocks();
  });

  it('should render status bar', () => {
    render(<StatusBar />);
    
    const statusBar = document.querySelector('.status-bar');
    expect(statusBar).toBeInTheDocument();
  });

  it('should display AI not configured when no config', () => {
    render(<StatusBar />);
    
    expect(screen.getByText('AI Not Configured')).toBeInTheDocument();
  });

  it('should display git branch', () => {
    render(<StatusBar />);
    
    expect(screen.getByText('main')).toBeInTheDocument();
  });

  it('should display cursor position', () => {
    render(<StatusBar />);
    
    expect(screen.getByText(/Ln 1, Col 1/)).toBeInTheDocument();
  });

  it('should update cursor position when it changes', () => {
    useAppStore.setState({ cursorPosition: { line: 10, column: 5 } });
    
    render(<StatusBar />);
    
    expect(screen.getByText(/Ln 10, Col 5/)).toBeInTheDocument();
  });

  it('should display UTF-8 encoding', () => {
    render(<StatusBar />);
    
    expect(screen.getByText('UTF-8')).toBeInTheDocument();
  });

  it('should display Plain Text for no file', () => {
    useAppStore.setState({ activeFile: null });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Plain Text')).toBeInTheDocument();
  });

  it('should display language mode based on file extension', () => {
    useAppStore.setState({ activeFile: '/workspace/src/index.ts' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('TypeScript')).toBeInTheDocument();
  });

  it('should detect TypeScript React files', () => {
    useAppStore.setState({ activeFile: '/workspace/src/App.tsx' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('TypeScript React')).toBeInTheDocument();
  });

  it('should detect JavaScript files', () => {
    useAppStore.setState({ activeFile: '/workspace/src/app.js' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('JavaScript')).toBeInTheDocument();
  });

  it('should detect Python files', () => {
    useAppStore.setState({ activeFile: '/workspace/main.py' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Python')).toBeInTheDocument();
  });

  it('should detect Rust files', () => {
    useAppStore.setState({ activeFile: '/workspace/src/lib.rs' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Rust')).toBeInTheDocument();
  });

  it('should detect Go files', () => {
    useAppStore.setState({ activeFile: '/workspace/main.go' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Go')).toBeInTheDocument();
  });

  it('should detect Java files', () => {
    useAppStore.setState({ activeFile: '/workspace/src/Main.java' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Java')).toBeInTheDocument();
  });

  it('should detect JSON files', () => {
    useAppStore.setState({ activeFile: '/workspace/package.json' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('JSON')).toBeInTheDocument();
  });

  it('should detect Markdown files', () => {
    useAppStore.setState({ activeFile: '/workspace/README.md' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Markdown')).toBeInTheDocument();
  });

  it('should detect HTML files', () => {
    useAppStore.setState({ activeFile: '/workspace/index.html' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('HTML')).toBeInTheDocument();
  });

  it('should detect CSS files', () => {
    useAppStore.setState({ activeFile: '/workspace/styles.css' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('CSS')).toBeInTheDocument();
  });

  it('should display Ollama provider with model', () => {
    useAppStore.setState({
      aiConfig: {
        provider: 'ollama',
        ollamaModel: 'codellama',
      },
    });
    
    render(<StatusBar />);
    
    expect(screen.getByText(/Ollama: codellama/)).toBeInTheDocument();
  });

  it('should display OpenAI provider with model', () => {
    useAppStore.setState({
      aiConfig: {
        provider: 'openai',
        openaiModel: 'gpt-4',
      },
    });
    
    render(<StatusBar />);
    
    expect(screen.getByText(/OpenAI: gpt-4/)).toBeInTheDocument();
  });

  it('should display Anthropic provider with model', () => {
    useAppStore.setState({
      aiConfig: {
        provider: 'anthropic',
        anthropicModel: 'claude-3-5-sonnet',
      },
    });
    
    render(<StatusBar />);
    
    expect(screen.getByText(/Anthropic: claude-3-5-sonnet/)).toBeInTheDocument();
  });

  it('should fetch git branch on mount', async () => {
    window.electronAPI.gitBranch.mockResolvedValueOnce('feature/test');
    
    render(<StatusBar />);
    
    await waitFor(() => {
      expect(window.electronAPI.gitBranch).toHaveBeenCalled();
    });
  });

  it('should update git branch when returned from API', async () => {
    window.electronAPI.gitBranch.mockResolvedValueOnce('feature/new-branch');
    
    render(<StatusBar />);
    
    await waitFor(() => {
      expect(screen.getByText('feature/new-branch')).toBeInTheDocument();
    });
  });

  it('should have status-left and status-right sections', () => {
    render(<StatusBar />);
    
    const leftSection = document.querySelector('.status-left');
    const rightSection = document.querySelector('.status-right');
    
    expect(leftSection).toBeInTheDocument();
    expect(rightSection).toBeInTheDocument();
  });

  it('should display AI status on left side', () => {
    render(<StatusBar />);
    
    const aiStatus = document.querySelector('.ai-status');
    expect(aiStatus).toBeInTheDocument();
  });

  it('should display git branch on left side', () => {
    render(<StatusBar />);
    
    const gitBranch = document.querySelector('.git-branch');
    expect(gitBranch).toBeInTheDocument();
  });

  it('should display cursor position on right side', () => {
    render(<StatusBar />);
    
    const cursorPosition = document.querySelector('.cursor-position');
    expect(cursorPosition).toBeInTheDocument();
  });

  it('should display language mode on right side', () => {
    render(<StatusBar />);
    
    const languageMode = document.querySelector('.language-mode');
    expect(languageMode).toBeInTheDocument();
  });

  it('should handle unknown file extensions', () => {
    useAppStore.setState({ activeFile: '/workspace/file.xyz' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Plain Text')).toBeInTheDocument();
  });

  it('should handle files without extension', () => {
    useAppStore.setState({ activeFile: '/workspace/Makefile' });
    
    render(<StatusBar />);
    
    expect(screen.getByText('Plain Text')).toBeInTheDocument();
  });
});
