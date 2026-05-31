// Ollama Client - Local AI Integration

class OllamaClient {
  constructor() {
    this.endpoint = 'http://localhost:11434';
    this.timeout = 60000;
  }

  setEndpoint(endpoint) {
    this.endpoint = endpoint;
  }

  async healthCheck(timeout = 3000, retries = 2) {
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
      } catch (error) {
        if (attempt === retries) {
          return {
            available: false,
            error: error.message || 'Connection failed',
            latencyMs: Date.now() - startTime,
          };
        }
        // Wait before retry
        await new Promise(r => setTimeout(r, 500));
      }
    }

    return {
      available: false,
      error: 'Max retries exceeded',
    };
  }

  async listModels() {
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

      return [];
    } catch (error) {
      console.error('[OllamaClient] Failed to list models:', error);
      return [];
    }
  }

  async generate(options, onChunk) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    const requestOptions = {
      model: options.model || 'codellama',
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
    };

    try {
      const response = await fetch(`${this.endpoint}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(requestOptions),
        signal: controller.signal,
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
                } catch (e) {
                  // Skip invalid JSON lines
                }
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
    } catch (error) {
      clearTimeout(timeoutId);
      throw error;
    }
  }

  async pullModel(model, onProgress) {
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
              } catch (e) {
                // Skip invalid JSON
              }
            }
          }
        } finally {
          reader.releaseLock();
        }
      }

      return true;
    } catch (error) {
      console.error('[OllamaClient] Failed to pull model:', error);
      return false;
    }
  }

  getContextLimit(model) {
    const limits = {
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

const ollamaClient = new OllamaClient();

module.exports = { ollamaClient };
