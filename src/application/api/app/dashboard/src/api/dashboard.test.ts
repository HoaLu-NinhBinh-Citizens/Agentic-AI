import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock fetch globally
const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe('dashboardApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getOverview', () => {
    it('fetches overview data successfully', async () => {
      const mockData = {
        system: {
          agent_initialized: true,
          uptime_seconds: 3600,
          uptime_human: '1h 0m',
          task_count: 42,
          success_count: 40,
          error_count: 2,
          success_rate: 95.2,
        },
        resources: {
          cpu: 45.5,
          memory: 62.3,
          speed: 1500,
          temperature: 45.0,
        },
        workflow: {
          active: 2,
          queued: 5,
          completed: 35,
          failed: 2,
        },
        timestamp: '2024-01-01T12:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getOverview();

      expect(result).toEqual(mockData);
      expect(mockFetch).toHaveBeenCalledWith('/api/dashboard/overview', expect.any(Object));
    });

    it('throws error on failed response', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });

      const { dashboardApi } = await import('@/api/dashboard');

      await expect(dashboardApi.getOverview()).rejects.toThrow('API Error: 500 Internal Server Error');
    });
  });

  describe('getHealth', () => {
    it('fetches health status', async () => {
      const mockData = {
        overall: 'healthy',
        checks: {
          agent: { status: 'up', latency_ms: 15 },
          metrics: { status: 'up', count: 100 },
        },
        alerts: [],
        timestamp: '2024-01-01T12:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getHealth();

      expect(result).toEqual(mockData);
      expect(mockFetch).toHaveBeenCalledWith('/api/dashboard/health', expect.any(Object));
    });
  });

  describe('getWorkflowStatus', () => {
    it('fetches workflow status', async () => {
      const mockData = {
        workflows: [
          { state: 'running', source: 'agent', timestamp: '2024-01-01T12:00:00Z' },
          { state: 'completed', source: 'system', timestamp: '2024-01-01T11:30:00Z' },
        ],
        total: 2,
        timestamp: '2024-01-01T12:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getWorkflowStatus();

      expect(result).toEqual(mockData);
      expect(result.workflows).toHaveLength(2);
    });
  });

  describe('getWorkflowHistory', () => {
    it('fetches workflow history with pagination', async () => {
      const mockData = {
        workflows: [
          { id: 'wf-001', timestamp: '2024-01-01T12:00:00Z', level: 'info', source: 'agent', message: 'Task completed' },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getWorkflowHistory(50, 0);

      expect(result).toEqual(mockData);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/dashboard/workflows/history?limit=50&offset=0',
        expect.any(Object)
      );
    });

    it('uses default pagination', async () => {
      const mockData = {
        workflows: [],
        total: 0,
        limit: 50,
        offset: 0,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      await dashboardApi.getWorkflowHistory();

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/dashboard/workflows/history?limit=50&offset=0',
        expect.any(Object)
      );
    });
  });

  describe('getRollbackEvents', () => {
    it('fetches rollback events', async () => {
      const mockData = {
        events: [
          {
            timestamp: '2024-01-01T12:00:00Z',
            source: 'agent',
            level: 'error',
            message: 'Task failed',
            reason: 'timeout',
          },
        ],
        count: 1,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getRollbackEvents(20);

      expect(result).toEqual(mockData);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/dashboard/rollbacks?limit=20',
        expect.any(Object)
      );
    });
  });

  describe('getTokenUsage', () => {
    it('fetches token usage data', async () => {
      const mockData = {
        current_session: {
          input_tokens: 1000,
          output_tokens: 500,
          total_tokens: 1500,
        },
        limits: { daily_limit: 100000, monthly_limit: 3000000 },
        costs: { estimated: 0.05 },
        history_24h: [],
        timestamp: '2024-01-01T12:00:00Z',
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getTokenUsage();

      expect(result.current_session.total_tokens).toBe(1500);
    });
  });

  describe('getHardwareStatus', () => {
    it('fetches hardware status', async () => {
      const mockData = {
        connected: true,
        boards: [
          { id: 'board-1', name: 'STM32F407', type: 'STM32', status: 'connected' },
        ],
        uart_streams: [
          { port: 'COM3', baudrate: 115200, data: ['line1', 'line2'], status: 'active' },
        ],
        last_update: '2024-01-01T12:00:00Z',
        mock_mode: false,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getHardwareStatus();

      expect(result.connected).toBe(true);
      expect(result.boards).toHaveLength(1);
    });
  });

  describe('getEventTimeline', () => {
    it('fetches event timeline', async () => {
      const mockData = {
        events: [
          { id: 'evt-1', timestamp: '2024-01-01T12:00:00Z', level: 'info', source: 'agent', message: 'Task started', type: 'task_start' },
        ],
        total: 1,
        by_level: { info: 1 },
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getEventTimeline(100, 'info');

      expect(result.events).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/dashboard/timeline?limit=100&level=info',
        expect.any(Object)
      );
    });

    it('fetches without level filter', async () => {
      const mockData = {
        events: [],
        total: 0,
        by_level: {},
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      await dashboardApi.getEventTimeline(50);

      expect(mockFetch).toHaveBeenCalledWith(
        '/api/dashboard/timeline?limit=50',
        expect.any(Object)
      );
    });
  });

  describe('getPrometheusMetrics', () => {
    it('fetches metrics as text', async () => {
      const mockText = '# HELP process_cpu_seconds_total CPU usage\nprocess_cpu_seconds_total 0.5';

      mockFetch.mockResolvedValueOnce({
        ok: true,
        text: () => Promise.resolve(mockText),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getPrometheusMetrics();

      expect(result).toBe(mockText);
    });
  });

  describe('getLogs', () => {
    it('fetches logs with filters', async () => {
      const mockData = {
        logs: [
          { timestamp: '2024-01-01T12:00:00Z', level: 'info', source: 'agent', message: 'Test log' },
        ],
        total: 1,
      };

      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve(mockData),
      });

      const { dashboardApi } = await import('@/api/dashboard');
      const result = await dashboardApi.getLogs(100, 'info');

      expect(result.logs).toHaveLength(1);
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/logs?limit=100&level=info',
        expect.any(Object)
      );
    });
  });
});
