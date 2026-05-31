import React, { useState, useEffect } from 'react';
import clsx from 'clsx';

interface AppScore {
  name: string;
  icon: string;
  score: number;
  selected?: boolean;
}

interface ScoreTileProps {
  onAppSelect?: (appName: string) => void;
  selectedApp?: string;
}

const defaultApps: AppScore[] = [
  { name: 'Reader', icon: '📖', score: 45 },
  { name: 'Edge', icon: '🌐', score: 72 },
  { name: 'Audacity', icon: '🎵', score: 38 },
  { name: 'Cursor', icon: '⚡', score: 60, selected: true },
  { name: 'Chrome', icon: '🔍', score: 85 },
];

export function ScoreTile({ onAppSelect, selectedApp = 'Cursor' }: ScoreTileProps) {
  const [apps, setApps] = useState<AppScore[]>(defaultApps);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchScore() {
      try {
        const backendUrl = await window.electronAPI?.getBackendUrl();
        if (backendUrl) {
          const response = await fetch(`${backendUrl}/api/score`);
          if (response.ok) {
            const data = await response.json();
            setApps(prev => prev.map(app => 
              app.name === 'Cursor' 
                ? { ...app, score: data.score }
                : app
            ));
          }
        }
      } catch (error) {
        console.log('Backend not available, using default scores');
      } finally {
        setIsLoading(false);
      }
    }
    fetchScore();
  }, []);

  const handleSelect = (appName: string) => {
    setApps(prev => prev.map(app => ({
      ...app,
      selected: app.name === appName,
    })));
    onAppSelect?.(appName);
  };

  return (
    <div className="bg-app-sidebar border-b border-app-border">
      <div className="flex items-center gap-2 p-3 overflow-x-auto">
        {apps.map((app) => (
          <button
            key={app.name}
            onClick={() => handleSelect(app.name)}
            className={clsx(
              'flex items-center gap-2 px-3 py-2 rounded-lg transition-all min-w-fit',
              'border hover:bg-app-panel',
              app.name === selectedApp
                ? 'border-app-accent border-dotted bg-app-selection'
                : 'border-transparent hover:border-app-border'
            )}
          >
            <span className="text-lg">{app.icon}</span>
            <span className="text-sm text-app-text font-medium">{app.name}</span>
            <span
              className={clsx(
                'text-xs font-bold px-1.5 py-0.5 rounded',
                app.score >= 70
                  ? 'bg-app-accent-green/20 text-app-accent-green'
                  : app.score >= 50
                  ? 'bg-app-accent-yellow/20 text-app-accent-yellow'
                  : 'bg-app-accent-red/20 text-app-accent-red'
              )}
            >
              {isLoading && app.name === 'Cursor' ? '...' : app.score}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function ScoreBadge({ score, size = 'md' }: { score: number; size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'text-xs px-1 py-0.5',
    md: 'text-sm px-2 py-1',
    lg: 'text-lg px-3 py-1.5',
  };

  return (
    <span
      className={clsx(
        'font-bold rounded',
        sizeClasses[size],
        score >= 70
          ? 'bg-app-accent-green/20 text-app-accent-green'
          : score >= 50
          ? 'bg-app-accent-yellow/20 text-app-accent-yellow'
          : 'bg-app-accent-red/20 text-app-accent-red'
      )}
    >
      {score}
    </span>
  );
}
