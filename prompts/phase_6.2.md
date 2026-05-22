# Phase 6.2 – Target Loader, Registry, Firmware Versioning, Compatibility Matrix

## Lệnh Agent

```
@prompts/phase_6.2.md Thực hiện tuần tự. Commit [Phase 6.2]. Cập nhật build_log.md + ERA_ROADMAP.
```

## Bảng sub-phase

| ID | Sub‑phase | Mô tả |
|----|-----------|-------|
| 6.2 | Target loader & registry | YAML config, registry |
| 6.2a | Firmware versioning | Lưu hash, version, compatibility |
| 6.2b | Compatibility matrix | Target ↔ firmware version |
| 6.2c | Flash infrastructure | Transaction, A/B, OTA, journal, fleet |

## Task list (thực hiện tuần tự)

- [ ] **6.2.1** TargetLoader — YAML/JSON, schema_version, skip_on_error
- [ ] **6.2.2** TargetRegistry — get, get_by_alias, wildcard `STLINK-*`, distributed lock
- [ ] **6.2.3** TargetAliasResolver — aliases field
- [ ] **6.2.4** TargetMerger — YAML + CMSIS-Pack + auto-detect priority
- [ ] **6.2.5** TargetValidator — chip, toolchain, probe, schema_version
- [ ] **6.2.6** FirmwareHasher — SHA256, cache path+mtime
- [ ] **6.2.7** FirmwareVersionParser — regex/ELF, pre-release
- [ ] **6.2.8** FirmwareFlashSizeValidator — size ≤ flash_size
- [ ] **6.2.9** CompatibilityMatrix — YAML/URL, SpecifierSet
- [ ] **6.2.10** CompatibilityChecker — + secure boot policy
- [ ] **6.2.11** SecureBootCompatibilityExtension — signed required check
- [ ] **6.2.12** Migration schema v1→v2
- [ ] **6.2.13** Hot-reload watchdog → RegistryReloaded event
- [ ] **6.2.14** Distributed lock (Redis/file, no silent fallback)
- [ ] **6.2.15** CLI — load, list, show, export, watch, alias, migrate
- [ ] **6.2.16** MCP tools — target_*, firmware_hash, compatibility_check
- [ ] **6.2.17** Events — TargetLoaded, TargetReloaded, CompatibilityChecked
- [ ] **6.2.18** Metrics + audit JSONL
- [ ] **6.2.19** Unit tests ≥85%
- [ ] **6.2.20** Integration tests
- [ ] **6.2.21** Docs 7 files
- [ ] **6.2c** Flash infrastructure — transaction, A/B, OTA, journal, fleet

## Kết thúc phase

- [ ] pytest pass
- [ ] Commit `[Phase 6.2]`, build_log, ERA_ROADMAP
