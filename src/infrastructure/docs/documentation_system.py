"""Documentation and training materials (Phase 16.3).

Provides documentation system:
- API documentation
- User guides
- Video tutorials index
- Search functionality
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DocType(Enum):
    """Documentation types."""
    API_REFERENCE = "api_reference"
    USER_GUIDE = "user_guide"
    TUTORIAL = "tutorial"
    QUICKSTART = "quickstart"
    TROUBLESHOOTING = "troubleshooting"


class Difficulty(Enum):
    """Content difficulty."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


@dataclass
class DocMetadata:
    """Documentation metadata."""
    title: str
    doc_type: DocType
    difficulty: Difficulty
    
    # Tags
    tags: list[str] = field(default_factory=list)
    
    # Timing
    read_time_minutes: int = 5
    video_duration_minutes: int | None = None
    
    # Related
    related_docs: list[str] = field(default_factory=list)  # doc_ids
    prerequisites: list[str] = field(default_factory=list)
    
    # Version
    version_added: str = "1.0.0"
    version_updated: str = "1.0.0"


@dataclass
class Document:
    """Documentation document."""
    doc_id: str
    path: str
    
    metadata: DocMetadata
    content: str = ""
    
    # Search
    keywords: list[str] = field(default_factory=list)
    
    @property
    def url(self) -> str:
        return f"/docs/{self.path}"


@dataclass
class VideoTutorial:
    """Video tutorial."""
    video_id: str
    title: str
    description: str
    
    # URL
    video_url: str = ""
    thumbnail_url: str = ""
    
    # Content
    duration_minutes: int = 0
    difficulty: Difficulty = Difficulty.BEGINNER
    
    # Links
    related_docs: list[str] = field(default_factory=list)
    code_samples: list[str] = field(default_factory=list)


class SearchEngine:
    """Simple search for documentation."""
    
    def __init__(self) -> None:
        self._index: dict[str, Document] = {}
    
    def index(self, doc: Document) -> None:
        """Index document."""
        self._index[doc.doc_id] = doc
    
    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Search documents."""
        query_lower = query.lower()
        results = []
        
        for doc in self._index.values():
            # Check title
            if query_lower in doc.metadata.title.lower():
                results.append((doc, 2))  # Higher score
                continue
            
            # Check keywords
            for kw in doc.metadata.tags:
                if query_lower in kw.lower():
                    results.append((doc, 1))
                    break
            else:
                # Check content
                if query_lower in doc.content.lower():
                    results.append((doc, 0.5))
        
        # Sort by score
        results.sort(key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in results[:limit]]


class DocumentationSystem:
    """Documentation and training system.
    
    Phase 16.3: Documentation & training
    """
    
    def __init__(self, docs_root: Path | None = None) -> None:
        self._docs_root = docs_root or Path("docs")
        self._documents: dict[str, Document] = {}
        self._videos: dict[str, VideoTutorial] = {}
        self._search = SearchEngine()
    
    def register_document(self, doc: Document) -> None:
        """Register documentation."""
        self._documents[doc.doc_id] = doc
        self._search.index(doc)
        logger.info("Document registered", doc_id=doc.doc_id)
    
    def register_video(self, video: VideoTutorial) -> None:
        """Register video tutorial."""
        self._videos[video.video_id] = video
        logger.info("Video registered", video_id=video.video_id)
    
    def get_document(self, doc_id: str) -> Document | None:
        """Get document."""
        return self._documents.get(doc_id)
    
    def get_documents_by_type(self, doc_type: DocType) -> list[Document]:
        """Get documents by type."""
        return [
            doc for doc in self._documents.values()
            if doc.metadata.doc_type == doc_type
        ]
    
    def get_documents_by_difficulty(self, difficulty: Difficulty) -> list[Document]:
        """Get documents by difficulty."""
        return [
            doc for doc in self._documents.values()
            if doc.metadata.difficulty == difficulty
        ]
    
    def search(self, query: str, limit: int = 10) -> list[Document]:
        """Search documentation."""
        return self._search.search(query, limit)
    
    def get_quickstart_guide(self) -> Document | None:
        """Get quickstart guide."""
        quickstarts = self.get_documents_by_type(DocType.QUICKSTART)
        return quickstarts[0] if quickstarts else None
    
    def get_tutorials(self, difficulty: Difficulty | None = None) -> list[VideoTutorial]:
        """Get video tutorials."""
        videos = list(self._videos.values())
        if difficulty:
            videos = [v for v in videos if v.difficulty == difficulty]
        return videos
    
    def get_related_docs(self, doc_id: str) -> list[Document]:
        """Get related documentation."""
        doc = self._documents.get(doc_id)
        if not doc:
            return []
        
        related = []
        for related_id in doc.metadata.related_docs:
            related_doc = self._documents.get(related_id)
            if related_doc:
                related.append(related_doc)
        
        return related
    
    def generate_table_of_contents(self) -> dict[str, list[Document]]:
        """Generate table of contents."""
        toc = {}
        for doc_type in DocType:
            docs = self.get_documents_by_type(doc_type)
            if docs:
                toc[doc_type.value] = docs
        return toc
    
    def export_docs(self, output_dir: Path) -> None:
        """Export documentation to directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Export as JSON index
        import json
        
        index = {
            "documents": [
                {
                    "doc_id": doc.doc_id,
                    "title": doc.metadata.title,
                    "type": doc.metadata.doc_type.value,
                    "difficulty": doc.metadata.difficulty.value,
                    "tags": doc.metadata.tags,
                    "read_time": doc.metadata.read_time_minutes,
                    "url": doc.url,
                }
                for doc in self._documents.values()
            ],
            "videos": [
                {
                    "video_id": v.video_id,
                    "title": v.title,
                    "duration": v.duration_minutes,
                    "url": v.video_url,
                }
                for v in self._videos.values()
            ],
        }
        
        with open(output_dir / "index.json", "w") as f:
            json.dump(index, f, indent=2)
        
        logger.info("Documentation exported", count=len(self._documents))


# Global system
_docs_system: DocumentationSystem | None = None


def get_documentation_system(docs_root: Path | None = None) -> DocumentationSystem:
    """Get global documentation system."""
    global _docs_system
    if _docs_system is None:
        _docs_system = DocumentationSystem(docs_root)
    return _docs_system


if __name__ == "__main__":
    docs = get_documentation_system()
    
    # Register sample documents
    docs.register_document(Document(
        doc_id="quickstart",
        path="quickstart.md",
        metadata=DocMetadata(
            title="Quick Start Guide",
            doc_type=DocType.QUICKSTART,
            difficulty=Difficulty.BEGINNER,
            tags=["getting-started", "setup"],
            read_time_minutes=10,
        ),
        content="Get started with AI Support in 5 minutes...",
    ))
    
    docs.register_document(Document(
        doc_id="api-debug",
        path="api/debug.md",
        metadata=DocMetadata(
            title="Debug API Reference",
            doc_type=DocType.API_REFERENCE,
            difficulty=Difficulty.INTERMEDIATE,
            tags=["api", "debug", "reference"],
            read_time_minutes=15,
        ),
        content="Debug API endpoints...",
    ))
    
    print("Documentation System")
    print("=" * 40)
    
    # Search
    results = docs.search("debug")
    print(f"Search 'debug': {len(results)} results")
    for doc in results:
        print(f"  - {doc.metadata.title}")
    
    # TOC
    toc = docs.generate_table_of_contents()
    print(f"\nTable of Contents:")
    for doc_type, docs_list in toc.items():
        print(f"  {doc_type}: {len(docs_list)} docs")
