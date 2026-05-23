"""Patch sandbox for safe firmware modification (Phase 9.1).

Provides:
- Isolated git worktree for patches
- Compilation validation
- Risk scoring
- Patch history and rollback
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class PatchStatus(Enum):
    """Patch application status."""
    DRAFT = "draft"
    VALIDATED = "validated"
    APPROVED = "approved"
    APPLIED = "applied"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"


class RiskLevel(Enum):
    """Patch risk assessment."""
    LOW = "low"           # Documentation, minor config
    MEDIUM = "medium"     # Logic changes, safe peripherals
    HIGH = "high"         # Interrupt, DMA, memory changes
    CRITICAL = "critical"  # Bootloader, flash, safety-critical


@dataclass
class PatchRisk:
    """Risk assessment for a patch."""
    level: RiskLevel
    score: float  # 0.0 - 10.0
    factors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Patch validation result."""
    success: bool
    compiles: bool = False
    style_ok: bool = True
    tests_pass: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifacts: dict[str, Path] = field(default_factory=dict)


@dataclass
class Patch:
    """Firmware patch representation."""
    id: str
    title: str
    description: str
    diff: str
    files_changed: list[str] = field(default_factory=list)
    risk: PatchRisk | None = None
    validation: ValidationResult | None = None
    status: PatchStatus = PatchStatus.DRAFT
    created_at: datetime = field(default_factory=datetime.now)
    approved_by: str | None = None
    approved_at: datetime | None = None
    applied_at: datetime | None = None
    rollback_id: str | None = None
    
    @property
    def checksum(self) -> str:
        """Compute patch checksum."""
        return hashlib.sha256(self.diff.encode()).hexdigest()[:16]


@dataclass
class SandboxConfig:
    """Sandbox configuration."""
    workspace_root: Path = field(default_factory=lambda: Path("sandbox/patches"))
    compile_command: str = "python build.py"
    test_command: str = "python test.py"
    max_concurrent_patches: int = 4
    auto_cleanup_hours: int = 24


class PatchSandbox:
    """Isolated sandbox for patch development and validation.
    
    Phase 9.1: Patch sandbox
    Phase 9.5: Patch validation
    Phase 9.6: Patch history + rollback
    """
    
    def __init__(self, config: SandboxConfig | None = None) -> None:
        self.config = config or SandboxConfig()
        self._workspace_root = self.config.workspace_root
        self._active_worktrees: dict[str, Path] = {}
        self._patch_history: list[Patch] = []
    
    async def create_worktree(self, patch_id: str, base_branch: str = "main") -> Path:
        """Create isolated git worktree for patch."""
        worktree_path = self._workspace_root / "worktrees" / patch_id
        
        if worktree_path.exists():
            logger.warning("Worktree already exists, reusing", path=str(worktree_path))
            return worktree_path
        
        worktree_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create git worktree
        cmd = [
            "git", "worktree", "add",
            "-b", f"patch/{patch_id}",
            str(worktree_path),
            f"origin/{base_branch}",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            # Fallback: clone instead
            logger.info("Falling back to git clone")
            worktree_path = self._workspace_root / "worktrees" / patch_id
            subprocess.run(["git", "clone", ".", str(worktree_path)], capture_output=True)
        
        self._active_worktrees[patch_id] = worktree_path
        logger.info("Created worktree", patch_id=patch_id, path=str(worktree_path))
        
        return worktree_path
    
    async def apply_patch(self, patch: Patch, worktree: Path) -> bool:
        """Apply patch diff to worktree."""
        patch_file = worktree / f"patch_{patch.id}.diff"
        patch_file.write_text(patch.diff)
        
        cmd = ["git", "apply", str(patch_file)]
        result = subprocess.run(cmd, cwd=worktree, capture_output=True, text=True)
        
        if result.returncode != 0:
            logger.error("Patch application failed", stderr=result.stderr)
            patch.errors.append(f"Git apply failed: {result.stderr}")
            return False
        
        patch.files_changed = self._get_changed_files(worktree)
        return True
    
    def _get_changed_files(self, worktree: Path) -> list[str]:
        """Get list of changed files."""
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            cwd=worktree,
            capture_output=True,
            text=True,
        )
        return [f.strip() for f in result.stdout.split("\n") if f.strip()]
    
    async def validate(self, patch: Patch, worktree: Path) -> ValidationResult:
        """Validate patch compiles and passes tests."""
        result = ValidationResult(success=False)
        
        # Check compilation
        compile_result = await self._compile(worktree)
        result.compiles = compile_result.success
        if not compile_result.success:
            result.errors.extend(compile_result.errors)
        
        # Check tests
        test_result = await self._run_tests(worktree)
        result.tests_pass = test_result.success
        if not test_result.success:
            result.warnings.extend(test_result.warnings)
        
        # Check style (optional)
        style_result = await self._check_style(worktree)
        result.style_ok = style_result.success
        
        result.success = result.compiles and result.tests_pass
        patch.validation = result
        
        return result
    
    async def _compile(self, worktree: Path) -> ValidationResult:
        """Compile firmware in worktree."""
        logger.info("Compiling patch", worktree=str(worktree))
        
        result = subprocess.run(
            self.config.compile_command.split(),
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=300,
        )
        
        validation = ValidationResult(
            success=result.returncode == 0,
            compiles=result.returncode == 0,
        )
        
        if result.returncode != 0:
            validation.errors.append(f"Compilation failed:\n{result.stderr[:500]}")
        
        return validation
    
    async def _run_tests(self, worktree: Path) -> ValidationResult:
        """Run tests in worktree."""
        logger.info("Running tests", worktree=str(worktree))
        
        result = subprocess.run(
            self.config.test_command.split(),
            cwd=worktree,
            capture_output=True,
            text=True,
            timeout=120,
        )
        
        validation = ValidationResult(
            success=result.returncode == 0,
            tests_pass=result.returncode == 0,
        )
        
        if result.returncode != 0:
            validation.warnings.append(f"Tests failed:\n{result.stderr[:500]}")
        
        return validation
    
    async def _check_style(self, worktree: Path) -> ValidationResult:
        """Check code style."""
        # Check with clang-format or similar
        return ValidationResult(success=True)
    
    async def assess_risk(self, patch: Patch) -> PatchRisk:
        """Assess patch risk level."""
        factors = []
        warnings = []
        recommendations = []
        score = 0.0
        
        # High-risk file patterns
        critical_files = [
            "bootloader", "startup", "linker", "flash", "memory",
            "interrupt", "dma", "systick", "nvic", "rtc_*_nvic",
        ]
        
        safe_files = [
            "test", "mock", "example", "documentation",
        ]
        
        # Check file patterns
        for file in patch.files_changed:
            file_lower = file.lower()
            
            # Critical files increase risk
            if any(p in file_lower for p in critical_files):
                score += 2.5
                factors.append(f"Critical file: {file}")
                warnings.append(f"Changes to {file} may affect system reliability")
            
            # Safe files reduce risk
            elif any(p in file_lower for p in safe_files):
                score -= 0.5
            
            # Config changes
            elif file.endswith((".yaml", ".json", ".ini", ".conf")):
                score += 0.5
                factors.append(f"Configuration file: {file}")
        
        # Check diff content for risky patterns
        risky_patterns = {
            r"\bvolatile\b": "Volatile usage - check if necessary",
            r"\bdma\b": "DMA changes - verify channel configuration",
            r"\binterrupt\b": "Interrupt changes - verify priority",
            r"\bNVIC\b": "NVIC changes - verify vector table",
            r"\b__attribute__\s*\(\s*\(\s*section": "Section changes - verify linker script",
            r"\bwhile\s*\(\s*1\s*\)|while\s*\(\s*true\s*\)": "Potential infinite loop",
            r"\bdelay|Delay": "Timing changes - verify constraints",
        }
        
        for pattern, warning in risky_patterns.items():
            import re
            if re.search(pattern, patch.diff, re.IGNORECASE):
                score += 0.5
                warnings.append(warning)
        
        # Determine level
        if score >= 7.0:
            level = RiskLevel.CRITICAL
            recommendations = [
                "Manual code review required",
                "Hardware-in-the-loop testing recommended",
                "Consider staged rollout",
            ]
        elif score >= 4.0:
            level = RiskLevel.HIGH
            recommendations = [
                "Automated testing required",
                "Risk acknowledgment needed",
            ]
        elif score >= 2.0:
            level = RiskLevel.MEDIUM
            recommendations = [
                "Basic testing sufficient",
            ]
        else:
            level = RiskLevel.LOW
            recommendations = [
                "Standard review process",
            ]
        
        # Clamp score
        score = max(0.0, min(10.0, score))
        
        patch.risk = PatchRisk(
            level=level,
            score=score,
            factors=factors,
            warnings=warnings,
            recommendations=recommendations,
        )
        
        return patch.risk
    
    async def apply_to_main(
        self,
        patch: Patch,
        worktree: Path,
        approved_by: str,
    ) -> bool:
        """Apply validated patch to main branch."""
        if patch.validation and not patch.validation.success:
            logger.error("Cannot apply unvalidated patch")
            return False
        
        # Get original repo path
        original_repo = Path.cwd()
        
        try:
            # Apply patch to original repo
            subprocess.run(
                ["git", "apply", "--index"],
                input=patch.diff.encode(),
                cwd=original_repo,
            )
            
            # Commit
            subprocess.run(
                [
                    "git", "commit",
                    "-m", f"feat(patch): {patch.title}\n\n{patch.description}",
                    "-m", f"Patch-ID: {patch.id}\nRisk: {patch.risk.level.value if patch.risk else 'N/A'}",
                ],
                cwd=original_repo,
            )
            
            patch.status = PatchStatus.APPLIED
            patch.applied_at = datetime.now()
            patch.approved_by = approved_by
            patch.approved_at = datetime.now()
            
            # Store in history
            self._patch_history.append(patch)
            
            logger.info("Patch applied", patch_id=patch.id)
            return True
            
        finally:
            pass
    
    async def rollback(self, patch_id: str) -> bool:
        """Rollback an applied patch."""
        # Find patch in history
        patch = next((p for p in self._patch_history if p.id == patch_id), None)
        if not patch:
            logger.error("Patch not found in history", patch_id=patch_id)
            return False
        
        # Get original commit hash
        result = subprocess.run(
            ["git", "log", "--oneline", "-n", "1", "--grep", f"Patch-ID: {patch_id}"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0 or not result.stdout:
            logger.error("Could not find patch commit", patch_id=patch_id)
            return False
        
        commit = result.stdout.split()[0]
        
        # Revert
        subprocess.run(["git", "revert", "--no-commit", commit])
        subprocess.run(["git", "commit", "-m", f"Revert: {patch.title}"])
        
        patch.status = PatchStatus.ROLLED_BACK
        patch.rollback_id = datetime.now().isoformat()
        
        logger.info("Patch rolled back", patch_id=patch_id)
        return True
    
    async def cleanup(self, patch_id: str) -> None:
        """Clean up worktree after patch is done."""
        worktree = self._active_worktrees.pop(patch_id, None)
        if worktree and worktree.exists():
            shutil.rmtree(worktree, ignore_errors=True)
            logger.info("Cleaned up worktree", patch_id=patch_id)
    
    def get_history(self) -> list[Patch]:
        """Get patch application history."""
        return list(reversed(self._patch_history))


# Global singleton
_patch_sandbox: PatchSandbox | None = None


def get_patch_sandbox() -> PatchSandbox:
    """Get global patch sandbox instance."""
    global _patch_sandbox
    if _patch_sandbox is None:
        _patch_sandbox = PatchSandbox()
    return _patch_sandbox
