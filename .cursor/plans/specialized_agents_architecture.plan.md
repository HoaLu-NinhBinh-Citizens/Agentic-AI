# Plan: Implement Specialized AI Agents Architecture

## Mục tiêu
Xây dựng hệ thống 7 specialized AI agents nhẹ, mỗi agent làm MỘT việc và làm tốt nhất.

## Architecture Overview

```
Orchestrator (Lightweight)
├── PDF Agent       → KB từ datasheets
├── CodeGen Agent   → Generate firmware code
├── Review Agent    → Code review + traceability
├── Build Agent     → Compile code
├── Flash Agent     → Flash xuống board
├── Test Agent      → Unit tests + regression
└── DevOps Agent    → CI/CD + build health
```

## Agents Specification

### 1. PDF Agent (Agent 1 - Đã có)
**Responsibility:** Parse PDF datasheets → Structured KB

**Input:** PDF file path
**Output:** KB với citations (metadata.json, chunks.json, tables.json)
**Tool:** PyMuPDF, pytesseract OCR

```python
class PDFAgent:
    def run(pdf_path, project_name) -> KBResult
```

### 2. CodeGen Agent (Tái sử dụng EmbeddedCAgent)
**Responsibility:** Generate firmware code từ task + KB

**Input:** Task description + KB citations
**Output:** Generated .c/.h files
**Tool:** LLM (Ollama/OpenAI)

```python
class CodeGenAgent:
    def generate(task, kb_citations, allowed_outputs) -> CodeResult
```

### 3. Review Agent
**Responsibility:** Validate generated code against spec

**Input:** Generated code + KB citations + spec
**Output:** Approved/Rejected + findings
**Tool:** LLM + local rules

```python
class ReviewAgent:
    def review(code, spec, kb_citations) -> ReviewResult
    # Rules:
    # - Every register use must have citation
    # - Every peripheral config must be documented
    # - No hallucinated APIs
```

### 4. Build Agent
**Responsibility:** Compile code → ELF file

**Input:** Source files path
**Output:** ELF file + build log
**Tool:** GCC, make

```python
class BuildAgent:
    def build(source_path, project_name, target) -> BuildResult:
        # Tái sử dụng BuildTools từ EmbeddedCAgent
```

### 5. Flash Agent
**Responsibility:** Flash ELF → Hardware board

**Input:** ELF file path + target device
**Output:** Flash result + verification
**Tool:** J-Link, ST-Link, SEGGER

```python
class FlashAgent:
    def flash(elf_path, device, hardware_id) -> FlashResult:
        # Safety: --dry-run flag
        # Verify: đọc lại flash để verify
```

### 6. Test Agent ⭐ (NEW)
**Responsibility:** Automated testing cho firmware

**Input:** Generated code + KB spec + previous test results
**Output:** Test report + coverage + regression status
**Tool:** pytest, CUnit, hardware tests

```python
class TestAgent:
    def run_tests(code_path, kb_spec, target) -> TestResult:
        # Unit tests từ register spec
        # Integration tests với peripherals
        # Regression vs previous builds
```

### 7. DevOps Agent ⭐ (NEW - RIÊNG)
**Responsibility:** CI/CD pipeline + build health monitoring

**Input:** Build events + flash results + test results
**Output:** Pipeline status + health dashboard + alerts
**Tool:** Git hooks, monitoring, notifications

```python
class DevOpsAgent:
    def monitor() -> HealthReport:
        # Track: success rate, common failures, trends
        # Alert: khi success rate drop
        # Optimize: suggest improvements
```

## Data Flow

```
User Task
    │
    ▼
┌─────────────────────────────────────────────┐
│ Orchestrator (Task Router)                   │
│ - Classify task type                        │
│ - Determine required agents                 │
│ - Aggregate results                         │
└─────────────────────────────────────────────┘
    │
    ├──► PDF Agent ──────────────────────► KB
    │                                            │
    │◄──────────────────────────────────────────┘
    │
    ├──► CodeGen Agent ◄────────────────── KB
    │           │
    │           ▼
    │      Review Agent ◄────────────── KB
    │           │
    │           │ Approved?
    │           ▼
    │      Build Agent
    │           │
    │           │ ELF ready?
    │           ▼
    │      Flash Agent
    │           │
    │           │ Flash success?
    │           ▼
    │      Test Agent ──────────────────► Report
    │           │
    └───────────┴──────────────────────────► Result
                        │
                        ▼
              DevOps Agent (background)
                        │
                        ▼
              Health Dashboard
```

## Implementation Phases

### Phase 1: Foundation
- [x] Create agent base class interface
- [x] Create orchestrator/task router
- [x] Define agent communication protocol

### Phase 2: Core Agents
- [x] PDF Agent (adapt from existing)
- [x] CodeGen Agent (adapt from EmbeddedCAgent)
- [x] Review Agent (adapt from existing review logic)

### Phase 3: Build/Flash Agents
- [x] Build Agent (adapt from BuildTools)
- [x] Flash Agent (new, safe implementation)
- [x] Dry-run mode for safety

### Phase 4: Test + DevOps Agents
- [x] Test Agent (new)
- [x] DevOps Agent (new)

## Shared Memory Schema

```python
@dataclass
class SharedMemory:
    # KB Store
    kb_entries: Dict[str, KBEntry]  # KB cache by file hash

    # Build History
    build_history: List[BuildRecord]  # timestamp, success, duration

    # Flash History
    flash_history: List[FlashRecord]  # device, success, ELF hash

    # Test History
    test_history: List[TestRecord]  # coverage, failures, regressions

    # Citation Store (từ Agent 1)
    citations: Dict[str, Citation]  # Evidence citations

@dataclass
class BuildRecord:
    timestamp: datetime
    source_hash: str
    elf_hash: str
    success: bool
    duration_ms: int
    error: str

@dataclass
class FlashRecord:
    timestamp: datetime
    device: str
    elf_hash: str
    success: bool
    verification_passed: bool
```

## File Structure

```
AI_support/
├── multi_agent/
│   ├── __init__.py
│   ├── base.py                 # Agent base class
│   ├── orchestrator.py         # Task router
│   ├── pdf_agent.py            # Agent 1 (existing)
│   ├── codegen_agent.py        # Code generation
│   ├── review_agent.py         # Code review
│   ├── build_agent.py          # Build compilation
│   ├── flash_agent.py          # Hardware flash
│   ├── test_agent.py           # Test automation
│   ├── devops_agent.py         # CI/CD + monitoring
│   └── memory.py               # Shared memory store
```

## Safety Considerations

1. **Flash Agent**:
   - Always support `--dry-run`
   - Verify ELF hash before flash
   - Verify flash after flash
   - Rollback capability

2. **Build Agent**:
   - Sandbox build environment
   - Prevent arbitrary code execution
   - Validate output paths

3. **DevOps Agent**:
   - Read-only by default
   - Alert-only for external systems
   - Audit log for all actions

## Questions Before Implementation

### Đã xác định:

1. **Test Agent Framework**: Unity Test
   - Phổ biến nhất cho embedded C
   - Nhẹ, dễ integrate
   - Có mock support (Unity + CMock)

2. **DevOps Integration**: Git Hooks
   - Auto build/test on commit
   - Pre-commit: build check
   - Post-commit: test + flash notification

3. **Orchestrator**: Stateful với context persistence
   - Giữ context giữa các agent calls
   - Shared memory cho cross-agent communication
