"""Real AI agent for production use.

This module provides a real AI agent that uses configured LLM providers
(OpenAI, Anthropic, Ollama) via the existing LLMManager infrastructure.

Replaces MockAgent for actual AI responses in chat.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class RealAgent:
    """Real AI agent that uses configured LLM providers.

    Uses infrastructure.llm.llm_manager.LLMManager for actual AI generation.
    Supports streaming responses with cancellation.
    """

    def __init__(self):
        self._llm_manager = None
        self._is_configured = False
        self._init_error: str | None = None
        self._initialization_lock = asyncio.Lock()

    async def _initialize_if_needed(self) -> None:
        """Initialize LLM manager if not already done."""
        async with self._initialization_lock:
            if self._llm_manager is not None:
                return

            try:
                from infrastructure.llm.llm_manager import (
                    LLMManager,
                    LLMConfig,
                    ModelProvider,
                )

                # Detect provider from environment
                openai_key = os.getenv("OPENAI_API_KEY")
                anthropic_key = os.getenv("ANTHROPIC_API_KEY")
                ollama_url = os.getenv(
                    "OLLAMA_BASE_URL", "http://localhost:11434"
                )

                # Choose provider based on what's available
                if openai_key:
                    config = LLMConfig(
                        provider=ModelProvider.OPENAI,
                        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                        api_key=openai_key,
                        temperature=0.3,
                        max_tokens=2048,
                    )
                    logger.info("RealAgent: Using OpenAI provider")
                elif anthropic_key:
                    config = LLMConfig(
                        provider=ModelProvider.ANTHROPIC,
                        model=os.getenv(
                            "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
                        ),
                        api_key=anthropic_key,
                        temperature=0.3,
                        max_tokens=2048,
                    )
                    logger.info("RealAgent: Using Anthropic provider")
                else:
                    # Default to Ollama (local, free)
                    config = LLMConfig(
                        provider=ModelProvider.OLLAMA,
                        model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
                        base_url=ollama_url,
                        temperature=0.3,
                        max_tokens=2048,
                    )
                    logger.info("RealAgent: Using Ollama provider")

                self._llm_manager = LLMManager(config=config)
                self._is_configured = True
                self._init_error = None
                logger.info(
                    "RealAgent initialized: provider=%s, model=%s",
                    config.provider,
                    config.model,
                )

            except Exception as e:
                logger.error("Failed to initialize RealAgent: %s", e)
                self._is_configured = False
                self._init_error = str(e)
                raise

    def is_configured(self) -> bool:
        """Check if agent has valid AI provider configuration."""
        return self._is_configured and self._llm_manager is not None

    def get_configuration_status(self) -> dict[str, Any]:
        """Get detailed configuration status."""
        openai_key = bool(os.getenv("OPENAI_API_KEY"))
        anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
        ollama_url = os.getenv(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )

        providers = {
            "openai": {"available": openai_key, "model": "gpt-4o-mini"},
            "anthropic": {
                "available": anthropic_key,
                "model": "claude-sonnet-4-20250514",
            },
            "ollama": {
                "available": True,
                "model": "llama3.2",
                "base_url": ollama_url,
            },
        }

        return {
            "configured": self._is_configured,
            "error": self._init_error,
            "providers": providers,
            "active_provider": (
                self._llm_manager.config.provider
                if self._llm_manager
                else None
            ),
            "suggestions": [
                "Set OPENAI_API_KEY for OpenAI",
                "Set ANTHROPIC_API_KEY for Anthropic",
                "Install Ollama from https://ollama.ai/ for local AI",
            ],
        }

    async def stream_response(
        self,
        message: str,
        send_event: Callable[[dict], Awaitable[None]],
        cancellation_event: asyncio.Event | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Stream a response from AI provider.

        Args:
            message: The user message.
            send_event: Callback to send events to the client.
            cancellation_event: Optional cancellation signal.
            trace_id: Optional trace ID.
            session_id: Optional session ID.
        """
        try:
            await self._initialize_if_needed()
        except Exception as e:
            error_info = self._get_user_friendly_error(e)
            await send_event({
                "type": "error",
                "data": {
                    "code": error_info["code"],
                    "message": error_info["message"],
                    "suggestions": error_info.get("suggestions", []),
                },
            })
            return

        if not message or message.strip() == "":
            await send_event({"type": "done", "data": {"success": True}})
            return

        logger.info(
            "Processing AI request: session=%s, len=%d",
            session_id,
            len(message),
        )

        try:
            system_prompt = (
                "You are AI_SUPPORT, an embedded engineering intelligence "
                "assistant. You help with embedded systems, firmware, "
                "hardware analysis, and automotive engineering. "
                "Be precise and deterministic about hardware behavior."
            )

            # Stream response token by token
            async for chunk in self._llm_manager.stream(
                prompt=message, system=system_prompt
            ):
                if cancellation_event and cancellation_event.is_set():
                    await send_event({"type": "cancelled", "data": {}})
                    logger.info("Stream cancelled: session=%s", session_id)
                    return

                if chunk.content:
                    await send_event({
                        "type": "token",
                        "data": {
                            "content": chunk.content,
                            "is_last": chunk.done,
                        },
                    })

                if chunk.done:
                    break

            # Send done event
            if not (cancellation_event and cancellation_event.is_set()):
                await send_event({
                    "type": "done",
                    "data": {
                        "success": True,
                        "provider": self._llm_manager.config.provider,
                    },
                })

        except asyncio.CancelledError:
            await send_event({"type": "cancelled", "data": {}})

        except Exception as e:
            logger.error(
                "AI generation error: session=%s, error=%s",
                session_id,
                str(e),
            )
            error_info = self._get_user_friendly_error(e)
            await send_event({
                "type": "error",
                "data": {
                    "code": error_info["code"],
                    "message": error_info["message"],
                    "suggestions": error_info.get("suggestions", []),
                },
            })

    async def generate_response(
        self,
        message: str,
        session_id: str | None = None,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Generate a non-streaming response.

        Args:
            message: The user message.
            session_id: Optional session ID.
            trace_id: Optional trace ID.

        Returns:
            Dictionary with response and metadata.
        """
        try:
            await self._initialize_if_needed()
        except Exception as e:
            return {
                "success": False,
                "error": type(e).__name__,
                "message": str(e),
                "details": self.get_configuration_status(),
            }

        try:
            system_prompt = (
                "You are AI_SUPPORT, an embedded engineering assistant."
            )

            response = await self._llm_manager.generate(
                prompt=message, system=system_prompt
            )

            return {
                "success": True,
                "response": response.content,
                "provider": self._llm_manager.config.provider,
                "model": self._llm_manager.config.model,
                "tokens_used": response.usage.get("total_tokens", 0)
                if response.usage
                else 0,
            }

        except Exception as e:
            logger.error("Error in generate_response: %s", e)
            return {
                "success": False,
                "error": type(e).__name__,
                "message": str(e),
            }

    def _get_user_friendly_error(self, error: Exception) -> dict[str, Any]:
        """Convert technical errors to user-friendly messages."""
        error_msg = str(error).lower()

        if "api key" in error_msg or "auth" in error_msg:
            return {
                "code": "AUTH_ERROR",
                "message": "AI provider authentication failed. "
                "Check your API key.",
                "suggestions": [
                    "Verify OPENAI_API_KEY or ANTHROPIC_API_KEY",
                    "Check API key has sufficient credits",
                    "Use Ollama for free local AI",
                ],
            }

        if "connect" in error_msg or "network" in error_msg:
            return {
                "code": "NETWORK_ERROR",
                "message": "Cannot connect to AI service.",
                "suggestions": [
                    "Check internet connection",
                    "If using Ollama, run: ollama serve",
                    "Try again in a few minutes",
                ],
            }

        if "timeout" in error_msg:
            return {
                "code": "TIMEOUT_ERROR",
                "message": "AI response timed out.",
                "suggestions": [
                    "Try a shorter/simpler query",
                    "AI provider may be overloaded",
                    "Wait and try again",
                ],
            }

        if "rate" in error_msg or "limit" in error_msg:
            return {
                "code": "RATE_LIMIT",
                "message": "Rate limit exceeded.",
                "suggestions": [
                    "Wait 60 seconds before retrying",
                    "Reduce request frequency",
                ],
            }

        if "not configured" in error_msg or "not found" in error_msg:
            return {
                "code": "NOT_CONFIGURED",
                "message": "No AI provider available.",
                "suggestions": [
                    "Set OPENAI_API_KEY environment variable",
                    "Or install Ollama: https://ollama.ai/",
                    "Run: python scripts/setup_ai_provider.py",
                ],
            }

        return {
            "code": "INTERNAL_ERROR",
            "message": f"Unexpected error: {str(error)}",
            "suggestions": [
                "Check server logs",
                "Try again",
                "Restart the server",
            ],
        }

    async def close(self) -> None:
        """Clean up resources."""
        self._llm_manager = None
        self._is_configured = False
        logger.info("RealAgent closed")
