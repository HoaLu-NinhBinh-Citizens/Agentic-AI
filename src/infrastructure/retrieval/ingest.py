import hashlib
import json
import logging
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional

from src.infrastructure.retrieval.pdf_ocr import PdfTableOCR, extract_tables_with_fallback

from src.core.config.agent_prompts import (
    METADATA_ONLY_EXTENSIONS,
    PDF_SEMANTIC_CHUNK_LIMIT,
    PDF_SEMANTIC_PAGE_LIMIT,
    RAG_REGISTER_SCHEMA_FILE,
    RAG_SCHEMA_VERSION,
    TEXT_CHUNK_OVERLAP_RATIO,
    TEXT_PREVIEW_EXTENSIONS,
    TEXT_SECTION_CHUNK_CHARS,
    TEXT_SECTION_CHUNK_LIMIT,
    VENDOR_FILE_PATTERNS,
    VENDOR_PATH_PARTS,
    WORKSPACE_DOC_ROOTS,
)
from src.infrastructure.models import ChunkRecord
from src.infrastructure.retrieval.manifest import IndexManifest, compute_file_hash, compute_content_hash

try:
    import fitz
except ImportError:
    fitz = None

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None

logger = logging.getLogger(__name__)


def compact_text(text: object, max_chars: int, marker: str = " ...[TRUNCATED]... ") -> str:
    """Compact long evidence without losing both ends of the source text."""
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= max_chars:
        return normalized
    if max_chars <= len(marker) + 2:
        return normalized[:max_chars].strip()
    head = max((max_chars - len(marker)) // 2, 1)
    tail = max(max_chars - len(marker) - head, 1)
    return f"{normalized[:head].rstrip()}{marker}{normalized[-tail:].lstrip()}"


class RetrievalIngestor:
    def __init__(self, file_tools, reference_kb, chunk_store, is_vendor_managed_path: Optional[Callable[[str], bool]] = None):
        self.file_tools = file_tools
        self.reference_kb = reference_kb
        self.chunk_store = chunk_store
        self._is_vendor_managed_path = is_vendor_managed_path or self._default_vendor_managed_path
        self._register_schema_entries: List[Dict] = []
        self._manifest: Optional[IndexManifest] = None

    @property
    def manifest(self) -> IndexManifest:
        """Lazy-initialize manifest."""
        if self._manifest is None:
            self._manifest = IndexManifest(self.file_tools.workspace_root)
        return self._manifest

    def bootstrap_rag_index(self, include_semantic: bool = False, progress_callback=None) -> None:
        """
        Build the RAG index from all available sources.

        Uses incremental rebuilds when possible:
        - If schema version unchanged and manifest exists, only re-index changed sources
        - If schema version changed, full rebuild is required (no migration path from v9)

        Args:
            include_semantic: Build semantic (vector) index.
            progress_callback: Optional callable(current, total, message) for progress updates.
        """
        if not self.should_rebuild_rag_index(require_page_chunks=include_semantic):
            return

        documents = self.reference_kb.data.get("documents", {}) if isinstance(self.reference_kb.data, dict) else {}
        if not isinstance(documents, dict):
            return

        chunks: List[ChunkRecord] = []
        self._register_schema_entries = []

        # Progress-aware iteration over documents
        doc_items = list(documents.items())
        for idx, (key, doc) in enumerate(doc_items):
            if not isinstance(doc, dict):
                continue
            if progress_callback:
                progress_callback(idx, len(doc_items), f"Indexing {key}...")
            chunks.extend(self.build_pdf_chunks(str(key), doc, include_semantic=include_semantic))

        if progress_callback:
            progress_callback(len(doc_items), len(doc_items), "Building workspace index...")

        chunks.extend(self.build_workspace_asset_chunks(include_semantic=include_semantic))

        if chunks:
            if progress_callback:
                progress_callback(len(doc_items) + 1, len(doc_items) + 2, "Writing chunk store...")
            self.chunk_store.replace_all(chunks)

        if progress_callback:
            progress_callback(len(doc_items) + 2, len(doc_items) + 2, "Done")

        self.write_register_schema()
        self.manifest.record_build(RAG_SCHEMA_VERSION, len(chunks))

    def should_rebuild_rag_index(self, require_page_chunks: bool = False) -> bool:
        if self.chunk_store.is_empty():
            return True

        # Check manifest for smart rebuild decision
        if not self.manifest.needs_full_rebuild():
            # Schema version matches - check for incremental updates
            return False

        # Schema version changed or no manifest - need full rebuild
        existing_chunks = self.chunk_store.get_all()
        has_current_schema = any(
            isinstance(chunk.metadata, dict) and chunk.metadata.get("rag_schema") == RAG_SCHEMA_VERSION
            for chunk in existing_chunks[:50]
        )
        if not has_current_schema:
            return True
        pdf_page_chunks = [
            chunk for chunk in existing_chunks[:200]
            if isinstance(chunk.metadata, dict) and str(chunk.metadata.get("chunk_role", "")).strip().lower() in {"pdf_page", "pdf_page_selective"}
        ]
        if require_page_chunks and not pdf_page_chunks:
            return True
        if pdf_page_chunks:
            has_page_context = any(
                str(chunk.metadata.get("section_title", "")).strip()
                or str(chunk.metadata.get("toc_section", "")).strip()
                for chunk in pdf_page_chunks
            )
            has_register_context = any(
                chunk.metadata.get("register_terms") or chunk.metadata.get("bitfield_terms")
                for chunk in pdf_page_chunks
            )
            if not has_page_context or not has_register_context:
                return True
        return False

    def build_pdf_chunks(self, key: str, doc: Dict, include_semantic: bool = True) -> List[ChunkRecord]:
        filename = str(doc.get("filename", key)).strip()
        title = str(doc.get("title", "")).strip()
        summary = str(doc.get("summary", "")).strip()
        preview = str(doc.get("content_preview", "")).strip()
        doc_type = self.infer_pdf_doc_type(filename, title, summary)
        chips = [str(item).strip() for item in doc.get("chips", []) if str(item).strip()]
        topics = [str(item).strip() for item in doc.get("topics", []) if str(item).strip()]
        chapters = [str(item).strip() for item in doc.get("chapters", []) if str(item).strip()]
        use_cases = [str(item).strip() for item in doc.get("use_cases", []) if str(item).strip()]

        base_metadata = {
            "topics": topics,
            "chapters": chapters,
            "use_cases": use_cases,
            "title": title,
            "chips": chips,
            "doc_type": doc_type,
            "rag_schema": RAG_SCHEMA_VERSION,
        }

        chunks: List[ChunkRecord] = []
        overview_parts = [
            title,
            summary,
            preview,
            "Chapters: " + ", ".join(chapters[:8]) if chapters else "",
            "Topics: " + ", ".join(topics[:8]) if topics else "",
            "Use cases: " + ", ".join(use_cases[:6]) if use_cases else "",
        ]
        overview_text = "\n".join(part for part in overview_parts if part).strip()
        if overview_text:
            chunks.append(self.make_pdf_chunk(
                key=key,
                filename=filename,
                section="document_overview",
                summary=summary or title,
                text=overview_text,
                metadata={**base_metadata, "section": "document_overview", "chunk_role": "overview"},
            ))

        for chapter in chapters[:12]:
            chapter_text = "\n".join(part for part in [
                title,
                f"Chapter focus: {chapter}",
                summary,
                "Related topics: " + ", ".join(topics[:6]) if topics else "",
                "Relevant use cases: " + ", ".join(use_cases[:4]) if use_cases else "",
            ] if part).strip()
            chunks.append(self.make_pdf_chunk(
                key=key,
                filename=filename,
                section=chapter,
                summary=f"{chapter} in {filename}",
                text=chapter_text,
                metadata={**base_metadata, "section": chapter, "chunk_role": "chapter"},
            ))

        for topic in topics[:10]:
            topic_text = "\n".join(part for part in [
                title,
                f"Topic focus: {topic}",
                summary,
                "Related chapters: " + ", ".join(chapters[:6]) if chapters else "",
            ] if part).strip()
            chunks.append(self.make_pdf_chunk(
                key=key,
                filename=filename,
                section=topic,
                summary=f"{topic} in {filename}",
                text=topic_text,
                metadata={**base_metadata, "section": topic, "chunk_role": "topic"},
            ))

        for use_case in use_cases[:8]:
            use_case_text = "\n".join(part for part in [
                title,
                f"Use case focus: {use_case}",
                summary,
                "Related topics: " + ", ".join(topics[:6]) if topics else "",
                "Related chapters: " + ", ".join(chapters[:6]) if chapters else "",
            ] if part).strip()
            chunks.append(self.make_pdf_chunk(
                key=key,
                filename=filename,
                section=use_case,
                summary=f"{use_case} in {filename}",
                text=use_case_text,
                metadata={**base_metadata, "section": use_case, "chunk_role": "use_case"},
            ))

        resolved_pdf = self.resolve_workspace_document_path(filename)
        if include_semantic and resolved_pdf is not None and resolved_pdf.suffix.lower() == ".pdf" and self.should_semantically_index_kb_pdf(filename, title, summary, doc_type, topics, chapters, use_cases):
            chunks.extend(self.build_pdf_semantic_chunks(resolved_pdf, filename, base_metadata))

        return chunks

    def build_workspace_asset_chunks(self, include_semantic: bool = True) -> List[ChunkRecord]:
        chunks: List[ChunkRecord] = []
        seen_paths = set()
        for root in WORKSPACE_DOC_ROOTS:
            root_path = (self.file_tools.workspace_root / Path(root)).resolve()
            if not root_path.exists() or not root_path.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root_path):
                current_dir = Path(dirpath)
                dirnames[:] = [dirname for dirname in dirnames if not self.should_prune_workspace_dir(current_dir / dirname)]
                for filename in filenames:
                    file_path = current_dir / filename
                    suffix = file_path.suffix.lower()
                    if suffix not in TEXT_PREVIEW_EXTENSIONS and suffix not in METADATA_ONLY_EXTENSIONS:
                        continue
                    normalized_path = str(file_path.relative_to(self.file_tools.workspace_root)).replace("\\", "/")
                    if self.should_skip_workspace_indexing(file_path, normalized_path):
                        continue
                    if normalized_path in seen_paths:
                        continue
                    seen_paths.add(normalized_path)
                    chunks.extend(self.build_workspace_file_chunks(file_path, normalized_path, include_semantic=include_semantic))
        return chunks

    def build_workspace_file_chunks(self, file_path: Path, normalized_path: str, include_semantic: bool = True) -> List[ChunkRecord]:
        suffix = file_path.suffix.lower()
        path_parts = list(Path(normalized_path).parts)
        filename = file_path.name
        source_type = self.infer_chunk_source_type(file_path)
        section = "/".join(path_parts[-4:-1]) if len(path_parts) > 1 else "workspace_file"
        summary = f"Workspace asset: {filename}"
        preview = ""
        if suffix in TEXT_PREVIEW_EXTENSIONS:
            try:
                preview = file_path.read_text(encoding="utf-8", errors="ignore")[:1200].strip()
            except OSError:
                preview = ""
        text_parts = [
            f"Path: {normalized_path}",
            f"Filename: {filename}",
            f"Extension: {suffix or 'none'}",
            f"Folders: {' '.join(path_parts[:-1])}",
            preview,
        ]
        text = "\n".join(part for part in text_parts if part).strip()
        if not text:
            return []
        metadata = {
            "title": filename,
            "topics": [part for part in path_parts[:-1] if part],
            "chapters": [section] if section else [],
            "use_cases": path_parts[-3:-1] if len(path_parts) >= 3 else [],
            "doc_type": self.infer_workspace_doc_type(file_path),
            "chunk_role": "workspace_file",
            "rag_schema": RAG_SCHEMA_VERSION,
        }
        chunks = [self.make_pdf_chunk(
            key=normalized_path,
            filename=normalized_path,
            section=section,
            summary=summary,
            text=text,
            source_type=source_type,
            metadata=metadata,
        )]

        if include_semantic and suffix in TEXT_PREVIEW_EXTENSIONS:
            chunks.extend(self.build_text_semantic_chunks(file_path, normalized_path, metadata))
        elif include_semantic and suffix == ".pdf" and self.should_semantically_index_workspace_pdf(normalized_path):
            chunks.extend(self.build_pdf_semantic_chunks(file_path, normalized_path, metadata))

        return chunks

    def build_text_semantic_chunks(self, file_path: Path, normalized_path: str, metadata: Dict) -> List[ChunkRecord]:
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []

        content = content.strip()
        if len(content) < 200:
            return []

        chunks: List[ChunkRecord] = []
        section_title = "document_body"
        section_buffer: List[str] = []

        def flush_section() -> None:
            nonlocal section_buffer, section_title
            section_text = "\n".join(part for part in section_buffer if part).strip()
            if len(section_text) < 120:
                section_buffer = []
                return
            windows = self.chunk_text_with_overlap(section_text, TEXT_SECTION_CHUNK_CHARS)
            for index, window in enumerate(windows, start=1):
                chunks.append(self.make_pdf_chunk(
                    key=f"{normalized_path}:{section_title}:{index}",
                    filename=normalized_path,
                    section=section_title,
                    summary=f"Section {section_title} in {file_path.name}",
                    text=window,
                    source_type=self.infer_chunk_source_type(file_path),
                    metadata={**metadata, "section": section_title, "chunk_role": "text_section", "window": index},
                ))
            section_buffer = []

        for line in content.splitlines():
            stripped = line.strip()
            is_heading = bool(re.match(r"^(#+\s+.+|[A-Z][A-Za-z0-9 _/\-]{2,80}:)$", stripped))
            if is_heading:
                flush_section()
                section_title = re.sub(r"^#+\s*", "", stripped).rstrip(":").strip() or section_title
                continue
            section_buffer.append(line)

        flush_section()
        return chunks[:TEXT_SECTION_CHUNK_LIMIT]

    def build_pdf_semantic_chunks(self, file_path: Path, normalized_path: str, metadata: Dict) -> List[ChunkRecord]:
        page_texts = self.extract_pdf_structured_pages(file_path)
        if not page_texts and PdfReader is not None:
            try:
                reader = PdfReader(str(file_path))
                page_texts = [self.extract_pdf_page_text_with_fallback(reader.pages[index]) for index in range(len(reader.pages))]
            except Exception:
                page_texts = []

        page_texts = [text for text in page_texts if str(text).strip()]
        page_count = len(page_texts)
        if page_count == 0:
            return []

        selected_pages = self.select_pdf_page_indices(page_count)
        chunks: List[ChunkRecord] = []
        toc_buffer: List[str] = []
        toc_entries = self.extract_pdf_toc_entries(file_path, page_texts)
        layout_tables_by_page = self.extract_pdf_layout_tables(file_path)
        for page_index in selected_pages:
            text = page_texts[page_index - 1]
            if len(text) < 120:
                continue
            chunk_role = "pdf_page" if page_count <= PDF_SEMANTIC_PAGE_LIMIT else "pdf_page_selective"
            section_title = self.infer_pdf_page_section_title(text)
            register_terms = self.extract_register_terms_from_text(text)
            bitfield_terms = self.extract_bitfield_terms_from_text(text)
            register_table_hints = self.extract_register_table_hints(text)
            layout_register_entries = self.extract_register_schema_entries_from_layout_tables(
                layout_tables_by_page.get(page_index, []),
                normalized_path,
                page_index,
                section_title,
            )
            text_register_entries = self.extract_register_schema_entries(text, normalized_path, page_index, section_title)
            register_schema_entries = self.dedupe_register_schema_entries(layout_register_entries + text_register_entries)
            self._register_schema_entries.extend(register_schema_entries)
            toc_match = self.match_page_to_toc_entry(page_index, toc_entries)
            windows = self.chunk_text_with_overlap(text, TEXT_SECTION_CHUNK_CHARS)
            for window_index, window in enumerate(windows, start=1):
                chunks.append(self.make_pdf_chunk(
                    key=f"{normalized_path}:page:{page_index}:{window_index}",
                    filename=normalized_path,
                    section=f"page_{page_index}",
                    summary=f"Page {page_index} in {file_path.name}",
                    text=window,
                    source_type="pdf",
                    metadata={
                        **metadata,
                        "section": f"page_{page_index}",
                        "chunk_role": chunk_role,
                        "page": page_index,
                        "window": window_index,
                        "section_title": section_title,
                        "register_terms": register_terms[:12],
                        "bitfield_terms": bitfield_terms[:12],
                        "register_table_hints": register_table_hints[:12],
                        "register_schema_entries": register_schema_entries[:8],
                        "layout_tables": [
                            {
                                "table_id": table.get("table_id", ""),
                                "table_bbox": table.get("table_bbox", []),
                                "extraction_quality": table.get("extraction_quality", {}),
                            }
                            for table in layout_tables_by_page.get(page_index, [])[:4]
                        ],
                        "toc_section": toc_match.get("title", ""),
                        "toc_level": toc_match.get("level", 0),
                        "toc_page_anchor": toc_match.get("page", 0),
                    },
                ))
            if page_index <= min(12, page_count):
                toc_buffer.append(text[:TEXT_SECTION_CHUNK_CHARS])
            if len(chunks) >= PDF_SEMANTIC_CHUNK_LIMIT:
                break

        toc_text = self.format_pdf_toc_entries(toc_entries)
        if not toc_text:
            toc_text = self.extract_pdf_toc_with_pymupdf(file_path)
        if not toc_text:
            toc_text = self.extract_pdf_toc_text(toc_buffer)

        if toc_text:
            chunks.insert(0, self.make_pdf_chunk(
                key=f"{normalized_path}:toc",
                filename=normalized_path,
                section="table_of_contents",
                summary=f"Selective section hints in {file_path.name}",
                text=toc_text[:TEXT_SECTION_CHUNK_CHARS],
                source_type="pdf",
                metadata={**metadata, "section": "table_of_contents", "chunk_role": "pdf_toc", "toc_entries": toc_entries[:40]},
            ))
        return chunks

    def extract_pdf_layout_tables(self, file_path: Path) -> Dict[int, List[Dict]]:
        """Extract PyMuPDF tables with page/table/row/cell coordinates."""
        if fitz is None:
            return {}
        try:
            document = fitz.open(str(file_path))
        except Exception:
            return {}
        pages: Dict[int, List[Dict]] = {}
        try:
            for page_number, page in enumerate(document, start=1):
                try:
                    tables = page.find_tables()
                except Exception:
                    tables = []
                for table_index, table in enumerate(tables or [], start=1):
                    try:
                        rows = table.extract()
                    except Exception:
                        rows = []
                    normalized_rows = [[str(cell or "").replace("\n", " ").strip() for cell in row] for row in rows if row]
                    if not normalized_rows:
                        continue
                    headers = normalized_rows[0]
                    body = normalized_rows[1:]
                    table_bbox = self.normalize_bbox(getattr(table, "bbox", []))
                    table_id = hashlib.sha1(f"{file_path.name}:{page_number}:{table_index}:{table_bbox}".encode("utf-8")).hexdigest()[:16]
                    cells = self.extract_layout_cells(table, page_number, table_id, table_bbox, headers, normalized_rows)
                    pages.setdefault(page_number, []).append({
                        "table_id": table_id,
                        "page_number": page_number,
                        "table_bbox": table_bbox,
                        "headers": headers,
                        "rows": body,
                        "cells": cells,
                        "extraction_quality": {
                            "method": "pymupdf_layout_table",
                            "row_count": len(body),
                            "column_count": len(headers),
                            "has_cell_bbox": any(cell.get("cell_bbox") for cell in cells),
                            "confidence": self.layout_table_confidence(headers, body, cells),
                        },
                    })
        finally:
            document.close()
        return pages

    def extract_layout_cells(self, table, page_number: int, table_id: str, table_bbox: List[float], headers: List[str], rows: List[List[str]]) -> List[Dict]:
        raw_cells = list(getattr(table, "cells", []) or [])
        column_count = max(len(headers), 1)
        cells: List[Dict] = []
        for body_row_index, row in enumerate(rows, start=1):
            row_boxes = []
            row_cells: List[Dict] = []
            for column_index, value in enumerate(row):
                flat_index = body_row_index * column_count + column_index
                cell_bbox = self.normalize_bbox(raw_cells[flat_index]) if flat_index < len(raw_cells) else []
                if cell_bbox:
                    row_boxes.append(cell_bbox)
                row_cells.append({
                    "page_number": page_number,
                    "table_id": table_id,
                    "table_bbox": table_bbox,
                    "row_index": body_row_index,
                    "row_bbox": [],
                    "column_index": column_index,
                    "column_name": headers[column_index] if column_index < len(headers) else f"column_{column_index + 1}",
                    "cell_bbox": cell_bbox,
                    "text": str(value or "").strip(),
                    "extraction_method": "layout_table",
                    "confidence": 0.96 if cell_bbox else 0.86,
                })
            row_bbox = self.union_bbox(row_boxes)
            for cell in row_cells:
                cell["row_bbox"] = row_bbox
            cells.extend(row_cells)
        return cells

    def normalize_bbox(self, bbox) -> List[float]:
        try:
            values = [float(value) for value in list(bbox)[:4]]
        except (TypeError, ValueError, OverflowError):
            return []
        if len(values) < 4:
            return []
        if not all(math.isfinite(value) for value in values):
            return []
        x0, y0, x1, y1 = values
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        return [round(value, 3) for value in (x0, y0, x1, y1)]

    def union_bbox(self, boxes: List[List[float]]) -> List[float]:
        valid = [self.normalize_bbox(box) for box in boxes]
        valid = [box for box in valid if box]
        if not valid:
            return []
        return [
            round(min(box[0] for box in valid), 3),
            round(min(box[1] for box in valid), 3),
            round(max(box[2] for box in valid), 3),
            round(max(box[3] for box in valid), 3),
        ]

    def layout_table_confidence(self, headers: List[str], rows: List[List[str]], cells: List[Dict]) -> float:
        if not headers or not rows:
            return 0.0
        filled = sum(1 for row in rows for cell in row if str(cell).strip())
        total = sum(max(len(row), 1) for row in rows) or 1
        bbox_bonus = 0.08 if any(cell.get("cell_bbox") for cell in cells) else 0.0
        return round(min(0.72 + (filled / total) * 0.18 + bbox_bonus, 0.98), 3)

    def assess_table_quality(self, table: Dict) -> Dict:
        """
        Assess the quality of an extracted table.
        
        Returns a detailed quality report with:
        - overall_score: 0.0-1.0
        - confidence: low/medium/high
        - issues: list of detected problems
        - recommendation: use_table/ocr_required/human_review
        """
        quality = table.get("extraction_quality", {})
        confidence = float(quality.get("confidence", 0.0))
        
        headers = table.get("headers", [])
        rows = table.get("rows", [])
        cells = table.get("cells", [])
        
        issues = []
        
        # Check for empty/missing content
        if not headers:
            issues.append("no_headers")
        if not rows:
            issues.append("no_data_rows")
            
        # Check for sparse content (potential merged cell issue)
        filled_cells = sum(1 for row in rows for cell in row if str(cell).strip())
        total_cells = sum(len(row) for row in rows) or 1
        fill_ratio = filled_cells / total_cells if total_cells > 0 else 0
        if fill_ratio < 0.5:
            issues.append("sparse_content")
            
        # Check for inconsistent column counts (merged cell symptom)
        if rows:
            col_counts = [len(row) for row in rows]
            if len(set(col_counts)) > 1:
                issues.append("inconsistent_columns")
                
        # Check for missing cell bounding boxes
        has_bbox = any(cell.get("cell_bbox") for cell in cells)
        if not has_bbox:
            issues.append("no_cell_coordinates")
            
        # Check for suspicious content (OCR errors)
        if headers or rows:
            all_text = " ".join([" ".join(headers), " ".join([" ".join(r) for r in rows])])
            if re.search(r"[\|\[\]{}]", all_text) and confidence < 0.8:
                issues.append("potential_ocr_errors")
                
        # Calculate overall score
        base_score = confidence
        if "no_headers" in issues:
            base_score *= 0.7
        if "sparse_content" in issues:
            base_score *= 0.8
        if "inconsistent_columns" in issues:
            base_score *= 0.75
        if "no_cell_coordinates" in issues:
            base_score *= 0.85
        if "potential_ocr_errors" in issues:
            base_score *= 0.7
            
        overall_score = round(min(base_score, 0.98), 3)
        
        # Determine recommendation
        if overall_score >= 0.85 and not issues:
            recommendation = "use_table"
        elif overall_score >= 0.7:
            recommendation = "use_with_caution"
        elif overall_score >= 0.5:
            recommendation = "ocr_required"
        else:
            recommendation = "human_review"
            
        return {
            "overall_score": overall_score,
            "confidence": "high" if overall_score >= 0.85 else "medium" if overall_score >= 0.7 else "low",
            "issues": issues,
            "fill_ratio": round(fill_ratio, 3),
            "row_count": len(rows),
            "column_count": len(headers),
            "has_coordinates": has_bbox,
            "recommendation": recommendation,
        }

    def extract_table_with_ocr_fallback(
        self,
        file_path: Path,
        page_number: int,
        table_bbox: List[float],
        threshold_confidence: float = 0.75,
    ) -> Optional[Dict]:
        """
        Extract table with OCR fallback when layout extraction has low confidence.
        
        Args:
            file_path: Path to PDF file
            page_number: Page number (1-indexed)
            table_bbox: Bounding box of the table [x0, y0, x1, y1]
            threshold_confidence: Minimum confidence to use layout extraction
            
        Returns:
            Enhanced table dict with OCR fallback data, or None if all methods fail
        """
        if fitz is None:
            return None
            
        try:
            document = fitz.open(str(file_path))
            page = document[page_number - 1]
        except Exception:
            return None
            
        try:
            # Get layout extraction tables for comparison
            layout_tables = self.extract_pdf_layout_tables(file_path)
            page_tables = layout_tables.get(page_number, [])
            
            # Find matching table by bbox
            matching_table = None
            for tbl in page_tables:
                if tbl.get("table_bbox") == table_bbox:
                    matching_table = tbl
                    break
                    
            if matching_table:
                quality = self.assess_table_quality(matching_table)
                
                # If already good, no need for OCR
                if quality["overall_score"] >= threshold_confidence:
                    document.close()
                    return matching_table
                    
                # Check if OCR is likely to help
                needs_ocr = (
                    quality["overall_score"] < threshold_confidence or
                    "sparse_content" in quality["issues"] or
                    "inconsistent_columns" in quality["issues"] or
                    "potential_ocr_errors" in quality["issues"]
                )
                
                if needs_ocr:
                    ocr_result = self._extract_table_region_with_ocr(page, table_bbox)
                    if ocr_result:
                        # Merge OCR result with layout
                        merged = self._merge_table_extractions(matching_table, ocr_result)
                        merged["extraction_quality"]["ocr_applied"] = True
                        merged["extraction_quality"]["original_confidence"] = quality["overall_score"]
                        merged["extraction_quality"]["ocr_confidence"] = ocr_result.get("confidence", 0.0)
                        document.close()
                        return merged
                        
            # No matching table found, try direct OCR
            ocr_result = self._extract_table_region_with_ocr(page, table_bbox)
            if ocr_result:
                document.close()
                return ocr_result
                
        finally:
            document.close()
            
        return None

    def _extract_table_region_with_ocr(self, page, table_bbox: List[float]) -> Optional[Dict]:
        """
        Extract table content using OCR on a specific region.
        Uses PyMuPDF's built-in text extraction as fallback OCR.
        """
        if len(table_bbox) < 4:
            return None
            
        x0, y0, x1, y1 = table_bbox
        
        # Expand bbox slightly to capture full content
        padding = 2
        x0 = max(0, x0 - padding)
        y0 = max(0, y0 - padding)
        
        try:
            # Extract text from region
            clip = fitz.Rect(x0, y0, x1, y1)
            blocks = page.get_text("dict", clip=clip)
            
            text_blocks = []
            if isinstance(blocks, dict) and "blocks" in blocks:
                for block in blocks["blocks"]:
                    if block.get("type") == 0:  # Text block
                        text_blocks.append(block)
                        
            if not text_blocks:
                return None
                
            # Parse into table format
            rows = self._parse_text_blocks_as_table(text_blocks)
            if not rows:
                return None
                
            headers = rows[0] if rows else []
            body = rows[1:] if len(rows) > 1 else []
            
            return {
                "table_id": f"ocr_{hashlib.md5(str(table_bbox).encode()).hexdigest()[:8]}",
                "page_number": 0,  # Unknown at this point
                "table_bbox": table_bbox,
                "headers": headers,
                "rows": body,
                "cells": [],
                "extraction_quality": {
                    "method": "ocr_fallback",
                    "confidence": 0.78,  # Lower than layout
                    "row_count": len(body),
                    "column_count": len(headers),
                    "has_cell_bbox": False,
                    "ocr_applied": True,
                },
            }
            
        except Exception as exc:
            logger.warning("OCR table extraction failed: %s", exc)
            return None

    def _parse_text_blocks_as_table(self, text_blocks: List[Dict]) -> List[List[str]]:
        """
        Parse text blocks into table rows based on spatial arrangement.
        """
        if not text_blocks:
            return []
            
        # Sort blocks by vertical position, then horizontal
        sorted_blocks = sorted(
            text_blocks,
            key=lambda b: (
                float(b.get("bbox", [0, 0, 0, 0])[1]),
                float(b.get("bbox", [0, 0, 0, 0])[0])
            )
        )
        
        # Group blocks into rows based on y-coordinate
        rows = []
        current_row = []
        current_y = None
        row_threshold = 5  # pixels
        
        for block in sorted_blocks:
            bbox = block.get("bbox", [0, 0, 0, 0])
            block_y = float(bbox[1])
            block_text = ""
            
            # Extract text from lines
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        block_text += span.get("text", "")
                    block_text += " "
                    
            block_text = block_text.strip()
            if not block_text:
                continue
                
            # Split by multiple spaces (column separator approximation)
            cells = re.split(r"\s{2,}", block_text)
            
            if current_y is None or abs(block_y - current_y) < row_threshold:
                current_row.extend(cells)
                current_y = block_y
            else:
                if current_row:
                    rows.append(current_row)
                current_row = cells
                current_y = block_y
                
        if current_row:
            rows.append(current_row)
            
        return rows

    def _merge_table_extractions(self, layout_table: Dict, ocr_table: Dict) -> Dict:
        """
        Merge layout table with OCR table, preferring layout for coordinate data.
        """
        merged = dict(layout_table)
        
        # If OCR has more rows, use it for data
        layout_rows = len(layout_table.get("rows", []))
        ocr_rows = len(ocr_table.get("rows", []))
        
        if ocr_rows > layout_rows:
            merged["rows"] = ocr_table.get("rows", [])
            
        # If OCR has correct column count, use headers
        layout_cols = len(layout_table.get("headers", []))
        ocr_cols = len(ocr_table.get("headers", []))
        
        # Prefer layout headers but merge if OCR provides additional info
        if ocr_cols > 0 and ocr_cols != layout_cols:
            # Take longer row as reference for column count
            merged["headers"] = max(
                [layout_table.get("headers", [])],
                [ocr_table.get("headers", [])],
                key=len
            )
            
        # Recalculate quality
        merged["extraction_quality"]["merged"] = True
        merged["extraction_quality"]["layout_rows"] = layout_rows
        merged["extraction_quality"]["ocr_rows"] = ocr_rows
        
        return merged

    def filter_tables_by_quality(
        self,
        tables: List[Dict],
        min_confidence: float = 0.75,
        require_coordinates: bool = False,
    ) -> Dict[str, List[Dict]]:
        """
        Filter tables based on quality thresholds.
        
        Args:
            tables: List of extracted table dicts
            min_confidence: Minimum confidence to include table
            require_coordinates: If True, require cell bboxes
            
        Returns:
            Dict with:
            - approved: Tables that passed quality checks
            - needs_ocr: Tables that should be re-extracted with OCR
            - requires_review: Tables that need human review
        """
        approved = []
        needs_ocr = []
        requires_review = []
        
        for table in tables:
            quality = self.assess_table_quality(table)
            table["quality_report"] = quality
            
            # Check requirements
            has_enough_confidence = quality["overall_score"] >= min_confidence
            has_coords = quality["has_coordinates"] or not require_coordinates
            
            if quality["recommendation"] == "human_review":
                requires_review.append(table)
            elif not has_enough_confidence or not has_coords:
                needs_ocr.append(table)
            else:
                approved.append(table)
                
        return {
            "approved": approved,
            "needs_ocr": needs_ocr,
            "requires_review": requires_review,
            "summary": {
                "total": len(tables),
                "approved_count": len(approved),
                "needs_ocr_count": len(needs_ocr),
                "requires_review_count": len(requires_review),
                "min_confidence": min_confidence,
            },
        }

    def get_register_tables_from_pdf(
        self,
        file_path: Path,
        min_quality: float = 0.70,
        use_ocr_fallback: bool = True,
    ) -> Dict:
        """
        Extract register-related tables from a PDF with quality control.
        
        This is the main entry point for extracting register maps from PDFs
        with automatic OCR fallback and quality scoring.
        
        Args:
            file_path: Path to the PDF
            min_quality: Minimum quality score for approved tables
            use_ocr_fallback: Whether to use OCR for low-quality tables
            
        Returns:
            Dict with:
            - tables: List of extracted tables with quality reports
            - register_entries: Extracted register schema entries
            - validation: Quality validation summary
        """
        layout_tables = self.extract_pdf_layout_tables(file_path)
        
        all_tables = []
        for page_num, page_tables in layout_tables.items():
            for table in page_tables:
                table["page_number"] = page_num
                all_tables.append(table)
                
        # Filter by quality
        filtered = self.filter_tables_by_quality(
            all_tables,
            min_confidence=min_quality,
            require_coordinates=False,
        )
        
        # Apply Enhanced OCR fallback if enabled (merged cell detection)
        ocr_tables = []
        if use_ocr_fallback and fitz is not None:
            try:
                document = fitz.open(str(file_path))
                for table in filtered["needs_ocr"]:
                    page_num = table.get("page_number", 1)
                    if page_num <= len(document):
                        page = document[page_num - 1]
                        ocr = PdfTableOCR()
                        result = ocr.extract_table_with_merged_cells(
                            page,
                            table.get("table_bbox", []),
                        )
                        if result.success:
                            # Convert OCR result to table dict format
                            if result.grid:
                                table["headers"] = result.grid.headers
                                table["rows"] = [[c.text for c in row] for row in result.grid.rows if row]
                                table["cells"] = [
                                    {"text": c.text, "row": c.row, "col": c.col}
                                    for row in result.grid.rows if row for c in row if c
                                ]
                            table["extraction_quality"]["ocr_quality_score"] = result.quality_score
                            table["extraction_quality"]["ocr_method"] = result.method
                            ocr_tables.append(table)
                document.close()
            except Exception as e:
                logger.warning(f"Enhanced OCR fallback failed: {e}")
                        
        # Combine results
        final_tables = filtered["approved"] + ocr_tables
        
        # Re-assess quality of OCR tables
        for table in ocr_tables:
            quality = self.assess_table_quality(table)
            table["quality_report"] = quality
            if quality["overall_score"] < min_quality:
                filtered["requires_review"].append(table)
                
        # Extract register entries from approved tables
        register_entries = []
        for table in final_tables:
            if table.get("quality_report", {}).get("overall_score", 0) >= min_quality:
                entries = self.extract_register_schema_entries_from_layout_tables(
                    [table],
                    str(file_path),
                    table.get("page_number", 1),
                    "",
                )
                register_entries.extend(entries)
                
        return {
            "tables": final_tables,
            "register_entries": register_entries,
            "validation": {
                "total_extracted": len(all_tables),
                "approved": len(filtered["approved"]),
                "ocr_recovered": len(ocr_tables),
                "requires_review": len(filtered["requires_review"]),
                "min_quality_threshold": min_quality,
            },
            "needs_review": filtered["requires_review"],
        }

    def chunk_text_with_overlap(self, text: str, max_chars: int) -> List[str]:
        overlap_chars = max(int(max_chars * TEXT_CHUNK_OVERLAP_RATIO), 120)
        separators = ["\n\n", "\n", ". ", " "]

        def split_recursively(text_to_split: str, current_sep_index: int) -> List[str]:
            if len(text_to_split) <= max_chars:
                return [text_to_split]
            if current_sep_index >= len(separators):
                return [text_to_split[i:i + max_chars] for i in range(0, len(text_to_split), max_chars - overlap_chars)]

            separator = separators[current_sep_index]
            splits = text_to_split.split(separator)
            good_chunks = []
            current_chunk = []
            current_length = 0

            for item in splits:
                item_len = len(item) + (len(separator) if current_length > 0 else 0)
                if current_length + item_len > max_chars and current_length > 0:
                    joined_chunk = separator.join(current_chunk)
                    good_chunks.append(joined_chunk)
                    overlap_len = 0
                    overlap_chunk = []
                    for overlap_item in reversed(current_chunk):
                        if overlap_len + len(overlap_item) > overlap_chars and overlap_len > 0:
                            break
                        overlap_chunk.insert(0, overlap_item)
                        overlap_len += len(overlap_item) + len(separator)
                    current_chunk = overlap_chunk + [item]
                    current_length = sum(len(value) for value in current_chunk) + len(separator) * (len(current_chunk) - 1)
                else:
                    current_chunk.append(item)
                    current_length += item_len

            if current_chunk:
                good_chunks.append(separator.join(current_chunk))

            final_chunks = []
            for chunk in good_chunks:
                if len(chunk) > max_chars:
                    final_chunks.extend(split_recursively(chunk, current_sep_index + 1))
                else:
                    final_chunks.append(chunk)
            return final_chunks

        cleaned = re.sub(r"\n{3,}", "\n\n", str(text).strip())
        if not cleaned:
            return []
        raw_chunks = split_recursively(cleaned, 0)
        deduped: List[str] = []
        for window in raw_chunks:
            candidate = window.strip()
            if candidate and candidate not in deduped:
                deduped.append(candidate)
        return deduped

    def extract_pdf_structured_pages(self, file_path: Path) -> List[str]:
        if fitz is None:
            return []
        pages: List[str] = []
        try:
            document = fitz.open(str(file_path))
        except Exception:
            return []
        try:
            for page in document:
                page_text = self.extract_pdf_page_text_with_pymupdf(page)
                if not page_text:
                    try:
                        page_text = page.get_text("text", sort=True)
                    except Exception:
                        page_text = ""
                if not page_text:
                    try:
                        blocks = page.get_text("blocks")
                    except Exception:
                        blocks = []
                    ordered_blocks = sorted(blocks, key=lambda item: (float(item[1]), float(item[0])))
                    lines: List[str] = []
                    for block in ordered_blocks:
                        if len(block) < 5:
                            continue
                        text = self.clean_pdf_block_text(block[4])
                        if text:
                            lines.append(text)
                    page_text = "\n\n".join(lines)
                pages.append(self.normalize_pdf_page_text(page_text))
        finally:
            document.close()
        return pages

    def extract_pdf_page_text_with_pymupdf(self, page) -> str:
        text_parts = []
        table_bboxes = []
        try:
            if hasattr(page, "find_tables"):
                tables = page.find_tables()
                for table in tables:
                    if hasattr(table, "bbox"):
                        table_bboxes.append(table.bbox)
                    try:
                        md_table = table.to_markdown()
                        if md_table:
                            text_parts.append(f"\n[TABLE START]\n{md_table.strip()}\n[TABLE END]\n")
                    except AttributeError:
                        extracted = table.extract()
                        if extracted and len(extracted) > 0:
                            headers = extracted[0]
                            markdown = "| " + " | ".join(str(header or "").replace("\n", " ") for header in headers) + " |\n"
                            markdown += "|-" + "-|-".join("" for _ in headers) + "-|\n"
                            for row in extracted[1:]:
                                markdown += "| " + " | ".join(str(cell or "").replace("\n", " ") for cell in row) + " |\n"
                            text_parts.append(f"\n[TABLE START]\n{markdown.strip()}\n[TABLE END]\n")
        except Exception as exc:
            logger.warning("Table extraction failed: %s", exc)

        def overlaps_table(block_bbox):
            bx0, by0, bx1, by1 = block_bbox
            for tx0, ty0, tx1, ty1 in table_bboxes:
                ix0 = max(bx0, tx0)
                iy0 = max(by0, ty0)
                ix1 = min(bx1, tx1)
                iy1 = min(by1, ty1)
                if ix0 < ix1 and iy0 < iy1:
                    area_intersection = (ix1 - ix0) * (iy1 - iy0)
                    area_block = (bx1 - bx0) * (by1 - by0)
                    if area_block > 0 and (area_intersection / area_block) > 0.5:
                        return True
            return False

        try:
            page_dict = page.get_text("dict")
        except Exception:
            return "\n\n".join(text_parts).strip()

        blocks = page_dict.get("blocks", []) if isinstance(page_dict, dict) else []
        ordered_blocks = sorted(
            [block for block in blocks if isinstance(block, dict)],
            key=lambda item: (float(item.get("bbox", [0, 0, 0, 0])[1]), float(item.get("bbox", [0, 0, 0, 0])[0])),
        )
        lines: List[str] = []
        for block in ordered_blocks:
            if int(block.get("type", 0)) != 0:
                continue
            bbox = block.get("bbox", [0, 0, 0, 0])
            if table_bboxes and overlaps_table(bbox):
                continue
            block_lines: List[str] = []
            for line in block.get("lines", []):
                spans = line.get("spans", []) if isinstance(line, dict) else []
                span_lines: List[str] = []
                for span in spans:
                    cleaned = self.clean_pdf_block_text(span.get("text", ""))
                    if cleaned:
                        span_lines.append(cleaned)
                if span_lines:
                    block_lines.append(" ".join(span_lines))
            block_text = "\n".join(block_lines).strip()
            if block_text:
                lines.append(block_text)
        if lines:
            text_parts.append("\n\n".join(lines).strip())
        return "\n\n".join(text_parts).strip()

    def clean_pdf_block_text(self, text: str) -> str:
        cleaned_lines: List[str] = []
        for line in str(text).splitlines():
            stripped = re.sub(r"\s+", " ", line).strip()
            if stripped:
                cleaned_lines.append(stripped)
        return "\n".join(cleaned_lines).strip()

    def normalize_pdf_page_text(self, text: str) -> str:
        normalized = str(text or "").replace("\u00ad", "")
        normalized = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", normalized)
        normalized = re.sub(r"(?<![\.!?:;])\n(?=\w)", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        lines: List[str] = []
        previous = ""
        for raw_line in normalized.splitlines():
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue
            if re.fullmatch(r"(?:page|trang|pagina|seite)?\s*\d+(?:\s*/\s*\d+)?", line, re.IGNORECASE):
                continue
            if len(line) <= 2 and line.isdigit():
                continue
            if line == previous:
                continue
            lines.append(line)
            previous = line
        return "\n".join(lines).strip()

    def extract_pdf_page_text_with_fallback(self, page) -> str:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        return self.normalize_pdf_page_text(text)

    def select_pdf_page_indices(self, page_count: int) -> List[int]:
        if page_count <= PDF_SEMANTIC_PAGE_LIMIT:
            return list(range(1, page_count + 1))
        selected = set(range(1, min(13, page_count + 1)))
        if page_count > 20:
            interval = max(page_count // max(PDF_SEMANTIC_CHUNK_LIMIT - len(selected), 1), 1)
            for page_index in range(13, page_count + 1, interval):
                selected.add(page_index)
                if len(selected) >= PDF_SEMANTIC_CHUNK_LIMIT:
                    break
        return sorted(selected)[:PDF_SEMANTIC_CHUNK_LIMIT]

    def extract_pdf_toc_with_pymupdf(self, file_path: Path) -> str:
        if fitz is None:
            return ""
        try:
            document = fitz.open(str(file_path))
            toc = document.get_toc()
            document.close()
            if not toc:
                return ""
            lines = []
            for item in toc:
                if len(item) >= 3:
                    level, title, page = item[:3]
                    indent = "  " * (level - 1)
                    lines.append(f"{indent}- {title} (Page {page})")
            return "\n".join(lines)[:3000]
        except Exception as exc:
            logger.warning("Native TOC extraction failed: %s", exc)
            return ""

    def extract_pdf_toc_entries(self, file_path: Path, page_texts: List[str]) -> List[Dict]:
        entries = self.extract_pdf_toc_entries_with_pymupdf(file_path)
        if entries:
            return entries
        return self.extract_pdf_toc_entries_from_text(page_texts)

    def extract_pdf_toc_entries_with_pymupdf(self, file_path: Path) -> List[Dict]:
        if fitz is None:
            return []
        try:
            document = fitz.open(str(file_path))
            toc = document.get_toc()
            document.close()
        except Exception:
            return []
        entries: List[Dict] = []
        for item in toc or []:
            if len(item) < 3:
                continue
            level, title, page = item[:3]
            title_text = str(title).strip()
            page_number = int(page) if str(page).isdigit() else 0
            if title_text and page_number > 0:
                entries.append({"level": int(level), "title": title_text, "page": page_number})
        return entries[:120]

    def extract_pdf_toc_entries_from_text(self, page_texts: List[str]) -> List[Dict]:
        entries: List[Dict] = []
        for text in page_texts[:12]:
            for line in re.split(r"\n", text):
                candidate = re.sub(r"\s+", " ", line).strip()
                if len(candidate) < 8:
                    continue
                match = re.match(r"^(?:(\d+(?:\.\d+)*)\s+)?(.+?)\s+(\d{1,4})$", candidate)
                if not match:
                    continue
                title = str(match.group(2)).strip(". ").strip()
                page_number = int(match.group(3))
                level = str(match.group(1) or "").count(".") + 1 if match.group(1) else 1
                if title and any(token in title.lower() for token in ("chapter", "section", "gpio", "clock", "usart", "uart", "dma", "nvic", "timer", "rcc")):
                    entries.append({"level": level, "title": title, "page": page_number})
        return self.dedupe_toc_entries(entries)[:80]

    def format_pdf_toc_entries(self, entries: List[Dict]) -> str:
        lines: List[str] = []
        for item in entries[:60]:
            try:
                level = int(item.get("level", 1) or 1)
            except Exception:
                level = 1
            indent = "  " * max(level - 1, 0)
            title = str(item.get("title", "")).strip()
            page = str(item.get("page", "")).strip()
            if title and page:
                lines.append(f"{indent}- {title} (Page {page})")
        return "\n".join(lines)

    def match_page_to_toc_entry(self, page_index: int, toc_entries: List[Dict]) -> Dict:
        best: Dict = {}
        best_page = -1
        for entry in toc_entries:
            try:
                anchor_page = int(entry.get("page", 0) or 0)
            except Exception:
                continue
            if anchor_page <= page_index and anchor_page >= best_page:
                best = entry
                best_page = anchor_page
        return best

    def dedupe_toc_entries(self, entries: List[Dict]) -> List[Dict]:
        deduped: List[Dict] = []
        seen = set()
        for item in entries:
            key = (str(item.get("title", "")).strip().lower(), int(item.get("page", 0) or 0))
            if key in seen or not key[0] or key[1] <= 0:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def extract_pdf_toc_text(self, page_texts: List[str]) -> str:
        toc_lines: List[str] = []
        for text in page_texts:
            for line in re.split(r"(?<=[a-zA-Z0-9])\s{2,}|\n", text):
                candidate = line.strip()
                if len(candidate) < 12:
                    continue
                if re.search(r"\b\d{1,4}\b", candidate) and any(token in candidate.lower() for token in ("chapter", "section", "contents", ". .", ".....")):
                    toc_lines.append(candidate)
        toc_lines = self.dedupe_preserve_order(toc_lines)
        return "\n".join(toc_lines[:20])

    def infer_pdf_page_section_title(self, text: str) -> str:
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        for line in lines[:8]:
            normalized = compact_text(line, 120)
            if len(normalized) < 4 or len(normalized) > 120:
                continue
            if re.match(r"^(chapter|section)\b", normalized, re.IGNORECASE):
                return normalized
            if re.match(r"^\d+(?:\.\d+)*\s+[A-Za-z]", normalized):
                return normalized
            if normalized.isupper() and len(normalized.split()) <= 8:
                return normalized.title()
        return ""

    def extract_register_terms_from_text(self, text: str) -> List[str]:
        terms = self.dedupe_preserve_order(re.findall(r"\b(?:RCC|GPIO[A-Ix]?|USART[1-6x]?|UART[1-8x]?|DMA[12x]?|TIM(?:\d+|x)?|NVIC|EXTI|SYSCFG|FLASH|PWR)_[A-Z0-9]+\b", str(text)))
        return terms[:16]

    def extract_bitfield_terms_from_text(self, text: str) -> List[str]:
        terms = self.dedupe_preserve_order(re.findall(r"\b(?:AF\d+|UE|TE|RE|RXNE|TXE|TC|DMAT|DMAR|RXNEIE|TXEIE|TCIE|CHSEL|DIR|MINC|PINC|CIRC|EN|SW|SWS|PLLM|PLLN|PLLP|HSEON|HSERDY|PLLON|PLLRDY)\b", str(text)))
        return terms[:20]

    def extract_register_table_hints(self, text: str) -> List[str]:
        """Extract compact hints from PDF table rows that mention registers, offsets, or reset values."""
        hints: List[str] = []
        for line in str(text).splitlines():
            normalized = re.sub(r"\s+", " ", line).strip()
            if not normalized:
                continue
            has_register = re.search(r"\b(?:CR1|CR2|CR3|SR|DR|BRR|GTPR|RTOR|RQR|ISR|ICR|RDR|TDR|AHB1ENR|APB1ENR|APB2ENR|MODER|AFRL|AFRH|SxCR|SxNDTR|SxPAR|SxM0AR)\b", normalized)
            has_address = re.search(r"\b0x[0-9A-Fa-f]{2,8}\b|\boffset\b|\breset\b", normalized, re.IGNORECASE)
            if has_register and has_address:
                hints.append(compact_text(normalized, 220))
        return self.dedupe_preserve_order(hints)[:24]

    def extract_register_schema_entries(self, text: str, document_path: str, page: int, section_title: str = "") -> List[Dict]:
        """Extract register-map schema entries with page citations from page/table text."""
        entries: List[Dict] = []
        peripheral = self.infer_peripheral_from_text(" ".join([section_title, text[:1200]]))
        lines = [re.sub(r"\s+", " ", line).strip() for line in str(text).splitlines()]
        for index, line in enumerate(lines):
            if not line:
                continue
            offset_match = re.search(r"\b(?:offset|address offset)?\s*[:=]?\s*(0x[0-9A-Fa-f]{1,8})\b", line, re.IGNORECASE)
            if not offset_match:
                offset_match = re.search(r"\b(0x[0-9A-Fa-f]{1,8})\b", line)
            if not offset_match:
                continue
            register = self.extract_register_name_from_line(line, peripheral)
            if not register:
                continue
            context = " ".join(part for part in lines[max(0, index - 1): index + 2] if part)
            entry = {
                "peripheral": peripheral or self.infer_peripheral_from_register(register),
                "register": register,
                "offset": offset_match.group(1).lower(),
                "reset": self.extract_reset_value(context),
                "access": self.extract_access_type(context),
                "bitfields": self.extract_bitfield_terms_from_text(context)[:16],
                "citation": {
                    "document": document_path,
                    "page": page,
                    "section": section_title,
                    "excerpt": compact_text(context, 260),
                },
            }
            entries.append(entry)
        return self.dedupe_register_schema_entries(entries)[:32]

    def extract_register_schema_entries_from_layout_tables(self, tables: List[Dict], document_path: str, page: int, section_title: str = "") -> List[Dict]:
        """Extract register schema from layout table cells before regex fallback."""
        entries: List[Dict] = []
        peripheral = self.infer_peripheral_from_text(section_title)
        for table in tables:
            headers = [str(header).strip().lower() for header in table.get("headers", [])]
            header_text = " ".join(headers)
            if not ("register" in header_text and ("offset" in header_text or "address" in header_text)):
                continue
            row_count = int(table.get("extraction_quality", {}).get("row_count", len(table.get("rows", []))) or 0)
            for body_row_index in range(1, row_count + 1):
                row_cells = [
                    cell for cell in table.get("cells", [])
                    if int(cell.get("row_index", -1)) == body_row_index
                ]
                row_map = self.layout_row_map(row_cells)
                evidence = " | ".join(str(cell.get("text", "")).strip() for cell in row_cells if str(cell.get("text", "")).strip())
                name = self.first_layout_value(row_map, ("register", "name"))
                offset_text = self.first_layout_value(row_map, ("offset", "address"))
                offset_match = re.search(r"0x[0-9A-Fa-f]{1,8}", offset_text)
                if not name or not offset_match:
                    continue
                register = self.extract_register_name_from_line(name, peripheral) or name.strip().upper()
                citation = self.layout_citation(document_path, page, section_title, table, row_cells, evidence, ("register", "name"))
                entry = {
                    "peripheral": peripheral or self.infer_peripheral_from_register(register),
                    "register": register,
                    "offset": offset_match.group(0).lower(),
                    "reset": self.first_layout_value(row_map, ("reset", "reset value")).lower(),
                    "access": self.normalize_access(self.first_layout_value(row_map, ("access", "type"))),
                    "bitfields": [],
                    "citation": citation,
                    "extraction_method": "layout_table",
                    "confidence": table.get("extraction_quality", {}).get("confidence", 0.9),
                }
                bit_name = self.first_layout_value(row_map, ("bitfield", "field", "bits name"))
                bits = self.first_layout_value(row_map, ("bits", "bit", "position"))
                if bit_name or bits:
                    bit_citation = self.layout_citation(document_path, page, section_title, table, row_cells, evidence, ("field", "bitfield", "bits", "bit"))
                    entry["bitfields"].append({
                        "name": bit_name.strip().upper(),
                        "bits": bits.strip(),
                        "access": entry["access"],
                        "reset": entry["reset"],
                        "citation": bit_citation,
                        "cell_bbox": bit_citation.get("cell_bbox", []),
                    })
                entries.append(entry)
        return self.dedupe_register_schema_entries(entries)[:32]

    def layout_row_map(self, row_cells: List[Dict]) -> Dict[str, Dict]:
        row_map: Dict[str, Dict] = {}
        for cell in row_cells:
            column_name = str(cell.get("column_name", "")).strip().lower()
            if column_name:
                row_map[column_name] = cell
        return row_map

    def first_layout_value(self, row_map: Dict[str, Dict], keys) -> str:
        for key in keys:
            for existing_key, cell in row_map.items():
                if key == existing_key or key in existing_key:
                    return str(cell.get("text", "")).strip()
        return ""

    def layout_citation(self, document_path: str, page: int, section_title: str, table: Dict, row_cells: List[Dict], evidence: str, preferred_columns=None) -> Dict:
        row_boxes = [cell.get("cell_bbox", []) for cell in row_cells if cell.get("cell_bbox")]
        preferred = tuple(str(item).lower() for item in (preferred_columns or ()))
        primary_cell = self.preferred_layout_cell(row_cells, preferred)
        if not primary_cell:
            primary_cell = next((cell for cell in row_cells if cell.get("cell_bbox")), row_cells[0] if row_cells else {})
        return {
            "document": document_path,
            "page": page,
            "section": section_title,
            "excerpt": compact_text(evidence, 260),
            "table_id": table.get("table_id", ""),
            "table_bbox": table.get("table_bbox", []),
            "row_index": primary_cell.get("row_index"),
            "row_bbox": self.union_bbox(row_boxes),
            "column_index": primary_cell.get("column_index"),
            "column_name": primary_cell.get("column_name", ""),
            "cell_bbox": primary_cell.get("cell_bbox", []),
            "extraction_method": "layout_table",
            "confidence": table.get("extraction_quality", {}).get("confidence", 0.9),
        }

    def preferred_layout_cell(self, row_cells: List[Dict], preferred_columns) -> Dict:
        for wanted in preferred_columns:
            for cell in row_cells:
                column = str(cell.get("column_name", "")).strip().lower()
                if wanted == column or wanted in column or column in wanted:
                    return cell
        return {}

    def normalize_access(self, text: str) -> str:
        value = str(text or "").strip().lower()
        aliases = {
            "read/write": "read/write",
            "r/w": "read/write",
            "rw": "read/write",
            "read-only": "read-only",
            "ro": "read-only",
            "write-only": "write-only",
            "wo": "write-only",
        }
        return aliases.get(value, value)

    def extract_register_name_from_line(self, line: str, peripheral: str = "") -> str:
        prefixed = re.search(r"\b((?:RCC|GPIO[A-Ix]?|USART[1-6x]?|UART[1-8x]?|DMA[12x]?|TIM(?:\d+|x)?|NVIC|EXTI|SYSCFG|FLASH|PWR)_[A-Z0-9]+)\b", line)
        if prefixed:
            return prefixed.group(1)
        generic = re.search(r"\b(CR1|CR2|CR3|SR|DR|BRR|GTPR|RTOR|RQR|ISR|ICR|RDR|TDR|AHB1ENR|APB1ENR|APB2ENR|MODER|OTYPER|OSPEEDR|PUPDR|AFRL|AFRH|SxCR|SxNDTR|SxPAR|SxM0AR)\b", line)
        if not generic:
            return ""
        register = generic.group(1)
        if peripheral and "_" not in register:
            return f"{peripheral}_{register}"
        return register

    def infer_peripheral_from_text(self, text: str) -> str:
        upper = str(text).upper()
        for token in ("USART", "UART", "RCC", "GPIO", "DMA", "TIM", "FLASH", "PWR", "EXTI", "SYSCFG"):
            if re.search(rf"\b{token}\b|\b{token}\d+\b", upper):
                return token
        return ""

    def infer_peripheral_from_register(self, register: str) -> str:
        if "_" in register:
            return register.split("_", 1)[0]
        return ""

    def extract_reset_value(self, text: str) -> str:
        match = re.search(r"\breset(?:\s+value)?\s*[:=]?\s*(0x[0-9A-Fa-f]+|\d+h)\b", text, re.IGNORECASE)
        return match.group(1).lower() if match else ""

    def extract_access_type(self, text: str) -> str:
        match = re.search(r"\b(read/write|read-only|write-only|rw|r/w|ro|wo)\b", text, re.IGNORECASE)
        return self.normalize_access(match.group(1)) if match else ""

    def dedupe_register_schema_entries(self, entries: List[Dict]) -> List[Dict]:
        deduped: List[Dict] = []
        seen = set()
        for entry in entries:
            citation = entry.get("citation", {}) if isinstance(entry.get("citation", {}), dict) else {}
            key = (
                str(entry.get("peripheral", "")).upper(),
                str(entry.get("register", "")).upper(),
                str(entry.get("offset", "")).lower(),
                str(citation.get("document", "")),
                int(citation.get("page", 0) or 0),
            )
            if not key[1] or key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped

    def write_register_schema(self) -> None:
        schema_path = (self.file_tools.workspace_root / RAG_REGISTER_SCHEMA_FILE).resolve()
        entries = self.dedupe_register_schema_entries(self._register_schema_entries)
        payload = {
            "schema_version": RAG_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "entry_count": len(entries),
            "entries": entries,
        }
        try:
            schema_path.parent.mkdir(parents=True, exist_ok=True)
            schema_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to write register schema: %s", exc)

    def index_rm_schema(
        self,
        pdf_path: Path,
        chip: str = "",
        max_pages: int = 0,
        progress: Optional[Callable[[str], None]] = None,
    ) -> Dict:
        """Build a register schema directly from one reference-manual PDF."""
        resolved_pdf = Path(pdf_path).resolve()
        if not resolved_pdf.exists():
            raise FileNotFoundError(f"Reference manual PDF not found: {resolved_pdf}")
        if resolved_pdf.suffix.lower() != ".pdf":
            raise ValueError(f"Reference manual input must be a PDF: {resolved_pdf}")

        emit = progress or (lambda message: None)
        emit(f"extracting pages from {resolved_pdf.name}")
        page_texts = self.extract_pdf_structured_pages(resolved_pdf)
        if not page_texts and PdfReader is not None:
            reader = PdfReader(str(resolved_pdf))
            page_texts = [self.extract_pdf_page_text_with_fallback(reader.pages[index]) for index in range(len(reader.pages))]
        if max_pages > 0:
            page_texts = page_texts[:max_pages]

        toc_entries = self.extract_pdf_toc_entries(resolved_pdf, page_texts)
        layout_tables_by_page = self.extract_pdf_layout_tables(resolved_pdf)
        entries: List[Dict] = []
        for page_index, text in enumerate(page_texts, start=1):
            if not str(text).strip():
                continue
            section_title = self.infer_pdf_page_section_title(text)
            toc_match = self.match_page_to_toc_entry(page_index, toc_entries)
            if not section_title and toc_match:
                section_title = str(toc_match.get("title", ""))
            layout_entries = self.extract_register_schema_entries_from_layout_tables(
                layout_tables_by_page.get(page_index, []),
                resolved_pdf.name,
                page_index,
                section_title,
            )
            text_entries = self.extract_register_schema_entries(text, resolved_pdf.name, page_index, section_title)
            page_entries = self.dedupe_register_schema_entries(layout_entries + text_entries)
            if chip:
                for entry in page_entries:
                    entry["chip"] = chip.upper()
            entries.extend(page_entries)
            if page_index == 1 or page_index % 25 == 0 or page_index == len(page_texts):
                emit(f"indexed page {page_index}/{len(page_texts)} entries={len(entries)}")

        deduped = self.dedupe_register_schema_entries(entries)
        payload = {
            "schema_version": RAG_SCHEMA_VERSION,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_pdf": str(resolved_pdf),
            "chip": chip.upper(),
            "page_count": len(page_texts),
            "entry_count": len(deduped),
            "entries": deduped,
        }
        schema_path = (self.file_tools.workspace_root / RAG_REGISTER_SCHEMA_FILE).resolve()
        schema_path.parent.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        emit(f"wrote {schema_path} entries={len(deduped)}")
        return payload

    def validate_register_schema(self, schema: Optional[Dict] = None) -> Dict:
        """Validate register schema consistency beyond JSON shape."""
        payload = schema if isinstance(schema, dict) else self.load_register_schema()
        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        findings: List[Dict] = []
        seen_offsets: Dict[tuple, str] = {}
        seen_registers = set()

        if not isinstance(entries, list):
            findings.append({"severity": "error", "message": "entries must be a list"})
            entries = []

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                findings.append({"severity": "error", "entry": index, "message": "entry must be an object"})
                continue
            register = str(entry.get("register", "")).strip()
            peripheral = str(entry.get("peripheral", "")).strip()
            offset = str(entry.get("offset", "")).strip()
            reset = str(entry.get("reset", "")).strip()
            access = str(entry.get("access", "")).strip()
            bitfields = entry.get("bitfields", [])
            citation = entry.get("citation", {}) if isinstance(entry.get("citation", {}), dict) else {}

            if not peripheral:
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "missing peripheral"})
            if not register:
                findings.append({"severity": "error", "entry": index, "message": "missing register"})
            if offset and not re.fullmatch(r"0x[0-9a-fA-F]{1,8}", offset):
                findings.append({"severity": "error", "entry": index, "register": register, "message": f"invalid offset: {offset}"})
            if not offset:
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "missing offset"})
            if not reset:
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "missing reset value"})
            if not access:
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "missing access type"})
            if not isinstance(bitfields, list):
                findings.append({"severity": "error", "entry": index, "register": register, "message": "bitfields must be a list"})
            if not citation.get("document"):
                findings.append({"severity": "error", "entry": index, "register": register, "message": "missing citation document"})
            try:
                page = int(citation.get("page", 0) or 0)
            except Exception:
                page = 0
            if page <= 0:
                findings.append({"severity": "error", "entry": index, "register": register, "message": "missing or invalid citation page"})
            extraction_method = str(entry.get("extraction_method", "") or citation.get("extraction_method", "")).strip().lower()
            if extraction_method != "layout_table":
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "register extracted from non-layout fallback"})
            if extraction_method == "layout_table" and not citation.get("cell_bbox"):
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "layout table citation missing cell_bbox"})
            if isinstance(bitfields, list):
                for bit_index, bitfield in enumerate(bitfields):
                    if not isinstance(bitfield, dict):
                        continue
                    if not str(bitfield.get("bits", "")).strip():
                        findings.append({"severity": "warning", "entry": index, "register": register, "bitfield": bit_index, "message": "bitfield missing bits"})
                    if not str(bitfield.get("access", "")).strip():
                        findings.append({"severity": "warning", "entry": index, "register": register, "bitfield": bit_index, "message": "bitfield missing access"})
                    bit_citation = bitfield.get("citation", {}) if isinstance(bitfield.get("citation", {}), dict) else {}
                    if not bit_citation.get("cell_bbox") and not bitfield.get("cell_bbox"):
                        findings.append({"severity": "warning", "entry": index, "register": register, "bitfield": bit_index, "message": "bitfield missing cell citation"})

            key = (peripheral.upper(), offset.lower())
            if peripheral and offset:
                previous = seen_offsets.get(key)
                if previous and previous != register:
                    findings.append({"severity": "error", "entry": index, "register": register, "message": f"duplicate offset {offset} conflicts with {previous}"})
                else:
                    seen_offsets[key] = register
            reg_key = (peripheral.upper(), register.upper())
            if register and reg_key in seen_registers:
                findings.append({"severity": "warning", "entry": index, "register": register, "message": "duplicate register entry"})
            seen_registers.add(reg_key)

        errors = sum(1 for item in findings if item.get("severity") == "error")
        warnings = sum(1 for item in findings if item.get("severity") == "warning")
        return {
            "valid": errors == 0,
            "errors": errors,
            "warnings": warnings,
            "entry_count": len(entries),
            "findings": findings,
        }

    def load_register_schema(self) -> Dict:
        schema_path = (self.file_tools.workspace_root / RAG_REGISTER_SCHEMA_FILE).resolve()
        if not schema_path.exists():
            return {"schema_version": RAG_SCHEMA_VERSION, "entries": []}
        try:
            payload = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"schema_version": RAG_SCHEMA_VERSION, "entries": []}
        return payload if isinstance(payload, dict) else {"schema_version": RAG_SCHEMA_VERSION, "entries": []}

    def resolve_workspace_document_path(self, filename: str) -> Optional[Path]:
        name = Path(filename).name.strip()
        if not name:
            return None
        for root in WORKSPACE_DOC_ROOTS:
            root_path = (self.file_tools.workspace_root / Path(root)).resolve()
            if not root_path.exists() or not root_path.is_dir():
                continue
            matches = list(root_path.rglob(name))
            if matches:
                return matches[0]
        return None

    def should_skip_workspace_indexing(self, file_path: Path, normalized_path: str) -> bool:
        normalized = normalized_path.replace("\\", "/")
        normalized_lower = normalized.lower()
        vendor_markers = ("/vendor_archive/", "/driver/cmsis/", "/driver/chip/", "/cmsis/")
        if any(marker in normalized_lower for marker in vendor_markers):
            return True
        return self._is_vendor_managed_path(normalized) or self._is_vendor_managed_path(file_path.name)

    def should_semantically_index_kb_pdf(self, filename: str, title: str, summary: str, doc_type: str, topics: List[str], chapters: List[str], use_cases: List[str]) -> bool:
        return True

    def should_semantically_index_workspace_pdf(self, normalized_path: str) -> bool:
        return True

    def should_prune_workspace_dir(self, dir_path: Path) -> bool:
        normalized = dir_path.as_posix().lower()
        if "/vendor_archive" in normalized or "/ide_archive" in normalized:
            return True
        return normalized.endswith("/driver/cmsis") or normalized.endswith("/driver/chip")

    def infer_workspace_doc_type(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix in {".onnx", ".tflite", ".pt", ".pth", ".pb"}:
            return "ml_model"
        if suffix in {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".xml", ".ini", ".cfg", ".conf"}:
            return "text_document"
        if suffix in {".h", ".hpp", ".c", ".cpp", ".py"}:
            return "source_document"
        if suffix == ".pdf":
            return "pdf_document"
        return "workspace_asset"

    def make_pdf_chunk(self, key: str, filename: str, section: str, summary: str, text: str, metadata: Dict, source_type: str = "pdf") -> ChunkRecord:
        chunk_id = hashlib.sha1(f"{key}:{filename}:{section}:{text[:160]}".encode("utf-8")).hexdigest()[:16]
        return ChunkRecord(
            chunk_id=chunk_id,
            doc_id=str(key),
            path=filename,
            source_type=source_type,
            text=text,
            summary=summary,
            section=section,
            metadata=metadata,
        )

    def infer_chunk_source_type(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        if suffix in {".c", ".cpp", ".h", ".hpp", ".py"}:
            return "code"
        if suffix == ".pdf":
            return "pdf"
        return "text"

    def infer_pdf_doc_type(self, filename: str, title: str, summary: str) -> str:
        haystack = " ".join([filename, title, summary]).lower()
        if "reference manual" in haystack:
            return "reference_manual"
        if "datasheet" in haystack:
            return "datasheet"
        if "schematic" in haystack:
            return "schematic"
        if "application note" in haystack or "app note" in haystack:
            return "application_note"
        return "document"

    def dedupe_preserve_order(self, items: List[str]) -> List[str]:
        deduped: List[str] = []
        seen = set()
        for item in items:
            normalized = str(item).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _default_vendor_managed_path(self, path: str) -> bool:
        normalized = Path(path).as_posix()
        if any(part in normalized for part in VENDOR_PATH_PARTS):
            return True
        basename = Path(normalized).name
        return any(re.fullmatch(pattern, basename, re.IGNORECASE) for pattern in VENDOR_FILE_PATTERNS)

