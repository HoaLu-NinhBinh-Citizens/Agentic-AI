"""Ghost text (inline completion) integration for IDEs.

Shows AI-generated code completions directly in the editor,
similar to Cursor's inline completions feature.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from src.interfaces.ide.bridge.protocol import (
    CompletionItem, InlineCompletion, MessageType,
)


@dataclass
class GhostTextConfig:
    """Configuration for ghost text behavior."""
    debounce_ms: int = 150
    max_lines: int = 20
    max_chars_per_line: int = 200
    show_in_ghost_mode: bool = True  # Grey out the completion
    accept_on_tab: bool = True
    accept_on_enter: bool = False
    dismiss_on_escape: bool = True
    auto_trigger: bool = True
    min_trigger_chars: int = 3


@dataclass
class GhostTextSession:
    """An active ghost text session."""
    id: str
    file_path: str
    cursor_line: int
    cursor_col: int
    trigger_text: str
    completion: Optional[InlineCompletion] = None
    accepted: bool = False
    dismissed: bool = False
    created_at: float = field(default_factory=time.time)


class GhostTextProvider:
    """Provides inline completions (ghost text) to IDEs.

    Integrates with the completion engine to generate AI-powered
    inline suggestions that appear directly in the editor.
    """

    def __init__(
        self,
        completion_engine: Optional[Any] = None,
        config: Optional[GhostTextConfig] = None,
    ):
        self.engine = completion_engine
        self.config = config or GhostTextConfig()
        self._sessions: dict[str, GhostTextSession] = {}
        self._callbacks: list[Callable[[dict], None]] = []
        self._debounce_task: Optional[asyncio.Task] = None
        self._debounce_event = asyncio.Event()
        self._pending_trigger: Optional[dict] = None

    # ─── Session management ──────────────────────────────────────────────────

    def start_session(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        trigger_text: str,
    ) -> GhostTextSession:
        """Start a new ghost text session."""
        session = GhostTextSession(
            id=f"gt-{int(time.time() * 1000)}",
            file_path=file_path,
            cursor_line=cursor_line,
            cursor_col=cursor_col,
            trigger_text=trigger_text,
        )
        self._sessions[session.id] = session
        return session

    def trigger_session(self, session: GhostTextSession) -> None:
        """Trigger completion for an existing session (async, no running loop required)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running — store for later trigger
            return
        loop.create_task(self._trigger_completion(session))

    def end_session(self, session_id: str) -> Optional[GhostTextSession]:
        """End a ghost text session."""
        session = self._sessions.pop(session_id, None)
        if session and not session.accepted and not session.dismissed:
            # User didn't accept or dismiss - they moved away
            self._send_dismiss(session)
        return session

    # ─── Trigger & completion ────────────────────────────────────────────────

    def on_cursor_changed(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        current_line_text: str,
    ) -> None:
        """Called when cursor position changes. Debounces completion requests."""
        if not self.config.auto_trigger:
            return

        # Cancel pending debounce
        if self._debounce_task and not self._debounce_task.done():
            self._debounce_task.cancel()

        self._pending_trigger = {
            "file_path": file_path,
            "cursor_line": cursor_line,
            "cursor_col": cursor_col,
            "trigger_text": current_line_text,
        }
        self._debounce_event.set()

        # Start new debounce (defer to trigger_debounce)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._debounce_task = loop.create_task(self._debounce_trigger())

    async def _debounce_trigger(self) -> None:
        """Wait debounce period then trigger completion."""
        try:
            await asyncio.sleep(self.config.debounce_ms / 1000.0)
        except asyncio.CancelledError:
            return
        if self._pending_trigger:
            t = self._pending_trigger
            self._pending_trigger = None
            session = GhostTextSession(
                id=f"gt-{int(time.time() * 1000)}",
                file_path=t["file_path"],
                cursor_line=t["cursor_line"],
                cursor_col=t["cursor_col"],
                trigger_text=t["trigger_text"],
            )
            self._sessions[session.id] = session
            await self._trigger_completion(session)

    async def _trigger_completion(self, session: GhostTextSession) -> None:
        """Generate completion for a session."""
        if len(session.trigger_text) < self.config.min_trigger_chars:
            return

        try:
            if self.engine:
                # Collect tokens from the completion engine
                result = await self._collect_completion(
                    file_path=session.file_path,
                    prefix=session.trigger_text,
                )
                if result:
                    items = self._convert_to_completion_items(result)
                    if items:
                        completion = InlineCompletion(items=items)
                        session.completion = completion
                        await self._send_completion(session)
            else:
                # Fallback: simple line completion
                items = self._simple_completion(session.trigger_text)
                if items:
                    completion = InlineCompletion(items=items)
                    session.completion = completion
                    await self._send_completion(session)
        except Exception:
            pass  # Silently fail - completions are non-blocking

    async def _collect_completion(
        self,
        file_path: str,
        prefix: str,
    ) -> Optional[dict[str, Any]]:
        """Collect completion from the engine and return as a dict result."""
        engine = self.engine
        if hasattr(engine, "complete"):
            # Use streaming completion engine
            buffer = ""
            async for token in engine.complete(
                file_path=file_path,
                cursor_line=0,
                cursor_col=0,
                source_before=prefix,
                source_after="",
            ):
                buffer += token.text

            if buffer:
                return {"choices": [{"text": buffer, "score": 1.0}]}
        return None

    def _convert_to_completion_items(
        self, result: dict[str, Any]
    ) -> list[CompletionItem]:
        """Convert completion engine result to IDE completion items."""
        items = []
        for i, choice in enumerate(result.get("choices", [])):
            text = choice.get("text", "")
            # Truncate to max_lines
            lines = text.split("\n")[: self.config.max_lines]
            text = "\n".join(lines)[: self.config.max_chars_per_line * self.config.max_lines]

            items.append(CompletionItem(
                label=text[:50],
                insert_text=text,
                kind="text",
                detail=f"AI Completion #{i + 1}",
                documentation=f"Generated completion with {len(text)} characters",
                score=choice.get("score", 1.0 - i * 0.1),
                sort_text=f"{1000 - i:04d}",
            ))

        return items

    def _simple_completion(self, prefix: str) -> list[CompletionItem]:
        """Simple pattern-based completion as fallback."""
        # Try to detect common patterns and suggest completions
        items = []

        if prefix.rstrip().endswith("("):
            # Function call - suggest closing
            items.append(CompletionItem(
                label=")",
                insert_text=")",
                kind="text",
                detail="Close parenthesis",
            ))

        if prefix.rstrip().endswith("{"):
            items.append(CompletionItem(
                label="}",
                insert_text="}",
                kind="text",
                detail="Close brace",
            ))

        if prefix.rstrip().endswith('"'):
            items.append(CompletionItem(
                label='"\n    \n"',
                insert_text='"\n    \n"',
                kind="text",
                detail="Close quote with newlines",
            ))

        return items

    # ─── Accept/dismiss ────────────────────────────────────────────────────

    async def accept_completion(self, session_id: str) -> Optional[str]:
        """Accept the current ghost text completion."""
        session = self._sessions.get(session_id)
        if not session or not session.completion:
            return None

        session.accepted = True
        session.completion.is_incomplete = False

        # Return the accepted text
        if session.completion.items:
            # Return the first (best) completion
            return session.completion.items[0].insert_text

        return session.completion.text

    async def dismiss_completion(self, session_id: str) -> None:
        """Dismiss the current ghost text."""
        session = self._sessions.get(session_id)
        if session:
            session.dismissed = True
            self._send_dismiss(session)

    # ─── IDE communication ────────────────────────────────────────────────────

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for messages from the IDE."""
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        """Send a message to the IDE."""
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    async def _send_completion(self, session: GhostTextSession) -> None:
        """Send completion to IDE."""
        if not session.completion:
            return

        message = session.completion.to_ide_message()
        message["sessionId"] = session.id
        message["filePath"] = session.file_path
        message["cursor"] = {
            "line": session.cursor_line,
            "column": session.cursor_col,
        }
        self._send_to_ide(message)

    def _send_dismiss(self, session: GhostTextSession) -> None:
        """Send dismiss to IDE."""
        self._send_to_ide({
            "type": MessageType.COMPLETION_DISMISS.value,
            "sessionId": session.id,
        })

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        """Get ghost text statistics."""
        accepted = sum(1 for s in self._sessions.values() if s.accepted)
        dismissed = sum(1 for s in self._sessions.values() if s.dismissed)
        active = len(self._sessions) - accepted - dismissed
        return {
            "total_sessions": len(self._sessions),
            "accepted": accepted,
            "dismissed": dismissed,
            "active": active,
        }
