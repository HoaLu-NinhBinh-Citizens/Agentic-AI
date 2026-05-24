"""SSH tunneling and remote execution.

Provides:
- SSH connection management
- Port forwarding
- Remote command execution
- File transfer (SFTP)
- Reverse tunnels
- Jump hosts
"""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class SSHError(Exception):
    """SSH operation error."""
    pass


class AuthMethod(Enum):
    """Authentication methods."""
    PASSWORD = "password"
    KEY = "key"
    AGENT = "agent"


@dataclass
class SSHConfig:
    """SSH connection configuration."""
    host: str
    port: int = 22
    username: str = ""
    password: str | None = None
    key_path: Path | None = None
    auth_method: AuthMethod = AuthMethod.KEY
    timeout: float = 30.0
    compress: bool = True
    agent_forward: bool = False


@dataclass
class PortForward:
    """Port forwarding configuration."""
    local_port: int
    remote_host: str
    remote_port: int
    bind_address: str = "localhost"


@dataclass
class RemoteResult:
    """Result of remote command execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


class SSHConnection:
    """SSH connection wrapper.
    
    Uses paramiko for SSH operations.
    """
    
    def __init__(self, config: SSHConfig):
        self.config = config
        self._client = None
        self._transport = None
        self._sftp = None
    
    async def connect(self) -> None:
        """Establish SSH connection."""
        try:
            import paramiko
            
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect
            connect_kwargs = {
                "hostname": self.config.host,
                "port": self.config.port,
                "timeout": self.config.timeout,
                "compress": self.config.compress,
            }
            
            if self.config.auth_method == AuthMethod.KEY and self.config.key_path:
                connect_kwargs["key_filename"] = str(self.config.key_path)
            elif self.config.auth_method == AuthMethod.PASSWORD and self.config.password:
                connect_kwargs["password"] = self.config.password
            elif self.config.auth_method == AuthMethod.AGENT:
                # Use SSH agent
                agent = paramiko.Agent()
                keys = agent.get_keys()
                if keys:
                    connect_kwargs["pkey"] = keys[0]
            
            if self.config.username:
                connect_kwargs["username"] = self.config.username
            
            # Connect in executor
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: self._client.connect(**connect_kwargs)
            )
            
        except ImportError:
            raise SSHError("paramiko not installed: pip install paramiko")
        except Exception as e:
            raise SSHError(f"Connection failed: {e}")
    
    async def execute(
        self,
        command: str,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
    ) -> RemoteResult:
        """Execute command on remote host."""
        if not self._client:
            raise SSHError("Not connected")
        
        import time
        start = time.time()
        
        # Build command with env vars
        if env:
            env_prefix = " ".join(f"{k}={v}" for k, v in env.items())
            full_command = f"{env_prefix} {command}"
        else:
            full_command = command
        
        loop = asyncio.get_event_loop()
        
        stdin, stdout, stderr = await loop.run_in_executor(
            None,
            lambda: self._client.exec_command(full_command, timeout=timeout)
        )
        
        # Read output
        stdout_data = await loop.run_in_executor(
            None,
            lambda: stdout.read().decode()
        )
        stderr_data = await loop.run_in_executor(
            None,
            lambda: stderr.read().decode()
        )
        
        # Get exit code
        exit_code = await loop.run_in_executor(
            None,
            stdout.channel.recv_exit_status
        )
        
        duration_ms = (time.time() - start) * 1000
        
        return RemoteResult(
            stdout=stdout_data,
            stderr=stderr_data,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )
    
    async def execute_streaming(
        self,
        command: str,
        callback,
    ) -> int:
        """Execute command with streaming output."""
        if not self._client:
            raise SSHError("Not connected")
        
        loop = asyncio.get_event_loop()
        
        stdin, stdout, stderr = await loop.run_in_executor(
            None,
            lambda: self._client.exec_command(command)
        )
        
        # Stream stdout
        async def stream_output(stream, is_stderr=False):
            while True:
                chunk = await loop.run_in_executor(
                    None,
                    stream.read,
                    4096
                )
                if not chunk:
                    break
                await callback(chunk.decode(), is_stderr=is_stderr)
        
        # Start streaming tasks
        await asyncio.gather(
            stream_output(stdout, False),
            stream_output(stderr, True),
        )
        
        return await loop.run_in_executor(
            None,
            stdout.channel.recv_exit_status
        )
    
    async def open_sftp(self) -> Any:
        """Open SFTP session."""
        if not self._client:
            raise SSHError("Not connected")
        
        loop = asyncio.get_event_loop()
        self._sftp = await loop.run_in_executor(
            None,
            self._client.open_sftp
        )
        return self._sftp
    
    async def upload_file(
        self,
        local_path: Path,
        remote_path: str,
    ) -> None:
        """Upload file via SFTP."""
        sftp = await self.open_sftp()
        loop = asyncio.get_event_loop()
        
        await loop.run_in_executor(
            None,
            lambda: sftp.put(str(local_path), remote_path)
        )
    
    async def download_file(
        self,
        remote_path: str,
        local_path: Path,
    ) -> None:
        """Download file via SFTP."""
        sftp = await self.open_sftp()
        loop = asyncio.get_event_loop()
        
        await loop.run_in_executor(
            None,
            lambda: sftp.get(remote_path, str(local_path))
        )
    
    async def create_tunnel(
        self,
        local_port: int,
        remote_host: str,
        remote_port: int,
    ) -> Any:
        """Create SSH tunnel (local port forwarding)."""
        if not self._client:
            raise SSHError("Not connected")
        
        transport = self._client.get_transport()
        if not transport:
            raise SSHError("Transport not available")
        
        loop = asyncio.get_event_loop()
        
        # Create channel with dynamic port forwarding
        channel = await loop.run_in_executor(
            None,
            transport.open_channel,
            "direct-tcpip",
            (remote_host, remote_port),
            ("127.0.0.1", local_port),
        )
        
        return channel
    
    async def close(self) -> None:
        """Close SSH connection."""
        if self._sftp:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._sftp.close
            )
            self._sftp = None
        
        if self._client:
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._client.close
            )
            self._client = None


class SSHManager:
    """Manages multiple SSH connections."""
    
    def __init__(self):
        self._connections: dict[str, SSHConnection] = {}
        self._tunnels: dict[str, Any] = {}
    
    async def add_connection(
        self,
        name: str,
        config: SSHConfig,
    ) -> SSHConnection:
        """Add and connect to SSH host."""
        conn = SSHConnection(config)
        await conn.connect()
        self._connections[name] = conn
        return conn
    
    def get_connection(self, name: str) -> SSHConnection | None:
        """Get connection by name."""
        return self._connections.get(name)
    
    def list_connections(self) -> list[str]:
        """List all connection names."""
        return list(self._connections.keys())
    
    async def remove_connection(self, name: str) -> None:
        """Remove and close connection."""
        if name in self._connections:
            await self._connections[name].close()
            del self._connections[name]
    
    async def execute_all(
        self,
        command: str,
        hosts: list[str] | None = None,
    ) -> dict[str, RemoteResult]:
        """Execute command on multiple hosts."""
        results = {}
        targets = hosts or list(self._connections.keys())
        
        tasks = []
        for name in targets:
            conn = self._connections.get(name)
            if conn:
                tasks.append((name, conn.execute(command)))
        
        completed = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        
        for (name, _), result in zip(tasks, completed):
            if isinstance(result, Exception):
                results[name] = RemoteResult(
                    stdout="",
                    stderr=str(result),
                    exit_code=-1,
                    duration_ms=0,
                )
            else:
                results[name] = result
        
        return results
    
    async def close_all(self) -> None:
        """Close all connections."""
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()


class ReverseTunnel:
    """Reverse SSH tunnel for exposing local ports."""
    
    def __init__(
        self,
        ssh_config: SSHConfig,
        remote_port: int,
        local_port: int = 22,
        remote_bind: str = "0.0.0.0",
    ):
        self.ssh_config = ssh_config
        self.remote_port = remote_port
        self.local_port = local_port
        self.remote_bind = remote_bind
        self._client = None
        self._transport = None
        self._reverse_channel = None
    
    async def start(self) -> None:
        """Start reverse tunnel."""
        import paramiko
        
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect
        connect_kwargs = {
            "hostname": self.ssh_config.host,
            "port": self.ssh_config.port,
            "username": self.ssh_config.username,
            "timeout": self.ssh_config.timeout,
        }
        
        if self.ssh_config.key_path:
            connect_kwargs["key_filename"] = str(self.ssh_config.key_path)
        elif self.ssh_config.password:
            connect_kwargs["password"] = self.ssh_config.password
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self._client.connect(**connect_kwargs)
        )
        
        # Request reverse port forwarding
        transport = self._client.get_transport()
        transport.request_port_forward(
            self.remote_bind,
            self.remote_port,
        )
        
        print(f"Reverse tunnel established: {self.remote_bind}:{self.remote_port} -> localhost:{self.local_port}")
    
    async def stop(self) -> None:
        """Stop reverse tunnel."""
        if self._client:
            if self._transport:
                self._transport.cancel_port_forward(self.remote_bind, self.remote_port)
            await asyncio.get_event_loop().run_in_executor(
                None,
                self._client.close
            )
            self._client = None


class JumpHost:
    """SSH connection via jump/bastion host."""
    
    def __init__(
        self,
        jump_config: SSHConfig,
        target_config: SSHConfig,
    ):
        self.jump_config = jump_config
        self.target_config = target_config
        self._jump_conn = None
        self._target_conn = None
    
    async def connect(self) -> SSHConnection:
        """Connect through jump host to target."""
        # Connect to jump host
        self._jump_conn = SSHConnection(self.jump_config)
        await self._jump_conn.connect()
        
        # Get transport from jump
        jump_transport = self._jump_conn._client.get_transport()
        
        # Create channel through jump
        dest_addr = (self.target_config.host, self.target_config.port)
        local_addr = ("127.0.0.1", 0)
        
        loop = asyncio.get_event_loop()
        channel = await loop.run_in_executor(
            None,
            jump_transport.open_channel,
            "direct-tcpip",
            dest_addr,
            local_addr,
        )
        
        # Create target connection over channel
        import paramiko
        
        target_client = paramiko.SSHClient()
        target_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # Connect via channel (fake socket)
        target_client.connect(
            hostname=self.target_config.host,
            port=self.target_config.port,
            username=self.target_config.username,
            password=self.target_config.password,
            sock=channel,
        )
        
        self._target_conn = SSHConnection(self.target_config)
        self._target_conn._client = target_client
        
        return self._target_conn
    
    async def close(self) -> None:
        """Close both connections."""
        if self._target_conn:
            await self._target_conn.close()
        if self._jump_conn:
            await self._jump_conn.close()


class SSHKeyManager:
    """Manage SSH keys."""
    
    def __init__(self, key_dir: Path | None = None):
        self.key_dir = key_dir or (Path.home() / ".ssh")
        self.key_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_key(
        self,
        name: str,
        key_type: str = "rsa",
        bits: int = 4096,
        passphrase: str | None = None,
    ) -> tuple[Path, Path]:
        """Generate new SSH key pair."""
        import paramiko
        
        # Generate key
        if key_type == "rsa":
            key = paramiko.RSAKey.generate(bits)
        elif key_type == "ed25519":
            key = paramiko.Ed25519Key.generate()
        else:
            key = paramiko.ECDSAKey.generate()
        
        # Save keys
        private_path = self.key_dir / name
        public_path = self.key_dir / f"{name}.pub"
        
        key.write_private_key_file(str(private_path), password=passphrase)
        public_path.write_text(f"{key.get_name()} {key.get_base64()}")
        
        # Set permissions
        private_path.chmod(0o600)
        public_path.chmod(0o644)
        
        return private_path, public_path
    
    def load_key(self, path: Path, passphrase: str | None = None) -> Any:
        """Load SSH key from file."""
        import paramiko
        
        try:
            if "rsa" in path.name.lower() or ".pub" not in path.name:
                return paramiko.RSAKey.from_private_key_file(str(path), password=passphrase)
            elif "ed25519" in path.name.lower():
                return paramiko.Ed25519Key.from_private_key_file(str(path), password=passphrase)
            else:
                return paramiko.ECDSAKey.from_private_key_file(str(path), password=passphrase)
        except paramiko.PasswordRequiredException:
            if passphrase:
                return self.load_key(path, passphrase)
            raise SSHError("Key requires passphrase")
    
    def list_keys(self) -> list[dict]:
        """List available SSH keys."""
        keys = []
        
        for path in self.key_dir.glob("*"):
            if path.is_file() and not path.name.endswith(".pub"):
                try:
                    stat = path.stat()
                    keys.append({
                        "name": path.name,
                        "path": str(path),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
                except:
                    pass
        
        return keys


# Convenience functions

async def quick_connect(
    host: str,
    username: str,
    key_path: Path | None = None,
    password: str | None = None,
) -> SSHConnection:
    """Quick SSH connection."""
    config = SSHConfig(
        host=host,
        username=username,
        key_path=key_path,
        password=password,
        auth_method=AuthMethod.KEY if key_path else AuthMethod.PASSWORD if password else AuthMethod.AGENT,
    )
    conn = SSHConnection(config)
    await conn.connect()
    return conn


async def remote_exec(
    host: str,
    command: str,
    username: str,
    key_path: Path | None = None,
) -> RemoteResult:
    """Quick remote command execution."""
    conn = await quick_connect(host, username, key_path)
    try:
        return await conn.execute(command)
    finally:
        await conn.close()
