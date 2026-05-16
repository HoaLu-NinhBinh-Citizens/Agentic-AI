/**
 * Dashboard Types - Unified types from frontend
 *
 * Imports types from the main frontend types folder
 * to maintain type consistency across both dashboard implementations.
 *
 * Types are defined in: AI_support/frontend/src/types/dashboard.ts
 */

export type {
  SystemStatus,
  Resources,
  WorkflowState,
  HealthCheck,
  Alert,
  DashboardEvent,
  WorkflowHistoryItem,
  RollbackEvent,
  TokenUsage,
  TokenLimits,
  TokenCosts,
  TokenHistoryPoint,
  HardwareBoard,
  HardwareStatus,
  UartStream,
  TimelineEvent,
  DashboardOverview,
  WorkflowStatusResponse,
  WorkflowHistoryResponse,
  RollbackEventsResponse,
  TokenUsageResponse,
  TimelineResponse,
  LogsResponse,
  EventChannel,
} from '@frontend/types/dashboard';

// EventChannel constants for compatibility (avoiding naming conflict with the type)
export const EVENT_CHANNEL = {
  OVERVIEW: 'overview',
  WORKFLOWS: 'workflows',
  HARDWARE: 'hardware',
  METRICS: 'metrics',
  TIMELINE: 'timeline',
  ALERTS: 'alerts',
  ALL: 'all',
} as const;
