# Trace T1.1: CLI run → ResearchDirector → Research Loop → Experiment → Results

## Entry: `kosmos/cli/commands/run.py:run_research()` (L51)
Typer CLI command. Interactive or direct mode.

```
run_research(question, domain, max_iterations, ...) (run.py:51)
  → run_interactive_mode() if no question (cli/interactive.py) — gathers user input via Rich prompts
  → get_config() (config.py) — loads KosmosConfig with nested Pydantic models
  → flattens config to dict (agents expect flat keys, NOT nested KosmosConfig)  [GOTCHA]
  → ResearchDirectorAgent(question, domain, config=flat_config) (research_director.py:53)
      init does:
        → BaseAgent.__init__(agent_id, agent_type, config)
        → _validate_domain() — warns if domain not in enabled_domains but proceeds [GOTCHA: non-fatal]
        → _load_skills() — SkillLoader loads domain-specific prompt injections
        → get_client() (core/llm.py) — gets configured LLM client
        → init_from_config() (db/__init__.py) — initializes SQLAlchemy DB, swallows "already initialized" errors
        → creates asyncio.Lock and threading.RLock (both kept for sync/async compat) [GOTCHA: dual lock pattern]
        → get_world_model() — tries Neo4j knowledge graph, falls back silently if unavailable
  → get_registry().register(director) — registers in AgentRegistry for message routing
  → asyncio.run(run_with_progress_async(director, ...)) (run.py:186)
      → director.execute({"action": "start_research"}) (research_director.py:2868)
          → generate_research_plan() — uses LLM to plan research approach
          → start() — transitions workflow to INITIALIZING
          → decide_next_action() → _execute_next_action(action) (research_director.py:2550)
              dispatches to:
              - GENERATE_HYPOTHESIS → _handle_generate_hypothesis_action()
              - DESIGN_EXPERIMENT → _handle_design_experiment_action(hypothesis_id)
              - EXECUTE_EXPERIMENT → _handle_execute_experiment_action(protocol_id)
              - ANALYZE_RESULT → _handle_analyze_result_action(result_id)
              - REFINE_HYPOTHESES → ...
              - CHECK_CONVERGENCE → convergence_detector.should_stop()
              - REPORT → generate summary
      → while iteration < max_iterations: (run.py:308)
          → director.execute({"action": "step"}) — one cycle
          → director.get_research_status() — checks convergence
          → breaks if has_converged or 2-hour timeout
      → get_session() → get_hypothesis/get_experiment from DB (run.py:404-435)
      → builds results dict with metrics
      → ResultsViewer displays and optionally exports
```

## Key branching:
- Concurrent path: if enable_concurrent=True AND async_llm_client AND multiple untested hypotheses, 
  evaluates hypotheses concurrently via asyncio.wait_for with 300s timeout (research_director.py:2593)
- Fallback: always falls back to sequential on timeout/error
- Error recovery: MAX_CONSECUTIVE_ERRORS=3 with exponential backoff [2,4,8] seconds (research_director.py:44-46)
- Loop guard: MAX_ACTIONS_PER_ITERATION=50 forces convergence to prevent infinite loops (L50)

## Side effects:
- [DB] init_from_config() creates/connects SQLite DB
- [DB] hypotheses, experiments, results stored via kosmos.db.operations
- [GRAPH] Neo4j world model entities created (optional, fails silently)
- [LLM] Multiple API calls to Anthropic/OpenAI during research cycle
- [FILE] Optional JSON/Markdown export via ResultsViewer

## Gotchas:
- Config is FLATTENED from nested KosmosConfig to dict before passing to agents (run.py:148-170)
- Domain validation is non-fatal — warns but proceeds with potentially limited features
- Dual locking: asyncio.Lock for async paths + threading.RLock for sync backwards compat
- 2-hour max_loop_duration hardcoded in run.py:301, separate from config max_runtime_hours
- AgentRegistry.register() is required for message routing but easy to forget
# Trace T1.2: HypothesisGeneratorAgent.execute() → LLM → literature → storage

## Entry: `kosmos/agents/hypothesis_generator.py:HypothesisGeneratorAgent.execute()` (L91)

```
execute(message: AgentMessage) (hypothesis_generator.py:91)
  → sets status = WORKING
  → message.content.get("task_type") == "generate_hypotheses"
  → generate_hypotheses(research_question, num_hypotheses, domain) (hypothesis_generator.py:142)
      → _detect_domain(research_question) if domain not provided — LLM call for domain detection
      → _gather_literature_context(research_question, domain) (hypothesis_generator.py:~200)
          → UnifiedLiteratureSearch() from literature/unified_search.py
          → searches across: Semantic Scholar, arXiv, PubMed
          → returns List[PaperMetadata] (up to max_papers_context=10)
      → _generate_with_claude(research_question, domain, literature_context) 
          → builds prompt using HYPOTHESIS_GENERATOR from core/prompts.py
          → llm_client.generate(prompt, system=system_prompt) 
          → [LLM API CALL] — generates structured hypothesis JSON
          → parses response into List[Hypothesis]
      → for each hypothesis:
          → _validate_hypothesis(hypothesis) — validates testability, statement format
          → if require_novelty_check:
              → novelty_checker.check_novelty(hypothesis) — another LLM call
          → _store_hypothesis(hypothesis) if store_in_db=True
              → with get_session() as session:
              → creates DBHypothesis from Hypothesis runtime model
              → session.add(db_hypothesis) → [DB COMMIT]
      → returns HypothesisGenerationResponse(hypotheses, domain, generation_time, model_used, ...)
  → wraps in AgentMessage(type=RESPONSE) with model_to_dict(response)
  → on error: sets status = ERROR, returns AgentMessage(type=ERROR)
  → finally: sets status = IDLE
```

## Side effects:
- [LLM] Domain detection (optional), hypothesis generation, novelty checking
- [DB] Each hypothesis stored in SQLAlchemy DB via get_session()
- [API] Literature search hits Semantic Scholar / arXiv / PubMed APIs

## Gotchas:
- Hypothesis model validates statement ends with period not question mark (hypothesis.py:94)
- generate_hypotheses has store_in_db=True by default — always writes to DB
- HypothesisGenerationResponse has avg_novelty_score/avg_testability_score (computed post-gen)
- The execute() signature takes AgentMessage, not Dict — different from ResearchDirector's execute()
- UnifiedLiteratureSearch() created in __init__ only if use_literature_context=True (L87)
# Trace T1.4: CodeExecutor.execute() → sandbox/restricted → result collection

## Entry: `kosmos/execution/executor.py:CodeExecutor.execute()` (L237)

```
execute(code, local_vars, retry_on_error, llm_client, language) (executor.py:237)
  → auto-detect language (Python or R) via r_executor.detect_language()
  → if R: route to _execute_r(code) → RExecutor
  → Python path:
    → while attempt < max_retries (if retry_on_error):
        → if use_sandbox AND sandbox available:
            → DockerSandbox.execute(code) (execution/sandbox.py)
            → runs in Docker container with restricted permissions
            → returns SandboxExecutionResult
        → else (no sandbox):
            → _execute_restricted(code, local_vars) 
            → uses SAFE_BUILTINS dict (L43-83) — restrictive but allows scientific modules
            → _ALLOWED_MODULES: numpy, pandas, scipy, sklearn, matplotlib, etc. (L86-94)
            → _make_restricted_import(allowed) — creates custom __import__ (L97)
            → captures stdout/stderr via redirect_stdout/redirect_stderr
            → executes with signal-based timeout (DEFAULT_EXECUTION_TIMEOUT=300s, L39)
        → on error AND retry_on_error AND llm_client:
            → RetryStrategy.fix_code(code, error, llm_client) — LLM repairs code [GOTCHA]
            → retries with fixed code
    → returns ExecutionResult(success, output, error, results, execution_time)
```

## Key facts:
- Sandbox uses Docker when available, falls back to restricted builtins (NO CRASH on missing Docker)
- SAFE_BUILTINS is a restricted set — notably allows print, all numeric types, exceptions
- _ALLOWED_MODULES whitelists scientific stack: numpy, pandas, scipy, sklearn, etc.
- open() and __import__ NOT in SAFE_BUILTINS — code cannot read arbitrary files
- RetryStrategy uses LLM to fix broken code — max_retries=3 default
- 300-second execution timeout for unsandboxed execution

## Gotchas:
- signal.alarm not available on Windows — timeout may not work (platform check at L13: import platform)
- SAFE_BUILTINS includes 'super' and 'object' — object creation possible in restricted mode
- R code support via optional RExecutor — auto-detected if R patterns found
- Executor swallows ImportError for sandbox and R — graceful degradation pattern
# Trace T1.5: scientific_evaluation.py main() → 6-phase evaluation

## Entry: `evaluation/scientific_evaluation.py:main()` (top-level script)

```
main() (scientific_evaluation.py)
  → argparse: --output-dir, --research-question, --domain, --data-path, --max-iterations
  → init_from_config() (db init)
  → ResearchDirectorAgent(research_question, domain, config)
  → asyncio.run(director.execute({"action": "start_research"}))
  → Phase evaluation pipeline (6 phases):
    Phase 1: Hypothesis Generation Quality
    Phase 2: Experiment Design Validation 
    Phase 3: Research Loop Execution
    Phase 4: Data Analysis Pipeline (with optional real data)
    Phase 5: Literature Integration
    Phase 6: Scientific Rigor Scorecard (CC=28, run_phase6_rigor_scorecard L816)
  → Each phase produces PhaseResult with score/details
  → Final report: JSON + human-readable summary

## Key observations:
- Phase 6 has CC=28 (complexity hotspot) — 8 independent try/except blocks scoring rigor features
- Evaluation uses same research pipeline as production — not a mock
- Evaluation resets database between runs for isolation via reset_database()
- Output directory for results: evaluation/{version}/ with auto-incrementing versions
# Trace T1.3: ExperimentDesignerAgent.execute() → template/LLM → protocol

## Entry: `kosmos/agents/experiment_designer.py:ExperimentDesignerAgent.execute()` (L~50)

```
execute(message: AgentMessage)
  → task_type == "design_experiment"
  → design_experiment(hypothesis_id, domain, ...)
      → _load_hypothesis(hypothesis_id) — loads from DB via get_session()
      → _select_experiment_type(hypothesis) — determines COMPUTATIONAL/DATA_ANALYSIS/LITERATURE_SYNTHESIS
      → if use_templates:
          → _generate_from_template(hypothesis, experiment_type)
          → template_registry.get_template(experiment_type, domain)
          → fills template with hypothesis-specific parameters
      → if use_llm_enhancement:
          → _generate_with_claude(hypothesis, experiment_type) or _enhance_protocol_with_llm()
          → LLM call to design experiment protocol with statistical power analysis
          → _parse_claude_protocol(response) — extracts structured ExperimentProtocol
      → _validate_protocol(protocol)
          → checks: control group present, power analysis present, rigor score >= threshold
          → returns validation_passed, warnings[], errors[]
      → stores ExperimentProtocol in DB
      → returns ExperimentDesignResponse

## Config keys:
- require_control_group: True (default)
- require_power_analysis: True (default)  
- min_rigor_score: configurable
- use_templates: True (default) — domain-specific experiment templates
- use_llm_enhancement: True (default) — LLM refines template output

## Templates directory:
- kosmos/experiments/templates/{domain}/ — biology, neuroscience, materials
- Base template class in experiments/templates/base.py
# Module: kosmos/agents/base.py — BaseAgent (T2.1)

## What this module does
Defines the BaseAgent abstract base class that ALL Kosmos agents inherit from. Provides lifecycle management (start/stop/pause/resume), message passing (async+sync), state persistence, and statistics tracking.

## Non-obvious behaviors
- Message queue is DUAL: both a legacy sync list `message_queue` (L136) AND an async `_async_message_queue` (L137). Both are always populated on receive.
- `start()` can only be called from CREATED status — calling it twice is a no-op with warning (L161-163). [GOTCHA]
- `process_message()` default implementation just logs a warning — easy to forget to override (L391)
- `send_message()` checks for both sync and async routers via `asyncio.iscoroutine(result)` (L294)
- `send_message_sync()` wraps with run_coroutine_threadsafe or asyncio.run fallback (L313-327)
- `execute()` raises NotImplementedError — MUST be overridden

## Blast radius
- ALL agent classes inherit from this: ResearchDirectorAgent, HypothesisGeneratorAgent, ExperimentDesignerAgent, DataAnalystAgent, LiteratureAnalyzerAgent
- AgentMessage is the universal message format (Pydantic model with type, content, correlation_id)
- AgentStatus enum used everywhere for agent state checks
- MessageType enum (REQUEST/RESPONSE/NOTIFICATION/ERROR) used in all agent communication

## Key types
- AgentStatus: CREATED → STARTING → RUNNING → IDLE → WORKING → PAUSED → STOPPED → ERROR
- AgentMessage: Pydantic model (id, type, from_agent, to_agent, content, correlation_id, timestamp)
- AgentState: for persistence (agent_id, agent_type, status, data)
# Module: kosmos/config.py — Configuration (T2.3)

## What this module does
Centralized Pydantic-based configuration loaded from env vars and .env file. Houses ALL config: LLM providers (Anthropic/OpenAI/LiteLLM), research params, database, Redis, logging, safety, performance, monitoring, world model.

## Non-obvious behaviors
- KosmosConfig uses pydantic_settings to load from .env file AND environment variables
- ClaudeConfig, OpenAIConfig, LiteLLMConfig are OPTIONAL — created only if their API key env var is set (L896-919)
- CLI mode detection: `api_key.replace('9', '') == ''` — all-9s key routes to Claude Code CLI [GOTCHA]
- LiteLLM env vars require MANUAL SYNC via model_validator because nested BaseSettings don't auto-inherit parent .env (L986-1022)
- get_config() is a SINGLETON with global `_config` — thread-safe via global var, NOT lock-protected [GOTCHA]
- Config is FLATTENED by run.py before passing to agents — agents don't receive KosmosConfig directly

## Blast radius
- Risk score 0.96 (highest in codebase) — 27 churn, 18 hotfixes, 4 authors
- 53 modules import config.py
- Changes to field names break environment variable binding
- Changes to nesting break the flattening logic in run.py:148-170

## Key config classes
- KosmosConfig (master): llm_provider, claude, openai, litellm, research, database, redis, logging, safety, performance, world_model
- ClaudeConfig: api_key, model (claude-sonnet-4-5), max_tokens=4096, temperature=0.7, enable_cache=True
- ResearchConfig: max_iterations=10, enabled_domains, budget_usd=10.0, max_runtime_hours=12.0
- DatabaseConfig: url="sqlite:///kosmos.db", normalized_url property converts relative paths to absolute
- SafetyConfig: enable_code_validation=True, require_human_approval=False
- PerformanceConfig: max_concurrent_experiments=10, max_concurrent_llm_calls=5
# Module: kosmos/core/llm.py — LLM Client (T2.4)

## What this module does
Multi-provider LLM integration with unified interface. Contains ClaudeClient (legacy) and get_client() factory function. The get_client() singleton decides between ClaudeClient, AnthropicProvider, OpenAIProvider, or LiteLLMProvider based on config.

## Non-obvious behaviors
- CIRCULAR DEPENDENCY with kosmos.core.providers.anthropic — both import from each other's namespace [GOTCHA]
- get_client() is a SINGLETON protected by threading.Lock (_client_lock) — double-checked locking pattern (L640-649)
- ClaudeClient.generate() returns str, NOT LLMResponse — different from LLMProvider.generate() which returns LLMResponse [GOTCHA]
- LLMResponse has str-compatible methods (strip(), lower(), etc.) so it works in str contexts (base.py:80-153) [GOTCHA]
- ModelComplexity.estimate_complexity() scores prompts for Haiku vs Sonnet auto-selection (L52-105)
  - Keywords like 'analyze', 'synthesis', 'complex' push toward Sonnet
  - Always recommends "sonnet" for score >= 30 (effectively never picks haiku for complex tasks)
- Response caching via ClaudeCache — keyed on prompt+model+params hash

## Blast radius
- 27 modules import this directly
- All hypothesis generation, experiment design, analysis, refinement flow through this
- Changing return types would break many callers that expect either str or str-compatible LLMResponse

## Key interfaces
- get_client(reset=False, use_provider_system=True) → Union[ClaudeClient, LLMProvider]
- ClaudeClient.generate(prompt, system, ...) → str
- LLMProvider.generate(prompt, system, ...) → LLMResponse (has .content: str)
# Module: kosmos/core/workflow.py — Workflow State Machine (T2.5)

## What this module does
Defines the research workflow state machine (ResearchWorkflow) and the research plan tracker (ResearchPlan).

## States and transitions
INITIALIZING → GENERATING_HYPOTHESES → DESIGNING_EXPERIMENTS → EXECUTING → ANALYZING → REFINING → (loop or CONVERGED)
- Error recovery: ERROR → INITIALIZING or GENERATING_HYPOTHESES
- PAUSED can resume to any active state
- CONVERGED can restart to GENERATING_HYPOTHESES (new research question)

## Non-obvious behaviors
- ResearchPlan is a Pydantic model — ALL tracking (hypothesis_pool, experiment_queue, results) are just List[str] of IDs, not objects
- Research plan tracks convergence via boolean has_converged and string convergence_reason
- transition_to() raises ValueError on invalid transitions — not silently ignored [GOTCHA]
- Transition history records full audit trail with timestamps
- get_state_duration() calculates cumulative time in any state — useful for performance monitoring

## Blast radius
- 26 modules import this (pillar #7)
- WorkflowState enum used in CLI progress display, research director, and logging
- NextAction enum drives the entire research director dispatch logic
# Cross-Cutting: Configuration Surface (T4.2)

## Config hierarchy (highest precedence first):
1. CLI arguments (typer options in run.py)
2. Environment variables (via pydantic_settings)
3. .env file at project root (loaded by KosmosConfig)
4. Default values in Pydantic fields

## Critical environment variables:
| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| ANTHROPIC_API_KEY | Yes (for anthropic) | None | Claude API key or all-9s for CLI mode |
| OPENAI_API_KEY | Yes (for openai) | None | OpenAI API key |
| LLM_PROVIDER | No | "anthropic" | Provider selection: anthropic/openai/litellm |
| DATABASE_URL | No | sqlite:///kosmos.db | Database connection |
| NEO4J_URI | No | bolt://localhost:7687 | Neo4j for world model |
| NEO4J_USER | No | neo4j | Neo4j auth |
| NEO4J_PASSWORD | No | None | Neo4j auth |
| REDIS_ENABLED | No | false | Enable Redis caching |
| REDIS_URL | No | redis://localhost:6379/0 | Redis connection |
| MAX_RESEARCH_ITERATIONS | No | 10 | Research loop limit |
| RESEARCH_BUDGET_USD | No | 10.0 | API cost budget |
| KOSMOS_SKILLS_DIR | No | None | Custom skills directory |
| LOG_LEVEL | No | INFO | Logging level |
| DEBUG_MODE | No | false | Verbose debug logging |

## Config gotchas:
- CLI mode: ANTHROPIC_API_KEY=999...999 routes through Claude Code CLI, not API [FACT: config.py:82]
- Config flattening: run.py:148-170 manually flattens nested config to dict for agents
- LiteLLM env vars need manual sync via model_validator [FACT: config.py:986-1022]
- DatabaseConfig.normalized_url converts relative SQLite paths to absolute [FACT: config.py:270-300]
- get_config() is a singleton — once loaded, env var changes are NOT picked up [GOTCHA]
# Cross-Cutting: Error Handling Strategy (T4.1)

## Dominant strategy: catch-log-continue per module, halt on consecutive errors at director level

### Pattern 1: Agent-level error isolation
All agents catch exceptions in execute(), log them, set status=ERROR, and return error messages.
Never crash the research loop — errors become data.
[PATTERN: 6/6 agent classes follow this — hypothesis_generator.py:128, experiment_designer.py, data_analyst.py, literature_analyzer.py, research_director.py, registry.py]

### Pattern 2: ResearchDirector error recovery with exponential backoff
- MAX_CONSECUTIVE_ERRORS = 3 (research_director.py:45)
- ERROR_BACKOFF_SECONDS = [2, 4, 8] (research_director.py:46)
- After 3 consecutive errors → halt research and report
- On each error → classify recoverable vs non-recoverable
- Recoverable → backoff + retry, Non-recoverable → halt immediately

### Pattern 3: Optional dependency graceful degradation
- Docker sandbox: ImportError → fallback to restricted builtins (executor.py:24-29)
- Neo4j world model: Exception → continue without graph persistence (research_director.py:242-254)
- R executor: ImportError → Python-only mode (executor.py:33-37)
- Anthropic package: ImportError → HAS_ANTHROPIC=False, raise on use (llm.py:23-31)
[PATTERN: 8/8 optional dependencies use try/except ImportError with fallback]

### Pattern 4: Swallowed exceptions (risky)
- base.py:286-287: config not available → pass (suppress logging config errors)
- research_director.py:135-137: "already initialized" DB errors → pass
- 617 total except-pass or bare-except hits across 120 files [FACT]
[ABSENCE: No global exception handler or crash reporter — errors stay in logs]

### Pattern 5: LLM error classification
- ProviderAPIError has is_recoverable() method (base.py:445-484)
- Status codes 429 (rate limit), 5xx → recoverable
- Status codes 400-4xx (except 429) → non-recoverable
- Pattern-based: "timeout", "connection" → recoverable; "authentication", "invalid" → non-recoverable
# Gap Investigation: Initialization Sequences (T6.1)

## Required initialization order:
1. Environment (.env file must exist with at minimum ANTHROPIC_API_KEY or OPENAI_API_KEY)
2. get_config() — loads and validates all config (first call creates singleton)
3. init_from_config() or init_database() — creates/connects to database
4. get_client() — initializes LLM client singleton
5. Agent creation (ResearchDirectorAgent, etc.) — calls get_client() and init_from_config() internally

## What auto-initializes:
- ResearchDirectorAgent.__init__() calls init_from_config() itself (L131-139)
- ResearchDirectorAgent.__init__() calls get_client() itself (L128)
- get_config() auto-loads from .env if present
- first_time_setup() creates .env from template if missing

## What does NOT auto-initialize:
- Neo4j connection (requires NEO4J_URI, NEO4J_PASSWORD env vars)
- Redis connection (requires REDIS_ENABLED=true)
- Docker sandbox (requires Docker daemon running)
- ChromaDB (requires chromadb package installed)

## Gotchas:
- If ANTHROPIC_API_KEY is not set AND LLM_PROVIDER is not changed → config validation fails
- Database init swallows "already initialized" errors but logs warnings (research_director.py:136)
- first_time_setup() can CREATE .env file with default values — may overwrite
# Cross-Cutting: LLM Provider Strategy (T4.3)

## Architecture:
LLMProvider (ABC) → AnthropicProvider, OpenAIProvider, LiteLLMProvider
- get_client() factory decides based on KosmosConfig.llm_provider
- Fallback chain: config provider → AnthropicProvider direct → ClaudeClient legacy

## Provider implementations:
1. AnthropicProvider (providers/anthropic.py): Direct Anthropic SDK, prompt caching, auto model selection
2. OpenAIProvider (providers/openai.py): OpenAI SDK, supports OpenAI-compatible APIs (Ollama, OpenRouter)
3. LiteLLMProvider (providers/litellm_provider.py): 100+ providers via litellm package
4. ClaudeClient (core/llm.py): Legacy client, backward-compatible, still used if use_provider_system=False

## Key differences:
- ClaudeClient.generate() returns str
- LLMProvider.generate() returns LLMResponse (but LLMResponse acts like str via delegation)
- ClaudeClient tracks cache_hits/cache_misses directly
- LLMProvider tracks via _update_usage_stats()

## CLI mode:
- API key of all 9s → routes through Anthropic SDK which proxies to Claude Code CLI
- Detected via: api_key.replace('9', '') == '' [FACT: config.py:82, llm.py:179, anthropic.py:110]

## Circular dependency:
- llm.py imports from providers.anthropic (indirectly via get_provider_from_config)
- providers.anthropic imports from config.py which imports model names from llm.py
- Both llm.py and providers/anthropic.py import _DEFAULT_CLAUDE_SONNET_MODEL from config.py
[FACT: xray circular deps: llm <-> providers.anthropic]
# Cross-Cutting: Database and Persistence (T4.6)

## Storage systems (4 independent):
1. **SQLAlchemy/SQLite** (kosmos/db/): Primary store for hypotheses, experiments, results
   - Default: sqlite:///kosmos.db (relative to project root, normalized via config)
   - Connection pooling for PostgreSQL, basic for SQLite
   - get_session() context manager with auto-commit/rollback
   - init_from_config() runs first_time_setup including migrations
   - Alembic migrations in kosmos/alembic/

2. **ChromaDB** (kosmos/knowledge/vector_db.py): Vector embeddings for semantic search
   - Singleton pattern via global _vector_db
   - Used for hypothesis similarity, literature dedup
   - Optional — graceful degradation if unavailable

3. **Neo4j** (kosmos/world_model/simple.py): Knowledge graph for entity relationships
   - Stores: papers, concepts, authors, methods, research questions
   - Mode: "simple" (Neo4j direct) or "production" (polyglot)
   - Optional — ResearchDirector continues without it (research_director.py:252-254)

4. **File-based** (kosmos/core/claude_cache.py): Response caching
   - Caches LLM responses keyed on prompt hash
   - Default TTL from config (redis.default_ttl_seconds=3600)

## Initialization sequence:
1. get_config() loads from env/dotenv
2. init_from_config() → first_time_setup() → init_database()
3. Database tables created via Base.metadata.create_all()
4. Optional: get_world_model() for Neo4j

## Gotchas:
- Database not auto-initialized — must call init_from_config() or init_database() first
- get_session() raises RuntimeError("Database not initialized") if called before init
- reset_database() exists but DROPS ALL TABLES — evaluation isolation only
- SQLite check_same_thread=False needed for multi-threaded access [FACT: db/__init__.py:77]
# Gap Investigation: Reference Code vs Core (T6.3)

## Structure:
- kosmos/ (core): 802 Python files (the actual system)
- kosmos-reference/ (231 files): Reference implementations of related projects
  - kosmos-agentic-data-scientist/: ADK-based agent for data science tasks
  - kosmos-claude-scientific-writer/: Scientific paper writing assistant with CLI
  - kosmos-claude-skills-mcp/: MCP server for Claude Code skills
  - kosmos-karpathy/: Reference implementation (likely from Karpathy's work)
- kosmos-claude-scientific-skills/ (142 files): Scientific domain skill scripts
  - Skills for: biorxiv, diffdock, rdkit, medchem, pymatgen, pufferlib, etc.
  - Each skill is a standalone script with main() entry point
  - Loaded by SkillLoader from kosmos/agents/skill_loader.py

## Key distinction:
- kosmos-reference/ code is NOT imported by the core system (xray: all leaf/orphan nodes)
- kosmos-claude-scientific-skills/ scripts ARE used — loaded by SkillLoader for domain-specific prompts
- The "802 files" xray count includes BOTH core + skills + reference
- Actual core codebase: ~400 files in kosmos/ directory

## Gotcha:
- xray investigation_targets include many duplicates from reference code
  (same script appears in 3 places: skills/, reference/.claude/skills/, reference/scientific_writer/.claude/skills/)
# Cross-Cutting: Safety and Code Validation (T4.5)

## Safety layers:
1. **CodeValidator** (safety/code_validator.py): Static analysis of generated code
   - DANGEROUS_MODULES blacklist: os, subprocess, sys, shutil, importlib, socket, etc.
   - DANGEROUS_PATTERNS: eval(, exec(, compile(, __import__, open(
   - NETWORK_KEYWORDS: socket, http, urllib, requests
   - Ethical guidelines loaded from JSON or defaults
   - Risk levels: LOW, MEDIUM, HIGH, CRITICAL
   - Approval gate: if require_human_approval=True in SafetyConfig → human must approve HIGH/CRITICAL

2. **Executor restricted builtins** (execution/executor.py:43-94):
   - SAFE_BUILTINS: curated set of safe Python builtins
   - _ALLOWED_MODULES: scientific stack only (numpy, pandas, scipy, sklearn, etc.)
   - Custom __import__ blocks unapproved modules

3. **Docker sandbox** (execution/sandbox.py):
   - Optional isolation layer
   - CPU/memory/timeout limits configurable
   - Graceful fallback to restricted builtins if Docker unavailable

4. **ApprovalRequest** (models/safety.py):
   - Pydantic model for human-in-the-loop approval
   - Tracks: operation_type, risk_level, reason, status (pending/approved/rejected)

## Config (SafetyConfig):
- enable_code_validation: True (default)
- require_human_approval: False (default) — can be turned on
- max_code_length: configurable
- sandbox_timeout: configurable
# Conventions and Patterns (T5.1, T5.2, T5.3)

## C1: Agent implementation convention
Every agent inherits BaseAgent and follows this lifecycle:
1. __init__(agent_id, agent_type, config) → super().__init__() → component initialization
2. execute(task/message) → main logic → returns result/message
3. Error handling: try/except in execute(), set status=ERROR, return error message
4. Components initialized in __init__: llm_client = get_client(), optional literature search, DB setup
[PATTERN: 6/6 agent classes follow this exactly]

## C2: Config-driven initialization
All agents read config via self.config.get("key", default). Config is a flat dict, NOT KosmosConfig.
[PATTERN: 6/6 agents use self.config.get() pattern]

## C3: Singleton factories
Module-level globals with get_* factory functions:
- get_config() → KosmosConfig singleton (config.py:1150)
- get_client() → ClaudeClient/LLMProvider singleton (llm.py:613)
- get_session() → DB session context manager (db/__init__.py:108)
- get_world_model() → WorldModelStorage (world_model/__init__.py)
- get_registry() → AgentRegistry (agents/registry.py)
- get_stage_tracker() → StageTracker (core/stage_tracker.py)
[PATTERN: 8/8 singleton services use this pattern]

## C4: Data model dual representation
Runtime models (Pydantic in kosmos/models/) vs DB models (SQLAlchemy in kosmos/db/models.py):
- Hypothesis: models/hypothesis.py (Pydantic) ↔ db/models.py (SQLAlchemy)
- Experiment: models/experiment.py (Pydantic) ↔ db/models.py (SQLAlchemy)
- Result: models/result.py (Pydantic) ↔ db/models.py (SQLAlchemy)
- Conversion: model_to_dict() from kosmos/utils/compat.py used everywhere
[PATTERN: 3/3 core entities have dual models]

## C5: Optional dependency pattern
try/except ImportError with feature flag:
```python
try:
    from package import Module
    HAS_FEATURE = True
except ImportError:
    HAS_FEATURE = False
```
[PATTERN: 8/8 optional deps follow this — anthropic, docker, neo4j, chromadb, R, litellm, etc.]

## C6: Async/sync dual API
All agent methods have async primary + sync wrapper:
- send_message() (async) + send_message_sync()
- receive_message() (async) + receive_message_sync()
- process_message() (async) + process_message_sync()
- execute() can be either — ResearchDirector is async, others are sync
[PATTERN: observed in base.py L246-404]

## Convention deviations (T5.3):
- 36 classes use untyped __init__ args instead of typed injection
  - Mostly in kosmos-claude-scientific-skills (templates, validators)
  - Core agents all use typed injection correctly
  - Deviation is localized to "skills" scripts, not core architecture

## Coupling anomalies:
- config.py ↔ anthropic.py: co-modified 100% without import relationship [FACT: xray coupling data]
  - Both change when LLM model or API behavior changes — implicit coupling through env vars
- experiment_designer ↔ research_director: 80% co-modified without imports
  - Connected through workflow state machine, not direct imports
- research_director ↔ code_generator: 80% co-modified
  - Connected through executor, not direct calls
