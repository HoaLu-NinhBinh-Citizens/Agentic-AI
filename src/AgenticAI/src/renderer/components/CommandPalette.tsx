import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Command } from '../../shared/types';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  commands: Command[];
  onSelect: (commandId: string) => void;
  recentCommands?: string[];
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({
  isOpen,
  onClose,
  commands,
  onSelect,
  recentCommands = [],
}) => {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Filter commands based on search query
  const filteredCommands = React.useMemo(() => {
    if (!query.trim()) {
      // Show recent commands first when no query
      const recent = commands.filter(cmd => recentCommands.includes(cmd.id));
      const others = commands.filter(cmd => !recentCommands.includes(cmd.id));
      return [...recent, ...others];
    }

    const lowerQuery = query.toLowerCase().trim();
    const queryWords = lowerQuery.split(/\s+/);

    return commands.filter(cmd => {
      const label = cmd.label.toLowerCase();
      const category = cmd.category.toLowerCase();
      const id = cmd.id.toLowerCase();

      return queryWords.every(word =>
        label.includes(word) ||
        category.includes(word) ||
        id.includes(word)
      );
    }).sort((a, b) => {
      // Prioritize exact matches
      const aStartsWith = a.label.toLowerCase().startsWith(lowerQuery);
      const bStartsWith = b.label.toLowerCase().startsWith(lowerQuery);
      if (aStartsWith && !bStartsWith) return -1;
      if (bStartsWith && !aStartsWith) return 1;

      // Then by recent usage
      const aRecent = recentCommands.indexOf(a.id);
      const bRecent = recentCommands.indexOf(b.id);
      if (aRecent !== -1 && bRecent === -1) return -1;
      if (bRecent !== -1 && aRecent === -1) return 1;
      if (aRecent !== -1 && bRecent !== -1 && aRecent < bRecent) return -1;

      return 0;
    });
  }, [commands, query, recentCommands]);

  // Reset selected index when filter changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      inputRef.current?.focus();
    }
  }, [isOpen]);

  // Scroll selected item into view
  useEffect(() => {
    if (listRef.current) {
      const selectedElement = listRef.current.querySelector('.command-item.selected');
      if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(i => Math.min(i + 1, filteredCommands.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(i => Math.max(i - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          onSelect(filteredCommands[selectedIndex].id);
          onClose();
        }
        break;
      case 'Escape':
        e.preventDefault();
        onClose();
        break;
      case 'Tab':
        e.preventDefault();
        if (filteredCommands.length > 0) {
          const nextIndex = (selectedIndex + 1) % filteredCommands.length;
          setSelectedIndex(nextIndex);
        }
        break;
    }
  }, [filteredCommands, selectedIndex, onSelect, onClose]);

  // Click outside to close
  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!isOpen) return null;

  // Group commands by category
  const groupedCommands = React.useMemo(() => {
    const groups = new Map<string, Command[]>();
    for (const cmd of filteredCommands) {
      if (!groups.has(cmd.category)) {
        groups.set(cmd.category, []);
      }
      groups.get(cmd.category)!.push(cmd);
    }
    return groups;
  }, [filteredCommands]);

  let flatIndex = 0;

  return (
    <div className="command-palette-overlay" onClick={handleOverlayClick}>
      <div className="command-palette" onKeyDown={handleKeyDown}>
        <div className="command-palette-header">
          <svg
            className="search-icon"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="M21 21l-4.35-4.35" />
          </svg>
          <input
            ref={inputRef}
            type="text"
            className="command-palette-input"
            placeholder="Type a command or search..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoFocus
          />
          <kbd className="escape-hint">ESC</kbd>
        </div>

        <div className="command-palette-body" ref={listRef}>
          {filteredCommands.length === 0 ? (
            <div className="command-palette-empty">
              <svg
                width="48"
                height="48"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <circle cx="11" cy="11" r="8" />
                <path d="M21 21l-4.35-4.35" />
              </svg>
              <p>No commands found</p>
              <span>Try a different search term</span>
            </div>
          ) : (
            Array.from(groupedCommands.entries()).map(([category, cmds]) => (
              <div key={category} className="command-group">
                <div className="command-group-header">{category}</div>
                {cmds.map(cmd => {
                  const currentIndex = flatIndex++;
                  const isSelected = currentIndex === selectedIndex;
                  return (
                    <div
                      key={cmd.id}
                      className={`command-item ${isSelected ? 'selected' : ''}`}
                      onClick={() => {
                        onSelect(cmd.id);
                        onClose();
                      }}
                      onMouseEnter={() => setSelectedIndex(currentIndex)}
                    >
                      <span className="command-label">{cmd.label}</span>
                      {cmd.shortcut && (
                        <span className="command-shortcut">{cmd.shortcut}</span>
                      )}
                    </div>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="command-palette-footer">
          <span>
            <kbd>↑↓</kbd> to navigate
          </span>
          <span>
            <kbd>Enter</kbd> to select
          </span>
          <span>
            <kbd>Esc</kbd> to close
          </span>
        </div>
      </div>
    </div>
  );
};

export default CommandPalette;
