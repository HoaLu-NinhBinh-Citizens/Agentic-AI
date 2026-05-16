"""Interrupt Model - NVIC configuration and interrupt allocation."""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from src.domains.hardware_engine.core.models import InterruptAllocation


# ─── STM32F407 NVIC Reference ────────────────────────────────────────

STM32F407_NVIC: Dict[str, int] = {
    "WWDG": 0, "PVD": 1, "TAMPER": 2, "RTC_WKUP": 3,
    "EXTI0": 6, "EXTI1": 7, "EXTI2": 8, "EXTI3": 9, "EXTI4": 10,
    "DMA1_Stream0": 11, "DMA1_Stream1": 12, "DMA1_Stream2": 13,
    "DMA1_Stream3": 14, "DMA1_Stream4": 15, "DMA1_Stream5": 16,
    "DMA1_Stream6": 17, "DMA1_Stream7": 18,
    "ADC1_2": 18, "CAN1_TX": 19, "CAN1_RX0": 20, "CAN1_RX1": 21,
    "CAN1_SCE": 22, "EXTI9_5": 23,
    "TIM1_BRK_TIM9": 24, "TIM1_UP_TIM10": 25, "TIM1_TRG_COM_TIM11": 26,
    "TIM1_CC": 27,
    "TIM2": 28, "TIM3": 29, "TIM4": 30,
    "I2C1_EV": 31, "I2C1_ER": 32, "I2C2_EV": 33, "I2C2_ER": 34,
    "SPI1": 35, "SPI2": 36,
    "USART1": 37, "USART2": 38, "USART3": 39,
    "EXTI15_10": 40, "RTC_Alarm": 41, "OTG_FS_WKUP": 42,
    "TIM5": 50, "TIM6": 54, "TIM7": 55,
    "DMA2_Stream0": 56, "DMA2_Stream1": 57, "DMA2_Stream2": 58,
    "DMA2_Stream3": 59, "DMA2_Stream4": 60,
    "ETH": 61, "ETH_WKUP": 62,
    "CAN2_TX": 63, "CAN2_RX0": 64, "CAN2_RX1": 65, "CAN2_SCE": 66,
    "OTG_FS": 67,
    "DMA2_Stream5": 68, "DMA2_Stream6": 69, "DMA2_Stream7": 70,
    "USART6": 71, "USART6": 72,
    "I2C3_EV": 77, "I2C3_ER": 78,
}


class InterruptModel:
    """
    NVIC interrupt allocation model.

    Models:
    - IRQ line numbers per peripheral
    - Priority levels (STM32F4: 16 priority levels, 4 bits for pre-emption)
    - Interrupt enable/disable state
    - Priority conflicts
    - DMA channel mapping
    """

    def __init__(self):
        self._nvic_config = {
            "total_channels": 82,
            "priority_bits": 4,
            "priority_levels": 16,
        }
        self._irq_by_name: Dict[str, int] = {}
        self._name_by_irq: Dict[int, str] = {}
        self._allocations: Dict[int, InterruptAllocation] = {}
        self._priority_conflicts: List[Dict] = []
        self._dma_channels: Dict[int, str] = {}

    def load_default_stm32f4(self):
        """Load STM32F4 default NVIC configuration."""
        self._irq_by_name = dict(STM32F407_NVIC)
        self._name_by_irq = {v: k for k, v in self._irq_by_name.items()}

        # DMA channels
        self._dma_channels = {
            0: "DMA2_Stream0", 1: "DMA2_Stream0",
            2: "DMA2_Stream1", 3: "DMA2_Stream1",
            4: "DMA2_Stream2", 5: "DMA2_Stream2",
            6: "DMA2_Stream3", 7: "DMA2_Stream3",
            8: "DMA2_Stream4", 9: "DMA2_Stream4",
            10: "DMA2_Stream5", 11: "DMA2_Stream5",
            12: "DMA2_Stream6", 13: "DMA2_Stream6",
            14: "DMA2_Stream7", 15: "DMA2_Stream7",
        }

    def load_custom(self, irq_map: Dict[str, int]):
        """Load a custom IRQ mapping."""
        self._irq_by_name = dict(irq_map)
        self._name_by_irq = {v: k for k, v in self._irq_by_name.items()}

    def get_irq(self, peripheral_name: str) -> Optional[int]:
        """Get IRQ line number for a peripheral."""
        return self._irq_by_name.get(peripheral_name)

    def get_name(self, irq_line: int) -> Optional[str]:
        """Get peripheral name for an IRQ line."""
        return self._name_by_irq.get(irq_line)

    def is_available(self, irq_line: int) -> bool:
        """Check if IRQ line is available."""
        return irq_line not in self._allocations

    def is_peripheral_available(self, peripheral_name: str) -> bool:
        """Check if a peripheral's interrupt is available."""
        irq = self.get_irq(peripheral_name)
        if irq is None:
            return False
        return self.is_available(irq)

    def allocate(
        self,
        peripheral: str,
        handler_name: str,
        priority: int = 0,
        subpriority: int = 0,
    ) -> tuple[bool, str, int]:
        """
        Allocate an interrupt for a peripheral.

        Returns: (success, error_message, irq_line)
        """
        irq_line = self.get_irq(peripheral)
        if irq_line is None:
            return False, f"No IRQ defined for peripheral '{peripheral}'", -1

        if not self.is_available(irq_line):
            existing = self._allocations.get(irq_line)
            return (
                False,
                f"IRQ {irq_line} already allocated to '{existing.peripheral if existing else 'unknown'}'",
                irq_line,
            )

        if priority < 0 or priority >= self._nvic_config["priority_levels"]:
            return False, f"Priority {priority} out of range (0-{self._nvic_config['priority_levels'] - 1})", irq_line

        alloc = InterruptAllocation(
            irq_line=irq_line,
            peripheral=peripheral,
            handler_name=handler_name,
            priority=priority,
            subpriority=subpriority,
            enabled=False,
        )
        self._allocations[irq_line] = alloc
        return True, "", irq_line

    def free(self, peripheral: str) -> bool:
        """Free an interrupt allocation."""
        irq = self.get_irq(peripheral)
        if irq in self._allocations:
            del self._allocations[irq]
            return True
        return False

    def get_allocation(self, irq_line: int) -> Optional[InterruptAllocation]:
        return self._allocations.get(irq_line)

    def list_allocations(self) -> List[InterruptAllocation]:
        return list(self._allocations.values())

    def validate_priority_conflict(self, peripheral: str, priority: int) -> List[Dict]:
        """Check for priority conflicts."""
        conflicts = []
        irq = self.get_irq(peripheral)
        if irq is None:
            return conflicts

        for alloc in self._allocations.values():
            if alloc.irq_line == irq:
                continue
            if alloc.priority == priority:
                conflicts.append({
                    "peripheral": peripheral,
                    "existing": alloc.peripheral,
                    "existing_irq": alloc.irq_line,
                    "priority": priority,
                    "conflict_type": "same_priority",
                })
        return conflicts

    def get_handler_name(self, peripheral: str) -> str:
        """Generate standard handler name."""
        return f"{peripheral}_IRQHandler"

    def get_enable_sequence(self, peripheral: str) -> List[Dict]:
        """
        Generate NVIC enable code sequence.

        Returns list of dicts with register operations.
        """
        irq = self.get_irq(peripheral)
        if irq is None:
            return []

        alloc = self._allocations.get(irq)
        priority = alloc.priority if alloc else 0

        return [
            {"action": "set_priority", "register": f"NVIC->IP[{irq}]", "value": priority << 4},
            {"action": "enable", "register": f"NVIC->ISER[{(irq) >> 5}]", "value": 1 << (irq & 0x1F)},
        ]

    def list_dma_channels(self, stream: int) -> List[int]:
        """Get DMA channel numbers for a stream."""
        return [ch for ch, s in self._dma_channels.items() if s == stream]

    def reset(self):
        self._allocations.clear()
        self._priority_conflicts.clear()

    def to_dict(self) -> dict:
        return {
            "nvic_config": self._nvic_config,
            "allocations": {
                str(irq): {
                    "peripheral": a.peripheral,
                    "handler": a.handler_name,
                    "priority": a.priority,
                    "enabled": a.enabled,
                }
                for irq, a in self._allocations.items()
            },
            "available_count": self._nvic_config["total_channels"] - len(self._allocations),
            "dma_channels": self._dma_channels,
        }
