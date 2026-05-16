"""Runtime configuration for tool execution (Phase 2B/2C).

Configuration schema for tool execution parameters including
concurrency limits, timeouts, history retention, and Phase 2C middleware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class RetryConfig:
    """Configuration for retry middleware.

    Attributes:
        max_attempts: Maximum number of retry attempts.
        base_delay_seconds: Base delay between retries.
        max_delay_seconds: Maximum delay cap.
        retryable_codes: Error codes that should trigger retry.
        jitter_factor: Random jitter factor (0.0 to 1.0).
    """

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    retryable_codes: list[str] = field(
        default_factory=lambda: ["MCP_ERROR", "TIMEOUT"]
    )
    jitter_factor: float = 0.1


@dataclass
class RateLimitRule:
    """Single rate limit rule.

    Attributes:
        calls: Maximum calls allowed.
        period: Time window in seconds.
    """

    calls: int = 10
    period: float = 60.0


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting.

    Attributes:
        per_session: Default per-session rate limit.
        per_tool: Per-tool rate limit overrides.
    """

    per_session: RateLimitRule = field(default_factory=lambda: RateLimitRule(calls=10, period=60.0))
    per_tool: dict[str, RateLimitRule] = field(default_factory=dict)


@dataclass
class CancellationConfig:
    """Configuration for cancellation.

    Attributes:
        grace_period_seconds: Grace period before force cleanup.
    """

    grace_period_seconds: float = 2.0


@dataclass
class ToolExecutionConfig:
    """Configuration for tool execution runtime.

    Phase 2C extends with middleware, retry, rate limiting, and cancellation config.

    Attributes:
        default_timeout_seconds: Default timeout for tool execution.
        max_concurrent_tools_per_session: Max concurrent tool calls per session.
        max_pending_calls_per_session: Max pending calls before backpressure.
        max_history_per_session: Max completed calls to retain in history.
        enable_trace_id: Whether to generate trace IDs for observability.
        retry: Retry policy configuration.
        rate_limits: Rate limit configuration.
        cancellation: Cancellation configuration.
        middleware_order: Ordered list of middleware names.
    """

    default_timeout_seconds: float = 30.0
    max_concurrent_tools_per_session: int = 5
    max_pending_calls_per_session: int = 20
    max_history_per_session: int = 100
    enable_trace_id: bool = True
    retry: RetryConfig = field(default_factory=RetryConfig)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    cancellation: CancellationConfig = field(default_factory=CancellationConfig)
    middleware_order: list[str] = field(
        default_factory=lambda: ["ownership", "rate_limit", "retry", "cancellation", "audit"]
    )

    @classmethod
    def from_dict(cls, data: dict) -> ToolExecutionConfig:
        """Create config from dictionary.

        Args:
            data: Configuration dictionary.

        Returns:
            ToolExecutionConfig instance.
        """
        retry_data = data.get("retry", {})
        retry_config = RetryConfig(
            max_attempts=retry_data.get("max_attempts", 3),
            base_delay_seconds=retry_data.get("base_delay_seconds", 1.0),
            max_delay_seconds=retry_data.get("max_delay_seconds", 30.0),
            retryable_codes=retry_data.get("retryable_codes", ["MCP_ERROR", "TIMEOUT"]),
            jitter_factor=retry_data.get("jitter_factor", 0.1),
        )

        rate_limits_data = data.get("rate_limits", {})
        per_session_data = rate_limits_data.get("per_session", {})
        per_session = RateLimitRule(
            calls=per_session_data.get("calls", 10),
            period=per_session_data.get("period", 60.0),
        )
        per_tool = {}
        for tool_name, tool_data in rate_limits_data.get("per_tool", {}).items():
            per_tool[tool_name] = RateLimitRule(
                calls=tool_data.get("calls", 30),
                period=tool_data.get("period", 60.0),
            )
        rate_limit_config = RateLimitConfig(
            per_session=per_session,
            per_tool=per_tool,
        )

        cancellation_data = data.get("cancellation", {})
        cancellation_config = CancellationConfig(
            grace_period_seconds=cancellation_data.get("grace_period_seconds", 2.0),
        )

        middleware_order = data.get(
            "middleware_order",
            ["ownership", "rate_limit", "retry", "cancellation", "audit"]
        )

        return cls(
            default_timeout_seconds=data.get("default_timeout_seconds", 30.0),
            max_concurrent_tools_per_session=data.get(
                "max_concurrent_tools_per_session", 5
            ),
            max_pending_calls_per_session=data.get(
                "max_pending_calls_per_session", 20
            ),
            max_history_per_session=data.get("max_history_per_session", 100),
            enable_trace_id=data.get("enable_trace_id", True),
            retry=retry_config,
            rate_limits=rate_limit_config,
            cancellation=cancellation_config,
            middleware_order=middleware_order,
        )

    def to_dict(self) -> dict:
        """Convert config to dictionary.

        Returns:
            Configuration as dictionary.
        """
        return {
            "default_timeout_seconds": self.default_timeout_seconds,
            "max_concurrent_tools_per_session": self.max_concurrent_tools_per_session,
            "max_pending_calls_per_session": self.max_pending_calls_per_session,
            "max_history_per_session": self.max_history_per_session,
            "enable_trace_id": self.enable_trace_id,
            "retry": {
                "max_attempts": self.retry.max_attempts,
                "base_delay_seconds": self.retry.base_delay_seconds,
                "max_delay_seconds": self.retry.max_delay_seconds,
                "retryable_codes": self.retry.retryable_codes,
                "jitter_factor": self.retry.jitter_factor,
            },
            "rate_limits": {
                "per_session": {
                    "calls": self.rate_limits.per_session.calls,
                    "period": self.rate_limits.per_session.period,
                },
                "per_tool": {
                    tool_name: {"calls": rule.calls, "period": rule.period}
                    for tool_name, rule in self.rate_limits.per_tool.items()
                },
            },
            "cancellation": {
                "grace_period_seconds": self.cancellation.grace_period_seconds,
            },
            "middleware_order": self.middleware_order,
        }


def load_runtime_config(config_dir: str | Path = "configs/runtime") -> dict:
    """Load runtime configuration from YAML file.

    Args:
        config_dir: Directory containing runtime configuration files.

    Returns:
        Dictionary of runtime configuration.

    Raises:
        FileNotFoundError: If config file doesn't exist.
        Exception: If YAML parsing fails.
    """
    import yaml

    config_path = Path(config_dir) / "server.yaml"

    if not config_path.exists():
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_tool_execution_config(
    config_dir: str | Path = "configs/runtime",
) -> ToolExecutionConfig:
    """Get tool execution configuration.

    Args:
        config_dir: Directory containing runtime configuration files.

    Returns:
        ToolExecutionConfig instance with defaults applied.
    """
    config = load_runtime_config(config_dir)
    tool_exec = config.get("tool_execution", {})
    return ToolExecutionConfig.from_dict(tool_exec)
