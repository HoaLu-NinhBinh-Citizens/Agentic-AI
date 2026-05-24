"""Persistent code kernel (Jupyter-like).

Provides:
- Persistent execution state
- Multi-language support
- Variable persistence
- Code cell management
- Rich output rendering
- Kernel interrupts
"""

from __future__ import annotations

import asyncio
import io
import json
import sys
import traceback
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class KernelState(Enum):
    """Kernel states."""
    IDLE = "idle"
    BUSY = "busy"
    STARTING = "starting"
    STOPPING = "stopping"
    DEAD = "dead"


class KernelLanguage(Enum):
    """Supported languages."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BASH = "bash"


@dataclass
class CodeCell:
    """A code cell."""
    id: str
    code: str
    execution_count: int = 0
    outputs: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    execution_time_ms: float = 0.0


@dataclass
class KernelOutput:
    """Output from kernel execution."""
    output_type: str  # stream, execute_result, error, display_data
    text: str = ""
    data: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)
    ename: str = ""  # Error name
    evalue: str = ""  # Error value
    traceback: list[str] = field(default_factory=list)


@dataclass
class ExecutionResult:
    """Result of code execution."""
    success: bool
    outputs: list[KernelOutput]
    execution_count: int
    execution_time_ms: float


class VariablesStore:
    """Persistent variable storage."""
    
    def __init__(self):
        self._variables: dict[str, Any] = {}
        self._history: list[tuple[str, Any]] = []
    
    def set(self, name: str, value: Any) -> None:
        """Set a variable."""
        self._variables[name] = value
        self._history.append((name, value))
    
    def get(self, name: str) -> Any:
        """Get a variable."""
        return self._variables.get(name)
    
    def delete(self, name: str) -> bool:
        """Delete a variable."""
        if name in self._variables:
            del self._variables[name]
            return True
        return False
    
    def list_all(self) -> dict[str, type]:
        """List all variables with types."""
        return {name: type(value).__name__ for name, value in self._variables.items()}
    
    def clear(self) -> None:
        """Clear all variables."""
        self._variables.clear()
    
    def to_dict(self) -> dict:
        """Serialize variables."""
        return {
            name: repr(value) for name, value in self._variables.items()
        }
    
    def from_dict(self, data: dict) -> None:
        """Deserialize variables."""
        # Note: This is limited - actual objects won't survive serialization
        pass


class OutputCapture:
    """Capture stdout/stderr."""
    
    def __init__(self):
        self._stdout_buffer = io.StringIO()
        self._stderr_buffer = io.StringIO()
        self._old_stdout = None
        self._old_stderr = None
    
    def __enter__(self):
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = self._stdout_buffer
        sys.stderr = self._stderr_buffer
        return self
    
    def __exit__(self, *args):
        sys.stdout = self._old_stdout
        sys.stderr = self._old_stderr
    
    @property
    def stdout(self) -> str:
        return self._stdout_buffer.getvalue()
    
    @property
    def stderr(self) -> str:
        return self._stderr_buffer.getvalue()
    
    def clear(self) -> None:
        self._stdout_buffer = io.StringIO()
        self._stderr_buffer = io.StringIO()


class PersistentKernel:
    """Persistent Jupyter-like kernel."""
    
    def __init__(self, language: KernelLanguage = KernelLanguage.PYTHON):
        self.language = language
        self.state = KernelState.IDLE
        self.variables = VariablesStore()
        
        # Execution state
        self._execution_count = 0
        self._cells: dict[str, CodeCell] = {}
        self._interrupted = False
        self._background_tasks: list[asyncio.Task] = []
        
        # Configuration
        self._timeout = 30.0
        self._capture_output = True
        
        # Hooks
        self._pre_execute_hooks: list = []
        self._post_execute_hooks: list = []
    
    async def start(self) -> None:
        """Start the kernel."""
        self.state = KernelState.STARTING
        
        # Initialize based on language
        if self.language == KernelLanguage.PYTHON:
            # Python is always available
            pass
        elif self.language == KernelLanguage.JAVASCRIPT:
            # Check for node
            import shutil
            if not shutil.which("node"):
                raise RuntimeError("Node.js not installed")
        
        self.state = KernelState.IDLE
    
    async def stop(self) -> None:
        """Stop the kernel."""
        self.state = KernelState.STOPPING
        
        # Cancel background tasks
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        self.state = KernelState.DEAD
    
    async def execute(
        self,
        code: str,
        cell_id: str | None = None,
        store_variables: bool = True,
    ) -> ExecutionResult:
        """Execute code."""
        import time
        start = time.time()
        
        if self.state == KernelState.DEAD:
            return ExecutionResult(
                success=False,
                outputs=[KernelOutput(
                    output_type="error",
                    ename="KernelDead",
                    evalue="Kernel is not running",
                )],
                execution_count=self._execution_count,
                execution_time_ms=0,
            )
        
        self.state = KernelState.BUSY
        self._interrupted = False
        
        # Run pre-execute hooks
        for hook in self._pre_execute_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(code)
                else:
                    hook(code)
            except:
                pass
        
        outputs = []
        success = True
        
        # Create cell
        cell_id = cell_id or str(uuid.uuid4())
        self._execution_count += 1
        
        try:
            if self.language == KernelLanguage.PYTHON:
                outputs = await self._execute_python(code, store_variables)
            elif self.language == KernelLanguage.JAVASCRIPT:
                outputs = await self._execute_javascript(code)
            elif self.language == KernelLanguage.BASH:
                outputs = await self._execute_bash(code)
        
        except asyncio.CancelledError:
            success = False
            outputs.append(KernelOutput(
                output_type="error",
                ename="Interrupted",
                evalue="Execution was interrupted",
            ))
        
        except Exception as e:
            success = False
            outputs.append(KernelOutput(
                output_type="error",
                ename=type(e).__name__,
                evalue=str(e),
                traceback=traceback.format_exc().split("\n"),
            ))
        
        execution_time_ms = (time.time() - start) * 1000
        
        # Store cell
        self._cells[cell_id] = CodeCell(
            id=cell_id,
            code=code,
            execution_count=self._execution_count,
            outputs=outputs,
            execution_time_ms=execution_time_ms,
        )
        
        self.state = KernelState.IDLE
        
        # Run post-execute hooks
        for hook in self._post_execute_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(code, outputs)
                else:
                    hook(code, outputs)
            except:
                pass
        
        return ExecutionResult(
            success=success,
            outputs=outputs,
            execution_count=self._execution_count,
            execution_time_ms=execution_time_ms,
        )
    
    async def _execute_python(
        self,
        code: str,
        store_variables: bool,
    ) -> list[KernelOutput]:
        """Execute Python code."""
        outputs = []
        
        with OutputCapture() as capture:
            try:
                # Compile and execute
                compiled = compile(code, "<kernel>", "exec")
                
                # Create namespace with variables
                namespace = self.variables._variables.copy()
                
                # Execute
                exec(compiled, namespace)
                
                # Update variables
                if store_variables:
                    # Find new variables
                    for name, value in namespace.items():
                        if name not in ("__builtins__", "__name__", "__doc__"):
                            self.variables.set(name, value)
                
                # Capture stdout
                if capture.stdout:
                    outputs.append(KernelOutput(
                        output_type="stream",
                        text=capture.stdout,
                        metadata={"name": "stdout"},
                    ))
                
                # Return result if any
                if compiled.co_names and namespace.get("_") is not None:
                    result = namespace.get("_")
                    if result is not None:
                        outputs.append(KernelOutput(
                            output_type="execute_result",
                            text=repr(result),
                            metadata={"text/plain": repr(result)},
                        ))
                
            except Exception as e:
                if capture.stderr:
                    outputs.append(KernelOutput(
                        output_type="stream",
                        text=capture.stderr,
                        metadata={"name": "stderr"},
                    ))
                
                outputs.append(KernelOutput(
                    output_type="error",
                    ename=type(e).__name__,
                    evalue=str(e),
                    traceback=traceback.format_exc().split("\n"),
                ))
        
        return outputs
    
    async def _execute_javascript(self, code: str) -> list[KernelOutput]:
        """Execute JavaScript code."""
        import tempfile
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
            f.write(code)
            temp_path = f.name
        
        try:
            proc = await asyncio.create_subprocess_exec(
                "node", temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._timeout,
            )
            
            outputs = []
            
            if stdout:
                outputs.append(KernelOutput(
                    output_type="stream",
                    text=stdout.decode(),
                    metadata={"name": "stdout"},
                ))
            
            if stderr:
                outputs.append(KernelOutput(
                    output_type="stream",
                    text=stderr.decode(),
                    metadata={"name": "stderr"},
                ))
            
            if proc.returncode != 0 and not stderr:
                outputs.append(KernelOutput(
                    output_type="error",
                    ename="Error",
                    evalue=f"Exit code: {proc.returncode}",
                ))
            
            return outputs
            
        finally:
            Path(temp_path).unlink(missing_ok=True)
    
    async def _execute_bash(self, code: str) -> list[KernelOutput]:
        """Execute bash code."""
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", code,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=self._timeout,
        )
        
        outputs = []
        
        if stdout:
            outputs.append(KernelOutput(
                output_type="stream",
                text=stdout.decode(),
                metadata={"name": "stdout"},
            ))
        
        if stderr:
            outputs.append(KernelOutput(
                output_type="stream",
                text=stderr.decode(),
                metadata={"name": "stderr"},
            ))
        
        return outputs
    
    def interrupt(self) -> None:
        """Interrupt execution."""
        self._interrupted = True
        # Note: Full interruption requires signal handling
    
    def add_pre_execute_hook(self, hook) -> None:
        """Add a pre-execute hook."""
        self._pre_execute_hooks.append(hook)
    
    def add_post_execute_hook(self, hook) -> None:
        """Add a post-execute hook."""
        self._post_execute_hooks.append(hook)
    
    def get_cell(self, cell_id: str) -> CodeCell | None:
        """Get a cell by ID."""
        return self._cells.get(cell_id)
    
    def get_history(self) -> list[CodeCell]:
        """Get execution history."""
        return list(self._cells.values())
    
    def reset_history(self) -> None:
        """Clear execution history."""
        self._cells.clear()
        self._execution_count = 0


class KernelManager:
    """Manage multiple kernels."""
    
    def __init__(self):
        self._kernels: dict[str, PersistentKernel] = {}
    
    def create_kernel(
        self,
        kernel_id: str | None = None,
        language: KernelLanguage = KernelLanguage.PYTHON,
    ) -> PersistentKernel:
        """Create a new kernel."""
        kernel_id = kernel_id or str(uuid.uuid4())
        
        kernel = PersistentKernel(language)
        self._kernels[kernel_id] = kernel
        
        return kernel
    
    def get_kernel(self, kernel_id: str) -> PersistentKernel | None:
        """Get a kernel by ID."""
        return self._kernels.get(kernel_id)
    
    def list_kernels(self) -> list[str]:
        """List all kernel IDs."""
        return list(self._kernels.keys())
    
    async def shutdown_kernel(self, kernel_id: str) -> bool:
        """Shutdown a kernel."""
        kernel = self._kernels.get(kernel_id)
        if kernel:
            await kernel.stop()
            del self._kernels[kernel_id]
            return True
        return False
    
    async def shutdown_all(self) -> None:
        """Shutdown all kernels."""
        for kernel_id in list(self._kernels.keys()):
            await self.shutdown_kernel(kernel_id)


# Convenience functions

async def quick_kernel() -> PersistentKernel:
    """Create a quick Python kernel."""
    kernel = PersistentKernel(KernelLanguage.PYTHON)
    await kernel.start()
    return kernel


async def execute_in_kernel(
    code: str,
    kernel: PersistentKernel | None = None,
) -> ExecutionResult:
    """Execute code in a temporary kernel."""
    if kernel is None:
        kernel = await quick_kernel()
    
    try:
        return await kernel.execute(code)
    finally:
        await kernel.stop()
