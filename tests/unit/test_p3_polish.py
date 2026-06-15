"""Unit tests for P3 polish: retry jitter, ML seed patterns, patch ranking."""

import asyncio

import pytest


# ─── (B) Retry jitter ────────────────────────────────────────────────────────


class TestRetryPolicyJitter:
    def test_jitter_disabled_is_deterministic_exponential(self):
        from src.core.runtime.retry_policy import RetryPolicy

        p = RetryPolicy(delay=1.0, backoff_factor=2.0, jitter_factor=0.0)
        assert p.compute_delay(0) == 1.0
        assert p.compute_delay(1) == 2.0
        assert p.compute_delay(2) == 4.0

    def test_delay_capped_at_max(self):
        from src.core.runtime.retry_policy import RetryPolicy

        p = RetryPolicy(delay=1.0, backoff_factor=10.0, max_delay=5.0, jitter_factor=0.0)
        assert p.compute_delay(3) == 5.0  # would be 1000 without the cap

    def test_jitter_within_bounds(self):
        from src.core.runtime.retry_policy import RetryPolicy

        p = RetryPolicy(delay=1.0, backoff_factor=1.0, jitter_factor=0.5)
        for _ in range(50):
            d = p.compute_delay(0)
            assert 1.0 <= d <= 1.5  # base + [0, 0.5*base]

    def test_execute_retries_then_succeeds(self):
        from src.core.runtime.retry_policy import RetryPolicy

        calls = {"n": 0}

        async def flaky():
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("nope")
            return "ok"

        p = RetryPolicy(max_attempts=3, delay=0.0, jitter_factor=0.0)
        assert asyncio.run(p.execute(flaky)) == "ok"
        assert calls["n"] == 3


# ─── (C) ML005 seed pattern recognition ──────────────────────────────────────


class TestSeedPatterns:
    def test_includes_determinism_knobs(self):
        from src.infrastructure.analysis.ml_detectors.ast_based import _SEED_PATTERNS

        joined = " ".join(_SEED_PATTERNS)
        assert "PYTHONHASHSEED" in joined
        assert "cudnn" in joined.lower()
        assert "enable_op_determinism" in joined

    @pytest.mark.parametrize(
        "code",
        [
            "import os\nos.environ['PYTHONHASHSEED'] = '0'",
            "torch.backends.cudnn.deterministic = True",
            "pl.seed_everything(42)",
            "tf.random.set_seed(0)",
        ],
    )
    def test_recognized_forms_match(self, code):
        import re
        from src.infrastructure.analysis.ml_detectors.ast_based import _SEED_PATTERNS

        assert any(re.search(p, code) for p in _SEED_PATTERNS)

    def test_unseeded_code_does_not_match(self):
        import re
        from src.infrastructure.analysis.ml_detectors.ast_based import _SEED_PATTERNS

        code = "def train(model, data):\n    return model.fit(data)"
        assert not any(re.search(p, code) for p in _SEED_PATTERNS)


# ─── (A) Patch ranking ───────────────────────────────────────────────────────


class TestPatchRanking:
    def _engine(self):
        from src.application.suggestion.suggestion_engine import (
            UnifiedSuggestionEngine,
        )

        return UnifiedSuggestionEngine()

    def _opt(self, **kw):
        from src.application.suggestion.suggestion_engine import FixOption, RiskLevel

        defaults = dict(
            id="x",
            description="",
            old_code="a",
            new_code="b",
            risk=RiskLevel("low"),
            confidence=0.9,
            requires_review=True,
            automated=False,
        )
        defaults.update(kw)
        return FixOption(**defaults)

    def test_higher_confidence_ranks_first(self):
        eng = self._engine()
        low = self._opt(id="low", confidence=0.5)
        high = self._opt(id="high", confidence=0.95)
        ranked = eng._rank_options([low, high])
        assert ranked[0].id == "high"

    def test_no_review_breaks_tie_over_requires_review(self):
        eng = self._engine()
        # identical except requires_review; the no-review fix should win.
        needs = self._opt(id="needs", requires_review=True, automated=True)
        clean = self._opt(id="clean", requires_review=False, automated=True)
        ranked = eng._rank_options([needs, clean])
        assert ranked[0].id == "clean"
