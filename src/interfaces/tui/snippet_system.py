"""Snippet System — Cursor-like code snippets with tabstops and variables.

Supports:
- Built-in snippets (if, for, while, try, class, function, etc.)
- Custom user snippets
- Tabstop placeholders ($1, $2, ...)
- Variable transformations (${1:default})
- Transformed variables (${1/pattern/replacement/flags})
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class TabStop:
    """A tabstop in a snippet."""
    index: int
    default: str = ""
    choices: list[str] = field(default_factory=list)
    is_final: bool = False


@dataclass
class SnippetVariable:
    """A variable in a snippet."""
    name: str
    default: str = ""
    transform: Optional[str] = None


@dataclass
class Snippet:
    """A code snippet."""
    id: str
    prefix: str
    body: str
    description: str = ""
    scope: str = ""
    tabstops: list[TabStop] = field(default_factory=list)
    variables: list[SnippetVariable] = field(default_factory=list)
    is_user: bool = False

    def __post_init__(self):
        self._parse_body()

    def _parse_body(self) -> None:
        """Parse tabstops and variables from body."""
        self.tabstops = []
        self.variables = []

        tabstop_pattern = r"\$\{(\d+)(?::([^}]*))?(?:\|([^}]*))?\}"
        for m in re.finditer(tabstop_pattern, self.body):
            index = int(m.group(1))
            default = m.group(2) or ""
            choices_str = m.group(3)
            choices = [c.strip() for c in choices_str.split(",")] if choices_str else []

            self.tabstops.append(TabStop(
                index=index,
                default=default,
                choices=choices,
                is_final=index == 0,
            ))

        for m in re.finditer(r"\$([1-9][0-9]*)", self.body):
            index = int(m.group(1))
            if not any(ts.index == index for ts in self.tabstops):
                self.tabstops.append(TabStop(index=index))

        var_pattern = r"\$\{([A-Z_][A-Z0-9_]*)(?::([^}]*))?\}"
        for m in re.finditer(var_pattern, self.body):
            name = m.group(1)
            default = m.group(2) or ""
            if not any(v.name == name for v in self.variables):
                self.variables.append(SnippetVariable(name=name, default=default))

    def expand(
        self,
        context: Optional[dict[str, str]] = None,
        user_input: Optional[dict[int, str]] = None,
    ) -> str:
        """Expand the snippet with context and user input."""
        result = self.body
        context = context or {}
        user_input = user_input or {}

        for var in self.variables:
            value = context.get(var.name, var.default)
            result = result.replace(f"${{{var.name}}}", value)
            result = result.replace(f"${{{var.name}:{var.default}}}", value)

        for ts in sorted(self.tabstops, key=lambda t: t.index, reverse=True):
            replacement = user_input.get(ts.index, ts.default)
            pattern = f"${{{ts.index}}}"
            if pattern in result:
                result = result.replace(pattern, replacement)
            pattern_with_default = f"${{{ts.index}:{ts.default}}}"
            if pattern_with_default in result:
                result = result.replace(pattern_with_default, replacement)
            result = result.replace(f"${ts.index}", replacement)

        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prefix": self.prefix,
            "body": self.body,
            "description": self.description,
            "scope": self.scope,
            "tabstops": [{"index": ts.index, "default": ts.default, "choices": ts.choices}
                        for ts in self.tabstops],
            "isUser": self.is_user,
        }


class SnippetSystem:
    """Manages code snippets."""

    def __init__(self, user_snippets_path: Optional[str] = None):
        self._snippets: dict[str, Snippet] = {}
        self._user_snippets_path = user_snippets_path
        self._callbacks: list[Callable[[dict], None]] = []

        self._register_builtin_snippets()

    def _register_builtin_snippets(self) -> None:
        """Register built-in snippets for common languages."""
        self._register(Snippet(
            id="py-if",
            prefix="if",
            body="if ${1:condition}:\n    ${2:pass}",
            description="If statement",
            scope="python",
        ))
        self._register(Snippet(
            id="py-elif",
            prefix="elif",
            body="elif ${1:condition}:\n    ${2:pass}",
            description="Elif statement",
            scope="python",
        ))
        self._register(Snippet(
            id="py-else",
            prefix="else",
            body="else:\n    ${1:pass}",
            description="Else statement",
            scope="python",
        ))
        self._register(Snippet(
            id="py-for",
            prefix="for",
            body="for ${1:item} in ${2:iterable}:\n    ${3:pass}",
            description="For loop",
            scope="python",
        ))
        self._register(Snippet(
            id="py-while",
            prefix="while",
            body="while ${1:condition}:\n    ${2:pass}",
            description="While loop",
            scope="python",
        ))
        self._register(Snippet(
            id="py-def",
            prefix="def",
            body="def ${1:function_name}(${2:self}):\n    \"\"\"${3:Docstring}\"\"\"\n    ${4:pass}",
            description="Function definition",
            scope="python",
        ))
        self._register(Snippet(
            id="py-async-def",
            prefix="adef",
            body="async def ${1:function_name}(${2:self}):\n    \"\"\"${3:Docstring}\"\"\"\n    ${4:pass}",
            description="Async function definition",
            scope="python",
        ))
        self._register(Snippet(
            id="py-class",
            prefix="class",
            body="class ${1:ClassName}(${2:object}):\n    \"\"\"${3:Docstring}\"\"\"\n\n    def __init__(self${4:, }):\n        ${5:pass}",
            description="Class definition",
            scope="python",
        ))
        self._register(Snippet(
            id="py-try",
            prefix="try",
            body="try:\n    ${1:pass}\nexcept ${2:Exception} as ${3:e}:\n    ${4:raise}\nfinally:\n    ${5:pass}",
            description="Try-except block",
            scope="python",
        ))
        self._register(Snippet(
            id="py-with",
            prefix="with",
            body="with ${1:context_manager} as ${2:target}:\n    ${3:pass}",
            description="With statement",
            scope="python",
        ))
        self._register(Snippet(
            id="py-lambda",
            prefix="lambda",
            body="lambda ${1:x}: ${2:x}",
            description="Lambda function",
            scope="python",
        ))
        self._register(Snippet(
            id="py-list-comp",
            prefix="lc",
            body="[${1:x} for ${2:x} in ${3:iterable}]",
            description="List comprehension",
            scope="python",
        ))
        self._register(Snippet(
            id="py-dict-comp",
            prefix="dc",
            body="{${1:k}: ${2:v} for ${3:k}, ${4:v} in ${5:items}}",
            description="Dict comprehension",
            scope="python",
        ))
        self._register(Snippet(
            id="py-assert",
            prefix="ass",
            body="assert ${1:condition}, ${2:'message'}",
            description="Assert statement",
            scope="python",
        ))
        self._register(Snippet(
            id="py-property",
            prefix="property",
            body="@property\ndef ${1:name}(self):\n    \"\"\"${2:Docs}\"\"\"\n    return self._${1:name}\n\n@${1:name}.setter\ndef ${1:name}(self, value):\n    self._${1:name} = value",
            description="Property decorator",
            scope="python",
        ))
        self._register(Snippet(
            id="py-context-manager",
            prefix="cm",
            body="class ${1:ContextManager}:\n    def __enter__(self):\n        ${2:pass}\n        return self\n\n    def __exit__(self, exc_type, exc_val, exc_tb):\n        ${3:pass}",
            description="Context manager class",
            scope="python",
        ))
        self._register(Snippet(
            id="py-dataclass",
            prefix="dc",
            body="@dataclass\nclass ${1:ClassName}:\n    ${2:field}: ${3:type}",
            description="Dataclass",
            scope="python",
        ))
        self._register(Snippet(
            id="py-main",
            prefix="main",
            body="def main():\n    ${1:pass}\n\nif __name__ == '__main__':\n    main()",
            description="Main function guard",
            scope="python",
        ))
        self._register(Snippet(
            id="py-type-var",
            prefix="tv",
            body="${1:T} = TypeVar('${1:T}')",
            description="TypeVar",
            scope="python",
        ))

        self._register(Snippet(
            id="js-func",
            prefix="func",
            body="const ${1:functionName} = (${2:params}) => {\n    ${3:/* code */}\n};",
            description="Arrow function",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-async-func",
            prefix="afunc",
            body="const ${1:functionName} = async (${2:params}) => {\n    ${3:/* code */}\n};",
            description="Async arrow function",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-for-of",
            prefix="forof",
            body="for (const ${1:item} of ${2:iterable}) {\n    ${3:/* code */}\n}",
            description="For-of loop",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-try",
            prefix="etry",
            body="try {\n    ${1:/* code */}\n} catch (${2:error}) {\n    ${3:/* handle */}\n}",
            description="Try-catch",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-console",
            prefix="cl",
            body="console.log(${1:msg});",
            description="Console log",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-console-dir",
            prefix="cd",
            body="console.dir(${1:obj}, { depth: null, colors: true });",
            description="Console dir",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-require",
            prefix="req",
            body="const ${1:module} = require('${1:module}');",
            description="Require module",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-import",
            prefix="imp",
            body="import { ${2:export} } from '${1:module}';",
            description="Named import",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-import-default",
            prefix="impd",
            body="import ${2:name} from '${1:module}';",
            description="Default import",
            scope="javascript",
        ))
        self._register(Snippet(
            id="js-export",
            prefix="exp",
            body="export ${1:const} ${2:name} = ${3:value};",
            description="Export",
            scope="javascript",
        ))

        self._register(Snippet(
            id="sh-if",
            prefix="if",
            body="if [ ${1:condition} ]; then\n    ${2:/* code */}\nfi",
            description="If statement",
            scope="shell",
        ))
        self._register(Snippet(
            id="sh-for",
            prefix="for",
            body="for ${1:item} in ${2:items}; do\n    ${3:/* code */}\ndone",
            description="For loop",
            scope="shell",
        ))
        self._register(Snippet(
            id="sh-func",
            prefix="func",
            body="${1:function_name}() {\n    ${2:/* code */}\n}",
            description="Function definition",
            scope="shell",
        ))

    def _register(self, snippet: Snippet) -> None:
        self._snippets[snippet.id] = snippet

    def get_snippet(self, snippet_id: str) -> Optional[Snippet]:
        return self._snippets.get(snippet_id)

    def find_snippet(self, prefix: str, scope: str = "") -> list[Snippet]:
        """Find snippets matching a prefix."""
        results = []
        for snippet in self._snippets.values():
            if snippet.prefix.startswith(prefix.lower()):
                if not scope or not snippet.scope or snippet.scope == scope:
                    results.append(snippet)
        return sorted(results, key=lambda s: len(s.prefix))

    def expand_snippet(
        self,
        snippet_id: str,
        context: Optional[dict[str, str]] = None,
        user_input: Optional[dict[int, str]] = None,
    ) -> Optional[str]:
        """Expand a snippet and return the result."""
        snippet = self.get_snippet(snippet_id)
        if not snippet:
            return None
        return snippet.expand(context, user_input)

    def add_user_snippet(self, snippet: Snippet) -> None:
        """Add a user-defined snippet."""
        snippet.is_user = True
        self._snippets[snippet.id] = snippet

    def remove_snippet(self, snippet_id: str) -> bool:
        """Remove a snippet (user snippets only)."""
        snippet = self._snippets.get(snippet_id)
        if snippet and snippet.is_user:
            del self._snippets[snippet_id]
            return True
        return False

    def get_all_snippets(self, scope: str = "") -> list[Snippet]:
        """Get all snippets, optionally filtered by scope."""
        if scope:
            return [s for s in self._snippets.values() if not s.scope or s.scope == scope]
        return list(self._snippets.values())

    def get_stats(self) -> dict[str, Any]:
        return {
            "total_snippets": len(self._snippets),
            "user_snippets": sum(1 for s in self._snippets.values() if s.is_user),
            "by_scope": {
                scope: sum(1 for s in self._snippets.values() if s.scope == scope)
                for scope in set(s.scope for s in self._snippets.values() if s.scope)
            },
        }
