"""Pydantic models for the CARV API server."""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class MetricUpdate(BaseModel):
    cpu: float = Field(ge=0, le=100, description="CPU usage percentage")
    memory: float = Field(ge=0, le=100, description="Memory usage percentage")
    speed: float = Field(ge=0, description="Motor speed in RPM")
    temperature: float = Field(ge=0, description="Temperature in Celsius")


class LogEntry(BaseModel):
    level: str = Field(pattern="^(debug|info|warn|error)$")
    source: str
    message: str
    timestamp: Optional[str] = None


class ToolStatus(BaseModel):
    tool: str
    status: str = Field(pattern="^(operational|degraded|offline)$")
    latency: int = Field(ge=0, description="Latency in milliseconds")


class SystemStatus(BaseModel):
    agent_initialized: bool
    model: str
    rag_ready: bool
    uptime_seconds: float
    task_count: int = 0
    success_count: int = 0
    error_count: int = 0


class TaskRequest(BaseModel):
    task: str = Field(min_length=1)
    plan_mode: bool = False


class TaskResponse(BaseModel):
    task_id: str
    status: str
    success: bool
    message: str
    result: Optional[Dict[str, Any]] = None
