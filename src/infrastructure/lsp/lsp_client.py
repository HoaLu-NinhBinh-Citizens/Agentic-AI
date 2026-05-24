"""LSP (Language Server Protocol) operations for Agentic-AI.

Provides IDE-like capabilities:
- Symbol navigation
- Code completion
- Find references
- Rename symbols
- Go to definition
- Hover information
- Diagnostics

Supports:
- pyright (Python)
- typescript-language-server
- rust-analyzer
- gopls (Go)
- clangd (C/C++)
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4


class LSPError(Exception):
    """LSP operation error."""
    pass


class LSPConnection:
    """Connection to an LSP server.
    
    Uses stdio protocol (JSON-RPC over stdin/stdout).
    """
    
    def __init__(
        self,
        server_command: list[str],
        workspace_root: Path,
        env: dict[str, str] | None = None,
    ):
        self.server_command = server_command
        self.workspace_root = workspace_root
        self.env = env or {}
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
    
    async def start(self) -> None:
        """Start the LSP server."""
        self._process = await asyncio.create_subprocess_exec(
            *self.server_command,
            cwd=str(self.workspace_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**subprocess.os.environ, **self.env},
        )
        
        # Start reader task
        self._reader_task = asyncio.create_task(self._read_messages())
        
        # Initialize
        await self._send_initialize()
    
    async def _send_initialize(self) -> None:
        """Send initialize request."""
        result = await self.send_request(
            "initialize",
            {
                "processId": None,
                "rootUri": str(self.workspace_root),
                "capabilities": {
                    "textDocument": {
                        "synchronization": {"willSave": True, "didSave": True},
                        "hover": {"dynamicRegistration": True},
                        "completion": {"dynamicRegistration": True},
                        "references": {"dynamicRegistration": True},
                        "definition": {"dynamicRegistration": True},
                        "rename": {"dynamicRegistration": True},
                        "documentSymbol": {"dynamicRegistration": True},
                    },
                    "workspace": {
                        "applyEdit": True,
                        "workspaceFolders": True,
                    },
                },
            },
        )
        
        # Send initialized
        await self.send_notification("initialized", {})
    
    async def _read_messages(self) -> None:
        """Read messages from server."""
        assert self._process and self._process.stdout
        
        while True:
            try:
                # Read headers
                headers: dict[str, str] = {}
                while True:
                    line = await self._process.stdout.readline()
                    if not line:
                        return
                    line = line.decode().strip()
                    if not line:
                        break
                    if ":" in line:
                        key, value = line.split(":", 1)
                        headers[key.strip().lower()] = value.strip()
                
                # Read body
                content_length = int(headers.get("content-length", 0))
                body = await self._process.stdout.read(content_length)
                
                if body:
                    message = json.loads(body.decode())
                    await self._handle_message(message)
                    
            except Exception as e:
                if self._process.returncode is not None:
                    break
    
    async def _handle_message(self, message: dict) -> None:
        """Handle incoming message."""
        if message.get("id"):
            # Response
            req_id = message["id"]
            if req_id in self._pending:
                future = self._pending.pop(req_id)
                if "result" in message:
                    future.set_result(message["result"])
                elif "error" in message:
                    future.set_exception(LSPError(message["error"]))
    
    async def send_request(self, method: str, params: dict) -> Any:
        """Send a request and wait for response."""
        req_id = self._request_id
        self._request_id += 1
        
        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        
        await self._send_message({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        
        return await future
    
    async def send_notification(self, method: str, params: dict) -> None:
        """Send a notification (no response)."""
        await self._send_message({"jsonrpc": "2.0", "method": method, "params": params})
    
    async def _send_message(self, message: dict) -> None:
        """Send a message."""
        if not self._process or not self._process.stdin:
            raise LSPError("Process not running")
        
        body = json.dumps(message).encode()
        header = f"Content-Length: {len(body)}\r\n\r\n".encode()
        
        self._process.stdin.write(header + body)
        await self._process.stdin.drain()
    
    async def close(self) -> None:
        """Close the connection."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._process:
            self._process.terminate()
            await self._process.wait()


@dataclass
class TextDocument:
    """A text document opened in the editor."""
    uri: str
    language_id: str
    version: int = 1
    text: str = ""


class LSPServer:
    """LSP server wrapper with high-level operations."""
    
    def __init__(self, connection: LSPConnection):
        self.conn = connection
        self._docs: dict[str, TextDocument] = {}
    
    @classmethod
    async def start(
        cls,
        language: str,
        workspace_root: Path,
    ) -> LSPServer:
        """Start an LSP server for the given language."""
        server_cmd = cls._get_server_command(language)
        conn = LSPConnection(server_cmd, workspace_root)
        await conn.start()
        return cls(conn)
    
    @staticmethod
    def _get_server_command(language: str) -> list[str]:
        """Get the LSP server command for a language."""
        servers = {
            "python": ["pyright-langserver", "--stdio"],
            "typescript": ["typescript-language-server", "--stdio"],
            "javascript": ["typescript-language-server", "--stdio"],
            "rust": ["rust-analyzer"],
            "go": ["gopls"],
            "c": ["clangd"],
            "cpp": ["clangd"],
            "java": ["jdtls"],
            "json": ["vscode-json-languageserver", "--stdio"],
            "html": ["vscode-html-languageserver", "--stdio"],
            "css": ["vscode-css-languageserver", "--stdio"],
            "yaml": ["yaml-language-server", "--stdio"],
            "toml": ["taplo", "lsp", "stdio"],
        }
        
        if language not in servers:
            raise LSPError(f"No LSP server configured for {language}")
        
        return servers[language]
    
    async def open_document(self, path: Path, text: str) -> None:
        """Open a document in the LSP server."""
        uri = f"file://{path}"
        self._docs[uri] = TextDocument(uri=uri, text=text, language_id=self._get_language(path))
        
        await self.conn.send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": self._get_language(path),
                    "version": 1,
                    "text": text,
                }
            },
        )
    
    async def change_document(self, path: Path, text: str, version: int) -> None:
        """Update document content."""
        uri = f"file://{path}"
        if uri in self._docs:
            self._docs[uri].text = text
            self._docs[uri].version = version
            
            await self.conn.send_notification(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": text}],
                },
            )
    
    async def document_symbols(self, path: Path) -> list[dict]:
        """Get all symbols in a document."""
        uri = f"file://{path}"
        result = await self.conn.send_request(
            "textDocument/documentSymbol",
            {"textDocument": {"uri": uri}},
        )
        return result or []
    
    async def goto_definition(self, path: Path, line: int, character: int) -> dict | None:
        """Go to definition of symbol at position."""
        uri = f"file://{path}"
        result = await self.conn.send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        return result[0] if result else None
    
    async def find_references(
        self,
        path: Path,
        line: int,
        character: int,
    ) -> list[dict]:
        """Find all references to symbol at position."""
        uri = f"file://{path}"
        result = await self.conn.send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "context": {"includeDeclaration": True},
            },
        )
        return result or []
    
    async def rename(
        self,
        path: Path,
        line: int,
        character: int,
        new_name: str,
    ) -> dict:
        """Rename symbol at position."""
        uri = f"file://{path}"
        return await self.conn.send_request(
            "textDocument/rename",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
                "newName": new_name,
            },
        )
    
    async def hover(self, path: Path, line: int, character: int) -> dict | None:
        """Get hover information."""
        uri = f"file://{path}"
        result = await self.conn.send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        return result
    
    async def completion(self, path: Path, line: int, character: int) -> list[dict]:
        """Get completion items."""
        uri = f"file://{path}"
        result = await self.conn.send_request(
            "textDocument/completion",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": character},
            },
        )
        # Handle both CompletionList and array
        if isinstance(result, dict):
            return result.get("items", [])
        return result or []
    
    async def diagnostics(self, path: Path) -> list[dict]:
        """Get diagnostics for a document."""
        uri = f"file://{path}"
        result = await self.conn.send_request(
            "textDocument/diagnostic",
            {"textDocument": {"uri": uri}},
        )
        return result.get("items", []) if result else []
    
    def _get_language(self, path: Path) -> str:
        """Get language ID from file extension."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".jsx": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".java": "java",
            ".json": "json",
            ".html": "html",
            ".css": "css",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
        }
        return ext_map.get(path.suffix.lower(), "plaintext")
    
    async def close(self) -> None:
        """Close the LSP server."""
        await self.conn.close()


class LSPLanguageServerManager:
    """Manages multiple LSP servers for different languages."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self._servers: dict[str, LSPServer] = {}
        self._server_lock = asyncio.Lock()
    
    async def get_server(self, language: str) -> LSPServer:
        """Get or start a server for the language."""
        async with self._server_lock:
            if language not in self._servers:
                try:
                    server = await LSPServer.start(language, self.workspace_root)
                    self._servers[language] = server
                except Exception as e:
                    raise LSPError(f"Failed to start LSP server for {language}: {e}")
            
            return self._servers[language]
    
    async def document_symbols(self, path: Path) -> list[dict]:
        """Get symbols for a document."""
        server = await self.get_server(self._get_language(path))
        return await server.document_symbols(path)
    
    async def close_all(self) -> None:
        """Close all servers."""
        for server in self._servers.values():
            await server.close()
        self._servers.clear()
    
    def _get_language(self, path: Path) -> str:
        """Get language from path."""
        ext_map = {
            ".py": "python",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".js": "javascript",
            ".rs": "rust",
            ".go": "go",
            ".c": "c",
            ".cpp": "cpp",
            ".java": "java",
        }
        return ext_map.get(path.suffix.lower(), "plaintext")
