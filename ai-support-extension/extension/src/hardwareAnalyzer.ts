import * as vscode from 'vscode';
import { OllamaClient } from './ollamaClient';

export class HardwareAnalyzer {
    private ollama: OllamaClient;

    constructor(ollama: OllamaClient) {
        this.ollama = ollama;
    }

    async analyzeDependencies(code: string): Promise<void> {
        const panel = vscode.window.createWebviewPanel(
            'aiSupport.hardware',
            'Hardware Dependencies',
            vscode.ViewColumn.Beside,
            { enableFindWidget: true }
        );

        panel.webview.html = this.getLoadingHtml('Analyzing hardware dependencies...');

        const prompt = `Analyze this STM32 firmware code for hardware dependencies and peripheral relationships.

\`\`\`c
${code}
\`\`\`

Provide a detailed analysis including:
1. **Peripherals Used**: List all hardware peripherals (UART, SPI, GPIO, etc.)
2. **Register Access**: Identify register read/write operations
3. **Clock Dependencies**: Which clocks must be enabled?
4. **GPIO Configuration**: Pin assignments and alternate functions
5. **DMA Channels**: Any DMA transfers?
6. **Interrupt Handlers**: ISR functions and their priorities
7. **Dependency Graph**: How do peripherals depend on each other?
8. **Potential Conflicts**: Any resource conflicts or misconfigurations?`;

        try {
            const analysis = await this.ollama.generate(prompt);
            panel.webview.html = this.formatResponse(analysis, 'Hardware Analysis', '🔧');
        } catch (error) {
            panel.webview.html = this.getErrorHtml('Failed to analyze hardware');
        }
    }

    async explainRegister(register: string): Promise<void> {
        const panel = vscode.window.createWebviewPanel(
            'aiSupport.register',
            `Register: ${register}`,
            vscode.ViewColumn.Beside,
            { enableFindWidget: true }
        );

        panel.webview.html = this.getLoadingHtml(`Explaining ${register}...`);

        const prompt = `Explain the STM32 register/peripheral "${register}" in detail.

For registers, include:
- Full name and abbreviation
- Base address (if applicable)
- Bit field layout and purpose
- Reset value
- Access type (read/write)
- Related registers
- Typical usage in HAL code

For peripherals, include:
- Overview and use cases
- Key configuration registers
- Clock requirements
- Typical initialization sequence
- Common issues and debugging tips

Use technical accuracy and reference specific STM32 reference manuals.`;

        try {
            const explanation = await this.ollama.generate(prompt);
            panel.webview.html = this.formatResponse(explanation, register, '📖');
        } catch (error) {
            panel.webview.html = this.getErrorHtml('Failed to explain register');
        }
    }

    async validateConfig(configCode: string): Promise<void> {
        const panel = vscode.window.createWebviewPanel(
            'aiSupport.validation',
            'Configuration Validation',
            vscode.ViewColumn.Beside,
            { enableFindWidget: true }
        );

        panel.webview.html = this.getLoadingHtml('Validating MCU configuration...');

        const prompt = `Validate this STM32 MCU configuration code for correctness and best practices.

\`\`\`c
${configCode}
\`\`\`

Check for:
1. **Clock Configuration**: PLL, prescalers, flash latency
2. **GPIO Settings**: Mode, speed, pull-up/down, alternate function
3. **Peripheral Init Order**: Correct sequence of initialization
4. **Interrupt Priorities**: Valid NVIC priority assignments
5. **DMA Configuration**: Channel mappings, transfer modes
6. **Power Management**: PWR clock, voltage scaling
7. **Common Mistakes**: Typical configuration errors
8. **Compliance**: Follows STM32 HAL best practices?

Provide a detailed report with specific issues and fixes.`;

        try {
            const validation = await this.ollama.generate(prompt);
            panel.webview.html = this.formatResponse(validation, 'Validation Report', '✅');
        } catch (error) {
            panel.webview.html = this.getErrorHtml('Failed to validate configuration');
        }
    }

    private formatResponse(content: string, title: string, icon: string): string {
        const escapedContent = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');

        return `<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: var(--vscode-font-family); padding: 20px; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
        .header { display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid var(--vscode-border); }
        .icon { font-size: 24px; }
        h1 { margin: 0; font-size: 18px; }
        .content { line-height: 1.6; white-space: pre-wrap; }
    </style>
</head>
<body>
    <div class="header">
        <span class="icon">${icon}</span>
        <h1>${title}</h1>
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
        body { font-family: var(--vscode-font-family); padding: 40px; text-align: center; background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); }
        .spinner { border: 3px solid var(--vscode-border); border-top-color: var(--vscode-progressBar-background); border-radius: 50%; width: 40px; height: 40px; animation: spin 1s linear infinite; margin: 0 auto 20px; }
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
    </style>
</head>
<body>
    <p>⚠️ ${message}</p>
</body>
</html>`;
    }
}
