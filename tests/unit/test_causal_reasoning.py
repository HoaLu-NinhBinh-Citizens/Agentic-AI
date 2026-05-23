"""Tests for causal reasoning."""

import pytest
from src.infrastructure.analysis.causal_reasoning import (
    CausalReasoner,
    CausalType,
)


class TestCausalReasoner:
    def test_reasoner_creation(self):
        reasoner = CausalReasoner()
        assert reasoner is not None

    def test_add_observation(self):
        reasoner = CausalReasoner()
        node_id = reasoner.add_observation("null_pointer_error", "error")
        assert node_id is not None

    def test_add_causal_link(self):
        reasoner = CausalReasoner()
        reasoner.add_observation("memory_leak", "error")
        reasoner.add_observation("hardfault", "error")
        reasoner.add_causal_link("memory_leak", "hardfault", CausalType.CAUSES)

    def test_explain_effect(self):
        reasoner = CausalReasoner()
        reasoner.add_observation("error1", "error")
        reasoner.add_observation("error2", "error")
        reasoner.add_causal_link("error1", "error2")
        
        explanation = reasoner.explain_effect("error2")
        assert "effect" in explanation
        assert explanation["effect"] == "error2"

    def test_suggest_fixes(self):
        from src.infrastructure.analysis.causal_reasoning import RootCause, CausalNode
        
        reasoner = CausalReasoner()
        node = CausalNode(node_id="n1", event="null_pointer", event_type="error")
        root_cause = RootCause(
            cause_id="n1",
            node=node,
            confidence=0.8,
            chain=["n1"],
        )
        
        fixes = reasoner.suggest_fixes(root_cause)
        assert len(fixes) > 0
