"""Schema validation with versioning - Phase 5B Enterprise."""

from __future__ import annotations

from typing import Any, Callable, Optional

from .types import SchemaDefinition, SchemaMigration, ValidationResult


class SchemaValidationError(Exception):
    """Error during schema validation."""
    pass


class SchemaMigrationError(Exception):
    """Error during schema migration."""
    pass


class SchemaRegistry:
    """Registry for schema versions and migrations.
    
    Manages schema definitions and migration chains between versions.
    """
    
    def __init__(self):
        self._schemas: dict[str, dict[str, SchemaDefinition]] = {}
        self._migrations: dict[str, list[SchemaMigration]] = {}

    def register_schema(
        self,
        schema_id: str,
        version: str,
        schema_def: dict,
    ) -> None:
        """Register a schema definition."""
        if schema_id not in self._schemas:
            self._schemas[schema_id] = {}
        
        self._schemas[schema_id][version] = SchemaDefinition(
            schema_id=schema_id,
            version=version,
            schema_def=schema_def,
        )

    def register_migration(
        self,
        schema_id: str,
        from_version: str,
        to_version: str,
        migrate_fn: Callable[[dict], dict],
    ) -> None:
        """Register a migration between schema versions."""
        migration = SchemaMigration(
            schema_id=schema_id,
            from_version=from_version,
            to_version=to_version,
            migrate_fn=migrate_fn,
        )
        
        if schema_id not in self._migrations:
            self._migrations[schema_id] = []
        
        self._migrations[schema_id].append(migration)

    def get_schema(
        self,
        schema_id: str,
        version: str,
    ) -> Optional[SchemaDefinition]:
        """Get a schema definition by ID and version."""
        if schema_id not in self._schemas:
            return None
        return self._schemas[schema_id].get(version)

    def get_migration_chain(
        self,
        schema_id: str,
        from_version: str,
        to_version: str,
    ) -> list[SchemaMigration]:
        """Get the migration chain from one version to another."""
        if schema_id not in self._migrations:
            return []
        
        migrations = self._migrations[schema_id]
        chain = []
        
        current_version = from_version
        visited = set()
        
        while current_version != to_version:
            if current_version in visited:
                raise SchemaMigrationError(
                    f"Circular migration detected for {schema_id}"
                )
            visited.add(current_version)
            
            next_migration = None
            for migration in migrations:
                if migration.from_version == current_version:
                    next_migration = migration
                    break
            
            if next_migration is None:
                raise SchemaMigrationError(
                    f"No migration path from {from_version} to {to_version} "
                    f"for schema {schema_id}"
                )
            
            chain.append(next_migration)
            current_version = next_migration.to_version
        
        return chain


class SchemaValidator:
    """Schema validator with version support and migration.
    
    Validates input/output data against versioned schemas and
    performs migrations when needed.
    """
    
    def __init__(
        self,
        registry: Optional[SchemaRegistry] = None,
        migration_enabled: bool = True,
    ):
        self._registry = registry or SchemaRegistry()
        self._migration_enabled = migration_enabled

    @property
    def registry(self) -> SchemaRegistry:
        return self._registry

    async def validate_input(
        self,
        task_id: str,
        schema_version: str,
        data: dict,
    ) -> ValidationResult:
        """Validate input data against schema version.
        
        Args:
            task_id: Task identifier
            schema_version: Expected schema version
            data: Input data to validate
            
        Returns:
            ValidationResult with is_valid and any errors
        """
        schema = self._registry.get_schema(task_id, schema_version)
        
        if schema is None:
            return ValidationResult(
                is_valid=False,
                errors=[f"Schema not found: {task_id} v{schema_version}"],
            )
        
        errors = []
        warnings = []
        
        errors.extend(self._validate_required_fields(
            schema.schema_def, data
        ))
        errors.extend(self._validate_types(
            schema.schema_def, data
        ))
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    async def validate_output(
        self,
        task_id: str,
        schema_version: str,
        data: dict,
    ) -> ValidationResult:
        """Validate output data against schema version."""
        return await self.validate_input(task_id, schema_version, data)

    async def migrate_input(
        self,
        task_id: str,
        from_version: str,
        to_version: str,
        data: dict,
    ) -> dict:
        """Migrate data from one schema version to another.
        
        Args:
            task_id: Task identifier
            from_version: Source schema version
            to_version: Target schema version
            data: Data to migrate
            
        Returns:
            Migrated data conforming to target version
            
        Raises:
            SchemaMigrationError: If migration fails
        """
        if not self._migration_enabled:
            raise SchemaMigrationError("Migration is disabled")
        
        if from_version == to_version:
            return data
        
        try:
            chain = self._registry.get_migration_chain(
                task_id, from_version, to_version
            )
        except SchemaMigrationError:
            raise
        
        migrated_data = data.copy()
        for migration in chain:
            migrated_data = migration.migrate_fn(migrated_data)
        
        return migrated_data

    async def migrate_to_latest(
        self,
        task_id: str,
        data: dict,
        current_version: str,
    ) -> tuple[dict, str]:
        """Migrate data to the latest schema version.
        
        Args:
            task_id: Task identifier
            data: Data to migrate
            current_version: Current schema version
            
        Returns:
            Tuple of (migrated_data, latest_version)
        """
        if task_id not in self._registry._schemas:
            raise SchemaMigrationError(f"Schema not found: {task_id}")
        
        versions = sorted(
            self._registry._schemas[task_id].keys(),
            key=lambda v: [int(x) for x in v.split(".")],
        )
        latest_version = versions[-1]
        
        if current_version == latest_version:
            return data, latest_version
        
        migrated_data = await self.migrate_input(
            task_id, current_version, latest_version, data
        )
        
        return migrated_data, latest_version

    def _validate_required_fields(
        self,
        schema: dict,
        data: dict,
        path: str = "",
    ) -> list[str]:
        """Validate required fields are present."""
        errors = []
        
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        
        for field_name in required:
            field_path = f"{path}.{field_name}" if path else field_name
            if field_name not in data:
                errors.append(f"Missing required field: {field_path}")
        
        for field_name, field_schema in properties.items():
            if field_name in data:
                field_path = f"{path}.{field_name}" if path else field_name
                if isinstance(data[field_name], dict) and "properties" in field_schema:
                    errors.extend(self._validate_required_fields(
                        field_schema, data[field_name], field_path
                    ))
        
        return errors

    def _validate_types(
        self,
        schema: dict,
        data: dict,
        path: str = "",
    ) -> list[str]:
        """Validate field types match schema."""
        errors = []
        
        properties = schema.get("properties", {})
        
        for field_name, field_schema in properties.items():
            if field_name not in data:
                continue
            
            field_path = f"{path}.{field_name}" if path else field_name
            value = data[field_name]
            expected_type = field_schema.get("type")
            
            type_errors = self._check_type(value, expected_type, field_path)
            errors.extend(type_errors)
        
        return errors

    def _check_type(
        self,
        value: Any,
        expected_type: Optional[str],
        path: str,
    ) -> list[str]:
        """Check if value matches expected type."""
        if expected_type is None:
            return []
        
        errors = []
        
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
            "null": type(None),
        }
        
        expected_python_type = type_map.get(expected_type)
        if expected_python_type and not isinstance(value, expected_python_type):
            if expected_type == "number" and isinstance(value, int):
                return []
            errors.append(
                f"Type mismatch at {path}: expected {expected_type}, "
                f"got {type(value).__name__}"
            )
        
        return errors


class InMemorySchemaStore:
    """In-memory implementation of schema store for testing."""
    
    def __init__(self):
        self._schemas: dict[str, dict[str, SchemaDefinition]] = {}
        self._migrations: dict[str, list[SchemaMigration]] = {}

    async def save_schema(self, schema: SchemaDefinition) -> None:
        """Save schema to store."""
        if schema.schema_id not in self._schemas:
            self._schemas[schema.schema_id] = {}
        self._schemas[schema.schema_id][schema.version] = schema

    async def get_schema(
        self,
        schema_id: str,
        version: str,
    ) -> Optional[SchemaDefinition]:
        """Get schema from store."""
        if schema_id not in self._schemas:
            return None
        return self._schemas[schema_id].get(version)

    async def get_all_versions(self, schema_id: str) -> list[str]:
        """Get all versions of a schema."""
        if schema_id not in self._schemas:
            return []
        return list(self._schemas[schema_id].keys())

    async def save_migration(self, migration: SchemaMigration) -> None:
        """Save migration to store."""
        if migration.schema_id not in self._migrations:
            self._migrations[migration.schema_id] = []
        self._migrations[migration.schema_id].append(migration)

    async def get_migrations(
        self,
        schema_id: str,
        from_version: str,
    ) -> list[SchemaMigration]:
        """Get migrations from a specific version."""
        if schema_id not in self._migrations:
            return []
        return [
            m for m in self._migrations[schema_id]
            if m.from_version == from_version
        ]
