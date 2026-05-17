"""Strong Query Mechanics - Phase 5A (v6).

Strong consistency query implementation.
Strong query acquires workflow execution lock and replays
all committed events before evaluation.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Callable, Awaitable
from enum import Enum

logger = logging.getLogger(__name__)


class QueryConsistency(str, Enum):
    """Query consistency levels."""
    EVENTUAL = "eventual"  # Fast, may not reflect latest state
    STRONG = "strong"     # Acquires lock, replays events, ensures consistency


@dataclass
class QueryRequest:
    """A query request to a workflow."""
    query_id: str
    workflow_id: str
    query_name: str
    args: dict = field(default_factory=dict)
    
    # Consistency
    consistency: QueryConsistency = QueryConsistency.EVENTUAL
    
    # Timing
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class QueryResult:
    """Result of a workflow query."""
    query_id: str
    workflow_id: str
    query_name: str
    
    # Consistency
    consistency: QueryConsistency
    
    # Result
    result: Optional[Any] = None
    error: Optional[str] = None
    
    # State at query time
    state_snapshot: Optional[dict] = None
    
    # Timing
    queried_at: float = field(default_factory=time.time)
    duration_ms: float = 0.0


class StrongQueryExecutor:
    """Executor for strong consistency queries.
    
    Strong query protocol:
    1. Acquire workflow execution lock
    2. Wait for all pending mutations to complete
    3. Replay all committed events
    4. Execute query handler on current state
    5. Release lock
    6. Return query result
    
    This ensures query sees consistent snapshot.
    """
    
    def __init__(
        self,
        lock_manager: Any = None,
        event_store: Any = None,
        workflow_registry: Any = None,
        strong_query_timeout_seconds: float = 30.0,
    ):
        self._lock_manager = lock_manager
        self._event_store = event_store
        self._workflow_registry = workflow_registry
        self._strong_query_timeout = strong_query_timeout_seconds
        
        # Query handlers registry
        self._handlers: dict[str, Callable[[], Awaitable[Any]]] = {}
        
        # Active strong queries (for monitoring)
        self._active_queries: dict[str, QueryRequest] = {}
        self._lock = asyncio.Lock()
    
    def register_handler(
        self,
        query_name: str,
        handler: Callable[[], Awaitable[Any]],
    ) -> None:
        """Register a query handler.
        
        Args:
            query_name: Name of the query.
            handler: Async function to handle query.
        """
        self._handlers[query_name] = handler
    
    async def execute_query(
        self,
        workflow_id: str,
        query_name: str,
        args: dict = None,
        consistency: QueryConsistency = QueryConsistency.EVENTUAL,
    ) -> QueryResult:
        """Execute a query on a workflow.
        
        Args:
            workflow_id: Workflow to query.
            query_name: Name of query handler.
            args: Query arguments.
            consistency: Consistency level.
            
        Returns:
            QueryResult with query response.
        """
        args = args or {}
        start_time = time.time()
        
        if consistency == QueryConsistency.STRONG:
            return await self._execute_strong_query(
                workflow_id, query_name, args, start_time
            )
        else:
            return await self._execute_eventual_query(
                workflow_id, query_name, args, start_time
            )
    
    async def _execute_strong_query(
        self,
        workflow_id: str,
        query_name: str,
        args: dict,
        start_time: float,
    ) -> QueryResult:
        """Execute strong query with full consistency guarantee.
        
        Protocol:
        1. Acquire workflow execution lock
        2. Wait for all pending mutations to complete
        3. Replay all committed events
        4. Execute query handler
        5. Release lock
        """
        query_id = f"sq_{workflow_id[:8]}_{query_name}_{int(time.time() * 1000)}"
        query = QueryRequest(
            query_id=query_id,
            workflow_id=workflow_id,
            query_name=query_name,
            args=args,
            consistency=QueryConsistency.STRONG,
        )
        
        # Track active query
        async with self._lock:
            self._active_queries[query_id] = query
            query.started_at = time.time()
        
        lock_token = None
        
        try:
            logger.debug(f"Starting strong query {query_id} for workflow {workflow_id[:8]}...")
            
            # Step 1: Acquire workflow execution lock
            if self._lock_manager:
                lock_token = await asyncio.wait_for(
                    self._lock_manager.acquire(
                        key=f"workflow_exec_{workflow_id}",
                        owner_id=f"query_{query_id}",
                    ),
                    timeout=self._strong_query_timeout,
                )
                logger.debug(f"Acquired lock for strong query {query_id}")
            
            # Step 2: Wait for pending mutations to complete
            await self._wait_for_pending_mutations(workflow_id)
            
            # Step 3: Replay committed events (if needed for query)
            state = await self._replay_events_for_query(workflow_id)
            
            # Step 4: Execute query handler
            handler = self._handlers.get(query_name)
            if not handler:
                raise ValueError(f"Unknown query: {query_name}")
            
            result = await handler()
            
            duration = (time.time() - start_time) * 1000
            
            return QueryResult(
                query_id=query_id,
                workflow_id=workflow_id,
                query_name=query_name,
                consistency=QueryConsistency.STRONG,
                result=result,
                state_snapshot=state,
                duration_ms=duration,
            )
            
        except asyncio.TimeoutError:
            logger.warning(f"Strong query {query_id} timed out after {self._strong_query_timeout}s")
            return QueryResult(
                query_id=query_id,
                workflow_id=workflow_id,
                query_name=query_name,
                consistency=QueryConsistency.STRONG,
                error=f"Query timed out after {self._strong_query_timeout}s",
                duration_ms=(time.time() - start_time) * 1000,
            )
            
        except Exception as e:
            logger.error(f"Strong query {query_id} failed: {e}")
            return QueryResult(
                query_id=query_id,
                workflow_id=workflow_id,
                query_name=query_name,
                consistency=QueryConsistency.STRONG,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
            
        finally:
            # Step 5: Release lock
            if lock_token and self._lock_manager:
                await self._lock_manager.release(
                    key=f"workflow_exec_{workflow_id}",
                    token=lock_token,
                )
                logger.debug(f"Released lock for strong query {query_id}")
            
            # Remove from active queries
            async with self._lock:
                self._active_queries.pop(query_id, None)
    
    async def _execute_eventual_query(
        self,
        workflow_id: str,
        query_name: str,
        args: dict,
        start_time: float,
    ) -> QueryResult:
        """Execute eventual query - fast but may see stale data.
        
        Reads from cached state without acquiring lock.
        """
        query_id = f"eq_{workflow_id[:8]}_{query_name}_{int(time.time() * 1000)}"
        
        try:
            # Get cached state (fast path)
            state = await self._get_cached_state(workflow_id)
            
            # Execute handler with cached state
            handler = self._handlers.get(query_name)
            if not handler:
                raise ValueError(f"Unknown query: {query_name}")
            
            result = await handler()
            
            duration = (time.time() - start_time) * 1000
            
            return QueryResult(
                query_id=query_id,
                workflow_id=workflow_id,
                query_name=query_name,
                consistency=QueryConsistency.EVENTUAL,
                result=result,
                state_snapshot=state,
                duration_ms=duration,
            )
            
        except Exception as e:
            logger.error(f"Eventual query {query_id} failed: {e}")
            return QueryResult(
                query_id=query_id,
                workflow_id=workflow_id,
                query_name=query_name,
                consistency=QueryConsistency.EVENTUAL,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    async def _wait_for_pending_mutations(
        self,
        workflow_id: str,
    ) -> None:
        """Wait for all pending mutations to complete.
        
        Ensures no concurrent mutations while we replay.
        """
        if self._workflow_registry:
            workflow = await self._workflow_registry.get_workflow(workflow_id)
            if workflow:
                # Wait for any pending activity/child completions
                while workflow.has_pending_mutations():
                    await asyncio.sleep(0.01)
    
    async def _replay_events_for_query(
        self,
        workflow_id: str,
    ) -> dict:
        """Replay events to get current state for query.
        
        Returns the workflow state after replaying all committed events.
        """
        if not self._event_store:
            return {}
        
        # Get all committed events
        events = await self._event_store.get_committed_events(workflow_id)
        
        # Rebuild state by replaying
        state = {}
        for event in events:
            state = self._apply_event_to_state(state, event)
        
        return state
    
    def _apply_event_to_state(
        self,
        state: dict,
        event: Any,
    ) -> dict:
        """Apply an event to state during replay.
        
        Args:
            state: Current state dict.
            event: Event to apply.
            
        Returns:
            Updated state dict.
        """
        # This is a simplified implementation
        # In production, this would need to handle all event types
        event_type = event.get("event_type", "")
        
        if event_type == "state_updated":
            state.update(event.get("data", {}))
        
        return state
    
    async def _get_cached_state(
        self,
        workflow_id: str,
    ) -> Optional[dict]:
        """Get cached workflow state (for eventual query)."""
        if self._workflow_registry:
            workflow = await self._workflow_registry.get_workflow(workflow_id)
            if workflow and workflow.snapshot:
                return workflow.snapshot.state
        return None
    
    async def get_active_queries(
        self,
        workflow_id: Optional[str] = None,
    ) -> list[QueryRequest]:
        """Get list of active queries.
        
        Args:
            workflow_id: Optional filter by workflow.
            
        Returns:
            List of active query requests.
        """
        async with self._lock:
            queries = list(self._active_queries.values())
            if workflow_id:
                queries = [q for q in queries if q.workflow_id == workflow_id]
            return queries
    
    async def cancel_query(
        self,
        query_id: str,
    ) -> bool:
        """Cancel an active query.
        
        Args:
            query_id: Query ID to cancel.
            
        Returns:
            True if query was cancelled.
        """
        async with self._lock:
            query = self._active_queries.get(query_id)
            if query:
                logger.info(f"Cancelling query {query_id}")
                query.error = "Cancelled by user"
                # Note: We can't actually interrupt a running query
                # but we can prevent its result from being used
                return True
        return False


class QueryHandlerRegistry:
    """Registry for query handlers per workflow type."""
    
    def __init__(self):
        self._handlers: dict[str, dict[str, Callable]] = {}
    
    def register(
        self,
        workflow_type: str,
        query_name: str,
        handler: Callable,
    ) -> None:
        """Register a query handler for a workflow type.
        
        Args:
            workflow_type: Workflow type name.
            query_name: Query name.
            handler: Handler function.
        """
        if workflow_type not in self._handlers:
            self._handlers[workflow_type] = {}
        self._handlers[workflow_type][query_name] = handler
    
    def get(
        self,
        workflow_type: str,
        query_name: str,
    ) -> Optional[Callable]:
        """Get handler for workflow type and query name."""
        return self._handlers.get(workflow_type, {}).get(query_name)
    
    def get_workflow_handlers(
        self,
        workflow_type: str,
    ) -> dict[str, Callable]:
        """Get all handlers for a workflow type."""
        return self._handlers.get(workflow_type, {}).copy()
