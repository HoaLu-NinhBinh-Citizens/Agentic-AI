"""Workspace legacy folder migration utilities."""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict

from src.core.config.agent_prompts import AI_SUPPORT_ROOT

logger = logging.getLogger(__name__)


class LegacyMigrator:
    """Move legacy AI support folders into the canonical workspace-level AI_support root."""

    def __init__(self, build_root: Path, memory) -> None:
        self.build_root = build_root
        self.memory = memory

    def migrate(self) -> None:
        """Execute all legacy folder migrations and auto-compact memory if needed."""
        workspace_root = self.build_root.parent  # project root is parent of build_root
        legacy_roots = [
            self.build_root / "output" / "ai_generated",
            self.build_root / "output" / "rm_notes",
            self.build_root / "output" / "ai_agent_memory",
            self.build_root / "AI_support" / "ai_generated",
            self.build_root / "AI_support" / "rm_notes",
            self.build_root / "AI_support" / "memory" / "chroma_db",
        ]
        destination_root: Dict[str, Path] = {
            "ai_generated": workspace_root / AI_SUPPORT_ROOT / "ai_generated",
            "rm_notes": workspace_root / AI_SUPPORT_ROOT / "rm_notes",
            "ai_agent_memory": workspace_root / AI_SUPPORT_ROOT / "memory" / "chroma_db",
        }

        for source in legacy_roots:
            if not source.exists() or not source.is_dir():
                continue
            target = destination_root.get(source.name)
            if not target:
                continue
            target.mkdir(parents=True, exist_ok=True)
            self._move_directory_contents(source, target)
            try:
                if source.exists() and not any(source.iterdir()):
                    source.rmdir()
            except OSError:
                pass

        self._auto_compact_memory()

    def _move_directory_contents(self, source: Path, target: Path) -> None:
        """Move files from one directory tree into another without overwriting existing files."""
        for item in source.iterdir():
            destination = target / item.name
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                self._move_directory_contents(item, destination)
                try:
                    if not any(item.iterdir()):
                        item.rmdir()
                except OSError:
                    pass
                continue

            if destination.exists():
                stem = destination.stem
                suffix = destination.suffix
                destination = destination.with_name(f"{stem}_legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}{suffix}")
            shutil.move(str(item), str(destination))

    def _auto_compact_memory(self) -> None:
        """Auto-compact memory if size thresholds are exceeded."""
        try:
            compact_report = self.memory.auto_compact_if_needed()
            if compact_report:
                logger.info(
                    "AgentMemory: Auto-compacted (deduped=%s trimmed=%s)",
                    compact_report.get("deduped", {}),
                    compact_report.get("trimmed", {}),
                )
        except Exception:
            pass  # Non-critical
