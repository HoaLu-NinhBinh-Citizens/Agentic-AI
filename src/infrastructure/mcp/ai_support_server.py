"""AI_SUPPORT MCP Server — exposes AI_SUPPORT capabilities as MCP tools.

This module turns AI_SUPPORT into an MCP server that Cursor (or any MCP client)
can connect to and use AI_SUPPORT's embedded engineering intelligence.

Tools exposed:
- hardware_validate: Validate hardware allocation (pins, clocks, IRQs)
- plan_hardware_init: Generate validated hardware initialization plan
- analyze_firmware: Analyze firmware for issues
- reason_about_hardware: Formal reasoning over hardware constraints
- debug_issue: Diagnose and fix embedded issues
- generate_code: Generate hardware-validated C code
- query_knowledge_base: Search hardware knowledge base
- cross_validate: Full cross-validation pipeline

Usage (from servers.yaml):
  - name: "ai_support"
    command: "python"
    args:
      - "-m"
      - "infrastructure.mcp.ai_support_server"
    transport: "stdio"
    enabled: true
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

import structlog

from src.domains.hardware_engine.core.peripheral_graph import PeripheralGraph
from src.domains.hardware_engine.validator.hw_validator import HardwareValidator
from src.domains.hardware_engine.core.register_schema import RegisterSchemaDB
from src.domains.hardware_engine.core.pin_map import PinMap
from src.domains.hardware_engine.core.clock_tree import ClockTree
from src.domains.hardware_engine.core.interrupt_model import InterruptModel
from src.domains.validation import CrossValidator
from src.application.workflows.hardware import HardwareWorkflow
from src.application.workflows.debugging import DebuggingWorkflow
from src.application.workflows.coding import CodingWorkflow
from src.core.agent.reasoning_loop import ReasoningLoop, ReasoningContext
from src.domain.knowledge.kb import KnowledgeBase, KBQuery

logger = structlog.get_logger(__name__)

# ─── MCP Server Bootstrap ────────────────────────────────────────────

async def main():
    """Main entry point for MCP stdio server."""
    try:
        server = AISupportMCPServer()
        await server.run()
    except Exception as e:
        logger.error("ai_support_server_fatal", error=str(e))
        sys.exit(1)


class AISupportMCPServer:
    """
    AI_SUPPORT MCP Server — exposes embedded engineering tools via MCP.

    Implements MCP protocol over stdio for integration with Cursor MCP client.

    Tools:
    1. hardware_validate — Validate pin/clock/IRQ allocation
    2. plan_hardware_init — Generate hardware initialization plan
    3. reason_about_hardware — Formal reasoning over constraints
    4. analyze_firmware — Analyze firmware for issues
    5. debug_issue — Diagnose and generate fix
    6. generate_code — Generate hardware-validated C code
    7. query_knowledge_base — Semantic KB search
    8. cross_validate — Full validation pipeline
    """

    def __init__(self):
        self._initialized = False
        self._graph: PeripheralGraph | None = None
        self._validator: HardwareValidator | None = None
        self._cross_validator: CrossValidator | None = None
        self._reasoning_loop: ReasoningLoop | None = None
        self._kb: KnowledgeBase | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize AI_SUPPORT subsystems."""
        if self._initialized:
            return

        logger.info("ai_support_server_initializing")

        # Initialize hardware graph
        self._graph = PeripheralGraph()

        # Initialize sub-components
        register_schema = RegisterSchemaDB()
        pin_map = PinMap()
        clock_tree = ClockTree()
        interrupt_model = InterruptModel()

        # Initialize hardware validator
        self._validator = HardwareValidator(
            peripheral_graph=self._graph,
            register_schema=register_schema,
            pin_map=pin_map,
            clock_tree=clock_tree,
            interrupt_model=interrupt_model,
        )

        # Initialize cross validator
        self._cross_validator = CrossValidator(
            peripheral_graph=self._graph,
            hardware_validator=self._validator,
        )

        # Initialize reasoning loop
        self._reasoning_loop = ReasoningLoop(
            peripheral_graph=self._graph,
            hardware_validator=self._validator,
        )

        # Initialize knowledge base
        self._kb = KnowledgeBase()

        self._initialized = True
        logger.info("ai_support_server_ready", tools=len(self._tool_handlers))

    # ─── MCP Protocol Handlers ─────────────────────────────────────────

    async def handle_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle incoming MCP request."""
        if method == "initialize":
            return await self._handle_initialize(params)
        elif method == "tools/list":
            return await self._handle_list_tools()
        elif method == "tools/call":
            return await self._handle_call_tool(params)
        elif method == "resources/list":
            return await self._handle_list_resources()
        elif method == "resources/read":
            return await self._handle_read_resource(params)
        else:
            return {"error": f"Unknown method: {method}"}

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        await self.initialize()
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {},
                "resources": {},
            },
            "serverInfo": {
                "name": "ai_support",
                "version": "1.0.0",
            },
        }

    async def _handle_list_tools(self) -> dict[str, Any]:
        return {
            "tools": [
                self._tool_schema(name, schema)
                for name, schema in self._tool_schemas.items()
            ]
        }

    async def _handle_call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = self._tool_handlers.get(name)
        if not handler:
            return {"error": f"Unknown tool: {name}"}

        try:
            result = await handler(arguments)
            # Format result as MCP tool response
            return {
                "content": [
                    {
                        "type": "text",
                        "text": self._format_result(result),
                    }
                ]
            }
        except Exception as e:
            logger.error("tool_call_error", tool=name, error=str(e))
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error: {str(e)}",
                    }
                ],
                "isError": True,
            }

    async def _handle_list_resources(self) -> dict[str, Any]:
        return {
            "resources": [
                {"uri": "ai_support://hardware/schema", "name": "Hardware Schema", "description": "Register and peripheral schema"},
                {"uri": "ai_support://knowledge/stats", "name": "KB Statistics", "description": "Knowledge base entry count"},
            ]
        }

    async def _handle_read_resource(self, params: dict[str, Any]) -> dict[str, Any]:
        uri = params.get("uri", "")
        if uri == "ai_support://knowledge/stats":
            stats = await self._kb.get_stats()
            return {"contents": [{"uri": uri, "mimeType": "application/json", "text": str(stats)}]}
        return {"contents": [{"uri": uri, "mimeType": "text/plain", "text": "Resource not found"}]}

    # ─── Tool Schemas ────────────────────────────────────────────────

    @property
    def _tool_schemas(self) -> dict[str, dict[str, Any]]:
        return {
            "hardware_validate": {
                "description": "Validate hardware allocation (pins, clocks, IRQs, registers) against hardware rules.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "peripheral": {"type": "string", "description": "Peripheral name, e.g. CAN1, USART1"},
                        "pin_assignments": {"type": "array", "description": "List of pin assignments", "items": {"type": "object"}},
                        "clock_assignment": {"type": "object", "description": "Clock configuration"},
                        "interrupt_assignment": {"type": "object", "description": "Interrupt configuration"},
                        "register_writes": {"type": "array", "description": "Register write operations", "items": {"type": "object"}},
                    },
                    "required": ["peripheral"],
                },
            },
            "plan_hardware_init": {
                "description": "Generate a validated hardware initialization plan for a peripheral.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Task description, e.g. 'Initialize CAN1 at 500kbps'"},
                        "chip_family": {"type": "string", "description": "Chip family, e.g. STM32F407"},
                        "peripherals": {"type": "array", "description": "Required peripherals", "items": {"type": "string"}},
                    },
                    "required": ["task"],
                },
            },
            "reason_about_hardware": {
                "description": "Perform formal reasoning over hardware constraints to determine initialization sequence.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "Task to reason about"},
                        "peripherals": {"type": "array", "description": "Available peripherals", "items": {"type": "string"}},
                        "allocation": {"type": "object", "description": "Current allocation state"},
                    },
                    "required": ["task"],
                },
            },
            "analyze_firmware": {
                "description": "Analyze firmware code for hardware issues and violations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "C source code to analyze"},
                        "peripheral": {"type": "string", "description": "Target peripheral"},
                        "allocation": {"type": "object", "description": "Expected allocation"},
                    },
                    "required": ["code"],
                },
            },
            "debug_issue": {
                "description": "Diagnose an embedded firmware issue and generate fix recommendations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "symptom": {"type": "string", "description": "Error symptom or problem description"},
                        "chip_family": {"type": "string", "description": "Chip family"},
                        "error_logs": {"type": "array", "description": "Error log lines", "items": {"type": "string"}},
                    },
                    "required": ["symptom"],
                },
            },
            "generate_code": {
                "description": "Generate hardware-validated C code for peripheral initialization.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "request": {"type": "string", "description": "Code generation request"},
                        "chip_family": {"type": "string", "description": "Chip family"},
                        "style": {"type": "string", "enum": ["register", "hal", "ll"], "description": "Code style"},
                        "output_format": {"type": "string", "enum": ["snippet", "c_file", "full_driver"]},
                    },
                    "required": ["request"],
                },
            },
            "query_knowledge_base": {
                "description": "Query the hardware knowledge base for relevant specs, patterns, and citations.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Search query"},
                        "chip_family": {"type": "string", "description": "Filter by chip family"},
                        "peripheral": {"type": "string", "description": "Filter by peripheral"},
                        "top_k": {"type": "integer", "description": "Number of results (default 5)"},
                    },
                    "required": ["text"],
                },
            },
            "cross_validate": {
                "description": "Run full cross-validation pipeline on a hardware allocation (allocation + dependency + flash + code + safety).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "peripheral": {"type": "string", "description": "Peripheral name"},
                        "allocation": {"type": "object", "description": "Full allocation dict"},
                        "generated_code": {"type": "string", "description": "Generated C code to validate"},
                    },
                    "required": ["peripheral"],
                },
            },
        }

    def _tool_schema(self, name: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": name,
            "description": schema["description"],
            "inputSchema": schema["inputSchema"],
        }

    @property
    def _tool_handlers(self) -> dict[str, callable]:
        return {
            "hardware_validate": self._tool_hardware_validate,
            "plan_hardware_init": self._tool_plan_hardware_init,
            "reason_about_hardware": self._tool_reason_about_hardware,
            "analyze_firmware": self._tool_analyze_firmware,
            "debug_issue": self._tool_debug_issue,
            "generate_code": self._tool_generate_code,
            "query_knowledge_base": self._tool_query_kb,
            "cross_validate": self._tool_cross_validate,
        }

    # ─── Tool Implementations ─────────────────────────────────────────

    async def _tool_hardware_validate(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        allocation = {
            "peripheral": args.get("peripheral", ""),
            "pin_assignments": args.get("pin_assignments", []),
            "clock_assignment": args.get("clock_assignment", {}),
            "interrupt_assignment": args.get("interrupt_assignment", {}),
            "register_writes": args.get("register_writes", []),
        }

        result = self._validator.validate_allocation(allocation)
        return self._format_validation_result(result)

    async def _tool_plan_hardware_init(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        wf = HardwareWorkflow(context={
            "task": args.get("task", ""),
            "chip_family": args.get("chip_family", "STM32F4"),
            "peripherals": args.get("peripherals", []),
        })
        wf._hardware_validator = self._validator
        wf._reasoning_loop = self._reasoning_loop
        wf._knowledge_base = self._kb

        result = await wf.run()
        return result.to_dict()

    async def _tool_reason_about_hardware(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        context = ReasoningContext(
            task=args.get("task", ""),
            hardware_query=args.get("hardware_query", {}),
            available_peripherals=args.get("peripherals", []),
            current_allocation=args.get("allocation", {}),
        )

        result = await self._reasoning_loop.reason(context)
        return result.to_dict()

    async def _tool_analyze_firmware(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        result = self._validator.validate_code(
            args.get("code", ""),
            args.get("allocation", {"peripheral": args.get("peripheral", "")}),
        )
        return self._format_validation_result(result)

    async def _tool_debug_issue(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        wf = DebuggingWorkflow(context={
            "symptom": args.get("symptom", ""),
            "chip_family": args.get("chip_family", "STM32F4"),
            "error_logs": args.get("error_logs", []),
        })
        wf._knowledge_base = self._kb
        wf._reasoning_loop = self._reasoning_loop

        result = await wf.run()
        return result.to_dict()

    async def _tool_generate_code(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        wf = CodingWorkflow(context={
            "request": args.get("request", ""),
            "chip_family": args.get("chip_family", "STM32F407"),
            "style": args.get("style", "register"),
            "output_format": args.get("output_format", "snippet"),
        })
        wf._hardware_validator = self._validator
        wf._reasoning_loop = self._reasoning_loop
        wf._knowledge_base = self._kb

        result = await wf.run()
        return result.to_dict()

    async def _tool_query_kb(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        results = await self._kb.query_by_text(
            text=args.get("text", ""),
            chip_family=args.get("chip_family"),
            peripheral=args.get("peripheral"),
            top_k=args.get("top_k", 5),
        )

        return {
            "results": [
                {
                    "title": r.entry.title,
                    "source": r.entry.source,
                    "type": r.entry.type.value,
                    "score": r.score,
                    "preview": r.entry.content[:300],
                }
                for r in results
            ],
            "total": len(results),
        }

    async def _tool_cross_validate(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            await self.initialize()

        allocation = args.get("allocation", {})
        allocation["peripheral"] = args.get("peripheral", "")
        allocation["generated_code"] = args.get("generated_code", "")

        result = await self._cross_validator.validate_allocation(allocation)
        return result.to_dict()

    # ─── Utilities ────────────────────────────────────────────────────

    def _format_validation_result(self, result) -> dict[str, Any]:
        """Format validation result as readable dict."""
        return {
            "valid": result.valid,
            "errors": result.errors,
            "warnings": result.warnings,
            "findings": [
                {
                    "severity": f.severity.value,
                    "rule_id": f.rule_id,
                    "message": f.message,
                    "location": f.location,
                    "peripheral": f.peripheral,
                }
                for f in result.findings
            ],
        }

    def _format_result(self, result: dict[str, Any]) -> str:
        """Format result as readable text for MCP response."""
        import json
        return json.dumps(result, indent=2, default=str)

    # ─── Stdio Run Loop ──────────────────────────────────────────────

    async def run(self) -> None:
        """Run the MCP server over stdio."""
        await self.initialize()
        logger.info("ai_support_mcp_server_running")

        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break

                import json
                request = json.loads(line)

                method = request.get("method", "")
                params = request.get("params", {})
                req_id = request.get("id")

                response = await self.handle_request(method, params)

                if req_id is not None:
                    reply = {"jsonrpc": "2.0", "id": req_id, **response}
                    print(json.dumps(reply), flush=True)

            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error("mcp_stdio_error", error=str(e))
                if "id" in locals():
                    print(json.dumps({
                        "jsonrpc": "2.0",
                        "id": request.get("id"),
                        "error": {"code": -32603, "message": str(e)},
                    }), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
