"""Debug probe lifecycle manager (Phase 6.1)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from src.domain.hardware.debug_probe import BaseProbe, create_probe
from src.domain.hardware.embedded_target import DebugProbeType
from src.domain.hardware.probe import ProbePort, probe_supports_memory
from src.infrastructure.hardware.jlink.probe import JLinkProbeAdapter

logger = logging.getLogger(__name__)

DEFAULT_TARGETS_PATH = Path(__file__).resolve().parents[3] / "configs" / "hardware" / "targets.yaml"


class ProbeManager:
    """Discover, connect, and track debug probes."""

    def __init__(self, targets_path: Path | None = None) -> None:
        self._targets_path = targets_path or DEFAULT_TARGETS_PATH
        self._probes: dict[str, BaseProbe] = {}
        self._targets: dict[str, dict[str, Any]] = {}

    def load_targets(self) -> dict[str, dict[str, Any]]:
        """Load target definitions from YAML."""
        if not self._targets_path.is_file():
            logger.warning("targets file missing: %s", self._targets_path)
            return {}
        with self._targets_path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
        self._targets = data.get("targets", {})
        return self._targets

    def list_targets(self) -> list[str]:
        if not self._targets:
            self.load_targets()
        return list(self._targets.keys())

    def get_target_config(self, name: str) -> dict[str, Any] | None:
        if not self._targets:
            self.load_targets()
        return self._targets.get(name)

    async def connect(
        self,
        target_name: str,
        probe_type: DebugProbeType = DebugProbeType.JLINK,
        probe_id: str | None = None,
    ) -> BaseProbe:
        """Connect probe for named target."""
        cfg = self.get_target_config(target_name)
        if cfg is None:
            raise KeyError(f"Unknown target: {target_name}")

        key = probe_id or f"{target_name}:{probe_type.value}"
        if key in self._probes and self._probes[key].is_connected:
            return self._probes[key]

        probe = self._create_probe(probe_type, cfg)
        await probe.connect()
        self._probes[key] = probe
        return probe

    def _create_probe(self, probe_type: DebugProbeType, cfg: dict[str, Any]) -> BaseProbe:
        if probe_type == DebugProbeType.JLINK:
            speed = int(cfg.get("jlink_speed_khz", 4000))
            return JLinkProbeAdapter(speed_khz=speed, use_mock=True)
        return create_probe(probe_type)

    async def disconnect(self, probe_id: str) -> None:
        probe = self._probes.pop(probe_id, None)
        if probe and probe.is_connected:
            await probe.disconnect()

    async def disconnect_all(self) -> None:
        for pid in list(self._probes.keys()):
            await self.disconnect(pid)

    def get_probe(self, probe_id: str) -> BaseProbe | None:
        return self._probes.get(probe_id)

    def get_memory_probe(self, probe_id: str) -> ProbePort | None:
        probe = self._probes.get(probe_id)
        if probe and probe_supports_memory(probe):
            return probe  # type: ignore[return-value]
        return None
