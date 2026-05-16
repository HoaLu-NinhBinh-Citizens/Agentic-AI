import { useState, useRef, useEffect, useCallback } from 'react';
import { Card, Badge } from '@/components/ui';
import { chatApi, type ChatMessage } from '@/api/dashboard';

interface AgentChatPanelProps {
  onSendMessage?: (message: string) => void;
  messages?: ChatMessage[];
  isProcessing?: boolean;
  enableBackend?: boolean;
}

// Demo messages for fallback when backend is not available
const demoMessages: ChatMessage[] = [
  {
    id: '1',
    role: 'user',
    content: 'Explain the USART initialization flow',
    timestamp: new Date(Date.now() - 60000).toISOString(),
  },
  {
    id: '2',
    role: 'assistant',
    content: 'The USART initialization flow in this codebase follows the STM32 HAL pattern:\n\n1. `MX_USART2_UART_Init()` - Generated initialization\n2. Calls `HAL_UART_Init()` with `huart2` handle\n3. Internally calls `HAL_UART_MspInit()` for GPIO/clock setup\n\nKey registers configured:\n- `USART_CR1` - Word length, parity, enable\n- `USART_CR2` - Stop bits, clock config\n- `USART_BRR` - Baud rate divisor\n- `USART_CR3` - Flow control, DMA',
    timestamp: new Date(Date.now() - 55000).toISOString(),
    confidence: 0.92,
    reasoning: 'Based on static analysis of 15 USART-related files',
    sources: ['Src/usart.c', 'Src/main.c'],
  },
  {
    id: '3',
    role: 'user',
    content: 'What about DMA configuration for UART?',
    timestamp: new Date(Date.now() - 30000).toISOString(),
  },
  {
    id: '4',
    role: 'assistant',
    content: 'DMA for UART is configured in `HAL_UART_MspInit()`:\n\n1. Clock enable: `__HAL_RCC_DMA1_CLK_ENABLE()`\n2. DMA stream: `DMA1_Stream5` (RX), `DMA1_Stream6` (TX)\n3. Channel: `DMA_CHANNEL_4`\n4. Interrupt: `USART2_IRQn`\n\nConfiguration parameters:\n- Priority: `DMA_PRIORITY_MEDIUM`\n- Direction: `DMA_PERIPH_TO_MEMORY` (RX)\n- Mode: `DMA_NORMAL` (blocking) or `DMA_CIRCULAR` (streaming)\n\nFor streaming UART data, set `DMA_MODE_CIRCULAR` in the init struct.',
    timestamp: new Date(Date.now() - 25000).toISOString(),
    confidence: 0.88,
    reasoning: 'Found DMA configuration in 3 interrupt handlers and 2 init files',
    sources: ['Src/usart.c', 'Src/stm32f4xx_it.c'],
  },
];

export function AgentChatPanel({ 
  onSendMessage,
  messages,
  isProcessing: externalIsProcessing = false,
  enableBackend = true,
}: AgentChatPanelProps) {
  const [inputValue, setInputValue] = useState('');
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>(messages ?? demoMessages);
  const [showConfidence, setShowConfidence] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [localMessages]);

  // Load chat history from backend on mount
  useEffect(() => {
    if (enableBackend) {
      chatApi.getHistory(20)
        .then(({ history }) => {
          if (history.length > 0) {
            setLocalMessages(history);
          }
        })
        .catch(() => {
          // Backend not available, use demo messages
        });
    }
  }, [enableBackend]);

  const handleSend = useCallback(async () => {
    if (!inputValue.trim() || isProcessing) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue.trim(),
      timestamp: new Date().toISOString(),
    };

    setLocalMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsProcessing(true);
    setConnectionError(null);

    onSendMessage?.(userMessage.content);

    // If backend is enabled, call the API
    if (enableBackend) {
      try {
        const response = await chatApi.sendMessage(userMessage.content);
        
        const assistantMessage: ChatMessage = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: response.message,
          timestamp: new Date().toISOString(),
          confidence: response.success ? 0.85 : undefined,
        };

        setLocalMessages(prev => [...prev, assistantMessage]);
      } catch (error) {
        setConnectionError('Could not connect to agent backend. Using demo mode.');
        // Keep demo mode - no assistant response added
      }
    }

    setIsProcessing(false);
  }, [inputValue, isProcessing, enableBackend, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const getConfidenceColor = (confidence?: number) => {
    if (!confidence) return 'text-gray-400';
    if (confidence >= 0.9) return 'text-green-400';
    if (confidence >= 0.7) return 'text-yellow-400';
    return 'text-red-400';
  };

  const getConfidenceLabel = (confidence?: number) => {
    if (!confidence) return null;
    if (confidence >= 0.9) return 'High';
    if (confidence >= 0.7) return 'Medium';
    return 'Low';
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-medium text-white">AI Agent Chat</h3>
          {isProcessing && (
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              <span className="text-sm text-gray-400">Processing...</span>
            </div>
          )}
          {!isProcessing && connectionError && (
            <span className="text-xs text-yellow-400" title={connectionError}>
              Demo Mode
            </span>
          )}
          {!isProcessing && !connectionError && (
            <span className="w-2 h-2 rounded-full bg-green-500" title="Connected" />
          )}
        </div>
        <div className="flex items-center gap-2">
          {connectionError && (
            <button
              onClick={() => setConnectionError(null)}
              className="px-2 py-1 text-xs bg-gray-700 text-gray-400 rounded hover:text-white"
              title="Retry connection"
            >
              Retry
            </button>
          )}
          <button
            onClick={() => setShowConfidence(!showConfidence)}
            className={`px-3 py-1 text-xs rounded transition-colors ${
              showConfidence 
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-700 text-gray-400 hover:text-white'
            }`}
          >
            {showConfidence ? 'Hide' : 'Show'} Confidence
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {localMessages.map((message) => (
          <div
            key={message.id}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`
                max-w-[80%] rounded-lg p-4
                ${message.role === 'user' 
                  ? 'bg-blue-600 text-white' 
                  : message.role === 'system'
                    ? 'bg-yellow-900/30 text-yellow-200 border border-yellow-700'
                    : 'bg-gray-800 text-gray-200'
                }
              `}
            >
              {/* Role Label */}
              <div className="flex items-center gap-2 mb-2">
                {message.role === 'assistant' && (
                  <span className="text-xs text-blue-400 font-medium">AI Agent</span>
                )}
                {message.role === 'system' && (
                  <span className="text-xs text-yellow-400 font-medium">System</span>
                )}
                {message.role === 'user' && (
                  <span className="text-xs text-blue-200 font-medium">You</span>
                )}
                
                {/* Confidence Badge */}
                {message.role === 'assistant' && showConfidence && message.confidence && (
                  <Badge 
                    variant={
                      message.confidence >= 0.9 ? 'success' : 
                      message.confidence >= 0.7 ? 'warning' : 'error'
                    }
                    className="ml-auto"
                  >
                    {getConfidenceLabel(message.confidence)} ({Math.round(message.confidence * 100)}%)
                  </Badge>
                )}
              </div>

              {/* Content */}
              <div className="text-sm whitespace-pre-wrap">
                {message.content}
              </div>

              {/* Reasoning */}
              {message.role === 'assistant' && showConfidence && message.reasoning && (
                <div className="mt-3 pt-3 border-t border-gray-700">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-xs text-gray-500">Reasoning:</span>
                    <span className="text-xs text-gray-400">{message.reasoning}</span>
                  </div>
                </div>
              )}

              {/* Sources */}
              {message.sources && message.sources.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-700">
                  <span className="text-xs text-gray-500">Sources: </span>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {message.sources.map((source, i) => (
                      <Badge key={i} variant="default" className="text-xs">
                        {source.split('/').pop()}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* Timestamp */}
              <div className="mt-2 text-xs text-gray-500 text-right">
                {new Date(message.timestamp).toLocaleTimeString()}
              </div>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-700">
        <div className="flex gap-3">
          <textarea
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about the codebase..."
            className="
              flex-1 bg-gray-800 text-white rounded-lg px-4 py-3 
              resize-none h-20 text-sm
              placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500
            "
            disabled={isProcessing}
          />
          <button
            onClick={handleSend}
            disabled={!inputValue.trim() || isProcessing}
            className="
              px-6 py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 
              disabled:text-gray-500 text-white rounded-lg font-medium
              transition-colors self-end
            "
          >
            Send
          </button>
        </div>
        <div className="mt-2 flex items-center gap-4 text-xs text-gray-500">
          <span>Press Enter to send, Shift+Enter for newline</span>
        </div>
      </div>
    </div>
  );
}
