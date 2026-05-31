"""Tests for ReviewRetriever - RAG-enhanced code review retrieval."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.workflows.unified.review_retriever import (
    ReviewRetriever,
    BugPattern,
    CrossFileContext,
    RetrievalEnrichedFinding,
)


class TestReviewRetriever:
    """Test suite for ReviewRetriever."""

    @pytest.fixture
    def mock_retrieval_engine(self):
        """Create a mock retrieval engine."""
        engine = MagicMock()
        engine.retrieve = AsyncMock()
        return engine

    @pytest.fixture
    def retriever(self, mock_retrieval_engine):
        """Create a ReviewRetriever with mock engine."""
        return ReviewRetriever(retrieval_engine=mock_retrieval_engine)

    @pytest.mark.asyncio
    async def test_find_similar_bugs_returns_patterns(self, retriever, mock_retrieval_engine):
        """Test that find_similar_bugs returns bug patterns."""
        mock_hit = MagicMock()
        mock_hit.chunk_id = "pattern_1"
        mock_hit.text = "Hardcoded password found"
        mock_hit.vector_score = 0.85
        mock_hit.metadata = {"doc_id": "auth.py"}

        mock_response = MagicMock()
        mock_response.hits = [mock_hit]
        mock_retrieval_engine.retrieve.return_value = mock_response

        patterns = await retriever.find_similar_bugs("hardcoded password")

        assert len(patterns) == 1
        assert patterns[0].pattern_id == "pattern_1"
        assert patterns[0].confidence == 0.85
        assert "password" in patterns[0].description.lower()

    @pytest.mark.asyncio
    async def test_find_similar_bugs_with_language_filter(self, retriever, mock_retrieval_engine):
        """Test find_similar_bugs with language filter."""
        mock_response = MagicMock()
        mock_response.hits = []
        mock_retrieval_engine.retrieve.return_value = mock_response

        await retriever.find_similar_bugs("null pointer", language="Python")

        mock_retrieval_engine.retrieve.assert_called_once()
        call_args = mock_retrieval_engine.retrieve.call_args[0][0]
        assert "Python" in call_args.query
        assert "null pointer" in call_args.query

    @pytest.mark.asyncio
    async def test_find_similar_bugs_max_results(self, retriever, mock_retrieval_engine):
        """Test that max_results limits returned patterns."""
        mock_response = MagicMock()
        mock_response.hits = [
            MagicMock(chunk_id=f"pattern_{i}", text=f"Issue {i}",
                     vector_score=0.9, metadata={"doc_id": f"file{i}.py"})
            for i in range(10)
        ]
        mock_retrieval_engine.retrieve.return_value = mock_response

        patterns = await retriever.find_similar_bugs("issue", max_results=3)

        assert len(patterns) == 3

    @pytest.mark.asyncio
    async def test_get_cross_file_context(self, retriever, mock_retrieval_engine):
        """Test cross-file context retrieval."""
        mock_hit = MagicMock()
        mock_hit.metadata = {"doc_id": "helper.py"}
        mock_hit.text = "import logging"

        mock_response = MagicMock()
        mock_response.hits = [mock_hit]
        mock_retrieval_engine.retrieve.return_value = mock_response

        context = await retriever.get_cross_file_context(Path("main.py"))

        assert context is not None
        assert "helper.py" in context.related_files

    @pytest.mark.asyncio
    async def test_enrich_finding(self, retriever, mock_retrieval_engine):
        """Test finding enrichment with RAG context."""
        mock_hit = MagicMock()
        mock_hit.chunk_id = "similar_1"
        mock_hit.text = "Similar bug pattern"
        mock_hit.vector_score = 0.8
        mock_hit.metadata = {"doc_id": "legacy.py"}

        mock_response = MagicMock()
        mock_response.hits = [mock_hit]
        mock_retrieval_engine.retrieve.return_value = mock_response

        finding = {
            "rule_id": "SEC001",
            "message": "Hardcoded secret detected",
            "file": "config.py",
            "line": 42,
        }

        enriched = await retriever.enrich_finding(finding)

        assert isinstance(enriched, RetrievalEnrichedFinding)
        assert enriched.original_finding == finding
        assert len(enriched.similar_bugs) == 1
        assert enriched.confidence_boost > 0

    @pytest.mark.asyncio
    async def test_language_detection(self, retriever):
        """Test automatic language detection from file path."""
        assert retriever._detect_language("script.py") == "Python"
        assert retriever._detect_language("app.js") == "JavaScript"
        assert retriever._detect_language("main.rs") == "Rust"
        assert retriever._detect_language("module.ts") == "TypeScript"

    def test_severity_inference(self, retriever):
        """Test severity inference from pattern."""
        assert retriever._infer_severity("sql injection vulnerability") == "CRITICAL"
        assert retriever._infer_severity("memory leak detected") == "HIGH"
        assert retriever._infer_severity("unused variable") == "LOW"
        assert retriever._infer_severity("some pattern") == "MEDIUM"

    def test_fix_hint_generation(self, retriever):
        """Test fix hint generation."""
        hint = retriever._generate_fix_hint("hardcoded password in code")
        assert "environment" in hint.lower() or "config" in hint.lower()

        hint = retriever._generate_fix_hint("null pointer dereference")
        assert "null" in hint.lower() or "check" in hint.lower()

    @pytest.mark.asyncio
    async def test_graceful_failure_without_engine(self):
        """Test graceful handling when no retrieval engine available."""
        retriever = ReviewRetriever(retrieval_engine=None)

        with patch.object(retriever, '_ensure_initialized', AsyncMock(return_value=False)):
            patterns = await retriever.find_similar_bugs("test")
            assert patterns == []

            context = await retriever.get_cross_file_context(Path("test.py"))
            assert context is None


class TestBugPattern:
    """Test BugPattern dataclass."""

    def test_bug_pattern_creation(self):
        """Test BugPattern instantiation."""
        pattern = BugPattern(
            pattern_id="SEC001",
            description="Hardcoded password",
            severity="HIGH",
            language="Python",
            code_snippet="password = 'secret123'",
            fix_suggestion="Use environment variable",
            confidence=0.9,
            source_doc="auth.py",
        )

        assert pattern.pattern_id == "SEC001"
        assert pattern.confidence == 0.9
        assert "password" in pattern.code_snippet


class TestCrossFileContext:
    """Test CrossFileContext dataclass."""

    def test_cross_file_context_creation(self):
        """Test CrossFileContext instantiation."""
        context = CrossFileContext(
            related_files=["helper.py", "utils.py"],
            usage_patterns=["from helper import func"],
            similar_implementations=["def func(): pass"],
            dependencies=["import logging"],
        )

        assert len(context.related_files) == 2
        assert "helper.py" in context.related_files


class TestRetrievalEnrichedFinding:
    """Test RetrievalEnrichedFinding dataclass."""

    def test_enriched_finding_creation(self):
        """Test RetrievalEnrichedFinding instantiation."""
        finding = {"rule_id": "TEST001", "message": "Test issue"}
        pattern = BugPattern(
            pattern_id="p1", description="test", severity="LOW",
            language="Python", code_snippet="", fix_suggestion="",
            confidence=0.5, source_doc="test.py"
        )

        enriched = RetrievalEnrichedFinding(
            original_finding=finding,
            similar_bugs=[pattern],
            cross_file_context=None,
            confidence_boost=0.1,
        )

        assert enriched.original_finding == finding
        assert len(enriched.similar_bugs) == 1
        assert enriched.confidence_boost == 0.1
