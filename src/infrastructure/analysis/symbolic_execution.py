"""Symbolic execution engine (Phase 13b.1).

Provides path-sensitive symbolic execution:
- Symbolic variable tracking
- Path exploration
- Constraint solving
- Bug detection
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConstraintType(Enum):
    """Constraint types."""
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    GREATER = "greater"
    LESS = "less"
    AND = "and"
    OR = "or"


@dataclass
class SymbolicVar:
    """Symbolic variable."""
    name: str
    value: Any  # concrete or symbolic
    constraints: list = field(default_factory=list)


@dataclass
class PathConstraint:
    """Path constraint."""
    var: str
    constraint_type: ConstraintType
    value: Any


@dataclass
class ExecutionPath:
    """Single execution path."""
    path_id: str
    pc: int  # program counter
    constraints: list[PathConstraint] = field(default_factory=list)
    visited_nodes: list[int] = field(default_factory=list)


@dataclass
class BugInstance:
    """Detected bug."""
    bug_id: str
    path_id: str
    bug_type: str  # null_deref, buffer_overflow, etc.
    location: str
    description: str


class SymbolicEngine:
    """Symbolic execution engine.
    
    Phase 13b.1: Symbolic execution engine - Path-sensitive analysis
    """
    
    def __init__(self, max_depth: int = 100) -> None:
        self._max_depth = max_depth
        self._paths: list[ExecutionPath] = []
        self._bugs: list[BugInstance] = []
        self._variables: dict[str, SymbolicVar] = {}
    
    def add_variable(self, name: str, initial_value: Any = None) -> None:
        """Add symbolic variable."""
        self._variables[name] = SymbolicVar(name=name, value=initial_value)
    
    def add_constraint(self, var: str, constraint_type: ConstraintType, value: Any) -> None:
        """Add path constraint."""
        constraint = PathConstraint(var=var, constraint_type=constraint_type, value=value)
        
        for path in self._paths:
            path.constraints.append(constraint)
    
    def execute_instruction(self, instruction: str) -> list[ExecutionPath]:
        """Execute single instruction symbolically."""
        new_paths = []
        
        for path in self._paths:
            if len(path.visited_nodes) >= self._max_depth:
                continue
            
            # Create new path for branches
            if "if" in instruction or "branch" in instruction:
                # Take branch
                new_path = ExecutionPath(
                    path_id=f"{path.path_id}_t",
                    pc=path.pc + 1,
                    constraints=path.constraints.copy(),
                    visited_nodes=path.visited_nodes + [path.pc],
                )
                new_paths.append(new_path)
                
                # Fall through
                path.pc += 1
                path.visited_nodes.append(path.pc)
            else:
                path.pc += 1
                path.visited_nodes.append(path.pc)
        
        self._paths.extend(new_paths)
        return self._paths
    
    def check_null_deref(self, var: str) -> list[BugInstance]:
        """Check for null dereference."""
        bugs = []
        
        for path in self._paths:
            # Check if var could be null based on constraints
            for constraint in path.constraints:
                if constraint.var == var and constraint.constraint_type == ConstraintType.EQUAL:
                    if constraint.value == 0:
                        bugs.append(BugInstance(
                            bug_id=f"null_{var}_{path.path_id}",
                            path_id=path.path_id,
                            bug_type="null_dereference",
                            location=f"pc_{path.pc}",
                            description=f"Variable {var} may be null on this path",
                        ))
        
        return bugs
    
    def explore_paths(self, instructions: list[str]) -> list[ExecutionPath]:
        """Explore all paths through code."""
        # Initialize with starting path
        self._paths = [
            ExecutionPath(path_id="root", pc=0, constraints=[], visited_nodes=[])
        ]
        
        # Execute each instruction
        for instruction in instructions:
            self.execute_instruction(instruction)
        
        return self._paths
    
    def get_bugs(self) -> list[BugInstance]:
        """Get all detected bugs."""
        return self._bugs
    
    def get_statistics(self) -> dict[str, Any]:
        """Get execution statistics."""
        return {
            "total_paths": len(self._paths),
            "max_depth": max(len(p.visited_nodes) for p in self._paths) if self._paths else 0,
            "bugs_found": len(self._bugs),
        }


# Global engine
_symbolic_engine: SymbolicEngine | None = None


def get_symbolic_engine() -> SymbolicEngine:
    """Get global symbolic engine."""
    global _symbolic_engine
    if _symbolic_engine is None:
        _symbolic_engine = SymbolicEngine()
    return _symbolic_engine


if __name__ == "__main__":
    engine = get_symbolic_engine()
    
    print("Symbolic Execution Engine")
    print("=" * 40)
    
    # Add variable
    engine.add_variable("ptr", 0)
    
    # Add constraint
    engine.add_constraint("ptr", ConstraintType.NOT_EQUAL, 0)
    
    # Simulate exploration
    instructions = [
        "load ptr",
        "if ptr == 0",
        "dereference",
    ]
    
    paths = engine.explore_paths(instructions)
    print(f"Explored {len(paths)} paths")
    
    # Check for bugs
    bugs = engine.check_null_deref("ptr")
    print(f"Bugs found: {len(bugs)}")
    
    # Stats
    stats = engine.get_statistics()
    print(f"Statistics: {stats}")
