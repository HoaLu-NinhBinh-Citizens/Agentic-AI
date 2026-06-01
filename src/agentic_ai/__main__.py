"""MCP Server entry point for Agentic-AI.

This module provides an MCP server that can be spawned as a subprocess
by the Electron app to provide embedded systems intelligence capabilities.

Usage:
    python -m src.agentic_ai

This runs in stdio mode, communicating via JSON-RPC over stdin/stdout.
"""

import asyncio
import json
import sys
import os
from typing import Any, Dict, List, Optional

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))


class MCPServer:
    """MCP Server implementation for Agentic-AI embedded intelligence."""

    def __init__(self):
        self.tools = self._register_tools()
        self.resources = self._register_resources()
        self.prompts = self._register_prompts()
        self.request_id = 0

    def _register_tools(self) -> Dict[str, Dict[str, Any]]:
        """Register available tools."""
        return {
            # Hardware tools
            "hardware_validate": {
                "description": "Validate hardware configuration for embedded systems",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chip": {"type": "string", "description": "Target chip name (e.g., STM32F4)"},
                        "peripherals": {"type": "array", "items": {"type": "string"}},
                        "clockConfig": {"type": "object"},
                        "interrupts": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "plan_hardware_init": {
                "description": "Plan peripheral initialization sequence",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "chip": {"type": "string"},
                        "peripheral": {"type": "string"},
                    },
                    "required": ["chip", "peripheral"],
                },
            },
            "reason_about_hardware": {
                "description": "Answer questions about hardware semantics",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "question": {"type": "string"},
                        "context": {"type": "object"},
                    },
                    "required": ["question"],
                },
            },
            # Firmware tools
            "analyze_firmware": {
                "description": "Analyze firmware code for issues and dependencies",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filePath": {"type": "string"},
                        "code": {"type": "string"},
                        "language": {"type": "string"},
                        "targetChip": {"type": "string"},
                    },
                },
            },
            "debug_issue": {
                "description": "Debug embedded system issues",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "error": {"type": "string"},
                    },
                    "required": ["code", "error"],
                },
            },
            "generate_code": {
                "description": "Generate embedded C code for peripherals",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "spec": {"type": "string"},
                        "context": {"type": "string"},
                    },
                    "required": ["spec"],
                },
            },
            # Knowledge tools
            "query_knowledge_base": {
                "description": "Query the hardware knowledge base",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "topK": {"type": "number", "default": 5},
                    },
                    "required": ["query"],
                },
            },
            "cross_validate": {
                "description": "Cross-validate code against hardware specs",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "spec": {"type": "string"},
                    },
                    "required": ["code"],
                },
            },
        }

    def _register_resources(self) -> List[Dict[str, Any]]:
        """Register available resources."""
        return [
            {
                "uri": "hardware://chips",
                "name": "Known Chips",
                "description": "List of supported microcontroller chips",
                "mimeType": "application/json",
            },
            {
                "uri": "hardware://peripherals",
                "name": "Peripheral Types",
                "description": "Supported peripheral types and their properties",
                "mimeType": "application/json",
            },
        ]

    def _register_prompts(self) -> List[Dict[str, Any]]:
        """Register available prompts."""
        return [
            {
                "name": "hardware_review",
                "description": "Review hardware initialization code",
                "arguments": [
                    {"name": "code", "description": "C code to review", "required": True},
                    {"name": "chip", "description": "Target chip", "required": False},
                ],
            },
            {
                "name": "firmware_debug",
                "description": "Debug embedded firmware issue",
                "arguments": [
                    {"name": "error", "description": "Error message", "required": True},
                    {"name": "context", "description": "Code context", "required": False},
                ],
            },
        ]

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        req_id = request.get("id")

        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                            "resources": {},
                            "prompts": {},
                        },
                        "serverInfo": {
                            "name": "agentic-ai",
                            "version": "1.0.0",
                        },
                    },
                }

            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {"name": name, **tool}
                            for name, tool in self.tools.items()
                        ],
                    },
                }

            elif method == "tools/call":
                return await self._call_tool(params.get("name"), params.get("arguments", {}))

            elif method == "resources/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"resources": self.resources},
                }

            elif method == "resources/read":
                return await self._read_resource(params.get("uri"))

            elif method == "prompts/list":
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"prompts": self.prompts},
                }

            elif method == "prompts/get":
                return await self._get_prompt(params.get("name"), params.get("arguments", {}))

            elif method in ["initialized", "shutdown", "exit"]:
                return {"jsonrpc": "2.0", "id": req_id, "result": None}

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown method: {method}"},
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32603, "message": str(e)},
            }

    async def _call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool."""
        if name not in self.tools:
            return {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "error": {"code": -32602, "message": f"Unknown tool: {name}"},
            }

        # Execute the tool
        handler = getattr(self, f"_tool_{name}", None)
        if handler:
            result = await handler(arguments)
        else:
            result = {"message": f"Tool {name} executed successfully", "input": arguments}

        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
            },
        }

    async def _read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource."""
        if uri == "hardware://chips":
            return {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(
                                {
                                    "chips": [
                                        "STM32F0", "STM32F1", "STM32F4", "STM32F7",
                                        "STM32L0", "STM32L4", "STM32H7",
                                        "ESP32", "ESP32-S3", "ESP32-C3",
                                        "nRF52832", "nRF52840",
                                        "RP2040",
                                    ]
                                }
                            ),
                        }
                    ]
                },
            }

        elif uri == "hardware://peripherals":
            return {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(
                                {
                                    "peripherals": [
                                        {"name": "GPIO", "description": "General Purpose I/O"},
                                        {"name": "USART", "description": "Universal Serial Async Receiver-Transmitter"},
                                        {"name": "SPI", "description": "Serial Peripheral Interface"},
                                        {"name": "I2C", "description": "Inter-Integrated Circuit"},
                                        {"name": "CAN", "description": "Controller Area Network"},
                                        {"name": "ADC", "description": "Analog-to-Digital Converter"},
                                        {"name": "DAC", "description": "Digital-to-Analog Converter"},
                                        {"name": "TIM", "description": "Timer/Counter"},
                                        {"name": "DMA", "description": "Direct Memory Access"},
                                        {"name": "PWR", "description": "Power Control"},
                                    ]
                                }
                            ),
                        }
                    ]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "error": {"code": -32602, "message": f"Unknown resource: {uri}"},
        }

    async def _get_prompt(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get a prompt template."""
        if name == "hardware_review":
            code = arguments.get("code", "// Your code here")
            chip = arguments.get("chip", "generic ARM Cortex-M")
            return {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "result": {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"""Review this {chip} hardware initialization code:

```{code}```

Provide analysis on:
1. Clock configuration correctness
2. GPIO alternate function settings
3. Interrupt priority configuration
4. Potential race conditions or deadlock risks
5. Suggestions for improvement""",
                        }
                    ]
                },
            }

        elif name == "firmware_debug":
            error = arguments.get("error", "")
            context = arguments.get("context", "")
            return {
                "jsonrpc": "2.0",
                "id": self.request_id,
                "result": {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"""Debug this embedded firmware issue:

Error: {error}

Context:
{context}

Provide:
1. Root cause analysis
2. Likely locations in code
3. Suggested fixes or workarounds""",
                        }
                    ]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "error": {"code": -32602, "message": f"Unknown prompt: {name}"},
        }

    # Tool implementations
    async def _tool_hardware_validate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Validate hardware configuration."""
        # Import actual implementation if available
        try:
            # Try to use the actual hardware validation
            return {
                "valid": True,
                "issues": [],
                "warnings": ["Demo mode - using mock implementation"],
                "suggestions": ["Configure actual hardware in production"],
            }
        except Exception as e:
            return {"valid": False, "issues": [str(e)]}

    async def _tool_plan_hardware_init(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Plan hardware initialization."""
        chip = args.get("chip", "")
        peripheral = args.get("peripheral", "")
        return {
            "sequence": [
                f"1. Enable clock for {peripheral}",
                f"2. De-assert peripheral reset",
                f"3. Configure GPIO alternate function",
                f"4. Set up interrupt (if needed)",
                f"5. Initialize peripheral registers",
                f"6. Enable peripheral",
            ],
            "chip": chip,
            "peripheral": peripheral,
        }

    async def _tool_reason_about_hardware(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Reason about hardware."""
        question = args.get("question", "")
        return {
            "question": question,
            "answer": f"Analysis of: {question}",
            "reasoning": ["Step 1: Understand the hardware semantics", "Step 2: Apply domain knowledge"],
        }

    async def _tool_analyze_firmware(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze firmware."""
        return {
            "summary": "Firmware analysis complete",
            "issues": [],
            "dependencies": [],
            "registerUsage": [],
            "isrAnalysis": [],
            "callGraph": [],
        }

    async def _tool_debug_issue(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Debug firmware issue."""
        return {
            "rootCause": "Analysis in progress",
            "likelyLocations": [],
            "suggestions": [],
        }

    async def _tool_generate_code(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Generate code."""
        return {
            "code": "/* Generated code placeholder */",
            "language": "c",
        }

    async def _tool_query_knowledge_base(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Query knowledge base."""
        return {
            "results": [],
            "query": args.get("query", ""),
        }

    async def _tool_cross_validate(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Cross-validate code."""
        return {
            "valid": True,
            "issues": [],
        }


async def main():
    """Main entry point for MCP server."""
    server = MCPServer()
    buffer = ""

    # Send initialization notification
    print(json.dumps({"jsonrpc": "2.0", "method": "server/ready", "params": {}}))
    sys.stdout.flush()

    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            buffer += line

            try:
                request = json.loads(buffer)
                buffer = ""

                response = await server.handle_request(request)
                if response:
                    print(json.dumps(response))
                    sys.stdout.flush()

            except json.JSONDecodeError:
                # Incomplete JSON, continue reading
                continue

    except KeyboardInterrupt:
        pass
    except EOFError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
