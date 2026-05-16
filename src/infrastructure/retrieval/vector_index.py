import concurrent.futures
import hashlib
import json
import logging
from pathlib import Path
from typing import Dict, List, Tuple

from src.core.config.agent_prompts import (
    RAG_SCHEMA_VERSION,
    RAG_VECTOR_DATA_FILE,
    RAG_VECTOR_META_FILE,
    VECTOR_BUILD_BATCH_SIZE,
)
from src.infrastructure.models import ChunkRecord

try:
    import numpy as np
except ImportError:
    np = None

logger = logging.getLogger(__name__)


class VectorIndex:
    """Persist semantic vectors beside the chunk store and search them by cosine similarity."""

    def __init__(self, workspace_root: str, embedding_client):
        self.workspace_root = Path(workspace_root)
        self.embedding_client = embedding_client
        self.meta_path = self.workspace_root / RAG_VECTOR_META_FILE
        self.data_path = self.workspace_root / RAG_VECTOR_DATA_FILE
        self._chunk_ids: List[str] = []
        self._vectors = None
        self._vector_by_chunk: Dict[str, object] = {}
        self._vector_dim = 0
        self._loaded = False
        self._semantic_warning_emitted = False

    def ensure_for_chunks(self, chunks: List[ChunkRecord]) -> bool:
        if np is None:
            return False
        self._load()
        if not chunks:
            return self._vectors is not None and bool(self._chunk_ids)
        if self._vectors is None or not self._chunk_ids or not self._is_current(chunks):
            try:
                self._rebuild(chunks)
            except Exception as exc:
                self._warn_semantic_unavailable(exc)
                return False
        return True

    def search(self, query_text: str, top_k: int = 5) -> Dict[str, float]:
        if np is None or not str(query_text).strip():
            return {}
        self._load()
        if self._vectors is None or not self._chunk_ids:
            return {}
        try:
            query_vectors = self.embedding_client.embed_texts([query_text])
        except Exception as exc:
            self._warn_semantic_unavailable(exc)
            return {}
        if not query_vectors:
            return {}
        query_vector = self._normalize(np.asarray(query_vectors[0], dtype=np.float32))
        if not self._query_vector_matches_index(query_vector):
            self._warn_semantic_unavailable(ValueError("Query embedding dimension does not match vector index"))
            return {}
        scores = self._vectors @ query_vector
        ranked_indices = np.argsort(scores)[::-1][:max(top_k, 1)]
        return {
            self._chunk_ids[int(index)]: float(scores[int(index)])
            for index in ranked_indices
            if float(scores[int(index)]) > 0
        }

    def score_candidates(self, query_text: str, chunks: List[ChunkRecord], top_k: int = 5) -> Dict[str, float]:
        if np is None or not str(query_text).strip() or not chunks:
            return {}
        self._load()
        missing = [chunk for chunk in chunks if chunk.chunk_id not in self._vector_by_chunk]
        if missing:
            texts = [self._build_embedding_text(chunk) for chunk in missing]
            try:
                vectors = self.embedding_client.embed_texts(texts)
            except Exception as exc:
                self._warn_semantic_unavailable(exc)
                return {}
            if len(vectors) == len(missing):
                for chunk, vector in zip(missing, vectors):
                    self._vector_by_chunk[chunk.chunk_id] = self._normalize(np.asarray(vector, dtype=np.float32))
                self._persist_cache()

        try:
            query_vectors = self.embedding_client.embed_texts([query_text])
        except Exception as exc:
            self._warn_semantic_unavailable(exc)
            return {}
        if not query_vectors:
            return {}
        query_vector = self._normalize(np.asarray(query_vectors[0], dtype=np.float32))
        if not self._query_vector_matches_index(query_vector):
            self._warn_semantic_unavailable(ValueError("Query embedding dimension does not match vector cache"))
            return {}
        scored: List[Tuple[str, float]] = []
        for chunk in chunks:
            vector = self._vector_by_chunk.get(chunk.chunk_id)
            if vector is None:
                continue
            vector_array = np.asarray(vector, dtype=np.float32)
            scored.append((chunk.chunk_id, float(np.dot(vector_array, query_vector))))
        scored.sort(key=lambda item: item[1], reverse=True)
        return {chunk_id: score for chunk_id, score in scored[:max(top_k, 1)] if score > 0}

    def _rebuild(self, chunks: List[ChunkRecord]):
        if np is None:
            raise ValueError("NumPy is required to rebuild the vector index")
        texts = [self._build_embedding_text(chunk) for chunk in chunks]
        vectors: List[List[float]] = [[] for _ in range(len(texts))]
        batches = []
        for start in range(0, len(texts), VECTOR_BUILD_BATCH_SIZE):
            batches.append((start, texts[start:start + VECTOR_BUILD_BATCH_SIZE]))

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            future_to_batch = {executor.submit(self.embedding_client.embed_texts, batch): start for start, batch in batches}
            for future in concurrent.futures.as_completed(future_to_batch):
                start = future_to_batch[future]
                batch_vectors = future.result()
                for index, vector in enumerate(batch_vectors):
                    vectors[start + index] = vector

        if len([vector for vector in vectors if vector]) != len(chunks):
            raise ValueError("Vector index rebuild returned an unexpected embedding count")
        vector_array = np.asarray(vectors, dtype=np.float32)
        if getattr(vector_array, "ndim", 0) != 2 or len(vector_array) != len(chunks):
            raise ValueError("Vector index rebuild produced an invalid vector matrix")
        self._vectors = self._normalize(vector_array)
        self._chunk_ids = [chunk.chunk_id for chunk in chunks]
        self._vector_dim = int(self._vectors.shape[1]) if len(self._vectors.shape) > 1 else 0
        self._loaded = True
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.data_path, vectors=self._vectors)
        self.meta_path.write_text(json.dumps({
            "schema": RAG_SCHEMA_VERSION,
            "model": self.embedding_client.model,
            "chunk_hash": self._chunk_hash(chunks),
            "chunk_ids": self._chunk_ids,
            "vector_dim": self._vector_dim,
            "vector_count": len(self._chunk_ids),
        }, indent=2), encoding="utf-8")

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        if np is None or not self.data_path.exists() or not self.meta_path.exists():
            return
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if str(meta.get("schema", "")).strip() != RAG_SCHEMA_VERSION:
                raise ValueError("Vector index schema mismatch")
            if str(meta.get("model", "")).strip() != self.embedding_client.model:
                raise ValueError("Vector index model mismatch")
            data = np.load(self.data_path)
            vectors = data["vectors"].astype(np.float32)
            if getattr(vectors, "ndim", 0) != 2:
                raise ValueError("Vector index payload is not a matrix")
            self._chunk_ids = [str(item) for item in meta.get("chunk_ids", [])]
            expected_count = int(meta.get("vector_count", len(self._chunk_ids)) or 0)
            expected_dim = int(meta.get("vector_dim", 0) or 0)
            if expected_count and expected_count != len(self._chunk_ids):
                raise ValueError("Vector index chunk count metadata mismatch")
            if len(self._chunk_ids) != len(vectors):
                raise ValueError("Vector index row count does not match chunk ids")
            if expected_dim and vectors.shape[1] != expected_dim:
                raise ValueError("Vector index dimension metadata mismatch")
            self._vectors = vectors
            self._vector_dim = int(vectors.shape[1])
            self._vector_by_chunk = {
                chunk_id: self._vectors[index]
                for index, chunk_id in enumerate(self._chunk_ids)
                if index < len(self._vectors)
            }
        except Exception as exc:
            logger.warning("Failed to load semantic vector index: %s", exc)
            self._chunk_ids = []
            self._vectors = None
            self._vector_by_chunk = {}

    def _persist_cache(self):
        if np is None or not self._vector_by_chunk:
            return
        self._chunk_ids = list(self._vector_by_chunk.keys())
        self._vectors = np.asarray([self._vector_by_chunk[chunk_id] for chunk_id in self._chunk_ids], dtype=np.float32)
        if getattr(self._vectors, "ndim", 0) != 2 or len(self._vectors) != len(self._chunk_ids):
            raise ValueError("Vector cache payload is invalid")
        self._vector_dim = int(self._vectors.shape[1]) if len(self._vectors.shape) > 1 else 0
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(self.data_path, vectors=self._vectors)
        self.meta_path.write_text(json.dumps({
            "schema": RAG_SCHEMA_VERSION,
            "model": self.embedding_client.model,
            "chunk_hash": self._chunk_hash_from_ids(self._chunk_ids),
            "chunk_ids": self._chunk_ids,
            "vector_dim": self._vector_dim,
            "vector_count": len(self._chunk_ids),
        }, indent=2), encoding="utf-8")

    def _is_current(self, chunks: List[ChunkRecord]) -> bool:
        if not self.meta_path.exists() or not self.data_path.exists():
            return False
        try:
            meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return (
            str(meta.get("schema", "")).strip() == RAG_SCHEMA_VERSION
            and str(meta.get("model", "")).strip() == self.embedding_client.model
            and str(meta.get("chunk_hash", "")).strip() == self._chunk_hash(chunks)
            and int(meta.get("vector_count", len(meta.get("chunk_ids", []))) or 0) == len(chunks)
        )

    def _chunk_hash(self, chunks: List[ChunkRecord]) -> str:
        return self._chunk_hash_from_ids([chunk.chunk_id for chunk in chunks])

    def _chunk_hash_from_ids(self, chunk_ids: List[str]) -> str:
        digest = hashlib.sha1()
        for chunk_id in chunk_ids:
            digest.update(str(chunk_id).encode("utf-8"))
        return digest.hexdigest()

    def _build_embedding_text(self, chunk: ChunkRecord) -> str:
        parts = [
            chunk.path,
            chunk.section,
            chunk.summary,
            chunk.text[:2400],
            str(chunk.metadata.get("title", "")),
            " ".join(str(item) for item in chunk.metadata.get("topics", []) if str(item).strip()) if isinstance(chunk.metadata.get("topics", []), list) else str(chunk.metadata.get("topics", "")),
        ]
        return "\n".join(part for part in parts if str(part).strip())

    def _normalize(self, values):
        if np is None:
            return values
        if getattr(values, "ndim", 1) == 1:
            denom = float(np.linalg.norm(values)) or 1.0
            return values / denom
        denom = np.linalg.norm(values, axis=1, keepdims=True)
        denom[denom == 0] = 1.0
        return values / denom

    def _warn_semantic_unavailable(self, exc: Exception):
        if self._semantic_warning_emitted:
            return
        self._semantic_warning_emitted = True
        logger.warning("Semantic retrieval unavailable; falling back to lexical-only search: %s", exc)

    def _query_vector_matches_index(self, query_vector) -> bool:
        if self._vectors is None:
            return False
        if self._vector_dim <= 0:
            return True
        return int(getattr(query_vector, "shape", [0])[0]) == self._vector_dim

