"""Semantic tool router for intelligent tool selection (Phase 10.2).

Provides:
- Semantic similarity-based tool matching
- Tool capability matching
- Automatic tool recommendation
- Tool performance tracking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolCapability:
    """Tool capability descriptor."""
    name: str
    description: str
    keywords: list[str]
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ToolMatch:
    """Tool matching result."""
    tool_name: str
    confidence: float  # 0.0 - 1.0
    reason: str = ""
    capabilities: list[str] = field(default_factory=list)


class SemanticToolRouter:
    """Semantic routing for tool selection.
    
    Phase 10.2: Semantic router - chọn tool nhanh dựa trên semantic similarity
    """
    
    def __init__(self) -> None:
        self._tools: dict[str, ToolCapability] = {}
        self._usage_stats: dict[str, dict[str, Any]] = {}
    
    def register_tool(self, capability: ToolCapability) -> None:
        """Register a tool with its capabilities."""
        self._tools[capability.name] = capability
        self._usage_stats[capability.name] = {
            "total_uses": 0,
            "successes": 0,
            "failures": 0,
            "avg_latency_ms": 0,
        }
        logger.info("Registered tool", name=capability.name)
    
    def route(
        self,
        query: str,
        context: dict[str, Any] | None = None,
        top_k: int = 3,
    ) -> list[ToolMatch]:
        """Route query to best matching tools."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        matches: list[ToolMatch] = []
        
        for tool_name, capability in self._tools.items():
            score = 0.0
            matched_capabilities: list[str] = []
            
            # Check keywords
            for kw in capability.keywords:
                if kw.lower() in query_lower:
                    score += 0.3
                    matched_capabilities.append(kw)
            
            # Check tags
            for tag in capability.tags:
                if tag.lower() in query_lower:
                    score += 0.2
                if tag in query_words:
                    score += 0.1
            
            # Check description (lower weight)
            if capability.description:
                desc_words = set(capability.description.lower().split())
                overlap = query_words & desc_words
                score += len(overlap) * 0.05
            
            # Context boosting
            if context:
                if context.get("hardware") in capability.tags:
                    score += 0.2
                if context.get("language") in capability.tags:
                    score += 0.1
            
            # Normalize score
            max_possible = 0.3 * len(capability.keywords) + 0.2 * len(capability.tags)
            if max_possible > 0:
                score = min(1.0, score / max_possible * 2)
            
            if score > 0.1:
                matches.append(ToolMatch(
                    tool_name=tool_name,
                    confidence=score,
                    reason=f"Matched: {', '.join(matched_capabilities) or 'semantic similarity'}",
                    capabilities=matched_capabilities,
                ))
        
        # Sort by confidence
        matches.sort(key=lambda m: m.confidence, reverse=True)
        
        return matches[:top_k]
    
    def record_usage(
        self,
        tool_name: str,
        success: bool,
        latency_ms: float,
    ) -> None:
        """Record tool usage statistics."""
        if tool_name not in self._usage_stats:
            self._usage_stats[tool_name] = {
                "total_uses": 0,
                "successes": 0,
                "failures": 0,
                "avg_latency_ms": 0,
            }
        
        stats = self._usage_stats[tool_name]
        stats["total_uses"] += 1
        
        if success:
            stats["successes"] += 1
        else:
            stats["failures"] += 1
        
        # Rolling average
        n = stats["total_uses"]
        stats["avg_latency_ms"] = (
            (stats["avg_latency_ms"] * (n - 1) + latency_ms) / n
        )
    
    def get_tool_stats(self, tool_name: str) -> dict[str, Any] | None:
        """Get tool usage statistics."""
        return self._usage_stats.get(tool_name)
    
    def suggest_tool(
        self,
        task: str,
        available_tools: list[str],
    ) -> str | None:
        """Suggest best tool for task from available options."""
        matches = self.route(task, top_k=len(available_tools))
        
        for match in matches:
            if match.tool_name in available_tools:
                return match.tool_name
        
        return available_tools[0] if available_tools else None


# Global singleton
_semantic_router: SemanticToolRouter | None = None


def get_semantic_router() -> SemanticToolRouter:
    """Get global semantic router instance."""
    global _semantic_router
    if _semantic_router is None:
        _semantic_router = SemanticToolRouter()
    return _semantic_router


# Pre-defined tool capabilities
TOOL_CAPABILITIES: list[ToolCapability] = [
    ToolCapability(
        name="gdb_debug",
        description="Debug ARM Cortex-M firmware via GDB",
        keywords=["debug", "gdb", "breakpoint", "watch", "step", "backtrace"],
        tags=["debug", "arm", "cortex", "gdb"],
    ),
    ToolCapability(
        name="flash_binary",
        description="Flash firmware binary to target via J-Link/ST-Link",
        keywords=["flash", "upload", "program", "jlink", "stlink"],
        tags=["flash", "hardware", "upload"],
    ),
    ToolCapability(
        name="serial_monitor",
        description="Monitor UART/serial output from firmware",
        keywords=["uart", "serial", "console", "log", "monitor"],
        tags=["monitor", "uart", "serial"],
    ),
    ToolCapability(
        name="memory_read",
        description="Read memory from target via debug probe",
        keywords=["memory", "read", "ram", "flash", "register"],
        tags=["memory", "hardware", "read"],
    ),
    ToolCapability(
        name="reset_target",
        description="Reset target MCU",
        keywords=["reset", "reboot", "halt", "run"],
        tags=["reset", "hardware", "control"],
    ),
    ToolCapability(
        name="svd_parse",
        description="Parse SVD files for peripheral register definitions",
        keywords=["svd", "register", "peripheral", "cmsis"],
        tags=["svd", "register", "parse"],
    ),
    ToolCapability(
        name="coredump_parse",
        description="Parse ARM core dump files",
        keywords=["coredump", "crash", "fault", "stack"],
        tags=["crash", "analysis", "dump"],
    ),
    ToolCapability(
        name="build_firmware",
        description="Build firmware from source",
        keywords=["build", "compile", "make", "cmake"],
        tags=["build", "compile"],
    ),
    ToolCapability(
        name="test_runner",
        description="Run firmware tests",
        keywords=["test", "unity", "gtest", "pytest"],
        tags=["test", "qa"],
    ),
    ToolCapability(
        name="patch_analyze",
        description="Analyze code patches",
        keywords=["patch", "diff", "git", "change"],
        tags=["patch", "git", "analyze"],
    ),
]


def init_semantic_router() -> SemanticToolRouter:
    """Initialize semantic router with default tool capabilities."""
    router = get_semantic_router()
    for cap in TOOL_CAPABILITIES:
        router.register_tool(cap)
    return router
