# Kosmos: Deep Onboarding Document

> Generated: 2026-03-29 | Files: 802 analyzed (1520 total) | ~2.5M tokens
> For xray structural output: /tmp/xray/xray.md and /tmp/xray/xray.json

## Identity

Kosmos is an autonomous AI scientist that runs research cycles: generate hypotheses from literature, design experiments, execute code in sandboxed containers, analyze results, and iterate until convergence. Implements the architecture from Lu et al. (2024). Written in Python 3.11+, uses Claude/OpenAI/LiteLLM for LLM calls, SQLite for persistence, Neo4j for knowledge graphs, ChromaDB for vector search.

## Architecture

```
CLI (typer)                  Programmatic API
  │                              │
  ▼                              ▼
cli/commands/run.py        workflow/research_loop.py
  │                              │
  ▼                              ▼
ResearchDirectorAgent      ResearchWorkflow
(state machine)            (gap-based orchestration)
  │
  ├─ HypothesisGeneratorAgent ──► LLM + Literature Search ──► DB
  ├─ ExperimentDesignerAgent  ──► LLM + Templates ──► DB
  ├─ CodeExecutor/Sandbox     ──► Docker or restricted exec()
  ├─ DataAnalystAgent         ──► LLM interpretation ──► DB
  ├─ ConvergenceDetector      ──► Stopping criteria check
  └─ World Model              ──► Neo4j knowledge graph
```

**Two orchestration paths exist:** [FACT: both at workflow/research_loop.py and agents/research_director.py]
1. **CLI path** (primary, actively maintained): `kosmos run` → `ResearchDirectorAgent` — state machine with direct agent calls (research_director.py, 2900+ lines, risk score 0.83)
2. **API path**: `ResearchWorkflow.run()` — gap-based architecture with plan/review/delegate pattern (research_loop.py)

Both paths are complete but use different coordination strategies. The CLI path is the one that gets tested and modified most.

## Critical Path: `kosmos run` Research Cycle

```
kosmos run "question" --domain biology
  ├─ run_research() (cli/commands/run.py:51)
  │   ├─ get_config() → KosmosConfig singleton (config.py)
  │   ├─ Flattens nested config to flat dict (run.py:148-170) ← GOTCHA
  │   └─ ResearchDirectorAgent(question, domain, flat_config)
  │       ├─ _validate_domain() — warns if domain not in enabled list
  │       ├─ _load_skills() — domain-specific prompt injection
  │       ├─ get_client() → LLM provider singleton (core/llm.py:613)
  │       ├─ init_from_config() → SQLite init (db/__init__.py)
  │       ├─ ConvergenceDetector(criteria) (core/convergence.py)
  │       └─ get_world_model() → Neo4j or None (world_model/)
  │
  ├─ asyncio.run(run_with_progress_async(director))
  │   ├─ director.execute({"action": "start_research"})
  │   │   └─ _on_start() → WorkflowState.GENERATING_HYPOTHESES
  │   │
  │   └─ LOOP while iteration < max_iterations:
  │       ├─ director.execute({"action": "step"})
  │       │   ├─ decide_next_action() (research_director.py:2388)
  │       │   │   ├─ Budget check → Runtime check → Loop guard
  │       │   │   └─ State-based decision tree → NextAction enum
  │       │   └─ _do_execute_action(action) dispatches to:
  │       │       ├─ GENERATE_HYPOTHESIS → HypothesisGeneratorAgent
  │       │       │   ├─ literature search (PubMed, arXiv, Semantic Scholar)
  │       │       │   ├─ LLM call with HYPOTHESIS_GENERATOR prompt
  │       │       │   ├─ novelty check (min_novelty_score=0.5)
  │       │       │   └─ store in DB + knowledge graph
  │       │       ├─ DESIGN_EXPERIMENT → ExperimentDesignerAgent
  │       │       │   ├─ template matching or LLM-based design
  │       │       │   └─ store protocol in DB + graph
  │       │       ├─ EXECUTE_EXPERIMENT → CodeGenerator + CodeExecutor
  │       │       │   ├─ generate Python/R code from protocol
  │       │       │   ├─ validate via CodeValidator (AST safety check)
  │       │       │   └─ execute in Docker sandbox or restricted exec()
  │       │       ├─ ANALYZE_RESULT → DataAnalystAgent
  │       │       │   ├─ LLM interpretation of results
  │       │       │   └─ marks hypothesis SUPPORTED/REJECTED
  │       │       ├─ REFINE_HYPOTHESIS → generate refined hypotheses
  │       │       └─ CONVERGE → ConvergenceDetector.evaluate()
  │       └─ check convergence, update progress bars
  │
  └─ ResultsViewer.display_*() — Rich output
```

## Workflow State Machine

[FACT: core/workflow.py:18]

```
INITIALIZING → GENERATING_HYPOTHESES → DESIGNING_EXPERIMENTS → EXECUTING
    → ANALYZING → REFINING → (loop back to GENERATING or CONVERGED)
```

Additional states: PAUSED, ERROR

**Stopping criteria** (core/convergence.py):
- Mandatory: iteration_limit, no_testable_hypotheses
- Optional: novelty_decline, diminishing_returns, all_hypotheses_tested
- Budget enforcement: halts if RESEARCH_BUDGET_USD exceeded [FACT: research_director.py:2404-2422]
- Runtime limit: max_runtime_hours default 12.0 [FACT: config.py:238]
- Loop guard: MAX_ACTIONS_PER_ITERATION=50 forces convergence [FACT: research_director.py:50]

## Module Behavioral Index

### Agents (kosmos/agents/)

| Module | Behavior | Key Detail |
|--------|----------|------------|
| base.py | BaseAgent: lifecycle, async messaging, state persistence | execute() is sync on base, async on ResearchDirector [FACT] |
| research_director.py | Master orchestrator, 2900+ lines, coordinates all agents | Circuit breaker: 3 errors → ERROR state [FACT: line 44] |
| hypothesis_generator.py | Generates hypotheses via LLM with literature context | Default num_hypotheses=3, min_novelty_score=0.5 [FACT: line 79-83] |
| experiment_designer.py | Designs experiments from templates or LLM | Co-modified with research_director (coupling 0.8) [PATTERN] |
| data_analyst.py | LLM-based result interpretation | significance thresholds: strict and relaxed [FACT] |
| literature_analyzer.py | Literature analysis with knowledge graph integration | 17 except Exception blocks (highest count) [FACT: grep count] |
| skill_loader.py | Loads domain-specific skills for prompt injection | load_from_github() has CC:36 [FACT: xray] |
| registry.py | Agent registry for message routing | Simple dict-based lookup |

### Core (kosmos/core/)

| Module | Behavior | Key Detail |
|--------|----------|------------|
| llm.py | Multi-provider LLM client singleton | 3-layer fallback: provider system → AnthropicProvider → ClaudeClient [FACT: line 652-663] |
| workflow.py | Workflow state machine (9 states, 8 actions) | ResearchPlan tracks all hypothesis/experiment/result IDs [FACT] |
| convergence.py | Stopping criteria evaluation | Mandatory + optional criteria with numpy for metric computation |
| logging.py | Structured JSON/text logging, 140 importers | ContextVar-based correlation_id [FACT: line 23] |
| providers/factory.py | Provider registry and factory | Auto-registers at import: anthropic, openai, litellm + aliases [FACT] |
| providers/anthropic.py | Anthropic Claude API implementation | Co-modified with config.py (coupling 1.0) [FACT] |
| prompts.py | System prompt templates for all agents | HYPOTHESIS_GENERATOR, EXPERIMENT_DESIGNER, etc. |
| claude_cache.py | SQLite response cache | Cache key: prompt + model + system + max_tokens + temperature |
| event_bus.py | Event publishing for streaming display | Async event bus for real-time UI updates |

### Execution (kosmos/execution/)

| Module | Behavior | Key Detail |
|--------|----------|------------|
| executor.py | Code execution with Docker sandbox or restricted exec() | SAFE_BUILTINS whitelist (line 43), _ALLOWED_MODULES (line 86) [FACT] |
| sandbox.py | Docker container isolation | Defaults: 2 CPU, 2GB RAM, 300s timeout, network off [FACT: line 81-84] |
| code_generator.py | Generates Python code from experiment protocols | Template-based + LLM-based + hybrid approach [FACT: docstring] |
| data_provider.py | Provides datasets to experiments | Handles CSV loading and synthetic data generation |
| r_executor.py | R language execution support | Auto-detected, Docker image "kosmos-sandbox-r:latest" [FACT] |

### Data Layer

| Module | Behavior | Key Detail |
|--------|----------|------------|
| config.py | Pydantic-settings config, 12+ sections, risk 0.96 | 50 env vars across 11 files [FACT: grep count] |
| db/__init__.py | SQLAlchemy + SQLite, session context manager | Slow query logging at 100ms threshold [FACT: line 33] |
| knowledge/graph.py | Neo4j via py2neo, auto-starts Docker | Degrades gracefully if unavailable [FACT: research_director.py:252] |
| knowledge/vector_db.py | ChromaDB PersistentClient | Optional: HAS_CHROMADB flag [FACT: line 19-27] |
| models/hypothesis.py | Hypothesis Pydantic model, 48 importers | Statement validator rejects questions (no trailing ?) [FACT: line 94] |
| models/experiment.py | ExperimentProtocol model, 30 importers | Includes ProtocolStep, StatisticalTest, Variable definitions |
| models/result.py | ExperimentResult model, 27 importers | Links to hypothesis and protocol via IDs |
| literature/base_client.py | ABC for literature APIs, 35 importers | PaperMetadata dataclass: unified cross-source format [FACT] |

## Gotchas and Hazards

### Tier 1: Could Cause Bugs, Security Issues, or Crashes

1. **SECURITY: Non-Docker execution is not fully sandboxed** — When Docker is unavailable, CodeExecutor falls back to exec() with restricted builtins and import whitelist. This runs in-process and a crafted payload could escape the restrictions. [FACT: executor.py:215-221, SAFE_BUILTINS at line 43]

2. **BUG RISK: Flat config translation is manual** — cli/commands/run.py:148-170 manually maps nested KosmosConfig to flat dict keys for agents. If new config fields are added to KosmosConfig without updating this mapping, agents silently use default values instead of configured ones. [FACT: run.py:148-170]

3. **BUG RISK: Dual message queues** — BaseAgent stores messages in both `message_queue` (List, legacy sync) and `_async_message_queue` (asyncio.Queue). If code reads from the wrong queue, messages appear lost. [FACT: base.py:136-137]

4. **BUG RISK: Async/sync execute() mismatch** — BaseAgent.execute() is sync (returns Dict). ResearchDirectorAgent.execute() is async (returns Coroutine). Code that calls execute() on a generic BaseAgent reference may not await correctly. [FACT: base.py:485, research_director.py:2868]

5. **CRASH RISK: Database not initialized** — get_session() raises RuntimeError if init_database() hasn't been called. Any code path that uses DB before ResearchDirectorAgent.__init__ (which calls init_from_config()) will crash. [FACT: db/__init__.py:127]

### Tier 2: Non-obvious Behaviors, Side Effects, Gotchas

6. **CLI mode detection via API key** — If ANTHROPIC_API_KEY is all-9s (e.g., "999999999..."), ClaudeClient routes to Claude Code CLI instead of the Anthropic API. This is intentional but undocumented in config validation. [FACT: llm.py:179]

7. **Provider fallback cascade is silent** — get_client() tries: (1) provider system via config, (2) AnthropicProvider directly, (3) legacy ClaudeClient. Each failure is logged as warning but execution continues. A misconfigured provider silently falls back to a different one. [FACT: llm.py:652-663]

8. **Auto model selection by keyword** — ModelComplexity.estimate_complexity() routes simple queries to Haiku and complex ones to Sonnet based on keyword matching (20 keywords like "analyze", "research", "hypothesis"). This means prompt wording affects which model is used and therefore cost. [FACT: llm.py:45-50]

9. **first_time_setup creates files** — init_from_config() calls first_time_setup() which creates .env file if missing and runs Alembic migrations. First run may create files in project root unexpectedly. [FACT: db/__init__.py:170, utils/setup.py]

10. **Neo4j auto-starts Docker** — KnowledgeGraph.__init__() with auto_start_container=True (default) will attempt to start a Docker container if Neo4j is not running. This is a side effect of import/initialization. [FACT: knowledge/graph.py:75-76]

11. **Circuit breaker with time.sleep** — ResearchDirectorAgent error recovery uses time.sleep() for exponential backoff [2,4,8]s inside an async context. This blocks the event loop. [FACT: research_director.py:674]

12. **MAX_ACTIONS_PER_ITERATION=50** — Loop guard in decide_next_action(). If exceeded, forces convergence. Counter uses hasattr/dynamic attribute, not initialized in __init__. [FACT: research_director.py:50, 2451-2452]

13. **Hypothesis statement validator** — Hypothesis.statement cannot end with "?". Validates for predictive words but only warns (doesn't reject) if missing. [FACT: models/hypothesis.py:86-99]

14. **Two orchestration paths** — ResearchDirectorAgent (CLI) and ResearchWorkflow (API) are separate systems that can produce different results for the same question. They are not interchangeable. [FACT: research_director.py vs workflow/research_loop.py]

## Configuration Reference

### Required Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| ANTHROPIC_API_KEY | LLM provider auth | None (required if using Anthropic) |

### Key Optional Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| CLAUDE_MODEL | Model name | "claude-sonnet-4-5" |
| CLAUDE_MAX_TOKENS | Max response tokens | 4096 |
| CLAUDE_TEMPERATURE | Sampling temp | 0.7 |
| DATABASE_URL | SQLite/PostgreSQL URL | "sqlite:///kosmos.db" |
| MAX_RESEARCH_ITERATIONS | Research iteration cap | 10 |
| RESEARCH_BUDGET_USD | API cost budget | 10.0 |
| MAX_RUNTIME_HOURS | Runtime limit | 12.0 |
| ENABLE_SANDBOXING | Docker sandbox for code exec | True |
| ENABLE_SAFETY_CHECKS | Code safety validation | True |
| NEO4J_URI | Knowledge graph connection | "bolt://localhost:7687" |
| REDIS_ENABLED | Redis caching | False |
| LOG_LEVEL | Logging verbosity | "INFO" |
| LLM_PROVIDER | Provider selection | "anthropic" |

Config loaded via: `.env` file → environment variables → Pydantic defaults.
Config object: `get_config()` returns singleton `KosmosConfig` (config.py).

## Error Handling Strategy

[PATTERN: 205 except Exception blocks across 50 files]

| Layer | Strategy | Detail |
|-------|----------|--------|
| ResearchDirector | Circuit breaker | 3 consecutive errors → ERROR state, exponential backoff [2,4,8]s [FACT: research_director.py:44-46] |
| Code Execution | Self-correcting retry | Sends error to LLM for code fix, retries up to 3x [FACT: executor.py, Issue #54] |
| Literature APIs | Retry with backoff | Exponential backoff for HTTP errors (arxiv_client: 23 retry occurrences) [FACT] |
| Database | Session rollback | Context manager: commit on success, rollback on exception [FACT: db/__init__.py:133] |
| Optional deps | Graceful degradation | try import / HAS_X flag / fallback for chromadb, docker, neo4j, litellm [PATTERN: 5/5 optional deps] |

No swallowed exceptions (except...pass) found in kosmos/ directory. [ABSENCE: grep returned 0 hits]

## Shared State and Singletons

| Singleton | Location | Thread Safety |
|-----------|----------|---------------|
| _config | config.py:get_config() | Global variable, simple assignment |
| _default_client | core/llm.py:get_client() | threading.Lock with double-check [FACT: line 646] |
| _engine, _SessionLocal | db/__init__.py | Global variables |
| _world_model | world_model/factory.py | Global variable |
| _PROVIDER_REGISTRY | core/providers/factory.py | Dict, populated at import time |
| _metrics_collector | monitoring/metrics.py | Global with singleton getter |

## Conventions

1. **Always** inherit from BaseAgent for new agents. Call super().__init__(agent_id, agent_type, config). Extract config in __init__ via self.config.get(). [PATTERN: 6/6 agents]
2. **Always** use `logger = logging.getLogger(__name__)` at module level. [PATTERN: all modules]
3. **Always** use Google-style docstrings with Args/Returns. [PATTERN: 8/10 top files]
4. **Always** handle optional dependencies with try/import/HAS_X flag pattern. [PATTERN: 5/5 optional deps]
5. **Never** add sync time.sleep() in async code paths. The research director already has this bug (line 674). [FACT]
6. **Never** assume Docker is available. Always check SANDBOX_AVAILABLE or handle ImportError. [PATTERN]
7. **When** adding new config fields: update both KosmosConfig AND the flat_config mapping in cli/commands/run.py:148-170. [FACT: see Gotcha #2]
8. **When** adding new LLM providers: register in core/providers/factory.py:_register_builtin_providers() AND add config section to config.py. [PATTERN: 3/3 existing providers]
9. **When** modifying agent message protocol: update both send_message() and receive_message() in base.py, and all process_message() implementations in subclasses. [PATTERN]

## Testing

- **Framework:** pytest [PATTERN]
- **Structure:** tests/{unit, integration, e2e, requirements, manual}/
- **Fixtures:** conftest.py with session-scoped sample data, per-test temp dirs [FACT: tests/conftest.py]
- **Environment:** conftest.py loads .env at import time [FACT: conftest.py:24-27]
- **Mock pattern:** unittest.mock.MagicMock for LLM clients [PATTERN]
- **Test count:** ~644 test functions [FACT: grep count]
- **Run:** `pytest tests/unit/ -v --tb=short` (unit), `pytest tests/integration/` (integration)

## Coupling Anomalies

Files that are co-modified without import relationships (hidden coupling):

| Files | Score | Impact |
|-------|-------|--------|
| config.py ↔ providers/anthropic.py | 1.0 | Model name changes require both [FACT] |
| experiment_designer.py ↔ research_director.py | 0.8 | Protocol design changes [FACT] |
| research_director.py ↔ code_generator.py | 0.8 | Execution chain changes [FACT] |
| research_director.py ↔ cli/commands/run.py | 0.8 | CLI entry changes [FACT] |
| anthropic.py ↔ openai.py | 0.8 | Provider implementations co-evolve [FACT] |
| config.py ↔ litellm_provider.py | 0.8 | New provider config [FACT] |

## External Dependencies

### Required
- Python 3.11+
- anthropic (or openai/litellm for alternative providers)
- pydantic, pydantic-settings
- sqlalchemy
- typer, rich (CLI)
- httpx (literature APIs)

### Optional (graceful degradation)
- docker (for sandboxed execution)
- py2neo (for Neo4j knowledge graph)
- chromadb (for vector search)
- litellm (for multi-provider support)
- sentence-transformers (for embeddings)

### External Services
- LLM API (Anthropic, OpenAI, or local Ollama) — required
- Docker daemon — recommended for code sandbox + Neo4j
- Neo4j — optional, auto-started via Docker
- Redis — optional, disabled by default

## Sub-Projects

The repository contains semi-independent sub-projects alongside core kosmos/:

| Sub-project | Purpose | Integration |
|-------------|---------|-------------|
| kosmos-reference/kosmos-agentic-data-scientist/ | Google ADK agents (Gemini-based) | Separate entry, uses ADK patterns |
| kosmos-reference/kosmos-claude-scientific-writer/ | Claude-based paper writing with MCP skills | Separate CLI (CC:67), own skill system |
| kosmos-claude-scientific-skills/ | MCP scientific skill packages (biorxiv, biomni, FDA, etc.) | Standalone scripts for MCP tool servers |

These are NOT tightly integrated with core kosmos/. They share some patterns but have independent dependencies and entry points.

## Extension Guide

**To add a new agent:**
1. Create `kosmos/agents/my_agent.py`
2. Inherit from `BaseAgent` (agents/base.py)
3. Implement `execute(task: Dict) -> Dict` and `process_message(message: AgentMessage)`
4. Register in ResearchDirectorAgent if it participates in the research cycle
5. Add config keys to KosmosConfig if needed (update flat_config mapping too)

**To add a new LLM provider:**
1. Create `kosmos/core/providers/my_provider.py`
2. Inherit from `LLMProvider` (providers/base.py)
3. Implement `generate()` method
4. Register in `_register_builtin_providers()` (providers/factory.py)
5. Add config section to config.py (e.g., MyProviderConfig)
6. Update `get_provider_from_config()` in factory.py

**To add a new experiment type:**
1. Add to `ExperimentType` enum (models/hypothesis.py)
2. Create template in `kosmos/experiments/templates/`
3. Update ExperimentDesignerAgent to handle the new type
4. Update CodeGenerator if code generation patterns differ

## Maintenance Hotspots

| File | Risk Score | Reason |
|------|-----------|--------|
| config.py | 0.96 | 27 commits, 18 hotfixes, 4 authors [FACT] |
| research_director.py | 0.83 | 21 commits, 17 hotfixes, 2900+ lines [FACT] |
| llm.py | 0.70 | 12 commits, 6 hotfixes [FACT] |
| executor.py | 0.70 | 12 commits, 8 hotfixes [FACT] |
| code_generator.py | 0.67 | 10 commits, 8 hotfixes [FACT] |
| run.py | 0.66 | 12 commits, 10 hotfixes [FACT] |

## Reading Order for New Contributors

1. `README.md` — Quick start and overview
2. `kosmos/__init__.py` — Package exports (ResearchDirectorAgent, get_config)
3. `kosmos/core/workflow.py` — State machine (understand the research cycle)
4. `kosmos/agents/base.py` — Agent protocol
5. `kosmos/config.py` — Configuration surface
6. `kosmos/cli/commands/run.py` — CLI entry point (trace the full path)
7. `kosmos/agents/research_director.py` — Master orchestrator (read selectively; 2900+ lines)
