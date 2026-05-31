import React, { useState, useEffect } from 'react';
import { FiGitBranch, FiRefreshCw } from 'react-icons/fi';
import { useAppStore } from '../store/useAppStore';

export const GitPanel: React.FC = () => {
  const { workspacePath } = useAppStore();
  const [gitBranch, setGitBranch] = useState('main');

  useEffect(() => {
    const loadGitInfo = async () => {
      if (window.electronAPI?.gitBranch && workspacePath) {
        const branch = await window.electronAPI.gitBranch(workspacePath);
        if (branch) {
          setGitBranch(branch);
        }
      }
    };
    loadGitInfo();
  }, [workspacePath]);

  if (!workspacePath) {
    return (
      <div className="git-panel">
        <div className="git-header">
          <FiGitBranch size={16} />
          <span>Source Control</span>
        </div>
        <div className="git-content">
          <div className="git-placeholder">
            <FiGitBranch size={48} />
            <p>Open a folder to see git status</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="git-panel">
      <div className="git-header">
        <FiGitBranch size={16} />
        <span>Source Control</span>
        <span className="branch-indicator">{gitBranch}</span>
        <button className="refresh-btn" title="Refresh" onClick={() => window.location.reload()}>
          <FiRefreshCw size={14} />
        </button>
      </div>
      <div className="git-content">
        <div className="git-placeholder">
          <FiGitBranch size={48} />
          <p>Git integration</p>
          <p className="hint">View changes, stage files, and commit directly from the editor.</p>
        </div>
        
        {/* Placeholder for future: */}
        <div className="git-changes">
          <h4>Changes</h4>
          <div className="change-item placeholder">
            <span>src/file.tsx</span>
            <span className="badge">Modified</span>
          </div>
        </div>
        
        <div className="git-commits">
          <h4>Recent Commits</h4>
          <div className="commit-item placeholder">
            <span className="hash">abc1234</span>
            <span className="message">Update feature</span>
          </div>
        </div>
      </div>
    </div>
  );
};
