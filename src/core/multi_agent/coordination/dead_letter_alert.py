"""
Dead Letter Alert for Multi-Agent Coordination.

Monitors dead letter queue depth and sends webhook alerts when threshold exceeded.
Supports Slack, PagerDuty, and custom webhook integrations.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.core.multi_agent.coordination.types import (
    DeadLetterItem,
    DeadLetterAlertConfig,
)

logger = logging.getLogger(__name__)


class DeadLetterStore:
    """Interface for dead letter queue storage."""
    
    async def get_depth(self, tenant_id: str, queue_name: str = "default") -> int:
        raise NotImplementedError
    
    async def get_items(
        self,
        tenant_id: str,
        queue_name: str = "default",
        limit: int = 100,
    ) -> List[DeadLetterItem]:
        raise NotImplementedError
    
    async def add_item(self, item: DeadLetterItem) -> None:
        raise NotImplementedError
    
    async def remove_item(self, item_id: str) -> None:
        raise NotImplementedError
    
    async def retry_item(self, item_id: str) -> bool:
        raise NotImplementedError


class InMemoryDeadLetterStore(DeadLetterStore):
    """In-memory implementation of DeadLetterStore."""
    
    def __init__(self):
        self._items: Dict[str, DeadLetterItem] = {}
        self._queue_index: Dict[str, List[str]] = {}  # (tenant_id, queue) -> [item_ids]
        self._lock = asyncio.Lock()
    
    async def get_depth(self, tenant_id: str, queue_name: str = "default") -> int:
        key = f"{tenant_id}:{queue_name}"
        return len(self._queue_index.get(key, []))
    
    async def get_items(
        self,
        tenant_id: str,
        queue_name: str = "default",
        limit: int = 100,
    ) -> List[DeadLetterItem]:
        key = f"{tenant_id}:{queue_name}"
        item_ids = self._queue_index.get(key, [])[:limit]
        return [self._items[iid] for iid in item_ids if iid in self._items]
    
    async def add_item(self, item: DeadLetterItem) -> None:
        async with self._lock:
            self._items[item.id] = item
            key = f"{item.tenant_id}:{item.queue_name}"
            if key not in self._queue_index:
                self._queue_index[key] = []
            self._queue_index[key].append(item.id)
    
    async def remove_item(self, item_id: str) -> None:
        async with self._lock:
            if item_id in self._items:
                item = self._items[item_id]
                key = f"{item.tenant_id}:{item.queue_name}"
                if key in self._queue_index:
                    self._queue_index[key] = [
                        iid for iid in self._queue_index[key] if iid != item_id
                    ]
                del self._items[item_id]
    
    async def retry_item(self, item_id: str) -> bool:
        async with self._lock:
            if item_id in self._items:
                item = self._items[item_id]
                item.retry_count += 1
                item.last_retry_at = datetime.now()
                return True
            return False


class WebhookSender:
    """Interface for sending webhook alerts."""
    
    async def send(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> bool:
        raise NotImplementedError


class HTTPWebhookSender(WebhookSender):
    """HTTP-based webhook sender."""
    
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
    
    async def send(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> bool:
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                if method.upper() == "POST":
                    response = await client.post(url, json=payload, headers=headers)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=payload, headers=headers)
                else:
                    response = await client.request(method, url, json=payload, headers=headers)
                
                return response.status_code < 400
                
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False


@dataclass
class DLQAlert:
    """Dead letter queue alert payload."""
    tenant_id: str
    queue_name: str
    depth: int
    threshold: int
    timestamp: datetime
    top_errors: List[Dict[str, Any]] = field(default_factory=list)
    oldest_item_age_seconds: float = 0.0


class DeadLetterAlert:
    """
    Dead letter queue alert system for multi-agent coordination.
    
    Monitors DLQ depth and sends webhook alerts when threshold exceeded.
    Supports:
    - Configurable depth thresholds per tenant/queue
    - Slack webhook formatting
    - PagerDuty integration
    - Custom webhook payloads
    
    Alerts are sent when:
    - DLQ depth exceeds threshold
    - New failed items are added (optional)
    - System detects stuck items
    """
    
    def __init__(
        self,
        store: Optional[DeadLetterStore] = None,
        webhook_sender: Optional[WebhookSender] = None,
        default_threshold: int = 1000,
        default_webhook_url: str = "",
        default_webhook_method: str = "POST",
        default_webhook_headers: Optional[Dict[str, str]] = None,
        check_interval_seconds: int = 60,
        enabled: bool = True,
    ):
        self.store = store or InMemoryDeadLetterStore()
        self.webhook_sender = webhook_sender or HTTPWebhookSender()
        self.default_threshold = default_threshold
        self.default_webhook_url = default_webhook_url
        self.default_webhook_method = default_webhook_method
        self.default_webhook_headers = default_webhook_headers or {}
        self.check_interval_seconds = check_interval_seconds
        self.enabled = enabled
        
        self._lock = asyncio.Lock()
        self._configs: Dict[str, DeadLetterAlertConfig] = {}
        self._alert_history: List[DLQAlert] = []
        self._last_alert_time: Dict[str, datetime] = {}
        self._check_task: Optional[asyncio.Task] = None
        self._running = False
        
        # Metrics
        self._alert_count = 0
        self._alert_success_count = 0
        self._alert_failure_count = 0
    
    async def start(self) -> None:
        """Start background DLQ monitoring."""
        if self._running:
            return
        
        self._running = True
        self._check_task = asyncio.create_task(self._monitor_loop())
        logger.info("DeadLetterAlert monitoring started")
    
    async def stop(self) -> None:
        """Stop background DLQ monitoring."""
        self._running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info("DeadLetterAlert monitoring stopped")
    
    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                await asyncio.sleep(self.check_interval_seconds)
                await self.check_and_alert()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DLQ monitoring error: {e}")
    
    def _get_config_key(self, tenant_id: str, queue_name: str = "default") -> str:
        """Get config key for tenant/queue."""
        return f"{tenant_id}:{queue_name}"
    
    async def set_alert_config(
        self,
        tenant_id: str,
        queue_name: str = "default",
        threshold: Optional[int] = None,
        webhook_url: Optional[str] = None,
        webhook_method: Optional[str] = None,
        webhook_headers: Optional[Dict[str, str]] = None,
        enabled: bool = True,
    ) -> DeadLetterAlertConfig:
        """Set alert configuration for a tenant/queue."""
        key = self._get_config_key(tenant_id, queue_name)
        
        config = DeadLetterAlertConfig(
            tenant_id=tenant_id,
            queue_name=queue_name,
            threshold=threshold or self.default_threshold,
            webhook_url=webhook_url or self.default_webhook_url,
            webhook_method=webhook_method or self.default_webhook_method,
            webhook_headers=webhook_headers or self.default_webhook_headers,
            enabled=enabled,
        )
        
        async with self._lock:
            self._configs[key] = config
        
        logger.info(f"Set alert config for {key}: threshold={config.threshold}")
        return config
    
    async def get_alert_config(
        self,
        tenant_id: str,
        queue_name: str = "default",
    ) -> DeadLetterAlertConfig:
        """Get alert configuration for a tenant/queue."""
        key = self._get_config_key(tenant_id, queue_name)
        
        async with self._lock:
            if key in self._configs:
                return self._configs[key]
        
        # Return default config
        return DeadLetterAlertConfig(
            tenant_id=tenant_id,
            queue_name=queue_name,
            threshold=self.default_threshold,
            webhook_url=self.default_webhook_url,
            webhook_method=self.default_webhook_method,
            webhook_headers=self.default_webhook_headers,
            enabled=self.enabled,
        )
    
    async def check_and_alert(
        self,
        tenant_id: Optional[str] = None,
        queue_name: str = "default",
    ) -> Optional[DLQAlert]:
        """
        Check DLQ depth and send alert if threshold exceeded.
        
        Args:
            tenant_id: Optional tenant ID (checks all if not provided)
            queue_name: Queue name to check
            
        Returns:
            DLQAlert if alert was sent, None otherwise
        """
        if not self.enabled:
            return None
        
        if tenant_id:
            return await self._check_single(tenant_id, queue_name)
        
        # Check all tenants
        alerts = []
        async with self._lock:
            keys = list(self._configs.keys())
        
        for key in keys:
            parts = key.split(":")
            t_id, q_name = parts[0], parts[1] if len(parts) > 1 else "default"
            alert = await self._check_single(t_id, q_name)
            if alert:
                alerts.append(alert)
        
        return alerts[0] if len(alerts) == 1 else alerts if alerts else None
    
    async def _check_single(
        self,
        tenant_id: str,
        queue_name: str,
    ) -> Optional[DLQAlert]:
        """Check DLQ depth for a single tenant/queue."""
        config = await self.get_alert_config(tenant_id, queue_name)
        
        if not config.enabled:
            return None
        
        depth = await self.store.get_depth(tenant_id, queue_name)
        
        if depth < config.threshold:
            return None
        
        # Get top errors
        items = await self.store.get_items(tenant_id, queue_name, limit=5)
        top_errors = [
            {
                "error": item.error,
                "retry_count": item.retry_count,
                "age_seconds": (datetime.now() - item.created_at).total_seconds(),
            }
            for item in items
        ]
        
        oldest_age = 0.0
        if items:
            oldest_age = (datetime.now() - items[0].created_at).total_seconds()
        
        # Create alert
        alert = DLQAlert(
            tenant_id=tenant_id,
            queue_name=queue_name,
            depth=depth,
            threshold=config.threshold,
            timestamp=datetime.now(),
            top_errors=top_errors,
            oldest_item_age_seconds=oldest_age,
        )
        
        # Check if we should send (avoid alert storms)
        if await self._should_send_alert(tenant_id, queue_name):
            await self._send_alert(config, alert)
            self._last_alert_time[f"{tenant_id}:{queue_name}"] = datetime.now()
        
        self._alert_count += 1
        return alert
    
    async def _should_send_alert(
        self,
        tenant_id: str,
        queue_name: str,
    ) -> bool:
        """Check if we should send an alert (avoid spamming)."""
        key = f"{tenant_id}:{queue_name}"
        last_time = self._last_alert_time.get(key)
        
        if not last_time:
            return True
        
        # Don't send more than one alert per minute
        elapsed = (datetime.now() - last_time).total_seconds()
        return elapsed > 60
    
    async def _send_alert(
        self,
        config: DeadLetterAlertConfig,
        alert: DLQAlert,
    ) -> bool:
        """Send alert via webhook."""
        if not config.webhook_url:
            logger.warning(f"No webhook URL configured for {config.tenant_id}")
            return False
        
        # Build payload
        payload = self._build_payload(alert)
        
        try:
            success = await self.webhook_sender.send(
                url=config.webhook_url,
                method=config.webhook_method,
                headers=config.webhook_headers,
                payload=payload,
            )
            
            if success:
                self._alert_success_count += 1
                self._alert_history.append(alert)
                logger.info(
                    f"DLQ alert sent for {config.tenant_id}: "
                    f"depth={alert.depth}, threshold={alert.threshold}"
                )
            else:
                self._alert_failure_count += 1
                logger.error(f"Failed to send DLQ alert for {config.tenant_id}")
            
            return success
            
        except Exception as e:
            self._alert_failure_count += 1
            logger.error(f"Error sending DLQ alert: {e}")
            return False
    
    def _build_payload(self, alert: DLQAlert) -> Dict[str, Any]:
        """Build webhook payload from alert."""
        # Slack format
        return {
            "text": f"🚨 Dead Letter Queue Alert",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "DLQ Alert",
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Tenant:*\n{alert.tenant_id}"},
                        {"type": "mrkdwn", "text": f"*Queue:*\n{alert.queue_name}"},
                        {"type": "mrkdwn", "text": f"*Depth:*\n{alert.depth}"},
                        {"type": "mrkdwn", "text": f"*Threshold:*\n{alert.threshold}"},
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Oldest item: {alert.oldest_item_age_seconds:.0f}s"}
                    ]
                }
            ]
        }
    
    async def add_failed_item(
        self,
        tenant_id: str,
        item_id: str,
        message: Dict[str, Any],
        error: str,
        queue_name: str = "default",
        max_retries: int = 3,
    ) -> DeadLetterItem:
        """Add a failed item to the dead letter queue."""
        item = DeadLetterItem(
            id=item_id,
            tenant_id=tenant_id,
            queue_name=queue_name,
            message=message,
            error=error,
            max_retries=max_retries,
        )
        
        await self.store.add_item(item)
        
        # Check if we should alert
        await self.check_and_alert(tenant_id, queue_name)
        
        return item
    
    async def retry_item(self, item_id: str) -> bool:
        """Retry a dead letter item."""
        return await self.store.retry_item(item_id)
    
    async def discard_item(self, item_id: str) -> None:
        """Discard a dead letter item."""
        await self.store.remove_item(item_id)
    
    async def get_queue_stats(
        self,
        tenant_id: str,
        queue_name: str = "default",
    ) -> Dict[str, Any]:
        """Get dead letter queue statistics."""
        depth = await self.store.get_depth(tenant_id, queue_name)
        items = await self.store.get_items(tenant_id, queue_name, limit=100)
        
        config = await self.get_alert_config(tenant_id, queue_name)
        
        exhausted_count = sum(1 for item in items if item.is_exhausted)
        
        oldest_age = 0.0
        if items:
            oldest_age = (datetime.now() - min(items, key=lambda i: i.created_at).created_at).total_seconds()
        
        return {
            "tenant_id": tenant_id,
            "queue_name": queue_name,
            "depth": depth,
            "threshold": config.threshold,
            "threshold_exceeded": depth >= config.threshold,
            "exhausted_items": exhausted_count,
            "oldest_item_age_seconds": oldest_age,
            "alert_enabled": config.enabled,
        }
    
    async def get_all_queue_stats(self) -> List[Dict[str, Any]]:
        """Get statistics for all queues."""
        async with self._lock:
            keys = list(self._configs.keys())
        
        results = []
        seen = set()
        
        for key in keys:
            parts = key.split(":")
            tenant_id, queue_name = parts[0], parts[1] if len(parts) > 1 else "default"
            seen.add((tenant_id, queue_name))
            results.append(await self.get_queue_stats(tenant_id, queue_name))
        
        return results
    
    async def get_alert_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get alert history."""
        return [
            {
                "tenant_id": a.tenant_id,
                "queue_name": a.queue_name,
                "depth": a.depth,
                "threshold": a.threshold,
                "timestamp": a.timestamp.isoformat(),
            }
            for a in self._alert_history[-limit:]
        ]
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get dead letter alert metrics."""
        return {
            "alert_count": self._alert_count,
            "alert_success_count": self._alert_success_count,
            "alert_failure_count": self._alert_failure_count,
            "monitoring_enabled": self.enabled,
            "check_interval_seconds": self.check_interval_seconds,
            "configured_queues": len(self._configs),
        }
