import React, { useState, useRef, useEffect, createContext, useContext } from 'react';
import { useAppStore } from '../store/useAppStore';
import { FiSend, FiTrash2, FiSettings, FiAlertCircle } from 'react-icons/fi';
import ReactMarkdown from 'react-markdown';
import { SettingsPanel } from './SettingsPanel';
import { ElectronBridge, electronBridge } from '../../services/electronBridge';

// Context for dependency injection
const ElectronBridgeContext = createContext<ElectronBridge>(electronBridge);
export const useElectronBridge = () => useContext(ElectronBridgeContext);

export interface ChatPanelProps {
  bridge?: ElectronBridge;
}

export const ChatPanel: React.FC<ChatPanelProps> = ({ bridge }) => {
  const api = bridge || useElectronBridge();
  const { messages, addMessage, clearMessages, steeringContext, activeFile } = useAppStore();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAIInitialized, setIsAIInitialized] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    checkAIInitialization();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const checkAIInitialization = async () => {
    const initialized = await api.ai.isInitialized();
    setIsAIInitialized(initialized);
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = {
      id: Date.now().toString(),
      role: 'user' as const,
      content: input,
      timestamp: new Date().toISOString()
    };

    addMessage(userMessage);
    setInput('');
    setIsLoading(true);
    setError(null);

    try {
      const isInitialized = await api.ai.isInitialized();
      
      if (!isInitialized) {
        setShowSettings(true);
        throw new Error('AI not configured. Please set up your API key in settings.');
      }

      const chatMessages: ChatMessage[] = messages.map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content,
      })) as ChatMessage[];

      chatMessages.push({ role: 'user', content: input });

      const response = await api.ai.chat(chatMessages);

      if (response.error) {
        throw new Error(response.error);
      }

      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: response.content || 'No response from AI',
        timestamp: new Date().toISOString()
      });

      setIsAIInitialized(true);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to get AI response';
      setError(errorMessage);
      
      if (err instanceof Error && errorMessage.includes('not configured')) {
        setShowSettings(true);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const getContextSnippet = (): string => {
    if (activeFile) {
      return `Currently viewing: ${activeFile.split(/[/\\]/).pop()}`;
    }
    return 'No file currently open';
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>AI Assistant</h3>
        <div className="header-actions">
          {!isAIInitialized && (
            <button 
              className="config-warning"
              onClick={() => setShowSettings(true)}
              title="Configure AI"
            >
              <FiAlertCircle />
            </button>
          )}
          <button onClick={clearMessages} title="Clear chat"><FiTrash2 /></button>
          <button onClick={() => setShowSettings(true)} title="Settings"><FiSettings /></button>
        </div>
      </div>

      {error && (
        <div className="chat-error">
          <FiAlertCircle />
          <span>{error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <h4>Welcome to AgenticAI</h4>
            {!isAIInitialized ? (
              <div className="setup-prompt">
                <p>To get started, please configure your AI provider:</p>
                <button onClick={() => setShowSettings(true)}>
                  <FiSettings /> Configure AI
                </button>
              </div>
            ) : (
              <p>I can help you with:</p>
            )}
            <ul>
              <li>Create new files and components</li>
              <li>Review code for issues</li>
              <li>Manage your tasks</li>
              <li>Refactor and optimize code</li>
            </ul>
            <p className="hint">Try asking: "Create a new React component"</p>
            <p className="context-hint">{getContextSnippet()}</p>
          </div>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="message-role">{msg.role === 'user' ? 'You' : 'AI'}</div>
              <div className="message-content">
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              </div>
              <div className="message-time">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </div>
            </div>
          ))
        )}
        {isLoading && (
          <div className="message assistant">
            <div className="message-role">AI</div>
            <div className="message-content loading">
              <span>●</span><span>●</span><span>●</span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input">
        <textarea
          placeholder={isAIInitialized ? "Ask me anything..." : "Configure AI first..."}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
          disabled={!isAIInitialized}
        />
        <button 
          onClick={sendMessage} 
          disabled={!input.trim() || isLoading || !isAIInitialized}
        >
          <FiSend />
        </button>
      </div>

      <SettingsPanel 
        isOpen={showSettings} 
        onClose={() => {
          setShowSettings(false);
          checkAIInitialization();
        }} 
      />
    </div>
  );
};
