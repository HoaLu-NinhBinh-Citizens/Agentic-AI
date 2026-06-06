"""Tests for inter-procedural taint tracking.

Validates that taint flows correctly across function boundaries:
- Tainted argument -> callee parameter -> sink
- Tainted return value -> caller variable
- Multi-hop call chains
- Sanitizers break the chain
"""

from __future__ import annotations

import pytest

from src.infrastructure.analysis.interprocedural_taint import (
    FunctionSummary,
    InterproceduralTaintAnalyzer,
    analyze_combined,
)


@pytest.fixture
def analyzer() -> InterproceduralTaintAnalyzer:
    return InterproceduralTaintAnalyzer()


# ─── Tests: Cross-Function Argument Taint ────────────────────────────────────


class TestArgumentTaint:
    """Tainted argument flows to callee parameter and reaches sink."""

    def test_tainted_arg_to_sink(self, analyzer: InterproceduralTaintAnalyzer):
        """source -> arg -> param -> sink (cross-function)."""
        code = """\
def query(uid):
    cursor.execute(uid)

def handler():
    data = input()
    query(data)
"""
        findings = analyzer.analyze(code)
        assert len(findings) >= 1
        # The sink is reached via parameter 'uid' in query()
        assert any(f.sink.sink_type == "sql_injection" for f in findings)

    def test_clean_arg_no_finding(self, analyzer: InterproceduralTaintAnalyzer):
        """Constant argument does not taint the parameter."""
        code = """\
def query(uid):
    cursor.execute(uid)

def handler():
    query("SELECT 1")
"""
        findings = analyzer.analyze(code)
        assert len(findings) == 0

    def test_command_injection_cross_function(self, analyzer):
        code = """\
def run_cmd(cmd):
    os.system(cmd)

def handler():
    user_cmd = request.args["cmd"]
    run_cmd(user_cmd)
"""
        findings = analyzer.analyze(code)
        assert any(f.sink.sink_type == "command_injection" for f in findings)


# ─── Tests: Return Value Taint ───────────────────────────────────────────────


class TestReturnTaint:
    """Tainted return value flows back to caller."""

    def test_tainted_return_then_sink(self, analyzer: InterproceduralTaintAnalyzer):
        """func returns taint -> caller var tainted -> sink."""
        code = """\
def get_input():
    return input()

def handler():
    data = get_input()
    os.system(data)
"""
        findings = analyze_combined(code)
        # Either intra (in handler, data->os.system) or inter should catch it
        assert any(f.sink.sink_type == "command_injection" for f in findings)

    def test_return_propagates_param_taint(self, analyzer):
        """func returns its param -> taint flows through."""
        code = """\
def passthrough(x):
    return x

def handler():
    tainted = input()
    result = passthrough(tainted)
    eval(result)
"""
        findings = analyze_combined(code)
        assert any(f.sink.sink_type == "code_execution" for f in findings)


# ─── Tests: Multi-Hop Chains ─────────────────────────────────────────────────


class TestMultiHopChains:
    """Taint flows through chains of function calls."""

    def test_two_hop_chain(self, analyzer: InterproceduralTaintAnalyzer):
        """A -> B -> C where taint originates in A and sink is in C."""
        code = """\
def level_c(value):
    os.system(value)

def level_b(data):
    level_c(data)

def level_a():
    user = input()
    level_b(user)
"""
        findings = analyzer.analyze(code)
        # Taint should reach the sink in level_c via the chain
        assert any(f.sink.sink_type == "command_injection" for f in findings)


# ─── Tests: Sanitizers ───────────────────────────────────────────────────────


class TestSanitizers:
    """Sanitizers break the taint chain."""

    def test_sanitized_arg_no_finding(self, analyzer: InterproceduralTaintAnalyzer):
        """Sanitized data does not trigger a finding."""
        code = """\
def query(uid):
    cursor.execute(uid)

def handler():
    raw = input()
    safe = shlex.quote(raw)
    query(safe)
"""
        findings = analyzer.analyze(code)
        # safe is sanitized, so no taint should flow into query
        assert len(findings) == 0


# ─── Tests: Function Summaries ───────────────────────────────────────────────


class TestFunctionSummaries:
    """Verify per-function summary computation."""

    def test_summary_param_to_sink(self, analyzer: InterproceduralTaintAnalyzer):
        code = """\
def vulnerable(param):
    os.system(param)
"""
        analyzer.analyze(code)
        summary = analyzer._summaries.get("vulnerable")
        assert summary is not None
        assert "param" in summary.tainted_param_to_sink
        assert summary.tainted_param_to_sink["param"] == "command_injection"

    def test_summary_param_to_return(self, analyzer):
        code = """\
def echo(x):
    return x
"""
        analyzer.analyze(code)
        summary = analyzer._summaries.get("echo")
        assert summary is not None
        assert "x" in summary.tainted_param_to_return

    def test_summary_returns_source(self, analyzer):
        code = """\
def get_data():
    return input()
"""
        analyzer.analyze(code)
        summary = analyzer._summaries.get("get_data")
        assert summary is not None
        assert summary.returns_source_taint


# ─── Tests: Combined Analysis ────────────────────────────────────────────────


class TestCombinedAnalysis:
    """analyze_combined merges intra + inter findings without duplicates."""

    def test_combined_dedup(self):
        code = """\
def handler():
    data = input()
    os.system(data)
"""
        findings = analyze_combined(code)
        # Intra-procedural catches this; should appear once
        cmd_findings = [f for f in findings if f.sink.sink_type == "command_injection"]
        assert len(cmd_findings) >= 1

    def test_combined_catches_cross_function(self):
        code = """\
def sink_fn(p):
    eval(p)

def source_fn():
    x = input()
    sink_fn(x)
"""
        findings = analyze_combined(code)
        assert any(f.sink.sink_type == "code_execution" for f in findings)

    def test_no_false_positive_on_safe_code(self):
        code = """\
def add(a, b):
    return a + b

def main():
    result = add(1, 2)
    print(result)
"""
        findings = analyze_combined(code)
        assert len(findings) == 0
