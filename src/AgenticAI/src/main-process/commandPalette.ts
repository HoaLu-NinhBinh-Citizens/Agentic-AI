export interface Command {
  id: string;
  label: string;
  shortcut?: string;
  category: string;
  icon?: string;
  action: () => void | Promise<void>;
  enabled?: () => boolean;
}

export interface CommandFilter {
  category?: string;
  search?: string;
}

export interface CommandExecutionResult {
  success: boolean;
  error?: string;
  output?: unknown;
}

type CommandHandler = () => void | Promise<void>;

class CommandPalette {
  private commands: Map<string, Command> = new Map();
  private recentCommands: string[] = [];
  private maxRecentCommands = 10;

  /**
   * Register a new command
   */
  register(command: Command): void {
    if (this.commands.has(command.id)) {
      console.warn(`Command ${command.id} already registered, replacing...`);
    }
    this.commands.set(command.id, command);
  }

  /**
   * Unregister a command
   */
  unregister(id: string): boolean {
    return this.commands.delete(id);
  }

  /**
   * Get all registered commands
   */
  getCommands(filter?: CommandFilter): Command[] {
    let commands = Array.from(this.commands.values());

    if (filter?.category) {
      commands = commands.filter(cmd => cmd.category === filter.category);
    }

    if (filter?.search) {
      const search = filter.search.toLowerCase();
      commands = commands.filter(cmd =>
        cmd.label.toLowerCase().includes(search) ||
        cmd.category.toLowerCase().includes(search) ||
        cmd.id.toLowerCase().includes(search)
      );
    }

    return commands;
  }

  /**
   * Get a specific command by ID
   */
  getCommand(id: string): Command | undefined {
    return this.commands.get(id);
  }

  /**
   * Search commands by label or category
   */
  search(query: string): Command[] {
    const lowerQuery = query.toLowerCase().trim();
    if (!lowerQuery) {
      return this.getCommands();
    }

    // Split query into words for more flexible matching
    const queryWords = lowerQuery.split(/\s+/);

    return this.getCommands().filter(cmd => {
      const label = cmd.label.toLowerCase();
      const category = cmd.category.toLowerCase();
      const id = cmd.id.toLowerCase();

      // Check if all query words match
      return queryWords.every(word =>
        label.includes(word) ||
        category.includes(word) ||
        id.includes(word)
      );
    }).sort((a, b) => {
      // Sort by relevance (exact match first, then by recent usage)
      const aExact = a.label.toLowerCase() === lowerQuery;
      const bExact = b.label.toLowerCase() === lowerQuery;
      if (aExact && !bExact) return -1;
      if (bExact && !aExact) return 1;

      // Then by recent usage
      const aRecent = this.recentCommands.indexOf(a.id);
      const bRecent = this.recentCommands.indexOf(b.id);
      if (aRecent !== -1 && bRecent === -1) return -1;
      if (bRecent !== -1 && aRecent === -1) return 1;
      if (aRecent !== -1 && bRecent !== -1 && aRecent < bRecent) return -1;
      if (aRecent !== -1 && bRecent !== -1 && bRecent < aRecent) return 1;

      return 0;
    });
  }

  /**
   * Execute a command by ID
   */
  async execute(id: string): Promise<CommandExecutionResult> {
    const command = this.commands.get(id);
    if (!command) {
      return { success: false, error: `Command not found: ${id}` };
    }

    if (command.enabled && !command.enabled()) {
      return { success: false, error: `Command ${id} is not currently enabled` };
    }

    try {
      await command.action();
      this.addToRecent(id);
      return { success: true };
    } catch (error) {
      return {
        success: false,
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }

  /**
   * Add command to recent usage list
   */
  private addToRecent(id: string): void {
    // Remove if already in list
    const index = this.recentCommands.indexOf(id);
    if (index !== -1) {
      this.recentCommands.splice(index, 1);
    }

    // Add to front
    this.recentCommands.unshift(id);

    // Trim to max size
    if (this.recentCommands.length > this.maxRecentCommands) {
      this.recentCommands.pop();
    }
  }

  /**
   * Get recently used commands
   */
  getRecentCommands(): Command[] {
    return this.recentCommands
      .map(id => this.commands.get(id))
      .filter((cmd): cmd is Command => cmd !== undefined);
  }

  /**
   * Get commands grouped by category
   */
  getCommandsByCategory(): Map<string, Command[]> {
    const grouped = new Map<string, Command[]>();

    for (const command of this.commands.values()) {
      const category = command.category;
      if (!grouped.has(category)) {
        grouped.set(category, []);
      }
      grouped.get(category)!.push(command);
    }

    return grouped;
  }

  /**
   * Clear all commands
   */
  clear(): void {
    this.commands.clear();
    this.recentCommands = [];
  }

  /**
   * Get command count
   */
  get count(): number {
    return this.commands.size;
  }
}

// Singleton instance
export const commandPalette = new CommandPalette();

// ============================================================================
// Built-in Command Handlers
// ============================================================================

export interface BuiltinCommandHandlers {
  // File commands
  onNewFile: CommandHandler;
  onOpenFile: CommandHandler;
  onSaveFile: CommandHandler;
  onSaveAll: CommandHandler;
  onCloseFile: CommandHandler;

  // Edit commands
  onUndo: CommandHandler;
  onRedo: CommandHandler;
  onCut: CommandHandler;
  onCopy: CommandHandler;
  onPaste: CommandHandler;
  onFind: CommandHandler;
  onReplace: CommandHandler;

  // View commands
  onToggleSidebar: CommandHandler;
  onToggleTerminal: CommandHandler;
  onToggleChatPanel: CommandHandler;
  onToggleTaskPanel: CommandHandler;
  onZoomIn: CommandHandler;
  onZoomOut: CommandHandler;
  onResetZoom: CommandHandler;

  // AI commands
  onReviewCurrentFile: CommandHandler;
  onFixAllIssues: CommandHandler;
  onGenerateFromSpec: CommandHandler;
  onExplainCode: CommandHandler;
  onRefactorCode: CommandHandler;

  // Settings commands
  onOpenSettings: CommandHandler;
  onOpenKeyboardShortcuts: CommandHandler;
  onOpenTheme: CommandHandler;
}

/**
 * Register all built-in commands with their handlers
 */
export function registerBuiltinCommands(handlers: BuiltinCommandHandlers): void {
  // ==========================================================================
  // File Commands
  // ==========================================================================
  commandPalette.register({
    id: 'file.newFile',
    label: 'New File',
    shortcut: 'Ctrl+N',
    category: 'File',
    icon: 'file-plus',
    action: handlers.onNewFile,
  });

  commandPalette.register({
    id: 'file.openFile',
    label: 'Open File...',
    shortcut: 'Ctrl+O',
    category: 'File',
    icon: 'folder-open',
    action: handlers.onOpenFile,
  });

  commandPalette.register({
    id: 'file.save',
    label: 'Save',
    shortcut: 'Ctrl+S',
    category: 'File',
    icon: 'save',
    action: handlers.onSaveFile,
  });

  commandPalette.register({
    id: 'file.saveAll',
    label: 'Save All',
    shortcut: 'Ctrl+Shift+S',
    category: 'File',
    icon: 'save-all',
    action: handlers.onSaveAll,
  });

  commandPalette.register({
    id: 'file.close',
    label: 'Close File',
    shortcut: 'Ctrl+W',
    category: 'File',
    icon: 'x',
    action: handlers.onCloseFile,
  });

  // ==========================================================================
  // Edit Commands
  // ==========================================================================
  commandPalette.register({
    id: 'edit.undo',
    label: 'Undo',
    shortcut: 'Ctrl+Z',
    category: 'Edit',
    icon: 'undo',
    action: handlers.onUndo,
  });

  commandPalette.register({
    id: 'edit.redo',
    label: 'Redo',
    shortcut: 'Ctrl+Y',
    category: 'Edit',
    icon: 'redo',
    action: handlers.onRedo,
  });

  commandPalette.register({
    id: 'edit.cut',
    label: 'Cut',
    shortcut: 'Ctrl+X',
    category: 'Edit',
    icon: 'scissors',
    action: handlers.onCut,
  });

  commandPalette.register({
    id: 'edit.copy',
    label: 'Copy',
    shortcut: 'Ctrl+C',
    category: 'Edit',
    icon: 'copy',
    action: handlers.onCopy,
  });

  commandPalette.register({
    id: 'edit.paste',
    label: 'Paste',
    shortcut: 'Ctrl+V',
    category: 'Edit',
    icon: 'clipboard',
    action: handlers.onPaste,
  });

  commandPalette.register({
    id: 'edit.find',
    label: 'Find',
    shortcut: 'Ctrl+F',
    category: 'Edit',
    icon: 'search',
    action: handlers.onFind,
  });

  commandPalette.register({
    id: 'edit.replace',
    label: 'Find and Replace',
    shortcut: 'Ctrl+H',
    category: 'Edit',
    icon: 'replace',
    action: handlers.onReplace,
  });

  // ==========================================================================
  // View Commands
  // ==========================================================================
  commandPalette.register({
    id: 'view.toggleSidebar',
    label: 'Toggle Sidebar',
    shortcut: 'Ctrl+B',
    category: 'View',
    icon: 'sidebar',
    action: handlers.onToggleSidebar,
  });

  commandPalette.register({
    id: 'view.toggleTerminal',
    label: 'Toggle Terminal',
    shortcut: 'Ctrl+`',
    category: 'View',
    icon: 'terminal',
    action: handlers.onToggleTerminal,
  });

  commandPalette.register({
    id: 'view.toggleChatPanel',
    label: 'Toggle Chat Panel',
    shortcut: 'Ctrl+Shift+G',
    category: 'View',
    icon: 'message-circle',
    action: handlers.onToggleChatPanel,
  });

  commandPalette.register({
    id: 'view.toggleTaskPanel',
    label: 'Toggle Task Panel',
    shortcut: 'Ctrl+Shift+T',
    category: 'View',
    icon: 'check-square',
    action: handlers.onToggleTaskPanel,
  });

  commandPalette.register({
    id: 'view.zoomIn',
    label: 'Zoom In',
    shortcut: 'Ctrl+=',
    category: 'View',
    icon: 'zoom-in',
    action: handlers.onZoomIn,
  });

  commandPalette.register({
    id: 'view.zoomOut',
    label: 'Zoom Out',
    shortcut: 'Ctrl+-',
    category: 'View',
    icon: 'zoom-out',
    action: handlers.onZoomOut,
  });

  commandPalette.register({
    id: 'view.resetZoom',
    label: 'Reset Zoom',
    shortcut: 'Ctrl+0',
    category: 'View',
    icon: 'maximize-2',
    action: handlers.onResetZoom,
  });

  // ==========================================================================
  // AI Commands
  // ==========================================================================
  commandPalette.register({
    id: 'ai.reviewCurrentFile',
    label: 'Review Current File',
    shortcut: 'Ctrl+Shift+R',
    category: 'AI',
    icon: 'eye',
    action: handlers.onReviewCurrentFile,
  });

  commandPalette.register({
    id: 'ai.fixAllIssues',
    label: 'Fix All Critical Issues',
    shortcut: 'Ctrl+Shift+F',
    category: 'AI',
    icon: 'wrench',
    action: handlers.onFixAllIssues,
  });

  commandPalette.register({
    id: 'ai.generateFromSpec',
    label: 'Generate Tasks from Spec',
    category: 'AI',
    icon: 'file-text',
    action: handlers.onGenerateFromSpec,
  });

  commandPalette.register({
    id: 'ai.explainCode',
    label: 'Explain Selected Code',
    category: 'AI',
    icon: 'help-circle',
    action: handlers.onExplainCode,
  });

  commandPalette.register({
    id: 'ai.refactorCode',
    label: 'Refactor Selected Code',
    category: 'AI',
    icon: 'refresh-cw',
    action: handlers.onRefactorCode,
  });

  // ==========================================================================
  // Settings Commands
  // ==========================================================================
  commandPalette.register({
    id: 'settings.open',
    label: 'Open Settings',
    shortcut: 'Ctrl+,',
    category: 'Settings',
    icon: 'settings',
    action: handlers.onOpenSettings,
  });

  commandPalette.register({
    id: 'settings.keyboardShortcuts',
    label: 'Open Keyboard Shortcuts',
    category: 'Settings',
    icon: 'command',
    action: handlers.onOpenKeyboardShortcuts,
  });

  commandPalette.register({
    id: 'settings.theme',
    label: 'Color Theme',
    category: 'Settings',
    icon: 'palette',
    action: handlers.onOpenTheme,
  });
}

/**
 * Register custom commands for workspace-specific actions
 */
export function registerCustomCommands(commands: Command[]): void {
  for (const command of commands) {
    commandPalette.register(command);
  }
}
