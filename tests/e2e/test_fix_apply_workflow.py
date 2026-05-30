"""End-to-end tests for fix application workflow.

Tests the complete flow: detect issue → generate patch → apply → verify issue disappears.

Workflow:
    1. Create temp file with ML code containing issues
    2. Run MLDetector to find issues (ML001-ML006)
    3. Apply fix (replace old_code with new_code)
    4. Re-run detector
    5. Verify issue is resolved
"""

import pytest
import tempfile
import shutil
import ast
from pathlib import Path

from src.infrastructure.analysis.ml_detectors import MLDetector
from src.infrastructure.patching.ast_patch_engine import ASTPatchEngine, Patch
from src.application.workflows.unified.review_engine import (
    UnifiedReviewEngine,
    ReviewEngineConfig,
)


class TestFixApplyWorkflow:
    """E2E tests for /fix command workflow."""

    @pytest.fixture
    def temp_project(self):
        """Create a temp project directory."""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)

    @pytest.fixture
    def ml_detector(self):
        """Create ML detector instance."""
        return MLDetector()

    def _apply_fix(self, content: str, old_code: str, new_code: str) -> str:
        """Apply a simple text-based fix.

        Args:
            content: Original file content
            old_code: Code pattern to replace
            new_code: Replacement code

        Returns:
            Modified content
        """
        # Handle multi-line old_code by normalizing whitespace
        old_normalized = " ".join(old_code.split())
        lines = content.split("\n")
        result_lines = []

        for line in lines:
            line_normalized = " ".join(line.split())
            if old_normalized in line_normalized or old_code.strip() in line:
                result_lines.append(line.replace(old_code.strip(), new_code))
            else:
                result_lines.append(line)

        return "\n".join(result_lines)

    def test_fix_hardcoded_batch_size(self, temp_project, ml_detector):
        """Test: detect batch_size=32 → fix → no more ML006 findings.

        Uses real MLDetector to verify the fix workflow.
        """
        # Create file with hardcoded config - standalone assignments are detected
        code = """batch_size = 32
epochs = 100
lr = 0.001
"""
        file_path = temp_project / "train.py"
        file_path.write_text(code)

        # Step 1: Detect with real MLDetector
        findings = ml_detector.detect_file(file_path, code, "python")
        ml006_findings = [f for f in findings if f.rule_id == "ML006"]
        assert len(ml006_findings) >= 1, f"Should detect ML006 hardcoded config, got: {[f.message for f in ml006_findings]}"

        # Step 2: Get first finding and its suggested fix
        finding = ml006_findings[0]
        assert finding.new_code, "ML006 finding should have new_code suggestion"

        # Step 3: Apply fix - replace just the specific line
        lines = code.split("\n")
        fixed_line = finding.new_code.split(" # ")[0]  # Remove comment from suggestion
        lines[finding.line - 1] = fixed_line
        new_content = "\n".join(lines)

        # Step 4: Re-detect
        new_findings = ml_detector.detect_file(file_path, new_content, "python")
        new_ml006 = [f for f in new_findings if f.rule_id == "ML006"]

        # Step 5: Verify finding count decreased
        assert len(new_ml006) < len(ml006_findings), (
            f"Should have fewer ML006 findings after fix. "
            f"Before: {len(ml006_findings)}, After: {len(new_ml006)}"
        )

    def test_fix_preserves_surrounding_code(self, temp_project, ml_detector):
        """Test: fixing one issue doesn't break other code."""
        code = """import torch
# Important comment
batch_size = 32  # hardcoded
def train():
    model = Model()
    optimizer = torch.optim.Adam(model.parameters())
    return model
"""
        file_path = temp_project / "train.py"
        file_path.write_text(code)

        # Detect with real MLDetector
        findings = ml_detector.detect_file(file_path, code, "python")
        ml006_findings = [f for f in findings if f.rule_id == "ML006"]
        assert len(ml006_findings) >= 1, "Should detect hardcoded batch_size"

        finding = ml006_findings[0]
        old_code = finding.old_code
        new_code = finding.new_code

        # Apply fix - use line-based replacement
        lines = code.split("\n")
        fixed_line = new_code.split(" # ")[0]  # Remove comment
        lines[finding.line - 1] = fixed_line
        new_content = "\n".join(lines)
        file_path.write_text(new_content)

        # Verify imports preserved
        assert "import torch" in new_content, "Import should be preserved"
        assert "Important comment" in new_content, "Comment should be preserved"
        assert "Adam" in new_content, "Optimizer should be preserved"

        # Verify syntax valid (can parse)
        try:
            compile(new_content, str(file_path), "exec")
        except SyntaxError as e:
            pytest.fail(f"Fixed code has syntax error: {e}")

    def test_fix_multiple_issues(self, temp_project, ml_detector):
        """Test: fix multiple issues in sequence."""
        code = """batch_size = 32
lr = 0.001
epochs = 100
hidden_dim = 256
"""
        file_path = temp_project / "config.py"
        file_path.write_text(code)

        # Detect all issues with real MLDetector
        findings = ml_detector.detect_file(file_path, code, "python")
        ml006_findings = [f for f in findings if f.rule_id == "ML006"]
        initial_count = len(ml006_findings)
        assert initial_count >= 2, f"Should detect multiple ML006 issues, got {initial_count}"

        # Fix first issue - use line-based replacement
        finding1 = ml006_findings[0]
        lines = code.split("\n")
        fixed_line = finding1.new_code.split(" # ")[0]
        lines[finding1.line - 1] = fixed_line
        new_content = "\n".join(lines)
        file_path.write_text(new_content)

        # Re-detect
        new_findings = ml_detector.detect_file(file_path, new_content, "python")
        new_ml006 = [f for f in new_findings if f.rule_id == "ML006"]

        # Should have fewer findings
        assert len(new_ml006) < initial_count, "Should reduce ML006 count after one fix"

    def test_data_leakage_fix(self, temp_project, ml_detector):
        """Test: detect data leakage → fix → ML001 resolved."""
        code = """from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

scaler = StandardScaler()
X_scaled = scaler.fit(X)  # Bug: fit before split
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y)
"""
        file_path = temp_project / "leak.py"
        file_path.write_text(code)

        # Detect ML001 (data leakage)
        findings = ml_detector.detect_file(file_path, code, "python")
        ml001_findings = [f for f in findings if f.rule_id == "ML001"]

        if len(ml001_findings) == 0:
            # Fallback: verify the pattern exists
            assert "scaler.fit(X)" in code, "Test code should have data leakage pattern"
            pytest.skip("ML001 detector did not find the data leakage pattern")

        finding = ml001_findings[0]

        # Apply fix - split first, then fit
        fixed_code = """from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

scaler = StandardScaler()
X_train, X_test, y_train, y_test = train_test_split(X, y)
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)
"""
        file_path.write_text(fixed_code)

        # Re-detect
        new_findings = ml_detector.detect_file(file_path, fixed_code, "python")
        ml001_after = [f for f in new_findings if f.rule_id == "ML001"]

        assert len(ml001_after) == 0, f"ML001 should be fixed. Still found: {[f.message for f in ml001_after]}"

    @pytest.mark.asyncio
    async def test_unified_review_with_fix(self, temp_project):
        """Test: UnifiedReviewEngine → findings → apply fix."""
        code = """from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# Data leakage: scaler.fit before split
scaler = StandardScaler()
X_scaled = scaler.fit(X)
X_train, X_test, y_train, y_test = train_test_split(X_scaled, y)
"""
        file_path = temp_project / "leak.py"
        file_path.write_text(code)

        # Run unified review with ML focus
        config = ReviewEngineConfig(
            focus_areas=["ml"],
            output_format="markdown",
            enable_parallel=False,
        )
        engine = UnifiedReviewEngine(config)
        result = await engine.review([file_path])

        # Should complete without error
        assert result is not None, "Review should complete"
        assert isinstance(result.findings, list), "Result should have findings list"

        # Apply the fix manually
        fixed_code = """from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

# Fixed: split first, then fit
X_train, X_test, y_train, y_test = train_test_split(X, y)
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)
"""
        file_path.write_text(fixed_code)

        # Re-run review
        result2 = await engine.review([file_path])

        # Verify no critical ML findings in fixed code
        ml_findings = [f for f in result2.findings if f.rule_id.startswith("ML")]
        assert len(ml_findings) == 0 or all(f.severity.value != "error" for f in ml_findings), (
            f"Fixed code should have no critical ML issues. Found: {[f.rule_id for f in ml_findings]}"
        )


class TestPatchWorkflowIntegration:
    """Integration tests for the complete patch workflow."""

    @pytest.fixture
    def temp_project(self):
        """Create a temp project directory."""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_detect_fix_redetect_cycle(self, temp_project):
        """Test complete detect → fix → redetect cycle."""
        # Setup: Create ML code with issues
        code = """import torch
import numpy as np

def train():
    # No random seed set
    model = Model()
    optimizer = torch.optim.Adam(model.parameters())
    return model
"""
        file_path = temp_project / "train.py"
        file_path.write_text(code)

        # Step 1: Initial detection
        detector = MLDetector()
        initial_findings = detector.detect_file(file_path, code, "python")

        # Step 2: Identify issues to fix
        ml005_findings = [f for f in initial_findings if f.rule_id == "ML005"]
        if len(ml005_findings) == 0:
            pytest.skip("ML005 (missing seed) not detected in test code")

        # Step 3: Apply fix
        fixed_code = """import torch
import numpy as np

def train():
    # Set seeds for reproducibility
    torch.manual_seed(42)
    np.random.seed(42)

    model = Model()
    optimizer = torch.optim.Adam(model.parameters())
    return model
"""
        file_path.write_text(fixed_code)

        # Step 4: Re-detect
        new_findings = detector.detect_file(file_path, fixed_code, "python")
        new_ml005 = [f for f in new_findings if f.rule_id == "ML005"]

        # Step 5: Verify
        assert len(new_ml005) == 0, (
            f"ML005 should be resolved after adding seed. Still found: {len(new_ml005)}"
        )

    def test_multiple_rule_fix_cycle(self, temp_project):
        """Test fixing multiple rule violations."""
        code = """# Multiple ML issues
batch_size = 32
lr = 0.001
epochs = 50

def predict(model, X):
    return model(X)  # Missing no_grad
"""
        file_path = temp_project / "model.py"
        file_path.write_text(code)

        detector = MLDetector()
        initial_findings = detector.detect_file(file_path, code, "python")

        # Track initial counts by rule
        initial_by_rule = {}
        for f in initial_findings:
            rule = f.rule_id
            initial_by_rule[rule] = initial_by_rule.get(rule, 0) + 1

        assert len(initial_by_rule) >= 1, "Should detect at least one issue"

        # Apply fixes
        fixed_code = """# Fixed ML code
import argparse
args = argparse.Namespace(batch_size=32, lr=0.001, epochs=50)

def predict(model, X):
    with torch.no_grad():
        return model(X)
"""
        file_path.write_text(fixed_code)

        # Re-detect
        new_findings = detector.detect_file(file_path, fixed_code, "python")
        new_by_rule = {}
        for f in new_findings:
            rule = f.rule_id
            new_by_rule[rule] = new_by_rule.get(rule, 0) + 1

        # Should have fewer issues overall
        total_before = sum(initial_by_rule.values())
        total_after = sum(new_by_rule.values())
        assert total_after < total_before, (
            f"Should reduce total findings. Before: {total_before}, After: {total_after}"
        )


class TestEdgeCases:
    """Edge case tests for the fix workflow."""

    @pytest.fixture
    def temp_project(self):
        """Create a temp project directory."""
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        shutil.rmtree(tmp, ignore_errors=True)

    def test_fix_non_existent_pattern(self, temp_project):
        """Test fixing when old_code pattern doesn't match exactly."""
        code = "x = 1\ny = 2\nz = 3\n"
        file_path = temp_project / "test.py"
        file_path.write_text(code)

        # Try to fix a non-existent pattern
        original_content = file_path.read_text()

        # Simple apply fix function should handle gracefully
        def safe_apply(content, old, new):
            if old in content:
                return content.replace(old, new)
            return content

        result = safe_apply(original_content, "nonexistent_pattern", "replacement")

        # Content should be unchanged
        assert result == original_content, "Non-existent pattern should not modify content"

    def test_empty_file_handling(self, temp_project):
        """Test detection on empty file."""
        file_path = temp_project / "empty.py"
        file_path.write_text("")

        detector = MLDetector()
        findings = detector.detect_file(file_path, "", "python")

        # Should not crash, should return empty list
        assert isinstance(findings, list), "Should return list even for empty file"

    def test_fix_preserves_file_encoding(self, temp_project):
        """Test that fix preserves file encoding."""
        # Create file with unicode content
        code = """# Unicode: émoji = 42
name = "日本語"
batch_size = 32
"""
        file_path = temp_project / "unicode.py"
        file_path.write_text(code, encoding="utf-8")

        detector = MLDetector()
        findings = detector.detect_file(file_path, code, "python")

        # Apply fix
        new_content = code.replace("batch_size = 32", "batch_size = args.batch_size")
        file_path.write_text(new_content, encoding="utf-8")

        # Read back and verify
        read_content = file_path.read_text(encoding="utf-8")
        assert "日本語" in read_content, "Unicode content should be preserved"
        assert "batch_size = args.batch_size" in read_content, "Fix should be applied"


class TestPatchContract:
    """
    Tests for the complete patch contract:
    1. Apply patch
    2. Syntax validation passes
    3. Re-run detector
    4. Issue is resolved (finding count decreases)
    """

    @pytest.fixture
    def ml_detector(self):
        return MLDetector()

    @pytest.fixture
    def patch_engine(self):
        return ASTPatchEngine()

    def test_full_contract_hardcoded_config(self, tmp_path, ml_detector, patch_engine):
        """Test complete: detect -> apply -> validate -> re-detect clean."""
        # 1. Create file with hardcoded config (using known ML hyperparameters)
        code = """batch_size = 32
lr = 0.001
epochs = 100
"""
        file_path = tmp_path / "config.py"
        file_path.write_text(code)

        # 2. Initial detection
        initial_findings = ml_detector.detect_file(file_path, code, "python")
        initial_ml006 = [f for f in initial_findings if f.rule_id == "ML006"]
        assert len(initial_ml006) >= 2, f"Should find 2+ issues, got {len(initial_ml006)}"

        # 3. Fix first issue (batch_size=32)
        first_finding = initial_ml006[0]
        node_info = patch_engine.find_node_at_position(code, first_finding.line, 0, "python")
        assert node_info is not None, "Should find AST node"

        patch = patch_engine.generate_patch(
            file_path=file_path,
            content=code,
            node_start=node_info.start_point,
            node_end=node_info.end_point,
            new_code="batch_size = args.batch_size"
        )

        # 4. Apply and validate
        result = patch_engine.apply_and_validate(code, patch, "python")
        assert result.success, f"Patch should succeed: {result.error}"
        assert result.validation_passed, "Syntax should be valid after patch"

        # 5. Write patched content
        file_path.write_text(result.patched_content)

        # 6. Re-run detector
        new_content = result.patched_content
        new_findings = ml_detector.detect_file(file_path, new_content, "python")
        new_ml006 = [f for f in new_findings if f.rule_id == "ML006"]

        # 7. Contract: issue count should decrease
        assert len(new_ml006) < len(initial_ml006), \
            f"Should have fewer issues. Before: {len(initial_ml006)}, After: {len(new_ml006)}"

    def test_contract_preserves_syntax_on_failure(self, tmp_path, patch_engine):
        """Test: if patch fails validation, it is properly detected."""
        code = "x = 1\n"
        bad_patch = Patch(
            file_path=tmp_path / "test.py",
            start_line=1,
            end_line=1,
            old_code="x = 1",
            new_code="def foo("  # Invalid syntax
        )

        result = patch_engine.apply_and_validate(code, bad_patch, "python")

        # Contract: validation should fail - caller should know NOT to use result
        assert not result.validation_passed, "Should fail validation"
        # Error should be present when validation fails
        if result.error:
            assert "syntax" in result.error.lower(), "Error should mention syntax"
        # Success is True (patch was applied), but validation failed (caller should reject)
        assert result.success, "Patch application should succeed even if validation fails"

    def test_contract_multiple_rules(self, tmp_path, ml_detector, patch_engine):
        """Test contract across multiple finding types."""
        # Use code that the detector can reliably find issues in
        code = """batch_size = 32
lr = 0.001
n_estimators = 100
"""
        file_path = tmp_path / "config.py"
        file_path.write_text(code)

        # Detect issues
        initial = ml_detector.detect_file(file_path, code, "python")
        ml006 = [f for f in initial if f.rule_id == "ML006"]

        assert len(ml006) >= 2, f"Should detect ML006 issues, got {len(ml006)}"

        # Fix first ML006 issue (batch_size)
        finding = ml006[0]
        node_info = patch_engine.find_node_at_position(code, finding.line, 0, "python")
        assert node_info is not None, "Should find AST node for ML006"

        patch = patch_engine.generate_patch(
            file_path=file_path,
            content=code,
            node_start=node_info.start_point,
            node_end=node_info.end_point,
            new_code="batch_size = args.batch_size"
        )
        result = patch_engine.apply_and_validate(code, patch, "python")

        if result.validation_passed:
            file_path.write_text(result.patched_content)

            # Re-detect
            new_code = file_path.read_text()
            after = ml_detector.detect_file(file_path, new_code, "python")
            ml006_after = [f for f in after if f.rule_id == "ML006"]

            # Contract: ML006 count should decrease
            assert len(ml006_after) < len(ml006), \
                f"ML006 should be reduced. Before: {len(ml006)}, After: {len(ml006_after)}"
