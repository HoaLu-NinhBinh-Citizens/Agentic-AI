class ExtensionSystem {
  constructor() {
    this.extensions = new Map();
    this.detectors = new Map();
    this.commands = new Map();
  }

  async loadExtension(extension) {
    try {
      if (extension.activate) {
        await extension.activate();
      }
      this.extensions.set(extension.id, extension);
      
      if (extension.contributions?.detectors) {
        for (const detector of extension.contributions.detectors) {
          this.detectors.set(detector.id, {
            id: detector.id,
            name: detector.name,
            detect: (code) => {
              const results = [];
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

  unloadExtension(id) {
    const extension = this.extensions.get(id);
    if (extension) {
      if (extension.deactivate) {
        extension.deactivate();
      }
      this.extensions.delete(id);
      this.detectors.delete(id);
      return true;
    }
    return false;
  }

  getExtension(id) {
    return this.extensions.get(id);
  }

  getAllExtensions() {
    return Array.from(this.extensions.values());
  }

  runDetector(id, code, context) {
    const detector = this.detectors.get(id);
    if (detector) {
      return detector.detect(code, context);
    }
    return [];
  }

  runAllDetectors(code, context) {
    const results = [];
    for (const detector of this.detectors.values()) {
      results.push(...detector.detect(code, context));
    }
    return results;
  }

  registerCommand(id, handler) {
    this.commands.set(id, handler);
  }

  async executeCommand(id, ...args) {
    const handler = this.commands.get(id);
    if (handler) {
      return await handler(...args);
    }
    throw new Error(`Command not found: ${id}`);
  }
}

const extensionSystem = new ExtensionSystem();
module.exports = { extensionSystem };
