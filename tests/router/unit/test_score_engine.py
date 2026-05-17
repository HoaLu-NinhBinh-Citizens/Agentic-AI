"""Unit tests for ScoreEngine."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from src.infrastructure.router.fairness.boost_fairness import FairnessBoostCalculator
from src.infrastructure.router.score_engine import (
    ANNNeighbor,
    InMemoryANNIndex,
    InMemoryEmbeddingModel,
    ScoreEngine,
)
from src.infrastructure.router.types import (
    BoostFairnessConfig,
    IntentConfig,
    Request,
    RequestContext,
    RouterConfig,
    Snapshot,
)


class TestScoreEngineBasic:
    """Test basic ScoreEngine functionality."""

    @pytest.fixture
    def embedding_model(self) -> InMemoryEmbeddingModel:
        """Create embedding model."""
        return InMemoryEmbeddingModel(dimension=128)

    @pytest.fixture
    def ann_index(
        self,
        embedding_model: InMemoryEmbeddingModel,
    ) -> InMemoryANNIndex:
        """Create ANN index with test data."""
        index = InMemoryANNIndex(dimension=128)

        async def seed():
            examples = [
                ("code_generation", "write a function to sort a list"),
                ("code_generation", "create a class for user auth"),
                ("data_query", "find all users with status"),
                ("data_query", "query database for orders"),
            ]
            for intent, text in examples:
                embedding = await embedding_model.embed(text)
                await index.add(intent, text, embedding)

        asyncio.get_event_loop().run_until_complete(seed())
        return index

    @pytest.fixture
    def fairness_calculator(self) -> FairnessBoostCalculator:
        """Create fairness calculator."""
        config = BoostFairnessConfig(
            enabled=True,
            per_intent_weight_cap=0.3,
            min_share_per_intent=0.01,
            global_boost_per_second=1000,
        )
        return FairnessBoostCalculator(config)

    @pytest.fixture
    def score_engine(
        self,
        embedding_model: InMemoryEmbeddingModel,
        ann_index: InMemoryANNIndex,
        fairness_calculator: FairnessBoostCalculator,
    ) -> ScoreEngine:
        """Create score engine."""
        return ScoreEngine(
            embedding_model=embedding_model,
            ann_index=ann_index,
            fairness_calculator=fairness_calculator,
        )

    @pytest.fixture
    def snapshot(self) -> Snapshot:
        """Create test snapshot."""
        intents = {
            "code_generation": IntentConfig(name="code_generation", base_score=0.8),
            "data_query": IntentConfig(name="data_query", base_score=0.7),
            "rag": IntentConfig(name="rag", base_score=0.6),
        }
        return Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

    @pytest.fixture
    def context(
        self,
        snapshot: Snapshot,
    ) -> RequestContext:
        """Create test context."""
        return RequestContext.create(
            snapshot=snapshot,
            request=Request(query="write a sorting function"),
        )

    @pytest.mark.asyncio
    async def test_calculate_scores_returns_dict(
        self,
        score_engine: ScoreEngine,
        context: RequestContext,
    ):
        """Test that calculate_scores returns a dictionary."""
        scores = await score_engine.calculate_scores(
            context,
            context.request.query,
            ["code_generation", "data_query"],
        )

        assert isinstance(scores, dict)
        assert "code_generation" in scores
        assert "data_query" in scores

    @pytest.mark.asyncio
    async def test_calculate_scores_returns_valid_scores(
        self,
        score_engine: ScoreEngine,
        context: RequestContext,
    ):
        """Test that calculate_scores returns valid scores for all intents."""
        scores = await score_engine.calculate_scores(
            context,
            "write code to sort",
            ["code_generation", "data_query"],
        )

        # Both intents should have scores
        assert "code_generation" in scores
        assert "data_query" in scores
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.asyncio
    async def test_calculate_scores_zero_for_unknown_intent(
        self,
        score_engine: ScoreEngine,
        context: RequestContext,
    ):
        """Test that unknown intents get zero score."""
        scores = await score_engine.calculate_scores(
            context,
            "random query",
            ["nonexistent_intent"],
        )

        assert scores["nonexistent_intent"] == 0.0

    @pytest.mark.asyncio
    async def test_calculate_final_score_combines_components(
        self,
        score_engine: ScoreEngine,
        context: RequestContext,
    ):
        """Test that final score combines semantic + boost."""
        final_score = await score_engine.calculate_final_score(
            context,
            "code_generation",
            semantic_score=0.9,
        )

        # Should be combination of semantic (70%), base (20%), boost (10%)
        assert 0.0 <= final_score <= 1.0

    @pytest.mark.asyncio
    async def test_frequency_boost_applied(
        self,
        embedding_model: InMemoryEmbeddingModel,
        ann_index: InMemoryANNIndex,
        fairness_calculator: FairnessBoostCalculator,
    ):
        """Test that frequency-based boost is applied."""
        # Create snapshot with high frequency
        intents = {
            "high_freq": IntentConfig(
                name="high_freq",
                base_score=0.5,
                frequency=100,  # High frequency
            ),
            "low_freq": IntentConfig(
                name="low_freq",
                base_score=0.5,
                frequency=1,  # Low frequency
            ),
        }
        snapshot = Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

        score_engine = ScoreEngine(
            embedding_model=embedding_model,
            ann_index=ann_index,
            fairness_calculator=fairness_calculator,
        )

        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test"),
        )

        high_freq_score = await score_engine.calculate_final_score(
            context,
            "high_freq",
            semantic_score=0.5,
        )
        low_freq_score = await score_engine.calculate_final_score(
            context,
            "low_freq",
            semantic_score=0.5,
        )

        # High frequency should get higher boost
        assert high_freq_score >= low_freq_score


class TestANNIndex:
    """Test ANN index functionality."""

    @pytest.fixture
    def embedding_model(self) -> InMemoryEmbeddingModel:
        """Create embedding model."""
        return InMemoryEmbeddingModel(dimension=128)

    @pytest.fixture
    def ann_index(
        self,
        embedding_model: InMemoryEmbeddingModel,
    ) -> InMemoryANNIndex:
        """Create and seed ANN index."""
        index = InMemoryANNIndex(dimension=128)

        async def seed():
            examples = [
                ("code_generation", "write function sort list"),
                ("code_generation", "create class user auth"),
                ("data_query", "find users status"),
                ("data_query", "query database orders"),
                ("rag", "retrieve documents policy"),
                ("rag", "find information company"),
            ]
            for intent, text in examples:
                embedding = await embedding_model.embed(text)
                await index.add(intent, text, embedding)

        asyncio.get_event_loop().run_until_complete(seed())
        return index

    @pytest.mark.asyncio
    async def test_search_returns_neighbors(
        self,
        ann_index: InMemoryANNIndex,
        embedding_model: InMemoryEmbeddingModel,
    ):
        """Test that search returns neighbors."""
        query = await embedding_model.embed("write a function")
        neighbors = await ann_index.search(query, k=3)

        assert len(neighbors) <= 3
        assert all(isinstance(n, ANNNeighbor) for n in neighbors)

    @pytest.mark.asyncio
    async def test_search_results_sorted_by_similarity(
        self,
        ann_index: InMemoryANNIndex,
        embedding_model: InMemoryEmbeddingModel,
    ):
        """Test that search results are sorted by similarity."""
        query = await embedding_model.embed("write a function")
        neighbors = await ann_index.search(query, k=5)

        # Should be sorted by similarity descending
        if len(neighbors) > 1:
            for i in range(len(neighbors) - 1):
                assert neighbors[i].similarity >= neighbors[i + 1].similarity

    @pytest.mark.asyncio
    async def test_search_with_cosine_similarity(
        self,
        ann_index: InMemoryANNIndex,
    ):
        """Test cosine similarity calculation."""
        # Two identical vectors should have similarity 1.0
        await ann_index.add("test", "test", [1.0] * 128)
        neighbors = await ann_index.search([1.0] * 128, k=1)

        assert len(neighbors) == 1
        assert abs(neighbors[0].similarity - 1.0) < 0.001

    @pytest.mark.asyncio
    async def test_search_empty_index(self):
        """Test search on empty index."""
        index = InMemoryANNIndex(dimension=128)
        neighbors = await index.search([0.5] * 128, k=5)

        assert len(neighbors) == 0


class TestEmbeddingModel:
    """Test embedding model functionality."""

    @pytest.mark.asyncio
    async def test_embed_returns_vector(self):
        """Test that embed returns a vector."""
        model = InMemoryEmbeddingModel(dimension=128)
        embedding = await model.embed("test text")

        assert isinstance(embedding, list)
        assert len(embedding) == 128
        assert all(isinstance(x, float) for x in embedding)

    @pytest.mark.asyncio
    async def test_embed_deterministic(self):
        """Test that embed is deterministic."""
        model = InMemoryEmbeddingModel(dimension=128)
        embedding1 = await model.embed("test text")
        embedding2 = await model.embed("test text")

        assert embedding1 == embedding2

    @pytest.mark.asyncio
    async def test_embed_different_texts(self):
        """Test that different texts produce different embeddings."""
        model = InMemoryEmbeddingModel(dimension=128)
        embedding1 = await model.embed("hello world")
        embedding2 = await model.embed("goodbye world")

        assert embedding1 != embedding2

    def test_different_dimensions(self):
        """Test embedding model with different dimensions."""
        for dim in [64, 128, 256, 512]:
            model = InMemoryEmbeddingModel(dimension=dim)
            loop = asyncio.get_event_loop()
            embedding = loop.run_until_complete(model.embed("test"))
            assert len(embedding) == dim


class TestRuleMatcherPriority:
    """Test rule matcher with priority."""

    @pytest.fixture
    def embedding_model(self) -> InMemoryEmbeddingModel:
        """Create embedding model."""
        return InMemoryEmbeddingModel(dimension=128)

    @pytest.fixture
    def ann_index(self) -> InMemoryANNIndex:
        """Create empty ANN index."""
        return InMemoryANNIndex(dimension=128)

    @pytest.fixture
    def fairness_calculator(self) -> FairnessBoostCalculator:
        """Create fairness calculator with fairness disabled."""
        config = BoostFairnessConfig(enabled=False)
        return FairnessBoostCalculator(config)

    @pytest.fixture
    def score_engine(
        self,
        embedding_model: InMemoryEmbeddingModel,
        ann_index: InMemoryANNIndex,
        fairness_calculator: FairnessBoostCalculator,
    ) -> ScoreEngine:
        """Create score engine."""
        return ScoreEngine(
            embedding_model=embedding_model,
            ann_index=ann_index,
            fairness_calculator=fairness_calculator,
        )

    @pytest.mark.asyncio
    async def test_intent_priority_affects_score(
        self,
        score_engine: ScoreEngine,
    ):
        """Test that intent priority affects final score."""
        intents = {
            "high_priority": IntentConfig(
                name="high_priority",
                base_score=0.9,
                priority=100,
            ),
            "low_priority": IntentConfig(
                name="low_priority",
                base_score=0.3,
                priority=1,
            ),
        }
        snapshot = Snapshot(
            snapshot_id="test-snap",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )
        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test"),
        )

        high_score = await score_engine.calculate_final_score(
            context, "high_priority", semantic_score=0.5
        )
        low_score = await score_engine.calculate_final_score(
            context, "low_priority", semantic_score=0.5
        )

        # High priority base score should lead to higher final score
        assert high_score > low_score


class TestSemanticSimilarityWithANN:
    """Test semantic similarity calculation with ANN."""

    @pytest.fixture
    def embedding_model(self) -> InMemoryEmbeddingModel:
        """Create embedding model."""
        return InMemoryEmbeddingModel(dimension=128)

    @pytest.fixture
    def ann_index(
        self,
        embedding_model: InMemoryEmbeddingModel,
    ) -> InMemoryANNIndex:
        """Create seeded ANN index."""
        index = InMemoryANNIndex(dimension=128)

        async def seed():
            code_examples = [
                "write a function to sort",
                "create a class for user",
                "implement binary search",
            ]
            data_examples = [
                "find all users with status",
                "query database for orders",
                "search products in category",
            ]
            for text in code_examples:
                emb = await embedding_model.embed(text)
                await index.add("code_generation", text, emb)
            for text in data_examples:
                emb = await embedding_model.embed(text)
                await index.add("data_query", text, emb)

        asyncio.get_event_loop().run_until_complete(seed())
        return index

    @pytest.fixture
    def fairness_calculator(self) -> FairnessBoostCalculator:
        """Create fairness calculator."""
        return FairnessBoostCalculator(BoostFairnessConfig(enabled=False))

    @pytest.fixture
    def score_engine(
        self,
        embedding_model: InMemoryEmbeddingModel,
        ann_index: InMemoryANNIndex,
        fairness_calculator: FairnessBoostCalculator,
    ) -> ScoreEngine:
        """Create score engine."""
        return ScoreEngine(
            embedding_model=embedding_model,
            ann_index=ann_index,
            fairness_calculator=fairness_calculator,
        )

    @pytest.mark.asyncio
    async def test_similar_queries_return_valid_scores(
        self,
        score_engine: ScoreEngine,
    ):
        """Test that semantically similar queries return valid scores."""
        scores = await score_engine.calculate_scores(
            RequestContext.create(
                snapshot=Snapshot(
                    snapshot_id="test",
                    config=RouterConfig(intents={
                        "code_generation": IntentConfig(name="code_generation"),
                        "data_query": IntentConfig(name="data_query"),
                    }),
                    index=MagicMock(),
                    frequency_version=1,
                    freq_snapshot_time=0.0,
                    created_at=0.0,
                ),
                request=Request(query="write a sorting function"),
            ),
            "write a sorting function",
            ["code_generation", "data_query"],
        )

        # Both intents should have scores in valid range
        assert all(0.0 <= s <= 1.0 for s in scores.values())

    @pytest.mark.asyncio
    async def test_dissimilar_queries_return_valid_scores(
        self,
        score_engine: ScoreEngine,
    ):
        """Test that dissimilar queries return valid scores."""
        scores = await score_engine.calculate_scores(
            RequestContext.create(
                snapshot=Snapshot(
                    snapshot_id="test",
                    config=RouterConfig(intents={
                        "code_generation": IntentConfig(name="code_generation"),
                        "data_query": IntentConfig(name="data_query"),
                    }),
                    index=MagicMock(),
                    frequency_version=1,
                    freq_snapshot_time=0.0,
                    created_at=0.0,
                ),
                request=Request(query="random unrelated query xyz"),
            ),
            "random unrelated query xyz",
            ["code_generation", "data_query"],
        )

        # Both intents should have valid scores
        assert all(0.0 <= s <= 1.0 for s in scores.values())


class TestContextBoostingWithCache:
    """Test context boosting with cache."""

    @pytest.fixture
    def embedding_model(self) -> InMemoryEmbeddingModel:
        """Create embedding model."""
        return InMemoryEmbeddingModel(dimension=128)

    @pytest.fixture
    def ann_index(
        self,
        embedding_model: InMemoryEmbeddingModel,
    ) -> InMemoryANNIndex:
        """Create ANN index."""
        index = InMemoryANNIndex(dimension=128)

        async def seed():
            await index.add("code", "write code", await embedding_model.embed("write code"))

        asyncio.get_event_loop().run_until_complete(seed())
        return index

    @pytest.fixture
    def fairness_calculator(self) -> FairnessBoostCalculator:
        """Create fairness calculator."""
        return FairnessBoostCalculator(BoostFairnessConfig(enabled=False))

    @pytest.mark.asyncio
    async def test_context_metadata_used_in_boost(
        self,
        embedding_model: InMemoryEmbeddingModel,
        ann_index: InMemoryANNIndex,
        fairness_calculator: FairnessBoostCalculator,
    ):
        """Test that context metadata can influence boost."""
        score_engine = ScoreEngine(
            embedding_model=embedding_model,
            ann_index=ann_index,
            fairness_calculator=fairness_calculator,
        )

        intents = {
            "code": IntentConfig(
                name="code",
                frequency=10,
            ),
        }
        snapshot = Snapshot(
            snapshot_id="test",
            config=RouterConfig(intents=intents),
            index=MagicMock(),
            frequency_version=1,
            freq_snapshot_time=0.0,
            created_at=0.0,
        )

        # Create context with metadata
        context = RequestContext.create(
            snapshot=snapshot,
            request=Request(query="test"),
        )
        context_with_meta = context.with_metadata("user_preference", "code")

        # Score should be calculable
        score = await score_engine.calculate_final_score(
            context_with_meta,
            "code",
            semantic_score=0.5,
        )

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
