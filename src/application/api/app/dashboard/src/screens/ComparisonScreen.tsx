import { useState } from 'react';
import { Card } from '@/components/ui';
import { AppComparison, type AppData } from '@/components/AppComparison';

const MOCK_APPS: AppData[] = [
  { id: 'reader', name: 'Reader', percentage: 89, icon: '📖' },
  { id: 'edge', name: 'Edge', percentage: 85, icon: '🌐' },
  { id: 'audacity', name: 'Audacity', percentage: 76, icon: '🎵' },
  { id: 'cursor', name: 'Cursor', percentage: 60, icon: '💡' },
  { id: 'chrome', name: 'Chrome', percentage: 58, icon: '🔵' },
];

export function ComparisonScreen() {
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);

  const selectedApp = MOCK_APPS.find(app => app.id === selectedAppId);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-white">App Comparison</h1>
        <p className="text-sm text-gray-400 mt-1">
          Compare application performance and usage metrics
        </p>
      </div>

      {/* App Comparison Cards */}
      <Card title="Select an Application">
        <AppComparison
          apps={MOCK_APPS}
          selectedAppId={selectedAppId}
          onSelectApp={(appId) => setSelectedAppId(appId || null)}
        />
      </Card>

      {/* Selected App Details */}
      {selectedApp && (
        <Card title={`${selectedApp.name} Details`}>
          <div className="flex items-center gap-4">
            <div className="text-5xl">{selectedApp.icon}</div>
            <div>
              <h3 className="text-xl font-semibold text-white">{selectedApp.name}</h3>
              <p className="text-gray-400 mt-1">
                Performance Score:{' '}
                <span className={`
                  font-bold
                  ${selectedApp.percentage >= 80 ? 'text-green-400' :
                    selectedApp.percentage >= 60 ? 'text-blue-400' :
                    selectedApp.percentage >= 40 ? 'text-yellow-400' : 'text-gray-400'}
                `}>
                  {selectedApp.percentage}%
                </span>
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <p className="text-sm text-gray-400 mb-1">Best Performer</p>
          <div className="flex items-center gap-2">
            <span className="text-2xl">📖</span>
            <div>
              <p className="font-semibold text-white">Reader</p>
              <p className="text-sm text-green-400">89%</p>
            </div>
          </div>
        </Card>
        <Card>
          <p className="text-sm text-gray-400 mb-1">Average Score</p>
          <div className="flex items-center gap-2">
            <span className="text-2xl">📊</span>
            <div>
              <p className="font-semibold text-white">
                {Math.round(MOCK_APPS.reduce((sum, app) => sum + app.percentage, 0) / MOCK_APPS.length)}%
              </p>
              <p className="text-sm text-gray-400">across all apps</p>
            </div>
          </div>
        </Card>
        <Card>
          <p className="text-sm text-gray-400 mb-1">Total Apps</p>
          <div className="flex items-center gap-2">
            <span className="text-2xl">📱</span>
            <div>
              <p className="font-semibold text-white">{MOCK_APPS.length}</p>
              <p className="text-sm text-gray-400">applications</p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
