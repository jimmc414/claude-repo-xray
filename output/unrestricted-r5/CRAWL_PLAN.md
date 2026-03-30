# Deep Crawl Plan: Kosmos

> Domain: Agent-based scientific research platform (CLI + multi-agent orchestration)
> Codebase: 802 files, ~2,455,608 tokens
> X-Ray scan: 2026-03-29T04:49:55Z
> Plan generated: 2026-03-29
> Git commit: 3ff33c3

## Subsystems

| # | Subsystem | Path | Files | Role |
|---|-----------|------|-------|------|
| 1 | agents | kosmos/agents/ | 8 | Core agent classes (research_director, experiment_designer, etc.) |
| 2 | core | kosmos/core/ | 20+ | Foundation (llm, logging, workflow, memory, cache, events) |
| 3 | cli | kosmos/cli/ | 10+ | Typer-based CLI with commands/ subpackage |
| 4 | execution | kosmos/execution/ | 5+ | Code generation and sandboxed execution |
| 5 | knowledge | kosmos/knowledge/ | 5+ | Vector DB (ChromaDB) and knowledge graph (Neo4j) |
| 6 | models | kosmos/models/ | 5+ | Data models (hypothesis, experiment, result) |
| 7 | safety | kosmos/safety/ | 3+ | Code validation and safety checks |
| 8 | literature | kosmos/literature/ | 5+ | Literature search clients (base_client) |
| 9 | world_model | kosmos/world_model/ | 5+ | World model storage (Neo4j-backed) |
| 10 | config | kosmos/config.py | 1 | Central configuration (highest churn: 0.96 risk) |
| 11 | evaluation | evaluation/ | 10+ | Scientific evaluation and persona testing |
| 12 | workflow | kosmos/workflow/ | 3+ | Research loop orchestration |
| 13 | orchestration | kosmos/orchestration/ | 3+ | Stage orchestration |
| 14 | scientific-skills | kosmos-claude-scientific-skills/ | 200+ | Scientific skill plugins (biomni, rdkit, etc.) |
| 15 | reference | kosmos-reference/ | 200+ | Reference implementations |

### Priority 1: Request Traces (5 tasks)

- [x] T01: CLI `kosmos run` → ResearchDirectorAgent → hypothesis generation → experiment design → execution → results (main research loop)
- [x] T02: CLI `kosmos config` → configuration loading → get_config() → provider selection chain
- [x] T03: `evaluation/scientific_evaluation.py:main()` → multi-phase scientific evaluation pipeline
- [x] T04: `evaluation/personas/run_persona_eval.py:main()` → persona-based evaluation flow
- [x] T05: E2E smoke test `.claude/skills/kosmos-e2e-testing/templates/smoke-test.py:main()` → test execution path

### Priority 2: High-Uncertainty Module Deep Reads (6 tasks)

- [x] T06: `kosmos/core/llm.py` — uncertainty: high churn (0.70 risk), 27 importers, LLM abstraction layer
- [x] T07: `kosmos/execution/executor.py` — uncertainty: high churn (0.70), sandboxed code execution
- [x] T08: `kosmos/execution/code_generator.py` — uncertainty: high churn (0.67), LLM-based code generation
- [x] T09: `kosmos/safety/code_validator.py` — uncertainty: safety-critical validation logic
- [x] T10: `kosmos/core/convergence.py` — uncertainty: convergence detection (stopping criteria)
- [x] T11: `kosmos/knowledge/vector_db.py` — uncertainty: ChromaDB integration, embedding storage

### Priority 3: Pillar Behavioral Summaries (6 tasks)

- [x] T12: `kosmos/core/logging.py` — pillar #1, 140 importers
- [x] T13: `kosmos/models/hypothesis.py` — pillar #2, 48 importers, core data model
- [x] T14: `kosmos/literature/base_client.py` — pillar #3, 35 importers, literature search abstraction
- [x] T15: `kosmos/models/experiment.py` — pillar #4, 30 importers + `kosmos/models/result.py` (27 importers)
- [x] T16: `kosmos/agents/research_director.py` — pillar #9, 22 importers, 0.83 risk, master orchestrator
- [x] T17: `kosmos/config.py` — 0.96 risk, highest churn, central configuration

### Priority 4: Cross-Cutting Concerns (5 tasks)

- [x] T18: Error handling strategy — exception patterns, retry logic, fallback behavior
- [x] T19: Configuration surface — env vars, config files, provider selection, feature flags
- [x] T20: LLM provider integration — Anthropic/OpenAI abstraction, client lifecycle, token management
- [x] T21: Database/storage patterns — Neo4j, ChromaDB, Redis, Postgres, Alembic migrations
- [x] T22: Agent communication — inter-agent messaging, event bus, shared state, orchestration

### Priority 5: Conventions and Patterns (2 tasks)

- [ ] T23: Dominant coding conventions — agent class pattern, config access, logging usage, test patterns
- [ ] T24: Convention deviations and coupling anomalies

### Priority 6: Gap Investigation (2 tasks)

- [ ] T25: Implicit initialization sequences and startup dependencies
- [ ] T26: Undocumented environment dependencies and hidden coupling

## Batching

| Batch | Tasks | Max Agents | Dependencies |
|-------|-------|------------|--------------|
| 1 | T01-T05 (P1) | 5 | None |
| 2 | T06-T17 (P2+P3) | 8 | None |
| 3 | T18-T22 (P4) | 5 | None |
| 4 | T23-T26 (P5+P6) | 4 | Batches 1-3 |

Batches 1-3 launch concurrently. Batch 4 waits for 1-3.

## Completion Criteria

All P1-P6 investigated + 10/10 standard questions answerable + coverage check passes:
- 50%+ subsystems (8/15) have at least one module deep-read
- Modules deep-read >= max(10, 802/40) = 20+
- All 5 entry point traces complete
- Every cross-cutting concern has examples from 3+ subsystems

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | 5 | 5 |
| 2 | 6 | 6 |
| 3 | 6 | 6 |
| 4 | 5 | 5 |
| 5 | 2 | 0 |
| 6 | 2 | 0 |

Last checkpoint: Batches 1-3 complete, Batch 4 in progress
