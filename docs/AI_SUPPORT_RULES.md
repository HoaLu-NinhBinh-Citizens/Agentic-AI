# AI_SUPPORT Rule Reference

## Overview

AI_SUPPORT includes 121+ built-in rules for comprehensive code analysis covering security, performance, quality, and more.

## Rule Categories

### Security Rules (41 rules)

| Rule ID | Name | Severity | Description | CWE |
|---------|------|----------|-------------|-----|
| SEC001 | hardcoded-secret | ERROR | Hardcoded API key, token, password, or secret detected | CWE-798 |
| SEC002 | sql-injection | ERROR | Potential SQL injection via string concatenation | CWE-89 |
| SEC003 | command-injection | ERROR | Shell command injection risk via subprocess with shell=True | CWE-78 |
| SEC004 | path-traversal | ERROR | Potential path traversal vulnerability | CWE-22 |
| SEC005 | eval-usage | WARNING | Use of eval() or exec() is a security risk | CWE-95 |
| SEC006 | insecure-random | WARNING | Using random.random() for security purposes | CWE-338 |
| SEC007 | hardcoded-password | ERROR | Hardcoded password detected | CWE-259 |
| SEC008 | xss | CRITICAL | Cross-site scripting vulnerability | CWE-79 |
| SEC009 | unsafe-redirect | WARNING | Unvalidated redirect | CWE-601 |
| SEC010 | insecure-deserialization | ERROR | Unsafe deserialization | CWE-502 |

### Type Safety Rules (4 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| TYPE001 | untyped-function | INFO | Python function without type hints |
| TYPE002 | any-usage | HINT | Function using 'Any' type annotation |
| TYPE003 | missing-return-type | INFO | Public function missing return type annotation |
| TYPE004 | type-mismatch | WARNING | Potential type mismatch in comparison |

### Import Analysis Rules (4 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| IMP001 | unused-import | INFO | Imported module not used in the file |
| IMP002 | circular-import | WARNING | Potential circular import detected |
| IMP003 | wildcard-import | WARNING | Wildcard import (from X import *) reduces clarity |
| IMP004 | relative-import | INFO | Relative import used |

### Naming Convention Rules (4 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| NAME001 | snake-case-function | INFO | Function name should use snake_case |
| NAME002 | PascalCase-class | INFO | Class name should use PascalCase |
| NAME003 | UPPER_CASE-constant | INFO | Module-level constant should use UPPER_CASE |
| NAME004 | single-letter-variable | HINT | Avoid single-letter variable names |

### Code Quality Rules (10 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| QUAL001 | long-function | WARNING | Function exceeds 50 lines |
| QUAL002 | nested-callbacks | WARNING | Callback/Promise nesting exceeds 3 levels |
| QUAL003 | broad-except | WARNING | Bare except or except Exception catches everything |
| QUAL004 | empty-except | WARNING | Empty except block without logging |
| QUAL005 | TODO-FIXME | INFO | Unresolved TODO/FIXME/XXX comment found |
| QUAL006 | print-statement | HINT | Print statement used instead of logging |
| QUAL007 | magic-number | INFO | Magic number detected |
| QUAL008 | consecutive-blank-lines | HINT | Multiple consecutive blank lines detected |
| QUAL009 | trailing-whitespace | HINT | Lines with trailing whitespace |
| QUAL010 | cyclomatic-complexity | WARNING | Function cyclomatic complexity exceeds 10 |

### Performance Rules (30 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| PERF001 | n-plus-one-query | MEDIUM | N+1 query patterns |
| PERF002 | regex-in-loop | MEDIUM | Regex compiled in loop |
| PERF003 | sync-in-async | HIGH | Blocking calls in async |
| PERF004 | inefficient-list-concat | MEDIUM | Inefficient list concatenation |
| PERF005 | nested-queries | MEDIUM | Nested database queries |
| PERF006 | large-data-copy | MEDIUM | Unnecessary large data copying |
| PERF007 | inefficient-string-concat | LOW | Inefficient string concatenation |
| PERF008 | missing-index | MEDIUM | Database table missing index |
| PERF009 | memory-leak | HIGH | Potential memory leak |
| PERF010 | resource-not-closed | WARNING | Resource not properly closed |

### Framework-Specific Rules

#### FastAPI Rules (6 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| FAST001 | sync-in-async-route | HIGH | Sync function in async route |
| FAST002 | missing-validation | MEDIUM | Missing request validation |
| FAST003 | verbose-error | WARNING | Verbose error messages in production |
| FAST004 | missing-rate-limit | MEDIUM | Missing rate limiting |
| FAST005 | insecure-cors | WARNING | Overly permissive CORS |
| FAST006 | missing-deps-injection | INFO | Missing dependency injection |

#### Django Rules (5 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| DJANGO001 | csrf-missing | HIGH | Missing CSRF protection |
| DJANGO002 | raw-query | MEDIUM | Raw SQL query usage |
| DJANGO003 | select-related | MEDIUM | Missing select_related/prefetch_related |
| DJANGO004 | mass-assignment | HIGH | Mass assignment vulnerability |
| DJANGO005 | debug-in-production | ERROR | Debug mode enabled in production |

#### React Rules (4 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| REACT001 | missing-key-prop | WARNING | List element missing key prop |
| REACT002 | stale-closure | WARNING | Stale closure in useEffect |
| REACT003 | missing-deps | WARNING | Missing dependency in useEffect |
| REACT004 | imperative-after-declarative | INFO | Imperative DOM manipulation after render |

### Testing Rules (10 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| TEST001 | missing-tests | INFO | No test coverage |
| TEST002 | assertion-in-loop | WARNING | Assertion inside loop |
| TEST003 | commented-code | INFO | Commented-out code detected |
| TEST004 | skipped-test | INFO | Skipped test found |
| TEST005 | flaky-test | WARNING | Potentially flaky test |
| TEST006 | hardcoded-test-data | INFO | Hardcoded test data |
| TEST007 | no-mock | MEDIUM | Missing mock usage |
| TEST008 | weak-assertion | INFO | Weak test assertion |
| TEST009 | long-test | MEDIUM | Test exceeds recommended duration |
| TEST010 | test-coverage-gap | INFO | Critical code path without tests |

### Documentation Rules (5 rules)

| Rule ID | Name | Severity | Description |
|---------|------|----------|-------------|
| DOC001 | missing-docstring | INFO | Missing module/class/function docstring |
| DOC002 | outdated-docstring | INFO | Outdated docstring |
| DOC003 | missing-parameter-doc | INFO | Missing parameter documentation |
| DOC004 | missing-return-doc | INFO | Missing return value documentation |
| DOC005 | broken-link | WARNING | Broken documentation link |

## Severity Levels

| Level | Numeric | Description |
|-------|---------|-------------|
| ERROR | 1.0 | Critical issues requiring immediate attention |
| WARNING | 0.7 | Important issues that should be addressed |
| INFO | 0.4 | Informational notices |
| HINT | 0.2 | Suggestions for improvement |

## Custom Rules

Create custom rules by implementing the Rule interface:

```python
from dataclasses import dataclass
from src.infrastructure.analysis.rule_engine import Rule, RuleSeverity

@dataclass
class MyCustomRule(Rule):
    rule_id: str = "CUSTOM001"
    name: str = "my-custom-rule"
    description: str = "Description of what this rule detects"
    severity: RuleSeverity = RuleSeverity.WARNING
    languages: list = None

    def __post_init__(self):
        if self.languages is None:
            self.languages = ["python"]

    def match(self, content: str) -> list:
        import re
        pattern = re.compile(r'your_pattern_here')
        return pattern.finditer(content)
```

## Plugin System

AI_SUPPORT supports a plugin system for extending functionality. See `.ai_support/plugins/example/` for a demo plugin.

### Plugin Structure

```
.ai_support/plugins/
└── example/
    ├── plugin.json      # Plugin manifest
    └── plugin.py        # Plugin code
```

### Plugin Manifest

```json
{
    "name": "example-plugin",
    "version": "1.0.0",
    "description": "Example plugin for AI_SUPPORT",
    "author": "Your Name",
    "main": "plugin.py",
    "entry_point": "register",
    "min_ai_support_version": "1.0.0",
    "hooks": ["on_finding_found", "on_review_start", "on_review_complete"]
}
```

### Available Hooks

| Hook | Description | Parameters |
|------|-------------|------------|
| `on_review_start` | Called before review starts | `context: dict` |
| `on_review_complete` | Called after review completes | `results: dict` |
| `on_finding_found` | Called for each finding | `finding: dict` |
| `on_fix_applied` | Called when a fix is applied | `fix: dict` |

### Example Plugin

```python
def on_finding_found(finding):
    """Modify or filter findings."""
    if finding and 'TODO' in str(finding.get('message', '')):
        finding['source'] = 'example-plugin'
    return finding
```

## Usage Examples

### Basic Rule Detection

```python
from src.infrastructure.analysis.rule_engine import RuleEngine

engine = RuleEngine()
findings = engine.detect("path/to/file.py", "python")

for finding in findings:
    print(f"{finding.rule_id}: {finding.message}")
```

### Running Full Analysis

```python
from src.infrastructure.analysis.rule_engine import RuleEngine

engine = RuleEngine()
all_findings = engine.detect_all("path/to/project")

stats = engine.get_stats(all_findings)
print(f"Total issues: {stats['total']}")
print(f"By severity: {stats['by_severity']}")
```

### Integration with Plugins

```python
from src.infrastructure.plugins.discovery import PluginDiscovery

discovery = PluginDiscovery()
discovery.discover()

# Run review with plugins
results = discovery.execute_hook('on_review_start', context)
```
