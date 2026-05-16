"""Token usage tracker stub."""

from typing import Any


class TokenUsage:
    """Tracks LLM token usage."""
    
    def __init__(self):
        self._total_input = 0
        self._total_output = 0
    
    def record(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage."""
        self._total_input += input_tokens
        self._total_output += output_tokens
    
    def get_total(self) -> dict[str, int]:
        """Get total token usage."""
        return {
            "input": self._total_input,
            "output": self._total_output,
            "total": self._total_input + self._total_output,
        }
