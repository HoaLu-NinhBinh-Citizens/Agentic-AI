"""Unit tests for shell, plugin, autofix, kernel, cloud, and CLI."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.infrastructure.shell.shell_wrapper import (
    ShellWrapper,
    ShellType,
    ShellResult,
    OMPBinaryManager,
)
from src.infrastructure.plugins.plugin_system import (
    PluginManager,
    PluginMetadata,
    PluginState,
    PluginInfo,
)
from src.infrastructure.autofix.auto_fix import (
    DiagnosticFixer,
    Diagnostic,
    FixResult,
    FixSeverity,
)
from src.infrastructure.kernel.persistent_kernel import (
    PersistentKernel,
    KernelLanguage,
    KernelState,
    VariablesStore,
)
from src.infrastructure.cloud.cloud_sync import (
    CloudSyncManager,
    SyncProvider,
    SyncConfig,
)


# =============================================================================
# Shell Tests
# =============================================================================

class TestShellWrapper:
    """Tests for ShellWrapper."""

    def test_create_wrapper(self):
        """Test creating shell wrapper."""
        wrapper = ShellWrapper(ShellType.BASH)
        
        assert wrapper.shell_type == ShellType.BASH

    def test_shell_result(self):
        """Test shell result."""
        result = ShellResult(
            stdout="hello",
            stderr="",
            exit_code=0,
            duration_ms=100.0,
        )
        
        assert result.stdout == "hello"
        assert result.exit_code == 0


class TestOMPBinaryManager:
    """Tests for OMPBinaryManager."""

    def test_create_manager(self):
        """Test creating manager."""
        manager = OMPBinaryManager()
        
        assert manager.install_dir is not None

    def test_find_existing(self):
        """Test finding existing binary."""
        manager = OMPBinaryManager()
        path = manager.find_existing()
        
        # May be None if not installed
        assert path is None or isinstance(path, Path)


# =============================================================================
# Plugin Tests
# =============================================================================

class TestPluginManager:
    """Tests for PluginManager."""

    def test_create_manager(self, tmp_path):
        """Test creating manager."""
        manager = PluginManager(tmp_path / "plugins")
        
        assert manager.plugin_dir == tmp_path / "plugins"

    def test_create_plugin_info(self):
        """Test creating plugin info."""
        metadata = PluginMetadata(
            name="test-plugin",
            version="1.0.0",
        )
        
        info = PluginInfo(
            metadata=metadata,
            path=Path("."),
        )
        
        assert info.metadata.name == "test-plugin"
        assert info.state == PluginState.DISCOVERED


class TestPluginMetadata:
    """Tests for PluginMetadata."""

    def test_create_metadata(self):
        """Test creating metadata."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            description="A test plugin",
            author="Test Author",
        )
        
        assert metadata.name == "test"
        assert metadata.version == "1.0.0"
        assert metadata.author == "Test Author"


# =============================================================================
# Auto-fix Tests
# =============================================================================

class TestDiagnosticFixer:
    """Tests for DiagnosticFixer."""

    def test_create_fixer(self):
        """Test creating fixer."""
        fixer = DiagnosticFixer()
        
        assert len(fixer._rules) > 0


class TestFixResult:
    """Tests for FixResult."""

    def test_create_result(self):
        """Test creating fix result."""
        result = FixResult(
            success=True,
            applied=[],
            failed=[],
            skipped=[],
        )
        
        assert result.success is True


class TestDiagnostic:
    """Tests for Diagnostic."""

    def test_create_diagnostic(self):
        """Test creating diagnostic."""
        diag = Diagnostic(
            message="Missing import",
            severity=FixSeverity.WARNING,
            range={"start": {"line": 1, "character": 0}},
        )
        
        assert diag.message == "Missing import"
        assert diag.severity == FixSeverity.WARNING


# =============================================================================
# Kernel Tests
# =============================================================================

class TestVariablesStore:
    """Tests for VariablesStore."""

    def test_create_store(self):
        """Test creating store."""
        store = VariablesStore()
        
        assert len(store._variables) == 0

    def test_set_get(self):
        """Test set and get."""
        store = VariablesStore()
        
        store.set("x", 10)
        
        assert store.get("x") == 10

    def test_delete(self):
        """Test delete."""
        store = VariablesStore()
        
        store.set("x", 10)
        result = store.delete("x")
        
        assert result is True
        assert store.get("x") is None

    def test_list_all(self):
        """Test listing all."""
        store = VariablesStore()
        
        store.set("x", 10)
        store.set("y", "hello")
        
        all_vars = store.list_all()
        
        assert "x" in all_vars
        assert "y" in all_vars


class TestPersistentKernel:
    """Tests for PersistentKernel."""

    def test_create_kernel(self):
        """Test creating kernel."""
        kernel = PersistentKernel(KernelLanguage.PYTHON)
        
        assert kernel.language == KernelLanguage.PYTHON
        assert kernel.state == KernelState.IDLE

    @pytest.mark.asyncio
    async def test_start_stop(self):
        """Test start and stop."""
        kernel = PersistentKernel(KernelLanguage.PYTHON)
        
        await kernel.start()
        assert kernel.state == KernelState.IDLE
        
        await kernel.stop()
        assert kernel.state == KernelState.DEAD

    @pytest.mark.asyncio
    async def test_execute_simple(self):
        """Test simple execution."""
        kernel = PersistentKernel(KernelLanguage.PYTHON)
        await kernel.start()
        
        result = await kernel.execute("x = 1 + 1")
        
        assert result.success is True
        
        await kernel.stop()


# =============================================================================
# Cloud Sync Tests
# =============================================================================

class TestSyncConfig:
    """Tests for SyncConfig."""

    def test_create_config(self):
        """Test creating config."""
        config = SyncConfig(
            provider=SyncProvider.LOCAL,
        )
        
        assert config.provider == SyncProvider.LOCAL


class TestCloudSyncManager:
    """Tests for CloudSyncManager."""

    def test_create_manager(self):
        """Test creating manager."""
        config = SyncConfig(provider=SyncProvider.LOCAL)
        manager = CloudSyncManager(config)
        
        assert manager.config.provider == SyncProvider.LOCAL


# =============================================================================
# CLI Packaging Tests
# =============================================================================

class TestCLISetup:
    """Tests for CLISetup."""

    def test_create_pyproject(self, tmp_path):
        """Test creating pyproject.toml."""
        from src.infrastructure.cli.packaging import CLISetup
        
        setup = CLISetup(tmp_path)
        path = setup.create_pyproject_toml(name="test-pkg", version="0.1.0")
        
        assert path.exists()
        content = path.read_text()
        assert "test-pkg" in content
        assert "0.1.0" in content
