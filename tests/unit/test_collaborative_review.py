"""Tests for collaborative review."""
from __future__ import annotations

import pytest
from pathlib import Path

from src.application.workflows.collaborative.collaborative_review import (
    CollaborativeReview,
    CollaborativeReviewDB,
    ThreadState,
)


class TestCollaborativeReviewDB:
    """Tests for database operations."""

    def test_create_session(self, tmp_path: Path) -> None:
        """Should create a new session."""
        db = CollaborativeReviewDB(tmp_path / "test.db")
        session_id = db.create_session("Test Review", pr_id="PR-123")

        assert session_id
        session = db.get_session(session_id)
        assert session is not None
        assert session["title"] == "Test Review"
        assert session["pr_id"] == "PR-123"

        db.close()

    def test_create_thread(self, tmp_path: Path) -> None:
        """Should create a thread."""
        db = CollaborativeReviewDB(tmp_path / "test.db")
        session_id = db.create_session("Test")
        thread_id = db.create_thread(session_id, "test.py", 42)

        assert thread_id
        threads = db.get_threads(session_id)
        assert len(threads) == 1
        assert threads[0]["file"] == "test.py"
        assert threads[0]["line"] == 42

        db.close()

    def test_add_comment(self, tmp_path: Path) -> None:
        """Should add a comment to a thread."""
        db = CollaborativeReviewDB(tmp_path / "test.db")
        session_id = db.create_session("Test")
        thread_id = db.create_thread(session_id, "test.py", 42)

        comment_id = db.add_comment(thread_id, "alice", "This looks good!")
        assert comment_id

        comments = db.get_comments(thread_id)
        assert len(comments) == 1
        assert comments[0]["author"] == "alice"

        db.close()

    def test_list_sessions(self, tmp_path: Path) -> None:
        """Should list all sessions."""
        db = CollaborativeReviewDB(tmp_path / "test.db")
        db.create_session("Session 1")
        db.create_session("Session 2")

        sessions = db.list_sessions()
        assert len(sessions) == 2

        db.close()

    def test_update_thread_state(self, tmp_path: Path) -> None:
        """Should update thread state."""
        db = CollaborativeReviewDB(tmp_path / "test.db")
        session_id = db.create_session("Test")
        thread_id = db.create_thread(session_id, "test.py", 10)

        result = db.update_thread_state(thread_id, ThreadState.RESOLVED)
        assert result is True

        threads = db.get_threads(session_id)
        assert threads[0]["state"] == "resolved"

        db.close()


class TestCollaborativeReview:
    """Tests for collaborative review API."""

    def test_create_session(self, tmp_path: Path) -> None:
        """Should create a session."""
        review = CollaborativeReview(tmp_path / "test.db")
        session_id = review.create_session("My Review")

        assert session_id

        summary = review.get_summary(session_id)
        assert summary["title"] == "My Review"

        review.close()

    def test_add_comment(self, tmp_path: Path) -> None:
        """Should add a comment."""
        review = CollaborativeReview(tmp_path / "test.db")
        session_id = review.create_session("Test")

        comment_id = review.add_comment(
            session_id, "test.py", 10, "alice", "Nice fix!"
        )

        assert comment_id

        summary = review.get_summary(session_id)
        assert summary["total_threads"] == 1

        review.close()

    def test_resolve_thread(self, tmp_path: Path) -> None:
        """Should resolve a thread."""
        review = CollaborativeReview(tmp_path / "test.db")
        session_id = review.create_session("Test")

        review.add_comment(session_id, "test.py", 10, "alice", "Comment")

        result = review.resolve_thread(session_id, "test.py", 10)
        assert result is True

        summary = review.get_summary(session_id)
        assert summary["resolved_threads"] == 1

        review.close()

    def test_export_report(self, tmp_path: Path) -> None:
        """Should export markdown report."""
        review = CollaborativeReview(tmp_path / "test.db")
        session_id = review.create_session("Test Review", pr_id="PR-123")

        review.add_comment(session_id, "test.py", 10, "alice", "Nice work!")
        review.resolve_thread(session_id, "test.py", 10)

        report = review.export_report(session_id)

        assert "# Code Review: Test Review" in report
        assert "PR-123" in report
        assert "Total Threads: 1" in report
        assert "alice" in report

        review.close()

    def test_multiple_comments_same_thread(self, tmp_path: Path) -> None:
        """Should add multiple comments to same thread."""
        review = CollaborativeReview(tmp_path / "test.db")
        session_id = review.create_session("Test")

        review.add_comment(session_id, "test.py", 10, "alice", "First comment")
        review.add_comment(session_id, "test.py", 10, "bob", "Second comment")

        summary = review.get_summary(session_id)
        assert summary["total_threads"] == 1

        review.close()

    def test_get_summary_nonexistent(self, tmp_path: Path) -> None:
        """Should handle nonexistent session gracefully."""
        review = CollaborativeReview(tmp_path / "test.db")
        summary = review.get_summary("nonexistent-id")
        assert summary == {}

        review.close()
