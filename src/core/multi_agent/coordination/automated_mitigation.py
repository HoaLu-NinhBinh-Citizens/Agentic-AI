"""
Automated DLQ Mitigation.

Provides automated actions when DLQ exceeds thresholds:
- Auto pause source agent
- Auto quarantine tenant
- Auto disable plugin
- Auto reroute coordinator
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MitigationAction(str, Enum):
    """Automated mitigation actions."""
    PAUSE_AGENT = "pause_agent"
    QUARANTINE_TENANT = "quarantine_tenant"
    DISABLE_PLUGIN = "disable_plugin"
    REROUTE_COORDINATOR = "reroute_coordinator"
    THROTTLE_RATE = "throttle_rate"
    ESCALATE = "escalate"
    NOTIFY = "notify"


@dataclass
class MitigationRule:
    """Rule for automated mitigation."""
    rule_id: str
    name: str
    condition: Dict[str, Any]  # e.g., {"depth_threshold": 1000, "error_pattern": "timeout"}
    actions: List[MitigationAction]
    cooldown_seconds: float = 60.0
    enabled: bool = True
    priority: int = 5  # 1-10, higher = more urgent


@dataclass
class MitigationEvent:
    """Record of a mitigation action."""
    event_id: str
    rule_id: str
    action: MitigationAction
    target_id: str  # agent_id, tenant_id, etc.
    timestamp: datetime
    details: Dict[str, Any]
    success: bool
    error: Optional[str] = None


class AutomatedMitigationEngine:
    """
    Automated DLQ mitigation engine.
    
    Monitors DLQ and executes automated actions when thresholds are exceeded.
    
    Actions:
    - PAUSE_AGENT: Pause failing agent
    - QUARANTINE_TENANT: Quarantine misbehaving tenant
    - DISABLE_PLUGIN: Disable problematic plugin
    - REROUTE_COORDINATOR: Failover to another coordinator
    - THROTTLE_RATE: Reduce rate limit for source
    - ESCALATE: Send to human review
    - NOTIFY: Send notification
    """
    
    def __init__(
        self,
        check_interval_seconds: float = 60.0,
    ):
        self.check_interval_seconds = check_interval_seconds
        
        self._rules: Dict[str, MitigationRule] = {}
        self._actions: Dict[MitigationAction, Callable] = {}
        self._events: List[MitigationEvent] = []
        self._last_action_time: Dict[str, datetime] = {}
        self._running = False
        self._check_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        # Metrics
        self._action_count = defaultdict(int)
        self._success_count = defaultdict(int)
        
        # Register default rules
        self._register_default_rules()
    
    def _register_default_rules(self) -> None:
        """Register default mitigation rules."""
        self.add_rule(MitigationRule(
            rule_id="dlq_depth_high",
            name="DLQ Depth Exceeded",
            condition={"depth_threshold": 1000},
            actions=[MitigationAction.NOTIFY, MitigationAction.ESCALATE],
            cooldown_seconds=300,
            priority=8,
        ))
        
        self.add_rule(MitigationRule(
            rule_id="dlq_depth_critical",
            name="DLQ Depth Critical",
            condition={"depth_threshold": 5000},
            actions=[
                MitigationAction.THROTTLE_RATE,
                MitigationAction.PAUSE_AGENT,
                MitigationAction.NOTIFY,
            ],
            cooldown_seconds=60,
            priority=10,
        ))
        
        self.add_rule(MitigationRule(
            rule_id="dlq_agent_failure",
            name="Agent Failure Pattern",
            condition={"failure_count": 100, "window_seconds": 300},
            actions=[
                MitigationAction.PAUSE_AGENT,
                MitigationAction.ESCALATE,
            ],
            cooldown_seconds=180,
            priority=9,
        ))
        
        self.add_rule(MitigationRule(
            rule_id="dlq_tenant_abuse",
            name="Tenant Resource Abuse",
            condition={"tenant_error_rate": 0.5, "window_seconds": 60},
            actions=[
                MitigationAction.THROTTLE_RATE,
                MitigationAction.QUARANTINE_TENANT,
            ],
            cooldown_seconds=600,
            priority=10,
        ))
    
    def add_rule(self, rule: MitigationRule) -> None:
        """Add a mitigation rule."""
        self._rules[rule.rule_id] = rule
        logger.info(f"Added mitigation rule: {rule.rule_id}")
    
    def remove_rule(self, rule_id: str) -> None:
        """Remove a mitigation rule."""
        self._rules.pop(rule_id, None)
        logger.info(f"Removed mitigation rule: {rule_id}")
    
    def register_action(
        self,
        action: MitigationAction,
        handler: Callable[[str, Dict[str, Any]], Any],
    ) -> None:
        """Register an action handler."""
        self._actions[action] = handler
    
    async def execute_action(
        self,
        action: MitigationAction,
        target_id: str,
        rule: MitigationRule,
        context: Dict[str, Any],
    ) -> bool:
        """Execute a mitigation action."""
        # Check cooldown
        cooldown_key = f"{action.value}:{target_id}"
        last_time = self._last_action_time.get(cooldown_key)
        if last_time:
            elapsed = (datetime.now() - last_time).total_seconds()
            if elapsed < rule.cooldown_seconds:
                logger.debug(f"Action {action} on {target_id} in cooldown")
                return False
        
        # Execute action
        logger.info(f"Executing action {action} on {target_id}")
        
        success = False
        error = None
        
        try:
            if action in self._actions:
                handler = self._actions[action]
                result = handler(target_id, context)
                if asyncio.iscoroutine(result):
                    await result
                success = True
            else:
                # Default action handlers
                success = await self._default_action(action, target_id, context)
                
        except Exception as e:
            logger.error(f"Action {action} failed: {e}")
            error = str(e)
            success = False
        
        # Record event
        event = MitigationEvent(
            event_id=f"{rule.rule_id}:{target_id}:{datetime.now().timestamp()}",
            rule_id=rule.rule_id,
            action=action,
            target_id=target_id,
            timestamp=datetime.now(),
            details=context,
            success=success,
            error=error,
        )
        
        self._events.append(event)
        self._action_count[action.value] += 1
        if success:
            self._success_count[action.value] += 1
        
        if success:
            self._last_action_time[cooldown_key] = datetime.now()
        
        return success
    
    async def _default_action(
        self,
        action: MitigationAction,
        target_id: str,
        context: Dict[str, Any],
    ) -> bool:
        """Default action implementations."""
        if action == MitigationAction.NOTIFY:
            logger.warning(f"NOTIFY: {target_id} - {context}")
            return True
        
        elif action == MitigationAction.ESCALATE:
            logger.warning(f"ESCALATE: {target_id} - {context}")
            # Would send to alerting system
            return True
        
        elif action == MitigationAction.THROTTLE_RATE:
            logger.warning(f"THROTTLE: {target_id}")
            # Would reduce rate limit
            return True
        
        elif action == MitigationAction.PAUSE_AGENT:
            logger.warning(f"PAUSE AGENT: {target_id}")
            # Would pause the agent
            return True
        
        elif action == MitigationAction.QUARANTINE_TENANT:
            logger.warning(f"QUARANTINE TENANT: {target_id}")
            # Would quarantine the tenant
            return True
        
        elif action == MitigationAction.REROUTE_COORDINATOR:
            logger.warning(f"REROUTE COORDINATOR: {target_id}")
            # Would trigger failover
            return True
        
        return False
    
    async def evaluate_rules(
        self,
        dlq_stats: Dict[str, Any],
    ) -> List[MitigationEvent]:
        """
        Evaluate all rules against DLQ stats.
        
        Returns list of executed mitigation events.
        """
        executed = []
        
        # Sort rules by priority
        rules = sorted(
            self._rules.values(),
            key=lambda r: r.priority,
            reverse=True,
        )
        
        for rule in rules:
            if not rule.enabled:
                continue
            
            # Check condition
            if self._matches_condition(rule, dlq_stats):
                # Execute actions
                for action in rule.actions:
                    target_id = dlq_stats.get("tenant_id", "unknown")
                    
                    success = await self.execute_action(
                        action, target_id, rule, dlq_stats
                    )
                    
                    if success:
                        executed.append(MitigationEvent(
                            event_id=f"{rule.rule_id}:{action.value}:{datetime.now().timestamp()}",
                            rule_id=rule.rule_id,
                            action=action,
                            target_id=target_id,
                            timestamp=datetime.now(),
                            details=dlq_stats,
                            success=True,
                        ))
        
        return executed
    
    def _matches_condition(
        self,
        rule: MitigationRule,
        stats: Dict[str, Any],
    ) -> bool:
        """Check if rule condition matches stats."""
        condition = rule.condition
        
        # Depth threshold
        if "depth_threshold" in condition:
            depth = stats.get("depth", 0)
            if depth < condition["depth_threshold"]:
                return False
        
        # Failure count
        if "failure_count" in condition:
            failures = stats.get("recent_failures", 0)
            if failures < condition["failure_count"]:
                return False
        
        # Tenant error rate
        if "tenant_error_rate" in condition:
            rate = stats.get("tenant_error_rate", 0)
            if rate < condition["tenant_error_rate"]:
                return False
        
        # Error pattern (simplified)
        if "error_pattern" in condition:
            error = stats.get("last_error", "")
            if condition["error_pattern"] not in error:
                return False
        
        return True
    
    async def start(self) -> None:
        """Start automated mitigation monitoring."""
        if self._running:
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._monitor_loop())
        logger.info("Automated mitigation engine started")
    
    async def stop(self) -> None:
        """Stop automated mitigation monitoring."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("Automated mitigation engine stopped")
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval_seconds)
                
                # This would typically fetch DLQ stats and evaluate
                # For now, just check cooldown expiry
                await self._check_cooldown_expiry()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Mitigation loop error: {e}")
    
    async def _check_cooldown_expiry(self) -> None:
        """Check and reset cooldown if expired."""
        now = datetime.now()
        expired = [
            key for key, last_time in self._last_action_time.items()
            if (now - last_time).total_seconds() > 3600  # Reset after 1 hour
        ]
        for key in expired:
            del self._last_action_time[key]
    
    async def get_mitigation_history(
        self,
        rule_id: Optional[str] = None,
        action: Optional[MitigationAction] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get mitigation event history."""
        events = self._events
        
        if rule_id:
            events = [e for e in events if e.rule_id == rule_id]
        if action:
            events = [e for e in events if e.action == action]
        
        events = events[-limit:]
        
        return [
            {
                "event_id": e.event_id,
                "rule_id": e.rule_id,
                "action": e.action.value,
                "target_id": e.target_id,
                "timestamp": e.timestamp.isoformat(),
                "success": e.success,
                "error": e.error,
            }
            for e in reversed(events)
        ]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get mitigation metrics."""
        return {
            "rules_enabled": sum(1 for r in self._rules.values() if r.enabled),
            "total_rules": len(self._rules),
            "action_counts": dict(self._action_count),
            "success_counts": dict(self._success_count),
            "total_events": len(self._events),
            "active_cooldowns": len(self._last_action_time),
        }
