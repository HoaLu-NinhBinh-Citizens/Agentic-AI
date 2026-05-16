import re
from typing import Dict, List

from src.core.config.agent_prompts import GENERIC_QUERY_STOPWORDS
from src.infrastructure.models import DomainProfile, RetrievalQuery


class QueryAnalyzer:
    """Infer retrieval intent and extract task entities before searching."""

    DOMAIN_PROFILES: Dict[str, DomainProfile] = {
        "generic_document": DomainProfile(
            name="generic_document",
            preferred_doc_types=("textbook", "manual", "guide", "reference"),
        ),
        "stm32_embedded": DomainProfile(
            name="stm32_embedded",
            family_tokens=("stm32", "cortex", "cmsis"),
            chip_tokens=("stm32f", "stm32g", "stm32h", "stm32l", "stm32u", "stm32wb"),
            keyword_markers=("uart", "usart", "gpio", "dma", "nvic", "rcc", "timer", "register", "irq", "alternate function"),
            preferred_doc_types=("reference_manual", "datasheet", "application_note"),
            avoid_doc_types=("schematic",),
        ),
        "esp32_embedded": DomainProfile(
            name="esp32_embedded",
            family_tokens=("esp32", "esp-idf", "freertos"),
            chip_tokens=("esp32", "esp32s", "esp32c", "esp32h", "esp32p"),
            keyword_markers=("uart", "gpio", "spi", "i2c", "interrupt", "dma", "idf"),
            preferred_doc_types=("technical_reference", "datasheet", "programming_guide"),
        ),
        "nrf_embedded": DomainProfile(
            name="nrf_embedded",
            family_tokens=("nrf", "nordic", "zephyr"),
            chip_tokens=("nrf52", "nrf53", "nrf54", "nrf91"),
            keyword_markers=("uart", "gpio", "ppi", "gpiote", "interrupt", "zephyr"),
            preferred_doc_types=("product_specification", "reference_manual", "infocenter"),
        ),
        "rp2040_embedded": DomainProfile(
            name="rp2040_embedded",
            family_tokens=("rp2040", "pico", "pico-sdk"),
            chip_tokens=("rp2040",),
            keyword_markers=("pio", "uart", "gpio", "dma", "irq", "clock"),
            preferred_doc_types=("datasheet", "sdk_guide", "reference"),
        ),
    }

    def analyze(self, task: str, build_error: str = "", review_feedback: str = "") -> RetrievalQuery:
        raw_query = " ".join(part for part in [task, build_error, review_feedback] if part).strip()
        text = raw_query.lower()
        intent = "answer"
        if build_error:
            intent = "fix_build"
        elif review_feedback:
            intent = "repair_codegen"
        elif any(term in text for term in ("generate", "write", "implement", "driver", "code")):
            intent = "codegen"
        elif any(term in text for term in ("summarize", "summary", "compare", "extract", "table", "chapter", "section")):
            intent = "document_analysis"

        domain_profile = self._detect_domain_profile(text)

        entities: Dict[str, List[str]] = {
            "chips": re.findall(r"(?:stm32[a-z0-9]+|esp32[a-z0-9-]*|nrf\d+[a-z0-9]*|rp2040|atmega\d+|pic32[a-z0-9]+)", text),
            "peripherals": sorted({match.upper() for match in re.findall(r"uart|usart|gpio|dma|nvic|timer|tim\d*|clock|rcc|spi|i2c|pio|gpiote|ppi", text)}),
            "pages": self._extract_page_references(raw_query),
            "section_terms": self._extract_section_terms(raw_query),
            "register_terms": self._extract_register_terms(raw_query),
            "bitfield_terms": self._extract_bitfield_terms(raw_query),
            "symbols": re.findall(r"[A-Za-z_][A-Za-z0-9_]+", raw_query)[:12],
            "keywords": self._extract_keywords(raw_query),
        }
        filters: Dict[str, str] = {}
        if build_error:
            filters["source_type"] = "code"
        if domain_profile != "generic_document":
            filters["domain"] = domain_profile
        return RetrievalQuery(
            raw_query=raw_query or task,
            normalized_query=" ".join(re.findall(r"[a-z0-9_]+", text)),
            intent=intent,
            domain_profile=domain_profile,
            entities=entities,
            filters=filters,
            top_k=3,
        )

    def _detect_domain_profile(self, text: str) -> str:
        profile_matches = [
            ("stm32_embedded", ("stm32", "stm32f", "stm32g", "stm32h", "stm32l", "stm32u", "stm32wb")),
            ("esp32_embedded", ("esp32", "esp-idf")),
            ("nrf_embedded", ("nrf", "nordic", "zephyr")),
            ("rp2040_embedded", ("rp2040", "pico-sdk", "raspberry pi pico")),
        ]
        for profile_name, markers in profile_matches:
            if any(marker in text for marker in markers):
                return profile_name
        return "generic_document"

    def _extract_keywords(self, text: str) -> List[str]:
        terms = []
        seen = set()
        for token in re.findall(r"[a-z0-9_]+", text.lower()):
            if len(token) < 3 or token in GENERIC_QUERY_STOPWORDS or token in seen:
                continue
            seen.add(token)
            terms.append(token)
        return terms[:16]

    def _extract_page_references(self, text: str) -> List[str]:
        pages: List[str] = []
        for match in re.finditer(r"\b(?:page|trang|pagina|seite)\s+(\d{1,4})\b", text, re.IGNORECASE):
            page = match.group(1).strip()
            if page and page not in pages:
                pages.append(page)
        return pages[:6]

    def _extract_section_terms(self, text: str) -> List[str]:
        terms: List[str] = []
        patterns = [
            r"\bsection\s+([A-Za-z0-9_.-]{1,32})",
            r"\bchapter\s+([A-Za-z0-9_.-]{1,32})",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                token = match.group(1).strip()
                if token and token.lower() not in (term.lower() for term in terms):
                    terms.append(token)
        return terms[:8]

    def _extract_register_terms(self, text: str) -> List[str]:
        matches = re.findall(r"\b(?:RCC|GPIO[A-Ix]?|USART[1-6x]?|DMA[12x]?|TIMx?|NVIC)_[A-Z0-9]+\b", text)
        matches.extend(re.findall(r"\b(?:BRR|CR1|CR2|CR3|SR|DR|MODER|OTYPER|OSPEEDR|PUPDR|AFRL|AFRH|AHB1ENR|APB1ENR|APB2ENR|SxCR|SxNDTR|SxPAR|SxM0AR)\b", text))
        deduped: List[str] = []
        for item in matches:
            if item not in deduped:
                deduped.append(item)
        return deduped[:12]

    def _extract_bitfield_terms(self, text: str) -> List[str]:
        matches = re.findall(r"\b(?:AF\d+|UE|TE|RE|RXNE|TXE|TC|DMAT|DMAR|RXNEIE|CHSEL|DIR|MINC|PINC|TCIE|EN|SW|SWS|PLLM|PLLN|PLLP)\b", text)
        deduped: List[str] = []
        for item in matches:
            if item not in deduped:
                deduped.append(item)
        return deduped[:16]

