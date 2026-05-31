# BÁO CÁO ĐÁNH GIÁ AI_SUPPORT
## So sánh với Cursor AI cho tác vụ Code Review

**Ngày đánh giá:** 2026-05-31  
**Người đánh giá:** AI_SUPPORT Evaluation Agent  
**Phiên bản:** 1.0

---

## Mục lục# Kế hoạch nâng cấp AI_SUPPORT lên 100% Cursor-like (Phần mềm)

**Mục tiêu:** Đạt ≥95% điểm đánh giá tổng hợp (A+B+C+D+E) với mỗi tiêu chí ≥90%.

**Chiến lược:** Cải thiện tuần tự theo 3 giai đoạn (P0 → P1 → P2), mỗi giai đoạn kết thúc bằng một phiên bản có thể kiểm thử độc lập.

## Giai đoạn P0 (Tuần 1) – Nền tảng: 80% → 85%

**Trọng tâm:** Tăng số lượng rules, cải thiện phân tích tĩnh cơ bản.

### Task P0-1: Mở rộng Rule Engine lên 100+ rules (4h)
- Thêm 72 rules mới vào `src/infrastructure/analysis/rules/`
  - Security (20 rules): SQL injection, hardcoded secrets, unsafe deserialization, path traversal, command injection, weak crypto, etc.
  - Code Quality (20 rules): cognitive complexity, too many branches, too long methods, duplicate code, unused variables, etc.
  - Type safety (15 rules): missing type hints, type inconsistencies, `Any` usage, etc.
  - Error handling (10 rules): bare except, too broad exception, missing finally, etc.
  - Performance (7 rules): O(n^2) loops, inefficient string concat, etc.
- Cập nhật `rule_engine.py` để load rules từ thư mục con động.
- Viết unit tests cho mỗi rule mới.

### Task P0-2: Nâng cấp Call Graph & Dependency Graph (6h)
- **Alias import resolution**: Sửa `call_graph.py` để map alias → module gốc (dùng `ImportResolver` class).
- **Reverse index**: Xây dựng `_callers` dict lưu danh sách các nơi gọi một hàm (phục vụ `find references`).
- **Incremental indexing**: Thêm cơ chế theo dõi `last_modified` và chỉ re-index file thay đổi.
- **Call site arguments**: Lưu danh sách tên biến được truyền vào mỗi lời gọi (dùng cho data flow sau này).
- Cập nhật `build()` method để dùng AST visitor ghi nhận cả alias và dynamic call (nếu khả thi, ít nhất là static).

### Task P0-3: Tích hợp Data Flow Analyzer cơ bản (4h)
- Tạo `src/infrastructure/analysis/data_flow.py`
- Phân tích luồng dữ liệu trong một hàm (local data flow)
- Phát hiện lỗi sử dụng biến chưa gán, gán nhưng không dùng
- Kết hợp với call graph để phát hiện taint qua tham số (cơ bản)

### Task P0-4: Viết integration tests cho các module mới (3h)
- Test `ImportResolver` với các trường hợp alias, nested import.
- Test `CallGraph` incremental update.
- Test `DataFlowAnalyzer` với các mẫu code có luồng dữ liệu phức tạp.

**Tiêu chí hoàn thành P0:**
- Unit tests pass (≥80% coverage)
- Rule count ≥100
- Call graph có reverse index và hỗ trợ alias
- Data flow cơ bản hoạt động
- Điểm đánh giá tổng ≥80%

## Giai đoạn P1 (Tuần 2) – Trải nghiệm người dùng: 85% → 90%

**Trọng tâm:** Cải thiện UX, output, và tốc độ cảm nhận.

### Task P1-1: Syntax highlighting & Better Output (4h)
- Tích hợp `pygments` vào `result_formatter.py`
- Tạo class `SyntaxHighlightedCode` với theme mặc định (monokai, one-dark)
- Định dạng lại report: thêm icon severity, code blocks màu, side-by-side diff preview.
- Hỗ trợ xuất HTML (để xem trong browser) và JSON.

### Task P1-2: CLI Autocomplete & Inline Hints (6h)
- Cài đặt `readline` completer trong `src/interfaces/cli/autocomplete.py`
- Bổ sung command `Tab` completion cho `/fix`, `/review`, `@file`, `--rule`.
- Tạo cơ chế inline hint (hiển thị khi gõ lệnh) – dùng `prompt_toolkit` thay vì `readline` nếu cần.
- Cập nhật `slash.py` để xử lý hint và hiển thị gợi ý trước khi người dùng gõ xong.

### Task P1-3: Thêm 30 rules framework‑specific (4h)
- TypeScript/React (10 rules): hooks rules, missing dependency, improper useEffect, etc.
- FastAPI/Django (10 rules): missing async, insecure CORS, ORM n+1, etc.
- Testing (5 rules): missing assertions, slow tests, etc.
- Documentation (5 rules): missing docstrings, outdated comments.

### Task P1-4: Tối ưu incremental indexing để review real‑time (4h)
- Cập nhật `call_graph.py` và `indexer.py` để lắng nghe sự kiện thay đổi file (watchdog).
- Chỉ chạy phân tích lại file thay đổi và các file bị ảnh hưởng (dùng dependency graph).
- Đo thời gian review trung bình cho codebase 1000 file < 2s.

**Tiêu chí hoàn thành P1:**
- CLI có autocomplete và inline hint.
- Output có syntax highlighting và side-by-side diff.
- Có ít nhất 130 rules.
- Incremental indexing hoạt động, review nhanh.
- Điểm tổng ≥90%.

## Giai đoạn P2 (Tuần 3) – Thông minh & Mở rộng: 90% → 100%

**Trọng tâm:** LLM integration, plugin system, collaboration.

### Task P2-1: LLM‑Powered Fix Suggestions (8h)
- Tạo `src/core/fix_engine/llm_fixer.py`
- Dùng OpenAI API (hoặc local LLM) để sinh fix cho các lỗi phức tạp.
- Cung cấp cơ chế fallback (khi không có LLM, dùng template).
- Thêm tham số `--llm` cho CLI.
- Viết tests với mock API.

### Task P2-2: Plugin Discovery & Hot‑Reload (6h)
- Thiết kế plugin spec (`plugin.json` + entry point).
- Tạo `PluginManager` trong `src/infrastructure/plugins/`.
- Tự động phát hiện plugin từ thư mục `.ai_support/plugins` và các thư mục cấu hình.
- Hỗ trợ hot‑reload (cài đặt plugin mới mà không restart).
- Cung cấp plugin mẫu (ví dụ: custom rule, custom formatter).

### Task P2-3: Team Collaboration Features (4h)
- Tạo module `collaborative_review.py`
- Lưu các comment, thread, resolution state (dùng SQLite).
- CLI command `/review session start`, `/comment`, `/resolve`.
- Xuất báo cáo tổng hợp review cho PR.

### Task P2-4: Full Integration Testing & Documentation (4h)
- Viết end‑to‑end tests cho luồng review từ đầu đến cuối.
- Tạo tài liệu hướng dẫn cài đặt, sử dụng, viết plugin.
- Cập nhật `README.md` với badge, ví dụ.

**Tiêu chí hoàn thành P2:**
- LLM fix hoạt động (có fallback).
- Có ít nhất 1 plugin demo hoạt động.
- Có thể review PR với comment và thread.
- Điểm tổng ≥95%, mỗi tiêu chí ≥90%.

## Kế hoạch kiểm thử & đánh giá liên tục

- Sau mỗi task, chạy `pytest` và `pre-commit`.
- Mỗi cuối ngày, chạy bộ đánh giá tự động (dựa trên bộ tiêu chí A-E) để cập nhật điểm.
- Nếu điểm giảm, rollback commit và phân tích nguyên nhân.

## Tổng kết nguồn lực

| Giai đoạn | Giờ làm việc | Kết quả mong đợi |
|-----------|--------------|------------------|
| P0        | 17h (2 ngày) | 80% → 85%      |
| P1        | 18h (2.5 ngày) | 85% → 90%      |
| P2        | 22h (3 ngày) | 90% → 95%+     |
| **Tổng**  | **57h (≈7.5 ngày)** | **95-100%** |

*Thời gian tính cho 1 developer full-time. Có thể chia sẻ cho 2 người để hoàn thành trong 5 ngày.*

## Rủi ro & phương án giảm thiểu

| Rủi ro | Phương án |
|--------|-----------|
| LLM API không ổn định hoặc tốn kém | Fallback sang template; cho phép dùng local model (Ollama). |
| Plugin system quá phức tạp | Làm minimal plugin manager trước, chỉ hỗ trợ rules và formatters. |
| Incremental indexing sai sót | Kiểm tra kỹ bằng cách so sánh kết quả với full rebuild sau mỗi lần sửa. |
| Thiếu thời gian | Ưu tiên P0 và P1 trước; P2 có thể kéo dài thêm 1 tuần. |

**Ký duyệt:**  
- Product Owner: ________________  
- Lead Developer: ________________  
- Ngày bắt đầu: 2026-06-01

1. [Tổng quan](#1-tổng-quan)
2. [Đánh giá chi tiết (A-E)](#2-đánh-giá-chi-tiết-a-e)
3. [Điểm số tổng](#3-điểm-số-tổng)
4. [Kết luận](#4-kết-luận)
5. [3-5 Tính năng còn thiếu cho 90%](#5-3-5-tính-năng-còn-thiếu-cho-90)
6. [So sánh với Cursor thực](#6-so-sánh-với-cursor-thực)
7. [Thiết kế Subagent tự cải thiện](#7-thiết-kế-subagent-tự-cải-thiện)
8. [Lộ trình 3 giai đoạn đến 100%](#8-lộ-trình-3-giai-đoạn-đến-100)
9. [Output mẫu hoàn hảo](#9-output-mẫu-hoàn-hảo)

---

## 1. Tổng quan

### Mục tiêu đánh giá
Đánh giá mức độ "giống Cursor" của hệ thống AI_SUPPORT trong tác vụ code review tự động.

### Phạm vi đánh giá
- **Module chính:** `src/core/cognition/call_graph.py`
- **ML Detector:** `src/infrastructure/analysis/ml_detectors/detector.py`
- **CLI Commands:** `src/interfaces/cli/commands/slash.py`
- **Result Formatter:** `src/application/workflows/unified/result_formatter.py`
- **Unified Review:** `src/interfaces/cli/commands/unified_review.py`
- **Rule Engine:** `src/infrastructure/analysis/rule_engine.py`
- **Tests:** `tests/unit/test_call_graph.py`

### Tiêu chí đánh giá (A-E)

| Tiêu chí | Mô tả |
|----------|-------|
| **A. Độ chính xác phân tích** | Khả năng phát hiện lỗi chính xác |
| **B. Tính đầy đủ của rules** | Số lượng và phạm vi rules |
| **C. Chất lượng output** | Định dạng, rõ ràng, hữu ích |
| **D. Tích hợp CLI/UX** | Giao diện dòng lệnh, tương tác |
| **E. Khả năng mở rộng** | Kiến trúc plugin, custom rules |

---

## 2. Đánh giá chi tiết (A-E)

### A. Độ chính xác phân tích (Accuracy)

**Điểm: 75/100**

#### Evidence

| File | Dòng | Nội dung | Đánh giá |
|------|------|----------|----------|
| `call_graph.py` | 23-29 | Built-in function filtering | ✅ Tốt |
| `call_graph.py` | 97-99 | `build()` method với AST parsing | ✅ Tốt |
| `detector.py` | 95-98 | `is_high_confidence` property (threshold 0.85) | ✅ Tốt |
| `rule_engine.py` | 44-47 | Constants cho thresholds | ✅ Tốt |
| `rule_engine.py` | 49-50 | Language support check | ⚠️ Cần cải thiện |

#### Strengths

1. **AST-based analysis:** Sử dụng AST parsing thay vì regex đơn giản
   ```python
   # call_graph.py:32-41
   @dataclass
   class CallSite:
       caller: str
       callee: str
       file: str
       line: int
       col: int = 0
       is_method: bool = False
   ```

2. **Confidence scoring:** Hệ thống điểm confidence rõ ràng
   ```python
   # detector.py:95-98
   @property
   def is_high_confidence(self) -> bool:
       """Check if finding has high confidence (>= 0.85)."""
       return self.confidence >= 0.85
   ```

3. **Built-in function filtering:** Tránh false positives
   ```python
   # call_graph.py:23-29
   _BUILTINS: set[str] = {
       "print", "len", "str", "int", "float", "bool",
       "list", "dict", "set", "tuple", "range", ...
   }
   ```

#### Weaknesses

1. **Cross-file resolution limited:** Chỉ resolve imports cơ bản
   ```python
   # call_graph.py:82 - Imports per file
   self._imports: dict[str, list[ImportEntry]] = {}
   ```

2. **Không có data flow analysis đầy đủ:** Chỉ có fallback regex
   ```python
   # detector.py:9 - "Graceful fallback to regex when AST unavailable"
   ```

3. **ML detector thiếu context-aware detection:** Không track state across functions

---

### B. Tính đầy đủ của Rules

**Điểm: 65/100**

#### Evidence

| File | Dòng | Rule count | Đánh giá |
|------|------|------------|----------|
| `rule_engine.py` | 4 | "28 built-in rules" | ⚠️ Ít hơn Cursor |
| `rule_engine.py` | 10-15 | Security, Type, Import, Naming, Quality | ✅ Đa dạng |
| `detector.py` | 1 | ML001-ML00x rules | ⚠️ Cần mở rộng |

#### Strengths

1. **Phạm vi đa dạng:** Security, Quality, ML, Embedded
   ```python
   # rule_engine.py:10-15
   Built-in rules cover:
   - Security: hardcoded secrets, SQL injection, command injection
   - Type Safety: untyped functions, Any usage, missing return types
   - Import Analysis: unused imports, circular imports
   - Naming Conventions: snake_case, PascalCase
   - Code Quality: long functions, broad except, TODO/FIXME
   ```

2. **Auto-fix templates:** Có sẵn fix suggestions
   ```python
   # rule_engine.py:6
   - Auto-fix templates for common issues
   ```

3. **External linter integration:** Merge từ pylint, ruff, eslint
   ```python
   # rule_engine.py:8
   - Merge findings from external linters (pylint, ruff, eslint, golangci-lint)
   ```

#### Weaknesses

1. **Chỉ 28 rules:** Cursor có 100+ rules
2. **Không có framework-specific rules:** React, Vue, Angular
3. **Không có performance rules:** Memory leaks, big O complexity
4. **Không có accessibility rules:** WCAG compliance

---

### C. Chất lượng Output

**Điểm: 70/100**

#### Evidence

| File | Dòng | Tính năng | Đánh giá |
|------|------|------------|----------|
| `result_formatter.py` | 28-64 | UnifiedPipelineStats | ✅ Tốt |
| `result_formatter.py` | 79-100 | `from_issues()` classmethod | ✅ Tốt |
| `unified_review.py` | 340-364 | Multiple format output | ✅ Tốt |
| `slash.py` | 620-651 | Diff preview in fix output | ✅ Tốt |

#### Strengths

1. **Multiple output formats:** Markdown, JSON, CLI
   ```python
   # result_formatter.py:3-7
   Provides multiple output formats:
   - UnifiedMarkdownFormatter: Cursor-style markdown
   - UnifiedJsonFormatter: Structured JSON
   - UnifiedCLIFormatter: Terminal output
   ```

2. **Statistics tracking:** Chi tiết và có metadata
   ```python
   # result_formatter.py:28-43
   @dataclass
   class UnifiedPipelineStats:
       files_scanned: int = 0
       total_issues: int = 0
       critical_count: int = 0
       high_count: int = 0
       medium_count: int = 0
       low_count: int = 0
       execution_time_ms: float = 0.0
       detectors_used: list[str] = field(default_factory=list)
   ```

3. **Diff preview:** Hiển thị thay đổi trước khi apply
   ```python
   # slash.py:640-650
   if show_diff:
       result = await applicator.apply_fix_ast(
           file_path=Path(fix.file),
           line=fix.line,
           new_code=applicator._extract_code_from_fix(fix.fix),
           create_backup=False,
           dry_run=True,
       )
       if result.get("diff"):
           output_lines.append(f"\n```diff\n{result['diff']}\n```")
   ```

#### Weaknesses

1. **Không có syntax highlighting:** Code blocks không màu
2. **Không có inline comments:** Khó theo dõi conversation
3. **Report structure cứng:** Không customizable layout
4. **Không có before/after code comparison:** Chỉ hiển thị fix

---

### D. Tích hợp CLI/UX

**Điểm: 78/100**

#### Evidence

| File | Dòng | Tính năng | Đánh giá |
|------|------|------------|----------|
| `slash.py` | 1-15 | Command documentation | ✅ Tốt |
| `slash.py` | 44-51 | CommandCategory enum | ✅ Tốt |
| `slash.py` | 524-702 | `cmd_fix()` function | ✅ Tốt |
| `unified_review.py` | 187-230 | Interactive pre-review | ✅ Tốt |
| `unified_review.py` | 233-263 | Interactive post-review | ✅ Tốt |

#### Strengths

1. **Cursor-style slash commands:** `/fix`, `/review`, `/explain`
   ```python
   # slash.py:3-11
   Supports:
       /fix [@file[:line]] [--dry-run] [--apply] [--interactive]
       /fix @file:line:end_line [options]
       /fix @file --rule=ML001
       /review [--files=FILES] [--focus=AREA]
       /explain [@symbol]
       /stats
   ```

2. **Interactive mode:** Xác nhận trước khi apply
   ```python
   # slash.py:714-828
   async def cmd_fix_interactive(ctx: CommandContext) -> CommandResult:
       """Interactive fix mode with user confirmation."""
       # Options: [y] Yes, [n] No, [a] Yes to all, [q] Quit, [e] Edit, [s] Skip, [h] Help
   ```

3. **Rich command aliases:** Multiple ways to invoke
   ```python
   # slash.py:1413-1415
   "fix": Command(
       name="fix",
       aliases=["f"],
       ...
   )
   ```

#### Weaknesses

1. **Không có autocomplete:** Không support Tab completion
2. **Không có keyboard shortcuts:** vim-style navigation
3. **Interactive mode hạn chế:** Không có paging, filtering
4. **Không có TUI:** Chỉ có CLI text

---

### E. Khả năng mở rộng

**Điểm: 72/100**

#### Evidence

| File | Dòng | Tính năng | Đánh giá |
|------|------|------------|----------|
| `rule_engine.py` | 2 | "Extensible rule system" | ✅ Tốt |
| `rule_engine.py` | 17-22 | Usage example | ✅ Tốt |
| `detector.py` | 1-22 | MLDetector documentation | ✅ Tốt |
| `call_graph.py` | 64-70 | CallGraph class docstring | ✅ Tốt |

#### Strengths

1. **Plugin architecture:** Dễ thêm rules mới
   ```python
   # rule_engine.py:17-22
   Usage:
       from src.infrastructure.analysis.rule_engine import RuleEngine
       engine = RuleEngine(indexer=indexer)
       findings = engine.detect("path/to/file.py", "python")
   ```

2. **Dataclass-based findings:** Dễ extend
   ```python
   # detector.py:50-66
   @dataclass
   class MLFinding:
       rule_id: str
       severity: MLSeverity
       line: int
       message: str
       confidence: float
       old_code: str
       new_code: str
       explanation: str
   ```

3. **Indexer integration:** TreeSitter, SymbolGraph, ReferenceGraph
   ```python
   # slash.py:1016-1027
   from src.infrastructure.indexing.symbol_graph import SymbolGraph
   from src.infrastructure.indexing.reference_graph import ReferenceGraph
   symbol_graph = SymbolGraph()
   ref_graph = ReferenceGraph()
   ```

#### Weaknesses

1. **Không có plugin discovery:** Phải import thủ công
2. **Không có hot-reload:** Thay đổi rules không tự cập nhật
3. **Không có rule dependencies:** Không có way to express rule relationships
4. **Không có rule testing framework:** Không có cách test rules mới

---

## 3. Điểm số tổng

| Tiêu chí | Điểm | Trọng số |
|----------|------|----------|
| A. Độ chính xác phân tích | 75 | 30% |
| B. Tính đầy đủ của rules | 65 | 25% |
| C. Chất lượng output | 70 | 20% |
| D. Tích hợp CLI/UX | 78 | 15% |
| E. Khả năng mở rộng | 72 | 10% |

### Công thức tính

```
Total = (75 × 0.30) + (65 × 0.25) + (70 × 0.20) + (78 × 0.15) + (72 × 0.10)
Total = 22.5 + 16.25 + 14.0 + 11.7 + 7.2
Total = 71.65/100
```

**Điểm tổng: 71.65/100 (≈ 72%)**

---

## 4. Kết luận

### Ngưỡng đánh giá

| Ngưỡng | Kết quả | Mô tả |
|--------|---------|--------|
| ≥85% | Rất giống Cursor | Có thể thay thế trong các tác vụ review cơ bản |
| 60-85% | Giống khá | Cần bổ sung vài module |
| <60% | Còn nhiều thiếu sót | Cần cải thiện đáng kể |

### Kết luận: **71.65% - Giống khá, cần bổ sung vài module**

AI_SUPPORT đã có:
- ✅ Kiến trúc tốt cho code analysis
- ✅ Slash commands theo phong cách Cursor
- ✅ ML detector với confidence scoring
- ✅ Rule engine extensible
- ✅ Interactive mode với fix confirmation

AI_SUPPORT cần thêm:
- ⚠️ Nhiều rules hơn (28 vs 100+ của Cursor)
- ⚠️ Tích hợp AI/LLM mạnh hơn cho suggestions
- ⚠️ Better output formatting (syntax highlighting)
- ⚠️ Autocomplete và keyboard shortcuts
- ⚠️ Plugin discovery system

---

## 5. 3-5 Tính năng còn thiếu cho 90%

### 1. AI-Powered Fix Suggestions (Critical)
**Priority:** P0 - Week 1

**Current state:** Chỉ có regex-based fixes
**Needed:** LLM-powered fix generation

```python
# Thiếu: src/core/fix_engine/llm_fixer.py
class LLMFixEngine:
    """Generate fixes using LLM for complex issues."""
    
    async def generate_fix(
        self,
        finding: Finding,
        context: CodeContext,
    ) -> FixSuggestion:
        """Generate contextual fix using LLM."""
        prompt = f"""
Analyze this code issue and suggest a fix:

File: {context.file_path}:{finding.line}
Issue: {finding.message}
Severity: {finding.severity}

Code context:
```python
{context.get_context(finding.line)}
```

Generate a fix that:
1. Addresses the root cause
2. Maintains code style consistency
3. Includes tests if needed
"""
        response = await self.llm.complete(prompt)
        return FixSuggestion.parse(response)
```

### 2. Multi-Language Advanced Analysis (High)
**Priority:** P0 - Week 1

**Current state:** Chỉ basic multi-language support
**Needed:** Deep analysis cho TypeScript, Rust, Go

```python
# Thiếu: src/infrastructure/analysis/languages/
# src/infrastructure/analysis/languages/typescript.py
class TypeScriptAnalyzer:
    """Deep TypeScript/TSX analysis."""
    
    def detect_type_issues(self, content: str) -> list[Finding]:
        # Generic type inference
        # React hooks rules
        # Angular template analysis
        # Next.js specific patterns
        pass
    
    def detect_framework_issues(self, content: str, framework: str) -> list[Finding]:
        # React: hooks rules, component patterns
        # Vue: composition API, options API
        # Angular: dependency injection, change detection
        pass
```

### 3. Intelligent Codebase Indexing (High)
**Priority:** P1 - Week 2

**Current state:** File-level indexing
**Needed:** Project-wide semantic understanding

```python
# Thiếu: src/infrastructure/indexing/project_indexer.py
class ProjectIndexer:
    """Index entire project for semantic understanding."""
    
    async def index_project(self, root: Path) -> ProjectKnowledgeGraph:
        """Build complete project knowledge graph."""
        
        # 1. Parse all files by language
        files = await self._discover_files(root)
        
        # 2. Build symbol graph across files
        symbol_graph = await self._build_cross_file_symbols(files)
        
        # 3. Extract type hierarchies
        type_hierarchy = await self._extract_inheritance(files)
        
        # 4. Build call graph with data flow
        call_graph = await self._build_data_flow_graph(files)
        
        # 5. Identify architectural patterns
        patterns = await self._detect_architectural_patterns(files)
        
        return ProjectKnowledgeGraph(
            symbols=symbol_graph,
            types=type_hierarchy,
            calls=call_graph,
            patterns=patterns,
        )
```

### 4. Smart Autocomplete & Inline Actions (Medium)
**Priority:** P1 - Week 2

**Current state:** Không có
**Needed:** Cursor-style inline suggestions

```python
# Thiếu: src/interfaces/editor/inline_suggestions.py
class InlineSuggestionEngine:
    """Provide Cursor-style inline suggestions."""
    
    async def get_suggestions(
        self,
        cursor_position: CursorPosition,
        context: EditorContext,
    ) -> list[InlineSuggestion]:
        """Generate context-aware suggestions."""
        
        suggestions = []
        
        # 1. Import suggestions
        if self._should_suggest_import(context):
            suggestions.append(await self._suggest_import(context))
        
        # 2. Function call completion
        if self._is_in_function_call(context):
            suggestions.append(await self._suggest_call_args(context))
        
        # 3. Fix suggestions for errors
        if self._has_nearby_error(context):
            suggestions.append(await self._suggest_quick_fix(context))
        
        # 4. Refactoring suggestions
        if self._detected_code_smell(context):
            suggestions.append(await self._suggest_refactor(context))
        
        return sorted(suggestions, key=lambda s: s.confidence, reverse=True)
```

### 5. Collaborative Review Mode (Medium)
**Priority:** P2 - Week 3

**Current state:** Không có
**Needed:** Team-based code review

```python
# Thiếu: src/application/workflows/collaborative/
class CollaborativeReview:
    """Multi-user code review session."""
    
    def create_session(self, pr_id: str) -> ReviewSession:
        """Create a review session for PR."""
        
    async def add_comment(
        self,
        session_id: str,
        file: str,
        line: int,
        comment: str,
        author: str,
    ) -> Comment:
        """Add inline comment to review."""
        
    async def resolve_thread(
        self,
        session_id: str,
        thread_id: str,
    ) -> None:
        """Mark comment thread as resolved."""
        
    async def get_review_summary(
        self,
        session_id: str,
    ) -> ReviewSummary:
        """Generate summary for PR approval."""
```

---

## 6. So sánh với Cursor thực

### Strengths của AI_SUPPORT

| Tính năng | AI_SUPPORT | Cursor | Notes |
|------------|------------|--------|-------|
| AST-based analysis | ✅ | ✅ | Tương đương |
| Call graph | ✅ | ✅ | Tương đương |
| Rule engine extensible | ✅ | ✅ | AI_SUPPORT tốt hơn |
| Embedded systems focus | ✅ | ❌ | AI_SUPPORT advantage |
| ML-specific detection | ✅ | Partial | AI_SUPPORT advantage |
| Open source | ✅ | ❌ | AI_SUPPORT advantage |

### Gaps so với Cursor

| Tính năng | Cursor | AI_SUPPORT | Gap |
|------------|--------|------------|-----|
| Inline suggestions | Real-time | ❌ | **Major** |
| LLM-powered fixes | GPT-4 | Regex only | **Major** |
| Autocomplete | Yes | ❌ | **Major** |
| Keyboard shortcuts | vim/emacs | ❌ | Medium |
| Syntax highlighting | Yes | ❌ | Medium |
| Plugin ecosystem | 1000+ | 0 | **Major** |
| Team collaboration | Yes | ❌ | **Major** |
| PR integration | GitHub native | ❌ | Medium |
| Learning from edits | Yes | ❌ | **Major** |

### Specific Improvements Needed

```python
# Gap 1: No inline suggestions
# Cursor: Shows suggestions as you type
# AI_SUPPORT: Only runs on explicit /fix or /review

# Gap 2: No LLM fix generation  
# Cursor: Uses GPT-4 to generate contextual fixes
# AI_SUPPORT: Only template-based regex fixes

# Gap 3: No learning from edits
# Cursor: Learns from your accept/reject patterns
# AI_SUPPORT: Static rules only

# Gap 4: No plugin ecosystem
# Cursor: 1000+ extensions
# AI_SUPPORT: No plugin system

# Gap 5: No team features
# Cursor: PR comments, reviews, assignments
# AI_SUPPORT: Single user only
```

---

## 7. Thiết kế Subagent tự cải thiện

### Architecture Diagram (Text-based)

```
┌─────────────────────────────────────────────────────────────────┐
│                    AI_SUPPORT SELF-IMPROVEMENT AGENT             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   SCAN      │───▶│   ANALYZE   │───▶│   DETECT    │         │
│  │   Module    │    │   Module    │    │   Gaps      │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│        │                  │                  │                  │
│        ▼                  ▼                  ▼                  │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              GAP ANALYSIS ENGINE                     │       │
│  │   - Missing features (A-E criteria)                │       │
│  │   - Code quality issues                            │       │
│  │   - Test coverage gaps                             │       │
│  │   - Pattern violations                             │       │
│  └─────────────────────────────────────────────────────┘       │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              CODE GENERATOR                          │       │
│  │   - Generate fix code for each gap                  │       │
│  │   - Follow project patterns                         │       │
│  │   - Include tests                                   │       │
│  └─────────────────────────────────────────────────────┘       │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │   VERIFY    │◀───│   APPLY     │───▶│   TEST      │         │
│  │   Module    │    │   Module    │    │   Module    │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│                          │                                      │
│                          ▼                                      │
│  ┌─────────────────────────────────────────────────────┐       │
│  │              ITERATION LOOP                         │       │
│  │   While score < 100%:                               │       │
│  │     1. Generate improvements                        │       │
│  │     2. Run tests                                    │       │
│  │     3. Update score                                 │       │
│  │     4. If test fails → rollback & retry             │       │
│  └─────────────────────────────────────────────────────┘       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Subagent Prompt (subagent_prompt.md)

```markdown
# AI_SUPPORT Self-Improvement Subagent Prompt

## Role
You are the AI_SUPPORT Self-Improvement Agent. Your mission is to 
continuously improve AI_SUPPORT until it reaches 100% Cursor-like 
capability for code review tasks (software only, NOT hardware).

## Objective
Iteratively improve AI_SUPPORT based on the 5 evaluation criteria:
- A: Analysis Accuracy (target: 100%)
- B: Rule Completeness (target: 100+ rules)
- C: Output Quality (target: Cursor-quality reports)
- D: CLI/UX Integration (target: Full Cursor UX)
- E: Extensibility (target: Plugin ecosystem)

## Current Score
- Total: 72%
- A: 75% (AST analysis good, need data flow)
- B: 65% (28 rules, need 100+)
- C: 70% (Good formatting, need highlighting)
- D: 78% (Slash commands good, need autocomplete)
- E: 72% (Extensible, need plugin discovery)

## Workflow Steps

### Step 1: Scan All Source Code
```
1.1. Read all files in src/
1.2. Read all test files in tests/
1.3. Identify module boundaries
1.4. Map current capabilities
```

### Step 2: Analyze Against Criteria
```
For each module:
  - Check against Criterion A (accuracy)
  - Check against Criterion B (rules)
  - Check against Criterion C (output)
  - Check against Criterion D (UX)
  - Check against Criterion E (extensibility)
```

### Step 3: Detect Gaps
```
3.1. Compare with Cursor capabilities
3.2. Identify missing features
3.3. Prioritize by impact on score
3.4. Generate gap list with severity
```

### Step 4: Generate Fixes
```
For each gap:
  4.1. Read relevant existing code
  4.2. Generate new/improved code
  4.3. Follow project patterns
  4.4. Include unit tests
  4.5. Update imports if needed
```

### Step 5: Verify & Iterate
```
5.1. Run relevant unit tests
5.2. If tests pass → commit changes
5.3. If tests fail → rollback & retry
5.4. Recalculate score
5.5. If score < 100% → repeat
```

## Tooling Requirements

### Required Tools
- File read/write
- AST parsing (Python)
- Test runner (pytest)
- Git for versioning

### Quality Gates
- All tests must pass
- No linting errors
- Type hints required
- Docstrings required

## Output Format

After each iteration, report:
```markdown
## Iteration N Results

### Gaps Fixed
- [List of fixes applied]

### Tests Added
- [List of new tests]

### Score Update
- A: old% → new%
- B: old% → new%
- C: old% → new%
- D: old% → new%
- E: old% → new%
- Total: old% → new%

### Remaining Gaps
- [List of gaps still to fix]

### Next Steps
- [Priority list for next iteration]
```

## Constraints

1. **Software ONLY**: Do not modify hardware/embedded code
2. **Preserve existing functionality**: Backward compatible
3. **Follow patterns**: Match existing code style
4. **Test coverage**: New code must have tests
5. **No breaking changes**: Maintain API compatibility

## Success Criteria

Iteration completes when:
- All unit tests pass
- Score ≥ 90% for all criteria
- Total score ≥ 95%

## Files to Modify

Priority order:
1. `src/infrastructure/analysis/rule_engine.py` (B: +rules)
2. `src/infrastructure/analysis/ml_detectors/detector.py` (A: +accuracy)
3. `src/application/workflows/unified/result_formatter.py` (C: +quality)
4. `src/interfaces/cli/commands/slash.py` (D: +UX)
5. `src/infrastructure/` (E: +extensibility)

## Example Fix Generation

### Gap: Missing TypeScript deep analysis

**Current code:**
```python
# src/infrastructure/analysis/rule_engine.py:49-50
SUPPORTED_LANGUAGES: frozenset[str] = frozenset({
    "python", "javascript", "typescript", ...
})
# No deep TypeScript analysis
```

**Generated fix:**
```python
# NEW FILE: src/infrastructure/analysis/languages/typescript.py
"""TypeScript deep analysis module."""

from dataclasses import dataclass
from typing import Optional

from ..rule_engine import Rule, Finding, Severity

@dataclass
class TypeScriptRule(Rule):
    """Base class for TypeScript-specific rules."""
    language: str = "typescript"
    
    def detect(self, content: str, file_path: str) -> list[Finding]:
        raise NotImplementedError

class TSNoImplicitAny(TypeScriptRule):
    """Detect implicit any type annotations."""
    rule_id = "TS7006"
    
    def detect(self, content: str, file_path: str) -> list[Finding]:
        findings = []
        for match in self._find_implicit_any(content):
            findings.append(Finding(
                rule_id=self.rule_id,
                severity=Severity.ERROR,
                file=file_path,
                line=match.line,
                message=f"Parameter '{match.name}' implicitly has an 'any' type",
            ))
        return findings
    
    def _find_implicit_any(self, content: str) -> list[Match]:
        # AST-based detection
        ...
```

---

BEGIN EXECUTION
```

### Complete `subagent_prompt.md` File Content

```markdown
# AI_SUPPORT Self-Improvement Agent
# Version: 1.0
# Target: 100% Cursor-like for software code review

## 1. AGENT OVERVIEW

**Name:** ai-support-improver  
**Purpose:** Automatically improve AI_SUPPORT until it matches Cursor capabilities  
**Scope:** Software code review ONLY (no hardware/embedded)  
**Target Score:** ≥95% total, ≥90% per criterion

## 2. CURRENT STATE ASSESSMENT

### Scores by Criterion
| Criterion | Current | Target | Gap |
|-----------|---------|--------|-----|
| A: Analysis Accuracy | 75% | 100% | 25% |
| B: Rule Completeness | 65% | 100% | 35% |
| C: Output Quality | 70% | 100% | 30% |
| D: CLI/UX | 78% | 100% | 22% |
| E: Extensibility | 72% | 100% | 28% |
| **TOTAL** | **72%** | **95%** | **23%** |

### Key Gaps Identified
1. **B-1:** Only 28 rules (need 100+)
2. **A-1:** No data flow analysis
3. **C-1:** No syntax highlighting in output
4. **D-1:** No inline autocomplete
5. **E-1:** No plugin discovery system

## 3. EXECUTION WORKFLOW

### Phase 1: Scan (5 minutes)
```
1. List all source files in src/
2. List all test files in tests/
3. Map modules to criteria
4. Identify existing capabilities
```

### Phase 2: Gap Analysis (10 minutes)
```
For each module:
  1. Read module source
  2. Evaluate against 5 criteria
  3. Identify specific gaps
  4. Prioritize by impact
```

### Phase 3: Fix Generation (15 minutes per gap)
```
For each high-priority gap:
  1. Read related existing code
  2. Design solution
  3. Generate code
  4. Write unit tests
  5. Update documentation
```

### Phase 4: Verification (10 minutes)
```
1. Run pytest on modified modules
2. Check linting
3. Verify type hints
4. Measure score improvement
```

### Phase 5: Iterate (loop until target)
```
If score < 95%:
  Go to Phase 2
Else:
  Generate completion report
```

## 4. GAP PRIORITY MATRIX

| Gap ID | Criterion | Impact | Effort | Priority |
|--------|-----------|--------|--------|----------|
| B-1 | B: +35 rules | High | Medium | P0 |
| A-1 | A: Data flow | High | High | P1 |
| C-1 | C: Highlighting | Medium | Low | P1 |
| D-1 | D: Autocomplete | High | High | P2 |
| E-1 | E: Plugin system | Medium | High | P2 |

## 5. CODE GENERATION RULES

### File Naming
- Tests: `tests/unit/test_<module>.py`
- Implementation: `src/<layer>/<module>.py`
- Type hints: Required for all functions
- Docstrings: Required for all public functions

### Pattern Examples

#### New Rule Pattern
```python
# src/infrastructure/analysis/rules/<category>/<rule_name>.py
"""<Rule description>."""

from dataclasses import dataclass
from typing import Optional

from ..rule_engine import Rule, Finding, Severity

@dataclass
class <RuleName>Rule(Rule):
    """<One-line description>.
    
    Extended description if needed.
    """
    
    rule_id: str = "<CATEGORY><NUMBER>"
    severity: Severity = Severity.WARNING
    
    def detect(self, content: str, file_path: str) -> list[Finding]:
        """Detect <issue> in source code.
        
        Args:
            content: Source code content
            file_path: Path to source file
            
        Returns:
            List of findings
        """
        findings = []
        # Implementation
        return findings
```

#### Test Pattern
```python
# tests/unit/test_<rule_name>.py
"""Tests for <RuleName>Rule."""

import pytest
from src.infrastructure.analysis.rules.<category>.<rule_name> import <RuleName>Rule

class Test<RuleName>Rule:
    """Test suite for <RuleName>Rule."""
    
    def test_detects_<issue>(self):
        """Should detect <specific issue>."""
        rule = <RuleName>Rule()
        code = '''
def example():
    # problematic code
    pass
'''
        findings = rule.detect(code, "test.py")
        assert len(findings) == 1
        assert findings[0].rule_id == "<CATEGORY><NUMBER>"
```

## 6. SUCCESS METRICS

### Quantitative
- Total score ≥ 95%
- Each criterion ≥ 90%
- Test coverage ≥ 80%
- No linting errors

### Qualitative
- Output matches Cursor format
- Commands behave like Cursor
- Rules cover same ground as Cursor

## 7. ROLLBACK PROCEDURE

If tests fail after change:
1. Revert changed files
2. Log failure reason
3. Retry with modified approach
4. If still failing, skip to next gap

## 8. REPORTING TEMPLATE

```markdown
# Self-Improvement Report - Iteration N

## Summary
- Started at: X%
- Ended at: Y%
- Changes: Z files modified
- Tests: W tests added

## Changes Made
### Files Created
- list of new files

### Files Modified
- list of modified files

### Files Deleted
- list of deleted files

## Test Results
- Total tests: N
- Passed: M
- Failed: K
- Coverage: O%

## Score Update
| Criterion | Before | After |
|-----------|--------|-------|
| A | 75% | XX% |
| B | 65% | XX% |
| C | 70% | XX% |
| D | 78% | XX% |
| E | 72% | XX% |
| TOTAL | 72% | XX% |

## Remaining Gaps
1. Gap description
2. ...

## Next Iteration Plan
1. Priority task
2. ...
```

---

BEGIN: Scan all source files and begin gap analysis
```
```

---

## 8. Lộ trình 3 giai đoạn đến 100%

### P0: Giai đoạn 1 - Tuần 1 (Critical Gaps)

**Mục tiêu:** Đạt 80% tổng điểm

#### Tasks

| Task | Module | Time | Description |
|------|--------|------|-------------|
| P0-1 | rule_engine | 4h | Thêm 20 rules mới (security, quality) |
| P0-2 | ml_detectors | 6h | Implement data flow analysis |
| P0-3 | typescript | 4h | Deep TypeScript/React analysis |
| P0-4 | tests | 3h | Viết tests cho new rules |

#### Specific Implementations

```python
# P0-1: Add 20 rules to src/infrastructure/analysis/rules/

# NEW: security/sql_injection.py
class SQLInjectionRule(Rule):
    """Detect SQL injection vulnerabilities."""
    rule_id = "SEC001"
    severity = Severity.CRITICAL
    
    def detect(self, content: str, file_path: str) -> list[Finding]:
        findings = []
        # Pattern: f"SELECT * FROM {user_input}"
        # Pattern: "SELECT * FROM " + variable
        # Pattern: cursor.execute(f"...".format(...))
        for match in re.finditer(SQL_INJECTION_PATTERNS, content):
            findings.append(Finding(
                rule_id=self.rule_id,
                severity=self.severity,
                file=file_path,
                line=match.start(),
                message="Potential SQL injection",
                fix=self._generate_fix(match),
            ))
        return findings

# NEW: security/hardcoded_secret.py
class HardcodedSecretRule(Rule):
    """Detect hardcoded passwords, API keys, tokens."""
    rule_id = "SEC002"
    
    PATTERNS = [
        r'password\s*=\s*["\'](?!xxx|placeholder)',
        r'api[_-]?key\s*=\s*["\'][a-zA-Z0-9]{20,}',
        r'secret\s*=\s*["\'][a-zA-Z0-9]{32,}',
        r'token\s*=\s*["\'][a-zA-Z0-9_\-]{20,}',
    ]

# NEW: quality/cognitive_complexity.py
class CognitiveComplexityRule(Rule):
    """Detect high cognitive complexity."""
    rule_id = "QUAL001"
    
    def detect(self, content: str, file_path: str) -> list[Finding]:
        for func in extract_functions(content):
            complexity = calculate_cognitive_complexity(func)
            if complexity > 15:
                yield Finding(
                    rule_id=self.rule_id,
                    severity=Severity.WARNING,
                    file=file_path,
                    line=func.start_line,
                    message=f"Cognitive complexity {complexity} exceeds threshold 15",
                )

# Continue for 17 more rules...
```

```python
# P0-2: Add data flow analysis to src/infrastructure/analysis/data_flow.py
class DataFlowAnalyzer:
    """Track variable values through code."""
    
    def analyze(self, content: str, file_path: str) -> DataFlowGraph:
        """Build data flow graph for file."""
        
        # 1. Parse AST
        tree = ast.parse(content)
        
        # 2. Track assignments
        assignments = self._track_assignments(tree)
        
        # 3. Track uses
        uses = self._track_uses(tree)
        
        # 4. Build flow graph
        flow_graph = DataFlowGraph()
        for var, assigns in assignments.items():
            for use in uses.get(var, []):
                flow_graph.add_edge(assigns, use)
        
        return flow_graph
    
    def detect_taint(self, content: str) -> list[TaintFinding]:
        """Detect tainted data flow (user input → dangerous operation)."""
        flow = self.analyze(content, "")
        taint_sources = ["input(", "request.args", "request.form"]
        taint_sinks = ["execute(", "eval(", "open("]
        
        findings = []
        for path in flow.paths:
            if path.source in taint_sources and path.sink in taint_sinks:
                findings.append(TaintFinding(
                    source=path.source,
                    sink=path.sink,
                    severity=Severity.CRITICAL,
                ))
        return findings
```

#### Time Estimate
- **Total:** 17 giờ (1 dev full-time)
- P0-1: 4h
- P0-2: 6h
- P0-3: 4h
- P0-4: 3h

---

### P1: Giai đoạn 2 - Tuần 2 (High Priority)

**Mục tiêu:** Đạt 90% tổng điểm

#### Tasks

| Task | Module | Time | Description |
|------|--------|------|-------------|
| P1-1 | result_formatter | 4h | Add syntax highlighting to output |
| P1-2 | CLI | 6h | Implement autocomplete system |
| P1-3 | rules | 4h | Add 30 more rules |
| P1-4 | tests | 4h | Expand test coverage |

#### Specific Implementations

```python
# P1-1: Syntax highlighting in src/application/workflows/unified/result_formatter.py

from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import Terminal256Formatter

class SyntaxHighlightedCode:
    """Add syntax highlighting to code blocks."""
    
    THEME = "monokai"  # or cursor-dark, atom-one-dark
    
    def highlight_code(self, code: str, language: str) -> str:
        """Highlight code with syntax colors."""
        try:
            lexer = get_lexer_by_name(language)
        except:
            lexer = guess_lexer(code)
        
        formatter = Terminal256Formatter(style=self.THEME)
        return highlight(code, lexer, formatter)
    
    def format_finding(self, finding: Finding) -> str:
        """Format finding with highlighted code."""
        old_code = finding.metadata.get("old_code", "")
        new_code = finding.metadata.get("new_code", "")
        language = self._detect_language(finding.file)
        
        return f"""
## {finding.rule_id}: {finding.message}

**File:** `{finding.file}:{finding.line}`
**Severity:** {finding.severity.value}

### Before (problematic)
```{language}
{self.highlight_code(old_code, language)}
```

### After (fixed)
```{language}
{self.highlight_code(new_code, language)}
```
"""
```

```python
# P1-2: Autocomplete in src/interfaces/cli/autocomplete.py

import readline
from typing import Callable

class AutocompleteEngine:
    """Provide Tab autocomplete for CLI."""
    
    COMMANDS = ["/fix", "/review", "/explain", "/refactor", "/test"]
    FILES_CACHE = []
    
    def __init__(self):
        readline.parse_and_bind("tab: complete")
        readline.set_completer(self._complete)
    
    def _complete(self, text: str, state: int) -> str:
        """Readline completion callback."""
        tokens = text.split()
        
        if len(tokens) == 0:
            return None
        
        if tokens[0] == "/":
            # Complete command names
            matches = [c for c in self.COMMANDS if c.startswith(text)]
        elif tokens[0] == "@":
            # Complete file paths
            matches = [f"@{f}" for f in self.FILES_CACHE if f.startswith(tokens[1])]
        else:
            matches = []
        
        return matches[state] if state < len(matches) else None
    
    def update_files_cache(self, workspace: Path):
        """Refresh file cache for autocomplete."""
        self.FILES_CACHE = [
            str(f.relative_to(workspace))
            for f in workspace.rglob("*.py")
        ]
```

#### Time Estimate
- **Total:** 18 giờ (1 dev full-time)
- P1-1: 4h
- P1-2: 6h
- P1-3: 4h
- P1-4: 4h

---

### P2: Giai đoạn 3 - Tuần 3 (Polish & Testing)

**Mục tiêu:** Đạt 95-100% tổng điểm

#### Tasks

| Task | Module | Time | Description |
|------|--------|------|-------------|
| P2-1 | plugin | 6h | Implement plugin discovery system |
| P2-2 | collaboration | 4h | Add team review features |
| P2-3 | llm | 8h | Integrate LLM for smart fixes |
| P2-4 | testing | 4h | Full integration testing |

#### Specific Implementations

```python
# P2-1: Plugin system in src/infrastructure/plugins/

class PluginDiscovery:
    """Discover and load plugins from directory."""
    
    PLUGIN_DIR = ".ai_support/plugins"
    
    def discover(self) -> list[Plugin]:
        """Find all available plugins."""
        plugins = []
        plugin_path = Path(self.PLUGIN_DIR)
        
        if not plugin_path.exists():
            return plugins
        
        for entry in plugin_path.iterdir():
            if entry.is_dir() and (entry / "plugin.json").exists():
                plugin = self._load_plugin(entry)
                if self._validate_plugin(plugin):
                    plugins.append(plugin)
        
        return plugins
    
    def _load_plugin(self, path: Path) -> Plugin:
        """Load plugin from directory."""
        with open(path / "plugin.json") as f:
            manifest = json.load(f)
        
        # Load plugin module
        spec = importlib.util.spec_from_file_location(
            "plugin", path / manifest["main"]
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        return Plugin(
            manifest=manifest,
            module=module,
            path=path,
        )
```

```python
# P2-3: LLM integration in src/core/fix_engine/llm_fixer.py

from openai import AsyncOpenAI

class LLMFixGenerator:
    """Generate fixes using LLM."""
    
    def __init__(self, api_key: str = None):
        self.client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))
    
    async def generate_fix(
        self,
        finding: Finding,
        context: CodeContext,
    ) -> FixSuggestion:
        """Generate contextual fix using LLM."""
        
        prompt = f"""You are an expert code reviewer. Fix this issue:

FILE: {context.file_path}
LINE: {finding.line}
ISSUE: {finding.message}
SEVERITY: {finding.severity.value}

CODE CONTEXT:
```{context.language}
{context.get_surrounding_code(finding.line, lines=10)}
```

REQUIREMENTS:
1. Fix the root cause, not just symptoms
2. Maintain code style consistency
3. Ensure the fix is minimal and focused
4. Consider edge cases and error handling

Respond with:
```json
{{
    "fix": "the corrected code",
    "explanation": "brief explanation of the fix",
    "tests_needed": ["description of test cases"]
}}
```
"""
        
        response = await self.client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        
        return self._parse_response(response)
```

#### Time Estimate
- **Total:** 22 giờ (1 dev full-time)
- P2-1: 6h
- P2-2: 4h
- P2-3: 8h
- P2-4: 4h

---

### Summary Roadmap

| Giai đoạn | Tuần | Mục tiêu | Tasks | Time |
|-----------|------|----------|-------|------|
| P0 | 1 | 80% | 4 tasks | 17h |
| P1 | 2 | 90% | 4 tasks | 18h |
| P2 | 3 | 95-100% | 4 tasks | 22h |
| **Total** | **3 weeks** | **95-100%** | **12 tasks** | **57h** |

---

## 9. Output mẫu hoàn hảo

### Khi đạt 100% Cursor-like

```markdown
# Code Review Report
Generated by AI_SUPPORT v1.0 | 2026-05-31 10:47 AM

## Summary

| Metric | Value |
|--------|-------|
| Files Reviewed | 42 |
| Total Issues | 127 |
| Critical | 3 ⚠️ |
| High | 15 |
| Medium | 45 |
| Low | 64 |
| Duration | 2.3s |

---

## Critical Issues

### 🚨 [SEC001] SQL Injection in user_auth.py:142

**Severity:** CRITICAL  
**Confidence:** 98%  
**Detector:** LLM-powered analysis

**Problematic Code:**
```python
def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    cursor.execute(query)  # ❌ SQL Injection!
    return cursor.fetchone()
```

**Suggested Fix:**
```python
def get_user(user_id):
    query = "SELECT * FROM users WHERE id = %s"
    cursor.execute(query, (user_id,))  # ✅ Parameterized
    return cursor.fetchone()
```

**Explanation:** User-controlled input is directly interpolated into SQL query. An attacker could inject malicious SQL to extract sensitive data or modify database.

**Tests Needed:**
```python
def test_get_user_sql_injection():
    # Should not execute malicious input
    result = get_user("1; DROP TABLE users;")
    assert result is None
    assert "DROP" not in captured_query
```

---

### 🚨 [SEC002] Hardcoded API Key in config.py:15

**Severity:** HIGH  
**Confidence:** 95%

**Problematic Code:**
```python
API_KEY = "sk_live_abc123xyz789..."  # ❌ Exposed!
```

**Suggested Fix:**
```python
API_KEY = os.getenv("API_KEY")  # ✅ Environment variable
if not API_KEY:
    raise ValueError("API_KEY environment variable required")
```

---

## High Priority Issues

### [QUAL001] Cognitive Complexity in order_processor.py:45
**Complexity:** 23 (threshold: 15)  
**Recommendation:** Extract nested conditions into separate functions

### [QUAL002] Memory Leak in cache_manager.py:89
**Issue:** Dict growing unboundedly  
**Recommendation:** Implement LRU eviction

### [TS001] TypeScript: Implicit Any in api.ts:34
**Issue:** Parameter `data` has implicit 'any' type  
**Fix:** Add explicit type annotation

---

## Quick Fix Actions

```bash
# Apply all critical fixes automatically
ai-support --apply --severity=critical

# Apply specific rule fixes
ai-support --apply --rule=SEC001,SEC002

# Preview before applying
ai-support --preview --diff
```

---

## Interactive Mode

```
> ai-support /review @src/auth/

🔍 Analyzing auth module...
✅ Completed in 1.2s

Found 8 issues:

1. [CRITICAL] SQL Injection (SEC001)
   Location: user_auth.py:142
   Fix available: [Apply] [Skip] [Explain]
   
2. [HIGH] Hardcoded Secret (SEC002)
   Location: config.py:15
   Fix available: [Apply] [Skip] [Explain]

Command: _
```

---

## Comparison with Current Output

| Feature | Current (72%) | Target (100%) |
|---------|--------------|---------------|
| Severity icons | ⚠️ | 🚨 (animated) |
| Code highlighting | ❌ | ✅ Pygments |
| LLM explanations | ❌ | ✅ GPT-4 |
| Interactive mode | Basic | Full TUI |
| Fix previews | Text diff | Side-by-side |
| Test generation | ❌ | ✅ Auto |

---

*Report generated by AI_SUPPORT - Your local Cursor alternative*
```

---

## Kết luận cuối cùng

AI_SUPPORT đã đạt **72%** khả năng của Cursor trong tác vụ code review. Với lộ trình 3 tuần và 57 giờ phát triển, hệ thống có thể đạt **95-100%** tương đương Cursor cho các tác vụ software code review.

**Ưu điểm của AI_SUPPORT:**
- ✅ Open source, có thể customize
- ✅ Embedded systems focus
- ✅ Extensible architecture
- ✅ ML-specific detection

**Cần cải thiện:**
- ⚠️ Rules (28 → 100+)
- ⚠️ LLM integration cho smart fixes
- ⚠️ Syntax highlighting
- ⚠️ Autocomplete system
- ⚠️ Plugin ecosystem

---

*Báo cáo được tạo tự động bởi AI_SUPPORT Evaluation Agent*
*Ngày: 2026-05-31*
