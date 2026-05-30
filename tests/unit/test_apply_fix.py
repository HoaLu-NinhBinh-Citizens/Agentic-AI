"""Unit tests for ApplyFixTool."""
import pytest
from pathlib import Path

from src.core.fix_engine.apply_fix import ApplyFixTool
from src.core.fix_engine.models import (
    Fix,
    FixBatch,
    FixResult,
    FixStatus,
    FixSeverity,
    ReviewFinding,
)


class TestApplyFixTool:
    def setup_method(self):
        self.tool = ApplyFixTool()

    def test_validate_fix_missing_file(self):
        valid, msg = self.tool.validate_fix("nonexistent.py", "old", "new")
        assert valid is False

    def test_validate_fix_old_text_not_found(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original content\n", encoding="utf-8")
        valid, msg = self.tool.validate_fix(str(f), "not present", "new")
        assert valid is False

    def test_validate_fix_success(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original\ncontent\n", encoding="utf-8")
        valid, msg = self.tool.validate_fix(str(f), "original", "modified")
        assert valid is True

    def test_apply_fix_creates_backup(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="test1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="original",
            new_text="modified",
            reason="test",
            severity=FixSeverity.WARNING,
        )
        result = tool.apply_fix(fix)
        assert result.success is True
        assert result.has_backup
        assert f.read_text(encoding="utf-8") == "modified\n"

    def test_apply_fix_without_old_text(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="test2",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="line1\nnew_content\n",
            reason="test",
            severity=FixSeverity.INFO,
        )
        result = tool.apply_fix(fix)
        assert result.success is True

    def test_apply_fix_failure(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("content\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="test3",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="not found",
            new_text="modified",
            reason="test",
            severity=FixSeverity.WARNING,
        )
        result = tool.apply_fix(fix)
        assert result.success is False

    def test_preview_fix(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("old content\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="preview1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="old content",
            new_text="new content",
            reason="test",
            severity=FixSeverity.WARNING,
        )
        old_disp, new_disp = tool.preview_fix(fix)
        assert "old content" in old_disp
        assert "new content" in new_disp

    def test_apply_batch(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="batch1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="line1",
            new_text="LINE1",
            reason="uppercase",
            severity=FixSeverity.INFO,
        )
        batch = tool.apply_batch([fix])
        assert batch.total_fixes >= 1

    def test_apply_batch_dry_run(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="dry1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="line1",
            new_text="modified",
            reason="test",
            severity=FixSeverity.INFO,
        )
        batch = tool.apply_batch([fix], dry_run=True)
        assert batch.total_fixes >= 1

    def test_apply_batch_skip_invalid(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="skip1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="not in file",
            new_text="modified",
            reason="test",
            severity=FixSeverity.INFO,
        )
        batch = tool.apply_batch([fix])
        assert batch.total_fixes >= 1
        assert batch.pending >= 0

    def test_rollback(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original\n", encoding="utf-8")
        tool = ApplyFixTool(workspace_root=str(tmp_path))
        fix = Fix(
            id="rollback1",
            file_path="test.py",
            line_start=1,
            line_end=1,
            old_text="original",
            new_text="modified",
            reason="test",
            severity=FixSeverity.INFO,
        )
        result = tool.apply_fix(fix)
        assert result.success is True
        assert f.read_text(encoding="utf-8") == "modified\n"
        restored = tool.rollback([result])
        assert restored >= 0

    def test_compute_hash(self):
        h1 = self.tool._compute_hash("hello")
        h2 = self.tool._compute_hash("hello")
        h3 = self.tool._compute_hash("world")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16


class TestFixModels:
    def test_fix_mark_applied(self):
        fix = Fix(
            id="f1",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
        )
        fix.mark_applied()
        assert fix.status == FixStatus.APPLIED

    def test_fix_mark_rejected(self):
        fix = Fix(
            id="f2",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
        )
        fix.mark_rejected()
        assert fix.status == FixStatus.REJECTED

    def test_fix_mark_failed(self):
        fix = Fix(
            id="f3",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
        )
        fix.mark_failed()
        assert fix.status == FixStatus.FAILED

    def test_fix_is_critical_error(self):
        fix = Fix(
            id="f4",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
            severity=FixSeverity.ERROR,
        )
        assert fix.is_critical is True

    def test_fix_is_not_critical_warning(self):
        fix = Fix(
            id="f5",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
            severity=FixSeverity.WARNING,
        )
        assert fix.is_critical is False

    def test_fix_location_same_line(self):
        fix = Fix(
            id="f6",
            file_path="a.py",
            line_start=5,
            line_end=5,
            old_text="",
            new_text="",
            reason="test",
        )
        assert ":5" in fix.location

    def test_fix_location_multi_line(self):
        fix = Fix(
            id="f7",
            file_path="a.py",
            line_start=3,
            line_end=7,
            old_text="",
            new_text="",
            reason="test",
        )
        assert "3-7" in fix.location

    def test_fix_default_severity(self):
        fix = Fix(
            id="f8",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
        )
        assert fix.severity == FixSeverity.WARNING

    def test_fix_batch_add(self):
        batch = FixBatch()
        fix = Fix(
            id="b1",
            file_path="a.py",
            line_start=1,
            line_end=1,
            old_text="",
            new_text="",
            reason="test",
        )
        batch.add(fix)
        assert batch.total_fixes == 1
        assert batch.total_files == 1

    def test_fix_batch_adds_unique_files(self):
        batch = FixBatch()
        f1 = Fix(
            id="b1", file_path="a.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        f2 = Fix(
            id="b2", file_path="a.py", line_start=2, line_end=2,
            old_text="", new_text="", reason="test",
        )
        f3 = Fix(
            id="b3", file_path="b.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        batch.add(f1)
        batch.add(f2)
        batch.add(f3)
        assert batch.total_fixes == 3
        assert batch.total_files == 2

    def test_fix_batch_update_counters(self):
        batch = FixBatch()
        f1 = Fix(
            id="b1", file_path="a.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
            severity=FixSeverity.ERROR,
        )
        f2 = Fix(
            id="b2", file_path="b.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
            severity=FixSeverity.WARNING,
        )
        batch.add(f1)
        batch.add(f2)
        f1.mark_applied()
        batch.update_counters()
        assert batch.applied == 1

    def test_fix_batch_pending(self):
        batch = FixBatch()
        fix = Fix(
            id="p1", file_path="a.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        batch.add(fix)
        assert batch.pending == 1

    def test_fix_batch_success_rate(self):
        batch = FixBatch()
        f1 = Fix(
            id="s1", file_path="a.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        f2 = Fix(
            id="s2", file_path="b.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        batch.add(f1)
        batch.add(f2)
        f1.mark_applied()
        batch.update_counters()
        assert batch.success_rate > 0

    def test_fix_batch_get_by_file(self):
        batch = FixBatch()
        f1 = Fix(
            id="gf1", file_path="a.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        f2 = Fix(
            id="gf2", file_path="b.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
        )
        batch.add(f1)
        batch.add(f2)
        assert len(batch.get_by_file("a.py")) == 1
        assert len(batch.get_by_file("b.py")) == 1

    def test_fix_batch_get_by_severity(self):
        batch = FixBatch()
        e = Fix(
            id="gs1", file_path="a.py", line_start=1, line_end=1,
            old_text="", new_text="", reason="test",
            severity=FixSeverity.ERROR,
        )
        w = Fix(
            id="gs2", file_path="a.py", line_start=2, line_end=2,
            old_text="", new_text="", reason="test",
            severity=FixSeverity.WARNING,
        )
        batch.add(e)
        batch.add(w)
        errors = batch.get_by_severity(FixSeverity.ERROR)
        assert len(errors) == 1
        assert errors[0].severity == FixSeverity.ERROR

    def test_fix_result_has_backup(self):
        result = FixResult(fix_id="r1", success=True, backup_path="/tmp/backup")
        assert result.has_backup is True

    def test_fix_result_no_backup(self):
        result = FixResult(fix_id="r2", success=False)
        assert result.has_backup is False

    def test_review_finding_to_fix(self):
        finding = ReviewFinding(
            file_path="test.py",
            line=10,
            rule_id="SEC001",
            message="Hardcoded secret detected",
            severity=FixSeverity.ERROR,
            suggested_fix="# REDACTED",
            confidence=0.95,
        )
        fix = finding.to_fix("fix-123")
        assert fix.id == "fix-123"
        assert fix.file_path == "test.py"
        assert fix.line_start == 10
        assert fix.line_end == 10
        assert fix.rule_id == "SEC001"
        assert fix.reason == "Hardcoded secret detected"
        assert fix.severity == FixSeverity.ERROR
        assert fix.created_by == "review_agent"


class TestFixStatus:
    def test_all_statuses(self):
        assert FixStatus.PENDING.value == "pending"
        assert FixStatus.APPLIED.value == "applied"
        assert FixStatus.REJECTED.value == "rejected"
        assert FixStatus.FAILED.value == "failed"
        assert FixStatus.SKIPPED.value == "skipped"


class TestFixSeverity:
    def test_all_severities(self):
        assert FixSeverity.ERROR.value == "error"
        assert FixSeverity.WARNING.value == "warning"
        assert FixSeverity.INFO.value == "info"
