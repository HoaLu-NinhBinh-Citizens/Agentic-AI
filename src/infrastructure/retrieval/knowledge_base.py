import json
import re
from pathlib import Path
from typing import Dict, List, Optional

from src.core.config.agent_prompts import REFERENCE_KB_CANDIDATES
from src.core.config.chapter_config import STM32F407_REGISTER_HINTS


class ReferenceKnowledgeBase:
    """Lightweight local retrieval over the prebuilt PDF knowledge base."""

    def __init__(self, search_root: str = "."):
        self.search_root = Path(search_root).resolve()
        self.kb_path = self._find_kb_path()
        self.data = self._load()

    def _find_kb_path(self) -> Optional[Path]:
        for candidate in REFERENCE_KB_CANDIDATES:
            path = (self.search_root / candidate).resolve()
            if path.exists():
                return path
        for path in self.search_root.rglob("pdf_knowledge_base.json"):
            return path.resolve()
        return None

    def _load(self) -> Dict:
        if not self.kb_path:
            return {}
        try:
            return json.loads(self.kb_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def query(self, task: str, limit: int = 3) -> List[Dict[str, str]]:
        """Return the most relevant reference snippets for a task."""
        documents = self.data.get("documents", {})
        if not isinstance(documents, dict):
            return []

        query_terms = self._extract_query_terms(task)
        scored = []
        for key, doc in documents.items():
            score = self._score_document(key, doc, query_terms)
            if score <= 0:
                continue
            scored.append((score, key, doc))

        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for _, key, doc in scored[:limit]:
            results.append({
                "id": key,
                "filename": doc.get("filename", key),
                "summary": doc.get("summary", ""),
                "topics": ", ".join(doc.get("topics", [])[:5]),
                "chapters": ", ".join(doc.get("chapters", [])[:6]),
                "use_cases": ", ".join(doc.get("use_cases", [])[:4]),
                "preview": doc.get("content_preview", ""),
            })
        return results

    def query_register_hints(self, task: str, chapter: str, chip: str = "") -> Dict[str, List[str]]:
        """Return register-level hints synthesized from KB metadata and chapter rules."""
        refs = self.query(f"{task} {chip} {chapter}", limit=2)
        chapter_hints = STM32F407_REGISTER_HINTS.get(chapter, {}) if chip.upper() == "STM32F407" else {}
        registers = list(chapter_hints.get("registers", []))
        bitfields = list(chapter_hints.get("bitfields", []))
        notes = list(chapter_hints.get("notes", []))
        sources: List[str] = []

        for ref in refs:
            label = ref.get("filename") or ref.get("id") or "reference"
            sources.append(str(label))
            topic_text = " ".join([
                ref.get("summary", ""),
                ref.get("topics", ""),
                ref.get("chapters", ""),
                ref.get("preview", ""),
            ])
            self._extend_register_hints_from_text(topic_text, registers, bitfields)

        return {
            "registers": registers[:16],
            "bitfields": bitfields[:16],
            "notes": notes[:8],
            "sources": sources[:4],
        }

    def _extract_query_terms(self, task: str) -> List[str]:
        text = task.lower()
        base_terms = set(re.findall(r"[a-z0-9_]+", text))

        if "stm32" in text:
            base_terms.update({"stm32", "cortex", "gpio", "clock"})
        if "stm32f407" in text or "f407" in text:
            base_terms.update({"stm32f407", "f407", "uart", "usart", "dma", "interrupt"})
        if "uart" in text or "usart" in text:
            base_terms.update({"uart", "usart", "serial", "baud", "tx", "rx"})
        if "dma" in text:
            base_terms.add("dma")
        if "timer" in text:
            base_terms.add("timer")
        return sorted(base_terms)

    def _score_document(self, key: str, doc: Dict, query_terms: List[str]) -> int:
        haystack_parts = [
            key,
            doc.get("filename", ""),
            doc.get("summary", ""),
            doc.get("content_preview", ""),
            " ".join(doc.get("topics", [])),
            " ".join(doc.get("key_phrases", [])),
            " ".join(doc.get("chapters", [])),
            " ".join(doc.get("use_cases", [])),
        ]
        haystack = " ".join(haystack_parts).lower()
        score = 0
        for term in query_terms:
            if term in haystack:
                score += 2

        if "stm32f407" in haystack:
            score += 6
        if "reference manual" in haystack:
            score += 4
        if "uart" in haystack or "usart" in haystack:
            score += 3
        if "implementing peripheral drivers" in haystack:
            score += 2
        return score

    def _extend_register_hints_from_text(self, text: str, registers: List[str], bitfields: List[str]):
        """Pull obvious register-like tokens from reference metadata text."""
        register_matches = re.findall(r"\b(?:RCC|GPIO[A-Ix]?|USART[1-6x]?|DMA[12x]?|TIMx?|NVIC)_[A-Z0-9]+\b", text)
        bitfield_matches = re.findall(r"\b(?:AF\d+|UE|TE|RE|RXNE|TXE|TC|DMAT|DMAR|RXNEIE|CHSEL|DIR|MINC|PINC|TCIE|EN|SW|SWS|PLLM|PLLN|PLLP)\b", text)
        for item in register_matches:
            if item not in registers:
                registers.append(item)
        for item in bitfield_matches:
            if item not in bitfields:
                bitfields.append(item)

