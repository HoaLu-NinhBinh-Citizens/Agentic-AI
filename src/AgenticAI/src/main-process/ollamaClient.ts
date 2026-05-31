export interface OllamaModel {
  name: string;
  modified_at: string;
  size: number;
}

export interface OllamaConfig {
  endpoint: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface OllamaGenerateOptions {
  prompt: string;
  system?: string;
  context?: number[];
  stream?: boolean;
  options?: {
    temperature?: number;
    num_predict?: number;
    top_p?: number;
    top_k?: number;
  };
}

export interface OllamaHealthStatus {
  available: boolean;
  error?: string;
  latencyMs?: number;
}

export interface PullProgress {
  status: string;
  digest?: string;
  total?: number;
  completed?: number;
  percent?: number;
}

class OllamaClient {
  private endpoint: string = 'http://localhost:11434';
  private timeout: number = 60000;
  
  setEndpoint(endpoint: string) {
    this.endpoint = endpoint;
  }

  async healthCheck(timeout: number = 3000, retries: number = 2): Promise<OllamaHealthStatus> {
    const startTime = Date.now();
    
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        const response = await fetch(`${this.endpoint}/api/tags`, {
          method: 'GET',
          signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        if (response.ok) {
          return {
            available: true,
            latencyMs: Date.now() - startTime,
          };
        }
      } catch (error: any) {
        if (attempt === retries) {
          return {
            available: false,
            error: error.message || 'Connection failed',
            latencyMs: Date.now() - startTime,
          };
        }
        await new Promise(r => setTimeout(r, 500));
      }
    }
    
    return {
      available: false,
      error: 'Max retries exceeded',
    };
  }

  async listModels(): Promise<OllamaModel[]> {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);
      
      const response = await fetch(`${this.endpoint}/api/tags`, {
        method: 'GET',
        signal: controller.signal,
      });
      
      clearTimeout(timeoutId);
      
      if (response.ok) {
        const data = await response.json();
        return data.models || [];
      }
      
      if (response.status === 404) {
        return [];
      }
      
      return [];
    } catch {
      return [];
    }
  }

  async generate(
    options: OllamaGenerateOptions,
    onChunk?: (text: string) => void,
    signal?: AbortSignal
  ): Promise<string> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);
    
    const combinedSignal = signal 
      ? AbortSignal.any([signal, controller.signal])
      : controller.signal;

    const response = await fetch(`${this.endpoint}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'codellama',
        prompt: options.prompt,
        system: options.system,
        context: options.context,
        stream: options.stream !== false,
        options: {
          temperature: options.options?.temperature ?? 0.7,
          num_predict: options.options?.num_predict ?? 2048,
          top_p: options.options?.top_p ?? 0.9,
          top_k: options.options?.top_k ?? 40,
        },
      }),
      signal: combinedSignal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      if (response.status === 404) {
        throw new Error('Model not found. Please pull it first.');
      }
      throw new Error(`Ollama error: ${response.status}`);
    }

    if (options.stream !== false && onChunk) {
      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let fullResponse = '';

      if (reader) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n').filter(Boolean);

            for (const line of lines) {
              try {
                const data = JSON.parse(line);
                if (data.response) {
                  fullResponse += data.response;
                  onChunk(data.response);
                }
              } catch {}
            }
          }
        } finally {
          reader.releaseLock();
        }
      }

      return fullResponse;
    } else {
      const data = await response.json();
      return data.response || '';
    }
  }

  async pullModel(
    model: string,
    onProgress?: (progress: PullProgress) => void
  ): Promise<boolean> {
    try {
      const response = await fetch(`${this.endpoint}/api/pull`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: model, stream: true }),
      });

      if (!response.ok) {
        throw new Error(`Failed to pull model: ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n').filter(Boolean);

            for (const line of lines) {
              try {
                const data = JSON.parse(line);
                if (onProgress) {
                  onProgress({
                    status: data.status || 'pulling',
                    digest: data.digest,
                    total: data.total,
                    completed: data.completed,
                    percent: data.total ? Math.round((data.completed / data.total) * 100) : undefined,
                  });
                }
              } catch {}
            }
          }
        } finally {
          reader.releaseLock();
        }
      }

      return true;
    } catch (error) {
      console.error('Failed to pull model:', error);
      return false;
    }
  }

  getContextLimit(model: string): number {
    const limits: Record<string, number> = {
      'llama2': 2048,
      'llama2:latest': 2048,
      'codellama': 4096,
      'codellama:latest': 4096,
      'codellama:7b': 4096,
      'codellama:13b': 4096,
      'deepseek-coder': 8192,
      'deepseek-coder:latest': 8192,
      'mistral': 8192,
      'mistral:latest': 8192,
      'phi3': 4096,
      'phi3:latest': 4096,
      'mixtral': 32768,
      'mixtral:latest': 32768,
      'qwen': 8192,
      'qwen:latest': 8192,
    };
    
    if (limits[model]) return limits[model];
    
    for (const [prefix, limit] of Object.entries(limits)) {
      if (model.startsWith(prefix.replace(':latest', ''))) {
        return limit;
      }
    }
    
    return 4096;
  }
}

export const ollamaClient = new OllamaClient();
