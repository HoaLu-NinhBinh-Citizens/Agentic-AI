from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Tuple, cast

from src.core.agent import AgentCore, AgentExecutor, AgentPlanner
from src.core.agent.plan_mode_agent import PlanModeAgent
from src.application.services.agent_services import AgentSupportService
from src.infrastructure.benchmark import BenchmarkSuite
from src.application.services.document_workers import DocumentWorkerSupport
from src.application.services.evidence_support import EvidenceSupport
from src.application.services.experience_support import ExperienceSupport
from src.infrastructure.llm import OllamaLLM, AnthropicLLM, GeminiLLM
from src.infrastructure.llm.openai_llm import OpenAILLM, ModelRouter
from src.core.memory import AgentMemory
from src.infrastructure.models import RetrievalHit, RuntimeDiagnosis, TaskPlan, ToolResult
from src.core.config.output_policy import OutputPolicy
from src.core.parsing import OutputSanitizer, ResponseParser
from src.reporting import ReportWriter, TraceReporter
from src.application.services.review_support import ReviewSupport
from src.application.services.runtime_support import RuntimeSupport
from src.infrastructure.retrieval import (
    ChunkStore,
    EvidenceBuilder,
    HybridRetriever,
    OllamaEmbeddingClient,
    PageAwareRetrievalSupport,
    QueryAnalyzer,
    ReferenceKnowledgeBase,
    RetrievalIngestor,
    VectorIndex,
    create_vector_store,
)
from src.core.tools import BuildTools, FileTools


@dataclass
class AgentComponents:
    llm: OllamaLLM
    openai_llm: OpenAILLM
    model_router: ModelRouter
    plan_mode_agent: PlanModeAgent
    embedding_client: OllamaEmbeddingClient
    build_tools: BuildTools
    file_tools: FileTools
    memory: AgentMemory
    reference_kb: ReferenceKnowledgeBase
    chunk_store: ChunkStore
    vector_index: VectorIndex
    query_analyzer: QueryAnalyzer
    output_policy: OutputPolicy
    hybrid_retriever: HybridRetriever
    evidence_builder: EvidenceBuilder
    response_parser: ResponseParser
    output_sanitizer: OutputSanitizer
    evidence_support: EvidenceSupport
    retrieval_support: PageAwareRetrievalSupport
    review_support: ReviewSupport
    runtime_support: RuntimeSupport
    experience_support: ExperienceSupport
    document_workers: DocumentWorkerSupport
    agent_planner: AgentPlanner
    agent_core: AgentCore
    agent_executor: AgentExecutor
    benchmark_suite: BenchmarkSuite
    report_writer: ReportWriter
    trace_reporter: TraceReporter
    agent_services: AgentSupportService
    retrieval_ingestor: RetrievalIngestor


class AgentComponentFactory:
    @staticmethod
    def create(agent: Any, project_root: str, model: str) -> AgentComponents:
        # Load config for all component settings
        try:
            from src.core.config.config_loader import get_config
            cfg = get_config()
        except Exception:
            cfg = None

        def cfg_get(key: str, default):
            return cfg.get(key, default) if cfg else default

        llm = OllamaLLM(
            model=model or cfg_get("llm.ollama.model", "llama3.1:latest"),
        )
        openai_llm = OpenAILLM(
            model=cfg_get("llm.openai.model", "gpt-4o"),
            api_key=cfg_get("llm.openai.api_key", ""),
            base_url=cfg_get("llm.openai.base_url", "https://api.openai.com/v1"),
            temperature=float(cfg_get("llm.openai.temperature", 0.3)),
            max_tokens=int(cfg_get("llm.openai.max_tokens", 2048)),
        )
        anthropic_llm = AnthropicLLM(
            model=cfg_get("llm.anthropic.model", "claude-sonnet-4-5"),
            api_key=cfg_get("llm.anthropic.api_key", ""),
            temperature=float(cfg_get("llm.anthropic.temperature", 0.3)),
            max_tokens=int(cfg_get("llm.anthropic.max_tokens", 4096)),
        )
        gemini_llm = GeminiLLM(
            model=cfg_get("llm.gemini.model", "gemini-2.0-flash"),
            api_key=cfg_get("llm.gemini.api_key", ""),
            temperature=float(cfg_get("llm.gemini.temperature", 0.3)),
            max_tokens=int(cfg_get("llm.gemini.max_tokens", 4096)),
        )
        fallback_order = cfg_get("model_routing.fallback_order", ["ollama", "openai", "anthropic", "gemini"])
        model_router = ModelRouter(
            ollama_client=llm,
            openai_client=openai_llm,
            anthropic_client=anthropic_llm,
            gemini_client=gemini_llm,
            fallback_order=list(fallback_order),
        )
        plan_mode_agent = PlanModeAgent(model_router=model_router, embedded_agent=agent)
        embedding_client = OllamaEmbeddingClient(url=llm.url)
        build_tools = BuildTools(project_root)
        file_tools = FileTools(str(build_tools.build_root), workspace_root=project_root)
        memory = AgentMemory(project_root)
        reference_kb = ReferenceKnowledgeBase(project_root)
        chunk_store = ChunkStore(file_tools)
        # Use config to select vector backend (numpy or chromadb)
        try:
            from src.core.config.config_loader import get_config
            cfg = get_config()
            vector_backend = cfg.get("rag.vector_backend", "numpy")
        except Exception:
            vector_backend = "numpy"
        vector_index = create_vector_store(project_root, embedding_client, backend=vector_backend)
        query_analyzer = QueryAnalyzer()
        output_policy = OutputPolicy()
        hybrid_retriever = HybridRetriever(chunk_store, reference_kb, vector_index=vector_index)
        evidence_builder = EvidenceBuilder()
        response_parser = ResponseParser()
        output_sanitizer = OutputSanitizer(
            response_parser,
            file_tools,
            lambda task: output_policy.default_allowed_outputs(
                task,
                domain_profile=query_analyzer.analyze(task).domain_profile,
            ),
        )
        evidence_support = EvidenceSupport(agent)
        retrieval_support = PageAwareRetrievalSupport(agent)
        review_support = ReviewSupport(agent)
        runtime_support = RuntimeSupport(agent)
        experience_support = ExperienceSupport(agent)
        document_workers = DocumentWorkerSupport(agent)
        agent_planner = AgentPlanner(
            query_analyzer=query_analyzer,
            infer_task_target=agent._infer_task_target,
            should_use_chapter_workers=agent._should_use_chapter_workers,
            select_chapter_plan=agent._select_chapter_plan,
            default_allowed_outputs=output_policy.default_allowed_outputs,
            normalize_allowed_outputs=agent._normalize_allowed_outputs,
            derive_lessons=agent._derive_lessons,
            safe_int=agent._safe_int,
        )
        agent_core = AgentCore(
            create_task_plan=agent._create_task_plan,
            plan_to_dict=agent._plan_to_dict,
            analyze_iteration_state=agent._analyze_iteration_state,
            log_agent_phase=agent._log_agent_phase,
            decide_next_action=agent._decide_next_action,
            execute_action=agent._execute_action,
            observe_action=agent._observe_action,
            record_iteration_trace=agent._record_iteration_trace,
            build_final_result=agent._build_final_result,
            record_experience=agent._record_experience,
        )
        agent_executor = AgentExecutor(
            build_tools=build_tools,
            file_tools=file_tools,
            evidence_builder=evidence_builder,
            parse_and_write_code=agent._parse_and_write_code,
            review_generated_outputs=agent._review_generated_outputs,
            ensure_retrieval_confidence=agent._ensure_retrieval_confidence,
            collect_reference_hints=agent._collect_reference_hints,
            format_retrieved_context_block=cast(Callable[[object], str], agent._format_retrieved_context_block),
            format_memory_context_block=cast(Callable[[object], str], agent._format_memory_context_block),
            build_document_understanding=cast(Callable[[str, object], List[str]], agent._build_document_understanding),
            format_reference_hint_block=agent._format_reference_hint_block,
            guarded_llm_generate=agent._guarded_llm_generate,
            capture_llm_preview=agent._capture_llm_preview,
            normalize_allowed_outputs=agent._normalize_allowed_outputs,
            get_task_plan=agent._get_task_plan,
            parse_code=agent._extract_code,
            preview_text=agent._preview_text,
            diagnose_runtime_output=cast(Callable[[ToolResult, TaskPlan], RuntimeDiagnosis], agent._diagnose_runtime_output),
            is_vendor_managed_path=agent._is_vendor_managed_path,
            is_output_only_generation=cast(Callable[[object], bool], agent._is_output_only_generation),
        )
        benchmark_suite = BenchmarkSuite(agent)
        report_writer = ReportWriter(project_root)
        trace_reporter = TraceReporter(
            project_root=project_root,
            memory=memory,
            execute_task=lambda task: agent.execute_task(task),
        )
        agent_services = AgentSupportService(agent, benchmark_suite, report_writer, trace_reporter, retrieval_support)
        retrieval_ingestor = RetrievalIngestor(
            file_tools,
            reference_kb,
            chunk_store,
            is_vendor_managed_path=agent._is_vendor_managed_path,
        )
        return AgentComponents(
            llm=llm,
            openai_llm=openai_llm,
            model_router=model_router,
            plan_mode_agent=plan_mode_agent,
            embedding_client=embedding_client,
            build_tools=build_tools,
            file_tools=file_tools,
            memory=memory,
            reference_kb=reference_kb,
            chunk_store=chunk_store,
            vector_index=vector_index,
            query_analyzer=query_analyzer,
            output_policy=output_policy,
            hybrid_retriever=hybrid_retriever,
            evidence_builder=evidence_builder,
            response_parser=response_parser,
            output_sanitizer=output_sanitizer,
            evidence_support=evidence_support,
            retrieval_support=retrieval_support,
            review_support=review_support,
            runtime_support=runtime_support,
            experience_support=experience_support,
            document_workers=document_workers,
            agent_planner=agent_planner,
            agent_core=agent_core,
            agent_executor=agent_executor,
            benchmark_suite=benchmark_suite,
            report_writer=report_writer,
            trace_reporter=trace_reporter,
            agent_services=agent_services,
            retrieval_ingestor=retrieval_ingestor,
        )