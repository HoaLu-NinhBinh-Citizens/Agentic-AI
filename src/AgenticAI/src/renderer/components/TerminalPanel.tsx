import React from 'react';
import { FiX, FiMinus } from 'react-icons/fi';

interface TerminalPanelProps {
  isOpen: boolean;
  onClose: () => void;
  onMinimize: () => void;
}

export const TerminalPanel: React.FC<TerminalPanelProps> = ({ isOpen, onClose, onMinimize }) => {
  if (!isOpen) return null;

  return (
    <div className="terminal-panel">
      <div className="terminal-header">
        <span className="terminal-title">Terminal</span>
        <div className="terminal-actions">
          <button onClick={onMinimize} title="Minimize"><FiMinus size={14} /></button>
          <button onClick={onClose} title="Close"><FiX size={14} /></button>
        </div>
      </div>
      <div className="terminal-content">
        <div className="terminal-placeholder">
          <p>Terminal integration coming soon...</p>
          <p className="hint">This panel will support real terminal sessions in a future update.</p>
          <div className="terminal-preview">
            <p>$ <span className="cursor">_</span></p>
          </div>
        </div>
      </div>
    </div>
  );
};
