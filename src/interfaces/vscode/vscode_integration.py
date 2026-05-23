"""VS Code extension wiring to CLI/WebSocket server (Phase 10.5).

Wires VS Code extension to AI Support backend:
- CLI integration
- WebSocket connection
- Command handlers
- Debug session management
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VSCodeConfig:
    """VS Code extension configuration."""
    server_host: str = "localhost"
    server_port: int = 8765
    use_websocket: bool = True
    timeout_seconds: int = 30


class CLIIntegration:
    """CLI command integration."""
    
    def __init__(self) -> None:
        self._last_command = ""
    
    def execute_command(self, command: str, *args: str) -> dict[str, Any]:
        """Execute CLI command."""
        import subprocess
        
        cmd = ["python", "-m", "src.interfaces.cli.main", command] + list(args)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }


class WebSocketClient:
    """WebSocket client for VS Code extension."""
    
    def __init__(self, config: VSCodeConfig) -> None:
        self._config = config
        self._connected = False
    
    async def connect(self) -> bool:
        """Connect to server."""
        try:
            import websockets
            
            uri = f"ws://{self._config.server_host}:{self._config.server_port}"
            self._ws = await websockets.connect(uri)
            self._connected = True
            logger.info("Connected to server", uri=uri)
            return True
        except Exception as e:
            logger.error("Connection failed", error=str(e))
            return False
    
    async def send(self, message: dict[str, Any]) -> dict[str, Any]:
        """Send message to server."""
        if not self._connected:
            return {"error": "Not connected"}
        
        try:
            import websockets
            
            await self._ws.send(json.dumps(message))
            response = await asyncio.wait_for(
                self._ws.recv(),
                timeout=self._config.timeout_seconds,
            )
            return json.loads(response)
        except Exception as e:
            logger.error("Send failed", error=str(e))
            return {"error": str(e)}
    
    async def disconnect(self) -> None:
        """Disconnect from server."""
        if self._connected and hasattr(self, "_ws"):
            await self._ws.close()
        self._connected = False


class VSCodeIntegration:
    """VS Code extension backend integration.
    
    Phase 10.5: VS Code extension - Debug in IDE
    """
    
    def __init__(self, config: VSCodeConfig | None = None) -> None:
        self._config = config or VSCodeConfig()
        self._cli = CLIIntegration()
        self._ws_client = WebSocketClient(self._config)
    
    async def connect_to_server(self) -> bool:
        """Connect to AI Support server."""
        if self._config.use_websocket:
            return await self._ws_client.connect()
        return True
    
    async def disconnect_from_server(self) -> None:
        """Disconnect from server."""
        await self._ws_client.disconnect()
    
    async def debug_target(self, target_name: str) -> dict[str, Any]:
        """Start debug session for target."""
        if self._config.use_websocket:
            return await self._ws_client.send({
                "action": "debug_connect",
                "target": target_name,
            })
        else:
            return self._cli.execute_command("debug", "connect", target_name)
    
    async def flash_target(
        self,
        target_name: str,
        firmware_path: str,
    ) -> dict[str, Any]:
        """Flash target with firmware."""
        if self._config.use_websocket:
            return await self._ws_client.send({
                "action": "flash",
                "target": target_name,
                "firmware": firmware_path,
            })
        else:
            return self._cli.execute_command(
                "flash",
                target_name,
                "--firmware", firmware_path,
            )
    
    async def get_target_status(self, target_name: str) -> dict[str, Any]:
        """Get target status."""
        if self._config.use_websocket:
            return await self._ws_client.send({
                "action": "target_status",
                "target": target_name,
            })
        else:
            result = self._cli.execute_command("debug", "status", target_name)
            return {"status": "ok", "data": result}
    
    async def trace_target(
        self,
        target_name: str,
        duration_seconds: int = 10,
    ) -> dict[str, Any]:
        """Start trace session."""
        if self._config.use_websocket:
            return await self._ws_client.send({
                "action": "trace_start",
                "target": target_name,
                "duration": duration_seconds,
            })
        else:
            return self._cli.execute_command(
                "trace",
                target_name,
                "--duration", str(duration_seconds),
            )


# Global integration
_vscode_integration: VSCodeIntegration | None = None


def get_vscode_integration(config: VSCodeConfig | None = None) -> VSCodeIntegration:
    """Get VS Code integration."""
    global _vscode_integration
    if _vscode_integration is None:
        _vscode_integration = VSCodeIntegration(config)
    return _vscode_integration


if __name__ == "__main__":
    integration = get_vscode_integration()
    
    print("VS Code Extension Integration")
    print("=" * 40)
    print("Commands:")
    print("  - debug_target(target_name)")
    print("  - flash_target(target_name, firmware)")
    print("  - trace_target(target_name, duration)")
