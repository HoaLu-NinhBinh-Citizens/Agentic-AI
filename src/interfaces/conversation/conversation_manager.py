"""
Conversational flow manager for interactive code review.
Enables back-and-forth dialogue with user.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any
from datetime import datetime
import asyncio


class MessageRole(Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


@dataclass
class Message:
    """A conversation message."""
    role: MessageRole
    content: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)
    attachments: list[str] = field(default_factory=list)


@dataclass
class Context:
    """Conversation context with history."""
    messages: list[Message] = field(default_factory=list)
    current_files: list[str] = field(default_factory=list)
    current_findings: list[dict] = field(default_factory=list)
    pending_actions: list[str] = field(default_factory=list)
    session_id: str = ""


class ConversationManager:
    """
    Manages conversational flow with user.
    Supports clarification, follow-up questions, and action confirmation.
    """

    def __init__(self):
        self._context = Context()
        self._handlers: dict[str, Callable] = {}
        self._register_handlers()

    async def process_message(self, user_input: str) -> str:
        """Process user message and generate response."""

        self.add_message(MessageRole.USER, user_input)

        intent = self._parse_intent(user_input)

        response = await self._dispatch(intent, user_input)

        self.add_message(MessageRole.ASSISTANT, response)

        return response

    def _parse_intent(self, text: str) -> str:
        """Parse user intent from message."""
        text_lower = text.lower()

        if any(kw in text_lower for kw in ["fix", "sửa", "apply"]):
            return "apply_fix"
        elif any(kw in text_lower for kw in ["explain", "giải thích", "why"]):
            return "explain"
        elif any(kw in text_lower for kw in ["skip", "bỏ qua", "ignore"]):
            return "skip"
        elif any(kw in text_lower for kw in ["next", "tiếp", "continue"]):
            return "next"
        elif any(kw in text_lower for kw in ["summary", "tổng hợp", "overview"]):
            return "summary"
        elif any(kw in text_lower for kw in ["help", "hướng dẫn", "?"]):
            return "help"
        elif any(kw in text_lower for kw in ["config", "cài đặt", "setting"]):
            return "config"
        else:
            return "general"

    async def _dispatch(self, intent: str, text: str) -> str:
        """Dispatch to appropriate handler."""
        handler = self._handlers.get(intent, self._handle_general)
        return await handler(text)

    def _register_handlers(self):
        """Register intent handlers."""
        self._handlers = {
            "apply_fix": self._handle_apply_fix,
            "explain": self._handle_explain,
            "skip": self._handle_skip,
            "next": self._handle_next,
            "summary": self._handle_summary,
            "help": self._handle_help,
            "config": self._handle_config,
            "general": self._handle_general,
        }

    async def _handle_apply_fix(self, text: str) -> str:
        """Handle fix application request."""
        import re

        match = re.search(r"@?(\S+):(\d+)", text)

        if match:
            file_path, line = match.groups()
            finding_msg = "N/A"
            rule_id = "N/A"
            risk = "MEDIUM"
            new_code = "N/A"

            if self._context.current_findings:
                finding = self._context.current_findings[0]
                finding_msg = finding.get("message", "N/A")
                rule_id = finding.get("rule_id", "N/A")
                risk = finding.get("risk", "MEDIUM")
                new_code = finding.get("new_code", "N/A")

            return f"""Okay, I'll apply the fix for `{file_path}:{line}`.

**Before applying, let me confirm:**

```python
# Issue: {finding_msg}
# Rule: {rule_id}
# Risk: {risk}
```

**Suggested fix:**
```python
{new_code}
```

Shall I proceed? (yes/no/auto)"""

        return "Which finding would you like to fix? Use `/fix @file:line`"

    async def _handle_explain(self, text: str) -> str:
        """Handle explanation request."""
        if not self._context.current_findings:
            return "No findings to explain. Run a review first with `/review`"

        finding = self._context.current_findings[0]
        return f"""## Explanation

**Rule:** {finding.get("rule_id", "N/A")}
**Severity:** {finding.get("severity", "MEDIUM")}
**File:** {finding.get("file_path", "N/A")}:{finding.get("line", 0)}

### Why This Is A Problem
{finding.get("explanation", "No detailed explanation available.")}

### Current Code
```python
{finding.get("old_code", "N/A")}
```

### Suggested Fix
```python
{finding.get("new_code", "N/A")}
```

### Best Practices
{finding.get("best_practice", "N/A")}

---

Do you want me to:
1. Apply this fix (`/fix`)
2. See next finding (`/next`)
3. Get full summary (`/summary`)"""

    async def _handle_skip(self, text: str) -> str:
        """Handle skip request."""
        self._context.pending_actions.append("skip")
        return "Okay, skipping this finding. Say `/next` to continue or `/summary` for overview."

    async def _handle_next(self, text: str) -> str:
        """Handle next finding request."""
        if not self._context.current_findings:
            return "No more findings. Run `/review` to analyze more files."

        self._context.pending_actions.append("next")
        finding = self._context.current_findings.pop(0)

        file_path = finding.get("file_path", "file")
        line_num = finding.get("line", 0)

        return f"""## Next Finding

**{finding.get("rule_id", "N/A")}** | **{finding.get("severity", "MEDIUM")}** severity
{finding.get("file_path", "unknown")}:{line_num}

### Message
{finding.get("message", "N/A")}

```python
{finding.get("old_code", "N/A")}
```

**Confidence:** {int(finding.get("confidence", 0.8) * 100)}%

What would you like to do?
- `/fix @{file_path}:{line_num}`
- `/explain`
- `/skip`"""

    async def _handle_summary(self, text: str) -> str:
        """Handle summary request."""
        findings = self._context.current_findings

        if not findings:
            return "No findings to summarize. Run `/review` first."

        by_severity = {"CRITICAL": [], "HIGH": [], "MEDIUM": [], "LOW": [], "INFO": []}
        for f in findings:
            sev = f.get("severity", "INFO").upper()
            if sev in by_severity:
                by_severity[sev].append(f)

        lines = ["## Review Summary\n", f"**Total findings:** {len(findings)}\n\n"]

        for sev, items in by_severity.items():
            if items:
                emoji = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🔵", "INFO": "⚪"}.get(sev, "")
                lines.append(f"{emoji} **{sev}:** {len(items)}")

        lines.append("\n### Top 3 Actionable\n")
        for i, f in enumerate(findings[:3], 1):
            lines.append(f"{i}. [{f.get('rule_id', 'N/A')}] {f.get('file_path', 'file')}:{f.get('line', 0)}")

        lines.append("\n### All Findings\n")
        lines.append("| Rule | File | Line | Severity | Message |")
        lines.append("|------|------|------|----------|---------|")
        for f in findings:
            msg = f.get("message", "N/A")[:50]
            lines.append(f"| {f.get('rule_id', 'N/A')} | {f.get('file_path', 'N/A')} | {f.get('line', 0)} | {f.get('severity', 'N/A')} | {msg}... |")

        return "\n".join(lines)

    async def _handle_help(self, text: str) -> str:
        """Handle help request."""
        return """## AI_SUPPORT Commands

### Review & Analysis
- `/review [files...]` - Analyze code for issues
- `/review --focus ml` - Focus on ML-specific issues
- `/review --focus security` - Focus on security issues

### Fixes
- `/fix @file:line` - Apply fix for specific finding
- `/fix --all` - Apply all safe fixes automatically
- `/fix --dry-run` - Preview all fixes without applying

### Navigation
- `/next` - Show next finding
- `/skip` - Skip current finding
- `/summary` - Show findings summary
- `/explain` - Explain current finding

### Configuration
- `/config` - Show current settings
- `/config --set model=llama3` - Change LLM model
- `/config --set confidence=0.8` - Set confidence threshold

### General
- `/help` - Show this help
- `/clear` - Clear conversation history

---

Type any question in natural language and I'll help you!"""

    async def _handle_config(self, text: str) -> str:
        """Handle configuration request."""
        return """## Current Configuration

| Setting | Value |
|---------|-------|
| LLM Model | llama3 |
| Confidence Threshold | 0.7 |
| Focus Areas | all |
| Auto-fix | disabled |

To change settings:
- `/config --set model=codellama`
- `/config --set confidence=0.9`
- `/config --set focus=ml,security`"""

    async def _handle_general(self, text: str) -> str:
        """Handle general questions."""
        return f"""I understand you're asking about: "{text[:100]}..."

For specific help, try:
- `/review [files]` - Analyze code
- `/fix @file:line` - Fix an issue
- `/summary` - See all findings
- `/help` - See all commands

Or ask me anything about the current findings!"""

    def add_message(self, role: MessageRole, content: str):
        """Add a message to the conversation."""
        self._context.messages.append(Message(
            role=role,
            content=content,
            timestamp=datetime.now()
        ))

    def set_findings(self, findings: list[dict]):
        """Set current findings for context."""
        self._context.current_findings = findings

    def get_context(self) -> Context:
        """Get current conversation context."""
        return self._context
