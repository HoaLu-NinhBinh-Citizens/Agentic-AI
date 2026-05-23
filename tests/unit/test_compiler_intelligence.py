"""Tests for compiler intelligence."""

import pytest
from src.infrastructure.analysis.compiler_intelligence import (
    CompilerIntelligence,
    ABIAnalyzer,
    InlineAsm,
)


class TestCompilerIntelligence:
    def test_intelligence_creation(self):
        intel = CompilerIntelligence()
        assert intel is not None

    def test_analyze_elf(self):
        intel = CompilerIntelligence()
        result = intel.analyze_elf("test.elf")
        assert "functions" in result


class TestABIAnalyzer:
    def test_analyzer_creation(self):
        analyzer = ABIAnalyzer()
        assert analyzer is not None

    def test_check_stack_alignment(self):
        from src.infrastructure.analysis.compiler_intelligence import FunctionInfo
        
        analyzer = ABIAnalyzer()
        func = FunctionInfo(
            name="test_func",
            linkage_name="test_func",
            address=0x100,
            low_pc=0x100,
            high_pc=0x200,
        )
        violations = analyzer.check_stack_alignment(func)
        assert isinstance(violations, list)


class TestInlineAsmAnalyzer:
    def test_analyzer_creation(self):
        from src.infrastructure.analysis.compiler_intelligence import InlineAsmAnalyzer
        analyzer = InlineAsmAnalyzer()
        assert analyzer is not None

    def test_analyze_valid_asm(self):
        from src.infrastructure.analysis.compiler_intelligence import InlineAsmAnalyzer, InlineAsm
        
        analyzer = InlineAsmAnalyzer()
        asm = InlineAsm(
            location="test.c:10",
            assembly="mov r0, #0",
            constraints=["r"],
        )
        result = analyzer.analyze(asm)
        assert "valid" in result
