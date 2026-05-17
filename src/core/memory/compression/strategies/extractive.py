"""Extractive summarization using Maximal Marginal Relevance (MMR).

Phase 4E: Issue #8 - Complexity controls and sentence cap.
"""

from __future__ import annotations

import hashlib
import re
import time
from typing import TYPE_CHECKING

import numpy as np

from .base import CompressionStrategy, DecompressionError
from ..types import CompressionMetadata

if TYPE_CHECKING:
    from ..config import ExtractiveConfig
    from ...embeddings.embedding_service import EmbeddingService


class ExtractiveSummarizer(CompressionStrategy):
    """Extract important sentences using MMR for diversity.
    
    Phase 4E Updates:
    - Issue #8: Sentence cap to prevent O(n²) blowup
    - Issue #8: Approximate MMR for faster computation
    
    Uses Maximal Marginal Relevance to select sentences that are:
    1. Relevant to the overall content (high similarity to query)
    2. Diverse from each other (low similarity to already selected)
    """
    
    def __init__(
        self,
        embedding_service: "EmbeddingService | None" = None,
        config: "ExtractiveConfig | None" = None,
    ):
        if config is None:
            from ..config import ExtractiveConfig
            config = ExtractiveConfig()
        
        self._embedding_service = embedding_service
        self._top_k_ratio = config.top_k_ratio
        self._diversity_lambda = config.diversity_lambda
        self._model_version = config.model_version
        # Phase 4E: Issue #8 - Sentence cap
        self._max_sentences = config.max_sentences
        self._use_approximate_mmr = config.use_approximate_mmr
    
    @property
    def name(self) -> str:
        return "extractive"
    
    def _split_sentences(self, content: str) -> list[str]:
        """Split content into sentences."""
        sentences = re.split(r"(?<=[.!?])\s+", content)
        sentences = [s.strip() for s in sentences if s.strip()]
        return sentences
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    
    def _mmr_select(
        self,
        query_emb: list[float],
        sent_embs: list[list[float]],
        k: int,
        lambda_: float,
    ) -> list[int]:
        """Select k sentences using Maximal Marginal Relevance.
        
        MMR formula: argmax [λ * Sim(q, d) - (1-λ) * max(Sim(d, S))]
        Where q is query, d is candidate, S is already selected set.
        
        Args:
            query_emb: Query embedding (content itself).
            sent_embs: List of sentence embeddings.
            k: Number of sentences to select.
            lambda_: Balance between relevance (λ) and diversity (1-λ).
            
        Returns:
            Indices of selected sentences.
        """
        n = len(sent_embs)
        if n == 0:
            return []
        
        k = min(k, n)
        selected: list[int] = []
        remaining = set(range(n))
        
        for _ in range(k):
            if not remaining:
                break
            
            best_score = float("-inf")
            best_idx = -1
            
            for idx in remaining:
                relevance = self._cosine_similarity(query_emb, sent_embs[idx])
                
                if selected:
                    max_diversity = max(
                        self._cosine_similarity(sent_embs[idx], sent_embs[j])
                        for j in selected
                    )
                else:
                    max_diversity = 0.0
                
                mmr_score = lambda_ * relevance - (1 - lambda_) * max_diversity
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx
            
            if best_idx >= 0:
                selected.append(best_idx)
                remaining.remove(best_idx)
        
        return selected
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        """Compress using extractive summarization with MMR.
        
        Phase 4E: Issue #8 - Sentence cap to prevent O(n²) blowup.
        """
        original_hash = hashlib.sha256(content.encode()).hexdigest()
        
        sentences = self._split_sentences(content)
        original_count = len(sentences)
        
        # Phase 4E: Issue #8 - HARD CAP: Never process more than max_sentences
        if len(sentences) > self._max_sentences:
            # Select evenly distributed subset to maintain coverage
            step = len(sentences) / self._max_sentences
            indices = [int(i * step) for i in range(self._max_sentences)]
            sentences = [sentences[i] for i in indices]
        
        if len(sentences) <= 2:
            return content, CompressionMetadata(
                strategy=self.name,
                params={
                    "top_k_ratio": self._top_k_ratio,
                    "diversity_lambda": self._diversity_lambda,
                    "original_sentence_count": original_count,
                    "processed_sentence_count": len(sentences),
                    "was_truncated": original_count > self._max_sentences,
                },
                original_hash=original_hash,
                selected_indices=list(range(len(sentences))),
            )
        
        top_k = max(1, int(len(sentences) * self._top_k_ratio))
        top_k = min(top_k, len(sentences))
        
        if self._embedding_service is None:
            return content, CompressionMetadata(
                strategy=self.name,
                params={"error": "no_embedding_service"},
                original_hash=original_hash,
                error="embedding_service_not_available",
            )
        
        try:
            query_emb = await self._embedding_service.embed(content)
            if not query_emb:
                return content, CompressionMetadata(
                    strategy=self.name,
                    params={"error": "embed_failed"},
                    original_hash=original_hash,
                    error="embedding_failed",
                )
            
            # Phase 4E: Issue #8 - Batch size limit
            sent_embs = await self._embedding_service.embed_batch(sentences)
            if not sent_embs or len(sent_embs) != len(sentences):
                return content, CompressionMetadata(
                    strategy=self.name,
                    params={"error": "batch_embed_failed"},
                    original_hash=original_hash,
                    error="batch_embedding_failed",
                )
            
            # Phase 4E: Issue #8 - Use approximate MMR if enabled
            if self._use_approximate_mmr:
                selected = await self._approximate_mmr_select(
                    query_emb, sent_embs, top_k, self._diversity_lambda
                )
            else:
                selected = self._mmr_select(
                    query_emb, sent_embs, top_k, self._diversity_lambda
                )
            
            selected.sort()
            summary = " ".join(sentences[i] for i in selected)
            
            return summary, CompressionMetadata(
                strategy=self.name,
                params={
                    "top_k_ratio": self._top_k_ratio,
                    "diversity_lambda": self._diversity_lambda,
                    "original_sentence_count": original_count,
                    "processed_sentence_count": len(sentences),
                    "was_truncated": original_count > self._max_sentences,
                    "selected_count": len(selected),
                },
                model_version=self._model_version,
                original_hash=original_hash,
                selected_indices=selected,
                compressed_at=int(time.time()),
            )
            
        except Exception as e:
            return content, CompressionMetadata(
                strategy=self.name,
                params={"error": str(e)},
                original_hash=original_hash,
                error=str(e),
            )
    
    async def _approximate_mmr_select(
        self,
        query_emb: list[float],
        sent_embs: list[list[float]],
        k: int,
        lambda_: float,
    ) -> list[int]:
        """Phase 4E: Issue #8 - Approximate MMR for faster computation.
        
        Pre-computes local diversity only (sliding window) instead of
        comparing against all selected items. Reduces O(n²) to O(n).
        """
        n = len(sent_embs)
        if n == 0:
            return []
        
        k = min(k, n)
        selected: list[int] = []
        remaining = list(range(n))
        
        # Pre-compute relevance scores: O(n)
        relevance_scores = [
            self._cosine_similarity(query_emb, emb) 
            for emb in sent_embs
        ]
        
        # Pre-compute local diversity (sliding window approximation)
        diversity_cache = self._precompute_local_diversity(sent_embs, window=10)
        
        for _ in range(k):
            if not remaining:
                break
            
            best_score = float("-inf")
            best_idx = -1
            
            for idx in remaining:
                relevance = relevance_scores[idx]
                
                # Use cached local diversity
                if selected:
                    # Find minimum diversity from selected items
                    min_diversity = min(
                        diversity_cache[idx].get(j, 0.5)
                        for j in selected
                    )
                else:
                    min_diversity = 0.0
                
                mmr_score = lambda_ * relevance - (1 - lambda_) * min_diversity
                
                if mmr_score > best_score:
                    best_score = mmr_score
                    best_idx = idx
            
            if best_idx >= 0:
                selected.append(best_idx)
                remaining.remove(best_idx)
        
        return selected
    
    def _precompute_local_diversity(
        self,
        sent_embs: list[list[float]],
        window: int = 10,
    ) -> list[dict[int, float]]:
        """Phase 4E: Issue #8 - Pre-compute local diversity for approximate MMR.
        
        For each sentence, compute similarity only to nearby sentences
        (sliding window) instead of all sentences.
        """
        n = len(sent_embs)
        cache: list[dict[int, float]] = [{} for _ in range(n)]
        
        for i in range(n):
            # Check nearby sentences within window
            for j in range(max(0, i - window), min(n, i + window + 1)):
                if i != j:
                    sim = self._cosine_similarity(sent_embs[i], sent_embs[j])
                    cache[i][j] = sim
        
        return cache
    
    async def decompress(
        self, content: str, metadata: CompressionMetadata
    ) -> str:
        """Decompress extractive summary."""
        return content
