# Implementation Plan: Universal Repo Handler

## Overview

This plan implements the Universal Repo Handler as a multi-language pipeline extending AI_SUPPORT's existing infrastructure. The implementation follows a bottom-up approach: data models and interfaces first, then detection, analysis, build execution, error parsing, fix generation, iterative cycle, and finally progress streaming integration. Each task builds incrementally on the previous, wiring components together at each stage.

## Tasks

- [x] 1. Define data models and core interfaces
  - [x] 1.1 Create data model module with all shared dataclasses
    - Create `src/infrastructure/analysis/universal_repo/models.py`
    - Define `ProjectProfile`, `LanguageDistribution`, `LanguageStats`, `BuildToolInfo`, `Framework`, `BuildCommand`, `CompilerError`, `FixPatch`, `BuildResult`, `IterativeBuildResult`, `DependencyResult`, `PipelineProgressEvent`
    - Include proper type annotations, default factories, and validation
    - _Requirements: 1.2, 2.1, 5.6, 6.4_

  - [x] 1.2 Create package init and component interface definitions
    - Create `src/infrastructure/analysis/universal_repo/__init__.py` with public exports
    - Define abstract base interfaces: `CompilerOutputParser` protocol, `StreamSink` protocol
    - _Requirements: 5.6, 10.1_

- [x] 2. Implement Project Detector — Language Detection
  - [x] 2.1 Implement language detection by file extension and shebang scanning
    - Create `src/infrastructure/analysis/universal_repo/project_detector.py`
    - Implement `ProjectDetector.detect_languages()` scanning file extensions, shebang lines, and language-specific markers (e.g., `go.mod`, `Cargo.toml`, `tsconfig.json`)
    - Support Python, JavaScript, TypeScript, C, C++, Rust, Go, Java as primary languages
    - Produce `LanguageDistribution` with percentage breakdown by file count and lines of code
    - Return `confidence=0.0` and `language="unknown"` when no recognizable files found
    - Handle repositories up to 50,000 files within performance budget
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [x] 2.2 Write unit tests for language detection
    - Test each supported language is detected via extension
    - Test shebang detection for scripts without extensions
    - Test empty/unknown repository returns confidence 0.0
    - Test percentage calculation accuracy
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [x] 3. Implement Project Detector — Framework and Build Tool Detection
  - [x] 3.1 Implement framework detection from config files and imports
    - Add `ProjectDetector.detect_frameworks()` analyzing config files (package.json, Cargo.toml, pyproject.toml, pom.xml, build.gradle) and import patterns
    - Return `list[Framework]` with name, version, language, and detection source
    - _Requirements: 2.1_

  - [x] 3.2 Implement build tool detection with relevance ranking
    - Add `ProjectDetector.detect_build_tools()` detecting Make, CMake, npm/yarn/pnpm, pip/poetry/setuptools, Cargo, Go modules, Gradle, Maven
    - Rank by proximity to project root and dependency graph position
    - Extract build scripts from package.json, workspace members from Cargo.toml, targets from CMakeLists.txt
    - Report `"no_build_tool_detected"` when no build tool config found
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 3.3 Implement full `detect()` method composing language, framework, and build tool detection
    - Wire `detect_languages`, `detect_frameworks`, `detect_build_tools` into a single `detect()` producing a complete `ProjectProfile`
    - Compute `file_tree_hash` for caching
    - _Requirements: 1.2, 2.1_

  - [x] 3.4 Write unit tests for framework and build tool detection
    - Test detection from package.json, Cargo.toml, CMakeLists.txt, pyproject.toml, go.mod
    - Test relevance ranking with multiple build tools present
    - Test no-build-tool scenario
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

- [x] 4. Checkpoint — Detection phase complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement Project Detection Caching
  - [x] 5.1 Implement content-hash caching and cache invalidation
    - Add `ProjectDetector.get_cached_profile()` returning cached result when file tree hash matches
    - Add `ProjectDetector.invalidate_cache()` for explicit invalidation
    - Invalidate automatically when config files (package.json, Cargo.toml, CMakeLists.txt, pyproject.toml) are modified
    - Use existing `src/infrastructure/cache/disk/` patterns for disk persistence
    - _Requirements: 9.1, 9.2, 9.4_

  - [x] 5.2 Implement incremental detection for file additions/removals
    - When files are added or removed, update only the changed portions of the `ProjectProfile` rather than full re-scan
    - _Requirements: 9.3_

  - [x] 5.3 Write unit tests for caching behavior
    - Test cache hit returns without re-scanning
    - Test cache invalidation on config file changes
    - Test incremental update on file addition
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 6. Implement Multi-Language Rule Engine
  - [x] 6.1 Create UniversalRuleEngine extending existing RuleEngine
    - Create `src/infrastructure/analysis/universal_repo/rule_engine.py`
    - Extend existing `RuleEngine` from `src/infrastructure/analysis/rule_engine.py`
    - Implement `load_rules_for_profile()` loading language-specific rule sets
    - Use tree-sitter grammars for AST parsing
    - _Requirements: 3.1, 3.6_

  - [x] 6.2 Implement language-specific rule sets for JS/TS and C/C++
    - Create `src/infrastructure/analysis/universal_repo/rules/` directory with per-language rule modules
    - JS/TS rules: type-checking, unused variables, import resolution (minimum 30 rules)
    - C/C++ rules: memory safety, uninitialized variables, header include validation (minimum 30 rules)
    - _Requirements: 3.2, 3.3, 3.8_

  - [x] 6.3 Implement language-specific rule sets for Rust and Go
    - Rust rules: ownership pattern checks, unsafe block validation
    - Go rules: error handling pattern checks, goroutine leak detection
    - _Requirements: 3.4, 3.5_

  - [x] 6.4 Implement `analyze_file()` and `analyze_project()` with Finding output
    - `analyze_file()` returns `list[Finding]` with file_path, line, column, severity, rule_id, message
    - `analyze_project()` iterates all project files with applicable rules
    - _Requirements: 3.7_

  - [x] 6.5 Write unit tests for rule engine analysis
    - Test rule loading for each supported language
    - Test finding output includes all required fields
    - Test minimum rule count per language
    - _Requirements: 3.1, 3.7, 3.8_

- [x] 7. Checkpoint — Analysis phase complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement Error Parser with strategy pattern
  - [x] 8.1 Create ErrorParser with strategy registration pattern
    - Create `src/infrastructure/analysis/universal_repo/error_parser.py`
    - Implement `ErrorParser` with `parse()`, `format()`, and `register_parser()` methods
    - Define `CompilerOutputParser` protocol for strategy implementations
    - _Requirements: 5.6_

  - [x] 8.2 Implement gcc/g++ and clang output parser
    - Parse format: `file:line:column: severity: message`
    - Extract error codes where available
    - Handle multi-line error context
    - _Requirements: 5.1_

  - [x] 8.3 Implement TypeScript compiler (tsc) output parser
    - Parse format: `file(line,column): error TSnnnn: message`
    - Extract TS error codes
    - _Requirements: 5.2_

  - [x] 8.4 Implement Rust compiler (rustc) output parser
    - Parse multi-line error spans and suggestion blocks
    - Extract error codes (E0308, etc.)
    - Handle rustc's structured diagnostic output
    - _Requirements: 5.3_

  - [x] 8.5 Implement Go compiler and Java compiler (javac) output parsers
    - Go format: `file:line:column: message`
    - Java format: `file:line: error: message`
    - _Requirements: 5.4, 5.5_

  - [x] 8.6 Implement pretty-printer formatting back to compiler-style output
    - Format `CompilerError` objects back into human-readable strings for each supported compiler style (gcc, tsc, rustc, go, javac)
    - Ensure round-trip property: parse → format → parse produces equivalent object
    - _Requirements: 8.1, 8.2, 8.3_

  - [x] 8.7 Write unit tests for error parsers and pretty printer
    - Test each parser with real compiler output samples
    - Test normalization into common schema
    - Test round-trip: parse → serialize → parse equivalence
    - Test format output matches expected compiler style
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.1, 8.2, 8.3_

- [x] 9. Implement Build Runner
  - [x] 9.1 Create BuildRunner with build command construction
    - Create `src/infrastructure/analysis/universal_repo/build_runner.py`
    - Implement `construct_build_command()` generating appropriate commands from `ProjectProfile`
    - Support npm/yarn/pnpm build, cargo build, go build, make, cmake, gradle, maven
    - _Requirements: 4.1_

  - [x] 9.2 Implement build execution with subprocess isolation and timeout
    - Implement `run_build()` using `asyncio.subprocess` with configurable timeout (default 180s)
    - Capture stdout/stderr, parse errors via `ErrorParser`
    - Terminate on timeout, report partial output
    - Associate each `CompilerError` with source file and location
    - _Requirements: 4.2, 4.3, 4.4, 4.6_

  - [x] 9.3 Implement dependency installation as pre-build step
    - Implement `install_dependencies()` running npm install, pip install, cargo fetch, etc.
    - Report failures with specific missing packages and resolution suggestions
    - _Requirements: 4.7, 4.8_

  - [x] 9.4 Write unit tests for build runner
    - Test command construction for each build tool
    - Test timeout handling terminates process
    - Test error association with source files
    - Test dependency installation failure reporting
    - _Requirements: 4.1, 4.2, 4.6, 4.7, 4.8_

- [x] 10. Checkpoint — Build phase complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement Fix Generator
  - [x] 11.1 Create FixGenerator with template-first, LLM-fallback strategy
    - Create `src/infrastructure/analysis/universal_repo/fix_generator.py`
    - Implement `get_template_fix()` for common error patterns per language
    - Implement `get_llm_fix()` using existing LLM provider with confidence scoring
    - Wire into `generate_fix()` trying templates first, falling back to LLM
    - _Requirements: 6.1, 6.2, 6.3_

  - [x] 11.2 Implement fix ranking and no-confident-fix fallback
    - When multiple fixes possible, rank by `Confidence_Score` and return top 3
    - When no fix exceeds 0.3 confidence, indicate `"no_confident_fix"` with error context
    - Include original code, replacement, file location, and explanation in each `FixPatch`
    - _Requirements: 6.4, 6.5, 6.6_

  - [x] 11.3 Implement `generate_fix_from_finding()` for static analysis findings
    - Generate fixes from Rule_Engine findings using same template+LLM approach
    - _Requirements: 6.1_

  - [x] 11.4 Write unit tests for fix generator
    - Test template fix selection for known patterns
    - Test LLM fallback invocation
    - Test confidence filtering and ranking
    - Test no-confident-fix threshold behavior
    - _Requirements: 6.2, 6.3, 6.5, 6.6_

- [x] 12. Implement Iterative Build-Fix Cycle
  - [x] 12.1 Implement `run_iterative_fix_cycle()` with max 3 iterations
    - Wire `BuildRunner` → `ErrorParser` → `FixGenerator` → apply patches → rebuild loop
    - Apply only patches with confidence > 0.7 automatically
    - Cap at 3 iterations to prevent infinite loops
    - Report success with summary of applied patches on full resolution
    - Report remaining errors with all attempted fixes when max iterations reached
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 12.2 Write unit tests for iterative build-fix cycle
    - Test cycle terminates after 3 iterations max
    - Test only high-confidence fixes are applied
    - Test success reporting when all errors resolved
    - Test remaining errors reporting after max iterations
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 13. Implement WebSocket Progress Streaming
  - [x] 13.1 Create PipelineProgressEmitter extending existing StreamEvent model
    - Create `src/infrastructure/analysis/universal_repo/progress_emitter.py`
    - Extend `StreamEvent` from `src/core/streaming/stream.py`
    - Implement `emit_detection_progress()`, `emit_analysis_progress()`, `emit_build_progress()`, `emit_phase_complete()`
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 13.2 Wire progress streaming into detection, analysis, and build phases
    - Add `progress_sink` parameter to `ProjectDetector.detect()`, `UniversalRuleEngine.analyze_project()`, `BuildRunner.run_build()`
    - Emit progress during file scanning, rule analysis, and build output streaming
    - Emit status updates during iterative fix cycle (iteration number, errors fixed, errors remaining)
    - _Requirements: 4.5, 7.6, 10.1, 10.2, 10.3, 10.4_

  - [x] 13.3 Write unit tests for progress streaming
    - Test events emitted during detection phase
    - Test events emitted during build output streaming
    - Test completion events include summary and duration
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 14. Integration — Wire full pipeline together
  - [x] 14.1 Create pipeline orchestrator wiring all phases
    - Create `src/infrastructure/analysis/universal_repo/pipeline.py`
    - Implement full pipeline: detect → analyze → build → parse → fix → iterate → report
    - Expose as single entry point accepting a repository path
    - Wire cache, progress streaming, and all components
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.6, 6.1, 7.1, 9.1, 10.1_

  - [x] 14.2 Write integration tests for full pipeline
    - Test pipeline end-to-end with a minimal test repository
    - Test pipeline handles missing build tool gracefully
    - Test pipeline reports results with all errors, fixes, and outcomes
    - _Requirements: 1.1, 4.1, 7.4, 7.5_

- [x] 15. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at phase boundaries
- The design uses Python explicitly — all implementations use Python with async/await patterns
- The implementation extends existing modules (`rule_engine.py`, `compile_error_fixer.py`, `fix_engine/`, `streaming/stream.py`) rather than replacing them
- All new code lives under `src/infrastructure/analysis/universal_repo/` to maintain existing project structure conventions
- Unit tests validate specific examples and edge cases; the design has no Correctness Properties section so no property-based tests are included

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1", "8.1"] },
    { "id": 3, "tasks": ["2.2", "3.1", "8.2", "8.3", "8.4", "8.5"] },
    { "id": 4, "tasks": ["3.2", "8.6"] },
    { "id": 5, "tasks": ["3.3", "8.7"] },
    { "id": 6, "tasks": ["3.4", "5.1"] },
    { "id": 7, "tasks": ["5.2", "5.3", "6.1"] },
    { "id": 8, "tasks": ["6.2", "6.3"] },
    { "id": 9, "tasks": ["6.4", "6.5"] },
    { "id": 10, "tasks": ["9.1"] },
    { "id": 11, "tasks": ["9.2", "9.3"] },
    { "id": 12, "tasks": ["9.4", "11.1"] },
    { "id": 13, "tasks": ["11.2", "11.3"] },
    { "id": 14, "tasks": ["11.4", "12.1"] },
    { "id": 15, "tasks": ["12.2", "13.1"] },
    { "id": 16, "tasks": ["13.2"] },
    { "id": 17, "tasks": ["13.3", "14.1"] },
    { "id": 18, "tasks": ["14.2"] }
  ]
}
```
