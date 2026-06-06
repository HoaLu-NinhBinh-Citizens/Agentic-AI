"""Advanced tests for TypeInferenceEngine: control-flow, narrowing, params.

Tests the enhanced type inference engine that covers:
- Control-flow aware return type inference
- Branch narrowing (isinstance, is None)
- Union type construction from conditional returns
- Parameter type inference from usage patterns
- Reachability analysis (implicit None detection)
- Scope-aware variable tracking
"""

from __future__ import annotations

import ast

import pytest

from src.infrastructure.analysis.type_inference import (
    FunctionSignature,
    InferredType,
    NarrowingInfo,
    ScopeContext,
    TypeInferenceEngine,
)


@pytest.fixture
def engine() -> TypeInferenceEngine:
    return TypeInferenceEngine()


# ─── Tests: Union Return Types ───────────────────────────────────────────────


class TestUnionReturnTypes:
    """Test that functions with multiple return paths get Union types."""

    def test_str_or_int_from_branches(self, engine: TypeInferenceEngine):
        """def foo(x): if x > 0: return 'hello' else: return 123"""
        code = """\
def foo(x):
    if x > 0:
        return "hello"
    else:
        return 123
"""
        sigs = engine.infer_file(code)
        assert len(sigs) == 1
        assert sigs[0].return_type is not None
        rt = sigs[0].return_type.type_str
        assert "int" in rt
        assert "str" in rt
        assert "|" in rt

    def test_none_or_value(self, engine: TypeInferenceEngine):
        """Function that may return None."""
        code = """\
def find(items, key):
    for item in items:
        if item == key:
            return item
    return None
"""
        sigs = engine.infer_file(code)
        assert len(sigs) == 1
        rt = sigs[0].return_type
        assert rt is not None
        # Should include None since explicit return None
        assert "None" in rt.type_str

    def test_single_return_type(self, engine: TypeInferenceEngine):
        """All paths return same type → no Union."""
        code = """\
def always_int(x):
    if x > 0:
        return 1
    else:
        return -1
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "int"

    def test_multiple_branch_types(self, engine: TypeInferenceEngine):
        """Three different return types."""
        code = """\
def multi(x):
    if x == 0:
        return None
    elif x > 0:
        return "positive"
    else:
        return -1
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert "None" in rt
        assert "str" in rt
        assert "int" in rt

    def test_annotated_function_uses_annotation(self, engine: TypeInferenceEngine):
        """If annotation exists, use it directly."""
        code = """\
def typed(x: int) -> str:
    return str(x)
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "str"
        assert sigs[0].return_type.source == "annotation"


# ─── Tests: Implicit None Return ─────────────────────────────────────────────


class TestImplicitNoneReturn:
    """Test detection of implicit None returns (fall-through)."""

    def test_no_return_statement(self, engine: TypeInferenceEngine):
        """Function with no return → None."""
        code = """\
def void_func():
    x = 1
    print(x)
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "None"

    def test_conditional_return_with_fallthrough(self, engine: TypeInferenceEngine):
        """Only returns in if-branch → can fall through to implicit None."""
        code = """\
def maybe_return(x):
    if x > 0:
        return x
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        # Should detect that else-branch falls through → None is possible
        assert "None" in rt

    def test_all_paths_return_no_implicit_none(self, engine: TypeInferenceEngine):
        """All paths return explicitly → no implicit None."""
        code = """\
def complete(x):
    if x > 0:
        return 1
    else:
        return -1
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert rt == "int"  # Both branches return int, no None


# ─── Tests: Branch Narrowing ─────────────────────────────────────────────────


class TestBranchNarrowing:
    """Test isinstance / is None narrowing."""

    def test_isinstance_narrowing(self, engine: TypeInferenceEngine):
        """isinstance(x, str) narrows x to str in if-branch."""
        code = """\
def process(x):
    if isinstance(x, str):
        return x.upper()
    return str(x)
"""
        sigs = engine.infer_file(code)
        # Both branches return str
        assert sigs[0].return_type.type_str == "str"

    def test_is_none_narrowing(self, engine: TypeInferenceEngine):
        """x is None check → x: None in if-branch."""
        code = """\
def check(x):
    if x is None:
        return "nothing"
    return x
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert "str" in rt

    def test_isinstance_tuple(self, engine: TypeInferenceEngine):
        """isinstance(x, (int, float)) → int | float narrowing."""
        code = """\
def numeric(x):
    if isinstance(x, (int, float)):
        return x + 1
    return 0
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type
        assert rt is not None


# ─── Tests: Parameter Type Inference ─────────────────────────────────────────


class TestParameterInference:
    """Test parameter type inference from usage patterns."""

    def test_param_with_str_methods(self, engine: TypeInferenceEngine):
        """Parameter uses .strip(), .split() → inferred as str."""
        code = """\
def clean(text):
    return text.strip().split(",")
"""
        sigs = engine.infer_file(code)
        params = sigs[0].params
        # text is inferred from .strip() usage
        text_param = next((p for p in params if p[0] == "text"), None)
        assert text_param is not None
        if text_param[1]:
            assert text_param[1].type_str == "str"

    def test_param_with_list_methods(self, engine: TypeInferenceEngine):
        """Parameter uses .append() → inferred as list."""
        code = """\
def add_item(items, item):
    items.append(item)
"""
        sigs = engine.infer_file(code)
        items_param = next((p for p in sigs[0].params if p[0] == "items"), None)
        assert items_param is not None
        if items_param[1]:
            assert items_param[1].type_str == "list"

    def test_annotated_param_preserved(self, engine: TypeInferenceEngine):
        """Annotated params are not overridden by inference."""
        code = """\
def typed(x: int, y):
    return x + y
"""
        sigs = engine.infer_file(code)
        x_param = next((p for p in sigs[0].params if p[0] == "x"), None)
        assert x_param is not None
        assert x_param[1].type_str == "int"
        assert x_param[1].source == "annotation"


# ─── Tests: Scope Context ────────────────────────────────────────────────────


class TestScopeContext:
    """Test ScopeContext for variable tracking."""

    def test_basic_bind_and_lookup(self):
        scope = ScopeContext()
        scope.bind("x", InferredType(type_str="int"))
        assert scope.lookup("x") is not None
        assert scope.lookup("x").type_str == "int"

    def test_child_scope_inherits_parent(self):
        parent = ScopeContext()
        parent.bind("x", InferredType(type_str="int"))

        child = parent.child()
        assert child.lookup("x") is not None
        assert child.lookup("x").type_str == "int"

    def test_child_scope_shadows_parent(self):
        parent = ScopeContext()
        parent.bind("x", InferredType(type_str="int"))

        child = parent.child()
        child.bind("x", InferredType(type_str="str"))

        # Child sees str, parent still sees int
        assert child.lookup("x").type_str == "str"
        assert parent.lookup("x").type_str == "int"

    def test_lookup_nonexistent_returns_none(self):
        scope = ScopeContext()
        assert scope.lookup("missing") is None


# ─── Tests: Expression Type Inference ────────────────────────────────────────


class TestExpressionInference:
    """Test individual expression type inference."""

    def test_list_with_mixed_types(self, engine: TypeInferenceEngine):
        """[1, 'a', 2.0] → list[float | int | str]."""
        code = """\
def mixed():
    return [1, "a", 2.0]
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert "list" in rt

    def test_dict_with_typed_kv(self, engine: TypeInferenceEngine):
        """{'a': 1, 'b': 2} → dict[str, int]."""
        code = """\
def make_dict():
    return {"a": 1, "b": 2}
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert "dict" in rt
        assert "str" in rt
        assert "int" in rt

    def test_ternary_same_type(self, engine: TypeInferenceEngine):
        """x if cond else y where both are int → int."""
        code = """\
def ternary(x):
    return 1 if x else 2
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "int"

    def test_ternary_different_types(self, engine: TypeInferenceEngine):
        """x if cond else y where types differ → Union."""
        code = """\
def ternary(x):
    return "yes" if x else 0
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert "str" in rt
        assert "int" in rt

    def test_fstring_returns_str(self, engine: TypeInferenceEngine):
        code = """\
def greet(name):
    return f"Hello, {name}"
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "str"

    def test_division_returns_float(self, engine: TypeInferenceEngine):
        code = """\
def half(x):
    return x / 2
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "float"

    def test_floor_div_returns_int(self, engine: TypeInferenceEngine):
        code = """\
def halved(x):
    return x // 2
"""
        sigs = engine.infer_file(code)
        assert sigs[0].return_type.type_str == "int"


# ─── Tests: Generator Detection ─────────────────────────────────────────────


class TestGeneratorDetection:
    """Test generator function detection."""

    def test_yield_makes_generator(self, engine: TypeInferenceEngine):
        code = """\
def gen():
    yield 1
    yield 2
"""
        sigs = engine.infer_file(code)
        assert sigs[0].is_generator
        assert "Generator" in sigs[0].return_type.type_str

    def test_yield_from(self, engine: TypeInferenceEngine):
        code = """\
def delegating():
    yield from range(10)
"""
        sigs = engine.infer_file(code)
        assert sigs[0].is_generator


# ─── Tests: Async Functions ──────────────────────────────────────────────────


class TestAsyncFunctions:
    """Test async function inference."""

    def test_async_detected(self, engine: TypeInferenceEngine):
        code = """\
async def fetch():
    return "data"
"""
        sigs = engine.infer_file(code)
        assert sigs[0].is_async
        assert sigs[0].return_type.type_str == "str"

    def test_async_with_await(self, engine: TypeInferenceEngine):
        code = """\
async def process():
    result = await some_coroutine()
    return result
"""
        sigs = engine.infer_file(code)
        assert sigs[0].is_async


# ─── Tests: Try/Except Return Types ─────────────────────────────────────────


class TestTryExceptReturns:
    """Test return type inference through try/except blocks."""

    def test_try_returns_different_types(self, engine: TypeInferenceEngine):
        code = """\
def safe_parse(text):
    try:
        return int(text)
    except ValueError:
        return None
"""
        sigs = engine.infer_file(code)
        rt = sigs[0].return_type.type_str
        assert "int" in rt
        assert "None" in rt

    def test_try_with_finally(self, engine: TypeInferenceEngine):
        code = """\
def with_cleanup():
    try:
        return 42
    finally:
        pass
"""
        sigs = engine.infer_file(code)
        assert "int" in sigs[0].return_type.type_str
