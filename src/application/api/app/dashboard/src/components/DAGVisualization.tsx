import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, Badge } from '@/components/ui';
import { dashboardApi } from '@/api/dashboard';

interface CallNode {
  id: string;
  name: string;
  file?: string;
  children?: CallNode[];
  depth?: number;
  isExpanded?: boolean;
  callCount?: number;
}

interface CallGraphData {
  entry_points: string[];
  functions: Record<string, {
    name: string;
    file: string;
    callees: string[];
    callers: string[];
  }>;
}

interface DAGVisualizationProps {
  data?: CallGraphData;
  maxDepth?: number;
}

export function DAGVisualization({ maxDepth = 3 }: DAGVisualizationProps) {
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set());
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Fetch real call graph data
  const { data, isLoading } = useQuery({
    queryKey: ['dashboard', 'callgraph'],
    queryFn: () => dashboardApi.getCallGraph(undefined, maxDepth),
    staleTime: 60000, // Cache for 1 minute
    retry: 1,
  });

  // Fallback sample data for demo mode
  const sampleData: CallGraphData = useMemo(() => ({
    entry_points: ['main', 'HAL_Init', 'SystemClock_Config'],
    functions: {
      'main': {
        name: 'main',
        file: 'Src/main.c',
        callees: ['HAL_Init', 'SystemClock_Config', 'MX_GPIO_Init', 'MX_USART2_UART_Init', 'Error_Handler'],
        callers: [],
      },
      'HAL_Init': {
        name: 'HAL_Init',
        file: 'Src/main.c',
        callees: ['HAL_MspInit'],
        callers: ['main'],
      },
      'SystemClock_Config': {
        name: 'SystemClock_Config',
        file: 'Src/main.c',
        callees: ['HAL_RCC_OscConfig', 'HAL_RCC_ClockConfig'],
        callers: ['main'],
      },
      'MX_GPIO_Init': {
        name: 'MX_GPIO_Init',
        file: 'Src/gpio.c',
        callees: ['HAL_GPIO_Init'],
        callers: ['main'],
      },
      'MX_USART2_UART_Init': {
        name: 'MX_USART2_UART_Init',
        file: 'Src/usart.c',
        callees: ['HAL_UART_Init'],
        callers: ['main'],
      },
      'HAL_RCC_OscConfig': {
        name: 'HAL_RCC_OscConfig',
        file: 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c',
        callees: [],
        callers: ['SystemClock_Config'],
      },
      'HAL_RCC_ClockConfig': {
        name: 'HAL_RCC_ClockConfig',
        file: 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c',
        callees: ['HAL_RCC_GetClockConfig'],
        callers: ['SystemClock_Config'],
      },
      'HAL_GPIO_Init': {
        name: 'HAL_GPIO_Init',
        file: 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_gpio.c',
        callees: [],
        callers: ['MX_GPIO_Init'],
      },
      'HAL_UART_Init': {
        name: 'HAL_UART_Init',
        file: 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c',
        callees: ['HAL_UART_MspInit'],
        callers: ['MX_USART2_UART_Init'],
      },
      'HAL_MspInit': {
        name: 'HAL_MspInit',
        file: 'Src/main.c',
        callees: [],
        callers: ['HAL_Init'],
      },
      'Error_Handler': {
        name: 'Error_Handler',
        file: 'Src/main.c',
        callees: [],
        callers: ['main'],
      },
      'HAL_RCC_GetClockConfig': {
        name: 'HAL_RCC_GetClockConfig',
        file: 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_rcc.c',
        callees: [],
        callers: ['HAL_RCC_ClockConfig'],
      },
      'HAL_UART_MspInit': {
        name: 'HAL_UART_MspInit',
        file: 'Drivers/STM32F4xx_HAL_Driver/Src/stm32f4xx_hal_uart.c',
        callees: [],
        callers: ['HAL_UART_Init'],
      },
    },
  }), []);

  // Build tree from entry point
  const buildTree = (entryPoint: string, depth = 0, data: CallGraphData | undefined): CallNode | null => {
    if (!data?.functions[entryPoint]) return null;
    if (depth > maxDepth) return null;

    const func = data.functions[entryPoint];
    const node: CallNode = {
      id: entryPoint,
      name: func.name,
      file: func.file,
      depth,
      callCount: func.callers.length + func.callees.length,
      children: func.callees
        .filter(callee => data.functions[callee])
        .map(callee => buildTree(callee, depth + 1, data))
        .filter((n): n is CallNode => n !== null),
    };

    return node;
  };

  const toggleNode = (nodeId: string) => {
    setExpandedNodes(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) {
        next.delete(nodeId);
      } else {
        next.add(nodeId);
      }
      return next;
    });
  };

  const renderNode = (node: CallNode, index: number) => {
    const hasChildren = node.children && node.children.length > 0;
    const isExpanded = expandedNodes.has(node.id);
    const isSelected = selectedNode === node.id;
    const indentPx = (node.depth || 0) * 24;

    return (
      <div key={node.id} className="select-none">
        <div
          className={`
            flex items-center gap-2 py-2 px-3 rounded-lg cursor-pointer
            transition-colors hover:bg-gray-700/50
            ${isSelected ? 'bg-blue-900/40 border border-blue-500' : ''}
          `}
          style={{ marginLeft: `${indentPx}px` }}
          onClick={() => setSelectedNode(node.id)}
        >
          {hasChildren ? (
            <button
              onClick={(e) => {
                e.stopPropagation();
                toggleNode(node.id);
              }}
              className="w-5 h-5 flex items-center justify-center rounded hover:bg-gray-600"
            >
              <span className={`text-xs transition-transform ${isExpanded ? 'rotate-90' : ''}`}>
                ▶
              </span>
            </button>
          ) : (
            <div className="w-5" />
          )}

          <span className={`
            w-6 h-6 rounded flex items-center justify-center text-xs font-mono
            ${hasChildren ? 'bg-blue-600 text-white' : 'bg-gray-600 text-gray-300'}
          `}>
            {hasChildren ? 'F' : 'f'}
          </span>

          <span className="text-sm text-gray-200 font-mono">
            {node.name}
          </span>

          {node.file && (
            <span className="text-xs text-gray-500 truncate max-w-[200px]">
              {node.file.split('/').pop()}
            </span>
          )}

          {node.callCount !== undefined && node.callCount > 0 && (
            <Badge variant="info" className="ml-auto">
              {node.callCount} refs
            </Badge>
          )}

          {hasChildren && (
            <span className="text-xs text-gray-500 ml-2">
              {node.children!.length} callees
            </span>
          )}
        </div>

        {hasChildren && isExpanded && (
          <div className="border-l border-gray-700 ml-2">
            {node.children!.map((child, i) => renderNode(child, i))}
          </div>
        )}
      </div>
    );
  };

  const graphData: CallGraphData | undefined = data?.functions && Object.keys(data.functions).length > 0 ? {
    entry_points: data.entry_points,
    functions: data.functions,
  } : sampleData;

  const entryPoints = graphData?.entry_points || [];

  const initialExpanded = useMemo(() => {
    return new Set(entryPoints);
  }, [entryPoints]);

  const [expanded, setExpanded] = useState<Set<string>>(initialExpanded);

  const handleExpandAll = () => {
    if (graphData) {
      setExpanded(new Set(Object.keys(graphData.functions)));
    }
  };
  const handleCollapseAll = () => setExpanded(new Set(entryPoints));

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
        <span className="ml-3 text-gray-400">Loading call graph...</span>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="text-center py-8 text-red-400">
        <p>Error loading call graph: {loadError}</p>
        <p className="text-sm text-gray-500 mt-2">Using demo data instead.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleExpandAll}
          className="px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
        >
          Expand All
        </button>
        <button
          onClick={handleCollapseAll}
          className="px-3 py-1.5 text-sm bg-gray-700 hover:bg-gray-600 rounded text-gray-300"
        >
          Collapse All
        </button>
        <span className="text-sm text-gray-500 ml-auto">
          {data?.total_functions || Object.keys(graphData?.functions || {}).length} functions | {entryPoints.length} entry points
          {data?.orphaned_count ? ` | ${data.orphaned_count} orphaned` : ''}
        </span>
        {data?.error && (
          <Badge variant="warning">Using demo data</Badge>
        )}
      </div>

      {/* Call Graph Tree */}
      <div className="bg-gray-900 rounded-lg p-4 max-h-[600px] overflow-y-auto">
        <div className="space-y-1">
          {entryPoints.map((entry, i) => {
            const tree = buildTree(entry, 0, graphData);
            if (!tree) return null;
            return renderNode({ ...tree, id: `${entry}-${i}` }, i);
          })}
        </div>
      </div>

      {/* Selected Node Details */}
      {selectedNode && graphData?.functions[selectedNode] && (
        <Card title="Function Details">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-xs text-gray-400 mb-1">Function</p>
              <p className="text-white font-mono">{graphData.functions[selectedNode].name}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">File</p>
              <p className="text-gray-300 text-sm">{graphData.functions[selectedNode].file}</p>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Callers</p>
              <div className="flex flex-wrap gap-1">
                {graphData.functions[selectedNode].callers.length > 0 ? (
                  graphData.functions[selectedNode].callers.map(caller => (
                    <Badge key={caller} variant="default">{caller}</Badge>
                  ))
                ) : (
                  <span className="text-gray-500 text-sm">None (entry point)</span>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs text-gray-400 mb-1">Callees</p>
              <div className="flex flex-wrap gap-1">
                {graphData.functions[selectedNode].callees.length > 0 ? (
                  graphData.functions[selectedNode].callees.map(callee => (
                    <Badge key={callee} variant="info">{callee}</Badge>
                  ))
                ) : (
                  <span className="text-gray-500 text-sm">None (leaf)</span>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
