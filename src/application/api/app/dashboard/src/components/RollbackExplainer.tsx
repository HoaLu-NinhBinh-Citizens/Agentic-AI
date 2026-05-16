import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Badge } from '@/components/ui';
import { dashboardApi } from '@/api/dashboard';

interface RollbackStep {
  id: string;
  action: string;
  before: string;
  after: string;
  reason: string;
  timestamp: string;
  status: 'completed' | 'failed' | 'skipped';
}

interface RollbackEvent {
  id: string;
  timestamp: string;
  workflowId: string;
  workflowName: string;
  reason: string;
  trigger: 'automatic' | 'manual' | 'error';
  steps: RollbackStep[];
  impact: {
    filesAffected: number;
    linesChanged: number;
    tasksReverted: number;
  };
  preventions?: string[];
}

interface RollbackExplainerProps {
  events?: RollbackEvent[];
  onSelectEvent?: (event: RollbackEvent) => void;
}

// Sample rollback events for demo mode
const sampleEvents: RollbackEvent[] = [
  {
    id: 'rb-001',
    timestamp: new Date(Date.now() - 3600000).toISOString(),
    workflowId: 'wf-042',
    workflowName: 'GPIO Configuration Update',
    reason: 'Compilation failed: undefined reference to HAL_GPIO_LockPin',
    trigger: 'automatic',
    steps: [
      {
        id: 'step-1',
        action: 'Restore original gpio.c from git HEAD',
        before: 'Modified gpio.c with HAL_GPIO_LockPin calls',
        after: 'Restored gpio.c from commit a3f2b1c',
        reason: 'HAL_GPIO_LockPin is not available on STM32F4xx',
        timestamp: new Date(Date.now() - 3600000).toISOString(),
        status: 'completed',
      },
      {
        id: 'step-2',
        action: 'Restore usart.c backup',
        before: 'Modified usart.c with new baudrate',
        after: 'Restored usart.c from commit a3f2b1c',
        reason: 'Part of the same change set',
        timestamp: new Date(Date.now() - 3590000).toISOString(),
        status: 'completed',
      },
      {
        id: 'step-3',
        action: 'Clear build cache',
        before: 'build/output/*.o files',
        after: 'Clean build directory',
        reason: 'Ensure no stale object files',
        timestamp: new Date(Date.now() - 3580000).toISOString(),
        status: 'completed',
      },
      {
        id: 'step-4',
        action: 'Notify engineering team',
        before: 'No notification sent',
        after: 'Slack notification #firmware-alerts',
        reason: 'Required for all rollbacks',
        timestamp: new Date(Date.now() - 3570000).toISOString(),
        status: 'completed',
      },
    ],
    impact: {
      filesAffected: 2,
      linesChanged: -47,
      tasksReverted: 1,
    },
    preventions: [
      'Verify HAL function availability in reference manual before use',
      'Add compile-time checks for MCU-specific features',
      'Create unit test for peripheral changes before commit',
    ],
  },
  {
    id: 'rb-002',
    timestamp: new Date(Date.now() - 7200000).toISOString(),
    workflowId: 'wf-038',
    workflowName: 'DMA Buffer Size Increase',
    reason: 'Test assertion failed: buffer overflow detected in DMA ISR',
    trigger: 'automatic',
    steps: [
      {
        id: 'step-1',
        action: 'Restore original dma.c',
        before: 'Increased DMA buffer to 1024 bytes',
        after: 'DMA buffer restored to 256 bytes',
        reason: 'Buffer size increase caused overflow',
        timestamp: new Date(Date.now() - 7200000).toISOString(),
        status: 'completed',
      },
      {
        id: 'step-2',
        action: 'Validate memory constraints',
        before: 'No memory validation',
        after: 'Added static analysis check',
        reason: 'Prevent similar issue',
        timestamp: new Date(Date.now() - 7190000).toISOString(),
        status: 'completed',
      },
    ],
    impact: {
      filesAffected: 1,
      linesChanged: -23,
      tasksReverted: 1,
    },
    preventions: [
      'Run memory footprint analysis before DMA changes',
      'Add boundary checks in ISR',
    ],
  },
  {
    id: 'rb-003',
    timestamp: new Date(Date.now() - 86400000).toISOString(),
    workflowId: 'wf-030',
    workflowName: 'Clock Configuration Change',
    reason: 'Manual rollback requested by engineer',
    trigger: 'manual',
    steps: [
      {
        id: 'step-1',
        action: 'Restore clock configuration',
        before: 'PLL@180MHz, SYSCLK@90MHz',
        after: 'PLL@168MHz, SYSCLK@84MHz (stock)',
        reason: 'Production stability requirement',
        timestamp: new Date(Date.now() - 86400000).toISOString(),
        status: 'completed',
      },
    ],
    impact: {
      filesAffected: 1,
      linesChanged: -12,
      tasksReverted: 0,
    },
  },
];

export function RollbackExplainer({
  onSelectEvent,
}: RollbackExplainerProps) {
  // Fetch real rollback data from API
  const { data: rollbackData, isLoading } = useQuery({
    queryKey: ['dashboard', 'rollbacks'],
    queryFn: () => dashboardApi.getRollbackEvents(20),
    staleTime: 30000,
  });

  // Convert API response to RollbackEvent format
  const realEvents: RollbackEvent[] = rollbackData?.events?.map((event, index) => ({
    id: `rb-${index.toString().padStart(3, '0')}`,
    timestamp: event.timestamp,
    workflowId: event.source || `source-${index}`,
    workflowName: event.message.split(':')[0] || 'Unknown Workflow',
    reason: event.reason,
    trigger: event.level === 'error' ? 'automatic' : 'manual',
    steps: [
      {
        id: `step-1-${index}`,
        action: `Process rollback for: ${event.message.substring(0, 50)}...`,
        before: 'Modified state',
        after: 'Restored to previous state',
        reason: event.reason,
        timestamp: event.timestamp,
        status: 'completed' as const,
      },
    ],
    impact: {
      filesAffected: 1,
      linesChanged: -10,
      tasksReverted: 1,
    },
  })) || [];

  // Use real data if available, otherwise sample
  const events = realEvents.length > 0 ? realEvents : sampleEvents;

  const [selectedEventId, setSelectedEventId] = useState<string | null>(
    events.length > 0 ? events[0].id : null
  );
  const [expandedSteps, setExpandedSteps] = useState<Set<string>>(new Set());
  const [filterTrigger, setFilterTrigger] = useState<'all' | 'automatic' | 'manual'>('all');

  const selectedEvent = events.find(e => e.id === selectedEventId);

  const filteredEvents = events.filter(e =>
    filterTrigger === 'all' || e.trigger === filterTrigger
  );

  const toggleStep = (stepId: string) => {
    setExpandedSteps(prev => {
      const next = new Set(prev);
      if (next.has(stepId)) {
        next.delete(stepId);
      } else {
        next.add(stepId);
      }
      return next;
    });
  };

  const getStatusIcon = (status: RollbackStep['status']) => {
    switch (status) {
      case 'completed':
        return <span className="text-green-400">✓</span>;
      case 'failed':
        return <span className="text-red-400">✕</span>;
      case 'skipped':
        return <span className="text-gray-400">○</span>;
    }
  };

  const getTriggerBadge = (trigger: RollbackEvent['trigger']) => {
    switch (trigger) {
      case 'automatic':
        return <Badge variant="error">Auto</Badge>;
      case 'manual':
        return <Badge variant="warning">Manual</Badge>;
      case 'error':
        return <Badge variant="error">Error</Badge>;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        <span className="ml-3 text-gray-400">Loading rollback events...</span>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Event List */}
      <div className="lg:col-span-1 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-medium text-white">Rollback History</h3>
          <Badge variant="info">{events.length} events</Badge>
        </div>

        {/* Filter */}
        <div className="flex gap-2">
          {(['all', 'automatic', 'manual'] as const).map(filter => (
            <button
              key={filter}
              onClick={() => setFilterTrigger(filter)}
              className={`
                px-3 py-1.5 text-xs rounded capitalize transition-colors
                ${filterTrigger === filter
                  ? 'bg-blue-600 text-white'
                  : 'bg-gray-700 text-gray-400 hover:text-white'
                }
              `}
            >
              {filter}
            </button>
          ))}
        </div>

        {/* Event Cards */}
        <div className="space-y-2 max-h-[500px] overflow-y-auto">
          {filteredEvents.map(event => (
            <div
              key={event.id}
              onClick={() => {
                setSelectedEventId(event.id);
                onSelectEvent?.(event);
              }}
              className={`
                p-4 rounded-lg cursor-pointer transition-colors
                ${selectedEventId === event.id
                  ? 'bg-blue-900/40 border border-blue-500'
                  : 'bg-gray-800 hover:bg-gray-700 border border-transparent'
                }
              `}
            >
              <div className="flex items-start justify-between mb-2">
                <div>
                  <p className="text-sm font-medium text-white">{event.workflowName}</p>
                  <p className="text-xs text-gray-500">{event.id}</p>
                </div>
                {getTriggerBadge(event.trigger)}
              </div>
              <p className="text-xs text-gray-400 line-clamp-2 mb-2">
                {event.reason}
              </p>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                <span>{event.steps.length} steps</span>
                <span>{event.impact.filesAffected} files</span>
                <span>{new Date(event.timestamp).toLocaleDateString()}</span>
              </div>
            </div>
          ))}

          {filteredEvents.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No rollback events match the filter
            </div>
          )}
        </div>
      </div>

      {/* Event Details */}
      <div className="lg:col-span-2 space-y-4">
        {selectedEvent ? (
          <>
            {/* Event Header */}
            <Card>
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-xl font-medium text-white">
                    {selectedEvent.workflowName}
                  </h3>
                  <p className="text-sm text-gray-400">
                    {selectedEvent.workflowId} • {new Date(selectedEvent.timestamp).toLocaleString()}
                  </p>
                </div>
                {getTriggerBadge(selectedEvent.trigger)}
              </div>

              {/* Reason */}
              <div className="bg-red-900/30 border border-red-800 rounded-lg p-4 mb-4">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-red-400 text-lg">⚠</span>
                  <span className="text-sm font-medium text-red-300">Rollback Reason</span>
                </div>
                <p className="text-sm text-red-200">{selectedEvent.reason}</p>
              </div>

              {/* Impact */}
              <div className="grid grid-cols-3 gap-4">
                <div className="bg-gray-700/50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-white">{selectedEvent.impact.filesAffected}</p>
                  <p className="text-xs text-gray-400">Files Affected</p>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-red-400">-{selectedEvent.impact.linesChanged}</p>
                  <p className="text-xs text-gray-400">Lines Changed</p>
                </div>
                <div className="bg-gray-700/50 rounded-lg p-3 text-center">
                  <p className="text-2xl font-bold text-yellow-400">{selectedEvent.impact.tasksReverted}</p>
                  <p className="text-xs text-gray-400">Tasks Reverted</p>
                </div>
              </div>
            </Card>

            {/* Steps */}
            <Card title="Rollback Steps">
              <div className="space-y-3">
                {selectedEvent.steps.map((step, index) => (
                  <div
                    key={step.id}
                    className={`
                      border rounded-lg overflow-hidden
                      ${step.status === 'completed' ? 'border-green-800' : ''}
                      ${step.status === 'failed' ? 'border-red-800' : ''}
                      ${step.status === 'skipped' ? 'border-gray-700' : ''}
                    `}
                  >
                    {/* Step Header */}
                    <button
                      onClick={() => toggleStep(step.id)}
                      className="w-full flex items-center gap-3 p-4 bg-gray-800/50 hover:bg-gray-700/50 transition-colors"
                    >
                      <div className="flex items-center justify-center w-6 h-6 rounded-full bg-gray-700 text-xs font-mono">
                        {index + 1}
                      </div>
                      {getStatusIcon(step.status)}
                      <div className="flex-1 text-left">
                        <p className="text-sm text-white">{step.action}</p>
                        <p className="text-xs text-gray-500">{step.reason}</p>
                      </div>
                      <span className={`text-xs ${expandedSteps.has(step.id) ? 'rotate-180' : ''}`}>
                        ▼
                      </span>
                    </button>

                    {/* Step Details */}
                    {expandedSteps.has(step.id) && (
                      <div className="p-4 bg-gray-900/50 space-y-3">
                        <div>
                          <p className="text-xs text-gray-500 mb-1">Before</p>
                          <code className="block bg-gray-800 text-red-300 text-xs p-2 rounded">
                            {step.before}
                          </code>
                        </div>
                        <div>
                          <p className="text-xs text-gray-500 mb-1">After</p>
                          <code className="block bg-gray-800 text-green-300 text-xs p-2 rounded">
                            {step.after}
                          </code>
                        </div>
                        <div className="text-xs text-gray-500">
                          Executed: {new Date(step.timestamp).toLocaleString()}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>

            {/* Prevention Measures */}
            {selectedEvent.preventions && selectedEvent.preventions.length > 0 && (
              <Card title="Prevention Measures">
                <div className="space-y-2">
                  {selectedEvent.preventions.map((prevention, i) => (
                    <div key={i} className="flex items-start gap-3 p-3 bg-green-900/20 border border-green-800/50 rounded-lg">
                      <span className="text-green-400 mt-0.5">✓</span>
                      <p className="text-sm text-green-200">{prevention}</p>
                    </div>
                  ))}
                </div>
              </Card>
            )}
          </>
        ) : (
          <div className="flex items-center justify-center h-64 bg-gray-800 rounded-lg">
            <p className="text-gray-500">Select a rollback event to view details</p>
          </div>
        )}
      </div>
    </div>
  );
}
