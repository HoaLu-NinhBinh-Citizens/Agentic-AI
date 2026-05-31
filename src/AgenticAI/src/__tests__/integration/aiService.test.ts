describe('AI Service Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('AI Initialization', () => {
    it('should check AI initialization status', async () => {
      window.electronAPI.ai.isInitialized.mockResolvedValueOnce(true);
      
      const isInitialized = await window.electronAPI.ai.isInitialized();
      
      expect(isInitialized).toBe(true);
    });

    it('should return false when AI is not initialized', async () => {
      window.electronAPI.ai.isInitialized.mockResolvedValueOnce(false);
      
      const isInitialized = await window.electronAPI.ai.isInitialized();
      
      expect(isInitialized).toBe(false);
    });
  });

  describe('Chat Functionality', () => {
    it('should send chat message and receive response', async () => {
      const mockResponse = {
        content: 'Hello! How can I help you today?',
        error: null
      };
      
      window.electronAPI.ai.chat.mockResolvedValueOnce(mockResponse);
      
      const messages = [
        { role: 'user', content: 'Hello' }
      ];
      
      const response = await window.electronAPI.ai.chat(messages);
      
      expect(response.content).toBe(mockResponse.content);
      expect(response.error).toBeNull();
    });

    it('should handle chat error gracefully', async () => {
      window.electronAPI.ai.chat.mockResolvedValueOnce({
        content: '',
        error: 'API key not configured'
      });
      
      const messages = [
        { role: 'user', content: 'Hello' }
      ];
      
      const response = await window.electronAPI.ai.chat(messages);
      
      expect(response.error).toBe('API key not configured');
      expect(response.content).toBe('');
    });

    it('should send conversation history', async () => {
      const mockResponse = {
        content: 'That makes sense.',
        error: null
      };
      
      window.electronAPI.ai.chat.mockResolvedValueOnce(mockResponse);
      
      const messages = [
        { role: 'user', content: 'Hello' },
        { role: 'assistant', content: 'Hi there!' },
        { role: 'user', content: 'How are you?' }
      ];
      
      const response = await window.electronAPI.ai.chat(messages);
      
      expect(window.electronAPI.ai.chat).toHaveBeenCalledWith(messages);
      expect(response.content).toBe('That makes sense.');
    });
  });

  describe('Code Review', () => {
    it('should request code review', async () => {
      const mockReview = JSON.stringify({
        issues: [
          {
            type: 'QUAL',
            severity: 'warning',
            line: 5,
            message: 'Unused variable',
            suggestion: 'Remove unused variable or prefix with underscore'
          }
        ],
        summary: 'Code looks good overall'
      });
      
      window.electronAPI.ai.codeReview.mockResolvedValueOnce(mockReview);
      
      const code = 'const unused = 1;\nconsole.log("test");';
      const review = await window.electronAPI.ai.codeReview(code, 'typescript', 'Test context');
      
      expect(window.electronAPI.ai.codeReview).toHaveBeenCalledWith(code, 'typescript', 'Test context');
      expect(review).toContain('issues');
    });

    it('should handle code review with no context', async () => {
      window.electronAPI.ai.codeReview.mockResolvedValueOnce('{}');
      
      const code = 'const x = 1;';
      await window.electronAPI.ai.codeReview(code, 'javascript', null);
      
      expect(window.electronAPI.ai.codeReview).toHaveBeenCalledWith(code, 'javascript', null);
    });
  });

  describe('Code Generation', () => {
    it('should generate code from specification', async () => {
      const mockCode = 'function hello() {\n  console.log("Hello, World!");\n}';
      
      window.electronAPI.ai.generateCode.mockResolvedValueOnce(mockCode);
      
      const spec = 'Create a function that logs Hello World';
      const code = await window.electronAPI.ai.generateCode(spec);
      
      expect(window.electronAPI.ai.generateCode).toHaveBeenCalledWith(spec);
      expect(code).toContain('Hello');
    });

    it('should modify existing code based on specification', async () => {
      const mockCode = 'function goodbye() {\n  console.log("Goodbye!");\n}';
      
      window.electronAPI.ai.generateCode.mockResolvedValueOnce(mockCode);
      
      const spec = 'Change hello to goodbye';
      const existingCode = 'function hello() {\n  console.log("Hello!");\n}';
      
      const code = await window.electronAPI.ai.generateCode(spec, existingCode);
      
      expect(window.electronAPI.ai.generateCode).toHaveBeenCalledWith(spec, existingCode);
      expect(code).toContain('Goodbye');
    });
  });

  describe('Code Explanation', () => {
    it('should explain code', async () => {
      const mockExplanation = 'This function creates a new array by doubling each element.';
      
      window.electronAPI.ai.explainCode.mockResolvedValueOnce(mockExplanation);
      
      const code = 'const doubled = arr.map(x => x * 2);';
      const explanation = await window.electronAPI.ai.explainCode(code, 'javascript');
      
      expect(window.electronAPI.ai.explainCode).toHaveBeenCalledWith(code, 'javascript');
      expect(explanation).toContain('array');
    });
  });

  describe('Error Handling', () => {
    it('should handle network errors', async () => {
      window.electronAPI.ai.chat.mockRejectedValue(new Error('Network error'));
      
      const messages = [{ role: 'user', content: 'Hello' }];
      
      await expect(window.electronAPI.ai.chat(messages)).rejects.toThrow('Network error');
    });

    it('should handle timeout errors', async () => {
      window.electronAPI.ai.chat.mockRejectedValue(new Error('Request timeout'));
      
      const messages = [{ role: 'user', content: 'Hello' }];
      
      await expect(window.electronAPI.ai.chat(messages)).rejects.toThrow('Request timeout');
    });

    it('should handle rate limiting', async () => {
      window.electronAPI.ai.chat.mockResolvedValueOnce({
        content: '',
        error: 'Rate limit exceeded. Please wait.'
      });
      
      const messages = [{ role: 'user', content: 'Hello' }];
      const response = await window.electronAPI.ai.chat(messages);
      
      expect(response.error).toContain('Rate limit');
    });
  });
});
