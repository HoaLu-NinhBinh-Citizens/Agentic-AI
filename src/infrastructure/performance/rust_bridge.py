"""Rust CLI wrapper for performance-critical operations.

Provides optional Rust subprocess calls for:
- Fast file globbing
- Content hashing (SHA256)
- Process spawning
- High-throughput operations

Falls back gracefully to Python if Rust binary not available.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


class RustBridge:
    """Bridge to Rust CLI for performance-critical operations.
    
    Uses subprocess to call a Rust binary for heavy operations.
    Falls back to Python implementations if Rust binary not found.
    """
    
    def __init__(self, binary_path: str | None = None):
        self.binary_path = binary_path or self._find_binary()
        self._available = self.binary_path is not None
    
    def _find_binary(self) -> str | None:
        """Find the Rust binary in common locations."""
        candidates = [
            Path(__file__).parent.parent.parent.parent / "target" / "release" / "ai-support-cli",
            Path.home() / ".local" / "bin" / "ai-support-cli",
            Path("/usr/local/bin/ai-support-cli"),
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        
        # Check PATH
        import shutil
        if shutil.which("ai-support-cli"):
            return "ai-support-cli"
        
        return None
    
    @property
    def is_available(self) -> bool:
        """Check if Rust binary is available."""
        return self._available
    
    async def glob_fast(self, root: Path, pattern: str, max_depth: int = 10) -> list[str]:
        """Fast glob using Rust.
        
        Much faster than Python's pathlib.glob for large directories.
        """
        if not self.is_available:
            return list(root.glob(pattern))
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path, "glob",
                str(root),
                pattern,
                "--max-depth", str(max_depth),
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                return json.loads(stdout.decode())
        except Exception:
            pass
        
        # Fallback to Python
        return list(root.glob(pattern))
    
    async def hash_content(self, content: str) -> str:
        """Fast SHA256 hashing using Rust."""
        if not self.is_available:
            import hashlib
            return hashlib.sha256(content.encode()).hexdigest()
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path, "hash",
                "--stdin",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate(input=content.encode())
            
            if proc.returncode == 0:
                return stdout.decode().strip()
        except Exception:
            pass
        
        # Fallback
        import hashlib
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def spawn_process(
        self,
        cmd: list[str],
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Spawn a process with Rust's efficient subprocess handling."""
        if not self.is_available:
            # Fallback to asyncio subprocess
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                return {
                    "returncode": proc.returncode,
                    "stdout": stdout.decode() if stdout else "",
                    "stderr": stderr.decode() if stderr else "",
                }
            except asyncio.TimeoutError:
                proc.kill()
                return {"returncode": -1, "stdout": "", "stderr": "Timeout"}
        
        try:
            # Build command
            rust_cmd = [
                self.binary_path, "spawn",
                "--json",
                "--", *cmd,
            ]
            if cwd:
                rust_cmd.insert(2, f"--cwd={cwd}")
            
            proc = await asyncio.create_subprocess_exec(
                *rust_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                return json.loads(stdout.decode())
        except Exception:
            pass
        
        # Fallback to Python
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd) if cwd else None,
                env=env,
                capture_output=True,
                timeout=timeout,
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout.decode(),
                "stderr": result.stderr.decode(),
            }
        except subprocess.TimeoutExpired:
            return {"returncode": -1, "stdout": "", "stderr": "Timeout"}


# Global singleton
_rust_bridge: RustBridge | None = None


def get_rust_bridge() -> RustBridge:
    """Get or create the global Rust bridge instance."""
    global _rust_bridge
    if _rust_bridge is None:
        _rust_bridge = RustBridge()
    return _rust_bridge


# =============================================================================
# Optional: PyO3 integration (requires maturin setup)
# Uncomment if using PyO3/Maturin for native Python-Rust integration
# =============================================================================
# try:
#     from ._rust_ext import RustExtensions
#     HAS_PYO3 = True
# except ImportError:
#     HAS_PYO3 = False
#
# class PyO3Bridge:
#     """Native Python bindings via PyO3 (faster than subprocess)."""
#
#     def __init__(self):
#         self._ext = RustExtensions()
#
#     def glob_fast(self, root: str, pattern: str) -> list[str]:
#         return self._ext.glob(root, pattern)
#
#     def hash_content(self, content: str) -> str:
#         return self._ext.sha256(content)
#
#     @property
#     def is_available(self) -> bool:
#         return True
