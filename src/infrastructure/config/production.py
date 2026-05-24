"""Production Configuration - Deployment-ready settings for AI_SUPPORT.

This module provides production configuration:
- Environment-based settings
- Security settings
- Rate limiting
- Health checks
- Monitoring
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class Environment(Enum):
    """Deployment environment."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 4
    reload: bool = False
    log_level: str = "INFO"
    
    # SSL/TLS
    ssl_cert: Optional[str] = None
    ssl_key: Optional[str] = None
    ssl_ca: Optional[str] = None


@dataclass
class SecurityConfig:
    """Security configuration."""
    secret_key: str = "change-me-in-production"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24
    
    # CORS
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    cors_methods: list[str] = field(default_factory=lambda: ["GET", "POST"]))
    cors_headers: list[str] = field(default_factory=lambda: ["*"])
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60
    
    # API keys
    require_api_key: bool = True
    allowed_api_keys: list[str] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    """Database configuration."""
    url: str = "sqlite:///./ai_support.db"
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False


@dataclass
class RedisConfig:
    """Redis configuration for caching/sessions."""
    url: str = "redis://localhost:6379/0"
    password: Optional[str] = None
    ssl: bool = False
    max_connections: int = 50


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "openai"
    model: str = "gpt-4"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    
    # Limits
    max_tokens: int = 4096
    max_requests_per_minute: int = 60
    max_tokens_per_minute: int = 90000
    
    # Fallback
    fallback_model: Optional[str] = None


@dataclass
class MonitoringConfig:
    """Monitoring configuration."""
    enabled: bool = True
    prometheus_port: int = 9090
    
    # Tracing
    tracing_enabled: bool = True
    tracing_endpoint: Optional[str] = None
    tracing_sample_rate: float = 0.1
    
    # Metrics
    metrics_enabled: bool = True
    metrics_prefix: str = "ai_support"


@dataclass
class ProductionConfig:
    """Complete production configuration."""
    environment: Environment = Environment.DEVELOPMENT
    
    server: ServerConfig = field(default_factory=ServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    
    # Application
    app_name: str = "AI_SUPPORT"
    app_version: str = "1.0.0"
    debug: bool = False


def load_config_from_env() -> ProductionConfig:
    """
    Load configuration from environment variables.
    
    Environment variables:
        AI_ENV: development|staging|production
        AI_HOST: Server host
        AI_PORT: Server port
        AI_SECRET_KEY: Secret key for encryption
        AI_DATABASE_URL: Database URL
        AI_REDIS_URL: Redis URL
        AI_LLM_PROVIDER: openai|anthropic|ollama
        AI_LLM_MODEL: Model name
        AI_LLM_API_KEY: API key
        AI_PROMETHEUS_PORT: Prometheus metrics port
    """
    env = os.getenv("AI_ENV", "development")
    environment = Environment(env.lower())
    
    # Determine if production
    is_production = environment == Environment.PRODUCTION
    
    config = ProductionConfig(
        environment=environment,
        debug=not is_production,
        server=ServerConfig(
            host=os.getenv("AI_HOST", "0.0.0.0"),
            port=int(os.getenv("AI_PORT", "8000")),
            reload=environment == Environment.DEVELOPMENT,
            log_level="DEBUG" if environment == Environment.DEVELOPMENT else "INFO",
        ),
        security=SecurityConfig(
            secret_key=os.getenv("AI_SECRET_KEY", "change-me-in-production"),
            jwt_secret=os.getenv("AI_JWT_SECRET", "change-me-in-production"),
            require_api_key=is_production,
            allowed_api_keys=_parse_list(os.getenv("AI_ALLOWED_API_KEYS", "")),
        ),
        database=DatabaseConfig(
            url=os.getenv("AI_DATABASE_URL", "sqlite:///./ai_support.db"),
            echo=environment == Environment.DEVELOPMENT,
        ),
        redis=RedisConfig(
            url=os.getenv("AI_REDIS_URL", "redis://localhost:6379/0"),
            password=os.getenv("AI_REDIS_PASSWORD"),
        ),
        llm=LLMConfig(
            provider=os.getenv("AI_LLM_PROVIDER", "openai"),
            model=os.getenv("AI_LLM_MODEL", "gpt-4"),
            api_key=os.getenv("AI_LLM_API_KEY"),
            base_url=os.getenv("AI_LLM_BASE_URL"),
        ),
        monitoring=MonitoringConfig(
            enabled=is_production,
            prometheus_port=int(os.getenv("AI_PROMETHEUS_PORT", "9090")),
            tracing_enabled=is_production,
            metrics_enabled=is_production,
        ),
    )
    
    logger.info(f"Configuration loaded for environment: {env}")
    return config


def _parse_list(value: str, separator: str = ",") -> list[str]:
    """Parse comma-separated list from environment."""
    if not value:
        return []
    return [item.strip() for item in value.split(separator) if item.strip()]


# Global config
_config: Optional[ProductionConfig] = None


def get_config() -> ProductionConfig:
    """Get global configuration."""
    global _config
    if _config is None:
        _config = load_config_from_env()
    return _config


def reset_config() -> None:
    """Reset global configuration (useful for testing)."""
    global _config
    _config = None


class ConfigManager:
    """
    Configuration manager with hot reload support.
    
    Usage:
        manager = ConfigManager()
        
        # Get current config
        config = manager.get()
        
        # Reload from environment
        manager.reload()
        
        # Watch for changes (file-based)
        async for change in manager.watch():
            print("Config changed:", change)
    """
    
    def __init__(self):
        self._config: Optional[ProductionConfig] = None
        self._last_modified: float = 0
    
    def get(self) -> ProductionConfig:
        """Get current configuration."""
        if self._config is None:
            self._config = load_config_from_env()
        return self._config
    
    def reload(self) -> ProductionConfig:
        """Reload configuration from environment."""
        logger.info("Reloading configuration...")
        self._config = load_config_from_env()
        return self._config
    
    async def watch(self):
        """Watch for configuration changes (async generator)."""
        import asyncio
        
        while True:
            await asyncio.sleep(5)  # Check every 5 seconds
            # In production, this would check a config file
            yield {"event": "check"}


# Validation
def validate_config(config: ProductionConfig) -> list[str]:
    """Validate configuration and return errors."""
    errors = []
    
    if config.environment == Environment.PRODUCTION:
        if config.security.secret_key == "change-me-in-production":
            errors.append("SECRET_KEY must be changed in production")
        
        if config.security.jwt_secret == "change-me-in-production":
            errors.append("JWT_SECRET must be changed in production")
        
        if config.llm.api_key is None:
            errors.append("LLM_API_KEY required in production")
    
    if config.server.port < 1 or config.server.port > 65535:
        errors.append("Invalid server port")
    
    if config.llm.max_tokens < 100:
        errors.append("max_tokens must be at least 100")
    
    return errors


# Production utilities
def is_production() -> bool:
    """Check if running in production."""
    return get_config().environment == Environment.PRODUCTION


def is_development() -> bool:
    """Check if running in development."""
    return get_config().environment == Environment.DEVELOPMENT


def is_staging() -> bool:
    """Check if running in staging."""
    return get_config().environment == Environment.STAGING


if __name__ == "__main__":
    config = load_config_from_env()
    
    print("=" * 50)
    print("AI_SUPPORT Configuration")
    print("=" * 50)
    print(f"Environment: {config.environment.value}")
    print(f"App: {config.app_name} v{config.app_version}")
    print()
    print("Server:")
    print(f"  Host: {config.server.host}")
    print(f"  Port: {config.server.port}")
    print(f"  Workers: {config.server.workers}")
    print()
    print("LLM:")
    print(f"  Provider: {config.llm.provider}")
    print(f"  Model: {config.llm.model}")
    print(f"  API Key: {'*' * 20 if config.llm.api_key else 'NOT SET'}")
    print()
    print("Monitoring:")
    print(f"  Enabled: {config.monitoring.enabled}")
    print(f"  Tracing: {config.monitoring.tracing_enabled}")
    print()
    
    # Validate
    errors = validate_config(config)
    if errors:
        print("Configuration errors:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("Configuration valid!")
