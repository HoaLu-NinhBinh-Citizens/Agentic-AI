/**
 * Dashboard WebSocket Hook
 *
 * Provides real-time WebSocket connection for dashboard updates.
 * Uses shared types from @/types/dashboard.
 */

import { useEffect, useRef, useCallback, useState } from 'react';
import type { DashboardEvent } from '@/types/dashboard';
import { EventChannel } from '@/types/dashboard';

interface UseDashboardWebSocketOptions {
  url?: string;
  channels?: EventChannel[];
  onEvent?: (event: DashboardEvent) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
  enabled?: boolean;
}

interface UseDashboardWebSocketReturn {
  isConnected: boolean;
  lastEvent: DashboardEvent | null;
  subscribe: (channel: EventChannel) => void;
  unsubscribe: (channel: EventChannel) => void;
  sendPing: () => void;
}

export function useDashboardWebSocket(
  options: UseDashboardWebSocketOptions = {}
): UseDashboardWebSocketReturn {
  const {
    url = `ws://${window.location.host}/ws/dashboard`,
    channels = ['all' as EventChannel],
    onEvent,
    onConnect,
    onDisconnect,
    reconnectInterval = 5000,
    enabled = true,
  } = options;

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<DashboardEvent | null>(null);

  const connect = useCallback(() => {
    if (!enabled) return;

    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        onConnect?.();

        // Subscribe to channels
        channels.forEach(channel => {
          ws.send(`subscribe:${channel}`);
        });
      };

      ws.onmessage = (event) => {
        try {
          const data: DashboardEvent = JSON.parse(event.data);
          setLastEvent(data);
          onEvent?.(data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        onDisconnect?.();

        // Attempt reconnection
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, reconnectInterval);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        ws.close();
      };
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
    }
  }, [url, channels, enabled, onEvent, onConnect, onDisconnect, reconnectInterval]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const subscribe = useCallback((channel: EventChannel) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(`subscribe:${channel}`);
    }
  }, []);

  const unsubscribe = useCallback((channel: EventChannel) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(`unsubscribe:${channel}`);
    }
  }, []);

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send('ping');
    }
  }, []);

  useEffect(() => {
    if (enabled) {
      connect();
    }

    return () => {
      disconnect();
    };
  }, [connect, disconnect, enabled]);

  return {
    isConnected,
    lastEvent,
    subscribe,
    unsubscribe,
    sendPing,
  };
}
