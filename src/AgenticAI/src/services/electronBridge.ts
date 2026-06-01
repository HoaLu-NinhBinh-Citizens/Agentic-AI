/**
 * ElectronBridge - Dependency Injection for Electron API
 * 
 * This module provides TypeScript types and interfaces for the Electron IPC bridge.
 * The types are defined in vite-env.d.ts.
 * 
 * Usage:
 *   import { ElectronBridge } from '@/services/electronBridge';
 *   // Use the implementation from electronBridgeImpl.ts
 */

// ============================================================================
// Re-export types from global scope (vite-env.d.ts)
// ============================================================================

// Re-export the bridge implementation
export { electronBridge, getElectronBridge, setElectronBridge } from './electronBridgeImpl';

// ============================================================================
// ElectronBridge Interface
// ============================================================================

export interface ElectronBridge {
  // Dialog
  openDirectory(): Promise<string | null>;
  
  // File System
  readDirectory(path: string): Promise<FileEntry[]>;
  readFile(path: string): Promise<string | null>;
  writeFile(path: string, content: string): Promise<void>;
  createFile(path: string): Promise<void>;
  createDirectory(path: string): Promise<void>;
  deleteFile(path: string): Promise<void>;
  rename(oldPath: string, newPath: string): Promise<void>;
  
  // Git (legacy flat methods)
  gitStatus(): Promise<GitStatus>;
  gitBranch(): Promise<string>;
  gitCommit(message: string): Promise<void>;
  gitStage(files: string[]): Promise<void>;
  gitUnstage(files: string[]): Promise<void>;
  gitCheckout(branch: string): Promise<void>;
  gitDiscard(path: string): Promise<void>;
  gitLog(limit?: number): Promise<GitLogEntry[]>;
  gitDiff(path?: string): Promise<string>;
  
  // Terminal
  terminal: TerminalAPI;
  
  // AI
  ai: AIAPI;
  
  // AI Agent (MCP - Python Agent)
  aiAgent: AIAgentAPI;
  
  // Storage
  storage: StorageAPI;
  
  // Steering
  steering: SteeringAPI;
  
  // Settings (convenience methods)
  getSettings?(): Promise<AppSettings | null>;
  saveSettings?(settings: AppSettings): Promise<void>;
  
  // Events
  onFileChange(callback: (path: string) => void): void;
  onGitStatusChange(callback: () => void): void;
}

// AI Agent API for MCP
export interface AIAgentAPI {
  connect(options?: AIAgentConfig): Promise<{ success: boolean; error?: string }>;
  disconnect(): Promise<{ success: boolean; error?: string }>;
  status(): Promise<AIAgentStatus>;
  
  listTools(): Promise<{ success: boolean; tools?: MCPTool[]; error?: string }>;
  callTool(name: string, args?: Record<string, unknown>): Promise<{ success: boolean; result?: MCPToolResult; error?: string }>;
  
  hardware: {
    validate(config: HardwareValidationRequest): Promise<{ success: boolean; result?: HardwareValidationResult; error?: string }>;
    planInit(params: { chip: string; peripheral: string }): Promise<{ success: boolean; result?: unknown; error?: string }>;
    reason(params: { question: string; context?: Record<string, unknown> }): Promise<{ success: boolean; result?: unknown; error?: string }>;
  };
  
  firmware: {
    analyze(params: FirmwareAnalysisRequest): Promise<{ success: boolean; result?: FirmwareAnalysisResult; error?: string }>;
    debug(params: { code: string; error: string }): Promise<{ success: boolean; result?: unknown; error?: string }>;
    generateCode(params: { spec: string; context?: string }): Promise<{ success: boolean; result?: unknown; error?: string }>;
  };
  
  knowledge: {
    query(params: { query: string; topK?: number }): Promise<{ success: boolean; result?: unknown; error?: string }>;
    crossValidate(params: Record<string, unknown>): Promise<{ success: boolean; result?: unknown; error?: string }>;
  };
  
  listResources(): Promise<{ success: boolean; resources?: MCPResource[]; error?: string }>;
  readResource(uri: string): Promise<{ success: boolean; resource?: unknown; error?: string }>;
  
  listPrompts(): Promise<{ success: boolean; prompts?: MCPPrompt[]; error?: string }>;
  getPrompt(name: string, args?: Record<string, unknown>): Promise<{ success: boolean; prompt?: unknown; error?: string }>;
  
  subscribe(eventName: string, channel: string): Promise<{ success: boolean; error?: string }>;
  unsubscribe(eventName: string): Promise<{ success: boolean; error?: string }>;
  onEvent(channel: string, callback: (event: AIAgentEvent) => void): void;
}
