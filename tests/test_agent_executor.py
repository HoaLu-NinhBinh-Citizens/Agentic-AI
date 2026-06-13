import asyncio

from src.core.agent.executor import AgentExecutor
from src.infrastructure.models import AgentState, TaskPlan
from src.infrastructure.models.build import RuntimeDiagnosis, ToolResult


class StubBuildTools:
    def __init__(self, runtime_result, debug_result):
        self.runtime_result = runtime_result
        self.debug_result = debug_result
        self.runtime_calls = []
        self.auto_debug_calls = []

    async def run_runtime_observe(self, dry_run=True):
        self.runtime_calls.append(dry_run)
        return self.runtime_result

    async def run_auto_debug(self, target_project):
        self.auto_debug_calls.append(target_project)
        return self.debug_result


def make_executor(build_tools, diagnose_runtime_output):
    async def review_generated_outputs(*args, **kwargs):
        return True, ""

    async def guarded_llm_generate(*args, **kwargs):
        return ""

    return AgentExecutor(
        build_tools=build_tools,
        file_tools=object(),
        evidence_builder=object(),
        parse_and_write_code=lambda *args, **kwargs: None,
        review_generated_outputs=review_generated_outputs,
        ensure_retrieval_confidence=lambda *args, **kwargs: object(),
        collect_reference_hints=lambda *args, **kwargs: {},
        format_retrieved_context_block=lambda evidence: "",
        format_memory_context_block=lambda evidence: "",
        build_document_understanding=lambda task, evidence: [],
        format_reference_hint_block=lambda hints: "",
        guarded_llm_generate=guarded_llm_generate,
        capture_llm_preview=lambda state, stage, response: None,
        normalize_allowed_outputs=lambda outputs: list(outputs),
        get_task_plan=lambda state, task: TaskPlan(task=task),
        parse_code=lambda response: None,
        preview_text=lambda text, limit: text[:limit],
        diagnose_runtime_output=diagnose_runtime_output,
        is_vendor_managed_path=lambda path: False,
        is_output_only_generation=lambda paths: False,
    )


def test_runtime_observe_launches_auto_debug_on_hardfault():
    runtime_result = ToolResult(status="success", returncode=0, stdout="HardFault detected", stderr="")
    debug_result = ToolResult(status="success", returncode=0, stdout="backtrace line", stderr="")
    captured = {}
    build_tools = StubBuildTools(runtime_result, debug_result)
    executor = make_executor(
        build_tools,
        diagnose_runtime_output=lambda result, plan: captured.setdefault(
            "diagnosis",
            RuntimeDiagnosis(status="degraded", warnings=[result.stdout]),
        ),
    )
    state = AgentState(task="Observe runtime")
    plan = TaskPlan(task="Observe runtime", target_project="EngineCar", runtime_dry_run=False)

    success = asyncio.run(executor.execute_action("runtime_observe", state.task, state, plan))

    assert success is True
    assert build_tools.runtime_calls == [False]
    assert build_tools.auto_debug_calls == ["EngineCar"]
    assert "GDB AUTO DEBUGGER" in state.last_runtime_result.stdout
    assert "backtrace line" in state.last_runtime_result.stdout
    assert state.last_runtime_diagnosis is captured["diagnosis"]


def test_flash_requires_known_target_project():
    runtime_result = ToolResult(status="success", returncode=0, stdout="", stderr="")
    debug_result = ToolResult(status="success", returncode=0, stdout="", stderr="")
    executor = make_executor(
        StubBuildTools(runtime_result, debug_result),
        diagnose_runtime_output=lambda result, plan: RuntimeDiagnosis(status="ok"),
    )
    state = AgentState(task="Flash firmware")
    plan = TaskPlan(task="Flash firmware", should_flash=True)

    try:
        asyncio.run(executor.execute_action("flash", state.task, state, plan))
    except ValueError as exc:
        assert "target project is unknown" in str(exc)
    else:
        raise AssertionError("flash without target project should fail fast")