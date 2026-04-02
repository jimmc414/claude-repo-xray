# Deep Crawl Plan: Kosmos

> Domain: Agent-based autonomous scientific research platform (hybrid: agent framework + CLI + ML pipeline)
> Codebase: 802 files, ~2,455,608 tokens
> X-Ray scan: 2026-03-29T06:00:03Z
> Plan generated: 2026-03-29
> Git commit: 3ff33c3

### Priority 1: Request Traces (5 tasks)
<!-- Main execution paths through the system -->
- [ ] CLI `run` command → ResearchDirectorAgent → agent loop → execution → results (est. 8+ module hops)
- [ ] scientific_evaluation.py:main() → multi-phase evaluation pipeline (est. 5 module hops)
- [ ] CLI hypothesis/experiment/literature commands → individual agent execution (est. 4 module hops)
- [ ] smoke-test.py:main() → db validation path (est. 2 module hops)
- [ ] run_persona_eval.py:main() → subprocess evaluation (est. 3 module hops)

### Priority 2: High-Uncertainty Module Deep Reads (8 tasks)
- [ ] `kosmos/agents/base.py` — uncertainty 0.5: generic_name, low_type_coverage, high_fan_in
- [ ] `kosmos/core/providers/base.py` — uncertainty 0.5: generic_name, low_type_coverage, high_fan_in
- [ ] `kosmos/config.py` — risk 0.96, 27 churn, 18 hotfixes, central config
- [ ] `kosmos/core/llm.py` — 27 importers, circular dep with anthropic provider
- [ ] `kosmos/execution/executor.py` — risk 0.70, code execution sandbox
- [ ] `kosmos/execution/code_generator.py` — risk 0.67, LLM-generated code
- [ ] `kosmos/compression/compressor.py` — convention deviation (untyped_args)
- [ ] `kosmos/world_model/simple.py` — Neo4j world model, 10K tokens

### Priority 3: Pillar Behavioral Summaries (10 tasks)
- [ ] `kosmos/core/logging.py` — pillar #1, 140 cross-module importers
- [ ] `kosmos/models/hypothesis.py` — pillar #2, 48 importers
- [ ] `kosmos/literature/base_client.py` — pillar #3, 35 importers
- [ ] `kosmos/models/experiment.py` — pillar #4, 30 importers
- [ ] `kosmos/models/result.py` — pillar #6, 27 importers
- [ ] `kosmos/core/workflow.py` — pillar #7, 26 importers
- [ ] `kosmos/agents/research_director.py` — pillar #9, 22 importers, master orchestrator
- [ ] `kosmos/knowledge/graph.py` — knowledge graph integration
- [ ] `kosmos/knowledge/vector_db.py` — vector database integration
- [ ] `kosmos/world_model/factory.py` — world model factory

### Priority 4: Cross-Cutting Concerns (5 tasks)
- [ ] Error handling strategy (except patterns, retry, backoff)
- [ ] Configuration surface (os.getenv, config[], env vars)
- [ ] Shared mutable state verification (globals, singletons, caches)
- [ ] LLM provider abstraction (anthropic vs openai, model selection, token management)
- [ ] Agent lifecycle (BaseAgent subclass pattern, start/stop/execute)

### Priority 5: Conventions and Patterns (3 tasks)
- [ ] Dominant coding conventions (typing, DI, naming)
- [ ] 36 convention deviations (untyped_args pattern)
- [ ] 6 coupling anomalies (co-modification without imports)

### Priority 6: Gap Investigation (3 tasks)
- [ ] Implicit initialization sequences (config loading, DB connections, world model setup)
- [ ] Undocumented environment dependencies (54 env side effects)
- [ ] Hidden coupling: circular deps (llm↔anthropic, world_model↔artifacts)

## Completion Criteria
All P1-P6 investigated + 10/10 standard questions answerable + coverage check passes (50%+ subsystems documented, modules deep-read >= 20, all entry points traced).

## Coverage Targets
- Subsystems: 20+ subsystem directories under kosmos/
- Module deep-reads needed: >= max(10, 802/40) = 20
- Request traces: >= 5 core paths (10 xray entry points, many are tool scripts)
- Cross-cutting examples: >= 3 subsystems each

## Context Management
Write findings to /tmp/deep_crawl/findings/{type}/ after each task.
Checkpoint this file every 5 tasks.

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | 5 | 0 |
| 2 | 8 | 0 |
| 3 | 10 | 0 |
| 4 | 5 | 0 |
| 5 | 3 | 0 |
| 6 | 3 | 0 |

Last checkpoint: 2026-03-29 Phase 1 complete
