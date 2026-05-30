"""ML/AI-specific static analysis rules for code review.

DEPRECATED: Use src.infrastructure.analysis.ml_detectors instead.
This module will be removed in v2.0.
"""

from __future__ import annotations
import warnings

warnings.warn(
    "ml_rules.py is deprecated. Use ml_detectors instead.",
    DeprecationWarning,
    stacklevel=2
)
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
import re

# ─── Severity ────────────────────────────────────────────────────────────────

class MLSeverity(Enum):
    CRITICAL = "critical"  # Data leakage, wrong loss
    HIGH = "high"           # Device mismatch, missing no_grad
    MEDIUM = "medium"       # Missing seeds, hardcoded params

# ─── Rule definition ────────────────────────────────────────────────────────

@dataclass
class MLRule:
    id: str
    name: str
    description: str
    severity: MLSeverity
    patterns: list[str]
    fix_template: str = ""
    cwe_id: str = ""
    tags: list[str] = field(default_factory=list)

    def match(self, content: str) -> list[re.Match]:
        compiled = [re.compile(p, re.MULTILINE) for p in self.patterns]
        matches = []
        for p in compiled:
            matches.extend(p.finditer(content))
        return sorted(matches, key=lambda m: m.start())


@dataclass
class MLFinding:
    rule_id: str
    rule_name: str
    severity: MLSeverity
    file: str
    line: int
    message: str
    fix: str
    confidence: float = 1.0
    matched_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "fix": self.fix,
            "confidence": self.confidence,
            "matched_text": self.matched_text,
        }


# ─── ML Rules Registry ─────────────────────────────────────────────────────

ML_RULES: list[MLRule] = [
    # CRITICAL
    MLRule(
        id="ML001",
        name="data-leakage-scaler",
        description="Scaler fit before train/test split leaks information",
        severity=MLSeverity.CRITICAL,
        patterns=[
            r'\.fit\s*\(',
            r'\.fit_transform\s*\(',
        ],
        fix_template="Fit scaler only on training data: scaler.fit(X_train); scaler.transform(X_test)",
        cwe_id="CWE-69",
        tags=["ml", "data-leakage", "critical"],
    ),
    MLRule(
        id="ML002",
        name="data-leakage-encoding",
        description="Encoder fit on full dataset before split",
        severity=MLSeverity.CRITICAL,
        patterns=[
            r'(LabelEncoder|OneHotEncoder|StandardScaler|MinMaxScaler)\s*\([^)]*\)\s*\.fit\s*\([^)]*(?:train|test|split)',
        ],
        fix_template="Fit encoder on training data only, then transform both train and test",
        cwe_id="CWE-69",
        tags=["ml", "data-leakage", "critical"],
    ),
    MLRule(
        id="ML003",
        name="wrong-loss-multi-label",
        description="CrossEntropyLoss used for multi-label classification (should use BCEWithLogitsLoss)",
        severity=MLSeverity.CRITICAL,
        patterns=[
            r'CrossEntropyLoss\s*\(\s*\)',
            r'nn\.CrossEntropyLoss\s*\(\s*\)',
            r'nn\.BCEWithLogitsLoss\s*\([^)]*reduction\s*=\s*[\'"]none[\'"]',
        ],
        fix_template="For multi-label: use nn.BCEWithLogitsLoss() or nn.BCELoss(). For multi-class: CrossEntropyLoss is correct.",
        cwe_id="CWE-710",
        tags=["ml", "loss-function", "critical"],
    ),
    MLRule(
        id="ML004",
        name="wrong-loss-binary-single",
        description="BCEWithLogitsLoss used for single-label binary classification (should use CrossEntropyLoss)",
        severity=MLSeverity.CRITICAL,
        patterns=[
            r'BCEWithLogitsLoss\s*\(\s*\)',
            r'BCELoss\s*\(\s*\)',
        ],
        fix_template="For single-label binary classification: use nn.CrossEntropyLoss() which handles the sigmoid internally.",
        cwe_id="CWE-710",
        tags=["ml", "loss-function", "critical"],
    ),
    # HIGH
    MLRule(
        id="ML005",
        name="device-mismatch",
        description="Model and data on different devices causes runtime error",
        severity=MLSeverity.HIGH,
        patterns=[
            r'\.to\s*\(\s*device\s*\)',
            r'\.cuda\s*\(\s*\)',
        ],
        fix_template="Ensure data tensors are moved to same device: data = data.to(model.device) or data = data.cuda()",
        cwe_id="CWE-754",
        tags=["ml", "device", "runtime-error"],
    ),
    MLRule(
        id="ML006",
        name="missing-no-grad-inference",
        description="Inference code missing torch.no_grad() causes memory leak",
        severity=MLSeverity.HIGH,
        patterns=[
            r'(?:model|train|fit|predict|evaluate)\s*\(.*?\)\s*:(?:\s*\n\s*[^#]*?\n){1,20}(?!.*(?:no_grad|torch\.inference_mode))',
        ],
        fix_template="Wrap inference in: with torch.no_grad(): or with torch.inference_mode():",
        cwe_id="CWE-401",
        tags=["ml", "memory", "inference"],
    ),
    MLRule(
        id="ML007",
        name="missing-seed-cuda",
        description="CUDA non-determinism without torch.backends.cudnn.deterministic",
        severity=MLSeverity.HIGH,
        patterns=[
            r'torch\.manual_seed\s*\(',
            r'np\.random\.seed\s*\(',
            r'random\.seed\s*\(',
        ],
        fix_template="Add: torch.backends.cudnn.deterministic = True; torch.backends.cudnn.benchmark = False",
        cwe_id="CWE-665",
        tags=["ml", "reproducibility"],
    ),
    MLRule(
        id="ML008",
        name="missing-any-seed",
        description="No random seed set - training is not reproducible",
        severity=MLSeverity.MEDIUM,
        patterns=[
            r'def\s+(?:train|fit|main)\s*\(',
        ],
        fix_template="Add reproducibility seed block: import random, numpy, torch; set seeds for all",
        cwe_id="CWE-665",
        tags=["ml", "reproducibility", "medium"],
    ),
    MLRule(
        id="ML009",
        name="hardcoded-hyperparams",
        description="Batch size, learning rate, or other hyperparams hardcoded",
        severity=MLSeverity.MEDIUM,
        patterns=[
            r'batch_size\s*=\s*[0-9]+(?!.*config)',
            r'lr\s*=\s*0\.[0-9]+(?!.*config)',
            r'learning_rate\s*=\s*0\.[0-9]+(?!.*config)',
            r'epochs?\s*=\s*[0-9]+(?!.*config)',
            r'n_estimators\s*=\s*[0-9]+(?!.*config)',
        ],
        fix_template="Move hyperparams to config dict or CLI args: config['batch_size'] or args.batch_size",
        cwe_id="CWE-94",
        tags=["ml", "config", "medium"],
    ),
    MLRule(
        id="ML010",
        name="dropout-inference",
        description="Dropout active during inference mode",
        severity=MLSeverity.MEDIUM,
        patterns=[
            r'(?:eval|train)\s*\(\s*\)\s*(?:\n\s*[^#]*?){1,5}(?!.*\.eval\s*\(\s*\))',
        ],
        fix_template="Call model.eval() before inference and model.train() before training",
        cwe_id="CWE-754",
        tags=["ml", "inference", "dropout"],
    ),
]


# ─── ML Rule Engine ───────────────────────────────────────────────────────────

class MLRuleEngine:
    def __init__(self):
        self._rules: dict[str, MLRule] = {r.id: r for r in ML_RULES}

    def detect(self, file_path: str, content: str) -> list[MLFinding]:
        findings = []
        for rule in self._rules.values():
            for match in rule.match(content):
                line_num = content[:match.start()].count("\n") + 1
                matched_text = match.group()
                findings.append(MLFinding(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    file=file_path,
                    line=line_num,
                    message=f"[{rule.id}] {rule.name}: {rule.description}",
                    fix=rule.fix_template,
                    confidence=0.85,
                    matched_text=matched_text,
                ))
        return findings

    def get_stats(self, findings: list[MLFinding]) -> dict[str, Any]:
        by_sev = {s.value: 0 for s in MLSeverity}
        for f in findings:
            by_sev[f.severity.value] += 1
        return {
            "total": len(findings),
            "by_severity": by_sev,
            "files": len({f.file for f in findings}),
        }
