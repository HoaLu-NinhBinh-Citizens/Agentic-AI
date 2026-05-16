import asyncio

from src.agent.core import AgentCore
from src.agent.planner import AgentPlanner
from src.models.build import BuildError, BuildResult
from src.models import ActionObservation, AgentState, TaskPlan, TaskResult


class StubQueryAnalyzer:
    def analyze(self, task):
        raise NotImplementedError()


def make_planner():
    return AgentPlanner(
        query_analyzer=StubQueryAnalyzer(),
        infer_task_target=lambda task, query: ("", ""),
        should_use_chapter_workers=lambda task: False,
        select_chapter_plan=lambda task: [],
        default_allowed_outputs=lambda task, profile, family, chip: [],
        normalize_allowed_outputs=lambda outputs: list(outputs),
        derive_lessons=lambda state, result, message: [],
        safe_int=lambda value, default=0: int(value) if str(value).strip() else default,
    )


def make_plan(**overrides):
    base = TaskPlan(task="Generate UART driver", execution_sequence=["generate", "build"], should_build=True)
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_planner_stops_after_repeated_no_progress():
    planner = make_planner()
    state = AgentState(
        task="task",
        no_progress_streak=2,
        repeated_failure_signatures={"same failure": 2},
        review_feedback="same failure",
    )
    plan = make_plan()

    analysis = planner.analyze_iteration_state(state, plan)
    action, reason = planner.decide_next_action(state, plan, analysis)

    assert action == "complete"
    assert "no measurable progress" in reason
    assert state.stop_reason == reason


def test_planner_requests_retrieval_after_repeated_fix_failure():
    planner = make_planner()
    state = AgentState(
        task="task",
        last_action="fix",
        last_error=BuildError(file="main.c", line=1, column=1, message="build broke"),
        last_build_result=BuildResult(status="failed", returncode=1, stdout="", stderr="", errors=[]),
        response_preview="build broke",
    )
    state.repeated_failure_signatures = {planner.build_failure_signature(state): 1}
    plan = make_plan(needs_fix_loop=True)

    analysis = planner.analyze_iteration_state(state, plan)
    action, reason = planner.decide_next_action(state, plan, analysis)

    assert action == "retrieve_more"
    assert "switch strategy" in reason


def test_planner_marks_output_only_generation_complete():
    planner = make_planner()
    state = AgentState(
        task="task",
        generated_files={"AI_support/outputs/report.json": "{}"},
    )
    plan = make_plan(should_build=False)

    observation = planner.observe_action(
        "generate",
        True,
        state,
        plan,
        is_output_only_generation=lambda paths: True,
    )

    assert observation.completed is True
    assert observation.success is True
    assert state.status == "success"


def test_agent_core_returns_final_result_on_completion():
    plan = make_plan()
    recorded = {"experience": None, "trace": []}

    async def execute_action(action, task, state, current_plan):
        assert action == "generate"
        return True

    async def observe_action(action, success, state, current_plan):
        return ActionObservation(success=True, completed=True, message="done")

    def build_final_result(state, task_start, success, message):
        return TaskResult(success=success, message=message, attempts=state.attempt)

    core = AgentCore(
        create_task_plan=lambda task: plan,
        plan_to_dict=lambda current_plan: {"mode": current_plan.mode},
        analyze_iteration_state=lambda state, current_plan: {"phase": "start"},
        log_agent_phase=lambda phase, message: None,
        decide_next_action=lambda state, current_plan, analysis: ("generate", "initial generation"),
        execute_action=execute_action,
        observe_action=observe_action,
        record_iteration_trace=lambda state, action, reason, success, observation: recorded["trace"].append((action, success, observation.message)),
        build_final_result=build_final_result,
        record_experience=lambda state, result: recorded.__setitem__("experience", result),
    )

    result = asyncio.run(core.execute_task("Generate UART driver"))

    assert result.success is True
    assert result.message == "done"
    assert result.attempts == 1
    assert recorded["trace"] == [("generate", True, "done")]
    assert recorded["experience"] == result


def test_agent_core_converts_exception_into_failed_result():
    plan = make_plan()
    recorded = {"experience": None}

    async def execute_action(action, task, state, current_plan):
        raise RuntimeError("boom")

    async def observe_action(action, success, state, current_plan):
        raise AssertionError("observe_action should not run after execute_action failure")

    def build_final_result(state, task_start, success, message):
        return TaskResult(success=success, message=message, attempts=state.attempt)

    core = AgentCore(
        create_task_plan=lambda task: plan,
        plan_to_dict=lambda current_plan: {"mode": current_plan.mode},
        analyze_iteration_state=lambda state, current_plan: {},
        log_agent_phase=lambda phase, message: None,
        decide_next_action=lambda state, current_plan, analysis: ("generate", "initial generation"),
        execute_action=execute_action,
        observe_action=observe_action,
        record_iteration_trace=lambda state, action, reason, success, observation: None,
        build_final_result=build_final_result,
        record_experience=lambda state, result: recorded.__setitem__("experience", result),
    )

    result = asyncio.run(core.execute_task("Generate UART driver"))

    assert result.success is False
    assert result.attempts == 1
    assert result.message == "Error: boom"
    assert recorded["experience"] == result