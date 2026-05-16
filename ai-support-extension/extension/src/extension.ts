import * as vscode from 'vscode';
import { OllamaClient } from './ollamaClient';
import { CodeAnalyzer } from './codeAnalyzer';
import { HardwareAnalyzer } from './hardwareAnalyzer';
import { ContextManager } from './contextManager';
import { registerTreeViews } from './treeViews';

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('ai-support');
    const ollamaUrl = config.get<string>('ollamaUrl', 'http://localhost:11434');
    const model = config.get<string>('model', 'llama3.1:latest');
    const maxTokens = config.get<number>('maxTokens', 2048);

    const ollamaClient = new OllamaClient(ollamaUrl, model, maxTokens);
    const codeAnalyzer = new CodeAnalyzer(ollamaClient);
    const hardwareAnalyzer = new HardwareAnalyzer(ollamaClient);
    const contextManager = ContextManager.getInstance();
    contextManager.setContext(context);

    registerTreeViews(context);

    const analyzeCodeCmd = vscode.commands.registerCommand(
        'ai-support.analyzeCode',
        async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) {
                vscode.window.showWarningMessage('No active editor');
                return;
            }

            const selection = editor.selection;
            const selectedCode = editor.document.getText(selection);

            if (!selectedCode.trim()) {
                vscode.window.showWarningMessage('No code selected');
                return;
            }

            await codeAnalyzer.analyze(selectedCode, editor.document.languageId);
        }
    );

    const generateDriverCmd = vscode.commands.registerCommand(
        'ai-support.generateDriver',
        async () => {
            const peripheral = await vscode.window.showInputBox({
                prompt: 'Enter peripheral name (e.g., UART, SPI, I2C)',
                placeHolder: 'UART'
            });

            if (!peripheral) { return; }

            const mcu = await vscode.window.showInputBox({
                prompt: 'Enter MCU name (e.g., STM32F407)',
                placeHolder: 'STM32F407'
            });

            if (!mcu) { return; }

            await codeAnalyzer.generateDriver(peripheral, mcu);
        }
    );

    const analyzeHardwareCmd = vscode.commands.registerCommand(
        'ai-support.analyzeHardware',
        async () => {
            const document = vscode.window.activeTextEditor?.document;
            if (!document) {
                vscode.window.showWarningMessage('No active document');
                return;
            }

            const code = document.getText();
            await hardwareAnalyzer.analyzeDependencies(code);
        }
    );

    const explainRegisterCmd = vscode.commands.registerCommand(
        'ai-support.explainRegister',
        async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) { return; }

            const selection = editor.selection;
            const selectedText = editor.document.getText(selection);

            if (!selectedText.trim()) {
                const wordRange = editor.document.getWordRangeAtPosition(selection.start);
                const word = wordRange ? editor.document.getText(wordRange) : '';
                if (word) {
                    await hardwareAnalyzer.explainRegister(word);
                }
                return;
            }

            await hardwareAnalyzer.explainRegister(selectedText.trim());
        }
    );

    const validateConfigCmd = vscode.commands.registerCommand(
        'ai-support.validateConfig',
        async () => {
            const document = vscode.window.activeTextEditor?.document;
            if (!document) {
                vscode.window.showWarningMessage('No active document');
                return;
            }

            await hardwareAnalyzer.validateConfig(document.getText());
        }
    );

    const searchDocsCmd = vscode.commands.registerCommand(
        'ai-support.searchDocs',
        async () => {
            const query = await vscode.window.showInputBox({
                prompt: 'Enter search query',
                placeHolder: 'e.g., UART DMA configuration'
            });

            if (query) {
                await codeAnalyzer.searchDocs(query);
            }
        }
    );

    context.subscriptions.push(
        analyzeCodeCmd,
        generateDriverCmd,
        analyzeHardwareCmd,
        explainRegisterCmd,
        validateConfigCmd,
        searchDocsCmd
    );

    vscode.window.showInformationMessage('AI Support extension activated!');
}

export function deactivate() {}
