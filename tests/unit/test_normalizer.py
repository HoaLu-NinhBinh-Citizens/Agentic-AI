"""Unit tests for normalizer and key generator."""

import pytest

from src.infrastructure.cache.tool.normalizer import (
    KeyGenerator,
    NormalizationConfig,
    StrictNormalizer,
)


class TestStrictNormalizer:
    """Tests for StrictNormalizer."""

    @pytest.fixture
    def normalizer(self):
        """Create a fresh normalizer."""
        return StrictNormalizer()

    def test_normalize_dict_sorted(self, normalizer):
        """Test dict keys are sorted."""
        result = normalizer.normalize({"b": 2, "a": 1, "c": 3})

        keys = [k for k, v in result]
        assert keys == sorted(keys)

    def test_normalize_whitespace_trim(self, normalizer):
        """Test whitespace is trimmed."""
        result = normalizer.normalize({"key": "  value  "})

        for k, v in result:
            if k == "key":
                assert v == "value"

    def test_normalize_nested_dict(self, normalizer):
        """Test nested dict normalization."""
        result = normalizer.normalize({"outer": {"inner": "value"}})

        assert ("outer", {"inner": "value"}) in result

    def test_normalize_list(self, normalizer):
        """Test list normalization."""
        result = normalizer.normalize({"key": [1, 2, 3]})

        for k, v in result:
            if k == "key":
                assert v == [1, 2, 3]

    def test_normalize_preserves_types(self, normalizer):
        """Test types are preserved."""
        result = normalizer.normalize({
            "string": "value",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "null": None,
        })

        result_dict = dict(result)
        assert result_dict["string"] == "value"
        assert result_dict["int"] == 42
        assert result_dict["float"] == 3.14
        assert result_dict["bool"] is True
        assert result_dict["null"] is None

    def test_case_fold_config(self):
        """Test case fold configuration."""
        config = NormalizationConfig(case_fold=True)
        normalizer = StrictNormalizer(config)

        result = normalizer.normalize({"Key": "VALUE"})
        result_dict = dict(result)

        assert result_dict["key"] == "value"


class TestKeyGenerator:
    """Tests for KeyGenerator."""

    @pytest.fixture
    def generator(self):
        """Create a fresh key generator."""
        return KeyGenerator()

    def test_generate_key_deterministic(self, generator):
        """Test key generation is deterministic."""
        key1 = generator.generate("tool1", "1.0.0", {"arg": "value"})
        key2 = generator.generate("tool1", "1.0.0", {"arg": "value"})

        assert key1 == key2

    def test_different_args_different_key(self, generator):
        """Test different args produce different keys."""
        key1 = generator.generate("tool1", "1.0.0", {"arg": "value1"})
        key2 = generator.generate("tool1", "1.0.0", {"arg": "value2"})

        assert key1 != key2

    def test_different_tool_different_key(self, generator):
        """Test different tools produce different keys."""
        key1 = generator.generate("tool1", "1.0.0", {"arg": "value"})
        key2 = generator.generate("tool2", "1.0.0", {"arg": "value"})

        assert key1 != key2

    def test_different_version_different_key(self, generator):
        """Test different versions produce different keys."""
        key1 = generator.generate("tool1", "1.0.0", {"arg": "value"})
        key2 = generator.generate("tool1", "2.0.0", {"arg": "value"})

        assert key1 != key2

    def test_key_is_sha256(self, generator):
        """Test key is a valid SHA256 hash."""
        key = generator.generate("tool1", "1.0.0", {"arg": "value"})

        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_order_independent(self, generator):
        """Test key is independent of arg order."""
        key1 = generator.generate("tool1", "1.0.0", {"a": 1, "b": 2})
        key2 = generator.generate("tool1", "1.0.0", {"b": 2, "a": 1})

        assert key1 == key2
