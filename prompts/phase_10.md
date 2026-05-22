# Phase 10 – Tooling, UX & CI/CD Integration

## Lệnh Agent

```
@prompts/phase_10.md Thực hiện tuần tự. Commit [Phase 10]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 10.1 | Tool cache | Embedding‑based cache, semantic similarity |
| 10.2 | Semantic router | Chọn tool nhanh dựa trên embedding |
| 10.3 | CLI & WebSocket UI | Các lệnh aisupport debug, test, approve, logs |
| 10.4 | Approval UI | Hiển thị đề xuất, chờ approve, gửi kết quả |
| 10.5 | VS Code extension | Debug trực tiếp trong IDE |
| 10.6 | GitHub Actions integration | Chạy HIL test trên PR |
| 10.6a | Jenkins plugin | Tích hợp với Jenkins pipeline |
| 10.6b | GitLab CI & Azure DevOps | Hỗ trợ thêm CI/CD |

## Task list (thực hiện tuần tự)

- [ ] **10.1** Tool cache — embedding-based
- [ ] **10.2** Semantic router — fast tool selection
- [ ] **10.3** CLI commands đầy đủ
- [ ] **10.4** Approval web UI
- [ ] **10.5** VS Code extension — `vscode-extension/` wire CLI
- [ ] **10.6** GitHub workflow — HIL on PR
- [ ] **10.6a** Jenkins plugin
- [ ] **10.6b** GitLab CI & Azure DevOps

## Kết thúc phase

- [ ] CLI commands work
- [ ] VS Code extension loads
- [ ] Commit `[Phase 10]`, build_log, ERA_ROADMAP
