import pytest

from src.app.embedded_agent import EmbeddedCAgent


class BrokenIngestor:
    def bootstrap_rag_index(self, include_semantic=False):
        raise RuntimeError("boom")

    def should_rebuild_rag_index(self, require_page_chunks=False):
        return True


def make_agent_with_broken_ingestor() -> EmbeddedCAgent:
    agent = EmbeddedCAgent.__new__(EmbeddedCAgent)
    agent._search_cache = {}
    agent._rag_bootstrap_error = ""
    agent.retrieval_ingestor = BrokenIngestor()
    return agent


def test_initialize_rag_raises_explicit_error_when_strict():
    agent = make_agent_with_broken_ingestor()

    with pytest.raises(RuntimeError, match="RAG bootstrap failed during startup_test: boom"):
        agent._initialize_rag(reason="startup_test", strict=True)

    assert agent._rag_bootstrap_error == "startup_test: boom"


def test_ensure_rag_ready_raises_when_lazy_bootstrap_fails():
    agent = make_agent_with_broken_ingestor()

    with pytest.raises(RuntimeError, match="lazy_retrieval"):
        agent._ensure_rag_ready()

    assert agent._rag_bootstrap_error == "lazy_retrieval: boom"
