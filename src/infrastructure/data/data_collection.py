"""Data collection for opt-in telemetry (Phase 11.1).

Provides:
- Opt-in data collection
- Log anonymization
- PII removal
- Secure storage
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DataType(Enum):
    """Types of data that can be collected."""
    LOG = "log"
    COREDUMP = "coredump"
    PATCH = "patch"
    METRICS = "metrics"
    BUG_REPORT = "bug_report"


@dataclass
class DataCollectionConfig:
    """Configuration for data collection."""
    enabled: bool = False  # Must be opt-in
    collection_dir: Path = field(default_factory=lambda: Path("data/collected"))
    anonymize: bool = True
    pii_patterns: list[str] = field(default_factory=list)
    max_log_size_kb: int = 1024
    retention_days: int = 30


class PIIRedactor:
    """Remove personally identifiable information from data."""
    
    # Common PII patterns
    DEFAULT_PATTERNS = [
        # Email
        (re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'), '[EMAIL_REDACTED]'),
        # Phone numbers
        (re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b'), '[PHONE_REDACTED]'),
        (re.compile(r'\b\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b'), '[PHONE_REDACTED]'),
        # IP addresses
        (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '[IP_REDACTED]'),
        # MAC addresses
        (re.compile(r'\b([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})\b'), '[MAC_REDACTED]'),
        # Serial numbers (various formats)
        (re.compile(r'\b[A-Z0-9]{8,}-[A-Z0-9]{4,}-[A-Z0-9]{4,}-[A-Z0-9]{4,}-[A-Z0-9]{12,}\b'), '[SERIAL_REDACTED]'),
        # Credit card numbers
        (re.compile(r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'), '[CC_REDACTED]'),
        # Names (common patterns)
        (re.compile(r'\b(Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+ [A-Z][a-z]+\b'), '[NAME_REDACTED]'),
        # File paths with usernames (Windows)
        (re.compile(r'C:\\Users\\[A-Za-z0-9_]+\\'), 'C:\\Users\\[USER]\\'),
        # File paths with usernames (Unix)
        (re.compile(r'/home/[A-Za-z0-9_]+/'), '/home/[USER]/'),
        # API keys
        (re.compile(r'(api[_-]?key|apikey|secret|token)\s*[=:]\s*["\']?[A-Za-z0-9_\-]{16,}["\']?', re.I), '[KEY_REDACTED]'),
        # Passwords
        (re.compile(r'password\s*[=:]\s*["\']?[^\s"\']{8,}["\']?', re.I), 'password=[REDACTED]'),
    ]
    
    def __init__(self, custom_patterns: list[tuple[re.Pattern, str]] | None = None) -> None:
        self._patterns = custom_patterns or self.DEFAULT_PATTERNS.copy()
    
    def add_pattern(self, pattern: re.Pattern, replacement: str) -> None:
        """Add a custom PII pattern."""
        self._patterns.append((pattern, replacement))
    
    def redact(self, text: str) -> str:
        """Redact PII from text."""
        result = text
        for pattern, replacement in self._patterns:
            result = pattern.sub(replacement, result)
        return result
    
    def redact_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Recursively redact PII from dictionary."""
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.redact(value)
            elif isinstance(value, dict):
                result[key] = self.redact_dict(value)
            elif isinstance(value, list):
                result[key] = [
                    self.redact(v) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value
        return result


class LogAnonymizer:
    """Anonymize firmware logs for collection."""
    
    # Hardware-specific patterns to keep (not PII)
    KEEP_PATTERNS = [
        # Register values
        (re.compile(r'R0:\s*0x[0-9a-fA-F]+'), True),
        (re.compile(r'R[1-9]:\s*0x[0-9a-fA-F]+'), True),
        # Memory addresses
        (re.compile(r'0x[0-9a-fA-F]{8}'), True),
        # Stack traces
        (re.compile(r'#\d+\s+0x[0-9a-fA-F]+\s+in\s+\w+'), True),
        # Board/board IDs (generic)
        (re.compile(r'board[_-]?id\s*[=:]\s*[A-Z0-9]{6,}'), True),
        # Firmware versions
        (re.compile(r'fw[_-]?version\s*[=:]\s*\d+\.\d+'), True),
    ]
    
    # Patterns that should be redacted
    REDACT_PATTERNS = [
        # User data in logs
        re.compile(r'user[_-]?name\s*[=:]\s*\w+'),
        re.compile(r'user[_-]?id\s*[=:]\s*\w+'),
        re.compile(r'token\s*[=:]\s*[A-Za-z0-9_\-]+'),
    ]
    
    def __init__(self) -> None:
        self._redactor = PIIRedactor()
    
    def anonymize(self, log_content: str) -> str:
        """Anonymize log content."""
        # First pass: redact PII
        result = self._redactor.redact(log_content)
        
        # Second pass: redact user data patterns
        for pattern in self.REDACT_PATTERNS:
            result = pattern.sub('[USER_DATA]', result)
        
        return result


@dataclass
class CollectedData:
    """Collected telemetry data."""
    id: str
    data_type: DataType
    content: str
    
    # Metadata
    board_id: str = ""
    firmware_version: str = ""
    collected_at: datetime = field(default_factory=datetime.now)
    anonymized: bool = False
    checksum: str = ""
    
    # Provenance
    source_path: str = ""
    collection_method: str = ""  # "manual", "automatic", "cli"


class DataCollector:
    """Collect telemetry data (opt-in only).
    
    Phase 11.1: Data collection (opt-in)
    Phase 11.3: Storage & anonymization
    """
    
    def __init__(self, config: DataCollectionConfig | None = None) -> None:
        self.config = config or DataCollectionConfig()
        self._anonymizer = LogAnonymizer()
        self._collected: list[CollectedData] = []
    
    def collect(
        self,
        data_type: DataType,
        content: str,
        board_id: str = "",
        firmware_version: str = "",
        source_path: str = "",
        collection_method: str = "automatic",
    ) -> CollectedData | None:
        """Collect data (only if opt-in enabled)."""
        if not self.config.enabled:
            logger.debug("Data collection disabled")
            return None
        
        # Check size limit
        size_kb = len(content.encode()) / 1024
        if size_kb > self.config.max_log_size_kb:
            logger.warning(
                "Data exceeds size limit, truncating",
                size_kb=size_kb,
                limit_kb=self.config.max_log_size_kb,
            )
            content = content[:self.config.max_log_size_kb * 1024]
        
        # Anonymize if enabled
        if self.config.anonymize:
            if data_type == DataType.LOG:
                content = self._anonymizer.anonymize(content)
        
        # Create collected data
        data = CollectedData(
            id=self._generate_id(),
            data_type=data_type,
            content=content,
            board_id=self._hash_board_id(board_id) if board_id else "",
            firmware_version=firmware_version,
            anonymized=self.config.anonymize,
            checksum=self._compute_checksum(content),
            source_path=source_path,
            collection_method=collection_method,
        )
        
        self._collected.append(data)
        
        logger.info(
            "Data collected",
            id=data.id,
            type=data_type.value,
            size_kb=len(content) / 1024,
        )
        
        return data
    
    def _generate_id(self) -> str:
        """Generate unique collection ID."""
        content = f"{datetime.now().isoformat()}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _hash_board_id(self, board_id: str) -> str:
        """Hash board ID to remove identifying information."""
        return hashlib.sha256(board_id.encode()).hexdigest()[:8]
    
    def _compute_checksum(self, content: str) -> str:
        """Compute content checksum for integrity."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def collect_log(
        self,
        log_content: str,
        board_id: str = "",
        source_path: str = "",
    ) -> CollectedData | None:
        """Collect log data."""
        return self.collect(
            DataType.LOG,
            log_content,
            board_id=board_id,
            source_path=source_path,
        )
    
    def collect_coredump(
        self,
        coredump_content: str,
        board_id: str = "",
        firmware_version: str = "",
    ) -> CollectedData | None:
        """Collect coredump data."""
        return self.collect(
            DataType.COREDUMP,
            coredump_content,
            board_id=board_id,
            firmware_version=firmware_version,
        )
    
    def collect_bug_report(
        self,
        bug_report: dict[str, Any],
        board_id: str = "",
    ) -> CollectedData | None:
        """Collect bug report data."""
        import json
        content = json.dumps(bug_report, indent=2)
        return self.collect(
            DataType.BUG_REPORT,
            content,
            board_id=board_id,
        )
    
    def save(self, data: CollectedData) -> Path | None:
        """Save collected data to disk."""
        if not self.config.collection_dir.exists():
            self.config.collection_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{data.data_type.value}_{data.id}_{data.collected_at.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.config.collection_dir / filename
        
        import json
        with open(filepath, "w") as f:
            json.dump({
                "id": data.id,
                "data_type": data.data_type.value,
                "content": data.content,
                "board_id": data.board_id,
                "firmware_version": data.firmware_version,
                "collected_at": data.collected_at.isoformat(),
                "anonymized": data.anonymized,
                "checksum": data.checksum,
                "source_path": data.source_path,
                "collection_method": data.collection_method,
            }, f, indent=2)
        
        logger.info("Saved collected data", path=str(filepath))
        return filepath
    
    def cleanup_old_data(self, days: int | None = None) -> int:
        """Remove old collected data."""
        retention_days = days or self.config.retention_days
        cutoff = datetime.now() - timedelta(days=retention_days)
        
        removed = 0
        if self.config.collection_dir.exists():
            for file in self.config.collection_dir.glob("*.json"):
                stat = file.stat()
                if datetime.fromtimestamp(stat.st_mtime) < cutoff:
                    file.unlink()
                    removed += 1
        
        if removed:
            logger.info("Cleaned up old data", removed=removed)
        
        return removed
    
    def get_statistics(self) -> dict[str, Any]:
        """Get collection statistics."""
        return {
            "total_collected": len(self._collected),
            "by_type": {
                dt.value: len([d for d in self._collected if d.data_type == dt])
                for dt in DataType
            },
            "anonymized": len([d for d in self._collected if d.anonymized]),
            "config": {
                "enabled": self.config.enabled,
                "collection_dir": str(self.config.collection_dir),
                "retention_days": self.config.retention_days,
            },
        }


# Import timedelta
from datetime import timedelta

# Global singleton
_collector: DataCollector | None = None


def get_data_collector() -> DataCollector:
    """Get global data collector instance."""
    global _collector
    if _collector is None:
        _collector = DataCollector()
    return _collector


# CLI for testing
if __name__ == "__main__":
    collector = DataCollector(DataCollectionConfig(enabled=True))
    
    # Test log collection
    sample_log = """
[2024-01-15 10:30:45] ERROR: HardFault at 0x20001000
  R0: 0x08000000 R1: 0x00000000 R2: 0x20001000
  #0  HardFault_Handler() at stm32f4xx_it.c:142
  #1  UART_IRQHandler() at uart.c:56
  board_id=ABC123XYZ firmware=v1.2.3
  user@example.com - test session
"""
    
    print("Testing data collection:")
    print("-" * 50)
    
    data = collector.collect_log(
        sample_log,
        board_id="board123",
        source_path="/var/log/firmware.log",
    )
    
    if data:
        print(f"Collected: {data.id}")
        print(f"Anonymized: {data.anonymized}")
        print(f"Checksum: {data.checksum}")
        print(f"\nContent preview:\n{data.content[:300]}...")
    
    print("\nStatistics:", collector.get_statistics())
