"""LSP (Language Server Protocol) client tools for Agentic-AI CLI.

Provides:
- Diagnostics (errors, warnings)
- Symbol navigation
- References
- Definitions
- Rename
- Code actions
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LSPPosition:
    """A position in a text document."""
    line: int = 0  # 0-indexed
    character: int = 0  # 0-indexed
    
    def to_dict(self) -> dict[str, int]:
        return {"line": self.line, "character": self.character}


@dataclass
class LSPRange:
    """A range in a text document."""
    start: LSPPosition = field(default_factory=LSPPosition)
    end: LSPPosition = field(default_factory=LSPPosition)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
        }


@dataclass
class LSPDocumentURI:
    """A document URI."""
    scheme: str = "file"
    path: str = ""
    
    @classmethod
    def from_path(cls, path: Path) -> LSPDocumentURI:
        return cls(scheme="file", path=str(path.absolute()))
    
    def to_str(self) -> str:
        return f"{self.scheme}://{self.path.replace('\\', '/')}"


@dataclass
class LSPDiagnostic:
    """A diagnostic (error, warning, etc.)."""
    range: LSPRange
    severity: int  # 1=Error, 2=Warning, 3=Info, 4=Hint
    message: str
    source: str = ""
    code: str = ""
    
    @property
    def severity_name(self) -> str:
        names = {1: "Error", 2: "Warning", 3: "Info", 4: "Hint"}
        return names.get(self.severity, "Unknown")
    
    @property
    def is_error(self) -> bool:
        return self.severity == 1


@dataclass
class LSPSymbol:
    """A symbol in a document."""
    name: str
    kind: int  # LSP SymbolKind
    location: LSPLocation
    detail: str = ""
    
    @property
    def kind_name(self) -> str:
        kinds = {
            1: "File", 2: "Module", 3: "Namespace", 4: "Package",
            5: "Class", 6: "Method", 7: "Property", 8: "Field",
            9: "Constructor", 10: "Enum", 11: "Interface", 12: "Function",
            13: "Variable", 14: "Constant", 15: "String", 16: "Number",
            17: "Boolean", 18: "Array", 19: "Object", 20: "Key",
            21: "Null", 22: "EnumMember", 23: "Struct", 24: "Event",
            25: "Operator", 26: "TypeParameter",
        }
        return kinds.get(self.kind, f"Kind({self.kind})")


@dataclass
class LSPLocation:
    """A location in a document."""
    uri: str = ""
    range: LSPRange | None = None
    
    @classmethod
    def from_dict(cls, data: dict) -> LSPLocation:
        range_data = data.get("range")
        return cls(
            uri=data.get("uri", ""),
            range=LSPRange(
                start=LSPPosition(
                    line=range_data["start"]["line"] if range_data else 0,
                    character=range_data["start"]["character"] if range_data else 0,
                ),
                end=LSPPosition(
                    line=range_data["end"]["line"] if range_data else 0,
                    character=range_data["end"]["character"] if range_data else 0,
                ),
            ) if range_data else None,
        )


class LSPClient:
    """LSP client for communicating with language servers.
    
    Uses stdio transport to communicate with LSP servers.
    """
    
    def __init__(self, server_command: list[str], root_path: Path | None = None):
        self.server_command = server_command
        self.root_path = root_path or Path.cwd()
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._capabilities: dict[str, Any] = {}
    
    async def start(self) -> None:
        """Start the LSP server."""
        self._process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(self.root_path),
        )
        
        # Initialize
        await self._send_initialize()
    
    async def stop(self) -> None:
        """Stop the LSP server."""
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._process = None
    
    async def _send_initialize(self) -> None:
        """Send initialize request."""
        response = await self._send_request("initialize", {
            "processId": None,
            "rootPath": str(self.root_path),
            "capabilities": {
                "textDocument": {
                    "synchronization": {"didSave": True},
                    "diagnostics": {},
                    "codeAction": {"dynamicRegistration": True},
                },
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {},
                },
            },
        })
        self._capabilities = response.get("capabilities", {})
    
    async def _send_request(self, method: str, params: dict) -> dict:
        """Send a request and wait for response."""
        if not self._process:
            raise RuntimeError("LSP server not started")
        
        self._request_id += 1
        request_id = self._request_id
        
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        
        content = json.dumps(message).encode()
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()
        
        self._process.stdin.write(header + content)
        await self._process.stdin.drain()
        
        # Read response
        response_line = await self._process.stdout.readline()
        if not response_line:
            return {}
        
        # Parse header
        header_str = response_line.decode()
        if "Content-Length:" in header_str:
            content_length = int(header_str.split(":")[1].strip())
            await self._process.stdout.readline()  # Empty line
            
            content = await self._process.stdout.readexactly(content_length)
            response = json.loads(content.decode())
            
            if response.get("id") == request_id:
                if "result" in response:
                    return response["result"]
                elif "error" in response:
                    raise LSPError(response["error"])
        
        return {}
    
    async def did_open(self, path: Path) -> None:
        """Notify server that a document was opened."""
        if not self._process:
            return
        
        content = path.read_text(encoding="utf-8", errors="replace")
        uri = LSPDocumentURI.from_path(path).to_str()
        
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didOpen",
            "params": {
                "textDocument": {
                    "uri": uri,
                    "languageId": self._get_language_id(path),
                    "version": 1,
                    "text": content,
                }
            },
        }
        
        await self._send_notification(message)
    
    async def did_save(self, path: Path) -> None:
        """Notify server that a document was saved."""
        uri = LSPDocumentURI.from_path(path).to_str()
        
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didSave",
            "params": {
                "textDocument": {"uri": uri},
            },
        }
        
        await self._send_notification(message)
    
    async def did_close(self, path: Path) -> None:
        """Notify server that a document was closed."""
        uri = LSPDocumentURI.from_path(path).to_str()
        
        message = {
            "jsonrpc": "2.0",
            "method": "textDocument/didClose",
            "params": {
                "textDocument": {"uri": uri},
            },
        }
        
        await self._send_notification(message)
    
    async def _send_notification(self, message: dict) -> None:
        """Send a notification (no response expected)."""
        if not self._process:
            return
        
        content = json.dumps(message).encode()
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()
        
        self._process.stdin.write(header + content)
        await self._process.stdin.drain()
    
    async def get_diagnostics(self, path: Path) -> list[LSPDiagnostic]:
        """Get diagnostics for a document."""
        await self.did_open(path)
        await asyncio.sleep(0.1)  # Give server time to analyze
        
        uri = LSPDocumentURI.from_path(path).to_str()
        
        result = await self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })
        
        # Diagnostics are usually sent via pull
        diagnostics_result = await self._send_request("textDocument/diagnostic", {
            "textDocument": {"uri": uri},
        })
        
        diagnostics = []
        for d in diagnostics_result.get("items", []):
            range_data = d.get("range", {})
            diagnostics.append(LSPDiagnostic(
                range=LSPRange(
                    start=LSPPosition(
                        line=range_data.get("start", {}).get("line", 0),
                        character=range_data.get("start", {}).get("character", 0),
                    ),
                    end=LSPPosition(
                        line=range_data.get("end", {}).get("line", 0),
                        character=range_data.get("end", {}).get("character", 0),
                    ),
                ),
                severity=d.get("severity", 1),
                message=d.get("message", ""),
                source=d.get("source", ""),
                code=str(d.get("code", "")),
            ))
        
        return diagnostics
    
    async def get_symbols(self, path: Path) -> list[LSPSymbol]:
        """Get document symbols."""
        await self.did_open(path)
        
        uri = LSPDocumentURI.from_path(path).to_str()
        
        result = await self._send_request("textDocument/documentSymbol", {
            "textDocument": {"uri": uri},
        })
        
        symbols = []
        for s in result:
            loc = s.get("location", {})
            symbols.append(LSPSymbol(
                name=s.get("name", ""),
                kind=s.get("kind", 0),
                location=LSPLocation.from_dict(loc),
                detail=s.get("detail", ""),
            ))
        
        return symbols
    
    async def find_references(self, path: Path, line: int, character: int) -> list[LSPLocation]:
        """Find all references to a symbol."""
        uri = LSPDocumentURI.from_path(path).to_str()
        
        result = await self._send_request("textDocument/references", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "context": {"includeDeclaration": True},
        })
        
        return [LSPLocation.from_dict(loc) for loc in result]
    
    async def goto_definition(self, path: Path, line: int, character: int) -> LSPLocation | None:
        """Go to definition of a symbol."""
        uri = LSPDocumentURI.from_path(path).to_str()
        
        result = await self._send_request("textDocument/definition", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
        })
        
        if result:
            return LSPLocation.from_dict(result[0] if isinstance(result, list) else result)
        return None
    
    async def rename(self, path: Path, line: int, character: int, new_name: str) -> dict:
        """Rename a symbol."""
        uri = LSPDocumentURI.from_path(path).to_str()
        
        return await self._send_request("textDocument/rename", {
            "textDocument": {"uri": uri},
            "position": {"line": line, "character": character},
            "newName": new_name,
        })
    
    @staticmethod
    def _get_language_id(path: Path) -> str:
        """Get LSP language ID for a file."""
        ext = path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "javascriptreact",
            ".tsx": "typescriptreact",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".html": "html",
            ".css": "css",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
        }
        return lang_map.get(ext, "plaintext")


class LSPError(Exception):
    """LSP error."""
    pass


# LSP Server detection
LSP_SERVERS = {
    ".py": ["pyright-langserver", "pylsp", "ruff"],
    ".js": ["typescript-language-server", "vtsls"],
    ".ts": ["typescript-language-server", "vtsls"],
    ".rs": ["rust-analyzer"],
    ".go": ["gopls"],
    ".cpp": ["clangd", "ccls"],
    ".c": ["clangd", "ccls"],
}


def detect_lsp_server(path: Path) -> list[str] | None:
    """Detect available LSP server for a file."""
    ext = path.suffix.lower()
    
    for server in LSP_SERVERS.get(ext, []):
        import shutil
        if shutil.which(server):
            return [server]
    
    return None
