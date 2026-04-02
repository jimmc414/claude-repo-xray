# DEEP_ONBOARD: Kosmos AI Scientist

## Identity

Kosmos is an autonomous AI scientist platform that executes the full scientific research cycle: question formulation, hypothesis generation, experiment design, code execution, result analysis, and iterative refinement. [FACT] `kosmos/__init__.py:4-10` describes it as "fully autonomous AI scientist system." Version 0.2.0 adds multi-provider LLM support (Anthropic, OpenAI, LiteLLM). [FACT] `kosmos/__init__.py:12`.

**Stack:** Python 3.11+, Pydantic v2 + pydantic-settings, SQLAlchemy 2.x, Neo4j (py2neo), ChromaDB, Anthropic/OpenAI SDKs, Typer/Rich CLI, Docker sandboxing. [FACT] `pyproject.toml:26-100`.

**Scale:** 802 Python files, ~284K lines, ~2.4M estimated tokens. 146 files in core `kosmos/` package across 20 subpackages. [FACT] xray metadata.

---

## Critical Paths

### Path 1: Research Execution (Primary)

```
CLI: kosmos run "question" --domain biology
  kosmos/cli/commands/run.py:run_research()          # Typer command, validates input
    -> run_with_progress_async()                      # Live Rich display
      -> ResearchDirectorAgent.__init__()             # Wires all sub-agents
        -> get_client()                               # LLM singleton (core/llm.py:613)
        -> init_from_config()                         # DB init (db/__init__.py:26)
        -> get_world_model()                          # Neo4j knowledge graph
      -> director.execute({"action": "start_research"})
        -> generate_research_plan()                   # LLM call for plan
        -> decide_next_action()                       # State machine decision tree
        -> _execute_next_action(action)               # Dispatches to sub-agents
```

[FACT] `kosmos/agents/research_director.py:2868-2909` defines async execute() method.

### Path 2: Workflow State Machine

```
INITIALIZING -> GENERATING_HYPOTHESES -> DESIGNING_EXPERIMENTS
  -> EXECUTING -> ANALYZING -> REFINING -> (loop or CONVERGED)
```

[FACT] States defined in `kosmos/core/workflow.py:18-29` as `WorkflowState` enum. Transitions validated against `ALLOWED_TRANSITIONS` dict at line 175. The `decide_next_action()` method at `research_director.py:2388` implements the decision tree: no hypotheses -> GENERATE; untested hypotheses -> DESIGN; experiments in queue -> EXECUTE; results need analysis -> ANALYZE; refinement needed -> REFINE; convergence criteria met -> CONVERGE.

### Path 3: Experiment Execution

```
CodeGenerator.generate() -> code string
  -> CodeValidator.validate() -> SafetyReport (risk level assessment)
  -> Executor.execute_code() -> ExecutionResult
    -> Option A: restricted exec() with SAFE_BUILTINS allowlist
    -> Option B: DockerSandbox.execute() (container isolation)
```

[FACT] `execution/executor.py:43-83` defines SAFE_BUILTINS allowlist. `execution/executor.py:86-94` defines _ALLOWED_MODULES for restricted import. DockerSandbox at `execution/sandbox.py:66` provides container-based isolation with CPU/memory limits.

---

## Module Behavioral Index

### kosmos/config.py (Risk: 0.96)
[FACT] Highest risk hotspot (churn:27, hotfixes:18, `xray.md`). Master config via `KosmosConfig(BaseSettings)` at line 922. Singleton pattern: `get_config()` at line 1140 creates/returns `_config` global. 16 nested config sections (claude, openai, litellm, research, database, redis, logging, literature, vector_db, neo4j, safety, performance, monitoring, development, world_model, local_model). All values from env vars via `pydantic-settings` alias mapping. [FACT] LLM provider selection via `llm_provider` field, default "anthropic" (line 953).

### kosmos/core/llm.py (Risk: 0.70)
[FACT] Dual-interface module: legacy `ClaudeClient` class (line 108) and new `LLMProvider`-based system. `get_client()` at line 613 is a thread-safe singleton with double-checked locking. Tries provider system first, falls back to AnthropicProvider on failure (line 662-673). CLI mode detected by all-9s API key (`api_key.replace('9', '') == ''`, line 179). Auto model selection based on keyword complexity scoring (lines 41-105).

### kosmos/agents/research_director.py (30K tokens)
[FACT] Master orchestrator at line 53. `__init__` wires: LLM client, database, world model, convergence detector, skill loader, rollout tracker, strategy stats, error recovery tracking. Lazy-inits 7 sub-agent slots (lines 145-151). Async locks + threading locks for dual async/sync support (lines 193-200). `MAX_ACTIONS_PER_ITERATION = 50` prevents infinite loops (line 50). `MAX_CONSECUTIVE_ERRORS = 3` with exponential backoff `[2, 4, 8]` seconds (lines 45-46).

### kosmos/agents/base.py
[FACT] `BaseAgent` at line 97 provides: lifecycle management (start/stop/pause/resume), async message passing via `asyncio.Queue` (line 137), state persistence, health checks. Subclasses implement `process_message()` and `execute()`. Agent status enum: CREATED, STARTING, RUNNING, IDLE, WORKING, PAUSED, STOPPED, ERROR (lines 25-34).

### kosmos/core/workflow.py
[FACT] `ResearchWorkflow` at line 166 is a state machine with validated transitions. `ResearchPlan` (Pydantic model, line 57) tracks hypothesis_pool, tested/supported/rejected hypotheses, experiment_queue, completed_experiments, results, iteration_count. All list mutations deduplicate via `if x not in list` checks.

### kosmos/core/convergence.py
[FACT] `ConvergenceDetector` implements mandatory criteria (iteration_limit, no_testable_hypotheses) and optional criteria (novelty_decline, diminishing_returns). `StoppingDecision` model has `should_stop`, `reason`, `is_mandatory`, `confidence` fields. Uses numpy for novelty trend analysis.

### kosmos/execution/executor.py
[FACT] Two execution modes: (1) restricted exec with `SAFE_BUILTINS` allowlist and `_ALLOWED_MODULES` set (numpy, pandas, scipy, sklearn, etc., line 86-94), (2) Docker sandbox via `DockerSandbox` (optional import, line 24-29). Default timeout 300s (line 40). `ExecutionResult` captures success, return_value, stdout, stderr, error, execution_time.

### kosmos/safety/code_validator.py
[FACT] `CodeValidator` at line 27 checks DANGEROUS_MODULES (os, subprocess, sys, etc., line 35-39) and DANGEROUS_PATTERNS (eval, exec, open, etc., line 42-53). Loads ethical guidelines from JSON. `SafetyReport` model with risk level assessment (from `models/safety.py`).

### kosmos/core/providers/base.py
[FACT] `LLMProvider` ABC at line 156 defines interface: generate(), generate_structured(), generate_with_messages(), streaming methods. `LLMResponse` dataclass (line 58) implements 20+ string compatibility methods (__str__, strip, lower, split, startswith, etc., lines 83-154) so it can be used where str is expected.

### kosmos/knowledge/graph.py
[FACT] `KnowledgeGraph` at line 24 wraps Neo4j via py2neo. Node types: Paper, Concept, Method, Author. Relationship types: CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO. Auto-starts Docker container if needed (`auto_start_container=True`, line 41). Graceful degradation: sets `self._connected = False` on connection failure, does not raise (line 97-99).

### kosmos/db/models.py + operations.py
[FACT] SQLAlchemy declarative models: Experiment, Hypothesis, Result, Paper, AgentRecord, ResearchSession (line 1-10 of operations.py imports). Connection pooling for PostgreSQL, SQLite fallback without pooling (db/__init__.py:72-78). Slow query logging via SQLAlchemy event listeners at operations.py:51.

---

## Key Interfaces

### get_config() -> KosmosConfig
[FACT] `config.py:1140`. Singleton. Loads from env vars and `.env` file. Call `get_config(reload=True)` to force reload. `reset_config()` for testing.

### get_client() -> Union[ClaudeClient, LLMProvider]
[FACT] `core/llm.py:613`. Thread-safe singleton with lock. `use_provider_system=True` (default) uses config-driven provider. `reset=True` recreates. Falls back to AnthropicProvider on init failure.

### get_world_model() -> WorldModelStorage
[FACT] `world_model/__init__.py`. Factory returning Neo4jWorldModel (simple mode) or InMemoryWorldModel (fallback). Strategy pattern: WorldModelStorage ABC in `world_model/interface.py:36`.

### get_provider(name, config) -> LLMProvider
[FACT] `core/providers/factory.py:34`. Registry-based factory. Available: "anthropic", "openai", "litellm".

### init_database(url, ...)
[FACT] `db/__init__.py:26`. Initializes `_engine` and `_SessionLocal` globals. SQLite: no pooling, `check_same_thread=False`. PostgreSQL: QueuePool with configurable pool_size.

---

## Error Handling Strategy

[PATTERN] **Per-operation try/except with continue** (observed in 15/15 agent methods examined). Each agent operation catches `Exception`, logs error, and continues to next step. ResearchDirector tracks `_consecutive_errors` and halts after `MAX_CONSECUTIVE_ERRORS = 3` with exponential backoff `[2, 4, 8]` seconds. [FACT] `research_director.py:45-46`.

[PATTERN] **Graceful degradation for optional dependencies** (6/6 checked). Docker sandbox, R executor, Neo4j, async LLM client, parallel executor, and skill loader all use try/except ImportError with fallback to simpler modes. [FACT] Example: `executor.py:24-29` tries sandbox import, sets `SANDBOX_AVAILABLE = False` on failure.

[PATTERN] **Budget enforcement** via `BudgetExceededError` at `research_director.py:2406-2418`. On budget exceeded, transitions to CONVERGED state gracefully.

---

## Shared State & Singletons

[FACT] Four module-level singletons with lazy init:
1. `_config: KosmosConfig` in `config.py` (line 1138, no lock)
2. `_default_client` in `core/llm.py` (line 640, `threading.Lock`)
3. `_engine` + `_SessionLocal` in `db/__init__.py` (line 22-23)
4. World model via factory in `world_model/__init__.py`

[FACT] `ResearchDirectorAgent` maintains mutable state across async boundaries: `research_plan` (protected by `asyncio.Lock` + `threading.RLock`), `strategy_stats`, `iteration_history`, `_consecutive_errors`. Lines 193-200.

---

## Domain Glossary

| Term | Meaning | Code Location |
|------|---------|---------------|
| Research Director | Master orchestrator agent coordinating all sub-agents | `agents/research_director.py` |
| Workflow State | FSM state in research cycle (INIT through CONVERGED) | `core/workflow.py:18` |
| Hypothesis Pool | List of hypothesis IDs under investigation | `core/workflow.py:68` |
| Convergence | Research stopping decision based on criteria | `core/convergence.py` |
| World Model | Persistent Neo4j knowledge graph accumulating across sessions | `world_model/` |
| CLI Mode | LLM routing via Claude Code CLI (API key = all 9s) | `core/llm.py:179` |
| Skill Loader | Loads domain-specific prompts from skill files | `agents/skill_loader.py` |
| Safety Report | Result of code validation with risk level | `models/safety.py` |
| Sandbox | Docker-based isolated code execution | `execution/sandbox.py` |

---

## Configuration Surface

[FACT] All configuration via environment variables, loaded through `pydantic-settings`. Master class: `KosmosConfig` at `config.py:922`. `.env` file path: `Path(__file__).parent.parent / ".env"` (project root).

**Critical env vars:**

| Variable | Default | Effect |
|----------|---------|--------|
| `ANTHROPIC_API_KEY` | (required) | Claude API key; all-9s = CLI mode |
| `LLM_PROVIDER` | `"anthropic"` | Provider selection: anthropic/openai/litellm |
| `DATABASE_URL` | `"sqlite:///kosmos.db"` | SQLite default, supports PostgreSQL |
| `MAX_RESEARCH_ITERATIONS` | `10` | Loop bound for research cycle |
| `MAX_RUNTIME_HOURS` | `12.0` | Hard time limit on research |
| `RESEARCH_BUDGET_USD` | `10.0` | API cost budget |
| `ENABLE_SANDBOXING` | `True` | Docker sandbox for code execution |
| `WORLD_MODEL_MODE` | `"simple"` | Neo4j simple vs polyglot production |
| `NEO4J_URI` | `"bolt://localhost:7687"` | Knowledge graph connection |
| `CLAUDE_MODEL` | `"claude-sonnet-4-5"` | Default model |

---

## Conventions

[PATTERN] **Agent pattern** (5/5 agents checked): Inherit `BaseAgent`, accept `(agent_id, agent_type, config)`, implement `execute()` as async, use `get_client()` for LLM access, wrap operations in try/except. [FACT] BaseAgent at `agents/base.py:97`.

[PATTERN] **Pydantic models for runtime data, SQLAlchemy for persistence** (8/8 model files checked). Runtime models in `models/` use Pydantic BaseModel. Database models in `db/models.py` use SQLAlchemy declarative_base. Both Hypothesis models exist: Pydantic at `models/hypothesis.py:32`, SQLAlchemy at `db/models.py:75`.

[PATTERN] **Logging convention** (140/140 modules use `logging.getLogger(__name__)`). JSON structured logging via `core/logging.py` with correlation_id ContextVar for request tracing.

[PATTERN] **Config from environment** (16/16 config sections use pydantic-settings `alias` for env var names). No hardcoded credentials or config values outside config.py.

[PATTERN] **Optional dependency import** (6/6 checked): `try: import X; HAS_X = True / except ImportError: HAS_X = False`. Used for: anthropic, openai, docker, py2neo, sentence-transformers, R executor.

---

## Gotchas

1. [FACT] **Dual Hypothesis models.** `models/hypothesis.py:32` (Pydantic, runtime) and `db/models.py:75` (SQLAlchemy, persistence) both define `Hypothesis` with overlapping but not identical fields. The Pydantic model has evolution tracking (parent_hypothesis_id, generation, evolution_history) that the DB model lacks.

2. [FACT] **LLMResponse masquerades as str.** `core/providers/base.py:58-154` implements 20+ string methods on LLMResponse. Code expecting `str` from `generate()` works, but `isinstance(response, str)` returns False. The legacy `ClaudeClient.generate()` returns actual `str`, creating inconsistency between old and new paths.

3. [FACT] **Config singleton has no lock.** `config.py:1140` `get_config()` reads/writes `_config` global without synchronization, while `get_client()` at `core/llm.py:646` uses `threading.Lock`. Race condition possible if `get_config()` called from multiple threads during startup.

4. [FACT] **CLI mode detection is fragile.** `api_key.replace('9', '') == ''` at `core/llm.py:179` means any all-9s string routes to CLI. The convention requires exactly 48 nines but validation only checks "all digits are 9."

5. [FACT] **Async/sync dual-lock pattern.** `research_director.py:193-200` maintains both `asyncio.Lock` and `threading.RLock` for the same state. Comment at line 192 notes "asyncio.Lock is not reentrant." If sync code is called from async context, wrong lock is acquired.

6. [FACT] **World model failure is silent.** `research_director.py:252-254` catches all exceptions from `get_world_model()`, sets `self.wm = None`, and continues. Research proceeds without persistent knowledge, with no user-visible warning.

---

## Hazards

1. [FACT] **Unrestricted exec fallback.** If Docker sandbox is unavailable (`SANDBOX_AVAILABLE = False`, `executor.py:28`), code runs via restricted `exec()` with only module-level allowlisting. The `SAFE_BUILTINS` dict at line 43 includes `type`, `super`, `object`, `property` which could be exploited for sandbox escapes.

2. [FACT] **No connection pooling for SQLite.** `db/__init__.py:72-78` uses `check_same_thread=False` for SQLite without connection pooling. Concurrent writes to SQLite can cause `database is locked` errors under load.

3. [FACT] **Budget check only in decide_next_action.** `research_director.py:2404-2418` checks budget in `decide_next_action()`. An expensive LLM call within a single step (e.g., hypothesis generation) can exceed budget before the next check occurs.

---

## Extension Points

1. **New LLM Provider:** Implement `LLMProvider` ABC (`core/providers/base.py:156`), register via `register_provider()` in `core/providers/factory.py:19`. Add config class inheriting `BaseSettings` in `config.py`.

2. **New Agent:** Inherit `BaseAgent` (`agents/base.py:97`), implement `execute()`, register in agent_registry dict on ResearchDirector.

3. **New Scientific Domain:** Add subpackage under `kosmos/domains/` (existing: biology, chemistry, materials, neuroscience, physics). Create domain-specific API clients and data models.

4. **New World Model Backend:** Implement `WorldModelStorage` ABC (`world_model/interface.py:36`). Update factory in `world_model/__init__.py`.

5. **New Experiment Type:** Add to `ExperimentType` enum (`models/hypothesis.py:15-18`), create template class inheriting `CodeTemplate` (`execution/code_generator.py:25`).

---

## Reading Order

1. `kosmos/config.py` -- All configuration originates here; understand KosmosConfig first
2. `kosmos/core/llm.py` -- LLM abstraction layer; get_client() singleton
3. `kosmos/core/providers/base.py` -- LLMProvider interface contract
4. `kosmos/agents/base.py` -- BaseAgent ABC; lifecycle + messaging
5. `kosmos/core/workflow.py` -- WorkflowState FSM + ResearchPlan model
6. `kosmos/agents/research_director.py` -- Master orchestrator (read skeleton, not full file)
7. `kosmos/execution/executor.py` -- Execution engine with safety controls
8. `kosmos/models/hypothesis.py` -- Core domain model
9. `kosmos/db/models.py` -- Persistence schema
10. `kosmos/knowledge/graph.py` -- Neo4j knowledge graph integration

---

## Gaps / Unknowns

[ABSENCE] **No integration tests in core package.** Searched `tests/` -- 249 test modules exist but are primarily requirements-based (`tests/requirements/`). No test exercises the full CLI-to-convergence path end-to-end.

[ABSENCE] **Production mode (polyglot world model) not implemented.** `world_model/interface.py:18-19` describes "Production Mode (Phase 4)" with PostgreSQL + Neo4j + ES + Vector DB, but only Neo4jWorldModel and InMemoryWorldModel exist.

[ABSENCE] **No rate limiting on LLM calls in sync path.** `AsyncClaudeClient` has `max_requests_per_minute` but the sync `ClaudeClient.generate()` path has no rate limiter.
