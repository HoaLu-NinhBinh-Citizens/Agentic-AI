"""Compiler output parsers for the Universal Repo Handler.

Each parser implements the CompilerOutputParser protocol defined in the
parent package, providing parse() and format() methods for a specific
compiler's output format.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
"""

from __future__ import annotations

from .gcc_parser import GccParser
from .go_parser import GoParser
from .javac_parser import JavacParser
from .rustc_parser import RustcParser
from .tsc_parser import TscParser

__all__ = [
    "GccParser",
    "GoParser",
    "JavacParser",
    "RustcParser",
    "TscParser",
]
