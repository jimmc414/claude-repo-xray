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

**Import degradation:** [PATTERN: 41 files, 7 with `*_AVAILABLE` flags] `try/except ImportError` with feature flags for Docker sandbox, R executor, tenacity, Prometheus, LiteLLM, ChromaDB, anthropic SDK. Each creates placeholder stubs when absent.

**Swallowed exceptions (30+ instances across 17 files):**

| Category | Examples | Risk |
|----------|---------|------|
| Cleanup/teardown (justified) | `sandbox.py:214` temp dir, `docker_manager.py:414` container, `executor.py:535` process | Low |
| Optional diagnostics (justified) | `world_model/simple.py:926-938` Neo4j health, `api/health.py:374-394` version detection | Low |
| Data parsing in loops (debatable) | `literature/unified_search.py:182-183` unparseable results, `research_director.py:1304-1305` unparseable p-values | Medium |
| **Best-effort infrastructure (risky)** | `core/workflow.py:297-298` **silent workflow state save failure**, `execution/provenance.py:36-37` **silent provenance loss**, `knowledge/vector_db.py:94-95` silent collection creation failure | **High** |

**Validation layer:** Pydantic validators use `raise ValueError(...)` extensively — 30+ instances across model files. `hypothesis.py` has 6 validators (empty statement, question detection, rationale length). `experiment.py` has 5 validators with LLM output coercion (string→int, regex float extraction, comma→list). `orchestration/delegation.py` raises `RuntimeError` at 6 locations with prescriptive fix instructions.

**Deviations:**
- `domains/neuroscience/apis.py` uses `@retry` decorator pattern (tenacity); other domain APIs use direct `httpx.HTTPError` catch [ABSENCE in biology/materials APIs]
- `orchestration/delegation.py` raises `RuntimeError` at 6 locations for missing agent dependencies (config errors, not runtime)

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

### Complete Environment Variable Catalog

#### Research Settings
| Variable | Default | Constraints |
|----------|---------|-------------|
| `MAX_RESEARCH_ITERATIONS` | `10` | 1-100 |
| `ENABLED_DOMAINS` | `biology,physics,chemistry,neuroscience` | comma-separated |
| `ENABLED_EXPERIMENT_TYPES` | `computational,data_analysis,literature_synthesis` | comma-separated |
| `MIN_NOVELTY_SCORE` | `0.6` | 0.0-1.0 |
| `ENABLE_AUTONOMOUS_ITERATION` | `True` | — |
| `RESEARCH_BUDGET_USD` | `10.0` | >= 0 |
| `MAX_RUNTIME_HOURS` | `12.0` | 0.1-24.0 |

#### Database
| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_URL` | `sqlite:///kosmos.db` | `normalized_url` property converts relative to absolute |
| `DATABASE_ECHO` | `False` | SQLAlchemy echo mode |

#### Safety
| Variable | Default | Notes |
|----------|---------|-------|
| `ENABLE_SAFETY_CHECKS` | `True` | — |
| `MAX_EXPERIMENT_EXECUTION_TIME` | `300` (seconds) | >= 1 |
| `MAX_MEMORY_MB` | `2048` | >= 128 |
| `ENABLE_SANDBOXING` | `True` | Docker sandbox preference |
| `REQUIRE_HUMAN_APPROVAL` | `False` | For HIGH/CRITICAL risk code |
| `ETHICAL_GUIDELINES_PATH` | `None` | JSON file with custom guidelines |
| `APPROVAL_MODE` | `"blocking"` | blocking/queue/automatic/disabled |
| `AUTO_APPROVE_LOW_RISK` | `True` | — |

#### Performance / Concurrency
| Variable | Default | Notes |
|----------|---------|-------|
| `ENABLE_CONCURRENT_OPERATIONS` | `False` | Enables ParallelExperimentExecutor |
| `MAX_PARALLEL_HYPOTHESES` | `3` | 1-10 |
| `MAX_CONCURRENT_EXPERIMENTS` | `10` | 1-16 |
| `MAX_CONCURRENT_LLM_CALLS` | `5` | 1-20 |
| `LLM_RATE_LIMIT_PER_MINUTE` | `50` | 1-200 |
| `ASYNC_BATCH_TIMEOUT` | `300` | 10-3600 |

#### Logging
| Variable | Default | Notes |
|----------|---------|-------|
| `LOG_LEVEL` | `"INFO"` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `LOG_FORMAT` | `"json"` | json/text |
| `LOG_FILE` | `"logs/kosmos.log"` | — |
| `DEBUG_MODE` | `False` | — |
| `DEBUG_LEVEL` | `0` | 0/1/2/3 (verbosity) |
| `DEBUG_MODULES` | `None` | comma-separated module names |
| `LOG_LLM_CALLS` | `False` | Log all LLM request/response |
| `LOG_AGENT_MESSAGES` | `False` | Log agent messaging |
| `LOG_WORKFLOW_TRANSITIONS` | `False` | Log state machine transitions |
| `STAGE_TRACKING_ENABLED` | `False` | JSONL stage tracking |

#### Literature APIs
| Variable | Default | Notes |
|----------|---------|-------|
| `SEMANTIC_SCHOLAR_API_KEY` | `None` | Optional, rate-limited without key |
| `PUBMED_API_KEY` | `None` | Optional |
| `PUBMED_EMAIL` | `None` | Required by NCBI policy if using PubMed |
| `LITERATURE_CACHE_TTL_HOURS` | `48` | 1-168 |
| `MAX_RESULTS_PER_QUERY` | `100` | 1-1000 |
| `LITERATURE_SEARCH_TIMEOUT` | `90` | 10-300 seconds |

#### Vector DB
| Variable | Default | Notes |
|----------|---------|-------|
| `VECTOR_DB_TYPE` | `"chromadb"` | chromadb/pinecone/weaviate (only chromadb implemented) |
| `CHROMA_PERSIST_DIRECTORY` | `".chroma_db"` | — |

#### Neo4j
| Variable | Default | Notes |
|----------|---------|-------|
| `NEO4J_URI` | `"bolt://localhost:7687"` | — |
| `NEO4J_USER` | `"neo4j"` | — |
| `NEO4J_PASSWORD` | `"kosmos-password"` | — |
| `NEO4J_DATABASE` | `"neo4j"` | — |

#### Local Model Tuning
| Variable | Default | Notes |
|----------|---------|-------|
| `LOCAL_MODEL_MAX_RETRIES` | `1` | 0-5 |
| `LOCAL_MODEL_STRICT_JSON` | `False` | — |
| `LOCAL_MODEL_REQUEST_TIMEOUT` | `120` | 30-600 seconds |
| `LOCAL_MODEL_CB_THRESHOLD` | `3` | Circuit breaker failure threshold |
| `LOCAL_MODEL_CB_RESET_TIMEOUT` | `60` | Circuit breaker reset (10-300s) |

#### Redis
| Variable | Default | Notes |
|----------|---------|-------|
| `REDIS_ENABLED` | `False` | Only used in health endpoint |
| `REDIS_URL` | `"redis://localhost:6379/0"` | — |
| `REDIS_DEFAULT_TTL_SECONDS` | `3600` | 60-86400 |

#### World Model
| Variable | Default | Notes |
|----------|---------|-------|
| `WORLD_MODEL_ENABLED` | `True` | — |
| `WORLD_MODEL_MODE` | `"simple"` | simple (Neo4j) / production |

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

## Storage Architecture

Kosmos uses a **polyglot persistence architecture** with five distinct storage technologies:

| Storage | Technology | Required? | Config | Failure Mode |
|---------|-----------|-----------|--------|-------------|
| Primary relational | SQLAlchemy over SQLite (dev) / PostgreSQL (prod) | **Yes** | `DATABASE_URL` | Fatal: `RuntimeError` from `get_session()` |
| Knowledge graph | Neo4j via py2neo | No | `NEO4J_URI` | Falls back to `InMemoryWorldModel` |
| Vector search | ChromaDB (persistent client, cosine similarity) | No | `CHROMA_PERSIST_DIRECTORY` | Skips vector search; `HAS_CHROMADB` flag guards all operations |
| Cache | Redis (disabled by default) | No | `REDIS_ENABLED=False` | No impact — only used in health endpoint, NOT in CacheManager |
| Experiment cache | Standalone SQLite via raw `sqlite3` | No | `.kosmos_cache/experiments/experiments.db` | Graceful degradation |

**ORM Models** (db/models.py): `Experiment`, `Hypothesis`, `Result`, `Paper`, `AgentRecord`, `ResearchSession`. All use application-generated String IDs. JSON columns used extensively for protocol, data, statistical_tests. [FACT]

**Session lifecycle** (db/__init__.py:108-137): Context manager pattern — yields session, commits on success, rolls back on exception, always closes. SQLite uses `check_same_thread=False`; PostgreSQL uses `QueuePool` with `pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`. [FACT]

**Alembic migrations**: 3 migrations auto-run at startup via `first_time_setup()` → `run_database_migrations()`. Creates 6 tables + 29 performance indexes + 2 profiling tables. [FACT]

**Neo4j auto-start**: `_ensure_container_running()` (graph.py:118) shells out to `docker ps` and `docker-compose up -d neo4j`, waiting up to 60s. Catches `FileNotFoundError` if Docker not installed. Creates 8 indexes on Paper, Author, Concept, Method nodes. [FACT]

**Redis reality**: Despite comprehensive `RedisConfig` (13 settings) and Docker deployment with health checks, Redis is ONLY used in the health check endpoint. `CacheManager` uses file-based and in-memory caches instead. [ABSENCE: CacheManager has zero Redis references]

**Experiment cache isolation**: `ExperimentCache` (core/experiment_cache.py:178) maintains its OWN SQLite database at `.kosmos_cache/experiments/experiments.db`, separate from the main SQLAlchemy database. Uses raw `sqlite3` module, thread-safe via `threading.RLock()`. Similarity search loads ALL experiments into memory and computes cosine similarity — O(n) per query. [FACT]

**Docker compose topology**: postgres → redis → neo4j → kosmos-app startup chain. All services use profiles (`dev`/`prod`). Production PostgreSQL tuned with 20+ settings via `scripts/init_db.sql`. [FACT]

---

## Initialization Sequence

The startup chain is implicit — no central bootstrap function. Initialization is driven by first calls to `get_*()` singleton factories.

### CLI Entry Initialization Order

```
Phase 1: Module-Level Side Effects (on import)
  1. load_dotenv()                    (cli/main.py:22)
  2. install_rich_traceback()          (cli/main.py:35)
  3. Typer app creation               (cli/main.py:39)
  4. register_commands()              (cli/main.py:419) — imports all command modules
  5. _register_builtin_providers()    (providers/factory.py:217) — registers Anthropic/OpenAI/LiteLLM

Phase 2: Typer Callback (runs before every command)
  6. setup_logging()                  (main.py:132)
  7. get_config() — first access      (main.py:77, if --trace)
  8. init_from_config()               (main.py:145)
     a. ensure_env_file()             — creates .env from .env.example if missing
     b. run_database_migrations()     — alembic upgrade head
     c. validate_database_schema()    — checks tables and indexes
     d. init_database()               — SQLAlchemy engine + session factory

Phase 3: ResearchDirectorAgent.__init__() cascade
  9. get_client()                     — LLM singleton (thread-safe, Lock)
  10. init_from_config()              — defensive DB re-init (idempotent)
  11. ConvergenceDetector()           — pure logic, no deps
  12. [conditional] ParallelExperimentExecutor  — if concurrent enabled
  13. [conditional] AsyncClaudeClient           — if concurrent + ANTHROPIC_API_KEY
  14. get_world_model()               — Neo4j or InMemoryWorldModel
      → get_knowledge_graph()         — may shell out to Docker, block up to 60s
      → _ensure_container_running()   — docker ps + docker-compose up
      → py2neo.Graph() connection     — health check + create indexes
```

### Initialization Order Violations

| Violation | Consequence | Mitigation |
|-----------|-------------|------------|
| `get_session()` before `init_database()` | `RuntimeError("Database not initialized")` | Director defensively calls `init_from_config()` again |
| Config access before `.env` loading | Missing env vars; Pydantic has its own `.env` reading | CLI's `load_dotenv()` is redundant with Pydantic's |
| Provider registry before SDK install | Silent registration failure; `get_provider()` raises "Unknown provider" | `list_providers()` returns fewer than expected |
| World model before config | Safe — lazy import inside function body avoids circular deps | Hidden config init path |

### Singleton Inventory (24 total)

All follow the pattern: `_x = None; get_x() / reset_x()`. None use thread locks for creation (except `get_client()`).

| Singleton | Thread-Safe | Module |
|-----------|-------------|--------|
| KosmosConfig | No | config.py |
| SQLAlchemy engine | No | db/__init__.py |
| LLM Client | **Yes** (Lock) | core/llm.py |
| KnowledgeGraph | No | knowledge/graph.py |
| WorldModel | No | world_model/factory.py |
| PaperVectorDB | No | knowledge/vector_db.py |
| ExperimentCache | **Yes** (RLock) | core/experiment_cache.py |
| CacheManager | **Yes** (Lock) | core/cache_manager.py |
| EventBus | Mixed | core/event_bus.py |
| AgentRegistry | No | agents/registry.py |
| StageTracker | No | core/stage_tracker.py |
| + 13 more | No | knowledge/, literature/, monitoring/ |

---

## LLM Provider Architecture

### Three-Layer Abstraction

```
Layer 1: Facade
  get_client() → Union[ClaudeClient, LLMProvider]  (core/llm.py)
  get_provider() → LLMProvider                      (core/llm.py)

Layer 2: Provider System
  LLMProvider (ABC) → AnthropicProvider | OpenAIProvider | LiteLLMProvider
  LLMResponse — string-compatible dataclass (25+ string methods)
  Factory: get_provider_from_config() → provider instance

Layer 3: Async (Independent)
  AsyncClaudeClient — Anthropic-only, own retry/circuit-breaker/rate-limiter
  Returns str (not LLMResponse), no provider system integration
```

### Key Behaviors

**LLMResponse string compatibility** [FACT] (providers/base.py:58): Implements `strip()`, `lower()`, `split()`, `__contains__`, `__len__`, `__iter__`, `__getitem__` etc. delegating to `.content`. Code that previously used raw `str` returns works transparently. But `isinstance(response, str)` returns `False`.

**CLI mode** [FACT]: API key consisting entirely of digit 9 triggers CLI proxy routing. Cost returns $0. Detected at `llm.py:179` and `anthropic.py:110`.

**Auto model selection** [FACT] (llm.py:41-105): Heuristic complexity scoring 0-100. Score <30 → Haiku, >=30 → Sonnet. Never recommends Opus. Disabled in CLI mode.

**Response caching** [FACT]: AnthropicProvider uses `ClaudeCache` (SHA-256 content-hash). Bypass patterns: time-sensitive, random, "latest/newest". OpenAI and LiteLLM providers have NO caching.

**generate_structured parameter mismatch** [FACT]: `ClaudeClient` accepts both `output_schema` and `schema`. `LLMProvider` subclasses only accept `schema`. Callers using `output_schema=` (like `literature_analyzer.py:267`) work with ClaudeClient but the parameter is silently swallowed by AnthropicProvider. Latent bug.

**Two ClaudeClient classes** [FACT]: `llm.py:108` defines the legacy `ClaudeClient` (returns `str`). `providers/anthropic.py:881` defines `ClaudeClient = AnthropicProvider` (returns `LLMResponse`). Different imports get different classes.

**Cost estimation bug** [FACT] (llm.py:519): Legacy `ClaudeClient` hardcodes `"claude-sonnet-4-5"` for cost estimation regardless of actual model used. If haiku was auto-selected, costs are overstated. AnthropicProvider correctly passes actual model name.

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

## Agent Communication Architecture

### Two Parallel Systems (One Active, One Dormant)

**Active: Direct-Call Pattern (Issue #76)**

All agent interactions in the main research loop use direct method calls:
```
ResearchDirector.execute()
  → _handle_generate_hypothesis_action()
    → HypothesisGeneratorAgent.generate_hypotheses()  [direct call, line 1406]
  → _handle_design_experiment_action()
    → ExperimentDesignerAgent.design_experiment()      [direct call, line 1474]
  → _handle_execute_experiment_action()
    → ExperimentCodeGenerator.generate() + CodeExecutor.execute()  [direct calls]
  → _handle_analyze_result_action()
    → DataAnalystAgent.interpret_results()             [direct call, line 1737]
  → _handle_refine_hypothesis_action()
    → HypothesisRefiner.evaluate_hypothesis_status()   [utility class, not BaseAgent]
```

[FACT] All sub-agents are lazily initialized on first use (e.g., `research_director.py:1403-1404`) and persist across iterations. `DataAnalystAgent.interpretation_history` accumulates unboundedly. [FACT]

**Dormant: AgentMessage + AgentRegistry System**

[FACT] `AgentMessage` (base.py:37-85) — Pydantic model with `from_agent`, `to_agent`, `content`, `correlation_id`, `MessageType` (REQUEST/RESPONSE/NOTIFICATION/ERROR). `AgentRegistry` (registry.py:70-97) injects `_route_message()` into agents at registration. `_route_message()` (registry.py:230-254) looks up target agent and calls `receive_message()`.

[FACT] But agents are NEVER registered with AgentRegistry in the main execution loop. `_message_router` on each agent is `None`. The five `_send_to_*` methods on ResearchDirector (lines 1039-1219) silently drop messages when router is None. [FACT] Comment at `research_director.py:1225`: "Issue #76 fix: ConvergenceDetector is not an agent that can receive messages."

**EventBus: Observability Only**

[FACT] EventBus (core/event_bus.py:28-258) — type-filtered pub/sub with 21 event types across 6 categories. Used for streaming display (cli/streaming.py), WebSocket/SSE endpoints (api/websocket.py), and stage tracking. NOT used for agent coordination.

**Two Independent Research Loops**

[FACT] `ResearchDirectorAgent` (state machine + direct calls) and `ResearchWorkflow` in `workflow/research_loop.py` (Plan Creator → Novelty Check → Plan Reviewer → Delegation Manager → State Manager) are SEPARATE orchestration paths. Both instantiate agent objects independently. `DelegationManager.AGENT_ROUTING` (delegation.py:72-95) maps task types to agent classes. Not obvious which is canonical — CLI uses ResearchDirector.

### Code Execution Security Model

**Two-mode architecture** (executor.py):

| Mode | Entry | Security | When Used |
|------|-------|----------|-----------|
| Sandboxed | `_execute_in_sandbox()` (line 555) | Docker: network disabled, read-only FS, all caps dropped, no-new-privileges, tmpfs /tmp, mem_limit 2g, non-root user | When Docker SDK available |
| Unsandboxed | `_execute_once()` → `exec()` (line 617) | Restricted builtins only (SAFE_BUILTINS at line 43-83) + restricted `__import__` (line 97-110) whitelisting ~30 scientific modules | Docker unavailable (SILENT fallback) |

**Restricted builtins expose**: `type`, `hasattr`, `isinstance`, `super`, `object` — allows class creation via `type('Foo', (object,), {})`. Tradeoff: needed for scientific code patterns. [FACT]

**RetryStrategy** (executor.py:667-1014): 10+ error-specific fix strategies plus LLM repair. Most "fixes" wrap code in `try/except` — the "fixed" code always "succeeds" but returns error dict. Downstream must check `result.return_value.get('status') == 'failed'`. [PATTERN: 9/11 fix methods use this pattern]

**LLM repair is unrestricted** [FACT] (executor.py:835-848): Sends full code + traceback to LLM for repair. Returned code is executed WITHOUT re-validation through CodeValidator. A confused LLM response could introduce unsafe code.

**Code generation three-tier fallback** (code_generator.py):
1. Template match (5 templates: TTest, Correlation, LogLog, ML, Generic — order matters, Generic is catch-all)
2. LLM generation (naive code extraction: finds first ``` block)
3. Basic template (crashes without `data_path` — no guard unlike other templates)

**Generated code convention**: All templates check `if 'data_path' in dir() and data_path:` to decide file vs synthetic data. All check `if 'figure_path' in dir()` for figure generation. These are IMPLICIT contracts with the executor. [PATTERN: 5/5 templates]

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

## LLM Pricing Table

[FACT] Canonical pricing at `kosmos/core/pricing.py:14`:

| Model | Input $/1M tokens | Output $/1M tokens |
|-------|-------------------|-------------------|
| `claude-sonnet-4-5` | $3.00 | $15.00 |
| `claude-haiku-4-5` | $1.00 | $5.00 |
| `claude-opus-4-5` | $15.00 | $75.00 |
| `gpt-4-turbo` | $10.00 | $30.00 |
| `gpt-4o` | $5.00 | $15.00 |
| `deepseek/deepseek-chat` | $0.14 | $0.28 |
| `ollama/*` | $0.00 | $0.00 |

Fallback: family-keyword matching (`haiku`/`sonnet`/`opus` in model name). OpenAI provider has DUPLICATED pricing table (openai.py:575-612) that doesn't use the canonical module — prices may diverge.

---

## Code Template Reference

[FACT] Template match order in `code_generator.py:787-793` (first match wins):

| # | Template Class | Matches When | Key Generated Code |
|---|---------------|-------------|-------------------|
| 1 | `TTestComparisonCodeTemplate` | DATA_ANALYSIS + `t_test` in statistical_tests | `DataAnalyzer.ttest_comparison()`, synthetic data with configurable `effect_size` (default 0.0 = null hypothesis) |
| 2 | `CorrelationAnalysisCodeTemplate` | DATA_ANALYSIS + `correlation`/`regression` in tests or name | `DataAnalyzer.correlation_analysis()`, synthetic r~0.89 |
| 3 | `LogLogScalingCodeTemplate` | Name/description contains `scaling`/`power law`/`log-log` | `DataAnalyzer.log_log_scaling_analysis()`, exponent=0.75 |
| 4 | `MLExperimentCodeTemplate` | COMPUTATIONAL + ML keywords | `MLAnalyzer.run_experiment()`, sklearn imports |
| 5 | `GenericComputationalCodeTemplate` | COMPUTATIONAL or DATA_ANALYSIS (**catch-all**) | `scipy.stats`, `scipy.optimize.curve_fit` |

**Generated code dependencies** (exec-time, not import-time): `pandas`, `numpy`, `scipy.stats`, `kosmos.execution.data_analysis.DataAnalyzer`, `kosmos.analysis.visualization.PublicationVisualizer`. ML template also needs `sklearn`. Basic fallback template has NO `data_path` guard — crashes without it.

---

## Test Infrastructure

**Organization** [PATTERN: mirrors `kosmos/` structure]:
```
tests/
  conftest.py              ← Shared fixtures, .env loading, singleton reset, skip markers
  unit/                    ← One file per module (test_hypothesis_generator.py, test_llm.py, etc.)
  integration/             ← Cross-module scenarios (test_execution_pipeline.py, etc.)
  e2e/                     ← Full workflow tests (test_smoke.py with optional dep markers)
  requirements/            ← Requirements verification tests
  manual/                  ← Manual test scripts
```

**conftest.py key fixtures** [FACT]:
- `reset_singletons` (autouse): Resets all known singletons after each test via `reset_*()` functions
- `requires_llm`: Skip if no `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- `requires_anthropic`: Skip if no `ANTHROPIC_API_KEY`
- `requires_neo4j`: Skip if no `NEO4J_URI`
- `requires_docker`: Skip if Docker daemon not running
- `requires_full_stack`: Skip if any of LLM+Neo4j+Docker missing

**Evaluation test suite** [FACT]:
- `evaluation/scientific_evaluation.py` — 7-phase evaluation pipeline (1489 lines)
- `evaluation/run_phase2_tests.py` — 6 component tests (571 lines)
- `evaluation/personas/run_persona_eval.py` — Persona-based regression testing (4 personas)
- `evaluation/personas/compare_runs.py` — Version comparison with regression detection

**Test artifacts**: 4 persona definitions in `evaluation/personas/definitions/`, 4 test datasets in `evaluation/data/`, persona runs in `evaluation/personas/runs/` (persona 004 has 7 versions indicating heavy iteration).

---

*Generated by deep_crawl skill. 26 tasks, 22 modules read, 5 traces verified.
Compression: 2,455,608 → ~45,000 tokens (~55:1).
Evidence: 200+ [FACT], 30+ [PATTERN], 10+ [ABSENCE].*
