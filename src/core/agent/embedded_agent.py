"""AI_support Embedded Agent - Main Entry Point

⚠️  DEPRECATED: This module is deprecated.
    Please use: python -m src.application.api.app.embedded_agent

Autonomous embedded engineering agent that can:
- Understand firmware architecture
- Analyze code relationships
- Build/flash/test firmware
- Debug issues
- Validate on real hardware

Usage:
    python -m src.application.api.app.embedded_agent chat
    python -m src.application.api.app.embedded_agent task "Build EngineCar"
    python -m src.application.api.app.embedded_agent analyze "Explain DMA architecture"
    python -m src.application.api.app.embedded_agent debug "HardFault in UART"
"""

import warnings
warnings.warn(
    "src.core.agent.embedded_agent is deprecated. "
    "Please use: python -m src.application.api.app.embedded_agent",
    DeprecationWarning,
    stacklevel=2
)

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(name)s | %(message)s",
    handlers=[logging.StreamHandler()]
)

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.domains.knowledge.architecture_map import ArchitectureMap
from src.domains.knowledge.semantic_search import SemanticSearch
from src.domains.knowledge.call_graph_parallel import CallGraphAnalyzer
from src.domains.knowledge.symbol_index import SymbolIndexer
from src.core.tools.progress_utils import NoOpProgressBar


class EmbeddedAgent:
    """AI Embedded Engineer Agent - Main orchestrator."""

    def __init__(self, project_root: str = "main/software"):
        self.project_root = Path(project_root).resolve()
        
        # Initialize knowledge layer
        self.architecture: Optional[ArchitectureMap] = None
        self.semantic_search: Optional[SemanticSearch] = None
        self.call_graph: Optional[CallGraph] = None
        self.symbol_index: Optional[SymbolIndex] = None
        
        # Build indexes on init
        self._initialize_knowledge()

    def _initialize_knowledge(self):
        """Initialize and build knowledge indexes with progress display."""
        print("[AI_support] Initializing knowledge layer...")
        
        # Define initialization steps with descriptions
        steps = [
            ("Building architecture map", self._build_architecture),
            ("Building semantic search index", self._build_semantic),
            ("Building call graph", self._build_call_graph),
            ("Building symbol index", self._build_symbol_index),
        ]
        
        total_start = time.time()
        total_steps = len(steps)
        
        for i, (step_name, step_func) in enumerate(steps):
            # Print progress header (overwrite previous)
            pct = int(((i + 1) / total_steps) * 100)
            bar_len = 20
            filled = int((i / total_steps) * bar_len)
            bar = "=" * filled + "-" * (bar_len - filled)
            
            print(f"\r[AI_support] [{bar}] {pct}% ({i + 1}/{total_steps}) - {step_name}...", end="", flush=True)
            
            start_time = time.time()
            step_func()
            elapsed = time.time() - start_time
            
            # Show completed step
            filled = int(((i + 1) / total_steps) * bar_len)
            bar = "=" * filled + "-" * (bar_len - filled)
            print(f"\r[AI_support] [{bar}] 100% ({i + 1}/{total_steps}) - {step_name} OK ({elapsed:.1f}s)")
        
        total_elapsed = time.time() - total_start
        print(f"[AI_support] Knowledge layer ready ({total_elapsed:.1f}s)")
        
        # Print summary
        print(f"[AI_support]   Files: {getattr(self, '_arch_file_count', '?')}")
        print(f"[AI_support]   Functions: {getattr(self, '_func_count', '?')}")
        print(f"[AI_support]   Symbols: {getattr(self, '_symbol_count', '?')}")

    def _build_architecture(self):
        """Build architecture map."""
        self.architecture = ArchitectureMap(str(self.project_root))
        self.architecture.build()
        self._arch_file_count = len(self.architecture.graph.files)

    def _build_semantic(self):
        """Build semantic search index."""
        self.semantic_search = SemanticSearch(str(self.project_root))
        self.semantic_search.build_index()

    # Cache file path for call graph
    CALL_GRAPH_CACHE = "callgraph_cache.json"

    def _build_call_graph(self):
        """Build or load call graph (tries cache first)."""
        self.call_graph = CallGraphAnalyzer(str(self.project_root))
        cache_path = self.project_root.parent / self.CALL_GRAPH_CACHE
        
        if cache_path.exists():
            if self.call_graph.load(str(cache_path)):
                self._func_count = len(self.call_graph.graph.functions)
                print(f"[AI_support] Call graph loaded from cache ({self._func_count} functions)")
                return
        
        self.call_graph.build()
        self._func_count = len(self.call_graph.graph.functions)
        self.call_graph.save(str(cache_path))
        print(f"[AI_support] Call graph saved to cache")

    def _build_symbol_index(self):
        """Build symbol index."""
        self.symbol_index = SymbolIndexer(str(self.project_root))
        self.symbol_index.build()
        self._symbol_count = len(self.symbol_index.index.symbols)

    def query(self, question: str) -> Dict:
        """Query the agent with a question."""
        print(f"\n[AI_support] Processing: {question}")
        
        # Try architecture query first
        result = self.architecture.query(question)
        if result.get("status") != "unknown_query":
            return result
        
        # Try call graph query
        result = self.call_graph.query(question)
        if result.get("query") != "unknown":
            return result
        
        # Try symbol index query
        result = self.symbol_index.query(question)
        if result.get("query") != "unknown":
            return result
        
        # Fallback to semantic search
        results = self.semantic_search.search(question, max_results=10)
        return {
            "query": "semantic_search",
            "question": question,
            "results": [
                {
                    "file": r.file_path,
                    "line": r.line_number,
                    "content": r.line_content[:100],
                    "score": r.score,
                }
                for r in results
            ]
        }

    def analyze(self, topic: str) -> Dict:
        """Analyze a specific topic in depth."""
        print(f"\n[AI_support] Deep analysis: {topic}")
        
        topic_lower = topic.lower()
        
        if "dma" in topic_lower:
            return self._analyze_dma()
        elif "interrupt" in topic_lower or "isr" in topic_lower:
            return self._analyze_interrupts()
        elif "uart" in topic_lower:
            return self._analyze_uart()
        elif "can" in topic_lower:
            return self._analyze_can()
        elif "gpio" in topic_lower:
            return self._analyze_gpio()
        elif "timer" in topic_lower or "pwm" in topic_lower:
            return self._analyze_timer()
        elif "clock" in topic_lower or "rcc" in topic_lower:
            return self._analyze_clock()
        else:
            return {"status": "unsupported_topic", "topic": topic}

    def _analyze_dma(self) -> Dict:
        """Deep DMA analysis."""
        dma_files = self.architecture.find_file("dma")
        dma_funcs = []
        
        for node in dma_files:
            dma_funcs.extend([f for f in node.functions if "dma" in f.lower()])
        
        # Get ISRs that use DMA
        isr_dma_usage = []
        for func_name in self.call_graph.graph.entry_points:
            if "IRQ" in func_name:
                callees = self.call_graph.get_callees(func_name)
                if any("DMA" in c["name"] for c in callees):
                    isr_dma_usage.append(func_name)
        
        return {
            "analysis": "dma",
            "files": [f.path for f in dma_files[:10]],
            "functions": list(set(dma_funcs))[:20],
            "isrs_using_dma": isr_dma_usage,
            "summary": f"Found {len(dma_files)} DMA-related files, {len(dma_funcs)} DMA functions",
        }

    def _analyze_interrupts(self) -> Dict:
        """Deep interrupt analysis."""
        isrs = self.symbol_index.find_isrs()
        
        # Group by type
        isr_by_priority = {}
        for isr in isrs:
            if "DMA" in isr.name:
                isr_by_priority.setdefault("dma", []).append(isr.name)
            elif "UART" in isr.name or "USART" in isr.name:
                isr_by_priority.setdefault("uart", []).append(isr.name)
            elif "TIM" in isr.name:
                isr_by_priority.setdefault("timer", []).append(isr.name)
            elif "CAN" in isr.name:
                isr_by_priority.setdefault("can", []).append(isr.name)
            elif "EXTI" in isr.name:
                isr_by_priority.setdefault("external", []).append(isr.name)
            else:
                isr_by_priority.setdefault("other", []).append(isr.name)
        
        return {
            "analysis": "interrupts",
            "total_isrs": len(isrs),
            "isrs_by_type": isr_by_priority,
            "isr_list": [{"name": isr.name, "file": isr.file} for isr in isrs],
        }

    def _analyze_uart(self) -> Dict:
        """Deep UART analysis."""
        uart_files = self.architecture.find_file("uart")
        uart_funcs = []
        
        for node in uart_files:
            uart_funcs.extend(node.functions)
        
        return {
            "analysis": "uart",
            "files": [f.path for f in uart_files[:5]],
            "functions": list(set(uart_funcs))[:30],
            "summary": f"Found {len(uart_files)} UART-related files",
        }

    def _analyze_can(self) -> Dict:
        """Deep CAN analysis."""
        can_files = self.architecture.find_file("can")
        can_funcs = []
        
        for node in can_files:
            can_funcs.extend(node.functions)
        
        return {
            "analysis": "can",
            "files": [f.path for f in can_files[:5]],
            "functions": list(set(can_funcs))[:30],
        }

    def _analyze_gpio(self) -> Dict:
        """Deep GPIO analysis."""
        gpio_files = self.architecture.find_file("gpio")
        
        return {
            "analysis": "gpio",
            "files": [f.path for f in gpio_files[:5]],
        }

    def _analyze_timer(self) -> Dict:
        """Deep timer/PWM analysis."""
        timer_files = self.architecture.find_file("timer")
        timer_files.extend(self.architecture.find_file("pwm"))
        
        return {
            "analysis": "timer/pwm",
            "files": list(set(f.path for f in timer_files))[:5],
        }

    def _analyze_clock(self) -> Dict:
        """Deep clock/RCC analysis."""
        clock_files = self.architecture.find_file("rcc")
        clock_files.extend(self.architecture.find_file("clock"))
        
        return {
            "analysis": "clock/rcc",
            "files": [f.path for f in clock_files[:5]],
        }

    def find_function(self, func_name: str) -> Dict:
        """Find detailed information about a function."""
        # Get from symbol index
        sym = self.symbol_index.find(func_name)
        
        # Get callers
        callers = self.call_graph.get_callers(func_name)
        
        # Get callees
        callees = self.call_graph.get_callees(func_name)
        
        # Get ISRs that call this
        isr_callers = [c for c in callers if "IRQ" in c["name"] or "Handler" in c["name"]]
        
        return {
            "function": func_name,
            "definition": {
                "file": sym.file if sym else "unknown",
                "line": sym.line if sym else 0,
                "kind": sym.kind if sym else "unknown",
                "address": sym.address if sym else None,
            },
            "callers": callers,
            "callees": callees,
            "isr_callers": isr_callers,
        }

    def find_symbol(self, symbol_name: str) -> Dict:
        """Find detailed information about a symbol."""
        sym = self.symbol_index.find(symbol_name)
        
        if not sym:
            return {"error": f"Symbol '{symbol_name}' not found"}
        
        # Get references
        refs = self.symbol_index.find_references(symbol_name)
        
        return {
            "symbol": symbol_name,
            "kind": sym.kind,
            "file": sym.file,
            "line": sym.line,
            "address": sym.address,
            "size": sym.size,
            "type_info": sym.type_info,
            "references": refs,
        }

    def get_project_summary(self) -> Dict:
        """Get summary of the project."""
        return {
            "project": self.architecture.graph.project_name,
            "mcu": self.architecture.graph.mcu,
            "files": len(self.architecture.graph.files),
            "components": len(self.architecture.graph.components),
            "functions": len(self.call_graph.graph.functions),
            "symbols": len(self.symbol_index.index.symbols),
            "isrs": len(self.symbol_index.find_isrs()),
            "entry_points": len(self.call_graph.graph.entry_points),
        }


def interactive_chat(agent: EmbeddedAgent):
    """Interactive chat loop."""
    print("\n" + "=" * 60)
    print("AI_support Embedded Engineer Agent")
    print("=" * 60)
    print("\nCommands:")
    print("  query <question>     - Ask about the firmware")
    print("  analyze <topic>      - Deep analysis (dma, isr, uart, etc.)")
    print("  find <symbol>        - Find symbol details")
    print("  function <name>      - Find function details")
    print("  summary             - Project summary")
    print("  help                - Show commands")
    print("  quit                - Exit")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting...")
            break

        if not user_input:
            continue

        parts = user_input.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "quit":
            print("Goodbye!")
            break
        elif cmd == "help":
            print("\nCommands:")
            print("  query <question>     - Ask about the firmware")
            print("  analyze <topic>      - Deep analysis")
            print("  find <symbol>        - Find symbol details")
            print("  function <name>      - Find function details")
            print("  summary             - Project summary")
            print("  quit                - Exit")
        elif cmd == "summary":
            result = agent.get_project_summary()
            print(json.dumps(result, indent=2))
        elif cmd == "query":
            if not args:
                print("Usage: query <question>")
            else:
                result = agent.query(args)
                print(json.dumps(result, indent=2))
        elif cmd == "analyze":
            if not args:
                print("Usage: analyze <topic>")
            else:
                result = agent.analyze(args)
                print(json.dumps(result, indent=2))
        elif cmd == "find":
            if not args:
                print("Usage: find <symbol>")
            else:
                result = agent.find_symbol(args)
                print(json.dumps(result, indent=2))
        elif cmd == "function":
            if not args:
                print("Usage: function <name>")
            else:
                result = agent.find_function(args)
                print(json.dumps(result, indent=2))
        else:
            # Default to query
            result = agent.query(user_input)
            print(json.dumps(result, indent=2))


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="AI_support Embedded Engineer Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python -m src.core.agent.embedded_agent chat
    python -m src.core.agent.embedded_agent task "Explain DMA configuration"
    python -m src.core.agent.embedded_agent analyze dma
    python -m src.core.agent.embedded_agent find DMA_Config
    python -m src.core.agent.embedded_agent function USART1_IRQHandler
        """
    )

    parser.add_argument(
        "command",
        nargs="?",
        default="chat",
        help="Command: chat, task, analyze, find, function, summary"
    )
    parser.add_argument(
        "args",
        nargs="?",
        default="",
        help="Arguments for the command"
    )
    parser.add_argument(
        "-p", "--project",
        default="main/software",
        help="Path to project root (default: main/software)"
    )

    args = parser.parse_args()

    # Determine project root
    project_root = Path(args.project)
    if not project_root.is_absolute():
        # Make relative to current working directory
        project_root = Path.cwd() / project_root
    
    if not project_root.exists():
        print(f"Error: Project root not found: {project_root}")
        return 1

    # Initialize agent
    print(f"[AI_support] Initializing agent for: {project_root}")
    agent = EmbeddedAgent(str(project_root))

    # Execute command
    if args.command == "chat":
        interactive_chat(agent)
    elif args.command == "task":
        if not args.args:
            print("Usage: task <question>")
            return 1
        result = agent.query(args.args)
        print(json.dumps(result, indent=2))
    elif args.command == "analyze":
        if not args.args:
            print("Usage: analyze <topic>")
            return 1
        result = agent.analyze(args.args)
        print(json.dumps(result, indent=2))
    elif args.command == "find":
        if not args.args:
            print("Usage: find <symbol>")
            return 1
        result = agent.find_symbol(args.args)
        print(json.dumps(result, indent=2))
    elif args.command == "function":
        if not args.args:
            print("Usage: function <name>")
            return 1
        result = agent.find_function(args.args)
        print(json.dumps(result, indent=2))
    elif args.command == "summary":
        result = agent.get_project_summary()
        print(json.dumps(result, indent=2))
    else:
        # Default: treat as query
        result = agent.query(args.command + (" " + args.args if args.args else ""))
        print(json.dumps(result, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
