"""LSP (Language Server Protocol) infrastructure for AI_SUPPORT.

Provides IDE-like features:
- Go-to-definition (F12)
- Find all references
- Hover info (type signatures)
- Inline diagnostics/errors
- Auto-completion
- Code lens

Architecture:
    1. AISupportLanguageServer - pygls-based LSP server
    2. SymbolResolver integration - real symbol resolution
    3. SafeTreeSitterIndexer - AST-based parsing
    4. SymbolGraph - call graph and dependency tracking
    5. MLDetector integration - code quality diagnostics
"""

from __future__ import annotations

from .server import AISupportLanguageServer, LSPCapabilities

__all__ = [
    "AISupportLanguageServer",
    "LSPCapabilities",
]
