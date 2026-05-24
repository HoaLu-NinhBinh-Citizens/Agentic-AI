"""Extended LLM providers for Agentic-AI.

Additional providers beyond the base client:
- Groq (fast inference)
- Cohere
- Mistral
- Vertex AI (Google)
- AWS Bedrock
- DeepInfra
- Fireworks AI
- Perplexity
- Together AI
- Anyscale

Usage:
    from src.infrastructure.llm.providers_extended import (
        Provider,
        MultiProviderClient,
        GroqClient,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx


class Provider(Enum):
    """Supported LLM providers."""
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GROQ = "groq"
    COHERE = "cohere"
    MISTRAL = "mistral"
    VERTEX = "vertex"
    BEDROCK = "bedrock"
    DEEPINFRA = "deepinfra"
    FIREWORKS = "fireworks"
    PERPLEXITY = "perplexity"
    TOGETHER = "together"
    ANYSCALE = "anyscale"


# Model configurations per provider
PROVIDER_MODELS: dict[Provider, list[str]] = {
    Provider.OLLAMA: [
        "llama3.3:70b",
        "llama3.2:3b",
        "llama3.1:8b",
        "codellama:34b",
        "mistral:7b",
        "mixtral:8x7b",
        "qwen2.5:14b",
        "phi4:14b",
    ],
    Provider.OPENAI: [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-4",
        "gpt-3.5-turbo",
    ],
    Provider.ANTHROPIC: [
        "claude-opus-4-5",
        "claude-sonnet-4-5",
        "claude-haiku-3-5",
    ],
    Provider.GROQ: [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    Provider.COHERE: [
        "command-r-plus",
        "command-r",
        "command",
        "command-light",
    ],
    Provider.MISTRAL: [
        "mistral-large-latest",
        "mistral-small-latest",
        "codestral-latest",
        "mixtral-8x22b-latest",
    ],
    Provider.VERTEX: [
        "gemini-2.0-flash",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
        "gemini-pro",
    ],
    Provider.BEDROCK: [
        "anthropic.claude-3-5-sonnet-20241022-v1:0",
        "anthropic.claude-3-opus-20240229-v1:0",
        "anthropic.claude-3-sonnet-20240229-v1:0",
        "meta.llama3-1-70b-instruct-v1:0",
        "mistral.mixtral-8x7b-instruct-v0:1",
    ],
    Provider.DEEPINFRA: [
        "meta-llama/Llama-3.3-70B-Instruct",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "Qwen/Qwen2.5-72B-Instruct",
    ],
    Provider.FIREWORKS: [
        "accounts/fireworks/models/llama-v3p3-70b-instruct",
        "accounts/fireworks/models/qwen2p5-72b-instruct",
        "accounts/fireworks/models/codestral-22b-instruct",
    ],
    Provider.PERPLEXITY: [
        "sonar",
        "sonar-pro",
        "sonar-reasoning",
        "sonar-reasoning-pro",
    ],
    Provider.TOGETHER: [
        "meta-llama/Llama-3-70b-chat-hf",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
        "Qwen/Qwen2.5-72B-Instruct",
    ],
    Provider.ANYSCALE: [
        "meta-llama/Llama-3-70b-chat-hf",
        "mistralai/Mixtral-8x22B-Instruct-v0.1",
    ],
}


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    provider: Provider
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 60.0


class MultiProviderClient:
    """Client for multiple LLM providers."""
    
    def __init__(self):
        self._clients: dict[Provider, httpx.AsyncClient] = {}
        self._configs: dict[Provider, ProviderConfig] = {}
    
    def configure(self, config: ProviderConfig) -> None:
        """Configure a provider."""
        self._configs[config.provider] = config
        
        base_url = config.base_url or self._get_default_url(config.provider)
        self._clients[config.provider] = httpx.AsyncClient(
            base_url=base_url,
            timeout=config.timeout,
            headers=self._get_headers(config.provider, config.api_key),
        )
    
    def _get_default_url(self, provider: Provider) -> str:
        """Get default API URL for provider."""
        urls = {
            Provider.OLLAMA: "http://localhost:11434",
            Provider.OPENAI: "https://api.openai.com/v1",
            Provider.ANTHROPIC: "https://api.anthropic.com/v1",
            Provider.GROQ: "https://api.groq.com/openai/v1",
            Provider.COHERE: "https://api.cohere.ai/v1",
            Provider.MISTRAL: "https://api.mistral.ai/v1",
            Provider.DEEPINFRA: "https://api.deepinfra.com/v1/openai",
            Provider.FIREWORKS: "https://api.fireworks.ai/inference/v1",
            Provider.PERPLEXITY: "https://api.perplexity.ai",
            Provider.TOGETHER: "https://api.together.xyz/v1",
            Provider.ANYSCALE: "https://api.endpoints.anyscale.com/v1",
        }
        return urls.get(provider, "")
    
    def _get_headers(self, provider: Provider, api_key: str | None) -> dict:
        """Get headers for provider."""
        headers = {"Content-Type": "application/json"}
        
        if api_key:
            if provider == Provider.ANTHROPIC:
                headers["x-api-key"] = api_key
                headers["anthropic-version"] = "2023-06-01"
            else:
                headers["Authorization"] = f"Bearer {api_key}"
        
        return headers
    
    async def complete(
        self,
        provider: Provider,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> dict[str, Any]:
        """Generate completion from a provider."""
        if provider not in self._clients:
            raise ValueError(f"Provider not configured: {provider}")
        
        config = self._configs[provider]
        client = self._clients[provider]
        
        model = model or config.model or PROVIDER_MODELS[provider][0]
        temperature = temperature or config.temperature
        max_tokens = max_tokens or config.max_tokens
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools
        
        response = await client.post("/chat/completions", json=payload)
        response.raise_for_status()
        
        result = response.json()
        
        choice = result.get("choices", [{}])[0]
        return {
            "content": choice.get("message", {}).get("content", ""),
            "tool_calls": choice.get("message", {}).get("tool_calls", []),
            "usage": result.get("usage", {}),
            "model": result.get("model"),
        }
    
    async def close(self) -> None:
        """Close all clients."""
        for client in self._clients.values():
            await client.aclose()


class GroqClient:
    """Specialized Groq client for fast inference."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.groq.com/openai/v1"
    
    async def complete(
        self,
        messages: list[dict],
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.7,
    ) -> dict:
        """Complete using Groq API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 4096,
                },
            )
            response.raise_for_status()
            return response.json()


class PerplexityClient:
    """Specialized Perplexity client."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.perplexity.ai"
    
    async def complete(
        self,
        messages: list[dict],
        model: str = "sonar",
        temperature: float = 0.7,
    ) -> dict:
        """Complete using Perplexity API."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": 4096,
                },
            )
            response.raise_for_status()
            return response.json()


async def quick_complete(
    provider: Provider,
    api_key: str,
    prompt: str,
    model: str | None = None,
) -> str:
    """Quick completion without full setup."""
    client = MultiProviderClient()
    
    try:
        client.configure(ProviderConfig(
            provider=provider,
            api_key=api_key,
            model=model,
        ))
        
        result = await client.complete(
            provider,
            [{"role": "user", "content": prompt}],
        )
        
        return result.get("content", "")
    finally:
        await client.close()
