import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/dashboard';
import { Card, Table, Badge, StatusIndicator } from '@/components/ui';

export function WorkflowsScreen() {
  const { data: workflowStatus, isLoading } = useQuery({
    queryKey: ['dashboard', 'workflows'],
    queryFn: dashboardApi.getWorkflowStatus,
    refetchInterval: 3000,
  });

  const { data: workflowHistory } = useQuery({
    queryKey: ['dashboard', 'workflowHistory'],
    queryFn: () => dashboardApi.getWorkflowHistory(50),
    refetchInterval: 10000,
  });

  const { data: rollbackEvents } = useQuery({
    queryKey: ['dashboard', 'rollbacks'],
    queryFn: () => dashboardApi.getRollbackEvents(20),
    refetchInterval: 15000,
  });

  const workflowColumns = [
    { key: 'state', label: 'State', width: '100px' },
    { key: 'source', label: 'Source', width: '150px' },
    { key: 'timestamp', label: 'Timestamp', width: '200px' },
  ];

  const historyColumns = [
    { key: 'id', label: 'ID', width: '100px' },
    { key: 'timestamp', label: 'Time', width: '180px' },
    { key: 'level', label: 'Level', width: '80px' },
    { key: 'source', label: 'Source', width: '120px' },
    { key: 'message', label: 'Message' },
  ];

  const rollbackColumns = [
    { key: 'timestamp', label: 'Time', width: '180px' },
    { key: 'level', label: 'Level', width: '80px' },
    { key: 'source', label: 'Source', width: '120px' },
    { key: 'reason', label: 'Reason', width: '150px' },
    { key: 'message', label: 'Details' },
  ];

  const getStateBadge = (state: string) => {
    switch (state) {
      case 'completed':
        return <Badge variant="success">Completed</Badge>;
      case 'running':
        return <Badge variant="info"><StatusIndicator status="running" size="sm" /> Running</Badge>;
      case 'failed':
        return <Badge variant="error">Failed</Badge>;
      case 'queued':
        return <Badge variant="default">Queued</Badge>;
      default:
        return <Badge>{state}</Badge>;
    }
  };

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

  const workflowData = (workflowStatus?.workflows || []).map((wf, i) => ({
    ...wf,
    id: `wf-${i.toString().padStart(4, '0')}`,
    state: getStateBadge(wf.state),
  }));

  const historyData = (workflowHistory?.workflows || []).map(wf => ({
    ...wf,
    level: getLevelBadge(wf.level),
  }));

  const rollbackData = (rollbackEvents?.events || []).map(evt => ({
    ...evt,
    reason: <Badge variant="error">{evt.reason}</Badge>,
    level: getLevelBadge(evt.level),
  }));

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
          <h1 className="text-2xl font-bold text-white">Workflows</h1>
          <p className="text-sm text-gray-400 mt-1">
            Monitor active workflows and execution history
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="text-sm text-gray-400">Active Workflows</p>
            <p className="text-xl font-semibold text-white">
              {workflowData.filter(w => w.state?.props?.children === 'Running').length || 0}
            </p>
          </div>
        </div>
      </div>

      {/* Active Workflows */}
      <Card title="Active Workflows" className="col-span-full">
        <Table 
          columns={workflowColumns} 
          data={workflowData}
          emptyMessage="No active workflows"
        />
      </Card>

      {/* Execution History */}
      <Card title="Execution History" className="col-span-full">
        <Table 
          columns={historyColumns} 
          data={historyData.map(h => ({
            id: h.id,
            timestamp: new Date(h.timestamp).toLocaleString(),
            level: h.level,
            source: h.source,
            message: h.message.substring(0, 100) + (h.message.length > 100 ? '...' : ''),
          }))}
          emptyMessage="No workflow history"
        />
      </Card>

      {/* Rollback Events */}
      <Card title="Rollback Events & Failures" className="col-span-full">
        {rollbackData.length > 0 ? (
          <Table 
            columns={rollbackColumns} 
            data={rollbackData.map(r => ({
              timestamp: new Date(r.timestamp).toLocaleString(),
              level: r.level,
              source: r.source,
              reason: r.reason,
              message: r.message.substring(0, 80) + (r.message.length > 80 ? '...' : ''),
            }))}
          />
        ) : (
          <div className="text-center py-8 text-gray-500">
            No rollback events recorded
          </div>
        )}
      </Card>
    </div>
  );
}
