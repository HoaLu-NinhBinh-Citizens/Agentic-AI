"""Collaborative code review module.

Provides team collaboration features for code review:
- Review sessions
- Inline comments and threads
- Resolution tracking
- PR integration
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ThreadState(Enum):
    """State of a comment thread."""

    OPEN = "open"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


@dataclass
class Comment:
    """A comment in a review thread."""

    id: str
    author: str
    content: str
    created_at: str
    updated_at: Optional[str] = None


@dataclass
class Thread:
    """A comment thread on a specific location."""

    id: str
    file: str
    line: int
    state: ThreadState = ThreadState.OPEN
    comments: list[Comment] = field(default_factory=list)
    created_at: str = field(default_factory=datetime.now().isoformat)


@dataclass
class ReviewSession:
    """A collaborative review session."""

    id: str
    pr_id: Optional[str]
    title: str
    status: str = "active"  # active, completed, cancelled
    created_at: str = field(default_factory=datetime.now().isoformat)
    updated_at: str = field(default_factory=datetime.now().isoformat)
    threads: list[Thread] = field(default_factory=list)


class CollaborativeReviewDB:
    """Database for collaborative review data.

    Uses SQLite to store review sessions, threads, and comments.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database.

        Args:
            db_path: Path to SQLite database (default: .ai_support/reviews.db)
        """
        if db_path is None:
            db_path = Path(".ai_support/reviews.db")

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = self._get_conn()
        cursor = conn.cursor()

        # Sessions table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                pr_id TEXT,
                title TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        # Threads table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                file TEXT NOT NULL,
                line INTEGER NOT NULL,
                state TEXT DEFAULT 'open',
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
            """
        )

        # Comments table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS comments (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                author TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT,
                FOREIGN KEY (thread_id) REFERENCES threads(id)
            )
            """
        )

        conn.commit()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    # Session methods
    def create_session(self, title: str, pr_id: Optional[str] = None) -> str:
        """Create a new review session.

        Args:
            title: Session title
            pr_id: Optional PR ID for integration

        Returns:
            Session ID
        """
        session_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO sessions (id, pr_id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, pr_id, title, "active", now, now),
        )
        conn.commit()

        logger.info(f"Created review session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_sessions(self, status: Optional[str] = None) -> list[dict]:
        """List all sessions."""
        conn = self._get_conn()
        cursor = conn.cursor()

        if status:
            cursor.execute(
                "SELECT * FROM sessions WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        else:
            cursor.execute("SELECT * FROM sessions ORDER BY created_at DESC")

        return [dict(row) for row in cursor.fetchall()]

    # Thread methods
    def create_thread(
        self, session_id: str, file: str, line: int
    ) -> str:
        """Create a new thread.

        Args:
            session_id: Session ID
            file: File path
            line: Line number

        Returns:
            Thread ID
        """
        thread_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO threads (id, session_id, file, line, state, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (thread_id, session_id, file, line, "open", now),
        )
        conn.commit()

        # Update session timestamp
        cursor.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id)
        )
        conn.commit()

        return thread_id

    def get_threads(self, session_id: str) -> list[dict]:
        """Get all threads for a session."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM threads WHERE session_id = ? ORDER BY created_at",
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def update_thread_state(
        self, thread_id: str, state: ThreadState
    ) -> bool:
        """Update thread state."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE threads SET state = ? WHERE id = ?", (state.value, thread_id)
        )
        conn.commit()
        return cursor.rowcount > 0

    # Comment methods
    def add_comment(
        self, thread_id: str, author: str, content: str
    ) -> str:
        """Add a comment to a thread.

        Args:
            thread_id: Thread ID
            author: Comment author
            content: Comment content

        Returns:
            Comment ID
        """
        comment_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO comments (id, thread_id, author, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (comment_id, thread_id, author, content, now),
        )
        conn.commit()

        return comment_id

    def get_comments(self, thread_id: str) -> list[dict]:
        """Get all comments for a thread."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM comments WHERE thread_id = ? ORDER BY created_at",
            (thread_id,),
        )
        return [dict(row) for row in cursor.fetchall()]


class CollaborativeReview:
    """Main class for collaborative code review."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize collaborative review.

        Args:
            db_path: Path to database
        """
        self.db = CollaborativeReviewDB(db_path)

    def create_session(self, title: str, pr_id: Optional[str] = None) -> str:
        """Create a new review session."""
        return self.db.create_session(title, pr_id)

    def add_comment(
        self,
        session_id: str,
        file: str,
        line: int,
        author: str,
        content: str,
    ) -> str:
        """Add an inline comment to a review.

        Args:
            session_id: Session ID
            file: File path
            line: Line number
            author: Comment author
            content: Comment content

        Returns:
            Comment ID
        """
        # Create thread if doesn't exist
        threads = self.db.get_threads(session_id)
        thread_id: Optional[str] = None

        for thread in threads:
            if thread["file"] == file and thread["line"] == line:
                thread_id = thread["id"]
                break

        if not thread_id:
            thread_id = self.db.create_thread(session_id, file, line)

        # Add comment
        return self.db.add_comment(thread_id, author, content)

    def resolve_thread(
        self, session_id: str, file: str, line: int
    ) -> bool:
        """Mark a thread as resolved."""
        threads = self.db.get_threads(session_id)

        for thread in threads:
            if thread["file"] == file and thread["line"] == line:
                return self.db.update_thread_state(
                    thread["id"], ThreadState.RESOLVED
                )

        return False

    def get_summary(self, session_id: str) -> dict:
        """Get review summary for a session.

        Args:
            session_id: Session ID

        Returns:
            Summary dict with counts and statistics
        """
        session = self.db.get_session(session_id)
        if not session:
            return {}

        threads = self.db.get_threads(session_id)

        open_count = sum(1 for t in threads if t["state"] == "open")
        resolved_count = sum(1 for t in threads if t["state"] == "resolved")

        return {
            "session_id": session_id,
            "title": session["title"],
            "pr_id": session.get("pr_id"),
            "status": session["status"],
            "total_threads": len(threads),
            "open_threads": open_count,
            "resolved_threads": resolved_count,
            "completion_rate": (
                f"{(resolved_count / len(threads) * 100):.1f}%"
                if threads
                else "0%"
            ),
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
        }

    def export_report(self, session_id: str) -> str:
        """Export review report as markdown.

        Args:
            session_id: Session ID

        Returns:
            Markdown report
        """
        summary = self.get_summary(session_id)
        threads = self.db.get_threads(session_id)

        lines = [
            f"# Code Review: {summary.get('title', 'Untitled')}",
            "",
            f"**PR:** {summary.get('pr_id', 'N/A')}",
            f"**Status:** {summary.get('status', 'active')}",
            f"**Created:** {summary.get('created_at', '')}",
            "",
            "## Summary",
            "",
            f"- Total Threads: {summary.get('total_threads', 0)}",
            f"- Open: {summary.get('open_threads', 0)}",
            f"- Resolved: {summary.get('resolved_threads', 0)}",
            f"- Completion: {summary.get('completion_rate', '0%')}",
            "",
        ]

        if threads:
            lines.append("## Threads")
            lines.append("")

            for thread in threads:
                comments = self.db.get_comments(thread["id"])
                state_icon = "✅" if thread["state"] == "resolved" else "💬"

                lines.append(f"### {state_icon} {thread['file']}:{thread['line']}")
                lines.append(f"**State:** {thread['state']}")
                lines.append("")

                for comment in comments:
                    lines.append(
                        f"**{comment['author']}** ({comment['created_at'][:10]}):"
                    )
                    lines.append(f"> {comment['content']}")
                    lines.append("")

        return "\n".join(lines)

    def close(self) -> None:
        """Close database connection."""
        self.db.close()
