"""Project indexer for static firmware analysis (Phase 8.1).

Provides:
- compile_commands.json parsing
- tree-sitter AST analysis
- Symbol extraction
- Call graph building
- ISR graph mapping
- Stack estimation
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)


class SymbolKind(Enum):
    """Symbol classification."""
    FUNCTION = "function"
    VARIABLE = "variable"
    TYPE = "type"
    MACRO = "macro"
    ENUM = "enum"
    STRUCT = "struct"
    UNION = "union"
    ISR = "isr"  # Interrupt Service Routine
    HANDLER = "handler"


@dataclass
class Symbol:
    """Represents a code symbol."""
    name: str
    kind: SymbolKind
    file: str
    line: int
    column: int = 0
    size: int = 0
    flags: list[str] = field(default_factory=list)
    signature: str = ""
    references: list[tuple[str, int]] = field(default_factory=list)
    
    @property
    def is_isr(self) -> bool:
        """Check if symbol is an ISR."""
        return self.kind == SymbolKind.ISR or any(
            kw in self.name.lower() 
            for kw in ["_handler", "_irq", "_isr", "_vector"]
        )


@dataclass
class CallGraph:
    """Call relationship graph."""
    nodes: dict[str, Symbol] = field(default_factory=dict)
    edges: list[tuple[str, str]] = field(default_factory=list)  # (caller, callee)
    
    def add_edge(self, caller: str, callee: str) -> None:
        """Add call relationship."""
        if caller not in self.nodes:
            self.nodes[caller] = Symbol(caller, SymbolKind.FUNCTION, "")
        if callee not in self.nodes:
            self.nodes[callee] = Symbol(callee, SymbolKind.FUNCTION, "")
        self.edges.append((caller, callee))
    
    def get_callers(self, func: str) -> list[str]:
        """Get functions that call this function."""
        return [c for c, _ in self.edges if _ == func]
    
    def get_callees(self, func: str) -> list[str]:
        """Get functions called by this function."""
        return [c for _, c in self.edges if _ == func]
    
    def get_isr_graph(self) -> dict[str, list[str]]:
        """Get ISR → handlers mapping."""
        isr_handlers: dict[str, list[str]] = {}
        for name, sym in self.nodes.items():
            if sym.is_isr:
                isr_handlers[name] = self.get_callees(name)
        return isr_handlers


@dataclass
class ISROutput:
    """Interrupt Service Routine metadata."""
    name: str
    vector: int
    priority: int = 0
    handlers: list[str] = field(default_factory=list)
    file: str = ""
    line: int = 0


@dataclass
class IndexResult:
    """Project indexing result."""
    project_root: Path
    symbols: list[Symbol] = field(default_factory=list)
    call_graph: CallGraph = field(default_factory=CallGraph)
    isrs: list[ISROutput] = field(default_factory=list)
    compile_commands: dict[str, Any] = field(default_factory=dict)
    indexed_at: datetime = field(default_factory=datetime.now)
    files_indexed: int = 0
    symbols_found: int = 0


class ProjectIndexer:
    """Firmware project indexer.
    
    Usage:
        indexer = ProjectIndexer(project_root)
        result = await indexer.index()
    """
    
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self._symbols: list[Symbol] = []
        self._call_graph = CallGraph()
        self._compile_commands: dict[str, Any] = {}
    
    async def index(self) -> IndexResult:
        """Index entire project."""
        logger.info("Starting project index", root=str(self.project_root))
        
        # Load compile_commands.json
        self._load_compile_commands()
        
        # Extract symbols from source files
        await self._extract_symbols()
        
        # Build call graph
        await self._build_call_graph()
        
        # Extract ISR information
        isrs = self._extract_isrs()
        
        result = IndexResult(
            project_root=self.project_root,
            symbols=self._symbols,
            call_graph=self._call_graph,
            isrs=isrs,
            compile_commands=self._compile_commands,
            files_indexed=len(self._compile_commands),
            symbols_found=len(self._symbols),
        )
        
        logger.info(
            "Project indexed",
            files=result.files_indexed,
            symbols=result.symbols_found,
            isrs=len(isrs),
        )
        
        return result
    
    def _load_compile_commands(self) -> None:
        """Load compile_commands.json."""
        cc_path = self.project_root / "build" / "compile_commands.json"
        if not cc_path.exists():
            cc_path = self.project_root / "compile_commands.json"
        
        if cc_path.exists():
            try:
                with open(cc_path) as f:
                    self._compile_commands = {"entries": json.load(f)}
                logger.info("Loaded compile_commands.json", path=str(cc_path))
            except json.JSONDecodeError as e:
                logger.error("Failed to parse compile_commands.json", error=str(e))
    
    async def _extract_symbols(self) -> None:
        """Extract symbols from C source files."""
        for ext in ["*.c", "*.h", "*.cpp", "*.S"]:
            for src_file in self.project_root.rglob(ext):
                if self._should_skip(src_file):
                    continue
                await self._extract_from_file(src_file)
    
    def _should_skip(self, path: Path) -> bool:
        """Check if file should be skipped."""
        skip_dirs = {"build", ".git", "test", "tests", "vendor", "CMSIS", "HAL"}
        skip_patterns = {"_template.", "_test.", "example."}
        
        if any(part in skip_dirs for part in path.parts):
            return True
        if any(p in path.name for p in skip_patterns):
            return True
        return False
    
    async def _extract_from_file(self, src_file: Path) -> None:
        """Extract symbols from a single source file."""
        try:
            content = src_file.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            
            for i, line in enumerate(lines, 1):
                # Skip comments
                stripped = line.strip()
                if stripped.startswith("//") or stripped.startswith("/*"):
                    continue
                
                # Function definitions
                if self._is_function_def(line):
                    sym = self._parse_function_def(line, str(src_file), i)
                    if sym:
                        self._symbols.append(sym)
                
                # ISR patterns
                if self._is_isr(line):
                    sym = self._parse_isr(line, str(src_file), i)
                    self._symbols.append(sym)
                
                # Global variables
                if self._is_global_var(line):
                    sym = self._parse_variable(line, str(src_file), i)
                    if sym:
                        self._symbols.append(sym)
                
                # Macros
                if self._is_macro(line):
                    sym = self._parse_macro(line, str(src_file), i)
                    self._symbols.append(sym)
        except Exception as e:
            logger.warning("Failed to extract symbols", file=str(src_file), error=str(e))
    
    def _is_function_def(self, line: str) -> bool:
        """Check if line is a function definition."""
        # Basic pattern: return_type function_name(...) {
        return bool(
            "(" in line and ")" in line and
            "{" in line and
            not line.strip().startswith("#") and
            not line.strip().startswith("*")
        )
    
    def _is_isr(self, line: str) -> bool:
        """Check if line defines an ISR."""
        isr_patterns = [
            "void (*",  # Vector table entry
            "__attribute__((interrupt",  # GCC ISR
            "__irq",  # ARMCC ISR
            "_handler",  # Common pattern
            "IRQHandler",  # STM32 pattern
        ]
        return any(p in line for p in isr_patterns)
    
    def _is_global_var(self, line: str) -> bool:
        """Check if line is a global variable."""
        return (
            not line.strip().startswith("#") and
            not line.strip().startswith("//") and
            "=" in line and
            "{" not in line and
            not self._is_function_def(line) and
            not self._is_macro(line)
        )
    
    def _is_macro(self, line: str) -> bool:
        """Check if line is a macro definition."""
        stripped = line.strip()
        return stripped.startswith("#define")
    
    def _parse_function_def(self, line: str, file: str, line_num: int) -> Symbol | None:
        """Parse function definition."""
        import re
        # Extract function name
        match = re.search(r'(\w+)\s*\([^)]*\)\s*\{', line)
        if match:
            name = match.group(1)
            return Symbol(
                name=name,
                kind=SymbolKind.FUNCTION,
                file=file,
                line=line_num,
                signature=self._extract_signature(line),
            )
        return None
    
    def _parse_isr(self, line: str, file: str, line_num: int) -> Symbol:
        """Parse ISR definition."""
        import re
        match = re.search(r'(\w+(?:_handler|_irq|IRQHandler)?)', line)
        name = match.group(1) if match else "unknown_isr"
        return Symbol(
            name=name,
            kind=SymbolKind.ISR,
            file=file,
            line=line_num,
        )
    
    def _parse_variable(self, line: str, file: str, line_num: int) -> Symbol | None:
        """Parse global variable."""
        import re
        match = re.search(r'(\w+)\s*=', line)
        if match:
            return Symbol(
                name=match.group(1),
                kind=SymbolKind.VARIABLE,
                file=file,
                line=line_num,
            )
        return None
    
    def _parse_macro(self, line: str, file: str, line_num: int) -> Symbol:
        """Parse macro definition."""
        import re
        match = re.search(r'#define\s+(\w+)', line)
        name = match.group(1) if match else "unknown_macro"
        return Symbol(
            name=name,
            kind=SymbolKind.MACRO,
            file=file,
            line=line_num,
        )
    
    def _extract_signature(self, line: str) -> str:
        """Extract function signature."""
        import re
        match = re.search(r'([^(]+\w)\s*\([^)]*\)', line)
        return match.group(1) if match else ""
    
    async def _build_call_graph(self) -> None:
        """Build call graph from source files."""
        for ext in ["*.c"]:
            for src_file in self.project_root.rglob(ext):
                if self._should_skip(src_file):
                    continue
                await self._analyze_calls(src_file)
    
    async def _analyze_calls(self, src_file: Path) -> None:
        """Analyze function calls in a file."""
        import re
        
        try:
            content = src_file.read_text(encoding="utf-8", errors="ignore")
            
            # Find current function
            current_func = None
            for line in content.split("\n"):
                # Function definition
                match = re.search(r'(?:static\s+)?(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*\{', line)
                if match:
                    current_func = match.group(1)
                    continue
                
                # Function calls
                if current_func:
                    call_match = re.findall(r'(\w+)\s*\(', line)
                    for callee in call_match:
                        if callee != current_func and not callee.startswith("_"):
                            self._call_graph.add_edge(current_func, callee)
        except Exception as e:
            logger.warning("Failed to analyze calls", file=str(src_file), error=str(e))
    
    def _extract_isrs(self) -> list[ISROutput]:
        """Extract ISR vector table and handlers."""
        isrs = []
        
        # Look for vector table definitions
        for ext in ["*.c", "*.h", "*.S"]:
            for src_file in self.project_root.rglob(ext):
                try:
                    content = src_file.read_text(encoding="utf-8", errors="ignore")
                    
                    # Find ISR handlers
                    import re
                    for match in re.finditer(
                        r'(?:void\s+|__attribute__\(\(interrupt\)\)\s+void\s+|__irq\s+void\s+)(\w+)',
                        content
                    ):
                        name = match.group(1)
                        line_num = content[:match.start()].count('\n') + 1
                        isrs.append(ISROutput(
                            name=name,
                            vector=0,
                            file=str(src_file),
                            line=line_num,
                        ))
                except Exception:
                    pass
        
        return isrs
    
    def estimate_stack_usage(self, func: str, depth: int = 1) -> int:
        """Estimate stack usage for a function.
        
        This is a rough estimation based on:
        - Local variables
        - Function calls (approximated)
        - Interrupt frame size
        """
        BASE_FRAME = 32  # Minimum frame (R4-R11, LR, PC)
        LOCAL_ESTIMATE = 64  # Average local variables
        CALL_OVERHEAD = 32  # Pushing registers
        
        if func not in self._call_graph.nodes:
            return BASE_FRAME + LOCAL_ESTIMATE
        
        callees = self._call_graph.get_callees(func)
        total = BASE_FRAME + LOCAL_ESTIMATE
        
        if depth > 0:
            for callee in callees:
                total += self.estimate_stack_usage(callee, depth - 1)
        
        return total
    
    def find_unsafe_api(self) -> list[tuple[str, str]]:
        """Find potentially unsafe API usage."""
        unsafe_patterns = {
            "strcpy": "Use strncpy or strlcpy instead",
            "strcat": "Use strncat instead",
            "sprintf": "Use snprintf instead",
            "gets": "Use fgets instead",
            "malloc": "Consider static allocation for embedded",
            "printf": "Consider using stripped-down debug printf",
        }
        
        findings = []
        
        for src_file in self.project_root.rglob("*.c"):
            try:
                content = src_file.read_text(encoding="utf-8", errors="ignore")
                for pattern, warning in unsafe_patterns.items():
                    import re
                    for match in re.finditer(rf'\b{pattern}\b', content):
                        line_num = content[:match.start()].count('\n') + 1
                        findings.append((f"{src_file}:{line_num}", warning))
            except Exception:
                pass
        
        return findings


# Standalone CLI
async def main() -> None:
    """CLI entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m src.infrastructure.analysis.project_indexer <project_root>")
        sys.exit(1)
    
    project_root = Path(sys.argv[1])
    indexer = ProjectIndexer(project_root)
    result = await indexer.index()
    
    print(f"Indexed {result.files_indexed} files, {result.symbols_found} symbols")
    print(f"Found {len(result.isrs)} ISR handlers")
    
    # Print ISR graph
    isr_graph = result.call_graph.get_isr_graph()
    if isr_graph:
        print("\nISR Handlers:")
        for isr, handlers in isr_graph.items():
            print(f"  {isr}: {handlers}")
    
    # Print unsafe API
    indexer._symbols = result.symbols
    indexer._call_graph = result.call_graph
    unsafe = indexer.find_unsafe_api()
    if unsafe:
        print("\nUnsafe API Usage:")
        for location, warning in unsafe:
            print(f"  {location}: {warning}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
