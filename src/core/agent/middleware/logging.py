"""Logging middleware module."""

import logging
from typing import Any


logger = logging.getLogger(__name__)


class LoggingMiddleware:
    """Logging middleware."""
    
    async def process(self, context: dict[str, Any], next_handler) -> Any:
        """Process with logging."""
        logger.info(f"Processing: {context.get('type', 'unknown')}")
        result = await next_handler(context)
        logger.info(f"Completed: {context.get('type', 'unknown')}")
        return result
