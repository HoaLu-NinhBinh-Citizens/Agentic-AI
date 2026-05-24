"""Citation tracking for hardware evidence sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SourceType(Enum):
    """Source type for citations."""
    RM = "reference_manual"       # Reference Manual (e.g. RM0090)
    SVD = "svd"                    # CMSIS SVD file
    CODE = "code"                  # Source code
    DATASHEET = "datasheet"        # Chip datasheet
    APP_NOTE = "app_note"          # Application note
    HARDWARE_MODEL = "hw_model"   # Hardware model
    ERROR_LOG = "error_log"       # Past error analysis
    USER_FEEDBACK = "user_feedback"  # User corrections


@dataclass
class Citation:
    """
    A citation referencing a hardware evidence source.

    Tracks where knowledge comes from so LLM can cite evidence.
    """
    source: str                    # e.g. "RM0090", "STM32F407.svd", "main.c"
    text: str                      # Excerpt or description
    source_type: SourceType
    page: int | None = None        # Page number in document
    section: str | None = None     # Section name/number
    line_start: int | None = None  # Line number (for code)
    line_end: int | None = None
    url: str | None = None         # Optional URL
    chip_family: str | None = None # e.g. "STM32F407"
    peripheral: str | None = None  # e.g. "CAN1"
    register: str | None = None     # e.g. "CAN_MCR"
    confidence: float = 1.0        # Confidence in citation correctness (0-1)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def formatted(self) -> str:
        """Format citation as readable string."""
        parts = [f"[{self.source}"]
        if self.source_type == SourceType.RM and self.page:
            parts.append(f"p.{self.page}")
        elif self.source_type == SourceType.CODE and self.line_start:
            if self.line_end:
                parts.append(f"L{self.line_start}-{self.line_end}")
            else:
                parts.append(f"L{self.line_start}")
        if self.section:
            parts.append(f"§{self.section}")
        if self.peripheral:
            parts.append(f"({self.peripheral})")
        parts.append("]")
        return " ".join(parts)

    def to_llm_context(self) -> str:
        """Format as LLM context snippet."""
        ctx = f"Source: {self.source}"
        if self.source_type.value:
            ctx += f" ({self.source_type.value})"
        if self.page:
            ctx += f", p.{self.page}"
        if self.section:
            ctx += f", §{self.section}"
        if self.peripheral:
            ctx += f"\nPeripheral: {self.peripheral}"
        if self.register:
            ctx += f"\nRegister: {self.register}"
        ctx += f"\n{self.text}"
        return ctx

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_type": self.source_type.value,
            "page": self.page,
            "section": self.section,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "text": self.text,
            "url": self.url,
            "chip_family": self.chip_family,
            "peripheral": self.peripheral,
            "register": self.register,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class CitationChain:
    """
    A chain of citations forming an evidence trail.

    Used to trace how a conclusion was reached through multiple sources.
    """
    id: str
    citations: list[Citation] = field(default_factory=list)
    conclusion: str = ""
    confidence: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)

    def add(self, citation: Citation) -> None:
        """Add citation to the chain."""
        self.citations.append(citation)
        self.confidence *= citation.confidence

    def to_llm_context(self) -> str:
        """Format chain as LLM evidence trail."""
        lines = [
            f"[Evidence Chain: {self.id}]",
            f"Conclusion: {self.conclusion}",
            "",
        ]
        for i, c in enumerate(self.citations, 1):
            lines.append(f"  [{i}] {c.to_llm_context()}")
        lines.append(f"\nChain Confidence: {self.confidence:.2%}")
        return "\n".join(lines)
