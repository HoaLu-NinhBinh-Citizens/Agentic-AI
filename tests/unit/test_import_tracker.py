import pytest
import tempfile
from pathlib import Path
from src.infrastructure.analysis.import_tracker import ImportTracker, SymbolExport


class TestImportTracker:
    """Tests for ImportTracker."""

    def test_module_name_from_path(self):
        """Test converting file path to module name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            # Create src/package/module.py structure
            src_dir = project_root / "src"
            src_dir.mkdir()
            module_file = src_dir / "package" / "module.py"
            module_file.parent.mkdir()
            module_file.touch()
            
            module_name = tracker._get_module_name(module_file)
            assert module_name == "src.package.module"

    def test_index_python_file(self):
        """Test indexing a Python file for exports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            # Create test file
            test_file = project_root / "test_module.py"
            test_file.write_text("""
class MyClass:
    pass

def my_function():
    pass

async def async_func():
    pass

__all__ = ["MyClass", "my_function"]
""")
            
            tracker._index_file(test_file)
            
            exports = tracker.get_module_exports("test_module")
            export_names = {e.name for e in exports}
            
            assert "MyClass" in export_names
            assert "my_function" in export_names
            assert "async_func" in export_names

    def test_index_typescript_file(self):
        """Test indexing a TypeScript file for exports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            # Create test file
            test_file = project_root / "test_module.ts"
            test_file.write_text("""
export class MyClass {
    name: string;
}

export function myFunction(): void {
    return;
}

export const CONSTANT = 42;
""")
            
            tracker._index_file(test_file)
            
            exports = tracker.get_module_exports("test_module")
            export_names = {e.name for e in exports}
            
            assert "MyClass" in export_names
            assert "myFunction" in export_names
            assert "CONSTANT" in export_names

    def test_resolve_import_from_module(self):
        """Test resolving an import from a specific module."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            # Create test file
            test_file = project_root / "test_module.py"
            test_file.write_text("""
class MyClass:
    pass
""")
            
            tracker._index_file(test_file)
            
            result = tracker.resolve_import(
                project_root / "other_file.py",
                "MyClass",
                from_module="test_module"
            )
            
            assert result is not None
            assert result.name == "MyClass"
            assert result.kind == "class"

    def test_resolve_module_import(self):
        """Test resolving 'import module' style imports."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            # Create test file
            test_file = project_root / "test_module.py"
            test_file.touch()
            
            tracker._index_file(test_file)
            
            result = tracker.resolve_import(
                project_root / "other_file.py",
                "test_module",
                from_module=None
            )
            
            assert result is not None
            assert result.name == "test_module"
            assert result.kind == "module"

    def test_get_all_modules(self):
        """Test getting all indexed module names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            # Create multiple test files
            for name in ["module_a.py", "module_b.py"]:
                (project_root / name).touch()
                tracker._index_file(project_root / name)
            
            modules = tracker.get_all_modules()
            assert "module_a" in modules
            assert "module_b" in modules

    def test_index_project(self):
        """Test indexing an entire project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            
            # Create project structure
            src_dir = project_root / "src"
            src_dir.mkdir()
            (src_dir / "module1.py").write_text("class Class1: pass")
            (src_dir / "module2.py").write_text("def func1(): pass")
            (src_dir / "module3.ts").write_text("export class TSClass: pass")
            
            tracker = ImportTracker(project_root)
            files = list(project_root.rglob("*.py")) + list(project_root.rglob("*.ts"))
            tracker.index_project(files)
            
            modules = tracker.get_all_modules()
            assert "src.module1" in modules
            assert "src.module2" in modules
            assert "src.module3" in modules

    def test_symbol_export_dataclass(self):
        """Test SymbolExport dataclass structure."""
        file_path = Path("/path/to/file.py")
        export = SymbolExport(
            name="MyClass",
            file_path=file_path,
            line=10,
            kind="class"
        )
        assert export.name == "MyClass"
        assert export.file_path == file_path
        assert export.line == 10
        assert export.kind == "class"

    def test_export_kind_detection(self):
        """Test that exports are correctly categorized by kind."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            tracker = ImportTracker(project_root)
            
            test_file = project_root / "kinds.py"
            test_file.write_text("""
class MyClass:
    pass

def my_func():
    pass

MY_CONST = 42
""")
            
            tracker._index_file(test_file)
            exports = tracker.get_module_exports("kinds")
            
            for exp in exports:
                if exp.name == "MyClass":
                    assert exp.kind == "class"
                elif exp.name == "my_func":
                    assert exp.kind == "function"
