"""
CodeGraph Tools for Agentic-AI

Exposes CodeGraph capabilities as tools for the AI agent.
"""

from typing import Optional
from .codegraph_client import CodeGraphClient, format_search_results, format_callers_callees


class CodeGraphTools:
    """Tools for code analysis using CodeGraph."""
    
    def __init__(self, project_path: str):
        self.client = CodeGraphClient(project_path)
    
    def search_symbol(self, query: str, limit: int = 10) -> str:
        """
        Search for code symbols (functions, structs, variables, etc.)
        
        Args:
            query: Search term (e.g., function name, type name)
            limit: Max results to return
            
        Returns:
            Formatted search results
        """
        result = self.client.search(query, limit)
        return format_search_results(result)
    
    def get_callers(self, function: str, limit: int = 20) -> str:
        """
        Find what functions/methods call a specific function
        
        Args:
            function: Function name to analyze
            limit: Max callers to return
            
        Returns:
            List of functions that call this function
        """
        result = self.client.callers(function, limit)
        if result.success:
            return result.data or f"No callers found for {function}"
        return f"Error: {result.error}"
    
    def get_callees(self, function: str, limit: int = 20) -> str:
        """
        Find what functions/methods a specific function calls
        
        Args:
            function: Function name to analyze
            limit: Max callees to return
            
        Returns:
            List of functions called by this function
        """
        result = self.client.callees(function, limit)
        if result.success:
            return result.data or f"No callees found for {function}"
        return f"Error: {result.error}"
    
    def analyze_impact(self, symbol: str, depth: int = 2) -> str:
        """
        Analyze the impact of changing a symbol
        
        Args:
            symbol: Symbol name (function, struct, etc.)
            depth: How deep to trace dependencies
            
        Returns:
            Impact analysis showing affected code
        """
        result = self.client.impact(symbol, depth)
        if result.success:
            return result.data or f"No impact data for {symbol}"
        return f"Error: {result.error}"
    
    def get_symbol_info(self, symbol: str) -> str:
        """
        Get detailed information about a symbol
        
        Args:
            symbol: Symbol name
            
        Returns:
            Symbol details including definition and references
        """
        result = self.client.node(symbol)
        if result.success:
            return result.data or f"No info found for {symbol}"
        return f"Error: {result.error}"
    
    def build_context(self, task: str, max_nodes: int = 20) -> str:
        """
        Build relevant code context for a task/question
        
        Args:
            task: Task description or question
            max_nodes: Max code nodes to include
            
        Returns:
            Markdown with relevant code context
        """
        result = self.client.context(task, max_nodes)
        if result.success:
            return result.data or f"No context found for: {task}"
        return f"Error: {result.error}"
    
    def get_file_structure(self, max_depth: int = 3) -> str:
        """
        Get project file structure from index
        
        Args:
            max_depth: Max directory depth
            
        Returns:
            Tree view of project structure
        """
        result = self.client.files(max_depth)
        if result.success:
            return result.data or "Empty project"
        return f"Error: {result.error}"
    
    def get_status(self) -> str:
        """
        Get CodeGraph index status
        
        Returns:
            Index statistics and health
        """
        result = self.client.status()
        if result.success:
            return result.data or "Unknown status"
        return f"Error: {result.error}"


# Tool registry for agent
TOOLS = {
    "search_symbol": {
        "description": "Search for code symbols by name (functions, structs, variables, enums)",
        "parameters": {
            "query": "Search term",
            "limit": "Max results (default 10)"
        }
    },
    "get_callers": {
        "description": "Find what calls a specific function",
        "parameters": {
            "function": "Function name",
            "limit": "Max callers (default 20)"
        }
    },
    "get_callees": {
        "description": "Find what a specific function calls",
        "parameters": {
            "function": "Function name",
            "limit": "Max callees (default 20)"
        }
    },
    "analyze_impact": {
        "description": "Analyze code impact of changing a symbol",
        "parameters": {
            "symbol": "Symbol name",
            "depth": "Dependency depth (default 2)"
        }
    },
    "build_context": {
        "description": "Build code context for a task/question",
        "parameters": {
            "task": "Task description",
            "max_nodes": "Max nodes (default 20)"
        }
    },
    "get_file_structure": {
        "description": "Get project file structure",
        "parameters": {
            "max_depth": "Max depth (default 3)"
        }
    },
    "get_status": {
        "description": "Get CodeGraph index status",
        "parameters": {}
    }
}


def list_tools() -> dict:
    """List all available tools."""
    return TOOLS
