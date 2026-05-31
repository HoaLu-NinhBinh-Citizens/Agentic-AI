"""RAG-Enhanced Review Retriever — bridges AdvancedRetrievalEngine with code review.

This module provides semantic search capabilities for code review by:
1. Querying similar bug patterns from the knowledge base
2. Retrieving cross-file context for better fix suggestions
3. Enriching findings with related code patterns

Usage:
    retriever = ReviewRetriever(advanced_retrieval_engine)
    similar_bugs = await retriever.find_similar_bugs("hardcoded password", "Python")
    context = await retriever.get_cross_file_context(file_path, function_name)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
from src.infrastructure.retrieval.retrieval_types import (
    AdvancedRetrievalRequest,
    QueryIntent,
)


logger = logging.getLogger(__name__)


@dataclass
class BugPattern:
    """A similar bug pattern retrieved from knowledge base."""
    pattern_id: str
    description: str
    severity: str
    language: str
    code_snippet: str
    fix_suggestion: str
    confidence: float
    source_doc: str


@dataclass
class CrossFileContext:
    """Cross-file context for understanding code relationships."""
    related_files: list[str]
    usage_patterns: list[str]
    similar_implementations: list[str]
    dependencies: list[str]


@dataclass
class RetrievalEnrichedFinding:
    """A finding enriched with RAG context."""
    original_finding: dict
    similar_bugs: list[BugPattern]
    cross_file_context: Optional[CrossFileContext]
    confidence_boost: float


class ReviewRetriever:
    """Bridges AdvancedRetrievalEngine with code review operations.

    Provides semantic search capabilities:
    - Find similar bug patterns
    - Get cross-file context
    - Enrich findings with retrieved knowledge
    """

    def __init__(self, retrieval_engine: Optional[AdvancedRetrievalEngine] = None):
        """Initialize the review retriever.

        Args:
            retrieval_engine: Optional AdvancedRetrievalEngine instance.
                            If None, will be lazily initialized.
        """
        self._retrieval_engine = retrieval_engine
        self._initialized = False

    async def _ensure_initialized(self) -> bool:
        """Ensure retrieval engine is initialized."""
        if self._retrieval_engine is not None:
            return True

        try:
            from src.infrastructure.retrieval.retrieval_engine import AdvancedRetrievalEngine
            self._retrieval_engine = AdvancedRetrievalEngine()
            self._initialized = True
            return True
        except Exception as e:
            logger.warning("Failed to initialize retrieval engine: %s", e)
            return False

    async def find_similar_bugs(
        self,
        error_pattern: str,
        language: Optional[str] = None,
        max_results: int = 5,
    ) -> list[BugPattern]:
        """Find similar bug patterns from the knowledge base.

        Args:
            error_pattern: The error/bug pattern to search for
            language: Optional language filter
            max_results: Maximum number of results to return

        Returns:
            List of similar bug patterns
        """
        if not await self._ensure_initialized():
            return []

        query = error_pattern
        if language:
            query = f"{language} {error_pattern}"

        request = AdvancedRetrievalRequest(
            query=query,
            intent=QueryIntent.CODE,
            require_explanation=True,
            max_provenance_entries=max_results,
        )

        try:
            response = await self._retrieval_engine.retrieve(request)

            patterns = []
            for i, hit in enumerate(response.hits[:max_results]):
                pattern = BugPattern(
                    pattern_id=getattr(hit, "chunk_id", f"pattern_{i}"),
                    description=getattr(hit, "text", "")[:200],
                    severity=self._infer_severity(error_pattern),
                    language=language or "unknown",
                    code_snippet=getattr(hit, "text", ""),
                    fix_suggestion=self._generate_fix_hint(error_pattern),
                    confidence=getattr(hit, "vector_score", 0.5),
                    source_doc=getattr(hit, "metadata", {}).get("doc_id", "unknown"),
                )
                patterns.append(pattern)

            return patterns

        except Exception as e:
            logger.error("Failed to find similar bugs: %s", e)
            return []

    async def get_cross_file_context(
        self,
        file_path: Path,
        symbol_name: Optional[str] = None,
    ) -> Optional[CrossFileContext]:
        """Get cross-file context for understanding code relationships.

        Args:
            file_path: The file to get context for
            symbol_name: Optional specific symbol/function name

        Returns:
            CrossFileContext with related files and patterns
        """
        if not await self._ensure_initialized():
            return None

        query_parts = [str(file_path)]
        if symbol_name:
            query_parts.append(symbol_name)

        request = AdvancedRetrievalRequest(
            query=" ".join(query_parts),
            intent=QueryIntent.CODE,
            require_explanation=True,
            max_provenance_entries=10,
        )

        try:
            response = await self._retrieval_engine.retrieve(request)

            related_files = []
            usage_patterns = []
            similar_impls = []
            dependencies = []

            for hit in response.hits:
                metadata = getattr(hit, "metadata", {})
                doc_id = metadata.get("doc_id", "")

                if doc_id and doc_id != str(file_path):
                    related_files.append(doc_id)

                text = getattr(hit, "text", "")
                if "import" in text or "include" in text:
                    dependencies.append(text[:100])
                elif "def " in text or "class " in text:
                    similar_impls.append(text[:150])

            return CrossFileContext(
                related_files=related_files[:5],
                usage_patterns=usage_patterns[:5],
                similar_implementations=similar_impls[:5],
                dependencies=dependencies[:5],
            )

        except Exception as e:
            logger.error("Failed to get cross-file context: %s", e)
            return None

    async def enrich_finding(
        self,
        finding: dict,
        max_similar: int = 3,
    ) -> RetrievalEnrichedFinding:
        """Enrich a finding with RAG context.

        Args:
            finding: The finding dict to enrich
            max_similar: Maximum similar bugs to find

        Returns:
            RetrievalEnrichedFinding with RAG context
        """
        rule_id = finding.get("rule_id", "")
        message = finding.get("message", "")
        file_path = finding.get("file", "")

        language = self._detect_language(file_path)
        combined_query = f"{message} {rule_id}"

        similar_bugs = await self.find_similar_bugs(
            combined_query,
            language=language,
            max_results=max_similar,
        )

        context = await self.get_cross_file_context(Path(file_path))

        confidence_boost = 0.0
        if similar_bugs:
            avg_confidence = sum(b.confidence for b in similar_bugs) / len(similar_bugs)
            confidence_boost = min(avg_confidence * 0.1, 0.15)

        return RetrievalEnrichedFinding(
            original_finding=finding,
            similar_bugs=similar_bugs,
            cross_file_context=context,
            confidence_boost=confidence_boost,
        )

    def _infer_severity(self, pattern: str) -> str:
        """Infer severity from error pattern."""
        pattern_lower = pattern.lower()

        if any(k in pattern_lower for k in ["sql injection", "xss", "csrf", "auth bypass"]):
            return "CRITICAL"
        if any(k in pattern_lower for k in ["memory leak", "buffer overflow", "null pointer"]):
            return "HIGH"
        if any(k in pattern_lower for k in ["unused", "deprecated", "style"]):
            return "LOW"
        return "MEDIUM"

    def _generate_fix_hint(self, pattern: str) -> str:
        """Generate a fix hint based on pattern."""
        pattern_lower = pattern.lower()

        if "hardcoded" in pattern_lower and "password" in pattern_lower:
            return "Use environment variables or secure config management"
        if "null" in pattern_lower or "none" in pattern_lower:
            return "Add null/None check before use"
        if "import" in pattern_lower:
            return "Use dependency injection or proper module imports"
        return "Review and refactor according to best practices"

    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file path."""
        suffixes = {
            ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
            ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java",
            ".c": "C", ".cpp": "C++", ".h": "C/C++", ".rs": "Rust",
            ".go": "Go", ".rb": "Ruby", ".swift": "Swift", ".kt": "Kotlin",
        }

        path = Path(file_path)
        return suffixes.get(path.suffix, "unknown")
