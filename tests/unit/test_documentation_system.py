"""Tests for documentation system."""

import pytest
from src.infrastructure.docs.documentation_system import (
    DocumentationSystem,
    DocType,
    Difficulty,
    Document,
    DocMetadata,
)


class TestDocumentationSystem:
    def test_system_creation(self):
        docs = DocumentationSystem()
        assert docs is not None

    def test_register_document(self):
        docs = DocumentationSystem()
        doc = Document(
            doc_id="test_doc",
            path="test.md",
            metadata=DocMetadata(
                title="Test Document",
                doc_type=DocType.USER_GUIDE,
                difficulty=Difficulty.BEGINNER,
            ),
        )
        docs.register_document(doc)

    def test_get_document(self):
        docs = DocumentationSystem()
        doc = Document(
            doc_id="test_doc",
            path="test.md",
            metadata=DocMetadata(
                title="Test",
                doc_type=DocType.QUICKSTART,
                difficulty=Difficulty.BEGINNER,
            ),
        )
        docs.register_document(doc)
        
        retrieved = docs.get_document("test_doc")
        assert retrieved is not None
        assert retrieved.doc_id == "test_doc"

    def test_search(self):
        docs = DocumentationSystem()
        doc = Document(
            doc_id="debug_guide",
            path="debug.md",
            metadata=DocMetadata(
                title="Debug Guide",
                doc_type=DocType.USER_GUIDE,
                difficulty=Difficulty.INTERMEDIATE,
                tags=["debug", "firmware"],
            ),
            content="Learn how to debug firmware.",
        )
        docs.register_document(doc)
        
        results = docs.search("debug")
        assert len(results) >= 1

    def test_get_documents_by_type(self):
        docs = DocumentationSystem()
        doc = Document(
            doc_id="api_ref",
            path="api.md",
            metadata=DocMetadata(
                title="API Reference",
                doc_type=DocType.API_REFERENCE,
                difficulty=Difficulty.ADVANCED,
            ),
        )
        docs.register_document(doc)
        
        api_docs = docs.get_documents_by_type(DocType.API_REFERENCE)
        assert len(api_docs) >= 1

    def test_generate_table_of_contents(self):
        docs = DocumentationSystem()
        toc = docs.generate_table_of_contents()
        assert isinstance(toc, dict)
