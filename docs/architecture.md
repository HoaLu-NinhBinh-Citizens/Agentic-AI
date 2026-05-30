# AI_SUPPORT Architecture

## Overview

AI_SUPPORT is a local embedded engineering intelligence system with Cursor-like code review capabilities.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI / TUI                                │
│                    (User Interface Layer)                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Conversation Layer                            │
│     (ConversationManager, SuggestionHandler)                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Application Layer                               │
│  ┌─────────────────┐  ┌──────────────────┐  ┌────────────────┐  │
│  │ Unified Review  │  │ Unified           │  │ Workflows     │  │
│  │ Engine          │  │ SuggestionEngine  │  │               │  │
│  └─────────────────┘  └──────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                            │
│  ┌──────────────┐ ┌────────────┐ ┌──────────┐ ┌───────────────┐ │
│  │ Indexing     │ │ Analysis   │ │ Reporting│ │ LLM          │ │
│  │ - SafeTree   │ │ - ML Rules │ │ - Markdown│ │ - Ollama     │ │
│  │ - Reference  │ │ - Security │ │ - JSON   │ │ - Prompts    │ │
│  │ - Dependency │ │ - Quality  │ │ - CLI    │ │              │ │
│  └──────────────┘ └────────────┘ └──────────┘ └───────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Layer                                    │
│  ┌──────────────┐ ┌────────────┐ ┌──────────────────────────┐  │
│  │ Fix Engine   │ │ LLM Fixes  │ │ Type Resolver            │  │
│  │ - Apply      │ │ - Generate │ │ - Import Tracker          │  │
│  │ - Preview    │ │ - Explain  │ │ - Semantic Resolver      │  │
│  │ - Rollback   │ │            │ │ - Call Graph Builder      │  │
│  └──────────────┘ └────────────┘ └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### Indexing (`src/infrastructure/indexing/`)

| Component | Purpose |
|-----------|---------|
| `SafeTreeSitterIndexer` | AST parsing with 14+ language support |
| `IncrementalIndexer` | Content-hash based incremental indexing |
| `ReferenceGraph` | Symbol definitions, references, call graph |
| `DependencyGraph` | Import/export tracking |

### Analysis (`src/infrastructure/analysis/`)

| Component | Purpose |
|-----------|---------|
| `RuleEngine` | 28 general-purpose rules |
| `MLRuleEngine` | 10 ML-specific rules |
| `MLDetectors` | AST-based ML bug detection |
| `TypeResolver` | Import alias resolution |
| `SemanticResolver` | Cross-file symbol resolution |

### Fix Engine (`src/core/fix_engine/`)

| Component | Purpose |
|-----------|---------|
| `ApplyFixTool` | Apply fixes with backup/rollback |
| `FixBatch` | Batch fix operations |

### LLM Integration (`src/infrastructure/llm/`)

| Component | Purpose |
|-----------|---------|
| `LocalLLMProvider` | Ollama API integration |
| `LLMManager` | Multi-provider management |
| `LLMFixEngine` | LLM-powered fix generation |

## Data Flow

1. **Input**: User runs `/review [files]`
2. **Indexing**: SafeTreeSitterIndexer parses AST
3. **Analysis**: Detectors run against CodeContext
4. **Findings**: Results collected and deduplicated
5. **Suggestions**: Fix options generated
6. **Output**: Markdown/JSON/CLI report

## Configuration

See `docs/CONFIGURATION.md`
