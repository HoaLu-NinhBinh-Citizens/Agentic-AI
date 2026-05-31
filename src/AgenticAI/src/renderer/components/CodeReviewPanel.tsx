import React, { useState, useMemo } from 'react';
import { CodeIssue } from '../../shared/types';

interface CodeReviewPanelProps {
  issues: CodeIssue[];
  onIssueClick?: (issue: CodeIssue) => void;
  onApplyFix?: (issueId: string) => void;
  onFixAll?: (issues: CodeIssue[]) => void;
  isLoading?: boolean;
  title?: string;
}

type SeverityFilter = 'all' | 'error' | 'warning' | 'info';
type SortBy = 'severity' | 'line' | 'rule';

export const CodeReviewPanel: React.FC<CodeReviewPanelProps> = ({
  issues,
  onIssueClick,
  onApplyFix,
  onFixAll,
  isLoading = false,
  title = 'Code Review',
}) => {
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const [sortBy, setSortBy] = useState<SortBy>('severity');
  const [expandedIssue, setExpandedIssue] = useState<string | null>(null);

  // Count issues by severity
  const issueCounts = useMemo(() => {
    return {
      error: issues.filter(i => i.severity === 'error').length,
      warning: issues.filter(i => i.severity === 'warning').length,
      info: issues.filter(i => i.severity === 'info').length,
    };
  }, [issues]);

  // Filter and sort issues
  const filteredIssues = useMemo(() => {
    let filtered = issues;

    // Apply severity filter
    if (severityFilter !== 'all') {
      filtered = filtered.filter(i => i.severity === severityFilter);
    }

    // Apply sorting
    const sorted = [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'severity': {
          const severityOrder = { error: 0, warning: 1, info: 2 };
          const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
          if (severityDiff !== 0) return severityDiff;
          return a.line - b.line;
        }
        case 'line':
          return a.line - b.line;
        case 'rule':
          return a.rule.localeCompare(b.rule);
        default:
          return 0;
      }
    });

    return sorted;
  }, [issues, severityFilter, sortBy]);

  // Issues with fixes available
  const issuesWithFixes = useMemo(() => {
    return issues.filter(i => i.fix);
  }, [issues]);

  const severityColors: Record<string, string> = {
    error: '#f14c4c',
    warning: '#dcdcaa',
    info: '#4ec9b0',
  };

  const severityIcons: Record<string, JSX.Element> = {
    error: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
      </svg>
    ),
    warning: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z" />
      </svg>
    ),
    info: (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z" />
      </svg>
    ),
  };

  if (isLoading) {
    return (
      <div className="review-panel loading">
        <div className="review-header">
          <h3>{title}</h3>
        </div>
        <div className="review-loading">
          <div className="loading-spinner" />
          <p>Analyzing code...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="review-panel">
      <div className="review-header">
        <h3>{title}</h3>
        <span className="issue-count">{issues.length} issues</span>
      </div>

      {issues.length > 0 && (
        <>
          <div className="review-summary">
            <button
              className={`summary-item error ${severityFilter === 'error' ? 'active' : ''}`}
              onClick={() => setSeverityFilter(severityFilter === 'error' ? 'all' : 'error')}
            >
              <span className="count">{issueCounts.error}</span>
              <span className="label">errors</span>
            </button>
            <button
              className={`summary-item warning ${severityFilter === 'warning' ? 'active' : ''}`}
              onClick={() => setSeverityFilter(severityFilter === 'warning' ? 'all' : 'warning')}
            >
              <span className="count">{issueCounts.warning}</span>
              <span className="label">warnings</span>
            </button>
            <button
              className={`summary-item info ${severityFilter === 'info' ? 'active' : ''}`}
              onClick={() => setSeverityFilter(severityFilter === 'info' ? 'all' : 'info')}
            >
              <span className="count">{issueCounts.info}</span>
              <span className="label">info</span>
            </button>
          </div>

          <div className="review-toolbar">
            <select
              className="sort-select"
              value={sortBy}
              onChange={e => setSortBy(e.target.value as SortBy)}
            >
              <option value="severity">Sort by Severity</option>
              <option value="line">Sort by Line</option>
              <option value="rule">Sort by Rule</option>
            </select>

            {issuesWithFixes.length > 0 && onFixAll && (
              <button
                className="fix-all-button"
                onClick={() => onFixAll(issuesWithFixes)}
              >
                Fix All ({issuesWithFixes.length})
              </button>
            )}
          </div>

          <div className="review-list">
            {filteredIssues.map(issue => (
              <div
                key={issue.id}
                className={`review-issue severity-${issue.severity} ${expandedIssue === issue.id ? 'expanded' : ''}`}
                onClick={() => {
                  setExpandedIssue(expandedIssue === issue.id ? null : issue.id);
                  onIssueClick?.(issue);
                }}
              >
                <div className="issue-header">
                  <span
                    className="severity-badge"
                    style={{ background: severityColors[issue.severity] }}
                  >
                    {severityIcons[issue.severity]}
                    {issue.rule}
                  </span>
                  <span className="issue-location">Line {issue.line}</span>
                  {issue.column && <span className="issue-location">Col {issue.column}</span>}
                </div>

                <p className="issue-message">{issue.message}</p>

                {expandedIssue === issue.id && issue.fix && (
                  <div className="issue-details">
                    <div className="fix-preview">
                      <div className="fix-section">
                        <span className="fix-label">Original:</span>
                        <pre className="code-block remove">{issue.fix.original}</pre>
                      </div>
                      <div className="fix-section">
                        <span className="fix-label">Replacement:</span>
                        <pre className="code-block add">{issue.fix.replacement}</pre>
                      </div>
                    </div>

                    {onApplyFix && (
                      <button
                        className="apply-fix-button"
                        onClick={e => {
                          e.stopPropagation();
                          onApplyFix(issue.id);
                        }}
                      >
                        Apply Fix
                      </button>
                    )}
                  </div>
                )}

                {!expandedIssue && issue.fix && (
                  <span className="fix-available">Fix available</span>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {issues.length === 0 && (
        <div className="review-empty">
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
            <polyline points="22 4 12 14.01 9 11.01" />
          </svg>
          <h4>No Issues Found</h4>
          <p>Your code looks clean!</p>
        </div>
      )}
    </div>
  );
};

export default CodeReviewPanel;
