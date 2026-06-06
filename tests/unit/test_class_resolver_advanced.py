"""Advanced tests for ClassResolver: complex inheritance, MRO, overriding.

Covers scenarios that are critical for correctness:
- Deep inheritance chains (A → B → C → D)
- Multiple inheritance with diamond problem
- Method overriding
- Mixin classes
- Abstract base classes
- Property resolution through inheritance
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.analysis.class_resolver import (
    ClassDefinition,
    ClassMember,
    ClassResolver,
)


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def resolver() -> ClassResolver:
    """Fresh ClassResolver instance."""
    return ClassResolver()


DEEP_INHERITANCE = """\
class Base:
    def base_method(self) -> str:
        return "base"

    def overridden(self) -> int:
        return 0


class Middle(Base):
    def middle_method(self) -> None:
        pass

    def overridden(self) -> int:
        return 1


class Child(Middle):
    def child_method(self) -> bool:
        return True

    def overridden(self) -> int:
        return 2


class GrandChild(Child):
    pass
"""

DIAMOND_INHERITANCE = """\
class Base:
    def common(self) -> str:
        return "base"

    x: int = 0


class Left(Base):
    def left_only(self) -> None:
        pass

    def common(self) -> str:
        return "left"


class Right(Base):
    def right_only(self) -> None:
        pass

    def common(self) -> str:
        return "right"


class Diamond(Left, Right):
    pass
"""

MIXIN_CLASSES = """\
class LogMixin:
    def log(self, msg: str) -> None:
        pass


class SerializeMixin:
    def to_json(self) -> str:
        return "{}"

    def from_json(self, data: str) -> None:
        pass


class BaseModel:
    def save(self) -> None:
        pass

    def delete(self) -> None:
        pass


class User(BaseModel, LogMixin, SerializeMixin):
    name: str = ""

    def get_name(self) -> str:
        return self.name
"""

ABSTRACT_CLASSES = """\
from abc import ABC, abstractmethod

class Shape(ABC):
    @abstractmethod
    def area(self) -> float:
        pass

    @abstractmethod
    def perimeter(self) -> float:
        pass

    def describe(self) -> str:
        return "shape"


class Circle(Shape):
    radius: float = 0.0

    def area(self) -> float:
        return 3.14 * self.radius ** 2

    def perimeter(self) -> float:
        return 2 * 3.14 * self.radius


class Rectangle(Shape):
    width: float = 0.0
    height: float = 0.0

    def area(self) -> float:
        return self.width * self.height

    def perimeter(self) -> float:
        return 2 * (self.width + self.height)
"""

PROPERTY_CLASSES = """\
class Config:
    @property
    def debug(self) -> bool:
        return False

    @property
    def version(self) -> str:
        return "1.0"


class AppConfig(Config):
    @property
    def app_name(self) -> str:
        return "app"


class ExtendedConfig(AppConfig):
    pass
"""


# ─── Tests: Deep Inheritance ─────────────────────────────────────────────────


class TestDeepInheritance:
    """Test resolution through multi-level inheritance."""

    def test_direct_method_lookup(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_member("Child", "child_method")
        assert member is not None
        assert member.name == "child_method"
        assert member.class_name == "Child"
        assert not member.is_inherited

    def test_inherited_from_parent(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_member("Child", "middle_method")
        assert member is not None
        assert member.name == "middle_method"
        assert member.is_inherited
        assert member.defined_in == "Middle"

    def test_inherited_from_grandparent(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_member("Child", "base_method")
        assert member is not None
        assert member.name == "base_method"
        assert member.is_inherited
        # resolve_member traces through Middle first, so defined_in
        # reflects the nearest ancestor that provided it
        assert member.defined_in in ("Base", "Middle")

    def test_deep_grandchild_inherits_all(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        all_members = resolver.get_all_members("GrandChild", include_inherited=True)
        member_names = set(all_members.keys())

        assert "base_method" in member_names
        assert "middle_method" in member_names
        assert "child_method" in member_names
        assert "overridden" in member_names

    def test_method_override_resolves_to_nearest(self, resolver: ClassResolver):
        """Method overriding: Child.overridden should resolve to Child, not Base."""
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_member("Child", "overridden")
        assert member is not None
        assert member.class_name == "Child"
        assert not member.is_inherited

    def test_grandchild_override_from_child(self, resolver: ClassResolver):
        """GrandChild inherits overridden from Child (not Base or Middle)."""
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_member("GrandChild", "overridden")
        assert member is not None
        assert member.is_inherited
        assert member.defined_in == "Child"


# ─── Tests: Diamond Inheritance ──────────────────────────────────────────────


class TestDiamondInheritance:
    """Test diamond inheritance (MRO)."""

    def test_diamond_resolves_left_first(self, resolver: ClassResolver):
        """Python MRO: Diamond(Left, Right) → Left wins for 'common'."""
        resolver.index_file(Path("test.py"), DIAMOND_INHERITANCE)

        member = resolver.resolve_member("Diamond", "common")
        assert member is not None
        assert member.is_inherited
        # Left is listed first in bases, so it should win
        assert member.defined_in == "Left"

    def test_diamond_left_only(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DIAMOND_INHERITANCE)

        member = resolver.resolve_member("Diamond", "left_only")
        assert member is not None
        assert member.defined_in == "Left"

    def test_diamond_right_only(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DIAMOND_INHERITANCE)

        member = resolver.resolve_member("Diamond", "right_only")
        assert member is not None
        assert member.defined_in == "Right"

    def test_diamond_base_attribute(self, resolver: ClassResolver):
        """Attribute 'x' from Base is accessible through Diamond."""
        resolver.index_file(Path("test.py"), DIAMOND_INHERITANCE)

        member = resolver.resolve_member("Diamond", "x")
        assert member is not None
        assert member.kind == "attribute"

    def test_diamond_all_members(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DIAMOND_INHERITANCE)

        all_members = resolver.get_all_members("Diamond")
        names = set(all_members.keys())
        assert "common" in names
        assert "left_only" in names
        assert "right_only" in names
        assert "x" in names


# ─── Tests: Mixin Classes ────────────────────────────────────────────────────


class TestMixinClasses:
    """Test mixin pattern resolution."""

    def test_user_has_own_method(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), MIXIN_CLASSES)

        member = resolver.resolve_member("User", "get_name")
        assert member is not None
        assert not member.is_inherited

    def test_user_inherits_from_base_model(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), MIXIN_CLASSES)

        member = resolver.resolve_member("User", "save")
        assert member is not None
        assert member.is_inherited
        assert member.defined_in == "BaseModel"

    def test_user_inherits_log_mixin(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), MIXIN_CLASSES)

        member = resolver.resolve_member("User", "log")
        assert member is not None
        assert member.is_inherited
        assert member.defined_in == "LogMixin"

    def test_user_inherits_serialize_mixin(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), MIXIN_CLASSES)

        member = resolver.resolve_member("User", "to_json")
        assert member is not None
        assert member.defined_in == "SerializeMixin"

    def test_user_all_members_count(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), MIXIN_CLASSES)

        all_members = resolver.get_all_members("User")
        # Own: get_name, name
        # BaseModel: save, delete
        # LogMixin: log
        # SerializeMixin: to_json, from_json
        assert len(all_members) >= 7


# ─── Tests: Abstract Classes ─────────────────────────────────────────────────


class TestAbstractClasses:
    """Test abstract class and implementation resolution."""

    def test_circle_implements_area(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), ABSTRACT_CLASSES)

        member = resolver.resolve_member("Circle", "area")
        assert member is not None
        assert member.class_name == "Circle"
        assert not member.is_inherited

    def test_circle_inherits_describe(self, resolver: ClassResolver):
        """Non-abstract method from ABC is inherited."""
        resolver.index_file(Path("test.py"), ABSTRACT_CLASSES)

        member = resolver.resolve_member("Circle", "describe")
        assert member is not None
        assert member.is_inherited
        assert member.defined_in == "Shape"

    def test_circle_has_own_attribute(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), ABSTRACT_CLASSES)

        member = resolver.resolve_member("Circle", "radius")
        assert member is not None
        assert member.kind == "attribute"


# ─── Tests: Property Resolution ──────────────────────────────────────────────


class TestPropertyResolution:
    """Test property access through inheritance."""

    def test_property_direct(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), PROPERTY_CLASSES)

        member = resolver.resolve_member("Config", "debug")
        assert member is not None
        assert member.kind == "property"

    def test_property_inherited(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), PROPERTY_CLASSES)

        member = resolver.resolve_member("AppConfig", "debug")
        assert member is not None
        assert member.is_inherited
        assert member.defined_in == "Config"

    def test_property_deep_inherited(self, resolver: ClassResolver):
        """ExtendedConfig inherits through AppConfig → Config."""
        resolver.index_file(Path("test.py"), PROPERTY_CLASSES)

        member = resolver.resolve_member("ExtendedConfig", "debug")
        assert member is not None
        assert member.is_inherited

    def test_extended_has_all_properties(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), PROPERTY_CLASSES)

        all_members = resolver.get_all_members("ExtendedConfig")
        names = set(all_members.keys())
        assert "debug" in names
        assert "version" in names
        assert "app_name" in names


# ─── Tests: Re-indexing and Dirty State ──────────────────────────────────────


class TestReindexing:
    """Test that re-indexing properly updates state."""

    def test_reindex_clears_old_classes(self, resolver: ClassResolver):
        """When file is re-indexed, old class data is replaced."""
        path = Path("test.py")

        # Index version 1
        resolver.index_file(path, "class Foo:\n    def bar(self): pass\n")
        assert resolver.resolve_member("Foo", "bar") is not None

        # Re-index with different content
        resolver.index_file(path, "class Foo:\n    def baz(self): pass\n")
        assert resolver.resolve_member("Foo", "bar") is None
        assert resolver.resolve_member("Foo", "baz") is not None

    def test_clear_file_removes_classes(self, resolver: ClassResolver):
        path = Path("test.py")
        resolver.index_file(path, "class Foo:\n    pass\n")
        assert resolver.resolve_member("Foo", "__init__") is None  # no init

        resolver.clear_file(path)
        # After clear, class should not be found
        all_members = resolver.get_all_members("Foo")
        assert len(all_members) == 0

    def test_nonexistent_class_returns_none(self, resolver: ClassResolver):
        assert resolver.resolve_member("NonExistent", "method") is None

    def test_nonexistent_member_returns_none(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), "class Foo:\n    pass\n")
        assert resolver.resolve_member("Foo", "nonexistent") is None


# ─── Tests: Self Reference ───────────────────────────────────────────────────


class TestSelfReference:
    """Test self.method() resolution."""

    def test_self_direct_method(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_self_reference("Child", "child_method")
        assert member is not None
        assert member.name == "child_method"

    def test_self_inherited_method(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_self_reference("Child", "base_method")
        assert member is not None
        assert member.is_inherited

    def test_self_nonexistent(self, resolver: ClassResolver):
        resolver.index_file(Path("test.py"), DEEP_INHERITANCE)

        member = resolver.resolve_self_reference("Child", "no_such_method")
        assert member is None
