"""CLI packaging and distribution.

Provides:
- CLI entry point
- Binary packaging (PyInstaller)
- pip installable package
- Docker support
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


class CLISetup:
    """CLI setup utilities."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def create_pyproject_toml(
        self,
        name: str = "agentic-ai",
        version: str = "1.0.0",
        description: str = "Local AI Agent for Embedded Systems",
        python_version: str = ">=3.10",
    ) -> Path:
        """Create pyproject.toml for pip installation."""
        
        content = f'''[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{name}"
version = "{version}"
description = "{description}"
readme = "README.md"
license = {{text = "MIT"}}
requires-python = "{python_version}"
authors = [
    {{name = "Agentic-AI Team"}}
]
keywords = ["ai", "agent", "embedded", "firmware"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "httpx>=0.25.0",
    "rich>=13.0.0",
    "pyyaml>=6.0.0",
    "pydantic>=2.0.0",
    "numpy>=1.24.0",
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
]
llm = [
    "openai>=1.0.0",
    "anthropic>=0.5.0",
]
vector = [
    "sentence-transformers>=2.2.0",
    "onnxruntime>=1.16.0",
]
all = [
    "openai>=1.0.0",
    "anthropic>=0.5.0",
    "sentence-transformers>=2.2.0",
    "onnxruntime>=1.16.0",
    "paramiko>=3.0.0",
]

[project.scripts]
agentic-ai = "agentic_ai.cli:main"

[project.urls]
Homepage = "https://github.com/agentic-ai/agentic-ai"
Documentation = "https://agentic-ai.readthedocs.io"
Repository = "https://github.com/agentic-ai/agentic-ai"

[tool.setuptools.packages.find]
where = ["src"]

[tool.setuptools.package-dir]
"" = ""

[tool.black]
line-length = 100
target-version = ['py310']

[tool.ruff]
line-length = 100
target-version = "py310"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
'''
        
        pyproject_path = self.project_root / "pyproject.toml"
        pyproject_path.write_text(content)
        
        return pyproject_path
    
    def create_cli_entry_point(self) -> Path:
        """Create CLI entry point."""
        cli_dir = self.project_root / "src" / "agentic_ai"
        cli_dir.mkdir(parents=True, exist_ok=True)
        
        cli_path = cli_dir / "cli.py"
        
        content = '''"""Command-line interface for Agentic-AI."""

import argparse
import asyncio
import sys
from pathlib import Path


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="agentic-ai",
        description="Local AI Agent for Embedded Systems",
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="agentic-ai 1.0.0",
    )
    
    parser.add_argument(
        "--config",
        type=Path,
        default=Path.home() / ".config" / "agentic-ai",
        help="Configuration directory",
    )
    
    parser.add_argument(
        "--session",
        type=str,
        help="Session ID to resume",
    )
    
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use",
    )
    
    parser.add_argument(
        "--provider",
        type=str,
        default="openai",
        choices=["openai", "anthropic", "ollama", "groq"],
        help="LLM provider",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start chat session")
    chat_parser.add_argument("--prompt", type=str, help="Initial prompt")
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run a task")
    run_parser.add_argument("task", type=str, help="Task description")
    
    # Session commands
    session_parser = subparsers.add_parser("session", help="Session management")
    session_parser.add_argument("--list", action="store_true", help="List sessions")
    session_parser.add_argument("--export", type=str, help="Export session")
    
    args = parser.parse_args()
    
    if args.command == "chat":
        asyncio.run(run_chat(args))
    elif args.command == "run":
        asyncio.run(run_task(args))
    elif args.command == "session":
        manage_sessions(args)
    else:
        # Interactive mode
        asyncio.run(run_interactive(args))


async def run_chat(args):
    """Run chat mode."""
    from agentic_ai.core import AgenticAI
    
    agent = AgenticAI(
        config_dir=args.config,
        model=args.model,
        provider=args.provider,
    )
    
    if args.prompt:
        response = await agent.chat(args.prompt)
        print(response)
    else:
        print("Starting interactive chat...")
        # Would start TUI here


async def run_task(args):
    """Run a task."""
    from agentic_ai.core import AgenticAI
    
    agent = AgenticAI(
        config_dir=args.config,
        model=args.model,
        provider=args.provider,
    )
    
    result = await agent.run_task(args.task)
    print(result)


def manage_sessions(args):
    """Manage sessions."""
    if args.list:
        from agentic_ai.session import SessionManager
        
        manager = SessionManager(args.config)
        sessions = manager.list_sessions()
        
        for session in sessions:
            print(f"{session.id}: {session.created_at}")
    elif args.export:
        print(f"Exporting session: {args.export}")


async def run_interactive(args):
    """Run interactive mode."""
    from agentic_ai.tui import InteractiveTUI
    
    ui = InteractiveTUI(
        config_dir=args.config,
        model=args.model,
        provider=args.provider,
    )
    
    await ui.run()


if __name__ == "__main__":
    main()
'''
        
        cli_path.write_text(content)
        return cli_path
    
    def create_dockerfile(self) -> Path:
        """Create Dockerfile."""
        dockerfile_path = self.project_root / "Dockerfile"
        
        content = '''FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy project
COPY pyproject.toml ./
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e ".[all]"

# Create non-root user
RUN useradd -m -u 1000 agentic && \\
    mkdir -p /home/agentic/.config/agentic-ai && \\
    chown -R agentic:agentic /home/agentic

USER agentic

# Default command
CMD ["python", "-m", "agentic_ai.cli"]

# Entrypoint for easy CLI use
ENTRYPOINT ["agentic-ai"]
'''
        
        dockerfile_path.write_text(content)
        return dockerfile_path
    
    def create_docker_compose(self) -> Path:
        """Create docker-compose.yml."""
        compose_path = self.project_root / "docker-compose.yml"
        
        content = '''version: "3.8"

services:
  agentic-ai:
    build: .
    container_name: agentic-ai
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    volumes:
      - ~/.config/agentic-ai:/home/agentic/.config/agentic-ai
      - ~/.cache/agentic-ai:/home/agentic/.cache/agentic-ai
    stdin_open: true
    tty: true
    profiles:
      - interactive
  
  # Optional: Local LLM with Ollama
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ollama:/root/.ollama
    ports:
      - "11434:11434"
    profiles:
      - llm

volumes:
  ollama:
'''
        
        compose_path.write_text(content)
        return compose_path


class PyInstallerBuilder:
    """Build binary with PyInstaller."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
    
    def create_spec_file(self, name: str = "agentic-ai") -> Path:
        """Create PyInstaller spec file."""
        spec_path = self.project_root / f"{name}.spec"
        
        content = f'''# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

block_cipher = None

# Get src directory
src_path = Path("../src")

a = Analysis(
    ["src/agentic_ai/cli.py"],
    pathex=[str(src_path)],
    binaries=[],
    datas=[
        (str(src_path / "agentic_ai" / "prompts"), "prompts"),
    ],
    hiddenimports=[
        "httpx",
        "rich",
        "pydantic",
        "numpy",
        "asyncio",
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="{name}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
        
        spec_path.write_text(content)
        return spec_path
    
    def build(
        self,
        name: str = "agentic-ai",
        onefile: bool = True,
        clean: bool = True,
    ) -> Path:
        """Build binary."""
        import sys
        
        spec_path = self.create_spec_file(name)
        
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--clean" if clean else "",
            "--noconfirm",
            f"--distpath=dist/{name}",
            f"--workpath=build/{name}",
            str(spec_path),
        ]
        
        cmd = [c for c in cmd if c]  # Remove empty strings
        
        result = subprocess.run(cmd, cwd=str(self.project_root))
        
        if result.returncode != 0:
            raise RuntimeError(f"Build failed: {result.stderr}")
        
        dist_path = self.project_root / "dist" / name
        
        if platform.system() == "Windows":
            dist_path = dist_path.with_suffix(".exe")
        
        return dist_path


class Installer:
    """Create installers."""
    
    @staticmethod
    def create_pip_package(project_root: Path) -> None:
        """Create pip installable package."""
        setup = CLISetup(project_root)
        setup.create_pyproject_toml()
        setup.create_cli_entry_point()
        print(f"Created pip package in {project_root}")
    
    @staticmethod
    def create_docker(project_root: Path) -> None:
        """Create Docker setup."""
        setup = CLISetup(project_root)
        setup.create_dockerfile()
        setup.create_docker_compose()
        print(f"Created Docker setup in {project_root}")
    
    @staticmethod
    def build_binary(project_root: Path, name: str = "agentic-ai") -> Path:
        """Build binary."""
        builder = PyInstallerBuilder(project_root)
        return builder.build(name)


def install_package():
    """Install package in development mode."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-e", "."],
        check=True,
    )


def create_release(name: str = "agentic-ai", version: str = "1.0.0"):
    """Create a release bundle."""
    import zipfile
    import shutil
    
    root = Path.cwd()
    
    # Create distributions
    dist_dir = root / "dist"
    dist_dir.mkdir(exist_ok=True)
    
    release_dir = dist_dir / f"{name}-{version}"
    release_dir.mkdir(exist_ok=True)
    
    # Build components
    setup = CLISetup(root)
    setup.create_pyproject_toml(name=name, version=version)
    setup.create_cli_entry_point()
    setup.create_dockerfile()
    setup.create_docker_compose()
    
    # Create zip
    zip_path = dist_dir / f"{name}-{version}.zip"
    
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in root.rglob("*"):
            if path.is_file() and not any(
                p in path.parts for p in ["dist", "build", "__pycache__", ".git", "node_modules"]
            ):
                arcname = path.relative_to(root)
                zf.write(path, arcname)
    
    print(f"Created release: {zip_path}")
    return zip_path


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Agentic-AI Packaging")
    parser.add_argument("--name", default="agentic-ai", help="Package name")
    parser.add_argument("--version", default="1.0.0", help="Version")
    parser.add_argument("--pip", action="store_true", help="Create pip package")
    parser.add_argument("--docker", action="store_true", help="Create Docker setup")
    parser.add_argument("--binary", action="store_true", help="Build binary")
    parser.add_argument("--release", action="store_true", help="Create release bundle")
    
    args = parser.parse_args()
    
    root = Path.cwd()
    
    if args.pip:
        CLISetup.create_pip_package(root)
    if args.docker:
        CLISetup.create_docker(root)
    if args.binary:
        path = Installer.build_binary(root, args.name)
        print(f"Binary: {path}")
    if args.release:
        create_release(args.name, args.version)
