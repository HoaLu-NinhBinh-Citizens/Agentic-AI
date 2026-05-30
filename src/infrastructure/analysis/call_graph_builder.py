"""Build accurate call graphs using semantic resolution.

This module provides semantic call graph construction that understands:
- Direct function calls
- Method calls on objects
- Imported function calls
- Dynamic dispatch
- Callback patterns
"""

from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CallSite:
    """A call site in code."""
    caller: str
    callee: str
    file_path: Path
    line: int
    is_direct: bool = True
    is_method: bool = False
    receiver_type: Optional[str] = None


@dataclass
class MethodInfo:
    """Information about a method in a class."""
    name: str
    class_name: str
    file_path: Path
    line: int
    is_static: bool = False
    is_classmethod: bool = False
    parameters: list[str] = field(default_factory=list)


@dataclass
class ClassInfo:
    """Information about a class."""
    name: str
    file_path: Path
    line: int
    end_line: int
    base_classes: list[str] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)


@dataclass
class CallGraph:
    """Complete call graph with semantic understanding."""
    edges: list[CallSite] = field(default_factory=list)
    callers: dict[str, list[CallSite]] = field(default_factory=dict)
    callees: dict[str, list[CallSite]] = field(default_factory=dict)
    classes: dict[str, ClassInfo] = field(default_factory=dict)
    methods: dict[str, list[MethodInfo]] = field(default_factory=dict)

    def find_path(self, start: str, end: str) -> list[str]:
        """Find call path from start to end using BFS.
        
        Args:
            start: Starting function/method name.
            end: Target function/method name.
            
        Returns:
            List of function names from start to end, or empty list if no path.
        """
        visited: set[str] = set()
        queue: list[tuple[str, list[str]]] = [(start, [start])]

        while queue:
            current, path = queue.pop(0)
            if current == end:
                return path

            if current in visited:
                continue
            visited.add(current)

            for call in self.callees.get(current, []):
                if call.callee not in visited:
                    queue.append((call.callee, path + [call.callee]))

        return []

    def find_cycles(self) -> list[list[str]]:
        """Find circular dependencies in the call graph.
        
        Returns:
            List of cycles, each cycle is a list of function names.
        """
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: list[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.append(node)

            for call in self.callees.get(node, []):
                if call.callee not in visited:
                    dfs(call.callee)
                elif call.callee in rec_stack:
                    cycle_start = rec_stack.index(call.callee)
                    cycle = rec_stack[cycle_start:] + [call.callee]
                    if cycle not in cycles:
                        cycles.append(cycle)

            rec_stack.pop()

        for node in self.callees:
            if node not in visited:
                dfs(node)

        return cycles

    def get_callers(self, func_name: str) -> list[CallSite]:
        """Get all call sites that call the given function."""
        return self.callers.get(func_name, [])

    def get_callees(self, func_name: str) -> list[CallSite]:
        """Get all functions called by the given function."""
        return self.callees.get(func_name, [])

    def get_method(self, class_name: str, method_name: str) -> Optional[MethodInfo]:
        """Get method info for a class method."""
        methods = self.methods.get(class_name, [])
        for method in methods:
            if method.name == method_name:
                return method
        return None

    def get_class_methods(self, class_name: str) -> list[MethodInfo]:
        """Get all methods for a class."""
        return self.methods.get(class_name, [])

    def find_override_methods(self, base_method: str) -> list[MethodInfo]:
        """Find methods that override a base class method.
        
        Args:
            base_method: Name of the base method (e.g., 'object.__init__').
            
        Returns:
            List of MethodInfo for overriding methods.
        """
        parts = base_method.split(".")
        if len(parts) != 2:
            return []

        base_class, method_name = parts
        overrides: list[MethodInfo] = []

        for cls_info in self.classes.values():
            if base_class in cls_info.base_classes:
                for method in cls_info.methods:
                    if method.name == method_name:
                        overrides.append(method)

        return overrides


class CallGraphBuilder:
    """Build call graphs using semantic resolution.
    
    This builder uses Python AST parsing for accurate call graph construction,
    understanding method calls, imports, and class hierarchies.
    """

    def __init__(self, semantic_resolver) -> None:
        """Initialize the builder.
        
        Args:
            semantic_resolver: SemanticResolver instance for symbol resolution.
        """
        self.resolver = semantic_resolver
        self._current_class: Optional[str] = None
        self._current_function: Optional[str] = None

    def build(
        self,
        files: list[Path],
        contents: dict[Path, str]
    ) -> CallGraph:
        """Build complete call graph for project.
        
        Args:
            files: List of file paths to analyze.
            contents: Dict mapping file paths to their content strings.
            
        Returns:
            Complete CallGraph with edges, callers, callees, and class info.
        """
        graph = CallGraph()

        # Index project first for import resolution
        self.resolver.index_project(files, contents)

        # Extract class info first (needed for method resolution)
        for path, content in contents.items():
            self._extract_classes(path, content, graph)

        # Find all call sites
        for path, content in contents.items():
            calls = self._find_calls(path, content, graph)
            for call in calls:
                graph.edges.append(call)

                if call.callee not in graph.callers:
                    graph.callers[call.callee] = []
                graph.callers[call.callee].append(call)

                if call.caller not in graph.callees:
                    graph.callees[call.caller] = []
                graph.callees[call.caller].append(call)

        return graph

    def _extract_classes(self, path: Path, content: str, graph: CallGraph) -> None:
        """Extract class definitions and their methods."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                base_classes = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_classes.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        base_classes.append(self._get_attr_name(base))

                class_info = ClassInfo(
                    name=node.name,
                    file_path=path,
                    line=node.lineno,
                    end_line=node.end_lineno or node.lineno,
                    base_classes=base_classes,
                    methods=[]
                )
                graph.classes[node.name] = class_info

                # Extract methods
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        # Check decorators directly without ast.walk on decorator list
                        is_static = False
                        is_classmethod = False
                        for dec in item.decorator_list:
                            if isinstance(dec, ast.Name):
                                if dec.id == "staticmethod":
                                    is_static = True
                                elif dec.id == "classmethod":
                                    is_classmethod = True
                            elif isinstance(dec, ast.Attribute):
                                # Handle @something.static_method style
                                attr_name = self._get_attr_name(dec)
                                if "staticmethod" in attr_name:
                                    is_static = True
                                elif "classmethod" in attr_name:
                                    is_classmethod = True

                        params = [arg.arg for arg in item.args.args]
                        method_info = MethodInfo(
                            name=item.name,
                            class_name=node.name,
                            file_path=path,
                            line=item.lineno,
                            is_static=is_static,
                            is_classmethod=is_classmethod,
                            parameters=params
                        )
                        class_info.methods.append(method_info)

                        # Index method by class
                        if node.name not in graph.methods:
                            graph.methods[node.name] = []
                        graph.methods[node.name].append(method_info)

    def _find_calls(
        self,
        path: Path,
        content: str,
        graph: CallGraph
    ) -> list[CallSite]:
        """Find all call sites in content."""
        calls: list[CallSite] = []

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return calls

        # Find all Call nodes
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_site = self._analyze_call(node, path, tree)
                if call_site:
                    calls.append(call_site)

        return calls

    def _analyze_call(
        self,
        node: ast.Call,
        path: Path,
        tree: ast.AST
    ) -> Optional[CallSite]:
        """Analyze a single call node and extract call site info."""
        caller = self._find_parent_function(tree, node)
        if not caller:
            caller = "<module>"

        callee_name: str
        is_method = False
        receiver_type: Optional[str] = None

        if isinstance(node.func, ast.Name):
            # Direct function call: foo()
            callee_name = node.func.id
            is_method = False

        elif isinstance(node.func, ast.Attribute):
            # Method call: obj.method() or Class.method()
            callee_name = node.func.attr
            is_method = True

            # Try to determine receiver type
            receiver = node.func.value
            if isinstance(receiver, ast.Name):
                receiver_type = receiver.id
            elif isinstance(receiver, ast.Attribute):
                receiver_type = self._get_attr_name(receiver)

        else:
            return None

        # Skip keywords and builtins
        if callee_name in {"if", "while", "for", "return", "class", "def", 
                          "import", "raise", "assert", "with", "lambda"}:
            return None

        return CallSite(
            caller=caller,
            callee=callee_name,
            file_path=path,
            line=node.lineno,
            is_direct=not is_method,
            is_method=is_method,
            receiver_type=receiver_type
        )

    def _get_enclosing_function(self, node: ast.AST, content: str) -> Optional[str]:
        """Find the function that contains the given node."""
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return None

        # Find all function definitions and their ranges
        for child in ast.walk(tree):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Check if node is within this function's range
                func_line = child.lineno
                func_end = child.end_lineno or child.lineno + 100

                # Get the line of the target node
                target_line = getattr(node, 'lineno', None)
                if target_line and func_line <= target_line <= func_end:
                    # Make sure the node is actually in this function, not just in range
                    for inner in ast.walk(child):
                        if inner is node:
                            return child.name
                        # Check if the node is a child of this inner node
                        if target_line == getattr(inner, 'lineno', 0):
                            for grandchild in ast.walk(inner):
                                if grandchild is node:
                                    return child.name
        return None

    def _get_attr_name(self, node: ast.Attribute) -> str:
        """Get the full attribute name from an Attribute node."""
        parts = []
        current = node
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
        return ".".join(reversed(parts))

    def _find_parent_function(self, tree: ast.AST, target: ast.AST) -> Optional[str]:
        """Recursively find the parent function containing the target node."""
        # First find the path from tree to target
        path_to_target: list[ast.AST] = []

        def find_path(node: ast.AST) -> bool:
            if node is target:
                path_to_target.append(node)
                return True
            for child in ast.iter_child_nodes(node):
                if find_path(child):
                    path_to_target.append(node)
                    return True
            return False

        find_path(tree)

        # Now walk backward through the path to find FunctionDef
        for ancestor in path_to_target:
            if isinstance(ancestor, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return ancestor.name

        return None

    def build_from_file(self, path: Path, content: str) -> CallGraph:
        """Build call graph for a single file.
        
        Args:
            path: Path to the file.
            content: File content.
            
        Returns:
            CallGraph for the file.
        """
        return self.build([path], {path: content})

    def find_external_calls(
        self,
        graph: CallGraph,
        external_modules: set[str]
    ) -> list[CallSite]:
        """Find calls to external modules (not defined in the project).
        
        Args:
            graph: The call graph to analyze.
            external_modules: Set of external module names to consider.
            
        Returns:
            List of CallSite objects that call external modules.
        """
        external_calls: list[CallSite] = []

        # Get all defined functions
        defined_funcs: set[str] = set()
        for edges in graph.callees.values():
            for edge in edges:
                defined_funcs.add(edge.callee)

        for edge in graph.edges:
            callee = edge.callee
            if callee not in defined_funcs:
                # This is either an external call or builtin
                if not self.resolver._resolve_builtin(callee):
                    external_calls.append(edge)

        return external_calls

    def analyze_dynamic_dispatch(
        self,
        graph: CallGraph,
        method_name: str
    ) -> list[MethodInfo]:
        """Find all implementations of a method across the project.
        
        Args:
            graph: The call graph.
            method_name: Name of the method to find implementations of.
            
        Returns:
            List of MethodInfo for all implementations.
        """
        implementations: list[MethodInfo] = []

        for class_name, methods in graph.methods.items():
            for method in methods:
                if method.name == method_name:
                    implementations.append(method)

        return implementations

    def find_callbacks(self, graph: CallGraph) -> list[CallSite]:
        """Find common callback patterns.
        
        Identifies function references passed as arguments, which often
        indicate callback patterns.
        
        Returns:
            List of CallSite objects that appear to be callbacks.
        """
        callbacks: list[CallSite] = []

        # Common callback argument names
        callback_names = {
            "callback", "cb", "handler", "on_*", "before_*", "after_*",
            "process_*", "transform_*", "filter_*"
        }

        for edge in graph.edges:
            # Heuristic: callbacks are often passed as arguments
            # Check if the callee name suggests callback behavior
            for pattern in callback_names:
                if pattern.startswith("*"):
                    if edge.callee.endswith(pattern[1:]):
                        callbacks.append(edge)
                        break
                elif edge.callee == pattern or edge.callee.startswith(pattern):
                    callbacks.append(edge)
                    break

        return callbacks

    def get_call_depth(self, graph: CallGraph, func_name: str) -> int:
        """Calculate the maximum call depth for a function.
        
        Args:
            graph: The call graph.
            func_name: Function to analyze.
            
        Returns:
            Maximum depth of function calls (0 if no calls).
        """
        def calc_depth(current: str, visited: set[str]) -> int:
            if current in visited:
                return 0
            visited.add(current)

            callees = graph.callees.get(current, [])
            if not callees:
                return 0

            max_child_depth = 0
            for callee in callees:
                depth = calc_depth(callee.callee, visited.copy())
                max_child_depth = max(max_child_depth, depth)

            return 1 + max_child_depth

        return calc_depth(func_name, set())

    def find_hot_paths(
        self,
        graph: CallGraph,
        min_calls: int = 3
    ) -> list[tuple[list[str], int]]:
        """Find frequently traversed call paths.
        
        Args:
            graph: The call graph.
            min_calls: Minimum number of calls to consider a path as "hot".
            
        Returns:
            List of (path, call_count) tuples sorted by call count.
        """
        # Count call frequencies
        call_counts: dict[str, int] = defaultdict(int)
        for edge in graph.edges:
            call_counts[edge.callee] += 1

        # Find hot paths
        hot_paths: list[tuple[list[str], int]] = []
        for callee, count in call_counts.items():
            if count >= min_calls:
                path = self.find_path(list(graph.callees.keys())[0], callee)
                if path:
                    hot_paths.append((path, count))

        return sorted(hot_paths, key=lambda x: x[1], reverse=True)
