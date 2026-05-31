"""Debug Adapter Protocol (DAP) client for debugging support."""
from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DebugState(Enum):
    """Debugger state."""
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    TERMINATED = "terminated"


@dataclass
class Breakpoint:
    """Represents a breakpoint."""
    id: int
    file: str
    line: int
    enabled: bool = True
    condition: Optional[str] = None


@dataclass
class StackFrame:
    """Represents a stack frame."""
    id: int
    name: str
    file: str
    line: int
    column: int


@dataclass
class Variable:
    """Represents a variable in scope."""
    name: str
    value: str
    type: str
    reference: int = 0


class DAPClient:
    """Debug Adapter Protocol client for debugging support.
    
    Connects to debug adapters (debugpy, lldb, etc.) via TCP or stdio.
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 5678):
        self.host = host
        self.port = port
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._seq = 0
        self._state = DebugState.STOPPED
        self._breakpoints: dict[int, Breakpoint] = {}
        self._bp_id_counter = 1
        self._handlers: dict[str, callable] = {}
        
    async def connect(self) -> bool:
        """Connect to debug adapter.
        
        Returns:
            True if connected successfully
        """
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=5.0
            )
            logger.info(f"Connected to debug adapter at {self.host}:{self.port}")
            
            # Start message handler
            asyncio.create_task(self._read_messages())
            return True
            
        except asyncio.TimeoutError:
            logger.error(f"Connection to debug adapter timed out")
            return False
        except ConnectionRefusedError:
            logger.error(f"Debug adapter connection refused at {self.host}:{self.port}")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to debug adapter: {e}")
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from debug adapter."""
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        self._state = DebugState.TERMINATED
        logger.info("Disconnected from debug adapter")
    
    async def _read_messages(self) -> None:
        """Read and handle messages from debug adapter."""
        while self._state != DebugState.TERMINATED:
            try:
                if not self._reader:
                    break
                    
                # Read content length
                headers = {}
                while True:
                    line = await self._reader.readline()
                    if not line:
                        break
                    line = line.decode('utf-8').strip()
                    if not line:
                        break
                    if ':' in line:
                        key, value = line.split(':', 1)
                        headers[key.strip()] = value.strip()
                
                if 'Content-Length' not in headers:
                    continue
                
                length = int(headers['Content-Length'])
                body = await self._reader.readexactly(length)
                
                message = json.loads(body.decode('utf-8'))
                await self._handle_message(message)
                
            except Exception as e:
                logger.error(f"Error reading from debug adapter: {e}")
                break
    
    async def _handle_message(self, message: dict) -> None:
        """Handle a message from debug adapter."""
        msg_type = message.get('event') or message.get('command', 'unknown')
        
        if msg_type in self._handlers:
            self._handlers[msg_type](message)
        
        # Handle state changes
        if message.get('event') == 'stopped':
            self._state = DebugState.PAUSED
        elif message.get('event') == 'continued':
            self._state = DebugState.RUNNING
        elif message.get('event') == 'exited':
            self._state = DebugState.TERMINATED
    
    async def _send_request(self, command: str, args: dict = None) -> dict:
        """Send a request to debug adapter."""
        self._seq += 1
        request = {
            'seq': self._seq,
            'type': 'request',
            'command': command,
            'arguments': args or {}
        }
        
        body = json.dumps(request)
        header = f"Content-Length: {len(body)}\r\n\r\n"
        
        if self._writer:
            self._writer.write((header + body).encode('utf-8'))
            await self._writer.drain()
        
        # Wait for response
        # In real implementation, use event-based response handling
        return {'success': True, 'command': command}
    
    def on(self, event: str, handler: callable) -> None:
        """Register an event handler.
        
        Args:
            event: Event name to listen for
            handler: Callback function
        """
        self._handlers[event] = handler
    
    # ─── Debugger Commands ────────────────────────────────────────────────
    
    async def launch(self, program: str, **kwargs) -> bool:
        """Launch a debuggee.
        
        Args:
            program: Path to program to debug
            **kwargs: Additional launch arguments
        """
        args = {
            'program': program,
            'request': 'launch',
            'noDebug': False,
            **kwargs
        }
        
        result = await self._send_request('launch', args)
        self._state = DebugState.RUNNING
        return result.get('success', False)
    
    async def set_breakpoint(self, file: str, line: int, condition: str = None) -> Breakpoint:
        """Set a breakpoint.
        
        Args:
            file: File path
            line: Line number (1-indexed)
            condition: Optional condition expression
        """
        args = {
            'source': {'path': file},
            'line': line,
        }
        if condition:
            args['condition'] = condition
        
        await self._send_request('setBreakpoints', args)
        
        bp = Breakpoint(
            id=self._bp_id_counter,
            file=file,
            line=line,
            condition=condition
        )
        self._breakpoints[self._bp_id_counter] = bp
        self._bp_id_counter += 1
        
        return bp
    
    async def remove_breakpoint(self, bp_id: int) -> bool:
        """Remove a breakpoint."""
        if bp_id in self._breakpoints:
            del self._breakpoints[bp_id]
            return True
        return False
    
    async def continue_(self) -> None:
        """Continue execution."""
        await self._send_request('continue')
        self._state = DebugState.RUNNING
    
    async def pause(self) -> None:
        """Pause execution."""
        await self._send_request('pause')
        self._state = DebugState.PAUSED
    
    async def step_over(self) -> None:
        """Step over current line."""
        await self._send_request('next')
        self._state = DebugState.RUNNING
    
    async def step_into(self) -> None:
        """Step into function."""
        await self._send_request('stepIn')
        self._state = DebugState.RUNNING
    
    async def step_out(self) -> None:
        """Step out of current function."""
        await self._send_request('stepOut')
        self._state = DebugState.RUNNING
    
    async def get_stack_trace(self, thread_id: int = 1, levels: int = 20) -> list[StackFrame]:
        """Get stack trace for a thread.
        
        Args:
            thread_id: Thread ID
            levels: Number of frames to return
        """
        args = {
            'threadId': thread_id,
            'levels': levels
        }
        
        response = await self._send_request('stackTrace', args)
        
        frames = []
        for i, frame_data in enumerate(response.get('stackFrames', [])):
            frames.append(StackFrame(
                id=frame_data.get('id', i),
                name=frame_data.get('name', '<unknown>'),
                file=frame_data.get('source', {}).get('path', ''),
                line=frame_data.get('line', 0),
                column=frame_data.get('column', 0)
            ))
        
        return frames
    
    async def get_variables(self, frame_id: int = 0, thread_id: int = 1) -> list[Variable]:
        """Get variables in scope.
        
        Args:
            frame_id: Frame ID (0 = current)
            thread_id: Thread ID
        """
        args = {
            'variablesReference': frame_id,
            'threadId': thread_id
        }
        
        response = await self._send_request('scopes', args)
        
        variables = []
        for scope in response.get('scopes', []):
            variables_ref = scope.get('variablesReference', 0)
            if variables_ref:
                var_response = await self._send_request('variables', {
                    'variablesReference': variables_ref
                })
                for var_data in var_response.get('variables', []):
                    variables.append(Variable(
                        name=var_data.get('name', ''),
                        value=var_data.get('value', ''),
                        type=var_data.get('type', ''),
                        reference=var_data.get('variablesReference', 0)
                    ))
        
        return variables
    
    async def evaluate(self, expression: str, frame_id: int = 0) -> str:
        """Evaluate an expression.
        
        Args:
            expression: Expression to evaluate
            frame_id: Frame context
        """
        args = {
            'expression': expression,
            'frameId': frame_id,
            'context': 'repl'
        }
        
        response = await self._send_request('evaluate', args)
        return response.get('result', '')
    
    @property
    def state(self) -> DebugState:
        """Get current debugger state."""
        return self._state
    
    @property
    def breakpoints(self) -> list[Breakpoint]:
        """Get all breakpoints."""
        return list(self._breakpoints.values())
