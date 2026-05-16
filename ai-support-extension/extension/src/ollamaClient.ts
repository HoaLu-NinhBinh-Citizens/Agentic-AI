import * as vscode from 'vscode';

export interface OllamaResponse {
    model: string;
    response: string;
    done: boolean;
}

export class OllamaClient {
    private baseUrl: string;
    private model: string;
    private maxTokens: number;

    constructor(baseUrl: string, model: string, maxTokens: number) {
        this.baseUrl = baseUrl;
        this.model = model;
        this.maxTokens = maxTokens;
    }

    async generate(prompt: string, system?: string): Promise<string> {
        try {
            const response = await fetch(`${this.baseUrl}/api/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model: this.model,
                    prompt: prompt,
                    system: system || this.getDefaultSystemPrompt(),
                    stream: false,
                    options: {
                        num_predict: this.maxTokens,
                        temperature: 0.3,
                    }
                })
            });

            if (!response.ok) {
                throw new Error(`Ollama API error: ${response.status}`);
            }

            const data = await response.json() as OllamaResponse;
            return data.response;
        } catch (error) {
            if (error instanceof Error) {
                vscode.window.showErrorMessage(`AI Support Error: ${error.message}`);
            }
            throw error;
        }
    }

    async checkConnection(): Promise<boolean> {
        try {
            const response = await fetch(`${this.baseUrl}/api/tags`);
            return response.ok;
        } catch {
            return false;
        }
    }

    private getDefaultSystemPrompt(): string {
        return `You are an expert embedded systems engineer specializing in:
- STM32 microcontroller firmware development
- ARM Cortex-M architecture
- HAL/LL driver development
- Hardware peripheral configuration (UART, SPI, I2C, DMA, TIM, ADC, etc.)
- Interrupt and real-time systems
- CAN/LIN automotive protocols

Provide accurate, concise technical guidance. Always:
1. Reference specific register names and bit fields
2. Mention clock configurations and timing constraints
3. Note potential hardware conflicts or race conditions
4. Follow STM32 HAL coding conventions

Never hallucinate register names or hardware behavior.`;
    }
}
