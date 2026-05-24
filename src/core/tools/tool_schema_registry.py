"""Tool Schema Registry - Prevents API Hallucination.

PROBLEM:
AI invent non-existent APIs như:
- HAL_TIM_PWM_Start_IT (không tồn tại)
- SPI_EnableDMA() (không tồn tại)
- UART_SetTimeout() (không tồn tại)

SOLUTION:
┌─────────────────────────────────────────────────────────────────┐
│                    ToolSchemaRegistry                              │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  HAL API Registry (STM32 HAL functions)                   │  │
│  │  - Function name                                          │  │
│  │  - Parameters (name, type, direction)                     │  │
│  │  - Return type                                            │  │
│  │  - Header file                                            │  │
│  │  - Valid values/ranges                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Validation Engine                                         │  │
│  │  1. Check if function exists                              │  │
│  │  2. Check if parameters are valid                          │  │
│  │  3. Check if return type matches                          │  │
│  │  4. Suggest closest valid alternative                     │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Detection Rules                                           │  │
│  │  - Pattern: "HAL_*_IT" → usually wrong (no IT variant)   │  │
│  │  - Pattern: "*_DMA_" → verify DMA exists for peripheral  │  │
│  │  - Pattern: "*_Async" → check for async variant          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

KEY FEATURES:
1. Schema validation - verify function exists
2. Parameter validation - verify parameters match
3. Pattern detection - flag suspicious API patterns
4. Suggestion engine - suggest correct alternatives
5. Custom registries - add project-specific APIs
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class ValidationResult(Enum):
    """API validation result."""
    VALID = "valid"
    INVALID_NAME = "invalid_name"
    INVALID_PARAMS = "invalid_params"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    NOT_FOUND = "not_found"


@dataclass
class Parameter:
    """API parameter definition."""
    name: str
    param_type: str
    direction: str = "in"  # in, out, inout
    optional: bool = False
    valid_values: Optional[list[Any]] = None
    range_min: Optional[float] = None
    range_max: Optional[float] = None


@dataclass
class APISchema:
    """Schema for a single API function."""
    name: str
    full_name: str
    return_type: str
    parameters: list[Parameter] = field(default_factory=list)
    header_file: str = ""
    description: str = ""
    category: str = ""
    since_version: str = ""
    deprecated: bool = False
    alternatives: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    """Report from API validation."""
    result: ValidationResult
    api_name: str
    message: str
    suggestions: list[str] = field(default_factory=list)
    similar_apis: list[str] = field(default_factory=list)
    pattern_warning: Optional[str] = None
    parameter_issues: list[str] = field(default_factory=list)


class SuspiciousPatternDetector:
    """Detects patterns that indicate API hallucination."""

    PATTERNS = [
        {
            "pattern": r"HAL_.*_IT\b",
            "warning": "HAL *_IT functions typically don't exist. Use interrupt enable flags instead.",
            "example": "HAL_TIM_PWM_Start_IT → use HAL_TIM_PWM_Start + interrupt enable",
        },
        {
            "pattern": r"HAL_.*_DMA\b",
            "warning": "Verify DMA exists for this peripheral. Many peripherals don't have DMA.",
            "example": "Check if peripheral has DMA channel",
        },
        {
            "pattern": r".*_Async\b",
            "warning": "Async variant may not exist. Check for sync version.",
            "example": "Use sync version or polling pattern",
        },
        {
            "pattern": r".*_IT\b",
            "warning": "IT/Interrupt variant may not exist. Check base function.",
            "example": "Use base function with interrupt configuration",
        },
        {
            "pattern": r".*_Fast\b",
            "warning": "Fast variant may not exist.",
            "example": "Use standard function",
        },
        {
            "pattern": r".*_Multi\b",
            "warning": "Multi variant may not exist.",
            "example": "Use single-item functions",
        },
        {
            "pattern": r".*_Ex\b$",
            "warning": "Extended variant may not exist or has different signature.",
            "example": "Check base function for Extended version",
        },
    ]

    @classmethod
    def check(cls, api_name: str) -> Optional[str]:
        """Check if API matches suspicious pattern."""
        for p in cls.PATTERNS:
            if re.search(p["pattern"], api_name):
                return p["warning"]
        return None


class STM32HALRegistry:
    """Registry of STM32 HAL APIs."""

    # UART HAL APIs
    UART_APIS = {
        "HAL_UART_Init": APISchema(
            name="HAL_UART_Init",
            full_name="HAL_UART_Init",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("huart", "UART_HandleTypeDef*", "in"),
                Parameter("pConfig", "UART_InitTypeDef*", "in"),
            ],
            header_file="stm32f4xx_hal_uart.h",
            description="Initialize UART peripheral",
            category="uart",
        ),
        "HAL_UART_Transmit": APISchema(
            name="HAL_UART_Transmit",
            full_name="HAL_UART_Transmit",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("huart", "UART_HandleTypeDef*", "in"),
                Parameter("pData", "uint8_t*", "in"),
                Parameter("Size", "uint16_t", "in"),
                Parameter("Timeout", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_uart.h",
            description="Transmit data via UART",
            category="uart",
        ),
        "HAL_UART_Receive": APISchema(
            name="HAL_UART_Receive",
            full_name="HAL_UART_Receive",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("huart", "UART_HandleTypeDef*", "in"),
                Parameter("pData", "uint8_t*", "out"),
                Parameter("Size", "uint16_t", "in"),
                Parameter("Timeout", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_uart.h",
            description="Receive data via UART",
            category="uart",
        ),
        "HAL_UART_Transmit_IT": APISchema(
            name="HAL_UART_Transmit_IT",
            full_name="HAL_UART_Transmit_IT",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("huart", "UART_HandleTypeDef*", "in"),
                Parameter("pData", "uint8_t*", "in"),
                Parameter("Size", "uint16_t", "in"),
            ],
            header_file="stm32f4xx_hal_uart.h",
            description="Transmit data via UART in interrupt mode",
            category="uart",
        ),
        "HAL_UART_Receive_IT": APISchema(
            name="HAL_UART_Receive_IT",
            full_name="HAL_UART_Receive_IT",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("huart", "UART_HandleTypeDef*", "in"),
                Parameter("pData", "uint8_t*", "out"),
                Parameter("Size", "uint16_t", "in"),
            ],
            header_file="stm32f4xx_hal_uart.h",
            description="Receive data via UART in interrupt mode",
            category="uart",
        ),
    }

    # SPI HAL APIs
    SPI_APIS = {
        "HAL_SPI_Init": APISchema(
            name="HAL_SPI_Init",
            full_name="HAL_SPI_Init",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hspi", "SPI_HandleTypeDef*", "in"),
            ],
            header_file="stm32f4xx_hal_spi.h",
            description="Initialize SPI peripheral",
            category="spi",
        ),
        "HAL_SPI_TransmitReceive": APISchema(
            name="HAL_SPI_TransmitReceive",
            full_name="HAL_SPI_TransmitReceive",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hspi", "SPI_HandleTypeDef*", "in"),
                Parameter("pTxData", "uint8_t*", "in"),
                Parameter("pRxData", "uint8_t*", "out"),
                Parameter("DataSize", "uint16_t", "in"),
                Parameter("Timeout", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_spi.h",
            description="Transmit and receive data via SPI",
            category="spi",
        ),
    }

    # TIM HAL APIs
    TIM_APIS = {
        "HAL_TIM_Base_Init": APISchema(
            name="HAL_TIM_Base_Init",
            full_name="HAL_TIM_Base_Init",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("htim", "TIM_HandleTypeDef*", "in"),
            ],
            header_file="stm32f4xx_hal_tim.h",
            description="Initialize timer base",
            category="tim",
        ),
        "HAL_TIM_PWM_Init": APISchema(
            name="HAL_TIM_PWM_Init",
            full_name="HAL_TIM_PWM_Init",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("htim", "TIM_HandleTypeDef*", "in"),
            ],
            header_file="stm32f4xx_hal_tim.h",
            description="Initialize PWM mode",
            category="tim",
        ),
        "HAL_TIM_PWM_Start": APISchema(
            name="HAL_TIM_PWM_Start",
            full_name="HAL_TIM_PWM_Start",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("htim", "TIM_HandleTypeDef*", "in"),
                Parameter("Channel", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_tim.h",
            description="Start PWM generation",
            category="tim",
        ),
        "HAL_TIM_PWM_Stop": APISchema(
            name="HAL_TIM_PWM_Stop",
            full_name="HAL_TIM_PWM_Stop",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("htim", "TIM_HandleTypeDef*", "in"),
                Parameter("Channel", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_tim.h",
            description="Stop PWM generation",
            category="tim",
        ),
        # NOTE: HAL_TIM_PWM_Start_IT does NOT exist!
    }

    # GPIO HAL APIs
    GPIO_APIS = {
        "HAL_GPIO_Init": APISchema(
            name="HAL_GPIO_Init",
            full_name="HAL_GPIO_Init",
            return_type="void",
            parameters=[
                Parameter("GPIOx", "GPIO_TypeDef*", "in"),
                Parameter("GPIO_Pin", "uint16_t", "in"),
                Parameter("Config", "GPIO_InitTypeDef*", "in"),
            ],
            header_file="stm32f4xx_hal_gpio.h",
            description="Initialize GPIO pin",
            category="gpio",
        ),
        "HAL_GPIO_WritePin": APISchema(
            name="HAL_GPIO_WritePin",
            full_name="HAL_GPIO_WritePin",
            return_type="void",
            parameters=[
                Parameter("GPIOx", "GPIO_TypeDef*", "in"),
                Parameter("GPIO_Pin", "uint16_t", "in"),
                Parameter("PinState", "GPIO_PinState", "in"),
            ],
            header_file="stm32f4xx_hal_gpio.h",
            description="Write GPIO pin state",
            category="gpio",
        ),
        "HAL_GPIO_ReadPin": APISchema(
            name="HAL_GPIO_ReadPin",
            full_name="HAL_GPIO_ReadPin",
            return_type="GPIO_PinState",
            parameters=[
                Parameter("GPIOx", "GPIO_TypeDef*", "in"),
                Parameter("GPIO_Pin", "uint16_t", "in"),
            ],
            header_file="stm32f4xx_hal_gpio.h",
            description="Read GPIO pin state",
            category="gpio",
        ),
    }

    # I2C HAL APIs
    I2C_APIS = {
        "HAL_I2C_Master_Transmit": APISchema(
            name="HAL_I2C_Master_Transmit",
            full_name="HAL_I2C_Master_Transmit",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hi2c", "I2C_HandleTypeDef*", "in"),
                Parameter("DevAddress", "uint16_t", "in"),
                Parameter("pData", "uint8_t*", "in"),
                Parameter("Size", "uint16_t", "in"),
                Parameter("Timeout", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_i2c.h",
            description="Master transmit via I2C",
            category="i2c",
        ),
        "HAL_I2C_Master_Receive": APISchema(
            name="HAL_I2C_Master_Receive",
            full_name="HAL_I2C_Master_Receive",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hi2c", "I2C_HandleTypeDef*", "in"),
                Parameter("DevAddress", "uint16_t", "in"),
                Parameter("pData", "uint8_t*", "out"),
                Parameter("Size", "uint16_t", "in"),
                Parameter("Timeout", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_i2c.h",
            description="Master receive via I2C",
            category="i2c",
        ),
        "HAL_I2C_Mem_Read": APISchema(
            name="HAL_I2C_Mem_Read",
            full_name="HAL_I2C_Mem_Read",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hi2c", "I2C_HandleTypeDef*", "in"),
                Parameter("DevAddress", "uint16_t", "in"),
                Parameter("MemAddress", "uint16_t", "in"),
                Parameter("MemAddSize", "uint8_t", "in"),
                Parameter("pData", "uint8_t*", "out"),
                Parameter("Size", "uint16_t", "in"),
                Parameter("Timeout", "uint32_t", "in"),
            ],
            header_file="stm32f4xx_hal_i2c.h",
            description="Memory read via I2C",
            category="i2c",
        ),
    }

    # DMA APIs (peripheral-agnostic)
    DMA_APIS = {
        "HAL_DMA_Init": APISchema(
            name="HAL_DMA_Init",
            full_name="HAL_DMA_Init",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hdma", "DMA_HandleTypeDef*", "in"),
            ],
            header_file="stm32f4xx_hal_dma.h",
            description="Initialize DMA",
            category="dma",
        ),
        "HAL_DMA_Start": APISchema(
            name="HAL_DMA_Start",
            full_name="HAL_DMA_Start",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hdma", "DMA_HandleTypeDef*", "in"),
                Parameter("SrcAddress", "uint32_t", "in"),
                Parameter("DstAddress", "uint32_t", "in"),
                Parameter("DataLength", "uint16_t", "in"),
            ],
            header_file="stm32f4xx_hal_dma.h",
            description="Start DMA transfer",
            category="dma",
        ),
        "HAL_DMA_Start_IT": APISchema(
            name="HAL_DMA_Start_IT",
            full_name="HAL_DMA_Start_IT",
            return_type="HAL_StatusTypeDef",
            parameters=[
                Parameter("hdma", "DMA_HandleTypeDef*", "in"),
                Parameter("SrcAddress", "uint32_t", "in"),
                Parameter("DstAddress", "uint32_t", "in"),
                Parameter("DataLength", "uint16_t", "in"),
            ],
            header_file="stm32f4xx_hal_dma.h",
            description="Start DMA transfer with interrupt",
            category="dma",
        ),
    }

    @classmethod
    def get_all_apis(cls) -> dict[str, APISchema]:
        """Get all registered APIs."""
        all_apis = {}
        all_apis.update(cls.UART_APIS)
        all_apis.update(cls.SPI_APIS)
        all_apis.update(cls.TIM_APIS)
        all_apis.update(cls.GPIO_APIS)
        all_apis.update(cls.I2C_APIS)
        all_apis.update(cls.DMA_APIS)
        return all_apis


class ToolSchemaRegistry:
    """
    Registry for validating API/tool usage.

    Prevents API hallucination by:
    1. Checking if API exists in registry
    2. Detecting suspicious patterns
    3. Validating parameters
    4. Suggesting correct alternatives
    """

    def __init__(self) -> None:
        self._registry: dict[str, APISchema] = {}
        self._custom_apis: dict[str, APISchema] = {}
        self._known_hallucinations: set[str] = set()

        # Initialize with STM32 HAL
        self._initialize_stm32_hal()

    def _initialize_stm32_hal(self) -> None:
        """Initialize STM32 HAL API registry."""
        all_apis = STM32HALRegistry.get_all_apis()
        for name, schema in all_apis.items():
            self._registry[name] = schema

        # Mark known non-existent APIs
        self._known_hallucinations = {
            "HAL_TIM_PWM_Start_IT",  # Does NOT exist
            "HAL_TIM_PWM_Stop_IT",    # Does NOT exist
            "HAL_SPI_EnableDMA",      # Does NOT exist
            "HAL_UART_SetTimeout",    # Does NOT exist
            "UART_EnableDMA",         # Does NOT exist
        }

    def register_api(self, schema: APISchema) -> None:
        """Register a custom API."""
        self._custom_apis[schema.name] = schema
        self._registry[schema.name] = schema

    def validate_api_call(
        self,
        api_name: str,
        parameters: Optional[dict[str, Any]] = None,
    ) -> ValidationReport:
        """
        Validate an API call.

        Returns ValidationReport with:
        - result: ValidationResult enum
        - message: Human-readable message
        - suggestions: Alternative APIs
        - similar_apis: Similar existing APIs
        """
        parameters = parameters or {}

        # Check known hallucinations
        if api_name in self._known_hallucinations:
            return ValidationReport(
                result=ValidationResult.INVALID_NAME,
                api_name=api_name,
                message=f"'{api_name}' does NOT exist. This is a known hallucinated API.",
                suggestions=self._get_alternatives(api_name),
                similar_apis=self._find_similar(api_name),
            )

        # Check if API exists
        if api_name not in self._registry:
            # Check for suspicious pattern
            pattern_warning = SuspiciousPatternDetector.check(api_name)

            if pattern_warning:
                similar = self._find_similar(api_name)
                return ValidationReport(
                    result=ValidationResult.SUSPICIOUS_PATTERN,
                    api_name=api_name,
                    message=pattern_warning,
                    similar_apis=similar[:5],
                    pattern_warning=pattern_warning,
                    suggestions=self._get_alternatives(api_name),
                )

            return ValidationReport(
                result=ValidationResult.NOT_FOUND,
                api_name=api_name,
                message=f"API '{api_name}' not found in registry.",
                suggestions=self._get_alternatives(api_name),
                similar_apis=self._find_similar(api_name),
            )

        # Validate parameters
        schema = self._registry[api_name]
        param_issues = self._validate_parameters(schema, parameters)

        if param_issues:
            return ValidationReport(
                result=ValidationResult.INVALID_PARAMS,
                api_name=api_name,
                message=f"Parameter validation failed for '{api_name}'",
                parameter_issues=param_issues,
                suggestions=[f"Expected: {p.name} ({p.param_type})" for p in schema.parameters],
            )

        return ValidationReport(
            result=ValidationResult.VALID,
            api_name=api_name,
            message=f"API '{api_name}' is valid",
        )

    def _validate_parameters(
        self,
        schema: APISchema,
        provided: dict[str, Any],
    ) -> list[str]:
        """Validate parameters against schema."""
        issues = []

        required_params = [p for p in schema.parameters if not p.optional]
        provided_names = set(provided.keys())

        for req in required_params:
            if req.name not in provided_names:
                issues.append(f"Missing required parameter: {req.name} ({req.param_type})")

        return issues

    def _find_similar(self, api_name: str) -> list[str]:
        """Find similar APIs using fuzzy matching."""
        all_names = list(self._registry.keys())

        # Use difflib for similarity
        matches = difflib.get_close_matches(api_name, all_names, n=5, cutoff=0.5)

        # Also check by prefix
        prefix_matches = [name for name in all_names if name.startswith(api_name[:6])]

        return list(set(matches + prefix_matches))[:5]

    def _get_alternatives(self, api_name: str) -> list[str]:
        """Get alternative API suggestions."""
        # Common substitutions for hallucinations
        substitutions = {
            "IT": "Use interrupt enable flags in register configuration",
            "DMA": "Use DMA_Init + DMA_Start functions",
            "Async": "Use synchronous version with polling or callback",
            "_Fast": "Use standard function",
        }

        suggestions = []
        for suffix, alt in substitutions.items():
            if api_name.endswith(suffix):
                base = api_name[:-len(suffix)]
                if base in self._registry:
                    suggestions.append(f"{base} (exist) - {alt}")
                suggestions.append(alt)

        return suggestions

    def check_code_for_hallucinations(self, code: str) -> list[ValidationReport]:
        """Scan code for potential API hallucinations."""
        reports = []

        # Find function calls
        pattern = r'\b([A-Z][A-Za-z0-9_]*(?:_[A-Z][A-Za-z0-9_]*)+\s*\()'

        for match in re.finditer(pattern, code):
            func_name = match.group(1)[:-1]  # Remove opening paren
            if not func_name.startswith("HAL_") and not func_name.startswith("USB_"):
                continue

            report = self.validate_api_call(func_name)
            if report.result != ValidationResult.VALID:
                reports.append(report)

        return reports

    def get_api_info(self, api_name: str) -> Optional[APISchema]:
        """Get API schema information."""
        return self._registry.get(api_name)

    def list_apis_by_category(self, category: str) -> list[str]:
        """List all APIs in a category."""
        return [
            name for name, schema in self._registry.items()
            if schema.category == category
        ]

    def get_stats(self) -> dict[str, Any]:
        """Get registry statistics."""
        categories = {}
        for schema in self._registry.values():
            cat = schema.category or "uncategorized"
            categories[cat] = categories.get(cat, 0) + 1

        return {
            "total_apis": len(self._registry),
            "custom_apis": len(self._custom_apis),
            "known_hallucinations": len(self._known_hallucinations),
            "by_category": categories,
        }
