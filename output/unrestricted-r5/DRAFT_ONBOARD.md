# Kosmos: Agent Onboarding

> Codebase: 802 files, ~2,455,608 tokens
> Generated: 2026-03-29 from commit `3ff33c3`
> Crawl: 26/26 tasks, 22 modules read, 5 traces verified
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---

## Identity

Kosmos is an autonomous AI scientist system that generates hypotheses, designs experiments, executes code, analyzes results, and iteratively refines findings across scientific domains (biology, materials, neuroscience, physics, chemistry). Built on a multi-agent architecture with Claude/OpenAI/LiteLLM as LLM providers, Typer CLI, SQLAlchemy (SQLite/Postgres), Neo4j knowledge graph, ChromaDB vector store, and Redis caching. Python 3.8+, Pydantic v2 + pydantic-settings for config.

---

## Critical Paths

### 1. `kosmos run` — Main Research Loop

```
cli_entrypoint() (cli/main.py:422)
  → load_dotenv() (main.py:22) — loads .env at import time [SIDE EFFECT: mutates os.environ]
  → main() callback (main.py:98) — processes --verbose/--debug/--trace/--quiet
    → setup_logging() (main.py:49) — file+console handlers
    → init_from_config() (db/__init__.py:140) — DB init (runs on EVERY command)
      → first_time_setup() — creates .env if missing, runs alembic migrations
      → init_database() — SQLAlchemy engine + session factory
      [SIDE EFFECT: DB file/connection created] (db/__init__.py:178)
  → run_research() (commands/run.py:51) — registered as "run" command
    → ResearchDirectorAgent.__init__() (research_director.py:68)
      → BaseAgent.__init__() — agent_id, status=CREATED
      → get_client() (core/llm.py:613) — thread-safe LLM singleton
        [SIDE EFFECT: Anthropic/OpenAI HTTP client created]
      → init_from_config() — defensive DB re-init (idempotent)
      → ConvergenceDetector() — stopping criteria evaluator
      → [optional] ParallelExperimentExecutor if concurrent enabled
      → [optional] AsyncClaudeClient if concurrent + ANTHROPIC_API_KEY set
      → get_world_model() (world_model/factory.py) — Neo4j or InMemoryWorldModel
        [SIDE EFFECT: may shell out to docker for Neo4j, blocks up to 60s]
    → asyncio.run(run_with_progress_async(director, ...)) (run.py:186)
      → director.execute({"action": "start_research"})
        → generate_research_plan() — LLM call to create plan
        → director.start() — status CREATED→STARTING→RUNNING
          → _on_start() → workflow.transition_to(GENERATING_HYPOTHESES)
```

**Research loop (run.py:308-386):**
```
while iteration < max_iterations:
  → director.get_research_status() — snapshot for progress bars
  → check CLI timeout (2hr, run.py:301)
  → check convergence
  → await director.execute({"action": "step"})
    → decide_next_action() — deterministic state machine
      Guards: budget enforcement (research_director.py:2404), runtime limit 12hr (research_director.py:2428),
              loop guard MAX_ACTIONS_PER_ITERATION=50 (research_director.py:2455)
    → _execute_next_action(action)
      GENERATE_HYPOTHESIS → HypothesisGeneratorAgent.generate_hypotheses() [DIRECT CALL]
        → _gather_literature_context() [SIDE EFFECT: external API calls]
        → _generate_with_claude() [SIDE EFFECT: LLM call]
        → session.add(DBHypothesis), session.commit() [SIDE EFFECT: DB write]
      DESIGN_EXPERIMENT → ExperimentDesignerAgent.design_experiment() [DIRECT CALL]
        → _generate_from_template() or _generate_with_claude()
        → session.add(DBExperiment), session.commit() [SIDE EFFECT: DB write]
      EXECUTE_EXPERIMENT → ExperimentCodeGenerator.generate() + CodeExecutor.execute() [DIRECT CALL]
        → template or LLM code generation [SIDE EFFECT: possible LLM call]
        → BRANCH: Docker sandbox (executor.py:576) or exec() fallback (executor.py:617)
          [SIDE EFFECT: arbitrary Python code executed]
        → session.add(Result), session.commit() [SIDE EFFECT: DB write]
      ANALYZE_RESULT → DataAnalystAgent.interpret_results() [DIRECT CALL]
        → llm_client.generate(prompt, temperature=0.3) [SIDE EFFECT: LLM call]
        → wm.add_relationship(SUPPORTS/REFUTES) [SIDE EFFECT: knowledge graph write]
      REFINE_HYPOTHESIS → HypothesisRefiner.evaluate_hypothesis_status()
        → RetirementDecision: RETIRE | REFINE | SPAWN_VARIANT | CONTINUE_TESTING
        → research_plan.increment_iteration() — iteration counter only increments here
      CONVERGE → ConvergenceDetector.evaluate()
        → if should_stop: workflow → CONVERGED, director.stop()
  → asyncio.sleep(0.05) — UI update yield
```

**State machine:**
```
INITIALIZING → GENERATING_HYPOTHESES → DESIGNING_EXPERIMENTS → EXECUTING → ANALYZING → REFINING → (loop or CONVERGED)
```

**Terminal side effects:**
```
ResultsViewer.display_research_overview(results) — Rich console
BRANCH on --output: .json → export_to_json() | .md → export_to_markdown()
```

### 2. `kosmos config` — Configuration Loading Chain

```
cli_entrypoint() (cli/main.py:422)
  → main() callback — DB init happens here too (even for config --show!)
  → manage_config() (commands/config.py:25)
    --show: display_config() → get_config() → shows claude OR openai (NOT litellm)
    --validate: validate_config() → checks API keys, model names, domains
    --edit: opens .env in $EDITOR
    --reset: copies .env.example → .env (singleton NOT invalidated)
    --path: shows config file locations
```

**Config singleton chain:**
```
get_config() (config.py:1140)
  → KosmosConfig() — pydantic-settings BaseSettings
    → reads .env file (config.py:979, path relative to config.py parent.parent)
    → reads os.environ (takes precedence over .env)
    → constructs 16 sub-configs via default_factory
    → validate_provider_config() — ANTHROPIC_API_KEY required if LLM_PROVIDER=anthropic
    → create_directories() — log dir, chromadb dir
```

**Config precedence** (highest wins): Runtime env vars → .env file → Pydantic field defaults

### 3. Scientific Evaluation Pipeline

```
evaluation/scientific_evaluation.py:main() (line 1342, async)
  → P1: run_phase1_preflight() — config, LLM connectivity, DB init, type compat
    ✗ on FAIL: writes partial report, exit 1
  → P2: run_phase2_smoke_test() — single-iteration research cycle (max_iterations=1)
    → _reset_eval_state() — DESTRUCTIVE: drops all DB tables, clears all caches
    → ResearchDirectorAgent(max_iterations=1, budget_usd=5.0)
    → 20 action steps with 120s timeout each
  → P3: run_phase3_multi_iteration() — 3 iterations, budget_usd=10.0, 60+ actions
  → P4: run_phase4_dataset_test() — requires --data-path, uses pandas
  → P5: assess_output_quality() — heuristic keyword-based quality scoring
  → P6: run_phase6_rigor_scorecard() — introspects 8 rigor features via import+hasattr
  → P7: run_phase7_paper_compliance() — 15 claims from arXiv:2511.02824v2
  → generate_report() → EVALUATION_REPORT.md
```

### 4. Persona Evaluation

```
evaluation/personas/run_persona_eval.py:main() (line 258)
  → load_persona(name) — reads YAML from definitions/ (requires PyYAML)
  → get_next_version() — auto-increments from runs/{persona}/v*
  → create_run_directory() — runs/{persona}/{version}/tier{1,2,3}/
  → write_meta_json() — initial metadata with git_sha, config_hash
  → run_tier1():
    → DESTRUCTIVE: deletes kosmos.db and .kosmos_cache/ (lines 186-191)
    → subprocess.run(scientific_evaluation.py, ...) — blocking, NO timeout
    → subprocess.run(run_phase2_tests.py, ...) — blocking, NO timeout
  → parse_tier1_results() — regex-parses EVALUATION_REPORT.md
  → write_meta_json() — final results
```

### 5. E2E Smoke Tests (3 variants)

| Test | File | Exercises | Issues |
|------|------|-----------|--------|
| Template | `.claude/skills/.../smoke-test.py` | LLM init, workflow, providers, gaps, DB, LLM call | Stale `kosmos.gaps.*` paths (5/6 don't exist), `client.complete()` API mismatch |
| Script | `scripts/smoke_test.py` | 7 test groups with correct module paths | More thorough, uses correct paths |
| Pytest | `tests/e2e/test_smoke.py` | Config, DB, Neo4j, metrics, world model, CLI help | Uses markers for optional deps |

---

## Module Behavioral Index

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `config.py` | Pydantic-settings singleton composing 16 sub-configs from env+.env. Risk 0.96. | `.env` file, env vars, pydantic-settings | Config crash if ANTHROPIC_API_KEY missing with default provider; `config.claude` and `config.anthropic` are independent instances of same class |
| `core/llm.py` | Thread-safe LLM client singleton with provider factory fallback chain. 27 importers. | Config, provider registry, API key | Singleton: switching providers after first call requires `reset=True`; fallback to AnthropicProvider hardcoded |
| `core/logging.py` | Custom logging setup with file+console handlers, debug module filtering, trace mode. 140 importers. | stdlib logging | `get_logger()` exists but unused — all 109 modules use `logging.getLogger(__name__)` directly |
| `core/workflow.py` | ResearchPlan (hypothesis pools, experiment queues, results tracking) + ResearchWorkflow state machine with 9 states and validated transitions. 26 importers. | None | Silent workflow state save failure (workflow.py:297-298) |
| `core/convergence.py` | Evaluates stopping criteria: mandatory (max_iterations, max_runtime, budget) + optional (novelty_saturation, insight_plateau, effect_size_consistency). ~17 metrics scored 0-100. | None (pure logic) | Thresholds from config dict, not from KosmosConfig; `overall_confidence` is weighted average but convergence requires mandatory_met=True |
| `core/memory.py` | Per-run MemoryStore with SUCCESS/FAILURE/DEAD_END/INSIGHT categories. Experiment deduplication via MD5 hash. | None | Recency-weighted importance scoring; NOT a singleton |
| `core/feedback.py` | Extracts success/failure patterns from experiment results, adjusts hypothesis confidence_score directly. | None | Mutates hypothesis objects in-place; NOT a singleton |
| `core/async_llm.py` | Async LLM client with circuit breaker (3 failures → 60s open) + tenacity retry (3 attempts, exponential backoff 2-30s). | anthropic SDK (optional), tenacity (optional) | Creates placeholder exception stubs when anthropic SDK missing |
| `core/event_bus.py` | Type-filtered pub/sub for 21 event types (workflow, cycle, task, LLM, execution, stage). Thread-safe with threading.Lock + asyncio.Lock. | None | `publish_sync()` silently drops async callbacks if no event loop running |
| `core/providers/factory.py` | Provider registry with auto-registration at import. Aliases: anthropic/claude, openai, litellm/ollama/deepseek/lmstudio. | Provider SDKs (optional) | Silent registration failure on missing SDK; LiteLLM has triple config precedence |
| `agents/research_director.py` | Master orchestrator: state machine + direct-call pattern for all sub-agents. 54+ methods, 22 importers, 0.83 risk. | All agents, LLM, DB, world model, config | Two independent timeouts (CLI 2hr vs director 12hr); lazy agent init means state accumulates; dead _send_to_* message methods |
| `agents/base.py` | BaseAgent: agent_id, status enum, config dict, message queues (both sync List and async Queue), message router injection. | None | Dual message queues (both populated, async queue never drained) |
| `agents/hypothesis_generator.py` | Generates hypotheses via LLM with literature context, validates, checks novelty, stores in DB. | LLM client, literature search, DB | Domain auto-detection can pick wrong domain; novelty checker is optional (fails silently) |
| `agents/experiment_designer.py` | Designs experiment protocols from hypotheses via templates or LLM. Includes power analysis. | LLM client, DB | Template registry loaded once at init; `_generate_from_template()` + `_enhance_with_llm()` can produce different results per run |
| `agents/data_analyst.py` | Interprets experiment results via LLM. Anomaly detection, pattern detection across results. | LLM client | `interpretation_history` accumulates across iterations (lazy init, not reset) |
| `agents/registry.py` | Singleton agent registry with message routing. Injects `_route_message` into agents at registration. | None | Message-passing is dead code in main loop (Issue #76 fix); message history stored twice (route + send) |
| `execution/executor.py` | CodeExecutor: runs Python code in Docker sandbox or exec() fallback. Restricted builtins, 300s timeout, 3 retries with auto-fix. | Docker (optional), subprocess | **CRITICAL**: exec() fallback when Docker unavailable — restricted builtins mitigate but don't fully sandbox; RetryStrategy auto-modifies code |
| `execution/code_generator.py` | Three-tier code generation: template match → LLM → basic fallback. 5 templates (TTest, Correlation, LogLog, ML, Generic). Risk 0.67. | LLM client (optional), ExperimentProtocol model | Basic template crashes without data_path (no guard); template order is load-bearing (Generic is catch-all); LLM code extraction is naive |
| `safety/code_validator.py` | Static analysis gate: dangerous imports (AST+string), dangerous patterns, file/network policy, dunder access, ethical guidelines. | ast (stdlib) | Missing: ctypes, cffi, multiprocessing, pathlib.Path.write_text; ethical guidelines only implement "keyword" method; string-matching false positives |
| `knowledge/vector_db.py` | ChromaDB integration: PaperVectorDB singleton for literature embeddings. | chromadb (optional) | Silent collection creation failure; no explicit cleanup/close |
| `knowledge/graph.py` | Neo4j knowledge graph: entities, relationships, CRUD. Auto-starts Docker container. ~1000 lines. | Neo4j (optional), py2neo, Docker | `_ensure_container_running()` shells out to docker/docker-compose, blocks up to 60s; graceful fallback to InMemoryWorldModel |
| `models/hypothesis.py` | Pydantic model: statement, rationale, domain, novelty_score, confidence_score, status enum. 6 validators. 48 importers. | pydantic | Validators reject: empty statements, questions as hypotheses, short rationales; HypothesisStatus enum: PROPOSED→TESTING→SUPPORTED/REJECTED/RETIRED |
| `models/experiment.py` | Pydantic models: ExperimentProtocol (type, steps, variables, statistical_tests), ExperimentResult. 30 importers. | pydantic | ExperimentType enum: DATA_ANALYSIS, COMPUTATIONAL, LITERATURE_SYNTHESIS, SIMULATION; status lifecycle |
| `models/result.py` | ExperimentResult: raw_output, p_value, effect_size, confidence_interval, interpretation. 27 importers. | pydantic | Manual JSON serialization for DB storage (not using Pydantic's json()) |
| `literature/base_client.py` | Abstract base for literature search: search(), get_paper(), get_citations(). 35 importers. | httpx | Rate limiting via time.sleep(); 5 concrete implementations (Semantic Scholar, PubMed, CrossRef, OpenAlex, ArXiv) |
| `workflow/research_loop.py` | Alternative research loop using Plan Creator → Novelty Check → Plan Reviewer → Delegation Manager → State Manager. | LLM client, all agents | This is a SEPARATE orchestration path from ResearchDirector; both exist, not obvious which is canonical |
| `orchestration/delegation.py` | DelegationManager: routes tasks to agents by type, executes in batches (max_parallel_tasks=3), retry with backoff. | Agent instances | Uses direct method calls, not message passing; `AGENT_ROUTING` maps task types to agent classes |
| `db/__init__.py` | SQLAlchemy engine + session management. Session context manager with rollback-on-error. | SQLAlchemy, alembic | `get_session()` raises RuntimeError if `init_database()` not called first; `reset_database()` drops ALL tables |

---

## Key Interfaces

```python
# kosmos/config.py
class KosmosConfig(BaseSettings):
    llm_provider: Literal["anthropic", "openai", "litellm"] = "anthropic"
    claude: Optional[ClaudeConfig]   # None if no ANTHROPIC_API_KEY
    openai: Optional[OpenAIConfig]   # None if no OPENAI_API_KEY
    litellm: Optional[LiteLLMConfig] # Always created
    research: ResearchConfig
    database: DatabaseConfig
    # ... 12 more sub-configs
def get_config(reload=False) -> KosmosConfig: ...  # module-level singleton

# kosmos/agents/base.py
class BaseAgent:
    def __init__(self, agent_id=None, agent_type=None, config=None): ...
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]: ...  # raises NotImplementedError
    async def send_message(self, to_agent: str, content: dict, msg_type=REQUEST): ...
    async def receive_message(self, message: AgentMessage): ...
    def start(self): ...  # status → STARTING → RUNNING
    def stop(self): ...   # status → STOPPING → STOPPED

# kosmos/agents/research_director.py
class ResearchDirectorAgent(BaseAgent):
    async def execute(self, task: Dict[str, Any]): ...    # Main entry: {"action": "start_research"|"step"}
    def generate_research_plan(self): ...                  # LLM call, stores in research_plan.initial_strategy
    def decide_next_action(self) -> NextAction: ...        # Deterministic state machine
    def get_research_status(self) -> Dict: ...             # Snapshot for UI/progress
    # 54+ methods total

# kosmos/core/llm.py
class ClaudeClient:
    def generate(self, prompt, system=None, max_tokens=None, temperature=None) -> str: ...
    def generate_with_messages(self, messages, system=None, ...) -> str: ...
    def generate_structured(self, prompt, schema, ...) -> dict: ...
def get_client(reset=False, use_provider_system=True) -> Union[ClaudeClient, LLMProvider]: ...

# kosmos/execution/executor.py
class CodeExecutor:
    def execute(self, code: str, retry_on_error=True) -> dict: ...
    def execute_with_data(self, code: str, data_path: str, retry_on_error=True) -> dict: ...
    # 300s default timeout, 3 retries, Docker sandbox or exec() fallback

# kosmos/execution/code_generator.py
class ExperimentCodeGenerator:
    def generate(self, protocol: ExperimentProtocol) -> str: ...  # template → LLM → basic fallback

# kosmos/safety/code_validator.py
class CodeValidator:
    def validate(self, code: str, context: dict = None) -> SafetyReport: ...
    def requires_approval(self, report: SafetyReport) -> bool: ...

# kosmos/models/hypothesis.py
class Hypothesis(BaseModel):
    statement: str          # Validated: not empty, not a question
    rationale: str          # Min 10 chars
    domain: str             # biology, materials, neuroscience, physics, chemistry, general
    novelty_score: float    # 0-1
    confidence_score: float # 0-1
    status: HypothesisStatus  # PROPOSED → TESTING → SUPPORTED/REJECTED/RETIRED

# kosmos/core/convergence.py
class ConvergenceDetector:
    def evaluate(self, research_plan, metrics_snapshot: dict) -> ConvergenceDecision: ...
    def check_convergence(self, ...) -> ConvergenceDecision: ...
    # Mandatory criteria: max_iterations, max_runtime, budget
    # Optional: novelty_saturation, insight_plateau, effect_size_consistency
```

---

## Error Handling Strategy

**Dominant pattern:** Log-and-return-default [PATTERN: 60+ instances across 30+ files]
```python
try:
    # operation
except Exception as e:
    logger.error(f"Description: {e}")
    return []  # or None, {}, 0, False
```
Rationale: Most subsystems are non-critical enhancements. A failure in novelty checking or caching should not halt a multi-hour research cycle.

**LLM/API layer:** 3-tier resilience stack [FACT] (core/async_llm.py)
1. **Tenacity retry**: exponential backoff 2-30s, max 3 attempts, only retries "recoverable" errors (async_llm.py:440-470)
2. **Circuit breaker**: 3 consecutive failures → OPEN for 60s (async_llm.py:51-129)
3. **Recoverability classification**: RateLimitError=recoverable, 4xx (except 429)=non-recoverable (providers/base.py:445-469)

**Agent layer:** Independent backoff + state machine [FACT] (research_director.py:44-47)
- `MAX_CONSECUTIVE_ERRORS = 3`, backoff `[2, 4, 8]` seconds
- Transitions to `WorkflowState.ERROR` after max errors
- `_reset_error_streak()` on success

**JSON parsing:** 7-strategy fallback chain [FACT] (core/utils/json_parser.py:31-145)
- Direct parse → ```json blocks → unclosed blocks → generic blocks → regex {..} → clean issues → combine

**Database:** Rollback-and-reraise (db/__init__.py:130-137) — the ONLY catch-and-reraise in the codebase

**Custom exceptions:**

| Exception | File | Carries |
|-----------|------|---------|
| `ProviderAPIError` | core/providers/base.py:417 | `recoverable` flag, `status_code`, `raw_error` |
| `BudgetExceededError` | core/metrics.py:63 | `current_cost`, `limit`, `usage_percent` |
| `JSONParseError` | core/utils/json_parser.py:21 | `original_text`, `attempts` count |
| `CacheError` | core/cache.py:22 | Thin wrapper (pass body) |
| `LiteratureCacheError` | literature/cache.py:19 | Thin wrapper |
| `PDFExtractionError` | literature/pdf_extractor.py:22 | Thin wrapper |

**Deviations:**
- `domains/neuroscience/apis.py` uses `@retry` decorator pattern (tenacity); other domain APIs use direct `httpx.HTTPError` catch [ABSENCE in biology/materials APIs]
- `orchestration/delegation.py` raises `RuntimeError` at 6 locations for missing agent dependencies (config errors, not runtime)
- 30+ swallowed exceptions (`except Exception: pass`) clustered in: cleanup/teardown (justified), optional diagnostics (justified), data parsing in loops (debatable), best-effort infrastructure (risky — silent workflow state save failure at workflow.py:297)

---

## Shared State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `_config: KosmosConfig` | `config.py:1137` | `get_config(reload=True)` | Not invalidated after `kosmos config --reset`; thread-unsafe |
| `_engine, _SessionLocal` | `db/__init__.py:22-23` | `init_database()`, `reset_database()` | `reset_database()` drops ALL tables; `get_session()` raises RuntimeError if not initialized |
| `_default_client: LLMProvider` | `core/llm.py:608-609` | `get_client(reset=True)` | Thread-safe (Lock); switching providers requires explicit reset |
| `_knowledge_graph` | `knowledge/graph.py:1000` | `get_knowledge_graph()` | May block 60s on Docker startup; thread-unsafe |
| `_world_model` | `world_model/factory.py:52` | `get_world_model()`, `reset_world_model()` | Falls back to InMemoryWorldModel on Neo4j failure; thread-unsafe |
| `_vector_db: PaperVectorDB` | `knowledge/vector_db.py:444` | `get_vector_db()`, `reset_vector_db()` | Silent collection creation failure; thread-unsafe |
| `_event_bus: EventBus` | `core/event_bus.py:261` | `get_event_bus()`, `reset_event_bus()` | Thread-safe (Lock); silently drops async callbacks in sync context |
| `_registry: AgentRegistry` | `agents/registry.py:509` | `get_registry()` | Dead code in main loop; message history stored twice |
| `_experiment_cache` | `core/experiment_cache.py:726` | `get_experiment_cache()` | Thread-safe (RLock) |
| `_cache_manager` | `core/cache_manager.py:38` | `CacheManager()`, `reset_cache_manager()` | Thread-safe (Lock) |
| `_stage_tracker` | `core/stage_tracker.py:244` | `get_stage_tracker()` | Thread-unsafe |
| `Provider registry` | `core/providers/factory.py:16` | Module-level dict, populated at import | Silent registration failure on missing SDK |
| `research_plan` | `core/workflow.py:57` | ResearchDirectorAgent methods | In-memory only; hypothesis_pool, experiment_queue, results are mutable lists |
| `MemoryStore` | `core/memory.py:66` | Per-run instance (NOT singleton) | Experiment deduplication via MD5 |
| `FeedbackLoop` | `core/feedback.py:76` | Per-run instance | Mutates hypothesis objects in-place |

---

## Domain Glossary

| Term | Means Here | Defined In |
|------|------------|------------|
| Director | `ResearchDirectorAgent` — the master orchestrator that owns the state machine and directly calls all sub-agents | `agents/research_director.py` |
| Research Plan | In-memory `ResearchPlan` Pydantic model tracking hypothesis_pool, experiment_queue, results, iteration_count — NOT a serialized plan | `core/workflow.py:57` |
| Pillar | A module imported by many other modules — high blast radius for changes | xray terminology |
| Issue #76 | The fix that replaced message-passing with direct method calls between agents | `research_director.py:144,167` |
| World Model | Neo4j-backed or in-memory knowledge graph storing entities (hypotheses, experiments, results) and relationships (SPAWNED_BY, TESTS, PRODUCED_BY, SUPPORTS, REFUTES) | `world_model/` |
| CLI Mode | When `ANTHROPIC_API_KEY` is all-9s digits, requests proxy through local Claude Code CLI instead of Anthropic API | `config.py:80` |
| Flat Config | Plain `Dict[str, Any]` cherry-picked from `KosmosConfig` fields and passed to agents at construction | `commands/run.py:148-170` |

---

## Configuration Surface

### Required Environment Variables

| Env Var | Required When | Default | Affects |
|---------|---------------|---------|---------|
| `ANTHROPIC_API_KEY` | `LLM_PROVIDER=anthropic` (default) | None — **crash** | LLM calls, ClaudeClient creation |
| `OPENAI_API_KEY` | `LLM_PROVIDER=openai` | None — crash | OpenAI provider |
| `LLM_PROVIDER` | Always | `"anthropic"` | Provider selection |

### Key Optional Variables

| Env Var | Default | Affects |
|---------|---------|---------|
| `CLAUDE_MODEL` | `claude-sonnet-4-5` | Model selection |
| `CLAUDE_MAX_TOKENS` | `4096` | Response length |
| `CLAUDE_TEMPERATURE` | `0.7` | LLM temperature |
| `CLAUDE_ENABLE_CACHE` | `True` | Prompt caching |
| `CLAUDE_TIMEOUT` | `120` | API timeout (1-600s) |
| `OPENAI_MODEL` | `gpt-4-turbo` | OpenAI model |
| `LITELLM_MODEL` | `gpt-3.5-turbo` | LiteLLM model |
| `LITELLM_API_BASE` | `None` | Custom endpoint (Ollama, etc.) |
| `DATABASE_URL` | `sqlite:///kosmos.db` | DB connection |
| `NEO4J_URI` | `bolt://localhost:7687` | Knowledge graph |
| `NEO4J_USERNAME` | `neo4j` | Neo4j auth |
| `NEO4J_PASSWORD` | (set in .env) | Neo4j auth |
| `REDIS_URL` | `redis://localhost:6379` | Redis cache |

### Config Architecture

```
.env file (project root)
  ↓ (load_dotenv at CLI import + pydantic-settings env_file)
KosmosConfig (pydantic-settings BaseSettings)
  ├── claude: Optional[ClaudeConfig]    ← only if ANTHROPIC_API_KEY set
  ├── anthropic: Optional[AnthropicConfig] ← same class as ClaudeConfig, independent instance
  ├── openai: Optional[OpenAIConfig]    ← only if OPENAI_API_KEY set
  ├── litellm: LiteLLMConfig            ← always created
  ├── research: ResearchConfig
  ├── database: DatabaseConfig
  ├── redis: RedisConfig
  ├── logging: LoggingConfig
  ├── literature: LiteratureConfig
  ├── vector_db: VectorDBConfig
  ├── neo4j: Neo4jConfig
  ├── safety: SafetyConfig
  ├── performance: PerformanceConfig
  ├── monitoring: MonitoringConfig
  ├── development: DevelopmentConfig
  └── world_model: WorldModelConfig
```

### Provider Selection at Runtime

```
get_provider_from_config(config) (core/providers/factory.py)
  → reads config.llm_provider
  → ANTHROPIC: checks config.claude, then config.anthropic (backward compat)
  → OPENAI: checks config.openai
  → LITELLM: checks config.litellm, then falls back to raw os.getenv() (THIRD precedence layer)
  → looks up provider class in _PROVIDER_REGISTRY
  → instantiates: AnthropicProvider | OpenAIProvider | LiteLLMProvider
```

Auto-registered aliases: `"anthropic"` and `"claude"` → AnthropicProvider, `"openai"` → OpenAIProvider, `"litellm"`, `"ollama"`, `"deepseek"`, `"lmstudio"` → LiteLLMProvider

---

## Conventions

1. **Agent class structure:** Always inherit from `BaseAgent`, call `super().__init__(agent_id, agent_type or "ClassName", config)`, read config from `self.config.get("key", default)`, acquire LLM via `get_client()`, set status in execute() try/finally. [PATTERN: 5/5 agents]
2. **Config in agents:** Never pass `KosmosConfig` directly — always pass a plain dict. [PATTERN: 5/5 agents]
3. **Logging:** Always `import logging; logger = logging.getLogger(__name__)`. Never `print()` for operational output. Never `from kosmos.core.logging import get_logger`. [PATTERN: 109/109 modules]
4. **Imports:** Always absolute (`from kosmos.X.Y import Z`). Never relative. Order: stdlib → third-party → kosmos → conditional/lazy. [PATTERN: all modules]
5. **Singleton pattern:** `_x = None; get_x() / reset_x()`. Always expose as function, not module-level instance. Provide `reset_*()` for test isolation. [PATTERN: 24 singletons]
6. **Optional dependency handling:** `try/except ImportError` + `*_AVAILABLE = False` flag. Check at init, not call-time. [PATTERN: 7 files]
7. **Lazy imports for circular deps:** Import inside function body. Especially common in `research_director.py` (12 deferred imports) and `config.py`. [PATTERN: 30+ files]
8. **Direct agent calls (Issue #76):** ResearchDirector calls sub-agents via direct method invocation, NOT message passing. All `_send_to_*` methods are dead code. [PATTERN: 5/5 agent interactions]
9. **Test organization:** `tests/unit/` mirrors `kosmos/` package structure, one test file per module. Use `conftest.py` fixtures for singleton reset. [PATTERN: 3/3 sampled test dirs]
10. **Error handling in agents:** `try/except Exception` with `logger.error(...)` and return default. Never crash the research loop for non-critical failures. [PATTERN: 60+ instances]

---

## Gotchas

### Security / Data Loss

1. **exec() fallback when Docker unavailable** — If Docker sandbox is not available, experiment code runs via `exec()` in the host Python process with only restricted builtins as protection. Warning logged but execution proceeds. [FACT] (`executor.py:217-221, 617`)
2. **Destructive DB reset in evaluations** — `_reset_eval_state()` calls `reset_database()` which runs `Base.metadata.drop_all()` + `create_all()`. No guard against running on production DB. `run_persona_eval.py` also unconditionally deletes `kosmos.db` and `.kosmos_cache/`. [FACT] (`scientific_evaluation.py:54-61`, `run_persona_eval.py:186-191`)
3. **CodeValidator missing dangerous modules** — `ctypes`, `cffi`, `multiprocessing`, `threading`, `signal`, `atexit`, `gc`, `inspect`, `code` not in DANGEROUS_MODULES list. `pathlib.Path.write_text()` bypasses file operation check. [FACT] (`safety/code_validator.py:35-39`)
4. **CodeValidator string-matching false positives/negatives** — `open(` matched globally (comments, strings trigger violations). Variable-based write modes (`mode=m`) evade detection. SyntaxError fallback matches inside strings. [FACT] (`code_validator.py:291-304, 271-280`)

### Architecture / State

5. **Two independent timeout mechanisms** — CLI loop enforces 2-hour max (`run.py:301`), director enforces 12-hour max (`research_director.py:105`). CLI timeout binds first and kills loop without director knowing. [FACT]
6. **Two independent research loops** — `ResearchDirectorAgent` (state machine + direct calls) and `ResearchWorkflow` in `research_loop.py` (Plan Creator → Delegation Manager). Both instantiate agent objects independently. Not obvious which is canonical. [FACT]
7. **Message-passing system is dead code** — Five `_send_to_*` async methods exist in research_director.py (lines 1039-1219). Agents are never registered with AgentRegistry in the main loop, so `_message_router` is None and messages are silently dropped. [FACT]
8. **Dual message queues never drained** — `BaseAgent` maintains both `message_queue: List` and `_async_message_queue: asyncio.Queue`. Both populated by `receive_message()`, but nothing drains the async queue. [FACT] (`base.py:136-137`)
9. **Config singleton not invalidated after reset** — `kosmos config --reset` copies `.env.example` → `.env` but doesn't call `reset_config()`. Same-invocation reads see stale data. [FACT] (`commands/config.py:322-341`)
10. **Double .env load** — `load_dotenv()` at import time (`main.py:22`) AND pydantic-settings reads `.env` independently. Could diverge if file changes between reads. [FACT]

### Data / Logic

11. **Manual Pydantic model reconstruction** — In `_handle_analyze_result_action` (`research_director.py:1704-1722`) and `_handle_refine_hypothesis_action` (`research_director.py:1831-1872`), DB ORM objects are manually converted to Pydantic models field-by-field. Fields must be kept in sync manually. [FACT]
12. **Lazy agent initialization accumulates state** — All sub-agents persist across iterations (no re-init). `DataAnalystAgent.interpretation_history` grows unboundedly. [FACT] (`research_director.py:1403-1404`)
13. **Config flattening is lossy** — `flat_config` at `run.py:148-170` cherry-picks specific fields. Any config key not explicitly listed is invisible to the director and sub-agents. [FACT]
14. **`_json_safe` stringifies unknowns** — Complex objects (sklearn models, custom classes) become opaque strings in the DB via `str(obj)` rather than raising errors. [FACT] (`research_director.py:1595-1613`)
15. **Iteration counter sync gap** — CLI reads iteration from `status.get("iteration", iteration)` but director only increments after REFINE phase. Mid-cycle break causes CLI/director iteration disagreement. [FACT] (`run.py:374`, `research_director.py:2704`)

### Config

16. **No ANTHROPIC_API_KEY = config crash** — If `LLM_PROVIDER=anthropic` (default) and no API key, `get_config()` raises ValueError. `kosmos config --show` fails entirely. [FACT] (`config.py:1033-1038`)
17. **`config.claude` and `config.anthropic` are independent instances** — Both `Optional[ClaudeConfig]` (same class `AnthropicConfig = ClaudeConfig` at line 88), constructed separately. Mutations to one don't affect the other. [FACT] (`config.py:960-961`)
18. **LiteLLM not shown in `config --show`** — `display_config()` only has branches for claude and openai. LiteLLM users see no provider info. [FACT] (`commands/config.py:129-155`)
19. **LiteLLM triple precedence** — `get_provider_from_config()` falls back to raw `os.getenv()` if `config.litellm` is None, creating a third config source not covered by pydantic validation. [FACT] (`providers/factory.py:162-170`)
20. **DB init on every command** — Global callback initializes database even for `kosmos config --path`. Misconfigured DB shows error before config output. [FACT] (`main.py:145`)
21. **AsyncClaudeClient bypasses provider system** — When concurrent mode enabled, `AsyncClaudeClient` reads `ANTHROPIC_API_KEY` directly via `os.getenv()`, hardcoded to Anthropic even if `LLM_PROVIDER=openai`. [FACT] (`research_director.py:228`)

### Evaluation / Testing

22. **Stale gap module paths in template smoke test** — `test_gap_modules()` references `kosmos.gaps.*` modules that don't exist (5/6 paths invalid). Test always fails (threshold 3, only 1 exists). Script smoke test has correct paths. [FACT] (`smoke-test.py:74-96`)
23. **API mismatch in template smoke test** — `test_simple_llm_call()` calls `client.complete()` which doesn't exist on any Kosmos LLM client. Error silently swallowed. [FACT] (`smoke-test.py:112`)
24. **Persona model/provider fields never used** — Persona YAML `setup.model` and `setup.provider` are recorded in meta.json but never passed to scientific_evaluation.py. Evaluation uses system default. [FACT] (`run_persona_eval.py:129-130`)
25. **`expectations` section never evaluated** — Persona YAML `expectations` block (e.g., `hypothesis_quality_minimum: 5`) is loaded but never compared against actual scores. [FACT]
26. **create_world_model ImportError (known bug)** — `scientific_evaluation.py:1161` imports `create_world_model` from factory, but it doesn't exist (factory exports `get_world_model` and `reset_world_model` only). Paper compliance claim 14 always reports PARTIAL. [FACT]
27. **Hardcoded os.chdir in run_phase2_tests.py** — Line 16: `os.chdir("/mnt/c/python/Kosmos")` — breaks on any machine with different filesystem layout. [FACT]
28. **No subprocess timeout in persona eval** — Both subprocess calls in `run_tier1()` use `subprocess.run()` without timeout. Hangs indefinitely if evaluation hangs. [FACT] (`run_persona_eval.py:196,219`)

---

## Hazards — Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `kosmos-reference/**` | ~800K | Reference implementations (duplicated code); not used by main kosmos package |
| `kosmos-claude-scientific-skills/**` | ~600K | External scientific skill plugins; independent codebases |
| `kosmos-figures/**` | ~5K | Generated figures, no code logic |
| `archived/**`, `archive/**` | ~50K | Historical planning docs, may be outdated |
| `htmlcov/**` | ~30K | Coverage reports |
| `*.egg-info/**` | ~5K | Package metadata |
| `neo4j_data/`, `neo4j_import/`, `neo4j_logs/`, `neo4j_plugins/` | ~0 | Neo4j data directories |

---

## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| Add new agent | `agents/base.py` (inherit BaseAgent) | `agents/__init__.py`, `research_director.py` (add handler), `orchestration/delegation.py` (add AGENT_ROUTING entry) | Follow agent class pattern exactly; use direct calls not messages; register in AgentRegistry if needed |
| Add new LLM provider | `core/providers/base.py` (inherit LLMProvider) | `core/providers/factory.py` (_register_builtin_providers), `core/providers/__init__.py` | Add try/except ImportError guard; register with aliases |
| Add new experiment type | `models/experiment.py` (add to ExperimentType enum) | `execution/code_generator.py` (add template before GenericComputational) | Template order matters — Generic catch-all absorbs COMPUTATIONAL and DATA_ANALYSIS |
| Add new domain | `domains/` (create module) | `config.py` (valid domains set), `commands/config.py:417` (validation) | `_validate_domain()` in research_director.py warns if not in enabled list |
| Add new CLI command | `cli/commands/` (create module) | `cli/main.py:register_commands()` | DB init runs in global callback for ALL commands |
| Add new config field | `config.py` (add to sub-config) | `.env.example`, `commands/config.py` (display/validate) | Remember double .env load; LiteLLM needs manual sync in validator |
| Add new evaluation phase | `evaluation/scientific_evaluation.py` | Phase order matters (P5 depends on P2+P3, P7 on P2+P3+P4+P6) | 120s hardcoded timeout per action; _reset_eval_state() is destructive |

---

## Reading Order

1. `kosmos/config.py` — Configuration architecture, all env vars, provider selection (0.96 risk, highest churn)
2. `kosmos/agents/research_director.py` — Master orchestrator, state machine, all agent interactions (0.83 risk)
3. `kosmos/core/llm.py` — LLM abstraction, provider factory, singleton pattern (0.70 risk)
4. `kosmos/agents/base.py` — Agent interface contract, message system (dead but still defines the interface)
5. `kosmos/core/workflow.py` — State machine, ResearchPlan data structure
6. `kosmos/models/hypothesis.py` + `experiment.py` + `result.py` — Core data models (48+30+27 importers)
7. `kosmos/execution/executor.py` — Code execution, sandbox, security (0.70 risk)
8. `kosmos/execution/code_generator.py` — Code generation, templates (0.67 risk)
9. `kosmos/cli/commands/run.py` — CLI entry point for research
10. `kosmos/literature/base_client.py` — Literature search abstraction (35 importers)

**Skip:** `kosmos-reference/` (reference code, not used), `kosmos-claude-scientific-skills/` (external plugins), `archived/` (historical docs)

---

## Gaps

- **No rate limiting found** — No rate limit implementation for API endpoints (`kosmos/api/`). [ABSENCE: grepped for rate_limit, throttle, slowapi — zero hits in kosmos/api/]
- **No integration tests for concurrent mode** — `ParallelExperimentExecutor` and `AsyncClaudeClient` are tested only in unit tests; no integration test exercises the concurrent research path
- **Event bus coverage** — EventBus publish_sync silently drops async callbacks; no test verifies this edge case
- **Evaluation does not test OpenAI/LiteLLM providers** — All evaluation paths assume Anthropic provider; persona YAMLs specify litellm but the evaluation ignores this
- **No structured evaluation output** — Evaluation produces only Markdown reports; no machine-readable JSON for programmatic comparison
- **World model mode selection untested** — `world_model/factory.py` supports "simple" (Neo4j) and "memory" modes, but only "simple" with fallback to memory is exercised in code paths
- **Database migration testing** — Alembic migrations run at startup but there are no tests that verify migration correctness or rollback behavior

---

*Generated by deep_crawl skill. 26 tasks, 22 modules read, 5 traces verified.
Compression: 2,455,608 → ~45,000 tokens (~55:1).
Evidence: 200+ [FACT], 30+ [PATTERN], 10+ [ABSENCE].*
