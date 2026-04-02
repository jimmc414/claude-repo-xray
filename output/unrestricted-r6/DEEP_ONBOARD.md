# Kosmos: Agent Onboarding

> Codebase: 802 files, ~2,455,608 tokens
> This document: ~40,000 tokens (refined)
> Generated: 2026-03-29 from commit `3ff33c3`
> Crawl: 35/35 tasks, 19 modules read
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---
## Identity

Kosmos is an autonomous scientific research platform that orchestrates AI agents to conduct end-to-end research: generating hypotheses, designing experiments, generating and executing code in sandboxes, analyzing results, and iterating through a convergence-driven research loop. Built on Python with Anthropic/OpenAI LLM providers, Neo4j knowledge graphs, ChromaDB vector storage, and SQLAlchemy persistence. The codebase spans 802 Python files across 20 subsystems (agents, execution, knowledge, literature, orchestration, safety, etc.) with a CLI interface (`kosmos run`) and evaluation framework.

---
## Critical Paths

The following traces document the complete request flows through the Kosmos codebase. Two shared sub-paths recur across multiple traces and are documented once here.

#### Shared Sub-Path A: Initialization Sequence
Used by: Path 1 (CLI Run), Path 10 (Scientific Evaluation), Path 11 (Persona Evaluation)
```
get_config() (config.py:1140) — Singleton, reads env vars
  → get_client() (llm.py:613) — Singleton LLM client (Anthropic or provider-based)
  → init_from_config() (db/__init__.py:140) — Creates SQLAlchemy tables [SIDE EFFECT]
  → get_world_model() (factory.py:55) — Singleton, Neo4j or in-memory fallback
  → ResearchDirectorAgent.__init__() (research_director.py:68) — Full orchestration stack
```

#### Shared Sub-Path B: LLM Structured Generation
Used by: Path 3 (Hypothesis Generation), Path 4 (Experiment Design), Path 6 (Result Analysis)
```
llm_client.generate_structured(prompt, schema, max_tokens, temperature) (llm.py:410)
  → Appends JSON schema instruction to system prompt (llm.py:456-457)
  → Retry loop: up to max_retries + 1 = 3 attempts (llm.py:460)
  → [BRANCH] On retry, bypasses cache (bypass_cache=attempt > 0) (llm.py:466)
  → ClaudeClient.generate() (llm.py:207) — cache check → API call → token tracking
  → parse_json_response() (core/utils/json_parser.py:31) — 5 fallback strategies
  → On total failure: raises ProviderAPIError with recoverable=False (llm.py:481-486)
```

### 1. CLI Entry: `kosmos run` to Research Loop

```
run_research() (kosmos/cli/commands/run.py:51)
  — Typer command. Accepts question, domain, max_iterations, budget, data_path, streaming flags.
  — [BRANCH] If interactive or no question → run_interactive_mode() (run.py:87-99)
  — [BRANCH] If no question after interactive → typer.Exit(1) (run.py:102-104)
  — [BRANCH] If data_path provided but not exists → typer.Exit(1) (run.py:107-109)
  — Data transformation: CLI parameters → flat_config dict (run.py:148-171)
    [FACT] Nested KosmosConfig is flattened because agents expect flat keys (run.py:147 comment)
  → get_config() (kosmos/config.py:1140) — Singleton. Creates KosmosConfig from env, calls create_directories() (config.py:1151-1153)
  → ResearchDirectorAgent.__init__() (kosmos/agents/research_director.py:68)
    — Initializes: ResearchPlan (Pydantic), ResearchWorkflow (state machine), LLM client, DB, convergence detector, world model (Neo4j), rollout tracker, error recovery state, async locks (research_director.py:68-260)
    → get_client() (kosmos/core/llm.py:613) — Singleton. Tries provider system from config, falls back to AnthropicProvider (llm.py:652-664)
    → init_from_config() (kosmos/db/__init__.py:140) — Runs first_time_setup(), creates SQLAlchemy tables
      → [SIDE EFFECT: table creation] (db/__init__.py:140-179)
    → get_world_model() (kosmos/world_model/factory.py:55) — Singleton. Returns Neo4jWorldModel wrapping KnowledgeGraph (factory.py:55-104)
    → Entity.from_research_question() → wm.add_entity()
      → [SIDE EFFECT: Neo4j entity write] (research_director.py:245-251)
    → SkillLoader().load_skills_for_task() — Loads domain-specific prompt fragments (research_director.py:280-307)
    — [BRANCH] If concurrent operations enabled → also initializes ParallelExperimentExecutor and AsyncClaudeClient (research_director.py:208-239)
  → get_registry() (kosmos/agents/registry.py:512) — Singleton registry
  → registry.register(director) (registry.py:70) — Adds to _agents dict, sets message router callback
    [FACT] Sets agent.set_message_router(self._route_message) for async message passing (registry.py:94)
  → asyncio.run(run_with_progress_async(director, question, max_iterations, ...)) (run.py:186)
    → run_with_progress_async() (run.py:225) — Manages Rich live progress display

    Phase A: Start Research (run.py:296):
      → director.execute({"action": "start_research"}) (research_director.py:2868)
        → generate_research_plan() (research_director.py:2349)
          → self.llm_client.generate(prompt, max_tokens=1000) (research_director.py:2372)
            → [SIDE EFFECT: LLM API call to Claude]
            [FACT] Prompt asks Claude for hypothesis directions, experiment strategy, success criteria, resource considerations (research_director.py:2356-2368)
        → start() → _on_start() (research_director.py:319)
          → workflow.transition_to(WorkflowState.GENERATING_HYPOTHESES) (research_director.py:329)
            [FACT] Transitions INITIALIZING → GENERATING_HYPOTHESES (research_director.py:329-331)
        → decide_next_action() (research_director.py:2388)
        → _execute_next_action(next_action) (research_director.py:2889)

    Phase B: Iterative Loop (run.py:308-389):
      while iteration < max_iterations:
        — [BRANCH] Timeout check: elapsed > 7200s → break (run.py:313-319)
        — [BRANCH] Convergence check: status.get("has_converged") → break (run.py:362-365)
        → director.execute({"action": "step"})
        → asyncio.sleep(0.05) — UI update delay

  ✗ on failure: Each action wrapped in error recovery. BudgetExceededError → CONVERGE. Runtime exceeded → CONVERGE.
```

### 2. State Machine Decision: `decide_next_action()`

```
decide_next_action() (kosmos/agents/research_director.py:2388)
  — Decision tree based on workflow.current_state.
  — Guard rails checked first:
    → [BRANCH] Budget enforcement: imports get_metrics(), calls enforce_budget()
      On BudgetExceededError → CONVERGE (research_director.py:2404-2422)
      [FACT] Import is inside function body, re-imported each time. Fails silently if metrics module unavailable (ImportError caught) (research_director.py:2406-2425)
    → [BRANCH] Runtime limit: _check_runtime_exceeded() → CONVERGE (research_director.py:2428-2446)
    → [BRANCH] Loop guard: _actions_this_iteration > 50 → force CONVERGE (research_director.py:2455-2461)
      [FACT] _actions_this_iteration uses hasattr check for lazy initialization. Not initialized in __init__ (research_director.py:2451-2453)

  State→Action routing (research_director.py:2483-2548):
    GENERATING_HYPOTHESES → GENERATE_HYPOTHESIS
    DESIGNING_EXPERIMENTS → DESIGN_EXPERIMENT (if untested hyps) | EXECUTE_EXPERIMENT (if queue) | ANALYZE_RESULT (if results) | CONVERGE
    EXECUTING → EXECUTE_EXPERIMENT (if queue) | ANALYZE_RESULT (if results) | REFINE_HYPOTHESIS
    ANALYZING → ANALYZE_RESULT (if results) | EXECUTE_EXPERIMENT | REFINE_HYPOTHESIS
    REFINING → REFINE_HYPOTHESIS (if tested hyps) | GENERATE_HYPOTHESIS
    CONVERGED → CONVERGE
    ERROR → ERROR_RECOVERY

  → _execute_next_action(action) (research_director.py:2550)
    → tracker.track(f"ACTION_{action.value}") — stage tracker context
    → _do_execute_action(action) (research_director.py:2573) — routes to 1 of 7 handlers

  ✗ on failure: ERROR state → ERROR_RECOVERY → workflow.transition_to(GENERATING_HYPOTHESES) (research_director.py:2716-2728)
    [FACT] MAX_CONSECUTIVE_ERRORS = 3 with exponential backoff [2, 4, 8] seconds (research_director.py:44-46)
```

### 3. Hypothesis Generation Pipeline

```
_handle_generate_hypothesis_action() (kosmos/agents/research_director.py:1391)
  → HypothesisGeneratorAgent(config=self.config) — lazy-init (research_director.py:1404)
  → agent.generate_hypotheses(question, num=3, domain, store_in_db=True) (research_director.py:1408)
    — Orchestrates 6-step pipeline. Returns HypothesisGenerationResponse (Pydantic).

    Step 1: _detect_domain(question) (hypothesis_generator.py:259)
      → llm_client.generate(prompt, max_tokens=50, temperature=0.0) (hypothesis_generator.py:275)
        → [SIDE EFFECT: Anthropic API call]
      — Normalizes response to lowercase+underscores. Falls back to "general" on any exception.
        [FACT] (hypothesis_generator.py:286)

    Step 2: _gather_literature_context(question, domain) (hypothesis_generator.py:289)
      → UnifiedLiteratureSearch.search(query, max_results=10) (unified_search.py:76)
        → ThreadPoolExecutor: ArxivClient.search() + SemanticScholarClient.search() + PubMedClient.search() (unified_search.py:147-161)
          → [SIDE EFFECT: HTTP calls to arXiv, Semantic Scholar, PubMed APIs]
        → _deduplicate_papers() (unified_search.py:371) — DOI > arXiv ID > PubMed ID > title dedup
        → _rank_papers() (unified_search.py:449) — citation count + title relevance + abstract relevance + recency
        — [BRANCH] Timeout path collects partial results. Per-source errors logged and skipped (unified_search.py:172-183)
          [FACT] On timeout, already-completed source results are still included. A slow PubMed won't discard fast arXiv results (unified_search.py:172-183)
      — Returns empty list on error (hypothesis_generator.py:320)

    Step 3: _generate_with_claude(question, domain, n, papers) (hypothesis_generator.py:322)
      — Builds literature context from top 5 papers (title + year + 200-char truncated abstract)
        [FACT] Even though up to 10 papers fetched, only 5 used in prompt (hypothesis_generator.py:346-347)
      → HYPOTHESIS_GENERATOR.render(...) (prompts.py:105) — template via Template.safe_substitute()
        [FACT] (prompts.py:74)
      → llm_client.generate_structured(prompt, schema, max_tokens=4000, temperature=0.7) (hypothesis_generator.py:378-383)
        [FACT] Temperature 0.7 for creativity. Schema enforces statement, rationale, confidence_score, testability_score, suggested_experiment_types.
        → ClaudeClient.generate_structured() (llm.py:410)
          — Appends JSON schema instruction to system prompt (llm.py:456-457)
          — Retry loop: up to max_retries + 1 = 3 attempts (llm.py:460)
          — [BRANCH] On retry, bypasses cache (bypass_cache=attempt > 0) (llm.py:466)
            [FACT] Retries bypass cache to avoid getting same bad response (llm.py:466)
          → ClaudeClient.generate() (llm.py:207)
            — [BRANCH] Model selection: auto-select (Haiku vs Sonnet based on complexity) or use default (llm.py:246-268)
              [FACT] ModelComplexity.estimate_complexity() scores prompts 0-100 by token count + keyword matches (llm.py:53-105)
            — [BRANCH] If API key is all 9s, routes to CLI mode (llm.py:179)
            → Cache check via ClaudeCache.get() (llm.py:278-303)
            → client.messages.create(model, max_tokens, temperature, system, messages) (llm.py:309)
              → [SIDE EFFECT: Anthropic API call]
            → Token stats tracking (input/output) (llm.py:320-324)
            — [FACT] Logs warning if stop_reason == 'max_tokens' (llm.py:329-330)
            → Cache response via ClaudeCache.set() (llm.py:336-358)
          → parse_json_response() (core/utils/json_parser.py:31) — 5 fallback strategies
          — On total failure: raises ProviderAPIError with recoverable=False (llm.py:481-486)
      → Parses JSON into List[Hypothesis] with UUID ids (hypothesis_generator.py:387-420)
      — Maps experiment type strings to ExperimentType enum (hypothesis_generator.py:391-395)
      — Attaches related_papers from context papers (hypothesis_generator.py:407-411)
      — [BRANCH] Per-hypothesis parse errors logged and skipped (hypothesis_generator.py:416-418). Returns empty list on total failure (hypothesis_generator.py:424)

    Step 4: _validate_hypothesis(hyp) loop (hypothesis_generator.py:426)
      — Validates: statement length >= 15 chars (line 441), rationale length >= 30 chars (line 446)
      — [FACT] Vague language check ("maybe", "might", etc.) warns but does NOT reject (hypothesis_generator.py:451-455). Comment: "Don't fail, but warn."

    Step 5: NoveltyChecker.check_novelty(hyp) loop (novelty_checker.py:72)
      — [FACT] NoveltyChecker import is guarded. If module cannot be imported, ALL hypotheses pass without scoring. Fail-open design (hypothesis_generator.py:227-228)
      — [FACT] Per-hypothesis novelty errors fail open -- hypothesis is kept (hypothesis_generator.py:223-224)
      — Instantiated with similarity_threshold = 1.0 - min_novelty_score. Default min_novelty_score=0.5 → threshold=0.5
        [FACT] This is lower than NoveltyChecker's own default of 0.75 (hypothesis_generator.py:211)
      → _search_similar_literature(hyp) (novelty_checker.py:182)
        — [BRANCH] Vector path: vector_db.search(query, top_k=20) (novelty_checker.py:194-195)
        — [BRANCH] Keyword path: literature_search.search(query, max_results=20) (novelty_checker.py:198-199)
          [FACT] Keyword fallback also indexes retrieved papers into vector DB as side-effect (novelty_checker.py:207-210)
      → _check_existing_hypotheses(hyp) (novelty_checker.py:260)
        → DB query: DBHypothesis filtered by domain (novelty_checker.py:273)
          → [SIDE EFFECT: DB read]
        — Filters by similarity >= 0.5 (lower threshold for preliminary filtering) (novelty_checker.py:299)
      → _compute_similarity() / _compute_hypothesis_similarity() (novelty_checker.py:315/360)
        — SPECTER embeddings + cosine similarity (or Jaccard fallback) (novelty_checker.py:346-354)
      — Scoring: >= 0.95 similarity: score = 0.0 (duplicate); >= threshold: linear decay, capped 0.5; < threshold: 1.0 - (similarity * 0.5) (novelty_checker.py:120-130)
      — Returns NoveltyReport. Also mutates hypothesis.novelty_score in place (novelty_checker.py:168)

    Step 6: _store_hypothesis(hyp) loop (hypothesis_generator.py:463)
      → get_session() (db/__init__.py:108) — context manager, auto-commits on success, auto-rollbacks on exception (db/__init__.py:133-135)
      → session.add(DBHypothesis) + session.commit() (hypothesis_generator.py:491-492)
        → [SIDE EFFECT: DB write -- hypothesis INSERT to "hypotheses" table]
      — DB model: kosmos/db/models.py:75 table "hypotheses" with columns: id, research_question, statement, rationale, domain, status, novelty_score, testability_score, confidence_score, related_papers (JSON), created_at, updated_at

  — Back in director after hypothesis generation:
  → research_plan.add_hypothesis(hyp_id) (research_director.py:1429)
  → _persist_hypothesis_to_graph(hyp_id) (research_director.py:1433)
    → [SIDE EFFECT: Neo4j write]
  → workflow.transition_to(DESIGNING_EXPERIMENTS) (research_director.py:1444)

  — Data flow: research_question (str) → domain (str, via LLM) → papers (List[PaperMetadata], via 3 APIs) → hypotheses (List[Hypothesis], via LLM + JSON parse) → validated_hypotheses (filtered by length checks) → novel_hypotheses (filtered by novelty score via embeddings/DB) → stored in DB → HypothesisGenerationResponse (Pydantic) → AgentMessage (serialized dict)

  ✗ on failure: Falls back to "general" domain on domain detection error. Returns empty list if LLM generation totally fails. Fail-open on novelty check failure.
```

### 4. Experiment Design Pipeline

```
_handle_design_experiment_action(hypothesis_id) (kosmos/agents/research_director.py:1458)
  → ExperimentDesignerAgent(config=self.config) — lazy-init (research_director.py:1470)
  → agent.design_experiment(hypothesis_id=hyp_id, store_in_db=True) (research_director.py:1474)

    Step 1: _load_hypothesis(hypothesis_id) (experiment_designer.py:353)
      → session.query(DBHypothesis).filter_by(id=hypothesis_id) (experiment_designer.py:356)
        → [SIDE EFFECT: Database SELECT]

    Step 2: _select_experiment_type(hypothesis, preferred) (experiment_designer.py:380)
      — Priority: preferred > hypothesis.suggested_experiment_types > domain_defaults
      — [FACT] Domain defaults map ML/AI/CS → COMPUTATIONAL, stats/data_science/psych/neuro → DATA_ANALYSIS (experiment_designer.py:394-403)

    Step 3: Generate protocol (experiment_designer.py:205-218)
      — [BRANCH] If use_templates:
        → _generate_from_template(hypothesis, experiment_type, ...) (experiment_designer.py:409)
          → template_registry.find_best_template(hypothesis, experiment_type) (experiment_designer.py:418)
          → template.generate_protocol(params) (experiment_designer.py:435)
          — Falls back to LLM if no template found (experiment_designer.py:421-423)
      — [BRANCH] Else:
        → _generate_with_claude(hypothesis, experiment_type, ...) (experiment_designer.py:441)
          → llm_client.generate_structured(prompt, schema, max_tokens=8192) (experiment_designer.py:495-499)
            → [SIDE EFFECT: LLM API call]
          → _parse_claude_protocol(protocol_data, hypothesis, experiment_type) (experiment_designer.py:510)
            — [FACT] If LLM returns empty steps, generates 3 default steps (experiment_designer.py:568-586)
            — [FACT] If LLM returns empty variables, generates 2 default variables (experiment_designer.py:589-601)
            — [FACT] Coerces variable values: strings → None, scalars → [scalar] (experiment_designer.py:547-555)

    Step 4: LLM enhancement (experiment_designer.py:221-222)
      — [BRANCH] If use_llm_enhancement AND use_templates:
        → _enhance_protocol_with_llm(protocol, hypothesis) (experiment_designer.py:681)
          → llm_client.generate(prompt, max_tokens=1000) (experiment_designer.py:711)
            → [SIDE EFFECT: LLM API call]
          — [FACT] Enhancement response is NOT parsed or applied. Method logs "LLM enhancements applied" but returns protocol unchanged (experiment_designer.py:714-717)

    Step 4b: Power analysis (experiment_designer.py:225-260)
      → PowerAnalyzer.ttest_sample_size() / correlation_sample_size() / anova_sample_size()
      — Updates protocol.sample_size if power analysis yields higher N
      — [FACT] Falls back silently on ImportError (experiment_designer.py:259-260)

    Step 5: Validate protocol (experiment_designer.py:263)
      → _validate_protocol(protocol) (experiment_designer.py:720)
        → ExperimentValidator.validate(protocol) (experiment_designer.py:729)
          — [FACT] Falls back to inline validation if ExperimentValidator fails (experiment_designer.py:737-739)
        — Inline checks: control group, sample size >= 10, independent/dependent vars, statistical tests, >= 3 steps, duration estimate (experiment_designer.py:741-777)

    Step 6: Calculate metrics (experiment_designer.py:266-268)
      → _calculate_rigor_score() — 0.0-1.0 (experiment_designer.py:779)
      → _calculate_completeness_score() — 0/10 checklist (experiment_designer.py:807)
      → _assess_feasibility() — "High"/"Medium"/"Low" (experiment_designer.py:836)

    Step 7: _store_protocol(protocol, hypothesis) (experiment_designer.py:885)
      → session.add(DBExperiment(...)) + session.commit() (experiment_designer.py:896-903)
        → [SIDE EFFECT: Database INSERT]
      — [FACT] Stores full protocol JSON blob in protocol column (experiment_designer.py:897)
      — [FACT] Gracefully handles "Database not initialized" and schema mismatch (experiment_designer.py:909-921)

  — Back in director:
  → research_plan.add_experiment(protocol_id) (research_director.py:1492)
  → _persist_protocol_to_graph(protocol_id, hypothesis_id) (research_director.py:1496)
    → [SIDE EFFECT: Neo4j write]
  → workflow.transition_to(EXECUTING) (research_director.py:1507)

  ✗ on failure: Sets status = ERROR, returns AgentMessage(type=ERROR) (experiment_designer.py:151-158). Finally block resets to IDLE (experiment_designer.py:162).
```

### 5. Code Execution Pipeline (exec/sandbox)

```
_handle_execute_experiment_action(protocol_id) (kosmos/agents/research_director.py:1521)
  — Lazy-initializes (research_director.py:1537-1543):
    ExperimentCodeGenerator(use_templates=True, use_llm=True)
    CodeExecutor(max_retries=3)
    DataProvider(default_data_dir=self.data_path)

  Step 1: Load protocol from DB (research_director.py:1551-1561)
    → get_experiment(session, protocol_id) (research_director.py:1552)
    → ExperimentProtocol.model_validate(protocol_data) (research_director.py:1559)

  Step 2: Code generation
    → code_generator.generate(protocol) (research_director.py:1564)
      → _match_template(protocol) (code_generator.py:835) — tries 5 template types in priority order:
        [FACT] (code_generator.py:787-793):
          1. TTestComparisonCodeTemplate — matches DATA_ANALYSIS + t_test in statistical_tests
          2. CorrelationAnalysisCodeTemplate — matches DATA_ANALYSIS + correlation/regression
          3. LogLogScalingCodeTemplate — matches keywords: scaling, power law, log-log
          4. MLExperimentCodeTemplate — matches COMPUTATIONAL + ML keywords
          5. GenericComputationalCodeTemplate — catch-all for COMPUTATIONAL or DATA_ANALYSIS

      — [BRANCH] Template matched:
        → template.generate(protocol) (code_generator.py:71 for TTest)
          [FACT] All templates generate synthetic data fallback if data_path not available (code_generator.py:112-129)
          [FACT] All templates import DataAnalyzer from kosmos.execution.data_analysis (code_generator.py:107)
          [FACT] All templates set results = result at end for executor extraction (code_generator.py:187)
          [FACT] All templates include assumption checks (normality via Shapiro, variance via Levene) (code_generator.py:135-144)
        — [BRANCH] If llm_enhance_templates enabled:
          → _enhance_with_llm(code, protocol) (code_generator.py:926)
            → llm_client.generate(prompt) (code_generator.py:947)
              → [SIDE EFFECT: LLM API call]
            → _extract_code_from_response(response) (code_generator.py:907)

      — [BRANCH] No template AND use_llm:
        → _generate_with_llm(protocol) (code_generator.py:842)
          → _create_code_generation_prompt(protocol) (code_generator.py:858)
          → llm_client.generate(prompt) (code_generator.py:847)
            → [SIDE EFFECT: LLM API call]
          → _extract_code_from_response(response) (code_generator.py:907)

      — [BRANCH] Both template and LLM failed:
        → _generate_basic_template(protocol) (code_generator.py:954)
          — Minimal fallback: pd.read_csv(data_path) + df.describe()
          — [FACT] Does NOT include synthetic data generation, will crash if data_path not set (code_generator.py:964)

      — ALWAYS: _validate_syntax(code) (code_generator.py:982)
        [FACT] Uses ast.parse(code) for syntax validation (code_generator.py:984). Raises ValueError on SyntaxError.

  Step 3: Code execution
    — [BRANCH] data_path set:
      → code_executor.execute_with_data(code, data_path, retry_on_error=True) (research_director.py:1568-1569)
        [FACT] Both prepends data_path as code AND passes it as local_vars. Double injection for template compatibility (executor.py:655-658)
    — [BRANCH] no data_path:
      → code_executor.execute(code, retry_on_error=True) (research_director.py:1572)

    → CodeExecutor.execute() (executor.py:237)
      — Language auto-detection (executor.py:261-266). Default: 'python'
      — [BRANCH] R code → R executor via subprocess (executor.py:378-396)

      Python execution retry loop (max 3 attempts):
        → _execute_once(code, local_vars) (executor.py:282)

          — [BRANCH] self.use_sandbox:
            → _execute_in_sandbox(code, local_vars) (executor.py:555)
              → DockerSandbox.execute(code, data_files) (sandbox.py:163)
                → tempfile.mkdtemp(prefix="kosmos_sandbox_") (sandbox.py:181)
                → Write code to temp_dir/code/experiment.py (sandbox.py:185-186)
                → Copy data files to temp_dir/data/ (sandbox.py:190-196)
                → _run_container(temp_dir, environment) (sandbox.py:203)
                  — Container config (sandbox.py:259-277):
                    [FACT] image: kosmos-sandbox:latest (sandbox.py:79)
                    [FACT] command: python3 /workspace/code/experiment.py (sandbox.py:261)
                    [FACT] mem_limit: 2g default (sandbox.py:83)
                    [FACT] cpu_limit: 2.0 cores default (sandbox.py:82)
                    [FACT] network_disabled: True (sandbox.py:92)
                    [FACT] read_only: True (sandbox.py:93)
                    [FACT] security_opt: no-new-privileges (sandbox.py:274)
                    [FACT] cap_drop: ALL (sandbox.py:275)
                    [FACT] tmpfs: /tmp (100m), /home/sandbox/.local (50m) (sandbox.py:269-272)
                  → self.client.containers.create(**container_config) (sandbox.py:285)
                    → [SIDE EFFECT: Docker container creation + execution]
                  → container.start() (sandbox.py:299)
                  → container.wait(timeout=300) (sandbox.py:304)
                    — On timeout: container.stop(timeout=5) then container.kill() (sandbox.py:313-317)
                  → container.logs() (sandbox.py:331-332)
                  → _extract_return_value(stdout) (sandbox.py:352)
                    [FACT] Parses stdout for "RESULT:" prefix lines (sandbox.py:442-448)
                    [FACT] Generated code does NOT emit RESULT: prefix -- stores in local var 'results'. Sandbox path returns None for return_value. Non-sandbox path extracts via exec_locals.get('results') which works correctly.
                  FINALLY: shutil.rmtree(temp_dir) (sandbox.py:213), container.remove(force=True) (sandbox.py:397)

          — [BRANCH] not self.use_sandbox (restricted builtins):
            → _prepare_globals() (executor.py:589)
              [FACT] Creates restricted builtins from SAFE_BUILTINS (executor.py:594)
              [FACT] Installs restricted __import__ allowing only _ALLOWED_MODULES: numpy, pandas, scipy, sklearn, matplotlib, seaborn, statsmodels, math, statistics, xarray, netCDF4, h5py, zarr, dask + stdlib (executor.py:86-94)
            → _exec_with_timeout(code, exec_globals, exec_locals) (executor.py:600)
              — [BRANCH] Unix: signal.SIGALRM for timeout (executor.py:608-620)
              — [BRANCH] Windows: ThreadPoolExecutor with timeout (executor.py:622-630)
              → exec(code, exec_globals, exec_locals) (executor.py:617)
                → [SIDE EFFECT: arbitrary Python code execution]
              — Default timeout: 300 seconds (executor.py:40)
            — Captures stdout/stderr via redirect_stdout/redirect_stderr (executor.py:496-504)
            — Extracts return value: exec_locals.get('results', exec_locals.get('result')) (executor.py:516)

        — [BRANCH] If result.success AND test_determinism:
          → ReproducibilityManager().test_determinism() — re-runs 2x comparing outputs (executor.py:296-299)
          RETURN result

        — [BRANCH] If failed AND retry_on_error:
          → RetryStrategy.modify_code_for_retry(code, error, ...) (executor.py:317-324)
            — [BRANCH] LLM repair first (if client available, attempt <= 2) (executor.py:779-788)
            — Then pattern-based fixes for 11 error types (executor.py:791-825):
              KeyError, FileNotFoundError, NameError, TypeError, IndexError, AttributeError, ValueError, ZeroDivisionError, ImportError, PermissionError, MemoryError
            — [FACT] FileNotFoundError returns None (terminal, no fix) (executor.py:879-906)
            — [FACT] Most pattern fixes wrap code in try/except, producing results = {'error': ..., 'status': 'failed'} (executor.py:869-1008)
            — NameError fix: auto-inserts common imports from COMMON_IMPORTS dict (executor.py:908-916)
          → time.sleep(delay) with exponential backoff (executor.py:333-335)

        — If all retries exhausted:
          RETURN ExecutionResult(success=False, error_type="MaxRetriesExceeded") (executor.py:372-376)

  Step 4: Store result in DB (research_director.py:1621-1630)
    → _json_safe(return_value) (research_director.py:1595-1613)
      [FACT] Defined as nested function inside _handle_execute_experiment_action(). Recreated on every call.
      — Recursively converts numpy arrays → list, np.integer → int, np.floating → float
      — Falls back to str() for unknown types. sklearn models, matplotlib figures → string representations.
    → create_result(session, id=result_id, experiment_id=protocol_id, data=safe_data, ...) (db/operations.py:339)
      → session.add(Result) → session.commit() (db/operations.py:366-367)
        → [SIDE EFFECT: DB INSERT]

  — Back in director:
  → research_plan.add_result(result_id) (research_director.py:1641)
  → research_plan.mark_experiment_complete(protocol_id) (research_director.py:1642)
  → _persist_result_to_graph(result_id, protocol_id, hypothesis_id) (research_director.py:1646)
    → [SIDE EFFECT: Neo4j write]
  → workflow.transition_to(ANALYZING) (research_director.py:1652)

  ✗ on failure: _handle_error_with_recovery(error_source="CodeExecutor", ...) (research_director.py:1659-1663). Up to 3 retries with exponential backoff at executor level. FileNotFoundError is terminal (no retry fix).
```

### 6. Result Analysis Pipeline

```
_handle_analyze_result_action(result_id) (kosmos/agents/research_director.py:1666)
  → DataAnalystAgent(config=self.config) — lazy-init (research_director.py:1681)
  → DB load: get_result(session, result_id, with_experiment=True) (research_director.py:1691)
  → Construct Pydantic ExperimentResult and Hypothesis from DB rows (research_director.py:1704-1734)
    — Data transformation: DB rows → Pydantic models. Manual reconstruction from SQLAlchemy attributes.

  → analyst.interpret_results(result, hypothesis) (research_director.py:1737)
    → _extract_result_summary(result) (data_analyst.py:381)
      — Extracts: experiment_id, status, primary_test, primary_p_value, primary_effect_size, supports_hypothesis (data_analyst.py:383-390)
      — Adds statistical_tests details: test_name, statistic, p_value, effect_size, effect_size_type, significance_label, sample_size (data_analyst.py:394-403)
      — Adds top 5 variable results: name, mean, median, std, min, max, n_samples (data_analyst.py:407-417)

    → _build_interpretation_prompt(result_summary, hypothesis, literature_context) (data_analyst.py:421)
      — Includes hypothesis statement if provided (data_analyst.py:432-438)
      — Includes result summary with statistical tests (data_analyst.py:441-460)
      — Includes literature context truncated to 1000 chars (data_analyst.py:463-467)
      — Requests JSON response with 9 fields (data_analyst.py:470-503)

    → llm_client.generate(prompt, system=..., max_tokens=2000, temperature=0.3) (data_analyst.py:355-362)
      → [SIDE EFFECT: LLM API call to Claude]
      [FACT] Temperature 0.3 for focused analysis. System prompt: "expert scientific data analyst" (data_analyst.py:357-361)

    → _parse_interpretation_response(response_text, experiment_id, result) (data_analyst.py:508)
      — Extracts JSON by finding first '{' and last '}' (data_analyst.py:517-519)
      — json.loads() to parse (data_analyst.py:521)
      — [BRANCH] If anomaly_detection_enabled:
        → detect_anomalies(result) (data_analyst.py:524)
          — Checks: significant p-value + tiny effect size (data_analyst.py:594-601)
          — Checks: large effect size + non-significant p-value (data_analyst.py:604-611)
          — Checks: p-value exactly 0.0 or 1.0 (data_analyst.py:614-623)
          — Checks: inconsistent statistical tests (data_analyst.py:626-636)
          — Checks: high coefficient of variation (data_analyst.py:639-647)

    — [BRANCH] On json.JSONDecodeError:
      → _create_fallback_interpretation(result) (data_analyst.py:548)
        — Uses raw result fields (p_value, effect_size) directly (data_analyst.py:554-558)
        — confidence=0.5, assessment="Automated fallback" (data_analyst.py:553, 568)

    → interpretation_history.append(interpretation) (data_analyst.py:371) — for cross-result pattern detection

  — Back in director:
  → research_plan.mark_supported(hyp_id) OR mark_rejected(hyp_id) OR mark_tested(hyp_id) (research_director.py:1760-1767)
  → _add_support_relationship(result_id, hypothesis_id, supports, confidence, p_value, effect_size) (research_director.py:1771)
    → [SIDE EFFECT: Neo4j write — SUPPORTS/REFUTES edge]
  → workflow.transition_to(REFINING) (research_director.py:1782)

  ✗ on failure: _handle_error_with_recovery(error_source="DataAnalystAgent", ...) (research_director.py:1789-1793). JSON parse failure → fallback interpretation with confidence=0.5.
```

### 7. Hypothesis Refinement Pipeline

```
_handle_refine_hypothesis_action(hypothesis_id) (kosmos/agents/research_director.py:1796)
  → HypothesisRefiner(config=self.config) — lazy-init (research_director.py:1817)
  → DB load: get_hypothesis(session, hypothesis_id, with_experiments=True) (research_director.py:1826)
  → Get results_history for all experiments under this hypothesis (research_director.py:1843-1872)

  → refiner.evaluate_hypothesis_status(hypothesis, latest_result, results_history) (research_director.py:1886)
    → _count_consecutive_failures(results) — rule-based check (refiner.py:135)
    → _bayesian_confidence_update(hypothesis, results) — Bayesian posterior (refiner.py:145)
    — Decision logic (refiner.py:135-167):
      [FACT] consecutive failures → RETIRE; low posterior → RETIRE; rejected but not enough → REFINE; inconclusive → SPAWN_VARIANT; supported 2+ times → SPAWN_VARIANT

  — [BRANCH] on RetirementDecision:
    RETIRE: → refiner.retire_hypothesis(hyp) — marks retired (research_director.py:1894-1898)
    REFINE: → refiner.refine_hypothesis(hyp, result)
      → [SIDE EFFECT: db_create_hypothesis() → session.commit()] (research_director.py:1900-1918)
    SPAWN_VARIANT: → refiner.spawn_variant(hyp, result, num_variants=2)
      → [SIDE EFFECT: db_create_hypothesis() per variant → session.commit()] (research_director.py:1921-1942)
    CONTINUE_TESTING: → no action

  → research_plan.add_hypothesis(hyp_id) — for each refined/variant hypothesis (research_director.py:1954-1955)
  → _persist_hypothesis_to_graph(hyp_id) (research_director.py:1958-1959)
    → [SIDE EFFECT: Neo4j write]
  → research_plan.increment_iteration() (research_director.py:2704) — marks end of one research cycle
    [FACT] Iteration increment happens ONLY in REFINE_HYPOTHESIS handler. If loop skips refinement (e.g., goes directly to CONVERGE), iterations may not increment. Convergence action has its own increment path at research_director.py:1387 (research_director.py:2704)
  → _actions_this_iteration = 0 (research_director.py:2706) — resets loop guard

  ✗ on failure: Error recovery via director's standard error handling. Failure thresholds and confidence retirement thresholds are configurable (refiner.py:135-142, 145-152).
```

### 8. Convergence Pipeline

```
_handle_convergence_action() (kosmos/agents/research_director.py:1334)
  → _apply_multiple_comparison_correction() (research_director.py:1343) — Benjamini-Hochberg FDR correction on p-values
  → _check_convergence_direct() (research_director.py:1221)
    — Loads hypotheses from DB (research_director.py:1237-1238)
    [FACT] Passes empty results=[] to detector. results list is never populated from DB. Detector relies on research_plan counts instead (research_director.py:1237-1238, 1267-1271)
    → convergence_detector.check_convergence(research_plan, hypotheses, results, total_cost) (research_director.py:1267)
      → _update_metrics(plan, hypotheses, results) (convergence.py:243)
      → For each mandatory_criterion: _check_criterion() (convergence.py:246-251)
      → For each optional_criterion: _check_criterion() (convergence.py:256-260)
      → check_iteration_limit | check_hypothesis_exhaustion | check_novelty_decline | check_diminishing_returns
      [FACT] Mandatory criteria checked first (except iteration_limit checked last). Optional scientific criteria between (convergence.py:246-267)
      → Returns StoppingDecision(should_stop, reason)

  — [BRANCH] If converged (should_stop=True):
    → research_plan.has_converged = True (research_director.py:1358)
    → wm.add_annotation(question_entity_id, convergence_annotation) (research_director.py:1368)
      → [SIDE EFFECT: Neo4j write]
    → workflow.transition_to(CONVERGED) (research_director.py:1376)
    → self.stop() (research_director.py:1381) — stops the director agent

  — [BRANCH] If not converged:
    → research_plan.increment_iteration() (research_director.py:1387) — continue
  → rollout_tracker.increment("literature") (research_director.py:1350)
    [FACT] Misleadingly increments "literature" rollout counter even though no literature search is performed in convergence. Inflates reported literature rollout count (research_director.py:1350)

  ✗ on failure: If convergence check fails, loop continues with next iteration.
```

### 9. Results Assembly and Display

```
run_with_progress_async() — post-loop (run.py:403)
  → director.get_research_status() (run.py:400) (research_director.py:2926)
  → get_session() → get_hypothesis(), get_experiment() — fetch from DB (run.py:417-435)
  → Build results dict with metrics (run.py:437-458)

run_research() — post-async (run.py:195-211)
  → ResultsViewer.display_research_overview(results) (run.py:196)
  → ResultsViewer.display_hypotheses_table(results["hypotheses"]) (run.py:197)
  → ResultsViewer.display_experiments_table(results["experiments"]) (run.py:198)
  → ResultsViewer.display_metrics_summary(results["metrics"]) (run.py:200)
  — [BRANCH] If --output:
    → viewer.export_to_json(results, output) OR export_to_markdown() (run.py:205-209)
      → [SIDE EFFECT: file write]

  ✗ on failure: Display proceeds with whatever data is available. Missing metrics/experiments shown as empty tables.
```

### 10. Scientific Evaluation Entry (7-Phase Pipeline)

```
__main__ block (scientific_evaluation.py:1454)
  → argparse setup (scientific_evaluation.py:1457-1480)
  → asyncio.run(main(...)) (scientific_evaluation.py:1482)

main() (scientific_evaluation.py:1342)
  → [SIDE EFFECT: LOG FILE] logging.basicConfig creates evaluation/logs/evaluation_<timestamp>.log (scientific_evaluation.py:41-50)
  → EvaluationReport() — empty report container (scientific_evaluation.py:1360)

  Phase 1: run_phase1_preflight() (scientific_evaluation.py:1364)
    → get_config() — loads Pydantic settings from env
    → get_client(reset=True) — creates LLM client
      → client.generate("Say hello...") (scientific_evaluation.py:176)
        → [SIDE EFFECT: LLM API call]
    → init_from_config() (db/__init__.py:140)
      → first_time_setup() (kosmos/utils/setup.py) — [SIDE EFFECT: may create .env file, run migrations]
      → init_database() (db/__init__.py:26) — [SIDE EFFECT: creates SQLite DB + tables via Base.metadata.create_all]
    → get_session() — validates DB connection (scientific_evaluation.py:199)
    → client.generate(...) x2 — type compatibility checks (scientific_evaluation.py:212, 223)
      → [SIDE EFFECT: LLM API calls]
    — [BRANCH] If p1.status == "FAIL" → early exit (scientific_evaluation.py:1369-1381):
      → generate_report(report) (scientific_evaluation.py:1373)
      → [SIDE EFFECT: report_path.write_text()] (scientific_evaluation.py:1379)
      [FACT] Early exit still writes a report with only Phase 1 results. Partial report file exists even on total failure (scientific_evaluation.py:1373-1380)

  Phase 2: run_phase2_smoke_test() (scientific_evaluation.py:1385)
    → _reset_eval_state() (scientific_evaluation.py:262) — ISOLATION between phases:
      → reset_database() (db/__init__.py:191) — [SIDE EFFECT: drops and recreates ALL DB tables]
        [FACT] Base.metadata.drop_all(). If evaluation DB is shared with production data, this destroys everything. No separate database created (db/__init__.py:200-201)
      → reset_cache_manager() (cache_manager.py:515) — clears global cache singleton
      → reset_claude_cache() (claude_cache.py:401) — clears LLM prompt cache
      → get_registry().clear() (registry.py) — clears agent registry
      → reset_world_model() (factory.py:158) — clears knowledge graph singleton
    → ResearchDirectorAgent setup (same as CLI path)
    → LOOP: max 20 actions (scientific_evaluation.py:328-348)
      [FACT] Each action step has asyncio.wait_for(timeout=120) (scientific_evaluation.py:338-341)
      → director.decide_next_action() → director._execute_next_action(action)
        → dispatches to same handlers as CLI path (generate/design/execute/analyze/refine/converge)

  Phase 3: run_phase3_multi_iteration() (scientific_evaluation.py:1392)
    → _reset_eval_state() — same isolation as Phase 2
    → Same ResearchDirectorAgent setup but max_iterations=3
    → LOOP: max(60, max_iterations*10) actions (scientific_evaluation.py:474)
      — Snapshot capture at iteration boundaries (scientific_evaluation.py:500-504)
      [FACT] Worst-case wall time: 120 * 60 = 7200 seconds (2 hours) for Phase 3 alone. No aggregate timeout for entire evaluation (scientific_evaluation.py:338-341, 485-488)

  Phase 4: run_phase4_dataset_test() (scientific_evaluation.py:1399)
    → _reset_eval_state()
    — [BRANCH] data_path is None → FAIL immediately (scientific_evaluation.py:580-585)
      [FACT] data_path required for Phase 4, no default dataset. Result is "FAIL" not "SKIP", counts against overall pass rate (scientific_evaluation.py:580-585)
    — [BRANCH] data_path.exists() False → SKIP (scientific_evaluation.py:590-594)
    → pd.read_csv(data_path) — validates dataset readable (scientific_evaluation.py:601)
    → DataProvider().get_data(file_path=str(data_path)) — CSV/TSV/parquet/JSON/JSONL extension dispatch (data_provider.py:310)
    → Same ResearchDirectorAgent loop (10 steps max) with data_path in flat_config

  Phase 5: assess_output_quality(p2, p3) (scientific_evaluation.py:1406)
    — Pure analysis, no side effects. Reads from PhaseResult.details.
    [FACT] Scores hypothesis quality via keyword heuristics: checks for "specific", "measurable", "mechanism" in first 500 chars of plan (scientific_evaluation.py:741-747). Fragile -- plan could be high quality without these keywords.

  Phase 6: run_phase6_rigor_scorecard() (scientific_evaluation.py:1413)
    — Pure analysis with import-time checks, no LLM calls.
    — Checks 8 rigor features via hasattr() and inspect.getsource():
      1. NoveltyChecker.check_novelty (hypothesis/novelty_checker.py:27)
      2. PowerAnalyzer methods (experiments/statistical_power.py)
      3. Shapiro-Wilk + Levene in code_generator source
      4. SyntheticDataGenerator.randomize_effect_size
      5. DataProvider multi-format support
      6. ConvergenceDetector.check_convergence (core/convergence.py:172)
      7. ReproducibilityManager.set_seed (safety/reproducibility.py)
      8. Metrics.enforce_budget (core/metrics.py)
    [FACT] Checks source code strings, not runtime behavior. Verifies code template contains the word "shapiro", not that checks actually execute at runtime (scientific_evaluation.py:831-833, 870-875)

  Phase 7: run_phase7_paper_compliance(p2, p3, p4, p6) (scientific_evaluation.py:1420)
    — Pure analysis. Evaluates 15 claims from arXiv:2511.02824v2.
    — Status per claim: PASS, PARTIAL, FAIL, BLOCKER.
    — Attempts imports to verify module existence (ResultSummarizer, DockerSandbox, etc.)

  → generate_report(report) (scientific_evaluation.py:1220)
    — Builds Markdown string from all phase results (scientific_evaluation.py:1220-1335)
  → [TERMINAL SIDE EFFECTS] (scientific_evaluation.py:1427-1451):
    → report_path.write_text(report_text) (scientific_evaluation.py:1432)
    → print() summary to stdout (scientific_evaluation.py:1435-1450)
    → return 0 → sys.exit(0) (scientific_evaluation.py:1489)
    [FACT] main() always returns 0 unless Phase 1 fails (returns 1). Phases 2-7 can all FAIL and exit code is still 0 (scientific_evaluation.py:1451)

  ✗ on failure: Phase 1 failure causes early exit with partial report (exit code 1). All other phase failures produce "FAIL" status but do not halt execution or change exit code.
```

### 11. Persona Evaluation Orchestration

```
main() (run_persona_eval.py:258)
  → argparse.parse_args() — parse --persona, --tier, --dry-run, --version
  → load_persona(args.persona) (run_persona_eval.py:36)
    → yaml.safe_load(file) — loads YAML from definitions/{name}.yaml
    → validates required fields: "persona", "research", "setup"
    — [ERROR PATH] sys.exit(1) if PyYAML missing, file not found, or missing field
  → get_next_version(args.persona) (run_persona_eval.py:64)
    → scans runs/{persona_name}/v* directories
    — Extracts highest version from "v{NNN}_{date}" format
    [FACT] Splits on '_' and takes index 0. If directory name lacks '_' (e.g., plain v001), IndexError caught and directory silently skipped (run_persona_eval.py:79)
  → create_run_directory(persona_name, version) (run_persona_eval.py:105)
    → [SIDE EFFECT: mkdir] creates runs/{persona}/v{NNN}_{YYYYMMDD}/tier1/artifacts/, tier2/, tier3/ (run_persona_eval.py:112-114)
  → write_meta_json(run_dir, persona, version) (run_persona_eval.py:119)
    → get_git_sha() — subprocess: git rev-parse HEAD (run_persona_eval.py:87)
    → compute_config_hash(persona) — sha256 of json-serialized persona (run_persona_eval.py:99)
    → [SIDE EFFECT: file.write] meta.json with persona_id, model, git sha, config_hash (run_persona_eval.py:142)

  → run_tier1(persona_name, persona, run_dir, dry_run) (run_persona_eval.py:148)
    — [BRANCH] If dry_run → prints commands, returns True early (run_persona_eval.py:178-181)
    → [SIDE EFFECT: file.unlink] deletes PROJECT_ROOT/kosmos.db for clean eval (run_persona_eval.py:187)
    → [SIDE EFFECT: shutil.rmtree] deletes PROJECT_ROOT/.kosmos_cache (run_persona_eval.py:190)
      [FACT] Destructively deletes kosmos.db and .kosmos_cache before every run. Destroys any prior application state on the machine (run_persona_eval.py:186-190)
    → [SUBPROCESS] python scientific_evaluation.py --output-dir {run_dir}/tier1 \
          --research-question {question} --domain {domain} --data-path {dataset} \
          --max-iterations {max_iterations} (run_persona_eval.py:196)
      → scientific_evaluation.main() (see Path 10 above)
    → [SUBPROCESS] python run_phase2_tests.py --output-dir {run_dir}/tier1/artifacts/phase2_components \
          --research-question {question} --domain {domain} --data-path {dataset} (run_persona_eval.py:219)
      [FACT] run_phase2_tests.py hardcodes os.chdir("/mnt/c/python/Kosmos") at module level (run_phase2_tests.py:16). Machine-specific absolute path that fails on any other machine.
      → test_component("2.1_hypothesis_generation", ...) — HypothesisGeneratorAgent
      → test_component("2.2_literature_search", ...) — UnifiedLiteratureSearch
      → test_component("2.3_experiment_design", ...) — ExperimentDesignerAgent
      → test_component("2.4_code_execution", ...) — TTestComparisonCodeTemplate + CodeExecutor
      → test_component("2.5_data_analysis", ...) — DataAnalystAgent
      → test_component("2.6_convergence_detection", ...) — ConvergenceDetector
      → [SIDE EFFECT: file.write] per-component JSON + all_components.json (run_phase2_tests.py:563-569)
    → [SIDE EFFECT: shutil.copy2] copies latest eval log to run_dir/tier1/eval.log (run_persona_eval.py:228)

  → parse_tier1_results(run_dir) (run_persona_eval.py:233)
    — Reads EVALUATION_REPORT.md
    — Regex extracts checks_passed/total and duration
    [FACT] Lossy round-trip: write_meta_json writes structured JSON, then parse_tier1_results re-extracts stats from markdown via regex, not from original PhaseResult objects. If markdown format changes, parsing breaks silently (returns 0/0/0.0) (run_persona_eval.py:244-249)
  → write_meta_json(run_dir, ..., tier1_completed=success, checks_passed, ...) (run_persona_eval.py:318)
    → [SIDE EFFECT: file.write] overwrites meta.json with final results (run_persona_eval.py:142)
  → Prints next steps for Tier 2 (technical report) and Tier 3 (narrative)
  → Prints regression comparison command if prior versions exist

  — Data transformation: YAML dict → CLI args (run_persona_eval.py:156-174); CLI args → flat_config dict (scientific_evaluation.py:272-287); PhaseResult → EvaluationReport → Markdown (scientific_evaluation.py:1220-1335); Markdown → regex → (checks_passed, checks_total, duration) (run_persona_eval.py:233-255)

  ✗ on failure: sys.exit(1) if persona file missing or invalid. Subprocess failures captured via subprocess.run() returncode. Missing data_path prints WARNING but continues without --data-path flag; Phase 4 then FAILs.
```

### 12. Run Comparison (Regression Detection)

```
main() (compare_runs.py:248)
  → argparse.parse_args() — parse --persona, --v1, --v2, --output
  → compare_runs(args.persona, args.v1, args.v2) (compare_runs.py:148)
    → validates run directories exist under runs/{persona}/{v1|v2}
      — [ERROR PATH] sys.exit(1) if either directory missing (compare_runs.py:154-157)
    → load_meta(v1_dir) (compare_runs.py:26)
      — reads meta.json from run directory
      — [ERROR PATH] sys.exit(1) if meta.json missing (compare_runs.py:29-30)
    → load_meta(v2_dir) — same for v2
    → parse_evaluation_report(v1_dir) (compare_runs.py:36)
      — reads tier1/EVALUATION_REPORT.md
      — regex extracts:
        summary (checks_passed/total, duration, quality_score, rigor_score)
        individual check rows (name → PASS/FAIL) via r"\|\s*(\w+)\s*\|\s*(PASS|FAIL)\s*\|([^|]*)\|"
        quality scores (dimension → N/10) via r"\|\s*(phase\d+_\w+)\s*\|\s*(\d+)/10\s*\|"
        rigor scores (feature → N/10) — from "Scientific Rigor Scorecard" section only
        paper claims (claim_num → STATUS) via r"\|\s*(\d+)\s*\|\s*([^|]+)\|\s*(PASS|PARTIAL|FAIL|BLOCKER)\s*\|"
      — [BRANCH] Missing report → returns empty dicts for all categories. No error raised (compare_runs.py:38-40)
      — [BRANCH] Missing regex matches → multiple fallback patterns. If neither matches, summary stays empty (compare_runs.py:51-57)
      — [FACT] Check regex requires single-word names (\w+). Hyphens, spaces, dots would not match. Current names use underscores so this works (compare_runs.py:66-67)
      — [FACT] Quality score regex requires dimension names to start with phase\d+_. Non-conforming names silently excluded (compare_runs.py:75)
      — [FACT] Rigor section scoped: only text after "Scientific Rigor Scorecard" heading and before next ## heading. phase prefix skipped to avoid double-counting (compare_runs.py:92-105)
    → parse_evaluation_report(v2_dir) — same for v2
    → Summary comparison: for each metric key, builds {v1, v2, delta} triples
    → compute_delta(v1_val, v2_val) (compare_runs.py:135) — formats "+N" / "0" / "-N"
      [FACT] Returns string "N/A" when either value is None (compare_runs.py:137-138). No type annotation; consumers treat it as string alongside "+3" or "-1"
    → Check changes: classifies all checks into improved/regressed/unchanged lists (compare_runs.py:179-194)
    → Quality score changes: per-dimension {v1, v2, delta} (compare_runs.py:197-206)
    → Rigor score changes: per-feature {v1, v2, delta} (compare_runs.py:209-217)
    → Paper claim changes: only changed claims recorded (compare_runs.py:220-226)
      [FACT] Claims keyed by integer claim number. If markdown changes claim numbering between versions, diff shows false changes (compare_runs.py:118-119)

  — [BRANCH] If --output: uses provided path; else: creates runs/{persona}/regression/ directory
  → [SIDE EFFECT: mkdir] output_path.parent.mkdir(parents=True, exist_ok=True) (compare_runs.py:280)
  → [SIDE EFFECT: file.write] json.dump(comparison, f, indent=2) (compare_runs.py:281-282)
  → Prints summary table to stdout: metric, baseline, current, delta (compare_runs.py:288-294)
  → Prints improved/regressed check names and unchanged count (compare_runs.py:296-301)

  [FACT] Entirely self-contained -- zero imports from Kosmos application code. Only reads files (meta.json, EVALUATION_REPORT.md) and writes JSON. No database, no LLM, no network calls.
  [FACT] Regression directory contains actual comparison outputs (v001_20260207_vs_v002_20260207.json, etc.) confirming active use.

  ✗ on failure: sys.exit(1) if run directories or meta.json missing. Missing evaluation reports produce empty comparison (all unchanged), no error.
```

### 13. Literature Analysis (Multi-Branch)

```
LiteratureAnalyzerAgent.execute(task: Dict) (kosmos/agents/literature_analyzer.py:153)
  — Sets status = WORKING (line 180)
  — [FACT] Different execute() signature from HypothesisGeneratorAgent: takes Dict and returns Dict, not AgentMessage→AgentMessage. BaseAgent.execute is (task: Dict) → Dict (base.py:485). Incompatible override (literature_analyzer.py:153 vs hypothesis_generator.py:91)

  __init__ (literature_analyzer.py:81) initializes up to 6 components:
    → llm_client = get_client() (literature_analyzer.py:107)
    → knowledge_graph = get_knowledge_graph() — Neo4j (conditional, fails gracefully) (literature_analyzer.py:111-116)
      [FACT] If Neo4j unavailable, sets use_knowledge_graph = False silently (literature_analyzer.py:114-116)
    → vector_db = get_vector_db() — ChromaDB (conditional) (literature_analyzer.py:119)
    → embedder = get_embedder() — SPECTER embeddings (conditional) (literature_analyzer.py:120)
    → concept_extractor = get_concept_extractor() — Claude-powered (conditional) (literature_analyzer.py:123)
    → semantic_search = SemanticLiteratureSearch() (literature_analyzer.py:125)
    → unified_search = UnifiedLiteratureSearch() (literature_analyzer.py:126)
    → [SIDE EFFECT: mkdir] .literature_analysis_cache/ directory (literature_analyzer.py:129)
    [FACT] Singleton via get_literature_analyzer(). Can be reset with reset=True (literature_analyzer.py:1050-1075)

  — Dispatches on task["task_type"] (5 branches):

  Branch "summarize_paper":
    → summarize_paper(paper) (literature_analyzer.py:231)
      → _get_cached_analysis(paper.primary_identifier) (literature_analyzer.py:1007)
        — File-based JSON cache in .literature_analysis_cache/, 24-hour TTL (literature_analyzer.py:1018-1019)
        [FACT] Stale cache entries return None (not deleted) (literature_analyzer.py:1019)
      → _validate_paper(paper) — requires title AND (abstract OR full_text) (literature_analyzer.py:768)
      → _build_summarization_prompt(paper) — title + first 5000 chars of full_text or abstract (literature_analyzer.py:876)
      → llm_client.generate_structured(prompt, schema, system, max_tokens=4096) (literature_analyzer.py:265-269)
        → [SIDE EFFECT: Anthropic API call]
      → _cache_analysis(paper_id, result.to_dict()) (literature_analyzer.py:284)
        → [SIDE EFFECT: file cache write]

  Branch "analyze_corpus":
    → analyze_corpus(papers, generate_insights) (literature_analyzer.py:658)
      → Temporal distribution: counts papers by year (literature_analyzer.py:699-702)
      → concept_extractor.extract_from_paper(paper) per paper (up to max_papers_per_analysis=50) (literature_analyzer.py:709-711)
        → [SIDE EFFECT: Claude API calls for concept extraction]
      → LLM insights: summarizes up to 20 papers (200 chars of abstract each) (literature_analyzer.py:726-738)
        → [SIDE EFFECT: Anthropic API call for corpus insights]

  Branch "citation_network":
    → analyze_citation_network(paper_id, depth, build_if_missing) (literature_analyzer.py:415)
      → knowledge_graph query for citations and citing papers (literature_analyzer.py:457-459)
        → [SIDE EFFECT: Neo4j read]
      — [BRANCH] No citations found AND build_if_missing=True:
        → _build_citation_graph_on_demand(paper_id) (literature_analyzer.py:488)
          → SemanticScholarClient.get_paper() (literature_analyzer.py:791)
            → [SIDE EFFECT: Semantic Scholar API call]
          → knowledge_graph.add_paper() + add_citation() (literature_analyzer.py:816-852)
            → [SIDE EFFECT: Neo4j graph writes]
          [FACT] References capped at 50, citations capped at 50 per paper (literature_analyzer.py:821, 838)
        → self.analyze_citation_network(paper_id, depth, build_if_missing=False) — recursive retry
          [FACT] Only 1 retry attempt via build_if_missing=False prevention of infinite loop (literature_analyzer.py:494)

  Branch "find_related":
    → find_related_papers(paper, max_results, similarity_threshold) (literature_analyzer.py:574)
      → vector_db.search_by_paper(paper, top_k) — ChromaDB vector search (literature_analyzer.py:610-611)
        → [SIDE EFFECT: ChromaDB query]
      → knowledge_graph.find_related_papers(paper_id, max_hops=2) — Neo4j traversal (literature_analyzer.py:630-634)
        → [SIDE EFFECT: Neo4j traversal]
      → Results deduplicated by paper ID and merged (literature_analyzer.py:647-656)

  Branch "extract_methodology":
    → extract_methodology(paper) (literature_analyzer.py:348)
      → concept_extractor.extract_from_paper(paper) — categorizes methods (literature_analyzer.py:377-393)
        → [SIDE EFFECT: Claude API call]
      — [BRANCH] If concept extractor found nothing:
        → llm_client.generate_structured() — LLM fallback extraction (literature_analyzer.py:398-412)
          → [SIDE EFFECT: Anthropic API call]

  On success: increments tasks_completed, returns result dict.
  On error: increments errors_encountered, returns error dict.

  ✗ on failure: Per-task error handling. Neo4j failures degrade silently. Individual task errors don't crash the agent.
```

### Terminal Side Effects Summary (All Paths)

| Side Effect | Location | Frequency per run |
|---|---|---|
| **LLM API call** (research plan) | research_director.py:2372 | 1x at start |
| **LLM API call** (hypothesis generation) | hypothesis_generator.py:378 | 1x per iteration |
| **LLM API call** (domain detection) | hypothesis_generator.py:275 | 1x per hypothesis batch |
| **LLM API call** (code generation, if no template) | code_generator.py:847 | 0-1x per experiment |
| **LLM API call** (result interpretation) | data_analyst.py:355 | 1x per result |
| **HTTP calls** (arXiv, Semantic Scholar, PubMed) | unified_search.py:147-161 | 3x per literature search |
| **DB commit** (hypothesis creation) | hypothesis_generator.py:491-492 | N per iteration (typically 3) |
| **DB commit** (protocol storage) | experiment_designer.py:902-903 | 1 per experiment |
| **DB commit** (result storage) | db/operations.py:366-367 | 1 per experiment |
| **DB commit** (refined hypothesis) | research_director.py:1906-1915 | 0-2 per refinement |
| **DB tables dropped** (eval reset) | db/__init__.py:200-201 | 1x per eval phase (2, 3, 4) |
| **exec()** (code execution) | executor.py:617 | 1 per experiment |
| **Docker sandbox** (if enabled) | executor.py:476, sandbox.py:285 | 1 per experiment (alt to exec()) |
| **Neo4j write** (entities & relationships) | research_director.py:250,1433,1496,1646,1771,1958 | Many per iteration |
| **File write** (output export) | run.py:205-209 | 0-1x at end |
| **File write** (evaluation report) | scientific_evaluation.py:1432 | 1x at eval end |
| **File delete** (kosmos.db) | run_persona_eval.py:187 | 1x per persona eval |
| **Dir delete** (.kosmos_cache) | run_persona_eval.py:190 | 1x per persona eval |
## Module Behavioral Index

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `kosmos/agents/base.py` | Defines `BaseAgent` lifecycle management, async inter-agent message passing via `AgentMessage`, state persistence, and health monitoring for all 6 agent subclasses | `pydantic`, `asyncio`, `kosmos.config.get_config` (deferred), `kosmos.agents.registry` | Sync `message_queue` list grows without bound -- memory leak in long-running agents [FACT: base.py:136-138] |
| `kosmos/core/providers/anthropic.py` | Implements the Anthropic (Claude) LLM provider with sync/async generation, streaming, structured JSON output, response caching, auto model selection (Haiku/Sonnet), and cost tracking -- supporting both real API keys and CLI mode | `anthropic` (hard), `kosmos.core.providers.base`, `kosmos.core.utils.json_parser`, `kosmos.core.claude_cache`, `kosmos.config`, `kosmos.core.pricing`, `kosmos.core.events` + `kosmos.core.event_bus` (lazy) | `generate_stream` counts text chunks as "tokens" (`total_tokens += 1`) -- token counts are wrong [FACT: anthropic.py:731-732] |
| `kosmos/literature/base_client.py` | Defines abstract `BaseLiteratureClient` and unified data types (`PaperMetadata`, `Author`, `PaperSource`) for all literature API integrations; leaf dependency with zero Kosmos imports | `abc`, `dataclasses`, `logging`, `typing`, `datetime`, `enum` (all stdlib; no external deps) | `_validate_query` says "truncating to 1000" but does NOT truncate -- returns True without modifying the query [FACT: base_client.py:248-250] |
| `kosmos/execution/code_generator.py` | Generates executable Python code from `ExperimentProtocol` objects using template matching (5 built-in templates) with LLM fallback and a minimal hardcoded last-resort template | `kosmos.models.experiment`, `kosmos.core.llm.ClaudeClient`, `kosmos.core.providers.litellm_provider.LiteLLMProvider` (lazy), `kosmos.config.get_config` (lazy); generated code imports `pandas`, `numpy`, `scipy`, `sklearn` | `random_seed=0` silently replaced with 42 due to `or 42` pattern -- zero is a valid seed but treated as falsy [FACT: code_generator.py:89] |
| `kosmos/safety/code_validator.py` | Validates generated Python code for safety (dangerous imports/calls), security (AST-based reflection detection), and ethical compliance (keyword screening), producing a `SafetyReport` that gates all code execution | `kosmos.models.safety` (SafetyReport, SafetyViolation, etc.), `kosmos.utils.compat.model_to_dict`, `kosmos.config.get_config`, `ast`, `json`, `pathlib` (stdlib) | Pattern detection `if pattern in code` matches inside comments and string literals -- `# eval()` triggers CRITICAL violation [FACT: code_validator.py:288] |
| `kosmos/core/convergence.py` | Decides when the autonomous research loop should stop by evaluating mandatory stopping criteria (iteration limit, hypothesis exhaustion) and optional scientific criteria (novelty decline, diminishing returns) | `kosmos.core.workflow.ResearchPlan`, `kosmos.models.hypothesis.Hypothesis`, `kosmos.models.result.ExperimentResult`, `kosmos.utils.compat.model_to_dict`, `pydantic` | `novelty_trend` list grows without bound -- every `check_convergence` call appends [FACT: convergence.py:562]; flat novelty score is considered "declining" (`>=` comparison) [FACT: convergence.py:424] |
| `kosmos/execution/executor.py` | Executes generated Python/R code with safety sandboxing (restricted builtins), output capture, timeout enforcement, optional profiling, determinism testing, and self-correcting retry logic | `kosmos.execution.sandbox.DockerSandbox` (optional), `kosmos.execution.r_executor.RExecutor` (optional), `kosmos.safety.code_validator.CodeValidator`, `kosmos.utils.compat.model_to_dict`, `kosmos.core.profiling.ExecutionProfiler` (lazy), `concurrent.futures`, `signal` | On Windows, `ThreadPoolExecutor` timeout does not kill the thread -- hung computation continues consuming resources [FACT: executor.py:621-630]; retry fixes wrap code in try/except making execution "succeed" with error dict [FACT: executor.py:869-877] |
| `kosmos/models/experiment.py` | Defines Pydantic data models for experiment design: variables, control groups, protocol steps, resource requirements, statistical test specs, validation checks, and full experiment protocols, with defensive LLM-output validators | `pydantic`, `kosmos.models.hypothesis.ExperimentType` (top-level import), `kosmos.config._DEFAULT_CLAUDE_SONNET_MODEL` (top-level import), `logging`, `re` (inside validator), `datetime`, `enum` | `validate_steps` silently SORTS steps by `step_number` as a validator side effect [FACT: experiment.py:438]; `to_dict()` is hand-written -- adding a new field without updating it means silent data loss [FACT: experiment.py:471-573] |
| `kosmos/knowledge/graph.py` | Provides Neo4j-backed knowledge graph with CRUD on 4 node types (Paper, Concept, Method, Author) and 5 relationship types, plus graph traversal queries, with Docker auto-start | `py2neo` (hard), `kosmos.config.get_config()`, `kosmos.literature.base_client.PaperMetadata`, Docker CLI + `docker-compose` (subprocess), Neo4j server | `create_authored` increments `paper_count` every call regardless of merge -- double-counting on repeated calls [FACT: graph.py:615-616]; Cypher queries use f-string interpolation for `depth`/`max_hops` [FACT: graph.py:761]; Docker health check hardcodes `neo4j`/`kosmos-password` credentials [FACT: graph.py:155-156] |
| `kosmos/models/hypothesis.py` | Defines Pydantic data models for the hypothesis lifecycle: `Hypothesis`, `ExperimentType`, `HypothesisStatus`, generation requests/responses, novelty/testability reports, and prioritized hypothesis wrappers | `pydantic`, `kosmos.config._DEFAULT_CLAUDE_SONNET_MODEL` (top-level import), `datetime`, `enum` | `ExperimentType` is defined HERE, not in experiment.py -- 48 importers affected if moved [FACT: experiment.py:14]; `datetime.utcnow()` used for defaults, deprecated in Python 3.12+ [FACT: hypothesis.py:76-77] |
| `kosmos/core/llm.py` | Provides unified LLM client interface via singleton pattern; all LLM access funnels through `get_client()` or `get_provider()`, supporting Anthropic API and CLI mode, and OpenAI-compatible providers | `anthropic` (optional but required at runtime), `kosmos.config`, `kosmos.core.pricing`, `kosmos.core.claude_cache`, `kosmos.core.utils.json_parser`, `kosmos.core.providers.base`, `kosmos.core.providers.anthropic` (lazy) | Cost estimation hardcodes `"claude-sonnet-4-5"` model name for lookup regardless of actual model used [FACT: llm.py:519]; `get_client()` can return either `ClaudeClient` or `LLMProvider` -- callers must handle both [FACT: llm.py:609] |
| `kosmos/core/logging.py` | Provides structured logging with JSON and text output modes, a module-level `ContextVar` for correlation IDs, and `ExperimentLogger` for experiment lifecycle tracking with timing | `logging`, `logging.handlers`, `contextvars`, `json` (all stdlib); `kosmos.config.get_config` (deferred import in `configure_from_config`) | `setup_logging()` clears ALL root logger handlers on every call [FACT: logging.py:179]; `TextFormatter` mutates `record.levelname` in place -- ANSI codes leak to JSON output if both formatters share a record [FACT: logging.py:128] |
| `kosmos/core/providers/base.py` | Defines abstract `LLMProvider` interface and supporting types (`Message`, `UsageStats`, `LLMResponse`, `ProviderAPIError`) enabling backend swapping via unified API | `abc`, `datetime` (stdlib only); zero external packages; zero Kosmos imports | `LLMResponse` with empty content is falsy -- `if not response:` treats successful empty API response as failure [FACT: base.py:98-99]; `response.strip()` returns `str`, losing `.usage`, `.model` metadata [FACT: base.py:107-108]; `if False: yield` in `generate_stream_async` is load-bearing dead code [FACT: base.py:360-363] |
| `kosmos/agents/research_director.py` | Master orchestrator driving the full autonomous research cycle (hypothesize -> design -> execute -> analyze -> refine -> iterate) by coordinating 6+ specialized agents through a workflow state machine | `kosmos.agents.base`, `kosmos.utils.compat`, `kosmos.core.rollout_tracker`, `kosmos.core.workflow`, `kosmos.core.convergence`, `kosmos.core.llm`, `kosmos.core.stage_tracker`, `kosmos.models.hypothesis`, `kosmos.world_model`, `kosmos.db`, `kosmos.agents.skill_loader`; 10+ lazy imports for agents and executors | `time.sleep()` in error recovery blocks the asyncio event loop [FACT: research_director.py:674]; message-based `_send_to_*` methods are effectively dead code (Issue #76) [FACT: research_director.py:1039-1219]; DB init failures are only logged as warnings -- cascading failures when handlers query DB [FACT: research_director.py:131-139] |
| `kosmos/models/result.py` | Defines Pydantic data models for experiment results: `ExperimentResult`, `StatisticalTestResult`, `VariableResult`, `ExecutionMetadata`, `ResultStatus`, and `ResultExport` | `pydantic`, `kosmos.utils.compat.model_to_dict`, `pandas` (lazy import in `export_csv` only) | `export_markdown()` formats variable stats with `{var.mean:.2f}` without null check -- `TypeError` if any optional stat is `None` [FACT: result.py:349-353]; `created_at` uses deprecated `datetime.utcnow()` [FACT: result.py:203] |
| `kosmos/orchestration/` (plan_creator, plan_reviewer, delegation, novelty_detector) | Strategic research planning pipeline: generates 10-task plans with adaptive exploration/exploitation, filters redundant tasks via semantic similarity, validates plans on 5 dimensions, and executes approved plans by routing to specialized agents | `anthropic` (direct SDK, bypasses provider layer), `sentence-transformers` (optional, fallback to Jaccard), `numpy`, agent instances via constructor injection | PlanCreatorAgent and PlanReviewerAgent bypass Kosmos LLMProvider -- no caching, no cost tracking, no retry logic [FACT: plan_creator.py:158-162, plan_reviewer.py:125-129]; DelegationManager raises RuntimeError at execution time if agent missing -- no init-time validation [FACT: delegation.py:395-399] |
| `kosmos/knowledge/vector_db.py` | Wraps ChromaDB for persistent vector storage and cosine-similarity search for scientific papers, with SPECTER embedding computation and singleton access pattern | `chromadb` (optional), `kosmos.knowledge.embeddings.get_embedder()`, `kosmos.literature.base_client.PaperMetadata`, `kosmos.config.get_config()`, `numpy` | `clear()` has no null guard on `self.client` -- raises `AttributeError` if ChromaDB unavailable [FACT: vector_db.py:370-371]; embedder initialization may trigger ~440MB model download during construction [FACT: vector_db.py:103]; singleton is not thread-safe [FACT: vector_db.py:443-477] |
| `kosmos/core/workflow.py` | Defines the research workflow state machine: 9 states, allowed transitions, and the `ResearchPlan` data structure tracking hypotheses, experiments, and results across iterations | `pydantic`, `kosmos.config.get_config` (lazy import in `transition_to` for log-gating) | `ResearchPlan.current_state` and `ResearchWorkflow.current_state` can diverge if workflow is modified without `transition_to()` [FACT: workflow.py:319, 323-325]; `CONVERGED` is not terminal -- can transition back to `GENERATING_HYPOTHESES` [FACT: workflow.py:212-213]; `get_untested_hypotheses()` is O(n*m) using list instead of set [FACT: workflow.py:149-151] |
| `kosmos/world_model/` (interface, models, factory, simple, in_memory, artifacts) | Persistent knowledge graph for accumulating research findings across sessions, using Strategy pattern with Neo4j-backed and in-memory fallback implementations, plus a JSON artifact layer | `kosmos.knowledge.graph` (for Neo4j adapter), `py2neo` (via graph.py), `kosmos.config.get_config` (lazy), Docker (for Neo4j auto-start); `warnings` (stdlib) | No thread safety on singleton factory [FACT: factory.py:38]; silent fallback to in-memory means data loss on restart without clear signal [FACT: factory.py:123-133]; `reset_knowledge_graph()` does not close existing Neo4j connection -- potential leak [FACT: world_model analysis]; vector store Layer 3 is a stub (`pass`) [FACT: artifacts.py:560-567] |

---

### Detailed Module Behavioral Descriptions

---

### `kosmos/agents/base.py`

**What it does**: Defines `BaseAgent`, the superclass of all Kosmos agents (ResearchDirector, HypothesisGenerator, ExperimentDesigner, DataAnalyst, LiteratureAnalyzer, StageOrchestrator). Provides lifecycle management (start/stop/pause/resume), async inter-agent message passing via `AgentMessage` Pydantic objects, state persistence via `AgentState`, and health monitoring. [FACT: base.py:97-111]

**What's non-obvious**:
- **Dual message queue**: Both a legacy sync `message_queue: List` (line 136) and an `_async_message_queue: asyncio.Queue` (line 137) exist side-by-side. `receive_message()` writes to BOTH (line 337-338). The sync list grows unbounded -- no eviction or size limit. [FACT: base.py:136-138, 337-338]
- **Config import inside method body**: `send_message()` and `receive_message()` perform deferred `from kosmos.config import get_config` inside try/except (lines 276-287, 341-352). This avoids circular imports but silently swallows config failures. [FACT: base.py:276-287]
- **Router can be sync or async**: `_message_router` is typed `Union[Callable, Callable[..., Awaitable]]`. `send_message()` checks `asyncio.iscoroutine(result)` to decide whether to await (line 294). Router errors are caught per-message but do NOT prevent `send_message()` from returning the constructed message. [FACT: base.py:290-298]
- **`start()` is one-shot**: Can only transition from CREATED state (line 161). Calling on already-started agent logs warning and returns silently. [FACT: base.py:161-163]
- **`stop()` has no status guard**: Unlike `pause()`/`resume()` which check current status, `stop()` attempts to stop from ANY status, including CREATED or ERROR. [FACT: base.py:177-187]
- **Sync wrappers use 30s hardcoded timeout**: `send_message_sync`, `receive_message_sync`, `process_message_sync` all use `future.result(timeout=30)`. [FACT: base.py:322, 378, 402]
- **`_on_pause()` and `_on_resume()` hooks exist but are never called** by `pause()` and `resume()` methods -- dead code. [FACT: base.py:513-517]
- **`register_message_handler()` stores handlers but `process_message()` does NOT dispatch to them** -- the registered handlers dict is dead code unless subclasses explicitly use it. [FACT: base.py:406-415]

**Blast radius**: Every agent inherits from `BaseAgent`. Changing `__init__` signature, message protocol, or lifecycle states ripples to at least 6 agent subclasses. [PATTERN: 6 subclasses found]. `AgentMessage` is the wire format for all inter-agent communication. The `AgentRegistry` calls `agent.set_message_router()` on every registered agent [FACT: registry.py:94]. `AgentStatus` enum values are used in monitoring/logging.

**Public API**:

- **`AgentMessage.to_dict()`**: Serializes to dict with ISO timestamp. No preconditions, no side effects, cannot fail on valid instance. [FACT: base.py:69-80]
- **`AgentMessage.to_json()`**: JSON via `json.dumps(self.to_dict())`. Raises `TypeError` if content not JSON-serializable. [FACT: base.py:82-84]
- **`BaseAgent.__init__(agent_id, agent_type, config)`**: Auto-generates UUID if no agent_id. Creates both queues, zeroes stats. Side effect: logs at INFO. [FACT: base.py:113-153]
- **`BaseAgent.start()`**: CREATED -> STARTING -> RUNNING. Calls `_on_start()` hook. Precondition: status must be CREATED. Sets ERROR and re-raises if hook throws. [FACT: base.py:159-175]
- **`BaseAgent.stop()`**: Transitions to STOPPED from ANY status. Calls `_on_stop()` hook. Re-raises if hook throws. [FACT: base.py:177-187]
- **`BaseAgent.pause()`/`resume()`**: RUNNING <-> PAUSED. Warns and returns on wrong state. [FACT: base.py:189-205]
- **`BaseAgent.send_message(to_agent, content, message_type, correlation_id)`** [async]: Constructs `AgentMessage`, increments counter, logs via config, routes via `_message_router`. Returns message even if routing fails. [FACT: base.py:246-300]
- **`BaseAgent.receive_message(message)`** [async]: Appends to both queues, calls `process_message()`. On processing failure for REQUEST messages, sends ERROR response back. [FACT: base.py:329-367]
- **`BaseAgent.process_message(message)`** [async]: Default logs warning. Subclasses must override. [FACT: base.py:382-391]
- **`BaseAgent.execute(task)`**: Raises `NotImplementedError`. [FACT: base.py:485-497]
- **`BaseAgent.get_state()`**: Returns `AgentState`. Side effect: updates `self.updated_at`. [FACT: base.py:439-454]
- **`BaseAgent.restore_state(state)`**: Overwrites all identity/state fields from saved state. [FACT: base.py:456-470]

---

### `kosmos/core/providers/anthropic.py`

**What it does**: Implements the Anthropic (Claude) LLM provider with sync/async generation, streaming, structured JSON output, response caching, auto model selection (Haiku/Sonnet), and cost tracking -- supporting both real API keys and a "CLI mode" where an all-9s key routes through Claude Code. [FACT: anthropic.py:1-5]

**What's non-obvious**:
- **CLI mode detection is string-based**: `self.api_key.replace('9', '') == ''` -- any key consisting entirely of 9s (any length) triggers CLI mode, disabling cost calculation. [FACT: anthropic.py:110]
- **Cache key includes all generation parameters**: Composite key of prompt, model, system prompt, max_tokens, temperature, stop_sequences. Changing ANY causes a cache miss. [FACT: anthropic.py:213-218]
- **Cache hits bypass usage tracking**: `_update_usage_stats` is NOT called on cache hits. `self.total_input_tokens` and `self.total_cost_usd` undercount when cache is active. [FACT: anthropic.py:228-249]
- **Auto model selection disabled by default AND in CLI mode**: Even with `enable_auto_model_selection=True`, CLI mode skips auto-selection. [FACT: anthropic.py:187]
- **`generate_structured` instructs JSON via system prompt appendage**: Appends `\n\nYou must respond with valid JSON matching this schema:\n{schema}` to system prompt. [FACT: anthropic.py:530]
- **JSON parse errors marked non-recoverable**: `ProviderAPIError(recoverable=False)` prevents DelegationManager retry logic from retrying. [FACT: anthropic.py:548-556]
- **Streaming counts text chunks, not tokens**: `total_tokens += 1` per text chunk, not per actual token. The `completion_tokens` field in emitted events is wrong. [FACT: anthropic.py:731-732]
- **Async client lazily initialized**: `self._async_client` created on first access via property. [FACT: anthropic.py:344-359]
- **`generate_with_messages` does NOT use caching** and does NOT support model override (always uses `self.model`). [FACT: anthropic.py:432-500, 467]
- **Backward compatibility alias**: `ClaudeClient = AnthropicProvider` at module level. [FACT: anthropic.py:881]
- **`generate_async` does not call `_update_usage_stats`**: Async calls don't contribute to running totals, inconsistent with sync `generate`. [FACT: anthropic.py:400-430]

**Blast radius**: All LLM-dependent agents go through this class. Cost tracking pipeline depends on CLI mode detection and pricing calls. Cache layer affects hit rates across all agents. Streaming methods emit events to event bus. `LLMResponse` string compatibility affects all callers.

**Public API**:

- **`AnthropicProvider.__init__(config)`**: Initializes sync client, configures caching and model selection. Raises `ImportError`/`ValueError`/`ProviderAPIError`. [FACT: anthropic.py:36-108]
- **`generate(prompt, system, max_tokens=4096, temperature=0.7, ...)`**: Generates with caching, auto-model-selection, cost tracking. Side effects: updates counters, writes cache. kwargs: `bypass_cache`, `model_override`. [FACT: anthropic.py:207-365]
- **`generate_async(...)`** [async]: True async via `AsyncAnthropic`. No caching, no usage stat updates. [FACT: anthropic.py:370-430]
- **`generate_with_messages(messages, ...)`**: Multi-turn. No caching. No model override. System messages extracted separately. [FACT: anthropic.py:432-500]
- **`generate_structured(prompt, schema, ...)`**: Returns `Dict`. JSON parse failures raise `ProviderAPIError(recoverable=False)`. [FACT: anthropic.py:520-560]
- **`generate_stream(prompt, ...)`**: Yields text chunks. Emits LLM events to event bus. Token counts are inaccurate. [FACT: anthropic.py:700-740]

---

### `kosmos/literature/base_client.py`

**What it does**: Defines the abstract base class (`BaseLiteratureClient`) and unified data types (`PaperMetadata`, `Author`, `PaperSource`) for all literature API integrations. Every literature client (arXiv, Semantic Scholar, PubMed) inherits from `BaseLiteratureClient` and returns `PaperMetadata` objects. This is a leaf dependency -- it imports nothing from Kosmos. [FACT: base_client.py:1-13]

**What's non-obvious**:
- **`PaperMetadata` is a `@dataclass`, not a Pydantic model**: No automatic validation, no `.model_dump()`. Uses `__post_init__` for default mutable fields. [FACT: base_client.py:36, 80]
- **`authors` defaults to `None`, not `[]`**: Workaround for Python dataclass mutable-default restriction. Patched to `[]` in `__post_init__`. Same for `fields` and `keywords`. [FACT: lines 53, 71, 72, 84-87]
- **`_normalize_paper_metadata` is NOT `@abstractmethod`**: Concrete method that raises `NotImplementedError`. Subclasses can omit it without ABC enforcement -- error only surfaces at runtime. [FACT: base_client.py:255]
- **`_validate_query` warns but doesn't truncate**: Log says "truncating to 1000" but returns `True` without modification. [FACT: base_client.py:248-250]
- **`raw_data` stores entire API responses**: Excluded from `to_dict()` serialization but consumes memory. [FACT: base_client.py:78, 99-122]
- **`_handle_api_error` swallows exceptions**: Logs but does not re-raise. [FACT: base_client.py:229-233]

**Blast radius**: 35 importers. Renaming `PaperMetadata` or its fields breaks every literature client, agent, knowledge graph ingestion, and world model. Changing `PaperSource` enum breaks persisted data. Changing `BaseLiteratureClient.search()` signature breaks all 4 concrete implementations. [FACT: grep found 4 subclasses]

**Public API**:
- **`PaperSource(str, Enum)`**: ARXIV, SEMANTIC_SCHOLAR, PUBMED, UNKNOWN, MANUAL. [FACT: line 17]
- **`Author` dataclass**: name (required), optional affiliation, email, author_id. No validation. [FACT: line 27]
- **`PaperMetadata` dataclass**: Unified paper representation. `id` and `source` required. `primary_identifier` property returns first non-None in order DOI > arXiv > PubMed > id. `to_dict()` excludes `raw_data`. [FACT: lines 36, 89, 99]
- **`BaseLiteratureClient(ABC)`**: Abstract with `search()`, `get_paper_by_id()`, `get_paper_references()`, `get_paper_citations()`. [FACT: lines 125, 146, 172, 184, 198]

---

### `kosmos/execution/code_generator.py`

**What it does**: Generates executable Python code from `ExperimentProtocol` objects using a hybrid approach: template matching against 5 built-in experiment type templates (t-test, correlation, log-log scaling, ML, generic computational), falling back to LLM-based generation via Claude, with a minimal hardcoded template as last resort. [FACT: code_generator.py:1-9, 786-793]

**What's non-obvious**:
- **Template priority is order-dependent**: Templates matched in registration order. `GenericComputationalCodeTemplate` registered LAST catches `COMPUTATIONAL` and `DATA_ANALYSIS`. First match wins -- no priority scoring. [FACT: code_generator.py:787-793, 559-564]
- **All templates generate synthetic data fallback**: Every template checks `if 'data_path' in dir()` and falls through to synthetic `np.random.seed()` data. Experiments can run without input data files. [FACT: code_generator.py:112-130, 243-259, 381-397, 474-488, 590-608]
- **Generated code uses `dir()` for variable detection**: Templates check `if 'data_path' in dir()` rather than try/except. Works because `dir()` in exec'd code returns local scope names. [FACT: code_generator.py:112, 169]
- **LLM client has double fallback**: Tries `ClaudeClient()` first, then `LiteLLMProvider`, then silently disables LLM (`self.use_llm = False`). [FACT: code_generator.py:762-778]
- **Template code NOT validated for safety**: Only `_validate_syntax()` (AST parse). `CodeValidator` runs later in executor. [FACT: code_generator.py:831, 981-989]
- **`_generate_basic_template` is the ONLY template without synthetic data**: Uses `pd.read_csv(data_path)` without fallback. Raises `NameError` if `data_path` undefined. [FACT: code_generator.py:954-977]
- **`random_seed=0` silently becomes 42**: `getattr(protocol, 'random_seed', 42) or 42` -- 0 is falsy. [FACT: code_generator.py:89]
- **`_validate_syntax` raises `ValueError`, not `SyntaxError`**: Changes exception type for callers. [FACT: code_generator.py:988-989]
- **`_extract_code_from_response` has weak heuristic**: If no code fences, checks for "import", "def ", or "=" -- natural language with "=" is treated as code. [FACT: code_generator.py:907-924]

**Blast radius**: `ExperimentCodeGenerator.generate()` called by `research_director.py:1528` for every experiment. Generated code must assign to `results` variable (executor extracts by name). Templates import from Kosmos internal modules.

**Public API**:
- **`CodeTemplate`**: Base with `matches(protocol)` and `generate(protocol)`. [FACT: code_generator.py:27-45]
- **`TTestComparisonCodeTemplate`**: Matches `DATA_ANALYSIS` with t-test. Produces Shapiro normality + Levene variance + t-test. [FACT: code_generator.py:58-190]
- **`CorrelationAnalysisCodeTemplate`**: Pearson+Spearman, picks best by p-value. [FACT: code_generator.py:203-340]
- **`LogLogScalingCodeTemplate`**: Power-law fitting with log-log plot. [FACT: code_generator.py:353-441]
- **`MLExperimentCodeTemplate`**: sklearn classification pipeline. [FACT: code_generator.py:450-544]
- **`GenericComputationalCodeTemplate`**: Catch-all for COMPUTATIONAL/DATA_ANALYSIS. [FACT: code_generator.py:559-728]
- **`ExperimentCodeGenerator.generate(protocol)`**: Hybrid: template -> LLM -> basic fallback. Always validates syntax. Returns code string. [FACT: code_generator.py:797-833]
- **`ExperimentCodeGenerator.save_code(code, file_path)`**: Filesystem write. [FACT: code_generator.py:991-995]

---

### `kosmos/safety/code_validator.py`

**What it does**: Validates generated Python code for safety (dangerous imports, dangerous function calls, file/network access), security (AST-based detection of reflection calls and dunder attribute access), and ethical research compliance (keyword-based screening against configurable guidelines), producing a `SafetyReport`. [FACT: code_validator.py:1-9]

**What's non-obvious**:
- **`os` on dangerous list but auto-fix inserts it**: RetryStrategy's `COMMON_IMPORTS` includes `'os': 'import os'` (executor.py:686), which the validator would reject. [FACT: code_validator.py:36, executor.py:686]
- **Ethical checks are keyword-based with high false-positive risk**: Words like "email", "password", "survey", "harm" trigger violations. Scientific code about email metadata or harm-reduction triggers these. [FACT: code_validator.py:118-119, 395-418]
- **Pattern checking uses raw string matching**: `if pattern in code:` catches patterns in comments and string literals. [FACT: code_validator.py:288]
- **`open(` write mode detection is fragile**: Checks `"'w'"`, `"'a'"`, `"'x'"`, `"mode='w'"` as substrings. Misses `'wb'`, `'ab'`, `'r+'`, and variable-based modes. [FACT: code_validator.py:296-297]
- **AST parsed up to 3 times**: `_check_syntax()`, `_check_dangerous_imports()`, and `_check_ast_calls()` each parse independently. [FACT: code_validator.py:237, 252, 332]
- **`getattr` flagged as CRITICAL**: Common `getattr(obj, 'attr', default)` pattern fails validation. [FACT: code_validator.py:338]
- **Approval request truncates code to 500 chars**: Long code not fully visible to reviewer. [FACT: code_validator.py:510]
- **Ethical guideline `break` after first keyword match per guideline**: Only one violation per guideline reported. [FACT: code_validator.py:417]

**Blast radius**: `CodeValidator.validate()` called by executor.py (line 1040) and guardrails.py (line 26). Gates ALL code execution. `SafetyReport` determines pass/fail for entire execution pipeline. `DANGEROUS_MODULES` list determines blocked imports.

**Public API**:
- **`CodeValidator.__init__(ethical_guidelines_path, allow_file_read=True, allow_file_write=False, allow_network=False)`**: Loads guidelines from JSON or defaults. [FACT: code_validator.py:58-85]
- **`CodeValidator.validate(code, context)`**: Runs 6 checks: syntax, imports, patterns, network, AST calls, ethics. Returns `SafetyReport`. `passed` = zero violations. [FACT: code_validator.py:159-231]
- **`CodeValidator.requires_approval(report)`**: True if config mandates approval, OR risk HIGH/CRITICAL, OR critical violations, OR ethical violations. [FACT: code_validator.py:436-465]
- **`CodeValidator.create_approval_request(code, report, context)`**: Creates `ApprovalRequest` with truncated code (500 chars). [FACT: code_validator.py:467-515]

---

### `kosmos/core/convergence.py`

**What it does**: Decides when the autonomous research loop should stop iterating by evaluating mandatory stopping criteria (iteration limit, hypothesis exhaustion) and optional scientific criteria (novelty decline, diminishing returns), then generates a convergence report. [FACT: convergence.py:1-7]

**What's non-obvious**:
- **Iteration limit checked LAST**: Mandatory hard-stops checked first, then optional scientific criteria, then iteration limit. If both `novelty_decline` and `iteration_limit` fire, `novelty_decline` is the reported reason. [FACT: convergence.py:246-268]
- **Iteration limit can be DEFERRED**: When at limit but fewer than `min_experiments_before_convergence` (default 2) experiments completed AND testable work remains, returns `should_stop=False`. [FACT: convergence.py:332-356, line 206]
- **Novelty trend is stateful and unbounded**: Each call appends to `self.metrics.novelty_trend`. Never truncated. [FACT: convergence.py:562]
- **Novelty decline uses OR logic**: Below-threshold OR monotonically-decreasing. [FACT: convergence.py:421-427]
- **"Continue" uses `USER_REQUESTED` as placeholder**: Enum has no "none" variant. [FACT: convergence.py:271]
- **`novelty_decline_window` dynamically clamped**: `min(5, max(2, max_iters - 1))`. [FACT: convergence.py:200-203]
- **Flat novelty score is "declining"**: Uses `>=` comparison, so constant scores trigger stop. [FACT: convergence.py:424]

**Blast radius**: Return value directly controls whether the autonomous research loop continues. `ConvergenceReport` consumed by reporting/output layers. Cost tracking feeds `check_diminishing_returns`.

**Public API**:
- **`ConvergenceDetector.check_convergence(research_plan, hypotheses, results, total_cost)`**: Evaluates all criteria in priority order. Mutates `self.metrics`. Unknown criteria names return `should_stop=False` with `confidence=0.0`. [FACT: convergence.py:246-308]
- **`ConvergenceDetector.check_iteration_limit(research_plan)`**: Deferrable stop. [FACT: convergence.py:332-356]
- **`ConvergenceDetector.check_novelty_decline()`**: Requires populated `novelty_trend`. Returns `should_stop=False` on insufficient data. [FACT: convergence.py:421-427]
- **`ConvergenceDetector.generate_convergence_report(research_plan, hypotheses, results, stopping_reason)`**: Final report with stats and recommendations. Mutates metrics one final time. [FACT: convergence.py:700+]

---

### `kosmos/execution/executor.py`

**What it does**: Executes generated Python (and optionally R) code with safety sandboxing, output capture, timeout enforcement, optional profiling, determinism testing, and self-correcting retry logic. [FACT: executor.py:1-6]

**What's non-obvious**:
- **Restricted builtins sandbox**: Replaces `__builtins__` with `SAFE_BUILTINS` (~80 safe builtins) and custom `_make_restricted_import()` limiting to ~30 modules. NOT process isolation. [FACT: executor.py:43-94, 589-597]
- **Return value by convention**: Looks for `results` or `result` in exec'd namespace. [FACT: executor.py:516]
- **Docker sandbox fallback is silent**: If `use_sandbox=True` but Docker unavailable, silently downgrades. [FACT: executor.py:216-220]
- **Platform-dependent timeout**: Unix uses `signal.SIGALRM` (clean). Windows uses `ThreadPoolExecutor` -- cannot kill stuck thread, it continues executing. [FACT: executor.py:600-630]
- **`execute_with_data()` injects data_path twice**: Both prepended to code AND passed as local variable. [FACT: executor.py:653-660]
- **RetryStrategy wraps entire code in try/except**: Execution "succeeds" but with `results = {'error': ..., 'status': 'failed'}`. [FACT: executor.py:869-877]
- **FileNotFoundError is terminal**: Returns `None`, listed as non-retryable. Intentional Issue #51 fix. [FACT: executor.py:726, 879-906]
- **LLM repair only on first 2 attempts**: After that, pattern-based fixes only. [FACT: executor.py:779]
- **`execute_protocol_code()` always validates safety**: Previous bypass deliberately removed (F-21). [FACT: executor.py:1039-1048]
- **Restricted builtins include `hasattr` but NOT `getattr`/`setattr`/`delattr`**. However, `type` and `object` ARE included, which can bypass restrictions via `type.__getattribute__`. [FACT: executor.py:594-597]
- **Retry loop calls `time.sleep()` synchronously**: Blocks event loop in async contexts. [FACT: executor.py:335]

**Blast radius**: Used by `research_director.py` for all experiment execution. `ExecutionResult` consumed by entire results pipeline. `SAFE_BUILTINS` and `_ALLOWED_MODULES` define the security boundary. `execute_protocol_code()` called by parallel.py for parallel execution.

**Public API**:
- **`CodeExecutor.execute(code, local_vars, retry_on_error, llm_client, language)`**: Auto-detects language. Returns `ExecutionResult`. Never raises -- returns failure result. [FACT: executor.py:237-376]
- **`CodeExecutor.execute_with_data(code, data_path, retry_on_error)`**: Wraps `execute()` with data_path injection. [FACT: executor.py:632-660]
- **`RetryStrategy.modify_code_for_retry(original_code, error, error_type, traceback_str, attempt, llm_client)`**: Handles 11 error types. Returns modified code or None. [FACT: executor.py:751-825]
- **`execute_protocol_code(code, data_path, max_retries, use_sandbox, sandbox_config)`**: Convenience function. Always validates safety. Returns dict. [FACT: executor.py:1017-1066]

---

### `kosmos/models/experiment.py`

**What it does**: Defines Pydantic data models for experiment design and validation: variables, control groups, protocol steps, resource requirements, statistical test specs, validation checks, and full experiment protocols. Contains defensive validators for malformed LLM output. [FACT: experiment.py:1-9]

**What's non-obvious**:
- **Imports `ExperimentType` from hypothesis.py**: Creates import chain experiment.py -> hypothesis.py -> kosmos.config. [FACT: experiment.py:14]
- **`_MAX_SAMPLE_SIZE = 100_000`**: Module-level constant used as hard ceiling in multiple validators. Changing it silently changes validation behavior. [FACT: experiment.py:19, 120-124, 386-392]
- **LLM-output defensive validators**: `coerce_sample_size` converts string to int, clamps to max [lines 106-125]. `coerce_groups` splits comma-separated strings [lines 266-273]. `parse_effect_size` extracts floats from text like `"Medium (Cohen's d = 0.5)"` via regex [lines 282-299]. `ensure_title` replaces empty titles with `"Untitled Step"` [lines 176-182].
- **`validate_steps` sorts steps by number**: Side effect hidden in a validator. Input order not preserved. [FACT: experiment.py:438]
- **`to_dict()` is hand-written (100 lines)**: Adding a new field without updating `to_dict()` means silent disappearance from serialization. [FACT: experiment.py:471-573]
- **`re` imported inside validator**: `parse_effect_size` imports `re` at call time. [FACT: experiment.py:293]

**Blast radius**: 30 importers. Renaming `ExperimentProtocol` breaks experiment designer agent, validator, all templates, resource estimator, memory module, world model, and research director.

**Public API**:
- **`ExperimentProtocol(BaseModel)`**: Central experiment data object. `name` (5+ chars), `hypothesis_id`, `experiment_type`, `domain`, `description` (20+ chars), `objective` (10+ chars), `steps` (non-empty, sequential), `variables`, `resource_requirements` required. [FACT: experiment.py:329-575]
- **`ExperimentProtocol.get_step(step_number)`**: Returns step or `None`. [FACT: line 440]
- **`ExperimentProtocol.get_independent_variables()`/`get_dependent_variables()`**: Filters by `VariableType`. [FACT: lines 447, 452]
- **`ExperimentProtocol.to_dict()`**: Manual 100-line serialization. [FACT: lines 471-573]

---

### `kosmos/knowledge/graph.py`

**What it does**: Provides a Neo4j-backed knowledge graph for scientific literature with full CRUD on 4 node types (Paper, Concept, Method, Author) and 5 relationship types (CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO), plus graph traversal queries. [FACT: graph.py:1-6]

**What's non-obvious**:
- **Auto-starts a Docker container**: `_ensure_container_running()` runs `docker ps`, then `docker-compose up -d neo4j`, then polls health up to 30 times (2s each = 60s). Hardcodes `neo4j`/`kosmos-password` credentials. [FACT: graph.py:118-171]
- **Connection failure swallowed**: Sets `self.graph = None`, `self._connected = False`. Does NOT raise. [FACT: graph.py:96-99]
- **`create_authored` increments `paper_count` without idempotency**: Merge applies to relationship only, not count logic. Double-counting on repeated calls. Same for `create_discusses` (frequency) and `create_uses_method` (usage_count). [FACT: graph.py:615-616, 659, 703]
- **Cypher injection via f-string**: `depth` and `max_hops` interpolated into Cypher. Typed as `int` but no validation prevents string injection. [FACT: graph.py:761, 917]
- **Node lookup cascade**: `get_paper` tries 4 indexes sequentially: id, doi, arxiv_id, pubmed_id. DOI matching wrong paper's id field returns wrong paper. [FACT: graph.py:262-289]
- **`delete_paper` uses py2neo's detach-delete**: All relationships auto-deleted. [FACT: graph.py:322-329]

**Blast radius**: Docker dependency means init can take 60+ seconds. 10 indexes created at init. `get_knowledge_graph()` returns module-global singleton (not thread-safe). py2neo is a hard (non-optional) dependency.

**Public API**:
- **`KnowledgeGraph.__init__(..., auto_start_container=True, create_indexes=True)`**: May start Docker container, create 10 indexes. Swallows connection errors. [FACT: graph.py:36-112]
- **`create_paper(paper, merge=True)`**: Creates/merges Paper node. [FACT: graph.py:360-420]
- **`create_citation(citing_paper_id, cited_paper_id, merge=True)`**: CITES relationship. Returns None if paper not found. [FACT: graph.py:500-540]
- **`get_citations(paper_id, depth=1)`**: Variable-depth traversal. F-string interpolated depth. [FACT: graph.py:760+]
- **`find_related_papers(paper_id, max_hops=2, limit=20)`**: Multi-hop traversal. [FACT: graph.py:900+]
- **`clear_graph()`**: `MATCH (n) DETACH DELETE n` -- destroys ALL data. [FACT: graph.py:960+]
- **`get_knowledge_graph()`**: Module-level singleton factory. [FACT: graph.py:999-1038]

---

### `kosmos/models/hypothesis.py`

**What it does**: Defines Pydantic data models for the hypothesis lifecycle: generation requests, hypothesis objects with scores and evolution tracking, generation responses, novelty reports, testability reports, and prioritized hypothesis wrappers. Pure data-model file with no business logic beyond validation. [FACT: hypothesis.py:1-7]

**What's non-obvious**:
- **Import-time dependency on `kosmos.config`**: Imports `_DEFAULT_CLAUDE_SONNET_MODEL` at module scope. Importing `Hypothesis` triggers the entire config module. [FACT: hypothesis.py:13]
- **`ExperimentType` defined HERE, not in experiment.py**: Three-value enum: COMPUTATIONAL, DATA_ANALYSIS, LITERATURE_SYNTHESIS. Re-imported by experiment.py. [FACT: hypothesis.py:15-19, experiment.py:14]
- **`Hypothesis` NOT re-exported from `kosmos/models/__init__.py`**: Every importer must use direct import path. [ABSENCE: checked models/__init__.py]
- **Validator `validate_statement` has dead code**: Checks for predictive words but only as pass-through comment -- never warns or fails. [FACT: hypothesis.py:101]
- **`datetime.utcnow()` for defaults**: Deprecated in Python 3.12+. Produces naive datetimes. [FACT: hypothesis.py:76-77]
- **`ConfigDict(use_enum_values=False)` on Hypothesis**: Stores enum objects, not strings. `model_dump()` returns Enum objects. [FACT: line 156]
- **`PrioritizedHypothesis.update_hypothesis_priority()` mutates the contained Hypothesis**: Only mutation in the entire file. [FACT: line 329-330]

**Blast radius**: 48 importers -- the most-imported module. Renaming `Hypothesis` breaks 30+ direct importers. Changing `ExperimentType` cascades through experiment templates, resource estimator, and experiment services.

**Public API**:
- **`Hypothesis(BaseModel)`**: `research_question` (required), `statement` (10-500 chars, must not end with `?`), `rationale` (20+ chars), `domain` (required). Four float scores: testability, novelty, confidence, priority. [FACT: hypothesis.py:32-156]
- **`Hypothesis.is_testable(threshold=0.3)`/`is_novel(threshold=0.5)`**: Score threshold checks. [FACT: lines 144, 150]
- **`HypothesisGenerationResponse.get_best_hypothesis()`**: Highest priority_score. Falls back to first. Returns None if empty. [FACT: line 218]
- **`PrioritizedHypothesis`**: Composite scoring (novelty 30%, feasibility 25%, impact 25%, testability 20%). [FACT: line 299]

---

### `kosmos/core/llm.py`

**What it does**: Provides a unified LLM client interface through a singleton pattern; all LLM access funnels through `get_client()` or `get_provider()`. Supports Anthropic API and CLI mode, and OpenAI-compatible providers. [FACT: llm.py:1-12]

**What's non-obvious**:
- **CLI mode detection**: `self.api_key.replace('9', '') == ''` -- silently changes cost tracking (CLI returns $0.00). [FACT: llm.py:179, 587-588]
- **Singleton holds either `ClaudeClient` OR `LLMProvider`**: Different interfaces. Callers must know which type or use `get_provider()` which asserts type. [FACT: llm.py:609, 700-706]
- **Thread safety via double-checked locking**: Fast-path outside lock, re-check inside. But `reset=True` from any thread replaces client for all threads. [FACT: llm.py:643-649]
- **Auto model selection never picks higher than Sonnet**: "haiku" for scores <30, "sonnet" for everything else. [FACT: llm.py:88-94]
- **Cache bypasses on retry**: `generate_structured()` passes `bypass_cache=attempt > 0`. [FACT: llm.py:467]
- **Auto model selection disabled in CLI mode**: `self.enable_auto_model_selection and not self.is_cli_mode`. [FACT: llm.py:251]
- **Cost estimation hardcodes model name**: Uses `"claude-sonnet-4-5"` regardless of actual model. [FACT: llm.py:519]

**Blast radius**: 27+ Python importers call `get_client()`. Key consumers include research_director, all agent types, code_generator, hypothesis modules. Changing singleton pattern breaks concurrent workflows.

**Public API**:
- **`ModelComplexity.estimate_complexity(prompt, system)`**: Returns dict with score, recommendation ("haiku"/"sonnet"), reason. Pure function. [FACT: llm.py:52-105]
- **`ClaudeClient.generate(prompt, system, max_tokens, temperature, ...)`**: Checks cache, supports model_override, bypass_cache. [FACT: llm.py:207-365]
- **`ClaudeClient.generate_structured(prompt, output_schema, ...)`**: Retries, appends schema to system prompt, raises `ProviderAPIError` on exhaustion. [FACT: llm.py:410-486]
- **`get_client(reset=False, use_provider_system=True)`**: Thread-safe singleton. Falls back to `AnthropicProvider` if config fails. [FACT: llm.py:613-679]
- **`get_provider()`**: Asserts `LLMProvider` type. Raises `TypeError` if singleton is `ClaudeClient`. [FACT: llm.py:682-706]

---

### `kosmos/core/logging.py`

**What it does**: Provides structured logging with JSON and text output modes, a module-level `ContextVar` for cross-async correlation IDs, and an `ExperimentLogger` class for experiment lifecycle tracking. [FACT: logging.py:1-7]

**What's non-obvious**:
- **Import side effect**: Module-level `correlation_id: contextvars.ContextVar` instantiated at import. However, no code in `kosmos/` imports this ContextVar from here [ABSENCE]. Only read by `JSONFormatter.format()`. [FACT: logging.py:23-25, 62-64]
- **`setup_logging()` clears ALL root logger handlers**: If called more than once or after third-party handler setup, handlers silently destroyed. [FACT: logging.py:179]
- **`TextFormatter` mutates LogRecord in place**: `record.levelname = f"{color}{record.levelname}{reset}"`. ANSI codes leak to other handlers sharing the record. [FACT: logging.py:128]
- **`configure_from_config()` uses deferred import**: `from kosmos.config import get_config` at line 395. Avoids circular imports. [FACT: logging.py:395]
- **`ExperimentLogger.events` list is unbounded**: No flush or rotation. [FACT: logging.py:271]
- **`JSONFormatter` has no serialization guard**: Non-JSON-serializable extras cause `TypeError`. [FACT: logging.py:82]
- **`datetime.utcfromtimestamp` deprecated in Python 3.12+**: Used at line 52. [FACT: logging.py:52]

**Blast radius**: 140 importers -- the most-imported module. Renaming `get_logger` or `setup_logging` breaks nearly everything. Changing `JSONFormatter` output schema breaks log parsing/monitoring.

**Public API**:
- **`setup_logging(level, log_format, log_file, debug_mode)`**: Clears ALL handlers, configures root logger, optional 10MB rotating file (5 backups). Emits "Logging initialized" INFO. [FACT: logging.py:133-215]
- **`get_logger(name)`**: Thin wrapper around `logging.getLogger(name)`. [FACT: logging.py:220]
- **`ExperimentLogger`**: Stateful lifecycle tracker. `start()` must precede `end()` for duration. Events accumulate unbounded. [FACT: logging.py:242-380]

---

### `kosmos/core/providers/base.py`

**What it does**: Defines the abstract `LLMProvider` interface and supporting data types (`Message`, `UsageStats`, `LLMResponse`, `ProviderAPIError`) enabling Kosmos to swap between LLM backends via unified API. [FACT: base.py:1-6]

**What's non-obvious**:
- **`LLMResponse` masquerades as str**: Implements 20+ string methods delegating to `self.content`. `isinstance(response, str)` returns False. [FACT: base.py:80-154]
- **String methods return `str`, not `LLMResponse`**: `response.strip()` loses `.usage`, `.model` metadata. [FACT: base.py:107-108]
- **`if False: yield` is load-bearing dead code**: In `generate_stream_async`, removing it changes function from async generator to coroutine, breaking `async for` callers. [FACT: base.py:360-363]
- **`is_recoverable()` has competing heuristics**: Checks flag, then HTTP codes, then message patterns. "timeout" (recoverable) matched before "invalid" (non-recoverable) due to early-return. [FACT: base.py:445-484]
- **`_update_usage_stats` skips `cost_usd=0.0`**: Falsy check means free-tier costs not accumulated. [FACT: base.py:401]
- **Empty content `LLMResponse` is falsy**: `if not response:` treats successful empty response as failure. [FACT: base.py:98-99]

**Blast radius**: Three concrete providers inherit (`AnthropicProvider`, `OpenAIProvider`, `LiteLLMProvider`). `LLMResponse` returned by every `generate()` call system-wide. `ProviderAPIError.is_recoverable()` controls retry behavior everywhere.

**Public API**:
- **`Message` dataclass**: `role`, `content`, optional `name`, `metadata`. [FACT: base.py:18-31]
- **`UsageStats` dataclass**: Token counts, optional cost/model/provider/timestamp. [FACT: base.py:35-54]
- **`LLMResponse` dataclass**: `content` + `usage` + `model` + 20+ string compatibility methods. [FACT: base.py:57-154]
- **`LLMProvider(ABC)`**: Abstract with `generate`, `generate_async`, `generate_with_messages`, `generate_structured`, `get_model_info`. Non-abstract defaults: `generate_stream`, `generate_stream_async` (raise `NotImplementedError`). [FACT: base.py:170-410]
- **`ProviderAPIError(Exception)`**: With `is_recoverable()` heuristic. Default `recoverable=True`. [FACT: base.py:429-484]

---

### `kosmos/agents/research_director.py`

**What it does**: Master orchestrator for autonomous research: drives the full cycle (hypothesize -> design -> execute -> analyze -> refine -> iterate) by coordinating 6+ agents through a workflow state machine, managing convergence, error recovery, and knowledge graph persistence. (See Critical Paths 1-9 for detailed traces through this module.) [FACT: research_director.py:1-12]

**What's non-obvious**:
- **Two coordination mechanisms coexist**: Message-based `_send_to_*` methods AND direct-call `_handle_*_action()` methods. Issue #76 revealed message-based coordination silently failed (agents never registered in router). Direct-call methods are actually used. `_send_to_*` methods are dead code. [FACT: research_director.py:1039-1219, 1391-1979]
- **Constructor does a LOT**: DB init, world model entity creation, skill loading, convergence detector setup, optional parallel/async initialization. Failures caught-and-logged, not raised. [FACT: research_director.py:68-260]
- **Dual locking**: Both `asyncio.Lock` and `threading.RLock/Lock`. Async locks for async paths, threading locks for sync contexts. [FACT: research_director.py:192-200]
- **Lazy agent initialization**: Sub-agents are `None` at init, created on first use. [FACT: research_director.py:145-152]
- **Infinite loop guard**: `MAX_ACTIONS_PER_ITERATION = 50`. Forces `NextAction.CONVERGE` when exceeded. [FACT: research_director.py:50, 2455-2461]
- **Error recovery blocks event loop**: `time.sleep()` during async execution -- [2, 4, 8] seconds. [FACT: research_director.py:674]
- **Circuit breaker at 3 errors**: After 3 consecutive failures, transitions to ERROR state. [FACT: research_director.py:45, 649-662]
- **`_actions_this_iteration` lazily initialized via `hasattr`**: Not in `__init__`. [FACT: research_director.py:2451-2452]
- **4 separate graph persistence methods**: Each opens new DB session, all fire-and-forget (catch-and-log). [FACT: research_director.py:388-562]
- **World model optional**: If `get_world_model()` fails, `self.wm = None`, all graph ops silently no-op. [FACT: research_director.py:242-255]
- **JSON sanitization is inline**: Nested `_json_safe()` handles numpy types by string conversion. [FACT: research_director.py:1595-1613]
- **Sync `_workflow_context()` yields without lock**: No mutual exclusion between sync and async paths. [FACT: research_director.py:376-379]
- **`ExperimentResult` constructed with placeholder metadata**: `start_time=_now, end_time=_now, duration_seconds=0.0`. Analysis code relying on duration gets 0. [FACT: research_director.py:1704-1722]
- **Async LLM client reads `ANTHROPIC_API_KEY` from `os.getenv()` directly**: Bypasses config system. [FACT: research_director.py:228-239]
- **Sequential fallback in `execute_experiments_batch()` uses `run_until_complete()`**: Raises `RuntimeError` if event loop already running. [FACT: research_director.py:2171-2174]

**Blast radius**: CLI `run` command, integration tests, e2e tests all instantiate this class. Changing `execute()` return type breaks CLI and tests. `decide_next_action()` is the brain of the system.

**Public API**:
- **`ResearchDirectorAgent.__init__(research_question, domain, agent_id, config)`**: Full orchestration stack init. Precondition: `research_question` required. [FACT: research_director.py:68-260]
- **`execute(task: Dict)`** [async]: Supports `"start_research"` and `"step"` actions. Raises `ValueError` for unknown. [FACT: research_director.py:2868-2909]
- **`execute_sync(task: Dict)`**: Sync wrapper. [FACT: research_director.py:2911-2920]
- **`decide_next_action()`**: State-machine decision tree with budget/runtime/iteration/convergence checks. [FACT: research_director.py:2388-2548]
- **`get_research_status()`**: Comprehensive status dict. [FACT: research_director.py:2926-2952]

---

### `kosmos/models/result.py`

**What it does**: Defines Pydantic data models for experiment results -- `ExperimentResult`, `StatisticalTestResult`, `VariableResult`, `ExecutionMetadata`, `ResultStatus`, and `ResultExport`. [FACT: result.py:1-6]

**What's non-obvious**:
- **Pydantic models, not database models**: Distinct from SQLAlchemy `ResultModel` in `kosmos.db.models`. Research_director manually constructs these from DB records. [FACT: result.py analysis]
- **`model_to_dict` is a compat shim**: `to_dict()` calls Pydantic v1/v2 compatible serialization. [FACT: result.py:9, 242-243]
- **`export_csv()` imports pandas at call time**: Only pandas dependency in models layer. Crashes if not installed. [FACT: result.py:293]
- **`created_at` captures object creation time**: Uses `datetime.utcnow` default factory, not DB insertion time. [FACT: result.py:203-204]
- **Validators handle both dict and model instances**: `validate_primary_test` handles raw dicts during Pydantic v2 validation. Fragile if ordering changes. [FACT: result.py:217-228]

**Blast radius**: 34 importers. Key consumers: research_director (3 construction sites), data_analyst, hypothesis refiner, convergence, result_collector, feedback, memory, verifier, summarizer, visualization, world_model.

**Public API**:
- **`ExperimentResult(BaseModel)`**: `experiment_id`, `protocol_id`, `status`, `metadata` required. `validate_statistical_tests` enforces unique test names. `validate_primary_test` checks existence. [FACT: result.py:127-228]
- **`ExperimentResult.is_significant(alpha=0.05)`**: Checks `primary_p_value`. Returns False if None. [FACT: result.py:259-263]
- **`ResultExport.export_csv()`**: Requires `pandas`. [FACT: result.py:293]
- **`ResultExport.export_markdown()`**: Crashes with `TypeError` if any `VariableResult` stat is `None`. [FACT: result.py:349-353]

---

### `kosmos/orchestration/` (plan_creator, plan_reviewer, delegation, novelty_detector)

**What it does**: Implements a strategic research planning pipeline: PlanCreatorAgent generates 10-task plans per cycle, NoveltyDetector filters redundant tasks, PlanReviewerAgent validates on 5 dimensions, and DelegationManager executes approved plans by routing to agents in parallel. [FACT: __init__.py:1-26]

**What's non-obvious**:
- **Exploration ratio hardcoded by cycle range**: cycles 1-7 = 70%, 8-14 = 50%, 15-20 = 30%. No config override. [FACT: plan_creator.py:105-121]
- **Falls back to mock planning**: If LLM unavailable, generates deterministic mock tasks. Mock plans pass structural requirements. [FACT: plan_creator.py:146-149, 292-346]
- **JSON parsing is naive**: `find('{')` and `rfind('}')` for extraction. [FACT: plan_creator.py:279-284]
- **Uses raw `anthropic_client.messages.create()` directly**: BOTH PlanCreatorAgent and PlanReviewerAgent bypass the Kosmos LLMProvider. No caching, no cost tracking, no retry. [FACT: plan_creator.py:158-162, plan_reviewer.py:125-129]
- **Structural requirements are hard gates**: >= 3 `data_analysis` tasks AND >= 2 types AND every task needs description/expected_output. Perfect scores fail without these. [FACT: plan_reviewer.py:272-313]
- **Dimension weights defined but NOT used**: Simple arithmetic mean for approval. [FACT: plan_reviewer.py:68-69]
- **Tasks batched sequentially**: Fixed-size batches run in parallel via `asyncio.gather`, but batches are sequential. [FACT: delegation.py:196-219]
- **Agent validation deferred to execution time**: DelegationManager raises `RuntimeError` at task time if agent missing, not at init. [FACT: delegation.py:395-399]
- **NoveltyDetector has no persistence**: Index lives in memory. Lost on restart. [FACT: novelty_detector.py analysis]
- **Graceful fallback to Jaccard similarity**: If `sentence-transformers` not installed. [FACT: novelty_detector.py:72-85]
- **`filter_redundant_tasks` uses copy-restore**: Temporarily modifies then restores internal index. [FACT: novelty_detector.py:320-342]

**Public API**:
- **`PlanCreatorAgent.create_plan(research_objective, context, num_tasks)`**: LLM or mock plan. Falls back on ANY exception. [FACT: plan_creator.py:194-198]
- **`PlanReviewerAgent.review_plan(plan, context)`**: 5 dimensions + structural checks. Falls back to mock review. [FACT: plan_reviewer.py:161-162]
- **`DelegationManager.execute_plan(plan, cycle, context)`** [async]: Parallel batches. Individual failures caught. [FACT: delegation.py:126-250]
- **`NoveltyDetector.check_task_novelty(task)`**: Returns `is_novel`, `novelty_score`, `similar_tasks`. [FACT: novelty_detector.py:140+]
- **`NoveltyDetector.filter_redundant_tasks(tasks)`**: Returns only novel tasks with temporary indexing. [FACT: novelty_detector.py:320-342]

**Also in orchestration:** `StageOrchestrator` (`kosmos/orchestration/stage_orchestrator.py`) provides a higher-level research loop abstraction with stage-based execution: plan creation -> review -> delegation -> convergence check. It wraps `PlanCreatorAgent`, `PlanReviewerAgent`, and `DelegationManager` into a single `run_cycle()` method. This is an alternative to the `ResearchDirectorAgent`'s direct orchestration and is used by the `research_loop.py` workflow module. [PATTERN: observed in stage_orchestrator.py and research_loop.py]

---

### `kosmos/knowledge/vector_db.py`

**What it does**: Wraps ChromaDB for persistent vector storage and cosine-similarity search for scientific papers, handling SPECTER embedding computation, batched insertion, and metadata extraction. [FACT: vector_db.py:1-5]

**What's non-obvious**:
- **ChromaDB is optional**: Catches `ImportError`, sets `HAS_CHROMADB = False`. Constructor completes but all operations return empty results or no-op. [FACT: vector_db.py:19-27, 62-67]
- **Distance-to-similarity assumes cosine**: `1 - distance`. Wrong if distance metric changed. [FACT: vector_db.py:99, 239]
- **Singleton is mutable and not thread-safe**: `get_vector_db()` module-global with no lock. [FACT: vector_db.py:443-477]
- **Title truncated to 500 chars**: ChromaDB metadata size limits. [FACT: vector_db.py:403]
- **Abstract truncated to 1000 chars**: Stored as `title [SEP] abstract`. Long abstracts lose information. [FACT: vector_db.py:437-440]
- **`search_by_paper` requests `top_k + 1`**: Accounts for self-match filtering. [FACT: vector_db.py:275]
- **`add_papers` requires numpy array**: `embeddings[i:batch_end].tolist()` fails on Python lists. [FACT: vector_db.py:176]

**Blast radius**: Embedding dimension must match SPECTER (768-dim). Paper ID format is `"{source}:{primary_identifier}"`. Persist directory from config. `[SEP]` separator in stored documents.

**Public API**:
- **`PaperVectorDB.__init__(collection_name, persist_directory, reset)`**: Connects ChromaDB, initializes SPECTER embedder (may download ~440MB). [FACT: vector_db.py:45-100]
- **`add_papers(papers, embeddings, batch_size=100)`**: Computes embeddings if not provided. Writes to ChromaDB. [FACT: vector_db.py:140-180]
- **`search(query, top_k=10, filters)`**: Embeds query, returns results with similarity scores. [FACT: vector_db.py:200-250]
- **`clear()`**: Deletes and recreates collection. No null guard on `self.client` -- raises `AttributeError` if ChromaDB unavailable. [FACT: vector_db.py:370-371]
- **`get_vector_db()`**: Module-level singleton factory. Not thread-safe. [FACT: vector_db.py:443-477]

---

### `kosmos/core/workflow.py`

**What it does**: Defines the research workflow state machine -- 9 states, allowed transitions, and the `ResearchPlan` data structure tracking hypotheses, experiments, and results across iterations. [FACT: workflow.py:1-7]

**What's non-obvious**:
- **State machine not enforced at type level**: `current_state` is public. `transition_to()` validates but nothing prevents bypass. [FACT: workflow.py:319]
- **`ResearchPlan` duplicates state**: `ResearchPlan.current_state` and `ResearchWorkflow.current_state` can diverge. Sync only happens inside `transition_to()`. [FACT: workflow.py:323-325]
- **ID-based tracking only**: Lists of string IDs, not objects. No DB knowledge. [FACT: workflow.py:68-78]
- **`PAUSED` can resume to almost any active state** (6 targets): Soft reset. [FACT: workflow.py:214-221]
- **`CONVERGED` can restart**: Transition to `GENERATING_HYPOTHESES` allowed. Not truly terminal. (See Gotcha 30.) [FACT: workflow.py:212-213]
- **Transition logging is config-gated**: Deferred import, wrapped in try/except. Silent if config unavailable. [FACT: workflow.py:293-308]
- **`use_enum_values=True`**: Enum fields stored as strings, not instances. `isinstance` checks against enum types fail after serialization round-trip. [FACT: workflow.py:48, 60]
- **`get_untested_hypotheses()` is O(n*m)**: List comprehension with `tested_hypotheses` as list, not set. Called repeatedly by director. [FACT: workflow.py:149-151]

**Blast radius**: 32 importers. Changing `WorkflowState` enum breaks research_director, all tests, CLI. `ALLOWED_TRANSITIONS` changes affect research flow behavior. `ResearchPlan` fields read extensively by director.

**Public API**:
- **`WorkflowState(str, Enum)`**: 9 states. [FACT: workflow.py:18-29]
- **`NextAction(str, Enum)`**: 8 actions. [FACT: workflow.py:32-43]
- **`ResearchPlan(BaseModel)`**: `research_question` required. ID-based tracking with dedup. [FACT: workflow.py:57-163]
- **`ResearchWorkflow`**: State machine with `transition_to()` (raises `ValueError` on invalid), `can_transition_to()`, `reset()`, `get_state_statistics()`. [FACT: workflow.py:166-416]

---

### `kosmos/world_model/` (interface, models, factory, simple, in_memory, artifacts)

**What it does**: Provides a persistent knowledge graph for accumulating research findings across sessions using a Strategy pattern with two implementations (Neo4j-backed and in-memory fallback), a singleton factory, and an Adapter wrapping `KnowledgeGraph`. [FACT: world_model analysis]

**What's non-obvious**:
- **`WorldModelStorage` ABC defines 10+ abstract methods**: Separate `EntityManager` and `ProvenanceTracker` ABCs (not part of `WorldModelStorage`). [FACT: interface.py:36-513]
- **Entity type validation is advisory**: Non-standard types trigger `warnings.warn()` but are NOT rejected. [FACT: models.py:160-166]
- **Factory methods use `getattr()` extensively**: Handle both Pydantic and SQLAlchemy objects. [FACT: models.py:257]
- **`get_world_model()` is NOT thread-safe**: No lock guards the singleton. [FACT: factory.py:38]
- **Silent fallback to in-memory**: If Neo4j down, switches silently. Data lost on restart. Only a log warning signals this. [FACT: factory.py:123-133]
- **Neo4j adapter shares singleton with literature knowledge graph**: `self.graph = get_knowledge_graph()` -- same Neo4j connection. [FACT: simple.py:89]
- **Entity type bifurcation**: Standard types (Paper, Concept, Author, Method) use optimized `KnowledgeGraph` methods with indexes. Research types (Hypothesis, Finding) use raw node creation. [FACT: simple.py analysis]
- **`InMemoryWorldModel` query is O(R)**: Linear scan of all relationships. [FACT: in_memory.py:96-122]
- **`ArtifactStateManager` is separate from `WorldModelStorage`**: 4-layer hybrid (JSON files + optional graph + optional vector + citation tracking). Not auto-wired. [FACT: artifacts.py:146-727, 164-169]
- **Vector store Layer 3 is a stub**: `pass` at line 567. [FACT: artifacts.py:560-567]
- **`UpdateType` enum**: CONFIRMATION, CONFLICT, PRUNING -- the paper's three update categories. [FACT: artifacts.py:37-47]
- **Conflict detection is statistical**: Checks effect direction, p-value significance, hypothesis refutation. [FACT: artifacts.py:573-661]
- **`reset_knowledge_graph()` does not close existing connection**: Just sets global to None, leaking Neo4j connection. [FACT: world_model analysis]
- **Two overlapping graph systems**: `KnowledgeGraph` (literature-focused) and `WorldModelStorage` (research-focused) with adapter bridging them. [FACT: world_model analysis]

**Blast radius**: Research Director is primary consumer. Entity factory methods (from_hypothesis, from_protocol, from_result) used for all persistence. Singleton threading issues affect all callers.

**Public API**:
- **`Entity` dataclass**: 10 fields, 11 valid types, factory methods `from_hypothesis()`, `from_protocol()`, `from_result()`, `from_research_question()`. [FACT: models.py:72-341]
- **`Relationship` dataclass**: 8 fields, 12 valid types, `with_provenance()` classmethod. [FACT: models.py:461-667]
- **`get_world_model()`**: Singleton factory. Tries Neo4j, falls back to in-memory. Not thread-safe. [FACT: factory.py:55-155]
- **`ArtifactStateManager`**: JSON file artifacts in `artifacts/cycle_N/task_M_finding.json`. Optional graph and vector store integration. [FACT: artifacts.py:146-727]

---

The Module Behavioral Index above documents the runtime behavior and non-obvious characteristics of each core module. The Key Interfaces section below provides the exact method signatures and contracts that agents and callers depend on.

## Key Interfaces

### BaseAgent -- Foundation for All Agents
```python
# kosmos/agents/base.py
class AgentMessage(BaseModel):
    from_agent: str
    to_agent: str
    content: Dict[str, Any]
    message_type: MessageType  # REQUEST, RESPONSE, NOTIFICATION, ERROR
    correlation_id: Optional[str]
    timestamp: datetime
    metadata: Dict[str, Any]
    def to_dict(self) -> Dict: ...       # Serializes with ISO timestamp string [FACT: base.py:69-80]
    def to_json(self) -> str: ...        # json.dumps(self.to_dict()); raises TypeError if content non-serializable [FACT: base.py:82-84]

class BaseAgent:
    def __init__(self, agent_id=None, agent_type=None, config=None): ...
        # Auto-generates UUID if no agent_id; creates BOTH sync list queue (message_queue) AND async queue (_async_message_queue) [FACT: base.py:113-153]
    def start(self) -> None: ...         # CREATED -> STARTING -> RUNNING; one-shot, silently ignores if already started [FACT: base.py:159-175]
    def stop(self) -> None: ...          # Transitions to STOPPED from ANY status (no guard) [FACT: base.py:177-187]
    def pause(self) -> None: ...         # RUNNING -> PAUSED; warns and returns on wrong state [FACT: base.py:189-195]
    def resume(self) -> None: ...        # PAUSED -> RUNNING; warns and returns on wrong state [FACT: base.py:197-205]
    def is_running(self) -> bool: ...    # True only if RUNNING [FACT: base.py:207-209]
    def is_healthy(self) -> bool: ...    # True if RUNNING, IDLE, or WORKING; subclasses can override [FACT: base.py:211-217]
    def get_status(self) -> Dict: ...    # Returns agent metadata, health, stats, sync queue length [FACT: base.py:219-240]
    async def send_message(self, to_agent, content, message_type, correlation_id) -> AgentMessage: ...
        # Constructs message, increments counter, routes via _message_router if set; routing errors caught, not raised [FACT: base.py:246-300]
    def send_message_sync(self, ...) -> AgentMessage: ...  # 30s hardcoded timeout [FACT: base.py:302-327]
    async def receive_message(self, message: AgentMessage) -> None: ...
        # Appends to BOTH queues, calls process_message(); sends ERROR response on processing failure [FACT: base.py:329-367]
    async def process_message(self, message: AgentMessage) -> None: ...
        # Default: logs warning. Subclasses MUST override. [FACT: base.py:382-391]
    def register_message_handler(self, message_type, handler) -> None: ...
        # Stores handler but process_message() does NOT dispatch to it -- dead code unless subclass uses it [FACT: base.py:406-415]
    def set_message_router(self, router: Union[Callable, Callable[..., Awaitable]]) -> None: ...
        # Accepts sync or async callable; router checked via asyncio.iscoroutine() at call time [FACT: base.py:417-433]
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]: ...
        # Raises NotImplementedError; subclasses must override [FACT: base.py:485-497]
    def get_state(self) -> AgentState: ...     # Returns Pydantic model; side-effect: updates self.updated_at [FACT: base.py:439-454]
    def restore_state(self, state) -> None: ... # Overwrites all identity/state fields from saved state [FACT: base.py:456-470]
    def save_state_data(self, key, value) -> None: ...  # key-value in self.state_data; updates updated_at [FACT: base.py:472-475]
    def get_state_data(self, key, default=None) -> Any: ... # Pure query [FACT: base.py:477-479]
```
[PATTERN: 6 subclasses inherit from BaseAgent: ResearchDirector, HypothesisGenerator, ExperimentDesigner, DataAnalyst, LiteratureAnalyzer, StageOrchestrator]

[PATTERN] Two of 5 agents have execute() signatures incompatible with the base class contract:
| Agent | Signature | Base Contract |
|-------|-----------|---------------|
| `HypothesisGeneratorAgent` | `execute(self, message: AgentMessage) -> AgentMessage` | `execute(self, task: Dict) -> Dict` |
| `ExperimentDesignerAgent` | `execute(self, message: AgentMessage) -> AgentMessage` | `execute(self, task: Dict) -> Dict` |
| `DataAnalystAgent` | `execute(self, task: Dict) -> Dict` | matches |
| `LiteratureAnalyzerAgent` | `execute(self, task: Dict) -> Dict` | matches |
| `ResearchDirectorAgent` | `async execute(self, task: Dict) -> Dict` | matches (async variant) |
[FACT: base.py:485-497, agent_communication finding Section 4]

In practice, none of these `execute()` methods are called in the main loop. The director calls domain-specific methods directly (e.g., `generate_hypotheses()`, `design_experiment()`, `interpret_results()`). [PATTERN: observed in all 5 direct-call handlers]

---

### ResearchDirectorAgent -- Central Orchestrator
```python
# kosmos/agents/research_director.py
class ResearchDirectorAgent(BaseAgent):
    def __init__(self, research_question, domain=None, agent_id=None, config=None): ...
        # Initializes workflow, research plan, LLM client, convergence detector, rollout tracker, optional parallel executor, optional async LLM, world model entity.
        # Side effects: initializes database (catch-and-log on failure). Creates ResearchQuestion entity in world model.
        # Error: catches and logs most init errors; continues with degraded functionality (no world model, no parallel, no async LLM). [FACT: research_director.py:68-260]
        # Lazy agent slots (all None at init): _hypothesis_agent, _experiment_designer, _code_generator, _code_executor, _data_provider, _data_analyst, _hypothesis_refiner [FACT: research_director.py:144-152]
        # Dual locking: asyncio.Lock (async) AND threading.RLock/Lock (sync) [FACT: research_director.py:192-200]
    async def execute(self, task: Dict) -> Dict: ...
        # Supports "start_research" and "step" actions. Raises ValueError for unknown actions. [FACT: research_director.py:2868-2909]
    def execute_sync(self, task: Dict) -> Dict: ...
        # Sync wrapper: tries running event loop first, falls back to asyncio.run() [FACT: research_director.py:2911-2920]
    def decide_next_action(self) -> NextAction: ...
        # State-machine-based decision tree. Checks budget, runtime, iteration limits, convergence. Side-effect: increments _actions_this_iteration. [FACT: research_director.py:2388-2548]
    async def process_message(self, message: AgentMessage) -> None: ...
        # Routes by metadata["agent_type"] to type-specific handlers [FACT: research_director.py:568-593]
    def get_research_status(self) -> Dict: ...
        # Returns question, domain, state, iteration, convergence, counts, strategy stats, rollouts, agent status [FACT: research_director.py:2926-2952]
    def generate_research_plan(self) -> str: ...
        # Uses LLM to generate initial strategy. Stores in research_plan.initial_strategy. [FACT: research_director.py:2349-2382]
    def register_agent(self, agent_type, agent_id) -> None: ...  # Agent registry, unused by direct-call pattern (Issue #76) [FACT: research_director.py:2841-2862]
    def get_agent_id(self, agent_type) -> Optional[str]: ...
    def execute_experiments_batch(self, protocol_ids) -> List[Dict]: ...
        # Parallel execution, falls back to sequential if parallel executor unavailable [FACT: research_director.py:2152-2204]
    async def evaluate_hypotheses_concurrently(self, hypothesis_ids) -> List[Dict]: ...
        # Concurrent LLM-based evaluation. Requires async LLM client. [FACT: research_director.py:2206-2275]
    async def analyze_results_concurrently(self, result_ids) -> List[Dict]: ...
        # Concurrent LLM-based analysis. Requires async LLM client. [FACT: research_director.py:2277-2343]
```

---

### LLM Provider Layer
```python
# kosmos/core/providers/base.py
@dataclass
class Message:
    role: str                      # "user", "assistant", "system"
    content: str
    name: Optional[str] = None
    metadata: Optional[Dict] = None
    # Plain data container, no methods beyond dataclass defaults [FACT: base.py:18-31]

@dataclass
class UsageStats:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    timestamp: Optional[datetime] = None
    # [FACT: base.py:35-54]

@dataclass
class LLMResponse:
    content: str
    usage: UsageStats
    model: str
    finish_reason: Optional[str] = None
    raw_response: Optional[Any] = None
    metadata: Optional[Dict] = None
    # Implements 20+ string methods delegating to self.content (strip, lower, split, replace, find, __contains__, __len__, __iter__, etc.)
    # isinstance(response, str) returns False. Chaining (response.strip().lower()) returns plain str, losing metadata. [FACT: base.py:80-154]
    def __bool__(self) -> bool: ...  # Returns bool(self.content) -- empty content is falsy [FACT: base.py:98-99]

class LLMProvider(ABC):
    def __init__(self, config: Dict): ...
        # Derives provider_name from class name by stripping "Provider" suffix. Zeroes usage counters. [FACT: base.py:179-195]
    @abstractmethod
    def generate(self, prompt, system=None, max_tokens=4096, temperature=0.7, stop_sequences=None, **kwargs) -> LLMResponse: ...
        # Sync text generation. Raises ProviderAPIError. [FACT: base.py:197-224]
    @abstractmethod
    async def generate_async(self, prompt, system=None, max_tokens=4096, temperature=0.7, **kwargs) -> LLMResponse: ...
        # Async variant, same contract. [FACT: base.py:226-253]
    @abstractmethod
    def generate_with_messages(self, messages: List[Message], max_tokens=4096, temperature=0.7, **kwargs) -> LLMResponse: ...
        # Multi-turn from List[Message]. [FACT: base.py:255-278]
    @abstractmethod
    def generate_structured(self, prompt, schema: Dict, system=None, max_tokens=4096, **kwargs) -> Dict[str, Any]: ...
        # Returns parsed JSON dict. Raises ProviderAPIError or JSONDecodeError. [FACT: base.py:280-308]
    def generate_stream(self, prompt, system=None, max_tokens=4096, **kwargs) -> Iterator[str]: ...
        # Non-abstract default raises NotImplementedError. [FACT: base.py:310-334]
    async def generate_stream_async(self, prompt, system=None, max_tokens=4096, **kwargs) -> AsyncIterator[str]: ...
        # Non-abstract default raises NotImplementedError. Has load-bearing "if False: yield" dead code. [FACT: base.py:336-363]
    def get_usage_stats(self) -> Dict: ...    # Accumulated usage (instance-level only). [FACT: base.py:375-389]
    @abstractmethod
    def get_model_info(self) -> Dict: ...     # Model metadata (name, max_tokens, cost rates). [FACT: base.py:365-373]
    def _update_usage_stats(self, usage: UsageStats) -> None: ...
        # Increments counters. Skips cost when cost_usd is exactly 0.0 (falsy). [FACT: base.py:391-402]
    def reset_usage_stats(self) -> None: ...  # Zeroes all usage counters. [FACT: base.py:404-410]

class ProviderAPIError(Exception):
    def __init__(self, provider, message, status_code=None, raw_error=None, recoverable=True): ...
        # Default recoverable=True. [FACT: base.py:429-443]
    def is_recoverable(self) -> bool: ...
        # Multi-stage: explicit flag -> HTTP status (4xx except 429 = non-recoverable) -> message patterns -> default True.
        # Order-dependent: recoverable patterns checked before non-recoverable patterns. [FACT: base.py:445-484]
```
[PATTERN: 3 concrete providers inherit from LLMProvider: AnthropicProvider, OpenAIProvider, LiteLLMProvider. FACT: anthropic.py:36, openai.py:32, litellm_provider.py:40]

---

### ClaudeClient -- Legacy Direct Anthropic Client
```python
# kosmos/core/llm.py
class ModelComplexity:
    @staticmethod
    def estimate_complexity(prompt, system=None) -> Dict: ...
        # Returns complexity_score (0-100), recommendation ("haiku" or "sonnet" -- never higher than sonnet). [FACT: llm.py:52-105]

class ClaudeClient:
    def __init__(self, api_key=None, model=None, enable_auto_model_selection=True, enable_caching=True): ...
        # CLI mode: api_key.replace('9', '') == '' triggers CLI routing (undocumented). Raises ImportError (no anthropic), ValueError (no key). [FACT: llm.py:154-179]
    def generate(self, prompt, system=None, max_tokens=4096, temperature=0.7, stop_sequences=None, bypass_cache=False, model_override=None) -> str: ...
        # Checks cache first. Auto-selects model if enabled (disabled in CLI mode). [FACT: llm.py:207-365]
    def generate_with_messages(self, messages, system=None, max_tokens=4096, temperature=0.7) -> str: ...
        # No cache. No auto model selection. Always uses self.model. [FACT: llm.py:367-408]
    def generate_structured(self, prompt, output_schema=None, system=None, max_tokens=4096, temperature=0.5, max_retries=2, schema=None) -> Dict: ...
        # Retries JSON parsing (max_retries+1 total). bypass_cache on retry. Raises ProviderAPIError on exhaustion. schema is alias for output_schema. [FACT: llm.py:410-486]
    def get_usage_stats(self) -> Dict: ...   # Cost hardcodes "claude-sonnet-4-5" model name regardless of actual model used [FACT: llm.py:488-578, llm.py:519]
    def reset_stats(self) -> None: ...       # Zeroes all counters [FACT: llm.py:596-605]

def get_client(reset=False, use_provider_system=True) -> Union[ClaudeClient, LLMProvider]: ...
    # Thread-safe singleton (double-checked locking). use_provider_system=True returns LLMProvider from config, fallback to AnthropicProvider. use_provider_system=False returns ClaudeClient.
    # reset=True replaces singleton for ALL threads. [FACT: llm.py:613-679]

def get_provider() -> LLMProvider: ...
    # Calls get_client(use_provider_system=True), asserts result is LLMProvider. Raises TypeError if ClaudeClient. [FACT: llm.py:682-706]
```
[FACT: llm.py:609] The global `_default_client` is `Optional[Union[ClaudeClient, LLMProvider]]` -- callers that expect one type may get the other depending on config and `use_provider_system` flag.

---

### Workflow State Machine
```python
# kosmos/core/workflow.py
class WorkflowState(str, Enum):
    INITIALIZING = "initializing"
    GENERATING_HYPOTHESES = "generating_hypotheses"
    DESIGNING_EXPERIMENTS = "designing_experiments"
    EXECUTING = "executing"
    ANALYZING = "analyzing"
    REFINING = "refining"
    CONVERGED = "converged"       # NOT terminal: can transition back to GENERATING_HYPOTHESES [FACT: workflow.py:212-213]
    PAUSED = "paused"             # Can resume to 6 different states (soft reset) [FACT: workflow.py:214-221]
    ERROR = "error"
    # [FACT: workflow.py:18-29]

class NextAction(str, Enum):
    # 8 actions: GENERATE_HYPOTHESIS, DESIGN_EXPERIMENT, EXECUTE_EXPERIMENT, ANALYZE_RESULT, REFINE_HYPOTHESIS, CONVERGE, PAUSE, ERROR_RECOVERY [FACT: workflow.py:32-43]

class ResearchPlan(BaseModel):
    research_question: str         # Required
    domain: Optional[str]
    hypothesis_pool: List[str]     # IDs only, not objects
    tested_hypotheses: List[str]
    supported_hypotheses: List[str]
    rejected_hypotheses: List[str]
    experiment_queue: List[str]
    completed_experiments: List[str]
    results: List[str]
    iteration_count: int
    max_iterations: int
    has_converged: bool
    current_state: str             # Synced from workflow ONLY inside transition_to() [FACT: workflow.py:323-325]
    # use_enum_values=True means enum fields stored as strings, not enum instances [FACT: workflow.py:60]
    def add_hypothesis(self, hypothesis_id) -> None: ...    # Append-only with dedup [FACT: workflow.py:100-104]
    def get_untested_hypotheses(self) -> List[str]: ...      # O(n*m) -- list, not set [FACT: workflow.py:149-151]

class ResearchWorkflow:
    current_state: WorkflowState   # Public attribute -- can be bypassed without transition_to() [FACT: workflow.py:319]
    def can_transition_to(self, target_state) -> bool: ...   # Checks ALLOWED_TRANSITIONS [FACT: workflow.py:247-258]
    def transition_to(self, target_state, action="", metadata=None) -> bool: ...
        # Validates, records WorkflowTransition, syncs research_plan.current_state. Raises ValueError on invalid. [FACT: workflow.py:260-328]
    def reset(self) -> None: ...                             # Returns to INITIALIZING, clears history [FACT: workflow.py:342-349]
    def to_dict(self) -> Dict: ...                           # Exports state + last 5 transitions [FACT: workflow.py:351-365]
    def get_state_duration(self, state) -> float: ...        # Total seconds in a state via history scan [FACT: workflow.py:367-396]
```

---

### Code Execution Layer
```python
# kosmos/execution/executor.py
class ExecutionResult:
    def __init__(self, success, return_value=None, stdout="", stderr="", error=None, error_type=None,
                 execution_time=0.0, profile_result=None, data_source=None): ...
        # Data container [FACT: executor.py:113-136]
    def to_dict(self) -> Dict: ...  # Includes profile_data if available, silent fallback on serialization failure [FACT: executor.py:138-159]

class CodeExecutor:
    def __init__(self, max_retries=3, retry_delay=1.0, allowed_globals=None, use_sandbox=True,
                 sandbox_config=None, enable_profiling=False, profiling_mode="basic",
                 test_determinism=False, execution_timeout=300): ...
        # Creates RetryStrategy, optionally DockerSandbox and RExecutor. Graceful degradation. [FACT: executor.py:174-235]
    def execute(self, code, local_vars=None, retry_on_error=True, llm_client=None, language="python") -> ExecutionResult: ...
        # Auto-detects language. Retry loop with code modification on failure. time.sleep() between retries (blocks in async). Returns failure result rather than raising. [FACT: executor.py:237-376]
    def execute_r(self, code, capture_results=True, output_dir=None) -> ExecutionResult: ...
        # R execution. Returns failure result if R unavailable. [FACT: executor.py:409-452]
    def execute_with_data(self, code, data_path, retry_on_error=True) -> ExecutionResult: ...
        # Injects data_path twice: prepended to code AND passed as local var [FACT: executor.py:653-660]

class RetryStrategy:
    def __init__(self, max_retries=3, base_delay=1.0): ...   # Tracks repair_stats per error type [FACT: executor.py:699-715]
    def should_retry(self, attempt, error_type) -> bool: ... # False for SyntaxError, FileNotFoundError, DataUnavailableError [FACT: executor.py:717-730]
    def get_delay(self, attempt) -> float: ...                # base_delay * 2^(attempt-1) [FACT: executor.py:732-734]
    def modify_code_for_retry(self, original_code, error, error_type, traceback_str, attempt, llm_client=None) -> Optional[str]: ...
        # LLM repair on attempts 1-2 only; then pattern-based fixes. Handles 11 error types. [FACT: executor.py:751-825]

def execute_protocol_code(code, data_path=None, max_retries=3, use_sandbox=True, sandbox_config=None) -> Dict: ...
    # Always validates safety via CodeValidator first. Creates fresh CodeExecutor per call. [FACT: executor.py:1017-1066]
```

---

### Code Generation Layer
```python
# kosmos/execution/code_generator.py
class CodeTemplate:
    def __init__(self, name, experiment_type): ...            # Base template [FACT: code_generator.py:27-37]
    def matches(self, protocol) -> bool: ...                  # Default: checks experiment_type equality [FACT: code_generator.py:39-41]
    def generate(self, protocol) -> str: ...                  # Raises NotImplementedError [FACT: code_generator.py:43-45]
    # 5 concrete subclasses: TTestComparisonCodeTemplate, CorrelationAnalysisCodeTemplate, LogLogScalingCodeTemplate, MLExperimentCodeTemplate, GenericComputationalCodeTemplate
    # Registration order determines priority: first match wins [FACT: code_generator.py:787-793]

class ExperimentCodeGenerator:
    def __init__(self, use_templates=True, use_llm=True, llm_enhance_templates=False, llm_client=None): ...
        # Double fallback LLM init: ClaudeClient -> LiteLLMProvider -> disabled. [FACT: code_generator.py:741-783]
    def generate(self, protocol) -> str: ...
        # Template match -> LLM generation -> basic fallback. Validates syntax. Raises ValueError on syntax error. [FACT: code_generator.py:797-833]
    def _validate_syntax(code) -> None: ...  # [static] Raises ValueError (NOT SyntaxError) on failure [FACT: code_generator.py:981-989]
    def save_code(self, code, file_path) -> None: ...  # Writes to filesystem [FACT: code_generator.py:991-995]
```

---

### Code Safety Layer
```python
# kosmos/safety/code_validator.py
class CodeValidator:
    def __init__(self, ethical_guidelines_path=None, allow_file_read=True, allow_file_write=False, allow_network=False): ...
        # Loads ethical guidelines from JSON or defaults. [FACT: code_validator.py:58-85]
    def validate(self, code, context=None) -> SafetyReport: ...
        # 6 sequential checks: syntax, dangerous imports, dangerous patterns, network ops, AST calls, ethical guidelines. passed=True only if zero violations. [FACT: code_validator.py:159-231]
    def requires_approval(self, report) -> bool: ...
        # True if: config mandates, risk HIGH/CRITICAL, critical violations, or ethical violations. [FACT: code_validator.py:436-465]
    def create_approval_request(self, code, report, context) -> ApprovalRequest: ...
        # Code truncated to 500 chars in approval context [FACT: code_validator.py:467-515]
```

---

### Orchestration Layer
```python
# kosmos/orchestration/plan_creator.py
class PlanCreatorAgent:
    def __init__(self, anthropic_client, model, default_num_tasks=10, temperature=0.7): ...
    def create_plan(self, research_objective, context, num_tasks=None) -> ResearchPlan: ...
        # LLM or mock fallback. Falls back on ANY exception. [FACT: plan_creator.py:146-198]
        # Uses raw anthropic_client.messages.create() -- bypasses provider layer [FACT: plan_creator.py:158-162]
    def revise_plan(self, original_plan, review_feedback, context) -> ResearchPlan: ...
        # Regenerates with feedback. Falls back to mock via create_plan. [FACT: plan_creator.py]

# kosmos/orchestration/plan_reviewer.py
class PlanReviewerAgent:
    def review_plan(self, plan, context) -> PlanReview: ...
        # 5 dimension scores (0-10) + structural requirements (hard gates). Falls back to mock on ANY exception.
        # Also uses raw anthropic_client.messages.create() [FACT: plan_reviewer.py:125-129, 161-162]
        # Dimension weights defined but NOT used (simple mean instead). [FACT: plan_reviewer.py:68-69]

# kosmos/orchestration/delegation.py
class DelegationManager:
    def __init__(self, max_parallel_tasks=3, max_retries=2, task_timeout=300, agents=None): ...
        # agents dict maps task-type keys to agent instances. No init-time validation. [FACT: delegation.py:100]
    async def execute_plan(self, plan, cycle, context) -> Dict: ...
        # Tasks batched sequentially (batch_size=3), each batch in parallel via asyncio.gather(return_exceptions=True).
        # Retry: exponential backoff min(2^attempt, 8)s. Checks is_recoverable(). [FACT: delegation.py:126-345]

# kosmos/orchestration/novelty_detector.py
class NoveltyDetector:
    def __init__(self, novelty_threshold=0.75, model_name="all-MiniLM-L6-v2", use_sentence_transformers=True): ...
        # Falls back to Jaccard similarity if sentence-transformers unavailable. [FACT: novelty_detector.py:72-85]
    def index_past_tasks(self, tasks: List[Dict]) -> None: ...    # Appends to in-memory index [FACT: novelty_detector.py]
    def check_task_novelty(self, task: Dict) -> Dict: ...         # Returns is_novel, novelty_score, max_similarity, similar_tasks [FACT: novelty_detector.py]
    def filter_redundant_tasks(self, tasks, keep_most_novel=True) -> List[Dict]: ...
        # Temporary copy-restore pattern to avoid index mutation [FACT: novelty_detector.py:320-342]
```

---

### Communication Architecture Summary

The active communication pattern is **direct-call, not message-passing** (Issue #76):

```
                      ResearchDirectorAgent
                      (hub / orchestrator)
                              |
                decide_next_action() -> state machine
                              |
          +--------+----------+----------+---------+
          |        |          |          |         |
HypothesisGen  ExpDesigner  CodeExecutor  DataAnalyst  HypRefiner
(direct call)  (direct call) (direct call) (direct call) (direct call)
          |        |          |          |         |
          +--------+----------+----------+---------+
                              |
                      SQLAlchemy DB
                   (shared via IDs)
```

[FACT: research_director.py:1039-1219] The `_send_to_*` message-based methods are kept but effectively dead code.
[FACT: research_director.py:1391-1979] The `_handle_*_action()` direct-call methods are the ones actually used.
[ABSENCE] No peer-to-peer agent communication exists in the active code path.
[ABSENCE] `MemoryStore` (`core/memory.py:66`) and `FeedbackLoop` (`core/feedback.py:76`) are designed but not integrated into any agent. `MemoryStore` stores success/failure patterns, dead ends, and insights with experiment deduplication. Neither is imported or used by `ResearchDirectorAgent` or any other active agent. These are infrastructure for future agent learning, not current functionality.
## Error Handling Strategy

**Dominant pattern:** Catch-log-degrade -- catch broad `Exception`, log via `logger.error()` or `logger.warning()`, return a degraded result (empty list, None, dict with error key, or failure status object). Errors generally do NOT propagate upward as exceptions; they are converted to return values at each boundary. [PATTERN: observed in 364 `except Exception as e:` sites across 102 files, plus 38 bare `except Exception:` across 22 files]

**Retry strategy:** Three distinct retry implementations, all using exponential backoff:

1. **Code execution retry** (`execution/executor.py`): Self-correcting -- `RetryStrategy.modify_code_for_retry()` analyzes error type and applies automatic fixes (11 error types handled: KeyError, FileNotFoundError, NameError, TypeError, IndexError, AttributeError, ValueError, ZeroDivisionError, ImportError/ModuleNotFoundError, PermissionError, MemoryError). LLM-based repair on attempts 1-2 only, then pattern-based. Backoff: `base_delay * 2^(attempt-1)`, `max_retries=3`, `base_delay=1.0`. Non-retryable: SyntaxError, FileNotFoundError, DataUnavailableError. [FACT: executor.py:667-825]

2. **Task delegation retry** (`orchestration/delegation.py`): Exponential backoff `min(2^attempt, 8)` seconds, `max_retries=2` (3 total attempts). Checks `ProviderAPIError.is_recoverable()` to skip retries on non-recoverable errors. [FACT: delegation.py:280-345]

3. **LLM API retry with circuit breaker** (`core/async_llm.py`): Uses `tenacity` library (optional) with `wait_exponential(min=1, max=30)`, `stop_after_attempt(3)`. Circuit breaker: CLOSED/OPEN/HALF_OPEN states, `failure_threshold=5`, `reset_timeout=30s`, `half_open_max_calls=2`. On OPEN, all requests immediately rejected. Failure in HALF_OPEN re-opens immediately. [FACT: async_llm.py:58-120, 429-462]

4. **JSON parse retry** (`core/llm.py`): `ClaudeClient.generate_structured()` retries with `max_retries=2`. On `JSONParseError`, bypasses cache (`bypass_cache=attempt > 0`) and re-calls the API. Separate from tenacity retry. [FACT: llm.py:460-486]

5. **Research Director error recovery** (`agents/research_director.py`): Application-level recovery. Uses `ERROR_BACKOFF_SECONDS = [2, 4, 8]` with `MAX_CONSECUTIVE_ERRORS = 3` (circuit breaker). Distinguishes recoverable (backoff + re-enter decide_next_action()) from non-recoverable (skip to next action). Error history maintained as list of dicts with full context. [FACT: research_director.py:45-46, 599-698]

**Recoverability classification** -- `ProviderAPIError.is_recoverable()` is the central oracle:
- **Recoverable**: timeout, connection, network, rate_limit, overloaded, service_unavailable, HTTP 429/502/503/504
- **Non-recoverable**: json parse, invalid, authentication, unauthorized, forbidden, not found, bad request, HTTP 400/401/403/404
- **Default**: unknown errors treated as recoverable
[FACT: core/providers/base.py:445-484]

**Custom Exception Hierarchy:**

| Exception Class | File | Purpose |
|---|---|---|
| `ProviderAPIError` | `core/providers/base.py:417` | Provider API failures with recoverability flag and `is_recoverable()` heuristic |
| `JSONParseError` | `core/utils/json_parser.py:21` | LLM response JSON parsing failures |
| `APIError` | `core/async_llm.py:23` | Anthropic SDK API errors (conditional import) |
| `APITimeoutError` | `core/async_llm.py:26` | Anthropic SDK timeout errors (conditional import) |
| `RateLimitError` | `core/async_llm.py:29` | Anthropic SDK rate limit errors (conditional import) |
| `CacheError` | `core/cache.py:22` | Cache operation failures |
| `BudgetExceededError` | `core/metrics.py:63` | Budget limit exceeded -- carries structured cost data (`current_cost`, `limit`, `usage_percent`) |
| `LiteratureCacheError` | `literature/cache.py:19` | Literature cache operation failures |
| `PDFExtractionError` | `literature/pdf_extractor.py:22` | PDF extraction failures |

**Graceful degradation via optional imports:** 61 `except ImportError:` sites across 38 files. [PATTERN: observed in executor.py, llm.py, async_llm.py, monitoring/metrics.py, validation/null_model.py, analysis/visualization.py, safety/reproducibility.py]

---

**Deviations:**

| Module | Pattern | Risk |
|--------|---------|------|
| `world_model/simple.py:926,937,955` | Three consecutive `except Exception: pass` blocks inside `_get_neo4j_storage_size()` with zero logging. Intentional 3-tier fallback chain (APOC -> db.stats -> estimation). | Debugging Neo4j connectivity issues is very difficult since no logging occurs at any fallback tier. Silent total swallowing. [FACT: world_model/simple.py:926,937,955] |
| `agents/research_director.py:674` | `_handle_error_with_recovery()` calls blocking `time.sleep()` with `[2, 4, 8]` second backoff. | Blocks the asyncio event loop since `execute()` and all `_handle_*_action()` methods are async. Entire event loop thread freezes during error backoff. (See also Gotcha 11.) [FACT: research_director.py:674] |
| `agents/research_director.py:131-139` | Database init in `__init__` catches `RuntimeError` for "already initialized" and ALL other exceptions, logging as warning only. | If DB init fails for a real reason, director continues without working database, causing cascading failures when any handler queries the DB. [FACT: research_director.py:131-139] |
| `core/async_llm.py:33-39` | tenacity is imported inside try/except. If missing, `_api_call_with_retry()` falls through to no-retry path. | No warning logged when tenacity is missing -- API calls silently run without retry protection. [FACT: core/async_llm.py:33-39] |
| `core/providers/anthropic.py:340-342` | `AnthropicProvider.generate()` catches ALL Anthropic SDK exceptions and wraps in `ProviderAPIError`. | Loses original exception type for downstream handlers. The `raw_error` field preserves it but callers rarely check it. [FACT: anthropic.py:340-342] |
| `agents/research_director.py` | 27 `except Exception as e:` sites (highest single-file count in codebase). | Reflects file size and orchestrator role, but massive catch surface means many failure modes are silently degraded. [FACT: research_director.py, error_handling finding Section 8f] |
| `core/metrics.py:63` | `BudgetExceededError` is defined and raised but never caught anywhere in the codebase. | Budget overruns propagate as unhandled exceptions, potentially crashing a research run. May be intentional (hard limit) but undocumented. [FACT: core/metrics.py:63, ABSENCE: no `except BudgetExceededError` found] |
| `executor.py:869-877` | RetryStrategy fix methods wrap entire code in try/except, making execution "succeed" with error result dict `{'status': 'failed'}`. | Callers must check `result.return_value` for `{'status': 'failed'}` in addition to `result.success`. A "successful" execution may contain failure. [FACT: executor.py:869-877] |
| `executor.py:621-630` | Windows timeout uses `ThreadPoolExecutor` -- cannot kill stuck computation. | Thread continues consuming resources after timeout fires. Only stops waiting for it. [FACT: executor.py:621-630] |
| `executor.py:335` | Retry loop calls `time.sleep()` synchronously between attempts. | Blocks the calling thread. In async contexts, blocks the event loop. [FACT: executor.py:335] |
| `code_generator.py:762-778` | LLM client failure during `__init__` silently disables LLM generation (`self.use_llm = False`). | If templates also don't match, only the basic fallback (which lacks synthetic data) runs. No exception raised. [FACT: code_generator.py:762-778] |
| `code_generator.py:988-989` | `_validate_syntax` raises `ValueError` wrapping `SyntaxError`. | Changes exception type for callers who expect SyntaxError. [FACT: code_generator.py:988-989] |
| `experiment_cache.py:391-446` | Inconsistent: `cache_experiment()` re-raises on write failure; `get_cached_result()` returns None on read failure. | Write-fail-loudly / read-fail-silently split is intentional but undocumented. [FACT: experiment_cache.py:391-446] |
| `cache.py:22` vs `literature/cache.py:19` | Two separate cache error hierarchies (`CacheError` and `LiteratureCacheError`) with no shared base class. | Cannot catch all cache errors with a single except clause. [FACT: error_handling finding Section 8c] |
| `plan_creator.py:194-198` | Falls back to mock plan on ANY exception (not just LLM failures). | A bug in plan creation logic would be silently masked by the mock fallback. [FACT: plan_creator.py:194-198] |
| `plan_reviewer.py:161-162` | Falls back to mock review on ANY exception. | Same risk as plan_creator -- bugs masked by optimistic mock review. [FACT: plan_reviewer.py:161-162] |
| `plan_creator.py:158-162`, `plan_reviewer.py:125-129` | Both use raw `anthropic_client.messages.create()` directly, bypassing Kosmos LLMProvider layer. | No caching, no cost tracking, no auto-model-selection, and no retry logic from the provider. [FACT: plan_creator.py:158-162, plan_reviewer.py:125-129] |
| `agents/base.py:276-287` | `send_message()` performs deferred `from kosmos.config import get_config` inside try/except. | Config failures silently swallowed -- message logging is best-effort. [FACT: base.py:276-287] |
| `safety/guardrails.py:95-110` | Signal handler registration for SIGTERM/SIGINT catches and logs failure rather than raising. | The safety system itself uses catch-log-degrade. If signal registration fails, emergency stop won't work but no error surfaces. [FACT: guardrails.py:95-110] |
| `research_director.py:2171-2174` | Sequential fallback in `execute_experiments_batch()` calls `asyncio.get_event_loop().run_until_complete()`. | Raises `RuntimeError` if event loop already running (e.g., during async execution). Only taken when concurrent execution is disabled. [FACT: research_director.py:2171-2174] |
| `code_validator.py:288` | Pattern detection uses `if pattern in code:` (raw string matching). | Matches inside comments and string literals. `# eval(` or `description = "do not eval("` triggers CRITICAL violation. [FACT: code_validator.py:288] |
| `base.py:136-138` | Sync `message_queue` list grows without bound (appended but never removed). | Memory leak in long-running agents. [FACT: base.py:136-138] |
| `experiment_designer.py:908-919` | Agent catches `get_session()` failures (e.g., "Database not initialized") and continues with a generated UUID. | Protocol/hypothesis object remains valid but is not persisted. Downstream code may expect DB persistence that didn't happen. [FACT: experiment_designer.py:908-919] |
| `core/async_llm.py:141-169` | `is_recoverable_error()` extends `ProviderAPIError` heuristic for Anthropic SDK: `RateLimitError` always recoverable, `APITimeoutError` always recoverable, `APIError` checked by message pattern. Unknown exceptions default to recoverable. | This is an independent recoverability check from the one in `providers/base.py:445-484`. The two can disagree on the same error class. [FACT: async_llm.py:141-169] |
| `core/providers/factory.py:191-213` | Each provider registration wrapped in `try/except ImportError`. Missing packages result in warnings, not crashes. | Only actually-available providers are registered. If all three provider packages are missing, the factory has zero providers but does not raise. [FACT: factory.py:191-213] |

---

**Error Event Propagation:**
[FACT] `core/events.py` defines typed failure events: `WORKFLOW_FAILED`, `CYCLE_FAILED`, `TASK_FAILED`, `LLM_CALL_FAILED`, `CODE_FAILED` (lines 22-46), published via `EventBus`.
[FACT] `AlertManager` at `monitoring/alerts.py:114` defines default rules for `database_connection_failed` (CRITICAL, 60s cooldown), `high_api_failure_rate` (ERROR, 300s cooldown), `api_rate_limit_warning` (WARNING, 600s cooldown), `high_memory_usage` (WARNING, 300s cooldown). Alert condition evaluator failures return `False` rather than propagating.

**Error Architecture Diagram:**
```
    Caller
      |
      v
  [Agent Layer]  --- catch Exception, log, return degraded result
      |               (research_director: error history + circuit breaker at 3)
      v
  [Orchestration Layer] --- retry with backoff, ProviderAPIError.is_recoverable() gate
      |                      (delegation: max_retries=2, exp backoff capped 8s)
      v
  [Core LLM Layer] --- tenacity retry + CircuitBreaker + ProviderAPIError
      |                  (async_llm: 3 attempts, exp backoff 1-30s)
      v
  [Provider Layer] --- wraps SDK exceptions into ProviderAPIError
      |                 (anthropic.py: all errors -> ProviderAPIError)
      v
  [External APIs]  --- Anthropic, PubMed, arXiv, Semantic Scholar
```

[ABSENCE] There is no centralized exception handler, error boundary, or middleware pattern. Each module independently implements its own try/except. No `error_handler`, `exception_middleware`, or `error_boundary` found in `kosmos/kosmos/`.

---

Error handling is tightly coupled to shared state: the singleton pattern means errors in one module's initialization can cascade to all callers that depend on the same singleton. The section below catalogs all mutable shared state and its risks.

## Shared State

### Module-Level Singletons

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `_default_client` | `core/llm.py:609` | `get_client(reset=True)` from any thread | `Optional[Union[ClaudeClient, LLMProvider]]` -- two incompatible types. Thread-safe via double-checked locking, but `reset=True` replaces the client for ALL threads. Callers expecting one type may get the other. [FACT: llm.py:609, 643-649] |
| `_client_lock` | `core/llm.py:610` | Never replaced, but guards `_default_client` | threading.Lock used for double-checked locking on singleton creation. |
| `_engine` | `db/__init__.py:22` | `init_database()` | SQLAlchemy engine. `None` until `init_database()`. `get_session()` raises `RuntimeError("Database not initialized")` if None -- the ONLY singleton that refuses to lazy-init. [FACT: db/__init__.py:22, 126-127] |
| `_SessionLocal` | `db/__init__.py:23` | `init_database()` | SQLAlchemy session factory. Same lifecycle as `_engine`. |
| `_config` | `config.py:1137` | `get_config(reload=True)` | `KosmosConfig` (Pydantic settings). Once created, changing env vars has no effect unless `reload=True`. Validates provider API keys at construction -- `ANTHROPIC_API_KEY` missing causes `ValueError`. [FACT: config.py:1137-1154, 1024-1043] |
| `_knowledge_graph` | `knowledge/graph.py:1000` | `get_knowledge_graph()`, `reset_knowledge_graph()` | Neo4j `KnowledgeGraph`. Init may auto-start Docker container (blocking up to 120 seconds). Connection failure sets `self.graph = None`, `self._connected = False`. [FACT: graph.py:1000, 118-172, 96-99] |
| `_world_model` | `world_model/factory.py:52` | `get_world_model()`, `reset_world_model()` | `WorldModelStorage` impl. Explicitly documented as NOT thread-safe. Falls back to `InMemoryWorldModel` if Neo4j unavailable. [FACT: factory.py:52, 38, 124-131] |
| `_vector_db` | `knowledge/vector_db.py:444` | `get_vector_db()`, `reset_vector_db()` | ChromaDB client singleton. Optional dependency (`HAS_CHROMADB` flag). All operations return empty results if unavailable. [FACT: vector_db.py:444-477] |
| `_event_bus` | `core/event_bus.py:261` | `get_event_bus()` | EventBus pub/sub. No external dependencies (standalone). |
| `_experiment_cache` | `core/experiment_cache.py:743` | `get_experiment_cache()` | Uses raw sqlite3 (not SQLAlchemy). Thread-safe via `threading.RLock()`. Connect-per-operation pattern. [FACT: experiment_cache.py:743, 220] |
| `_cache_manager` | `core/cache_manager.py:38` | Uses `__new__` singleton pattern | Different singleton mechanism from all others. |
| `_tracker` | `core/stage_tracker.py:249` | `get_stage_tracker()` | JSONL event emitter with timing. |
| `_metrics_collector` | `monitoring/metrics.py:448` | `get_metrics_collector()` | Metrics collector. |
| `_alert_manager` | `monitoring/alerts.py:535` | `get_alert_manager()` | Alert manager. |
| `_registry` | `agents/registry.py:522` | `get_registry()` | Agent registry. Wires message routers on `register()`. In practice unused by main loop (Issue #76). [FACT: registry.py:6-8, 70-97, 522] |
| `_literature_analyzer` | `agents/literature_analyzer.py:1069` | `get_literature_analyzer()` | Literature analyzer agent singleton. Depends on `_config` and `_default_client`. |
| `_reference_manager` | `literature/reference_manager.py:799` | `get_reference_manager()` | Reference manager singleton. |
| `_global_registry` | `experiments/templates/base.py:635` | Auto-discovery on first call | Template registry. Import-time auto-population. |

[PATTERN: 12+ singletons across 10+ modules, all following `global _var` / `get_var()` / `reset_var()` pattern. FACT: initialization finding]

---

### ResearchDirectorAgent In-Memory State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `self.workflow` | `research_director.py:105` | `transition_to()`, but `current_state` is public and can be set directly | `current_state` can be bypassed without `transition_to()`, causing `ResearchPlan.current_state` to diverge. The sync `_workflow_context()` yields workflow without any lock. [FACT: workflow.py:319, 323-325; research_director.py:376-379] |
| `self.research_plan` | `research_director.py:~108` | All `_handle_*_action()` methods, `transition_to()` (syncs current_state) | In-memory only. Protected by `_research_plan_lock` (async) and `_research_plan_lock_sync` (threading), but sync `_workflow_context()` has no lock. Only the director reads/writes it. [FACT: research_director.py, workflow.py:57-95] |
| `self._hypothesis_agent` through `self._hypothesis_refiner` (7 slots) | `research_director.py:144-152` | Lazy-initialized on first use in `_handle_*_action()` methods | All `None` at init. Created when first needed. No synchronization on creation -- if two async tasks trigger the same handler concurrently, two agents could be created (race). [FACT: research_director.py:144-152] |
| `self._actions_this_iteration` | `research_director.py:2451-2452` | `decide_next_action()` via `hasattr` check | Lazily initialized via `hasattr` instead of `__init__`. Inconsistent with all other instance variables. Used for infinite loop guard (`MAX_ACTIONS_PER_ITERATION = 50`). [FACT: research_director.py:2451-2452, 50] |
| `self._consecutive_errors` | `research_director.py:~640` | `_handle_error()`, `_handle_error_with_recovery()` | Circuit breaker counter. At 3, transitions workflow to ERROR state. Reset on successful action. [FACT: research_director.py:45, 649-662] |
| `self._error_history` | `research_director.py:~640` | `_handle_error()` | List of error dicts (source, message, timestamp, recoverability, details). Grows without bound. [FACT: research_director.py:627-684] |
| `self.errors_encountered` | `research_director.py:~640` | `_handle_error()` | Total error counter (int). |
| `self.wm` | `research_director.py:242-255` | `__init__` only | World model reference. Set to `None` if `get_world_model()` fails. All 4 graph persistence methods (`_persist_hypothesis_to_graph`, `_persist_protocol_to_graph`, `_persist_result_to_graph`, `_add_support_relationship`) silently no-op when `self.wm is None`. Fire-and-forget (catch-and-log). [FACT: research_director.py:242-255, 388-562] |
| Async locks: `_research_plan_lock`, `_strategy_stats_lock`, `_workflow_lock`, `_agent_registry_lock` | `research_director.py:192-200` | `asyncio.Lock()` instances | Async-only locking. Threading counterparts exist for sync compatibility, but no mutual exclusion between async and sync paths. [FACT: research_director.py:192-200, 376-379] |

---

### BaseAgent In-Memory State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `self.message_queue` | `base.py:136` | `receive_message()` appends; nothing removes | Sync list grows without bound. Memory leak in long-running agents. [FACT: base.py:136-138] |
| `self._async_message_queue` | `base.py:137` | `receive_message()` puts | `asyncio.Queue()` -- no size limit specified. |
| `self.status` | `base.py:131` | `start()`, `stop()`, `pause()`, `resume()`, error in `_on_start()` | No lock. `start()` is one-shot (CREATED only). `stop()` from ANY state. Cannot restart from ERROR. [FACT: base.py:161-187] |
| `self.state_data` | `base.py:140` | `save_state_data()`, `restore_state()` | Arbitrary dict. No validation. |
| `self.message_handlers` | `base.py:141` | `register_message_handler()` | Dict of handlers, but `process_message()` does NOT dispatch to them. Dead code unless subclass explicitly uses it. [FACT: base.py:406-415] |
| `self._message_router` | `base.py:142` | `set_message_router()` | Can be sync or async callable. Checked at runtime via `asyncio.iscoroutine()`. |
| `self.messages_sent` / `self.messages_received` / `self.errors_count` | `base.py:145-148` | `send_message()`, `receive_message()`, error paths | Counters. No lock. |

---

### LLM Client Internal State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `ClaudeClient` internal counters | `llm.py:~180-200` | Every `generate()` / `generate_structured()` call | `_request_count`, `_total_input_tokens`, `_total_output_tokens`, `_cache_hits`, `_cache_misses`, etc. No lock -- concurrent calls can produce inaccurate counts. |
| `ClaudeClient.model` | `llm.py:~175` | Auto-model selection in `generate()` | If auto-selection changes `self.model`, it persists to `generate_with_messages()` which uses `self.model` directly without auto-selection. [FACT: llm.py:389] |
| `LLMProvider` usage counters | `providers/base.py:190-193` | `_update_usage_stats()` on every call | Instance-level only. No global/shared tracking across multiple provider instances. Skips cost when `cost_usd` is exactly `0.0` (falsy). [FACT: base.py:190-193, 401] |

---

### Executor / Validator State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `SAFE_BUILTINS` | `executor.py:43-83` | Module-level constant (not mutated) | Dict of ~80 safe builtins. Includes `hasattr` but NOT `getattr`/`setattr`/`delattr`. However, `type` and `object` ARE included -- can be used to bypass restrictions via `type.__getattribute__`. [FACT: executor.py:594-597] |
| `_ALLOWED_MODULES` | `executor.py:86-94` | Module-level constant (not mutated) | Set of ~30 allowed import modules. Does NOT include `os`, but `RetryStrategy.COMMON_IMPORTS` dict DOES include `'os': 'import os'` -- auto-fix can insert an import the validator would reject. [FACT: code_validator.py:36, executor.py:686] |
| `RetryStrategy.repair_stats` | `executor.py:711` | `record_repair_attempt()` | Per-error-type success/failure counts. Instance-level, no persistence. |

---

### NoveltyDetector In-Memory State

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `self.task_embeddings` / `self.task_texts` / `self.task_metadata` | `novelty_detector.py:~90` | `index_past_tasks()`, `filter_redundant_tasks()` (temporarily) | No persistence -- lost on process restart. `filter_redundant_tasks` does copy-restore to avoid permanent mutation, but copy is shallow (list of numpy arrays). [FACT: novelty_detector.py:320-342] |
| `self.use_sentence_transformers` | `novelty_detector.py:72-85` | `__init__` -- mutated to `False` on import failure | Flag mutated from init param value if sentence-transformers package unavailable. Silently degrades to Jaccard similarity. |

---

### Database Singletons

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| SQLAlchemy `_engine` / `_SessionLocal` | `db/__init__.py:22-23` | `init_database()` only | Only singleton that refuses lazy-init -- raises RuntimeError. `ResearchDirectorAgent.__init__` is de facto initializer. Double-init caught as RuntimeError. [FACT: db/__init__.py:126-127, research_director.py:131-139] |
| `ExperimentCache` SQLite DB | `core/experiment_cache.py:240-298` | All cache operations (connect-per-op) | Completely independent from main SQLAlchemy database. Raw sqlite3 with `threading.RLock()` serialization. [FACT: experiment_cache.py:231, 220] |

---

### Provider Registration (Import-Time Side Effect)

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| Provider registry | `core/providers/factory.py:216-217` | `_register_builtin_providers()` called at module import time | Importing `kosmos.core.providers` triggers immediate import of `anthropic.py`, `openai.py`, `litellm_provider.py`. Each sets `HAS_ANTHROPIC`/`HAS_OPENAI` flags. Graceful degradation on missing packages. [FACT: factory.py:216-217, anthropic.py:13-18, openai.py:14-18] |

---

### Dual Model System (Cross-Store State)

[PATTERN] Two parallel data model systems with no automatic synchronization:
1. **SQLAlchemy ORM models** (`kosmos/db/models.py`) -- `Hypothesis`, `Experiment`, `Result`, `Paper`, `AgentRecord`, `ResearchSession`. Used by agents for CRUD. String primary keys (application-generated UUIDs).
2. **Dataclass models** (`kosmos/world_model/models.py`) -- `Entity`, `Relationship`, `Annotation`. Used by world model for graph operations.

The `ResearchDirectorAgent` writes to BOTH: SQLAlchemy for structured queries, world model for graph traversal. `Entity` has factory methods (`from_hypothesis()`, `from_protocol()`, `from_result()`) that convert between systems, but there is no automatic synchronization. [FACT: database_storage finding Section 8]

[ABSENCE] No distributed transaction coordinator. When data is written to multiple backends (JSON + knowledge graph + vector store), each write is independent. Failure in one does not roll back others.

---

### Agents Bypass CRUD Layer

[PATTERN] Agent classes (`hypothesis_generator.py:474-492`, `experiment_designer.py:888-903`) directly construct SQLAlchemy model instances and call `session.add()` + `session.commit()` instead of using CRUD functions in `operations.py`. Bypasses the validation logic (`_validate_json_dict`, `_validate_json_list`) that the CRUD layer provides. [FACT: database_storage finding]

[PATTERN] Double-commit: CRUD operations in `operations.py` call `session.commit()` explicitly, AND `get_session()` context manager also calls `session.commit()` on exit. Harmless (second is no-op) but indicates CRUD layer designed for use both with and without context manager. [FACT: db/operations.py, db/__init__.py:108-137]

---

### Initialization DAG Critical Ordering

```
get_config()                                    # ROOT: must init before everything
    |
    +-- get_client() [core/llm.py:613]          # Level 1
    +-- init_database() [db/__init__.py:140]    # Level 1 (HARD FAILURE if not init'd)
    +-- get_knowledge_graph() [graph.py:1003]   # Level 1 (may auto-start Docker: 120s blocking)
    +-- get_stage_tracker()                     # Level 1
    |
    +-- get_world_model() [factory.py:55]       # Level 2 (depends on config + knowledge_graph)
    |
    +-- ResearchDirectorAgent.__init__()        # Level 2 (depends on all of above)
```

[FACT: `config.py:1024-1043`] Config validation gates everything: missing `ANTHROPIC_API_KEY` with `LLM_PROVIDER=anthropic` raises `ValueError` at config construction.

[FACT: `knowledge/graph.py:118-172`] Neo4j Docker auto-start: `subprocess.run(["docker-compose", "up", "-d", "neo4j"])` with 60s timeout + 30 polls x 2s = potential 120 seconds blocking during `get_knowledge_graph()`.

[FACT: `world_model/factory.py:38`] World model factory explicitly warns "NOT thread-safe" -- no lock on `_world_model` global, unlike `_default_client` which has `_client_lock`.
## Domain Glossary

| Term | Means Here | Defined In |
|------|------------|------------|
| **CLI mode** | A runtime mode where the API key consists entirely of 9-digit characters (`api_key.replace('9', '') == ''`), routing requests through Claude Code instead of the Anthropic API. Disables cost calculation and auto-model-selection. | `kosmos/core/llm.py:179`, `kosmos/core/providers/anthropic.py:110` |
| **AgentMessage** | Pydantic-based wire format for all inter-agent communication. Contains `from_agent`, `to_agent`, `content`, `correlation_id`, `message_type`, and timestamp. | `kosmos/agents/base.py:40-84` |
| **AgentStatus** | Lifecycle state enum for agents: CREATED, STARTING, RUNNING, PAUSED, STOPPED, ERROR, IDLE, WORKING. Used in health monitoring. | `kosmos/agents/base.py` (enum definition) |
| **BaseAgent** | Abstract superclass of all 6 Kosmos agents providing lifecycle management, dual message queues, state persistence, and health monitoring. | `kosmos/agents/base.py:97-111` |
| **Hypothesis** | Pydantic data model representing a scientific hypothesis with statement, rationale, domain, four float scores (testability, novelty, confidence, priority), and evolution tracking. The most-imported symbol (48 importers). | `kosmos/models/hypothesis.py:32-156` |
| **HypothesisStatus** | Six-value lifecycle enum: GENERATED, UNDER_REVIEW, TESTING, SUPPORTED, REJECTED, INCONCLUSIVE. | `kosmos/models/hypothesis.py:22` |
| **ExperimentType** | Three-value enum: COMPUTATIONAL, DATA_ANALYSIS, LITERATURE_SYNTHESIS. Defines what kind of experiment tests a hypothesis. Defined in hypothesis.py despite the name. | `kosmos/models/hypothesis.py:15-19` (re-imported by `kosmos/models/experiment.py:14`) |
| **ExperimentProtocol** | Central Pydantic model tying together hypothesis, steps, variables, control groups, statistical tests, resources, and reproducibility metadata. 30 importers. | `kosmos/models/experiment.py:329-575` |
| **ProtocolStep** | Single experiment step with number, title, description, action, dependencies, expected outputs, time estimates, and code hints. Silently sorted by `step_number` during validation. | `kosmos/models/experiment.py:138-190` |
| **ExperimentResult** | Pydantic model combining status, raw/processed data, variable results, statistical tests, primary metrics, execution metadata, and versioning. The canonical schema for all experiment output. Distinct from the SQLAlchemy `ResultModel`. | `kosmos/models/result.py:127-205` |
| **ResultStatus** | Five-value enum: SUCCESS, FAILED, PARTIAL, TIMEOUT, ERROR. | `kosmos/models/result.py:16-22` |
| **StatisticalTestResult** | Captures one statistical test result: type, name, statistic value, p-value, effect size, confidence intervals, significance at multiple alpha levels. | `kosmos/models/result.py:61-103` |
| **ExecutionMetadata** | Captures execution context: timestamps, system info, resource usage, experiment/protocol IDs, sandbox/timeout flags. | `kosmos/models/result.py:25-58` |
| **SafetyReport** | Pydantic model returned by `CodeValidator.validate()` containing violations, warnings, risk assessment, and pass/fail decision. `passed` = zero violations (warnings ignored). | `kosmos/models/safety` (imported by `kosmos/safety/code_validator.py:17-19`) |
| **PaperMetadata** | Stdlib `@dataclass` (not Pydantic) representing a scientific paper across all literature sources. Contains identifiers, core metadata, links, citation counts, fields/keywords, optional full text. Universal paper representation (35 importers). | `kosmos/literature/base_client.py:36-122` |
| **PaperSource** | Five-value `str, Enum`: ARXIV, SEMANTIC_SCHOLAR, PUBMED, UNKNOWN, MANUAL. Identifies where a paper came from. | `kosmos/literature/base_client.py:17` |
| **LLMResponse** | Dataclass wrapping LLM output with `content`, `usage`, `model`, plus 20+ string-compatibility methods that delegate to `content`. `response.strip()` returns `str`, losing metadata. Empty content makes response falsy. | `kosmos/core/providers/base.py:57-154` |
| **LLMProvider** | Abstract base class for all LLM backends. Defines `generate`, `generate_async`, `generate_with_messages`, `generate_structured`, `generate_stream`. Three concrete implementations: Anthropic, OpenAI, LiteLLM. | `kosmos/core/providers/base.py:170-410` |
| **ProviderAPIError** | Canonical exception for provider failures with multi-stage `is_recoverable()` heuristic (flag -> HTTP code -> message pattern). Controls retry behavior system-wide. Default: `recoverable=True`. | `kosmos/core/providers/base.py:429-484` |
| **Message** | Dataclass for multi-turn conversation input: `role`, `content`, optional `name` and `metadata`. Input format for `generate_with_messages()`. | `kosmos/core/providers/base.py:18-31` |
| **UsageStats** | Dataclass tracking LLM call metrics: input/output/total tokens, optional cost, model, provider, timestamp. | `kosmos/core/providers/base.py:35-54` |
| **ModelComplexity** | Static utility in llm.py that scores prompt complexity (0-100) via token count + keyword matching. Recommends "haiku" (score <30) or "sonnet" (everything else). Never picks higher than Sonnet. | `kosmos/core/llm.py:52-105` |
| **ClaudeClient** | Legacy name for `AnthropicProvider`. Wraps the Anthropic SDK with caching, auto model selection, usage tracking. Also exposed as `AnthropicProvider` via backward-compat alias. | `kosmos/core/llm.py:154-605`, `kosmos/core/providers/anthropic.py:881` |
| **WorkflowState** | Nine-value state machine enum: INITIALIZING, GENERATING_HYPOTHESES, DESIGNING_EXPERIMENTS, EXECUTING, ANALYZING, REFINING, CONVERGED, PAUSED, ERROR. | `kosmos/core/workflow.py:18-29` |
| **NextAction** | Eight-value enum: GENERATE_HYPOTHESIS, DESIGN_EXPERIMENT, EXECUTE_EXPERIMENT, ANALYZE_RESULT, REFINE_HYPOTHESIS, CONVERGE, PAUSE, ERROR_RECOVERY. Maps to handler methods in ResearchDirector. | `kosmos/core/workflow.py:32-43` |
| **ResearchPlan** | Pydantic model tracking research state: question, domain, hypothesis pool (IDs), experiment queue (IDs), results (IDs), iteration count, convergence. ID-based tracking only -- no object references, no DB knowledge. | `kosmos/core/workflow.py:57-163` |
| **ResearchWorkflow** | State machine with validated transitions, history tracking, and `ResearchPlan` sync. `transition_to()` validates; direct assignment to `current_state` bypasses validation. | `kosmos/core/workflow.py:166-416` |
| **ALLOWED_TRANSITIONS** | Dict mapping each `WorkflowState` to its set of valid target states. Enforced by `transition_to()`. Notable: `CONVERGED` can go back to `GENERATING_HYPOTHESES`; `PAUSED` can resume to 6 different states. | `kosmos/core/workflow.py:170-230` |
| **StoppingDecision** | Pydantic model returned by `ConvergenceDetector.check_convergence()`: `should_stop` (bool), `reason` (StoppingReason enum), `confidence` (float), `details` (dict). | `kosmos/core/convergence.py` |
| **StoppingReason** | Enum of convergence reasons. Includes `USER_REQUESTED` which is also used as a placeholder for "no reason" when research continues -- not a meaningful signal. | `kosmos/core/convergence.py:271` |
| **ConvergenceDetector** | Stateful evaluator of stopping criteria: iteration_limit, hypothesis_exhaustion, novelty_decline, diminishing_returns. Accumulates metrics across calls. `novelty_trend` list grows unbounded. | `kosmos/core/convergence.py` |
| **ConvergenceReport** | Final report with statistics, supported/rejected hypotheses, summary, and recommendations. Produced by `ConvergenceDetector.generate_convergence_report()`. | `kosmos/core/convergence.py` |
| **CodeValidator** | Safety gate for generated code. Runs 6 checks: syntax, dangerous imports, dangerous patterns (string-based), network operations, AST calls, ethical guidelines. Pattern matching catches comments and string literals. | `kosmos/safety/code_validator.py` |
| **DANGEROUS_MODULES** | Module-level list of imports that trigger CRITICAL violations: includes `os`, `subprocess`, `sys`, `shutil`, `ctypes`, etc. | `kosmos/safety/code_validator.py:36` |
| **CodeTemplate** | Base class for experiment code templates. `matches(protocol)` checks experiment type; `generate(protocol)` produces executable Python. 5 built-in templates plus a basic fallback. | `kosmos/execution/code_generator.py:27-45` |
| **ExperimentCodeGenerator** | Hybrid code generation: template match -> LLM generation -> basic fallback. Always validates syntax. LLM client has double fallback (ClaudeClient -> LiteLLM -> disable). | `kosmos/execution/code_generator.py:741-995` |
| **CodeExecutor** | Executes Python/R code with restricted builtins sandbox (~80 safe builtins, ~30 allowed modules), timeout enforcement, profiling, determinism testing, and self-correcting retry logic. NOT process isolation. | `kosmos/execution/executor.py:174-660` |
| **ExecutionResult** | Data container for execution output: `success`, `return_value`, `stdout`, `stderr`, `error`, `error_type`, `execution_time`, `profile_result`, `data_source`. | `kosmos/execution/executor.py:113-159` |
| **SAFE_BUILTINS** | Whitelist of ~80 safe Python builtins used when Docker sandbox unavailable. Includes `hasattr` but NOT `getattr`/`setattr`/`delattr`. Includes `type` and `object` (potential bypass). | `kosmos/execution/executor.py:43-83` |
| **RetryStrategy** | Self-correcting retry logic handling 11 error types. LLM repair on first 2 attempts, then pattern-based. Some fixes wrap entire code in try/except, making execution "succeed" with error dict. FileNotFoundError is terminal (Issue #51). | `kosmos/execution/executor.py:665-906` |
| **ResearchDirectorAgent** | Master orchestrator. Inherits from `BaseAgent`. Drives the full research cycle. Has two coordination mechanisms (message-based = dead code per Issue #76; direct-call = active). 50-action-per-iteration guard. 3-error circuit breaker. | `kosmos/agents/research_director.py` |
| **KnowledgeGraph** | Neo4j-backed graph with 4 node types (Paper, Concept, Method, Author) and 5 relationship types (CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO). Auto-starts Docker container. Connection failure silently swallowed. | `kosmos/knowledge/graph.py` |
| **PaperVectorDB** | ChromaDB wrapper for cosine-similarity paper search. Uses SPECTER embedder (768-dim). ChromaDB optional -- graceful degradation. Abstracts truncated to 1000 chars. Document format: `title [SEP] abstract`. | `kosmos/knowledge/vector_db.py` |
| **WorldModelStorage** | Abstract base class defining 10+ methods for persistent knowledge graph operations. Two implementations: `Neo4jWorldModel` (adapter over KnowledgeGraph) and `InMemoryWorldModel` (dict-based fallback). | `kosmos/world_model/interface.py:36-367` |
| **Entity** | Dataclass in world_model/models.py with 11 valid types (Paper, Concept, Author, Experiment, Hypothesis, Finding, Dataset, Method, ResearchQuestion, ExperimentProtocol, ExperimentResult). Factory methods translate Pydantic/SQLAlchemy objects. Non-standard types trigger warning but are accepted. | `kosmos/world_model/models.py:72-341` |
| **Relationship** | Dataclass in world_model/models.py with 12 valid types including research-workflow-specific: `SPAWNED_BY`, `TESTS`, `REFINED_FROM`, `SUPPORTS`, `REFUTES`. | `kosmos/world_model/models.py:461-667` |
| **ArtifactStateManager** | 4-layer hybrid state manager: JSON file artifacts, optional knowledge graph, optional vector store (stub), citation tracking. Implements statistical conflict detection (effect direction, p-value contradiction). Separate from WorldModelStorage. | `kosmos/world_model/artifacts.py:146-727` |
| **UpdateType** | Three-value enum in ArtifactStateManager: CONFIRMATION, CONFLICT, PRUNING. Implements the paper's three finding-update categories. | `kosmos/world_model/artifacts.py:37-47` |
| **Finding** | Dataclass in artifacts.py with 23 fields: core (id, cycle, task_id, summary, statistics), validation (scholar_eval, null_model_result, failure_detection_result), provenance (code_provenance, notebook_path), expert review (validated, accurate, notes). | `kosmos/world_model/artifacts.py:51-96` |
| **PlanCreatorAgent** | Generates strategic 10-task research plans with adaptive exploration/exploitation ratios (70%/50%/30% by cycle range). Uses raw Anthropic SDK, bypassing provider layer. Falls back to mock planning on any error. | `kosmos/orchestration/plan_creator.py` |
| **PlanReviewerAgent** | Validates plans on 5 dimensions (specificity, relevance, novelty, coverage, feasibility) scored 0-10, plus hard structural requirements. Uses raw Anthropic SDK. Dimension weights defined but NOT used. | `kosmos/orchestration/plan_reviewer.py` |
| **DelegationManager** | Executes approved plans by routing tasks to specialized agents in parallel batches (default size 3). Tasks batched sequentially -- batch 2 waits for batch 1. Agent validation deferred to execution time. | `kosmos/orchestration/delegation.py` |
| **NoveltyDetector** | Prevents redundant research tasks via semantic similarity (sentence-transformers) or Jaccard fallback. Threshold 0.75 for redundancy. Index is in-memory only -- lost on restart. | `kosmos/orchestration/novelty_detector.py` |
| **LogFormat** | Two-value enum: JSON, TEXT. Selects logging formatter in `setup_logging()`. | `kosmos/core/logging.py:28` |
| **ExperimentLogger** | Stateful logger tracking experiment lifecycle events with timing. Events accumulate unbounded in memory. Duration returns 0 if `start()` never called. | `kosmos/core/logging.py:242-380` |
| **correlation_id** | Module-level `contextvars.ContextVar` for cross-async request tracing. Instantiated at import. Read only by `JSONFormatter.format()`. Not imported by any agent (agents use their own `correlation_id` field on `AgentMessage`). [ABSENCE] | `kosmos/core/logging.py:23-25` |
| **_MAX_SAMPLE_SIZE** | Module-private constant = 100,000. Hard ceiling used by multiple validators in experiment.py for `ControlGroup.sample_size` and `ExperimentProtocol.sample_size`. Silently clamps values. | `kosmos/models/experiment.py:19` |
| **Issue #51** | Referenced fix making FileNotFoundError terminal in executor retry logic. Templates generate synthetic data instead of retrying missing data files. | `kosmos/execution/executor.py:726`, `kosmos/execution/code_generator.py:112-130` |
| **Issue #76** | Revealed that message-based agent coordination silently failed because agents were never registered in the message router. Direct-call `_handle_*_action()` methods are the active code path. `_send_to_*` methods kept as dead code. | `kosmos/agents/research_director.py:1039-1219` |
| **F-21** | Referenced fix removing the `validate_safety` bypass in `execute_protocol_code()`. All code now always passes through `CodeValidator`. | `kosmos/execution/executor.py:1039-1048` |
| **model_to_dict** | Pydantic v1/v2 compatibility shim from `kosmos.utils.compat`. Used by `ExperimentResult.to_dict()`, `ConvergenceDetector.get_metrics_dict()`, and others instead of standard `model_dump()`. | `kosmos/utils/compat` (imported across many modules) |
| **`[SEP]`** | Separator token used in vector_db.py to concatenate title and abstract for stored documents: `title [SEP] abstract`. Downstream document parsers must know this format. | `kosmos/knowledge/vector_db.py:440` |
| **SPECTER** | Embedding model used by PaperVectorDB. Produces 768-dimensional vectors. May trigger ~440MB download on first use. | `kosmos/knowledge/embeddings` (used by `vector_db.py:103`) |

---

The glossary above defines the canonical terms used throughout this document. The Configuration Surface below catalogs all ~105 environment variables that control Kosmos behavior at runtime.

## Configuration Surface

### Configuration Architecture

[FACT] The entire configuration system is centralized in `kosmos/config.py` (1161 lines). It uses **Pydantic v2 `BaseSettings`** (from `pydantic_settings`) to define typed, validated configuration classes that auto-populate from environment variables and `.env` files. `config.py:1140`

[FACT] The entry point for configuration access is a module-level singleton: `get_config() -> KosmosConfig` at `config.py:1140`. It is a lazy singleton (`_config` global, line 1137) that creates the `KosmosConfig` instance on first access, with an optional `reload=True` parameter. A `reset_config()` function (line 1157) exists for testing.

[FACT] The `.env` file location is hardcoded in `KosmosConfig.model_config` at line 979:
```python
env_file=str(Path(__file__).parent.parent / ".env")
```
This resolves to the repository root. The same pattern appears in `LiteLLMConfig` at line 194.

[FACT] `load_dotenv()` is called at module import time in `kosmos/cli/main.py:22`, before any config access. This means environment variables from `.env` are available when Pydantic `BaseSettings` reads them.

#### Loading Chain
```
CLI launch (kosmos/cli/main.py:22)
  -> load_dotenv()                              # python-dotenv reads .env
  -> get_config()                               # Pydantic BaseSettings auto-reads env vars
     -> KosmosConfig.__init__()
        -> Each sub-config class instantiated via default_factory
        -> model_validator: sync_litellm_env_vars() (line 985)
        -> model_validator: validate_provider_config() (line 1024)
     -> create_directories()                    # Create log + chromadb dirs
```

#### Config Class Hierarchy

[FACT] `KosmosConfig` (line 922) composes 16 sub-configuration classes, all inheriting from `BaseSettings`:

| Sub-Config Class | Lines | Env Alias Prefix | Purpose |
|---|---|---|---|
| `ClaudeConfig` | 29-84 | `ANTHROPIC_*`, `CLAUDE_*` | Anthropic/Claude LLM settings |
| `OpenAIConfig` | 91-140 | `OPENAI_*` | OpenAI provider settings |
| `LiteLLMConfig` | 143-197 | `LITELLM_*` | LiteLLM multi-provider config |
| `ResearchConfig` | 200-247 | `MAX_RESEARCH_*`, etc. | Research workflow parameters |
| `DatabaseConfig` | 250-302 | `DATABASE_*` | SQLAlchemy DB connection |
| `RedisConfig` | 305-362 | `REDIS_*` | Redis cache settings |
| `LoggingConfig` | 365-432 | `LOG_*`, `DEBUG_*`, `STAGE_*` | Logging and debug config |
| `LiteratureConfig` | 435-489 | `SEMANTIC_SCHOLAR_*`, `PUBMED_*`, `LITERATURE_*` | Academic API config |
| `VectorDBConfig` | 492-531 | `VECTOR_DB_*`, `CHROMA_*`, `PINECONE_*` | Vector database config |
| `Neo4jConfig` | 534-570 | `NEO4J_*` | Knowledge graph connection |
| `SafetyConfig` | 573-683 | `ENABLE_SAFETY_*`, `MAX_*`, etc. | Safety guardrails |
| `PerformanceConfig` | 686-749 | `ENABLE_*`, `MAX_*`, `ASYNC_*` | Concurrency and caching |
| `LocalModelConfig` | 752-822 | `LOCAL_MODEL_*` | Ollama/LM Studio tuning |
| `MonitoringConfig` | 825-840 | `ENABLE_USAGE_*`, `METRICS_*` | Metrics export settings |
| `DevelopmentConfig` | 843-862 | `HOT_RELOAD`, `LOG_API_*`, `TEST_MODE` | Dev/test toggles |
| `WorldModelConfig` | 865-893 | `WORLD_MODEL_*` | Knowledge graph persistence |

[FACT] `ClaudeConfig` and `AnthropicConfig` are aliases (line 88: `AnthropicConfig = ClaudeConfig`). Both the `claude` and `anthropic` fields in `KosmosConfig` point to the same class but are conditionally instantiated.

---

### LLM Provider Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LLM_PROVIDER` | env | Provider selector: `anthropic`, `openai`, or `litellm` | `"anthropic"` |

#### Anthropic (when LLM_PROVIDER=anthropic) -- REQUIRED

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ANTHROPIC_API_KEY` | env | API key or `999...` for CLI proxy mode. Read at `config.py:39`, `core/llm.py:160`, `core/providers/anthropic.py:88`, `api/health.py:283`, `cli/main.py:255`, `agents/research_director.py:228` | *none* |
| `CLAUDE_MODEL` | env | Model identifier | `"claude-sonnet-4-5"` |
| `CLAUDE_MAX_TOKENS` | env | Max response tokens | `4096` |
| `CLAUDE_TEMPERATURE` | env | Sampling temperature (0.0-1.0) | `0.7` |
| `CLAUDE_ENABLE_CACHE` | env | Prompt caching toggle | `true` |
| `CLAUDE_BASE_URL` | env | Custom endpoint URL. Read at `config.py:68`, `core/providers/anthropic.py:107` | *none* |
| `CLAUDE_TIMEOUT` | env | Request timeout (seconds) | `120` |

#### OpenAI (when LLM_PROVIDER=openai) -- REQUIRED

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `OPENAI_API_KEY` | env | OpenAI API key (or dummy for local). Read at `config.py:101`, `core/providers/openai.py:106` | *none* |
| `OPENAI_MODEL` | env | Model name | `"gpt-4-turbo"` |
| `OPENAI_MAX_TOKENS` | env | Max response tokens | `4096` |
| `OPENAI_TEMPERATURE` | env | Sampling temperature | `0.7` |
| `OPENAI_BASE_URL` | env | Custom endpoint (Ollama, OpenRouter, etc.). Read at `config.py:124`, `core/providers/openai.py:116` | *none* |
| `OPENAI_ORGANIZATION` | env | OpenAI org ID. Read at `config.py:129`, `core/providers/openai.py:117` | *none* |
| `OPENAI_TIMEOUT` | env | Request timeout | `120` |

#### LiteLLM (when LLM_PROVIDER=litellm) -- REQUIRED

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LITELLM_MODEL` | env | Model in LiteLLM format (e.g., `ollama/llama3.1:8b`). Read at `config.py:157`, `core/providers/factory.py:164` | `"gpt-3.5-turbo"` |
| `LITELLM_API_KEY` | env | API key (optional for local models). Read at `config.py:162`, `core/providers/factory.py:165` | *none* |
| `LITELLM_API_BASE` | env | Custom base URL. Read at `config.py:167`, `core/providers/factory.py:166` | *none* |
| `LITELLM_MAX_TOKENS` | env | Max response tokens. Read at `config.py:172`, `core/providers/factory.py:167` | `4096` |
| `LITELLM_TEMPERATURE` | env | Sampling temperature. Read at `config.py:179`, `core/providers/factory.py:168` | `0.7` |
| `LITELLM_TIMEOUT` | env | Request timeout. Read at `config.py:186`, `core/providers/factory.py:169` | `120` |

---

### Research Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `MAX_RESEARCH_ITERATIONS` | env | Max autonomous iterations | `10` |
| `ENABLED_DOMAINS` | env | Comma-separated scientific domains | `"biology,physics,chemistry,neuroscience"` |
| `ENABLED_EXPERIMENT_TYPES` | env | Experiment type whitelist | `"computational,data_analysis,literature_synthesis"` |
| `MIN_NOVELTY_SCORE` | env | Hypothesis novelty threshold | `0.6` |
| `ENABLE_AUTONOMOUS_ITERATION` | env | Autonomous loop toggle | `true` |
| `RESEARCH_BUDGET_USD` | env | API cost budget | `10.0` |
| `MAX_RUNTIME_HOURS` | env | Maximum wall-clock hours | `12.0` |

---

### Database Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `DATABASE_URL` | env | SQLAlchemy connection string | `"sqlite:///kosmos.db"` |
| `DATABASE_ECHO` | env | SQL logging toggle | `false` |

---

### Redis Cache Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `REDIS_ENABLED` | env | Redis toggle. Read at `config.py:315` AND `api/health.py:226` (dual-read) | `false` |
| `REDIS_URL` | env | Redis connection URL. Read at `config.py:310` AND `api/health.py:231` (dual-read) | `"redis://localhost:6379/0"` |
| `REDIS_MAX_CONNECTIONS` | env | Connection pool size | `50` |
| `REDIS_SOCKET_TIMEOUT` | env | Socket timeout (seconds) | `5` |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | env | Connect timeout | `5` |
| `REDIS_RETRY_ON_TIMEOUT` | env | Retry behavior | `true` |
| `REDIS_DECODE_RESPONSES` | env | UTF-8 decode toggle | `true` |
| `REDIS_DEFAULT_TTL_SECONDS` | env | Cache TTL | `3600` |

---

### Logging Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LOG_LEVEL` | env | Log severity level | `"INFO"` |
| `LOG_FORMAT` | env | Output format: `json` or `text` | `"json"` |
| `LOG_FILE` | env | Log file path | `"logs/kosmos.log"` |
| `DEBUG_MODE` | env | Verbose debug output | `false` |
| `DEBUG_LEVEL` | env | Granularity: 0=off, 1=critical path, 2=full trace, 3=data dumps | `0` |
| `DEBUG_MODULES` | env | Comma-separated module filter | *none* |
| `LOG_LLM_CALLS` | env | Log LLM request/response | `false` |
| `LOG_AGENT_MESSAGES` | env | Log inter-agent messages | `false` |
| `LOG_WORKFLOW_TRANSITIONS` | env | Log state machine events | `false` |
| `STAGE_TRACKING_ENABLED` | env | JSON event stage tracking | `false` |
| `STAGE_TRACKING_FILE` | env | Stage tracking output path | `"logs/stages.jsonl"` |

---

### Literature API Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `SEMANTIC_SCHOLAR_API_KEY` | env | Semantic Scholar key (increases rate limits) | *none* |
| `PUBMED_API_KEY` | env | PubMed NCBI key | *none* |
| `PUBMED_EMAIL` | env | PubMed E-utilities email | *none* |
| `LITERATURE_CACHE_TTL_HOURS` | env | Literature cache lifetime | `48` |
| `MAX_RESULTS_PER_QUERY` | env | Search result limit | `100` |
| `PDF_DOWNLOAD_TIMEOUT` | env | PDF fetch timeout | `30` |
| `LITERATURE_SEARCH_TIMEOUT` | env | Combined search timeout | `90` |
| `LITERATURE_API_TIMEOUT` | env | Per-API call timeout | `30` |

---

### Vector Database Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `VECTOR_DB_TYPE` | env | Backend: `chromadb`, `pinecone`, `weaviate` | `"chromadb"` |
| `CHROMA_PERSIST_DIRECTORY` | env | ChromaDB storage path | `".chroma_db"` |
| `PINECONE_API_KEY` | env | Pinecone API key (required if type=pinecone) | *none* |
| `PINECONE_ENVIRONMENT` | env | Pinecone environment (required if type=pinecone) | *none* |
| `PINECONE_INDEX_NAME` | env | Pinecone index name | `"kosmos"` |

---

### Neo4j Knowledge Graph Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `NEO4J_URI` | env | Connection URI. Read at `config.py:539` AND `api/health.py:336` (dual-read) | `"bolt://localhost:7687"` |
| `NEO4J_USER` | env | Username. Read at `config.py:544` AND `api/health.py:337` (dual-read) | `"neo4j"` |
| `NEO4J_PASSWORD` | env | Password. Read at `config.py:549` AND `api/health.py:338` (dual-read) | `"kosmos-password"` |
| `NEO4J_DATABASE` | env | Database name | `"neo4j"` |
| `NEO4J_MAX_CONNECTION_LIFETIME` | env | Connection lifetime | `3600` |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | env | Pool size | `50` |

---

### Safety Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_SAFETY_CHECKS` | env | Safety check toggle | `true` |
| `MAX_EXPERIMENT_EXECUTION_TIME` | env | Execution timeout (seconds) | `300` |
| `MAX_MEMORY_MB` | env | Memory ceiling | `2048` |
| `MAX_CPU_CORES` | env | CPU limit (None=unlimited) | *none* |
| `ENABLE_SANDBOXING` | env | Docker sandbox toggle | `true` |
| `REQUIRE_HUMAN_APPROVAL` | env | Human-in-the-loop gate | `false` |
| `ETHICAL_GUIDELINES_PATH` | env | Path to ethics JSON | *none* |
| `ENABLE_RESULT_VERIFICATION` | env | Result verification toggle | `true` |
| `OUTLIER_THRESHOLD` | env | Z-score outlier threshold | `3.0` |
| `DEFAULT_RANDOM_SEED` | env | Reproducibility seed | `42` |
| `CAPTURE_ENVIRONMENT` | env | Environment snapshot toggle | `true` |
| `APPROVAL_MODE` | env | Approval workflow mode | `"blocking"` |
| `AUTO_APPROVE_LOW_RISK` | env | Auto-approve toggle | `true` |
| `NOTIFICATION_CHANNEL` | env | Notification output | `"both"` |
| `NOTIFICATION_MIN_LEVEL` | env | Minimum notification severity | `"info"` |
| `USE_RICH_FORMATTING` | env | Rich console toggle | `true` |
| `INCIDENT_LOG_PATH` | env | Incident log path | `"safety_incidents.jsonl"` |
| `AUDIT_LOG_PATH` | env | Audit log path | `"human_review_audit.jsonl"` |

---

### Performance / Concurrency Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_RESULT_CACHING` | env | Result cache toggle | `true` |
| `CACHE_TTL` | env | Cache lifetime (seconds) | `3600` |
| `PARALLEL_EXPERIMENTS` | env | Parallel experiment count (0=sequential) | `0` |
| `ENABLE_CONCURRENT_OPERATIONS` | env | Concurrent research toggle | `false` |
| `MAX_PARALLEL_HYPOTHESES` | env | Concurrent hypothesis evals | `3` |
| `MAX_CONCURRENT_EXPERIMENTS` | env | Concurrent experiment limit | `10` |
| `MAX_CONCURRENT_LLM_CALLS` | env | Concurrent API call limit | `5` |
| `LLM_RATE_LIMIT_PER_MINUTE` | env | API rate limit | `50` |
| `ASYNC_BATCH_TIMEOUT` | env | Batch operation timeout | `300` |

---

### Local Model Tuning Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LOCAL_MODEL_MAX_RETRIES` | env | Retry count for local models | `1` |
| `LOCAL_MODEL_STRICT_JSON` | env | Strict JSON compliance | `false` |
| `LOCAL_MODEL_JSON_RETRY_HINT` | env | Retry with formatting hint | `true` |
| `LOCAL_MODEL_REQUEST_TIMEOUT` | env | Local model timeout | `120` |
| `LOCAL_MODEL_CONCURRENT_REQUESTS` | env | Max concurrent local requests | `1` |
| `LOCAL_MODEL_FALLBACK_UNSTRUCTURED` | env | Fallback to unstructured extraction | `true` |
| `LOCAL_MODEL_CB_THRESHOLD` | env | Circuit breaker failure threshold | `3` |
| `LOCAL_MODEL_CB_RESET_TIMEOUT` | env | Circuit breaker reset delay | `60` |

[ABSENCE] These `LocalModelConfig` settings are defined in `config.py:752-822` but not wired into the provider implementations. The LiteLLM and OpenAI providers do not read `LocalModelConfig`. This is configuration infrastructure that exists but is not yet consumed.

---

### World Model Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `WORLD_MODEL_ENABLED` | env | Knowledge graph toggle | `true` |
| `WORLD_MODEL_MODE` | env | Storage mode: `simple` or `production` | `"simple"` |
| `WORLD_MODEL_PROJECT` | env | Default project namespace | *none* |
| `WORLD_MODEL_AUTO_SAVE_INTERVAL` | env | Auto-export interval | `300` |

---

### Monitoring Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_USAGE_STATS` | env | Usage stats toggle | `true` |
| `METRICS_EXPORT_INTERVAL` | env | Export interval (seconds) | `60` |

---

### Development Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `HOT_RELOAD` | env | Hot reload toggle | `false` |
| `LOG_API_REQUESTS` | env | API request logging | `false` |
| `TEST_MODE` | env | Test mock mode | `false` |

---

### NOT MODELED IN PYDANTIC (read via raw `os.getenv()`)

These env vars are consumed directly without Pydantic validation. They bypass the typed config system entirely.

#### Alerting

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ALERT_EMAIL_ENABLED` | env (raw) | Enable email alerts. `monitoring/alerts.py:362,543` | `"false"` |
| `ALERT_EMAIL_FROM` | env (raw) | Sender email. `monitoring/alerts.py:371` | `"alerts@kosmos.ai"` |
| `ALERT_EMAIL_TO` | env (raw) | Recipient email. `monitoring/alerts.py:372` | `"admin@example.com"` |
| `SMTP_HOST` | env (raw) | SMTP server. `monitoring/alerts.py:390` | `"localhost"` |
| `SMTP_PORT` | env (raw) | SMTP port. `monitoring/alerts.py:391` | `"587"` |
| `SMTP_USER` | env (raw) | SMTP username. `monitoring/alerts.py:392` | *none* |
| `SMTP_PASSWORD` | env (raw) | SMTP password. `monitoring/alerts.py:393` | *none* |
| `ALERT_SLACK_ENABLED` | env (raw) | Enable Slack alerts. `monitoring/alerts.py:415,546` | `"false"` |
| `SLACK_WEBHOOK_URL` | env (raw) | Slack webhook. `monitoring/alerts.py:421` | *none* |
| `ALERT_PAGERDUTY_ENABLED` | env (raw) | Enable PagerDuty. `monitoring/alerts.py:483,549` | `"false"` |
| `PAGERDUTY_INTEGRATION_KEY` | env (raw) | PagerDuty key. `monitoring/alerts.py:493` | *none* |

#### Utilities

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `KOSMOS_SKILLS_DIR` | env (raw) | Custom skills directory. `agents/skill_loader.py:148` | *none* |
| `EDITOR` | env (raw) | Config file editor. `cli/commands/config.py:313` | `"nano"` |

#### Profiling (documented in `.env.example` / K8s only)

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_PROFILING` | env (raw) | Profiling toggle. `.env.example` only, `k8s/configmap.yaml` | `"false"` |
| `PROFILING_MODE` | env (raw) | Profiling depth. `.env.example` only, `k8s/configmap.yaml` | `"light"` |
| `STORE_PROFILE_RESULTS` | env (raw) | Store profiling data. `.env.example` only | `"true"` |
| `PROFILE_STORAGE_DAYS` | env (raw) | Profile retention. `.env.example` only | `"30"` |
| `ENABLE_BOTTLENECK_DETECTION` | env (raw) | Bottleneck detection toggle. `.env.example` only | `"true"` |
| `BOTTLENECK_THRESHOLD_PERCENT` | env (raw) | Bottleneck threshold. `.env.example` only | `"10"` |

---

### Domain-Specific API Keys (documented in `.env.example` only)

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `KEGG_API_KEY` | env | KEGG biology database | *none* |
| `UNIPROT_API_KEY` | env | UniProt protein database | *none* |
| `MATERIALS_PROJECT_API_KEY` | env | Materials Project API | *none* |
| `NASA_API_KEY` | env | NASA astronomy API | *none* |
| `DEEPSEEK_API_KEY` | env | DeepSeek (used via LiteLLM, not read by Kosmos directly) | *none* |

---

### Legacy / Backward Compatibility

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `MAX_PARALLEL_HYPOTHESIS_EVALUATIONS` | env | Superseded by `MAX_PARALLEL_HYPOTHESES`. `.env.example:406` only | `3` |
| `ENABLE_CONCURRENT_RESULT_ANALYSIS` | env | Legacy concurrent toggle. `.env.example:407` only | `true` |

---

### Config Access Patterns

#### Pattern 1: Pydantic-validated access via `get_config()` (dominant)

[PATTERN] The CLI, health checks, and initialization code use `get_config()` to obtain the typed `KosmosConfig` singleton, then access nested fields like `config.research.max_iterations`. Observed in `cli/commands/run.py:132`, `cli/commands/config.py:209`, and `core/providers/factory.py:83`.

#### Pattern 2: Flat dict for agents (bridge layer)

[FACT] Agents (`BaseAgent` subclasses) receive a `config: Dict[str, Any]` in their constructor (`base.py:117`), stored as `self.config` (a plain dict, line 129). The CLI's `run.py:147-170` constructs a `flat_config` dict by manually extracting values from the nested `KosmosConfig` object. Agents then access config via `self.config.get("key", default)`.

[PATTERN] 53 occurrences of `self.config.get(` across 9 files (agents, core/convergence, core/feedback, core/memory, hypothesis/refiner). This is the dominant pattern for agent-side config access.

#### Pattern 3: Direct `os.getenv()` / `os.environ.get()` (bypassing Pydantic)

[PATTERN] Several subsystems bypass `KosmosConfig` and read env vars directly:
- `api/health.py` (lines 226-338): reads `REDIS_ENABLED`, `REDIS_URL`, `ANTHROPIC_API_KEY`, `NEO4J_*` directly for health checks
- `monitoring/alerts.py` (lines 362-549): reads `ALERT_EMAIL_*`, `SMTP_*`, `SLACK_WEBHOOK_URL`, `PAGERDUTY_INTEGRATION_KEY` directly -- none of these are modeled in `KosmosConfig`
- `core/providers/factory.py` (lines 164-169): reads `LITELLM_*` directly as fallback when config object lacks LiteLLM sub-config
- `cli/commands/config.py` (lines 215-224): reads `LLM_PROVIDER`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` directly for validation display
- `agents/skill_loader.py` (lines 148-149): reads `KOSMOS_SKILLS_DIR` directly
- `cli/commands/config.py` (line 313): reads `EDITOR` for config editing

#### Pattern 4: Provider config dicts

[FACT] The provider factory (`core/providers/factory.py:83-175`) bridges between `KosmosConfig` and the flat dict that each provider `__init__` expects. Each provider (`AnthropicProvider`, `OpenAIProvider`, `LiteLLMProvider`) takes a `config: Dict[str, Any]` and extracts fields with `.get()` with fallbacks to `os.environ.get()`.

---

### Validation

[FACT] Validation is primarily Pydantic-native, using:
1. **Field constraints**: `ge`, `le`, `Literal` types (e.g., `temperature: float = Field(ge=0.0, le=1.0)`)
2. **`@model_validator`** at three locations:
   - `VectorDBConfig.validate_pinecone_config` (line 521): validates Pinecone-specific fields when Pinecone is selected
   - `KosmosConfig.sync_litellm_env_vars` (line 985): manually syncs LITELLM_* env vars into nested config because Pydantic doesn't auto-propagate to nested models
   - `KosmosConfig.validate_provider_config` (line 1024): ensures API key is present for the selected provider
3. **`BeforeValidator(parse_comma_separated)`**: custom parser for comma-separated list fields (`enabled_domains`, `enabled_experiment_types`, `debug_modules`)

[FACT] No runtime config validation exists beyond Pydantic initialization. If environment variables change after `get_config()` is called, the singleton retains stale values unless `reload=True` is passed.

---

### Conditional Sub-Config Instantiation

[FACT] Three optional provider configs use conditional factory functions (lines 896-919):
- `_optional_openai_config()`: only creates `OpenAIConfig` if `OPENAI_API_KEY` is set
- `_optional_anthropic_config()`: only creates `AnthropicConfig` if `ANTHROPIC_API_KEY` is set
- `_optional_claude_config()`: same as above (backward compat alias)

This means `config.openai` is `None` when OpenAI is not configured, and code must null-check before access.

---

### Dual-Read Pattern (GOTCHA)

[PATTERN] Several env vars are read in two places -- once by Pydantic during config initialization and again directly by subsystems. This affects 5 variables: `ANTHROPIC_API_KEY`, `REDIS_ENABLED`, `REDIS_URL`, `NEO4J_URI/USER/PASSWORD`. The health check system (`api/health.py`) bypasses Pydantic entirely, reading these directly from `os.getenv()`. This creates a risk of inconsistency if values are modified programmatically in the config singleton but not in the actual environment.

---

### Nested Env Var Propagation Issue (GOTCHA)

[FACT] The `sync_litellm_env_vars` model validator (line 985) exists specifically because Pydantic `BaseSettings` does not auto-propagate env vars from the parent `.env` file to nested `BaseSettings` submodels. This is a known Pydantic limitation, and only LiteLLM has this workaround. Other sub-configs may be similarly affected if they define their own `env_file`.

---

### Hidden Coupling in Configuration

#### The Flat Config Dict Anti-Pattern

[PATTERN] 3 places bridge structured config to flat dicts: `core/providers/factory.py:107-170`, `cli/commands/run.py:148-170`, and `core/llm.py:655-676`. Each manually extracts fields from Pydantic models into `dict[str, Any]`. There is no shared schema for these dicts, so each bridging point can drift independently.

[FACT] The `flat_config` dict keys (e.g., `"max_iterations"`, `"budget_usd"`, `"data_path"`) are string-based. No schema validates that `run.py` passes the right keys or that the director reads the right ones. A typo in either file fails silently. `cli/commands/run.py:148-170`

[FACT] `run.py:136-137` directly mutates the config singleton: `config_obj.research.enabled_domains = [domain]`. This means CLI parameter handling has side effects on the global config, potentially affecting other singletons that read from config later.

#### sync_litellm_env_vars Drift Risk

[FACT] The `sync_litellm_env_vars` validator at `config.py:986-1022` has a hardcoded `env_map` and `default_vals` dict that must stay in sync with `LiteLLMConfig` fields. Adding a new field to `LiteLLMConfig` without updating `sync_litellm_env_vars` means the env var won't be picked up from `.env`. `config.py:986-1022`

---

### Security Observations

1. [FACT] The `.env` file in the repo contains a real `DEEPSEEK_API_KEY` (`sk-925e...`) at line 16. This file is checked into git.
2. [FACT] `NEO4J_PASSWORD` has a hardcoded default `"kosmos-password"` in `config.py:549`, which means Neo4j will connect with a known password if no env var overrides it.
3. [FACT] The K8s secrets template (`k8s/secrets.yaml.template`) correctly separates secrets from the ConfigMap, requiring base64-encoded values at deployment time.
4. [FACT] `safety/reproducibility.py:208` filters environment captures to a safe whitelist: `PATH`, `PYTHONPATH`, `LANG`, `LC_ALL` -- no secrets leak into reproducibility snapshots.

---

### Kubernetes Surface

[FACT] A K8s ConfigMap (`k8s/configmap.yaml`) mirrors the `.env.example` structure for non-secret values. Secrets (`anthropic-api-key`, `postgres-password`, `neo4j-password`, optional `smtp-password`, `slack-webhook-url`, `pagerduty-key`) are in `k8s/secrets.yaml.template`. The deployment (`k8s/kosmos-deployment.yaml`) maps a subset of these into container env vars.

---

### Minimum Viable Environment

[FACT] To run Kosmos with the absolute minimum configuration:

**For Anthropic provider (default):**
```bash
ANTHROPIC_API_KEY=sk-ant-...   # or 999... for CLI proxy mode
```
Everything else has defaults. `LLM_PROVIDER` defaults to `"anthropic"`, database defaults to SQLite, Redis is disabled by default.

**For LiteLLM/local provider:**
```bash
LLM_PROVIDER=litellm
LITELLM_MODEL=ollama/llama3.1:8b
```
No API key needed for local models.

---

### Total Count

- **Total unique env vars**: ~105 distinct environment variables
- **Modeled in Pydantic**: ~85 (validated with types, ranges, defaults)
- **Read directly via os.getenv**: ~17 (no type validation, string-only)
- **Documentation-only**: ~8 (appear in .env.example but not consumed in code)
## Conventions

### Coding Conventions

1. **Always accept `(agent_id, agent_type, config)` as the base parameters for agent classes, call `super().__init__()` passing these parameters, and extract config values via `self.config.get(key, default)` rather than requiring typed constructor params.** [PATTERN: 6/6 agent subclasses -- HypothesisGeneratorAgent, ExperimentDesignerAgent, DataAnalystAgent, LiteratureAnalyzerAgent, ResearchDirectorAgent, StageOrchestrator and BaseAgent itself] [FACT: kosmos/agents/hypothesis_generator.py:62-88] Deviation: `ResearchDirectorAgent` adds a mandatory positional `research_question: str` before the standard triple [FACT: kosmos/agents/research_director.py:68-74] -- this is intentional. The 36 deviations flagged by X-Ray are predominantly parameterless `__init__(self)` in ~30 utility/singleton classes, Pydantic model `__init__` with typed Fields, and ~20 plain `@dataclass` uses -- all intentional, not oversights.

2. **Always declare `logger = logging.getLogger(__name__)` at module scope after imports. Never create loggers inside methods or classes. Never use `print()` for diagnostic output.** [PATTERN: 109/109 sampled source files] One deviation: `kosmos/models/experiment.py:18` uses `_experiment_logger = logging.getLogger(__name__)` to avoid shadowing the `logger` name used by Pydantic validators.

3. **Always use absolute imports from `kosmos.*` -- no relative imports (`from .module`). Always use `from kosmos.X import Y` style, not bare `import kosmos.X`. Type imports always come from `typing` as the first import group.** Import ordering: (1) module docstring, (2) standard library, (3) third-party, (4) internal `kosmos.*`. [PATTERN: 15/15+ modules sampled]

4. **Always define enums as `class X(str, Enum)` with lowercase string values. Never use bare `Enum` or integer-valued enums.** This ensures all enums are JSON-serializable strings. [PATTERN: 25/25+ enum definitions across the codebase] [FACT: kosmos/agents/base.py:25-35]

5. **Always provide both `get_X()` and `reset_X()` functions for singleton instances.** The `reset_X()` is critical for test isolation -- the conftest fixture `reset_singletons` calls all available reset functions. [PATTERN: 15/15+ modules: config, llm, event_bus, cache_manager, metrics, registry, literature_analyzer, etc.] [FACT: tests/conftest.py:332-386]

6. **Always use Google-style docstrings with `Args:`, `Returns:`, `Raises:` sections and inline `Example:` blocks for public methods. Class docstrings should list capabilities.** Private methods (`_method`) need only brief docstrings. [PATTERN: 6/6 agent classes, all model classes, all core modules sampled]

---

### Agent Pattern Conventions

7. **Every agent MUST inherit from `BaseAgent`, accept `(agent_id, agent_type, config)` in `__init__`, override `execute(task)`, set `self.status = AgentStatus.WORKING` at the start of `execute()`, set `self.status = AgentStatus.IDLE` in the `finally` block, and return a result dict or `AgentMessage`.** [PATTERN: 5/5 agent subclasses follow this contract exactly] [FACT: kosmos/agents/base.py:97-528]

8. **Always dispatch on a `task_type` or `action` field from the execute() input. Always catch exceptions, log them, and return an error response rather than raising. Always increment `self.tasks_completed` and `self.errors_encountered` appropriately.** The common try/except/finally structure with status management appears in all agent execute() methods. [PATTERN: 5/5 agents] Two `execute()` signatures coexist: dict-based (`Dict[str, Any] -> Dict[str, Any]`, used by DataAnalystAgent, LiteratureAnalyzerAgent) and message-based (`AgentMessage -> AgentMessage`, used by HypothesisGeneratorAgent, ExperimentDesignerAgent). The base class declares the dict-based signature; message-based is technically a Liskov substitution violation, though callers know which type they invoke. [FACT: base.py:485-497, data_analyst.py:160, hypothesis_generator.py:91]

9. **Never override `_on_pause()` or `_on_resume()` -- they are never called.** These lifecycle hooks are defined in `base.py:189-206` but `pause()` and `resume()` do NOT invoke them. They are dead code. Only `LiteratureAnalyzerAgent` overrides `_on_start()`/`_on_stop()` (to track runtime). [FACT: base.py:189-206, base.py:503-509, literature_analyzer.py:138-151]

10. **Always acquire service dependencies in `__init__` using factory functions (`get_client()`, `get_knowledge_graph()`, etc.), not during `_on_start()`. Wrap optional dependencies in try/except to degrade gracefully.** [PATTERN: 5/5 agent subclasses] [FACT: literature_analyzer.py:109-115 wraps knowledge_graph init in try/except]

11. **Name agent classes as `{Descriptive Role}Agent`. Pass `agent_type or "ClassName"` to super. Never hardcode an agent_type that differs from the class name.** [PATTERN: 6/6 agents follow this pattern]

---

### LLM Provider Conventions

12. **Always obtain LLM clients via `get_client()` from `kosmos.core.llm`, never by directly instantiating provider classes.** [PATTERN: 9/9 files -- all 5 agents and 4 non-agent modules use `from kosmos.core.llm import get_client; self.llm_client = get_client()`] Agents call either `self.llm_client.generate()` or `self.llm_client.generate_structured()` -- never directly constructing API calls. This means provider switching via config works transparently.

    **Known violations:**
    - `core/domain_router.py:157` -- creates `ClaudeClient()` directly, always uses Anthropic regardless of `LLM_PROVIDER`
    - `execution/code_generator.py:764` -- creates `ClaudeClient()` first, then falls back to LiteLLM. Ignores provider system.
    - `research_director.py:222-238` -- initializes a separate `AsyncClaudeClient` directly using `os.getenv("ANTHROPIC_API_KEY")`. Anthropic-hardcoded, does not respect `LLM_PROVIDER`.

13. **Never duplicate pricing data -- use the centralized `kosmos/core/pricing.py` module.** `get_model_cost()` at `pricing.py:54-86` handles exact, base-name, and family-keyword matching with a `(0.0, 0.0)` fallback. [PATTERN: Anthropic and LiteLLM providers use centralized pricing] **Known violation**: OpenAI provider has its own hardcoded pricing table (`openai.py:575-613`) duplicating data from `pricing.py`.

14. **The async LLM client (`AsyncClaudeClient`) is Anthropic-only and not pluggable to the provider abstraction.** It directly wraps `AsyncAnthropic` at `async_llm.py:269`. Only the AnthropicProvider emits LLM events, and only during streaming. Non-streaming `generate()` calls do not emit events. OpenAI and LiteLLM providers never emit events. [ABSENCE: No async provider abstraction exists]

---

### Error Handling Conventions

15. **Always wrap optional dependency initialization in try/except. Log at WARNING level. Set the dependency to None and disable the feature flag. Never let an optional dependency failure prevent the agent from starting.** [PATTERN: 5/5 agent classes and multiple core modules] [FACT: literature_analyzer.py:109-115]

16. **Never let one bad item crash a batch operation. Catch per-item, log the error, and continue processing remaining items.** [PATTERN: hypothesis_generator, experiment_designer, data_analyst] [FACT: hypothesis_generator.py:196-204]

---

### Testing Conventions

17. **Always mirror source package structure under `tests/unit/`. Name test files `test_{source_module}.py`.** Directory structure: `tests/unit/agents/`, `tests/unit/core/`, etc. [PATTERN: test file naming is always `test_{module_name}.py`]

18. **Always group related tests into a class named `Test{Concern}` with a docstring stating what is being tested. Always include `@pytest.mark.unit` or `@pytest.mark.integration` on each class or at module level.** Test methods start with `test_` and describe the scenario: `test_init_default`, `test_generate_hypotheses_success`, `test_empty_llm_response`. [PATTERN: 5/5 test files examined] [FACT: test_hypothesis_generator.py uses 7 test classes]

19. **Always use `pytestmark` at module level for service-dependency skips. Never use `@pytest.mark.skip` without a `reason`. Available markers: `unit`, `integration`, `e2e`, `slow`, `smoke`, `requires_api_key`, `requires_neo4j`, `requires_chromadb`, `requires_claude`.** [PATTERN: 3/3 agent test files use this exact pattern] [FACT: pytest.ini:26-41]

20. **Always use `Mock()` from `unittest.mock`, not third-party mocking libraries. Always use `AsyncMock` for async methods. Always name mock fixtures `mock_{thing}` and real fixtures without the prefix.** Mock fixtures return `unittest.mock.Mock` objects with pre-configured return values. Real service fixtures include skip logic. [PATTERN: conftest.py provides 6+ mock fixtures following identical pattern] [FACT: conftest.py provides mock_llm_client, mock_anthropic_client, mock_knowledge_graph, mock_vector_db, mock_concept_extractor, mock_cache]

21. **Always reset singletons in test fixtures.** The autouse `reset_singletons` fixture handles most cases, but module-specific resets may be needed (e.g., `reset_event_bus()`). [FACT: tests/conftest.py:332-393, test_event_bus.py:24-29]

22. **Use `@patch('kosmos.module.dependency')` for database and external service mocking. Use real API calls for LLM tests (marked with `requires_claude`). Always use `store_in_db=False` in tests that don't need database interaction.** Two mocking approaches coexist intentionally: real Claude API calls for LLM-dependent tests and mocked dependencies for isolation. [PATTERN: consistent across all agent test files]

23. **Define data-construction helpers as module-level functions (not in conftest.py) when they are specific to one test file. Use `unique_id()` to prevent test interference from cached data.** [PATTERN: 3/5 test files examined] [FACT: test_data_analyst.py:39-95 defines `unique_id()`, `make_metadata()`, `make_result()`]

24. **Never add tests that run longer than 300 seconds. Always declare custom markers in pytest.ini before using them.** Key pytest.ini settings: `asyncio_mode = auto`, `--cov-fail-under=80`, `--strict-markers`, `timeout = 300`, `log_file = tests/test_run.log`. [FACT: pytest.ini:1-69]

---

### Data Model Conventions

25. **Always define runtime models as Pydantic `BaseModel` with `Field(...)` validators. Always define DB models as SQLAlchemy with `Column()`. Perform conversion in the agent methods that touch the database.** Hypothesis, Experiment, and Result each have both Pydantic (in `kosmos/models/`) and SQLAlchemy (in `kosmos/db/models.py`) representations. [PATTERN: all three domain entities follow dual model pattern]

26. **Always use `Field(...)` with `description=` for all Pydantic model fields. Use `field_validator` with `@classmethod` for custom validation. Score fields use `Field(None, ge=0.0, le=1.0)` bounds. Include `to_dict()` method for serialization.** [PATTERN: all Pydantic models in `kosmos/models/`] [FACT: hypothesis.py:50-84, experiment.py:42-68, result.py:61-103]

---

### Hidden Coupling Conventions

27. **Never rename `_DEFAULT_CLAUDE_SONNET_MODEL` or `_DEFAULT_CLAUDE_HAIKU_MODEL` from `config.py` without updating all consumers -- they are underscore-prefixed "private" constants that are effectively public API.** [PATTERN] These two constants from `config.py:17-18` are imported by 7+ files: `core/providers/anthropic.py`, `core/providers/litellm_provider.py`, `core/llm.py`, `validation/scholar_eval.py`, `compression/compressor.py`, `orchestration/plan_reviewer.py`, `orchestration/plan_creator.py`, `models/hypothesis.py`, `models/experiment.py`, `models/domain.py`.

28. **Never change the string `"ExperimentDesignerAgent"` used for agent-type message routing without updating all message handlers.** The Research Director routes messages via type-string matching (`sender_type == "ExperimentDesignerAgent"` at `research_director.py:582-583`). A rename breaks routing silently. Both agents share implicit contracts about Hypothesis model format, Experiment protocol format, and message payload dict keys. [FACT: research_director.py:582-583] Risk: MEDIUM.

29. **When modifying `ExperimentCodeGenerator.generate()`, always check `research_director.py:1528-1564` which lazy-imports and calls it.** The lazy import at `research_director.py:1528` hides the dependency from static analysis. The code generator also generates Python code strings that reference Kosmos internal modules, creating tertiary dependencies. [FACT: research_director.py:1528, 1537-1538, 1564] Risk: MEDIUM.

30. **When adding new config fields to `LiteLLMConfig`, always update the `sync_litellm_env_vars` validator at `config.py:986-1022`.** The validator has a hardcoded `env_map` and `default_vals` dict that must stay in sync with `LiteLLMConfig` fields. Failing to update means the env var won't be picked up from `.env`. Risk: LOW-MEDIUM.

31. **When adding new config options to `ResearchDirectorAgent`, always update the `flat_config` dict in `cli/commands/run.py:148-170`.** The flat_config dict keys are string-based with no schema validation. A typo in either file fails silently. [PATTERN: 3/3 config bridging points use this unvalidated flat-dict pattern] [FACT: cli/commands/run.py:148-170]

32. **Providers `anthropic.py` and `openai.py` are co-modified siblings sharing the `LLMProvider` ABC. When the base interface changes, both must update.** Feature asymmetry exists: caching, auto model selection, and event bus integration are Anthropic-only. [FACT: anthropic.py:36, openai.py:32, both from core/providers/base.py] Risk: LOW (ABC enforces at import time).
## Gotchas

1. **Sandbox return value silently lost** -- DockerSandbox extracts return values via stdout "RESULT:" prefix lines, but all code templates store results in a local variable `results`. Non-sandbox path extracts correctly via `exec_locals.get('results')`. Sandbox path silently returns `None` for `return_value`, losing all experiment result data. (See Critical Path 5, Step 3 for the execution flow.) [FACT] (`sandbox.py:442`, `code_generator.py:187`)

2. **exec() runs with __builtins__ exposed when Docker unavailable** -- When `use_sandbox=False` (default when Docker unavailable), `exec()` runs with `__builtins__` in globals. The restricted import list provides some guardrails, but arbitrary code execution is possible. Docker sandbox provides real isolation when enabled, but the fallback is silent -- no warning that code is running without filesystem/network isolation. [FACT] (`executor.py:617`, `executor.py:474-475`, `executor.py:216-221`)

3. **Security bypass via type.__getattribute__ in restricted builtins** -- `SAFE_BUILTINS` includes `type` and `object` but NOT `getattr`/`setattr`/`delattr`. However, `type.__getattribute__` can be used to bypass the restriction entirely since `type` is in the whitelist. [FACT] (`executor.py:594-597`)

4. **_reset_eval_state() drops ALL database tables** -- Each evaluation phase (2, 3, 4) calls `reset_database()` which does `Base.metadata.drop_all()`. The evaluation does NOT create a separate database -- it uses whatever `config.database.normalized_url` points to. If shared with production data, this destroys everything. (See Critical Path 10, Phase 2 for context.) [FACT] (`scientific_evaluation.py:56-60`, `db/__init__.py:200-201`)

5. **run_tier1() destructively deletes kosmos.db and .kosmos_cache** -- Before every persona evaluation run, the production database file and cache directory are deleted for "clean evaluation." Destroys any prior application state on the machine. [FACT] (`run_persona_eval.py:186-190`)

6. **LEAKED API KEY IN GIT** -- The `.env` file in the repo contains a real `DEEPSEEK_API_KEY` (`sk-925e...`) at line 16. This file is checked into git. [FACT] (`env_dependencies.md`)

7. **HARDCODED DEFAULT NEO4J PASSWORD** -- `NEO4J_PASSWORD` has a hardcoded default `"kosmos-password"` in `config.py:549`, which means Neo4j will connect with a known password if no env var overrides it. Docker health check also hardcodes `neo4j`/`kosmos-password` credentials. [FACT] (`config.py:549`, `graph.py:155-156`)

8. **Auto-fix inserts forbidden imports** -- `RetryStrategy.COMMON_IMPORTS` includes `'os': 'import os'`, but `os` is on the `DANGEROUS_MODULES` list. Auto-fix for NameError can insert an import that the validator would reject. [FACT] (`code_validator.py:36`, `executor.py:686`)

9. **Pattern detection matches inside comments and strings** -- `_check_dangerous_patterns()` uses `if pattern in code:` (raw string matching). `# eval(` or `description = "do not eval("` triggers a CRITICAL violation. Not AST-based. [FACT] (`code_validator.py:288`)

10. **Convergence check passes empty results=[]** -- In `_check_convergence_direct()`, the `results` list is never populated from DB. The convergence detector relies on `research_plan` counts instead, meaning convergence decisions are made without examining actual experiment results. (See Critical Path 8 for the convergence pipeline flow.) [FACT] (`research_director.py:1237-1238`, `research_director.py:1267-1271`)

11. **time.sleep() blocks asyncio event loop in error recovery and retry** -- `_handle_error_with_recovery()` uses blocking `time.sleep([2, 4, 8])`. Since `execute()` and all `_handle_*_action()` methods are async, the entire event loop thread freezes during error backoff. Same issue in executor retry loop. [FACT] (`research_director.py:674`, `executor.py:335`)

12. **random_seed=0 silently replaced with 42** -- Templates use `getattr(protocol, 'random_seed', 42) or 42`. Zero is falsy, so valid seed 0 is overridden. [FACT] (`code_generator.py:89`)

13. **BudgetExceededError never caught** -- Propagates as unhandled exception, potentially crashing research run. May be intentional but undocumented. [FACT] (`core/metrics.py:63`) [ABSENCE: no `except BudgetExceededError` found]

14. **LLM enhancement is a no-op** -- `_enhance_protocol_with_llm()` calls the LLM but never parses or applies the response. Logs "LLM enhancements applied" but returns protocol unchanged. Burns API tokens for nothing. [FACT] (`experiment_designer.py:714-717`)

15. **Write-mode detection is incomplete** -- Misses `'wb'`, `'ab'`, `'r+'`, and variable-based mode arguments. `open(f, 'wb')` passes the write check when `allow_file_read=True`. [FACT] (`code_validator.py:296-297`)

16. **Approval request truncates code to 500 chars** -- Dangerous patterns at character 501+ are not visible to the human reviewer. [FACT] (`code_validator.py:510`)

17. **getattr() flagged as CRITICAL** -- Common safe pattern (`getattr(obj, 'attr', default)`) fails validation even when usage is benign. Generated code using `getattr` will not pass. [FACT] (`code_validator.py:338`)

18. **Windows timeout cannot kill stuck computation** -- `ThreadPoolExecutor` timeout only stops waiting. The stuck thread continues consuming resources indefinitely. [FACT] (`executor.py:621-630`)

19. **run_until_complete() in running event loop** -- Sequential fallback in `execute_experiments_batch()` raises `RuntimeError` if called from async context. Only taken when concurrent execution disabled. [FACT] (`research_director.py:2171-2174`)

20. **DB init failure masked as warning** -- Real DB errors logged as warning; director continues without working database, causing cascading failures when handlers query DB. [FACT] (`research_director.py:131-139`)

21. **LLMResponse with empty content is falsy** -- `if not response:` incorrectly treats empty but successful LLM response as failure. [FACT] (`providers/base.py:98-99`)

22. **String methods on LLMResponse lose metadata** -- `response.strip()` returns `str`, not `LLMResponse`. After any string method, `.usage`, `.model`, `.finish_reason` are lost. [FACT] (`providers/base.py:107-108`)

23. **Cost estimation hardcodes wrong model** -- `get_usage_stats()` hardcodes `"claude-sonnet-4-5"` for cost lookup regardless of actual model used. [FACT] (`llm.py:519`)

24. **ExperimentResult timestamps are fake** -- `start_time=_now, end_time=_now, duration_seconds=0.0`. Analysis code relying on execution duration gets 0. [FACT] (`research_director.py:1704-1722`)

25. **Different execute() signatures across agents (Liskov violation)** -- `HypothesisGeneratorAgent.execute` takes `AgentMessage`, returns `AgentMessage`. `LiteratureAnalyzerAgent.execute` takes `Dict`, returns `Dict`. `BaseAgent.execute` signature is `(task: Dict) -> Dict`. Works only because callers know specific agent types. [FACT] (`hypothesis_generator.py:91`, `literature_analyzer.py:153`, `base.py:485-497`)

26. **Novelty checking is fail-open at two levels** -- If `kosmos.hypothesis.novelty_checker` cannot be imported, ALL hypotheses pass without any novelty scoring. Additionally, if `check_novelty()` throws for a single hypothesis, that hypothesis is kept. [FACT] (`hypothesis_generator.py:227-228`, `hypothesis_generator.py:223-224`)

27. **Novelty threshold inversion** -- `NoveltyChecker` receives `similarity_threshold = 1.0 - min_novelty_score`. Default `min_novelty_score=0.5` yields `similarity_threshold=0.5`, lower than `NoveltyChecker`'s own default of `0.75`. [FACT] (`hypothesis_generator.py:211`)

28. **Basic fallback template lacks synthetic data** -- `_generate_basic_template()` uses `pd.read_csv(data_path)` without synthetic fallback. Unlike all other templates, will crash if `data_path` not set. Combined with `FileNotFoundError` being terminal in retry (returns `None`, breaking retry loop), this is a dead end. [FACT] (`code_generator.py:964`, `executor.py:879-906`)

29. **Workflow state can diverge** -- `ResearchPlan.current_state` synced only inside `transition_to()`. Direct modification of `workflow.current_state` (public attribute) causes silent divergence. [FACT] (`workflow.py:323-325`)

30. **CONVERGED is not terminal** -- `CONVERGED -> GENERATING_HYPOTHESES` allowed. Callers assuming convergence is final may be surprised. [FACT] (`workflow.py:212-213`)

31. **No PAUSED state memory** -- PAUSED can resume to 6 different states but no mechanism remembers which state was active before pausing. [FACT] (`workflow.py:214-221`)

32. **World model factory NOT thread-safe** -- Explicitly documented. `_world_model` global has no lock, unlike `_default_client`. [FACT] (`world_model/factory.py:38`)

33. **Silent fallback to in-memory world model** -- If Neo4j is down, switches silently. Data lost on restart. Only a log warning signals this. [FACT] (`factory.py:123-133`)

34. **Neo4j triple-silent-swallow** -- Three consecutive `except Exception: pass` with zero logging. Makes Neo4j debugging nearly impossible. [FACT] (`world_model/simple.py:926,937,955`)

35. **Sync message_queue unbounded memory leak** -- Messages appended but never removed from sync list in long-running agents. [FACT] (`base.py:136-138`)

36. **Dead code in agent infrastructure (3 instances)** -- (a) `_on_pause()` and `_on_resume()` lifecycle hooks exist in `BaseAgent` but are never called by `pause()` and `resume()` -- do not override them expecting invocation (`base.py:513-517`, `base.py:189-206`). (b) `register_message_handler()` stores handlers in a dict but `process_message()` does NOT dispatch to them -- the handlers dict is dead code unless a subclass explicitly reads it (`base.py:406-415`). (c) `AgentRegistry.register(director)` at `run.py:182` sets up message routing, but all agents use direct calls per the Issue #76 fix -- the registry registration is cosmetic (`research_director.py:1391-1397`, `registry.py:70-97`). [FACT]

37. **Cannot restart from ERROR** -- `start()` only works from CREATED state. Agent in ERROR cannot be restarted. [FACT] (`base.py:161-163`)

38. **Dual locking without mutual exclusion** -- Async locks and threading locks exist side-by-side, but sync `_workflow_context()` yields workflow without any lock. No mutual exclusion between async and sync paths. [FACT] (`research_director.py:192-200`, `research_director.py:376-379`)

39. **DUAL-READ ENV VARS CREATE INCONSISTENCY RISK** -- 5 variables (`ANTHROPIC_API_KEY`, `REDIS_ENABLED`, `REDIS_URL`, `NEO4J_URI/USER/PASSWORD`) are read both by Pydantic during config init and directly via `os.getenv()` in `api/health.py`. If values are modified programmatically in the config singleton but not in the actual environment, the health check system will read stale/different values. [PATTERN] (`env_dependencies.md`)

40. **Config bridging is unvalidated and mutation-prone** -- (a) `run.py:136-137` directly mutates the global config singleton (`config_obj.research.enabled_domains = [domain]`), creating side effects on any other code that reads from the config singleton later. (b) The `flat_config` dict bridging from `KosmosConfig` to agents (`cli/commands/run.py:148-170`) uses string keys with no schema validation. A typo in either the bridging code or agent `self.config.get()` calls fails silently with default values. Three separate bridging points exist (`run.py`, `factory.py`, `llm.py`), each manually extracting fields with no shared schema, allowing independent drift. [FACT] (`hidden_coupling.md`)

41. **PRIVATE CONSTANTS ARE EFFECTIVELY PUBLIC API** -- `_DEFAULT_CLAUDE_SONNET_MODEL` and `_DEFAULT_CLAUDE_HAIKU_MODEL` from `config.py:17-18` are underscore-prefixed but imported by 7+ files. Renaming or removing them breaks consumers with no warning. [PATTERN] (`hidden_coupling.md`)

42. **STRING-BASED AGENT ROUTING IS FRAGILE** -- The Research Director routes messages via `sender_type == "ExperimentDesignerAgent"` string matching at `research_director.py:582-583`. Renaming an agent class breaks routing silently. [FACT] (`hidden_coupling.md`)

43. **Five components bypass the LLM provider abstraction** -- (a) `core/domain_router.py:157` creates `ClaudeClient()` directly, always using Anthropic regardless of `LLM_PROVIDER` config. (b) `execution/code_generator.py:764` creates `ClaudeClient()` first, falls back to LiteLLM -- ignores provider system. (c) `plan_creator.py:158-162` uses raw `anthropic_client.messages.create()` directly -- no caching, no cost tracking, no retry. (d) `plan_reviewer.py:125-129` also uses raw `anthropic_client.messages.create()` directly -- same bypass. Both plan_creator and plan_reviewer additionally catch ALL exceptions and fall back to mock plans, masking bugs (`plan_creator.py:194-198`, `plan_reviewer.py:161-162`). (e) `research_director.py:222-238` initializes `AsyncClaudeClient` using `os.getenv("ANTHROPIC_API_KEY")` directly, not respecting `LLM_PROVIDER` and running its own independent rate limiter and circuit breaker. [FACT] Consequence: switching `LLM_PROVIDER` to OpenAI or LiteLLM does not affect these 5 components. Cost tracking underreports because their API calls are not metered.

44. **Most retry fixes are try/except wrappers** -- 8 of 11 error-type fixes simply wrap code in try/except, producing `results = {'error': ..., 'status': 'failed'}` rather than fixing the underlying issue. Callers must check `return_value` for failure, not just `success` flag. [FACT] (`executor.py:869-1008`)

45. **Phase evaluations exit code ignores failures** -- `main()` always returns 0 unless Phase 1 fails. Phases 2-7 can all FAIL with exit code still 0. [FACT] (`scientific_evaluation.py:1451`)

46. **Phase 5 keyword heuristics** -- Quality scored by searching for "specific", "measurable", "mechanism" in first 500 chars of plan text. Fragile and not measuring actual quality. [FACT] (`scientific_evaluation.py:741-747`)

47. **Phase 6 checks source strings, not runtime** -- Rigor checks look for string "shapiro" in `inspect.getsource()`. Verifies template contains the word, not that checks execute at runtime. [FACT] (`scientific_evaluation.py:831-833`, `scientific_evaluation.py:870-875`)

48. **Lossy markdown round-trip** -- `parse_tier1_results` extracts stats from markdown via regex instead of from original `PhaseResult` objects. If markdown format changes, parsing breaks silently (returns 0/0/0.0). [FACT] (`run_persona_eval.py:244-249`)

49. **run_phase2_tests.py hardcodes machine path** -- `os.chdir("/mnt/c/python/Kosmos")` at module level. Machine-specific path that fails on any other machine. [FACT] (`run_phase2_tests.py:16`)

50. **get_session() auto-commits on context exit** -- Every `with get_session()` block commits on normal exit. Code that calls explicit `session.commit()` after `session.add()` double-commits -- the explicit commit succeeds, the context manager commit is a no-op. Agents bypass CRUD validation by using direct `session.add()` + `session.commit()` instead of CRUD functions, skipping `_validate_json_dict` / `_validate_json_list`. [FACT] (`db/__init__.py:131-133`, `hypothesis_generator.py:474-492`, `experiment_designer.py:888-903`)

51. **_actions_this_iteration uses lazy hasattr initialization** -- Not initialized in `__init__`. Created via `self._actions_this_iteration = 0` on first access via hasattr check. [FACT] (`research_director.py:2451-2453`)

52. **Budget enforcement re-imports get_metrics() on every call** -- Import inside function body, re-imported each time. Fails silently if metrics module unavailable (ImportError caught). [FACT] (`research_director.py:2406-2425`)

53. **_json_safe() is a nested function recreated per call** -- Defined inside `_handle_execute_experiment_action()`. Handles numpy/sklearn types but falls back to `str()` for unknowns, losing structured data for sklearn models, matplotlib figures, etc. [FACT] (`research_director.py:1595-1613`)

54. **Vague language check is warn-only** -- `_validate_hypothesis()` detects "maybe", "might" but does NOT reject. Comment: "Don't fail, but warn." [FACT] (`hypothesis_generator.py:451-455`)

55. **Literature context uses only top 5 of 10 fetched papers** -- Even though up to 10 papers fetched (`max_papers_context=10`), only first 5 included in LLM prompt, abstracts truncated to 200 chars. [FACT] (`hypothesis_generator.py:346-347`)

56. **CLI mode detection edge case** -- `self.api_key.replace('9', '') == ''` -- any key of all 9s triggers CLI mode. Empty string would also match but is prevented by ValueError at line 163. [FACT] (`llm.py:179`)

57. **_extract_code_from_response weak heuristic** -- If LLM response has no code fences, checks for "import", "def ", or "=". Natural language containing "=" treated as code. [FACT] (`code_generator.py:907-924`)

58. **LLM client failure silently disables generation** -- If both `ClaudeClient` and `LiteLLMProvider` fail in `ExperimentCodeGenerator.__init__`, `self.use_llm = False` silently. [FACT] (`code_generator.py:762-778`)

59. **tenacity missing = no retry, no warning** -- API calls silently run without retry protection if tenacity not installed. [FACT] (`core/async_llm.py:33-39`)

60. **Anthropic SDK errors re-wrapped** -- All Anthropic exceptions become `ProviderAPIError`, losing original type. `raw_error` preserved but callers rarely check. [FACT] (`anthropic.py:340-342`)

61. **_update_usage_stats skips zero cost** -- `if usage.cost_usd:` check skips `0.0` (falsy). Free-tier calls with `cost_usd=0.0` not accumulated. [FACT] (`providers/base.py:401`)

62. **Ethical keyword false positives** -- Keywords like "email", "password", "harm", "survey" trigger violations in legitimate scientific code (e.g., bioinformatics analyzing "harmful mutations"). [FACT] (`code_validator.py:118-119`)

63. **Code parsed up to 3 times** -- `_check_syntax()`, `_check_dangerous_imports()`, and `_check_ast_calls()` each parse independently with `ast.parse()`. [FACT] (`code_validator.py:237`, `code_validator.py:252`, `code_validator.py:332`)

64. **Dimension weights defined but unused** -- `DIMENSION_WEIGHTS` dict exists in plan_reviewer but approval uses simple arithmetic mean. Someone adding weighted scoring may assume weights are applied. [FACT] (`plan_reviewer.py:68-69`)

65. **is_recoverable() order-dependent** -- Recoverable patterns checked before non-recoverable. Ambiguous messages (containing both "timeout" and "invalid") default to recoverable. [FACT] (`providers/base.py:466-477`)

66. **Load-bearing dead code** -- `if False: yield` in `generate_stream_async` makes Python treat function as async generator. Removing it changes type from async generator to coroutine, breaking `async for` callers. [FACT] (`providers/base.py:360-363`)

67. **_validate_query says "truncating" but doesn't truncate** -- Log says "truncating to 1000" but returns True without modifying the query. [FACT] (`base_client.py:248-250`)

68. **validate_steps silently sorts steps** -- Side effect hidden in a Pydantic validator. Steps reordered by `step_number`. Input order not preserved. [FACT] (`experiment.py:438`)

69. **to_dict() is hand-written, not model_dump()** -- The 100-line `to_dict()` method in ExperimentProtocol manually serializes every field. Adding a new field without updating it means silent data loss. [FACT] (`experiment.py:471-573`)

70. **create_authored increments paper_count every call** -- Regardless of merge. Calling it twice for the same pair produces `paper_count = 2` instead of 1. Same issue affects `create_discusses` (frequency) and `create_uses_method` (usage_count). [FACT] (`graph.py:615-616`, `graph.py:659`, `graph.py:703`)

71. **Cypher injection via f-string** -- `depth` and `max_hops` interpolated into Cypher queries. Typed as `int` but no validation prevents string injection if callers pass unexpected types. [FACT] (`graph.py:761`, `graph.py:917`)

72. **ExperimentType lives in hypothesis.py, not experiment.py** -- Anyone looking for it in experiment.py will find only a re-import. Moving it would break experiment.py:14 and dozens of experiment templates. 48 importers affected. [FACT] (`hypothesis.py:15-19`, `experiment.py:14`)

73. **datetime.utcnow() deprecated** -- Used in multiple locations as default_factory. Deprecated in Python 3.12+. Produces naive datetimes. [FACT] (`hypothesis.py:76-77`, `result.py:203`, `logging.py:52`)

74. **setup_logging() clears ALL root logger handlers** -- Calling it a second time silently destroys all previously-configured handlers, including any added by libraries. [FACT] (`logging.py:179`)

75. **TextFormatter mutates shared LogRecord** -- When colors are on, `record.levelname` is mutated in place. If the same record is processed by both TextFormatter and JSONFormatter, the JSON output will contain ANSI escape codes. [FACT] (`logging.py:128`)

76. **generate_stream counts text chunks as "tokens"** -- `total_tokens += 1` per text chunk, not per actual token. The `completion_tokens` field in emitted events is wrong. [FACT] (`anthropic.py:731-732`)

77. **Cache hits bypass usage tracking** -- `_update_usage_stats` is NOT called on cache hits. `self.total_input_tokens` and `self.total_cost_usd` undercount when cache is active. [FACT] (`anthropic.py:228-249`)

78. **generate_async does not call _update_usage_stats** -- Async calls don't contribute to running totals, inconsistent with sync `generate`. [FACT] (`anthropic.py:400-430`)

79. **get_untested_hypotheses() is O(n*m)** -- Uses list comprehension with `if h not in self.tested_hypotheses` (list, not set). Called repeatedly by `decide_next_action()`. [FACT] (`workflow.py:149-151`)

80. **Keyword fallback indexes papers into vector DB** -- Side-effect that enriches vector DB as a byproduct of novelty checking. Not documented behavior. [FACT] (`novelty_checker.py:207-210`)

81. **File cache TTL 24 hours, stale entries not deleted** -- Stale cache entries return None but are not cleaned up, accumulating on disk. [FACT] (`literature_analyzer.py:1019`)

82. **Convergence rollout_tracker.increment("literature") is misleading** -- Convergence action increments "literature" rollout counter even though no literature search is performed. Inflates reported count. [FACT] (`research_director.py:1350`)

83. **novelty_trend grows without bound** -- Every `check_convergence` call appends. Long-running research accumulates an unbounded list inside the Pydantic model. [FACT] (`convergence.py:562`)

84. **Flat novelty score is "declining"** -- Uses `>=` comparison, so constant scores trigger stop. [FACT] (`convergence.py:424`)

85. **sync_litellm_env_vars DRIFT** -- The validator at `config.py:986-1022` has a hardcoded `env_map` that must stay in sync with `LiteLLMConfig` fields. Adding a field to `LiteLLMConfig` without updating this validator means the env var won't be picked up from `.env`. [FACT] (`hidden_coupling.md`)

86. **DUPLICATE PRICING TABLE** -- OpenAI provider has its own hardcoded pricing table (`openai.py:575-613`) that duplicates and can drift from the centralized `pricing.py`. [FACT] (`llm_providers.md`)

87. **LOCAL MODEL CONFIG DEFINED BUT UNUSED** -- `LocalModelConfig` settings (`config.py:752-822`) are defined but not wired into the LiteLLM or OpenAI providers. [ABSENCE] (`llm_providers.md`)

88. **17 ENV VARS BYPASS PYDANTIC VALIDATION** -- Alerting, profiling, `KOSMOS_SKILLS_DIR`, and `EDITOR` are read via raw `os.getenv()` with no type validation. [FACT] (`env_dependencies.md`)

89. **_send_to_convergence_detector deprecated but not removed** -- Returns dummy `AgentMessage`. If called, silently works but return value meaningless. [FACT] (`research_director.py:1981-2003`)

90. **generate_with_messages() bypasses cache** -- Unlike `generate()`, multi-turn messages have no caching. Also ignores auto-model selection. [FACT] (`llm.py:367-408`)

91. **vector_db clear() has no null guard** -- If ChromaDB is unavailable, calling `clear()` will raise `AttributeError: 'NoneType' object has no attribute 'delete_collection'`. All other methods check `self.collection is None` but `clear()` does not. [FACT] (`vector_db.py:370-371`)

92. **SPECTER model download at construction** -- The embedder is initialized at `__init__` time. If the SPECTER model is not downloaded, this triggers a ~440MB download during construction. [FACT] (`vector_db.py:103`)

93. **vector_db singleton not thread-safe** -- Concurrent calls to `get_vector_db()` during initialization could create multiple instances. [FACT] (`vector_db.py:443-477`)

94. **compare_runs.py check regex requires single-word names** -- Pattern `\w+` won't match hyphens/spaces/dots. Currently safe because names use underscores, but fragile. [FACT] (`compare_runs.py:66-67`)

95. **Paper claims keyed by integer** -- If markdown changes claim numbering between versions, diff shows false changes. [FACT] (`compare_runs.py:118-119`)

96. **Citation graph caps at 50+50** -- Only first 50 references and 50 citations added to Neo4j per paper from Semantic Scholar. [FACT] (`literature_analyzer.py:821`, `literature_analyzer.py:838`)

97. **ResultExport.export_markdown() crashes on None stats** -- Formats variable stats with `{var.mean:.2f}` without null check. Since `mean`, `median`, `std`, `min`, `max` are all `Optional[float]`, this raises `TypeError`. [FACT] (`result.py:349-353`)

98. **Empty LLM protocol fallbacks** -- If Claude returns empty steps or variables, designer silently generates minimal defaults (3 generic steps, 2 generic variables). May not match actual hypothesis domain. [FACT] (`experiment_designer.py:568-601`)

99. **Phase 4 FAIL vs SKIP** -- Missing --data-path produces "FAIL" not "SKIP", counting against overall pass rate even when no dataset is intentionally provided. [FACT] (`scientific_evaluation.py:580-585`)

100. **asyncio.wait_for(timeout=120) per action** -- With 60 actions in Phase 3, worst-case 7200 seconds (2 hours). No aggregate timeout for entire evaluation. [FACT] (`scientific_evaluation.py:338-341`)

101. **use_enum_values=True serialization caveat** -- If you serialize and deserialize `ResearchPlan` or `WorkflowTransition`, enum fields come back as strings, not enum instances. `isinstance` checks against enum types fail, though `==` still works because `WorkflowState` is a `str` enum. [FACT] (`workflow.py:48`, `workflow.py:60`)

102. **Lazy imports hide dependencies** -- `research_director.py:1528` lazy-imports `ExperimentCodeGenerator`, and `anthropic.py:174` lazy-imports `get_config`. These runtime dependencies are invisible to static analysis and import-graph tools. [FACT] (`hidden_coupling.md`)

103. **DelegationManager raises RuntimeError at execution time** -- If required agent is not in the `agents` dict. No validation at init time. [FACT] (`delegation.py:395-399`)

104. **NO SYNC RETRY IN PROVIDERS** -- None of the three sync provider implementations have built-in retry logic. They catch exceptions and raise `ProviderAPIError`. Only the async path (Anthropic-only) has tenacity/circuit breaker. [ABSENCE] (`llm_providers.md`)

105. **Vector store Layer 3 is a stub** -- `pass` at line 567 in artifacts.py. [FACT] (`artifacts.py:560-567`)
## Hazards -- Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `kosmos-reference/` | ~500K+ | Complete duplicate of the Kosmos codebase stored as a reference copy. Reading these files wastes context -- use the actual source in `kosmos/` instead. |
| `runs/*/tier1/EVALUATION_REPORT.md` | ~20K each | Generated markdown evaluation reports. Multiple versions accumulate. Machine-generated output, not source truth. Read `scientific_evaluation.py` for the generation logic instead. |
| `runs/*/regression/*.json` | ~5K each | Generated comparison JSON from `compare_runs.py`. Machine output. Read the script source for logic. |
| `evaluation/run_phase2_tests.py` | ~8K | Hardcodes `os.chdir("/mnt/c/python/Kosmos")` at module level (`run_phase2_tests.py:16`). Machine-specific. Will mislead any agent that tries to run it. Read `scientific_evaluation.py` instead for evaluation logic. |
| `tests/integration/` | ~30K | Integration tests that require running Docker, Neo4j, and external APIs. Cannot be executed in most agent contexts. Read `tests/unit/` for testable behavior contracts. |
| `docs/archive/` | ~15K | Historical planning documents. Outdated design decisions that no longer reflect the codebase. `CLAUDE.md` explicitly warns: "Don't read archive/ for current architecture." |
| `kosmos/agents/research_director.py` (lines 1039-1219) | ~5K | Dead code: message-based `_send_to_*` methods. Issue #76 confirmed these silently fail. All real coordination uses `_handle_*_action()` methods (lines 1391-1979). Reading the dead send methods will mislead. |
| `kosmos/agents/research_director.py` (lines 1981-2003) | ~0.5K | Deprecated `_send_to_convergence_detector()`. Returns dummy `AgentMessage`. Dead code. |
| `kosmos/orchestration/plan_creator.py` (lines 292-346) | ~1.5K | Mock planning fallback. Generates deterministic mock tasks when LLM unavailable. Not representative of real behavior. |
| `kosmos/orchestration/plan_reviewer.py` (mock review path) | ~1K | Mock review fallback. Almost always approves structurally-valid plans. Not representative of real behavior. |
| `.env` | ~0.5K | Contains leaked `DEEPSEEK_API_KEY`. Should not be read by agents (risk of echoing secrets). Read `env_dependencies.md` or `config.py` for environment variable documentation instead. |
| `kosmos/core/providers/openai.py` (lines 575-613) | ~1K | Duplicate hardcoded pricing table. Drifts from centralized `pricing.py`. Read `pricing.py` for authoritative pricing data. |
| `kosmos/config.py` (lines 752-822) | ~2K | `LocalModelConfig` settings defined but never wired into any provider. Reading them suggests local model support exists when it does not. |
| `kosmos/world_model/artifacts.py` (vector store Layer 3) | ~0.5K | Stub implementation -- all methods are `pass`. No functionality. |
| `*.pyc`, `__pycache__/`, `.kosmos_cache/` | variable | Compiled bytecode and cache directories. No useful information for understanding the codebase. |
| `kosmos/execution/sandbox.py` (Docker config lines) | ~2K | Docker sandbox configuration details. Only relevant if Docker is available. The silent fallback to `exec()` (executor.py:216-221) means most runtime paths never use this. |
## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| Add a new agent | `kosmos/agents/base.py` (subclass `BaseAgent`, implement `execute()`) | `kosmos/agents/research_director.py` (lazy-init pattern at lines 145-152, add `_handle_*_action()` method), `kosmos/agents/registry.py` (registration), `kosmos/orchestration/delegation.py` (add to agents dict for plan execution) | `execute()` signature is not enforced -- `HypothesisGeneratorAgent` takes `AgentMessage`, `LiteratureAnalyzerAgent` takes `Dict`. Pick one and be consistent. `_on_pause()` and `_on_resume()` hooks are dead code -- do NOT rely on them (`base.py:513-517`). `start()` is one-shot from CREATED only (`base.py:161-163`). Message routing via registry is dead code (Issue #76); use direct calls instead. |
| Add a new LLM provider | `kosmos/core/providers/base.py` (subclass `LLMProvider`, implement abstract methods) | `kosmos/core/llm.py` (register in `get_client()`/`get_provider()` factory at lines 613-679), `kosmos/config.py` (`LLM_PROVIDER` config field), `kosmos/core/pricing.py` (add model pricing) | `LLMResponse.strip()` returns `str`, losing metadata (`base.py:107-108`). Empty `LLMResponse` is falsy (`base.py:98-99`). `if False: yield` in `generate_stream_async` is load-bearing (`base.py:360-363`). Plan creator/reviewer bypass the provider layer entirely (`plan_creator.py:158-162`). Async client in research_director reads `ANTHROPIC_API_KEY` directly from env (`research_director.py:228-239`). `generate_with_messages()` has no caching (`llm.py:367-408`). Cost hardcodes `claude-sonnet-4-5` (`llm.py:519`). |
| Add a new experiment type / code template | `kosmos/execution/code_generator.py` (subclass `CodeTemplate`, implement `matches()` and `generate()`) | `kosmos/models/hypothesis.py` (add to `ExperimentType` enum -- note it lives HERE, not in experiment.py), `kosmos/models/experiment.py` (update `to_dict()` if adding fields -- it is hand-written, not `model_dump()`), `kosmos/execution/executor.py` (ensure generated code assigns to `results` variable for extraction) | Template registration order matters -- first match wins, no priority scoring (`code_generator.py:787-793`). ALL templates should include synthetic data fallback; the basic template lacks it and crashes without `data_path` (`code_generator.py:964`). `random_seed=0` becomes 42 due to `or 42` pattern (`code_generator.py:89`). `validate_steps` silently reorders steps (`experiment.py:438`). Code validator flags `getattr` as CRITICAL (`code_validator.py:338`) and matches patterns inside comments/strings (`code_validator.py:288`). |
| Add a new CLI command | `kosmos/cli/commands/` (create new Typer command module) | `kosmos/cli/main.py` (register the command), `kosmos/config.py` (`get_config()` singleton for config access) | CLI `run.py:136-137` mutates global config singleton directly. The flat_config dict bridging has no schema -- typos fail silently. Config singleton is stale after init unless `reload=True` passed. |
| Add a new research domain | `kosmos/agents/research_director.py` (SkillLoader at lines 280-307 loads domain-specific prompt fragments) | `kosmos/core/domain_router.py` (domain routing -- bypasses provider system, always uses Anthropic at line 157), `kosmos/execution/experiment_designer.py` (domain defaults at lines 394-403 map domains to experiment types), `kosmos/agents/hypothesis_generator.py` (LLM-based domain detection at line 259) | Domain detection falls back to "general" on any exception (`hypothesis_generator.py:286`). Domain defaults are hardcoded: ML/AI/CS -> COMPUTATIONAL, stats/data_science/psych/neuro -> DATA_ANALYSIS (`experiment_designer.py:394-403`). New domain needs mapping here or gets no default. |
| Add a new knowledge storage backend | `kosmos/world_model/interface.py` (implement `WorldModelStorage` ABC, 10+ abstract methods) | `kosmos/world_model/factory.py` (update `get_world_model()` singleton factory), `kosmos/world_model/models.py` (use `Entity`, `Relationship` data types) | Factory is NOT thread-safe (`factory.py:38`). Silent fallback to in-memory means data loss on restart (`factory.py:123-133`). Entity type validation is advisory only -- non-standard types trigger `warnings.warn()` but are not rejected (`models.py:160-166`). `reset_knowledge_graph()` does not close existing Neo4j connection. Vector store Layer 3 is a stub (`artifacts.py:560-567`). |
| Add a new literature source | `kosmos/literature/base_client.py` (subclass `BaseLiteratureClient`, implement `search()`, `get_paper_by_id()`, etc.) | `kosmos/literature/unified_search.py` (add source to `ThreadPoolExecutor` parallel search at lines 147-161), `kosmos/literature/base_client.py` (add to `PaperSource` enum) | `_validate_query` says "truncating" but doesn't truncate (`base_client.py:248-250`). `_normalize_paper_metadata` is not `@abstractmethod` -- missing implementation only surfaces at runtime (`base_client.py:255`). `_handle_api_error` swallows exceptions (`base_client.py:229-233`). `PaperMetadata` is a `@dataclass`, not Pydantic -- no automatic validation. Timeout path collects partial results from faster sources (`unified_search.py:172-183`). |
| Add a new database model | `kosmos/db/models.py` (define SQLAlchemy model) | `kosmos/db/__init__.py` (auto-creates tables via `Base.metadata.create_all`), `kosmos/db/operations.py` (add CRUD functions) | `get_session()` auto-commits on context exit (`db/__init__.py:131-133`). Existing agents bypass CRUD validation, using direct `session.add()` + `session.commit()` (`hypothesis_generator.py:474-492`, `experiment_designer.py:888-903`). `_reset_eval_state()` drops ALL tables (`scientific_evaluation.py:56-60`). |
| Add a new convergence criterion | `kosmos/core/convergence.py` (add check method, integrate into `check_convergence()` priority order) | `kosmos/agents/research_director.py` (`_check_convergence_direct()` at line 1237 -- currently passes empty results) | `novelty_trend` grows without bound (`convergence.py:562`). Flat novelty is "declining" due to `>=` comparison (`convergence.py:424`). `StoppingReason.USER_REQUESTED` is used as sentinel for "no reason" when research continues (`convergence.py:271`). Iteration limit can be deferred indefinitely if no experiments complete (`convergence.py:339`). |
## Reading Order

1. `kosmos/core/workflow.py` -- Learn the 9-state research workflow state machine, `NextAction` enum, and `ResearchPlan` data structure. This is the skeleton of the entire system: states, transitions, and what data is tracked per iteration. Small file, high conceptual density.

2. `kosmos/agents/base.py` -- Learn the `BaseAgent` lifecycle (CREATED -> RUNNING -> STOPPED), `AgentMessage` wire format, dual sync/async message queues, and the hooks pattern. All 6 agents inherit from this. Understanding `execute()` contract and `start()`/`stop()` semantics is essential before reading any specific agent.

3. `kosmos/core/providers/base.py` -- Learn the `LLMProvider` abstract interface, `LLMResponse` (str-like with metadata), `UsageStats`, and `ProviderAPIError` recovery heuristics. Every LLM call in the system returns these types.

4. `kosmos/models/hypothesis.py` -- Learn the `Hypothesis` Pydantic model (the core data object), `ExperimentType` enum (lives HERE, not in experiment.py), score fields, and status tracking. 48 importers depend on this file. Understanding `ExperimentType` location avoids wasted search time.

5. `kosmos/models/experiment.py` -- Learn `ExperimentProtocol`, the central experiment definition with steps, variables, and statistical test specs. Note the defensive LLM-output validators (coercing strings to ints, sorting steps silently). Note that `to_dict()` is hand-written (100 lines), not `model_dump()`.

6. `kosmos/models/result.py` -- Learn `ExperimentResult`, `StatisticalTestResult`, `VariableResult`. Completes the data model triad (hypothesis -> experiment -> result). Note the `export_markdown()` crash on None stats.

7. `kosmos/core/llm.py` -- Learn the `ClaudeClient` singleton, `get_client()`/`get_provider()` factory, CLI mode detection, auto-model selection (Haiku vs Sonnet), caching, and structured generation. This is the choke point for all LLM access.

8. `kosmos/core/providers/anthropic.py` -- Learn the concrete Anthropic provider: sync/async generation, streaming, JSON output, cache bypasses on retry, and cost tracking. The `ClaudeClient = AnthropicProvider` alias lives here. Understanding CLI mode and caching behavior is critical for cost analysis.

9. `kosmos/config.py` -- Learn `KosmosConfig` (Pydantic BaseSettings), the singleton `get_config()`, environment variable mapping, and nested sub-configs. Note `_DEFAULT_CLAUDE_SONNET_MODEL` and `_DEFAULT_CLAUDE_HAIKU_MODEL` are underscore-prefixed but imported by 7+ files. The `sync_litellm_env_vars` validator has a hardcoded drift risk.

10. `kosmos/agents/research_director.py` -- The master orchestrator. Read AFTER all of the above. Focus on `__init__` (lines 68-260) for initialization scope, `decide_next_action()` (lines 2388-2548) for the decision tree, `_do_execute_action()` (lines 2573+) for dispatch, and the `_handle_*_action()` methods (lines 1391-1979) for actual agent coordination. Skip lines 1039-1219 (dead message-based `_send_to_*` methods from Issue #76).

11. `kosmos/execution/code_generator.py` -- Learn the 5 code templates, template matching order, LLM fallback, and the basic template gap. Read after understanding `ExperimentProtocol` (step 5).

12. `kosmos/execution/executor.py` -- Learn the execution sandbox (restricted builtins vs Docker), timeout handling (Unix SIGALRM vs Windows ThreadPoolExecutor), retry strategy, and return value extraction convention (`results` variable). Security boundary lives here.

13. `kosmos/safety/code_validator.py` -- Learn the 6-check validation pipeline: syntax, imports, patterns, network, AST calls, ethics. Gates all code execution. Understand the false-positive risks (comments/strings, `getattr`, ethical keywords).

14. `kosmos/db/__init__.py` -- Learn `get_session()` (auto-commit context manager), `init_from_config()`, `reset_database()` (drops ALL tables). Short but critical for understanding data persistence.

15. `kosmos/core/convergence.py` -- Learn stopping criteria: mandatory (iteration limit, hypothesis exhaustion) and optional (novelty decline, diminishing returns). Understand deferral logic and the flat-novelty-is-declining gotcha.

16. `kosmos/agents/hypothesis_generator.py` -- Learn the 6-step hypothesis pipeline: domain detection, literature context, LLM generation, validation, novelty checking, storage. Read after understanding `Hypothesis` model and LLM client.

17. `kosmos/execution/experiment_designer.py` -- Learn protocol generation via templates and LLM, power analysis, validation, and the no-op LLM enhancement. Read after code_generator.

18. `kosmos/literature/base_client.py` -- Learn `PaperMetadata` dataclass, `BaseLiteratureClient` ABC, and `PaperSource` enum. Leaf dependency with 35 importers.

19. `kosmos/knowledge/vector_db.py` -- Learn ChromaDB wrapper, SPECTER embeddings, singleton pattern. Optional component (graceful degradation if ChromaDB missing).

20. `kosmos/world_model/factory.py` + `kosmos/world_model/interface.py` -- Learn the Strategy pattern for knowledge persistence: `WorldModelStorage` ABC, Neo4j vs in-memory fallback, singleton factory.

**Skip:**

| File / Range | Reason |
|---|---|
| `kosmos/agents/research_director.py` lines 1039-1219 | Dead code: message-based `_send_to_*` methods. Issue #76 confirmed direct `_handle_*_action()` calls are used instead. |
| `kosmos/agents/research_director.py` lines 1981-2003 | Deprecated `_send_to_convergence_detector()`. Returns dummy value. |
| `kosmos/orchestration/plan_creator.py` lines 292-346 | Deterministic mock tasks. Not representative of real behavior. |
| `kosmos/orchestration/plan_reviewer.py` mock path | Always approves. Masks real review logic. |
| `evaluation/run_phase2_tests.py` | Hardcodes machine-specific path (`/mnt/c/python/Kosmos`). Will not run elsewhere. |
| `kosmos/config.py` lines 752-822 (`LocalModelConfig`) | Defined but never wired into any provider. |
| `docs/archive/` | Outdated design docs. `CLAUDE.md` explicitly warns against reading these. |
| `.env` | Contains leaked API key (Gotcha 6). Read `config.py` for env var documentation instead. |
| `kosmos/world_model/artifacts.py` vector store Layer 3 | Stub (`pass`). No functionality (Gotcha 105). |
## Gaps

- `kosmos/monitoring/` — not deep-read; monitoring and observability patterns unknown
- `kosmos/compression/` — not deep-read; compression strategy undocumented
- `kosmos/domains/` (biology, chemistry, materials, neuroscience, physics) — domain-specific logic not traced
- `kosmos/oversight/` — human oversight mechanisms not investigated
- `kosmos/api/` — REST API endpoints not traced (only CLI paths traced)
- `kosmos-claude-scientific-skills/` — 40+ scientific skill scripts not individually traced; treated as leaf nodes
- `kosmos-reference/` — reference implementation not compared against main codebase for drift
- `kosmos/db/` — Alembic migration history and schema evolution not investigated
- `kosmos/experiments/` — experiment persistence and lifecycle not fully traced
- No load testing or performance data available — concurrent agent execution limits unknown

---

---

*Generated by deep_crawl agent (R6 — parallel synthesis). 35 tasks,
19 modules read, 5 traces verified.
Compression: 2,455,608 → ~38658 tokens (63:1).
Evidence: 304 [FACT], 49 [PATTERN], 15 [ABSENCE]. Refined: 5 Tier 1-2 findings recovered, 7 gotchas merged into 3, 12 cross-references added, 3 transitions smoothed.*
