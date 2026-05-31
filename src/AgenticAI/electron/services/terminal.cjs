const { spawn } = require('child_process');

class TerminalManager {
  constructor() {
    this.sessions = new Map();
    this.nextId = 1;
  }

  createSession(cwd = process.env.HOME || process.env.USERPROFILE || 'C:\\') {
    const id = `term-${this.nextId++}`;
    
    const shell = process.platform === 'win32' ? 'powershell.exe' : 'bash';
    const shellArgs = process.platform === 'win32' ? ['-NoLogo'] : ['--login'];
    
    const proc = spawn(shell, shellArgs, {
      cwd,
      env: { ...process.env, TERM: 'xterm-256color' },
      shell: true,
    });

    const session = {
      id,
      process: proc,
      write: (data) => {
        if (proc.stdin) {
          proc.stdin.write(data);
        }
      },
      resize: (cols, rows) => {
        // Note: node-pty would be needed for proper resize
      },
      kill: () => proc.kill(),
    };

    this.sessions.set(id, session);
    
    proc.on('exit', () => {
      this.sessions.delete(id);
    });

    return session;
  }

  getSession(id) {
    return this.sessions.get(id);
  }

  getAllSessions() {
    return Array.from(this.sessions.values());
  }

  killSession(id) {
    const session = this.sessions.get(id);
    if (session) {
      session.kill();
      this.sessions.delete(id);
      return true;
    }
    return false;
  }
}

const terminalManager = new TerminalManager();
module.exports = { terminalManager };
