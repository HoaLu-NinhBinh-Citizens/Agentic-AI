"""Code intelligence tools - LSP, DAP, AST."""

from ..lsp import (
    LSPClient,
    LSPPosition,
    LSPRange,
    LSPDocumentURI,
    LSPDiagnostic,
    LSPSymbol,
    LSPLocation,
    detect_lsp_server,
    LSP_SERVERS,
)
from ..debug import (
    DAPClient,
    StackFrame,
    Variable,
    Thread,
    Breakpoint,
    StoppedEvent,
    OutputEvent,
    detect_dap_adapter,
    DAP_ADAPTERS,
)
from ..ast import (
    ASTMatch,
    ASTQueryResult,
    ASTQuery,
    ASTRewrite,
    ASTEdit,
    ast_search,
    ast_edit_propose,
    ast_edit_resolve,
)

__all__ = [
    # LSP
    "LSPClient",
    "LSPPosition",
    "LSPRange",
    "LSPDocumentURI",
    "LSPDiagnostic",
    "LSPSymbol",
    "LSPLocation",
    "detect_lsp_server",
    "LSP_SERVERS",
    # DAP
    "DAPClient",
    "StackFrame",
    "Variable",
    "Thread",
    "Breakpoint",
    "StoppedEvent",
    "OutputEvent",
    "detect_dap_adapter",
    "DAP_ADAPTERS",
    # AST
    "ASTMatch",
    "ASTQueryResult",
    "ASTQuery",
    "ASTRewrite",
    "ASTEdit",
    "ast_search",
    "ast_edit_propose",
    "ast_edit_resolve",
]


def register_code_tools(registry):
    """Register code intelligence tools to a registry."""
    # Code intelligence tools are advanced - they require external LSP/DAP servers
    # For now, register stubs that can be used by the agent
    from ..tool_registry import BaseTool, ToolCategory, ToolSchema, ToolResult
    
    class DiagnoseTool(BaseTool):
        """Get diagnostics for a file."""
        name = "diagnose"
        description = "Get code diagnostics (errors, warnings)"
        category = ToolCategory.CODE
        
        schema = ToolSchema(
            properties={
                "path": {"type": "string", "description": "File path"},
            },
            required=["path"],
        )
        
        async def execute(self, path: str, **kwargs) -> ToolResult:
            try:
                from .lsp import detect_lsp_server, LSPClient
                server_cmd = detect_lsp_server(path)
                if not server_cmd:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error="No LSP server available. Install pyright, rust-analyzer, etc.",
                        is_error=True,
                    )
                
                client = LSPClient(server_cmd)
                await client.start()
                diagnostics = await client.get_diagnostics(path)
                await client.stop()
                
                if not diagnostics:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        content=[{"type": "text", "text": "No diagnostics"}],
                    )
                
                lines = [f"[{len(diagnostics)} diagnostics]"]
                for d in diagnostics[:20]:
                    lines.append(f"  {d.severity_name}: {d.message} (line {d.range.start.line + 1})")
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "\n".join(lines)}],
                )
            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=str(e),
                    is_error=True,
                )
    
    class SymbolsTool(BaseTool):
        """Get document symbols."""
        name = "symbols"
        description = "List code symbols in a file"
        category = ToolCategory.CODE
        
        schema = ToolSchema(
            properties={
                "path": {"type": "string", "description": "File path"},
            },
            required=["path"],
        )
        
        async def execute(self, path: str, **kwargs) -> ToolResult:
            try:
                from .lsp import detect_lsp_server, LSPClient
                server_cmd = detect_lsp_server(path)
                if not server_cmd:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error="No LSP server available",
                        is_error=True,
                    )
                
                client = LSPClient(server_cmd)
                await client.start()
                symbols = await client.get_symbols(path)
                await client.stop()
                
                if not symbols:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        content=[{"type": "text", "text": "No symbols found"}],
                    )
                
                lines = [f"[{len(symbols)} symbols]"]
                for s in symbols[:30]:
                    lines.append(f"  {s.kind_name}: {s.name}")
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "\n".join(lines)}],
                )
            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=str(e),
                    is_error=True,
                )
    
    class ReferencesTool(BaseTool):
        """Find symbol references."""
        name = "references"
        description = "Find all references to a symbol"
        category = ToolCategory.CODE
        
        schema = ToolSchema(
            properties={
                "path": {"type": "string", "description": "File path"},
                "line": {"type": "integer", "description": "Line number (1-indexed)"},
                "column": {"type": "integer", "description": "Column number"},
            },
            required=["path", "line"],
        )
        
        async def execute(self, path: str, line: int, column: int = 0, **kwargs) -> ToolResult:
            try:
                from .lsp import detect_lsp_server, LSPClient
                server_cmd = detect_lsp_server(path)
                if not server_cmd:
                    return ToolResult(
                        tool_name=self.name,
                        success=False,
                        error="No LSP server available",
                        is_error=True,
                    )
                
                client = LSPClient(server_cmd)
                await client.start()
                refs = await client.find_references(path, line - 1, column)
                await client.stop()
                
                if not refs:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        content=[{"type": "text", "text": "No references found"}],
                    )
                
                lines = [f"[{len(refs)} references]"]
                for r in refs[:20]:
                    if r.range:
                        lines.append(f"  {r.uri}:{r.range.start.line + 1}")
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "\n".join(lines)}],
                )
            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=str(e),
                    is_error=True,
                )
    
    class ASTSearchTool(BaseTool):
        """Search code using AST patterns."""
        name = "ast_search"
        description = "Search code using AST structural patterns"
        category = ToolCategory.CODE
        
        schema = ToolSchema(
            properties={
                "pattern": {"type": "string", "description": "AST pattern"},
                "path": {"type": "string", "description": "File or directory path"},
                "language": {"type": "string", "description": "Language (python, js, etc.)"},
            },
            required=["pattern", "path"],
        )
        
        async def execute(self, pattern: str, path: str, language: str = "auto", **kwargs) -> ToolResult:
            try:
                from .ast import ast_search
                result = await ast_search(pattern, [path], language)
                
                if not result.matches:
                    return ToolResult(
                        tool_name=self.name,
                        success=True,
                        content=[{"type": "text", "text": "No matches found"}],
                    )
                
                lines = [f"[{result.total_matches} matches]"]
                for m in result.matches[:20]:
                    lines.append(f"  {m.file}:{m.line}: {m.content[:60]}")
                
                return ToolResult(
                    tool_name=self.name,
                    success=True,
                    content=[{"type": "text", "text": "\n".join(lines)}],
                )
            except Exception as e:
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    error=str(e),
                    is_error=True,
                )
    
    # Register tools
    registry.register(DiagnoseTool())
    registry.register(SymbolsTool())
    registry.register(ReferencesTool())
    registry.register(ASTSearchTool())
