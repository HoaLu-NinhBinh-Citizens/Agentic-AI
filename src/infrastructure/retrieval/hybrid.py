import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.core.config.agent_prompts import GENERIC_QUERY_STOPWORDS, MIN_HIGH_CONFIDENCE_HITS, VECTOR_RERANK_CANDIDATES
from src.infrastructure.models import ChunkRecord, DomainProfile, RetrievalHit, RetrievalQuery

from .chunk_store import ChunkStore
from .knowledge_base import ReferenceKnowledgeBase
from .query_analyzer import QueryAnalyzer
from .vector_index import VectorIndex


class HybridRetriever:
    """Hybrid retriever: lexical scoring + semantic vector search + deterministic reranking."""

    def __init__(self, chunk_store: ChunkStore, reference_kb: ReferenceKnowledgeBase, vector_index: Optional[VectorIndex] = None):
        self.chunk_store = chunk_store
        self.reference_kb = reference_kb
        self.vector_index = vector_index

    def search_docs(self, query: RetrievalQuery, allow_semantic: bool = True) -> List[RetrievalHit]:
        lexical_hits = self._search_chunk_store(query)
        vector_scores = self._search_vector_index(query, lexical_hits) if allow_semantic else {}
        merged_hits = self._merge_hits(lexical_hits, vector_scores)
        kb_hits = self._search_reference_kb(query)
        if kb_hits:
            merged_hits.extend(kb_hits)
        reranked = self._rerank_hits(query, merged_hits)
        return self._dedupe_hits_by_path(reranked)[:query.top_k]

    def assess_confidence(self, hits: List[RetrievalHit]) -> str:
        if not hits:
            return "low"
        top_score = hits[0].score
        supporting_hits = [hit for hit in hits[:3] if hit.score >= 6]
        if top_score >= 11 and len(supporting_hits) >= MIN_HIGH_CONFIDENCE_HITS:
            return "high"
        if top_score >= 6:
            return "medium"
        return "low"

    def explain_confidence(self, hits: List[RetrievalHit]) -> str:
        if not hits:
            return "No lexical or semantic evidence was retrieved."
        top_hit = hits[0]
        if self.assess_confidence(hits) == "high":
            return f"Top evidence has strong combined lexical/semantic support (score={top_hit.score:.2f}) and is backed by multiple relevant hits."
        return f"Top evidence is only partially supported (score={top_hit.score:.2f}); coding should stop if refinement does not improve support."

    def _search_chunk_store(self, query: RetrievalQuery) -> List[RetrievalHit]:
        terms = self._build_query_terms(query)
        scored: List[RetrievalHit] = []
        profile = QueryAnalyzer.DOMAIN_PROFILES.get(query.domain_profile, QueryAnalyzer.DOMAIN_PROFILES["generic_document"])
        for chunk in self.chunk_store.get_all():
            if query.filters.get("source_type") and chunk.source_type != query.filters["source_type"]:
                continue
            section_name = str(chunk.section or "")
            core_haystack = " ".join([
                chunk.path,
                chunk.summary,
                section_name,
                chunk.text[:2500],
            ]).lower()
            haystack = " ".join([
                core_haystack,
                " ".join(str(value) for value in chunk.metadata.values()),
            ]).lower()
            if not self._matches_domain_profile(query, profile, core_haystack):
                continue
            if self._mentions_other_stm32_family(query, core_haystack):
                continue
            if self._is_low_value_hardware_doc(query, chunk.path.lower(), core_haystack):
                continue
            score = 0.0
            breakdown = {
                "source": "lexical",
                "matched_terms": [],
                "chip_hits": [],
                "peripheral_hits": [],
                "metadata": {},
            }
            term_haystack = core_haystack if query.filters.get("domain") == "stm32_embedded" else haystack
            peripheral_terms = [term.lower() for term in query.entities.get("peripherals", [])]
            matched_peripherals = [term for term in peripheral_terms if term in core_haystack]
            if peripheral_terms and not matched_peripherals and chunk.source_type == "code":
                continue
            for term in terms:
                if term in term_haystack:
                    score += 2.0
                    breakdown["matched_terms"].append(term)
            for chip in query.entities.get("chips", []):
                if chip.lower() in core_haystack:
                    score += 4.0
                    breakdown["chip_hits"].append(chip)
            for peripheral in query.entities.get("peripherals", []):
                if peripheral.lower() in core_haystack:
                    score += 3.0
                    breakdown["peripheral_hits"].append(peripheral)
            if peripheral_terms and not matched_peripherals:
                score -= 2.5
            domain_score = self._score_domain_relevance(query, profile, core_haystack, str(chunk.metadata.get("doc_type", "")))
            metadata_score, metadata_breakdown = self._score_metadata_overlap(query, chunk.path, section_name, chunk.metadata)
            score += domain_score
            score += metadata_score
            breakdown["domain_score"] = domain_score
            breakdown["metadata"] = metadata_breakdown
            if score <= 0:
                continue
            scored.append(RetrievalHit(
                chunk_id=chunk.chunk_id,
                path=chunk.path,
                source_type=chunk.source_type,
                score=score,
                text=chunk.text,
                summary=chunk.summary,
                lexical_score=score,
                score_breakdown=breakdown,
                metadata=dict(chunk.metadata),
            ))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored

    def _search_vector_index(self, query: RetrievalQuery, lexical_hits: List[RetrievalHit]) -> Dict[str, float]:
        if not self.vector_index:
            return {}
        chunk_map = {chunk.chunk_id: chunk for chunk in self.chunk_store.get_all()}
        candidates: List[ChunkRecord] = []
        profile = QueryAnalyzer.DOMAIN_PROFILES.get(query.domain_profile, QueryAnalyzer.DOMAIN_PROFILES["generic_document"])
        for chunk in self.chunk_store.get_all():
            if query.filters.get("source_type") and chunk.source_type != query.filters["source_type"]:
                continue
            section_name = str(chunk.section or "")
            core_haystack = " ".join([
                chunk.path,
                chunk.summary,
                section_name,
                chunk.text[:2500],
            ]).lower()
            if not self._matches_domain_profile(query, profile, core_haystack):
                continue
            if self._mentions_other_stm32_family(query, core_haystack):
                continue
            if self._is_low_value_hardware_doc(query, chunk.path.lower(), core_haystack):
                continue
            candidates.append(chunk)
        if not candidates or not self.vector_index.ensure_for_chunks(candidates):
            return {}
        vector_scores = self.vector_index.search(query.raw_query, top_k=max(query.top_k * 4, VECTOR_RERANK_CANDIDATES))
        if not vector_scores:
            return {}
        allowed_ids = {chunk.chunk_id for chunk in candidates}
        lexical_ids = {hit.chunk_id for hit in lexical_hits[:VECTOR_RERANK_CANDIDATES]}
        filtered_scores = {
            chunk_id: score
            for chunk_id, score in vector_scores.items()
            if chunk_id in allowed_ids and (chunk_id in lexical_ids or score > 0.45)
        }
        if filtered_scores:
            return filtered_scores
        lexical_candidates = [chunk_map[hit.chunk_id] for hit in lexical_hits[:VECTOR_RERANK_CANDIDATES] if hit.chunk_id in chunk_map]
        if not lexical_candidates:
            return {}
        return self.vector_index.score_candidates(query.raw_query, lexical_candidates, top_k=max(query.top_k * 3, 6))

    def _merge_hits(self, lexical_hits: List[RetrievalHit], vector_scores: Dict[str, float]) -> List[RetrievalHit]:
        lexical_by_id = {hit.chunk_id: hit for hit in lexical_hits}
        merged: List[RetrievalHit] = []
        chunk_map = {chunk.chunk_id: chunk for chunk in self.chunk_store.get_all()}

        for chunk_id, hit in lexical_by_id.items():
            vector_score = float(vector_scores.get(chunk_id, 0.0))
            merged.append(RetrievalHit(
                chunk_id=hit.chunk_id,
                path=hit.path,
                source_type=hit.source_type,
                score=(hit.lexical_score * 0.65) + (vector_score * 8.0),
                text=hit.text,
                summary=hit.summary,
                lexical_score=hit.lexical_score,
                vector_score=vector_score,
                score_breakdown={**dict(hit.score_breakdown), "merge": {"lexical_weighted": hit.lexical_score * 0.65, "semantic_weighted": vector_score * 8.0}},
                metadata=dict(hit.metadata),
            ))

        for chunk_id, vector_score in vector_scores.items():
            if chunk_id in lexical_by_id:
                continue
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue
            merged.append(RetrievalHit(
                chunk_id=chunk.chunk_id,
                path=chunk.path,
                source_type=chunk.source_type,
                score=vector_score * 8.0,
                text=chunk.text,
                summary=chunk.summary,
                vector_score=vector_score,
                score_breakdown={"source": "semantic_only", "merge": {"semantic_weighted": vector_score * 8.0}},
                metadata=dict(chunk.metadata),
            ))

        merged.sort(key=lambda item: item.score, reverse=True)
        return merged[:VECTOR_RERANK_CANDIDATES]

    def _rerank_hits(self, query: RetrievalQuery, hits: List[RetrievalHit]) -> List[RetrievalHit]:
        reranked: List[RetrievalHit] = []
        query_terms = self._build_query_terms(query)
        for hit in hits:
            haystack = " ".join([
                hit.path,
                hit.summary,
            str(hit.metadata.get("section", "") if isinstance(hit.metadata, dict) else ""),
            str(hit.metadata.get("section_title", "") if isinstance(hit.metadata, dict) else ""),
            str(hit.metadata.get("register_table_hints", "") if isinstance(hit.metadata, dict) else ""),
            hit.text[:1600],
        ]).lower()
            doc_type = str(hit.metadata.get("doc_type", "") if isinstance(hit.metadata, dict) else "").strip().lower()
            coverage = sum(1 for term in query_terms if term in haystack)
            chip_bonus = sum(1.5 for chip in query.entities.get("chips", []) if chip.lower() in haystack)
            peripheral_bonus = sum(1.0 for peripheral in query.entities.get("peripherals", []) if peripheral.lower() in haystack)
            exact_path_bonus = 1.5 if any(term in Path(hit.path).name.lower() for term in query_terms[:4]) else 0.0
            semantic_bonus = hit.vector_score * 4.0
            lexical_bonus = hit.lexical_score * 0.35
            evidence_quality_bonus, evidence_quality_breakdown = self._score_evidence_quality(query, hit)
            rerank_score = lexical_bonus + semantic_bonus + float(coverage) + chip_bonus + peripheral_bonus + exact_path_bonus + evidence_quality_bonus
            rerank_breakdown = {
                "lexical_bonus": lexical_bonus,
                "semantic_bonus": semantic_bonus,
                "coverage": float(coverage),
                "chip_bonus": chip_bonus,
                "peripheral_bonus": peripheral_bonus,
                "exact_path_bonus": exact_path_bonus,
                "evidence_quality_bonus": evidence_quality_bonus,
                "evidence_quality": evidence_quality_breakdown,
                "page_bonus": 0.0,
                "section_bonus": 0.0,
                "register_bonus": 0.0,
                "bitfield_bonus": 0.0,
            }
            page_value = str(hit.metadata.get("page", "") if isinstance(hit.metadata, dict) else "").strip()
            if page_value and any(page == page_value for page in query.entities.get("pages", [])):
                rerank_score += 10.0
                rerank_breakdown["page_bonus"] += 10.0
            section_text = " ".join([
                str(hit.metadata.get("section", "") if isinstance(hit.metadata, dict) else ""),
                str(hit.metadata.get("section_title", "") if isinstance(hit.metadata, dict) else ""),
                str(hit.metadata.get("toc_section", "") if isinstance(hit.metadata, dict) else ""),
            ]).lower()
            for term in query.entities.get("section_terms", []):
                normalized = str(term).strip().lower()
                if normalized and normalized in section_text:
                    rerank_score += 4.0
                    rerank_breakdown["section_bonus"] += 4.0
            for term in query.entities.get("register_terms", []):
                normalized = str(term).strip().lower()
                if normalized and normalized in haystack:
                    rerank_score += 3.0
                    rerank_breakdown["register_bonus"] += 3.0
            for term in query.entities.get("bitfield_terms", []):
                normalized = str(term).strip().lower()
                if normalized and normalized in haystack:
                    rerank_score += 2.0
                    rerank_breakdown["bitfield_bonus"] += 2.0
            if query.intent in {"codegen", "repair_codegen"}:
                if hit.source_type == "pdf" or doc_type in {"reference_manual", "datasheet", "application_note"}:
                    rerank_score += 3.0
                    rerank_breakdown["doc_type_bonus"] = 3.0
                elif hit.source_type == "code":
                    rerank_score -= 4.0
                    rerank_breakdown["doc_type_bonus"] = -4.0
            if query.entities.get("peripherals") and peripheral_bonus == 0:
                rerank_score -= 3.0
                rerank_breakdown["peripheral_penalty"] = -3.0
            if hit.vector_score > 0 and hit.lexical_score == 0 and coverage == 0:
                rerank_score -= 1.0
                rerank_breakdown["semantic_only_penalty"] = -1.0
            reranked.append(RetrievalHit(
                chunk_id=hit.chunk_id,
                path=hit.path,
                source_type=hit.source_type,
                score=rerank_score,
                text=hit.text,
                summary=hit.summary,
                lexical_score=hit.lexical_score,
                vector_score=hit.vector_score,
                rerank_score=rerank_score,
                score_breakdown={**dict(hit.score_breakdown), "rerank": rerank_breakdown},
                metadata=dict(hit.metadata),
            ))
        reranked.sort(key=lambda item: item.score, reverse=True)
        return reranked

    def _score_evidence_quality(self, query: RetrievalQuery, hit: RetrievalHit) -> Tuple[float, Dict]:
        metadata = hit.metadata if isinstance(hit.metadata, dict) else {}
        bonus = 0.0
        breakdown: Dict[str, object] = {
            "citation_bonus": 0.0,
            "table_bonus": 0.0,
            "layout_table_bonus": 0.0,
            "cell_bbox_bonus": 0.0,
            "register_schema_bonus": 0.0,
            "confidence_bonus": 0.0,
            "ocr_penalty": 0.0,
        }

        page = str(metadata.get("page", "") or metadata.get("page_number", "")).strip()
        if page:
            bonus += 1.0
            breakdown["citation_bonus"] = 1.0
        table_hints = metadata.get("register_table_hints", [])
        if isinstance(table_hints, list) and table_hints:
            table_bonus = 2.5 if query.intent in {"codegen", "repair_codegen", "fix_build"} else 1.0
            bonus += table_bonus
            breakdown["table_bonus"] = table_bonus
        schema_entries = metadata.get("register_schema_entries", [])
        if isinstance(schema_entries, list) and schema_entries:
            register_terms = [str(item).lower() for item in query.entities.get("register_terms", [])]
            schema_text = " ".join(jsonish for jsonish in [str(schema_entries)]).lower()
            exact_matches = sum(1 for term in register_terms if term and term in schema_text)
            layout_entries = [
                item for item in schema_entries
                if isinstance(item, dict)
                and (
                    str(item.get("extraction_method", "")).lower() == "layout_table"
                    or str(item.get("citation", {}).get("extraction_method", "") if isinstance(item.get("citation", {}), dict) else "").lower() == "layout_table"
                )
            ]
            cell_cited_entries = [
                item for item in schema_entries
                if isinstance(item, dict)
                and isinstance(item.get("citation", {}), dict)
                and item.get("citation", {}).get("cell_bbox")
            ]
            schema_bonus = 3.0 + exact_matches * 2.0 + len(layout_entries) * 2.0 + len(cell_cited_entries) * 1.5
            bonus += schema_bonus
            breakdown["register_schema_bonus"] = schema_bonus
            breakdown["register_schema_exact_matches"] = exact_matches
            breakdown["layout_schema_entries"] = len(layout_entries)
            breakdown["cell_cited_schema_entries"] = len(cell_cited_entries)
        layout_tables = metadata.get("layout_tables", [])
        if isinstance(layout_tables, list) and layout_tables:
            layout_bonus = 2.0 if any(table.get("table_bbox") for table in layout_tables if isinstance(table, dict)) else 1.0
            bonus += layout_bonus
            breakdown["layout_table_bonus"] = layout_bonus
        if self.metadata_has_cell_bbox(metadata):
            bonus += 1.5
            breakdown["cell_bbox_bonus"] = 1.5
        field_citations = metadata.get("field_citations", {})
        if isinstance(field_citations, dict):
            confidences = []
            for citations in field_citations.values():
                if isinstance(citations, list):
                    for citation in citations:
                        if isinstance(citation, dict):
                            try:
                                confidences.append(float(citation.get("confidence", 0.0) or 0.0))
                            except Exception:
                                pass
            if confidences:
                confidence_bonus = min(sum(confidences) / len(confidences), 1.0) * 1.5
                bonus += confidence_bonus
                breakdown["confidence_bonus"] = round(confidence_bonus, 3)
        extraction_method = str(metadata.get("extraction_method", "")).lower()
        if extraction_method == "ocr":
            bonus -= 1.0
            breakdown["ocr_penalty"] = -1.0
        return bonus, breakdown

    def metadata_has_cell_bbox(self, metadata: Dict) -> bool:
        for key in ("register_schema_entries", "field_citations"):
            value = metadata.get(key)
            if self.value_has_cell_bbox(value):
                return True
        return False

    def value_has_cell_bbox(self, value) -> bool:
        if isinstance(value, dict):
            if value.get("cell_bbox"):
                return True
            return any(self.value_has_cell_bbox(item) for item in value.values())
        if isinstance(value, list):
            return any(self.value_has_cell_bbox(item) for item in value)
        return False

    def _search_reference_kb(self, query: RetrievalQuery) -> List[RetrievalHit]:
        hits: List[RetrievalHit] = []
        profile = QueryAnalyzer.DOMAIN_PROFILES.get(query.domain_profile, QueryAnalyzer.DOMAIN_PROFILES["generic_document"])
        for index, item in enumerate(self.reference_kb.query(query.raw_query, limit=query.top_k), start=1):
            text = "\n".join(part for part in [item.get("summary", ""), item.get("preview", "")] if part).strip()
            core_haystack = " ".join([
                item.get("filename", ""),
                item.get("summary", ""),
                text,
            ]).lower()
            haystack = " ".join([
                core_haystack,
                item.get("topics", ""),
                item.get("chapters", ""),
                item.get("use_cases", ""),
            ]).lower()
            if not self._matches_domain_profile(query, profile, core_haystack):
                continue
            if self._mentions_other_stm32_family(query, core_haystack):
                continue
            if self._is_low_value_hardware_doc(query, str(item.get("filename", "")).lower(), core_haystack):
                continue
            score = float(max(query.top_k - index + 1, 1)) + self._score_domain_relevance(query, profile, core_haystack, "")
            metadata_score, metadata_breakdown = self._score_metadata_overlap(
                query,
                str(item.get("filename", "")),
                " ".join([
                    str(item.get("chapters", "")),
                    str(item.get("topics", "")),
                    str(item.get("use_cases", "")),
                ]),
                {
                    "topics": item.get("topics", ""),
                    "chapters": item.get("chapters", ""),
                    "use_cases": item.get("use_cases", ""),
                },
            )
            score += metadata_score
            hits.append(RetrievalHit(
                chunk_id=f"kb::{item.get('id', index)}",
                path=item.get("filename", item.get("id", "reference")),
                source_type="pdf",
                score=score,
                text=text,
                summary=item.get("summary", ""),
                score_breakdown={"source": "reference_kb", "rank_index": index, "metadata": metadata_breakdown},
                metadata={
                    "topics": item.get("topics", ""),
                    "chapters": item.get("chapters", ""),
                    "use_cases": item.get("use_cases", ""),
                },
            ))
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[:query.top_k]

    def _matches_domain_profile(self, query: RetrievalQuery, profile: DomainProfile, haystack: str) -> bool:
        if profile.name == "generic_document":
            return True
        if any(token in haystack for token in query.entities.get("chips", [])):
            return True
        family_match = any(token in haystack for token in profile.family_tokens)
        peripheral_match = any(token.lower() in haystack for token in query.entities.get("peripherals", []))
        keyword_match_count = sum(1 for token in profile.keyword_markers if token in haystack)
        return family_match or (peripheral_match and keyword_match_count >= 1) or keyword_match_count >= 2

    def _score_domain_relevance(self, query: RetrievalQuery, profile: DomainProfile, haystack: str, doc_type: str) -> float:
        if profile.name == "generic_document":
            return 0.0
        score = 0.0
        if any(token in haystack for token in query.entities.get("chips", [])):
            score += 4.0
        score += sum(1.5 for token in profile.family_tokens if token in haystack)
        score += sum(1.0 for token in profile.keyword_markers if token in haystack)
        normalized_doc_type = str(doc_type).strip().lower()
        if normalized_doc_type and normalized_doc_type in profile.preferred_doc_types:
            score += 2.5
        if normalized_doc_type and normalized_doc_type in profile.avoid_doc_types:
            score -= 2.0
        return score

    def _mentions_other_stm32_family(self, query: RetrievalQuery, haystack: str) -> bool:
        chip_terms = [term.lower() for term in query.entities.get("chips", [])]
        if not chip_terms:
            return False
        if any(term in haystack for term in chip_terms):
            return False
        mentioned = re.findall(r"stm32[a-z0-9]+", haystack)
        return bool(mentioned)

    def _build_query_terms(self, query: RetrievalQuery) -> List[str]:
        terms = []
        seen = set()
        for token in query.entities.get("keywords", []) + query.normalized_query.split():
            normalized = str(token).strip().lower()
            if len(normalized) < 2 or normalized in GENERIC_QUERY_STOPWORDS or normalized in seen:
                continue
            seen.add(normalized)
            terms.append(normalized)
        return terms

    def _score_metadata_overlap(self, query: RetrievalQuery, path: str, section: str, metadata: Dict) -> Tuple[float, Dict]:
        query_terms = self._build_query_terms(query)
        if not query_terms:
            return 0.0, {}

        path_haystack = " ".join([path, Path(path).name]).lower()
        metadata_parts = [
            path,
            section,
            str(metadata.get("title", "")),
            " ".join(str(item) for item in metadata.get("topics", []) if str(item).strip()) if isinstance(metadata.get("topics", []), list) else str(metadata.get("topics", "")),
            " ".join(str(item) for item in metadata.get("chapters", []) if str(item).strip()) if isinstance(metadata.get("chapters", []), list) else str(metadata.get("chapters", "")),
            " ".join(str(item) for item in metadata.get("use_cases", []) if str(item).strip()) if isinstance(metadata.get("use_cases", []), list) else str(metadata.get("use_cases", "")),
            str(metadata.get("doc_type", "")),
            str(metadata.get("chunk_role", "")),
            " ".join(str(item) for item in metadata.get("register_table_hints", []) if str(item).strip()) if isinstance(metadata.get("register_table_hints", []), list) else str(metadata.get("register_table_hints", "")),
        ]
        haystack = " ".join(part for part in metadata_parts if part).lower()
        score = 0.0
        section_matches: List[str] = []
        breakdown: Dict[str, object] = {
            "matched_terms": [],
            "path_matches": [],
            "page_bonus": 0.0,
            "section_matches": section_matches,
            "register_matches": [],
            "bitfield_matches": [],
        }
        matched_terms = [term for term in query_terms if term in haystack]
        path_matches = [term for term in query_terms if term in path_haystack]
        score += float(len(matched_terms)) * 1.5
        score += float(len(path_matches)) * 3.0
        breakdown["matched_terms"] = matched_terms
        breakdown["path_matches"] = path_matches

        chunk_role = str(metadata.get("chunk_role", "")).strip().lower()
        generic_sections = ("document_overview", "overview", "introduction", "summary")
        if query.intent in {"codegen", "fix_build", "repair_codegen"} and chunk_role == "overview" and len(matched_terms) <= 1:
            score -= 2.0
            breakdown["overview_penalty"] = -2.0
        if any(marker in haystack for marker in generic_sections) and len(matched_terms) <= 1:
            score -= 1.0
            breakdown["generic_section_penalty"] = -1.0
        if chunk_role == "workspace_file" and path_matches:
            score += 2.0 + float(len(path_matches))
            breakdown["workspace_path_bonus"] = 2.0 + float(len(path_matches))

        for bucket_name in ("topics", "chapters", "use_cases"):
            values = metadata.get(bucket_name, [])
            if not isinstance(values, list):
                values = [values]
            for value in values:
                value_text = str(value).strip().lower()
                if not value_text:
                    continue
                overlap_count = sum(1 for term in query_terms if term in value_text)
                if overlap_count:
                    score += 1.0 + float(overlap_count)
                    bucket_matches = breakdown.setdefault(f"{bucket_name}_matches", [])
                    if isinstance(bucket_matches, list):
                        bucket_matches.append({"value": value_text, "overlap": overlap_count})

        page_value = str(metadata.get("page", "")).strip()
        if page_value and any(page == page_value for page in query.entities.get("pages", [])):
            score += 8.0
            breakdown["page_bonus"] = 8.0
        elif query.entities.get("pages") and str(metadata.get("chunk_role", "")).strip().lower().startswith("pdf_page"):
            score -= 1.5
            breakdown["page_penalty"] = -1.5

        section_text = " ".join([
            section,
            str(metadata.get("section_title", "")),
            str(metadata.get("title", "")),
            str(metadata.get("toc_section", "")),
        ]).lower()
        for term in query.entities.get("section_terms", []):
            normalized = str(term).strip().lower()
            if normalized and normalized in section_text:
                score += 4.0
                section_matches.append(normalized)

        register_terms = [str(item).strip().lower() for item in query.entities.get("register_terms", []) if str(item).strip()]
        bitfield_terms = [str(item).strip().lower() for item in query.entities.get("bitfield_terms", []) if str(item).strip()]
        if register_terms:
            register_haystack = " ".join([
                section_text,
                str(metadata.get("register_terms", "")),
                str(metadata.get("register_hints", "")),
                str(metadata.get("register_table_hints", "")),
            ]).lower()
            register_matches = [term for term in register_terms if term in register_haystack]
            score += float(len(register_matches)) * 3.0
            breakdown["register_matches"] = register_matches
        if bitfield_terms:
            bitfield_haystack = " ".join([
                section_text,
                str(metadata.get("bitfield_terms", "")),
                str(metadata.get("bitfield_hints", "")),
                str(metadata.get("register_table_hints", "")),
            ]).lower()
            bitfield_matches = [term for term in bitfield_terms if term in bitfield_haystack]
            score += float(len(bitfield_matches)) * 2.0
            breakdown["bitfield_matches"] = bitfield_matches
        return score, breakdown

    def _is_low_value_hardware_doc(self, query: RetrievalQuery, path: str, haystack: str) -> bool:
        if query.intent not in {"codegen", "fix_build", "repair_codegen"}:
            return False
        hardware_markers = ("schematic", "hardware datasheet", "hardware datasheets")
        if not any(marker in path or marker in haystack for marker in hardware_markers):
            return False
        firmware_markers = ("reference manual", "register", "bitfield", "uart", "usart", "irq", "dma", "nvic", "rcc", "brr", "cr1", "cr2", "cr3")
        return not any(marker in haystack for marker in firmware_markers)

    def _dedupe_hits_by_path(self, hits: List[RetrievalHit]) -> List[RetrievalHit]:
        deduped: List[RetrievalHit] = []
        seen_keys = set()
        for hit in hits:
            normalized_path = str(hit.path).strip().lower()
            section = str(hit.metadata.get("section", "") if isinstance(hit.metadata, dict) else "").strip().lower()
            normalized_key = (normalized_path, section)
            if not normalized_path or normalized_key in seen_keys:
                continue
            seen_keys.add(normalized_key)
            deduped.append(hit)
        return deduped

