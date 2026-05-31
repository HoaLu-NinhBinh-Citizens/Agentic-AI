# Requirements Document

## Introduction

This document specifies the requirements for upgrading AI_SUPPORT to achieve ≥95% Cursor-like capabilities across a 3-phase plan (P0 → P1 → P2). The upgrade expands the static analysis rule engine to 100+ rules, enhances the call graph and dependency graph with alias resolution and incremental indexing, integrates data flow analysis with taint tracking, improves CLI user experience with syntax highlighting and autocomplete, adds framework-specific rules, and introduces LLM-powered fix suggestions, plugin hot-reload, and team collaboration features.

## Glossary

- **Rule_Engine**: The extensible static analysis engine (`src/infrastructure/analysis/rule_engine.py`) that registers, manages, and executes detection rules against source code files.
- **Call_Graph**: The AST-based cross-file call graph builder (`src/core/cognition/call_graph.py`) that tracks function definitions, call sites, and caller/callee relationships.
- **Call_Graph_Builder**: The semantic call graph builder (`src/infrastructure/analysis/call_graph_builder.py`) with alias resolution and class hierarchy understanding.
- **Data_Flow_Analyzer**: The taint tracking module (`src/infrastructure/analysis/data_flow.py`) that traces user input propagation from sources to sinks.
- **CLI**: The command-line interface (`src/interfaces/cli/main.py`) providing slash commands, autocomplete, and interactive review workflows.
- **Autocomplete_Engine**: The readline-based Tab completion system (`src/interfaces/cli/autocomplete.py`) for commands, files, flags, and symbols.
- **Plugin_Manager**: The plugin lifecycle manager (`src/infrastructure/plugins/plugin_system.py`) handling discovery, loading, activation, deactivation, and hot-reload of plugins.
- **Report_Generator**: The output formatting system (`src/infrastructure/reporting/`) producing CLI, Markdown, HTML, and JSON reports.
- **Incremental_Indexer**: The file-watching subsystem that re-indexes only modified files using modification timestamps and dependency-aware invalidation.
- **LLM_Suggester**: The AI-powered component that generates fix suggestions using OpenAI, local LLM, or template-based fallback.
- **Collaboration_Engine**: The team collaboration subsystem providing comments, threads, resolution state tracking, and PR review report generation.

## Requirements

### Requirement 1: Expand Rule Engine to 100+ Rules

**User Story:** As a developer, I want the Rule_Engine to contain at least 100 detection rules covering security, code quality, type safety, error handling, and performance categories, so that code reviews are comprehensive and catch a wide range of issues.

#### Acceptance Criteria

1. THE Rule_Engine SHALL register at least 100 unique rules across the categories: security, code quality, type safety, error handling, and performance.
2. WHEN a new rule is registered, THE Rule_Engine SHALL validate that the rule has a unique ID, a non-empty pattern list or AST query, and at least one target language.
3. WHEN the Rule_Engine executes detection on a Python file, THE Rule_Engine SHALL apply all rules whose language list includes "python" and return deduplicated findings sorted by file, line, and severity.
4. THE Rule_Engine SHALL provide at least 40 security rules, 15 code quality rules, 10 type safety rules, 10 error handling rules, and 25 performance rules.
5. WHEN a rule produces a finding, THE Rule_Engine SHALL include a fix_template field containing a non-empty suggested remediation for at least 80% of all registered rules.

### Requirement 2: Alias-Aware Import Resolution in Call Graph

**User Story:** As a developer, I want the Call_Graph to resolve aliased imports correctly, so that call graph edges reflect actual function references regardless of import aliases used.

#### Acceptance Criteria

1. WHEN a Python file imports a function using an alias (e.g., `from module import func as f`), THE Call_Graph SHALL resolve calls to `f` by recording the original name `module.func` in the callee field of the call graph edge.
2. WHEN a Python file uses a module alias (e.g., `import numpy as np`), THE Call_Graph SHALL resolve attribute calls like `np.array()` to `numpy.array` in the callee field, including chained attributes up to 3 levels deep (e.g., `np.linalg.solve()` resolves to `numpy.linalg.solve`).
3. THE Call_Graph SHALL maintain an alias mapping per file that maps each alias to its original fully-qualified name, where fully-qualified means the source module path concatenated with the symbol name using dot notation.
4. WHEN an alias is re-assigned within a function or module scope via a subsequent assignment statement, THE Call_Graph SHALL use the lexically most recent binding at each call site based on line number order.
5. IF an alias references a module or symbol that is not indexed in the project, THEN THE Call_Graph SHALL retain the resolved module-qualified name as the callee (e.g., `numpy.array`) without raising an error or omitting the call edge.
6. WHEN a file's alias mapping is rebuilt, THE Call_Graph SHALL complete alias resolution for a single file containing up to 50 import statements within 100 milliseconds.

### Requirement 3: Reverse Index for Call Graph

**User Story:** As a developer, I want to quickly find all callers of a given function using a reverse index, so that impact analysis and refactoring are efficient.

#### Acceptance Criteria

1. THE Call_Graph SHALL maintain a reverse index mapping each callee function name to a list of CallSite objects representing all callers.
2. WHEN a new call site is added via `add_call()`, THE Call_Graph SHALL append the CallSite to the reverse index under the callee's function name before the `add_call()` method returns.
3. WHEN `get_callers(function_name)` is invoked, THE Call_Graph SHALL return all CallSite objects where the callee matches the given function name.
4. IF `get_callers(function_name)` is invoked with a function name that has no recorded callers, THEN THE Call_Graph SHALL return an empty list.
5. WHEN a file is cleared from the Call_Graph, THE Call_Graph SHALL remove all reverse index entries where the CallSite's file matches the cleared file path, while preserving entries associated with other files.
6. WHEN `get_callers(function_name)` is invoked with an optional file_path parameter, THE Call_Graph SHALL return only CallSite objects where both the callee matches the given function name and the file matches the given file_path.

### Requirement 4: Incremental Indexing for Call Graph

**User Story:** As a developer, I want the Call_Graph to support incremental indexing based on file modification timestamps, so that only changed files are re-analyzed during iterative development.

#### Acceptance Criteria

1. WHEN `build_incremental(file_path, content)` is called, THE Call_Graph SHALL retrieve the file's current modification time from the filesystem and compare it against the last recorded timestamp for that file path.
2. IF the file modification time is less than or equal to the last recorded timestamp, THEN THE Call_Graph SHALL skip re-indexing and return False.
3. IF the file has no previously recorded timestamp (first-time indexing), THEN THE Call_Graph SHALL proceed with indexing and return True.
4. WHEN a file is re-indexed incrementally, THE Call_Graph SHALL clear all existing call sites, function definitions, and import mappings associated with that file before adding new call sites and function definitions.
5. THE Call_Graph SHALL store the modification timestamp for each indexed file and expose it via `get_file_mtime(file_path)`, returning 0 for files that have not been indexed.
6. IF the file path does not exist on the filesystem when `build_incremental` is called, THEN THE Call_Graph SHALL skip the modification time check and proceed with indexing using the provided content.

### Requirement 5: Call Site Argument Tracking

**User Story:** As a developer, I want call sites to record the arguments passed at each call, so that data flow analysis can trace variable propagation through function calls.

#### Acceptance Criteria

1. WHEN a call site is recorded, THE Call_Graph SHALL extract and store the list of argument identifiers from both positional and keyword arguments passed to the function.
2. THE CallSite dataclass SHALL include an `arguments` field of type `list[str]` containing the extracted argument identifiers from all positional and keyword arguments at the call site.
3. WHEN a positional argument is a simple variable reference (AST Name node), THE Call_Graph SHALL include the variable name in the arguments list.
4. WHEN an argument is a constant literal (number, string, boolean, or None), THE Call_Graph SHALL omit it from the arguments list.
5. WHEN an argument is a keyword argument, THE Call_Graph SHALL include the keyword parameter name in the arguments list (e.g., for `func(key=value)`, include "key").
6. WHEN an argument is an attribute access expression (e.g., `obj.attr`), THE Call_Graph SHALL include the dotted name string in the arguments list (e.g., "obj.attr").
7. WHEN an argument is a starred expression (`*args`) or double-starred expression (`**kwargs`), THE Call_Graph SHALL include the unpacked variable name in the arguments list without the star prefix.

### Requirement 6: Local Data Flow Analysis with Taint Tracking

**User Story:** As a developer, I want the Data_Flow_Analyzer to track tainted data from sources through local variable assignments and function parameters, so that security vulnerabilities from unsanitized input are detected.

#### Acceptance Criteria

1. WHEN a variable is assigned the return value of a function listed in the configured taint sources (e.g., `input()`, `request.args`, `request.form`, `sys.argv`), THE Data_Flow_Analyzer SHALL mark that variable as tainted and record a TaintSource with the function name, line number, and source type.
2. WHEN a tainted variable is passed as an argument to a function listed in the configured taint sinks (e.g., `exec()`, `eval()`, `cursor.execute()`), THE Data_Flow_Analyzer SHALL produce a TaintFinding containing the originating TaintSource, the matched TaintSink, a severity of "CRITICAL", and a message identifying the flow path from source type to sink type.
3. WHEN a tainted variable is assigned to another variable via direct assignment (e.g., `y = x`), THE Data_Flow_Analyzer SHALL propagate the taint to the new variable.
4. WHEN a tainted variable is used in a string operation (concatenation, f-string interpolation, or format call), THE Data_Flow_Analyzer SHALL propagate the taint to the resulting variable.
5. WHEN a tainted variable is passed as an argument at a call site within the same file, THE Data_Flow_Analyzer SHALL mark the corresponding function parameter as tainted for analysis of that function's body.
6. IF a tainted variable is passed as an argument to a function listed in the configured sanitizer functions, THEN THE Data_Flow_Analyzer SHALL remove the taint from the variable holding the return value of that sanitizer call.
7. IF the source code content cannot be parsed due to a syntax error, THEN THE Data_Flow_Analyzer SHALL return an empty list of findings without raising an exception.
8. THE Data_Flow_Analyzer SHALL complete analysis of a single file of up to 1000 lines within 200 milliseconds.

### Requirement 7: Syntax Highlighting for CLI Output

**User Story:** As a developer, I want code snippets in CLI review output to have syntax highlighting, so that findings are easier to read and understand in the terminal.

#### Acceptance Criteria

1. WHEN the Report_Generator produces CLI output containing code context, THE Report_Generator SHALL apply syntax highlighting using Pygments or equivalent token-based colorization.
2. WHEN the Report_Generator renders a code snippet in CLI output, THE Report_Generator SHALL detect the programming language based on the source file extension and apply language-appropriate token colorization, displaying the snippet with line numbers corresponding to the original file positions.
3. WHERE the terminal does not support ANSI colors as determined by the absence of a TTY (non-interactive output) or the presence of the NO_COLOR environment variable, THE Report_Generator SHALL fall back to plain text output without highlighting.
4. THE Report_Generator SHALL support at least Python, JavaScript, TypeScript, Go, Rust, and Java syntax highlighting.
5. IF the file extension is not recognized or no lexer is available for the detected language, THEN THE Report_Generator SHALL render the code snippet as plain text without highlighting and without producing an error.

### Requirement 8: HTML and JSON Export for Reports

**User Story:** As a developer, I want to export review reports in HTML and JSON formats, so that findings can be shared in web dashboards or consumed by other tools.

#### Acceptance Criteria

1. WHEN the user specifies `--format=html`, THE Report_Generator SHALL produce a single HTML file with all CSS and JavaScript embedded inline (no external resource dependencies), containing syntax-highlighted code snippets, severity badges, and navigation links to each finding.
2. WHEN the user specifies `--format=json`, THE Report_Generator SHALL produce a JSON document conforming to the structure defined in criterion 3, encoded as UTF-8, and parseable by any standard JSON parser.
3. THE JSON export SHALL include the following top-level fields: `findings` (array of objects each containing `file`, `line`, `rule_id`, `severity`, `message`, and `code_context`), `stats` (object with `files_analyzed`, `duration_seconds`, `total_findings`), and `metadata` (object with `timestamp` in ISO 8601 format, `version`, `project_name`).
4. THE HTML export SHALL include a summary table listing total findings per severity level, per-file findings sections with line numbers and rule IDs, and inline code diffs for findings that have a non-empty fix_template or LLM-generated fix suggestion.
5. IF the analysis produces zero findings, THEN THE Report_Generator SHALL produce a valid output file in the requested format containing an empty findings array (JSON) or a summary table showing zero counts (HTML).

### Requirement 9: Side-by-Side Diff Display

**User Story:** As a developer, I want to see side-by-side diffs of original and fixed code in review output, so that I can quickly understand what each fix changes.

#### Acceptance Criteria

1. WHEN a finding has both old_code and new_code available, THE Report_Generator SHALL display a side-by-side diff showing removed lines, added lines, and up to 3 unchanged context lines above and below each change, with line numbers displayed on each side.
2. THE side-by-side diff SHALL use color coding in terminal output: red background for removed lines, green background for added lines, and no background color for unchanged context lines.
3. WHEN the terminal width is less than 120 characters, THE Report_Generator SHALL fall back to a unified diff format preserving the same color coding and context lines.
4. THE HTML export SHALL render side-by-side diffs using a two-column layout with line numbers, red highlighting for removed lines, and green highlighting for added lines.
5. IF a finding has old_code but no new_code, or new_code but no old_code, THEN THE Report_Generator SHALL display only the available code block without diff formatting, labeled as "Original" or "Suggested Fix" respectively.
6. IF the diff between old_code and new_code exceeds 50 lines on either side, THEN THE Report_Generator SHALL truncate the display to the first 50 lines and append an indicator showing the total number of remaining lines.

### Requirement 10: CLI Autocomplete with prompt_toolkit

**User Story:** As a developer, I want the CLI to provide rich autocomplete with inline hints, dropdown suggestions, and fuzzy matching, so that command entry is fast and discoverable.

#### Acceptance Criteria

1. THE Autocomplete_Engine SHALL provide Tab completion for all registered slash commands, file paths, symbol names, and command flags.
2. WHEN the user types at least 1 character of a command, THE Autocomplete_Engine SHALL display a dropdown list of at most 15 matching completions with descriptions, ordered by prefix match first then by fuzzy match score descending.
3. THE Autocomplete_Engine SHALL support fuzzy matching so that non-contiguous character subsequences match commands (e.g., typing "rv" matches "/review" and "fx" matches "/fix").
4. WHEN the user types `@` followed by at least 1 character, THE Autocomplete_Engine SHALL suggest at most 15 matching file paths from the workspace using fuzzy search.
5. THE Autocomplete_Engine SHALL display inline hint text (grayed out) showing the highest-scored completion after the cursor, where score is determined by prefix match length then alphabetical order.
6. IF no completions match the user's input, THEN THE Autocomplete_Engine SHALL hide the dropdown and display no inline hint text.
7. WHEN the user triggers autocomplete, THE Autocomplete_Engine SHALL display suggestions within 100 milliseconds of the last keystroke.

### Requirement 11: Framework-Specific Rules for TypeScript and React

**User Story:** As a developer, I want the Rule_Engine to include at least 10 TypeScript/React-specific rules, so that common framework pitfalls are detected during review.

#### Acceptance Criteria

1. THE Rule_Engine SHALL include at least 10 rules targeting TypeScript and React code patterns, with a minimum of 5 React-specific rules and a minimum of 5 TypeScript-specific rules, each identified by a rule ID prefix ("REACT" for React rules, "TS" for TypeScript rules).
2. WHEN analyzing a `.tsx` or `.jsx` file, THE Rule_Engine SHALL apply React-specific rules detecting issues such as missing key props in lists, direct state mutation, missing dependency arrays in hooks, and unsafe dangerouslySetInnerHTML usage.
3. WHEN analyzing a `.ts` or `.tsx` file, THE Rule_Engine SHALL apply TypeScript-specific rules detecting issues such as `any` type usage, missing return types on exported functions, and non-null assertion usage exceeding 3 occurrences per file.
4. THE framework-specific rules SHALL each include a fix_template containing a syntactically valid code example that resolves the detected issue.
5. WHEN analyzing a `.tsx` file, THE Rule_Engine SHALL apply both React-specific rules and TypeScript-specific rules to the file.

### Requirement 12: Framework-Specific Rules for FastAPI and Django

**User Story:** As a developer, I want the Rule_Engine to include at least 10 FastAPI-specific and 10 Django-specific rules, so that backend framework security and performance issues are caught.

#### Acceptance Criteria

1. THE Rule_Engine SHALL include at least 10 rules targeting FastAPI code patterns covering: missing dependency injection, insecure CORS (allow_origins set to wildcard "*"), SQL injection via ORM, missing request validation, sync operations in async handlers, missing rate limiting, verbose error responses (stack traces or internal details exposed in non-debug mode), missing timeouts (HTTP client calls without explicit timeout parameter), debug mode enabled, and unsafe file uploads (no file size limit or content-type validation).
2. THE Rule_Engine SHALL include at least 10 rules targeting Django code patterns covering: raw SQL usage, XSS in templates, missing CSRF protection, debug mode in production, exposed secret keys (SECRET_KEY hardcoded in source files), unrestricted allowed hosts (ALLOWED_HOSTS containing wildcard "*"), missing permission checks, missing select_related/prefetch_related, missing transaction atomicity, and unfiltered QuerySet.all().
3. WHEN a FastAPI or Django rule produces a finding, THE Rule_Engine SHALL include the framework name in the rule ID prefix followed by a zero-padded 3-digit number (e.g., "FASTAPI001", "DJANGO001").
4. WHEN analyzing a Python file that imports from `fastapi` or its submodules, THE Rule_Engine SHALL apply all FastAPI-specific rules to that file.
5. WHEN analyzing a Python file that imports from `django` or its submodules, THE Rule_Engine SHALL apply all Django-specific rules to that file.
6. THE Rule_Engine SHALL include a fix_template with a corrected code example for each FastAPI-specific and Django-specific rule.

### Requirement 13: Real-Time Incremental Re-Analysis with File Watching

**User Story:** As a developer, I want the system to automatically re-analyze modified files in real-time using file system watching, so that review findings stay current without manual re-runs.

#### Acceptance Criteria

1. WHEN watch mode is enabled, THE Incremental_Indexer SHALL monitor the workspace for file creation, modification, and deletion events using watchdog, observing only files matching configured language extensions (e.g., `.py`, `.ts`, `.js`, `.go`, `.rs`, `.java`) and excluding paths matching ignore patterns (e.g., `.git`, `node_modules`, `__pycache__`, `venv`).
2. WHEN a file modification event is detected, THE Incremental_Indexer SHALL debounce events for a configurable duration (default 2 seconds, minimum 100 milliseconds, maximum 30 seconds) before triggering re-analysis, resetting the debounce timer on each subsequent event for the same file within the window.
3. WHEN re-analysis is triggered, THE Incremental_Indexer SHALL re-index only the modified file and any files that directly or transitively depend on it according to the import graph, up to a maximum of 50 dependent files per trigger.
4. IF a file is deleted, THEN THE Incremental_Indexer SHALL remove all findings, call sites, and function definitions associated with that file and trigger re-analysis of files that previously depended on the deleted file.
5. THE Incremental_Indexer SHALL emit typed events that the CLI can subscribe to, including: `analysis_started` (with file list), `analysis_completed` (with updated findings), and `analysis_failed` (with file path and error reason).
6. IF re-analysis fails for a file due to a parse error or unexpected exception, THEN THE Incremental_Indexer SHALL emit an `analysis_failed` event containing the file path and error reason, retain the previous findings for that file, and continue watching for subsequent events without interrupting the watch loop.

### Requirement 14: LLM-Powered Fix Suggestions

**User Story:** As a developer, I want the system to generate intelligent fix suggestions using an LLM when template-based fixes are insufficient, so that complex issues receive context-aware remediation advice.

#### Acceptance Criteria

1. WHEN a finding has no fix_template or the fix_template is marked as generic (empty string or placeholder text containing no language-specific code statements), THE LLM_Suggester SHALL generate a fix suggestion using the configured LLM provider, including the finding's rule_id, severity, message, file path, and surrounding code in the prompt.
2. THE LLM_Suggester SHALL support OpenAI API, local LLM (Ollama), and Anthropic as provider options, configurable via `configs/llm.yaml`.
3. IF the LLM provider is unavailable, returns an error, or does not respond within the configured timeout (default 30 seconds for cloud providers, 120 seconds for local providers), THEN THE LLM_Suggester SHALL fall back to the template-based fix without failing the review pipeline, retrying up to 3 attempts with exponential backoff before falling back.
4. THE LLM_Suggester SHALL include the surrounding code context (at least 5 lines above and below the finding, up to a maximum of 20 lines total as configured in `configs/llm.yaml`) in the prompt sent to the LLM.
5. WHEN the LLM returns a fix suggestion, THE LLM_Suggester SHALL validate that the suggested code is syntactically valid for the detected language by parsing it without errors.
6. IF the LLM-generated fix suggestion fails syntax validation, THEN THE LLM_Suggester SHALL discard the invalid suggestion and fall back to the template-based fix, logging the validation failure.
7. WHEN the LLM returns a valid fix suggestion, THE LLM_Suggester SHALL return a structured result containing the original code, suggested fix, explanation, confidence score (0.0 to 1.0), and the associated rule_id.

### Requirement 15: Plugin Discovery and Hot-Reload

**User Story:** As a developer, I want the Plugin_Manager to auto-discover plugins from a configured directory and support hot-reloading without restarting the application, so that plugin development iteration is fast.

#### Acceptance Criteria

1. WHEN the Plugin_Manager starts, THE Plugin_Manager SHALL scan the configured plugin directory for subdirectories containing a `plugin.json` or `manifest.json` manifest file and set each discovered plugin to the DISCOVERED state.
2. WHEN a plugin manifest is loaded, THE Plugin_Manager SHALL validate that the manifest contains all required fields (`name`, `version`, `description`, `entry_point`, `dependencies`, and `permissions`) and that `name` is a non-empty string, `version` matches semver format, and `entry_point` references an existing file within the plugin subdirectory.
3. IF a plugin manifest fails schema validation, THEN THE Plugin_Manager SHALL skip that plugin, set its state to ERROR, log an error message indicating the plugin name and the validation failure reason, and continue discovering remaining plugins.
4. WHEN a file with extension `.py` or `.json` within a loaded plugin's subdirectory is modified, created, or deleted while the Plugin_Manager is running, THE Plugin_Manager SHALL detect the change within 5 seconds and initiate a hot-reload of that plugin without requiring application restart.
5. WHEN a plugin is hot-reloaded, THE Plugin_Manager SHALL call `on_deactivate` on the old instance, unload the module from the Python module cache, reload the module from disk, create a new instance, and call `on_activate` on the new instance.
6. IF `on_deactivate` raises an exception during hot-reload, THEN THE Plugin_Manager SHALL log the exception, force-unload the old module, and proceed with loading the new version.
7. IF a plugin fails to load or activate, THEN THE Plugin_Manager SHALL log an error message indicating the plugin name and failure reason, set the plugin state to ERROR, and continue operating with remaining plugins without interruption.
8. WHEN a new plugin subdirectory containing a valid manifest is added to the configured plugin directory while the Plugin_Manager is running, THE Plugin_Manager SHALL discover and load the new plugin without requiring application restart.

### Requirement 16: Team Collaboration - Comments and Threads

**User Story:** As a team lead, I want reviewers to add comments and threaded discussions on findings, so that code review feedback is organized and traceable.

#### Acceptance Criteria

1. THE Collaboration_Engine SHALL allow users to create comments attached to a specific finding identified by file path, line number, and rule ID.
2. THE Collaboration_Engine SHALL support threaded replies on comments, maintaining parent-child relationships up to a maximum nesting depth of 10 levels.
3. WHEN a comment is created with a non-empty body of 1 to 10,000 characters, THE Collaboration_Engine SHALL record the author (1–128 characters), timestamp, and comment body.
4. WHEN a new thread is created, THE Collaboration_Engine SHALL assign an initial resolution state of "open", and support transitions to "resolved" and "wont_fix".
5. WHEN a thread is marked as "resolved" or "wont_fix", THE Collaboration_Engine SHALL record the resolver identity and the resolution timestamp.
6. IF a comment is submitted with an empty body or a body exceeding 10,000 characters, THEN THE Collaboration_Engine SHALL reject the comment and return an error message indicating the validation failure.
7. IF a thread is already in "resolved" or "wont_fix" state and a state change to the same state is requested, THEN THE Collaboration_Engine SHALL reject the transition and return an error message indicating the thread is already in that state.

### Requirement 17: PR Review Report Generation

**User Story:** As a team lead, I want to generate a PR review report summarizing all findings, comments, and resolution states, so that pull request reviews have a structured summary document.

#### Acceptance Criteria

1. WHEN the user invokes PR report generation, THE Collaboration_Engine SHALL produce a Markdown document containing: summary statistics (total findings count, counts per severity level, open thread count, resolved thread count, and files analyzed count), findings grouped by severity, open threads, and resolved threads.
2. THE PR review report SHALL include a table of contents with links to each section.
3. THE PR review report SHALL include per-file sections showing findings with their resolution status and any associated comments, ordered alphabetically by file path.
4. WHEN all critical and high-severity findings are resolved, THE PR review report SHALL display a "Ready to Merge" status indicator.
5. IF unresolved critical or high-severity findings exist, THEN THE PR review report SHALL display a "Blocking Issues" section listing each unresolved critical and high-severity finding with its file path, line number, and rule ID.
6. IF no findings exist for the PR, THEN THE Collaboration_Engine SHALL produce a report containing the summary statistics section with all counts at zero and a "Ready to Merge" status indicator.

### Requirement 18: Integration Test Coverage for New Modules

**User Story:** As a developer, I want integration tests covering the interactions between the Rule_Engine, Call_Graph, Data_Flow_Analyzer, and Incremental_Indexer, so that cross-module behavior is verified.

#### Acceptance Criteria

1. THE test suite SHALL include integration tests that exercise the Rule_Engine detecting findings in at least 3 sample files containing known vulnerabilities (at least one security, one code quality, and one performance issue) and assert that each expected finding is returned with correct rule ID, file path, and line number.
2. THE test suite SHALL include integration tests that build a Call_Graph from at least 3 files with cross-file function calls and verify that every expected caller/callee edge is present in the graph and no spurious edges exist for the sample inputs.
3. THE test suite SHALL include integration tests that run the Data_Flow_Analyzer on sample code containing at least 2 distinct taint paths from source to sink and verify that a TaintFinding is generated for each path with correct source location, sink location, and taint variable name.
4. THE test suite SHALL include integration tests that modify a previously indexed file, invoke incremental re-indexing, and verify that stale call sites from the old version are removed and new call sites from the modified version are present in the Call_Graph.
5. THE test suite SHALL include integration tests that verify the Plugin_Manager can discover, load, activate, and deactivate a test plugin, asserting that the plugin state transitions through DISCOVERED, LOADED, ACTIVE, and INACTIVE in sequence.
6. THE test suite SHALL include at least one end-to-end pipeline integration test that feeds a sample file through the Rule_Engine, Call_Graph, and Data_Flow_Analyzer in sequence and verifies that a taint finding detected via cross-file call graph resolution produces a valid TaintFinding.
7. IF a module raises an exception during a cross-module integration test, THEN THE test suite SHALL include at least one error-path test per module interaction that verifies the calling module handles the failure without crashing and produces a meaningful error indication.
8. THE test suite SHALL pass all integration tests (zero failures) when executed via `pytest tests/integration/` on a clean environment with no external service dependencies.

### Requirement 19: Performance Optimization for Large Codebases

**User Story:** As a developer working on large projects, I want the analysis pipeline to complete within acceptable time bounds, so that real-time feedback remains responsive.

#### Acceptance Criteria

1. WHEN analyzing a single file of up to 1000 lines, THE Rule_Engine SHALL complete detection within 500 milliseconds.
2. WHEN incrementally re-indexing a single modified file of up to 1000 lines, THE Call_Graph SHALL complete the update within 200 milliseconds.
3. WHEN a file of up to 1000 lines is saved, THE Incremental_Indexer SHALL process the file change event and display updated findings within 3 seconds from the file save timestamp.
4. WHEN analyzing a project with up to 500 files averaging up to 500 lines each, THE Rule_Engine SHALL complete a full scan within 60 seconds using concurrent file processing.
5. WHEN querying callers of a function via the reverse index, THE Call_Graph SHALL return results within 5 milliseconds regardless of the total number of indexed functions.
6. IF any analysis operation exceeds its specified time bound, THEN THE Rule_Engine SHALL terminate the operation, return partial results collected up to that point, and include a timeout indication in the output.

### Requirement 20: Evaluation Score Targets

**User Story:** As a project stakeholder, I want the upgraded system to achieve measurable quality targets across five evaluation areas, so that progress toward Cursor-like capabilities is quantifiable.

#### Acceptance Criteria

1. THE upgraded system SHALL achieve an overall weighted evaluation score of at least 95%, calculated as: (Area A score × 0.30) + (Area B score × 0.25) + (Area C score × 0.20) + (Area D score × 0.15) + (Area E score × 0.10), where the five areas are: A (Analysis Accuracy), B (Rule Completeness), C (Output Quality), D (CLI/UX Integration), and E (Extensibility).
2. THE upgraded system SHALL achieve at least 90% in each individual evaluation area (A through E), where each area is scored on a 0 to 100 scale.
3. WHEN evaluation is performed, THE system SHALL produce a score report containing: the numeric score (0-100) for each of the five areas, the weighted overall score, the list of modules evaluated per area, and a timestamp of the evaluation run.
4. IF any evaluation area scores below 90%, THEN THE score report SHALL list each sub-criterion that scored below its target within that area and provide at least one recommended improvement action per identified sub-criterion.
5. WHEN evaluation is performed, THE system SHALL score each area by assessing the corresponding system modules against the defined sub-criteria: Area A against detection precision and recall, Area B against rule count and category coverage, Area C against output format completeness and clarity metrics, Area D against command coverage and interaction features, and Area E against plugin lifecycle and extensibility mechanisms.
