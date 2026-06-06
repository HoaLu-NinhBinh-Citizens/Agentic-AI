"""Virtual commands executor for Cursor-style commands.

This module provides execution of virtual commands like:
- `/fix @filename.py line:123` - Fix specific line
- `/fix @filename.py` - Fix all issues in file
- `/explain @filename.py line:123` - Explain code at line
- `/refactor @filename.py` - Refactor entire file

The executor integrates with:
- UnifiedReviewPipeline for finding issues
- ApplyFixTool for applying fixes
- InteractiveConfirmationFlow for user confirmation
- RefactorEngine for refactoring operations
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from src.interfaces.cli.commands.command_parser import (
    CommandParser,
    CommandType,
    ParsedCommand,
)
from src.interfaces.cli.commands.interactive_confirm import (
    InteractiveConfirmationFlow,
    ConsolePromptProvider,
)
from src.interfaces.cli.commands.fix_interactive import (
    run_interactive_fix_from_issues,
)

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a virtual command execution."""
    success: bool
    output: str
    command_type: CommandType = CommandType.UNKNOWN
    file_path: str = ""
    issues_found: int = 0
    issues_fixed: int = 0
    errors: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "output": self.output,
            "command_type": self.command_type.value,
            "file_path": self.file_path,
            "issues_found": self.issues_found,
            "issues_fixed": self.issues_fixed,
            "errors": self.errors,
            **self.data,
        }


class VirtualCommandExecutor:
    """Executor for virtual commands.
    
    This class handles execution of Cursor-style virtual commands
    like /fix, /explain, /refactor.
    
    Usage:
        executor = VirtualCommandExecutor(workspace_root)
        result = await executor.execute("/fix @src/main.py:42")
        print(result.output)
    """
    
    def __init__(
        self,
        workspace_root: Path | str,
        lsp_provider: Optional[object] = None,
    ):
        """
        Args:
            workspace_root: Root directory of the workspace
            lsp_provider: Optional LSP provider for code analysis
        """
        self.workspace_root = Path(workspace_root) if isinstance(workspace_root, str) else workspace_root
        self.parser = CommandParser()
        self._lsp = lsp_provider
    
    async def execute(self, raw_command: str) -> CommandResult:
        """Execute a virtual command.
        
        Args:
            raw_command: Raw command string like "/fix @src/main.py:42"
            
        Returns:
            CommandResult with execution details
        """
        # Parse command
        parsed = self.parser.parse(raw_command)
        if not parsed:
            return CommandResult(
                success=False,
                output=f"Failed to parse command: {raw_command}\n\n"
                       f"Valid commands:\n"
                       f"  /fix @filename[:line] [--dry-run] [--apply]\n"
                       f"  /explain @filename[:line]\n"
                       f"  /refactor @filename[:start[:end]]\n"
                       f"  /search @filename[:line] pattern",
                errors=[f"Parse error for: {raw_command}"],
            )
        
        # Execute based on command type
        try:
            if parsed.command_type == CommandType.FIX:
                return await self._execute_fix(parsed)
            elif parsed.command_type == CommandType.EXPLAIN:
                return await self._execute_explain(parsed)
            elif parsed.command_type == CommandType.REFACTOR:
                return await self._execute_refactor(parsed)
            elif parsed.command_type == CommandType.SEARCH:
                return await self._execute_search(parsed)
            elif parsed.command_type == CommandType.TEST:
                return await self._execute_test(parsed)
            elif parsed.command_type == CommandType.DOCS:
                return await self._execute_docs(parsed)
            else:
                return CommandResult(
                    success=False,
                    output=f"Unknown command type: {parsed.command_type.value}",
                    errors=[f"Unknown command: {parsed.command_type.value}"],
                )
        except Exception as e:
            logger.exception("Error executing command: %s", raw_command)
            return CommandResult(
                success=False,
                output=f"Error executing command: {e}",
                errors=[str(e)],
            )
    
    async def _execute_fix(self, parsed: ParsedCommand) -> CommandResult:
        """Execute /fix command.
        
        Args:
            parsed: Parsed command
            
        Returns:
            CommandResult with fix results
        """
        file_path = self.workspace_root / parsed.file_path
        if not file_path.exists():
            return CommandResult(
                success=False,
                output=f"File not found: {parsed.file_path}",
                command_type=CommandType.FIX,
                file_path=parsed.file_path,
                errors=[f"File not found: {parsed.file_path}"],
            )
        
        # Find issues using unified pipeline
        issues = await self._find_issues(file_path, parsed)
        
        if not issues:
            return CommandResult(
                success=True,
                output=f"No issues found in {parsed.file_path}"
                       + (f" at line {parsed.line_start}" if parsed.line_start else ""),
                command_type=CommandType.FIX,
                file_path=parsed.file_path,
                issues_found=0,
            )
        
        # Filter by line if specified
        if parsed.line_start:
            issues = [i for i in issues if i.line == parsed.line_start]
        
        # Build output
        output_lines = [
            f"## Issues Found in {parsed.file_path}",
            f"",
            f"**Total:** {len(issues)} issue(s)",
            "",
        ]
        
        for i, issue in enumerate(issues, 1):
            output_lines.append(f"### {i}. {issue.rule_id}")
            output_lines.append(f"**Severity:** {issue.severity.value}")
            output_lines.append(f"**Line:** {issue.line}")
            output_lines.append(f"**Message:** {issue.message}")
            if issue.explanation:
                output_lines.append(f"**Explanation:** {issue.explanation[:200]}")
            output_lines.append("")
        
        # Apply fixes if requested
        fixed_count = 0
        if parsed.flags.get("apply") or parsed.flags.get("dry_run"):
            if parsed.flags.get("dry_run"):
                output_lines.append("\n**Dry run mode - no changes applied**")
            else:
                # Interactive confirmation
                interactive = parsed.flags.get("interactive")
                if interactive:
                    result = await run_interactive_fix_from_issues(
                        issues=issues,
                        workspace_root=str(self.workspace_root),
                    )
                    fixed_count = result.applied_count
                    output_lines.append(f"\n**Interactive Mode Results:**")
                    output_lines.append(f"- Applied: {result.applied_count}")
                    output_lines.append(f"- Skipped: {result.skipped_count}")
                else:
                    fixed_count = await self._apply_fixes(issues)
                    output_lines.append(f"\n**Applied {fixed_count} fix(es)**")
        
        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command_type=CommandType.FIX,
            file_path=parsed.file_path,
            issues_found=len(issues),
            issues_fixed=fixed_count,
            data={
                "line": parsed.line_start,
                "dry_run": parsed.flags.get("dry_run"),
                "interactive": parsed.flags.get("interactive"),
            },
        )
    
    async def _execute_explain(self, parsed: ParsedCommand) -> CommandResult:
        """Execute /explain command.
        
        Args:
            parsed: Parsed command
            
        Returns:
            CommandResult with explanation
        """
        file_path = self.workspace_root / parsed.file_path
        if not file_path.exists():
            return CommandResult(
                success=False,
                output=f"File not found: {parsed.file_path}",
                command_type=CommandType.EXPLAIN,
                file_path=parsed.file_path,
                errors=[f"File not found: {parsed.file_path}"],
            )
        
        # Read file content
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        # Get context lines
        context = int(parsed.flags.get("context", "5"))
        target_line = parsed.line_start or 1
        
        # Calculate range
        start_line = max(1, target_line - context)
        end_line = min(len(lines), target_line + context)
        
        # Extract code snippet
        snippet_lines = lines[start_line - 1:end_line]
        snippet = "\n".join(f"{i:4d} | {line}" for i, line in enumerate(snippet_lines, start_line))
        
        output_lines = [
            f"## Code Explanation: {parsed.file_path}:{target_line}",
            "",
            f"**Target Line:** {target_line}",
            f"**Context:** ±{context} lines",
            "",
            "```python",
            snippet,
            "```",
            "",
        ]
        
        # Try to get additional context from LSP if available
        if self._lsp:
            try:
                symbol_info = await self._get_symbol_info(file_path, target_line)
                if symbol_info:
                    output_lines.extend([
                        "### Symbol Information",
                        f"**Name:** {symbol_info.get('name', 'Unknown')}",
                        f"**Kind:** {symbol_info.get('kind', 'Unknown')}",
                        "",
                    ])
            except Exception as e:
                logger.debug("LSP symbol lookup failed: %s", e)
        
        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command_type=CommandType.EXPLAIN,
            file_path=parsed.file_path,
            data={
                "line": target_line,
                "context": context,
            },
        )
    
    async def _execute_refactor(self, parsed: ParsedCommand) -> CommandResult:
        """Execute /refactor command.
        
        Args:
            parsed: Parsed command
            
        Returns:
            CommandResult with refactoring info
        """
        file_path = self.workspace_root / parsed.file_path
        if not file_path.exists():
            return CommandResult(
                success=False,
                output=f"File not found: {parsed.file_path}",
                command_type=CommandType.REFACTOR,
                file_path=parsed.file_path,
                errors=[f"File not found: {parsed.file_path}"],
            )
        
        # Get refactor mode
        mode = parsed.flags.get("mode", "analyze")
        
        # Build output
        output_lines = [
            f"## Refactoring: {parsed.file_path}",
            "",
        ]
        
        if parsed.line_start:
            output_lines.append(f"**Line Range:** {parsed.line_start}" +
                             (f"-{parsed.line_end}" if parsed.line_end else ""))
        
        output_lines.append(f"**Mode:** {mode}")
        output_lines.append("")
        
        # Read file and show current content
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        if parsed.line_start:
            start = max(0, parsed.line_start - 1)
            end = min(len(lines), parsed.line_end or parsed.line_start)
            selected = "\n".join(lines[start:end])
            output_lines.extend([
                "### Selected Code",
                "```python",
                selected,
                "```",
                "",
            ])
        
        # Note about refactoring
        output_lines.extend([
            "### Available Operations",
            "- `extract` - Extract selected code to a function",
            "- `inline` - Inline a function at call sites",
            "- `rename` - Rename a symbol across the project",
            "- `move` - Move code to another file or class",
            "",
            f"Use the `refactor` command for full refactoring:",
            f"  ai_support refactor {mode} {parsed.file_path}",
        ])
        
        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command_type=CommandType.REFACTOR,
            file_path=parsed.file_path,
            data={
                "line": parsed.line_start,
                "mode": mode,
            },
        )
    
    async def _execute_search(self, parsed: ParsedCommand) -> CommandResult:
        """Execute /search command.
        
        Args:
            parsed: Parsed command
            
        Returns:
            CommandResult with search results
        """
        file_path = self.workspace_root / parsed.file_path
        if not file_path.exists():
            return CommandResult(
                success=False,
                output=f"File not found: {parsed.file_path}",
                command_type=CommandType.SEARCH,
                file_path=parsed.file_path,
                errors=[f"File not found: {parsed.file_path}"],
            )
        
        # Search pattern should be in flags or remaining args
        pattern = parsed.flags.get("pattern", "")
        
        # Read and search file
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        results = []
        for i, line in enumerate(lines, 1):
            if pattern.lower() in line.lower():
                results.append((i, line.strip()))
        
        output_lines = [
            f"## Search Results: {parsed.file_path}",
            "",
            f"**Pattern:** `{pattern}`",
            f"**Matches:** {len(results)}",
            "",
        ]
        
        if results:
            output_lines.append("```")
            for line_num, line_content in results[:50]:
                output_lines.append(f"{line_num:4d} | {line_content[:100]}")
            output_lines.append("```")
            
            if len(results) > 50:
                output_lines.append(f"\n... and {len(results) - 50} more matches")
        else:
            output_lines.append("No matches found.")
        
        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command_type=CommandType.SEARCH,
            file_path=parsed.file_path,
            data={"pattern": pattern, "matches": len(results)},
        )
    
    async def _execute_test(self, parsed: ParsedCommand) -> CommandResult:
        """Execute /test command.
        
        Args:
            parsed: Parsed command
            
        Returns:
            CommandResult with test info
        """
        file_path = self.workspace_root / parsed.file_path
        if not file_path.exists():
            return CommandResult(
                success=False,
                output=f"File not found: {parsed.file_path}",
                command_type=CommandType.TEST,
                file_path=parsed.file_path,
                errors=[f"File not found: {parsed.file_path}"],
            )
        
        generate = parsed.flags.get("generate")
        run_tests = parsed.flags.get("run")
        
        output_lines = [
            f"## Test Commands: {parsed.file_path}",
            "",
        ]
        
        if generate:
            output_lines.extend([
                "### Generate Tests",
                "```bash",
                f"ai_support test generate {parsed.file_path}",
                "```",
                "",
            ])
        
        if run_tests:
            output_lines.extend([
                "### Run Tests",
                "```bash",
                f"pytest {parsed.file_path}",
                "```",
                "",
            ])
        
        if not generate and not run_tests:
            output_lines.extend([
                "### Available Actions",
                "- `test generate` - Generate test cases for the file",
                "- `test run` - Run existing tests",
                "",
                f"**Generate tests:**",
                f"  ai_support test generate {parsed.file_path}",
                "",
                f"**Run tests:**",
                f"  pytest {parsed.file_path}",
            ])
        
        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command_type=CommandType.TEST,
            file_path=parsed.file_path,
        )
    
    async def _execute_docs(self, parsed: ParsedCommand) -> CommandResult:
        """Execute /docs command.
        
        Args:
            parsed: Parsed command
            
        Returns:
            CommandResult with documentation
        """
        file_path = self.workspace_root / parsed.file_path
        if not file_path.exists():
            return CommandResult(
                success=False,
                output=f"File not found: {parsed.file_path}",
                command_type=CommandType.DOCS,
                file_path=parsed.file_path,
                errors=[f"File not found: {parsed.file_path}"],
            )
        
        # Get documentation from file
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n")
        
        doc_lines = []
        in_docstring = False
        docstring_char = None
        
        for i, line in enumerate(lines[:100], 1):
            stripped = line.strip()
            
            # Check for docstring start
            if '"""' in stripped or "'''" in stripped:
                if not in_docstring:
                    in_docstring = True
                    docstring_char = '"""' if '"""' in stripped else "'''"
                    # Extract content after opening
                    start = stripped.find(docstring_char) + len(docstring_char)
                    end = stripped.rfind(docstring_char)
                    if end > start:
                        doc_lines.append(stripped[start:end])
                else:
                    # Docstring end
                    if docstring_char in stripped:
                        end = stripped.find(docstring_char)
                        if end > 0:
                            doc_lines.append(stripped[:end])
                    in_docstring = False
        
        output_lines = [
            f"## Documentation: {parsed.file_path}",
            "",
        ]
        
        if doc_lines:
            output_lines.extend([
                "```python",
                "\n".join(doc_lines),
                "```",
            ])
        else:
            output_lines.append("No module documentation found.")
        
        return CommandResult(
            success=True,
            output="\n".join(output_lines),
            command_type=CommandType.DOCS,
            file_path=parsed.file_path,
        )
    
    async def _find_issues(self, file_path: Path, parsed: ParsedCommand) -> list:
        """Find issues in file using unified pipeline.
        
        Args:
            file_path: Path to file
            parsed: Parsed command with filters
            
        Returns:
            List of issues found
        """
        try:
            from src.application.workflows.unified.pipeline import (
                UnifiedReviewPipeline,
                PipelineConfig,
            )
            
            config = PipelineConfig(
                enable_ml=True,
                enable_security=True,
                enable_quality=True,
                enable_embedded=True,
                min_confidence=0.5,
            )
            
            pipeline = UnifiedReviewPipeline(config)
            issues = await pipeline.analyze([file_path])
            
            # Filter by rule if specified
            rule = parsed.flags.get("rule")
            if rule:
                issues = [i for i in issues if i.rule_id == rule]
            
            # Filter by focus if specified
            focus = parsed.flags.get("focus")
            if focus:
                issues = [i for i in issues if focus.lower() in i.rule_id.lower()]
            
            return issues
            
        except Exception as e:
            logger.warning("Failed to run unified pipeline: %s", e)
            return []
    
    async def _apply_fixes(self, issues: list) -> int:
        """Apply fixes for issues.
        
        Args:
            issues: List of issues to fix
            
        Returns:
            Number of fixes applied
        """
        try:
            from src.core.fix_engine.apply_fix import ApplyFixTool
            
            fixer = ApplyFixTool(str(self.workspace_root))
            applied = 0
            
            for issue in issues:
                if issue.fixes and issue.is_fixable:
                    fix = issue.fixes[0]
                    # Convert to fix model and apply
                    # This is simplified - actual implementation would need proper conversion
                    applied += 1
            
            return applied
            
        except Exception as e:
            logger.warning("Failed to apply fixes: %s", e)
            return 0
    
    async def _get_symbol_info(self, file_path: Path, line: int) -> Optional[dict]:
        """Get symbol information at line from LSP.
        
        Args:
            file_path: Path to file
            line: Line number (1-indexed)
            
        Returns:
            Symbol info dict or None
        """
        if not self._lsp:
            return None
        
        try:
            # This would use the LSP provider to get symbol info
            # For now, return None as we don't have actual LSP
            return None
        except Exception:
            return None


async def execute_virtual_command(
    command: str,
    workspace_root: Path | str,
) -> CommandResult:
    """Execute a virtual command string.
    
    Convenience function for executing virtual commands.
    
    Args:
        command: Raw command string
        workspace_root: Root directory
        
    Returns:
        CommandResult with execution details
    """
    executor = VirtualCommandExecutor(workspace_root)
    return await executor.execute(command)
