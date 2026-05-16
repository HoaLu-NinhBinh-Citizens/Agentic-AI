#!/usr/bin/env python3
"""
Embedded C Development AI Agent

A local, offline AI agent for embedded C firmware development.
Features:
- Generates C code from natural language
- Fixes compilation errors automatically
- Analyzes build logs
- Refactors existing code
- Runs entirely with local Ollama (no API keys)
"""

import asyncio
import subprocess
import re
import sys
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Callable, Iterable, List, Dict, Optional, Tuple, cast
import requests
import json
import logging
import time

from src.core.agent import AgentCore, AgentExecutor, AgentPlanner
from src.application.services.agent_services import AgentSupportService
from src.application.api.app.component_factory import AgentComponentFactory, AgentComponents
from src.application.services.document_workers import DocumentWorkerSupport
from src.application.services.evidence_support import EvidenceSupport
from src.application.services.experience_support import ExperienceSupport
from src.core.config.agent_prompts import (
    AGENT_MEMORY_FILE,
    AI_SUPPORT_ROOT,
    CHAPTER_CACHE_MAX_AGE_HOURS,
    CHAPTER_NOTE_RETRY_LIMIT,
    DOC_QUESTION_SET_FILE,
    LOCAL_AGENT_RAG_BEHAVIOR_PROMPT,
    METADATA_ONLY_EXTENSIONS,
    MIN_HIGH_CONFIDENCE_HITS,
    OUTPUT_GENERATED_ROOT,
    OUTPUT_GENERATED_INC,
    OUTPUT_GENERATED_SRC,
    PDF_SEMANTIC_CHUNK_LIMIT,
    PDF_SEMANTIC_PAGE_LIMIT,
    RAG_CHUNKS_FILE,
    RAG_REGISTER_SCHEMA_FILE,
    RAG_SCHEMA_VERSION,
    RAG_VECTOR_DATA_FILE,
    RAG_VECTOR_META_FILE,
    REFERENCE_KB_CANDIDATES,
    RM_NOTES_ROOT,
    SEARCH_CACHE_MAX_ENTRIES,
    SEARCH_CACHE_TTL_SECONDS,
    SPEC_WARNING_THRESHOLD,
    TEXT_CHUNK_OVERLAP_RATIO,
    TEXT_PREVIEW_EXTENSIONS,
    TEXT_SECTION_CHUNK_CHARS,
    TEXT_SECTION_CHUNK_LIMIT,
    VECTOR_BUILD_BATCH_SIZE,
    VECTOR_EMBED_MODEL,
    VECTOR_RERANK_CANDIDATES,
    VENDOR_FILE_PATTERNS,
    VENDOR_PATH_PARTS,
    WINDOWS_INVALID_FILENAME_CHARS,
    WORKSPACE_DOC_ROOTS,
)
from src.infrastructure.llm import OllamaLLM
from src.infrastructure.llm.openai_llm import OpenAILLM, ModelRouter
from src.core.agent.plan_mode_agent import PlanModeAgent
from src.core.memory import AgentMemory
from src.infrastructure.models import (
    ActionObservation,
    AgentState,
    BenchmarkCase,
    BenchmarkResult,
    BuildError,
    BuildResult,
    ChapterNote,
    ChunkRecord,
    EvidenceBundle,
    RetrievalHit,
    RetrievalQuery,
    RuntimeDiagnosis,
    TaskPlan,
    TaskResult,
    ToolResult,
)
from src.benchmarking import BenchmarkSuite
from src.core.parsing import OutputSanitizer, ResponseParser
from src.reporting import ReportWriter, TraceReporter
from src.application.services.review_support import ReviewSupport
from src.application.services.runtime_support import RuntimeSupport
from src.infrastructure.retrieval import (
    ChunkStore,
    EvidenceBuilder,
    HybridRetriever,
    OllamaEmbeddingClient,
    PageAwareRetrievalSupport,
    QueryAnalyzer,
    ReferenceKnowledgeBase,
    RetrievalIngestor,
    VectorIndex,
)
from src.core.tools import BuildTools, FileTools
from src.application.api.app.config import LLM_STAGE_TIMEOUTS
from src.application.api.app.search_cache import SearchCache
from src.application.api.app.migrator import LegacyMigrator

logger = logging.getLogger(__name__)

# ============================================================================
# AI AGENT
# ============================================================================

class EmbeddedCAgent:
    """Main AI agent for embedded C development"""

    llm: OllamaLLM
    openai_llm: OpenAILLM
    model_router: ModelRouter
    plan_mode_agent: PlanModeAgent
    embedding_client: OllamaEmbeddingClient
    build_tools: BuildTools
    file_tools: FileTools
    memory: AgentMemory
    reference_kb: ReferenceKnowledgeBase
    chunk_store: ChunkStore
    vector_index: VectorIndex
    query_analyzer: QueryAnalyzer
    hybrid_retriever: HybridRetriever
    evidence_builder: EvidenceBuilder
    response_parser: ResponseParser
    output_sanitizer: OutputSanitizer
    evidence_support: EvidenceSupport
    retrieval_support: PageAwareRetrievalSupport
    review_support: ReviewSupport
    runtime_support: RuntimeSupport
    experience_support: ExperienceSupport
    document_workers: DocumentWorkerSupport
    agent_planner: AgentPlanner
    agent_core: AgentCore
    agent_executor: AgentExecutor
    benchmark_suite: BenchmarkSuite
    report_writer: ReportWriter
    trace_reporter: TraceReporter
    agent_services: AgentSupportService
    retrieval_ingestor: RetrievalIngestor
    search_cache: SearchCache
    
    def __init__(
        self,
        project_root: str = ".",
        model: str = "llama3.1",
        bootstrap_rag: bool = True,
        bootstrap_semantic_rag: bool = False,
        strict_rag_bootstrap: bool = False,
    ):
        self.project_root = str(Path(project_root).resolve())
        components: AgentComponents = AgentComponentFactory.create(self, self.project_root, model)
        for name, value in vars(components).items():
            setattr(self, name, value)
        self.search_cache = SearchCache()
        self._rag_bootstrap_error = ""
        self._migrate_legacy_ai_support()
        if bootstrap_rag:
            self._initialize_rag(include_semantic=bootstrap_semantic_rag, reason="startup", strict=strict_rag_bootstrap)

    def _bootstrap_rag_index(self, include_semantic: bool = False):
        """Seed the first local retrieval index from the prebuilt PDF knowledge base."""
        try:
            self.retrieval_ingestor.bootstrap_rag_index(include_semantic=include_semantic)
        except TypeError as exc:
            if "include_semantic" not in str(exc):
                raise
            self.retrieval_ingestor.bootstrap_rag_index()
        self.search_cache.clear()
        self._rag_bootstrap_error = ""

    def _initialize_rag(self, include_semantic: bool = False, reason: str = "startup", strict: bool = False):
        try:
            try:
                self._bootstrap_rag_index(include_semantic=include_semantic)
            except TypeError as exc:
                if "include_semantic" not in str(exc):
                    raise
                self._bootstrap_rag_index()
        except Exception as exc:
            self._rag_bootstrap_error = f"{reason}: {exc}"
            logger.exception("RAG bootstrap failed during %s", reason)
            if strict:
                raise RuntimeError(f"RAG bootstrap failed during {reason}: {exc}") from exc

    def _migrate_legacy_ai_support(self):
        LegacyMigrator(self.build_tools.build_root, self.memory).migrate()

    def _log_agent_phase(self, phase: str, message: str):
        """Emit explicit runtime logs for the think/act/observe loop."""
        logger.info("[%s] %s", phase.upper(), message)

    def _get_llm_stage_timeout(self, stage: str, prompt: str = "") -> int:
        prompt_chars = len(str(prompt))
        base_timeout = int(LLM_STAGE_TIMEOUTS.get(stage, 120))
        timeout_seconds = base_timeout + int(prompt_chars / 100)
        return min(timeout_seconds, 300)

    async def _guarded_llm_generate(self, prompt: str, stage: str, state: Optional[AgentState] = None) -> str:
        timeout_seconds = self._get_llm_stage_timeout(stage, prompt)
        if hasattr(self.llm, "read_timeout_seconds"):
            self.llm.read_timeout_seconds = max(int(getattr(self.llm, "read_timeout_seconds", 0)), timeout_seconds)

        # Apply token truncation to prevent context overflow
        try:
            from src.infrastructure.llm.token_tracker import get_token_counter
            counter = get_token_counter()
            prompt, original = counter.truncate_for_context(prompt, self.llm.model)
            if original > counter.get_context_window(self.llm.model):
                logger.info(
                    "TokenTracker: Truncated prompt from ~%d to ~%d tokens",
                    counter.count(prompt) if hasattr(counter, 'count') else original,
                    counter.count(prompt) if hasattr(counter, 'count') else original,
                )
        except Exception:
            pass  # Non-critical - proceed without truncation

        try:
            return await asyncio.wait_for(self.llm.generate(prompt), timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            message = f"{stage} timed out after {timeout_seconds}s"
            logger.error(message)
            if state is not None:
                state.response_stage = f"{stage}_timeout"
                state.response_preview = message
            raise TimeoutError(message) from exc
        except Exception as exc:
            failure_signature = self._classify_failure_signature(str(exc))
            if state is not None:
                if self._is_backend_failure_signature(failure_signature):
                    state.response_stage = f"{stage}_backend_failure"
                    state.response_preview = failure_signature
                elif not state.response_preview:
                    state.response_stage = f"{stage}_failure"
                    state.response_preview = str(exc)[:300]
            raise
    
    async def execute_task(self, task: str) -> TaskResult:
        """Execute a development task"""
        return await self.agent_core.execute_task(task)

    def record_feedback(self, rating: str, note: str = ""):
        """Persist explicit user feedback for future prompts."""
        self.agent_services.record_feedback(rating, note=note)

    def run_benchmarks(self, include_llm: bool = False) -> List[BenchmarkResult]:
        """Run a deterministic benchmark suite to track retrieval and runtime guard quality."""
        return self.agent_services.run_benchmarks(include_llm=include_llm)

    def run_smoke_tests(self) -> List[BenchmarkResult]:
        """Run only fast local checks for developer feedback."""
        return self.agent_services.run_smoke_tests()

    def _load_document_question_cases(self) -> List[BenchmarkCase]:
        return self.agent_services.load_document_question_cases()

    def write_task_learning_report(self, report_path: Path, task: str, limit: int = 5) -> Dict:
        """Persist one task-centric replay and memory report for later inspection."""
        return self.agent_services.write_task_learning_report(report_path, task, limit=limit)

    def index_rm_schema(self, pdf_path: Path, chip: str = "", max_pages: int = 0, progress=None) -> Dict:
        """Build the authoritative register schema from a reference-manual PDF."""
        return self.agent_services.index_rm_schema(pdf_path, chip=chip, max_pages=max_pages, progress=progress)

    def validate_register_schema(self) -> Dict:
        """Validate the cached authoritative register schema."""
        return self.agent_services.validate_register_schema()

    def synthesize_policy(self, limit: int = 20) -> Dict:
        """Write a durable coding policy from src.core.memory scores and learned rules."""
        return self.agent_services.synthesize_policy(limit=limit)

    def _benchmark_insufficient_documentation_guard(self) -> BenchmarkResult:
        return self.agent_services.benchmark_insufficient_documentation_guard()

    def _benchmark_parser_prose_recovery(self) -> BenchmarkResult:
        return self.agent_services.benchmark_parser_prose_recovery()

    def _benchmark_semantic_chunk_coverage(self) -> BenchmarkResult:
        return self.agent_services.benchmark_semantic_chunk_coverage()

    def _benchmark_generated_output_quality(self) -> BenchmarkResult:
        return self.agent_services.benchmark_generated_output_quality()

    def _benchmark_vendor_index_exclusion(self) -> BenchmarkResult:
        return self.agent_services.benchmark_vendor_index_exclusion()

    def _benchmark_memory_retrieval_quality(self) -> BenchmarkResult:
        return self.agent_services.benchmark_memory_retrieval_quality()

    def _benchmark_reference_hint_traceability(self) -> BenchmarkResult:
        return self.agent_services.benchmark_reference_hint_traceability()

    def _benchmark_page_section_query_parsing(self) -> BenchmarkResult:
        return self.agent_services.benchmark_page_section_query_parsing()

    def _benchmark_retrieval_report_schema(self) -> BenchmarkResult:
        return self.agent_services.benchmark_retrieval_report_schema()

    def _benchmark_decision_escalation(self) -> BenchmarkResult:
        return self.agent_services.benchmark_decision_escalation()

    def _benchmark_backend_failure_escalation(self) -> BenchmarkResult:
        return self.agent_services.benchmark_backend_failure_escalation()

    def _benchmark_python_runtime_validation(self) -> BenchmarkResult:
        return self.agent_services.benchmark_python_runtime_validation()

    def _benchmark_replay_improves(self) -> BenchmarkResult:
        return self.agent_services.benchmark_replay_improves()

    def _benchmark_regression_task_matrix(self) -> BenchmarkResult:
        return self.agent_services.benchmark_regression_task_matrix()

    def _benchmark_llm_smoke(self) -> BenchmarkResult:
        return self.agent_services.benchmark_llm_smoke()

    async def run_live_replay_benchmark(self, task: str, runs: int = 2) -> BenchmarkResult:
        """Execute the same real task multiple times and report whether later runs improve."""
        started = time.perf_counter()
        attempts: List[int] = []
        successes: List[bool] = []
        total_runs = max(runs, 2)
        for _ in range(total_runs):
            result = await self.execute_task(task)
            attempts.append(int(result.attempts))
            successes.append(bool(result.success))
        report = self.build_task_learning_report(task, limit=total_runs)
        return self.trace_reporter.build_replay_benchmark_result(task, attempts, successes, report, started)

    def build_task_learning_report(self, task: str, limit: int = 5) -> Dict:
        """Summarize decision traces and reusable memory for one task."""
        traces = self._load_task_traces(task, limit=limit)
        memory_hits = self.memory.retrieve_relevant(task, limit=limit)
        return self.trace_reporter.build_task_learning_report_from_data(task, traces, memory_hits, limit=limit)

    def _write_benchmark_report(self, report_path: Path, results: List[BenchmarkResult]):
        """Compatibility facade for older tests and scripts."""
        return self.agent_services.write_benchmark_report(report_path, results)

    def _load_task_traces(self, task: str, limit: int = 5) -> List[Dict]:
        """Compatibility facade for trace loading."""
        return self.agent_services.load_task_traces(task, limit=limit)

    def _select_next_action(self, state: AgentState, plan: TaskPlan) -> str:
        """Planner-guided executor action selection."""
        action, _ = self._decide_next_action(state, plan, self._analyze_iteration_state(state, plan))
        return action

    def _analyze_iteration_state(self, state: AgentState, plan: TaskPlan) -> Dict[str, object]:
        """Summarize the current loop state into decision-friendly signals."""
        return self.agent_planner.analyze_iteration_state(state, plan)

    def _decide_next_action(self, state: AgentState, plan: TaskPlan, analysis: Dict[str, object]) -> Tuple[str, str]:
        """Choose the next agent action using loop state, failure repetition, and retrieval quality."""
        return self.agent_planner.decide_next_action(state, plan, analysis)

    def _build_failure_signature(self, state: AgentState) -> str:
        """Collapse the dominant current failure into one comparable signature."""
        return self.agent_planner.build_failure_signature(state)

    def _classify_failure_signature(self, text: str) -> str:
        return self.agent_planner.classify_failure_signature(text)

    def _is_backend_failure_signature(self, signature: str) -> bool:
        return self.agent_planner.is_backend_failure_signature(signature)

    def _normalize_failure_signature(self, text: str) -> str:
        return self.agent_planner.normalize_failure_signature(text)

    def _record_iteration_trace(self, state: AgentState, action: str, reason: str, success: bool, observation: ActionObservation):
        """Track loop progress, repeated failures, and iteration-level decisions."""
        self.agent_planner.record_iteration_trace(state, action, reason, success, observation)

    def _build_progress_fingerprint(self, state: AgentState) -> str:
        """Represent task progress compactly so the loop can detect stagnation."""
        return self.agent_planner.build_progress_fingerprint(state)

    async def _execute_action(self, action: str, task: str, state: AgentState, plan: TaskPlan) -> bool:
        """Run the chosen executor action."""
        return await self.agent_executor.execute_action(action, task, state, plan)

    async def _observe_action(self, action: str, success: bool, state: AgentState, plan: TaskPlan) -> ActionObservation:
        """Observe the result of one executor action and decide next step."""
        planner_observation = self.agent_planner.observe_action(action, success, state, plan, self._is_output_only_generation)
        return await self.agent_executor.observe_action(action, success, state, plan, planner_observation)

    def _build_final_result(self, state: AgentState, task_start: datetime, success: bool, message: str) -> TaskResult:
        """Convert current agent state into a stable task result."""
        return self.agent_planner.build_final_result(state, task_start, success, message)

    def _create_task_plan(self, task: str) -> TaskPlan:
        """Create a deterministic execution plan before retrieval or generation."""
        return self.agent_planner.create_task_plan(task)

    def _plan_to_dict(self, plan: TaskPlan) -> Dict:
        return self.agent_planner.plan_to_dict(plan)

    def _get_task_plan(self, state: AgentState, task: str) -> TaskPlan:
        return self.agent_planner.get_task_plan(state, task)
    
    async def _generate_code(self, task: str, state: AgentState) -> bool:
        """Generate code from task"""
        return await self.agent_executor.generate_code(task, state)
    
    async def _fix_errors(self, state: AgentState) -> bool:
        """Fix compilation error"""
        return await self.agent_executor.fix_errors(state)

    async def _build_integrated_reference_spec(self, task: str, plan: Optional[TaskPlan] = None, state: Optional[AgentState] = None) -> str:
        """Create per-chapter notes and merge them into one implementation spec."""
        return await self.document_workers.build_integrated_reference_spec(task, plan=plan, state=state)

    def _parse_and_write_code(self, response: str, state: AgentState, allowed_outputs: Optional[List[str]] = None):
        """Parse and write generated code"""
        if self._is_insufficient_documentation_response(response):
            state.insufficient_documentation = True
            state.response_preview = "INSUFFICIENT DOCUMENTATION"
            raise ValueError("INSUFFICIENT DOCUMENTATION")

        normalized_response = self._normalize_document_worker_response(response)
        code_payload = self._extract_code_payload(normalized_response)
        generated_files = self._extract_file_blocks(code_payload)
        normalized_allowed = set(self._normalize_allowed_outputs(allowed_outputs))
        for raw_path, code in generated_files:
            path = self._sanitize_generated_path(raw_path, code)
            if not path or not code:
                continue
            if normalized_allowed and path not in normalized_allowed:
                raise ValueError(f"Generated file outside allowed_outputs whitelist: {path}")
            self.file_tools.write_file(path, code)
            state.generated_files[path] = code
            logger.info(f"[OK] Generated: {path}")
        if not generated_files:
            preview = re.sub(r"\s+", " ", normalized_response[:400]).strip()
            state.response_preview = preview
            logger.error(f"LLM response preview: {preview}")
            if "[CODE]" in normalized_response or any(marker in normalized_response for marker in ("[QUERY]", "[UNDERSTANDING]")):
                raise ValueError("Model returned structured prose but no FILE blocks in [CODE]")
            raise ValueError("No valid FILE blocks found in model response")

    async def _review_generated_outputs(
        self,
        task: str,
        state: AgentState,
        evidence: EvidenceBundle,
        reference_hints: Dict[str, List[str]],
        allowed_outputs: List[str],
        query_text: str,
        understanding_lines: List[str],
    ) -> Tuple[bool, str]:
        """Review generated files before reporting success."""
        file_payload = []
        for path in allowed_outputs:
            code = state.generated_files.get(path)
            if not code:
                continue
            file_payload.append({
                "path": path,
                "code": self._truncate_smart(code, max_chars=6000),
            })

        if len(file_payload) != len(allowed_outputs):
            missing = [path for path in allowed_outputs if path not in state.generated_files]
            return False, f"Missing required output files: {', '.join(missing[:4])}"

        local_findings = self._run_local_output_checks(state, allowed_outputs, evidence, understanding_lines, reference_hints)
        if local_findings:
            summary = "; ".join(local_findings[:3])
            logger.info(f"[FAIL] Local output checks rejected generated outputs: {summary}")
            state.review_preview = self._preview_text(summary)
            return False, summary

        static_result = self.build_tools.run_static_analysis(allowed_outputs)
        if static_result.status != "success":
            summary = static_result.stderr.strip() or static_result.stdout.strip() or "Static analysis rejected generated outputs."
            logger.info("[FAIL] Static analysis rejected generated outputs: %s", summary[:300])
            state.review_preview = self._preview_text(summary)
            return False, summary

        prompt = f"""Task: {task}

You are a strict document-driven reviewer.
Review only for concrete implementation issues against the retrieved documents below.
Do not rewrite code.
Return one compact JSON object only.
    Approval rules:
    - approved may be true only when every hardware-specific symbol, instance, pin, AF mapping, IRQ name, and helper/API used in the generated code is directly supported by the retrieved context or the understanding section below.
    - register_schema_authoritative is the strongest register-level evidence. It contains peripheral/register/offset/reset/access/bitfields/page citation extracted from the RM.
    - register_reference_hints and bitfield_reference_hints are distilled from retrieved STM32 references and may be used as secondary traceability evidence.
    - register-level code must not use offsets, bitfields, reset/access assumptions, or registers absent from register_schema_authoritative unless the retrieved context explicitly supports them.
    - if there is any unsupported anchor or any traceability gap, approved must be false.
    - prefer false negatives over false positives.

Query:
{query_text}

Retrieved context:
{self._format_retrieved_context_block(evidence)}

Reference hints:
{self._format_reference_hint_block(reference_hints)}

Understanding:
{chr(10).join(f'- {line}' for line in understanding_lines)}

Allowed outputs:
{json.dumps(allowed_outputs, indent=2)}

Generated files:
{json.dumps(file_payload, indent=2)}

Return JSON only with this schema:
{{
    "approved": false,
  "findings": ["..."],
    "required_fixes": ["..."],
    "unsupported_references": ["..."],
    "traceability_gaps": ["..."],
    "evidence_backing": [{{"path": "...", "symbols": ["..."]}}]
}}
"""
        from src.infrastructure.llm.structured_output import extract_structured_json, SCHEMA_REVIEW_RESPONSE
        response = await self._guarded_llm_generate(prompt, "review", state=state)
        self._capture_llm_preview(state, "review_response", response)

        data, errors = extract_structured_json(response, schema=SCHEMA_REVIEW_RESPONSE)
        if not data:
            logger.warning("Review JSON extraction failed: %s", errors)
            # Fall back to regex-based extraction
            review = self._extract_json_object(response) or {}
        else:
            review = data
        approved = bool(review.get("approved"))
        findings = review.get("findings", [])
        required_fixes = review.get("required_fixes", [])
        unsupported_references = review.get("unsupported_references", [])
        traceability_gaps = review.get("traceability_gaps", [])
        messages: List[str] = []
        if isinstance(findings, list):
            messages.extend(str(item).strip() for item in findings if str(item).strip())
        if isinstance(required_fixes, list):
            messages.extend(str(item).strip() for item in required_fixes if str(item).strip())
        if isinstance(unsupported_references, list):
            messages.extend(str(item).strip() for item in unsupported_references if str(item).strip())
        if isinstance(traceability_gaps, list):
            messages.extend(str(item).strip() for item in traceability_gaps if str(item).strip())
        if traceability_gaps or unsupported_references:
            approved = False
        if approved:
            logger.info("[OK] Reviewer approved generated outputs")
            return True, "; ".join(messages[:2]) if messages else "approved"
        state.review_preview = self._preview_text(response)
        summary = "; ".join(messages[:3]) if messages else "Reviewer did not approve the generated outputs."
        if not review:
            summary = f"{summary} Raw review preview: {state.review_preview}"
        logger.info(f"[FAIL] Reviewer rejected generated outputs: {summary}")
        return False, summary

    def _run_local_output_checks(
        self,
        state: AgentState,
        allowed_outputs: List[str],
        evidence: EvidenceBundle,
        understanding_lines: List[str],
        reference_hints: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        """Reject obviously invalid generated code before asking the model to review it."""
        return self.review_support.run_local_output_checks(state, allowed_outputs, evidence, understanding_lines, reference_hints)

    def _find_required_traceability_gaps(
        self,
        code: str,
        understanding_lines: List[str],
        reference_hints: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        return self.review_support.find_required_traceability_gaps(code, understanding_lines, reference_hints)

    def _find_unsupported_traceability_anchors(
        self,
        source_code: str,
        evidence: EvidenceBundle,
        understanding_lines: List[str],
        reference_hints: Optional[Dict[str, List[str]]] = None,
    ) -> List[str]:
        return self.review_support.find_unsupported_traceability_anchors(source_code, evidence, understanding_lines, reference_hints)

    def _extract_driver_api_names(self, spec_data: Dict) -> List[str]:
        return self.review_support.extract_driver_api_names(spec_data)

    def _find_signature_mismatches(self, header_code: str, source_code: str) -> List[str]:
        return self.review_support.find_signature_mismatches(header_code, source_code)

    def _collect_reference_hints(self, task: str, plan: TaskPlan) -> Dict[str, List[str]]:
        """Aggregate register/bitfield hints across the planned STM32 chapters."""
        return self.review_support.collect_reference_hints(task, plan)

    def _format_reference_hint_block(self, reference_hints: Optional[Dict[str, List[str]]]) -> str:
        return self.review_support.format_reference_hint_block(reference_hints)

    def _extract_function_signatures(self, code: str, expect_definition: bool) -> Dict[str, str]:
        return self.review_support.extract_function_signatures(code, expect_definition)

    def _dedupe_preserve_order(self, items: List[str]) -> List[str]:
        return self.review_support.dedupe_preserve_order(items)
    
    def _extract_code(self, response: str) -> Optional[str]:
        """Extract code block from response"""
        return self.output_sanitizer.extract_code(response)

    def _extract_json_object(self, response: str) -> Optional[Dict]:
        """Extract the first valid JSON object from an LLM response."""
        return self.output_sanitizer.extract_json_object(response)

    def _preview_text(self, response: str, limit: int = 400) -> str:
        """Create a compact single-line preview from an LLM response."""
        return self._truncate_smart(response, max_chars=limit)

    def _truncate_smart(self, text: str, max_chars: int = 6000) -> str:
        """Keep both ends of long text so diagnostics preserve endings."""
        return self.output_sanitizer.truncate_smart(text, max_chars)

    def _log_response_preview(self, label: str, response: str, level: str = "info"):
        """Log a compact preview of a model response for debugging."""
        preview = self._preview_text(response)
        log_fn = logger.info if level == "info" else logger.debug
        log_fn(f"LLM preview [{label}]: {preview}")

    def _capture_llm_preview(self, state: AgentState, label: str, response: str):
        """Persist the latest model preview in agent state and logs."""
        state.response_stage = label
        state.response_preview = self._preview_text(response)
        self._log_response_preview(label, response)

    def _is_insufficient_documentation_response(self, response: str) -> bool:
        return self.output_sanitizer.is_insufficient_documentation_response(response)

    def _normalize_document_worker_response(self, response: str) -> str:
        return self.output_sanitizer.normalize_document_worker_response(response)

    def _extract_code_payload(self, response: str) -> str:
        return self.output_sanitizer.extract_code_payload(response)

    def _extract_file_blocks(self, response: str) -> List[Tuple[str, str]]:
        """Extract file/code pairs from several common LLM response formats."""
        return self.output_sanitizer.extract_file_blocks(response)

    def _extract_explicit_file_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.output_sanitizer.extract_explicit_file_blocks(response)

    def _extract_backticked_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.output_sanitizer.extract_backticked_path_blocks(response)

    def _extract_bold_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.output_sanitizer.extract_bold_path_blocks(response)

    def _extract_heading_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.output_sanitizer.extract_heading_path_blocks(response)

    def _extract_plain_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.output_sanitizer.extract_plain_path_blocks(response)

    def _sanitize_generated_path(self, raw_path: str, code: str) -> Optional[str]:
        """Normalize model-generated FILE paths into safe relative paths."""
        return self.output_sanitizer.sanitize_generated_path(raw_path, code)

    def _is_vendor_managed_path(self, path: str) -> bool:
        """Return True when a path points at vendor-managed HAL/CMSIS content."""
        return self.output_sanitizer.is_vendor_managed_path(path)

    def _normalize_to_output_path(self, path: str) -> str:
        """Force all generated output into a separate output-only folder."""
        return self.output_sanitizer.normalize_to_output_path(path)

    def _is_output_only_generation(self, paths: Iterable[str]) -> bool:
        """Return True when all generated files are confined to the output folder."""
        return all(Path(path).as_posix().startswith(f"{OUTPUT_GENERATED_ROOT}/") for path in paths)

    def _format_reference_context(self, task: str) -> str:
        """Build evidence-backed reference context using the phase-1 retriever."""
        evidence = self._build_evidence_bundle(task)
        if not evidence.retrieved_hits:
            return "- No local retrieval evidence found."
        return self.evidence_builder.format_for_prompt(evidence)

    def search_docs(self, task: str, build_error: str = "", review_feedback: str = "", top_k: int = 3, allow_semantic: bool = True) -> List[RetrievalHit]:
        """Search local chunks and reference metadata before answering or coding."""
        query = self.query_analyzer.analyze(task, build_error=build_error, review_feedback=review_feedback)
        self._ensure_rag_ready(require_page_chunks=allow_semantic and self._query_needs_page_chunks(query))
        query.top_k = top_k
        cache_key = self._make_search_cache_key(query, top_k=top_k, allow_semantic=allow_semantic)
        cached = self._get_cached_search_hits(cache_key)
        if cached is not None:
            return cached
        hits = self.hybrid_retriever.search_docs(query, allow_semantic=allow_semantic)
        if allow_semantic:
            hits = self._augment_hits_with_direct_page_hits(query, hits)
        self._cache_search_hits(cache_key, hits)
        return hits

    def _make_search_cache_key(self, query: RetrievalQuery, top_k: int, allow_semantic: bool) -> str:
        return self.search_cache.make_key(query, top_k, allow_semantic)

    def _get_cached_search_hits(self, cache_key: str) -> Optional[List[RetrievalHit]]:
        return self.search_cache.get(cache_key)

    def _cache_search_hits(self, cache_key: str, hits: List[RetrievalHit]):
        self.search_cache.set(cache_key, hits)

    def build_retrieval_report(
        self,
        task: str,
        build_error: str = "",
        review_feedback: str = "",
        top_k: int = 5,
        allow_semantic: bool = True,
    ) -> Dict:
        """Build a JSON-friendly retrieval report with page/section aware ranking details."""
        return self.agent_services.build_retrieval_report(
            task,
            build_error=build_error,
            review_feedback=review_feedback,
            top_k=top_k,
            allow_semantic=allow_semantic,
        )

    def _query_needs_page_chunks(self, query: RetrievalQuery) -> bool:
        return self.retrieval_support.query_needs_page_chunks(query)

    def _augment_hits_with_direct_page_hits(self, query: RetrievalQuery, hits: List[RetrievalHit]) -> List[RetrievalHit]:
        return self.retrieval_support.augment_hits_with_direct_page_hits(query, hits)

    def _resolve_candidate_pdf_paths(self, query: RetrievalQuery, hits: List[RetrievalHit]) -> List[Path]:
        return self.retrieval_support.resolve_candidate_pdf_paths(query, hits)

    def _extract_direct_page_hits(self, pdf_path: Path, requested_pages: List[str]) -> List[RetrievalHit]:
        return self.retrieval_support.extract_direct_page_hits(pdf_path, requested_pages)

    def write_retrieval_report(
        self,
        report_path: Path,
        task: str,
        build_error: str = "",
        review_feedback: str = "",
        top_k: int = 5,
        allow_semantic: bool = True,
    ) -> Dict:
        return self.agent_services.write_retrieval_report(
            report_path,
            task,
            build_error=build_error,
            review_feedback=review_feedback,
            top_k=top_k,
            allow_semantic=allow_semantic,
        )

    def _build_document_understanding(self, task: str, evidence: EvidenceBundle) -> List[str]:
        return self.evidence_support.build_document_understanding(task, evidence)

    def _format_retrieved_context_block(self, evidence: EvidenceBundle) -> str:
        return self.evidence_support.format_retrieved_context_block(evidence)

    def _format_memory_context_block(self, evidence: EvidenceBundle) -> str:
        """Render relevant prior failures and fixes as a compact prompt block."""
        return self.evidence_support.format_memory_context_block(evidence)

    def _build_evidence_bundle(
        self,
        task: str,
        state: Optional[AgentState] = None,
        local_paths: Optional[List[str]] = None,
        query_suffix: str = "",
        allow_semantic: bool = True,
    ) -> EvidenceBundle:
        """Assemble retrieval results and optional local files into one bundle."""
        return self.evidence_support.build_evidence_bundle(task, state=state, local_paths=local_paths, query_suffix=query_suffix, allow_semantic=allow_semantic)

    def _ensure_rag_ready(self, require_page_chunks: bool = False):
        """Lazily build the local retrieval index when the caller skipped eager bootstrap."""
        if not self.retrieval_ingestor.should_rebuild_rag_index(require_page_chunks=require_page_chunks):
            return
        self._initialize_rag(include_semantic=require_page_chunks, reason="lazy_retrieval", strict=True)

    def _resolve_workspace_document_path(self, filename: str) -> Optional[Path]:
        return self.retrieval_ingestor.resolve_workspace_document_path(filename)

    def _extract_pdf_structured_pages(self, file_path: Path) -> List[str]:
        return self.retrieval_ingestor.extract_pdf_structured_pages(file_path)

    def _extract_pdf_page_text_with_fallback(self, page) -> str:
        return self.retrieval_ingestor.extract_pdf_page_text_with_fallback(page)

    def _extract_pdf_toc_entries(self, file_path: Path, page_texts: List[str]) -> List[Dict]:
        return self.retrieval_ingestor.extract_pdf_toc_entries(file_path, page_texts)

    def _infer_pdf_page_section_title(self, text: str) -> str:
        return self.retrieval_ingestor.infer_pdf_page_section_title(text)

    def _match_page_to_toc_entry(self, page_index: int, toc_entries: List[Dict]) -> Dict:
        return self.retrieval_ingestor.match_page_to_toc_entry(page_index, toc_entries)

    def _extract_register_terms_from_text(self, text: str) -> List[str]:
        return self.retrieval_ingestor.extract_register_terms_from_text(text)

    def _extract_bitfield_terms_from_text(self, text: str) -> List[str]:
        return self.retrieval_ingestor.extract_bitfield_terms_from_text(text)

    def _safe_int(self, value: object, default: int = 0) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                return default
        return default

    def _build_retrieval_refinement_suffix(self, state: AgentState) -> str:
        """Rotate retrieval query strategy when the gate has blocked repeatedly."""
        parts: List[str] = []
        if state.last_error:
            parts.extend([state.last_error.message, state.last_error.file])
        if state.review_feedback:
            parts.append(state.review_feedback)
        for item in state.last_memory_hits[:2]:
            parts.extend([
                str(item.get("error_signature", "")),
                str(item.get("root_cause", "")),
                str(item.get("fix_strategy", "")),
            ])

        strategy_index = min(state.retrieval_block_streak, 3)
        if strategy_index == 0:
            parts.append("reference manual registers bitfields initialization sequence")
        elif strategy_index == 1:
            parts.append("peripheral register map clock enable alternate function irq configuration")
        elif strategy_index == 2:
            parts.append("implementation example baud rate brr cr1 cr2 cr3 sr dr nvic gpio afr")
        else:
            parts.append("datasheet app note code example failure analysis debug fix constraints")

        return " ".join(str(part).strip() for part in parts if str(part).strip())

    def _ensure_retrieval_confidence(self, task: str, state: AgentState, local_paths: Optional[List[str]] = None) -> EvidenceBundle:
        """Run retrieval, refine once when weak, and block acting when evidence stays too weak."""
        evidence = self._build_evidence_bundle(task, state=state, local_paths=local_paths)
        if evidence.confidence != "low":
            state.retrieval_blocker = ""
            state.retrieval_block_streak = 0
            return evidence

        self._log_agent_phase("think", "Initial retrieval confidence is low; refining search strategy.")
        refined_suffix = self._build_retrieval_refinement_suffix(state)
        evidence = self._build_evidence_bundle(task, state=state, local_paths=local_paths, query_suffix=refined_suffix)
        if evidence.confidence == "low":
            state.retrieval_block_streak += 1
            state.retrieval_blocker = f"Retrieval confidence remained low after refinement for query: {state.last_retrieval_query}"
            self._log_agent_phase("observe", state.retrieval_blocker)
        else:
            state.retrieval_block_streak = 0
            state.retrieval_blocker = ""
            self._log_agent_phase("observe", "Retrieval confidence improved after refinement.")
        return evidence

    def _should_use_chapter_workers(self, task: str) -> bool:
        return self.document_workers.should_use_chapter_workers(task)

    def _select_chapter_plan(self, task: str) -> List[str]:
        return self.document_workers.select_chapter_plan(task)

    def _infer_task_target(self, task: str, query: Optional[RetrievalQuery] = None) -> Tuple[str, str]:
        text = task.lower()
        query = query or self.query_analyzer.analyze(task)
        chip = ""
        if query.entities.get("chips"):
            chip = str(query.entities["chips"][0]).upper()
        else:
            match = re.search(r"\b(stm32[a-z0-9]+|esp32[a-z0-9-]*|nrf[0-9]+[a-z0-9]*|atmega[0-9]+|rp2040|pic32[a-z0-9]+)\b", text, re.IGNORECASE)
            if match:
                chip = match.group(1).upper()

        family = ""
        chip_lower = chip.lower()
        if chip_lower.startswith("stm32"):
            family = chip_lower[:7]
        elif chip:
            family = chip_lower
        return family, chip

    def _resolve_target_chip(self, task: str, plan: Optional[TaskPlan] = None, state: Optional[AgentState] = None) -> str:
        if plan and plan.target_chip:
            return plan.target_chip
        if state and isinstance(state.plan, dict):
            target_chip = str(state.plan.get("target_chip", "")).strip()
            if target_chip:
                return target_chip
        _, target_chip = self._infer_task_target(task)
        return target_chip

    async def _generate_chapter_note(
        self,
        task: str,
        chapter: str,
        session_dir: Path,
        retry_count: int = 0,
        state: Optional[AgentState] = None,
    ) -> Optional[ChapterNote]:
        """Generate a JSON note for one chapter/peripheral area."""
        return await self.document_workers.generate_chapter_note(task, chapter, session_dir, retry_count=retry_count, state=state)

    async def _merge_chapter_notes(
        self,
        task: str,
        chapter_notes: List[ChapterNote],
        session_dir: Path,
        plan: Optional[TaskPlan] = None,
    ) -> str:
        """Merge worker outputs into one integrated implementation spec."""
        return await self.document_workers.merge_chapter_notes(task, chapter_notes, session_dir, plan=plan)

    def _normalize_allowed_outputs(self, paths) -> List[str]:
        """Normalize spec output paths into safe, exact whitelist entries."""
        return self.output_sanitizer.normalize_allowed_outputs(paths)

    def _default_allowed_outputs(
        self,
        task: str,
        domain_profile: str = "generic_document",
        target_family: str = "",
        target_chip: str = "",
    ) -> List[str]:
        """Compatibility facade for default generated output policy."""
        return self.output_policy.default_allowed_outputs(
            task,
            domain_profile=domain_profile,
            target_family=target_family,
            target_chip=target_chip,
        )

    def _score_trace_artifact_quality(self, trace: Dict) -> Dict[str, int | bool]:
        """Compatibility facade for trace quality scoring."""
        return self.agent_services.score_trace_artifact_quality(trace)

    def _should_skip_workspace_indexing(self, file_path: Path, normalized_path: str) -> bool:
        """Compatibility facade for workspace indexing policy."""
        return self.retrieval_ingestor.should_skip_workspace_indexing(file_path, normalized_path)

    def _load_register_schema(self) -> Dict:
        schema_path = (Path(self.project_root) / RAG_REGISTER_SCHEMA_FILE).resolve()
        if not schema_path.exists():
            return {"schema_version": RAG_SCHEMA_VERSION, "entries": []}
        try:
            data = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": RAG_SCHEMA_VERSION, "entries": []}
        if not isinstance(data, dict):
            return {"schema_version": RAG_SCHEMA_VERSION, "entries": []}
        data.setdefault("entries", [])
        return data

    def _query_register_schema(self, task: str, plan: Optional[TaskPlan] = None, limit: int = 24) -> List[Dict]:
        schema = self._load_register_schema()
        entries = schema.get("entries", [])
        if not entries:
            entries = self._query_register_schema_from_chunks(task, plan, limit=limit)
        if not isinstance(entries, list):
            return []
        query = self.query_analyzer.analyze(task)
        terms = set(query.normalized_query.split())
        terms.update(str(item).lower() for item in query.entities.get("peripherals", []))
        terms.update(str(item).lower() for item in query.entities.get("register_terms", []))
        target_chip = (plan.target_chip if plan else "") or self._resolve_target_chip(task)
        if target_chip:
            terms.add(target_chip.lower())
        scored: List[Tuple[float, Dict]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            citation = entry.get("citation", {}) if isinstance(entry.get("citation", {}), dict) else {}
            haystack = " ".join([
                str(entry.get("peripheral", "")),
                str(entry.get("register", "")),
                str(entry.get("offset", "")),
                " ".join(str(item) for item in entry.get("bitfields", [])),
                str(citation.get("document", "")),
                str(citation.get("section", "")),
                str(citation.get("excerpt", "")),
            ]).lower()
            score = sum(1.0 for term in terms if term and term in haystack)
            if str(entry.get("register", "")).lower() in {term.lower() for term in query.entities.get("register_terms", [])}:
                score += 4.0
            if str(entry.get("peripheral", "")).lower() in {term.lower() for term in query.entities.get("peripherals", [])}:
                score += 3.0
            if target_chip and target_chip.lower() in haystack:
                score += 2.0
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    def _query_register_schema_from_chunks(self, task: str, plan: Optional[TaskPlan] = None, limit: int = 24) -> List[Dict]:
        query = self.query_analyzer.analyze(task)
        query_terms = set(query.normalized_query.split())
        query_terms.update(str(item).lower() for item in query.entities.get("peripherals", []))
        query_terms.update(str(item).lower() for item in query.entities.get("register_terms", []))
        scored_chunks: List[Tuple[float, object]] = []
        for chunk in self.chunk_store.get_all():
            metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
            haystack = " ".join([
                str(chunk.path),
                str(chunk.summary),
                str(chunk.section),
                str(metadata.get("section_title", "")),
                str(metadata.get("toc_section", "")),
                str(metadata.get("register_terms", "")),
                str(metadata.get("register_table_hints", "")),
                str(chunk.text[:1000]),
            ]).lower()
            score = sum(1.0 for term in query_terms if term and term in haystack)
            if metadata.get("register_table_hints"):
                score += 2.0
            if metadata.get("page"):
                score += 0.5
            if score > 0:
                scored_chunks.append((score, chunk))
        scored_chunks.sort(key=lambda item: item[0], reverse=True)

        entries: List[Dict] = []
        for _, chunk in scored_chunks[:20]:
            metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
            try:
                page = int(metadata.get("page", 0) or 0)
            except Exception:
                page = 0
            entries.extend(self.retrieval_ingestor.extract_register_schema_entries(
                chunk.text,
                str(chunk.path),
                page,
                str(metadata.get("section_title", "") or metadata.get("toc_section", "") or chunk.section),
            ))
            if len(entries) >= limit:
                break
        return self.retrieval_ingestor.dedupe_register_schema_entries(entries)[:limit]

    def _diagnose_runtime_output(self, result: ToolResult, plan: TaskPlan) -> RuntimeDiagnosis:
        """Parse runtime logs into a compact diagnosis for the observer loop."""
        return self.runtime_support.diagnose_runtime_output(result, plan)

    def _record_experience(self, state: AgentState, result: TaskResult):
        """Persist a compact lesson set for later runs."""
        self.experience_support.record_experience(state, result)

    def _persist_decision_trace(self, state: AgentState, result: TaskResult, last_error: str, memory_records: List[Dict]):
        """Write one audit trace per run so loop decisions and learning can be inspected after execution."""
        self.experience_support.persist_decision_trace(state, result, last_error, memory_records)

    def _make_task_slug(self, task: str) -> str:
        return self.experience_support.make_task_slug(task)

    def _build_memory_records(self, state: AgentState, result: TaskResult, last_error: str) -> List[Dict]:
        """Convert one task run into structured memory records reusable on later iterations."""
        return self.experience_support.build_memory_records(state, result, last_error)

    def _summarize_root_cause(self, state: AgentState, last_error: str) -> str:
        """Choose the most informative current failure description for persistent memory."""
        return self.experience_support.summarize_root_cause(state, last_error)

    def _summarize_fix_strategy(self, state: AgentState, result: TaskResult) -> str:
        """Persist the corrective action that should be reused or avoided later."""
        return self.experience_support.summarize_fix_strategy(state, result)

    def _collect_memory_context_terms(self, state: AgentState) -> List[str]:
        """Extract compact matching terms so later runs can retrieve this memory slice."""
        return self.experience_support.collect_memory_context_terms(state)

    def _derive_lessons(self, state: AgentState, result: Optional[TaskResult], last_error: str) -> List[str]:
        """Convert one run into reusable prompt rules."""
        return self.experience_support.derive_lessons(state, result, last_error)


async def main():
    from src.application.api.app.cli import run_cli

    await run_cli(EmbeddedCAgent)


if __name__ == "__main__":
    asyncio.run(main())