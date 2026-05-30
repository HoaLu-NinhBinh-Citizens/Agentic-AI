"""Tests for unified ReviewIssue schema and converters.

Tests cover:
- ReviewIssue creation and properties
- CodeEvidence and FixOption functionality
- MLFindingConverter
- FindingConverter
- FixConverter
- Deduplication
- Serialization/deserialization
"""

import pytest
from unittest.mock import MagicMock

from src.domain.models.review_issue import (
    CodeEvidence,
    FixOption,
    ReviewIssue,
    Severity,
    generate_issue_id,
)


# ─── ReviewIssue Tests ───────────────────────────────────────────────────────────


def test_review_issue_creation():
    """Test basic ReviewIssue creation."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=18,
        message="Data leakage detected",
    )
    assert issue.id == "test-1"
    assert issue.rule_id == "ML001"
    assert issue.severity == Severity.CRITICAL
    assert issue.file == "train.py"
    assert issue.line == 18
    assert issue.message == "Data leakage detected"


def test_review_issue_is_fixable():
    """Test is_fixable property."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=18,
    )
    assert issue.is_fixable is False

    issue.fixes.append(FixOption(
        id="fix-1",
        title="Fix",
    ))
    assert issue.is_fixable is True


def test_review_issue_is_auto_fixable():
    """Test is_auto_fixable property."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=18,
    )

    # No fixes
    assert issue.is_auto_fixable is False

    # Add low-risk fix
    issue.fixes.append(FixOption(
        id="fix-1",
        title="Fix",
        risk=Severity.LOW,
    ))
    assert issue.is_auto_fixable is True


def test_review_issue_primary_fix():
    """Test primary_fix property returns best fix."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=18,
    )

    # No fixes
    assert issue.primary_fix is None

    # Add multiple fixes
    issue.fixes.append(FixOption(
        id="fix-1",
        title="Risky fix",
        risk=Severity.HIGH,
        confidence=0.9,
    ))
    issue.fixes.append(FixOption(
        id="fix-2",
        title="Safe fix",
        risk=Severity.LOW,
        confidence=0.7,
    ))

    primary = issue.primary_fix
    assert primary is not None
    assert primary.risk == Severity.LOW  # Lowest risk first


def test_review_issue_location():
    """Test location property."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=10,
    )
    assert issue.location == "train.py:10"

    issue.end_line = 15
    assert issue.location == "train.py:10-15"


def test_review_issue_to_dict():
    """Test ReviewIssue serialization to dict."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=18,
        message="Test message",
        explanation="Test explanation",
        evidence=CodeEvidence(
            file="train.py",
            line_start=18,
            line_end=20,
            old_code="scaler.fit(data)",
            new_code="scaler.fit(X_train)",
        ),
        confidence=0.85,
        tags=["ml", "data-leakage"],
        detector="ml",
    )

    data = issue.to_dict()

    assert data["id"] == "test-1"
    assert data["rule_id"] == "ML001"
    assert data["severity"] == "CRITICAL"
    assert data["severity_weight"] == 1.0
    assert data["file"] == "train.py"
    assert data["line"] == 18
    assert data["message"] == "Test message"
    assert data["confidence"] == 0.85
    assert data["tags"] == ["ml", "data-leakage"]
    assert data["detector"] == "ml"
    assert data["is_fixable"] is False  # No fixes added to issue
    assert data["is_auto_fixable"] is False

    # Check evidence
    assert data["evidence"] is not None
    assert data["evidence"]["old_code"] == "scaler.fit(data)"
    assert data["evidence"]["new_code"] == "scaler.fit(X_train)"


def test_review_issue_from_dict():
    """Test ReviewIssue deserialization from dict."""
    data = {
        "id": "test-1",
        "rule_id": "ML001",
        "severity": "CRITICAL",
        "file": "train.py",
        "line": 18,
        "end_line": 20,
        "message": "Test message",
        "explanation": "Test explanation",
        "confidence": 0.85,
        "tags": ["ml"],
        "detector": "ml",
        "evidence": {
            "file": "train.py",
            "line_start": 18,
            "line_end": 20,
            "old_code": "old",
            "new_code": "new",
        },
        "fixes": [],
    }

    issue = ReviewIssue.from_dict(data)

    assert issue.id == "test-1"
    assert issue.rule_id == "ML001"
    assert issue.severity == Severity.CRITICAL
    assert issue.file == "train.py"
    assert issue.message == "Test message"
    assert issue.confidence == 0.85
    assert issue.evidence is not None
    assert issue.evidence.old_code == "old"


def test_review_issue_to_markdown():
    """Test ReviewIssue markdown generation."""
    issue = ReviewIssue(
        id="test-1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=18,
        title="Data Leakage Detected",
        message="Scaler fit before split",
        explanation="This causes data leakage",
        evidence=CodeEvidence(
            file="train.py",
            line_start=18,
            line_end=18,
            old_code="scaler.fit(data)",
            new_code="scaler.fit(X_train)",
        ),
        fixes=[
            FixOption(
                id="fix-1",
                title="Move scaler after split",
                risk=Severity.LOW,
            ),
        ],
        confidence=0.85,
    )

    markdown = issue.to_markdown()

    assert "🔴 CRITICAL" in markdown
    assert "Data Leakage Detected" in markdown
    assert "train.py:18" in markdown
    assert "Scaler fit before split" in markdown
    assert "scaler.fit(data)" in markdown
    assert "scaler.fit(X_train)" in markdown
    assert "This causes data leakage" in markdown


# ─── CodeEvidence Tests ────────────────────────────────────────────────────────


def test_code_evidence_diff():
    """Test CodeEvidence diff generation."""
    evidence = CodeEvidence(
        file="test.py",
        line_start=10,
        line_end=10,
        old_code="old_code",
        new_code="new_code",
    )

    diff = evidence.diff

    assert "@@" in diff
    assert "-old_code" in diff
    assert "+new_code" in diff


def test_code_evidence_diff_multiline():
    """Test CodeEvidence diff with multiline code."""
    evidence = CodeEvidence(
        file="test.py",
        line_start=10,
        line_end=12,
        old_code="line1\nline2\nline3",
        new_code="line1\nmodified\nline3",
    )

    diff = evidence.diff

    assert "---" in diff
    assert "+++" in diff
    assert "line2" in diff
    assert "modified" in diff


def test_code_evidence_location():
    """Test CodeEvidence location property."""
    evidence = CodeEvidence(
        file="test.py",
        line_start=10,
        line_end=10,
    )
    assert evidence.location == "test.py:10"

    evidence.line_end = 15
    assert evidence.location == "test.py:10-15"


# ─── FixOption Tests ───────────────────────────────────────────────────────────


def test_fix_option_diff_generation():
    """Test FixOption auto-generates diff from old/new code."""
    fix = FixOption(
        id="fix-1",
        title="Move scaler after split",
        old_code="scaler.fit(data)",
        new_code="scaler.fit(X_train)",
    )

    assert fix.diff is not None
    assert "scaler.fit(data)" in fix.diff
    assert "scaler.fit(X_train)" in fix.diff


def test_fix_option_is_safe():
    """Test FixOption is_safe property."""
    fix_low = FixOption(
        id="fix-1",
        title="Low risk",
        risk=Severity.LOW,
    )
    assert fix_low.is_safe is True

    fix_high = FixOption(
        id="fix-2",
        title="High risk",
        risk=Severity.HIGH,
    )
    assert fix_high.is_safe is False


def test_fix_option_to_dict():
    """Test FixOption serialization."""
    fix = FixOption(
        id="fix-1",
        title="Test fix",
        description="Description",
        old_code="old",
        new_code="new",
        risk=Severity.LOW,
        confidence=0.9,
        effort="low",
    )

    data = fix.to_dict()

    assert data["id"] == "fix-1"
    assert data["title"] == "Test fix"
    assert data["risk"] == "LOW"
    assert data["confidence"] == 0.9
    assert data["effort"] == "low"


# ─── Severity Tests ─────────────────────────────────────────────────────────────


def test_severity_from_old_format():
    """Test Severity conversion from legacy formats."""
    assert Severity.from_old_format("error") == Severity.CRITICAL
    assert Severity.from_old_format("warning") == Severity.HIGH
    assert Severity.from_old_format("info") == Severity.INFO
    assert Severity.from_old_format("hint") == Severity.LOW


def test_severity_weight():
    """Test Severity weight for sorting."""
    assert Severity.CRITICAL.weight == 1.0
    assert Severity.HIGH.weight == 0.8
    assert Severity.MEDIUM.weight == 0.5
    assert Severity.LOW.weight == 0.3
    assert Severity.INFO.weight == 0.1


# ─── Generate Issue ID Tests ────────────────────────────────────────────────────


def test_generate_issue_id():
    """Test issue ID generation."""
    id1 = generate_issue_id("ML001", "train.py", 18)
    id2 = generate_issue_id("ML001", "train.py", 18)

    # Same inputs should produce same ID
    assert id1 == id2

    # Should contain rule_id
    assert "ml001" in id1

    # Should be reasonably short
    assert len(id1) < 30


# ─── Converter Tests ────────────────────────────────────────────────────────────


def test_ml_finding_converter():
    """Test MLFinding to ReviewIssue conversion."""
    from src.domain.models.converters import MLFindingConverter

    # Create mock MLFinding
    ml_finding = MagicMock()
    ml_finding.rule_id = "ML001"
    ml_finding.severity.value = "CRITICAL"
    ml_finding.line = 18
    ml_finding.end_line = 18
    ml_finding.file_path = "train.py"
    ml_finding.message = "Data leakage"
    ml_finding.old_code = "scaler.fit(data)"
    ml_finding.new_code = "scaler.fit(X_train)"
    ml_finding.explanation = "Scaler fit before split"
    ml_finding.confidence = 0.85
    ml_finding.detection_method = "ast"

    issue = MLFindingConverter.convert(ml_finding)

    assert issue.rule_id == "ML001"
    assert issue.severity == Severity.CRITICAL
    assert issue.file == "train.py"
    assert issue.line == 18
    assert issue.message == "Data leakage"
    assert issue.explanation == "Scaler fit before split"
    assert issue.confidence == 0.85
    assert issue.detector == "ml"
    assert issue.detection_method == "ast"
    assert issue.is_fixable is True
    assert issue.evidence is not None
    assert issue.evidence.old_code == "scaler.fit(data)"
    assert issue.evidence.new_code == "scaler.fit(X_train)"


def test_finding_converter():
    """Test Finding to ReviewIssue conversion."""
    from src.domain.models.converters import FindingConverter

    # Create mock Finding
    finding = MagicMock()
    finding.rule_id = "SEC001"
    finding.rule_name = "hardcoded-secret"
    finding.severity.value = "error"
    finding.file = "config.py"
    finding.line = 10
    finding.end_line = 10
    finding.message = "Hardcoded API key detected"
    finding.fix = "Use environment variable"
    finding.confidence = 0.95
    finding.detector = "security"
    finding.metadata = {
        "explanation": "Hardcoded secrets are a security risk",
        "old_code": "API_KEY = 'secret123'",
        "new_code": "API_KEY = os.getenv('API_KEY')",
        "tags": ["security", "secrets"],
    }

    issue = FindingConverter.convert(finding)

    assert issue.rule_id == "SEC001"
    assert issue.severity == Severity.CRITICAL  # error -> CRITICAL
    assert issue.file == "config.py"
    assert issue.line == 10
    assert issue.message == "Hardcoded API key detected"
    assert issue.explanation == "Hardcoded secrets are a security risk"
    assert issue.is_fixable is True
    assert issue.tags == ["security", "secrets"]


def test_fix_converter():
    """Test Fix to ReviewIssue conversion."""
    from src.domain.models.converters import FixConverter
    from src.core.fix_engine.models import Fix, FixSeverity

    # Create mock Fix
    fix = Fix(
        id="fix-1",
        file_path="test.py",
        line_start=10,
        line_end=10,
        old_text="old_code",
        new_text="new_code",
        reason="Fix bug",
        rule_id="BUG001",
        severity=FixSeverity.WARNING,
        confidence=0.9,
    )

    issue = FixConverter.to_review_issue(fix)

    assert issue.rule_id == "BUG001"
    assert issue.severity == Severity.HIGH  # warning -> HIGH
    assert issue.file == "test.py"
    assert issue.line == 10
    assert issue.message == "Fix bug"
    assert issue.is_fixable is True
    assert issue.evidence is not None
    assert issue.evidence.old_code == "old_code"
    assert issue.evidence.new_code == "new_code"


def test_convert_batch():
    """Test batch conversion."""
    from src.domain.models.converters import convert_batch, deduplicate_issues

    # Create mock findings
    mock_finding1 = MagicMock()
    mock_finding1.rule_id = "ML001"
    mock_finding1.severity.value = "CRITICAL"
    mock_finding1.line = 10
    mock_finding1.end_line = 10
    mock_finding1.file_path = "train.py"
    mock_finding1.message = "Issue 1"
    mock_finding1.old_code = "code1"
    mock_finding1.new_code = "fix1"
    mock_finding1.explanation = ""
    mock_finding1.confidence = 0.9
    mock_finding1.detection_method = "ast"

    mock_finding2 = MagicMock()
    mock_finding2.rule_id = "ML002"
    mock_finding2.severity.value = "HIGH"
    mock_finding2.line = 20
    mock_finding2.end_line = 20
    mock_finding2.file_path = "train.py"
    mock_finding2.message = "Issue 2"
    mock_finding2.old_code = "code2"
    mock_finding2.new_code = "fix2"
    mock_finding2.explanation = ""
    mock_finding2.confidence = 0.8
    mock_finding2.detection_method = "ast"

    issues = convert_batch([mock_finding1, mock_finding2])

    assert len(issues) == 2
    assert issues[0].rule_id == "ML001"
    assert issues[1].rule_id == "ML002"


def test_deduplicate_issues():
    """Test issue deduplication."""
    from src.domain.models.converters import deduplicate_issues

    issue1 = ReviewIssue(
        id="1",
        rule_id="ML001",
        severity=Severity.CRITICAL,
        file="train.py",
        line=10,
    )
    issue2 = ReviewIssue(
        id="2",
        rule_id="ML001",  # Same rule_id, file, line
        severity=Severity.HIGH,
        file="train.py",
        line=10,
    )
    issue3 = ReviewIssue(
        id="3",
        rule_id="ML001",  # Same rule_id, file, different line
        severity=Severity.MEDIUM,
        file="train.py",
        line=20,
    )

    issues = deduplicate_issues([issue1, issue2, issue3])

    # Should only keep unique (rule_id, file, line) combos
    assert len(issues) == 2


# ─── Integration Tests ───────────────────────────────────────────────────────────


def test_full_pipeline_simulation():
    """Simulate full pipeline: MLFinding -> ReviewIssue -> JSON."""
    from src.domain.models.converters import MLFindingConverter

    # Simulate MLFinding from infrastructure detector
    ml_finding = MagicMock()
    ml_finding.rule_id = "ML001"
    ml_finding.severity.value = "CRITICAL"
    ml_finding.line = 18
    ml_finding.end_line = 20
    ml_finding.file_path = "train.py"
    ml_finding.message = "Data leakage: scaler.fit() called before train_test_split"
    ml_finding.old_code = "scaler.fit(data)\nX_train, X_test, y_train, y_test = train_test_split(...)"
    ml_finding.new_code = "X_train, X_test, y_train, y_test = train_test_split(...)\nscaler.fit(X_train)"
    ml_finding.explanation = "Fitting the scaler on the entire dataset before splitting leaks information about the test set into the training process."
    ml_finding.confidence = 0.92
    ml_finding.detection_method = "ast"

    # Convert to unified ReviewIssue
    issue = MLFindingConverter.convert(ml_finding)

    # Verify conversion
    assert issue.severity == Severity.CRITICAL
    assert issue.is_fixable is True
    assert issue.is_auto_fixable is True  # Has LOW risk fix
    assert issue.evidence is not None
    assert "scaler.fit" in issue.evidence.diff

    # Convert to JSON
    json_data = issue.to_dict()
    import json
    json_str = json.dumps(json_data, indent=2)

    # Verify JSON contains expected fields
    assert '"severity": "CRITICAL"' in json_str
    assert '"rule_id": "ML001"' in json_str
    assert '"detector": "ml"' in json_str
    assert '"is_fixable": true' in json_str

    # Convert back to ReviewIssue
    restored = ReviewIssue.from_dict(json_data)

    assert restored.rule_id == issue.rule_id
    assert restored.severity == issue.severity
    assert restored.confidence == issue.confidence


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
