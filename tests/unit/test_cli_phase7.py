"""Unit tests for Phase 7 CLI."""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch

from src.interfaces.cli.main import build_parser, main


def test_parser_has_commands() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    args = parser.parse_args(["health"])
    assert args.command == "health"


@pytest.mark.asyncio
async def test_health_local() -> None:
    code = await main(["health"])
    assert code == 0


@pytest.mark.asyncio
async def test_flash_dry_run(tmp_path: Path) -> None:
    fw = tmp_path / "fw.bin"
    fw.write_bytes(b"\x00" * 128)
    code = await main(["flash", "EngineCar", str(fw)])
    assert code == 0


@pytest.mark.asyncio
async def test_debug_connect(tmp_path: Path) -> None:
    targets = tmp_path / "targets.yaml"
    targets.write_text(
        "targets:\n  T1:\n    jlink_speed_khz: 4000\n",
        encoding="utf-8",
    )
    code = await main(["debug", "connect", "T1", "--targets", str(targets)])
    assert code == 0
