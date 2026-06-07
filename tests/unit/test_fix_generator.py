"""Unit tests for FixGenerator with template-first, LLM-fallback strategy.

Verifies template fix selection for common error patterns, LLM fallback
invocation, and the generate_fix() orchestration.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
"""

from __future__ import annotations

import pytest

from infrastructure.analysis.universal_repo.fix_generator import (
    FileContext,
    FixGenerator,
    MAX_RANKED_FIXES,
    TEMPLATE_CONFIDENCE_HIGH,
    TEMPLATE_CONFIDENCE_MEDIUM,
)
from infrastructure.analysis.universal_repo.models import (
    CompilerError,
    FixPatch,
    NO_CONFIDENT_FIX_THRESHOLD,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


class FakeLLMResponse:
    """Fake LLM response for testing."""

    def __init__(self, content: str):
        self.content = content


class FakeLLMProvider:
    """Fake LLM provider that returns a canned response."""

    def __init__(self, response_text: str = "", available: bool = True):
        self._response_text = response_text
        self._available = available
        self.calls: list[dict] = []

    def is_available(self) -> bool:
        return self._available

    async def generate(
        self,
        prompt: str,
        system_prompt=None,
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> FakeLLMResponse:
        self.calls.append({
            "prompt": prompt,
            "system_prompt": system_prompt,
            "temperature": temperature,
            "max_tokens": max_tokens,
        })
        return FakeLLMResponse(content=self._response_text)


class ErrorLLMProvider:
    """Fake LLM provider that raises an exception."""

    def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, **kwargs) -> FakeLLMResponse:
        raise RuntimeError("LLM service unavailable")


def _make_error(
    compiler: str = "gcc",
    error_code: str = "",
    message: str = "some error",
    file_path: str = "main.c",
    line: int = 10,
    column: int = 1,
    severity: str = "error",
) -> CompilerError:
    return CompilerError(
        file_path=file_path,
        line=line,
        column=column,
        severity=severity,
        error_code=error_code,
        message=message,
        compiler=compiler,
    )


def _make_context(file_path: str = "main.c") -> FileContext:
    return FileContext(
        file_path=file_path,
        content="int main() { return 0; }",
        surrounding_lines=["int main() {", "    return 0;", "}"],
    )


# ─── Template Fix Tests ──────────────────────────────────────────────────────


class TestTemplateFixes:
    """Test template-based fix selection for known patterns."""

    def test_missing_semicolon_tsc(self):
        """TSC TS1005 missing semicolon produces template fix."""
        gen = FixGenerator()
        error = _make_error(
            compiler="tsc",
            error_code="TS1005",
            message="';' expected.",
            file_path="app.ts",
        )
        fix = gen.get_template_fix(error)

        assert fix is not None
        assert fix.source == "template"
        assert fix.confidence == TEMPLATE_CONFIDENCE_HIGH
        assert ";" in fix.new_code
        assert fix.file_path == "app.ts"

    def test_undeclared_identifier_gcc_known_function(self):
        """GCC undeclared identifier for printf suggests stdio.h include."""
        gen = FixGenerator()
        error = _make_error(
            compiler="gcc",
            error_code="",
            message="implicit declaration of function 'printf'",
            file_path="main.c",
        )
        fix = gen.get_template_fix(error)

        assert fix is not None
        assert fix.source == "template"
        assert fix.confidence == TEMPLATE_CONFIDENCE_MEDIUM
        assert "#include <stdio.h>" in fix.new_code

    def test_undeclared_identifier_gcc_malloc(self):
        """GCC undeclared identifier for malloc suggests stdlib.h."""
        gen = FixGenerator()
        error = _make_error(
            compiler="gcc",
            error_code="",
            message="implicit declaration of function 'malloc'",
            file_path="alloc.c",
        )
        fix = gen.get_template_fix(error)

        assert fix is not None
        assert "#include <stdlib.h>" in fix.new_code

    def test_undeclared_identifier_gcc_unknown_function(self):
        """GCC undeclared identifier for unknown function returns None."""
        gen = FixGenerator()
        error = _make_error(
            compiler="gcc",
            error_code="",
            message="implicit declaration of function 'my_custom_func'",
            file_path="main.c",
        )
        fix = gen.get_template_fix(error)

        assert fix is None

    def test_missing_import_tsc(self):
        """TSC TS2304 Cannot find name suggests import."""
        gen = FixGenerator()
        error = _make_error(
            compiler="tsc",
            error_code="TS2304",
            message="Cannot find name 'Router'",
            file_path="app.ts",
        )
        fix = gen.get_template_fix(error)

        assert fix is not None
        assert fix.source == "template"
        assert "import" in fix.new_code
        assert "Router" in fix.new_code

    def test_unused_variable_gcc(self):
        """GCC unused variable warning suggests (void) cast."""
        gen = FixGenerator()
        error = _make_error(
            compiler="gcc",
            error_code="",
            message="unused variable 'count'",
            file_path="main.c",
            severity="warning",
        )
        fix = gen.get_template_fix(error)

        assert fix is not None
        assert fix.source == "template"
        assert "(void)count;" in fix.new_code
        assert fix.confidence == TEMPLATE_CONFIDENCE_HIGH

    def test_no_template_for_unknown_error(self):
        """Unknown error pattern returns None from template."""
        gen = FixGenerator()
        error = _make_error(
            compiler="rustc",
            error_code="E0599",
            message="no method named `foo` found for struct `Bar`",
            file_path="main.rs",
        )
        fix = gen.get_template_fix(error)

        assert fix is None

    def test_template_fix_has_error_ref(self):
        """Template fix includes reference to original error."""
        gen = FixGenerator()
        error = _make_error(
            compiler="tsc",
            error_code="TS1005",
            message="';' expected.",
        )
        fix = gen.get_template_fix(error)

        assert fix is not None
        assert fix.error_ref is error


# ─── LLM Fix Tests ──────────────────────────────────────────────────────────


class TestLLMFix:
    """Test LLM-based fix generation."""

    @pytest.mark.asyncio
    async def test_llm_fix_parses_valid_response(self):
        """Valid LLM response is parsed into FixPatch."""
        response_text = (
            "CONFIDENCE: 0.75\n"
            "EXPLANATION: Add return type annotation\n"
            "OLD_CODE: function foo() {\n"
            "NEW_CODE: function foo(): void {"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        error = _make_error(compiler="tsc", error_code="TS7030", message="Not all code paths return a value.")
        context = _make_context("app.ts")

        fix = await gen.get_llm_fix(error, context)

        assert fix is not None
        assert fix.source == "llm"
        assert fix.confidence == 0.75
        assert fix.explanation == "Add return type annotation"
        assert "function foo()" in fix.old_code
        assert "function foo(): void" in fix.new_code
        assert fix.error_ref is error

    @pytest.mark.asyncio
    async def test_llm_fix_returns_none_when_no_provider(self):
        """No LLM provider returns None."""
        gen = FixGenerator(llm_provider=None)
        error = _make_error()
        context = _make_context()

        fix = await gen.get_llm_fix(error, context)
        assert fix is None

    @pytest.mark.asyncio
    async def test_llm_fix_returns_none_when_provider_unavailable(self):
        """Unavailable LLM provider returns None."""
        provider = FakeLLMProvider(available=False)
        gen = FixGenerator(llm_provider=provider)
        error = _make_error()
        context = _make_context()

        fix = await gen.get_llm_fix(error, context)
        assert fix is None

    @pytest.mark.asyncio
    async def test_llm_fix_returns_none_on_invalid_response(self):
        """Unparseable LLM response returns None."""
        provider = FakeLLMProvider(response_text="I don't know how to fix this.")
        gen = FixGenerator(llm_provider=provider)
        error = _make_error()
        context = _make_context()

        fix = await gen.get_llm_fix(error, context)
        assert fix is None

    @pytest.mark.asyncio
    async def test_llm_fix_returns_none_on_provider_error(self):
        """LLM provider exception returns None gracefully."""
        gen = FixGenerator(llm_provider=ErrorLLMProvider())
        error = _make_error()
        context = _make_context()

        fix = await gen.get_llm_fix(error, context)
        assert fix is None

    @pytest.mark.asyncio
    async def test_llm_fix_clamps_confidence(self):
        """Confidence values are clamped to [0.0, 1.0]."""
        response_text = (
            "CONFIDENCE: 1.5\n"
            "EXPLANATION: Over-confident fix\n"
            "OLD_CODE: old\n"
            "NEW_CODE: new"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)
        error = _make_error()
        context = _make_context()

        fix = await gen.get_llm_fix(error, context)
        assert fix is not None
        assert fix.confidence == 1.0

    @pytest.mark.asyncio
    async def test_llm_prompt_includes_error_details(self):
        """LLM prompt includes error code, message, and context."""
        provider = FakeLLMProvider(response_text="incomplete")
        gen = FixGenerator(llm_provider=provider)

        error = _make_error(
            compiler="rustc",
            error_code="E0308",
            message="mismatched types",
            file_path="lib.rs",
            line=42,
        )
        context = FileContext(
            file_path="lib.rs",
            content="fn main() {}",
            surrounding_lines=["let x: i32 = \"hello\";"],
        )

        await gen.get_llm_fix(error, context)

        assert len(provider.calls) == 1
        prompt = provider.calls[0]["prompt"]
        assert "rustc" in prompt
        assert "E0308" in prompt
        assert "mismatched types" in prompt
        assert "lib.rs" in prompt
        assert "42" in prompt
        assert "let x: i32" in prompt


# ─── generate_fix() Orchestration Tests ──────────────────────────────────────


class TestGenerateFix:
    """Test the generate_fix() method orchestration."""

    @pytest.mark.asyncio
    async def test_returns_template_fix_without_calling_llm(self):
        """Template match short-circuits LLM call."""
        provider = FakeLLMProvider(response_text="should not be called")
        gen = FixGenerator(llm_provider=provider)

        error = _make_error(
            compiler="tsc",
            error_code="TS1005",
            message="';' expected.",
            file_path="app.ts",
        )
        context = _make_context("app.ts")

        fixes = await gen.generate_fix(error, context)

        assert len(fixes) == 1
        assert fixes[0].source == "template"
        assert len(provider.calls) == 0  # LLM not called

    @pytest.mark.asyncio
    async def test_falls_back_to_llm_when_no_template(self):
        """No template match triggers LLM fallback."""
        response_text = (
            "CONFIDENCE: 0.65\n"
            "EXPLANATION: Add error handling\n"
            "OLD_CODE: result = divide(a, b)\n"
            "NEW_CODE: result = divide(a, b) if b != 0 else 0"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        error = _make_error(
            compiler="rustc",
            error_code="E0599",
            message="no method named `divide` found",
            file_path="calc.rs",
        )
        context = _make_context("calc.rs")

        fixes = await gen.generate_fix(error, context)

        assert len(fixes) == 1
        assert fixes[0].source == "llm"
        assert len(provider.calls) == 1

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_fix_available(self):
        """Returns empty list when neither template nor LLM produces a fix."""
        gen = FixGenerator(llm_provider=None)

        error = _make_error(
            compiler="javac",
            error_code="",
            message="cannot find symbol",
            file_path="Main.java",
        )
        context = _make_context("Main.java")

        fixes = await gen.generate_fix(error, context)
        assert fixes == []


# ─── generate_fixes_ranked() Tests ───────────────────────────────────────────


class TestGenerateFixesRanked:
    """Test fix ranking and no-confident-fix fallback.

    Requirements: 6.4, 6.5, 6.6
    """

    @pytest.mark.asyncio
    async def test_ranked_returns_top_3(self):
        """When multiple fixes are generated, returns top 3 by confidence."""
        # Template fix will match (high confidence 0.9) + LLM returns another
        response_text = (
            "CONFIDENCE: 0.65\n"
            "EXPLANATION: Alternative LLM fix\n"
            "OLD_CODE: old_code\n"
            "NEW_CODE: new_code_llm"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        # Use an error that matches a template (TS1005 missing semicolon)
        error = _make_error(
            compiler="tsc",
            error_code="TS1005",
            message="';' expected.",
            file_path="app.ts",
        )
        context = _make_context("app.ts")

        fixes = await gen.generate_fixes_ranked(error, context)

        # Should get both template and LLM fixes, sorted by confidence
        assert len(fixes) <= MAX_RANKED_FIXES
        assert len(fixes) >= 1
        # First fix should have higher confidence (template = 0.9)
        assert fixes[0].confidence >= fixes[-1].confidence
        # All fixes include required fields
        for fix in fixes:
            assert fix.file_path == "app.ts"
            assert fix.explanation != ""
            assert fix.old_code is not None
            assert fix.new_code is not None

    @pytest.mark.asyncio
    async def test_ranked_no_confident_fix_threshold(self):
        """When no fix exceeds threshold, returns no_confident_fix sentinel."""
        # LLM returns a low-confidence fix
        response_text = (
            "CONFIDENCE: 0.2\n"
            "EXPLANATION: Uncertain fix\n"
            "OLD_CODE: old\n"
            "NEW_CODE: new"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        # Error that won't match any template
        error = _make_error(
            compiler="javac",
            error_code="",
            message="cannot find symbol",
            file_path="Main.java",
            line=5,
            column=10,
        )
        context = _make_context("Main.java")

        fixes = await gen.generate_fixes_ranked(error, context)

        assert len(fixes) == 1
        assert fixes[0].source == "no_confident_fix"
        assert fixes[0].confidence == 0.0
        assert "cannot find symbol" in fixes[0].explanation
        assert "Main.java" in fixes[0].explanation
        assert fixes[0].error_ref is error

    @pytest.mark.asyncio
    async def test_ranked_empty_candidates_returns_no_confident_fix(self):
        """When no fixes are generated at all, returns no_confident_fix."""
        gen = FixGenerator(llm_provider=None)

        error = _make_error(
            compiler="javac",
            error_code="",
            message="some obscure error",
            file_path="Foo.java",
            line=1,
            column=0,
        )
        context = _make_context("Foo.java")

        fixes = await gen.generate_fixes_ranked(error, context)

        assert len(fixes) == 1
        assert fixes[0].source == "no_confident_fix"
        assert fixes[0].confidence == 0.0

    @pytest.mark.asyncio
    async def test_ranked_sorts_by_confidence_descending(self):
        """Fixes are sorted by confidence, highest first."""
        response_text = (
            "CONFIDENCE: 0.55\n"
            "EXPLANATION: LLM fix\n"
            "OLD_CODE: old\n"
            "NEW_CODE: new_llm"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        # Template fix (0.9) + LLM fix (0.55)
        error = _make_error(
            compiler="tsc",
            error_code="TS1005",
            message="';' expected.",
            file_path="app.ts",
        )
        context = _make_context("app.ts")

        fixes = await gen.generate_fixes_ranked(error, context)

        assert len(fixes) >= 2
        assert fixes[0].confidence >= fixes[1].confidence

    @pytest.mark.asyncio
    async def test_ranked_fix_includes_location_and_explanation(self):
        """Each FixPatch includes file location and explanation."""
        response_text = (
            "CONFIDENCE: 0.8\n"
            "EXPLANATION: Fix the issue\n"
            "OLD_CODE: broken()\n"
            "NEW_CODE: fixed()"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        error = _make_error(
            compiler="go",
            error_code="",
            message="undefined: broken",
            file_path="main.go",
            line=42,
        )
        context = _make_context("main.go")

        fixes = await gen.generate_fixes_ranked(error, context)

        assert len(fixes) >= 1
        fix = fixes[0]
        assert fix.file_path == "main.go"
        assert fix.line_start == 42
        assert fix.explanation != ""


# ─── generate_fix_from_finding() Tests ───────────────────────────────────────


class TestGenerateFixFromFinding:
    """Test fix generation from Rule_Engine findings.

    Requirements: 6.1
    """

    @pytest.mark.asyncio
    async def test_generate_fix_from_finding_works(self):
        """Finding is converted to CompilerError and produces fixes."""
        from enum import Enum

        class FakeSeverity(Enum):
            ERROR = "error"

        class FakeFinding:
            rule_id = "no-unused-vars"
            rule_name = "Disallow unused variables"
            severity = FakeSeverity.ERROR
            file = "app.ts"
            line = 10
            end_line = 10
            column = 4
            message = "Variable 'x' is declared but never used"

        # Use LLM provider that returns a fix
        response_text = (
            "CONFIDENCE: 0.7\n"
            "EXPLANATION: Remove unused variable\n"
            "OLD_CODE: const x = 1;\n"
            "NEW_CODE: // removed unused variable"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        finding = FakeFinding()
        context = FileContext(
            file_path="app.ts",
            content="const x = 1;\nconsole.log('hello');",
            surrounding_lines=["const x = 1;", "console.log('hello');"],
        )

        fixes = await gen.generate_fix_from_finding(finding, context)

        assert len(fixes) == 1
        assert fixes[0].source == "llm"
        assert fixes[0].file_path == "app.ts"
        assert fixes[0].line_start == 10
        assert fixes[0].error_ref is not None
        assert fixes[0].error_ref.compiler == "static_analysis"
        assert fixes[0].error_ref.error_code == "no-unused-vars"

    @pytest.mark.asyncio
    async def test_generate_fix_from_finding_uses_message_fallback(self):
        """Finding with empty message uses rule_name as message."""
        from enum import Enum

        class FakeSeverity(Enum):
            WARNING = "warning"

        class FakeFinding:
            rule_id = "memory-leak"
            rule_name = "Potential memory leak detected"
            severity = FakeSeverity.WARNING
            file = "main.c"
            line = 20
            end_line = 25
            column = 0
            message = ""

        gen = FixGenerator(llm_provider=None)
        finding = FakeFinding()
        context = _make_context("main.c")

        # No LLM provider, no template for static_analysis → empty list
        fixes = await gen.generate_fix_from_finding(finding, context)

        # Even though no fix is returned, verify the method runs without error
        assert isinstance(fixes, list)

    @pytest.mark.asyncio
    async def test_generate_fix_from_finding_maps_severity_string(self):
        """Finding with string severity (not Enum) is handled gracefully."""
        class FakeFinding:
            rule_id = "lint-001"
            rule_name = "Style issue"
            severity = "warning"  # Plain string, not Enum
            file = "style.py"
            line = 5
            end_line = 5
            column = 0
            message = "Line too long"

        response_text = (
            "CONFIDENCE: 0.6\n"
            "EXPLANATION: Break long line\n"
            "OLD_CODE: very_long_line()\n"
            "NEW_CODE: short_line()"
        )
        provider = FakeLLMProvider(response_text=response_text)
        gen = FixGenerator(llm_provider=provider)

        finding = FakeFinding()
        context = _make_context("style.py")

        fixes = await gen.generate_fix_from_finding(finding, context)

        assert len(fixes) == 1
        assert fixes[0].error_ref.severity == "warning"
        assert fixes[0].error_ref.compiler == "static_analysis"
