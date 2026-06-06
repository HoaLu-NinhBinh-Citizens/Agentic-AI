import React, { useState } from 'react';
import { FiCheck, FiX, FiEye, FiChevronDown, FiChevronRight } from 'react-icons/fi';

export interface DiffHunk {
  id: string;
  filePath: string;
  oldContent: string;
  newContent: string;
  startLine: number;
  status: 'pending' | 'accepted' | 'rejected';
}

interface InlineDiffViewProps {
  hunks: DiffHunk[];
  onAcceptHunk: (id: string) => void;
  onRejectHunk: (id: string) => void;
  onAcceptAll: () => void;
  onRejectAll: () => void;
  onViewAll: () => void;
}

export const InlineDiffView: React.FC<InlineDiffViewProps> = ({
  hunks,
  onAcceptHunk,
  onRejectHunk,
  onAcceptAll,
  onRejectAll,
  onViewAll,
}) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const acceptedCount = hunks.filter(h => h.status === 'accepted').length;
  const pendingCount = hunks.filter(h => h.status === 'pending').length;
  const totalCount = hunks.length;

  if (totalCount === 0) return null;

  return (
    <div className="inline-diff-view">
      <div className="diff-summary-bar">
        <button 
          className="diff-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? <FiChevronDown size={12} /> : <FiChevronRight size={12} />}
        </button>

        <span className="diff-count">
          {pendingCount > 0 
            ? `${pendingCount} changes pending`
            : `${acceptedCount} changes accepted`
          }
        </span>

        <div className="diff-actions">
          <button className="diff-action-btn" onClick={onViewAll} title="View all changes">
            <FiEye size={12} /> View all
          </button>
          {pendingCount > 0 && (
            <>
              <button 
                className="diff-action-btn accept" 
                onClick={onAcceptAll}
                title="Accept all"
              >
                <FiCheck size={12} /> Accept
              </button>
              <button 
                className="diff-action-btn reject"
                onClick={onRejectAll}
                title="Reject all"
              >
                <FiX size={12} /> Reject
              </button>
            </>
          )}
        </div>
      </div>

      {isExpanded && pendingCount > 0 && (
        <div className="diff-hunks">
          {hunks.filter(h => h.status === 'pending').map(hunk => (
            <DiffHunkItem
              key={hunk.id}
              hunk={hunk}
              onAccept={() => onAcceptHunk(hunk.id)}
              onReject={() => onRejectHunk(hunk.id)}
            />
          ))}
        </div>
      )}
    </div>
  );
};

interface DiffHunkItemProps {
  hunk: DiffHunk;
  onAccept: () => void;
  onReject: () => void;
}

const DiffHunkItem: React.FC<DiffHunkItemProps> = ({ hunk, onAccept, onReject }) => {
  const oldLines = hunk.oldContent.split('\n');
  const newLines = hunk.newContent.split('\n');

  return (
    <div className="diff-hunk-item">
      <div className="diff-hunk-header">
        <span className="diff-file-path">{hunk.filePath.split(/[/\\]/).pop()}</span>
        <span className="diff-line-info">Line {hunk.startLine}</span>
        <div className="diff-hunk-actions">
          <button className="hunk-accept" onClick={onAccept} title="Accept">
            <FiCheck size={11} />
          </button>
          <button className="hunk-reject" onClick={onReject} title="Reject">
            <FiX size={11} />
          </button>
        </div>
      </div>
      <div className="diff-hunk-content">
        {oldLines.map((line, i) => (
          <div key={`old-${i}`} className="diff-line removed">
            <span className="diff-gutter">-</span>
            <code>{line}</code>
          </div>
        ))}
        {newLines.map((line, i) => (
          <div key={`new-${i}`} className="diff-line added">
            <span className="diff-gutter">+</span>
            <code>{line}</code>
          </div>
        ))}
      </div>
    </div>
  );
};
