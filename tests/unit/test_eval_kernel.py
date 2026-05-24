"""Unit tests for Eval kernel."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.infrastructure.eval.eval_kernel import (
    EvalKernel,
    PythonKernel,
    JavaScriptKernel,
    EvalSession,
    ExecutionResult,
    KernelVariable,
    KernelType,
)


class TestExecutionResult:
    """Tests for ExecutionResult."""

    def test_create_success(self):
        """Test creating successful result."""
        result = ExecutionResult(
            success=True,
            stdout="Hello",
            stderr="",
            result="Hello",
            execution_time_ms=10.0,
        )
        
        assert result.success is True
        assert result.stdout == "Hello"
        assert result.execution_time_ms == 10.0

    def test_create_error(self):
        """Test creating error result."""
        result = ExecutionResult(
            success=False,
            error="SyntaxError",
            stderr="traceback",
        )
        
        assert result.success is False
        assert result.error == "SyntaxError"


class TestKernelVariable:
    """Tests for KernelVariable."""

    def test_create_variable(self):
        """Test creating variable."""
        var = KernelVariable(
            name="x",
            type="int",
            value="42",
            repr="42",
        )
        
        assert var.name == "x"
        assert var.type == "int"
        assert var.value == "42"


class TestPythonKernel:
    """Tests for PythonKernel."""

    def test_create_kernel(self):
        """Test creating kernel."""
        kernel = PythonKernel()
        
        assert kernel.kernel_type == KernelType.PYTHON
        assert kernel._globals == {}

    @pytest.mark.asyncio
    async def test_execute_simple(self):
        """Test executing simple code."""
        kernel = PythonKernel()
        await kernel.start()
        
        result = await kernel.execute("x = 1 + 1")
        
        assert result.success is True
        assert result.execution_time_ms >= 0

    @pytest.mark.asyncio
    async def test_execute_print(self):
        """Test executing print statement."""
        kernel = PythonKernel()
        await kernel.start()
        
        result = await kernel.execute("print('Hello')")
        
        assert result.success is True
        assert "Hello" in result.stdout

    @pytest.mark.asyncio
    async def test_execute_error(self):
        """Test executing code with error."""
        kernel = PythonKernel()
        await kernel.start()
        
        result = await kernel.execute("raise ValueError('test')")
        
        assert result.success is False
        assert "ValueError" in result.stderr


class TestJavaScriptKernel:
    """Tests for JavaScriptKernel."""

    def test_create_kernel(self):
        """Test creating kernel."""
        kernel = JavaScriptKernel("node")
        
        assert kernel.kernel_type == KernelType.JAVASCRIPT
        assert kernel.runtime == "node"


class TestEvalSession:
    """Tests for EvalSession."""

    def test_create_session(self):
        """Test creating session."""
        session = EvalSession()
        
        assert len(session._kernels) == 0
        assert session._active_kernel is None

    @pytest.mark.asyncio
    async def test_add_kernel(self):
        """Test adding kernel."""
        session = EvalSession()
        kernel = PythonKernel()
        
        await session.add_kernel(kernel)
        
        assert KernelType.PYTHON in session._kernels
        assert session._active_kernel == KernelType.PYTHON

    def test_set_active(self):
        """Test setting active kernel."""
        session = EvalSession()
        
        session._kernels[KernelType.PYTHON] = PythonKernel()
        session._active_kernel = KernelType.PYTHON
        
        session.set_active(KernelType.PYTHON)
        
        assert session.active_kernel == KernelType.PYTHON

    @pytest.mark.asyncio
    async def test_execute_no_kernel(self):
        """Test executing with no kernel."""
        session = EvalSession()
        
        result = await session.execute("print(1)")
        
        assert result.success is False
        assert "No active kernel" in result.error
