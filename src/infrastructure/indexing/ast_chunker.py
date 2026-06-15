"""AST-aware chunking using tree-sitter for semantic code splitting.

Fixes: Text-based chunking that breaks symbol boundaries.
Provides: Symbol-aware chunks preserving function/class context.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """A semantically coherent code chunk."""
    content: str
    file_path: str
    symbol_name: Optional[str]
    symbol_kind: Optional[str]
    start_line: int
    end_line: int
    chunk_type: str  # "symbol", "section", "block"


class ASTCodeChunker:
    """Chunk code using tree-sitter AST for semantic boundaries.
    
    Splits at:
    - Function/class definitions
    - Import blocks
    - Comment sections
    - Logical code blocks based on indentation
    
    Usage:
        chunker = ASTCodeChunker()
        chunks = await chunker.chunk_file("src/main.py", content)
    """
    
    def __init__(self, max_chunk_size: int = 2000):
        self.max_chunk_size = max_chunk_size
        self._parsers_cache: dict[str, Any] = {}
    
    def _get_parser(self, language: str) -> Any:
        """Get tree-sitter parser for language."""
        if language in self._parsers_cache:
            return self._parsers_cache[language]
        
        try:
            import tree_sitter_languages
            parser = tree_sitter_languages.get_parser(language)
            self._parsers_cache[language] = parser
            return parser
        except Exception as e:
            logger.debug("No tree-sitter parser for %s: %s", language, e)
            return None
    
    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".c": "c", ".h": "c",
            ".cpp": "cpp", ".hpp": "cpp",
            ".js": "javascript", ".ts": "typescript",
            ".rs": "rust", ".go": "go",
        }
        return ext_map.get(Path(file_path).suffix.lower(), "python")
    
    async def chunk_file(
        self,
        file_path: str,
        content: Optional[str] = None,
    ) -> list[CodeChunk]:
        """Chunk file using AST boundaries."""
        if content is None:
            try:
                content = Path(file_path).read_text(encoding='utf-8')
            except Exception as e:
                logger.error("Failed to read file: %s", e)
                return []
        
        language = self._detect_language(file_path)
        parser = self._get_parser(language)
        
        if parser:
            return self._chunk_with_parser(file_path, content, language, parser)
        
        return self._chunk_fallback(file_path, content)
    
    def _chunk_with_parser(
        self,
        file_path: str,
        content: str,
        language: str,
        parser: Any,
    ) -> list[CodeChunk]:
        """Chunk using tree-sitter AST."""
        import tree_sitter
        
        source_bytes = content.encode('utf-8')
        tree = parser.parse(source_bytes)
        
        chunks: list[CodeChunk] = []
        lines = content.split('\n')
        
        # Extract top-level symbols
        symbol_nodes = []
        self._walk_for_symbols(tree.root_node, language, symbol_nodes)
        
        for node in symbol_nodes:
            start_line = node.start_point[0] + 1
            end_line = node.end_point[0] + 1
            node_content = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
            symbol_name = self._get_node_name(node, source_bytes)
            symbol_kind = node.type
            
            if len(node_content) <= self.max_chunk_size:
                chunks.append(CodeChunk(
                    content=node_content,
                    file_path=file_path,
                    symbol_name=symbol_name,
                    symbol_kind=symbol_kind,
                    start_line=start_line,
                    end_line=end_line,
                    chunk_type="symbol",
                ))
        
        # Fallback for large files: chunk by lines
        if not chunks:
            chunks = self._chunk_by_lines(file_path, lines, content)
        
        return chunks
    
    def _walk_for_symbols(self, node: Any, language: str, symbols: list) -> None:
        """Walk AST for symbol-defining nodes."""
        symbol_types = {
            "python": ["function_definition", "class_definition", "async_function_definition"],
            "c": ["function_definition", "preproc_include"],
            "cpp": ["function_definition", "class_definition", "preproc_include"],
            "javascript": ["function_declaration", "class_declaration"],
            "typescript": ["function_declaration", "class_declaration"],
            "rust": ["function_item", "struct_item"],
            "go": ["function_declaration"],
        }
        
        allowed = set(symbol_types.get(language, []))
        if node.type in allowed:
            symbols.append(node)
        else:
            for child in node.children:
                self._walk_for_symbols(child, language, symbols)
    
    def _get_node_name(self, node: Any, source_bytes: bytes) -> Optional[str]:
        """Extract name from AST node."""
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return child.text.decode('utf-8')
        return None
    
    def _chunk_fallback(self, file_path: str, content: str) -> list[CodeChunk]:
        """Regex-based fallback chunking."""
        lines = content.split('\n')
        chunks: list[CodeChunk] = []
        
        # Group import statements
        import_lines = []
        non_import_lines = []
        
        for i, line in enumerate(lines):
            if line.strip().startswith(("import ", "from ")) or line.strip().startswith("#include"):
                import_lines.append((i, line))
            else:
                non_import_lines.append((i, line))
        
        if import_lines:
            chunks.append(CodeChunk(
                content='\n'.join(l for _, l in import_lines),
                file_path=file_path,
                symbol_name=None,
                symbol_kind="imports",
                start_line=import_lines[0][0] + 1,
                end_line=import_lines[-1][0] + 1,
                chunk_type="section",
            ))
        
        # Chunk by symbol-like patterns
        current_chunk: list[str] = []
        chunk_start = 0
        size = 0
        
        for i, (line_no, line) in enumerate(non_import_lines):
            if self._is_symbol_boundary(line):
                if current_chunk and size > 0:
                    chunks.append(CodeChunk(
                        content='\n'.join(current_chunk),
                        file_path=file_path,
                        symbol_name=self._extract_symbol_from_line(current_chunk[0]) if current_chunk else None,
                        symbol_kind=self._detect_kind(current_chunk[0]) if current_chunk else None,
                        start_line=chunk_start,
                        end_line=line_no,
                        chunk_type="block",
                    ))
                current_chunk = [line]
                chunk_start = line_no + 1
                size = len(line)
            else:
                current_chunk.append(line)
                size += len(line)
                
                if size > self.max_chunk_size and len(current_chunk) > 1:
                    chunks.append(CodeChunk(
                        content='\n'.join(current_chunk[:-1]),
                        file_path=file_path,
                        symbol_name=None,
                        symbol_kind=None,
                        start_line=chunk_start,
                        end_line=chunk_start + len(current_chunk) - 2,
                        chunk_type="block",
                    ))
                    current_chunk = [current_chunk[-1]]
                    chunk_start = chunk_start + len(current_chunk) - 1
                    size = len(current_chunk[0])
        
        if current_chunk:
            chunks.append(CodeChunk(
                content='\n'.join(current_chunk),
                file_path=file_path,
                symbol_name=None,
                symbol_kind=None,
                start_line=chunk_start,
                end_line=chunk_start + len(current_chunk) - 1,
                chunk_type="block",
            ))
        
        return chunks
    
    def _is_symbol_boundary(self, line: str) -> bool:
        """Check if line marks a symbol boundary."""
        stripped = line.strip()
        return bool(
            stripped and not stripped.startswith('#')
            and stripped.startswith(('def ', 'class ', 'async def ', 'fn ', 'func ', 'function '))
        )
    
    def _extract_symbol_from_line(self, line: str) -> Optional[str]:
        """Extract symbol name from definition line."""
        import re
        match = re.search(r'(?:def |class |fn |func |function )\s+([a-zA-Z_]\w*)', line)
        return match.group(1) if match else None
    
    def _detect_kind(self, line: str) -> str:
        """Detect symbol kind from line."""
        stripped = line.strip()
        if stripped.startswith('def '):
            return "function"
        if stripped.startswith('class '):
            return "class"
        return "unknown"