"""Ollama-specific adapter with model management.

Provides utilities for managing Ollama models including listing,
pulling, and health checking.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)


class OllamaAdapter:
    """Adapter for Ollama model management and health checks.

    This class provides a higher-level interface to Ollama's API
    for operations like listing models, pulling new models, and
    checking server availability.

    Example:
        ```python
        adapter = OllamaAdapter()
        models = await adapter.list_models()
        for model in models:
            print(f"  {model['name']}")

        # Pull a new model
        async for status in adapter.pull_model("llama3.2"):
            print(f"  {status}")
        ```
    """

    DEFAULT_BASE_URL = "http://localhost:11434"

    def __init__(self, base_url: str = DEFAULT_BASE_URL) -> None:
        """Initialize the Ollama adapter.

        Args:
            base_url: Ollama server URL (default: http://localhost:11434)
        """
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        """Initialize the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            )

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "OllamaAdapter":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def is_available(self) -> bool:
        """Check if Ollama server is running.

        Returns:
            True if the server responds to /api/tags request
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """List available Ollama models.

        Returns:
            List of model info dicts with 'name', 'size', 'modified_at' keys
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])
        except httpx.HTTPStatusError as e:
            logger.error("Failed to list models: HTTP %s", e.response.status_code)
            return []
        except Exception as e:
            logger.error("Failed to list models: %s", e)
            return []

    async def pull_model(self, model: str) -> AsyncIterator[str]:
        """Pull a model from Ollama registry.

        Yields status updates as the model is downloaded.

        Args:
            model: Model name (e.g., "llama3.2", "codellama")

        Yields:
            Status messages during the pull process

        Example:
            ```python
            async for status in adapter.pull_model("llama3.2"):
                print(status)
            ```
        """
        if not self._client:
            await self.initialize()

        try:
            async with self._client.stream(
                "POST",
                "/api/pull",
                json={"name": model},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            status = data.get("status", "")
                            if status:
                                yield status
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error("Failed to pull model %s: %s", model, e)
            raise

    async def delete_model(self, model: str) -> bool:
        """Delete a model from local storage.

        Args:
            model: Model name to delete

        Returns:
            True if deletion was successful
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.delete("/api/delete", json={"name": model})
            return response.status_code == 200
        except Exception as e:
            logger.error("Failed to delete model %s: %s", model, e)
            return False

    async def get_model_info(self, model: str) -> dict[str, Any]:
        """Get information about a specific model.

        Args:
            model: Model name

        Returns:
            Model information dict
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.post(
                "/api/show",
                json={"name": model},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error("Failed to get model info for %s: %s", model, e)
            return {}

    async def generate_embeddings(
        self,
        model: str,
        prompt: str,
    ) -> list[float]:
        """Generate embeddings for a prompt.

        Args:
            model: Model to use for embeddings
            prompt: Text to embed

        Returns:
            List of embedding values
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.post(
                "/api/embeddings",
                json={"model": model, "prompt": prompt},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("embedding", [])
        except Exception as e:
            logger.error("Failed to generate embeddings: %s", e)
            return []

    async def create_model(
        self,
        name: str,
        modelfile: str,
    ) -> bool:
        """Create a new model from a Modelfile.

        Args:
            name: Name for the new model
            modelfile: Modelfile content

        Returns:
            True if creation was successful
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.post(
                "/api/create",
                json={"name": name, "modelfile": modelfile},
            )
            return response.status_code == 200
        except Exception as e:
            logger.error("Failed to create model %s: %s", name, e)
            return False

    async def copy_model(self, source: str, destination: str) -> bool:
        """Copy a model to a new name.

        Args:
            source: Source model name
            destination: Destination model name

        Returns:
            True if copy was successful
        """
        if not self._client:
            await self.initialize()

        try:
            response = await self._client.post(
                "/api/copy",
                json={"source": source, "destination": destination},
            )
            return response.status_code == 200
        except Exception as e:
            logger.error("Failed to copy model %s -> %s: %s", source, destination, e)
            return False


async def check_ollama_status() -> tuple[bool, list[str]]:
    """Check Ollama status and return available models.

    Returns:
        Tuple of (is_available, model_names)
    """
    async with OllamaAdapter() as adapter:
        available = await adapter.is_available()
        if available:
            models = await adapter.list_models()
            model_names = [m.get("name", "unknown") for m in models]
            return True, model_names
        return False, []


async def pull_ollama_model(model: str) -> AsyncIterator[str]:
    """Pull a model with automatic adapter management.

    Args:
        model: Model name to pull

    Yields:
        Status messages
    """
    async with OllamaAdapter() as adapter:
        async for status in adapter.pull_model(model):
            yield status
