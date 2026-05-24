"""Knowledge embeddings with semantic vector generation."""

from __future__ import annotations

import hashlib
import math
from typing import Any


class KnowledgeEmbeddings:
    """
    Embedding management for knowledge entries.

    Primary: use EmbeddingService (Ollama bge-m3) via KnowledgeBase.set_embed_service()
    Fallback: deterministic hash-based embeddings for offline use
    """

    def __init__(self):
        self._embeddings: dict[str, list[float]] = {}

    def add(self, key: str, embedding: list[float]) -> None:
        """Add embedding for a key."""
        self._embeddings[key] = embedding

    def get(self, key: str) -> list[float] | None:
        """Get embedding by key."""
        return self._embeddings.get(key)

    def fallback_embedding(self, text: str, dimension: int = 384) -> list[float]:
        """
        Generate a deterministic fallback embedding from text hash.

        Uses locality-sensitive hashing via word-level hashing.
        NOT semantic — only provides consistent embeddings when Ollama is unavailable.

        Args:
            text: Text to embed
            dimension: Embedding dimension (default 384 for bge-m3)

        Returns:
            Dense vector of floats
        """
        words = text.lower().split()
        if not words:
            return [0.0] * dimension

        # Hash each word into the embedding space
        vector = [0.0] * dimension
        for word in words:
            word_hash = hashlib.sha256(word.encode()).digest()
            for i in range(min(len(word_hash), dimension)):
                # Map byte to [-1, 1] range
                vector[i] += (word_hash[i] / 128.0) - 1.0

        # Normalize to unit sphere
        norm = math.sqrt(sum(v * v for v in vector))
        if norm > 0:
            vector = [v / norm for v in vector]

        return vector

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two embeddings."""
        if len(a) != len(b) or not a:
            return 0.0

        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)
