"""Diagnostics runner for compile-time and lint errors.

This module runs language-specific linters/compilers and parses errors
into a structured format for feeding back to the LLM.
"""

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class Diagnostic:
    """A single diagnostic (error or warning)."""
    file: str
    line: int
    column: int
    severity: str  # "error" or "warning"
    message: str
    code: Optional[str] = None


class DiagnosticsRunner:
    """Run diagnostics using language-specific tools."""

    # Compiler regex patterns for error parsing
    GCC_PATTERN = re.compile(
        r"([^:]+):(\d+):(\d+):\s*(error|warning):\s*(.+?)(?:\s+\[([^\]]+)\])?$"
    )
    CLANG_PATTERN = re.compile(
        r"([^:]+):(\d+):(\d+):\s*(error|warning):\s*(.+)$"
    )
    ARM_GCC_PATTERN = re.compile(
        r"([^:]+):(\d+):(\d+):\s*(error|warning):\s*(.+?)(?:\s+\[([^\]]+)\])?$"
    )

    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else Path.cwd()
        self.timeout_seconds = 30

    def run(
        self,
        file_path: str,
        compiler: str = "gcc",
        extra_args: Optional[list] = None,
    ) -> list[Diagnostic]:
        """
        Run diagnostics on a single file.

        Args:
            file_path: Path to the file to check
            compiler: Compiler to use (gcc, clang, arm-none-eabi-gcc)
            extra_args: Extra arguments to pass to the compiler

        Returns:
            List of Diagnostic objects
        """
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            return []

        cmd = self._build_command(compiler, file_path, extra_args)
        if not cmd:
            return []

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
            return self._parse_output(result.stderr + result.stdout, compiler)
        except (subprocess.TimeoutExpired, subprocess.SubprocessError):
            return []

    def run_directory(
        self,
        directory: str,
        pattern: str = "*.c",
        compiler: str = "gcc",
    ) -> list[Diagnostic]:
        """Run diagnostics on all files matching pattern in a directory."""
        directory = Path(directory)
        if not directory.exists():
            return []

        diagnostics = []
        for file_path in directory.rglob(pattern):
            # Skip vendor directories
            if self._is_vendor_managed(file_path):
                continue
            diagnostics.extend(self.run(str(file_path), compiler))

        return diagnostics

    def _build_command(
        self,
        compiler: str,
        file_path: Path,
        extra_args: Optional[list],
    ) -> Optional[list]:
        """Build the command for running diagnostics."""
        if compiler == "gcc":
            return [
                "gcc",
                "-fsyntax-only",
                "-Wall",
                "-Wextra",
                "-fdiagnostics-color=never",
                "-I", str(self.project_root),
                *self._get_include_flags(file_path.parent),
                str(file_path),
                *(extra_args or []),
            ]
        elif compiler == "clang":
            return [
                "clang",
                "-fsyntax-only",
                "-Wall",
                "-Wextra",
                "-fdiagnostics-color=never",
                "-I", str(self.project_root),
                *self._get_include_flags(file_path.parent),
                str(file_path),
                *(extra_args or []),
            ]
        elif compiler == "arm-none-eabi-gcc":
            return [
                "arm-none-eabi-gcc",
                "-fsyntax-only",
                "-mcpu=cortex-m4",
                "-mthumb",
                "-Wall",
                "-Wextra",
                "-Idrivers/CMSIS/Include",
                "-Idrivers/CMSIS/Device/ST/STM32F4xx/Include",
                "-Idrivers/STM32F4xx_HAL_Driver/Inc",
                str(file_path),
                *(extra_args or []),
            ]
        return None

    def _get_include_flags(self, file_dir: Path) -> list:
        """Get include flags based on file location."""
        flags = []
        # Common include directories
        common_dirs = ["include", "inc", "src", "drivers", "libraries"]
        for common in common_dirs:
            for parent in file_dir.parents:
                inc_dir = parent / common
                if inc_dir.exists() and inc_dir.is_dir():
                    flags.extend(["-I", str(inc_dir)])
                    break
        return flags

    def _is_vendor_managed_path(self, file_path: Path) -> bool:
        """Check if file is in a vendor-managed directory."""
        vendor_dirs = {"vendor", "third_party", "CMSIS", "STM32F4xx_HAL_Driver"}
        return any(part in vendor_dirs for part in file_path.parts)

    def _parse_output(self, output: str, compiler: str) -> list[Diagnostic]:
        """Parse compiler output into Diagnostic objects."""
        diagnostics = []
        pattern = self._get_pattern(compiler)

        for line in output.splitlines():
            match = pattern.match(line.strip())
            if match:
                diagnostics.append(Diagnostic(
                    file=match.group(1),
                    line=int(match.group(2)),
                    column=int(match.group(3)),
                    severity=match.group(4),
                    message=match.group(5).strip(),
                    code=match.group(6) if match.group(6) else None,
                ))

        return diagnostics

    def _get_pattern(self, compiler: str):
        """Get the appropriate regex pattern for the compiler."""
        if compiler == "gcc":
            return self.GCC_PATTERN
        elif compiler == "clang":
            return self.CLANG_PATTERN
        elif compiler == "arm-none-eabi-gcc":
            return self.ARM_GCC_PATTERN
        return self.GCC_PATTERN

    def format_for_llm(self, diagnostics: list[Diagnostic]) -> str:
        """Format diagnostics for inclusion in LLM prompt."""
        if not diagnostics:
            return ""

        lines = ["[DIAGNOSTICS]"]
        for d in diagnostics:
            severity_tag = "[ERROR]" if d.severity == "error" else "[WARNING]"
            lines.append(f"{severity_tag} {d.file}:{d.line}:{d.column}: {d.message}")
            if d.code:
                lines.append(f"  Code: {d.code}")
        return "\n".join(lines)
