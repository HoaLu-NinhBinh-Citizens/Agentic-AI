'use strict';

const { OpenAI } = require('openai');
const { Anthropic } = require('@anthropic-ai/sdk');

class AIService {
  constructor() {
    this.openai = null;
    this.anthropic = null;
    this.config = null;
  }

  initialize(config) {
    this.config = config;

    if (config.provider === 'openai') {
      this.openai = new OpenAI({ apiKey: config.apiKey });
    } else if (config.provider === 'anthropic') {
      this.anthropic = new Anthropic({ apiKey: config.apiKey });
    }
  }

  isInitialized() {
    return this.config !== null && this.config.apiKey && this.config.apiKey.length > 0;
  }

  getConfig() {
    if (!this.config) return null;
    return { ...this.config, apiKey: '***' };
  }

  async chat(messages, systemPrompt, onChunk) {
    if (!this.config) {
      throw new Error('AI service not initialized. Call initialize() first.');
    }

    if (!this.config.apiKey) {
      throw new Error('API key not configured');
    }

    const allMessages = [];

    if (systemPrompt) {
      allMessages.push({ role: 'system', content: systemPrompt });
    }
    allMessages.push(...messages);

    if (this.config.provider === 'openai' && this.openai) {
      return this._chatOpenAI(allMessages, onChunk);
    } else if (this.config.provider === 'anthropic' && this.anthropic) {
      return this._chatAnthropic(allMessages, onChunk);
    }

    throw new Error(`Unknown provider: ${this.config.provider}`);
  }

  async _chatOpenAI(messages, onChunk) {
    const stream = await this.openai.chat.completions.create({
      model: this.config.model || 'gpt-4',
      messages: messages,
      temperature: this.config.temperature ?? 0.7,
      max_tokens: this.config.maxTokens ?? 4096,
      stream: true,
    });

    let fullContent = '';
    let usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content || '';
      if (delta) {
        fullContent += delta;
        if (onChunk) onChunk(delta);
      }
      if (chunk.usage) {
        usage = {
          promptTokens: chunk.usage.prompt_tokens || 0,
          completionTokens: chunk.usage.completion_tokens || 0,
          totalTokens: chunk.usage.total_tokens || 0,
        };
      }
    }

    return { content: fullContent, usage, model: this.config.model || 'gpt-4' };
  }

  async _chatAnthropic(messages, onChunk) {
    const systemMessage = messages.find(m => m.role === 'system');
    const userMessages = messages.filter(m => m.role !== 'system');

    const stream = await this.anthropic.messages.stream({
      model: this.config.model || 'claude-3-5-sonnet-20241022',
      max_tokens: this.config.maxTokens ?? 4096,
      temperature: this.config.temperature ?? 0.7,
      system: systemMessage?.content,
      messages: userMessages,
    });

    let fullContent = '';

    for await (const event of stream.fullStreamEventEnumerator()) {
      if (event.type === 'content_block_delta') {
        if (event.delta && event.delta.text) {
          fullContent += event.delta.text;
          if (onChunk) onChunk(event.delta.text);
        }
      }
    }

    const usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    return { content: fullContent, usage, model: this.config.model || 'claude-3-5-sonnet' };
  }

  async codeReview(code, language, context) {
    const systemPrompt = `You are an expert code reviewer. Analyze the provided code and return a JSON review with:
{
  "issues": [
    {
      "type": "SEC|QUAL|PERF|STYLE",
      "severity": "error|warning|info",
      "line": number,
      "message": "description",
      "suggestion": "optional fix"
    }
  ],
  "summary": "overall assessment"
}

Languages: ${language}
Context: ${context || 'No additional context'}`;

    const response = await this.chat([
      { role: 'user', content: `Review this code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], systemPrompt);

    return response.content;
  }

  async generateCode(spec, existingCode) {
    const systemPrompt = `You are an expert software engineer. Generate code based on the specification. Return ONLY the code with minimal explanation.`;

    const userMessage = existingCode
      ? `Modify this existing code:\n\n\`\`\`\n${existingCode}\n\`\`\`\n\nTo meet this specification:\n\n${spec}`
      : `Generate code for this specification:\n\n${spec}`;

    const response = await this.chat([{ role: 'user', content: userMessage }], systemPrompt);
    return response.content;
  }

  async explainCode(code, language) {
    const response = await this.chat([
      { role: 'user', content: `Explain this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], 'You are a helpful code assistant that explains code clearly.');
    return response.content;
  }

  async createTasksFromSpec(spec) {
    const systemPrompt = `You are a task planning assistant. Break down the specification into actionable tasks.
Return a JSON array of tasks:
[
  {
    "title": "task title",
    "description": "detailed description",
    "priority": "high|medium|low"
  }
]`;

    const response = await this.chat([
      { role: 'user', content: `Create tasks for this specification:\n\n${spec}` }
    ], systemPrompt);

    return response.content;
  }

  async suggestRefactor(code, language, goal) {
    const response = await this.chat([
      { role: 'user', content: `Suggest refactoring for this ${language} code to achieve: ${goal}\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], 'You are an expert software architect. Provide specific, actionable refactoring suggestions.');
    return response.content;
  }

  async completeCode(code, language, cursorPosition) {
    const systemPrompt = `You are a code completion assistant. Complete the following ${language} code.
Return ONLY the completion, no explanation.`;

    const response = await this.chat([
      { role: 'user', content: `Complete this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], systemPrompt);
    return response.content;
  }
}

module.exports = { aiService: new AIService(), AIService };
