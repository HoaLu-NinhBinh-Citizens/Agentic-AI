import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.config.agent_prompts import AI_SUPPORT_ROOT

logger = logging.getLogger(__name__)


class FileTools:
    """File system operations."""

    def __init__(self, project_root: str = ".", workspace_root: Optional[str] = None):
        self.project_root = Path(project_root).resolve()
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else self.project_root

    def resolve_relative_path(self, path: str) -> Path:
        """Resolve a relative path while blocking invalid or escaping paths."""
        normalized = Path(path.replace("\\", "/"))
        if normalized.is_absolute():
            raise ValueError(f"Absolute paths are not allowed: {path}")

        base_root = self.workspace_root if Path(normalized).as_posix().startswith(f"{AI_SUPPORT_ROOT}/") else self.project_root
        file_path = (base_root / normalized).resolve()
        try:
            file_path.relative_to(base_root)
        except ValueError as exc:
            raise ValueError(f"Path escapes project root: {path}") from exc
        return file_path

    def read_file(self, path: str) -> str:
        """Read file content."""
        file_path = self.resolve_relative_path(path)
        if not file_path.is_file():
            if file_path.is_dir():
                raise ValueError(f"Path is a directory, not a file: {path}")
            raise ValueError(f"File not found: {path}")
        return file_path.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> bool:
        """Write file."""
        file_path = self.resolve_relative_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        logger.info("[OK] Wrote: %s", path)
        return True

    def edit_file(self, path: str, old_text: str, new_text: str) -> bool:
        """Replace text in file."""
        file_path = self.resolve_relative_path(path)
        content = file_path.read_text(encoding="utf-8")
        if old_text not in content:
            return False
        new_content = content.replace(old_text, new_text)
        file_path.write_text(new_content, encoding="utf-8")
        logger.info("[OK] Edited: %s", path)
        return True

    def list_files(self, pattern: str = "*.c") -> List[str]:
        """List files matching pattern."""
        files = list(self.project_root.glob(f"**/{pattern}"))
        return [str(file_path.relative_to(self.project_root)) for file_path in files]

    def find_headers(self) -> List[str]:
        """Find all .h files."""
        return self.list_files("*.h")

    def find_sources(self) -> List[str]:
        """Find all .c files."""
        return self.list_files("*.c")

    def search_code(self, pattern: str, file_pattern: str = "*.c") -> Dict[str, List[Tuple[int, str]]]:
        """Search code for pattern (grep-like)."""
        results: Dict[str, List[Tuple[int, str]]] = {}
        for file_path in self.list_files(file_pattern):
            try:
                content = self.read_file(file_path)
                matches = []
                for line_num, line in enumerate(content.split("\n"), 1):
                    if pattern.lower() in line.lower():
                        matches.append((line_num, line.strip()))
                if matches:
                    results[file_path] = matches
            except OSError:
                continue
        return results

    def get_project_context(self) -> Dict:
        """Get project structure info."""
        return {
            "sources": self.find_sources()[:20],
            "headers": self.find_headers()[:20],
            "root": str(self.project_root),
        }

