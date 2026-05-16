"""Dashboard-specific REST API endpoints."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import Query

from src.application.api.app.api_state import state
from src.infrastructure.metrics.collector import get_metrics_collector

logger = logging.getLogger(__name__)


# ============================================================================
# DASHBOARD OVERVIEW
# ============================================================================

async def get_dashboard_overview() -> Dict[str, Any]:
    """Get dashboard overview data."""
    collector = get_metrics_collector()
    
    return {
        "system": {
            "agent_initialized": state.agent is not None,
            "uptime_seconds": state.uptime,
            "uptime_human": _format_uptime(state.uptime),
            "task_count": state.task_count,
            "success_count": state.success_count,
            "error_count": state.error_count,
            "success_rate": _calc_success_rate(state.task_count, state.success_count, state.error_count),
        },
        "resources": {
            "cpu": state._metrics.get("cpu", 0.0),
            "memory": state._metrics.get("memory", 0.0),
            "speed": state._metrics.get("speed", 0.0),
            "temperature": state._metrics.get("temperature", 0.0),
        },
        "workflow": {
            "active": 0,
            "queued": state.task_count,
            "completed": state.success_count,
            "failed": state.error_count,
        },
        "timestamp": datetime.now().isoformat(),
    }


async def get_system_health() -> Dict[str, Any]:
    """Get detailed system health metrics."""
    collector = get_metrics_collector()
    
    cpu_stats = collector.get_histogram_stats("cpu_usage")
    memory_stats = collector.get_histogram_stats("memory_usage")
    
    return {
        "overall": "healthy",
        "checks": {
            "agent": {"status": "up" if state.agent else "down", "latency_ms": 0},
            "metrics": {"status": "up", "count": len(collector._gauges)},
            "websocket": {"status": "up", "connections": len(state.websocket_connections)},
            "logs": {"status": "up", "buffer_size": len(state.logs)},
        },
        "alerts": _check_health_alerts(state._metrics),
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# WORKFLOW STATUS
# ============================================================================

async def get_workflow_status() -> Dict[str, Any]:
    """Get current workflow statuses."""
    return {
        "workflows": _get_workflow_states(),
        "total": len(state.logs),
        "timestamp": datetime.now().isoformat(),
    }


async def get_workflow_history(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Dict[str, Any]:
    """Get workflow execution history."""
    logs = list(reversed(state.logs))
    
    return {
        "workflows": [
            {
                "id": f"wf-{i:04d}",
                "timestamp": log.timestamp,
                "level": log.level,
                "source": log.source,
                "message": log.message,
            }
            for i, log in enumerate(logs[offset:offset + limit])
        ],
        "total": len(logs),
        "limit": limit,
        "offset": offset,
    }


# ============================================================================
# ROLLBACK ANALYSIS
# ============================================================================

async def get_rollback_events(
    limit: int = Query(default=20, ge=1, le=100),
) -> Dict[str, Any]:
    """Get rollback events and reasons."""
    rollback_keywords = ["rollback", "revert", "fail", "error", "abort"]
    
    rollback_logs = [
        log for log in state.logs
        if any(kw in log.message.lower() for kw in rollback_keywords)
    ][-limit:]
    
    return {
        "events": [
            {
                "timestamp": log.timestamp,
                "source": log.source,
                "level": log.level,
                "message": log.message,
                "reason": _extract_rollback_reason(log.message),
            }
            for log in rollback_logs
        ],
        "count": len(rollback_logs),
    }


# ============================================================================
# TOKEN BUDGET & USAGE
# ============================================================================

async def get_token_usage() -> Dict[str, Any]:
    """Get token usage statistics."""
    collector = get_metrics_collector()
    
    return {
        "current_session": {
            "input_tokens": collector.get_counter("tokens.input"),
            "output_tokens": collector.get_counter("tokens.output"),
            "total_tokens": collector.get_counter("tokens.input") + collector.get_counter("tokens.output"),
        },
        "limits": {
            "daily_limit": 1000000,
            "monthly_limit": 30000000,
        },
        "costs": {
            "estimated": _estimate_token_cost(collector),
        },
        "history_24h": _get_token_history(collector),
        "timestamp": datetime.now().isoformat(),
    }


async def get_context_usage() -> Dict[str, Any]:
    """Get context window usage."""
    collector = get_metrics_collector()
    
    return {
        "current": {
            "used_tokens": collector.get_counter("context.used"),
            "max_tokens": 128000,
            "usage_percent": 0.0,
        },
        "by_phase": {
            "P0_bootstrap": collector.get_counter("context.P0"),
            "P1_planning": collector.get_counter("context.P1"),
            "P2_analysis": collector.get_counter("context.P2"),
            "P3_implementation": collector.get_counter("context.P3"),
            "P4_validation": collector.get_counter("context.P4"),
        },
        "timestamp": datetime.now().isoformat(),
    }


# ============================================================================
# HARDWARE STATUS (HIL)
# ============================================================================

async def get_hardware_status() -> Dict[str, Any]:
    """Get hardware/HIL board status."""
    return {
        "connected": False,
        "boards": [],
        "uart_streams": [],
        "last_update": datetime.now().isoformat(),
        "mock_mode": True,
    }


# ============================================================================
# EVENT TIMELINE
# ============================================================================

async def get_event_timeline(
    limit: int = Query(default=100, ge=1, le=500),
    level: Optional[str] = Query(default=None, pattern="^(debug|info|warn|error)$"),
) -> Dict[str, Any]:
    """Get event timeline for activity stream."""
    logs = state.logs
    
    if level:
        logs = [l for l in logs if l.level == level]
    
    logs = logs[-limit:]
    
    return {
        "events": [
            {
                "id": f"evt-{i:06d}",
                "timestamp": log.timestamp,
                "level": log.level,
                "source": log.source,
                "message": log.message,
                "type": _classify_event(log),
            }
            for i, log in enumerate(logs)
        ],
        "total": len(logs),
        "by_level": {
            "debug": len([l for l in logs if l.level == "debug"]),
            "info": len([l for l in logs if l.level == "info"]),
            "warn": len([l for l in logs if l.level == "warn"]),
            "error": len([l for l in logs if l.level == "error"]),
        },
    }


# ============================================================================
# METRICS EXPORT (Prometheus-compatible)
# ============================================================================

async def get_prometheus_metrics() -> str:
    """Export metrics in Prometheus format."""
    collector = get_metrics_collector()
    
    lines = []
    
    for name, value in collector._counters.items():
        lines.append(f'# TYPE {name} counter')
        lines.append(f'{name} {value}')
    
    for name, value in collector._gauges.items():
        lines.append(f'# TYPE {name} gauge')
        lines.append(f'{name} {value}')
    
    for name, values in collector._histograms.items():
        if values:
            lines.append(f'# TYPE {name} histogram')
            avg = sum(values) / len(values)
            lines.append(f'{name}_sum {avg * len(values)}')
            lines.append(f'{name}_count {len(values)}')
    
    lines.append(f'ai_support_uptime_seconds {state.uptime}')
    lines.append(f'ai_support_tasks_total {state.task_count}')
    lines.append(f'ai_support_tasks_success {state.success_count}')
    lines.append(f'ai_support_tasks_error {state.error_count}')
    
    return "\n".join(lines) + "\n"


# ============================================================================
# CALL GRAPH
# ============================================================================

async def get_call_graph(
    entry_point: Optional[str] = Query(default=None, description="Entry point function to analyze"),
    max_depth: int = Query(default=3, ge=1, le=5, description="Maximum depth for call graph traversal"),
    project_root: Optional[str] = Query(default=None, description="Project root path (defaults to software/main)"),
) -> Dict[str, Any]:
    """
    Get call graph data for the firmware project.
    
    This endpoint provides the call graph visualization data used by the
    Trust & UX dashboard to display function dependencies.
    """
    from src.domains.knowledge.call_graph_fast import CallGraphAnalyzer
    
    # Default to main/software project
    if project_root is None:
        # Try to find the software directory
        repo_root = Path(__file__).resolve().parents[3]
        candidate = repo_root / "main" / "software"
        if candidate.exists():
            project_root = str(candidate)
        else:
            project_root = str(repo_root)
    
    try:
        analyzer = CallGraphAnalyzer(project_root)
        graph = analyzer.build()
        
        # Convert to frontend format
        functions = {}
        for name, node in graph.functions.items():
            functions[name] = {
                "name": node.name,
                "file": node.file,
                "callees": node.callees,
                "callers": node.callers,
            }
        
        # Filter entry points if specified
        entry_points = graph.entry_points
        if entry_point:
            if entry_point in functions:
                entry_points = [entry_point]
            else:
                entry_points = [ep for ep in entry_points if entry_point.lower() in ep.lower()]
        
        return {
            "entry_points": entry_points,
            "functions": functions,
            "total_functions": len(functions),
            "orphaned_count": len(graph.orphaned_functions),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Call graph analysis failed: {e}")
        return {
            "entry_points": [],
            "functions": {},
            "total_functions": 0,
            "orphaned_count": 0,
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _format_uptime(seconds: float) -> str:
    """Format uptime in human-readable format."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        mins = int((seconds % 3600) // 60)
        return f"{hours}h {mins}m"
    else:
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        return f"{days}d {hours}h"


def _calc_success_rate(total: int, success: int, errors: int) -> float:
    """Calculate success rate percentage."""
    if total == 0:
        return 100.0
    return round((success / total) * 100, 2)


def _check_health_alerts(metrics: Dict[str, float]) -> List[Dict[str, Any]]:
    """Check for health alerts."""
    alerts = []
    
    if metrics.get("cpu", 0) > 90:
        alerts.append({"level": "critical", "metric": "cpu", "value": metrics["cpu"], "message": "CPU usage critical"})
    elif metrics.get("cpu", 0) > 75:
        alerts.append({"level": "warning", "metric": "cpu", "value": metrics["cpu"], "message": "CPU usage high"})
    
    if metrics.get("memory", 0) > 90:
        alerts.append({"level": "critical", "metric": "memory", "value": metrics["memory"], "message": "Memory usage critical"})
    elif metrics.get("memory", 0) > 80:
        alerts.append({"level": "warning", "metric": "memory", "value": metrics["memory"], "message": "Memory usage high"})
    
    if metrics.get("temperature", 0) > 80:
        alerts.append({"level": "critical", "metric": "temperature", "value": metrics["temperature"], "message": "Temperature critical"})
    elif metrics.get("temperature", 0) > 70:
        alerts.append({"level": "warning", "metric": "temperature", "value": metrics["temperature"], "message": "Temperature high"})
    
    return alerts


def _get_workflow_states() -> List[Dict[str, Any]]:
    """Get workflow states from logs."""
    states = []
    
    for log in reversed(state.logs[-50:]):
        if "starting" in log.message.lower():
            states.append({"state": "running", "source": log.source, "timestamp": log.timestamp})
        elif "completed" in log.message.lower():
            states.append({"state": "completed", "source": log.source, "timestamp": log.timestamp})
        elif "error" in log.level or "fail" in log.message.lower():
            states.append({"state": "failed", "source": log.source, "timestamp": log.timestamp})
    
    return states[-10:]


def _extract_rollback_reason(message: str) -> str:
    """Extract rollback reason from message."""
    reasons = {
        "compilation": "Compilation failed",
        "test": "Test assertion failed",
        "timeout": "Operation timed out",
        "memory": "Memory limit exceeded",
        "dependency": "Dependency conflict",
    }
    
    msg_lower = message.lower()
    for key, reason in reasons.items():
        if key in msg_lower:
            return reason
    
    return "Unknown reason"


def _estimate_token_cost(collector) -> Dict[str, float]:
    """Estimate token costs."""
    input_tokens = collector.get_counter("tokens.input")
    output_tokens = collector.get_counter("tokens.output")
    
    cost_per_1k_input = 0.0001
    cost_per_1k_output = 0.0003
    
    return {
        "input_cost": round(input_tokens / 1000 * cost_per_1k_input, 6),
        "output_cost": round(output_tokens / 1000 * cost_per_1k_output, 6),
        "total_cost": round((input_tokens / 1000 * cost_per_1k_input) + (output_tokens / 1000 * cost_per_1k_output), 6),
    }


def _get_token_history(collector) -> List[Dict[str, Any]]:
    """Get token usage history for last 24 hours."""
    time_series = collector.get_time_series("tokens.total", window=timedelta(hours=24))
    
    return [
        {
            "timestamp": point.timestamp.isoformat(),
            "value": point.value,
        }
        for point in time_series[-24:]
    ]


def _classify_event(log) -> str:
    """Classify event type from log entry."""
    msg_lower = log.message.lower()
    
    if "task" in msg_lower and "start" in msg_lower:
        return "task_start"
    elif "task" in msg_lower and ("complet" in msg_lower or "done" in msg_lower):
        return "task_complete"
    elif log.level == "error" or "fail" in msg_lower:
        return "error"
    elif "rollback" in msg_lower or "revert" in msg_lower:
        return "rollback"
    elif log.level == "warn":
        return "warning"
    else:
        return "info"
