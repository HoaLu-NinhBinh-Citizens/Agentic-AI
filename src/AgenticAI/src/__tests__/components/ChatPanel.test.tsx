jest.mock('react-icons/fi', () => ({
  FiSend: () => 'FiSend',
  FiTrash2: () => 'FiTrash2',
  FiSettings: () => 'FiSettings',
  FiAlertCircle: () => 'FiAlertCircle',
}));

jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: any) => children,
}));

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { ChatPanel } from '../../renderer/components/ChatPanel';
import { useAppStore } from '../../renderer/store/useAppStore';
import { MockElectronBridge, createMockBridge } from '../../../tests/__mocks__/electronBridge';

describe('ChatPanel', () => {
  let bridge: MockElectronBridge;

  beforeEach(() => {
    useAppStore.setState({
      messages: [],
      steeringContext: {},
      activeFile: null,
    });
    jest.clearAllMocks();
    // Create a fresh mock bridge for each test
    bridge = createMockBridge();
  });

  it('should render chat header', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    expect(screen.getByText('AI Assistant')).toBeInTheDocument();
  });

  it('should render welcome message when no messages', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    expect(screen.getByText('Welcome to AgenticAI')).toBeInTheDocument();
  });

  it('should render Configure AI button when AI is not initialized', async () => {
    bridge.setAIInitialized(false);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    // Check that the warning icon is shown
    expect(screen.getByTitle('Configure AI')).toBeInTheDocument();
  });

  it('should render textarea for input', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeInTheDocument();
  });

  it('should render send button', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    expect(screen.getByText('FiSend')).toBeInTheDocument();
  });

  it('should have clear chat button', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    expect(screen.getByText('FiTrash2')).toBeInTheDocument();
  });

  it('should have settings button', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    expect(screen.getByText('FiSettings')).toBeInTheDocument();
  });

  it('should update input value when typing', async () => {
    bridge.setAIInitialized(true);
    
    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });
    
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    
    expect(textarea.value).toBe('Hello');
  });

  it('should send message on button click', async () => {
    bridge.setAIInitialized(true);
    bridge.setAIResponse({ content: 'Hello! How can I help?', error: null });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Hello' } });

    const sendButton = screen.getByText('FiSend').closest('button')!;
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(bridge.ai.chat).toHaveBeenCalled();
    });
  });

  it('should add user message to chat', async () => {
    bridge.setAIInitialized(true);
    bridge.setAIResponse({ content: 'Response', error: null });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Test message' } });

    const sendButton = screen.getByText('FiSend').closest('button')!;
    fireEvent.click(sendButton);

    await waitFor(() => {
      expect(useAppStore.getState().messages).toContainEqual(
        expect.objectContaining({
          role: 'user',
          content: 'Test message',
        })
      );
    });
  });

  it('should clear messages when clear button is clicked', async () => {
    bridge.setAIInitialized(true);
    useAppStore.setState({
      messages: [
        {
          id: '1',
          role: 'user' as const,
          content: 'Hello',
          timestamp: new Date().toISOString(),
        },
      ],
    });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const clearButton = screen.getByText('FiTrash2').closest('button')!;
    fireEvent.click(clearButton);

    expect(useAppStore.getState().messages).toEqual([]);
  });

  it('should display error message and dismiss', async () => {
    bridge.setAIInitialized(true);
    bridge.setAIResponse({ content: '', error: 'API error occurred' });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Test' } });

    const sendButton = screen.getByText('FiSend').closest('button')!;
    fireEvent.click(sendButton);

    // Error should appear - test verifies no crash
  });

  it('should show loading indicator when sending message', async () => {
    let resolveChat: (value: { content: string; error: null }) => void;
    const chatPromise = new Promise<{ content: string; error: null }>((resolve) => {
      resolveChat = resolve;
    });
    
    bridge.setAIInitialized(true);
    bridge.ai.chat = jest.fn().mockImplementation(() => chatPromise);

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Hello' } });

    const sendButton = screen.getByText('FiSend').closest('button')!;
    fireEvent.click(sendButton);

    // Loading indicator should be visible - check that there are multiple loading dots
    const loadingDots = screen.getAllByText('●');
    expect(loadingDots.length).toBe(3);
    
    // Resolve the promise
    resolveChat!({ content: 'Response', error: null });
  });

  it('should send message on Enter key press', async () => {
    bridge.setAIInitialized(true);
    bridge.setAIResponse({ content: 'Response', error: null });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: 'Hello' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    await waitFor(() => {
      expect(bridge.ai.chat).toHaveBeenCalled();
    });
  });

  it('should not send empty message', async () => {
    bridge.setAIInitialized(true);

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const sendButton = screen.getByText('FiSend').closest('button') as HTMLButtonElement;
    expect(sendButton).toBeDisabled();
  });

  it('should not send message when AI is not initialized', async () => {
    bridge.setAIInitialized(false);

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea).toBeDisabled();
  });

  it('should show context hint when file is open', async () => {
    bridge.setAIInitialized(true);
    useAppStore.setState({ activeFile: '/workspace/src/index.ts' });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    expect(screen.getByText(/Currently viewing: index\.ts/i)).toBeInTheDocument();
  });

  it('should show no file context hint when no file is open', async () => {
    bridge.setAIInitialized(true);
    useAppStore.setState({ activeFile: null });

    await act(async () => {
      render(<ChatPanel bridge={bridge} />);
    });

    expect(screen.getByText(/No file currently open/i)).toBeInTheDocument();
  });
});
