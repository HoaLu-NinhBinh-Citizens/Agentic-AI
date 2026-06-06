"""Tests for ClassResolver — inheritance, MRO, properties, attributes."""
import pytest
from pathlib import Path
from src.infrastructure.analysis.class_resolver import ClassResolver, ClassMember


@pytest.fixture
def resolver():
    return ClassResolver()


class TestBasicResolution:
    """Test basic class member resolution."""

    def test_resolve_direct_method(self, resolver):
        code = "class Foo:\n    def bar(self) -> int:\n        return 1\n"
        resolver.index_file(Path("foo.py"), code)
        member = resolver.resolve_member("Foo", "bar")
        assert member is not None
        assert member.kind == "method"
        assert member.name == "bar"

    def test_resolve_class_attribute(self, resolver):
        code = "class Config:\n    debug = True\n    port = 8080\n"
        resolver.index_file(Path("config.py"), code)
        member = resolver.resolve_member("Config", "debug")
        assert member is not None
        assert member.kind == "attribute"

    def test_resolve_property(self, resolver):
        code = "class User:\n    @property\n    def name(self) -> str:\n        return self._name\n"
        resolver.index_file(Path("user.py"), code)
        member = resolver.resolve_member("User", "name")
        assert member is not None
        assert member.kind == "property"

    def test_resolve_staticmethod(self, resolver):
        code = "class Utils:\n    @staticmethod\n    def helper() -> None:\n        pass\n"
        resolver.index_file(Path("utils.py"), code)
        member = resolver.resolve_member("Utils", "helper")
        assert member is not None
        assert member.kind == "staticmethod"

    def test_resolve_classmethod(self, resolver):
        code = "class Factory:\n    @classmethod\n    def create(cls) -> 'Factory':\n        return cls()\n"
        resolver.index_file(Path("factory.py"), code)
        member = resolver.resolve_member("Factory", "create")
        assert member is not None
        assert member.kind == "classmethod"

    def test_nonexistent_member(self, resolver):
        code = "class Empty:\n    pass\n"
        resolver.index_file(Path("empty.py"), code)
        member = resolver.resolve_member("Empty", "missing")
        assert member is None


class TestInheritance:
    """Test inheritance-based resolution (MRO traversal)."""

    def test_single_inheritance(self, resolver):
        code = """
class Animal:
    def speak(self) -> str:
        return "..."

class Dog(Animal):
    def fetch(self):
        return "ball"
"""
        resolver.index_file(Path("animals.py"), code)
        member = resolver.resolve_member("Dog", "speak")
        assert member is not None
        assert member.is_inherited
        assert member.defined_in == "Animal"

    def test_multiple_inheritance(self, resolver):
        code = """
class Flyable:
    def fly(self):
        pass

class Swimmable:
    def swim(self):
        pass

class Duck(Flyable, Swimmable):
    def quack(self):
        pass
"""
        resolver.index_file(Path("birds.py"), code)
        assert resolver.resolve_member("Duck", "fly") is not None
        assert resolver.resolve_member("Duck", "swim") is not None
        assert resolver.resolve_member("Duck", "quack") is not None

    def test_deep_inheritance(self, resolver):
        code = """
class A:
    def method_a(self):
        pass

class B(A):
    def method_b(self):
        pass

class C(B):
    def method_c(self):
        pass
"""
        resolver.index_file(Path("chain.py"), code)
        member = resolver.resolve_member("C", "method_a")
        assert member is not None
        assert member.is_inherited

    def test_method_override(self, resolver):
        code = """
class Base:
    def process(self) -> str:
        return "base"

class Derived(Base):
    def process(self) -> str:
        return "derived"
"""
        resolver.index_file(Path("override.py"), code)
        member = resolver.resolve_member("Derived", "process")
        assert member is not None
        assert not member.is_inherited  # Overridden, not inherited
        assert member.class_name == "Derived"


class TestGetAllMembers:
    """Test getting all members including inherited."""

    def test_all_members_with_inheritance(self, resolver):
        code = """
class Parent:
    name = "parent"
    def greet(self):
        pass

class Child(Parent):
    age = 10
    def play(self):
        pass
"""
        resolver.index_file(Path("family.py"), code)
        members = resolver.get_all_members("Child", include_inherited=True)
        assert "play" in members
        assert "age" in members
        assert "greet" in members
        assert "name" in members

    def test_all_members_without_inheritance(self, resolver):
        code = """
class Parent:
    def greet(self):
        pass

class Child(Parent):
    def play(self):
        pass
"""
        resolver.index_file(Path("family.py"), code)
        members = resolver.get_all_members("Child", include_inherited=False)
        assert "play" in members
        assert "greet" not in members


class TestReindexing:
    """Test that re-indexing clears stale data."""

    def test_clear_file_removes_classes(self, resolver):
        code = "class Old:\n    def method(self):\n        pass\n"
        resolver.index_file(Path("old.py"), code)
        assert resolver.resolve_member("Old", "method") is not None

        resolver.clear_file(Path("old.py"))
        assert resolver.resolve_member("Old", "method") is None

    def test_reindex_updates_members(self, resolver):
        code_v1 = "class MyClass:\n    def old_method(self):\n        pass\n"
        code_v2 = "class MyClass:\n    def new_method(self):\n        pass\n"

        resolver.index_file(Path("my.py"), code_v1)
        assert resolver.resolve_member("MyClass", "old_method") is not None

        resolver.index_file(Path("my.py"), code_v2)
        assert resolver.resolve_member("MyClass", "old_method") is None
        assert resolver.resolve_member("MyClass", "new_method") is not None
