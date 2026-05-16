import re
from typing import Dict, List, Optional

from src.core.config.agent_prompts import MIN_HIGH_CONFIDENCE_HITS
from src.infrastructure.models import EvidenceBundle, RetrievalHit


class EvidenceBuilder:
    """Assemble retrieval hits and local file excerpts into one prompt-ready bundle."""

    def build_for_task(
        self,
        task: str,
        intent: str,
        retrieval_hits: List[RetrievalHit],
        local_files: Optional[Dict[str, str]] = None,
        memory_hits: Optional[List[Dict]] = None,
    ) -> EvidenceBundle:
        confidence = "low"
        confidence_reason = "No evidence yet."
        if retrieval_hits:
            support_hits = [hit for hit in retrieval_hits[:3] if hit.score >= 6]
            top_score = retrieval_hits[0].score
            if top_score >= 11 and len(support_hits) >= MIN_HIGH_CONFIDENCE_HITS:
                confidence = "high"
            elif top_score >= 6:
                confidence = "medium"
            confidence_reason = f"top_score={top_score:.2f}, supporting_hits={len(support_hits)}"
        bundle = EvidenceBundle(
            task=task,
            intent=intent,
            retrieved_hits=retrieval_hits,
            memory_hits=list(memory_hits or []),
            local_files=dict(local_files or {}),
            confidence=confidence,
            confidence_reason=confidence_reason,
        )
        if not retrieval_hits:
            bundle.open_questions.append("No relevant retrieval hits found yet.")
        if bundle.memory_hits:
            bundle.assumptions.append("Relevant prior failures/successes exist and should constrain the next action.")
        if confidence == "low":
            bundle.assumptions.append("Evidence is weak; the next step should retrieve more context before coding.")
        return bundle

    def format_for_prompt(self, evidence: EvidenceBundle, max_chars: int = 4000) -> str:
        lines: List[str] = [f"confidence: {evidence.confidence}", f"confidence_reason: {evidence.confidence_reason}"]
        for item in evidence.memory_hits[:3]:
            lines.append(
                "- memory: phase={phase} outcome={outcome} error={error}".format(
                    phase=str(item.get("phase", "unknown")),
                    outcome=str(item.get("outcome", "unknown")),
                    error=str(item.get("error_signature", "none"))[:120],
                )
            )
            fix_strategy = str(item.get("fix_strategy", "")).strip()
            if fix_strategy:
                lines.append(f"  avoid_repeat: {fix_strategy[:180]}")
        for hit in evidence.retrieved_hits[:3]:
            lines.append(
                f"- source: {hit.path} ({hit.source_type}, score={hit.score:.1f}, lexical={hit.lexical_score:.1f}, vector={hit.vector_score:.2f})"
            )
            if hit.summary:
                lines.append(f"  summary: {hit.summary}")
            preview = re.sub(r"\s+", " ", hit.text[:400]).strip()
            if preview:
                lines.append(f"  excerpt: {preview}")
        for path, content in list(evidence.local_files.items())[:3]:
            preview = re.sub(r"\s+", " ", content[:240]).strip()
            lines.append(f"- local_file: {path}")
            if preview:
                lines.append(f"  excerpt: {preview}")
        if evidence.open_questions:
            lines.append("- open_questions: " + " | ".join(evidence.open_questions[:3]))
        if evidence.assumptions:
            lines.append("- assumptions: " + " | ".join(evidence.assumptions[:3]))
        text = "\n".join(lines)
        return text[:max_chars]

