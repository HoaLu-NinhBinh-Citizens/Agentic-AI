"""Multi-file undo/redo manager for AI_SUPPORT.
Tracks changes across the entire project with checkpoints.
"""
from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Change:
    """A single file change within a checkpoint."""
    path: Path
    before: str
    after: str
    timestamp: datetime
    description: str
    applied_by: str  # command name or operation type


@dataclass
class UndoCheckpoint:
    """A checkpoint containing multiple file changes."""
    id: str
    timestamp: datetime
    changes: list[Change]
    description: str


class UndoManager:
    """Manages undo/redo across multiple files.
    
    Features:
    - Checkpoint-based change tracking
    - Multi-file undo/redo
    - Automatic backup creation
    - Checkpoint history with configurable limit
    - Serializable checkpoint storage
    
    Usage:
        manager = UndoManager(project_root=Path("."))
        
        # Record changes
        changes = [
            Change(path=Path("file1.py"), before="old", after="new", ...),
            Change(path=Path("file2.py"), before="old", after="new", ...),
        ]
        manager.checkpoint(changes, "Refactor user authentication")
        
        # Undo last checkpoint
        undone = manager.undo()
        
        # Redo
        redone = manager.redo()
    """
    
    def __init__(self, project_root: Path | str, max_checkpoints: int = 50):
        self.project_root = Path(project_root)
        self.max_checkpoints = max_checkpoints
        self.checkpoints: list[UndoCheckpoint] = []
        self.current_index: int = -1
        self._backup_base = self.project_root / ".ai_support" / "backups"
        self._backup_base.mkdir(parents=True, exist_ok=True)
        self._checkpoint_file = self.project_root / ".ai_support" / "undo_history.json"
        self._load_history()
    
    def _load_history(self) -> None:
        """Load checkpoint history from file."""
        if not self._checkpoint_file.exists():
            return
        
        try:
            data = json.loads(self._checkpoint_file.read_text(encoding='utf-8'))
            self.checkpoints = []
            
            for cp_data in data.get("checkpoints", []):
                changes = []
                for ch_data in cp_data.get("changes", []):
                    changes.append(Change(
                        path=Path(ch_data["path"]),
                        before=ch_data["before"],
                        after=ch_data["after"],
                        timestamp=datetime.fromisoformat(ch_data["timestamp"]),
                        description=ch_data["description"],
                        applied_by=ch_data["applied_by"],
                    ))
                
                self.checkpoints.append(UndoCheckpoint(
                    id=cp_data["id"],
                    timestamp=datetime.fromisoformat(cp_data["timestamp"]),
                    changes=changes,
                    description=cp_data["description"],
                ))
            
            self.current_index = data.get("current_index", -1)
            logger.info("Loaded %d checkpoints from history", len(self.checkpoints))
        except Exception as e:
            logger.warning("Failed to load checkpoint history: %s", e)
    
    def _save_history(self) -> None:
        """Save checkpoint history to file."""
        try:
            data = {
                "checkpoints": [
                    {
                        "id": cp.id,
                        "timestamp": cp.timestamp.isoformat(),
                        "description": cp.description,
                        "changes": [
                            {
                                "path": str(ch.path),
                                "before": ch.before,
                                "after": ch.after,
                                "timestamp": ch.timestamp.isoformat(),
                                "description": ch.description,
                                "applied_by": ch.applied_by,
                            }
                            for ch in cp.changes
                        ],
                    }
                    for cp in self.checkpoints
                ],
                "current_index": self.current_index,
            }
            
            self._checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
            self._checkpoint_file.write_text(json.dumps(data, indent=2), encoding='utf-8')
        except Exception as e:
            logger.error("Failed to save checkpoint history: %s", e)
    
    def checkpoint(
        self,
        changes: list[Change],
        description: str,
    ) -> str:
        """Create a new checkpoint with the given changes.
        
        Args:
            changes: List of Change objects
            description: Description of the checkpoint
            
        Returns:
            Checkpoint ID
        """
        checkpoint_id = f"cp_{len(self.checkpoints):04d}_{datetime.now().strftime('%H%M%S')}"
        
        # Backup files before applying
        for change in changes:
            backup_dir = self._backup_base / checkpoint_id
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            backup_path = backup_dir / change.path.name
            try:
                if change.path.exists():
                    shutil.copy2(change.path, backup_path)
                else:
                    # File doesn't exist, create empty marker
                    backup_path.write_text("", encoding='utf-8')
            except Exception as e:
                logger.warning("Backup failed for %s: %s", change.path, e)
        
        # Add timestamps to changes
        now = datetime.now()
        for change in changes:
            change.timestamp = now
        
        checkpoint = UndoCheckpoint(
            id=checkpoint_id,
            timestamp=now,
            changes=changes,
            description=description,
        )
        
        # Truncate future if we're not at the end
        if self.current_index < len(self.checkpoints) - 1:
            # Clean up discarded checkpoints
            for old_cp in self.checkpoints[self.current_index + 1:]:
                self._cleanup_backup(old_cp.id)
            
            self.checkpoints = self.checkpoints[:self.current_index + 1]
        
        self.checkpoints.append(checkpoint)
        self.current_index = len(self.checkpoints) - 1
        
        # Limit checkpoints
        while len(self.checkpoints) > self.max_checkpoints:
            oldest = self.checkpoints.pop(0)
            self._cleanup_backup(oldest.id)
            self.current_index -= 1
        
        self._save_history()
        logger.info("Created checkpoint %s: %s", checkpoint_id, description)
        
        return checkpoint_id
    
    def undo(self) -> Optional[UndoCheckpoint]:
        """Undo the last checkpoint. Returns the undone checkpoint.
        
        Returns:
            The undone checkpoint, or None if nothing to undo
        """
        if self.current_index < 0:
            logger.info("Nothing to undo")
            return None
        
        checkpoint = self.checkpoints[self.current_index]
        
        # Restore files from checkpoint data (not backup, as content is stored)
        for change in checkpoint.changes:
            path = self.project_root / change.path
            try:
                if change.before:
                    path.write_text(change.before, encoding='utf-8')
                else:
                    # File was created, remove it
                    if path.exists():
                        path.unlink()
            except Exception as e:
                logger.error("Undo failed for %s: %s", path, e)
        
        self.current_index -= 1
        self._save_history()
        
        logger.info("Undone checkpoint %s: %s", checkpoint.id, checkpoint.description)
        return checkpoint
    
    def redo(self) -> Optional[UndoCheckpoint]:
        """Redo the next checkpoint. Returns the redone checkpoint.
        
        Returns:
            The redone checkpoint, or None if nothing to redo
        """
        if self.current_index >= len(self.checkpoints) - 1:
            logger.info("Nothing to redo")
            return None
        
        self.current_index += 1
        checkpoint = self.checkpoints[self.current_index]
        
        # Re-apply files from checkpoint data
        for change in checkpoint.changes:
            path = self.project_root / change.path
            try:
                if change.after:
                    path.write_text(change.after, encoding='utf-8')
                else:
                    # File was deleted, remove it
                    if path.exists():
                        path.unlink()
            except Exception as e:
                logger.error("Redo failed for %s: %s", path, e)
        
        self._save_history()
        
        logger.info("Redone checkpoint %s: %s", checkpoint.id, checkpoint.description)
        return checkpoint
    
    def get_history(self) -> list[dict]:
        """Get checkpoint history for display.
        
        Returns:
            List of checkpoint summaries
        """
        return [
            {
                "id": cp.id,
                "timestamp": cp.timestamp.isoformat(),
                "description": cp.description,
                "file_count": len(cp.changes),
                "is_current": i == self.current_index,
                "can_undo": i == self.current_index and self.current_index >= 0,
                "can_redo": i == self.current_index + 1 and self.current_index < len(self.checkpoints) - 1,
            }
            for i, cp in enumerate(self.checkpoints)
        ]
    
    def get_checkpoint(self, checkpoint_id: str) -> Optional[UndoCheckpoint]:
        """Get a specific checkpoint by ID.
        
        Args:
            checkpoint_id: The checkpoint ID
            
        Returns:
            The checkpoint, or None if not found
        """
        for cp in self.checkpoints:
            if cp.id == checkpoint_id:
                return cp
        return None
    
    def _cleanup_backup(self, checkpoint_id: str) -> None:
        """Remove backup directory for a checkpoint.
        
        Args:
            checkpoint_id: The checkpoint ID
        """
        backup_dir = self._backup_base / checkpoint_id
        if backup_dir.exists():
            try:
                shutil.rmtree(backup_dir)
            except Exception as e:
                logger.warning("Cleanup failed for %s: %s", checkpoint_id, e)
    
    def can_undo(self) -> bool:
        """Check if undo is available."""
        return self.current_index >= 0
    
    def can_redo(self) -> bool:
        """Check if redo is available."""
        return self.current_index < len(self.checkpoints) - 1
    
    def clear_history(self) -> None:
        """Clear all checkpoint history."""
        # Clean up all backups
        for cp in self.checkpoints:
            self._cleanup_backup(cp.id)
        
        self.checkpoints = []
        self.current_index = -1
        self._save_history()
        
        logger.info("Cleared all checkpoint history")
