import React, { useState, useEffect, useCallback } from 'react';

interface GitStatus {
  modified: string[];
  staged: string[];
  created: string[];
  deleted: string[];
  not_added: string[];
  current: string;
  tracking: string | null;
}

interface GitInfo {
  isRepo: boolean;
  branch: string;
  branches: string[];
  status: GitStatus | null;
  remotes: string[];
}

interface CommitInfo {
  hash: string;
  message: string;
  author: string;
  date: string;
}

interface GitPanelProps {
  workspacePath: string;
  onCommit?: () => void;
}

export const GitPanel: React.FC<GitPanelProps> = ({ workspacePath, onCommit }) => {
  const [gitInfo, setGitInfo] = useState<GitInfo | null>(null);
  const [recentCommits, setRecentCommits] = useState<CommitInfo[]>([]);
  const [activeTab, setActiveTab] = useState<'changes' | 'commit' | 'history'>('changes');
  const [commitMessage, setCommitMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const loadGitInfo = useCallback(async () => {
    if (!workspacePath || !window.electronAPI?.gitInfo) return;

    try {
      const info = await window.electronAPI.gitInfo(workspacePath);
      setGitInfo(info);
    } catch (error) {
      console.error('Failed to load git info:', error);
    }
  }, [workspacePath]);

  const loadCommitHistory = useCallback(async () => {
    if (!workspacePath || !window.electronAPI?.gitLog) return;

    try {
      const commits = await window.electronAPI.gitLog(workspacePath, 50);
      setRecentCommits(commits);
    } catch (error) {
      console.error('Failed to load commit history:', error);
    }
  }, [workspacePath]);

  useEffect(() => {
    loadGitInfo();
    loadCommitHistory();
  }, [loadGitInfo, loadCommitHistory]);

  const handleStage = async (file: string) => {
    if (!window.electronAPI?.gitStage) return;

    try {
      await window.electronAPI.gitStage(workspacePath, [file]);
      await loadGitInfo();
    } catch (error) {
      console.error('Failed to stage file:', error);
    }
  };

  const handleStageAll = async () => {
    if (!window.electronAPI?.gitStage) return;

    const filesToStage = [
      ...(gitInfo?.status?.modified || []),
      ...(gitInfo?.status?.created || []),
      ...(gitInfo?.status?.not_added || []),
    ];

    if (filesToStage.length === 0) return;

    try {
      await window.electronAPI.gitStage(workspacePath, filesToStage);
      await loadGitInfo();
    } catch (error) {
      console.error('Failed to stage files:', error);
    }
  };

  const handleCommit = async () => {
    if (!commitMessage.trim() || !window.electronAPI?.gitCommit) return;

    setIsLoading(true);
    try {
      await window.electronAPI.gitCommit(workspacePath, commitMessage);
      setCommitMessage('');
      await loadGitInfo();
      await loadCommitHistory();
      onCommit?.();
    } catch (error) {
      console.error('Failed to commit:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCheckout = async (branchName: string) => {
    if (!window.electronAPI?.gitCheckout) return;

    try {
      await window.electronAPI.gitCheckout(workspacePath, branchName);
      await loadGitInfo();
    } catch (error) {
      console.error('Failed to checkout:', error);
    }
  };

  if (!gitInfo) {
    return (
      <div className="git-panel">
        <div className="git-loading">Loading...</div>
      </div>
    );
  }

  if (!gitInfo.isRepo) {
    return (
      <div className="git-panel">
        <div className="not-a-repo">
          <p>Not a Git repository</p>
        </div>
      </div>
    );
  }

  const status = gitInfo.status;

  return (
    <div className="git-panel">
      <div className="git-header">
        <span className="branch-indicator">
           {gitInfo.branch}
        </span>
      </div>

      <div className="git-tabs">
        <button 
          className={activeTab === 'changes' ? 'active' : ''}
          onClick={() => setActiveTab('changes')}
        >
          Changes
        </button>
        <button 
          className={activeTab === 'commit' ? 'active' : ''}
          onClick={() => setActiveTab('commit')}
        >
          Commit
        </button>
        <button 
          className={activeTab === 'history' ? 'active' : ''}
          onClick={() => setActiveTab('history')}
        >
          History
        </button>
      </div>

      <div className="git-content">
        {activeTab === 'changes' && status && (
          <div className="changes-list">
            {status.modified?.length > 0 && (
              <div className="change-group">
                <h4>Modified</h4>
                {status.modified.map(file => (
                  <div key={file} className="change-item modified">
                    <span className="file-name">{file}</span>
                    <button onClick={() => handleStage(file)}>+</button>
                  </div>
                ))}
              </div>
            )}
            {status.staged?.length > 0 && (
              <div className="change-group">
                <h4>Staged</h4>
                {status.staged.map(file => (
                  <div key={file} className="change-item staged">
                    <span className="file-name">{file}</span>
                  </div>
                ))}
              </div>
            )}
            {(status.created?.length > 0 || status.not_added?.length > 0) && (
              <div className="change-group">
                <h4>Untracked</h4>
                {[...status.created, ...status.not_added].map(file => (
                  <div key={file} className="change-item untracked">
                    <span className="file-name">{file}</span>
                    <button onClick={() => handleStage(file)}>+</button>
                  </div>
                ))}
              </div>
            )}
            {status.deleted?.length > 0 && (
              <div className="change-group">
                <h4>Deleted</h4>
                {status.deleted.map(file => (
                  <div key={file} className="change-item deleted">
                    <span className="file-name">{file}</span>
                    <button onClick={() => handleStage(file)}>+</button>
                  </div>
                ))}
              </div>
            )}
            {status.modified?.length === 0 && status.created?.length === 0 && 
             status.staged?.length === 0 && status.deleted?.length === 0 && (
              <div className="no-changes">No changes detected</div>
            )}
            {(status.modified?.length > 0 || status.created?.length > 0 || 
              status.not_added?.length > 0 || status.deleted?.length > 0) && (
              <button className="stage-all-button" onClick={handleStageAll}>
                Stage All Changes
              </button>
            )}
          </div>
        )}

        {activeTab === 'commit' && (
          <div className="commit-form">
            <textarea
              placeholder="Commit message..."
              value={commitMessage}
              onChange={e => setCommitMessage(e.target.value)}
              rows={4}
            />
            <button 
              className="commit-button" 
              onClick={handleCommit}
              disabled={!commitMessage.trim() || isLoading}
            >
              {isLoading ? 'Committing...' : 'Commit'}
            </button>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="commit-history">
            {recentCommits.length > 0 ? (
              recentCommits.map(commit => (
                <div key={commit.hash} className="commit-item">
                  <div className="commit-message">{commit.message}</div>
                  <div className="commit-meta">
                    <span className="commit-author">{commit.author}</span>
                    <span className="commit-date">{commit.date}</span>
                  </div>
                  <div className="commit-hash">{commit.hash.substring(0, 7)}</div>
                </div>
              ))
            ) : (
              <div className="no-commits">No commits yet</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
