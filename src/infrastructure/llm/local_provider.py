"""Local LLM provider using Ollama API.

Supports models like llama3, mistral, codellama, etc.
Designed for AI_SUPPORT code analysis and fix generation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for local LLM provider."""
    base_url: str = "http://localhost:11434/api"
    model: str = "llama3"
    temperature: float = 0.3
    max_tokens: int = 2048
    timeout: float = 120.0


@dataclass
class LocalModelInfo:
    """Information about a local model."""
    name: str
    size: int
    modified_at: int


class LocalLLMProvider:
    """Local LLM provider using Ollama REST API.

    Integrates with existing LLM infrastructure but focuses on:
    - Simple non-streaming generate
    - Streaming generate for long outputs
    - Health checks and model availability
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=httpx.Timeout(self.config.timeout),
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout),
            )
        return self._client

    async def generate(self, prompt: str, system: str = None) -> str:
        """Generate completion from prompt.

        Args:
            prompt: User prompt
            system: Optional system prompt

        Returns:
            Generated text response
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        if system:
            payload["system"] = system

        try:
            response = await self.client.post("/generate", json=payload)
            response.raise_for_status()
            return response.json()["response"]
        except httpx.HTTPStatusError as e:
            logger.error("Ollama HTTP error: %s", e)
            raise
        except Exception as e:
            logger.error("Ollama generate error: %s", e)
            raise

    async def generate_stream(self, prompt: str, system: str = None) -> AsyncIterator[str]:
        """Stream completion chunks.

        Args:
            prompt: User prompt
            system: Optional system prompt

        Yields:
            Text chunks as they arrive
        """
        payload = {
            "model": self.config.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.config.temperature,
                "num_predict": self.config.max_tokens,
            }
        }
        if system:
            payload["system"] = system

        try:
            async with self.client.stream("POST", "/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            content = data.get("response", "")
                            if content:
                                yield content
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.HTTPStatusError as e:
            logger.error("Ollama streaming HTTP error: %s", e)
            raise
        except Exception as e:
            logger.error("Ollama streaming error: %s", e)
            raise

    async def is_available(self) -> bool:
        """Check if Ollama is running and model is available.

        Returns:
            True if Ollama is accessible and model is installed
        """
        try:
            base = self.config.base_url.rsplit("/api", 1)[0]
            async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
                response = await client.get("/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return any(m["name"] == self.config.model for m in models)
                return False
        except Exception as e:
            logger.warning("Ollama availability check failed: %s", e)
            return False

    async def list_models(self) -> list[LocalModelInfo]:
        """List all available local models.

        Returns:
            List of model information
        """
        try:
            base = self.config.base_url.rsplit("/api", 1)[0]
            async with httpx.AsyncClient(base_url=base, timeout=10.0) as client:
                response = await client.get("/api/tags")
                if response.status_code == 200:
                    models = response.json().get("models", [])
                    return [
                        LocalModelInfo(
                            name=m["name"],
                            size=m.get("size", 0),
                            modified_at=m.get("modified_at", 0),
                        )
                        for m in models
                    ]
                return []
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    async def pull_model(self, model: Optional[str] = None) -> AsyncIterator[str]:
        """Pull a model from Ollama registry.

        Args:
            model: Model name to pull (defaults to configured model)

        Yields:
            Status messages during pull
        """
        model_name = model or self.config.model
        try:
            async with self.client.stream("POST", "/pull", json={"name": model_name}) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            if status:
                                yield status
                            if data.get("completed"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error("Failed to pull model: %s", e)
            raise

    @staticmethod
    def get_default_models() -> list[str]:
        """Get list of recommended models for code tasks.

        Returns:
            List of model names with descriptions
        """
        return [
            "llama3.2:3b",      # Fast, local friendly
            "llama3.1:8b",      # Balanced performance
            "llama3.1:70b",     # Best for reasoning
            "codellama:13b",    # Code specialized
            "mistral:7b",       # Fast, good quality
            "qwen2.5-coder:7b", # Code optimized
        ]

    def get_model_description(self, model: str) -> str:
        """Get description of a model's purpose.

        Args:
            model: Model name

        Returns:
            Description string
        """
        descriptions = {
            "llama3.2:3b": "Fast, efficient for simple tasks",
            "llama3.1:8b": "Balanced speed and quality",
            "llama3.1:70b": "Best reasoning, requires more memory",
            "codellama:13b": "Specialized for code generation",
            "mistral:7b": "Fast inference, good quality",
            "qwen2.5-coder:7b": "Optimized for code tasks",
        }
        return descriptions.get(model, "General purpose model")
