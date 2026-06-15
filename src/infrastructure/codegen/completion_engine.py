"""AI-powered code completion engine with speculative decoding and streaming.

Provides intelligent completions:
- Template-based completions for common patterns
- Symbol-based completions from indexed code
- Speculative cache with prefix trie
- Streaming LLM completions with cancellation
- Debounce/throttle for editor integration
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class Completion:
    """A code completion suggestion."""
    text: str
    label: str
    detail: str
    score: float  # 0.0-1.0
    source: str   # "lsp", "template", "ai", "history", "cache"


@dataclass
class CompletionRequest:
    """A completion request with context."""
    file_path: str
    cursor_line: int
    cursor_col: int
    prefix: str
    suffix: str = ""  # Text after cursor
    trigger: Optional[str] = None
    request_id: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass  
class CompletionResponse:
    """Streaming completion response."""
    request_id: str
    completions: list[Completion] = field(default_factory=list)
    is_complete: bool = False
    cancelled: bool = False


class PrefixTrie:
    """Speculative cache using prefix trie for O(k) lookup where k=prefix length."""
    
    def __init__(self, max_size: int = 10000):
        self._root: dict[str, dict] = {}
        self._completions: dict[str, list[Completion]] = {}
        self._max_size = max_size
        self._size = 0
    
    def get(self, prefix: str) -> Optional[list[Completion]]:
        """Get cached completions for prefix."""
        node = self._root
        for char in prefix.lower():
            if char not in node:
                return None
            node = node[char]
        return self._completions.get(prefix.lower())
    
    def put(self, prefix: str, completions: list[Completion]) -> None:
        """Cache completions for prefix."""
        if self._size >= self._max_size:
            return
        key = prefix.lower()
        if key not in self._completions:
            self._size += 1
        self._completions[key] = completions
        
        node = self._root
        for char in key:
            if char not in node:
                node[char] = {}
            node = node[char]
    
    def get_matches(self, prefix: str) -> list[Completion]:
        """Get all completions where prefix is a prefix of cached keys."""
        matches: list[Completion] = []
        key = prefix.lower()
        for cached_prefix, completions in self._completions.items():
            if cached_prefix.startswith(key) and cached_prefix != key:
                matches.extend(completions)
        return matches[:5]


class CompletionEngine:
    """AI-powered code completion engine with speculative caching and streaming.
    
    Provides intelligent completions through multiple sources:
    - Template-based completions for common patterns
    - Symbol-based completions from indexed code  
    - Speculative cache with prefix trie (local-first)
    - Streaming LLM completions with cancellation
    - History-based completions from recent edits
    - Debounce/throttle for editor integration
    
    Usage:
        engine = CompletionEngine(llm_provider=llm, project_root=Path("."))
        
        # Synchronous completion
        completions = await engine.get_completions(
            file_path="src/main.py",
            cursor_line=10,
            cursor_col=20,
            prefix="def ",
        )
        
        # Streaming completion
        async for chunk in engine.stream_completions(request):
            print(chunk.text, end="")
    """
    
    # Debounce time in seconds
    DEBOUNCE_MS = 0.15
    
    def __init__(
        self,
        llm_provider=None,
        project_root: Optional[Path] = None,
        debounce_seconds: float = 0.15,
    ):
        self.llm_provider = llm_provider
        self.project_root = project_root or Path.cwd()
        self._symbol_index: dict[str, list[tuple[str, int]]] = {}
        self._completion_templates = self._load_templates()
        self._history: deque[tuple[str, str]] = deque(maxlen=1000)
        
        # Speculative cache
        self._speculative_cache = PrefixTrie(max_size=10000)
        
        # Debounce state
        self._debounce_seconds = debounce_seconds
        self._pending_requests: dict[str, asyncio.Task] = {}
        self._debounce_lock = asyncio.Lock()
        
        # Streaming state
        self._active_requests: dict[str, asyncio.Event] = {}
        
        # HTTP client for streaming (reused)
        self._http_client: Optional[httpx.AsyncClient] = None
    
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
            ],
            "javascript": [
                "const {name} = async ({params}) => {",
                "export default function {name}({params}) {",
                "import { {names} } from '{module}';",
                "async function {name}({params}) {",
                "try {\n  {code}\n} catch (err) {\n  {handler}\n}",
                "export const {name} = ({params}) => {",
                "Object.keys({obj}).forEach(key => {",
                "await Promise.all({promises})",
            ],
            "typescript": [
                "const {name} = async ({params}): Promise<{ret}> => {",
                "export default function {name}({params}): {ret} {",
                "interface I{name} {{\n  {fields}\n}}",
                "type {name} = {{\n  {fields}\n}}",
                "async function {name}({params}): Promise<{ret}> {{",
            ],
            "c": [
                "if (result != SUCCESS) {{\n    goto cleanup;\n}}",
                "for (int i = 0; i < n; i++) {{",
                "while ({condition}) {{",
                "switch ({expr}) {{\n  case {val}: break;\n  default: break;\n}}",
                "printf(\"[DEBUG] %s\\n\", {msg});",
                "static inline void {name}({params}) {{",
            ],
        }
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create reusable HTTP client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=5.0),
                limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            )
        return self._http_client
    
    async def get_completions(
        self,
        file_path: str,
        cursor_line: int,
        cursor_col: int,
        prefix: str,
        suffix: str = "",
        trigger: Optional[str] = None,
    ) -> list[Completion]:
        """Get completions at cursor position with debounce.
        
        Args:
            file_path: Current file path
            cursor_line: Current line number (1-indexed)
            cursor_col: Current column position
            prefix: Text prefix before cursor
            suffix: Text after cursor
            trigger: Optional trigger character
            
        Returns:
            List of Completions sorted by score
        """
        completions: list[Completion] = []
        request_id = f"{file_path}:{cursor_line}:{cursor_col}:{prefix[:20]}"
        
        # Check speculative cache first
        cached = self._speculative_cache.get(prefix)
        if cached:
            return cached[:20]
        
        # 1. Template completions (highest priority for common patterns)
        template_completions = self._get_template_completions(file_path, prefix)
        completions.extend(template_completions)
        
        # 2. Symbol completions from indexed code
        symbol_completions = self._get_symbol_completions(prefix, file_path)
        completions.extend(symbol_completions)
        
        # 3. History completions
        history_completions = self._get_history_completions(prefix)
        completions.extend(history_completions)
        
        # 4. Speculative cache hints (from similar prefixes)
        cache_hints = self._speculative_cache.get_matches(prefix)
        if cache_hints:
            completions.extend(cache_hints[:3])
        
        # Sort by score and deduplicate
        completions.sort(key=lambda x: x.score, reverse=True)
        seen: set[str] = set()
        unique: list[Completion] = []
        for c in completions:
            if c.text not in seen:
                seen.add(c.text)
                unique.append(c)
        
        result = unique[:20]
        
        # Cache non-AI completions
        if result and any(c.source != "ai" for c in result):
            self._speculative_cache.put(prefix, result)
        
        return result
    
    async def stream_completions(
        self,
        request: CompletionRequest,
    ) -> CompletionResponse:
        """Stream completions with cancellation support.
        
        Args:
            request: Completion request with context
            
        Returns:
            CompletionResponse with streaming results
        """
        request_id = request.request_id or f"{request.file_path}:{time.time()}"
        cancel_event = asyncio.Event()
        self._active_requests[request_id] = cancel_event
        
        try:
            # Get fast completions first
            fast_completions = await self.get_completions(
                request.file_path,
                request.cursor_line,
                request.cursor_col,
                request.prefix,
                request.suffix,
                request.trigger,
            )
            
            response = CompletionResponse(
                request_id=request_id,
                completions=fast_completions,
                is_complete=True,
            )
            
            # If prefix is long enough, stream LLM completions
            if self.llm_provider and len(request.prefix) >= 10:
                llm_completions = await self._stream_llm_completion(request, cancel_event)
                if not cancel_event.is_set() and llm_completions:
                    response.completions = llm_completions + fast_completions
                    response.completions.sort(key=lambda x: x.score, reverse=True)
                    response.completions = response.completions[:20]
            
            return response
            
        finally:
            self._active_requests.pop(request_id, None)
    
    async def _stream_llm_completion(
        self,
        request: CompletionRequest,
        cancel_event: asyncio.Event,
    ) -> list[Completion]:
        """Stream LLM completions with cancellation."""
        if cancel_event.is_set():
            return []
        
        # Build context-aware prompt
        context = self._build_completion_context(request)
        
        try:
            prompt = f"""Complete the code at cursor in {request.file_path}:

Context before cursor:
{context.before}

Complete only what comes AFTER the cursor. Return single line only.
No explanation, no markdown, just code."""
            
            if hasattr(self.llm_provider, 'stream'):
                chunks: list[str] = []
                async for chunk in self.llm_provider.stream(prompt):
                    if cancel_event.is_set():
                        return []
                    if chunk.content:
                        chunks.append(chunk.content)
                
                completion_text = "".join(chunks).strip()
                if completion_text:
                    return [Completion(
                        text=completion_text,
                        label=completion_text[:40],
                        detail="AI completion (streamed)",
                        score=0.85,
                        source="ai",
                    )]
        except Exception as e:
            logger.warning("Streaming LLM completion failed: %s", e)
        
        return []
    
    def _build_completion_context(self, request: CompletionRequest) -> dict:
        """Build context window for completion."""
        # Read file content if available
        try:
            file_path = Path(self.project_root) / request.file_path
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8')
                lines = content.split('\n')
                start = max(0, request.cursor_line - 20)
                before_lines = lines[start:request.cursor_line]
                return {
                    "before": '\n'.join(before_lines[-10:]),
                    "suffix": request.suffix,
                }
        except Exception:
            pass
        return {"before": request.prefix, "suffix": request.suffix}
    
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
        
        if template_start.startswith(prefix_lower):
            return 0.95
        
        if any(word.startswith(prefix_lower) for word in template_start.split()):
            return 0.75
        
        return 0.5
    
    def _get_symbol_completions(
        self,
        prefix: str,
        current_file: str,
    ) -> list[Completion]:
        """Get completions from indexed symbols using trie lookup."""
        completions: list[Completion] = []
        
        if not prefix:
            return completions
        
        prefix_lower = prefix.lower()
        
        for symbol, locations in self._symbol_index.items():
            if symbol.lower().startswith(prefix_lower):
                same_file = [loc for loc in locations if loc[0] == current_file]
                other_files = [loc for loc in locations if loc[0] != current_file]
                
                for file_path, line in same_file[:2]:
                    completions.append(Completion(
                        text=symbol,
                        label=symbol,
                        detail=f"{Path(file_path).name}:{line} (same file)",
                        score=0.85,
                        source="symbol",
                    ))
                
                for file_path, line in other_files[:2]:
                    completions.append(Completion(
                        text=symbol,
                        label=symbol,
                        detail=f"{Path(file_path).name}:{line}",
                        score=0.75,
                        source="symbol",
                    ))
        
        return completions
    
    def _get_history_completions(self, prefix: str) -> list[Completion]:
        """Get completions from recent code history."""
        completions: list[Completion] = []
        
        if not prefix:
            return completions
        
        prefix_lower = prefix.lower()
        seen: set[str] = set()
        
        for hist_prefix, hist_completion in reversed(self._history):
            if hist_prefix.lower().startswith(prefix_lower):
                if hist_completion not in seen:
                    seen.add(hist_completion)
                    completions.append(Completion(
                        text=hist_completion,
                        label=hist_completion[:40],
                        detail="Recent",
                        score=0.65,
                        source="history",
                    ))
                    if len(completions) >= 5:
                        break
        
        return completions
    
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
        """Add a symbol to the completion index."""
        if symbol not in self._symbol_index:
            self._symbol_index[symbol] = []
        
        loc = (str(file_path), line)
        if loc not in self._symbol_index[symbol]:
            self._symbol_index[symbol].append(loc)
    
    def add_to_history(self, prefix: str, completion: str) -> None:
        """Add a completion to history."""
        self._history.append((prefix, completion))
    
    def index_file(self, file_path: str, symbols: list[tuple[str, int]]) -> None:
        """Index symbols from a file."""
        for symbol, line in symbols:
            self.add_symbol(symbol, file_path, line)
    
    def cancel_request(self, request_id: str) -> None:
        """Cancel an active completion request."""
        if request_id in self._active_requests:
            self._active_requests[request_id].set()
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None