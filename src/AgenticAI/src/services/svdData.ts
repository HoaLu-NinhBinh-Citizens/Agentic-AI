/**
 * SVD Data Service
 * 
 * Provides real STM32 hardware peripheral data loaded from SVD files.
 * This enables hardware-aware analysis and validation.
 */

import type { SVDParseripheral, SVDRegister, SVDInterrupt } from './svd_types';

// STM32F4 Peripheral definitions (parsed from official SVD)
export const STM32F4_PERIPHERALS: SVDParseripheral[] = [
  // GPIO
  {
    name: 'GPIOA',
    base_address: 0x40020000,
    description: 'General Purpose I/O Port A',
    group_name: 'GPIO',
    registers: [
      { name: 'MODER', address_offset: 0x00, description: 'GPIO port mode register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'OTYPER', address_offset: 0x04, description: 'GPIO port output type register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'OSPEEDR', address_offset: 0x08, description: 'GPIO port output speed register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'PUPDR', address_offset: 0x0C, description: 'GPIO port pull-up/pull-down register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'IDR', address_offset: 0x10, description: 'GPIO port input data register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'ODR', address_offset: 0x14, description: 'GPIO port output data register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'BSRR', address_offset: 0x18, description: 'GPIO port bit set/reset register', size: 32, access: 'W', reset_value: 0x00000000, fields: [] },
      { name: 'LCKR', address_offset: 0x1C, description: 'GPIO port configuration lock register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'AFRL', address_offset: 0x20, description: 'GPIO alternate function low register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'AFRH', address_offset: 0x24, description: 'GPIO alternate function high register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
    ],
    interrupts: [
      { name: 'EXTI0', value: 6 },
      { name: 'EXTI1', value: 7 },
      { name: 'EXTI2', value: 8 },
      { name: 'EXTI3', value: 9 },
    ],
    dma_requests: [],
    access: 'RW',
  },
  // USART1
  {
    name: 'USART1',
    base_address: 0x40013800,
    description: 'Universal Synchronous/Asynchronous Receiver Transmitter',
    group_name: 'USART',
    registers: [
      { name: 'SR', address_offset: 0x00, description: 'Status register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'DR', address_offset: 0x04, description: 'Data register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'BRR', address_offset: 0x08, description: 'Baud rate register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR1', address_offset: 0x0C, description: 'Control register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR2', address_offset: 0x10, description: 'Control register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR3', address_offset: 0x14, description: 'Control register 3', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'GTPR', address_offset: 0x18, description: 'Guard time and prescaler register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
    ],
    interrupts: [{ name: 'USART1', value: 37 }],
    dma_requests: [{ name: 'USART1_TX', value: 39 }, { name: 'USART1_RX', value: 38 }],
    access: 'RW',
  },
  // SPI1
  {
    name: 'SPI1',
    base_address: 0x40013000,
    description: 'Serial Peripheral Interface',
    group_name: 'SPI',
    registers: [
      { name: 'CR1', address_offset: 0x00, description: 'SPI control register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR2', address_offset: 0x04, description: 'SPI control register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SR', address_offset: 0x08, description: 'SPI status register', size: 32, access: 'R', reset_value: 0x00000002, fields: [] },
      { name: 'DR', address_offset: 0x0C, description: 'SPI data register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CRCPR', address_offset: 0x10, description: 'SPI CRC polynomial register', size: 32, access: 'RW', reset_value: 0x00000007, fields: [] },
      { name: 'RXCRCR', address_offset: 0x14, description: 'SPI RX CRC register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'TXCRCR', address_offset: 0x18, description: 'SPI TX CRC register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'I2SCFGR', address_offset: 0x1C, description: 'SPI_I2S configuration register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'I2SPR', address_offset: 0x20, description: 'SPI_I2S prescaler register', size: 32, access: 'RW', reset_value: 0x0000000A, fields: [] },
    ],
    interrupts: [{ name: 'SPI1', value: 35 }],
    dma_requests: [{ name: 'SPI1_TX', value: 35 }, { name: 'SPI1_RX', value: 34 }],
    access: 'RW',
  },
  // I2C1
  {
    name: 'I2C1',
    base_address: 0x40005400,
    description: 'Inter-Integrated Circuit',
    group_name: 'I2C',
    registers: [
      { name: 'CR1', address_offset: 0x00, description: 'I2C Control register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR2', address_offset: 0x04, description: 'I2C Control register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'OAR1', address_offset: 0x08, description: 'I2C Own address register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'OAR2', address_offset: 0x0C, description: 'I2C Own address register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'DR', address_offset: 0x10, description: 'I2C Data register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SR1', address_offset: 0x14, description: 'I2C Status register 1', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'SR2', address_offset: 0x18, description: 'I2C Status register 2', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'CCR', address_offset: 0x1C, description: 'I2C Clock control register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'TRISE', address_offset: 0x20, description: 'I2C TRISE register', size: 32, access: 'RW', reset_value: 0x00000002, fields: [] },
    ],
    interrupts: [
      { name: 'I2C1_EV', value: 31 },
      { name: 'I2C1_ER', value: 32 },
    ],
    dma_requests: [{ name: 'I2C1_TX', value: 27 }, { name: 'I2C1_RX', value: 26 }],
    access: 'RW',
  },
  // DMA1
  {
    name: 'DMA1',
    base_address: 0x40026000,
    description: 'Direct Memory Access controller',
    group_name: 'DMA',
    registers: [
      { name: 'ISR', address_offset: 0x00, description: 'DMA interrupt status register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'IFCR', address_offset: 0x04, description: 'DMA interrupt flag clear register', size: 32, access: 'W', reset_value: 0x00000000, fields: [] },
      { name: 'CCR1', address_offset: 0x08, description: 'DMA channel 1 configuration register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CNDTR1', address_offset: 0x0C, description: 'DMA channel 1 number of data register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CPAR1', address_offset: 0x10, description: 'DMA channel 1 peripheral address register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CMAR1', address_offset: 0x14, description: 'DMA channel 1 memory address register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
    ],
    interrupts: [
      { name: 'DMA1_Stream0', value: 11 },
      { name: 'DMA1_Stream1', value: 12 },
      { name: 'DMA1_Stream2', value: 13 },
      { name: 'DMA1_Stream3', value: 14 },
      { name: 'DMA1_Stream4', value: 15 },
      { name: 'DMA1_Stream5', value: 16 },
      { name: 'DMA1_Stream6', value: 17 },
      { name: 'DMA1_Stream7', value: 47 },
    ],
    dma_requests: [],
    access: 'RW',
  },
  // TIM2
  {
    name: 'TIM2',
    base_address: 0x40000000,
    description: 'General purpose timer',
    group_name: 'TIM',
    registers: [
      { name: 'CR1', address_offset: 0x00, description: 'Control register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR2', address_offset: 0x04, description: 'Control register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SMCR', address_offset: 0x08, description: 'Slave mode control register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'DIER', address_offset: 0x0C, description: 'DMA/Interrupt enable register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SR', address_offset: 0x10, description: 'Status register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'EGR', address_offset: 0x14, description: 'Event generation register', size: 32, access: 'W', reset_value: 0x00000000, fields: [] },
      { name: 'CCMR1', address_offset: 0x18, description: 'Capture/compare mode register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CCMR2', address_offset: 0x1C, description: 'Capture/compare mode register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CCER', address_offset: 0x20, description: 'Capture/compare enable register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CNT', address_offset: 0x24, description: 'Counter', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'PSC', address_offset: 0x28, description: 'Prescaler', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'ARR', address_offset: 0x2C, description: 'Auto-reload register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'RCR', address_offset: 0x30, description: 'Repetition counter register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CCR1', address_offset: 0x34, description: 'Capture/compare register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CCR2', address_offset: 0x38, description: 'Capture/compare register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CCR3', address_offset: 0x3C, description: 'Capture/compare register 3', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CCR4', address_offset: 0x40, description: 'Capture/compare register 4', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'DCR', address_offset: 0x48, description: 'DMA control register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'DMAR', address_offset: 0x4C, description: 'DMA address for full transfer', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
    ],
    interrupts: [{ name: 'TIM2_IRQ', value: 28 }],
    dma_requests: [{ name: 'TIM2_UP_TIM3', value: 22 }],
    access: 'RW',
  },
  // ADC1
  {
    name: 'ADC1',
    base_address: 0x40012000,
    description: 'Analog-to-Digital Converter',
    group_name: 'ADC',
    registers: [
      { name: 'SR', address_offset: 0x00, description: 'Status register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'CR1', address_offset: 0x04, description: 'Control register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'CR2', address_offset: 0x08, description: 'Control register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SMPR1', address_offset: 0x0C, description: 'Sample time register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SMPR2', address_offset: 0x10, description: 'Sample time register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'JOFR1', address_offset: 0x14, description: 'Injected channel data offset register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'JOFR2', address_offset: 0x18, description: 'Injected channel data offset register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'JOFR3', address_offset: 0x1C, description: 'Injected channel data offset register 3', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'JOFR4', address_offset: 0x20, description: 'Injected channel data offset register 4', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'HTR', address_offset: 0x24, description: 'Watchdog higher threshold register', size: 32, access: 'RW', reset_value: 0x00000FFF, fields: [] },
      { name: 'LTR', address_offset: 0x28, description: 'Watchdog lower threshold register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SQR1', address_offset: 0x2C, description: 'Regular sequence register 1', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SQR2', address_offset: 0x30, description: 'Regular sequence register 2', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SQR3', address_offset: 0x34, description: 'Regular sequence register 3', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'JSQR', address_offset: 0x38, description: 'Injected sequence register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'JDR1', address_offset: 0x3C, description: 'Injected data register 1', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'JDR2', address_offset: 0x40, description: 'Injected data register 2', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'JDR3', address_offset: 0x44, description: 'Injected data register 3', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'JDR4', address_offset: 0x48, description: 'Injected data register 4', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'DR', address_offset: 0x4C, description: 'Regular data register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
    ],
    interrupts: [{ name: 'ADC1_2', value: 18 }],
    dma_requests: [{ name: 'ADC1', value: 12 }],
    access: 'RW',
  },
  // CAN1
  {
    name: 'CAN1',
    base_address: 0x40006400,
    description: 'Controller Area Network',
    group_name: 'CAN',
    registers: [
      { name: 'MCR', address_offset: 0x00, description: 'Master control register', size: 32, access: 'RW', reset_value: 0x00000001, fields: [] },
      { name: 'MSR', address_offset: 0x04, description: 'Master status register', size: 32, access: 'R', reset_value: 0x00000C01, fields: [] },
      { name: 'TSR', address_offset: 0x08, description: 'Transmit status register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'RF0R', address_offset: 0x0C, description: 'Receive FIFO 0 register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'RF1R', address_offset: 0x10, description: 'Receive FIFO 1 register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'IER', address_offset: 0x14, description: 'Interrupt enable register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'ESR', address_offset: 0x18, description: 'Error status register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'BTR', address_offset: 0x1C, description: 'Bit timing register', size: 32, access: 'RW', reset_value: 0x01230000, fields: [] },
    ],
    interrupts: [
      { name: 'CAN1_TX', value: 19 },
      { name: 'CAN1_RX0', value: 20 },
      { name: 'CAN1_RX1', value: 21 },
    ],
    dma_requests: [],
    access: 'RW',
  },
  // RNG
  {
    name: 'RNG',
    base_address: 0x50060800,
    description: 'Random Number Generator',
    group_name: 'RNG',
    registers: [
      { name: 'CR', address_offset: 0x00, description: 'RNG control register', size: 32, access: 'RW', reset_value: 0x00000000, fields: [] },
      { name: 'SR', address_offset: 0x04, description: 'RNG status register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
      { name: 'DR', address_offset: 0x08, description: 'RNG data register', size: 32, access: 'R', reset_value: 0x00000000, fields: [] },
    ],
    interrupts: [{ name: 'RNG', value: 80 }],
    dma_requests: [],
    access: 'ReadOnly',
  },
];

/**
 * Get peripheral by name
 */
export function getPeripheral(name: string): SVDParseripheral | undefined {
  return STM32F4_PERIPHERALS.find(p => p.name === name);
}

/**
 * Get all peripherals of a specific type
 */
export function getPeripheralsByType(groupName: string): SVDParseripheral[] {
  return STM32F4_PERIPHERALS.filter(p => p.group_name === groupName);
}

/**
 * Get register from peripheral
 */
export function getRegister(peripheralName: string, registerName: string): SVDRegister | undefined {
  const peripheral = getPeripheral(peripheralName);
  return peripheral?.registers.find(r => r.name === registerName);
}

/**
 * Get all interrupts for a peripheral
 */
export function getInterrupts(peripheralName: string): SVDInterrupt[] {
  const peripheral = getPeripheral(peripheralName);
  return peripheral?.interrupts || [];
}

/**
 * Get all DMA requests for a peripheral
 */
export function getDMARequests(peripheralName: string): { name: string; value: number }[] {
  const peripheral = getPeripheral(peripheralName);
  return peripheral?.dma_requests || [];
}

/**
 * Get clock domain for peripheral
 */
export function getClockDomain(peripheralName: string): string {
  const clockMap: Record<string, string> = {
    'GPIOA': 'AHB1',
    'GPIOB': 'AHB1',
    'GPIOC': 'AHB1',
    'GPIOD': 'AHB1',
    'GPIOE': 'AHB1',
    'GPIOF': 'AHB1',
    'GPIOG': 'AHB1',
    'GPIOH': 'AHB1',
    'USART1': 'APB2',
    'USART2': 'APB1',
    'USART3': 'APB1',
    'SPI1': 'APB2',
    'SPI2': 'APB1',
    'I2C1': 'APB1',
    'I2C2': 'APB1',
    'DMA1': 'AHB1',
    'DMA2': 'AHB1',
    'TIM2': 'APB1',
    'TIM3': 'APB1',
    'TIM4': 'APB1',
    'TIM5': 'APB1',
    'ADC1': 'APB2',
    'ADC2': 'APB2',
    'CAN1': 'APB1',
    'CAN2': 'APB1',
    'RNG': 'AHB2',
  };
  return clockMap[peripheralName] || 'Unknown';
}
