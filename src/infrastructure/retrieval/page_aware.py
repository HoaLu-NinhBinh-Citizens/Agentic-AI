import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.infrastructure.models import RetrievalHit, RetrievalQuery

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None


class PageAwareRetrievalSupport:
    def __init__(self, agent):
        self.agent = agent

    def query_needs_page_chunks(self, query: RetrievalQuery) -> bool:
        return bool(
            query.entities.get("pages")
            or query.entities.get("section_terms")
            or query.entities.get("register_terms")
            or query.entities.get("bitfield_terms")
        )

    def augment_hits_with_direct_page_hits(self, query: RetrievalQuery, hits: List[RetrievalHit]) -> List[RetrievalHit]:
        requested_pages = [str(page).strip() for page in query.entities.get("pages", []) if str(page).strip()]
        if not requested_pages:
            return hits
        hit_pages = {str(hit.metadata.get("page", "")).strip() for hit in hits if isinstance(hit.metadata, dict)}
        missing_pages = [page for page in requested_pages if page and page not in hit_pages]
        if not missing_pages:
            return hits

        direct_hits: List[RetrievalHit] = []
        candidate_paths = self.resolve_candidate_pdf_paths(query, hits)
        for pdf_path in candidate_paths[:3]:
            direct_hits.extend(self.extract_direct_page_hits(pdf_path, missing_pages))

        if not direct_hits:
            return hits
        combined = hits + direct_hits
        reranked = self.agent.hybrid_retriever._rerank_hits(query, combined)
        deduped = self.agent.hybrid_retriever._dedupe_hits_by_path(reranked)
        return deduped[:query.top_k]

    def resolve_candidate_pdf_paths(self, query: RetrievalQuery, hits: List[RetrievalHit]) -> List[Path]:
        candidates: List[Path] = []
        seen = set()
        for hit in hits:
            path = self.agent._resolve_workspace_document_path(hit.path)
            if path and path.suffix.lower() == ".pdf" and str(path) not in seen:
                seen.add(str(path))
                candidates.append(path)
        for item in self.agent.reference_kb.query(query.raw_query, limit=max(query.top_k, 3)):
            path = self.agent._resolve_workspace_document_path(str(item.get("filename", "")))
            if path and path.suffix.lower() == ".pdf" and str(path) not in seen:
                seen.add(str(path))
                candidates.append(path)
        return candidates

    def extract_direct_page_hits(self, pdf_path: Path, requested_pages: List[str]) -> List[RetrievalHit]:
        try:
            page_texts = self.agent._extract_pdf_structured_pages(pdf_path)
            if not page_texts and PdfReader is not None:
                reader = PdfReader(str(pdf_path))
                page_texts = [self.agent._extract_pdf_page_text_with_fallback(reader.pages[index]) for index in range(len(reader.pages))]
        except Exception:
            return []

        if not page_texts:
            return []

        toc_entries = self.agent._extract_pdf_toc_entries(pdf_path, page_texts)
        hits: List[RetrievalHit] = []
        for page_text in requested_pages:
            try:
                page_number = int(page_text)
            except ValueError:
                continue
            if page_number <= 0 or page_number > len(page_texts):
                continue
            text = str(page_texts[page_number - 1]).strip()
            if len(text) < 40:
                continue
            section_title = self.agent._infer_pdf_page_section_title(text)
            toc_match = self.agent._match_page_to_toc_entry(page_number, toc_entries)
            metadata = {
                "section": f"page_{page_number}",
                "page": page_number,
                "section_title": section_title,
                "toc_section": toc_match.get("title", ""),
                "toc_level": toc_match.get("level", 0),
                "toc_page_anchor": toc_match.get("page", 0),
                "register_terms": self.agent._extract_register_terms_from_text(text)[:12],
                "bitfield_terms": self.agent._extract_bitfield_terms_from_text(text)[:12],
                "register_table_hints": self.agent.retrieval_ingestor.extract_register_table_hints(text)[:12],
                "register_schema_entries": self.agent.retrieval_ingestor.extract_register_schema_entries(text, pdf_path.name, page_number, section_title)[:8],
                "chunk_role": "pdf_page_direct",
                "doc_type": "reference_manual",
            }
            hits.append(RetrievalHit(
                chunk_id=f"direct::{pdf_path.name}::page::{page_number}",
                path=pdf_path.name,
                source_type="pdf",
                score=0.0,
                text=text,
                summary=f"Direct page {page_number} from {pdf_path.name}",
                metadata=metadata,
                score_breakdown={"source": "direct_page_extract"},
            ))
        return hits

    def build_retrieval_report(
        self,
        task: str,
        build_error: str = "",
        review_feedback: str = "",
        top_k: int = 5,
        allow_semantic: bool = True,
    ) -> Dict:
        query = self.agent.query_analyzer.analyze(task, build_error=build_error, review_feedback=review_feedback)
        self.agent._ensure_rag_ready(require_page_chunks=allow_semantic and self.query_needs_page_chunks(query))
        query.top_k = top_k
        hits = self.agent.search_docs(
            task,
            build_error=build_error,
            review_feedback=review_feedback,
            top_k=top_k,
            allow_semantic=allow_semantic,
        )
        return {
            "generated_at": datetime.now().isoformat(),
            "task": task,
            "query": {
                "raw_query": query.raw_query,
                "normalized_query": query.normalized_query,
                "intent": query.intent,
                "domain_profile": query.domain_profile,
                "entities": query.entities,
                "filters": query.filters,
                "top_k": query.top_k,
            },
            "hits": [self.retrieval_hit_to_report_entry(hit) for hit in hits],
        }

    def write_retrieval_report(
        self,
        report_path: Path,
        task: str,
        build_error: str = "",
        review_feedback: str = "",
        top_k: int = 5,
        allow_semantic: bool = True,
    ) -> Dict:
        report = self.build_retrieval_report(
            task,
            build_error=build_error,
            review_feedback=review_feedback,
            top_k=top_k,
            allow_semantic=allow_semantic,
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report

    def retrieval_hit_to_report_entry(self, hit: RetrievalHit) -> Dict:
        metadata = dict(hit.metadata) if isinstance(hit.metadata, dict) else {}
        return {
            "path": hit.path,
            "source_type": hit.source_type,
            "score": round(hit.score, 4),
            "lexical_score": round(hit.lexical_score, 4),
            "vector_score": round(hit.vector_score, 4),
            "rerank_score": round(hit.rerank_score, 4),
            "section": metadata.get("section", ""),
            "section_title": metadata.get("section_title", ""),
            "toc_section": metadata.get("toc_section", ""),
            "page": metadata.get("page", ""),
            "toc_level": metadata.get("toc_level", 0),
            "toc_page_anchor": metadata.get("toc_page_anchor", 0),
            "register_terms": metadata.get("register_terms", []),
            "bitfield_terms": metadata.get("bitfield_terms", []),
            "register_table_hints": metadata.get("register_table_hints", []),
            "register_schema_entries": metadata.get("register_schema_entries", []),
            "summary": hit.summary,
            "excerpt": " ".join(str(hit.text[:320]).split()),
            "score_breakdown": hit.score_breakdown,
            "metadata": metadata,
        }
