# Phase 15 – Security, Compliance & Offline Mode

## Lệnh Agent

```
@prompts/phase_15.md Thực hiện tuần tự. Commit [Phase 15]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 15.1 | Deployment modes | SaaS, on‑prem, hybrid, air‑gapped |
| 15.2 | Licensing & pricing | Community, Pro, Enterprise |
| 15.3 | Offline mode core | Không cần internet, lưu local |
| 15.3a | Offline sync engine | Đồng bộ khi có mạng (log, telemetry, patches) |
| 15.4 | Security ISO 27001, SOC2 | |
| 15.4a | End‑to‑end encryption | Truyền firmware/patch an toàn |
| 15.4b | Code signing & attestation | Xác thực nguồn gốc patch |
| 15.4c | Secure channel | TLS 1.3, mutual auth |
| 15.4d | On‑prem data processing | Xử lý local, không gửi IP ra ngoài |
| 15.4e | Audit trail | Ghi lại mọi action, không thể xoá |

## Task list (thực hiện tuần tự)

- [ ] **15.1** Deployment modes — SaaS, on-prem, hybrid, air-gapped
- [ ] **15.2** Licensing — Community, Pro, Enterprise
- [ ] **15.3** Offline core — local storage, no internet
- [ ] **15.3a** Offline sync — đồng bộ khi online
- [ ] **15.4** ISO 27001, SOC2 compliance
- [ ] **15.4a** E2E encryption
- [ ] **15.4b** Code signing
- [ ] **15.4c** TLS 1.3, mutual auth
- [ ] **15.4d** On-prem data processing
- [ ] **15.4e** Audit trail

## Kết thúc phase

- [ ] Offline mode works without internet
- [ ] Audit trail immutable
- [ ] Commit `[Phase 15]`, build_log, ERA_ROADMAP
