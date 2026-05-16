"""Clock Tree Model - peripheral clock configuration."""

from typing import Dict, List, Optional, Set

from src.domains.hardware_engine.core.models import ClockDomain, Chip


# ─── STM32F407 Clock Tree Reference ──────────────────────────────────

STM32F407_CLOCK_TREE: Dict[str, ClockDomain] = {
    "HSE": ClockDomain(
        name="HSE",
        source="external",
        frequency_hz=8_000_000,
        description="High-Speed External oscillator",
    ),
    "HSI": ClockDomain(
        name="HSI",
        source="internal",
        frequency_hz=16_000_000,
        description="High-Speed Internal 16MHz RC",
    ),
    "PLL": ClockDomain(
        name="PLL",
        source="HSE",
        frequency_hz=168_000_000,
        description="Phase-Locked Loop, VCO = HSE / PLLM * PLLN, SYSCLK = VCO / PLLP",
        enables=["SYSCLK"],
    ),
    "SYSCLK": ClockDomain(
        name="SYSCLK",
        source="PLL",
        frequency_hz=168_000_000,
        description="System clock, 168MHz for STM32F407",
        enables=["AHB", "APB1", "APB2"],
    ),
    "AHB": ClockDomain(
        name="AHB",
        source="SYSCLK",
        frequency_hz=168_000_000,
        prescaler=1,
        enables=["GPIOA", "GPIOB", "GPIOC", "GPIOD", "GPIOE"],
        description="Advanced High-Performance Bus",
    ),
    "APB1": ClockDomain(
        name="APB1",
        source="AHB",
        frequency_hz=42_000_000,
        prescaler=4,
        enables=["USART2", "USART3", "UART4", "UART5", "SPI2", "SPI3", "I2C1", "I2C2", "I2C3", "CAN1", "CAN2", "TIM2", "TIM3", "TIM4", "TIM5"],
        description="APB1 bus, max 42MHz for STM32F4",
    ),
    "APB2": ClockDomain(
        name="APB2",
        source="AHB",
        frequency_hz=84_000_000,
        prescaler=2,
        enables=["USART1", "USART6", "SPI1", "SPI4", "SPI5", "ADC1", "ADC2", "ADC3", "TIM1", "TIM8", "TIM9", "TIM10", "TIM11"],
        description="APB2 bus, max 84MHz for STM32F4",
    ),
    "I2S": ClockDomain(
        name="I2S",
        source="PLLI2SN",
        frequency_hz=192_000_000,
        description="I2S clock from dedicated PLL",
    ),
}


class ClockTree:
    """
    Clock tree model for peripheral clock configuration.

    Models:
    - Clock domains (HSE, HSI, PLL, SYSCLK, AHB, APB1, APB2)
    - Clock enables per peripheral
    - Frequency calculations
    - Bus speed constraints (e.g., APB1 max 42MHz)
    """

    def __init__(self):
        self._domains: Dict[str, ClockDomain] = {}
        self._enabled_peripherals: Set[str] = set()
        self._sysclk_hz: int = 168_000_000
        self._hse_hz: int = 8_000_000
        self._hsi_hz: int = 16_000_000

    def load_default_stm32f4(self):
        """Load STM32F4xx default clock tree."""
        for name, domain in STM32F407_CLOCK_TREE.items():
            self._domains[name] = domain
        self._sysclk_hz = 168_000_000

    def load_custom(self, domains: Dict[str, ClockDomain]):
        """Load a custom clock tree."""
        self._domains.update(domains)

    def set_sysclk(self, frequency_hz: int):
        self._sysclk_hz = frequency_hz

    def get_domain(self, name: str) -> Optional[ClockDomain]:
        return self._domains.get(name)

    def get_frequency(self, peripheral: str) -> int:
        """Get peripheral clock frequency based on bus."""
        domain = self._get_peripheral_domain(peripheral)
        if domain and domain in self._domains:
            return self._domains[domain].frequency_hz
        return 0

    def _get_peripheral_domain(self, peripheral: str) -> Optional[str]:
        """Infer clock domain from peripheral name."""
        if any(p in peripheral for p in ["USART2", "USART3", "UART4", "UART5", "SPI2", "SPI3", "I2C1", "I2C2", "CAN1", "CAN2", "TIM2", "TIM3", "TIM4", "TIM5"]):
            return "APB1"
        if any(p in peripheral for p in ["USART1", "USART6", "SPI1", "SPI4", "SPI5", "ADC1", "TIM1", "TIM8", "TIM9", "TIM10", "TIM11"]):
            return "APB2"
        if "GPIO" in peripheral:
            return "AHB"
        if "CAN" in peripheral:
            return "APB1"
        return "APB1"

    def enable_clock(self, peripheral: str) -> bool:
        """Enable clock for a peripheral."""
        if peripheral in self._enabled_peripherals:
            return True

        domain = self._get_peripheral_domain(peripheral)
        if domain and domain in self._domains:
            domain_obj = self._domains[domain]
            if peripheral not in domain_obj.enables:
                domain_obj.enables.append(peripheral)

        self._enabled_peripherals.add(peripheral)
        return True

    def is_enabled(self, peripheral: str) -> bool:
        return peripheral in self._enabled_peripherals

    def get_enabled_peripherals(self) -> List[str]:
        return sorted(self._enabled_peripherals)

    def calculate_baudrate_prescaler(
        self,
        peripheral: str,
        target_baudrate: int,
    ) -> Dict[str, int]:
        """
        Calculate USART baudrate generator values.

        Returns dict with BRR register value and error percentage.
        """
        periph_clock = self.get_frequency(peripheral)

        if periph_clock == 0 or target_baudrate == 0:
            return {"brr": 0, "error_ppm": 0, "periph_clock": 0}

        oversample = 16
        best_error = float("inf")
        best_div = 0

        for div in range(1, 65536):
            actual = periph_clock / (div * oversample)
            error = abs(actual - target_baudrate) / target_baudrate * 1_000_000
            if error < best_error:
                best_error = error
                best_div = div
                if error < 1:
                    break

        return {
            "brr": best_div,
            "div": best_div,
            "actual_baudrate": periph_clock / (best_div * oversample),
            "error_ppm": int(best_error),
            "periph_clock": periph_clock,
            "oversample": oversample,
            "acceptable": best_error < 10000,
        }

    def validate_bus_speed(self, peripheral: str) -> Dict:
        """
        Validate peripheral bus speed against hardware constraints.

        STM32F4: APB1 max 42MHz, APB2 max 84MHz
        """
        domain = self._get_peripheral_domain(peripheral)
        if not domain or domain not in self._domains:
            return {"valid": True}

        domain_obj = self._domains[domain]
        max_speed = {"APB1": 42_000_000, "APB2": 84_000_000}.get(domain, 168_000_000)

        actual = domain_obj.frequency_hz
        return {
            "valid": actual <= max_speed,
            "domain": domain,
            "actual_hz": actual,
            "max_hz": max_speed,
            "peripheral": peripheral,
            "over_limit": actual - max_speed if actual > max_speed else 0,
        }

    def can_peripheral_run(self, peripheral: str, target_speed: int) -> bool:
        """Check if a peripheral can run at target speed."""
        domain = self._get_peripheral_domain(peripheral)
        if not domain or domain not in self._domains:
            return True
        return self._domains[domain].frequency_hz >= target_speed

    def get_clock_enable_register(self, peripheral: str) -> str:
        """Get the RCC register for enabling peripheral clock."""
        domain = self._get_peripheral_domain(peripheral)
        if domain == "APB1":
            return "RCC->APB1ENR"
        if domain == "APB2":
            return "RCC->APB2ENR"
        if domain == "AHB":
            return "RCC->AHB1ENR"
        return "RCC->APB1ENR"

    def list_domains(self) -> List[str]:
        return sorted(self._domains.keys())

    def reset(self):
        self._enabled_peripherals.clear()

    def to_dict(self) -> dict:
        return {
            "sysclk_hz": self._sysclk_hz,
            "hse_hz": self._hse_hz,
            "hsi_hz": self._hsi_hz,
            "domains": {
                name: {
                    "frequency_hz": d.frequency_hz,
                    "prescaler": d.prescaler,
                    "source": d.source,
                    "enabled_peripherals": d.enables,
                }
                for name, d in self._domains.items()
            },
            "enabled_peripherals": sorted(self._enabled_peripherals),
        }
