"""Tests for data flow analysis."""

import pytest
from src.infrastructure.analysis.data_flow import DataFlowAnalyzer, TaintSource, TaintSink, TaintFinding


class TestDataFlowAnalyzer:
    """Tests for data flow analysis."""

    def test_analyze_basic(self):
        """Test basic analysis doesn't crash."""
        analyzer = DataFlowAnalyzer()
        code = '''x = 1
y = 2'''
        findings = analyzer.analyze(code, "test.py")
        assert isinstance(findings, list)

    def test_analyze_detects_taint_flow(self):
        """Test taint flow detection from source to sink."""
        analyzer = DataFlowAnalyzer()
        code = '''x = input()
exec(x)'''
        findings = analyzer.analyze(code, "test.py")
        assert len(findings) >= 1
        assert "user_input" in findings[0].message

    def test_analyze_empty_code(self):
        """Test empty code handling."""
        analyzer = DataFlowAnalyzer()
        code = ''
        findings = analyzer.analyze(code, "test.py")
        assert findings == []
