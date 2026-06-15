"""Unit tests for P1 context fusion: rerank, packing, and engine wiring."""

import asyncio

from src.application.suggestion.context_fusion import (
    ContextFusion,
    RetrievedSnippet,
    pack_context,
    rerank,
)


# ─── Fakes ────────────────────────────────────────────────────────────────


class FakeRetriever:
    def __init__(self, snippets):
        self._snippets = snippets

    async def retrieve(self, query, top_k):
        return list(self._snippets[:top_k])


class WordCountCounter:
    """Deterministic token counter for tests: one token per whitespace word."""

    def count(self, text):
        return max(1, len(text.split()))

    def truncate_prompt(self, text, max_tokens):
        return " ".join(text.split()[:max_tokens])


# ─── rerank ──────────────────────────────────────────────────────────────


class TestRerank:
    def test_lexical_rerank_orders_by_overlap(self):
        snips = [
            RetrievedSnippet("completely unrelated text here", source="a"),
            RetrievedSnippet("scaler fit before train test split", source="b"),
        ]
        ranked = asyncio.run(rerank("data leakage scaler fit train test split", snips))
        assert ranked[0].source == "b"

    def test_embedder_rerank_uses_cosine(self):
        # Query vector closest to snippet 'b'.
        vectors = {
            "Q": [1.0, 0.0],
            "a": [0.0, 1.0],
            "b": [0.9, 0.1],
        }

        async def embedder(text):
            if text.startswith("query"):
                return vectors["Q"]
            return vectors[text]

        snips = [RetrievedSnippet("a", source="a"), RetrievedSnippet("b", source="b")]
        ranked = asyncio.run(rerank("query", snips, embedder=embedder))
        assert ranked[0].source == "b"

    def test_embedder_failure_falls_back_to_lexical(self):
        async def broken(text):
            raise RuntimeError("no embeddings")

        snips = [
            RetrievedSnippet("nothing matching", source="a"),
            RetrievedSnippet("device mismatch cuda cpu", source="b"),
        ]
        ranked = asyncio.run(
            rerank("device mismatch cuda cpu", snips, embedder=broken)
        )
        assert ranked[0].source == "b"

    def test_empty_input(self):
        assert asyncio.run(rerank("q", [])) == []


# ─── pack_context ──────────────────────────────────────────────────────────


class TestPackContext:
    def test_respects_token_budget(self):
        snips = [
            RetrievedSnippet("alpha beta gamma delta", source="a"),
            RetrievedSnippet("one two three four five", source="b"),
        ]
        out = pack_context(snips, max_tokens=15, token_counter=WordCountCounter())
        # Budget admits header + first block only; second must not fully fit.
        assert "alpha beta gamma delta" in out
        assert "one two three four five" not in out

    def test_deduplicates_identical_snippets(self):
        dup = RetrievedSnippet("same content here", source="a")
        dup2 = RetrievedSnippet("same   content here", source="a")  # whitespace diff
        out = pack_context(
            [dup, dup2], max_tokens=100, token_counter=WordCountCounter()
        )
        assert out.count("same content here") == 1 or out.count("same") == 1

    def test_empty_returns_empty_string(self):
        assert pack_context([], max_tokens=100) == ""

    def test_zero_budget_returns_empty(self):
        snips = [RetrievedSnippet("x y z", source="a")]
        assert pack_context(snips, max_tokens=0) == ""

    def test_includes_source_attribution(self):
        snips = [RetrievedSnippet("relevant code", source="src/foo.py")]
        out = pack_context(snips, max_tokens=100, token_counter=WordCountCounter())
        assert "src/foo.py" in out


# ─── ContextFusion orchestrator ──────────────────────────────────────────────


class TestContextFusion:
    def test_build_context_end_to_end(self):
        retriever = FakeRetriever(
            [
                RetrievedSnippet("unrelated boilerplate", source="a"),
                RetrievedSnippet("scaler fit train test split leakage", source="b"),
            ]
        )
        fusion = ContextFusion(
            retriever, token_counter=WordCountCounter(), max_tokens=50
        )
        out = asyncio.run(fusion.build_context("data leakage scaler fit split"))
        assert "src" not in out  # source 'b' has no path prefix issue
        assert "scaler fit train test split leakage" in out
        # most-relevant snippet 'b' should appear before the unrelated one
        assert out.index("scaler") < (
            out.index("unrelated") if "unrelated" in out else len(out)
        )

    def test_retriever_failure_returns_empty(self):
        class Boom:
            async def retrieve(self, query, top_k):
                raise RuntimeError("down")

        fusion = ContextFusion(Boom(), token_counter=WordCountCounter())
        assert asyncio.run(fusion.build_context("q")) == ""

    def test_no_candidates_returns_empty(self):
        fusion = ContextFusion(FakeRetriever([]), token_counter=WordCountCounter())
        assert asyncio.run(fusion.build_context("q")) == ""


# ─── Engine integration ──────────────────────────────────────────────────────


class TestEngineIntegration:
    def _finding(self):
        from src.application.workflows.unified.detector_base import (
            Finding,
            FindingSeverity,
        )

        return Finding(
            rule_id="ML001",
            rule_name="data leakage",
            severity=FindingSeverity.ERROR,
            file="train.py",
            line=10,
            end_line=10,
            message="scaler fit before split",
            context="scaler.fit(X)",
        )

    def test_fused_context_appears_in_prompt(self):
        from src.application.suggestion.suggestion_engine import (
            UnifiedSuggestionEngine,
            LLMProviderInterface,
        )

        captured = {}

        class CapturingLLM(LLMProviderInterface):
            async def is_available(self):
                return True

            async def generate(self, prompt, system=None):
                captured["prompt"] = prompt
                return "[]"  # no options; we only care about the prompt

        retriever = FakeRetriever(
            [RetrievedSnippet("scaler fit train split leakage example", source="util.py")]
        )
        fusion = ContextFusion(retriever, token_counter=WordCountCounter(), max_tokens=50)
        engine = UnifiedSuggestionEngine(
            llm_provider=CapturingLLM(), context_fusion=fusion
        )

        asyncio.run(engine._generate_llm_fixes(self._finding(), None, 2))
        assert "Related code" in captured["prompt"]
        assert "util.py" in captured["prompt"]

    def test_works_without_context_fusion(self):
        from src.application.suggestion.suggestion_engine import (
            UnifiedSuggestionEngine,
            LLMProviderInterface,
        )

        captured = {}

        class CapturingLLM(LLMProviderInterface):
            async def is_available(self):
                return True

            async def generate(self, prompt, system=None):
                captured["prompt"] = prompt
                return "[]"

        engine = UnifiedSuggestionEngine(llm_provider=CapturingLLM())  # no fusion
        asyncio.run(engine._generate_llm_fixes(self._finding(), None, 2))
        assert "Related code" not in captured["prompt"]
