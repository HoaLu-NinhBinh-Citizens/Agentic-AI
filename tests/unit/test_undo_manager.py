"""Tests for UndoManager - 6.2.UTXX.

Tests multi-file undo/redo functionality with checkpoint management.
"""

import pytest
from pathlib import Path
from datetime import datetime

from src.infrastructure.refactoring.undo_manager import (
    UndoManager,
    Change,
    UndoCheckpoint,
)


class TestChange:
    """Test Change dataclass."""
    
    def test_create_change(self):
        """Test creating a change object."""
        change = Change(
            path=Path("test.py"),
            before="old content",
            after="new content",
            timestamp=datetime.now(),
            description="Update test.py",
            applied_by="refactor",
        )
        
        assert change.path == Path("test.py")
        assert change.before == "old content"
        assert change.after == "new content"
        assert change.description == "Update test.py"
        assert change.applied_by == "refactor"


class TestUndoCheckpoint:
    """Test UndoCheckpoint dataclass."""
    
    def test_create_checkpoint(self):
        """Test creating a checkpoint."""
        changes = [
            Change(
                path=Path("file1.py"),
                before="a",
                after="b",
                timestamp=datetime.now(),
                description="change1",
                applied_by="test",
            ),
        ]
        
        checkpoint = UndoCheckpoint(
            id="cp_0001",
            timestamp=datetime.now(),
            changes=changes,
            description="Test checkpoint",
        )
        
        assert checkpoint.id == "cp_0001"
        assert len(checkpoint.changes) == 1
        assert checkpoint.description == "Test checkpoint"


class TestUndoManager:
    """Test UndoManager class."""
    
    @pytest.fixture
    def manager(self, tmp_path):
        """Create an UndoManager instance."""
        return UndoManager(project_root=tmp_path, max_checkpoints=10)
    
    def test_init(self, tmp_path):
        """Test UndoManager initialization."""
        manager = UndoManager(project_root=tmp_path)
        
        assert manager.project_root == tmp_path
        assert manager.max_checkpoints == 50
        assert manager.checkpoints == []
        assert manager.current_index == -1
    
    def test_init_with_max_checkpoints(self, tmp_path):
        """Test initialization with custom max_checkpoints."""
        manager = UndoManager(project_root=tmp_path, max_checkpoints=5)
        
        assert manager.max_checkpoints == 5
    
    def test_checkpoint_creation(self, manager, tmp_path):
        """Test creating a checkpoint."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")
        
        change = Change(
            path=Path("test.txt"),
            before="original content",
            after="modified content",
            timestamp=datetime.now(),
            description="Modify test.txt",
            applied_by="test",
        )
        
        cp_id = manager.checkpoint([change], "Test checkpoint")
        
        assert cp_id is not None
        assert cp_id.startswith("cp_")
        assert len(manager.checkpoints) == 1
        assert manager.current_index == 0
    
    def test_checkpoint_multiple_changes(self, manager, tmp_path):
        """Test checkpoint with multiple file changes."""
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("original1")
        file2.write_text("original2")
        
        changes = [
            Change(
                path=Path("file1.py"),
                before="original1",
                after="modified1",
                timestamp=datetime.now(),
                description="change1",
                applied_by="test",
            ),
            Change(
                path=Path("file2.py"),
                before="original2",
                after="modified2",
                timestamp=datetime.now(),
                description="change2",
                applied_by="test",
            ),
        ]
        
        cp_id = manager.checkpoint(changes, "Multiple changes")
        
        assert cp_id is not None
        checkpoint = manager.checkpoints[0]
        assert len(checkpoint.changes) == 2
    
    def test_undo_restores_original(self, manager, tmp_path):
        """Test that undo restores original file content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="Test change",
            applied_by="test",
        )
        
        manager.checkpoint([change], "Test")
        test_file.write_text("modified")
        
        result = manager.undo()
        
        assert result is not None
        assert test_file.read_text() == "original"
        assert manager.current_index == -1
    
    def test_undo_returns_checkpoint(self, manager, tmp_path):
        """Test that undo returns the undone checkpoint."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="Test change",
            applied_by="test",
        )
        
        manager.checkpoint([change], "Test checkpoint")
        
        # After checkpoint, current_index is 0
        # After undo, current_index becomes -1
        result = manager.undo()
        
        # Undo should return the checkpoint
        assert result is not None
        assert result.description == "Test checkpoint"
        # File should be restored
        assert test_file.read_text() == "original"
    
    def test_redo_reapplies_changes(self, manager, tmp_path):
        """Test that redo reapplies the changes."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="Test change",
            applied_by="test",
        )
        
        manager.checkpoint([change], "Test")
        manager.undo()
        result = manager.redo()
        
        assert result is not None
        assert test_file.read_text() == "modified"
        assert manager.current_index == 0
    
    def test_undo_nothing_to_undo(self, manager):
        """Test undo when nothing to undo."""
        result = manager.undo()
        
        assert result is None
        assert manager.current_index == -1
    
    def test_redo_nothing_to_redo(self, manager):
        """Test redo when nothing to redo."""
        result = manager.redo()
        
        assert result is None
    
    def test_can_undo(self, manager, tmp_path):
        """Test can_undo method."""
        assert manager.can_undo() is False
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="test",
            applied_by="test",
        )
        manager.checkpoint([change], "test")
        
        assert manager.can_undo() is True
    
    def test_can_redo(self, manager, tmp_path):
        """Test can_redo method."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="test",
            applied_by="test",
        )
        manager.checkpoint([change], "test")
        
        assert manager.can_redo() is False
        
        manager.undo()
        
        assert manager.can_redo() is True
    
    def test_get_history(self, manager, tmp_path):
        """Test getting checkpoint history."""
        for i in range(3):
            test_file = tmp_path / f"test{i}.txt"
            test_file.write_text(f"original{i}")
            
            change = Change(
                path=Path(f"test{i}.txt"),
                before=f"original{i}",
                after=f"modified{i}",
                timestamp=datetime.now(),
                description=f"Change {i}",
                applied_by="test",
            )
            manager.checkpoint([change], f"Checkpoint {i}")
        
        history = manager.get_history()
        
        assert len(history) == 3
        assert history[0]["description"] == "Checkpoint 0"
        assert history[2]["file_count"] == 1
    
    def test_get_checkpoint(self, manager, tmp_path):
        """Test getting a specific checkpoint."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="test",
            applied_by="test",
        )
        cp_id = manager.checkpoint([change], "Test")
        
        checkpoint = manager.get_checkpoint(cp_id)
        
        assert checkpoint is not None
        assert checkpoint.id == cp_id
        assert checkpoint.description == "Test"
    
    def test_get_nonexistent_checkpoint(self, manager):
        """Test getting a nonexistent checkpoint."""
        result = manager.get_checkpoint("nonexistent_id")
        
        assert result is None
    
    def test_clear_history(self, manager, tmp_path):
        """Test clearing all checkpoint history."""
        for i in range(3):
            test_file = tmp_path / f"test{i}.txt"
            test_file.write_text(f"original{i}")
            
            change = Change(
                path=Path(f"test{i}.txt"),
                before=f"original{i}",
                after=f"modified{i}",
                timestamp=datetime.now(),
                description=f"Change {i}",
                applied_by="test",
            )
            manager.checkpoint([change], f"Checkpoint {i}")
        
        manager.clear_history()
        
        assert manager.checkpoints == []
        assert manager.current_index == -1
    
    def test_checkpoint_truncates_future(self, manager, tmp_path):
        """Test that new checkpoint truncates future history."""
        for i in range(3):
            test_file = tmp_path / f"test{i}.txt"
            test_file.write_text(f"original{i}")
            
            change = Change(
                path=Path(f"test{i}.txt"),
                before=f"original{i}",
                after=f"modified{i}",
                timestamp=datetime.now(),
                description=f"Change {i}",
                applied_by="test",
            )
            manager.checkpoint([change], f"Checkpoint {i}")
        
        manager.undo()
        manager.undo()
        
        test_file = tmp_path / "new_test.txt"
        test_file.write_text("new original")
        
        change = Change(
            path=Path("new_test.txt"),
            before="new original",
            after="new modified",
            timestamp=datetime.now(),
            description="New change",
            applied_by="test",
        )
        manager.checkpoint([change], "New checkpoint")
        
        assert len(manager.checkpoints) == 2
        assert manager.checkpoints[0].description == "Checkpoint 0"
        assert manager.checkpoints[1].description == "New checkpoint"
    
    def test_max_checkpoints_limit(self, manager, tmp_path):
        """Test that checkpoints are limited by max_checkpoints."""
        assert manager.max_checkpoints == 10
        
        for i in range(15):
            test_file = tmp_path / f"test{i}.txt"
            test_file.write_text(f"original{i}")
            
            change = Change(
                path=Path(f"test{i}.txt"),
                before=f"original{i}",
                after=f"modified{i}",
                timestamp=datetime.now(),
                description=f"Change {i}",
                applied_by="test",
            )
            manager.checkpoint([change], f"Checkpoint {i}")
        
        assert len(manager.checkpoints) <= manager.max_checkpoints


class TestUndoManagerEdgeCases:
    """Test edge cases in UndoManager."""
    
    def test_undo_with_new_file(self, tmp_path):
        """Test undo when file was created (not modified)."""
        manager = UndoManager(project_root=tmp_path)
        
        new_file = tmp_path / "new_file.py"
        new_file.write_text("content")
        
        change = Change(
            path=Path("new_file.py"),
            before="",
            after="content",
            timestamp=datetime.now(),
            description="Create new file",
            applied_by="test",
        )
        
        manager.checkpoint([change], "Create file")
        result = manager.undo()
        
        assert result is not None
        assert not new_file.exists()
    
    def test_redo_with_deleted_file(self, tmp_path):
        """Test redo when file was deleted."""
        manager = UndoManager(project_root=tmp_path)
        
        file_to_delete = tmp_path / "to_delete.txt"
        file_to_delete.write_text("content to delete")
        
        change = Change(
            path=Path("to_delete.txt"),
            before="content to delete",
            after="",
            timestamp=datetime.now(),
            description="Delete file",
            applied_by="test",
        )
        
        manager.checkpoint([change], "Delete file")
        manager.undo()
        result = manager.redo()
        
        assert result is not None
        assert not file_to_delete.exists()
    
    def test_history_with_nonexistent_files(self, tmp_path):
        """Test history when files have been deleted."""
        manager = UndoManager(project_root=tmp_path)
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        change = Change(
            path=Path("test.txt"),
            before="original",
            after="modified",
            timestamp=datetime.now(),
            description="Test change",
            applied_by="test",
        )
        manager.checkpoint([change], "Test")
        
        test_file.unlink()
        
        history = manager.get_history()
        
        assert len(history) == 1
        assert history[0]["file_count"] == 1
