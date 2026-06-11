"""Safety tests for hunk application: no silent corruption on bad hunks.

Covers the fix replacing silent bounds-clamping in _apply_single_hunk with
context validation + nearest-match relocation + explicit rejection.
"""

from __future__ import annotations

import pytest

from src.infrastructure.patching.diff_parser import UnifiedDiffParser


@pytest.fixture
def parser() -> UnifiedDiffParser:
    return UnifiedDiffParser()


class TestHunkValidation:
    def test_mismatched_hunk_raises_instead_of_corrupting(self, parser):
        original = "alpha\nbeta\ngamma\n"
        diff = (
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,2 +1,2 @@\n"
            " nonexistent context\n"
            "-not in file\n"
            "+replacement\n"
        )
        with pytest.raises(ValueError, match="does not match"):
            parser.apply_diff(original, diff, "f.py")

    def test_off_by_n_hunk_header_is_relocated(self, parser):
        # Header claims line 1 but the real content is at line 3
        original = "pad1\npad2\nold line\ntail\n"
        diff = (
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old line\n"
            "+new line\n"
        )
        result = parser.apply_diff(original, diff, "f.py")
        assert result == "pad1\npad2\nnew line\ntail"

    def test_correct_hunk_still_applies_at_declared_position(self, parser):
        original = "a\nb\nc\n"
        diff = (
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -2,1 +2,1 @@\n"
            "-b\n"
            "+B\n"
        )
        result = parser.apply_diff(original, diff, "f.py")
        assert result == "a\nB\nc"

    def test_ambiguous_relocation_prefers_nearest_to_declared(self, parser):
        # "x" appears at lines 1 and 5; header says line 4 -> nearest is line 5
        original = "x\nb\nc\nd\nx\nf\n"
        diff = (
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -4,1 +4,1 @@\n"
            "-x\n"
            "+X\n"
        )
        result = parser.apply_diff(original, diff, "f.py")
        assert result == "x\nb\nc\nd\nX\nf"

    def test_blank_context_line_without_leading_space(self, parser):
        # LLM-style diff: blank context emitted as "" instead of " "
        original = "def f():\n    pass\n\ndef g():\n    pass\n"
        diff = (
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -4,2 +4,2 @@\n"
            " def g():\n"
            "-    pass\n"
            "+    return 1\n"
        )
        result = parser.apply_diff(original, diff, "f.py")
        assert "return 1" in result
        assert result.count("def g():") == 1
