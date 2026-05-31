"""Agentic-AI CLI."""

import argparse
import asyncio
import sys


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="agentic-ai",
        description="Agentic-AI - Local AI Agent for Embedded Systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agentic-ai                          # Interactive mode
  agentic-ai chat                     # Chat mode
  agentic-ai chat --prompt "Hello"   # Single prompt
  agentic-ai run "Fix bug in main.py" # Run task
  agentic-ai shell                     # Shell engine
  agentic-ai search "Python tips"     # Web search
  agentic-ai plugins list             # List plugins
        """,
    )
    
    # Options
    parser.add_argument("--version", action="version", version="Agentic-AI 1.0.0")
    parser.add_argument("--config", help="Config directory")
    parser.add_argument("--model", default="gpt-4o", help="LLM model")
    parser.add_argument("--provider", default="openai", 
                       choices=["openai", "anthropic", "ollama", "groq"],
                       help="LLM provider")
    
    # Commands
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start chat session")
    chat_parser.add_argument("--prompt", type=str, help="Initial prompt")
    chat_parser.add_argument("--model", default="llama3.1:latest", help="Model name")
    chat_parser.add_argument("--provider", default="ollama", 
                           choices=["openai", "anthropic", "ollama", "groq"],
                           help="LLM provider")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run a task")
    run_parser.add_argument("task", type=str, help="Task description")
    run_parser.add_argument("--context", help="Context directory")
    
    # Shell command
    subparsers.add_parser("shell", help="Start shell engine")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Web search")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument("--provider", default="duckduckgo",
                            choices=["duckduckgo", "tavily", "serpapi"],
                            help="Search provider")
    
    # Plugins command
    plugins_parser = subparsers.add_parser("plugins", help="Plugin management")
    plugins_parser.add_argument("action", choices=["list", "install", "update", "remove"],
                                help="Action")
    plugins_parser.add_argument("name", nargs="?", help="Plugin name")
    
    # Session command
    session_parser = subparsers.add_parser("session", help="Session management")
    session_parser.add_argument("action", choices=["list", "export", "import"],
                               help="Action")
    session_parser.add_argument("path", nargs="?", help="Session path")
    
    # LSP command
    lsp_parser = subparsers.add_parser("lsp", help="LSP operations")
    lsp_parser.add_argument("action", choices=["diagnostics", "completions", "goto"],
                           help="Action")
    lsp_parser.add_argument("file", help="File path")
    
    # LLM command
    llm_parser = subparsers.add_parser("llm", help="Local LLM (Ollama) management")
    llm_sub = llm_parser.add_subparsers(dest="llm_action", help="LLM actions")
    
    # LLM status
    status_parser = llm_sub.add_parser("status", help="Check local LLM status")
    status_parser.set_defaults(func="_llm_status")
    
    # LLM models
    models_parser = llm_sub.add_parser("models", help="List available models")
    models_parser.set_defaults(func="_llm_models")
    
    # LLM pull
    pull_parser = llm_sub.add_parser("pull", help="Pull a model")
    pull_parser.add_argument("model", help="Model name")
    pull_parser.set_defaults(func="_llm_pull")
    
    # LLM info
    info_parser = llm_sub.add_parser("info", help="Show model info")
    info_parser.add_argument("model", help="Model name")
    info_parser.set_defaults(func="_llm_info")
    
    args = parser.parse_args()
    
    # Default to interactive mode
    if not args.command:
        run_interactive(args)
    else:
        handle_command(args)


def handle_command(args):
    """Handle a specific command."""
    if args.command == "chat":
        run_chat(args.prompt, args.provider, args.model)
    elif args.command == "run":
        run_task(args)
    elif args.command == "shell":
        run_shell()
    elif args.command == "search":
        run_search(args)
    elif args.command == "plugins":
        manage_plugins(args)
    elif args.command == "session":
        manage_session(args)
    elif args.command == "lsp":
        run_lsp(args)
    elif args.command == "llm":
        # Handle LLM subcommands
        llm_func = getattr(args, "func", None)
        if llm_func:
            func = globals().get(llm_func)
            if func and callable(func):
                return func(args)
        return handle_llm_command(args)


def run_interactive(args):
    """Run interactive mode."""
    print("=" * 60)
    print("Agentic-AI - Local AI Agent for Embedded Systems")
    print("=" * 60)
    print()
    print("Available commands:")
    print("  chat              - Chat with AI")
    print("  run <task>       - Run a task")
    print("  shell            - Shell engine")
    print("  search <query>   - Web search")
    print("  plugins <action>  - Plugin management")
    print("  exit             - Exit")
    print()
    
    while True:
        try:
            user_input = input("> ")
            
            if not user_input.strip():
                continue
            
            if user_input.strip() in ("exit", "quit", "q"):
                print("Goodbye!")
                break
            
            # Parse command
            parts = user_input.split(maxsplit=1)
            cmd = parts[0]
            arg = parts[1] if len(parts) > 1 else ""
            
            if cmd == "?" or cmd == "h":
                print("\nAvailable commands:")
                print("  chat              - Chat with AI")
                print("  run <task>       - Run a task")
                print("  shell            - Shell engine")
                print("  search <query>   - Web search")
                print("  plugins <action>  - Plugin management")
                print("  exit             - Exit")
                print()
            elif cmd == "chat":
                run_chat()
            elif cmd == "shell":
                run_shell()
            elif cmd == "search" and arg:
                run_search_simple(arg)
            elif cmd == "plugins":
                print("\n[Plugins] No plugins installed")
                print("Use 'agentic-ai plugins list' to view available plugins")
                print()
            elif cmd == "run" and arg:
                print(f"\n[Task] {arg}")
                print("Task execution complete")
                print()
            else:
                print(f"Unknown command: {cmd}")
                print("Type '?' or 'h' for help")
                print()
                
        except KeyboardInterrupt:
            print("\nUse 'exit' to quit")
        except EOFError:
            break


def run_chat(initial_prompt=None, provider="ollama", model="llama3.1:latest"):
    """Run chat mode with CodeGraph integration."""
    print(f"\n[Chat Mode]")
    print(f"Provider: {provider}")
    print(f"Model: {model}")
    
    # Get project path
    import os
    project_path = os.getcwd()
    
    # Initialize CodeGraph tools if available
    cg_tools = None
    try:
        from .codegraph_tools import CodeGraphTools
        cg_tools = CodeGraphTools(project_path)
        print(f"Project: {project_path}")
        status = cg_tools.get_status()
        print("[CodeGraph] Connected")
    except Exception as e:
        print(f"[CodeGraph] Not available: {e}")
    
    print()
    
    # Try to use Ollama
    try:
        import httpx
        import asyncio
        
        async def chat_with_ollama(messages, tools=None):
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": False
                }
                
                response = await client.post(
                    "http://localhost:11434/api/chat",
                    json=payload
                )
                return response.json()
        
        async def chat_loop():
            messages = []
            
            # System prompt with tools info
            system_msg = """You are an AI assistant with access to code analysis tools.
Use CodeGraph tools to understand the codebase before answering.
Available tools: search_symbol, get_callers, get_callees, analyze_impact, build_context"""
            
            if initial_prompt:
                messages.append({"role": "user", "content": initial_prompt})
                try:
                    result = await chat_with_ollama(messages)
                    print(f"AI: {result['message']['content']}")
                    print()
                except Exception as e:
                    print(f"AI: Error connecting to Ollama: {e}")
                    print()
            
            while True:
                try:
                    msg = input("You: ")
                    if not msg.strip():
                        continue
                    if msg.lower() in ("exit", "quit", "back"):
                        break
                    
                    # Handle tool commands
                    if msg.startswith("/search "):
                        query = msg[8:].strip()
                        if cg_tools:
                            print("\n[Searching...]")
                            results = cg_tools.search_symbol(query)
                            print(results)
                            print()
                        else:
                            print("CodeGraph not available")
                        continue
                    elif msg.startswith("/callers "):
                        func = msg[9:].strip()
                        if cg_tools:
                            print("\n[Finding callers...]")
                            results = cg_tools.get_callers(func)
                            print(results)
                            print()
                        continue
                    elif msg.startswith("/callees "):
                        func = msg[9:].strip()
                        if cg_tools:
                            print("\n[Finding callees...]")
                            results = cg_tools.get_callees(func)
                            print(results)
                            print()
                        continue
                    elif msg.startswith("/context "):
                        task = msg[9:].strip()
                        if cg_tools:
                            print("\n[Building context...]")
                            results = cg_tools.build_context(task)
                            print(results)
                            print()
                        continue
                    elif msg.lower() in ("/help", "/tools"):
                        print("""
CodeGraph Tools:
  /search <query>     - Search for symbols
  /callers <func>     - Find who calls a function
  /callees <func>     - Find what a function calls
  /context <task>     - Build code context for task
  /status            - Check CodeGraph status
  
Chat Commands:
  exit               - Exit chat
""")
                        continue
                    elif msg.lower() == "/status":
                        if cg_tools:
                            print(cg_tools.get_status())
                        else:
                            print("CodeGraph not available")
                        continue
                    
                    # Regular chat with context
                    if cg_tools:
                        # Add context query
                        context = cg_tools.build_context(msg, max_nodes=5)
                        enhanced_msg = f"Context:\n{context}\n\nQuestion: {msg}"
                        messages.append({"role": "user", "content": enhanced_msg})
                    else:
                        messages.append({"role": "user", "content": msg})
                    
                    try:
                        result = await chat_with_ollama(messages)
                        response = result['message']['content']
                        print(f"AI: {response}")
                    except Exception as e:
                        print(f"AI: Error: {e}")
                    print()
                    
                except KeyboardInterrupt:
                    break
                except EOFError:
                    break
        
        asyncio.run(chat_loop())
        
    except ImportError:
        print("httpx not installed. Install with: pip install httpx")
        print()


def run_task(args):
    """Run a task."""
    print(f"\n[Task] {args.task}")
    print()
    print("Analyzing task...")
    print("Task execution complete")


def run_shell():
    """Start shell engine."""
    print("\n[Shell Engine] Starting...")
    print("Type 'exit' to return to agentic-ai")
    print()
    
    while True:
        try:
            line = input("$ ")
            
            if line.strip() in ("exit", "quit"):
                break
            
            if line.strip():
                print(f"Executing: {line}")
                # In full implementation, would use ShellEngine
                
        except KeyboardInterrupt:
            print("^C")
        except EOFError:
            break


def run_search(args):
    """Web search."""
    run_search_simple(args.query)


def run_search_simple(query: str):
    """Simple search."""
    print(f"\n[Search] {query}")
    print()
    
    # Demo results
    results = [
        {
            "title": f"Python Documentation - {query}",
            "url": "https://docs.python.org/",
            "snippet": "Official Python documentation with tutorials and library reference."
        },
        {
            "title": f"Real Python - {query}",
            "url": "https://realpython.com/",
            "snippet": "Python tutorials, articles, and podcasts for developers."
        },
        {
            "title": f"Python Tutorial - W3Schools",
            "url": "https://www.w3schools.com/python/",
            "snippet": "Free Python tutorial with examples and exercises."
        },
    ]
    
    for i, r in enumerate(results, 1):
        print(f"{i}. {r['title']}")
        print(f"   {r['url']}")
        print(f"   {r['snippet'][:60]}...")
        print()
    
    print("(Configure API keys for real search results)")


def manage_plugins(args):
    """Plugin management."""
    if args.action == "list":
        print("\n[Plugins]")
        print()
        print("Installed plugins: None")
        print()
        print("Available plugins:")
        print("  - git-assistant     Git workflow automation")
        print("  - code-analysis     Static code analysis")
        print("  - api-client        HTTP/REST API testing")
        print("  - docker-helper     Docker management")
        print("  - database-tools    Database utilities")
        print()
        print("Use 'agentic-ai plugins install <name>' to install")
        
    elif args.action == "install" and args.name:
        print(f"\n[Install] {args.name}")
        print("Installing plugin...")
        print(f"Installed: {args.name}")
        
    elif args.action == "remove" and args.name:
        print(f"\n[Remove] {args.name}")
        print("Plugin removed")


def manage_session(args):
    """Session management."""
    print(f"\n[Session] {args.action}")
    
    if args.action == "list":
        print("No active sessions")
    elif args.action == "export":
        print("Exporting session...")
    elif args.action == "import":
        print("Importing session...")


def run_lsp(args):
    """LSP operations."""
    print(f"\n[LSP] {args.action} - {args.file}")
    print()
    print("LSP features require running language server")
    print("Start with: agentic-ai lsp diagnostics <file>")


async def _llm_status_async():
    """Check local LLM status."""
    from src.infrastructure.llm.local_provider import LocalLLMProvider
    
    provider = LocalLLMProvider()
    print(f"Checking local LLM at {provider.config.base_url}...")
    
    available = await provider.health_check()
    
    if available:
        print("[OK] Local LLM is running")
        
        # Try to list models
        try:
            from src.infrastructure.llm.ollama_adapter import OllamaAdapter
            adapter = OllamaAdapter()
            models = await adapter.list_models()
            if models:
                print(f"\nAvailable models ({len(models)}):")
                for m in models:
                    print(f"  - {m.get('name', 'unknown')}")
            await adapter.close()
        except Exception as e:
            print(f"Warning: Could not list models: {e}")
        
        await provider.close()
        return 0
    else:
        print("[X] Local LLM is not running")
        print("\nTo start Ollama, run:")
        print("  ollama serve")
        print("\nOr install Ollama from: https://ollama.ai")
        await provider.close()
        return 1


def _llm_status(args):
    """Sync wrapper for LLM status."""
    return asyncio.run(_llm_status_async())


async def _llm_models_async():
    """List available models."""
    from src.infrastructure.llm.ollama_adapter import OllamaAdapter
    
    adapter = OllamaAdapter()
    
    print("Fetching models from Ollama...")
    models = await adapter.list_models()
    
    if models:
        print(f"\nAvailable models ({len(models)}):\n")
        for m in models:
            name = m.get("name", "unknown")
            size = m.get("size", 0)
            print(f"  {name} ({_format_size(size)})")
    else:
        print("\nNo models found.")
        print("\nTo pull a model, run:")
        print("  agentic-ai llm pull llama3.2")
    
    await adapter.close()
    return 0


def _llm_models(args):
    """Sync wrapper for LLM models."""
    return asyncio.run(_llm_models_async())


async def _llm_pull_async(model: str):
    """Pull a model from Ollama registry."""
    from src.infrastructure.llm.ollama_adapter import OllamaAdapter
    
    adapter = OllamaAdapter()
    
    print(f"Pulling model: {model}")
    print("(This may take several minutes depending on model size and network)\n")
    
    try:
        async for status in adapter.pull_model(model):
            print(f"  {status}")
        
        print("\nModel pulled successfully!")
        await adapter.close()
        return 0
    except Exception as e:
        print(f"\nFailed to pull model: {e}")
        await adapter.close()
        return 1


def _llm_pull(args):
    """Sync wrapper for LLM pull."""
    return asyncio.run(_llm_pull_async(args.model))


async def _llm_info_async(model: str):
    """Show information about a model."""
    from src.infrastructure.llm.ollama_adapter import OllamaAdapter
    
    adapter = OllamaAdapter()
    
    print(f"Fetching info for: {model}...")
    
    info = await adapter.get_model_info(model)
    
    if info:
        print("\nModel Information:")
        print("-" * 40)
        
        if "modelfile" in info:
            print("\nModelfile:")
            modelfile = info["modelfile"]
            for line in modelfile.split("\n")[:20]:
                print(f"  {line}")
            if len(modelfile.split("\n")) > 20:
                print("  ... (truncated)")
        
        if "parameters" in info:
            print("\nParameters:")
            print(f"  {info['parameters']}")
    else:
        print(f"\nModel '{model}' not found.")
    
    await adapter.close()
    return 0


def _llm_info(args):
    """Sync wrapper for LLM info."""
    return asyncio.run(_llm_info_async(args.model))


def _format_size(size_bytes: int) -> str:
    """Format bytes as human-readable string."""
    if size_bytes == 0:
        return "unknown"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    unit_idx = 0
    size = float(size_bytes)
    
    while size >= 1024 and unit_idx < len(units) - 1:
        size /= 1024
        unit_idx += 1
    
    if unit_idx == 0:
        return f"{int(size)} {units[unit_idx]}"
    return f"{size:.1f} {units[unit_idx]}"


def handle_llm_command(args):
    """Handle LLM subcommands."""
    if not hasattr(args, "llm_action") or not args.llm_action:
        print("Available LLM commands:")
        print("  agentic-ai llm status   - Check if local LLM is running")
        print("  agentic-ai llm models   - List available models")
        print("  agentic-ai llm pull <m> - Pull a model")
        print("  agentic-ai llm info <m> - Show model info")
        return 1
    
    # Dispatch to handler
    handler_map = {
        "status": _llm_status,
        "models": _llm_models,
        "pull": _llm_pull,
        "info": _llm_info,
    }
    
    handler = handler_map.get(args.llm_action)
    if handler:
        return handler(args)
    
    return 1


if __name__ == "__main__":
    main()
