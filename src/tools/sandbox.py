"""Compatibility shim for `src.tools.sandbox`.

The canonical implementation lives in `src.core.tools.sandbox`.
This module exists so older imports (and tests) keep working.
"""

from src.core.tools.sandbox import *  # noqa: F403
