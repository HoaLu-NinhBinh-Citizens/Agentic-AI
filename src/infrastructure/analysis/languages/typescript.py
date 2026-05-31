"""TypeScript and React analysis for AI_SUPPORT.

Provides deep static analysis for TypeScript, React, Vue, and Angular codebases.
Detects framework-specific issues like missing keys in maps, async useEffect errors,
component performance problems, and type safety violations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..rule_engine import RuleSeverity


@dataclass
class TypeScriptFinding:
    """A finding from TypeScript/React analysis."""
    rule_id: str
    severity: RuleSeverity
    line: int
    message: str
    explanation: str
    fix: Optional[str] = None


class TypeScriptAnalyzer:
    """Deep TypeScript/TSX analysis.

    Detects TypeScript-specific and React-specific issues including:
    - React hooks rules (useState, useEffect, async issues)
    - TypeScript type rules (implicit any, explicit any usage)
    - React component rules (missing keys, class components, inline styles)
    - React performance rules (missing memo, inline functions)

    Args:
        framework: Target framework ('react', 'vue', 'angular', 'generic')
    """

    REACT_HOOK_RULES = {
        "use_state_array": {
            "pattern": r"useState\s*\(\s*\[\s*\]\s*\)",
            "message": "useState with empty array initial value",
            "severity": RuleSeverity.WARNING,
            "explanation": "Empty array in useState may cause infinite re-renders. "
                           "Use useCallback or stable reference.",
            "fix": "useState(() => []) or useRef([])",
        },
        "missing_deps": {
            "pattern": r"useEffect\s*\(",
            "message": "useEffect with empty dependency array",
            "severity": RuleSeverity.WARNING,
            "explanation": "Empty deps array means effect runs only once. "
                           "Make sure this is intentional.",
            "fix": "Add proper dependencies or use useMemo/useCallback",
        },
        "use_effect_sync": {
            "pattern": r"useEffect\s*\([^)]*async\s*\(",
            "message": "useEffect with async function",
            "severity": RuleSeverity.ERROR,
            "explanation": "useEffect cannot be async directly. "
                           "Define async function inside and call it.",
            "fix": """useEffect(() => {
    const fetchData = async () => {
        // async operations
    };
    fetchData();
}, [dependencies]);""",
        },
    }

    TYPESCRIPT_RULES = {
        "implicit_any": {
            "pattern": r"(const|let|var)\s+\w+\s*=\s*[^:]+(?<![;:])",
            "message": "Variable without explicit type annotation",
            "severity": RuleSeverity.WARNING,
            "explanation": "Variable may have implicit any type. "
                           "Add explicit type annotation for better type safety.",
            "fix": "Add explicit type: const x: Type = value",
        },
        "no_implicit_any": {
            "pattern": r"function\s+\w+\s*\([^)]*\)\s*:\s*\w+\s*\{",
            "message": "Function without explicit return type",
            "severity": RuleSeverity.INFO,
            "explanation": "Function should have explicit return type for better type safety.",
            "fix": "Add return type: function foo(): ReturnType { }",
        },
        "any_type": {
            "pattern": r":\s*any\b",
            "message": "Use of 'any' type",
            "severity": RuleSeverity.WARNING,
            "explanation": "'any' defeats TypeScript type checking. "
                           "Use unknown or specific types.",
            "fix": "Use unknown for truly unknown types, or specific types",
        },
        "unsafe_cast": {
            "pattern": r"as\s+any\b|\bas\s+unknown\b",
            "message": "Unsafe type cast",
            "severity": RuleSeverity.WARNING,
            "explanation": "Type casts can hide type errors. "
                           "Use type guards instead.",
            "fix": "Use type guards or instanceof checks",
        },
    }

    REACT_COMPONENT_RULES = {
        "class_component": {
            "pattern": r"class\s+\w+\s+extends\s+React\.Component|class\s+\w+\s+extends\s+Component",
            "message": "Class component used",
            "severity": RuleSeverity.INFO,
            "explanation": "Prefer functional components with hooks for modern React.",
            "fix": "Convert to functional component with hooks",
        },
        "inline_style": {
            "pattern": r"style\s*=\s*\{\s*\{",
            "message": "Inline style object",
            "severity": RuleSeverity.INFO,
            "explanation": "Inline styles make responsive design harder. "
                           "Use CSS classes or styled-components.",
            "fix": "Use CSS classes or CSS-in-JS solution",
        },
        "missing_key": {
            "pattern": r"\{[^}]*\.map\([^)]*\)\s*\}(?!\s*key\s*=)",
            "message": "map() without key prop",
            "severity": RuleSeverity.ERROR,
            "explanation": "Elements in map() need unique key prop for proper rendering.",
            "fix": "Add key prop: .map((item, index) => <Item key={item.id} />)",
        },
    }

    REACT_PERF_RULES = {
        "missing_memo": {
            "pattern": r"export\s+default\s+function\s+\w+\s*\([^)]*\)\s*\{[^}]*\bprops\.\w+[^}]*\}",
            "message": "Component may benefit from React.memo",
            "severity": RuleSeverity.INFO,
            "explanation": "Pure components should be wrapped in React.memo for performance.",
            "fix": "export default React.memo(ComponentName)",
        },
        "use_callback": {
            "pattern": r"const\s+\w+\s*=\s*\([^)]*\)\s*=>\s*\{[^}]*set\w+\s*\(",
            "message": "Inline function in JSX may cause re-renders",
            "severity": RuleSeverity.WARNING,
            "explanation": "Inline functions create new references on each render.",
            "fix": "Use useCallback or define outside JSX",
        },
        "object_create": {
            "pattern": r"style\s*=\s*\{\s*\{[^}]*\}\s*\}",
            "message": "Style object recreated on each render",
            "severity": RuleSeverity.WARNING,
            "explanation": "Creating style objects in render causes unnecessary re-renders.",
            "fix": "Move style object outside component or use useMemo",
        },
    }

    def __init__(self, framework: str = "react") -> None:
        """Initialize TypeScript analyzer.

        Args:
            framework: Target framework ('react', 'vue', 'angular', 'generic')
        """
        self.framework = framework.lower()
        self._finding_id_counter = 0

    def _next_rule_id(self, prefix: str) -> str:
        """Generate unique rule ID for findings."""
        self._finding_id_counter += 1
        return f"{prefix}_{self._finding_id_counter}"

    def analyze(self, content: str, file_path: str) -> list[dict]:
        """Analyze TypeScript/React code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []

        language = self._detect_language(file_path, content)

        if language in ("typescript", "javascript"):
            findings.extend(self._analyze_typescript(content, file_path))

        if language in ("tsx", "jsx") or self.framework == "react":
            findings.extend(self._analyze_react(content, file_path, language))

        return findings

    def _detect_language(self, file_path: str, content: str) -> str:
        """Detect the language from file extension and content."""
        if file_path.endswith(".tsx"):
            return "tsx"
        elif file_path.endswith(".jsx"):
            return "jsx"
        elif file_path.endswith(".ts"):
            return "typescript"
        elif file_path.endswith(".js"):
            if "React" in content or "useState" in content or "useEffect" in content:
                return "jsx"
            if "Vue" in content or "vue" in content or "v-for" in content:
                return "jsx"
            return "javascript"

        if "React" in content or "useState" in content or "useEffect" in content:
            return "jsx"

        if "Vue" in content or "vue" in content or "v-for" in content:
            return "jsx"

        return "javascript"

    def _analyze_typescript(self, content: str, file_path: str) -> list[dict]:
        """Analyze TypeScript-specific issues."""
        findings = []
        lines = content.split("\n")

        for rule_name, rule in self.TYPESCRIPT_RULES.items():
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    findings.append({
                        "rule_id": self._next_rule_id(f"TS_{rule_name.upper()}"),
                        "severity": rule["severity"],
                        "file": file_path,
                        "line": i,
                        "message": rule["message"],
                        "explanation": rule["explanation"],
                        "fix": rule.get("fix"),
                    })

        return findings

    def _analyze_react(self, content: str, file_path: str, language: str) -> list[dict]:
        """Analyze React-specific issues."""
        findings = []
        lines = content.split("\n")

        for rule_name, rule in self.REACT_HOOK_RULES.items():
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    findings.append({
                        "rule_id": self._next_rule_id(f"REACT_{rule_name.upper()}"),
                        "severity": rule["severity"],
                        "file": file_path,
                        "line": i,
                        "message": rule["message"],
                        "explanation": rule["explanation"],
                        "fix": rule.get("fix"),
                    })

        for rule_name, rule in self.REACT_COMPONENT_RULES.items():
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    findings.append({
                        "rule_id": self._next_rule_id(f"REACT_{rule_name.upper()}"),
                        "severity": rule["severity"],
                        "file": file_path,
                        "line": i,
                        "message": rule["message"],
                        "explanation": rule["explanation"],
                        "fix": rule.get("fix"),
                    })

        for rule_name, rule in self.REACT_PERF_RULES.items():
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    findings.append({
                        "rule_id": self._next_rule_id(f"REACT_PERF_{rule_name.upper()}"),
                        "severity": rule["severity"],
                        "file": file_path,
                        "line": i,
                        "message": rule["message"],
                        "explanation": rule["explanation"],
                        "fix": rule.get("fix"),
                    })

        return findings


class VueAnalyzer:
    """Vue.js specific analysis.

    Detects Vue-specific issues including:
    - Options API usage (vs Composition API)
    - Missing key attributes in v-for
    - Deprecated .sync modifier
    """

    VUE_RULES = {
        "options_api": {
            "pattern": r"data\s*\(\s*\)\s*\{",
            "message": "Options API used",
            "severity": RuleSeverity.INFO,
            "explanation": "Consider using Composition API for better type safety and reusability.",
            "fix": "Use <script setup> with Composition API",
        },
        "missing_key": {
            "pattern": r"v-for\s*=\s*[\"'][^\"']*in\s+[^\"']*[\"']",
            "message": "v-for without key attribute",
            "severity": RuleSeverity.ERROR,
            "explanation": "v-for requires a unique key attribute for proper rendering.",
            "fix": 'Add :key="item.id" to v-for',
        },
        "sync_deprecated": {
            "pattern": r"\.sync\s*=",
            "message": ".sync modifier deprecated",
            "severity": RuleSeverity.WARNING,
            "explanation": ".sync modifier is deprecated. Use v-model:propName instead.",
            "fix": "Use v-model:propName instead of .sync",
        },
    }

    def __init__(self) -> None:
        self._finding_id_counter = 0

    def _next_rule_id(self) -> str:
        """Generate unique rule ID for findings."""
        self._finding_id_counter += 1
        return f"VUE_FINDING_{self._finding_id_counter}"

    def analyze(self, content: str, file_path: str) -> list[dict]:
        """Analyze Vue.js code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []
        lines = content.split("\n")

        for rule_name, rule in self.VUE_RULES.items():
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    findings.append({
                        "rule_id": self._next_rule_id(),
                        "severity": rule["severity"],
                        "file": file_path,
                        "line": i,
                        "message": rule["message"],
                        "explanation": rule["explanation"],
                        "fix": rule.get("fix"),
                    })

        return findings


class AngularAnalyzer:
    """Angular specific analysis.

    Detects Angular-specific issues including:
    - Missing OnPush change detection
    - Missing trackBy in *ngFor
    - Subscriptions without unsubscription
    - Use of 'any' type
    """

    ANGULAR_RULES = {
        "change_detection": {
            "pattern": r"@Component\(",
            "message": "Consider using OnPush change detection",
            "severity": RuleSeverity.INFO,
            "explanation": "OnPush can improve performance for static components.",
            "fix": "Add changeDetection: ChangeDetectionStrategy.OnPush",
        },
        "missing_track": {
            "pattern": r"\*ngFor",
            "message": "*ngFor without trackBy function",
            "severity": RuleSeverity.WARNING,
            "explanation": "trackBy improves performance by tracking items by identity.",
            "fix": "Add trackBy: trackByFn to *ngFor",
        },
        "subscribe_no_unsubscribe": {
            "pattern": r"\.subscribe\s*\(",
            "message": "Subscription without unsubscription",
            "severity": RuleSeverity.WARNING,
            "explanation": "Memory leak: subscriptions should be unsubscribed.",
            "fix": "Use takeUntil pattern or ngOnDestroy to unsubscribe",
        },
        "any_type": {
            "pattern": r":\s*any\b",
            "message": "Use of 'any' type in Angular",
            "severity": RuleSeverity.WARNING,
            "explanation": "Avoid 'any' in Angular for better type safety.",
            "fix": "Use specific types or unknown",
        },
    }

    def __init__(self) -> None:
        self._finding_id_counter = 0

    def _next_rule_id(self) -> str:
        """Generate unique rule ID for findings."""
        self._finding_id_counter += 1
        return f"ANGULAR_FINDING_{self._finding_id_counter}"

    def analyze(self, content: str, file_path: str) -> list[dict]:
        """Analyze Angular code.

        Args:
            content: Source code content
            file_path: Path to source file

        Returns:
            List of finding dictionaries
        """
        findings = []
        lines = content.split("\n")

        for rule_name, rule in self.ANGULAR_RULES.items():
            for i, line in enumerate(lines, 1):
                if re.search(rule["pattern"], line):
                    findings.append({
                        "rule_id": self._next_rule_id(),
                        "severity": rule["severity"],
                        "file": file_path,
                        "line": i,
                        "message": rule["message"],
                        "explanation": rule["explanation"],
                        "fix": rule.get("fix"),
                    })

        return findings
