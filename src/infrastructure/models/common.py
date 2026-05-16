from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class BenchmarkCase:
    """One deterministic benchmark case for the agent."""

    name: str
    query: str
    expected_substrings: List[str] = field(default_factory=list)


@dataclass
class BenchmarkResult:
    """Outcome of one benchmark case."""

    name: str
    passed: bool
    details: str
    duration: float = 0.0
    payload: Dict = field(default_factory=dict)


@dataclass
class ChapterNote:
    """Structured note produced by one RM-focused worker."""

    chapter: str
    note_path: str
    content: Dict = field(default_factory=dict)


@dataclass(frozen=True)
class DomainProfile:
    """Small domain adapter description used by retrieval and planning."""

    name: str
    family_tokens: Tuple[str, ...] = ()
    chip_tokens: Tuple[str, ...] = ()
    keyword_markers: Tuple[str, ...] = ()
    preferred_doc_types: Tuple[str, ...] = ()
    avoid_doc_types: Tuple[str, ...] = ()
