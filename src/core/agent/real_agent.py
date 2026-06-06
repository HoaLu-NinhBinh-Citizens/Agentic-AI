"""Real AI agent for production use.

This module provides a real AI agent that uses configured LLM providers.
Supports multiple LLM backends (OpenAI, Anthropic, Ollama) with fallbacks.

Phase 2B: Real AI integration with proper error handling and configuration.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Awaitable, Callable

# Add src/ to path so infrastructure imports work
import sys
from pathlib import Path

_SRC_DIR = Path(__file__).parent.parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

try:
    from infrastructure.llm.llm_manager import LLMManager
    from infrastructure.llm.provider import ProviderConfig, ProviderType
    from infrastructure.llm.openai_llm import OpenAILLM
    from infrastructure.llm.ollama_adapter import OllamaAdapter
except ImportError as e:
    logging.error(f"Failed to import LLM infrastructure: {e}")
    raise

logger = logging.getLogger(__name__)

# Context variable for request tracing
_trace_id: ContextVar[str] = ContextVar('trace_id', default='')
_session_id: ContextVar[str] = ContextVar('session_id', default='')


def set_trace_context(trace_id: str | None = None, session_id: str | None = None) -> None:
    """Set trace context for the current async task."""
    if trace_id:
        _trace_id.set(trace_id)
    if session_id:
        _session_id.set(session_id)


def get_trace_context() -> tuple[str, str]:
    """Get current trace context."""
    return _trace_id.get(), _session_id.get()


class RealAgent:
    """Real AI agent that uses configured LLM providers.
    
    Features:
    - Multiple LLM provider support (OpenAI, Anthropic, Ollama)
    - Automatic fallback between providers
    - Streaming responses
    - Error handling and retries
    - Configuration validation
    """
    
    def __init__(self):
        self._llm_manager: LLMManager | None = None
        self._is_configured = False
        self._initialization_lock = asyncio.Lock()
        
    async def _initialize_if_needed(self) -> None:
        """Initialize LLM manager if not already done."""
        async with self._initialization_lock:
            if self._llm_manager is not None:
                return
                
            try:
                # Check environment variables for API keys
                openai_key = os.getenv("OPENAI_API_KEY")
                anthropic_key = os.getenv("ANTHROPIC_API_KEY")
                ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                
                # Determine which providers to enable
                enabled_providers = []
                configs = {}
                
                # OpenAI configuration
                if openai_key:
                    configs[ProviderType.OPENAI] = ProviderConfig(
                        provider_type=ProviderType.OPENAI,
                        api_key=openai_key,
                        base_url="https://api.openai.com/v1",
                        model="gpt-4o-mini",  # Cost-effective default
                        timeout=30.0,
                        max_tokens=2048,
                        temperature=0.3
                    )
                    enabled_providers.append(ProviderType.OPENAI)
                    logger.info("OpenAI provider enabled")
                
                # Ollama configuration (local fallback)
                if ollama_url:
                    try:
                        import aiohttp
                        async with aiohttp.ClientSession() as session:
                            async with session.get(f"{ollama_url}/api/tags", timeout=2.0) as resp:
                                if resp.status == 200:
                                    configs[ProviderType.OLLAMA] = ProviderConfig(
                                        provider_type=ProviderType.OLLAMA,
                                        api_key=None,
                                        base_url=ollama_url,
                                        model="llama3.2",
                                        timeout=60.0,
                                        max_tokens=4096,
                                        temperature=0.7
                                    )
                                    enabled_providers.append(ProviderType.OLLAMA)
                                    logger.info("Ollama provider enabled")
                    except Exception as e:
                        logger.warning(f"Ollama not available: {e}")
                
                if not enabled_providers:
                    raise RuntimeError(
                        "No AI providers configured. Please set one of:\n"
                        "- OPENAI_API_KEY environment variable\n"
                        "- OLLAMA_BASE_URL (default: http://localhost:11434)\n"
                        "- ANTHROPIC_API_KEY environment variable"
                    )
                
                # Create LLM manager with enabled providers
                self._llm_manager = LLMManager(
                    enabled_providers=enabled_providers,
                    provider_configs=configs,
                    fallback_order=enabled_providers,  # Try providers in order
                    default_provider=enabled_providers[0]
                )
                
                # Initialize the manager
                await self._llm_manager.initialize()
                self._is_configured = True
                logger.info(f"RealAgent initialized with providers: {[p.value for p in enabled_providers]}")
                
            except Exception as e:
                logger.error(f"Failed to initialize RealAgent: {e}")
                self._is_configured = False
                raise
    
    def is_configured(self) -> bool:
        """Check if agent has valid AI provider configuration."""
        return self._is_configured and self._llm_manager is not None
    
    def get_configuration_status(self) -> dict[str, Any]:
        """Get detailed configuration status."""
        if not self._llm_manager:
            return {
                "configured": False,
                "error": "Not initialized",
                "providers": {},
                "suggestions": [
                    "Set OPENAI_API_KEY environment variable for OpenAI",
                    "Install Ollama and run `ollama serve` for local inference",
                    "Set ANTHROPIC_API_KEY for Anthropic Claude"
                ]
            }
        
        return {
            "configured": self._is_configured,
            "providers": self._llm_manager.get_provider_status(),
            "default_provider": self._llm_manager.get_default_provider().value if self._llm_manager.get_default_provider() else None
        }
    
    async def stream_response(
        self,
        message: str,
        send_event: Callable[[dict], Awaitable[None]],
        cancellation_event: asyncio.Event | None = None,
        trace_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Stream a response from real AI provider.
        
        Args:
            message: The message to respond to.
            send_event: Callback to send events to the client.
            cancellation_event: Optional event to check for cancellation.
            trace_id: Optional trace ID for distributed tracing.
            session_id: Optional session ID for context.
        """
        # Set trace context
        if trace_id:
            set_trace_context(trace_id=trace_id, session_id=session_id)
        
        trace_id, session_id = get_trace_context()
        
        try:
            # Initialize if needed
            await self._initialize_if_needed()
            
            if not self.is_configured():
                await send_event({
                    "type": "error",
                    "data": {
                        "code": "AI_NOT_CONFIGURED",
                        "message": "AI provider not configured. Please set up API keys or install Ollama.",
                        "details": self.get_configuration_status(),
                        "suggestions": [
                            "Install Ollama: https://ollama.ai/",
                            "Set OPENAI_API_KEY environment variable",
                            "Configure AI in settings"
                        ]
                    },
                })
                return
            
            if not message or message.strip() == "":
                await send_event({
                    "type": "done",
                    "data": {"success": True},
                })
                return
            
            logger.info(
                "Processing real AI request: session=%s, message_length=%d",
                session_id,
                len(message),
            )
            
            # Create system prompt for embedded engineering
            system_prompt = """You are AI_SUPPORT, an embedded engineering intelligence assistant.
            You help with embedded systems, firmware, hardware analysis, and automotive engineering.
            
            Guidelines:
            1. Be precise and deterministic about hardware behavior
            2. Never hallucinate registers or peripherals
            3. Validate hardware dependencies in your reasoning
            4. Explain initialization sequences and timing
            5. Focus on embedded engineering workflows
            
            Current task: Respond to the user's query about embedded systems."""
            
            full_prompt = f"System: {system_prompt}\n\nUser: {message}\n\nAssistant:"
            
            # Stream response from LLM
            async def on_token(token: str, is_last: bool = False) -> None:
                """Callback for each token streamed."""
                if cancellation_event and cancellation_event.is_set():
                    raise asyncio.CancelledError()
                
                await send_event({
                    "type": "token",
                    "data": {
                        "content": token,
                        "is_last": is_last,
                    },
                })
            
            try:
                # Get response from LLM manager
                response = await self._llm_manager.generate_streaming(
                    prompt=full_prompt,
                    on_token=on_token,
                    cancellation_event=cancellation_event,
                    session_id=session_id,
                    trace_id=trace_id,
                )
                
                if cancellation_event and cancellation_event.is_set():
                    await send_event({
                        "type": "cancelled",
                        "data": {},
                    })
                    logger.info("AI response cancelled", trace_id=trace_id, session_id=session_id)
                    return
                
                await send_event({
                    "type": "done",
                    "data": {
                        "success": True,
                        "provider": response.provider.value if response.provider else "unknown",
                        "tokens_used": response.tokens_used,
                    },
                })
                logger.info(
                    "AI response completed: provider=%s, tokens=%d",
                    response.provider.value if response.provider else "unknown",
                    response.tokens_used,
                )
                
            except asyncio.CancelledError:
                await send_event({
                    "type": "cancelled",
                    "data": {},
                })
                logger.info("AI response cancelled", trace_id=trace_id, session_id=session_id)
                return
                
            except Exception as e:
                logger.error(
                    "AI generation error",
                    trace_id=trace_id,
                    session_id=session_id,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                await send_event({
                    "type": "error",
                    "data": {
                        "code": "AI_GENERATION_ERROR",
                        "message": f"AI generation failed: {str(e)}",
                        "provider": "unknown",
                        "suggestion": "Check API keys or try local Ollama installation",
                    },
                })
                
        except Exception as e:
            logger.exception(
                "Unexpected error in RealAgent.stream_response",
                trace_id=trace_id,
                session_id=session_id,
            )
            await send_event({
                "type": "error",
                "data": {
                    "code": "INTERNAL_ERROR",
                    "message": f"Internal error: {str(e)}",
                    "details": "Please check server logs",
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
            message: The message to respond to.
            session_id: Optional session ID.
            trace_id: Optional trace ID.
            
        Returns:
            Dictionary with response and metadata.
        """
        try:
            await self._initialize_if_needed()
            
            if not self.is_configured():
                return {
                    "success": False,
                    "error": "AI_NOT_CONFIGURED",
                    "message": "AI provider not configured",
                    "details": self.get_configuration_status(),
                }
            
            system_prompt = "You are AI_SUPPORT, an embedded engineering assistant."
            full_prompt = f"System: {system_prompt}\n\nUser: {message}\n\nAssistant:"
            
            response = await self._llm_manager.generate(
                prompt=full_prompt,
                session_id=session_id,
                trace_id=trace_id,
            )
            
            return {
                "success": True,
                "response": response.text,
                "provider": response.provider.value if response.provider else "unknown",
                "tokens_used": response.tokens_used,
                "latency_ms": response.latency_ms,
            }
            
        except Exception as e:
            logger.error(f"Error in generate_response: {e}")
            return {
                "success": False,
                "error": type(e).__name__,
                "message": str(e),
            }
    
    async def close(self) -> None:
        """Clean up resources."""
        if self._llm_manager:
            await self._llm_manager.close()
            self._llm_manager = None
        self._is_configured = False
        logger.info("RealAgent closed")