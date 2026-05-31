"""Shared utils module."""

import hashlib
import re
from typing import Any


def generate_id(data: str) -> str:
    """Generate unique ID from data."""
    return hashlib.sha256(data.encode()).hexdigest()[:16]


def merge_dicts(base: dict, update: dict) -> dict:
    """Merge two dictionaries."""
    result = base.copy()
    result.update(update)
    return result


# =============================================================================
# Language Detection Utilities
# =============================================================================

# Vietnamese diacritics pattern - matches Vietnamese characters with diacritics
VIETNAMESE_DIACRITICS = (
    "àáạảãâầấậẩẫăằắặẳẵ"
    "èéẹẻẽêềếệểễ"
    "ìíịỉĩ"
    "òóọỏõôồốộổỗơờớợởỡ"
    "ùúụủũưừứựửữ"
    "ỳýỵỷỹ"
    "đ"
    "ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴ"
    "ÈÉẸẺẼÊỀẾỆỂỄ"
    "ÌÍỊỈĨ"
    "ÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠ"
    "ÙÚỤỦŨƯỪỨỰỬỮ"
    "ỲÝỴỶỸ"
    "Đ"
)

# Vietnamese keyword indicators (case-insensitive patterns)
VIETNAMESE_PATTERNS = [
    r"\bXin chào\b",
    r"\bChào\b",
    r"\bCảm ơn\b",
    r"\bTôi\b",
    r"\bLàm sao\b",
    r"\bGiúp\b",
    r"\bHỏi\b",
    r"\bCho tôi\b",
    r"\bthêm\b",
    r"\btạo\b",
    r"\bsửa\b",
    r"\bở đâu\b",
    r"\bnào\b",
    r"\bđược không\b",
    r"\bcó thể\b",
    r"\bmong muốn\b",
    r"\bmuốn\b",
]

# English keyword indicators (case-insensitive patterns)
ENGLISH_PATTERNS = [
    r"\bHello\b",
    r"\bHi\b",
    r"\bThanks\b",
    r"\bThank you\b",
    r"\bI need\b",
    r"\bHow do\b",
    r"\bHelp\b",
    r"\bCan you\b",
    r"\bPlease\b",
    r"\badd\b",
    r"\bcreate\b",
    r"\bfix\b",
    r"\bwhere\b",
    r"\bwhat\b",
    r"\bhow\b",
    r"\bwhy\b",
    r"\bcan I\b",
    r"\bcould you\b",
    r"\bwould you\b",
    r"\bshould I\b",
]

# Unicode ranges for CJK languages
UNICODE_RANGES = {
    "zh": (0x4E00, 0x9FFF),      # Chinese (CJK Unified Ideographs)
    "ja": (0x3040, 0x309F),      # Japanese Hiragana
    "ja2": (0x30A0, 0x30FF),     # Japanese Katakana
    "ko": (0xAC00, 0xD7AF),      # Korean Hangul Syllables
}

# Compile patterns for performance
_vietnamese_re = re.compile("|".join(VIETNAMESE_PATTERNS), re.IGNORECASE)
_english_re = re.compile("|".join(ENGLISH_PATTERNS), re.IGNORECASE)
_vietnamese_diacritics_re = re.compile(f"[{VIETNAMESE_DIACRITICS}]")


def detect_language(text: str) -> str:
    """
    Detect the language of input text.

    Supports: Vietnamese (vi), English (en), Chinese (zh), Japanese (ja), Korean (ko).

    Detection priority:
    1. CJK Unicode range detection (Chinese/Japanese/Korean)
    2. Vietnamese keyword patterns + diacritics
    3. English keyword patterns
    4. Default to 'en'

    Args:
        text: Input text to detect language for.

    Returns:
        Language code: 'vi', 'en', 'zh', 'ja', or 'ko'.

    Examples:
        >>> detect_language("Xin chào, bạn khỏe không?")
        'vi'
        >>> detect_language("Hello, how can I help you?")
        'en'
        >>> detect_language("你好，请问有什么可以帮助的？")
        'zh'
    """
    if not text or not text.strip():
        return "en"  # Default to English for empty input

    # Step 1: Check for CJK Unicode ranges first (most definitive)
    cjk_counts = _count_cjk_characters(text)
    if cjk_counts:
        # Return the dominant CJK language
        dominant = max(cjk_counts.items(), key=lambda x: x[1])
        if dominant[1] > 0:
            return dominant[0]

    # Step 2: Check for Vietnamese patterns
    vi_pattern_match = _vietnamese_re.search(text)
    vi_diacritics = len(_vietnamese_diacritics_re.findall(text))

    if vi_pattern_match or vi_diacritics >= 2:
        # If we have Vietnamese patterns or significant diacritics
        return "vi"

    # Step 3: Check for English patterns
    en_pattern_match = _english_re.search(text)
    if en_pattern_match:
        return "en"

    # Step 4: Check for Vietnamese diacritics (even without patterns)
    if vi_diacritics >= 1:
        return "vi"

    # Step 5: Default to English
    return "en"


def _count_cjk_characters(text: str) -> dict[str, int]:
    """Count characters in each CJK Unicode range."""
    counts: dict[str, int] = {}

    for char in text:
        code_point = ord(char)

        # Chinese range
        if UNICODE_RANGES["zh"][0] <= code_point <= UNICODE_RANGES["zh"][1]:
            counts["zh"] = counts.get("zh", 0) + 1
        # Japanese Hiragana range
        elif UNICODE_RANGES["ja"][0] <= code_point <= UNICODE_RANGES["ja"][1]:
            counts["ja"] = counts.get("ja", 0) + 1
        # Japanese Katakana range
        elif UNICODE_RANGES["ja2"][0] <= code_point <= UNICODE_RANGES["ja2"][1]:
            counts["ja"] = counts.get("ja", 0) + 1
        # Korean Hangul range
        elif UNICODE_RANGES["ko"][0] <= code_point <= UNICODE_RANGES["ko"][1]:
            counts["ko"] = counts.get("ko", 0) + 1

    return counts


def get_language_display_name(lang_code: str) -> str:
    """
    Get the human-readable display name for a language code.

    Args:
        lang_code: Language code ('vi', 'en', 'zh', 'ja', 'ko').

    Returns:
        Human-readable language name.
    """
    names = {
        "vi": "Tiếng Việt",
        "en": "English",
        "zh": "中文",
        "ja": "日本語",
        "ko": "한국어",
    }
    return names.get(lang_code, lang_code.upper())


def get_language_system_prompt_suffix(lang_code: str) -> str:
    """
    Get a system prompt suffix to instruct the LLM to respond in the detected language.

    Args:
        lang_code: Language code.

    Returns:
        A prompt suffix instructing the LLM to use the appropriate language.
    """
    suffixes = {
        "vi": "\n\nPlease respond in Vietnamese (Tiếng Việt).",
        "en": "",  # Default, no suffix needed
        "zh": "\n\n请用中文回复。",
        "ja": "\n\n日本語でお答えください。",
        "ko": "\n\n한국어로 답변해 주세요.",
    }
    return suffixes.get(lang_code, "")
