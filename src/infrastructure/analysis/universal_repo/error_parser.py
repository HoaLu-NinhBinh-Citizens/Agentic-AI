"""Error parser with strategy registration pattern.

Delegates compiler output parsing and formatting to registered
language-specific parsers (gcc, tsc, rustc, go, javac). Each parser
implements the CompilerOutputParser protocol defined in __init__.py.

Requirements: 5.6, 8.1, 8.2, 8.3
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import CompilerError

if TYPE_CHECKING:
    from . import CompilerOutputParser


class ErrorParser:
    """Parses compiler output into structured CompilerError objects.

    Uses a strategy pattern: each supported compiler has a registered
    parser implementing the CompilerOutputParser protocol. Parsing and
    formatting are delegated to the appropriate registered strategy.

    Requirement: 5.6 — Normalized common schema for compiler errors.
    """

    def __init__(self) -> None:
        """Initialize with an empty parser registry."""
        self._parsers: dict[str, CompilerOutputParser] = {}

    @classmethod
    def create_default(cls) -> ErrorParser:
        """Create an ErrorParser pre-registered with all supported parsers.

        Registers gcc, tsc, rustc, go, and javac parsers so the returned
        instance is ready to parse and format output from any supported
        compiler without additional setup.

        Returns:
            An ErrorParser instance with all 5 parsers registered.
        """
        from .parsers import GccParser, GoParser, JavacParser, RustcParser, TscParser

        instance = cls()
        instance.register_parser("gcc", GccParser())
        instance.register_parser("tsc", TscParser())
        instance.register_parser("rustc", RustcParser())
        instance.register_parser("go", GoParser())
        instance.register_parser("javac", JavacParser())
        return instance

    def register_parser(self, compiler: str, parser: CompilerOutputParser) -> None:
        """Register a parser strategy for a specific compiler.

        Args:
            compiler: Compiler identifier (e.g., "gcc", "tsc", "rustc", "go", "javac").
            parser: An object implementing the CompilerOutputParser protocol.
        """
        self._parsers[compiler] = parser

    def parse(self, output: str, compiler: str) -> list[CompilerError]:
        """Parse raw compiler output using the registered strategy.

        Delegates to the parser registered for the given compiler name.

        Args:
            output: Raw text output from a compiler invocation.
            compiler: Compiler identifier to select the correct parser.

        Returns:
            List of structured CompilerError objects extracted from the output.

        Raises:
            ValueError: If no parser is registered for the given compiler.
        """
        parser = self._parsers.get(compiler)
        if parser is None:
            raise ValueError(
                f"No parser registered for compiler '{compiler}'. "
                f"Registered compilers: {self.get_supported_compilers()}"
            )
        return parser.parse(output)

    def format(self, error: CompilerError, style: str) -> str:
        """Format a CompilerError into a human-readable string.

        Delegates to the parser registered for the given style (compiler name).

        Args:
            error: A structured CompilerError object.
            style: Output style matching a registered compiler name
                   (e.g., "gcc", "tsc", "rustc", "go", "javac").

        Returns:
            Human-readable string in the compiler's native output format.

        Raises:
            ValueError: If no parser is registered for the given style.
        """
        parser = self._parsers.get(style)
        if parser is None:
            raise ValueError(
                f"No parser registered for style '{style}'. "
                f"Registered compilers: {self.get_supported_compilers()}"
            )
        return parser.format(error)

    def get_supported_compilers(self) -> list[str]:
        """List all registered compiler identifiers.

        Returns:
            Sorted list of compiler names with registered parsers.
        """
        return sorted(self._parsers.keys())


def create_error_parser() -> ErrorParser:
    """Factory function to create an ErrorParser with all parsers registered.

    Convenience function that creates and returns an ErrorParser instance
    pre-registered with gcc, tsc, rustc, go, and javac parsers.

    Returns:
        An ErrorParser instance ready to parse and format all supported compilers.
    """
    return ErrorParser.create_default()
