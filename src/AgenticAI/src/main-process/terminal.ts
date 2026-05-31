import { spawn, ChildProcess } from 'child_process';

export interface TerminalSession {
  id: string;
  process: ChildProcess;
  write: (data: string) => void;
  resize: (cols: number, rows: number) => void;
  kill: () => void;
}

class TerminalManager {
  private sessions: Map<string, TerminalSession> = new Map();
  private nextId = 1;

  createSession(cwd: string = process.env.HOME || process.env.USERPROFILE || 'C:\\'): TerminalSession {
    const id = `term-${this.nextId++}`;
    
    const shell = process.platform === 'win32' ? 'powershell.exe' : 'bash';
    const shellArgs = process.platform === 'win32' ? ['-NoLogo'] : ['--login'];
    
    const proc = spawn(shell, shellArgs, {
      cwd,
      env: { ...process.env, TERM: 'xterm-256color' },
      shell: true,
    });

    const session: TerminalSession = {
      id,
      process: proc,
      write: (data: string) => {
        if (proc.stdin) {
          proc.stdin.write(data);
        }
      },
      resize: (cols: number, rows: number) => {
        // Note: node-pty would be needed for proper resize
        // This is a simplified version
      },
      kill: () => proc.kill(),
    };

    this.sessions.set(id, session);
    
    proc.on('exit', () => {
      this.sessions.delete(id);
    });

    return session;
  }

  getSession(id: string): TerminalSession | undefined {
    return this.sessions.get(id);
  }

  getAllSessions(): TerminalSession[] {
    return Array.from(this.sessions.values());
  }

  killSession(id: string): boolean {
    const session = this.sessions.get(id);
    if (session) {
      session.kill();
      this.sessions.delete(id);
      return true;
    }
    return false;
  }

  getOutput(id: string): string {
    // For simpler implementation, we'll track output through event handlers
    return '';
  }
}

export const terminalManager = new TerminalManager();
