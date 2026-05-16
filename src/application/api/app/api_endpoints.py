"""REST API endpoints for the CARV API server."""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import BackgroundTasks, HTTPException, Query

from src.application.api.app.api_models import (
    LogEntry,
    MetricUpdate,
    SystemStatus,
    TaskRequest,
    TaskResponse,
    ToolStatus,
)
from src.application.api.app.api_state import state

logger = logging.getLogger(__name__)


def _get_repo_root():
    return Path(__file__).resolve().parents[2]


# ============================================================================
# HEALTH & STATUS
# ============================================================================

async def health_check():
    """Quick health check."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


async def get_status():
    """Get system status."""
    return SystemStatus(
        agent_initialized=state.agent is not None,
        model="llama3.1",
        rag_ready=state.agent is not None,
        uptime_seconds=state.uptime,
        task_count=state.task_count,
        success_count=state.success_count,
        error_count=state.error_count,
    )


# ============================================================================
# METRICS
# ============================================================================

async def get_metrics():
    """Get current metrics snapshot."""
    return {
        "cpu": state._metrics.get("cpu", 0.0),
        "memory": state._metrics.get("memory", 0.0),
        "speed": state._metrics.get("speed", 0.0),
        "temperature": state._metrics.get("temperature", 0.0),
        "timestamp": datetime.now().isoformat(),
    }


async def update_metrics(metrics: MetricUpdate):
    """Update metrics (called by agent internals)."""
    state.update_metrics(metrics.model_dump())
    return {"status": "ok"}


# ============================================================================
# LOGS
# ============================================================================

async def get_logs(
    limit: int = Query(default=100, ge=1, le=500),
    level: Optional[str] = Query(default=None, pattern="^(debug|info|warn|error)$"),
):
    """Get recent logs."""
    logs = state.logs
    if level:
        logs = [l for l in logs if l.level == level]
    return {
        "logs": logs[-limit:],
        "total": len(logs),
    }


async def add_log(entry: LogEntry):
    """Add a log entry."""
    state.add_log(entry.level, entry.source, entry.message)
    return {"status": "ok"}


async def export_logs(
    level: Optional[str] = Query(default=None, pattern="^(debug|info|warn|error)$"),
):
    """Export logs to file and return path."""
    import json

    repo_root = _get_repo_root()
    logs_dir = repo_root / "AI_support" / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"carv_logs_{timestamp}.json"
    filepath = logs_dir / filename

    logs = state.logs
    if level:
        logs = [l for l in logs if l.level == level]

    export_data = {
        "exported_at": datetime.now().isoformat(),
        "total_logs": len(logs),
        "filter": level,
        "logs": [
            {
                "timestamp": log.timestamp,
                "level": log.level,
                "source": log.source,
                "message": log.message,
            }
            for log in logs
        ]
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)

    txt_filename = f"carv_logs_{timestamp}.txt"
    txt_filepath = logs_dir / txt_filename

    with open(txt_filepath, "w", encoding="utf-8") as f:
        f.write(f"CARV Logs Export - {datetime.now().isoformat()}\n")
        f.write(f"Total: {len(logs)} entries\n")
        f.write(f"Filter: {level or 'none'}\n")
        f.write("=" * 60 + "\n\n")
        for log in logs:
            f.write(f"[{log.timestamp}] [{log.level.upper():5}] [{log.source}]\n")
            f.write(f"  {log.message}\n\n")

    return {
        "status": "exported",
        "json_file": str(filepath),
        "txt_file": str(txt_filepath),
        "count": len(logs),
    }


# ============================================================================
# TOOLS
# ============================================================================

async def get_tools():
    """Get tool statuses."""
    return {
        "tools": list(state._tool_statuses.values()),
        "count": len(state._tool_statuses),
    }


async def update_tool(tool: ToolStatus):
    """Update tool status."""
    state.update_tool_status(tool.tool, tool.status, tool.latency)
    return {"status": "ok"}


# ============================================================================
# TASKS
# ============================================================================

async def create_task(request: TaskRequest, background_tasks: BackgroundTasks):
    """Submit a new agent task."""
    task_id = str(uuid.uuid4())[:8]
    state.task_count += 1

    if state.agent is None:
        state.error_count += 1
        state.add_log("error", "API", f"Task {task_id}: Agent not initialized")
        raise HTTPException(status_code=503, detail="Agent not initialized")

    state.add_log("info", "API", f"Task {task_id}: Submitted - {request.task[:100]}")

    async def run_task():
        try:
            state.add_log("info", "Agent", f"Task {task_id}: Starting execution")
            state.success_count += 1
            state.add_log("info", "Agent", f"Task {task_id}: Completed")
        except Exception as e:
            state.error_count += 1
            state.add_log("error", "Agent", f"Task {task_id}: Failed - {e}")

    background_tasks.add_task(run_task)

    return TaskResponse(
        task_id=task_id,
        status="queued",
        success=True,
        message=f"Task {task_id} queued for execution",
    )


# ============================================================================
# LOG ANALYSIS
# ============================================================================

async def list_log_files():
    """List available log files."""
    repo_root = _get_repo_root()
    logs_dir = repo_root / "AI_support" / "logs"
    if not logs_dir.exists():
        return {"files": [], "count": 0}

    files = []
    for f in logs_dir.glob("*.json"):
        files.append({
            "name": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    for f in logs_dir.glob("*.txt"):
        files.append({
            "name": f.name,
            "size": f.stat().st_size,
            "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })

    files.sort(key=lambda x: x["modified"], reverse=True)
    return {"files": files, "count": len(files)}


async def analyze_logs(request: dict):
    """Analyze logs for AI Agent to provide insights."""
    import json

    repo_root = _get_repo_root()
    log_file = request.get("file_path")
    if not log_file:
        return {"error": "file_path required"}

    log_path = Path(log_file)
    if not log_path.exists():
        log_path = repo_root / "AI_support" / "logs" / log_file

    if not log_path.exists():
        return {"error": f"File not found: {log_file}"}

    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        logs = data.get("logs", [])
        error_logs = [l for l in logs if l.get("level") == "error"]
        warn_logs = [l for l in logs if l.get("level") == "warn"]

        by_source = {}
        for log in logs:
            source = log.get("source", "unknown")
            if source not in by_source:
                by_source[source] = []
            by_source[source].append(log)

        return {
            "file": str(log_path),
            "total": len(logs),
            "errors": len(error_logs),
            "warnings": len(warn_logs),
            "error_logs": error_logs[:20],
            "by_source": {s: len(lst) for s, lst in by_source.items()},
            "analysis": "ready_for_ai"
        }
    except Exception as e:
        return {"error": str(e)}
