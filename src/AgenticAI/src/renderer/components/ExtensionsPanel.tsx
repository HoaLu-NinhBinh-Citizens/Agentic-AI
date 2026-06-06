import React, { useState, useEffect, useCallback } from 'react';
import { FiSearch, FiDownload, FiTrash2, FiRefreshCw, FiStar, FiPackage } from 'react-icons/fi';

interface Extension {
  id: string;
  name: string;
  publisher: string;
  description: string;
  version: string;
  downloads: number;
  rating: number;
  icon: string;
  installed: boolean;
}

export const ExtensionsPanel: React.FC = () => {
  const [query, setQuery] = useState('');
  const [extensions, setExtensions] = useState<Extension[]>([]);
  const [installed, setInstalled] = useState<Extension[]>([]);
  const [loading, setLoading] = useState(false);
  const [installing, setInstalling] = useState<string | null>(null);
  const [installProgress, setInstallProgress] = useState(0);

  // Load installed extensions on mount
  useEffect(() => {
    loadInstalled();
    loadPopular();

    // Listen for install progress
    window.electronAPI?.marketplace?.onInstallProgress?.((data: any) => {
      setInstallProgress(data.progress);
    });
  }, []);

  const loadInstalled = async () => {
    try {
      const result = await window.electronAPI?.marketplace?.installed();
      if (result) setInstalled(result);
    } catch (e) {
      console.error('Failed to load installed extensions:', e);
    }
  };

  const loadPopular = async () => {
    setLoading(true);
    try {
      const result = await window.electronAPI?.marketplace?.popular();
      if (result) setExtensions(result);
    } catch (e) {
      console.error('Failed to load popular extensions:', e);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = useCallback(async () => {
    if (!query.trim()) {
      loadPopular();
      return;
    }
    setLoading(true);
    try {
      const result = await window.electronAPI?.marketplace?.search(query, 20);
      if (result) setExtensions(result);
    } catch (e) {
      console.error('Search failed:', e);
    } finally {
      setLoading(false);
    }
  }, [query]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleInstall = async (ext: Extension) => {
    setInstalling(ext.id);
    setInstallProgress(0);
    try {
      const result = await window.electronAPI?.marketplace?.install(ext.publisher, ext.id.split('.').pop());
      if (result?.success) {
        await loadInstalled();
        setExtensions(prev => prev.map(e => e.id === ext.id ? { ...e, installed: true } : e));
      }
    } catch (e) {
      console.error('Install failed:', e);
    } finally {
      setInstalling(null);
    }
  };

  const handleUninstall = async (extId: string) => {
    try {
      await window.electronAPI?.marketplace?.uninstall(extId);
      await loadInstalled();
      setExtensions(prev => prev.map(e => e.id === extId ? { ...e, installed: false } : e));
    } catch (e) {
      console.error('Uninstall failed:', e);
    }
  };

  const formatDownloads = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toString();
  };

  return (
    <div className="extensions-panel">
      <div className="extensions-header">
        <h3>EXTENSIONS</h3>
        <button className="ext-refresh-btn" onClick={loadPopular} title="Refresh">
          <FiRefreshCw size={14} />
        </button>
      </div>

      <div className="extensions-search">
        <FiSearch size={14} className="search-icon" />
        <input
          type="text"
          placeholder="Search Extensions in Marketplace"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
        />
      </div>

      {/* Installed Section */}
      {installed.length > 0 && (
        <div className="extensions-section">
          <div className="section-header">
            <span>INSTALLED</span>
            <span className="section-count">{installed.length}</span>
          </div>
          {installed.map(ext => (
            <ExtensionItem
              key={ext.id}
              ext={{ ...ext, installed: true } as Extension}
              onInstall={() => {}}
              onUninstall={() => handleUninstall(ext.id)}
              installing={false}
              progress={0}
            />
          ))}
        </div>
      )}

      {/* Marketplace Section */}
      <div className="extensions-section">
        <div className="section-header">
          <span>{query ? 'RESULTS' : 'POPULAR'}</span>
        </div>
        {loading ? (
          <div className="extensions-loading">
            <FiRefreshCw className="spin" size={16} />
            <span>Loading...</span>
          </div>
        ) : (
          extensions.map(ext => (
            <ExtensionItem
              key={ext.id}
              ext={ext}
              onInstall={() => handleInstall(ext)}
              onUninstall={() => handleUninstall(ext.id)}
              installing={installing === ext.id}
              progress={installing === ext.id ? installProgress : 0}
            />
          ))
        )}
      </div>
    </div>
  );
};

interface ExtensionItemProps {
  ext: Extension;
  onInstall: () => void;
  onUninstall: () => void;
  installing: boolean;
  progress: number;
}

const ExtensionItem: React.FC<ExtensionItemProps> = ({
  ext, onInstall, onUninstall, installing, progress
}) => {
  const formatDownloads = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n || 0);
  };

  return (
    <div className="extension-item">
      <div className="ext-icon">
        {ext.icon ? (
          <img src={ext.icon} alt="" width={32} height={32} />
        ) : (
          <FiPackage size={24} />
        )}
      </div>
      <div className="ext-info">
        <div className="ext-name">{ext.name}</div>
        <div className="ext-description">{ext.description}</div>
        <div className="ext-meta">
          <span className="ext-publisher">{ext.publisher}</span>
          {ext.downloads > 0 && (
            <span className="ext-downloads">
              <FiDownload size={10} /> {formatDownloads(ext.downloads)}
            </span>
          )}
          {ext.rating > 0 && (
            <span className="ext-rating">
              <FiStar size={10} /> {ext.rating.toFixed(1)}
            </span>
          )}
        </div>
      </div>
      <div className="ext-action">
        {installing ? (
          <div className="ext-progress">
            <div className="ext-progress-bar" style={{ width: `${progress}%` }} />
          </div>
        ) : ext.installed ? (
          <button className="ext-uninstall-btn" onClick={onUninstall}>
            <FiTrash2 size={12} />
          </button>
        ) : (
          <button className="ext-install-btn" onClick={onInstall}>
            Install
          </button>
        )}
      </div>
    </div>
  );
};
