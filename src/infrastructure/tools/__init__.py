"""Infrastructure tools module.

Built-in tools:
- File: read, write, edit, find
- Search: search, grep
- Shell: bash, pwd, cd
- LSP: diagnostics, symbols, references, definitions, rename
- DAP: debugger breakpoints, stepping, variables
- AST: structural code queries and rewrites
- Web: search, extract_url
"""

from .tool_registry import (
    BaseTool,
    ToolCallRequest,
    ToolCallResponse,
    ToolCategory,
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    ToolSchema,
    get_registry,
    register_tool,
)
from .hashline import (
    EditResult,
    HashlineAnchor,
    HashlineEditor,
    HashlinePatch,
    edit_file,
    preview_edit,
)
from .lsp import (
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
from .debug import (
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
from .ast import (
    ASTMatch,
    ASTQueryResult,
    ASTQuery,
    ASTRewrite,
    ASTEdit,
    ast_search,
    ast_edit_propose,
    ast_edit_resolve,
)
from .web_search import (
    SearchResult,
    SearchResponse,
    WebSearch,
    web_search,
    extract_url,
)

__all__ = [
    # Registry
    "ToolRegistry",
    "ToolDefinition",
    "ToolSchema",
    "ToolCategory",
    "ToolResult",
    "ToolCallRequest",
    "ToolCallResponse",
    "BaseTool",
    "get_registry",
    "register_tool",
    # Hashline
    "HashlineEditor",
    "HashlinePatch",
    "HashlineAnchor",
    "EditResult",
    "edit_file",
    "preview_edit",
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
    # Web Search
    "SearchResult",
    "SearchResponse",
    "WebSearch",
    "web_search",
    "extract_url",
]
