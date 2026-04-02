# Deep Crawl Plan: Kosmos

> Domain Facets: async_service, web_api, cli_tool, scientific_computation
> Codebase: 802 files, ~2,455,608 tokens
> X-Ray scan: 2026-04-02T20:31:46Z
> Plan generated: 2026-04-02
> Git commit: 3ff33c376c
> Root path: /mnt/c/python/Kosmos

### Priority 1: Request Traces (5 tasks)
<!-- Note: hop counts are module-level estimates from xray.
The crawl agent traces at function level; actual depth may differ. -->
- [x] P1.1 `cli_entrypoint` → CLI main → research_director → agent pipeline → LLM → results (est. 6+ hops)
- [x] P1.2 FastAPI `api/health.py` → service health checks → db/redis/neo4j connectivity (est. 3 hops)
- [x] P1.3 Experiment execution: `experiment_designer` → `executor.py` → `sandbox.py` → code execution → provenance (est. 5 hops)
- [x] P1.4 Literature pipeline: `arxiv_http_client` → `pdf_extractor` → `reference_manager` → knowledge graph (est. 4 hops)
- [x] P1.5 API websocket: `api/websocket.py` → streaming → agent events → client (est. 3 hops)

### Priority 2: High-Uncertainty Module Deep Reads (2 tasks)
- [x] P2.1 `kosmos/agents/base.py` — uncertainty 0.5: generic_name, low_type_coverage, high_fan_in (6)
- [x] P2.2 `kosmos/core/providers/base.py` — uncertainty 0.5: generic_name, low_type_coverage, high_fan_in (6)

### Priority 3: Pillar Behavioral Summaries (18 tasks)
- [x] P3.1 `kosmos/core/logging.py` — pillar #1, 141 connections
- [x] P3.2 `kosmos/config.py` — pillar #2, 54 connections
- [x] P3.3 `kosmos/agents/research_director.py` — pillar #3, 50 connections
- [x] P3.4 `kosmos/models/hypothesis.py` — pillar #4, 49 connections
- [x] P3.5 `kosmos/literature/base_client.py` — pillar #5, 36 connections
- [x] P3.6 `kosmos/core/llm.py` — pillar #6, 35 connections
- [x] P3.7 `kosmos/models/experiment.py` — pillar #7, 33 connections
- [x] P3.8 `kosmos/core/workflow.py` — pillar #8, 28 connections
- [x] P3.9 `kosmos/models/result.py` — pillar #9, 28 connections
- [x] P3.10 `kosmos/db/__init__.py` + `kosmos/db/operations.py` — pillar #10, 14 connections
- [x] P3.11 `kosmos/execution/executor.py` — high complexity (cc=15 for validate), 7 cross-module callers
- [x] P3.12 `kosmos/knowledge/graph.py` — 16 DB side effects, knowledge graph core
- [x] P3.13 `kosmos/world_model/simple.py` — 27 side effects, world model core
- [x] P3.14 `kosmos/safety/guardrails.py` — 3 side effects, safety-critical
- [x] P3.15 `kosmos/orchestration/plan_reviewer.py` — orchestration review logic
- [x] P3.16 `kosmos/core/experiment_cache.py` — 22 side effects, caching layer
- [x] P3.17 `kosmos/monitoring/alerts.py` — 4 side effects, PagerDuty/Slack/SMTP
- [x] P3.18 `kosmos/cli/main.py` — CLI entry point, register_commands, doctor

### Priority 4: Cross-Cutting Concerns (10 tasks)
- [x] P4.1 Error handling strategy — Protocol C
- [x] P4.2 Configuration surface — Protocol C
- [x] P4.3 Shared mutable state verification — Protocol C
- [x] P4.4 Exception taxonomy — Protocol C targeting all custom exception classes
- [x] P4.5 Agent communication patterns — Protocol C (how agents coordinate)
- [x] P4.6 Async/sync boundary patterns — Protocol C (asyncio.run, loop.run_until_complete, sync→async transitions)
- [x] P4.7 Database session lifecycle — Protocol C (per-request? connection pool? ORM patterns)
- [x] P4.8 LLM provider abstraction — Protocol C (provider switching, model selection, retry/fallback)
- [x] P4.9 Environment dependencies — Protocol C (os.getenv, os.environ usage)
- [x] P4.10 Initialization sequences — Protocol C (startup ordering, service dependencies)

### Priority 5: Conventions and Patterns (3 tasks)
- [x] P5.1 Dominant coding conventions — Protocol D
- [x] P5.2 Testing patterns — Protocol D (fixture patterns, mocking strategies, 202 test files)
- [x] P5.3 Domain module conventions — Protocol D (how domains are structured: biology, chemistry, materials, neuroscience, physics)

### Priority 6: Gap Investigation (3 tasks)
- [x] P6.1 Implicit initialization sequences (startup ordering, service bootstrap)
- [x] P6.2 Hidden coupling not captured by imports (runtime dispatch, dynamic loading)
- [x] P6.3 Security boundaries (exec in executor.py, sandbox isolation, API key handling)

### Priority 7: Change Impact Analysis (5 tasks)
- [x] P7.1 Hub cluster: core modules (logging, config, llm, workflow) — Protocol E
- [x] P7.2 Hub cluster: model layer (hypothesis, experiment, result) — Protocol E
- [x] P7.3 Hub cluster: agents + orchestration (research_director, base, plan_reviewer) — Protocol E
- [x] P7.4 Change scenario: Add new agent type with custom behavior — Protocol F
- [x] P7.5 Change scenario: Add new scientific domain — Protocol F

## Completion Criteria
All P1-P7 investigated + 12/12 standard questions answerable + coverage check passes (50%+ subsystems documented, modules deep-read >= 20, all entry points traced, hub module coverage).

## Context Management
Write findings to /tmp/deep_crawl/findings/{type}/ after each task.
Checkpoint this file every 5 tasks.

## Progress

| Priority | Total | Done |
|----------|-------|------|
| 1 | 5 | 0 |
| 2 | 2 | 0 |
| 3 | 18 | 0 |
| 4 | 10 | 0 |
| 5 | 3 | 0 |
| 6 | 3 | 0 |
| 7 | 5 | 0 |

Last checkpoint: 2026-04-02
