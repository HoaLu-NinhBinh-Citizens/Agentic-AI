"""Context fusion for LLM fix/review prompts.

Turns a finding into a compact, relevant block of *related code* to fuse into
the LLM prompt, instead of sending only the few lines around the issue. Three
stages:

1. **Retrieve** — pull candidate snippets from an injected retriever (semantic
   memory, a vector store, etc.). The retriever is a Protocol so this module
   has no hard dependency on any embedding backend and stays unit-testable.
2. **Rerank** — order candidates by relevance to the query. If an embedder is
   supplied, rank by cosine similarity of embeddings; otherwise fall back to a
   deterministic lexical (Jaccard) overlap so reranking still works offline.
3. **Pack** — greedily fit the top snippets under a real *token* budget
   (via the project's TokenCounter), de-duplicating and truncating at line
   boundaries — replacing the previous crude 200-character cut.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Protocol

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")

# Async callable: text -> embedding vector. Returns [] on failure.
Embedder = Callable[[str], Awaitable[list[float]]]


@dataclass
class RetrievedSnippet:
    """A candidate context snippet returned by a retriever."""

    text: str
    score: float = 0.0  # retriever's own score (may be overwritten by rerank)
    source: str = ""  # file path / memory id, for attribution


class ContextRetriever(Protocol):
    async def retrieve(self, query: str, top_k: int) -> list[RetrievedSnippet]: ...


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text)}


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def rerank(
    query: str,
    snippets: list[RetrievedSnippet],
    embedder: Optional[Embedder] = None,
) -> list[RetrievedSnippet]:
    """Return snippets ordered most→least relevant to ``query``.

    Uses embedding cosine similarity when ``embedder`` is provided and yields a
    usable query vector; otherwise falls back to lexical Jaccard overlap. Ties
    are broken by the snippet's original retriever score then text for
    determinism.
    """
    if not snippets:
        return []

    scored: list[tuple[float, RetrievedSnippet]] = []

    query_vec: list[float] = []
    if embedder is not None:
        try:
            query_vec = await embedder(query)
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Embedder failed for query, using lexical rerank: %s", exc)
            query_vec = []

    for snip in snippets:
        relevance = 0.0
        if query_vec:
            try:
                vec = await embedder(snip.text)  # type: ignore[misc]
                relevance = _cosine(query_vec, vec)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("Embedder failed for snippet, lexical fallback: %s", exc)
                relevance = _jaccard(query, snip.text)
        else:
            relevance = _jaccard(query, snip.text)
        scored.append((relevance, snip))

    scored.sort(key=lambda s: (-s[0], -s[1].score, s[1].text))
    out: list[RetrievedSnippet] = []
    for relevance, snip in scored:
        out.append(RetrievedSnippet(text=snip.text, score=relevance, source=snip.source))
    return out


class _LenCounter:
    """Fallback token counter (~4 chars/token) when TokenCounter is unavailable."""

    def count(self, text: str) -> int:
        return max(1, len(text) // 4)


def _get_token_counter(counter):
    if counter is not None:
        return counter
    try:
        from src.infrastructure.llm.token_tracker import TokenCounter

        return TokenCounter()
    except Exception:  # pragma: no cover - defensive
        return _LenCounter()


def pack_context(
    snippets: list[RetrievedSnippet],
    max_tokens: int,
    token_counter=None,
    header: str = "Related code (most relevant first):",
) -> str:
    """Pack reranked snippets under a token budget.

    Greedily adds snippets in order, de-duplicating identical text and skipping
    those that would exceed ``max_tokens``. The first snippet that does not fit
    whole is truncated at a line boundary if a meaningful remainder fits;
    packing then stops. Returns an empty string if nothing fits.
    """
    if not snippets or max_tokens <= 0:
        return ""

    counter = _get_token_counter(token_counter)
    used = counter.count(header) + 1
    seen: set[str] = set()
    blocks: list[str] = []

    for snip in snippets:
        text = snip.text.strip()
        if not text:
            continue
        norm = re.sub(r"\s+", " ", text)
        if norm in seen:
            continue

        block = f"# from {snip.source}\n{text}" if snip.source else text
        cost = counter.count(block) + 1

        if used + cost <= max_tokens:
            blocks.append(block)
            seen.add(norm)
            used += cost
            continue

        # Try to fit a line-truncated remainder, then stop.
        remaining = max_tokens - used
        if remaining > counter.count(header):  # only if room for something useful
            truncated = _truncate_to_tokens(block, remaining, counter)
            if truncated.strip():
                blocks.append(truncated + "\n# … (truncated)")
        break

    if not blocks:
        return ""
    return header + "\n" + "\n\n".join(blocks)


def _truncate_to_tokens(text: str, max_tokens: int, counter) -> str:
    """Trim ``text`` to fit ``max_tokens``, cutting on whole lines."""
    lines = text.splitlines()
    kept: list[str] = []
    used = 0
    for line in lines:
        cost = counter.count(line) + 1
        if used + cost > max_tokens:
            break
        kept.append(line)
        used += cost
    return "\n".join(kept)


class ContextFusion:
    """Orchestrates retrieve → rerank → pack into a prompt-ready block."""

    def __init__(
        self,
        retriever: ContextRetriever,
        embedder: Optional[Embedder] = None,
        token_counter=None,
        max_tokens: int = 800,
        top_k: int = 8,
    ) -> None:
        self._retriever = retriever
        self._embedder = embedder
        self._token_counter = token_counter
        self._max_tokens = max_tokens
        self._top_k = top_k

    async def build_context(
        self,
        query: str,
        max_tokens: Optional[int] = None,
        top_k: Optional[int] = None,
    ) -> str:
        """Return a packed, reranked context block for ``query`` (may be empty)."""
        budget = max_tokens if max_tokens is not None else self._max_tokens
        k = top_k if top_k is not None else self._top_k
        try:
            candidates = await self._retriever.retrieve(query, k)
        except Exception as exc:
            logger.warning("Context retrieval failed: %s", exc)
            return ""
        if not candidates:
            return ""
        ranked = await rerank(query, candidates, self._embedder)
        return pack_context(ranked, budget, self._token_counter)
