"""LSP Server for AI_SUPPORT — provides go-to-def, hover, references, diagnostics.

Integrates with:
- SafeTreeSitterIndexer: real AST parsing
- SymbolGraph: call graph and symbol tracking
- MLDetector: code quality diagnostics

Supports Python, C/C++, JavaScript/TypeScript, Rust, Go, Java.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# pygls imports with graceful fallback
try:
    from pygls.server import LanguageServer
    from pygls.types import (
        CompletionItem,
        CompletionList,
        CompletionParams,
        DefinitionParams,
        Diagnostic,
        DiagnosticSeverity,
        Hover,
        HoverParams,
        Location,
        MarkupContent,
        MarkupKind,
        Position,
        Range,
        ReferencesParams,
        TextDocumentIdentifier,
        TextDocumentItem,
        TextDocumentPositionParams,
        WorkspaceFolder,
        TEXT_DOCUMENT_DID_CHANGE,
        TEXT_DOCUMENT_DID_CLOSE,
        TEXT_DOCUMENT_DID_OPEN,
        TEXT_DOCUMENT_DID_SAVE,
        PUBLISH_DIAGNOSTICS,
    )
    PYGLS_AVAILABLE = True
except ImportError:
    logger.warning("pygls not installed. LSP server will be disabled.")
    PYGLS_AVAILABLE = False
    LanguageServer = object  # type: ignore

# Local imports
try:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
    from src.infrastructure.indexing.symbol_graph import SymbolGraph
    from src.infrastructure.analysis.ml_detectors import MLDetector
except ImportError as e:
    logger.warning("Failed to import AI_SUPPORT modules: %s", e)
    SafeTreeSitterIndexer = None  # type: ignore
    SymbolGraph = None  # type: ignore
    MLDetector = None  # type: ignore


# ─── LSP Symbol Kind Mapping ─────────────────────────────────────────────────

_LSP_SYMBOL_KINDS: dict[str, int] = {
    "file": 1, "module": 2, "namespace": 3, "package": 4,
    "class": 5, "enum": 6, "interface": 7, "struct": 8,
    "typeParameter": 9, "string": 10, "number": 11, "boolean": 12,
    "array": 13, "object": 14, "key": 15, "null": 16,
    "enumMember": 17, "event": 18, "operator": 19,
    "function": 22, "method": 6, "variable": 24,
    "constant": 25, "parameter": 26, "property": 27,
    "type": 25, "impl": 10, "trait": 22,
}


def _kind_to_lsp(kind: str) -> int:
    """Convert AI_SUPPORT symbol kind to LSP symbol kind."""
    return _LSP_SYMBOL_KINDS.get(kind.lower(), 1)


def _severity_to_lsp(severity: str) -> int:
    """Convert AI_SUPPORT severity to LSP diagnostic severity."""
    mapping = {
        "error": DiagnosticSeverity.Error,
        "warning": DiagnosticSeverity.Warning,
        "info": DiagnosticSeverity.Information,
        "hint": DiagnosticSeverity.Hint,
    }
    return mapping.get(severity.lower(), DiagnosticSeverity.Information)


# ─── Document Tracking ────────────────────────────────────────────────────────

@dataclass
class LSPDocument:
    """An open document in the LSP server."""
    uri: str
    file_path: str
    content: str
    version: int = 1
    language_id: str = "plaintext"
    diagnostics: list[Diagnostic] = field(default_factory=list)


# ─── Capabilities ────────────────────────────────────────────────────────────

@dataclass
class LSPCapabilities:
    """Server capabilities advertised to the client."""
    hover_provider: bool = True
    definition_provider: bool = True
    references_provider: bool = True
    completion_provider: bool = True
    diagnostic_provider: bool = True
    document_symbol_provider: bool = True
    text_document_sync_kind: int = 1  # Full sync


# ─── Main LSP Server ─────────────────────────────────────────────────────────

if PYGLS_AVAILABLE:
    class AISupportLanguageServer(LanguageServer):
        """AI_SUPPORT LSP server providing IDE-like features.

        Features:
        - Go-to-definition (F12)
        - Find all references
        - Hover info (type signatures, docstrings)
        - Inline diagnostics (ML-based code analysis)
        - Auto-completion
        - Document symbols

        Usage:
            server = AISupportLanguageServer()
            server.start_io()  # stdio mode
            # or
            server.start_tcp(host="localhost", port=8765)
        """

        def __init__(
            self,
            root_path: str | None = None,
            debounce_ms: int = 300,
        ):
            super().__init__()

            self.root_path = root_path or os.getcwd()
            self._debounce_ms = debounce_ms

            # Document tracking
            self._documents: dict[str, LSPDocument] = {}
            self._pending_diagnostics: dict[str, asyncio.Task] = {}

            # AI_SUPPORT integration
            self._indexer: Optional["SafeTreeSitterIndexer"] = None
            self._symbol_graph: Optional["SymbolGraph"] = None
            self._ml_detector: Optional["MLDetector"] = None

            # Statistics
            self._stats = {
                "documents_opened": 0,
                "definitions_found": 0,
                "references_found": 0,
                "hovers_resolved": 0,
                "diagnostics_sent": 0,
                "completions_served": 0,
            }

            self._initialize_components()

        def _initialize_components(self) -> None:
            """Initialize AI_SUPPORT components lazily."""
            if SafeTreeSitterIndexer is not None:
                try:
                    self._indexer = SafeTreeSitterIndexer()
                    logger.info("LSP: SafeTreeSitterIndexer initialized")
                except Exception as e:
                    logger.warning("LSP: Failed to initialize indexer: %s", e)

            if SymbolGraph is not None:
                try:
                    self._symbol_graph = SymbolGraph(indexer=self._indexer)
                    logger.info("LSP: SymbolGraph initialized")
                except Exception as e:
                    logger.warning("LSP: Failed to initialize symbol graph: %s", e)

            if MLDetector is not None:
                try:
                    self._ml_detector = MLDetector()
                    logger.info("LSP: MLDetector initialized")
                except Exception as e:
                    logger.warning("LSP: Failed to initialize ML detector: %s", e)

        # ─── Document Management ───────────────────────────────────────────────

        def _get_document(self, uri: str) -> Optional[LSPDocument]:
            """Get tracked document by URI."""
            return self._documents.get(uri)

        def _uri_to_path(self, uri: str) -> str:
            """Convert file URI to filesystem path."""
            if uri.startswith("file://"):
                path = uri[7:]
                # Handle Windows paths
                if path.startswith("/"):
                    path = path[1:]
                return path.replace("/", "\\")
            return uri

        def _path_to_uri(self, path: str) -> str:
            """Convert filesystem path to file URI."""
            return f"file:///{path.replace('\\', '/')}"

        def _detect_language(self, file_path: str) -> str:
            """Detect LSP language ID from file extension."""
            ext = Path(file_path).suffix.lower()
            langs = {
                ".py": "python",
                ".rs": "rust",
                ".js": "javascript",
                ".ts": "typescript",
                ".tsx": "typescriptreact",
                ".jsx": "javascriptreact",
                ".go": "go",
                ".java": "java",
                ".c": "c",
                ".h": "c",
                ".cpp": "cpp",
                ".cc": "cpp",
                ".cxx": "cpp",
                ".hpp": "cpp",
                ".cs": "csharp",
                ".rb": "ruby",
                ".swift": "swift",
                ".kt": "kotlin",
                ".sh": "shell",
                ".bash": "shell",
                ".zsh": "shell",
                ".sql": "sql",
                ".html": "html",
                ".htm": "html",
                ".css": "css",
                ".json": "json",
                ".yaml": "yaml",
                ".yml": "yaml",
                ".md": "markdown",
                ".xml": "xml",
                ".toml": "toml",
            }
            return langs.get(ext, "plaintext")

        # ─── Text Document Sync ──────────────────────────────────────────────

        @self.feature(TEXT_DOCUMENT_DID_OPEN)
        async def text_document_did_open(self, params: TextDocumentItem) -> None:
            """Handle text document open."""
            file_path = self._uri_to_path(params.uri)
            language_id = self._detect_language(file_path)

            doc = LSPDocument(
                uri=params.uri,
                file_path=file_path,
                content=params.text,
                version=params.version or 1,
                language_id=language_id,
            )
            self._documents[params.uri] = doc
            self._stats["documents_opened"] += 1

            logger.debug("LSP: Document opened: %s", file_path)

            # Index the file and run diagnostics
            await self._index_file_async(file_path, params.text)
            await self._run_diagnostics(params.uri)

        @self.feature(TEXT_DOCUMENT_DID_CHANGE)
        async def text_document_did_change(self, params: Any) -> None:
            """Handle text document changes (full sync)."""
            # Get the URI from the text document
            uri = getattr(params, "text_document", params).uri
            doc = self._documents.get(uri)
            if not doc:
                return

            # Get full content from changes
            changes = getattr(params, "content_changes", params.get("contentChanges", []))
            if changes and hasattr(changes[0], "text"):
                doc.content = changes[0].text
            elif changes and isinstance(changes[0], dict):
                doc.content = changes[0].get("text", doc.content)

            doc.version += 1

            # Debounce diagnostics
            self._schedule_diagnostics(uri)

        @self.feature(TEXT_DOCUMENT_DID_SAVE)
        async def text_document_did_save(self, params: Any) -> None:
            """Handle text document save."""
            uri = getattr(params, "text_document", params).uri
            await self._run_diagnostics(uri)

        @self.feature(TEXT_DOCUMENT_DID_CLOSE)
        async def text_document_did_close(self, params: Any) -> None:
            """Handle text document close."""
            uri = getattr(params, "text_document", params).uri
            if uri in self._documents:
                del self._documents[uri]

        # ─── Indexing ─────────────────────────────────────────────────────────

        async def _index_file_async(self, file_path: str, content: str) -> None:
            """Index a file for symbol resolution."""
            if not os.path.exists(file_path):
                return

            try:
                # Write content to temp file for indexing if needed
                if self._symbol_graph is not None:
                    await self._symbol_graph.index_file(file_path)
                    logger.debug("LSP: Indexed: %s", file_path)
            except Exception as e:
                logger.warning("LSP: Failed to index %s: %s", file_path, e)

        def _schedule_diagnostics(self, uri: str) -> None:
            """Schedule diagnostics with debouncing."""
            if uri in self._pending_diagnostics:
                self._pending_diagnostics[uri].cancel()

            async def run():
                await asyncio.sleep(self._debounce_ms / 1000.0)
                await self._run_diagnostics(uri)
                self._pending_diagnostics.pop(uri, None)

            try:
                loop = asyncio.get_running_loop()
                self._pending_diagnostics[uri] = asyncio.create_task(run())
            except RuntimeError:
                pass

        async def _run_diagnostics(self, uri: str) -> None:
            """Run diagnostics on a document and publish to client."""
            doc = self._documents.get(uri)
            if not doc or not os.path.exists(doc.file_path):
                return

            diagnostics: list[Diagnostic] = []

            # ML-based diagnostics
            if self._ml_detector is not None:
                try:
                    findings = self._ml_detector.detect(doc.file_path, doc.language_id)
                    for finding in findings:
                        diagnostics.append(Diagnostic(
                            range=Range(
                                start=Position(line=max(0, finding.line - 1), character=0),
                                end=Position(line=max(0, finding.line - 1), character=1000),
                            ),
                            severity=_severity_to_lsp(finding.severity),
                            message=finding.message,
                            source="AI_SUPPORT",
                            code=finding.rule_id,
                        ))
                except Exception as e:
                    logger.warning("LSP: ML diagnostics failed: %s", e)

            # Basic syntax diagnostics
            diagnostics.extend(self._basic_diagnostics(doc))

            # Publish diagnostics
            self._stats["diagnostics_sent"] += len(diagnostics)
            self.publish_diagnostics(uri, diagnostics)

        def _basic_diagnostics(self, doc: LSPDocument) -> list[Diagnostic]:
            """Run basic syntax/pattern diagnostics."""
            diagnostics: list[Diagnostic] = []
            lines = doc.content.split("\n")

            for i, line in enumerate(lines):
                stripped = line.lstrip()

                # Check for trailing whitespace
                if line != line.rstrip():
                    diagnostics.append(Diagnostic(
                        range=Range(
                            start=Position(line=i, character=len(line.rstrip())),
                            end=Position(line=i, character=len(line)),
                        ),
                        severity=DiagnosticSeverity.Hint,
                        message="Trailing whitespace",
                        source="AI_SUPPORT",
                    ))

                # Check for tabs in Python
                if doc.language_id == "python" and "\t" in line:
                    diagnostics.append(Diagnostic(
                        range=Range(
                            start=Position(line=i, character=line.index("\t")),
                            end=Position(line=i, character=line.index("\t") + 1),
                        ),
                        severity=DiagnosticSeverity.Warning,
                        message="Use spaces instead of tabs (PEP 8)",
                        source="AI_SUPPORT",
                    ))

            return diagnostics

        # ─── Go-to Definition ─────────────────────────────────────────────────

        @self.feature("textDocument/definition")
        async def definition(self, params: DefinitionParams) -> list[Location]:
            """Handle go-to-definition request."""
            uri = params.text_document.uri
            doc = self._documents.get(uri)
            if not doc:
                return []

            # Get word at cursor position
            word = self._get_word_at_position(doc.content, params.position)
            if not word:
                return []

            locations: list[Location] = []

            # Search in symbol graph
            if self._symbol_graph is not None:
                try:
                    # Search for symbol definition
                    for node_key, node in self._symbol_graph._nodes.items():
                        if node.name == word:
                            locations.append(Location(
                                uri=self._path_to_uri(node.file_path),
                                range=Range(
                                    start=Position(line=node.line - 1, character=0),
                                    end=Position(line=node.line - 1, character=100),
                                ),
                            ))
                except Exception as e:
                    logger.warning("LSP: Definition search failed: %s", e)

            # Fallback: search in document
            if not locations:
                locations = self._search_definition_in_doc(doc, word)

            self._stats["definitions_found"] += len(locations)
            return locations

        def _search_definition_in_doc(
            self,
            doc: LSPDocument,
            word: str,
        ) -> list[Location]:
            """Search for symbol definition in document content."""
            locations: list[Location] = []
            lines = doc.content.split("\n")
            patterns = [
                rf"def\s+{re.escape(word)}\s*\(",
                rf"class\s+{re.escape(word)}\s*[\(:]",
                rf"async\s+def\s+{re.escape(word)}\s*\(",
                rf"func\s+{re.escape(word)}\s*\(",
                rf"fn\s+{re.escape(word)}\s*[<(]",
                rf"struct\s+{re.escape(word)}\s*",
                rf"enum\s+{re.escape(word)}\s*",
                rf"type\s+{re.escape(word)}\s*=",
            ]

            for i, line in enumerate(lines):
                for pattern in patterns:
                    if re.search(pattern, line):
                        locations.append(Location(
                            uri=doc.uri,
                            range=Range(
                                start=Position(line=i, character=0),
                                end=Position(line=i, character=len(line)),
                            ),
                        ))
                        break

            return locations

        # ─── Find References ─────────────────────────────────────────────────

        @self.feature("textDocument/references")
        async def references(self, params: ReferencesParams) -> list[Location]:
            """Handle find-references request."""
            uri = params.text_document.uri
            doc = self._documents.get(uri)
            if not doc:
                return []

            # Get word at cursor position
            word = self._get_word_at_position(doc.content, params.position)
            if not word:
                return []

            locations: list[Location] = []

            # Search in all tracked documents
            for tracked_uri, tracked_doc in self._documents.items():
                refs = self._find_word_references(tracked_doc, word)
                locations.extend(refs)

            self._stats["references_found"] += len(locations)
            return locations

        def _find_word_references(
            self,
            doc: LSPDocument,
            word: str,
        ) -> list[Location]:
            """Find all references to a word in a document."""
            locations: list[Location] = []
            lines = doc.content.split("\n")

            for i, line in enumerate(lines):
                # Find all occurrences of word as a complete identifier
                for match in re.finditer(rf"\b{re.escape(word)}\b", line):
                    locations.append(Location(
                        uri=doc.uri,
                        range=Range(
                            start=Position(line=i, character=match.start()),
                            end=Position(line=i, character=match.end()),
                        ),
                    ))

            return locations

        # ─── Hover ───────────────────────────────────────────────────────────

        @self.feature("textDocument/hover")
        async def hover(self, params: HoverParams) -> Hover | None:
            """Handle hover request."""
            uri = params.text_document.uri
            doc = self._documents.get(uri)
            if not doc:
                return None

            # Get word at cursor position
            word = self._get_word_at_position(doc.content, params.position)
            if not word:
                return None

            # Try to get symbol info
            symbol_info = self._get_symbol_info(doc, word)
            if not symbol_info:
                return None

            self._stats["hovers_resolved"] += 1

            return Hover(
                contents=MarkupContent(
                    kind=MarkupKind.Markdown,
                    value=symbol_info,
                ),
            )

        def _get_symbol_info(self, doc: LSPDocument, word: str) -> str | None:
            """Get hover information for a symbol."""
            lines = doc.content.split("\n")

            # Find definition line
            for i, line in enumerate(lines):
                for prefix in ["def ", "class ", "async def ", "func ", "fn "]:
                    pattern = rf"({prefix}|struct\s+|enum\s+|type\s+){re.escape(word)}"
                    if re.search(pattern, line):
                        sig = line.strip()
                        # Try to get docstring
                        docstring = self._get_docstring(lines, i + 1)

                        result = f"```\n{sig}\n```\n"
                        if docstring:
                            result += f"\n_{docstring}_"
                        return result

            return None

        def _get_docstring(self, lines: list[str], start_line: int) -> str | None:
            """Extract docstring from lines following a definition."""
            if start_line >= len(lines):
                return None

            next_line = lines[start_line].strip()

            # Check for triple-quoted docstring on next line
            if '"""' in next_line or "'''" in next_line:
                quote = '"""' if '"""' in next_line else "'''"
                if next_line.count(quote) >= 2:
                    # Single-line docstring
                    return next_line.split(quote)[1].strip()
                # Multi-line docstring
                doc_lines = [next_line.split(quote)[1]]
                for j in range(start_line + 1, len(lines)):
                    if quote in lines[j]:
                        doc_lines.append(lines[j].split(quote)[0].strip())
                        break
                    doc_lines.append(lines[j].strip())
                return " ".join(l for l in doc_lines if l)

            # Check for single-line comment docstring
            if next_line.startswith("#"):
                return next_line.lstrip("# ").strip()

            return None

        # ─── Auto-completion ──────────────────────────────────────────────────

        @self.feature("textDocument/completion")
        async def completion(self, params: CompletionParams) -> CompletionList:
            """Handle completion request."""
            uri = params.text_document.uri
            doc = self._documents.get(uri)
            if not doc:
                return CompletionList(is_incomplete=False, items=[])

            # Get word prefix at cursor
            prefix = self._get_word_prefix(doc.content, params.position)

            items: list[CompletionItem] = []

            # Add keywords based on language
            if doc.language_id == "python":
                items.extend(self._python_completions(prefix))
            elif doc.language_id in ("javascript", "typescript"):
                items.extend(self._js_completions(prefix))

            # Add symbols from indexed files
            items.extend(self._symbol_completions(prefix))

            self._stats["completions_served"] += len(items)

            return CompletionList(is_incomplete=False, items=items)

        def _python_completions(self, prefix: str) -> list[CompletionItem]:
            """Provide Python keyword completions."""
            keywords = [
                ("def ", "def ", "Define a function"),
                ("class ", "class ", "Define a class"),
                ("async def ", "async def ", "Define an async function"),
                ("if ", "if ", "Conditional statement"),
                ("elif ", "elif ", "Else-if condition"),
                ("else:", "else:", "Else clause"),
                ("for ", "for ", "For loop"),
                ("while ", "while ", "While loop"),
                ("try:", "try:", "Try block"),
                ("except:", "except:", "Exception handler"),
                ("return ", "return ", "Return statement"),
                ("import ", "import ", "Import module"),
                ("from ", "from ", "Import from module"),
                ("raise ", "raise ", "Raise exception"),
                ("with ", "with ", "Context manager"),
                ("as ", "as ", "Alias"),
                ("lambda ", "lambda ", "Lambda function"),
                ("assert ", "assert ", "Assertion"),
                ("yield ", "yield ", "Yield statement"),
                ("global ", "global ", "Global declaration"),
            ]

            return [
                CompletionItem(
                    label=kw[0].strip(),
                    kind=14,  # Keyword
                    documentation=kw[2],
                    insert_text=kw[1],
                    sort_text=f"1{kw[0]}",
                )
                for kw in keywords
                if kw[0].lower().startswith(prefix.lower())
            ]

        def _js_completions(self, prefix: str) -> list[CompletionItem]:
            """Provide JavaScript/TypeScript keyword completions."""
            keywords = [
                ("function ", "function ", "Function declaration"),
                ("const ", "const ", "Constant declaration"),
                ("let ", "let ", "Block-scoped variable"),
                ("var ", "var ", "Variable declaration"),
                ("class ", "class ", "Class declaration"),
                ("import ", "import ", "Import statement"),
                ("export ", "export ", "Export statement"),
                ("async ", "async ", "Async modifier"),
                ("await ", "await ", "Await expression"),
                ("try {", "try {\n  \n}", "Try-catch block"),
                ("catch ", "catch ", "Catch clause"),
                ("throw ", "throw ", "Throw exception"),
                ("return ", "return ", "Return statement"),
                ("typeof ", "typeof ", "Type check"),
                ("instanceof", "instanceof", "Instance check"),
            ]

            return [
                CompletionItem(
                    label=kw[0].strip().split()[0],
                    kind=14,
                    documentation=kw[2],
                    insert_text=kw[1],
                    sort_text=f"1{kw[0]}",
                )
                for kw in keywords
                if kw[0].lower().startswith(prefix.lower())
            ]

        def _symbol_completions(self, prefix: str) -> list[CompletionItem]:
            """Provide symbol completions from indexed code."""
            items: list[CompletionItem] = []

            if self._symbol_graph is None:
                return items

            try:
                for node_key, node in self._symbol_graph._nodes.items():
                    if node.name.lower().startswith(prefix.lower()):
                        items.append(CompletionItem(
                            label=node.name,
                            kind=_kind_to_lsp(node.kind),
                            documentation=f"{node.kind}: {node.file_path}:{node.line}",
                            detail=node.signature if node.signature else None,
                            sort_text=f"2{node.name}",
                        ))
            except Exception as e:
                logger.warning("LSP: Symbol completions failed: %s", e)

            return items

        # ─── Helpers ────────────────────────────────────────────────────────

        def _get_word_at_position(
            self,
            content: str,
            position: Position,
        ) -> str | None:
            """Extract the identifier word at a cursor position."""
            lines = content.split("\n")
            if position.line >= len(lines):
                return None

            line = lines[position.line]
            if position.character >= len(line):
                return None

            # Find word boundaries
            start = position.character
            end = position.character

            while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
                start -= 1
            while end < len(line) and (line[end].isalnum() or line[end] == "_"):
                end += 1

            word = line[start:end]
            return word if word else None

        def _get_word_prefix(
            self,
            content: str,
            position: Position,
        ) -> str:
            """Get the prefix before cursor for completion."""
            lines = content.split("\n")
            if position.line >= len(lines):
                return ""

            line = lines[position.line]
            if position.character >= len(line):
                return line

            # Find start of word
            start = position.character
            while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
                start -= 1

            return line[start:position.character]

        # ─── Stats ───────────────────────────────────────────────────────────

        def get_stats(self) -> dict[str, Any]:
            """Get server statistics."""
            return {
                **self._stats,
                "documents_tracked": len(self._documents),
                "pending_diagnostics": len(self._pending_diagnostics),
            }

        def set_root_path(self, path: str) -> None:
            """Update the workspace root path."""
            self.root_path = path
            logger.info("LSP: Root path set to: %s", path)


else:
    # Stub class when pygls is not available
    class AISupportLanguageServer:
        """LSP server stub when pygls is not installed."""

        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "pygls is not installed. Install with: pip install pygls"
            )


# ─── Server Factory ──────────────────────────────────────────────────────────

def create_lsp_server(
    root_path: str | None = None,
    debounce_ms: int = 300,
) -> AISupportLanguageServer:
    """Create and configure an LSP server instance.

    Args:
        root_path: Workspace root directory
        debounce_ms: Diagnostics debounce delay in milliseconds

    Returns:
        Configured AISupportLanguageServer instance
    """
    if not PYGLS_AVAILABLE:
        raise RuntimeError(
            "pygls is not installed. Install with: pip install pygls"
        )

    return AISupportLanguageServer(root_path=root_path, debounce_ms=debounce_ms)
