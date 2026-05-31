"""Composer-style chat for AI_SUPPORT.
Conversational refactoring and code generation.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Literal, Any

logger = logging.getLogger(__name__)


class ComposerMode(Enum):
    """Mode of the composer."""
    EDIT = "edit"           # Edit existing code
    CREATE = "create"       # Create new files
    REFACTOR = "refactor"    # Refactor existing code
    EXPLAIN = "explain"      # Explain code
    DEBUG = "debug"          # Debug code


@dataclass
class ComposerMessage:
    """A message in the composer conversation."""
    role: Literal["user", "assistant", "system"]
    content: str
    files_referenced: list[str] = field(default_factory=list)
    code_changes: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 1.0


@dataclass
class ComposerContext:
    """Context for the composer workflow."""
    mode: ComposerMode = ComposerMode.EDIT
    active_file: Optional[str] = None
    selection_start: Optional[int] = None
    selection_end: Optional[int] = None
    conversation_history: list[ComposerMessage] = field(default_factory=list)
    last_intent: Optional[str] = None


@dataclass
class Intent:
    """Parsed user intent."""
    type: str  # "create", "edit", "refactor", "explain", "debug", "search"
    files: list[str] = field(default_factory=list)
    matches: tuple = field(default_factory=tuple)
    changes: list[dict[str, Any]] = field(default_factory=list)


class ComposerWorkflow:
    """Chat-based code editing workflow like Cursor Composer.
    
    Features:
    - Conversational code editing
    - Intent detection from natural language
    - Multi-file operations
    - Code generation and refactoring
    - Code explanation
    
    Usage:
        composer = ComposerWorkflow(project_root=Path("."))
        response = await composer.chat("create a new file for handling users")
    """
    
    def __init__(self, project_root: Path | str, llm_provider=None):
        self.project_root = Path(project_root)
        self.llm_provider = llm_provider
        self.context = ComposerContext()
        self._file_changes: dict[str, str] = {}  # file -> original content
    
    async def chat(self, message: str) -> ComposerMessage:
        """Process a chat message and return assistant response.
        
        Args:
            message: User's chat message
            
        Returns:
            ComposerMessage with assistant's response
        """
        # Parse intent from message
        intent = self._parse_intent(message)
        
        # Update context based on intent
        self._update_context(intent, message)
        
        # Generate response based on intent type
        if intent.type == "create":
            response = await self._handle_create(message, intent)
        elif intent.type == "refactor":
            response = await self._handle_refactor(message, intent)
        elif intent.type == "explain":
            response = await self._handle_explain(message, intent)
        elif intent.type == "debug":
            response = await self._handle_debug(message, intent)
        elif intent.type == "search":
            response = await self._handle_search(message, intent)
        else:
            response = await self._handle_edit(message, intent)
        
        # Save to history
        user_msg = ComposerMessage(
            role="user",
            content=message,
            files_referenced=intent.files,
        )
        assistant_msg = ComposerMessage(
            role="assistant",
            content=response,
            files_referenced=intent.files,
            code_changes=intent.changes,
        )
        
        self.context.conversation_history.append(user_msg)
        self.context.conversation_history.append(assistant_msg)
        
        return assistant_msg
    
    def _parse_intent(self, message: str) -> Intent:
        """Parse user intent from message using pattern matching.
        
        Args:
            message: User message to parse
            
        Returns:
            Intent with parsed information
        """
        message_lower = message.lower()
        
        # Pattern matching for intent types
        patterns = [
            # Create patterns
            (r"create\s+(?:a\s+)?(?:new\s+)?(?:file|class|function|module)\s+(?:called\s+)?(?:for\s+)?(\w+)", "create"),
            (r"add\s+(?:a\s+)?new\s+(?:file|class|function)\s+(?:called\s+)?(\w+)", "create"),
            (r"make\s+(?:a\s+)?(?:new\s+)?(?:file|class|function)\s+(?:for|called)\s+(\w+)", "create"),
            
            # Refactor patterns
            (r"refactor\s+(\w+)", "refactor"),
            (r"rename\s+(\w+)\s+(?:to|into)\s+(\w+)", "refactor"),
            (r"extract\s+(?:function|method)\s+(?:from|called)?\s*(\w+)?", "refactor"),
            (r"move\s+(\w+)\s+(?:to|from)\s+(\w+)", "refactor"),
            (r"inline\s+(\w+)", "refactor"),
            
            # Explain patterns
            (r"explain\s+(\w+)", "explain"),
            (r"what\s+does\s+(\w+)\s+do", "explain"),
            (r"how\s+(?:does|do)\s+(\w+)\s+work", "explain"),
            (r"what\s+is\s+(\w+)", "explain"),
            (r"describe\s+(\w+)", "explain"),
            
            # Debug patterns
            (r"debug\s+(\w+)", "debug"),
            (r"fix\s+(?:the\s+)?(?:bug\s+(?:in|with))?\s*(\w+)?", "debug"),
            (r"why\s+(?:is|does|doesn)?[\"']?t?\s+(?:this|it)\s+(\w+)", "debug"),
            
            # Search patterns
            (r"search\s+(?:for\s+)?(\w+)", "search"),
            (r"find\s+(?:all\s+)?(?:instances?\s+of\s+)?(\w+)", "search"),
            
            # Edit patterns (default)
            (r"edit\s+(\w+)", "edit"),
            (r"change\s+(\w+)", "edit"),
            (r"modify\s+(\w+)", "edit"),
            (r"update\s+(\w+)", "edit"),
        ]
        
        for pattern, intent_type in patterns:
            match = re.search(pattern, message_lower)
            if match:
                files = self._extract_file_references(message)
                return Intent(
                    type=intent_type,
                    files=files,
                    matches=match.groups(),
                )
        
        # Check for file references
        files = self._extract_file_references(message)
        if files:
            return Intent(type="edit", files=files, matches=())
        
        return Intent(type="edit", files=[], matches=())
    
    def _extract_file_references(self, message: str) -> list[str]:
        """Extract file references from message.
        
        Looks for:
        - @filename patterns
        - Common file extensions
        - Explicit file mentions
        """
        files: list[str] = []
        
        # Look for @filename patterns
        at_refs = re.findall(r"@(\w+\.\w+)", message)
        files.extend(at_refs)
        
        # Look for file paths
        file_patterns = [
            r"(\w+/[\w/.]+)",  # Unix-style paths
            r"([A-Z]:\\[\w\\/.]+)",  # Windows paths
        ]
        
        for pattern in file_patterns:
            matches = re.findall(pattern, message)
            for match in matches:
                if any(ext in match for ext in [".py", ".js", ".ts", ".c", ".h", ".md"]):
                    files.append(match)
        
        return list(set(files))  # Remove duplicates
    
    def _update_context(self, intent: Intent, message: str) -> None:
        """Update composer context based on parsed intent.
        
        Args:
            intent: Parsed intent
            message: Original message
        """
        mode_map = {
            "create": ComposerMode.CREATE,
            "refactor": ComposerMode.REFACTOR,
            "explain": ComposerMode.EXPLAIN,
            "debug": ComposerMode.DEBUG,
        }
        
        self.context.mode = mode_map.get(intent.type, ComposerMode.EDIT)
        self.context.last_intent = intent.type
        
        # Update active file from intent
        if intent.files:
            self.context.active_file = intent.files[0]
    
    async def _handle_create(self, message: str, intent: Intent) -> str:
        """Handle file/function creation requests.
        
        Args:
            message: User message
            intent: Parsed intent
            
        Returns:
            Response describing the creation plan
        """
        if intent.matches:
            name = intent.matches[0]
            
            # Determine what to create based on context
            if "file" in message.lower():
                response = f"I'll create a new file for `{name}`.\n\n"
                response += "Here's the plan:\n"
                response += f"1. Create `{name}` in the appropriate location\n"
                response += "2. Add appropriate imports and structure\n"
                response += "3. Export any public interfaces\n"
                
                # If LLM available, generate the file content
                if self.llm_provider:
                    response += "\nWould you like me to generate the file content?"
            elif "class" in message.lower():
                response = f"I'll create a new class `{name}`.\n\n"
                response += "Structure:\n"
                response += f"- Class: `{name}`\n"
                response += "- `__init__` method with parameters\n"
                response += "- `__repr__` for debugging\n"
                response += "- Public methods as needed\n"
            elif "function" in message.lower():
                response = f"I'll create a new function `{name}`.\n\n"
                response += "Structure:\n"
                response += f"- Function: `{name}`\n"
                response += "- Type hints for parameters and return\n"
                response += "- Docstring with description\n"
                response += "- Implementation placeholder\n"
            else:
                response = f"I'll create `{name}` as requested.\n\n"
                response += "Please let me know what type it should be (file, class, function)."
        else:
            response = "I'll help you create something new.\n\n"
            response += "Could you specify:\n"
            response += "- What you want to create (file, class, function)\n"
            response += "- Its purpose or name\n"
            response += "- Any specific requirements"
        
        return response
    
    async def _handle_refactor(self, message: str, intent: Intent) -> str:
        """Handle refactoring requests.
        
        Args:
            message: User message
            intent: Parsed intent
            
        Returns:
            Response describing the refactoring plan
        """
        if intent.type == "rename" and len(intent.matches) >= 2:
            old_name, new_name = intent.matches[0], intent.matches[1]
            response = f"I'll rename `{old_name}` to `{new_name}`.\n\n"
            response += "Changes:\n"
            response += f"- Rename all occurrences in current file\n"
            response += f"- Update import statements if needed\n"
            response += f"- Search for cross-file references\n"
            
            intent.changes.append({
                "type": "rename",
                "old_name": old_name,
                "new_name": new_name,
            })
        elif "extract" in message.lower():
            response = "I'll extract a function from the selected code.\n\n"
            response += "Steps:\n"
            response += "1. Analyze the selected code block\n"
            response += "2. Detect variables used (parameters)\n"
            response += "3. Create new function with parameters\n"
            response += "4. Replace selection with function call\n"
        elif "inline" in message.lower():
            target = intent.matches[0] if intent.matches else "function"
            response = f"I'll inline the `{target}` function.\n\n"
            response += "Steps:\n"
            response += "1. Find all call sites\n"
            response += "2. Replace each call with function body\n"
            response += "3. Adjust for parameter passing\n"
            response += "4. Remove original function\n"
        else:
            response = "I'll help you refactor the code.\n\n"
            response += "Supported operations:\n"
            response += "- Rename symbols\n"
            response += "- Extract functions/methods\n"
            response += "- Inline functions\n"
            response += "- Move code between files\n"
        
        return response
    
    async def _handle_explain(self, message: str, intent: Intent) -> str:
        """Handle code explanation requests.
        
        Args:
            message: User message
            intent: Parsed intent
            
        Returns:
            Explanation of the code
        """
        target = intent.matches[0] if intent.matches else None
        
        if target:
            # Try to find and explain the target
            response = f"Let me explain `{target}`.\n\n"
            
            if self.context.active_file:
                try:
                    content = Path(self.context.active_file).read_text(encoding='utf-8')
                    lines = content.split('\n')
                    
                    # Find the target in the file
                    for i, line in enumerate(lines):
                        if target in line and any(kw in line for kw in ['def ', 'class ', 'import ']):
                            response += f"**Location:** {self.context.active_file}:{i+1}\n"
                            response += f"**Code:**\n```\n{line.strip()}\n```\n\n"
                            
                            # Try to get following context
                            if i + 1 < len(lines):
                                response += f"**Context:**\n```\n{lines[i+1].strip()}\n```\n"
                            break
                    else:
                        response += f"Could not find `{target}` in the current file.\n"
                        response += "Make sure you have the file open or reference it with @filename.\n"
                except Exception as e:
                    response += f"Could not read the file: {e}\n"
            else:
                response += "Please open the file or reference it with @filename.\n"
        else:
            response = "I'll explain the code for you.\n\n"
            response += "Please specify what you'd like explained:\n"
            response += "- A function name\n"
            response += "- A class\n"
            response += "- A specific code block\n"
        
        return response
    
    async def _handle_debug(self, message: str, intent: Intent) -> str:
        """Handle debugging requests.
        
        Args:
            message: User message
            intent: Parsed intent
            
        Returns:
            Debugging assistance
        """
        if intent.matches:
            target = intent.matches[0]
            response = f"I'll help debug `{target}`.\n\n"
            response += "Analysis:\n"
            response += f"1. Locate `{target}` in codebase\n"
            response += "2. Check for common issues:\n"
            response += "   - Variable scope\n"
            response += "   - Null/undefined checks\n"
            response += "   - Type mismatches\n"
            response += "   - Logic errors\n"
            response += "3. Suggest fixes\n"
        else:
            response = "I'll help you debug.\n\n"
            response += "Please tell me:\n"
            response += "- What's the specific issue?\n"
            response += "- Which function/class is affected?\n"
            response += "- Any error messages?\n"
        
        return response
    
    async def _handle_search(self, message: str, intent: Intent) -> str:
        """Handle search requests.
        
        Args:
            message: User message
            intent: Parsed intent
            
        Returns:
            Search results
        """
        query = intent.matches[0] if intent.matches else ""
        
        if not query:
            response = "I'll search the codebase.\n\n"
            response += "Please specify what to search for."
        else:
            response = f"Searching for `{query}` in the codebase.\n\n"
            
            # Perform search
            results = self._search_codebase(query)
            
            if results:
                response += f"Found {len(results)} occurrences:\n"
                for file_path, line_num, line in results[:10]:
                    response += f"- {file_path}:{line_num}: {line[:60]}...\n"
                
                if len(results) > 10:
                    response += f"\n... and {len(results) - 10} more.\n"
            else:
                response += "No matches found.\n"
        
        return response
    
    async def _handle_edit(self, message: str, intent: Intent) -> str:
        """Handle general edit requests.
        
        Args:
            message: User message
            intent: Parsed intent
            
        Returns:
            Edit plan
        """
        response = "I'll help you edit the code.\n\n"
        
        if intent.files:
            response += f"Files to edit: {', '.join(intent.files)}\n"
        
        response += "Please describe the specific changes you want:\n"
        response += "- What should be changed\n"
        response += "- Where it should be changed\n"
        response += "- Any constraints or requirements\n"
        
        return response
    
    def _search_codebase(self, query: str) -> list[tuple[str, int, str]]:
        """Search the codebase for a query.
        
        Args:
            query: Search query
            
        Returns:
            List of (file_path, line_number, line_content) tuples
        """
        results: list[tuple[str, int, str]] = []
        
        skip_dirs = {".git", "__pycache__", "node_modules", ".venv", "build", "dist", ".venv"}
        
        for ext in ["*.py", "*.js", "*.ts", "*.c", "*.h"]:
            for file_path in self.project_root.rglob(ext):
                if any(skip in file_path.parts for skip in skip_dirs):
                    continue
                
                try:
                    content = file_path.read_text(encoding='utf-8')
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        if query.lower() in line.lower():
                            results.append((str(file_path), i + 1, line.strip()))
                except Exception:
                    pass
                
                # Limit results per file
                if len(results) >= 100:
                    return results
        
        return results
    
    def get_conversation_summary(self) -> str:
        """Get a summary of the conversation so far.
        
        Returns:
            Formatted summary of messages
        """
        if not self.context.conversation_history:
            return "No conversation yet."
        
        lines = ["Conversation Summary:", "=" * 50]
        
        for msg in self.context.conversation_history[-5:]:  # Last 5 messages
            role = msg.role.upper()
            content = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            lines.append(f"\n**{role}:** {content}")
            
            if msg.files_referenced:
                lines.append(f"  Files: {', '.join(msg.files_referenced)}")
        
        return "\n".join(lines)
    
    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.context.conversation_history = []
        self.context.mode = ComposerMode.EDIT
        self.context.active_file = None
        self.context.last_intent = None
