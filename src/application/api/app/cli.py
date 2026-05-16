import argparse
import asyncio
import json
import sys
import threading
from datetime import datetime
from pathlib import Path

from src.core.memory.session_store import SessionStore, ChatSession, ChatTurn

"""AI Agent CLI - Private, minimal interface.

Only exposes:
  task "..."   # Execute task
  chat         # Interactive chat

All other capabilities are internal (memory, pdf, v2, etc.)
"""

MODEL_PROVIDER_MAP = {
    "ollama": "ollama", "openai": "openai", "anthropic": "anthropic", "gemini": "gemini",
    "llama": "ollama", "codellama": "ollama", "mistral": "ollama", "phi": "ollama",
    "qwen": "ollama", "deepseek": "ollama", "gemma": "ollama", "starcoder": "ollama",
    "wizardcoder": "ollama", "nous-hermes": "ollama", "mixtral": "ollama",
    "llama2": "ollama", "llama3": "ollama", "gpt": "openai", "claude": "anthropic",
}


def get_provider_for_model(model_name: str) -> str:
    if not model_name:
        return "ollama"
    if model_name.lower() in MODEL_PROVIDER_MAP:
        return MODEL_PROVIDER_MAP[model_name.lower()]
    for prefix, provider in MODEL_PROVIDER_MAP.items():
        if model_name.lower().startswith(prefix):
            return provider
    return "ollama"


def resolve_project_root(project: str) -> Path:
    root = Path(project).resolve()
    if root.name == "AI_support" and (root.parent / "AI_support").is_dir():
        return root.parent
    return root


# =============================================================================
# Task Handler
# =============================================================================

def print_task_result(result) -> None:
    print("\n" + "=" * 60)
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Message: {result.message}")
    print(f"Attempts: {result.attempts}")
    print(f"Duration: {result.duration:.1f}s")
    if result.files_created:
        print(f"Files: {', '.join(result.files_created)}")
    if result.learned_rules:
        print("Learned:")
        for i, rule in enumerate(result.learned_rules, 1):
            print(f"  {i}. {rule}")
    print("=" * 60)


async def handle_task(args, agent_factory) -> int:
    """Handle 'task' command - unified execution."""
    agent = agent_factory(project_root=args.project, model=args.model)

    # INTERACTIVE PLAN MODE
    if args.plan:
        plan_agent = agent.plan_mode_agent
        should_execute, refined_task = await plan_agent.chat_about_plan(
            args.description, max_turns=10
        )
        
        if not should_execute:
            print("Plan cancelled.")
            return 0
        
        print(f"\n[EXECUTE] Using refined task: {refined_task}")
        args.description = refined_task

    # AUTO PLAN MODE / EXECUTE
    if args.plan_mode or args.execute:
        print("\n[EXECUTE MODE] Using automatic task classification and model switching")
        print(f"[EXECUTE MODE] Force model: {args.force_model or 'auto'}")
        
        plan_agent = agent.plan_mode_agent
        if args.force_model:
            plan_agent.router._select_model = lambda task_type, prompt: args.force_model
        result = await plan_agent.execute_task(args.description)
        
    # STREAM MODE
    elif args.stream:
        from src.infrastructure.llm import StreamProgressCallback
        print(f"\n[STREAM] Model: {agent.llm.model} | Streaming enabled\n")
        
        progress = StreamProgressCallback(prefix="[STREAM]", show_progress=False)
        try:
            full_response = []
            async for token in agent.model_router.generate_streaming(
                args.description,
                force_model=args.force_model or "ollama",
                progress_callback=progress,
            ):
                print(token, end="", flush=True)
                full_response.append(token)
            print()
            result = agent.plan_mode_agent._build_result()
            result.success = True
            result.message = "".join(full_response)
        except Exception as exc:
            print(f"\n[ERROR] Streaming failed: {exc}")
            result = await agent.execute_task(args.description)
    
    # DEFAULT EXECUTION
    else:
        result = await agent.execute_task(args.description)

    print_task_result(result)
    return 0 if result.success else 1


# =============================================================================
# Chat Handler
# =============================================================================

async def _run_chat(project: str, model: str, system_override: str):
    from src.application.api.app.embedded_agent import EmbeddedCAgent
    from src.core.tools.file_tools import FileTools
    from src.core.tools.tool_registry import ToolRegistry, _make_tools
    from src.core.tools.tool_executor import ToolExecutor
    from src.core.tools.context_provider import ContextProvider

    agent = EmbeddedCAgent(project_root=project, model=model, bootstrap_rag=False)
    file_tools = FileTools(project_root=project)
    ctx_provider = ContextProvider(project_root=str(agent.project_root))

    registry = ToolRegistry()
    registry.register(_make_tools(file_tools, agent.build_tools, agent.project_root))
    tools_schema = registry.get_schemas()

    print("=" * 60)
    print("AI Agent Chat  —  type 'exit' or 'quit' to stop")
    print("                  type '/model <name>' to switch provider")
    print("                  type '/stream' to toggle streaming")
    print("                  type '/auto' to toggle auto model")
    print("                  type '/save' to save session")
    print("=" * 60)

    session_store = SessionStore(project_root=project)
    history = []
    active_provider = get_provider_for_model(model)
    _stream_mode = False
    _auto_model = True

    base_system = "You are an expert embedded C firmware engineer."
    if system_override:
        base_system = system_override

    def _gather_context() -> str:
        return ctx_provider.gather_full_context()

    def _detect_intent(text: str) -> str:
        text_lower = text.lower()
        if any(kw in text_lower for kw in ["debug", "crash", "error", "fail", "fix"]):
            return "debug"
        if any(kw in text_lower for kw in ["analyze", "review", "explain"]):
            return "analyze"
        if any(kw in text_lower for kw in ["generate", "create", "write", "implement"]):
            return "generate"
        return "general"

    def _auto_select_model(task_type: str, prompt: str) -> str:
        intent = _detect_intent(prompt)
        if intent == "debug":
            return "claude-sonnet-4-20250514"
        elif intent == "generate":
            return "gpt-4o"
        return "ollama"

    if _auto_model:
        agent.model_router._select_model = _auto_select_model

    async def _llm_generate(prompt_text: str, use_tools: bool = False) -> str:
        if use_tools and tools_schema:
            return await agent.model_router.generate_with_fallback(
                prompt_text, primary=active_provider, tools=tools_schema
            )
        return await agent.model_router.generate_with_fallback(prompt_text, primary=active_provider)

    while True:
        try:
            prompt = input("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n[EXIT]")
            break

        if prompt.lower() in ["exit", "quit"]:
            break

        if prompt.startswith("/model "):
            new_model = prompt[7:].strip()
            active_provider = get_provider_for_model(new_model)
            print(f"[MODEL] Switched to provider: {active_provider}")
            continue

        if prompt == "/stream":
            _stream_mode = not _stream_mode
            print(f"[STREAM] {'ON' if _stream_mode else 'OFF'}")
            continue

        if prompt == "/auto":
            _auto_model = not _auto_model
            if _auto_model:
                agent.model_router._select_model = _auto_select_model
            print(f"[AUTO MODEL] {'ON' if _auto_model else 'OFF'}")
            continue

        if prompt == "/save":
            turns = [ChatTurn(role=m["role"], content=m["content"]) for m in history]
            session = ChatSession(
                id=f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                turns=turns,
                metadata={"project": project, "model": model},
            )
            session_store.save_session(session)
            print(f"[SAVED] Session: {session.id}")
            continue

        if not prompt:
            continue

        context = _gather_context()
        full_prompt = f"{base_system}\n\n# Context\n{context}\n\n# Task\n{prompt}"

        try:
            history.append({"role": "user", "content": prompt})

            if _stream_mode:
                print("\nAI: ", end="", flush=True)
                tokens = []
                async for token in agent.model_router.generate_streaming(full_prompt, force_model=active_provider):
                    print(token, end="", flush=True)
                    tokens.append(token)
                response = "".join(tokens)
            else:
                response = await _llm_generate(full_prompt, use_tools=True)
                print(response, flush=True)

            executor = ToolExecutor(registry)
            for _ in range(2):
                calls = executor.parse_tool_calls(response)
                if not calls:
                    break
                print(f"\n[TOOL] {len(calls)} call(s) detected")
                confirm = input("Execute? [Y/n]: ").strip().lower()
                if confirm == "n":
                    break
                response, results = await executor.execute_all(response)
                print(f"[TOOL] {len(results)} result(s)")
                response = await _llm_generate(f"{full_prompt}\n\nAssistant: {response}\n{executor.format_for_llm(results)}\n\nFinal answer.", use_tools=False)
                print(response, flush=True)

            history.append({"role": "assistant", "content": response})
        except Exception as exc:
            print(f"[Error: {exc}]")


# =============================================================================
# Autonomous Handler
# =============================================================================

async def handle_autonomous(args, agent_factory) -> int:
    """Handle 'autonomous' command - AI controls entire development loop."""
    from src.core.agent.autonomous_loop import run_autonomous_task, LoopConfig

    agent = agent_factory(project_root=args.project, model=args.model)

    # Build config from args
    config = LoopConfig(
        max_retries=args.max_retries,
        build_timeout=args.build_timeout,
        flash_timeout=args.flash_timeout,
        read_timeout=args.read_timeout,
        read_duration=args.read_duration,
        serial_port=args.serial_port,
        serial_baudrate=args.baudrate,
        auto_reset_on_crash=not args.no_auto_reset,
        pause_on_max_retries=True,
        verbose=True,
    )

    print("\n" + "=" * 60)
    print("AUTONOMOUS MODE - AI Controls Development")
    print("=" * 60)
    print(f"Task: {args.description}")
    print(f"Project: {args.project_name}")
    print(f"Max retries: {config.max_retries}")
    print(f"Serial: {config.serial_port} @ {config.serial_baudrate} baud")
    print("=" * 60)
    print()

    if not args.yes:
        confirm = input("Start autonomous loop? [y/N]: ").strip().lower()
        if confirm not in ("y", "yes"):
            print("Cancelled.")
            return 0

    print("[INFO] Starting autonomous development loop...")
    print("[INFO] AI will: generate code -> build -> flash -> read serial -> analyze -> fix")
    print()

    result = await run_autonomous_task(
        agent=agent,
        task=args.description,
        project=args.project_name,
        config=config,
        verbose=True,
    )

    # Print result
    print()
    print("=" * 60)
    print("AUTONOMOUS LOOP RESULT")
    print("=" * 60)
    print(f"Status: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Final State: {result.final_state.value}")
    print(f"Total Attempts: {result.total_attempts}")
    print(f"Total Duration: {result.total_duration:.1f}s")
    print(f"Steps Completed: {len(result.steps)}")
    print(f"Errors Detected: {len(result.errors)}")

    if result.errors:
        print()
        print("Errors:")
        for i, error in enumerate(result.errors, 1):
            print(f"  {i}. [{error.severity.value}] {error.message}")

    print()
    print("Step History:")
    for step in result.steps:
        status = "OK" if step.success else "FAIL"
        print(f"  [{status}] {step.step}: {step.message[:50]} ({step.duration:.1f}s)")

    print("=" * 60)

    return 0 if result.success else 1


# =============================================================================
# Main CLI Entry
# =============================================================================

async def run_cli(agent_factory):
    parser = argparse.ArgumentParser(description="AI Agent - Embedded C Engineering Assistant")
    parser.add_argument("--project", default=".", help="Project root")
    parser.add_argument("--model", default="llama3.1:latest", help="Model")

    subparsers = parser.add_subparsers(dest="command")

    # TASK
    p = subparsers.add_parser("task", help="Execute task")
    p.add_argument("description", nargs="?", default="", help="Task description")
    p.add_argument("--plan", action="store_true", help="Interactive plan mode")
    p.add_argument("--plan-mode", action="store_true", help="Auto model switching")
    p.add_argument("--execute", action="store_true", help="Execute immediately")
    p.add_argument("--stream", action="store_true", help="Stream output")
    p.add_argument("--force-model", default="", choices=["ollama", "openai", ""])

    # CHAT
    p = subparsers.add_parser("chat", help="Interactive chat")
    p.add_argument("--system", default="")

    # AUTONOMOUS
    p = subparsers.add_parser("autonomous", help="AI-controlled autonomous development")
    p.add_argument("description", nargs="?", default="", help="Task/requirement description")
    p.add_argument("--project-name", default="EngineCar", choices=["EngineCar", "RemoteControl"],
                   help="Project to flash (default: EngineCar)")
    p.add_argument("--max-retries", type=int, default=5,
                   help="Max retry attempts (default: 5)")
    p.add_argument("--build-timeout", type=int, default=180,
                   help="Build timeout in seconds (default: 180)")
    p.add_argument("--flash-timeout", type=int, default=120,
                   help="Flash timeout in seconds (default: 120)")
    p.add_argument("--read-timeout", type=int, default=10,
                   help="Serial read timeout in seconds (default: 10)")
    p.add_argument("--read-duration", type=float, default=3.0,
                   help="Serial read duration in seconds (default: 3.0)")
    p.add_argument("--serial-port", default="auto",
                   help="Serial port (default: auto-detect)")
    p.add_argument("--baudrate", type=int, default=115200,
                   help="Baudrate (default: 115200)")
    p.add_argument("--no-auto-reset", action="store_true",
                   help="Disable auto-reset on crash")
    p.add_argument("--yes", "-y", action="store_true",
                   help="Skip confirmation prompt")

    args = parser.parse_args()
    args.project = str(resolve_project_root(args.project))

    if not args.command:
        parser.print_help()
        return

    if args.command == "task":
        sys.exit(await handle_task(args, agent_factory))
    elif args.command == "chat":
        chat_thread = threading.Thread(
            target=_run_chat,
            args=(args.project, args.model, args.system or ""),
            daemon=True
        )
        chat_thread.start()
        chat_thread.join()
        sys.exit(0)
    elif args.command == "autonomous":
        if not args.description:
            print("Error: autonomous command requires a task description")
            print("Usage: python -m src.application.api.app.embedded_agent autonomous \"Your task here\"")
            sys.exit(1)
        sys.exit(await handle_autonomous(args, agent_factory))
    else:
        parser.print_help()
        sys.exit(1)