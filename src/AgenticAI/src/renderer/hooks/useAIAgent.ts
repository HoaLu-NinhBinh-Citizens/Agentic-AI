import { useState, useCallback, useEffect, useRef } from 'react';
import type {
  AIAgentStatus,
  MCPTool,
  MCPToolResult,
  MCPResource,
  MCPPrompt,
  HardwareValidationRequest,
  HardwareValidationResult,
  FirmwareAnalysisRequest,
  FirmwareAnalysisResult,
  AIAgentEvent,
} from '../../shared/types';

export interface UseAIAgentOptions {
  autoConnect?: boolean;
  workspace?: string;
}

export interface UseAIAgentReturn {
  // Connection state
  status: AIAgentStatus;
  isConnected: boolean;
  isConnecting: boolean;
  error: string | null;

  // Actions
  connect: (workspace?: string) => Promise<void>;
  disconnect: () => Promise<void>;

  // Tools
  tools: MCPTool[];
  listTools: () => Promise<void>;
  callTool: (name: string, args?: Record<string, unknown>) => Promise<MCPToolResult | null>;

  // Hardware tools
  validateHardware: (config: HardwareValidationRequest) => Promise<HardwareValidationResult | null>;
  planHardwareInit: (chip: string, peripheral: string) => Promise<unknown>;
  reasonAboutHardware: (question: string, context?: Record<string, unknown>) => Promise<unknown>;

  // Firmware tools
  analyzeFirmware: (params: FirmwareAnalysisRequest) => Promise<FirmwareAnalysisResult | null>;
  debugFirmware: (code: string, error: string) => Promise<unknown>;
  generateCode: (spec: string, context?: string) => Promise<unknown>;

  // Knowledge tools
  queryKnowledge: (query: string, topK?: number) => Promise<unknown>;
  crossValidate: (params: Record<string, unknown>) => Promise<unknown>;

  // Resources
  resources: MCPResource[];
  listResources: () => Promise<void>;
  readResource: (uri: string) => Promise<unknown>;

  // Prompts
  prompts: MCPPrompt[];
  listPrompts: () => Promise<void>;
  getPrompt: (name: string, args?: Record<string, unknown>) => Promise<unknown>;

  // Events
  subscribe: (eventName: string, channel: string) => Promise<void>;
  unsubscribe: (eventName: string) => Promise<void>;
  onEvent: (channel: string, callback: (event: AIAgentEvent) => void) => void;
}

export function useAIAgent(options: UseAIAgentOptions = {}): UseAIAgentReturn {
  const { autoConnect = false, workspace } = options;

  // State
  const [status, setStatus] = useState<AIAgentStatus>({
    connected: false,
    reconnectAttempts: 0,
    pendingRequests: 0,
  });
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [resources, setResources] = useState<MCPResource[]>([]);
  const [prompts, setPrompts] = useState<MCPPrompt[]>([]);

  // Refs
  const eventCallbacks = useRef<Map<string, Set<(event: AIAgentEvent) => void>>>(new Map());

  // Check if API is available
  const isAvailable = useCallback((): boolean => {
    return !!(window.electronAPI?.aiAgent);
  }, []);

  // Get AI Agent API with proper typing
  const getAIAgent = useCallback((): AIAgentAPI | null => {
    return window.electronAPI?.aiAgent ?? null;
  }, []);

  // Connection
  const connect = useCallback(async (workspacePath?: string) => {
    const agent = getAIAgent();
    if (!agent) {
      setError('AI Agent not available');
      return;
    }

    setIsConnecting(true);
    setError(null);

    try {
      const result = await agent.connect({
        workspace: workspacePath || workspace,
      });

      if (result.success) {
        const newStatus = await agent.status();
        setStatus(newStatus);
        // Auto-fetch tools on connect
        listTools();
        listResources();
        listPrompts();
      } else {
        setError(result.error || 'Connection failed');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Connection failed');
    } finally {
      setIsConnecting(false);
    }
  }, [getAIAgent, workspace]);

  const disconnect = useCallback(async () => {
    const agent = getAIAgent();
    if (!agent) return;

    try {
      await agent.disconnect();
      setStatus({ connected: false, reconnectAttempts: 0, pendingRequests: 0 });
      setTools([]);
      setResources([]);
      setPrompts([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Disconnect failed');
    }
  }, [getAIAgent]);

  // Polling status
  useEffect(() => {
    if (!status.connected) return;

    const interval = setInterval(async () => {
      try {
        const agent = getAIAgent();
        if (agent) {
          const newStatus = await agent.status();
          setStatus(newStatus);
        }
      } catch {
        // Ignore errors
      }
    }, 5000);

    return () => clearInterval(interval);
  }, [status.connected, getAIAgent]);

  // Tools
  const listTools = useCallback(async () => {
    const agent = getAIAgent();
    if (!agent) return;

    try {
      const result = await agent.listTools();
      if (result.success && result.tools) {
        setTools(result.tools);
      }
    } catch (err) {
      console.error('List tools error:', err);
    }
  }, [getAIAgent]);

  const callTool = useCallback(async (name: string, args?: Record<string, unknown>): Promise<MCPToolResult | null> => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.callTool(name, args);
      if (result.success && result.result) {
        return result.result;
      } else if (!result.success) {
        setError(result.error || 'Tool call failed');
      }
      return result.result || null;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Tool call failed');
      return null;
    }
  }, [getAIAgent]);

  // Hardware tools
  const validateHardware = useCallback(async (config: HardwareValidationRequest): Promise<HardwareValidationResult | null> => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.hardware.validate(config);
      return result.result || null;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed');
      return null;
    }
  }, [getAIAgent]);

  const planHardwareInit = useCallback(async (chip: string, peripheral: string) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.hardware.planInit({ chip, peripheral });
      return result.result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Plan failed');
      return null;
    }
  }, [getAIAgent]);

  const reasonAboutHardware = useCallback(async (question: string, context?: Record<string, unknown>) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.hardware.reason({ question, context });
      return result.result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reasoning failed');
      return null;
    }
  }, [getAIAgent]);

  // Firmware tools
  const analyzeFirmware = useCallback(async (params: FirmwareAnalysisRequest): Promise<FirmwareAnalysisResult | null> => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.firmware.analyze(params);
      return result.result || null;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed');
      return null;
    }
  }, [getAIAgent]);

  const debugFirmware = useCallback(async (code: string, error: string) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.firmware.debug({ code, error });
      return result.result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Debug failed');
      return null;
    }
  }, [getAIAgent]);

  const generateCode = useCallback(async (spec: string, context?: string) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.firmware.generateCode({ spec, context });
      return result.result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Code generation failed');
      return null;
    }
  }, [getAIAgent]);

  // Knowledge tools
  const queryKnowledge = useCallback(async (query: string, topK?: number) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.knowledge.query({ query, topK });
      return result.result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Query failed');
      return null;
    }
  }, [getAIAgent]);

  const crossValidate = useCallback(async (params: Record<string, unknown>) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.knowledge.crossValidate(params);
      return result.result;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Validation failed');
      return null;
    }
  }, [getAIAgent]);

  // Resources
  const listResources = useCallback(async () => {
    const agent = getAIAgent();
    if (!agent) return;

    try {
      const result = await agent.listResources();
      if (result.success && result.resources) {
        setResources(result.resources);
      }
    } catch (err) {
      console.error('List resources error:', err);
    }
  }, [getAIAgent]);

  const readResource = useCallback(async (uri: string) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.readResource(uri);
      return result.resource;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Read resource failed');
      return null;
    }
  }, [getAIAgent]);

  // Prompts
  const listPrompts = useCallback(async () => {
    const agent = getAIAgent();
    if (!agent) return;

    try {
      const result = await agent.listPrompts();
      if (result.success && result.prompts) {
        setPrompts(result.prompts);
      }
    } catch (err) {
      console.error('List prompts error:', err);
    }
  }, [getAIAgent]);

  const getPrompt = useCallback(async (name: string, args?: Record<string, unknown>) => {
    const agent = getAIAgent();
    if (!agent) return null;

    try {
      const result = await agent.getPrompt(name, args);
      return result.prompt;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Get prompt failed');
      return null;
    }
  }, [getAIAgent]);

  // Events
  const subscribe = useCallback(async (eventName: string, channel: string) => {
    const agent = getAIAgent();
    if (!agent) return;

    try {
      await agent.subscribe(eventName, channel);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Subscribe failed');
    }
  }, [getAIAgent]);

  const unsubscribe = useCallback(async (eventName: string) => {
    const agent = getAIAgent();
    if (!agent) return;

    try {
      await agent.unsubscribe(eventName);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unsubscribe failed');
    }
  }, [getAIAgent]);

  const onEvent = useCallback((channel: string, callback: (event: AIAgentEvent) => void) => {
    const agent = getAIAgent();
    if (!agent) return;

    if (!eventCallbacks.current.has(channel)) {
      eventCallbacks.current.set(channel, new Set());
    }
    eventCallbacks.current.get(channel)?.add(callback);

    agent.onEvent(channel, callback);
  }, [getAIAgent]);

  // Auto-connect
  useEffect(() => {
    if (autoConnect && isAvailable()) {
      connect(workspace);
    }
  }, [autoConnect, isAvailable, connect, workspace]);

  return {
    status,
    isConnected: status.connected,
    isConnecting,
    error,
    connect,
    disconnect,
    tools,
    listTools,
    callTool,
    validateHardware,
    planHardwareInit,
    reasonAboutHardware,
    analyzeFirmware,
    debugFirmware,
    generateCode,
    queryKnowledge,
    crossValidate,
    resources,
    listResources,
    readResource,
    prompts,
    listPrompts,
    getPrompt,
    subscribe,
    unsubscribe,
    onEvent,
  };
}

export default useAIAgent;
