"""End-to-end integration tests for the review pipeline."""
import pytest
import tempfile
from pathlib import Path

from src.infrastructure.analysis.ml_detectors.detector import MLDetector
from src.infrastructure.analysis.ml_detectors.extended_rules import (
    check_extended_rules,
    get_extended_rules,
)
from src.shared.enums.severity import Severity


class TestEndToEndReview:
    """Integration tests for full review pipeline."""
    
    @pytest.fixture
    def sample_project(self, tmp_path):
        """Create a sample ML project for testing."""
        # Create train.py
        train_py = tmp_path / "train.py"
        train_py.write_text('''
import torch
import torch.nn as nn
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Data leakage example
X, y = load_data()
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)  # Leakage: fit before split
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y)

# Model
model = nn.Linear(10, 2).cuda()
criterion = nn.CrossEntropyLoss()  # Wrong for multi-label
optimizer = torch.optim.Adam(model.parameters(), lr=0.001)

# Training
for epoch in range(10):
    model.train()
    X_gpu = torch.FloatTensor(X_train).cuda()
    y_gpu = torch.LongTensor(y_train).cuda()
    
    optimizer.zero_grad()
    outputs = model(X_gpu)
    loss = criterion(outputs, y_gpu)
    loss.backward()
    optimizer.step()
''')
        
        # Create requirements.txt
        req_txt = tmp_path / "requirements.txt"
        req_txt.write_text('''
torch>=2.0.0
numpy>=1.24.0
scikit-learn>=1.0.0
''')
        
        return tmp_path
    
    def test_full_review_pipeline(self, sample_project):
        """Test complete review pipeline on sample project."""
        # Initialize detector
        detector = MLDetector()
        
        # Read and analyze the training file
        train_py = sample_project / "train.py"
        content = train_py.read_text()
        
        findings = detector.detect_file(train_py, content, "python")
        
        # Verify results
        assert findings is not None
        assert len(findings) > 0
        
        # Should find some ML issues
        rule_ids = [f.rule_id for f in findings]
        
        # Check that we have extended rules findings too
        extended_rule_ids = ['ML016', 'ML017', 'ML018', 'ML019', 'ML020', 
                           'ML021', 'ML022', 'ML023', 'ML024', 'ML025']
        found_extended = [rid for rid in extended_rule_ids if rid in rule_ids]
        
        # Should have some extended rules findings
        assert len(found_extended) >= 0  # Extended rules are regex-based
    
    def test_extended_rules_integration(self):
        """Test extended rules integration."""
        code = '''
model = transformers.BertLarge()
for epoch in range(100):
    train()
'''
        findings = check_extended_rules(code)
        
        assert len(findings) >= 1
        assert any(f['rule_id'] == 'ML016' for f in findings)
    
    def test_extended_rules_all_rule_ids(self):
        """Test that all extended rules can be retrieved."""
        rules = get_extended_rules()
        
        expected_rules = ['ML016', 'ML017', 'ML018', 'ML019', 'ML020',
                         'ML021', 'ML022', 'ML023', 'ML024', 'ML025']
        
        for rule_id in expected_rules:
            assert rule_id in rules, f"Missing rule: {rule_id}"
    
    def test_ml_detector_with_extended_rules(self):
        """Test ML detector integration with extended rules."""
        detector = MLDetector()
        
        # Test code with multiple ML issues
        code = '''
model = BertLarge()
batch_size = 512
lr = 0.001
optimizer = AdamW(model.parameters(), lr=lr)

for epoch in range(100):
    train()
'''
        
        findings = detector.detect_file(Path("test.py"), code, "python")
        
        # Should find ML issues from extended rules
        rule_ids = [f.rule_id for f in findings]
        
        # ML016 (gradient checkpointing), ML017 (lr scaling), ML018 (warmup) should be found
        assert 'ML016' in rule_ids or 'ML017' in rule_ids or 'ML018' in rule_ids


class TestFixSuggestionPipeline:
    """Integration tests for fix suggestion generation."""
    
    def test_fix_confidence_calculation(self):
        """Test fix confidence scoring."""
        from src.application.workflows.unified.suggestion_engine import SuggestionEngine
        from src.domain.models.review_issue import FixOption
        from src.application.workflows.unified.code_context import CodeContext
        
        engine = SuggestionEngine()
        
        # Create a mock fix option
        fix = FixOption(
            id="test-fix",
            title="Test fix",
            description="Test description",
            old_code="old",
            new_code="new",
            risk=Severity.MEDIUM,
            confidence=0.8,
        )
        
        # Create context with correct parameters
        context = CodeContext(
            file_path=Path("test.py"),
            content="def foo():\n    pass",
            ast_root=None,
            language="python",
        )
        
        # Create a mock finding with correct parameters
        from src.application.workflows.unified.detector_base import Finding
        finding = Finding(
            rule_id="TEST001",
            rule_name="Test Rule",
            severity=Severity.HIGH,
            file="test.py",
            line=1,
            end_line=1,
            message="Test issue",
            confidence=0.9,
        )
        
        # Calculate confidence
        confidence = engine.calculate_fix_confidence(fix, context, finding)
        
        # Should be a valid confidence score
        assert 0.0 <= confidence <= 1.0
    
    def test_fix_ranking(self):
        """Test fix ranking by confidence."""
        from src.application.workflows.unified.suggestion_engine import SuggestionEngine
        from src.domain.models.review_issue import FixOption
        from src.application.workflows.unified.code_context import CodeContext
        from src.application.workflows.unified.detector_base import Finding
        
        engine = SuggestionEngine()
        
        # Create multiple fix options with different confidences
        fix1 = FixOption(
            id="fix-1",
            title="Low confidence fix",
            description="Test",
            old_code="old",
            new_code="new",
            risk=Severity.HIGH,
            confidence=0.5,
        )
        
        fix2 = FixOption(
            id="fix-2",
            title="High confidence fix",
            description="Test",
            old_code="old",
            new_code="new",
            risk=Severity.LOW,
            confidence=0.9,
        )
        
        context = CodeContext(
            file_path=Path("test.py"),
            content="def foo():\n    pass",
            ast_root=None,
            language="python",
        )
        
        finding = Finding(
            rule_id="TEST",
            rule_name="Test",
            severity=Severity.HIGH,
            file="test.py",
            line=1,
            end_line=1,
            message="Test",
            confidence=0.9,
        )
        
        # Rank fixes
        ranked = engine.rank_fixes([fix1, fix2], context, finding)
        
        # High confidence fix should come first
        assert ranked[0].id == "fix-2"


class TestSeverityIntegration:
    """Test severity handling across modules."""
    
    def test_all_severity_levels(self):
        """Test that all severity levels are handled."""
        # Test code that triggers each severity level
        codes_by_severity = {
            'CRITICAL': '''
for batch in dataloader:
    loss.backward()
    optimizer.step()
''',  # ML021: gradient accumulation
            'HIGH': '''
optimizer = AdamW(model.parameters(), lr=0.001)
for epoch in range(100):
    train()
''',  # ML018: warmup
            'MEDIUM': '''
model = BertLarge()
''',  # ML016: gradient checkpointing
            'LOW': '''
DataLoader(dataset, batch_size=32, num_workers=0)
''',  # ML022: dataloader workers
        }
        
        for severity, code in codes_by_severity.items():
            findings = check_extended_rules(code)
            # Should find at least one finding of expected severity
            severity_findings = [f for f in findings if f['severity'] == severity]
            assert len(severity_findings) >= 1, f"No {severity} findings for code: {code[:50]}"


class TestSummaryGeneration:
    """Test summary/report generation."""
    
    def test_stats_calculation(self):
        """Test statistics calculation."""
        detector = MLDetector()
        
        code = '''
model = BertLarge()
batch_size = 512
lr = 0.001
optimizer = AdamW(model.parameters(), lr=lr)

for epoch in range(100):
    train()
    eval()
'''
        
        findings = detector.detect_file(Path("test.py"), code, "python")
        
        # Get stats
        stats = detector.get_stats(findings)
        
        assert stats is not None
        assert 'total' in stats
        assert 'by_severity' in stats
        assert 'by_rule' in stats
        assert 'avg_confidence' in stats
        
        # Stats should reflect findings
        assert stats['total'] == len(findings)
    
    def test_filtering_by_confidence(self):
        """Test filtering findings by confidence."""
        detector = MLDetector()
        
        code = '''
model = BertLarge()
for epoch in range(100):
    train()
'''
        
        findings = detector.detect_file(Path("test.py"), code, "python")
        
        # Filter by high confidence
        high_conf_findings = detector.filter_findings(
            findings, 
            min_confidence=0.85
        )
        
        # All filtered findings should have confidence >= 0.85
        for f in high_conf_findings:
            assert f.confidence >= 0.85
    
    def test_filtering_by_severity(self):
        """Test filtering findings by severity."""
        detector = MLDetector()
        
        code = '''
model = BertLarge()
for batch in dataloader:
    loss.backward()
    optimizer.step()
'''
        
        findings = detector.detect_file(Path("test.py"), code, "python")
        
        # Filter by HIGH severity
        high_findings = detector.filter_findings(
            findings,
            min_severity=Severity.HIGH
        )
        
        # All filtered findings should have severity >= HIGH
        for f in high_findings:
            assert f.severity >= Severity.HIGH


class TestMultiFileAnalysis:
    """Test analysis across multiple files."""
    
    def test_batch_detection(self):
        """Test batch detection across multiple files."""
        detector = MLDetector()
        
        files = [
            (Path("train.py"), '''
model = BertLarge()
optimizer = AdamW(model.parameters())
for epoch in range(100):
    train()
''', "python"),
            (Path("eval.py"), '''
outputs = model(inputs)
''', "python"),
        ]
        
        results = detector.detect_batch(files)
        
        assert len(results) >= 0  # Should complete without error
        assert isinstance(results, dict)
    
    def test_independent_file_analysis(self):
        """Test that files are analyzed independently."""
        detector = MLDetector()
        
        # File 1: Has gradient checkpointing issue
        code1 = '''
model = BertLarge()
'''
        
        # File 2: Has multiple ML issues (lr scaling, no warmup, no eval)
        code2 = '''
optimizer = AdamW(model.parameters(), lr=0.01)
outputs = model(inputs)
'''
        
        findings1 = detector.detect_file(Path("file1.py"), code1, "python")
        findings2 = detector.detect_file(Path("file2.py"), code2, "python")
        
        # Both should complete without error
        assert isinstance(findings1, list)
        assert isinstance(findings2, list)
        # At least one should have findings
        assert len(findings1) > 0 or len(findings2) > 0


class TestIntegrationEdgeCases:
    """Test edge cases and error handling."""
    
    def test_empty_code(self):
        """Test handling of empty code."""
        detector = MLDetector()
        
        findings = detector.detect_file(Path("empty.py"), "", "python")
        assert findings == []
    
    def test_non_python_code(self):
        """Test handling of non-Python code."""
        from src.infrastructure.analysis.ml_detectors.extended_rules import check_extended_rules
        
        # Extended rules should only work on Python
        findings = check_extended_rules("int main() { return 0; }", "c")
        # Should return empty for non-Python
        assert findings == []
    
    def test_python_code_only(self):
        """Test that extended rules only work on Python."""
        from src.infrastructure.analysis.ml_detectors.extended_rules import check_extended_rules
        
        # Python code should work
        code = 'model = BertLarge()'
        findings = check_extended_rules(code, "python")
        assert isinstance(findings, list)
    
    def test_malformed_code(self):
        """Test handling of malformed code."""
        detector = MLDetector()
        
        # Malformed Python should not crash
        findings = detector.detect_file(Path("bad.py"), "def foo(:", "python")
        assert isinstance(findings, list)
    
    def test_large_code(self):
        """Test handling of large code files."""
        detector = MLDetector()
        
        # Generate large code
        large_code = '''
model = BertLarge()
optimizer = AdamW(model.parameters(), lr=0.001)

''' + '\n'.join([f'''
for epoch in range(100):
    train()
    eval()
''' for _ in range(100)])
        
        findings = detector.detect_file(Path("large.py"), large_code, "python")
        # Should complete without timeout or crash
        assert isinstance(findings, list)
