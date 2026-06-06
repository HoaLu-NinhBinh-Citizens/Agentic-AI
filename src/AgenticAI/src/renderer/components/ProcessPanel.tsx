import React, { useState, useRef, useEffect } from 'react';
import { FiTerminal, FiX, FiPlay, FiTrash2, FiChevronDown, FiChevronRight } from 'react-icons/fi';

export interface ProcessLog {
  id: string;
  command: string;
  output: string[];
  status: 'running' | 'completed' | 'error';
  startTime: string;
}

interface ProcessPanelProps {
  processes?: ProcessLog[];
  onClear?: () => void;
  onStopProcess?: (id: string) => void;
}

export const ProcessPanel: React.FC<ProcessPanelProps> = ({
  processes: externalProcesses,
  onClear,
  onStopProcess,
}) => {
  const [processes, setProcesses] = useState<ProcessLog[]>(externalProcesses || []);
  const [expandedProcess, setExpandedProcess] = useState<string | null>(null);
  const outputRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (externalProcesses) {
      setProcesses(externalProcesses);
    }
  }, [externalProcesses]);

  useEffect(() => {
    // Auto-scroll to bottom when new output arrives
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight;
    }
  }, [processes]);

  // Listen for process events from electron
  useEffect(() => {
    const handleProcessOutput = (_event: any, data: { id: string; line: string }) => {
      setProcesses(prev => prev.map(p => 
        p.id === data.id 
          ? { ...p, output: [...p.output, data.line] }
          : p
      ));
    };

    const handleProcessStart = (_event: any, data: { id: string; command: string }) => {
      const newProcess: ProcessLog = {
        id: data.id,
        command: data.command,
        output: [],
        status: 'running',
        startTime: new Date().toISOString(),
      };
      setProcesses(prev => [...prev, newProcess]);
      setExpandedProcess(data.id);
    };

    const handleProcessEnd = (_event: any, data: { id: string; exitCode: number }) => {
      setProcesses(prev => prev.map(p =>
        p.id === data.id
          ? { ...p, status: data.exitCode === 0 ? 'completed' : 'error' }
          : p
      ));
    };

    if (window.electronAPI) {
      window.electronAPI.on?.('process:output', handleProcessOutput);
      window.electronAPI.on?.('process:start', handleProcessStart);
      window.electronAPI.on?.('process:end', handleProcessEnd);
    }

    return () => {
      if (window.electronAPI) {
        window.electronAPI.off?.('process:output', handleProcessOutput);
        window.electronAPI.off?.('process:start', handleProcessStart);
        window.electronAPI.off?.('process:end', handleProcessEnd);
      }
    };
  }, []);

  const getStatusIcon = (status: ProcessLog['status']) => {
    switch (status) {
      case 'running': return <span className="process-status running">●</span>;
      case 'completed': return <span className="process-status completed">✓</span>;
      case 'error': return <span className="process-status error">✗</span>;
    }
  };

  const activeProcess = processes.find(p => p.id === expandedProcess) || processes[processes.length - 1];

  return (
    <div className="process-panel">
      <div className="process-panel-header">
        <div className="process-tabs">
          {processes.map(p => (
            <button
              key={p.id}
              className={`process-tab ${p.id === activeProcess?.id ? 'active' : ''}`}
              onClick={() => setExpandedProcess(p.id)}
            >
              {getStatusIcon(p.status)}
              <span className="process-tab-label">
                {p.command.length > 20 ? p.command.slice(0, 20) + '...' : p.command}
              </span>
            </button>
          ))}
          {processes.length === 0 && (
            <span className="process-empty-label">
              <FiTerminal size={12} /> No processes
            </span>
          )}
        </div>
        <div className="process-actions">
          <button onClick={onClear} title="Clear all"><FiTrash2 size={12} /></button>
        </div>
      </div>

      <div className="process-output" ref={outputRef}>
        {activeProcess ? (
          <>
            <div className="process-command-line">
              <FiPlay size={10} />
              <code>{activeProcess.command}</code>
            </div>
            {activeProcess.output.map((line, i) => (
              <div key={i} className="process-output-line">
                {line}
              </div>
            ))}
            {activeProcess.status === 'running' && (
              <div className="process-output-line process-cursor">▊</div>
            )}
          </>
        ) : (
          <div className="process-placeholder">
            <FiTerminal size={16} />
            <span>Process output will appear here</span>
          </div>
        )}
      </div>
    </div>
  );
};
