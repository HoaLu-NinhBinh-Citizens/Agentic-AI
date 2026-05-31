import React, { useState, useRef, useEffect, useCallback } from 'react';
import clsx from 'clsx';
import {
  Send,
  Bot,
  User,
  Sparkles,
  Copy,
  CheckCheck,
  Loader2,
  Trash2,
  Code,
  FileText,
  Lightbulb,
} from 'lucide-react';
import { useAgenticStore, ChatMessage, Task } from '../store/useAgenticStore';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// ============================================
// ChatPanel - AI Chat Interface
// ============================================

interface CodeBlock {
  language: string;
  code: string;
  filePath?: string;
}

function parseCodeBlocks(content: string): Array<{ type: 'text' | 'code'; content: string; lang?: string; filePath?: string }> {
  const parts: Array<{ type: 'text' | 'code'; content: string; lang?: string; filePath?: string }> = [];
  const codeBlockRegex = /```(\w+)?(?::(\S+))?\n([\s\S]*?)```/g;
  
  let lastIndex = 0;
  let match;

  while ((match = codeBlockRegex.exec(content)) !== null) {
    // Add text before code block
    if (match.index > lastIndex) {
      const text = content.slice(lastIndex, match.index).trim();
      if (text) {
        parts.push({ type: 'text', content: text });
      }
    }

    // Add code block
    parts.push({
      type: 'code',
      lang: match[1] || 'text',
      filePath: match[2],
      content: match[3].trim(),
    });

    lastIndex = match.index + match[0].length;
  }

  // Add remaining text
  if (lastIndex < content.length) {
    const text = content.slice(lastIndex).trim();
    if (text) {
      parts.push({ type: 'text', content: text });
    }
  }

  return parts;
}

function CodeBlockView({ block }: { block: { type: 'code'; content: string; lang?: string; filePath?: string } }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(block.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="my-2 rounded-lg overflow-hidden border border-app-border bg-app-panel">
      <div className="flex items-center justify-between px-3 py-1.5 bg-app-bg border-b border-app-border">
        <div className="flex items-center gap-2">
          <Code className="w-3.5 h-3.5 text-app-text-dim" />
          <span className="text-xs text-app-text-dim font-mono">
            {block.lang || 'code'}
          </span>
          {block.filePath && (
            <span className="text-xs text-app-text-dim">
              → {block.filePath}
            </span>
          )}
        </div>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-0.5 text-xs text-app-text-dim hover:text-app-text transition-colors"
        >
          {copied ? (
            <>
              <CheckCheck className="w-3 h-3" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3 h-3" />
              Copy
            </>
          )}
        </button>
      </div>
      <pre className="p-3 overflow-x-auto text-sm font-mono">
        <code className="text-app-text">{block.content}</code>
      </pre>
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  const parts = parseCodeBlocks(content);

  return (
    <div className="text-sm leading-relaxed">
      {parts.map((part, idx) => (
        <React.Fragment key={idx}>
          {part.type === 'text' ? (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-inside mb-2 space-y-1">{children}</ol>,
                li: ({ children }) => <li className="text-app-text">{children}</li>,
                code: ({ children, className }) => {
                  const isInline = !className;
                  return isInline ? (
                    <code className="px-1.5 py-0.5 bg-app-panel rounded text-xs font-mono text-app-accent">
                      {children}
                    </code>
                  ) : (
                    <code className={className}>{children}</code>
                  );
                },
                pre: ({ children }) => <>{children}</>,
                h1: ({ children }) => <h1 className="text-lg font-bold mb-2 mt-3">{children}</h1>,
                h2: ({ children }) => <h2 className="text-base font-semibold mb-2 mt-3">{children}</h2>,
                h3: ({ children }) => <h3 className="text-sm font-semibold mb-1 mt-2">{children}</h3>,
                strong: ({ children }) => <strong className="font-semibold text-app-text">{children}</strong>,
                a: ({ href, children }) => (
                  <a href={href} className="text-app-accent hover:underline" target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {part.content}
            </ReactMarkdown>
          ) : (
            <CodeBlockView block={part} />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

interface MessageBubbleProps {
  message: ChatMessage;
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) {
    return (
      <div className="flex items-start gap-2 p-3 bg-app-panel/50 border border-app-border rounded-lg">
        <Sparkles className="w-4 h-4 text-app-accent flex-shrink-0 mt-0.5" />
        <MessageContent content={message.content} />
      </div>
    );
  }

  return (
    <div className={clsx('flex items-start gap-2', isUser ? 'flex-row-reverse' : '')}>
      <div
        className={clsx(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser ? 'bg-app-accent' : 'bg-app-panel border border-app-border'
        )}
      >
        {isUser ? (
          <User className="w-4 h-4 text-white" />
        ) : (
          <Bot className="w-4 h-4 text-app-accent" />
        )}
      </div>

      <div
        className={clsx(
          'flex-1 max-w-[85%] rounded-lg px-4 py-2',
          isUser
            ? 'bg-app-accent text-white'
            : 'bg-app-panel border border-app-border'
        )}
      >
        {message.isStreaming ? (
          <div className="flex items-center gap-2 text-app-text-dim">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Thinking...</span>
          </div>
        ) : (
          <MessageContent content={message.content} />
        )}
        
        <div
          className={clsx(
            'text-xs mt-1',
            isUser ? 'text-white/60' : 'text-app-text-dim'
          )}
        >
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}

// Quick actions
const QUICK_ACTIONS = [
  { icon: <Lightbulb className="w-4 h-4" />, label: 'Gợi ý cải thiện code', prompt: 'Phân tích code hiện tại và đề xuất cách cải thiện' },
  { icon: <Code className="w-4 h-4" />, label: 'Viết function mới', prompt: 'Tôi cần viết một function mới:' },
  { icon: <FileText className="w-4 h-4" />, label: 'Tạo spec mới', prompt: 'Tạo spec mới cho dự án:' },
  { icon: <Sparkles className="w-4 h-4" />, label: 'Phân tích yêu cầu', prompt: 'Phân tích yêu cầu và tạo task list' },
];

export function ChatPanel() {
  const {
    messages,
    addMessage,
    updateMessage,
    clearMessages,
    steeringFiles,
    currentSpec,
    tasks,
    workspacePath,
    addTask,
  } = useAgenticStore();

  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Welcome message
  useEffect(() => {
    if (messages.length === 0) {
      addMessage({
        role: 'assistant',
        content: `Xin chào! Tôi là **AgenticAI** - trợ lý lập trình thông minh.\n\nTôi có thể giúp bạn:\n- 📝 **Quản lý Spec & Tasks** - Tạo và theo dõi công việc\n- 💻 **Viết code** - Tạo function, module, hoặc toàn bộ ứng dụng\n- 🔍 **Phân tích code** - Review và đề xuất cải thiện\n- 📖 **Đọc steering files** - Hiểu cấu trúc và quy tắc dự án\n\nHiện tại tôi đã đọc **${steeringFiles.length}** steering files trong workspace.\n\nBạn cần tôi hỗ trợ gì?`,
      });
    }
  }, []);

  // Send message to AI
  const sendMessage = useCallback(async (message: string) => {
    if (!message.trim() || isLoading) return;

    // Add user message
    addMessage({ role: 'user', content: message.trim() });
    setInput('');
    setIsLoading(true);

    // Add streaming indicator
    const assistantMsgId = Date.now().toString();
    addMessage({ role: 'assistant', content: '', isStreaming: true });

    try {
      // Build context for AI
      const context = {
        workspacePath,
        steeringFiles: steeringFiles.map((f) => ({ name: f.name, path: f.path, content: f.content })),
        currentSpec: currentSpec ? { title: currentSpec.title, description: currentSpec.description } : undefined,
        currentTasks: tasks.map((t) => ({ id: t.id, title: t.title, status: t.status })),
        openFiles: [],
      };

      // Call AI
      const response = await window.electronAPI?.sendToAI(message, context);

      if (response) {
        // Update streaming message with response
        const lastMsgId = messages.length > 0 ? messages[messages.length - 1].id : assistantMsgId;
        updateMessage(lastMsgId, { content: response.message, isStreaming: false });

        // Add suggested tasks if any
        if (response.tasks && response.tasks.length > 0) {
          const taskDescriptions = response.tasks.map((t, i) => 
            `- Task ${i + 1}: **${t.title}**${t.description ? `: ${t.description}` : ''}`
          ).join('\n');

          setTimeout(() => {
            addMessage({
              role: 'assistant',
              content: `Tôi đề xuất các tasks sau:\n\n${taskDescriptions}\n\nBạn có muốn tôi thêm các tasks này vào danh sách?`,
            });
          }, 500);
        }

        // Handle code snippets if any
        if (response.codeSnippets && response.codeSnippets.length > 0) {
          const codeBlocks = response.codeSnippets.map((s) =>
            `\`\`\`${s.language}${s.filePath ? `:${s.filePath}` : ''}\n${s.code}\n\`\`\``
          ).join('\n\n');

          setTimeout(() => {
            addMessage({
              role: 'assistant',
              content: `Đây là code tôi đề xuất:\n\n${codeBlocks}`,
            });
          }, 500);
        }
      }
    } catch (error) {
      console.error('AI Error:', error);
      const lastMsgId = messages.length > 0 ? messages[messages.length - 1].id : assistantMsgId;
      updateMessage(lastMsgId, {
        content: 'Xin lỗi, đã có lỗi xảy ra khi xử lý yêu cầu của bạn. Vui lòng thử lại.',
        isStreaming: false,
      });
    } finally {
      setIsLoading(false);
    }
  }, [addMessage, updateMessage, steeringFiles, currentSpec, tasks, workspacePath, isLoading, messages]);

  // Handle quick actions
  const handleQuickAction = (prompt: string) => {
    setInput(prompt);
    inputRef.current?.focus();
  };

  // Handle keyboard shortcuts
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  return (
    <div className="h-full flex flex-col bg-app-sidebar">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-app-border">
        <div className="flex items-center gap-2">
          <Bot className="w-5 h-5 text-app-accent" />
          <span className="font-semibold text-app-text">AgenticAI</span>
        </div>
        <button
          onClick={clearMessages}
          className="p-1.5 rounded hover:bg-app-panel text-app-text-dim hover:text-app-text transition-colors"
          title="Clear chat"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Quick Actions */}
      <div className="px-3 py-2 border-b border-app-border">
        <div className="flex flex-wrap gap-1.5">
          {QUICK_ACTIONS.map((action, idx) => (
            <button
              key={idx}
              onClick={() => handleQuickAction(action.prompt)}
              className="flex items-center gap-1.5 px-2 py-1 text-xs bg-app-panel hover:bg-app-panel/80 text-app-text-dim hover:text-app-text rounded border border-app-border transition-colors"
            >
              {action.icon}
              <span>{action.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-app-border">
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask me anything... (Enter to send, Shift+Enter for new line)"
            rows={1}
            className="flex-1 px-3 py-2 bg-app-panel border border-app-border rounded-lg text-sm text-app-text placeholder:text-app-text-dim focus:outline-none focus:border-app-accent resize-none max-h-32"
            style={{ minHeight: '40px' }}
          />
          <button
            onClick={() => sendMessage(input)}
            disabled={!input.trim() || isLoading}
            className={clsx(
              'flex-shrink-0 p-2 rounded-lg transition-colors',
              input.trim() && !isLoading
                ? 'bg-app-accent text-white hover:opacity-90'
                : 'bg-app-panel text-app-text-dim cursor-not-allowed'
            )}
          >
            {isLoading ? (
              <Loader2 className="w-5 h-5 animate-spin" />
            ) : (
              <Send className="w-5 h-5" />
            )}
          </button>
        </div>
      </div>

      {/* Context Info */}
      <div className="px-3 py-2 border-t border-app-border text-xs text-app-text-dim">
        <div className="flex items-center gap-4">
          <span>Steering: {steeringFiles.length} files</span>
          <span>Tasks: {tasks.length}</span>
          {currentSpec && <span>Spec: {currentSpec.title}</span>}
        </div>
      </div>
    </div>
  );
}
