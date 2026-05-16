import json
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ResponseParser:
    def extract_function_signatures(self, code: str, expect_definition: bool) -> Dict[str, str]:
        suffix = r"\{" if expect_definition else r";"
        pattern = rf"([A-Za-z_][\w\s\*]+?)\b([A-Za-z_]\w*)\s*\(([^{{;}}]*)\)\s*{suffix}"
        signatures: Dict[str, str] = {}
        for match in re.finditer(pattern, code):
            return_type = re.sub(r"\s+", " ", match.group(1)).strip()
            name = match.group(2).strip()
            params = re.sub(r"\s+", " ", match.group(3)).strip()
            signatures[name] = f"{return_type}({params})"
        return signatures

    def extract_code(self, response: str) -> Optional[str]:
        pattern = r"```[c\s]*\n(.*?)\n```"
        match = re.search(pattern, response, re.DOTALL)
        if match:
            return match.group(1).strip()
        if response.startswith("#include"):
            return response.strip()
        return None

    def extract_json_object(self, response: str) -> Optional[Dict]:
        response = str(response or "").strip()
        if not response:
            return None
        candidates = []
        candidates.append(response)

        fenced = re.findall(r"```(?:json)?\n(.*?)\n```", response, re.DOTALL)
        candidates.extend(fenced)

        start = response.find("{")
        end = response.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(response[start:end + 1])

        for candidate in candidates:
            for cleaned in self._json_candidate_variants(candidate):
                try:
                    data = json.loads(cleaned)
                except json.JSONDecodeError:
                    continue
                if isinstance(data, dict):
                    return data
        return None

    def _json_candidate_variants(self, candidate: str) -> List[str]:
        text = str(candidate or "").strip()
        variants = [text]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            variants.append(text[start:end + 1])
        trimmed = re.sub(r"[\s,;`]+$", "", text)
        if trimmed != text:
            variants.append(trimmed)
        deduped: List[str] = []
        for variant in variants:
            if variant and variant not in deduped:
                deduped.append(variant)
        return deduped

    def normalize_document_worker_response(self, response: str) -> str:
        text = response.strip()
        if not text:
            return text

        markers = ["[QUERY]", "[RETRIEVED CONTEXT]", "[UNDERSTANDING]", "[CODE]"]
        marker_positions = [text.find(marker) for marker in markers if text.find(marker) != -1]
        if marker_positions:
            first_marker = min(marker_positions)
            if first_marker > 0:
                prefix = text[:first_marker].strip()
                if prefix:
                    logger.warning("LLM response included prose before structured markers; stripping %d chars", len(prefix))
                text = text[first_marker:].strip()
        return text

    def extract_code_payload(self, response: str) -> str:
        normalized = self.normalize_document_worker_response(response)
        match = re.search(r"\[CODE\]\s*(.*)$", normalized, re.IGNORECASE | re.DOTALL)
        payload = match.group(1).strip() if match else normalized.strip()

        file_index = payload.find("FILE:")
        if file_index > 0:
            prefix = payload[:file_index].strip()
            if prefix:
                logger.warning("LLM code payload included prose before first FILE block; stripping %d chars", len(prefix))
            payload = payload[file_index:].strip()
        return payload

    def extract_file_blocks(self, response: str) -> List[Tuple[str, str]]:
        extractors = (
            self.extract_explicit_file_blocks,
            self.extract_bold_path_blocks,
            self.extract_backticked_path_blocks,
            self.extract_heading_path_blocks,
            self.extract_plain_path_blocks,
        )
        for extractor in extractors:
            blocks = extractor(response)
            if blocks:
                return blocks
        return []

    def extract_explicit_file_blocks(self, response: str) -> List[Tuple[str, str]]:
        pattern = r"FILE:\s*([^\n]+)\s*```[c\s]*\n(.*?)\n```"
        return [(match.group(1).strip(), match.group(2).strip()) for match in re.finditer(pattern, response, re.DOTALL)]

    def extract_backticked_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        pattern = r"`([^`\n]+\.(?:c|h))`\s*```[a-zA-Z0-9_+-]*\n(.*?)\n```"
        return [(match.group(1).strip(), match.group(2).strip()) for match in re.finditer(pattern, response, re.DOTALL)]

    def extract_bold_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        pattern = r"\*\*([^*\n]+\.(?:c|h))\*\*\s*```[a-zA-Z0-9_+-]*\n(.*?)\n```"
        return [(match.group(1).strip(), match.group(2).strip()) for match in re.finditer(pattern, response, re.DOTALL)]

    def extract_heading_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        pattern = r"(?:^|\n)(?:#+\s*)?([A-Za-z0-9_./\\-]+\.(?:c|h))\s*\n```[a-zA-Z0-9_+-]*\n(.*?)\n```"
        return [(match.group(1).strip(), match.group(2).strip()) for match in re.finditer(pattern, response, re.DOTALL)]

    def extract_plain_path_blocks(self, response: str) -> List[Tuple[str, str]]:
        pattern = r"([A-Za-z0-9_./\\-]+\.(?:c|h))\s*```[a-zA-Z0-9_+-]*\n(.*?)\n```"
        return [(match.group(1).strip(), match.group(2).strip()) for match in re.finditer(pattern, response, re.DOTALL)]
