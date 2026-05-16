import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from src.core.config.agent_prompts import AGENT_TRACE_ROOT, GENERIC_QUERY_STOPWORDS, OUTPUT_GENERATED_ROOT
from src.infrastructure.models import AgentState, ExperienceEntry, TaskResult

logger = logging.getLogger(__name__)


class ExperienceSupport:
    def __init__(self, agent):
        self.agent = agent

    def record_experience(self, state: AgentState, result: TaskResult):
        last_error = ""
        if state.retrieval_blocker:
            last_error = state.retrieval_blocker[:300]
        elif state.last_error:
            last_error = str(state.last_error)
        elif state.last_runtime_diagnosis and state.last_runtime_diagnosis.summary:
            last_error = state.last_runtime_diagnosis.summary[:300]
        elif state.last_runtime_result and state.last_runtime_result.stderr:
            last_error = state.last_runtime_result.stderr[:300]
        elif state.last_flash_result and state.last_flash_result.stderr:
            last_error = state.last_flash_result.stderr[:300]
        elif state.last_build_result and state.last_build_result.stderr:
            last_error = state.last_build_result.stderr[:300]
        elif not result.success:
            last_error = result.message

        entry = ExperienceEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            task=state.task,
            success=result.success,
            attempts=result.attempts,
            files_created=result.files_created,
            last_error=last_error,
            response_preview=state.response_preview,
            lessons=[],
            memory_records=self.build_memory_records(state, result, last_error),
        )
        self.agent.memory.record(entry)
        self.persist_decision_trace(state, result, last_error, entry.memory_records)

    def persist_decision_trace(self, state: AgentState, result: TaskResult, last_error: str, memory_records: List[Dict]):
        slug = self.make_task_slug(state.task)
        trace_relpath = f"{AGENT_TRACE_ROOT}/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}.json"
        payload = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "task": state.task,
            "success": result.success,
            "message": result.message,
            "attempts": result.attempts,
            "duration": result.duration,
            "stop_reason": state.stop_reason,
            "last_error": last_error,
            "last_retrieval_confidence": state.last_retrieval_confidence,
            "last_retrieval_query": state.last_retrieval_query,
            "last_memory_summary": state.last_memory_summary,
            "iteration_history": list(state.iteration_history),
            "generated_files": list(state.generated_files.keys()),
            "memory_records": list(memory_records),
        }
        try:
            self.agent.file_tools.write_file(trace_relpath, json.dumps(payload, indent=2))
        except OSError as exc:
            logger.warning("Failed to persist decision trace: %s", exc)

    def make_task_slug(self, task: str) -> str:
        parts = re.findall(r"[a-z0-9]+", task.lower())[:8]
        return "_".join(parts) or "task"

    def build_memory_records(self, state: AgentState, result: TaskResult, last_error: str) -> List[Dict]:
        outcome = "success" if result.success else "failure"
        root_cause = self.summarize_root_cause(state, last_error)
        fix_strategy = self.summarize_fix_strategy(state, result)
        context_terms = self.collect_memory_context_terms(state)
        evidence_paths = [
            str(item.get("path", "")).strip()
            for item in state.last_retrieval_hits
            if str(item.get("path", "")).strip()
        ]
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "task": state.task,
            "iteration": state.attempt,
            "phase": state.last_action or state.response_stage or "execute",
            "outcome": outcome,
            "error_signature": self.agent._build_failure_signature(state) or self.agent._normalize_failure_signature(last_error),
            "root_cause": root_cause,
            "fix_strategy": fix_strategy,
            "context_terms": context_terms,
            "prevention_rules": self.derive_proposal_rules(state, result, last_error)[:4],
            "evidence_paths": evidence_paths[:4],
        }
        if not any(str(value).strip() for value in [record["error_signature"], record["root_cause"], record["fix_strategy"]]):
            return []
        return [record]

    def derive_proposal_rules(self, state: AgentState, result: TaskResult, last_error: str) -> List[str]:
        """Create proposal-only operational rules without copying reviewer/output facts."""
        rules: List[str] = []
        files_created = result.files_created if result else list(state.generated_files.keys())
        if files_created and self.agent._is_output_only_generation(files_created):
            rules.append(f"Keep generated artifacts constrained to the configured generated-output directory.")
        if state.retrieval_blocker or state.retrieval_block_streak:
            rules.append("When retrieval validation is weak, stop code generation and request stronger evidence.")
        if "No valid FILE blocks found" in str(last_error):
            rules.append("When structured output parsing fails, retry with an explicit schema contract before downstream validation.")
        if "flash failed" in str(last_error).lower() or "runtime observe failed" in str(last_error).lower():
            rules.append("When hardware observation tools fail, preserve the trace and require explicit hardware/tool confirmation.")
        if state.review_feedback:
            rules.append("When reviewer validation fails, record a fix proposal instead of learning reviewer text as policy.")
        if not result.success and not rules:
            rules.append("On failure, preserve response preview and error summary for a pending learning proposal.")
        return rules

    def summarize_root_cause(self, state: AgentState, last_error: str) -> str:
        for candidate in [
            state.review_feedback,
            state.retrieval_blocker,
            str(state.last_error) if state.last_error else "",
            last_error,
            state.response_preview,
        ]:
            text = str(candidate).strip()
            if text:
                return text[:300]
        return ""

    def summarize_fix_strategy(self, state: AgentState, result: TaskResult) -> str:
        if result.success and state.last_action == "generate":
            return "Reuse the current evidence-guided generation pattern and keep output constrained to allowed files."
        if state.last_action == "retrieve_more":
            return "Rewrite the retrieval query with the failing slice, then regenerate only after confidence improves."
        if state.last_action == "fix" and state.fixes_applied:
            return f"Apply a focused fix around: {state.fixes_applied[-1][:220]}"
        if state.review_feedback:
            return f"Regenerate while explicitly addressing reviewer finding: {state.review_feedback[:220]}"
        if state.retrieval_blocker:
            return "Do not continue coding; gather stronger document evidence first."
        return state.last_action_reason[:240]

    def collect_memory_context_terms(self, state: AgentState) -> List[str]:
        text = " ".join([
            state.task,
            state.review_feedback,
            state.retrieval_blocker,
            str(state.last_error) if state.last_error else "",
            " ".join(str(item.get("path", "")) for item in state.last_retrieval_hits),
        ])
        terms: List[str] = []
        seen = set()
        for token in re.findall(r"[a-z0-9_]+", text.lower()):
            if len(token) < 3 or token in GENERIC_QUERY_STOPWORDS or token in seen:
                continue
            seen.add(token)
            terms.append(token)
        return terms[:24]

    def derive_lessons(self, state: AgentState, result: Optional[TaskResult], last_error: str) -> List[str]:
        lessons: List[str] = []
        files_created = result.files_created if result else list(state.generated_files.keys())
        success = result.success if result else bool(files_created)

        if files_created and self.agent._is_output_only_generation(files_created):
            lessons.append(f"Write new artifacts only under {OUTPUT_GENERATED_ROOT}.")
        if any(path.endswith(".h") for path in files_created) and any(path.endswith(".c") for path in files_created):
            lessons.append("Prefer paired header and source outputs for driver generation tasks.")

        if state.response_preview:
            if "**" in state.response_preview:
                lessons.append("Model may emit bold file paths before code blocks; keep parser tolerant of markdown path formatting.")
            if "Here is the complete C code" in state.response_preview:
                lessons.append("Model may prepend explanatory prose before file blocks; prompts should emphasize code-first output.")
            if state.response_stage:
                lessons.append(f"Last captured LLM output stage: {state.response_stage}.")

        if "No valid FILE blocks found" in last_error:
            lessons.append("When parsing model output, accept FILE markers plus markdown-styled file paths.")
        if "cannot find the path specified" in last_error.lower():
            lessons.append("Do not rely on full project build success for review-only generated output.")
        if "flash failed" in last_error.lower() or "j-link" in last_error.lower():
            lessons.append("When flashing hardware, require an explicit target project and expect J-Link connectivity issues.")
        if "runtime observe failed" in last_error.lower() or "rtt" in last_error.lower():
            lessons.append("Runtime observation may need dry-run mode unless hardware and debugger are explicitly available.")

        if state.last_runtime_diagnosis:
            if state.last_runtime_diagnosis.findings:
                lessons.append(f"Runtime signals seen: {', '.join(state.last_runtime_diagnosis.findings[:3])}.")
            if state.last_runtime_diagnosis.warnings:
                lessons.append(f"Runtime warnings to address: {', '.join(state.last_runtime_diagnosis.warnings[:2])}.")

        if state.review_feedback:
            lessons.append(f"Reviewer focus: {state.review_feedback}")
        if state.review_preview:
            lessons.append("Persist reviewer response previews when JSON review parsing fails.")
        if state.last_retrieval_confidence:
            lessons.append(f"Last retrieval confidence: {state.last_retrieval_confidence}.")
        if state.retrieval_block_streak:
            lessons.append(f"Retrieval gate block streak reached {state.retrieval_block_streak}; widen the next query strategy instead of repeating the same query.")
        if state.retrieval_blocker:
            lessons.append(f"Do not code or auto-fix when retrieval is weak: {state.retrieval_blocker}")
        elif state.last_evidence_summary:
            lessons.append("Use retrieved evidence summary before codegen/fix instead of relying only on reviewer text.")
        if state.last_retrieval_query:
            lessons.append(f"Last retrieval query used: {state.last_retrieval_query[:140]}")
        if state.last_retrieval_hits:
            top_paths = [str(item.get("path", "")).strip() for item in state.last_retrieval_hits if str(item.get("path", "")).strip()]
            if top_paths:
                lessons.append("Recent evidence sources: " + ", ".join(top_paths[:3]))

        if not success and not lessons:
            lessons.append("On failure, preserve response preview and error summary for the next prompt.")
        return lessons[:6]
