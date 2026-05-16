"""Search result caching for retrieval operations."""

import json
import logging
import time
from typing import Dict, List, Optional, Tuple

from src.core.config.agent_prompts import SEARCH_CACHE_MAX_ENTRIES, SEARCH_CACHE_TTL_SECONDS
from src.infrastructure.models import RetrievalHit, RetrievalQuery

logger = logging.getLogger(__name__)


class SearchCache:
    """LRU-stamped cache for retrieval search hits with TTL eviction."""

    def __init__(self) -> None:
        self._cache: Dict[str, Tuple[float, List[RetrievalHit]]] = {}

    def make_key(
        self,
        query: RetrievalQuery,
        top_k: int,
        allow_semantic: bool,
    ) -> str:
        return json.dumps({
            "query": query.raw_query,
            "normalized_query": query.normalized_query,
            "intent": query.intent,
            "filters": query.filters,
            "top_k": top_k,
            "allow_semantic": allow_semantic,
        }, sort_keys=True)

    def get(self, cache_key: str) -> Optional[List[RetrievalHit]]:
        entry = self._cache.get(cache_key)
        if not entry:
            return None
        cached_at, hits = entry
        if time.time() - cached_at > SEARCH_CACHE_TTL_SECONDS:
            self._cache.pop(cache_key, None)
            return None
        return [RetrievalHit(**{
            "chunk_id": hit.chunk_id,
            "path": hit.path,
            "source_type": hit.source_type,
            "score": hit.score,
            "text": hit.text,
            "summary": hit.summary,
            "lexical_score": hit.lexical_score,
            "vector_score": hit.vector_score,
            "rerank_score": hit.rerank_score,
            "score_breakdown": dict(hit.score_breakdown),
            "metadata": dict(hit.metadata),
        }) for hit in hits]

    def set(self, cache_key: str, hits: List[RetrievalHit]) -> None:
        if len(self._cache) >= SEARCH_CACHE_MAX_ENTRIES:
            oldest_key = min(self._cache.items(), key=lambda item: item[1][0])[0]
            self._cache.pop(oldest_key, None)
        self._cache[cache_key] = (time.time(), [RetrievalHit(**{
            "chunk_id": hit.chunk_id,
            "path": hit.path,
            "source_type": hit.source_type,
            "score": hit.score,
            "text": hit.text,
            "summary": hit.summary,
            "lexical_score": hit.lexical_score,
            "vector_score": hit.vector_score,
            "rerank_score": hit.rerank_score,
            "score_breakdown": dict(hit.score_breakdown),
            "metadata": dict(hit.metadata),
        }) for hit in hits])

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)
