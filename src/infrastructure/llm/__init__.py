"""Infrastructure LLM module - Client exports."""

from .client import (
    LLMClient,
    LLMConfig,
    LLMResponse,
    Message,
    ModelRole,
    Provider,
    ToolCall,
    configure_llm,
    get_llm_client,
)
from .local_provider import (
    LocalLLMProvider,
    LocalLLMConfig,
    LocalModelInfo,
)
from .prompts import (
    ML_FIX_SYSTEM,
    SECURITY_FIX_SYSTEM,
    CODE_QUALITY_SYSTEM,
    CODE_EXPLANATION_SYSTEM,
    GENERAL_FIX_SYSTEM,
    build_finding_explanation_prompt,
    build_fix_generation_prompt,
    build_code_review_prompt,
    build_security_review_prompt,
    build_ml_review_prompt,
    FixPromptConfig,
)
from .prompt_engine import PromptEngine, PromptTemplate, PromptContext
from .context_builder import ContextBuilder, LLMContext
from .response_parser import ResponseParser, ParsedResponse, ValidationError
from .base import BaseLLM
from .ollama import OllamaLLM
from .anthropic_llm import AnthropicLLM
from .gemini_llm import GeminiLLM

__all__ = [
    # From client
    "LLMClient",
    "LLMConfig",
    "LLMResponse",
    "Message",
    "ModelRole",
    "Provider",
    "ToolCall",
    "configure_llm",
    "get_llm_client",
    # From local_provider
    "LocalLLMProvider",
    "LocalLLMConfig",
    "LocalModelInfo",
    # From prompts
    "ML_FIX_SYSTEM",
    "SECURITY_FIX_SYSTEM",
    "CODE_QUALITY_SYSTEM",
    "CODE_EXPLANATION_SYSTEM",
    "GENERAL_FIX_SYSTEM",
    "build_finding_explanation_prompt",
    "build_fix_generation_prompt",
    "build_code_review_prompt",
    "build_security_review_prompt",
    "build_ml_review_prompt",
    "FixPromptConfig",
    # From prompt_engine
    "PromptEngine",
    "PromptTemplate",
    "PromptContext",
    # From context_builder
    "ContextBuilder",
    "LLMContext",
    # From response_parser
    "ResponseParser",
    "ParsedResponse",
    "ValidationError",
    # Provider adapters
    "BaseLLM",
    "OllamaLLM",
    "AnthropicLLM",
    "GeminiLLM",
]
