import logging
from datetime import datetime
from typing import Awaitable, Callable, Dict, Tuple

from src.infrastructure.models import ActionObservation, AgentState, TaskPlan, TaskResult

logger = logging.getLogger(__name__)


class AgentCore:
    def __init__(
        self,
        create_task_plan: Callable[[str], TaskPlan],
        plan_to_dict: Callable[[TaskPlan], Dict],
        analyze_iteration_state: Callable[[AgentState, TaskPlan], Dict[str, object]],
        log_agent_phase: Callable[[str, str], None],
        decide_next_action: Callable[[AgentState, TaskPlan, Dict[str, object]], Tuple[str, str]],
        execute_action: Callable[[str, str, AgentState, TaskPlan], Awaitable[bool]],
        observe_action: Callable[[str, bool, AgentState, TaskPlan], Awaitable[ActionObservation]],
        record_iteration_trace: Callable[[AgentState, str, str, bool, ActionObservation], None],
        build_final_result: Callable[[AgentState, datetime, bool, str], TaskResult],
        record_experience: Callable[[AgentState, TaskResult], None],
    ):
        self._create_task_plan = create_task_plan
        self._plan_to_dict = plan_to_dict
        self._analyze_iteration_state = analyze_iteration_state
        self._log_agent_phase = log_agent_phase
        self._decide_next_action = decide_next_action
        self._execute_action = execute_action
        self._observe_action = observe_action
        self._record_iteration_trace = record_iteration_trace
        self._build_final_result = build_final_result
        self._record_experience = record_experience

    async def execute_task(self, task: str) -> TaskResult:
        logger.info(f"Task: {task}")
        plan = self._create_task_plan(task)
        logger.info(
            "[OK] Plan: mode=%s, chapter_workers=%s, build=%s, review=%s, actions=%s, chapters=%s",
            plan.mode,
            plan.use_chapter_workers,
            plan.should_build,
            plan.should_review,
            "->".join(plan.execution_sequence) if plan.execution_sequence else "none",
            ",".join(plan.chapter_plan) if plan.chapter_plan else "none",
        )
        state = AgentState(task=task, plan=self._plan_to_dict(plan))
        task_start = datetime.now()

        try:
            while state.attempt < state.max_attempts:
                state.attempt += 1
                logger.info(f"\n[Attempt {state.attempt}/{state.max_attempts}]")
                analysis = self._analyze_iteration_state(state, plan)
                self._log_agent_phase("think", f"State analysis: {analysis}")
                action, reason = self._decide_next_action(state, plan, analysis)
                state.last_action = action
                state.last_action_reason = reason
                self._log_agent_phase("act", f"Selected action: {action} | reason: {reason}")
                success = await self._execute_action(action, task, state, plan)
                self._log_agent_phase("observe", f"Action {action} returned success={success}")
                observation = await self._observe_action(action, success, state, plan)
                self._record_iteration_trace(state, action, reason, success, observation)
                self._log_agent_phase("observe", f"Planner decision after {action}: completed={observation.completed}, retry={observation.retry}, message={observation.message}")
                if observation.completed:
                    result = self._build_final_result(state, task_start, observation.success, observation.message)
                    self._record_experience(state, result)
                    return result
                if observation.retry:
                    continue

            result = self._build_final_result(
                state,
                task_start,
                False,
                f"Failed after {state.max_attempts} attempts",
            )
            self._record_experience(state, result)
            return result

        except Exception as exc:
            logger.error(f"Task error: {exc}")
            result = self._build_final_result(
                state,
                task_start,
                False,
                f"Error: {exc}",
            )
            self._record_experience(state, result)
            return result