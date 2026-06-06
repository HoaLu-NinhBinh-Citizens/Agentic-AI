"""Class member and method resolution for semantic cross-file analysis.

Resolves:
- Instance methods (self.method())
- Class methods (Class.method())
- Inherited methods (via MRO traversal)
- Property access (self.attr)
- Dynamic references through type inference
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ClassMember:
    """A resolved class member (method, attribute, property)."""

    name: str
    kind: str  # "method", "classmethod", "staticmethod", "property", "attribute"
    class_name: str
    file_path: Path
    line: int
    end_line: int = 0
    signature: str = ""
    return_type: Optional[str] = None
    is_inherited: bool = False
    defined_in: Optional[str] = None  # Class where it's actually defined


@dataclass
class ClassDefinition:
    """Complete class definition with members and inheritance."""

    name: str
    file_path: Path
    line: int
    end_line: int
    bases: list[str] = field(default_factory=list)
    members: dict[str, ClassMember] = field(default_factory=dict)
    module: str = ""


class ClassResolver:
    """Resolve class members, methods, and inheritance across files.

    Handles:
    - Direct method lookup: MyClass.my_method
    - Instance method lookup: self.method
    - Inherited method resolution (MRO traversal)
    - Property and attribute resolution
    - Type-guided resolution for typed variables
    """

    def __init__(self) -> None:
        self._classes: dict[str, ClassDefinition] = {}  # fully-qualified -> ClassDef
        self._type_annotations: dict[str, str] = {}  # var_name -> type_name
        self._indexed_files: set[str] = set()

    def index_file(self, file_path: Path, content: str) -> list[ClassDefinition]:
        """Index all class definitions in a file.

        Args:
            file_path: Path to the source file
            content: File content

        Returns:
            List of indexed ClassDefinition objects
        """
        file_str = str(file_path)

        # Clear existing classes from this file (for re-indexing)
        self._classes = {
            k: v for k, v in self._classes.items()
            if str(v.file_path) != file_str
        }

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cls_def = self._extract_class(node, file_path)
                key = f"{file_str}:{cls_def.name}"
                self._classes[key] = cls_def
                # Also store by simple name for lookup
                self._classes[cls_def.name] = cls_def
                classes.append(cls_def)

        self._indexed_files.add(file_str)
        return classes

    def resolve_member(
        self,
        class_name: str,
        member_name: str,
        follow_inheritance: bool = True,
    ) -> Optional[ClassMember]:
        """Resolve a class member by class name and member name.

        Args:
            class_name: Name of the class
            member_name: Name of the member to resolve
            follow_inheritance: Whether to traverse base classes

        Returns:
            ClassMember if found, None otherwise
        """
        cls_def = self._find_class(class_name)
        if not cls_def:
            return None

        # Direct lookup
        if member_name in cls_def.members:
            return cls_def.members[member_name]

        # Inheritance traversal (MRO)
        if follow_inheritance:
            for base_name in cls_def.bases:
                base_cls = self._find_class(base_name)
                if base_cls:
                    member = self.resolve_member(base_name, member_name, True)
                    if member:
                        # Mark as inherited
                        inherited = ClassMember(
                            name=member.name,
                            kind=member.kind,
                            class_name=class_name,
                            file_path=member.file_path,
                            line=member.line,
                            end_line=member.end_line,
                            signature=member.signature,
                            return_type=member.return_type,
                            is_inherited=True,
                            defined_in=member.class_name,
                        )
                        return inherited

        return None

    def resolve_self_reference(
        self,
        class_name: str,
        attr_name: str,
    ) -> Optional[ClassMember]:
        """Resolve self.attr_name within a class.

        Args:
            class_name: The class context
            attr_name: The attribute being accessed

        Returns:
            ClassMember if resolved
        """
        return self.resolve_member(class_name, attr_name, follow_inheritance=True)

    def get_all_members(
        self, class_name: str, include_inherited: bool = True
    ) -> dict[str, ClassMember]:
        """Get all members of a class including inherited ones.

        Args:
            class_name: Name of the class
            include_inherited: Whether to include inherited members

        Returns:
            Dict of member_name -> ClassMember
        """
        cls_def = self._find_class(class_name)
        if not cls_def:
            return {}

        members = dict(cls_def.members)

        if include_inherited:
            for base_name in cls_def.bases:
                base_members = self.get_all_members(base_name, True)
                for name, member in base_members.items():
                    if name not in members:  # Don't override with inherited
                        members[name] = ClassMember(
                            name=member.name,
                            kind=member.kind,
                            class_name=class_name,
                            file_path=member.file_path,
                            line=member.line,
                            end_line=member.end_line,
                            signature=member.signature,
                            return_type=member.return_type,
                            is_inherited=True,
                            defined_in=member.class_name,
                        )

        return members

    def resolve_typed_variable(
        self, var_name: str, type_name: str, attr_name: str
    ) -> Optional[ClassMember]:
        """Resolve attribute access on a typed variable.

        e.g., if `x: MyClass`, resolve `x.method()`.

        Args:
            var_name: Variable name
            type_name: Annotated type of the variable
            attr_name: Attribute being accessed

        Returns:
            ClassMember if resolved
        """
        return self.resolve_member(type_name, attr_name, follow_inheritance=True)

    def clear_file(self, file_path: Path) -> None:
        """Remove all class data for a specific file (for re-indexing)."""
        file_str = str(file_path)
        self._classes = {
            k: v for k, v in self._classes.items()
            if str(v.file_path) != file_str
        }
        self._indexed_files.discard(file_str)

    # ─── Private Helpers ─────────────────────────────────────────────────────

    def _find_class(self, name: str) -> Optional[ClassDefinition]:
        """Find a class by name (simple or qualified)."""
        if name in self._classes:
            return self._classes[name]
        # Try partial match
        for key, cls_def in self._classes.items():
            if cls_def.name == name:
                return cls_def
        return None

    def _extract_class(self, node: ast.ClassDef, file_path: Path) -> ClassDefinition:
        """Extract a ClassDefinition from an AST ClassDef node."""
        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(self._get_dotted_name(base))

        members: dict[str, ClassMember] = {}

        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = self._get_method_kind(item)
                sig = self._get_signature(item)
                ret_type = self._get_return_type(item)
                members[item.name] = ClassMember(
                    name=item.name,
                    kind=kind,
                    class_name=node.name,
                    file_path=file_path,
                    line=item.lineno,
                    end_line=item.end_lineno or item.lineno,
                    signature=sig,
                    return_type=ret_type,
                )
            elif isinstance(item, ast.Assign):
                # Class-level attributes
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        members[target.id] = ClassMember(
                            name=target.id,
                            kind="attribute",
                            class_name=node.name,
                            file_path=file_path,
                            line=item.lineno,
                        )
            elif isinstance(item, ast.AnnAssign):
                # Annotated class attributes
                if isinstance(item.target, ast.Name):
                    members[item.target.id] = ClassMember(
                        name=item.target.id,
                        kind="attribute",
                        class_name=node.name,
                        file_path=file_path,
                        line=item.lineno,
                    )

        return ClassDefinition(
            name=node.name,
            file_path=file_path,
            line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            bases=bases,
            members=members,
        )

    def _get_method_kind(self, node: ast.FunctionDef) -> str:
        """Determine method kind from decorators."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name):
                if dec.id == "staticmethod":
                    return "staticmethod"
                elif dec.id == "classmethod":
                    return "classmethod"
                elif dec.id == "property":
                    return "property"
        return "method"

    def _get_signature(self, node: ast.FunctionDef) -> str:
        """Get function signature string."""
        args = []
        for arg in node.args.args:
            name = arg.arg
            if arg.annotation:
                ann = ast.unparse(arg.annotation) if hasattr(ast, "unparse") else "?"
                args.append(f"{name}: {ann}")
            else:
                args.append(name)
        return f"({', '.join(args)})"

    def _get_return_type(self, node: ast.FunctionDef) -> Optional[str]:
        """Get return type annotation."""
        if node.returns:
            if hasattr(ast, "unparse"):
                return ast.unparse(node.returns)
        return None

    def _get_dotted_name(self, node: ast.Attribute) -> str:
        """Get dotted name from attribute node."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))
