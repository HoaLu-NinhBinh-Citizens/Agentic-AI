import re
from typing import Dict, List, Optional

from src.infrastructure.models import AgentState, EvidenceBundle


class EvidenceSupport:
    def __init__(self, agent):
        self.agent = agent

    def build_document_understanding(self, task: str, evidence: EvidenceBundle) -> List[str]:
        lines: List[str] = []
        for hit in evidence.retrieved_hits[:3]:
            summary = str(hit.summary).strip()
            section = str(hit.metadata.get("section", "") if isinstance(hit.metadata, dict) else "").strip()
            if summary:
                if section:
                    lines.append(f"{hit.path} -> {section}: {summary}")
                else:
                    lines.append(f"{hit.path}: {summary}")
            preview = re.sub(r"\s+", " ", hit.text[:220]).strip()
            if preview and preview not in lines:
                lines.append(preview)
        if not lines:
            lines.append(f"No document-backed technical details were found for task: {task}")
        return lines[:6]

    def format_retrieved_context_block(self, evidence: EvidenceBundle) -> str:
        lines: List[str] = []
        for index, hit in enumerate(evidence.retrieved_hits[:3], start=1):
            section = str(hit.metadata.get("section", "") if isinstance(hit.metadata, dict) else "").strip()
            lines.append(f"{index}. source={hit.path} | section={section or 'n/a'} | score={hit.score:.1f}")
            preview = re.sub(r"\s+", " ", hit.text[:260]).strip()
            if preview:
                lines.append(f"   excerpt={preview}")
        return "\n".join(lines) if lines else "none"

    def format_memory_context_block(self, evidence: EvidenceBundle) -> str:
        return self.agent.memory.format_for_prompt(evidence.memory_hits, max_chars=1200)

    def build_evidence_bundle(
        self,
        task: str,
        state: Optional[AgentState] = None,
        local_paths: Optional[List[str]] = None,
        query_suffix: str = "",
        allow_semantic: bool = True,
    ) -> EvidenceBundle:
        self.agent._ensure_rag_ready()
        build_error = str(state.last_error) if state and state.last_error else ""
        review_feedback = state.review_feedback if state else ""
        retrieval_task = " ".join(part for part in [task, query_suffix] if part).strip()
        self.agent._log_agent_phase("think", f"Need evidence for task slice: {retrieval_task[:180]}")
        query = self.agent.query_analyzer.analyze(retrieval_task, build_error=build_error, review_feedback=review_feedback)
        self.agent._log_agent_phase("act", f"search_docs query={query.raw_query[:180]}")
        hits = self.agent.hybrid_retriever.search_docs(query, allow_semantic=allow_semantic)
        local_files: Dict[str, str] = {}
        for path in local_paths or []:
            try:
                local_files[path] = self.agent.file_tools.read_file(path)
            except (OSError, ValueError, FileNotFoundError):
                continue
        memory_hits = self.agent.memory.retrieve_relevant(task, build_error=build_error, review_feedback=review_feedback, limit=4)
        evidence = self.agent.evidence_builder.build_for_task(task, query.intent, hits, local_files, memory_hits=memory_hits)
        self.agent._log_agent_phase("observe", f"Retrieved {len(hits)} hits with confidence={evidence.confidence}")
        if state is not None:
            state.retrieval_attempts += 1
            state.last_retrieval_query = query.raw_query
            state.last_retrieval_confidence = evidence.confidence
            state.last_retrieval_hits = [
                {
                    "chunk_id": hit.chunk_id,
                    "path": hit.path,
                    "source_type": hit.source_type,
                    "score": hit.score,
                    "summary": hit.summary,
                }
                for hit in hits[:5]
            ]
            state.last_memory_hits = [dict(item) for item in memory_hits]
            state.last_memory_summary = self.agent.memory.format_for_prompt(memory_hits, max_chars=1000)
            state.last_evidence_summary = self.agent.evidence_builder.format_for_prompt(evidence, max_chars=1200)
        return evidence