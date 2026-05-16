import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { dashboardApi } from '@/api/dashboard';
import { Card, StatusIndicator, Badge } from '@/components/ui';
import { useDashboardWebSocket } from '@/hooks/useDashboardWebSocket';
import { EVENT_CHANNEL } from '@/types/dashboard';

export function HardwareScreen() {
  const [uartOutput, setUartOutput] = useState<string[]>([]);
  const terminalRef = useRef<HTMLDivElement>(null);

  const { data: hardwareStatus, isLoading } = useQuery({
    queryKey: ['dashboard', 'hardware'],
    queryFn: dashboardApi.getHardwareStatus,
    refetchInterval: 5000,
  });

  const { isConnected, lastEvent } = useDashboardWebSocket({
    channels: [EVENT_CHANNEL.HARDWARE],
    onEvent: (event) => {
      if (event.channel === 'hardware' && event.data) {
        const data = event.data as { uart_data?: string[] };
        if (data.uart_data) {
          setUartOutput(prev => [...prev, ...data.uart_data!].slice(-100));
        }
      }
    },
  });

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [uartOutput]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
      </div>
    );
  }

  const boards = hardwareStatus?.boards || [];
  const isConnectedToHardware = hardwareStatus?.connected || boards.length > 0;
  const mockMode = hardwareStatus?.mock_mode ?? true;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Hardware / HIL</h1>
          <p className="text-sm text-gray-400 mt-1">
            Monitor hardware status and UART streams
          </p>
        </div>
        <div className="flex items-center gap-4">
          <StatusIndicator 
            status={isConnected ? 'connected' : 'disconnected'} 
            label="WebSocket"
            pulse={isConnected}
          />
          {mockMode && (
            <Badge variant="warning">Mock Mode</Badge>
          )}
        </div>
      </div>

      {/* Connection Status */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="Connection Status">
          <div className="flex items-center gap-4">
            <StatusIndicator 
              status={isConnectedToHardware ? 'connected' : 'disconnected'} 
              size="lg"
              pulse={isConnectedToHardware}
            />
            <div>
              <p className="text-lg font-medium text-white">
                {isConnectedToHardware ? 'Hardware Connected' : 'No Hardware'}
              </p>
              <p className="text-sm text-gray-400">
                {boards.length} board(s) detected
              </p>
            </div>
          </div>
        </Card>

        <Card title="Active Streams">
          <div className="text-center">
            <p className="text-3xl font-bold text-white">
              {hardwareStatus?.uart_streams?.length || 0}
            </p>
            <p className="text-sm text-gray-400">UART streams</p>
          </div>
        </Card>

        <Card title="Last Update">
          <div className="text-center">
            <p className="text-lg font-medium text-white">
              {hardwareStatus?.last_update 
                ? new Date(hardwareStatus.last_update).toLocaleTimeString()
                : 'Never'}
            </p>
            <p className="text-sm text-gray-400">System timestamp</p>
          </div>
        </Card>
      </div>

      {/* Board List */}
      {boards.length > 0 && (
        <Card title="Connected Boards">
          <div className="space-y-4">
            {boards.map((board) => (
              <div 
                key={board.id}
                className="flex items-center justify-between p-4 bg-gray-700/50 rounded-lg"
              >
                <div className="flex items-center gap-4">
                  <StatusIndicator 
                    status={board.status === 'connected' ? 'connected' : 'error'} 
                    size="lg"
                  />
                  <div>
                    <p className="text-lg font-medium text-white">{board.name}</p>
                    <p className="text-sm text-gray-400">
                      Type: {board.type} | ID: {board.id}
                    </p>
                  </div>
                </div>
                <div className="text-right">
                  <Badge variant={board.status === 'connected' ? 'success' : 'error'}>
                    {board.status.toUpperCase()}
                  </Badge>
                  {board.firmware_version && (
                    <p className="text-sm text-gray-400 mt-1">
                      FW: {board.firmware_version}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* UART Terminal */}
      <Card 
        title="UART Terminal" 
        className="col-span-full"
        headerRight={
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setUartOutput([])}
              className="px-3 py-1 text-xs bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
            >
              Clear
            </button>
            <StatusIndicator 
              status={uartOutput.length > 0 ? 'connected' : 'disconnected'} 
              label={uartOutput.length > 0 ? 'Live' : 'Idle'}
            />
          </div>
        }
      >
        <div 
          ref={terminalRef}
          className="bg-gray-900 rounded-lg p-4 h-80 overflow-y-auto font-mono text-sm"
        >
          {uartOutput.length === 0 ? (
            <div className="text-gray-500 text-center py-8">
              {mockMode 
                ? 'Mock mode active - No real UART data'
                : 'Waiting for UART data...'
              }
            </div>
          ) : (
            uartOutput.map((line, i) => (
              <div 
                key={i}
                className={`${
                  line.includes('ERROR') || line.includes('FAIL') 
                    ? 'text-red-400' 
                    : line.includes('WARN') 
                      ? 'text-yellow-400' 
                      : 'text-green-400'
                }`}
              >
                <span className="text-gray-600 mr-2">[{i.toString().padStart(4, '0')}]</span>
                {line}
              </div>
            ))
          )}
        </div>
      </Card>

      {/* Stream Details */}
      {hardwareStatus?.uart_streams && hardwareStatus.uart_streams.length > 0 && (
        <Card title="Stream Details">
          <div className="space-y-4">
            {hardwareStatus.uart_streams.map((stream, i) => (
              <div key={i} className="p-4 bg-gray-700/50 rounded-lg">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-blue-400">{stream.port}</span>
                    <span className="text-gray-500">@</span>
                    <span className="font-mono text-purple-400">{stream.baudrate} baud</span>
                  </div>
                  <Badge variant={stream.status === 'active' ? 'success' : 'default'}>
                    {stream.status.toUpperCase()}
                  </Badge>
                </div>
                <p className="text-sm text-gray-400">
                  {stream.data.length} lines buffered
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Quick Actions */}
      <Card title="Quick Actions">
        <div className="flex flex-wrap gap-4">
          <button 
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
            disabled={mockMode}
          >
            Connect Hardware
          </button>
          <button 
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
            disabled={!isConnectedToHardware}
          >
            Flash Firmware
          </button>
          <button 
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            Run E2E Test
          </button>
          <button 
            className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
          >
            Export UART Log
          </button>
        </div>
      </Card>
    </div>
  );
}
