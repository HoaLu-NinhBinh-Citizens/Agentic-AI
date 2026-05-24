"""TypeScript/JavaScript LSP integration using tsserver protocol.

Provides:
- TypeScript language service
- JavaScript support
- React/JSX support
- Code completion
- Diagnostics
- Refactoring
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


class TSServerError(Exception):
    """tsserver operation error."""
    pass


class TSServerConnection:
    """Connection to tsserver (TypeScript Language Service).
    
    Uses the tsserver protocol over stdio.
    """
    
    def __init__(self, typescript_path: Path | None = None):
        self.typescript_path = typescript_path or self._find_typescript()
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._event_handlers: dict[str, list] = {}
        self._reader_task: asyncio.Task | None = None
        self._seq = 0
        self._closed = False
    
    def _find_typescript(self) -> Path | None:
        """Find TypeScript installation."""
        # Check common locations
        candidates = [
            Path.home() / ".npm" / "global" / "node_modules" / "typescript" / "bin",
            Path.home() / ".nvm" / "versions" / "node" / "v*/lib" / "node_modules" / "typescript" / "bin",
            Path("C:/Program Files/nodejs"),
            Path("/usr/local/lib/node_modules/typescript/bin"),
            Path("/usr/lib/node_modules/typescript/bin"),
        ]
        
        # Check for npx
        if shutil.which("npx"):
            return Path("npx")
        
        for candidate in candidates:
            tsserver = candidate / "tsserver"
            if tsserver.exists():
                return tsserver
        
        # Check node_modules in common paths
        for base in [Path.cwd(), Path.home()]:
            for node_modules in [base, base / "node_modules"]:
                ts_path = node_modules / "typescript" / "bin" / "tsserver"
                if ts_path.exists():
                    return ts_path
        
        return None
    
    @property
    def is_available(self) -> bool:
        """Check if tsserver is available."""
        return self.typescript_path is not None
    
    async def start(self, workspace_root: Path) -> None:
        """Start tsserver."""
        if not self.is_available:
            raise TSServerError("TypeScript not found")
        
        # Start tsserver
        cmd = [str(self.typescript_path)]
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(workspace_root),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "TSS_LOG": "-1"},
        )
        
        # Start reader
        self._reader_task = asyncio.create_task(self._read_messages())
        
        # Configure
        await self._configure(workspace_root)
    
    async def _configure(self, workspace_root: Path) -> None:
        """Configure tsserver."""
        await self.send_request("configure", {
            "hostInfo": "agentic-ai",
            "formatOptions": {
                "tabSize": 4,
                "indentSize": 4,
                "convertTabsToSpaces": True,
                "insertSpaceAfterCommaDelimiter": True,
                "insertSpaceAfterSemicolonInForStatements": True,
                "insertSpaceBeforeAndAfterBinaryOperators": True,
            },
            "preferences": {
                "disableSizeLimit": True,
                "importModuleSpecifierEnding": "auto",
                "includeAutomaticOptionalChainCompletions": True,
            },
        })
    
    async def _read_messages(self) -> None:
        """Read messages from tsserver."""
        assert self._process and self._process.stdout
        
        buffer = ""
        
        while not self._closed:
            try:
                data = await self._process.stdout.read(1024)
                if not data:
                    break
                
                buffer += data.decode()
                
                # Process complete messages
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if not line.strip():
                        continue
                    
                    try:
                        message = json.loads(line)
                        await self._handle_message(message)
                    except json.JSONDecodeError:
                        continue
                        
            except Exception as e:
                if self._closed:
                    break
    
    async def _handle_message(self, message: dict) -> None:
        """Handle incoming message."""
        if message.get("type") == "response":
            req_id = message.get("request_seq", 0)
            if req_id in self._pending:
                future = self._pending.pop(req_id)
                if "success" in message:
                    if message["success"]:
                        future.set_result(message.get("body", {}))
                    else:
                        future.set_exception(TSServerError(
                            message.get("message", "Unknown error")
                        ))
        
        elif message.get("type") == "event":
            event_name = message.get("event", "")
            body = message.get("body", {})
            
            if event_name in self._event_handlers:
                for handler in self._event_handlers[event_name]:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(body)
                        else:
                            handler(body)
                    except:
                        pass
    
    def on_event(self, event: str, handler) -> None:
        """Register event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)
    
    async def send_request(self, command: str, args: dict | None = None) -> Any:
        """Send request and wait for response."""
        req_id = self._seq
        self._seq += 1
        
        future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        
        message = {
            "seq": req_id,
            "type": "request",
            "command": command,
            "arguments": args or {},
        }
        
        await self._send(message)
        return await future
    
    async def _send(self, message: dict) -> None:
        """Send message."""
        if not self._process or not self._process.stdin:
            raise TSServerError("tsserver not running")
        
        content = json.dumps(message) + "\n"
        self._process.stdin.write(content.encode())
        await self._process.stdin.drain()
    
    async def close(self) -> None:
        """Close tsserver."""
        self._closed = True
        if self._reader_task:
            self._reader_task.cancel()
        if self._process:
            self._process.terminate()
            await asyncio.sleep(0.1)
            if self._process.returncode is None:
                self._process.kill()


@dataclass
class TypeScriptProject:
    """A TypeScript project context."""
    project_root: Path
    tsconfig_path: Path | None = None
    files: list[str] = field(default_factory=list)
    
    @classmethod
    async def discover(cls, root: Path) -> TypeScriptProject | None:
        """Discover TypeScript project in directory."""
        tsconfig = root / "tsconfig.json"
        jsconfig = root / "jsconfig.json"
        
        if tsconfig.exists():
            return cls(project_root=root, tsconfig_path=tsconfig)
        elif jsconfig.exists():
            return cls(project_root=root, tsconfig_path=jsconfig)
        
        return None


class TSServerClient:
    """High-level TypeScript/JavaScript operations."""
    
    def __init__(self, connection: TSServerConnection):
        self.conn = connection
    
    @classmethod
    async def create(cls, workspace_root: Path) -> TSServerClient:
        """Create a new tsserver client."""
        conn = TSServerConnection()
        await conn.start(workspace_root)
        return cls(conn)
    
    async def open_file(self, path: Path, content: str) -> None:
        """Open a file in tsserver."""
        await self.conn.send_request("open", {
            "file": str(path),
            "fileContent": content,
        })
    
    async def get_completions(
        self,
        path: Path,
        line: int,
        offset: int,
    ) -> list[dict]:
        """Get completions at position."""
        result = await self.conn.send_request("completions", {
            "file": str(path),
            "line": line,
            "offset": offset,
        })
        return result.get("entries", [])
    
    async def get_completion_details(
        self,
        path: Path,
        line: int,
        offset: int,
        names: list[str],
    ) -> list[dict]:
        """Get detailed completion info."""
        result = await self.conn.send_request("completionEntryDetails", {
            "file": str(path),
            "line": line,
            "offset": offset,
            "entryNames": names,
        })
        return result.get("entries", [])
    
    async def get_definition(
        self,
        path: Path,
        line: int,
        offset: int,
    ) -> list[dict]:
        """Get definition at position."""
        result = await self.conn.send_request("definition", {
            "file": str(path),
            "line": line,
            "offset": offset,
        })
        return result.get("body", [])
    
    async def get_references(
        self,
        path: Path,
        line: int,
        offset: int,
    ) -> list[dict]:
        """Get all references to symbol."""
        result = await self.conn.send_request("references", {
            "file": str(path),
            "line": line,
            "offset": offset,
        })
        return result.get("refs", [])
    
    async def rename(
        self,
        path: Path,
        line: int,
        offset: int,
        find_in_comments: bool = False,
        find_in_strings: bool = False,
    ) -> dict:
        """Rename symbol at position."""
        return await self.conn.send_request("rename", {
            "file": str(path),
            "line": line,
            "offset": offset,
            "findInComments": find_in_comments,
            "findInStrings": find_in_strings,
        })
    
    async def get_errors(self, path: Path) -> list[dict]:
        """Get semantic errors for file."""
        result = await self.conn.send_request("semanticDiagnosticsSync", {
            "file": str(path),
        })
        return result.get("diagnostics", [])
    
    async def get_syntactic_errors(self, path: Path) -> list[dict]:
        """Get syntactic errors for file."""
        result = await self.conn.send_request("syntacticDiagnosticsSync", {
            "file": str(path),
        })
        return result.get("diagnostics", [])
    
    async def format_document(
        self,
        path: Path,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> list[dict]:
        """Format document or range."""
        args = {
            "file": str(path),
            "line": start_line,
            "offset": 1,
            "endLine": end_line or start_line,
            "endOffset": 1,
        }
        result = await self.conn.send_request("format", args)
        return result.get("textChanges", [])
    
    async def organize_imports(self, path: Path) -> list[dict]:
        """Organize imports in file."""
        result = await self.conn.send_request("organizeImports", {
            "file": str(path),
            "mode": "sortAndOrganizeImports",
        })
        return result.get("textChanges", [])
    
    async def get_navigate_to_items(
        self,
        search_term: str,
        max_result_count: int = 50,
    ) -> list[dict]:
        """Search for symbols matching term."""
        result = await self.conn.send_request("navto", {
            "file": str(self.conn.typescript_path),  # workspace file
            "searchTerm": search_term,
            "maxResultCount": max_result_count,
        })
        return result.get("symbolNames", [])
    
    async def get_outline(self, path: Path) -> list[dict]:
        """Get document outline (top-level symbols)."""
        result = await self.conn.send_request("navtree", {
            "file": str(path),
        })
        return [result.get("body", {})]
    
    async def get_signature(self, path: Path, line: int, offset: int) -> dict | None:
        """Get signature help at position."""
        result = await self.conn.send_request("signatureHelp", {
            "file": str(path),
            "line": line,
            "offset": offset,
        })
        return result
    
    async def quick_info(self, path: Path, line: int, offset: int) -> dict | None:
        """Get quick info (hover) at position."""
        result = await self.conn.send_request("quickinfo", {
            "file": str(path),
            "line": line,
            "offset": offset,
        })
        return result
    
    async def get_available_refactorings(
        self,
        path: Path,
        line: int,
        offset: int,
    ) -> list[dict]:
        """Get available refactorings."""
        result = await self.conn.send_request("getAvailableRefactors", {
            "file": str(path),
            "startLine": line,
            "startOffset": offset,
            "endLine": line,
            "endOffset": offset,
        })
        return result.get("actions", [])
    
    async def apply_refactoring(
        self,
        path: Path,
        line: int,
        offset: int,
        refactor_name: str,
        action_name: str,
    ) -> list[dict]:
        """Apply a refactoring."""
        result = await self.conn.send_request("getEditsForRefactor", {
            "file": str(path),
            "startLine": line,
            "startOffset": offset,
            "endLine": line,
            "endOffset": offset,
            "refactor": refactor_name,
            "action": action_name,
        })
        return result.get("edits", [])
    
    async def close(self) -> None:
        """Close tsserver."""
        await self.conn.close()


# Convenience functions

async def quick_typecheck(path: Path) -> list[dict]:
    """Quick type check a file."""
    conn = TSServerConnection()
    if not conn.is_available:
        return []
    
    client = TSServerClient(conn)
    await client.open_file(path, path.read_text())
    
    try:
        return await client.get_errors(path)
    finally:
        await client.close()


async def get_typescript_symbols(path: Path) -> list[dict]:
    """Get all symbols in a TypeScript file."""
    conn = TSServerConnection()
    if not conn.is_available:
        return []
    
    client = TSServerClient(conn)
    await client.open_file(path, path.read_text())
    
    try:
        outline = await client.get_outline(path)
        return _flatten_outline(outline[0]) if outline else []
    finally:
        await client.close()


def _flatten_outline(node: dict, results: list | None = None) -> list[dict]:
    """Flatten outline tree to list."""
    if results is None:
        results = []
    
    if not node:
        return results
    
    results.append({
        "name": node.get("name", ""),
        "kind": node.get("kind", ""),
        "line": node.get("spans", [{}])[0].get("start", {}).get("line", 0),
    })
    
    for child in node.get("childItems", []):
        _flatten_outline(child, results)
    
    return results
