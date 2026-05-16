"""HardwareAgent - multi-agent integration for the Hardware Semantic Engine."""

from typing import Dict, List, Optional, Any

from src.domains.hardware_engine.core.models import (
    AllocationContext,
    ValidationResult,
    HardwareConstraint,
    ValidationSeverity,
)


class HardwareSemanticEngine:
    """Forward reference - actual class defined in __init__.py"""


class HardwareAgent:
    """
    Hardware reasoning agent - connects HSE to the CARV multi-agent system.

    This agent exposes the Hardware Semantic Engine capabilities
    to the agent orchestration layer. It handles:
    - Natural language hardware queries (e.g., "configure USART2 at 115200")
    - Translation of user intent into hardware allocations
    - Validation of generated firmware against hardware constraints
    - Hardware-aware code review
    """

    def __init__(self, chip: str = "STM32F407"):
        self._chip = chip
        self._engine: Optional[Any] = None
        self._loaded = False

    @property
    def engine(self):
        if self._engine is None:
            from src.domains.hardware_engine import HardwareSemanticEngine
            self._engine = HardwareSemanticEngine(chip=self._chip)
            self._engine.clock_tree.load_default_stm32f4()
            self._engine.interrupt_model.load_default_stm32f4()
        return self._engine

    # ─── Configuration ───────────────────────────────────────────────

    def configure(self, config: Dict):
        """
        Configure the hardware agent from a dict.

        Supported keys:
            chip: str - Chip name (e.g., "STM32F407")
            rm_path: str - Path to Reference Manual PDF
            svd_path: str - Path to CMSIS SVD file
            schema: dict - Direct register schema dict
            pin_map: dict - Custom pin map data
        """
        chip = config.get("chip", self._chip)
        self._chip = chip

        if "schema" in config:
            self.engine.load_json_schema(config["schema"])
            self._loaded = True
        elif "svd_path" in config:
            self.engine.load_svd(config["svd_path"])
            self._loaded = True
        elif "rm_path" in config:
            self.engine.load_rm(config["rm_path"])
            self._loaded = True

        if "pin_map" in config:
            self._load_pin_map(config["pin_map"])

    def _load_pin_map(self, pin_map_data: Dict):
        """Load custom pin map data."""
        for pin_entry in pin_map_data.get("pins", []):
            self.engine.pin_map.add_pin(
                name=pin_entry.get("name", ""),
                port=pin_entry.get("port", ""),
                number=pin_entry.get("number", 0),
                analog=pin_entry.get("analog", []),
                reserved_by=pin_entry.get("reserved_by", ""),
            )

    # ─── Allocation ─────────────────────────────────────────────────

    def process_request(self, request: Dict) -> Dict:
        """
        Process a hardware configuration request.

        Expected request format:
        {
            "peripheral": "USART2",
            "mode": "interrupt",
            "baudrate": 115200,
            "pins": {"TX": "PA2", "RX": "PA3"},
            "priority": 5,
        }

        Returns allocation result with generated code.
        """
        peripheral = request.get("peripheral", "")
        if not peripheral:
            return {
                "success": False,
                "error": "No peripheral specified in request",
            }

        if not self._loaded:
            return {
                "success": False,
                "error": f"Hardware model for {self._chip} not loaded. Call configure() first.",
            }

        result = self.engine.allocate(
            peripheral=peripheral,
            mode=request.get("mode", "default"),
            baudrate=request.get("baudrate"),
            pins=request.get("pins", {}),
            priority=request.get("priority", 0),
            handler=request.get("handler", ""),
        )

        response: Dict[str, Any] = {
            "success": result.valid,
            "peripheral": peripheral,
            "chip": self._chip,
        }

        if result.valid and result.allocation:
            alloc = result.allocation
            response["allocation"] = {
                "peripheral": alloc.peripheral,
                "mode": alloc.mode,
                "pins": [
                    {"signal": pa.signal, "pin": pa.pin, "af": pa.alternate_function}
                    for pa in alloc.pin_assignments
                ],
                "clock": alloc.clock_assignment.__dict__ if alloc.clock_assignment else {},
                "interrupt": alloc.interrupt_assignment.__dict__ if alloc.interrupt_assignment else {},
            }

            # Generate code
            alloc_dict = {
                "peripheral": alloc.peripheral,
                "mode": alloc.mode,
                "pin_assignments": [
                    {"signal": pa.signal, "pin": pa.pin, "peripheral": alloc.peripheral, "alternate_function": pa.alternate_function}
                    for pa in alloc.pin_assignments
                ],
                "clock_assignment": alloc.clock_assignment.__dict__ if alloc.clock_assignment else {},
                "interrupt_assignment": alloc.interrupt_assignment.__dict__ if alloc.interrupt_assignment else {},
                "register_writes": [rw.__dict__ for rw in alloc.register_writes],
            }

            response["code"] = self.engine.generate_init_code(alloc_dict)
            response["summary"] = self.engine.summary()
        else:
            response["errors"] = result.errors
            response["warnings"] = result.warnings

        return response

    # ─── Validation ─────────────────────────────────────────────────

    def validate_firmware(self, firmware_code: str, allocation: dict) -> Dict:
        """
        Validate generated firmware code against hardware constraints.

        Args:
            firmware_code: C source code as string
            allocation: The hardware allocation dict

        Returns:
            Validation report dict
        """
        validation = self.engine.validate_code(firmware_code, allocation)

        return {
            "valid": validation.valid,
            "errors": validation.errors,
            "warnings": validation.warnings,
            "findings": [
                {
                    "severity": f.severity.value,
                    "rule_id": f.rule_id,
                    "message": f.message,
                    "location": f.location,
                    "fix_suggestion": f.fix_suggestion,
                }
                for f in validation.findings
            ],
        }

    def check_conflicts(self, pin: str) -> Dict:
        """Check for pin conflicts."""
        conflicts = self.engine.check_pin_conflict(pin)
        return {
            "pin": pin,
            "conflicts": conflicts,
            "available": len(conflicts) == 0,
        }

    # ─── Information ───────────────────────────────────────────────

    def get_peripheral_info(self, peripheral: str) -> Dict:
        """Get information about a peripheral."""
        return self.engine.get_peripheral_info(peripheral)

    def list_peripherals(self) -> List[str]:
        """List all available peripherals."""
        return self.engine.list_peripherals()

    def get_register_schema(self, peripheral: str) -> Dict:
        """Get register schema for a peripheral."""
        return self.engine.get_register_schema(peripheral)

    def get_summary(self) -> Dict:
        """Get hardware model summary."""
        return self.engine.summary()

    # ─── Tool Interface ────────────────────────────────────────────

    def get_tool_definitions(self) -> List[Dict]:
        """
        Return tool definitions for agent tool registry.

        These expose HSE capabilities as callable tools.
        """
        return [
            {
                "name": "hw_allocate",
                "description": "Allocate hardware resources for a peripheral (pins, clock, interrupt, registers)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peripheral": {"type": "string", "description": "Peripheral name (e.g., USART2, CAN1)"},
                        "mode": {"type": "string", "description": "Mode: default, interrupt, dma, loopback"},
                        "baudrate": {"type": "integer", "description": "Target baudrate for USART/UART"},
                        "pins": {"type": "object", "description": "Explicit pin assignments (signal -> pin)"},
                        "priority": {"type": "integer", "description": "Interrupt priority (0-15)"},
                    },
                    "required": ["peripheral"],
                },
            },
            {
                "name": "hw_validate",
                "description": "Validate C firmware code against hardware constraints",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "C source code to validate"},
                        "allocation": {"type": "object", "description": "Hardware allocation dict"},
                    },
                    "required": ["code", "allocation"],
                },
            },
            {
                "name": "hw_info",
                "description": "Get hardware information about a peripheral (registers, interrupts, signals)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peripheral": {"type": "string", "description": "Peripheral name"},
                    },
                    "required": ["peripheral"],
                },
            },
            {
                "name": "hw_check_conflict",
                "description": "Check if a pin has conflicts",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pin": {"type": "string", "description": "Pin name (e.g., PA9)"},
                    },
                    "required": ["pin"],
                },
            },
            {
                "name": "hw_list_peripherals",
                "description": "List all available peripherals in the hardware model",
            },
            {
                "name": "hw_generate_register_header",
                "description": "Generate register bit definition header for a peripheral",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "peripheral": {"type": "string", "description": "Peripheral name"},
                    },
                    "required": ["peripheral"],
                },
            },
        ]
