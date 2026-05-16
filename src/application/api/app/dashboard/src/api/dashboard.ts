import type {
  DashboardOverview,
  HealthCheck,
  WorkflowStatusResponse,
  WorkflowHistoryResponse,
  RollbackEventsResponse,
  TokenUsageResponse,
  HardwareStatus,
  TimelineResponse,
  LogsResponse,
} from '@/types/dashboard';

const API_BASE = '/api';

// ============================================================================
// Reasoning/Confidence Types
// ============================================================================

export interface ConfidenceFactor {
  id: string;
  label: string;
  description: string;
  impact: 'positive' | 'negative' | 'neutral';
  weight: number;
  evidence?: string[];
}

export interface ReasoningStep {
  step: number;
  description: string;
  conclusion: string;
  confidence_delta: number;
}

export interface SourceRef {
  file: string;
  line?: number;
  snippet?: string;
  relevance: 'high' | 'medium' | 'low';
}

export interface ReasoningChain {
  id: string;
  question: string;
  answer: string;
  confidence: number;
  factors: ConfidenceFactor[];
  sources: SourceRef[];
  reasoning_steps: ReasoningStep[];
  limitations?: string[];
}

export interface ReasoningRequest {
  question: string;
  context?: Record<string, unknown>;
}

// ============================================================================
// Chat API
// ============================================================================

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  confidence?: number;
  reasoning?: string;
  sources?: string[];
}

export interface ChatRequest {
  message: string;
  context?: Record<string, unknown>;
}

export interface ChatResponse {
  message: string;
  success: boolean;
  agent_version: string;
  context?: Record<string, unknown>;
}

export interface ChatHistoryResponse {
  history: ChatMessage[];
  total: number;
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

export const chatApi = {
  async sendMessage(message: string, context?: Record<string, unknown>): Promise<ChatResponse> {
    return fetchJson<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, context }),
    });
  },

  async getHistory(limit = 50): Promise<ChatHistoryResponse> {
    return fetchJson<ChatHistoryResponse>(`/chat/history?limit=${limit}`);
  },

  async clearHistory(): Promise<{ status: string }> {
    return fetchJson<{ status: string }>('/chat/history', { method: 'DELETE' });
  },

  async analyzeReasoning(question: string, context?: Record<string, unknown>): Promise<ReasoningChain> {
    return fetchJson<ReasoningChain>('/reasoning/analyze', {
      method: 'POST',
      body: JSON.stringify({ question, context }),
    });
  },

  async getConfidenceFactors(): Promise<{
    factors: Array<{ id: string; label: string; weight_range: number[] }>;
  }> {
    return fetchJson<{ factors: Array<{ id: string; label: string; weight_range: number[] }> }>(
      '/reasoning/factors'
    );
  },
};

export interface CallGraphData {
  entry_points: string[];
  functions: Record<string, {
    name: string;
    file: string;
    callees: string[];
    callers: string[];
  }>;
  total_functions: number;
  orphaned_count: number;
  error?: string;
  timestamp: string;
}

export const dashboardApi = {
  // Overview
  async getOverview(): Promise<DashboardOverview> {
    return fetchJson<DashboardOverview>('/dashboard/overview');
  },

  // Health
  async getHealth(): Promise<HealthCheck> {
    return fetchJson<HealthCheck>('/dashboard/health');
  },

  // Workflows
  async getWorkflowStatus(): Promise<WorkflowStatusResponse> {
    return fetchJson<WorkflowStatusResponse>('/dashboard/workflows');
  },

  async getWorkflowHistory(limit = 50, offset = 0): Promise<WorkflowHistoryResponse> {
    return fetchJson<WorkflowHistoryResponse>(`/dashboard/workflows/history?limit=${limit}&offset=${offset}`);
  },

  // Rollbacks
  async getRollbackEvents(limit = 20): Promise<RollbackEventsResponse> {
    return fetchJson<RollbackEventsResponse>(`/dashboard/rollbacks?limit=${limit}`);
  },

  // Call Graph
  async getCallGraph(entryPoint?: string, maxDepth = 3): Promise<CallGraphData> {
    const params = new URLSearchParams();
    if (entryPoint) params.append('entry_point', entryPoint);
    params.append('max_depth', maxDepth.toString());
    return fetchJson<CallGraphData>(`/dashboard/callgraph?${params}`);
  },

  // Tokens
  async getTokenUsage(): Promise<TokenUsageResponse> {
    return fetchJson<TokenUsageResponse>('/dashboard/tokens');
  },

  async getContextUsage() {
    return fetchJson<{
      current: { used_tokens: number; max_tokens: number; usage_percent: number };
      by_phase: Record<string, number>;
      timestamp: string;
    }>('/dashboard/context');
  },

  // Hardware
  async getHardwareStatus(): Promise<HardwareStatus> {
    return fetchJson<HardwareStatus>('/dashboard/hardware');
  },

  // Timeline
  async getEventTimeline(limit = 100, level?: string): Promise<TimelineResponse> {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (level) params.append('level', level);
    return fetchJson<TimelineResponse>(`/dashboard/timeline?${params}`);
  },

  // Prometheus metrics
  async getPrometheusMetrics(): Promise<string> {
    const response = await fetch(`${API_BASE}/dashboard/prometheus`);
    return response.text();
  },

  // Logs
  async getLogs(limit = 100, level?: string): Promise<LogsResponse> {
    const params = new URLSearchParams({ limit: limit.toString() });
    if (level) params.append('level', level);
    return fetchJson<LogsResponse>(`/logs?${params}`);
  },
};
