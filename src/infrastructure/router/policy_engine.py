"""Policy engine for rule-based and semantic routing."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Optional

from src.infrastructure.router.types import (
    PolicyResult,
    Request,
    RequestContext,
    RouteResult,
    RoutingRule,
)

if TYPE_CHECKING:
    from src.infrastructure.router.score_engine import ScoreEngine

logger = logging.getLogger(__name__)


@dataclass
class PolicyEngineConfig:
    """Configuration for policy engine."""

    default_intent: str = "unknown"
    fallback_enabled: bool = True
    min_confidence_threshold: float = 0.3


class PolicyEngine:
    """
    Combines rule-based and semantic routing.
    
    Evaluation order:
    1. Rule-based matching (priority order)
    2. Semantic scoring (if needed)
    3. Fallback to default (if enabled)
    """

    def __init__(
        self,
        config: PolicyEngineConfig,
        score_engine: Optional[ScoreEngine] = None,
    ):
        self._config = config
        self._score_engine = score_engine
        self._rules: list[RoutingRule] = []
        self._rule_lock = asyncio.Lock()

    def add_rule(self, rule: RoutingRule) -> None:
        """Add routing rule."""
        self._rules.append(rule)

    async def evaluate(
        self,
        context: RequestContext,
        request: Request,
    ) -> PolicyResult:
        """
        Evaluate rules and determine routing strategy.
        
        Args:
            context: Request context with frozen snapshot
            request: Incoming request
            
        Returns:
            PolicyResult with routing decision
        """
        snapshot = context.frozen_snapshot

        sorted_rules = sorted(
            snapshot.config.intents.values(),
            key=lambda x: x.priority if x.rules else 0,
            reverse=True,
        )

        for intent_config in sorted_rules:
            if not intent_config.rules:
                continue
            for rule in intent_config.rules:
                if rule.matches(request):
                    return PolicyResult(
                        intent=rule.intent,
                        confidence=rule.confidence,
                        needs_semantic=rule.needs_semantic,
                        handler=intent_config.handler,
                    )

        return PolicyResult(
            needs_semantic=True,
        )

    async def route(
        self,
        context: RequestContext,
        request: Request,
        available_intents: Optional[list[str]] = None,
    ) -> RouteResult:
        """
        Full routing with semantic scoring.
        
        Args:
            context: Request context
            request: Incoming request
            available_intents: Filter to specific intents (for lifecycle)
            
        Returns:
            RouteResult with final routing decision
        """
        policy_result = await self.evaluate(context, request)

        if not policy_result.needs_semantic:
            return RouteResult(
                intent=policy_result.intent or self._config.default_intent,
                confidence=policy_result.confidence,
                handler=policy_result.handler,
                routing_type=policy_result.routing_type,
            )

        if not self._score_engine:
            logger.warning("Semantic routing needed but no score engine")
            return RouteResult(
                intent=self._config.default_intent,
                confidence=0.0,
                routing_type=policy_result.routing_type,
            )

        if available_intents is None:
            snapshot = context.frozen_snapshot
            available_intents = list(snapshot.config.intents.keys())

        scores = await self._score_engine.calculate_scores(
            context,
            request.query,
            available_intents,
        )

        final_scores = {}
        for intent, score in scores.items():
            final_score = await self._score_engine.calculate_final_score(
                context, intent, score
            )
            final_scores[intent] = final_score

        if not final_scores:
            return RouteResult(
                intent=self._config.default_intent,
                confidence=0.0,
                routing_type=policy_result.routing_type,
            )

        best_intent = max(final_scores, key=final_scores.get)
        best_score = final_scores[best_intent]

        if best_score < self._config.min_confidence_threshold and self._config.fallback_enabled:
            return RouteResult(
                intent=self._config.default_intent,
                confidence=best_score,
                all_scores=final_scores,
                routing_type=policy_result.routing_type,
            )

        return RouteResult(
            intent=best_intent,
            confidence=best_score,
            all_scores=final_scores,
            routing_type=policy_result.routing_type,
        )


def create_keyword_rule(pattern: str, intent: str, priority: int = 10) -> RoutingRule:
    """Create rule matching keywords."""
    return RoutingRule(
        pattern=pattern,
        intent=intent,
        confidence=0.9,
        needs_semantic=False,
        priority=priority,
    )


def create_regex_rule(pattern: str, intent: str, priority: int = 10) -> RoutingRule:
    """Create rule matching regex."""
    return RoutingRule(
        pattern=pattern,
        intent=intent,
        confidence=0.95,
        needs_semantic=False,
        priority=priority,
    )
