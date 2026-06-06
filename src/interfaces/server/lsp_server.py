"""AI_SUPPORT LSP Server — Real-time editor integration.

Provides a Language Server Protocol server that integrates AI_SUPPORT
analysis directly into editors (VS Code, Neovim, etc.) via:

- textDocument/publishDiagnostics — push errors/warnings inline
- textDocument/codeAction — suggest fixes on hover
- workspace/applyEdit — auto-apply fixes from editor

This bridges the gap between CLI-only analysis and real-time
inline-as-you-code experience.

Usage:
    python -m src.interfaces.server.lsp_server
    # Or via CLI:
    ai-support lsp --stdio
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ─── Protocol Constants ──────────────────────────────────────────────────────

LSP_SEVERITY_ERROR = 1
LSP_SEVERITY_WARNING = 2
LSP_SEVERITY_INFO = 3
LSP_SEVERITY_HINT = 4


# ─── Data Types ──────────────────────────────────────────────────────────────


class Position:
    """LSP Position (0-indexed line and character)."""

    __slots__ = ("line", "character")

    def __init__(self, line: int = 0, character: int = 0):
        self.line = line
        self.character = character

    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


class Range:
    """LSP Range."""

    __slots__ = ("start", "end")

    def __init__(self, start: Position | None = None, end: Position | None = None):
        self.start = start or Position()
        self.end = end or Position()

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}


class Diagnostic:
    """LSP Diagnostic item."""

    __slots__ = ("range", "severity", "code", "source", "message", "data")

    def __init__(
        self,
        range: Range,
        severity: int,
        code: str,
        source: str,
        message: str,
        data: dict | None = None,
    ):
        self.range = range
        self.severity = severity
        self.code = code
        self.source = source
        self.message = message
        self.data = data or {}

    def to_dict(self) -> dict[str, Any]:
        result = {
            "range": self.range.to_dict(),
            "severity": self.severity,
            "code": self.code,
            "source": self.source,
            "message": self.message,
        }
        if self.data:
            result["data"] = self.data
        return result


class TextEdit:
    """LSP TextEdit."""

    __slots__ = ("range", "new_text")

    def __init__(self, range: Range, new_text: str):
        self.range = range
        self.new_text = new_text

    def to_dict(self) -> dict[str, Any]:
        return {"range": self.range.to_dict(), "newText": self.new_text}


class CodeAction:
    """LSP CodeAction."""

    __slots__ = ("title", "kind", "diagnostics", "edit", "is_preferred")

    def __init__(
        self,
        title: str,
        kind: str = "quickfix",
        diagnostics: list[Diagnostic] | None = None,
        edit: dict | None = None,
        is_preferred: bool = False,
    ):
        self.title = title
        self.kind = kind
        self.diagnostics = diagnostics or []
        self.edit = edit
        self.is_preferred = is_preferred

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "title": self.title,
            "kind": self.kind,
        }
        if self.diagnostics:
            result["diagnostics"] = [d.to_dict() for d in self.diagnostics]
        if self.edit:
            result["edit"] = self.edit
        if self.is_preferred:
            result["isPreferred"] = True
        return result


# ─── LSP Server ──────────────────────────────────────────────────────────────


class AISupportLSPServer:
    """AI_SUPPORT Language Server.

    Implements the LSP protocol over stdio to provide:
    1. publishDiagnostics — real-time error reporting
    2. codeAction — suggest fixes for detected issues
    3. workspace/applyEdit — apply fixes directly in editor
    4. textDocument/didOpen, didChange, didSave — document sync
    5. textDocument/definition — go to definition (F12)
    6. textDocument/references — find all references (Shift+F12)
    7. textDocument/completion — inline code completion
    8. textDocument/rename — workspace-wide rename
    """

    def __init__(self, root_path: Path | None = None):
        self.root_path = root_path or Path.cwd()
        self._documents: dict[str, str] = {}  # uri -> content
        self._diagnostics_cache: dict[str, list[Diagnostic]] = {}
        self._request_id = 0
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._running = False

        # Lazy-loaded analysis engines
        self._rule_engine = None
        self._type_engine = None
        self._compile_fixer = None
        self._class_resolver = None
        self._symbol_index: dict[str, list[dict]] = {}  # name -> [{file, line, kind}]

    async def start_stdio(self) -> None:
        """Start the LSP server over stdio."""
        self._reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(self._reader)

        loop = asyncio.get_event_loop()
        await loop.connect_read_pipe(lambda: protocol, sys.stdin.buffer)

        transport, _ = await loop.connect_write_pipe(
            asyncio.Protocol, sys.stdout.buffer
        )
        self._writer = asyncio.StreamWriter(
            transport, protocol, self._reader, loop
        )

        self._running = True
        logger.info("AI_SUPPORT LSP Server started (stdio)")

        await self._message_loop()

    async def _message_loop(self) -> None:
        """Main message processing loop."""
        while self._running:
            try:
                message = await self._read_message()
                if message is None:
                    break

                response = await self._handle_message(message)
                if response is not None:
                    await self._send_message(response)

            except Exception as e:
                logger.error("LSP message loop error: %s", e)
                break

    async def _handle_message(self, message: dict) -> Optional[dict]:
        """Route incoming LSP message to handler."""
        method = message.get("method", "")
        params = message.get("params", {})
        msg_id = message.get("id")

        # Requests (expect response)
        if method == "initialize":
            return self._make_response(msg_id, self._handle_initialize(params))
        elif method == "textDocument/codeAction":
            result = await self._handle_code_action(params)
            return self._make_response(msg_id, result)
        elif method == "textDocument/diagnostic":
            result = await self._handle_pull_diagnostics(params)
            return self._make_response(msg_id, result)
        elif method == "textDocument/definition":
            result = self._handle_goto_definition(params)
            return self._make_response(msg_id, result)
        elif method == "textDocument/references":
            result = self._handle_find_references(params)
            return self._make_response(msg_id, result)
        elif method == "textDocument/completion":
            result = self._handle_completion(params)
            return self._make_response(msg_id, result)
        elif method == "textDocument/rename":
            result = self._handle_rename(params)
            return self._make_response(msg_id, result)
        elif method == "shutdown":
            self._running = False
            return self._make_response(msg_id, None)

        # Notifications (no response)
        elif method == "initialized":
            pass
        elif method == "textDocument/didOpen":
            await self._handle_did_open(params)
        elif method == "textDocument/didChange":
            await self._handle_did_change(params)
        elif method == "textDocument/didSave":
            await self._handle_did_save(params)
        elif method == "textDocument/didClose":
            self._handle_did_close(params)
        elif method == "exit":
            self._running = False

        return None

    def _handle_initialize(self, params: dict) -> dict:
        """Handle initialize request — declare server capabilities."""
        if "rootUri" in params:
            uri = params["rootUri"]
            if uri.startswith("file://"):
                self.root_path = Path(uri[7:])

        return {
            "capabilities": {
                "textDocumentSync": {
                    "openClose": True,
                    "change": 1,  # Full sync
                    "save": {"includeText": True},
                },
                "codeActionProvider": {
                    "codeActionKinds": [
                        "quickfix",
                        "refactor",
                        "source.fixAll",
                    ],
                },
                "diagnosticProvider": {
                    "interFileDependencies": True,
                    "workspaceDiagnostics": False,
                },
                "definitionProvider": True,
                "referencesProvider": True,
                "completionProvider": {
                    "triggerCharacters": [".", "(", "[", '"', "'"],
                    "resolveProvider": False,
                },
                "renameProvider": {
                    "prepareProvider": False,
                },
            },
            "serverInfo": {
                "name": "ai-support-lsp",
                "version": "0.2.0",
            },
        }

    async def _handle_did_open(self, params: dict) -> None:
        """Handle textDocument/didOpen — store content and analyze."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        text = td.get("text", "")

        self._documents[uri] = text
        self._index_document_symbols(uri, text)
        await self._analyze_and_publish(uri, text)

    async def _handle_did_change(self, params: dict) -> None:
        """Handle textDocument/didChange — update content and re-analyze."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        changes = params.get("contentChanges", [])

        if changes:
            # Full sync mode: take last change as full content
            self._documents[uri] = changes[-1].get("text", "")
            await self._analyze_and_publish(uri, self._documents[uri])

    async def _handle_did_save(self, params: dict) -> None:
        """Handle textDocument/didSave — full re-analysis."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        text = params.get("text") or self._documents.get(uri, "")

        if text:
            self._documents[uri] = text
        await self._analyze_and_publish(uri, self._documents.get(uri, ""))

    def _handle_did_close(self, params: dict) -> None:
        """Handle textDocument/didClose — clean up."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        self._documents.pop(uri, None)
        self._diagnostics_cache.pop(uri, None)

    async def _handle_code_action(self, params: dict) -> list[dict]:
        """Handle textDocument/codeAction — return fix suggestions.

        Returns code actions based on:
        1. Cached diagnostics for the range
        2. AI_SUPPORT rule-based fixes
        3. Compile-error-driven fixes
        """
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        context = params.get("context", {})

        actions = []
        diagnostics = self._diagnostics_cache.get(uri, [])
        content = self._documents.get(uri, "")

        # Get diagnostics in the requested range
        req_range = params.get("range", {})
        start_line = req_range.get("start", {}).get("line", 0)
        end_line = req_range.get("end", {}).get("line", 0)

        relevant_diags = [
            d for d in diagnostics
            if start_line <= d.range.start.line <= end_line
        ]

        for diag in relevant_diags:
            fix = self._generate_fix_for_diagnostic(diag, uri, content)
            if fix:
                actions.append(fix.to_dict())

        return actions

    async def _handle_pull_diagnostics(self, params: dict) -> dict:
        """Handle textDocument/diagnostic (pull model)."""
        td = params.get("textDocument", {})
        uri = td.get("uri", "")

        diagnostics = self._diagnostics_cache.get(uri, [])
        return {
            "kind": "full",
            "items": [d.to_dict() for d in diagnostics],
        }

    # ─── Go To Definition ────────────────────────────────────────────────────

    def _handle_goto_definition(self, params: dict) -> list[dict] | None:
        """Handle textDocument/definition — navigate to symbol definition.

        Uses the symbol index built from open documents and class resolver
        for inherited member lookup.
        """
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)

        content = self._documents.get(uri, "")
        if not content:
            return None

        # Get the symbol name at position
        symbol = self._get_symbol_at_position(content, line, character)
        if not symbol:
            return None

        # Search symbol index for definition
        locations = self._find_definition(symbol, uri)
        if locations:
            return locations

        return None

    def _handle_find_references(self, params: dict) -> list[dict]:
        """Handle textDocument/references — find all references to a symbol.

        Searches all open documents for occurrences of the symbol.
        """
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)
        context = params.get("context", {})
        include_declaration = context.get("includeDeclaration", True)

        content = self._documents.get(uri, "")
        if not content:
            return []

        symbol = self._get_symbol_at_position(content, line, character)
        if not symbol:
            return []

        references = []

        # Search all open documents for references
        for doc_uri, doc_content in self._documents.items():
            doc_refs = self._find_references_in_content(
                symbol, doc_uri, doc_content
            )
            references.extend(doc_refs)

        return references

    # ─── Code Completion ─────────────────────────────────────────────────────

    def _handle_completion(self, params: dict) -> dict:
        """Handle textDocument/completion — provide inline code completions.

        Returns completions from:
        1. Local variables and function parameters (scope)
        2. Imported symbols
        3. Built-in functions and types
        4. Class members (after '.')
        """
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)

        content = self._documents.get(uri, "")
        if not content:
            return {"isIncomplete": False, "items": []}

        items = self._compute_completions(content, line, character, uri)

        return {
            "isIncomplete": len(items) > 50,
            "items": items[:50],  # Cap at 50 items
        }

    # ─── Workspace Rename ────────────────────────────────────────────────────

    def _handle_rename(self, params: dict) -> dict | None:
        """Handle textDocument/rename — workspace-wide symbol rename.

        Collects all references across open documents and returns a
        WorkspaceEdit with text edits for each file.
        """
        td = params.get("textDocument", {})
        uri = td.get("uri", "")
        position = params.get("position", {})
        line = position.get("line", 0)
        character = position.get("character", 0)
        new_name = params.get("newName", "")

        if not new_name:
            return None

        content = self._documents.get(uri, "")
        if not content:
            return None

        symbol = self._get_symbol_at_position(content, line, character)
        if not symbol:
            return None

        # Collect all references across workspace
        changes: dict[str, list[dict]] = {}

        for doc_uri, doc_content in self._documents.items():
            edits = self._compute_rename_edits(symbol, new_name, doc_uri, doc_content)
            if edits:
                changes[doc_uri] = edits

        if not changes:
            return None

        return {"changes": changes}

    # ─── Analysis Integration ────────────────────────────────────────────────

    async def _analyze_and_publish(self, uri: str, content: str) -> None:
        """Run AI_SUPPORT analysis and publish diagnostics.

        Runs:
        1. Rule engine (static analysis rules)
        2. Type inference (type errors)
        3. Compile error check (syntax errors)
        """
        if not content:
            return

        file_path = self._uri_to_path(uri)
        if not file_path or not file_path.suffix == ".py":
            return

        diagnostics: list[Diagnostic] = []

        # Run analysis in background to avoid blocking
        try:
            diagnostics.extend(self._run_static_analysis(content, file_path))
            diagnostics.extend(self._run_type_analysis(content, file_path))
        except Exception as e:
            logger.debug("Analysis error for %s: %s", uri, e)

        self._diagnostics_cache[uri] = diagnostics

        # Publish diagnostics (push model)
        await self._publish_diagnostics(uri, diagnostics)

    def _run_static_analysis(
        self, content: str, file_path: Path
    ) -> list[Diagnostic]:
        """Run rule-based static analysis."""
        diagnostics = []

        # Import rule engine lazily
        try:
            if self._rule_engine is None:
                from src.infrastructure.analysis.rule_engine import RuleEngine
                self._rule_engine = RuleEngine()
        except ImportError:
            return diagnostics

        try:
            results = self._rule_engine.analyze(content, str(file_path))
            for result in results:
                severity = LSP_SEVERITY_WARNING
                if hasattr(result, "severity"):
                    if result.severity == "error":
                        severity = LSP_SEVERITY_ERROR
                    elif result.severity == "info":
                        severity = LSP_SEVERITY_INFO

                line = getattr(result, "line", 1) - 1  # 0-indexed
                col = getattr(result, "column", 0)
                msg = getattr(result, "message", str(result))
                code = getattr(result, "rule_id", "ai-support")

                diagnostics.append(Diagnostic(
                    range=Range(
                        start=Position(line=line, character=col),
                        end=Position(line=line, character=col + 20),
                    ),
                    severity=severity,
                    code=code,
                    source="ai-support",
                    message=msg,
                    data={"fix_available": hasattr(result, "fix")},
                ))
        except Exception as e:
            logger.debug("Rule engine error: %s", e)

        return diagnostics

    def _run_type_analysis(
        self, content: str, file_path: Path
    ) -> list[Diagnostic]:
        """Run type inference analysis for type errors."""
        diagnostics = []

        try:
            if self._type_engine is None:
                from src.infrastructure.analysis.type_inference import TypeInferenceEngine
                self._type_engine = TypeInferenceEngine()
        except ImportError:
            return diagnostics

        # Type inference doesn't produce diagnostics directly,
        # but we can detect some patterns:
        # - Unreachable code after unconditional return
        # - Inconsistent return types without Union annotation
        try:
            import ast
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    self._check_return_type_consistency(node, diagnostics)
        except SyntaxError:
            pass

        return diagnostics

    def _check_return_type_consistency(
        self, func_node, diagnostics: list[Diagnostic]
    ) -> None:
        """Check if function return type annotation matches inferred type."""
        if not func_node.returns:
            return  # No annotation to check against

        inferred = self._type_engine.infer_return_type(func_node)
        if not inferred or inferred.source == "annotation":
            return

        # Compare annotation with inference
        import ast
        annotation = ast.unparse(func_node.returns) if hasattr(ast, "unparse") else ""
        if not annotation:
            return

        # Simple mismatch detection
        if (
            inferred.type_str != annotation
            and inferred.confidence >= 0.85
            and "|" in inferred.type_str
            and "|" not in annotation
        ):
            diagnostics.append(Diagnostic(
                range=Range(
                    start=Position(line=func_node.lineno - 1, character=0),
                    end=Position(line=func_node.lineno - 1, character=80),
                ),
                severity=LSP_SEVERITY_INFO,
                code="ai-support-type-mismatch",
                source="ai-support",
                message=(
                    f"Function '{func_node.name}' annotated as -> {annotation} "
                    f"but inferred return type is {inferred.type_str}"
                ),
            ))

    def _generate_fix_for_diagnostic(
        self, diag: Diagnostic, uri: str, content: str
    ) -> Optional[CodeAction]:
        """Generate a code action fix for a diagnostic."""
        # Check if fix data is available
        if not diag.data.get("fix_available"):
            return None

        # Try compile-error-driven fixes
        try:
            if self._compile_fixer is None:
                from src.infrastructure.analysis.compile_error_fixer import (
                    CompileError,
                    generate_fix,
                )
                self._compile_fixer = generate_fix

            error = CompileError(
                file=self._uri_to_path(uri) or "",
                line=diag.range.start.line + 1,
                column=diag.range.start.character,
                error_type=diag.code,
                message=diag.message,
            )

            fix = self._compile_fixer(error, content)
            if fix and fix.new_code:
                text_edit = TextEdit(
                    range=diag.range,
                    new_text=fix.new_code,
                )
                return CodeAction(
                    title=fix.fix_description,
                    kind="quickfix",
                    diagnostics=[diag],
                    edit={
                        "changes": {
                            uri: [text_edit.to_dict()],
                        },
                    },
                    is_preferred=True,
                )
        except (ImportError, Exception) as e:
            logger.debug("Fix generation error: %s", e)

        return None

    async def _publish_diagnostics(
        self, uri: str, diagnostics: list[Diagnostic]
    ) -> None:
        """Send textDocument/publishDiagnostics notification."""
        notification = {
            "jsonrpc": "2.0",
            "method": "textDocument/publishDiagnostics",
            "params": {
                "uri": uri,
                "diagnostics": [d.to_dict() for d in diagnostics],
            },
        }
        await self._send_message(notification)

    async def apply_edit(self, uri: str, edits: list[TextEdit], label: str = "") -> None:
        """Send workspace/applyEdit request to editor.

        This allows the server to push edits to the editor.
        """
        request = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "workspace/applyEdit",
            "params": {
                "label": label or "AI_SUPPORT fix",
                "edit": {
                    "changes": {
                        uri: [e.to_dict() for e in edits],
                    },
                },
            },
        }
        await self._send_message(request)

    # ─── Symbol Resolution Helpers ───────────────────────────────────────────

    def _get_symbol_at_position(
        self, content: str, line: int, character: int
    ) -> Optional[str]:
        """Extract the symbol (identifier) at the given position."""
        lines = content.split("\n")
        if line >= len(lines):
            return None

        text_line = lines[line]
        if character >= len(text_line):
            return None

        # Expand from character position to get full identifier
        start = character
        end = character

        while start > 0 and (text_line[start - 1].isalnum() or text_line[start - 1] == "_"):
            start -= 1
        while end < len(text_line) and (text_line[end].isalnum() or text_line[end] == "_"):
            end += 1

        word = text_line[start:end]
        if not word or not (word[0].isalpha() or word[0] == "_"):
            return None

        return word

    def _find_definition(self, symbol: str, current_uri: str) -> list[dict]:
        """Find definition of a symbol across indexed documents."""
        import ast as _ast

        locations = []

        # Search all open documents for definitions
        for uri, content in self._documents.items():
            try:
                tree = _ast.parse(content)
            except SyntaxError:
                continue

            for node in _ast.walk(tree):
                # Function/method definitions
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    if node.name == symbol:
                        locations.append({
                            "uri": uri,
                            "range": Range(
                                start=Position(line=node.lineno - 1, character=0),
                                end=Position(
                                    line=node.lineno - 1,
                                    character=len(f"def {symbol}"),
                                ),
                            ).to_dict(),
                        })

                # Class definitions
                elif isinstance(node, _ast.ClassDef):
                    if node.name == symbol:
                        locations.append({
                            "uri": uri,
                            "range": Range(
                                start=Position(line=node.lineno - 1, character=0),
                                end=Position(
                                    line=node.lineno - 1,
                                    character=len(f"class {symbol}"),
                                ),
                            ).to_dict(),
                        })

                # Variable assignments (top-level or annotated)
                elif isinstance(node, _ast.Assign):
                    for target in node.targets:
                        if isinstance(target, _ast.Name) and target.id == symbol:
                            locations.append({
                                "uri": uri,
                                "range": Range(
                                    start=Position(line=node.lineno - 1, character=0),
                                    end=Position(
                                        line=node.lineno - 1,
                                        character=len(symbol),
                                    ),
                                ).to_dict(),
                            })

                elif isinstance(node, _ast.AnnAssign):
                    if isinstance(node.target, _ast.Name) and node.target.id == symbol:
                        locations.append({
                            "uri": uri,
                            "range": Range(
                                start=Position(line=node.lineno - 1, character=0),
                                end=Position(
                                    line=node.lineno - 1,
                                    character=len(symbol),
                                ),
                            ).to_dict(),
                        })

        # Also check class resolver for inherited members
        if not locations and self._class_resolver:
            member = self._class_resolver.resolve_member(symbol, symbol)
            if member:
                locations.append({
                    "uri": self._path_to_uri(member.file_path),
                    "range": Range(
                        start=Position(line=member.line - 1, character=0),
                        end=Position(line=member.line - 1, character=len(symbol)),
                    ).to_dict(),
                })

        return locations

    def _find_references_in_content(
        self, symbol: str, uri: str, content: str
    ) -> list[dict]:
        """Find all references to a symbol in a document."""
        import re as _re

        references = []
        # Use word boundary regex to find all occurrences
        pattern = _re.compile(r'\b' + _re.escape(symbol) + r'\b')

        for i, line in enumerate(content.split("\n")):
            for match in pattern.finditer(line):
                references.append({
                    "uri": uri,
                    "range": Range(
                        start=Position(line=i, character=match.start()),
                        end=Position(line=i, character=match.end()),
                    ).to_dict(),
                })

        return references

    def _compute_completions(
        self, content: str, line: int, character: int, uri: str
    ) -> list[dict]:
        """Compute completion items for the given position."""
        import ast as _ast

        items: list[dict] = []
        lines = content.split("\n")

        # Check if this is a dot-completion (obj.)
        if line < len(lines) and character > 0:
            text_before = lines[line][:character]
            if text_before.rstrip().endswith("."):
                return self._compute_member_completions(content, text_before, uri)

        # Collect symbols from the current file
        try:
            tree = _ast.parse(content)
        except SyntaxError:
            return items

        seen: set[str] = set()

        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                if node.name not in seen:
                    seen.add(node.name)
                    items.append({
                        "label": node.name,
                        "kind": 3,  # Function
                        "detail": f"def {node.name}(...)",
                        "sortText": f"0_{node.name}",
                    })
                # Add parameters as local variables
                for arg in node.args.args:
                    if arg.arg not in seen and arg.arg != "self":
                        seen.add(arg.arg)
                        items.append({
                            "label": arg.arg,
                            "kind": 6,  # Variable
                            "detail": "parameter",
                            "sortText": f"1_{arg.arg}",
                        })

            elif isinstance(node, _ast.ClassDef):
                if node.name not in seen:
                    seen.add(node.name)
                    items.append({
                        "label": node.name,
                        "kind": 7,  # Class
                        "detail": f"class {node.name}",
                        "sortText": f"0_{node.name}",
                    })

            elif isinstance(node, _ast.Assign):
                for target in node.targets:
                    if isinstance(target, _ast.Name) and target.id not in seen:
                        seen.add(target.id)
                        items.append({
                            "label": target.id,
                            "kind": 6,  # Variable
                            "sortText": f"1_{target.id}",
                        })

            elif isinstance(node, _ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[-1]
                    if name not in seen:
                        seen.add(name)
                        items.append({
                            "label": name,
                            "kind": 9,  # Module
                            "detail": f"import {alias.name}",
                            "sortText": f"2_{name}",
                        })

            elif isinstance(node, _ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name not in seen:
                        seen.add(name)
                        items.append({
                            "label": name,
                            "kind": 9,  # Module
                            "detail": f"from {node.module} import {alias.name}",
                            "sortText": f"2_{name}",
                        })

        # Add Python builtins
        builtins = [
            "print", "len", "range", "int", "str", "float", "bool",
            "list", "dict", "set", "tuple", "None", "True", "False",
            "isinstance", "hasattr", "getattr", "setattr", "type",
            "super", "property", "staticmethod", "classmethod",
            "enumerate", "zip", "map", "filter", "sorted", "reversed",
        ]
        for b in builtins:
            if b not in seen:
                items.append({
                    "label": b,
                    "kind": 21,  # Constant / builtin
                    "sortText": f"9_{b}",
                })

        return items

    def _compute_member_completions(
        self, content: str, text_before: str, uri: str
    ) -> list[dict]:
        """Compute member completions after a dot (obj.xxx)."""
        import ast as _ast
        import re as _re

        items: list[dict] = []

        # Extract the receiver name: "self." or "obj." or "ClassName."
        match = _re.search(r'(\w+)\.\s*$', text_before)
        if not match:
            return items

        receiver = match.group(1)

        # Try parsing the content — add a placeholder to make it valid
        parse_content = content
        try:
            _ast.parse(parse_content)
        except SyntaxError:
            # Replace the incomplete last line with 'pass' to make it parseable
            lines = content.split("\n")
            if lines:
                indent = len(lines[-1]) - len(lines[-1].lstrip())
                lines[-1] = " " * indent + "pass"
            parse_content = "\n".join(lines)
            try:
                _ast.parse(parse_content)
            except SyntaxError:
                # Remove the last line entirely
                parse_content = "\n".join(lines[:-1]) + "\n"
                try:
                    _ast.parse(parse_content)
                except SyntaxError:
                    return items

        try:
            tree = _ast.parse(parse_content)
        except SyntaxError:
            return items

        if receiver == "self":
            # Find all methods/attributes in the enclosing class
            for node in _ast.walk(tree):
                if isinstance(node, _ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                            if item.name != "__init__":
                                items.append({
                                    "label": item.name,
                                    "kind": 2,  # Method
                                    "detail": f"method of {node.name}",
                                })
                        elif isinstance(item, _ast.AnnAssign):
                            if isinstance(item.target, _ast.Name):
                                items.append({
                                    "label": item.target.id,
                                    "kind": 5,  # Field
                                    "detail": "attribute",
                                })
                    # Also scan __init__ for self.attr assignments
                    for item in node.body:
                        if isinstance(item, _ast.FunctionDef) and item.name == "__init__":
                            for stmt in _ast.walk(item):
                                if isinstance(stmt, _ast.Assign):
                                    for t in stmt.targets:
                                        if (
                                            isinstance(t, _ast.Attribute)
                                            and isinstance(t.value, _ast.Name)
                                            and t.value.id == "self"
                                        ):
                                            items.append({
                                                "label": t.attr,
                                                "kind": 5,  # Field
                                                "detail": "instance attribute",
                                            })
                    break  # Use first class found
        else:
            # Check if receiver is a class name → show class methods
            for node in _ast.walk(tree):
                if isinstance(node, _ast.ClassDef) and node.name == receiver:
                    for item in node.body:
                        if isinstance(item, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                            items.append({
                                "label": item.name,
                                "kind": 2,  # Method
                                "detail": f"method of {receiver}",
                            })

        return items

    def _compute_rename_edits(
        self, symbol: str, new_name: str, uri: str, content: str
    ) -> list[dict]:
        """Compute text edits for renaming a symbol in a document.

        Only renames identifiers in code, skips comments and strings.
        """
        import re as _re

        edits = []
        pattern = _re.compile(r'\b' + _re.escape(symbol) + r'\b')

        for i, line in enumerate(content.split("\n")):
            # Skip comment lines
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue

            # Skip occurrences inside strings (simple heuristic)
            # Remove string contents before matching
            code_part = self._strip_strings(line)

            for match in pattern.finditer(code_part):
                # Verify the match position is valid in original line
                if match.start() < len(line):
                    edits.append(TextEdit(
                        range=Range(
                            start=Position(line=i, character=match.start()),
                            end=Position(line=i, character=match.end()),
                        ),
                        new_text=new_name,
                    ).to_dict())

        return edits

    def _strip_strings(self, line: str) -> str:
        """Replace string contents with spaces to avoid renaming inside strings."""
        import re as _re
        # Replace triple-quoted, double-quoted, and single-quoted strings
        result = _re.sub(r'""".*?"""', lambda m: " " * len(m.group()), line)
        result = _re.sub(r"'''.*?'''", lambda m: " " * len(m.group()), result)
        result = _re.sub(r'"[^"]*"', lambda m: " " * len(m.group()), result)
        result = _re.sub(r"'[^']*'", lambda m: " " * len(m.group()), result)
        return result

    def _path_to_uri(self, file_path) -> str:
        """Convert a Path to file URI."""
        path_str = str(file_path).replace("\\", "/")
        if not path_str.startswith("/"):
            path_str = "/" + path_str
        return f"file://{path_str}"

    def _index_document_symbols(self, uri: str, content: str) -> None:
        """Index symbols in a document for fast lookup."""
        import ast as _ast

        try:
            tree = _ast.parse(content)
        except SyntaxError:
            return

        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                entry = {"uri": uri, "line": node.lineno, "kind": "function"}
                self._symbol_index.setdefault(node.name, []).append(entry)
            elif isinstance(node, _ast.ClassDef):
                entry = {"uri": uri, "line": node.lineno, "kind": "class"}
                self._symbol_index.setdefault(node.name, []).append(entry)

    # ─── Protocol I/O ────────────────────────────────────────────────────────

    async def _read_message(self) -> Optional[dict]:
        """Read one LSP message from stdin."""
        import json

        if not self._reader:
            return None

        # Read headers
        content_length = 0
        while True:
            line = await self._reader.readline()
            if not line:
                return None

            header = line.decode("utf-8").strip()
            if not header:
                break  # Empty line separates headers from content

            if header.startswith("Content-Length:"):
                content_length = int(header.split(":")[1].strip())

        if content_length == 0:
            return None

        # Read content
        data = await self._reader.readexactly(content_length)
        return json.loads(data.decode("utf-8"))

    async def _send_message(self, message: dict) -> None:
        """Write one LSP message to stdout."""
        import json

        if not self._writer:
            return

        content = json.dumps(message).encode("utf-8")
        header = f"Content-Length: {len(content)}\r\n\r\n".encode("utf-8")

        self._writer.write(header + content)
        await self._writer.drain()

    def _make_response(self, msg_id: Any, result: Any) -> dict:
        """Create a JSON-RPC response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }

    def _next_id(self) -> int:
        """Generate next request ID."""
        self._request_id += 1
        return self._request_id

    def _uri_to_path(self, uri: str) -> Optional[Path]:
        """Convert file URI to Path."""
        if uri.startswith("file:///"):
            # Windows: file:///C:/path → C:/path
            path_str = uri[8:] if uri[9] == ":" else uri[7:]
            return Path(path_str.replace("/", "\\"))
        elif uri.startswith("file://"):
            return Path(uri[7:])
        return None


# ─── Entry Point ─────────────────────────────────────────────────────────────


def main() -> None:
    """Run the AI_SUPPORT LSP server."""
    logging.basicConfig(
        level=logging.DEBUG,
        filename="ai_support_lsp.log",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    server = AISupportLSPServer()
    asyncio.run(server.start_stdio())


if __name__ == "__main__":
    main()
