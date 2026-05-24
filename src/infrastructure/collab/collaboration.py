"""Real-time Collaboration - WebSocket-based terminal sharing.

Features:
- Create shareable terminal sessions
- Real-time cursor sharing
- Terminal output broadcasting
- Session management
- User presence
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class CollabError(Exception):
    """Collaboration error."""
    pass


class SessionState(Enum):
    """Session states."""
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class UserRole(Enum):
    """User roles in session."""
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


@dataclass
class User:
    """A user in a session."""
    id: str
    name: str
    color: str = "#4CAF50"  # Cursor color
    role: UserRole = UserRole.VIEWER
    joined_at: datetime = field(default_factory=datetime.now)


@dataclass
class Cursor:
    """Shared cursor position."""
    user_id: str
    x: int = 0
    y: int = 0
    visible: bool = True


@dataclass
class TerminalOutput:
    """Terminal output chunk."""
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    source: str = "stdout"  # stdout, stderr, prompt


@dataclass
class CollabSession:
    """A collaboration session."""
    id: str
    name: str
    owner_id: str
    state: SessionState = SessionState.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    users: dict[str, User] = field(default_factory=dict)
    cursors: dict[str, Cursor] = field(default_factory=dict)
    output_history: list[TerminalOutput] = field(default_factory=list)


class CollabMessage:
    """Message types for collaboration."""
    
    # Client -> Server
    JOIN = "join"
    LEAVE = "leave"
    INPUT = "input"  # User typed something
    CURSOR_MOVE = "cursor_move"
    RESIZE = "resize"  # Terminal resize
    CHAT = "chat"  # Chat message
    
    # Server -> Client
    USER_JOINED = "user_joined"
    USER_LEFT = "user_left"
    OUTPUT = "output"  # Terminal output
    CURSOR_UPDATE = "cursor_update"
    SESSION_STATE = "session_state"
    ERROR = "error"
    
    # System
    HEARTBEAT = "heartbeat"
    ACK = "ack"


class CollabProtocol:
    """Protocol for collaboration messages."""
    
    @staticmethod
    def encode(msg_type: str, data: dict) -> str:
        """Encode message to JSON."""
        return json.dumps({"type": msg_type, "data": data})
    
    @staticmethod
    def decode(msg: str) -> tuple[str, dict]:
        """Decode message from JSON."""
        parsed = json.loads(msg)
        return parsed["type"], parsed.get("data", {})


class SessionManager:
    """Manages collaboration sessions."""
    
    def __init__(self):
        self._sessions: dict[str, CollabSession] = {}
        self._user_sessions: dict[str, str] = {}  # user_id -> session_id
    
    def create_session(self, owner: User, name: str) -> CollabSession:
        """Create new session."""
        session_id = str(uuid.uuid4())[:8]
        
        session = CollabSession(
            id=session_id,
            name=name,
            owner_id=owner.id,
        )
        session.users[owner.id] = owner
        
        self._sessions[session_id] = session
        self._user_sessions[owner.id] = session_id
        
        return session
    
    def get_session(self, session_id: str) -> CollabSession | None:
        """Get session by ID."""
        return self._sessions.get(session_id)
    
    def get_user_session(self, user_id: str) -> CollabSession | None:
        """Get session for user."""
        session_id = self._user_sessions.get(user_id)
        if session_id:
            return self._sessions.get(session_id)
        return None
    
    def join_session(self, session_id: str, user: User) -> CollabSession | None:
        """Join existing session."""
        session = self._sessions.get(session_id)
        if not session:
            return None
        
        session.users[user.id] = user
        self._user_sessions[user.id] = session_id
        
        return session
    
    def leave_session(self, user_id: str) -> None:
        """Remove user from session."""
        session_id = self._user_sessions.pop(user_id, None)
        if session_id:
            session = self._sessions.get(session_id)
            if session and user_id in session.users:
                del session.users[user_id]
                if user_id in session.cursors:
                    del session.cursors[user_id]
    
    def list_sessions(self) -> list[dict]:
        """List all active sessions."""
        return [
            {
                "id": s.id,
                "name": s.name,
                "owner": s.owner_id,
                "users": len(s.users),
                "state": s.state.value,
            }
            for s in self._sessions.values()
            if s.state == SessionState.ACTIVE
        ]


class TerminalMultiplexer:
    """Broadcast terminal output to multiple clients."""
    
    def __init__(self, session: CollabSession):
        self.session = session
        self._clients: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
    
    async def add_client(self, client_id: str) -> asyncio.Queue:
        """Add a client to receive output."""
        queue = asyncio.Queue()
        async with self._lock:
            self._clients[client_id] = queue
        return queue
    
    async def remove_client(self, client_id: str) -> None:
        """Remove a client."""
        async with self._lock:
            if client_id in self._clients:
                del self._clients[client_id]
    
    async def broadcast(self, output: TerminalOutput) -> None:
        """Broadcast output to all clients."""
        message = CollabProtocol.encode(CollabMessage.OUTPUT, {
            "content": output.content,
            "timestamp": output.timestamp.isoformat(),
            "source": output.source,
        })
        
        async with self._lock:
            for queue in self._clients.values():
                await queue.put(message)
    
    async def broadcast_cursor(self, cursor: Cursor) -> None:
        """Broadcast cursor position."""
        message = CollabProtocol.encode(CollabMessage.CURSOR_UPDATE, {
            "user_id": cursor.user_id,
            "x": cursor.x,
            "y": cursor.y,
            "visible": cursor.visible,
        })
        
        async with self._lock:
            for client_id, queue in self._clients.items():
                # Don't send own cursor back
                if client_id != cursor.user_id:
                    await queue.put(message)


class CollabServer:
    """WebSocket collaboration server."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._sessions = SessionManager()
        self._multiplexers: dict[str, TerminalMultiplexer] = {}
        self._clients: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter]] = {}
        self._running = False
    
    async def start(self) -> None:
        """Start the collaboration server."""
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
        )
        
        self._running = True
        addr = self._server.sockets[0].getsockname()
        print(f"Collab server started on {addr}")
        
        async with self._server:
            await self._server.serve_forever()
    
    async def stop(self) -> None:
        """Stop the server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
    
    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle client connection."""
        client_id = str(uuid.uuid4())[:8]
        self._clients[client_id] = (reader, writer)
        
        queue: asyncio.Queue | None = None
        user: User | None = None
        session: CollabSession | None = None
        
        try:
            # Handle messages
            while self._running:
                data = await reader.readline()
                if not data:
                    break
                
                msg = data.decode().strip()
                if not msg:
                    continue
                
                msg_type, data = CollabProtocol.decode(msg)
                
                if msg_type == CollabMessage.JOIN:
                    # Join session
                    session_id = data.get("session_id")
                    user = User(
                        id=client_id,
                        name=data.get("name", "Anonymous"),
                        role=UserRole(data.get("role", "viewer")),
                    )
                    
                    if session_id:
                        session = self._sessions.join_session(session_id, user)
                    else:
                        # Create new session
                        session = self._sessions.create_session(
                            user, data.get("session_name", "Untitled")
                        )
                    
                    if session:
                        queue = await self._get_multiplexer(session.id).add_client(client_id)
                        
                        # Send session state
                        await self._send(
                            writer,
                            CollabMessage.SESSION_STATE,
                            {
                                "session": {
                                    "id": session.id,
                                    "name": session.name,
                                    "users": [
                                        {"id": u.id, "name": u.name, "role": u.role.value}
                                        for u in session.users.values()
                                    ],
                                }
                            },
                        )
                
                elif msg_type == CollabMessage.INPUT:
                    # User input - broadcast to all
                    if session and queue:
                        mx = self._get_multiplexer(session.id)
                        await mx.broadcast(TerminalOutput(
                            content=data.get("content", ""),
                            source="user_input",
                        ))
                
                elif msg_type == CollabMessage.CURSOR_MOVE:
                    # Cursor update
                    if session:
                        cursor = Cursor(
                            user_id=client_id,
                            x=data.get("x", 0),
                            y=data.get("y", 0),
                            visible=data.get("visible", True),
                        )
                        session.cursors[client_id] = cursor
                        mx = self._get_multiplexer(session.id)
                        await mx.broadcast_cursor(cursor)
                
                elif msg_type == CollabMessage.RESIZE:
                    # Terminal resize - broadcast
                    if session:
                        mx = self._get_multiplexer(session.id)
                        await mx.broadcast(TerminalOutput(
                            content=json.dumps({"resize": data}),
                            source="system",
                        ))
                
                elif msg_type == CollabMessage.LEAVE:
                    break
                
                elif msg_type == CollabMessage.HEARTBEAT:
                    await self._send(writer, CollabMessage.ACK, {})
            
        except Exception as e:
            print(f"Client error: {e}")
        
        finally:
            # Cleanup
            if queue and session:
                mx = self._get_multiplexer(session.id)
                await mx.remove_client(client_id)
            
            if user:
                self._sessions.leave_session(client_id)
            
            if client_id in self._clients:
                del self._clients[client_id]
            
            writer.close()
            await writer.wait_closed()
    
    async def _send(
        self,
        writer: asyncio.StreamWriter,
        msg_type: str,
        data: dict,
    ) -> None:
        """Send message to client."""
        msg = CollabProtocol.encode(msg_type, data) + "\n"
        writer.write(msg.encode())
        await writer.drain()
    
    def _get_multiplexer(self, session_id: str) -> TerminalMultiplexer:
        """Get or create multiplexer for session."""
        if session_id not in self._multiplexers:
            session = self._sessions.get_session(session_id)
            if session:
                self._multiplexers[session_id] = TerminalMultiplexer(session)
        return self._multiplexers.get(session_id)


class CollabClient:
    """Client for connecting to collaboration server."""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
    
    async def connect(self) -> None:
        """Connect to server."""
        # Parse URL
        import re
        match = re.match(r"ws://([^:]+):(\d+)", self.server_url)
        if not match:
            raise CollabError("Invalid URL format")
        
        host, port = match.group(1), int(match.group(2))
        
        self._reader, self._writer = await asyncio.open_connection(host, port)
        self._running = True
    
    async def disconnect(self) -> None:
        """Disconnect from server."""
        self._running = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
    
    async def join(
        self,
        session_id: str | None = None,
        name: str = "Anonymous",
        role: str = "viewer",
    ) -> dict:
        """Join a session."""
        await self._send(CollabMessage.JOIN, {
            "session_id": session_id,
            "name": name,
            "role": role,
        })
        
        # Wait for session state
        while self._running:
            msg = await self._queue.get()
            if msg["type"] == CollabMessage.SESSION_STATE:
                return msg["data"]["session"]
    
    async def leave(self) -> None:
        """Leave session."""
        await self._send(CollabMessage.LEAVE, {})
        await self.disconnect()
    
    async def send_input(self, content: str) -> None:
        """Send terminal input."""
        await self._send(CollabMessage.INPUT, {"content": content})
    
    async def send_cursor(self, x: int, y: int, visible: bool = True) -> None:
        """Send cursor position."""
        await self._send(CollabMessage.CURSOR_MOVE, {
            "x": x,
            "y": y,
            "visible": visible,
        })
    
    async def send_resize(self, cols: int, rows: int) -> None:
        """Send terminal resize."""
        await self._send(CollabMessage.RESIZE, {
            "cols": cols,
            "rows": rows,
        })
    
    async def _send(self, msg_type: str, data: dict) -> None:
        """Send message."""
        msg = CollabProtocol.encode(msg_type, data) + "\n"
        self._writer.write(msg.encode())
        await self._writer.drain()
    
    async def receive(self) -> dict:
        """Receive a message."""
        return await self._queue.get()
    
    async def listen(self) -> None:
        """Listen for messages in background."""
        while self._running:
            try:
                data = await self._reader.readline()
                if not data:
                    break
                
                msg = data.decode().strip()
                if msg:
                    msg_type, msg_data = CollabProtocol.decode(msg)
                    await self._queue.put({"type": msg_type, "data": msg_data})
                    
            except Exception:
                break


# Convenience functions

async def create_session(name: str, owner_name: str = "Owner") -> dict:
    """Create new collaboration session."""
    server = CollabServer()
    # Would need to start server in background
    return {"id": "demo", "name": name}


async def join_session(url: str, session_id: str, name: str) -> CollabClient:
    """Join existing session."""
    client = CollabClient(url)
    await client.connect()
    session = await client.join(session_id=session_id, name=name)
    return client


class TerminalSharing:
    """Share a terminal with collaborators."""
    
    def __init__(self, session: CollabSession, shell):
        self.session = session
        self.shell = shell
        self._multiplexer = TerminalMultiplexer(session)
    
    async def start(self) -> None:
        """Start sharing terminal."""
        # Hook into shell output
        # For each output, broadcast to collaborators
        pass
    
    async def stop(self) -> None:
        """Stop sharing."""
        pass
