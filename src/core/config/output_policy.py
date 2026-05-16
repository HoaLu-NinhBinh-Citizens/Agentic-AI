import re
from typing import List

from src.core.config.agent_prompts import OUTPUT_GENERATED_INC, OUTPUT_GENERATED_SRC


class OutputPolicy:
    """Derive generated output paths from the inferred task domain instead of hardcoded chip names."""

    _CAPABILITY_MARKERS = (
        "uart",
        "usart",
        "gpio",
        "dma",
        "spi",
        "i2c",
        "timer",
        "pwm",
        "can",
        "adc",
        "dac",
        "eth",
        "ethernet",
        "usb",
        "flash",
        "boot",
        "clock",
        "interrupt",
        "monitor",
        "driver",
    )

    _PROFILE_PREFIXES = {
        "stm32_embedded": "stm32",
        "esp32_embedded": "esp32",
        "nrf_embedded": "nrf",
        "rp2040_embedded": "rp2040",
        "generic_document": "module",
    }

    def default_allowed_outputs(
        self,
        task: str,
        domain_profile: str = "generic_document",
        target_family: str = "",
        target_chip: str = "",
    ) -> List[str]:
        stem = self.derive_output_stem(
            task,
            domain_profile=domain_profile,
            target_family=target_family,
            target_chip=target_chip,
        )
        return [
            f"{OUTPUT_GENERATED_INC}/{stem}.h",
            f"{OUTPUT_GENERATED_SRC}/{stem}.c",
        ]

    def derive_output_stem(
        self,
        task: str,
        domain_profile: str = "generic_document",
        target_family: str = "",
        target_chip: str = "",
    ) -> str:
        platform_token = self._select_platform_token(domain_profile, target_family, target_chip)
        capability_token = self._select_capability_token(task)
        stem_parts = [part for part in [platform_token, capability_token] if part]
        if not stem_parts:
            stem_parts = ["generated", "driver"]
        return "_".join(stem_parts)

    def _select_platform_token(self, domain_profile: str, target_family: str, target_chip: str) -> str:
        candidates = [target_chip, target_family, self._PROFILE_PREFIXES.get(domain_profile, "module")]
        for candidate in candidates:
            token = self._slugify(candidate)
            if token:
                return token
        return "module"

    def _select_capability_token(self, task: str) -> str:
        task_lower = str(task).lower()
        for marker in self._CAPABILITY_MARKERS:
            if marker in task_lower:
                if marker == "ethernet":
                    return "eth"
                if marker == "interrupt":
                    return "irq"
                return self._slugify(marker)

        tokens = [
            self._slugify(token)
            for token in re.findall(r"[a-z0-9_]+", task_lower)
            if len(token) >= 3 and token not in {"generate", "write", "implement", "create", "build", "code"}
        ]
        return tokens[0] if tokens else "driver"

    def _slugify(self, value: str) -> str:
        token = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
        return token[:64]
