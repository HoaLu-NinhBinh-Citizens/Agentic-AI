"""Legacy alias for backward compatibility with tests.

This module redirects imports from src.agent.* to src.core.agent.*
to maintain compatibility with test files that use legacy import paths.
"""

from src.core.agent.core import AgentCore
from src.core.agent.planner import AgentPlanner

__all__ = ["AgentCore", "AgentPlanner"]
