"""Tests for TypeInferenceEngine — return type inference, branch narrowing."""
import pytest
from src.infrastructure.analysis.type_inference import TypeInferenceEngine, InferredType


@pytest.fixture
def engine():
    return TypeInferenceEngine()


class TestReturnTypeInference:
    """Test inferring function return types from return paths."""

    def test_single_return_literal(self, engine):
        code = 'def foo():\n    return 42\n'
        sigs = engine.infer_file(code)
        assert len(sigs) == 1
        assert sigs[0].return_type is not None
        assert sigs[0].return_type.type_str == "int"

    def test_single_return_string(self, engine):
        code = 'def greet():\n    return "hello"\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "str"

    def test_union_return_type(self, engine):
        code = '''
def foo(x):
    if x > 0:
        return "hello"
    else:
        return 123
'''
        sigs = engine.infer_file(code)
        assert sigs[0].return_type is not None
        ret = sigs[0].return_type.type_str
        assert "int" in ret and "str" in ret

    def test_none_return(self, engine):
        code = 'def noop():\n    pass\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "None"

    def test_explicit_none_return(self, engine):
        code = 'def maybe(x):\n    if x:\n        return x\n    return None\n'
        sigs = engine.infer_file(code)
        ret = sigs[0].return_type.type_str
        assert "None" in ret

    def test_annotation_takes_precedence(self, engine):
        code = 'def typed() -> list[int]:\n    return [1, 2, 3]\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "list[int]"
        assert sigs[0].return_type.confidence == 1.0

    def test_list_return(self, engine):
        code = 'def get_items():\n    return [1, 2, 3]\n'
        sigs = engine.infer_file(code)
        ret = sigs[0].return_type.type_str
        assert "list" in ret

    def test_bool_comparison_return(self, engine):
        code = 'def is_valid(x):\n    return x > 0\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "bool"

    def test_constructor_call_return(self, engine):
        code = 'def create():\n    return MyClass()\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "MyClass"

    def test_async_function(self, engine):
        code = 'async def fetch():\n    return "data"\n'
        sigs = engine.infer_file(code)
        assert sigs[0].is_async
        assert sigs[0].return_type.type_str == "str"


class TestExpressionInference:
    """Test type inference for individual expressions."""

    def test_fstring_is_str(self, engine):
        code = 'def fmt(x):\n    return f"value: {x}"\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "str"

    def test_dict_literal(self, engine):
        code = 'def config():\n    return {"key": "value"}\n'
        sigs = engine.infer_file(code)
        assert "dict" in sigs[0].return_type.type_str

    def test_builtin_call(self, engine):
        code = 'def count(items):\n    return len(items)\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "int"

    def test_division_returns_float(self, engine):
        code = 'def ratio(a, b):\n    return a / b\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "float"

    def test_floor_division_returns_int(self, engine):
        code = 'def half(x):\n    return x // 2\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "int"

    def test_tuple_return(self, engine):
        code = 'def pair():\n    return (1, "hello")\n'
        sigs = engine.infer_file(code)
        ret = sigs[0].return_type.type_str
        assert "tuple" in ret

    def test_ternary_same_type(self, engine):
        code = 'def pick(x):\n    return 1 if x else 2\n'
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "int"

    def test_ternary_different_types(self, engine):
        code = 'def pick(x):\n    return "yes" if x else 0\n'
        sigs = engine.infer_file(code)
        ret = sigs[0].return_type.type_str
        assert "str" in ret or "int" in ret


class TestParameterInference:
    """Test parameter type inference from annotations."""

    def test_annotated_params(self, engine):
        code = 'def add(a: int, b: int) -> int:\n    return a + b\n'
        sigs = engine.infer_file(code)
        assert sigs[0].params[0][1].type_str == "int"
        assert sigs[0].params[1][1].type_str == "int"

    def test_unannotated_params(self, engine):
        code = 'def add(a, b):\n    return a + b\n'
        sigs = engine.infer_file(code)
        assert sigs[0].params[0][1] is None
        assert sigs[0].params[1][1] is None


class TestEdgeCases:
    """Test edge cases for type inference."""

    def test_empty_file(self, engine):
        sigs = engine.infer_file("")
        assert sigs == []

    def test_syntax_error(self, engine):
        sigs = engine.infer_file("def broken(:\n    pass")
        assert sigs == []

    def test_generator_function(self, engine):
        code = 'def gen():\n    yield 1\n    yield 2\n'
        sigs = engine.infer_file(code)
        assert sigs[0].is_generator
        assert "Generator" in sigs[0].return_type.type_str

    def test_multiple_functions(self, engine):
        code = 'def a():\n    return 1\n\ndef b():\n    return "x"\n'
        sigs = engine.infer_file(code)
        assert len(sigs) == 2
        assert sigs[0].return_type.type_str == "int"
        assert sigs[1].return_type.type_str == "str"
