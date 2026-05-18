"""
Schema Evolution Engine for Multi-Agent Coordination.

Handles message schema versioning with backward/forward compatibility.
Supports migration functions for upgrading messages between versions.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.core.multi_agent.coordination.types import (
    CompatibilityPolicy,
    SchemaDefinition,
    SchemaField,
    SchemaMigration,
)

logger = logging.getLogger(__name__)


class SchemaStore:
    """Interface for schema storage."""
    
    async def save_schema(self, schema: SchemaDefinition) -> None:
        raise NotImplementedError
    
    async def get_schema(self, message_type: str, version: str) -> Optional[SchemaDefinition]:
        raise NotImplementedError
    
    async def get_latest_version(self, message_type: str) -> Optional[str]:
        raise NotImplementedError
    
    async def list_versions(self, message_type: str) -> List[str]:
        raise NotImplementedError


class InMemorySchemaStore(SchemaStore):
    """In-memory implementation of SchemaStore."""
    
    def __init__(self):
        self._schemas: Dict[str, Dict[str, SchemaDefinition]] = defaultdict(dict)
        self._versions: Dict[str, List[str]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def save_schema(self, schema: SchemaDefinition) -> None:
        async with self._lock:
            self._schemas[schema.message_type][schema.version] = schema
            if schema.version not in self._versions[schema.message_type]:
                self._versions[schema.message_type].append(schema.version)
                self._versions[schema.message_type].sort()
    
    async def get_schema(self, message_type: str, version: str) -> Optional[SchemaDefinition]:
        return self._schemas.get(message_type, {}).get(version)
    
    async def get_latest_version(self, message_type: str) -> Optional[str]:
        versions = self._versions.get(message_type, [])
        return versions[-1] if versions else None
    
    async def list_versions(self, message_type: str) -> List[str]:
        return self._versions.get(message_type, [])


@dataclass
class VersionMigration:
    """Migration between two versions."""
    from_version: str
    to_version: str
    migration_fn: SchemaMigration
    created_at: datetime = field(default_factory=datetime.now)


class SchemaEvolutionEngine:
    """
    Schema evolution engine for multi-agent coordination.
    
    Handles message schema versioning with:
    - Backward compatibility: New code reads old data
    - Forward compatibility: Old code reads new data (ignores unknown fields)
    - Full compatibility: Both directions
    
    Supports migration chains for multi-version upgrades.
    """
    
    def __init__(
        self,
        compatibility_policy: CompatibilityPolicy = CompatibilityPolicy.BACKWARD,
        current_version: str = "1",
        store: Optional[SchemaStore] = None,
    ):
        self.compatibility_policy = compatibility_policy
        self.current_version = current_version
        self.store = store or InMemorySchemaStore()
        
        self._schemas: Dict[str, SchemaDefinition] = {}
        self._migrations: Dict[str, Dict[str, VersionMigration]] = defaultdict(dict)
        self._migration_cache: Dict[Tuple[str, str], SchemaMigration] = {}
        self._lock = asyncio.Lock()
        
        # Metrics
        self._migration_count = 0
        self._transform_count = 0
    
    async def register_schema(
        self,
        message_type: str,
        version: str,
        schema: Dict[str, Any],
        migrations: Optional[Dict[Tuple[str, str], Callable]] = None,
    ) -> SchemaDefinition:
        """
        Register a new schema version.
        
        Args:
            message_type: Type of message (e.g., "TaskMessage", "AgentMessage")
            version: Schema version (e.g., "1", "2", "1.0.0")
            schema: Schema definition dictionary
            migrations: Optional migration functions from previous versions
            
        Returns:
            SchemaDefinition
        """
        fields = []
        for field_def in schema.get("fields", []):
            fields.append(SchemaField(
                name=field_def["name"],
                type=field_def.get("type", "any"),
                required=field_def.get("required", False),
                default=field_def.get("default"),
                description=field_def.get("description", ""),
            ))
        
        definition = SchemaDefinition(
            message_type=message_type,
            version=version,
            fields=fields,
            description=schema.get("description", ""),
        )
        
        async with self._lock:
            self._schemas[f"{message_type}:{version}"] = definition
            await self.store.save_schema(definition)
        
        # Register migrations
        if migrations:
            for (from_ver, to_ver), fn in migrations.items():
                if to_ver == version:
                    self._migrations[message_type][from_ver] = VersionMigration(
                        from_version=from_ver,
                        to_version=version,
                        migration_fn=fn,
                    )
                    # Clear migration cache
                    self._migration_cache.clear()
        
        logger.info(f"Registered schema {message_type}:{version}")
        return definition
    
    async def transform_message(
        self,
        message: Dict[str, Any],
        target_version: Optional[str] = None,
        source_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Transform a message to target schema version.
        
        Args:
            message: Message to transform
            target_version: Target version (defaults to current_version)
            source_version: Source version (extracted from message if not provided)
            
        Returns:
            Transformed message
        """
        target_version = target_version or self.current_version
        source_version = source_version or message.get("_schema_version", "1")
        
        if source_version == target_version:
            return message
        
        # Find migration path
        migration_fn = await self._get_migration_fn(source_version, target_version)
        
        if migration_fn:
            try:
                result = migration_fn(message.copy())
                self._migration_count += 1
                logger.debug(
                    f"Migrated message from {source_version} to {target_version}"
                )
                return result
            except Exception as e:
                logger.error(f"Migration failed: {e}")
                raise
        else:
            # No migration path, apply compatibility policy
            return self._apply_compatibility_policy(message, source_version, target_version)
    
    async def _get_migration_fn(
        self,
        source_version: str,
        target_version: str,
    ) -> Optional[SchemaMigration]:
        """Get or compute migration function for version transformation."""
        cache_key = (source_version, target_version)
        
        if cache_key in self._migration_cache:
            return self._migration_cache[cache_key]
        
        # Direct migration
        for msg_type, migrations in self._migrations.items():
            migration = migrations.get(source_version)
            if migration and migration.to_version == target_version:
                self._migration_cache[cache_key] = migration.migration_fn
                return migration.migration_fn
        
        # Find migration chain
        chain = await self._find_migration_chain(source_version, target_version)
        if chain:
            async def chained_migration(msg: Dict[str, Any]) -> Dict[str, Any]:
                result = msg
                for version_pair in chain:
                    for msg_type, migrations in self._migrations.items():
                        migration = migrations.get(version_pair[0])
                        if migration and migration.to_version == version_pair[1]:
                            result = migration.migration_fn(result)
                            break
                return result
            
            self._migration_cache[cache_key] = chained_migration
            return chained_migration
        
        return None
    
    async def _find_migration_chain(
        self,
        source: str,
        target: str,
    ) -> Optional[List[Tuple[str, str]]]:
        """Find migration chain using BFS."""
        # Build version graph
        versions = set()
        edges = []
        
        for msg_type, migrations in self._migrations.items():
            for from_ver, migration in migrations.items():
                versions.add(from_ver)
                versions.add(migration.to_version)
                edges.append((from_ver, migration.to_version))
        
        versions.add(source)
        versions.add(target)
        
        # BFS to find shortest path
        visited = {source: None}
        queue = [source]
        
        while queue:
            current = queue.pop(0)
            
            if current == target:
                # Reconstruct path
                path = []
                node = target
                while visited[node] is not None:
                    prev = visited[node]
                    path.append((prev, node))
                    node = prev
                return list(reversed(path))
            
            for from_ver, to_ver in edges:
                if from_ver == current and to_ver not in visited:
                    visited[to_ver] = from_ver
                    queue.append(to_ver)
        
        return None
    
    def _apply_compatibility_policy(
        self,
        message: Dict[str, Any],
        source_version: str,
        target_version: str,
    ) -> Dict[str, Any]:
        """
        Apply compatibility policy when no migration is available.
        
        BACKWARD: Add default values for missing fields
        FORWARD: Remove unknown fields
        FULL: Add defaults and remove unknowns
        """
        self._transform_count += 1
        
        if self.compatibility_policy == CompatibilityPolicy.BACKWARD:
            # Add defaults for missing fields
            schema_key = f"{message.get('_message_type', 'unknown')}:{target_version}"
            schema = self._schemas.get(schema_key)
            
            if schema:
                result = message.copy()
                for field in schema.fields:
                    if field.name not in result and field.default is not None:
                        result[field.name] = field.default
                return result
            
        elif self.compatibility_policy == CompatibilityPolicy.FORWARD:
            # Remove unknown fields
            schema_key = f"{message.get('_message_type', 'unknown')}:{source_version}"
            schema = self._schemas.get(schema_key)
            
            if schema:
                known_fields = {f.name for f in schema.fields}
                known_fields.update(["_message_type", "_schema_version"])
                return {k: v for k, v in message.items() if k in known_fields}
        
        # FULL or no schema found: pass through with metadata
        return message
    
    async def validate_message(
        self,
        message: Dict[str, Any],
        version: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Validate a message against its schema.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        version = version or message.get("_schema_version", "1")
        msg_type = message.get("_message_type", "unknown")
        schema_key = f"{msg_type}:{version}"
        
        schema = self._schemas.get(schema_key)
        if not schema:
            return True, []  # Can't validate without schema
        
        errors = []
        
        # Check required fields
        for field in schema.fields:
            if field.required and field.name not in message:
                errors.append(f"Missing required field: {field.name}")
        
        # Check types
        for field in schema.fields:
            if field.name in message:
                value = message[field.name]
                expected_type = field.type.lower()
                
                type_valid = self._check_type(value, expected_type)
                if not type_valid:
                    errors.append(
                        f"Field '{field.name}' has wrong type: "
                        f"expected {expected_type}, got {type(value).__name__}"
                    )
        
        return len(errors) == 0, errors
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected type."""
        if expected_type == "any":
            return True
        
        type_map = {
            "string": str,
            "str": str,
            "integer": int,
            "int": int,
            "float": (int, float),
            "number": (int, float),
            "boolean": bool,
            "bool": bool,
            "array": list,
            "list": list,
            "object": dict,
            "dict": dict,
            "null": type(None),
        }
        
        expected = type_map.get(expected_type.lower())
        if expected is None:
            return True  # Unknown type, assume valid
        
        return isinstance(value, expected)
    
    async def get_current_schema(
        self,
        message_type: str,
    ) -> Optional[SchemaDefinition]:
        """Get current schema definition for a message type."""
        key = f"{message_type}:{self.current_version}"
        return self._schemas.get(key)
    
    async def list_message_types(self) -> List[str]:
        """List all registered message types."""
        types_set = set()
        for key in self._schemas.keys():
            msg_type = key.split(":")[0]
            types_set.add(msg_type)
        return sorted(list(types_set))
    
    async def get_version_info(
        self,
        message_type: str,
    ) -> Dict[str, Any]:
        """Get version information for a message type."""
        versions = []
        for key, schema in self._schemas.items():
            if key.startswith(f"{message_type}:"):
                versions.append({
                    "version": schema.version,
                    "description": schema.description,
                    "field_count": len(schema.fields),
                    "created_at": schema.created_at.isoformat(),
                })
        
        return {
            "message_type": message_type,
            "current_version": self.current_version,
            "compatibility_policy": self.compatibility_policy.value,
            "versions": sorted(versions, key=lambda v: v["version"]),
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get schema evolution metrics."""
        return {
            "registered_schemas": len(self._schemas),
            "migration_count": self._migration_count,
            "transform_count": self._transform_count,
            "current_version": self.current_version,
            "compatibility_policy": self.compatibility_policy.value,
            "message_types": len(set(k.split(":")[0] for k in self._schemas.keys())),
        }
