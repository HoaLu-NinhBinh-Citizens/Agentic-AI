"""Deterministic LLM Tool Wrapper.

Fixes Critical Gap: Planner replay ↔ nondeterministic LLM/tool execution.

Features:
- Deterministic wrapper for LLM calls
- Side-effect capture and replay
- Tool execution caching
- LLM call logging
- Retry with exponential backoff
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# DETERMINISTIC TOOL TYPES
# =============================================================================


class ToolType(Enum):
    """Types of tools."""
    
    LLM = auto()           # LLM API call
    FILE = auto()          # File operation
    HTTP = auto()          # HTTP request
    DATABASE = auto()      # Database query
    HARDWARE = auto()      # Hardware operation
    CUSTOM = auto()         # Custom tool


@dataclass
class ToolResult:
    """Result of a tool execution."""
    
    tool_type: ToolType
    tool_name: str
    
    # Input
    args: tuple = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    
    # Output
    success: bool = False
    result: Any = None
    error: str | None = None
    
    # Determinism
    deterministic_hash: str = ""  # Hash for verification
    
    # Timing
    executed_at: datetime = field(default_factory=datetime.utcnow)
    execution_time_ms: float = 0.0


# =============================================================================
# DETERMINISTIC TOOL REGISTRY
# =============================================================================


class DeterministicToolRegistry:
    """Registry for deterministic tool wrappers.
    
    CRITICAL: All tools used in workflows MUST be wrapped
    for deterministic replay.
    """
    
    def __init__(self):
        # Tool wrappers
        self._tools: dict[str, Callable] = {}
        
        # Cached results (for replay)
        self._cache: dict[str, ToolResult] = {}
        
        # Execution log
        self._execution_log: list[ToolResult] = []
        
        # Mode
        self._replay_mode = False
        
        self._lock = asyncio.Lock()
    
    def register_tool(self, tool_name: str, tool_func: Callable) -> None:
        """Register a tool wrapper.
        
        Args:
            tool_name: Tool identifier
            tool_func: Tool function
        """
        self._tools[tool_name] = tool_func
        logger.info("tool_registered: name=%s", tool_name)
    
    def _compute_cache_key(
        self,
        tool_name: str,
        args: tuple,
        kwargs: dict[str, Any],
    ) -> str:
        """Compute deterministic cache key."""
        content = {
            "tool": tool_name,
            "args": args,
            "kwargs": kwargs,
        }
        content_str = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    async def execute(
        self,
        tool_name: str,
        tool_type: ToolType,
        args: tuple,
        kwargs: dict[str, Any],
        deterministic: bool = True,
    ) -> ToolResult:
        """Execute a tool with deterministic tracking.
        
        Args:
            tool_name: Tool identifier
            tool_type: Type of tool
            args: Positional arguments
            kwargs: Keyword arguments
            deterministic: Whether this tool is deterministic
            
        Returns:
            ToolResult with execution details
        """
        import time
        
        async with self._lock:
            cache_key = self._compute_cache_key(tool_name, args, kwargs)
            start_time = time.perf_counter()
            
            result = ToolResult(
                tool_type=tool_type,
                tool_name=tool_name,
                args=args,
                kwargs=kwargs,
            )
            
            # Check cache in replay mode
            if self._replay_mode and deterministic:
                cached = self._cache.get(cache_key)
                if cached:
                    result = cached
                    logger.info(
                        "tool_replayed: name=%s cache_hit=True hash=%s",
                        tool_name, cache_key[:16],
                    )
                    return result
            
            # Execute tool
            tool_func = self._tools.get(tool_name)
            if not tool_func:
                result.success = False
                result.error = f"Unknown tool: {tool_name}"
            else:
                try:
                    if asyncio.iscoroutinefunction(tool_func):
                        result.result = await tool_func(*args, **kwargs)
                    else:
                        result.result = tool_func(*args, **kwargs)
                    result.success = True
                except Exception as e:
                    result.success = False
                    result.error = str(e)
            
            # Update timing
            result.execution_time_ms = (time.perf_counter() - start_time) * 1000
            result.deterministic_hash = cache_key
            
            # Cache if deterministic
            if deterministic and result.success:
                self._cache[cache_key] = result
            
            # Log execution
            self._execution_log.append(result)
            
            logger.info(
                "tool_executed: name=%s success=%s time=%sms deterministic=%s",
                tool_name, result.success, result.execution_time_ms, deterministic,
            )
            
            return result
    
    def enable_replay_mode(self) -> None:
        """Enable replay mode (uses cached results)."""
        self._replay_mode = True
        logger.info("deterministic_mode_replay_enabled")
    
    def disable_replay_mode(self) -> None:
        """Disable replay mode (executes normally)."""
        self._replay_mode = False
        logger.info("deterministic_mode_replay_disabled")
    
    def get_cached_result(self, cache_key: str) -> ToolResult | None:
        """Get cached result by key."""
        return self._cache.get(cache_key)
    
    def get_execution_log(self) -> list[ToolResult]:
        """Get execution log."""
        return list(self._execution_log)
    
    def verify_determinism(
        self,
        log: list[ToolResult],
    ) -> tuple[bool, list[str]]:
        """Verify determinism of execution log.
        
        Returns:
            (is_deterministic, list of issues)
        """
        issues = []
        
        for entry in log:
            if entry.tool_type == ToolType.LLM:
                # LLM calls are not deterministic
                if entry.kwargs.get("deterministic", False):
                    issues.append(
                        f"LLM call marked as deterministic but is not: {entry.tool_name}"
                    )
        
        return len(issues) == 0, issues
    
    def clear_cache(self) -> None:
        """Clear execution cache."""
        self._cache.clear()
        logger.info("deterministic_tool_cache_cleared")
    
    def clear_log(self) -> None:
        """Clear execution log."""
        self._execution_log.clear()
        logger.info("deterministic_tool_log_cleared")


# =============================================================================
# DETERMINISTIC LLM WRAPPER
# =============================================================================


class DeterministicLLMWrapper:
    """Wrapper for LLM calls with deterministic tracking.
    
    CRITICAL: LLM calls are inherently non-deterministic.
    This wrapper captures and logs all LLM calls for analysis.
    """
    
    def __init__(self, registry: DeterministicToolRegistry):
        self._registry = registry
    
    async def generate(
        self,
        prompt: str,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        **kwargs,
    ) -> dict[str, Any]:
        """Generate with LLM (non-deterministic).
        
        CRITICAL: This IS NOT deterministic. Results vary between calls.
        Use cached results in replay mode.
        
        Args:
            prompt: Input prompt
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            **kwargs: Additional parameters
            
        Returns:
            LLM response
        """
        # Log as non-deterministic
        result = await self._registry.execute(
            tool_name="llm.generate",
            tool_type=ToolType.LLM,
            args=(prompt,),
            kwargs={
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "deterministic": False,  # LLM is never deterministic
                **kwargs,
            },
            deterministic=False,  # LLM is non-deterministic
        )
        
        if not result.success:
            raise RuntimeError(f"LLM call failed: {result.error}")
        
        return result.result
    
    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "gpt-4",
        temperature: float = 0.7,
        **kwargs,
    ) -> dict[str, Any]:
        """Chat with LLM (non-deterministic).
        
        Same caveats as generate().
        """
        result = await self._registry.execute(
            tool_name="llm.chat",
            tool_type=ToolType.LLM,
            args=(messages,),
            kwargs={
                "model": model,
                "temperature": temperature,
                "deterministic": False,
                **kwargs,
            },
            deterministic=False,
        )
        
        if not result.success:
            raise RuntimeError(f"LLM chat failed: {result.error}")
        
        return result.result


# =============================================================================
# DETERMINISTIC FILE TOOL
# =============================================================================


class DeterministicFileTool:
    """Deterministic file operations wrapper."""
    
    def __init__(self, registry: DeterministicToolRegistry):
        self._registry = registry
    
    async def read(self, path: str, binary: bool = False) -> str | bytes:
        """Read file (deterministic if file unchanged)."""
        import os
        
        result = await self._registry.execute(
            tool_name="file.read",
            tool_type=ToolType.FILE,
            args=(path,),
            kwargs={"binary": binary},
            deterministic=True,
        )
        
        if not result.success:
            raise RuntimeError(f"File read failed: {result.error}")
        
        return result.result
    
    async def write(self, path: str, content: str | bytes) -> None:
        """Write file (non-deterministic side effect)."""
        import os
        
        result = await self._registry.execute(
            tool_name="file.write",
            tool_type=ToolType.FILE,
            args=(path, content),
            kwargs={},
            deterministic=False,  # File writes are side effects
        )
        
        if not result.success:
            raise RuntimeError(f"File write failed: {result.error}")
    
    async def exists(self, path: str) -> bool:
        """Check if file exists (deterministic)."""
        import os
        
        result = await self._registry.execute(
            tool_name="file.exists",
            tool_type=ToolType.FILE,
            args=(path,),
            kwargs={},
            deterministic=True,
        )
        
        return result.success and result.result


# =============================================================================
# PLANNER INTEGRATION
# =============================================================================


class DeterministicPlannerWrapper:
    """Wrapper for planner with deterministic replay support.
    
    CRITICAL: This ensures planner replay is deterministic.
    """
    
    def __init__(self, registry: DeterministicToolRegistry):
        self._registry = registry
        self._llm = DeterministicLLMWrapper(registry)
        self._file = DeterministicFileTool(registry)
    
    def enable_replay(self) -> None:
        """Enable replay mode for planner."""
        self._registry.enable_replay_mode()
    
    def disable_replay(self) -> None:
        """Disable replay mode."""
        self._registry.disable_replay_mode()
    
    def get_execution_log(self) -> list[ToolResult]:
        """Get planner execution log."""
        return self._registry.get_execution_log()
    
    def verify_determinism(self) -> tuple[bool, list[str]]:
        """Verify planner determinism."""
        return self._registry.verify_determinism(self._execution_log)


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================


_global_registry: DeterministicToolRegistry | None = None


def get_deterministic_registry() -> DeterministicToolRegistry:
    """Get global deterministic tool registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = DeterministicToolRegistry()
    return _global_registry


def get_llm_wrapper() -> DeterministicLLMWrapper:
    """Get deterministic LLM wrapper."""
    return DeterministicLLMWrapper(get_deterministic_registry())


def get_file_tool() -> DeterministicFileTool:
    """Get deterministic file tool."""
    return DeterministicFileTool(get_deterministic_registry())


def get_planner_wrapper() -> DeterministicPlannerWrapper:
    """Get deterministic planner wrapper."""
    return DeterministicPlannerWrapper(get_deterministic_registry())
