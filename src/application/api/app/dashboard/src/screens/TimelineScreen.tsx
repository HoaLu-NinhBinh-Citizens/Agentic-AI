import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';
import { dashboardApi } from '@/api/dashboard';
import { Card, Badge } from '@/components/ui';

type LevelFilter = 'all' | 'debug' | 'info' | 'warn' | 'error';

export function TimelineScreen() {
  const [levelFilter, setLevelFilter] = useState<LevelFilter>('all');
  const [limit, setLimit] = useState(50);

  const { data: timeline, isLoading } = useQuery({
    queryKey: ['dashboard', 'timeline', limit, levelFilter],
    queryFn: () => dashboardApi.getEventTimeline(limit, levelFilter === 'all' ? undefined : levelFilter),
    refetchInterval: 5000,
  });

  const filterOptions: { value: LevelFilter; label: string; color: string }[] = [
    { value: 'all', label: 'All', color: 'bg-gray-600' },
    { value: 'debug', label: 'Debug', color: 'bg-gray-500' },
    { value: 'info', label: 'Info', color: 'bg-blue-500' },
    { value: 'warn', label: 'Warning', color: 'bg-yellow-500' },
    { value: 'error', label: 'Error', color: 'bg-red-500' },
  ];

  const getLevelBadge = (level: string) => {
    switch (level) {
      case 'error':
        return <Badge variant="error">Error</Badge>;
      case 'warn':
        return <Badge variant="warning">Warning</Badge>;
      case 'info':
        return <Badge variant="info">Info</Badge>;
      case 'debug':
        return <Badge>Debug</Badge>;
      default:
        return <Badge>{level}</Badge>;
    }
  };

  const getEventTypeIcon = (type: string) => {
    switch (type) {
      case 'task_start':
        return <span className="text-green-400">▶</span>;
      case 'task_complete':
        return <span className="text-blue-400">✓</span>;
      case 'error':
        return <span className="text-red-400">✕</span>;
      case 'rollback':
        return <span className="text-orange-400">↩</span>;
      case 'warning':
        return <span className="text-yellow-400">⚠</span>;
      default:
        return <span className="text-gray-400">•</span>;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Event Timeline</h1>
          <p className="text-sm text-gray-400 mt-1">
            Real-time activity stream
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-white">{timeline?.total || 0}</p>
          <p className="text-sm text-gray-400">Total Events</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-gray-400">{timeline?.by_level?.debug || 0}</p>
          <p className="text-sm text-gray-400">Debug</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-blue-400">{timeline?.by_level?.info || 0}</p>
          <p className="text-sm text-gray-400">Info</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-yellow-400">{timeline?.by_level?.warn || 0}</p>
          <p className="text-sm text-gray-400">Warnings</p>
        </div>
        <div className="bg-gray-800 rounded-lg p-4 text-center">
          <p className="text-2xl font-bold text-red-400">{timeline?.by_level?.error || 0}</p>
          <p className="text-sm text-gray-400">Errors</p>
        </div>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-400">Filter:</span>
            <div className="flex gap-2">
              {filterOptions.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => setLevelFilter(opt.value)}
                  className={`
                    px-3 py-1 text-sm rounded-full transition-colors
                    ${levelFilter === opt.value 
                      ? `${opt.color} text-white` 
                      : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
                    }
                  `}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm text-gray-400">Show:</span>
            <select
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              className="bg-gray-700 text-white rounded px-3 py-1 text-sm"
            >
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
              <option value={200}>200</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Timeline */}
      <Card className="col-span-full">
        <div className="space-y-1">
          {timeline?.events && timeline.events.length > 0 ? (
            timeline.events.map((event) => (
              <div
                key={event.id}
                className={`
                  flex items-start gap-4 p-3 rounded-lg hover:bg-gray-700/50 transition-colors
                  ${event.level === 'error' ? 'bg-red-900/20' : ''}
                  ${event.level === 'warn' ? 'bg-yellow-900/20' : ''}
                `}
              >
                <div className="flex-shrink-0 w-6 h-6 flex items-center justify-center mt-0.5">
                  {getEventTypeIcon(event.type)}
                </div>
                <div className="flex-shrink-0 w-20 text-xs text-gray-500 font-mono">
                  {format(new Date(event.timestamp), 'HH:mm:ss')}
                </div>
                <div className="flex-shrink-0 w-16">
                  {getLevelBadge(event.level)}
                </div>
                <div className="flex-shrink-0 w-24 text-xs text-gray-400">
                  {event.source}
                </div>
                <div className="flex-1 text-sm text-gray-300">
                  {event.message}
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-12 text-gray-500">
              No events to display
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
