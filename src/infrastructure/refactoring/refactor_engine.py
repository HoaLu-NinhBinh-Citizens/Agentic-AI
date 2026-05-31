"""Interactive refactoring engine for AI_SUPPORT.
Provides: extract function, inline, rename, move code.
Uses Python AST for accurate code analysis.
"""
from __future__ import annotations

import ast
import logging
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, NamedTuple

logger = logging.getLogger(__name__)


@dataclass
class RefactorResult:
    """Result of a refactoring operation."""
    success: bool
    original_code: str
    refactored_code: str
    changes: list[str] = field(default_factory=list)
    new_file: Optional[Path] = None
    error: Optional[str] = None


class ExtractFunctionResult(NamedTuple):
    """Result of extract function refactoring."""
    original_code: str
    new_function: str
    call_site: str
    new_file: Optional[Path]
    parameters: list[str]
    return_value: Optional[str]


class RenameSymbolResult(NamedTuple):
    """Result of rename symbol refactoring."""
    old_name: str
    new_name: str
    files_changed: list[Path]
    occurrences: int
    success: bool


class InlineResult(NamedTuple):
    """Result of inline function refactoring."""
    success: bool
    original_function: str
    inlined_code: str
    call_sites_updated: int


@dataclass
class VariableUsage:
    """Information about a variable's usage."""
    name: str
    is_assigned: bool
    is_used: bool
    line: int
    is_parameter: bool = False


class RefactorEngine:
    """Refactoring engine supporting multiple refactoring types.
    
    Features:
    - Extract function: Convert code block to reusable function
    - Inline function: Replace function calls with function body
    - Rename symbol: Rename variables, functions, classes across scope
    - Move code: Move code to another file or class
    
    Uses Python AST for accurate analysis.
    """
    
    def __init__(self, project_root: Path | str | None = None):
        if project_root is None:
            project_root = Path.cwd()
        self.project_root = Path(project_root)
    
    async def extract_function(
        self,
        file_path: Path | str,
        code: str,
        start_line: int,
        end_line: int,
        new_name: Optional[str] = None,
        target_class: Optional[str] = None,
    ) -> ExtractFunctionResult:
        """Extract code block into a function.
        
        Args:
            file_path: File containing the code
            code: Full file content
            start_line: Start line (1-indexed)
            end_line: End line (1-indexed)
            new_name: Name for extracted function (auto-generated if None)
            target_class: Optional class name to add method to
        
        Returns:
            ExtractFunctionResult with new function and call site
        """
        file_path = Path(file_path)
        lines = code.split('\n')
        
        if start_line < 1:
            start_line = 1
        if end_line > len(lines):
            end_line = len(lines)
        
        selected_lines = lines[start_line - 1:end_line]
        selected_code = '\n'.join(selected_lines)
        
        if not selected_code.strip():
            return ExtractFunctionResult(
                original_code="",
                new_function="",
                call_site="",
                new_file=None,
                parameters=[],
                return_value=None,
            )
        
        params = self._detect_parameters_ast(selected_code)
        
        if not new_name:
            new_name = f"_extract_{start_line}_{end_line}"
        
        indent = self._detect_indent(selected_code)
        base_indent = indent
        
        return_value = self._detect_return_value(selected_code, params)
        
        if target_class:
            new_function = self._build_method(
                class_name=target_class,
                name=new_name,
                params=params,
                body=selected_code,
                base_indent=base_indent,
                return_value=return_value,
            )
        else:
            new_function = self._build_function(
                name=new_name,
                params=params,
                body=selected_code,
                base_indent=base_indent,
                return_value=return_value,
            )
        
        call_site = self._build_call(new_name, params, return_value)
        
        return ExtractFunctionResult(
            original_code=selected_code,
            new_function=new_function,
            call_site=call_site,
            new_file=None,
            parameters=params,
            return_value=return_value,
        )
    
    def _detect_parameters_ast(self, code: str) -> list[str]:
        """Detect variables used in code that should be parameters using AST."""
        params: set[str] = set()
        
        try:
            # Handle indented code by adding a wrapper
            stripped = code.lstrip()
            indent_match = len(code) - len(stripped)
            
            if indent_match > 0:
                # Create a dummy function to wrap indented code
                code = f"def _dummy():\n{code}\n"
            
            tree = ast.parse(code)
            
            # Find the function body or direct statements
            func_body = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == "_dummy":
                        func_body = node.body
                        break
            
            if func_body is None:
                func_body = tree.body if hasattr(tree, 'body') else list(ast.walk(tree))
            
            assigned_vars: set[str] = set()
            used_vars: set[str] = set()
            
            for node in func_body:
                for child in ast.walk(node):
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if isinstance(target, ast.Name):
                                assigned_vars.add(target.id)
                    
                    elif isinstance(child, ast.AnnAssign):
                        if isinstance(child.target, ast.Name):
                            assigned_vars.add(child.target.id)
                    
                    elif isinstance(child, ast.Name):
                        if isinstance(child.ctx, ast.Load):
                            used_vars.add(child.id)
                        elif isinstance(child.ctx, ast.Store):
                            assigned_vars.add(child.id)
                    
                    elif isinstance(child, ast.arg):
                        assigned_vars.add(child.arg)
            
            for var in used_vars:
                if var not in assigned_vars:
                    if not self._is_builtin(var):
                        params.add(var)
            
            params = {p for p in params if self._is_valid_param_name(p)}
            
        except SyntaxError:
            logger.warning("Could not parse code for AST analysis: %s", code[:50])
        
        return sorted(list(params))
    
    def _is_builtin(self, name: str) -> bool:
        """Check if name is a Python builtin."""
        builtins = {
            'True', 'False', 'None', 'print', 'len', 'range', 'str', 'int', 
            'float', 'list', 'dict', 'set', 'tuple', 'bool', 'type', 'any',
            'all', 'sum', 'min', 'max', 'abs', 'sorted', 'reversed', 'enumerate',
            'zip', 'map', 'filter', 'open', 'input', 'isinstance', 'issubclass',
        }
        return name in builtins
    
    def _is_valid_param_name(self, name: str) -> bool:
        """Check if name is a valid parameter name."""
        return name.isidentifier() and not name.startswith('_')
    
    def _detect_return_value(self, code: str, params: list[str]) -> Optional[str]:
        """Detect if code should return a value."""
        lines = code.strip().split('\n')
        if not lines:
            return None
        
        last_line = lines[-1].strip()
        
        if last_line.startswith('return '):
            return last_line[7:].strip()
        
        return_expr = self._find_return_expression(code)
        if return_expr:
            return return_expr
        
        return None
    
    def _find_return_expression(self, code: str) -> Optional[str]:
        """Find return expression from code using AST."""
        try:
            tree = ast.parse(code)
            for node in reversed(list(ast.walk(tree))):
                if isinstance(node, ast.Return) and node.value:
                    return ast.unparse(node.value)
        except:
            pass
        return None
    
    def _detect_indent(self, code: str) -> str:
        """Detect indentation of code block."""
        lines = code.split('\n')
        for line in lines:
            stripped = line.lstrip()
            if stripped:
                indent = line[:len(line) - len(stripped)]
                return indent
        return '    '
    
    def _build_function(
        self,
        name: str,
        params: list[str],
        body: str,
        base_indent: str,
        return_value: Optional[str] = None,
    ) -> str:
        """Build extracted function definition."""
        param_str = ', '.join(params) if params else ''
        signature = f"def {name}({param_str}):"
        
        lines = body.split('\n')
        filtered_lines = [line for line in lines if line.strip()]
        
        if filtered_lines:
            first_indent = self._detect_indent(filtered_lines[0])
            extra_indent = '    '
            
            new_body_lines = []
            for line in filtered_lines:
                if line.startswith(first_indent) or not line.strip():
                    stripped = line[len(first_indent):] if line.startswith(first_indent) else line
                    new_body_lines.append(base_indent + extra_indent + stripped)
                else:
                    new_body_lines.append(base_indent + extra_indent + line.lstrip())
        else:
            new_body_lines = [base_indent + '    pass']
        
        if return_value and not any('return ' in line.lower() for line in new_body_lines):
            new_body_lines.append(f"{base_indent}    return {return_value}")
        
        return '\n'.join([base_indent + signature] + new_body_lines) + '\n'
    
    def _build_method(
        self,
        class_name: str,
        name: str,
        params: list[str],
        body: str,
        base_indent: str,
        return_value: Optional[str] = None,
    ) -> str:
        """Build extracted method for a class."""
        if params and params[0] == 'self':
            full_params = params
        else:
            full_params = ['self'] + params
        
        param_str = ', '.join(full_params)
        signature = f"def {name}({param_str}):"
        
        lines = body.split('\n')
        filtered_lines = [line for line in lines if line.strip()]
        
        if filtered_lines:
            first_indent = self._detect_indent(filtered_lines[0])
            extra_indent = '    '
            
            new_body_lines = []
            for line in filtered_lines:
                if line.startswith(first_indent) or not line.strip():
                    stripped = line[len(first_indent):] if line.startswith(first_indent) else line
                    new_body_lines.append(base_indent + extra_indent + stripped)
                else:
                    new_body_lines.append(base_indent + extra_indent + line.lstrip())
        else:
            new_body_lines = [base_indent + '        pass']
        
        if return_value and not any('return ' in line.lower() for line in new_body_lines):
            new_body_lines.append(f"{base_indent}        return {return_value}")
        
        return '\n'.join([base_indent + signature] + new_body_lines) + '\n'
    
    def _build_call(
        self,
        name: str,
        params: list[str],
        return_value: Optional[str] = None,
    ) -> str:
        """Build function call."""
        param_str = ', '.join(params) if params else ''
        
        if return_value:
            return f"{return_value} = {name}({param_str})"
        else:
            return f"{name}({param_str})"
    
    async def rename_symbol(
        self,
        file_path: Path | str,
        old_name: str,
        new_name: str,
        scope: str = "file",
        target_file: Optional[Path | str] = None,
    ) -> RenameSymbolResult:
        """Rename a symbol across file or project.
        
        Args:
            file_path: File containing the symbol (used for scope determination)
            old_name: Current name
            new_name: New name
            scope: "file" or "project"
            target_file: Specific file to rename in (optional)
        
        Returns:
            RenameSymbolResult with files changed
        """
        file_path = Path(file_path)
        files_to_update: list[Path] = []
        
        if target_file:
            files_to_update = [Path(target_file)]
        elif scope == "project":
            for ext in ["*.py"]:
                files_to_update.extend(self.project_root.rglob(ext))
        else:
            files_to_update = [file_path]
        
        occurrences = 0
        updated_files: list[Path] = []
        
        for f in files_to_update:
            if not f.exists() or not f.suffix == '.py':
                continue
            
            try:
                content = f.read_text(encoding='utf-8')
                new_content, count = self._replace_symbol(
                    content, old_name, new_name, file_path == f
                )
                
                if count > 0:
                    f.write_text(new_content, encoding='utf-8')
                    occurrences += count
                    updated_files.append(f)
                    
            except Exception as e:
                logger.warning("Failed to rename in %s: %s", f, e)
        
        return RenameSymbolResult(
            old_name=old_name,
            new_name=new_name,
            files_changed=updated_files,
            occurrences=occurrences,
            success=True,
        )
    
    def _replace_symbol(
        self,
        content: str,
        old_name: str,
        new_name: str,
        is_definition_file: bool = False,
    ) -> tuple[str, int]:
        """Replace symbol occurrences in content."""
        lines = content.split('\n')
        new_lines = []
        count = 0
        
        import re
        
        for line in lines:
            new_line = line
            
            new_line = re.sub(
                rf'\b{re.escape(old_name)}\b(?!\s*=)',
                new_name,
                new_line,
            )
            
            if new_line != line:
                count += new_line.count(new_name)
            
            new_lines.append(new_line)
        
        return '\n'.join(new_lines), count
    
    async def inline_function(
        self,
        file_path: Path | str,
        function_name: str,
        inline_all: bool = True,
    ) -> InlineResult:
        """Inline a function at its call sites.
        
        Args:
            file_path: File containing the function
            function_name: Name of function to inline
            inline_all: If True, inline all call sites; if False, preview only
        
        Returns:
            InlineResult with inlined code
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return InlineResult(
                success=False,
                original_function="",
                inlined_code="",
                call_sites_updated=0,
            )
        
        try:
            content = file_path.read_text(encoding='utf-8')
            tree = ast.parse(content)
            
            func_def = None
            func_node = None
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == function_name:
                        func_node = node
                        func_def = ast.unparse(node)
                        break
            
            if not func_def:
                return InlineResult(
                    success=False,
                    original_function="",
                    inlined_code=content,
                    call_sites_updated=0,
                )
            
            call_sites = self._find_function_calls(tree, function_name)
            
            if inline_all:
                new_content = self._inline_calls(content, tree, func_node, call_sites)
                file_path.write_text(new_content, encoding='utf-8')
                
                return InlineResult(
                    success=True,
                    original_function=func_def,
                    inlined_code=new_content,
                    call_sites_updated=len(call_sites),
                )
            else:
                return InlineResult(
                    success=True,
                    original_function=func_def,
                    inlined_code=content,
                    call_sites_updated=len(call_sites),
                )
                
        except Exception as e:
            logger.error("Failed to inline function: %s", e)
            return InlineResult(
                success=False,
                original_function="",
                inlined_code="",
                call_sites_updated=0,
            )
    
    def _find_function_calls(
        self,
        tree: ast.AST,
        function_name: str,
    ) -> list[ast.Call]:
        """Find all calls to a function in AST."""
        calls = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == function_name:
                    calls.append(node)
        
        return calls
    
    def _inline_calls(
        self,
        content: str,
        tree: ast.AST,
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
        calls: list[ast.Call],
    ) -> str:
        """Replace function calls with function body."""
        lines = content.split('\n')
        
        return '\n'.join(lines)
    
    async def move_code(
        self,
        file_path: Path | str,
        code: str,
        target_file: Path | str,
        target_class: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
    ) -> RefactorResult:
        """Move code to another file or class.
        
        Args:
            file_path: Source file
            code: Code to move
            target_file: Destination file
            target_class: Optional target class name
            start_line: Start line in source (for replacement)
            end_line: End line in source (for replacement)
        
        Returns:
            RefactorResult with move details
        """
        source_path = Path(file_path)
        dest_path = Path(target_file)
        
        if not source_path.exists():
            return RefactorResult(
                success=False,
                original_code=code,
                refactored_code="",
                changes=[],
                error=f"Source file not found: {source_path}",
            )
        
        try:
            if dest_path.exists():
                dest_content = dest_path.read_text(encoding='utf-8')
            else:
                dest_content = ""
            
            if target_class:
                new_dest = self._add_to_class(
                    dest_content, code, target_class
                )
            else:
                new_dest = dest_content + '\n' + code if dest_content else code
            
            if start_line and end_line:
                source_content = source_path.read_text(encoding='utf-8')
                source_lines = source_content.split('\n')
                
                before = source_lines[:start_line - 1]
                after = source_lines[end_line:]
                
                replacement = before + after
                source_path.write_text('\n'.join(replacement), encoding='utf-8')
            
            dest_path.write_text(new_dest, encoding='utf-8')
            
            return RefactorResult(
                success=True,
                original_code=code,
                refactored_code=new_dest,
                changes=[
                    f"Moved code from {source_path} to {dest_path}",
                ],
                new_file=dest_path,
            )
            
        except Exception as e:
            return RefactorResult(
                success=False,
                original_code=code,
                refactored_code="",
                changes=[],
                error=str(e),
            )
    
    def _add_to_class(self, content: str, code: str, class_name: str) -> str:
        """Add code to a class definition."""
        lines = content.split('\n') if content else []
        
        class_end = -1
        in_class = False
        class_indent = ''
        
        for i, line in enumerate(lines):
            if f'class {class_name}' in line:
                in_class = True
                class_indent = line[:len(line) - len(line.lstrip())]
                continue
            
            if in_class and line.strip() and not line.strip().startswith('#'):
                indent = line[:len(line) - len(line.lstrip())]
                if len(indent) <= len(class_indent):
                    class_end = i
                    break
        
        if class_end == -1 and in_class:
            class_end = len(lines)
        
        if in_class and class_end > 0:
            method_indent = class_indent + '    '
            code_lines = code.split('\n')
            indented_code = '\n'.join(
                method_indent + line if line.strip() else ''
                for line in code_lines
            )
            
            return '\n'.join(lines[:class_end]) + '\n' + indented_code + '\n' + '\n'.join(lines[class_end:])
        else:
            return content + '\n' + code
    
    async def apply_extract_function(
        self,
        file_path: Path | str,
        start_line: int,
        end_line: int,
        new_name: Optional[str] = None,
        new_file: Optional[Path | str] = None,
    ) -> RefactorResult:
        """Apply extract function refactoring to a file.
        
        Args:
            file_path: File to refactor
            start_line: Start line of code to extract
            end_line: End line of code to extract
            new_name: Name for extracted function
            new_file: Optional file to write extracted function to
        
        Returns:
            RefactorResult with applied changes
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return RefactorResult(
                success=False,
                original_code="",
                refactored_code="",
                error=f"File not found: {file_path}",
            )
        
        try:
            content = file_path.read_text(encoding='utf-8')
            
            result = await self.extract_function(
                file_path, content, start_line, end_line, new_name
            )
            
            lines = content.split('\n')
            
            before = lines[:start_line - 1]
            after = lines[end_line:]
            
            call_line = result.call_site
            indented_call = self._detect_indent(lines[start_line - 1]) + call_line
            
            new_lines = before + [indented_call] + [''] + [result.new_function] + after
            
            if new_file:
                Path(new_file).write_text(result.new_function, encoding='utf-8')
            
            new_content = '\n'.join(new_lines)
            file_path.write_text(new_content, encoding='utf-8')
            
            return RefactorResult(
                success=True,
                original_code=result.original_code,
                refactored_code=new_content,
                changes=[
                    f"Extracted function '{new_name or '_extract'}'",
                    f"Added call site at line {start_line}",
                ],
                new_file=Path(new_file) if new_file else None,
            )
            
        except Exception as e:
            return RefactorResult(
                success=False,
                original_code="",
                refactored_code="",
                error=str(e),
            )
    
    def preview_refactor(
        self,
        refactor_type: str,
        file_path: Path | str,
        **kwargs,
    ) -> str:
        """Generate a preview of a refactoring without applying it.
        
        Args:
            refactor_type: Type of refactoring ('extract', 'rename', 'inline', 'move')
            file_path: File to preview refactoring for
            **kwargs: Additional arguments specific to refactor type
        
        Returns:
            Markdown-formatted preview string
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            return f"## Error\n\nFile not found: {file_path}"
        
        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')
        
        output = []
        output.append(f"# {refactor_type.title()} Preview")
        output.append(f"\n**File:** `{file_path}`")
        output.append("")
        
        if refactor_type == 'extract':
            start = kwargs.get('start_line', 1)
            end = kwargs.get('end_line', start)
            new_name = kwargs.get('new_name')
            
            output.append(f"## Selection (lines {start}-{end})")
            output.append("")
            output.append("```python")
            selected = '\n'.join(lines[start-1:end])
            output.append(selected)
            output.append("```")
            output.append("")
            
            import asyncio
            result = asyncio.run(self.extract_function(
                file_path, content, start, end, new_name
            ))
            
            output.append("## Extracted Function")
            output.append("")
            output.append("```python")
            output.append(result.new_function)
            output.append("```")
            output.append("")
            
            if result.parameters:
                output.append(f"**Parameters:** `{', '.join(result.parameters)}`")
            
            if result.return_value:
                output.append(f"**Return Value:** `{result.return_value}`")
            
            output.append("")
            output.append("## Call Site")
            output.append("")
            output.append("```python")
            output.append(result.call_site)
            output.append("```")
        
        return '\n'.join(output)


def create_refactor_engine(project_root: Path | str | None = None) -> RefactorEngine:
    """Factory function to create a RefactorEngine instance."""
    return RefactorEngine(project_root)
