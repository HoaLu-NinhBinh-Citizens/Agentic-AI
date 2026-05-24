"""Architecture Preservation - Enforces architecture constraints during modifications.

PROBLEM:
AI modify code nhưng làm hỏng architecture:
- Thay đổi API mà không update callers
- Xóa file mà vẫn có imports
- Modify shared state mà không understand dependencies
- Refactor class mà break inheritance
- Thay đổi const mà affect compile-time behavior

SOLUTION:
┌─────────────────────────────────────────────────────────────────┐
│                  ArchitecturePreservation                            │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Architecture Graph                                          │  │
│  │  - Call dependencies (who calls who)                      │  │
│  │  - Import dependencies (who imports who)                   │  │
│  │  - Data dependencies (who shares data)                   │  │
│  │  - Inheritance hierarchy                                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Constraint Rules                                           │  │
│  │  - Preserved APIs (cannot change signature)                │  │
│  │  - Preserved files (cannot delete)                         │  │
│  │  - Preserved behaviors (cannot break tests)               │  │
│  │  - Dependency boundaries (cannot cross layers)           │  │
│  └───────────────────────────────────────────────────────────┘  │
│                           ↓                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Change Validator                                          │  │
│  │  1. Check if change violates constraints                   │  │
│  │  2. Find all affected components                           │  │
│  │  3. Validate cascading updates needed                      │  │
│  │  4. Warn or block dangerous changes                        │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

KEY FEATURES:
1. Dependency graph - understand relationships
2. Change impact analysis - what breaks if I change this
3. Constraint enforcement - preserve critical components
4. Layer boundary enforcement - don't cross layers
5. Regression detection - detect when tests break
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class DependencyType(Enum):
    """Types of dependencies."""
    CALL = "call"           # Function call
    IMPORT = "import"       # Module import
    INHERIT = "inherit"     # Class inheritance
    DATA = "data"          # Shared data/globals
    CONFIG = "config"      # Configuration dependency
    SIDE_EFFECT = "side_effect"  # Side effects


@dataclass
class Dependency:
    """Represents a dependency between components."""
    source: str  # e.g., "src/app/main.c"
    target: str  # e.g., "include/driver.h"
    dep_type: DependencyType
    symbol: Optional[str] = None  # e.g., "HAL_GPIO_Init"
    line: Optional[int] = None


@dataclass
class ChangeImpact:
    """Impact of a proposed change."""
    change_type: str
    target: str
    severity: str  # "breaking", "major", "minor", "safe"
    affected_files: list[str] = field(default_factory=list)
    affected_apis: list[str] = field(default_factory=list)
    affected_tests: list[str] = field(default_factory=list)
    cascading_updates_needed: list[str] = field(default_factory=list)
    breaking_change: bool = False
    explanation: str = ""


@dataclass
class ArchitectureConstraint:
    """Constraint on architecture."""
    constraint_id: str
    description: str
    applies_to: list[str]  # File patterns
    prohibits: list[str]    # Actions prohibited
    requires: Optional[list[str]] = None  # If action X, must also do Y
    severity: str = "error"  # "error", "warning", "info"


class LayerBoundary(Enum):
    """Architecture layers."""
    DOMAIN = "domain"           # Business logic
    APPLICATION = "application"  # Use cases, workflows
    INFRASTRUCTURE = "infrastructure"  # External systems
    INTERFACE = "interface"     # User-facing interfaces
    CORE = "core"              # Core utilities, types


@dataclass
class LayerRule:
    """Rule for layer boundaries."""
    from_layer: LayerBoundary
    to_layer: LayerBoundary
    allowed: bool
    reason: str = ""


class DependencyGraph:
    """
    Dependency graph for architecture analysis.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, dict[str, Any]] = {}
        self._edges: list[Dependency] = []
        self._api_signatures: dict[str, str] = {}  # API name -> signature hash

    def add_file(self, file_path: str, content: Optional[str] = None) -> None:
        """Add file to graph."""
        self._nodes[file_path] = {
            "path": file_path,
            "content_hash": hashlib.md5((content or "").encode()).hexdigest(),
            "apis": [],
            "imports": [],
        }

    def add_dependency(self, source: str, target: str, dep_type: DependencyType, symbol: Optional[str] = None) -> None:
        """Add dependency edge."""
        dep = Dependency(
            source=source,
            target=target,
            dep_type=dep_type,
            symbol=symbol,
        )
        self._edges.append(dep)

    def get_dependents(self, file_path: str) -> list[Dependency]:
        """Get all files that depend on this file."""
        return [d for d in self._edges if d.target == file_path]

    def get_dependencies(self, file_path: str) -> list[Dependency]:
        """Get all files this file depends on."""
        return [d for d in self._edges if d.source == file_path]

    def get_callers(self, api_name: str) -> list[str]:
        """Get all files that call this API."""
        return [
            d.source for d in self._edges
            if d.symbol == api_name and d.dep_type == DependencyType.CALL
        ]

    def find_cycles(self) -> list[list[str]]:
        """Find dependency cycles."""
        cycles = []
        visited = set()
        path = []

        def dfs(node: str) -> None:
            if node in path:
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for dep in self.get_dependencies(node):
                dfs(dep.target)

            path.pop()

        for node in self._nodes:
            dfs(node)

        return cycles

    def get_transitive_dependents(self, file_path: str) -> set[str]:
        """Get all files that transitively depend on this file."""
        result = set()

        def traverse(current: str) -> None:
            for dep in self.get_dependents(current):
                if dep.source not in result:
                    result.add(dep.source)
                    traverse(dep.source)

        traverse(file_path)
        return result


class ArchitecturePreservation:
    """
    Preserves architecture during code modifications.

    Prevents:
    - Breaking API contracts
    - Crossing layer boundaries
    - Deleting used files
    - Modifying preserved components
    """

    def __init__(self) -> None:
        self._graph = DependencyGraph()
        self._constraints: list[ArchitectureConstraint] = []
        self._preserved_files: set[str] = set()
        self._preserved_apis: dict[str, str] = {}  # API -> signature
        self._layer_rules: list[LayerRule] = []
        self._project_root = ""

        self._initialize_default_constraints()
        self._initialize_layer_rules()

    def _initialize_default_constraints(self) -> None:
        """Initialize default architecture constraints."""
        # Cannot modify HAL signatures (preserved API)
        self._preserved_apis = {
            "HAL_GPIO_Init": "void HAL_GPIO_Init(GPIO_TypeDef*, uint16_t, GPIO_InitTypeDef*)",
            "HAL_UART_Init": "HAL_StatusTypeDef HAL_UART_Init(UART_HandleTypeDef*)",
            "HAL_SPI_Init": "HAL_StatusTypeDef HAL_SPI_Init(SPI_HandleTypeDef*)",
            "HAL_TIM_Base_Init": "HAL_StatusTypeDef HAL_TIM_Base_Init(TIM_HandleTypeDef*)",
            "main": "int main(void)",
        }

    def _initialize_layer_rules(self) -> None:
        """Initialize layer boundary rules."""
        # Domain should not depend on Infrastructure
        self._layer_rules = [
            LayerRule(LayerBoundary.DOMAIN, LayerBoundary.INFRASTRUCTURE, False,
                     "Domain layer should not depend on infrastructure"),
            LayerRule(LayerBoundary.APPLICATION, LayerBoundary.INTERFACE, True),
            LayerRule(LayerBoundary.CORE, LayerBoundary.DOMAIN, True),
        ]

    def set_project_root(self, root: str) -> None:
        """Set project root for path analysis."""
        self._project_root = root

    def preserve_file(self, file_path: str) -> None:
        """Mark file as preserved (cannot delete/modify)."""
        self._preserved_files.add(file_path)

    def preserve_api(self, api_name: str, signature: Optional[str] = None) -> None:
        """Mark API as preserved (cannot change signature)."""
        self._preserved_apis[api_name] = signature or "preserved"

    def add_constraint(self, constraint: ArchitectureConstraint) -> None:
        """Add architecture constraint."""
        self._constraints.append(constraint)

    def build_from_source(self, source_files: dict[str, str]) -> None:
        """Build dependency graph from source files."""
        for file_path, content in source_files.items():
            self._graph.add_file(file_path, content)

            # Parse imports
            imports = self._parse_imports(content)
            for imp in imports:
                self._graph.add_dependency(
                    file_path, imp, DependencyType.IMPORT
                )

            # Parse function calls
            calls = self._parse_calls(content)
            for call in calls:
                self._graph.add_dependency(
                    file_path, "", DependencyType.CALL, symbol=call
                )

    def _parse_imports(self, content: str) -> list[str]:
        """Parse import/include statements."""
        imports = []

        # C/C++ includes
        for match in re.finditer(r'#include\s*[<"]([^>"]+)[>"]', content):
            imports.append(match.group(1))

        # Python imports
        for match in re.finditer(r'^import\s+(\S+)', content, re.MULTILINE):
            imports.append(match.group(1))
        for match in re.finditer(r'^from\s+(\S+)\s+import', content, re.MULTILINE):
            imports.append(match.group(1))

        return imports

    def _parse_calls(self, content: str) -> list[str]:
        """Parse function calls."""
        calls = []

        # Function calls like HAL_*, handle_*, etc.
        for match in re.finditer(r'\b([A-Z][A-Za-z0-9_]+)\s*\(', content):
            calls.append(match.group(1))

        return calls

    def analyze_change(self, change_type: str, target: str) -> ChangeImpact:
        """
        Analyze impact of proposed change.

        Args:
            change_type: "delete", "modify", "rename"
            target: file or API name

        Returns:
            ChangeImpact with details
        """
        impact = ChangeImpact(
            change_type=change_type,
            target=target,
            severity="safe",
        )

        # Check preserved files
        if change_type == "delete" and target in self._preserved_files:
            impact.severity = "breaking"
            impact.breaking_change = True
            impact.explanation = f"Cannot delete preserved file: {target}"
            return impact

        # Check preserved APIs
        if change_type == "modify" and target in self._preserved_apis:
            callers = self._graph.get_callers(target)
            if callers:
                impact.severity = "breaking"
                impact.affected_files = callers
                impact.breaking_change = True
                impact.explanation = f"Cannot modify preserved API: {target} (used by {len(callers)} files)"
                impact.cascading_updates_needed = [
                    f"Update callers of {target}: {', '.join(callers[:5])}"
                ]
                return impact

        # Check file dependencies
        if change_type == "delete":
            dependents = list(self._graph.get_transitive_dependents(target))
            if dependents:
                impact.severity = "breaking"
                impact.breaking_change = True
                impact.affected_files = dependents
                impact.explanation = f"Deleting {target} will break {len(dependents)} files"
                return impact

        # Check for cycles
        if change_type == "modify":
            cycles = self._graph.find_cycles()
            if cycles:
                impact.severity = "major"
                impact.explanation = f"Dependency cycle detected: {' -> '.join(cycles[0][:4])}"

        return impact

    def validate_modification(
        self,
        file_path: str,
        new_signature: str,
    ) -> tuple[bool, list[str]]:
        """
        Validate if file/API modification is safe.

        Returns:
            (is_safe, warnings)
        """
        warnings = []

        # Check preserved APIs
        api_name = self._extract_api_name(file_path)
        if api_name and api_name in self._preserved_apis:
            old_sig = self._preserved_apis[api_name]
            if new_signature != old_sig and old_sig != "preserved":
                warnings.append(
                    f"Changing preserved API '{api_name}' signature from '{old_sig}' to '{new_signature}'"
                )

        # Check affected files
        callers = self._graph.get_callers(api_name) if api_name else []
        if callers:
            warnings.append(
                f"Modification will affect {len(callers)} callers: {', '.join(callers[:3])}"
            )

        return len(warnings) == 0 or all("affected" not in w for w in warnings), warnings

    def _extract_api_name(self, file_path: str) -> Optional[str]:
        """Extract API/function name from file path."""
        # Simple heuristic
        name = file_path.split("/")[-1]
        name = name.replace(".c", "").replace(".h", "")
        return name if name.startswith("HAL_") or name.startswith("handle_") else None

    def get_affected_tests(
        self,
        changed_files: list[str],
        test_map: dict[str, list[str]],
    ) -> list[str]:
        """Get tests affected by file changes."""
        affected = []

        for file_path in changed_files:
            if file_path in test_map:
                affected.extend(test_map[file_path])

        return list(set(affected))

    def check_layer_boundary(
        self,
        source_layer: LayerBoundary,
        target_layer: LayerBoundary,
    ) -> tuple[bool, str]:
        """
        Check if layer dependency is allowed.

        Returns:
            (is_allowed, reason)
        """
        for rule in self._layer_rules:
            if rule.from_layer == source_layer and rule.to_layer == target_layer:
                return rule.allowed, rule.reason or "Layer rule"

        # Default: allow if no rule
        return True, "No specific rule"

    def generate_preservation_report(self) -> str:
        """Generate architecture preservation report."""
        lines = [
            "Architecture Preservation Report",
            "=" * 50,
            "",
            f"Preserved Files: {len(self._preserved_files)}",
            f"Preserved APIs: {len(self._preserved_apis)}",
            f"Constraints: {len(self._constraints)}",
            f"Layer Rules: {len(self._layer_rules)}",
            "",
            "Preserved APIs:",
        ]

        for api in self._preserved_apis:
            callers = self._graph.get_callers(api)
            lines.append(f"  - {api} ({len(callers)} callers)")

        cycles = self._graph.find_cycles()
        if cycles:
            lines.extend([
                "",
                "WARNING: Dependency cycles detected:",
            ])
            for cycle in cycles[:3]:
                lines.append(f"  - {' -> '.join(cycle[:5])}")

        return "\n".join(lines)


class PartialFixDetector:
    """
    Detects when AI applies partial fix that doesn't address root cause.

    Symptom vs Root Cause patterns:
    - Increase buffer size -> symptom relieved, but memory leak remains
    - Add timeout -> symptom relieved, but deadlock remains
    - Disable warning -> symptom gone, but bug remains
    - Retry logic -> symptom masked, but race condition remains
    """

    PARTIAL_FIX_PATTERNS = [
        {
            "pattern": r"increase.*buffer.*size",
            "root_cause": "buffer not being freed/reset",
            "detection": "Buffer index not reset after processing",
        },
        {
            "pattern": r"add.*timeout",
            "root_cause": "operation hangs indefinitely",
            "detection": "Check for infinite loop or deadlock",
        },
        {
            "pattern": r"disable.*warning",
            "root_cause": "underlying issue not addressed",
            "detection": "Warning indicates real problem",
        },
        {
            "pattern": r"increase.*delay",
            "root_cause": "timing dependency not understood",
            "detection": "Race condition or incorrect sequencing",
        },
        {
            "pattern": r"catch.*exception",
            "root_cause": "exception source not investigated",
            "detection": "What causes the exception?",
        },
    ]

    @classmethod
    def detect_partial_fix(cls, fix_description: str) -> Optional[dict[str, str]]:
        """Detect if fix is a partial symptom treatment."""
        for pattern in cls.PARTIAL_FIX_PATTERNS:
            if re.search(pattern["pattern"], fix_description, re.IGNORECASE):
                return {
                    "is_partial": True,
                    "fix_type": pattern["pattern"],
                    "actual_root_cause": pattern["root_cause"],
                    "investigate": pattern["detection"],
                }
        return None

    @classmethod
    def suggest_full_fix(cls, partial_fix: str, symptom: str) -> str:
        """Suggest what a full fix would require."""
        detection = cls.detect_partial_fix(partial_fix)

        if not detection:
            return "Fix appears complete - verify with tests"

        return f"""
Partial Fix Detected: {partial_fix}

This treats the symptom, not the root cause.

Root Cause to Investigate: {detection['actual_root_cause']}

What to Check:
{detection['investigate']}

Full Fix Checklist:
1. Identify the actual root cause
2. Fix the root cause, not just the symptom
3. Verify fix doesn't introduce new issues
4. Add regression tests
"""
