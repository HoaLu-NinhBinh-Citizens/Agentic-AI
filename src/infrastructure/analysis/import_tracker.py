"""Track imports across files for cross-file resolution."""

from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SymbolExport:
    """A symbol exported by a module."""
    name: str
    file_path: Path
    line: int
    kind: str  # "class", "function", "variable", "module"


class ImportTracker:
    """Track imports and exports across the project."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._exports: dict[str, list[SymbolExport]] = {}  # module_name -> exports
        self._modules: dict[str, Path] = {}  # module_name -> file_path

    def index_project(self, files: list[Path]) -> None:
        """Index all files to build import/export map."""
        for f in files:
            if f.suffix in (".py", ".ts", ".js"):
                self._index_file(f)

    def _index_file(self, file_path: Path) -> None:
        """Index a single file for exports."""
        try:
            content = file_path.read_text(encoding="utf-8")
            module_name = self._get_module_name(file_path)

            exports: list[SymbolExport] = []

            # Python: __all__, class/function defs
            if file_path.suffix == ".py":
                # __all__ = ["foo", "bar"]
                if match := re.search(r"__all__\s*=\s*\[(.*?)\]", content, re.DOTALL):
                    names = re.findall(r'"(\w+)"', match.group(1))
                    base_line = content[:match.start()].count("\n") + 1
                    for name in names:
                        exports.append(SymbolExport(
                            name=name,
                            file_path=file_path,
                            line=base_line,
                            kind="exported"
                        ))

                # class Foo:
                for match in re.finditer(r"^class\s+(\w+)", content, re.MULTILINE):
                    exports.append(SymbolExport(
                        name=match.group(1),
                        file_path=file_path,
                        line=content[:match.start()].count("\n") + 1,
                        kind="class"
                    ))

                # def foo():
                for match in re.finditer(r"^def\s+(\w+)", content, re.MULTILINE):
                    exports.append(SymbolExport(
                        name=match.group(1),
                        file_path=file_path,
                        line=content[:match.start()].count("\n") + 1,
                        kind="function"
                    ))

                # async def foo():
                for match in re.finditer(r"^async\s+def\s+(\w+)", content, re.MULTILINE):
                    exports.append(SymbolExport(
                        name=match.group(1),
                        file_path=file_path,
                        line=content[:match.start()].count("\n") + 1,
                        kind="function"
                    ))

            # TypeScript/JavaScript: export const, export function, export class
            elif file_path.suffix in (".ts", ".js", ".tsx", ".jsx"):
                # export class Foo
                for match in re.finditer(r"export\s+class\s+(\w+)", content, re.MULTILINE):
                    exports.append(SymbolExport(
                        name=match.group(1),
                        file_path=file_path,
                        line=content[:match.start()].count("\n") + 1,
                        kind="class"
                    ))
                # export function foo()
                for match in re.finditer(r"export\s+(?:async\s+)?function\s+(\w+)", content, re.MULTILINE):
                    exports.append(SymbolExport(
                        name=match.group(1),
                        file_path=file_path,
                        line=content[:match.start()].count("\n") + 1,
                        kind="function"
                    ))
                # export const/let/var foo
                for match in re.finditer(r"export\s+(?:const|let|var)\s+(\w+)", content, re.MULTILINE):
                    exports.append(SymbolExport(
                        name=match.group(1),
                        file_path=file_path,
                        line=content[:match.start()].count("\n") + 1,
                        kind="variable"
                    ))

            self._exports[module_name] = exports
            self._modules[module_name] = file_path

        except Exception as e:
            print(f"Failed to index {file_path}: {e}")

    def _get_module_name(self, file_path: Path) -> str:
        """Convert file path to module name."""
        try:
            rel = file_path.relative_to(self.project_root)
            parts = list(rel.parts[:-1]) + [rel.stem]
            return ".".join(parts)
        except ValueError:
            return file_path.stem

    def resolve_import(
        self,
        importing_file: Path,
        imported_name: str,
        from_module: Optional[str] = None
    ) -> Optional[SymbolExport]:
        """Resolve where an imported name comes from."""
        if from_module:
            # from module import name
            exports = self._exports.get(from_module, [])
            for exp in exports:
                if exp.name == imported_name:
                    return exp
        else:
            # import module
            if imported_name in self._modules:
                return SymbolExport(
                    name=imported_name,
                    file_path=self._modules[imported_name],
                    line=0,
                    kind="module"
                )

        return None

    def find_usages(
        self,
        symbol_name: str,
        module: str
    ) -> list[tuple[Path, int]]:
        """Find all usages of a symbol across the project."""
        usages: list[tuple[Path, int]] = []
        exports = self._exports.get(module, [])

        for exp in exports:
            if exp.name == symbol_name:
                # Search all files for references
                for file_path in self.project_root.rglob("*.py"):
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        for i, line in enumerate(content.split("\n"), 1):
                            if symbol_name in line and f"import {module}" in content:
                                usages.append((file_path, i))
                    except Exception:
                        pass

        return usages

    def get_module_exports(self, module_name: str) -> list[SymbolExport]:
        """Get all exports from a module."""
        return self._exports.get(module_name, [])

    def get_all_modules(self) -> list[str]:
        """Get all indexed module names."""
        return list(self._modules.keys())
