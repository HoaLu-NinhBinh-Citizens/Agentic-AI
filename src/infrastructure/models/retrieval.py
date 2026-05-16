from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ChunkRecord:
    """Normalized retrievable chunk stored in the local RAG index."""

    chunk_id: str
    doc_id: str
    path: str
    source_type: str
    text: str
    summary: str = ""
    section: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class RetrievalHit:
    """A ranked retrieval result returned to the agent loop."""

    chunk_id: str
    path: str
    source_type: str
    score: float
    text: str
    summary: str = ""
    lexical_score: float = 0.0
    vector_score: float = 0.0
    rerank_score: float = 0.0
    score_breakdown: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


@dataclass
class RetrievalQuery:
    """Parsed retrieval request used by the hybrid retriever."""

    raw_query: str
    normalized_query: str
    intent: str
    domain_profile: str = "generic_document"
    entities: Dict[str, List[str]] = field(default_factory=dict)
    filters: Dict[str, str] = field(default_factory=dict)
    top_k: int = 5


@dataclass
class EvidenceBundle:
    """Compact evidence package carried into prompts."""

    task: str
    intent: str
    retrieved_hits: List[RetrievalHit] = field(default_factory=list)
    memory_hits: List[Dict] = field(default_factory=list)
    local_files: Dict[str, str] = field(default_factory=dict)
    assumptions: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    confidence: str = "low"
    confidence_reason: str = ""
