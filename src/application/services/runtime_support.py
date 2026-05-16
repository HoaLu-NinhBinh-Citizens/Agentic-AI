import re
import json
from pathlib import Path
from typing import List

from src.core.config.agent_prompts import BOARD_PROFILE_FILE
from src.infrastructure.models import RuntimeDiagnosis, TaskPlan, ToolResult


class RuntimeSupport:
    def __init__(self, agent):
        self.agent = agent

    def diagnose_runtime_output(self, result: ToolResult, plan: TaskPlan) -> RuntimeDiagnosis:
        text = "\n".join(part for part in (result.stdout, result.stderr) if part).lower()
        findings: List[str] = []
        warnings: List[str] = []
        missing: List[str] = []
        board_profile = self.load_board_profile(plan.target_project)

        signal_patterns = {
            "system_init": [r"\[system init\]", r"stm32f407"],
            "clock_init": [r"\[clock\]", r"pll", r"168 mhz"],
            "hal_init": [r"\[hal\]", r"gpio initialized"],
            "rtos_start": [r"\[freertos\]", r"kernel starting"],
            "flash_ok": [r"flash successful", r"flash operation completed"],
            "rtt_monitor": [r"monitoring rtt", r"rtt output"],
        }

        if "dry run" in text:
            findings.append("runtime observe ran in dry-run mode")

        for signal in board_profile.get("required_signals", []):
            label = str(signal.get("label", "")).strip()
            patterns = [str(pattern) for pattern in signal.get("patterns", []) if str(pattern).strip()]
            if not label or not patterns:
                continue
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
                findings.append(label)
            elif plan.should_observe_runtime and not plan.runtime_dry_run:
                missing.append(label)

        for label, patterns in signal_patterns.items():
            if any(re.search(pattern, text, re.IGNORECASE) for pattern in patterns):
                findings.append(label)
            elif label in {"system_init", "clock_init", "hal_init"} and plan.should_observe_runtime:
                missing.append(label)

        if re.search(r"hard\s*fault|cfsr|backtrace|gdb", text, re.IGNORECASE):
            warnings.append("hardware_fault_detected")
            findings.append("GDB Backtrace contains fault data. Examine CFSR and Call Stack.")

        if re.search(r"\bfailed\b|\berror\b|\bexception\b", text, re.IGNORECASE):
            warnings.append("runtime output contains failure markers")
        if "j-link" in text and ("not found" in text or "failed" in text):
            warnings.append("j-link connectivity/tool issue detected")
        if "rtt" in text and ("requires hardware" in text or "[skip]" in text):
            warnings.append("rtt monitor did not attach to live target")

        status = "ok"
        if warnings or (missing and not plan.runtime_dry_run):
            status = "degraded"

        summary_parts: List[str] = []
        if findings:
            summary_parts.append("findings=" + ",".join(findings[:4]))
        if warnings:
            summary_parts.append("warnings=" + ",".join(warnings[:3]))
        if missing:
            summary_parts.append("missing=" + ",".join(missing[:3]))

        return RuntimeDiagnosis(
            status=status,
            findings=findings[:8],
            warnings=warnings[:8],
            missing_signals=missing[:8],
            summary="; ".join(summary_parts),
        )

    def load_board_profile(self, target_project: str) -> dict:
        profile_path = Path(self.agent.project_root) / BOARD_PROFILE_FILE
        if not profile_path.exists():
            return {}
        try:
            data = json.loads(profile_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        profiles = data.get("profiles", data)
        if not isinstance(profiles, dict):
            return {}
        key = str(target_project or "").strip()
        if key and isinstance(profiles.get(key), dict):
            return profiles[key]
        default = profiles.get("default", {})
        return default if isinstance(default, dict) else {}

