"""Hardware-Aware Knowledge Base Chunking.

Chunks hardware documentation (datasheets, reference manuals) for RAG.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class Chunk:
    """Represents a document chunk."""
    content: str
    chunk_type: str  # register, peripheral, interrupt, example, table
    metadata: dict
    embedding: Optional[list[float]] = None


class HardwareChunker:
    """Chunks hardware documentation for knowledge retrieval."""

    def __init__(self, chunk_size: int = 500, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_document(self, content: str, doc_type: str = "generic") -> list[Chunk]:
        """Chunk a hardware document."""
        if doc_type == "svd":
            return self._chunk_svd(content)
        elif doc_type == "datasheet":
            return self._chunk_datasheet(content)
        elif doc_type == "reference_manual":
            return self._chunk_reference_manual(content)
        else:
            return self._chunk_generic(content)

    def _chunk_svd(self, content: str) -> list[Chunk]:
        """Chunk SVD file content."""
        chunks = []
        metadata = {"type": "svd"}

        # Split by peripheral
        peripheral_pattern = r'<peripheral>(.*?)</peripheral>'
        peripherals = re.findall(peripheral_pattern, content, re.DOTALL)

        for i, peripheral in enumerate(peripherals):
            # Extract peripheral name
            name_match = re.search(r'<name>(.*?)</name>', peripheral)
            name = name_match.group(1) if name_match else f"peripheral_{i}"

            # Split by register
            register_pattern = r'<register>(.*?)</register>'
            registers = re.findall(register_pattern, peripheral, re.DOTALL)

            for j, register in enumerate(registers):
                reg_name_match = re.search(r'<name>(.*?)</name>', register)
                reg_name = reg_name_match.group(1) if reg_name_match else f"register_{j}"

                # Extract key fields
                fields = []
                field_pattern = r'<field>(.*?)</field>'
                for field in re.findall(field_pattern, register, re.DOTALL):
                    field_name = re.search(r'<name>(.*?)</name>', field)
                    field_bits = re.search(r'<bitOffset>(\d+)</bitOffset>', field) or \
                                 re.search(r'<bitRange>\[(\d+):(\d+)\]</bitRange>', field)
                    field_desc = re.search(r'<description>(.*?)</description>', field)

                    fields.append({
                        "name": field_name.group(1) if field_name else "unknown",
                        "bits": field_bits.groups() if field_bits else None,
                        "description": field_desc.group(1)[:100] if field_desc else "",
                    })

                chunks.append(Chunk(
                    content=f"""Peripheral: {name}
Register: {reg_name}
Fields:
{chr(10).join(f"- {f['name']} [{f['bits']}]: {f['description']}" for f in fields if f['name'] != 'unknown')}
""",
                    chunk_type="register",
                    metadata={
                        "peripheral": name,
                        "register": reg_name,
                        "type": "svd",
                    }
                ))

        return chunks

    def _chunk_datasheet(self, content: str) -> list[Chunk]:
        """Chunk datasheet content."""
        chunks = []

        # Split by major sections
        sections = re.split(r'\n(?=\d+\.\s+\w+)', content)

        current_chunk = []
        current_size = 0

        for section in sections:
            if current_size + len(section) > self.chunk_size:
                if current_chunk:
                    chunks.append(Chunk(
                        content='\n'.join(current_chunk),
                        chunk_type="datasheet",
                        metadata={}
                    ))
                current_chunk = [section[:self.chunk_size]]
                current_size = len(current_chunk[0])
            else:
                current_chunk.append(section)
                current_size += len(section)

        if current_chunk:
            chunks.append(Chunk(
                content='\n'.join(current_chunk),
                chunk_type="datasheet",
                metadata={}
            ))

        return chunks

    def _chunk_reference_manual(self, content: str) -> list[Chunk]:
        """Chunk reference manual content."""
        chunks = []

        # Split by chapter/section
        chapters = re.split(r'\n(?=Chapter\s+\d+)', content)

        for chapter in chapters:
            if len(chapter) > self.chunk_size:
                # Split by subsections
                subsections = re.split(r'\n(?=\d+\.\d+\s+)', chapter)
                for subsection in subsections:
                    if len(subsection) > self.chunk_size:
                        # Split by paragraphs
                        chunks.extend(self._chunk_by_paragraphs(subsection))
                    else:
                        chunks.append(Chunk(
                            content=subsection,
                            chunk_type="reference_manual",
                            metadata={}
                        ))
            else:
                chunks.append(Chunk(
                    content=chapter,
                    chunk_type="reference_manual",
                    metadata={}
                ))

        return chunks

    def _chunk_by_paragraphs(self, content: str) -> list[Chunk]:
        """Split content by paragraphs."""
        chunks = []
        paragraphs = content.split('\n\n')

        current = []
        current_size = 0

        for para in paragraphs:
            if current_size + len(para) > self.chunk_size and current:
                chunks.append(Chunk(
                    content='\n\n'.join(current),
                    chunk_type="paragraph",
                    metadata={}
                ))
                current = [para]
                current_size = len(para)
            else:
                current.append(para)
                current_size += len(para)

        if current:
            chunks.append(Chunk(
                content='\n\n'.join(current),
                chunk_type="paragraph",
                metadata={}
            ))

        return chunks

    def _chunk_generic(self, content: str) -> list[Chunk]:
        """Generic chunking by size with overlap."""
        chunks = []
        start = 0

        while start < len(content):
            end = start + self.chunk_size
            chunk = content[start:end]

            chunks.append(Chunk(
                content=chunk,
                chunk_type="generic",
                metadata={"start": start, "end": end}
            ))

            start = end - self.overlap

        return chunks


class HardwareRetriever:
    """Retrieves relevant hardware knowledge."""

    def __init__(self, chunker: Optional[HardwareChunker] = None):
        self.chunker = chunker or HardwareChunker()
        self.chunks: list[Chunk] = []

    def index(self, content: str, doc_type: str = "generic", metadata: dict = None) -> int:
        """Index a document."""
        chunks = self.chunker.chunk_document(content, doc_type)
        for chunk in chunks:
            if metadata:
                chunk.metadata.update(metadata)
        self.chunks.extend(chunks)
        return len(chunks)

    def retrieve(self, query: str, top_k: int = 5) -> list[Chunk]:
        """Retrieve relevant chunks for a query."""
        # Simple keyword-based retrieval (would use embeddings in production)
        query_words = set(query.lower().split())

        scored = []
        for chunk in self.chunks:
            content_words = set(chunk.content.lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                scored.append((overlap, chunk))

        scored.sort(reverse=True)
        return [chunk for _, chunk in scored[:top_k]]

    def retrieve_by_type(self, query: str, chunk_type: str, top_k: int = 5) -> list[Chunk]:
        """Retrieve chunks of a specific type."""
        filtered = [c for c in self.chunks if c.chunk_type == chunk_type]
        retriever = HardwareRetriever(self.chunker)
        retriever.chunks = filtered
        return retriever.retrieve(query, top_k)

    def get_peripheral_info(self, peripheral_name: str) -> list[Chunk]:
        """Get all information about a peripheral."""
        return [c for c in self.chunks
                if c.metadata.get("peripheral") == peripheral_name
                or peripheral_name.lower() in c.content.lower()]

    def get_register_info(self, peripheral: str, register: str) -> Optional[Chunk]:
        """Get information about a specific register."""
        for chunk in self.chunks:
            if (chunk.metadata.get("peripheral") == peripheral and
                chunk.metadata.get("register") == register):
                return chunk
        return None
