import * as vscode from 'vscode';
import { OllamaClient } from './ollamaClient';
import { ContextManager } from './contextManager';

export class CodeAnalyzer {
    private ollama: OllamaClient;
    private contextManager: ContextManager;

    constructor(ollama: OllamaClient) {
        this.ollama = ollama;
        this.contextManager = ContextManager.getInstance();
    }

    async analyze(code: string, languageId: string): Promise<void> {
        const panel = vscode.window.createWebviewPanel(
            'aiSupport.analyzer',
            'AI Code Analysis',
            vscode.ViewColumn.Beside,
            { enableFindWidget: true }
        );

        panel.webview.html = this.getLoadingHtml('Analyzing code...');

        const context = await this.contextManager.getProjectContext();
        const prompt = this.buildAnalysisPrompt(code, languageId, context);

        try {
            const analysis = await this.ollama.generate(prompt);

            panel.webview.html = this.formatResponse(analysis, {
                title: 'Code Analysis Results',
                icon: '🔍'
            });
        } catch (error) {
            panel.webview.html = this.getErrorHtml('Failed to analyze code');
        }
    }

    async generateDriver(peripheral: string, mcu: string): Promise<void> {
        const panel = vscode.window.createWebviewPanel(
            'aiSupport.generator',
            'AI Driver Generator',
            vscode.ViewColumn.Beside,
            { enableFindWidget: true }
        );

        panel.webview.html = this.getLoadingHtml(`Generating ${peripheral} driver for ${mcu}...`);

        const context = await this.contextManager.getProjectContext();
        const prompt = this.buildDriverPrompt(peripheral, mcu, context);

        try {
            const driver = await this.ollama.generate(prompt);

            const doc = await vscode.workspace.openTextDocument({
                content: driver,
                language: 'c'
            });
            await vscode.window.showTextDocument(doc, vscode.ViewColumn.One);

            panel.webview.html = this.formatResponse(driver, {
                title: `${peripheral} Driver Generated`,
                icon: '✅',
                copyable: true
            });
        } catch (error) {
            panel.webview.html = this.getErrorHtml('Failed to generate driver');
        }
    }

    async searchDocs(query: string): Promise<void> {
        const panel = vscode.window.createWebviewPanel(
            'aiSupport.search',
            'AI Documentation Search',
            vscode.ViewColumn.Beside,
            { enableFindWidget: true }
        );

        panel.webview.html = this.getLoadingHtml(`Searching for: ${query}`);

        const prompt = `Based on STM32 embedded systems knowledge, provide detailed information about:

Query: ${query}

Include:
1. Brief explanation
2. Key registers involved
3. Configuration steps
4. Common issues and solutions
5. Related topics

Format the response clearly with headers.`;

        try {
            const results = await this.ollama.generate(prompt);

            panel.webview.html = this.formatResponse(results, {
                title: `Documentation: ${query}`,
                icon: '📚'
            });
        } catch (error) {
            panel.webview.html = this.getErrorHtml('Failed to search documentation');
        }
    }

    private buildAnalysisPrompt(code: string, languageId: string, context: string): string {
        return `Analyze the following ${languageId} code for an embedded STM32 firmware project.

Context about the project:
${context}

Code to analyze:
\`\`\`${languageId}
${code}
\`\`\`

Provide a structured analysis including:
1. **Purpose**: What does this code do?
2. **Hardware Dependencies**: Which peripherals/registers are used?
3. **Potential Issues**: Any bugs, race conditions, or unsafe patterns?
4. **Compliance**: Does it follow STM32 HAL conventions?
5. **Suggestions**: Any improvements or optimizations?

Be specific about register names and configuration values.`;
    }

    private buildDriverPrompt(peripheral: string, mcu: string, context: string): string {
        return `Generate a production-ready ${peripheral} driver for ${mcu} using STM32 HAL.

Project context:
${context}

Requirements:
1. Include initialization function with clock, GPIO, and peripheral configuration
2. Implement basic send/receive operations
3. Include proper error handling
4. Add configuration macros for easy customization
5. Follow STM32 HAL coding standards
6. Include DMA and interrupt support if applicable
7. Add documentation comments explaining key sections

Output ONLY the complete C code with no additional explanation.`;
    }

    private formatResponse(content: string, options: { title: string; icon: string; copyable?: boolean }): string {
        const escapedContent = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>')
            .replace(/```(\w+)?\n([\s\S]*?)```/g, '<pre><code class="$1">$2</code></pre>');

        return `<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: var(--vscode-font-family); padding: 20px; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
        .header { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--vscode-border); }
        .icon { font-size: 24px; }
        h1 { margin: 0; font-size: 18px; }
        .content { line-height: 1.6; white-space: pre-wrap; }
        pre { background: var(--vscode-textCodeBlock-background); padding: 15px; border-radius: 5px; overflow-x: auto; }
        code { font-family: var(--vscode-editor-word-highlight-background); }
        .copy-btn { background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; padding: 8px 16px; cursor: pointer; border-radius: 3px; }
    </style>
</head>
<body>
    <div class="header">
        <span class="icon">${options.icon}</span>
        <h1>${options.title}</h1>
    </div>
    <div class="content">${escapedContent}</div>
</body>
</html>`;
    }

    private getLoadingHtml(message: string): string {
        return `<!DOCTYPE html>
<html>
<head>
    <style>
        body { 
            font-family: var(--vscode-font-family); 
            padding: 40px; 
            text-align: center; 
            background: var(--vscode-editor-background); 
            color: var(--vscode-editor-foreground);
        }
        .spinner { 
            border: 3px solid var(--vscode-border); 
            border-top-color: var(--vscode-progressBar-background);
            border-radius: 50%; 
            width: 40px; 
            height: 40px; 
            animation: spin 1s linear infinite; 
            margin: 0 auto 20px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="spinner"></div>
    <p>${message}</p>
</body>
</html>`;
    }

    private getErrorHtml(message: string): string {
        return `<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: var(--vscode-font-family); padding: 40px; text-align: center; background: var(--vscode-editor-background); color: var(--vscode-errorForeground); }
        .error-icon { font-size: 48px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="error-icon">⚠️</div>
    <p>${message}</p>
</body>
</html>`;
    }
}
