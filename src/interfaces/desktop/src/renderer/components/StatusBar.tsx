import React from 'react';
import clsx from 'clsx';
import { Wifi, WifiOff, GitBranch, FileText, Circle } from 'lucide-react';

interface StatusBarProps {
  filePath?: string;
  language?: string;
  line?: number;
  column?: number;
  backendConnected?: boolean;
  branch?: string;
}

export function StatusBar({
  filePath,
  language = 'Plain Text',
  line = 1,
  column = 1,
  backendConnected = true,
  branch = '',
}: StatusBarProps) {
  return (
    <div className="h-6 flex items-center justify-between px-3 bg-app-accent text-white text-xs">
      {/* Left section */}
      <div className="flex items-center gap-3">
        {backendConnected ? (
          <div className="flex items-center gap-1" title="Backend Connected">
            <Wifi className="w-3 h-3" />
            <span>Connected</span>
          </div>
        ) : (
          <div className="flex items-center gap-1" title="Backend Disconnected">
            <WifiOff className="w-3 h-3" />
            <span>Offline</span>
          </div>
        )}
        {filePath && (
          <div className="flex items-center gap-1 text-white/80">
            <FileText className="w-3 h-3" />
            <span className="truncate max-w-xs">{filePath}</span>
          </div>
        )}
      </div>

      {/* Center section */}
      <div className="flex items-center gap-1 text-white/80">
        <Circle className={clsx('w-2 h-2', backendConnected ? 'fill-green-400' : 'fill-red-400')} />
        <span>AI_SUPPORT Desktop v1.0</span>
      </div>

      {/* Right section */}
      <div className="flex items-center gap-3">
        {branch && (
          <div className="flex items-center gap-1 text-white/80">
            <GitBranch className="w-3 h-3" />
            <span>{branch}</span>
          </div>
        )}
        <div className="text-white/80">
          Ln {line}, Col {column}
        </div>
        <div className="text-white/80">{language}</div>
        <div className="text-white/80">UTF-8</div>
        <div className="text-white/80">Spaces: 4</div>
      </div>
    </div>
  );
}
