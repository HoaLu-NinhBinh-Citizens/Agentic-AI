"""Consensus module for distributed leader election and agreement."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class ConsensusState(Enum):
    """Raft-like consensus state."""
    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


@dataclass
class Vote:
    """Vote record for leader election."""
    candidate_id: str
    voter_id: str
    term: int
    granted: bool = True


@dataclass
class LogEntry:
    """Consensus log entry."""
    index: int
    term: int
    command: Dict


@dataclass
class ConsensusConfig:
    """Consensus module configuration."""
    election_timeout_ms: int = 500
    heartbeat_interval_ms: int = 150
    max_entries_per_append: int = 100


class ConsensusModule:
    """Raft-like consensus module for leader election."""

    def __init__(
        self,
        node_id: str,
        peers: Optional[List[str]] = None,
        config: Optional[ConsensusConfig] = None,
    ):
        self.node_id = node_id
        self.peers = peers or []
        self.config = config or ConsensusConfig()
        self.state = ConsensusState.FOLLOWER
        self.term = 0
        self._voted_for: Optional[str] = None
        self._votes: Dict[int, List[Vote]] = {}
        self._log: List[LogEntry] = []
        self._running = False
        self._leader_id: Optional[str] = None

    def is_leader(self) -> bool:
        return self.state == ConsensusState.LEADER

    def get_state(self) -> Dict:
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "term": self.term,
            "voted_for": self._voted_for,
            "leader": self._leader_id,
            "log_length": len(self._log),
        }

    def handle_vote_request(
        self,
        candidate_id: str,
        term: int,
        last_log_index: int,
        last_log_term: int,
    ) -> bool:
        if term > self.term:
            self.term = term
            self.state = ConsensusState.FOLLOWER
            self._voted_for = None

        last_term = self._log[-1].term if self._log else 0
        if term >= self.term and last_log_term >= last_term:
            self._voted_for = candidate_id
            if self.term not in self._votes:
                self._votes[self.term] = []
            self._votes[self.term].append(Vote(candidate_id=candidate_id, voter_id=self.node_id, term=self.term))
            return True
        return False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False
