# Deep Crawl Plan: Kosmos

**Domain:** Autonomous AI Scientist / Multi-Domain Scientific Research Platform
**Detected Architecture:** Agent-based orchestration with workflow state machine, multi-provider LLM integration, knowledge graph persistence
**Files:** 802 Python files, ~284K lines, ~2.4M tokens
**Generated:** 2026-03-28

## Priority 1: Request Traces

- [x] T1: CLI `kosmos run` -> ResearchDirector -> full research cycle
- [x] T2: ResearchWorkflow.run() -> cycle execution -> validation
- [x] T3: LLM call path: get_client() -> provider selection -> API call -> cache

## Priority 2: High-Uncertainty Module Deep Reads

- [x] M1: BaseAgent (kosmos/agents/base.py) - agent base class
- [x] M2: LLMProvider base (kosmos/core/providers/base.py) - provider abstraction
- [x] M3: config.py - singleton config, all env vars
- [x] M4: Executor (kosmos/execution/executor.py) - code execution engine
- [x] M5: WorldModel (kosmos/world_model/) - knowledge graph persistence

## Priority 3: Pillar Behavioral Summaries

- [x] P1: core/logging.py (140 importers)
- [x] P2: models/hypothesis.py (48 importers)
- [x] P3: literature/base_client.py (35 importers)
- [x] P4: models/experiment.py (30 importers)
- [x] P5: core/llm.py (27 importers) - ClaudeClient + provider system
- [x] P6: core/workflow.py (26 importers) - state machine
- [x] P7: research_director.py (22 importers) - master orchestrator

## Priority 4: Cross-Cutting Concerns

- [x] C1: Singleton pattern (global state management)
- [x] C2: Error handling strategy
- [x] C3: LLM provider abstraction
- [x] C4: Config/env var management

## Priority 5: Conventions

- [x] D1: Testing conventions (pytest patterns)
- [x] D2: Agent implementation pattern
- [x] D3: Module structure conventions

## Status: COMPLETE
