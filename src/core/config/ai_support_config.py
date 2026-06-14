"""Configuration loader for AI_SUPPORT with YAML + env var override support."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


@dataclass
class RuleConfig:
    enabled: bool = True
    severity_threshold: str = "info"
    max_function_lines: int = 50
    max_nesting_depth: int = 3
    max_cyclomatic_complexity: int = 10


@dataclass
class MLRuleConfig:
    check_data_leakage: bool = True
    check_device_mismatch: bool = True
    check_no_grad: bool = True
    check_deterministic: bool = True
    check_loss_function: bool = True
    check_hardcoded_params: bool = True


@dataclass
class IndexingConfig:
    incremental: bool = True
    watch_mode: bool = False
    debounce_seconds: float = 2.0
    concurrency: int = 4
    max_file_size_mb: int = 10


@dataclass
class OutputConfig:
    format: str = "rich"  # rich, json, plain, markdown
    include_code_context: int = 3
    show_confidence: bool = True
    color: bool = True


@dataclass
class AISupportConfig:
    rules: RuleConfig = field(default_factory=RuleConfig)
    ml_rules: MLRuleConfig = field(default_factory=MLRuleConfig)
    indexing: IndexingConfig = field(default_factory=IndexingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)

    def __post_init__(self) -> None:
        AISupportConfig._apply_env_overrides(self)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> AISupportConfig:
        if config_path is None:
            config_path = os.environ.get(
                "AI_SUPPORT_CONFIG",
                str(Path(__file__).parent.parent.parent.parent / "configs" / "ai_support_rules.yaml")
            )

        cfg = cls()
        path = Path(config_path)
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            cfg = cls._from_dict(data)

        # Override with env vars
        cls._apply_env_overrides(cfg)
        return cfg

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> AISupportConfig:
        rules_data = data.get("rules", {})
        ml_data = data.get("ml_rules", {})
        idx_data = data.get("indexing", {})
        out_data = data.get("output", {})
        return AISupportConfig(
            rules=RuleConfig(
                enabled=rules_data.get("enabled", True),
                severity_threshold=rules_data.get("severity_threshold", "info"),
                max_function_lines=rules_data.get("max_function_lines", 50),
                max_nesting_depth=rules_data.get("max_nesting_depth", 3),
                max_cyclomatic_complexity=rules_data.get("max_cyclomatic_complexity", 10),
            ),
            ml_rules=MLRuleConfig(
                check_data_leakage=ml_data.get("check_data_leakage", True),
                check_device_mismatch=ml_data.get("check_device_mismatch", True),
                check_no_grad=ml_data.get("check_no_grad", True),
                check_deterministic=ml_data.get("check_deterministic", True),
                check_loss_function=ml_data.get("check_loss_function", True),
                check_hardcoded_params=ml_data.get("check_hardcoded_params", True),
            ),
            indexing=IndexingConfig(
                incremental=idx_data.get("incremental", True),
                watch_mode=idx_data.get("watch_mode", False),
                debounce_seconds=idx_data.get("debounce_seconds", 2.0),
                concurrency=idx_data.get("concurrency", 4),
                max_file_size_mb=idx_data.get("max_file_size_mb", 10),
            ),
            output=OutputConfig(
                format=out_data.get("format", "rich"),
                include_code_context=out_data.get("include_code_context", 3),
                show_confidence=out_data.get("show_confidence", True),
                color=out_data.get("color", True),
            ),
        )

    @staticmethod
    def _apply_env_overrides(cfg: AISupportConfig) -> None:
        if val := os.environ.get("AI_SUPPORT_FORMAT"):
            cfg.output.format = val
        if val := os.environ.get("AI_SUPPORT_CONCURRENCY"):
            cfg.indexing.concurrency = int(val)
        if val := os.environ.get("AI_SUPPORT_WATCH"):
            cfg.indexing.watch_mode = val.lower() in ("1", "true", "yes")
