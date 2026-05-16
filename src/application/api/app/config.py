"""Configuration constants for Embedded Agent."""

# LLM Stage Timeouts (seconds)
LLM_STAGE_TIMEOUTS = {
    "generate": 150,
    "fix": 120,
    "review": 90,
    "chapter_worker": 75,
}

__all__ = [
    "LLM_STAGE_TIMEOUTS",
]
