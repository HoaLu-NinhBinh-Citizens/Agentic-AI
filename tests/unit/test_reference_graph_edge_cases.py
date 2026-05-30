"""Edge case tests for ReferenceGraph."""

import pytest
from pathlib import Path
from src.infrastructure.indexing.reference_graph import ReferenceGraph, DefLocation, RefLocation


class TestReferenceGraphEdgeCases:
    """Test edge cases in ReferenceGraph."""

    def test_self_reference(self):
        """Function calling itself."""
        graph = ReferenceGraph()

        # Add definition manually
        def_loc = DefLocation(
            file_path="recursive.py",
            line=10,
            column=0,
            end_line=10,
            symbol_type="function",
            node_type="function_definition",
        )
        graph._defs["recursive"] = def_loc
        graph._file_symbols.setdefault("recursive.py", set()).add("recursive")

        # Add reference manually
        ref = RefLocation(
            file_path="recursive.py",
            line=20,
            column=0,
            context="recursive()",
            node_type="identifier",
            is_call=True,
        )
        graph._refs.setdefault("recursive", []).append(ref)

        # find_references takes symbol_name first, then optional file_filter
        refs = graph.find_references("recursive")
        assert len(refs) >= 1  # At least the reference we added

    def test_cross_file_import_alias(self):
        """Import alias across files."""
        graph = ReferenceGraph()

        # File A defines normalize
        def_loc = DefLocation(
            file_path="file_a.py",
            line=10,
            column=0,
            end_line=10,
            symbol_type="function",
            node_type="function_definition",
        )
        graph._defs["normalize"] = def_loc

        # File B imports as norm - add alias tracking
        graph.add_import_alias("file_b.py", "norm", "normalize", "file_a")

        # Should resolve
        resolved = graph.resolve_reference("file_b.py", "norm")
        assert resolved is not None

    def test_cyclic_imports(self):
        """Circular imports between files."""
        graph = ReferenceGraph()

        def_loc_a = DefLocation(
            file_path="a.py",
            line=1,
            column=0,
            end_line=1,
            symbol_type="class",
            node_type="class_definition",
        )
        graph._defs["A"] = def_loc_a
        graph._file_symbols.setdefault("a.py", set()).add("A")

        def_loc_b = DefLocation(
            file_path="b.py",
            line=1,
            column=0,
            end_line=1,
            symbol_type="class",
            node_type="class_definition",
        )
        graph._defs["B"] = def_loc_b
        graph._file_symbols.setdefault("b.py", set()).add("B")

        # Add cross-references
        ref_b = RefLocation(
            file_path="a.py",
            line=5,
            column=0,
            context="from b import B",
            node_type="identifier",
            is_call=False,
        )
        graph._refs.setdefault("B", []).append(ref_b)

        ref_a = RefLocation(
            file_path="b.py",
            line=5,
            column=0,
            context="from a import A",
            node_type="identifier",
            is_call=False,
        )
        graph._refs.setdefault("A", []).append(ref_a)

        # find_callers takes only function_name (no file_filter)
        callers_a = graph.find_callers("A")
        callers_b = graph.find_callers("B")
        # Should not crash and return results
        assert isinstance(callers_a, list)
        assert isinstance(callers_b, list)

    def test_method_resolution(self):
        """Class method vs instance method."""
        graph = ReferenceGraph()

        def_loc = DefLocation(
            file_path="model.py",
            line=10,
            column=0,
            end_line=10,
            symbol_type="method",
            node_type="function_definition",
        )
        graph._defs["Model.forward"] = def_loc
        graph._file_symbols.setdefault("model.py", set()).add("Model.forward")

        resolved = graph.resolve_reference("main.py", "Model.forward")
        assert resolved is not None

    def test_namespace_collision(self):
        """Same name in different modules."""
        graph = ReferenceGraph()

        def_loc_a = DefLocation(
            file_path="module_a.py",
            line=5,
            column=0,
            end_line=5,
            symbol_type="class",
            node_type="class_definition",
        )
        graph._defs["Config"] = def_loc_a
        graph._file_symbols.setdefault("module_a.py", set()).add("Config")

        # Different file same name - different definition
        graph._defs["module_b.Config"] = DefLocation(
            file_path="module_b.py",
            line=10,
            column=0,
            end_line=10,
            symbol_type="class",
            node_type="class_definition",
        )
        graph._file_symbols.setdefault("module_b.py", set()).add("module_b.Config")

        # Add refs
        ref_a = RefLocation(
            file_path="module_a.py",
            line=1,
            column=0,
            context="Config()",
            node_type="identifier",
            is_call=True,
        )
        graph._refs.setdefault("Config", []).append(ref_a)

        refs_a = graph.find_references("Config")
        assert len(refs_a) >= 1

    def test_very_long_symbol_name(self):
        """Extremely long function name."""
        graph = ReferenceGraph()
        long_name = "a" * 1000

        def_loc = DefLocation(
            file_path="file.py",
            line=1,
            column=0,
            end_line=1,
            symbol_type="function",
            node_type="function_definition",
        )
        graph._defs[long_name] = def_loc
        graph._file_symbols.setdefault("file.py", set()).add(long_name)

        refs = graph.find_references(long_name)
        assert len(refs) == 0  # No refs added

    def test_unicode_in_symbol_names(self):
        """Unicode characters in code."""
        graph = ReferenceGraph()

        def_loc = DefLocation(
            file_path="file.py",
            line=1,
            column=0,
            end_line=1,
            symbol_type="function",
            node_type="function_definition",
        )
        graph._defs["hàm"] = def_loc
        graph._file_symbols.setdefault("file.py", set()).add("hàm")

        refs = graph.find_references("hàm")
        assert len(refs) == 0  # No refs added

    def test_empty_file(self):
        """Empty file with no symbols."""
        graph = ReferenceGraph()
        refs = graph.find_references("anything")
        assert refs == []

    def test_clear_and_rebuild(self):
        """Test that clear() allows rebuilding the graph."""
        graph = ReferenceGraph()

        def_loc = DefLocation(
            file_path="test.py",
            line=1,
            column=0,
            end_line=1,
            symbol_type="function",
            node_type="function_definition",
        )
        graph._defs["test_func"] = def_loc
        graph._stats.files_indexed = 1

        # Clear should reset state
        graph.clear()

        assert len(graph._defs) == 0
        assert len(graph._refs) == 0
        assert graph._stats.files_indexed == 0

    def test_get_stats(self):
        """Test getting reference graph statistics."""
        graph = ReferenceGraph()

        def_loc = DefLocation(
            file_path="test.py",
            line=1,
            column=0,
            end_line=1,
            symbol_type="function",
            node_type="function_definition",
        )
        graph._defs["test_func"] = def_loc
        graph._file_symbols["test.py"] = {"test_func"}

        stats = graph.get_stats()
        assert "files_indexed" in stats
        assert "symbols_indexed" in stats
        assert "total_definitions" in stats
        assert stats["total_definitions"] == 1
