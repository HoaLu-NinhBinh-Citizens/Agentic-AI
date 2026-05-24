"""Agentic-AI CLI - Production coding agent CLI with TUI.

Inspired by oh-my-pi's terminal-first approach:
- Interactive REPL with TUI
- Session management
- Streaming responses
- Tool rendering
- LLM integration
- Rich formatting
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from src.infrastructure.tui import (
    Color,
    Theme,
    print_header,
    print_success,
    print_error,
    print_info,
    get_terminal_width,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class AgenticCLI:
    """Main CLI for Agentic-AI with TUI.
    
    Features:
    - Rich terminal formatting
    - Message history
    - Tool cards
    - Streaming responses
    - LLM integration
    """
    
    def __init__(self):
        self.session = None
        self.registry = None
        self.agent = None
        self.tui = None
        self.verbose = False
        self._setup_complete = False
    
    def _setup_tools(self):
        """Setup tool registry."""
        from src.infrastructure.tools.tool_registry import get_registry
        from src.infrastructure.tools.builtin.file_tools import register_file_tools
        from src.infrastructure.tools.builtin.search_tools import register_search_tools
        from src.infrastructure.tools.builtin.shell_tools import register_shell_tools
        from src.infrastructure.tools.builtin.code_tools import register_code_tools
        from src.infrastructure.tools.builtin.web_tools import register_web_tools
        
        registry = get_registry()
        
        # Register builtin tools
        register_file_tools(registry)
        register_search_tools(registry)
        register_shell_tools(registry)
        register_code_tools(registry)
        register_web_tools(registry)
        
        self.registry = registry
        return registry
    
    def _setup_session(self, project_path: Path | None = None):
        """Setup session."""
        from src.infrastructure.session.session_manager import (
            create_session,
        )
        
        if project_path is None:
            project_path = Path.cwd()
        
        session = create_session(project_path)
        self.session = session
        return session
    
    def _setup_tui(self):
        """Setup TUI."""
        from src.infrastructure.tui import AgenticTUI
        
        self.tui = AgenticTUI()
        return self.tui
    
    def _setup_llm(self):
        """Setup LLM client and agent."""
        from src.infrastructure.llm.client import (
            LLMClient,
            LLMConfig,
            Provider,
            configure_llm,
        )
        from src.infrastructure.agent.agent_loop import AgenticAgent, AgentConfig, AgentLoop
        
        # Determine provider from environment or default to Ollama
        provider_str = os.environ.get("AI_PROVIDER", "ollama").lower()
        provider = Provider(provider_str) if provider_str in ["ollama", "openai", "anthropic", "groq", "gemini"] else Provider.OLLAMA
        
        # Build config from environment
        llm_config = LLMConfig(
            provider=provider,
            model=os.environ.get("AI_MODEL", "qwen2.5-coder:7b"),
            base_url=os.environ.get("AI_BASE_URL", "http://localhost:11434"),
            api_key=os.environ.get("AI_API_KEY"),
            temperature=0.1,
            max_tokens=4096,
        )
        
        configure_llm(llm_config)
        
        # Create agent
        agent_config = AgentConfig(
            max_turns=20,
            verbose=self.verbose,
        )
        
        agent = AgentLoop.create(
            session=self.session,
            llm_config=llm_config,
            agent_config=agent_config,
        )
        
        agent.setup()
        self.agent = agent
        
        return agent
    
    async def run_interactive(self):
        """Run interactive REPL with TUI."""
        # Setup
        self._setup_tui()
        self._setup_tools()
        self._setup_session()
        
        # Welcome
        print_header("Agentic-AI CLI")
        print_success("Session ready")
        
        # Setup LLM
        try:
            self._setup_llm()
            print_success("LLM connected")
        except Exception as e:
            print_error(f"LLM not available: {e}")
            print_info("Set AI_PROVIDER, AI_BASE_URL environment variables")
        
        # Print available tools
        if self.registry:
            tools = self.registry.list_tools()
            print_info(f"{len(tools)} tools registered")
        
        print()
        print(f"{Color.DIM}Type 'help' for commands, 'exit' to quit{Color.RESET}")
        print(f"{Color.DIM}{'─' * get_terminal_width()}{Color.RESET}")
        print()
        
        # Interactive loop
        while True:
            try:
                user_input = self.tui.read_input()
                
                if not user_input.strip():
                    continue
                
                # Handle commands
                if user_input.strip() in ("exit", "quit", "q"):
                    print_success("Goodbye!")
                    break
                
                if user_input.strip() == "help":
                    self._print_help()
                    continue
                
                if user_input.strip() == "tools":
                    self._print_tools()
                    continue
                
                if user_input.strip() == "session":
                    self._print_session()
                    continue
                
                if user_input.strip() == "models":
                    await self._list_models()
                    continue
                
                if user_input.strip() == "clear":
                    import os
                    os.system("cls" if os.name == "nt" else "clear")
                    continue
                
                # Handle slash commands
                if user_input.startswith("/"):
                    await self._handle_slash_command(user_input)
                    continue
                
                # Process as agent request
                await self._process_request(user_input)
                
            except KeyboardInterrupt:
                print(f"\n{Color.DIM}(Use 'exit' to quit){Color.RESET}")
            except EOFError:
                break
        
        # Save session
        if self.session:
            from src.infrastructure.session.session_manager import get_session_store
            store = get_session_store()
            store.save(self.session)
    
    def _print_help(self):
        """Print help."""
        help_text = f"""
Commands:
  {Theme.SUCCESS}help{Color.RESET}     - Show this help
  {Theme.SUCCESS}tools{Color.RESET}    - List available tools
  {Theme.SUCCESS}session{Color.RESET}   - Show current session info
  {Theme.SUCCESS}models{Color.RESET}   - List available LLM models
  {Theme.SUCCESS}clear{Color.RESET}    - Clear the screen
  {Theme.SUCCESS}exit{Color.RESET}     - Exit the CLI

Slash Commands:
  {Theme.WARNING}/model <name>{Color.RESET}   - Switch model
  {Theme.WARNING}/verbose{Color.RESET}        - Toggle verbose mode
  {Theme.WARNING}/memory{Color.RESET}         - Hindsight memory commands

Agentic-AI Specific:
  Embedded debugging, firmware analysis, hardware understanding
"""
        print(help_text)
    
    def _print_tools(self):
        """Print available tools."""
        if not self.registry:
            print_info("Tools not initialized")
            return
        
        tools = self.registry.list_tools()
        
        print(f"\n{Theme.PRIMARY}[{len(tools)} Available Tools]{Color.RESET}\n")
        
        # Group by category
        by_category: dict[str, list] = {}
        for tool in tools:
            by_category.setdefault(tool.category.value, []).append(tool)
        
        for category, category_tools in sorted(by_category.items()):
            print(f"\n  {Theme.PRIMARY}[{category}]{Color.RESET}")
            for tool in category_tools:
                desc = tool.description[:55] if len(tool.description) > 55 else tool.description
                print(f"    {Theme.SUCCESS}{tool.name}{Color.RESET} - {desc}")
    
    def _print_session(self):
        """Print session info."""
        if not self.session:
            print_info("No active session")
            return
        
        print(f"""
{Theme.PRIMARY}Session Information{Color.RESET}
{'─' * 40}
  ID:       {self.session.id[:8]}...
  Status:   {self.session.status.value}
  Created:  {self.session.created_at}
  Updated:  {self.session.updated_at}
  Turns:    {self.session.turn_count}
  Messages: {len(self.session.messages)}
  Tool Calls: {len(self.session.tool_calls)}
"""
        )
        
        if self.session.context.project_path:
            print(f"  {Theme.PRIMARY}Project:{Color.RESET} {self.session.context.project_path}")
            print(f"  {Theme.PRIMARY}Rules:{Color.RESET} {len(self.session.context.rules)} discovered")
    
    async def _list_models(self):
        """List available LLM models."""
        from src.infrastructure.llm.client import get_llm_client
        
        client = get_llm_client()
        
        if await client.health_check():
            print(f"\n{Theme.PRIMARY}Checking models...{Color.RESET}")
            
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as http:
                    response = await http.get(f"{client.config.base_url}/api/tags")
                    if response.status_code == 200:
                        data = response.json()
                        models = data.get("models", [])
                        print(f"\n{Theme.SUCCESS}[{len(models)} Available Models]{Color.RESET}\n")
                        
                        for model in models:
                            name = model.get("name", "unknown")
                            size = model.get("size", 0)
                            size_gb = size / (1024**3) if size else 0
                            print(f"  {Theme.SUCCESS}•{Color.RESET} {name} {Color.DIM}({size_gb:.1f} GB){Color.RESET}")
            except Exception as e:
                print_error(f"Error listing models: {e}")
        else:
            print_error("LLM provider not available")
    
    async def _handle_slash_command(self, user_input: str):
        """Handle slash commands."""
        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        
        if cmd == "/model":
            if arg:
                from src.infrastructure.llm.client import get_llm_client
                client = get_llm_client()
                old_model = client.config.model
                client.config.model = arg
                print_success(f"Model: {old_model} → {arg}")
            else:
                from src.infrastructure.llm.client import get_llm_client
                client = get_llm_client()
                print_info(f"Current model: {client.config.model}")
        
        elif cmd == "/verbose":
            self.verbose = not self.verbose
            print_success(f"Verbose mode: {'on' if self.verbose else 'off'}")
            if self.agent:
                self.agent.config.verbose = self.verbose
        
        elif cmd == "/memory":
            print(f"""
{Theme.PRIMARY}Hindsight Memory Commands{Color.RESET}
{'─' * 40}
  {Theme.WARNING}retain <fact>{Color.RESET} - Store a fact for later recall
  {Theme.WARNING}recall <query>{Color.RESET} - Search memory bank
  {Theme.WARNING}reflect <question>{Color.RESET} - Ask about memories
  {Theme.WARNING}stats{Color.RESET}         - Show memory statistics
""")
        
        else:
            print_error(f"Unknown command: {cmd}")
    
    async def _process_request(self, user_input: str):
        """Process a user request."""
        if not self.agent:
            print_error("LLM not available")
            print_info("Please configure AI_PROVIDER and AI_BASE_URL")
            return
        
        print()
        
        try:
            # Run agent
            result = await self.agent.prompt(user_input)
            
            # Print response with formatting
            if result.final_response:
                self.tui.print_assistant_message(result.final_response)
            
            # Print tool calls if verbose
            if result.tool_calls and self.verbose:
                print(f"\n{Color.DIM}[{len(result.tool_calls)} tool calls executed]{Color.RESET}")
                for tc in result.tool_calls:
                    success = "error" not in tc
                    print()
                    self.tui.print_tool_card(
                        name=tc.get("name", "unknown"),
                        args=tc.get("arguments"),
                        result=str(tc.get("result", ""))[:200],
                        success=success,
                    )
            
            # Add to session
            self.session.add_message("assistant", result.final_response)
            self.session.increment_turn()
            
        except Exception as e:
            logger.exception("Error processing request")
            print_error(f"Error: {e}")
    
    async def run_one_shot(self, prompt: str):
        """Run a single prompt and exit."""
        self._setup_tools()
        self._setup_session()
        
        try:
            self._setup_llm()
        except Exception as e:
            print_error(f"LLM not available: {e}")
            return
        
        print(f"\n{Theme.PRIMARY}Prompt:{Color.RESET} {prompt}\n")
        await self._process_request(prompt)


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        prog="ai-support",
        description="Agentic-AI - Production coding agent CLI",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-p", "--project", type=Path, help="Project path")
    parser.add_argument("--one-shot", type=str, help="Single prompt to run")
    
    # LLM options
    parser.add_argument("--provider", choices=["ollama", "openai", "anthropic"], default="ollama")
    parser.add_argument("--model", type=str, help="Model name")
    parser.add_argument("--base-url", type=str, help="API base URL")
    parser.add_argument("--api-key", type=str, help="API key")
    
    args = parser.parse_args()
    
    # Setup logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Apply CLI args to environment
    if args.provider:
        os.environ["AI_PROVIDER"] = args.provider
    if args.model:
        os.environ["AI_MODEL"] = args.model
    if args.base_url:
        os.environ["AI_BASE_URL"] = args.base_url
    if args.api_key:
        os.environ["AI_API_KEY"] = args.api_key
    
    cli = AgenticCLI()
    cli.verbose = args.verbose
    
    if args.one_shot:
        await cli.run_one_shot(args.one_shot)
    else:
        await cli.run_interactive()


if __name__ == "__main__":
    asyncio.run(main())
