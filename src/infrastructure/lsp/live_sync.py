"""LSP Live Sync — Real-time document synchronization and feature providers.

Implements LSP-style live features:
- Text document synchronization (incremental sync)
- Live diagnostics (errors, warnings, hints)
- Hover information
- Document symbols
- Formatting
- Go-to-definition
- Find references
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.interfaces.ide.bridge.protocol import (
    Diagnostic, IDEBridgeMessage, MessageType, Range,
)
from src.infrastructure.analysis.rule_engine import RuleEngine


# ─── Document tracking ─────────────────────────────────────────────────────────

@dataclass
class TrackedDocument:
    """A document being tracked for live sync."""
    uri: str
    file_path: str
    content: str
    version: int = 1
    last_modified: float = field(default_factory=time.time)
    language_id: str = "plaintext"
    diagnostics: list[Diagnostic] = field(default_factory=list)
    dirty: bool = False


# ─── Hover information ────────────────────────────────────────────────────────

@dataclass
class HoverInfo:
    """Hover information for a symbol."""
    contents: str
    range: Optional[Range] = None
    signature: str = ""
    docstring: str = ""
    symbol_type: str = ""

    def to_lsp(self) -> dict[str, Any]:
        contents: dict[str, Any] = {"kind": "markdown", "value": self.contents}
        result: dict[str, Any] = {"contents": contents}
        if self.range:
            result["range"] = self.range.to_lsp()
        return result


# ─── Symbol info ─────────────────────────────────────────────────────────────

@dataclass
class DocumentSymbol:
    """A symbol (function, class, etc.) in a document."""
    name: str
    kind: str  # function, class, method, variable, etc.
    detail: str = ""
    range: Optional[Range] = None
    selection_range: Optional[Range] = None
    children: list[DocumentSymbol] = field(default_factory=list)
    deprecated: bool = False
    docstring: str = ""

    def to_lsp(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "kind": self._kind_to_lsp(),
            "detail": self.detail,
            "deprecated": self.deprecated,
        }
        if self.range:
            result["range"] = self.range.to_lsp()
        if self.selection_range:
            result["selectionRange"] = self.selection_range.to_lsp()
        if self.children:
            result["children"] = [c.to_lsp() for c in self.children]
        return result

    def _kind_to_lsp(self) -> int:
        kinds = {
            "file": 1, "module": 2, "namespace": 3, "package": 4,
            "class": 5, "enum": 6, "interface": 7, "struct": 8,
            "typeParameter": 9, "string": 10, "number": 11, "boolean": 12,
            "array": 13, "object": 14, "key": 15, "null": 16,
            "enumMember": 17, "event": 18, "operator": 19,
            "typeAlias": 22, "parameter": 23, "variable": 24,
            "constant": 25, "property": 26, "field": 27,
            "method": 6, "function": 12, "constructor": 9,
        }
        return kinds.get(self.kind, 1)


# ─── LSPLiveSync ─────────────────────────────────────────────────────────────

class LSPLiveSync:
    """Manages live LSP features for tracked documents.

    Integrates with:
    - RuleEngine for static analysis diagnostics
    - SymbolGraph for symbol information
    - IDE bridge for sending updates to the editor
    """

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        debounce_ms: int = 500,
    ):
        self.rule_engine = rule_engine or RuleEngine()
        self._documents: dict[str, TrackedDocument] = {}
        self._callbacks: list[Callable[[dict], None]] = []
        self._debounce_ms = debounce_ms
        self._pending_diagnostics: dict[str, asyncio.Task] = {}
        self._stats = {
            "documents_tracked": 0,
            "diagnostics_sent": 0,
            "hover_requests": 0,
            "symbol_requests": 0,
        }

    # ─── Document management ──────────────────────────────────────────────────

    def track_document(self, file_path: str, content: str = "") -> TrackedDocument:
        """Start tracking a document."""
        uri = self._path_to_uri(file_path)
        language_id = self._detect_language(file_path)

        if uri in self._documents:
            doc = self._documents[uri]
            doc.dirty = True
        else:
            doc = TrackedDocument(
                uri=uri,
                file_path=file_path,
                content=content,
                language_id=language_id,
            )
            self._documents[uri] = doc
            self._stats["documents_tracked"] += 1

        return doc

    def untrack_document(self, uri: str) -> None:
        """Stop tracking a document."""
        if uri in self._documents:
            del self._documents[uri]
            # Cancel pending diagnostics task
            if uri in self._pending_diagnostics:
                self._pending_diagnostics[uri].cancel()
                del self._pending_diagnostics[uri]

    def update_content(self, uri: str, content: str) -> None:
        """Update document content and schedule diagnostics."""
        doc = self._documents.get(uri)
        if not doc:
            return

        doc.content = content
        doc.version += 1
        doc.last_modified = time.time()
        doc.dirty = True

        # Schedule diagnostics with debounce
        self._schedule_diagnostics(uri)

    # ─── Incremental sync ────────────────────────────────────────────────────

    def apply_text_edit(
        self,
        uri: str,
        range: Range,
        new_text: str,
    ) -> bool:
        """Apply an incremental text edit to a tracked document."""
        doc = self._documents.get(uri)
        if not doc:
            return False

        lines = doc.content.split("\n")

        # Apply the edit
        start_line = min(range.start_line, len(lines) - 1)
        end_line = min(range.end_line, len(lines) - 1)

        start_line_content = lines[start_line]
        end_line_content = lines[end_line]

        new_start = start_line_content[:range.start_col]
        new_end = end_line_content[range.end_col:]
        new_lines = lines[:start_line]
        new_lines.append(new_start + new_text + new_end)
        new_lines.extend(lines[end_line + 1:])

        doc.content = "\n".join(new_lines)
        doc.version += 1
        doc.last_modified = time.time()
        doc.dirty = True

        # Schedule re-analysis
        self._schedule_diagnostics(uri)

        return True

    # ─── Diagnostics ────────────────────────────────────────────────────────

    async def run_diagnostics(self, uri: str) -> list[Diagnostic]:
        """Run diagnostics on a document and send to IDE."""
        doc = self._documents.get(uri)
        if not doc:
            return []

        # Run static analysis
        try:
            findings = self.rule_engine.detect(doc.file_path, doc.language_id)
        except Exception:
            findings = []

        # Convert to IDE diagnostics
        diagnostics = []
        for finding in findings:
            diag = Diagnostic(
                id=f"diag-{uri}-{finding.line}",
                severity=self._severity_from_rule(finding.severity),
                message=finding.message,
                file_path=doc.file_path,
                range=Range(
                    start_line=finding.line,
                    start_col=0,
                    end_line=finding.line,
                    end_col=100,
                ),
                code=finding.rule_id,
                source="AI_SUPPORT",
            )
            diagnostics.append(diag)

        doc.diagnostics = diagnostics
        doc.dirty = False
        self._stats["diagnostics_sent"] += len(diagnostics)

        # Send to IDE
        await self._send_diagnostics(uri, diagnostics)

        return diagnostics

    def _schedule_diagnostics(self, uri: str) -> None:
        """Debounce diagnostics updates."""
        # Cancel existing task
        if uri in self._pending_diagnostics:
            self._pending_diagnostics[uri].cancel()

        async def run():
            await asyncio.sleep(self._debounce_ms / 1000.0)
            await self.run_diagnostics(uri)
            self._pending_diagnostics.pop(uri, None)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running event loop (sync context) — skip debounce scheduling
            return

        self._pending_diagnostics[uri] = asyncio.create_task(run())

    async def _send_diagnostics(self, uri: str, diagnostics: list[Diagnostic]) -> None:
        """Send diagnostics to the IDE."""
        message = {
            "type": MessageType.DIAGNOSTIC.value,
            "uri": uri,
            "diagnostics": [d.to_ide_message() for d in diagnostics],
            "version": self._documents[uri].version if uri in self._documents else 1,
        }
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    # ─── Hover ───────────────────────────────────────────────────────────────

    async def get_hover(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> Optional[HoverInfo]:
        """Get hover information for a position."""
        self._stats["hover_requests"] += 1
        doc = self._documents.get(uri)
        if not doc:
            return None

        # Try to get symbol info at position
        symbol = self._get_symbol_at_position(doc, line, character)
        if not symbol:
            return None

        hover = HoverInfo(
            contents=self._build_hover_markdown(symbol),
            signature=symbol.detail,
            symbol_type=symbol.kind,
        )

        return hover

    def _get_symbol_at_position(
        self,
        doc: TrackedDocument,
        line: int,
        character: int,
    ) -> Optional[DocumentSymbol]:
        """Find the symbol at a given position."""
        # Try symbol graph first
        try:
            from src.infrastructure.indexing.symbol_graph import SymbolGraph
            graph = SymbolGraph()
            # Get symbols from the graph
            # This is a simplified version
        except Exception:
            pass

        # Fallback: parse the document
        lines = doc.content.split("\n")
        if line >= len(lines):
            return None

        line_text = lines[line]

        # Find word at position
        start = character
        end = character
        while start > 0 and line_text[start - 1].isalnum():
            start -= 1
        while end < len(line_text) and line_text[end].isalnum() or line_text[end] == "_":
            end += 1

        word = line_text[start:end]
        if not word:
            return None

        # Search for the symbol in the document
        for search_line, content in enumerate(lines):
            if f"def {word}" in content or f"class {word}" in content or f"async def {word}" in content:
                return DocumentSymbol(
                    name=word,
                    kind="function" if "def " in content else "class",
                    detail=content.strip(),
                    range=Range(search_line, 0, search_line, len(content)),
                    selection_range=Range(search_line, start, search_line, end),
                )

        return None

    def _build_hover_markdown(self, symbol: DocumentSymbol) -> str:
        """Build markdown content for hover."""
        lines = [
            f"## `{symbol.name}`",
            f"**Kind:** {symbol.kind}",
        ]
        if symbol.detail:
            lines.append(f"\n```python\n{symbol.detail}\n```")
        if symbol.docstring:
            lines.append(f"\n{symbol.docstring}")
        return "\n".join(lines)

    # ─── Document symbols ───────────────────────────────────────────────────

    async def get_document_symbols(self, uri: str) -> list[DocumentSymbol]:
        """Get all symbols in a document."""
        self._stats["symbol_requests"] += 1
        doc = self._documents.get(uri)
        if not doc:
            return []

        symbols = self._extract_symbols(doc)
        return symbols

    def _extract_symbols(self, doc: TrackedDocument) -> list[DocumentSymbol]:
        """Extract symbols from document content."""
        symbols: list[DocumentSymbol] = []
        lines = doc.content.split("\n")

        for i, line in enumerate(lines):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Class
            if stripped.startswith("class ") and ":" in stripped:
                name = stripped.split("class ")[1].split("(")[0].split(":")[0].strip()
                symbols.append(DocumentSymbol(
                    name=name,
                    kind="class",
                    detail=stripped,
                    range=Range(i, 0, i, len(stripped)),
                    selection_range=Range(i, len(line) - len(stripped), i, len(line) - len(stripped) + len(name)),
                ))

            # Function/Method
            elif (stripped.startswith("def ") or stripped.startswith("async def ")) and "(" in stripped:
                prefix = "async def " if stripped.startswith("async def ") else "def "
                name = stripped.split(prefix)[1].split("(")[0].strip()
                symbols.append(DocumentSymbol(
                    name=name,
                    kind="method",
                    detail=stripped,
                    range=Range(i, 0, i, len(stripped)),
                    selection_range=Range(i, len(line) - len(stripped) + len(prefix), i, len(line) - len(stripped) + len(prefix) + len(name)),
                ))

            # Constant/Variable (module-level)
            elif i > 0 and (stripped.startswith("CONST ") or stripped.startswith("MY_")):
                name = stripped.split("=")[0].strip().split()[1] if "=" in stripped else stripped
                symbols.append(DocumentSymbol(
                    name=name,
                    kind="constant",
                    detail=stripped,
                    range=Range(i, 0, i, len(stripped)),
                    selection_range=Range(i, 0, i, len(name)),
                ))

        return symbols

    # ─── Formatting ─────────────────────────────────────────────────────────

    async def format_document(self, uri: str) -> list[dict[str, Any]]:
        """Format a document (returns text edits)."""
        doc = self._documents.get(uri)
        if not doc:
            return []

        # Simple format: strip trailing whitespace, ensure newline at end
        edits = []
        lines = doc.content.split("\n")

        for i, line in enumerate(lines):
            if line != line.rstrip():
                edits.append({
                    "range": {
                        "start": {"line": i, "character": len(line.rstrip())},
                        "end": {"line": i, "character": len(line)},
                    },
                    "newText": "",
                })

        # Add trailing newline if missing
        if doc.content and not doc.content.endswith("\n"):
            edits.append({
                "range": {
                    "start": {"line": len(lines) - 1, "character": len(lines[-1])},
                    "end": {"line": len(lines) - 1, "character": len(lines[-1])},
                },
                "newText": "\n",
            })

        return edits

    # ─── Go-to-definition ───────────────────────────────────────────────────

    async def goto_definition(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> Optional[dict[str, Any]]:
        """Go to definition of symbol at position."""
        doc = self._documents.get(uri)
        if not doc:
            return None

        lines = doc.content.split("\n")
        if line >= len(lines):
            return None

        # Extract word at position; grab the last word (most likely the symbol being invoked/defined)
        line_text = lines[line]
        import re as re_module

        # Fallback: grab first word if cursor couldn't extract one
        if not line_text.strip():
            return None

        words = re_module.findall(r"\w+", line_text)
        word = words[-1] if words else ""
        if not word:
            return None

        # Find definition in document
        for i, content in enumerate(lines):
            for pattern in [
                f"def {word}(",
                f"def {word}):",  # handles `def my_func():`
                f"class {word}(",
                f"async def {word}(",
            ]:
                if pattern in content:
                    return {
                        "uri": uri,
                        "range": {
                            "start": {"line": i, "character": 0},
                            "end": {"line": i, "character": len(content)},
                        },
                    }

        # Try symbol graph
        try:
            from src.infrastructure.indexing.symbol_graph import SymbolGraph
            graph = SymbolGraph()
            defs = graph.get_definitions(word)
            if defs:
                return defs[0]
        except Exception:
            pass

        return None

    # ─── Find references ────────────────────────────────────────────────────

    async def find_references(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> list[dict[str, Any]]:
        """Find all references to symbol at position."""
        doc = self._documents.get(uri)
        if not doc:
            return []

        lines = doc.content.split("\n")
        if line >= len(lines):
            return []

        # Find all occurrences
        references = []

        # Extract word at position; grab the last identifier word (likely the symbol)
        line_text = lines[line]
        import re as re_module

        # Fallback: grab last identifier word if cursor couldn't extract one
        if not line_text.strip():
            return []

        # Find all Python identifiers (alphanumeric + underscore)
        words = re_module.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", line_text)
        word = words[-1] if words else ""
        if not word:
            return []

        for i, content in enumerate(lines):
            if word in content:
                for m in re_module.finditer(rf"\b{re_module.escape(word)}\b", content):
                    references.append({
                        "uri": uri,
                        "range": {
                            "start": {"line": i, "character": m.start()},
                            "end": {"line": i, "character": m.end()},
                        },
                    })

        return references

    # ─── Helpers ────────────────────────────────────────────────────────────

    def _path_to_uri(self, file_path: str) -> str:
        """Convert file path to URI."""
        return f"file:///{file_path.replace('\\', '/')}"

    def _detect_language(self, file_path: str) -> str:
        """Detect language ID from file extension."""
        ext = Path(file_path).suffix
        langs = {
            ".py": "python", ".rs": "rust", ".js": "javascript",
            ".ts": "typescript", ".tsx": "typescriptreact",
            ".jsx": "javascriptreact", ".go": "go", ".java": "java",
            ".c": "c", ".h": "c", ".cpp": "cpp", ".cs": "csharp",
            ".rb": "ruby", ".swift": "swift", ".kt": "kotlin",
            ".sh": "shell", ".bash": "shell", ".zsh": "shell",
            ".sql": "sql", ".html": "html", ".css": "css",
            ".json": "json", ".yaml": "yaml", ".yml": "yaml",
            ".md": "markdown", ".xml": "xml", ".toml": "toml",
        }
        return langs.get(ext, "plaintext")

    def _severity_from_rule(self, severity: str) -> str:
        """Convert rule severity to diagnostic severity."""
        mapping = {
            "error": "error",
            "warning": "warning",
            "info": "info",
            "hint": "hint",
        }
        return mapping.get(severity.lower(), "info")

    # ─── Callbacks ───────────────────────────────────────────────────────────

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for messages from the IDE."""
        self._callbacks.append(callback)

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get live sync statistics."""
        return {
            **self._stats,
            "documents_tracked": len(self._documents),
            "pending_diagnostics": len(self._pending_diagnostics),
        }
