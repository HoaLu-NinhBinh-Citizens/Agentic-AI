"""Agent Runtime Kernel - Lifecycle, sandbox, deterministic FSM, scheduling, failure isolation.

This module provides the core runtime for agent execution:
- Lifecycle management (spawn, suspend, resume, cancel, checkpoint)
- Capability sandbox (tool permissions, resource quota, token budget)
- Deterministic FSM (replayable execution, action log, idempotency)
- Scheduling (priority, fairness, backpressure)
- Failure isolation (agent crash → isolated, retry boundary)
"""

from .lifecycle import AgentLifecycle, AgentState, LifecycleEvent
from .sandbox import AgentSandbox, SandboxConfig, SandboxPermission, ResourceQuota
from .fsm import DeterministicFSM, FSMState, FSMAction, FSMTransition
from .scheduler import AgentScheduler, SchedulingPolicy, PriorityLevel
from .isolation import FailureIsolation, IsolationBoundary, RetryBoundary, ErrorSeverity, ErrorCategory

__all__ = [
    "AgentLifecycle",
    "AgentState",
    "LifecycleEvent",
    "AgentSandbox",
    "SandboxConfig",
    "SandboxPermission",
    "ResourceQuota",
    "DeterministicFSM",
    "FSMState",
    "FSMAction",
    "FSMTransition",
    "AgentScheduler",
    "SchedulingPolicy",
    "PriorityLevel",
    "FailureIsolation",
    "IsolationBoundary",
    "RetryBoundary",
    "ErrorSeverity",
    "ErrorCategory",
]
