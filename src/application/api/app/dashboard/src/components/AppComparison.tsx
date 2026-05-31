import { clsx } from 'clsx';

export interface AppData {
  id: string;
  name: string;
  percentage: number;
  icon: string;
}

export interface AppComparisonProps {
  apps: AppData[];
  selectedAppId?: string | null;
  onSelectApp?: (appId: string) => void;
  className?: string;
}

const DEFAULT_APPS: AppData[] = [
  { id: 'reader', name: 'Reader', percentage: 89, icon: '📖' },
  { id: 'edge', name: 'Edge', percentage: 85, icon: '🌐' },
  { id: 'audacity', name: 'Audacity', percentage: 76, icon: '🎵' },
  { id: 'cursor', name: 'Cursor', percentage: 60, icon: '💡' },
  { id: 'chrome', name: 'Chrome', percentage: 58, icon: '🔵' },
];

function getPercentageColor(percentage: number): string {
  if (percentage >= 80) return 'text-green-400';
  if (percentage >= 60) return 'text-blue-400';
  if (percentage >= 40) return 'text-yellow-400';
  return 'text-gray-400';
}

function getBadgeColor(percentage: number): string {
  if (percentage >= 80) return 'bg-green-500/20 text-green-400 border-green-500/30';
  if (percentage >= 60) return 'bg-blue-500/20 text-blue-400 border-blue-500/30';
  if (percentage >= 40) return 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30';
  return 'bg-gray-500/20 text-gray-400 border-gray-500/30';
}

export function AppComparison({
  apps = DEFAULT_APPS,
  selectedAppId,
  onSelectApp,
  className,
}: AppComparisonProps) {
  return (
    <div className={clsx('w-full', className)}>
      {/* Left Sidebar Navigation */}
      <div className="mb-6">
        <nav className="flex flex-wrap gap-2">
          <button
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              selectedAppId === null
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700 hover:text-white'
            )}
            onClick={() => onSelectApp?.('')}
          >
            Tất cả
          </button>
          <button
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              selectedAppId === 'news'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700 hover:text-white'
            )}
            onClick={() => onSelectApp?.('news')}
          >
            Tin tức
          </button>
          <button
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              selectedAppId === 'sports'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700 hover:text-white'
            )}
            onClick={() => onSelectApp?.('sports')}
          >
            Thể thao
          </button>
          <button
            className={clsx(
              'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              selectedAppId === 'entertainment'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-700/50 text-gray-400 hover:bg-gray-700 hover:text-white'
            )}
            onClick={() => onSelectApp?.('entertainment')}
          >
            Giải trí
          </button>
        </nav>
      </div>

      {/* Horizontal Cards */}
      <div className="flex flex-wrap gap-4">
        {apps.map((app) => {
          const isSelected = selectedAppId === app.id;
          const percentageColor = getPercentageColor(app.percentage);
          const badgeColor = getBadgeColor(app.percentage);

          return (
            <button
              key={app.id}
              onClick={() => onSelectApp?.(isSelected ? '' : app.id)}
              className={clsx(
                'flex flex-col items-center justify-center',
                'min-w-[140px] w-[140px] h-[120px]',
                'rounded-xl border transition-all duration-200',
                'hover:scale-105 active:scale-95',
                isSelected
                  ? 'bg-blue-600/20 border-blue-500 ring-2 ring-blue-500/50'
                  : 'bg-gray-800/50 border-gray-700 hover:bg-gray-800 hover:border-gray-600'
              )}
            >
              {/* App Icon */}
              <div className={clsx(
                'text-3xl mb-2',
                isSelected && 'animate-bounce'
              )}>
                {app.icon}
              </div>

              {/* App Name */}
              <span className={clsx(
                'text-sm font-medium mb-2',
                isSelected ? 'text-white' : 'text-gray-300'
              )}>
                {app.name}
              </span>

              {/* Percentage Badge */}
              <span className={clsx(
                'px-3 py-1 rounded-full text-xs font-semibold border',
                badgeColor
              )}>
                {app.percentage}%
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
