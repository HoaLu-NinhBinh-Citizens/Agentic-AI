import React, { useState } from 'react';
import { FiSearch, FiRefreshCw } from 'react-icons/fi';
import { useAppStore } from '../store/useAppStore';

export const SearchPanel: React.FC = () => {
  const { workspacePath } = useAppStore();
  const [query, setQuery] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [regex, setRegex] = useState(false);

  if (!workspacePath) {
    return (
      <div className="search-panel">
        <div className="search-header">
          <FiSearch size={16} />
          <span>Search</span>
        </div>
        <div className="search-content">
          <div className="search-placeholder">
            <FiSearch size={48} />
            <p>Open a folder to search</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="search-panel">
      <div className="search-header">
        <FiSearch size={16} />
        <span>Search</span>
        <button className="refresh-btn" title="Refresh"><FiRefreshCw size={14} /></button>
      </div>
      <div className="search-input-container">
        <input
          type="text"
          placeholder="Search..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
      </div>
      <div className="search-options">
        <label>
          <input type="checkbox" checked={caseSensitive} onChange={e => setCaseSensitive(e.target.checked)} />
          Case Sensitive
        </label>
        <label>
          <input type="checkbox" checked={wholeWord} onChange={e => setWholeWord(e.target.checked)} />
          Whole Word
        </label>
        <label>
          <input type="checkbox" checked={regex} onChange={e => setRegex(e.target.checked)} />
          Regex
        </label>
      </div>
      <div className="search-content">
        <div className="search-placeholder">
          <FiSearch size={48} />
          <p>Global search</p>
          <p className="hint">Search across all files in your workspace.</p>
        </div>
      </div>
    </div>
  );
};
