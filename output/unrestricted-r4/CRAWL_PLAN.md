# Deep Crawl Plan: Kosmos

> Domain: Agent-based Scientific Research Platform (hybrid: agent orchestration + CLI + API)
> Codebase: 802 files, ~2,455,608 tokens
> X-Ray scan: 2026-03-29T04:49:55
> Plan generated: 2026-03-29
> Git commit: (current HEAD)

### Priority 1: Request Traces (5 tasks)
<!-- Core workflows that reveal cross-module behavior -->
- [x] T1.1: CLI `run` command → ResearchDirectorAgent → research loop → experiment execution → results
- [x] T1.2: HypothesisGeneratorAgent.execute() → LLM call → literature search → hypothesis storage
- [x] T1.3: ExperimentDesignerAgent.execute() → template selection → LLM enhancement → protocol validation
- [x] T1.4: Executor.execute() → CodeGenerator → sandbox execution → result collection
- [x] T1.5: scientific_evaluation.py main() → phase1-6 evaluation pipeline

### Priority 2: High-Uncertainty Module Deep Reads (6 tasks)
<!-- Core modules where name/signature tells you nothing -->
- [x] T2.1: `kosmos/agents/base.py` — BaseAgent: foundation for all agents
- [x] T2.2: `kosmos/core/providers/base.py` — LLM provider abstraction
- [x] T2.3: `kosmos/config.py` — Configuration: risk 0.96, 27 churn, 18 hotfixes
- [x] T2.4: `kosmos/core/llm.py` — LLM client: circular dep with anthropic provider
- [x] T2.5: `kosmos/core/workflow.py` — Workflow states (26 importers)
- [x] T2.6: `kosmos/compression/compressor.py` — 3 compressor classes with untyped args

### Priority 3: Pillar Behavioral Summaries (8 tasks)
<!-- Most-imported modules — blast radius analysis -->
- [x] T3.1: `kosmos/core/logging.py` — 140 importers
- [x] T3.2: `kosmos/models/hypothesis.py` — 48 importers, Hypothesis data model
- [x] T3.3: `kosmos/literature/base_client.py` — 35 importers, literature search abstraction
- [x] T3.4: `kosmos/models/experiment.py` — 30 importers, ExperimentProtocol/Result models
- [x] T3.5: `kosmos/models/result.py` — 27 importers, Result data model
- [x] T3.6: `kosmos/agents/research_director.py` — 22 importers, master orchestrator (30K tokens)
- [x] T3.7: `kosmos/world_model/models.py` — 16 importers, world model entities
- [x] T3.8: `kosmos/__init__.py` — 25 importers, package initialization

### Priority 4: Cross-Cutting Concerns (6 tasks)
- [x] T4.1: Error handling strategy (exception patterns, retry, fallback)
- [x] T4.2: Configuration surface (env vars, config files, CLI args)
- [x] T4.3: LLM provider strategy (provider switching, model selection, fallback)
- [x] T4.4: Shared mutable state verification (module-level globals, singletons)
- [x] T4.5: Safety and code validation (sandbox, approval, risk assessment)
- [x] T4.6: Database and persistence (SQLAlchemy, ChromaDB, Neo4j, file-based)

### Priority 5: Conventions and Patterns (3 tasks)
- [x] T5.1: Agent implementation conventions (BaseAgent pattern, lifecycle hooks)
- [x] T5.2: Data model conventions (Pydantic vs dataclass, validation patterns)
- [x] T5.3: 6 coupling anomalies investigation + 36 convention deviations

### Priority 6: Gap Investigation (3 tasks)
- [x] T6.1: Initialization sequences (what must be called before what?)
- [x] T6.2: Undocumented environment dependencies (API keys, services)
- [x] T6.3: Reference code vs core (kosmos-reference/ and kosmos-claude-scientific-skills/)

## Completion Criteria
All P1-P6 investigated + 10/10 standard questions answerable + coverage check passes

## Context Management
Write findings to /tmp/deep_crawl/findings/{type}/ after each task.
Checkpoint this file every 5 tasks.

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | 5 | 5 |
| 2 | 6 | 6 |
| 3 | 8 | 8 |
| 4 | 6 | 6 |
| 5 | 3 | 3 |
| 6 | 3 | 3 |

Last checkpoint: 2026-03-29 start
