# Phase 4 – LLM Gateway & Memory + Memory Governance

## Lệnh Agent

```
@prompts/phase_4.md Thực hiện tuần tự. Commit [Phase 4]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 4.1 | Hỗ trợ nhiều LLM | Ollama, Groq, OpenAI, Claude, Gemini, Local models |
| 4.2 | RAG cơ bản | Vector store (Chroma / Qdrant / PGVector) |
| 4.3 | Nén context | Summarization, selective retention |
| 4.4 | Working memory | Lưu tool outputs per session |
| 4.5 | Long‑term memory | Lưu pattern lỗi đã sửa, giải pháp thành công |
| **4.6** | **Memory Governance** | TTL, provenance, confidence decay, PII policy, dedup |

## Task list (thực hiện tuần tự)

### Part A — LLM Gateway

- [ ] **4.1** `infrastructure/llm/gateway.py` — route ollama, openai, anthropic, groq, gemini
- [ ] **4.2** Vector store — `domain/knowledge/` hoặc retrieval module
- [ ] **4.3** `core/memory/compression/` — pruner, engine
- [ ] **4.4** `core/agent/memory/working_memory/`
- [ ] **4.5** `core/memory/semantic_memory.py` — pattern lỗi

### Part B — Memory Governance 🆕

- [ ] **4.6** TTL & retention policy — working=1h, longterm=30d, episodic=7d
- [ ] **4.6a** Provenance tracking — mỗi fact có nguồn gốc
- [ ] **4.6b** Confidence decay — fact cũ → weight giảm
- [ ] **4.6c** PII policy — detect + redact trước lưu
- [ ] **4.6d** Semantic dedup — trùng fact → merge
- [ ] **4.6e** Hallucination guard — fact không provenance → không dùng làm basis

## Kết thúc phase

- [ ] Memory fact có provenance → answer cite nguồn
- [ ] PII tự động redact trước lưu long-term
- [ ] pytest pass
- [ ] Commit `[Phase 4]`, build_log, ERA_ROADMAP
