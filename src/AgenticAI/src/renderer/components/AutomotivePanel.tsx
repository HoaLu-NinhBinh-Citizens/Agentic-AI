import React, { useState, useCallback, useEffect, useRef } from 'react';
import {
  Car,
  Wifi,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Play,
  Pause,
  Settings,
  Download,
  Upload,
  Eye,
  Loader2,
  FileSearch,
} from 'lucide-react';
import { useAIAgent } from '../hooks/useAIAgent';

interface CANMessage {
  id: string;
  timestamp: string;
  canId: string;
  dlc: number;
  data: string;
  direction: 'rx' | 'tx';
  protocol?: 'standard' | 'extended';
}

interface UDSRequest {
  service: string;
  did?: string;
  data?: string;
  status: 'pending' | 'success' | 'error';
  response?: string;
}

interface FirmwareAnalysisResult {
  summary: string;
  issues: string[];
  dependencies: string[];
}

export const AutomotivePanel: React.FC = () => {
  const { 
    isConnected, 
    isConnecting, 
    connect, 
    disconnect,
    analyzeFirmware,
    debugFirmware,
    error: agentError,
  } = useAIAgent();

  const [activeTab, setActiveTab] = useState<'can' | 'lin' | 'uds' | 'ota' | 'diagnostics'>('can');
  const [canMessages, setCanMessages] = useState<CANMessage[]>([]);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const [udsRequests, setUdsRequests] = useState<UDSRequest[]>([]);
  const [selectedCanId, setSelectedCanId] = useState<string | null>(null);

  // Demo CAN messages
  const demoMessages: CANMessage[] = [
    { id: '1', timestamp: '10:23:45.123', canId: '0x100', dlc: 8, data: '01 02 03 04 05 06 07 08', direction: 'rx' },
    { id: '2', timestamp: '10:23:45.234', canId: '0x200', dlc: 8, data: 'AA BB CC DD EE FF 00 11', direction: 'tx' },
    { id: '3', timestamp: '10:23:45.456', canId: '0x300', dlc: 4, data: '12 34 56 78', direction: 'rx', protocol: 'extended' },
    { id: '4', timestamp: '10:23:45.567', canId: '0x400', dlc: 8, data: 'FE DC BA 98 76 54 32 10', direction: 'rx' },
    { id: '5', timestamp: '10:23:45.678', canId: '0x123', dlc: 3, data: 'FF FF FF', direction: 'tx' },
  ];

  // UDS Services
  const udsServices = [
    { id: '0x10', name: 'Diagnostic Session Control', description: 'Start/stop diagnostic session' },
    { id: '0x11', name: 'ECU Reset', description: 'Reset the ECU' },
    { id: '0x14', name: 'Clear DTC', description: 'Clear diagnostic trouble codes' },
    { id: '0x19', name: 'Read DTC Info', description: 'Read diagnostic trouble codes' },
    { id: '0x22', name: 'Read Data By ID', description: 'Read data by identifier' },
    { id: '0x27', name: 'Security Access', description: 'Unlock secured services' },
    { id: '0x2E', name: 'Write Data By ID', description: 'Write data by identifier' },
    { id: '0x34', name: 'Request Download', description: 'Start download session' },
    { id: '0x36', name: 'Transfer Data', description: 'Transfer data blocks' },
    { id: '0x3E', name: 'Tester Present', description: 'Keep session alive' },
  ];

  // Diagnostics state
  const [firmwareCode, setFirmwareCode] = useState(`// Example: Analyze this CAN initialization code
void CAN_Init(void) {
    // Enable CAN clock
    RCC->APB1ENR |= RCC_APB1ENR_CAN1EN;
    
    // Enter init mode
    CAN1->MCR |= CAN_MCR_INRQ;
    while (!(CAN1->MCR & CAN_MCR_INAK));
    
    // Configure bit timing
    CAN1->BTR = 0x001c0003; // 500kbps @ 42MHz APB1
    
    // Leave init mode
    CAN1->MCR &= ~CAN_MCR_INRQ;
}`);

  const [analysisResult, setAnalysisResult] = useState<FirmwareAnalysisResult | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [debugError, setDebugError] = useState('');
  const [debugResult, setDebugResult] = useState<string | null>(null);
  const [isDebugging, setIsDebugging] = useState(false);

  const handleStartMonitoring = useCallback(() => {
    setIsMonitoring(true);
    setCanMessages(demoMessages);
  }, []);

  const handleStopMonitoring = useCallback(() => {
    setIsMonitoring(false);
  }, []);

  const handleClearMessages = useCallback(() => {
    setCanMessages([]);
  }, []);

  const handleSendUDS = useCallback((serviceId: string) => {
    const request: UDSRequest = {
      service: serviceId,
      status: 'pending',
    };

    setUdsRequests(prev => [...prev, request]);

    // Simulate response
    setTimeout(() => {
      setUdsRequests(prev =>
        prev.map(r =>
          r === request
            ? {
                ...r,
                status: Math.random() > 0.2 ? 'success' : 'error',
                response: Math.random() > 0.2
                  ? 'Positive response: 7F ' + serviceId + ' 00'
                  : 'Negative response: 7F ' + serviceId + ' 22',
              }
            : r
        )
      );
    }, 500 + Math.random() * 500);
  }, []);

  return (
    <div className="automotive-panel h-full flex flex-col bg-[#1e1e1e] text-[#cccccc]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#3c3c3c]">
        <div className="flex items-center gap-2">
          <Car className="w-4 h-4" />
          <span className="font-medium">Automotive</span>
          <button
            onClick={() => isConnected ? disconnect() : connect()}
            disabled={isConnecting}
            className={`ml-2 px-2 py-0.5 rounded text-xs ${
              isConnected
                ? 'bg-green-600 hover:bg-green-700 text-white'
                : 'bg-yellow-600 hover:bg-yellow-700 text-white'
            }`}
          >
            {isConnecting ? 'Connecting...' : isConnected ? 'AI: ON' : 'AI: OFF'}
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('can')}
            className={`px-3 py-1 rounded text-xs ${
              activeTab === 'can' ? 'bg-[#007acc] text-white' : 'bg-[#3c3c3c]'
            }`}
          >
            CAN
          </button>
          <button
            onClick={() => setActiveTab('lin')}
            className={`px-3 py-1 rounded text-xs ${
              activeTab === 'lin' ? 'bg-[#007acc] text-white' : 'bg-[#3c3c3c]'
            }`}
          >
            LIN
          </button>
          <button
            onClick={() => setActiveTab('uds')}
            className={`px-3 py-1 rounded text-xs ${
              activeTab === 'uds' ? 'bg-[#007acc] text-white' : 'bg-[#3c3c3c]'
            }`}
          >
            UDS
          </button>
          <button
            onClick={() => setActiveTab('ota')}
            className={`px-3 py-1 rounded text-xs ${
              activeTab === 'ota' ? 'bg-[#007acc] text-white' : 'bg-[#3c3c3c]'
            }`}
          >
            OTA
          </button>
          <button
            onClick={() => setActiveTab('diagnostics')}
            className={`px-3 py-1 rounded text-xs ${
              activeTab === 'diagnostics' ? 'bg-[#007acc] text-white' : 'bg-[#3c3c3c]'
            }`}
          >
            AI Diagnostics
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'can' && (
          <div className="p-2">
            {/* Toolbar */}
            <div className="flex items-center gap-2 mb-3">
              <button
                onClick={isMonitoring ? handleStopMonitoring : handleStartMonitoring}
                className={`px-3 py-2 rounded text-xs flex items-center gap-2 ${
                  isMonitoring
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-green-600 hover:bg-green-700 text-white'
                }`}
              >
                {isMonitoring ? (
                  <>
                    <Pause className="w-3 h-3" />
                    Stop
                  </>
                ) : (
                  <>
                    <Play className="w-3 h-3" />
                    Start
                  </>
                )}
              </button>
              <button
                onClick={handleClearMessages}
                className="px-3 py-2 bg-[#3c3c3c] hover:bg-[#4c4c4c] rounded text-xs"
              >
                Clear
              </button>
              <div className="flex-1" />
              <span className="text-xs text-[#808080]">
                {canMessages.length} messages
              </span>
            </div>

            {/* Filter */}
            <div className="flex items-center gap-2 mb-3">
              <input
                type="text"
                placeholder="Filter by CAN ID..."
                className="flex-1 px-3 py-2 bg-[#2d2d2d] border border-[#3c3c3c] rounded text-xs"
                onChange={(e) => setSelectedCanId(e.target.value || null)}
              />
            </div>

            {/* Message Table */}
            <div className="bg-[#2d2d2d] rounded border border-[#3c3c3c] overflow-hidden">
              <div className="grid grid-cols-5 gap-2 px-3 py-2 bg-[#333] text-xs text-[#808080] border-b border-[#3c3c3c]">
                <div>Time</div>
                <div>CAN ID</div>
                <div>DLC</div>
                <div>Data</div>
                <div>Dir</div>
              </div>
              <div className="max-h-64 overflow-y-auto">
                {canMessages
                  .filter(m => !selectedCanId || m.canId.includes(selectedCanId))
                  .map((msg) => (
                    <div
                      key={msg.id}
                      className="grid grid-cols-5 gap-2 px-3 py-2 text-xs border-b border-[#3c3c3c] hover:bg-[#333] last:border-b-0"
                    >
                      <div className="font-mono">{msg.timestamp}</div>
                      <div className={`font-mono ${msg.protocol === 'extended' ? 'text-[#4ec9b0]' : 'text-[#569cd6]'}`}>
                        {msg.canId}
                      </div>
                      <div className="text-[#808080]">{msg.dlc}</div>
                      <div className="font-mono text-[#ce9178]">{msg.data}</div>
                      <div className={msg.direction === 'rx' ? 'text-green-400' : 'text-yellow-400'}>
                        {msg.direction === 'rx' ? 'RX' : 'TX'}
                      </div>
                    </div>
                  ))}
                {canMessages.length === 0 && (
                  <div className="px-3 py-8 text-center text-xs text-[#808080]">
                    {isMonitoring ? 'Waiting for CAN messages...' : 'Click Start to begin monitoring'}
                  </div>
                )}
              </div>
            </div>

            {/* Statistics */}
            <div className="mt-3 grid grid-cols-4 gap-2">
              <div className="bg-[#2d2d2d] rounded p-2 text-center">
                <div className="text-lg font-mono text-[#569cd6]">{canMessages.filter(m => m.direction === 'rx').length}</div>
                <div className="text-xs text-[#808080]">RX</div>
              </div>
              <div className="bg-[#2d2d2d] rounded p-2 text-center">
                <div className="text-lg font-mono text-[#ce9178]">{canMessages.filter(m => m.direction === 'tx').length}</div>
                <div className="text-xs text-[#808080]">TX</div>
              </div>
              <div className="bg-[#2d2d2d] rounded p-2 text-center">
                <div className="text-lg font-mono text-[#4ec9b0]">
                  {new Set(canMessages.map(m => m.canId)).size}
                </div>
                <div className="text-xs text-[#808080]">IDs</div>
              </div>
              <div className="bg-[#2d2d2d] rounded p-2 text-center">
                <div className="text-lg font-mono text-[#dcdcaa]">
                  {canMessages.reduce((sum, m) => sum + m.dlc, 0)}
                </div>
                <div className="text-xs text-[#808080]">Bytes</div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'lin' && (
          <div className="p-2">
            <div className="bg-[#2d2d2d] rounded p-4 text-center text-sm text-[#808080]">
              <Wifi className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>LIN analyzer coming soon</p>
              <p className="text-xs mt-2">Support for LIN 1.3, 2.0, 2.1, J2602</p>
            </div>
          </div>
        )}

        {activeTab === 'uds' && (
          <div className="p-2">
            <div className="mb-3">
              <h3 className="text-sm font-medium mb-2">UDS Diagnostic Services</h3>
              <div className="grid grid-cols-2 gap-2">
                {udsServices.map((service) => (
                  <button
                    key={service.id}
                    onClick={() => handleSendUDS(service.id)}
                    className="bg-[#2d2d2d] hover:bg-[#3c3c3c] rounded p-2 text-left border border-[#3c3c3c]"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-[#569cd6]">{service.id}</span>
                      <Play className="w-3 h-3 text-[#808080]" />
                    </div>
                    <div className="text-xs mt-1">{service.name}</div>
                    <div className="text-xs text-[#808080] mt-1">{service.description}</div>
                  </button>
                ))}
              </div>
            </div>

            {/* Request History */}
            <div className="mt-4">
              <h3 className="text-sm font-medium mb-2">Request History</h3>
              <div className="space-y-2">
                {udsRequests.slice(-5).reverse().map((req, i) => (
                  <div
                    key={i}
                    className={`bg-[#2d2d2d] rounded p-2 border ${
                      req.status === 'pending'
                        ? 'border-yellow-600'
                        : req.status === 'success'
                        ? 'border-green-600'
                        : 'border-red-600'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs text-[#569cd6]">{req.service}</span>
                      {req.status === 'pending' && (
                        <RefreshCw className="w-3 h-3 animate-spin text-yellow-400" />
                      )}
                      {req.status === 'success' && (
                        <CheckCircle className="w-3 h-3 text-green-400" />
                      )}
                      {req.status === 'error' && (
                        <XCircle className="w-3 h-3 text-red-400" />
                      )}
                    </div>
                    {req.response && (
                      <div className="mt-1 text-xs font-mono text-[#808080]">{req.response}</div>
                    )}
                  </div>
                ))}
                {udsRequests.length === 0 && (
                  <div className="text-center text-xs text-[#808080] py-4">
                    No requests sent yet
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {activeTab === 'ota' && (
          <div className="p-2">
            <div className="bg-[#2d2d2d] rounded p-4 mb-3">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-medium">Current Version</h3>
                <span className="px-2 py-1 bg-[#007acc] rounded text-xs">v1.2.3</span>
              </div>
              <div className="text-xs text-[#808080]">
                <div>Device: ECU_01</div>
                <div>Last Update: 2024-01-15</div>
                <div>Storage: 256 KB / 1 MB</div>
              </div>
            </div>

            <div className="bg-[#2d2d2d] rounded p-4 mb-3">
              <h3 className="text-sm font-medium mb-3">Available Updates</h3>
              <div className="space-y-2">
                <div className="bg-[#333] rounded p-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">v1.2.4</span>
                    <button className="px-2 py-1 bg-[#007acc] hover:bg-[#1177bb] rounded text-xs">
                      <Download className="w-3 h-3 inline mr-1" />
                      Download
                    </button>
                  </div>
                  <div className="text-xs text-[#808080] mt-1">
                    Bug fixes, improved CAN stability
                  </div>
                </div>
                <div className="bg-[#333] rounded p-2">
                  <div className="flex items-center justify-between">
                    <span className="text-sm">v1.3.0</span>
                    <button className="px-2 py-1 bg-[#3c3c3c] rounded text-xs">
                      <Download className="w-3 h-3 inline mr-1" />
                      Download
                    </button>
                  </div>
                  <div className="text-xs text-[#808080] mt-1">
                    New UDS services, LIN support
                  </div>
                </div>
              </div>
            </div>

            <div className="bg-[#2d2d2d] rounded p-4">
              <h3 className="text-sm font-medium mb-3">OTA Status</h3>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-[#808080]">Progress</span>
                  <span>0%</span>
                </div>
                <div className="h-2 bg-[#333] rounded overflow-hidden">
                  <div className="h-full bg-[#007acc] w-0 transition-all" />
                </div>
                <div className="text-xs text-[#808080] text-center">
                  No update in progress
                </div>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'diagnostics' && (
          <div className="p-2">
            {agentError && (
              <div className="mb-3 p-2 bg-red-900/20 border border-red-800 rounded text-xs text-red-400">
                AI Agent Error: {agentError}
              </div>
            )}

            <div className="mb-3">
              <h3 className="text-sm font-medium mb-2">Firmware Analysis</h3>
              <p className="text-xs text-[#808080] mb-2">
                Paste firmware code to analyze with AI Agent
              </p>
              <textarea
                value={firmwareCode}
                onChange={(e) => setFirmwareCode(e.target.value)}
                className="w-full h-48 px-3 py-2 bg-[#2d2d2d] border border-[#3c3c3c] rounded text-xs font-mono resize-none"
                placeholder="// Paste firmware code here..."
              />
              <button
                onClick={async () => {
                  if (!isConnected || !firmwareCode.trim()) return;
                  setIsAnalyzing(true);
                  try {
                    const result = await analyzeFirmware({
                      code: firmwareCode,
                      language: 'c',
                      targetChip: 'STM32F4',
                    });
                    if (result) {
                      setAnalysisResult({
                        summary: result.summary,
                        issues: result.issues,
                        dependencies: result.dependencies,
                      });
                    }
                  } catch (err) {
                    console.error('Analysis error:', err);
                  } finally {
                    setIsAnalyzing(false);
                  }
                }}
                disabled={!isConnected || isAnalyzing || !firmwareCode.trim()}
                className="mt-2 px-4 py-2 bg-[#0e639c] hover:bg-[#1177bb] disabled:bg-[#3c3c3c] disabled:text-[#808080] rounded text-xs flex items-center gap-2"
              >
                {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileSearch className="w-4 h-4" />}
                {isAnalyzing ? 'Analyzing...' : 'Analyze Firmware'}
              </button>
            </div>

            {analysisResult && (
              <div className="mb-3 bg-[#2d2d2d] rounded p-3 border border-[#3c3c3c]">
                <h4 className="text-xs font-medium mb-2 text-[#569cd6]">Analysis Result</h4>
                <p className="text-xs mb-3">{analysisResult.summary}</p>
                {analysisResult.issues.length > 0 && (
                  <div className="mb-2">
                    <h5 className="text-xs font-medium text-red-400 mb-1">Issues Found:</h5>
                    <ul className="text-xs space-y-1">
                      {analysisResult.issues.map((issue, i) => (
                        <li key={i} className="flex items-start gap-2 text-red-300">
                          <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                          {issue}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {analysisResult.dependencies.length > 0 && (
                  <div>
                    <h5 className="text-xs font-medium text-green-400 mb-1">Dependencies:</h5>
                    <div className="flex flex-wrap gap-1">
                      {analysisResult.dependencies.map((dep, i) => (
                        <span key={i} className="px-2 py-0.5 bg-[#333] rounded text-xs text-[#569cd6]">
                          {dep}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            <div className="bg-[#2d2d2d] rounded p-3 border border-[#3c3c3c]">
              <h3 className="text-sm font-medium mb-2">Debug Firmware Issue</h3>
              <div className="mb-2">
                <label className="text-xs text-[#808080] block mb-1">Error Description</label>
                <input
                  type="text"
                  value={debugError}
                  onChange={(e) => setDebugError(e.target.value)}
                  placeholder="e.g., HardFault on CAN init..."
                  className="w-full px-3 py-2 bg-[#1e1e1e] border border-[#3c3c3c] rounded text-xs"
                />
              </div>
              <button
                onClick={async () => {
                  if (!isConnected || !debugError.trim()) return;
                  setIsDebugging(true);
                  try {
                    const result = await debugFirmware(firmwareCode, debugError);
                    if (result) {
                      setDebugResult(typeof result === 'string' ? result : JSON.stringify(result, null, 2));
                    }
                  } catch (err) {
                    console.error('Debug error:', err);
                    setDebugResult('Error debugging firmware');
                  } finally {
                    setIsDebugging(false);
                  }
                }}
                disabled={!isConnected || isDebugging || !debugError.trim()}
                className="px-4 py-2 bg-[#dcdcaa] hover:bg-[#d4d4d4] text-black disabled:bg-[#3c3c3c] disabled:text-[#808080] rounded text-xs flex items-center gap-2"
              >
                {isDebugging ? <Loader2 className="w-4 h-4 animate-spin" /> : <AlertTriangle className="w-4 h-4" />}
                {isDebugging ? 'Debugging...' : 'Debug Issue'}
              </button>
              {debugResult && (
                <div className="mt-3 p-2 bg-[#1e1e1e] rounded border border-[#3c3c3c]">
                  <pre className="text-xs whitespace-pre-wrap">{debugResult}</pre>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default AutomotivePanel;
