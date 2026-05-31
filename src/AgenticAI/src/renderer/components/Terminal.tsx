import React, { useEffect, useRef, useState } from 'react';
import { Terminal as XTerminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

interface TerminalProps {
  sessionId?: string;
  onClose?: () => void;
}

export const Terminal: React.FC<TerminalProps> = ({ sessionId, onClose }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const terminalRef = useRef<XTerminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(sessionId || null);

  useEffect(() => {
    if (!containerRef.current) return;

    const terminal = new XTerminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Fira Code, Consolas, monospace',
      theme: {
        background: '#1e1e1e',
        foreground: '#cccccc',
        cursor: '#ffffff',
      },
    });

    const fitAddon = new FitAddon();
    terminal.loadAddon(fitAddon);

    terminal.open(containerRef.current);
    fitAddon.fit();

    terminalRef.current = terminal;
    fitAddonRef.current = fitAddon;

    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit();
    });
    resizeObserver.observe(containerRef.current);

    const createTerminalSession = async () => {
      if (window.electronAPI?.terminalCreate) {
        try {
          const session = await window.electronAPI.terminalCreate();
          setCurrentSessionId(session.id);
          setIsConnected(true);

          terminal.onData(data => {
            window.electronAPI?.terminalInput(session.id, data);
          });

          window.electronAPI?.terminalOnOutput(session.id, (output: string) => {
            terminal.write(output);
          });
        } catch {
          createLocalFallback(terminal);
        }
      } else {
        createLocalFallback(terminal);
      }
    };

    const createLocalFallback = (term: XTerminal) => {
      term.write('Terminal mode (local)\r\n$ ');
      
      term.onData(data => {
        term.write(data);
        if (data === '\r') {
          term.write('\r\n$ ');
        }
      });
      
      setIsConnected(true);
    };

    createTerminalSession();

    return () => {
      resizeObserver.disconnect();
      terminal.dispose();
      
      if (currentSessionId && window.electronAPI?.terminalClose) {
        window.electronAPI.terminalClose(currentSessionId);
      }
    };
  }, []);

  const handleClose = () => {
    if (currentSessionId && window.electronAPI?.terminalClose) {
      window.electronAPI.terminalClose(currentSessionId);
    }
    onClose?.();
  };

  return (
    <div className="terminal-container">
      <div className="terminal-header">
        <span>Terminal</span>
        <div className="terminal-actions">
          <span className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
          {onClose && <button onClick={handleClose}>×</button>}
        </div>
      </div>
      <div ref={containerRef} className="terminal-content" />
    </div>
  );
};
