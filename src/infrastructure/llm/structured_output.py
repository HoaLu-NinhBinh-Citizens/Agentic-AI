"""
Structured output helpers for reliable JSON extraction and tool calling.

Provides:
- Robust JSON extraction from LLM responses (handles markdown, trailing commas, etc.)
- Tool/function calling support for both Ollama and OpenAI
- Structured output validation with Pydantic-like schemas
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Type, Callable

logger = logging.getLogger(__name__)


class StructuredOutputError(Exception):
    """Raised when structured output cannot be parsed or validated."""
    pass


class JSONExtractor:
    """
    Extracts JSON objects/arrays from LLM responses.

    Handles:
    - Markdown code blocks (```json ... ```)
    - Trailing commas
    - Single-quoted strings
    - Comments
    - Incomplete JSON
    - Multiple JSON blocks
    """

    def __init__(self):
        self._patterns = [
            # Markdown code block with json
            re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL),
            # Markdown code block without language
            re.compile(r"```\s*(\{.*?\})\s*```", re.DOTALL),
            # Markdown code block with js
            re.compile(r"```js\s*(\{.*?\})\s*```", re.DOTALL),
            # JSON object directly
            re.compile(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"),
            # JSON array
            re.compile(r"\[[\s\S]*\]"),
        ]

    def extract(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Extract the first JSON object from text.

        Returns None if no valid JSON found.
        """
        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                json_str = match.group(1) if match.lastindex else match.group(0)
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try cleaning
                    cleaned = self._clean_json(json_str)
                    try:
                        return json.loads(cleaned)
                    except json.JSONDecodeError:
                        continue
        return None

    def extract_array(self, text: str) -> Optional[List[Any]]:
        """Extract the first JSON array from text."""
        for pattern in self._patterns:
            match = pattern.search(text)
            if match:
                json_str = match.group(1) if match.lastindex else match.group(0)
                try:
                    result = json.loads(json_str)
                    if isinstance(result, list):
                        return result
                except json.JSONDecodeError:
                    cleaned = self._clean_json(json_str)
                    try:
                        result = json.loads(cleaned)
                        if isinstance(result, list):
                            return result
                    except json.JSONDecodeError:
                        continue
        return None

    def extract_all(self, text: str) -> List[Dict[str, Any]]:
        """Extract all JSON objects from text."""
        results = []
        for pattern in self._patterns:
            for match in pattern.finditer(text):
                json_str = match.group(1) if match.lastindex else match.group(0)
                try:
                    result = json.loads(json_str)
                    if isinstance(result, dict):
                        results.append(result)
                except json.JSONDecodeError:
                    cleaned = self._clean_json(json_str)
                    try:
                        result = json.loads(cleaned)
                        if isinstance(result, dict):
                            results.append(result)
                    except json.JSONDecodeError:
                        continue
        return results

    def _clean_json(self, text: str) -> str:
        """Clean up common JSON malformation issues."""
        # Remove trailing commas
        text = re.sub(r",\s*([}\]])", r"\1", text)
        # Remove single-line comments
        text = re.sub(r"//[^\n]*\n", "\n", text)
        # Remove multi-line comments
        text = re.sub(r"/\*[\s\S]*?\*/", "", text)
        # Replace single quotes with double quotes (strings only)
        # This is a simple heuristic - won't work for all cases
        result = []
        in_string = False
        for i, char in enumerate(text):
            if char == '"' and (i == 0 or text[i - 1] != "\\"):
                in_string = not in_string
                result.append(char)
            elif char == "'" and in_string:
                result.append('"')
            else:
                result.append(char)
        return "".join(result)


class StructuredOutputValidator:
    """
    Validates extracted JSON against a schema.

    Supports:
    - Required fields
    - Type checking
    - Enum values
    - Numeric ranges
    - String patterns (regex)
    """

    def __init__(self, schema: Dict[str, Any]):
        """
        Args:
            schema: Dict defining expected fields.
                e.g. {
                    "category": {"type": str, "required": True},
                    "confidence": {"type": float, "min": 0.0, "max": 1.0},
                    "model_recommendation": {"type": str, "enum": ["ollama", "openai"]},
                }
        """
        self.schema = schema

    def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate data against the schema.

        Returns (is_valid, list_of_errors).
        """
        errors = []

        for field, rules in self.schema.items():
            if rules.get("required", False) and field not in data:
                errors.append(f"Missing required field: {field}")
                continue

            if field not in data:
                continue

            value = data[field]
            expected_type = rules.get("type")

            # Type check
            if expected_type and not isinstance(value, expected_type):
                errors.append(
                    f"Field '{field}': expected {expected_type.__name__}, got {type(value).__name__}"
                )

            # Enum check
            if "enum" in rules and value not in rules["enum"]:
                errors.append(
                    f"Field '{field}': value {value!r} not in allowed values {rules['enum']}"
                )

            # Numeric range
            if isinstance(value, (int, float)):
                if "min" in rules and value < rules["min"]:
                    errors.append(f"Field '{field}': value {value} below minimum {rules['min']}")
                if "max" in rules and value > rules["max"]:
                    errors.append(f"Field '{field}': value {value} above maximum {rules['max']}")

            # String pattern
            if isinstance(value, str) and "pattern" in rules:
                if not re.search(rules["pattern"], value):
                    errors.append(f"Field '{field}': value does not match pattern {rules['pattern']}")

            # String length
            if isinstance(value, str):
                if "min_length" in rules and len(value) < rules["min_length"]:
                    errors.append(f"Field '{field}': length {len(value)} below minimum {rules['min_length']}")
                if "max_length" in rules and len(value) > rules["max_length"]:
                    errors.append(f"Field '{field}': length {len(value)} exceeds maximum {rules['max_length']}")

            # List length
            if isinstance(value, list):
                if "min_items" in rules and len(value) < rules["min_items"]:
                    errors.append(f"Field '{field}': {len(value)} items below minimum {rules['min_items']}")
                if "max_items" in rules and len(value) > rules["max_items"]:
                    errors.append(f"Field '{field}': {len(value)} items exceeds maximum {rules['max_items']}")

        return len(errors) == 0, errors


# Pre-defined schemas for common tasks
SCHEMA_TASK_CLASSIFICATION = {
    "category": {"type": str, "required": True},
    "confidence": {"type": float, "min": 0.0, "max": 1.0},
    "target_project": {"type": str, "required": False},
    "target_chip": {"type": str, "required": False},
    "subtasks": {"type": list, "required": False},
    "estimated_difficulty": {"type": str, "enum": ["low", "medium", "high"], "required": False},
    "model_recommendation": {"type": str, "enum": ["ollama", "openai"], "required": False},
    "reasoning": {"type": str, "required": False},
}

SCHEMA_REVIEW_RESPONSE = {
    "approved": {"type": bool, "required": True},
    "findings": {"type": list, "required": False},
    "required_fixes": {"type": list, "required": False},
    "unsupported_references": {"type": list, "required": False},
    "traceability_gaps": {"type": list, "required": False},
    "evidence_backing": {"type": list, "required": False},
}


def extract_structured_json(
    text: str,
    schema: Optional[Dict[str, Any]] = None,
    required_fields: Optional[List[str]] = None,
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """
    Extract JSON from LLM response and validate against schema.

    Returns (parsed_data, validation_errors).
    If parsing fails, returns (None, errors).
    """
    extractor = JSONExtractor()
    data = extractor.extract(text)

    if data is None:
        return None, ["No valid JSON found in response"]

    if schema:
        validator = StructuredOutputValidator(schema)
        is_valid, errors = validator.validate(data)
        if not is_valid:
            # Try extracting from all JSON blocks
            all_data = extractor.extract_all(text)
            for candidate in all_data:
                is_valid, errors = validator.validate(candidate)
                if is_valid:
                    return candidate, []
            return None, errors

    # Check required fields if no schema but required_fields provided
    if required_fields:
        missing = [f for f in required_fields if f not in data]
        if missing:
            return data, [f"Missing required fields: {', '.join(missing)}"]

    return data, []


def make_structured_prompt(
    base_prompt: str,
    output_schema: Dict[str, Any],
    examples: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Enhance a prompt to request structured JSON output.

    Args:
        base_prompt: The original prompt
        output_schema: Dict describing required output fields
        examples: Optional list of example outputs

    Returns:
        Enhanced prompt with JSON schema instructions
    """
    schema_lines = []
    for field, rules in output_schema.items():
        parts = [f"  - {field}"]
        if rules.get("type"):
            parts.append(f"({rules['type'].__name__})")
        if rules.get("enum"):
            parts.append(f" ∈ {rules['enum']}")
        if rules.get("required"):
            parts.append(" [REQUIRED]")
        if rules.get("min") is not None:
            parts.append(f" >= {rules['min']}")
        if rules.get("max") is not None:
            parts.append(f" <= {rules['max']}")
        schema_lines.append("".join(parts))

    schema_text = "\n".join(schema_lines)

    example_text = ""
    if examples:
        example_lines = ["Examples:"]
        for ex in examples:
            example_lines.append(json.dumps(ex, indent=2))
        example_text = "\n" + "\n".join(example_lines)

    return f"""{base_prompt}

Return your response as a single JSON object with this schema:
{schema_text}{example_text}

Respond with ONLY the JSON object. Do not add any explanation, markdown formatting, or surrounding text."""


# Global extractor instance for convenience
_default_extractor = JSONExtractor()


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Quick JSON extraction from text."""
    return _default_extractor.extract(text)


def extract_json_array(text: str) -> Optional[List[Any]]:
    """Quick JSON array extraction from text."""
    return _default_extractor.extract_array(text)


def extract_all_json(text: str) -> List[Dict[str, Any]]:
    """Extract all JSON objects from text."""
    return _default_extractor.extract_all(text)
