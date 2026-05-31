import { OpenAI } from 'openai';
import { Anthropic } from '@anthropic-ai/sdk';

export type AIProvider = 'openai' | 'anthropic';

export interface AIConfig {
  provider: AIProvider;
  apiKey: string;
  model?: string;
  maxTokens?: number;
  temperature?: number;
}

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
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

export class AIService {
  private openai: OpenAI | null = null;
  private anthropic: Anthropic | null = null;
  private config: AIConfig | null = null;

  initialize(config: AIConfig): void {
    this.config = config;

    if (config.provider === 'openai') {
      this.openai = new OpenAI({ apiKey: config.apiKey });
    } else if (config.provider === 'anthropic') {
      this.anthropic = new Anthropic({ apiKey: config.apiKey });
    }
  }

  isInitialized(): boolean {
    return this.config !== null && this.config.apiKey.length > 0;
  }

  getConfig(): AIConfig | null {
    return this.config ? { ...this.config, apiKey: '***' } : null;
  }

  async chat(
    messages: ChatMessage[],
    systemPrompt?: string,
    onChunk?: (chunk: string) => void
  ): Promise<AIResponse> {
    if (!this.config) {
      throw new Error('AI service not initialized. Call initialize() first.');
    }

    if (!this.config.apiKey) {
      throw new Error('API key not configured');
    }

    const allMessages: ChatMessage[] = [];

    if (systemPrompt) {
      allMessages.push({ role: 'system', content: systemPrompt });
    }
    allMessages.push(...messages);

    if (this.config.provider === 'openai' && this.openai) {
      return this.chatOpenAI(allMessages, onChunk);
    } else if (this.config.provider === 'anthropic' && this.anthropic) {
      return this.chatAnthropic(allMessages, onChunk);
    }

    throw new Error(`Unknown provider: ${this.config.provider}`);
  }

  private async chatOpenAI(
    messages: ChatMessage[],
    onChunk?: (chunk: string) => void
  ): Promise<AIResponse> {
    const stream = await this.openai!.chat.completions.create({
      model: this.config!.model || 'gpt-4',
      messages: messages as unknown as OpenAI.Chat.ChatCompletionMessageParam[],
      temperature: this.config!.temperature ?? 0.7,
      max_tokens: this.config!.maxTokens ?? 4096,
      stream: true,
    });

    let fullContent = '';
    let usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    for await (const chunk of stream) {
      const delta = chunk.choices[0]?.delta?.content || '';
      if (delta) {
        fullContent += delta;
        onChunk?.(delta);
      }
      if (chunk.usage) {
        usage = {
          promptTokens: chunk.usage.prompt_tokens || 0,
          completionTokens: chunk.usage.completion_tokens || 0,
          totalTokens: chunk.usage.total_tokens || 0,
        };
      }
    }

    return { content: fullContent, usage, model: this.config!.model || 'gpt-4' };
  }

  private async chatAnthropic(
    messages: ChatMessage[],
    onChunk?: (chunk: string) => void
  ): Promise<AIResponse> {
    const systemMessage = messages.find(m => m.role === 'system');
    const userMessages = messages.filter(m => m.role !== 'system');

    const stream = await this.anthropic!.messages.stream({
      model: this.config!.model || 'claude-3-5-sonnet-20241022',
      max_tokens: this.config!.maxTokens ?? 4096,
      temperature: this.config!.temperature ?? 0.7,
      system: systemMessage?.content,
      messages: userMessages as unknown as Anthropic.MessageCreateParamsNonStreaming['messages'],
    });

    let fullContent = '';

    for await (const event of stream.fullStream) {
      if (event.type === 'content_block_delta' && event.type === 'content_block_delta') {
        if ('text' in event.delta) {
          fullContent += event.delta.text;
          onChunk?.(event.delta.text);
        }
      }
    }

    const usage = { promptTokens: 0, completionTokens: 0, totalTokens: 0 };

    return { content: fullContent, usage, model: this.config!.model || 'claude-3-5-sonnet' };
  }

  async codeReview(code: string, language: string, context?: string): Promise<string> {
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

  async generateCode(spec: string, existingCode?: string): Promise<string> {
    const systemPrompt = `You are an expert software engineer. Generate code based on the specification. Return ONLY the code with minimal explanation.`;

    const userMessage = existingCode
      ? `Modify this existing code:\n\n\`\`\`\n${existingCode}\n\`\`\`\n\nTo meet this specification:\n\n${spec}`
      : `Generate code for this specification:\n\n${spec}`;

    const response = await this.chat([{ role: 'user', content: userMessage }], systemPrompt);
    return response.content;
  }

  async explainCode(code: string, language: string): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Explain this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], 'You are a helpful code assistant that explains code clearly.');
    return response.content;
  }

  async createTasksFromSpec(spec: string): Promise<string> {
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

  async suggestRefactor(code: string, language: string, goal: string): Promise<string> {
    const response = await this.chat([
      { role: 'user', content: `Suggest refactoring for this ${language} code to achieve: ${goal}\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], 'You are an expert software architect. Provide specific, actionable refactoring suggestions.');
    return response.content;
  }

  async completeCode(
    code: string,
    language: string,
    cursorPosition?: number
  ): Promise<string> {
    const systemPrompt = `You are a code completion assistant. Complete the following ${language} code.
Return ONLY the completion, no explanation.`;

    const response = await this.chat([
      { role: 'user', content: `Complete this ${language} code:\n\n\`\`\`${language}\n${code}\n\`\`\`` }
    ], systemPrompt);
    return response.content;
  }
}

export const aiService = new AIService();
