import { useState, useCallback, useRef, useEffect } from 'react';
import { ChatMessage, SteeringContext } from '../../shared/types';
import { aiService, AIConfig } from '../../main-process/aiService';

export interface UseAIOptions {
  systemPrompt?: string;
  steeringContext?: SteeringContext;
}

export interface UseAIReturn {
  messages: ChatMessage[];
  isLoading: boolean;
  error: string | null;
  sendMessage: (content: string) => Promise<void>;
  clearMessages: () => void;
  setSystemPrompt: (prompt: string) => void;
  initialize: (config: AIConfig) => void;
  isInitialized: boolean;
}

export function useAI(options: UseAIOptions = {}): UseAIReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [systemPrompt, setSystemPrompt] = useState(options.systemPrompt || '');
  const [isInitialized, setIsInitialized] = useState(false);

  const messagesRef = useRef(messages);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const initialize = useCallback((config: AIConfig) => {
    try {
      aiService.initialize(config);
      setIsInitialized(aiService.isInitialized());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initialize AI service');
      setIsInitialized(false);
    }
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    if (isLoading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    };

    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);
    setError(null);

    try {
      if (!aiService.isInitialized()) {
        throw new Error('AI service not initialized. Please configure your API key.');
      }

      const aiMessages: Array<{ role: 'system' | 'user' | 'assistant'; content: string }> = [
        ...messagesRef.current.map(m => ({
          role: m.role as 'user' | 'assistant',
          content: m.content,
        })),
        { role: 'user', content },
      ];

      const fullResponse = await aiService.chat(
        aiMessages,
        systemPrompt || undefined,
        undefined
      );

      const assistantMessage: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: 'assistant',
        content: fullResponse.content,
        timestamp: new Date().toISOString(),
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to get AI response';
      setError(errorMessage);

      const errorResponse: ChatMessage = {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: `Error: ${errorMessage}\n\nPlease check your API key configuration.`,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errorResponse]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, systemPrompt]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return {
    messages,
    isLoading,
    error,
    sendMessage,
    clearMessages,
    setSystemPrompt,
    initialize,
    isInitialized,
  };
}

export function useStreamingAI(options: UseAIOptions = {}) {
  const [content, setContent] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isInitialized, setIsInitialized] = useState(false);

  const initialize = useCallback((config: AIConfig) => {
    try {
      aiService.initialize(config);
      setIsInitialized(aiService.isInitialized());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to initialize');
      setIsInitialized(false);
    }
  }, []);

  const streamMessage = useCallback(async (
    messages: Array<{ role: 'user' | 'assistant'; content: string }>,
    onChunk?: (chunk: string) => void
  ) => {
    if (isLoading) return;

    setIsLoading(true);
    setContent('');
    setError(null);

    try {
      if (!aiService.isInitialized()) {
        throw new Error('AI service not initialized');
      }

      const response = await aiService.chat(
        messages as any,
        options.systemPrompt,
        (chunk) => {
          setContent(prev => prev + chunk);
          onChunk?.(chunk);
        }
      );

      return response;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'Failed to stream response';
      setError(errorMessage);
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [isLoading, options.systemPrompt]);

  const clear = useCallback(() => {
    setContent('');
    setError(null);
  }, []);

  return {
    content,
    isLoading,
    error,
    streamMessage,
    clear,
    initialize,
    isInitialized,
  };
}
