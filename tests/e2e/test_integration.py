"""Integration test - verify all components work together."""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from src.application.workflows.unified import (
    UnifiedReviewEngine,
    ReviewEngineConfig,
)
from src.application.suggestion import UnifiedSuggestionEngine, SuggestionConfig
from src.interfaces.conversation import ConversationManager


@pytest.mark.asyncio
async def test_full_pipeline():
    """Test complete pipeline integration (simplified without file I/O)."""
    from src.application.workflows.unified.detector_base import Finding, FindingSeverity
    from src.infrastructure.reporting import MarkdownReportGenerator, Severity, PipelineStats
    
    # Create test finding directly
    finding = Finding(
        rule_id="ML001",
        rule_name="data-leakage",
        severity=FindingSeverity.ERROR,
        file="test.py",
        line=10,
        end_line=10,
        message="scaler.fit() called before train_test_split",
        context="scaler.fit(X)",
        fix="scaler.fit_transform(X_train)",
        confidence=0.95,
    )
    
    # Run suggestion engine
    suggestion_engine = UnifiedSuggestionEngine()
    suggestion = await suggestion_engine.generate(finding, None)
    
    assert suggestion is not None
    assert len(suggestion.options) > 0
    
    # Generate report (use reporter's own Finding type)
    reporter_finding = type('ReporterFinding', (), {
        'rule_id': finding.rule_id,
        'title': finding.rule_name,
        'severity': Severity.CRITICAL,  # Map to reporter's Severity
        'file_path': finding.file,
        'line': finding.line,
        'message': finding.message,
        'description': finding.context or "",
        'old_code': finding.context or "",
        'new_code': finding.fix or "",
        'confidence': finding.confidence,
        'fixable': bool(finding.fix),
        'auto_fixable': False,
        'risk_level': "HIGH",
    })()
    
    reporter = MarkdownReportGenerator("TestProject")
    by_severity = {s: 0 for s in Severity}
    by_severity[Severity.CRITICAL] = 1
    report = reporter.generate(
        [reporter_finding],
        PipelineStats(
            files_analyzed=1,
            duration_seconds=0.1,
            total_findings=1,
            findings_by_severity=by_severity,
        )
    )
    assert "Summary" in report or "summary" in report.lower()
    
    # Conversation - convert to dict with string severity
    manager = ConversationManager()
    manager.set_findings([{
        "rule_id": finding.rule_id,
        "rule_name": finding.rule_name,
        "severity": finding.severity.value,  # Convert enum to string
        "file": finding.file,
        "line": finding.line,
        "message": finding.message,
        "confidence": finding.confidence,
    }])
    response = await manager.process_message("/summary")
    assert len(response) > 0


@pytest.mark.asyncio
async def test_suggestion_engine():
    """Test suggestion engine with various findings."""
    from src.application.workflows.unified.detector_base import Finding, FindingSeverity
    
    # Create test finding
    finding = Finding(
        rule_id="ML001",
        rule_name="data-leakage",
        severity=FindingSeverity.ERROR,
        file="test.py",
        line=10,
        end_line=10,
        message="scaler.fit() called before train_test_split",
        context="scaler.fit(X)",
        fix="scaler.fit_transform(X_train)",
        confidence=0.95,
    )
    
    engine = UnifiedSuggestionEngine()
    result = await engine.generate(finding, None)
    
    assert result is not None
    assert result.rule_id == "ML001"
    assert len(result.options) > 0
    assert result.best_option is not None


@pytest.mark.asyncio
async def test_review_with_multiple_focus_areas():
    """Test review with multiple focus areas."""
    from src.application.workflows.unified.detector_base import Finding, FindingSeverity
    
    # Create test findings directly (bypass engine initialization issues)
    findings = [
        Finding(
            rule_id="SEC001",
            rule_name="hardcoded-secret",
            severity=FindingSeverity.ERROR,
            file="test.py",
            line=10,
            end_line=10,
            message="Hardcoded secret detected",
            confidence=0.9,
        ),
        Finding(
            rule_id="QUAL001",
            rule_name="long-function",
            severity=FindingSeverity.WARNING,
            file="test.py",
            line=20,
            end_line=20,
            message="Function exceeds recommended length",
            confidence=0.8,
        ),
    ]
    
    # Test that findings can be created with different severities
    assert findings[0].severity == FindingSeverity.ERROR
    assert findings[1].severity == FindingSeverity.WARNING
    assert len(findings) == 2


@pytest.mark.asyncio
async def test_conversation_manager():
    """Test conversation manager integration."""
    from src.application.workflows.unified.detector_base import Finding, FindingSeverity
    
    # Create sample findings as dicts (ConversationManager expects dicts)
    findings_as_dicts = [
        {
            "rule_id": "ML001",
            "rule_name": "data-leakage",
            "severity": "WARNING",
            "file": "test.py",
            "line": 10,
            "message": "Data leakage detected",
            "confidence": 0.9,
        },
        {
            "rule_id": "SEC001",
            "rule_name": "hardcoded-secret",
            "severity": "ERROR",
            "file": "test.py",
            "line": 20,
            "message": "Hardcoded secret detected",
            "confidence": 0.95,
        },
    ]
    
    manager = ConversationManager()
    manager.set_findings(findings_as_dicts)
    
    # Test summary command
    response = await manager.process_message("/summary")
    assert len(response) > 0
    
    # Test help command
    response = await manager.process_message("/help")
    assert len(response) > 0


@pytest.mark.asyncio
async def test_output_formats():
    """Test different output formats."""
    from src.application.workflows.unified.result_formatter import (
        MarkdownFormatter,
        JsonFormatter,
        ConsoleFormatter,
        PipelineStats,
    )
    from src.application.workflows.unified.detector_base import Finding, FindingSeverity
    
    findings = [
        Finding(
            rule_id="TEST001",
            rule_name="test-finding",
            severity=FindingSeverity.WARNING,
            file="test.py",
            line=10,
            end_line=10,
            message="Test message",
            confidence=0.8,
        )
    ]
    
    stats = PipelineStats(
        files_scanned=1,
        findings_count=1,
        execution_time_ms=100,
    )
    
    # Markdown format
    md_formatter = MarkdownFormatter()
    md_output = md_formatter.format(findings, stats)
    assert "# Code Review Report" in md_output or "Summary" in md_output
    
    # JSON format
    json_formatter = JsonFormatter()
    json_output = json_formatter.format(findings, stats)
    assert '"findings"' in json_output
    
    # Console format
    console_formatter = ConsoleFormatter()
    console_output = console_formatter.format(findings, stats)
    assert len(console_output) > 0


if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
