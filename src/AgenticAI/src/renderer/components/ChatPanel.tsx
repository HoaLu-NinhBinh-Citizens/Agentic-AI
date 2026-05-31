import React, { useState, useRef, useEffect } from 'react';
import { useAppStore } from '../store/useAppStore';
import { FiSend, FiTrash2 } from 'react-icons/fi';

export const ChatPanel: React.FC = () => {
  const { messages, addMessage, clearMessages, steeringContext } = useAppStore();
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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

    setTimeout(() => {
      const aiResponse = generateAIResponse(input, steeringContext);
      addMessage({
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: aiResponse,
        timestamp: new Date().toISOString()
      });
      setIsLoading(false);
    }, 1000);
  };

  const generateAIResponse = (userInput: string, context: any): string => {
    const input = userInput.toLowerCase();
    
    if (input.includes('create') || input.includes('new') || input.includes('add')) {
      return `I'll help you create that. Based on the current steering context, let me analyze the requirements:

1. **Analyze requirements** - I've reviewed the existing codebase structure
2. **Create implementation plan** - Breaking down into tasks:
   - Create the main component
   - Add necessary imports
   - Implement core functionality
   - Add tests

Should I proceed with creating the code?`;
    }
    
    if (input.includes('task') || input.includes('todo')) {
      return `Here are your current tasks:

**To Do:**
- Implement feature X
- Write tests for Y

**In Progress:**
- Refactor component Z

**Done:**
- Set up project structure

Would you like me to update any task status?`;
    }

    if (input.includes('review') || input.includes('check')) {
      return `I've analyzed the current code. Here are some findings:

**Security:**
- SEC001: Potential SQL injection in query string
- SEC003: Command injection risk detected

**Quality:**
- QUAL001: Function too long (85 lines, max recommended: 50)
- QUAL002: High cognitive complexity

Would you like me to apply fixes for these issues?`;
    }

    return `I understand you want to: "${userInput}"

I'm an AI assistant powered by AgenticAI. I can help you with:

- **Code Review**: Analyze code for issues, security vulnerabilities
- **Task Management**: Create, update, and track tasks
- **Code Generation**: Write new code based on your specifications
- **Refactoring**: Improve existing code structure

What would you like me to do?`;
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>AI Assistant</h3>
        <button onClick={clearMessages} title="Clear chat"><FiTrash2 /></button>
      </div>

      <div className="chat-messages">
        {messages.length === 0 ? (
          <div className="chat-welcome">
            <h4>Welcome to AgenticAI</h4>
            <p>I can help you with:</p>
            <ul>
              <li>Create new files and components</li>
              <li>Review code for issues</li>
              <li>Manage your tasks</li>
              <li>Refactor and optimize code</li>
            </ul>
            <p className="hint">Try asking: "Create a new React component"</p>
          </div>
        ) : (
          messages.map(msg => (
            <div key={msg.id} className={`message ${msg.role}`}>
              <div className="message-role">{msg.role === 'user' ? 'You' : 'AI'}</div>
              <div className="message-content">{msg.content}</div>
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
          placeholder="Ask me anything..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={2}
        />
        <button onClick={sendMessage} disabled={!input.trim() || isLoading}>
          <FiSend />
        </button>
      </div>
    </div>
  );
};
