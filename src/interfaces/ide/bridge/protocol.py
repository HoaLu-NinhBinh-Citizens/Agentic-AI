"""IDE Bridge Protocol — Cursor-like message types for IDE integration.

Defines the message protocol for communicating with IDEs (VS Code, Neovim, etc.)
via WebSocket or STDIO. Supports:
- Inline completions (ghost text)
- Inline chat
- Quick actions / code actions
- Live diagnostics
- Document sync
- Cursor position tracking
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class MessageType(Enum):
    """Message types for IDE <-> Agent communication."""
    # Agent -> IDE
    COMPLETION = "completion"
    COMPLETION_ACCEPT = "completion/accept"
    COMPLETION_DISMISS = "completion/dismiss"
    INLINE_CHAT = "inline_chat"
    CODE_ACTION = "code_action"
    QUICK_FIX = "quick_fix"
    DIAGNOSTIC = "diagnostic"
    GHOST_TEXT = "ghost_text"
    PROGRESS = "progress"
    NOTIFICATION = "notification"

    # IDE -> Agent
    CHAT_REQUEST = "chat_request"
    EDIT_ACCEPTED = "edit_accepted"
    EDIT_REJECTED = "edit_rejected"
    CURSOR_MOVED = "cursor_moved"
    DOCUMENT_CHANGED = "document_changed"
    ACTIVE_FILE_CHANGED = "active_file_changed"
    SELECTION_CHANGED = "selection_changed"
    COMMAND_EXECUTED = "command_executed"


@dataclass
class TextEdit:
    """A text edit to be applied to a document."""
    range: Range
    new_text: str
    priority: int = 0

    def to_lsp(self) -> dict[str, Any]:
        return {
            "range": self.range.to_lsp(),
            "newText": self.new_text,
        }


@dataclass
class Range:
    """A range in a text document."""
    start_line: int
    start_col: int
    end_line: int
    end_col: int

    def to_lsp(self) -> dict[str, Any]:
        return {
            "start": {"line": self.start_line, "character": self.start_col},
            "end": {"line": self.end_line, "character": self.end_col},
        }

    @classmethod
    def from_lsp(cls, lsp_range: dict) -> Range:
        return cls(
            start_line=lsp_range["start"]["line"],
            start_col=lsp_range["start"]["character"],
            end_line=lsp_range["end"]["line"],
            end_col=lsp_range["end"]["character"],
        )


@dataclass
class InlineCompletion:
    """An inline completion (ghost text) to show in the IDE."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    text: str = ""
    range: Optional[Range] = None
    is_incomplete: bool = False
    items: list[CompletionItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_ide_message(self) -> dict[str, Any]:
        if self.items:
            return {
                "type": MessageType.COMPLETION.value,
                "id": self.id,
                "items": [item.to_dict() for item in self.items],
                "isIncomplete": self.is_incomplete,
            }
        return {
            "type": MessageType.GHOST_TEXT.value,
            "id": self.id,
            "text": self.text,
            "range": self.range.to_lsp() if self.range else None,
            "isIncomplete": self.is_incomplete,
        }


@dataclass
class CompletionItem:
    """A completion item with label, text, and metadata."""
    label: str
    insert_text: str
    kind: str = "text"
    detail: str = ""
    documentation: str = ""
    additional_text_edits: list[TextEdit] = field(default_factory=list)
    command: Optional[dict] = None
    score: float = 0.0
    sort_text: str = ""
    filter_text: str = ""
    preselect: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "insertText": self.insert_text,
            "kind": self.kind,
            "detail": self.detail,
            "documentation": self.documentation,
            "additionalTextEdits": [t.to_lsp() for t in self.additional_text_edits],
            "command": self.command,
            "sortText": self.sort_text or self.label,
            "filterText": self.filter_text or self.insert_text,
            "preselect": self.preselect,
            "_score": self.score,
        }


@dataclass
class CodeAction:
    """A code action / quick fix."""
    title: str
    kind: str = "quickfix"  # quickfix, refactor, source.organizeImports
    command: Optional[str] = None
    edits: list[TextEdit] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    is_preferred: bool = False
    disabled: str = ""
    detail: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "kind": self.kind,
            "id": self.id,
            "command": self.command,
            "edit": {
                "changes": self._build_changes(),
            } if self.edits else None,
            "diagnostics": self.diagnostics,
            "isPreferred": self.is_preferred,
            "disabled": {"reason": self.disabled} if self.disabled else None,
            "detail": self.detail,
        }

    def _build_changes(self) -> dict[str, list[dict]]:
        by_file: dict[str, list[dict]] = {}
        for edit in self.edits:
            file_path = "unknown"  # Placeholder - caller fills this
            if file_path not in by_file:
                by_file[file_path] = []
            by_file[file_path].append(edit.to_lsp())
        return by_file


@dataclass
class InlineChat:
    """An inline chat message in the IDE."""
    message: str
    agent_name: str = "AI_SUPPORT"
    agent_avatar: str = "🤖"
    suggestions: list[str] = field(default_factory=list)
    can_continue: bool = True
    position: Optional[Range] = None
    is_streaming: bool = False
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_ide_message(self) -> dict[str, Any]:
        return {
            "type": MessageType.INLINE_CHAT.value,
            "id": self.id,
            "message": self.message,
            "position": self.position.to_lsp() if self.position else None,
            "isStreaming": self.is_streaming,
            "agent": {
                "name": self.agent_name,
                "avatar": self.agent_avatar,
            },
            "suggestions": self.suggestions,
            "canContinue": self.can_continue,
        }


@dataclass
class Diagnostic:
    """A diagnostic (error/warning/info) for the Problems panel."""
    message: str
    file_path: str = ""
    severity: str = "error"  # error, warning, info, hint
    range: Optional[Range] = None
    code: str = ""
    source: str = "AI_SUPPORT"
    related: list[RelatedDiagnostic] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_ide_message(self) -> dict[str, Any]:
        return {
            "type": MessageType.DIAGNOSTIC.value,
            "id": self.id,
            "severity": self._severity_to_lsp(),
            "message": self.message,
            "filePath": self.file_path,
            "range": self.range.to_lsp() if self.range else None,
            "code": self.code,
            "source": self.source,
            "related": [r.to_dict() for r in self.related],
        }

    def _severity_to_lsp(self) -> int:
        return {"error": 1, "warning": 2, "info": 3, "hint": 4}.get(self.severity, 1)


@dataclass
class RelatedDiagnostic:
    """Related location for a diagnostic."""
    range: Range
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "location": {
                "uri": "",
                "range": self.range.to_lsp(),
            },
        }


@dataclass
class IDEBridgeMessage:
    """A complete IDE bridge message."""
    type: MessageType
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default=0.0)
    session_id: str = ""
    request_id: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": self.id,
            "method" if self.payload else "result": (
                self.payload if self.payload else {}
            ),
            "sessionId": self.session_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_json(cls, data: dict) -> IDEBridgeMessage:
        return cls(
            type=MessageType(data.get("method", "notification")),
            id=data.get("id", str(uuid.uuid4())[:8]),
            payload=data.get("params", {}),
        )
