import { useState } from 'react';
import { Card, Badge } from '@/components/ui';
import { DAGVisualization } from '@/components/DAGVisualization';
import { AgentChatPanel } from '@/components/AgentChatPanel';
import { RollbackExplainer } from '@/components/RollbackExplainer';
import { WhyConfidenceDisplay } from '@/components/WhyConfidenceDisplay';
import { useDashboardWebSocket } from '@/hooks/useDashboardWebSocket';

type TabType = 'dag' | 'chat' | 'rollback' | 'why';

export function TrustScreen() {
  const [activeTab, setActiveTab] = useState<TabType>('dag');
  const [showLiveDemo, setShowLiveDemo] = useState(true);

  // WebSocket for real-time updates
  const { isConnected, lastEvent } = useDashboardWebSocket({
    enabled: showLiveDemo,
    onEvent: (event) => {
      console.log('TrustScreen received event:', event.type);
    },
  });

  const tabs: { id: TabType; label: string; icon: string; description: string }[] = [
    { 
      id: 'dag', 
      label: 'Call Graph', 
      icon: '🔗',
      description: 'Visualize function call dependencies',
    },
    { 
      id: 'chat', 
      label: 'Agent Chat', 
      icon: '💬',
      description: 'Interactive agent conversation',
    },
    { 
      id: 'rollback', 
      label: 'Rollback History', 
      icon: '↩',
      description: 'Track workflow rollbacks',
    },
    { 
      id: 'why', 
      label: 'Confidence Analysis', 
      icon: '❓',
      description: 'Understand AI reasoning',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Trust & UX</h1>
          <p className="text-sm text-gray-400 mt-1">
            Visualize workflows, understand agent reasoning, and track changes
          </p>
        </div>
        <div className="flex items-center gap-4">
          {/* WebSocket Status */}
          {showLiveDemo && (
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-500'}`} />
              <span className="text-xs text-gray-400">
                {isConnected ? 'Live' : 'Disconnected'}
              </span>
            </div>
          )}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={showLiveDemo}
              onChange={(e) => setShowLiveDemo(e.target.checked)}
              className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-600 focus:ring-blue-500"
            />
            <span className="text-sm text-gray-400">Show demo data</span>
          </label>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-gray-700">
        <nav className="flex gap-1">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`
                flex items-center gap-2 px-4 py-3 text-sm font-medium
                border-b-2 transition-colors
                ${activeTab === tab.id
                  ? 'text-blue-400 border-blue-400'
                  : 'text-gray-400 border-transparent hover:text-white hover:border-gray-600'
                }
              `}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      <div className="min-h-[600px]">
        {activeTab === 'dag' && (
          <div className="space-y-6">
            <Card>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h2 className="text-lg font-medium text-white">Call Graph Visualization</h2>
                  <p className="text-sm text-gray-400 mt-1">
                    Explore function call dependencies in the firmware codebase
                  </p>
                </div>
                <Badge variant="info">Static Analysis</Badge>
              </div>
              <DAGVisualization />
            </Card>
          </div>
        )}

        {activeTab === 'chat' && (
          <div className="h-[700px]">
            <Card className="h-full">
              <AgentChatPanel />
            </Card>
          </div>
        )}

        {activeTab === 'rollback' && (
          <div>
            <Card>
              <div className="mb-4">
                <h2 className="text-lg font-medium text-white">Rollback History</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Review automatic and manual workflow rollbacks with detailed reasoning
                </p>
              </div>
              <RollbackExplainer />
            </Card>
          </div>
        )}

        {activeTab === 'why' && (
          <div>
            <Card>
              <div className="mb-4">
                <h2 className="text-lg font-medium text-white">Confidence Analysis</h2>
                <p className="text-sm text-gray-400 mt-1">
                  Understand why the AI agent made specific recommendations
                </p>
              </div>
              <WhyConfidenceDisplay />
            </Card>
          </div>
        )}
      </div>

      {/* Info Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <div className="flex items-start gap-3">
            <span className="text-2xl">🔍</span>
            <div>
              <h3 className="text-sm font-medium text-white">Transparent Reasoning</h3>
              <p className="text-xs text-gray-400 mt-1">
                Every AI recommendation comes with confidence scores and evidence trails
              </p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-start gap-3">
            <span className="text-2xl">↩</span>
            <div>
              <h3 className="text-sm font-medium text-white">Automatic Rollback</h3>
              <p className="text-xs text-gray-400 mt-1">
                Failed workflows automatically restore to previous known-good state
              </p>
            </div>
          </div>
        </Card>
        <Card>
          <div className="flex items-start gap-3">
            <span className="text-2xl">🔗</span>
            <div>
              <h3 className="text-sm font-medium text-white">Dependency Tracking</h3>
              <p className="text-xs text-gray-400 mt-1">
                Full call graph analysis helps prevent breaking changes
              </p>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
