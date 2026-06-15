"""IDE Bridge — Cursor-like IDE integration with inline completions and code actions."""

from src.interfaces.ide.bridge.protocol import (
    CodeAction,
    CompletionItem,
    Diagnostic,
    IDEBridgeMessage,
    InlineChat,
    InlineCompletion,
    MessageType,
    Range,
    TextEdit,
)
from src.interfaces.ide.bridge.code_actions import (
    CodeActionContext,
    CodeActionProvider,
)

__all__ = [
    # Protocol
    "MessageType",
    "Range",
    "TextEdit",
    "CompletionItem",
    "InlineCompletion",
    "CodeAction",
    "Diagnostic",
    "InlineChat",
    "IDEBridgeMessage",
    # Code actions
    "CodeActionProvider",
    "CodeActionContext",
]
