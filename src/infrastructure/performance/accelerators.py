"""High-performance CLI utilities in Rust.

This module provides compiled Rust binaries for performance-critical operations:
- Fast file globbing and searching
- Content hashing (SHA256, xxHash)
- Streaming JSON parsing
- Efficient subprocess handling
- Regex-based text operations

Build:
    cd src/infrastructure/performance/rust
    cargo build --release

Install:
    cargo install --path .
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator


class RustBinary:
    """Wrapper for Rust CLI binary."""
    
    def __init__(self, binary_path: str | Path | None = None):
        self.binary_path = binary_path or self._find_binary()
        self._available = self.binary_path is not None
    
    def _find_binary(self) -> str | None:
        """Find the Rust binary."""
        candidates = [
            # Local build
            Path(__file__).parent.parent.parent.parent / "target" / "release" / "ai-support-perf",
            Path(__file__).parent / "target" / "release" / "ai-support-perf",
            # Installed
            Path.home() / ".local" / "bin" / "ai-support-perf",
            Path("/usr/local/bin/ai-support-perf"),
        ]
        
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        
        # Check PATH
        if shutil.which("ai-support-perf"):
            return "ai-support-perf"
        
        return None
    
    @property
    def is_available(self) -> bool:
        """Check if Rust binary is available."""
        return self._available


# =============================================================================
# High-Performance Search
# =============================================================================

class FastSearch:
    """Fast file searching using Rust's ripgrep-inspired implementation."""
    
    def __init__(self, binary: RustBinary):
        self.binary = binary
    
    async def grep(
        self,
        root: Path,
        pattern: str,
        file_pattern: str = "*",
        case_sensitive: bool = False,
        context: int = 0,
        max_count: int = 0,
    ) -> list[dict[str, Any]]:
        """Fast grep using Rust."""
        if not self.binary.is_available:
            return await self._python_grep(root, pattern, file_pattern)
        
        try:
            cmd = [
                self.binary.binary_path, "grep",
                "--json",
                "--root", str(root),
                "--pattern", pattern,
            ]
            
            if case_sensitive:
                cmd.append("--case-sensitive")
            if context > 0:
                cmd.extend(["--context", str(context)])
            if max_count > 0:
                cmd.extend(["--max-count", str(max_count)])
            
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                results = []
                for line in stdout.decode().splitlines():
                    if line.strip():
                        results.append(json.loads(line))
                return results
                
        except Exception:
            pass
        
        return await self._python_grep(root, pattern, file_pattern)
    
    async def _python_grep(
        self,
        root: Path,
        pattern: str,
        file_pattern: str,
    ) -> list[dict[str, Any]]:
        """Python fallback grep."""
        import re
        results = []
        
        for file in root.rglob(file_pattern):
            if not file.is_file():
                continue
            
            try:
                content = file.read_text(errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if re.search(pattern, line):
                        results.append({
                            "path": str(file),
                            "line_number": i,
                            "line": line,
                        })
            except:
                pass
        
        return results
    
    async def search_indexed(
        self,
        index_path: Path,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search using pre-built index."""
        if not self.binary.is_available:
            return []
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary.binary_path, "search",
                "--index", str(index_path),
                "--query", query,
                "--limit", str(limit),
                stdout=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                return json.loads(stdout.decode())
                
        except Exception:
            pass
        
        return []


# =============================================================================
# Streaming JSON Parser
# =============================================================================

class StreamingJSONParser:
    """High-performance streaming JSON parser using Rust."""
    
    def __init__(self, binary: RustBinary):
        self.binary = binary
    
    async def parse_stream(
        self,
        data: bytes,
        callback: callable,
    ) -> None:
        """Parse JSON stream with callback for each object."""
        if not self.binary.is_available:
            # Python fallback
            import ijson
            objects = ijson.items(data, "")
            for obj in objects:
                callback(obj)
            return
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary.binary_path, "json-stream",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await proc.communicate(input=data)
            
            if proc.returncode == 0:
                for line in stdout.decode().splitlines():
                    if line.strip():
                        callback(json.loads(line))
                        
        except Exception:
            # Fallback
            import ijson
            objects = ijson.items(data, "")
            for obj in objects:
                callback(obj)


# =============================================================================
# Fast Hash Operations
# =============================================================================

class FastHash:
    """Fast hashing using Rust's optimized implementation."""
    
    def __init__(self, binary: RustBinary):
        self.binary = binary
    
    async def hash_file(self, path: Path, algorithm: str = "sha256") -> str:
        """Hash a file."""
        if not self.binary.is_available:
            return await self._python_hash_file(path, algorithm)
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary.binary_path, "hash-file",
                "--algorithm", algorithm,
                str(path),
                stdout=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                return stdout.decode().strip()
                
        except Exception:
            pass
        
        return await self._python_hash_file(path, algorithm)
    
    async def _python_hash_file(self, path: Path, algorithm: str) -> str:
        """Python fallback file hashing."""
        import hashlib
        
        h = hashlib.new(algorithm)
        data = path.read_bytes()
        h.update(data)
        
        return h.hexdigest()
    
    async def hash_directory(self, path: Path) -> dict[str, str]:
        """Hash all files in a directory (for change detection)."""
        hashes = {}
        
        for file in sorted(path.rglob("*")):
            if file.is_file():
                rel_path = str(file.relative_to(path))
                hashes[rel_path] = await self.hash_file(file)
        
        return hashes


# =============================================================================
# Efficient File Operations
# =============================================================================

class FastFileOps:
    """High-performance file operations using Rust."""
    
    def __init__(self, binary: RustBinary):
        self.binary = binary
    
    async def copy_tree(
        self,
        src: Path,
        dst: Path,
        parallel: bool = True,
    ) -> None:
        """Copy directory tree."""
        if not self.binary.is_available or not parallel:
            # Use shutil fallback
            shutil.copytree(src, dst, dirs_exist_ok=True)
            return
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary.binary_path, "copy-tree",
                str(src),
                str(dst),
                stdout=asyncio.subprocess.PIPE,
            )
            
            await proc.communicate()
            
        except Exception:
            shutil.copytree(src, dst, dirs_exist_ok=True)
    
    async def find_duplicates(self, root: Path) -> list[list[Path]]:
        """Find duplicate files by content."""
        if not self.binary.is_available:
            return await self._python_find_duplicates(root)
        
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary.binary_path, "find-dupes",
                str(root),
                stdout=asyncio.subprocess.PIPE,
            )
            
            stdout, _ = await proc.communicate()
            
            if proc.returncode == 0:
                # Parse output as groups
                groups = []
                for line in stdout.decode().splitlines():
                    if line.strip():
                        groups.append([Path(p) for p in line.split("\t")])
                return groups
                
        except Exception:
            pass
        
        return await self._python_find_duplicates(root)
    
    async def _python_find_duplicates(self, root: Path) -> list[list[Path]]:
        """Python fallback for finding duplicates."""
        size_map: dict[int, list[Path]] = {}
        
        # Group by size
        for file in root.rglob("*"):
            if file.is_file():
                size = file.stat().st_size
                if size not in size_map:
                    size_map[size] = []
                size_map[size].append(file)
        
        # Check hash for same-size files
        hash_map: dict[str, list[Path]] = {}
        duplicates = []
        
        for paths in size_map.values():
            if len(paths) < 2:
                continue
            
            for path in paths:
                h = await FastHash(RustBinary()).hash_file(path)
                if h in hash_map:
                    hash_map[h].append(path)
                else:
                    hash_map[h] = [path]
        
        for paths in hash_map.values():
            if len(paths) > 1:
                duplicates.append(paths)
        
        return duplicates


# =============================================================================
# Global Performance Module
# =============================================================================

class PerformanceModule:
    """High-performance module combining all Rust-powered features."""
    
    def __init__(self):
        self.binary = RustBinary()
        self.search = FastSearch(self.binary)
        self.hash = FastHash(self.binary)
        self.file_ops = FastFileOps(self.binary)
        self.json_parser = StreamingJSONParser(self.binary)
    
    @property
    def rust_available(self) -> bool:
        """Check if Rust acceleration is available."""
        return self.binary.is_available


# Global singleton
_performance: PerformanceModule | None = None


def get_performance() -> PerformanceModule:
    """Get or create global performance module."""
    global _performance
    if _performance is None:
        _performance = PerformanceModule()
    return _performance


# =============================================================================
# Cython Acceleration (Optional)
# =============================================================================

try:
    from ._cython_ext import (
        fast_grep,
        fast_hash,
        fast_glob,
    )
    HAS_CYTHON = True
except ImportError:
    HAS_CYTHON = False


class CythonAccelerator:
    """Cython-accelerated operations (faster than pure Python, slower than Rust)."""
    
    @staticmethod
    def grep(root: str, pattern: str, max_results: int = 1000) -> list[dict]:
        """Fast grep with Cython."""
        if not HAS_CYTHON:
            raise ImportError("Cython extension not available")
        return fast_grep(root, pattern, max_results)
    
    @staticmethod
    def hash_file(path: str) -> str:
        """Fast file hash with Cython."""
        if not HAS_CYTHON:
            raise ImportError("Cython extension not available")
        return fast_hash(path)
    
    @staticmethod
    def glob(root: str, pattern: str) -> list[str]:
        """Fast glob with Cython."""
        if not HAS_CYTHON:
            raise ImportError("Cython extension not available")
        return fast_glob(root, pattern)
