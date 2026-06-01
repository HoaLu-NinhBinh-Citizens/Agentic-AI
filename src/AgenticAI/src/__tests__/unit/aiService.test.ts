import { AIService, AIConfig, ChatMessage } from '../../main-process/aiService';

// Mock the ollamaClient
jest.mock('../../main-process/ollamaClient', () => ({
  ollamaClient: {
    setEndpoint: jest.fn(),
    getContextLimit: jest.fn().mockReturnValue(4096),
    generate: jest.fn(),
  },
}));

// Mock OpenAI
jest.mock('openai', () => {
  return jest.fn().mockImplementation(() => ({
    chat: {
      completions: {
        create: jest.fn(),
      },
    },
  }));
});

// Mock Anthropic
jest.mock('@anthropic-ai/sdk', () => {
  return jest.fn().mockImplementation(() => ({
    messages: {
      stream: jest.fn().mockReturnValue({
        fullStreamEventEnumerator: jest.fn().mockReturnValue({
          next: jest.fn(),
        }),
      }),
    },
  }));
});

describe('AIService', () => {
  let aiService: AIService;

  beforeEach(() => {
    aiService = new AIService();
    jest.clearAllMocks();
  });

  describe('initialize', () => {
    it('should initialize with Ollama config', () => {
      const config: AIConfig = {
        provider: 'ollama',
        ollamaEndpoint: 'http://localhost:11434',
        ollamaModel: 'codellama',
      };

      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(true);
      expect(aiService.getProvider()).toBe('ollama');
    });

    it('should initialize with OpenAI config', () => {
      const config: AIConfig = {
        provider: 'openai',
        openaiApiKey: 'test-key',
        openaiModel: 'gpt-4',
      };

      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(true);
      expect(aiService.getProvider()).toBe('openai');
    });

    it('should initialize with Anthropic config', () => {
      const config: AIConfig = {
        provider: 'anthropic',
        anthropicApiKey: 'test-key',
        anthropicModel: 'claude-3-5-sonnet',
      };

      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(true);
      expect(aiService.getProvider()).toBe('anthropic');
    });

    it('should not initialize without API key for OpenAI', () => {
      const config: AIConfig = {
        provider: 'openai',
      };

      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(false);
    });

    it('should not initialize without API key for Anthropic', () => {
      const config: AIConfig = {
        provider: 'anthropic',
      };

      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(false);
    });
  });

  describe('chat', () => {
    it('should throw error when not initialized', async () => {
      const messages: ChatMessage[] = [
        { role: 'user', content: 'Hello' },
      ];

      await expect(aiService.chat(messages)).rejects.toThrow('AI service not initialized');
    });

    it('should return error for uninitialized provider', async () => {
      const config: AIConfig = {
        provider: 'openai',
      };
      aiService.initialize(config);

      const messages: ChatMessage[] = [
        { role: 'user', content: 'Hello' },
      ];

      await expect(aiService.chat(messages)).rejects.toThrow('No AI provider initialized');
    });
  });

  describe('cancel', () => {
    it('should not throw when calling cancel without initialization', () => {
      expect(() => aiService.cancel()).not.toThrow();
    });
  });

  describe('getConfig', () => {
    it('should return null when not initialized', () => {
      expect(aiService.getConfig()).toBeNull();
    });

    it('should return config after initialization', () => {
      const config: AIConfig = {
        provider: 'ollama',
        ollamaEndpoint: 'http://localhost:11434',
      };

      aiService.initialize(config);

      expect(aiService.getConfig()).toEqual(config);
    });
  });

  describe('getProvider', () => {
    it('should return null when not initialized', () => {
      expect(aiService.getProvider()).toBeNull();
    });

    it('should return correct provider after initialization', () => {
      const config: AIConfig = {
        provider: 'anthropic',
        anthropicApiKey: 'test-key',
      };

      aiService.initialize(config);

      expect(aiService.getProvider()).toBe('anthropic');
    });
  });

  describe('codeReview', () => {
    it('should call chat with review prompt', async () => {
      const { ollamaClient } = require('../../main-process/ollamaClient');
      ollamaClient.generate.mockResolvedValueOnce('Code review result');

      const config: AIConfig = {
        provider: 'ollama',
        ollamaModel: 'codellama',
      };
      aiService.initialize(config);

      const result = await aiService.codeReview('const x = 1;', 'javascript');

      expect(result).toBe('Code review result');
    });
  });

  describe('generateCode', () => {
    it('should call chat with code generation prompt', async () => {
      const { ollamaClient } = require('../../main-process/ollamaClient');
      ollamaClient.generate.mockResolvedValueOnce('Generated code');

      const config: AIConfig = {
        provider: 'ollama',
        ollamaModel: 'codellama',
      };
      aiService.initialize(config);

      const result = await aiService.generateCode('Create a function');

      expect(result).toBe('Generated code');
    });
  });

  describe('explainCode', () => {
    it('should call chat with explanation prompt', async () => {
      const { ollamaClient } = require('../../main-process/ollamaClient');
      ollamaClient.generate.mockResolvedValueOnce('Code explanation');

      const config: AIConfig = {
        provider: 'ollama',
        ollamaModel: 'codellama',
      };
      aiService.initialize(config);

      const result = await aiService.explainCode('const x = 1;', 'javascript');

      expect(result).toBe('Code explanation');
    });
  });

  describe('createTasksFromSpec', () => {
    it('should call chat with task creation prompt', async () => {
      const { ollamaClient } = require('../../main-process/ollamaClient');
      ollamaClient.generate.mockResolvedValueOnce('Task list');

      const config: AIConfig = {
        provider: 'ollama',
        ollamaModel: 'codellama',
      };
      aiService.initialize(config);

      const result = await aiService.createTasksFromSpec('Implement feature X');

      expect(result).toBe('Task list');
    });
  });

  describe('suggestRefactor', () => {
    it('should call chat with refactoring prompt', async () => {
      const { ollamaClient } = require('../../main-process/ollamaClient');
      ollamaClient.generate.mockResolvedValueOnce('Refactoring suggestions');

      const config: AIConfig = {
        provider: 'ollama',
        ollamaModel: 'codellama',
      };
      aiService.initialize(config);

      const result = await aiService.suggestRefactor('const x = 1;', 'javascript', 'improve performance');

      expect(result).toBe('Refactoring suggestions');
    });
  });

  describe('completeCode', () => {
    it('should call chat with code completion prompt', async () => {
      const { ollamaClient } = require('../../main-process/ollamaClient');
      ollamaClient.generate.mockResolvedValueOnce('completed code');

      const config: AIConfig = {
        provider: 'ollama',
        ollamaModel: 'codellama',
      };
      aiService.initialize(config);

      const result = await aiService.completeCode('const x = 1', 'javascript');

      expect(result).toBe('completed code');
    });
  });

  describe('isInitialized', () => {
    it('should return false when not initialized', () => {
      expect(aiService.isInitialized()).toBe(false);
    });

    it('should return true when ollama is initialized', () => {
      const config: AIConfig = {
        provider: 'ollama',
      };
      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(true);
    });

    it('should return true when openai is initialized with API key', () => {
      const config: AIConfig = {
        provider: 'openai',
        openaiApiKey: 'test-key',
      };
      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(true);
    });

    it('should return false when openai is missing API key', () => {
      const config: AIConfig = {
        provider: 'openai',
      };
      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(false);
    });

    it('should return true when anthropic is initialized with API key', () => {
      const config: AIConfig = {
        provider: 'anthropic',
        anthropicApiKey: 'test-key',
      };
      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(true);
    });

    it('should return false when anthropic is missing API key', () => {
      const config: AIConfig = {
        provider: 'anthropic',
      };
      aiService.initialize(config);

      expect(aiService.isInitialized()).toBe(false);
    });
  });
});
