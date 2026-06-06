import React, { useState, useEffect } from 'react';
import { FiMinus, FiMaximize2, FiX, FiSquare } from 'react-icons/fi';

export const TitleBar: React.FC = () => {
  const [isMaximized, setIsMaximized] = useState(false);

  const handleMinimize = () => {
    window.electronAPI?.app?.minimize();
  };

  const handleMaximize = () => {
    window.electronAPI?.app?.maximize();
    setIsMaximized(!isMaximized);
  };

  const handleClose = () => {
    window.electronAPI?.app?.close();
  };

  return (
    <div className="custom-titlebar">
      <div className="titlebar-drag-area">
        <span className="titlebar-title">AgenticAI</span>
      </div>
      <div className="titlebar-controls">
        <button 
          className="titlebar-btn minimize" 
          onClick={handleMinimize}
          title="Minimize"
        >
          <FiMinus size={14} />
        </button>
        <button 
          className="titlebar-btn maximize" 
          onClick={handleMaximize}
          title={isMaximized ? "Restore" : "Maximize"}
        >
          {isMaximized ? <FiSquare size={12} /> : <FiMaximize2 size={12} />}
        </button>
        <button 
          className="titlebar-btn close" 
          onClick={handleClose}
          title="Close"
        >
          <FiX size={14} />
        </button>
      </div>
    </div>
  );
};
