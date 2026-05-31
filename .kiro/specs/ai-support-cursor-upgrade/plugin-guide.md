# Kiro AI IDE — Plugin Development Guide

## Overview

Plugins extend Kiro AI IDE functionality through a standardized interface. Plugins can add custom rules, new LLM providers, report formats, and integrations.

## Plugin Structure

```
my-plugin/
├── plugin.json          # Manifest
├── __init__.py         # Entry point
├── rules/              # Custom rules
│   ├── __init__.py
│   └── my_rules.py
├── providers/          # Custom LLM providers
│   └── my_provider.py
└── static/             # Static assets
    └── icon.svg
```

## Plugin Manifest

```json
{
  "name": "my-custom-plugin",
  "version": "1.0.0",
  "description": "Custom rules for my organization",
  "author": "Your Name <email@example.com>",
  "entry_point": "my_plugin",
  "dependencies": {
    "requests": ">=2.28.0"
  },
  "permissions": ["read", "analyze"],
  "allowed_imports": ["json", "re", "requests"],
  "hooks": {
    "on_analysis_complete": "my_plugin.handle_analysis",
    "on_finding": "my_plugin.handle_finding"
  },
  "min_kiro_version": "1.0.0"
}
```

## Plugin Lifecycle

### States

```
DISCOVERED → LOADED → ACTIVE → INACTIVE → UNLOADED
    ↓
  ERROR
```

### Lifecycle Methods

```python
# __init__.py

class MyPlugin:
    def __init__(self, config: dict):
        self.config = config
        self.rules = []
    
    def on_discover(self) -> None:
        """Called when plugin is discovered."""
        pass
    
    def on_load(self) -> None:
        """Called when plugin is loaded."""
        self.rules = self._load_rules()
    
    def on_activate(self) -> None:
        """Called when plugin is activated."""
        for rule in self.rules:
            self.engine.register_rule(rule)
    
    def on_deactivate(self) -> None:
        """Called when plugin is deactivated."""
        for rule in self.rules:
            self.engine.unregister_rule(rule.id)
    
    def on_unload(self) -> None:
        """Called when plugin is unloaded."""
        self.rules = []
```

## Custom Rules

### Rule Structure

```python
from kiro.rule_engine import BaseRule, Finding, Severity

class MyCustomRule(BaseRule):
    id = "MYORG001"
    name = "Custom Security Check"
    description = "Detects custom security patterns"
    severity = Severity.HIGH
    languages = ["python"]
    category = "security"
    
    def detect(self, file_path: str, content: str, ast: AST) -> list[Finding]:
        findings = []
        for node in ast.walk():
            if self._is_vulnerable(node):
                findings.append(Finding(
                    file=file_path,
                    line=node.lineno,
                    rule_id=self.id,
                    severity=self.severity,
                    message=f"Vulnerable pattern at line {node.lineno}",
                    code_context=self._get_context(content, node.lineno),
                    fix_template=self._get_fix(node)
                ))
        return findings
    
    def _is_vulnerable(self, node) -> bool:
        # Custom detection logic
        return False
    
    def _get_fix(self, node) -> str:
        return "Suggested fix code here"
```

### Rule Registration

```python
def get_rules() -> list[type[BaseRule]]:
    return [MyCustomRule]
```

## Custom LLM Providers

### Provider Interface

```python
from kiro.llm import BaseLLMProvider

class MyLLMProvider(BaseLLMProvider):
    name = "my-provider"
    
    def __init__(self, api_key: str, model: str = "default"):
        self.api_key = api_key
        self.model = model
    
    async def generate(
        self,
        prompt: str,
        context: dict = None,
        **kwargs
    ) -> str:
        # Call your LLM API
        response = await self._call_api(prompt, context)
        return response.text
    
    async def generate_stream(
        self,
        prompt: str,
        context: dict = None,
        **kwargs
    ):
        # Streaming response
        async for chunk in self._stream_api(prompt, context):
            yield chunk
    
    async def _call_api(self, prompt: str, context: dict) -> Response:
        raise NotImplementedError
    
    def validate_config(self, config: dict) -> bool:
        return "api_key" in config
```

### Provider Registration

```python
def get_providers() -> dict[str, type[BaseLLMProvider]]:
    return {
        "my-provider": MyLLMProvider
    }
```

## Custom Report Formats

```python
from kiro.reporting import BaseReportFormat, ReportContext

class MyCustomFormat(BaseReportFormat):
    name = "custom"
    extension = "myfmt"
    
    def render(self, context: ReportContext) -> str:
        # Generate custom format output
        output = []
        output.append("=== ANALYSIS REPORT ===")
        output.append(f"Files: {context.stats.files_analyzed}")
        output.append(f"Findings: {context.stats.total_findings}")
        
        for finding in context.findings:
            output.append(f"\n[{finding.severity}] {finding.file}:{finding.line}")
            output.append(f"  {finding.message}")
        
        return "\n".join(output)
```

## Event Hooks

### Available Hooks

| Hook | Arguments | Description |
|------|-----------|-------------|
| `on_startup` | `None` | Called when Kiro starts |
| `on_shutdown` | `None` | Called when Kiro stops |
| `on_analysis_complete` | `context: AnalysisContext` | After analysis finishes |
| `on_finding` | `finding: Finding` | On each finding |
| `on_error` | `error: Exception` | On error occurs |
| `on_session_create` | `session: Session` | On new session |
| `on_llm_request` | `request: LLMRequest` | Before LLM call |
| `on_llm_response` | `response: LLMResponse` | After LLM call |

### Hook Implementation

```python
def on_analysis_complete(context: AnalysisContext):
    """Handle analysis completion."""
    if context.stats.total_findings > 100:
        send_slack_notification(
            "High number of findings detected!"
        )
```

## Testing Plugins

### Test Structure

```
tests/
├── test_my_plugin.py
└── fixtures/
    └── test_code.py
```

### Test Example

```python
import pytest
from my_plugin import MyCustomRule

class TestMyCustomRule:
    @pytest.fixture
    def rule(self):
        return MyCustomRule()
    
    def test_detects_vulnerability(self, rule):
        code = """
def vulnerable_func(x):
    exec(x)  # Dangerous!
"""
        findings = rule.detect("test.py", code, parse(code))
        
        assert len(findings) == 1
        assert findings[0].severity == Severity.HIGH
        assert findings[0].line == 3
    
    def test_no_false_positives(self, rule):
        code = """
def safe_func(x):
    print(x)
"""
        findings = rule.detect("test.py", code, parse(code))
        assert len(findings) == 0
```

### Local Testing

```bash
# Validate manifest
kiro plugin validate ./my-plugin

# Install locally for testing
kiro plugin install ./my-plugin

# Run with plugin
kiro analyze --with-plugin=my-custom-plugin src/

# View plugin logs
kiro doctor --plugin=my-custom-plugin
```

## Publishing Plugins

### Package Structure

```
my-custom-plugin-1.0.0/
├── plugin.json
├── pyproject.toml
├── README.md
└── src/
    └── my_plugin/
        ├── __init__.py
        └── rules/
            └── __init__.py
```

### pyproject.toml

```toml
[project]
name = "kiro-my-plugin"
version = "1.0.0"
description = "My custom Kiro plugin"
requires-python = ">=3.10"

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio"]

[tool.kiro]
plugin = true
```

## Best Practices

1. **Minimal Dependencies** — Keep dependencies to a minimum
2. **Error Handling** — Wrap all external calls in try/except
3. **Logging** — Use structured logging for debugging
4. **Performance** — Avoid blocking operations in hooks
5. **Security** — Validate all user inputs
6. **Testing** — Write comprehensive tests
7. **Documentation** — Document all configuration options
8. **Versioning** — Follow semantic versioning
