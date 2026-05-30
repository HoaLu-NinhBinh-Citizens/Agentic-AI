"""Code actions provider — implements lightbulb / quick fix functionality.

Detects code issues and provides actionable fixes directly in the IDE,
with lightbulb icons on the gutter (like Cursor/VS Code).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.interfaces.ide.bridge.protocol import (
    CodeAction, Diagnostic, MessageType, Range, TextEdit,
)
from src.infrastructure.analysis.rule_engine import RuleEngine
from src.core.fix_engine.models import Fix, FixStatus
from src.core.fix_engine.apply_fix import ApplyFixTool


@dataclass
class CodeActionContext:
    """Context for code action detection."""
    file_path: str
    cursor_line: int
    cursor_col: int
    selection: Optional[tuple[int, int, int, int]] = None  # start_line, start_col, end_line, end_col
    diagnostics: list[Diagnostic] = field(default_factory=list)
    trigger_kind: str = "invoked"  # invoked, automatic
    only: list[str] = field(default_factory=list)  # filter by action kind


class CodeActionProvider:
    """Provides code actions (lightbulb) in the IDE.

    Monitors diagnostics and generates actionable fixes that appear
    as lightbulb icons in the editor gutter.
    """

    def __init__(
        self,
        rule_engine: Optional[RuleEngine] = None,
        fix_tool: Optional[ApplyFixTool] = None,
    ):
        self.rule_engine = rule_engine or RuleEngine()
        self.fix_tool = fix_tool or ApplyFixTool()
        self._callbacks: list[Callable[[dict], None]] = []
        self._pending_actions: dict[str, list[CodeAction]] = {}
        self._action_stats = {
            "offered": 0,
            "accepted": 0,
            "dismissed": 0,
        }

    # ─── Request code actions ────────────────────────────────────────────────

    async def get_code_actions(
        self,
        context: CodeActionContext,
    ) -> list[CodeAction]:
        """Get available code actions for the current cursor position."""
        actions: list[CodeAction] = []

        # Get diagnostics at cursor
        at_cursor = self._get_diagnostics_at(context)
        if at_cursor:
            actions.extend(self._actions_from_diagnostics(at_cursor, context.file_path))

        # Get context-aware actions (e.g., add import, organize imports)
        actions.extend(self._get_context_actions(context))

        # Filter by 'only' if specified
        if context.only:
            actions = [a for a in actions if a.kind in context.only]

        # Sort: preferred first, then by severity
        actions.sort(key=lambda a: (not a.is_preferred, a.kind))

        self._action_stats["offered"] += len(actions)

        # Track for later apply
        if actions:
            self._pending_actions[context.file_path] = actions

        return actions

    def _get_diagnostics_at(
        self,
        context: CodeActionContext,
    ) -> list[Diagnostic]:
        """Get diagnostics at the current cursor position."""
        if not context.diagnostics:
            return []

        for diag in context.diagnostics:
            if not diag.range:
                continue
            if diag.file_path != context.file_path:
                continue

            line = context.cursor_line
            if diag.range.start_line <= line <= diag.range.end_line:
                return [diag]

        return []

    def _actions_from_diagnostics(
        self,
        diagnostics: list[Diagnostic],
        file_path: str,
    ) -> list[CodeAction]:
        """Generate code actions from diagnostics."""
        actions = []

        for diag in diagnostics:
            rule_id = diag.code
            rule = self.rule_engine.get_rule(rule_id) if rule_id else None

            if rule and rule.fix_template:
                action = self._make_action_from_rule(rule, diag)
                if action:
                    actions.append(action)

            # Generic fix action for any diagnostic
            actions.append(CodeAction(
                title=f"Fix: {diag.message[:60]}",
                kind="quickfix",
                detail=f"Apply fix for {diag.source} diagnostic",
                diagnostics=[diag.id],
                is_preferred=rule is not None and bool(rule.fix_template),
            ))

        return actions

    def _get_context_actions(
        self,
        context: CodeActionContext,
    ) -> list[CodeAction]:
        """Get context-aware actions (organize imports, add import, etc.)."""
        actions = []

        # Organize imports action
        actions.append(CodeAction(
            title="Organize Imports",
            kind="source.organizeImports",
            command="editor.action.organizeImports",
            detail="Sort and remove unused imports",
            is_preferred=False,
        ))

        # Extract to function (if there's a selection)
        if context.selection:
            actions.append(CodeAction(
                title="Extract to Function",
                kind="refactor.extract.function",
                detail="Extract selected code to a new function",
                is_preferred=False,
            ))

        # Add type annotation
        actions.append(CodeAction(
            title="Add Type Annotation",
            kind="source.addTypeAnnotation",
            detail="Add type annotation for the current symbol",
            is_preferred=False,
        ))

        return actions

    def _make_action_from_rule(
        self,
        rule: Any,
        diag: Diagnostic,
    ) -> Optional[CodeAction]:
        """Create a code action from a rule."""
        fix_template = getattr(rule, "fix_template", "") or ""
        if not fix_template:
            return None

        edits = []
        if diag.range:
            edits.append(TextEdit(
                range=diag.range,
                new_text=fix_template,
            ))

        return CodeAction(
            title=f"Fix with {rule.id}: {rule.name}",
            kind="quickfix",
            edits=edits,
            diagnostics=[diag.id],
            is_preferred=True,
            detail=f"Apply fix: {getattr(rule, 'description', '')}",
        )

    # ─── IDE communication ────────────────────────────────────────────────────

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for messages from the IDE."""
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    async def send_code_actions(
        self,
        context: CodeActionContext,
        actions: list[CodeAction],
    ) -> None:
        """Send available code actions to the IDE."""
        message = {
            "type": MessageType.CODE_ACTION.value,
            "actions": [a.to_dict() for a in actions],
            "filePath": context.file_path,
            "cursor": {
                "line": context.cursor_line,
                "column": context.cursor_col,
            },
            "timestamp": time.time(),
        }
        self._send_to_ide(message)

    # ─── Apply action ─────────────────────────────────────────────────────────

    async def apply_action(
        self,
        action_id: str,
        file_path: str,
    ) -> dict[str, Any]:
        """Apply a code action. Returns result."""
        self._action_stats["accepted"] += 1

        # Find the action
        actions = self._pending_actions.get(file_path, [])
        action = next((a for a in actions if a.id == action_id), None)
        if not action:
            return {"success": False, "error": "Action not found"}

        if action.edits:
            # Apply each edit using the fix tool
            for edit in action.edits:
                result = await self._apply_text_edit(file_path, edit)
                if not result["success"]:
                    return result

        if action.command:
            # Execute command
            return {"success": True, "command": action.command}

        return {"success": True}

    async def _apply_text_edit(
        self,
        file_path: str,
        edit: TextEdit,
    ) -> dict[str, Any]:
        """Apply a text edit using the fix tool."""
        # Build a Fix object from the TextEdit
        fix = Fix(
            id=f"action-{edit.range.start_line}",
            file_path=file_path,
            line_start=edit.range.start_line,
            line_end=edit.range.end_line,
            old_text="",
            new_text=edit.new_text,
            reason="Code action",
        )
        result = self.fix_tool.apply_fix(fix)
        return {
            "success": result.success,
            "error": result.error if not result.success else "",
            "backup_path": result.backup_path,
        }

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get code action statistics."""
        total = self._action_stats["offered"]
        accepted = self._action_stats["accepted"]
        return {
            **self._action_stats,
            "acceptance_rate": accepted / total if total > 0 else 0.0,
        }
