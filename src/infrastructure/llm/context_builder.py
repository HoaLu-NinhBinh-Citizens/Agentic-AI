"""Build rich context for LLM prompts.

Maximizes LLM understanding with minimal tokens through:
- Context compression
- Relevance filtering
- Code structure extraction
- Call chain analysis
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import re


@dataclass
class LLMContext:
    """Rich context for LLM prompts."""
    code_snippet: str
    language: str
    file_path: Optional[str] = None
    function_name: Optional[str] = None
    class_name: Optional[str] = None
    imports: list[str] = field(default_factory=list)
    type_hints: dict[str, str] = field(default_factory=dict)
    docstring: str = ""
    line_number: int = 0
    call_chain: list[str] = field(default_factory=list)
    related_files: list[str] = field(default_factory=list)
    return_type: Optional[str] = None
    parameters: dict[str, str] = field(default_factory=dict)


class ContextBuilder:
    """Build optimized context for LLM analysis.

    Implements context compression and relevance filtering to maximize
    LLM understanding while minimizing token usage.
    """

    def __init__(self, max_tokens: int = 8000):
        """Initialize context builder.

        Args:
            max_tokens: Maximum tokens for context compression
        """
        self.max_tokens = max_tokens

    def build_for_analysis(
        self,
        file_path: Path,
        content: str,
        line_number: int,
        language: str
    ) -> LLMContext:
        """Build context for code analysis.

        Args:
            file_path: Path to the file being analyzed
            content: Full file content
            line_number: Line number of interest (1-indexed)
            language: Programming language

        Returns:
            LLMContext with extracted code structure
        """
        function_name = self._get_enclosing_function(content, line_number)
        class_name = self._get_enclosing_class(content, line_number)
        snippet = self._extract_relevant_snippet(content, line_number)
        imports = self._parse_imports(content)
        type_hints = self._parse_type_hints(content)
        docstring = self._get_docstring(content, line_number)

        parameters = self._get_function_parameters(content, line_number)
        return_type = self._get_return_type(content, line_number)

        return LLMContext(
            code_snippet=snippet,
            language=language,
            file_path=str(file_path),
            function_name=function_name,
            class_name=class_name,
            imports=imports,
            type_hints=type_hints,
            docstring=docstring,
            line_number=line_number,
            parameters=parameters,
            return_type=return_type
        )

    def build_for_fix(
        self,
        file_path: Path,
        content: str,
        issue_line: int,
        language: str,
        issue_type: str
    ) -> LLMContext:
        """Build context for fix generation.

        Args:
            file_path: Path to the file
            content: Full file content
            issue_line: Line with the issue (1-indexed)
            language: Programming language
            issue_type: Type of issue (security, ml, quality, etc.)

        Returns:
            LLMContext enriched with fix-relevant context
        """
        context = self.build_for_analysis(file_path, content, issue_line, language)
        context.call_chain = self._get_call_chain(content, issue_line)
        context.related_files = self._get_related_files(content, context.imports)
        return context

    def compress_context(
        self,
        context: LLMContext,
        max_tokens: Optional[int] = None
    ) -> LLMContext:
        """Compress context to fit token limit.

        Args:
            context: Context to compress
            max_tokens: Optional override for max tokens

        Returns:
            Compressed LLMContext
        """
        limit = max_tokens or self.max_tokens

        current_tokens = self._estimate_tokens(context)
        if current_tokens <= limit:
            return context

        compressed = LLMContext(
            code_snippet=context.code_snippet,
            language=context.language,
            file_path=context.file_path,
            function_name=context.function_name,
            class_name=context.class_name,
            imports=context.imports[:10],
            type_hints=context.type_hints,
            docstring=context.docstring[:500] if context.docstring else "",
            line_number=context.line_number,
            call_chain=context.call_chain[:5],
            related_files=context.related_files[:3],
            return_type=context.return_type,
            parameters={k: v for i, (k, v) in enumerate(context.parameters.items()) if i < 5}
        )

        current_tokens = self._estimate_tokens(compressed)
        if current_tokens <= limit:
            return compressed

        lines = context.code_snippet.split("\n")
        max_lines = (limit * 4) // 60
        compressed.code_snippet = "\n".join(self._select_important_lines(
            lines, context.line_number, max_lines
        ))

        return compressed

    def _estimate_tokens(self, context: LLMContext) -> int:
        """Estimate token count for context."""
        tokens = len(context.code_snippet) // 4
        tokens += len(context.call_chain) * 10
        tokens += len(context.docstring) // 4
        tokens += len(context.imports) * 5
        return tokens

    def _select_important_lines(
        self,
        lines: list[str],
        focus_line: int,
        max_lines: int
    ) -> list[str]:
        """Select most important lines within limit."""
        if len(lines) <= max_lines:
            return lines

        important = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            if "def " in stripped or "class " in stripped:
                important.append(line)
            elif "return" in stripped and i != focus_line - 1:
                important.append(line)
            elif abs(i + 1 - focus_line) <= 3:
                important.append(line)

        important_lines = set()
        for line in important:
            for i, l in enumerate(lines):
                if l == line:
                    important_lines.add(i)
                    for j in range(max(0, i - 1), min(len(lines), i + 2)):
                        important_lines.add(j)

        sorted_lines = sorted(important_lines)
        start = max(0, min(sorted_lines))
        end = min(len(lines), max(sorted_lines) + 1)

        selected = lines[start:end]
        if len(selected) > max_lines:
            selected = selected[:max_lines]

        return selected

    def _extract_relevant_snippet(
        self,
        content: str,
        line_number: int,
        radius: int = 20
    ) -> str:
        """Extract relevant code snippet around line.

        Args:
            content: Full file content
            line_number: Center line (1-indexed)
            radius: Lines before/after to include

        Returns:
            Code snippet with line markers
        """
        lines = content.split("\n")
        start = max(0, line_number - radius - 1)
        end = min(len(lines), line_number + radius)

        snippet_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == line_number - 1 else "    "
            snippet_lines.append(f"{prefix}{lines[i]}")

        return "\n".join(snippet_lines)

    def _get_enclosing_function(self, content: str, line: int) -> Optional[str]:
        """Get the function containing the line.

        Args:
            content: Full file content
            line: Line number (1-indexed)

        Returns:
            Function name or None
        """
        lines = content.split("\n")

        for i in range(line - 1, -1, -1):
            if match := re.match(r"^\s*(?:async\s+)?def\s+(\w+)", lines[i]):
                return match.group(1)
            if match := re.match(r"^\s*(\w+)\s*=\s*(?:async\s+)?def\s+(\w+)", lines[i]):
                return match.group(2)

        return None

    def _get_enclosing_class(self, content: str, line: int) -> Optional[str]:
        """Get the class containing the line.

        Args:
            content: Full file content
            line: Line number (1-indexed)

        Returns:
            Class name or None
        """
        lines = content.split("\n")

        for i in range(line - 1, -1, -1):
            if match := re.match(r"^\s*class\s+(\w+)", lines[i]):
                return match.group(1)

        return None

    def _parse_imports(self, content: str) -> list[str]:
        """Parse import statements.

        Args:
            content: Full file content

        Returns:
            List of import statements
        """
        imports = []

        import_patterns = [
            r"^(?:from\s+[\w.]+\s+)?import\s+.+",
            r"^(?:from\s+[\w.]+\s+)?import\s+\{[^}]+\}",
        ]

        for pattern in import_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                imp = match.group(0).strip()
                if imp and imp not in imports:
                    imports.append(imp)

        return imports[:20]

    def _parse_type_hints(self, content: str) -> dict[str, str]:
        """Parse type hints from function signatures.

        Args:
            content: Full file content

        Returns:
            Dictionary of parameter names to types
        """
        type_hints: dict[str, str] = {}

        for match in re.finditer(
            r"(?:def|async\s+def)\s+\w+\s*\(([^)]*)\)\s*(?:->\s*(\w+))?",
            content
        ):
            params_str = match.group(1) or ""
            return_type = match.group(2)

            for param_match in re.finditer(r"(\w+)\s*:\s*([^,=]+)", params_str):
                param_name = param_match.group(1)
                param_type = param_match.group(2).strip()
                type_hints[param_name] = param_type

            if return_type:
                type_hints["return"] = return_type

        return type_hints

    def _get_function_parameters(
        self,
        content: str,
        line: int
    ) -> dict[str, str]:
        """Get parameters for function at line.

        Args:
            content: Full file content
            line: Line number (1-indexed)

        Returns:
            Dictionary of parameter names to types
        """
        type_hints = self._parse_type_hints(content)
        params: dict[str, str] = {}

        for i in range(line - 1, -1, -1):
            if match := re.match(
                r"(?:def|async\s+def)\s+\w+\s*\(([^)]*)\)",
                content.split("\n")[i]
            ):
                params_str = match.group(1)
                for param_match in re.finditer(r"(\w+)(?:\s*:\s*([^,=]+))?", params_str):
                    param_name = param_match.group(1)
                    param_type = param_match.group(2)
                    if param_name != "self" and param_name != "cls":
                        params[param_name] = (param_type.strip() if param_type
                                              else type_hints.get(param_name, "Any"))
                break

        return params

    def _get_return_type(self, content: str, line: int) -> Optional[str]:
        """Get return type for function at line.

        Args:
            content: Full file content
            line: Line number (1-indexed)

        Returns:
            Return type or None
        """
        type_hints = self._parse_type_hints(content)
        return type_hints.get("return")

    def _get_docstring(self, content: str, line: int) -> str:
        """Get docstring for function/class.

        Args:
            content: Full file content
            line: Line number (1-indexed)

        Returns:
            Docstring content or empty string
        """
        lines = content.split("\n")

        for i in range(line - 1, min(line + 5, len(lines))):
            line_content = lines[i]

            for quote in ['"""', "'''"]:
                if quote in line_content:
                    start = line_content.find(quote) + len(quote)
                    end = line_content.rfind(quote)

                    if start < end:
                        return line_content[start:end].strip()

                    rest_lines = "\n".join(lines[i + 1:])
                    end_idx = rest_lines.find(quote)
                    if end_idx != -1:
                        return (line_content[start:] + "\n" +
                                rest_lines[:end_idx]).strip()

        return ""

    def _get_call_chain(self, content: str, line: int) -> list[str]:
        """Get the call chain leading to this line.

        Args:
            content: Full file content
            line: Line number (1-indexed)

        Returns:
            List of function calls in chain
        """
        calls = []
        lines = content.split("\n")

        for i in range(line - 1, -1, -1):
            if match := re.search(r"(\w+)\s*\(", lines[i]):
                func_name = match.group(1)
                if func_name not in ("def", "class", "return", "if", "for", "while",
                                     "try", "except", "with"):
                    calls.append(func_name)

            if re.match(r"^\s*(?:def|class|async)", lines[i]):
                break

        return calls[:10]

    def _get_related_files(
        self,
        content: str,
        imports: list[str]
    ) -> list[str]:
        """Get related files from imports.

        Args:
            content: Full file content
            imports: List of import statements

        Returns:
            List of related module names
        """
        related = []

        for imp in imports:
            if "import" in imp:
                parts = imp.replace("import", "").strip().split()
                if parts:
                    module = parts[0].split(".")[-1]
                    if module and module not in related:
                        related.append(module)

        return related[:5]

    def build_file_context(
        self,
        file_path: Path,
        content: str,
        language: str
    ) -> LLMContext:
        """Build context for entire file analysis.

        Args:
            file_path: Path to the file
            content: Full file content
            language: Programming language

        Returns:
            LLMContext for full file
        """
        imports = self._parse_imports(content)
        type_hints = self._parse_type_hints(content)
        functions = self._extract_all_functions(content)
        classes = self._extract_all_classes(content)

        return LLMContext(
            code_snippet=content[:2000],
            language=language,
            file_path=str(file_path),
            imports=imports,
            type_hints=type_hints,
            call_chain=functions[:10],
            related_files=classes
        )

    def _extract_all_functions(self, content: str) -> list[str]:
        """Extract all function names from content.

        Args:
            content: Full file content

        Returns:
            List of function names
        """
        functions = []
        for match in re.finditer(r"(?:^|\n)(?:async\s+)?def\s+(\w+)", content):
            functions.append(match.group(1))
        return functions

    def _extract_all_classes(self, content: str) -> list[str]:
        """Extract all class names from content.

        Args:
            content: Full file content

        Returns:
            List of class names
        """
        classes = []
        for match in re.finditer(r"(?:^|\n)class\s+(\w+)", content):
            classes.append(match.group(1))
        return classes
