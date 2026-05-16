import logging
from typing import Awaitable, Callable, Dict, Iterable, List, Optional, Tuple

from src.infrastructure.models import ActionObservation, AgentState, EvidenceBundle, RuntimeDiagnosis, TaskPlan, ToolResult

logger = logging.getLogger(__name__)


class AgentExecutor:
    def __init__(
        self,
        build_tools,
        file_tools,
        evidence_builder,
        parse_and_write_code: Callable[..., None],
        review_generated_outputs: Callable[..., Awaitable[Tuple[bool, str]]],
        ensure_retrieval_confidence: Callable[..., EvidenceBundle],
        collect_reference_hints: Callable[[str, TaskPlan], Dict[str, List[str]]],
        format_retrieved_context_block: Callable[[EvidenceBundle], str],
        format_memory_context_block: Callable[[EvidenceBundle], str],
        build_document_understanding: Callable[[str, EvidenceBundle], List[str]],
        format_reference_hint_block: Callable[[Dict[str, List[str]]], str],
        guarded_llm_generate: Callable[..., Awaitable[str]],
        capture_llm_preview: Callable[[AgentState, str, str], None],
        normalize_allowed_outputs: Callable[[object], List[str]],
        get_task_plan: Callable[[AgentState, str], TaskPlan],
        parse_code: Callable[[str], Optional[str]],
        preview_text: Callable[[str, int], str],
        diagnose_runtime_output: Callable[[ToolResult, TaskPlan], RuntimeDiagnosis],
        is_vendor_managed_path: Callable[[str], bool],
        is_output_only_generation: Callable[[Iterable[str]], bool],
    ):
        self.build_tools = build_tools
        self.file_tools = file_tools
        self.evidence_builder = evidence_builder
        self._parse_and_write_code = parse_and_write_code
        self._review_generated_outputs = review_generated_outputs
        self._ensure_retrieval_confidence = ensure_retrieval_confidence
        self._collect_reference_hints = collect_reference_hints
        self._format_retrieved_context_block = format_retrieved_context_block
        self._format_memory_context_block = format_memory_context_block
        self._build_document_understanding = build_document_understanding
        self._format_reference_hint_block = format_reference_hint_block
        self._guarded_llm_generate = guarded_llm_generate
        self._capture_llm_preview = capture_llm_preview
        self._normalize_allowed_outputs = normalize_allowed_outputs
        self._get_task_plan = get_task_plan
        self._parse_code = parse_code
        self._preview_text = preview_text
        self._diagnose_runtime_output = diagnose_runtime_output
        self._is_vendor_managed_path = is_vendor_managed_path
        self._is_output_only_generation = is_output_only_generation

    async def execute_action(self, action: str, task: str, state: AgentState, plan: TaskPlan) -> bool:
        if action == "retrieve_more":
            evidence = self._ensure_retrieval_confidence(task, state=state, local_paths=list(state.generated_files.keys())[:2])
            return getattr(evidence, "confidence", "low") != "low"
        if action == "generate":
            return await self.generate_code(task, state)
        if action == "build":
            build_result = await self.build_tools.run_build()
            logger.info(f"Build: {build_result.status}")
            state.last_build_result = build_result
            return build_result.status == "success"
        if action == "flash":
            if not plan.target_project:
                raise ValueError("Flash requested but target project is unknown.")
            flash_result = await self.build_tools.run_flash(plan.target_project)
            logger.info(f"Flash: {flash_result.status}")
            state.last_flash_result = flash_result
            return flash_result.status == "success"
        if action == "runtime_observe":
            runtime_result = await self.build_tools.run_runtime_observe(dry_run=plan.runtime_dry_run)
            logger.info(f"Runtime observe: {runtime_result.status}")
            if runtime_result.status != "success" or "hardfault" in str(runtime_result.stdout).lower():
                logger.warning("Runtime failed! Launching Auto-Debugger...")
                gdb_result = await self.build_tools.run_auto_debug(plan.target_project)
                if gdb_result.status == "success":
                    runtime_result.stderr = (runtime_result.stderr or "") + "\n--- GDB AUTO DEBUGGER ---\n" + gdb_result.stdout
                    runtime_result.stdout = (runtime_result.stdout or "") + "\n--- GDB AUTO DEBUGGER ---\n" + gdb_result.stdout
            state.last_runtime_result = runtime_result
            state.last_runtime_diagnosis = self._diagnose_runtime_output(runtime_result, plan)
            return runtime_result.status == "success"
        if action == "fix":
            return await self.fix_errors(state)
        if action == "complete":
            return True
        raise ValueError(f"Unknown executor action: {action}")

    async def observe_action(self, action: str, success: bool, state: AgentState, plan: TaskPlan, planner_observation: ActionObservation) -> ActionObservation:
        if action in {"complete", "retrieve_more"}:
            return planner_observation
        if not success and action in {"generate", "build", "flash", "runtime_observe"}:
            if action == "build" and state.last_build_result:
                build_result = state.last_build_result
                if build_result.errors:
                    logger.info(f"[FAIL] {len(build_result.errors)} error(s)")
                else:
                    logger.info(f"[FAIL] Build failed: {build_result.stderr or 'unknown error'}")
            if action == "flash" and state.last_flash_result:
                flash_error = state.last_flash_result.stderr.strip() or state.last_flash_result.stdout.strip() or "flash failed"
                logger.info(f"[FAIL] Flash failed: {flash_error[:240]}")
            if action == "runtime_observe" and state.last_runtime_result:
                diagnosis = state.last_runtime_diagnosis
                runtime_error = state.last_runtime_result.stderr.strip() or state.last_runtime_result.stdout.strip() or "runtime observe failed"
                if diagnosis and getattr(diagnosis, "warnings", None):
                    logger.info("[FAIL] Runtime warnings: %s", "; ".join(diagnosis.warnings[:3]))
                logger.info(f"[FAIL] Runtime observe failed: {runtime_error[:240]}")
            return planner_observation
        if action == "runtime_observe" and state.last_runtime_diagnosis:
            diagnosis = state.last_runtime_diagnosis
            if getattr(diagnosis, "findings", None):
                logger.info("[OK] Runtime findings: %s", "; ".join(diagnosis.findings[:3]))
            if getattr(diagnosis, "warnings", None):
                logger.info("[FAIL] Runtime warnings: %s", "; ".join(diagnosis.warnings[:3]))
            if getattr(diagnosis, "status", "") == "degraded":
                return planner_observation
        return planner_observation

    async def generate_code(self, task: str, state: AgentState) -> bool:
        try:
            plan = self._get_task_plan(state, task)
            state.insufficient_documentation = False
            allowed_outputs = self._normalize_allowed_outputs(plan.allowed_outputs)
            evidence = self._ensure_retrieval_confidence(task, state=state, local_paths=list(state.generated_files.keys())[:2])
            reference_hints = self._collect_reference_hints(task, plan)
            query_text = state.last_retrieval_query or task
            retrieved_context = self._format_retrieved_context_block(evidence)
            memory_context = self._format_memory_context_block(evidence)
            understanding_lines = self._build_document_understanding(task, evidence)
            hint_context = self._format_reference_hint_block(reference_hints)
            logger.info("[OK] Retrieval confidence before codegen: %s", getattr(evidence, "confidence", "unknown"))
            if getattr(evidence, "confidence", "low") == "low" or not getattr(evidence, "retrieved_hits", None):
                state.response_stage = "insufficient_documentation"
                state.response_preview = "INSUFFICIENT DOCUMENTATION"
                state.insufficient_documentation = True
                raise ValueError("INSUFFICIENT DOCUMENTATION")
            prompt = f"""Task: {task}

You are a code generation worker.
You are a document-driven coding agent.
Strict document policy:
- You MUST use retrieved content and the traceability hints below as the only source of truth.
- You MUST NOT rely on prior knowledge, planner assumptions, memory lessons, or guessed APIs.
- For register-level code, you MUST use only entries listed under register_schema_authoritative.
- Do not invent offsets, reset values, access types, bitfields, IRQ names, pins, or AF mappings not present in retrieved context or register_schema_authoritative.
- Use only the top 3 retrieved chunks below.
- If the retrieved context is not sufficient, return exactly: INSUFFICIENT DOCUMENTATION

Known prior failures to avoid:
{memory_context}

Reviewer feedback from the previous rejected attempt:
{state.review_feedback or "- none"}

Allowed output paths:
{chr(10).join(f"- {path}" for path in allowed_outputs)}

Required outputs:
- One public header defining config, API, and status/error handling.
- One source file implementing the driver strictly from the retrieved documents.

Return this exact structure:
[QUERY]
{query_text}

[RETRIEVED CONTEXT]
{retrieved_context}

[REFERENCE HINTS]
{hint_context}

[UNDERSTANDING]
{chr(10).join(f"- {line}" for line in understanding_lines)}

[CODE]
FILE: path/file.h
```c
code
```
FILE: path/file.c
```c
code
```

Do not add extra sections.
Do not repeat any known failure pattern listed above.
Do not use any information that cannot be traced to the retrieved context or reference hints above."""
            response = await self._guarded_llm_generate(prompt, "generate", state=state)
            self._capture_llm_preview(state, "codegen_response", response)
            self._parse_and_write_code(response, state, allowed_outputs=allowed_outputs)
            if plan.should_review:
                approved, review_message = await self._review_generated_outputs(task, state, evidence, reference_hints, allowed_outputs, query_text, understanding_lines)
                if not approved:
                    state.review_feedback = review_message
                    raise ValueError(f"Reviewer rejected generated output: {review_message}")
            return True
        except Exception as exc:
            logger.error(f"Generation error: {exc}")
            return False

    async def fix_errors(self, state: AgentState) -> bool:
        if not state.last_error:
            logger.info("[FAIL] No compiler error available to fix")
            return False
        try:
            error = state.last_error
            if self._is_vendor_managed_path(error.file):
                logger.info(f"[FAIL] Refusing to overwrite vendor-managed file: {error.file}")
                return False
            evidence = self._ensure_retrieval_confidence(state.task, state=state, local_paths=[error.file])
            evidence_context = self.evidence_builder.format_for_prompt(evidence)
            memory_context = self._format_memory_context_block(evidence)
            if getattr(evidence, "confidence", "low") == "low":
                state.response_stage = "retrieval_gate"
                state.response_preview = self._preview_text(state.last_evidence_summary or state.retrieval_blocker, limit=400)
                raise ValueError(state.retrieval_blocker or "Retrieval confidence too low for fix flow")
            failing_file = self.file_tools.read_file(error.file)
            prompt = f"""Fix:
File: {error.file}
Error: {error.message}

Follow the local agent behavior contract exactly:
- Think -> act -> observe -> repeat.
- Use only the retrieved evidence and current file content below.
- Do not guess hidden APIs, symbols, or configuration.
- If the evidence is still insufficient to patch safely, say that you do not know based on current context.

Retrieved evidence:
{evidence_context}

Relevant prior failures and fixes:
{memory_context}

Current file content:
{failing_file[:6000]}

Provide fixed code only."""
            response = await self._guarded_llm_generate(prompt, "fix", state=state)
            code = self._parse_code(response)
            if code:
                self.file_tools.write_file(error.file, code)
                state.generated_files[error.file] = code
                state.fixes_applied.append(str(error))
                logger.info(f"[OK] Fixed: {error.file}")
                return True
            return False
        except Exception as exc:
            logger.error(f"Fix error: {exc}")
            return False
