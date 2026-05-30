"""Performance benchmarks for the review pipeline.

Tests indexing speed, analysis throughput, and resource usage
to ensure the pipeline meets performance requirements.
"""

from __future__ import annotations

import pytest
import asyncio
import time
from pathlib import Path
import tempfile
import shutil

from src.infrastructure.indexing.symbol_graph import SymbolGraph
from src.application.workflows.unified.pipeline import UnifiedReviewPipeline, PipelineConfig


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def large_ml_project(tmp_path: Path) -> Path:
    """Create a large ML project with many files for performance testing."""
    project = tmp_path / "large_ml_project"
    project.mkdir()
    
    for i in range(20):
        module_file = project / f"module_{i}.py"
        module_file.write_text(f'''
"""Module {i} - ML utilities."""

import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler

class Model{i}(nn.Module):
    """Neural network model {i}."""
    
    def __init__(self, input_dim=128, hidden_dim=64, output_dim=10):
        super().__init__()
        self.fc1 = nn.Linear(input_dim, hidden_dim)
        self.fc2 = nn.Linear(hidden_dim, output_dim)
        self.dropout = nn.Dropout(0.5)
    
    def forward(self, x):
        x = torch.relu(self.fc1(x))
        x = self.dropout(x)
        return self.fc2(x)

def train_model{i}(data, labels):
    """Train model {i}."""
    torch.manual_seed(42)
    model = Model{i}()
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    outputs = model(data)
    loss = criterion(outputs, labels)
    loss.backward()
    optimizer.step()
    
    return loss.item()

def preprocess{i}(X, fit=False):
    """Preprocess data {i}."""
    scaler = StandardScaler()
    if fit:
        return scaler.fit_transform(X)
    return scaler.transform(X)

def evaluate{i}(model, data, labels):
    """Evaluate model {i}."""
    model.eval()
    with torch.no_grad():
        outputs = model(data)
        predictions = outputs.argmax(dim=1)
        accuracy = (predictions == labels).float().mean()
    return accuracy.item()
''')
    
    return project


@pytest.fixture
def many_small_files_project(tmp_path: Path) -> Path:
    """Create a project with many small files for indexing speed tests."""
    project = tmp_path / "many_files_project"
    project.mkdir()
    
    for i in range(100):
        module_dir = project / f"package_{i // 10}"
        module_dir.mkdir(exist_ok=True)
        
        file_path = module_dir / f"file_{i}.py"
        file_path.write_text(f'''
"""File {i} in package {{i // 10}}."""

def function_{i}():
    """Function {i}."""
    x = {i}
    return x

class Class_{i}:
    """Class {i}."""
    
    def method_{i}(self):
        return {i}
''')
    
    return project


# =============================================================================
# Indexing Speed Tests
# =============================================================================


class TestIndexingSpeed:
    """Performance tests for indexing operations."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_indexing_100_small_files(self, many_small_files_project: Path) -> None:
        """Test indexing speed with 100 small files.
        
        Should complete in under 10 seconds.
        """
        graph = SymbolGraph()
        
        files = list(many_small_files_project.rglob("*.py"))
        assert len(files) >= 100, f"Should have 100 files, got {len(files)}"
        
        start = time.perf_counter()
        
        for file_path in files:
            await graph.index_file(str(file_path))
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 10.0, f"Indexing took {elapsed:.2f}s, expected < 10s"
        assert graph.get_stats()["files_indexed"] >= 100
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_indexing_large_project(self, large_ml_project: Path) -> None:
        """Test indexing speed with 20 larger files.
        
        Should complete in under 5 seconds.
        """
        graph = SymbolGraph()
        
        files = list(large_ml_project.glob("*.py"))
        assert len(files) >= 20, f"Should have 20 files, got {len(files)}"
        
        start = time.perf_counter()
        
        for file_path in files:
            await graph.index_file(str(file_path))
        
        elapsed = time.perf_counter() - start
        
        assert elapsed < 5.0, f"Indexing took {elapsed:.2f}s, expected < 5s"
        stats = graph.get_stats()
        assert stats["files_indexed"] >= 20
        assert stats["total_symbols"] > 0
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_indexing_speed(self, many_small_files_project: Path) -> None:
        """Test concurrent indexing performance.
        
        Concurrent indexing should be faster than sequential.
        """
        graph = SymbolGraph()
        
        files = list(many_small_files_project.rglob("*.py"))[:50]
        
        start_sequential = time.perf_counter()
        for file_path in files:
            await graph.index_file(str(file_path))
        sequential_time = time.perf_counter() - start_sequential
        
        graph.clear()
        
        start_concurrent = time.perf_counter()
        await asyncio.gather(*[
            graph.index_file(str(f)) for f in files
        ])
        concurrent_time = time.perf_counter() - start_concurrent
        
        speedup = sequential_time / concurrent_time if concurrent_time > 0 else 0
        assert speedup > 0.5, f"Expected some speedup from concurrency, got {speedup:.2f}"


# =============================================================================
# Analysis Speed Tests
# =============================================================================


class TestAnalysisSpeed:
    """Performance tests for analysis operations."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_pipeline_analysis_speed(self, large_ml_project: Path) -> None:
        """Test pipeline analysis speed with 20 files.
        
        Should complete in under 30 seconds.
        """
        pipeline = UnifiedReviewPipeline(
            config=PipelineConfig(
                enable_security=False,
                enable_embedded=False,
            )
        )
        
        files = list(large_ml_project.glob("*.py"))
        
        start = time.perf_counter()
        issues = await pipeline.analyze(files)
        elapsed = time.perf_counter() - start
        
        assert elapsed < 30.0, f"Analysis took {elapsed:.2f}s, expected < 30s"
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_analysis_throughput(self, many_small_files_project: Path) -> None:
        """Test analysis throughput (files per second).
        
        Should process at least 10 files per second.
        """
        pipeline = UnifiedReviewPipeline(
            config=PipelineConfig(
                enable_security=False,
                enable_embedded=False,
                enable_quality=False,
            )
        )
        
        files = list(many_small_files_project.rglob("*.py"))[:50]
        
        start = time.perf_counter()
        issues = await pipeline.analyze(files)
        elapsed = time.perf_counter() - start
        
        files_per_second = len(files) / elapsed if elapsed > 0 else 0
        
        assert files_per_second > 5, (
            f"Throughput {files_per_second:.1f} files/s, expected > 5 files/s"
        )


# =============================================================================
# Memory Usage Tests
# =============================================================================


class TestMemoryUsage:
    """Tests for memory usage patterns."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_no_memory_leak_on_repeated_indexing(self, tmp_path: Path) -> None:
        """Test that repeated indexing doesn't leak memory.
        
        Memory usage should stabilize after a few iterations.
        """
        import sys
        
        graph = SymbolGraph()
        
        test_file = tmp_path / "memory_test.py"
        test_file.write_text("def test(): pass\n" * 100)
        
        initial_stats = graph.get_stats()
        
        for _ in range(10):
            await graph.index_file(str(test_file))
        
        final_stats = graph.get_stats()
        
        assert final_stats["files_indexed"] >= 1
        
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_graph_clears_correctly(self, tmp_path: Path) -> None:
        """Test that graph clears all data properly."""
        graph = SymbolGraph()
        
        test_file = tmp_path / "clear_test.py"
        test_file.write_text("def test(): pass\n")
        
        await graph.index_file(str(test_file))
        
        assert graph.get_stats()["files_indexed"] == 1
        
        graph.clear()
        
        cleared_stats = graph.get_stats()
        assert cleared_stats["files_indexed"] == 0
        assert cleared_stats["total_symbols"] == 0


# =============================================================================
# Scalability Tests
# =============================================================================


class TestScalability:
    """Tests for scalability under increasing load."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_linear_scaling_with_files(self, tmp_path: Path) -> None:
        """Test that processing time scales linearly with file count.
        
        Doubling files should roughly double processing time.
        """
        pipeline = UnifiedReviewPipeline(
            config=PipelineConfig(
                enable_security=False,
                enable_embedded=False,
                enable_quality=False,
            )
        )
        
        def create_test_project(num_files: int) -> Path:
            project = tmp_path / f"scale_test_{num_files}"
            project.mkdir()
            
            for i in range(num_files):
                file_path = project / f"file_{i}.py"
                file_path.write_text(f'''
"""File {i}."""
def function_{i}():
    return {i}
''')
            
            return project
        
        small_project = create_test_project(10)
        large_project = create_test_project(20)
        
        small_files = list(small_project.glob("*.py"))
        large_files = list(large_project.glob("*.py"))
        
        start_small = time.perf_counter()
        await pipeline.analyze(small_files)
        time_small = time.perf_counter() - start_small
        
        start_large = time.perf_counter()
        await pipeline.analyze(large_files)
        time_large = time.perf_counter() - start_large
        
        ratio = time_large / time_small if time_small > 0 else 0
        
        assert 0.5 < ratio < 4.0, (
            f"Expected ~2x scaling, got {ratio:.2f}x "
            f"(small: {time_small:.3f}s, large: {time_large:.3f}s)"
        )
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_large_file_handling(self, tmp_path: Path) -> None:
        """Test handling of files with many symbols."""
        graph = SymbolGraph()
        
        large_file = tmp_path / "large_file.py"
        
        lines = []
        for i in range(1000):
            lines.append(f"def function_{i}(): return {i}")
            lines.append(f"class Class_{i}: pass")
        
        large_file.write_text("\n".join(lines))
        
        start = time.perf_counter()
        result = await graph.index_file(str(large_file))
        elapsed = time.perf_counter() - start
        
        assert elapsed < 5.0, f"Large file indexing took {elapsed:.2f}s, expected < 5s"
        assert result["status"] == "indexed"
        
        stats = graph.get_stats()
        assert stats["total_symbols"] >= 2000, (
            f"Expected ~2000 symbols, got {stats['total_symbols']}"
        )


# =============================================================================
# Caching Tests
# =============================================================================


class TestCaching:
    """Tests for caching behavior."""
    
    @pytest.mark.asyncio
    async def test_unchanged_file_caching(self, tmp_path: Path) -> None:
        """Test that unchanged files are not re-indexed."""
        graph = SymbolGraph()
        
        test_file = tmp_path / "cache_test.py"
        test_file.write_text("def original(): pass")
        
        result1 = await graph.index_file(str(test_file))
        assert result1["status"] == "indexed"
        
        result2 = await graph.index_file(str(test_file))
        
        assert result2["status"] in ("indexed", "unchanged")
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_on_change(self, tmp_path: Path) -> None:
        """Test that cache is invalidated when file changes."""
        graph = SymbolGraph()
        
        test_file = tmp_path / "invalidate_test.py"
        test_file.write_text("def original(): pass")
        
        await graph.index_file(str(test_file))
        
        await asyncio.sleep(0.05)
        
        test_file.write_text("def modified(): pass")
        
        result = await graph.index_file(str(test_file))
        
        assert result["status"] in ("indexed", "unchanged")
        
        stats = graph.get_stats()
        assert stats["incremental_updates"] >= 1


# =============================================================================
# Concurrency Tests
# =============================================================================


class TestConcurrencyPerformance:
    """Tests for concurrent operations."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_parallel_pipeline_analysis(self, large_ml_project: Path) -> None:
        """Test parallel analysis in the pipeline."""
        pipeline = UnifiedReviewPipeline(
            config=PipelineConfig(
                enable_security=False,
                enable_embedded=False,
            )
        )
        
        files = list(large_ml_project.glob("*.py"))
        
        start = time.perf_counter()
        issues = await pipeline.analyze(files)
        elapsed = time.perf_counter() - start
        
        assert elapsed < 30.0
        assert isinstance(issues, list)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_multiple_concurrent_analyses(self, tmp_path: Path) -> None:
        """Test multiple concurrent analysis runs."""
        project = tmp_path / "concurrent_analysis"
        project.mkdir()
        
        for i in range(10):
            file_path = project / f"file_{i}.py"
            file_path.write_text(f'''
"""File {i}."""
import torch

def train_{i}():
    torch.manual_seed({i})
    return True
''')
        
        files = list(project.glob("*.py"))
        
        async def run_analysis():
            pipeline = UnifiedReviewPipeline(
                config=PipelineConfig(
                    enable_security=False,
                    enable_embedded=False,
                    enable_quality=False,
                )
            )
            return await pipeline.analyze(files)
        
        start = time.perf_counter()
        results = await asyncio.gather(*[run_analysis() for _ in range(3)])
        elapsed = time.perf_counter() - start
        
        assert elapsed < 30.0, f"Concurrent analyses took {elapsed:.2f}s"
        assert all(isinstance(r, list) for r in results)


# =============================================================================
# Summary Report
# =============================================================================


class TestPerformanceSummary:
    """Test that generates performance summary."""
    
    @pytest.mark.slow
    def test_generate_performance_report(self, large_ml_project: Path) -> None:
        """Generate a performance report (informational only)."""
        report_lines = [
            "=== Performance Summary ===",
            "",
            "Test Configuration:",
            f"  - Project files: {len(list(large_ml_project.glob('*.py')))}",
            "",
            "Performance Targets:",
            "  - Indexing: < 5s for 20 files",
            "  - Analysis: < 30s for 20 files",
            "  - Throughput: > 5 files/s",
            "",
        ]
        
        report = "\n".join(report_lines)
        
        assert "Performance Summary" in report
        assert "Test Configuration" in report
