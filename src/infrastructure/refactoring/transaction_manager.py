"""Edit Transaction Manager — Atomic multi-file edits with workspace snapshot and rollback.

Provides:
- Workspace snapshot before edit
- AST-safe patching
- Multi-file transaction coordinator  
- Compile verification
- Rollback on failure
"""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class EditOperation:
    """A single edit operation within a transaction."""
    file_path: Path
    old_content: str
    new_content: str
    operation: str = "replace"


@dataclass
class TransactionState:
    """State of an edit transaction."""
    id: str
    timestamp: float
    operations: list[EditOperation]
    status: str = "pending"  # pending, applied, verified, rolled_back, failed
    verification_result: Optional[dict] = None
    error: Optional[str] = None


class WorkspaceSnapshot:
    """Snapshot of workspace files before edit."""
    
    def __init__(self, workspace_root: Path, snapshot_id: str):
        self.workspace_root = workspace_root
        self.snapshot_id = snapshot_id
        self.snapshot_dir = workspace_root / ".ai_support" / "snapshots" / snapshot_id
        self._files: dict[str, str] = {}
    
    def capture(self, files: list[Path]) -> int:
        """Capture files into snapshot."""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        
        for file_path in files:
            try:
                if file_path.exists():
                    rel_path = file_path.relative_to(self.workspace_root)
                    snapshot_file = self.snapshot_dir / rel_path
                    snapshot_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, snapshot_file)
                    self._files[str(rel_path)] = file_path.read_text(encoding='utf-8')
                    count += 1
            except Exception as e:
                logger.warning("Snapshot failed for %s: %s", file_path, e)
        
        return count
    
    def restore(self, files: list[Path]) -> int:
        """Restore files from snapshot."""
        restored = 0
        
        for file_path in files:
            try:
                rel_path = file_path.relative_to(self.workspace_root)
                snapshot_file = self.snapshot_dir / rel_path
                
                if snapshot_file.exists():
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(snapshot_file, file_path)
                    restored += 1
            except Exception as e:
                logger.warning("Restore failed for %s: %s", file_path, e)
        
        return restored
    
    def cleanup(self) -> None:
        """Remove snapshot directory."""
        if self.snapshot_dir.exists():
            shutil.rmtree(self.snapshot_dir, ignore_errors=True)


class EditTransactionManager:
    """Manages atomic multi-file edit transactions with rollback capability.
    
    Usage:
        manager = EditTransactionManager(workspace_root)
        
        # Start transaction
        tx_id = manager.begin(files_to_edit)
        
        # Apply edits
        manager.apply(tx_id, EditOperation(file_path, old, new))
        
        # Verify and commit
        success = await manager.verify_and_commit(tx_id)
        
        # Or rollback
        manager.rollback(tx_id)
    """
    
    def __init__(self, workspace_root: Path | str, max_snapshots: int = 100):
        self.workspace_root = Path(workspace_root)
        self._transactions: dict[str, TransactionState] = {}
        self._snapshots: dict[str, WorkspaceSnapshot] = {}
        self._max_snapshots = max_snapshots
    
    def begin(self, files: list[Path]) -> str:
        """Begin a transaction with workspace snapshot."""
        tx_id = f"tx_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        
        # Create snapshot
        snapshot = WorkspaceSnapshot(self.workspace_root, tx_id)
        snapshot.capture(files)
        self._snapshots[tx_id] = snapshot
        
        # Track transaction
        self._transactions[tx_id] = TransactionState(
            id=tx_id,
            timestamp=datetime.now().timestamp(),
            operations=[],
            status="pending",
        )
        
        logger.info("Transaction started: %s", tx_id)
        return tx_id
    
    def apply(self, tx_id: str, operation: EditOperation) -> bool:
        """Add operation to transaction."""
        tx = self._transactions.get(tx_id)
        if not tx:
            return False
        
        if tx.status != "pending":
            return False
        
        tx.operations.append(operation)
        
        try:
            operation.file_path.parent.mkdir(parents=True, exist_ok=True)
            if operation.operation == "replace":
                operation.file_path.write_text(operation.new_content, encoding='utf-8')
            tx.status = "applied"
            return True
        except Exception as e:
            logger.error("Apply failed: %s", e)
            tx.status = "failed"
            tx.error = str(e)
            return False
    
    async def verify_and_commit(
        self,
        tx_id: str,
        verify_compile: bool = False,
    ) -> bool:
        """Verify edits and commit transaction."""
        tx = self._transactions.get(tx_id)
        if not tx:
            return False
        
        if tx.status != "applied":
            return False
        
        verification: dict = {}
        
        if verify_compile:
            verification = await self._verify_compile(tx)
        
        if verification.get("has_errors", False):
            tx.status = "failed"
            tx.verification_result = verification
            tx.error = "Compile verification failed"
            self.rollback(tx_id)
            return False
        
        tx.status = "verified"
        tx.verification_result = verification
        
        self._cleanup_snapshot(tx_id)
        return True
    
    async def _verify_compile(self, tx: TransactionState) -> dict:
        """Verify files compile successfully."""
        errors: list[str] = []
        files_checked = 0
        
        for op in tx.operations:
            if op.file_path.suffix == ".py":
                result = await self._verify_python(op.file_path)
                if not result.get("valid", False):
                    errors.append(f"{op.file_path}: {result.get('error', 'syntax error')}")
                files_checked += 1
            elif op.file_path.suffix in {".c", ".cpp", ".h"}:
                result = await self._verify_c(op.file_path)
                if not result.get("valid", False):
                    errors.append(f"{op.file_path}: {result.get('error', 'compile error')}")
                files_checked += 1
        
        return {
            "files_checked": files_checked,
            "has_errors": len(errors) > 0,
            "errors": errors,
        }
    
    async def _verify_python(self, file_path: Path) -> dict:
        """Verify Python file syntax."""
        try:
            import ast
            content = file_path.read_text(encoding='utf-8')
            ast.parse(content)
            return {"valid": True}
        except SyntaxError as e:
            return {"valid": False, "error": str(e)}
    
    async def _verify_c(self, file_path: Path) -> dict:
        """Verify C file compiles (dry-run)."""
        try:
            result = subprocess.run(
                ["gcc", "-fsyntax-only", "-x", "c", str(file_path)],
                capture_output=True,
                timeout=5.0,
            )
            return {"valid": result.returncode == 0}
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def rollback(self, tx_id: str) -> int:
        """Rollback transaction."""
        tx = self._transactions.get(tx_id)
        if not tx:
            return 0
        
        snapshot = self._snapshots.get(tx_id)
        if snapshot:
            restored = snapshot.restore([op.file_path for op in tx.operations])
            tx.status = "rolled_back"
            self._cleanup_snapshot(tx_id)
            return restored
        
        return 0
    
    def _cleanup_snapshot(self, tx_id: str) -> None:
        """Remove old snapshot."""
        snapshot = self._snapshots.pop(tx_id, None)
        if snapshot:
            snapshot.cleanup()
        
        # Clean old snapshots
        if len(self._snapshots) > self._max_snapshots:
            oldest = min(self._snapshots.keys())
            self._snapshots.pop(oldest, None)
            (self.workspace_root / ".ai_support" / "snapshots" / oldest).mkdir(
                parents=True, exist_ok=True
            )
            shutil.rmtree(
                self.workspace_root / ".ai_support" / "snapshots" / oldest,
                ignore_errors=True,
            )
    
    def get_status(self, tx_id: str) -> Optional[TransactionState]:
        """Get transaction status."""
        return self._transactions.get(tx_id)
    
    def get_active_transactions(self) -> list[TransactionState]:
        """Get all active (non-committed) transactions."""
        return [
            tx for tx in self._transactions.values()
            if tx.status in ("pending", "applied", "failed")
        ]


class ASTSafePatcher:
    """Applies AST-safe patches to code files."""
    
    @staticmethod
    def apply_python_patch(content: str, old_text: str, new_text: str) -> str:
        """Apply patch with AST validation."""
        try:
            old_lines = content.split('\n')
            new_lines = new_text.split('\n')
            
            # Find old_text in content
            old_idx = content.find(old_text)
            if old_idx == -1:
                return content
            
            # Verify both are valid Python
            import ast
            ast.parse(content)
            if new_text.strip():
                ast.parse(new_text)
            
            # Apply replacement
            result = content[:old_idx] + new_text + content[old_idx + len(old_text):]
            return result
        except Exception as e:
            logger.warning("AST patch validation failed: %s", e)
            return content
    
    @staticmethod
    def apply_c_patch(content: str, old_text: str, new_text: str) -> str:
        """Apply C patch preserving formatting."""
        old_idx = content.find(old_text)
        if old_idx == -1:
            return content
        return content[:old_idx] + new_text + content[old_idx + len(old_text):]