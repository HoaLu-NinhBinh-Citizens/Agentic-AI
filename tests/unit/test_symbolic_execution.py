"""Tests for symbolic execution."""

import pytest
from src.infrastructure.analysis.symbolic_execution import (
    SymbolicEngine,
    ConstraintType,
    ExecutionPath,
)


class TestSymbolicEngine:
    def test_engine_creation(self):
        engine = SymbolicEngine()
        assert engine is not None

    def test_add_variable(self):
        engine = SymbolicEngine()
        engine.add_variable("x")
        engine.add_variable("ptr", 0)

    def test_add_constraint(self):
        engine = SymbolicEngine()
        engine.add_variable("x")
        engine.add_constraint("x", ConstraintType.NOT_EQUAL, 0)

    def test_explore_paths(self):
        engine = SymbolicEngine()
        instructions = ["load x", "if x > 0", "branch"]
        paths = engine.explore_paths(instructions)
        assert len(paths) >= 1

    def test_get_statistics(self):
        engine = SymbolicEngine()
        stats = engine.get_statistics()
        assert "total_paths" in stats
        assert "bugs_found" in stats
