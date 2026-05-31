import OpenAI from 'openai';
import Anthropic from '@anthropic-ai/sdk';
import { ollamaClient } from './ollamaClient';

export type AIProvider = 'ollama' | 'openai' | 'anthropic';

export interface AIConfig {
  provider: AIProvider;
  // Ollama
  ollamaEndpoint?: string;
  ollamaModel?: string;
  ollamaTemperature?: number;
  // OpenAI
  openaiApiKey?: string;
  openaiModel?: string;
  // Anthropic
  anthropicApiKey?: string;
  anthropicModel?: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface AIResponse {
  content: string;
  usage?: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  model: string;
}

export interface StreamChunk {
  content: string;
  done: boolean;
}

export class AIService {
  private openai: OpenAI | null = null;
  private anthropic: Anthropic | null = null;
  private config: AIConfig | null = null;
  private abortController: AbortController | null = null;

  initialize(config: AIConfig): void {
    this.config = config;

    if (config.provider === 'openai' && config.openaiApiKey) {
      this.openai = new OpenAI({ apiKey: config.openaiApiKey });
    } else if (config.provider === 'anthropic' && config.anthropicApiKey) {
      this.anthropic = new Anthropic({ apiKey: config.anthropicApiKey });
    } else if (config.provider === 'ollama') {
      if (config.ollamaEndpoint) {
        ollamaClient.setEndpoint(config.ollamaEndpoint);
      }
    }
  }

  async chat(
    messages: ChatMessage[],
    onChunk?: (chunk: StreamChunk) => void
  ): Promise<AIResponse> {
    if (!this.config) {
      throw new Error('AI service not initialized');
    }

    this.abortController?.abort();
    this.abortController = new AbortController();

    if (this.config.provider === 'ollama') {
      return this.chatWithOllama(messages, onChunk);
    } else if (this.config.provider === 'openai' && this.openai) {
      return this.chatWithOpenAI(messages, onChunk);
    } else if (this.config.provider === 'anthropic' && this.anthropic) {
      return this.chatWithAnthropic(messages, onChunk);
    }

    throw new Error('No AI provider initialized');
  }

  private async chatWithOllama(
    messages: ChatMessage[],
    onChunk?: (chunk: StreamChunk) => void
  ): Promise<AIResponse> {
    const model = this.config?.ollamaModel || 'codellama';
    const temperature = this.config?.ollamaTemperature || 0.7;
    const contextLimit = ollamaClient.getContextLimit(model);

    let prompt = messages.map(m => {
      if (m.role === 'system') return `System: ${m.content}`;
      if (m.role === 'user') return `User: ${m.content}`;
      return `Assistant: ${m.content}`;
    }).join('\n\n');

    prompt += '\n\nAssistant:';

    if (prompt.length > contextLimit * 4) {
      const excess = prompt.length - contextLimit * 4;
      const truncateAt = prompt.indexOf('\n\n', excess);
      if (truncateAt > 0) {
        prompt = prompt.slice(truncateAt + 2);
      }
    }

    let fullContent = '';

    const content = await ollamaClient.generate(
      {
        prompt,
        options: { temperature, num_predict: 2048 },
        stream: true,
      },
      onChunk ? (chunk) => {
        fullContent += chunk;
        onChunk({ content: chunk, done: false });
      } : undefined,
      this.abortController?.signal
    );

    if (onChunk) {
      onChunk({ content: '', done: true });
    }

    return { content: fullContent || content, model };
  }

  private async chatWithOpenAI(
    messages: ChatMessage[],
    onChunk?: (chunk: StreamChunk) => void
  ): Promise<AIResponse> {
    if (!this.openai) throw new Error('OpenAI not initialized');

    const model = this.config?.openaiModel || 'gpt-4';

    const stream = await this.openai.chat.completions.create({
      model,
      messages: messages as unknown as OpenAI.Chat.ChatCompletionMessageParam[],
      temperature: this.config?.ollamaTemperature ?? 0.7,
      max_tokens: 4096,
      stream: true,
    });

    let fullContent = '';

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content || '';
      if (delta) {
        fullContent += delta;
        onChunk?.({ content: delta, done: false });
      }
    }

    onChunk?.({ content: '', done: true });

    return { content: fullContent, model };
  }

  private async chatWithAnthropic(
    messages: ChatMessage[],
    onChunk?: (chunk: StreamChunk) => void
  ): Promise<AIResponse> {
    if (!this.anthropic) throw new Error('Anthropic not initialized');

    const systemMessage = messages.find(m => m.role === 'system');
    const userMessages = messages.filter(m => m.role !== 'system');

    // Convert messages to Anthropic format
    const anthropicMessages = userMessages.map(m => ({
      role: m.role as 'user',
      content: m.content,
    }));

    // Use the messages property via type assertion
    const messagesStream = (this.anthropic as any).messages.stream({
      model: this.config?.anthropicModel || 'claude-3-5-sonnet-20241022',
      max_tokens: 4096,
      temperature: this.config?.ollamaTemperature ?? 0.7,
      system: systemMessage?.content,
      messages: anthropicMessages,
    });

    let fullContent = '';

    for await (const event of messagesStream.fullStreamEventEnumerator()) {
      if (event.type === 'content_block_delta' && 'text' in event.delta) {
        fullContent += event.delta.text;
        onChunk?.({ content: event.delta.text, done: false });
      }
    }

    onChunk?.({ content: '', done: true });

    return { content: fullContent, model: this.config?.anthropicModel || 'claude-3-5-sonnet' };
  }

  cancel(): void {
    this.abortController?.abort();
  }

  isInitialized(): boolean {
    if (!this.config) return false;
    
    if (this.config.provider === 'openai') {
      return !!this.config.openaiApiKey;
    } else if (this.config.provider === 'anthropic') {
      return !!this.config.anthropicApiKey;
    } else if (this.config.provider === 'ollama') {
      return true;
    }
    return false;
  }

  getConfig(): AIConfig | null {
    return this.config;
  }

  getProvider(): AIProvider | null {
    return this.config?.provider || null;
  }

  async codeReview(_code: string, _language: string, _context?: string): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Review this code and provide feedback.` }
    ]);

    return response.content;
  }

  async generateCode(_spec: string, _existingCode?: string): Promise<string> {
    const userMessage = 'Generate code based on the specification provided.';

    const response = await this.chat([{ role: 'user', content: userMessage }]);
    return response.content;
  }

  async explainCode(code: string, language: string): Promise<string> {
    const systemMsg = { role: 'system' as const, content: 'You are a helpful code assistant that explains code clearly.' };
    const response = await this.chat([systemMsg, { role: 'user', content: `Explain this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }]);
    return response.content;
  }

  async createTasksFromSpec(_spec: string): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Create tasks for this specification.` }
    ]);
    return response.content;
  }

  async suggestRefactor(code: string, language: string, goal: string): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Suggest refactoring for this ${language} code to achieve: ${goal}\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ]);
    return response.content;
  }

  async completeCode(
    code: string,
    language: string,
    _cursorPosition?: number
  ): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Complete this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ]);
    return response.content;
  }
}

export const aiService = new AIService();
