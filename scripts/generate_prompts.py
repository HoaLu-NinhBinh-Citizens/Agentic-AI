"""
Generate phase prompt files — one file per sub-phase.
Each file includes weakness analysis, technical depth, dependencies, and risk.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent / "prompts"
ROOT.mkdir(exist_ok=True)

# ──────────────────────────────────────────────────────────────
# WEAKNESS ANALYSIS DATABASE
# key = sub-phase ID (e.g. "1a.1")
# fields:
#   difficulty   : Trivial | Easy | Medium | Hard | VeryHard | ResearchGrade
#   risk        : LOW | MEDIUM | HIGH | CRITICAL
#   hidden_trap : string — điểm yếu / cạm bẫy thường gặp
#   depends_on  : list of sub-phase IDs
#   tech_depth  : Implementation complexity
#   team_size   : Solo | Small (3-5) | Team (5-10) | Startup (10+)
# ──────────────────────────────────────────────────────────────
WEAKNESS = {
    # ── Era 1 ──────────────────────────────────────────────────
    "1a.1": dict(difficulty="Medium", risk="LOW",
                  hidden_trap="Scope creep — thêm quá nhiều chip/feature không cần thiết cho MVP. "
                              "Lock scope: ARM Cortex-M only, debug view only.",
                  depends_on=[], tech_depth="Low — mostly docs",
                  team_size="Solo"),
    "1a.2": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="Survey quá sâu vào tool details mà không cần cho Phase 1. "
                              "Chỉ cần high-level comparison table.",
                  depends_on=[], tech_depth="Low — research only",
                  team_size="Solo"),
    "1a.3": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="Thêm quá nhiều deps vào pyproject.toml. "
                              "Chỉ cần những cái cần cho Phase 1b.",
                  depends_on=[], tech_depth="Low",
                  team_size="Solo"),
    "1a.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Competitor analysis có thể làm ta thay đổi requirement. "
                              "Giữ objectivity — đừng copy feature của competitor.",
                  depends_on=["1a.1"], tech_depth="Low-Medium",
                  team_size="Solo"),
    "1a.5": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Thiết kế quá complex (microservices, event sourcing sớm) cho MVP. "
                              "Chọn monolithic + in-memory cho Phase 1-2, tách sau.",
                  depends_on=["1a.1","1a.2","1a.3","1a.4"], tech_depth="High",
                  team_size="Small"),
    "1a.6": dict(difficulty="Medium", risk="LOW",
                  hidden_trap="Mock agent quá phức tạp. Giữ đơn giản: generate() → string.",
                  depends_on=[], tech_depth="Medium",
                  team_size="Solo"),

    "1b.1": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="JWT nếu implement sớm sẽ tốn thời gian. "
                              "Có thể skip JWT ở Phase 1b, chỉ session ID.",
                  depends_on=[], tech_depth="Medium",
                  team_size="Solo"),
    "1b.2": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="WS streaming cần đúng event format: token/done/error. "
                              "Sai format → client không parse được.",
                  depends_on=["1b.1"], tech_depth="Medium",
                  team_size="Solo"),
    "1b.3": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Ollama có thể chưa có trong env. "
                              "Mock Ollama response để dev không bị block.",
                  depends_on=[], tech_depth="Medium",
                  team_size="Solo"),
    "1b.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Tool schema phải stable từ đầu. "
                              "Thay đổi schema giữa chừng → break all tools.",
                  depends_on=[], tech_depth="Medium",
                  team_size="Solo"),
    "1b.5": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="Structured logging nên dùng structlog từ đầu. "
                              "Đổi sau rất tốn effort.",
                  depends_on=[], tech_depth="Low-Medium",
                  team_size="Solo"),

    "2.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="MCP stdio subprocess có thể deadlock nếu không flush đúng. "
                              "Dùng communicate() không readline() trực tiếp.",
                  depends_on=["1b.1","1b.4"], tech_depth="High",
                  team_size="Small"),
    "2.2": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="asyncio.gather không handle exception tốt. "
                              "Dùng asyncio.gather(*, return_exceptions=True).",
                  depends_on=["2.1"], tech_depth="Medium",
                  team_size="Solo"),
    "2.3": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Retry exponential backoff nhưng không có jitter → thundering herd. "
                              "Bắt buộc thêm random jitter.",
                  depends_on=["2.2"], tech_depth="Medium",
                  team_size="Solo"),
    "2.4": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="Cache key phải hash stable (sort keys, canonical JSON). "
                              "Sai key → cache miss liên tục.",
                  depends_on=["2.2"], tech_depth="Low-Medium",
                  team_size="Solo"),
    "2.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Tool versioning nếu over-engineer sẽ tốn thời gian. "
                              "Chỉ cần major.minor.patch string compare.",
                  depends_on=["2.4"], tech_depth="Medium",
                  team_size="Solo"),

    "3.1": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Retry không idempotent tool sẽ gây side-effect. "
                              "Chỉ retry GET/read operations, không retry write.",
                  depends_on=["2.3"], tech_depth="Medium",
                  team_size="Solo"),
    "3.2": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Rate limit per-user dùng sliding window nhưng không atomic → race condition. "
                              "Dùng Redis sorted set hoặc Lua script.",
                  depends_on=["3.1"], tech_depth="Medium-High",
                  team_size="Solo"),
    "3.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Circuit breaker state machine phải thread-safe. "
                              "Dùng enum State(CLOSED/OPEN/HALF_OPEN), không bool flag.",
                  depends_on=["3.2"], tech_depth="High",
                  team_size="Small"),
    "3.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="JSON log nếu không có schema → không parse được sau. "
                              "Dùng structlog + known schema fields.",
                  depends_on=["1b.5"], tech_depth="Medium",
                  team_size="Solo"),
    "3.5": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="Metric cardinality explosion (label với user_id, request_id). "
                              "Chỉ count/count with low-cardinality labels.",
                  depends_on=["3.4"], tech_depth="Low",
                  team_size="Solo"),
    "3.6": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="OpenTelemetry setup dễ nhưng span context propagation qua WS khó. "
                              "Đảm bảo correlation_id được propagate trong WS messages.",
                  depends_on=["3.4","3.5"], tech_depth="High",
                  team_size="Small"),

    "4.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Mỗi LLM provider có response format khác nhau. "
                              "Abstract LLM interface từ đầu, không if/else provider trong code.",
                  depends_on=["3.3"], tech_depth="High",
                  team_size="Small"),
    "4.2": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Vector store có thể down. Phải có in-memory fallback. "
                              "Không block user vì vector store chậm.",
                  depends_on=["4.1"], tech_depth="High",
                  team_size="Small"),
    "4.3": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Summarization tốn token + latency. "
                              "Chỉ summarize khi context > threshold, không summarize always.",
                  depends_on=["4.1"], tech_depth="Medium",
                  team_size="Solo"),
    "4.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Working memory nếu không TTL sẽ leak. "
                              "Bắt buộc TTL per session, auto-cleanup.",
                  depends_on=["1b.4"], tech_depth="Medium",
                  team_size="Solo"),
    "4.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Pattern DB nếu không versioning sẽ conflict khi update. "
                              "Mỗi pattern phải có version field.",
                  depends_on=["4.4"], tech_depth="Medium",
                  team_size="Solo"),
    "4.6": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Hallucinated facts trong memory không có provenance → poison toàn bộ RAG. "
                              "FACT KHÔNG CÓ provenance → không được dùng làm basis cho answer. "
                              "Đây là lỗi phổ biến nhất của AI memory systems.",
                  depends_on=["4.2","4.5"], tech_depth="High",
                  team_size="Small"),

    "5.1": dict(difficulty="Hard", risk="CRITICAL",
                  hidden_trap="Event sourcing nếu replay không deterministic → bug rất khó debug. "
                              "Event phải immutable + idempotent. Không emit event có side-effect.",
                  depends_on=["3.6","4.1"], tech_depth="VeryHigh",
                  team_size="Small"),
    "5.2": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="Saga rollback nếu thiếu compensation step → inconsistent state. "
                              "Mỗi step PHẢI có compensation. Test rollback trước khi implement forward.",
                  depends_on=["5.1"], tech_depth="VeryHigh",
                  team_size="Small"),
    "5.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Multi-agent nếu không deterministic → nondeterministic bug. "
                              "Agent response phải deterministic given same input. "
                              "Dùng seed/LLM temperature=0.",
                  depends_on=["5.2"], tech_depth="High",
                  team_size="Small"),
    "5.4": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Snapshot nếu capture không đúng thời điểm → resume sai state. "
                              "Snapshot PHẢI atomic với event log.",
                  depends_on=["5.1"], tech_depth="High",
                  team_size="Small"),
    "5.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Human approval nếu không timeout → workflow treo vĩnh viễn. "
                              "Bắt buộc timeout với auto-rollback.",
                  depends_on=["5.2"], tech_depth="Medium-High",
                  team_size="Solo"),
    "5.6": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="Agent lifecycle leak (orphan agent) là bug nghiêm trọng. "
                              "PHẢI có watchdog monitor agent heartbeat. "
                              "Crash isolation: 1 agent crash không được crash toàn hệ thống.",
                  depends_on=["5.1","5.3"], tech_depth="VeryHigh",
                  team_size="Team"),
    "5.7": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Cost không có observability → không biết token spend. "
                              "Phải track cost/session real-time, alert khi exceed budget.",
                  depends_on=["4.1"], tech_depth="High",
                  team_size="Small"),

    # ── Era 1 – Embedded ────────────────────────────────────────
    "6.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Target state machine (UNKNOWN→CONNECTED→HALTED→RUNNING→FAULT) "
                              "phải atomic. Race condition khi multiple probes attach/detach.",
                  depends_on=[], tech_depth="High",
                  team_size="Small"),
    "6.1a": dict(difficulty="VeryHard", risk="HIGH",
                  hidden_trap="Abstraction layer không nên over-abstract. "
                              "Chỉ implement 1 chip thực tế (STM32), các chip khác là interface.",
                  depends_on=["6.1"], tech_depth="VeryHigh",
                  team_size="Team"),
    "6.1b": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Plugin sandbox nếu không isolate → malicious plugin có thể đọc file. "
                              "Dùng subprocess với resource limits.",
                  depends_on=["6.1"], tech_depth="High",
                  team_size="Small"),
    "6.1c": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="IDCODE read có thể fail nếu target không stop. "
                              "Phải halt trước khi read IDCODE.",
                  depends_on=["6.1"], tech_depth="Medium",
                  team_size="Solo"),

    "6.2": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="YAML schema evolution (v1→v2) nếu không có migration → "
                              "config cũ không load được. Validate schema_version trước khi parse.",
                  depends_on=["6.1"], tech_depth="Medium",
                  team_size="Solo"),
    "6.2a": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Firmware hash nếu dùng MD5 → không secure. "
                              "Bắt buộc SHA256.",
                  depends_on=["6.2"], tech_depth="Medium",
                  team_size="Solo"),
    "6.2b": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Compatibility matrix nếu không version-aware → "
                              "sai check khi firmware version format không đồng nhất.",
                  depends_on=["6.2","6.2a"], tech_depth="High",
                  team_size="Small"),
    "6.2c": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="Flash A/B nếu switch không atomic → brick device. "
                              "Phải có dual-bank validation + rollback mechanism. "
                              "ĐÂY LÀ CRITICAL — test kỹ trước khi deploy.",
                  depends_on=["6.2b"], tech_depth="VeryHigh",
                  team_size="Team"),

    "6.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="RTT buffer size nếu nhỏ → overflow. "
                              "Phải dynamic buffer hoặc throttle reader.",
                  depends_on=["6.1c"], tech_depth="High",
                  team_size="Solo"),
    "6.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Serial pattern detection phải handle malformed data. "
                              "Không crash khi receive binary data.",
                  depends_on=["6.1"], tech_depth="Medium",
                  team_size="Solo"),
    "6.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="HAL query phải handle peripheral not initialized. "
                              "Đọc register của peripheral chưa clock → 0xFFFFFFFF.",
                  depends_on=["6.1","6.3"], tech_depth="Medium",
                  team_size="Solo"),
    "6.6": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="SVD parsing phải handle incomplete SVD. "
                              "Nhiều vendor SVD có missing fields.",
                  depends_on=["6.1"], tech_depth="High",
                  team_size="Solo"),
    "6.7": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="GDB RSP packet nếu không handle long response → truncation. "
                              "Phải chunk reading với acknowledge packet.",
                  depends_on=["6.1"], tech_depth="High",
                  team_size="Solo"),
    "6.7b": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Core dump parsing phải handle stripped ELF (no symbols). "
                              "Phải fallback sang stack-only analysis.",
                  depends_on=["6.7"], tech_depth="High",
                  team_size="Solo"),

    # ── Era 2 ──────────────────────────────────────────────────
    "7.0a": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="QEMU emulation không chính xác 100% → test pass trên QEMU nhưng "
                              "fail trên hardware thật. Phải có hardware CI.",
                  depends_on=["6.1"], tech_depth="VeryHigh",
                  team_size="Team"),
    "7.0b": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="ESP-IDF emulator không production-ready. "
                              "Cân nhắc dùng real hardware hoặc skip phase này.",
                  depends_on=["7.0a"], tech_depth="VeryHigh",
                  team_size="Team"),
    "7.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="OpenOCD có nhiều version với command khác nhau. "
                              "Abstract OpenOCD version detection.",
                  depends_on=["6.1","6.7"], tech_depth="High",
                  team_size="Small"),
    "7.1a": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Multi-probe: J-Link và ST-Link có command set khác nhau. "
                              "Unified interface phải abstract thấp, không phạm vi quá rộng.",
                  depends_on=["7.1"], tech_depth="High",
                  team_size="Small"),
    "7.2": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Serial extraction từ test output phải handle multi-line log. "
                              "Regex phải greedy để không miss log lines.",
                  depends_on=["6.4"], tech_depth="Medium",
                  team_size="Solo"),
    "7.3": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Test harness generator phải handle different test framework syntax. "
                              "Unity, CppUTest, GTest có format khác nhau.",
                  depends_on=["7.1"], tech_depth="High",
                  team_size="Small"),
    "7.4": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Hardware farm manager: board state không persistent → "
                              "sau restart không biết board nào đang used. "
                              "Phải persist board state vào DB.",
                  depends_on=["7.3"], tech_depth="High",
                  team_size="Small"),
    "7.5": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Test orchestrator: concurrent flashing nhiều board cùng lúc "
                              "có thể gây USB overload → all boards fail. "
                              "Phải có throttle (max 2-3 boards đồng thời).",
                  depends_on=["7.4"], tech_depth="High",
                  team_size="Small"),
    "7.6": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Board watchdog: nếu reset không clean → file system corruption. "
                              "Phải graceful shutdown trước reset.",
                  depends_on=["7.5"], tech_depth="High",
                  team_size="Solo"),
    "7.6a": dict(difficulty="VeryHard", risk="HIGH",
                  hidden_trap="Board pool auto-replacement: detect bad board khó. "
                              "Phải distinguish hardware failure vs software failure vs cable issue.",
                  depends_on=["7.6"], tech_depth="VeryHigh",
                  team_size="Team"),
    "7.7": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Flaky test detector: flaky không deterministic → "
                              "retry có thể pass nhưng vẫn flaky. "
                              "Phải track flaky pattern, không chỉ pass/fail.",
                  depends_on=["7.5"], tech_depth="High",
                  team_size="Small"),

    "8.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Tree-sitter parse có thể crash trên large codebase. "
                              "Phải chunk parsing + incremental update.",
                  depends_on=["6.7"], tech_depth="High",
                  team_size="Small"),
    "8.2": dict(difficulty="VeryHard", risk="HIGH",
                  hidden_trap="ISR graph analysis: ISR không có symbol trong ELF stripped. "
                              "Phải infer ISR từ vector table.",
                  depends_on=["8.1"], tech_depth="VeryHigh",
                  team_size="Small"),
    "8.3": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Error pattern nếu quá generic (.*HardFault.*) → false positive. "
                              "Phải có context window (nearby lines).",
                  depends_on=["8.1"], tech_depth="High",
                  team_size="Small"),
    "8.3a": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Auto-learn pattern: new pattern có thể poison pattern library. "
                              "Phải có human review gate trước khi auto-add.",
                  depends_on=["8.3"], tech_depth="High",
                  team_size="Small"),
    "8.3b": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Pattern versioning: old pattern phải still match khi deprecated. "
                              "Deprecated pattern vẫn match nhưng log warning.",
                  depends_on=["8.3a"], tech_depth="Medium",
                  team_size="Solo"),
    "8.4": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Bug parser phải handle multiple log formats. "
                              "Test trên ≥5 format khác nhau.",
                  depends_on=["8.3"], tech_depth="High",
                  team_size="Small"),
    "8.4a": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Concurrent bug handling: deduplicate không deterministic → "
                              "inconsistent bug list. Dùng content hash.",
                  depends_on=["8.4"], tech_depth="Medium",
                  team_size="Solo"),
    "8.4b": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Bug dependency graph có thể circular. "
                              "Phải detect và break cycle.",
                  depends_on=["8.4a"], tech_depth="High",
                  team_size="Small"),
    # 8.5 symbolic → MOVED to 13b

    "9.1": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="Patch sandbox: malicious code có thể escape container. "
                              "Phải seccomp + AppArmor + no network. "
                              "ĐÂY LÀ SECURITY CRITICAL.",
                  depends_on=["5.6","8.1"], tech_depth="VeryHigh",
                  team_size="Team"),
    "9.2": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Risk score nếu không calibrated → false positive cao. "
                              "Phải tune với real patches.",
                  depends_on=["9.1"], tech_depth="High",
                  team_size="Small"),
    "9.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Trust gate: nếu confidence threshold quá cao → "
                              "almost no patch approved. Quá thấp → bad patches approved. "
                              "Phải A/B test threshold.",
                  depends_on=["9.2"], tech_depth="High",
                  team_size="Small"),
    "9.3a": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Approval timeout: nếu approver offline → workflow stuck. "
                              "Bắt buộc timeout với auto-reject + notification.",
                  depends_on=["9.3"], tech_depth="Medium",
                  team_size="Solo"),
    "9.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Skill learning: successful patch không always mean good pattern. "
                              "Phải track outcome over time.",
                  depends_on=["9.3"], tech_depth="Medium",
                  team_size="Solo"),
    "9.5": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Test generator từ crash: generated test có thể flaky. "
                              "Phải run generated test ≥3 times trước khi commit.",
                  depends_on=["9.4","7.3"], tech_depth="High",
                  team_size="Small"),

    "10.1": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Semantic cache: similar query ≠ same result. "
                              "Cache phải hash cả tool call results, không chỉ query.",
                  depends_on=["2.4"], tech_depth="High",
                  team_size="Small"),
    "10.2": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Semantic router: routing decision có thể wrong. "
                              "Phải log routing decisions để debug.",
                  depends_on=["10.1","4.2"], tech_depth="High",
                  team_size="Small"),
    "10.3": dict(difficulty="Medium", risk="LOW",
                  hidden_trap="CLI UX: nếu command không consistent → developer frustration. "
                              "Dùng Click/typer với consistent naming.",
                  depends_on=[], tech_depth="Medium",
                  team_size="Solo"),
    "10.4": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Approval UI: nếu không real-time update → approver không biết "
                              "có pending request. Dùng SSE/WebSocket push.",
                  depends_on=["9.3a"], tech_depth="Medium",
                  team_size="Solo"),
    "10.5": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="VS Code extension: extension API thay đổi giữa versions. "
                              "Phải test trên VS Code ≥3 versions.",
                  depends_on=["10.3"], tech_depth="High",
                  team_size="Small"),
    "10.6": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="GitHub Actions: secrets management không secure. "
                              "Dùng OIDC federation, không store long-lived credentials.",
                  depends_on=["7.5"], tech_depth="Medium",
                  team_size="Solo"),
    "10.6a": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Jenkins plugin: Jenkins có breaking changes giữa versions. "
                              "Phải test trên Jenkins ≥2 versions.",
                  depends_on=["10.6"], tech_depth="Medium",
                  team_size="Solo"),
    "10.6b": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="GitLab CI template phải handle both gitlab.com và self-hosted. "
                              "Self-hosted có config khác.",
                  depends_on=["10.6"], tech_depth="Medium",
                  team_size="Solo"),

    "11.1": dict(difficulty="Hard", risk="CRITICAL",
                  hidden_trap="PII removal: regex-based PII detection có false positive/negative. "
                              "Phải human review + logging để detect misses. "
                              "Sai PII removal → legal risk.",
                  depends_on=["4.6"], tech_depth="VeryHigh",
                  team_size="Team"),
    "11.2": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Labeling tool: labeler fatigue → inconsistent labels. "
                              "Phải have ≥2 labelers per sample, measure agreement.",
                  depends_on=["11.1"], tech_depth="Medium",
                  team_size="Small"),
    "11.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Encryption at rest: nếu dùng wrong key management → "
                              "data unrecoverable. Phải have key rotation mechanism.",
                  depends_on=["11.1"], tech_depth="High",
                  team_size="Small"),
    "11.4": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Benchmark: nếu benchmark không realistic → optimize wrong thing. "
                              "Phải validate benchmark với real engineers.",
                  depends_on=["11.2"], tech_depth="High",
                  team_size="Small"),
    "11.4a": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="MTTD measurement: 'detection time' phụ thuộc system load. "
                              "Phải measure trong controlled environment.",
                  depends_on=["11.4"], tech_depth="High",
                  team_size="Small"),
    "11.4b": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Agent quality metrics: false positive rate phụ thuộc threshold. "
                              "Phải report precision/recall curve.",
                  depends_on=["11.4"], tech_depth="Medium",
                  team_size="Solo"),
    "11.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Regression testing: benchmark có thể flaky trên CI. "
                              "Phải outlier detection, không fail on single run.",
                  depends_on=["11.4","10.6"], tech_depth="Medium",
                  team_size="Solo"),
    "11.6": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Human feedback: bias trong feedback. "
                              "Phải blind feedback collection.",
                  depends_on=["11.5"], tech_depth="Medium",
                  team_size="Solo"),

    # ── Era 3 ──────────────────────────────────────────────────
    "12.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Evaluation framework: baseline phải reproducible. "
                              "Fix random seed + model version.",
                  depends_on=["11.4b"], tech_depth="High",
                  team_size="Small"),
    "12.2": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="A/B testing: statistical significance cần sample size lớn. "
                              "Đủ sample trước khi conclude.",
                  depends_on=["12.1"], tech_depth="High",
                  team_size="Small"),
    "12.3": dict(difficulty="Medium", risk="HIGH",
                  hidden_trap="Rollback: không chỉ rollback model mà còn rollback config. "
                              "Config + model phải atomic.",
                  depends_on=["12.2"], tech_depth="Medium",
                  team_size="Small"),
    "12.3a": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Canary: traffic splitting có latency spike. "
                              "Phải gradual increase (1%→5%→10%→50%→100%).",
                  depends_on=["12.3"], tech_depth="Medium",
                  team_size="Solo"),
    "12.3b": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Auto-rollback trigger: alert noise → alert fatigue. "
                              "Phải tune threshold cẩn thận.",
                  depends_on=["12.3a"], tech_depth="Medium",
                  team_size="Solo"),
    "12.4": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="Fine-tune data quality: garbage in → garbage out. "
                              "Phải have data quality pipeline trước fine-tune. "
                              "≥1000 samples không đủ nếu quality thấp.",
                  depends_on=["12.2","11.6"], tech_depth="VeryHigh",
                  team_size="Team"),
    "12.5": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Quantization có thể degrade quality đáng kể. "
                              "Phải benchmark quality after quantization.",
                  depends_on=["12.4"], tech_depth="High",
                  team_size="Small"),

    "13.1": dict(difficulty="Medium", risk="LOW",
                  hidden_trap="Grafana dashboard: nếu quá nhiều metrics → noise. "
                              "Chỉ dashboard critical KPIs.",
                  depends_on=["3.5"], tech_depth="Medium",
                  team_size="Solo"),
    "13.2": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Deterministic replay: LLM call không deterministic → "
                              "replay có thể cho kết quả khác. Phải mock LLM responses.",
                  depends_on=["5.1"], tech_depth="High",
                  team_size="Small"),
    "13.3": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="SLO: nếu SLO quá tight → alert fatigue. "
                              "Đặt SLO dựa trên historical data.",
                  depends_on=["13.1"], tech_depth="Medium",
                  team_size="Solo"),
    "13.4": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Chaos engineering: inject failure có thể cascade. "
                              "Phải have circuit breaker trước khi chaos test.",
                  depends_on=["13.3","3.3"], tech_depth="High",
                  team_size="Small"),
    "13.5": dict(difficulty="ResearchGrade", risk="CRITICAL",
                  hidden_trap="CFG/ISR/DMA modeling: đây là research-grade. "
                              "Nhiều debugger thương mại còn struggle. "
                              "Chỉ implement nếu có dedicated researcher.",
                  depends_on=["13.2","8.2"], tech_depth="ResearchGrade",
                  team_size="Startup"),
    "13.6": dict(difficulty="ResearchGrade", risk="CRITICAL",
                  hidden_trap="DWARF/LTO/optimization: đây là vùng cực khó. "
                              "Inline asm + LTO → symbol information unreliable. "
                              "Không nên implement sớm.",
                  depends_on=["8.1","13.5"], tech_depth="ResearchGrade",
                  team_size="Startup"),
    "13.7": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Hardware ontology: SVD có nhiều vendor quirks. "
                              "Phải normalize trước khi build causal graph.",
                  depends_on=["6.6","8.4b"], tech_depth="High",
                  team_size="Small"),

    # Symbolic execution MOVED
    "13b.1": dict(difficulty="ResearchGrade", risk="CRITICAL",
                  hidden_trap="Symbolic execution: path explosion problem → không terminate. "
                              "Phải có path bound + heuristic pruning. "
                              "Research-grade, rất ít team làm được.",
                  depends_on=["13.2","13.7"], tech_depth="ResearchGrade",
                  team_size="Startup"),
    "13b.2": dict(difficulty="ResearchGrade", risk="CRITICAL",
                  hidden_trap="CFG reconstruction từ stripped binary: "
                              "indirect jump targets khó resolve. Không 100% accurate.",
                  depends_on=["13b.1"], tech_depth="ResearchGrade",
                  team_size="Startup"),
    "13b.3": dict(difficulty="ResearchGrade", risk="CRITICAL",
                  hidden_trap="DMA modeling: DMA peripheral config runtime-dependent. "
                              "Static analysis không thể capture runtime config.",
                  depends_on=["13b.2"], tech_depth="ResearchGrade",
                  team_size="Startup"),
    "13b.4": dict(difficulty="ResearchGrade", risk="CRITICAL",
                  hidden_trap="Causal reasoning: số lượng possible causes lớn. "
                              "Phải prune với confidence threshold.",
                  depends_on=["13b.3","13.7"], tech_depth="ResearchGrade",
                  team_size="Startup"),

    "14.1": dict(difficulty="VeryHard", risk="CRITICAL",
                  hidden_trap="OTA rollout: partial update có thể brick device. "
                              "Phải have rollback + health check + A/B switch atomic. "
                              "ĐÂY LÀ CRITICAL — real device brick = customer loss.",
                  depends_on=["6.2c","13.1"], tech_depth="VeryHigh",
                  team_size="Team"),
    "14.2": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Crash clustering: similar crash ≠ same cause. "
                              "Phải verify cluster với root cause analysis.",
                  depends_on=["8.4b","14.1"], tech_depth="High",
                  team_size="Small"),
    "14.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Anomaly detection: false positive cao → alert fatigue. "
                              "Phải tune threshold với labeled data.",
                  depends_on=["14.2"], tech_depth="High",
                  team_size="Small"),
    "14.4": dict(difficulty="VeryHard", risk="HIGH",
                  hidden_trap="Predictive failure: dự đoán trước khi xảy ra = hard. "
                              "Không có labeled failure data ban đầu. "
                              "Phải have unsupervised approach initially.",
                  depends_on=["14.3"], tech_depth="VeryHigh",
                  team_size="Team"),
    "14.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="Jira/Slack integration: external API thay đổi. "
                              "Phải handle API errors gracefully.",
                  depends_on=["14.2"], tech_depth="Medium",
                  team_size="Solo"),
    "14.6": dict(difficulty="Medium", risk="LOW",
                  hidden_trap="QA dashboard: metrics có thể be gamed. "
                              "Phải cross-validate metrics với nhau.",
                  depends_on=["7.7","11.4b"], tech_depth="Medium",
                  team_size="Solo"),

    "15.1": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Deployment modes: air-gapped có nhiều constraints. "
                              "Không có internet = không có auto-update. "
                              "Phải design for offline-first.",
                  depends_on=["14.1"], tech_depth="High",
                  team_size="Small"),
    "15.2": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="Licensing: license key management có thể bị crack. "
                              "Dùng hardware-based license if possible.",
                  depends_on=[], tech_depth="Low",
                  team_size="Solo"),
    "15.3": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Offline mode: không có internet = không có LLM API. "
                              "Phải bundle lightweight model hoặc dùng local LLM.",
                  depends_on=["15.1"], tech_depth="High",
                  team_size="Small"),
    "15.3a": dict(difficulty="Hard", risk="HIGH",
                  hidden_trap="Offline sync: conflict resolution khi online trở lại. "
                              "CRDT hoặc last-write-wins. Không data loss.",
                  depends_on=["15.3"], tech_depth="High",
                  team_size="Small"),
    "15.4": dict(difficulty="Hard", risk="CRITICAL",
                  hidden_trap="ISO 27001/SOC2 compliance: external audit required. "
                              "Đây là process, không chỉ code.",
                  depends_on=["15.3a"], tech_depth="High",
                  team_size="Team"),
    "15.4a": dict(difficulty="Hard", risk="CRITICAL",
                  hidden_trap="E2E encryption: key management là hardest part. "
                              "Phải have key rotation + key loss recovery.",
                  depends_on=["15.4"], tech_depth="VeryHigh",
                  team_size="Team"),
    "15.4b": dict(difficulty="Hard", risk="CRITICAL",
                  hidden_trap="Code signing: private key protection. "
                              "HSM không affordable cho startup. "
                              "Phải balance security vs cost.",
                  depends_on=["15.4"], tech_depth="VeryHigh",
                  team_size="Team"),
    "15.4c": dict(difficulty="Medium", risk="HIGH",
                  hidden_trap="TLS 1.3 + mTLS: certificate rotation. "
                              "Rotation có thể gây downtime nếu không automate.",
                  depends_on=["15.4"], tech_depth="Medium",
                  team_size="Small"),
    "15.4d": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="On-prem data: customer có thể violate license by forwarding data. "
                              "Đây là legal, không phải technical issue.",
                  depends_on=["15.3a"], tech_depth="Medium",
                  team_size="Solo"),
    "15.4e": dict(difficulty="Hard", risk="CRITICAL",
                  hidden_trap="Audit trail immutable: append-only log không đủ. "
                              "Phải có cryptographic integrity (hash chain hoặc WORM storage).",
                  depends_on=["15.4"], tech_depth="High",
                  team_size="Small"),

    "16.1": dict(difficulty="Easy", risk="LOW",
                  hidden_trap="OSS governance: contribution quality control. "
                              "Phải have CLA + code review process.",
                  depends_on=[], tech_depth="Low",
                  team_size="Solo"),
    "16.2": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Plugin marketplace: malicious plugins. "
                              "Phải sandbox + code review trước khi publish.",
                  depends_on=["6.1b"], tech_depth="High",
                  team_size="Small"),
    "16.3": dict(difficulty="Medium", risk="LOW",
                  hidden_trap="Documentation: docs out-of-date = worse than no docs. "
                              "Phải automate doc generation từ code.",
                  depends_on=[], tech_depth="Medium",
                  team_size="Solo"),
    "16.4a": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="AI sinh test case: generated test có thể test wrong thing. "
                              "Phải have human review + coverage analysis.",
                  depends_on=["9.5","11.5"], tech_depth="High",
                  team_size="Small"),
    "16.4b": dict(difficulty="VeryHard", risk="MEDIUM",
                  hidden_trap="AI đề xuất cải tiến: có thể recommend breaking changes. "
                              "Phải have impact analysis trước khi implement.",
                  depends_on=["16.4a"], tech_depth="VeryHigh",
                  team_size="Small"),
    "16.4c": dict(difficulty="Hard", risk="MEDIUM",
                  hidden_trap="Learning from rejections: rejection có thể vì political reason, "
                              "không phải technical reason. Phải distinguish.",
                  depends_on=["9.3"], tech_depth="High",
                  team_size="Small"),
    "16.4d": dict(difficulty="VeryHard", risk="HIGH",
                  hidden_trap="Auto fine-tune: model degradation over time. "
                              "Phải have regression testing sau mỗi fine-tune.",
                  depends_on=["12.4","11.6"], tech_depth="VeryHigh",
                  team_size="Team"),
    "16.5": dict(difficulty="Medium", risk="MEDIUM",
                  hidden_trap="ROI metrics: correlation ≠ causation. "
                              "Time saved có thể vì user change, không phải tool.",
                  depends_on=["11.4b"], tech_depth="Medium",
                  team_size="Solo"),
}


# ──────────────────────────────────────────────────────────────
# SUB-PHASE DEFINITIONS (same as before)
# ──────────────────────────────────────────────────────────────
SUBPHASES = {
    "phase_1a": [
        ("1a.1","Xác định yêu cầu và phạm vi","Debug firmware nhúng (ARM Cortex‑M, RISC‑V, ESP32, v.v.)"),
        ("1a.2","Khảo sát công cụ hiện có","OpenOCD, GDB, pyOCD, JLink, STLink, CMSIS‑DAP, QEMU, Renode"),
        ("1a.3","Lựa chọn stack công nghệ","FastAPI, WebSocket, Redis, PostgreSQL, Docker, Kubernetes, Prometheus"),
        ("1a.4","Phân tích đối thủ cạnh tranh","Segger SystemView, Lauterbach, Tracealyzer, AI debug khác"),
        ("1a.5","Lập kế hoạch kiến trúc tổng thể","Event sourcing, saga, multi‑agent, microservices hay monolithic"),
        ("1a.6","Xây dựng mock agent và test harness","Mock LLM, mock tool calling"),
    ],
    "phase_1b": [
        ("1b.1","FastAPI + WebSocket server","Session management, authentication JWT"),
        ("1b.2","Streaming token response","SSE / WebSocket streaming"),
        ("1b.3","Tích hợp LLM local (Ollama)","Gọi model, parse response"),
        ("1b.4","Tool registry cơ bản","Định nghĩa tool, schema, gọi hàm"),
        ("1b.5","Logging và health checks","Structured logging, /health endpoint"),
    ],
    "phase_2": [
        ("2.1","MCP client (Model Context Protocol)","Giao tiếp với tool server"),
        ("2.2","Tool calling song song","asyncio.gather, timeout"),
        ("2.3","Error handling và retry","Exponential backoff, fallback"),
        ("2.4","Tool caching","TTL‑based cache, LRU"),
        ("2.5","Tool versioning","Semantic versioning cho tool API"),
    ],
    "phase_3": [
        ("3.1","Retry và backoff","Exponential backoff, jitter"),
        ("3.2","Rate limiting","Per user, per tool, sliding window"),
        ("3.3","Circuit breaker","Cho LLM và tool endpoints"),
        ("3.4","Structured logging","JSON logs, ELK stack integration"),
        ("3.5","Prometheus metrics","Latency, error rate, tool usage, queue size"),
        ("3.6","Distributed tracing","OpenTelemetry + Jaeger"),
    ],
    "phase_4": [
        ("4.1","Hỗ trợ nhiều LLM","Ollama, Groq, OpenAI, Claude, Gemini, Local models"),
        ("4.2","RAG cơ bản","Vector store (Chroma / Qdrant / PGVector)"),
        ("4.3","Nén context","Summarization, selective retention"),
        ("4.4","Working memory","Lưu tool outputs per session"),
        ("4.5","Long‑term memory","Lưu pattern lỗi đã sửa, giải pháp thành công"),
        ("4.6","Memory Governance","TTL, provenance, confidence decay, PII policy, dedup"),
    ],
    "phase_5": [
        ("5.1","Event sourcing engine","Lưu mọi action, replay"),
        ("5.2","Saga orchestration","Cho debug workflow dài (rollback nếu lỗi)"),
        ("5.3","Multi‑agent coordination","Debug agent, test agent, patch agent, reviewer agent"),
        ("5.4","Distributed snapshots","Có thể resume sau lỗi"),
        ("5.5","Human‑in‑the‑loop","Checkpoint, chờ approve"),
        ("5.6","Agent Runtime Kernel","Lifecycle, sandbox, deterministic FSM, scheduling, failure isolation"),
        ("5.7","Cost Governance","Token budget, adaptive routing, model tiering, embedding budget"),
    ],
    "phase_6.1": [
        ("6.1","EmbeddedTarget model","Chip, board, debug probe, toolchain"),
        ("6.1a","Abstraction layer cho nhiều chip","STM32, NXP, TI, ESP32, RISC‑V"),
        ("6.1b","Plugin system cho chip vendor","Dễ dàng thêm chip mới"),
        ("6.1c","Auto‑detect target","Từ debug probe, đọc IDCODE"),
    ],
    "phase_6.2": [
        ("6.2","Target loader & registry","YAML config, registry"),
        ("6.2a","Firmware versioning","Lưu hash, version, compatibility"),
        ("6.2b","Compatibility matrix","Target ↔ firmware version"),
        ("6.2c","Flash infrastructure","Transaction, A/B, OTA, journal, fleet"),
    ],
    "phase_6.3": [("6.3","RTT / real-time trace","RTT up-channel, register updates, watchpoints, buffer")],
    "phase_6.4": [("6.4","Serial monitor","UART log, pattern detection")],
    "phase_6.5": [("6.5","HAL query tool","Lấy thông tin peripheral")],
    "phase_6.6": [("6.6","SVD parser","Đọc file ARM CMSIS‑SVD")],
    "phase_6.7": [
        ("6.7","GDB client","Kết nối, backtrace, biến"),
        ("6.7b","Core dump parser","ELF → stack, registers"),
    ],
    "phase_7_cli": [
        ("CLI-1","CLI commands","aisupport debug, test, approve, logs"),
        ("CLI-2","TUI","HomeScreen, StatusBar"),
    ],
    "phase_7_hil": [
        ("7.0a","Simulator cho STM32","QEMU, Renode (filter obvious failures)"),
        ("7.0b","Simulator cho ESP32","ESP‑IDF emulator"),
        ("7.1","OpenOCD adapter","Flash, reset, run"),
        ("7.1a","Multi‑probe adapter","JLink, STLink, CMSIS‑DAP, pyOCD"),
        ("7.2","Serial monitor nâng cao","Ghi log, trích xuất test result"),
        ("7.3","Test harness generator","Unity, CppUTest, GoogleTest"),
        ("7.4","Hardware farm manager","Quản lý board, trạng thái"),
        ("7.5","Test orchestrator","Song song trên nhiều board"),
        ("7.6","Board watchdog & health","Reset khi treo"),
        ("7.6a","Board pool & auto‑replacement","Dự phòng board"),
        ("7.7","Flaky test detector","Retry, phân tích"),
    ],
    "phase_8": [
        ("8.1","Project indexer","compile_commands.json, tree‑sitter, symbols"),
        ("8.2","Static firmware analysis","Call graph, ISR graph, stack estimate, unsafe API"),
        ("8.3","Error pattern library","Lưu pattern lỗi (HardFault, timeout, deadlock)"),
        ("8.3a","Auto‑learn error patterns","Từ log mới, phát hiện pattern tương tự"),
        ("8.3b","Pattern versioning","Cập nhật pattern mà không break"),
        ("8.4","Bug report parser","Log → structured bug (type, location, suspect)"),
        ("8.4a","Concurrent bug handling","Phân lập, ưu tiên, merge"),
        ("8.4b","Bug dependency graph","Bug A phụ thuộc bug B"),
    ],
    "phase_9": [
        ("9.1","Patch sandbox","Container/worktree, compile + test"),
        ("9.2","Patch suggestion","Git diff, giải thích, risk score"),
        ("9.3","Trust & approval gates","Confidence, risk (0‑10), require human"),
        ("9.3a","Approval workflow","WebSocket, CLI, REST, timeout, rollback"),
        ("9.4","Skill learning","Ghi nhớ patch thành công → skill"),
        ("9.5","Test case generator","Từ lỗi → regression test"),
    ],
    "phase_10": [
        ("10.1","Tool cache","Embedding‑based cache, semantic similarity"),
        ("10.2","Semantic router","Chọn tool nhanh dựa trên embedding"),
        ("10.3","CLI & WebSocket UI","Các lệnh aisupport debug, test, approve, logs"),
        ("10.4","Approval UI","Hiển thị đề xuất, chờ approve, gửi kết quả"),
        ("10.5","VS Code extension","Debug trực tiếp trong IDE"),
        ("10.6","GitHub Actions integration","Chạy HIL test trên PR"),
        ("10.6a","Jenkins plugin","Tích hợp với Jenkins pipeline"),
        ("10.6b","GitLab CI & Azure DevOps","Hỗ trợ thêm CI/CD"),
    ],
    "phase_11": [
        ("11.1","Data collection (opt‑in)","Log, coredump, patch (ẩn danh, xoá PII)"),
        ("11.2","Data labeling tool","CLI/Web gán nhãn (loại lỗi, patch đúng/sai)"),
        ("11.3","Storage & anonymization","PII removal, encryption at rest"),
        ("11.4","Benchmark suite","Đánh giá debug (phát hiện lỗi, đề xuất patch)"),
        ("11.4a","Debug automation benchmark","MTTD, MTTF"),
        ("11.4b","Agent quality metrics","Acceptance rate, false positive rate, time to patch"),
        ("11.5","Regression testing","Chạy benchmark trên mỗi PR"),
        ("11.6","Human feedback loop","Thu thập đúng/sai từ user"),
    ],
    "phase_12": [
        ("12.1","Evaluation framework","So sánh RAG vs fine‑tune vs baseline"),
        ("12.2","A/B testing","Triển khai song song, phân tích thống kê"),
        ("12.3","Model rollback","Tự động quay lại nếu performance giảm"),
        ("12.3a","Canary deployment","Phát hành model mới cho 1% user"),
        ("12.3b","Auto‑rollback triggers","Dựa trên metrics (error rate, latency, acceptance)"),
        ("12.4","Fine‑tune LLM","Trên dữ liệu debug (≥1000 mẫu)"),
        ("12.5","Quantization & optimization","GPU/CPU inference, ONNX, TensorRT"),
    ],
    "phase_13": [
        ("13.1","Monitoring & alerting","Prometheus, Grafana, PagerDuty"),
        ("13.2","Deterministic replay","Snapshot workspace, replay tool IO, agent state"),
        ("13.3","Error budget & SLO","99.9% availability, tự động cảnh báo"),
        ("13.4","Chaos engineering","Test farm failure, network partition"),
        ("13.5","Execution semantics","CFG, ISR interaction, DMA modeling"),
        ("13.6","Compiler intelligence","ELF symbol, ABI, inline asm, stack usage"),
        ("13.7","Hardware ontology","Từ SVD, causal graph cho lỗi"),
    ],
    "phase_13b": [
        ("13b.1","Symbolic execution engine","Path‑sensitive analysis cho embedded C"),
        ("13b.2","CFG + ISR modeling","Control flow graph + interrupt interaction"),
        ("13b.3","DMA modeling","Bus access patterns, peripheral conflicts"),
        ("13b.4","Causal reasoning","Root cause graph từ error → hardware fault"),
    ],
    "phase_14": [
        ("14.1","OTA orchestrator","Rollout, canary, health check, rollback"),
        ("14.2","Crash clustering","Gom nhóm lỗi từ nhiều thiết bị"),
        ("14.3","Telemetry anomaly detection","ML‑based (Isolation Forest, LSTM)"),
        ("14.4","Predictive failure","Dự đoán lỗi trước khi xảy ra"),
        ("14.5","Tích hợp Jira, Slack, Teams","Thông báo lỗi, tạo ticket tự động"),
        ("14.6","Dashboard cho QA","Độ bao phủ test, flaky tests, success rate"),
    ],
    "phase_15": [
        ("15.1","Deployment modes","SaaS, on‑prem, hybrid, air‑gapped"),
        ("15.2","Licensing & pricing","Community, Pro, Enterprise"),
        ("15.3","Offline mode core","Không cần internet, lưu local"),
        ("15.3a","Offline sync engine","Đồng bộ khi có mạng (log, telemetry, patches)"),
        ("15.4","Security ISO 27001, SOC2",""),
        ("15.4a","End‑to‑end encryption","Truyền firmware/patch an toàn"),
        ("15.4b","Code signing & attestation","Xác thực nguồn gốc patch"),
        ("15.4c","Secure channel","TLS 1.3, mutual auth"),
        ("15.4d","On‑prem data processing","Xử lý local, không gửi IP ra ngoài"),
        ("15.4e","Audit trail","Ghi lại mọi action, không thể xoá"),
    ],
    "phase_16": [
        ("16.1","Open source governance","CONTRIBUTING.md, CODE_OF_CONDUCT.md, PR templates"),
        ("16.2","Ecosystem integrations","Plugin marketplace, third‑party tools"),
        ("16.3","Documentation & training","User manual, API docs, video tutorials"),
        ("16.4a","AI tự sinh test case mới","Dựa trên lỗi chưa gặp, coverage gaps"),
        ("16.4b","AI tự đề xuất cải tiến kiến trúc","Phân tích bottlenecks, đề xuất thêm tool mới"),
        ("16.4c","Học từ lần từ chối của user","Điều chỉnh trust model, confidence calibration"),
        ("16.4d","Tự động fine‑tune hàng tháng","Dựa trên dữ liệu mới, benchmark"),
        ("16.5","Phân tích ROI và business metrics","Adoption rate, time saved, customer retention"),
    ],
}


def make_filename(phase_key: str, sp_id: str) -> str:
    prefix = phase_key.replace("phase_", "")
    safe_id = sp_id.replace(".", "").replace("-", "")
    return f"phase_{prefix}_{safe_id}.md"


RISK_ICON = {
    "LOW": "[LOW]",
    "MEDIUM": "[MED]",
    "HIGH": "[HIGH]",
    "CRITICAL": "[CRIT]",
}
DIFF_ICON = {
    "Trivial": "[TRIV]",
    "Easy": "[EZ]",
    "Medium": "[MED]",
    "Hard": "[HARD]",
    "VeryHard": "[V.HARD]",
    "ResearchGrade": "[RESEARCH]",
}


def make_content(phase_key: str, sp_id: str, name: str, desc: str) -> str:
    w = WEAKNESS.get(sp_id, {})
    difficulty = w.get("difficulty", "Unknown")
    risk = w.get("risk", "LOW")
    hidden_trap = w.get("hidden_trap", "Chưa phân tích.")
    depends_on = w.get("depends_on", [])
    tech_depth = w.get("tech_depth", "Unknown")
    team_size = w.get("team_size", "Solo")

    deps_str = ", ".join(depends_on) if depends_on else "Không phụ thuộc phase khác"

    return f"""# {sp_id} – {name}

## Lệnh Agent

```
@prompts/{make_filename(phase_key, sp_id)} Thực hiện task này. Commit [Phase {sp_id}]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Sub‑phase

| Trường | Giá trị |
|--------|---------|
| **ID** | {sp_id} |
| **Tên** | {name} |
| **Mô tả** | {desc} |

---

## Weakness Analysis

| Thuộc tính | Giá trị |
|------------|---------|
| **Độ khó** | {DIFF_ICON.get(difficulty, difficulty)} {difficulty} |
| **Risk** | {RISK_ICON.get(risk, risk)} {risk} |
| **Team size** | {team_size} |
| **Tech depth** | {tech_depth} |

### Hidden Trap / Điểm yếu

> ⚠️ {hidden_trap}

### Phụ thuộc (depends_on)

- {deps_str}

---

## Nhiệm vụ

- [ ] Nghiên cứu requirements cho "{name}"
- [ ] Thiết kế module / data model
- [ ] Implement code
- [ ] Viết unit tests
- [ ] Verify integration

## Acceptance Criteria

- [ ] Code chạy đúng spec
- [ ] Tests pass
- [ ] Không breaking change với phase khác

## Kết thúc

- [ ] Commit `[Phase {sp_id}] {name}`
- [ ] Cập nhật `build_log.md`
- [ ] Cập nhật `docs/ERA_ROADMAP.md` → ✅
"""


def main():
    total = 0
    for phase_key, subphases in SUBPHASES.items():
        for sp_id, name, desc in subphases:
            filename = make_filename(phase_key, sp_id)
            filepath = ROOT / filename
            filepath.write_text(make_content(phase_key, sp_id, name, desc), encoding="utf-8")
            total += 1
    print(f"[OK] {total} files generated in {ROOT}")


if __name__ == "__main__":
    main()
