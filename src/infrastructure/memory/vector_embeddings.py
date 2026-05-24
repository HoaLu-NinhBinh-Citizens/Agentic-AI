"""Vector embeddings integration for semantic memory search.

Provides:
- Embedding generation using local models (onnxruntime, transformers, or openai)
- Vector storage with cosine similarity search
- Hybrid search (vector + keyword)

Uses a lazy-loading approach - embeddings are generated on demand.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np


class EmbeddingError(Exception):
    """Error during embedding generation."""
    pass


class EmbeddingModel:
    """Abstraction for embedding models.
    
    Supports multiple backends:
    - onnxruntime: Local ONNX models (fastest, no GPU needed)
    - transformers: HuggingFace transformers (accurate, slower)
    - openai: OpenAI embeddings API (best quality, requires API key)
    """
    
    def __init__(
        self,
        backend: str = "auto",
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        device: str = "cpu",
        normalize: bool = True,
    ):
        self.backend = backend
        self.model_name = model_name
        self.device = device
        self.normalize = normalize
        self._model = None
        self._tokenizer = None
    
    def _load_onnx(self) -> tuple[Any, Any]:
        """Load ONNX Runtime model."""
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer
            
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = (
                ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            )
            
            # Download model if needed
            cache_dir = Path.home() / ".cache" / "ai-support" / "models"
            model_path = cache_dir / f"{self.model_name.replace('/', '_')}.onnx"
            
            if not model_path.exists():
                cache_dir.mkdir(parents=True, exist_ok=True)
                self._download_and_convert_model(model_path)
            
            session = ort.InferenceSession(str(model_path), sess_options)
            tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            
            return session, tokenizer
        except ImportError as e:
            raise EmbeddingError(f"ONNX Runtime not available: {e}")
    
    def _download_and_convert_model(self, output_path: Path):
        """Download and convert HuggingFace model to ONNX."""
        from transformers import AutoTokenizer, AutoModel
        import torch
        
        print(f"Downloading model {self.model_name}...")
        tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        model = AutoModel.from_pretrained(self.model_name)
        model.eval()
        
        # Export to ONNX
        torch.onnx.export(
            model,
            (torch.randn(1, 128),),
            str(output_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["embeddings"],
            dynamic_axes={
                "input_ids": {0: "batch", 1: "sequence"},
                "attention_mask": {0: "batch", 1: "sequence"},
                "embeddings": {0: "batch", 1: "sequence"},
            },
        )
        print(f"Model saved to {output_path}")
    
    def _load_transformers(self):
        """Load transformers model."""
        try:
            from transformers import AutoTokenizer, AutoModel
            import torch
            
            tokenizer = AutoTokenizer.from_pretrained(self.model_name)
            model = AutoModel.from_pretrained(self.model_name)
            
            if self.device == "cuda":
                model = model.cuda()
            
            model.eval()
            return model, tokenizer
        except ImportError as e:
            raise EmbeddingError(f"Transformers not available: {e}")
    
    def _mean_pooling(self, model_output: Any, attention_mask: Any) -> np.ndarray:
        """Mean pool token embeddings to get sentence embedding."""
        token_embeddings = model_output[0]
        input_mask_expanded = np.expand_dims(attention_mask, -1) * np.ones_like(token_embeddings)
        return np.sum(token_embeddings * input_mask_expanded, 1) / np.clip(
            np.sum(input_mask_expanded), a_min=1e-9, a_max=None
        )
    
    def _normalize_embeddings(self, embeddings: np.ndarray) -> np.ndarray:
        """L2 normalize embeddings."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / np.clip(norms, a_min=1e-9, a_max=None)
    
    def encode(self, texts: str | list[str]) -> np.ndarray:
        """Generate embeddings for text(s).
        
        Args:
            texts: Single text or list of texts
            
        Returns:
            Numpy array of embeddings (shape: [n_texts, embedding_dim])
        """
        if isinstance(texts, str):
            texts = [texts]
        
        # Lazy load model
        if self._model is None:
            if self.backend == "onnxruntime":
                self._model, self._tokenizer = self._load_onnx()
            elif self.backend == "transformers":
                self._model, self._tokenizer = self._load_transformers()
            elif self.backend == "auto":
                # Try onnx first, fall back to transformers
                try:
                    self._model, self._tokenizer = self._load_onnx()
                    self.backend = "onnxruntime"
                except EmbeddingError:
                    self._model, self._tokenizer = self._load_transformers()
                    self.backend = "transformers"
            else:
                raise EmbeddingError(f"Unknown backend: {self.backend}")
        
        # Tokenize
        encoded = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="np",
        )
        
        # Get embeddings
        if self.backend == "onnxruntime":
            inputs = {
                "input_ids": encoded["input_ids"],
                "attention_mask": encoded["attention_mask"],
            }
            outputs = self._model.run(None, inputs)
            embeddings = outputs[0]
        else:
            import torch
            with torch.no_grad():
                outputs = self._model(
                    input_ids=torch.tensor(encoded["input_ids"]),
                    attention_mask=torch.tensor(encoded["attention_mask"]),
                )
                embeddings = self._mean_pooling(
                    outputs.last_hidden_state.cpu().numpy(),
                    encoded["attention_mask"],
                )
        
        # Normalize
        if self.normalize:
            embeddings = self._normalize_embeddings(embeddings)
        
        return embeddings


@dataclass
class VectorEntry:
    """A vector-stored memory entry."""
    id: str
    content: str
    embedding: np.ndarray
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class VectorStore:
    """Simple in-memory vector store with cosine similarity search.
    
    For production, replace with:
    - SQLite with sqlite-vector extension
    - Qdrant for distributed vectors
    - Chroma for local persistence
    """
    
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.entries: dict[str, VectorEntry] = {}
        self._dirty = False
    
    def add(self, entry: VectorEntry) -> None:
        """Add an entry to the store."""
        if entry.embedding.shape != (self.dimension,):
            raise ValueError(f"Embedding dimension mismatch: expected {self.dimension}")
        self.entries[entry.id] = entry
        self._dirty = True
    
    def search(
        self,
        query_embedding: np.ndarray,
        limit: int = 5,
        min_score: float = 0.0,
        filter_ids: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Search for similar entries using cosine similarity.
        
        Args:
            query_embedding: Query vector
            limit: Maximum results
            min_score: Minimum similarity score (0-1)
            filter_ids: Optional set of IDs to filter
            
        Returns:
            List of (entry_id, similarity_score) tuples
        """
        results: list[tuple[str, float]] = []
        
        for entry_id, entry in self.entries.items():
            if filter_ids and entry_id not in filter_ids:
                continue
            
            # Cosine similarity (already normalized)
            score = float(np.dot(query_embedding, entry.embedding))
            
            if score >= min_score:
                results.append((entry_id, score))
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:limit]
    
    def save(self, path: Path) -> None:
        """Save to disk."""
        data = {
            "dimension": self.dimension,
            "entries": {
                id: {
                    "id": e.id,
                    "content": e.content,
                    "embedding": e.embedding.tolist(),
                    "metadata": e.metadata,
                    "created_at": e.created_at.isoformat(),
                }
                for id, e in self.entries.items()
            },
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        self._dirty = False
    
    @classmethod
    def load(cls, path: Path) -> VectorStore:
        """Load from disk."""
        data = json.loads(path.read_text())
        store = cls(dimension=data["dimension"])
        store.entries = {
            id: VectorEntry(
                id=e["id"],
                content=e["content"],
                embedding=np.array(e["embedding"]),
                metadata=e.get("metadata", {}),
                created_at=datetime.fromisoformat(e["created_at"]),
            )
            for id, e in data["entries"].items()
        }
        return store


class SemanticMemory:
    """Memory with vector embeddings for semantic search.
    
    Combines:
    - Exact keyword matching
    - Semantic similarity search
    - Hybrid scoring
    """
    
    def __init__(
        self,
        project_id: str,
        project_path: Path | None = None,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        embedding_cache: Path | None = None,
    ):
        self.project_id = project_id
        self.project_path = project_path or Path.cwd()
        
        # Embedding model
        self.embedding_model = EmbeddingModel(model_name=model_name)
        
        # Vector store
        if embedding_cache is None:
            embedding_cache = (
                Path.home() / ".config" / "ai-support" / "embeddings" / project_id
            )
        self.embedding_cache = embedding_cache
        self.vector_store = self._load_store()
        
        # Keyword index (inverted index)
        self.keyword_index: dict[str, set[str]] = {}
    
    def _load_store(self) -> VectorStore:
        """Load or create vector store."""
        cache_file = self.embedding_cache / "vectors.json"
        if cache_file.exists():
            return VectorStore.load(cache_file)
        return VectorStore()
    
    def _save_store(self) -> None:
        """Save vector store."""
        self.vector_store.save(self.embedding_cache / "vectors.json")
    
    def _index_keywords(self, entry_id: str, content: str) -> None:
        """Build keyword index for fast text matching."""
        words = content.lower().split()
        for word in words:
            if len(word) < 3:  # Skip short words
                continue
            if word not in self.keyword_index:
                self.keyword_index[word] = set()
            self.keyword_index[word].add(entry_id)
    
    async def add(
        self,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a memory entry with embedding.
        
        Args:
            content: Text content
            metadata: Optional metadata
            
        Returns:
            Entry ID
        """
        # Generate embedding
        embedding = await asyncio.to_thread(
            self.embedding_model.encode, content
        )
        
        entry_id = str(uuid.uuid4())
        
        # Add to vector store
        self.vector_store.add(VectorEntry(
            id=entry_id,
            content=content,
            embedding=embedding[0] if len(embedding) == 1 else embedding,
            metadata=metadata or {},
        ))
        
        # Index keywords
        self._index_keywords(entry_id, content)
        
        # Save
        self._save_store()
        
        return entry_id
    
    async def search(
        self,
        query: str,
        limit: int = 5,
        hybrid: bool = True,
    ) -> list[dict[str, Any]]:
        """Search memories using hybrid keyword + vector search.
        
        Args:
            query: Search query
            limit: Maximum results
            hybrid: Use hybrid scoring (keyword + vector)
            
        Returns:
            List of search results with scores
        """
        # Generate query embedding
        query_embedding = await asyncio.to_thread(
            self.embedding_model.encode, query
        )
        query_embedding = query_embedding[0] if len(query_embedding) == 1 else query_embedding
        
        # Keyword matches
        keyword_ids: set[str] | None = None
        if hybrid:
            query_words = set(w for w in query.lower().split() if len(w) >= 3)
            if query_words:
                keyword_ids = set()
                for word in query_words:
                    if word in self.keyword_index:
                        keyword_ids.update(self.keyword_index[word])
        
        # Vector search
        vector_results = self.vector_store.search(
            query_embedding,
            limit=limit * 2,  # Get more for hybrid scoring
            filter_ids=keyword_ids,
        )
        
        if not hybrid:
            return [
                {
                    "id": entry_id,
                    "content": self.vector_store.entries[entry_id].content,
                    "score": score,
                    "type": "semantic",
                }
                for entry_id, score in vector_results[:limit]
            ]
        
        # Hybrid scoring
        results = []
        for entry_id, vector_score in vector_results:
            entry = self.vector_store.entries[entry_id]
            
            # Keyword overlap score
            content_words = set(w for w in entry.content.lower().split() if len(w) >= 3)
            query_words = set(w for w in query.lower().split() if len(w) >= 3)
            keyword_score = len(content_words & query_words) / max(len(query_words), 1)
            
            # Combined score (weighted average)
            combined_score = (0.7 * vector_score + 0.3 * keyword_score)
            
            results.append({
                "id": entry_id,
                "content": entry.content,
                "metadata": entry.metadata,
                "score": combined_score,
                "vector_score": vector_score,
                "keyword_score": keyword_score,
                "type": "hybrid",
            })
        
        # Sort and limit
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]


# Global singleton
_semantic_memory: SemanticMemory | None = None


def get_semantic_memory(
    project_id: str = "default",
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
) -> SemanticMemory:
    """Get or create global semantic memory instance."""
    global _semantic_memory
    if _semantic_memory is None or _semantic_memory.project_id != project_id:
        _semantic_memory = SemanticMemory(project_id, model_name=model_name)
    return _semantic_memory
