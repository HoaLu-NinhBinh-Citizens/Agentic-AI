"""Score engine for semantic scoring."""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
    from src.infrastructure.router.types import RequestContext, Snapshot

logger = logging.getLogger(__name__)


@dataclass
class ANNNeighbor:
    """ANN search result neighbor."""

    intent_path: str
    example_text: str
    embedding: list[float]
    similarity: float


class ScoreEngine:
    """
    Calculates semantic scores for intent matching.
    
    Combines:
    - Semantic similarity from ANN index
    - Frequency-based boost
    - Fairness constraints
    """

    def __init__(
        self,
        embedding_model: EmbeddingModel,
        ann_index: ANNIndex,
        fairness_calculator: FairnessBoostCalculator,
    ):
        self._embedding_model = embedding_model
        self._ann_index = ann_index
        self._fairness_calculator = fairness_calculator

    async def calculate_scores(
        self,
        context: RequestContext,
        query: str,
        candidate_intents: list[str],
    ) -> dict[str, float]:
        """
        Calculate semantic scores for each candidate intent.
        
        Args:
            context: Request context with frozen snapshot
            query: Query text
            candidate_intents: List of intents to score
            
        Returns:
            Dict mapping intent to score
        """
        query_embedding = await self._embedding_model.embed(query)

        neighbors = await self._ann_index.search(
            query_embedding,
            k=10,
        )

        scores = {}
        for intent in candidate_intents:
            intent_examples = [n for n in neighbors if n.intent_path == intent]

            if not intent_examples:
                scores[intent] = 0.0
            else:
                avg_similarity = sum(e.similarity for e in intent_examples) / len(intent_examples)
                scores[intent] = avg_similarity

        return scores

    async def calculate_final_score(
        self,
        context: RequestContext,
        intent: str,
        semantic_score: float,
    ) -> float:
        """
        Calculate final score combining semantic + boost.
        
        Args:
            context: Request context
            intent: Intent to score
            semantic_score: Semantic similarity score
            
        Returns:
            Final combined score
        """
        snapshot = context.frozen_snapshot
        intent_config = snapshot.config.intents.get(intent)
        base_score = intent_config.base_score if intent_config else 0.5

        frequency_boost = await self._get_frequency_boost(context, intent)

        fair_boost = await self._fairness_calculator.calculate_boost(
            intent=intent,
            base_score=0.0,
            max_intent_boost=frequency_boost,
        )

        final_score = semantic_score * 0.7 + base_score * 0.2 + fair_boost * 0.1
        return final_score

    async def _get_frequency_boost(
        self,
        context: RequestContext,
        intent: str,
    ) -> float:
        """Get frequency-based boost from snapshot."""
        snapshot = context.frozen_snapshot
        frequency = snapshot.config.intents.get(intent, None)
        if frequency is None:
            return 0.0
        freq_value = frequency.frequency
        return math.log(1 + freq_value) / 10.0


class EmbeddingModel:
    """
    Interface for embedding models.
    
    Implement this to use your preferred embedding service.
    """

    async def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        raise NotImplementedError


class ANNIndex:
    """
    Interface for ANN index.
    
    Implement this to use your preferred ANN library (FAISS, Annoy, etc.)
    """

    async def search(
        self,
        query_embedding: list[float],
        k: int = 10,
    ) -> list[ANNNeighbor]:
        """
        Search ANN index for nearest neighbors.
        
        Args:
            query_embedding: Query vector
            k: Number of neighbors to return
            
        Returns:
            List of nearest neighbors
        """
        raise NotImplementedError

    async def add(
        self,
        intent_path: str,
        example_text: str,
        embedding: list[float],
    ) -> None:
        """Add embedding to index."""
        raise NotImplementedError


class InMemoryEmbeddingModel(EmbeddingModel):
    """Simple in-memory embedding model for testing."""

    def __init__(self, dimension: int = 128):
        self._dimension = dimension

    async def embed(self, text: str) -> list[float]:
        import hashlib
        h = hashlib.sha256(text.encode()).digest()
        vector = []
        for i in range(self._dimension):
            byte_idx = i % len(h)
            vector.append(float(h[byte_idx]) / 255.0)
        return vector


class InMemoryANNIndex(ANNIndex):
    """Simple in-memory ANN index for testing."""

    def __init__(self, dimension: int = 128):
        self._dimension = dimension
        self._vectors: list[tuple[str, str, list[float]]] = []

    async def search(
        self,
        query_embedding: list[float],
        k: int = 10,
    ) -> list[ANNNeighbor]:
        similarities = []
        for intent_path, example_text, embedding in self._vectors:
            sim = self._cosine_similarity(query_embedding, embedding)
            similarities.append(ANNNeighbor(
                intent_path=intent_path,
                example_text=example_text,
                embedding=embedding,
                similarity=sim,
            ))

        similarities.sort(key=lambda x: x.similarity, reverse=True)
        return similarities[:k]

    async def add(
        self,
        intent_path: str,
        example_text: str,
        embedding: list[float],
    ) -> None:
        self._vectors.append((intent_path, example_text, embedding))

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
