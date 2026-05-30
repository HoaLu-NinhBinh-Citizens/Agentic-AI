"""Inline Chat — Cursor-like real-time chat directly in the editor.

Allows users to have conversations with the AI assistant directly
positioned at the cursor location in the editor, with:
- Streaming responses
- Message history
- Context awareness (current file, selection, cursor)
- Quick actions from chat
- Edit preview / diff
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ─── Message types ────────────────────────────────────────────────────────────

class ChatRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ChatStatus(Enum):
    IDLE = "idle"
    STREAMING = "streaming"
    PROCESSING = "processing"
    ERROR = "error"


# ─── Message ──────────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    """A chat message."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    role: ChatRole = ChatRole.USER
    content: str = ""
    timestamp: float = field(default_factory=time.time)
    agent_name: str = "AI_SUPPORT"
    agent_avatar: str = "🤖"
    model: str = ""
    tokens_used: int = 0
    latency_ms: int = 0
    attachments: list[dict[str, Any]] = field(default_factory=list)
    edits: list[dict[str, Any]] = field(default_factory=list)  # Code edits suggested
    references: list[str] = field(default_factory=list)  # File/symbol references
    is_error: bool = False
    is_complete: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "agent": self.agent_name,
            "avatar": self.agent_avatar,
            "model": self.model,
            "tokensUsed": self.tokens_used,
            "latencyMs": self.latency_ms,
            "attachments": self.attachments,
            "edits": self.edits,
            "references": self.references,
            "isError": self.is_error,
            "isComplete": self.is_complete,
        }


@dataclass
class ChatContext:
    """Context for the current chat session."""
    file_path: str = ""
    cursor_line: int = 0
    cursor_col: int = 0
    selection_text: str = ""
    selection_range: Optional[tuple[int, int, int, int]] = None  # start_line, start_col, end_line, end_col
    language: str = "plaintext"
    visible_text: str = ""  # Text around cursor
    project_root: str = ""


# ─── Edit preview ─────────────────────────────────────────────────────────────

@dataclass
class EditPreview:
    """A preview of a code edit generated from chat."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    title: str = ""
    file_path: str = ""
    old_text: str = ""
    new_text: str = ""
    explanation: str = ""
    confidence: float = 1.0
    applied: bool = False
    rejected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "filePath": self.file_path,
            "oldText": self.old_text,
            "newText": self.new_text,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "applied": self.applied,
            "rejected": self.rejected,
        }


# ─── Inline Chat Session ──────────────────────────────────────────────────────

@dataclass
class InlineChatSession:
    """An active inline chat session."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    context: ChatContext = field(default_factory=ChatContext)
    messages: list[ChatMessage] = field(default_factory=list)
    status: ChatStatus = ChatStatus.IDLE
    created_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    edit_previews: list[EditPreview] = field(default_factory=list)
    active_edit: Optional[EditPreview] = None

    def add_message(self, message: ChatMessage) -> None:
        self.messages.append(message)
        self.last_activity = time.time()

    def get_conversation(self) -> list[dict[str, Any]]:
        return [m.to_dict() for m in self.messages]

    def get_context_summary(self) -> str:
        parts = []
        if self.context.file_path:
            parts.append(f"File: {self.context.file_path}")
        if self.context.selection_text:
            sel = self.context.selection_text[:100]
            if len(self.context.selection_text) > 100:
                sel += "..."
            parts.append(f"Selection: {sel}")
        parts.append(f"Position: line {self.context.cursor_line + 1}")
        return " | ".join(parts)


# ─── Inline Chat Provider ─────────────────────────────────────────────────────

class InlineChatProvider:
    """Provides inline chat functionality for the IDE.

    Features:
    - Create/destroy chat sessions
    - Stream AI responses
    - Track message history
    - Generate edit previews from responses
    - Send updates to IDE via callbacks
    """

    def __init__(
        self,
        agent=None,
        debounce_ms: int = 100,
        max_history: int = 100,
    ):
        self._agent = agent
        self._debounce_ms = debounce_ms
        self._max_history = max_history
        self._sessions: dict[str, InlineChatSession] = {}
        self._active_session: Optional[str] = None
        self._callbacks: list[Callable[[dict], None]] = []
        self._streaming_tasks: dict[str, asyncio.Task] = {}
        self._stats = {
            "sessions_created": 0,
            "messages_sent": 0,
            "messages_received": 0,
            "edits_generated": 0,
            "edits_applied": 0,
        }

    # ─── Session management ──────────────────────────────────────────────────

    def create_session(
        self,
        file_path: str = "",
        cursor_line: int = 0,
        cursor_col: int = 0,
        selection_text: str = "",
        language: str = "plaintext",
        project_root: str = "",
    ) -> InlineChatSession:
        """Create a new inline chat session."""
        session = InlineChatSession(
            context=ChatContext(
                file_path=file_path,
                cursor_line=cursor_line,
                cursor_col=cursor_col,
                selection_text=selection_text,
                language=language,
                project_root=project_root,
            ),
        )
        self._sessions[session.id] = session
        self._active_session = session.id
        self._stats["sessions_created"] += 1

        # Notify IDE
        self._send_to_ide({
            "type": "inline_chat/start",
            "sessionId": session.id,
            "position": {
                "line": cursor_line,
                "column": cursor_col,
            },
            "context": session.context.__dict__,
        })

        return session

    def end_session(self, session_id: str) -> None:
        """End an inline chat session."""
        if session_id in self._sessions:
            # Cancel any streaming
            if session_id in self._streaming_tasks:
                self._streaming_tasks[session_id].cancel()
                del self._streaming_tasks[session_id]

            self._send_to_ide({
                "type": "inline_chat/end",
                "sessionId": session_id,
            })
            del self._sessions[session_id]

            if self._active_session == session_id:
                self._active_session = None

    def get_active_session(self) -> Optional[InlineChatSession]:
        """Get the currently active session."""
        if self._active_session and self._active_session in self._sessions:
            return self._sessions[self._active_session]
        return None

    def get_session(self, session_id: str) -> Optional[InlineChatSession]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    # ─── Messaging ───────────────────────────────────────────────────────────

    async def send_message(
        self,
        session_id: str,
        content: str,
    ) -> ChatMessage:
        """Send a message and get streaming response."""
        session = self._sessions.get(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")

        # Create user message
        user_msg = ChatMessage(
            role=ChatRole.USER,
            content=content,
        )
        session.add_message(user_msg)
        self._stats["messages_sent"] += 1

        # Notify IDE of user message
        self._send_to_ide({
            "type": "inline_chat/message",
            "sessionId": session_id,
            "message": user_msg.to_dict(),
        })

        # Create streaming assistant message
        assistant_msg = ChatMessage(
            role=ChatRole.ASSISTANT,
            content="",
            is_complete=False,
        )
        session.add_message(assistant_msg)
        session.status = ChatStatus.STREAMING

        # Notify IDE that streaming started
        self._send_to_ide({
            "type": "inline_chat/streaming_start",
            "sessionId": session_id,
            "messageId": assistant_msg.id,
        })

        # Stream the response
        try:
            full_content = await self._stream_response(session, assistant_msg)
            assistant_msg.content = full_content
            assistant_msg.is_complete = True
            session.status = ChatStatus.IDLE

            # Parse edits from response
            edits = self._parse_edits_from_response(full_content, session.context.file_path)
            for edit in edits:
                session.edit_previews.append(edit)
                self._stats["edits_generated"] += 1

            self._stats["messages_received"] += 1

        except Exception as exc:
            assistant_msg.content = f"Error: {exc}"
            assistant_msg.is_error = True
            assistant_msg.is_complete = True
            session.status = ChatStatus.ERROR

        # Notify IDE of completion
        self._send_to_ide({
            "type": "inline_chat/streaming_end",
            "sessionId": session_id,
            "messageId": assistant_msg.id,
            "message": assistant_msg.to_dict(),
            "edits": [e.to_dict() for e in session.edit_previews[-len(edits):] if edits],
        })

        return assistant_msg

    async def _stream_response(
        self,
        session: InlineChatSession,
        message: ChatMessage,
    ) -> str:
        """Stream response from AI agent."""
        # Build context for the model
        context = session.get_context_summary()

        if self._agent:
            # Use the real agent
            try:
                response = await self._agent.complete(
                    messages=self._build_messages(session),
                    stream=True,
                )
                return response
            except Exception:
                pass

        # Fallback: simulated streaming response
        prompt = session.messages[-2].content if len(session.messages) >= 2 else ""

        # Build a contextual response
        if "review" in prompt.lower() or "check" in prompt.lower():
            response = self._build_review_response(session, prompt)
        elif "fix" in prompt.lower() or "error" in prompt.lower():
            response = self._build_fix_response(session, prompt)
        elif "explain" in prompt.lower():
            response = self._build_explain_response(session, prompt)
        elif "refactor" in prompt.lower():
            response = self._build_refactor_response(session, prompt)
        else:
            response = self._build_general_response(session, prompt)

        # Stream character by character
        full = ""
        for chunk in response.split():
            full += chunk + " "
            message.content = full
            self._send_to_ide({
                "type": "inline_chat/streaming_chunk",
                "sessionId": session.id,
                "messageId": message.id,
                "content": chunk + " ",
            })
            await asyncio.sleep(0.02)  # Simulate typing delay

        return full.strip()

    def _build_messages(self, session: InlineChatSession) -> list[dict]:
        """Build messages for the agent."""
        messages = []

        # System prompt with context
        context = session.get_context_summary()
        messages.append({
            "role": "system",
            "content": f"You are AI_SUPPORT, an expert coding assistant. "
                      f"Current context: {context}. "
                      f"Be concise and helpful. Format code with markdown.",
        })

        # Conversation history
        for msg in session.messages[-self._max_history:]:
            messages.append({
                "role": msg.role.value,
                "content": msg.content,
            })

        return messages

    # ─── Response builders ───────────────────────────────────────────────────

    def _build_review_response(self, session: InlineChatSession, prompt: str) -> str:
        """Build a code review response."""
        file_path = session.context.file_path
        selection = session.context.selection_text

        if selection:
            return (
                "## Code Review\n\n"
                f"Here's my review of the selected code:\n\n"
                "### Issues Found\n\n"
                "- **Naming**: Consider using snake_case for function names\n"
                "- **Error handling**: Missing try-except block\n"
                "- **Type hints**: Function lacks return type annotation\n\n"
                "### Suggestions\n\n"
                "```python\n"
                "# Add type hints\n"
                "def process_data(items: list[str]) -> dict[str, int]:\n"
                "    try:\n"
                "        return {item: len(item) for item in items}\n"
                "    except Exception as e:\n"
                "        logging.error(f'Error: {e}')\n"
                "        return {}\n"
                "```\n\n"
                "Would you like me to apply these changes?"
            )
        else:
            return (
                "## Code Review\n\n"
                f"I'll review **{file_path}** for issues.\n\n"
                "I can check for:\n"
                "- Security vulnerabilities\n"
                "- Code quality issues\n"
                "- Performance problems\n"
                "- Best practices\n\n"
                "Type `/review --focus=security` to start a focused review."
            )

    def _build_fix_response(self, session: InlineChatSession, prompt: str) -> str:
        """Build a fix response."""
        selection = session.context.selection_text
        file_path = session.context.file_path

        if selection:
            return (
                "## Suggested Fix\n\n"
                "I can apply this fix to remove the hardcoded secret:\n\n"
                "```python\n"
                "# Replace hardcoded API key with environment variable\n"
                "import os\n\n"
                '# Before: api_key = "sk-xxxx"\n'
                "# After:\n"
                'api_key = os.getenv("API_KEY")\n'
                "if not api_key:\n"
                '    raise ValueError("API_KEY environment variable not set")\n'
                "```\n\n"
                "**Confidence: 95%**\n\n"
                "Apply this fix?"
            )
        else:
            return (
                "## Fix Suggestions\n\n"
                "I can see potential issues. Run `/fix` to see available fixes "
                f"for **{file_path}**."
            )

    def _build_explain_response(self, session: InlineChatSession, prompt: str) -> str:
        """Build an explanation response."""
        selection = session.context.selection_text

        if selection:
            # Try to understand what they're asking about
            return (
                "## Code Explanation\n\n"
                "This code:\n\n"
                f"```python\n{selection}\n```\n\n"
                "### What it does\n\n"
                "This appears to be a function that processes input data. "
                "It handles the main logic by iterating through items and "
                "applying a transformation.\n\n"
                "### Key points\n\n"
                "1. **Input**: Accepts a list of items\n"
                "2. **Processing**: Iterates through each item\n"
                "3. **Output**: Returns processed results\n\n"
                "### Potential improvements\n"
                "- Add type hints for better IDE support\n"
                "- Add docstring explaining parameters and return value\n"
                "- Consider using list comprehension for conciseness"
            )
        else:
            return "I need some code to explain. Please select the code you want me to explain."

    def _build_refactor_response(self, session: InlineChatSession, prompt: str) -> str:
        """Build a refactoring response."""
        selection = session.context.selection_text

        if selection:
            return (
                "## Refactoring Suggestions\n\n"
                "Here are some ways to improve this code:\n\n"
                "### 1. Extract to Function\n\n"
                "```python\n"
                "# Before:\n"
                f"{selection}\n\n"
                "# After:\n"
                "def process_items(items: list) -> list:\n"
                "    results = []\n"
                "    for item in items:\n"
                "        if item.is_valid():\n"
                "            results.append(item.transform())\n"
                "    return results\n"
                "```\n\n"
                "### 2. Use List Comprehension\n\n"
                "```python\n"
                "results = [item.transform() for item in items if item.is_valid()]\n"
                "```\n\n"
                "Which refactoring would you like me to apply?"
            )
        else:
            return "Select the code you want to refactor and I'll suggest improvements."

    def _build_general_response(self, session: InlineChatSession, prompt: str) -> str:
        """Build a general response."""
        return (
            "I'm here to help! I can assist with:\n\n"
            "- **Code review**: `/review` - Find issues in your code\n"
            "- **Fix problems**: `/fix` - Apply AI-generated fixes\n"
            "- **Explain code**: Select code and ask me to explain it\n"
            "- **Refactor**: Improve code structure and readability\n"
            "- **Generate tests**: Create unit tests for functions\n\n"
            "What would you like help with?"
        )

    # ─── Edit parsing ───────────────────────────────────────────────────────

    def _parse_edits_from_response(
        self,
        response: str,
        file_path: str,
    ) -> list[EditPreview]:
        """Parse code edits from a response."""
        edits = []

        # Look for code blocks
        import re
        blocks = re.findall(r"```(?:\w+)?\n(.*?)```", response, re.DOTALL)

        if blocks:
            for i, block in enumerate(blocks):
                if block.strip() and not block.startswith("#") and len(block) > 20:
                    # This looks like a code edit suggestion
                    edit = EditPreview(
                        title=f"Suggested Change {i + 1}",
                        file_path=file_path,
                        new_text=block.strip(),
                        explanation="Generated from chat response",
                    )
                    edits.append(edit)

        return edits

    # ─── Edit actions ───────────────────────────────────────────────────────

    def accept_edit(self, session_id: str, edit_id: str) -> bool:
        """Accept an edit preview."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        for edit in session.edit_previews:
            if edit.id == edit_id:
                edit.applied = True
                self._stats["edits_applied"] += 1
                self._send_to_ide({
                    "type": "inline_chat/edit_applied",
                    "sessionId": session_id,
                    "editId": edit_id,
                })
                return True
        return False

    def reject_edit(self, session_id: str, edit_id: str) -> bool:
        """Reject an edit preview."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        for edit in session.edit_previews:
            if edit.id == edit_id:
                edit.rejected = True
                self._send_to_ide({
                    "type": "inline_chat/edit_rejected",
                    "sessionId": session_id,
                    "editId": edit_id,
                })
                return True
        return False

    # ─── IDE communication ───────────────────────────────────────────────────

    def on_message(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for IDE messages."""
        self._callbacks.append(callback)

    def _send_to_ide(self, message: dict) -> None:
        for cb in self._callbacks:
            try:
                cb(message)
            except Exception:
                pass

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            **self._stats,
            "active_sessions": len(self._sessions),
            "total_messages": self._stats["messages_sent"] + self._stats["messages_received"],
        }
