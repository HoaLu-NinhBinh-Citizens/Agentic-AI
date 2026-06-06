"""Reporting infrastructure for AI_SUPPORT code review output."""

from src.infrastructure.reporting.markdown_report import (
    MarkdownReportGenerator,
    Finding,
    PipelineStats,
    Severity,
)
from src.infrastructure.reporting.cli_report import CLIReportGenerator
from src.infrastructure.reporting.json_report import JSONReportGenerator
from src.infrastructure.reporting.html_report import HTMLReportGenerator
from src.infrastructure.reporting.syntax_highlight import (
    highlight_code,
    highlight_diff,
    detect_language,
)

__all__ = [
    "MarkdownReportGenerator",
    "CLIReportGenerator",
    "JSONReportGenerator",
    "HTMLReportGenerator",
    "Finding",
    "PipelineStats",
    "Severity",
    "highlight_code",
    "highlight_diff",
    "detect_language",
]
