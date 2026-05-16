import re
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional, Tuple

from src.core.config.agent_prompts import OUTPUT_GENERATED_ROOT, VENDOR_FILE_PATTERNS, VENDOR_PATH_PARTS, WINDOWS_INVALID_FILENAME_CHARS


class OutputSanitizer:
    PATH_TOKEN_RE = re.compile(r"(?i)(?:[A-Za-z]:)?/?[A-Za-z0-9_./\\:-]+\.(?:c|h)\b")

    def __init__(self, response_parser, file_tools, default_allowed_outputs):
        self.response_parser = response_parser
        self.file_tools = file_tools
        self._default_allowed_outputs = default_allowed_outputs

    def extract_code(self, response: str) -> Optional[str]:
        return self.response_parser.extract_code(response)

    def extract_json_object(self, response: str) -> Optional[Dict]:
        return self.response_parser.extract_json_object(response)

    def is_insufficient_documentation_response(self, response: str) -> bool:
        text = str(response or "").strip()
        if not text:
            return False
        if text == "INSUFFICIENT DOCUMENTATION":
            return True
        return bool(re.search(r"\[CODE\]\s*INSUFFICIENT DOCUMENTATION\s*$", text, re.IGNORECASE | re.DOTALL))

    def normalize_document_worker_response(self, response: str) -> str:
        return self.response_parser.normalize_document_worker_response(response)

    def extract_code_payload(self, response: str) -> str:
        return self.response_parser.extract_code_payload(response)

    def extract_file_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.response_parser.extract_file_blocks(response)

    def extract_explicit_file_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.response_parser.extract_explicit_file_blocks(response)

    def extract_backticked_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.response_parser.extract_backticked_path_blocks(response)

    def extract_bold_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.response_parser.extract_bold_path_blocks(response)

    def extract_heading_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.response_parser.extract_heading_path_blocks(response)

    def extract_plain_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        return self.response_parser.extract_plain_path_blocks(response)

    def sanitize_generated_path(self, raw_path: str, code: str) -> Optional[str]:
        path = self._path_candidate(raw_path)
        path = re.sub(r'^[>\-\*\s]+', '', path)
        path = path.replace("\\", "/")
        path = path.split("```", 1)[0].strip()
        path = re.sub(r'\*+$', '', path).strip()
        path = re.sub(r'/+', '/', path)
        if not path:
            return None

        suffix = Path(path).suffix.lower()
        if suffix not in {".c", ".h"}:
            inferred_suffix = ".h" if re.search(r'^\s*#ifndef|^\s*#pragma\s+once', code, re.MULTILINE) else ".c"
            path = f"{path}{inferred_suffix}"

        parts = []
        for part in Path(path).parts:
            cleaned = part.strip().strip(".")
            if not cleaned:
                continue
            cleaned = "".join("_" if ch in WINDOWS_INVALID_FILENAME_CHARS else ch for ch in cleaned)
            cleaned = cleaned.strip()
            if cleaned in {".", ".."}:
                continue
            parts.append(cleaned)
        if not parts:
            return None

        safe_path = Path(*parts).as_posix()
        safe_path = self.normalize_to_output_path(safe_path)
        self.file_tools.resolve_relative_path(safe_path)
        return safe_path

    def normalize_to_output_path(self, path: str) -> str:
        normalized = str(path or "").replace("\\", "/").lstrip("/")
        normalized = re.sub(r"/+", "/", normalized)
        parts = [
            part.strip()
            for part in PurePosixPath(normalized).parts
            if part.strip() and part not in {".", "..", "/"}
        ]
        normalized = PurePosixPath(*parts).as_posix() if parts else ""
        if normalized.startswith(f"{OUTPUT_GENERATED_ROOT}/"):
            return normalized
        filename = PurePosixPath(normalized).name
        suffix = Path(filename).suffix.lower()
        subdir = "Inc" if suffix == ".h" else "Src"
        return Path(OUTPUT_GENERATED_ROOT, subdir, filename).as_posix()

    def _path_candidate(self, raw_path: str) -> str:
        path = str(raw_path or "").strip().strip("`").strip("'").strip('"')
        path = re.sub(r"[\x00-\x1f]+", " ", path)
        path = re.sub(r"^(?:FILE|PATH|OUTPUT)\s*:\s*", "", path, flags=re.IGNORECASE)
        match = self.PATH_TOKEN_RE.search(path)
        if match:
            return match.group(0).strip()
        return path.splitlines()[0].strip() if path else ""

    def is_vendor_managed_path(self, path: str) -> bool:
        """Return True when a path points at vendor-managed HAL/CMSIS content."""
        normalized = Path(path).as_posix()
        if any(part in normalized for part in VENDOR_PATH_PARTS):
            return True
        basename = Path(normalized).name
        return any(re.fullmatch(pattern, basename, re.IGNORECASE) for pattern in VENDOR_FILE_PATTERNS)

    def is_output_only_generation(self, paths: Iterable[str]) -> bool:
        """Return True when all generated files are confined to the output folder."""
        return all(Path(path).as_posix().startswith(f"{OUTPUT_GENERATED_ROOT}/") for path in paths)

    def truncate_smart(self, text: str, max_chars: int = 6000) -> str:
        """Keep both ends of long text so diagnostics preserve endings."""
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(text) <= max_chars:
            return text
        marker = " ...[TRUNCATED]... "
        if max_chars <= len(marker) + 2:
            return text[:max_chars].strip()
        head = max((max_chars - len(marker)) // 2, 1)
        tail = max(max_chars - len(marker) - head, 1)
        return f"{text[:head].rstrip()}{marker}{text[-tail:].lstrip()}"

    def normalize_allowed_outputs(self, paths) -> List[str]:
        if not isinstance(paths, list):
            paths = self._default_allowed_outputs("")
        normalized: List[str] = []
        for item in paths:
            try:
                path = self.sanitize_generated_path(str(item), "")
            except ValueError:
                continue
            if path and path not in normalized:
                normalized.append(path)
        if not normalized:
            normalized = self._default_allowed_outputs("")
        return normalized
