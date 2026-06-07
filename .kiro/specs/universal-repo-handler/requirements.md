# Requirements Document

## Introduction

The Universal Repo Handler extends AI_SUPPORT to process any repository a user provides, regardless of programming language, framework, or build system. The system automatically detects project characteristics, applies language-specific static analysis, generates fix suggestions using LLM and templates, and discovers and executes build environments to capture and iterate on compiler errors. This transforms AI_SUPPORT from a Python-focused tool into a true multi-language engineering intelligence platform.

## Glossary

- **Project_Detector**: Module that identifies language, framework, build tools, and project structure from file signatures and configuration files within a repository
- **Build_Runner**: Module that discovers, configures, and executes build commands for a repository, capturing compiler output and parsing errors
- **Rule_Engine**: Multi-language static analysis engine that applies language-specific rules to detect errors, anti-patterns, and quality issues
- **Fix_Generator**: Module that produces code repair patches using LLM inference combined with language-specific fix templates
- **Error_Parser**: Component that parses compiler and linter output from multiple toolchains (gcc, tsc, rustc, go build, javac) into structured error objects
- **Project_Profile**: Structured representation of a detected project's language distribution, frameworks, build tools, entry points, and dependency manifest
- **Build_Command**: A discovered or configured shell command used to compile or build a project
- **Compiler_Error**: A structured object representing a single error or warning extracted from build output, including file path, line, column, severity, and message
- **Fix_Patch**: A structured diff or code replacement that resolves a detected error or quality issue
- **Language_Grammar**: A tree-sitter grammar definition used for AST parsing of a specific programming language
- **Confidence_Score**: A numeric value between 0.0 and 1.0 indicating the reliability of a detection or fix suggestion

## Requirements

### Requirement 1: Project Language Detection

**User Story:** As a developer, I want AI_SUPPORT to automatically detect the programming languages used in my repository, so that it can apply the correct analysis tools without manual configuration.

#### Acceptance Criteria

1. WHEN a repository path is provided, THE Project_Detector SHALL scan file extensions, shebang lines, and language-specific markers to identify all languages present
2. WHEN detection completes, THE Project_Detector SHALL produce a Project_Profile containing a language distribution map with percentage breakdown by file count and lines of code
3. THE Project_Detector SHALL support detection of Python, JavaScript, TypeScript, C, C++, Rust, Go, and Java as primary languages
4. WHEN no recognizable language files are found, THE Project_Detector SHALL return a Project_Profile with language set to "unknown" and a Confidence_Score of 0.0
5. THE Project_Detector SHALL complete language detection for repositories up to 50,000 files within 30 seconds

### Requirement 2: Framework and Build Tool Detection

**User Story:** As a developer, I want AI_SUPPORT to identify the frameworks and build tools in my project, so that it can understand the project structure and execute the correct build commands.

#### Acceptance Criteria

1. WHEN a repository is scanned, THE Project_Detector SHALL identify frameworks by analyzing configuration files, dependency manifests, and import patterns
2. THE Project_Detector SHALL detect the following build tools: Make, CMake, npm/yarn/pnpm, pip/poetry/setuptools, Cargo, Go modules, Gradle, and Maven
3. WHEN multiple build tools are present, THE Project_Detector SHALL rank them by relevance using file proximity to project root and dependency graph position
4. WHEN a package.json file is present, THE Project_Detector SHALL extract available build scripts and their commands
5. WHEN a Cargo.toml file is present, THE Project_Detector SHALL identify workspace members and build targets
6. WHEN a CMakeLists.txt file is present, THE Project_Detector SHALL extract target names and build configurations
7. IF no build tool configuration is found, THEN THE Project_Detector SHALL report "no_build_tool_detected" in the Project_Profile with suggestions for manual configuration

### Requirement 3: Multi-Language Static Analysis

**User Story:** As a developer, I want AI_SUPPORT to apply language-specific static analysis rules to detect errors across all supported languages, so that I receive accurate diagnostics regardless of which language my project uses.

#### Acceptance Criteria

1. THE Rule_Engine SHALL load language-specific rule sets for each detected language in the Project_Profile
2. WHEN analyzing JavaScript or TypeScript files, THE Rule_Engine SHALL apply type-checking rules, unused variable detection, and import resolution validation
3. WHEN analyzing C or C++ files, THE Rule_Engine SHALL apply memory safety checks, uninitialized variable detection, and header include validation
4. WHEN analyzing Rust files, THE Rule_Engine SHALL apply ownership pattern checks and unsafe block validation
5. WHEN analyzing Go files, THE Rule_Engine SHALL apply error handling pattern checks and goroutine leak detection
6. THE Rule_Engine SHALL use tree-sitter Language_Grammar definitions for AST parsing of each supported language
7. WHEN a rule produces a finding, THE Rule_Engine SHALL include file path, line number, column, severity level, rule identifier, and a human-readable message
8. THE Rule_Engine SHALL support a minimum of 30 rules per language for JavaScript/TypeScript and C/C++

### Requirement 4: Build Environment Discovery and Execution

**User Story:** As a developer, I want AI_SUPPORT to automatically discover and execute the build process for my project, so that I can get compiler-level error detection without manual build configuration.

#### Acceptance Criteria

1. WHEN a Project_Profile contains a detected build tool, THE Build_Runner SHALL construct the appropriate Build_Command for that tool
2. THE Build_Runner SHALL execute Build_Commands in an isolated subprocess with configurable timeout defaulting to 180 seconds
3. WHEN a build process produces output, THE Error_Parser SHALL parse compiler errors from gcc, g++, clang, tsc, rustc, go build, and javac output formats
4. WHEN a build fails, THE Build_Runner SHALL capture all Compiler_Errors and associate each with its source file and location
5. WHILE a build is executing, THE Build_Runner SHALL stream progress events via WebSocket to provide real-time feedback to the user
6. IF a build command exceeds the configured timeout, THEN THE Build_Runner SHALL terminate the process and report a timeout error with partial output captured
7. THE Build_Runner SHALL support dependency installation commands (npm install, pip install, cargo fetch) as a pre-build step when dependencies are missing
8. IF dependency installation fails, THEN THE Build_Runner SHALL report the failure with the specific missing packages and suggest resolution steps

### Requirement 5: Compiler Error Parsing

**User Story:** As a developer, I want compiler errors from any supported toolchain to be parsed into structured objects, so that AI_SUPPORT can generate targeted fixes for each error.

#### Acceptance Criteria

1. THE Error_Parser SHALL parse gcc/g++ error format: `file:line:column: severity: message`
2. THE Error_Parser SHALL parse TypeScript compiler (tsc) error format: `file(line,column): error TSnnnn: message`
3. THE Error_Parser SHALL parse Rust compiler (rustc) error format including multi-line error spans and suggestion blocks
4. THE Error_Parser SHALL parse Go compiler error format: `file:line:column: message`
5. THE Error_Parser SHALL parse Java compiler (javac) error format: `file:line: error: message`
6. WHEN parsing produces a Compiler_Error, THE Error_Parser SHALL normalize it into a common schema containing file_path, line, column, severity, error_code, and message
7. FOR ALL valid compiler output strings, parsing then serializing then parsing a Compiler_Error SHALL produce an equivalent Compiler_Error object (round-trip property)

### Requirement 6: Fix Suggestion Generation

**User Story:** As a developer, I want AI_SUPPORT to generate accurate fix suggestions for detected errors, so that I can quickly resolve issues across any supported language.

#### Acceptance Criteria

1. WHEN a Compiler_Error or Rule_Engine finding is detected, THE Fix_Generator SHALL produce a Fix_Patch with the suggested code correction
2. THE Fix_Generator SHALL use language-specific fix templates for common error patterns before falling back to LLM-based generation
3. WHEN an LLM-based fix is generated, THE Fix_Generator SHALL include a Confidence_Score and an explanation of the fix
4. THE Fix_Generator SHALL provide the original code, the suggested replacement, and the file location in each Fix_Patch
5. WHEN multiple fixes are possible for a single error, THE Fix_Generator SHALL rank suggestions by Confidence_Score and present the top 3 options
6. IF the Fix_Generator cannot produce a suggestion with Confidence_Score above 0.3, THEN THE Fix_Generator SHALL indicate "no_confident_fix" and provide the error context for manual resolution

### Requirement 7: Iterative Build-Fix Cycle

**User Story:** As a developer, I want AI_SUPPORT to automatically attempt to fix build errors and re-run the build, so that simple issues are resolved without manual intervention.

#### Acceptance Criteria

1. WHEN a build fails with Compiler_Errors, THE Build_Runner SHALL pass each error to the Fix_Generator and collect Fix_Patches
2. WHEN Fix_Patches are generated with Confidence_Score above 0.7, THE Build_Runner SHALL apply them and re-execute the build
3. THE Build_Runner SHALL limit automatic fix-rebuild iterations to a maximum of 3 cycles to prevent infinite loops
4. WHEN a fix-rebuild cycle resolves all errors, THE Build_Runner SHALL report success with a summary of applied patches
5. IF errors remain after the maximum iterations, THEN THE Build_Runner SHALL report remaining errors with all attempted fixes and their outcomes
6. WHILE an iterative fix cycle is running, THE Build_Runner SHALL stream status updates including current iteration number, errors fixed, and errors remaining

### Requirement 8: Error Parser Pretty Printer

**User Story:** As a developer, I want parsed compiler errors to be formatted back into readable strings, so that I can view them in a familiar format in the UI.

#### Acceptance Criteria

1. THE Error_Parser SHALL format Compiler_Error objects back into human-readable strings matching the original compiler output format
2. THE Error_Parser SHALL support formatting into gcc, tsc, rustc, go, and javac output styles
3. FOR ALL valid Compiler_Error objects, parsing then printing then parsing SHALL produce an equivalent Compiler_Error object (round-trip property)

### Requirement 9: Project Detection Caching and Incremental Updates

**User Story:** As a developer, I want project detection results to be cached and updated incrementally, so that repeated analysis of the same repository is fast.

#### Acceptance Criteria

1. WHEN a Project_Profile is generated, THE Project_Detector SHALL cache the result with a content hash of the scanned file tree
2. WHEN a cached Project_Profile exists and the file tree hash matches, THE Project_Detector SHALL return the cached result without re-scanning
3. WHEN files are added or removed from the repository, THE Project_Detector SHALL perform incremental detection updating only the changed portions of the Project_Profile
4. THE Project_Detector SHALL invalidate the cache when configuration files (package.json, Cargo.toml, CMakeLists.txt, pyproject.toml) are modified

### Requirement 10: WebSocket Progress Streaming for Analysis Pipeline

**User Story:** As a developer, I want real-time progress updates during repository analysis, so that I can monitor the detection, analysis, and build process as it happens.

#### Acceptance Criteria

1. WHILE the Project_Detector is scanning a repository, THE System SHALL emit progress events via WebSocket containing current phase, files scanned, and estimated completion percentage
2. WHILE the Rule_Engine is analyzing files, THE System SHALL emit progress events containing files analyzed count, findings count, and current file being processed
3. WHILE the Build_Runner is executing a build, THE System SHALL stream build output lines in real-time via WebSocket
4. WHEN any pipeline phase completes, THE System SHALL emit a completion event with phase summary and duration
