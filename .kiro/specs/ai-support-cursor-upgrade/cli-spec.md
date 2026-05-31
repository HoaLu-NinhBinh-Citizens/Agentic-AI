# Kiro AI IDE — CLI Specification

## Command Structure

```bash
kiro [global-options] <command> [command-options]
```

## Global Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--config` | `-c` | Config file path | `~/.kiro/config.yaml` |
| `--verbose` | `-v` | Verbose output | `false` |
| `--quiet` | `-q` | Suppress output | `false` |
| `--version` | | Show version | |
| `--help` | `-h` | Show help | |

## Commands

### `analyze`

Analyze source code files.

```bash
kiro analyze [options] [paths...]
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--category`, `-C` | Filter by category | All |
| `--severity`, `-S` | Minimum severity | All |
| `--format`, `-F` | Output format | `cli` |
| `--output`, `-o` | Output file | stdout |
| `--incremental` | Incremental analysis | `false` |
| `--watch`, `-w` | Watch mode | `false` |

**Examples:**

```bash
kiro analyze src/
kiro analyze -C security -S HIGH src/
kiro analyze --format=html --output=report.html src/
kiro analyze --watch src/
```

### `rules`

Manage detection rules.

```bash
kiro rules <subcommand>
```

**Subcommands:**

- `kiro rules list` — List all rules
- `kiro rules info <rule-id>` — Show rule details
- `kiro rules validate` — Validate custom rules

**Examples:**

```bash
kiro rules list
kiro rules info SEC001
kiro rules validate --config=custom-rules.yaml
```

### `call-graph`

Analyze call relationships.

```bash
kiro call-graph <subcommand>
```

**Subcommands:**

- `kiro call-graph build [files]` — Build call graph
- `kiro call-graph callers <function>` — Find callers
- `kiro call-graph callees <file>` — Find callees
- `kiro call-graph visualize` — Generate graphviz output

**Examples:**

```bash
kiro call-graph build src/
kiro call-graph callers validate
kiro call-graph visualize --format=png > graph.png
```

### `dataflow`

Trace data flow and taint.

```bash
kiro dataflow [options] <file>
```

**Options:**

| Option | Description |
|--------|-------------|
| `--sources` | Comma-separated source functions |
| `--sinks` | Comma-separated sink functions |
| `--sanitizers` | Comma-separated sanitizer functions |

**Examples:**

```bash
kiro dataflow src/handler.py
kiro dataflow --sources=input,request.args src/handler.py
```

### `session`

Manage analysis sessions.

```bash
kiro session <subcommand>
```

**Subcommands:**

- `kiro session list` — List sessions
- `kiro session show <id>` — Show session details
- `kiro session delete <id>` — Delete session
- `kiro session export <id>` — Export session data

### `plugin`

Manage plugins.

```bash
kiro plugin <subcommand>
```

**Subcommands:**

- `kiro plugin list` — List plugins
- `kiro plugin install <path>` — Install plugin
- `kiro plugin uninstall <name>` — Uninstall plugin
- `kiro plugin reload <name>` — Hot-reload plugin
- `kiro plugin validate <path>` — Validate plugin manifest

### `report`

Generate reports.

```bash
kiro report [options] <session-id>
```

**Options:**

| Option | Description | Default |
|--------|-------------|---------|
| `--format`, `-F` | Report format | `markdown` |
| `--template` | Custom template | Built-in |
| `--include-comments` | Include review comments | `true` |

**Examples:**

```bash
kiro report sess_abc123
kiro report --format=html sess_abc123 > report.html
kiro report --format=json sess_abc123
```

### `comment`

Manage review comments.

```bash
kiro comment <subcommand>
```

**Subcommands:**

- `kiro comment add <file>:<line> <rule-id>` — Add comment
- `kiro comment list <file>` — List comments for file
- `kiro comment resolve <thread-id>` — Resolve thread

### `config`

Configuration management.

```bash
kiro config <subcommand>
```

**Subcommands:**

- `kiro config show` — Show current config
- `kiro config edit` — Edit config file
- `kiro config set <key> <value>` — Set config value
- `kiro config reset` — Reset to defaults

### `doctor`

Run diagnostics.

```bash
kiro doctor
```

Checks:
- Python version
- Required dependencies
- Config file validity
- LLM provider connectivity
- Plugin directory permissions

### `init`

Initialize new project.

```bash
kiro init [path]
```

Creates `.kiro/` directory with:
- `config.yaml` — Configuration
- `.kiroignore` — Ignore patterns
- `rules/` — Custom rules directory

## Interactive Mode

Enter interactive mode with:

```bash
kiro
```

Interactive commands:
- `help` — Show available commands
- `clear` — Clear screen
- `history` — Show command history
- `exit` / `quit` — Exit interactive mode

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Analysis error |
| 4 | Plugin error |
| 5 | LLM provider error |

## Configuration File

```yaml
# ~/.kiro/config.yaml

llm:
  provider: openai  # openai, anthropic, ollama
  model: gpt-4o
  api_key: ${OPENAI_API_KEY}
  timeout: 30

analysis:
  categories:
    - security
    - code_quality
    - type_safety
    - error_handling
    - performance
  exclude_patterns:
    - "*.test.py"
    - "**/__pycache__/**"
    - "**/node_modules/**"

plugins:
  directory: ~/.kiro/plugins
  hot_reload: true

output:
  format: cli
  color: true
  verbosity: normal

session:
  storage: ~/.kiro/sessions
  max_age_days: 30
```
