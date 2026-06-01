import React, { useState, useCallback, useEffect } from 'react';
import {
  Cpu,
  HardDrive,
  Zap,
  AlertCircle,
  CheckCircle,
  XCircle,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Settings,
  Database,
  Loader2,
} from 'lucide-react';
import { useAIAgent } from '../hooks/useAIAgent';

interface ChipInfo {
  name: string;
  vendor: string;
  family: string;
  core: string;
  frequency: string;
  flash: string;
  ram: string;
}

interface Peripheral {
  name: string;
  baseAddress: string;
  interrupts: string[];
  clockDomain: string;
  status: 'enabled' | 'disabled' | 'unknown';
  description?: string;
}

interface Register {
  name: string;
  address: string;
  description: string;
}

interface ValidationResult {
  valid: boolean;
  issues: string[];
  warnings: string[];
  suggestions: string[];
}

export const HardwarePanel: React.FC = () => {
  const {
    isConnected,
    isConnecting,
    connect,
    disconnect,
    validateHardware,
    planHardwareInit,
    reasonAboutHardware,
    queryKnowledge,
    tools,
    error: agentError,
  } = useAIAgent();

  const [selectedChip, setSelectedChip] = useState<ChipInfo | null>(null);
  const [peripherals, setPeripherals] = useState<Peripheral[]>([]);
  const [expandedPeripheral, setExpandedPeripheral] = useState<string | null>(null);
  const [selectedRegister, setSelectedRegister] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'peripherals' | 'interrupts' | 'clocks' | 'knowledge'>('peripherals');
  const [validationResult, setValidationResult] = useState<ValidationResult | null>(null);
  const [isValidating, setIsValidating] = useState(false);
  const [initPlan, setInitPlan] = useState<{ sequence: string[]; chip: string; peripheral: string } | null>(null);
  const [isPlanning, setIsPlanning] = useState(false);
  const [knowledgeQuery, setKnowledgeQuery] = useState('');
  const [knowledgeResults, setKnowledgeResults] = useState<string[]>([]);
  const [isQuerying, setIsQuerying] = useState(false);

  // Chip definitions with real STM32F4 data
  const chipDefinitions: Record<string, ChipInfo> = {
    'STM32F407VG': {
      name: 'STM32F407VG',
      vendor: 'STMicroelectronics',
      family: 'STM32F4',
      core: 'ARM Cortex-M4 with FPU',
      frequency: '168 MHz',
      flash: '1 MB',
      ram: '192 KB',
    },
    'STM32F103C8': {
      name: 'STM32F103C8',
      vendor: 'STMicroelectronics',
      family: 'STM32F1',
      core: 'ARM Cortex-M3',
      frequency: '72 MHz',
      flash: '64 KB',
      ram: '20 KB',
    },
    'STM32L476RG': {
      name: 'STM32L476RG',
      vendor: 'STMicroelectronics',
      family: 'STM32L4',
      core: 'ARM Cortex-M4 with FPU',
      frequency: '80 MHz',
      flash: '1 MB',
      ram: '128 KB',
    },
    'ESP32': {
      name: 'ESP32',
      vendor: 'Espressif',
      family: 'ESP32',
      core: 'Xtensa LX6 Dual-Core',
      frequency: '240 MHz',
      flash: '4 MB',
      ram: '520 KB',
    },
    'nRF52840': {
      name: 'nRF52840',
      vendor: 'Nordic Semiconductor',
      family: 'nRF52',
      core: 'ARM Cortex-M4 with FPU',
      frequency: '64 MHz',
      flash: '1 MB',
      ram: '256 KB',
    },
    'RP2040': {
      name: 'RP2040',
      vendor: 'Raspberry Pi',
      family: 'RP2',
      core: 'ARM Cortex-M0+ Dual-Core',
      frequency: '133 MHz',
      flash: 'External',
      ram: '264 KB',
    },
  };

  // Peripheral definitions for STM32F4
  const stm32f4Peripherals: Peripheral[] = [
    { name: 'GPIOA', baseAddress: '0x4002 0000', interrupts: ['EXTI0', 'EXTI1', 'EXTI2', 'EXTI3'], clockDomain: 'APB2', status: 'enabled', description: 'General Purpose I/O Port A' },
    { name: 'GPIOB', baseAddress: '0x4002 0400', interrupts: ['EXTI0', 'EXTI1', 'EXTI2', 'EXTI3'], clockDomain: 'APB2', status: 'enabled', description: 'General Purpose I/O Port B' },
    { name: 'GPIOC', baseAddress: '0x4002 0800', interrupts: ['EXTI0', 'EXTI1', 'EXTI2', 'EXTI3'], clockDomain: 'APB2', status: 'enabled', description: 'General Purpose I/O Port C' },
    { name: 'USART1', baseAddress: '0x4001 3800', interrupts: ['USART1'], clockDomain: 'APB2', status: 'enabled', description: 'Universal Sync/Async Rx/Tx' },
    { name: 'USART2', baseAddress: '0x4000 4400', interrupts: ['USART2'], clockDomain: 'APB1', status: 'enabled', description: 'Universal Sync/Async Rx/Tx 2' },
    { name: 'SPI1', baseAddress: '0x4001 3000', interrupts: ['SPI1'], clockDomain: 'APB2', status: 'enabled', description: 'Serial Peripheral Interface 1' },
    { name: 'SPI2', baseAddress: '0x4000 3800', interrupts: ['SPI2'], clockDomain: 'APB1', status: 'enabled', description: 'Serial Peripheral Interface 2' },
    { name: 'I2C1', baseAddress: '0x4000 5400', interrupts: ['I2C1_EV', 'I2C1_ER'], clockDomain: 'APB1', status: 'disabled', description: 'Inter-Integrated Circuit 1' },
    { name: 'I2C2', baseAddress: '0x4000 5800', interrupts: ['I2C2_EV', 'I2C2_ER'], clockDomain: 'APB1', status: 'disabled', description: 'Inter-Integrated Circuit 2' },
    { name: 'DMA1', baseAddress: '0x4002 6000', interrupts: ['DMA1_Stream0', 'DMA1_Stream1', 'DMA1_Stream2', 'DMA1_Stream3'], clockDomain: 'AHB1', status: 'enabled', description: 'Direct Memory Access 1' },
    { name: 'DMA2', baseAddress: '0x4002 6400', interrupts: ['DMA2_Stream0', 'DMA2_Stream1', 'DMA2_Stream2', 'DMA2_Stream3'], clockDomain: 'AHB1', status: 'enabled', description: 'Direct Memory Access 2' },
    { name: 'TIM2', baseAddress: '0x4000 0000', interrupts: ['TIM2_IRQ'], clockDomain: 'APB1', status: 'enabled', description: 'General Purpose Timer 2' },
    { name: 'TIM3', baseAddress: '0x4000 0400', interrupts: ['TIM3_IRQ'], clockDomain: 'APB1', status: 'enabled', description: 'General Purpose Timer 3' },
    { name: 'TIM4', baseAddress: '0x4000 0800', interrupts: ['TIM4_IRQ'], clockDomain: 'APB1', status: 'enabled', description: 'General Purpose Timer 4' },
    { name: 'TIM5', baseAddress: '0x4000 0C00', interrupts: ['TIM5_IRQ'], clockDomain: 'APB1', status: 'enabled', description: 'General Purpose Timer 5' },
    { name: 'ADC1', baseAddress: '0x4001 2400', interrupts: ['ADC1_2'], clockDomain: 'APB2', status: 'enabled', description: 'Analog-to-Digital Converter 1' },
    { name: 'ADC2', baseAddress: '0x4001 2800', interrupts: ['ADC1_2'], clockDomain: 'APB2', status: 'enabled', description: 'Analog-to-Digital Converter 2' },
    { name: 'CAN1', baseAddress: '0x4000 6400', interrupts: ['CAN1_TX', 'CAN1_RX0', 'CAN1_RX1'], clockDomain: 'APB1', status: 'disabled', description: 'Controller Area Network 1' },
    { name: 'CAN2', baseAddress: '0x4000 6800', interrupts: ['CAN2_TX', 'CAN2_RX0', 'CAN2_RX1'], clockDomain: 'APB1', status: 'disabled', description: 'Controller Area Network 2' },
    { name: 'RNG', baseAddress: '0x5006 0800', interrupts: ['RNG'], clockDomain: 'AHB2', status: 'enabled', description: 'Random Number Generator' },
  ];

  const handleValidate = useCallback(async () => {
    if (!isConnected) return;

    setIsValidating(true);
    try {
      const result = await validateHardware({
        chip: selectedChip?.name || 'STM32F4',
        peripherals: peripherals.filter(p => p.status === 'enabled').map(p => p.name),
      });

      if (result) {
        setValidationResult(result);
      }
    } catch (error) {
      console.error('Validation error:', error);
    } finally {
      setIsValidating(false);
    }
  }, [isConnected, selectedChip, peripherals, validateHardware]);

  const handlePlanInit = useCallback(async (peripheral: string) => {
    if (!isConnected) return;

    setIsPlanning(true);
    try {
      const result = await planHardwareInit(selectedChip?.name || 'STM32F4', peripheral);
      console.log('Init plan:', result);
      if (result && typeof result === 'object' && 'sequence' in result) {
        setInitPlan(result as { sequence: string[]; chip: string; peripheral: string });
      }
    } catch (error) {
      console.error('Plan error:', error);
    } finally {
      setIsPlanning(false);
    }
  }, [isConnected, selectedChip, planHardwareInit]);

  const handleKnowledgeQuery = useCallback(async () => {
    if (!isConnected || !knowledgeQuery.trim()) return;

    setIsQuerying(true);
    try {
      const result = await queryKnowledge(knowledgeQuery);
      if (result && typeof result === 'object' && 'results' in result) {
        setKnowledgeResults((result as { results: string[] }).results);
      } else {
        setKnowledgeResults([JSON.stringify(result, null, 2)]);
      }
    } catch (error) {
      console.error('Knowledge query error:', error);
      setKnowledgeResults(['Error querying knowledge base']);
    } finally {
      setIsQuerying(false);
    }
  }, [isConnected, knowledgeQuery, queryKnowledge]);

  // Set peripherals based on selected chip
  useEffect(() => {
    if (selectedChip?.family === 'STM32F4' || selectedChip?.name.startsWith('STM32F4')) {
      setPeripherals(stm32f4Peripherals);
    } else {
      setPeripherals(stm32f4Peripherals.slice(0, 8)); // Show subset for other chips
    }
  }, [selectedChip]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'enabled':
        return <CheckCircle className="w-4 h-4 text-green-500" />;
      case 'disabled':
        return <XCircle className="w-4 h-4 text-gray-400" />;
      default:
        return <AlertCircle className="w-4 h-4 text-yellow-500" />;
    }
  };

  return (
    <div className="hardware-panel h-full flex flex-col bg-[#1e1e1e] text-[#cccccc]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#3c3c3c]">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4" />
          <span className="font-medium">Hardware</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => isConnected ? disconnect() : connect()}
            disabled={isConnecting}
            className={`px-3 py-1 rounded text-xs ${
              isConnected
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {isConnecting ? 'Connecting...' : isConnected ? 'Disconnect' : 'Connect AI'}
          </button>
        </div>
      </div>

      {/* Connection Status */}
      <div className={`px-4 py-2 text-xs border-b ${
        isConnected
          ? 'bg-green-900/30 border-green-800 text-green-400'
          : 'bg-yellow-900/30 border-yellow-800 text-yellow-400'
      }`}>
        <div className="flex items-center gap-2">
          {isConnected ? (
            <>
              <CheckCircle className="w-3 h-3" />
              <span>AI Agent Connected ({tools.length} tools available)</span>
            </>
          ) : (
            <>
              <AlertCircle className="w-3 h-3" />
              <span>AI Agent Disconnected - Click Connect to enable hardware intelligence</span>
            </>
          )}
        </div>
      </div>

      {/* Chip Selector */}
      <div className="px-4 py-3 border-b border-[#3c3c3c]">
        <label className="text-xs text-[#808080] mb-1 block">Target Chip</label>
        <select
          value={selectedChip?.name || 'STM32F407VG'}
          onChange={(e) => setSelectedChip({
            name: e.target.value,
            vendor: 'STMicroelectronics',
            family: 'STM32F4',
            core: 'ARM Cortex-M4',
            frequency: '168 MHz',
            flash: '1 MB',
            ram: '192 KB',
          })}
          className="w-full px-3 py-2 bg-[#2d2d2d] border border-[#3c3c3c] rounded text-sm"
        >
          <option value="STM32F407VG">STM32F407VG</option>
          <option value="STM32F103C8">STM32F103C8 (Blue Pill)</option>
          <option value="STM32L476RG">STM32L476RG</option>
          <option value="ESP32">ESP32</option>
          <option value="nRF52840">nRF52840</option>
          <option value="RP2040">RP2040</option>
        </select>

        {/* Chip Info */}
        {selectedChip && (
          <div className="mt-3 p-3 bg-[#2d2d2d] rounded border border-[#3c3c3c]">
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div>
                <span className="text-[#808080]">Vendor:</span>
                <span className="ml-2">{selectedChip.vendor}</span>
              </div>
              <div>
                <span className="text-[#808080]">Core:</span>
                <span className="ml-2">{selectedChip.core}</span>
              </div>
              <div>
                <span className="text-[#808080]">Clock:</span>
                <span className="ml-2">{selectedChip.frequency}</span>
              </div>
              <div>
                <span className="text-[#808080]">Flash:</span>
                <span className="ml-2">{selectedChip.flash}</span>
              </div>
              <div className="col-span-2">
                <span className="text-[#808080]">RAM:</span>
                <span className="ml-2">{selectedChip.ram}</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-[#3c3c3c]">
        {(['peripherals', 'interrupts', 'clocks', 'knowledge'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`flex-1 px-4 py-2 text-xs font-medium transition-colors ${
              activeTab === tab
                ? 'bg-[#2d2d2d] text-white border-b-2 border-[#007acc]'
                : 'text-[#808080] hover:text-[#cccccc]'
            }`}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {activeTab === 'peripherals' && (
          <div className="p-2">
            {/* Validate Button */}
            <button
              onClick={handleValidate}
              disabled={!isConnected || isValidating}
              className="w-full mb-3 px-3 py-2 bg-[#0e639c] hover:bg-[#1177bb] disabled:bg-[#3c3c3c] disabled:text-[#808080] rounded text-sm flex items-center justify-center gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${isValidating ? 'animate-spin' : ''}`} />
              {isValidating ? 'Validating...' : 'Validate Configuration'}
            </button>

            {/* Validation Result */}
            {validationResult && (
              <div className={`mb-3 p-3 rounded border ${
                validationResult.valid
                  ? 'bg-green-900/20 border-green-800'
                  : 'bg-red-900/20 border-red-800'
              }`}>
                <div className="flex items-center gap-2 text-sm font-medium mb-2">
                  {validationResult.valid ? (
                    <>
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      <span className="text-green-400">Configuration Valid</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-4 h-4 text-red-500" />
                      <span className="text-red-400">Configuration Issues</span>
                    </>
                  )}
                </div>
                {validationResult.issues.length > 0 && (
                  <ul className="text-xs text-red-400 space-y-1">
                    {validationResult.issues.map((issue, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                        {issue}
                      </li>
                    ))}
                  </ul>
                )}
                {validationResult.warnings.length > 0 && (
                  <ul className="text-xs text-yellow-400 space-y-1 mt-2">
                    {validationResult.warnings.map((warning, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <AlertCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                        {warning}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}

            {/* Peripheral List */}
            <div className="space-y-1">
              {peripherals.map((peripheral) => (
                <div key={peripheral.name} className="border border-[#3c3c3c] rounded overflow-hidden">
                  <button
                    onClick={() => setExpandedPeripheral(
                      expandedPeripheral === peripheral.name ? null : peripheral.name
                    )}
                    className="w-full px-3 py-2 flex items-center justify-between bg-[#2d2d2d] hover:bg-[#3c3c3c] transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      {getStatusIcon(peripheral.status)}
                      <span className="font-mono text-sm">{peripheral.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#808080]">{peripheral.baseAddress}</span>
                      {expandedPeripheral === peripheral.name ? (
                        <ChevronDown className="w-4 h-4" />
                      ) : (
                        <ChevronRight className="w-4 h-4" />
                      )}
                    </div>
                  </button>

                  {expandedPeripheral === peripheral.name && (
                    <div className="px-3 py-2 bg-[#1e1e1e] border-t border-[#3c3c3c]">
                      <div className="grid grid-cols-2 gap-2 text-xs mb-3">
                        <div>
                          <span className="text-[#808080]">Clock:</span>
                          <span className="ml-2">{peripheral.clockDomain}</span>
                        </div>
                        <div>
                          <span className="text-[#808080]">Status:</span>
                          <span className={`ml-2 ${
                            peripheral.status === 'enabled' ? 'text-green-400' : 'text-gray-400'
                          }`}>
                            {peripheral.status}
                          </span>
                        </div>
                      </div>

                      <div className="mb-3">
                        <span className="text-xs text-[#808080]">Interrupts:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {peripheral.interrupts.map((irq) => (
                            <span
                              key={irq}
                              className="px-2 py-0.5 bg-[#2d2d2d] rounded text-[#569cd6]"
                            >
                              {irq}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Registers */}
                      <div className="border-t border-[#3c3c3c] pt-2">
                        <span className="text-xs text-[#808080] mb-1 block">Registers:</span>
                        <div className="space-y-1">
                          <RegisterItem name="CR" description="Control Register" />
                          <RegisterItem name="SR" description="Status Register" />
                          <RegisterItem name="DR" description="Data Register" />
                          <RegisterItem name="BRR" description="Baud Rate Register" />
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={() => handlePlanInit(peripheral.name)}
                          disabled={!isConnected}
                          className="flex-1 px-2 py-1 bg-[#0e639c] hover:bg-[#1177bb] disabled:bg-[#3c3c3c] disabled:text-[#808080] rounded text-xs flex items-center justify-center gap-1"
                        >
                          {isPlanning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Settings className="w-3 h-3" />}
                          {isPlanning ? 'Planning...' : 'Plan Init'}
                        </button>
                        <button className="flex-1 px-2 py-1 bg-[#3c3c3c] hover:bg-[#4c4c4c] rounded text-xs flex items-center justify-center gap-1">
                          <Settings className="w-3 h-3" />
                          Configure
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Init Plan Display */}
              {initPlan && (
                <div className="mt-3 p-3 bg-[#2d2d2d] rounded border border-[#007acc]">
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="text-xs font-medium text-[#007acc]">
                      Initialization Plan: {initPlan.peripheral}
                    </h4>
                    <button
                      onClick={() => setInitPlan(null)}
                      className="text-xs text-[#808080] hover:text-[#cccccc]"
                    >
                      Close
                    </button>
                  </div>
                  <ol className="text-xs space-y-1">
                    {initPlan.sequence.map((step, i) => (
                      <li key={i} className="flex gap-2">
                        <span className="text-[#569cd6] font-mono">{i + 1}.</span>
                        <span>{step}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'interrupts' && (
          <div className="p-2">
            <div className="space-y-2">
              {[
                { name: 'HardFault', priority: -1, enabled: true },
                { name: 'SysTick', priority: -1, enabled: true },
                { name: 'USART1', priority: 5, enabled: true },
                { name: 'SPI1', priority: 5, enabled: true },
                { name: 'DMA1_Channel1', priority: 6, enabled: true },
                { name: 'EXTI0', priority: 8, enabled: true },
                { name: 'EXTI1', priority: 8, enabled: true },
                { name: 'CAN1_TX', priority: 9, enabled: false },
              ].map((irq) => (
                <div
                  key={irq.name}
                  className="flex items-center justify-between px-3 py-2 bg-[#2d2d2d] rounded border border-[#3c3c3c]"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${
                      irq.enabled ? 'bg-green-500' : 'bg-gray-500'
                    }`} />
                    <span className="font-mono text-sm">{irq.name}</span>
                  </div>
                  <div className="flex items-center gap-4 text-xs text-[#808080]">
                    {irq.priority < 0 ? (
                      <span className="text-red-400">Fixed</span>
                    ) : (
                      <span>Priority: {irq.priority}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'clocks' && (
          <div className="p-2">
            <div className="bg-[#2d2d2d] rounded border border-[#3c3c3c] p-4">
              <div className="flex items-center justify-center mb-4">
                <Database className="w-8 h-8 text-[#007acc]" />
              </div>

              {/* Clock Tree Visualization */}
              <div className="space-y-3">
                <ClockNode name="HSE" value="8 MHz" status="active" />
                <ClockNode name="PLL" value="168 MHz" status="active" />
                <div className="flex justify-center">
                  <div className="w-0.5 h-4 bg-[#007acc]" />
                </div>
                <ClockNode name="SYSCLK" value="168 MHz" status="active" />
                <div className="flex justify-around">
                  <ClockNode name="AHB" value="168 MHz" status="active" />
                  <ClockNode name="APB1" value="42 MHz" status="active" />
                  <ClockNode name="APB2" value="84 MHz" status="active" />
                </div>
              </div>
            </div>

            {/* Clock Details */}
            <div className="mt-3 space-y-2">
              {[
                { name: 'HSE', value: '8 MHz', source: 'External Crystal' },
                { name: 'HSI', value: '16 MHz', source: 'Internal RC' },
                { name: 'LSI', value: '32 kHz', source: 'Internal RC' },
                { name: 'PLL', value: '168 MHz', source: 'HSE / 8 * 336 / 2' },
              ].map((clock) => (
                <div
                  key={clock.name}
                  className="flex items-center justify-between px-3 py-2 bg-[#2d2d2d] rounded"
                >
                  <div>
                    <span className="font-mono text-sm">{clock.name}</span>
                    <span className="text-xs text-[#808080] ml-2">{clock.source}</span>
                  </div>
                  <span className="font-mono text-sm text-[#569cd6]">{clock.value}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'knowledge' && (
          <div className="p-2">
            <div className="mb-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Query hardware knowledge base..."
                  value={knowledgeQuery}
                  onChange={(e) => setKnowledgeQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleKnowledgeQuery()}
                  className="flex-1 px-3 py-2 bg-[#2d2d2d] border border-[#3c3c3c] rounded text-xs"
                />
                <button
                  onClick={handleKnowledgeQuery}
                  disabled={!isConnected || isQuerying || !knowledgeQuery.trim()}
                  className="px-3 py-2 bg-[#0e639c] hover:bg-[#1177bb] disabled:bg-[#3c3c3c] disabled:text-[#808080] rounded text-xs flex items-center gap-2"
                >
                  {isQuerying ? <Loader2 className="w-3 h-3 animate-spin" /> : <Database className="w-3 h-3" />}
                  Query
                </button>
              </div>
            </div>

            {agentError && (
              <div className="mb-3 p-2 bg-red-900/20 border border-red-800 rounded text-xs text-red-400">
                {agentError}
              </div>
            )}

            <div className="space-y-2">
              {knowledgeResults.length > 0 ? (
                knowledgeResults.map((result, i) => (
                  <div key={i} className="bg-[#2d2d2d] rounded p-3 border border-[#3c3c3c]">
                    <p className="text-xs text-[#cccccc] whitespace-pre-wrap">{result}</p>
                  </div>
                ))
              ) : (
                <div className="text-center text-xs text-[#808080] py-8">
                  <Database className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p>Query the hardware knowledge base</p>
                  <p className="mt-1">Examples: "GPIO initialization", "DMA transfer modes", "interrupt priorities"</p>
                </div>
              )}
            </div>

            <div className="mt-4">
              <h4 className="text-xs font-medium mb-2 text-[#808080]">Quick Queries</h4>
              <div className="flex flex-wrap gap-2">
                {['GPIO alternate functions', 'USART baudrate calculation', 'DMA channel mapping'].map((query) => (
                  <button
                    key={query}
                    onClick={() => {
                      setKnowledgeQuery(query);
                      setIsQuerying(true);
                      queryKnowledge(query).then((results) => {
                        if (results && typeof results === 'object' && 'results' in results) {
                          setKnowledgeResults((results as { results: string[] }).results);
                        } else {
                          setKnowledgeResults([JSON.stringify(results, null, 2)]);
                        }
                        setIsQuerying(false);
                      }).catch(() => {
                        setKnowledgeResults(['No results found']);
                        setIsQuerying(false);
                      });
                    }}
                    className="px-2 py-1 bg-[#2d2d2d] hover:bg-[#3c3c3c] rounded text-xs text-[#569cd6]"
                  >
                    {query}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

// Sub-components
const RegisterItem: React.FC<{ name: string; description: string }> = ({ name, description }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="bg-[#2d2d2d] rounded p-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-[#4ec9b0]">{name}</span>
          <span className="text-xs text-[#808080]">{description}</span>
        </div>
        {expanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
      </button>
      {expanded && (
        <div className="mt-2 pt-2 border-t border-[#3c3c3c] text-xs font-mono">
          <div className="flex justify-between mb-1">
            <span className="text-[#808080]">Address:</span>
            <span>0x4000_0000</span>
          </div>
          <div className="flex justify-between mb-1">
            <span className="text-[#808080]">Reset:</span>
            <span>0x0000_0000</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[#808080]">Access:</span>
            <span>RW</span>
          </div>
        </div>
      )}
    </div>
  );
};

const ClockNode: React.FC<{ name: string; value: string; status: string }> = ({
  name,
  value,
  status,
}) => (
  <div
    className={`flex flex-col items-center px-4 py-2 rounded border ${
      status === 'active'
        ? 'bg-[#2d4a2d] border-green-800'
        : 'bg-[#2d2d2d] border-[#3c3c3c]'
    }`}
  >
    <span className="text-xs text-[#808080]">{name}</span>
    <span className={`font-mono text-sm ${status === 'active' ? 'text-green-400' : ''}`}>
      {value}
    </span>
    <span className={`w-2 h-2 rounded-full mt-1 ${
      status === 'active' ? 'bg-green-500' : 'bg-gray-500'
    }`} />
  </div>
);

export default HardwarePanel;
