"""Unit tests for P2 confirmation gate (_confirm_and_apply_findings)."""

import asyncio
from dataclasses import dataclass, field

from src.interfaces.cli.commands.slash import _confirm_and_apply_findings


@dataclass
class FakeFinding:
    rule_id: str
    file: str = "a.py"
    line: int = 1
    message: str = "issue"


class ScriptedProvider:
    """Returns a pre-scripted answer per prompt call."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.prompts = []

    async def prompt(self, message, choices, default):
        self.prompts.append(message)
        return self._answers.pop(0) if self._answers else default


class RecordingApplicator:
    """Records which findings were applied; reports success."""

    def __init__(self, fail_for=None):
        self.applied = []
        self._fail_for = fail_for or set()

    async def apply_finding_fix(self, finding, create_backup=True):
        if finding.rule_id in self._fail_for:
            return False, "patch failed"
        self.applied.append(finding)
        return True, "ok"


def _run(answers, findings, **kw):
    provider = ScriptedProvider(answers)
    applicator = RecordingApplicator(**kw)
    result = asyncio.run(_confirm_and_apply_findings(findings, applicator, provider))
    return result, applicator, provider


class TestConfirmationGate:
    def test_yes_applies_only_confirmed(self):
        findings = [FakeFinding("ML001"), FakeFinding("SEC001")]
        result, applicator, _ = _run(["y", "n"], findings)
        assert [f.rule_id for f in result["applied"]] == ["ML001"]
        assert result["skipped"] == 1
        assert [f.rule_id for f in applicator.applied] == ["ML001"]

    def test_no_applies_nothing(self):
        findings = [FakeFinding("ML001")]
        result, applicator, _ = _run(["n"], findings)
        assert result["applied"] == []
        assert applicator.applied == []

    def test_yes_to_all_stops_prompting(self):
        findings = [FakeFinding("A"), FakeFinding("B"), FakeFinding("C")]
        result, applicator, provider = _run(["a"], findings)
        # Only one prompt issued; all three applied.
        assert len(provider.prompts) == 1
        assert len(result["applied"]) == 3

    def test_quit_aborts_remaining(self):
        findings = [FakeFinding("A"), FakeFinding("B"), FakeFinding("C")]
        result, applicator, _ = _run(["y", "q"], findings)
        assert result["aborted"] is True
        assert [f.rule_id for f in result["applied"]] == ["A"]

    def test_default_is_skip_when_no_answer(self):
        # Provider runs out of answers -> returns default ("n") -> skip.
        findings = [FakeFinding("A")]
        result, applicator, _ = _run([], findings)
        assert result["applied"] == []

    def test_failed_apply_is_not_counted_applied(self):
        findings = [FakeFinding("A"), FakeFinding("B")]
        result, applicator, _ = _run(["y", "y"], findings, fail_for={"A"})
        assert [f.rule_id for f in result["applied"]] == ["B"]
        assert any("failed" in line for line in result["log"])
