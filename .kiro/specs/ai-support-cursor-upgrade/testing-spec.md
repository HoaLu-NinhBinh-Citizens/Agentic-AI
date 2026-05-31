# Kiro AI IDE — Testing Specification

## Test Categories

### 1. Unit Tests

**Location:** `tests/unit/`

**Purpose:** Test individual components in isolation

**Coverage Requirements:**
- Rule engine registration and execution
- Call graph building and queries
- Data flow analysis
- Session management
- Plugin discovery

### 2. Integration Tests

**Location:** `tests/integration/`

**Purpose:** Test interactions between components

**Test Cases:**

#### Rule Engine + Call Graph
- Verify findings include correct call site context
- Test cross-file detection via call graph

#### Call Graph + Data Flow
- Verify taint tracking across function calls
- Test alias resolution in data flow

#### Incremental Indexer + Rule Engine
- Verify stale findings removed on file change
- Test watch mode event handling

#### Plugin Manager + Rule Engine
- Verify custom rules registered from plugins
- Test hot-reload with rule updates

### 3. End-to-End Tests

**Location:** `tests/e2e/`

**Purpose:** Test complete workflows

**Test Scenarios:**

1. **Full Analysis Pipeline**
   ```
   Input: Source files with known vulnerabilities
   Process: analyze command
   Expected: All vulnerabilities detected with correct locations
   ```

2. **Watch Mode Analysis**
   ```
   Input: Running kiro analyze --watch
   Action: Modify source file
   Expected: Incremental analysis within 3 seconds
   ```

3. **LLM Fix Generation**
   ```
   Input: Finding without fix_template
   Process: Request LLM fix
   Expected: Valid fix suggestion generated
   ```

4. **PR Report Generation**
   ```
   Input: Analysis with comments and resolutions
   Process: kiro report --format=markdown
   Expected: Complete report with statistics
   ```

## Test Data

### Sample Files

**Location:** `tests/fixtures/`

| File | Purpose |
|------|---------|
| `sql_injection.py` | SQL injection vulnerabilities |
| `xss_vulnerability.py` | XSS vulnerabilities |
| `missing_auth.py` | Missing authentication |
| `unsafe_redirect.py` | Open redirect vulnerabilities |
| `weak_crypto.py` | Weak cryptography usage |
| `import_alias.py` | Import alias patterns |
| `taint_sources.py` | Taint source patterns |
| `react_hooks.pyx` | React hooks patterns |

### Expected Findings

Each fixture has corresponding `*.expected.json`:

```json
{
  "file": "sql_injection.py",
  "findings": [
    {
      "line": 42,
      "rule_id": "SEC001",
      "severity": "CRITICAL"
    }
  ]
}
```

## Test Fixtures Structure

```
tests/
├── fixtures/
│   ├── python/
│   │   ├── security/
│   │   │   ├── sql_injection.py
│   │   │   └── sql_injection.expected.json
│   │   └── quality/
│   ├── typescript/
│   │   └── react/
│   └── config/
├── unit/
│   ├── test_rule_engine.py
│   ├── test_call_graph.py
│   ├── test_data_flow.py
│   └── test_session_manager.py
├── integration/
│   ├── test_rule_callgraph_integration.py
│   ├── test_incremental_indexing.py
│   └── test_plugin_lifecycle.py
└── e2e/
    ├── test_analyze_command.py
    └── test_watch_mode.py
```

## Mock Objects

### Mock LLM Provider
```python
class MockLLMProvider:
    def generate(self, prompt: str) -> str:
        return "Mocked fix suggestion"
    
    async def generate_stream(self, prompt: str):
        for token in ["Mocked", " fix", " suggestion"]:
            yield token
```

### Mock File System
```python
class MockFileSystem:
    def __init__(self, files: dict[str, str]):
        self.files = files
    
    def read(self, path: str) -> str:
        return self.files[path]
    
    def mtime(self, path: str) -> float:
        return 0.0
```

## Test Execution

### Run All Tests
```bash
python -m pytest tests/
```

### Run Specific Category
```bash
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/e2e/
```

### Run with Coverage
```bash
python -m pytest --cov=src --cov-report=html tests/
```

### Run Specific Test
```bash
python -m pytest tests/unit/test_rule_engine.py::test_register_rule
```

## Performance Benchmarks

### Target Metrics

| Operation | Target | Max |
|-----------|--------|-----|
| Unit test suite | < 10s | 30s |
| Integration test suite | < 30s | 60s |
| E2E test suite | < 60s | 120s |

### Benchmarking
```bash
python -m pytest tests/ --benchmark-only
```

## CI Integration

### Pre-commit Hook
```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: kiro-tests
        name: Run Tests
        entry: python -m pytest tests/
        language: system
        pass_filenames: false
```

### GitHub Actions
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: python -m pytest tests/ --cov=src
```

## Test Data Sanitization

- No real credentials in test fixtures
- No production API keys
- Use `faker` for generated test data
- Anonymize any file paths containing real usernames
