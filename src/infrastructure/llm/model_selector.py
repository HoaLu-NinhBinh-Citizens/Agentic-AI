"""Auto model selection based on query complexity."""

import os
import re
from enum import Enum
from typing import Optional


class Complexity(Enum):
    """Query complexity levels."""
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


# Keywords that indicate higher complexity
SIMPLE_KEYWORDS = [
    "what", "how", "explain", "list", "show", "tell me",
    "what is", "how to", "can you explain", "what does",
    "describe", "define", "what are",
]

MEDIUM_KEYWORDS = [
    "write", "create", "generate", "make", "add", "implement",
    "modify", "change", "update", "fix", "refactor",
    "help me", "i need", "please",
]

COMPLEX_KEYWORDS = [
    "optimize", "design", "architecture", "complex", "advanced",
    "multithread", "rtos", "optimization", "performance",
    "critical", "safety", "real-time", "bare-metal",
    "bootloader", "driver", "interrupt", "dma",
    "secure", "encryption", "protocol", "can bus", "i2c", "spi",
    "usb", "ethernet", "wireless", "ble", "lora",
    "pcb", "schematic", "kiCad", "altium",
]


class ModelSelector:
    """Select appropriate model based on query complexity and task type."""

    def __init__(
        self,
        simple_model: Optional[str] = None,
        medium_model: Optional[str] = None,
        complex_model: Optional[str] = None,
    ):
        self.simple_model = simple_model or os.environ.get(
            "CARV_MODEL_SIMPLE", "llama3.1:8b"
        )
        self.medium_model = medium_model or os.environ.get(
            "CARV_MODEL_MEDIUM", "llama3.1:8b"
        )
        self.complex_model = complex_model or os.environ.get(
            "CARV_MODEL_COMPLEX", "codellama:13b"
        )

    def classify(self, prompt: str) -> Complexity:
        """Classify the complexity of a prompt."""
        prompt_lower = prompt.lower()

        # Count keyword matches
        complex_matches = sum(1 for kw in COMPLEX_KEYWORDS if kw in prompt_lower)
        medium_matches = sum(1 for kw in MEDIUM_KEYWORDS if kw in prompt_lower)
        simple_matches = sum(1 for kw in SIMPLE_KEYWORDS if kw in prompt_lower)

        # Code block detection
        has_code_block = bool(re.search(r"```[\s\S]*?```", prompt))
        has_file_refs = bool(re.search(r"\b(file|path|src|c|h|py)\b", prompt_lower))
        has_error_msg = bool(re.search(
            r"(error|warning|exception|failed|undefined|conflict)", prompt_lower
        ))

        # Length factor
        length_factor = len(prompt) / 500

        # Scoring
        score = 0
        score += complex_matches * 3
        score += medium_matches * 2
        score += simple_matches * 1
        score += length_factor

        if has_code_block:
            score += 2
        if has_file_refs:
            score += 1
        if has_error_msg:
            score += 2

        # Classify based on score
        if score >= 8 or (complex_matches >= 2 and has_code_block):
            return Complexity.COMPLEX
        elif score >= 4 or has_code_block or has_error_msg:
            return Complexity.MEDIUM
        else:
            return Complexity.SIMPLE

    def select(self, prompt: str, task_type: str = "auto") -> str:
        """
        Select the best model for the given prompt.

        Args:
            prompt: The user prompt
            task_type: Optional task type hint (code_generation, fix_errors, etc.)

        Returns:
            Model name to use
        """
        complexity = self.classify(prompt)

        # Task-specific overrides
        if task_type == "fix_errors":
            # Fixes need a capable model
            if complexity == Complexity.SIMPLE:
                return self.medium_model
            return self.complex_model

        if task_type == "code_generation":
            # Code gen needs medium or complex
            if complexity == Complexity.SIMPLE:
                return self.medium_model
            return self.complex_model

        if task_type == "simple":
            return self.simple_model

        # Default behavior based on complexity
        if complexity == Complexity.SIMPLE:
            return self.simple_model
        elif complexity == Complexity.MEDIUM:
            return self.medium_model
        else:
            return self.complex_model

    def select_provider(self, prompt: str) -> str:
        """
        Select the best provider for the prompt.
        For now, returns 'ollama' for local models.
        """
        complexity = self.classify(prompt)

        # For complex tasks, might want to use cloud API if available
        if complexity == Complexity.COMPLEX:
            # Could check for OPENAI_API_KEY etc. and return "openai"
            pass

        return "ollama"
