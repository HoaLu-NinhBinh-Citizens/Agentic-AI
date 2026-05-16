import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from src.infrastructure.models import BuildError, BuildResult, ToolResult
from src.domains.runtime.board_profile import BoardProfileManager, MISSING_BOARD_PROFILE

BUILD_TIMEOUT_SECONDS = 180
FLASH_TIMEOUT_SECONDS = 180
AUTO_DEBUG_TIMEOUT_SECONDS = 60
RUNTIME_OBSERVE_TIMEOUT_SECONDS = 120


class BuildTools:
    """Build system operations."""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root).resolve()
        self.build_root = self._find_build_root()
        self.build_dir = self.build_root / "build"
        self.python_executable = self._resolve_python_executable()
        self.board_profiles = BoardProfileManager(str(self.project_root))

    def _score_build_root(self, candidate: Path) -> int:
        score = 0
        if (candidate / "build.py").exists():
            score += 10
        if (candidate / "Build.ps1").exists():
            score += 8
        if (candidate / "config.yaml").exists():
            score += 6
        if (candidate / "README.md").exists():
            score += 2
        if any(candidate.glob("**/CMakeLists.txt")):
            score += 4
        return score

    def _find_build_root(self) -> Path:
        """Find the most likely build root below the provided project root."""
        candidates = [self.project_root]
        candidates.extend(
            path for path in self.project_root.rglob("*")
            if path.is_dir() and len(path.relative_to(self.project_root).parts) <= 3
        )

        best = self.project_root
        best_score = self._score_build_root(self.project_root)
        for candidate in candidates:
            score = self._score_build_root(candidate)
            if score > best_score:
                best = candidate
                best_score = score
        return best

    def _resolve_python_executable(self) -> str:
        """Resolve the most reliable Python interpreter for build and runtime scripts."""
        override = str(os.environ.get("CARV_PYTHON", "")).strip()
        use_local_venv = str(os.environ.get("CARV_USE_LOCAL_VENV", "")).strip().lower() in {"1", "true", "yes", "on"}
        candidates: List[Path] = []
        if override:
            candidates.append(Path(override))

        if use_local_venv:
            search_roots = [self.build_root, self.build_root.parent, self.project_root / "main", self.project_root]
            seen = set()
            for root in search_roots:
                normalized_root = Path(root).resolve()
                if normalized_root in seen:
                    continue
                seen.add(normalized_root)
                candidates.extend([
                    normalized_root / ".venv" / "Scripts" / "python.exe",
                    normalized_root / ".venv" / "bin" / "python",
                ])

        current_python = Path(sys.executable)
        if current_python.exists():
            candidates.append(current_python)

        for name in ("python", "py"):
            resolved = shutil.which(name)
            if resolved:
                candidates.append(Path(resolved))

        for candidate in candidates:
            try:
                if candidate.exists():
                    return str(candidate.resolve())
            except OSError:
                continue
        return sys.executable

    def run_static_analysis(self, files: List[str]) -> ToolResult:
        """Run lightweight local static checks and optional external C analyzers."""
        start = datetime.now()
        findings: List[str] = []
        source_paths = [self._resolve_project_file(path) for path in files if path.endswith((".c", ".h"))]
        for path in source_paths:
            if not path.exists():
                findings.append(f"missing file: {path}")
                continue
            try:
                findings.extend(self._analyze_c_text(path, path.read_text(encoding="utf-8", errors="ignore")))
            except OSError as exc:
                findings.append(f"cannot read {path}: {exc}")

        external = self._run_external_static_analyzers([path for path in source_paths if path.exists()])
        if external.returncode != 0 and (external.stdout.strip() or external.stderr.strip()):
            findings.append((external.stdout + "\n" + external.stderr).strip())
        syntax = self.run_generated_syntax_check([str(path) for path in source_paths if path.exists()])
        if syntax.returncode != 0:
            findings.append((syntax.stdout + "\n" + syntax.stderr).strip())
        status = "success" if not findings and external.returncode == 0 else "failed"
        payload = "\n".join(item for item in findings if item).strip()
        return ToolResult(status, 0 if status == "success" else 1, payload, payload, duration=(datetime.now() - start).total_seconds())

    def _resolve_project_file(self, path: str) -> Path:
        normalized = Path(str(path).replace("\\", "/"))
        if normalized.is_absolute():
            return normalized
        return (self.project_root / normalized).resolve()

    def _analyze_c_text(self, path: Path, text: str) -> List[str]:
        findings: List[str] = []
        if text.count("{") != text.count("}"):
            findings.append(f"{path}: unbalanced braces")
        if text.count("(") != text.count(")"):
            findings.append(f"{path}: unbalanced parentheses")
        if re.search(r"\bTODO\b|\bFIXME\b", text, re.IGNORECASE):
            findings.append(f"{path}: unresolved TODO/FIXME marker")
        if path.suffix == ".h" and not re.search(r"#pragma\s+once|#ifndef\s+\w+", text):
            findings.append(f"{path}: header lacks include guard or #pragma once")
        if re.search(r"\bHAL_[A-Za-z0-9_]+\s*\(", text) and "stm32f4xx_hal" not in text.lower():
            findings.append(f"{path}: HAL calls present without explicit HAL header include")
        return findings

    def _run_external_static_analyzers(self, source_paths: List[Path]) -> ToolResult:
        if not source_paths:
            return ToolResult("success", 0, "", "")
        cppcheck = shutil.which("cppcheck")
        if cppcheck:
            try:
                result = subprocess.run(
                    [cppcheck, "--enable=warning,style,performance,portability", "--std=c99", "--quiet", *[str(path) for path in source_paths]],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                return ToolResult("success" if result.returncode == 0 else "failed", result.returncode, result.stdout, result.stderr)
            except subprocess.TimeoutExpired as exc:
                output = "\n".join(part for part in [exc.stdout or "", exc.stderr or "", "cppcheck timed out after 60s"] if part)
                return ToolResult("failed", 124, output, output)
        return ToolResult("success", 0, "", json.dumps({"skipped": "cppcheck not found"}))

    def run_generated_syntax_check(self, files: List[str]) -> ToolResult:
        """Run fsyntax-only on generated C files when a C compiler is available."""
        compiler = shutil.which("arm-none-eabi-gcc") or shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            return ToolResult("success", 0, "", json.dumps({"skipped": "no C compiler found"}))
        c_files = [Path(path).resolve() for path in files if str(path).endswith(".c") and Path(path).exists()]
        if not c_files:
            return ToolResult("success", 0, "", "")
        include_dirs = sorted({str(path.parent) for path in c_files})
        include_dirs.extend(str(path.parent) for path in [Path(file).resolve() for file in files if str(file).endswith(".h") and Path(file).exists()])
        cmd = [compiler, "-fsyntax-only", "-std=c99", *[f"-I{path}" for path in sorted(set(include_dirs))], *[str(path) for path in c_files]]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(part for part in [exc.stdout or "", exc.stderr or "", "syntax check timed out after 60s"] if part)
            return ToolResult("failed", 124, output, output)
        return ToolResult("success" if result.returncode == 0 else "failed", result.returncode, result.stdout, result.stderr)

    def run_shell_tool(self, command: List[str], cwd: Optional[Path] = None, timeout: int = 60) -> ToolResult:
        """Run a bounded command tool without invoking a shell string."""
        start = datetime.now()
        if not command:
            return ToolResult("failed", 1, "", "empty command")
        allowed = {"cmake", "make", "ninja", "python", "py", "arm-none-eabi-gcc", "arm-none-eabi-objcopy", "openocd", "JLinkExe", "JLinkGDBServerCLExe"}
        executable = Path(command[0]).name
        if executable not in allowed:
            return ToolResult("failed", 1, "", f"command not allowed: {executable}")
        work_dir = (cwd or self.build_root).resolve()
        try:
            work_dir.relative_to(self.project_root)
        except ValueError:
            return ToolResult("failed", 1, "", f"cwd outside project: {work_dir}")
        try:
            result = subprocess.run(command, cwd=str(work_dir), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(part for part in [exc.stdout or "", exc.stderr or "", f"{executable} timed out after {timeout}s"] if part)
            return ToolResult("failed", 124, output, output, duration=(datetime.now() - start).total_seconds())
        return ToolResult("success" if result.returncode == 0 else "failed", result.returncode, result.stdout, result.stderr, duration=(datetime.now() - start).total_seconds())

    def validate_python_runtime(self, required_scripts: Optional[List[str]] = None) -> Tuple[bool, str]:
        """Check that the selected interpreter exists and required scripts are reachable."""
        python_path = Path(self.python_executable)
        if not python_path.exists():
            return False, f"Python interpreter not found: {self.python_executable}"
        missing_scripts = [
            script_name for script_name in (required_scripts or [])
            if not (self.build_root / script_name).exists()
        ]
        if missing_scripts:
            return False, "Missing runtime script(s): " + ", ".join(missing_scripts)
        return True, f"python={python_path} build_root={self.build_root}"

    def detect_build_system(self) -> Tuple[str, Path]:
        """Auto-detect build system."""
        root = self.build_root

        if (root / "CMakeLists.txt").exists():
            return ("cmake", root)

        software_dir = root / "software"
        if software_dir.exists():
            if (software_dir / "CMakeLists.txt").exists():
                return ("cmake", software_dir)
            if (software_dir / "build.py").exists():
                return ("python", software_dir)
            if (software_dir / "Build.ps1").exists():
                return ("powershell", software_dir)

        if (root / "Makefile").exists():
            return ("make", root)
        if (root / "build.py").exists():
            return ("python", root)
        if (root / "Build.ps1").exists():
            return ("powershell", root)

        for cmake_file in root.glob("**/CMakeLists.txt"):
            parent = cmake_file.parent
            if parent != root:
                return ("cmake", parent)

        return ("custom", root)

    async def run_cmake(self, work_dir: Path) -> BuildResult:
        """Run cmake."""
        start = datetime.now()
        try:
            result = await asyncio.to_thread(subprocess.run,
                ["cmake", "-B", str(self.build_dir), "-DCMAKE_BUILD_TYPE=Debug"],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            return BuildResult("failed", 124, exc.stdout or "", exc.stderr or f"cmake timed out after {BUILD_TIMEOUT_SECONDS}s", duration=(datetime.now() - start).total_seconds())
        return BuildResult(
            status="success" if result.returncode == 0 else "failed",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            errors=self._parse_errors(result.stderr),
            duration=(datetime.now() - start).total_seconds(),
        )

    async def run_make(self) -> BuildResult:
        """Run make."""
        start = datetime.now()
        try:
            result = await asyncio.to_thread(subprocess.run,
                ["make", "-C", str(self.build_dir), "-j4"],
                capture_output=True,
                text=True,
                timeout=BUILD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(part for part in [exc.stdout or "", exc.stderr or "", f"make timed out after {BUILD_TIMEOUT_SECONDS}s"] if part)
            return BuildResult("failed", 124, output, output, errors=self._parse_errors(output), duration=(datetime.now() - start).total_seconds())
        return BuildResult(
            status="success" if result.returncode == 0 else "failed",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            errors=self._parse_errors(result.stderr + result.stdout),
            duration=(datetime.now() - start).total_seconds(),
        )

    async def run_build(self) -> BuildResult:
        """Auto-detect and run build."""
        build_sys, work_dir = self.detect_build_system()
        if build_sys == "cmake":
            cmake_result = await self.run_cmake(work_dir)
            if cmake_result.status == "failed":
                return cmake_result
            return await self.run_make()
        if build_sys == "make":
            return await self.run_make()
        if build_sys == "python":
            start = datetime.now()
            ok, message = self.validate_python_runtime(["build.py"])
            if not ok:
                return BuildResult("failed", 1, "", message, duration=0.0)
            try:
                result = await asyncio.to_thread(subprocess.run,
                    [self.python_executable, "build.py"],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=BUILD_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                output = "\n".join(part for part in [exc.stdout or "", exc.stderr or "", f"build.py timed out after {BUILD_TIMEOUT_SECONDS}s"] if part)
                return BuildResult("failed", 124, output, output, errors=self._parse_errors(output), duration=(datetime.now() - start).total_seconds())
            combined_output = self._merge_build_output(work_dir, result.stdout, result.stderr)
            return BuildResult(
                status="success" if result.returncode == 0 else "failed",
                returncode=result.returncode,
                stdout=combined_output,
                stderr=combined_output,
                errors=self._parse_errors(combined_output),
                duration=(datetime.now() - start).total_seconds(),
            )
        if build_sys == "powershell":
            start = datetime.now()
            try:
                result = await asyncio.to_thread(subprocess.run,
                    ["powershell", "-ExecutionPolicy", "Bypass", "-File", "Build.ps1"],
                    cwd=str(work_dir),
                    capture_output=True,
                    text=True,
                    timeout=BUILD_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                output = "\n".join(part for part in [exc.stdout or "", exc.stderr or "", f"Build.ps1 timed out after {BUILD_TIMEOUT_SECONDS}s"] if part)
                return BuildResult("failed", 124, output, output, errors=self._parse_errors(output), duration=(datetime.now() - start).total_seconds())
            combined_output = self._merge_build_output(work_dir, result.stdout, result.stderr)
            return BuildResult(
                status="success" if result.returncode == 0 else "failed",
                returncode=result.returncode,
                stdout=combined_output,
                stderr=combined_output,
                errors=self._parse_errors(combined_output),
                duration=(datetime.now() - start).total_seconds(),
            )
        return BuildResult("failed", 1, "", "No build system found")

    async def run_flash(self, project: str) -> ToolResult:
        """Run the project flash utility for one project."""
        start = datetime.now()
        profile_report = self.board_profiles.validate_profile(os.environ.get("CARV_BOARD_PROFILE", ""))
        if not profile_report.get("valid", False):
            return ToolResult("failed", 1, "", MISSING_BOARD_PROFILE + ": " + "; ".join(profile_report.get("errors", [])), duration=0.0)
        flash_result = self.board_profiles.run_flash(profile_report.get("profile", {}))
        try:
            output_dir = self.project_root / "AI_support" / "outputs" / "runtime"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "flash_result.json").write_text(json.dumps(flash_result, indent=2), encoding="utf-8")
        except OSError:
            pass
        return ToolResult(
            "success" if flash_result.get("status") == "success" else flash_result.get("status", "failed"),
            int(flash_result.get("returncode", 1)),
            str(flash_result.get("stdout", "")),
            str(flash_result.get("stderr", "")),
            duration=(datetime.now() - start).total_seconds(),
        )

    async def run_auto_debug(self, project: str) -> ToolResult:
        """Run the project auto-debugger utility to diagnose HardFaults."""
        start = datetime.now()
        ok, message = self.validate_python_runtime(["auto_debug.py"])
        if not ok:
            return ToolResult("failed", 1, "", message, duration=0.0)
        try:
            result = await asyncio.to_thread(subprocess.run,
                [self.python_executable, "auto_debug.py", project],
                cwd=str(self.build_root),
                capture_output=True,
                text=True,
                timeout=AUTO_DEBUG_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult("failed", 124, exc.stdout or "", exc.stderr or f"auto_debug.py timed out after {AUTO_DEBUG_TIMEOUT_SECONDS}s", duration=(datetime.now() - start).total_seconds())
        return ToolResult(
            status="success" if result.returncode == 0 else "failed",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration=(datetime.now() - start).total_seconds(),
        )

    async def run_runtime_observe(self, dry_run: bool = True) -> ToolResult:
        """Run the project runtime observation utility."""
        start = datetime.now()
        profile_report = self.board_profiles.validate_profile(os.environ.get("CARV_BOARD_PROFILE", ""))
        if not profile_report.get("valid", False):
            return ToolResult("failed", 1, "", MISSING_BOARD_PROFILE + ": " + "; ".join(profile_report.get("errors", [])), duration=0.0)
        if not dry_run:
            serial_result = self.board_profiles.read_serial_runtime(profile_report.get("profile", {}))
            observation = serial_result.get("observation", {})
            try:
                output_dir = self.project_root / "AI_support" / "outputs" / "runtime"
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "runtime_observation.json").write_text(json.dumps(observation, indent=2), encoding="utf-8")
            except OSError:
                pass
            return ToolResult(
                serial_result.get("status", "failed"),
                int(serial_result.get("returncode", 1)),
                str(serial_result.get("stdout", "")),
                str(serial_result.get("stderr", "")),
                duration=(datetime.now() - start).total_seconds(),
            )
        ok, message = self.validate_python_runtime(["test.py"])
        if not ok:
            return ToolResult("failed", 1, "", message, duration=0.0)
        cmd = [self.python_executable, "test.py", "--skip-hw-check"]
        if dry_run:
            cmd.append("--dry-run")
        try:
            result = await asyncio.to_thread(subprocess.run,
                cmd,
                cwd=str(self.build_root),
                capture_output=True,
                text=True,
                timeout=RUNTIME_OBSERVE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            return ToolResult("failed", 124, exc.stdout or "", exc.stderr or f"test.py timed out after {RUNTIME_OBSERVE_TIMEOUT_SECONDS}s", duration=(datetime.now() - start).total_seconds())
        tool_result = ToolResult(
            status="success" if result.returncode == 0 else "failed",
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration=(datetime.now() - start).total_seconds(),
        )
        observation = self.board_profiles.parse_runtime_log(profile_report.get("profile", {}), tool_result.stdout, tool_result.stderr)
        try:
            output_dir = self.project_root / "AI_support" / "outputs" / "runtime"
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "runtime_observation.json").write_text(json.dumps(observation, indent=2), encoding="utf-8")
        except OSError:
            pass
        return tool_result

    def _parse_errors(self, output: str) -> List[BuildError]:
        """Parse compiler errors."""
        errors = []
        pattern = r"([^:\s]+):(\d+):(\d+): (error|warning): (.+)"
        for line in output.split("\n"):
            match = re.match(pattern, line)
            if match:
                errors.append(
                    BuildError(
                        file=match.group(1),
                        line=int(match.group(2)),
                        column=int(match.group(3)),
                        severity=match.group(4),
                        message=match.group(5),
                    )
                )
        return errors

    def _merge_build_output(self, work_dir: Path, stdout: str, stderr: str) -> str:
        """Merge subprocess output with persisted build logs when available."""
        chunks = [chunk.strip() for chunk in (stdout, stderr) if chunk and chunk.strip()]
        error_log = work_dir / "output" / "build_error.log"
        if error_log.exists():
            try:
                log_text = error_log.read_text(encoding="utf-8", errors="ignore").strip()
                if log_text:
                    chunks.append(log_text)
            except OSError:
                pass
        return "\n".join(chunks)
