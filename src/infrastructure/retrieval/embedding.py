import hashlib
import time
from typing import Dict, List, Optional

import requests

from src.core.config.agent_prompts import VECTOR_EMBED_MODEL


class OllamaEmbeddingClient:
    """Embed retrieval text locally through Ollama so semantic search stays offline."""

    def __init__(self, url: str = "http://localhost:11434", model: str = VECTOR_EMBED_MODEL):
        self.url = url
        self.model = model
        self.connect_timeout_seconds = 10
        self.read_timeout_seconds = 60
        self.cooldown_seconds = 30
        self._disabled_until = 0.0
        self._cache: Dict[str, List[float]] = {}
        self._vector_size: Optional[int] = None

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        cleaned = [str(text).strip() for text in texts if str(text).strip()]
        if not cleaned:
            return []
        now = time.time()
        if now < self._disabled_until:
            raise RuntimeError("Embedding backend temporarily unavailable")
        cache_keys = [self._cache_key(text) for text in cleaned]
        cached_results = [self._cache.get(key) for key in cache_keys]
        missing_pairs = [
            (key, text)
            for key, text, cached in zip(cache_keys, cleaned, cached_results)
            if cached is None
        ]
        if not missing_pairs:
            return [list(self._cache[key]) for key in cache_keys]

        uncached_keys: List[str] = []
        uncached_texts: List[str] = []
        seen_uncached = set()
        for key, text in missing_pairs:
            if key in seen_uncached:
                continue
            seen_uncached.add(key)
            uncached_keys.append(key)
            uncached_texts.append(text)
        try:
            response = requests.post(
                f"{self.url}/api/embed",
                json={"model": self.model, "input": uncached_texts},
                timeout=(self.connect_timeout_seconds, self.read_timeout_seconds),
            )
            response.raise_for_status()
            embeddings = response.json().get("embeddings", [])
            if isinstance(embeddings, list) and len(embeddings) == len(uncached_texts):
                self._disabled_until = 0.0
                for key, item in zip(uncached_keys, embeddings):
                    self._cache[key] = self._coerce_vector(item)
                return [list(self._cache[key]) for key in cache_keys]
        except Exception:
            self._disabled_until = time.time() + self.cooldown_seconds

        try:
            for key, text in zip(uncached_keys, uncached_texts):
                response = requests.post(
                    f"{self.url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=(self.connect_timeout_seconds, self.read_timeout_seconds),
                )
                response.raise_for_status()
                self._cache[key] = self._coerce_vector(response.json().get("embedding", []))
        except Exception:
            self._disabled_until = time.time() + self.cooldown_seconds
            raise
        self._disabled_until = 0.0
        return [list(self._cache[key]) for key in cache_keys]

    def _coerce_vector(self, values: object) -> List[float]:
        if not isinstance(values, list):
            raise ValueError("Invalid embedding payload returned by Ollama")
        vector = [float(value) for value in values]
        if not vector:
            raise ValueError("Empty embedding payload returned by Ollama")
        if self._vector_size is None:
            self._vector_size = len(vector)
        elif len(vector) != self._vector_size:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self._vector_size}, got {len(vector)}"
            )
        return vector

    def _cache_key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}\n{text}".encode("utf-8")).hexdigest()

    def is_temporarily_unavailable(self) -> bool:
        return time.time() < self._disabled_until

