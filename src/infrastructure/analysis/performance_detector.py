"""Performance anti-pattern detectors using tree-sitter AST analysis.

Detects common performance issues:
- O(N²) nested loops
- Memory leaks (unbounded growth, missing cleanup)
- Deadlocks and race conditions
- Unbounded data structures
- Blocking I/O in async code
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer

# Pattern definitions for performance anti-patterns
LOOP_ITERABLE_PATTERNS = frozenset({
    "items", "elements", "data", "list", "array", "results",
    "items", "entries", "objects", "values", "records",
})

COLLECTION_METHODS = frozenset({
    "append", "extend", "add", "insert", "update",
    "put", "push", "enqueue",
})


class PerformanceDetector:
    """Detect performance anti-patterns using AST analysis."""

    def __init__(self, indexer: "SafeTreeSitterIndexer | None" = None) -> None:
        self.indexer = indexer

    def detect_on2_loops(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect O(N²) nested loop patterns.

        Detects:
        - Nested for loops over same collection
        - Nested loops where inner loop iterates over outer loop's result
        - List comprehensions inside loops over the same data
        """
        findings = []

        if language != "python":
            return self._detect_on2_regex(content)

        try:
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            findings = self._find_nested_loops(root, content)

        except ImportError:
            findings = self._detect_on2_regex(content)
        except Exception:
            findings = self._detect_on2_regex(content)

        return findings

    def _find_nested_loops(
        self,
        root: Any,
        content: str,
    ) -> list[dict[str, Any]]:
        """Find nested loop patterns using AST traversal."""
        findings = []

        def check_nested_loops(node: Any) -> None:
            if node.type in ("for_statement", "while_statement"):
                outer_info = self._extract_loop_info(node, content)
                if outer_info:
                    # Find all nested loops by searching within this loop's block
                    self._search_for_nested_loops(node, outer_info, findings, content)

            for child in node.children:
                check_nested_loops(child)

        check_nested_loops(root)
        return findings

    def _search_for_nested_loops(
        self,
        loop_node: Any,
        outer_info: dict[str, Any],
        findings: list,
        content: str,
    ) -> None:
        """Search for nested loops within a loop's block."""
        for child in loop_node.children:
            if child.type in ("for_statement", "while_statement"):
                inner_info = self._extract_loop_info(child, content)
                if inner_info:
                    # Check if patterns suggest O(N²)
                    if self._is_on2_pattern(outer_info, inner_info):
                        line_no = loop_node.start_point[0] + 1
                        findings.append({
                            "rule_id": "PERF001",
                            "severity": "HIGH",
                            "line": line_no,
                            "message": "O(N²) detected: nested loops over similar iterables",
                            "confidence": 0.85,
                            "old_code": self._get_snippet(content, line_no, lines=10),
                            "new_code": "# Consider using:\n# - dict/set for O(1) lookups\n# - itertools.product() for cross-product\n# - vectorized operations (NumPy/pandas)",
                            "explanation": (
                                "Nested loops iterating over similar collections result in O(N²) "
                                "complexity. Consider using hash-based lookups (dict/set) or "
                                "built-in functions that are optimized for bulk operations."
                            ),
                            "detection_method": "ast",
                        })
            elif child.type == "block":
                # Recursively search inside blocks
                self._search_for_nested_loops(child, outer_info, findings, content)

    def _extract_loop_info(self, node: Any, content: str) -> dict[str, Any] | None:
        """Extract information about a loop's iterable."""
        info = {"iterable": "", "variable": "", "type": node.type}

        # For loops have structure: for <var> in <iterable>:
        # Children: for, identifier (var), in, identifier (iterable), :, block
        prev_is_in = False
        for child in node.children:
            if prev_is_in and child.type == "identifier":
                info["iterable"] = child.text.decode("utf-8")
                break
            if child.type == "identifier":
                info["variable"] = child.text.decode("utf-8")
            if child.type == "in":
                prev_is_in = True
        return info

    def _is_on2_pattern(
        self,
        outer: dict[str, Any],
        inner: dict[str, Any],
    ) -> bool:
        """Determine if nested loops form an O(N²) pattern."""
        outer_var = outer.get("variable", "").lower()
        inner_var = inner.get("variable", "").lower()
        outer_iter = outer.get("iterable", "").lower()
        inner_iter = inner.get("iterable", "").lower()

        # Same variable names suggest same data source
        if outer_var and outer_var == inner_var:
            return True

        # Same iterable names (clear O(N²) pattern)
        if outer_iter and outer_iter == inner_iter:
            return True

        # Similar iterable names with common patterns
        if outer_iter and inner_iter:
            # Check if both use 'items' or similar generic names
            for pattern in LOOP_ITERABLE_PATTERNS:
                if pattern in outer_iter and pattern in inner_iter:
                    return True
            # Check if both are the same variable
            if outer_var and inner_var and outer_var == inner_var:
                return True
            # Check if inner uses outer variable
            if outer_var and outer_var in inner_iter:
                return True

        return False

    def detect_memory_leak(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect patterns that can cause memory leaks.

        Detects:
        - Global lists/dicts that grow unbounded
        - Missing cleanup in __init__ counterparts
        - Unbounded cache/cache without eviction
        - Event listeners without removal
        """
        findings = []

        if language != "python":
            return self._detect_memory_leak_regex(content)

        try:
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            findings = self._find_memory_leak_patterns(root, content)

        except ImportError:
            findings = self._detect_memory_leak_regex(content)
        except Exception:
            findings = self._detect_memory_leak_regex(content)

        return findings

    def _find_memory_leak_patterns(
        self,
        root: Any,
        content: str,
    ) -> list[dict[str, Any]]:
        """Find memory leak patterns using AST."""
        findings = []

        # Track module-level globals that grow
        module_globals: dict[str, dict] = {}

        def analyze_assignment(node: Any) -> None:
            """Analyze module-level assignments for potential leaks."""
            if node.type == "assignment":
                left = node.child_by_field_name("left")
                if left and left.type == "identifier":
                    var_name = left.text.decode("utf-8")
                    right = node.child_by_field_name("right")

                    # Check if initialized to mutable type
                    if right:
                        right_text = right.text.decode("utf-8", errors="replace")
                        if any(mutable in right_text for mutable in ["[]", "{}", "dict()", "list()"]):
                            module_globals[var_name] = {
                                "name": var_name,
                                "line": node.start_point[0] + 1,
                                "initial": right_text[:50],
                            }

        def analyze_function(node: Any) -> None:
            """Analyze functions for additions to module globals."""
            if node.type not in ("function_definition",):
                return

            func_name = ""
            for child in node.children:
                if child.type == "identifier":
                    func_name = child.text.decode("utf-8")
                    break

            # Check body for additions to known globals
            for child in node.children:
                if child.type == "block":
                    body_text = child.text.decode("utf-8")
                    for global_name in module_globals:
                        # Check for .append, .extend, etc. on global
                        if f"{global_name}.append" in body_text or f"{global_name}.extend" in body_text:
                            line_no = node.start_point[0] + 1
                            findings.append({
                                "rule_id": "PERF002",
                                "severity": "HIGH",
                                "line": line_no,
                                "message": f"Potential memory leak: '{global_name}' grows unbounded",
                                "confidence": 0.82,
                                "old_code": self._get_snippet(content, line_no, lines=10),
                                "new_code": "# Add LRU cache or size limit:\n# from functools import lru_cache\n# @lru_cache(maxsize=1000)",
                                "explanation": (
                                    f"Module-level variable '{global_name}' is appended to without size limits. "
                                    "This can cause memory leaks in long-running processes. "
                                    "Use LRU caches, size-bounded collections, or explicit cleanup."
                                ),
                                "detection_method": "ast",
                            })

        def analyze_class(node: Any) -> None:
            """Analyze class definitions for leak patterns."""
            if node.type in ("class_definition",):
                class_name = ""
                has_init = False
                global_attrs = []
                methods_with_add = []

                # Get class name
                for child in node.children:
                    if child.type == "identifier":
                        class_name = child.text.decode("utf-8")
                        break

                # Analyze methods
                for child in node.children:
                    if child.type in ("function_definition",):
                        method_info = self._analyze_method(child)
                        if method_info["is_init"]:
                            has_init = True
                        if method_info["adds_to_self"]:
                            for attr in method_info["added_attrs"]:
                                if attr not in global_attrs:
                                    global_attrs.append(attr)
                        methods_with_add.append(method_info)

                # Check for leak patterns
                if global_attrs and not has_init:
                    line_no = node.start_point[0] + 1
                    findings.append({
                        "rule_id": "PERF002",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": f"Class '{class_name}' has mutable class-level attributes without clear initialization",
                        "confidence": 0.78,
                        "old_code": self._get_snippet(content, line_no, lines=15),
                        "new_code": "# Add __init__ to initialize attrs:\n# def __init__(self):\n#     self.attrs = []",
                        "explanation": (
                            "Mutable class-level attributes can cause memory leaks if they accumulate "
                            "data across instances. Ensure proper initialization in __init__ and consider "
                            "using instance attributes instead of class attributes."
                        ),
                        "detection_method": "ast",
                    })

                # Check for unbounded caches
                for method in methods_with_add:
                    if method["adds_to_global"] or method["uses_unbounded_cache"]:
                        line_no = node.start_point[0] + 1
                        findings.append({
                            "rule_id": "PERF002",
                            "severity": "HIGH",
                            "line": line_no,
                            "message": "Potential unbounded growth - data added without size limits",
                            "confidence": 0.82,
                            "old_code": self._get_snippet(content, line_no, lines=15),
                            "new_code": "# Add LRU cache or size limit:\n# from functools import lru_cache\n# @lru_cache(maxsize=1000)",
                            "explanation": (
                                "Collections that grow without limits (lists, dicts) can cause memory leaks "
                                "in long-running processes. Use LRU caches, size-bounded collections, "
                                "or explicit cleanup mechanisms."
                            ),
                            "detection_method": "ast",
                        })

        def traverse(node: Any) -> None:
            # At module level, analyze assignments and functions
            if node.type in ("assignment",):
                analyze_assignment(node)
            elif node.type in ("function_definition",):
                analyze_function(node)
                # Continue to find nested code
                for child in node.children:
                    traverse(child)
            else:
                analyze_class(node)
                for child in node.children:
                    traverse(child)

        traverse(root)
        return findings

    def _analyze_method(self, node: Any) -> dict[str, Any]:
        """Analyze a method for potential leak patterns."""
        info = {
            "name": "",
            "is_init": False,
            "adds_to_self": False,
            "adds_to_global": False,
            "added_attrs": [],
            "uses_unbounded_cache": False,
        }

        for child in node.children:
            if child.type == "identifier":
                info["name"] = child.text.decode("utf-8")
                if info["name"] == "__init__":
                    info["is_init"] = True

        # Check for attribute additions
        code = node.text.decode("utf-8")
        if ".append" in code or ".extend" in code or ".add" in code:
            info["adds_to_self"] = True
            # Check if adding to self
            if "self." in code:
                info["adds_to_global"] = True

        # Check for unbounded cache patterns
        if "@lru_cache" not in code and ("cache" in code.lower() or "memo" in code.lower()):
            if "maxsize" not in code:
                info["uses_unbounded_cache"] = True

        return info

    def detect_deadlock_risk(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect potential deadlock and race condition patterns.

        Detects:
        - Nested locks without timeout
        - Lock acquisition order inconsistency
        - Missing async/await in critical sections
        - Thread-unsafe shared state access
        """
        findings = []

        if language != "python":
            return self._detect_deadlock_regex(content)

        try:
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            findings = self._find_deadlock_patterns(root, content)

        except ImportError:
            findings = self._detect_deadlock_regex(content)
        except Exception:
            findings = self._detect_deadlock_regex(content)

        return findings

    def _find_deadlock_patterns(
        self,
        root: Any,
        content: str,
    ) -> list[dict[str, Any]]:
        """Find deadlock patterns using AST."""
        findings = []

        def check_with_statement(node: Any) -> None:
            if node.type == "with":
                code = node.text.decode("utf-8")

                # Check for nested locks
                if code.count("Lock()") > 1 or code.count("acquire") > 1:
                    line_no = node.start_point[0] + 1
                    findings.append({
                        "rule_id": "PERF003",
                        "severity": "CRITICAL",
                        "line": line_no,
                        "message": "Potential deadlock: multiple locks acquired simultaneously",
                        "confidence": 0.80,
                        "old_code": self._get_snippet(content, line_no, lines=10),
                        "new_code": "# Use timeout or lock ordering:\n# with timeout(lock1, 5) and lock2:",
                        "explanation": (
                            "Acquiring multiple locks without a consistent order can cause deadlocks. "
                            "Use timeouts, consistent lock ordering, or lock-free data structures."
                        ),
                        "detection_method": "ast",
                    })

                # Check for blocking operations in async code
                if "async def" in content:
                    blocking_patterns = ["time.sleep", ".join(", "Lock.acquire"]
                    for pattern in blocking_patterns:
                        if pattern in code and "await" not in code.split(pattern)[0][-50:]:
                            findings.append({
                                "rule_id": "PERF003",
                                "severity": "HIGH",
                                "line": line_no,
                                "message": f"Blocking operation '{pattern}' in async context without await",
                                "confidence": 0.85,
                                "old_code": code[:100],
                                "new_code": "# Use async equivalent:\n# await asyncio.sleep()\n# await lock.acquire()",
                                "explanation": (
                                    "Blocking operations in async code can block the entire event loop. "
                                    "Use asyncio-compatible alternatives (asyncio.sleep, asyncio.Lock)."
                                ),
                                "detection_method": "ast",
                            })

        def traverse(node: Any) -> None:
            check_with_statement(node)
            for child in node.children:
                traverse(child)

        traverse(root)
        return findings

    def detect_blocking_io(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect blocking I/O operations in async code."""
        findings = []

        if language != "python":
            return findings

        blocking_patterns = [
            ("requests.get", "aiohttp", "async HTTP"),
            ("requests.post", "aiohttp", "async HTTP"),
            ("open(", "aiofiles", "async file I/O"),
            ("os.path.exists", "pathlib async", "async path ops"),
            ("time.sleep", "asyncio.sleep", "async sleep"),
            (".join()", "asyncio.gather", "concurrent ops"),
        ]

        lines = content.split("\n")
        in_async = False
        async_func_start = 0

        for i, line in enumerate(lines, 1):
            if "async def" in line:
                in_async = True
                async_func_start = i
            elif in_async and line.strip().startswith("def "):
                in_async = False

            if in_async:
                for blocking, alternative, desc in blocking_patterns:
                    if blocking in line and "await" not in line:
                        findings.append({
                            "rule_id": "PERF004",
                            "severity": "MEDIUM",
                            "line": i,
                            "message": f"Blocking operation '{blocking}' in async function",
                            "confidence": 0.75,
                            "old_code": line.strip(),
                            "new_code": f"# Use {alternative} for {desc}",
                            "explanation": (
                                f"'{blocking}' is blocking and will pause the entire event loop. "
                                f"Use '{alternative}' for non-blocking {desc}."
                            ),
                            "detection_method": "regex",
                        })
                        break

        return findings

    def detect_unbounded_recursion(
        self,
        content: str,
        language: str,
    ) -> list[dict[str, Any]]:
        """Detect unbounded recursion without base case checks."""
        findings = []

        if language != "python":
            return findings

        try:
            import tree_sitter_languages

            parser = tree_sitter_languages.get_parser("python")
            tree = parser.parse(content.encode("utf-8"))
            root = tree.root_node

            findings = self._find_recursive_functions(root, content)

        except ImportError:
            findings = self._detect_recursion_regex(content)
        except Exception:
            findings = self._detect_recursion_regex(content)

        return findings

    def _find_recursive_functions(
        self,
        root: Any,
        content: str,
    ) -> list[dict[str, Any]]:
        """Find recursive functions without depth checks."""
        findings = []

        def analyze_function(node: Any) -> None:
            if node.type not in ("function_definition",):
                return

            func_name = ""
            is_recursive = False
            has_depth_check = False
            body_text = ""

            # Get function name from identifier child
            for child in node.children:
                if child.type == "identifier":
                    func_name = child.text.decode("utf-8")
                    break

            # Get function body only (find the block child)
            for child in node.children:
                if child.type == "block":
                    body_text = child.text.decode("utf-8")
                    break

            if not body_text:
                body_text = node.text.decode("utf-8")

            line_no = node.start_point[0] + 1

            # Check if recursive - look for self-call in body only
            # Pattern: function_name followed by ( but NOT as part of def line
            if func_name and body_text:
                # Look for function calls that aren't in a string
                import re
                # Match function_name followed by ( but not preceded by 'def ' or '='
                recursive_pattern = rf"(?<!def\s)(?<!=\s){re.escape(func_name)}\s*\("
                if re.search(recursive_pattern, body_text):
                    is_recursive = True

            # Check for depth/limit check
            depth_patterns = [
                r"depth\s*[><=]", r"max_depth", r"limit\s*[><=]",
                r"sys\.getrecursionlimit", r"RecursionError",
                r"sys\.setrecursionlimit"
            ]
            if any(re.search(p, body_text, re.IGNORECASE) for p in depth_patterns):
                has_depth_check = True

            # Flag if recursive without depth check
            if is_recursive and not has_depth_check:
                findings.append({
                    "rule_id": "PERF005",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": f"Unbounded recursion in '{func_name}' without depth limit",
                    "confidence": 0.80,
                    "old_code": body_text[:150] if body_text else "",
                    "new_code": (
                        "# Add depth parameter:\n"
                        f"# def {func_name}(..., depth=0, max_depth=1000):\n"
                        "#     if depth > max_depth:\n"
                        "#         raise RecursionError('max depth exceeded')\n"
                        "#     return inner_call(depth+1)"
                    ),
                    "explanation": (
                        f"Function '{func_name}' calls itself without a depth limit. "
                        "This can cause stack overflow for deep recursion. "
                        "Add a depth parameter and check against a maximum."
                    ),
                    "detection_method": "ast",
                })

        def traverse(node: Any) -> None:
            analyze_function(node)
            for child in node.children:
                traverse(child)

        traverse(root)
        return findings

    # ─── Regex Fallback Methods ────────────────────────────────────────────────

    def _detect_on2_regex(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for O(N²) detection."""
        findings = []

        # Find nested for loops
        nested_pattern = re.compile(
            r"for\s+\w+\s+in\s+.*?:\s*\n\s*for\s+\w+\s+in\s+",
            re.DOTALL
        )

        for match in nested_pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            context = content[max(0, match.start()-100):match.end()+200]

            # Check if iterating over similar patterns
            if any(p in context.lower() for p in ["items", "data", "list", "array"]):
                findings.append({
                    "rule_id": "PERF001",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": "Potential O(N²): nested loops over similar collections",
                    "confidence": 0.70,
                    "old_code": match.group(0)[:100],
                    "new_code": "# Consider dict/set for O(1) lookups",
                    "explanation": "Nested loops over similar collections are often O(N²).",
                    "detection_method": "regex_fallback",
                })

        return findings

    def _detect_memory_leak_regex(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for memory leak detection."""
        findings = []

        # Find unbounded cache patterns
        cache_pattern = re.compile(r"@\w*cache\w*|memo\[|cache\[")

        for match in cache_pattern.finditer(content):
            line_no = content[:match.start()].count("\n") + 1
            line = content.split("\n")[line_no - 1]

            # Check if maxsize is specified
            if "maxsize" not in line and "LRU" not in line.upper():
                findings.append({
                    "rule_id": "PERF002",
                    "severity": "HIGH",
                    "line": line_no,
                    "message": "Unbounded cache without size limit",
                    "confidence": 0.68,
                    "old_code": line.strip(),
                    "new_code": "# Add @lru_cache(maxsize=1000) or similar",
                    "explanation": "Unbounded caches can grow indefinitely causing memory leaks.",
                    "detection_method": "regex_fallback",
                })

        return findings

    def _detect_deadlock_regex(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for deadlock detection."""
        findings = []

        # Find lock acquisitions
        lock_pattern = re.compile(r"\.acquire\(\)|with\s+.*lock|Lock\(\)")

        lock_count = len(lock_pattern.findall(content))
        if lock_count > 1:
            matches = list(lock_pattern.finditer(content))
            for i, match in enumerate(matches[:-1]):
                line_no = content[:match.start()].count("\n") + 1
                next_line = content.split("\n")[line_no - 1 + content[match.start():].count("\n")]
                if "Lock()" in next_line or ".acquire()" in next_line:
                    findings.append({
                        "rule_id": "PERF003",
                        "severity": "CRITICAL",
                        "line": line_no,
                        "message": "Multiple lock acquisitions - potential deadlock risk",
                        "confidence": 0.65,
                        "old_code": content.split("\n")[line_no - 1].strip(),
                        "new_code": "# Use consistent lock ordering or timeouts",
                        "explanation": "Multiple lock acquisitions without consistent ordering can deadlock.",
                        "detection_method": "regex_fallback",
                    })

        return findings

    def _detect_recursion_regex(self, content: str) -> list[dict[str, Any]]:
        """Regex fallback for recursion detection."""
        findings = []

        # Find recursive calls
        func_pattern = re.compile(r"def\s+(\w+)\s*\([^)]*\):")
        for match in func_pattern.finditer(content):
            func_name = match.group(1)
            func_start = match.start()
            line_no = content[:func_start].count("\n") + 1

            # Find function body
            next_func = func_pattern.search(content[match.end():])
            if next_func:
                func_end = match.end() + next_func.start()
            else:
                func_end = len(content)

            func_body = content[match.start():match.end() + 500]

            # Check for recursive call
            if f" {func_name}(" in func_body:
                # Check for depth limit
                if not any(p in func_body for p in ["depth", "limit", "max_depth", "sys."]):
                    findings.append({
                        "rule_id": "PERF005",
                        "severity": "HIGH",
                        "line": line_no,
                        "message": f"Function '{func_name}' is recursive without depth limit",
                        "confidence": 0.65,
                        "old_code": match.group(0),
                        "new_code": f"# Add depth parameter to {func_name}(..., depth=0)",
                        "explanation": "Unbounded recursion can cause stack overflow.",
                        "detection_method": "regex_fallback",
                    })

        return findings

    def _get_snippet(
        self,
        content: str,
        line_no: int,
        lines: int = 5,
    ) -> str:
        """Extract code snippet around a line number."""
        content_lines = content.split("\n")
        start = max(0, line_no - 1)
        end = min(len(content_lines), start + lines)
        return "\n".join(content_lines[start:end])
