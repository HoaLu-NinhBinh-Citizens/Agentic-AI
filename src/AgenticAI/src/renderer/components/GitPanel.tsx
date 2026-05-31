import React, { useState, useEffect, useCallback } from 'react';
import { FiGitBranch, FiRefreshCw, FiPlus, FiCheck, FiX, FiAlertCircle, FiCheckCircle } from 'react-icons/fi';
import { useAppStore, GitFileChange } from '../store/useAppStore';

interface GitCommit {
  hash: string;
  message: string;
  author: string;
  date: string;
}

export const GitPanel: React.FC = () => {
  const {
    workspacePath,
    gitBranch,
    setGitBranch,
    gitStatus,
    setGitStatus,
    gitLoading,
    setGitLoading,
    commitMessage,
    setCommitMessage
  } = useAppStore();

  const [isRepo, setIsRepo] = useState(true);
  const [commits, setCommits] = useState<GitCommit[]>([]);
  const [activeTab, setActiveTab] = useState<'changes' | 'commit'>('changes');
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [showBranchInput, setShowBranchInput] = useState(false);
  const [newBranchName, setNewBranchName] = useState('');
  const [isCommitting, setIsCommitting] = useState(false);

  // Load git info on mount or workspace change
  const loadGitInfo = useCallback(async () => {
    if (!workspacePath) return;
    setGitLoading(true);

    try {
      // Get basic git info
      const info = await window.electronAPI?.git?.info?.(workspacePath);
      if (info?.isRepo) {
        setIsRepo(true);
        setGitBranch(info.branch || 'main');

        // Get status
        await refreshStatus();

        // Get recent commits
        const log = await window.electronAPI?.git?.log?.(workspacePath, 10);
        if (Array.isArray(log)) {
          setCommits(log.map((c: any) => ({
            hash: c.hash?.substring(0, 7) || '',
            message: c.message || '',
            author: c.author || '',
            date: c.date || ''
          })));
        }
      } else {
        setIsRepo(false);
      }
    } catch (error) {
      console.error('Git info error:', error);
      setIsRepo(false);
    } finally {
      setGitLoading(false);
    }
  }, [workspacePath, setGitBranch, setGitLoading]);

  // Refresh status
  const refreshStatus = async () => {
    if (!workspacePath) return;
    try {
      const status = await window.electronAPI?.git?.status?.();
      if (status && typeof status === 'object') {
        // Parse git status output
        const files: GitFileChange[] = [];

        // Handle both array format and object format
        if (Array.isArray(status)) {
          status.forEach((s: any) => {
            files.push(parseGitStatus(s));
          });
        } else if (status.modified || status.staged || status.not_added) {
          // Object format
          if (status.modified) {
            status.modified.forEach((f: string) => files.push({ path: f, status: 'modified', staged: false }));
          }
          if (status.staged) {
            status.staged.forEach((f: string) => files.push({ path: f, status: 'modified', staged: true }));
          }
          if (status.not_added) {
            status.not_added.forEach((f: string) => files.push({ path: f, status: 'untracked', staged: false }));
          }
          if (status.deleted) {
            status.deleted.forEach((f: string) => files.push({ path: f, status: 'deleted', staged: false }));
          }
          if (status.created) {
            status.created.forEach((f: string) => files.push({ path: f, status: 'added', staged: false }));
          }
        }

        setGitStatus(files);
      }
    } catch (error) {
      console.error('Git status error:', error);
    }
  };

  // Parse git status line
  const parseGitStatus = (line: string): GitFileChange => {
    if (typeof line !== 'string' || line.length < 3) {
      return { path: line, status: 'modified', staged: false };
    }

    const index = line[0];
    const workTree = line[1];
    let status: GitFileChange['status'] = 'modified';
    let staged = false;

    // Determine status from porcelain format
    switch (index) {
      case 'A': status = 'added'; staged = true; break;
      case 'M': status = 'modified'; staged = true; break;
      case 'D': status = 'deleted'; staged = true; break;
      case 'R': status = 'renamed'; staged = true; break;
    }

    if (workTree === '?') {
      status = 'untracked';
      staged = false;
    } else if (workTree === 'M' || workTree === 'D') {
      status = workTree === 'D' ? 'deleted' : 'modified';
      staged = false;
    }

    const path = line.substring(3).split('\t')[0];
    return { path, status, staged };
  };

  useEffect(() => {
    loadGitInfo();
  }, [loadGitInfo]);

  // Show notification
  const showNotification = (type: 'success' | 'error', message: string) => {
    setNotification({ type, message });
    setTimeout(() => setNotification(null), 3000);
  };

  // Stage file
  const stageFile = async (file: GitFileChange) => {
    if (!workspacePath) return;
    try {
      const success = await window.electronAPI?.git?.stage?.(workspacePath, [file.path]);
      if (success) {
        await refreshStatus();
      } else {
        showNotification('error', `Failed to stage ${file.path}`);
      }
    } catch (error) {
      showNotification('error', `Error staging file`);
    }
  };

  // Unstage file
  const unstageFile = async (file: GitFileChange) => {
    if (!workspacePath) return;
    try {
      const success = await window.electronAPI?.git?.unstage?.(workspacePath, [file.path]);
      if (success) {
        await refreshStatus();
      } else {
        showNotification('error', `Failed to unstage ${file.path}`);
      }
    } catch (error) {
      showNotification('error', `Error unstaging file`);
    }
  };

  // Discard file changes
  const discardFile = async (file: GitFileChange) => {
    if (!workspacePath || file.status === 'untracked') return;
    try {
      const success = await window.electronAPI?.git?.discard?.(workspacePath, [file.path]);
      if (success) {
        await refreshStatus();
        showNotification('success', `Discarded changes to ${file.path}`);
      }
    } catch (error) {
      showNotification('error', `Error discarding changes`);
    }
  };

  // Stage all
  const stageAll = async () => {
    if (!workspacePath) return;
    const unstaged = gitStatus.filter(f => !f.staged);
    if (unstaged.length === 0) return;

    try {
      const success = await window.electronAPI?.git?.stage?.(
        workspacePath,
        unstaged.map(f => f.path)
      );
      if (success) {
        await refreshStatus();
        showNotification('success', `Staged ${unstaged.length} file(s)`);
      }
    } catch (error) {
      showNotification('error', `Error staging files`);
    }
  };

  // Unstage all
  const unstageAll = async () => {
    if (!workspacePath) return;
    const staged = gitStatus.filter(f => f.staged);
    if (staged.length === 0) return;

    try {
      const success = await window.electronAPI?.git?.unstage?.(
        workspacePath,
        staged.map(f => f.path)
      );
      if (success) {
        await refreshStatus();
      }
    } catch (error) {
      showNotification('error', `Error unstaging files`);
    }
  };

  // Commit
  const handleCommit = async () => {
    if (!workspacePath) return;
    if (!commitMessage.trim()) {
      showNotification('error', 'Please enter a commit message');
      return;
    }

    setIsCommitting(true);
    try {
      const success = await window.electronAPI?.git?.commit?.(workspacePath, commitMessage);
      if (success) {
        setCommitMessage('');
        await refreshStatus();
        await loadGitInfo();
        showNotification('success', 'Commit successful!');
      } else {
        showNotification('error', 'Commit failed. Make sure you have staged changes.');
      }
    } catch (error) {
      showNotification('error', `Commit error: ${error}`);
    } finally {
      setIsCommitting(false);
    }
  };

  // Create branch
  const handleCreateBranch = async () => {
    if (!workspacePath) return;
    if (!newBranchName.trim()) return;

    try {
      const result = await window.electronAPI?.git?.branch?.(workspacePath, newBranchName, true);
      if (result) {
        setGitBranch(newBranchName);
        setNewBranchName('');
        setShowBranchInput(false);
        showNotification('success', `Created branch: ${newBranchName}`);
      }
    } catch (error) {
      showNotification('error', `Error creating branch`);
    }
  };

  // Keyboard shortcut for commit
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'Enter') {
        if (activeTab === 'commit') {
          e.preventDefault();
          handleCommit();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab, commitMessage, workspacePath]);

  // Get status icon
  const getStatusIcon = (file: GitFileChange) => {
    if (file.staged) {
      return <FiCheck size={14} className="status-icon staged" />;
    }
    switch (file.status) {
      case 'modified': return <FiX size={14} className="status-icon modified" />;
      case 'deleted': return <FiX size={14} className="status-icon deleted" />;
      case 'untracked': return <FiX size={14} className="status-icon untracked" />;
      default: return <FiX size={14} className="status-icon" />;
    }
  };

  // Get file name from path
  const getFileName = (path: string) => {
    const parts = path.split(/[/\\]/);
    return parts[parts.length - 1];
  };

  const stagedFiles = gitStatus.filter(f => f.staged);
  const unstagedFiles = gitStatus.filter(f => !f.staged);

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

  if (!isRepo) {
    return (
      <div className="git-panel">
        <div className="git-header">
          <FiGitBranch size={16} />
          <span>Source Control</span>
        </div>
        <div className="git-content">
          <div className="git-not-repo">
            <FiAlertCircle size={32} />
            <p>Not a Git repository</p>
            <p className="hint">Initialize with: git init</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="git-panel">
      {/* Header */}
      <div className="git-header">
        <FiGitBranch size={16} />
        <span>Source Control</span>
        <span className="branch-indicator">{gitBranch}</span>
        <div className="header-actions">
          {showBranchInput ? (
            <div className="branch-input-group">
              <input
                type="text"
                placeholder="branch-name"
                value={newBranchName}
                onChange={(e) => setNewBranchName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreateBranch()}
                autoFocus
              />
              <button onClick={handleCreateBranch} title="Create branch"><FiCheck size={14} /></button>
              <button onClick={() => setShowBranchInput(false)} title="Cancel"><FiX size={14} /></button>
            </div>
          ) : (
            <>
              <button onClick={() => setShowBranchInput(true)} title="Create branch"><FiPlus size={14} /></button>
              <button onClick={loadGitInfo} title="Refresh" disabled={gitLoading}>
                <FiRefreshCw size={14} className={gitLoading ? 'spinning' : ''} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* Notification */}
      {notification && (
        <div className={`git-notification ${notification.type}`}>
          {notification.type === 'success' ? <FiCheckCircle size={14} /> : <FiAlertCircle size={14} />}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="git-tabs">
        <button
          className={activeTab === 'changes' ? 'active' : ''}
          onClick={() => setActiveTab('changes')}
        >
          Changes ({gitStatus.length})
        </button>
        <button
          className={activeTab === 'commit' ? 'active' : ''}
          onClick={() => setActiveTab('commit')}
        >
          Commit
        </button>
      </div>

      {/* Content */}
      <div className="git-content">
        {activeTab === 'changes' ? (
          <>
            {/* Staged */}
            {stagedFiles.length > 0 && (
              <div className="change-group">
                <div className="change-group-header">
                  <span>Staged Changes ({stagedFiles.length})</span>
                  <button onClick={unstageAll} className="unstage-all-btn">Unstage All</button>
                </div>
                {stagedFiles.map((file) => (
                  <div key={file.path} className={`change-item staged ${file.status}`}>
                    <button
                      className="stage-btn"
                      onClick={() => unstageFile(file)}
                      title="Unstage"
                    >
                      {getStatusIcon(file)}
                    </button>
                    <span className="file-path" title={file.path}>
                      {getFileName(file.path)}
                    </span>
                    <span className={`status-badge ${file.status}`}>
                      {file.status}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Unstaged */}
            {unstagedFiles.length > 0 && (
              <div className="change-group">
                <div className="change-group-header">
                  <span>Changes ({unstagedFiles.length})</span>
                  <button onClick={stageAll} className="stage-all-btn">Stage All</button>
                </div>
                {unstagedFiles.map((file) => (
                  <div key={file.path} className={`change-item ${file.status}`}>
                    <button
                      className="stage-btn"
                      onClick={() => stageFile(file)}
                      title="Stage"
                    >
                      {getStatusIcon(file)}
                    </button>
                    <span className="file-path" title={file.path}>
                      {getFileName(file.path)}
                    </span>
                    <div className="change-actions">
                      {file.status !== 'untracked' && (
                        <button
                          className="discard-btn"
                          onClick={() => discardFile(file)}
                          title="Discard changes"
                        >
                          <FiRefreshCw size={12} />
                        </button>
                      )}
                      <span className={`status-badge ${file.status}`}>
                        {file.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Empty state */}
            {gitStatus.length === 0 && !gitLoading && (
              <div className="no-changes">
                <FiCheckCircle size={24} />
                <p>No changes</p>
                <p className="hint">Working tree is clean</p>
              </div>
            )}

            {/* Loading */}
            {gitLoading && (
              <div className="git-loading">
                <div className="loading-spinner"></div>
                <p>Loading...</p>
              </div>
            )}
          </>
        ) : (
          <>
            {/* Commit form */}
            <div className="commit-form">
              <div className="commit-summary">
                <span className="staged-count">
                  {stagedFiles.length} file(s) staged
                </span>
              </div>

              <textarea
                className="commit-message-input"
                placeholder={`Message (Ctrl+Shift+Enter to commit on ${gitBranch})`}
                value={commitMessage}
                onChange={(e) => setCommitMessage(e.target.value)}
                rows={4}
              />

              <button
                className="commit-button"
                onClick={handleCommit}
                disabled={!commitMessage.trim() || stagedFiles.length === 0 || isCommitting}
              >
                {isCommitting ? (
                  <>
                    <div className="btn-spinner"></div>
                    Committing...
                  </>
                ) : (
                  <>
                    <FiCheck size={14} />
                    Commit
                  </>
                )}
              </button>
            </div>

            {/* Recent commits */}
            {commits.length > 0 && (
              <div className="commit-history">
                <h4>Recent Commits</h4>
                {commits.map((commit) => (
                  <div key={commit.hash} className="commit-item">
                    <div className="commit-message">{commit.message}</div>
                    <div className="commit-meta">
                      <span className="commit-hash">{commit.hash}</span>
                      <span className="commit-author">{commit.author}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};
