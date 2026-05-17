from .chunk_store import ChunkStore
from .embedding import OllamaEmbeddingClient
from .evidence_builder import EvidenceBuilder
from .hybrid import HybridRetriever
from .ingest import RetrievalIngestor
from .knowledge_base import ReferenceKnowledgeBase
from .manifest import IndexManifest, compute_file_hash, compute_content_hash
from .page_aware import PageAwareRetrievalSupport
from .query_analyzer import QueryAnalyzer
from .search_cache import SearchCache, get_search_cache, clear_search_cache
from .vector_index import VectorIndex
from .chroma_store import ChromaVectorStore, create_vector_store
from .rag_evaluation import RetrievalEvaluator, RetrievalMetrics, EvaluationCase

# Retrieval Engine Core (Phase 5C v12)
from .retrieval_types import (
    RetrievalSnapshot,
    Transaction,
    PluginVersion,
    PluginVersionHistory,
    PluginVersionStatus,
    QueryTypeBudget,
    GoldenQuery,
    GoldenSet,
    GoldenSetMetrics,
    DriftAlert,
    DocumentCacheMapping,
    CacheInvalidation,
    ProvenanceEntry,
    RetrievalExplanation,
    ReplicaMetrics,
    ReplicaStatus,
    QueryIntent,
    AdvancedRetrievalRequest,
    AdvancedRetrievalResponse,
)
from .retrieval_config import (
    ReadIsolationConfig,
    ReplicaLagConfig,
    PluginManagementConfig,
    QueryBudgetConfig,
    GoldenSetConfig,
    CacheConfig,
    ExplainabilityConfig,
    Phase5CConfig,
    DEFAULT_PHASE5C_CONFIG,
    PHASE5C_YAML_TEMPLATE,
)
from .retrieval_components import (
    SnapshotIsolationRead,
    ReplicaLagAwareRouter,
    PluginVersionManager,
    QueryTypeBudgeter,
    GoldenSetDriftDetector,
    DocumentBasedCacheInvalidator,
    ExplainabilitySizeLimiter,
)
from .retrieval_engine import AdvancedRetrievalEngine

# Retrieval Engine Resilience (Production Features)
from .retrieval_resilience import (
    SnapshotReferenceCounter,
    SnapshotGCManager,
    VectorConsistencyStrategy,
    VectorSegment,
    VectorSnapshotConsistencyManager,
    GenerationCacheInvalidator,
    DistributionShiftDetector,
    LoadSheddingPolicy,
    AdmissionDecision,
    RetrievalAdmissionController,
    RecoveryStrategy,
    FailureScope,
    RecoveryPlan,
    CatastrophicRecoveryManager,
    PluginStateSnapshot,
    PluginCompatibility,
    PluginStateMigrationManager,
    LSNBasedLagMetrics,
)

__all__ = [
	"ChunkStore",
	"EvidenceBuilder",
	"HybridRetriever",
	"RetrievalIngestor",
	"OllamaEmbeddingClient",
	"PageAwareRetrievalSupport",
	"QueryAnalyzer",
	"ReferenceKnowledgeBase",
	"VectorIndex",
	"ChromaVectorStore",
	"create_vector_store",
	"RetrievalEvaluator",
	"RetrievalMetrics",
	"EvaluationCase",
	"IndexManifest",
	"compute_file_hash",
	"compute_content_hash",
	"SearchCache",
	"get_search_cache",
	"clear_search_cache",
    # Retrieval Types
    "RetrievalSnapshot",
    "Transaction",
    "PluginVersion",
    "PluginVersionHistory",
    "PluginVersionStatus",
    "QueryTypeBudget",
    "GoldenQuery",
    "GoldenSet",
    "GoldenSetMetrics",
    "DriftAlert",
    "DocumentCacheMapping",
    "CacheInvalidation",
    "ProvenanceEntry",
    "RetrievalExplanation",
    "ReplicaMetrics",
    "ReplicaStatus",
    "QueryIntent",
    "AdvancedRetrievalRequest",
    "AdvancedRetrievalResponse",
    # Retrieval Config
    "ReadIsolationConfig",
    "ReplicaLagConfig",
    "PluginManagementConfig",
    "QueryBudgetConfig",
    "GoldenSetConfig",
    "CacheConfig",
    "ExplainabilityConfig",
    "Phase5CConfig",
    "DEFAULT_PHASE5C_CONFIG",
    "PHASE5C_YAML_TEMPLATE",
    # Retrieval Components
    "SnapshotIsolationRead",
    "ReplicaLagAwareRouter",
    "PluginVersionManager",
    "QueryTypeBudgeter",
    "GoldenSetDriftDetector",
    "DocumentBasedCacheInvalidator",
    "ExplainabilitySizeLimiter",
    # Retrieval Engine
    "AdvancedRetrievalEngine",
    # Retrieval Resilience
    "SnapshotReferenceCounter",
    "SnapshotGCManager",
    "VectorConsistencyStrategy",
    "VectorSegment",
    "VectorSnapshotConsistencyManager",
    "GenerationCacheInvalidator",
    "DistributionShiftDetector",
    "LoadSheddingPolicy",
    "AdmissionDecision",
    "RetrievalAdmissionController",
    "RecoveryStrategy",
    "FailureScope",
    "RecoveryPlan",
    "CatastrophicRecoveryManager",
    "PluginStateSnapshot",
    "PluginCompatibility",
    "PluginStateMigrationManager",
    "LSNBasedLagMetrics",
]
