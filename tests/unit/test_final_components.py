"""Unit tests for shell engine, collaboration, và marketplace."""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.infrastructure.shell.shell_engine import (
    ShellEngine,
    ShellParser,
    ShellBuiltins,
    JobState,
    Job,
)
from src.infrastructure.collab.collaboration import (
    CollabServer,
    CollabClient,
    CollabSession,
    User,
    UserRole,
    SessionState,
)
from src.infrastructure.marketplace.plugin_marketplace import (
    PluginMarketplace,
    PluginRegistry,
    PluginInstaller,
    PluginCategory,
    PluginManifest,
)


# =============================================================================
# Shell Engine Tests
# =============================================================================

class TestShellParser:
    """Tests for ShellParser."""

    def test_create_parser(self):
        """Test creating parser."""
        parser = ShellParser()
        assert parser is not None

    def test_parse_simple_command(self):
        """Test parsing simple command."""
        parser = ShellParser()
        pipelines = parser.parse("ls -la")
        
        assert len(pipelines) == 1
        assert pipelines[0].commands[0].name == "ls"
        assert pipelines[0].commands[0].args == ["-la"]

    def test_parse_pipeline(self):
        """Test parsing pipeline."""
        parser = ShellParser()
        pipelines = parser.parse("ls | grep foo")
        
        assert len(pipelines) == 1
        assert len(pipelines[0].commands) == 2

    def test_parse_background(self):
        """Test parsing background job."""
        parser = ShellParser()
        pipelines = parser.parse("sleep 10 &")
        
        assert len(pipelines) == 1
        assert pipelines[0].background is True


class TestShellEngine:
    """Tests for ShellEngine."""

    def test_create_engine(self):
        """Test creating engine."""
        engine = ShellEngine()
        assert engine is not None
        assert engine.cwd == Path.cwd()

    def test_builtins_available(self):
        """Test builtins are registered."""
        engine = ShellEngine()
        
        assert "cd" in engine.builtins._builtins
        assert "pwd" in engine.builtins._builtins
        assert "echo" in engine.builtins._builtins
        assert "jobs" in engine.builtins._builtins


class TestJob:
    """Tests for Job."""

    def test_create_job(self):
        """Test creating job."""
        job = Job(
            job_id=1,
            pid=1234,
            command="sleep 10",
            process=MagicMock(),
        )
        
        assert job.job_id == 1
        assert job.pid == 1234
        assert job.state == JobState.RUNNING


# =============================================================================
# Collaboration Tests
# =============================================================================

class TestUser:
    """Tests for User."""

    def test_create_user(self):
        """Test creating user."""
        user = User(id="123", name="Test User")
        
        assert user.id == "123"
        assert user.name == "Test User"
        assert user.role == UserRole.VIEWER


class TestCollabSession:
    """Tests for CollabSession."""

    def test_create_session(self):
        """Test creating session."""
        session = CollabSession(
            id="abc",
            name="Test Session",
            owner_id="123",
        )
        
        assert session.id == "abc"
        assert session.name == "Test Session"
        assert session.state == SessionState.ACTIVE


# =============================================================================
# Marketplace Tests
# =============================================================================

class TestPluginManifest:
    """Tests for PluginManifest."""

    def test_create_manifest(self):
        """Test creating manifest."""
        manifest = PluginManifest(
            id="test-plugin",
            name="Test Plugin",
            version="1.0.0",
            description="A test plugin",
        )
        
        assert manifest.id == "test-plugin"
        assert manifest.version == "1.0.0"


class TestPluginRegistry:
    """Tests for PluginRegistry."""

    def test_create_registry(self, tmp_path):
        """Test creating registry."""
        registry = PluginRegistry(tmp_path / "cache")
        
        assert registry.cache_dir == tmp_path / "cache"

    def test_add_plugin(self, tmp_path):
        """Test adding plugin."""
        registry = PluginRegistry(tmp_path / "cache")
        
        registry.add("test-plugin", {"name": "Test"})
        
        assert registry.get("test-plugin") is not None

    def test_remove_plugin(self, tmp_path):
        """Test removing plugin."""
        registry = PluginRegistry(tmp_path / "cache")
        
        registry.add("test-plugin", {"name": "Test"})
        result = registry.remove("test-plugin")
        
        assert result is True
        assert registry.get("test-plugin") is None


class TestPluginInstaller:
    """Tests for PluginInstaller."""

    def test_create_installer(self, tmp_path):
        """Test creating installer."""
        installer = PluginInstaller(tmp_path / "plugins")
        
        assert installer.plugins_dir == tmp_path / "plugins"


class TestPluginMarketplace:
    """Tests for PluginMarketplace."""

    def test_create_marketplace(self, tmp_path):
        """Test creating marketplace."""
        marketplace = PluginMarketplace(tmp_path / "plugins")
        
        assert marketplace.installer is not None
        assert marketplace.api is not None
