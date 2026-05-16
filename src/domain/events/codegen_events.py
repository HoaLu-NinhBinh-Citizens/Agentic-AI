"""Codegen events domain module."""

from dataclasses import dataclass


@dataclass
class CodegenEvent:
    """Code generation event."""
    file: str
    lines: int
