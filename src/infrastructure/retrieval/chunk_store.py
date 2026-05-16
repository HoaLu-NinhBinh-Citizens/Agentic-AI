import json
from typing import Dict, List

from src.core.config.agent_prompts import RAG_CHUNKS_FILE
from src.infrastructure.models import ChunkRecord
from src.core.tools import FileTools


class ChunkStore:
    """Minimal local store for retrieval chunks persisted under AI_support/rag_index."""

    def __init__(self, file_tools: FileTools):
        self.file_tools = file_tools
        self._chunks: List[ChunkRecord] = []
        self._loaded = False

    def load(self) -> List[ChunkRecord]:
        if self._loaded:
            return self._chunks
        try:
            raw = json.loads(self.file_tools.read_file(RAG_CHUNKS_FILE))
        except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
            raw = []
        self._chunks = [self._to_chunk_record(item) for item in raw if isinstance(item, dict)]
        self._loaded = True
        return self._chunks

    def save(self):
        payload = [self._chunk_to_dict(chunk) for chunk in self._chunks]
        self.file_tools.write_file(RAG_CHUNKS_FILE, json.dumps(payload, indent=2))

    def get_all(self) -> List[ChunkRecord]:
        return list(self.load())

    def replace_all(self, chunks: List[ChunkRecord]):
        self._chunks = list(chunks)
        self._loaded = True
        self.save()

    def is_empty(self) -> bool:
        return not self.load()

    def _to_chunk_record(self, data: Dict) -> ChunkRecord:
        return ChunkRecord(
            chunk_id=str(data.get("chunk_id", "")).strip(),
            doc_id=str(data.get("doc_id", "")).strip(),
            path=str(data.get("path", "")).strip(),
            source_type=str(data.get("source_type", "")).strip() or "pdf",
            text=str(data.get("text", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            section=str(data.get("section", "")).strip(),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata", {}), dict) else {},
        )

    def _chunk_to_dict(self, chunk: ChunkRecord) -> Dict:
        return {
            "chunk_id": chunk.chunk_id,
            "doc_id": chunk.doc_id,
            "path": chunk.path,
            "source_type": chunk.source_type,
            "text": chunk.text,
            "summary": chunk.summary,
            "section": chunk.section,
            "metadata": chunk.metadata,
        }