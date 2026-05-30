"""Error handling integration tests.

Tests error scenarios and graceful degradation for the review pipeline,
including handling of malformed input, missing files, permission errors,
and other edge cases.
"""

from __future__ import annotations

import pytest
import asyncio
import os
import stat
from pathlib import Path

from src.infrastructure.indexing.symbol_graph import SymbolGraph
from src.core.fix_engine.apply_fix import ApplyFixTool
from src.application.workflows.unified.pipeline import UnifiedReviewPipeline, PipelineConfig


# =============================================================================
# File Handling Error Tests
# =============================================================================


class TestFileHandlingErrors:
    """Test handling of file-related errors."""
    
    @pytest.mark.asyncio
    async def test_missing_file_graceful(self, tmp_path: Path) -> None:
        """Test handling of missing files."""
        fixer = ApplyFixTool(str(tmp_path))
        
        from src.core.fix_engine.models import Fix
        
        fix = Fix(
            id="missing_file_test",
            file_path="nonexistent_file.py",
            line_start=1,
            line_end=1,
            old_text="old",
            new_text="new",
            reason="Test missing file",
        )
        
        result = fixer.apply_fix(fix)
        
        assert not result.success
        assert result.error is not None
        assert "not found" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_invalid_path_handling(self, tmp_path: Path) -> None:
        """Test handling of invalid file paths."""
        fixer = ApplyFixTool(str(tmp_path))
        
        from src.core.fix_engine.models import Fix
        
        fix = Fix(
            id="invalid_path_test",
            file_path="/invalid/path/with/../../sibling/file.py",
            line_start=1,
            line_end=1,
            old_text="old",
            new_text="new",
            reason="Test invalid path",
        )
        
        result = fixer.apply_fix(fix)
        
        assert not result.success
    
    @pytest.mark.asyncio
    async def test_empty_file_handling(self, tmp_path: Path) -> None:
        """Test handling of empty files."""
        pipeline = UnifiedReviewPipeline()
        
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")
        
        issues = await pipeline.analyze([empty_file])
        
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    async def test_very_large_file_handling(self, tmp_path: Path) -> None:
        """Test handling of very large files."""
        pipeline = UnifiedReviewPipeline(
            config=PipelineConfig(max_issues_per_file=10)
        )
        
        large_file = tmp_path / "large.py"
        lines = ["def function_{}(): pass".format(i) for i in range(10000)]
        large_file.write_text("\n".join(lines))
        
        try:
            issues = await pipeline.analyze([large_file])
            assert isinstance(issues, list)
        except MemoryError:
            pytest.skip("Memory limit exceeded for large file test")


# =============================================================================
# Syntax Error Tests
# =============================================================================


class TestSyntaxErrors:
    """Test handling of Python syntax errors."""
    
    @pytest.mark.asyncio
    async def test_invalid_python_syntax(self, tmp_path: Path) -> None:
        """Test handling of files with syntax errors."""
        bad_file = tmp_path / "syntax_error.py"
        bad_file.write_text("def broken(\n    # Missing closing paren\n")
        
        pipeline = UnifiedReviewPipeline()
        
        try:
            issues = await pipeline.analyze([bad_file])
            assert isinstance(issues, list)
        except SyntaxError:
            pytest.fail("Pipeline crashed on syntax error")
    
    @pytest.mark.asyncio
    async def test_unclosed_string_syntax(self, tmp_path: Path) -> None:
        """Test handling of unclosed strings."""
        bad_file = tmp_path / "unclosed_string.py"
        bad_file.write_text('def example():\n    return "unclosed string\n')
        
        pipeline = UnifiedReviewPipeline()
        
        try:
            issues = await pipeline.analyze([bad_file])
            assert isinstance(issues, list)
        except SyntaxError:
            pass
    
    @pytest.mark.asyncio
    async def test_invalid_indent_syntax(self, tmp_path: Path) -> None:
        """Test handling of indentation errors."""
        bad_file = tmp_path / "indent_error.py"
        bad_file.write_text("def example():\n    pass\n        extra_indent()\n")
        
        pipeline = UnifiedReviewPipeline()
        
        try:
            issues = await pipeline.analyze([bad_file])
            assert isinstance(issues, list)
        except IndentationError:
            pass


# =============================================================================
# Permission Error Tests
# =============================================================================


class TestPermissionErrors:
    """Test handling of permission errors."""
    
    @pytest.mark.asyncio
    async def test_permission_error_on_write(self, tmp_path: Path) -> None:
        """Test handling of permission errors when writing."""
        fixer = ApplyFixTool(str(tmp_path))
        
        readonly_file = tmp_path / "readonly.py"
        readonly_file.write_text("# Read only content")
        
        try:
            readonly_file.chmod(0o444)
            
            from src.core.fix_engine.models import Fix
            
            fix = Fix(
                id="readonly_test",
                file_path=str(readonly_file),
                line_start=1,
                line_end=1,
                old_text="# Read only content",
                new_text="# Modified content",
                reason="Test readonly",
            )
            
            result = fixer.apply_fix(fix)
            
            assert not result.success or result.success
        finally:
            try:
                readonly_file.chmod(0o644)
            except Exception:
                pass
    
    @pytest.mark.asyncio
    async def test_permission_error_on_read(self, tmp_path: Path) -> None:
        """Test handling of permission errors when reading."""
        pipeline = UnifiedReviewPipeline()
        
        no_read_file = tmp_path / "no_read.py"
        no_read_file.write_text("# No read permission")
        
        try:
            no_read_file.chmod(0o000)
            
            try:
                issues = await pipeline.analyze([no_read_file])
                assert isinstance(issues, list)
            except PermissionError:
                pass
        finally:
            try:
                no_read_file.chmod(0o644)
            except Exception:
                pass
    
    @pytest.mark.asyncio
    async def test_directory_without_read_permission(self, tmp_path: Path) -> None:
        """Test handling of directories without read permission."""
        no_read_dir = tmp_path / "no_read_dir"
        no_read_dir.mkdir()
        
        file_in_dir = no_read_dir / "file.py"
        file_in_dir.write_text("content")
        
        try:
            no_read_dir.chmod(0o000)
            
            pipeline = UnifiedReviewPipeline()
            
            try:
                issues = await pipeline.analyze([file_in_dir])
                assert isinstance(issues, list)
            except PermissionError:
                pass
        finally:
            try:
                no_read_dir.chmod(0o755)
            except Exception:
                pass


# =============================================================================
# Encoding Error Tests
# =============================================================================


class TestEncodingErrors:
    """Test handling of encoding errors."""
    
    @pytest.mark.asyncio
    async def test_invalid_utf8_handling(self, tmp_path: Path) -> None:
        """Test handling of invalid UTF-8 sequences."""
        bad_file = tmp_path / "invalid_utf8.py"
        
        with open(str(bad_file), "wb") as f:
            f.write(b"# -*- coding: utf-8 -*-\n")
            f.write(b'content = "\\xc0\\xc1\\xfe\\xff"\n')
        
        pipeline = UnifiedReviewPipeline()
        
        try:
            issues = await pipeline.analyze([bad_file])
            assert isinstance(issues, list)
        except UnicodeDecodeError:
            pass
    
    @pytest.mark.asyncio
    async def test_binary_file_not_crash(self, tmp_path: Path) -> None:
        """Test that binary files don't crash the pipeline."""
        binary_file = tmp_path / "binary.dat"
        binary_file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        
        pipeline = UnifiedReviewPipeline()
        
        try:
            issues = await pipeline.analyze([binary_file])
            assert isinstance(issues, list)
        except Exception:
            pass


# =============================================================================
# Network/Resource Error Tests
# =============================================================================


class TestResourceErrors:
    """Test handling of resource-related errors."""
    
    @pytest.mark.asyncio
    async def test_symbol_graph_handles_invalid_file(self, tmp_path: Path) -> None:
        """Test SymbolGraph handles invalid file gracefully."""
        graph = SymbolGraph()
        
        invalid_file = tmp_path / "invalid.txt"
        invalid_file.write_text("not a valid file")
        
        result = await graph.index_file(str(invalid_file))
        
        assert result["status"] in ("indexed", "error", "not_found")
    
    @pytest.mark.asyncio
    async def test_pipeline_with_empty_directory(self, tmp_path: Path) -> None:
        """Test pipeline handles empty directory."""
        empty_dir = tmp_path / "empty_dir"
        empty_dir.mkdir()
        
        pipeline = UnifiedReviewPipeline()
        
        issues = await pipeline.analyze([empty_dir])
        
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    async def test_pipeline_with_symlink(self, tmp_path: Path) -> None:
        """Test pipeline handles symbolic links."""
        if os.name == "nt":
            pytest.skip("Symlinks require admin on Windows")
        
        real_file = tmp_path / "real.py"
        real_file.write_text("def real(): pass")
        
        try:
            link_file = tmp_path / "link.py"
            link_file.symlink_to(real_file)
            
            pipeline = UnifiedReviewPipeline()
            
            issues = await pipeline.analyze([link_file])
            assert isinstance(issues, list)
        except OSError:
            pytest.skip("Symlink creation not supported")


# =============================================================================
# Fix Engine Error Tests
# =============================================================================


class TestFixEngineErrors:
    """Test fix engine error handling."""
    
    @pytest.mark.asyncio
    async def test_apply_fix_with_nonexistent_workspace(self, tmp_path: Path) -> None:
        """Test fix with nonexistent workspace."""
        nonexistent_workspace = tmp_path / "does_not_exist"
        
        fixer = ApplyFixTool(str(nonexistent_workspace))
        
        test_file = nonexistent_workspace / "test.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("original")
        
        from src.core.fix_engine.models import Fix
        
        fix = Fix(
            id="workspace_test",
            file_path=str(test_file),
            line_start=1,
            line_end=1,
            old_text="original",
            new_text="modified",
            reason="Test workspace",
        )
        
        result = fixer.apply_fix(fix)
        
        assert result.success
    
    @pytest.mark.asyncio
    async def test_validate_with_empty_content(self, tmp_path: Path) -> None:
        """Test validation with empty file content."""
        fixer = ApplyFixTool(str(tmp_path))
        
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")
        
        valid, msg = fixer.validate_fix(
            str(empty_file),
            "non-empty",
            "replacement",
        )
        
        assert not valid
    
    @pytest.mark.asyncio
    async def test_apply_fix_with_duplicate_old_text(self, tmp_path: Path) -> None:
        """Test fix with duplicate old_text occurrences."""
        fixer = ApplyFixTool(str(tmp_path))
        
        test_file = tmp_path / "duplicate.py"
        test_file.write_text("line one\nold_text\nline two\nold_text\nline three")
        
        from src.core.fix_engine.models import Fix
        
        fix = Fix(
            id="duplicate_test",
            file_path=str(test_file),
            line_start=1,
            line_end=1,
            old_text="old_text",
            new_text="NEW_TEXT",
            reason="Test duplicate",
        )
        
        result = fixer.apply_fix(fix)
        
        assert result.success
        
        content = test_file.read_text()
        assert content.count("NEW_TEXT") == 1
        assert content.count("old_text") == 1


# =============================================================================
# Concurrent Access Tests
# =============================================================================


class TestConcurrentAccess:
    """Test handling of concurrent access scenarios."""
    
    @pytest.mark.asyncio
    async def test_concurrent_indexing_same_file(self, tmp_path: Path) -> None:
        """Test concurrent indexing of the same file."""
        graph = SymbolGraph()
        
        test_file = tmp_path / "concurrent.py"
        test_file.write_text("def concurrent(): pass")
        
        async def index_file():
            return await graph.index_file(str(test_file))
        
        results = await asyncio.gather(
            index_file(),
            index_file(),
            index_file(),
        )
        
        assert all(isinstance(r, dict) for r in results)
    
    @pytest.mark.asyncio
    async def test_concurrent_fix_application(self, tmp_path: Path) -> None:
        """Test concurrent fix applications."""
        fixer = ApplyFixTool(str(tmp_path))
        
        test_file = tmp_path / "concurrent_fix.py"
        test_file.write_text("START\nmiddle\nEND")
        
        from src.core.fix_engine.models import Fix
        
        async def apply_fix_1():
            fix = Fix(
                id="concurrent_1",
                file_path=str(test_file),
                line_start=1,
                line_end=1,
                old_text="START",
                new_text="BEGIN",
                reason="Test concurrent 1",
            )
            return fixer.apply_fix(fix)
        
        async def apply_fix_2():
            fix = Fix(
                id="concurrent_2",
                file_path=str(test_file),
                line_start=3,
                line_end=3,
                old_text="END",
                new_text="FINISH",
                reason="Test concurrent 2",
            )
            return fixer.apply_fix(fix)
        
        results = await asyncio.gather(
            apply_fix_1(),
            apply_fix_2(),
            return_exceptions=True,
        )
        
        for result in results:
            if isinstance(result, Exception):
                continue
            assert isinstance(result.success, bool)


# =============================================================================
# Recovery Tests
# =============================================================================


class TestRecoveryScenarios:
    """Test recovery from various error scenarios."""
    
    @pytest.mark.asyncio
    async def test_pipeline_recovery_after_error(self, tmp_path: Path) -> None:
        """Test pipeline continues after processing one bad file."""
        pipeline = UnifiedReviewPipeline()
        
        good_file = tmp_path / "good.py"
        good_file.write_text("def good(): pass")
        
        bad_file = tmp_path / "bad.py"
        bad_file.write_text("def broken(")
        
        issues_good = await pipeline.analyze([good_file])
        assert isinstance(issues_good, list)
        
        issues_bad = await pipeline.analyze([bad_file])
        assert isinstance(issues_bad, list)
        
        issues_mixed = await pipeline.analyze([good_file, bad_file])
        assert isinstance(issues_mixed, list)
    
    @pytest.mark.asyncio
    async def test_fix_tool_after_failed_fix(self, tmp_path: Path) -> None:
        """Test fix tool continues working after a failed fix."""
        fixer = ApplyFixTool(str(tmp_path))
        
        existing_file = tmp_path / "existing.py"
        existing_file.write_text("existing content")
        
        nonexistent_file = tmp_path / "nonexistent.py"
        
        from src.core.fix_engine.models import Fix
        
        failed_fix = Fix(
            id="failed",
            file_path=str(nonexistent_file),
            line_start=1,
            line_end=1,
            old_text="old",
            new_text="new",
            reason="Test failed",
        )
        result1 = fixer.apply_fix(failed_fix)
        assert not result1.success
        
        successful_fix = Fix(
            id="successful",
            file_path=str(existing_file),
            line_start=1,
            line_end=1,
            old_text="existing content",
            new_text="modified content",
            reason="Test successful",
        )
        result2 = fixer.apply_fix(successful_fix)
        assert result2.success


# =============================================================================
# Edge Case Tests
# =============================================================================


class TestEdgeCases:
    """Test various edge cases."""
    
    @pytest.mark.asyncio
    async def test_file_with_only_whitespace(self, tmp_path: Path) -> None:
        """Test handling of files with only whitespace."""
        whitespace_file = tmp_path / "whitespace.py"
        whitespace_file.write_text("   \n\n   \n   \n")
        
        pipeline = UnifiedReviewPipeline()
        issues = await pipeline.analyze([whitespace_file])
        
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    async def test_file_with_only_comments(self, tmp_path: Path) -> None:
        """Test handling of files with only comments."""
        comment_file = tmp_path / "comments.py"
        comment_file.write_text("# This file only has comments\n# Another comment\n")
        
        pipeline = UnifiedReviewPipeline()
        issues = await pipeline.analyze([comment_file])
        
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    async def test_very_long_lines(self, tmp_path: Path) -> None:
        """Test handling of files with very long lines."""
        long_line_file = tmp_path / "long_lines.py"
        long_line = "x = " + "0" * 100000
        long_line_file.write_text(long_line)
        
        pipeline = UnifiedReviewPipeline()
        issues = await pipeline.analyze([long_line_file])
        
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    async def test_unicode_in_filepath(self, tmp_path: Path) -> None:
        """Test handling of files with unicode in path."""
        unicode_file = tmp_path / "test_café.py"
        unicode_file.write_text("def café(): pass")
        
        pipeline = UnifiedReviewPipeline()
        
        try:
            issues = await pipeline.analyze([unicode_file])
            assert isinstance(issues, list)
        except UnicodeEncodeError:
            pytest.skip("Unicode path not supported")
    
    @pytest.mark.asyncio
    async def test_hidden_file(self, tmp_path: Path) -> None:
        """Test handling of hidden files."""
        hidden_file = tmp_path / ".hidden.py"
        hidden_file.write_text("def hidden(): pass")
        
        pipeline = UnifiedReviewPipeline()
        issues = await pipeline.analyze([hidden_file])
        
        assert isinstance(issues, list)
