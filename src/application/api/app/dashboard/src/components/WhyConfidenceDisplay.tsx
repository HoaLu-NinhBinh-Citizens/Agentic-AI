import { useState, useEffect, useCallback } from 'react';
import { Card, Badge } from '@/components/ui';
import { chatApi, type ReasoningChain } from '@/api/dashboard';

// Default sample reasoning for demo mode
const defaultReasoning: ReasoningChain = {
  id: 'default-reasoning',
  question: 'Analyze the confidence of the current analysis',
  answer: 'Default reasoning - enable backend for real analysis',
  confidence: 0.5,
  factors: [],
  sources: [],
  reasoning_steps: [],
  limitations: ['Backend not connected'],
};

interface WhyConfidenceDisplayProps {
  reasoning?: ReasoningChain;
  onDismiss?: () => void;
  enableBackend?: boolean;
  question?: string;
}

// Sample confidence breakdown
const sampleReasoning: ReasoningChain = {
  id: 'reasoning-001',
  question: 'Is it safe to increase UART baudrate to 921600?',
  answer: 'Yes, with proper clock configuration. The STM32F4xx can support 921600 baud with HSE or HSI at 8MHz if oversampling is configured correctly.',
  confidence: 0.87,
  factors: [
    {
      id: 'f1',
      label: 'Clock Source',
      description: 'HSE oscillator is configured at 8MHz',
      impact: 'positive',
      weight: 0.3,
      evidence: [
        'RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE',
        'RCC_OscInitStruct.HSEState = RCC_HSE_ON',
      ],
    },
    {
      id: 'f2',
      label: 'APB Clock',
      description: 'APB1 clock is 42MHz (divides SYSCLK by 2)',
      impact: 'positive',
      weight: 0.25,
      evidence: [
        'APB1 clock: 84MHz / 2 = 42MHz',
        'USART2 is on APB1 bus',
      ],
    },
    {
      id: 'f3',
      label: 'Baudrate Divider',
      description: 'OVER8=1 allows 921600 with acceptable error',
      impact: 'positive',
      weight: 0.2,
      evidence: [
        'USART_CR1_OVER8 = 1 (8x oversampling)',
        'BRR = 42MHz / (8 * 921600) ≈ 5.69',
      ],
    },
    {
      id: 'f4',
      label: 'No DMA Conflict',
      description: 'DMA1 Stream 5/6 not used by other peripherals',
      impact: 'positive',
      weight: 0.15,
      evidence: [
        'DMA1_Stream5 (UART_RX) free',
        'DMA1_Stream6 (UART_TX) free',
      ],
    },
    {
      id: 'f5',
      label: 'Limited Testing',
      description: 'Only tested on EngineCar board, not RemoteControl',
      impact: 'negative',
      weight: -0.1,
      evidence: [
        'Test logs show only 1 board tested',
        'RemoteControl uses different MCU variant',
      ],
    },
  ],
  sources: [
    {
      file: 'Src/main.c',
      line: 145,
      snippet: 'HAL_UART_Transmit(&huart2, buffer, len, 1000);',
      relevance: 'high',
    },
    {
      file: 'Src/clock.c',
      line: 89,
      snippet: 'RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;',
      relevance: 'high',
    },
    {
      file: 'Src/usart.c',
      line: 23,
      snippet: 'huart2.Init.BaudRate = 115200;',
      relevance: 'medium',
    },
  ],
  reasoning_steps: [
    {
      step: 1,
      description: 'Check clock configuration for UART peripheral',
      conclusion: 'USART2 is on APB1 bus with 42MHz clock',
      confidence_delta: 0.15,
    },
    {
      step: 2,
      description: 'Calculate baudrate divider for 921600',
      conclusion: 'BRR = 5.69 with OVER8=1, error < 2%',
      confidence_delta: 0.2,
    },
    {
      step: 3,
      description: 'Verify no DMA conflicts with existing streams',
      conclusion: 'DMA streams 5/6 available and not assigned',
      confidence_delta: 0.1,
    },
    {
      step: 4,
      description: 'Check hardware constraints (EMI, cable length)',
      conclusion: 'Short traces on board, but external cable may need shielding',
      confidence_delta: -0.05,
    },
    {
      step: 5,
      description: 'Review similar implementations in codebase',
      conclusion: 'Found 2 other UART instances at same baudrate',
      confidence_delta: 0.12,
    },
  ],
  limitations: [
    'Only tested on EngineCar (STM32F407VG)',
    'Not validated with long cable runs (>1m)',
    'EMI testing not performed',
  ],
};

export function WhyConfidenceDisplay({ 
  reasoning,
  onDismiss,
  enableBackend = true,
  question: initialQuestion,
}: WhyConfidenceDisplayProps) {
  const [activeTab, setActiveTab] = useState<'factors' | 'steps' | 'sources'>('factors');
  const [expandedFactors, setExpandedFactors] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [currentReasoning, setCurrentReasoning] = useState<ReasoningChain>(
    reasoning ?? defaultReasoning
  );

  // Fetch reasoning from backend when question changes
  useEffect(() => {
    if (!enableBackend || !initialQuestion) return;

    const fetchReasoning = async () => {
      setIsLoading(true);
      setBackendError(null);

      try {
        const result = await chatApi.analyzeReasoning(initialQuestion);
        setCurrentReasoning(result);
      } catch (error) {
        setBackendError('Could not fetch reasoning from backend');
        // Fall back to default
        if (!reasoning) {
          setCurrentReasoning({
            ...defaultReasoning,
            question: initialQuestion,
          });
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchReasoning();
  }, [initialQuestion, enableBackend]);

  // Update when reasoning prop changes
  useEffect(() => {
    if (reasoning) {
      setCurrentReasoning(reasoning);
    }
  }, [reasoning]);

  const toggleFactor = (id: string) => {
    setExpandedFactors(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const getConfidenceColor = (confidence: number) => {
    if (confidence >= 0.9) return 'text-green-400';
    if (confidence >= 0.7) return 'text-yellow-400';
    if (confidence >= 0.5) return 'text-orange-400';
    return 'text-red-400';
  };

  const getConfidenceBgColor = (confidence: number) => {
    if (confidence >= 0.9) return 'bg-green-500';
    if (confidence >= 0.7) return 'bg-yellow-500';
    if (confidence >= 0.5) return 'bg-orange-500';
    return 'bg-red-500';
  };

  const getImpactIcon = (impact: ConfidenceFactor['impact']) => {
    switch (impact) {
      case 'positive':
        return <span className="text-green-400">+</span>;
      case 'negative':
        return <span className="text-red-400">-</span>;
      case 'neutral':
        return <span className="text-gray-400">~</span>;
    }
  };

  const totalPositive = currentReasoning.factors
    .filter(f => f.impact === 'positive')
    .reduce((sum, f) => sum + f.weight, 0);

  const totalNegative = currentReasoning.factors
    .filter(f => f.impact === 'negative')
    .reduce((sum, f) => sum + Math.abs(f.weight), 0);

  return (
    <div className="space-y-4">
      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <div className="flex items-center gap-3">
            <div className="w-4 h-4 rounded-full bg-blue-500 animate-pulse" />
            <span className="text-gray-400">Analyzing reasoning...</span>
          </div>
        </div>
      )}

      {/* Question */}
      <Card>
        <div className="flex items-start gap-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-blue-600 flex items-center justify-center">
            <span className="text-white text-lg">?</span>
          </div>
          <div className="flex-1">
            <p className="text-sm text-gray-400 mb-1">Question</p>
            <p className="text-white font-medium">{currentReasoning.question}</p>
            {backendError && (
              <p className="text-xs text-yellow-400 mt-1">⚠ {backendError} - showing demo data</p>
            )}
          </div>
        </div>
      </Card>

      {/* Confidence Meter */}
      <Card>
        <div className="flex items-center gap-6 mb-4">
          <div className="flex-shrink-0">
            <div className="relative w-24 h-24">
              <svg className="w-24 h-24 transform -rotate-90">
                <circle
                  cx="48"
                  cy="48"
                  r="40"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  className="text-gray-700"
                />
                <circle
                  cx="48"
                  cy="48"
                  r="40"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${currentReasoning.confidence * 251.2} 251.2`}
                  className={getConfidenceColor(currentReasoning.confidence)}
                  strokeLinecap="round"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className={`text-2xl font-bold ${getConfidenceColor(currentReasoning.confidence)}`}>
                  {Math.round(currentReasoning.confidence * 100)}
                </span>
              </div>
            </div>
          </div>
          <div className="flex-1">
            <p className="text-sm text-gray-400 mb-2">Confidence Score</p>
            <p className="text-white text-lg mb-1">{currentReasoning.answer}</p>
            <div className="flex items-center gap-4 mt-3">
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span className="text-sm text-gray-400">+{totalPositive.toFixed(2)} positive</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-red-500" />
                <span className="text-sm text-gray-400">-{totalNegative.toFixed(2)} negative</span>
              </div>
            </div>
          </div>
        </div>

        {/* Confidence Bar */}
        <div className="w-full h-3 bg-gray-700 rounded-full overflow-hidden flex">
          {currentReasoning.factors
            .sort((a, b) => b.weight - a.weight)
            .map(factor => (
              <div
                key={factor.id}
                className={`
                  ${factor.impact === 'positive' ? 'bg-green-500' : ''}
                  ${factor.impact === 'negative' ? 'bg-red-500' : ''}
                  ${factor.impact === 'neutral' ? 'bg-gray-500' : ''}
                `}
                style={{ width: `${Math.abs(factor.weight) * 100}%` }}
                title={factor.label}
              />
            ))}
        </div>
      </Card>

      {/* Tabs */}
      <Card>
        <div className="flex border-b border-gray-700 mb-4">
          {(['factors', 'steps', 'sources'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`
                px-4 py-2 text-sm font-medium capitalize transition-colors
                ${activeTab === tab
                  ? 'text-blue-400 border-b-2 border-blue-400'
                  : 'text-gray-400 hover:text-white'
                }
              `}
            >
              {tab}
              {tab === 'factors' && (
                <Badge variant="default" className="ml-2">{currentReasoning.factors.length}</Badge>
              )}
              {tab === 'steps' && (
                <Badge variant="default" className="ml-2">{currentReasoning.reasoning_steps.length}</Badge>
              )}
              {tab === 'sources' && (
                <Badge variant="default" className="ml-2">{currentReasoning.sources.length}</Badge>
              )}
            </button>
          ))}
        </div>

        {/* Factors Tab */}
        {activeTab === 'factors' && (
          <div className="space-y-3">
            {currentReasoning.factors
              .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
              .map(factor => (
                <div
                  key={factor.id}
                  className={`
                    border rounded-lg overflow-hidden
                    ${factor.impact === 'positive' ? 'border-green-800/50' : ''}
                    ${factor.impact === 'negative' ? 'border-red-800/50' : ''}
                    ${factor.impact === 'neutral' ? 'border-gray-700' : ''}
                  `}
                >
                  <button
                    onClick={() => toggleFactor(factor.id)}
                    className="w-full flex items-center gap-3 p-4 hover:bg-gray-800/50 transition-colors"
                  >
                    <div className={`
                      w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold
                      ${factor.impact === 'positive' ? 'bg-green-900/50 text-green-400' : ''}
                      ${factor.impact === 'negative' ? 'bg-red-900/50 text-red-400' : ''}
                      ${factor.impact === 'neutral' ? 'bg-gray-700 text-gray-400' : ''}
                    `}>
                      {getImpactIcon(factor.impact)}
                    </div>
                    <div className="flex-1 text-left">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-white">{factor.label}</span>
                        <Badge variant={factor.impact === 'positive' ? 'success' : factor.impact === 'negative' ? 'error' : 'default'}>
                          {factor.weight > 0 ? '+' : ''}{factor.weight.toFixed(2)}
                        </Badge>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">{factor.description}</p>
                    </div>
                    <span className={`text-xs ${expandedFactors.has(factor.id) ? 'rotate-180' : ''}`}>
                      ▼
                    </span>
                  </button>

                  {expandedFactors.has(factor.id) && factor.evidence && (
                    <div className="px-4 pb-4 bg-gray-900/50">
                      <p className="text-xs text-gray-500 mb-2">Evidence:</p>
                      <div className="space-y-2">
                        {factor.evidence.map((e, i) => (
                          <code key={i} className="block bg-gray-800 text-gray-300 text-xs p-2 rounded overflow-x-auto">
                            {e}
                          </code>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
          </div>
        )}

        {/* Steps Tab */}
        {activeTab === 'steps' && (
          <div className="space-y-4">
            {currentReasoning.reasoning_steps.map((step, index) => (
              <div key={step.step} className="flex gap-4">
                <div className="flex flex-col items-center">
                  <div className="w-8 h-8 rounded-full bg-blue-600 flex items-center justify-center text-sm font-bold text-white">
                    {step.step}
                  </div>
                  {index < currentReasoning.reasoning_steps.length - 1 && (
                    <div className="w-0.5 flex-1 bg-gray-700 my-2" />
                  )}
                </div>
                <div className="flex-1 pb-4">
                  <p className="text-sm text-white">{step.description}</p>
                  <p className="text-sm text-gray-400 mt-1">{step.conclusion}</p>
                  <div className="flex items-center gap-2 mt-2">
                    <Badge
                      variant={step.confidence_delta >= 0 ? 'success' : 'error'}
                      className="text-xs"
                    >
                      {step.confidence_delta >= 0 ? '+' : ''}{step.confidence_delta.toFixed(2)}
                    </Badge>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Sources Tab */}
        {activeTab === 'sources' && (
          <div className="space-y-3">
            {currentReasoning.sources.map((source, index) => (
              <div
                key={index}
                className={`
                  border rounded-lg p-4
                  ${source.relevance === 'high' ? 'border-green-800/50 bg-green-900/20' : ''}
                  ${source.relevance === 'medium' ? 'border-yellow-800/50 bg-yellow-900/20' : ''}
                  ${source.relevance === 'low' ? 'border-gray-700' : ''}
                `}
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-mono text-sm">
                      {source.file.split('/').pop()}
                    </span>
                    {source.line && (
                      <span className="text-gray-500 text-xs">:{source.line}</span>
                    )}
                  </div>
                  <Badge 
                    variant={
                      source.relevance === 'high' ? 'success' : 
                      source.relevance === 'medium' ? 'warning' : 'default'
                    }
                    className="text-xs"
                  >
                    {source.relevance}
                  </Badge>
                </div>
                {source.snippet && (
                  <code className="block bg-gray-800 text-gray-300 text-xs p-3 rounded overflow-x-auto">
                    {source.snippet}
                  </code>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Limitations */}
      {currentReasoning.limitations && currentReasoning.limitations.length > 0 && (
        <Card title="Known Limitations">
          <div className="space-y-2">
            {reasoning.limitations.map((limitation, i) => (
              <div key={i} className="flex items-start gap-3 p-3 bg-yellow-900/20 border border-yellow-800/50 rounded-lg">
                <span className="text-yellow-400 mt-0.5">⚠</span>
                <p className="text-sm text-yellow-200">{limitation}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
