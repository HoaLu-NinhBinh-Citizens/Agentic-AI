"""HardwareEngineAdapter - bridges HSE to the CARV EmbeddedCAgent."""

from typing import Dict, List, Optional


class HardwareEngineAdapter:
    """
    Adapter bridging the Hardware Semantic Engine to the CARV agent system.

    Translates between:
    - EmbeddedCAgent tool calls <-> HardwareAgent tools
    - CARV schema output <-> HSE register schemas
    - Build error messages <-> hardware constraint violations

    This adapter allows the Hardware Semantic Engine to work with
    the existing CARV multi-agent infrastructure without requiring
    the EmbeddedCAgent to be rewritten.
    """

    def __init__(self, hardware_agent=None):
        self.hardware_agent = hardware_agent
        self._tool_registry: Dict[str, callable] = {}

    def register(self):
        """Register HSE tools with the CARV tool registry."""
        if not self.hardware_agent:
            from src.domains.hardware_engine.integration.hw_agent import HardwareAgent
            self.hardware_agent = HardwareAgent()

        tool_defs = self.hardware_agent.get_tool_definitions()
        for tool_def in tool_defs:
            name = tool_def["name"]
            self._tool_registry[name] = self._create_tool_wrapper(name)

        return list(self._tool_registry.keys())

    def _create_tool_wrapper(self, tool_name: str):
        """Create a callable wrapper for a tool."""
        def wrapper(**kwargs):
            return self.call_tool(tool_name, kwargs)
        wrapper.__name__ = tool_name
        wrapper.__doc__ = f"Hardware Semantic Engine tool: {tool_name}"
        return wrapper

    def call_tool(self, tool_name: str, params: Dict) -> Dict:
        """Call an HSE tool by name."""
        if not self.hardware_agent:
            return {"error": "HardwareAgent not initialized"}

        if tool_name == "hw_allocate":
            return self.hardware_agent.process_request(params)
        elif tool_name == "hw_validate":
            return self.hardware_agent.validate_firmware(
                params.get("code", ""), params.get("allocation", {})
            )
        elif tool_name == "hw_info":
            return self.hardware_agent.get_peripheral_info(params.get("peripheral", ""))
        elif tool_name == "hw_check_conflict":
            return self.hardware_agent.check_conflicts(params.get("pin", ""))
        elif tool_name == "hw_list_peripherals":
            return {"peripherals": self.hardware_agent.list_peripherals()}
        elif tool_name == "hw_generate_register_header":
            return {
                "header": self.hardware_agent.engine.codegen.generate_register_header(
                    params.get("peripheral", "")
                )
            }
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def configure_from_board_profile(self, board_profile: Dict):
        """
        Configure HSE from a CARV board profile.

        Extracts chip info, flash/debug settings, and applies them to HSE.
        """
        if not self.hardware_agent:
            from src.domains.hardware_engine.integration.hw_agent import HardwareAgent
            self.hardware_agent = HardwareAgent()

        mcu = board_profile.get("mcu", "")
        if mcu:
            self.hardware_agent._chip = mcu
            self.hardware_agent.engine.chip = mcu

        self.hardware_agent.engine.clock_tree.load_default_stm32f4()
        self.hardware_agent.engine.interrupt_model.load_default_stm32f4()
        self.hardware_agent._loaded = True

        return {"status": "configured", "chip": mcu}

    def translate_build_error(self, build_error: str) -> Dict:
        """
        Translate a build error message to hardware constraint context.

        Maps compiler/linker errors back to hardware constraints.
        """
        error_lower = build_error.lower()

        if "undefined reference" in error_lower:
            return {
                "type": "linker",
                "constraint": "missing_symbol",
                "message": "Likely missing peripheral initialization or register access",
                "suggestion": "Check if clock is enabled and peripheral is initialized",
            }
        if "conflicting types" in error_lower:
            return {
                "type": "compiler",
                "constraint": "type_mismatch",
                "message": "Type mismatch in peripheral register access",
                "suggestion": "Verify register definitions match hardware schema",
            }
        if "未定义" in build_error or "undefined" in error_lower:
            return {
                "type": "linker",
                "constraint": "missing_symbol",
                "message": "Undefined symbol - check peripheral initialization",
                "suggestion": "Run hw_allocate to generate required initialization",
            }

        return {
            "type": "unknown",
            "constraint": "none",
            "message": build_error,
            "suggestion": "Review build output",
        }

    def get_tool_registry(self) -> Dict[str, callable]:
        """Return the tool registry."""
        return self._tool_registry
