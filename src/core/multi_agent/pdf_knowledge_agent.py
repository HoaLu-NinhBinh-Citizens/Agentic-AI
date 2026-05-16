"""
PDF Knowledge Agent

Stub module for PDF knowledge extraction.
"""

from dataclasses import dataclass
from typing import List, Optional, Dict, Any


@dataclass
class KnowledgeChunk:
    """Knowledge chunk from PDF."""
    id: str
    content: str
    page: int
    metadata: Dict[str, Any]


@dataclass
class KnowledgeTable:
    """Extracted table from PDF."""
    headers: List[str]
    rows: List[List[str]]
    page: int


@dataclass
class KnowledgeImage:
    """Extracted image from PDF."""
    id: str
    path: str
    page: int
    caption: Optional[str]


class PDFKnowledgeAgent:
    """Agent for extracting knowledge from PDFs."""
    
    def extract(self, pdf_path: str) -> dict:
        return {
            "chunks": [],
            "tables": [],
            "images": [],
        }
    
    def query(self, question: str) -> str:
        return ""


__all__ = [
    "PDFKnowledgeAgent",
    "KnowledgeChunk",
    "KnowledgeTable",
    "KnowledgeImage",
]
