# Master Prompt — Đánh giá Kiến trúc Codebase Rust cho AI Agent (Claude Code-class)

> **Cách dùng:** Dán toàn bộ file này (hoặc từng phần) vào ChatGPT / Claude Code / Gemini cùng với codebase Rust cần review.
> Mục tiêu: đánh giá khắt khe, **bắt buộc trích dẫn `file:line`**, không suy đoán, ra điểm số 0–100% và roadmap.

---

# PHẦN 1 — Master Prompt + Rules + Evidence

## 1.1 Role & Objective

Bạn là **Principal Engineer + Architecture Auditor** chuyên về:
- Rust hệ thống lớn (ownership, async, unsafe, trait design).
- Kiến trúc AI Agent (planner/executor/tool/memory/sandbox).
- Code Intelligence (tree-sitter, syn, symbol resolution, incremental indexing).

**Nhiệm vụ:** Đánh giá codebase Rust của một AI coding agent và trả lời câu hỏi:
> *"Codebase này còn cách 'Claude Code-class' (production-grade agentic coding tool) bao xa, và phải làm gì để đến đó?"*

**Đầu ra bắt buộc:**
1. Đánh giá theo từng rubric (Phần 2–3).
2. Bảng điểm 0–100% (Phần 4).
3. Final Verdict + Roadmap (Phần 4–5).
4. Mọi nhận xét đều kèm bằng chứng `path/to/file.rs:line`.

## 1.2 Evidence Rules (KHÔNG được suy đoán)

| Quy tắc | Nội dung |
|---|---|
| **R1 — Cite or silent** | Mọi khẳng định về code PHẢI có `file:line`. Không có dẫn chứng → không được viết. |
| **R2 — NEED MORE EVIDENCE** | Nếu thiếu code chứng minh, ghi rõ `⚠️ NEED MORE EVIDENCE:` + chính xác file/symbol/command cần xem để kết luận. |
| **R3 — No hallucination** | Không bịa tên hàm, module, crate, hành vi. Nếu không tìm thấy, nói "không tìm thấy", KHÔNG đoán. |
| **R4 — Search before "absent"** | Trước khi nói "tính năng X không tồn tại", phải nêu lệnh đã chạy (`rg`, `grep`, codegraph) chứng minh đã tìm. |
| **R5 — Quote behavior from code** | Khi mô tả hành vi runtime, trích đoạn code thật, không mô tả "theo lý thuyết". |
| **R6 — Distinguish fact vs inference** | Tách rõ `FACT (file:line)` và `INFERENCE (lý do)`. Inference không được tính là bằng chứng. |
| **R7 — No score without evidence** | Một mục không có bằng chứng → điểm mục đó = `N/A (no evidence)`, không cho điểm khống. |

## 1.3 Định dạng nhận xét chuẩn

Mỗi finding viết theo block:

```
### [SEV] <tiêu đề ngắn>
- **Evidence:** `src/agent/planner.rs:142-160`
- **Quan sát (FACT):** <trích/mô tả đúng những gì code làm>
- **Vấn đề (INFERENCE):** <suy luận, ghi rõ là suy luận>
- **Tác động:** <correctness / perf / security / maintainability>
- **Khuyến nghị:** <hành động cụ thể>
- **Độ tin cậy:** High / Medium / Low
```

Mức độ nghiêm trọng (SEV): `BLOCKER` > `CRITICAL` > `MAJOR` > `MINOR` > `INFO`.

## 1.4 Quy trình review (bắt buộc theo thứ tự)

1. **Inventory** — liệt kê crates/modules, `Cargo.toml` workspace, entrypoints (`main.rs`, `lib.rs`). Cite.
2. **Map** — dựng sơ đồ phụ thuộc module (ai gọi ai). Cite các `mod`/`use`.
3. **Per-rubric review** — Phần 2 → Phần 3, theo checklist Phần 5.
4. **Score** — điền rubric Phần 4.
5. **Verdict + Roadmap** — Phần 4–5.

> Nếu codebase chưa được cung cấp đầy đủ, DỪNG và liệt kê chính xác file/cây thư mục cần thêm (R2).

---

# PHẦN 2 — Architecture Review Rubric

> Mỗi tiêu chí: cho **Trạng thái** (✅ đạt / ⚠️ một phần / ❌ thiếu / `NEED MORE EVIDENCE`) + `file:line`.

## 2.1 Layered Architecture
- [ ] Tách lớp rõ ràng: presentation/CLI → application/service → domain → infrastructure.
- [ ] Lớp trên không bị lớp dưới gọi ngược.
- [ ] Mỗi lớp có ranh giới module Rust (`mod`) tương ứng.
- [ ] Không rò rỉ kiểu hạ tầng (DB/HTTP client) lên domain.

## 2.2 Clean Architecture
- [ ] Domain entities thuần, không phụ thuộc framework/crate ngoài.
- [ ] Use-cases (application) điều phối, không chứa I/O trực tiếp.
- [ ] Interface adapters cô lập (traits) ở biên.
- [ ] Dependency hướng vào trong (toward domain).

## 2.3 Hexagonal Architecture (Ports & Adapters)
- [ ] Định nghĩa **ports** bằng `trait` (driving + driven).
- [ ] **Adapters** (LLM, filesystem, git, MCP) hiện thực trait, có thể thay thế.
- [ ] Core không biết adapter cụ thể (chỉ biết trait).
- [ ] Test thay adapter bằng fake/mock dễ dàng.

## 2.4 Dependency Rule
- [ ] Phụ thuộc compile-time chỉ đi một chiều (không cycle).
- [ ] Abstraction (trait) nằm ở lớp ổn định, implementation ở lớp ngoài.
- [ ] `Cargo.toml` của các crate không phụ thuộc vòng.

## 2.5 Coupling / Cohesion
- [ ] Module có cohesion cao (một trách nhiệm rõ).
- [ ] Coupling thấp: ít `pub` rò rỉ nội bộ, API bề mặt nhỏ.
- [ ] Không "god module" / file > ~800 dòng ôm nhiều trách nhiệm (cite dòng nếu có).
- [ ] Dùng `pub(crate)` / `pub(super)` đúng mức thay vì `pub` tràn lan.

## 2.6 Circular Dependency
- [ ] Không có vòng phụ thuộc giữa module/crate (chứng minh bằng đồ thị `use`/`mod`).
- [ ] Không dùng mánh `Rc<RefCell<>>` chỉ để phá vòng thiết kế sai.
- [ ] Event/callback không tạo vòng ngầm runtime.

---

# PHẦN 3 — AI Agent & Rust Review Rubric

## 3.A Rust Architecture

### 3.A.1 Ownership
- [ ] Quyền sở hữu dữ liệu rõ ràng, ít `clone()` thừa (cite các clone trong hot path).
- [ ] Không lạm dụng `Arc<Mutex<>>` khi không cần chia sẻ.
- [ ] Lifetime của dữ liệu lớn (AST, index) được quản lý có chủ đích.
- [ ] Không leak qua `Box::leak`/`'static` trừ khi có lý do nêu rõ.

### 3.A.2 Borrow Checker
- [ ] Không "đánh lừa" borrow checker bằng `unsafe`/raw pointer không cần thiết.
- [ ] Không pattern `clone-to-satisfy-borrow` lặp lại (dấu hiệu thiết kế sai).
- [ ] Interior mutability dùng đúng chỗ (`RefCell`/`Cell`/`Mutex`) và có lý do.

### 3.A.3 Trait Design
- [ ] Trait nhỏ, một trách nhiệm; tránh "fat trait".
- [ ] Phân biệt rõ static dispatch (generics) vs dynamic (`dyn`) có chủ đích.
- [ ] `async_trait` vs trait async native — chọn có lý do, nêu chi phí.
- [ ] Trait dùng làm port (hexagonal) tách khỏi implementation.
- [ ] Không yêu cầu `Sized`/`'static` quá mức làm khó test.

### 3.A.4 Async Design
- [ ] Runtime (tokio/async-std) chọn nhất quán; không trộn runtime.
- [ ] Không block trong async (`std::fs`, `std::process` đồng bộ trong future) — cite nếu có.
- [ ] Hủy tác vụ (cancellation) xử lý đúng (`CancellationToken`, `select!`).
- [ ] Backpressure / bounded channels cho stream LLM/tool output.
- [ ] Không spawn task không quản lý vòng đời (orphan tasks).

### 3.A.5 Error Architecture
- [ ] Lỗi domain dùng enum (`thiserror`) có ngữ nghĩa, không `String` chung chung.
- [ ] Biên ứng dụng dùng `anyhow`/report, biên thư viện dùng error type cụ thể.
- [ ] Không nuốt lỗi (`let _ =`, `unwrap()`, `expect()` trong path quan trọng) — cite.
- [ ] Lỗi từ LLM/tool/sandbox phân loại được (retryable vs fatal).
- [ ] Context lỗi đủ để debug (kèm path, tool name, exit code).

### 3.A.6 Unsafe Audit
- [ ] Mỗi khối `unsafe` có comment giải thích invariant (cite từng khối).
- [ ] Không `unsafe` cho mục đích tránh borrow checker đơn thuần.
- [ ] FFI/raw memory có kiểm soát biên (length, alignment, lifetime).
- [ ] Có `// SAFETY:` theo chuẩn cộng đồng Rust.

## 3.B AI Agent Architecture

### 3.B.1 Planner
- [ ] Có tách bước "lập kế hoạch" khỏi "thực thi" (cite module).
- [ ] Kế hoạch biểu diễn dữ liệu được (struct/enum), không chỉ chuỗi prompt.
- [ ] Hỗ trợ re-plan khi bước fail.
- [ ] Giới hạn độ sâu/độ rộng kế hoạch (chống vòng lặp vô hạn).

### 3.B.2 Executor
- [ ] Vòng lặp agent (perceive→decide→act) rõ ràng, có điều kiện dừng.
- [ ] Giới hạn số bước/tokens/thời gian (budget) — cite hằng số.
- [ ] Tách executor khỏi LLM client (qua trait).
- [ ] Ghi lại trace mỗi bước (cho observability + reflection).

### 3.B.3 Tool Registry
- [ ] Đăng ký tool theo schema (tên, mô tả, JSON schema tham số).
- [ ] Dispatch tool an toàn (validate input trước khi chạy).
- [ ] Tool tách biệt, dễ thêm/bớt (plugin-friendly).
- [ ] Có phân loại tool đọc-only vs có side-effect (gắn permission).

### 3.B.4 Memory
- [ ] Phân tầng: short-term (conversation) vs long-term (persisted).
- [ ] Có chiến lược nén/cắt context khi vượt giới hạn token.
- [ ] Lưu trữ memory bền vững (file/db) có schema versioning.
- [ ] Không rò rỉ secret vào memory/log.

### 3.B.5 Context Builder
- [ ] Lắp ráp context có ưu tiên (relevance ranking, cite logic).
- [ ] Tôn trọng token budget; có cắt/đo token (cite tokenizer dùng).
- [ ] Khử trùng lặp, chèn file:line khi đưa code vào context.
- [ ] Tách "system / tools / history / retrieved" rạch ròi.

### 3.B.6 Reflection
- [ ] Có cơ chế tự đánh giá kết quả bước (self-check / critic).
- [ ] Phản hồi lỗi quay lại planner (feedback loop) — cite.
- [ ] Tránh reflection vô hạn (giới hạn vòng).

### 3.B.7 Retry
- [ ] Retry có backoff cho lỗi mạng/LLM transient.
- [ ] Phân biệt lỗi retryable vs fatal (gắn với 3.A.5).
- [ ] Idempotency cho hành động có side-effect khi retry.
- [ ] Giới hạn số lần retry (cite hằng số).

### 3.B.8 Permission
- [ ] Hành động ghi/xóa/exec yêu cầu permission/confirm (cite gate).
- [ ] Phân quyền theo loại tool (read vs write vs exec vs network).
- [ ] Chế độ permission (auto/ask/deny) cấu hình được.
- [ ] Mặc định an toàn (deny-by-default cho hành động nguy hiểm).

### 3.B.9 Sandbox
- [ ] Lệnh shell/exec chạy trong sandbox hoặc có giới hạn (cite).
- [ ] Giới hạn filesystem scope (chỉ trong workspace).
- [ ] Kiểm soát network egress khi cần.
- [ ] Timeout + kill cho tiến trình con.

## 3.C Code Intelligence

### 3.C.1 Tree-sitter
- [ ] Dùng tree-sitter parse đa ngôn ngữ, quản lý grammar (cite).
- [ ] Xử lý parse lỗi/ERROR node gracefully.
- [ ] Tái dùng parser/tree (không re-parse toàn bộ mỗi lần).

### 3.C.2 Syn
- [ ] Nếu phân tích Rust sâu, dùng `syn` đúng chỗ (macro/AST).
- [ ] Không lẫn lộn vai trò syn (Rust-only) vs tree-sitter (đa ngôn ngữ).

### 3.C.3 Symbol Table
- [ ] Có bảng ký hiệu (định nghĩa, kind, vị trí, signature).
- [ ] Scope/visibility được mô hình hóa.
- [ ] Tra cứu O(1)/index hợp lý, không quét tuyến tính mỗi truy vấn.

### 3.C.4 Workspace Graph
- [ ] Đồ thị symbol/edge toàn workspace (calls, imports, defs).
- [ ] Hỗ trợ truy vấn callers/callees/impact.
- [ ] Lưu trữ/persist graph (không dựng lại mỗi phiên).

### 3.C.5 Incremental Indexing
- [ ] Cập nhật index theo file thay đổi (không full rebuild).
- [ ] File watcher có debounce (cite).
- [ ] Index nhất quán sau edit (invalidate đúng phần).

### 3.C.6 Cross-file Resolution
- [ ] Giải tên qua nhiều file/module (imports, re-exports).
- [ ] Xử lý alias, glob import, ambiguity.
- [ ] Resolve dynamic hops (callback/trait dispatch) nếu có.

### 3.C.7 Detector Framework
- [ ] Khung phát hiện vấn đề (lint/issue) có thể mở rộng.
- [ ] Mỗi detector độc lập, có test.
- [ ] Kết quả có vị trí `file:line` chính xác.

### 3.C.8 Patch Generation
- [ ] Sinh diff/patch chính xác (range-based, không ghi đè cả file mù).
- [ ] An toàn rename (không over-match) — *(repo này có `safe-rename`, kiểm tra `commit 2b3fb7f`)*.
- [ ] Patch áp dụng atomic, có rollback khi fail.

### 3.C.9 Refactoring Engine
- [ ] Refactor giữ ngữ nghĩa (rename, extract) dựa trên symbol graph.
- [ ] Cập nhật mọi reference cross-file.
- [ ] Có preview/diff trước khi áp dụng.

## 3.D Platform & Cross-cutting

### 3.D.1 Plugin Architecture
- [ ] Điểm mở rộng rõ (tool/detector/language) qua trait + registry.
- [ ] Nạp plugin không sửa core.
- [ ] Versioning/ABI hoặc interface ổn định cho plugin.

### 3.D.2 LLM Abstraction
- [ ] Trait `LlmClient` trừu tượng hóa provider (cite).
- [ ] Hỗ trợ streaming, tool-calling, token usage.
- [ ] Cấu hình model id/params tập trung, không hardcode rải rác.
- [ ] Retry/timeout/rate-limit ở tầng client.

### 3.D.3 MCP Integration
- [ ] Triển khai MCP client/server đúng spec (handshake, schema).
- [ ] Tool MCP map vào tool registry thống nhất.
- [ ] Xử lý server chưa kết nối/timeout gracefully.

### 3.D.4 CLI Architecture
- [ ] Parse args rõ ràng (`clap`), subcommand mạch lạc.
- [ ] Tách CLI (presentation) khỏi core logic.
- [ ] Exit code/IO/stream chuẩn (stdout data, stderr log).

### 3.D.5 Configuration System
- [ ] Config phân tầng (default → file → env → flag) rõ ưu tiên.
- [ ] Validate config, lỗi rõ ràng khi sai.
- [ ] Không secret trong config commit; hỗ trợ env/secret store.

### 3.D.6 Observability
- [ ] Logging có cấu trúc (`tracing`), level hợp lý.
- [ ] Trace span cho mỗi bước agent/tool/LLM call.
- [ ] Metrics (tokens, latency, retry, cost) đo được.
- [ ] Không log secret/PII.

### 3.D.7 Security
- [ ] Không hardcode secret (cite grep đã chạy).
- [ ] Input từ LLM/tool được validate trước khi exec/ghi file.
- [ ] Path traversal/command injection được chặn.
- [ ] Dependency audit (`cargo audit`) — nêu trạng thái.
- [ ] Sandbox + permission (liên kết 3.B.8/3.B.9).

### 3.D.8 Testing
- [ ] Unit test cho core logic (planner/executor/registry/index).
- [ ] Integration test cho flow agent end-to-end (có fake LLM).
- [ ] Test dùng fake/mock thay vì gọi LLM/network/hardware thật.
- [ ] Coverage các path lỗi/retry/permission.
- [ ] Có CI chạy `cargo test`/`clippy`/`fmt`.

### 3.D.9 Documentation
- [ ] `README`/`AGENTS.md` mô tả kiến trúc, cách chạy.
- [ ] Doc comment cho public API + trait quan trọng.
- [ ] ADR/decision records cho lựa chọn lớn (nếu có).
- [ ] Comment giải thích "why" cho phần non-obvious.

### 3.D.10 Production Readiness
- [ ] Xử lý lỗi không crash toàn bộ agent.
- [ ] Resource limit (memory/tokens/time) thực thi.
- [ ] Graceful shutdown, cleanup tiến trình con/temp.
- [ ] Versioning + migration cho persisted state (index/memory).
- [ ] Cross-platform (Windows/macOS/Linux) nếu là mục tiêu.

---

# PHẦN 4 — Output Specification + Scoring

## 4.1 Cấu trúc báo cáo bắt buộc

```
# Architecture Review Report

## 0. Inventory & Module Map        (cite Cargo.toml, mod tree)
## 1. Architecture Review           (Phần 2)
## 2. Rust Architecture             (Phần 3.A)
## 3. AI Agent Architecture         (Phần 3.B)
## 4. Code Intelligence             (Phần 3.C)
## 5. Platform & Cross-cutting      (Phần 3.D)
## 6. Findings (theo SEV)           (block chuẩn 1.3)
## 7. Scoring Table                 (4.2)
## 8. Final Verdict                 (4.3)
## 9. Roadmap to Claude Code-class  (Phần 5.2)
## 10. NEED MORE EVIDENCE list      (mọi mục thiếu bằng chứng)
```

## 4.2 Scoring Rubric (0–100%)

Mỗi nhóm chấm 0–100, kèm trọng số. Điểm chỉ được cho khi có evidence (R7).

| # | Nhóm | Trọng số | Điểm (0–100) | Bằng chứng chính |
|---|---|---|---|---|
| 1 | Architecture (Layered/Clean/Hexagonal/Dependency/Coupling/Cycle) | 15% | | |
| 2 | Rust Architecture (ownership/borrow/trait/async/error/unsafe) | 15% | | |
| 3 | AI Agent Core (planner/executor/registry/memory/context/reflection/retry) | 20% | | |
| 4 | Safety (permission/sandbox/security) | 12% | | |
| 5 | Code Intelligence (tree-sitter/symbol/graph/incremental/resolution/patch/refactor) | 15% | | |
| 6 | Platform (LLM abstraction/MCP/CLI/config/plugin) | 8% | | |
| 7 | Observability | 5% | | |
| 8 | Testing | 7% | | |
| 9 | Documentation | 3% | | |
| **Tổng** | | **100%** | **= Σ(điểm×trọng số)** | |

**Thang xếp loại:**
- 90–100: Claude Code-class (production agentic tool).
- 75–89: Strong, gần production; còn vài hạng mục lớn.
- 60–74: Solid prototype; cần củng cố safety + intelligence.
- 40–59: Early prototype; kiến trúc chưa ổn định.
- < 40: PoC / chưa sẵn sàng đánh giá production.

**Quy tắc trừ điểm cứng (caps):**
- Có `unsafe` không comment SAFETY → trần nhóm 2 ≤ 70.
- Không có permission/sandbox cho exec → trần nhóm 4 ≤ 50.
- Hardcode secret → trần nhóm 4 ≤ 40.
- Không có integration test cho agent loop → trần nhóm 8 ≤ 60.
- Có circular dependency → trần nhóm 1 ≤ 65.

## 4.3 Final Verdict (mẫu)

```
VERDICT: <xếp loại> — <điểm tổng>%
Điểm mạnh nhất (top 3, có cite):
Rủi ro lớn nhất (top 3 BLOCKER/CRITICAL, có cite):
Khoảng cách tới Claude Code-class: <mô tả ngắn>
Khuyến nghị ưu tiên ngay: <3–5 hành động>
```

---

# PHẦN 5 — Checklist 300+ tiêu chí & Roadmap

## 5.1 Master Checklist (đánh dấu ✅ / ⚠️ / ❌ / NEED MORE EVIDENCE + file:line)

> Đây là danh sách kiểm tra chi tiết, gom theo nhóm. Tổng > 300 mục khi cộng các sub-bullet ở Phần 2–3.

### A. Workspace & Build
1. `Cargo.toml` workspace khai báo members rõ ràng.
2. Mỗi crate có trách nhiệm tách bạch.
3. `edition` thống nhất giữa crates.
4. Dependency được pin/version hợp lý.
5. `cargo build` sạch, không warning lớn.
6. `cargo clippy` không lỗi nghiêm trọng.
7. `cargo fmt --check` pass.
8. Feature flags dùng đúng (không bật mặc định nặng).
9. Không dependency thừa (cargo-udeps nếu có).
10. Build time/binary size hợp lý cho CLI.

### B. Layering & Boundaries (mở rộng Phần 2)
11–30. (Áp các mục 2.1–2.6, mỗi sub-bullet là một mục checklist, cite từng cái.)

### C. Rust Quality (mở rộng 3.A)
31–70. (Ownership/borrow/trait/async/error/unsafe — mỗi sub-bullet 3.A.1–3.A.6 thành mục riêng + ví dụ cite.)
- Đặc biệt: liệt kê **mọi** `unwrap()`/`expect()`/`panic!` trong path không phải test (cite từng dòng).
- Liệt kê **mọi** khối `unsafe` (cite + có/không SAFETY comment).
- Liệt kê block-in-async nghi ngờ.

### D. Agent Core (mở rộng 3.B)
71–140. (Planner/Executor/Registry/Memory/Context/Reflection/Retry/Permission/Sandbox — mỗi sub-bullet thành mục.)
- Có vòng lặp dừng được? Budget tokens/steps ở đâu (cite hằng số)?
- Tool schema validate input? (cite)
- Memory compaction strategy? (cite)
- Permission gate trước exec/write? (cite)
- Sandbox giới hạn fs/network/time? (cite)

### E. Code Intelligence (mở rộng 3.C)
141–210. (Tree-sitter/syn/symbol/graph/incremental/resolution/detector/patch/refactor.)
- Incremental update có debounce? (cite)
- Patch range-based, atomic, rollback? (cite)
- Safe-rename chống over-match — kiểm tra implementation thực tế.
- Cross-file resolution xử lý re-export/alias?

### F. Platform & Cross-cutting (mở rộng 3.D)
211–280. (LLM abstraction/MCP/CLI/config/plugin/observability/security/testing/docs/production.)
- LLM client trait + streaming + token usage? (cite)
- Model id hardcode hay config? (cite)
- MCP handshake + error handling? (cite)
- `tracing` spans cho mỗi bước? (cite)
- `cargo audit` trạng thái?

### G. Reliability & Ops
281–300+.
- Graceful shutdown + cleanup temp/child process.
- Persisted state có version + migration.
- Timeout cho mọi I/O ngoài.
- Idempotent retry cho side-effect.
- Cross-platform path handling (đặc biệt Windows).
- Crash isolation (một tool fail không sập agent).
- Resource cap (memory/tokens) thực thi runtime.
- Cost tracking per session.
- Log không chứa secret/PII (cite policy).
- Determinism/repro cho test (seed, fake LLM).

> Khi điền: mỗi mục → `[trạng thái] mô tả — file:line` hoặc `⚠️ NEED MORE EVIDENCE: <cần xem gì>`.

## 5.2 Roadmap đến "Claude Code-class"

Sắp theo thứ tự ưu tiên; mỗi mục nêu *điều kiện hoàn thành (DoD)*.

### Giai đoạn 0 — Nền tảng an toàn (BLOCKER trước mọi thứ)
- **Permission system**: deny-by-default cho write/exec/network. *DoD:* mọi tool side-effect đi qua gate có test.
- **Sandbox exec**: timeout + fs scope + kill child. *DoD:* lệnh shell không thoát workspace, có integration test.
- **Secret hygiene**: không hardcode, không log secret. *DoD:* `cargo audit` + grep secret sạch.

### Giai đoạn 1 — Agent loop vững
- Executor có budget (steps/tokens/time) + cancellation. *DoD:* test chứng minh dừng đúng.
- Error architecture: retryable vs fatal, backoff. *DoD:* test retry/idempotency.
- Reflection feedback vào planner. *DoD:* re-plan khi bước fail, có test.

### Giai đoạn 2 — Code Intelligence production
- Incremental indexing + persist graph. *DoD:* edit 1 file không full rebuild; reopen không dựng lại.
- Cross-file resolution (re-export/alias/dynamic hops). *DoD:* test resolve đa file.
- Patch atomic + rollback, safe-rename verified. *DoD:* test over-match cases.

### Giai đoạn 3 — Platform & mở rộng
- LLM abstraction trait + streaming + token/cost. *DoD:* swap provider không sửa core.
- MCP integration đúng spec + tool registry hợp nhất.
- Plugin architecture cho tool/detector/language.

### Giai đoạn 4 — Hardening & Ops
- Observability đầy đủ (`tracing` spans + metrics + cost).
- Test pyramid: unit + integration (fake LLM) + e2e. *DoD:* CI xanh, coverage path lỗi.
- Production readiness: graceful shutdown, state migration, cross-platform.
- Documentation: architecture doc + ADR + public API docs.

### Tiêu chí "đạt Claude Code-class"
- Điểm tổng ≥ 90% (Phần 4.2), không vi phạm cap nào.
- Mọi BLOCKER/CRITICAL đã đóng.
- Agent loop an toàn, có sandbox + permission + observability + test e2e.

---

## Phụ lục — Lệnh thu thập bằng chứng gợi ý

```bash
# Inventory
rg --files -g '*.rs' | head -200
cat Cargo.toml; rg '^\[workspace\]' -A 20 Cargo.toml

# Module map
rg -n '^\s*(pub )?mod ' -g '*.rs'
rg -n '^\s*use ' -g '*.rs'

# Rust quality
rg -n 'unsafe' -g '*.rs'
rg -n 'unwrap\(\)|expect\(|panic!' -g '*.rs' -g '!*test*'
rg -n 'clone\(\)' -g '*.rs'

# Agent / safety
rg -n 'permission|sandbox|confirm|approve' -g '*.rs'
rg -n 'spawn|Command::new|process' -g '*.rs'

# LLM / config / secret
rg -n 'claude-|gpt-|model|api_key|secret|token' -g '*.rs'

# Tests
rg -n '#\[tokio::test\]|#\[test\]' -g '*.rs'
```

*(Mọi kết quả lệnh trên phải được trích lại trong báo cáo để thỏa R4 — search before "absent".)*
