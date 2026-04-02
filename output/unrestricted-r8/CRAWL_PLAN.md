# Deep Crawl Plan: Kosmos

> Domain: Agent-based scientific research platform (hybrid: agents + CLI + workflow orchestration)
> Codebase: 802 files, ~2,455,608 tokens
> X-Ray scan: 2026-03-29T04:49:55Z
> Plan generated: 2026-03-29
> Git commit: 3ff33c3

### Priority 1: Request Traces (5 tasks)
- [ ] T1.1: `kosmos run` CLI → ResearchDirectorAgent → full research loop (est. 8+ module hops)
- [ ] T1.2: `scientific_evaluation.py:main()` → evaluation pipeline → report generation (est. 5 module hops)
- [ ] T1.3: `run_persona_eval.py:main()` → persona evaluation → comparison (est. 4 module hops)
- [ ] T1.4: Hypothesis generation → novelty check → literature search → storage (est. 6 module hops)
- [ ] T1.5: Code generation → sandbox execution → result analysis (est. 5 module hops)

### Priority 2: High-Uncertainty Module Deep Reads (10 tasks)
- [ ] T2.1: `kosmos/agents/base.py` — uncertainty 0.5: generic_name, low_type_coverage, high_fan_in
- [ ] T2.2: `kosmos/core/providers/base.py` — uncertainty 0.5: generic_name, low_type_coverage, high_fan_in
- [ ] T2.3: `kosmos/execution/executor.py` — hotspot risk 0.70, churn:12, hotfixes:8
- [ ] T2.4: `kosmos/execution/code_generator.py` — hotspot risk 0.67, churn:10, hotfixes:8
- [ ] T2.5: `kosmos/safety/code_validator.py` — core safety module
- [ ] T2.6: `kosmos/core/convergence.py` — core convergence detection
- [ ] T2.7: `kosmos/knowledge/vector_db.py` — knowledge storage core
- [ ] T2.8: `kosmos/knowledge/graph.py` — knowledge graph core
- [ ] T2.9: `kosmos/orchestration/` — stage_orchestrator.py and related
- [ ] T2.10: `kosmos/core/providers/anthropic.py` — hotspot risk 0.65, churn:9

### Priority 3: Pillar Behavioral Summaries (8 tasks)
- [ ] T3.1: `kosmos/core/logging.py` — pillar #1, 140 cross-module callers
- [ ] T3.2: `kosmos/models/hypothesis.py` — pillar #2, 48 cross-module callers
- [ ] T3.3: `kosmos/literature/base_client.py` — pillar #3, 35 cross-module callers
- [ ] T3.4: `kosmos/models/experiment.py` — pillar #4, 30 cross-module callers
- [ ] T3.5: `kosmos/core/llm.py` — pillar #5, 27 callers, hotspot risk 0.70
- [ ] T3.6: `kosmos/models/result.py` — pillar #6, 27 cross-module callers
- [ ] T3.7: `kosmos/core/workflow.py` — pillar #7, 26 cross-module callers
- [ ] T3.8: `kosmos/agents/research_director.py` — pillar #9, 22 callers, hotspot risk 0.83

### Priority 4: Cross-Cutting Concerns (6 tasks)
- [ ] T4.1: Error handling strategy (exception patterns, retry/backoff, swallowed exceptions)
- [ ] T4.2: Configuration surface (os.getenv, config[], KosmosConfig patterns)
- [ ] T4.3: LLM provider abstraction (anthropic, openai, litellm — how they're swapped)
- [ ] T4.4: Agent communication patterns (how agents coordinate, message passing, state sharing)
- [ ] T4.5: Database and storage patterns (SQLAlchemy, ChromaDB, Neo4j — lifecycle management)
- [ ] T4.6: Environment dependencies (all env vars needed to run)

### Priority 5: Conventions and Patterns (3 tasks)
- [ ] T5.1: Dominant coding conventions (class_init_typed_injection: 193 conforming, 36 deviations)
- [ ] T5.2: Agent pattern conventions (BaseAgent subclassing, execute() contract, lifecycle hooks)
- [ ] T5.3: Testing conventions (test structure, fixtures, mocking patterns)

### Priority 6: Gap Investigation (3 tasks)
- [ ] T6.1: Implicit initialization sequences (what must start before what)
- [ ] T6.2: Hidden coupling (6 coupling anomalies: config↔anthropic, research_director↔code_generator, etc.)
- [ ] T6.3: World model subsystem (Neo4j integration, entity management, factory patterns)

## Completion Criteria
All P1-P6 investigated + 10/10 standard questions answerable + coverage check passes (50%+ subsystems documented, modules deep-read >= max(10, 802/40)=20, all 10 entry points traced).

## Context Management
Write findings to /tmp/deep_crawl/findings/{type}/ after each task.
Checkpoint this file every 5 tasks.

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | 5 | 0 |
| 2 | 10 | 0 |
| 3 | 8 | 0 |
| 4 | 6 | 0 |
| 5 | 3 | 0 |
| 6 | 3 | 0 |

Last checkpoint: 2026-03-29 (initial)
