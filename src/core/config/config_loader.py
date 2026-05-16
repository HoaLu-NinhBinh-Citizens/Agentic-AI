"""
Configuration loader for src.

Supports:
- config.yaml (YAML format)
- Environment variables (override YAML)
- Default values (fallback)

Environment variables take precedence over YAML.
Prefix: CARV_ (e.g., CARV_LLM_OLLAMA_MODEL, CARV_RAG_CHUNK_TEXT_CHARS)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional, Union

import yaml

logger = logging.getLogger(__name__)

# Module-level singleton
_config: Optional[Dict[str, Any]] = None


class Config:
    """
    Hierarchical configuration access.

    Load order (later overrides earlier):
    1. Default values
    2. config.yaml
    3. Environment variables (CARV_* prefix)

    Usage:
        cfg = Config()                    # Auto-load from AI_support/config.yaml
        cfg = Config(config_path)         # Custom config path
        model = cfg.get("llm.ollama.model")
        model = cfg.get("llm:ollama:model", sep=":")  # Colon separator
    """

    DEFAULT_CONFIG: Dict[str, Any] = {
        # LLM defaults
        "llm.ollama.model": "llama3.1:latest",
        "llm.ollama.url": "http://localhost:11434",
        "llm.ollama.streaming": True,
        "llm.ollama.keep_alive": "5m",
        "llm.ollama.connect_timeout": 10,
        "llm.ollama.read_timeout": 90,
        "llm.ollama.max_retries": 2,
        "llm.openai.model": "gpt-4o",
        "llm.openai.api_key": "",
        "llm.openai.base_url": "https://api.openai.com/v1",
        "llm.openai.streaming": True,
        "llm.openai.temperature": 0.3,
        "llm.openai.max_tokens": 2048,
        "llm.openai.read_timeout": 120,
        "llm.openai.max_retries": 2,
        # Model routing
        "model_routing.local_only": True,
        "model_routing.use_openai_for_complex": False,
        "model_routing.low_confidence_threshold": 0.5,
        "model_routing.low_confidence_model": "ollama",
        "model_routing.task_defaults.code_generation": "ollama",
        "model_routing.task_defaults.fix_errors": "ollama",
        "model_routing.task_defaults.document_analysis": "ollama",
        "model_routing.task_defaults.simple": "ollama",
        "model_routing.task_defaults.complex_reasoning": "ollama",
        # Tokens
        "tokens.use_tiktoken": True,
        "tokens.response_safety_margin": 512,
        "tokens.context_windows.default": 4096,
        # RAG
        "rag.chunk.text_chars": 1400,
        "rag.chunk.overlap_ratio": 0.25,
        "rag.chunk.max_chunks": 8,
        "rag.semantic.enabled": True,
        "rag.semantic.model": "nomic-embed-text:latest",
        "rag.semantic.top_k": 5,
        "rag.semantic.rerank_candidates": 10,
        "rag.vector_backend": "numpy",
        "rag.cache.ttl_seconds": 120,
        "rag.cache.max_entries": 64,
        "rag.confidence.high": 2,
        "rag.confidence.medium": 1,
        # Hybrid weights
        "rag.hybrid_weights.lexical": 0.65,
        "rag.hybrid_weights.vector": 8.0,
        "rag.hybrid_weights.rerank_bonus_high": 3.0,
        "rag.hybrid_weights.rerank_bonus_medium": 1.5,
        # Agent
        "agent.max_attempts": 3,
        "agent.timeouts.generate": 150,
        "agent.timeouts.fix": 120,
        "agent.timeouts.review": 90,
        "agent.timeouts.chapter_worker": 75,
        "agent.review.enabled": True,
        "agent.review.max_review_attempts": 2,
        "agent.chapter_workers.enabled": True,
        "agent.chapter_workers.max_workers": 4,
        "agent.chapter_workers.retry_limit": 2,
        "agent.chapter_workers.cache_max_age_hours": 12,
        # Memory
        "memory.compaction.keep_proposals": 100,
        "memory.compaction.keep_versions": 300,
        "memory.compaction.auto_compact_threshold": 250,
        "memory.experience.max_entries": 50,
        "memory.feedback_max_entries": 50,
        "memory.proposals.max_entries": 200,
        "memory.proposals.auto_approve_low_risk": False,
        # Build
        "build.parallel_jobs": 4,
        "build.use_ninja": True,
        "build.static_analysis.enabled": True,
        "build.flash.tool": "stlink",
        "build.flash.verify": True,
        # Streaming
        "streaming.enabled": True,
        "streaming.show_progress": False,
        "streaming.flush_interval": 0.1,
        # Logging
        "logging.level": "INFO",
        "logging.structured": False,
        "logging.log_file": "",
        "logging.max_file_size_mb": 10,
    }

    # Mapping from YAML paths to environment variable prefixes
    ENV_VAR_MAP: Dict[str, str] = {
        "llm.ollama.model": "CARV_LLM_OLLAMA_MODEL",
        "llm.ollama.url": "CARV_LLM_OLLAMA_URL",
        "llm.ollama.streaming": "CARV_LLM_OLLAMA_STREAMING",
        "llm.ollama.keep_alive": "CARV_LLM_OLLAMA_KEEP_ALIVE",
        "llm.ollama.connect_timeout": "CARV_LLM_OLLAMA_CONNECT_TIMEOUT",
        "llm.ollama.read_timeout": "CARV_LLM_OLLAMA_READ_TIMEOUT",
        "llm.openai.model": "OPENAI_MODEL",
        "llm.openai.api_key": "OPENAI_API_KEY",
        "llm.openai.base_url": "OPENAI_API_BASE",
        "llm.openai.streaming": "CARV_LLM_OPENAI_STREAMING",
        "llm.openai.temperature": "CARV_LLM_OPENAI_TEMPERATURE",
        "llm.openai.max_tokens": "CARV_LLM_OPENAI_MAX_TOKENS",
        "model_routing.local_only": "CARV_LOCAL_ONLY",
        "model_routing.use_openai_for_complex": "CARV_USE_OPENAI_FOR_COMPLEX",
        "tokens.use_tiktoken": "CARV_USE_TIKTOKEN",
        "rag.semantic.enabled": "CARV_RAG_SEMANTIC_ENABLED",
        "rag.vector_backend": "CARV_RAG_VECTOR_BACKEND",
        "streaming.enabled": "CARV_STREAMING_ENABLED",
        "streaming.show_progress": "CARV_STREAMING_SHOW_PROGRESS",
        "logging.level": "CARV_LOG_LEVEL",
    }

    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        self._config: Dict[str, Any] = {}
        self._loaded = False
        self._config_path: Optional[Path] = None

        # Load defaults first
        self._load_defaults()

        # Then load YAML
        if config_path:
            self._config_path = Path(config_path) if not isinstance(config_path, Path) else config_path
        else:
            # Auto-discover config.yaml relative to this module
            module_dir = Path(__file__).parent.parent
            candidate = module_dir / "config.yaml"
            if candidate.exists():
                self._config_path = candidate

        if self._config_path and self._config_path.exists():
            self._load_yaml(self._config_path)
        else:
            logger.debug("No config.yaml found at %s, using defaults", self._config_path)

        # Environment variables override everything
        self._load_env_overrides()

    def _load_defaults(self):
        """Load default configuration values."""
        for key, value in self.DEFAULT_CONFIG.items():
            self._set_nested(key, value)

    def _load_yaml(self, path: Path):
        """Load configuration from YAML file."""
        try:
            text = path.read_text(encoding="utf-8")
            data = yaml.safe_load(text)
            if not isinstance(data, dict):
                logger.warning("config.yaml root is not a dict, ignoring")
                return
            self._merge_dict(data)
            self._loaded = True
            logger.info("Loaded config from %s", path)
        except yaml.YAMLError as exc:
            logger.warning("Failed to parse config.yaml: %s", exc)
        except Exception as exc:
            logger.warning("Failed to load config.yaml: %s", exc)

    def _merge_dict(self, data: Dict[str, Any], prefix: str = ""):
        """Recursively merge a flat key-space dict."""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._merge_dict(value, full_key)
            else:
                self._set_nested(full_key, value)

    def _load_env_overrides(self):
        """Override config values with environment variables."""
        for yaml_key, env_var in self.ENV_VAR_MAP.items():
            env_value = os.environ.get(env_var)
            if env_value is not None:
                current = self.get(yaml_key)
                # Type coercion
                if isinstance(current, bool):
                    parsed = env_value.lower() in {"1", "true", "yes", "on"}
                elif isinstance(current, int):
                    try:
                        parsed = int(env_value)
                    except ValueError:
                        logger.warning("Env var %s=%s cannot be cast to int", env_var, env_value)
                        continue
                elif isinstance(current, float):
                    try:
                        parsed = float(env_value)
                    except ValueError:
                        logger.warning("Env var %s=%s cannot be cast to float", env_var, env_value)
                        continue
                else:
                    parsed = env_value
                self._set_nested(yaml_key, parsed)
                logger.debug("Config override: %s=%s (from %s)", yaml_key, parsed, env_var)

    def get(self, key: str, default: Any = None, sep: str = ".") -> Any:
        """
        Get a configuration value by dot-separated key.

        Args:
            key: Dot-separated path (e.g., "llm.ollama.model")
            default: Default value if key not found
            sep: Separator (default ".")

        Returns:
            The configuration value or default.
        """
        keys = key.split(sep)
        current = self._config
        for k in keys:
            if not isinstance(current, dict):
                return default
            current = current.get(k)
            if current is None:
                return default
        return current

    def set(self, key: str, value: Any, sep: str = "."):
        """Set a configuration value."""
        self._set_nested(key, value, sep)

    def _set_nested(self, key: str, value: Any, sep: str = "."):
        """Set a nested configuration value."""
        keys = key.split(sep)
        current = self._config
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            elif not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value

    def get_section(self, section: str) -> Dict[str, Any]:
        """Get an entire config section as a dict."""
        result = self.get(section, {})
        if not isinstance(result, dict):
            return {}
        return result

    def as_dict(self) -> Dict[str, Any]:
        """Return the full config as a flat dict."""
        return self._flatten_dict(self._config)

    def _flatten_dict(self, d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        result = {}
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                result.update(self._flatten_dict(v, full_key))
            else:
                result[full_key] = v
        return result

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def config_path(self) -> Optional[Path]:
        return self._config_path


# ─── Global config instance ────────────────────────────────────────────────────

_global_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """Get or create the global config instance."""
    global _global_config
    if _global_config is None:
        _global_config = Config(config_path)
    return _global_config


def reload_config(config_path: Optional[str] = None):
    """Force reload of configuration."""
    global _global_config
    _global_config = Config(config_path)
    return _global_config
