/**
 * SVD (System View Description) Types
 * 
 * TypeScript interfaces matching the SVD data structure from the SVD parser.
 * These types represent the hardware description from STM32 SVD files.
 */

export interface SVDField {
  name: string;
  bit_offset: number;
  bit_width: number;
  description: string;
  access: 'R' | 'W' | 'RW' | 'ReadOnly' | 'WriteOnly' | 'ReadWrite';
  enumerated_values?: Array<{
    name: string;
    value: number;
    description: string;
  }>;
  reset_value?: number;
}

export interface SVDRegister {
  name: string;
  address_offset: number;
  description: string;
  size: number;
  access: 'R' | 'W' | 'RW' | 'ReadOnly' | 'WriteOnce' | 'WriteOnly' | 'ReadWrite';
  reset_value?: number;
  reset_mask?: number;
  fields: SVDField[];
  dim?: number;
  dim_increment?: number;
}

export interface SVDInterrupt {
  name: string;
  value: number;
}

export interface SVDDMAChannel {
  name: string;
  value: number;
  channel?: number;
}

export interface SVDParseripheral {
  name: string;
  base_address: number;
  description: string;
  group_name?: string;
  prepended_to_group?: boolean;
  header_struct_name?: string;
  registers: SVDRegister[];
  interrupts: SVDInterrupt[];
  dma_requests: SVDDMAChannel[];
  access: 'R' | 'W' | 'RW' | 'ReadOnly' | 'WriteOnly' | 'ReadWrite';
}

export interface SVDDevice {
  name: string;
  vendor: string;
  vendor_id: string;
  series: string;
  version: string;
  description: string;
  license_text: string;
  address_block: Array<{
    offset: number;
    size: number;
    usage: 'registers' | 'memory' | 'reserved';
  }>;
  peripherals: SVDParseripheral[];
}

export interface ChipInfo {
  name: string;
  vendor: string;
  family: string;
  core: string;
  frequency: string;
  flash: string;
  ram: string;
  svd?: string;
}

export interface PeripheralInfo {
  name: string;
  baseAddress: string;
  description: string;
  clockDomain: string;
  interrupts: string[];
  registers: string[];
}
