"""
CodeGraph MCP Client for Agentic-AI

Integrates CodeGraph's knowledge graph capabilities for fast code understanding.
"""

import asyncio
import json
import subprocess
from typing import Optional
from dataclasses import dataclass


@dataclass
class CodeGraphNode:
    """Represents a code symbol."""
    kind: str
    name: str
    file: str
    line: int
    id: str


@dataclass
class CodeGraphResult:
    """Result from CodeGraph query."""
    success: bool
    data: any = None
    error: str = ""


class CodeGraphClient:
    """Client for CodeGraph CLI."""
    
    def __init__(self, project_path: str, codegraph_path: Optional[str] = None):
        self.project_path = project_path
        self.codegraph_path = codegraph_path or self._find_codegraph()
        print(f"CodeGraph path: {self.codegraph_path}")
    
    def _find_codegraph(self) -> str:
        """Find CodeGraph executable."""
        import os
        
        # Direct path for Windows
        paths_to_try = [
            r"C:\Users\thang\AppData\Local\codegraph\current\bin\codegraph.cmd",
            os.path.join(os.environ.get('LOCALAPPDATA', ''), 
                        'codegraph', 'current', 'bin', 'codegraph.cmd'),
            'codegraph.cmd',
            'codegraph'
        ]
        
        for path in paths_to_try:
            if os.path.exists(path):
                return path
        return paths_to_try[0]  # Return full path anyway
    
    def _run(self, *args) -> CodeGraphResult:
        """Run CodeGraph command."""
        try:
            cmd = [self.codegraph_path] + list(args)
            cmd_str = ' '.join(f'"{c}"' if ' ' in c else c for c in cmd)
            
            result = subprocess.run(
                cmd_str,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
                shell=True
            )
            
            # CodeGraph returns 1 for some commands but has valid output
            if result.returncode == 0 or result.stdout:
                return CodeGraphResult(success=True, data=result.stdout)
            else:
                return CodeGraphResult(success=False, error=result.stderr)
        except subprocess.TimeoutExpired:
            return CodeGraphResult(success=False, error="Timeout")
        except Exception as e:
            return CodeGraphResult(success=False, error=str(e))
    
    def search(self, query: str, limit: int = 10) -> CodeGraphResult:
        """Search for symbols by name."""
        result = self._run('query', query, '--limit', str(limit))
        return result
    
    def callers(self, symbol: str, limit: int = 20) -> CodeGraphResult:
        """Find what calls a function."""
        result = self._run('callers', symbol, '--limit', str(limit))
        return result
    
    def callees(self, symbol: str, limit: int = 20) -> CodeGraphResult:
        """Find what a function calls."""
        result = self._run('callees', symbol, '--limit', str(limit))
        return result
    
    def impact(self, symbol: str, depth: int = 2) -> CodeGraphResult:
        """Analyze impact of changing a symbol."""
        result = self._run('impact', symbol, '--depth', str(depth))
        return result
    
    def node(self, symbol: str) -> CodeGraphResult:
        """Get details about a symbol."""
        result = self._run('node', symbol)
        return result
    
    def status(self) -> CodeGraphResult:
        """Check index status."""
        result = self._run('status')
        if result.success:
            return CodeGraphResult(success=True, data=result.data)
        return result
    
    def context(self, task: str, max_nodes: int = 20) -> CodeGraphResult:
        """Build context for AI analysis."""
        result = self._run('context', task, '--max-nodes', str(max_nodes))
        if result.success:
            return CodeGraphResult(success=True, data=result.data)
        return result
    
    def files(self, max_depth: int = 3) -> CodeGraphResult:
        """Get indexed file structure."""
        result = self._run('files', '--max-depth', str(max_depth))
        if result.success:
            return CodeGraphResult(success=True, data=result.data)
        return result


def format_search_results(result: CodeGraphResult) -> str:
    """Format search results for display."""
    if not result.success:
        return f"Error: {result.error}"
    
    if isinstance(result.data, str):
        return result.data
    
    if isinstance(result.data, list):
        lines = []
        for item in result.data:
            if isinstance(item, dict):
                kind = item.get('kind', 'unknown')
                name = item.get('name', item.get('symbol', '?'))
                file = item.get('file', item.get('location', '?'))
                lines.append(f"  {kind:12} {name}")
                lines.append(f"    → {file}")
        return "\n".join(lines) if lines else "No results"
    
    return str(result.data)


def format_callers_callees(result: CodeGraphResult, direction: str = "calls") -> str:
    """Format callers/callees results."""
    if not result.success:
        return f"Error: {result.error}"
    
    if isinstance(result.data, str):
        return result.data
    
    return result.data if result.data else f"No {direction}"


# Quick test
if __name__ == "__main__":
    import sys
    
    # Test with CARV project
    project = r"C:\Users\thang\Desktop\carv"
    cg = CodeGraphClient(project)
    
    print("=" * 60)
    print("CodeGraph Client Test")
    print("=" * 60)
    
    # Check status
    print("\n[Status]")
    status = cg.status()
    print(status.data if status.success else status.error)
    
    # Search
    if len(sys.argv) > 1:
        query = sys.argv[1]
    else:
        query = "motor"
    
    print(f"\n[Search: {query}]")
    result = cg.search(query, limit=5)
    print(format_search_results(result))
