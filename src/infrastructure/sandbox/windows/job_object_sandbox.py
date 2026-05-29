"""Windows Job Object sandbox implementation.

Features:
- Windows Job Objects for process isolation
- JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
- Memory and CPU limits
- Process tree termination
- No inherited handles
- No console inheritance
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# WINDOWS CONSTANTS (from WinAPI)
# =============================================================================

if platform.system() == "Windows":
    kernel32 = ctypes.windll.kernel32
    
    # Job Object Limit Flags
    JOB_OBJECT_LIMIT_PROCESS_TIME = 0x00000001
    JOB_OBJECT_LIMIT_JOB_TIME = 0x00000004
    JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
    JOB_OBJECT_LIMIT_AFFINITY = 0x00000010
    JOB_OBJECT_LIMIT_PRIORITY_CLASS = 0x00000020
    JOB_OBJECT_LIMIT_PRESERVE_JOB_TIME = 0x00000040
    JOB_OBJECT_LIMIT_SCHEDULING_CLASS = 0x00000080
    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    JOB_OBJECT_LIMIT_DIE_ON_OK_DLL = 0x00000400
    JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
    JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK = 0x00001000
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    JOB_OBJECT_LIMIT_WORKINGSET = 0x00000001
    JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
    
    # Job Object Info Classes
    JobObjectBasicLimitInformation = 2
    JobObjectExtendedLimitInformation = 9
    JobObjectCpuRateControlInformation = 15
    
    # CPU Rate Control
    JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x00000001
    JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x00000004
    
    # Process creation flags
    CREATE_NO_WINDOW = 0x08000000
    CREATE_SUSPENDED = 0x00000004
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    EXTENDED_STARTUPINFO_PRESENT = 0x00080000
    DETACHED_PROCESS = 0x00000008
    
    # Wait timeout
    INFINITE = 0xFFFFFFFF
    
    # Access rights
    PROCESS_ALL_ACCESS = 0x1F0FFF
    JOB_OBJECT_ALL_ACCESS = 0x1F0000 | 0xF


# =============================================================================
# SANDBOX CONFIGURATION
# =============================================================================


@dataclass
class JobObjectSandboxConfig:
    """Configuration for Windows Job Object sandbox."""
    
    # Memory limits (in MB)
    max_memory_mb: int = 512
    max_working_set_mb: int = 512
    
    # CPU limits
    max_cpu_percent: int = 50  # 0-100
    max_cpu_time_ms: int = 30000  # Max CPU time per job
    
    # Process limits
    max_processes: int = 5
    
    # Timeouts
    execution_timeout_seconds: float = 60.0
    
    # Environment
    env_whitelist: list[str] = field(default_factory=list)
    extra_env: dict[str, str] = field(default_factory=dict)
    
    # Working directory
    working_dir: str | None = None
    
    # Security flags
    kill_on_job_close: bool = True
    allow_breakaway: bool = False


@dataclass
class JobObjectExecutionResult:
    """Result from Job Object sandbox execution."""
    
    execution_id: str
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    killed: bool
    memory_used_mb: float
    cpu_time_ms: float
    wall_time_ms: float
    error: str | None = None


# =============================================================================
# JOB OBJECT WRAPPER
# =============================================================================


class WindowsJobObject:
    """Wrapper for Windows Job Object.
    
    Job Objects allow controlling groups of processes as a unit.
    Key feature: JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE ensures all
    child processes are killed when the job handle closes.
    """
    
    def __init__(self, name: str | None = None):
        if platform.system() != "Windows":
            raise RuntimeError("Windows Job Objects are only available on Windows")
        
        self._job_handle: int | None = None
        self._name = name or f"aisandbox_{os.getpid()}_{int(time.time() * 1000)}"
        self._process_handle: int | None = None
        
        self._create_job_object()
    
    def _create_job_object(self) -> None:
        """Create the Job Object."""
        kernel32 = ctypes.windll.kernel32
        
        # Create Job Object with name
        self._job_handle = kernel32.CreateJobObjectW(
            None,  # Security attributes
            f"aisandbox_{self._name}"  # Name
        )
        
        if not self._job_handle:
            error = ctypes.get_last_error()
            raise RuntimeError(f"Failed to create Job Object: {error}")
        
        logger.debug("Created Job Object: %s (handle=%d)", self._name, self._job_handle)
    
    def _set_limit(self, limit_flags: int, limit_info: bytes) -> bool:
        """Set a limit on the Job Object."""
        kernel32 = ctypes.windll.kernel32
        
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", ctypes.c_uint32),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", ctypes.c_size_t),
                ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                ("PriorityClass", ctypes.c_ulong),
                ("SchedulingClass", ctypes.c_ulong),
            ]
        
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", ctypes.c_void_p),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]
        
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        ctypes.memset(ctypes.byref(info), 0, ctypes.sizeof(info))
        
        # Set basic limit flags
        info.BasicLimitInformation.LimitFlags = limit_flags
        info.ProcessMemoryLimit = limit_info[0] if limit_info else 0
        info.JobMemoryLimit = limit_info[1] if len(limit_info) > 1 else 0
        
        result = kernel32.SetInformationJobObject(
            self._job_handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        
        return bool(result)
    
    def configure_limits(self, config: JobObjectSandboxConfig) -> bool:
        """Configure resource limits for the Job Object."""
        kernel32 = ctypes.windll.kernel32
        
        flags = 0
        
        # Kill on job close (critical for sandboxing)
        if config.kill_on_job_close:
            flags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        
        # Active process limit
        if config.max_processes > 0:
            flags |= JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        
        # Memory limits
        if config.max_memory_mb > 0:
            flags |= JOB_OBJECT_LIMIT_PROCESS_MEMORY
        
        if config.max_cpu_time_ms > 0:
            flags |= JOB_OBJECT_LIMIT_JOB_TIME
        
        # Prepare limit info
        memory_bytes = config.max_memory_mb * 1024 * 1024
        
        success = self._set_limit(flags, [memory_bytes, 0])
        
        if not success:
            logger.warning("Failed to set Job Object limits")
            return False
        
        # Set active process limit
        if config.max_processes > 0:
            class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("PerProcessUserTimeLimit", ctypes.c_int64),
                    ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", ctypes.c_uint32),
                    ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t),
                    ("ActiveProcessLimit", ctypes.c_size_t),
                    ("Affinity", ctypes.POINTER(ctypes.c_ulong)),
                    ("PriorityClass", ctypes.c_ulong),
                    ("SchedulingClass", ctypes.c_ulong),
                ]
            
            info = JOBOBJECT_BASIC_LIMIT_INFORMATION()
            info.LimitFlags = JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            info.ActiveProcessLimit = config.max_processes
            
            result = kernel32.SetInformationJobObject(
                self._job_handle,
                JobObjectBasicLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info)
            )
            
            if not result:
                logger.warning("Failed to set active process limit")
        
        # Set CPU rate limit
        if config.max_cpu_percent < 100:
            class JOBOBJECT_CPU_RATE_CONTROL_INFORMATION(ctypes.Structure):
                _fields_ = [
                    ("ControlFlags", ctypes.c_ulong),
                    ("CpuRate", ctypes.c_ulong),
                ]
            
            info = JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()
            info.ControlFlags = JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
            info.CpuRate = int(config.max_cpu_percent * 100)  # Convert to 10000 = 100%
            
            result = kernel32.SetInformationJobObject(
                self._job_handle,
                JobObjectCpuRateControlInformation,
                ctypes.byref(info),
                ctypes.sizeof(info)
            )
            
            if not result:
                logger.warning("Failed to set CPU rate limit")
        
        logger.debug("Configured Job Object limits: memory=%dMB, processes=%d, cpu=%d%%",
                     config.max_memory_mb, config.max_processes, config.max_cpu_percent)
        return True
    
    def assign_process(self, process_handle: int) -> bool:
        """Assign a process to this Job Object."""
        kernel32 = ctypes.windll.kernel32
        
        result = kernel32.AssignProcessToJobObject(
            self._job_handle,
            process_handle
        )
        
        return bool(result)
    
    def is_process_in_job(self, process_handle: int) -> bool:
        """Check if process is in this job."""
        kernel32 = ctypes.windll.kernel32
        
        result = kernel32.IsProcessInJob(
            process_handle,
            self._job_handle
        )
        
        return bool(result)
    
    def terminate(self, exit_code: int = 1) -> bool:
        """Terminate all processes in the Job Object."""
        kernel32 = ctypes.windll.kernel32
        
        result = kernel32.TerminateJobObject(
            self._job_handle,
            exit_code
        )
        
        return bool(result)
    
    def get_job_memory_info(self) -> dict[str, int]:
        """Get memory usage info for the job."""
        kernel32 = ctypes.windll.kernel32
        
        class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("TotalUserTime", ctypes.c_int64),
                ("TotalKernelTime", ctypes.c_int64),
                ("ThisPeriodTotalUserTime", ctypes.c_int64),
                ("ThisPeriodTotalKernelTime", ctypes.c_int64),
                ("TotalPageFaultCount", ctypes.c_ulong),
                ("TotalProcesses", ctypes.c_ulong),
                ("ActiveProcesses", ctypes.c_ulong),
                ("TotalTerminatedProcesses", ctypes.c_ulong),
            ]
        
        info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
        
        result = kernel32.QueryInformationJobObject(
            self._job_handle,
            0,  # JobObjectBasicAccountingInformation
            ctypes.byref(info),
            ctypes.sizeof(info),
            None
        )
        
        if result:
            return {
                "total_processes": info.TotalProcesses,
                "active_processes": info.ActiveProcesses,
                "terminated_processes": info.TotalTerminatedProcesses,
            }
        
        return {}
    
    def close(self) -> None:
        """Close the Job Object handle.
        
        Note: If JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE was set,
        all processes in the job will be terminated.
        """
        if self._job_handle:
            kernel32 = ctypes.windll.kernel32
            kernel32.CloseHandle(self._job_handle)
            self._job_handle = None
            logger.debug("Closed Job Object: %s", self._name)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
    
    @property
    def handle(self) -> int | None:
        """Get Job Object handle."""
        return self._job_handle


# =============================================================================
# JOB OBJECT SANDBOX
# =============================================================================


class JobObjectSandbox:
    """Windows Job Object-based sandbox.
    
    Isolation guarantees:
    - All child processes killed when job closes
    - Memory limits enforced
    - CPU limits enforced
    - Process count limits
    - Process tree termination on timeout
    - No console window inheritance
    """
    
    def __init__(self, config: JobObjectSandboxConfig | None = None):
        if platform.system() != "Windows":
            raise RuntimeError("JobObjectSandbox is only available on Windows")
        
        self.config = config or JobObjectSandboxConfig()
        self._job: WindowsJobObject | None = None
        self._process: subprocess.Popen | None = None
        self._execution_id: str | None = None
        self._start_time: float | None = None
    
    def _filter_environment(self) -> dict[str, str]:
        """Filter environment variables."""
        if not self.config.env_whitelist:
            # Block all - start minimal
            filtered = {
                "PATH": os.environ.get("PATH", "C:\\Windows\\system32;C:\\Windows"),
                "TEMP": os.environ.get("TEMP", "C:\\Temp"),
                "TMP": os.environ.get("TMP", "C:\\Temp"),
                "SYSTEMROOT": os.environ.get("SYSTEMROOT", "C:\\Windows"),
                "USERPROFILE": os.environ.get("USERPROFILE", ""),
                "USERNAME": os.environ.get("USERNAME", ""),
            }
        else:
            filtered = {}
            for key in self.config.env_whitelist:
                if key in os.environ:
                    filtered[key] = os.environ[key]
        
        # Add extra env vars
        filtered.update(self.config.extra_env)
        
        return filtered
    
    async def execute(
        self,
        command: str | list[str],
        input_data: str | bytes | None = None,
    ) -> JobObjectExecutionResult:
        """Execute command in Job Object sandbox.
        
        Args:
            command: Command to execute
            input_data: Optional stdin input
            
        Returns:
            JobObjectExecutionResult
        """
        import hashlib
        
        # Generate execution ID
        self._execution_id = hashlib.sha256(
            f"{os.getpid()}:{time.time()}:{command}".encode()
        ).hexdigest()[:16]
        
        self._start_time = time.monotonic()
        
        # Parse command
        if isinstance(command, str):
            cmd_list = shlex.split(command)
        else:
            cmd_list = list(command)
        
        # Create job object
        self._job = WindowsJobObject(self._execution_id)
        self._job.configure_limits(self.config)
        
        # Setup environment
        env = self._filter_environment()
        
        # Setup working directory
        cwd = self.config.working_dir or None
        
        # Create startup info (hidden window)
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags = subprocess.STARTF_USESHOWWINDOW
        startup_info.wShowWindow = subprocess.SW_HIDE
        
        # Process creation flags
        creation_flags = (
            CREATE_NO_WINDOW |
            DETACHED_PROCESS
        )
        
        stdout_data = b""
        stderr_data = b""
        exit_code = -1
        timed_out = False
        killed = False
        
        try:
            # Create process
            self._process = subprocess.Popen(
                cmd_list,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE if input_data else subprocess.DEVNULL,
                env=env,
                cwd=cwd,
                startupinfo=startup_info,
                creationflags=creation_flags,
                close_fds=True,
            )
            
            # Assign to job
            if not self._job.assign_process(self._process._handle):  # type: ignore
                logger.warning("Failed to assign process to job")
            
            # Write input if provided
            if input_data is not None:
                if isinstance(input_data, str):
                    input_data = input_data.encode("utf-8")
                self._process.stdin.write(input_data)  # type: ignore
                self._process.stdin.close()
            
            # Wait with timeout
            timeout = self.config.execution_timeout_seconds
            
            try:
                stdout_data, stderr_data = self._process.communicate(timeout=timeout)
                exit_code = self._process.returncode
            except subprocess.TimeoutExpired:
                timed_out = True
                killed = True
                
                # Terminate job (kills all processes)
                self._job.terminate()
                self._process.kill()
                
                # Get output
                stdout_data, stderr_data = self._process.communicate()
                exit_code = -1
            
        except Exception as e:
            logger.error("Job Object execution error: %s", e)
            stderr_data = str(e).encode("utf-8")
            exit_code = -1
        
        finally:
            # Calculate timing
            wall_time_ms = (time.monotonic() - self._start_time) * 1000
            
            # Get CPU time if possible
            cpu_time_ms = 0.0
            memory_mb = 0.0
            
            if self._process is not None and self._process.returncode is not None:
                try:
                    import psutil
                    proc = psutil.Process(self._process.pid)
                    cpu_time_ms = (proc.cpu_times().user + proc.cpu_times().system) * 1000
                    memory_mb = proc.memory_info().rss / (1024 * 1024)
                except ImportError:
                    pass
            
            # Close job (kills all processes due to KILL_ON_JOB_CLOSE)
            if self._job:
                self._job.close()
                self._job = None
            
            # Clean up process
            if self._process:
                try:
                    self._process.kill()
                except OSError:
                    pass
                self._process = None
        
        return JobObjectExecutionResult(
            execution_id=self._execution_id or "",
            exit_code=exit_code,
            stdout=stdout_data.decode("utf-8", errors="replace"),
            stderr=stderr_data.decode("utf-8", errors="replace"),
            timed_out=timed_out,
            killed=killed,
            memory_used_mb=memory_mb,
            cpu_time_ms=cpu_time_ms,
            wall_time_ms=wall_time_ms,
            error=None if exit_code == 0 else "Execution failed",
        )
    
    def terminate(self) -> None:
        """Terminate the sandbox."""
        if self._job:
            self._job.terminate()
            self._job.close()
            self._job = None
        
        if self._process:
            self._process.kill()
            self._process = None
    
    def is_running(self) -> bool:
        """Check if sandbox is running."""
        return self._process is not None and self._process.poll() is None
    
    @property
    def execution_id(self) -> str | None:
        """Get current execution ID."""
        return self._execution_id
    
    @property
    def pid(self) -> int | None:
        """Get subprocess PID."""
        return self._process.pid if self._process else None


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_job_object_sandbox(
    config: JobObjectSandboxConfig | None = None,
) -> JobObjectSandbox:
    """Create a Job Object sandbox instance."""
    return JobObjectSandbox(config)
