"""Cloud sync for sessions, settings, and memories.

Provides:
- Session persistence to cloud
- Settings synchronization
- Memory backup
- Multi-device sync
- Conflict resolution
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class SyncProvider(Enum):
    """Cloud sync providers."""
    LOCAL = "local"
    FILESYSTEM = "filesystem"
    S3 = "s3"
    WEBDAV = "webdav"
    CUSTOM = "custom"


@dataclass
class SyncConfig:
    """Sync configuration."""
    provider: SyncProvider = SyncProvider.LOCAL
    endpoint: str = ""  # S3 bucket, WebDAV URL, etc.
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-east-1"
    bucket: str = "agentic-ai"
    base_path: str = "/sync"
    auto_sync: bool = True
    sync_interval: int = 60  # seconds
    conflict_resolution: str = "last-write-wins"  # or "manual"


@dataclass
class SyncItem:
    """An item to sync."""
    key: str
    value: Any
    checksum: str = ""
    version: int = 1
    last_modified: datetime = field(default_factory=datetime.now)
    synced: bool = False


@dataclass
class SyncResult:
    """Result of sync operation."""
    success: bool
    uploaded: list[str] = field(default_factory=list)
    downloaded: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class LocalSyncProvider:
    """Local filesystem sync provider."""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    async def upload(self, key: str, data: Any) -> None:
        """Upload data."""
        path = self.base_path / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, default=str))
    
    async def download(self, key: str) -> Any | None:
        """Download data."""
        path = self.base_path / f"{key}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text())
    
    async def list(self) -> list[str]:
        """List all keys."""
        keys = []
        for path in self.base_path.rglob("*.json"):
            key = str(path.relative_to(self.base_path))[:-5]  # Remove .json
            keys.append(key)
        return keys
    
    async def delete(self, key: str) -> None:
        """Delete data."""
        path = self.base_path / f"{key}.json"
        if path.exists():
            path.unlink()
    
    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        return (self.base_path / f"{key}.json").exists()


class S3SyncProvider:
    """AWS S3 sync provider."""
    
    def __init__(self, config: SyncConfig):
        self.config = config
        self._client = None
    
    async def _get_client(self):
        """Get or create S3 client."""
        if self._client is None:
            import boto3
            self._client = boto3.client(
                "s3",
                aws_access_key_id=self.config.access_key,
                aws_secret_access_key=self.config.secret_key,
                region_name=self.config.region,
            )
        return self._client
    
    async def upload(self, key: str, data: Any) -> None:
        """Upload to S3."""
        client = await self._get_client()
        
        data_str = json.dumps(data, default=str)
        
        client.put_object(
            Bucket=self.config.bucket,
            Key=f"{self.config.base_path}/{key}.json",
            Body=data_str.encode(),
            ContentType="application/json",
        )
    
    async def download(self, key: str) -> Any | None:
        """Download from S3."""
        client = await self._get_client()
        
        try:
            response = client.get_object(
                Bucket=self.config.bucket,
                Key=f"{self.config.base_path}/{key}.json",
            )
            return json.loads(response["Body"].read())
        except client.exceptions.NoSuchKey:
            return None
    
    async def list(self) -> list[str]:
        """List all keys."""
        client = await self._get_client()
        
        response = client.list_objects_v2(
            Bucket=self.config.bucket,
            Prefix=self.config.base_path,
        )
        
        keys = []
        for obj in response.get("Contents", []):
            key = obj["Key"][len(self.config.base_path)+1:-5]  # Remove path and .json
            keys.append(key)
        
        return keys
    
    async def delete(self, key: str) -> None:
        """Delete from S3."""
        client = await self._get_client()
        
        try:
            client.delete_object(
                Bucket=self.config.bucket,
                Key=f"{self.config.base_path}/{key}.json",
            )
        except:
            pass


class WebDAVSyncProvider:
    """WebDAV sync provider."""
    
    def __init__(self, config: SyncConfig):
        self.config = config
        self._session = None
    
    async def _get_session(self):
        """Get or create WebDAV session."""
        if self._session is None:
            import webdav3.client as webdav
            
            options = {
                "webdav_hostname": self.config.endpoint,
                "webdav_login": self.config.access_key,
                "webdav_password": self.config.secret_key,
            }
            self._session = webdav.Client(options)
        
        return self._session
    
    async def upload(self, key: str, data: Any) -> None:
        """Upload to WebDAV."""
        session = await self._get_session()
        
        path = f"{self.config.base_path}/{key}.json"
        data_str = json.dumps(data, indent=2, default=str)
        
        session.put(path, data_str)
    
    async def download(self, key: str) -> Any | None:
        """Download from WebDAV."""
        session = await self._get_session()
        
        path = f"{self.config.base_path}/{key}.json"
        
        try:
            content = session.download_sync(path)
            return json.loads(content)
        except:
            return None
    
    async def list(self) -> list[str]:
        """List all keys."""
        session = await self._get_session()
        
        try:
            files = session.list(self.config.base_path)
            keys = [f[:-5] for f in files if f.endswith(".json")]
            return keys
        except:
            return []
    
    async def delete(self, key: str) -> None:
        """Delete from WebDAV."""
        session = await self._get_session()
        path = f"{self.config.base_path}/{key}.json"
        session.clean(path)


class CloudSyncManager:
    """Manages cloud synchronization."""
    
    def __init__(self, config: SyncConfig):
        self.config = config
        self._provider = self._create_provider()
        self._local_cache: dict[str, SyncItem] = {}
        self._sync_task: asyncio.Task | None = None
    
    def _create_provider(self):
        """Create sync provider based on config."""
        if self.config.provider == SyncProvider.LOCAL:
            return LocalSyncProvider(Path.home() / ".config" / "agentic-ai" / "sync")
        elif self.config.provider == SyncProvider.S3:
            return S3SyncProvider(self.config)
        elif self.config.provider == SyncProvider.WEBDAV:
            return WebDAVSyncProvider(self.config)
        else:
            return LocalSyncProvider(Path.home() / ".config" / "agentic-ai" / "sync")
    
    async def start(self) -> None:
        """Start background sync."""
        if self.config.auto_sync and self._sync_task is None:
            self._sync_task = asyncio.create_task(self._sync_loop())
    
    async def stop(self) -> None:
        """Stop background sync."""
        if self._sync_task:
            self._sync_task.cancel()
            self._sync_task = None
    
    async def _sync_loop(self) -> None:
        """Background sync loop."""
        while True:
            try:
                await self.sync_all()
                await asyncio.sleep(self.config.sync_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Sync error: {e}")
                await asyncio.sleep(5)
    
    async def sync_all(self) -> SyncResult:
        """Sync all data."""
        result = SyncResult(success=True)
        
        # Upload local items
        for key, item in self._local_cache.items():
            if not item.synced:
                try:
                    await self._provider.upload(key, item.value)
                    item.synced = True
                    item.version += 1
                    result.uploaded.append(key)
                except Exception as e:
                    result.errors.append(f"Upload {key}: {e}")
                    result.success = False
        
        # Download remote items
        try:
            remote_keys = await self._provider.list()
            
            for key in remote_keys:
                if key not in self._local_cache:
                    data = await self._provider.download(key)
                    if data:
                        self._local_cache[key] = SyncItem(
                            key=key,
                            value=data,
                            synced=True,
                        )
                        result.downloaded.append(key)
                else:
                    # Check for conflicts
                    local = self._local_cache[key]
                    remote_data = await self._provider.download(key)
                    
                    if self._has_conflict(local.value, remote_data):
                        result.conflicts.append(key)
                        
                        if self.config.conflict_resolution == "last-write-wins":
                            # Keep remote (assumed to be newer)
                            self._local_cache[key].value = remote_data
                            self._local_cache[key].synced = True
                        # Manual resolution would require user input
                        
        except Exception as e:
            result.errors.append(f"Download: {e}")
            result.success = False
        
        return result
    
    def _has_conflict(self, local: Any, remote: Any) -> bool:
        """Check for sync conflicts."""
        if not local or not remote:
            return False
        
        local_checksum = hashlib.md5(json.dumps(local, sort_keys=True).encode()).hexdigest()
        remote_checksum = hashlib.md5(json.dumps(remote, sort_keys=True).encode()).hexdigest()
        
        return local_checksum != remote_checksum
    
    async def push(self, key: str, value: Any) -> None:
        """Push a value to cloud."""
        item = SyncItem(
            key=key,
            value=value,
            checksum=hashlib.md5(json.dumps(value, sort_keys=True).encode()).hexdigest(),
        )
        self._local_cache[key] = item
        
        if self.config.auto_sync:
            await self._provider.upload(key, value)
            item.synced = True
    
    async def pull(self, key: str) -> Any | None:
        """Pull a value from cloud."""
        if key in self._local_cache and self._local_cache[key].synced:
            return self._local_cache[key].value
        
        data = await self._provider.download(key)
        if data:
            self._local_cache[key] = SyncItem(
                key=key,
                value=data,
                synced=True,
            )
        
        return data
    
    async def resolve_conflict(
        self,
        key: str,
        resolution: str,  # "local" or "remote"
    ) -> None:
        """Resolve a sync conflict."""
        if key not in self._local_cache:
            return
        
        if resolution == "remote":
            remote_data = await self._provider.download(key)
            if remote_data:
                self._local_cache[key].value = remote_data
                self._local_cache[key].synced = True
        elif resolution == "local":
            await self._provider.upload(key, self._local_cache[key].value)
            self._local_cache[key].synced = True


# Convenience functions

def create_sync_manager(
    provider: str = "local",
    **kwargs,
) -> CloudSyncManager:
    """Create a sync manager."""
    provider_enum = SyncProvider(provider)
    config = SyncConfig(
        provider=provider_enum,
        **kwargs,
    )
    return CloudSyncManager(config)


async def quick_sync(
    data: dict,
    key: str = "default",
    provider: str = "local",
) -> None:
    """Quick sync to cloud."""
    manager = create_sync_manager(provider)
    await manager.start()
    await manager.push(key, data)
    await manager.stop()
