"""AI-powered code completion engine.
Provides intelligent completions beyond LSP basic suggestions.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Completion:
    """A code completion suggestion."""
    text: str
    label: str
    detail: str
    score: float  # 0.0-1.0
    source: str   # "lsp", "template", "ai", "history"


class CompletionEngine:
    """AI-powered code completion engine.
    
    Provides intelligent completions through multiple sources:
    - Template-based completions for common patterns
    - Symbol-based completions from indexed code
    - AI-powered completions using LLM
    - History-based completions from recent edits
    
    Usage:
        engine = CompletionEngine(llm_provider=llm, project_root=Path("."))
        completions = await engine.get_completions(
            file_path="src/main.py",
            cursor_line=10,
            cursor_col=20,
            prefix="def ",
        )
    """
    
    def __init__(self, llm_provider=None, project_root: Optional[Path] = None):
        self.llm_provider = llm_provider
        self.project_root = project_root or Path.cwd()
        self._symbol_index: dict[str, list[tuple[str, int]]] = {}  # symbol -> [(file, line)]
        self._completion_templates = self._load_templates()
        self._history: list[tuple[str, str]] = []  # (prefix, completion)
    
    def _load_templates(self) -> dict[str, list[str]]:
        """Load completion templates for each language."""
        return {
            "python": [
                "for i in range({n}):",
                "with open({path}) as f:",
                "if __name__ == '__main__':",
                "@dataclass\nclass {name}:",
                "async def {name}({params}):",
                "def {name}({params}) -> {ret}:",
                "class {name}({base}):",
                "try:\n    {code}\nexcept {exc} as e:\n    {handler}",
                "if {cond}:\n    {true}\nelse:\n    {false}",
                "return {value}  # TODO: implement",
                "async for {item} in {iterable}:",
                "while {condition}:",
                "match {value}:\n    case {pattern}:",
                "@property\ndef {name}(self):",
                "@staticmethod\ndef {name}({params}):",
                "@classmethod\ndef {name}(cls, {params}):",
                "from typing import {types}",
                "import logging\nlogger = logging.getLogger(__name__)",
                "from pathlib import Path",
                "import asyncio\nfrom concurrent.futures import ThreadPoolExecutor",
                "def __init__(self, {params}):\n    super().__init__()",
            ],
            "javascript": [
                "const {name} = async ({params}) => {",
                "export default function {name}({params}) {",
                "import { {names} } from '{module}';",
                "async function {name}({params}) {",
                "try {\n  {code}\n} catch (err) {\n  {handler}\n}",
                "export const {name} = ({params}) => {",
                "async () => {\n  const result = await {func}();\n}",
                "Object.keys({obj}).forEach(key => {",
                "Object.values({obj}).map(value => {",
                "const [first, ...rest] = {arr};",
                "try { } catch { } finally { }",
                "if ({cond}) { } else if { } else { }",
                "switch ({expr}) {\n  case {val}: break;\n  default: break;\n}",
                "await Promise.all({promises})",
                "new Promise((resolve, reject) => {",
            ],
            "typescript": [
                "const {name} = async ({params}): Promise<{ret}> => {",
                "export default function {name}({params}): {ret} {",
                "interface I{name} {\n  {fields}\n}",
                "type {name} = {\n  {fields}\n}",
                "async function {name}({params}): Promise<{ret}> {",
                "export interface {name} {\n  readonly id: string;\n}",
                "class {name} implements I{name} {",
                "async (): Promise<{ret}> => {",
                "Record<{K}, {V}>",
                "Partial<{T}>",
                "Required<{T}>",
                "Pick<{T}, {K}>",
                "Omit<{T}, {K}>",
                "async/await with Promise<{T}>",
            ],
            "c": [
                "if (result != SUCCESS) {\n    goto cleanup;\n}",
                "for (int i = 0; i < n; i++) {",
                "while ({condition}) {",
                "switch ({expr}) {\n  case {val}: break;\n  default: break;\n}",
                "printf(\"[DEBUG] %s\\n\", {msg});",
                "fprintf(stderr, \"Error: %s\\n\", {msg});",
                "memcpy({dest}, {src}, {size});",
                "sizeof({type})",
                "static inline void {name}({params}) {",
                "#ifdef {macro}\n#endif",
                "if (NULL == {ptr}) {\n    return ERROR;\n}",
            ],
        }
    
    async def get_completions(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        prefix: str,
        trigger: Optional[str] = None,
    ) -> list[Completion]:
        """Get completions at cursor position.
        
        Args:
            file_path: Current file path
            cursor_line: Current line number (1-indexed)
            cursor_col: Current column position
            prefix: Text prefix before cursor
            trigger: Optional trigger character
            
        Returns:
            List of Completions sorted by score
        """
        completions: list[Completion] = []
        
        # 1. Template completions (highest priority for common patterns)
        template_completions = self._get_template_completions(file_path, prefix)
        completions.extend(template_completions)
        
        # 2. Symbol completions from indexed code
        symbol_completions = self._get_symbol_completions(prefix, file_path)
        completions.extend(symbol_completions)
        
        # 3. History completions
        history_completions = self._get_history_completions(prefix)
        completions.extend(history_completions)
        
        # 4. AI completions (if LLM available and prefix is long enough)
        if self.llm_provider and len(prefix) >= 3:
            ai_completions = await self._get_ai_completions(
                file_path, cursor_line, prefix
            )
            completions.extend(ai_completions)
        
        # Sort by score and deduplicate
        completions.sort(key=lambda x: x.score, reverse=True)
        seen: set[str] = set()
        unique: list[Completion] = []
        for c in completions:
            if c.text not in seen:
                seen.add(c.text)
                unique.append(c)
        
        return unique[:20]  # Limit to 20 completions
    
    def _get_template_completions(
        self,
        file_path: str,
        prefix: str,
    ) -> list[Completion]:
        """Get completions from templates."""
        completions: list[Completion] = []
        
        if not prefix:
            return completions
        
        ext = Path(file_path).suffix.lstrip(".")
        lang = self._map_extension_to_language(ext)
        
        templates = self._completion_templates.get(lang, [])
        
        for template in templates:
            # Check if template starts with prefix
            template_start = template.split('\n')[0]
            if template_start.lower().startswith(prefix.lower()):
                score = self._calculate_template_score(template, prefix)
                completions.append(Completion(
                    text=template,
                    label=template_start[:50],
                    detail=f"Template ({lang})",
                    score=score,
                    source="template",
                ))
        
        return completions
    
    def _calculate_template_score(self, template: str, prefix: str) -> float:
        """Calculate relevance score for a template."""
        template_start = template.split('\n')[0].lower()
        prefix_lower = prefix.lower()
        
        # Exact prefix match gets highest score
        if template_start.startswith(prefix_lower):
            return 0.9
        
        # Partial match
        if any(word.startswith(prefix_lower) for word in template_start.split()):
            return 0.7
        
        return 0.5
    
    def _get_symbol_completions(
        self,
        prefix: str,
        current_file: str,
    ) -> list[Completion]:
        """Get completions from indexed symbols."""
        completions: list[Completion] = []
        
        if not prefix:
            return completions
        
        prefix_lower = prefix.lower()
        
        for symbol, locations in self._symbol_index.items():
            if symbol.lower().startswith(prefix_lower):
                # Prefer symbols from same file
                same_file = [loc for loc in locations if loc[0] == current_file]
                other_files = [loc for loc in locations if loc[0] != current_file]
                
                # Add same-file symbols first
                for file_path, line in same_file:
                    completions.append(Completion(
                        text=symbol,
                        label=symbol,
                        detail=f"{Path(file_path).name}:{line}",
                        score=0.85,
                        source="symbol",
                    ))
                
                # Add other-file symbols
                for file_path, line in other_files[:3]:  # Limit to 3 per symbol
                    completions.append(Completion(
                        text=symbol,
                        label=symbol,
                        detail=f"{Path(file_path).name}:{line}",
                        score=0.7,
                        source="symbol",
                    ))
        
        return completions
    
    def _get_history_completions(self, prefix: str) -> list[Completion]:
        """Get completions from recent code history."""
        completions: list[Completion] = []
        
        if not prefix:
            return completions
        
        prefix_lower = prefix.lower()
        
        # Get unique completions from history
        seen: set[str] = set()
        for hist_prefix, hist_completion in reversed(self._history):
            if hist_prefix.lower().startswith(prefix_lower):
                if hist_completion not in seen:
                    seen.add(hist_completion)
                    completions.append(Completion(
                        text=hist_completion,
                        label=hist_completion[:40],
                        detail="Recent",
                        score=0.6,
                        source="history",
                    ))
                    if len(completions) >= 5:
                        break
        
        return completions
    
    async def _get_ai_completions(
        self,
        file_path: str,
        cursor_line: int,
        prefix: str,
    ) -> list[Completion]:
        """Get completions using AI."""
        prompt = f"""Complete this code prefix in {file_path}:

{prefix}|

Return ONLY the completion text that makes sense at the cursor position.
Return ONE line only. No explanation."""

        try:
            response = await self.llm_provider.generate(prompt)
            if response and response.strip():
                return [Completion(
                    text=response.strip(),
                    label=response[:40].strip(),
                    detail="AI completion",
                    score=0.8,
                    source="ai",
                )]
        except Exception as e:
            logger.warning("AI completion failed: %s", e)
        
        return []
    
    def _map_extension_to_language(self, ext: str) -> str:
        """Map file extension to language identifier."""
        mapping = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "jsx": "javascript",
            "tsx": "typescript",
            "c": "c",
            "cpp": "c",
            "cc": "c",
            "h": "c",
            "hpp": "c",
        }
        return mapping.get(ext.lower(), "python")
    
    def add_symbol(self, symbol: str, file_path: str, line: int) -> None:
        """Add a symbol to the completion index.
        
        Args:
            symbol: Symbol name
            file_path: File containing the symbol
            line: Line number of symbol definition
        """
        if symbol not in self._symbol_index:
            self._symbol_index[symbol] = []
        
        loc = (str(file_path), line)
        if loc not in self._symbol_index[symbol]:
            self._symbol_index[symbol].append(loc)
    
    def add_to_history(self, prefix: str, completion: str) -> None:
        """Add a completion to history.
        
        Args:
            prefix: The prefix that triggered the completion
            completion: The completed text
        """
        self._history.append((prefix, completion))
        # Keep history limited to last 1000 entries
        if len(self._history) > 1000:
            self._history = self._history[-1000:]
    
    def index_file(self, file_path: str, symbols: list[tuple[str, int]]) -> None:
        """Index symbols from a file.
        
        Args:
            file_path: Path to the file
            symbols: List of (symbol_name, line_number) tuples
        """
        for symbol, line in symbols:
            self.add_symbol(symbol, file_path, line)
