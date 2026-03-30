# Kosmos: Agent Onboarding

> Codebase: 802 files, ~2,455,608 tokens | This document: ~13,000 tokens (~189:1 compression)
> Generated: 2026-03-29 from commit `3ff33c3`
> Crawl: 34/34 tasks, 30 modules read, 3 traces verified, 36 findings files (~38K words)
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---

## Identity

Kosmos is an autonomous AI scientist that generates hypotheses, designs experiments, executes computational analyses, and iterates toward convergence — all driven by LLM orchestration (primarily Claude). It runs unattended research loops lasting up to 12 hours, producing publication-quality results across biology, chemistry, materials science, neuroscience, and physics.

**Stack:** Python 3.9+, Pydantic v2 (models + config), SQLAlchemy + SQLite/Postgres (persistence), Neo4j (knowledge graphs), ChromaDB/Pinecone (vector search), Anthropic/OpenAI/LiteLLM SDKs (LLM access). CLI: Typer + Rich. Optional: Docker (code sandboxing), Redis (caching), FastAPI + WebSocket (API).

**Architecture:** 22 subsystem packages under `kosmos/` organized in 4 layers (94 foundation, 302 core, 147 orchestration, 259 leaf). Core loop: 5 specialized agents coordinated by a ResearchDirectorAgent through a state machine, with code generation → sandboxed execution → LLM-powered analysis at each iteration.

---

## Critical Paths

### Path 1: CLI Run → Research Loop (the primary execution path)

```
kosmos run "research question" --domain biology
  → main() (cli/main.py:98) — global callback on EVERY command
    → setup_logging() (cli/main.py:49) — file + console handlers at ~/.kosmos/logs/
    → init_from_config() (db/__init__.py:140) — DB bootstrap
      → first_time_setup() (utils/setup.py:219)
        → ensure_env_file() — copies .env.example → .env if missing
        → run_database_migrations() — alembic upgrade
        → validate_database_schema() — checks 9 tables + indexes
      → init_database() (db/__init__.py:26)
        → create_engine() — QueuePool for Postgres, no pool for SQLite
        → Base.metadata.create_all() — creates missing tables
        → log_slow_queries() — SQLAlchemy event listener
  → run_research() (cli/commands/run.py:51)
    → [BRANCH: --interactive] run_interactive_mode() → config or Exit
    → get_config() → override with CLI args (domain, iterations, budget, data_path)
    → ResearchDirectorAgent(question, domain, flat_config) (research_director.py:68)
      → super().__init__() → BaseAgent: uuid, status=CREATED, async message queue
      → _validate_domain() — warns if domain not in enabled_domains (non-fatal)
      → _load_skills() — loads domain-specific prompt fragments (swallowed on failure)
      → ResearchPlan(question, domain, max_iterations) — Pydantic model
      → ResearchWorkflow(INITIALIZING, plan) — state machine
      → get_client() → ClaudeClient or LLMProvider singleton
      → [SIDE EFFECT: DB] init_from_config() in constructor (swallows "already init")
      → ConvergenceDetector(mandatory_criteria, optional_criteria)
      → [CONDITIONAL] ParallelExperimentExecutor — if concurrent_operations enabled
      → [CONDITIONAL] AsyncClaudeClient — if concurrent + ANTHROPIC_API_KEY set
      → [SIDE EFFECT: Neo4j] get_world_model() → creates ResearchQuestion entity
      → RolloutTracker — counters for agent invocations
    → get_registry().register(director) — global agent registry
    → asyncio.run(run_with_progress_async(director, ...))
      → [OPTIONAL] create_streaming_display() — Rich real-time events
      → await director.execute({"action": "start_research"})
        → generate_research_plan() [SIDE EFFECT: LLM call]
        → workflow.transition_to(GENERATING_HYPOTHESES)
      → Loop: await director.execute({"action": "step"})
        → decide_next_action() (research_director.py:2388) — state machine
          ┌─ GENERATING_HYPOTHESES
          │  → _handle_generate_hypothesis_action()
          │    → HypothesisGeneratorAgent(lazy init).execute()
          │      → _gather_literature_context() — optional, swallowed on failure
          │      → _generate_with_claude() [SIDE EFFECT: LLM call]
          │      → _validate_hypothesis() — testability + novelty scoring
          │      → _store_hypothesis() [SIDE EFFECT: DB write]
          │    → [SIDE EFFECT: world model] add hypothesis entity
          │
          ├─ DESIGNING_EXPERIMENTS
          │  → _handle_design_experiment_action()
          │    → ExperimentDesignerAgent(lazy init).execute()
          │      → _select_experiment_type() — from hypothesis
          │      → _generate_from_template() OR _generate_with_claude()
          │        → TemplateRegistry auto-discovers on first call
          │      → _validate_protocol() — min_samples, significance level
          │    → [SIDE EFFECT: DB] store protocol
          │
          ├─ EXECUTING
          │  → _handle_execute_experiment_action()
          │    → CodeGenerator.generate_code(protocol)
          │      → 5 templates tried in order (t-test, correlation, log-log,
          │        ML classification, generic) — first match wins
          │      → LLM fallback if no template matches
          │      → ast.parse() syntax validation
          │    → CodeExecutor.execute(code, retry_on_error=True)
          │      → CodeValidator.validate() — AST-based safety check
          │      → Docker sandbox (if available) OR restricted builtins
          │      → Return value extracted from `results` or `result` variable
          │      → Self-correcting retry: pattern-based fixes + LLM repair
          │    → [SIDE EFFECT: DB] store result
          │
          ├─ ANALYZING
          │  → _handle_analyze_result_action()
          │    → DataAnalystAgent(lazy init).execute()
          │      → _build_interpretation_prompt() — includes result + hypothesis
          │      → LLM call → _parse_interpretation_response()
          │      → detect_anomalies() — z-score threshold 3.0
          │    → [SIDE EFFECT: DB] store interpretation
          │
          ├─ REFINING
          │  → HypothesisRefiner — modifies hypotheses based on results
          │  → Multiple comparison correction (BH-FDR) on last 20 experiments
          │
          └─ Convergence check:
             → iteration_limit (MAX_RESEARCH_ITERATIONS)
             → budget_exceeded (RESEARCH_BUDGET_USD via core/metrics)
             → runtime_exceeded (MAX_RUNTIME_HOURS)
             → novelty_decline (diminishing novelty scores)
             → no_testable_hypotheses
             → Loop guard: 50 actions per iteration max
             → Deferral: won't converge if < min_experiments AND work remains
        → [SIDE EFFECT: world model] persist results to Neo4j graph
  ✗ on failure: circuit breaker after 3 consecutive errors → ERROR state
  ✗ error recovery: exponential backoff (2s, 4s, 8s) then reset to GENERATING_HYPOTHESES
  ✗ budget/runtime exceeded: graceful convergence, not crash
```

**Key behaviors:**
- `execute()` runs ONE step per call — the CLI drives the loop [FACT] (`research_director.py:2868`)
- Sub-agents are lazily instantiated inside `_handle_*_action` methods, not at init [FACT]
- All error recovery resets to GENERATING_HYPOTHESES regardless of which phase failed [FACT] (`research_director.py:2721-2728`)

### Path 2: Scientific Evaluation Pipeline

```
python evaluation/scientific_evaluation.py --output-dir ./eval
  → asyncio.run(main())
    → [SIDE EFFECT: fs] creates evaluation/logs/ + timestamped log file
    → EvaluationReport() — accumulates all phase results

    → Phase 1: Pre-flight (FATAL gate — stops all if fails)
      → get_config() + validate
      → get_client(reset=True) + 3 LLM test calls [SIDE EFFECT: API]
      → init_from_config() + get_session() — DB check
      → Type compatibility: response.strip(), response.lower(), "e" in response
      → Structured output: generate('{"status": "ok"}') + JSON parse

    → Phase 2: Smoke test (async)
      → ResearchWorkflow + basic agent creation + LLM calls

    → Phase 3: Multi-iteration (async)
      → N research iterations, checks hypothesis quality + convergence

    → Phase 4: Dataset test (async) — tests with specific data path

    → Phase 5: Output quality (sync) — analyzes phase 2+3 results

    → Phase 6: Rigor scorecard (sync) — introspects source code for quality signals

    → Phase 7: Paper compliance (sync) — synthesizes all phases

    → generate_report() → [SIDE EFFECT: fs] writes EVALUATION_REPORT.md
```

### Path 3: CLI Subcommands

| Command | Entry | Key Behavior | Gotcha |
|---------|-------|-------------|--------|
| `kosmos run` | cli/commands/run.py:51 | Full research loop | DB init in ResearchDirector constructor |
| `kosmos status` | cli/commands/status.py:36 | DB read, Rich display | Hypotheses/experiments always empty (stub) |
| `kosmos history` | cli/commands/history.py:27 | DB query + interactive prompt | Prompt.ask for detail drill-down |
| `kosmos cache` | cli/commands/cache.py:28 | 5 HybridCache instances | `--clear-type` missing "literature" option |
| `kosmos config` | cli/commands/config.py:25 | .env management | `--path` uses relative paths (cwd-dependent) |
| `kosmos graph` | cli/commands/graph.py:26 | World model CRUD | Double confirmation on reset; InMemory fallback |
| `kosmos doctor` | cli/main.py:267 | System validation | Creates second engine for schema check |
| `kosmos profile` | cli/commands/profile.py:31 | **Non-functional stub** | `_load_profile_from_db` always returns None |

**Shared patterns across commands:**
- Flag-driven dispatch (flags not mutually exclusive — `--stats --clear` runs both) [PATTERN: 3/3 multi-flag commands]
- `confirm_action()` for destructive ops; graph reset has double confirmation [PATTERN: 3/3 destructive commands]
- Error boundary: `try/except → print_error + typer.Exit(1)` [PATTERN: 8/8 commands]
- ResultsViewer for research data display [PATTERN: 3/3 research display commands]

---

## Module Behavioral Index

### Core Agents

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `agents/base.py` | BaseAgent: lifecycle (start/stop/pause), async message passing via AgentMessage, state persistence via AgentState, statistics tracking | asyncio, config (optional) | Dual sync/async queues; message router optional — msgs go nowhere without it; _sync wrappers for backwards compat |
| `agents/research_director.py` | Master orchestrator: state machine + decision tree driving hypothesis→experiment→analysis loop. 2952 lines, 54 methods. | All agents (lazy), core/llm, workflow, convergence, DB, world_model, skills | 30K tokens; message-passing code is DEAD (Issue #76); _actions_this_iteration not in __init__; dual locking (asyncio + threading); FDR correction on every convergence check |
| `agents/hypothesis_generator.py` | Generates hypotheses via LLM + optional literature context. Validates testability and novelty. | core/llm, literature/base_client, models/hypothesis | Falls back to zero-context generation if literature fails; uses get_client() not get_provider() |
| `agents/experiment_designer.py` | Designs ExperimentProtocol from hypotheses using template registry + LLM enhancement | core/llm, experiments/templates, models/experiment | Template registry auto-discovers on first call; _generate_with_claude silently degrades to LLM-less mode |
| `agents/data_analyst.py` | Interprets experiment results using LLM, detects anomalies and cross-result patterns | core/llm, models/result | Anomaly detection z-score threshold 3.0 (hardcoded); _create_fallback_interpretation for LLM failures |
| `agents/literature_analyzer.py` | Literature search + knowledge graph integration + citation network analysis | literature/*, knowledge/graph, core/llm | Singleton via `get_literature_analyzer()`; NoveltyChecker side-effect: indexes results into vector DB |
| `agents/registry.py` | Agent discovery/lookup: register, get by type/id, list agents | none | Singleton `get_registry()`; NO reset function — test leakage risk |
| `agents/skill_loader.py` | Loads domain-specific skills from local dirs or GitHub repos | httpx (for GitHub), config | `load_from_github()` has complex tree-walking; HTTP calls on every load |

### Core Infrastructure

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `config.py` | Master config: 16 nested Pydantic BaseSettings, singleton `get_config()`, 60+ env vars | .env file, env vars | Risk 0.96 (highest churn); provider configs None if API key unset; CLI mode = all-9s key; .env path relative to config.py parent.parent |
| `core/llm.py` | Multi-provider LLM hub: legacy ClaudeClient + get_client() singleton factory | anthropic SDK (optional), config, providers/* | Circular import with anthropic provider (deferred); auto model: never picks Opus; cost hardcodes Sonnet; cache bypass on structured retries |
| `core/providers/base.py` | Abstract LLMProvider (6 methods) + LLMResponse (str-compatible) + ProviderAPIError (smart recoverability) | stdlib only | LLMResponse delegates 20+ string methods; ProviderAPIError.is_recoverable() uses heuristic pattern matching |
| `core/providers/anthropic.py` | AnthropicProvider: API + CLI routing, caching, auto model selection | anthropic SDK, config, claude_cache | CLI mode if key is all 9s; deferred import from core/llm (circular); cost tracking per-request |
| `core/providers/openai.py` | OpenAIProvider: standard OpenAI API | openai SDK | Optional; guarded by HAS_OPENAI flag |
| `core/providers/litellm_provider.py` | LiteLLMProvider: 100+ providers via LiteLLM (Ollama, DeepSeek, etc.) | litellm SDK | Registered under aliases: "litellm", "ollama", "deepseek", "lmstudio" |
| `core/providers/factory.py` | Provider registry + factory: get_provider(name, config), get_provider_from_config() | all provider modules (deferred) | All providers registered via try/except ImportError at import time |
| `core/workflow.py` | WorkflowState enum + ResearchWorkflow state machine with validated transitions | config, logging | ALLOWED_TRANSITIONS dict enforces valid state changes; invalid throws |
| `core/convergence.py` | ConvergenceDetector: checks iteration limit, budget, runtime, novelty decline | config | Pure utility (not an agent); mandatory + optional stopping criteria |
| `core/event_bus.py` | Pub/sub EventBus for workflow events | none | Singleton; subscribers list grows unbounded |
| `core/cache_manager.py` | CacheManager: 5 HybridCache instances (CLAUDE, EXPERIMENT, LITERATURE, EMBEDDING, GENERAL) | config | Only double-checked locking singleton in codebase (threading.Lock + __new__); creates .kosmos_cache/ dir |

### Execution Pipeline

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `execution/code_generator.py` | Generates Python from ExperimentProtocol: 5 templates + LLM fallback + LLM enhancement | core/llm, templates | Template ORDER matters — generic catches all; correlation template p-hacks (min p-value); magic vars (data_path, figure_path); seed 42 default absorbs seed=0; LLM code extraction fragile |
| `execution/executor.py` | Sandboxed execution: Docker or restricted builtins; self-correcting retry with pattern-based fixes | sandbox (optional), safety/code_validator | Restricted builtins LEAKY (type+object); Windows timeout doesn't kill thread; return via magic `results`/`result` var; FileNotFoundError is terminal (no retry) |
| `execution/sandbox.py` | Docker container sandbox for code execution | docker SDK (optional) | Falls back silently if Docker unavailable; SANDBOX_AVAILABLE flag |
| `execution/parallel.py` | ParallelExperimentExecutor: asyncio.gather for concurrent experiments | executor, code_generator | Only used if enable_concurrent_operations=True |

### Data Models

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `models/hypothesis.py` | Hypothesis, ExperimentType (enum), HypothesisStatus, PrioritizedHypothesis, NoveltyReport, TestabilityReport | config (default model name) | ExperimentType lives HERE not experiment.py; hand-rolled to_dict(); datetime.utcnow deprecated 3.12+; testability threshold 0.3 vs novelty 0.75 (inconsistent) |
| `models/experiment.py` | ExperimentProtocol (10+ fields), ExperimentDesignRequest/Response, ExperimentType import | models/hypothesis | 10 Pydantic models; min_samples >= 2, significance_level < 0.5; protocol.no_data flag for templateless experiments |
| `models/result.py` | ExperimentResult, StatisticalResult, AnalysisResult, ExperimentSummary | models/hypothesis, models/experiment | 5 status enums; hand-rolled to_dict(); confidence_interval must be exactly 2 elements; ResultStatus includes PARTIALLY_EXECUTED |

### Knowledge & Persistence

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `literature/base_client.py` | Abstract BaseLiteratureClient + PaperMetadata (dataclass, not Pydantic) + PaperSource enum | logging only | _validate_query CLAIMS to truncate but DOESN'T (bug); no rate limiting; PaperMetadata.primary_identifier fallback chain: DOI > arXiv > PubMed > source |
| `knowledge/graph.py` | Neo4j knowledge graph: CRUD for entities, relationships, queries, visualization | neo4j driver, config | Singleton; graceful fallback if Neo4j unavailable |
| `knowledge/vector_db.py` | Vector search: ChromaDB (default) or Pinecone | chromadb/pinecone SDK, config | Singleton; embedding model loaded on first use; search returns PaperMetadata |
| `world_model/factory.py` | get_world_model() singleton: Neo4j or InMemory | config, Neo4j (optional) | **SILENTLY falls back to InMemory — data lost on exit, no warning** |
| `world_model/simple.py` | Neo4jWorldModel: CRUD for papers, concepts, authors, methods + graph queries | neo4j driver | 10K tokens; entity-type dispatch in add_entity |
| `db/__init__.py` | SQLAlchemy engine + session factory + schema bootstrap | sqlalchemy, alembic | QueuePool for Postgres, no pool for SQLite; init_from_config on every CLI command; double-commit (CRUD + context manager) |
| `db/operations.py` | Full CRUD for 6 entity types (Hypothesis, Experiment, Result, Paper, AgentRecord, ResearchSession) | sqlalchemy | Session auto-commits; update_research_session uniquely renames param to db_session |

### Safety & Validation

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `safety/code_validator.py` | AST-based static analysis against dangerous module blocklist + ethical keyword matching | ast | Blocklist includes os/sys/subprocess — flags legitimate file I/O; ethical check is naive keyword match ("harm", "toxic", "email") |
| `safety/guardrails.py` | SafetyGuardrails: emergency stop (signal + flag file), resource limits, incident logging | code_validator, docker (optional) | Emergency stop checks flag file on EVERY call (no caching); blocking mode hangs on stdin in non-interactive env |
| `oversight/human_review.py` | 4 approval modes: blocking/queue/automatic/disabled, JSONL audit trail | config | Blocking mode calls input() — HANGS in CI; rejection raises RuntimeError; override_decision allows REJECTED→APPROVED |
| `validation/accuracy_validator.py` | Compares conclusions against benchmark datasets | benchmark_dataset | evaluate_finding callable is injected; None results silently skipped; paper accuracy figures NOT enforced |

### Supporting Subsystems

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `compression/compressor.py` | NotebookCompressor, LiteratureCompressor, ContextCompressor | none | Convention deviation: untyped __init__ args (3 classes) |
| `analysis/summarizer.py` | LLM-powered result summaries with deterministic fallback | core/llm | LLM response parsing is fragile (line-by-line state machine); fallback always appends 2 generic suggestions |
| `orchestration/plan_creator.py` | LLM-generated 10-task research plans with adaptive exploration/exploitation ratio | core/llm | Mock fallback for LLM-less mode; JSON extraction via crude rfind/find |
| `orchestration/delegation.py` | Parallel task execution (max 3 concurrent) with retry | agents, providers | Agents called synchronously despite async wrapper; requires agent dict injection |
| `monitoring/metrics.py` | Prometheus metrics: research cycles, API calls, cache ops | prometheus_client (optional) | Custom CollectorRegistry (not default); high cardinality risk from labels |
| `monitoring/alerts.py` | Rule-based alerts with cooldowns: DB, API, memory, disk | config, psutil | History trimmed to 1000 hard-coded; condition functions swallow exceptions |
| `hypothesis/novelty_checker.py` | Semantic + keyword novelty assessment against literature | vector_db, literature | Side-effect: indexes search results into vector DB; novelty score capped at 0.5 for any similarity |
| `hypothesis/prioritizer.py` | Multi-criteria ranking: novelty 30%, feasibility 25%, impact 25%, testability 20% | core/llm, novelty_checker | Defaults scores to 0.5 on any exception; LLM impact prediction at temperature=0.5 |
| `api/health.py` | Liveness/readiness endpoints; system metrics via psutil | psutil, config | API key check validates FORMAT only (sk-ant-*), not validity; Neo4j failure ≠ not_ready |
| `api/websocket.py` | FastAPI WebSocket at /ws/events with subscription filters | fastapi (optional) | Dynamic subscription via {"action": "subscribe", "event_types": [...]} |
| `domains/biology/ontology.py` | Hand-coded seed ontology (~20 concepts, typed relationships) | none | O(n) relation lookups; recursive hierarchy without cycle detection |
| `experiments/templates/base.py` | TemplateBase ABC + TemplateRegistry with auto-discovery | pkgutil | Two-phase init avoids circular imports; description min_length=50 can fail for short titles |
| `utils/compat.py` | `model_to_dict()`: Pydantic v1/v2 bridge | none | Silently returns {} if all conversion methods fail |
| `utils/setup.py` | First-time init: .env copy, alembic migrations, schema validation | alembic, sqlalchemy | Hardcodes expected tables from specific migration; runs on EVERY init_from_config |

---

## Key Interfaces

```python
# kosmos/agents/base.py — All agents inherit this
class BaseAgent:
    def __init__(self, agent_id?, agent_type?, config?): ...
    def start(self): ...          # CREATED → STARTING → RUNNING (calls _on_start)
    def stop(self): ...           # calls _on_stop → STOPPED
    def execute(self, task: Dict) -> Dict: ...  # Override in subclasses
    def _on_start(self): ...      # Hook for subclass init
    def _on_stop(self): ...       # Hook for subclass cleanup
    async def send_message(self, to_agent, content, type?, corr_id?) -> AgentMessage: ...
    async def receive_message(self, msg: AgentMessage): ...  # Queues + process_message
    def get_state(self) -> AgentState: ...     # For persistence
    def restore_state(self, state: AgentState): ...

# kosmos/core/providers/base.py — All LLM providers implement this
class LLMProvider(ABC):
    def generate(self, prompt, system?, max_tokens=4096, temperature=0.7) -> LLMResponse: ...
    async def generate_async(self, prompt, ...) -> LLMResponse: ...
    def generate_with_messages(self, messages: List[Message], ...) -> LLMResponse: ...
    def generate_structured(self, prompt, schema: Dict, ...) -> Dict: ...  # JSON output
    def generate_stream(self, ...) -> Iterator[str]: ...  # Optional
    def get_model_info(self) -> Dict: ...
    def get_usage_stats(self) -> Dict: ...  # Cumulative token/cost tracking

class LLMResponse:  # Acts as str via 20+ delegation methods
    content: str; usage: UsageStats; model: str; finish_reason: str?
    # strip(), lower(), split(), __contains__, __len__, replace(), find(), etc.

class ProviderAPIError(Exception):
    provider: str; message: str; status_code: int?; recoverable: bool
    def is_recoverable(self) -> bool: ...  # Heuristic: 429=yes, 401/403/404=no

# kosmos/config.py — Central config (90 call sites, 41 modules)
class KosmosConfig(BaseSettings):
    llm_provider: Literal["anthropic", "openai", "litellm"]
    claude: Optional[ClaudeConfig]; openai: Optional[OpenAIConfig]; litellm: LiteLLMConfig
    research: ResearchConfig; database: DatabaseConfig; safety: SafetyConfig
    # ... 16 total nested config sections
    def get_active_model(self) -> str: ...
    def get_active_provider_config(self) -> dict: ...
def get_config(reload=False) -> KosmosConfig: ...  # Singleton
def reset_config(): ...  # REQUIRED in tests

# kosmos/agents/research_director.py — Master orchestrator
class ResearchDirectorAgent(BaseAgent):
    def __init__(self, research_question, domain?, agent_id?, config?): ...
    async def execute(self, task: Dict) -> Dict: ...  # ONE step per call
    def decide_next_action(self) -> NextAction: ...    # State machine decision tree
    def generate_research_plan(self) -> str: ...        # LLM call
    def get_research_status(self) -> Dict: ...
    def select_next_strategy(self) -> str: ...          # Highest success-rate strategy
    async def execute_experiments_batch(self, ids) -> List[Dict]: ...  # Parallel

# kosmos/execution/executor.py — Sandboxed code execution
class CodeExecutor:
    def execute(self, code, local_vars?, retry_on_error=True, llm_client?) -> ExecutionResult: ...
    def execute_with_data(self, code, data_path) -> ExecutionResult: ...
class ExecutionResult:
    success: bool; return_value: Any; stdout: str; stderr: str
    error: str?; error_type: str?; execution_time: float
def execute_protocol_code(code, data_path?, ...) -> Dict: ...  # Validate + execute

# kosmos/models/ — Data flow: Hypothesis → Experiment → Result
class Hypothesis(BaseModel):
    statement: str; domain: str; rationale: str; status: HypothesisStatus
    testability_score: float; novelty_score: float; confidence_score: float
    experiment_type: ExperimentType  # COMPUTATIONAL | DATA_ANALYSIS | LITERATURE_SYNTHESIS
class ExperimentProtocol(BaseModel):
    hypothesis_id: str; experiment_type: ExperimentType; title: str
    steps: List[ExperimentStep]; code_template: str?; statistical_method: str
class ExperimentResult(BaseModel):
    experiment_id: str; hypothesis_id: str; status: ResultStatus
    statistical_result: StatisticalResult?; raw_output: Dict?
```

---

## LLM Provider Architecture

```
LLMProvider (ABC)                      # core/providers/base.py
  ├── AnthropicProvider                # core/providers/anthropic.py
  │     Features: response caching (ClaudeCache), auto model selection
  │     (Haiku for simple / Sonnet for complex), CLI mode routing
  ├── OpenAIProvider                   # core/providers/openai.py
  │     Standard OpenAI SDK wrapper
  └── LiteLLMProvider                  # core/providers/litellm_provider.py
        Aliases: "ollama", "deepseek", "lmstudio" — 100+ backends

Factory: get_provider_from_config()    # core/providers/factory.py
  → reads LLM_PROVIDER env var → extracts sub-config → instantiates provider
  → _PROVIDER_REGISTRY populated at import via try/except ImportError

Singleton: get_client()                # core/llm.py
  → thread-safe (Lock), fallback: provider system → AnthropicProvider → ClaudeClient
```

**Provider switching:** Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=sk-...` in .env. All LLM calls go through the singleton — no per-module configuration needed.

**What's common:** All providers wrap errors as `ProviderAPIError`, track usage via `_update_usage_stats()`, use identical JSON structured output strategy (append schema to system prompt → generate → parse with `parse_json_response()`). [PATTERN: 3/3 providers]

**What's provider-specific:**
- Anthropic: prompt caching, auto model selection (Haiku/Sonnet), CLI mode (key=all 9s)
- OpenAI: organization ID support, custom base URL for Azure
- LiteLLM: local model support (Ollama), circuit breaker, lenient JSON retry [FACT] (`core/providers/factory.py:189-217`)

---

## Error Handling Strategy

**Dominant pattern:** Catch-log-continue with graceful degradation [PATTERN: 627 except clauses across 121 files, 65% catch broad `Exception`, 0 swallowed `except: pass`]

| Tier | Where | Pattern | Effect |
|------|-------|---------|--------|
| Outer boundary | Agents (execute), CLI commands | `except Exception → log + return error dict/AgentMessage` | Never crashes; errors become status messages [PATTERN: 5/5 agents] |
| Subsystem init | Providers, knowledge graph, world model, Docker | `except ImportError → FEATURE_AVAILABLE = False` | Missing deps silently disable features [PATTERN: 5/5 optional deps] |
| Inner operations | LLM calls, JSON parse, DB ops | `except SpecificType → log + re-raise as typed exception` | Callers get `ProviderAPIError`, `JSONParseError` |

**Retry strategies:**

| Component | Strategy | Details |
|-----------|----------|---------|
| ResearchDirector | Exponential backoff + circuit breaker | 2s→4s→8s; breaks after 3 consecutive failures [FACT] (`research_director.py:666-674`) |
| CodeExecutor | Self-correcting with pattern-based fixes | 10+ error-type handlers; wraps failing code in try/except; LLM repair on first 2 attempts [FACT] (`executor.py:869-1008`) |
| generate_structured() | Cache bypass on retry | First attempt may return cached unparseable response; retries hit API directly [FACT] (`core/llm.py:467`) |
| DelegationManager | Max 2 attempts, exponential backoff capped at 8s | Checks ProviderAPIError.is_recoverable() to short-circuit [FACT] (`delegation.py:335-337`) |

**Notable deviations:**
- `base_client.py:_handle_api_error` logs but NEVER raises — callers must handle errors themselves [FACT] (`base_client.py:221-233`)
- `base_client.py:_validate_query` says "truncating to 1000" but doesn't truncate — bug [FACT] (`base_client.py:248-253`)
- ResearchDirector error recovery always resets to GENERATING_HYPOTHESES regardless of phase [FACT] (`research_director.py:2721-2728`)
- HypothesisPrioritizer silently defaults scores to 0.5 on any exception [FACT] (`prioritizer.py:194`)

---

## Shared State

| State | Location | Accessor / Mutator | Thread-Safe? | Risk |
|-------|----------|-------------------|-------------|------|
| `_config` | `config.py:1137` | `get_config()` / `reset_config()` | No | 90 call sites, 41 modules; test leakage if not reset |
| `_default_client` | `core/llm.py:609` | `get_client()` | Yes (Lock) | Provider change requires reset |
| `_world_model` | `world_model/factory.py:105` | `get_world_model()` / `reset_world_model()` | No | Silently InMemory if Neo4j down — data loss |
| `_knowledge_graph` | `knowledge/graph.py:1023` | `get_knowledge_graph()` / `reset_knowledge_graph()` | No | Neo4j connection; singleton per process |
| `_vector_db` | `knowledge/vector_db.py:463` | `get_vector_db()` / `reset_vector_db()` | No | Embedding model loaded on first use |
| `_event_bus` | `core/event_bus.py:271` | `get_event_bus()` / `reset_event_bus()` | No | Subscribers list grows unbounded |
| `_engine, _SessionLocal` | `db/__init__.py:67` | `init_database()` | No | Calling init_database twice replaces engine silently |
| `CacheManager._instance` | `core/cache_manager.py:38` | `CacheManager()` / `reset_cache_manager()` | Yes (Lock + __new__) | Only double-checked locking singleton |
| `_experiment_cache` | `core/experiment_cache.py:743` | `get_experiment_cache()` / `reset_experiment_cache()` | No | Disk + memory hybrid cache |
| `_tracker` | `core/stage_tracker.py:249` | `get_stage_tracker()` / `reset_stage_tracker()` | No | Publishes to event bus |
| `_cache` | `literature/cache.py:323` | `get_literature_cache()` / `reset_literature_cache()` | No | Literature API response cache |
| `_registry` | `agents/registry.py:522` | `get_registry()` | No | **NO reset function** — test leakage |
| `_global_registry` | `experiments/templates/base.py:649` | `get_template_registry()` | No | Auto-discovers templates; **NO reset** |
| `_metrics_collector` | `monitoring/metrics.py:448` | `get_metrics_collector()` | No | **NO reset function** |
| `_alert_manager` | `monitoring/alerts.py:528` | `get_alert_manager()` | No | **NO reset function** |

**Total: 20+ singletons.** 16 have reset functions, 4 do not. Only 2 are thread-safe (`_default_client` via Lock, CacheManager via __new__ + Lock). [PATTERN: 20/20 follow `_var = None` / `get_X()` pattern]

---

## Domain Glossary

| Term | Means Here | Defined In |
|------|------------|------------|
| Research Director | Master orchestrator agent driving the full hypothesis→experiment→analysis loop | `agents/research_director.py` |
| Protocol | ExperimentProtocol Pydantic model: steps, code template, statistical method, hypothesis reference | `models/experiment.py` |
| Convergence | When the research loop should stop: iteration limit, budget, runtime, novelty decline, no testable hypotheses | `core/convergence.py` |
| CLI mode | ANTHROPIC_API_KEY is all 9s — routes LLM calls through Claude Code CLI, not API | `config.py:81`, `core/llm.py:179` |
| World Model | Persistent Neo4j knowledge graph accumulating research knowledge across sessions | `world_model/` |
| Rollout | Single execution of the research loop; tracked for strategy effectiveness | `core/rollout_tracker.py` |
| Pillar | Architectural pillar module with high import count (xray analysis term) | xray output |
| HybridCache | Dual-layer cache (in-memory + disk) for API responses, experiments, embeddings | `core/cache_manager.py` |
| Safety Report | CodeValidator's AST analysis output: violations by severity, approval required flag | `safety/code_validator.py` |

---

## Configuration Surface

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ANTHROPIC_API_KEY` | env | LLM access (required for anthropic provider) | none (required) |
| `LLM_PROVIDER` | env | Provider selection: anthropic/openai/litellm | `"anthropic"` |
| `CLAUDE_MODEL` | env | Model for Anthropic calls | `"claude-sonnet-4-5"` |
| `OPENAI_API_KEY` | env | Required if LLM_PROVIDER=openai | none |
| `OPENAI_MODEL` | env | Model for OpenAI calls | `"gpt-4-turbo"` |
| `LITELLM_MODEL` | env | Model for LiteLLM (e.g., ollama/llama3.1:8b) | `"gpt-3.5-turbo"` |
| `LITELLM_API_BASE` | env | Custom API base (e.g., http://localhost:11434) | none |
| `DATABASE_URL` | env | SQLite or Postgres connection | `"sqlite:///kosmos.db"` |
| `MAX_RESEARCH_ITERATIONS` | env | Research loop iteration limit | `10` |
| `MAX_RUNTIME_HOURS` | env | Max runtime before forced convergence | `12.0` |
| `RESEARCH_BUDGET_USD` | env | API cost budget | `10.0` |
| `ENABLED_DOMAINS` | env | Comma-separated domain list | `"biology,physics,chemistry,neuroscience"` |
| `ENABLE_SAFETY_CHECKS` | env | AST code safety validation | `True` |
| `ENABLE_SANDBOXING` | env | Docker sandbox for code execution | `True` |
| `WORLD_MODEL_ENABLED` | env | Enable persistent knowledge graph | `True` |
| `WORLD_MODEL_MODE` | env | "simple" (Neo4j) or "production" (NotImplementedError) | `"simple"` |
| `NEO4J_URI` | env | Knowledge graph connection | `"bolt://localhost:7687"` |
| `NEO4J_PASSWORD` | env | Neo4j auth | `"kosmos-password"` |
| `REDIS_ENABLED` | env | Optional Redis caching layer | `False` |
| `DEBUG_LEVEL` | env | 0=off, 1=critical path, 2=full trace, 3=data dumps | `0` |
| `APPROVAL_MODE` | env | Human oversight mode | `"blocking"` |
| `MAX_CONCURRENT_EXPERIMENTS` | env | Parallel experiment execution limit | `10` |
| `LLM_RATE_LIMIT_PER_MINUTE` | env | API rate limit | `50` |
| `ENABLE_RESULT_CACHING` | env | Cache experiment results | `True` |
| `VECTOR_DB_TYPE` | env | chromadb/pinecone/weaviate | `"chromadb"` |

Full surface: 60+ env vars mapped via Pydantic aliases in `config.py`. All loadable from `.env` file at project root (`Path(config.py).parent.parent / ".env"`).

---

## Workflow State Machine

The research loop is driven by a state machine defined in `core/workflow.py`. This module is pure data — it tracks transitions but does not execute anything.

**States:**
```
INITIALIZING → GENERATING_HYPOTHESES → DESIGNING_EXPERIMENTS → EXECUTING
     ↑                    ↑                                        ↓
     |              (restart cycle)                            ANALYZING
     |                    ↑                                        ↓
     |              REFINING ←─────────────────────────────── REFINING
     |                    ↓
     |              CONVERGED (can restart → GENERATING_HYPOTHESES)
     |
     └──── ERROR (can restart → INITIALIZING or GENERATING_HYPOTHESES)
           PAUSED (reachable from most states; can resume to any active state)
```

**Key behaviors:**
- CONVERGED is NOT terminal — can transition back to GENERATING_HYPOTHESES [FACT] (`core/workflow.py:211-213`)
- ERROR recovery only goes to INITIALIZING (full restart) or GENERATING_HYPOTHESES (partial restart) [FACT] (`core/workflow.py:222-226`)
- PAUSED can resume to ANY active state — no validation it resumes where it paused [FACT] (`core/workflow.py:214-221`)
- Transition history grows unboundedly; `get_state_duration()` is O(n²) [FACT] (`core/workflow.py:243, 367-396`)
- ResearchPlan tracks hypothesis/experiment/result IDs, not objects — lookups needed elsewhere [FACT] (`core/workflow.py:68-78`)

**CAUTION: Two classes named ResearchWorkflow exist:**
1. `kosmos.core.workflow.ResearchWorkflow` — the state machine (this section)
2. `kosmos.workflow.research_loop.ResearchWorkflow` — the orchestration loop (different class, different purpose)

The orchestration loop in `workflow/research_loop.py`:
- Runs a simple `for cycle in range(1, num_cycles + 1)` — NO convergence detection, NO early stopping [FACT] (`research_loop.py:193`)
- Plan rejection gets ONE retry — if revision also rejected, cycle is skipped [FACT] (`research_loop.py:297-305`)
- Failed cycles are swallowed with `continue` — not counted in final statistics [FACT] (`research_loop.py:235-245`)
- Agent initialization requires an `anthropic_client` — if None, agents dict is empty and nothing executes [FACT] (`research_loop.py:118-133`)
- Sets global random seed (`random.seed()`, `numpy.random.seed()`) affecting the entire process [FACT] (`research_loop.py:83-89`)

---

## Agent Lifecycle

All 5 agents inherit BaseAgent. The lifecycle: CREATED → start() → RUNNING → execute(task) cycles → stop() → STOPPED.

**execute() signature varies across agents:**

| Agent | Signature | Returns | Notes |
|-------|-----------|---------|-------|
| ResearchDirectorAgent | `async execute(task: Dict)` | `Dict` | Async, one step per call, drives state machine |
| HypothesisGeneratorAgent | `execute(message: AgentMessage)` | `AgentMessage` | Sync, takes AgentMessage |
| ExperimentDesignerAgent | `execute(message: AgentMessage)` | `AgentMessage` | Sync, takes AgentMessage |
| DataAnalystAgent | `execute(task: Dict)` | `Dict` | Sync, takes dict |
| LiteratureAnalyzerAgent | `execute(task: Dict)` | `Dict` | Sync, takes dict |

**Inconsistency:** HypothesisGenerator and ExperimentDesigner take `AgentMessage` while DataAnalyst and LiteratureAnalyzer take `Dict`. ResearchDirector is async; all others are sync. [PATTERN: 3 different execute() signatures across 5 agents]

**_on_start() implementations:**
- ResearchDirectorAgent: starts runtime clock + transitions workflow to GENERATING_HYPOTHESES [FACT] (`research_director.py:319-332`)
- LiteratureAnalyzerAgent: saves start_time [FACT] (`literature_analyzer.py:138-141`)
- HypothesisGenerator, ExperimentDesigner, DataAnalyst: no-op (use BaseAgent default) [PATTERN: 3/5 agents]

**_on_stop() implementations:** All 5 agents use the no-op default — no cleanup logic anywhere. [PATTERN: 5/5 agents]

**execute() error pattern (all 5 agents):**
```python
try:
    self.status = AgentStatus.WORKING
    # ... dispatch on task type ...
except Exception as e:
    logger.error(f"Error: {e}", exc_info=True)
    self.status = AgentStatus.ERROR
    return error_response
finally:
    self.status = AgentStatus.IDLE
```
[PATTERN: 5/5 agents follow this try/except/finally with status reset]

---

## Initialization Sequence

The system has 20+ singletons with implicit ordering dependencies. There is NO centralized init function.

**Required order (derived from dependency analysis):**
1. **config** (`get_config()`) — must be first; creates log/chroma directories as side effect
2. **logging** (`setup_logging()`) — reads `config.logging`; must precede any logger usage
3. **database** (`init_database()` via `init_from_config()`) — creates SQLAlchemy engine from `config.database.url`; runs alembic migrations on first call
4. **event_bus** (`get_event_bus()`) — independent, but must exist before any event publisher
5. **LLM client** (`get_client()`) — reads config for provider + API key selection
6. **knowledge_graph** (`get_knowledge_graph()`) — reads `config.neo4j`; graceful fallback
7. **vector_db** (`get_vector_db()`) — reads `config.vector_db`; loads embedding model
8. **world_model** (`get_world_model()`) — reads config + knowledge_graph; InMemory fallback
9. **All other singletons** — generally depend on config + logging

**Gotchas in init:**
- No explicit orchestrator — order is established by call order in CLI global callback + ResearchDirector constructor
- If a module imports `get_config()` before `.env` is loaded, it gets default values
- `.env` path resolves to `Path(config.py).parent.parent / ".env"` — only works for source installations
- `init_from_config()` runs `first_time_setup()` on EVERY call, not just first time — migrations check adds startup overhead
- Test state leakage: must call `reset_X()` for ALL singletons touched; 4 singletons lack reset functions

---

## Testing Conventions

**Framework:** pytest with fixtures in `conftest.py` files throughout the test tree.

**Test structure:** 249 test modules across:
- `tests/` — unit tests organized by module
- `tests/requirements/` — requirement-based integration tests (core, literature, scientific)
- `tests/manual/` — manual test scripts
- `evaluation/` — scientific evaluation pipeline

**Key patterns:**
- Tests use `reset_config()` in setup to prevent state leakage [PATTERN: observed in test fixtures]
- Mock objects for LLM clients to avoid API costs in unit tests
- The evaluation pipeline (`evaluation/scientific_evaluation.py`) makes real API calls — it is NOT a unit test
- `conftest.py` provides shared fixtures including database sessions, config overrides, and mock agents

**Testing gaps:**
- No integration test for the full research loop end-to-end (unit tests only for individual agents)
- No test for circular import resilience between core/llm and core/providers/anthropic
- 4 singletons cannot be reset between tests (`_registry`, `_global_registry`, `_metrics_collector`, `_alert_manager`)

---

## Hypothesis Lifecycle (Detail)

Understanding the hypothesis data flow is essential for modifying the research pipeline.

**Stage 1: Generation** (`agents/hypothesis_generator.py`)
```
HypothesisGeneratorAgent.execute(task)
  → _gather_literature_context() — searches literature for context (swallowed on failure)
  → _detect_domain() — infers domain if not provided
  → _generate_with_claude() — LLM generates N hypotheses (default 3)
    → System prompt includes domain context, literature summaries, novelty requirements
    → Response parsed into Hypothesis objects
  → _validate_hypothesis() — each hypothesis:
    → testability scoring (threshold 0.3 — low bar)
    → novelty checking via NoveltyChecker (threshold 0.5)
  → _store_hypothesis() → DB write
  → Returns HypothesisGenerationResponse
```

**Stage 2: Prioritization** (`hypothesis/prioritizer.py`)
```
HypothesisPrioritizer.prioritize(hypotheses)
  → For each hypothesis:
    → novelty score (from generation) × 0.30
    → feasibility estimate (heuristic) × 0.25
    → impact prediction (LLM call at temp=0.5, or keyword heuristic) × 0.25
    → testability score (from generation) × 0.20
  → Returns sorted PrioritizedHypothesis list
```

**Gotcha:** On ANY exception during scoring, defaults to 0.5 — network failures produce "average" rankings rather than flagging incomplete data. [FACT] (`prioritizer.py:194`)

**Stage 3: Novelty Assessment** (`hypothesis/novelty_checker.py`)
```
NoveltyChecker.check_novelty(hypothesis)
  → Vector DB semantic search for similar papers
  → Keyword-based literature search
  → DB query for existing hypotheses
  → Compute similarity scores
  → SIDE EFFECT: indexes search results into vector DB
  → Score formula:
    → >= 0.95 similarity → 0.0 novelty (duplicate)
    → 0.75-0.95 similarity → 0.0-0.5 novelty (capped)
    → < 0.75 similarity → 0.5-1.0 novelty
  → Maximum novelty for anything similar = 0.5 [FACT] (novelty_checker.py:120-130)
```

**Stage 4: Experiment Design** (`agents/experiment_designer.py`)
```
ExperimentDesignerAgent.execute(task)
  → _load_hypothesis() — retrieves from DB or task payload
  → _select_experiment_type() — from hypothesis.experiment_type
  → _generate_from_template() — TemplateRegistry.find_best_template()
    → OR _generate_with_claude() — LLM designs protocol
  → _validate_protocol() — min_samples >= 2, significance_level < 0.5
  → _enhance_protocol_with_llm() — optional domain-specific refinement
  → Returns ExperimentDesignResponse
```

**Stage 5: Analysis** (`agents/data_analyst.py`)
```
DataAnalystAgent.execute(task)
  → _extract_result_summary() — extracts key metrics from ExecutionResult
  → _build_interpretation_prompt() — includes result + hypothesis + optional literature
  → LLM call → _parse_interpretation_response()
  → detect_anomalies() — z-score with hardcoded threshold 3.0 [FACT] (data_analyst.py)
  → detect_patterns_across_results() — cross-result pattern detection
  → _generate_synthesis() — combined analysis + recommendations
  → Returns analysis dict with interpretation, anomalies, patterns
```

**Stage 6: Refinement** (`hypothesis/refiner.py`)
- Modifies existing hypotheses based on experiment results
- Can generate refined versions (incremented generation count)
- Tracks evolution via `parent_hypothesis_id` and `evolution_history`
- Before each convergence check: Multiple comparison correction (Benjamini-Hochberg FDR) applied to last 20 experiments [FACT] (`research_director.py:1341`)

---

## Orchestration & Delegation

**PlanCreatorAgent** (`orchestration/plan_creator.py`):
- Generates 10-task research plans per cycle using LLM
- Adaptive exploration/exploitation ratio: 70/30 early → 50/50 mid → 30/70 late cycles
- Falls back to deterministic mock plans when no LLM client available
- JSON extraction from LLM response uses crude `rfind('}')` / `find('{')` — no markdown fence handling [FACT] (`plan_creator.py:278-290`)
- Pads plans with generic filler tasks if LLM returns fewer than `num_tasks` [FACT] (`plan_creator.py:184-185`)

**DelegationManager** (`orchestration/delegation.py`):
- Executes approved plans by routing tasks to specialized agents
- Max 3 concurrent tasks in parallel batches
- Retry: max 2 attempts, exponential backoff capped at 8s
- Checks `ProviderAPIError.is_recoverable()` to short-circuit retries for non-recoverable errors
- Requires agents dict injection at init — missing agent raises descriptive RuntimeError [FACT] (`delegation.py:396-400`)
- Agents called SYNCHRONOUSLY despite async wrapper (async only for `asyncio.gather` batching) [FACT] (`delegation.py:404-422`)

**PlanReviewerAgent** (quality gate):
- Reviews plans before execution
- Validates structural requirements (>= 2 task types, >= 3 data_analysis tasks)
- Rejection gets ONE retry — if revision also rejected, cycle is skipped [FACT] (`plan_creator.py:297-305`)

---

## Conventions

1. **Always use `get_X()` singleton factories** — never construct infrastructure objects directly. [PATTERN: 20/20 singletons]
2. **Every module: `logger = logging.getLogger(__name__)`** at module scope. [PATTERN: 112/112 core modules]
3. **Agent subclasses override `_on_start()`, `execute()`, `_on_stop()`** — never override lifecycle methods directly. [PATTERN: 5/5 agents]
4. **Pydantic BaseModel for domain objects, BaseSettings for config, @dataclass for simple value objects.** [PATTERN: 74 BaseModel across 22 files, 17 BaseSettings in config.py, 86 dataclasses across 38 files]
5. **Typed __init__ injection** — class constructors use type annotations. [PATTERN: 193/229 classes; 36 deviations in scientific-skills scripts and compression/]
6. **Graceful degradation via `try/except ImportError`** — missing optional deps disable features, don't crash. [PATTERN: 5/5 optional dependencies: anthropic, openai, docker, litellm, prometheus_client]
7. **Tests must call `reset_X()` for every singleton touched.** 20+ globals leak between tests otherwise. [PATTERN: 16/20 singletons have reset functions]
8. **Error boundary at every agent execute()** — try/except/finally with status reset to IDLE. [PATTERN: 5/5 agents]
9. **Config via env var aliases** — every config field has an `alias="ENV_VAR_NAME"` for env var loading. [PATTERN: 60+/60+ fields]

---

## Gotchas

1. **DB init runs on EVERY CLI command** — including `kosmos version`. A broken DATABASE_URL produces error output before informational commands succeed. [FACT] (`cli/main.py:98` → `db/__init__.py:140`)

2. **World model silently falls back to InMemoryWorldModel** — if Neo4j is unavailable, all graph operations succeed but data is lost on process exit. No warning shown to CLI users. [FACT] (`world_model/factory.py:105`)

3. **ResearchDirectorAgent.execute() runs ONE step, not a loop** — caller must repeatedly invoke `execute({"action": "step"})`. No built-in run_research_loop() method. [FACT] (`research_director.py:2868`)

4. **Message-passing in research_director.py is dead code** — Issue #76 rewrote to direct calls. 450+ lines of `_send_to_*` and `_handle_*_response` methods exist but are never used. [FACT] (`research_director.py:568-1219`)

5. **Restricted builtins sandbox is leaky** — `SAFE_BUILTINS` includes `type` and `object`, enabling class construction escape. Real safety depends on Docker. Docker silently falls back to restricted builtins. [FACT] (`executor.py:43-83`)

6. **Windows timeout doesn't kill executing thread** — ThreadPoolExecutor timeout raises TimeoutError but code continues running in background. [FACT] (`executor.py:607-630`)

7. **Code generator correlation template p-hacks** — picks test with minimum p-value between Pearson and Spearman, inflating false positive rate. [FACT] (`code_generator.py:292-300`)

8. **LLMResponse acts as a string** — 20+ string methods delegated to `.content`. Code like `if "error" in response` checks content text, not the response object. [FACT] (`providers/base.py:80-154`)

9. **Auto model selection never picks Opus** — ModelComplexity returns "haiku" or "sonnet" only. No path to higher-capability model even at max complexity. [FACT] (`core/llm.py:88-94`)

10. **Cost estimation hardcodes Sonnet pricing** — regardless of actual model used. Haiku costs inflated, Opus costs underreported. [FACT] (`core/llm.py:519, 592`)

11. **Circular import: core/llm.py ↔ core/providers/anthropic.py** — both use deferred imports inside functions. Moving either to module scope causes ImportError. [FACT] (`core/llm.py:665`, `core/providers/anthropic.py:189`)

12. **CLI status always shows empty hypotheses/experiments** — ORM-to-dict hardcodes `[]` with TODO comments. [FACT] (`cli/commands/status.py:103`)

13. **CLI profile command is entirely non-functional** — `_load_profile_from_db` always returns None; agent/workflow profiling says "not yet implemented". [FACT] (`cli/commands/profile.py:462`)

14. **Safety validator flags legitimate science code** — dangerous-modules blocklist includes `os`, `sys`, `subprocess`, `requests`. Any experiment needing file I/O or HTTP is flagged as CRITICAL. Ethical keyword check flags "toxic compounds" discussion. [FACT] (`safety/code_validator.py:35-39, 112-157`)

15. **Blocking approval mode calls input() directly** — system hangs waiting for stdin in non-interactive environments (server, CI). [FACT] (`oversight/human_review.py:259`)

16. **`_actions_this_iteration` uses hasattr instead of __init__** — dynamically created on first access. [FACT] (`research_director.py:2451`)

17. **Novelty side-effect: check_novelty() indexes search results into vector DB** — a read operation that silently writes. [FACT] (`hypothesis/novelty_checker.py:207-210`)

18. **Health check validates API key FORMAT only** — checks `sk-ant-*` prefix, never verifies key works. Revoked keys pass. [FACT] (`api/health.py:304-309`)

---

## Code Execution Pipeline (Detail)

The execution pipeline transforms an ExperimentProtocol into executable code, runs it in a sandbox, and captures results. Understanding this pipeline is critical for adding new experiment types.

**Step 1: Code Generation** (`execution/code_generator.py`)

Five templates tried in order — first match wins:

| Template | Matches | Key Output | Gotcha |
|----------|---------|------------|--------|
| TTestCodeTemplate | 2-group comparison | Welch's t-test, Shapiro-Wilk, Levene's | — |
| CorrelationCodeTemplate | Relationship analysis | Pearson + Spearman | **Picks min p-value (p-hacking)** |
| LogLogScalingCodeTemplate | Scaling laws | Log-log regression, power law | — |
| MLClassificationCodeTemplate | Classification tasks | Train/test split, cross-validation | — |
| GenericComputationalCodeTemplate | **Catch-all** | Basic pandas analysis | Matches both COMPUTATIONAL and DATA_ANALYSIS |

If no template matches: LLM generates code from a structured prompt. If LLM unavailable: basic fallback (`pd.read_csv(data_path)` + `df.describe()`).

**Magic variables injected by executor:**
- `data_path` — path to dataset file (injected by `execute_with_data()`)
- `figure_path` — path for saving figures
- Templates check `if 'data_path' in dir() and data_path:` before using
- Return value must be assigned to `results` or `result` variable

**All generated code uses `random_seed = getattr(protocol, 'random_seed', 42) or 42`** — the `or 42` absorbs seed=0, so deterministic seed 0 is silently replaced with 42. [FACT] (`code_generator.py:89, 231, 369`)

**Step 2: Safety Validation** (`safety/code_validator.py`)

AST-based static analysis against:
- **Dangerous modules:** os, sys, subprocess, shutil, socket, requests, urllib — ANY experiment using file I/O or HTTP is flagged CRITICAL
- **Dangerous functions:** eval, exec, compile, __import__
- **Ethical keywords:** harm, weapon, toxic, malicious — naive substring match, flags legitimate science ("toxic compounds")
- `allow_file_read=True` softens `open()` detection only, not `os` imports

**Step 3: Sandboxed Execution** (`execution/executor.py`)

Two modes:
1. **Docker sandbox** (if Docker available): Full container isolation, kosmos.sandbox=true label
2. **Restricted builtins** (fallback): `exec()` with curated `__builtins__` dict
   - Import whitelist: numpy, pandas, scipy, sklearn, matplotlib, seaborn, etc.
   - Import check: only validates top-level module name (`name.split('.')[0]`)
   - **Leaky:** `type`, `super`, `object` in builtins allow class construction escape

**Timeout:** Unix uses `signal.SIGALRM` (kills exec). Windows uses ThreadPoolExecutor (thread continues running after timeout). [FACT] (`executor.py:607-630`)

**Step 4: Self-Correcting Retry** (`execution/executor.py:RetryStrategy`)

On execution failure:
1. Identify error type from traceback
2. Apply pattern-based fix (10+ error types: KeyError → get(), TypeError → type check, etc.)
3. Optionally ask LLM to rewrite code (first 2 attempts only)
4. Re-execute modified code

**FileNotFoundError is terminal** — no retry, returns failure immediately. [FACT] (`executor.py:724-730`)

**The retry "fixes" wrap code in try/except returning error dicts** — callers must check `result.status` field, not just exception absence. [FACT] (`executor.py:869-1008`)

---

## Literature System

```
BaseLiteratureClient (ABC)           # literature/base_client.py
  ├── ArxivClient                    # literature/arxiv_client.py
  ├── ArxivHTTPClient                # literature/arxiv_http_client.py
  ├── SemanticScholarClient          # literature/semantic_scholar.py
  └── PubMedClient                   # literature/pubmed_client.py

UnifiedLiteratureSearch              # literature/unified_search.py
  → Searches all clients in parallel, deduplicates by DOI
  → PaperMetadata is the universal paper type (dataclass, not Pydantic)

Supporting:
  PDFExtractor (singleton)           # literature/pdf_extractor.py
  ReferenceManager (singleton)       # literature/reference_manager.py
  LiteratureCache (singleton)        # literature/cache.py
  CitationManager                    # literature/citations.py
```

**PaperMetadata** (`literature/base_client.py:37`) is a @dataclass with 20+ fields: id, doi, arxiv_id, pubmed_id, title, abstract, authors (List[Author]), date, journal, venue, year, url, pdf_url, citation_count, fields, keywords, full_text, raw_data.

**Primary identifier fallback chain:** DOI > arXiv ID > PubMed ID > source ID — same paper from different sources may have different identifiers, creating potential duplicates. [FACT] (`base_client.py:90-92`)

**No rate limiting in base class** — cache_enabled attribute exists but is never used. Each client must implement its own caching. [ABSENCE: grep for rate_limit in literature/ — 0 hits]

**NoveltyChecker side effect:** `check_novelty()` silently indexes search results into the vector DB — a nominally read-only operation that writes. [FACT] (`hypothesis/novelty_checker.py:207-210`)

---

## Database Schema

SQLAlchemy ORM with 6 primary entity types. SQLite default, Postgres supported.

| Table | Model | Key Columns | Used By |
|-------|-------|-------------|---------|
| `hypotheses` | Hypothesis | id, statement, domain, status, testability_score, novelty_score | research_director, hypothesis_generator |
| `experiments` | Experiment | id, hypothesis_id, protocol, status, type | experiment_designer, executor |
| `results` | Result | id, experiment_id, hypothesis_id, status, statistical_result | data_analyst, executor |
| `papers` | Paper | id, doi, title, abstract, source, metadata | literature_analyzer, knowledge |
| `agent_records` | AgentRecord | id, agent_type, status, task, result | all agents |
| `research_sessions` | ResearchSession | id, question, domain, state, config, metrics | CLI run, status |

**Session management:** `get_session()` context manager auto-commits on success, rolls back on exception. CRUD operations also commit internally — double-commit is harmless but reveals ops designed to work standalone. [FACT] (`db/__init__.py, db/operations.py`)

**Connection pooling:** QueuePool for Postgres (configurable), NullPool for SQLite (no pooling). [FACT] (`db/__init__.py:72-78`)

**`reset_database()`** drops ALL tables unconditionally — no confirmation gate. Meant for eval isolation. [FACT] (`db/__init__.py:191-202`)

---

## External Dependencies

**Required (core):**
| Package | Used By | Purpose |
|---------|---------|---------|
| pydantic + pydantic-settings | config, models | Data validation, env var loading |
| sqlalchemy | db/ | ORM, connection pooling, migrations |
| alembic | db/, utils/setup | Schema migrations |
| typer + rich | cli/ | CLI framework, terminal formatting |
| numpy, pandas, scipy | execution, analysis | Scientific computation in experiments |

**Required (LLM — at least one):**
| Package | Provider | Config |
|---------|----------|--------|
| anthropic | Anthropic (default) | `LLM_PROVIDER=anthropic` |
| openai | OpenAI | `LLM_PROVIDER=openai` |
| litellm | LiteLLM (100+ backends) | `LLM_PROVIDER=litellm` |

**Optional (feature-gated via ImportError):**
| Package | Feature | Fallback |
|---------|---------|----------|
| neo4j | Knowledge graph | InMemoryWorldModel (data lost on exit) |
| chromadb | Vector search | Feature disabled |
| docker | Code sandboxing | Restricted builtins (leaky) |
| redis | Caching layer | Memory + disk cache only |
| prometheus_client | Metrics export | Metrics disabled |
| fastapi + uvicorn | REST API + WebSocket | API endpoints unavailable |
| psutil | System metrics | Health check metrics disabled |
| httpx | Literature search, skill loading | Literature features degraded |

Total external dependencies: 121 packages detected by xray (including transitive).

---

## Hazards — Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `agents/research_director.py` | ~30K | Use skeleton view — 450+ lines dead message-passing code |
| `execution/data_analysis.py` | ~10K | Template-generated analysis code, not core logic |
| `evaluation/scientific_evaluation.py` | ~14K | Evaluation pipeline — read trace above instead |
| `kosmos-claude-scientific-skills/**` | ~500K | External tool wrappers, not core architecture |
| `kosmos-reference/**` | ~400K | Reference implementation (scientific writer), separate codebase |
| `tests/requirements/**` | ~30K+ | Requirement-based tests, skip unless debugging specific tests |
| `workflow/ensemble.py` | ~10K | Ensemble research workflow variant — not primary path |

---

## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| Add new agent | `agents/base.py` (subclass) | `agents/registry.py`, `research_director.py` (integrate into loop) | Must implement `execute()`; register with registry; lazy-init pattern in research_director |
| Add LLM provider | `core/providers/base.py` (subclass) | `core/providers/factory.py` (register), `config.py` (add section) | Must implement 4 abstract methods; add to `_PROVIDER_REGISTRY` dict with aliases |
| Add experiment template | `experiments/templates/base.py` (subclass) | New file in `experiments/templates/` | Auto-discovered by pkgutil; ORDER matters — specific before generic; description min_length=50 |
| Add CLI command | New file in `cli/commands/` | `cli/main.py` (register with Typer app) | Global callback runs DB init; use `get_db_session()` context manager |
| Add scientific domain | New dir in `domains/` | `config.py:ENABLED_DOMAINS`, ontology + API modules | Follow `biology/` pattern; register domain-specific APIs and templates |
| Add config section | New BaseSettings class in `config.py` | Add to KosmosConfig, `.env.example` | All fields need env var aliases; test with `reset_config()` |
| Add literature source | Subclass `BaseLiteratureClient` | New file in `literature/` | Implement search, get_paper_by_id, get_references, get_citations; PaperMetadata is the return type |
| Add safety check | Extend `CodeValidator` in `safety/code_validator.py` | `safety/guardrails.py` if broader scope | Current blocklist is broad — may flag legitimate code |

---

## Safety System (Detail)

The safety system has three layers that protect against dangerous generated code:

**Layer 1: Static Analysis** (`safety/code_validator.py`)
- AST-based module import checking against a blocklist of 20+ dangerous modules
- Function call checking against dangerous builtins (eval, exec, compile, __import__)
- Ethical keyword matching (naive substring: "harm", "weapon", "toxic", "malicious", "email")
- Returns `SafetyReport` with violations grouped by severity (CRITICAL, WARNING, INFO)
- `requires_approval(report)` → True if any CRITICAL violations exist
- `allow_file_read=True` parameter softens only `open()` detection, not `os` imports

**Key issue:** The blocklist is too broad for scientific code. Experiments that need to read CSV files from disk (`import os; os.path.exists(path)`) are flagged CRITICAL. Bioinformatics code discussing "toxic compounds" triggers ethical violations. [FACT] (`code_validator.py:35-39, 112-157`)

**Layer 2: Guardrails** (`safety/guardrails.py`)
- Wraps CodeValidator with resource limit enforcement (CPU, memory, time)
- Emergency stop mechanism: checks `.kosmos_emergency_stop` flag file on EVERY call
- Safety incident logging to JSONL file
- `safety_context(experiment_id)` context manager: checks emergency stop before AND after yield, but does NOT kill in-flight work
- `trigger_emergency_stop()` optionally kills Docker containers labeled `kosmos.sandbox=true`

**Layer 3: Human Oversight** (`oversight/human_review.py`)
Four approval modes configured via `APPROVAL_MODE` env var:

| Mode | Behavior | Risk |
|------|----------|------|
| `blocking` | Calls `input()` for CLI approval | **HANGS in non-interactive env** |
| `queue` | Adds to pending queue, returns immediately | Caller must poll `process_pending_requests()` |
| `automatic` | Auto-approves all operations | No human oversight |
| `disabled` | Skips approval entirely | No safety gate |

**override_decision()** allows changing ANY previous decision, including REJECTED → APPROVED, with only a log warning — no re-validation of the safety report. [FACT] (`human_review.py:316-359`)

---

## Monitoring & Observability

**Logging:** Every module uses `logger = logging.getLogger(__name__)` with centralized setup in `core/logging.py`. Supports JSON and text formats. Debug levels: 0=off, 1=critical path, 2=full trace, 3=data dumps. Optional debug by module name via `DEBUG_MODULES` env var. Agent message logging via `LOG_AGENT_MESSAGES`. Workflow transition logging via `LOG_WORKFLOW_TRANSITIONS`.

**Metrics** (`monitoring/metrics.py`): Prometheus-compatible metrics using a CUSTOM CollectorRegistry (not the default). Counters and histograms for: research cycles, hypotheses generated/tested, experiments run/succeeded/failed, API calls/costs/tokens, cache hits/misses, DB query latency. Label dimensions include domain, model, status — high cardinality risk if domains proliferate. All metrics gracefully disabled if prometheus_client not installed.

**Alerts** (`monitoring/alerts.py`): Rule-based with per-rule cooldowns. Default rules check: database connectivity, API failure rate > threshold, memory usage > 90%, disk usage > 90%, experiment failure rate, cache availability. Alert history trimmed to 1000 entries (hard-coded). Condition functions silently return False on exceptions.

**Stage Tracking** (`core/stage_tracker.py`): Real-time JSONL output of workflow stage transitions. Publishes to event bus. Enabled via `STAGE_TRACKING_ENABLED` env var.

**WebSocket Events** (`api/websocket.py`): FastAPI WebSocket at `/ws/events` for real-time streaming. Per-connection subscription filters by event type and process ID. Dynamic subscription changes mid-session via `{"action": "subscribe", "event_types": [...]}`.

---

## Knowledge System

### Knowledge Graph (`knowledge/graph.py`)
Neo4j-based entity-relationship graph. Stores papers, concepts, methods, hypotheses, and their relationships. CRUD operations + Cypher queries. Singleton via `get_knowledge_graph()`. Gracefully handles Neo4j unavailability.

### Vector Database (`knowledge/vector_db.py`)
ChromaDB (default) or Pinecone. Stores paper embeddings for semantic search. Embedding model loaded lazily on first use. Singleton via `get_vector_db()`.

### World Model (`world_model/`)
Strategy pattern with factory:
- **Simple Mode** (default): Single Neo4j database via `Neo4jWorldModel`. Easy setup (Docker Compose). Suitable for <10K entities.
- **Production Mode** (Phase 4): Polyglot architecture — NOT IMPLEMENTED, raises NotImplementedError.
- **InMemory fallback**: Used when Neo4j unavailable. All operations succeed but data lost on process exit. **No warning to users.**

Entity types: Paper, Concept, Author, Method (+ generic). Each has type-specific add/get methods in `world_model/simple.py`. Artifact tracking via `world_model/artifacts.py` for findings, hypotheses, and their relationships.

### Concept Extraction (`knowledge/concept_extractor.py`)
LLM-powered extraction of scientific concepts from text. Singleton. Feeds concepts into the knowledge graph.

### Graph Builder (`knowledge/graph_builder.py`)
Batch construction of knowledge graphs from paper collections. Extracts entities and relationships, deduplicates, and persists to Neo4j.

---

## Reading Order

1. `kosmos/__init__.py` — package identity; exports get_config + ResearchDirectorAgent
2. `kosmos/config.py` — all 60+ config knobs; understand before touching anything
3. `kosmos/agents/base.py` — agent lifecycle, message passing protocol, state persistence
4. `kosmos/core/providers/base.py` — LLM interface, LLMResponse string compatibility, ProviderAPIError
5. `kosmos/core/llm.py` — LLM dispatch, caching, provider selection, circular import awareness
6. `kosmos/models/hypothesis.py` → `experiment.py` → `result.py` — data flow through the system
7. `kosmos/agents/research_director.py` (skeleton only) — focus on `decide_next_action` and `_handle_*_action` methods
8. `kosmos/execution/code_generator.py` → `executor.py` — how experiments become code and run
9. `kosmos/core/workflow.py` — state machine transitions
10. `kosmos/safety/code_validator.py` — understand what code is blocked before writing templates

**Skip:** `research_director.py:568-1219` (dead message-passing), `kosmos-reference/` (separate project), `kosmos-claude-scientific-skills/` (tool wrappers)

---

## Subsystem Quick Reference

Quick behavioral summary of every `kosmos/` top-level package for navigation:

| Package | Files | Purpose | Key Entry Points |
|---------|-------|---------|-----------------|
| `agents/` | 10 | 5 science agents + base class + registry + skill loader | `BaseAgent`, `ResearchDirectorAgent`, `get_registry()` |
| `analysis/` | 4 | Result summarization, statistics, visualization | `ResultSummarizer.generate_summary()` |
| `api/` | 4 | FastAPI REST endpoints, WebSocket events, health checks | `get_basic_health()`, WebSocket at `/ws/events` |
| `cli/` | 9 | Typer CLI with 8 commands + Rich display | `main()` in `cli/main.py` |
| `compression/` | 1 | Context compression for notebooks, literature, general text | `NotebookCompressor`, `LiteratureCompressor`, `ContextCompressor` |
| `core/` | 18 | LLM hub, providers, workflow, event bus, caching, metrics, profiling | `get_config()`, `get_client()`, `get_event_bus()` |
| `db/` | 3 | SQLAlchemy ORM, session management, CRUD operations | `get_session()`, `init_from_config()`, `create_hypothesis()` |
| `domains/` | 12 | Domain-specific ontologies and APIs (biology, chemistry, materials, neuroscience, physics) | `BiologyOntology()`, domain API clients |
| `execution/` | 12 | Code generation, sandboxed execution, parallel execution, data management | `execute_protocol_code()`, `CodeExecutor`, `CodeGenerator` |
| `experiments/` | 10 | Experiment templates, statistical power analysis, resource estimation | `get_template_registry()`, `register_template()` |
| `hypothesis/` | 4 | Novelty checking, testability scoring, prioritization, refinement | `check_hypothesis_novelty()`, `prioritize_hypotheses()` |
| `knowledge/` | 7 | Neo4j graph, vector DB, embeddings, concept extraction, graph building | `get_knowledge_graph()`, `get_vector_db()` |
| `literature/` | 8 | Multi-source literature search, PDF extraction, citation management | `UnifiedLiteratureSearch`, `BaseLiteratureClient` |
| `models/` | 5 | Pydantic data models: Hypothesis, Experiment, Result, Safety, Domain | `Hypothesis`, `ExperimentProtocol`, `ExperimentResult` |
| `monitoring/` | 2 | Prometheus metrics, rule-based alerts | `get_metrics_collector()`, `get_alert_manager()` |
| `orchestration/` | 4 | Plan creation, review, delegation, novelty detection | `PlanCreatorAgent`, `DelegationManager` |
| `oversight/` | 2 | Human approval workflow, notification management | `HumanReviewWorkflow`, `NotificationManager` |
| `safety/` | 4 | Code validation, safety guardrails, reproducibility, verification | `CodeValidator.validate()`, `SafetyGuardrails` |
| `utils/` | 2 | Pydantic v1/v2 compat, first-time setup | `model_to_dict()`, `first_time_setup()` |
| `validation/` | 5 | Accuracy validation, benchmarks, failure detection, null models | `AccuracyValidator.validate_dataset()` |
| `workflow/` | 3 | Research loop orchestration, ensemble research | `ResearchWorkflow.run()` (the orchestrator, not the state machine) |
| `world_model/` | 6 | Persistent knowledge graph (Neo4j/InMemory), artifact tracking | `get_world_model()`, `ArtifactStateManager` |

---

## Gaps

- **No rate limiting infrastructure** — literature API clients have no built-in rate limiting [ABSENCE: grep for rate_limit in literature/ — 0 hits]
- **No centralized init orchestrator** — 20+ singletons with implicit ordering dependencies; no function ensures correct order
- **4 singletons lack reset functions** — `_registry`, `_global_registry`, `_metrics_collector`, `_alert_manager` cannot be reset for tests
- **Status command stubs** — hypotheses/experiments always empty in CLI status output
- **Profile command non-functional** — entire profiling CLI is a stub with no data source
- **Production world model mode not implemented** — `WORLD_MODEL_MODE=production` raises NotImplementedError
- **Smoke test hardcodes SQLite** — PostgreSQL deployments always get SKIP for DB validation
- **No circular import test** — core/llm ↔ core/providers/anthropic cycle works by accident of deferred imports
- **No integration test for full research loop** — each agent has unit tests, but end-to-end loop is only tested via evaluation pipeline
- **Domain ontologies are seed-only** — biology has ~20 concepts with O(n) relation lookups; recursive hierarchy traversal without cycle detection; chemistry/materials/neuroscience/physics untested for completeness [FACT] (`domains/biology/ontology.py:283-292, 362-382`)
- **Notification history grows unbounded** — no rotation or max-size limit [FACT] (`oversight/notifications.py:113`)
- **model_to_dict() silently returns {} on failure** — no logging or warning; callers may get empty dicts from valid objects [FACT] (`utils/compat.py:44-47`)
- **setup.py hardcodes migration revision** — expected tables include `execution_profiles` from specific migration `dc24ead48293`; rolling back that migration permanently breaks schema validation [FACT] (`utils/setup.py:147-156`)
- **Health check cache method has UnboundLocalError** — `_check_cache()` references `redis_enabled` in except block but it's only defined inside try; import failure causes UnboundLocalError [FACT] (`api/health.py:226-271`)
- **No end-to-end test for full research loop** — each agent has unit tests, but the complete hypothesis→experiment→analysis cycle is only tested via the evaluation pipeline which makes real API calls

---

## Caching Architecture

The system uses a multi-layer caching strategy to reduce LLM API costs and speed up repeated operations.

**CacheManager** (`core/cache_manager.py`): Singleton with 5 HybridCache instances:

| Cache | Purpose | Default TTL | Typical Size |
|-------|---------|-------------|-------------|
| CLAUDE | LLM API responses | 1 hour | Large — full response texts |
| EXPERIMENT | Experiment execution results | 1 hour | Medium — result dicts |
| LITERATURE | Literature API responses | 48 hours | Medium — paper metadata |
| EMBEDDING | Vector embeddings | Indefinite | Large — float arrays |
| GENERAL | Miscellaneous | 1 hour | Small |

Each HybridCache has two tiers: in-memory (fast, bounded) + disk (persistent, unlimited). Cache keys are typically content hashes.

**ClaudeCache** (`core/claude_cache.py`): Specialized LLM response cache. Separate from the HybridCache system. Indexes by prompt hash. Supports cache bypass for retries (`bypass_cache=True` in `generate()`). Singleton with reset.

**LiteratureCache** (`literature/cache.py`): Caches literature API responses. TTL from `config.literature.cache_ttl_hours` (default 48h). Singleton with reset.

**ExperimentCache** (`core/experiment_cache.py`): Caches experiment results by protocol hash. Prevents re-execution of identical experiments. Singleton with reset.

**Redis** (optional): If `REDIS_ENABLED=True`, provides a distributed cache layer. Not integrated with HybridCache — separate connection. Default TTL 3600s, max 50 connections.

**Gotcha:** `kosmos cache --clear-type` allowlist omits "literature" even though CacheType.LITERATURE exists — users cannot clear literature cache via CLI. [FACT] (`cli/commands/cache.py:252`)

---

## Coupling Anomalies

6 file pairs that are frequently co-modified in git but have NO import relationship:

| File A | File B | Co-modification Score | Why |
|--------|--------|----------------------|-----|
| `config.py` | `core/providers/anthropic.py` | 1.0 | Config changes always require provider updates |
| `agents/experiment_designer.py` | `agents/research_director.py` | 0.8 | Director orchestrates designer |
| `agents/research_director.py` | `execution/code_generator.py` | 0.8 | Director triggers code generation |
| `agents/research_director.py` | `cli/commands/run.py` | 0.8 | CLI is main entry to director |
| `core/providers/anthropic.py` | `core/providers/openai.py` | 0.8 | Provider implementations evolve together |
| `config.py` | `core/llm.py` | implicit | Config changes affect LLM client creation |

**Impact:** When modifying any file in these pairs, check its partner for needed changes. The lack of import relationship means IDE "find references" won't surface these dependencies.

---

## Research Director Decision Tree (Detail)

The `decide_next_action()` method (`research_director.py:2388`) is the core decision engine. It determines what happens next based on workflow state, available data, and resource constraints. Understanding this tree is essential for modifying research behavior.

```
decide_next_action() →
  1. Check budget (lazy import kosmos.core.metrics) → converge if exceeded
  2. Check runtime (MAX_RUNTIME_HOURS) → converge if exceeded
  3. Check loop guard (50 actions this iteration) → force converge
  4. Read workflow state from state machine

  State = GENERATING_HYPOTHESES:
    → Check if hypothesis_pool has untested hypotheses
    → If yes: transition to DESIGNING_EXPERIMENTS
    → If no: generate new hypotheses (LLM call)
    → If novelty declining: consider convergence

  State = DESIGNING_EXPERIMENTS:
    → Find highest-priority untested hypothesis
    → If found: design experiment → transition to EXECUTING
    → If none: transition back to GENERATING_HYPOTHESES

  State = EXECUTING:
    → Find next experiment to execute
    → If found: generate code + execute → transition to ANALYZING
    → If none: transition back to DESIGNING_EXPERIMENTS

  State = ANALYZING:
    → Find results needing analysis
    → If found: analyze via DataAnalyst → transition to REFINING
    → If none: transition back to EXECUTING

  State = REFINING:
    → Apply FDR correction to last 20 experiment p-values
    → Refine hypotheses based on results
    → Check convergence criteria
    → If converged: transition to CONVERGED
    → If not: transition to GENERATING_HYPOTHESES (new iteration)
    → Convergence deferred if < min_experiments AND work remains
```

**Strategy selection** (`select_next_strategy()`): Tracks success rates across strategies (hypothesis_generation, literature_search, experiment_refinement, etc.). Picks the strategy with the highest historical success rate. Updated after each action via `update_strategy_effectiveness()`.

**Lazy sub-agent initialization:** All 5 sub-agents are created inside `_handle_*_action()` methods, not in `__init__()`. This means import errors for agent dependencies are deferred until the agent is actually needed, not at ResearchDirector construction time.

**Budget enforcement:** Imported lazily inside `decide_next_action()` (`from kosmos.core.metrics import get_metrics`). If the metrics module is unavailable, budget checking is silently skipped — research can run without budget limits. [FACT] (`research_director.py:2406`)

**Convergence deferral:** Even after the iteration limit is reached, convergence is deferred if fewer than `min_experiments_before_convergence` experiments have completed AND testable work remains. This prevents premature stopping when early iterations produced only hypotheses without experimental validation. [FACT] (`research_director.py:2752-2763`)

**Dead code in ResearchDirector:** Lines 568-1219 contain the original message-passing implementation (Issue #76). This includes `_send_to_hypothesis_generator()`, `_send_to_experiment_designer()`, `_send_to_data_analyst()`, and corresponding `_handle_*_response()` methods. All were replaced by direct-call `_handle_*_action()` methods (lines 1391-1980). The dead code is ~450 lines (~6K tokens). [FACT] (`research_director.py:568-1219`)

---

*Generated by deep_crawl agent. 34 tasks, 30 modules read, 3 traces verified.
Compression: 2,455,608 → ~13,000 tokens (~189:1).
Evidence: 20 [FACT], 12 [PATTERN], 1 [ABSENCE].
Sections: 20 (Identity through Gaps).
Subsystems covered: 22/22 kosmos/ packages.*
