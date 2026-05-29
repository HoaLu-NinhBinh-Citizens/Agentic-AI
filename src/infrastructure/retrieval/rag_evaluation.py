"""
RAG evaluation framework for measuring retrieval quality.

Provides:
- Ground-truth evaluation dataset management
- Recall and precision metrics
- Hit-rate, MRR (Mean Reciprocal Rank), and NDCG scoring
- Cross-validation of hybrid search weights
- Evaluation report generation
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class EvaluationCase:
    """A single retrieval evaluation case with ground truth."""

    def __init__(
        self,
        case_id: str,
        query: str,
        relevant_chunk_ids: List[str],
        relevant_paths: List[str],
        category: str = "general",
        difficulty: str = "medium",
        notes: str = "",
    ):
        self.case_id = case_id
        self.query = query
        self.relevant_chunk_ids = set(relevant_chunk_ids)
        self.relevant_paths = set(relevant_paths)
        self.category = category
        self.difficulty = difficulty
        self.notes = notes

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "relevant_chunk_ids": list(self.relevant_chunk_ids),
            "relevant_paths": list(self.relevant_paths),
            "category": self.category,
            "difficulty": self.difficulty,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EvaluationCase":
        return cls(
            case_id=str(d.get("case_id", "")),
            query=str(d.get("query", "")),
            relevant_chunk_ids=d.get("relevant_chunk_ids", []),
            relevant_paths=d.get("relevant_paths", []),
            category=str(d.get("category", "general")),
            difficulty=str(d.get("difficulty", "medium")),
            notes=str(d.get("notes", "")),
        )


class RetrievalMetrics:
    """Metrics for a single retrieval evaluation."""

    def __init__(
        self,
        query: str,
        case_id: str,
        retrieved_ids: List[str],
        retrieved_paths: List[str],
        relevant_ids: set,
        relevant_paths: set,
        k_values: List[int] = None,
    ):
        self.query = query
        self.case_id = case_id
        self.retrieved_ids = retrieved_ids
        self.retrieved_paths = retrieved_paths
        self.relevant_ids = relevant_ids
        self.relevant_paths = relevant_paths
        self.k_values = k_values or [1, 3, 5, 10]

    @property
    def precision_at_k(self) -> Dict[int, float]:
        result = {}
        for k in self.k_values:
            retrieved = set(self.retrieved_ids[:k])
            result[k] = len(retrieved & self.relevant_ids) / k if k > 0 else 0.0
        return result

    @property
    def recall_at_k(self) -> Dict[int, float]:
        result = {}
        for k in self.k_values:
            retrieved = set(self.retrieved_ids[:k])
            total_relevant = len(self.relevant_ids)
            result[k] = len(retrieved & self.relevant_ids) / total_relevant if total_relevant > 0 else 0.0
        return result

    @property
    def hit_at_k(self) -> Dict[int, bool]:
        result = {}
        for k in self.k_values:
            retrieved = set(self.retrieved_ids[:k])
            result[k] = bool(retrieved & self.relevant_ids)
        return result

    @property
    def mrr(self) -> float:
        """Mean Reciprocal Rank: 1/rank of first relevant hit."""
        for rank, chunk_id in enumerate(self.retrieved_ids, start=1):
            if chunk_id in self.relevant_ids:
                return 1.0 / rank
        return 0.0

    @property
    def ndcg_at_k(self) -> Dict[int, float]:
        """Normalized Discounted Cumulative Gain at k."""
        result = {}
        dcg = {}
        idcg = {}
        for k in self.k_values:
            dcg[k] = 0.0
            idcg[k] = 0.0

        # DCG
        for rank, chunk_id in enumerate(self.retrieved_ids, start=1):
            if chunk_id in self.relevant_ids:
                for k in self.k_values:
                    if rank <= k:
                        dcg[k] += 1.0 / (rank ** 0.5 if rank > 0 else 1)

        # IDCG (ideal DCG)
        num_relevant = len(self.relevant_ids)
        for rank in range(1, max(self.k_values) + 1):
            if rank <= num_relevant:
                for k in self.k_values:
                    if rank <= k:
                        idcg[k] += 1.0 / (rank ** 0.5 if rank > 0 else 1)

        for k in self.k_values:
            if idcg[k] > 0:
                result[k] = dcg[k] / idcg[k]
            else:
                result[k] = 0.0
        return result

    @property
    def f1_at_k(self) -> Dict[int, float]:
        result = {}
        for k in self.k_values:
            p = self.precision_at_k.get(k, 0)
            r = self.recall_at_k.get(k, 0)
            if p + r > 0:
                result[k] = 2 * p * r / (p + r)
            else:
                result[k] = 0.0
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "retrieved_count": len(self.retrieved_ids),
            "relevant_count": len(self.relevant_ids),
            "hit_at_1": self.hit_at_k.get(1, False),
            "hit_at_3": self.hit_at_k.get(3, False),
            "hit_at_5": self.hit_at_k.get(5, False),
            "precision_at_5": round(self.precision_at_k.get(5, 0), 4),
            "recall_at_5": round(self.recall_at_k.get(5, 0), 4),
            "f1_at_5": round(self.f1_at_k.get(5, 0), 4),
            "mrr": round(self.mrr, 4),
            "ndcg_at_5": round(self.ndcg_at_k.get(5, 0), 4),
        }


class RetrievalEvaluator:
    """
    Evaluate the RAG retrieval quality against ground-truth evaluation cases.

    Usage:
        evaluator = RetrievalEvaluator(project_root)
        evaluator.load_cases("docs/retrieval_eval_cases.json")
        results = evaluator.run_evaluation(hybrid_retriever)
        evaluator.print_summary(results)
    """

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.cases: List[EvaluationCase] = []
        self._loaded = False

    def load_cases(self, path: str) -> int:
        """Load evaluation cases from a JSON file."""
        cases_path = self.project_root / path
        if not cases_path.exists():
            # Try default location
            cases_path = self.project_root / "main/docs/retrieval_eval_cases.json"

        if not cases_path.exists():
            logger.warning("Evaluation cases file not found at %s", cases_path)
            return 0

        try:
            data = json.loads(cases_path.read_text(encoding="utf-8"))
            cases_list = data if isinstance(data, list) else data.get("cases", [])
            self.cases = [EvaluationCase.from_dict(c) for c in cases_list]
            self._loaded = True
            logger.info("Loaded %d evaluation cases from %s", len(self.cases), cases_path)
            return len(self.cases)
        except Exception as exc:
            logger.error("Failed to load evaluation cases: %s", exc)
            return 0

    def add_case(self, case: EvaluationCase):
        """Add a single evaluation case programmatically."""
        self.cases.append(case)

    def create_case(
        self,
        query: str,
        expected_chunk_ids: List[str],
        expected_paths: List[str],
        category: str = "general",
        difficulty: str = "medium",
    ) -> EvaluationCase:
        """Factory to create and register a new evaluation case."""
        import time
        case = EvaluationCase(
            case_id=f"case_{int(time.time() * 1000)}",
            query=query,
            relevant_chunk_ids=expected_chunk_ids,
            relevant_paths=expected_paths,
            category=category,
            difficulty=difficulty,
        )
        self.add_case(case)
        return case

    def run_evaluation(
        self,
        retriever,
        k_values: List[int] = None,
    ) -> List[RetrievalMetrics]:
        """
        Run evaluation against all loaded cases.

        Args:
            retriever: HybridRetriever or similar with a search_docs(query) -> [RetrievalHit] method.
            k_values: List of k values for metrics (default: [1, 3, 5, 10]).

        Returns:
            List of RetrievalMetrics, one per case.
        """
        if not self.cases:
            logger.warning("No evaluation cases loaded")
            return []

        results: List[RetrievalMetrics] = []
        for case in self.cases:
            try:
                hits = retriever.search_docs(case.query, top_k=10)
                retrieved_ids = [hit.chunk_id for hit in hits]
                retrieved_paths = [hit.path for hit in hits]

                metrics = RetrievalMetrics(
                    query=case.query,
                    case_id=case.case_id,
                    retrieved_ids=retrieved_ids,
                    retrieved_paths=retrieved_paths,
                    relevant_ids=case.relevant_chunk_ids,
                    relevant_paths=case.relevant_paths,
                    k_values=k_values,
                )
                results.append(metrics)
            except Exception as exc:
                logger.error("Evaluation failed for case %s: %s", case.case_id, exc)

        return results

    def summarize(self, results: List[RetrievalMetrics]) -> Dict[str, Any]:
        """Generate a summary report from evaluation results."""
        if not results:
            return {"error": "No results to summarize"}

        hit_at_1 = sum(1 for r in results if r.hit_at_k.get(1, False))
        hit_at_3 = sum(1 for r in results if r.hit_at_k.get(3, False))
        hit_at_5 = sum(1 for r in results if r.hit_at_k.get(5, False))
        n = len(results)

        if n == 0:
            return {
                "total_cases": 0,
                "hit_rate_at_1": 0.0,
                "hit_rate_at_3": 0.0,
                "hit_rate_at_5": 0.0,
                "avg_precision_at_5": 0.0,
                "avg_recall_at_5": 0.0,
                "avg_f1_at_5": 0.0,
                "avg_mrr": 0.0,
                "avg_ndcg_at_5": 0.0,
                "category_breakdown": {},
            }

        avg_prec_5 = sum(r.precision_at_k.get(5, 0) for r in results) / n
        avg_recall_5 = sum(r.recall_at_k.get(5, 0) for r in results) / n
        avg_f1_5 = sum(r.f1_at_k.get(5, 0) for r in results) / n
        avg_mrr = sum(r.mrr for r in results) / n
        avg_ndcg_5 = sum(r.ndcg_at_k.get(5, 0) for r in results) / n

        # Per-category breakdown
        categories: Dict[str, List[RetrievalMetrics]] = {}
        for r in results:
            case = next((c for c in self.cases if c.case_id == r.case_id), None)
            cat = case.category if case else "unknown"
            categories.setdefault(cat, []).append(r)

        category_summary = {}
        for cat, cat_results in categories.items():
            cn = len(cat_results)
            if cn > 0:
                category_summary[cat] = {
                    "count": cn,
                    "hit_rate_at_5": round(sum(1 for r in cat_results if r.hit_at_k.get(5, False)) / cn, 4),
                    "avg_precision_at_5": round(sum(r.precision_at_k.get(5, 0) for r in cat_results) / cn, 4),
                    "avg_mrr": round(sum(r.mrr for r in cat_results) / cn, 4),
                }

        return {
            "total_cases": n,
            "hit_rate_at_1": round(hit_at_1 / n, 4),
            "hit_rate_at_3": round(hit_at_3 / n, 4),
            "hit_rate_at_5": round(hit_at_5 / n, 4),
            "avg_precision_at_5": round(avg_prec_5, 4),
            "avg_recall_at_5": round(avg_recall_5, 4),
            "avg_f1_at_5": round(avg_f1_5, 4),
            "avg_mrr": round(avg_mrr, 4),
            "avg_ndcg_at_5": round(avg_ndcg_5, 4),
            "by_category": category_summary,
            "per_case": [r.to_dict() for r in results],
        }

    def print_summary(self, results: List[RetrievalMetrics]):
        """Print a human-readable summary to stdout."""
        summary = self.summarize(results)
        if "error" in summary:
            print(f"Error: {summary['error']}")
            return

        print("\n" + "=" * 60)
        print("RAG Retrieval Evaluation Summary")
        print("=" * 60)
        print(f"Total cases: {summary['total_cases']}")
        print(f"Hit@1:  {summary['hit_rate_at_1']:.1%}")
        print(f"Hit@3:  {summary['hit_rate_at_3']:.1%}")
        print(f"Hit@5:  {summary['hit_rate_at_5']:.1%}")
        print(f"MRR:    {summary['avg_mrr']:.4f}")
        print(f"NDCG@5: {summary['avg_ndcg_at_5']:.4f}")
        print(f"P@5:    {summary['avg_precision_at_5']:.4f}")
        print(f"R@5:    {summary['avg_recall_at_5']:.4f}")
        print(f"F1@5:   {summary['avg_f1_at_5']:.4f}")

        if summary.get("by_category"):
            print("\nPer-category:")
            for cat, stats in summary["by_category"].items():
                print(f"  {cat}: Hit@5={stats['hit_rate_at_5']:.1%} MRR={stats['avg_mrr']:.4f} ({stats['count']} cases)")
        print("=" * 60)

    def save_report(self, results: List[RetrievalMetrics], output_path: str):
        """Save the evaluation report to a JSON file."""
        summary = self.summarize(results)
        report_path = Path(output_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info("Evaluation report saved to %s", report_path)
