export interface Extension {
  id: string;
  name: string;
  version: string;
  description?: string;
  author?: string;
  main: string;
  contributions?: ExtensionContributions;
  activate?: () => void | Promise<void>;
  deactivate?: () => void;
}

export interface ExtensionContributions {
  commands?: Array<{
    command: string;
    title: string;
    category?: string;
  }>;
  menus?: Array<{
    command: string;
    where: string;
  }>;
  detectors?: Array<{
    id: string;
    name: string;
    pattern: string;
  }>;
  views?: Array<{
    id: string;
    name: string;
    type: 'list' | 'webview';
  }>;
}

export interface Detector {
  id: string;
  name: string;
  detect: (code: string, context: any) => DetectorResult[];
}

export interface DetectorResult {
  severity: 'error' | 'warning' | 'info';
  message: string;
  line: number;
  rule: string;
}

class ExtensionSystem {
  private extensions: Map<string, Extension> = new Map();
  private detectors: Map<string, Detector> = new Map();
  private commands: Map<string, Function> = new Map();

  async loadExtension(extension: Extension): Promise<boolean> {
    try {
      await extension.activate?.();
      this.extensions.set(extension.id, extension);
      
      if (extension.contributions?.detectors) {
        for (const detector of extension.contributions.detectors) {
          this.detectors.set(detector.id, {
            id: detector.id,
            name: detector.name,
            detect: (code: string) => {
              const results: DetectorResult[] = [];
              const regex = new RegExp(detector.pattern, 'g');
              
              const lines = code.split('\n');
              for (let i = 0; i < lines.length; i++) {
                if (regex.test(lines[i])) {
                  results.push({
                    severity: 'warning',
                    message: `Pattern matched: ${detector.name}`,
                    line: i + 1,
                    rule: detector.id,
                  });
                }
              }
              
              return results;
            },
          });
        }
      }
      
      return true;
    } catch (error) {
      console.error(`Failed to load extension ${extension.id}:`, error);
      return false;
    }
  }

  unloadExtension(id: string): boolean {
    const extension = this.extensions.get(id);
    if (extension) {
      extension.deactivate?.();
      this.extensions.delete(id);
      this.detectors.delete(id);
      return true;
    }
    return false;
  }

  getExtension(id: string): Extension | undefined {
    return this.extensions.get(id);
  }

  getAllExtensions(): Extension[] {
    return Array.from(this.extensions.values());
  }

  runDetector(id: string, code: string, context: any): DetectorResult[] {
    const detector = this.detectors.get(id);
    if (detector) {
      return detector.detect(code, context);
    }
    return [];
  }

  runAllDetectors(code: string, context: any): DetectorResult[] {
    const results: DetectorResult[] = [];
    for (const detector of this.detectors.values()) {
      results.push(...detector.detect(code, context));
    }
    return results;
  }

  registerCommand(id: string, handler: Function): void {
    this.commands.set(id, handler);
  }

  async executeCommand(id: string, ...args: any[]): Promise<any> {
    const handler = this.commands.get(id);
    if (handler) {
      return await handler(...args);
    }
    throw new Error(`Command not found: ${id}`);
  }

  getAllDetectors(): Detector[] {
    return Array.from(this.detectors.values());
  }

  getAllCommands(): Array<{ id: string; handler: Function }> {
    return Array.from(this.commands.entries()).map(([id, handler]) => ({ id, handler }));
  }
}

export const extensionSystem = new ExtensionSystem();
