"""
ChromaDB-backed vector store for production-scale semantic search.

Replaces the NumPy-based VectorIndex when rag.vector_backend is set to "chromadb"
in the config. Provides:
- Persistent storage with automatic saving
- HNSW-based approximate nearest-neighbor search
- Incremental add/update/delete of chunks
- Collection management with metadata filtering
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.config.agent_prompts import RAG_SCHEMA_VERSION

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """
    Production-grade vector store backed by ChromaDB.

    Provides ANN (Approximate Nearest Neighbor) search using HNSW indexing,
    which scales to millions of vectors efficiently. Supports incremental
    updates without full reindexing.
    """

    def __init__(self, workspace_root: str, embedding_client, collection_name: str = "carv_embeddings"):
        self.workspace_root = Path(workspace_root)
        self.embedding_client = embedding_client
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._chunk_id_to_chroma_id: Dict[str, str] = {}
        self._semantic_warning_emitted = False

    def _get_client(self):
        """Lazy-initialize the ChromaDB client."""
        if self._client is not None:
            return self._client
        try:
            import chromadb
            from chromadb.config import Settings as ChromaSettings

            persist_dir = str(self.workspace_root / "rag_index" / "chromadb")
            Path(persist_dir).mkdir(parents=True, exist_ok=True)

            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )
            logger.info("ChromaDB client initialized at %s", persist_dir)
        except ImportError:
            logger.error("ChromaDB not installed. Run: pip install chromadb")
            raise
        return self._client

    def _get_collection(self):
        """Get or create the embeddings collection."""
        if self._collection is not None:
            return self._collection
        client = self._get_client()
        try:
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"schema": RAG_SCHEMA_VERSION, "embedding_model": self.embedding_client.model},
            )
            self._load_id_map()
            if not self._is_current():
                logger.warning(
                    "ChromaDB collection schema mismatch (expected=%s), will rebuild on next index",
                    RAG_SCHEMA_VERSION,
                )
            logger.info(
                "ChromaDB collection '%s' ready: %d chunks indexed",
                self.collection_name,
                self._collection.count(),
            )
        except Exception as exc:
            logger.error("Failed to create ChromaDB collection: %s", exc)
            raise
        return self._collection

    def _is_current(self) -> bool:
        """Check if the ChromaDB collection matches current schema version."""
        try:
            collection = self._get_collection()
            if collection is None:
                return False
            meta = collection.metadata or {}
            stored_version = meta.get("schema", "")
            return str(stored_version) == str(RAG_SCHEMA_VERSION)
        except Exception:
            return False

    def _load_id_map(self):
        """Load the chunk_id -> chroma_id mapping from existing collection."""
        if self._collection is None:
            return
        try:
            all_data = self._collection.get(include=["metadatas"])
            for i, meta in enumerate(all_data.get("metadatas", [])):
                chunk_id = meta.get("chunk_id", "") if meta else ""
                if chunk_id:
                    self._chunk_id_to_chroma_id[chunk_id] = all_data["ids"][i]
        except Exception as exc:
            logger.warning("Failed to load ChromaDB id map: %s", exc)

    def ensure_for_chunks(self, chunks: List) -> bool:
        """
        Ensure the store is ready for the given chunks.

        For ChromaDB, we don't need to rebuild the entire index on startup.
        We can incrementally add missing chunks.
        """
        try:
            collection = self._get_collection()
            existing_count = collection.count()

            # Find chunks that aren't indexed yet
            new_chunks = []
            for chunk in chunks:
                chunk_id = getattr(chunk, "chunk_id", str(chunk))
                if chunk_id not in self._chunk_id_to_chroma_id:
                    new_chunks.append(chunk)

            if new_chunks:
                self._index_chunks(new_chunks)
                logger.info(
                    "ChromaDB: Added %d new chunks (total: %d)",
                    len(new_chunks),
                    collection.count(),
                )
            return True
        except Exception as exc:
            self._warn_semantic_unavailable(exc)
            return False

    def _index_chunks(self, chunks: List):
        """Index a batch of chunks into ChromaDB."""
        if not chunks:
            return

        from src.infrastructure.models import ChunkRecord

        ids = []
        embeddings = []
        metadatas = []
        documents = []

        chunk_texts = []
        for chunk in chunks:
            if isinstance(chunk, ChunkRecord):
                chunk_id = chunk.chunk_id
                text = self._build_embedding_text(chunk)
            else:
                chunk_id = getattr(chunk, "chunk_id", str(chunk))
                text = getattr(chunk, "text", str(chunk))

            chunk_texts.append(text)
            ids.append(chunk_id)
            metadata = {}
            if isinstance(chunk, ChunkRecord):
                metadata = {
                    "chunk_id": chunk.chunk_id,
                    "path": getattr(chunk, "path", ""),
                    "section": getattr(chunk, "section", ""),
                    "summary": getattr(chunk, "summary", ""),
                }
                for k, v in (getattr(chunk, "metadata", {}) or {}).items():
                    if k not in metadata:
                        metadata[k] = str(v)
            else:
                metadata = {"chunk_id": chunk_id}
            metadatas.append(metadata)
            documents.append(text)

        # Generate embeddings
        vectors = self.embedding_client.embed_texts(chunk_texts)

        collection = self._get_collection()
        collection.add(
            ids=ids,
            embeddings=vectors,
            metadatas=metadatas,
            documents=documents,
        )

        # Update id map
        for chunk_id in ids:
            self._chunk_id_to_chroma_id[chunk_id] = chunk_id

    def search(self, query_text: str, top_k: int = 5) -> Dict[str, float]:
        """
        Search for the top_k most similar chunks.

        Returns a dict mapping chunk_id -> cosine similarity score.
        """
        try:
            collection = self._get_collection()
            if collection.count() == 0:
                return {}

            query_vector = self.embedding_client.embed_texts([query_text])
            if not query_vector:
                return {}

            results = collection.query(
                query_embeddings=query_vector,
                n_results=top_k,
                include=["distances", "metadatas"],
            )

            scores: Dict[str, float] = {}
            for i, chroma_id in enumerate(results.get("ids", [[]])[0] or []):
                distance = results.get("distances", [[]])[0] or [1.0]
                dist = distance[i] if i < len(distance) else 1.0
                # Convert L2 distance to cosine similarity (approximate for normalized vectors)
                similarity = max(0.0, 1.0 - dist / 2.0)
                chunk_id = str(results.get("metadatas", [[{}]])[0][i].get("chunk_id", chroma_id) if i < len(results.get("metadatas", [[]])[0] or []) else chroma_id)
                scores[chroma_id] = float(similarity)

            return scores
        except Exception as exc:
            self._warn_semantic_unavailable(exc)
            return {}

    def score_candidates(self, query_text: str, chunks: List, top_k: int = 5) -> Dict[str, float]:
        """
        Score specific candidate chunks against a query.

        More accurate than search() when you have a candidate set.
        """
        try:
            if not chunks:
                return {}
            collection = self._get_collection()
            chunk_ids = [getattr(c, "chunk_id", str(c)) for c in chunks]
            existing_ids = [cid for cid in chunk_ids if cid in self._chunk_id_to_chroma_id]

            if not existing_ids:
                return {}

            results = collection.get(ids=existing_ids, include=["embeddings", "metadatas"])
            if not results.get("ids"):
                return {}

            query_vectors = self.embedding_client.embed_texts([query_text])
            if not query_vectors:
                return {}
            query_vector = query_vectors[0]

            import numpy as np

            scores: Dict[str, float] = {}
            for i, emb in enumerate(results.get("embeddings", []) or []):
                if not emb:
                    continue
                chunk_id = results["ids"][i]
                similarity = float(np.dot(np.array(emb), np.array(query_vector)))
                scores[chunk_id] = similarity

            # Sort and return top_k
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            return dict(sorted_scores[:top_k])
        except Exception as exc:
            self._warn_semantic_unavailable(exc)
            return {}

    def add_chunk(self, chunk) -> bool:
        """Add a single chunk to the store."""
        try:
            if self._get_collection().count() == 0:
                self._index_chunks([chunk])
            else:
                self._index_chunks([chunk])
            return True
        except Exception as exc:
            logger.warning("Failed to add chunk to ChromaDB: %s", exc)
            return False

    def delete_chunk(self, chunk_id: str) -> bool:
        """Delete a chunk from the store."""
        try:
            collection = self._get_collection()
            chroma_id = self._chunk_id_to_chroma_id.get(chunk_id, chunk_id)
            collection.delete(ids=[chroma_id])
            self._chunk_id_to_chroma_id.pop(chunk_id, None)
            logger.info("ChromaDB: Deleted chunk %s", chunk_id)
            return True
        except Exception as exc:
            logger.warning("Failed to delete chunk from ChromaDB: %s", exc)
            return False

    def reset(self) -> bool:
        """Delete all chunks from the collection."""
        try:
            client = self._get_client()
            try:
                client.delete_collection(self.collection_name)
            except Exception:
                pass
            self._collection = None
            self._chunk_id_to_chroma_id.clear()
            logger.info("ChromaDB: Collection '%s' reset", self.collection_name)
            return True
        except Exception as exc:
            logger.warning("Failed to reset ChromaDB collection: %s", exc)
            return False

    def _build_embedding_text(self, chunk) -> str:
        """Build text representation for embedding."""
        if hasattr(chunk, "path"):
            parts = [
                str(getattr(chunk, "path", "")),
                str(getattr(chunk, "section", "")),
                str(getattr(chunk, "summary", "")),
                str(getattr(chunk, "text", "")[:2400]),
            ]
            metadata = getattr(chunk, "metadata", {}) or {}
            parts.append(str(metadata.get("title", "")))
            topics = metadata.get("topics", [])
            if isinstance(topics, list):
                parts.append(" ".join(str(t) for t in topics if str(t).strip()))
            else:
                parts.append(str(topics))
            return "\n".join(p for p in parts if str(p).strip())
        return str(chunk)[:2400]

    def _warn_semantic_unavailable(self, exc: Exception):
        if self._semantic_warning_emitted:
            return
        self._semantic_warning_emitted = True
        logger.warning("ChromaDB semantic retrieval unavailable; falling back to lexical-only: %s", exc)

    @property
    def count(self) -> int:
        """Return the number of indexed chunks."""
        try:
            return self._get_collection().count()
        except Exception:
            return 0


def create_vector_store(
    workspace_root: str,
    embedding_client,
    backend: str = "numpy",
) -> object:
    """
    Factory function to create the appropriate vector store backend.

    Args:
        workspace_root: Project root directory.
        embedding_client: OllamaEmbeddingClient instance.
        backend: "numpy" (default) or "chromadb".

    Returns:
        VectorIndex (numpy) or ChromaVectorStore (chromadb) instance.
    """
    if backend == "chromadb":
        from src.core.config.config_loader import get_config
        cfg = get_config()
        collection_name = cfg.get("rag.chromadb.collection_name", "carv_embeddings")
        logger.info("Using ChromaDB vector store (collection: %s)", collection_name)
        return ChromaVectorStore(workspace_root, embedding_client, collection_name=collection_name)

    # Default: NumPy backend
    from src.infrastructure.retrieval.vector_index import VectorIndex
    return VectorIndex(workspace_root, embedding_client)
