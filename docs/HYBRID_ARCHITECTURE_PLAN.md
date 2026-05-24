# Hybrid Architecture: Agentic-AI + oh-my-pi Patterns

> Transform Agentic-AI into a production coding agent by adopting omp patterns while preserving the embedded moat.

---

## Executive Summary

| Goal | Strategy |
|------|----------|
| Production-ready CLI | Adopt omp's TUI/CLI patterns |
| Performance | Optimize Python hot paths OR add Rust components |
| Tool ecosystem | Add LSP/DAP/AST tools like omp |
| Edit reliability | Implement hashline edit format |
| Memory | Add Hindsight (retain/recall/reflect) |
| Web search | Multi-provider chain (like omp) |
| **Keep** | Embedded/automotive debugging (unique moat) |

---

## Architecture Comparison

### Current Agentic-AI (Layered)
```
Web UI (React)
    ↓
API Server (FastAPI)
    ↓
core/agent/        # Reasoning loop
core/runtime/      # Workflow
domain/            # Business logic
infrastructure/    # External adapters
```

### Target Hybrid Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                     CLI/TUI Interface                       │
│  (Terminal-first like omp, keep Web UI optional)            │
├─────────────────────────────────────────────────────────────┤
│                    Agent Core (TypeScript)                  │
│  - Agent loop (event-based like omp)                        │
│  - Tool registry                                            │
│  - Session management                                       │
│  - Hindsight memory                                         │
├─────────────────────────────────────────────────────────────┤
│                  Tool Layer (Rust/TypeScript)               │
│  - File ops (hashline edit)                                 │
│  - Search (ripgrep in-process)                              │
│  - Shell (embedded PTY)                                      │
│  - LSP/DAP clients                                          │
│  - AST manipulation                                          │
├─────────────────────────────────────────────────────────────┤
│              Domain Layer (Python - PRESERVED)               │
│  - Embedded target models                                    │
│  - Flash state machine                                       │
│  - Hardware/HIL agents                                      │
│  - Deterministic workflow                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Patterns to Adopt from omp

### 1. Hashline Edit Format

**omp's approach:**
- Content-hash anchors instead of line numbers
- Stale-anchor recovery
- 61% fewer tokens on same work

**Implementation:**

```python
# src/infrastructure/tools/hashline.py

@dataclass
class HashlineAnchor:
    content_hash: str  # SHA256 of surrounding context
    line_hint: Optional[int]  # Hint only, not authoritative
    
@dataclass  
class HashlinePatch:
    anchor: HashlineAnchor
    old_content: str
    new_content: str
    
def apply_hashline_patch(file_path: Path, patch: HashlinePatch) -> EditResult:
    """Apply patch using content hash, reject stale anchors."""
    content = file_path.read_text()
    
    # Find anchor by hash
    lines = content.splitlines()
    anchor_line = find_line_by_hash(lines, patch.anchor.content_hash)
    
    if anchor_line is None:
        raise StaleAnchorError(f"Could not find hash {patch.anchor.content_hash}")
    
    # Verify surrounding context hasn't changed
    if not verify_context(lines, anchor_line, patch.old_content):
        raise ContextDriftError("File modified since anchor created")
    
    # Apply edit
    return perform_edit(lines, anchor_line, patch.old_content, patch.new_content)
```

### 2. AST Edit with Preview

**omp's approach:**
- `ast_edit` returns proposed changes
- User reviews before `resolve` applies

**Implementation:**

```python
# src/infrastructure/tools/ast_edit.py

@dataclass
class ASTEditProposal:
    file_path: str
    rule: str  # ast-grep pattern
    replacement: str
    replacement_count: int
    
async def ast_edit(proposal: ASTEditProposal) -> ASTEditProposal:
    """Return proposal without applying."""
    matches = await find_ast_matches(proposal.file_path, proposal.rule)
    return ASTEditProposal(
        file_path=proposal.file_path,
        rule=proposal.rule,
        replacement=proposal.replacement,
        replacement_count=len(matches)
    )

async def resolve(proposal: ASTEditProposal, reason: str) -> EditResult:
    """Apply the proposed AST edit."""
    # Atomic all-or-nothing apply
    pass
```

### 3. Hindsight Memory System

**omp's approach:**
- `retain` - queue facts into memory bank
- `recall` - search memory bank
- `reflect` - synthesize over bank

**Implementation:**

```python
# src/core/memory/hindsight.py

class HindsightMemory:
    """Project-scoped memory curated by agent."""
    
    async def retain(self, fact: str, context: str) -> str:
        """Queue durable fact into memory bank."""
        entry = MemoryEntry(
            content=fact,
            context=context,
            project=current_project(),
            timestamp=EventSourcedClock.now(),
            embedding=await self._embed(fact)
        )
        await self.store.insert(entry)
        return entry.id
    
    async def recall(self, query: str, limit: int = 5) -> List[MemoryEntry]:
        """Search memory bank for relevant facts."""
        query_emb = await self._embed(query)
        return await self.store.search(query_emb, limit=limit)
    
    async def reflect(self, question: str) -> str:
        """Synthesize answer over memory bank."""
        facts = await self.recall(question, limit=10)
        prompt = build_reflection_prompt(question, facts)
        return await self._llm.generate(prompt)
    
    async def compress_session(self) -> str:
        """Compress current session into mental model."""
        # Used at session end, loaded at next start
        pass
```

### 4. Time-Traveling Stream Rules

**omp's approach:**
- Rules trigger when model goes off-script
- Abort mid-token, inject rule, retry from same point
- Survives compaction

**Implementation:**

```python
# src/infrastructure/tools/stream_rules.py

class StreamRuleEngine:
    """Intercept and correct model output mid-stream."""
    
    def __init__(self, rules: List[StreamRule]):
        self.rules = rules
        self.pending_corrections: List[Correction] = []
    
    async def process_stream(self, stream: AsyncGenerator[str]) -> AsyncGenerator[str]:
        """Process stream, injecting corrections as needed."""
        buffer = ""
        
        async for chunk in stream:
            buffer += chunk
            
            # Check rules
            for rule in self.rules:
                if rule.matches(buffer):
                    # Abort, inject, retry
                    correction = rule.create_correction(buffer)
                    self.pending_corrections.append(correction)
                    yield from self._inject_correction(correction)
                    buffer = ""
                    break
            else:
                yield chunk
```

### 5. Multi-Provider Web Search Chain

**omp's 14 providers:**
```
auto → exa → brave → jina → kimi → zai → anthropic → perplexity → 
gemini → codex → tavily → parallel → kagi → synthetic → searxng
```

**Implementation:**

```python
# src/infrastructure/web_search/providers.py

PROVIDER_CHAIN = [
    "exa", "brave", "jina", "kimi", "zai", "anthropic",
    "perplexity", "gemini", "codex", "tavily", "parallel",
    "kagi", "synthetic", "searxng"
]

@dataclass
class SearchResult:
    url: str
    title: str
    snippet: str
    provider: str
    score: float

async def web_search(query: str, provider: str = "auto") -> List[SearchResult]:
    if provider == "auto":
        return await _chain_search(query)
    
    return await _provider_search(query, provider)

async def _chain_search(query: str) -> List[SearchResult]:
    """Walk chain until results found."""
    for provider in PROVIDER_CHAIN:
        try:
            results = await _provider_search(query, provider)
            if results:
                return results
        except Exception:
            continue
    
    return []
```

### 6. Embedded Tool Execution

**omp's Rust core:**
- ripgrep in-process (no fork-exec)
- brush-shell embedded
- Tree-sitter AST
- Native PTY

**Python optimization options:**

```python
# Option A: PyO3 Rust bindings (gradual)
# src/infrastructure/natives/rust_core.pyi

class RustGrep:
    def search(self, pattern: str, paths: List[str]) -> List[GrepMatch]: ...
    
class RustShell:
    def exec(self, cmd: str, cwd: str) -> ShellResult: ...
    
class RustGlob:
    def find(self, pattern: str, root: str) -> List[str]: ...

# Option B: Python-native optimization
# src/infrastructure/natives/optimized.py

import asyncio
import subprocess
from functools import lru_cache

class OptimizedGrep:
    """Use ripgrep subprocess with caching."""
    
    @lru_cache(maxsize=1000)
    def search_cached(self, pattern: str, root: str) -> List[GrepMatch]:
        result = subprocess.run(
            ["rg", "--json", pattern, root],
            capture_output=True, text=True
        )
        return self._parse_rg_json(result.stdout)
    
    async def search(self, pattern: str, root: str) -> List[GrepMatch]:
        proc = await asyncio.create_subprocess_exec(
            "rg", "--json", pattern, root,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await proc.communicate()
        return self._parse_rg_json(stdout.decode())
```

---

## Migration Phases

### Phase 1: CLI Foundation (Weeks 1-4)

**Goals:**
- [ ] Design agent CLI entry point
- [ ] Implement session management (like omp's session files)
- [ ] Add basic file tools with hashline format
- [ ] Add terminal/PTY support

**Files to create/modify:**
```
src/interfaces/cli/
├── main.py              # CLI entry point
├── session.py           # Session management
└── tools/
    ├── __init__.py
    ├── read.py           # Summarized reads
    ├── edit.py           # Hashline edits
    ├── search.py         # Optimized grep
    └── bash.py           # PTY shell

src/core/agent/
├── agent_loop.py        # Event-based loop
├── tool_registry.py     # Unified tool registry
└── session_state.py     # Session persistence
```

### Phase 2: Tool Ecosystem (Weeks 5-8)

**Goals:**
- [ ] Add LSP client integration
- [ ] Add DAP debugger support
- [ ] Implement AST edit/preview/resolve
- [ ] Add browser automation (if WebView available)

**Files to create:**
```
src/infrastructure/tools/
├── lsp/
│   ├── client.py
│   └── operations.py    # diagnostics, rename, refs
├── dap/
│   ├── client.py
│   └── operations.py    # breakpoints, stepping
└── ast/
    ├── matcher.py       # ast-grep integration
    └── editor.py        # Structural edits
```

### Phase 3: Memory & Search (Weeks 9-12)

**Goals:**
- [ ] Implement Hindsight memory
- [ ] Add multi-provider web search
- [ ] Build session compaction

**Files to create:**
```
src/core/memory/
├── hindsight.py         # retain/recall/reflect
├── session_compactor.py # Compress sessions
└── bank.py             # Persistent storage

src/infrastructure/web_search/
├── provider.py         # Base provider
├── providers/          # 14 provider implementations
└── scrapers/           # Site-specific extractors
```

### Phase 4: Embedded Integration (Weeks 13-16)

**Goals:**
- [ ] Integrate existing embedded domain
- [ ] Add hardware/HIL tools to registry
- [ ] Build embedded debugging workflow

**Preserve from current codebase:**
```
src/domain/hardware/         # Embedded target models
src/infrastructure/hardware/ # HIL, probes, GDB
src/domain/hardware/flash/   # Flash state machine
```

---

## Key Differences: omp vs Agentic-AI

| Aspect | omp | Agentic-AI Target |
|--------|-----|-------------------|
| Language | TypeScript + Rust | Python + optional Rust |
| Edit format | Hashline | Hashline (new) |
| Memory | Hindsight | Hindsight (new) |
| LSP/DAP | Built-in | Add (new) |
| Web search | 14 providers | Multi-provider (new) |
| Embedded | ❌ | ✅ (unique) |
| Flash recovery | ❌ | ✅ (unique) |
| Deterministic replay | Partial | Full (P0-E) |

---

## Implementation Order

### Must-have for v1.0:
1. ✅ CLI with session management
2. ✅ File tools (read/write/edit with hashline)
3. ✅ Search (optimized grep)
4. ✅ Shell execution
5. ✅ Basic LLM integration

### Should-have for v1.1:
6. ⬜ LSP operations
7. ⬜ DAP debugger
8. ⬜ AST edit/preview
9. ⬜ Multi-provider web search
10. ⬜ Hindsight memory

### Nice-to-have for v1.2:
11. ⬜ Embedded domain tools
12. ⬜ Flash recovery workflow
13. ⬜ Deterministic replay
14. ⬜ Browser automation

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep | High | Stick to phase order, don't add features |
| Python performance | Medium | Add Rust components incrementally |
| Complexity | High | Freeze current features before adding new |
| Embedded moat lost | Critical | Keep domain layer separate, well-tested |

---

## Next Steps

1. **Approve this plan** or request changes
2. **Start Phase 1** - Create CLI foundation
3. **Iterate** based on user feedback

---

*Created: May 2024*
*Status: Draft - Awaiting approval*
