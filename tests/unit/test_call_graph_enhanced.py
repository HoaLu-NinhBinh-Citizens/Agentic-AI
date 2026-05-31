"""Tests for enhanced call graph features.

This module tests:
- ImportResolver for alias resolution
- Reverse index (_callers) in CallGraph
- Incremental indexing with modification time tracking
- Call site argument capture
"""

import os
import pytest
from pathlib import Path

from src.core.cognition.call_graph import CallGraph, CallSite
from src.core.cognition.import_resolver import ImportResolver, ResolvedImport


class TestImportResolver:
    """Tests for ImportResolver class."""

    def test_add_import_simple(self):
        """Should add simple import entry."""
        resolver = ImportResolver()
        resolver.add_import('os', 'path')
        
        assert resolver.resolve('path') == 'os.path'
        assert resolver.resolve('os.path') == 'os.path'

    def test_resolve_alias(self):
        """Should resolve alias to original name."""
        resolver = ImportResolver()
        resolver.add_import('os', 'path', 'osp')
        
        assert resolver.resolve('osp') == 'os.path'
        assert resolver.resolve('os.path') == 'os.path'

    def test_add_import_from(self):
        """Should handle 'from X import Y' statements."""
        resolver = ImportResolver()
        resolver.add_import('collections', 'defaultdict', 'dd')
        
        assert resolver.resolve('dd') == 'collections.defaultdict'
        assert resolver.resolve('defaultdict') == 'collections.defaultdict'

    def test_parse_file_simple_imports(self):
        """Should parse simple imports from file."""
        code = '''
import os
import sys
'''
        resolver = ImportResolver().parse_file(code)
        
        assert resolver.resolve('os') == 'os'
        assert resolver.resolve('sys') == 'sys'

    def test_parse_file_import_with_alias(self):
        """Should parse imports with aliases."""
        code = '''
import os.path as osp
import sys as system
'''
        resolver = ImportResolver().parse_file(code)
        
        assert resolver.resolve('osp') == 'os.path'
        assert resolver.resolve('system') == 'sys'

    def test_parse_file_from_import(self):
        """Should parse 'from X import Y' statements."""
        code = '''
from collections import defaultdict
from typing import Optional as Opt
'''
        resolver = ImportResolver().parse_file(code)
        
        assert resolver.resolve('defaultdict') == 'collections.defaultdict'
        assert resolver.resolve('Opt') == 'typing.Optional'

    def test_get_import(self):
        """Should get import entry by name."""
        resolver = ImportResolver()
        resolver.add_import('os', 'path', 'osp')
        
        entry = resolver.get_import('osp')
        assert entry is not None
        assert entry.module == 'os'
        assert entry.name == 'path'
        assert entry.alias == 'osp'

    def test_get_import_not_found(self):
        """Should return None for unknown import."""
        resolver = ImportResolver()
        resolver.add_import('os', 'path')
        
        assert resolver.get_import('unknown') is None

    def test_clear(self):
        """Should clear all imports."""
        resolver = ImportResolver()
        resolver.add_import('os', 'path')
        
        resolver.clear()
        
        assert resolver.resolve('path') is None
        assert len(resolver._aliases) == 0

    def test_copy(self):
        """Should create a copy of the resolver."""
        resolver = ImportResolver()
        resolver.add_import('os', 'path', 'osp')
        
        resolver_copy = resolver.copy()
        
        assert resolver_copy.resolve('osp') == 'os.path'
        assert resolver_copy.resolve('path') == 'os.path'


class TestCallSiteCreate:
    """Tests for CallSite.create factory method."""

    def test_create_basic(self):
        """Should create CallSite with basic fields."""
        site = CallSite.create(
            caller='foo',
            callee='bar',
            file='test.py',
            line=10,
        )
        
        assert site.caller == 'foo'
        assert site.callee == 'bar'
        assert site.file == 'test.py'
        assert site.line == 10
        assert site.arguments == []

    def test_create_with_arguments(self):
        """Should create CallSite with arguments."""
        site = CallSite.create(
            caller='foo',
            callee='bar',
            file='test.py',
            line=10,
            arguments=['x', 'y', 'z'],
        )
        
        assert site.arguments == ['x', 'y', 'z']

    def test_create_with_method_flag(self):
        """Should create method call site."""
        site = CallSite.create(
            caller='MyClass.method',
            callee='helper',
            file='test.py',
            line=10,
            is_method=True,
        )
        
        assert site.is_method is True

    def test_default_values(self):
        """Should have correct default values."""
        site = CallSite.create(
            caller='foo',
            callee='bar',
            file='test.py',
            line=10,
        )
        
        assert site.col == 0
        assert site.is_method is False
        assert site.arguments == []


class TestCallGraphReverseIndex:
    """Tests for reverse index (_callers) in CallGraph."""

    def test_add_call_builds_reverse_index(self):
        """Should build reverse index when adding calls."""
        graph = CallGraph()
        graph.add_call('foo', 'bar', 'test.py', 10)
        graph.add_call('baz', 'bar', 'test.py', 20)
        
        callers = graph.get_callers('bar')
        assert len(callers) == 2
        
        caller_names = {c.caller for c in callers}
        assert 'foo' in caller_names
        assert 'baz' in caller_names

    def test_get_callers_with_file_filter(self):
        """Should filter callers by file."""
        graph = CallGraph()
        graph.add_call('foo', 'bar', 'file1.py', 10)
        graph.add_call('baz', 'bar', 'file2.py', 20)
        
        callers = graph.get_callers('bar', 'file1.py')
        assert len(callers) == 1
        assert callers[0].caller == 'foo'

    def test_get_callers_empty(self):
        """Should return empty list for unknown function."""
        graph = CallGraph()
        
        callers = graph.get_callers('unknown')
        assert callers == []

    def test_reverse_index_after_build(self):
        """Should build reverse index during build()."""
        graph = CallGraph()
        
        # Manually add call sites
        graph._call_sites.append(CallSite.create(
            caller='caller1',
            callee='callee1',
            file='test.py',
            line=1,
        ))
        graph._call_sites.append(CallSite.create(
            caller='caller2',
            callee='callee1',
            file='test.py',
            line=2,
        ))
        
        # Build the index
        graph._build_name_index()
        
        callers = graph.get_callers('callee1')
        assert len(callers) == 2


class TestCallGraphIncremental:
    """Tests for incremental indexing."""

    def test_skip_unchanged_file(self, tmp_path):
        """Should skip unchanged files."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")
        
        graph = CallGraph()
        
        # First call - file doesn't exist in mtimes yet
        result1 = graph.build_incremental(test_file, test_file.read_text())
        assert result1 is True  # Should index
        
        # Second call with same content
        result2 = graph.build_incremental(test_file, test_file.read_text())
        assert result2 is False  # Should skip

    def test_reindex_modified_file(self, tmp_path):
        """Should reindex modified files."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")
        
        graph = CallGraph()
        
        # First build
        graph.build_incremental(test_file, test_file.read_text())
        
        # Modify file and force filesystem sync
        test_file.write_text("def foo(): bar()")
        import time
        time.sleep(0.1)  # Ensure mtime changes
        
        # Second build - should reindex
        result = graph.build_incremental(test_file, test_file.read_text())
        assert result is True

    def test_file_mtime_tracking(self, tmp_path):
        """Should track file modification times."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): pass")
        
        graph = CallGraph()
        graph.build_incremental(test_file, test_file.read_text())
        
        # Should have tracked the mtime
        assert graph.get_file_mtime(test_file) > 0

    def test_clear_file(self, tmp_path):
        """Should clear data for a specific file."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo(): bar()")
        
        graph = CallGraph()
        graph.build_incremental(test_file, test_file.read_text())
        
        assert graph.stats['functions'] >= 1
        
        # Clear the file
        graph.clear_file(test_file)
        
        # Should have cleared the function
        assert graph.get_function('foo') is None or len(graph.get_function('foo')) == 0


class TestCallSiteArguments:
    """Tests for call site argument capture."""

    def test_capture_simple_arguments(self):
        """Should capture simple function arguments."""
        code = '''
def caller():
    foo(x, y, z=1)
'''
        graph = CallGraph()
        graph.build_content(code, 'test.py')
        
        # Find the foo call
        foo_calls = [c for c in graph.get_callees('caller') if c.callee == 'foo']
        assert len(foo_calls) >= 1
        
        call = foo_calls[0]
        assert 'x' in call.arguments
        assert 'y' in call.arguments

    def test_capture_no_arguments(self):
        """Should handle calls with no arguments."""
        code = '''
def caller():
    foo()
'''
        graph = CallGraph()
        graph.build_content(code, 'test.py')
        
        foo_calls = [c for c in graph.get_callees('caller') if c.callee == 'foo']
        assert len(foo_calls) >= 1
        assert foo_calls[0].arguments == []

    def test_arguments_in_serialization(self):
        """Should include arguments in to_dict output."""
        graph = CallGraph()
        graph.add_call('foo', 'bar', 'test.py', 10, arguments=['a', 'b'])
        
        result = graph.to_dict()
        
        assert len(result['call_sites']) >= 1
        call_site = result['call_sites'][0]
        assert call_site['arguments'] == ['a', 'b']

    def test_extract_multiple_calls(self):
        """Should extract arguments from multiple calls."""
        code = '''
def main():
    foo(a, b)
    bar(c, d, e)
    foo(x)
'''
        graph = CallGraph()
        graph.build_content(code, 'test.py')
        
        foo_calls = [c for c in graph.get_callees('main') if c.callee == 'foo']
        assert len(foo_calls) == 2
        
        # First foo call
        assert 'a' in foo_calls[0].arguments
        assert 'b' in foo_calls[0].arguments
        
        # Second foo call
        assert 'x' in foo_calls[1].arguments


class TestCallGraphIntegration:
    """Integration tests for enhanced call graph features."""

    def test_full_workflow(self):
        """Test complete workflow with all features."""
        code = '''
from collections import defaultdict as dd

def helper(a, b):
    return a + b

def main():
    data = dd(int)
    x = 1
    y = 2
    result = helper(x, y)
    return result
'''
        graph = CallGraph()
        graph.build_content(code, 'test.py')
        
        # Check function definitions
        assert graph.get_function('helper') is not None
        assert graph.get_function('main') is not None
        
        # Check callers
        main_calls = graph.get_callees('main')
        assert len(main_calls) >= 1
        
        # Check reverse index
        helper_callers = graph.get_callers('helper')
        assert len(helper_callers) >= 1
        
        # Check that we can find the helper call with variable arguments
        for caller in helper_callers:
            if caller.caller == 'main':
                assert 'x' in caller.arguments
                assert 'y' in caller.arguments

    def test_add_call_method(self):
        """Test the add_call helper method."""
        graph = CallGraph()
        
        site = graph.add_call(
            caller='my_func',
            callee='other_func',
            file='test.py',
            line=42,
            arguments=['arg1', 'arg2']
        )
        
        assert site.caller == 'my_func'
        assert site.callee == 'other_func'
        assert site.line == 42
        assert site.arguments == ['arg1', 'arg2']
        
        # Should be in callers index
        callers = graph.get_callers('other_func')
        assert len(callers) == 1
        assert callers[0] == site

    def test_find_references(self):
        """Test find_references still works with new structure."""
        graph = CallGraph()
        graph.add_call('foo', 'bar', 'test.py', 10)
        graph.add_call('baz', 'bar', 'test.py', 20)
        
        # find_references should find all references to 'bar'
        refs = graph.find_references('bar')
        assert len(refs) == 2
        
        # find_references should also find the callers
        refs = graph.find_references('foo')
        assert len(refs) == 1
