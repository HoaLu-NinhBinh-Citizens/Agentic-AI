import re
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from src.core.config.agent_prompts import GENERIC_QUERY_STOPWORDS, OUTPUT_GENERATED_ROOT
from src.infrastructure.models import ActionObservation, AgentState, RetrievalQuery, TaskPlan, TaskResult


class AgentPlanner:
    def __init__(
        self,
        query_analyzer,
        infer_task_target: Callable[[str, Optional[RetrievalQuery]], Tuple[str, str]],
        should_use_chapter_workers: Callable[[str], bool],
        select_chapter_plan: Callable[[str], List[str]],
        default_allowed_outputs: Callable[[str, str, str, str], List[str]],
        normalize_allowed_outputs: Callable[[object], List[str]],
        derive_lessons: Callable[[AgentState, Optional[TaskResult], str], List[str]],
        safe_int: Callable[..., int],
    ):
        self.query_analyzer = query_analyzer
        self._infer_task_target = infer_task_target
        self._should_use_chapter_workers = should_use_chapter_workers
        self._select_chapter_plan = select_chapter_plan
        self._default_allowed_outputs = default_allowed_outputs
        self._normalize_allowed_outputs = normalize_allowed_outputs
        self._derive_lessons = derive_lessons
        self._safe_int = safe_int

    def analyze_iteration_state(self, state: AgentState, plan: TaskPlan) -> Dict[str, object]:
        failure_signature = self.build_failure_signature(state)
        build_failed = bool(state.last_build_result and state.last_build_result.status != "success")
        retrieval_weak = state.last_retrieval_confidence == "low" or bool(state.retrieval_blocker)
        return {
            "has_generated_files": bool(state.generated_files),
            "build_failed": build_failed,
            "review_failed": bool(state.review_feedback),
            "retrieval_weak": retrieval_weak,
            "failure_signature": failure_signature,
            "repeated_failure_count": state.repeated_failure_signatures.get(failure_signature, 0) if failure_signature else 0,
            "no_progress_streak": state.no_progress_streak,
            "next_action_index": state.next_action_index,
            "remaining_plan_actions": max(len(plan.execution_sequence) - state.next_action_index, 0),
        }

    def decide_next_action(self, state: AgentState, plan: TaskPlan, analysis: Dict[str, object]) -> Tuple[str, str]:
        if state.stop_reason:
            return "complete", state.stop_reason

        repeated_failure_count = self._safe_int(analysis.get("repeated_failure_count", 0), default=0)
        retrieval_weak = bool(analysis.get("retrieval_weak", False))
        has_generated_files = bool(analysis.get("has_generated_files", False))
        build_failed = bool(analysis.get("build_failed", False))
        review_failed = bool(analysis.get("review_failed", False))
        failure_signature = str(analysis.get("failure_signature", "")).strip()

        if self.is_backend_failure_signature(failure_signature):
            state.stop_reason = "Stopping because the local LLM backend failed; inspect Ollama service/model health before retrying."
            return "complete", state.stop_reason

        if state.no_progress_streak >= 2 and repeated_failure_count >= 2:
            state.stop_reason = "Stopping after repeated iterations with no measurable progress."
            return "complete", state.stop_reason

        if review_failed:
            if repeated_failure_count >= 2 or retrieval_weak:
                return "retrieve_more", "Reviewer keeps rejecting output; strengthen evidence and reuse past fixes before regenerating."
            return "generate", "Regenerate using reviewer feedback and relevant memory."

        if build_failed and state.last_error and plan.needs_fix_loop:
            if state.last_action == "fix" and repeated_failure_count >= 1:
                return "retrieve_more", "The same build failure survived a focused fix; switch strategy and pull stronger evidence before changing code again."
            if repeated_failure_count >= 2:
                return "retrieve_more", "Build failure repeated; retrieve more targeted evidence before patching again."
            return "fix", "Apply a focused fix for the current build error."

        if retrieval_weak and state.retrieval_attempts > 0 and not has_generated_files:
            if state.retrieval_block_streak >= 2:
                state.stop_reason = state.retrieval_blocker or "Stopping because retrieval remained weak after refinement."
                return "complete", state.stop_reason
            return "retrieve_more", "Evidence is weak; rewrite the query and pull more relevant context first."

        if not has_generated_files:
            return "generate", "No acceptable generated output exists yet."

        if plan.should_build and state.last_build_result is None:
            return "build", "Generated output must be build-validated before completion."

        if state.next_action_index >= len(plan.execution_sequence):
            return "complete", "Execution sequence completed."

        return plan.execution_sequence[state.next_action_index], "Following the planner sequence."

    def build_failure_signature(self, state: AgentState) -> str:
        candidates = [
            state.retrieval_blocker,
            state.review_feedback,
            str(state.last_error) if state.last_error else "",
            state.response_preview,
        ]
        for candidate in candidates:
            normalized = self.classify_failure_signature(candidate)
            if normalized:
                return normalized
        return ""

    def classify_failure_signature(self, text: str) -> str:
        raw_text = str(text).strip()
        lowered = raw_text.lower()
        if not lowered:
            return ""
        if "500 server error" in lowered or "internal server error" in lowered:
            if "ollama" in lowered or "/api/generate" in lowered or "/api/" in lowered:
                return "ollama backend http 500"
        if "connection error" in lowered or "cannot connect to ollama" in lowered:
            return "ollama backend connection failure"
        if "timed out after" in lowered and ("generate" in lowered or "review" in lowered or "chapter" in lowered or "fix" in lowered):
            return "ollama backend timeout"
        return self.normalize_failure_signature(raw_text)

    def is_backend_failure_signature(self, signature: str) -> bool:
        normalized = str(signature).strip().lower()
        return normalized.startswith("ollama backend")

    def normalize_failure_signature(self, text: str) -> str:
        tokens = re.findall(r"[a-z0-9_]+", str(text).lower())
        if not tokens:
            return ""
        filtered = [token for token in tokens if token not in GENERIC_QUERY_STOPWORDS][:16]
        return " ".join(filtered[:12])

    def record_iteration_trace(self, state: AgentState, action: str, reason: str, success: bool, observation: ActionObservation) -> None:
        failure_signature = self.build_failure_signature(state)
        state.last_failure_signature = failure_signature
        if failure_signature and (not success or not observation.success):
            state.repeated_failure_signatures[failure_signature] = state.repeated_failure_signatures.get(failure_signature, 0) + 1

        fingerprint = self.build_progress_fingerprint(state)
        if fingerprint and fingerprint == state.last_progress_fingerprint:
            state.no_progress_streak += 1
        else:
            state.no_progress_streak = 0
            state.last_progress_fingerprint = fingerprint

        state.iteration_history.append({
            "attempt": state.attempt,
            "action": action,
            "reason": reason,
            "success": success,
            "completed": observation.completed,
            "message": observation.message,
            "failure_signature": failure_signature,
            "retrieval_confidence": state.last_retrieval_confidence,
        })
        state.iteration_history = state.iteration_history[-20:]

    def build_progress_fingerprint(self, state: AgentState) -> str:
        parts = [
            ",".join(sorted(state.generated_files.keys())),
            self.normalize_failure_signature(state.review_feedback),
            self.normalize_failure_signature(str(state.last_error) if state.last_error else ""),
            state.last_retrieval_confidence,
            state.response_stage,
        ]
        return "|".join(parts)

    def observe_action(self, action: str, success: bool, state: AgentState, plan: TaskPlan, is_output_only_generation: Callable[[Iterable[str]], bool]) -> ActionObservation:
        if action == "complete":
            if state.stop_reason:
                state.status = "blocked" if "backend" in state.stop_reason.lower() or "retrieval" in state.stop_reason.lower() else "failed"
                return ActionObservation(success=False, completed=True, message=state.stop_reason)
            state.status = "success"
            return ActionObservation(success=True, completed=True, message=f"[OK] Task completed in {state.attempt} attempt(s)")

        if not success:
            if action == "retrieve_more":
                if state.retrieval_block_streak >= 2:
                    state.status = "blocked"
                    return ActionObservation(success=False, completed=True, message=state.retrieval_blocker or "retrieval remained weak")
                return ActionObservation(success=False, retry=True, message=state.retrieval_blocker or "retrieval weak")
            if action == "generate" and state.insufficient_documentation:
                state.status = "blocked"
                return ActionObservation(success=False, completed=True, message="INSUFFICIENT DOCUMENTATION")
            if action == "build" and state.last_build_result:
                build_result = state.last_build_result
                if build_result.errors:
                    state.last_error = build_result.errors[0]
                return ActionObservation(success=False, retry=True, message="build failed")
            if action == "flash" and state.last_flash_result:
                return ActionObservation(success=False, retry=True, message="flash failed")
            if action == "runtime_observe" and state.last_runtime_result:
                return ActionObservation(success=False, retry=True, message="runtime observe failed")
            return ActionObservation(success=False, retry=True, message=f"{action} failed")

        if action == "generate":
            state.last_error = None
            state.last_build_result = None
            state.review_feedback = ""
            state.review_preview = ""
            if state.generated_files and is_output_only_generation(state.generated_files.keys()) and not plan.should_build:
                state.status = "success"
                return ActionObservation(success=True, completed=True, message="[OK] Generated review-only files in output folder")
        if action == "fix":
            state.last_error = None

        if action == "runtime_observe" and state.last_runtime_diagnosis and state.last_runtime_diagnosis.status == "degraded":
            return ActionObservation(success=False, retry=True, message=state.last_runtime_diagnosis.summary or "runtime diagnosis degraded")

        if action in {"generate", "build", "flash", "runtime_observe"}:
            state.next_action_index += 1
        if action == "fix":
            build_index = plan.execution_sequence.index("build") if "build" in plan.execution_sequence else 0
            state.next_action_index = build_index
        if action == "retrieve_more":
            return ActionObservation(success=True, retry=True, message="retrieval refreshed")

        if state.next_action_index >= len(plan.execution_sequence):
            state.status = "success"
            completion_message = f"[OK] Task completed in {state.attempt} attempt(s)"
            if plan.should_observe_runtime:
                completion_message = f"[OK] Runtime loop completed in {state.attempt} attempt(s)"
            elif plan.should_flash:
                completion_message = f"[OK] Build and flash completed in {state.attempt} attempt(s)"
            return ActionObservation(success=True, completed=True, message=completion_message)

        return ActionObservation(success=True, retry=True, message=f"{action} complete")

    def build_final_result(self, state: AgentState, task_start: datetime, success: bool, message: str) -> TaskResult:
        return TaskResult(
            success=success,
            message=message,
            files_created=list(state.generated_files.keys()),
            errors_fixed=len(state.fixes_applied),
            attempts=state.attempt,
            duration=(datetime.now() - task_start).total_seconds(),
            learned_rules=self._derive_lessons(state, None, message if not success else ""),
        )

    def create_task_plan(self, task: str) -> TaskPlan:
        text = task.lower()
        query = self.query_analyzer.analyze(task)
        target_family, target_chip = self._infer_task_target(task, query)
        target_project = ""
        if "enginecar" in text:
            target_project = "EngineCar"
        elif "remotecontrol" in text or "remote control" in text:
            target_project = "RemoteControl"

        plan = TaskPlan(
            task=task,
            mode="codegen" if query.intent in {"codegen", "repair_codegen", "fix_build"} else "document_analysis",
            domain_profile=query.domain_profile,
            use_chapter_workers=self._should_use_chapter_workers(task),
            chapter_plan=self._select_chapter_plan(task),
            execution_sequence=["generate"],
            required_tools=["ollama"],
            allowed_outputs=self._default_allowed_outputs(task, query.domain_profile, target_family, target_chip),
            should_build=True,
            should_flash=False,
            should_observe_runtime=False,
            runtime_dry_run=True,
            should_review=True,
            needs_fix_loop=True,
            target_family=target_family,
            target_chip=target_chip,
            target_project=target_project,
        )

        # Only use review_only mode when explicitly generating review documents (not code for projects)
        # If task mentions a project target or codegen intent, use codegen mode instead
        has_project_target = "enginecar" in text or "remotecontrol" in text or "remote control" in text
        has_codegen_intent = any(k in text for k in ["generate", "create", "implement", "write code", "write driver"])

        if plan.allowed_outputs and all(path.startswith(f"{OUTPUT_GENERATED_ROOT}/") for path in plan.allowed_outputs):
            # Only use review_only if no project target AND no explicit codegen intent
            if not has_project_target and not has_codegen_intent:
                plan.mode = "review_only"
                plan.should_build = False
            else:
                # Override to codegen mode for project tasks
                plan.mode = "codegen"
                plan.should_build = True

        if query.intent == "document_analysis":
            plan.execution_sequence = ["generate"]
            plan.should_build = False
            plan.should_flash = False
            plan.should_observe_runtime = False
            plan.needs_fix_loop = False
            plan.should_review = False

        if "flash" in text or "program" in text:
            plan.mode = "flash"
            plan.should_build = True
            plan.should_flash = bool(plan.target_project)

        if "runtime" in text or "debug" in text or "test" in text or "monitor" in text or "rtt" in text:
            plan.mode = "runtime"
            plan.should_build = True
            plan.should_flash = bool(plan.target_project)
            plan.should_observe_runtime = True

        if "hardware" in text or "real board" in text or "actual board" in text:
            plan.runtime_dry_run = False

        if "fix" in text and "compilation" in text:
            plan.mode = "fix_build"
            plan.should_build = True

        if plan.should_build:
            plan.execution_sequence.append("build")
            if "build" not in plan.required_tools:
                plan.required_tools.append("build")
        if plan.should_flash:
            plan.execution_sequence.append("flash")
            if "flash" not in plan.required_tools:
                plan.required_tools.append("flash")
        if plan.should_observe_runtime:
            plan.execution_sequence.append("runtime_observe")
            if "runtime_observe" not in plan.required_tools:
                plan.required_tools.append("runtime_observe")

        return plan

    def plan_to_dict(self, plan: TaskPlan) -> Dict:
        return {
            "task": plan.task,
            "mode": plan.mode,
            "domain_profile": plan.domain_profile,
            "use_chapter_workers": plan.use_chapter_workers,
            "chapter_plan": list(plan.chapter_plan),
            "execution_sequence": list(plan.execution_sequence),
            "required_tools": list(plan.required_tools),
            "allowed_outputs": list(plan.allowed_outputs),
            "should_build": plan.should_build,
            "should_flash": plan.should_flash,
            "should_observe_runtime": plan.should_observe_runtime,
            "runtime_dry_run": plan.runtime_dry_run,
            "should_review": plan.should_review,
            "needs_fix_loop": plan.needs_fix_loop,
            "target_family": plan.target_family,
            "target_chip": plan.target_chip,
            "target_project": plan.target_project,
        }

    def get_task_plan(self, state: AgentState, task: str) -> TaskPlan:
        data = state.plan if isinstance(state.plan, dict) else {}
        domain_profile = str(data.get("domain_profile", "generic_document"))
        target_family = str(data.get("target_family", ""))
        target_chip = str(data.get("target_chip", ""))
        allowed_outputs = data.get(
            "allowed_outputs",
            self._default_allowed_outputs(task, domain_profile, target_family, target_chip),
        )
        return TaskPlan(
            task=task,
            mode=str(data.get("mode", "review_only")),
            domain_profile=domain_profile,
            use_chapter_workers=bool(data.get("use_chapter_workers", self._should_use_chapter_workers(task))),
            chapter_plan=list(data.get("chapter_plan", self._select_chapter_plan(task))),
            execution_sequence=list(data.get("execution_sequence", ["generate"])),
            required_tools=list(data.get("required_tools", ["ollama"])),
            allowed_outputs=self._normalize_allowed_outputs(allowed_outputs),
            should_build=bool(data.get("should_build", True)),
            should_flash=bool(data.get("should_flash", False)),
            should_observe_runtime=bool(data.get("should_observe_runtime", False)),
            runtime_dry_run=bool(data.get("runtime_dry_run", True)),
            should_review=bool(data.get("should_review", True)),
            needs_fix_loop=bool(data.get("needs_fix_loop", True)),
            target_family=target_family,
            target_chip=target_chip,
            target_project=str(data.get("target_project", "")),
        )

