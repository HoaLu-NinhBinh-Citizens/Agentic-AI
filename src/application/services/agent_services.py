import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from src.infrastructure.models import BenchmarkCase, BenchmarkResult, RetrievalHit


class AgentSupportService:
    def __init__(self, agent, benchmark_suite, report_writer, trace_reporter, retrieval_support):
        self.agent = agent
        self.benchmark_suite = benchmark_suite
        self.report_writer = report_writer
        self.trace_reporter = trace_reporter
        self.retrieval_support = retrieval_support

    def record_feedback(self, rating: str, note: str = ""):
        normalized = rating.strip().lower()
        if normalized not in {"good", "bad"}:
            raise ValueError("Feedback rating must be 'good' or 'bad'.")

        experiences = self.agent.memory.data.get("experiences", [])
        last_task = str(experiences[-1].get("task", "")).strip() if experiences else ""
        self.agent.memory.record_feedback(normalized, note=note, task=last_task)

    def run_benchmarks(self, include_llm: bool = False) -> List[BenchmarkResult]:
        return self.benchmark_suite.run_benchmarks(include_llm=include_llm)

    def run_smoke_tests(self) -> List[BenchmarkResult]:
        return self.benchmark_suite.run_smoke_tests()

    def load_document_question_cases(self) -> List[BenchmarkCase]:
        return self.benchmark_suite.load_document_question_cases()

    def write_benchmark_report(self, report_path: Path, results: List[BenchmarkResult]):
        self.report_writer.write_benchmark_report(report_path, results)

    def write_task_learning_report(self, report_path: Path, task: str, limit: int = 5) -> Dict:
        report = self.build_task_learning_report(task, limit=limit)
        return self.report_writer.write_json_report(report_path, report)

    def benchmark_insufficient_documentation_guard(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_insufficient_documentation_guard()

    def benchmark_parser_prose_recovery(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_parser_prose_recovery()

    def benchmark_semantic_chunk_coverage(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_semantic_chunk_coverage()

    def benchmark_generated_output_quality(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_generated_output_quality()

    def benchmark_vendor_index_exclusion(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_vendor_index_exclusion()

    def benchmark_memory_retrieval_quality(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_memory_retrieval_quality()

    def benchmark_reference_hint_traceability(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_reference_hint_traceability()

    def benchmark_page_section_query_parsing(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_page_section_query_parsing()

    def benchmark_retrieval_report_schema(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_retrieval_report_schema()

    def benchmark_decision_escalation(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_decision_escalation()

    def benchmark_backend_failure_escalation(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_backend_failure_escalation()

    def benchmark_python_runtime_validation(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_python_runtime_validation()

    def benchmark_replay_improves(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_replay_improves()

    def benchmark_regression_task_matrix(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_regression_task_matrix()

    def benchmark_llm_smoke(self) -> BenchmarkResult:
        return self.benchmark_suite.benchmark_llm_smoke()

    async def run_live_replay_benchmark(self, task: str, runs: int = 2) -> BenchmarkResult:
        return await self.trace_reporter.run_live_replay_benchmark(task, runs=runs)

    def build_task_learning_report(self, task: str, limit: int = 5) -> Dict:
        traces = self.trace_reporter.load_task_traces(task, limit=limit)
        memory_hits = self.agent.memory.retrieve_relevant(task, limit=limit)
        return self.trace_reporter.build_task_learning_report_from_data(task, traces, memory_hits, limit=limit)

    def summarize_trace_for_report(self, trace: Dict, quality: Dict[str, int | bool], iteration_limit: int = 5) -> Dict:
        return self.trace_reporter.summarize_trace_for_report(trace, quality, iteration_limit=iteration_limit)

    def summarize_memory_hit(self, item: Dict) -> Dict:
        return self.trace_reporter.summarize_memory_hit(item)

    def score_trace_artifact_quality(self, trace: Dict) -> Dict[str, int | bool]:
        return self.trace_reporter.score_trace_artifact_quality(trace)

    def describe_trace_trend(self, traces: List[Dict], quality_scores: List[Dict[str, int | bool]]) -> str:
        return self.trace_reporter.describe_trace_trend(traces, quality_scores)

    def load_task_traces(self, task: str, limit: int = 5) -> List[Dict]:
        return self.trace_reporter.load_task_traces(task, limit=limit)

    def tasks_roughly_match(self, expected: str, candidate: str) -> bool:
        return self.trace_reporter.tasks_roughly_match(expected, candidate)

    def build_retrieval_report(
        self,
        task: str,
        build_error: str = "",
        review_feedback: str = "",
        top_k: int = 5,
        allow_semantic: bool = True,
    ) -> Dict:
        return self.retrieval_support.build_retrieval_report(
            task,
            build_error=build_error,
            review_feedback=review_feedback,
            top_k=top_k,
            allow_semantic=allow_semantic,
        )

    def write_retrieval_report(
        self,
        report_path: Path,
        task: str,
        build_error: str = "",
        review_feedback: str = "",
        top_k: int = 5,
        allow_semantic: bool = True,
    ) -> Dict:
        return self.retrieval_support.write_retrieval_report(
            report_path,
            task,
            build_error=build_error,
            review_feedback=review_feedback,
            top_k=top_k,
            allow_semantic=allow_semantic,
        )

    def retrieval_hit_to_report_entry(self, hit: RetrievalHit) -> Dict:
        return self.retrieval_support.retrieval_hit_to_report_entry(hit)

    def index_rm_schema(self, pdf_path: Path, chip: str = "", max_pages: int = 0, progress=None) -> Dict:
        return self.agent.retrieval_ingestor.index_rm_schema(
            pdf_path,
            chip=chip,
            max_pages=max_pages,
            progress=progress,
        )

    def validate_register_schema(self) -> Dict:
        return self.agent.retrieval_ingestor.validate_register_schema()

    def synthesize_policy(self, limit: int = 20) -> Dict:
        return self.agent.memory.synthesize_policy(limit=limit)
