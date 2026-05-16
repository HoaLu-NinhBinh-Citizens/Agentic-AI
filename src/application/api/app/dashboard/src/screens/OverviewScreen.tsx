import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { dashboardApi } from '@/api/dashboard';
import { Card, MetricCard, ProgressBar, StatusIndicator, Badge } from '@/components/ui';
import { useDashboardWebSocket } from '@/hooks/useDashboardWebSocket';

const COLORS = ['#22c55e', '#ef4444', '#3b82f6', '#f59e0b'];

// Interface for metrics history
interface MetricsHistoryPoint {
  time: string;
  cpu: number;
  memory: number;
  speed: number;
  temperature: number;
}

export function OverviewScreen() {
  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['dashboard', 'overview'],
    queryFn: dashboardApi.getOverview,
    refetchInterval: 5000,
  });

  const { data: health } = useQuery({
    queryKey: ['dashboard', 'health'],
    queryFn: dashboardApi.getHealth,
    refetchInterval: 10000,
  });

  const { data: tokenUsage } = useQuery({
    queryKey: ['dashboard', 'tokenUsage'],
    queryFn: dashboardApi.getTokenUsage,
    refetchInterval: 30000,
  });

  // WebSocket real-time data integration
  const [metricsHistory, setMetricsHistory] = useState<MetricsHistoryPoint[]>([]);
  const [isLive, setIsLive] = useState(false);

  const { isConnected, lastEvent } = useDashboardWebSocket({
    enabled: true,
    onEvent: (event) => {
      // Update metrics history when we receive resource updates
      if (event.type === 'resource_update' && event.data) {
        const newPoint: MetricsHistoryPoint = {
          time: new Date().toLocaleTimeString(),
          cpu: event.data.cpu ?? 0,
          memory: event.data.memory ?? 0,
          speed: event.data.speed ?? 0,
          temperature: event.data.temperature ?? 0,
        };
        setMetricsHistory(prev => {
          const updated = [...prev, newPoint];
          // Keep only last 20 points
          return updated.slice(-20);
        });
        setIsLive(true);
      }
    },
  });

  // Seed initial data from overview
  useEffect(() => {
    if (overview?.resources && metricsHistory.length === 0) {
      setMetricsHistory([{
        time: 'Now',
        cpu: overview.resources.cpu ?? 0,
        memory: overview.resources.memory ?? 0,
        speed: overview.resources.speed ?? 0,
        temperature: overview.resources.temperature ?? 0,
      }]);
    }
  }, [overview, metricsHistory.length]);

  if (overviewLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  const workflowData = overview ? [
    { name: 'Completed', value: overview.workflow.completed, color: '#22c55e' },
    { name: 'Failed', value: overview.workflow.failed, color: '#ef4444' },
    { name: 'Active', value: overview.workflow.active, color: '#3b82f6' },
    { name: 'Queued', value: overview.workflow.queued, color: '#f59e0b' },
  ] : [];

  const metricsData = overview?.resources ? [
    { time: 'Now', cpu: overview.resources.cpu, memory: overview.resources.memory },
  ] : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">System Overview</h1>
          <p className="text-sm text-gray-400 mt-1">
            Last updated: {overview?.timestamp ? new Date(overview.timestamp).toLocaleString() : 'N/A'}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StatusIndicator 
            status={overview?.system.agent_initialized ? 'connected' : 'disconnected'} 
            label="Agent"
            pulse
          />
          <StatusIndicator 
            status={health?.overall === 'healthy' ? 'connected' : 'warning'} 
            label="Health"
            pulse
          />
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Uptime"
          value={overview?.system.uptime_human || '0s'}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <MetricCard
          label="Total Tasks"
          value={overview?.system.task_count || 0}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
          }
        />
        <MetricCard
          label="Success Rate"
          value={`${overview?.system.success_rate?.toFixed(1) || 0}%`}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
        />
        <MetricCard
          label="Token Usage"
          value={(tokenUsage?.current_session.total_tokens || 0).toLocaleString()}
          icon={
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
            </svg>
          }
        />
      </div>

      {/* Live Metrics Chart */}
      {metricsHistory.length > 1 && (
        <Card title="Live Metrics">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-500'}`} />
              <span className="text-sm text-gray-400">
                {isConnected ? 'Connected' : 'Disconnected'}
              </span>
              {isLive && (
                <span className="text-xs text-green-400">(Live updates)</span>
              )}
            </div>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={metricsHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
              <XAxis dataKey="time" stroke="#9ca3af" fontSize={12} />
              <YAxis stroke="#9ca3af" fontSize={12} />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '0.5rem'
                }}
              />
              <Area 
                type="monotone" 
                dataKey="cpu" 
                stroke="#3b82f6" 
                fill="#3b82f6" 
                fillOpacity={0.2}
                name="CPU %"
              />
              <Area 
                type="monotone" 
                dataKey="memory" 
                stroke="#22c55e" 
                fill="#22c55e" 
                fillOpacity={0.2}
                name="Memory %"
              />
            </AreaChart>
          </ResponsiveContainer>
        </Card>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Resource Usage */}
        <Card title="Resource Usage">
          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">CPU</span>
                <span className="text-white">{overview?.resources.cpu?.toFixed(1) || 0}%</span>
              </div>
              <ProgressBar 
                value={overview?.resources.cpu || 0} 
                max={100} 
                color={overview?.resources.cpu && overview.resources.cpu > 80 ? 'red' : 'blue'}
              />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">Memory</span>
                <span className="text-white">{overview?.resources.memory?.toFixed(1) || 0}%</span>
              </div>
              <ProgressBar 
                value={overview?.resources.memory || 0} 
                max={100} 
                color={overview?.resources.memory && overview.resources.memory > 80 ? 'red' : 'green'}
              />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">Speed (RPM)</span>
                <span className="text-white">{overview?.resources.speed?.toFixed(0) || 0}</span>
              </div>
              <ProgressBar value={Math.min(100, (overview?.resources.speed || 0) / 10)} max={100} color="yellow" />
            </div>
            <div>
              <div className="flex justify-between text-sm mb-2">
                <span className="text-gray-400">Temperature</span>
                <span className="text-white">{overview?.resources.temperature?.toFixed(1) || 0}°C</span>
              </div>
              <ProgressBar 
                value={overview?.resources.temperature || 0} 
                max={100} 
                color={overview?.resources.temperature && overview.resources.temperature > 70 ? 'red' : 'blue'}
              />
            </div>
          </div>
        </Card>

        {/* Workflow Distribution */}
        <Card title="Workflow Distribution">
          <div className="flex items-center justify-center h-64">
            {workflowData.some(d => d.value > 0) ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={workflowData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={80}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {workflowData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="text-gray-500">No workflow data</div>
            )}
          </div>
          <div className="flex justify-center gap-4 mt-4">
            {workflowData.map((item, index) => (
              <div key={item.name} className="flex items-center gap-2">
                <div className="w-3 h-3 rounded-full" style={{ backgroundColor: item.color }} />
                <span className="text-sm text-gray-400">{item.name}: {item.value}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Health Checks */}
      <Card title="System Health">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {health?.checks && Object.entries(health.checks).map(([key, check]) => (
            <div key={key} className="text-center p-4 bg-gray-700/50 rounded-lg">
              <StatusIndicator 
                status={(check as { status: string }).status === 'up' ? 'connected' : 'error'} 
                size="lg"
                className="justify-center mb-2"
              />
              <p className="text-sm font-medium text-white capitalize">{key}</p>
              <p className="text-xs text-gray-400">{(check as { status: string }).status}</p>
            </div>
          ))}
        </div>
        
        {health?.alerts && health.alerts.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-medium text-gray-300 mb-2">Active Alerts</h4>
            <div className="space-y-2">
              {health.alerts.map((alert, i) => (
                <div 
                  key={i}
                  className={`
                    flex items-center gap-2 p-3 rounded-lg
                    ${alert.level === 'critical' ? 'bg-red-900/50 text-red-300' : 'bg-yellow-900/50 text-yellow-300'}
                  `}
                >
                  <Badge variant={alert.level === 'critical' ? 'error' : 'warning'}>
                    {alert.level.toUpperCase()}
                  </Badge>
                  <span>{alert.message}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Token Budget */}
      <Card title="Token Budget">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <p className="text-sm text-gray-400 mb-1">Input Tokens</p>
            <p className="text-2xl font-semibold text-white">
              {(tokenUsage?.current_session.input_tokens || 0).toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-400 mb-1">Output Tokens</p>
            <p className="text-2xl font-semibold text-white">
              {(tokenUsage?.current_session.output_tokens || 0).toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-sm text-gray-400 mb-1">Estimated Cost</p>
            <p className="text-2xl font-semibold text-green-400">
              ${tokenUsage?.costs?.estimated?.toFixed(4) || '0.0000'}
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}
