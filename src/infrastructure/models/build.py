from dataclasses import dataclass, field
from typing import List


@dataclass
class BuildError:
    """Represents a compilation error."""

    file: str
    line: int
    column: int
    message: str
    severity: str = "error"

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}: {self.severity}: {self.message}"


@dataclass
class BuildResult:
    """Result of a build operation."""

    status: str
    returncode: int
    stdout: str
    stderr: str
    errors: List[BuildError] = field(default_factory=list)
    duration: float = 0.0


@dataclass
class ToolResult:
    """Result of a non-build tool operation such as flash or runtime observe."""

    status: str
    returncode: int
    stdout: str
    stderr: str
    duration: float = 0.0


@dataclass
class RuntimeDiagnosis:
    """Parsed runtime observation with inferred health signals."""

    status: str
    findings: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_signals: List[str] = field(default_factory=list)
    summary: str = ""
