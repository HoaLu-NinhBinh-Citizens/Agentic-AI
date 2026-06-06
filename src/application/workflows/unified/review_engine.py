"""Unified ReviewEngine — single entry point for all code review operations.

This module provides the main orchestration layer that:
1. Builds CodeContext for all files using ReferenceGraph and DependencyGraph
2. Runs all detectors with unified context
3. Deduplicates and ranks findings
4. Generates intelligent fix suggestions
5. Formats output

Architecture:
    UnifiedReviewEngine
    ├── SafeTreeSitterIndexer (AST parsing)
    ├── ReferenceGraph (symbol references)
    ├── DependencyGraph (imports/exports)
    ├── CodeContextBuilder (context aggregation)
    ├── Detector[] (ML, Security, Quality, Embedded)
    ├── SuggestionEngine (fix generation)
    └── ResultFormatter (output)

Usage:
    config = ReviewEngineConfig(
        focus_areas=["security", "quality"],
        output_format="markdown"
    )
    engine = UnifiedReviewEngine(config)
    result = await engine.review(["src/file.py", "src/other.py"])
    print(result.output)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from src.application.workflows.unified.code_context import CodeContext, CodeContextBuilder
from src.application.workflows.unified.detector_base import (
    Detector,
    DetectorConfig,
    DetectorRegistry,
    Finding,
    FindingSeverity,
)
from src.application.workflows.unified.detectors import (
    MlDetector,
    SecurityDetector,
    QualityDetector,
    EmbeddedDetector,
)
from src.application.workflows.unified.result_formatter import (
    PipelineStats,
    ResultFormatter,
    MarkdownFormatter,
    get_formatter,
    UnifiedMarkdownFormatter,
)
from src.domain.models.review_issue import ReviewIssue
from src.application.workflows.unified.suggestion_engine import SuggestionEngine
from src.infrastructure.indexing.tree_sitter import SafeTreeSitterIndexer
from src.infrastructure.indexing.reference_graph import ReferenceGraph
from src.infrastructure.indexing.dependency_graph import DependencyGraph
from src.infrastructure.performance import (
    ParallelProcessor,
    IncrementalProcessor,
    CacheManager,
)

logger = logging.getLogger(__name__)


def _finding_to_review_issue(finding: Finding) -> "ReviewIssue":
    """Convert a legacy Finding to a unified ReviewIssue for formatting."""
    from src.domain.models.review_issue import ReviewIssue, CodeEvidence, FixOption, generate_issue_id

    old_code = finding.metadata.get("old_code", finding.context or "")
    new_code = finding.metadata.get("new_code", "")

    evidence = CodeEvidence(
        file=finding.file,
        line_start=finding.line,
        line_end=finding.end_line or finding.line,
        old_code=old_code,
        new_code=new_code,
    )

    fixes = []
    if finding.fix:
        fix_option = FixOption(
            id=f"fix-{finding.rule_id}-{finding.line}",
            title=finding.rule_name or f"Fix {finding.rule_id}",
            description="Suggested fix",
            old_code=old_code,
            new_code=new_code,
            risk=finding.severity,
            confidence=finding.confidence,
        )
        fixes.append(fix_option)

    return ReviewIssue(
        id=generate_issue_id(finding.rule_id, finding.file, finding.line),
        rule_id=finding.rule_id,
        severity=finding.severity,
        file=finding.file,
        line=finding.line,
        end_line=finding.end_line or finding.line,
        title=finding.rule_name or finding.rule_id,
        message=finding.message,
        explanation=finding.metadata.get("explanation", ""),
        evidence=evidence,
        fixes=fixes,
        confidence=finding.confidence,
        tags=finding.metadata.get("tags", []),
        detector=finding.detector,
        detection_method=finding.metadata.get("detection_method", ""),
    )


# ─── Config ──────────────────────────────────────────────────────────────────────


@dataclass
class ReviewEngineConfig:
    """Configuration for UnifiedReviewEngine.

    Attributes:
        focus_areas: Areas to focus on (e.g., ["security", "quality", "ml", "embedded"])
        output_format: Output format ("markdown", "json", "console")
        languages: Restrict to specific languages (None = all)
        confidence_threshold: Minimum confidence for findings
        max_findings_per_file: Cap findings per file (0 = unlimited)
        include_stats: Include statistics in output
        enable_parallel: Enable parallel file processing
        max_workers: Max parallel workers for file processing
        enable_incremental: Skip unchanged files (requires cache)
        enable_caching: Cache results for faster subsequent runs
    """
    focus_areas: list[str] = field(default_factory=lambda: [
        "security", "quality", "ml", "embedded"
    ])
    output_format: str = "markdown"
    languages: list[str] = field(default_factory=list)
    confidence_threshold: float = 0.5
    max_findings_per_file: int = 50
    include_stats: bool = True
    enable_parallel: bool = True
    max_workers: int = 4
    enable_incremental: bool = True
    enable_caching: bool = True


# ─── Review Result ───────────────────────────────────────────────────────────────


@dataclass
class ReviewResult:
    """Result of a code review operation.

    Attributes:
        findings: All findings from the review
        stats: Statistics about the review
        suggestions: Suggested fixes
        output: Formatted output string
        contexts: Built contexts (for debugging/inspection)
    """
    findings: list[Finding]
    stats: PipelineStats
    suggestions: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""
    contexts: dict[str, CodeContext] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "stats": self.stats.to_dict(),
            "suggestions": self.suggestions,
            "output": self.output,
        }


# ─── Main Engine ────────────────────────────────────────────────────────────────


class UnifiedReviewEngine:
    """Single entry point for all code review operations.

    This orchestrator:
    1. Initializes all required components (indexer, graphs, detectors)
    2. Builds CodeContext for all files
    3. Runs all detectors in parallel
    4. Deduplicates and ranks findings
    5. Generates fix suggestions
    6. Formats output

    Usage:
        config = ReviewEngineConfig(focus_areas=["security"])
        engine = UnifiedReviewEngine(config)
        result = await engine.review(["path/to/file.py"])
    """

    def __init__(self, config: Optional[ReviewEngineConfig] = None) -> None:
        """Initialize the review engine.

        Args:
            config: Engine configuration
        """
        self.config = config or ReviewEngineConfig()
        self._init_components()
        self._init_performance_components()

    def _init_performance_components(self) -> None:
        """Initialize performance optimization components."""
        self._parallel_processor = ParallelProcessor(
            max_workers=self.config.max_workers,
            chunk_size=100
        )
        self._incremental_processor = IncrementalProcessor(
            cache_dir=Path(".ai_support/index_cache")
        )
        self._cache = CacheManager(
            cache_dir=Path(".ai_support/results_cache"),
            max_memory_mb=500
        )

    def _init_components(self) -> None:
        """Initialize all required components."""
        # Core indexing infrastructure
        self.indexer = SafeTreeSitterIndexer()
        self.ref_graph = ReferenceGraph(self.indexer)
        self.dep_graph = DependencyGraph()

        # Context builder
        self.context_builder = CodeContextBuilder(
            self.indexer, self.ref_graph, self.dep_graph
        )

        # Detectors
        self._init_detectors()

        # Output formatter
        self.formatter: ResultFormatter = get_formatter(self.config.output_format)

        # Suggestion engine
        self.suggestion_engine = SuggestionEngine()

    def _init_detectors(self) -> None:
        """Initialize and register all detectors based on focus areas."""
        self.detectors: list[Detector] = []
        self._registry = DetectorRegistry()

        # Create detector config
        detector_config = DetectorConfig(
            focus_areas=self.config.focus_areas,
            confidence_threshold=self.config.confidence_threshold,
            languages=self.config.languages,
            max_findings_per_file=self.config.max_findings_per_file,
        )

        # Add detectors based on focus areas
        if self._should_include("ml"):
            ml_detector = MlDetector(detector_config)
            self.detectors.append(ml_detector)
            self._registry.register("ml", ml_detector)

        if self._should_include("security"):
            sec_detector = SecurityDetector(detector_config)
            self.detectors.append(sec_detector)
            self._registry.register("security", sec_detector)

        if self._should_include("quality"):
            qual_detector = QualityDetector(detector_config)
            self.detectors.append(qual_detector)
            self._registry.register("quality", qual_detector)

        if self._should_include("embedded"):
            emb_detector = EmbeddedDetector(detector_config)
            self.detectors.append(emb_detector)
            self._registry.register("embedded", emb_detector)

    def _should_include(self, area: str) -> bool:
        """Check if area should be included based on config.

        Args:
            area: Area name

        Returns:
            True if should be included
        """
        if not self.config.focus_areas:
            return True
        return area in self.config.focus_areas

    async def review(
        self,
        paths: list[Path | str],
        focus_areas: Optional[list[str]] = None,
        output_format: Optional[str] = None,
        incremental: bool = True,
    ) -> ReviewResult:
        """Run code review on the specified paths.

        Args:
            paths: List of file/directory paths to review
            focus_areas: Override focus areas for this run
            output_format: Override output format
            incremental: Use incremental processing (skip unchanged files)

        Returns:
            ReviewResult with findings, stats, and formatted output
        """
        start_time = time.time()

        # Update config if overrides provided
        if focus_areas:
            self.config.focus_areas = focus_areas
            self._init_detectors()

        if output_format:
            self.config.output_format = output_format
            self.formatter = get_formatter(output_format)

        # Expand directories to files
        file_paths = await self._expand_paths(paths)

        if not file_paths:
            logger.warning("No files to review")
            return ReviewResult(
                findings=[],
                stats=PipelineStats(),
                output="No files found to review.",
            )

        # Incremental processing - skip unchanged files
        if incremental and self.config.enable_incremental:
            changed_files, _ = self._incremental_processor.get_changed_files(file_paths)
            logger.info("Incremental: %d changed, %d unchanged",
                        len(changed_files), len(file_paths) - len(changed_files))
        else:
            changed_files = file_paths

        if not changed_files:
            logger.info("No changed files to process")
            return ReviewResult(
                findings=[],
                stats=PipelineStats.from_findings([], (time.time() - start_time) * 1000),
                output="No changes detected since last run.",
            )

        # Build contexts for changed files only
        contexts = await self._build_contexts(changed_files)

        # Run all detectors
        all_findings = await self._run_detectors(contexts)

        # Deduplicate findings
        findings = self._deduplicate(all_findings)

        # Generate suggestions
        suggestions = await self._generate_suggestions(findings, contexts)

        # Calculate stats
        execution_time_ms = (time.time() - start_time) * 1000
        # Pass actual number of files scanned - a clean file still counts as scanned
        stats = PipelineStats.from_findings(
            findings,
            execution_time_ms=execution_time_ms,
            detectors_used=[d.name for d in self.detectors],
            files_scanned=len(contexts),  # Actual files processed (may be fewer than input due to errors)
        )

        # Format output - convert findings to ReviewIssues for unified formatters
        issues = [_finding_to_review_issue(f) for f in findings]
        output = self.formatter.format(issues, stats)

        return ReviewResult(
            findings=findings,
            stats=stats,
            suggestions=suggestions,
            output=output,
            contexts=contexts,
        )

    async def _expand_paths(self, paths: list[Path | str]) -> list[Path]:
        """Expand paths to individual files.

        Args:
            paths: Input paths (files or directories)

        Returns:
            List of file paths
        """
        file_paths: list[Path] = []
        seen: set[str] = set()

        for path in paths:
            p = Path(path) if isinstance(path, str) else path

            if p.is_file():
                if str(p) not in seen:
                    seen.add(str(p))
                    file_paths.append(p)
            elif p.is_dir():
                # Find all source files
                for ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".c", ".cpp", ".h", ".rs", ".go", ".java"]:
                    for f in p.rglob(f"*{ext}"):
                        if str(f) not in seen:
                            seen.add(str(f))
                            file_paths.append(f)

        return file_paths

    async def _build_contexts(
        self,
        file_paths: list[Path],
    ) -> dict[str, CodeContext]:
        """Build CodeContext for all files.

        Args:
            file_paths: List of file paths

        Returns:
            Dict mapping file path to CodeContext
        """
        contexts: dict[str, CodeContext] = {}

        # Build reference graph first (needed for symbol info)
        if file_paths:
            await self.ref_graph.index_directory(str(file_paths[0].parent))

        if self.config.enable_parallel and len(file_paths) > 1:
            # Parallel processing with semaphore for rate limiting
            semaphore = asyncio.Semaphore(self.config.max_workers)

            async def build_with_limit(p: Path) -> tuple[str, CodeContext]:
                async with semaphore:
                    try:
                        return str(p), await self.context_builder.build(p)
                    except Exception as e:
                        logger.warning("Failed to build context for %s: %s", p, e)
                        return str(p), None

            tasks = [build_with_limit(p) for p in file_paths]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, tuple) and result[1] is not None:
                    contexts[result[0]] = result[1]
        else:
            # Sequential processing
            for path in file_paths:
                try:
                    context = await self.context_builder.build(path)
                    contexts[str(path)] = context
                except Exception as e:
                    logger.warning("Failed to build context for %s: %s", path, e)

        return contexts

    async def _run_detectors(
        self,
        contexts: dict[str, CodeContext],
    ) -> list[Finding]:
        """Run all detectors on the contexts.

        Args:
            contexts: Dict of file path to CodeContext

        Returns:
            Combined list of findings
        """
        all_findings: list[Finding] = []

        # Run each detector
        for detector in self.detectors:
            if self.config.enable_parallel and len(contexts) > 1:
                # Parallel detection
                findings = await asyncio.to_thread(
                    detector.detect_batch, contexts
                )
            else:
                # Sequential detection
                findings = []
                for ctx in contexts.values():
                    file_findings = detector.detect(ctx)
                    findings.extend(file_findings)

            all_findings.extend(findings)
            logger.info(
                "Detector %s found %d findings",
                detector.name, len(findings)
            )

        return all_findings

    def _deduplicate(self, findings: list[Finding]) -> list[Finding]:
        """Deduplicate and sort findings.

        Args:
            findings: Raw findings from all detectors

        Returns:
            Deduplicated and sorted findings
        """
        seen: set[tuple[str, str, int, int, str]] = set()
        unique: list[Finding] = []

        for finding in findings:
            # Skip low confidence
            if finding.confidence < self.config.confidence_threshold:
                continue

            # Deduplication key
            key = (
                finding.rule_id,
                finding.file,
                finding.line,
                finding.end_line,
                finding.message[:50],  # Truncate for comparison
            )

            if key not in seen:
                seen.add(key)
                unique.append(finding)
            else:
                # Keep higher confidence version
                existing = next(
                    (f for f in unique if f.file == finding.file and f.line == finding.line),
                    None
                )
                if existing and finding.confidence > existing.confidence:
                    unique[unique.index(existing)] = finding

        # Sort by severity, confidence, then line
        unique.sort(
            key=lambda f: (
                -f.severity.to_numeric(),
                -f.confidence,
                f.line,
            )
        )

        # Limit findings per file
        if self.config.max_findings_per_file > 0:
            unique = self._limit_per_file(unique)

        return unique

    def _limit_per_file(self, findings: list[Finding]) -> list[Finding]:
        """Limit findings per file.

        Args:
            findings: Sorted findings

        Returns:
            Limited findings
        """
        limited: list[Finding] = []
        file_counts: dict[str, int] = {}

        for finding in findings:
            count = file_counts.get(finding.file, 0)
            if count < self.config.max_findings_per_file:
                limited.append(finding)
                file_counts[finding.file] = count + 1

        return limited

    async def _generate_suggestions(
        self,
        findings: list[Finding],
        contexts: dict[str, CodeContext],
    ) -> list[dict[str, Any]]:
        """Generate fix suggestions for findings.

        Args:
            findings: Findings to generate suggestions for
            contexts: File contexts

        Returns:
            List of suggestion dicts
        """
        suggestions: list[dict[str, Any]] = []

        # Get top findings with fixes
        top_findings = [
            f for f in findings
            if f.fix and f.severity in (FindingSeverity.ERROR, FindingSeverity.WARNING)
        ][:20]  # Limit suggestions

        for finding in top_findings:
            context = contexts.get(finding.file)
            suggestion = await self.suggestion_engine.generate(finding, context)
            if suggestion:
                suggestions.append(suggestion)

        return suggestions

    def get_detectors(self) -> list[str]:
        """Get list of available detector names.

        Returns:
            List of detector names
        """
        return [d.name for d in self.detectors]

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the engine.

        Returns:
            Statistics dict
        """
        return {
            "detectors": [d.name for d in self.detectors],
            "config": {
                "focus_areas": self.config.focus_areas,
                "output_format": self.config.output_format,
                "confidence_threshold": self.config.confidence_threshold,
                "enable_parallel": self.config.enable_parallel,
                "max_workers": self.config.max_workers,
                "enable_incremental": self.config.enable_incremental,
            },
            "reference_graph": self.ref_graph.get_stats(),
            "dependency_graph": self.dep_graph.get_stats(),
            "performance": {
                "cache_hits": self._cache.stats.hits,
                "cache_misses": self._cache.stats.misses,
                "cache_hit_rate": self._cache.stats.hit_rate,
            },
        }


# ─── Factory Function ───────────────────────────────────────────────────────────


def create_review_engine(
    focus_areas: Optional[list[str]] = None,
    output_format: str = "markdown",
) -> UnifiedReviewEngine:
    """Create a configured review engine.

    Args:
        focus_areas: Focus areas to enable
        output_format: Output format

    Returns:
        Configured UnifiedReviewEngine
    """
    config = ReviewEngineConfig(
        focus_areas=focus_areas or ["security", "quality", "ml"],
        output_format=output_format,
    )
    return UnifiedReviewEngine(config)


# ─── CLI Entry Point ─────────────────────────────────────────────────────────────


async def main() -> None:
    """CLI entry point for the review engine."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Unified Code Review Engine")
    parser.add_argument("paths", nargs="+", help="Files or directories to review")
    parser.add_argument(
        "--focus",
        "-f",
        nargs="+",
        choices=["ml", "security", "quality", "embedded"],
        help="Focus areas",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json", "console"],
        default="markdown",
        help="Output format",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Confidence threshold",
    )

    args = parser.parse_args()

    engine = create_review_engine(
        focus_areas=args.focus,
        output_format=args.format,
    )

    result = await engine.review(args.paths)

    print(result.output)

    # Exit with error code if critical findings
    if result.stats.errors_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
