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
