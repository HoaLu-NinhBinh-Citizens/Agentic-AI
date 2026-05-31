import React, { useState, useCallback, useRef, useEffect } from 'react';

export interface SearchResult {
  file: string;
  line: number;
  column: number;
  match: string;
  context: string;
}

interface SearchPanelProps {
  workspacePath: string;
  onResultClick: (file: string, line: number) => void;
}

export const SearchPanel: React.FC<SearchPanelProps> = ({ workspacePath, onResultClick }) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [wholeWord, setWholeWord] = useState(false);
  const [regex, setRegex] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSearch = useCallback(async () => {
    if (!query.trim() || !workspacePath) return;

    setIsSearching(true);
    setError(null);
    
    try {
      if (window.electronAPI?.search) {
        const searchResults = await window.electronAPI.search({
          query,
          path: workspacePath,
          caseSensitive,
          wholeWord,
          regex,
        });
        setResults(searchResults);
      } else {
        setResults([]);
        setError('Search functionality not available');
      }
    } catch (err) {
      console.error('Search failed:', err);
      setResults([]);
      setError('Search failed. Make sure ripgrep is installed.');
    } finally {
      setIsSearching(false);
    }
  }, [query, workspacePath, caseSensitive, wholeWord, regex]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleResultClick = (result: SearchResult) => {
    onResultClick(result.file, result.line);
  };

  const getFileName = (filePath: string): string => {
    return filePath.split(/[/\\]/).pop() || filePath;
  };

  const getDirectory = (filePath: string): string => {
    const parts = filePath.split(/[/\\]/);
    parts.pop();
    return parts.join('/');
  };

  return (
    <div className="search-panel">
      <div className="search-input-container">
        <input
          ref={inputRef}
          type="text"
          placeholder="Search in files... (Ctrl+Shift+F)"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <button onClick={handleSearch} disabled={isSearching || !query.trim()}>
          {isSearching ? '...' : '🔍'}
        </button>
      </div>

      <div className="search-options">
        <label>
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={e => setCaseSensitive(e.target.checked)}
          />
          Case sensitive
        </label>
        <label>
          <input
            type="checkbox"
            checked={wholeWord}
            onChange={e => setWholeWord(e.target.checked)}
          />
          Whole word
        </label>
        <label>
          <input
            type="checkbox"
            checked={regex}
            onChange={e => setRegex(e.target.checked)}
          />
          Regex
        </label>
      </div>

      <div className="search-results">
        {error && (
          <div className="search-error">{error}</div>
        )}
        
        {!error && results.length > 0 && (
          <>
            <div className="results-count">
              {results.length} result{results.length !== 1 ? 's' : ''} found
            </div>
            {results.map((result, index) => (
              <div
                key={`${result.file}:${result.line}:${index}`}
                className="search-result"
                onClick={() => handleResultClick(result)}
              >
                <div className="result-header">
                  <span className="result-file">{getFileName(result.file)}</span>
                  <span className="result-location">Line {result.line}</span>
                </div>
                <div className="result-path">{getDirectory(result.file)}</div>
                <div className="result-match">
                  {result.match || <em>No match text</em>}
                </div>
              </div>
            ))}
          </>
        )}
        
        {!error && query && !isSearching && results.length === 0 && (
          <div className="no-results">
            No results found for "{query}"
          </div>
        )}
        
        {!error && !query && (
          <div className="search-hint">
            Enter a search query to find files
          </div>
        )}
      </div>
    </div>
  );
};
