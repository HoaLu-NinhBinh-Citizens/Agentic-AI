import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';

export class ContextManager {
    private static instance: ContextManager;
    private context?: vscode.ExtensionContext;
    private projectContext: string = '';

    private constructor() {}

    static getInstance(): ContextManager {
        if (!ContextManager.instance) {
            ContextManager.instance = new ContextManager();
        }
        return ContextManager.instance;
    }

    initialize(): void {
        // Context is set via activate()
    }

    setContext(context: vscode.ExtensionContext): void {
        this.context = context;
        this.loadProjectContext();
    }

    private loadProjectContext(): void {
        const workspaceFolders = vscode.workspace.workspaceFolders;
        if (!workspaceFolders || workspaceFolders.length === 0) {
            this.projectContext = 'No workspace folder open';
            return;
        }

        const rootPath = workspaceFolders[0].uri.fsPath;
        this.projectContext = this.buildProjectContext(rootPath);
    }

    async getProjectContext(): Promise<string> {
        if (!this.projectContext) {
            this.loadProjectContext();
        }

        const config = vscode.workspace.getConfiguration('ai-support');
        const enableContext = config.get<boolean>('enableContext', true);

        if (!enableContext) {
            return 'Context disabled';
        }

        return this.projectContext;
    }

    private buildProjectContext(rootPath: string): string {
        const sections: string[] = [];
        sections.push(`Project Root: ${rootPath}`);

        // Detect project structure
        const softwarePath = path.join(rootPath, 'main', 'software');
        const aiSupportPath = path.join(rootPath, 'AI_support');
        const firmwarePath = path.join(rootPath, 'main', 'software', 'src');

        const context: string[] = [];

        if (fs.existsSync(softwarePath)) {
            context.push('Project Structure: Firmware development workspace');

            // List key directories
            const dirs = this.listDirectories(softwarePath);
            if (dirs.length > 0) {
                context.push(`Key directories: ${dirs.join(', ')}`);
            }
        }

        if (fs.existsSync(firmwarePath)) {
            const sourceFiles = this.findSourceFiles(firmwarePath);
            context.push(`Source files: ${sourceFiles.length} C/H files found`);

            // List main modules
            const modules = this.detectModules(firmwarePath);
            if (modules.length > 0) {
                context.push(`Modules: ${modules.join(', ')}`);
            }
        }

        if (fs.existsSync(aiSupportPath)) {
            context.push('AI Support: Local AI agent present');
        }

        return context.join('\n');
    }

    private listDirectories(dirPath: string): string[] {
        try {
            const entries = fs.readdirSync(dirPath, { withFileTypes: true });
            return entries
                .filter(e => e.isDirectory() && !e.name.startsWith('.') && e.name !== 'node_modules')
                .map(e => e.name);
        } catch {
            return [];
        }
    }

    private findSourceFiles(dirPath: string, maxDepth = 2, currentDepth = 0): string[] {
        const files: string[] = [];
        if (currentDepth > maxDepth) { return files; }

        try {
            const entries = fs.readdirSync(dirPath, { withFileTypes: true });
            for (const entry of entries) {
                const fullPath = path.join(dirPath, entry.name);
                if (entry.isDirectory() && !entry.name.startsWith('.') && entry.name !== 'node_modules') {
                    files.push(...this.findSourceFiles(fullPath, maxDepth, currentDepth + 1));
                } else if (entry.isFile() && (entry.name.endsWith('.c') || entry.name.endsWith('.h'))) {
                    files.push(entry.name);
                }
            }
        } catch {
            // Ignore permission errors
        }

        return files;
    }

    private detectModules(dirPath: string): string[] {
        const modules: string[] = [];
        const knownModules = ['uart', 'spi', 'i2c', 'gpio', 'timer', 'dma', 'adc', 'can', 'pwm', 'rtc'];

        try {
            const entries = fs.readdirSync(dirPath, { withFileTypes: true });
            for (const entry of entries) {
                if (entry.isFile() && (entry.name.endsWith('.c') || entry.name.endsWith('.h'))) {
                    const name = entry.name.toLowerCase();
                    for (const mod of knownModules) {
                        if (name.includes(mod)) {
                            const moduleName = entry.name.replace(/\.(c|h)$/, '');
                            if (!modules.includes(moduleName)) {
                                modules.push(moduleName);
                            }
                        }
                    }
                }
            }
        } catch {
            // Ignore
        }

        return modules.slice(0, 10); // Limit to 10 modules
    }

    cacheKey(key: string): string {
        return `ai-support.${key}`;
    }

    async getCached<T>(key: string, maxAge?: number): Promise<T | undefined> {
        if (!this.context) { return undefined; }
        const cached = this.context.globalState.get<{ value: T; timestamp: number }>(this.cacheKey(key));
        if (!cached) { return undefined; }

        if (maxAge) {
            const age = Date.now() - cached.timestamp;
            if (age > maxAge) { return undefined; }
        }

        return cached.value;
    }

    async setCached<T>(key: string, value: T): Promise<void> {
        if (!this.context) { return; }
        await this.context.globalState.update(this.cacheKey(key), {
            value,
            timestamp: Date.now()
        });
    }
}
