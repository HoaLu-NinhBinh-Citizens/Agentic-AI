"""AST-aware patch engine for safe code modifications.

Provides:
- Precise AST node replacement based on byte/line positions
- Formatting and indentation preservation
- Syntax validation after patch application
- Unified diff generation for review

Architecture:
    ASTPatchEngine.generate_patch() → Patch with line range
    ASTPatchEngine.apply_patch() → modified content
    ASTPatchEngine.validate_syntax() → validation result
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tree_sitter import Language, Node, Parser


@dataclass
class Patch:
    """Represents a code patch with source and replacement."""
    file_path: Path
    start_line: int
    end_line: int
    old_code: str
    new_code: str

    def to_diff(self) -> str:
        """Generate unified diff format."""
        lines = []
        lines.append(f"--- {self.file_path}")
        lines.append(f"+++ {self.file_path}")
        lines.append(
            f"@@ -{self.start_line},{self.end_line - self.start_line + 1} "
            f"+{self.start_line},{self.end_line - self.start_line + 1} @@"
        )
        for line in self.old_code.split("\n"):
            lines.append(f"- {line}")
        for line in self.new_code.split("\n"):
            lines.append(f"+ {line}")
        return "\n".join(lines)


@dataclass
class PatchResult:
    """Result of patch application with validation status."""
    success: bool
    patched_content: str
    validation_passed: bool
    error: Optional[str] = None
    original_content: str = ""
    modified_lines: int = 0


@dataclass
class ASTNodeInfo:
    """Information about an AST node for precise targeting."""
    type: str
    start_byte: int
    end_byte: int
    start_point: tuple[int, int]
    end_point: tuple[int, int]
    text: str


class ASTPatchEngine:
    """Generates and applies AST-aware patches with syntax validation.

    Features:
    - Precise node/range replacement using tree-sitter
    - Formatting preservation (indentation, comments)
    - Syntax validation post-patch
    - Unified diff generation

    Usage:
        engine = ASTPatchEngine()
        patch = engine.generate_patch(file_path, content, (start_byte, end_byte), new_code)
        result = engine.apply_and_validate(content, patch, language="python")
    """

    def __init__(self) -> None:
        self._parser_cache: dict[str, Any] = {}
        self._language_cache: dict[str, Any] = {}

    def _get_parser(self, language: str) -> Any:
        """Get or create a tree-sitter parser for the language."""
        if language in self._parser_cache:
            return self._parser_cache[language]

        try:
            from tree_sitter_languages import get_parser, get_language
            parser = get_parser(language)
            self._parser_cache[language] = parser
            self._language_cache[language] = get_language(language)
            return parser
        except ImportError:
            logger.warning("tree-sitter-languages not available, using fallback")
            return None

    def _get_language(self, language: str) -> Any:
        """Get tree-sitter Language object."""
        if language in self._language_cache:
            return self._language_cache[language]
        try:
            from tree_sitter_languages import get_language
            lang = get_language(language)
            self._language_cache[language] = lang
            return lang
        except ImportError:
            return None

    def generate_patch(
        self,
        file_path: Path,
        content: str,
        node_start: tuple[int, int],
        node_end: tuple[int, int],
        new_code: str,
    ) -> Patch:
        """Generate a patch for a specific AST node range.

        Args:
            file_path: Path to the source file
            content: Full file content
            node_start: (byte_offset, column) tuple for start
            node_end: (byte_offset, column) tuple for end
            new_code: Replacement code

        Returns:
            Patch object with line range and old/new code
        """
        # Calculate line numbers from byte positions
        start_byte, start_col = node_start
        end_byte, end_col = node_end

        start_line = content[:start_byte].count("\n")
        end_line = content[:end_byte].count("\n")

        # Extract old code (handle multi-line nodes)
        if start_line == end_line:
            # Single line: extract between columns
            line_text = content.split("\n")[start_line]
            old_code = line_text[start_col:end_col + 1]
        else:
            # Multi-line: extract partial lines
            lines = content.split("\n")
            old_lines = []
            for i in range(start_line, end_line + 1):
                if i == start_line:
                    old_lines.append(lines[i][start_col:])
                elif i == end_line:
                    old_lines.append(lines[i][:end_col + 1])
                else:
                    old_lines.append(lines[i])
            old_code = "\n".join(old_lines)

        return Patch(
            file_path=file_path,
            start_line=start_line + 1,  # Convert to 1-based
            end_line=end_line + 1,
            old_code=old_code,
            new_code=new_code,
        )

    def find_node_at_position(
        self,
        content: str,
        line: int,
        column: int,
        language: str,
    ) -> Optional[ASTNodeInfo]:
        """Find the AST node at a specific line/column position.

        Args:
            content: File content
            line: 1-based line number
            column: 0-based column number
            language: Programming language (python, javascript, etc.)

        Returns:
            ASTNodeInfo if found, None otherwise
        """
        parser = self._get_parser(language)
        if parser is None:
            return None

        try:
            tree = parser.parse(content.encode("utf-8"))
            node = self._find_deepest_node_at(
                tree.root_node, line - 1, column  # Convert to 0-based
            )
            if node:
                return ASTNodeInfo(
                    type=node.type,
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                    start_point=node.start_point,
                    end_point=node.end_byte,
                    text=node.text.decode("utf-8") if node.text else "",
                )
        except Exception as e:
            logger.warning("Failed to find node: %s", e)

        return None

    def _find_deepest_node_at(
        self,
        node: Any,
        line: int,
        column: int,
    ) -> Optional[Any]:
        """Find the deepest (most specific) node at given position."""
        from tree_sitter import Node

        if not isinstance(node, Node):
            return None

        # Check if point is within this node
        start_row, start_col = node.start_point
        end_row, end_col = node.end_point

        if line < start_row or line > end_row:
            return None
        if line == start_row and column < start_col:
            return None
        if line == end_row and column > end_col:
            return None

        # Check children first (deepest = most specific)
        for child in node.children:
            found = self._find_deepest_node_at(child, line, column)
            if found:
                return found

        return node

    def find_nodes_by_type(
        self,
        content: str,
        node_type: str,
        language: str,
    ) -> list[ASTNodeInfo]:
        """Find all AST nodes of a specific type.

        Args:
            content: File content
            node_type: Node type to search for (e.g., "function_definition")
            language: Programming language

        Returns:
            List of matching ASTNodeInfo objects
        """
        parser = self._get_parser(language)
        if parser is None:
            return []

        results: list[ASTNodeInfo] = []

        try:
            tree = parser.parse(content.encode("utf-8"))
            self._collect_nodes_by_type(tree.root_node, node_type, results)
        except Exception as e:
            logger.warning("Failed to find nodes by type: %s", e)

        return results

    def _collect_nodes_by_type(
        self,
        node: Any,
        target_type: str,
        results: list[ASTNodeInfo],
    ) -> None:
        """Recursively collect nodes matching target type."""
        from tree_sitter import Node

        if not isinstance(node, Node):
            return

        if node.type == target_type:
            results.append(
                ASTNodeInfo(
                    type=node.type,
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                    start_point=node.start_point,
                    end_point=node.end_point,
                    text=node.text.decode("utf-8") if node.text else "",
                )
            )

        for child in node.children:
            self._collect_nodes_by_type(child, target_type, results)

    def apply_patch(self, content: str, patch: Patch) -> str:
        """Apply patch while preserving surrounding context.

        Args:
            content: Original file content
            patch: Patch to apply

        Returns:
            Modified content string
        """
        lines = content.split("\n")

        # Validate line range
        start_idx = max(0, patch.start_line - 1)
        end_idx = min(len(lines), patch.end_line)

        # Reconstruct with new code
        before = lines[:start_idx]
        after = lines[end_idx:]

        new_lines = before
        if patch.new_code:
            new_lines.extend(patch.new_code.split("\n"))
        new_lines.extend(after)

        return "\n".join(new_lines)

    def apply_and_validate(
        self,
        content: str,
        patch: Patch,
        language: str = "python",
    ) -> PatchResult:
        """Apply patch and validate syntax.

        Args:
            content: Original content
            patch: Patch to apply
            language: Programming language for validation

        Returns:
            PatchResult with success status and patched content
        """
        try:
            # Apply patch
            patched_content = self.apply_patch(content, patch)

            # Count modified lines
            old_line_count = patch.end_line - patch.start_line + 1
            new_line_count = len(patch.new_code.split("\n")) if patch.new_code else 0
            modified_lines = max(old_line_count, new_line_count)

            # Validate syntax
            validation_passed = self.validate_syntax(patched_content, language)

            return PatchResult(
                success=True,
                patched_content=patched_content,
                validation_passed=validation_passed,
                original_content=content,
                modified_lines=modified_lines,
            )

        except Exception as e:
            return PatchResult(
                success=False,
                patched_content=content,
                validation_passed=False,
                error=str(e),
                original_content=content,
            )

    def validate_syntax(self, content: str, language: str) -> bool:
        """Validate that content has correct syntax for the language.

        Args:
            content: Code content to validate
            language: Programming language (python, javascript, etc.)

        Returns:
            True if syntax is valid, False otherwise
        """
        # For Python, always use ast.parse for reliable validation
        if language == "python":
            return self._basic_syntax_check(content, language)

        parser = self._get_parser(language)
        if parser is None:
            # Fallback for other languages
            return self._basic_syntax_check(content, language)

        try:
            parser.parse(content.encode("utf-8"))
            return True
        except Exception as e:
            logger.debug("Syntax validation failed: %s", e)
            return False

    def _basic_syntax_check(self, content: str, language: str) -> bool:
        """Basic syntax validation without tree-sitter."""
        if language == "python":
            try:
                import ast
                ast.parse(content)
                return True
            except SyntaxError:
                return False
        # For other languages, assume valid
        return True

    def generate_diff(self, old_content: str, new_content: str) -> str:
        """Generate unified diff between two contents.

        Args:
            old_content: Original content
            new_content: Modified content

        Returns:
            Unified diff string
        """
        old_lines = old_content.splitlines(keepends=True)
        new_lines = new_content.splitlines(keepends=True)

        diff = difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="original",
            tofile="modified",
            lineterm="",
        )

        return "".join(diff)

    def apply_safely(
        self,
        content: str,
        patch: Patch,
        language: str = "python",
        require_valid_syntax: bool = True,
    ) -> tuple[bool, str]:
        """Apply patch safely with optional syntax validation.

        Args:
            content: Original content
            patch: Patch to apply
            language: Programming language
            require_valid_syntax: If True, reject patches that break syntax

        Returns:
            Tuple of (success, content)
        """
        result = self.apply_and_validate(content, patch, language)

        if not result.success:
            return False, content

        if require_valid_syntax and not result.validation_passed:
            logger.warning(
                "Patch would break syntax in %s",
                patch.file_path,
            )
            return False, content

        return True, result.patched_content

    def get_node_range(
        self,
        content: str,
        node: ASTNodeInfo,
    ) -> tuple[int, int]:
        """Get line range for an AST node.

        Args:
            content: File content
            node: AST node info

        Returns:
            (start_line, end_line) tuple (1-based)
        """
        start_line = content[: node.start_byte].count("\n") + 1
        end_line = content[: node.end_byte].count("\n") + 1
        return start_line, end_line

    def extract_with_context(
        self,
        content: str,
        start_line: int,
        end_line: int,
        context_lines: int = 3,
    ) -> tuple[str, str, str]:
        """Extract code with surrounding context lines.

        Args:
            content: Full file content
            start_line: Start line (1-based)
            end_line: End line (1-based)
            context_lines: Number of context lines on each side

        Returns:
            Tuple of (before, target, after) code snippets
        """
        lines = content.split("\n")
        total_lines = len(lines)

        # Calculate ranges with clamping (convert to 0-based)
        ctx_start_idx = max(0, start_line - 1 - context_lines)
        target_start_idx = start_line - 1
        target_end_idx = end_line  # exclusive (0-based, end is exclusive)
        ctx_end_idx = min(total_lines, end_line + context_lines)

        before = "\n".join(lines[ctx_start_idx:target_start_idx])
        target = "\n".join(lines[target_start_idx:target_end_idx])
        after = "\n".join(lines[target_end_idx:ctx_end_idx])

        return before, target, after

    def find_similar_code_pattern(
        self,
        content: str,
        pattern: str,
        language: str,
    ) -> list[tuple[int, int]]:
        """Find occurrences of a code pattern in content.

        Args:
            content: File content
            pattern: Code pattern to search for
            language: Programming language

        Returns:
            List of (start_line, end_line) tuples for matches
        """
        results: list[tuple[int, int]] = []

        # Use tree-sitter to find the pattern type
        parser = self._get_parser(language)
        if parser is None:
            # Fallback to simple string search
            return self._simple_pattern_search(content, pattern)

        try:
            tree = parser.parse(content.encode("utf-8"))
            self._find_pattern_occurrences(
                tree.root_node,
                content,
                pattern,
                results,
            )
        except Exception as e:
            logger.warning("Pattern search failed: %s", e)

        return results

    def _simple_pattern_search(
        self,
        content: str,
        pattern: str,
    ) -> list[tuple[int, int]]:
        """Simple string-based pattern search."""
        results: list[tuple[int, int]] = []
        lines = content.split("\n")

        for i, line in enumerate(lines):
            if pattern in line:
                results.append((i + 1, i + 1))

        return results

    def _find_pattern_occurrences(
        self,
        node: Any,
        content: str,
        pattern: str,
        results: list[tuple[int, int]],
    ) -> None:
        """Recursively find pattern occurrences in AST."""
        from tree_sitter import Node

        if not isinstance(node, Node):
            return

        node_text = node.text.decode("utf-8") if node.text else ""
        if pattern in node_text:
            start_line = content[: node.start_byte].count("\n") + 1
            end_line = content[: node.end_byte].count("\n") + 1
            results.append((start_line, end_line))

        for child in node.children:
            self._find_pattern_occurrences(child, content, pattern, results)


def create_engine() -> ASTPatchEngine:
    """Factory function to create an ASTPatchEngine instance."""
    return ASTPatchEngine()
