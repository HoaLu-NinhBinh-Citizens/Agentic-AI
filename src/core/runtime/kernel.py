"""
Runtime Kernel - Kernel boundary definition

Defines what belongs in the kernel vs extensions.

Kernel rules:
1. Kernel modules < 2000 lines total
2. Kernel modules < 500 lines each
3. Functions < 50 lines
4. No circular dependencies within kernel
5. Extensions can be loaded/unloaded

Usage:
    from src.domains.runtime.kernel import classify, KERNEL_BOUNDARY

    boundary = classify("AI_support/runtime/controller.py")
    if boundary == KernelBoundary.KERNEL:
        print("This is a kernel module")
"""

import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterator

logger = __name__


class KernelBoundary(Enum):
    """Classification for modules."""

    KERNEL = "kernel"  # Core, required for any operation
    EXTENSION = "extension"  # Optional, can be loaded/unloaded
    EXPERIMENTAL = "experimental"  # Under development, may be removed


# Kernel boundary definition
# Pattern → Boundary
KERNEL_BOUNDARY = {
    # KERNEL: Core functionality (< 2000 lines total)
    "runtime/controller": KernelBoundary.KERNEL,
    "runtime/lifecycle": KernelBoundary.KERNEL,
    "events/bus": KernelBoundary.KERNEL,
    "events/base": KernelBoundary.KERNEL,
    "orchestration/queue": KernelBoundary.KERNEL,
    "orchestration/state": KernelBoundary.KERNEL,
    # Import runtime helpers
    "runtime/circuit_breaker": KernelBoundary.KERNEL,
    "runtime/admission": KernelBoundary.KERNEL,
    "runtime/cancellation": KernelBoundary.KERNEL,
    "runtime/backpressure": KernelBoundary.KERNEL,
    "execution/idempotency": KernelBoundary.KERNEL,
    "scheduler/": KernelBoundary.KERNEL,
    # EXTENSION: Optional, loadable
    "llm/": KernelBoundary.EXTENSION,
    "retrieval/": KernelBoundary.EXTENSION,
    "tools/": KernelBoundary.EXTENSION,
    "memory/": KernelBoundary.EXTENSION,
    "config/": KernelBoundary.EXTENSION,
    "services/": KernelBoundary.EXTENSION,
    "domains/": KernelBoundary.EXTENSION,
    "runtime/resource": KernelBoundary.EXTENSION,
    "runtime/persistence": KernelBoundary.EXTENSION,
    # EXPERIMENTAL: May be removed
    "chaos/": KernelBoundary.EXPERIMENTAL,
    "distributed/": KernelBoundary.EXPERIMENTAL,
    "healing/": KernelBoundary.EXPERIMENTAL,
    "introspection/": KernelBoundary.EXPERIMENTAL,
}

# Size constraints
KERNEL_SIZE_LIMITS = {
    "max_kernel_lines": 2000,
    "max_module_lines": 500,
    "max_function_lines": 50,
}

# Kernel module list for counting
KERNEL_MODULES = [
    "runtime/controller.py",
    "runtime/lifecycle.py",
    "events/bus.py",
    "events/base.py",
    "orchestration/queue.py",
    "orchestration/state.py",
    "runtime/circuit_breaker.py",
    "runtime/admission.py",
    "runtime/cancellation.py",
    "runtime/backpressure.py",
    "execution/idempotency.py",
    "scheduler/task_scheduler.py",
]


def classify(module_path: str) -> KernelBoundary:
    """
    Classify a module by kernel boundary.

    Args:
        module_path: Path to module (e.g., "AI_support/runtime/controller.py")

    Returns:
        KernelBoundary classification
    """
    # Normalize path
    path = module_path.replace("\\", "/")

    # Extract relative path from AI_support
    if "AI_support/" in path:
        path = path.split("AI_support/", 1)[1]

    for pattern, boundary in KERNEL_BOUNDARY.items():
        if pattern.endswith("/"):
            # Directory match
            if path.startswith(pattern):
                return boundary
        else:
            # Exact or prefix match
            if pattern in path or path.startswith(pattern + "/"):
                return boundary

    # Default to EXTENSION if not matched
    return KernelBoundary.EXTENSION


def is_kernel(module_path: str) -> bool:
    """Check if module is in kernel."""
    return classify(module_path) == KernelBoundary.KERNEL


def is_extension(module_path: str) -> bool:
    """Check if module is an extension."""
    return classify(module_path) == KernelBoundary.EXTENSION


def is_experimental(module_path: str) -> bool:
    """Check if module is experimental."""
    return classify(module_path) == KernelBoundary.EXPERIMENTAL


@dataclass
class KernelMetrics:
    """Metrics for kernel size."""

    total_lines: int
    module_count: int
    largest_module: str
    largest_module_lines: int
    within_limits: bool
    violations: list[str]


def measure_kernel(root_path: str = ".") -> KernelMetrics:
    """
    Measure kernel size against limits.

    Args:
        root_path: Path to AI_support root

    Returns:
        KernelMetrics with measurements
    """
    violations = []
    total_lines = 0
    largest_module = ""
    largest_lines = 0
    module_count = 0

    for module in KERNEL_MODULES:
        module_path = Path(root_path) / module
        if not module_path.exists():
            continue

        try:
            lines = count_lines(module_path)
            total_lines += lines
            module_count += 1

            if lines > largest_lines:
                largest_lines = lines
                largest_module = module

            if lines > KERNEL_SIZE_LIMITS["max_module_lines"]:
                violations.append(
                    f"{module}: {lines} lines (max {KERNEL_SIZE_LIMITS['max_module_lines']})"
                )
        except Exception as e:
            logger.warning(f"Failed to measure {module}: {e}")

    # Check total
    if total_lines > KERNEL_SIZE_LIMITS["max_kernel_lines"]:
        violations.append(
            f"Kernel total: {total_lines} lines (max {KERNEL_SIZE_LIMITS['max_kernel_lines']})"
        )

    return KernelMetrics(
        total_lines=total_lines,
        module_count=module_count,
        largest_module=largest_module,
        largest_module_lines=largest_lines,
        within_limits=len(violations) == 0,
        violations=violations,
    )


def count_lines(file_path: Path) -> int:
    """Count non-empty, non-comment lines."""
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()

        count = 0
        in_docstring = False
        for line in lines:
            stripped = line.strip()

            # Skip empty
            if not stripped:
                continue

            # Skip comments
            if stripped.startswith("#"):
                continue

            # Track docstrings
            if '"""' in stripped or "'''" in stripped:
                in_docstring = not in_docstring
                continue

            if in_docstring:
                continue

            count += 1

        return count
    except Exception:
        return 0


def count_function_lines(file_path: Path) -> dict[str, int]:
    """Count lines per function in a file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        function_lines = {}
        current_func = None
        func_start = 0
        in_docstring = False

        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()

            # Track docstrings
            if '"""' in stripped or "'''" in stripped:
                in_docstring = not in_docstring
                continue

            if in_docstring:
                continue

            # Skip empty and comments
            if not stripped or stripped.startswith("#"):
                continue

            # Function definition
            if re.match(r"^(async\s+)?def\s+\w+\s*\(", stripped):
                if current_func:
                    function_lines[current_func] = i - func_start
                current_func = re.search(r"def\s+(\w+)", stripped).group(1)
                func_start = i

        if current_func:
            function_lines[current_func] = len(content.splitlines()) - func_start

        return function_lines
    except Exception:
        return {}


def find_large_functions(root_path: str = ".", threshold: int = 50) -> list[dict]:
    """Find functions exceeding line threshold."""
    violations = []

    for module in KERNEL_MODULES:
        module_path = Path(root_path) / module
        if not module_path.exists():
            continue

        func_lines = count_function_lines(module_path)
        for func_name, lines in func_lines.items():
            if lines > threshold:
                violations.append(
                    {
                        "module": module,
                        "function": func_name,
                        "lines": lines,
                        "threshold": threshold,
                    }
                )

    return violations


def validate_kernel() -> dict:
    """
    Validate kernel against all rules.

    Returns:
        Dict with validation results
    """
    metrics = measure_kernel()
    large_funcs = find_large_functions()

    violations = list(metrics.violations)
    for func in large_funcs:
        violations.append(
            f"{func['module']}::{func['function']}: {func['lines']} lines "
            f"(max {func['threshold']})"
        )

    return {
        "valid": len(violations) == 0,
        "metrics": {
            "total_lines": metrics.total_lines,
            "module_count": metrics.module_count,
            "largest_module": metrics.largest_module,
            "largest_module_lines": metrics.largest_module_lines,
        },
        "violations": violations,
    }


# Check on import
def _check_kernel_size():
    """Warn if kernel is getting large."""
    try:
        metrics = measure_kernel()
        if metrics.total_lines > KERNEL_SIZE_LIMITS["max_kernel_lines"] * 0.8:
            logger.warning(
                f"Kernel size warning: {metrics.total_lines} lines "
                f"(limit: {KERNEL_SIZE_LIMITS['max_kernel_lines']})"
            )
    except Exception:
        pass  # Don't fail import
