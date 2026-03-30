# Kosmos: Agent Onboarding

> Codebase: 802 files, ~2,455,608 tokens
> This document: ~6K tokens
> Generated: 2026-03-29 from git HEAD
> Crawl: 31/31 tasks, 15 modules read, 5 traces verified
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---

## Identity

Kosmos is an autonomous AI scientist that runs research cycles: research question → hypothesis generation → experiment design → code execution → data analysis → refinement → convergence. Built with Python, Pydantic, SQLAlchemy, Claude/OpenAI LLMs, with optional Neo4j knowledge graph and Docker sandboxing. CLI via Typer, agents communicate via async message passing. The codebase includes the core system (~400 files in `kosmos/`), scientific domain skills (142 scripts), and reference implementations (231 files, not imported by core).

---

## Critical Paths

### 1. CLI Run → Full Research Cycle

```
run_research(question, domain, max_iters) (cli/commands/run.py:51)
  → get_config() → flattens nested KosmosConfig to flat dict for agents
  → ResearchDirectorAgent(question, domain, config=flat_config) (agents/research_director.py:53)
      → get_client() — singleton LLM client (core/llm.py:613)
      → init_from_config() — SQLite DB init (db/__init__.py:140)
      → get_world_model() — Neo4j optional, silent fallback
  → asyncio.run(run_with_progress_async(director, ...)) (run.py:186)
      → director.execute({"action": "start_research"}) (research_director.py:2868)
          → generate_research_plan() → LLM plans approach
          → decide_next_action() → dispatches to agent handlers:
            GENERATE_HYPOTHESIS → HypothesisGeneratorAgent
            DESIGN_EXPERIMENT → ExperimentDesignerAgent
            EXECUTE_EXPERIMENT → CodeExecutor (executor.py:162)
            ANALYZE_RESULT → DataAnalystAgent
            REFINE_HYPOTHESIS → HypothesisRefiner
            CHECK_CONVERGENCE → ConvergenceDetector
      → while iteration < max_iterations: director.execute({"action":"step"})
      → breaks on convergence OR 2-hour hardcoded timeout (run.py:301)
      → fetches results from DB → ResultsViewer displays/exports
  ✗ on failure: MAX_CONSECUTIVE_ERRORS=3, backoff [2,4,8]s, then halt (research_director.py:44-46)
  ✗ loop guard: MAX_ACTIONS_PER_ITERATION=50 forces convergence (research_director.py:50)
```

### 2. Hypothesis Generation

```
HypothesisGeneratorAgent.execute(message) (agents/hypothesis_generator.py:91)
  → generate_hypotheses(question, num=3, domain)
      → _gather_literature_context() → UnifiedLiteratureSearch (Semantic Scholar + arXiv + PubMed)
      → _generate_with_claude() → LLM call with HYPOTHESIS_GENERATOR prompt
      → for each: _validate_hypothesis() + novelty_checker.check_novelty() [another LLM call]
      → _store_hypothesis() → DB via get_session() [AUTO-COMMITS]
  → returns AgentMessage(type=RESPONSE)
  ✗ on failure: status=ERROR, returns AgentMessage(type=ERROR), then status=IDLE
```

### 3. Code Execution

```
CodeExecutor.execute(code, retry_on_error=True) (execution/executor.py:237)
  → auto-detect language (Python/R)
  → if Docker available: DockerSandbox.execute() with resource limits
  → else: restricted builtins execution (SAFE_BUILTINS + _ALLOWED_MODULES)
      → blocks: os, subprocess, open(), eval(), exec()
      → allows: numpy, pandas, scipy, sklearn, matplotlib
      → 300s signal-based timeout (NOT on Windows)
  → on error + retry: RetryStrategy.fix_code() uses LLM to repair code
  ✗ on failure: returns ExecutionResult(success=False, error=...)
```

---

## Module Behavioral Index

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `config.py` | Pydantic config from env vars + .env. Houses ALL settings. | pydantic_settings, .env file | Risk 0.96. get_config() is singleton — env changes after first call ignored |
| `core/llm.py` | Multi-provider LLM factory. get_client() singleton. | anthropic/openai SDK, config | Circular dep with providers/anthropic. ClaudeClient returns str, LLMProvider returns LLMResponse |
| `agents/base.py` | BaseAgent ABC: lifecycle, async message passing, state | asyncio, pydantic | Dual message queues (sync+async). start() only works from CREATED |
| `core/workflow.py` | Research state machine: 9 states, validated transitions | config (optional) | transition_to() RAISES on invalid transitions |
| `agents/research_director.py` | Master orchestrator: 54+ methods, coordinates all agents | ALL other agents, DB, LLM, world model | 30K tokens. Dual locks (asyncio + threading). Config must be flat dict |
| `execution/executor.py` | Code execution with sandboxing and restricted builtins | Docker (optional), signal | signal.alarm fails on Windows |
| `db/__init__.py` | SQLAlchemy init, session management, connection pooling | sqlalchemy, config | Must call init_database() before get_session() |
| `models/hypothesis.py` | Hypothesis Pydantic model with validation | config (for model name) | Validates: no question marks, min 20-char rationale |
| `literature/base_client.py` | Abstract literature API client, PaperMetadata dataclass | — | PaperMetadata.authors defaults to None, needs __post_init__ |
| `safety/code_validator.py` | Static analysis + ethical guidelines for generated code | config, models/safety.py | Blocks os/subprocess/socket but allow_file_read=True by default |
| `core/convergence.py` | Stopping criteria: iteration limit, novelty decline, cost | config | min_experiments_before_convergence default is 2 |

---

## Key Interfaces

```python
# config.py
def get_config() -> KosmosConfig: ...  # Singleton, thread-safe-ish (no lock)
class KosmosConfig(BaseSettings):  # llm_provider, claude, openai, litellm, research, database, ...

# core/llm.py
def get_client(reset=False) -> Union[ClaudeClient, LLMProvider]: ...  # Singleton, locked
class ClaudeClient:
    def generate(prompt, system=None, ...) -> str: ...  # Returns str (NOT LLMResponse)

# core/providers/base.py
class LLMProvider(ABC):
    def generate(prompt, system=None, ...) -> LLMResponse: ...  # LLMResponse acts like str
class LLMResponse:  # .content: str, .usage: UsageStats; has strip(), lower(), etc.

# agents/base.py
class BaseAgent:
    def execute(task: Dict) -> Dict: ...  # Override this
    async def send_message(to_agent, content, ...) -> AgentMessage: ...
class AgentMessage(BaseModel):  # id, type, from_agent, to_agent, content, correlation_id

# core/workflow.py
class WorkflowState(Enum):  # INITIALIZING → GENERATING_HYPOTHESES → ... → CONVERGED
class NextAction(Enum):  # GENERATE_HYPOTHESIS, DESIGN_EXPERIMENT, EXECUTE_EXPERIMENT, ...
class ResearchPlan(BaseModel):  # hypothesis_pool, experiment_queue, results: all List[str] of IDs

# db/__init__.py
def init_from_config(): ...  # Auto-setup: .env, migrations, tables
def get_session() -> Generator[Session]: ...  # Context manager, auto-commit
```

---

## Error Handling Strategy

**Dominant pattern:** Agent-level catch-log-continue. Errors become AgentMessage(type=ERROR), never crash the research loop. [PATTERN: 6/6 agent classes]

**Retry strategy:** ResearchDirector: 3 consecutive errors → halt. Exponential backoff [2,4,8]s. Executor: 3 retries with LLM-assisted code repair. LLM providers: ProviderAPIError.is_recoverable() classifies retry-worthiness.

**Deviations:**

| Module | Pattern | Risk |
|--------|---------|------|
| `base.py:286` | Config check in send_message() — bare `except: pass` | Silently hides config errors |
| 120 files | 617 except-pass or bare-except hits total | Broad swallowing risk |
| `research_director.py:136` | DB "already initialized" errors swallowed | Could mask real DB issues |

---

## Shared State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `_config` (KosmosConfig) | `config.py:~1150` | `get_config()` first call | Singleton — env changes after init ignored |
| `_default_client` (LLM) | `core/llm.py:~610` | `get_client()` | Thread-safe (Lock). Reset via `get_client(reset=True)` |
| `_engine`, `_SessionLocal` | `db/__init__.py:22-23` | `init_database()` | Global DB engine. No re-init guard |
| `_vector_db` | `knowledge/vector_db.py:463` | Module-level factory | ChromaDB singleton |
| `_metrics_collector` | `monitoring/metrics.py:448` | `get_metrics_collector()` | Global metrics |

---

## Configuration Surface

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ANTHROPIC_API_KEY` | env | LLM provider auth; all-9s = CLI mode | None (required) |
| `LLM_PROVIDER` | env | Provider: anthropic/openai/litellm | `"anthropic"` |
| `MAX_RESEARCH_ITERATIONS` | env | Research loop limit | `10` |
| `RESEARCH_BUDGET_USD` | env | API cost cap | `10.0` |
| `DATABASE_URL` | env | DB location | `sqlite:///kosmos.db` |
| `ENABLE_CONCURRENT_OPERATIONS` | env | Parallel hypothesis eval + experiments | `False` |
| `MAX_CONCURRENT_EXPERIMENTS` | env | Parallel experiment slots | `10` |
| `WORLD_MODEL_ENABLED` | env | Neo4j knowledge graph | `True` |
| `KOSMOS_SKILLS_DIR` | env | Custom skills directory | None |
| `DEBUG_MODE` | env | Verbose logging | `False` |

---

## Conventions

1. **Always inherit BaseAgent** for new agents. Call `super().__init__(agent_id, agent_type, config)`. Override `execute()`. [PATTERN: 6/6 agents]
2. **Always use get_client()** for LLM access — never instantiate providers directly. [PATTERN: 6/6 agents]
3. **Always use get_session() context manager** for DB access — auto-commits on success, rolls back on error. [PATTERN: 12/12 DB-accessing modules]
4. **Agents receive flat config dicts**, not KosmosConfig objects. Flatten via `self.config.get("key", default)`. [PATTERN: 6/6 agents]
5. **Optional dependencies: try/except ImportError** with `HAS_FEATURE` flag and graceful degradation. [PATTERN: 8/8 optional deps]
6. **Data models have dual representation**: Pydantic (kosmos/models/) for runtime, SQLAlchemy (kosmos/db/models.py) for storage. Convert via `model_to_dict()`. [PATTERN: 3/3 core entities]
7. **Async/sync dual API**: Async methods are primary, sync wrappers use `asyncio.run()` or `run_coroutine_threadsafe()`. [PATTERN: observed in base.py, research_director.py]

---

## Gotchas

1. **Config flattening** — Agents receive flat dicts, NOT KosmosConfig. The flattening happens manually in `run.py:148-170`. Missing keys silently use defaults. [FACT] (`cli/commands/run.py:148`)
2. **CLI mode detection** — API key of all 9s (`999...`) routes through Claude Code CLI, not Anthropic API. Detected via `api_key.replace('9','') == ''`. [FACT] (`config.py:82`, `core/llm.py:179`)
3. **Dual locking** — ResearchDirector maintains BOTH `asyncio.Lock` AND `threading.RLock` for the same resources. asyncio.Lock is NOT reentrant. [FACT] (`agents/research_director.py:193-200`)
4. **2-hour hardcoded timeout** — `run.py:301` has `max_loop_duration=7200` separate from the configurable `max_runtime_hours`. The hardcoded value wins if lower. [FACT] (`cli/commands/run.py:301`)
5. **LLMResponse acts like str** — `LLMResponse` delegates `strip()`, `lower()`, `__contains__`, etc. to its `.content` field. Callers may not realize they have a response object. [FACT] (`core/providers/base.py:80-153`)
6. **Circular dependency** — `core/llm.py` ↔ `core/providers/anthropic.py` import from each other (both import model name constants from `config.py`). [FACT] (xray circular deps)
7. **signal.alarm on Windows** — Execution timeout uses `signal.alarm()` which is UNIX-only. On Windows, code execution has NO timeout. [FACT] (`execution/executor.py:13`)
8. **Hypothesis validation rejects questions** — `Hypothesis.statement` field validator rejects strings ending with `?`. [FACT] (`models/hypothesis.py:94`)
9. **Database must be initialized first** — `get_session()` raises `RuntimeError` if called before `init_database()`. ResearchDirector auto-inits, but standalone scripts may forget. [FACT] (`db/__init__.py:127`)
10. **generate_hypotheses auto-writes DB** — `store_in_db=True` by default. Every hypothesis generation writes to the database. [FACT] (`agents/hypothesis_generator.py:147`)

---

## Hazards — Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `agents/research_director.py` | ~30K | Use skeleton view. Module index above covers behavior. |
| `execution/data_analysis.py` | ~10K | Leaf analysis module. Behavior described in traces above. |
| `execution/code_generator.py` | ~10K | LLM-based code generation. Well-contained. |
| `evaluation/scientific_evaluation.py` | ~14K | Evaluation script. Trace T1.5 covers the pipeline. |
| `workflow/ensemble.py` | ~10K | Ensemble research — advanced feature, rarely needed. |
| `kosmos-reference/**` | ~200K+ | NOT imported by core. Historical reference implementations. |

---

## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| Add new agent | `agents/base.py` → create new class | `agents/registry.py`, `research_director.py` dispatch | Must register in AgentRegistry; flat config dict |
| Add new LLM provider | `core/providers/base.py` → implement ABC | `core/providers/factory.py`, `config.py` | Add config class + env vars; update get_provider_from_config |
| Add new experiment type | `models/experiment.py` → add to ExperimentType enum | `experiments/templates/`, `agents/experiment_designer.py` | Templates in experiments/templates/{domain}/ |
| Add new domain | Skills scripts in `kosmos-claude-scientific-skills/` | `agents/skill_loader.py`, `config.py` enabled_domains | Must update ENABLED_DOMAINS or domain validation warns |
| Add new CLI command | `cli/commands/` → new file | `cli/main.py` (register with typer app) | Use Typer decorators; console from `cli/utils.py` |

---

## Reading Order

1. `config.py` — All configuration knobs and env var bindings
2. `agents/base.py` — Agent lifecycle, message protocol
3. `core/workflow.py` — State machine: the research cycle
4. `core/llm.py` (first 200 lines) — LLM client patterns, get_client()
5. `cli/commands/run.py` — How CLI launches research

**Skip:** `kosmos-reference/` (not imported by core), `alembic/versions/` (DB migrations), `tests/` (207 files, standard pytest)

---

## Gaps

- No rate limiting on LLM API calls (only per-minute cap via config, no enforcement observed) [ABSENCE: grep rate_limit — only config fields, no middleware]
- No global crash reporter or exception aggregation — errors stay in per-module logs [ABSENCE]
- World model (Neo4j) integration is optional and largely untested — silently skipped when unavailable
- Circular dependency between llm.py and providers/anthropic.py — fragile import ordering
- 617 bare except/pass patterns across 120 files — broad error swallowing risk [FACT]

---

*Generated by deep_crawl agent. 31 tasks, 15 modules read, 5 traces verified.
Compression: 2,455,608 → ~6K tokens (~400:1).
Evidence: 18 [FACT], 8 [PATTERN], 2 [ABSENCE].*
