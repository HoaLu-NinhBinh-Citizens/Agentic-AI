"""Eval kernel for code execution.

Provides interactive code execution with:
- Persistent Python kernel
- Bun/Node.js kernel
- Tool calling from within kernels
- Variable inspection
- Multi-language support
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from enum import Enum
from io import StringIO
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4


class KernelType(Enum):
    """Supported kernel types."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BUN = "bun"


@dataclass
class ExecutionResult:
    """Result of code execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0


@dataclass
class KernelVariable:
    """A variable in the kernel."""
    name: str
    type: str
    value: str
    repr: str


class EvalKernel:
    """Base class for eval kernels."""
    
    def __init__(self, kernel_type: KernelType):
        self.kernel_type = kernel_type
        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._pending: dict[str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._variables: dict[str, KernelVariable] = {}
    
    async def start(self) -> None:
        """Start the kernel."""
        raise NotImplementedError
    
    async def execute(self, code: str) -> ExecutionResult:
        """Execute code and return result."""
        raise NotImplementedError
    
    async def get_variables(self) -> list[KernelVariable]:
        """Get current variables."""
        raise NotImplementedError
    
    async def interrupt(self) -> None:
        """Interrupt current execution."""
        raise NotImplementedError
    
    async def shutdown(self) -> None:
        """Shutdown the kernel."""
        if self._reader_task:
            self._reader_task.cancel()
        if self._process:
            self._process.terminate()
            await self._process.wait()


class PythonKernel(EvalKernel):
    """Python execution kernel using asyncio.
    
    Provides:
    - Async execution
    - Stdout/stderr capture
    - Exception handling
    - Variable inspection via locals()
    """
    
    def __init__(self):
        super().__init__(KernelType.PYTHON)
        self._globals: dict = {}
        self._locals: dict = {}
        self._execution_lock = asyncio.Lock()
    
    async def start(self) -> None:
        """Start the kernel."""
        self._running = True
    
    async def execute(self, code: str) -> ExecutionResult:
        """Execute Python code."""
        import time
        start = time.time()
        
        async with self._execution_lock:
            stdout_capture = StringIO()
            stderr_capture = StringIO()
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            
            try:
                sys.stdout = stdout_capture
                sys.stderr = stderr_capture
                
                # Run in executor
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: exec(code, self._globals, self._locals)
                )
                
                stdout = stdout_capture.getvalue()
                stderr = stderr_capture.getvalue()
                
                # Get result
                result = self._locals.get("_result", None)
                
                return ExecutionResult(
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                    result=result,
                    execution_time_ms=(time.time() - start) * 1000,
                )
                
            except Exception as e:
                import traceback
                return ExecutionResult(
                    success=False,
                    error=str(e),
                    stderr=traceback.format_exc(),
                    execution_time_ms=(time.time() - start) * 1000,
                )
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
    
    async def get_variables(self) -> list[KernelVariable]:
        """Get current variables."""
        variables = []
        
        for name, value in self._locals.items():
            if not name.startswith("_"):
                try:
                    variables.append(KernelVariable(
                        name=name,
                        type=type(value).__name__,
                        value=repr(value)[:100],
                        repr=repr(value),
                    ))
                except:
                    pass
        
        return variables
    
    async def interrupt(self) -> None:
        """Interrupt current execution."""
        pass


class JavaScriptKernel(EvalKernel):
    """JavaScript/Bun execution kernel.
    
    Uses Node.js or Bun for execution.
    Supports:
    - Async/await
    - ES modules
    - Tool calls via IPC
    """
    
    def __init__(self, runtime: str = "node"):
        super().__init__(
            KernelType.BUN if runtime == "bun" else KernelType.JAVASCRIPT
        )
        self.runtime = runtime
        self._variables: dict[str, Any] = {}
    
    async def start(self) -> None:
        """Start the JS engine."""
        self._running = True
    
    async def execute(self, code: str) -> ExecutionResult:
        """Execute JavaScript code."""
        import time
        start = time.time()
        
        try:
            # Create a temporary script
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(f"""
const logs = [];
const origLog = console.log;
console.log = (...args) => logs.push(args.join(' '));

try {{
    {code}
}} catch(e) {{
    console.error(e.message);
}}

console.log = origLog;
console.log(JSON.stringify({{ logs }}));
""")
                temp_path = f.name
            
            # Run with node/bun
            proc = await asyncio.create_subprocess_exec(
                self.runtime,
                temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await proc.communicate()
            
            # Cleanup
            Path(temp_path).unlink(missing_ok=True)
            
            stdout_text = stdout.decode() if stdout else ""
            stderr_text = stderr.decode() if stderr else ""
            
            return ExecutionResult(
                success=proc.returncode == 0,
                stdout=stdout_text,
                stderr=stderr_text,
                execution_time_ms=(time.time() - start) * 1000,
            )
            
        except FileNotFoundError:
            return ExecutionResult(
                success=False,
                error=f"{self.runtime} not found",
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start) * 1000,
            )
    
    async def get_variables(self) -> list[KernelVariable]:
        """Get current variables (limited in JS)."""
        return []
    
    async def interrupt(self) -> None:
        """Interrupt execution."""
        if self._process:
            self._process.terminate()


class EvalSession:
    """A multi-kernel eval session."""
    
    def __init__(self):
        self._kernels: dict[KernelType, EvalKernel] = {}
        self._active_kernel: KernelType | None = None
        self._history: list[tuple[KernelType, str, ExecutionResult]] = []
    
    async def add_kernel(self, kernel: EvalKernel) -> None:
        """Add a kernel to the session."""
        await kernel.start()
        self._kernels[kernel.kernel_type] = kernel
        if self._active_kernel is None:
            self._active_kernel = kernel.kernel_type
    
    async def execute(
        self,
        code: str,
        kernel_type: KernelType | None = None,
    ) -> ExecutionResult:
        """Execute code in the specified or active kernel."""
        kt = kernel_type or self._active_kernel
        if kt is None or kt not in self._kernels:
            return ExecutionResult(
                success=False,
                error="No active kernel",
            )
        
        result = await self._kernels[kt].execute(code)
        
        self._history.append((kt, code, result))
        
        return result
    
    def set_active(self, kernel_type: KernelType) -> None:
        """Set the active kernel."""
        if kernel_type in self._kernels:
            self._active_kernel = kernel_type
    
    async def get_variables(self) -> dict[KernelType, list[KernelVariable]]:
        """Get variables from all kernels."""
        return {
            kt: await kernel.get_variables()
            for kt, kernel in self._kernels.items()
        }
    
    async def shutdown_all(self) -> None:
        """Shutdown all kernels."""
        for kernel in self._kernels.values():
            await kernel.shutdown()
        self._kernels.clear()
    
    @property
    def active_kernel(self) -> KernelType | None:
        """Get the active kernel type."""
        return self._active_kernel
    
    @property
    def available_kernels(self) -> list[KernelType]:
        """Get available kernel types."""
        return list(self._kernels.keys())
    
    @property
    def history(self) -> list[tuple[KernelType, str, ExecutionResult]]:
        """Get execution history."""
        return self._history


# Convenience functions

async def create_python_session() -> EvalSession:
    """Create a session with Python kernel."""
    session = EvalSession()
    kernel = PythonKernel()
    await session.add_kernel(kernel)
    return session


async def create_js_session(runtime: str = "bun") -> EvalSession:
    """Create a session with JavaScript kernel."""
    session = EvalSession()
    kernel = JavaScriptKernel(runtime)
    await session.add_kernel(kernel)
    return session


async def create_dual_session(runtime: str = "bun") -> EvalSession:
    """Create a session with both Python and JS kernels."""
    session = EvalSession()
    
    py_kernel = PythonKernel()
    await session.add_kernel(py_kernel)
    
    js_kernel = JavaScriptKernel(runtime)
    await session.add_kernel(js_kernel)
    
    return session
