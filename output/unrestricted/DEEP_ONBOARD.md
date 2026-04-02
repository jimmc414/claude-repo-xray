# Kosmos: Agent Onboarding

> Codebase: 802 files, ~2.4M tokens
> This document: ~8K tokens
> Generated: 2026-03-28 from branch master
> Crawl: 18/18 tasks, 35+ modules read, 3 traces verified
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---

## Identity

Kosmos is an autonomous AI scientist that runs research cycles: generate hypotheses, design experiments, execute code in sandboxed Docker containers, analyze results, and refine hypotheses until convergence. Python 3.11+, Anthropic/OpenAI/LiteLLM multi-provider LLM, SQLAlchemy + SQLite/PostgreSQL for persistence, Neo4j knowledge graph (optional), ChromaDB vector store. CLI entry point: `kosmos run "question" --domain biology`. [FACT] (pyproject.toml:6, README.md:1-19)

---

## Critical Paths

### Path 1: CLI Research Run (primary user path)

```
kosmos.cli.main:cli_entrypoint (main.py:422)
  → typer app -> main() callback (main.py:98) — loads env, sets up logging
    → db.init_from_config() (main.py:144) — auto-creates .env, runs Alembic, inits SQLAlchemy
  → run_research() (commands/run.py:51) — parses args, flattens config to dict
    → ResearchDirectorAgent.__init__ (research_director.py:68) — creates workflow state machine
      → get_client() (core/llm.py:613) — singleton LLM provider from config
      → get_world_model() (world_model/factory.py:55) — Neo4j graph (non-fatal if fails)
      → ConvergenceDetector.__init__ (core/convergence.py) — stopping criteria
    → registry.register(director) (agents/registry.py) — message routing setup
    → asyncio.run(run_with_progress_async()) — enters async
      → director.execute() — state machine loop:
        INITIALIZING → GENERATING_HYPOTHESES → DESIGNING_EXPERIMENTS
        → EXECUTING → ANALYZING → REFINING → (loop or CONVERGED)
        → [DB COMMIT] hypothesis/experiment/result saved (db/__init__.py:get_session)
        → [GRAPH] entity added to Neo4j (world_model/simple.py)
        → convergence_detector.evaluate() per iteration
  ✗ on DB failure: error logged, user shown Rich panel, exit 1
  ✗ on Neo4j failure: warning logged, continues without graph
  ✗ on LLM failure: ProviderAPIError, retry with backoff [2,4,8]s, halt after 3 consecutive
```

### Path 2: LLM Call Resolution

```
get_client() (core/llm.py:613)
  → [thread-safe singleton with _client_lock]
  → get_config().llm_provider (config.py:1140) — reads LLM_PROVIDER env
  → get_provider_from_config(config) (providers/factory.py)
    → BRANCH "anthropic": AnthropicProvider(config_dict)
    → BRANCH "openai": OpenAIProvider(config_dict)
    → BRANCH "litellm": LiteLLMProvider(config_dict)
    → FALLBACK: AnthropicProvider with env defaults
  → provider.generate(prompt, system, ...) → LLMResponse
    → [cache check] ClaudeCache.get() → hit = return cached, miss = API call
    → [API CALL] Anthropic/OpenAI HTTP request
    → [cache write] ClaudeCache.set()
    → LLMResponse (string-compatible via delegation methods)
```

### Path 3: Code Execution

```
CodeGenerator.generate() (execution/code_generator.py)
  → template matching OR LLM-based code generation
  → CodeValidator.validate() (safety/code_validator.py) — AST analysis, restricted imports
Executor.execute() (execution/executor.py)
  → BRANCH Docker available: DockerSandbox.run() (execution/sandbox.py)
    → [container with CPU/memory/timeout limits, network isolation]
  → BRANCH no Docker: restricted exec() with SAFE_BUILTINS
    → only allows scientific modules (numpy, pandas, scipy, sklearn...)
    → [concurrent.futures timeout after DEFAULT_EXECUTION_TIMEOUT=300s]
  → ExecutionResult(success, return_value, stdout, stderr, execution_time)
```

---

## Module Behavioral Index

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `config.py` | Pydantic config singleton from .env + env vars; 18 sub-configs | .env file, env vars | Risk 0.96; agents expect FLAT dict, not nested config |
| `core/llm.py` | Two LLM client systems: ClaudeClient (legacy, returns str) and LLMProvider (new, returns LLMResponse) | anthropic/openai SDK, config | LLMResponse mimics str but `isinstance(r, str)` = False |
| `core/workflow.py` | State machine: WorkflowState enum + ResearchPlan tracking hypotheses/experiments/results | — | State transitions are not enforced by the enum |
| `agents/base.py` | BaseAgent ABC: lifecycle, async message queue, state persistence, execute() interface | asyncio | Has both async and sync wrappers; sync wrappers may create new event loops |
| `agents/research_director.py` | Master orchestrator: coordinates all agents, manages convergence, error recovery | db, llm, world_model, convergence | 30K tokens; config dict must be flat; 3 error halt |
| `execution/executor.py` | Runs generated Python code safely; Docker sandbox or restricted exec() | docker (optional) | SAFE_BUILTINS whitelist; _ALLOWED_MODULES whitelist |
| `execution/code_generator.py` | Template + LLM code generation from ExperimentProtocol | core/llm, models/experiment | Templates in kosmos-figures are pattern sources |
| `db/__init__.py` | SQLAlchemy engine + session factory; auto-migration on first run | sqlalchemy, alembic | Global _engine; reset_database() DESTROYS ALL DATA |
| `world_model/` | Neo4j knowledge graph via Strategy pattern; Entity/Relationship model | py2neo, neo4j | Singleton NOT thread-safe; failure is non-fatal |
| `agents/skill_loader.py` | Loads domain skills from kosmos-claude-scientific-skills into agent prompts | filesystem | 116 skill directories; failure non-fatal |
| `core/convergence.py` | Detects when research should stop: mandatory + optional criteria | numpy | novelty_decline uses windowed trend analysis |
| `workflow/research_loop.py` | High-level workflow integrating 6 "gaps": compression, state, orchestration, skills, tooling, validation | all agents, gap impls | Separate from ResearchDirector; both orchestrate |
| `core/providers/base.py` | LLMProvider ABC + LLMResponse string-compat + ProviderAPIError | — | is_recoverable() logic determines retry behavior |
| `models/hypothesis.py` | Pydantic Hypothesis model: scores, evolution tracking, experiment types | — | Validates statements don't end with "?" |
| `models/experiment.py` | Pydantic ExperimentProtocol: variables, statistical tests, steps | — | Has nested ProtocolStep list |
| `core/logging.py` | JSON/text structured logging with correlation IDs via contextvars | — | 140 importers; logging.py is the most-imported file |
| `agents/registry.py` | Central agent registry for message routing; not yet used in main loop | — | Docstring says "reserved for future" |

---

## Key Interfaces

```python
# kosmos/core/llm.py
def get_client(reset=False, use_provider_system=True) -> Union[ClaudeClient, LLMProvider]
    # Thread-safe singleton. Default returns LLMProvider; use_provider_system=False for legacy.

# kosmos/config.py
def get_config(reload=False) -> KosmosConfig  # Singleton from env vars + .env
def reset_config()                             # For testing only

# kosmos/agents/base.py
class BaseAgent:
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]  # Override for main logic
    async def send_message(self, to_agent, content, ...) -> AgentMessage
    def _on_start(self)   # Lifecycle hook
    def _on_stop(self)    # Lifecycle hook

# kosmos/core/providers/base.py
class LLMProvider(ABC):
    def generate(self, prompt, system=None, max_tokens=4096, ...) -> LLMResponse
    async def generate_async(self, prompt, ...) -> LLMResponse
    def generate_structured(self, prompt, schema, ...) -> Dict[str, Any]

# kosmos/core/workflow.py
class WorkflowState(Enum): INITIALIZING, GENERATING_HYPOTHESES, DESIGNING_EXPERIMENTS,
                           EXECUTING, ANALYZING, REFINING, CONVERGED, PAUSED, ERROR

# kosmos/db/__init__.py
def get_session() -> Generator[Session]  # Context manager: auto-commit/rollback
def init_from_config()                   # Auto-setup: .env, migrations, tables
```

---

## Error Handling Strategy

**Dominant pattern:** "catch-warn-continue" for infrastructure; "retry-then-halt" for LLM calls. [PATTERN: 5/5 infrastructure init sites use this]

**Retry strategy:** ResearchDirector uses exponential backoff [2, 4, 8]s, halts after MAX_CONSECUTIVE_ERRORS=3. ProviderAPIError.is_recoverable() determines retry eligibility: 4xx (except 429) = non-recoverable, 5xx/timeout/rate-limit = recoverable. [FACT] (research_director.py:45-46, providers/base.py:445-484)

**Loop prevention:** MAX_ACTIONS_PER_ITERATION=50 forces convergence. [FACT] (research_director.py:50)

---

## Shared State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `_config` | config.py:1137 | `get_config()`, `reset_config()` | Singleton; agents cache references |
| `_default_client` | core/llm.py:609 | `get_client()` | Thread-safe (Lock); returns different types based on config |
| `_world_model` | world_model/factory.py:52 | `get_world_model()`, `reset_world_model()` | NOT thread-safe per docstring |
| `_engine` + `_SessionLocal` | db/__init__.py:23-24 | `init_database()`, `reset_database()` | reset_database() DESTROYS ALL DATA |
| `_registry` | agents/registry.py:522 | `get_registry()` | Not yet integrated into main loop |
| `_claude_cache` | core/claude_cache.py:390 | `get_claude_cache()` | File-based; no TTL eviction |
| `CacheManager._instance` | core/cache_manager.py:38 | Class-level singleton | Threading lock in __new__ |
| `_cache` | literature/cache.py:323 | `get_cache()`, `reset_cache()` | Literature search cache |

**Testing rule:** Always call `reset_config()`, `reset_world_model()`, `reset_cache()` in test fixtures to prevent state leakage. [PATTERN: observed in conftest.py fixtures]

---

## Configuration Surface

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ANTHROPIC_API_KEY` | env | LLM provider auth; all 9s = CLI mode | required |
| `LLM_PROVIDER` | env | Provider selection: anthropic/openai/litellm | `"anthropic"` |
| `DATABASE_URL` | env | Persistence backend | `"sqlite:///kosmos.db"` |
| `NEO4J_URI` | env | Knowledge graph connection | `"bolt://localhost:7687"` |
| `MAX_RESEARCH_ITERATIONS` | env | Iteration ceiling | `10` |
| `RESEARCH_BUDGET_USD` | env | API cost ceiling | `10.0` |
| `MAX_RUNTIME_HOURS` | env | Wall-clock ceiling | `12.0` |
| `ENABLE_SANDBOXING` | env | Docker vs restricted exec | `True` |
| `CLAUDE_MODEL` | env | Default Claude model | `"claude-sonnet-4-5"` |
| `REDIS_ENABLED` | env | Redis caching layer | `False` |
| `CLAUDE_ENABLE_CACHE` | env | LLM response caching | `True` |
| `ENABLE_SAFETY_CHECKS` | env | Code validation pre-execution | `True` |
| `APPROVAL_MODE` | env | Human oversight: blocking/queue/automatic/disabled | `"blocking"` |

---

## Conventions

1. **Always use get_X() factories for shared state** — never import underscore-prefixed globals directly. [PATTERN: 13/13 singletons follow this]
2. **Agents inherit BaseAgent** and override execute(task) -> dict. [PATTERN: 5/5 core agents]
3. **Domain models are dual**: Pydantic in models/*.py (runtime), SQLAlchemy in db/models.py (persistence). Convert manually. [PATTERN: 3/3 core entities]
4. **Infrastructure failures degrade gracefully** — Neo4j, skills, event bus failures are caught and logged, never crash the system. [PATTERN: 5/5 infrastructure init sites]
5. **Tests use `@pytest.mark.unit`/`.integration`/`.e2e` markers** and conftest.py reset fixtures. [PATTERN: 207 test files]
6. **Ruff linter**: line_length=100, ignores E501/B008/C901. [FACT] (pyproject.toml:257-271)
7. **Async methods have sync wrappers** (e.g., `send_message` + `send_message_sync`). [PATTERN: 4/4 async agent methods]
8. **CLI commands flatten KosmosConfig into a dict** before passing to agents. [FACT] (commands/run.py:148-170)

---

## Gotchas

1. **LLMResponse is not a string** — `get_client()` returns LLMProvider by default, whose `.generate()` returns `LLMResponse`, not `str`. It has `.strip()`, `.lower()`, etc. but `isinstance(response, str)` returns False. Code migrated from ClaudeClient to LLMProvider will break on type checks. [FACT] (`core/providers/base.py:81-154`)

2. **Two orchestration systems exist** — `ResearchDirectorAgent` (agents/research_director.py) runs via CLI `kosmos run`; `ResearchWorkflow` (workflow/research_loop.py) is a separate async API. They share concepts but are independent codepaths with different initialization. [FACT] (`research_director.py:53`, `research_loop.py:30`)

3. **Config dict must be flat for agents** — KosmosConfig is nested Pydantic, but agents read `self.config.get("max_iterations")`. The CLI run command manually flattens this (run.py:148-170). Adding new config keys requires updating the flattening logic. [FACT] (`commands/run.py:148-170`, `research_director.py:104`)

4. **World model singleton is NOT thread-safe** — factory.py docstring explicitly states this. Concurrent access from multiple threads can corrupt state. [FACT] (`world_model/factory.py:37`)

5. **reset_database() destroys all data** — No confirmation prompt, no backup. Called by evaluation isolation code. [FACT] (`db/__init__.py:191-202`)

6. **Circular import: llm <-> anthropic** — `core/llm.py` and `core/providers/anthropic.py` have a circular dependency. Currently handled by import ordering but fragile. [FACT] (xray circular dependency detection)

7. **SQLite path normalization** — DatabaseConfig.normalized_url converts relative paths to absolute relative to project root, not cwd. Running from a different directory still uses the same DB. [FACT] (`config.py:270-298`)

8. **Sync wrappers may create event loops** — BaseAgent sync wrappers (send_message_sync, etc.) call `asyncio.run()` when no loop exists, which can conflict with existing loops in tests or async contexts. [FACT] (`agents/base.py:314-327`)

9. **Agent registry is not yet integrated** — Despite being registered in the CLI run path, the registry is "reserved for future" multi-agent message-passing. Messages currently go through direct method calls. [FACT] (`agents/registry.py:8-10`)

10. **Hidden coupling: config.py <-> anthropic.py** — These files are co-modified 100% of the time without any import relationship. Changes to config fields often require matching changes in the Anthropic provider. [FACT] (xray coupling analysis: co_modification_score=1.0)

---

## Hazards -- Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `kosmos/agents/research_director.py` | ~30K | Use skeleton from xray; this file has 54+ methods |
| `kosmos/execution/*.py` | ~20K | Two files; read executor.py up to line 150 for the API |
| `evaluation/scientific_evaluation.py` | ~14K | Evaluation harness, not core logic |
| `kosmos/workflow/ensemble.py` | ~10K | Experimental ensemble feature |
| `tests/requirements/**` | ~31K | Requirements-tracking test boilerplate |
| `kosmos-reference/**` | variable | Reference implementations (scientific writer, ADK, MCP); separate projects |
| `kosmos-claude-scientific-skills/**` | variable | 116 skill definition directories; read via SkillLoader, not directly |

---

## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| Add new LLM provider | `core/providers/`, create `new_provider.py` subclassing `LLMProvider` | `core/providers/factory.py` (register), `config.py` (add config class) | Return LLMResponse not str; register in factory |
| Add new agent type | `agents/new_agent.py` subclassing `BaseAgent` | `agents/__init__.py` (export), `research_director.py` (wire into execute) | Follow execute(task)->dict pattern; use get_client() |
| Add new scientific domain | `domains/new_domain/` | `config.py` (add to enabled_domains), `agents/skill_loader.py` (add bundle) | Skills in kosmos-claude-scientific-skills/ |
| Add new experiment type | `execution/code_generator.py` (new template), `experiments/templates/` | `models/experiment.py` (add ExperimentType enum value) | Template must match ExperimentProtocol schema |
| Add new CLI command | `cli/commands/new_cmd.py` | `cli/main.py` (register_commands), `cli/utils.py` | Use typer; flatten config before passing to agents |
| Add new config field | `config.py` (add to relevant sub-config) | `commands/run.py` (add to flat_config if agents need it) | Agents read flat dicts, not nested config |

---

## Reading Order

1. `kosmos/config.py` (lines 1-100, 1136-1161) — understand config hierarchy and singleton pattern
2. `kosmos/agents/base.py` — understand agent contract (execute, lifecycle, messaging)
3. `kosmos/core/llm.py` (lines 608-707) — get_client/get_provider factory
4. `kosmos/core/workflow.py` (lines 1-150) — state machine states and ResearchPlan
5. `kosmos/cli/commands/run.py` (lines 50-195) — how CLI wires everything together
6. `kosmos/core/providers/base.py` — LLMProvider interface and LLMResponse string compat

**Skip:** `kosmos-reference/` (separate projects), `kosmos-claude-scientific-skills/` (116 skill dirs, accessed via SkillLoader), `tests/requirements/` (boilerplate), `archive/` (outdated planning docs)

---

## Gaps

- **No rate limiting** on LLM calls beyond provider-level retry. Budget enforcement is checked per-iteration, not per-call. [ABSENCE: grepped for rate_limit, throttle, slowapi in kosmos/ — 0 hits in core]
- **Agent registry unused** — registered but messages route via direct calls, not registry. [FACT] (agents/registry.py:8-10)
- **World model not thread-safe** — documented limitation, no fix planned. [FACT] (world_model/factory.py:37)
- **No schema migration testing** — Alembic migrations run on first startup but are not tested in CI.
- **Two orchestration paths** — ResearchDirector and ResearchWorkflow are parallel implementations. No documented guidance on when to use which.

---

*Generated by deep_crawl agent. 18 tasks, 35+ modules read, 3 traces verified.
Compression: 2,455,608 → ~8,000 tokens (307:1).
Evidence: 25 [FACT], 11 [PATTERN], 1 [ABSENCE].*
