# Trace T1.1: CLI `kosmos run` → Research Cycle

## Entry: `kosmos/cli/commands/run.py:run_research()` (line 51)
Typer command handler for `kosmos run <question>`.

### Trace Path:
```
run_research(question, domain, ...) (cli/commands/run.py:51)
  → [INTERACTIVE MODE] run_interactive_mode() if --interactive (cli/interactive.py)
  → get_config() (config.py) — loads hierarchical KosmosConfig
  → Creates flat_config dict from nested KosmosConfig (lines 148-170)
  → ResearchDirectorAgent(research_question, domain, config=flat_config) (agents/research_director.py:53)
      → BaseAgent.__init__() (agents/base.py) — sets agent_id, status, inbox
      → _validate_domain() — warns if domain not in enabled list
      → _load_skills() — SkillLoader loads domain-specific research skills for prompt injection
      → get_client() → creates LLM provider (core/llm.py)
      → init_from_config() → initializes SQLite DB (db/__init__.py)
      → ConvergenceDetector() — stopping criteria checker (core/convergence.py)
      → get_world_model() → Neo4j or in-memory entity storage (world_model/__init__.py)
  → get_registry().register(director) (agents/registry.py) — registers for message routing
  → asyncio.run(run_with_progress_async(director, ...)) (cli/commands/run.py:186)
      → director.execute({"action": "start_research"}) (research_director.py:2868)
          → [LIFECYCLE] _on_start() → transitions workflow to GENERATING_HYPOTHESES
      → LOOP: while iteration < max_iterations (cli/commands/run.py:308)
          → director.get_research_status() — snapshot of workflow state
          → director.execute({"action": "step"}) (research_director.py:2868)
              → decide_next_action() — state machine decision (line 2388)
                  [Budget check → Runtime check → State-based decision tree]
              → _execute_next_action(action) → _do_execute_action(action) (line 2573)
                  NextAction.GENERATE_HYPOTHESIS → _handle_generate_hypothesis_action()
                      → HypothesisGeneratorAgent.generate_hypotheses() — LLM call
                      → stores hypotheses in DB, persists to knowledge graph
                  NextAction.DESIGN_EXPERIMENT → _handle_design_experiment_action()
                      → ExperimentDesignerAgent.design_experiment() — LLM call
                      → stores protocol in DB, persists to graph
                  NextAction.EXECUTE_EXPERIMENT → _handle_execute_experiment_action()
                      → CodeGenerator.generate_code() → Executor/Sandbox.run()
                      → stores result in DB
                  NextAction.ANALYZE_RESULT → _handle_analyze_result_action()
                      → DataAnalystAgent.analyze() — LLM call
                      → marks hypothesis as supported/rejected
                  NextAction.REFINE_HYPOTHESIS → _handle_refine_hypothesis_action()
                      → generates refined/spawned hypotheses
                  NextAction.CONVERGE → _handle_convergence_action()
                      → ConvergenceDetector.evaluate() — checks stopping criteria
          → checks convergence, updates progress bars
      → END LOOP
      → Fetches results from DB via get_session() + operations
      → ResultsViewer.display_*() — Rich-based output display
```

## Key Observations:
1. **GOTCHA: Flat config translation** — Agents expect flat dict keys, NOT nested KosmosConfig objects. The flat_config dict at cli/commands/run.py:148-170 manually maps nested config to flat keys. If new config fields are added to KosmosConfig, they must ALSO be added to this flat mapping.

2. **GOTCHA: Error recovery** — ResearchDirectorAgent has a circuit breaker: 3 consecutive errors → ERROR state. Exponential backoff [2,4,8] seconds. Defined at research_director.py:44-46.

3. **GOTCHA: Infinite loop guard** — MAX_ACTIONS_PER_ITERATION=50 forces convergence if exceeded (research_director.py:50). Counter tracked via _actions_this_iteration attribute.

4. **GOTCHA: Runtime limit** — Default max_runtime_hours=12.0 (research_director.py:105). The CLI also has a 2-hour timeout in the progress loop (run.py:301).

5. **Side effects**: DB writes (SQLite), knowledge graph writes (Neo4j), LLM API calls (Anthropic/OpenAI), optional Docker containers for code execution.

6. **World model initialization** — Silently degrades if Neo4j unavailable (research_director.py:252-254). Sets self.wm = None and continues without graph persistence.
# Trace T1.2: ResearchWorkflow.run() — Alternative Entry Point

## Entry: `kosmos/workflow/research_loop.py:ResearchWorkflow` (line 30)
The programmatic API entry point (as shown in README).

### Architecture:
ResearchWorkflow is a SEPARATE orchestration layer from ResearchDirectorAgent.
It integrates "6 gaps" from the paper implementation:
- Gap 0: ContextCompressor (kosmos/compression/)
- Gap 1: ArtifactStateManager (kosmos/world_model/artifacts.py)
- Gap 2: PlanCreatorAgent, PlanReviewerAgent, DelegationManager, NoveltyDetector (kosmos/orchestration/)
- Gap 3: SkillLoader (kosmos/agents/skill_loader.py)
- Gap 4: Python-first tooling
- Gap 5: ScholarEvalValidator (kosmos/validation/)

### Key Observation:
There are TWO orchestration paths:
1. CLI → ResearchDirectorAgent — state machine approach with direct agent calls
2. API → ResearchWorkflow — gap-based architecture with plan/review/delegate pattern

Both exist in the codebase and serve different purposes. ResearchDirectorAgent is the primary
path used by the CLI and is more actively maintained (higher churn). ResearchWorkflow is the
programmatic API with more structured orchestration.

# Trace T1.3: Code Execution Path

## Entry: `kosmos/execution/executor.py:CodeExecutor.execute()` (line 237)

### Trace Path:
```
CodeExecutor.execute(code, local_vars, retry_on_error, llm_client, language)
  → [AUTO-DETECT] language detection: R vs Python (line 261-266)
  → [R CODE PATH] _execute_r(code) → RExecutor (r_executor.py)
  → [PYTHON PATH]
      LOOP: while attempt < max_retries
      → _execute_once(code, local_vars) (line 282)
          → [DOCKER SANDBOX] if self.use_sandbox and self.sandbox:
              → DockerSandbox.execute(code) (sandbox.py:66)
                  → docker.containers.run() with resource limits
                  → cpu_limit=2.0, memory_limit="2g", timeout=300s
                  → network_disabled=True, read_only=True
                  → Returns SandboxExecutionResult
          → [RESTRICTED EXEC] else:
              → exec() with SAFE_BUILTINS whitelist (executor.py:43)
              → _make_restricted_import() limits imports to _ALLOWED_MODULES (line 86)
              → concurrent.futures.ThreadPoolExecutor with timeout (DEFAULT_EXECUTION_TIMEOUT=300s)
      → [ON ERROR with retry_on_error]:
          → RetryStrategy.attempt_repair(code, error, llm_client) (Issue #54)
          → LLM generates fixed code → retry
      → [DETERMINISM CHECK] optional: ReproducibilityManager.test_determinism()
```

## Key Observations:
1. **SECURITY: Docker sandbox graceful fallback** — If Docker not available, falls back to restricted builtins exec(). The fallback is NOT fully sandboxed — it restricts builtins and import whitelist but runs in-process. (executor.py:215-221)

2. **GOTCHA: Allowed imports whitelist** — Only scientific packages allowed: numpy, pandas, scipy, sklearn, matplotlib, seaborn, statsmodels, etc. (executor.py:86-94). Adding new package support requires updating _ALLOWED_MODULES.

3. **Self-correcting execution** — On failure, if llm_client provided and retry_on_error=True, sends error to LLM to generate fixed code (Issue #54).

4. **R language support** — Auto-detects R code and routes to RExecutor with Docker image "kosmos-sandbox-r:latest" (Issue #69).

5. **Docker defaults**: cpu_limit=2.0 cores, memory_limit="2g", timeout=300s, network_disabled=True, read_only=True (sandbox.py:81-84).
# Trace T1.4: Hypothesis Generation

## Entry: `kosmos/agents/hypothesis_generator.py:HypothesisGeneratorAgent.generate_hypotheses()` (line 142)

### Trace Path:
```
generate_hypotheses(research_question, num_hypotheses, domain, store_in_db=True)
  → _detect_domain(research_question) — keyword matching for domain detection
  → _gather_literature_context(research_question, domain) (line ~200)
      → UnifiedLiteratureSearch().search(query) (literature/unified_search.py)
          → searches PubMed, arXiv, Semantic Scholar, etc. via base_client
      → Returns List[PaperMetadata] (max_papers_context=10 default)
  → _generate_with_claude(research_question, domain, literature_context, num_hypotheses)
      → HYPOTHESIS_GENERATOR prompt from core/prompts.py
      → llm_client.generate(prompt, system=...) — LLM call
      → Parses JSON response → List[Hypothesis]
  → FOR EACH hypothesis:
      → _validate_hypothesis(hypothesis) — checks required fields
      → [OPTIONAL] novelty check if require_novelty_check=True (min_novelty_score=0.5)
      → _store_hypothesis(hypothesis) — writes to SQLite via get_session()
          → [DB WRITE] db/operations.py:store_hypothesis()
  → Returns HypothesisGenerationResponse(hypotheses, stats)
```

## Key Observations:
1. **Literature integration** — HypothesisGenerator fetches literature context before generating hypotheses. Uses UnifiedLiteratureSearch which aggregates multiple search backends.
2. **DB storage** — All hypotheses are stored in SQLite via db/operations.py, identified by UUID.
3. **Novelty checking** — Optional. Default min_novelty_score=0.5. Uses cosine similarity against existing hypotheses.
4. **Prompt template** — HYPOTHESIS_GENERATOR defined in core/prompts.py. Injected as system prompt.

# Trace T1.5: LLM Provider Chain

## Entry: `kosmos/core/llm.py:get_client()` (line 613)

### Trace Path:
```
get_client(reset=False, use_provider_system=True) — singleton with threading lock
  → [PROVIDER SYSTEM PATH]:
      → get_config() (config.py) — loads KosmosConfig
      → get_provider_from_config(config) (core/providers/factory.py:83)
          → Checks config.llm_provider: "anthropic" | "openai" | "litellm"
          → Builds provider_config dict from nested KosmosConfig
          → get_provider(name, config) (factory.py:34)
              → Looks up in _PROVIDER_REGISTRY (populated at module import)
              → [ANTHROPIC] AnthropicProvider(config) (providers/anthropic.py)
              → [OPENAI] OpenAIProvider(config) (providers/openai.py)
              → [LITELLM] LiteLLMProvider(config) (providers/litellm_provider.py)
                  aliases: ollama, deepseek, lmstudio all → LiteLLMProvider
  → [FALLBACK PATH] if provider system fails:
      → Tries AnthropicProvider directly
      → Falls back to ClaudeClient (legacy) (llm.py:108)
  → Returns Union[ClaudeClient, LLMProvider] singleton
```

### ClaudeClient.generate() flow (legacy, still used by many agents):
```
ClaudeClient.generate(prompt, system, ...)
  → ModelComplexity.estimate_complexity(prompt, system) — auto model selection
      → Returns "haiku" or "sonnet" based on keyword + token scoring
  → ClaudeCache.get(prompt, model, ...) — check cache first
      → SQLite-based cache (core/claude_cache.py)
  → client.messages.create(...) — Anthropic API call
  → ClaudeCache.set(...) — cache response
  → Returns response text string
```

## Key Observations:
1. **GOTCHA: CLI mode detection** — API key all-9s means CLI mode (routes to Claude Code CLI, not API). (llm.py:179)
2. **GOTCHA: Provider fallback cascade** — get_client() has 3 fallback layers: provider system → AnthropicProvider → ClaudeClient. Each fails silently to the next.
3. **Thread-safe singleton** — get_client() uses threading.Lock for thread-safe initialization. Fast path skips lock if instance exists.
4. **Auto model selection** — ModelComplexity.estimate_complexity() uses keyword matching to route simple queries to Haiku, complex ones to Sonnet. (llm.py:41-105)
5. **Response caching** — ClaudeCache in core/claude_cache.py uses SQLite. Cache key includes prompt + system + model + max_tokens + temperature.
6. **LiteLLM support** — Enables Ollama, DeepSeek, LM Studio via LiteLLM abstraction. Registered as aliases.
# Module Deep Reads (T2.1-T2.8 + T3.1-T3.7)

## T2.1: agents/base.py — Base Agent Class
**Behavior:** Defines BaseAgent: lifecycle management (start/stop/pause/resume), async message passing via AgentMessage (Pydantic), state persistence, and statistics tracking. All Kosmos agents inherit from this.

**Non-obvious:**
- Message routing requires explicit _message_router callback to be set. Without it, send_message() creates the message but does not deliver it.
- Both async and sync APIs exist (send_message vs send_message_sync). Sync wrappers use run_coroutine_threadsafe or asyncio.run as fallback.
- message_queue (legacy sync List) and _async_message_queue (asyncio.Queue) both store messages — dual storage.
- execute() is NOT async on BaseAgent but IS async on ResearchDirectorAgent — inconsistent interface.

**Blast radius:** Every agent inherits from this. Changes to message protocol, lifecycle states, or AgentMessage schema affect all agents.

**Public interface:**
- `start()`, `stop()`, `pause()`, `resume()` — lifecycle
- `send_message()` (async), `receive_message()` (async) — messaging
- `execute(task: Dict) -> Dict` — override in subclasses
- `_on_start()`, `_on_stop()` — lifecycle hooks for subclasses
- `get_state()`, `restore_state()` — persistence

## T2.2: config.py — Hierarchical Configuration (RISK 0.96)
**Behavior:** Pydantic-settings based configuration. Loads from .env file and environment variables. 12+ nested config sections: ClaudeConfig, OpenAIConfig, LiteLLMConfig, ResearchConfig, DatabaseConfig, RedisConfig, LoggingConfig, LiteratureConfig, VectorDBConfig, Neo4jConfig, SafetyConfig, PerformanceConfig, and more. Assembled into KosmosConfig at line ~800+.

**Non-obvious:**
- Uses pydantic_settings SettingsConfigDict for env loading, with `alias` fields mapping env var names.
- `parse_comma_separated()` validator handles both string and list inputs for fields like enabled_domains.
- Database path normalization: DatabaseConfig.normalized_url converts relative SQLite paths to absolute using project root.
- Default models are Claude 4.5 Sonnet/Haiku (lines 17-18): _DEFAULT_CLAUDE_SONNET_MODEL = "claude-sonnet-4-5".
- get_config() is a thread-safe singleton with global _config.
- CLI routing: If API key is all-9s, routes to Claude Code CLI instead of API.

**Blast radius:** Everything depends on config. Changing field names, env var aliases, or validation rules affects the entire system. Coupled to anthropic.py and litellm_provider.py via co-modification (xray coupling anomalies).

## T2.3: execution/executor.py — Code Execution Engine
**Behavior:** Executes LLM-generated Python/R code with safety measures. Supports Docker sandbox (DockerSandbox) and restricted exec() fallback. Self-correcting retry via LLM-based code repair.

**Non-obvious:**
- SAFE_BUILTINS whitelist at line 43: removes dangerous builtins from exec() namespace.
- _ALLOWED_MODULES at line 86: import whitelist for restricted mode (scientific packages only).
- RetryStrategy (Issue #54): On error, sends code + error to LLM for automated fix, then retries.
- Timeout: DEFAULT_EXECUTION_TIMEOUT=300s for unsandboxed exec (uses ThreadPoolExecutor).
- R language support: auto-detects R code and routes to RExecutor.
- Profiling mode: optional code profiling with light/standard/full modes.

**Blast radius:** Core execution path. Changes affect all experiment execution. Security-critical: sandbox fallback means non-Docker environments run code with reduced isolation.

## T2.4: execution/sandbox.py — Docker Sandbox
**Behavior:** Docker-based isolated code execution. Creates temporary directories, mounts code, runs in container with resource limits.

**Key defaults:** cpu_limit=2.0, memory_limit="2g", timeout=300s, network_disabled=True, read_only=True, image="kosmos-sandbox:latest".

**Non-obvious:** Auto-detects if Docker is available. If not, SANDBOX_AVAILABLE=False and executor falls back to restricted builtins. Container monitoring tracks CPU/memory usage via Docker stats API.

## T2.5: safety/code_validator.py — Code Safety Validation
**Behavior:** AST-based code analysis that checks for dangerous imports, functions, and patterns before execution. Validates against ethical research guidelines. Assigns risk levels (LOW/MEDIUM/HIGH/CRITICAL).

**Non-obvious:**
- DANGEROUS_MODULES list: os, subprocess, sys, shutil, importlib, socket, urllib, requests, http, pickle.
- DANGEROUS_PATTERNS: eval(), exec(), compile(), __import__, globals(), etc.
- Ethical guidelines loaded from JSON file (configurable path).
- Risk assessment considers both code patterns AND ethical compliance.

## T2.6: core/providers/anthropic.py — Anthropic Provider
**Behavior:** LLMProvider implementation for Anthropic Claude API. Handles API calls, token counting, response caching.

**Co-modified with config.py** (xray coupling anomaly: score 1.0, no import relationship). Config changes to Claude model names or API settings require coordinated updates here.

## T2.7: knowledge/graph.py — Neo4j Knowledge Graph
**Behavior:** Neo4j interface for scientific literature graph. CRUD for Paper, Concept, Method, Author nodes. Relationships: CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO.

**Non-obvious:**
- Auto-starts Docker container if Neo4j not running (auto_start_container=True default).
- Uses py2neo library (not official neo4j driver).
- Graph queries return raw py2neo Node/Relationship objects — not serializable without conversion.
- Connection settings from config.neo4j (uri, user, password, database).

## T2.8: knowledge/vector_db.py — ChromaDB Vector Store
**Behavior:** Vector database for paper embeddings and semantic search. Uses ChromaDB PersistentClient.

**Non-obvious:**
- Optional dependency: HAS_CHROMADB flag, graceful degradation if not installed.
- Embeddings via knowledge/embeddings.py get_embedder() — uses sentence-transformers or falls back.
- Persist directory from config.vector_db.chroma_persist_directory (default: ".chroma_db").

## T3.1: core/logging.py — Structured Logging (Pillar #1, 140 importers)
**Behavior:** JSON and text log formatters. ContextVar-based correlation_id for request tracing. Supports workflow context fields (workflow_id, cycle, task_id). RotatingFileHandler for log files.

**Key:** setup_logging() function initializes root logger. Called early in startup. Default log file: "logs/kosmos.log".

## T3.2: models/hypothesis.py — Hypothesis Model (Pillar #2, 48 importers)
**Behavior:** Pydantic model for scientific hypotheses. Fields: statement, rationale, domain, scores (testability, novelty, confidence, priority), experiment types, evolution tracking.

**Non-obvious:**
- Validator: statement cannot be a question (no trailing ?). Warns if no predictive words found.
- Evolution tracking: parent_hypothesis_id, generation number, refinement_count, evolution_history list.
- ExperimentType enum: COMPUTATIONAL, DATA_ANALYSIS, LITERATURE_SYNTHESIS.
- HypothesisStatus enum: GENERATED → UNDER_REVIEW → TESTING → SUPPORTED/REJECTED/INCONCLUSIVE.

## T3.3: literature/base_client.py — Literature Base Client (Pillar #3, 35 importers)
**Behavior:** ABC for literature API clients. Defines PaperMetadata dataclass (unified format across all sources), Author dataclass, PaperSource enum (ARXIV, SEMANTIC_SCHOLAR, PUBMED, UNKNOWN, MANUAL).

**Key:** All literature backends (arxiv_client.py, pubmed_client.py, semantic_scholar_client.py) implement this interface and return PaperMetadata objects.

## T3.4: models/experiment.py — Experiment Model (Pillar #4, 30 importers)
**Behavior:** Pydantic models for experiment design: ExperimentProtocol (with ProtocolStep, StatisticalTest, Variable definitions), ExperimentType enum. Request/response models for experiment design API.

## T3.5: core/llm.py — LLM Client (Pillar #5, 27 importers, RISK 0.70)
Already traced in T1.5. Key: ClaudeClient class + get_client() singleton factory. Multi-provider support via provider factory chain.

## T3.6: models/result.py — Result Model (Pillar #6, 27 importers)
**Behavior:** Pydantic model for experiment results. Links to hypothesis and protocol via IDs. Stores execution output, statistical metrics, interpretation.

## T3.7: core/workflow.py — Workflow State Machine (Pillar #7, 26 importers)
Already traced in T1.1. Key: WorkflowState enum (9 states), NextAction enum (8 actions), ResearchPlan (Pydantic model tracking all IDs), ResearchWorkflow (state transitions with history).
# Cross-Cutting Concerns (T4.1-T4.6)

## T4.1: Error Handling Strategy
**Dominant pattern:** try/except Exception with logging + continue. 205 `except Exception` blocks across 50 files.

**Specific strategies by layer:**
1. **Research Director** — Circuit breaker pattern (research_director.py:44-46):
   - MAX_CONSECUTIVE_ERRORS=3 → transitions to ERROR state
   - Exponential backoff: [2, 4, 8] seconds
   - _handle_error_with_recovery() returns NextAction for retry or None to abort
   - _reset_error_streak() called on successful operations

2. **Code Execution** — Self-correcting retry (executor.py):
   - RetryStrategy with max_retries=3, retry_delay=1.0
   - On error, if llm_client provided, sends error to LLM for code fix
   - Re-executes fixed code automatically

3. **API Clients (Literature)** — Retry with backoff (arxiv_client.py has 23 retry occurrences):
   - Literature search clients use exponential backoff for HTTP errors
   - Timeout configurability: search_timeout=90s, api_timeout=30s

4. **Database** — Session-level rollback (db/__init__.py:133-135):
   - Context manager pattern: commit on success, rollback on exception
   - No automatic retry of DB operations

5. **Optional Dependencies** — Graceful degradation pattern:
   - try import / HAS_X flag / fallback (chromadb, docker, neo4j, litellm)
   - Core functionality works without optional deps

**GOTCHA: No swallowed exceptions found** — grep for "except.*pass" returned 0 hits in kosmos/. Exception handling generally logs before continuing.

## T4.2: Configuration Surface
**Primary config:** kosmos/config.py with KosmosConfig (Pydantic BaseSettings).

**Environment variables (50 total across 11 files):**
Key env vars:
- ANTHROPIC_API_KEY — Required for default provider
- OPENAI_API_KEY — Required for OpenAI provider
- LITELLM_MODEL, LITELLM_API_KEY, LITELLM_API_BASE — For LiteLLM/Ollama
- DATABASE_URL — SQLite path (default: "sqlite:///kosmos.db")
- NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD — Knowledge graph
- REDIS_URL, REDIS_ENABLED — Cache layer
- LOG_LEVEL, DEBUG_MODE — Logging
- ENABLE_SAFETY_CHECKS, ENABLE_SANDBOXING — Safety
- MAX_RESEARCH_ITERATIONS, RESEARCH_BUDGET_USD — Research limits
- CLAUDE_MODEL, CLAUDE_MAX_TOKENS, CLAUDE_TEMPERATURE — LLM settings

**Config loading:** .env file at project root → environment variables → defaults.
**Singleton:** get_config() returns cached _config (thread-safe with global).

## T4.3: LLM Provider Abstraction
**Pattern:** LLMProvider ABC (core/providers/base.py) with concrete implementations:
- AnthropicProvider (anthropic.py) — also aliased as "claude"
- OpenAIProvider (openai.py)
- LiteLLMProvider (litellm_provider.py) — also aliased as "ollama", "deepseek", "lmstudio"

**Registry:** _PROVIDER_REGISTRY dict populated at module import via _register_builtin_providers().
**Selection:** config.llm_provider → get_provider_from_config() → factory lookup.
**Legacy:** ClaudeClient still exists and is used as ultimate fallback in get_client().

**Token tracking:** All providers track usage stats (total_input_tokens, total_output_tokens, total_requests).
**Caching:** ClaudeCache (SQLite-based) caches responses by prompt+model+params hash.

## T4.4: Code Execution Security Model
**Two-tier security:**
1. **Docker Sandbox (preferred):** DockerSandbox in execution/sandbox.py
   - Network disabled, read-only FS, resource limits (2 CPU, 2GB RAM, 300s timeout)
   - Uses "kosmos-sandbox:latest" image
2. **Restricted Exec (fallback):** When Docker unavailable
   - SAFE_BUILTINS whitelist: ~80 safe builtins, no file/network/os operations
   - _ALLOWED_MODULES: ~30 scientific packages only
   - ThreadPoolExecutor with 300s timeout

**Pre-execution validation:** CodeValidator (safety/code_validator.py):
- AST-based analysis for dangerous imports/patterns
- Risk level assessment: LOW/MEDIUM/HIGH/CRITICAL
- Ethical guidelines check (configurable JSON)

**IMPORTANT:** Fallback exec() is NOT fully sandboxed. It restricts builtins and imports but runs in-process. A carefully crafted payload could escape the restricted environment.

## T4.5: Shared Mutable State
**Global singletons (verified via grep):**
- `_config` in config.py (get_config()) — thread-safe
- `_default_client` in core/llm.py (get_client()) — thread-safe with lock
- `_engine`, `_SessionLocal` in db/__init__.py — DB globals
- `_world_model` in world_model/factory.py — knowledge graph singleton
- `_metrics_collector` in monitoring/metrics.py — metrics singleton
- `_alert_manager` in monitoring/alerts.py — alert singleton
- `_health_checker` in api/health.py — health check singleton
- `_PROVIDER_REGISTRY` in core/providers/factory.py — provider registry dict

**Module-level mutable state:** evaluation/run_phase2_tests.py:27 — `results` list (xray flagged as shared_mutable_state risk=hidden_state). Used by test_component function.

**Thread safety:** Most singletons use threading.Lock or global keyword with simple assignment. LLM client uses double-check locking pattern.

## T4.6: Database and Persistence Strategy
**Three storage layers:**
1. **SQLite** (primary) — kosmos/db/
   - SQLAlchemy ORM with models in db/models.py
   - Default: "sqlite:///kosmos.db" (relative path, normalized to absolute)
   - Tables: Hypothesis, Experiment, Result, etc.
   - Connection pooling: N/A for SQLite, QueuePool for PostgreSQL
   - Slow query logging: enabled by default (threshold 100ms)
   - Session management: context manager with auto-commit/rollback

2. **Neo4j** (knowledge graph) — kosmos/knowledge/graph.py
   - py2neo library, auto-starts Docker container
   - Entities: Paper, Concept, Method, Author
   - Relationships: CITES, USES_METHOD, DISCUSSES, SPAWNED_BY, TESTS, SUPPORTS, REFUTES
   - Optional: degrades gracefully if unavailable

3. **ChromaDB** (vector store) — kosmos/knowledge/vector_db.py
   - PersistentClient with local storage
   - Paper embeddings for semantic search
   - Optional: HAS_CHROMADB flag

**4. Redis (cache) — optional, disabled by default**
   - REDIS_ENABLED=False by default
   - Used for response caching and rate limiting

**5. File I/O** — Artifact storage in artifacts/ directory, log files in logs/
# Gap Investigation (T6.1-T6.3)

## T6.1: Initialization Sequence
**Required startup order:**
1. .env file must exist (or env vars set) — ANTHROPIC_API_KEY minimum
2. get_config() loads KosmosConfig from env (creates singleton)
3. init_from_config() initializes SQLite database (creates tables, runs migrations)
4. get_client() creates LLM provider singleton (depends on config)
5. Neo4j container must be running for knowledge graph features (auto-started if Docker available)
6. ChromaDB directory must be writable for vector search

**GOTCHA:** first_time_setup() in utils/setup.py is called by init_from_config() and creates .env file if missing, runs Alembic migrations. This means first run may create files in the project root.

## T6.2: Environment Dependencies
**Required external services:**
- LLM API: At least one of Anthropic API, OpenAI API, or local model (Ollama) must be configured
- SQLite: Always required (created automatically)

**Optional external services:**
- Docker: For sandboxed code execution and Neo4j
- Neo4j: For knowledge graph (auto-started via Docker, degrades gracefully)
- Redis: For response caching (disabled by default)
- ChromaDB: For vector search (optional pip install)

**Required Python packages (non-stdlib):**
- pydantic, pydantic-settings — configuration
- anthropic — default LLM provider
- sqlalchemy — database ORM
- typer, rich — CLI
- py2neo — Neo4j (optional)
- chromadb — vector DB (optional)
- litellm — multi-provider (optional)
- httpx — HTTP client for literature APIs

## T6.3: ADK/MCP Integration
The codebase contains multiple sub-projects:
1. **kosmos-reference/kosmos-agentic-data-scientist/** — Google ADK-based agent using Gemini. Contains LoopDetectionAgent (agentic loop detection), ClaudeCodeAgent (Claude Code SDK wrapper), NonEscalatingLoopAgent, StageOrchestratorAgent. Uses google-adk patterns (LlmAgent, LoopAgent).

2. **kosmos-reference/kosmos-claude-scientific-writer/** — Claude-based scientific writer with MCP skills for document generation. Contains its own CLI (cli.py with CC:67), skill system, and paper processing pipeline.

3. **kosmos-claude-scientific-skills/** — MCP skill packages for scientific domains (biorxiv, biomni, ensembl, FDA, matplotlib, medchem, pymatgen, rdkit, reactome, and document skills for docx/pdf/pptx). Each skill package has standalone scripts callable by MCP tool servers.

**IMPORTANT:** These sub-projects are somewhat independent codebases with their own entry points and dependencies. They share some code patterns but are not tightly integrated with the core kosmos/ package.
# Conventions and Patterns (T5.1-T5.4)

## T5.1: Agent Implementation Pattern
**Convention:** All agents inherit from BaseAgent (agents/base.py). [PATTERN: 6/6 agents]

Required implementation pattern:
1. `__init__(self, agent_id, agent_type, config)` — call super().__init__()
2. Extract config keys in __init__: `self.foo = self.config.get("foo", default)`
3. Initialize LLM client: `self.llm_client = get_client()`
4. Override `execute(task: Dict) -> Dict` for main logic
5. Override `process_message(message: AgentMessage)` for message handling

Agents: ResearchDirectorAgent, HypothesisGeneratorAgent, ExperimentDesignerAgent, DataAnalystAgent, LiteratureAnalyzerAgent, and a base SkillLoader agent.

**GOTCHA:** ResearchDirectorAgent.execute() is async; other agents' execute() is sync. Mixed async/sync in the agent hierarchy.

## T5.2: Coding Conventions
**Imports:** Standard library first, third-party second, kosmos.* third. [PATTERN: observed in all files]
**Typing:** 36.6% type coverage (xray metric). Pydantic models fully typed, functions partially typed.
**Docstrings:** Google-style docstrings with Args/Returns sections. [PATTERN: 8/10 top files]
**Logging:** `logger = logging.getLogger(__name__)` at module level. [PATTERN: all files]
**Error classes:** Not standardized — uses stdlib exceptions plus some Pydantic ValidationError.
**Naming:** snake_case functions, PascalCase classes. _private_method prefix for internal methods.

## T5.3: Coupling Anomalies (6 from xray)
1. **config.py ↔ anthropic.py** (score 1.0) — Co-modified without import. Config model names and API settings require coordinated changes. [FACT: coupling_anomalies in xray.json]
2. **experiment_designer.py ↔ research_director.py** (0.8) — Co-modified without import. Both respond to protocol design changes.
3. **research_director.py ↔ code_generator.py** (0.8) — Co-modified without import. Execution chain changes require both.
4. **research_director.py ↔ cli/commands/run.py** (0.8) — Co-modified without import. CLI entry changes require director updates.
5. **anthropic.py ↔ openai.py** (0.8) — Provider implementations co-evolve.
6. **config.py ↔ litellm_provider.py** (0.8) — Config changes for new providers.

## T5.4: Testing Conventions
**Framework:** pytest with conftest.py fixtures. [PATTERN]
**Structure:** tests/{unit, integration, e2e, requirements, manual}/ [FACT: verified via ls]
**Fixtures:** Session-scoped sample data (papers JSON, arXiv XML, PubMed XML) plus per-test temp directories.
**Environment:** conftest.py loads .env at import time (line 24-27).
**Mock pattern:** unittest.mock.MagicMock for LLM clients, httpx responses.
**Count:** ~644 test functions across all test files (grep count).
