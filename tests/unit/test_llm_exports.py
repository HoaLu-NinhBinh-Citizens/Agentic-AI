"""Regression test: provider adapter classes are exported from the package.

`component_factory` and `embedded_agent` import these names directly from
`src.infrastructure.llm`. They previously raised ImportError because the
package `__init__` did not re-export them.
"""


def test_provider_classes_importable_from_package():
    from src.infrastructure.llm import (
        BaseLLM,
        OllamaLLM,
        AnthropicLLM,
        GeminiLLM,
    )

    # They are concrete subclasses of the shared base.
    for cls in (OllamaLLM, AnthropicLLM, GeminiLLM):
        assert issubclass(cls, BaseLLM)


def test_provider_classes_in_all():
    import src.infrastructure.llm as llm_pkg

    for name in ("OllamaLLM", "AnthropicLLM", "GeminiLLM", "BaseLLM"):
        assert name in llm_pkg.__all__
