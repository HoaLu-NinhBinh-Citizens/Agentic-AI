"""Key-Value compaction compression strategy.

Keeps important fields based on value characteristics.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import TYPE_CHECKING

from .base import CompressionStrategy, DecompressionError
from ..types import CompressionMetadata

if TYPE_CHECKING:
    from ..config import KeyValueConfig


class KeyValueCompactor(CompressionStrategy):
    """Compress by keeping important key-value pairs.
    
    Scores fields by their value characteristics:
    - Longer strings = higher score
    - Larger numbers = higher score
    - More nested dicts = higher score
    - Longer lists = higher score
    
    Keeps top-ranked fields up to keep_fields_ratio.
    """
    
    def __init__(self, config: "KeyValueConfig | None" = None):
        if config is None:
            from ..config import KeyValueConfig
            config = KeyValueConfig()
        
        self._keep_fields_ratio = config.keep_fields_ratio
    
    @property
    def name(self) -> str:
        return "kv_compact"
    
    def _calculate_field_scores(self, data: dict) -> dict[str, float]:
        """Calculate importance scores for each field.
        
        Scoring heuristics:
        - Strings: longer = more important (content-bearing)
        - Numbers: larger magnitude = more important
        - Lists: longer = more data
        - Dicts: more keys = more structure
        """
        scores: dict[str, float] = {}
        
        for key, value in data.items():
            score = 1.0
            
            if isinstance(value, str):
                score += len(value) / 100
            elif isinstance(value, bool):
                score += 0.5
            elif isinstance(value, (int, float)):
                score += min(abs(value) / 1000, 10)
            elif isinstance(value, list):
                score += len(value) / 10
            elif isinstance(value, dict):
                score += len(value) * 2
                for nested_key, nested_value in value.items():
                    if isinstance(nested_value, str):
                        score += len(nested_value) / 200
                    elif isinstance(nested_value, (int, float)):
                        score += 0.1
            
            scores[key] = score
        
        return scores
    
    def _try_json_parse(self, content: str) -> tuple[dict | None, bool]:
        """Try to parse content as JSON.
        
        Returns:
            (parsed_data, is_dict) tuple.
        """
        try:
            parsed = json.loads(content)
            return parsed, isinstance(parsed, dict)
        except (json.JSONDecodeError, TypeError):
            return None, False
    
    async def compress(self, content: str) -> tuple[str, CompressionMetadata]:
        """Compress by keeping important key-value pairs."""
        original_hash = hashlib.sha256(content.encode()).hexdigest()
        
        data, is_dict = self._try_json_parse(content)
        
        if not is_dict:
            return content, CompressionMetadata(
                strategy=self.name,
                params={"error": "not_json_or_not_dict"},
                original_hash=original_hash,
                error="content_is_not_json_object",
            )
        
        if len(data) == 0:
            return content, CompressionMetadata(
                strategy=self.name,
                params={"original_keys": 0},
                original_hash=original_hash,
            )
        
        field_scores = self._calculate_field_scores(data)
        sorted_fields = sorted(field_scores.items(), key=lambda x: x[1], reverse=True)
        
        keep_count = max(1, int(len(sorted_fields) * self._keep_fields_ratio))
        keep_count = min(keep_count, len(sorted_fields))
        
        kept_fields = [f[0] for f in sorted_fields[:keep_count]]
        compacted = {k: v for k, v in data.items() if k in kept_fields}
        
        try:
            compacted_json = json.dumps(compacted)
        except (TypeError, ValueError) as e:
            return content, CompressionMetadata(
                strategy=self.name,
                params={"error": str(e)},
                original_hash=original_hash,
                error=f"serialization_failed: {e}",
            )
        
        return compacted_json, CompressionMetadata(
            strategy=self.name,
            params={
                "keep_fields_ratio": self._keep_fields_ratio,
                "original_keys": len(data),
                "kept_keys": len(kept_fields),
            },
            original_hash=original_hash,
            kept_fields=kept_fields,
            compressed_at=int(time.time()),
        )
    
    async def decompress(
        self, content: str, metadata: CompressionMetadata
    ) -> str:
        """Decompress key-value compaction.
        
        Note: Dropped fields cannot be recovered.
        """
        return content
