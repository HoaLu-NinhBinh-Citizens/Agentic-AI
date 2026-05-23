"""Deterministic LLM Framework for Reproducible AI.

Provides:
- Semantic caching for deterministic LLM responses
- Prompt fingerprinting
- Response schema enforcement
- Output caching with semantic matching
- Confidence scoring

Usage:
    det_llm = DeterministicLLM(provider=openai_provider)
    
    # First call - actual LLM
    result1 = await det_llm.generate(prompt)
    
    # Second call with same prompt - from cache
    result2 = await det_llm.generate(prompt)
    # result2 == result1 (deterministic!)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class LLMCacheEntry:
    """Cached LLM response."""
    prompt_hash: str
    response: str
    created_at: datetime
    model: str
    temperature: float
    confidence: float
    schema_version: str


@dataclass
class DeterministicConfig:
    """Configuration for deterministic LLM."""
    enable_semantic_cache: bool = True
    enable_schema_validation: bool = True
    enable_output_fingerprinting: bool = True
    cache_ttl_seconds: float = 3600.0
    semantic_similarity_threshold: float = 0.95
    max_cache_size: int = 10000


class PromptFingerprinter:
    """Creates deterministic fingerprints for prompts.
    
    Handles:
    - Whitespace normalization
    - Parameter ordering
    - Content normalization
    """
    
    def __init__(self, include_system: bool = True):
        self.include_system = include_system
    
    def fingerprint(
        self,
        prompt: str,
        system_prompt: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> str:
        """Create a deterministic fingerprint for a prompt."""
        parts = []
        
        if self.include_system and system_prompt:
            parts.append(self._normalize(system_prompt))
        
        parts.append(self._normalize(prompt))
        
        if parameters:
            # Sort parameters for determinism
            sorted_params = sorted(parameters.items())
            param_str = json.dumps(sorted_params, sort_keys=True)
            parts.append(self._normalize(param_str))
        
        combined = "|".join(parts)
        return hashlib.sha256(combined.encode()).hexdigest()[:32]
    
    def _normalize(self, text: str) -> str:
        """Normalize text for consistent fingerprinting."""
        # Remove extra whitespace
        text = " ".join(text.split())
        return text.strip().lower()


class SemanticPromptMatcher:
    """Match prompts semantically for cache hits.
    
    Uses embedding similarity to find semantically equivalent prompts.
    """
    
    def __init__(self, threshold: float = 0.95):
        self.threshold = threshold
        self._embeddings: dict[str, list[float]] = {}
        self._prompts: dict[str, str] = {}
    
    def add(self, prompt_hash: str, prompt: str, embedding: list[float]) -> None:
        """Add a prompt and its embedding."""
        self._embeddings[prompt_hash] = embedding
        self._prompts[prompt_hash] = prompt
    
    def find_match(self, prompt: str, embedding: list[float]) -> str | None:
        """Find a semantically similar prompt.
        
        Returns the hash of the matching prompt, or None if no match.
        """
        best_match = None
        best_similarity = 0.0
        
        for hash_val, stored_embedding in self._embeddings.items():
            similarity = self._cosine_similarity(embedding, stored_embedding)
            if similarity > best_similarity and similarity >= self.threshold:
                best_similarity = similarity
                best_match = hash_val
        
        if best_match:
            logger.debug("semantic_cache_hit", similarity=best_similarity)
        
        return best_match
    
    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(x * x for x in b) ** 0.5
        
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        
        return dot_product / (magnitude_a * magnitude_b)


@dataclass
class SchemaEnforcer:
    """Enforces output schema for deterministic responses."""
    
    schema: dict[str, Any]
    version: str = "1.0"
    
    def validate(self, response: str) -> tuple[bool, str]:
        """Validate response against schema.
        
        Returns (is_valid, error_message).
        """
        try:
            # Try to parse as JSON
            if response.strip().startswith("{"):
                data = json.loads(response)
            else:
                return True, ""  # Non-JSON responses are not validated
            
            # Validate required fields
            for key, spec in self.schema.items():
                if spec.get("required", False) and key not in data:
                    return False, f"Missing required field: {key}"
                
                if key in data:
                    expected_type = spec.get("type")
                    if expected_type and not isinstance(data[key], eval(expected_type)):
                        return False, f"Wrong type for {key}: expected {expected_type}"
            
            return True, ""
            
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON: {e}"
        except Exception as e:
            return False, f"Validation error: {e}"


class OutputFingerprinter:
    """Creates fingerprints for LLM outputs to detect drift."""
    
    def fingerprint(self, output: str) -> str:
        """Create a fingerprint for output."""
        # Normalize output
        normalized = self._normalize(output)
        return hashlib.sha256(normalized.encode()).hexdigest()[:32]
    
    def _normalize(self, text: str) -> str:
        """Normalize text for consistent fingerprinting."""
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line:
                lines.append(line)
        return "\n".join(lines)


class DeterministicLLM:
    """LLM wrapper that provides deterministic responses.
    
    Usage:
        det_llm = DeterministicLLM(provider=openai_provider)
        
        result = await det_llm.generate(
            prompt="What is 2+2?",
            temperature=0.0,  # Lower temp = more deterministic
        )
    """
    
    def __init__(
        self,
        provider: Any,  # LLM provider interface
        config: DeterministicConfig | None = None,
    ):
        self._provider = provider
        self._config = config or DeterministicConfig()
        
        self._fingerprinter = PromptFingerprinter()
        self._semantic_matcher = SemanticPromptMatcher(
            threshold=self._config.semantic_similarity_threshold
        )
        self._output_fingerprinter = OutputFingerprinter()
        
        # Cache storage
        self._exact_cache: dict[str, LLMCacheEntry] = {}
        self._schema_enforcers: dict[str, SchemaEnforcer] = {}
        
        # Metrics
        self._metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "schema_violations": 0,
        }
    
    def register_schema(self, name: str, schema: dict, version: str = "1.0") -> None:
        """Register an output schema."""
        self._schema_enforcers[name] = SchemaEnforcer(schema=schema, version=version)
    
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        parameters: dict[str, Any] | None = None,
        temperature: float = 0.0,
        model: str | None = None,
        schema_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate a response with deterministic caching.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            parameters: Generation parameters (temperature, etc.)
            temperature: Sampling temperature (0 = deterministic)
            model: Model to use
            schema_name: Name of registered schema to enforce
            
        Returns:
            Dict with response and metadata
        """
        self._metrics["total_requests"] += 1
        
        # Create fingerprint
        params = parameters or {}
        params["temperature"] = temperature
        params["model"] = model
        
        fingerprint = self._fingerprinter.fingerprint(
            prompt=prompt,
            system_prompt=system_prompt,
            parameters=params,
        )
        
        # Check exact cache first
        if fingerprint in self._exact_cache:
            self._metrics["cache_hits"] += 1
            entry = self._exact_cache[fingerprint]
            
            # Verify fingerprint matches
            if entry.prompt_hash == fingerprint:
                logger.debug("exact_cache_hit", fingerprint=fingerprint)
                return {
                    "response": entry.response,
                    "from_cache": True,
                    "fingerprint": fingerprint,
                    "confidence": entry.confidence,
                    "created_at": entry.created_at.isoformat(),
                }
        
        # Make actual LLM call
        try:
            response = await self._provider.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                **params,
            )
            
            # Handle streaming response
            if hasattr(response, '__aiter__'):
                response_text = ""
                async for chunk in response:
                    response_text += chunk
                response = response_text
            
            # Validate schema if registered
            confidence = 1.0
            if schema_name and schema_name in self._schema_enforcers:
                enforcer = self._schema_enforcers[schema_name]
                is_valid, error = enforcer.validate(response)
                if not is_valid:
                    self._metrics["schema_violations"] += 1
                    logger.warning("schema_violation", error=error)
                    confidence = 0.5
            
            # Create cache entry
            entry = LLMCacheEntry(
                prompt_hash=fingerprint,
                response=response,
                created_at=datetime.now(),
                model=model or "unknown",
                temperature=temperature,
                confidence=confidence,
                schema_version=self._config.semantic_similarity_threshold,
            )
            
            # Store in cache (with LRU eviction)
            self._evict_if_needed()
            self._exact_cache[fingerprint] = entry
            
            self._metrics["cache_misses"] += 1
            
            return {
                "response": response,
                "from_cache": False,
                "fingerprint": fingerprint,
                "confidence": confidence,
                "created_at": datetime.now().isoformat(),
            }
            
        except Exception as e:
            logger.exception("llm_generation_failed", error=str(e))
            raise
    
    def _evict_if_needed(self) -> None:
        """Evict oldest entries if cache is full."""
        if len(self._exact_cache) >= self._config.max_cache_size:
            # Remove oldest entries
            sorted_entries = sorted(
                self._exact_cache.items(),
                key=lambda x: x[1].created_at
            )
            
            # Remove 10%
            num_to_remove = self._config.max_cache_size // 10
            for key, _ in sorted_entries[:num_to_remove]:
                del self._exact_cache[key]
    
    def invalidate(self, fingerprint: str | None = None) -> int:
        """Invalidate cache entries.
        
        If fingerprint is None, clears all cache.
        Returns number of entries invalidated.
        """
        if fingerprint is None:
            count = len(self._exact_cache)
            self._exact_cache.clear()
            return count
        
        if fingerprint in self._exact_cache:
            del self._exact_cache[fingerprint]
            return 1
        
        return 0
    
    def get_metrics(self) -> dict[str, Any]:
        """Get deterministic LLM metrics."""
        total = self._metrics["total_requests"]
        hits = self._metrics["cache_hits"]
        
        return {
            **self._metrics,
            "cache_hit_rate": hits / total if total > 0 else 0.0,
            "cache_size": len(self._exact_cache),
        }


# Factory function
def create_deterministic_llm(
    provider: Any,
    enable_semantic_cache: bool = True,
    enable_schema_validation: bool = True,
) -> DeterministicLLM:
    """Create a deterministic LLM wrapper."""
    config = DeterministicConfig(
        enable_semantic_cache=enable_semantic_cache,
        enable_schema_validation=enable_schema_validation,
    )
    return DeterministicLLM(provider=provider, config=config)
