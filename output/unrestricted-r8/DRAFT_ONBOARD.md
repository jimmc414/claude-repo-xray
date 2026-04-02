# Kosmos: Agent Onboarding

> Codebase: 802 files, ~2,455,608 tokens
> This document: ~{DOC_TOKENS} tokens
> Generated: 2026-03-29 from commit `ed3fba5`
> Crawl: 32/32 tasks, 19 modules read
> For complete class skeletons and import graphs: `/tmp/xray/xray.md`

---
## Identity

Kosmos is an agent-based scientific research platform combining autonomous AI agents, workflow orchestration, and CLI tooling. Built in Python with 802 files across 4 architectural layers (foundation → core → orchestration → leaf). Core stack: 56 agent modules for autonomous task execution, 47 workflow modules for process coordination, LLM provider abstraction (Anthropic, OpenAI, Google), ChromaDB vector storage, sandboxed code execution, and a REST/HTTP API layer. The system orchestrates multi-stage research workflows where AI agents generate hypotheses, design experiments, execute code in sandboxes, and evaluate results for scientific novelty and convergence.

---
## Critical Paths

### Path 1: CLI `kosmos run` to Terminal Side Effects

This is the primary user-facing path. The `kosmos run` command orchestrates an autonomous research loop. The CLI entry point creates a `ResearchDirectorAgent`, which coordinates a state machine cycling through: hypothesis generation, experiment design, code generation, code execution, result analysis, hypothesis refinement, and convergence check. Each phase calls a specialized agent/utility directly (not via message passing, per Issue #76 fix) and persists results to both a SQLAlchemy database and an optional Neo4j knowledge graph.

`run_research()` (kosmos/cli/commands/run.py:51)
  [FACT] Typer command function. Accepts question, domain, max_iterations, budget, data_path, and streaming flags. (run.py:51-61)

  Branching at entry:
  - If `interactive` or no question provided -> calls `run_interactive_mode()` (run.py:87-99)
  - If no question after interactive -> typer.Exit(1) (run.py:102-104)
  - If `data_path` provided but not exists -> typer.Exit(1) (run.py:107-109)

  Data transformation: CLI parameters are flattened into a `flat_config` dict (run.py:148-171). Nested `KosmosConfig` is flattened because agents expect flat keys. [FACT] (run.py:147 comment)

  -> `get_config()` (kosmos/config.py:1140) -- Singleton pattern. Creates `KosmosConfig()` from environment, calls `create_directories()`. [FACT] (config.py:1151-1153)

  -> `ResearchDirectorAgent.__init__()` (kosmos/agents/research_director.py:68) -- Initializes: research plan (Pydantic `ResearchPlan`), workflow state machine (`ResearchWorkflow`), LLM client via `get_client()`, database via `init_from_config()`, convergence detector, world model (Neo4j knowledge graph), rollout tracker, error recovery state, async locks. [FACT] (research_director.py:68-260)

    Sub-hops during __init__:
    -> `get_client()` (kosmos/core/llm.py:613) -- Singleton. Tries provider system from config, falls back to `AnthropicProvider`. [FACT] (llm.py:652-664)
    -> `init_from_config()` (kosmos/db/__init__.py:140) -- Runs `first_time_setup()`, creates SQLAlchemy tables. [SIDE EFFECT: table creation] (db/__init__.py:140-179)
    -> `get_world_model()` (kosmos/world_model/factory.py:55) -- Singleton. Returns `Neo4jWorldModel` wrapping `KnowledgeGraph`. [FACT] (factory.py:55-104)
    -> `Entity.from_research_question()` -> `wm.add_entity()` -- [SIDE EFFECT: Neo4j entity write] (research_director.py:245-251)
    -> `SkillLoader().load_skills_for_task()` -- Loads domain-specific prompt fragments. (research_director.py:280-307)

    Branching: If concurrent operations enabled, also initializes `ParallelExperimentExecutor` and `AsyncClaudeClient`. (research_director.py:208-239)

  -> `get_registry()` (kosmos/agents/registry.py:512) -- Singleton registry
  -> `registry.register(director)` (registry.py:70) -- Adds to _agents dict, sets message router callback
    [FACT] Sets `agent.set_message_router(self._route_message)` for async message passing. (registry.py:94)

  -> `asyncio.run(run_with_progress_async(director, question, max_iterations, ...))` (run.py:186)
    -> `run_with_progress_async()` (run.py:225) -- Manages Rich live progress display. Orchestrates two phases:

    Phase A: Start Research (run.py:296):
      `await director.execute({"action": "start_research"})`

    Phase B: Iterative Loop (run.py:308-389):
      ```
      while iteration < max_iterations:
          # Check timeout (2hr max)
          # Get status
          # Check convergence -> break if converged
          await director.execute({"action": "step"})
          # Update iteration counter
          await asyncio.sleep(0.05)  # UI update delay
      ```

    Branching:
    - Timeout check: `elapsed > 7200s` -> break (run.py:313-319)
    - Convergence check: `status.get("has_converged")` -> break (run.py:362-365)

  -> `ResearchDirectorAgent.execute({"action": "start_research"})` (research_director.py:2868)
    -> `self.generate_research_plan()` (research_director.py:2882)
    -> `self.start()` (research_director.py:2885) -- triggers _on_start()
    -> `self.decide_next_action()` (research_director.py:2888)
    -> `await self._execute_next_action(next_action)` (research_director.py:2889)

    generate_research_plan() (research_director.py:2349):
      -> `self.llm_client.generate(prompt, max_tokens=1000)` (research_director.py:2372)
        [SIDE EFFECT: LLM API call to Claude] (research_director.py:2372)
        [FACT] Prompt asks Claude for hypothesis directions, experiment strategy, success criteria, resource considerations. (research_director.py:2356-2368)

    start() -> _on_start() (research_director.py:319):
      -> `self.workflow.transition_to(WorkflowState.GENERATING_HYPOTHESES)` (research_director.py:329)
        [FACT] Transitions INITIALIZING -> GENERATING_HYPOTHESES. (research_director.py:329-331)

  -> `decide_next_action()` (research_director.py:2388) -- State Machine Decision
    [FACT] Decision tree based on `workflow.current_state`. Contains budget check, runtime check, loop-guard (MAX_ACTIONS_PER_ITERATION=50). (research_director.py:2388-2548)

    Guard rails:
    - Budget enforcement: imports `get_metrics()`, calls `enforce_budget()`. On `BudgetExceededError` -> CONVERGE. (research_director.py:2404-2422)
    - Runtime limit: `_check_runtime_exceeded()` -> CONVERGE. (research_director.py:2428-2446)
    - Loop guard: `_actions_this_iteration > 50` -> force CONVERGE. (research_director.py:2455-2461)

    State -> Action mapping:
    | State | Action |
    |-------|--------|
    | GENERATING_HYPOTHESES | GENERATE_HYPOTHESIS |
    | DESIGNING_EXPERIMENTS | DESIGN_EXPERIMENT (if untested hyps) or EXECUTE_EXPERIMENT (if queue) or ANALYZE_RESULT (if results) or CONVERGE |
    | EXECUTING | EXECUTE_EXPERIMENT (if queue) or ANALYZE_RESULT (if results) or REFINE_HYPOTHESIS |
    | ANALYZING | ANALYZE_RESULT (if results) or fallback |
    | REFINING | REFINE_HYPOTHESIS (if tested hyps) or GENERATE_HYPOTHESIS |
    | CONVERGED | CONVERGE |
    | ERROR | ERROR_RECOVERY |

  -> `_execute_next_action(action)` (research_director.py:2550)
    -> `tracker.track(f"ACTION_{action.value}")` -- stage tracker context
    -> `_do_execute_action(action)` (research_director.py:2573) -- Routes to one of 7 handler methods based on `NextAction` enum value.

  #### GENERATE_HYPOTHESIS Handler

  -> `_handle_generate_hypothesis_action()` (research_director.py:1391)
    -> `HypothesisGeneratorAgent(config=self.config)` -- lazy-init (research_director.py:1404)
    -> `agent.generate_hypotheses(question, num=3, domain, store_in_db=True)` (research_director.py:1408)
      -> `_detect_domain(question)` (hypothesis_generator.py:177) -- LLM call for domain detection
      -> `_gather_literature_context(question, domain)` (hypothesis_generator.py:183) -- literature search
      -> `_generate_with_claude(question, domain, num, papers)` (hypothesis_generator.py:187)
        -> `HYPOTHESIS_GENERATOR.render(...)` -- prompt template rendering (hypothesis_generator.py:356)
        -> `self.llm_client.generate_structured(prompt, schema, max_tokens=4000, temperature=0.7)` (hypothesis_generator.py:378)
          [SIDE EFFECT: LLM API call] (hypothesis_generator.py:378)
          [FACT] Temperature 0.7 for creativity. Schema enforces `statement`, `rationale`, `confidence_score`, `testability_score`, `suggested_experiment_types`. (hypothesis_generator.py:364-383)
      -> `_validate_hypothesis(hyp)` (hypothesis_generator.py:197) -- length/vagueness checks
      -> `NoveltyChecker.check_novelty(hyp)` (hypothesis_generator.py:213) -- novelty scoring
      -> `_store_hypothesis(hyp)` (hypothesis_generator.py:233) -- [SIDE EFFECT: DB write]
        -> `get_session()` -> `session.add(DBHypothesis)` -> `session.commit()` (hypothesis_generator.py:474-492)
          [SIDE EFFECT: session.add + session.commit] (hypothesis_generator.py:491-492)

    Back in director after hypothesis generation:
    -> `research_plan.add_hypothesis(hyp_id)` (research_director.py:1429)
    -> `_persist_hypothesis_to_graph(hyp_id)` (research_director.py:1433) -- [SIDE EFFECT: Neo4j write]
    -> `workflow.transition_to(DESIGNING_EXPERIMENTS)` (research_director.py:1444)

  #### DESIGN_EXPERIMENT Handler

  -> `_handle_design_experiment_action(hypothesis_id)` (research_director.py:1458)
    -> `ExperimentDesignerAgent(config=self.config)` -- lazy-init (research_director.py:1470)
    -> `agent.design_experiment(hypothesis_id=hyp_id, store_in_db=True)` (research_director.py:1474)
      -> `_load_hypothesis(hypothesis_id)` -- DB read (experiment_designer.py:196)
      -> `_select_experiment_type(hypothesis, preferred)` -- picks from template registry (experiment_designer.py:201)
      -> `_generate_from_template(hypothesis, type, constraints)` -- template-based protocol (experiment_designer.py:206)
         OR `_generate_with_claude(hypothesis, type, constraints)` -- LLM-based protocol
      -> `_enhance_protocol_with_llm(protocol, hypothesis)` -- optional LLM enhancement (experiment_designer.py:222)
      -> `PowerAnalyzer.ttest_sample_size()` / `correlation_sample_size()` / `anova_sample_size()` -- power analysis (experiment_designer.py:226-258)
      -> `_validate_protocol(protocol)` (experiment_designer.py:263)
      -> `_calculate_rigor_score(protocol, validation)` (experiment_designer.py:266)
      -> `_store_protocol(protocol, hypothesis)` -- [SIDE EFFECT: DB write] (experiment_designer.py:272)
        -> `get_session()` -> `session.add(DBExperiment)` -> `session.commit()` (experiment_designer.py:902-903)
          [SIDE EFFECT: session.add + session.commit] (experiment_designer.py:902-903)
          [FACT] Stores full protocol JSON blob in `protocol` column. (experiment_designer.py:897)

    Back in director:
    -> `research_plan.add_experiment(protocol_id)` (research_director.py:1492)
    -> `_persist_protocol_to_graph(protocol_id, hypothesis_id)` (research_director.py:1496) -- [SIDE EFFECT: Neo4j write]
    -> `workflow.transition_to(EXECUTING)` (research_director.py:1507)

  #### EXECUTE_EXPERIMENT Handler

  -> `_handle_execute_experiment_action(protocol_id)` (research_director.py:1521)
    -> `ExperimentCodeGenerator(use_templates=True, use_llm=True)` -- lazy-init (research_director.py:1538)
    -> `CodeExecutor(max_retries=3)` -- lazy-init (research_director.py:1540)
    -> `DataProvider(default_data_dir=data_path)` -- lazy-init (research_director.py:1542)

    Load protocol from DB:
    -> `get_session()` -> `get_experiment(session, protocol_id)` (research_director.py:1551-1552)
    -> `ExperimentProtocol.model_validate(protocol_data)` -- reconstruct Pydantic model (research_director.py:1559)

    Code generation:
    -> `code_generator.generate(protocol)` (research_director.py:1564)
      -> `_match_template(protocol)` (code_generator.py:835) -- tries 5 template types
      -> `template.generate(protocol)` OR `_generate_with_llm(protocol)` (code_generator.py:810-823)
      -> `_validate_syntax(code)` -- ast.parse check (code_generator.py:831)
        [FACT] Template hierarchy: TTestComparisonCodeTemplate, CorrelationAnalysisCodeTemplate, etc. Falls back to LLM generation then basic template. (code_generator.py:807-829)
        [SIDE EFFECT: LLM API call if no template matches] (code_generator.py:847)

    Code execution -- CRITICAL TERMINAL SIDE EFFECT:
    -> `code_executor.execute(code, retry_on_error=True)` (research_director.py:1572)
      OR `code_executor.execute_with_data(code, data_path, retry_on_error=True)` (research_director.py:1568-1569)
      -> `execute()` (executor.py:237)
        -> `_execute_once(code, local_vars)` (executor.py:282)
          -> if use_sandbox: `_execute_in_sandbox(code, local_vars)` (executor.py:474-475) -- Docker sandbox
          -> else: `_exec_with_timeout(code, exec_globals, exec_locals)` (executor.py:506)
            -> `exec(code, exec_globals, exec_locals)` (executor.py:617) -- ACTUAL CODE EXECUTION
              [SIDE EFFECT: exec() -- arbitrary Python code execution] (executor.py:617)
              [FACT] Timeout protection: Unix uses SIGALRM, Windows uses ThreadPoolExecutor. Default timeout: 300s (DEFAULT_EXECUTION_TIMEOUT). (executor.py:600-630)
              [FACT] Retry logic: up to 3 retries with `RetryStrategy.modify_code_for_retry()` which handles 10+ error types (ImportError, TypeError, ValueError, etc.) via pattern matching or LLM-assisted repair. (executor.py:315-324)
              [FACT] Return value extracted from `exec_locals.get('results')` or `exec_locals.get('result')`. (executor.py:516)

    Store result in DB:
    -> `create_result(session, id=result_id, experiment_id=protocol_id, data=safe_data, ...)` (research_director.py:1621-1630)
      -> `session.add(Result)` -> `session.commit()` (db/operations.py:366-367)
        [SIDE EFFECT: session.add + session.commit] (db/operations.py:366-367)
    [FACT] Data sanitized via `_json_safe()` helper that handles numpy arrays, sklearn objects. (research_director.py:1595-1613)

    Back in director:
    -> `research_plan.add_result(result_id)` (research_director.py:1641)
    -> `research_plan.mark_experiment_complete(protocol_id)` (research_director.py:1642)
    -> `_persist_result_to_graph(result_id, protocol_id, hypothesis_id)` (research_director.py:1646) -- [SIDE EFFECT: Neo4j write]
    -> `workflow.transition_to(ANALYZING)` (research_director.py:1652)

  #### ANALYZE_RESULT Handler

  -> `_handle_analyze_result_action(result_id)` (research_director.py:1666)
    -> `DataAnalystAgent(config=self.config)` -- lazy-init (research_director.py:1681)
    -> DB load: `get_result(session, result_id, with_experiment=True)` (research_director.py:1691)
    -> Construct Pydantic ExperimentResult and Hypothesis from DB rows (research_director.py:1704-1734)
    -> `analyst.interpret_results(result, hypothesis)` (research_director.py:1737)
      -> `_extract_result_summary(result)` (data_analyst.py:346) -- builds dict from ExperimentResult
      -> `_build_interpretation_prompt(summary, hypothesis, lit_context)` (data_analyst.py:349)
      -> `self.llm_client.generate(prompt, system=..., max_tokens=2000, temperature=0.3)` (data_analyst.py:355)
        [SIDE EFFECT: LLM API call] (data_analyst.py:355)
        [FACT] Temperature 0.3 for focused analysis. System prompt: "expert scientific data analyst". (data_analyst.py:357-361)
      -> `_parse_interpretation_response(response_text, experiment_id, result)` (data_analyst.py:366)

    Back in director:
    -> `research_plan.mark_supported(hypothesis_id)` OR `mark_rejected(hypothesis_id)` (research_director.py:1763-1767) -- Update hypothesis status
    -> `_add_support_relationship(result_id, hypothesis_id, supports, confidence, p_value, effect_size)` (research_director.py:1771) -- [SIDE EFFECT: Neo4j write] Persist SUPPORTS/REFUTES relationship
    -> `workflow.transition_to(REFINING)` (research_director.py:1782)

  #### REFINE_HYPOTHESIS Handler

  -> `_handle_refine_hypothesis_action(hypothesis_id)` (research_director.py:1796)
    -> `HypothesisRefiner(config=self.config)` -- lazy-init (research_director.py:1817)
    -> DB load: `get_hypothesis(session, hypothesis_id, with_experiments=True)` (research_director.py:1826)
    -> Get results_history for all experiments under this hypothesis (research_director.py:1843-1872)
    -> `refiner.evaluate_hypothesis_status(hypothesis, latest_result, results_history)` (research_director.py:1886)
      -> `_count_consecutive_failures(results)` -- rule-based check (refiner.py:135)
      -> `_bayesian_confidence_update(hypothesis, results)` -- Bayesian posterior (refiner.py:145)
      -> Returns: RETIRE | REFINE | SPAWN_VARIANT | CONTINUE_TESTING
        [FACT] Failure threshold and confidence retirement threshold are configurable. (refiner.py:135-142, 145-152)
        [FACT] Decision logic: consecutive failures -> RETIRE; low posterior -> RETIRE; rejected but not enough -> REFINE; inconclusive -> SPAWN_VARIANT; supported 2+ times -> SPAWN_VARIANT. (refiner.py:135-167)

    Back in director depending on decision:
    - RETIRE: `refiner.retire_hypothesis(hyp)` -- marks retired (research_director.py:1894-1898)
    - REFINE: `refiner.refine_hypothesis(hyp, result)` -> [SIDE EFFECT: `db_create_hypothesis()` session.commit] (research_director.py:1900-1918)
    - SPAWN_VARIANT: `refiner.spawn_variant(hyp, result, num_variants=2)` -> [SIDE EFFECT: `db_create_hypothesis()` per variant session.commit] (research_director.py:1921-1942)

    -> `research_plan.add_hypothesis(hyp_id)` -- for each refined/variant hypothesis (research_director.py:1954-1955)
    -> `_persist_hypothesis_to_graph(hyp_id)` -- [SIDE EFFECT: Neo4j write] (research_director.py:1958-1959)
    -> `research_plan.increment_iteration()` (research_director.py:2704) -- marks end of one research cycle
    -> `_actions_this_iteration = 0` (research_director.py:2706) -- resets loop guard

  #### CONVERGE Handler

  -> `_handle_convergence_action()` (research_director.py:1334)
    -> `_apply_multiple_comparison_correction()` (research_director.py:1343) -- BH-FDR correction
    -> `_check_convergence_direct()` (research_director.py:1347)
      -> `convergence_detector.check_convergence(research_plan, hypotheses, results, total_cost)` (research_director.py:1267)
        -> `_update_metrics(plan, hypotheses, results)` (convergence.py:243)
        -> For each mandatory_criterion: `_check_criterion()` (convergence.py:246-251)
        -> For each optional_criterion: `_check_criterion()` (convergence.py:256-260)
        -> `check_iteration_limit` | `check_hypothesis_exhaustion` | `check_novelty_decline` | `check_diminishing_returns`
          [FACT] Mandatory criteria checked first (except iteration_limit which is checked last). Optional scientific criteria checked between. (convergence.py:246-267)

    If converged:
    -> `research_plan.has_converged = True` (research_director.py:1358)
    -> `wm.add_annotation(question_entity_id, convergence_annotation)` -- [SIDE EFFECT: Neo4j write] (research_director.py:1368)
    -> `workflow.transition_to(CONVERGED)` (research_director.py:1376)
    -> `self.stop()` (research_director.py:1381) -- stops the director agent

  #### ERROR_RECOVERY Handler

  -> `workflow.transition_to(GENERATING_HYPOTHESES)` (research_director.py:2716-2728) -- resets to safe state
    [FACT] `MAX_CONSECUTIVE_ERRORS = 3` with exponential backoff `[2, 4, 8]` seconds. (research_director.py:44-46)

  #### Results Assembly and Display (run.py:403-458)

  -> `run_with_progress_async()` (run.py:403)
    -> `director.get_research_status()` (run.py:400)
    -> `get_session()` -> `get_hypothesis()`, `get_experiment()` -- fetch from DB (run.py:417-435)
    -> Build results dict with metrics (run.py:437-458)

  -> `run_research()` (run.py:195-211)
    -> `ResultsViewer.display_research_overview(results)` (run.py:196)
    -> `ResultsViewer.display_hypotheses_table(results["hypotheses"])` (run.py:197)
    -> `ResultsViewer.display_experiments_table(results["experiments"])` (run.py:198)
    -> `ResultsViewer.display_metrics_summary(results["metrics"])` (run.py:200)
    -> `viewer.export_to_json(results, output)` OR `export_to_markdown()` (run.py:205-209) -- [SIDE EFFECT: file write if --output]

  #### Terminal Side Effects Summary for Path 1

  | Side Effect | Location | Frequency |
  |-------------|----------|-----------|
  | LLM API call (research plan) | research_director.py:2372 | 1x at start |
  | LLM API call (hypothesis generation) | hypothesis_generator.py:378 | 1x per iteration |
  | LLM API call (code generation, if no template) | code_generator.py:847 | 0-1x per experiment |
  | LLM API call (result interpretation) | data_analyst.py:355 | 1x per result |
  | DB commit (hypothesis creation) | hypothesis_generator.py:491-492 | N per iteration (typically 3) |
  | DB commit (protocol storage) | experiment_designer.py:902-903 | 1 per experiment |
  | DB commit (result storage) | db/operations.py:366-367 | 1 per experiment |
  | DB commit (refined hypothesis) | research_director.py:1906-1915 | 0-2 per refinement |
  | exec() (code execution) | executor.py:617 | 1 per experiment |
  | Docker sandbox (if enabled) | executor.py:476, 576 | 1 per experiment (alt to exec()) |
  | Neo4j write (entities and relationships) | research_director.py:250,1433,1496,1646,1771,1958 | Many per iteration |
  | File write (output export) | run.py:205-209 | 0-1x at end (if --output) |

  #### Data Flow Diagram for Path 1

  ```
  CLI args
    -> flat_config dict
      -> ResearchDirectorAgent(question, domain, config)
        -> ResearchPlan (Pydantic, in-memory state)
        -> ResearchWorkflow (state machine)

  Each iteration:
    decide_next_action() -> NextAction enum
      -> _do_execute_action() dispatches to handler

    GENERATE:  LLM prompt -> JSON hypotheses -> Hypothesis models -> DB commit -> Graph write
    DESIGN:    DB hypothesis -> template/LLM -> ExperimentProtocol -> DB commit -> Graph write
    EXECUTE:   DB protocol -> CodeGenerator -> Python string -> exec()/Docker -> ExecutionResult -> DB commit -> Graph write
    ANALYZE:   DB result -> LLM interpretation -> ResultInterpretation -> plan.mark_supported/rejected -> Graph write
    REFINE:    DB hypothesis + results -> RetirementDecision -> refine/retire/spawn -> DB commit -> Graph write
    CONVERGE:  plan metrics -> ConvergenceDetector -> StoppingDecision -> CONVERGED state -> stop()

  Post-loop:
    DB read (hypotheses, experiments) -> results dict -> Rich display -> optional file export
  ```

  ✗ on failure at any handler: `_handle_error_with_recovery()` catches the exception, logs it, increments consecutive error counter, applies exponential backoff ([2, 4, 8] seconds), transitions workflow to ERROR state. If 3 consecutive errors, forces CONVERGE. Otherwise ERROR_RECOVERY transitions back to GENERATING_HYPOTHESES.

---

### Path 2: Scientific Evaluation Pipeline (`scientific_evaluation.py:main()`)

This is the 7-phase evaluation harness that validates the research pipeline end-to-end. It creates `ResearchDirectorAgent` instances, runs them through abbreviated research loops, and scores the results.

`__main__ block` (scientific_evaluation.py:1454)
  -> `argparse setup` (scientific_evaluation.py:1457-1480)
  -> `asyncio.run(main(...))` (scientific_evaluation.py:1482)

`async def main(output_dir, research_question, domain, data_path, max_iterations)` (scientific_evaluation.py:1342)

  -> [SIDE EFFECT: LOG FILE] `logging.basicConfig` creates `evaluation/logs/evaluation_<timestamp>.log` (scientific_evaluation.py:41-50)

  -> `EvaluationReport()` -- creates empty report container (scientific_evaluation.py:1360)

  #### Phase 1: Preflight

  -> `run_phase1_preflight()` (scientific_evaluation.py:1364)
    -> `get_config()` (kosmos/config.py) -- loads Pydantic settings from env
    -> `get_client(reset=True)` (kosmos/core/llm.py) -- creates LLM client
      -> `client.generate("Say hello...")` -- [SIDE EFFECT: LLM API call] (scientific_evaluation.py:176)
    -> `init_from_config()` (kosmos/db/__init__.py:140)
      -> `first_time_setup()` (kosmos/utils/setup.py) -- [SIDE EFFECT: may create .env file, run migrations]
      -> `init_database()` (kosmos/db/__init__.py:26) -- [SIDE EFFECT: creates SQLite DB + tables via Base.metadata.create_all]
    -> `get_session()` -- validates DB connection (scientific_evaluation.py:199)
    -> `client.generate(...)` x2 -- type compatibility checks (scientific_evaluation.py:212, 223)
      -> [SIDE EFFECT: LLM API calls]

  -> [BRANCH: if p1.status == "FAIL"] -> early exit (scientific_evaluation.py:1369-1381)
    -> `generate_report(report)` (scientific_evaluation.py:1373)
    -> [SIDE EFFECT: report_path.write_text()] (scientific_evaluation.py:1379)
      Path: `output_dir/EVALUATION_REPORT.md` OR `evaluation/SCIENTIFIC_EVALUATION_REPORT.md`

  #### Phase 2: Smoke Test

  -> `run_phase2_smoke_test()` (scientific_evaluation.py:1385)
    -> `_reset_eval_state()` (scientific_evaluation.py:262) -- isolation between phases
      -> `reset_database()` (kosmos/db/__init__.py:191) -- [SIDE EFFECT: drops and recreates all DB tables]
      -> `reset_cache_manager()` (kosmos/core/cache_manager.py:515) -- clears global cache singleton
      -> `reset_claude_cache()` (kosmos/core/claude_cache.py:401) -- clears LLM prompt cache
      -> `get_registry().clear()` (kosmos/agents/registry.py) -- clears agent registry
      -> `reset_world_model()` (kosmos/world_model/factory.py:158) -- clears knowledge graph singleton
    -> `ResearchDirectorAgent(..., config=flat_config)` (kosmos/agents/research_director.py:68)
      -> `BaseAgent.__init__()` (kosmos/agents/base.py)
      -> `ResearchPlan(research_question, domain, max_iterations=1)` (kosmos/core/workflow.py:57)
      -> `ResearchWorkflow(initial_state=INITIALIZING)` (kosmos/core/workflow.py:166)
      -> `get_client()` (kosmos/core/llm.py) -- [SIDE EFFECT: LLM client creation]
      -> `init_from_config()` (kosmos/db/__init__.py:140) -- [SIDE EFFECT: DB init, idempotent]
      -> `ConvergenceDetector()` (kosmos/core/convergence.py:172)
      -> `RolloutTracker()` (kosmos/core/rollout_tracker.py)
    -> `registry.register(director)` (kosmos/agents/registry.py)
    -> `director.generate_research_plan()` (kosmos/agents/research_director.py:2349)
      -> `llm_client.generate(prompt, max_tokens=1000)` -- [SIDE EFFECT: LLM API call]
        Stores response in `research_plan.initial_strategy`
    -> `director.start()` (kosmos/agents/base.py:159)
      -> `_on_start()` (kosmos/agents/research_director.py:319)
        -> `workflow.transition_to(GENERATING_HYPOTHESES)` (kosmos/core/workflow.py)
    -> LOOP: max 20 actions (scientific_evaluation.py:328-348)
      -> `director.decide_next_action()` (research_director.py:2388)
        -> [BRANCH: BudgetExceededError] -> CONVERGE (research_director.py:2406-2422)
        -> [BRANCH: runtime exceeded] -> CONVERGE (research_director.py:2428-2446)
        -> [BRANCH: loop guard > 50 actions/iter] -> CONVERGE (research_director.py:2455-2461)
        -> State-based routing (research_director.py:2483-2548):
            GENERATING_HYPOTHESES -> GENERATE_HYPOTHESIS
            DESIGNING_EXPERIMENTS -> DESIGN_EXPERIMENT | EXECUTE_EXPERIMENT | ANALYZE_RESULT | CONVERGE
            EXECUTING -> EXECUTE_EXPERIMENT | ANALYZE_RESULT | REFINE_HYPOTHESIS
            ANALYZING -> ANALYZE_RESULT | EXECUTE_EXPERIMENT | REFINE_HYPOTHESIS
            REFINING -> REFINE_HYPOTHESIS | GENERATE_HYPOTHESIS
            CONVERGED -> CONVERGE
            ERROR -> ERROR_RECOVERY
      -> `director._execute_next_action(action)` (research_director.py:2550)
        -> `_do_execute_action(action)` (research_director.py:2573) -- dispatches to all 7 handlers as in Path 1
      -> `director.get_research_status()` -- snapshot research state (research_director.py:2926)

    [FACT] Each action step has `asyncio.wait_for(timeout=120)` (scientific_evaluation.py:338-341). With up to 20 actions, worst-case for Phase 2 is 2400 seconds.

  #### Phase 3: Multi-Iteration

  -> `run_phase3_multi_iteration()` (scientific_evaluation.py:1392)
    -> `_reset_eval_state()` -- same isolation as Phase 2
    -> Same ResearchDirectorAgent setup as Phase 2 but with `max_iterations=3` (or override)
    -> LOOP: max(60, max_iterations*10) actions (scientific_evaluation.py:474)
      -> Same `decide_next_action` -> `_execute_next_action` cycle as Phase 2
        with snapshot capture at iteration boundaries (scientific_evaluation.py:500-504)
    -> Checks: loop_completed, hypotheses_generated, experiments_executed, refinement_attempted, convergence_not_premature

    [FACT] With 120-second timeout per action and up to 60 actions in Phase 3, the worst-case wall time is 120 * 60 = 7200 seconds (2 hours) for Phase 3 alone. There is no aggregate timeout for the entire evaluation. (scientific_evaluation.py:485-488)

  #### Phase 4: Dataset Test

  -> `run_phase4_dataset_test()` (scientific_evaluation.py:1399)
    -> `_reset_eval_state()`
    -> [BRANCH: data_path is None?] -> FAIL immediately (scientific_evaluation.py:580-585)
    -> [BRANCH: data_path.exists()?] -> SKIP if missing (scientific_evaluation.py:590-594)
    -> `pd.read_csv(data_path)` -- validates dataset readable (scientific_evaluation.py:601)
    -> `DataProvider().get_data(file_path=str(data_path))` (execution/data_provider.py:310)
      -> Loads CSV/TSV/parquet/JSON/JSONL with extension dispatch
    -> Same ResearchDirectorAgent loop as Phase 2 (10 steps max) with `data_path` in flat_config
    -> Multi-format support check via source code inspection (scientific_evaluation.py:700)

  #### Phase 5: Output Quality

  -> `assess_output_quality(p2, p3)` (scientific_evaluation.py:1406)
    -> Pure analysis -- no side effects, reads from `PhaseResult.details`
    -> Scores hypothesis quality via keyword heuristics (scientific_evaluation.py:741-747)
    -> Scores experiment design, code execution, analysis presence
    -> Computes average quality score

  #### Phase 6: Rigor Scorecard

  -> `run_phase6_rigor_scorecard()` (scientific_evaluation.py:1413)
    -> Pure analysis with import-time checks -- no LLM calls
    -> Checks 8 rigor features via `hasattr()` and `inspect.getsource()`:
      1. `NoveltyChecker.check_novelty` (hypothesis/novelty_checker.py:27)
      2. `PowerAnalyzer` methods (experiments/statistical_power.py)
      3. Shapiro-Wilk + Levene in code_generator source
      4. `SyntheticDataGenerator.randomize_effect_size`
      5. `DataProvider` multi-format support
      6. `ConvergenceDetector.check_convergence` (core/convergence.py:172)
      7. `ReproducibilityManager.set_seed` (safety/reproducibility.py)
      8. `Metrics.enforce_budget` (core/metrics.py)
    -> Scores each 0-10 based on implementation + pipeline wiring

  #### Phase 7: Paper Compliance

  -> `run_phase7_paper_compliance(p2, p3, p4, p6)` (scientific_evaluation.py:1420)
    -> Pure analysis -- no side effects, reads from previous PhaseResults
    -> Evaluates 15 claims from arXiv:2511.02824v2
    -> Status per claim: PASS, PARTIAL, FAIL, BLOCKER
    -> Attempts imports to verify module existence (ResultSummarizer, DockerSandbox, etc.)

  #### Report Generation and Final Side Effects

  -> `generate_report(report)` (scientific_evaluation.py:1220)
    -> Builds Markdown string from all phase results
      Sections: Executive Summary, per-phase tables, quality scores, rigor scorecard, paper claims table, limitations disclaimer

  -> [TERMINAL SIDE EFFECTS] (scientific_evaluation.py:1427-1451)
    -> `report_path.write_text(report_text)` (scientific_evaluation.py:1432)
      Path: `output_dir/EVALUATION_REPORT.md` OR `evaluation/SCIENTIFIC_EVALUATION_REPORT.md`
    -> `print()` summary to stdout (scientific_evaluation.py:1435-1450)
    -> `return 0` -> `sys.exit(0)` (scientific_evaluation.py:1489)

  #### Data Transformations Between Hops

  1. Config -> flat_config dict: `get_config()` returns Pydantic model, manually flattened to dict for director constructor (scientific_evaluation.py:272-287). [FACT]
  2. LLM response -> `research_plan.initial_strategy`: Raw string from `client.generate()` stored directly, no parsing (research_director.py:2375). [FACT]
  3. HypothesisGenerationResponse -> hypothesis IDs: `response.hypotheses` list mapped to `[h.id for h in response.hypotheses]` (research_director.py:1418). [FACT]
  4. ExperimentProtocol (Pydantic) -> generated code string: `ExperimentCodeGenerator.generate(protocol)` transforms structured protocol to executable Python (code_generator.py). [FACT]
  5. exec() locals -> ExecutionResult: Code execution extracts `results` or `result` variable from exec namespace (executor.py:516). [FACT]
  6. ExecutionResult.return_value -> DB-safe dict: `_json_safe()` recursively converts numpy types, sklearn objects to JSON-serializable types (research_director.py:1595-1613). [FACT]
  7. DB result rows -> Pydantic models: Manual reconstruction of ExperimentResult/Hypothesis Pydantic objects from SQLAlchemy model attributes (research_director.py:1700-1722, 1851-1872). [FACT]
  8. Phase results -> Markdown string: `generate_report()` iterates PhaseResult list, formats checks as Markdown tables, scores as formatted rows (scientific_evaluation.py:1220-1335). [FACT]

  #### Branching Points Table

  | Location | Condition | True Path | False Path |
  |---|---|---|---|
  | scientific_evaluation.py:1369 | `p1.status == "FAIL"` | Early exit with partial report | Continue to Phase 2 |
  | scientific_evaluation.py:580 | `data_path is None` | Phase 4 FAIL immediately | Continue dataset checks |
  | scientific_evaluation.py:590 | `not data_path.exists()` | Phase 4 SKIP | Continue with dataset |
  | research_director.py:2406-2422 | BudgetExceededError caught | Transition to CONVERGED | Continue research |
  | research_director.py:2428 | `_check_runtime_exceeded()` | Force CONVERGE | Continue |
  | research_director.py:2455 | `_actions_this_iteration > 50` | Force CONVERGE (loop guard) | Continue |
  | research_director.py:2483-2548 | WorkflowState switch | Routes to appropriate NextAction | Default: GENERATE_HYPOTHESIS |
  | executor.py:474 | `self.use_sandbox` | Docker sandbox execution | Direct exec() with restricted builtins |
  | research_director.py:1567 | `self.data_path` truthy | `execute_with_data()` | `execute()` |
  | research_director.py:1893-1944 | RetirementDecision enum | RETIRE/REFINE/SPAWN_VARIANT/CONTINUE | Different hypothesis lifecycle actions |
  | scientific_evaluation.py:1427-1430 | `output_dir` provided | `output_dir/EVALUATION_REPORT.md` | `evaluation/SCIENTIFIC_EVALUATION_REPORT.md` |

  ✗ on failure at Phase 1: Early exit with partial report written. Returns exit code 1. Remaining phases skipped.
  ✗ on failure at any action step: `asyncio.wait_for(timeout=120)` wraps each step. On timeout, that step is skipped and loop continues.
  ✗ on failure at any later phase: Phase status set to FAIL but main() still returns 0. [FACT] No aggregate error count check -- Phases 2-7 can all FAIL and exit code is still 0 (scientific_evaluation.py:1451).

  #### Terminal Side Effects Summary for Path 2

  | Side Effect | File:Line | Description |
  |---|---|---|
  | Log file created | scientific_evaluation.py:41 | `evaluation/logs/evaluation_<timestamp>.log` created at module import |
  | LLM API calls | scientific_evaluation.py:176, 212, 223; research_director.py:2372; hypothesis_generator.py:187; experiment_designer.py:213; code_generator.py; data_analyst.py | Multiple LLM calls throughout phases 1-4 |
  | DB tables created | kosmos/db/__init__.py:100 | `Base.metadata.create_all()` during init_from_config |
  | DB tables dropped/recreated | kosmos/db/__init__.py:200-201 | `_reset_eval_state()` calls `reset_database()` before each phase (2, 3, 4) |
  | DB writes | kosmos/db/operations.py:339-371 | `create_result()`, `create_hypothesis()` via session.commit() |
  | Knowledge graph writes | research_director.py:1432-1433, 1496, 1646-1648, 1769-1778 | Hypotheses, protocols, results, relationships persisted to world model |
  | .env file created | kosmos/utils/setup.py (via first_time_setup) | May create .env if missing during init_from_config |
  | Report file written | scientific_evaluation.py:1432 | Markdown report to EVALUATION_REPORT.md or SCIENTIFIC_EVALUATION_REPORT.md |
  | stdout | scientific_evaluation.py:1355-1450 | Phase status summaries + final summary block printed |

---

### Path 3: Persona Evaluation and Run Comparison

This path has two sub-paths: `run_persona_eval.py` which drives the full evaluation for a persona definition, and `compare_runs.py` which diffs two evaluation runs.

#### Sub-Path 3a: `run_persona_eval.py:main()` -- Persona Evaluation Flow

`main()` (run_persona_eval.py:258)
  -> `argparse.parse_args()` -- parse `--persona`, `--tier`, `--dry-run`, `--version`

  -> `load_persona(args.persona)` (run_persona_eval.py:36)
    -> `yaml.safe_load(file)` -- loads YAML persona definition from `definitions/{name}.yaml`
    -> validates required fields: "persona", "research", "setup"
    -> [ERROR PATH] `sys.exit(1)` if PyYAML missing, file not found, or missing field
    -> returns dict

  -> `get_next_version(args.persona)` (run_persona_eval.py:64)
    -> scans `runs/{persona_name}/v*` directories
    -> extracts highest version number from `v{NNN}_{date}` format
    -> returns `v{NNN+1}` string (e.g., "v004")

  -> `create_run_directory(persona_name, version)` (run_persona_eval.py:105)
    -> creates `runs/{persona}/v{NNN}_{YYYYMMDD}/tier1/artifacts/`
    -> creates `runs/{persona}/v{NNN}_{YYYYMMDD}/tier2/`
    -> creates `runs/{persona}/v{NNN}_{YYYYMMDD}/tier3/`
    -> [SIDE EFFECT: mkdir] (run_persona_eval.py:112-114)

  -> `write_meta_json(run_dir, persona, version)` (run_persona_eval.py:119)
    -> `get_git_sha()` (run_persona_eval.py:87) -- subprocess: `git rev-parse HEAD`
    -> `compute_config_hash(persona)` (run_persona_eval.py:99) -- sha256 of json-serialized persona
    -> [SIDE EFFECT: file.write] meta.json with persona_id, model, git sha, config_hash (run_persona_eval.py:142)

  -> `run_tier1(persona_name, persona, run_dir, dry_run)` (run_persona_eval.py:148)
    -> [SIDE EFFECT: file.unlink] deletes `PROJECT_ROOT/kosmos.db` for clean eval (run_persona_eval.py:187)
    -> [SIDE EFFECT: shutil.rmtree] deletes `PROJECT_ROOT/.kosmos_cache` (run_persona_eval.py:190)
    -> [SUBPROCESS] `python scientific_evaluation.py --output-dir {run_dir}/tier1 --research-question {question} --domain {domain} --data-path {dataset} --max-iterations {max_iterations}` (run_persona_eval.py:196)
      -> `scientific_evaluation.main()` (scientific_evaluation.py:1342) -- Full 7-phase pipeline as described in Path 2 above, including:
        -> Phase 1: `run_phase1_preflight()` (scientific_evaluation.py:138)
          -> `kosmos.config.get_config()` -- validate LLM config
          -> `kosmos.core.llm.get_client()` -- test LLM connectivity
          -> `kosmos.db.init_from_config()` -- init database
          -> Type compatibility checks (str.strip/lower/json.loads on LLM responses)
        -> Phase 2: `run_phase2_smoke_test()` (scientific_evaluation.py:258)
          -> `_reset_eval_state()` -- reset DB, cache, claude cache, registry, world model
          -> `ResearchDirectorAgent(research_question, domain, config)` (research_director.py:68)
          -> `director.generate_research_plan()` -- LLM prompt for research plan (research_director.py:2349)
          -> `director.start()` -- transitions workflow state
          -> loop up to 20 actions:
            `director.decide_next_action()` (research_director.py:2388) -- decision tree
            `director._execute_next_action(action)` (research_director.py:2550) -- dispatches to handlers
            -> `_handle_generate_hypothesis_action()` -> `HypothesisGeneratorAgent.generate_hypotheses()`
            -> `_handle_design_experiment_action()` -> `ExperimentDesignerAgent.design_experiment()`
            -> `_handle_execute_experiment_action()` -> `CodeExecutor.execute()`
            -> `_handle_analyze_result_action()` -> `DataAnalystAgent.interpret_results()`
            -> `_handle_refine_hypothesis_action()` -> HypothesisRefiner
            -> `_handle_convergence_action()` -> `ConvergenceDetector.check_convergence()`
          -> `director.get_research_status()` -- snapshot research state (research_director.py:2926)
        -> Phase 3: `run_phase3_multi_iteration()` (scientific_evaluation.py:420)
          -> same as Phase 2 but max_iterations=3, max_total_actions=60
          -> takes iteration snapshots at boundaries
        -> Phase 4: `run_phase4_dataset_test()` (scientific_evaluation.py:574)
          -> validates dataset file exists (requires --data-path)
          -> `pandas.read_csv(data_path)`
          -> `DataProvider.get_data(file_path=data_path)`
          -> Runs abbreviated ResearchDirector loop with data_path in config
        -> Phase 5: `assess_output_quality()` (scientific_evaluation.py:724)
          -> heuristic keyword scoring of Phase 2/3 outputs (specificity, mechanism, testable, novel)
          -> scores 1-10 per dimension
        -> Phase 6: `run_phase6_rigor_scorecard()` (scientific_evaluation.py:816)
          -> introspects source code for: NoveltyChecker, PowerAnalyzer, Shapiro-Wilk, effect size randomization, multi-format loading, convergence, reproducibility, cost tracking
        -> Phase 7: `run_phase7_paper_compliance()` (scientific_evaluation.py:999)
          -> evaluates 15 paper claims from arXiv:2511.02824v2
        -> `generate_report(report)` (scientific_evaluation.py:1220)
          -> assembles markdown report
          -> [SIDE EFFECT: file.write] EVALUATION_REPORT.md (scientific_evaluation.py:1432)

    -> [SUBPROCESS] `python run_phase2_tests.py --output-dir {run_dir}/tier1/artifacts/phase2_components --research-question {question} --domain {domain} --data-path {dataset}` (run_persona_eval.py:219)
      -> `run_phase2_tests.py` (run_phase2_tests.py:497)
        -> `test_component("2.1_hypothesis_generation", ...)` -- HypothesisGeneratorAgent
        -> `test_component("2.2_literature_search", ...)` -- UnifiedLiteratureSearch
        -> `test_component("2.3_experiment_design", ...)` -- ExperimentDesignerAgent
        -> `test_component("2.4_code_execution", ...)` -- TTestComparisonCodeTemplate + CodeExecutor
        -> `test_component("2.5_data_analysis", ...)` -- DataAnalystAgent
        -> `test_component("2.6_convergence_detection", ...)` -- ConvergenceDetector
        -> [SIDE EFFECT: file.write] per-component JSON + all_components.json (run_phase2_tests.py:563-569)

    -> [SIDE EFFECT: shutil.copy2] copies latest eval log to `run_dir/tier1/eval.log` (run_persona_eval.py:228)

  -> `parse_tier1_results(run_dir)` (run_persona_eval.py:233)
    -> reads EVALUATION_REPORT.md
    -> regex extracts checks_passed/total and duration

  -> `write_meta_json(run_dir, ..., tier1_completed=success, checks_passed, ...)` (run_persona_eval.py:318)
    -> [SIDE EFFECT: file.write] overwrites meta.json with final results (run_persona_eval.py:142)

  -> prints next steps for Tier 2 (technical report) and Tier 3 (narrative)
  -> prints regression comparison command if prior versions exist

  ##### Branching and Conditional Logic

  1. **dry_run branch** (run_persona_eval.py:178-181, 302-304): If `--dry-run`, prints commands but skips execution and result parsing. `run_tier1()` returns `True` early at line 181.
  2. **data_path missing** (run_persona_eval.py:170-171): If persona's `research.dataset` path does not exist, prints WARNING but continues without `--data-path` flag. Phase 4 of scientific_evaluation will then FAIL or SKIP.
  3. **Phase 1 failure** (scientific_evaluation.py:1369-1381): If pre-flight checks fail, generates partial report and returns exit code 1. Remaining phases are skipped.
  4. **Budget exceeded** (research_director.py:2406-2422): `decide_next_action()` checks budget enforcement before each action. If exceeded, forces CONVERGE state.
  5. **Runtime limit** (research_director.py:2428-2446): Checks elapsed time against `max_runtime_hours` (default 12h). Forces CONVERGE if exceeded.
  6. **Infinite loop guard** (research_director.py:2450-2461): `MAX_ACTIONS_PER_ITERATION = 50`. Forces convergence if exceeded.
  7. **Error recovery** (research_director.py:44-46): `MAX_CONSECUTIVE_ERRORS = 3` with exponential backoff `[2, 4, 8]` seconds.

  ##### Data Transformations Between Hops

  1. YAML dict -> CLI args: Persona YAML fields (`research.question`, `research.domain`, `research.dataset`, `research.max_iterations`) are mapped to CLI flags for subprocess calls (run_persona_eval.py:156-174).
  2. CLI args -> flat config dict: `scientific_evaluation.py` builds a `flat_config` dict from args plus hardcoded defaults (e.g., `budget_usd: 5.0`, `enable_concurrent_operations: False`) (scientific_evaluation.py:272-287).
  3. PhaseResult -> EvaluationReport -> Markdown: Each phase returns a `PhaseResult` dataclass. `generate_report()` formats all phases into a single markdown file (scientific_evaluation.py:1220-1335).
  4. Markdown -> regex -> (checks_passed, checks_total, duration): `parse_tier1_results()` regex-parses the generated markdown report to extract summary stats back into structured data (run_persona_eval.py:233-255).
  5. State reset between phases: `_reset_eval_state()` resets DB, cache, Claude cache, agent registry, and world model before Phases 2, 3, and 4 for isolation (scientific_evaluation.py:54-81).

  ##### Side Effects for Sub-Path 3a

  | Side Effect | Location | Type |
  |---|---|---|
  | Create run directory tree | run_persona_eval.py:112-114 | mkdir |
  | Write initial meta.json | run_persona_eval.py:142 | file.write |
  | Delete kosmos.db | run_persona_eval.py:187 | file.unlink |
  | Delete .kosmos_cache | run_persona_eval.py:190 | shutil.rmtree |
  | Write EVALUATION_REPORT.md | scientific_evaluation.py:1432 | file.write |
  | Write eval log | scientific_evaluation.py:42 | logging.FileHandler |
  | Write per-component JSON | run_phase2_tests.py:563-566 | file.write |
  | Write all_components.json | run_phase2_tests.py:568-569 | file.write |
  | Copy eval log to run dir | run_persona_eval.py:228 | shutil.copy2 |
  | Write final meta.json | run_persona_eval.py:318->142 | file.write |

  ✗ on failure of scientific_evaluation subprocess: exit code != 0, `run_tier1()` returns False, `parse_tier1_results()` extracts whatever partial report exists. meta.json updated with `tier1_completed=False`.
  ✗ on failure of run_phase2_tests subprocess: component-level JSON files may be partial, but persona eval continues.

#### Sub-Path 3b: `compare_runs.py:main()` -- Run Comparison Flow

`main()` (compare_runs.py:248)
  -> `argparse.parse_args()` -- parse `--persona`, `--v1`, `--v2`, `--output`

  -> `compare_runs(args.persona, args.v1, args.v2)` (compare_runs.py:148)
    -> validates run directories exist under `runs/{persona}/{v1|v2}`
    -> [ERROR PATH] `sys.exit(1)` if either directory missing (compare_runs.py:154-157)

    -> `load_meta(v1_dir)` (compare_runs.py:26)
      -> reads `meta.json` from run directory
      -> [ERROR PATH] `sys.exit(1)` if meta.json missing (compare_runs.py:29-30)
      -> returns dict
    -> `load_meta(v2_dir)` (compare_runs.py:26) -- same for v2

    -> `parse_evaluation_report(v1_dir)` (compare_runs.py:36)
      -> reads `tier1/EVALUATION_REPORT.md`
      -> regex extracts:
        - summary (checks_passed/total, duration, quality_score, rigor_score)
        - individual check rows (name -> PASS/FAIL) via pattern `r"\|\s*(\w+)\s*\|\s*(PASS|FAIL)\s*\|([^|]*)\|"`
        - quality scores (dimension -> N/10) via pattern `r"\|\s*(phase\d+_\w+)\s*\|\s*(\d+)/10\s*\|"`
        - rigor scores (feature -> N/10) -- extracted from "Scientific Rigor Scorecard" section only
        - paper claims (claim_num -> STATUS) via pattern `r"\|\s*(\d+)\s*\|\s*([^|]+)\|\s*(PASS|PARTIAL|FAIL|BLOCKER)\s*\|"`
      -> returns `{"checks": {}, "quality_scores": {}, "rigor_scores": {}, "paper_claims": {}, "summary": {}}`
    -> `parse_evaluation_report(v2_dir)` -- same for v2

    -> Summary comparison: for each metric key, builds `{v1, v2, delta}` triples
    -> `compute_delta(v1_val, v2_val)` (compare_runs.py:135) -- formats "+N" / "0" / "-N"
    -> Check changes: classifies all checks into improved/regressed/unchanged lists (compare_runs.py:179-194)
    -> Quality score changes: per-dimension `{v1, v2, delta}` (compare_runs.py:197-206)
    -> Rigor score changes: per-feature `{v1, v2, delta}` (compare_runs.py:209-217)
    -> Paper claim changes: only changed claims recorded (compare_runs.py:220-226)
    -> returns comparison dict

  -> Determines output path (compare_runs.py:274-278):
    -> if `--output`: uses provided path
    -> else: creates `runs/{persona}/regression/` directory
    -> filename: `{v1}_vs_{v2}.json`

  -> [SIDE EFFECT: mkdir] `output_path.parent.mkdir(parents=True, exist_ok=True)` (compare_runs.py:280)
  -> [SIDE EFFECT: file.write] `json.dump(comparison, f, indent=2)` (compare_runs.py:281-282)
  -> Prints summary table to stdout: metric, baseline, current, delta (compare_runs.py:288-294)
  -> Prints improved/regressed check names and unchanged count (compare_runs.py:296-301)

  ##### Branching and Conditional Logic

  1. Missing report (compare_runs.py:38-40): If `EVALUATION_REPORT.md` does not exist in either run, returns empty dicts for all categories. No error raised -- comparison proceeds with empty data.
  2. Missing regex matches (compare_runs.py:51-57): Multiple fallback regex patterns for "Checks passed" line. If neither matches, summary stays empty.
  3. Rigor section scoping (compare_runs.py:92-105): Rigor scores are extracted only from text after "Scientific Rigor Scorecard" heading and before the next `##` heading. Scores with `phase` prefix are explicitly skipped to avoid double-counting quality scores.
  4. Paper claim changes (compare_runs.py:224-226): Only claims where status changed between v1 and v2 are recorded. Unchanged claims are omitted from the output.
  5. Output path (compare_runs.py:274-278): `--output` flag overrides the default `regression/` subdirectory path.

  ##### Data Transformations Between Hops

  1. Markdown -> structured dict: `parse_evaluation_report()` converts unstructured markdown tables into 5 typed dictionaries via regex. This is the primary data transformation (compare_runs.py:36-132).
  2. Two dicts -> diff: `compare_runs()` takes two report dicts and produces a single comparison dict with delta calculations for all numeric fields and set-based classification for checks (compare_runs.py:148-245).
  3. Dict -> JSON file + stdout table: Terminal side effects are the JSON dump and a formatted ASCII table to stdout (compare_runs.py:281-301).

  ##### Side Effects for Sub-Path 3b

  | Side Effect | Location | Type |
  |---|---|---|
  | Create regression/ directory | compare_runs.py:277 + 280 | mkdir |
  | Write comparison JSON | compare_runs.py:281-282 | file.write |
  | Print summary to stdout | compare_runs.py:284-301 | stdout |

  [FACT] `compare_runs.py` is entirely self-contained -- it has zero imports from the Kosmos application code. It only reads files (meta.json, EVALUATION_REPORT.md) and writes JSON. No database, no LLM, no network calls.

  ✗ on failure: If either run directory is missing, `sys.exit(1)`. If either meta.json is missing, `sys.exit(1)`. If EVALUATION_REPORT.md is missing, comparison proceeds with empty data -- no crash, but results will show all-zero deltas.

---

### Path 4: Hypothesis Generation and Literature Analysis

This path covers two specialized agent traces: the full hypothesis generation pipeline (HypothesisGeneratorAgent) and the literature analysis suite (LiteratureAnalyzerAgent).

#### Sub-Path 4a: HypothesisGeneratorAgent.execute() Full Chain

`HypothesisGeneratorAgent.execute(message: AgentMessage)` (kosmos/agents/hypothesis_generator.py:91)
  Sets `self.status = AgentStatus.WORKING` (line 101), dispatches on `message.content["task_type"]`. Only recognized value: `"generate_hypotheses"`. All other values raise `ValueError` (line 126). On error, returns `MessageType.ERROR` message (line 131). On success or error, resets to `AgentStatus.IDLE` in finally block (line 140).

  Branching: Single task_type branch ("generate_hypotheses"). Error path returns error AgentMessage.

  -> `generate_hypotheses(research_question, num_hypotheses, domain, store_in_db)` (hypothesis_generator.py:142)
    Orchestrates the full 6-step hypothesis pipeline. Returns `HypothesisGenerationResponse` (Pydantic model).
    Data transformation: `research_question` string enters; `HypothesisGenerationResponse` (list of `Hypothesis` objects + metrics) exits.

    Step 1: `_detect_domain(research_question)` (hypothesis_generator.py:259) -- LLM call
      Calls `self.llm_client.generate()` with `max_tokens=50, temperature=0.0`. Normalizes response to lowercase+underscores. Falls back to `"general"` on any exception (line 286). [FACT: hypothesis_generator.py:286]
      [SIDE EFFECT: LLM API call (Anthropic messages.create)]

    Step 2: `_gather_literature_context(research_question, domain)` (hypothesis_generator.py:289) -- Literature search
      Delegates to `self.literature_search.search(query, max_results=self.max_papers_context)`. Returns empty list on error (line 320). Max papers default: 10 (line 82).

      -> `UnifiedLiteratureSearch.search(query, max_results_per_source, ...)` (kosmos/literature/unified_search.py:76)
        Searches arXiv, Semantic Scholar, and PubMed in parallel via `ThreadPoolExecutor` (line 147). Each source searched via `_search_source()` which calls `client.search()`. Has configurable timeout from `config.literature.search_timeout` (line 164).

        Post-processing pipeline:
        1. Collect results from all sources (line 168-170)
        2. Timeout handling: collects any late results that completed (line 177-183) [FACT: unified_search.py:172-183]
        3. Deduplicate by DOI > arXiv ID > PubMed ID > title (line 189, method at line 371)
        4. Rank by citation count + title relevance + abstract relevance + recency (line 193, method at line 449)
        5. Optionally extract full PDF text (line 201)

        Data transformation: Query string in; ranked, deduplicated `List[PaperMetadata]` out.
        Branching: Timeout path collects partial results. Per-source errors logged and skipped (line 171).

    Step 3: `_generate_with_claude(research_question, domain, num_hypotheses, context_papers)` (hypothesis_generator.py:322) -- Structured LLM generation
      1. Builds literature context string from top 5 papers (title + year + truncated abstract at 200 chars) [FACT: hypothesis_generator.py:347]
      2. Renders `HYPOTHESIS_GENERATOR` prompt template (defined at `kosmos/core/prompts.py:105`), using `Template.safe_substitute()` [FACT: prompts.py:74]
      3. Calls `self.llm_client.generate_structured(prompt, schema, max_tokens=4000, temperature=0.7)` [FACT: hypothesis_generator.py:378-383]
      4. Parses JSON response into `Hypothesis` Pydantic objects with UUID ids (line 398)
      5. Maps experiment type strings to `ExperimentType` enum (line 391-395)
      6. Attaches `related_papers` from context papers (line 407-411)
      Data transformation: Research question + papers in; `List[Hypothesis]` with ids, scores, experiment types out.
      Branching: Per-hypothesis parse errors logged and skipped (line 416-418). Returns empty list on total failure (line 424).

      -> `ClaudeClient.generate_structured(prompt, schema, max_tokens, temperature, max_retries)` (kosmos/core/llm.py:410)
        1. Appends JSON schema instruction to system prompt (line 456-457)
        2. Calls `self.generate()` in a retry loop (up to `max_retries + 1` = 3 attempts) [FACT: llm.py:460]
        3. Parses response via `parse_json_response()` with fallback strategies [FACT: llm.py:471]
        4. On retry, bypasses cache (`bypass_cache=attempt > 0`) [FACT: llm.py:466]
        5. On total failure, raises `ProviderAPIError` with `recoverable=False` [FACT: llm.py:481-486]

        -> `ClaudeClient.generate(prompt, system, max_tokens, temperature, ...)` (kosmos/core/llm.py:207)
          1. Model selection: auto-select (Haiku vs Sonnet based on complexity) or use default [FACT: llm.py:246-268]
          2. Cache check via `ClaudeCache.get()` (line 278-303)
          3. API call: `self.client.messages.create(model, max_tokens, temperature, system, messages)` [FACT: llm.py:309]
            [SIDE EFFECT: Anthropic API call] (llm.py:309)
          4. Token stats tracking (input/output) (line 320-324)
          5. Logs warning if `stop_reason == 'max_tokens'` [FACT: llm.py:329-330]
          6. Cache response via `ClaudeCache.set()` (line 336-358)

          Mode detection: If API key is all 9s, routes to CLI mode (line 179). `ModelComplexity.estimate_complexity()` scores prompts 0-100 by token count + keyword matches [FACT: llm.py:53-105].

    Step 4: `_validate_hypothesis(hypothesis)` (hypothesis_generator.py:426) -- Quality gate
      Validates:
      - Statement length >= 15 chars (line 441)
      - Rationale length >= 30 chars (line 446)
      - Warns on vague words ("maybe", "might", etc.) but does NOT reject [FACT: hypothesis_generator.py:451-455]

    Step 5: `NoveltyChecker.check_novelty(hypothesis)` (kosmos/hypothesis/novelty_checker.py:72) -- Novelty scoring
      Called from hypothesis_generator.py:216. Instantiated with `similarity_threshold = 1.0 - self.min_novelty_score` [FACT: hypothesis_generator.py:211].
      Sub-steps:
      1. `_search_similar_literature(hypothesis)` (line 92) -- searches via vector DB or keyword fallback
        Two paths:
        - Vector path (line 194-195): `_vector_search_papers()` -> `self.vector_db.search(query, top_k=20)` -> reconstruct `PaperMetadata` from results
        - Keyword path (line 198-199): `self.literature_search.search(query, max_results=20)` using hypothesis statement + first 100 chars of rationale
        [SIDE EFFECT: Vector DB query or HTTP API calls]
      2. `_check_existing_hypotheses(hypothesis)` (line 95) -- queries DB for same-domain hypotheses
        -> Opens DB session via `get_session()` context manager
        -> Queries `DBHypothesis` filtered by `domain == hypothesis.domain` [FACT: novelty_checker.py:273]
        -> Converts to Pydantic `Hypothesis` models
        -> Filters by similarity >= 0.5 (lower threshold for preliminary filtering) [FACT: novelty_checker.py:299]
        -> Sorts by similarity descending
        [SIDE EFFECT: DB read] (novelty_checker.py:271-273)
      3. `_compute_similarity()` for each paper (line 100-103) -- cosine similarity via SPECTER embeddings (or Jaccard fallback)
      4. `_compute_hypothesis_similarity()` for each existing hypothesis (line 106-109)
      5. Prior art detection: `max_similarity >= threshold` (line 115)
      6. Novelty score calculation (lines 120-130):
         - `>= 0.95` similarity: score = 0.0 (duplicate)
         - `>= threshold`: linear decay, capped at 0.5
         - `< threshold`: `1.0 - (similarity * 0.5)`
      7. Returns `NoveltyReport` with score, similar papers, prior art flag, summary
      Data transformation: `Hypothesis` in; `NoveltyReport` out. Also mutates `hypothesis.novelty_score` in place [FACT: novelty_checker.py:168].

    Novelty filtering in generate_hypotheses() (hypothesis_generator.py:208-228):
      After novelty scoring, filtering logic:
      - `self.require_novelty_check` AND `report.novelty_score < self.min_novelty_score` -> filtered out [FACT: hypothesis_generator.py:217]
      - On exception per-hypothesis: fails open -- keeps hypothesis [FACT: hypothesis_generator.py:223-224]
      - On `ImportError` of NoveltyChecker: skips all novelty scoring [FACT: hypothesis_generator.py:227-228]

    Step 6: `_store_hypothesis(hypothesis)` (hypothesis_generator.py:463) -- DB write (terminal side effect)
      1. Opens `get_session()` context manager
      2. Creates `DBHypothesis` SQLAlchemy model from Pydantic model (line 476-489)
      3. `session.add(db_hypothesis)` + `session.commit()` [FACT: hypothesis_generator.py:491-492]
      4. Returns hypothesis ID on success, None on failure
      [SIDE EFFECT: DB write -- hypothesis INSERT] (hypothesis_generator.py:491-492)
      DB model: `kosmos/db/models.py:75` table `hypotheses` with columns: id, research_question, statement, rationale, domain, status, novelty_score, testability_score, confidence_score, related_papers (JSON), created_at, updated_at.
      Session management: `get_session()` (kosmos/db/__init__.py:108) is a context manager that auto-commits on success, auto-rollbacks on exception [FACT: db/__init__.py:133-135].

    Response construction (hypothesis_generator.py:236-257):
      Constructs `HypothesisGenerationResponse` with:
      - `hypotheses`: validated + novelty-filtered list
      - `generation_time_seconds`: wall clock time
      - `num_papers_analyzed`: count of context papers
      - `avg_novelty_score`: mean of non-None novelty scores
      - `avg_testability_score`: mean of non-None testability scores
      Back in `execute()`, response is serialized via `model_to_dict()` (line 122), which handles Pydantic v1/v2 compat [FACT: utils/compat.py:34-38].

  ##### Complete Trace 4a Summary Chain

  ```
  execute(message) [hypothesis_generator.py:91]
    -> generate_hypotheses(question, n, domain) [hypothesis_generator.py:142]
      -> _detect_domain(question) [hypothesis_generator.py:259]
        -> llm_client.generate(prompt, max_tokens=50, temp=0.0) [llm.py:207]
          -> [SIDE EFFECT: Anthropic API call] [llm.py:309]
      -> _gather_literature_context(question, domain) [hypothesis_generator.py:289]
        -> UnifiedLiteratureSearch.search(query, max_results=10) [unified_search.py:76]
          -> ThreadPoolExecutor: ArxivClient.search() + SemanticScholarClient.search() + PubMedClient.search() [unified_search.py:147-161]
            -> [SIDE EFFECT: HTTP calls to arXiv, Semantic Scholar, PubMed APIs]
          -> _deduplicate_papers() [unified_search.py:371]
          -> _rank_papers() [unified_search.py:449]
      -> _generate_with_claude(question, domain, n, papers) [hypothesis_generator.py:322]
        -> HYPOTHESIS_GENERATOR.render(...) [prompts.py:105]
        -> llm_client.generate_structured(prompt, schema, max_tokens=4000, temp=0.7) [llm.py:410]
          -> generate() with retry loop (up to 3 attempts) [llm.py:461]
            -> Cache check [llm.py:278]
            -> client.messages.create() [llm.py:309]
              -> [SIDE EFFECT: Anthropic API call]
            -> Cache store [llm.py:336]
          -> parse_json_response() [core/utils/json_parser.py:31]
        -> Parse JSON into List[Hypothesis] with UUIDs [hypothesis_generator.py:387-420]
      -> _validate_hypothesis(hyp) loop [hypothesis_generator.py:426]
      -> NoveltyChecker.check_novelty(hyp) loop [novelty_checker.py:72]
        -> _search_similar_literature(hyp) [novelty_checker.py:182]
          -> vector_db.search() OR literature_search.search() [novelty_checker.py:194-199]
            -> [SIDE EFFECT: Vector DB query or HTTP API calls]
        -> _check_existing_hypotheses(hyp) [novelty_checker.py:260]
          -> DB query: DBHypothesis filtered by domain [novelty_checker.py:273]
            -> [SIDE EFFECT: DB read]
        -> _compute_similarity() / _compute_hypothesis_similarity() [novelty_checker.py:315/360]
          -> SPECTER embeddings + cosine similarity (or Jaccard fallback) [novelty_checker.py:346-354]
        -> Returns NoveltyReport with score [novelty_checker.py:170]
      -> _store_hypothesis(hyp) loop [hypothesis_generator.py:463]
        -> get_session() [db/__init__.py:108]
        -> session.add(DBHypothesis) + session.commit() [hypothesis_generator.py:491-492]
          -> [SIDE EFFECT: DB write -- hypothesis INSERT to "hypotheses" table]
    -> HypothesisGenerationResponse -> model_to_dict() -> AgentMessage response
  ```

  ##### Hypothesis Generation Data Flow

  ```
  research_question (str)
    -> domain (str, via LLM)
    -> papers (List[PaperMetadata], via 3 APIs)
    -> hypotheses (List[Hypothesis], via LLM + JSON parse)
    -> validated_hypotheses (filtered by length checks)
    -> novel_hypotheses (filtered by novelty score via embeddings/DB)
    -> stored in DB (hypotheses table)
    -> HypothesisGenerationResponse (Pydantic model)
    -> AgentMessage (serialized dict)
  ```

  ✗ on failure at _detect_domain: Falls back to `"general"` domain string. No crash. [FACT: hypothesis_generator.py:286]
  ✗ on failure at literature search: Returns empty list, hypothesis generation proceeds without context papers. [FACT: hypothesis_generator.py:320]
  ✗ on failure at _generate_with_claude: Returns empty hypothesis list. Entire generate_hypotheses returns empty. [FACT: hypothesis_generator.py:424]
  ✗ on failure at novelty check per-hypothesis: Fails open, keeps hypothesis. [FACT: hypothesis_generator.py:223-224]
  ✗ on failure at novelty check import: Skips all novelty scoring, all hypotheses pass. [FACT: hypothesis_generator.py:227-228]
  ✗ on failure at _store_hypothesis: Returns None, hypothesis not persisted but still in response. [FACT: hypothesis_generator.py:502]

#### Sub-Path 4b: LiteratureAnalyzerAgent.execute() Full Chain

`LiteratureAnalyzerAgent.execute(task: Dict[str, Any])` (kosmos/agents/literature_analyzer.py:153)
  Sets `self.status = AgentStatus.WORKING` (line 180). Dispatches on `task["task_type"]` with 5 branches:
  - `"summarize_paper"` -> `summarize_paper()`
  - `"analyze_corpus"` -> `analyze_corpus()`
  - `"citation_network"` -> `analyze_citation_network()`
  - `"find_related"` -> `find_related_papers()`
  - `"extract_methodology"` -> `extract_methodology()`

  On success: increments `self.tasks_completed`, returns result dict. On error: increments `self.errors_encountered`, returns error dict.

  [FACT] Key difference from HypothesisGeneratorAgent: Takes plain dict (not AgentMessage), returns plain dict. Different `execute()` signature. (literature_analyzer.py:153 vs hypothesis_generator.py:91). BaseAgent.execute signature is `(task: Dict) -> Dict` (base.py:485).

  __init__ component initialization (literature_analyzer.py:81):
    Initializes up to 6 components:
    1. `self.llm_client = get_client()` -- LLM provider [FACT: literature_analyzer.py:107]
    2. `self.knowledge_graph = get_knowledge_graph()` -- Neo4j graph (conditional, fails gracefully) [FACT: literature_analyzer.py:111-116]
    3. `self.vector_db = get_vector_db()` -- ChromaDB vector store (conditional) [FACT: literature_analyzer.py:119]
    4. `self.embedder = get_embedder()` -- SPECTER embeddings (conditional) [FACT: literature_analyzer.py:120]
    5. `self.concept_extractor = get_concept_extractor()` -- Claude-powered concept extraction (conditional) [FACT: literature_analyzer.py:123]
    6. `self.semantic_search = SemanticLiteratureSearch()` -- combined API + vector search [FACT: literature_analyzer.py:125]
    7. `self.unified_search = UnifiedLiteratureSearch()` -- multi-source API search [FACT: literature_analyzer.py:126]
    Also creates `.literature_analysis_cache/` directory for file-based caching [FACT: literature_analyzer.py:129].

  ##### Branch: summarize_paper() path

  `summarize_paper(paper: PaperMetadata)` (literature_analyzer.py:231)
    1. Cache check: `_get_cached_analysis(paper.primary_identifier)` -- file-based JSON cache in `.literature_analysis_cache/`, 24-hour TTL [FACT: literature_analyzer.py:1018-1019]
    2. Validation: `_validate_paper(paper)` -- requires title AND (abstract OR full_text) [FACT: literature_analyzer.py:768]
    3. Prompt build: `_build_summarization_prompt(paper)` -- includes title + first 5000 chars of full_text or abstract [FACT: literature_analyzer.py:876]
    4. LLM call: `llm_client.generate_structured(prompt, output_schema, system, max_tokens=4096)` [FACT: literature_analyzer.py:265-269]
      [SIDE EFFECT: Anthropic API call]
    5. Result construction: `PaperAnalysis` dataclass with executive_summary, key_findings, methodology, significance, limitations, confidence_score, analysis_time
    6. Cache write: `_cache_analysis(paper_id, result.to_dict())` [FACT: literature_analyzer.py:284]
      [SIDE EFFECT: File cache write to .literature_analysis_cache/]

  ##### Branch: analyze_corpus() path

  `analyze_corpus(papers: List[PaperMetadata], generate_insights: bool)` (literature_analyzer.py:658)
    1. Temporal distribution: counts papers by year [FACT: literature_analyzer.py:699-702]
    2. Concept extraction: calls `self.concept_extractor.extract_from_paper(paper)` per paper (up to `max_papers_per_analysis`, default 50) [FACT: literature_analyzer.py:709-711]
    3. LLM insights: Summarizes up to 20 papers (200 chars of abstract each), generates structured insights via Claude [FACT: literature_analyzer.py:726-738]
    4. Returns dict with: corpus_size, common_themes, methodological_trends, temporal_distribution, research_gaps, key_authors
    [SIDE EFFECT: Claude API calls] (concept extraction + corpus insights)

  ##### Branch: analyze_citation_network() path

  `analyze_citation_network(paper_id, depth, build_if_missing)` (literature_analyzer.py:415)
    1. Graph query: Tries Neo4j knowledge graph first for citations and citing papers [FACT: literature_analyzer.py:457-459]
    2. On-demand build: If no citations found and `build_if_missing=True`, calls `_build_citation_graph_on_demand(paper_id)` [FACT: literature_analyzer.py:488]
    3. On-demand build fetches from Semantic Scholar API, adds papers + citation relationships to Neo4j [FACT: literature_analyzer.py:791-854]
    4. Recursive retry: After building, calls itself again with `build_if_missing=False` to prevent infinite loop [FACT: literature_analyzer.py:494]
    [SIDE EFFECT: Semantic Scholar API call] (literature_analyzer.py:791)
    [SIDE EFFECT: Neo4j graph writes -- add_paper(), add_citation()] (literature_analyzer.py:816-852)

  ##### Branch: find_related_papers() path

  `find_related_papers(paper, max_results, similarity_threshold)` (literature_analyzer.py:574)
    Two parallel search strategies:
    1. Semantic: `self.vector_db.search_by_paper(paper, top_k)` -- ChromaDB vector search [FACT: literature_analyzer.py:610-611]
    2. Graph: `self.knowledge_graph.find_related_papers(paper_id, max_hops=2)` -- Neo4j graph traversal [FACT: literature_analyzer.py:630-634]
    Results deduplicated by paper ID and merged [FACT: literature_analyzer.py:647-656].
    [SIDE EFFECT: ChromaDB vector search + Neo4j graph traversal]

  ##### Branch: extract_methodology() path

  `extract_methodology(paper: PaperMetadata)` (literature_analyzer.py:348)
    1. Concept extractor first: `self.concept_extractor.extract_from_paper(paper)` -- categorizes methods into experimental/computational/analytical [FACT: literature_analyzer.py:377-393]
    2. Claude fallback: If concept extractor found nothing, falls back to LLM-based extraction [FACT: literature_analyzer.py:398-412]
    [SIDE EFFECT: Claude API calls] (concept extraction and/or methodology extraction)

  ##### Complete Trace 4b Summary Chain

  ```
  execute(task) [literature_analyzer.py:153]
    +-- "summarize_paper":
    |   -> _get_cached_analysis(paper_id) [literature_analyzer.py:1007] -- 24h file cache check
    |   -> _validate_paper(paper) [literature_analyzer.py:766] -- requires title + text
    |   -> _build_summarization_prompt(paper) [literature_analyzer.py:870] -- title + 5000 chars
    |   -> llm_client.generate_structured() [llm.py:410]
    |     -> [SIDE EFFECT: Anthropic API call]
    |   -> _cache_analysis() [literature_analyzer.py:1027]
    |     -> [SIDE EFFECT: file cache write to .literature_analysis_cache/]
    |
    +-- "analyze_corpus":
    |   -> concept_extractor.extract_from_paper() per paper [literature_analyzer.py:711]
    |     -> [SIDE EFFECT: Claude API calls for concept extraction]
    |   -> llm_client.generate_structured() [literature_analyzer.py:733]
    |     -> [SIDE EFFECT: Anthropic API call for corpus insights]
    |
    +-- "citation_network":
    |   -> knowledge_graph.get_citations() [literature_analyzer.py:459]
    |     -> [SIDE EFFECT: Neo4j read]
    |   -> (if missing) _build_citation_graph_on_demand() [literature_analyzer.py:770]
    |     -> SemanticScholarClient.get_paper() [literature_analyzer.py:791]
    |       -> [SIDE EFFECT: Semantic Scholar API call]
    |     -> knowledge_graph.add_paper() + add_citation() [literature_analyzer.py:816-852]
    |       -> [SIDE EFFECT: Neo4j graph writes]
    |     -> self.analyze_citation_network(paper_id, depth, build_if_missing=False)
    |       -> [recursive, max 1 retry]
    |
    +-- "find_related":
    |   -> vector_db.search_by_paper() [literature_analyzer.py:610]
    |     -> [SIDE EFFECT: ChromaDB vector search]
    |   -> knowledge_graph.find_related_papers() [literature_analyzer.py:630]
    |     -> [SIDE EFFECT: Neo4j graph traversal]
    |
    +-- "extract_methodology":
        -> concept_extractor.extract_from_paper() [literature_analyzer.py:377]
          -> [SIDE EFFECT: Claude API call]
        -> (fallback) llm_client.generate_structured() [literature_analyzer.py:402]
          -> [SIDE EFFECT: Anthropic API call]
  ```

  ##### Literature Analysis Data Flow

  ```
  task dict (with task_type + params)
    -> dispatch to appropriate analysis method
    -> paper(s) processed via LLM/graph/vector DB
    -> result dict with structured analysis
  ```

  ##### External Dependencies Hit by Path 4

  | Component | Technology | Purpose |
  |-----------|-----------|---------|
  | Anthropic API | Claude Sonnet/Haiku | Domain detection, hypothesis generation, paper analysis |
  | arXiv API | HTTP REST | Paper search |
  | Semantic Scholar API | HTTP REST | Paper search + citations |
  | PubMed API | HTTP REST | Paper search |
  | SQLAlchemy/SQLite | SQL DB | Hypothesis storage, existing hypothesis queries |
  | Neo4j | Graph DB | Citation network, related paper discovery |
  | ChromaDB | Vector DB | Semantic similarity search |
  | SPECTER model | sentence-transformers | Paper/hypothesis embeddings (768-dim) |

  ✗ on failure at Neo4j: Agent silently degrades -- sets `self.use_knowledge_graph = False` and continues without graph features. [FACT: literature_analyzer.py:114-116]
  ✗ on failure at citation network build: References capped at 50, citations capped at 50 per paper. Recursive call with `build_if_missing=False` prevents infinite recursion but means only 1 retry attempt. [FACT: literature_analyzer.py:821, 838]

---

### Path 5: Code Generation, Sandbox Execution, and Result Analysis

This path covers the experiment execution pipeline in detail: template matching for code generation, sandboxed execution, and LLM-powered result interpretation.

#### Sub-Path 5a: ExperimentCodeGenerator.generate() -- Template Matching + LLM Fallback

`ExperimentCodeGenerator.generate()` (kosmos/execution/code_generator.py:797)

  -> `self._match_template(protocol)` (code_generator.py:835)
    Iterates `self.templates` list, calls `template.matches(protocol)` on each.
    [FACT] 5 templates registered in priority order (code_generator.py:787-793):
      1. TTestComparisonCodeTemplate -- matches DATA_ANALYSIS + t_test in statistical_tests
      2. CorrelationAnalysisCodeTemplate -- matches DATA_ANALYSIS + correlation/regression
      3. LogLogScalingCodeTemplate -- matches keywords: scaling, power law, log-log
      4. MLExperimentCodeTemplate -- matches COMPUTATIONAL + ML keywords
      5. GenericComputationalCodeTemplate -- catch-all for COMPUTATIONAL or DATA_ANALYSIS
    Returns first matching CodeTemplate or None.

  IF template matched:
    -> `template.generate(protocol)` (e.g. code_generator.py:71 for TTest)
      Returns string of executable Python code.
      [FACT] All templates generate synthetic data fallback if data_path not available (code_generator.py:112-129)
      [FACT] All templates import DataAnalyzer from kosmos.execution.data_analysis (code_generator.py:107)
      [FACT] All templates set `results = result` at end for executor to extract (code_generator.py:187)
      [FACT] All templates include assumption checks (normality via Shapiro, variance via Levene) (code_generator.py:135-144)

    IF `llm_enhance_templates` enabled:
      -> `self._enhance_with_llm(code, protocol)` (code_generator.py:926)
        -> `self.llm_client.generate(prompt)` (code_generator.py:947)
          [SIDE EFFECT: LLM API call] Asks Claude to enhance template code
        -> `self._extract_code_from_response(response)` (code_generator.py:907)
          Parses ```python blocks from LLM response

  IF no template matched AND use_llm:
    -> `self._generate_with_llm(protocol)` (code_generator.py:842)
      -> `self._create_code_generation_prompt(protocol)` (code_generator.py:858)
        Builds prompt from protocol steps, variables, statistical tests
      -> `self.llm_client.generate(prompt)` (code_generator.py:847)
        [SIDE EFFECT: LLM API call] Generates entire experiment code
      -> `self._extract_code_from_response(response)` (code_generator.py:907)

  IF still no code (both template and LLM failed):
    -> `self._generate_basic_template(protocol)` (code_generator.py:954)
      Minimal fallback: `pd.read_csv(data_path)` + `df.describe()`
      [GOTCHA] This fallback does NOT include synthetic data generation, so it will crash if data_path is not set (code_generator.py:964)

  ALWAYS:
    -> `self._validate_syntax(code)` (code_generator.py:982)
      [FACT] Uses `ast.parse(code)` for syntax validation (code_generator.py:984)
      Raises ValueError on SyntaxError

  Data Transformations:
  - Input: `ExperimentProtocol` (Pydantic model with steps, variables, statistical_tests, control_groups)
  - Output: `str` (executable Python code)
  - Template selection reads: `protocol.experiment_type`, `protocol.statistical_tests`, `protocol.name`, `protocol.description`
  - Generated code expects `data_path` variable injected by executor and a `results` variable at the end for return value extraction

  Branching Summary:
  1. Template match found -> use template code (optionally LLM-enhanced)
  2. No template -> LLM generates full code
  3. Both fail -> minimal basic template (risky: no synthetic data)

  ✗ on failure at template match: Falls through to LLM generation.
  ✗ on failure at LLM generation: Falls through to basic template.
  ✗ on failure at basic template: `_validate_syntax` raises ValueError. No code produced.

#### Sub-Path 5b: CodeExecutor.execute() -- Sandbox Execution with Retry

`CodeExecutor.execute(code, local_vars, retry_on_error, llm_client, language)` (kosmos/execution/executor.py:237)

  -> Language auto-detection (executor.py:261-266)
    If R executor available, calls `self.r_executor.detect_language(code)`. Default: 'python'.

  IF language == 'r':
    -> `self._execute_r(code)` (executor.py:378)
      -> `self.r_executor.execute(code, capture_results=True)` (executor.py:396)
      Returns ExecutionResult converted from RExecutionResult
      [SIDE EFFECT: subprocess.run via R executor]

  ELSE (Python execution):
    RETRY LOOP (max `self.max_retries` attempts if retry_on_error, else 1):
      -> `self._execute_once(current_code, local_vars)` (executor.py:282)

        IF self.use_sandbox:
          -> `self._execute_in_sandbox(code, local_vars)` (executor.py:555)
            Prepares data_files dict from `local_vars['data_path']` (executor.py:565-570)
            Prepends data_path assignment to code (executor.py:573)
            -> `self.sandbox.execute(code, data_files)` (executor.py:576)
              [SIDE EFFECT: Docker container creation + execution]
              See DockerSandbox trace below
            Converts SandboxExecutionResult -> ExecutionResult (executor.py:579-587)

        ELSE (non-sandboxed, restricted builtins):
          -> `self._prepare_globals()` (executor.py:589)
            [FACT] Creates restricted builtins dict from SAFE_BUILTINS (executor.py:594)
            [FACT] Installs restricted `__import__` allowing only _ALLOWED_MODULES (executor.py:595)
            [FACT] Allowed modules: numpy, pandas, scipy, sklearn, matplotlib, seaborn, statsmodels, math, statistics, xarray, netCDF4, h5py, zarr, dask + stdlib (executor.py:86-94)

          -> `self._exec_with_timeout(code, exec_globals, exec_locals)` (executor.py:600)
            ON Unix:
              Uses `signal.SIGALRM` for timeout (executor.py:608-620)
              [SIDE EFFECT: exec(code, exec_globals, exec_locals)] (executor.py:617)
            ON Windows:
              Uses `ThreadPoolExecutor` with timeout (executor.py:622-630)
              [SIDE EFFECT: exec(code, exec_globals, exec_locals)] (executor.py:624)
            Default timeout: 300 seconds (executor.py:40)

          Captures stdout/stderr via `redirect_stdout/redirect_stderr` (executor.py:496-504)
          Extracts return value: `exec_locals.get('results', exec_locals.get('result'))` (executor.py:516)
          Extracts data_source: `exec_locals.get('_data_source')` (executor.py:517)

        IF enable_profiling:
          Wraps execution with `ExecutionProfiler` from kosmos.core.profiling (executor.py:482-486, 501-511)

      IF result.success:
        IF test_determinism:
          -> `ReproducibilityManager().test_determinism()` (executor.py:296-299)
            Re-runs execution 2x comparing outputs
        RETURN result

      IF result failed AND retry_on_error:
        -> `self.retry_strategy.modify_code_for_retry(current_code, error, ...)` (executor.py:317-324)
          Attempts LLM repair first (if client available, attempt <= 2) (executor.py:779-788)
          Then pattern-based fixes for 11 error types (executor.py:791-825):
            KeyError, FileNotFoundError, NameError, TypeError, IndexError,
            AttributeError, ValueError, ZeroDivisionError, ImportError,
            PermissionError, MemoryError
          [GOTCHA] FileNotFoundError returns None (terminal, no fix) (executor.py:879-906)
          [GOTCHA] Most pattern fixes just wrap code in try/except (executor.py:869-1008)
          NameError fix: auto-inserts common imports from COMMON_IMPORTS dict (executor.py:908-916)
        -> `time.sleep(delay)` with exponential backoff (executor.py:333-335)

    IF all retries exhausted:
      RETURN ExecutionResult(success=False, error_type="MaxRetriesExceeded") (executor.py:372-376)

  Data Transformations:
  - Input: `str` (Python code), optional `Dict[str, Any]` (local_vars), optional LLM client
  - Output: `ExecutionResult` with fields: success, return_value, stdout, stderr, error, error_type, execution_time, profile_result, data_source
  - Return value extracted from `results` or `result` variable in exec namespace (executor.py:516)

  Branching Summary:
  1. R code -> R executor (subprocess)
  2. Python + sandbox -> Docker container
  3. Python + no sandbox -> restricted exec() with SIGALRM/ThreadPool timeout
  4. Failure -> retry with code modification (LLM or pattern-based)

  ✗ on failure at exec(): Retry loop kicks in with code modification. Up to 3 retries with exponential backoff.
  ✗ on failure at all retries: Returns ExecutionResult(success=False, error_type="MaxRetriesExceeded").
  ✗ on FileNotFoundError: Terminal -- retry strategy returns None, no fix attempted.

#### Sub-Path 5c: DockerSandbox.execute() -- Container Isolation

`DockerSandbox.execute(code, data_files, environment)` (kosmos/execution/sandbox.py:163)

  -> `tempfile.mkdtemp(prefix="kosmos_sandbox_")` (sandbox.py:181)
  -> Write code to `temp_dir/code/experiment.py` (sandbox.py:185-186)
  -> Copy data files to `temp_dir/data/` if provided (sandbox.py:190-196)
  -> Create `temp_dir/output/` directory (sandbox.py:199)

  -> `self._run_container(temp_dir, environment)` (sandbox.py:203)
    Prepares Docker volume mounts (sandbox.py:240-248):
      `/workspace/code` (ro), `/workspace/output` (rw), `/workspace/data` (ro)
    Container config (sandbox.py:259-277):
      [FACT] image: `kosmos-sandbox:latest` (sandbox.py:79)
      [FACT] command: `python3 /workspace/code/experiment.py` (sandbox.py:261)
      [FACT] mem_limit: 2g default (sandbox.py:83)
      [FACT] cpu_limit: 2.0 cores default (sandbox.py:82)
      [FACT] network_disabled: True (sandbox.py:92)
      [FACT] read_only: True (sandbox.py:93)
      [FACT] security_opt: no-new-privileges (sandbox.py:274)
      [FACT] cap_drop: ALL (sandbox.py:275)
      [FACT] tmpfs: /tmp (100m), /home/sandbox/.local (50m) (sandbox.py:269-272)

    -> `self.client.containers.create(**container_config)` (sandbox.py:285)
      [SIDE EFFECT: Docker API call to create container]

    IF enable_monitoring:
      -> `threading.Thread(target=self._monitor_container, ...)` (sandbox.py:290-295)
        Tracks CPU% and memory usage in background (sandbox.py:402-436)

    -> `container.start()` (sandbox.py:299)
      [SIDE EFFECT: Container starts executing experiment.py]

    -> `container.wait(timeout=self.timeout)` (sandbox.py:304)
      Default timeout: 300 seconds (sandbox.py:84)
      ON timeout:
        -> `container.stop(timeout=5)` then `container.kill()` (sandbox.py:313-317)

    -> `container.logs(stdout=True/False, stderr=True/False)` (sandbox.py:331-332)
    -> `self._extract_return_value(stdout)` (sandbox.py:352)
      [FACT] Parses stdout for lines starting with "RESULT:" prefix (sandbox.py:442-448)
      Tries `json.loads()` on the payload
      [GOTCHA] Generated code does NOT emit "RESULT:" prefix -- it stores results in local variable `results`. This means sandbox path returns None for return_value unless the generated code explicitly prints "RESULT:{json}". The non-sandbox path extracts via `exec_locals.get('results')` which does work.

    RETURN SandboxExecutionResult(success, return_value, stdout, stderr, ...)

  FINALLY:
    -> `shutil.rmtree(temp_dir)` (sandbox.py:213)
    -> `container.remove(force=True)` (sandbox.py:397)

  Data Transformations:
  - Input: `str` (code), optional `Dict[str, str]` (data_files: filename->path)
  - Output: `SandboxExecutionResult` with: success, return_value, stdout, stderr, error, error_type, execution_time, exit_code, timeout_occurred, resource_stats

  Security Model [FACT]:
  1. Restricted builtins (non-sandbox): Only safe builtins + scientific modules allowed (executor.py:43-94)
  2. Docker isolation (sandbox): network disabled, read-only fs, all capabilities dropped, no-new-privileges, tmpfs for /tmp (sandbox.py:259-277)
  3. Code validation: `CodeValidator` from `kosmos.safety.code_validator` validates before execution (executor.py:1040-1048)
  4. Timeout protection: SIGALRM on Unix, ThreadPoolExecutor on Windows, Docker wait timeout (executor.py:600-631, sandbox.py:304)

  ✗ on failure at container creation: Docker API error propagates up to CodeExecutor.
  ✗ on timeout: Container killed, SandboxExecutionResult with timeout_occurred=True returned.
  ✗ on return value extraction: Sandbox path silently returns None if code does not print "RESULT:" prefix.

#### Sub-Path 5d: DataAnalystAgent.interpret_results() -- LLM-Powered Result Analysis

`DataAnalystAgent.interpret_results(result, hypothesis, literature_context)` (kosmos/agents/data_analyst.py:326)

  -> `self._extract_result_summary(result)` (data_analyst.py:381)
    Extracts: experiment_id, status, primary_test, primary_p_value, primary_effect_size, supports_hypothesis (data_analyst.py:383-390)
    Adds statistical_tests details: test_name, statistic, p_value, effect_size, effect_size_type, significance_label, sample_size (data_analyst.py:394-403)
    Adds top 5 variable results: name, mean, median, std, min, max, n_samples (data_analyst.py:407-417)

  -> `self._build_interpretation_prompt(result_summary, hypothesis, literature_context)` (data_analyst.py:421)
    Includes hypothesis statement if provided (data_analyst.py:432-438)
    Includes result summary with statistical tests (data_analyst.py:441-460)
    Includes literature context (truncated to 1000 chars) if provided (data_analyst.py:463-467)
    Requests JSON response with 9 fields (data_analyst.py:470-503)

  -> `self.llm_client.generate(prompt, system=..., max_tokens=2000, temperature=0.3)` (data_analyst.py:355-362)
    [SIDE EFFECT: LLM API call to Claude]
    System prompt: "You are an expert scientific data analyst..." (data_analyst.py:357-359)

  -> `self._parse_interpretation_response(response_text, experiment_id, result)` (data_analyst.py:508)
    Extracts JSON by finding first '{' and last '}' (data_analyst.py:517-519)
    `json.loads()` to parse (data_analyst.py:521)
    IF `anomaly_detection_enabled`:
      -> `self.detect_anomalies(result)` (data_analyst.py:524)
        Checks: significant p-value + tiny effect size (data_analyst.py:594-601)
        Checks: large effect size + non-significant p-value (data_analyst.py:604-611)
        Checks: p-value exactly 0.0 or 1.0 (data_analyst.py:614-623)
        Checks: inconsistent statistical tests (data_analyst.py:626-636)
        Checks: high coefficient of variation in variables (data_analyst.py:639-647)
    Returns ResultInterpretation object

  ON json.JSONDecodeError:
    -> `self._create_fallback_interpretation(result)` (data_analyst.py:548)
      Uses raw result fields (p_value, effect_size) directly (data_analyst.py:554-558)
      confidence=0.5, assessment="Automated fallback" (data_analyst.py:553, 568)

  -> `self.interpretation_history.append(interpretation)` (data_analyst.py:371)
    Stores for later pattern detection across results

  RETURN ResultInterpretation

  Data Transformations:
  - Input: `ExperimentResult` (Pydantic model), optional `Hypothesis`, optional `str` (literature_context)
  - Output: `ResultInterpretation` with: hypothesis_supported (bool/None), confidence (0-1), summary, key_findings, significance_interpretation, biological_significance, potential_confounds, follow_up_experiments, anomalies_detected, patterns_detected, overall_assessment

  ✗ on failure at LLM call: Falls through to `_create_fallback_interpretation()` with confidence=0.5 and "Automated fallback" assessment.
  ✗ on failure at JSON parse: Same fallback path as LLM failure.

#### Sub-Path 5e: ExperimentDesignerAgent.execute() -- Protocol Design

`ExperimentDesignerAgent.execute(message)` (kosmos/agents/experiment_designer.py:109)
  Sets status = WORKING (experiment_designer.py:119)
  Extracts `task_type` from `message.content` (experiment_designer.py:122)

  IF task_type == "design_experiment":
    Extracts: hypothesis_id, hypothesis, preferred_type, max_cost, max_duration (experiment_designer.py:125-129)

    -> `self.design_experiment(hypothesis, hypothesis_id, ...)` (experiment_designer.py:131-137)

      Step 1: Load hypothesis if only ID provided (experiment_designer.py:195-198)
        -> `self._load_hypothesis(hypothesis_id)` (experiment_designer.py:353)
          -> `session.query(DBHypothesis).filter_by(id=hypothesis_id)` (experiment_designer.py:356)
            [SIDE EFFECT: Database SELECT]

      Step 2: Select experiment type (experiment_designer.py:201-202)
        -> `self._select_experiment_type(hypothesis, preferred)` (experiment_designer.py:380)
          Uses preferred > hypothesis.suggested_experiment_types > domain_defaults
          [FACT] Domain defaults map ML/AI/CS -> COMPUTATIONAL, stats/data_science/psych/neuro -> DATA_ANALYSIS (experiment_designer.py:394-403)

      Step 3: Generate protocol (experiment_designer.py:205-218)
        IF use_templates:
          -> `self._generate_from_template(hypothesis, experiment_type, ...)` (experiment_designer.py:409)
            -> `self.template_registry.find_best_template(hypothesis, experiment_type)` (experiment_designer.py:418)
            -> `template.generate_protocol(params)` (experiment_designer.py:435)
            Falls back to LLM if no template found (experiment_designer.py:421-423)
        ELSE:
          -> `self._generate_with_claude(hypothesis, experiment_type, ...)` (experiment_designer.py:441)
            -> `self.llm_client.generate_structured(prompt, schema, ...)` (experiment_designer.py:495-499)
              [SIDE EFFECT: LLM API call] with JSON schema for structured output
              max_tokens=8192 (experiment_designer.py:499)
            -> `self._parse_claude_protocol(protocol_data, hypothesis, experiment_type)` (experiment_designer.py:510)
              Parses steps, variables, control_groups, statistical_tests, resources
              [GOTCHA] If LLM returns empty steps, generates 3 default steps (experiment_designer.py:568-586)
              [GOTCHA] If LLM returns empty variables, generates 2 default variables (experiment_designer.py:589-601)
              [FACT] Coerces variable values: strings -> None, scalars -> [scalar] (experiment_designer.py:547-555)

      Step 4: LLM enhancement (experiment_designer.py:221-222)
        IF `use_llm_enhancement` AND `use_templates`:
          -> `self._enhance_protocol_with_llm(protocol, hypothesis)` (experiment_designer.py:681)
            -> `self.llm_client.generate(prompt, max_tokens=1000)` (experiment_designer.py:711)
              [SIDE EFFECT: LLM API call]
            [GOTCHA] Enhancement response is not actually parsed or applied (experiment_designer.py:714-717). The method logs "LLM enhancements applied" but returns protocol unchanged.

      Step 4b: Power analysis (experiment_designer.py:225-260)
        -> `PowerAnalyzer.ttest_sample_size()` / `correlation_sample_size()` / `anova_sample_size()`
          Updates `protocol.sample_size` if power analysis yields higher N
          [FACT] Falls back silently on ImportError (experiment_designer.py:259-260)

      Step 5: Validate protocol (experiment_designer.py:263)
        -> `self._validate_protocol(protocol)` (experiment_designer.py:720)
          -> `ExperimentValidator.validate(protocol)` (experiment_designer.py:729)
            [FACT] Falls back to inline validation if ExperimentValidator fails (experiment_designer.py:737-739)
          Inline checks: control group, sample size >= 10, independent/dependent vars, statistical tests, >= 3 steps, duration estimate (experiment_designer.py:741-777)

      Step 6: Calculate metrics (experiment_designer.py:266-268)
        -> `self._calculate_rigor_score()` -- 0.0-1.0 (experiment_designer.py:779)
        -> `self._calculate_completeness_score()` -- 0/10 checklist (experiment_designer.py:807)
        -> `self._assess_feasibility()` -- "High"/"Medium"/"Low" (experiment_designer.py:836)

      Step 7: Store in DB (experiment_designer.py:271-272)
        -> `self._store_protocol(protocol, hypothesis)` (experiment_designer.py:885)
          -> `session.add(DBExperiment(...))` (experiment_designer.py:896-900)
            [SIDE EFFECT: Database INSERT]
          [FACT] Gracefully handles "Database not initialized" and schema mismatch (experiment_designer.py:909-921)

      Step 8: Create response (experiment_designer.py:275-293)
        -> `ExperimentDesignResponse(protocol, rigor_score, completeness_score, ...)`

    RETURN `AgentMessage(type=RESPONSE, content={"response": model_to_dict(response)})`

  ELSE:
    RAISE `ValueError(f"Unknown task type: {task_type}")` (experiment_designer.py:148)

  ON ERROR:
    Sets status = ERROR, returns `AgentMessage(type=ERROR)` (experiment_designer.py:151-158)

  FINALLY:
    Sets status = IDLE (experiment_designer.py:162)

  ✗ on failure at hypothesis load: Returns error AgentMessage. No experiment designed.
  ✗ on failure at template + LLM: Falls back to basic template (risky). Or raises if that too fails.
  ✗ on failure at DB store: Gracefully handled. Protocol still returned in response but not persisted.

#### Sub-Path 5f: Research Director Orchestration of Execution Pipeline

`_handle_execute_experiment_action(protocol_id)` (research_director.py:1521)
  Lazy-initializes (research_director.py:1537-1543):
    `ExperimentCodeGenerator(use_templates=True, use_llm=True)`
    `CodeExecutor(max_retries=3)`
    `DataProvider(default_data_dir=self.data_path)`

  -> Load protocol from DB (research_director.py:1551-1561)
    -> `get_experiment(session, protocol_id)` (research_director.py:1552)
    -> `ExperimentProtocol.model_validate(protocol_data)` (research_director.py:1559)

  -> `self._code_generator.generate(protocol)` -> code (research_director.py:1564)
    See Sub-Path 5a above

  -> `self._code_executor.execute_with_data(code, data_path, retry_on_error=True)`
    OR `self._code_executor.execute(code, retry_on_error=True)` (research_director.py:1567-1572)
    `execute_with_data()` prepends data_path assignment to code (executor.py:655)
    See Sub-Path 5b above

  -> Extract metrics from `exec_result.return_value` (research_director.py:1578-1591)
    Pulls: p_value, effect_size, t_statistic, correlation, r_squared, etc.

  -> `_json_safe(return_value)` (research_director.py:1595-1613)
    Sanitizes numpy arrays/integers/floats for JSON serialization

  -> `create_result(session, ...)` in DB (research_director.py:1621-1630)
    [SIDE EFFECT: Database INSERT] Stores result with p_value, effect_size, statistical_tests

  -> `self.research_plan.add_result(result_id)` (research_director.py:1641)
  -> `self.research_plan.mark_experiment_complete(protocol_id)` (research_director.py:1642)
  -> `self._persist_result_to_graph(result_id, protocol_id, hypothesis_id)` (research_director.py:1646-1648)
  -> `workflow.transition_to(WorkflowState.ANALYZING)` (research_director.py:1651-1655)

  ON ERROR:
    -> `self._handle_error_with_recovery(error_source="CodeExecutor", ...)` (research_director.py:1659-1663)

  Then proceeds to analysis:

  `_handle_analyze_result_action(result_id)` (research_director.py:1666)
    Lazy-initializes DataAnalystAgent (research_director.py:1680-1681)

    -> Load result from DB (research_director.py:1690-1722)
      -> `db_get_result(session, result_id, with_experiment=True)` (research_director.py:1691)
      Constructs ExperimentResult pydantic model (research_director.py:1704-1722)
      Loads Hypothesis if hypothesis_id available (research_director.py:1725-1734)

    -> `self._data_analyst.interpret_results(result, hypothesis)` (research_director.py:1737-1740)
      See Sub-Path 5d above

    -> Extract interpretation fields (research_director.py:1746-1748)
      hypothesis_supported, confidence, p_value, effect_size

    -> Update research plan (research_director.py:1760-1767)
      `mark_supported()`, `mark_rejected()`, or `mark_tested()`

    -> `self._add_support_relationship(result_id, hypothesis_id, supports, confidence, ...)` (research_director.py:1770-1778)
      [SIDE EFFECT: Knowledge graph update] Adds SUPPORTS/REFUTES edge

    -> `workflow.transition_to(WorkflowState.REFINING)` (research_director.py:1780-1785)

    ON ERROR:
      -> `self._handle_error_with_recovery(error_source="DataAnalystAgent", ...)` (research_director.py:1789-1793)

  Workflow State Transitions:
  ```
  EXECUTING -> (experiment completes) -> ANALYZING -> (interpretation done) -> REFINING
                                                                                |
                                                                         (hypothesis update)
  ```

  ##### Key Patterns Observed in Path 5

  [PATTERN] Synthetic data fallback (4/5 templates): All specialized code templates include `if df is None: np.random.seed(seed); ...` synthetic data generation as fallback when no data file is available (code_generator.py:119-129, 253-260, 391-397, 483-488).

  [PATTERN] Lazy initialization (3/3 components in research_director): CodeGenerator, CodeExecutor, and DataAnalystAgent are all lazily initialized on first use via `if self._X is None: self._X = X(...)` (research_director.py:1537-1544, 1680-1681).

  [PATTERN] Graceful degradation (3 layers): (1) Docker sandbox falls back to restricted exec if Docker unavailable (executor.py:216-221), (2) ExperimentValidator falls back to inline validation (experiment_designer.py:737-739), (3) ClaudeClient falls back to LiteLLM provider (code_generator.py:766-776).

  [PATTERN] JSON sanitization before DB: Research director sanitizes numpy types (ndarray -> list, np.integer -> int, np.floating -> float) before database storage via recursive `_json_safe()` (research_director.py:1595-1613).

  ✗ on failure at code generation: `_handle_error_with_recovery()` invoked, increments error counter, may retry or force CONVERGE.
  ✗ on failure at code execution: Retry loop in CodeExecutor handles up to 3 retries. If all fail, error propagates to director's error recovery.
  ✗ on failure at result analysis: Fallback interpretation with confidence=0.5. Director continues to REFINING state.
# Module Behavioral Index

## Summary Table

| Module | Does | Runtime Deps | Danger |
|--------|------|--------------|--------|
| `kosmos/agents/base.py` | Defines `BaseAgent` lifecycle, async message passing, state persistence, and health monitoring for all 6 agent subclasses | `pydantic`, `asyncio`, `kosmos.config.get_config` (deferred), `kosmos.agents.registry` | Sync `message_queue` list grows without bound (memory leak); registered message handlers are never dispatched (dead code); `_on_pause()`/`_on_resume()` hooks exist but are never called |
| `kosmos/core/providers/anthropic.py` | Implements the Anthropic Claude LLM provider with sync/async generation, streaming, structured JSON output, response caching, auto model selection, cost tracking, and CLI mode routing | `anthropic` (hard), `kosmos.core.providers.base`, `kosmos.core.utils.json_parser`, `kosmos.core.claude_cache`, `kosmos.config`, `kosmos.core.pricing`, `kosmos.core.events`+`event_bus` (lazy) | Cache hits do not update usage stats (undercounting); streaming counts text chunks as "tokens" (inaccurate); CLI mode detection triggers on any all-9s string including single-char `"9"` |
| `kosmos/literature/base_client.py` | Defines abstract `BaseLiteratureClient` and unified data types (`PaperMetadata`, `Author`, `PaperSource`) for all literature API integrations | stdlib only (`abc`, `dataclasses`, `logging`, `typing`, `datetime`, `enum`) -- zero external or Kosmos dependencies | `_validate_query` logs "truncating to 1000" but does NOT actually truncate; `_normalize_paper_metadata` raises `NotImplementedError` but is not `@abstractmethod`; `_handle_api_error` swallows exceptions after logging |
| `kosmos/execution/code_generator.py` | Generates executable Python code from `ExperimentProtocol` via template matching (5 built-in templates) with LLM fallback and minimal hardcoded template as last resort | `kosmos.models.experiment`, `kosmos.core.llm.ClaudeClient`, `kosmos.core.providers.litellm_provider.LiteLLMProvider` (lazy), `kosmos.config.get_config` (lazy); generated code imports `pandas`, `numpy`, `scipy`, `sklearn` | `random_seed=0` silently overridden to 42 due to `or 42` pattern; basic fallback template lacks synthetic data support; LLM client failure silently disables LLM generation; template match is order-dependent with no priority scoring |
| `kosmos/safety/code_validator.py` | Validates generated Python code for safety (dangerous imports/calls/file/network), security (AST reflection detection), and ethical compliance (keyword screening), producing a `SafetyReport` | `kosmos.models.safety` (Pydantic models), `kosmos.utils.compat.model_to_dict`, `kosmos.config.get_config`, `ast`+`json`+`pathlib` (stdlib) | Pattern detection matches inside comments and string literals; `getattr()` flagged as CRITICAL despite being common safe usage; `open()` write-mode detection misses `'wb'`, `'ab'`, `'r+'`; approval request truncates code to 500 chars |
| `kosmos/core/convergence.py` | Decides when the autonomous research loop should stop by evaluating mandatory and optional stopping criteria, then generates a convergence report | `kosmos.core.workflow.ResearchPlan`, `kosmos.models.hypothesis.Hypothesis`, `kosmos.models.result.ExperimentResult`, `kosmos.utils.compat.model_to_dict`, `pydantic` | `novelty_trend` grows without bound; `StoppingReason.USER_REQUESTED` used as sentinel for "no reason" (false positives); flat novelty score counted as "declining"; iteration limit can be deferred indefinitely |
| `kosmos/execution/executor.py` | Executes generated Python/R code with restricted builtins sandbox, output capture, timeout enforcement, optional profiling, determinism testing, and self-correcting retry logic | `kosmos.execution.sandbox.DockerSandbox` (optional), `kosmos.execution.r_executor.RExecutor` (optional), `kosmos.safety.code_validator.CodeValidator`, `kosmos.utils.compat.model_to_dict`, `kosmos.core.profiling.ExecutionProfiler` (lazy), `concurrent.futures`, `signal` | Windows timeout cannot kill stuck threads; retry fix wraps code in try/except masking the real error; return value requires `results`/`result` variable by convention; `time.sleep()` in retry blocks event loop |
| `kosmos/models/experiment.py` | Defines Pydantic data models for experiment design: variables, control groups, protocol steps, resources, statistical tests, validation, full protocols, design requests/responses | `pydantic`, `kosmos.models.hypothesis.ExperimentType` (top-level import chain), `kosmos.config._DEFAULT_CLAUDE_SONNET_MODEL` (top-level), `logging`, `re` (call-time import) | `ExperimentType` imported from hypothesis.py not defined here; `validate_steps` silently sorts steps by number; `to_dict()` is hand-written (100 lines) -- new fields silently missing; `_MAX_SAMPLE_SIZE=100000` silently clamps values |
| `kosmos/knowledge/graph.py` | Neo4j-backed knowledge graph with CRUD for 4 node types and 5 relationship types, plus graph traversal queries for citations, co-occurrence, and multi-hop discovery | `py2neo` (hard), `kosmos.config.get_config`, `kosmos.literature.base_client.PaperMetadata`, Docker+docker-compose CLI tools, Neo4j server | Auto-starts Docker container (up to 60s blocking); connection failure silently swallowed; `create_authored`/`create_discusses`/`create_uses_method` increment counters non-idempotently; Cypher f-string interpolation risk; `clear_graph()` is irreversible |
| `kosmos/models/hypothesis.py` | Defines Pydantic data models for hypothesis lifecycle: generation requests/responses, hypothesis objects with scores and evolution tracking, novelty/testability reports, prioritized wrappers | `pydantic`, `kosmos.config._DEFAULT_CLAUDE_SONNET_MODEL` (top-level), `datetime`+`enum`+`typing` (stdlib) | `ExperimentType` defined HERE not in experiment.py; `model_config = ConfigDict(use_enum_values=False)` means enum objects not strings; `_DEFAULT_CLAUDE_SONNET_MODEL` import-time config dependency; `datetime.utcnow()` deprecated in 3.12+ |
| `kosmos/core/llm.py` | Unified LLM client interface supporting Anthropic (API+CLI) and OpenAI-compatible providers through a singleton pattern; all LLM access funnels through `get_client()`/`get_provider()` | `anthropic` (optional but required at runtime), `kosmos.config`, `kosmos.core.pricing`, `kosmos.core.claude_cache`, `kosmos.core.utils.json_parser`, `kosmos.core.providers.base`, `kosmos.core.providers.anthropic` (lazy), `ANTHROPIC_API_KEY` env var | CLI mode on all-9s key changes cost tracking silently; singleton holds either `ClaudeClient` OR `LLMProvider` with different interfaces; auto model selection never picks higher than Sonnet; cost estimation hardcodes `"claude-sonnet-4-5"` model name |
| `kosmos/core/logging.py` | Structured logging with JSON/text modes, module-level `ContextVar` for correlation IDs, and `ExperimentLogger` for lifecycle event tracking with timing | `logging`+`logging.handlers`, `contextvars`, `json` (all stdlib); `kosmos.config.get_config` (deferred import in `configure_from_config`) | `setup_logging()` clears ALL root logger handlers including third-party; `TextFormatter` mutates `record.levelname` in place (ANSI leak to other handlers); `ExperimentLogger.events` list unbounded; `JSONFormatter` has no serialization guard |
| `kosmos/core/providers/base.py` | Abstract `LLMProvider` interface and supporting data types (`Message`, `UsageStats`, `LLMResponse`, `ProviderAPIError`) for all LLM provider implementations | stdlib only (`abc`, `datetime`, `typing`) -- zero external deps; concrete providers import FROM this module | `LLMResponse` string methods return `str` not `LLMResponse` (metadata lost); empty content makes response falsy; `if False: yield` is load-bearing dead code; `_update_usage_stats` skips `cost_usd=0.0` (falsy); `is_recoverable()` order-dependent |
| `kosmos/agents/research_director.py` | Master orchestrator driving the full research cycle (hypothesize->design->execute->analyze->refine->iterate) via 6+ agents, workflow state machine, convergence detection, error recovery, and graph persistence | `kosmos.agents.base`, `kosmos.utils.compat`, `kosmos.core.rollout_tracker`, `kosmos.core.workflow`, `kosmos.core.convergence`, `kosmos.core.llm`, `kosmos.core.stage_tracker`, `kosmos.models.hypothesis`, `kosmos.world_model`, `kosmos.db`, `kosmos.agents.skill_loader` + many lazy imports | `time.sleep()` error backoff blocks async event loop; message-based `_send_to_*` methods are dead code (Issue #76); `_actions_this_iteration` lazily initialized via `hasattr`; DB init failure only logged as warning; sync/async lock paths have no mutual exclusion |
| `kosmos/models/result.py` | Defines Pydantic data models for experiment results: `ExperimentResult`, `StatisticalTestResult`, `VariableResult`, `ExecutionMetadata`, `ResultStatus`, `ResultExport` | `pydantic`, `kosmos.utils.compat.model_to_dict`, `pandas` (lazy import in `export_csv` only) | `export_markdown()` crashes on `None` stats with `TypeError`; `export_csv()` requires pandas (only place in models layer); `datetime.utcnow()` deprecated; `validate_primary_test` handles dict+model instances fragile if Pydantic changes ordering |
| `kosmos/orchestration/` (4 modules) | Strategic research planning: `PlanCreatorAgent` generates 10-task plans, `NoveltyDetector` filters redundant tasks via semantic similarity, `PlanReviewerAgent` validates on 5 dimensions, `DelegationManager` executes in parallel batches | `anthropic` (direct SDK, bypasses Kosmos provider), `sentence-transformers` (optional, Jaccard fallback), `asyncio`; agents injected via constructor dict | Both PlanCreator and PlanReviewer bypass Kosmos LLMProvider (no caching/cost tracking); DelegationManager validates agent availability at execution not init; exploration ratio hardcoded by cycle range; novelty index is memory-only (lost on restart) |
| `kosmos/knowledge/vector_db.py` | ChromaDB-backed persistent vector storage and cosine-similarity search for scientific papers with SPECTER embeddings and singleton access | `chromadb` (optional, graceful degradation), `kosmos.knowledge.embeddings.get_embedder()` (SPECTER), `kosmos.literature.base_client.PaperMetadata`, `kosmos.config.get_config`, `numpy`, filesystem | `clear()` has no null guard (crashes if ChromaDB unavailable); singleton not thread-safe; SPECTER model triggers ~440MB download on first use; abstract truncated to 1000 chars for search; distance-to-similarity assumes cosine metric |
| `kosmos/core/workflow.py` | Research workflow state machine: finite states (`WorkflowState`), allowed transitions (`ResearchWorkflow`), and research plan data structure (`ResearchPlan`) tracking hypotheses/experiments/results | `pydantic`, `kosmos.config.get_config` (lazy import in `transition_to` for log-gating) | `ResearchPlan.current_state` and `ResearchWorkflow.current_state` can diverge; `CONVERGED` is not terminal (can restart); `PAUSED` resumes to any of 6 states with no memory of prior state; `get_untested_hypotheses()` is O(n*m) with list-based lookup |
| `kosmos/world_model/` (5 modules) | Persistent knowledge graph for research findings using Strategy pattern: Neo4j adapter wrapping `KnowledgeGraph` plus in-memory fallback, `ArtifactStateManager` for JSON artifact layer, Entity/Relationship DTOs | `kosmos.knowledge.graph` (Neo4j/py2neo chain), `kosmos.config.get_config`, `warnings`, `uuid`, `datetime`; `ArtifactStateManager` takes optional `world_model` and `vector_store` | No thread safety on singleton; silent fallback to in-memory (data lost on restart); vector store Layer 3 not implemented (stub); `reset_knowledge_graph()` does not close existing connection (potential leak); entity type bifurcation in indexing |

---

## Per-Module Detailed Behavioral Descriptions

### kosmos/agents/base.py

This module defines the `BaseAgent` class from which all Kosmos agents (ResearchDirector, HypothesisGenerator, ExperimentDesigner, DataAnalyst, LiteratureAnalyzer, StageOrchestrator) inherit, providing lifecycle management, async inter-agent message passing via `AgentMessage` objects, state persistence, and health monitoring. [FACT: base.py:97-111]

**Dual message queue architecture.** Both a legacy sync `message_queue: List` (line 136) and an `_async_message_queue: asyncio.Queue` (line 137) exist side-by-side. `receive_message()` writes to BOTH (line 337-338). The sync list grows unbounded -- there is no eviction or size limit. [FACT: base.py:136-138, 337-338] In long-running agents, this is a memory leak since messages are appended but never removed. [FACT: base.py:136-138]

**Config import inside method body.** `send_message()` and `receive_message()` perform a deferred `from kosmos.config import get_config` inside a try/except (lines 276-287, 341-352). This avoids circular imports but silently swallows config failures -- message logging is best-effort. [FACT: base.py:276-287]

**Router can be sync or async.** `_message_router` is typed as `Union[Callable, Callable[..., Awaitable]]`. `send_message()` calls it and checks `asyncio.iscoroutine(result)` to decide whether to await (line 294). This means router errors are caught per-message but do NOT prevent `send_message()` from returning the constructed message. [FACT: base.py:290-298]

**`start()` is one-shot.** Can only transition from CREATED state (line 161). Calling `start()` on an already-started agent logs a warning and returns silently -- no error raised. [FACT: base.py:161-163] If an agent is in ERROR state, you cannot restart it -- `start()` just warns and returns. [FACT: base.py:161-163]

**`stop()` has no status guard.** Unlike `pause()`/`resume()` which check current status, `stop()` attempts to stop from ANY status, including CREATED or ERROR. [FACT: base.py:177-187]

**Sync wrappers use 30s hardcoded timeout.** `send_message_sync`, `receive_message_sync`, `process_message_sync` all use `future.result(timeout=30)` when a running loop exists. [FACT: base.py:322, 378, 402]

**Registered message handlers are dead code.** `register_message_handler()` stores handlers but `process_message()` does NOT dispatch to them. The registered handlers dict is dead code unless subclasses explicitly use it. [FACT: base.py:406-415]

**Lifecycle hook dead code.** `_on_pause()` and `_on_resume()` hooks exist but are never called by `pause()` and `resume()` methods. The hooks are dead code. [FACT: base.py:513-517]

**Runtime dependencies.** `pydantic.BaseModel` / `pydantic.Field` are used for `AgentMessage`, `AgentState` (dataclass-like validation). [FACT] `asyncio` is used for Queue and event loop for message passing. [FACT] `kosmos.config.get_config()` is a deferred import at runtime for message logging config (not a hard dependency; fails silently). [FACT] `kosmos.agents.registry` sets the message router at registration time. [FACT]

**Blast radius.** Every agent in the system inherits from `BaseAgent`. Changing the `__init__` signature, message protocol, or lifecycle states ripples to at least 6 agent subclasses. [PATTERN: 6 subclasses found: ResearchDirector, HypothesisGenerator, ExperimentDesigner, DataAnalyst, LiteratureAnalyzer, StageOrchestrator] `AgentMessage` is the wire format for all inter-agent communication. Changing its fields breaks serialization and any code that reads `.from_agent`, `.to_agent`, `.content`, `.correlation_id`. [FACT] The `AgentRegistry` (kosmos/agents/registry.py:94) calls `agent.set_message_router()` on every registered agent -- changing that method signature breaks the registry. [FACT: registry.py:94] `AgentStatus` enum values are used as string comparisons in monitoring/logging. Adding/removing states can break health check logic. [FACT]

**Public API details:**

`AgentMessage(BaseModel)`:
- `to_dict()`: Serializes message to a plain dict with ISO timestamp string. No preconditions. No side effects. No error behavior (cannot fail on valid instance). [FACT: base.py:69-80]
- `to_json()`: Serializes to JSON string via `json.dumps(self.to_dict())`. Precondition: content must be JSON-serializable. Raises `TypeError` if content contains non-serializable values. [FACT: base.py:82-84]

`BaseAgent`:
- `__init__(agent_id, agent_type, config)`: Initializes agent with auto-generated UUID if no agent_id, class name if no agent_type. Creates both sync and async message queues, zeroes statistics. Side effect: logs creation at INFO. [FACT: base.py:113-153]
- `start()`: Transitions from CREATED -> STARTING -> RUNNING. Calls `_on_start()` hook. Precondition: status must be CREATED. Side effects: mutates `self.status`, logs. Error: sets status to ERROR and re-raises if `_on_start()` throws. [FACT: base.py:159-175]
- `stop()`: Transitions to STOPPED. Calls `_on_stop()` hook. No status precondition. Side effects: mutates `self.status`, logs. Error: re-raises if `_on_stop()` throws. [FACT: base.py:177-187]
- `pause()`: Transitions RUNNING -> PAUSED. Precondition: status must be RUNNING (otherwise warns and returns). No error raised on wrong state. [FACT: base.py:189-195]
- `resume()`: Transitions PAUSED -> RUNNING. Precondition: status must be PAUSED (otherwise warns and returns). [FACT: base.py:197-205]
- `is_running()`: Returns True only if status is RUNNING. Pure query, no side effects. [FACT: base.py:207-209]
- `is_healthy()`: Returns True if status is RUNNING, IDLE, or WORKING. Subclasses can override. [FACT: base.py:211-217]
- `get_status()`: Returns dict with agent metadata, health, statistics, queue length. Pure query. Uses `len(self.message_queue)` (the sync queue only). [FACT: base.py:219-240]
- `send_message(to_agent, content, message_type, correlation_id)` [async]: Constructs `AgentMessage`, increments `messages_sent`, optionally logs via config, routes via `_message_router` if set. Returns the constructed message even if routing fails. Side effects: counter increment, logging, router invocation. Error: routing errors are caught and logged, not raised. [FACT: base.py:246-300]
- `send_message_sync(...)`: Sync wrapper. Uses `run_coroutine_threadsafe` if loop exists (30s timeout), otherwise `asyncio.run`. Can raise `TimeoutError` if the 30s timeout is hit. [FACT: base.py:302-327]
- `receive_message(message)` [async]: Increments counter, appends to both queues, calls `process_message()`. If processing fails and message was a REQUEST, sends an ERROR response back. Side effects: mutates both queues, counters, triggers processing. [FACT: base.py:329-367]
- `receive_message_sync(message)`: Sync wrapper with same 30s timeout pattern. [FACT: base.py:369-380]
- `process_message(message)` [async]: Default implementation logs a warning. Subclasses must override. [FACT: base.py:382-391]
- `register_message_handler(message_type, handler)`: Stores handler callable in `self.message_handlers` dict. Note: these handlers are NOT automatically called by `process_message()` -- subclasses must dispatch to them. [FACT: base.py:406-415]
- `set_message_router(router)`: Sets the delivery callback for `send_message()`. Accepts sync or async callable. [FACT: base.py:417-433]
- `get_state()`: Returns `AgentState` pydantic model. Side effect: updates `self.updated_at` to current time. [FACT: base.py:439-454]
- `restore_state(state)`: Overwrites agent_id, agent_type, status, state_data, timestamps from saved state. Side effect: mutates all identity/state fields. [FACT: base.py:456-470]
- `save_state_data(key, value)`: Stores key-value in `self.state_data` dict. Side effect: updates `self.updated_at`. [FACT: base.py:472-475]
- `get_state_data(key, default)`: Returns value from state_data or default. Pure query. [FACT: base.py:477-479]
- `execute(task)`: Raises `NotImplementedError`. Subclasses must override. [FACT: base.py:485-497]

---

### kosmos/core/providers/anthropic.py

Implements the Anthropic (Claude) LLM provider with sync/async generation, streaming, structured JSON output, response caching, auto model selection (Haiku/Sonnet), and cost tracking -- supporting both real API keys and a "CLI mode" where an all-9s key routes requests through Claude Code. [FACT: anthropic.py:1-5]

**CLI mode detection is string-based.** The provider checks `self.api_key.replace('9', '') == ''` to detect CLI mode. Any key consisting entirely of the digit 9 (any length) triggers CLI mode, which disables cost calculation. [FACT: anthropic.py:110] Even a single-character key of `"9"` triggers CLI mode. There is no minimum length check. [FACT: anthropic.py:110]

**Cache key includes all generation parameters.** The cache uses a composite key of prompt, model, system prompt, max_tokens, temperature, and stop_sequences. Changing ANY of these parameters causes a cache miss. [FACT: anthropic.py:213-218]

**Cache hits bypass usage tracking.** When a cache hit occurs, the returned `UsageStats` contains metadata from the original cached request (if stored), but `_update_usage_stats` is NOT called. This means `self.total_input_tokens` and `self.total_cost_usd` do not reflect cached responses. [FACT: anthropic.py:228-249, compare with line 307] The `get_usage_stats` method works around this by computing `total_requests_with_cache = self.request_count + self.cache_hits`. [FACT: anthropic.py:228-249]

**Auto model selection is disabled by default AND disabled in CLI mode.** Even if `enable_auto_model_selection=True`, CLI mode (`is_cli_mode=True`) skips auto-selection. [FACT: anthropic.py:187] Auto-model-selection is silently disabled in CLI mode, even if the config requests it. There is no warning logged for this. [FACT: anthropic.py:187]

**Auto-selection uses a lazy import.** `from kosmos.core.llm import ModelComplexity` is imported inside the generate method, not at module level. This is a circular import avoidance pattern. [FACT: anthropic.py:189]

**`generate_structured` instructs JSON via system prompt appendage.** It appends `\n\nYou must respond with valid JSON matching this schema:\n{schema}` to the system prompt. If the system prompt is None, the instruction starts with just the newlines. [FACT: anthropic.py:530] If the system prompt contains its own JSON formatting instructions, these will conflict. [FACT: anthropic.py:530]

**JSON parse errors are marked non-recoverable.** `generate_structured` catches `JSONParseError` and wraps it in `ProviderAPIError(recoverable=False)`. This prevents DelegationManager's retry logic from retrying (since retrying the same prompt typically produces the same malformed JSON). [FACT: anthropic.py:548-556]

**Streaming counts tokens by text chunks, not actual tokens.** In `generate_stream`, `total_tokens` is incremented by 1 per text chunk yielded, NOT by actual token count. The number of chunks does not equal the number of tokens. [FACT: anthropic.py:731-732] The `completion_tokens` field in the emitted `LLM_CALL_COMPLETED` event is therefore wrong. [FACT: anthropic.py:731-732]

**Async client is lazily initialized.** `self._async_client` is created on first access via the `async_client` property. It uses the same API key and base_url as the sync client. [FACT: anthropic.py:344-359]

**`generate_with_messages` does NOT use caching.** Unlike `generate`, the multi-turn method skips the cache entirely. [FACT: anthropic.py:432-500]

**`generate_with_messages` does NOT support model override.** It always uses `self.model`, unlike `generate` which accepts `model_override` via kwargs. [FACT: anthropic.py:467]

**`generate_async` does not call `_update_usage_stats`**, so async calls don't contribute to the provider's running totals. This is inconsistent with the sync `generate` method. [FACT: anthropic.py:400-430]

**Backward compatibility alias exists.** `ClaudeClient = AnthropicProvider` at module level allows old code to use the previous class name. [FACT: anthropic.py:881]

**Runtime dependencies:** `anthropic` package (hard dependency, raises `ImportError` if missing) [FACT: anthropic.py:13-16]. `kosmos.core.providers.base` -- `LLMProvider`, `Message`, `UsageStats`, `LLMResponse`, `ProviderAPIError` [FACT: anthropic.py:20-26]. `kosmos.core.utils.json_parser` -- `parse_json_response`, `JSONParseError` (for structured output) [FACT: anthropic.py:27]. `kosmos.core.claude_cache` -- `get_claude_cache`, `ClaudeCache` (for caching) [FACT: anthropic.py:28]. `kosmos.config` -- `_DEFAULT_CLAUDE_SONNET_MODEL`, `_DEFAULT_CLAUDE_HAIKU_MODEL`, `get_config().logging.log_llm_calls` [FACT: anthropic.py:33-34]. `kosmos.core.pricing` -- `get_model_cost`, `MODEL_PRICING`, `_FAMILY_PRICING` [FACT: anthropic.py:35]. `kosmos.core.llm.ModelComplexity` -- lazy import for auto-selection [FACT: anthropic.py:189]. `kosmos.core.events` + `kosmos.core.event_bus` -- lazy imports for streaming event emission [FACT: anthropic.py:700-703]. `ANTHROPIC_API_KEY` env var -- fallback if not in config [FACT: anthropic.py:88]. `CLAUDE_BASE_URL` env var -- optional custom endpoint [FACT: anthropic.py:107].

**Blast radius.** All LLM-dependent agents: Every agent that calls `provider.generate()`, `generate_structured()`, or `generate_with_messages()` goes through this class (or its OpenAI/DeepSeek siblings). Changing return types, error behavior, or caching logic affects the entire system. [FACT] Cost tracking pipeline: `_calculate_cost` uses `kosmos.core.pricing.get_model_cost`. Changing the CLI mode detection or pricing call path affects cost reports across the system. [FACT] Cache layer: Uses `kosmos.core.claude_cache.ClaudeCache` (backed by `HybridCache`). Changes to cache key construction affect hit rates across all agents. [FACT] Event bus integration: Streaming methods emit `LLMEvent`s to the event bus (`kosmos.core.events`, `kosmos.core.event_bus`). Breaking this affects real-time monitoring. [FACT] `LLMResponse` string compatibility: The `LLMResponse` base class implements `__str__`, `strip`, `lower`, etc. Code that treats the response as a string will break if the return type changes. [FACT]

**Public API details:**

`AnthropicProvider(LLMProvider)`:
- `__init__(config: Dict)`: Initializes sync Anthropic client, configures caching, sets up model selection. Preconditions: `config['api_key']` or `ANTHROPIC_API_KEY` env var must be set. `anthropic` package must be installed. Side effects: Creates `Anthropic` client. Initializes `ClaudeCache` if caching enabled. Error behavior: Raises `ImportError` if `anthropic` not installed. Raises `ValueError` if no API key. Raises `ProviderAPIError` if client init fails. [FACT]
- `generate(prompt, system, max_tokens=4096, temperature=0.7, stop_sequences, **kwargs) -> LLMResponse`: Generates text from Claude with caching, optional auto-model-selection, cost tracking, and optional LLM call logging. Side effects: Updates `self.total_input_tokens`, `self.total_output_tokens`, `self.total_cost_usd`, `self.request_count`. Writes to cache. Error behavior: All exceptions wrapped in `ProviderAPIError`. kwargs: `bypass_cache` (bool), `model_override` (str). [FACT]
- `generate_async(prompt, system, max_tokens, temperature, stop_sequences, **kwargs) -> LLMResponse` (async): True async generation using `AsyncAnthropic`. Does NOT use caching. Does NOT update usage stats via `_update_usage_stats`. Error behavior: Raises `ProviderAPIError`. Raises `ImportError` if `AsyncAnthropic` unavailable. [FACT]
- `generate_with_messages(messages, max_tokens, temperature, **kwargs) -> LLMResponse`: Multi-turn conversation. System messages are extracted and passed separately to the Anthropic API. No caching. Side effects: Updates usage stats. Error behavior: Wraps in `ProviderAPIError`. [FACT]
- `generate_structured(prompt, schema, system, max_tokens, temperature, **kwargs) -> Dict`: Generates JSON output by appending schema instructions to system prompt, then parses with `parse_json_response`. JSON parse failures raise `ProviderAPIError(recoverable=False)`. Other errors raise `ProviderAPIError(recoverable=True)`. [FACT]
- `generate_stream(prompt, system, max_tokens, temperature, stop_sequences, **kwargs) -> Iterator[str]`: Yields text chunks as they arrive. Emits LLM events to the event bus. Error behavior: Raises `ProviderAPIError`. Emits `LLM_CALL_FAILED` event on failure. [FACT]
- `generate_stream_async(prompt, system, max_tokens, temperature, stop_sequences, **kwargs) -> AsyncIterator[str]` (async): Async version of streaming. Uses `AsyncAnthropic`. Publishes async events to `event_bus`. [FACT]
- `get_model_info() -> Dict`: Returns model name, max tokens, mode (cli/api), and pricing for API mode. No side effects. [FACT]
- `get_usage_stats() -> Dict`: Returns usage statistics including cache hit rate, mode, and optional model selection breakdown. No side effects. [FACT]

Alias: `ClaudeClient = AnthropicProvider` -- Backward compatibility alias. [FACT: anthropic.py:881]

---

### kosmos/literature/base_client.py

Defines the abstract base class (`BaseLiteratureClient`) and unified data types (`PaperMetadata`, `Author`, `PaperSource`) for all literature API integrations. Every literature client (arXiv, Semantic Scholar, PubMed) inherits from `BaseLiteratureClient` and returns `PaperMetadata` objects. This is the type contract layer for the entire literature subsystem. [FACT]

**`PaperMetadata` is a `@dataclass`, not a Pydantic model.** Unlike the hypothesis and experiment models, `PaperMetadata` uses stdlib `dataclasses.dataclass` (line 36). This means no automatic validation, no field constraints, and no `.model_dump()`. It relies on `__post_init__` for default mutable fields (line 80-87). [FACT: base_client.py:36, 80]

**`authors` field defaults to `None`, not `[]`.** The dataclass field `authors: List[Author] = None` (line 53) uses `None` as default and patches it to `[]` in `__post_init__` (line 84). This is a deliberate workaround for the Python dataclass mutable-default restriction. Same for `fields` and `keywords`. [FACT: lines 53, 71, 72, 84-87]

**`_normalize_paper_metadata` raises `NotImplementedError`, not from ABC.** The method is NOT marked `@abstractmethod` (line 255-268). It's a concrete method that raises `NotImplementedError`. This means subclasses can instantiate without implementing it, and the error only surfaces at runtime when the method is called. [FACT: base_client.py:255 -- no @abstractmethod decorator]

**`_validate_query` warns but returns `True` for too-long queries.** When `len(query) > 1000`, it logs a warning saying "truncating to 1000" but does NOT actually truncate -- it just returns `True` (line 249-250). The caller gets no truncation. [FACT: base_client.py:248-250]

**`raw_data` field stores entire API responses.** `PaperMetadata.raw_data` (line 78) holds the complete API response dict for debugging. This is excluded from `to_dict()` serialization [FACT: line 99-122 -- `raw_data` not in `to_dict()` output], so it only lives in memory. Can be large for verbose APIs. [FACT: base_client.py:78, 99-122]

**No import side effects.** The module-level `logger = logging.getLogger(__name__)` (line 14) is standard and harmless. No ContextVars, no config loading, no file I/O at import time. [FACT]

**`_handle_api_error` swallows exceptions.** It logs but does not re-raise. [FACT: base_client.py:229-233] Comment says "Could add retry logic, circuit breaker, etc. here" [FACT: line 233]. Callers that need error propagation must handle it themselves. [FACT: base_client.py:229-233]

**`PaperMetadata` has no validation.** Being a plain dataclass, it accepts any values for any field. A `citation_count` of -999 or a `title` of `None` will not raise errors. [FACT]

**Blast radius.** With 35 importers across literature clients, agents, knowledge, tests, and world_model: Renaming `PaperMetadata` or its fields breaks every literature client, every agent that processes papers, knowledge graph ingestion, and the world model. This is the universal paper representation. [FACT] Changing `PaperSource` enum values breaks persisted data and any code that checks `paper.source == PaperSource.ARXIV` etc. [FACT] Changing `BaseLiteratureClient.search()` signature breaks all 4 concrete implementations (ArxivClient, ArxivHTTPClient, SemanticScholarClient, PubMedClient). [FACT: grep found 4 subclasses] Changing `to_dict()` output format breaks database storage layer and any serialization consumers. [FACT] Adding required fields to `PaperMetadata` breaks every place that constructs `PaperMetadata(id=..., source=...)` without the new field. [FACT] Changing `Author` dataclass affects `PaperMetadata.author_names` property and `to_dict()` serialization. [FACT]

**Runtime dependencies.** `abc` (ABC, abstractmethod) -- stdlib. `dataclasses` -- stdlib. `logging` -- stdlib. `typing`, `datetime`, `enum` -- stdlib. No external dependencies. No imports from other Kosmos modules. This module is a leaf dependency -- it imports nothing from the Kosmos package. [FACT: base_client.py:1-13 -- only stdlib imports]

**Public API details:**

`PaperSource(str, Enum)` (line 17): Five-value enum: `ARXIV`, `SEMANTIC_SCHOLAR`, `PUBMED`, `UNKNOWN`, `MANUAL`. Identifies where a paper came from. [FACT]

`@dataclass Author` (line 27): Represents an author with name (required), optional affiliation, email, and source-specific author_id. No validation. [FACT]

`@dataclass PaperMetadata` (line 36): Unified paper representation across all literature sources. Contains identifiers (id, doi, arxiv_id, pubmed_id), core metadata (title, abstract, authors), publication info, links, citation counts, fields/keywords, optional full text, and raw API data. `id` and `source` are required positional-style fields (no defaults). `__post_init__` initializes `None` mutable fields to empty lists. [FACT: lines 84-87] No validation. Invalid data is silently accepted. [FACT]
- `primary_identifier` (property, line 89): Returns the first non-None identifier in priority order: DOI > arXiv ID > PubMed ID > source ID. Returns `self.id` as final fallback (always set). [FACT]
- `author_names` (property, line 95): Returns list of author name strings. Returns empty list if no authors. [FACT]
- `to_dict()` (line 99): Serializes to a dict suitable for database storage. Excludes `raw_data`. Converts `source` enum to string, `publication_date` to ISO string, authors to name/affiliation dicts. [FACT]

`BaseLiteratureClient(ABC)` (line 125): Abstract base class that all literature API clients must inherit from. Provides common initialization (api_key, cache_enabled, per-class logger) and helper methods. `api_key` is optional. Creates a child logger `__name__.ClassName` (line 143). [FACT]
- `__init__(api_key, cache_enabled)` (line 133): Stores api_key and cache_enabled flag. Creates class-specific logger. No side effects beyond logger creation. [FACT]
- `search()` (abstract, line 146): Must return `List[PaperMetadata]` matching query with optional field/year filters. Raises `TypeError` if called on the ABC directly. [FACT]
- `get_paper_by_id()` (abstract, line 172): Returns single `PaperMetadata` or `None`. [FACT]
- `get_paper_references()` (abstract, line 184): Returns papers cited by the given paper. [FACT]
- `get_paper_citations()` (abstract, line 198): Returns papers that cite the given paper. [FACT]
- `get_source_name()` (line 212): Returns class name with "Client" suffix removed. E.g., `ArxivClient` -> `"Arxiv"`. [FACT]
- `_handle_api_error(error, operation)` (line 221): Logs API errors with source name, operation description, and full traceback. Emits ERROR-level log with `exc_info=True`. [FACT: line 230-232] Does not re-raise. Swallows the error after logging. [FACT: line 233]
- `_validate_query(query)` (line 235): Returns `False` for empty/whitespace queries, `True` otherwise. Warns on queries > 1000 chars but does NOT truncate. [FACT: lines 248-250]
- `_normalize_paper_metadata(raw_data)` (line 255): Raises `NotImplementedError`. NOT marked `@abstractmethod`, so subclasses can omit it without ABC enforcement. [FACT: line 268]

---

### kosmos/execution/code_generator.py

Generates executable Python code from `ExperimentProtocol` objects using a hybrid approach: first attempting template matching against 5 built-in experiment type templates (t-test, correlation, log-log scaling, ML, generic computational), falling back to LLM-based generation via Claude, with a minimal hardcoded template as the last resort. [FACT: code_generator.py:1-9, 786-793]

**Template priority order matters.** Templates are matched in registration order (lines 787-793). `GenericComputationalCodeTemplate` is registered LAST and matches both `COMPUTATIONAL` and `DATA_ANALYSIS` types (line 559-564). If a more specific template (t-test, correlation) does not match, the generic catches everything. A protocol that is `DATA_ANALYSIS` type with "scaling" in the name would match `LogLogScalingCodeTemplate` first (checked before generic), but a `DATA_ANALYSIS` protocol with no distinguishing keywords falls through to generic. [FACT: code_generator.py:787-793, 559-564] Template matching is order-dependent with no priority scoring. The first match wins. If `GenericComputationalCodeTemplate` were registered before `TTestComparisonCodeTemplate`, t-test protocols would get generic analysis instead. [FACT: code_generator.py:787-793]

**All templates generate synthetic data fallback.** Every template checks `if 'data_path' in dir() and data_path:` to try loading real data, then falls through to synthetic data generation with `np.random.seed()` (Issue #51 fix). This means experiments can run without any input data files. [FACT: code_generator.py:112-130, 243-259, 381-397, 474-488, 590-608]

**Generated code uses `dir()` for variable detection.** Templates check `if 'data_path' in dir()` and `if 'figure_path' in dir()` rather than using try/except or checking locals/globals. This pattern works because `dir()` in exec'd code returns local scope names. [FACT: code_generator.py:112, 169]

**LLM client initialization has double fallback.** `ExperimentCodeGenerator.__init__` tries `ClaudeClient()` first, catches failure, then tries `LiteLLMProvider` as fallback. If both fail, LLM generation is silently disabled (`self.use_llm = False`). [FACT: code_generator.py:762-778]

**Template code is NOT validated for safety.** The `generate()` method only calls `_validate_syntax()` (AST parse check) on the output (line 831). It does NOT run `CodeValidator` -- that happens later in the executor. Templates can contain imports of `kosmos.execution.data_analysis` and `kosmos.analysis.visualization` which are Kosmos internal modules, not dangerous. [FACT: code_generator.py:831, 981-989]

**`_generate_basic_template` hardcodes `data_path`.** The fallback template at line 964 uses `pd.read_csv(data_path)` without the synthetic data fallback. If `data_path` is undefined, this will raise `NameError`. This is the ONLY template without synthetic data support. [FACT: code_generator.py:954-977]

**Protocol random_seed used for reproducibility.** Templates extract `getattr(protocol, 'random_seed', 42) or 42` (e.g., line 89). The `or 42` guard means a `random_seed=0` would be overridden to 42 (since 0 is falsy). [FACT: code_generator.py:89, 231, 368, 572]

**`_validate_syntax` raises ValueError, not SyntaxError.** On syntax failure, it wraps the SyntaxError in a ValueError (line 989). This changes the exception type for callers. [FACT: code_generator.py:988-989]

**Effect size from protocol influences synthetic data.** The t-test template reads `expected_effect_size` from the protocol's first statistical test (lines 94-97) and uses it as the mean shift in synthetic data generation. This means synthetic experiments can simulate null (effect_size=0) or non-null hypotheses. [FACT: code_generator.py:93-97, 124]

**`_extract_code_from_response` has a weak heuristic.** If the LLM response contains no code fences, it checks for "import", "def ", or "=" to decide if it's code. A natural language response containing "=" would be treated as code. [FACT: code_generator.py:907-924]

**Blast radius.** `ExperimentCodeGenerator.generate()` is called by `research_director.py:1528` to produce code for every experiment. Changing its output format or template structure affects all experiment execution. [FACT] Generated code must assign to `results` variable -- the executor extracts return values by that name (executor.py:516). Changing the variable name breaks result capture. [FACT] Templates import from `kosmos.execution.data_analysis.DataAnalyzer`, `kosmos.execution.ml_experiments.MLAnalyzer`, and `kosmos.analysis.visualization.PublicationVisualizer`. If those APIs change, template-generated code will fail at runtime. [FACT] `CodeTemplate.matches()` logic determines which template runs. Changing match criteria can silently route experiments to the wrong template. [FACT] The synthetic data patterns in templates are used for testing and demo. Changing seeds or distributions changes expected test outputs. [FACT]

**Runtime dependencies.** `kosmos.models.experiment.ExperimentProtocol`, `ProtocolStep`, `ExperimentType` -- protocol definition models. [FACT] `kosmos.models.hypothesis.Hypothesis` -- imported but not used in visible code. [FACT] `kosmos.core.llm.ClaudeClient` -- primary LLM client for code generation. [FACT] `kosmos.core.prompts.EXPERIMENT_DESIGNER` -- imported but not used in visible code (likely for prompt templates). [FACT] `kosmos.core.providers.litellm_provider.LiteLLMProvider` -- lazy fallback import in __init__. [FACT] `kosmos.config.get_config` -- lazy import for LiteLLM fallback config. [FACT] At runtime, generated code imports: `pandas`, `numpy`, `scipy`, `sklearn`, `kosmos.execution.data_analysis`, `kosmos.execution.ml_experiments`, `kosmos.analysis.visualization`. [FACT]

**Public API details:**

`CodeTemplate`:
- `__init__(name, experiment_type)`: Base template with name and type. [FACT: code_generator.py:27-37]
- `matches(protocol)`: Default: checks `protocol.experiment_type == self.experiment_type`. Subclasses override for more specific matching. [FACT: code_generator.py:39-41]
- `generate(protocol)`: Raises `NotImplementedError`. Subclasses must override. [FACT: code_generator.py:43-45]

`TTestComparisonCodeTemplate`:
- `matches(protocol)`: Returns True for `DATA_ANALYSIS` type with t-test in statistical_tests. [FACT: code_generator.py:58-69]
- `generate(protocol)`: Produces t-test code with synthetic data fallback, Shapiro normality check, Levene equal variance check, DataAnalyzer.ttest_comparison() call, and publication figure generation. [FACT: code_generator.py:71-190]

`CorrelationAnalysisCodeTemplate`:
- `matches(protocol)`: Matches `DATA_ANALYSIS` with correlation/regression in tests or "correlation" in name. [FACT: code_generator.py:203-214]
- `generate(protocol)`: Produces Pearson+Spearman correlation code, picks "best" method by p-value, includes scatter plot with regression. [FACT: code_generator.py:216-340]

`LogLogScalingCodeTemplate`:
- `matches(protocol)`: Keyword match on "scaling", "power law", "log-log" in protocol name/description. [FACT: code_generator.py:353-360]
- `generate(protocol)`: Generates power-law fitting with log-log plot. Uses `DataCleaner.filter_positive()` to remove non-positive values before log transform. [FACT: code_generator.py:362-441]

`MLExperimentCodeTemplate`:
- `matches(protocol)`: Keyword match on ML terms ("classification", "random forest", "svm", etc.) in name/description. [FACT: code_generator.py:450-458]
- `generate(protocol)`: Produces sklearn classification pipeline with train/test split, cross-validation, and MLAnalyzer. [FACT: code_generator.py:460-544]

`GenericComputationalCodeTemplate`:
- `matches(protocol)`: Matches COMPUTATIONAL or DATA_ANALYSIS (catch-all). [FACT: code_generator.py:559-564]
- `generate(protocol)`: Generates descriptive stats, correlation, nonlinear curve fitting (exponential decay), linear regression, and scatter plot. [FACT: code_generator.py:566-728]

`ExperimentCodeGenerator`:
- `__init__(use_templates, use_llm, llm_enhance_templates, llm_client)`: Initializes with template registration and LLM client (with double fallback). Side effects: logs template count, warns on LLM client failures. [FACT: code_generator.py:741-783]
- `generate(protocol)`: Hybrid code generation. Step 1: template match. Step 2: LLM generation. Step 3: basic fallback. Always validates syntax. Returns code string. Raises `ValueError` on syntax error. [FACT: code_generator.py:797-833]
- `_generate_with_llm(protocol)`: Creates detailed prompt from protocol steps/variables/tests, calls `llm_client.generate()`, extracts code from response. Returns None on failure. [FACT: code_generator.py:842-856]
- `_enhance_with_llm(template_code, protocol)`: Optional LLM enhancement of template output. Falls back to original on failure. [FACT: code_generator.py:926-952]
- `_validate_syntax(code)` [static]: AST parse check. Raises `ValueError` (not `SyntaxError`) on failure. [FACT: code_generator.py:981-989]
- `save_code(code, file_path)`: Writes code string to file. Side effect: filesystem write, logs. [FACT: code_generator.py:991-995]

---

### kosmos/safety/code_validator.py

Validates generated Python code for safety (dangerous imports, dangerous function calls, file/network access), security (AST-based detection of reflection calls and dunder attribute access), and ethical research compliance (keyword-based screening against configurable guidelines), producing a `SafetyReport` with violations, warnings, risk assessment, and optional approval request generation. [FACT: code_validator.py:1-9]

**`os` is on the dangerous list but executor's RetryStrategy can reinsert it.** The validator flags `import os` as CRITICAL (line 36), but the RetryStrategy's `COMMON_IMPORTS` dict DOES include `'os': 'import os'` (executor.py:686). This means auto-fix can insert an `import os` that the validator would reject. [FACT: code_validator.py:36, executor.py:686]

**Ethical checks are keyword-based with high false-positive risk.** Keywords like "email", "password", "survey", "harm" in the code OR context description trigger ethical violations (lines 401-418). Scientific code analyzing email metadata, password-strength algorithms, or harm-reduction studies would trigger these. [FACT: code_validator.py:118-119, 395-418] A bioinformatics experiment analyzing "harmful mutations" would trigger the "no_harm" guideline. [FACT: code_validator.py:118-119]

**Pattern checking uses raw string matching, not AST.** `_check_dangerous_patterns()` uses `if pattern in code:` (line 288). This means commented-out code like `# eval(` or strings containing `'eval('` trigger violations. [FACT: code_validator.py:288] `# eval()` or `description = "do not eval("` would trigger a CRITICAL violation. [FACT: code_validator.py:288]

**`open(` write mode detection is fragile.** The validator checks for `"'w'"`, `"'a'"`, `"'x'"`, `"mode='w'"`, `'mode="w"'` as substrings (lines 296-297). It misses `mode='a'`, `mode='x'`, `'wb'`, `'ab'`, or variable-based modes like `open(f, mode)`. [FACT: code_validator.py:296-297] Code using `open(f, 'wb')` would pass the write check when `allow_file_read=True`. [FACT: code_validator.py:296-297]

**AST is parsed up to 3 times.** `_check_syntax()` parses with `ast.parse()` (line 237), `_check_dangerous_imports()` parses again (line 252), and `_check_ast_calls()` parses a third time (line 332). The syntax check and AST call check each parse independently. If syntax check fails, the import check falls back to string matching. [FACT: code_validator.py:237, 252, 332] A syntax error in `_check_syntax` does not prevent `_check_dangerous_imports` from also attempting to parse (it has its own try/except with string fallback). [FACT: code_validator.py:237, 252, 332]

**`getattr` is flagged as dangerous.** The AST call checker flags `getattr()` as CRITICAL (lines 338, 353-361). This is a commonly-used Python built-in, so any generated code using `getattr(obj, 'attr', default)` will fail validation. [FACT: code_validator.py:338]

**`requires_approval()` depends on global config.** It reads `config.safety.require_human_approval` from `get_config()` (lines 447-449). If that config flag is True, ALL code requires approval regardless of risk level. [FACT: code_validator.py:447-449]

**Approval request truncates code to 500 chars.** `create_approval_request()` stores only `code[:500]` in the context dict (line 510). Long code is not fully visible in the approval request. [FACT: code_validator.py:510] Dangerous patterns at character 501+ are not visible to the human reviewer. [FACT: code_validator.py:510]

**Ethical guideline `break` after first keyword match.** The inner loop breaks after the first keyword match per guideline (line 417). This means only one violation is reported per guideline even if multiple keywords match. [FACT: code_validator.py:417]

**Blast radius.** `CodeValidator.validate()` is called by `execute_protocol_code()` in executor.py (line 1040) and by `guardrails.py` (line 26). It gates ALL code execution. Making it stricter blocks experiments; making it looser opens security holes. [FACT] `SafetyReport` is the return type used by the execution pipeline to decide pass/fail. Changing report fields or the `passed` logic affects all downstream decision-making. [FACT] `DANGEROUS_MODULES` list determines what imports are blocked. Adding modules (e.g., `pathlib`) would break templates that import them. Removing modules weakens security. [FACT] `DANGEROUS_PATTERNS` list affects what code constructs are blocked. The `open(` entry interacts with the `allow_file_read`/`allow_file_write` flags. [FACT] The ethical guidelines (default or loaded from JSON) affect whether experiments trigger approval requirements. [FACT]

**Runtime dependencies.** `kosmos.models.safety.SafetyReport`, `SafetyViolation`, `ViolationType`, `RiskLevel`, `EthicalGuideline`, `ApprovalRequest`, `ApprovalStatus` -- all Pydantic models from the safety models module. [FACT: code_validator.py:17-19] `kosmos.utils.compat.model_to_dict` -- for serializing the SafetyReport in approval requests. [FACT: code_validator.py:20] `kosmos.config.get_config` -- for reading `safety.require_human_approval` flag. [FACT: code_validator.py:21] `ast` (stdlib) -- for syntax checking and AST-based call analysis. `json` (stdlib) -- for loading ethical guidelines from file. `pathlib.Path` (stdlib) -- for checking ethical guidelines file existence. [FACT]

**Public API details:**

`CodeValidator`:
- `__init__(ethical_guidelines_path, allow_file_read, allow_file_write, allow_network)`: Loads ethical guidelines from JSON file or defaults. Defaults: `allow_file_read=True`, `allow_file_write=False`, `allow_network=False`. Side effect: logs configuration. [FACT: code_validator.py:58-85]
- `validate(code, context)`: Main validation entry point. Runs 6 checks in sequence: syntax, dangerous imports, dangerous patterns, network operations, AST call analysis, ethical guidelines. Returns `SafetyReport`. `passed` is True only if zero violations (warnings are ignored). Side effect: logs summary. [FACT: code_validator.py:159-231]
- `_check_syntax(code)`: Parses with `ast.parse()`. Returns list of violations (0 or 1). Violation severity: HIGH. [FACT: code_validator.py:233-245]
- `_check_dangerous_imports(code)`: AST-based import detection. Falls back to string matching on SyntaxError. Severity: CRITICAL for all dangerous imports. Checks both `import X` and `from X import ...` forms, including submodule imports like `os.path`. [FACT: code_validator.py:247-281]
- `_check_dangerous_patterns(code)`: String-based pattern detection. Returns tuple of (violations, warnings). Special handling for `open(`: allowed if `allow_file_write=True` (warning only) or `allow_file_read=True` (checks for write-mode strings). All other patterns are CRITICAL violations. [FACT: code_validator.py:283-320]
- `_check_ast_calls(code)`: AST walk detecting `getattr()`/`setattr()`/`delattr()` calls and `__dict__`/`__class__`/`__builtins__`/`__subclasses__` attribute access. Returns on SyntaxError (defers to `_check_syntax`). Severity: CRITICAL for all detections. [FACT: code_validator.py:322-375]
- `_check_network_operations(code)`: String-based keyword search (case-insensitive). Returns warnings only (not violations). Only checks if `allow_network=False`. [FACT: code_validator.py:377-384]
- `_check_ethical_guidelines(code, context)`: Keyword matching against code text plus context description/hypothesis. Only reports violations for `required=True` guidelines. Severity comes from guideline's `severity_if_violated`. [FACT: code_validator.py:386-418]
- `_assess_risk_level(violations)`: Returns the highest severity found among violations. Returns `RiskLevel.LOW` if no violations. [FACT: code_validator.py:420-434]
- `requires_approval(report)`: Returns True if: config mandates approval, OR risk is HIGH/CRITICAL, OR critical violations exist, OR any ethical violations exist. [FACT: code_validator.py:436-465]
- `create_approval_request(code, report, context)`: Creates `ApprovalRequest` Pydantic model with truncated code (500 chars), violation list, and risk level. [FACT: code_validator.py:467-515]

---

### kosmos/core/convergence.py

Decides when the autonomous research loop should stop iterating by evaluating mandatory stopping criteria (iteration limit, hypothesis exhaustion) and optional scientific criteria (novelty decline, diminishing returns), then generates a comprehensive convergence report summarizing research outcomes. [FACT: convergence.py:1-7]

**Iteration limit is checked LAST, not first.** The `check_convergence` method deliberately checks hard-stop mandatory criteria (like `no_testable_hypotheses`) first, then optional scientific criteria, and finally `iteration_limit`. This means if both `novelty_decline` and `iteration_limit` fire on the same call, `novelty_decline` is reported as the reason -- a deliberate choice so the stopping reason reflects scientific convergence rather than an arbitrary limit. [FACT: convergence.py:246-268]

**Iteration limit can be DEFERRED.** When `iteration_count >= max_iterations` but fewer than `min_experiments_before_convergence` experiments have completed AND testable work remains (untested hypotheses or queued experiments), the detector returns `should_stop=False` despite being at the limit. This prevents premature stopping when hypotheses were generated but barely tested. The default `min_experiments_before_convergence` is 2. [FACT: convergence.py:332-356, line 206] If no experiments ever complete, convergence is deferred indefinitely until other criteria or external safety caps intervene. [FACT: convergence.py:339]

**Novelty trend is stateful and grows unboundedly.** Each call to `check_convergence` appends the current novelty score to `self.metrics.novelty_trend` (line 562). This list is never truncated. Over many iterations, this accumulates. [FACT: convergence.py:562]

**Novelty decline uses OR logic.** A task is considered declining if EITHER all recent values are below the threshold OR the values form a strictly monotonically decreasing sequence. These are independent checks. [FACT: convergence.py:421-427]

**The "continue" decision uses `USER_REQUESTED` as a placeholder reason.** When no criteria are met, the returned `StoppingDecision` has `reason=StoppingReason.USER_REQUESTED` -- not a meaningful reason, just a placeholder since the enum has no "none" variant. [FACT: convergence.py:271] Code that filters on `reason == USER_REQUESTED` will get false positives from normal "continue" decisions. [FACT: convergence.py:271]

**`novelty_decline_window` is dynamically clamped.** It is set to `min(5, max(2, max_iters - 1))`, meaning for the default `max_iterations=10` it is 5, but for `max_iterations=2` it would be 1 (clamped to 2). [FACT: convergence.py:200-203]

**The novelty decline check uses `>=` for "declining".** `recent[i] >= recent[i+1]` means a flat novelty score is also considered "declining." A constant novelty score triggers a stop. [FACT: convergence.py:424]

**Blast radius.** ResearchDirector loop termination: The `check_convergence` return value directly controls whether the autonomous research loop continues. Changing the logic or defaults changes how many iterations actually run. [FACT] `ConvergenceReport` downstream: The `generate_convergence_report` method produces a `ConvergenceReport` consumed by reporting/output layers and potentially serialized. Changing the model fields breaks serializers. [FACT] Metrics dict consumers: `get_metrics_dict()` (line 710) uses `model_to_dict` from `kosmos.utils.compat`. Any code deserializing those metrics depends on the field names. [FACT] Cost tracking: The `_update_metrics` method integrates `total_cost` from the LLM provider (line 578-583). Changing cost logic affects convergence decisions via `check_diminishing_returns`. [FACT]

**Runtime dependencies.** `kosmos.core.workflow.ResearchPlan` -- accessed for `iteration_count`, `max_iterations`, `hypothesis_pool`, `tested_hypotheses`, `supported_hypotheses`, `rejected_hypotheses`, `completed_experiments`, `experiment_queue`, `get_untested_hypotheses()`, `get_testability_rate()`, `has_converged`, `research_question`. [FACT: convergence.py:16] `kosmos.models.hypothesis.Hypothesis` -- accessed for `.novelty_score`, `.id`, `.statement` attributes. [FACT: convergence.py:17] `kosmos.models.result.ExperimentResult` -- accessed for `.supports_hypothesis` attribute. [FACT: convergence.py:18] `kosmos.utils.compat.model_to_dict` -- Pydantic compatibility helper for serialization. [FACT: convergence.py:19] `numpy` -- imported [FACT: convergence.py:14]. `pydantic.BaseModel` -- all data classes inherit from it. [FACT: convergence.py:11]

**Public API details:**

`ConvergenceDetector`:
- `__init__(mandatory_criteria, optional_criteria, config)`: Configures which stopping criteria to evaluate and their thresholds. No exceptions; all values have defaults. Creates internal `ConvergenceMetrics` instance. [FACT]
- `check_convergence(research_plan, hypotheses, results, total_cost=None) -> StoppingDecision`: Evaluates all configured stopping criteria in priority order (mandatory hard-stops, then optional scientific criteria, then iteration_limit) and returns the first that fires, or a "continue" decision. Side effects: Mutates `self.metrics` (updates all fields, appends to `novelty_trend`). Unknown criteria names log a warning and return `should_stop=False` with `confidence=0.0`. [FACT: convergence.py:300-308]
- `check_iteration_limit(research_plan) -> StoppingDecision`: Returns `should_stop=True` if `iteration_count >= max_iterations`, UNLESS fewer than `min_experiments_before_convergence` experiments are completed and testable work remains. [FACT]
- `check_hypothesis_exhaustion(research_plan, hypotheses) -> StoppingDecision`: Stops if there are zero untested hypotheses AND zero queued experiments. [FACT]
- `check_novelty_decline() -> StoppingDecision`: Checks if the last N novelty scores are all below threshold OR monotonically decreasing. Returns `should_stop=False` with `confidence=0.0` if insufficient data points. [FACT]
- `check_diminishing_returns() -> StoppingDecision`: Stops if `cost_per_discovery` exceeds `cost_per_discovery_threshold` (default $1000). Returns `should_stop=False` if no cost data available. [FACT]
- `generate_convergence_report(research_plan, hypotheses, results, stopping_reason) -> ConvergenceReport`: Produces a final report with statistics, supported/rejected hypotheses, summary text, and recommended next steps. Mutates `self.metrics` one final time. [FACT]
- `get_metrics() -> ConvergenceMetrics`: Returns the current metrics object (mutable reference). [FACT]

`ConvergenceReport`:
- `to_markdown() -> str`: Renders the report as a formatted markdown string with statistics, supported hypotheses, and recommendations. [FACT]

---

### kosmos/execution/executor.py

Executes generated Python (and optionally R) code with safety sandboxing, output capture, timeout enforcement, optional profiling, determinism testing, and self-correcting retry logic that can modify failing code using pattern-based fixes or LLM-assisted repair. [FACT: executor.py:1-6]

**Restricted builtins sandbox.** When Docker sandbox is unavailable, the executor replaces `__builtins__` with `SAFE_BUILTINS` (lines 43-83) -- a whitelist of ~80 safe builtins. A custom `_make_restricted_import()` (lines 97-110) limits `import` to a set of ~30 scientific/stdlib modules. This is NOT process isolation -- the code still runs in the same Python process. [FACT: executor.py:43-94, 589-597] The restricted builtins include `hasattr` but NOT `getattr`/`setattr`/`delattr`. However, `type` and `object` ARE included, which can be used to bypass restrictions via `type.__getattribute__`. [FACT: executor.py:594-597]

**Return value extraction by convention.** `_execute_once()` looks for a variable named `results` or `result` in the exec'd code's local namespace (line 516). All code templates MUST assign to `results` for the executor to capture output. [FACT: executor.py:516] If generated code does not assign to `results` or `result`, `return_value` will be `None` even on successful execution. [FACT: executor.py:516]

**Docker sandbox fallback is silent.** If `use_sandbox=True` but Docker is not installed, the executor sets `self.use_sandbox = False` and continues with restricted builtins only (lines 216-220). No error is raised. [FACT: executor.py:216-220]

**Timeout implementation is platform-dependent.** On Unix, uses `signal.SIGALRM` (same-thread, clean). On Windows, uses `ThreadPoolExecutor` with 1 worker (lines 607-630). The thread-based approach on Windows cannot actually kill a stuck computation -- it only stops waiting for it. The thread continues executing. [FACT: executor.py:600-630]

**`execute_with_data()` injects data_path twice.** Prepends `data_path = repr(path)` to the code string AND passes it as a local variable (lines 653-660). This double-injection ensures templates that use either `data_path` as a global or local will find it. [FACT: executor.py:653-660]

**Re-export of CodeValidator.** Line 664 does `from kosmos.safety.code_validator import CodeValidator` at module level. This means importing `CodeValidator` from `executor.py` works, but it's a re-export not a definition. Comment says "F-22: removed duplicate". [FACT: executor.py:663-664]

**RetryStrategy wraps entire code in try/except.** Most fix methods (e.g., `_fix_key_error`, `_fix_type_error`) wrap the ENTIRE original code in a try/except block (lines 869-877). This masks the original error and produces a `results = {'error': ..., 'status': 'failed'}` dict. The experiment appears to "succeed" (no exception) but with a failure result. [FACT: executor.py:869-877] Callers must check `result.return_value` for `{'status': 'failed'}` in addition to `result.success`. [FACT: executor.py:869-877]

**FileNotFoundError is explicitly terminal.** `_fix_file_not_found()` returns `None` (line 906), and `should_retry()` lists FileNotFoundError as non-retryable (line 726). This is an intentional Issue #51 fix -- missing data files should trigger synthetic data generation in templates, not retry loops. [FACT: executor.py:726, 879-906]

**LLM repair only on first 2 attempts.** `modify_code_for_retry()` only tries LLM-based repair when `attempt <= 2` (line 779). Subsequent attempts use pattern-based fixes only. [FACT: executor.py:779]

**`execute_protocol_code()` always validates safety.** The convenience function at line 1017 always runs `CodeValidator.validate()` before execution. The comment "F-21: removed validate_safety bypass" indicates a previous version had a way to skip validation that was deliberately removed. [FACT: executor.py:1039-1048]

**Retry loop calls `time.sleep()` synchronously.** This blocks the calling thread. In async contexts this blocks the event loop. [FACT: executor.py:335]

**Blast radius.** `CodeExecutor` is used by `research_director.py` (line 1529) for all experiment execution. Changing its interface breaks the primary experiment pipeline. [FACT] `ExecutionResult` is the return type consumed by the entire results pipeline. Changing fields breaks result serialization, data analyst agents, and reporting. [FACT] `SAFE_BUILTINS` and `_ALLOWED_MODULES` define the security boundary for unsandboxed execution. Expanding them increases attack surface; restricting them can break experiment code that uses the removed builtins/modules. [FACT] `execute_protocol_code()` is called by `parallel.py:290` for parallel experiment execution. [FACT] The `RetryStrategy.COMMON_IMPORTS` dict (lines 680-697) determines auto-fix capability. Missing entries mean NameError for those imports cannot be auto-fixed. [FACT] Changing `DEFAULT_EXECUTION_TIMEOUT` (300s) affects all unsandboxed executions. [FACT]

**Runtime dependencies.** `kosmos.execution.sandbox.DockerSandbox` -- optional, imported with try/except at module load (lines 24-29). [FACT] `kosmos.execution.r_executor.RExecutor` -- optional, imported with try/except at module load (lines 32-37). [FACT] `kosmos.safety.code_validator.CodeValidator` -- re-exported and used by `execute_protocol_code()` (line 664, 1040). [FACT] `kosmos.utils.compat.model_to_dict` -- for serializing profile results (line 9). [FACT] `kosmos.core.profiling.ExecutionProfiler` -- optional, lazy imported inside `_execute_once()` (line 482). [FACT] `kosmos.safety.reproducibility.ReproducibilityManager` -- optional, lazy imported for determinism testing (line 296). [FACT] `concurrent.futures` -- for Windows timeout fallback. [FACT] `signal` -- for Unix SIGALRM timeout. [FACT]

**Public API details:**

`ExecutionResult`:
- `__init__(...)`: Data container with `success`, `return_value`, `stdout`, `stderr`, `error`, `error_type`, `execution_time`, `profile_result`, `data_source`. [FACT: executor.py:113-136]
- `to_dict()`: Serializes to dict. Includes `profile_data` if available, with silent fallback on serialization failure. [FACT: executor.py:138-159]

`CodeExecutor`:
- `__init__(max_retries, retry_delay, allowed_globals, use_sandbox, sandbox_config, enable_profiling, profiling_mode, test_determinism, execution_timeout)`: Initializes executor with all features. Creates `RetryStrategy`, optionally creates `DockerSandbox` and `RExecutor`. Side effects: logs warnings if sandbox/R not available. Precondition: none (graceful degradation). [FACT: executor.py:174-235]
- `execute(code, local_vars, retry_on_error, llm_client, language)`: Main execution entry point. Auto-detects language (Python/R). For Python: runs `_execute_once()` in a retry loop with code modification on failure. Returns `ExecutionResult`. Side effects: `time.sleep()` between retries, logging, optional determinism check. Error: returns `ExecutionResult(success=False)` rather than raising. [FACT: executor.py:237-376]
- `execute_r(code, capture_results, output_dir)`: Explicit R execution. Returns `ExecutionResult` converted from `RExecutionResult`. Precondition: R executor available. Error: returns failure result if R unavailable. [FACT: executor.py:409-452]
- `is_r_available()`: Checks R availability. Pure query. [FACT: executor.py:454-458]
- `get_r_version()`: Returns R version string or None. Pure query. [FACT: executor.py:460-464]
- `execute_with_data(code, data_path, retry_on_error)`: Wraps `execute()` with data_path injection (both prepended to code and passed as local var). [FACT: executor.py:632-660]

`RetryStrategy`:
- `__init__(max_retries, base_delay)`: Initializes with repair statistics tracking dict. [FACT: executor.py:699-715]
- `should_retry(attempt, error_type)`: Returns False for SyntaxError, FileNotFoundError, DataUnavailableError. Returns False if attempts exceeded. [FACT: executor.py:717-730]
- `get_delay(attempt)`: Exponential backoff: `base_delay * 2^(attempt-1)`. [FACT: executor.py:732-734]
- `record_repair_attempt(error_type, success)`: Tracks per-error-type success/failure counts. Side effect: mutates `self.repair_stats`. [FACT: executor.py:736-749]
- `modify_code_for_retry(original_code, error, error_type, traceback_str, attempt, llm_client)`: Dispatches to error-type-specific fixers. Tries LLM first (attempts 1-2 only), then pattern-based. Returns modified code or None. Handles 11 error types: KeyError, FileNotFoundError, NameError, TypeError, IndexError, AttributeError, ValueError, ZeroDivisionError, ImportError/ModuleNotFoundError, PermissionError, MemoryError. [FACT: executor.py:751-825]

`execute_protocol_code(code, data_path, max_retries, use_sandbox, sandbox_config)`: Convenience function. Always validates safety first via `CodeValidator`. Creates a fresh `CodeExecutor` per call. Returns dict. Precondition: code must pass safety validation. Error: returns `{'success': False, 'error': 'Code validation failed', ...}` if validation fails. [FACT: executor.py:1017-1066]

---

### kosmos/models/experiment.py

Defines the Pydantic data models for experiment design and validation: variables, control groups, protocol steps, resource requirements, statistical test specs, validation checks, full experiment protocols, design requests/responses, and validation reports. This is the data contract for the entire experiment subsystem. It contains several defensive validators specifically designed to handle malformed LLM output. [FACT]

**Imports `ExperimentType` from hypothesis.py, not defined locally.** The key enum `ExperimentType` is imported from `kosmos.models.hypothesis` (experiment.py:14). This creates a hard dependency chain: importing experiment.py triggers hypothesis.py, which triggers kosmos.config. Any breakage in that chain cascades. [FACT: experiment.py:14]

**Module-level constants set policy.** `_MAX_SAMPLE_SIZE = 100_000` (line 19) is used as a hard ceiling in multiple validators. Changing this value silently changes validation behavior for `ControlGroup.sample_size`, `ExperimentProtocol.sample_size`, and any future validators that reference it. [FACT: experiment.py:19, 120-124, 386-392]

**LLM-output defensive validators throughout.** Several `field_validator` methods are specifically designed to handle messy LLM output:
- `ControlGroup.coerce_sample_size` (line 106): Converts string to int, clamps to max. [FACT: lines 106-125]
- `StatisticalTestSpec.coerce_groups` (line 266): Splits comma-separated strings into lists. [FACT: lines 266-273]
- `StatisticalTestSpec.parse_effect_size` (line 282): Extracts floats from text like `"Medium (Cohen's d = 0.5)"` using regex. [FACT: lines 282-299]
- `ProtocolStep.ensure_title` (line 176): Replaces empty/short titles with `"Untitled Step"`. [FACT: lines 176-182]
- `ExperimentProtocol.coerce_protocol_sample_size` (line 373): Same clamping pattern as ControlGroup. [FACT: lines 373-392]

**`ProtocolStep` title validator runs in two phases.** `ensure_title` (mode='before') runs before standard validation, providing a fallback for empty strings. Then `validate_text_fields` runs after, ensuring the result is non-empty. [FACT: lines 176-189] The interaction is: empty string -> "Untitled Step" -> passes text validation.

**`ExperimentProtocol.validate_steps` sorts steps by number.** The validator at line 424-438 not only validates sequential numbering but also SORTS the steps list as a side effect. [FACT: line 438: `return sorted(v, key=lambda s: s.step_number)`] Input order is not preserved. [FACT: experiment.py:438]

**`model_config = ConfigDict(use_enum_values=False)` only on `ExperimentProtocol`.** Only one model (line 575) has this setting. Other models in this file (Variable, StatisticalTestSpec, etc.) use Pydantic defaults. [FACT: line 575]

**`re` is imported at call time, not module scope.** `StatisticalTestSpec.parse_effect_size` imports `re` inside the validator function (line 293). This is a micro-performance hit on every validation call. [FACT: experiment.py:293]

**`to_dict()` is hand-written, not `model_dump()`.** The 100-line `to_dict()` method (lines 471-573) manually serializes every field. Adding a new field to the model without updating `to_dict()` means it silently disappears from serialization. [FACT: experiment.py:471-573]

**Blast radius.** With 30 importers spanning experiment templates, agents, execution, validators, and tests: Renaming `ExperimentProtocol` breaks the experiment designer agent, validator, all templates, resource estimator, memory module, world model, and research director. [FACT: grep found 30+ import sites] Changing `ProtocolStep` fields breaks all experiment templates that construct steps. [FACT] Changing `Variable`/`VariableType` breaks template variable definitions and protocol accessors like `get_independent_variables()`. [FACT] Changing `_MAX_SAMPLE_SIZE` silently changes validation behavior for all sample_size fields across ControlGroup and ExperimentProtocol. [FACT] Changing `ResourceRequirements` fields breaks `ExperimentProtocol.to_dict()` (which manually serializes every field) and `ExperimentDesignResponse`. [FACT] Changing `StatisticalTest` enum breaks experiment templates and statistical test specs. [FACT]

**Runtime dependencies.** `pydantic` (BaseModel, Field, field_validator, ConfigDict) -- external dependency. [FACT] `kosmos.models.hypothesis.ExperimentType` -- top-level import. [FACT: line 14] `kosmos.config._DEFAULT_CLAUDE_SONNET_MODEL` -- top-level import, value is `"claude-sonnet-4-5"`. [FACT: line 15] `logging` (stdlib) -- for module logger and validator warnings. [FACT] `re` (stdlib) -- imported INSIDE `parse_effect_size` validator (line 293), not at module scope. [FACT: line 293] `datetime`, `enum`, `typing` (stdlib). [FACT] Import chain: experiment.py -> hypothesis.py -> kosmos.config. [FACT]

**Public API details:**

`VariableType(str, Enum)` (line 21): Four-value enum: `INDEPENDENT`, `DEPENDENT`, `CONTROL`, `CONFOUNDING`. [FACT]

`StatisticalTest(str, Enum)` (line 29): Nine-value enum of common statistical tests plus `CUSTOM`. [FACT]

`Variable(BaseModel)` (line 42): Represents an experiment variable with name, type, description (10+ chars), optional values/fixed_value, unit, and measurement method. Preconditions: `name`, `type`, `description` (10+ chars) required. [FACT]

`ControlGroup(BaseModel)` (line 81): Control group with name, description (5+ chars), variable settings, rationale (10+ chars), and optional sample size. Side effects: `coerce_sample_size` validator logs warnings via `_experiment_logger` when it coerces strings or clamps values. [FACT: lines 116-117, 121-123] String sample_size that can't be parsed -> set to `None` (line 119). Values > 100,000 -> clamped to 100,000 (line 124). [FACT]

`ProtocolStep(BaseModel)` (line 138): A single experiment step with number, title (3+ chars or auto-filled), description (10+ chars), action, dependencies, expected outputs, time estimates, and code hints. Side effects: `ensure_title` replaces empty titles with `"Untitled Step"`. [FACT: line 181]

`ResourceRequirements(BaseModel)` (line 193): Resource estimate container: compute hours, memory, GPU requirements, cost, duration, data sources, libraries, parallelization hints. All fields optional with defaults. All numeric fields have `ge=0`. [FACT]

`StatisticalTestSpec(BaseModel)` (line 235): Specification for a statistical test with type, hypotheses, alpha, variables, groups, power analysis parameters. Side effects: `coerce_groups` validator splits comma-separated strings. [FACT: line 271] `parse_effect_size` extracts floats from text. [FACT: line 293] Non-numeric effect size strings with no extractable number -> `None`. [FACT: line 298]

`ValidationCheck(BaseModel)` (line 302): A single validation check result with type, description, severity, status, message, and recommendation. [FACT]

`ExperimentProtocol(BaseModel)` (line 329): Complete experiment protocol tying together hypothesis, steps, variables, control groups, statistical tests, resources, validation, and reproducibility metadata. The central data object for the experiment subsystem. Preconditions: `name` (5+ chars), `hypothesis_id`, `experiment_type`, `domain`, `description` (20+ chars), `objective` (10+ chars), `steps` (non-empty, sequentially numbered), `variables`, `resource_requirements` required. Side effects: `validate_steps` sorts steps by step_number. [FACT: line 438] `coerce_protocol_sample_size` logs warnings on coercion. [FACT: lines 383-384] Non-sequential step numbers -> `ValidationError`. [FACT: line 436]
- `get_step(step_number)` (line 440): Returns step by number, or `None`. [FACT]
- `get_independent_variables()` / `get_dependent_variables()` (lines 447, 452): Filters variables dict by `VariableType`. [FACT]
- `has_control_group()` (line 455): Returns `True` if `control_groups` is non-empty. [FACT]
- `total_duration_estimate_days()` (line 459): Returns `resource_requirements.estimated_duration_days` if set, otherwise sums step durations and converts minutes to days. Returns 0.0 if no durations set. [FACT]
- `to_dict()` (line 471): Manual serialization of the entire protocol tree to a plain dict. Converts enums to `.value`, datetimes to ISO strings. [FACT]

`ExperimentDesignRequest(BaseModel)` (line 578): Request for experiment design with hypothesis_id, preferences, constraints, design parameters, and template selection. [FACT]

`ExperimentDesignResponse(BaseModel)` (line 616): Response containing the generated protocol, validation results, quality metrics, resource summary, and recommendations.
- `is_feasible(max_cost, max_duration)` (line 648): Returns `True` if within budget, within time, and validation passed. [FACT]

`ValidationReport(BaseModel)` (line 657): Comprehensive rigor assessment: checks performed/passed/failed, control group adequacy, sample size, power analysis, bias detection, reproducibility, and overall summary. [FACT]

---

### kosmos/knowledge/graph.py

Provides a Neo4j-backed knowledge graph for scientific literature with full CRUD operations on four node types (Paper, Concept, Method, Author) and five relationship types (CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO), plus graph traversal queries for citations, co-occurrence, and multi-hop paper discovery. [FACT: graph.py:1-6]

**Auto-starts a Docker container.** On initialization, `_ensure_container_running()` runs `docker ps` and, if the `kosmos-neo4j` container is not found, runs `docker-compose up -d neo4j`. It then polls via `docker exec kosmos-neo4j cypher-shell` up to 30 times with 2-second waits (up to 60 seconds). The hardcoded credentials in the health check are `neo4j` / `kosmos-password`. [FACT: graph.py:118-171]

**Connection failure is swallowed, not raised.** If Neo4j is unreachable, the constructor logs the error and sets `self.graph = None` and `self._connected = False`. It does NOT raise. Callers must check `self.connected` before use. [FACT: graph.py:96-99] Code that calls methods on `self.graph` without checking `self.connected` will get `AttributeError: 'NoneType' object has no attribute 'run'`. [FACT: graph.py:96-99]

**`create_authored` increments `paper_count` without idempotency.** Each call to `create_authored` does `author["paper_count"] += 1` and pushes. If called twice for the same author-paper pair (even with `merge=True`), the count is double-incremented because the merge only applies to the relationship, not the count logic. [FACT: graph.py:615-616] Same issue affects `create_discusses` (frequency, line 659) and `create_uses_method` (usage_count, line 703). [FACT: graph.py:659, 703]

**Cypher injection via f-string in `get_citations` and `find_related_papers`.** The `depth` and `max_hops` integer parameters are interpolated into Cypher via f-strings (e.g., `[:CITES*1..{depth}]`). While these are typed as `int`, any caller passing a string could inject Cypher. [FACT: graph.py:761, 917]

**Node lookup cascade in `get_paper`.** The method tries four different indexes sequentially: `id`, then `doi`, then `arxiv_id`, then `pubmed_id`. This means a DOI string that accidentally matches a different paper's `id` field will return the wrong paper. [FACT: graph.py:262-289]

**`delete_paper` uses py2neo's `graph.delete(node)` which detaches relationships automatically** -- deleting a Paper node also deletes all its CITES, AUTHORED, DISCUSSES, and USES_METHOD relationships. [FACT: graph.py:322-329]

**`get_stats()` runs 9 separate Cypher queries** (4 node counts + 5 relationship counts), which can be slow on large graphs. There is no caching. [FACT: graph.py:981]

**The Docker health check hardcodes Neo4j credentials** (`neo4j` / `kosmos-password`) in a subprocess command, which may differ from the actual config credentials passed to the constructor. [FACT: graph.py:155-156]

**Blast radius.** Docker dependency: The auto-start feature means initialization can take up to 60+ seconds and requires Docker to be installed and running. Disabling `auto_start_container` skips this but requires manual Neo4j setup. [FACT] Index names: The 10 indexes created at init use Neo4j's `CREATE INDEX ... IF NOT EXISTS`. Renaming or removing indexes affects query performance. [FACT] Node properties: The property names on Paper nodes are used in Cypher queries. Changing property names breaks all queries. [FACT] Singleton pattern: `get_knowledge_graph()` returns a module-global singleton. Thread safety is not guaranteed. [FACT] py2neo dependency: The entire module depends on `py2neo` for Neo4j access. This is NOT an optional dependency (no try/except guard). [FACT]

**Runtime dependencies.** `py2neo` (hard dependency) -- Graph, Node, Relationship, NodeMatcher, RelationshipMatcher. [FACT: graph.py:15] `py2neo.errors.Neo4jError` -- imported but not directly used in the visible code. [FACT: graph.py:16] `kosmos.config.get_config()` -- for `config.neo4j.uri`, `config.neo4j.user`, `config.neo4j.password`, `config.neo4j.database`. [FACT: graph.py:18] `kosmos.literature.base_client.PaperMetadata` -- paper model for `create_paper`. [FACT: graph.py:19] `docker` and `docker-compose` CLI tools -- invoked via `subprocess.run()` for container management. [FACT: graph.py:126-143] Neo4j server -- must be running (either via Docker auto-start or manually). [FACT: graph.py:81-88]

**Public API details:**

`KnowledgeGraph`:
- `__init__(uri, user, password, database, auto_start_container=True, create_indexes=True)`: Connects to Neo4j, optionally auto-starts Docker container, creates performance indexes. Side effects: May start a Docker container. Creates 10 database indexes. Tests connection with `RETURN 1`. Error behavior: Swallows connection errors; sets `self._connected = False`. Does NOT raise. [FACT]
- `connected -> bool` (property): Returns whether Neo4j connection is active. [FACT]
- `create_paper(paper, merge=True) -> Node`: Creates or merges a Paper node. With `merge=True`, updates existing node if found by `primary_identifier`. Will raise if not connected (no guard on `self.node_matcher`). [FACT]
- `get_paper(paper_id) -> Optional[Node]`: Looks up a Paper by trying `id`, `doi`, `arxiv_id`, `pubmed_id` fields in sequence. Returns None if not found. [FACT]
- `create_citation(citing_paper_id, cited_paper_id, merge=True) -> Optional[Relationship]`: Creates a CITES relationship between two existing Paper nodes. Returns None if either paper not found (logs warning). [FACT]
- `create_authored(author_name, paper_id, order, role, merge=True) -> Optional[Relationship]`: Creates an AUTHORED relationship and increments the author's `paper_count`. Returns None if nodes not found. [FACT]
- `create_discusses(paper_id, concept_name, relevance_score, section, merge=True) -> Optional[Relationship]`: Creates a DISCUSSES relationship and increments concept `frequency`. Returns None if nodes not found. [FACT]
- `create_uses_method(paper_id, method_name, confidence, context, merge=True) -> Optional[Relationship]`: Creates a USES_METHOD relationship and increments method `usage_count`. Returns None if nodes not found. [FACT]
- `get_citations(paper_id, depth=1) -> List[Dict]`: Returns papers cited by a given paper, up to N hops deep. Will raise on Neo4j errors. [FACT]
- `find_related_papers(paper_id, max_hops=2, limit=20) -> List[Dict]`: Finds related papers through any relationship type within N hops. Will raise on Neo4j errors. [FACT]
- `get_stats() -> Dict`: Counts all node types and relationship types via 9 separate Cypher queries. Will raise on Neo4j errors. [FACT]
- `clear_graph()`: Executes `MATCH (n) DETACH DELETE n` -- destroys ALL data in the database. Irreversible data loss. Will raise on Neo4j errors. [FACT]

`get_knowledge_graph(...) -> KnowledgeGraph`: Module-level singleton factory. First call triggers Docker auto-start and Neo4j connection. Propagates constructor behavior (connection errors swallowed). [FACT]

---

### kosmos/models/hypothesis.py

Defines the Pydantic data models for the hypothesis lifecycle: generation requests, hypothesis objects with scores and evolution tracking, generation responses, novelty reports, testability reports, and prioritized hypothesis wrappers. This is a pure data-model file -- it contains no business logic beyond validation and serialization. [FACT]

**Import-time dependency on `kosmos.config`.** The module imports `_DEFAULT_CLAUDE_SONNET_MODEL` from `kosmos.config` at module scope (hypothesis.py:13). This means importing `Hypothesis` triggers the entire config module to load. If `kosmos.config` fails (e.g., missing env vars), this module fails too. [FACT: hypothesis.py:13]

**`ExperimentType` is defined HERE, not in experiment.py.** Despite the name, `ExperimentType` lives in `hypothesis.py` (line 15-19) and is re-imported by `kosmos/models/experiment.py` (experiment.py:14). This creates a cross-module dependency where the experiment model depends on the hypothesis model. [FACT: experiment.py:14]

**`Hypothesis` is NOT re-exported from `kosmos/models/__init__.py`.** [ABSENCE: checked models/__init__.py -- only Domain models are exported] Every importer must use `from kosmos.models.hypothesis import Hypothesis` directly.

**Validator is lenient on predictive language.** `validate_statement` checks for predictive words (line 98-101) but only as a pass-through comment -- it never warns or fails. [FACT: hypothesis.py:101] The check is effectively dead code.

**`datetime.utcnow()` used for defaults.** `created_at` and `updated_at` use `datetime.utcnow()` as `default_factory` (line 76-77). This is deprecated in Python 3.12+ and produces naive datetimes (no timezone info). [FACT]

**`model_config = ConfigDict(use_enum_values=False)` on Hypothesis.** Hypothesis stores enum objects, not their string values. Code that serializes Hypothesis must call `.value` explicitly or use `to_dict()`. Direct `model_dump()` will return Enum objects, not strings. [FACT: line 156]

**No `model_config` on `HypothesisGenerationResponse`.** Unlike `Hypothesis`, the response model does not set `use_enum_values=False`. Pydantic default behavior applies, which may differ between Pydantic v1 and v2. [FACT: line 199 -- no ConfigDict]

**Blast radius.** With 48 importers spanning experiments, agents, execution, knowledge, world_model, and tests: Renaming/removing `Hypothesis` class breaks 30+ direct importers across the codebase. The most-imported single symbol. [FACT] Renaming/removing `ExperimentType` enum breaks experiment.py (which re-imports it at line 14), plus every experiment template, resource_estimator, and experiment-related service. Chain reaction. [FACT] Changing `Hypothesis` field names or types breaks any code that accesses `.statement`, `.rationale`, `.testability_score`, etc. Also breaks serialization consumers of `to_dict()`. [FACT] Changing validation thresholds (e.g., `min_length=10` on `statement`) could cause previously-valid hypotheses to fail validation at deserialization time. [FACT] Changing `HypothesisStatus` enum values breaks any persisted data or config that references status strings like "generated", "testing", etc. [FACT]

**Runtime dependencies.** `pydantic` (BaseModel, Field, field_validator, ConfigDict) -- external dependency. [FACT] `kosmos.config._DEFAULT_CLAUDE_SONNET_MODEL` -- top-level import, value is `"claude-sonnet-4-5"`. [FACT: config.py:17] `datetime`, `enum`, `typing` (stdlib). [FACT] No deferred/lazy imports. [FACT]

**Public API details:**

`ExperimentType(str, Enum)` (line 15): Three-value enum: `COMPUTATIONAL`, `DATA_ANALYSIS`, `LITERATURE_SYNTHESIS`. Defines what kind of experiment can test a hypothesis. [FACT]

`HypothesisStatus(str, Enum)` (line 22): Six-value lifecycle enum: `GENERATED`, `UNDER_REVIEW`, `TESTING`, `SUPPORTED`, `REJECTED`, `INCONCLUSIVE`. [FACT]

`Hypothesis(BaseModel)` (line 32): Core data model for a scientific hypothesis. Contains statement, rationale, domain, status, four float scores (testability, novelty, confidence, priority), experiment suggestions, literature links, and evolution tracking fields. Preconditions: `research_question` (required), `statement` (10-500 chars, must not end with `?`), `rationale` (20+ chars), `domain` (required). `validate_statement` rejects questions ending with `?`. [FACT: line 94-95] `validate_rationale` rejects strings under 20 chars. [FACT: line 113]
- `to_dict()` (line 117): Converts to a plain dict with enum values as strings and datetimes as ISO strings. [FACT]
- `is_testable(threshold=0.3)` (line 144): Returns `True` if `testability_score >= threshold`. Returns `False` if score is `None`. [FACT]
- `is_novel(threshold=0.5)` (line 150): Returns `True` if `novelty_score >= threshold`. Returns `False` if score is `None`. [FACT]

`HypothesisGenerationRequest(BaseModel)` (line 159): Request model for hypothesis generation. Contains research question, optional domain, count (1-10), context, paper IDs, and generation parameters (max iterations, novelty check toggle, min novelty score). Preconditions: `research_question` (10+ chars). [FACT]

`HypothesisGenerationResponse(BaseModel)` (line 199): Response wrapper containing a list of `Hypothesis` objects plus generation metadata (time, papers analyzed, model used, average scores).
- `get_best_hypothesis()` (line 218): Returns the hypothesis with the highest `priority_score`. Falls back to first hypothesis if none have scores. Returns `None` if list is empty. [FACT: line 221]
- `filter_testable(threshold)` / `filter_novel(threshold)` (lines 231, 235): Filters the hypothesis list by testability or novelty score threshold. Returns empty list if none qualify. [FACT]

`NoveltyReport(BaseModel)` (line 240): Detailed novelty analysis for a hypothesis, with similar work detection, max similarity score, prior art flag, and human-readable summary. [FACT]

`TestabilityReport(BaseModel)` (line 265): Testability analysis for a hypothesis, with experiment suggestions, resource estimates, challenges, and recommendation. [FACT]

`PrioritizedHypothesis(BaseModel)` (line 299): Wraps a `Hypothesis` with composite priority scoring (novelty 30%, feasibility 25%, impact 25%, testability 20%) plus rank and rationale.
- `update_hypothesis_priority()` (line 328): Mutates the wrapped `Hypothesis` object's `priority_score` and `updated_at` fields in place. This is the only mutation in the entire file. [FACT: line 329-330]

---

### kosmos/core/llm.py

Provides a unified LLM client interface supporting Anthropic (API and CLI mode) and OpenAI-compatible providers through a singleton pattern; all LLM access in the codebase funnels through `get_client()` or `get_provider()`. [FACT: llm.py:1-12]

**CLI mode detection is a string trick.** `self.is_cli_mode = self.api_key.replace('9', '') == ''` -- any API key consisting entirely of 9s triggers CLI routing through the Anthropic SDK. This is undocumented externally and silently changes cost tracking behavior (CLI mode returns $0.00 cost). [FACT: llm.py:179, llm.py:587-588] An empty string API key would also match as CLI mode. In practice, the `ValueError` at line 163 prevents this. [FACT: llm.py:179]

**The singleton holds either `ClaudeClient` OR `LLMProvider`.** `_default_client` is typed `Optional[Union[ClaudeClient, LLMProvider]]`. The two types have different interfaces (`generate()` vs provider-specific methods), so callers must know which type they received or use `get_provider()` which asserts the type. [FACT: llm.py:609, llm.py:700-706]

**Thread safety via double-checked locking.** The `get_client()` function uses a fast-path check outside the lock, then re-checks inside. Safe but the singleton is module-global, so `reset=True` from any thread replaces the client for all threads. [FACT: llm.py:643-649]

**Auto model selection never picks higher than Sonnet.** The `ModelComplexity.estimate_complexity()` returns "haiku" for scores <30 and "sonnet" for everything else (both moderate and high). The "high complexity" path also maps to "sonnet". [FACT: llm.py:88-94]

**Cache bypasses on retry.** `generate_structured()` passes `bypass_cache=attempt > 0`, so retries after JSON parse failures always hit the API. [FACT: llm.py:467]

**`generate_with_messages()` does not use the cache.** Unlike `generate()`, multi-turn messages bypass caching entirely. [FACT: llm.py:367-408, no cache logic present]

**Auto model selection disabled in CLI mode.** The condition is `self.enable_auto_model_selection and not self.is_cli_mode`. [FACT: llm.py:251]

**Cost estimation hardcodes model name.** Cost estimation in `get_usage_stats()` hardcodes `"claude-sonnet-4-5"` model name for cost lookup regardless of what model was actually used. [FACT: llm.py:519]

**`generate_with_messages()` uses `self.model` directly.** It ignores `self.default_model` and auto-selection. If the caller previously changed `self.model`, this persists. [FACT: llm.py:389]

**`generate_structured()` schema append behavior.** It appends schema to system prompt on every retry, but the system prompt is rebuilt from the original `system` param, so no duplication occurs. However, the schema instruction is always added even if the original system prompt already contains JSON instructions. [FACT: llm.py:456]

**Blast radius.** Changing `get_client()` return type or signature breaks the 27+ Python importers that call `get_client()`. Key consumers: `research_director.py:128`, `hypothesis_generator.py`, `experiment_designer.py`, `data_analyst.py`, `literature_analyzer.py`, `code_generator.py`, `hypothesis/refiner.py`, `hypothesis/prioritizer.py`, `hypothesis/testability.py`, `domain_router.py`, `analysis/summarizer.py`. [FACT] Changing `generate()` signature: callers depend on kwargs `prompt`, `system`, `max_tokens`, `temperature`, `bypass_cache`, `model_override`. [FACT] Changing `generate_structured()` return type affects agents that expect parsed JSON back. [FACT] Changing the singleton pattern: the module-global `_default_client` means all callers share state. If the singleton is removed or the locking changes, concurrent agent workflows break. [FACT]

**Runtime dependencies.** `anthropic` SDK (optional import, but required at runtime if `ClaudeClient` is instantiated). [FACT: llm.py:23-31] `kosmos.config` for `_DEFAULT_CLAUDE_SONNET_MODEL`, `_DEFAULT_CLAUDE_HAIKU_MODEL`, and `get_config()`. [FACT: llm.py:20, llm.py:655] `kosmos.core.pricing.get_model_cost` for cost estimation. [FACT: llm.py:21] `kosmos.core.claude_cache.get_claude_cache` for response caching. [FACT: llm.py:33] `kosmos.core.utils.json_parser.parse_json_response` for structured output parsing. [FACT: llm.py:34] `kosmos.core.providers.base.LLMProvider` and `ProviderAPIError`. [FACT: llm.py:36-37] `kosmos.core.providers.anthropic.AnthropicProvider` (lazy import in fallback path). [FACT: llm.py:665] `kosmos.core.providers.get_provider_from_config` (lazy import). [FACT: llm.py:657] `ANTHROPIC_API_KEY` environment variable at runtime. [FACT: llm.py:160-165]

**Public API details:**

`ModelComplexity`:
- `estimate_complexity(prompt, system=None)`: Static utility that scores prompt complexity (0-100) using token count and keyword matching, then recommends "haiku" or "sonnet". Returns dict with `complexity_score`, `total_tokens_estimate`, `keyword_matches`, `recommendation`, `reason`. Pure function, no side effects, no exceptions. [FACT: llm.py:52-105]

`ClaudeClient`:
- Wraps the Anthropic SDK, adding caching, auto model selection, and usage tracking. Supports API mode (real API key) and CLI mode (all-9s key routes to Claude Code CLI). Preconditions: `anthropic` package must be installed. `ANTHROPIC_API_KEY` env var or `api_key` param required. Side effects: Creates `ClaudeCache` instance on init. Mutates internal counters on every call. `__init__` raises `ImportError` if `anthropic` not installed, `ValueError` if no API key. `generate()` propagates API exceptions. `generate_structured()` raises `ProviderAPIError` after retries exhausted. [FACT: llm.py:154-165, llm.py:480-486]
- `generate(prompt, system, max_tokens, temperature, stop_sequences, bypass_cache, model_override) -> str`: Returns generated text. Checks cache first (unless `bypass_cache=True`). Logs warning on `max_tokens` truncation. [FACT: llm.py:207-365]
- `generate_with_messages(messages, system, max_tokens, temperature) -> str`: Multi-turn conversation. Does NOT use cache. Does NOT support auto model selection (always uses `self.model`). [FACT: llm.py:367-408]
- `generate_structured(prompt, output_schema, system, max_tokens, temperature, max_retries, schema) -> Dict`: Retries up to `max_retries+1` total attempts. Appends JSON schema to system prompt. Uses `parse_json_response()` for robust parsing. `schema` is an alias for `output_schema` (provider compatibility). Raises `ProviderAPIError` on exhaustion. [FACT: llm.py:410-486]
- `get_usage_stats() -> Dict`: Returns comprehensive stats: requests, tokens, cost, cache metrics, model selection stats. Cost is $0.00 in CLI mode. [FACT: llm.py:488-578]
- `reset_stats()`: Zeroes all counters. [FACT: llm.py:596-605]

`get_client(reset=False, use_provider_system=True) -> Union[ClaudeClient, LLMProvider]`: Thread-safe singleton accessor. With `use_provider_system=True` (default), returns an `LLMProvider` from config. Falls back to `AnthropicProvider` if config fails. With `use_provider_system=False`, returns a `ClaudeClient`. First call creates the global singleton. `reset=True` replaces it for all threads. Catches config exceptions and falls back to `AnthropicProvider` with env-var API key. [FACT: llm.py:613-679]

`get_provider() -> LLMProvider`: Calls `get_client(use_provider_system=True)` and asserts the result is an `LLMProvider`. Raises `TypeError` if the singleton is a `ClaudeClient` instead of `LLMProvider`. [FACT: llm.py:682-706]

---

### kosmos/core/logging.py

Provides a structured logging system with JSON and text output modes, a module-level `ContextVar` for cross-async correlation IDs, and an `ExperimentLogger` class that tracks experiment lifecycle events with timing and structured metadata. It wraps Python's stdlib `logging` with Kosmos-specific formatters and configuration. [FACT]

**Import side effect: module-level ContextVar.** Importing this module instantiates `correlation_id: contextvars.ContextVar` at module scope (logging.py:23-25). This ContextVar exists in the process regardless of whether `setup_logging()` is ever called. However, no code in `kosmos/` actually imports this ContextVar from here [ABSENCE] -- agents use their own `correlation_id` field on `AgentMessage` (base.py:65). The ContextVar is only read inside `JSONFormatter.format()` (logging.py:62-64). [FACT]

**`setup_logging()` clears ALL root logger handlers** (logging.py:179: `root_logger.handlers = []`). If called more than once, or if third-party code has added handlers to the root logger, those handlers are silently destroyed. [FACT: logging.py:179]

**`setup_logging()` emits a log message as a side effect** (logging.py:210-215). Every call to `setup_logging()` produces an INFO-level "Logging initialized" message with `extra={}` dict. This means the very first log line from any Kosmos process is always this setup message. [FACT]

**TextFormatter mutates the LogRecord in place** (logging.py:128: `record.levelname = f"{color}{record.levelname}{reset}"`). If multiple handlers share the same record, downstream handlers will see ANSI-colored level names. [FACT: logging.py:128] This only triggers when stdout is a TTY (logging.py:125). [FACT] If the same record is processed by both a TextFormatter and a JSONFormatter (e.g., console + file), the JSON output will contain ANSI escape codes. [FACT: logging.py:128]

**`configure_from_config()` uses a deferred import** of `kosmos.config.get_config` (logging.py:395). This avoids circular imports at module load time but means the function will fail at runtime if `kosmos.config` is not importable. [FACT]

**`datetime.utcfromtimestamp` is deprecated** in Python 3.12+. Used at logging.py:52. This will emit deprecation warnings on newer Python versions. [FACT]

**JSONFormatter has no serialization guard.** If `record.extra` contains non-JSON-serializable objects, `json.dumps` raises `TypeError` and the log line is lost. [FACT: logging.py:82]

**Blast radius.** With 140 importers, changes here affect nearly the entire codebase. Specific risks: Renaming `get_logger` or `setup_logging` breaks every module that imports them. These are the two most-used exports. [FACT] Changing `JSONFormatter` output schema (the JSON keys at logging.py:51-59) breaks any log parsing, monitoring, or alerting that consumes structured logs. The fields `timestamp`, `level`, `logger`, `message`, `module`, `function`, `line` are the contract. [FACT] Changing `LogFormat` enum values ("json", "text") breaks config files and CLI flags that reference these strings. [FACT] Removing `ExperimentLogger` breaks experiment tracking workflows. [FACT] Changing `correlation_id` ContextVar name: currently low risk (no external importers found [ABSENCE]), but the JSONFormatter reads it every log line. [FACT]

**Runtime dependencies.** `logging`, `logging.handlers` (stdlib) -- core dependency. [FACT] `contextvars` (stdlib) -- for the ContextVar. [FACT] `json` (stdlib) -- for JSONFormatter. [FACT] `kosmos.config.get_config` -- only via `configure_from_config()`, deferred import at logging.py:395. [FACT] No external (pip) dependencies. [FACT]

**Public API details:**

`correlation_id` (ContextVar, line 23): Process-scoped ContextVar holding an optional string for request tracing across async boundaries. Defaults to `None`. Value is read by `JSONFormatter.format()`. [FACT]

`LogFormat(str, Enum)` (line 28): Enum with two values: `JSON = "json"`, `TEXT = "text"`. Used to select formatter. [FACT]

`JSONFormatter(logging.Formatter)` (line 34): Formats log records as single-line JSON strings with standard fields plus optional correlation_id, workflow context, and extras. Must be attached to a handler. Reads `correlation_id` ContextVar on every format call (line 62). If `json.dumps` fails (e.g., non-serializable extra), raises `TypeError` -- no catch. [FACT: logging.py:82]

`TextFormatter(logging.Formatter)` (line 85): Human-readable log formatter with optional ANSI color codes for terminal output. Mutates `record.levelname` in place when colors are enabled and stdout is a TTY. [FACT: logging.py:128] Falls through to parent `Formatter.format()`. [FACT]

`setup_logging(level, log_format, log_file, debug_mode)` (line 133): Configures the root logger with specified level, format, and optional rotating file handler (10MB max, 5 backups). Side effects: (1) Clears ALL existing root logger handlers. [FACT: line 179] (2) Creates directory for log_file. [FACT: line 197] (3) Emits "Logging initialized" INFO message. [FACT: line 210] (4) `debug_mode=True` overrides `level` to DEBUG. [FACT: line 174-175] `getattr(logging, level.upper())` raises `AttributeError` for invalid level strings -- no catch. [FACT]

`get_logger(name)` (line 220): Returns a `logging.Logger` for the given name. Thin wrapper around `logging.getLogger(name)`. No side effects beyond stdlib logger creation. [FACT]

`ExperimentLogger` (line 242): Stateful logger that tracks experiment lifecycle (start, hypotheses, designs, execution, results, errors, end) with timing. Accumulates events in an in-memory list. `experiment_id` must be provided. `start()` must be called before `end()` for duration calculation to work (line 353: returns 0 if start_time is None). [FACT] Emits structured log messages via `self.logger` on every method call. Accumulates events in `self.events` list (unbounded -- no max size). [FACT: line 271] `end()` returns duration=0 if `start()` was never called. [FACT: line 353] `get_summary()` returns `None` timestamps if start/end never called. [FACT: line 376]

`configure_from_config()` (line 383): Reads logging configuration from `kosmos.config.get_config()` and calls `setup_logging()`. Deferred import of `kosmos.config` (line 395) raises `ImportError` if config module is broken. Same side effects as `setup_logging()`. [FACT]

---

### kosmos/core/providers/base.py

Defines the abstract `LLMProvider` interface and supporting data types (`Message`, `UsageStats`, `LLMResponse`, `ProviderAPIError`) that all LLM provider implementations (Anthropic, OpenAI, LiteLLM) must implement, enabling Kosmos to swap between LLM backends via a unified API for text generation, structured output, streaming, and usage tracking. [FACT: base.py:1-6]

**LLMResponse masquerades as str.** `LLMResponse` implements 20+ string methods (`strip`, `lower`, `split`, `replace`, `find`, `__contains__`, `__len__`, `__iter__`, `__getitem__`, `encode`, `format`, `join`, etc.) delegating to `self.content`. This means callers can use an `LLMResponse` object where `str` is expected without explicit conversion. However, `isinstance(response, str)` returns False. [FACT: base.py:80-154] All string methods delegate to `self.content` and return `str` (not `LLMResponse`). This means chaining like `response.strip().lower()` works but returns plain `str`, losing the response metadata. [FACT: base.py:80-154]

**`generate_stream_async` has dead code after raise.** The method raises `NotImplementedError` at line 360, then has `if False: yield` at lines 362-363. The dead yield exists solely to make Python treat the function as an async generator rather than a coroutine (which would cause a TypeError at the call site). [FACT: base.py:360-363] This is load-bearing dead code -- removing it changes the function from an async generator to a plain coroutine, which breaks callers using `async for`. [FACT: base.py:360-363]

**`ProviderAPIError.is_recoverable()` has competing heuristics.** The method checks the `self.recoverable` flag first, then HTTP status codes, then does string pattern matching on the error message. The message patterns can conflict -- e.g., an error containing both "timeout" (recoverable) and "invalid" (non-recoverable) would match the recoverable pattern first and return True because of the early-return logic. [FACT: base.py:445-484] The "recoverable_patterns" check runs before "non_recoverable_patterns", so ambiguous error messages default to recoverable. [FACT: base.py:466-477]

**Provider name derived from class name.** `self.provider_name` is set by stripping "Provider" from the class name and lowercasing (line 187). If a subclass is named `MyCustomProvider`, the provider_name becomes `"mycustom"`. [FACT: base.py:187]

**Usage tracking is instance-level only.** Token counts and cost are accumulated on the provider instance (`self.total_input_tokens`, etc.). There is no global/shared tracking across multiple provider instances. [FACT: base.py:190-193]

**`_update_usage_stats` does not validate.** The method blindly adds token counts. If `usage.cost_usd` is `0` (falsy but valid), it will NOT be added due to `if usage.cost_usd:` check. Only `None` and `0.0` are skipped; negative costs would be added. [FACT: base.py:391-402]

**`LLMResponse` with empty content is falsy.** `__bool__` returns `bool(self.content)` -- an empty content string means the response is falsy. Code like `if not response:` will incorrectly treat an empty LLM response as a failure even if the API call succeeded. [FACT: base.py:98-99]

**Blast radius.** Three concrete providers inherit from `LLMProvider`: `AnthropicProvider`, `OpenAIProvider`, `LiteLLMProvider`. Changing any abstract method signature breaks all three. [FACT: anthropic.py:36, openai.py:32, litellm_provider.py:40] `LLMResponse` is returned by every `generate()` call across the system. Its string-compatibility methods are relied upon by callers that do `response.strip()`, `if "keyword" in response`, etc. Removing any string method would cause AttributeError in downstream code. [FACT] `ProviderAPIError` is the canonical exception type for provider failures. Retry logic in the execution layer checks `is_recoverable()` to decide whether to retry. Changing recoverability heuristics changes retry behavior system-wide. [FACT] `Message` dataclass is the input format for `generate_with_messages()`. Any field change affects all multi-turn conversation code. [FACT]

**Runtime dependencies.** `abc.ABC` / `abc.abstractmethod` -- for abstract interface enforcement. [FACT] `datetime.datetime` -- for `UsageStats.timestamp`. [FACT] No external packages -- this module is pure stdlib + typing. [FACT] Concrete providers import from this module; this module imports nothing from Kosmos. [FACT]

**Public API details:**

`Message` (dataclass): Fields: `role` (str), `content` (str), `name` (Optional[str]), `metadata` (Optional[Dict]). Plain data container. No methods beyond dataclass defaults. [FACT: base.py:18-31]

`UsageStats` (dataclass): Fields: `input_tokens`, `output_tokens`, `total_tokens` (all int), plus optional `cost_usd`, `model`, `provider`, `timestamp`. Plain data container. [FACT: base.py:35-54]

`LLMResponse` (dataclass): Fields: `content` (str), `usage` (UsageStats), `model` (str), optional `finish_reason`, `raw_response`, `metadata`. [FACT: base.py:57-78]

`LLMProvider(ABC)`:
- `__init__(config)`: Stores config dict, derives provider_name from class name, zeroes usage counters. Side effect: logs initialization at INFO. [FACT: base.py:179-195]
- `generate(prompt, system, max_tokens, temperature, stop_sequences, **kwargs)` [abstract]: Sync text generation. Returns `LLMResponse`. Raises `ProviderAPIError`. [FACT: base.py:197-224]
- `generate_async(prompt, system, max_tokens, temperature, stop_sequences, **kwargs)` [abstract, async]: Async text generation. Same contract as `generate()`. [FACT: base.py:226-253]
- `generate_with_messages(messages, max_tokens, temperature, **kwargs)` [abstract]: Multi-turn generation from `List[Message]`. Returns `LLMResponse`. [FACT: base.py:255-278]
- `generate_structured(prompt, schema, system, max_tokens, temperature, **kwargs)` [abstract]: Returns `Dict[str, Any]` (parsed JSON). Raises `ProviderAPIError` or `JSONDecodeError`. [FACT: base.py:280-308]
- `generate_stream(prompt, system, max_tokens, temperature, **kwargs)`: Non-abstract, default raises `NotImplementedError`. Returns `Iterator[str]`. [FACT: base.py:310-334]
- `generate_stream_async(prompt, system, max_tokens, temperature, **kwargs)`: Non-abstract, default raises `NotImplementedError`. Returns `AsyncIterator[str]`. [FACT: base.py:336-363]
- `get_model_info()` [abstract]: Returns dict with model metadata. [FACT: base.py:365-373]
- `get_usage_stats()`: Returns accumulated usage dict. Pure query. [FACT: base.py:375-389]
- `_update_usage_stats(usage)`: Increments counters from a `UsageStats` instance. Side effect: mutates instance counters. [FACT: base.py:391-402]
- `reset_usage_stats()`: Zeroes all usage counters. Side effect: logs at INFO. [FACT: base.py:404-410]

`ProviderAPIError(Exception)`:
- `__init__(provider, message, status_code, raw_error, recoverable)`: Default `recoverable=True`. [FACT: base.py:429-443]
- `is_recoverable()`: Multi-stage heuristic: explicit flag -> HTTP status code (4xx except 429 = non-recoverable) -> message pattern matching -> defaults to True for unknown errors. [FACT: base.py:445-484]

---

### kosmos/agents/research_director.py

The master orchestrator for autonomous research: it drives the full research cycle (hypothesize -> design experiment -> execute -> analyze -> refine -> iterate) by coordinating 6+ specialized agents and utility classes through a workflow state machine, managing convergence detection, error recovery, and knowledge graph persistence. [FACT: research_director.py:1-12]

**Architecture duality (Issue #76 Transition).** Two coordination mechanisms coexist: The module has both message-based `_send_to_*` methods (async, using `self.send_message()`) AND direct-call `_handle_*_action()` methods. Issue #76 revealed that message-based coordination silently failed because agents were never registered in the message router. The direct-call methods are the ones actually used. The `_send_to_*` methods are kept but effectively dead code. [FACT: research_director.py:1039-1219 (message-based), research_director.py:1391-1979 (direct-call)] `_send_to_convergence_detector` is explicitly deprecated: it now just calls `_handle_convergence_action()` and returns a dummy message. [FACT: research_director.py:1981-2003]

**Initialization complexity.** The constructor does a LOT: Database initialization, world model entity creation, skill loading, convergence detector setup, optional parallel executor and async LLM client initialization. Any of these can fail independently, and failures are caught-and-logged rather than raised. [FACT: research_director.py:68-260]

**Dual locking strategy.** Both `asyncio.Lock` and `threading.RLock/Lock` are maintained. The async locks are used in async code paths, the threading locks in sync context managers. [FACT: research_director.py:192-200] The sync `_workflow_context()` context manager yields `self.workflow` without any lock -- the comment says "not used with async". But if sync code uses this while async code uses the async lock, there is no mutual exclusion between the two paths. [FACT: research_director.py:376-379]

**Lazy agent initialization.** Sub-agents (`_hypothesis_agent`, `_experiment_designer`, `_code_generator`, `_code_executor`, `_data_provider`, `_data_analyst`, `_hypothesis_refiner`) are `None` at init and created on first use via lazy-init in the `_handle_*_action()` methods. [FACT: research_director.py:145-152]

**Infinite loop guard.** `MAX_ACTIONS_PER_ITERATION = 50` (module constant). If the `_actions_this_iteration` counter exceeds this, `decide_next_action()` forces `NextAction.CONVERGE`. [FACT: research_director.py:50, research_director.py:2455-2461] `_actions_this_iteration` is created via `hasattr` check in `decide_next_action()` instead of being initialized in `__init__`. This works but is inconsistent with all other instance variables. [FACT: research_director.py:2451-2452]

**Error recovery uses `time.sleep()`.** Inside `_handle_error_with_recovery()`, backoff is done with blocking `time.sleep()` -- [2, 4, 8] seconds. This blocks the event loop if called from async context. [FACT: research_director.py:674]

**Circuit breaker at 3 errors.** `MAX_CONSECUTIVE_ERRORS = 3`. After 3 consecutive failures, the workflow transitions to `ERROR` state. [FACT: research_director.py:45, research_director.py:649-662]

**Budget enforcement runs every decision cycle.** `decide_next_action()` checks budget via `kosmos.core.metrics.get_metrics().enforce_budget()` on every call. If the module is not available, it silently continues. [FACT: research_director.py:2405-2425]

**4 separate graph persistence methods.** `_persist_hypothesis_to_graph`, `_persist_protocol_to_graph`, `_persist_result_to_graph`, `_add_support_relationship`. Each opens a new DB session, fetches the entity, converts to a `world_model.Entity`, and creates relationships. All are fire-and-forget (catch-and-log exceptions). [FACT: research_director.py:388-562]

**World model is optional.** If `get_world_model()` fails, `self.wm = None` and all graph operations silently no-op. [FACT: research_director.py:242-255]

**`_handle_execute_experiment_action` is the most complex handler.** It loads protocol from DB, generates code via `ExperimentCodeGenerator`, executes via `CodeExecutor`, sanitizes results for JSON serialization (handling numpy types), and stores results in DB. [FACT: research_director.py:1521-1664]

**JSON sanitization is inline.** A nested `_json_safe()` function handles numpy types and non-serializable objects by converting to string. [FACT: research_director.py:1595-1613]

**Database initialization failure is soft.** Database initialization in `__init__` catches `RuntimeError` for "already initialized" and all other exceptions. If the DB init fails for a real reason, the error is only logged as a warning -- the director continues without a working database, which will cause cascading failures when any handler tries to query the DB. [FACT: research_director.py:131-139]

**Async LLM client reads env directly.** The async LLM client initialization reads `ANTHROPIC_API_KEY` directly from `os.getenv()`, bypassing the config system. This is different from how the sync `get_client()` works (which uses config-based provider factory). [FACT: research_director.py:228-239]

**`ExperimentResult` construction uses placeholder timing.** In `_handle_analyze_result_action()`, `ExperimentResult` is constructed with `start_time=_now, end_time=_now, duration_seconds=0.0` as placeholder metadata. This means any analysis code that relies on execution duration will get 0. [FACT: research_director.py:1704-1722]

**Sequential fallback has event loop issue.** The sequential fallback in `execute_experiments_batch()` calls `asyncio.get_event_loop().run_until_complete()` which will raise `RuntimeError` if an event loop is already running (e.g., during async execution). This path is only taken when concurrent execution is disabled. [FACT: research_director.py:2171-2174]

**Blast radius.** Changing `ResearchDirectorAgent.__init__` signature: The CLI `run` command, integration tests, e2e tests, and evaluation scripts all instantiate this class. Key consumers: `kosmos/cli/commands/run.py`, `kosmos/__init__.py`, 12+ test files, `evaluation/scientific_evaluation.py`. [FACT] Changing `execute()` return type: The `execute_sync()` wrapper, CLI, and tests depend on the return dict shape (`status`, `research_plan`, `next_action`, `workflow_state`). [FACT] Changing `get_research_status()` return shape: Test assertions and reporting depend on specific keys. [FACT] Changing message handler contracts: The `_handle_*_response()` methods expect specific `content` dict shapes from agents. Changing what agents return requires updating these handlers. [FACT] Changing `decide_next_action()` logic: This is the brain of the system. Any change to the decision tree alters research flow for all users. [FACT]

**Runtime dependencies.** `kosmos.agents.base` (BaseAgent, AgentMessage, MessageType, AgentStatus). [FACT: research_director.py:24] `kosmos.utils.compat.model_to_dict`. [FACT: research_director.py:25] `kosmos.core.rollout_tracker.RolloutTracker`. [FACT: research_director.py:26] `kosmos.core.workflow` (ResearchWorkflow, ResearchPlan, WorkflowState, NextAction). [FACT: research_director.py:27-32] `kosmos.core.convergence` (ConvergenceDetector, StoppingDecision, StoppingReason). [FACT: research_director.py:33] `kosmos.core.llm.get_client`. [FACT: research_director.py:34] `kosmos.core.stage_tracker.get_stage_tracker`. [FACT: research_director.py:35] `kosmos.models.hypothesis` (Hypothesis, HypothesisStatus). [FACT: research_director.py:36] `kosmos.world_model` (get_world_model, Entity, Relationship). [FACT: research_director.py:37] `kosmos.db` (get_session, init_from_config). [FACT: research_director.py:38, 131] `kosmos.db.operations` (get_hypothesis, get_experiment, get_result). [FACT: research_director.py:39] `kosmos.agents.skill_loader.SkillLoader`. [FACT: research_director.py:40] Lazy imports at runtime: `kosmos.agents.hypothesis_generator`, `kosmos.agents.experiment_designer`, `kosmos.agents.data_analyst`, `kosmos.execution.code_generator`, `kosmos.execution.executor`, `kosmos.execution.data_provider`, `kosmos.hypothesis.refiner`, `kosmos.execution.statistics`, `kosmos.core.async_llm`, `kosmos.execution.parallel`, `kosmos.core.metrics`. [FACT]

**Public API details:**

`ResearchDirectorAgent(BaseAgent)`:
- `__init__(research_question, domain=None, agent_id=None, config=None)`: Initializes the full orchestration stack. Preconditions: `research_question` required. Database must be initializable. `ANTHROPIC_API_KEY` must be set for LLM client. Side effects: Initializes database (catch-and-log on failure). Creates a `ResearchQuestion` entity in the world model. Error behavior: Catches and logs most init errors; continues with degraded functionality. [FACT: research_director.py:68-260]
- `execute(task: Dict) -> Dict` [async]: Main entry point. Supports `"start_research"` and `"step"`. Raises `ValueError` for unknown actions. [FACT: research_director.py:2868-2909]
- `execute_sync(task: Dict) -> Dict`: Synchronous wrapper. Tries to use running event loop first, falls back to `asyncio.run()`. [FACT: research_director.py:2911-2920]
- `decide_next_action() -> NextAction`: State-machine-based decision tree. Checks budget, runtime limits, iteration limits, convergence criteria, then routes based on `workflow.current_state`. Side effects: Increments `_actions_this_iteration`. May transition to CONVERGED if budget/runtime exceeded. [FACT: research_director.py:2388-2548]
- `process_message(message: AgentMessage)`: Routes incoming messages to type-specific handlers based on `metadata["agent_type"]`. [FACT: research_director.py:568-593]
- `get_research_status() -> Dict`: Returns comprehensive status dict. [FACT: research_director.py:2926-2952]
- `generate_research_plan() -> str`: Uses LLM to generate initial research strategy. Stores in `research_plan.initial_strategy`. [FACT: research_director.py:2349-2382]
- `register_agent(agent_type, agent_id)` / `get_agent_id(agent_type) -> Optional[str]`: Agent registry for coordination. In practice, unused by direct-call pattern (Issue #76). [FACT: research_director.py:2841-2862]
- `execute_experiments_batch(protocol_ids) -> List[Dict]`: Parallel experiment execution. Falls back to sequential if parallel executor not available. [FACT: research_director.py:2152-2204]
- `evaluate_hypotheses_concurrently(hypothesis_ids) -> List[Dict]` [async]: Concurrent LLM-based hypothesis evaluation. Requires async LLM client. [FACT: research_director.py:2206-2275]
- `analyze_results_concurrently(result_ids) -> List[Dict]` [async]: Concurrent LLM-based result analysis. Requires async LLM client. [FACT: research_director.py:2277-2343]

---

### kosmos/models/result.py

Defines the Pydantic data models for experiment results -- `ExperimentResult`, `StatisticalTestResult`, `VariableResult`, `ExecutionMetadata`, `ResultStatus`, and `ResultExport` -- serving as the canonical schema for all experiment output flowing through the system. [FACT: result.py:1-6]

**This is a data model, not a database model.** These Pydantic models are distinct from the SQLAlchemy `ResultModel` in `kosmos.db.models`. The research_director manually constructs these Pydantic models from DB records (e.g., `research_director.py:1704-1722`). There is no ORM relationship between them. [FACT]

**`model_to_dict` is a compat shim.** `to_dict()` calls `model_to_dict(self, mode='json', exclude_none=True)` from `kosmos.utils.compat`, not the standard Pydantic `model_dump()`. This exists for Pydantic v1/v2 compatibility. [FACT: result.py:9, result.py:242-243]

**`export_csv()` imports pandas at call time.** The `ResultExport.export_csv()` method does `import pandas as pd` inside the method body. This is the only place in the models layer that requires pandas, and it will crash if pandas is not installed. [FACT: result.py:293]

**`created_at` uses `datetime.utcnow` as default factory.** This captures time at object creation, not at DB insertion. The timestamp reflects when the Python object was instantiated. [FACT: result.py:203-204] `datetime.utcnow()` is deprecated in Python 3.12+. Should use `datetime.now(timezone.utc)`. [FACT: result.py:203]

**Validators enforce cross-field constraints.** `validate_primary_test` checks that `primary_test` name exists in `statistical_tests` list. But it handles both dict and model instances in `info.data` because Pydantic v2 passes raw dicts during validation. [FACT: result.py:217-228] This is fragile if Pydantic changes validation ordering. [FACT: result.py:220-226]

**`export_markdown()` crashes on `None` stats.** `ResultExport.export_markdown()` formats variable stats with `{var.mean:.2f}` without checking for `None`. Since `mean`, `median`, `std`, `min`, `max` are all `Optional[float]`, this will raise `TypeError` if any are `None`. [FACT: result.py:349-353]

**Blast radius.** Adding/removing fields on `ExperimentResult`: 27 importers construct or consume this model. Key consumers: `research_director.py` constructs `ExperimentResult` instances from DB records in 3 separate methods (lines 1704, 1851, and `_handle_analyze_result_action`). [FACT] `kosmos/agents/data_analyst.py` receives `ExperimentResult` in `interpret_results()`. [FACT] `kosmos/hypothesis/refiner.py` receives `ExperimentResult` in `evaluate_hypothesis_status()`. [FACT] `kosmos/core/convergence.py` accepts results for convergence checking. [FACT] `kosmos/execution/result_collector.py` creates and manages results. [FACT] `kosmos/core/feedback.py` and `kosmos/core/memory.py` consume results. [FACT] `kosmos/safety/verifier.py` validates results. [FACT] `kosmos/analysis/summarizer.py` and `kosmos/analysis/visualization.py` consume results. [FACT] `kosmos/world_model/models.py` creates Entity objects from results. [FACT] Changing `ResultStatus` enum values breaks any code doing `ResultStatus.SUCCESS` or comparing against `"success"` string. [FACT] Changing `to_dict()` or `to_json()` output format breaks anything that persists or deserializes results. [FACT] Changing `StatisticalTestResult` fields: The `ExperimentResult.validate_statistical_tests` validator enforces unique `test_name` values; changing the field name silently breaks validation. [FACT]

**Runtime dependencies.** `pydantic` (BaseModel, Field, field_validator, ConfigDict). [FACT: result.py:8] `kosmos.utils.compat.model_to_dict` for Pydantic v1/v2 compatible serialization. [FACT: result.py:9] `pandas` (lazy import in `ResultExport.export_csv()` only). [FACT: result.py:293] No LLM, DB, or network dependencies at import time. [FACT]

**Public API details:**

`ResultStatus(str, Enum)`: Values: `SUCCESS`, `FAILED`, `PARTIAL`, `TIMEOUT`, `ERROR`. [FACT: result.py:16-22]

`ExecutionMetadata(BaseModel)`: Captures execution context: timestamps, system info, resource usage, IDs, sandbox/timeout flags, errors/warnings. Required: `start_time`, `end_time`, `duration_seconds`, `python_version`, `platform`, `experiment_id`, `protocol_id`. `duration_seconds` must be >= 0. [FACT: result.py:25-58]

`StatisticalTestResult(BaseModel)`: Captures one statistical test: test type/name, statistic, p-value, effect size, confidence intervals, significance at multiple alpha levels. Required: `test_type`, `test_name`, `statistic`, `p_value`, `significant_0_05`, `significant_0_01`, `significant_0_001`, `significance_label`. `p_value` constrained to [0, 1]. [FACT: result.py:61-103]

`VariableResult(BaseModel)`: Summary statistics for one variable: mean, median, std, min, max, values, sample counts. Required: `variable_name` and `variable_type`. [FACT: result.py:105-124]

`ExperimentResult(BaseModel)`: The central result model. Combines status, raw/processed data, variable results, statistical tests, primary metrics, metadata, versioning, outputs, interpretation, timestamps. Required: `experiment_id`, `protocol_id`, `status`, `metadata`. `validate_statistical_tests` raises `ValueError` on duplicate test names. `validate_primary_test` raises `ValueError` if `primary_test` not found in `statistical_tests`. [FACT: result.py:127-205]
- `get_primary_test_result() -> Optional[StatisticalTestResult]`: Returns the matching result or `None`. [FACT: result.py:230-239]
- `to_dict() -> Dict` / `to_json() -> str`: Serialization using compat shim and Pydantic's `model_dump_json`. Both exclude `None` values. [FACT: result.py:241-247]
- `from_dict(data)` / `from_json(json_str)`: Class methods for deserialization via `model_validate` / `model_validate_json`. [FACT: result.py:249-257]
- `is_significant(alpha=0.05) -> bool`: Checks `primary_p_value < alpha`. Returns `False` if `primary_p_value` is `None`. [FACT: result.py:259-263]
- `get_summary_stats() -> Dict`: Returns dict of variable name -> stats dict. [FACT: result.py:265-277]

`ResultExport(BaseModel)`: Export wrapper supporting JSON, CSV, and Markdown formats. `export_csv()` requires `pandas` at runtime. [FACT: result.py:293] `export_markdown()` will crash with `TypeError` if any `VariableResult` has `None` for stats fields. [FACT: result.py:349-353]

---

### kosmos/orchestration/ (stage_orchestrator and 4 orchestration modules)

The file `kosmos/orchestration/stage_orchestrator.py` does **not exist** in the main Kosmos package. [ABSENCE: glob for `*orchestrat*` found no match in `kosmos/orchestration/`] A `StageOrchestratorAgent` exists in the reference codebase at `kosmos-reference/kosmos-agentic-data-scientist/src/agentic_data_scientist/agents/adk/stage_orchestrator.py`, which is a Google ADK-based agent (not part of Kosmos core).

The actual Kosmos orchestration layer lives in `kosmos/orchestration/` with four modules: `plan_creator.py`, `plan_reviewer.py`, `delegation.py`, and `novelty_detector.py`.

Implements a strategic research planning pipeline: PlanCreatorAgent generates 10-task plans per cycle with adaptive exploration/exploitation ratios, NoveltyDetector filters redundant tasks via semantic similarity, PlanReviewerAgent validates plans on 5 dimensions, and DelegationManager executes approved plans by routing tasks to specialized agents in parallel. [FACT: __init__.py:1-26]

Architecture flow: `Context -> Plan Creator -> Novelty Check -> Plan Reviewer -> Delegation Manager -> State Manager -> (loop back to Context)`. [FACT: __init__.py:17-21]

**plan_creator.py:**

Generates strategic research plans of 10 tasks per cycle, balancing exploration (new directions) vs exploitation (deepening findings) based on cycle number. [FACT: plan_creator.py:1-13]

Exploration ratio is hardcoded by cycle range: cycles 1-7 = 70% exploration, 8-14 = 50%, 15-20 = 30%. There is no configuration override. [FACT: plan_creator.py:105-121]

Falls back to mock planning if LLM is unavailable. If `self.client is None`, generates deterministic mock tasks instead of raising. The mock plan ensures structural requirements are met (3+ data_analysis, 2+ task types). [FACT: plan_creator.py:146-149, 292-346]

Pads plans to requested size. If the LLM returns fewer tasks than `num_tasks`, generic filler tasks are appended. [FACT: plan_creator.py:184-185]

JSON parsing is naive. Uses `find('{')` and `rfind('}')` to extract JSON from LLM response. Nested JSON in non-plan text could cause misparsing. [FACT: plan_creator.py:279-284]

Uses raw `anthropic_client.messages.create()` directly, NOT the Kosmos provider abstraction. This bypasses caching, cost tracking, and auto-model-selection. [FACT: plan_creator.py:158-162]

Falls back to mock plan on ANY exception. [FACT: plan_creator.py:194-198]

Public API:
- `PlanCreatorAgent.__init__(anthropic_client, model, default_num_tasks=10, temperature=0.7)`: Stores config. No validation. No side effects. [FACT]
- `create_plan(research_objective, context, num_tasks) -> ResearchPlan`: Generates a plan via LLM or mock. `context` dict should contain `cycle` key (defaults to 1). Side effects: Makes LLM API call if client available. Error behavior: Falls back to mock plan on ANY exception. [FACT]
- `revise_plan(original_plan, review_feedback, context) -> ResearchPlan`: Regenerates plan with feedback added to context. Falls back to mock plan (via `create_plan`). [FACT]

**plan_reviewer.py:**

Validates research plans on 5 dimensions (specificity, relevance, novelty, coverage, feasibility) scored 0-10, plus structural requirements, returning an approval/rejection decision with actionable feedback. [FACT: plan_reviewer.py:1-18]

Structural requirements are hard gates independent of scores. A plan must have >= 3 `data_analysis` tasks AND >= 2 different task types AND every task must have `description` and `expected_output`. Even a perfect 10.0 average score fails without these. [FACT: plan_reviewer.py:272-313]

Dimension weights are defined but NOT used. `DIMENSION_WEIGHTS` dict exists (line 69-75) but approval uses simple arithmetic mean. The weights are labeled "not currently used, but available for future." [FACT: plan_reviewer.py:68-69]

Score clamping: LLM-returned scores are clamped to `[0.0, 10.0]`. [FACT: plan_reviewer.py:252-253]

Mock review is intentionally optimistic. When no LLM is available, it returns scores slightly above the 7.0 minimum (base 7.5 if structural requirements pass, 6.0 if not). This means mock plans from PlanCreator that pass structural checks will usually also pass mock review. [FACT: plan_reviewer.py:316-357]

Also uses raw `anthropic_client.messages.create()` directly, bypassing the provider layer. [FACT: plan_reviewer.py:125-129]

Public API:
- `PlanReviewerAgent.review_plan(plan, context) -> PlanReview`: Evaluates plan on 5 dimensions + structural requirements. `plan` must be a dict with `tasks` list. `context` should have `research_objective`. Side effects: Makes LLM API call if client available. Falls back to mock review on ANY exception. [FACT: plan_reviewer.py:161-162]

**delegation.py:**

Executes approved research plans by routing tasks to specialized agents in parallel batches, with retry logic and result aggregation. [FACT: delegation.py:1-12]

Tasks are batched sequentially, not round-robin. Tasks are split into fixed-size batches (default 3) and each batch is executed in parallel via `asyncio.gather`. But batches run sequentially -- batch 2 waits for batch 1 to finish. [FACT: delegation.py:196-219, 161-166]

Retry uses exponential backoff capped at 8 seconds. Delay is `min(2^attempt, 8)` seconds. Max retries defaults to 2 (so up to 3 total attempts). [FACT: delegation.py:343-345, 100]

Non-recoverable `ProviderAPIError` skips retries. If the exception has `is_recoverable() == False`, the retry loop breaks immediately. [FACT: delegation.py:335-337]

Agents are injected via constructor dict. The routing map expects keys: `data_analyst`, `literature_analyzer`, `hypothesis_generator`, `experiment_designer`. Missing agents cause `RuntimeError` with descriptive messages. [FACT: delegation.py:395-399, 434-436, 469-471, 512-516]

All exceptions from `asyncio.gather` are caught because `return_exceptions=True` is used. Individual task exceptions become `TaskResult(status='failed')` rather than aborting the batch. [FACT: delegation.py:247]

The entire method is async (`execute_plan`). The whole delegation pipeline requires an asyncio event loop. [FACT: delegation.py:126]

Public API:
- `DelegationManager.__init__(max_parallel_tasks=3, max_retries=2, task_timeout=300, agents=None)`: Configures execution parameters and agent routing. [FACT]
- `execute_plan(plan, cycle, context) -> Dict` (async): Executes all tasks in the plan in parallel batches. Individual task failures are caught and returned as failed `TaskResult`s. [FACT]

**novelty_detector.py:**

Prevents redundant research tasks across cycles by computing semantic similarity (via sentence-transformers) or token-based Jaccard similarity against an index of past tasks, flagging any task above 75% similarity as redundant. [FACT: novelty_detector.py:1-16]

Graceful fallback to Jaccard similarity. If `sentence-transformers` is not installed, falls back to word-token Jaccard similarity. The flag `use_sentence_transformers` is mutated to `False` on import failure. [FACT: novelty_detector.py:72-85]

Task text format is `"{type}: {description}"`. Both indexing and querying use this concatenation. Type is included in similarity comparison, so a `data_analysis` task will have lower similarity to a `literature_review` task even with identical descriptions. [FACT: novelty_detector.py:100-102, 140-142]

`filter_redundant_tasks` has a copy-restore pattern. It temporarily saves `task_embeddings/task_texts/task_metadata`, indexes seen tasks, checks novelty, then restores the original index. This avoids permanently modifying the index. But it calls `index_past_tasks` which EXTENDS the lists, requiring the copy-restore to prevent side effects. [FACT: novelty_detector.py:320-342]

Top-3 similar tasks are returned only if similarity > 0.6. The `similar_tasks` list in the result filters by a hardcoded 0.6 threshold, even when the novelty threshold is set to 0.75. [FACT: novelty_detector.py:171]

No persistence. The index lives in memory only (`self.task_embeddings`, `self.task_texts`, `self.task_metadata`). If the process restarts, the history is lost. [FACT]

`filter_redundant_tasks` copies Python lists but not the numpy arrays deeply. The `copy()` on a list of numpy arrays produces a shallow copy, which should be safe since `index_past_tasks` extends (appends) rather than mutates, but is worth noting. [FACT: novelty_detector.py:320-342]

Public API:
- `NoveltyDetector.__init__(novelty_threshold=0.75, model_name="all-MiniLM-L6-v2", use_sentence_transformers=True)`: Loads the sentence transformer model or falls back to token-based similarity. Side effects: Downloads model on first use (~90MB for MiniLM). [FACT]
- `index_past_tasks(tasks: List[Dict])`: Computes embeddings for tasks and appends them to the internal index. Side effects: Modifies internal lists. [FACT]
- `check_task_novelty(task: Dict) -> Dict`: Returns novelty assessment with `is_novel` bool, `novelty_score`, `max_similarity`, and `similar_tasks`. No side effects. [FACT]
- `check_plan_novelty(plan: Dict) -> Dict`: Checks novelty of every task in a plan and returns aggregate metrics. No side effects. [FACT]
- `filter_redundant_tasks(tasks, keep_most_novel=True) -> List[Dict]`: Returns only novel tasks from a list. Temporarily modifies then restores internal index. [FACT]

**Reference: StageOrchestratorAgent (kosmos-reference/):**

This is in `kosmos-reference/kosmos-agentic-data-scientist/`, NOT in the Kosmos core package. It is a Google ADK (`google.adk`) agent, not a Kosmos component.

Feeds high-level stages one-at-a-time to an implementation loop, checks success criteria after each stage, and adapts remaining stages through reflection. Exits when all success criteria are met or max iterations (50) reached. [FACT: stage_orchestrator.py:1-7, 248]

Reads `high_level_stages` and `high_level_success_criteria` from session state. [FACT: stage_orchestrator.py:143-144] After each implementation loop, runs manual event compression (threshold=40 events, overlap=20). [FACT: stage_orchestrator.py:366-369] If all stages are completed but criteria are not met, calls the stage_reflector to generate new stages. If reflector fails to produce stages, exits anyway. [FACT: stage_orchestrator.py:283-315] Stage completion is marked AFTER criteria check and reflection, not immediately after implementation. [FACT: stage_orchestrator.py:486] Implementation loop failures cause the stage to be skipped (continue to next iteration). [FACT: stage_orchestrator.py:375-396] Criteria checker and reflector failures are logged but do NOT stop the loop. [FACT: stage_orchestrator.py:429-448, 451-483]

---

### kosmos/knowledge/vector_db.py

Wraps ChromaDB to provide persistent vector storage and cosine-similarity search for scientific papers, handling embedding computation (via SPECTER), batched insertion, metadata extraction, and a singleton access pattern for the database instance. [FACT: vector_db.py:1-5]

**ChromaDB is an optional dependency.** The module catches `ImportError` at import time and sets `HAS_CHROMADB = False`. If ChromaDB is missing, the constructor completes successfully but sets `self.client = None` and `self.collection = None`. All operations then silently return empty results or do nothing. [FACT: vector_db.py:19-27, 62-67]

**Distance-to-similarity conversion assumes cosine distance.** The search methods convert ChromaDB distances to similarity via `1 - distance`. This is only correct for cosine distance, which is configured via `{"hnsw:space": "cosine"}`. If someone changes the distance metric, scores will be wrong. [FACT: vector_db.py:99, 239]

**The singleton is mutable via module-level function.** `get_vector_db()` returns a module-global singleton but allows reconfiguration via `reset=True`. The `reset_vector_db()` function sets the singleton to `None`. There is no thread safety on the global. [FACT: vector_db.py:443-477]

**Title is truncated to 500 chars in metadata.** ChromaDB has metadata size limits, so the title is silently truncated. [FACT: vector_db.py:403]

**Abstract is truncated to 1000 chars in document text.** The stored document is `title [SEP] abstract`, where abstract is capped at 1000 characters. This means long abstracts lose information for search purposes. [FACT: vector_db.py:437-440]

**`search_by_paper` requests `top_k + 1` results** to account for the self-match that will be filtered out. If the paper is not in the DB, the caller gets `top_k + 1` results minus any self-match, which could return `top_k` results (correct) or fewer. [FACT: vector_db.py:275]

**`add_papers` calls `embeddings[i:batch_end].tolist()`**, requiring embeddings to be a numpy array. If a list of arrays is passed (from pre-computed embeddings), the `.tolist()` call on a list slice will fail. [FACT: vector_db.py:176]

**Paper ID format.** Paper IDs are constructed as `"{source}:{primary_identifier}"`. Any code that constructs paper IDs for lookup must use this format. [FACT: vector_db.py:389]

**`[SEP]` separator in documents.** If downstream code parses stored documents, it must know the `[SEP]` format. [FACT: vector_db.py:440]

**`clear()` has no null guard.** If ChromaDB is unavailable, calling `clear()` will raise `AttributeError: 'NoneType' object has no attribute 'delete_collection'`. All other methods check `self.collection is None` but `clear()` does not. [FACT: vector_db.py:370-371]

**The embedder is initialized at `__init__` time.** If the SPECTER model is not downloaded, this triggers a ~440MB download during construction. [FACT: vector_db.py:103]

**Blast radius.** Embedding dimension must match. The embedder (SPECTER, 768-dim) and ChromaDB collection must agree on dimension. Changing the embedder model without resetting the collection causes dimension mismatch errors. [FACT] Persist directory defaults from `config.vector_db.chroma_persist_directory`. Changing the config path means the DB starts empty. [FACT] Singleton consumers: Any code calling `get_vector_db()` shares state. A `reset=True` call affects all callers. [FACT]

**Runtime dependencies.** `chromadb` (optional) -- PersistentClient, Settings, Collection. [FACT: vector_db.py:20-21] `kosmos.knowledge.embeddings.get_embedder()` -- returns a `PaperEmbedder` instance (SPECTER model, 768-dim). Called at init time. [FACT: vector_db.py:103] `kosmos.literature.base_client.PaperMetadata` -- paper model with `.source`, `.primary_identifier`, `.title`, `.abstract`, `.year`, `.citation_count`, `.fields`, `.doi`, `.arxiv_id`, `.pubmed_id`, `.url`. [FACT: vector_db.py:8] `kosmos.config.get_config()` -- for `config.vector_db.chroma_persist_directory`. [FACT: vector_db.py:69] `numpy` -- for embedding arrays. [FACT: vector_db.py:9] Filesystem -- creates persist directory at init via `mkdir(parents=True, exist_ok=True)`. [FACT: vector_db.py:76-77]

**Public API details:**

`PaperVectorDB`:
- `__init__(collection_name="papers", persist_directory=None, reset=False)`: Connects to ChromaDB (persistent client), creates or gets a collection with cosine similarity, initializes the SPECTER embedder. May delete an existing collection if `reset=True`. Side effects: Creates directory on disk. May download ~440MB model. Error behavior: If ChromaDB init fails, logs warning and sets `self.client = None`. [FACT]
- `add_paper(paper, embedding=None)`: Delegates to `add_papers([paper])`. Convenience wrapper. [FACT]
- `add_papers(papers, embeddings=None, batch_size=100)`: Computes embeddings if not provided, then inserts in batches. If `embeddings` is provided, it must be a numpy array. Logs warning if collection unavailable; returns silently. [FACT]
- `search(query, top_k=10, filters=None) -> List[Dict]`: Embeds the query string, queries ChromaDB, returns results with similarity scores. Returns empty list if collection is None. [FACT]
- `search_by_paper(paper, top_k=10, filters=None) -> List[Dict]`: Finds similar papers, excluding the paper itself. Returns empty list if collection unavailable. [FACT]
- `get_paper(paper_id) -> Optional[Dict]`: Retrieves by ID. Returns `None` on any exception. [FACT]
- `delete_paper(paper_id)`: Deletes by ID. Logs error but does not raise. [FACT]
- `count() -> int`: Returns document count. Returns 0 if collection unavailable. [FACT]
- `clear()`: Deletes and recreates the collection. Will raise if `self.client` is None (no guard). [FACT: vector_db.py:370-371]

`get_vector_db(collection_name, persist_directory, reset) -> PaperVectorDB`: Returns module-level singleton. No thread safety. Propagates constructor errors. [FACT]

---

### kosmos/core/workflow.py

Defines the research workflow state machine -- the finite set of states (`WorkflowState`), allowed transitions between them (`ResearchWorkflow`), and the research plan data structure (`ResearchPlan`) that tracks hypotheses, experiments, and results across iterations. [FACT: workflow.py:1-7]

**The state machine is not enforced at the type level.** Callers can read/write `current_state` directly on both `ResearchWorkflow` and `ResearchPlan`. The `transition_to()` method validates transitions, but nothing prevents bypassing it. [FACT: workflow.py:319 sets `self.current_state = target_state`; the attribute is public]

**`ResearchPlan` duplicates state.** `ResearchPlan.current_state` and `ResearchWorkflow.current_state` can diverge if the workflow is modified without going through `transition_to()`. The sync happens inside `transition_to()` at line 323-325: `self.research_plan.current_state = target_state`. [FACT: workflow.py:323-325]

**ID-based tracking only.** `ResearchPlan` stores only string IDs for hypotheses, experiments, and results -- not the actual objects. It has no knowledge of the database. All list operations are ID deduplication checks (`if x not in list`). [FACT: workflow.py:68-78]

**`PAUSED` state can resume to almost any active state.** The transition table allows PAUSED to go to 6 different states, making it a "soft reset" mechanism. [FACT: workflow.py:214-221]

**`CONVERGED` can restart.** `CONVERGED -> GENERATING_HYPOTHESES` is allowed, enabling re-opening of a converged research question. [FACT: workflow.py:212-213]

**Transition logging is config-gated.** `transition_to()` only logs the `[WORKFLOW]` debug line if `config.logging.log_workflow_transitions` is truthy. The config import is wrapped in try/except, so if config is unavailable, transitions proceed silently. [FACT: workflow.py:293-308]

**`use_enum_values=True` on Pydantic models.** `WorkflowTransition` and `ResearchPlan` use `ConfigDict(use_enum_values=True)`, meaning enum fields are stored as their string values, not enum instances. [FACT: workflow.py:48, workflow.py:60] If you serialize and deserialize `ResearchPlan` or `WorkflowTransition`, the enum fields come back as strings, not enum instances. Code doing `==` comparison against enum members still works because `WorkflowState` is a `str` enum, but `isinstance` checks against enum types fail. [FACT: workflow.py:48, 60]

**`get_untested_hypotheses()` is O(n*m).** Uses list comprehension `[h for h in self.hypothesis_pool if h not in self.tested_hypotheses]`. For large pools, this is O(n*m) because `tested_hypotheses` is a list, not a set. The director calls this repeatedly in `decide_next_action()`. [FACT: workflow.py:149-151]

**`PAUSED` has no memory of prior state.** There is no mechanism to remember which state was active before pausing. The caller must decide where to resume. [FACT: workflow.py:214-221]

**Blast radius.** Changing `WorkflowState` enum values: 32 files reference this module. The `ResearchDirectorAgent` makes decisions based on state comparisons. All convergence tests, integration tests, and the CLI `run` command depend on these values. [FACT] Changing `ALLOWED_TRANSITIONS`: Adding or removing allowed transitions changes research flow behavior. Invalid ones raise `ValueError` at runtime. [FACT: workflow.py:280-284] Changing `NextAction` enum: `ResearchDirectorAgent` maps `NextAction` values to handler methods. Adding/removing values requires updating the director's dispatch table. [FACT] Changing `ResearchPlan` fields: The director reads plan fields extensively. Renaming or removing any field breaks the orchestrator. [FACT] Changing `transition_to()` behavior: The director calls this in 12+ places. [FACT]

**Runtime dependencies.** `pydantic` (BaseModel, Field, ConfigDict). [FACT: workflow.py:9-14] `kosmos.config.get_config` (lazy import inside `transition_to()` for log-gating). [FACT: workflow.py:295-296] No LLM, DB, or network dependencies. [FACT]

**Public API details:**

`WorkflowState(str, Enum)`: 9 states: `INITIALIZING`, `GENERATING_HYPOTHESES`, `DESIGNING_EXPERIMENTS`, `EXECUTING`, `ANALYZING`, `REFINING`, `CONVERGED`, `PAUSED`, `ERROR`. [FACT: workflow.py:18-29]

`NextAction(str, Enum)`: 8 actions: `GENERATE_HYPOTHESIS`, `DESIGN_EXPERIMENT`, `EXECUTE_EXPERIMENT`, `ANALYZE_RESULT`, `REFINE_HYPOTHESIS`, `CONVERGE`, `PAUSE`, `ERROR_RECOVERY`. [FACT: workflow.py:32-43]

`WorkflowTransition(BaseModel)`: Records one state transition: `from_state`, `to_state`, `action`, `timestamp`, `metadata`. [FACT: workflow.py:45-54]

`ResearchPlan(BaseModel)`: Tracks the full research state: question, domain, hypothesis pool (IDs), experiment queue (IDs), results (IDs), iteration count, convergence status, timestamps. Required: `research_question`. Mutates internal lists and timestamps. [FACT: workflow.py:57-95]
- `add_hypothesis(hypothesis_id)` / `mark_tested(id)` / `mark_supported(id)` / `mark_rejected(id)`: Append-only ID tracking with deduplication. `mark_supported` and `mark_rejected` both call `mark_tested` internally. [FACT: workflow.py:100-122]
- `add_experiment(protocol_id)` / `mark_experiment_complete(protocol_id)`: `mark_experiment_complete` removes from `experiment_queue` and adds to `completed_experiments`. [FACT: workflow.py:124-136]
- `get_untested_hypotheses() -> List[str]`: Returns `hypothesis_pool` minus `tested_hypotheses`. [FACT: workflow.py:149-151]
- `get_testability_rate() -> float` / `get_support_rate() -> float`: Simple ratio calculations. Return 0.0 on empty denominators. [FACT: workflow.py:153-163]

`ResearchWorkflow`: State machine with transition validation and history tracking. Mutates `current_state`, appends to `transition_history`, syncs `research_plan.current_state`. [FACT: workflow.py:166-416]
- `can_transition_to(target_state) -> bool`: Checks against `ALLOWED_TRANSITIONS` dict. [FACT: workflow.py:247-258]
- `transition_to(target_state, action="", metadata=None) -> bool`: Validates transition, records `WorkflowTransition`, updates state. Raises `ValueError` on invalid transition with allowed transitions listed in the message. Optionally logs via config. [FACT: workflow.py:260-328]
- `reset()`: Returns to `INITIALIZING`, clears history, syncs plan. [FACT: workflow.py:342-349]
- `get_state_duration(state) -> float`: Total seconds spent in a state by scanning transition history. Uses `datetime.utcnow()` for current state duration. [FACT: workflow.py:367-396]
- `get_state_statistics() -> Dict`: Visit counts and durations per state. [FACT: workflow.py:398-416]
- `to_dict() -> Dict`: Exports current state and last 5 transitions. [FACT: workflow.py:351-365]

---

### kosmos/world_model/ (5 modules)

The world model provides a persistent knowledge graph for accumulating research findings across sessions. It uses a Strategy pattern with two implementations (Neo4j-backed and in-memory fallback), a singleton factory, and an Adapter pattern to wrap the pre-existing `KnowledgeGraph` class. The subsystem also includes an `ArtifactStateManager` that adds a JSON-artifact layer on top. Neo4j integration involves Docker auto-start with up to 120 seconds of blocking I/O. [FACT]

**interface.py -- Abstract Interfaces:**

`WorldModelStorage` ABC defines 10 abstract methods: `add_entity`, `get_entity`, `update_entity`, `delete_entity`, `add_relationship`, `get_relationship`, `query_related_entities`, `export_graph`, `import_graph`, `get_statistics`, `reset`, `close`. [FACT: Lines 36-367]

`EntityManager` ABC adds 3 methods for curation (Phase 2): `verify_entity`, `add_annotation`, `get_annotations`. [FACT: Lines 370-433]

`ProvenanceTracker` ABC adds 2 methods for PROV-O tracking (Phase 4): `record_derivation`, `get_provenance`. [FACT: Lines 436-513]

Key design choice: `EntityManager` and `ProvenanceTracker` are separate ABCs, not part of `WorldModelStorage`. This means implementations can choose which interfaces to support. Currently, both `Neo4jWorldModel` and `InMemoryWorldModel` implement `WorldModelStorage` + `EntityManager` but NOT `ProvenanceTracker`. [FACT]

**models.py -- Data Transfer Objects:**

`Entity` dataclass with 10 fields: `type`, `properties`, `id`, `confidence`, `project`, `created_at`, `updated_at`, `created_by`, `verified`, `annotations`. [FACT: Lines 72-458]

`Entity.VALID_TYPES` defines 11 standard types: `Paper`, `Concept`, `Author`, `Experiment`, `Hypothesis`, `Finding`, `Dataset`, `Method`, `ResearchQuestion`, `ExperimentProtocol`, `ExperimentResult`. [FACT: Lines 134-147]

Non-standard entity types trigger `warnings.warn()` but are NOT rejected. This is intentional for extensibility. [FACT: Line 160-166]

`__post_init__` auto-generates UUID if `id` is None, validates confidence range [0.0, 1.0], sets timestamps. [FACT: Lines 149-176]

Factory methods on Entity:
- `from_hypothesis()` (line 183): Converts `kosmos.models.hypothesis.Hypothesis` (Pydantic/SQLAlchemy) to Entity. [FACT]
- `from_protocol()` (line 240): Converts `ExperimentProtocol` to Entity. [FACT]
- `from_result()` (line 287): Converts `ExperimentResult` to Entity. [FACT]
- `from_research_question()` (line 341): Creates Entity from a question string. [FACT]

These factory methods use `getattr()` with defaults extensively (e.g., line 257: `getattr(protocol, 'name', 'unnamed')`) to handle both Pydantic models and SQLAlchemy ORM objects, which have different attribute access patterns. [FACT]

`Relationship` dataclass with 8 fields, 12 valid types (including `SPAWNED_BY`, `TESTS`, `REFINED_FROM` for research workflow), and a `with_provenance()` classmethod that attaches rich metadata. [FACT: Lines 461-667]

**factory.py -- Singleton Factory:**

Module-level singleton: `_world_model: Optional[WorldModelStorage] = None`. [FACT: Lines 52-53]

`get_world_model()` function: Uses lazy `from kosmos.config import get_config` (line 110) to avoid circular imports. Reads `config.world_model.mode` to select implementation. For `mode="simple"`: Creates `Neo4jWorldModel()`, checks `.graph.connected`, falls back to `InMemoryWorldModel` if Neo4j unavailable. For `mode="production"`: Raises `NotImplementedError` (Phase 4 not implemented). [FACT: Lines 55-155]

Docstring explicitly warns "The current implementation is NOT thread-safe." No lock guards `_world_model`. Compare to `core/llm.py:610` which has `_client_lock = threading.Lock()`. [FACT: Line 38]

Fallback mechanism (lines 123-133): Creates `Neo4jWorldModel()`, checks `wm.graph.connected`, falls back to `InMemoryWorldModel` with only a log warning as the signal. A user might not realize they're running without persistence. [FACT]

**simple.py -- Neo4j Adapter:**

Imports `get_knowledge_graph` from `kosmos.knowledge`, creating the critical dependency chain: `get_world_model()` -> `Neo4jWorldModel.__init__()` -> `get_knowledge_graph()` -> `KnowledgeGraph.__init__()` -> Docker auto-start. [FACT: Line 32]

`self.graph = get_knowledge_graph()` -- Uses the SAME singleton as the rest of the knowledge subsystem. This means the world model and the literature knowledge graph share one Neo4j connection. [FACT: Line 89]

`Neo4jWorldModel` inherits from both `WorldModelStorage` AND `EntityManager`, implementing all 13 abstract methods. [FACT: Line 45]

Entity type mapping: For standard types (Paper, Concept, Author, Method), `add_entity()` delegates to the existing `KnowledgeGraph` methods (`create_paper`, `create_concept`, etc.). For other entity types (Hypothesis, Finding, etc.), it creates generic Neo4j nodes directly. This means "Paper" entities go through optimized, indexed pathways while "Hypothesis" entities use raw node creation. [FACT]

**in_memory.py -- Testing/Fallback Implementation:**

Complete implementation of `WorldModelStorage` + `EntityManager` using three dicts: `_entities: Dict[str, Entity]`, `_relationships: Dict[str, Relationship]`, `_annotations: Dict[str, List[Annotation]]`. [FACT: Lines 18-235]

`query_related_entities()` does a linear scan of all relationships. No indexing. This is O(R) where R is relationship count -- acceptable for testing but would be slow at scale. [FACT: Lines 96-122]

`close()` is a no-op. Safe to call multiple times. [FACT: Line 211-213]

**artifacts.py -- Hybrid State Manager:**

`ArtifactStateManager` is a separate system from `WorldModelStorage`. It provides:
- Layer 1: JSON file artifacts in `artifacts/cycle_N/task_M_finding.json`. [FACT]
- Layer 2: Optional knowledge graph integration (takes a `world_model` parameter). [FACT]
- Layer 3: Optional vector store (placeholder, not implemented -- line 567: `pass`). [FACT]
- Layer 4: Citation tracking embedded in findings. [FACT]

Constructor takes optional `world_model` and `vector_store` parameters. These are NOT auto-wired -- callers must explicitly pass them. [FACT: Lines 164-169]

`UpdateType` enum implements the paper's three update categories: `CONFIRMATION`, `CONFLICT`, `PRUNING`. [FACT: Lines 37-47]

`add_finding_with_conflict_check()` implements statistical conflict detection: Checks effect direction contradiction (opposite signs). Checks p-value significance contradiction (significant vs non-significant). Checks hypothesis refutation flag. [FACT: Lines 573-661]

Finding dataclass (lines 51-96): 23 fields including Core (`finding_id`, `cycle`, `task_id`, `summary`, `statistics`), Validation (`scholar_eval`, `null_model_result`, `failure_detection_result`), Provenance (`code_provenance`, `notebook_path`, `figure_paths`), Expert review (`expert_validated`, `validation_accurate`, `validation_notes`). [FACT]

**Two graph systems coexist.** The codebase has two overlapping graph systems: (1) `KnowledgeGraph` (knowledge/graph.py) -- Literature-focused: Papers, Authors, Concepts, Methods. (2) `WorldModelStorage` (world_model/) -- Research-focused: Hypotheses, Findings, Experiments, Protocols. `Neo4jWorldModel` bridges them by wrapping `KnowledgeGraph`, but they maintain separate entity models. `KnowledgeGraph` uses `py2neo.Node` objects; `WorldModelStorage` uses `Entity` dataclasses. The adapter in `simple.py` translates between these representations. [FACT]

**Blast radius and risks:**

No thread safety on world model singleton: Unlike `get_client()` which uses `threading.Lock()`, `get_world_model()` has no synchronization. Concurrent access could create multiple instances. [FACT]

Silent fallback to in-memory: If Neo4j is down, the system silently switches to `InMemoryWorldModel`. All data from that session is lost on restart. Only a log warning signals this. [FACT]

Vector store Layer 3 not implemented: `ArtifactStateManager._index_finding_to_vectors()` at line 560-567 is a stub (`pass`). Semantic search over findings is not available. [FACT]

`reset_knowledge_graph()` doesn't close: Unlike `reset_world_model()` which calls `.close()` before clearing, `reset_knowledge_graph()` just sets the global to None, potentially leaking the Neo4j connection. [FACT]

Entity type bifurcation: Standard types (Paper, Concept, Author, Method) go through optimized `KnowledgeGraph` methods with proper indexing. Research types (Hypothesis, Finding, etc.) use raw Neo4j node creation without dedicated indexes, potentially slower for queries. [FACT]
# Key Interfaces

## Interface Index

| Module | Class / Function | Primary Role |
|--------|-----------------|--------------|
| `kosmos/agents/research_director.py` | `ResearchDirectorAgent(BaseAgent)` | Master orchestrator for autonomous research |
| `kosmos/core/llm.py` | `ClaudeClient` | Anthropic SDK wrapper with caching and auto-model |
| `kosmos/core/llm.py` | `ModelComplexity` | Static prompt complexity estimator |
| `kosmos/core/llm.py` | `get_client()` | Thread-safe LLM singleton accessor |
| `kosmos/core/llm.py` | `get_provider()` | Typed LLMProvider accessor |
| `kosmos/execution/executor.py` | `CodeExecutor` | Sandboxed code execution with retry |
| `kosmos/execution/executor.py` | `ExecutionResult` | Execution outcome data container |
| `kosmos/execution/executor.py` | `RetryStrategy` | Self-correcting code repair on failure |
| `kosmos/execution/executor.py` | `execute_protocol_code()` | Convenience function: validate + execute |
| `kosmos/execution/code_generator.py` | `ExperimentCodeGenerator` | Hybrid template + LLM code generation |
| `kosmos/execution/code_generator.py` | `CodeTemplate` | Base class for experiment templates |
| `kosmos/execution/code_generator.py` | `TTestComparisonCodeTemplate` | T-test experiment code template |
| `kosmos/execution/code_generator.py` | `CorrelationAnalysisCodeTemplate` | Correlation analysis code template |
| `kosmos/execution/code_generator.py` | `LogLogScalingCodeTemplate` | Power-law / log-log code template |
| `kosmos/execution/code_generator.py` | `MLExperimentCodeTemplate` | ML classification pipeline template |
| `kosmos/execution/code_generator.py` | `GenericComputationalCodeTemplate` | Catch-all computational template |
| `kosmos/safety/code_validator.py` | `CodeValidator` | Safety, security, and ethical code validation |
| `kosmos/core/workflow.py` | `WorkflowState(str, Enum)` | 9-state workflow enum |
| `kosmos/core/workflow.py` | `NextAction(str, Enum)` | 8-action decision enum |
| `kosmos/core/workflow.py` | `WorkflowTransition(BaseModel)` | State transition record |
| `kosmos/core/workflow.py` | `ResearchPlan(BaseModel)` | Research state tracker (ID-based) |
| `kosmos/core/workflow.py` | `ResearchWorkflow` | State machine with transition validation |
| `kosmos/literature/base_client.py` | `PaperSource(str, Enum)` | Literature source identifier |
| `kosmos/literature/base_client.py` | `Author` (dataclass) | Paper author representation |
| `kosmos/literature/base_client.py` | `PaperMetadata` (dataclass) | Unified paper representation |
| `kosmos/literature/base_client.py` | `BaseLiteratureClient(ABC)` | Abstract literature API client |
| `kosmos/core/providers/base.py` | `Message` (dataclass) | LLM conversation message |
| `kosmos/core/providers/base.py` | `UsageStats` (dataclass) | Token/cost usage record |
| `kosmos/core/providers/base.py` | `LLMResponse` (dataclass) | LLM response with string compatibility |
| `kosmos/core/providers/base.py` | `LLMProvider(ABC)` | Abstract LLM provider interface |
| `kosmos/core/providers/base.py` | `ProviderAPIError(Exception)` | Provider error with recoverability |
| `kosmos/orchestration/plan_creator.py` | `PlanCreatorAgent` | Strategic research plan generator |
| `kosmos/orchestration/plan_reviewer.py` | `PlanReviewerAgent` | Plan validation on 5 dimensions |
| `kosmos/orchestration/delegation.py` | `DelegationManager` | Parallel task delegation to agents |
| `kosmos/orchestration/novelty_detector.py` | `NoveltyDetector` | Semantic redundancy filtering |
| `kosmos/agents/base.py` | `BaseAgent` / `AgentMessage` / `MessageType` | Agent base class and message protocol |
| `kosmos/agents/registry.py` | `AgentRegistry` | Agent message routing (dormant) |
| `kosmos/db/__init__.py` | `get_session()` | SQLAlchemy session context manager |
| `kosmos/world_model/factory.py` | `get_world_model()` | World model singleton with fallback |
| `kosmos/world_model/interface.py` | `WorldModelStorage(ABC)` | CRUD for entities and relationships |
| `kosmos/world_model/artifacts.py` | `ArtifactStateManager` | 4-layer hybrid JSON + graph storage |
| `kosmos/core/async_llm.py` | `AsyncLLMClient` | Async LLM with circuit breaker |
| `kosmos/core/async_llm.py` | `CircuitBreaker` | Three-state circuit breaker |

---

## Full Interface Specifications

---

### `kosmos/agents/research_director.py`

```python
# kosmos/agents/research_director.py
class ResearchDirectorAgent(BaseAgent):
    def __init__(self, research_question, domain=None, agent_id=None, config=None): ...
        # Master orchestrator init: workflow, research plan, LLM client, convergence detector,
        # rollout tracker, optional parallel executor, optional async LLM, world model entity.
    async def execute(self, task: Dict) -> Dict: ...
        # Main entry point. Supports "start_research" and "step" actions.
    def execute_sync(self, task: Dict) -> Dict: ...
        # Synchronous wrapper: tries running loop first, falls back to asyncio.run().
    def decide_next_action(self) -> NextAction: ...
        # State-machine decision tree. Checks budget, runtime, iteration, convergence, then routes on workflow state.
    def process_message(self, message: AgentMessage): ...
        # Routes incoming messages to type-specific handlers based on metadata["agent_type"].
    def get_research_status(self) -> Dict: ...
        # Returns comprehensive status: question, domain, state, iteration, convergence, counts, strategy, rollouts.
    def generate_research_plan(self) -> str: ...
        # Uses LLM to generate initial research strategy. Stores in research_plan.initial_strategy.
    def register_agent(self, agent_type, agent_id): ...
        # Agent registry for coordination. In practice, unused by direct-call pattern (Issue #76).
    def get_agent_id(self, agent_type) -> Optional[str]: ...
        # Retrieves registered agent ID by type. Unused in active code path.
    def execute_experiments_batch(self, protocol_ids) -> List[Dict]: ...
        # Parallel experiment execution. Falls back to sequential if parallel executor not available.
    async def evaluate_hypotheses_concurrently(self, hypothesis_ids) -> List[Dict]: ...
        # Concurrent LLM-based hypothesis evaluation. Requires async LLM client.
    async def analyze_results_concurrently(self, result_ids) -> List[Dict]: ...
        # Concurrent LLM-based result analysis. Requires async LLM client.
```

**Initialization requirements**: `research_question` is required. Database must be initializable. `ANTHROPIC_API_KEY` must be set for LLM client. The constructor does a LOT: database initialization, world model entity creation, skill loading, convergence detector setup, optional parallel executor and async LLM client initialization. Any of these can fail independently, and failures are caught-and-logged rather than raised. [FACT: research_director.py:68-260]

**Dual locking strategy**: Both `asyncio.Lock` and `threading.RLock/Lock` are maintained. The async locks (`_research_plan_lock`, `_strategy_stats_lock`, `_workflow_lock`, `_agent_registry_lock`) are used in async code paths, the threading locks in sync context managers. [FACT: research_director.py:192-200]

**Lazy agent initialization**: Sub-agents (`_hypothesis_agent`, `_experiment_designer`, `_code_generator`, `_code_executor`, `_data_provider`, `_data_analyst`, `_hypothesis_refiner`) are `None` at init and created on first use via lazy-init in the `_handle_*_action()` methods. [FACT: research_director.py:145-152]

**`execute()` side effects**: Raises `ValueError` for unknown actions. Returns dict with keys `status`, `research_plan`, `next_action`, `workflow_state`. The `execute_sync()` wrapper tries to use running event loop first, falls back to `asyncio.run()`. [FACT: research_director.py:2868-2909, 2911-2920]

**`decide_next_action()` side effects**: Increments `_actions_this_iteration`. May transition to CONVERGED if budget/runtime exceeded. Checks budget via `kosmos.core.metrics.get_metrics().enforce_budget()` on every call. If the module is not available, it silently continues. `_actions_this_iteration` is lazily initialized via `hasattr` check instead of `__init__`. [FACT: research_director.py:2388-2548, 2405-2425, 2451-2452]

**Infinite loop guard**: `MAX_ACTIONS_PER_ITERATION = 50` (module constant). If the `_actions_this_iteration` counter exceeds this, `decide_next_action()` forces `NextAction.CONVERGE`. [FACT: research_director.py:50, 2455-2461]

**Circuit breaker**: `MAX_CONSECUTIVE_ERRORS = 3`. After 3 consecutive failures, the workflow transitions to `ERROR` state. [FACT: research_director.py:45, 649-662]

**Knowledge graph persistence**: 4 separate graph persistence methods: `_persist_hypothesis_to_graph`, `_persist_protocol_to_graph`, `_persist_result_to_graph`, `_add_support_relationship`. Each opens a new DB session, fetches the entity, converts to a `world_model.Entity`, and creates relationships. All are fire-and-forget (catch-and-log exceptions). World model is optional: if `get_world_model()` fails, `self.wm = None` and all graph operations silently no-op. [FACT: research_director.py:388-562, 242-255]

**`_handle_execute_experiment_action`**: The most complex handler. Loads protocol from DB, generates code via `ExperimentCodeGenerator`, executes via `CodeExecutor`, sanitizes results for JSON serialization (handling numpy types), and stores results in DB. JSON sanitization is inline via a nested `_json_safe()` function that handles numpy types and non-serializable objects by converting to string. [FACT: research_director.py:1521-1664, 1595-1613]

**Architecture duality (Issue #76)**: Two coordination mechanisms coexist. The module has both message-based `_send_to_*` methods (async, using `self.send_message()`) AND direct-call `_handle_*_action()` methods. Issue #76 revealed that message-based coordination silently failed because agents were never registered in the message router. The direct-call methods are the ones actually used. The `_send_to_*` methods are kept but effectively dead code. `_send_to_convergence_detector` is explicitly deprecated: it now just calls `_handle_convergence_action()` and returns a dummy message. [FACT: research_director.py:1039-1219 (message-based), 1391-1979 (direct-call), 1981-2003]

**`execute_experiments_batch()`**: The sequential fallback calls `asyncio.get_event_loop().run_until_complete()` which will raise `RuntimeError` if an event loop is already running (e.g., during async execution). This path is only taken when concurrent execution is disabled. [FACT: research_director.py:2171-2174]

**Blast radius**: Changing `__init__` signature breaks CLI `run` command, integration tests, e2e tests, and evaluation scripts. Key consumers: `kosmos/cli/commands/run.py`, `kosmos/__init__.py`, 12+ test files, `evaluation/scientific_evaluation.py`. Changing `execute()` return type breaks `execute_sync()` wrapper, CLI, and tests which depend on return dict shape. Changing `get_research_status()` return shape breaks test assertions and reporting. Changing message handler contracts breaks the `_handle_*_response()` methods which expect specific `content` dict shapes. Changing `decide_next_action()` logic alters research flow for all users.

---

### `kosmos/core/llm.py`

```python
# kosmos/core/llm.py
class ModelComplexity:
    @staticmethod
    def estimate_complexity(prompt, system=None) -> Dict: ...
        # Returns complexity_score (0-100), total_tokens_estimate, keyword_matches, recommendation, reason.

class ClaudeClient:
    def __init__(self, api_key=None, model=None, enable_cache=True, enable_auto_model_selection=False): ...
        # Wraps Anthropic SDK. Creates ClaudeCache on init. Mutates internal counters on every call.
    def generate(self, prompt, system=None, max_tokens=4096, temperature=0.7,
                 stop_sequences=None, bypass_cache=False, model_override=None) -> str: ...
        # Returns generated text. Checks cache first (unless bypass_cache=True). Logs warning on max_tokens truncation.
    def generate_with_messages(self, messages, system=None, max_tokens=4096, temperature=0.7) -> str: ...
        # Multi-turn conversation. Does NOT use cache. Does NOT support auto model selection (always uses self.model).
    def generate_structured(self, prompt, output_schema=None, system=None, max_tokens=4096,
                           temperature=0.0, max_retries=2, schema=None) -> Dict: ...
        # Retries up to max_retries+1 attempts. Appends JSON schema to system prompt. schema is alias for output_schema.
    def get_usage_stats(self) -> Dict: ...
        # Returns requests, tokens, cost, cache metrics, model selection stats. Cost is $0.00 in CLI mode.
    def reset_stats(self): ...
        # Zeroes all counters.

def get_client(reset=False, use_provider_system=True) -> Union[ClaudeClient, LLMProvider]: ...
    # Thread-safe singleton accessor. With use_provider_system=True, returns LLMProvider. Falls back to AnthropicProvider.
def get_provider() -> LLMProvider: ...
    # Calls get_client(use_provider_system=True) and asserts result is LLMProvider. Raises TypeError if not.
```

**`ModelComplexity` behavior**: Static utility that scores prompt complexity (0-100) using token count and keyword matching, then recommends "haiku" or "sonnet". Auto model selection never picks higher than Sonnet: `estimate_complexity()` returns "haiku" for scores <30 and "sonnet" for everything else (both moderate and high). The "high complexity" path also maps to "sonnet". No preconditions, no side effects, no exceptions. [FACT: llm.py:52-105, 88-94]

**`ClaudeClient` preconditions**: `anthropic` package must be installed. `ANTHROPIC_API_KEY` env var or `api_key` param required. `__init__` raises `ImportError` if `anthropic` not installed, `ValueError` if no API key. [FACT: llm.py:154-165]

**CLI mode detection**: `self.is_cli_mode = self.api_key.replace('9', '') == ''` -- any API key consisting entirely of 9s triggers CLI routing through the Anthropic SDK. This is undocumented externally and silently changes cost tracking behavior (CLI mode returns $0.00 cost). An empty string API key would also match as CLI mode, but the `ValueError` at line 163 prevents this in practice. [FACT: llm.py:179, 587-588]

**Auto model selection disabled in CLI mode**: The condition is `self.enable_auto_model_selection and not self.is_cli_mode`. [FACT: llm.py:251]

**Cache behavior**: `generate()` checks cache first. `generate_with_messages()` does NOT use the cache: unlike `generate()`, multi-turn messages bypass caching entirely. `generate_structured()` bypasses cache on retry: `bypass_cache=attempt > 0`, so retries after JSON parse failures always hit the API. [FACT: llm.py:207-365, 367-408, 467]

**`generate_with_messages()` uses `self.model` directly**, ignoring `self.default_model` and auto-selection. If the caller previously changed `self.model`, this persists. [FACT: llm.py:389]

**`generate_structured()` retry behavior**: Retries up to `max_retries+1` total attempts. Appends JSON schema to system prompt. Uses `parse_json_response()` for robust parsing. Raises `ProviderAPIError` on exhaustion. The schema instruction is always added even if the original system prompt already contains JSON instructions. [FACT: llm.py:410-486, 456]

**Cost estimation**: `get_usage_stats()` hardcodes `"claude-sonnet-4-5"` model name for cost lookup regardless of what model was actually used. [FACT: llm.py:519]

**`get_client()` singleton behavior**: Thread-safe via double-checked locking. The fast-path check runs outside the lock, then re-checks inside. The singleton is module-global (`_default_client` is `Optional[Union[ClaudeClient, LLMProvider]]`), so `reset=True` from any thread replaces the client for all threads. With `use_provider_system=True` (default), returns an `LLMProvider` from config. Falls back to `AnthropicProvider` if config fails. With `use_provider_system=False`, returns a `ClaudeClient`. [FACT: llm.py:609, 613-679, 643-649]

**`get_provider()` assertion**: Calls `get_client(use_provider_system=True)` and asserts the result is an `LLMProvider`. Raises `TypeError` if the singleton is a `ClaudeClient` instead of `LLMProvider`. [FACT: llm.py:682-706]

**Blast radius**: Changing `get_client()` breaks 27+ Python importers. Changing `generate()` signature breaks all callers depending on kwargs `prompt`, `system`, `max_tokens`, `temperature`, `bypass_cache`, `model_override`. Changing `generate_structured()` error behavior (currently raises `ProviderAPIError` after exhausting retries) breaks error handling in callers. Changing the singleton pattern breaks concurrent agent workflows.

---

### `kosmos/execution/executor.py`

```python
# kosmos/execution/executor.py
class ExecutionResult:
    def __init__(self, success, return_value=None, stdout="", stderr="", error=None,
                 error_type=None, execution_time=0.0, profile_result=None, data_source=None): ...
        # Data container for execution outcomes.
    def to_dict(self) -> Dict: ...
        # Serializes to dict. Includes profile_data if available, with silent fallback on serialization failure.

class CodeExecutor:
    def __init__(self, max_retries=3, retry_delay=1.0, allowed_globals=None, use_sandbox=False,
                 sandbox_config=None, enable_profiling=False, profiling_mode="basic",
                 test_determinism=False, execution_timeout=300): ...
        # Creates RetryStrategy, optionally creates DockerSandbox and RExecutor. Logs warnings if unavailable.
    def execute(self, code, local_vars=None, retry_on_error=True, llm_client=None, language="python") -> ExecutionResult: ...
        # Main entry. Auto-detects language. For Python: _execute_once() in retry loop with code modification on failure.
    def execute_r(self, code, capture_results=True, output_dir=None) -> ExecutionResult: ...
        # Explicit R execution. Returns failure result if R unavailable.
    def is_r_available(self) -> bool: ...
        # Checks R availability. Pure query.
    def get_r_version(self) -> Optional[str]: ...
        # Returns R version string or None. Pure query.
    def execute_with_data(self, code, data_path, retry_on_error=True) -> ExecutionResult: ...
        # Wraps execute() with data_path injection (prepended to code AND passed as local var).

class RetryStrategy:
    def __init__(self, max_retries=3, base_delay=1.0): ...
        # Initializes with repair statistics tracking dict.
    def should_retry(self, attempt, error_type) -> bool: ...
        # Returns False for SyntaxError, FileNotFoundError, DataUnavailableError. Returns False if attempts exceeded.
    def get_delay(self, attempt) -> float: ...
        # Exponential backoff: base_delay * 2^(attempt-1).
    def record_repair_attempt(self, error_type, success): ...
        # Tracks per-error-type success/failure counts. Mutates self.repair_stats.
    def modify_code_for_retry(self, original_code, error, error_type, traceback_str, attempt, llm_client=None) -> Optional[str]: ...
        # Dispatches to error-type-specific fixers. Tries LLM first (attempts 1-2 only), then pattern-based.
        # Handles 11 error types: KeyError, FileNotFoundError, NameError, TypeError, IndexError,
        # AttributeError, ValueError, ZeroDivisionError, ImportError/ModuleNotFoundError, PermissionError, MemoryError.

def execute_protocol_code(code, data_path=None, max_retries=3, use_sandbox=False, sandbox_config=None) -> Dict: ...
    # Convenience function. Always validates safety first via CodeValidator. Creates fresh CodeExecutor per call.
```

**Restricted builtins sandbox**: When Docker sandbox is unavailable, the executor replaces `__builtins__` with `SAFE_BUILTINS` (lines 43-83) -- a whitelist of ~80 safe builtins. A custom `_make_restricted_import()` (lines 97-110) limits `import` to ~30 scientific/stdlib modules. This is NOT process isolation -- the code still runs in the same Python process. [FACT: executor.py:43-94, 589-597]

**Return value extraction by convention**: `_execute_once()` looks for a variable named `results` or `result` in the exec'd code's local namespace (line 516). All code templates MUST assign to `results` for the executor to capture output. If generated code does not assign to `results` or `result`, `return_value` will be `None` even on successful execution. [FACT: executor.py:516]

**Docker sandbox fallback is silent**: If `use_sandbox=True` but Docker is not installed, the executor sets `self.use_sandbox = False` and continues with restricted builtins only. No error is raised. [FACT: executor.py:216-220]

**Timeout implementation is platform-dependent**: On Unix, uses `signal.SIGALRM` (same-thread, clean). On Windows, uses `ThreadPoolExecutor` with 1 worker. The thread-based approach on Windows cannot actually kill a stuck computation -- it only stops waiting for it. The thread continues executing. [FACT: executor.py:600-630]

**`execute_with_data()` double injection**: Prepends `data_path = repr(path)` to the code string AND passes it as a local variable. This ensures templates that use either `data_path` as a global or local will find it. [FACT: executor.py:653-660]

**Re-export of CodeValidator**: Line 664 does `from kosmos.safety.code_validator import CodeValidator` at module level. Code that does `from kosmos.execution.executor import CodeValidator` works but is an indirect import path. Comment says "F-22: removed duplicate". [FACT: executor.py:663-664]

**RetryStrategy wraps entire code in try/except**: Most fix methods (e.g., `_fix_key_error`, `_fix_type_error`) wrap the ENTIRE original code in a try/except block. This masks the original error and produces a `results = {'error': ..., 'status': 'failed'}` dict. The experiment appears to "succeed" (no exception) but with a failure result. Callers must check `result.return_value` for `{'status': 'failed'}` in addition to `result.success`. [FACT: executor.py:869-877]

**FileNotFoundError is explicitly terminal**: `_fix_file_not_found()` returns `None`, and `should_retry()` lists FileNotFoundError as non-retryable. This is an intentional Issue #51 fix -- missing data files should trigger synthetic data generation in templates, not retry loops. [FACT: executor.py:726, 879-906]

**LLM repair only on first 2 attempts**: `modify_code_for_retry()` only tries LLM-based repair when `attempt <= 2`. Subsequent attempts use pattern-based fixes only. [FACT: executor.py:779]

**`execute_protocol_code()` always validates safety**: The convenience function always runs `CodeValidator.validate()` before execution. The comment "F-21: removed validate_safety bypass" indicates a previous version had a way to skip validation that was deliberately removed. [FACT: executor.py:1039-1048]

**`execute()` error behavior**: Returns `ExecutionResult(success=False)` rather than raising. Side effects: `time.sleep()` between retries, logging, optional determinism check. The retry loop calls `time.sleep()` synchronously, blocking the calling thread. In async contexts this blocks the event loop. [FACT: executor.py:237-376, 335]

**Security note on restricted builtins**: The restricted builtins include `hasattr` but NOT `getattr`/`setattr`/`delattr`. However, `type` and `object` ARE included, which can be used to bypass restrictions via `type.__getattribute__`. [FACT: executor.py:594-597]

**Blast radius**: `CodeExecutor` is used by `research_director.py` (line 1529) for all experiment execution. `ExecutionResult` is consumed by the entire results pipeline. `SAFE_BUILTINS` and `_ALLOWED_MODULES` define the security boundary. `execute_protocol_code()` is called by `parallel.py:290`. `RetryStrategy.COMMON_IMPORTS` dict determines auto-fix capability. Changing `DEFAULT_EXECUTION_TIMEOUT` (300s) affects all unsandboxed executions.

---

### `kosmos/execution/code_generator.py`

```python
# kosmos/execution/code_generator.py
class CodeTemplate:
    def __init__(self, name, experiment_type): ...  # Base template with name and type.
    def matches(self, protocol) -> bool: ...         # Default: checks protocol.experiment_type == self.experiment_type.
    def generate(self, protocol) -> str: ...         # Raises NotImplementedError. Subclasses must override.

class TTestComparisonCodeTemplate(CodeTemplate):
    def matches(self, protocol) -> bool: ...  # True for DATA_ANALYSIS type with t-test in statistical_tests.
    def generate(self, protocol) -> str: ...  # T-test code: synthetic data fallback, Shapiro, Levene, DataAnalyzer.ttest_comparison().

class CorrelationAnalysisCodeTemplate(CodeTemplate):
    def matches(self, protocol) -> bool: ...  # Matches DATA_ANALYSIS with correlation/regression in tests or name.
    def generate(self, protocol) -> str: ...  # Pearson+Spearman, picks "best" method by p-value, scatter with regression.

class LogLogScalingCodeTemplate(CodeTemplate):
    def matches(self, protocol) -> bool: ...  # Keyword match on "scaling", "power law", "log-log" in name/description.
    def generate(self, protocol) -> str: ...  # Power-law fitting with log-log plot, DataCleaner.filter_positive().

class MLExperimentCodeTemplate(CodeTemplate):
    def matches(self, protocol) -> bool: ...  # Keyword match on ML terms in name/description.
    def generate(self, protocol) -> str: ...  # Sklearn classification pipeline: train/test split, cross-validation, MLAnalyzer.

class GenericComputationalCodeTemplate(CodeTemplate):
    def matches(self, protocol) -> bool: ...  # Matches COMPUTATIONAL or DATA_ANALYSIS (catch-all).
    def generate(self, protocol) -> str: ...  # Descriptive stats, correlation, nonlinear curve fitting, linear regression, scatter.

class ExperimentCodeGenerator:
    def __init__(self, use_templates=True, use_llm=True, llm_enhance_templates=False, llm_client=None): ...
        # Template registration and LLM client with double fallback.
    def generate(self, protocol) -> str: ...
        # Hybrid: template match -> LLM generation -> basic fallback. Always validates syntax. Raises ValueError on syntax error.
    def save_code(self, code, file_path): ...  # Writes code string to file.
```

**Template priority order matters**: Templates are matched in registration order. `GenericComputationalCodeTemplate` is registered LAST and matches both `COMPUTATIONAL` and `DATA_ANALYSIS` types. If a more specific template (t-test, correlation) does not match, the generic catches everything. A protocol that is `DATA_ANALYSIS` type with "scaling" in the name would match `LogLogScalingCodeTemplate` first (checked before generic), but a `DATA_ANALYSIS` protocol with no distinguishing keywords falls through to generic. Template matching is order-dependent with no priority scoring. The first match wins. [FACT: code_generator.py:787-793, 559-564]

**All templates generate synthetic data fallback**: Every template checks `if 'data_path' in dir() and data_path:` to try loading real data, then falls through to synthetic data generation with `np.random.seed()` (Issue #51 fix). This means experiments can run without any input data files. [FACT: code_generator.py:112-130, 243-259, 381-397, 474-488, 590-608]

**Generated code uses `dir()` for variable detection**: Templates check `if 'data_path' in dir()` and `if 'figure_path' in dir()` rather than using try/except or checking locals/globals. This pattern works because `dir()` in exec'd code returns local scope names. [FACT: code_generator.py:112, 169]

**LLM client initialization has double fallback**: `ExperimentCodeGenerator.__init__` tries `ClaudeClient()` first, catches failure, then tries `LiteLLMProvider` as fallback. If both fail, LLM generation is silently disabled (`self.use_llm = False`). No exception is raised. [FACT: code_generator.py:762-778]

**Template code is NOT validated for safety**: The `generate()` method only calls `_validate_syntax()` (AST parse check) on the output. It does NOT run `CodeValidator` -- that happens later in the executor. Templates can contain imports of internal Kosmos modules. [FACT: code_generator.py:831, 981-989]

**`_generate_basic_template` hardcodes `data_path`**: The fallback template uses `pd.read_csv(data_path)` without the synthetic data fallback. If `data_path` is undefined, this will raise `NameError`. This is the ONLY template without synthetic data support. [FACT: code_generator.py:954-977]

**Protocol `random_seed` gotcha**: Templates extract `getattr(protocol, 'random_seed', 42) or 42`. The `or 42` guard means a `random_seed=0` would be overridden to 42 (since 0 is falsy). Zero is a valid seed but treated as falsy. [FACT: code_generator.py:89, 231, 368, 572]

**`_validate_syntax` raises ValueError, not SyntaxError**: On syntax failure, it wraps the SyntaxError in a ValueError. This changes the exception type for callers. [FACT: code_generator.py:988-989]

**Effect size influences synthetic data**: The t-test template reads `expected_effect_size` from the protocol's first statistical test and uses it as the mean shift in synthetic data generation. Synthetic experiments can simulate null (effect_size=0) or non-null hypotheses. [FACT: code_generator.py:93-97, 124]

**`_extract_code_from_response` weak heuristic**: If the LLM response contains no code fences, it checks for "import", "def ", or "=" to decide if it's code. A natural language response containing "=" would be treated as code. [FACT: code_generator.py:907-924]

**Blast radius**: `ExperimentCodeGenerator.generate()` is called by `research_director.py:1528` for every experiment. Generated code must assign to `results` variable -- the executor extracts return values by that name. Templates import from `kosmos.execution.data_analysis.DataAnalyzer`, `kosmos.execution.ml_experiments.MLAnalyzer`, and `kosmos.analysis.visualization.PublicationVisualizer`. The synthetic data patterns are used for testing and demo -- changing seeds or distributions changes expected test outputs.

---

### `kosmos/safety/code_validator.py`

```python
# kosmos/safety/code_validator.py
class CodeValidator:
    def __init__(self, ethical_guidelines_path=None, allow_file_read=True,
                 allow_file_write=False, allow_network=False): ...
        # Loads ethical guidelines from JSON or defaults. Logs configuration.
    def validate(self, code, context=None) -> SafetyReport: ...
        # Runs 6 checks: syntax, dangerous imports, dangerous patterns, network, AST calls, ethical guidelines.
        # passed is True only if zero violations (warnings ignored).
    def requires_approval(self, report) -> bool: ...
        # True if: config mandates approval, OR risk HIGH/CRITICAL, OR critical violations, OR ethical violations.
    def create_approval_request(self, code, report, context=None) -> ApprovalRequest: ...
        # Creates ApprovalRequest with truncated code (500 chars), violation list, and risk level.
```

**`validate()` runs 6 checks in sequence**: `_check_syntax` (AST parse, severity HIGH), `_check_dangerous_imports` (AST-based with string fallback, severity CRITICAL), `_check_dangerous_patterns` (string-based `if pattern in code`, severity CRITICAL), `_check_network_operations` (string-based case-insensitive, warnings only if `allow_network=False`), `_check_ast_calls` (AST walk for `getattr`/`setattr`/`delattr` and dunder attributes, severity CRITICAL), `_check_ethical_guidelines` (keyword matching against code+context, severity from guideline). `passed` is True only if zero violations. [FACT: code_validator.py:159-231]

**`os` is on the dangerous list**: The validator flags `import os` as CRITICAL. The executor's `_ALLOWED_MODULES` set also does not include `os`. However, the RetryStrategy's `COMMON_IMPORTS` dict DOES include `'os': 'import os'`. This means auto-fix can insert an `import os` that the validator would reject. [FACT: code_validator.py:36, executor.py:686]

**Ethical checks are keyword-based with high false-positive risk**: Keywords like "email", "password", "survey", "harm" in the code OR context description trigger ethical violations. Scientific code analyzing email metadata, password-strength algorithms, or harm-reduction studies would trigger these. The default ethical guideline keywords include common words that trigger false positives in legitimate scientific code. A bioinformatics experiment analyzing "harmful mutations" would trigger the "no_harm" guideline. [FACT: code_validator.py:118-119, 395-418]

**Pattern checking uses raw string matching, not AST**: `_check_dangerous_patterns()` uses `if pattern in code:`. Commented-out code like `# eval(` or strings containing `'eval('` trigger violations. [FACT: code_validator.py:288]

**`open(` write mode detection is fragile**: Checks for `"'w'"`, `"'a'"`, `"'x'"`, `"mode='w'"`, `'mode="w"'` as substrings. Misses `mode='a'`, `mode='x'`, `'wb'`, `'ab'`, or variable-based modes like `open(f, mode)`. Code using `open(f, 'wb')` would pass the write check when `allow_file_read=True`. [FACT: code_validator.py:296-297]

**AST is parsed up to 3 times**: `_check_syntax()` parses with `ast.parse()`, `_check_dangerous_imports()` parses again, and `_check_ast_calls()` parses a third time. Each parse independently. If syntax check fails, the import check falls back to string matching. [FACT: code_validator.py:237, 252, 332]

**`getattr` is flagged as dangerous**: The AST call checker flags `getattr()` as CRITICAL. This is a commonly-used Python built-in, so any generated code using `getattr(obj, 'attr', default)` will fail validation. [FACT: code_validator.py:338]

**`requires_approval()` depends on global config**: Reads `config.safety.require_human_approval` from `get_config()`. If that config flag is True, ALL code requires approval regardless of risk level. [FACT: code_validator.py:447-449]

**Approval request truncates code to 500 chars**: `create_approval_request()` stores only `code[:500]` in the context dict. Long code is not fully visible in the approval request. Dangerous patterns at character 501+ are not visible to the human reviewer. [FACT: code_validator.py:510]

**Ethical guideline `break` after first keyword match**: The inner loop breaks after the first keyword match per guideline. Only one violation is reported per guideline even if multiple keywords match. [FACT: code_validator.py:417]

**`_assess_risk_level`**: Returns the highest severity found among violations. Returns `RiskLevel.LOW` if no violations. [FACT: code_validator.py:420-434]

**Blast radius**: `CodeValidator.validate()` is called by `execute_protocol_code()` in executor.py and by `guardrails.py`. It gates ALL code execution. `SafetyReport` is the return type for pass/fail decisions. `DANGEROUS_MODULES` determines import blocks. `DANGEROUS_PATTERNS` interacts with `allow_file_read`/`allow_file_write` flags. Ethical guidelines affect approval requirements.

---

### `kosmos/core/workflow.py`

```python
# kosmos/core/workflow.py
class WorkflowState(str, Enum):
    # 9 states: INITIALIZING, GENERATING_HYPOTHESES, DESIGNING_EXPERIMENTS, EXECUTING,
    # ANALYZING, REFINING, CONVERGED, PAUSED, ERROR

class NextAction(str, Enum):
    # 8 actions: GENERATE_HYPOTHESIS, DESIGN_EXPERIMENT, EXECUTE_EXPERIMENT, ANALYZE_RESULT,
    # REFINE_HYPOTHESIS, CONVERGE, PAUSE, ERROR_RECOVERY

class WorkflowTransition(BaseModel):
    # Records one state transition: from_state, to_state, action, timestamp, metadata.
    # ConfigDict(use_enum_values=True) -- enum fields stored as string values, not enum instances.

class ResearchPlan(BaseModel):
    # Tracks full research state: question, domain, hypothesis pool (IDs), experiment queue (IDs),
    # results (IDs), iteration count, convergence status, timestamps.
    # ConfigDict(use_enum_values=True)
    def add_hypothesis(self, hypothesis_id): ...       # Append-only with deduplication.
    def mark_tested(self, id): ...                     # Moves to tested set.
    def mark_supported(self, id): ...                  # Calls mark_tested internally.
    def mark_rejected(self, id): ...                   # Calls mark_tested internally.
    def add_experiment(self, protocol_id): ...          # Adds to experiment queue.
    def mark_experiment_complete(self, protocol_id): ... # Moves from queue to completed.
    def get_untested_hypotheses(self) -> List[str]: ... # Returns pool minus tested.
    def get_testability_rate(self) -> float: ...        # Ratio. Returns 0.0 on empty.
    def get_support_rate(self) -> float: ...            # Ratio. Returns 0.0 on empty.

class ResearchWorkflow:
    def can_transition_to(self, target_state) -> bool: ...     # Checks ALLOWED_TRANSITIONS.
    def transition_to(self, target_state, action="", metadata=None) -> bool: ...
        # Validates, records WorkflowTransition, updates state. Raises ValueError on invalid.
    def reset(self): ...                                        # Returns to INITIALIZING, clears history.
    def get_state_duration(self, state) -> float: ...           # Total seconds in a state.
    def get_state_statistics(self) -> Dict: ...                 # Visit counts and durations per state.
    def to_dict(self) -> Dict: ...                              # Exports current state + last 5 transitions.
```

**State machine not enforced at type level**: Callers can read/write `current_state` directly on both `ResearchWorkflow` and `ResearchPlan`. The `transition_to()` method validates transitions, but nothing prevents bypassing it. [FACT: workflow.py:319]

**`ResearchPlan` duplicates state**: `ResearchPlan.current_state` and `ResearchWorkflow.current_state` can diverge if the workflow is modified without going through `transition_to()`. The sync happens inside `transition_to()` at line 323-325: `self.research_plan.current_state = target_state`. [FACT: workflow.py:323-325]

**ID-based tracking only**: `ResearchPlan` stores only string IDs for hypotheses, experiments, and results -- not the actual objects. It has no knowledge of the database. All list operations are ID deduplication checks (`if x not in list`). [FACT: workflow.py:68-78]

**`PAUSED` state can resume to almost any active state**: The transition table allows PAUSED to go to 6 different states, making it a "soft reset" mechanism. But there is no mechanism to remember which state was active before pausing. The caller must decide where to resume. [FACT: workflow.py:214-221]

**`CONVERGED` can restart**: `CONVERGED -> GENERATING_HYPOTHESES` is allowed, enabling re-opening of a converged research question. Callers that assume convergence is final may be surprised. [FACT: workflow.py:212-213]

**Transition logging is config-gated**: `transition_to()` only logs the `[WORKFLOW]` debug line if `config.logging.log_workflow_transitions` is truthy. The config import is wrapped in try/except, so if config is unavailable, transitions proceed silently. [FACT: workflow.py:293-308]

**`use_enum_values=True` on Pydantic models**: `WorkflowTransition` and `ResearchPlan` use this setting, meaning enum fields are stored as their string values, not enum instances. If you serialize and deserialize, the enum fields come back as strings. Code doing `==` comparison against enum members still works because `WorkflowState` is a `str` enum, but `isinstance` checks against enum types fail. [FACT: workflow.py:48, 60]

**Performance concern on `get_untested_hypotheses()`**: Uses list comprehension `[h for h in self.hypothesis_pool if h not in self.tested_hypotheses]`. For large pools, this is O(n*m) because `tested_hypotheses` is a list, not a set. The director calls this repeatedly in `decide_next_action()`. [FACT: workflow.py:149-151]

**Transition error behavior**: `transition_to()` raises `ValueError` with allowed transitions listed in the message. [FACT: workflow.py:280-284]

**Blast radius**: 32 files reference this module. Changing `WorkflowState` enum values breaks all state comparisons. Changing `ALLOWED_TRANSITIONS` changes research flow. Changing `NextAction` enum requires updating the director's dispatch table. Changing `ResearchPlan` fields breaks the orchestrator. Changing `transition_to()` behavior can halt the research loop.

---

### `kosmos/literature/base_client.py`

```python
# kosmos/literature/base_client.py
class PaperSource(str, Enum):
    # Five values: ARXIV, SEMANTIC_SCHOLAR, PUBMED, UNKNOWN, MANUAL.

@dataclass
class Author:
    name: str           # Required
    affiliation: Optional[str] = None
    email: Optional[str] = None
    author_id: Optional[str] = None

@dataclass
class PaperMetadata:
    id: str             # Required
    source: PaperSource # Required
    title: Optional[str] = None
    abstract: Optional[str] = None
    authors: List[Author] = None  # Patched to [] in __post_init__
    # ... doi, arxiv_id, pubmed_id, publication_date, url, pdf_url,
    #     citation_count, fields, keywords, full_text, raw_data
    @property
    def primary_identifier(self) -> str: ...   # DOI > arXiv ID > PubMed ID > source ID fallback.
    @property
    def author_names(self) -> List[str]: ...   # List of author name strings.
    def to_dict(self) -> Dict: ...             # Serializes for DB. Excludes raw_data.

class BaseLiteratureClient(ABC):
    def __init__(self, api_key=None, cache_enabled=True): ...  # Stores key, creates class-specific logger.
    @abstractmethod
    def search(self, query, max_results=10, field=None, year_range=None) -> List[PaperMetadata]: ...
    @abstractmethod
    def get_paper_by_id(self, paper_id) -> Optional[PaperMetadata]: ...
    @abstractmethod
    def get_paper_references(self, paper_id) -> List[PaperMetadata]: ...
    @abstractmethod
    def get_paper_citations(self, paper_id) -> List[PaperMetadata]: ...
    def get_source_name(self) -> str: ...       # Class name minus "Client" suffix.
    def _handle_api_error(self, error, operation): ...  # Logs with traceback. Does NOT re-raise.
    def _validate_query(self, query) -> bool: ...       # False for empty. True for long (warns but no truncation).
    def _normalize_paper_metadata(self, raw_data): ...  # Raises NotImplementedError. NOT @abstractmethod.
```

**`PaperMetadata` is a `@dataclass`, not a Pydantic model**: Unlike hypothesis and experiment models, uses stdlib `dataclasses.dataclass`. No automatic validation, no field constraints, no `.model_dump()`. It relies on `__post_init__` for default mutable fields. [FACT: base_client.py:36, 80]

**`authors` field defaults to `None`, not `[]`**: `authors: List[Author] = None` uses `None` as default and patches it to `[]` in `__post_init__`. Deliberate workaround for the Python dataclass mutable-default restriction. Same for `fields` and `keywords`. [FACT: base_client.py:53, 71, 72, 84-87]

**`_normalize_paper_metadata` raises `NotImplementedError` but is NOT `@abstractmethod`**: The method is a concrete method that raises `NotImplementedError`. Subclasses can instantiate without implementing it, and the error only surfaces at runtime when the method is called. [FACT: base_client.py:255]

**`_validate_query` says "truncating" but doesn't truncate**: When `len(query) > 1000`, it logs a warning saying "truncating to 1000" but does NOT actually truncate -- it just returns `True`. Callers get no truncation and must do their own. [FACT: base_client.py:248-250]

**`raw_data` stores entire API responses**: `PaperMetadata.raw_data` holds the complete API response dict for debugging. Excluded from `to_dict()` serialization -- only lives in memory. Can be large for verbose APIs. [FACT: base_client.py:78, 99-122]

**`_handle_api_error` swallows exceptions**: Logs API errors with source name, operation, and full traceback (`exc_info=True`). Does not re-raise. Callers that need error propagation must handle it themselves. Comment says "Could add retry logic, circuit breaker, etc. here". [FACT: base_client.py:221-233]

**`PaperMetadata` has no validation**: Being a plain dataclass, it accepts any values. A `citation_count` of -999 or a `title` of `None` will not raise errors. [FACT: base_client.py:36]

**Blast radius**: With 35 importers. Renaming `PaperMetadata` or its fields breaks every literature client, agent, knowledge graph, and world model. Changing `PaperSource` enum values breaks persisted data. Changing `BaseLiteratureClient.search()` signature breaks all 4 concrete implementations. Changing `to_dict()` output format breaks database storage. Adding required fields to `PaperMetadata` breaks all construction sites. This module is a leaf dependency -- imports nothing from Kosmos. [FACT: base_client.py:1-13]

---

### `kosmos/core/providers/base.py`

```python
# kosmos/core/providers/base.py
@dataclass
class Message:
    role: str
    content: str
    name: Optional[str] = None
    metadata: Optional[Dict] = None

@dataclass
class UsageStats:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: Optional[float] = None
    model: Optional[str] = None
    provider: Optional[str] = None
    timestamp: Optional[datetime] = None

@dataclass
class LLMResponse:
    content: str
    usage: UsageStats
    model: str
    finish_reason: Optional[str] = None
    raw_response: Optional[Any] = None
    metadata: Optional[Dict] = None
    def strip(self) -> str: ...       # Delegates to self.content. Returns str, NOT LLMResponse.
    def lower(self) -> str: ...       # Same delegation pattern for 20+ string methods.
    def __contains__(self, item): ... # Makes "keyword" in response work.
    def __len__(self) -> int: ...     # Returns len(self.content).
    def __bool__(self) -> bool: ...   # Returns bool(self.content). Empty content = falsy.

class LLMProvider(ABC):
    def __init__(self, config: Dict): ...
        # Stores config, derives provider_name from class name, zeroes usage counters.
    @abstractmethod
    def generate(self, prompt, system=None, max_tokens=4096, temperature=0.7,
                 stop_sequences=None, **kwargs) -> LLMResponse: ...
    @abstractmethod
    async def generate_async(self, prompt, system=None, max_tokens=4096,
                             temperature=0.7, stop_sequences=None, **kwargs) -> LLMResponse: ...
    @abstractmethod
    def generate_with_messages(self, messages: List[Message], max_tokens=4096,
                               temperature=0.7, **kwargs) -> LLMResponse: ...
    @abstractmethod
    def generate_structured(self, prompt, schema, system=None, max_tokens=4096,
                           temperature=0.0, **kwargs) -> Dict[str, Any]: ...
    def generate_stream(self, prompt, system=None, max_tokens=4096,
                       temperature=0.7, **kwargs) -> Iterator[str]: ...
        # Non-abstract. Default raises NotImplementedError.
    async def generate_stream_async(self, prompt, system=None, max_tokens=4096,
                                    temperature=0.7, **kwargs) -> AsyncIterator[str]: ...
        # Non-abstract. Default raises NotImplementedError. Has dead `if False: yield` to make it async generator.
    @abstractmethod
    def get_model_info(self) -> Dict: ...
    def get_usage_stats(self) -> Dict: ...    # Returns accumulated usage.
    def _update_usage_stats(self, usage: UsageStats): ...  # Increments counters.
    def reset_usage_stats(self): ...          # Zeroes all usage counters.

class ProviderAPIError(Exception):
    def __init__(self, provider, message, status_code=None, raw_error=None, recoverable=True): ...
    def is_recoverable(self) -> bool: ...
        # Multi-stage: explicit flag -> HTTP status (4xx except 429 = non-recoverable) -> message pattern -> default True.
```

**`LLMResponse` masquerades as str**: Implements 20+ string methods (`strip`, `lower`, `split`, `replace`, `find`, `__contains__`, `__len__`, `__iter__`, `__getitem__`, `encode`, `format`, `join`, etc.) delegating to `self.content`. Callers can use an `LLMResponse` where `str` is expected without explicit conversion. However, `isinstance(response, str)` returns False. All string methods return `str` (not `LLMResponse`), so chaining like `response.strip().lower()` works but returns plain `str`, losing the response metadata (`.usage`, `.model`, `.finish_reason`). [FACT: base.py:80-154, 107-108]

**`LLMResponse.__bool__`**: Returns `bool(self.content)` -- an empty content string means the response is falsy. Code like `if not response:` will incorrectly treat an empty LLM response as a failure even if the API call succeeded. [FACT: base.py:98-99]

**`generate_stream_async` dead code is load-bearing**: The method raises `NotImplementedError` then has `if False: yield`. The dead yield exists solely to make Python treat the function as an async generator rather than a coroutine (which would cause a TypeError at the call site). Removing it changes the function type and breaks callers using `async for`. [FACT: base.py:360-363]

**`ProviderAPIError.is_recoverable()` competing heuristics**: Checks the `self.recoverable` flag first, then HTTP status codes, then string pattern matching on the error message. The message patterns can conflict -- an error containing both "timeout" (recoverable) and "invalid" (non-recoverable) would match the recoverable pattern first and return True because of the early-return logic. The "recoverable_patterns" check runs before "non_recoverable_patterns", so ambiguous error messages default to recoverable. [FACT: base.py:445-484, 466-477]

**Provider name derived from class name**: `self.provider_name` is set by stripping "Provider" from the class name and lowercasing. If a subclass is named `MyCustomProvider`, the provider_name becomes `"mycustom"`. [FACT: base.py:187]

**Usage tracking is instance-level only**: Token counts and cost are accumulated on the provider instance (`self.total_input_tokens`, etc.). No global/shared tracking across multiple provider instances. [FACT: base.py:190-193]

**`_update_usage_stats` skips zero cost**: The method blindly adds token counts, but if `usage.cost_usd` is `0` (falsy but valid), it will NOT be added due to `if usage.cost_usd:` check. Free-tier API calls that report `cost_usd=0.0` will not accumulate, making cost tracking slightly inaccurate. Negative costs would be added. [FACT: base.py:391-402]

**Blast radius**: Three concrete providers inherit: `AnthropicProvider`, `OpenAIProvider`, `LiteLLMProvider`. Changing any abstract method signature breaks all three. `LLMResponse` is returned by every `generate()` call -- removing any string method would cause AttributeError. `ProviderAPIError` drives retry decisions system-wide. `Message` dataclass is the input format for `generate_with_messages()`. This module is pure stdlib + typing -- no Kosmos imports. [FACT: anthropic.py:36, openai.py:32, litellm_provider.py:40]

---

### `kosmos/orchestration/plan_creator.py`

```python
# kosmos/orchestration/plan_creator.py
class PlanCreatorAgent:
    def __init__(self, anthropic_client, model, default_num_tasks=10, temperature=0.7): ...
        # Stores config. No validation.
    def create_plan(self, research_objective, context, num_tasks=None) -> ResearchPlan: ...
        # Generates plan via LLM or mock. Falls back to mock plan on ANY exception.
    def revise_plan(self, original_plan, review_feedback, context) -> ResearchPlan: ...
        # Regenerates plan with feedback. Falls back to mock plan via create_plan.
```

**Exploration ratio is hardcoded by cycle range**: Cycles 1-7 = 70% exploration, 8-14 = 50%, 15-20 = 30%. There is no configuration override. [FACT: plan_creator.py:105-121]

**Falls back to mock planning if LLM is unavailable**: If `self.client is None`, generates deterministic mock tasks instead of raising. The mock plan ensures structural requirements are met (3+ data_analysis, 2+ task types). [FACT: plan_creator.py:146-149, 292-346]

**Pads plans to requested size**: If the LLM returns fewer tasks than `num_tasks`, generic filler tasks are appended. [FACT: plan_creator.py:184-185]

**JSON parsing is naive**: Uses `find('{')` and `rfind('}')` to extract JSON from LLM response. Nested JSON in non-plan text could cause misparsing. [FACT: plan_creator.py:279-284]

**Uses raw `anthropic_client.messages.create()` directly**: NOT the Kosmos provider abstraction. Bypasses caching, cost tracking, auto-model-selection, and retry logic from the provider. [FACT: plan_creator.py:158-162]

---

### `kosmos/orchestration/plan_reviewer.py`

```python
# kosmos/orchestration/plan_reviewer.py
class PlanReviewerAgent:
    def review_plan(self, plan, context) -> PlanReview: ...
        # Evaluates on 5 dimensions + structural requirements. Falls back to mock review on ANY exception.
```

**Structural requirements are hard gates independent of scores**: A plan must have >= 3 `data_analysis` tasks AND >= 2 different task types AND every task must have `description` and `expected_output`. Even a perfect 10.0 average score fails without these. [FACT: plan_reviewer.py:272-313]

**Dimension weights are defined but NOT used**: `DIMENSION_WEIGHTS` dict exists but approval uses simple arithmetic mean. The weights are labeled "not currently used, but available for future." [FACT: plan_reviewer.py:68-69]

**Score clamping**: LLM-returned scores are clamped to `[0.0, 10.0]`. [FACT: plan_reviewer.py:252-253]

**Mock review is intentionally optimistic**: When no LLM is available, returns scores slightly above the 7.0 minimum (base 7.5 if structural requirements pass, 6.0 if not). Mock plans that pass structural checks usually also pass mock review. [FACT: plan_reviewer.py:316-357]

**Uses raw `anthropic_client.messages.create()` directly**: Bypasses the provider layer. No caching, no cost tracking, no auto-model-selection, no retry logic. [FACT: plan_reviewer.py:125-129]

---

### `kosmos/orchestration/delegation.py`

```python
# kosmos/orchestration/delegation.py
class DelegationManager:
    def __init__(self, max_parallel_tasks=3, max_retries=2, task_timeout=300, agents=None): ...
        # Configures execution parameters and agent routing.
    async def execute_plan(self, plan, cycle, context) -> Dict: ...
        # Executes all tasks in parallel batches. Returns completed/failed task lists and summary.
```

**Tasks are batched sequentially, not round-robin**: Tasks are split into fixed-size batches (default 3) and each batch is executed in parallel via `asyncio.gather`. But batches run sequentially -- batch 2 waits for batch 1 to finish. [FACT: delegation.py:196-219, 161-166]

**Retry uses exponential backoff capped at 8 seconds**: Delay is `min(2^attempt, 8)` seconds. Max retries defaults to 2 (so up to 3 total attempts). [FACT: delegation.py:343-345, 100]

**Non-recoverable `ProviderAPIError` skips retries**: If the exception has `is_recoverable() == False`, the retry loop breaks immediately. [FACT: delegation.py:335-337]

**Agents are injected via constructor dict**: The routing map expects keys: `data_analyst`, `literature_analyzer`, `hypothesis_generator`, `experiment_designer`. Missing agents cause `RuntimeError` with descriptive messages. There is no validation at init time -- the error surfaces at task execution time. [FACT: delegation.py:395-399, 434-436, 469-471, 512-516]

**All exceptions from `asyncio.gather` are caught**: `return_exceptions=True` is used. Individual task exceptions become `TaskResult(status='failed')` rather than aborting the batch. [FACT: delegation.py:247]

**The entire method is async**: The whole delegation pipeline requires an asyncio event loop. [FACT: delegation.py:126]

---

### `kosmos/orchestration/novelty_detector.py`

```python
# kosmos/orchestration/novelty_detector.py
class NoveltyDetector:
    def __init__(self, novelty_threshold=0.75, model_name="all-MiniLM-L6-v2", use_sentence_transformers=True): ...
        # Loads sentence transformer model or falls back to token-based Jaccard similarity.
    def index_past_tasks(self, tasks: List[Dict]): ...
        # Computes embeddings and appends to internal index. Mutates self.task_embeddings, task_texts, task_metadata.
    def check_task_novelty(self, task: Dict) -> Dict: ...
        # Returns is_novel bool, novelty_score, max_similarity, similar_tasks.
    def check_plan_novelty(self, plan: Dict) -> Dict: ...
        # Checks novelty of every task in plan, returns aggregate metrics.
    def filter_redundant_tasks(self, tasks, keep_most_novel=True) -> List[Dict]: ...
        # Returns only novel tasks. Uses temporary indexing with copy-restore to avoid permanent modification.
```

**Graceful fallback to Jaccard similarity**: If `sentence-transformers` is not installed, falls back to word-token Jaccard similarity. The flag `use_sentence_transformers` is mutated to `False` on import failure. [FACT: novelty_detector.py:72-85]

**Task text format is `"{type}: {description}"`**: Both indexing and querying use this concatenation. Type is included in similarity comparison, so a `data_analysis` task will have lower similarity to a `literature_review` task even with identical descriptions. [FACT: novelty_detector.py:100-102, 140-142]

**`filter_redundant_tasks` copy-restore pattern**: Temporarily saves `task_embeddings/task_texts/task_metadata`, indexes seen tasks, checks novelty, then restores the original index. This avoids permanently modifying the index. Copies Python lists but not numpy arrays deeply -- the `copy()` on a list of numpy arrays produces a shallow copy, which should be safe since `index_past_tasks` extends (appends) rather than mutates. [FACT: novelty_detector.py:320-342]

**Top-3 similar tasks threshold discrepancy**: `similar_tasks` list filters by a hardcoded 0.6 threshold, even when the novelty threshold is set to 0.75. [FACT: novelty_detector.py:171]

**No persistence**: The index lives in memory only. If the process restarts, the history is lost. [FACT: novelty_detector.py -- no file I/O]

---

### `kosmos/agents/base.py` (Agent Communication Protocol)

```python
# kosmos/agents/base.py
class MessageType(Enum):
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    ERROR = "error"

class AgentMessage(BaseModel):
    from_agent: str
    to_agent: str
    content: Dict
    correlation_id: str
    # ... message_type, timestamp, metadata

class BaseAgent:
    async def send_message(self, ...) -> AgentMessage: ...
        # Constructs AgentMessage and dispatches through _message_router callback if set.
    async def receive_message(self, message: AgentMessage): ...
        # Enqueues in both legacy sync list and asyncio.Queue, then calls process_message().
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]: ...
        # Base contract. Overridden inconsistently by subclasses.
```

**Two incompatible `execute()` signatures**: [PATTERN] Observed across 5 agent classes:

| Agent | Signature | Input | Output |
|-------|-----------|-------|--------|
| `HypothesisGeneratorAgent` | `execute(self, message: AgentMessage) -> AgentMessage` | AgentMessage | AgentMessage |
| `ExperimentDesignerAgent` | `execute(self, message: AgentMessage) -> AgentMessage` | AgentMessage | AgentMessage |
| `DataAnalystAgent` | `execute(self, task: Dict[str, Any]) -> Dict[str, Any]` | Dict | Dict |
| `LiteratureAnalyzerAgent` | `execute(self, task: Dict[str, Any]) -> Dict[str, Any]` | Dict | Dict |
| `ResearchDirectorAgent` | `async execute(self, task: Dict[str, Any]) -> Dict[str, Any]` | Dict (async) | Dict |

`HypothesisGeneratorAgent` and `ExperimentDesignerAgent` override `execute()` with an `AgentMessage` parameter -- written for the message-passing architecture and break the base class contract. In practice, none of these `execute()` methods are called in the main loop. The director calls domain-specific methods directly. [FACT: base.py:485-497, HypothesisGeneratorAgent line 91, ExperimentDesignerAgent line 109]

---

### `kosmos/agents/registry.py`

```python
# kosmos/agents/registry.py
class AgentRegistry:
    def register(self, agent): ...
        # Wires agent's message router to _route_message(). Routes by agent ID lookup.
```

**Reserved for future use**: The registry is documented as "Reserved for multi-agent message-passing architecture (future work). Not yet integrated into the main research loop." The full message bus infrastructure exists but is not used. `get_registry()` singleton is available but never called from `ResearchDirectorAgent`. [FACT: registry.py:6-8, 70-97]

---

### `kosmos/db/__init__.py`

```python
# kosmos/db/__init__.py
def init_database(url=None, config=None): ...
    # Creates engine with SQLite or PostgreSQL strategy. Auto-creates tables via Base.metadata.create_all().
def init_from_config(): ...
    # Reads config.database.normalized_url and calls init_database().
@contextmanager
def get_session() -> Session: ...
    # Provides transaction boundary: auto-commit on success, auto-rollback on failure, always close.
    # Raises RuntimeError("Database not initialized") if _SessionLocal is None.
```

**Database must init before use (HARD FAILURE)**: `get_session()` raises `RuntimeError("Database not initialized. Call init_database() first.")` if `_SessionLocal is None`. This is the only singleton in the codebase that refuses to lazy-init. `ResearchDirectorAgent.__init__()` is the de facto DB initializer. [FACT: db/__init__.py:126-127]

**Double-commit pattern**: CRUD operations in `operations.py` call `session.commit()` explicitly, AND the `get_session()` context manager also calls `session.commit()` on exit. Each operation triggers two commits -- the second is a no-op. The CRUD layer was designed to be usable both with and without the context manager. [FACT: db/operations.py:113, 187, 220, 328, 452, 501]

**Agents bypass CRUD layer**: Agent classes directly construct SQLAlchemy model instances and call `session.add()` + `session.commit()` instead of using CRUD functions in `operations.py`. This bypasses validation logic (`_validate_json_dict`, `_validate_json_list`). [PATTERN: hypothesis_generator.py:474-492, experiment_designer.py:888-903]

**Error recovery pattern**: Agents use graceful degradation: if `get_session()` raises (e.g., "Database not initialized"), the agent logs a warning and continues with a generated UUID. Protocol/hypothesis objects remain valid without DB persistence. [FACT: experiment_designer.py:908-919]

---

### `kosmos/world_model/factory.py` and `kosmos/world_model/interface.py`

```python
# kosmos/world_model/factory.py
def get_world_model() -> WorldModelStorage: ...
    # Singleton. Reads mode from config. 'simple': Neo4jWorldModel with fallback to InMemoryWorldModel.
    # 'production': raises NotImplementedError. Explicitly NOT thread-safe.

# kosmos/world_model/interface.py
class WorldModelStorage(ABC): ...  # CRUD for entities and relationships, import/export, statistics.
class EntityManager(ABC): ...      # Verification and annotation operations.
class ProvenanceTracker(ABC): ...  # W3C PROV-O standard derivation tracking (Phase 4).
```

**Three implementations**: `Neo4jWorldModel` (wraps `KnowledgeGraph` via Adapter pattern, default for production), `InMemoryWorldModel` (dict-based for testing, automatic fallback), `ArtifactStateManager` (JSON file-based, independent of WorldModelStorage). [FACT: simple.py, in_memory.py, artifacts.py]

**Factory with fallback**: `simple` mode creates `Neo4jWorldModel`, checks `connected` property, falls back to `InMemoryWorldModel` if Neo4j unavailable. `production` mode raises `NotImplementedError`. Explicitly documented as NOT thread-safe. [FACT: factory.py:108-155]

**Only ResearchDirectorAgent writes to the world model**: No other agent imports `world_model` or `get_world_model`. The knowledge graph is a write-only audit log from the agents' perspective. [ABSENCE confirmed in agent_communication.md]

---

### `kosmos/world_model/artifacts.py`

```python
# kosmos/world_model/artifacts.py
class ArtifactStateManager:
    def save_finding_artifact(self, finding, cycle, task_id): ...
        # Saves as artifacts/cycle_{N}/task_{M}_finding.json. Caches in _findings_cache. Indexes to graph if available.
    def save_hypothesis(self, hypothesis): ...
        # Saves as artifacts/hypotheses/{hypothesis_id}.json.
    def get_finding(self, finding_id) -> Optional[Dict]: ...
        # Checks in-memory cache, falls back to filesystem glob + linear scan. O(n) by finding_id.
    def add_finding_with_conflict_check(self, finding, ...) -> Dict: ...
        # Three update categories: Confirmation, Conflict, Pruning.
```

**4-layer hybrid architecture**: Layer 1: JSON artifacts (always active). Layer 2: Knowledge graph (optional). Layer 3: Vector store (stub). Layer 4: Citation tracking (in JSON layer). [FACT: artifacts.py:146-178]

**No cross-backend transactions**: When data is written to multiple backends, each write is independent. A failure in Layer 2 (graph) does not roll back Layer 1 (JSON). The `_index_finding_to_graph` method catches all exceptions and logs warnings. [ABSENCE: no distributed transaction coordinator]

---

### `kosmos/core/async_llm.py`

```python
# kosmos/core/async_llm.py
class CircuitBreaker:
    # States: CLOSED, OPEN, HALF_OPEN
    # Config: failure_threshold=5, reset_timeout=30s, half_open_max_calls=2
    # On OPEN: all requests immediately rejected.
    # After reset_timeout: transitions to HALF_OPEN, allows 2 test calls.
    # A failure in HALF_OPEN immediately re-opens.

class AsyncLLMClient:
    # Uses tenacity (optional) with wait_exponential(min=1, max=30) and stop_after_attempt(3).
    # Custom should_retry predicate checks is_recoverable_error().
    # If tenacity not installed, API calls run without retry protection (no warning logged).
```

**`tenacity` is optional**: Imported inside try/except. If not installed, API calls silently run without retry protection. There is no warning logged when this happens. [FACT: async_llm.py:33-39, 462]

**Circuit breaker**: Classic three-state pattern (CLOSED/OPEN/HALF_OPEN). A failure in HALF_OPEN immediately re-opens. [FACT: async_llm.py:58, 66-67, 118-120]

---

### Hidden Coupling: The `_DEFAULT_CLAUDE_*_MODEL` Constants

[PATTERN] Two constants from `config.py:17-18` (`_DEFAULT_CLAUDE_SONNET_MODEL`, `_DEFAULT_CLAUDE_HAIKU_MODEL`) are underscore-prefixed "private" constants imported by 7+ files: `core/providers/anthropic.py`, `core/providers/litellm_provider.py`, `core/llm.py`, `validation/scholar_eval.py`, `compression/compressor.py`, `orchestration/plan_reviewer.py`, `orchestration/plan_creator.py`, `models/hypothesis.py`, `models/experiment.py`, `models/domain.py`. These are effectively public API. Renaming or removing them would break 7+ consumers with no warning.

### Hidden Coupling: The Flat Config Dict Anti-Pattern

[PATTERN] 3 places bridge structured config to flat dicts: `core/providers/factory.py:107-170`, `cli/commands/run.py:148-170`, and `core/llm.py:655-676`. Each manually extracts fields from Pydantic models into `dict[str, Any]`. There is no shared schema, so each bridging point can drift independently. The `flat_config` dict keys (e.g., `"max_iterations"`, `"budget_usd"`, `"data_path"`) are string-based. No schema validates that the CLI passes the right keys or that the director reads the right ones. A typo in either file fails silently. [FACT: run.py:148-170, research_director.py config usage]

### Hidden Coupling: String-Based Agent Type Matching

[FACT] `research_director.py:582-583` routes messages from `ExperimentDesignerAgent` via string matching: `elif sender_type == "ExperimentDesignerAgent"`. A rename breaks routing silently. Both agents share implicit contracts about hypothesis model format, experiment protocol format, and message payload structure. [FACT: research_director.py:582-583]

### Hidden Coupling: `run.py` Mutates Global Config

[FACT] `run.py:136-137` directly mutates the config singleton: `config_obj.research.enabled_domains = [domain]`. CLI parameter handling has side effects on the global config, potentially affecting other singletons that read from config later.
# Error Handling Strategy

## Summary Table

```
**Dominant pattern:** Catch-log-degrade (catch Exception, log, return degraded result)
    [PATTERN: observed in 364 except-Exception sites across 102/102 modules]

**Retry strategy:** Three distinct retry implementations exist -- code execution (self-correcting),
    task delegation (exponential backoff with recoverability gate), and async LLM
    (tenacity + circuit breaker). Plus two auxiliary retry loops: JSON parse retry and
    research director error recovery.

**Deviations:**
| Module | Pattern | Risk |
|--------|---------|------|
| `world_model/simple.py` | Three consecutive `except Exception: pass` with zero logging | Debugging Neo4j issues impossible |
| `experiment_cache.py` | Re-raises on write, returns None on read (intentional split) | Callers must handle both patterns |
| `core/async_llm.py` | tenacity is optional -- silent degradation to no-retry | API calls unprotected with no warning |
| `core/providers/anthropic.py` | Wraps all SDK errors into ProviderAPIError | Loses original exception type |
| `research_director.py` | 27 except-Exception sites (highest count) | Must-never-crash orchestrator |
| `core/metrics.py` | BudgetExceededError raised but never caught | Unhandled exception crashes run |
| `safety/guardrails.py` | Raises RuntimeError on emergency stop | One of the few raise-not-catch sites |
| `experiment_cache.py` vs `literature/cache.py` | Two separate cache error hierarchies | No shared base class |
| `base_client.py:_handle_api_error` | Swallows exception after logging | Callers must propagate manually |
| `base_client.py:_validate_query` | Warns "truncating" but does not truncate | Misleading log message |
| `code_validator.py` | AST parsed up to 3 times independently | Minor perf + inconsistent fallback |
| `code_generator.py:_validate_syntax` | Raises ValueError, not SyntaxError | Changes exception type for callers |
```

---

## 1. Custom Exception Hierarchy

[PATTERN] 9 custom exception classes defined across the codebase. Observed in 9 files.

| Exception Class | File | Purpose |
|---|---|---|
| `JSONParseError` | `core/utils/json_parser.py:21` | LLM response JSON parsing failures |
| `ProviderAPIError` | `core/providers/base.py:417` | Provider API call failures with recoverability flag |
| `APIError` | `core/async_llm.py:23` | Anthropic SDK API errors (conditional import) |
| `APITimeoutError` | `core/async_llm.py:26` | Anthropic SDK timeout errors (conditional import) |
| `RateLimitError` | `core/async_llm.py:29` | Anthropic SDK rate limit errors (conditional import) |
| `CacheError` | `core/cache.py:22` | Cache operation failures |
| `BudgetExceededError` | `core/metrics.py:63` | Budget limit exceeded |
| `LiteratureCacheError` | `literature/cache.py:19` | Literature cache operation failures |
| `PDFExtractionError` | `literature/pdf_extractor.py:22` | PDF extraction failures |

[FACT] `ProviderAPIError` is the most architecturally significant: it carries a `recoverable` flag and `is_recoverable()` method that classifies errors by HTTP status code and message patterns (`core/providers/base.py:445-484`). This flag drives retry/circuit-breaker decisions upstream. Classification logic:
- **Recoverable**: timeout, connection, network, rate_limit, overloaded, service_unavailable, HTTP 429/502/503/504
- **Non-recoverable**: json parse, invalid, authentication, unauthorized, forbidden, not found, bad request, HTTP 400/401/403/404
- **Default**: unknown errors are treated as recoverable

[FACT] `ProviderAPIError.is_recoverable()` has competing heuristics at `core/providers/base.py:445-484`. The method checks the `self.recoverable` flag first, then HTTP status codes, then does string pattern matching on the error message. The message patterns can conflict -- e.g., an error containing both "timeout" (recoverable) and "invalid" (non-recoverable) would match the recoverable pattern first and return True because of the early-return logic. The "recoverable_patterns" check runs before "non_recoverable_patterns", so ambiguous error messages default to recoverable. [FACT: base.py:466-477]

[FACT] `BudgetExceededError` at `core/metrics.py:63-85` carries structured cost data (`current_cost`, `limit`, `usage_percent`) -- a well-designed exception for cost governance.

[FACT] `CacheError` at `core/cache.py:22` and `LiteratureCacheError` at `literature/cache.py:19` are two separate cache error hierarchies that do not share a base class. This means a single `except CacheError` will not catch literature cache failures.

---

## 2. Dominant Strategy: Catch-Log-Degrade

[PATTERN] The dominant error handling pattern across the entire codebase is: catch broad `Exception`, log via `logger.error()` or `logger.warning()`, then return a degraded result (empty list, None, dict with error key, or a failure status object). Observed in 364 `except Exception as e:` sites across 102 files, plus 38 bare `except Exception:` sites across 22 files.

### 2a. Agents Layer: Research Director

[FACT] `ResearchDirectorAgent._handle_error()` at line 627 implements the most sophisticated agent-level error recovery. It tracks `errors_encountered`, `_consecutive_errors`, `_error_history` (list of error records with source/message/timestamp/recoverability). When `_consecutive_errors >= MAX_CONSECUTIVE_ERRORS` (3, defined at line 45), it transitions the workflow to `WorkflowState.ERROR`. For recoverable errors, it applies exponential backoff from `ERROR_BACKOFF_SECONDS = [2, 4, 8]` (line 46), then calls `self.decide_next_action()` to re-enter the state machine. [FACT: research_director.py:640-684]

[FACT] `research_director.py` has 27 `except Exception as e:` sites (highest in the codebase by count for a single file), reflecting both the file's size and its role as the orchestration hub that must never crash.

[FACT] `research_director.py:674` -- `_handle_error_with_recovery()` calls `time.sleep()` which blocks the asyncio event loop. Since `execute()` and all `_handle_*_action()` methods are async, this sleep blocks the entire event loop thread during error backoff. The backoff delays are `[2, 4, 8]` seconds.

[FACT] `research_director.py:131-139` -- Database initialization in `__init__` catches `RuntimeError` for "already initialized" and all other exceptions. If the DB init fails for a real reason, the error is only logged as a warning -- the director continues without a working database, which will cause cascading failures when any handler tries to query the DB.

[FACT] `research_director.py:228-239` -- The async LLM client initialization reads `ANTHROPIC_API_KEY` directly from `os.getenv()`, bypassing the config system. This is different from how the sync `get_client()` works (which uses config-based provider factory).

[FACT] `research_director.py:242-255` -- World model initialization: if `get_world_model()` fails, `self.wm = None` and all graph operations silently no-op.

[FACT] `research_director.py:376-379` -- The sync `_workflow_context()` context manager yields `self.workflow` without any lock. The comment says "not used with async". But if sync code uses this while async code uses the async lock, there is no mutual exclusion between the two paths.

### 2b. Research Director: Knowledge Graph Persistence

[FACT] `research_director.py:388-562` -- 4 separate graph persistence methods (`_persist_hypothesis_to_graph`, `_persist_protocol_to_graph`, `_persist_result_to_graph`, `_add_support_relationship`). Each opens a new DB session, fetches the entity, converts to a `world_model.Entity`, and creates relationships. All are fire-and-forget: catch all exceptions and log, never propagate.

### 2c. Knowledge Graph

[FACT] `GraphBuilder.add_paper()` (graph_builder.py:119-142) wraps the entire paper-adding operation in try/except, catches any Exception, logs it, increments `self.stats["errors"]` counter, and returns `None`. A single bad paper in a batch of 100 silently skips without halting the pipeline.

### 2d. Literature Search

[FACT] `UnifiedLiteratureSearch.search()` (unified_search.py:163-175) uses `ThreadPoolExecutor` with `as_completed()` and a configurable timeout. Individual source failures are caught per-future with `logger.error()` -- a failing PubMed API does not block arXiv results. On `FuturesTimeoutError`, it logs which sources completed and salvages any late-arriving results.

### 2e. World Model (Most Deeply Nested Silent Catch)

[FACT] `world_model/simple.py:918-960` -- `_get_neo4j_storage_size()` uses a three-tier fallback chain: try APOC procedure, try db.stats, try estimation from counts. Each tier catches `Exception` and `pass`es to fall through to the next. The outer except also catches and returns 0.0. This is the most deeply nested silent-catch pattern in the codebase (3 inner `except Exception: pass` + 1 outer `except Exception as e`). These are intentional (fallback chain) but make debugging Neo4j connectivity issues very difficult since no logging occurs at all for any of these failures.

### 2f. Experiment Cache (Intentional Split)

[FACT] `experiment_cache.py` has two contrasting patterns in the same class: `cache_experiment()` at line 391 catches Exception and **re-raises** it (data integrity matters for writes). `get_cached_result()` at line 444 catches Exception and **returns None** (cache misses are tolerable for reads). This write-fail-loudly/read-fail-silently split is an intentional design choice.

### 2g. Literature Client Base

[FACT] `base_client.py:_handle_api_error()` (lines 221-233) logs API errors with source name, operation description, and full traceback (`exc_info=True`). It does NOT re-raise. Swallows the error after logging. Comment says "Could add retry logic, circuit breaker, etc. here". Callers that need error propagation must handle it themselves.

### 2h. Database Session Error Recovery

[FACT] `kosmos/db/__init__.py:108-137` -- `get_session()` is a `@contextmanager` that provides the sole transaction boundary:
```python
session = _SessionLocal()
try:
    yield session
    session.commit()    # auto-commit on success
except Exception:
    session.rollback()  # auto-rollback on failure
    raise               # NOTE: this one RE-RAISES unlike most patterns
finally:
    session.close()     # always close
```

This is one of the few places where `except Exception` actually re-raises the error rather than swallowing it.

[FACT] `experiment_designer.py:908-919` -- Agents use graceful degradation: if `get_session()` raises (e.g., "Database not initialized"), the agent logs a warning and continues with a generated UUID. The protocol/hypothesis object remains valid even without database persistence.

---

## 3. Retry Strategies (Full Detail)

### 3a. Code Execution Retry (kosmos/execution/executor.py) -- Self-Correcting

[FACT] `CodeExecutor` at line 162 uses `RetryStrategy` (line 667) with `max_retries=3` and `base_delay=1.0`. The retry loop at lines 273-376 is self-correcting: on failure, `modify_code_for_retry()` analyzes the error type and applies automatic fixes (missing imports, data type issues, etc.) before re-executing. This is the most intelligent retry in the system -- it doesn't just retry the same code, it modifies it.

[FACT] Non-retryable errors: `SyntaxError` (requires code rewrite), `FileNotFoundError` (terminal -- use synthetic data, Issue #51 fix), `DataUnavailableError` (custom error for missing data). The `should_retry()` method at line 724-728 checks these.

[FACT] The delay formula is `base_delay * 2^(attempt-1)` (line 733), capped implicitly by max_retries.

[FACT] `RetryStrategy` tracks repair statistics per error type (`repair_stats` dict at line 711), enabling observability into which auto-fixes succeed.

[FACT] `modify_code_for_retry()` handles 11 error types: KeyError, FileNotFoundError, NameError, TypeError, IndexError, AttributeError, ValueError, ZeroDivisionError, ImportError/ModuleNotFoundError, PermissionError, MemoryError. It dispatches to error-type-specific fixers. Tries LLM first (attempts 1-2 only), then pattern-based. Returns modified code or None. [FACT: executor.py:751-825]

[FACT] Most fix methods (e.g., `_fix_key_error`, `_fix_type_error`) wrap the ENTIRE original code in a try/except block (lines 869-877). This masks the original error and produces a `results = {'error': ..., 'status': 'failed'}` dict. The experiment appears to "succeed" (no exception) but with a failure result. Callers must check `result.return_value` for `{'status': 'failed'}` in addition to `result.success`.

[FACT] `FileNotFoundError` is explicitly terminal: `_fix_file_not_found()` returns `None` (line 906). This is intentional -- missing data files should trigger synthetic data generation in templates, not retry loops.

[FACT] LLM repair only on first 2 attempts: `modify_code_for_retry()` only tries LLM-based repair when `attempt <= 2`. Subsequent attempts use pattern-based fixes only. [FACT: executor.py:779]

[FACT] The retry loop calls `time.sleep()` synchronously (line 335), blocking the calling thread. In async contexts this blocks the event loop.

### 3b. Task Delegation Retry (kosmos/orchestration/delegation.py)

[FACT] `TaskDelegationEngine._execute_task_with_retry()` at line 280 retries tasks up to `max_retries` (configurable, default 2, line 100). Uses exponential backoff `min(2^attempt, 8)` (line 344, capped at 8 seconds). Each TaskResult records `retry_count` for visibility.

[FACT] Checks `ProviderAPIError.is_recoverable()` at line 335 to skip retries on non-recoverable errors. If the exception has `is_recoverable() == False`, the retry loop breaks immediately. [FACT: delegation.py:335-337]

[FACT] All exceptions from `asyncio.gather` are caught because `return_exceptions=True` is used. Individual task exceptions become `TaskResult(status='failed')` rather than aborting the batch. [FACT: delegation.py:247]

[FACT] Agents are injected via constructor dict. The routing map expects keys: `data_analyst`, `literature_analyzer`, `hypothesis_generator`, `experiment_designer`. Missing agents cause `RuntimeError` with descriptive messages. There is no validation at init time -- the error surfaces at task execution time. [FACT: delegation.py:395-399, 434-436, 469-471, 512-516]

### 3c. LLM API Retry with Circuit Breaker (kosmos/core/async_llm.py)

[FACT] `AsyncLLMClient` at line 440 uses `tenacity` library (optional import at line 36) with `wait_exponential(min=1, max=30)` and `stop_after_attempt(3)`. A custom `should_retry` predicate at line 429 checks `is_recoverable_error()` (line 141) which delegates to `ProviderAPIError.is_recoverable()` for provider errors and pattern-matches Anthropic SDK error types.

[FACT] The `CircuitBreaker` class at `core/async_llm.py:58` implements the classic three-state pattern (CLOSED/OPEN/HALF_OPEN). Configuration: `failure_threshold=5`, `reset_timeout=30s`, `half_open_max_calls=2` (lines 66-67). On OPEN, all requests are immediately rejected. After `reset_timeout`, transitions to HALF_OPEN and allows 2 test calls. A failure in HALF_OPEN immediately re-opens (line 118-120).

[FACT] `is_recoverable_error()` at `core/async_llm.py:141-169` extends `ProviderAPIError.is_recoverable()` to Anthropic SDK exceptions: `RateLimitError` always recoverable, `APITimeoutError` always recoverable, `APIError` checked by message pattern. Unknown exceptions default to recoverable.

[FACT] At `core/async_llm.py:33-39`, tenacity is imported inside a try/except. If tenacity is not installed, the `_api_call_with_retry()` function at line 462 falls through to a no-retry path. **There is no warning logged when this happens** -- API calls silently run without retry protection.

### 3d. JSON Parse Retry (kosmos/core/llm.py)

[FACT] `ClaudeClient.generate_structured()` at line 460 retries JSON parsing with `max_retries=2` (default). On `JSONParseError`, it bypasses cache (`bypass_cache=attempt > 0` at line 466) and re-calls the API. This is a separate retry loop from the tenacity-based provider retry. The schema instruction is always added to the system prompt even if the original system prompt already contains JSON instructions. [FACT: llm.py:460-478, 456]

[FACT] `generate_structured()` raises `ProviderAPIError` after exhausting retries. The `schema` parameter is an alias for `output_schema` for provider compatibility. [FACT: llm.py:410-486, 480-486]

### 3e. Research Director Error Recovery (kosmos/agents/research_director.py)

[FACT] `_handle_error()` at line 610 implements application-level error recovery separate from API retry. Uses `ERROR_BACKOFF_SECONDS = [2, 4, 8]` (line 46) with `MAX_CONSECUTIVE_ERRORS = 3` (line 45). Distinguishes recoverable (backoff + retry via `decide_next_action()`) from non-recoverable (skip to next action). Error history is maintained as a list of dicts with full context (source, message, timestamp, recoverability, details).

[FACT] The circuit breaker at 3 errors: after 3 consecutive failures, the workflow transitions to `WorkflowState.ERROR`. [FACT: research_director.py:45, 649-662]

[FACT] `_handle_error_with_recovery()` calls blocking `time.sleep()` with `[2, 4, 8]` second delays inside async code paths. This blocks the entire event loop thread during error backoff. [FACT: research_director.py:674]

---

## 4. Graceful Degradation via Optional Imports

[PATTERN] 61 `except ImportError:` sites across 38 files. The codebase extensively uses optional imports to degrade gracefully when dependencies are missing.

[FACT] Representative examples with their degradation behavior:
- `execution/executor.py:24-28`: Docker sandbox import failure sets `SANDBOX_AVAILABLE = False`, executor falls back to restricted builtins. Docker sandbox fallback is silent: if `use_sandbox=True` but Docker is not installed, the executor sets `self.use_sandbox = False` and continues. No error raised. [FACT: executor.py:216-220]
- `execution/executor.py:32-37`: R executor import failure sets `R_EXECUTOR_AVAILABLE = False`, R code execution disabled
- `core/llm.py:26`: Anthropic import failure handled (enables CLI mode)
- `core/async_llm.py:33-39`: tenacity import failure means no retry decorator -- API calls execute without retry. **No warning logged.**
- `monitoring/metrics.py:18`: prometheus import failure handled (metrics disabled)
- `validation/null_model.py:31`: scipy import failure handled
- `analysis/visualization.py:21`: plotly import failure handled
- `safety/reproducibility.py:32,154,161`: Multiple optional imports for hash functions
- `knowledge/vector_db.py:19-27`: ChromaDB optional, imported with try/except with `HAS_CHROMADB` flag. If missing, all operations return empty results or no-ops.

[FACT] `ExperimentCodeGenerator.__init__` has double fallback for LLM client: tries `ClaudeClient()` first, catches failure, then tries `LiteLLMProvider` as fallback. If both fail, LLM generation is silently disabled (`self.use_llm = False`). No exception is raised. If templates also don't match, only the basic fallback (which lacks synthetic data) runs. [FACT: code_generator.py:762-778]

[FACT] `NoveltyDetector` gracefully falls back to Jaccard similarity if `sentence-transformers` is not installed. The flag `use_sentence_transformers` is mutated to `False` on import failure. [FACT: novelty_detector.py:72-85]

---

## 5. Safety-Critical Error Handling

[FACT] `SafetyGuardrails` at `safety/guardrails.py:95-110` registers SIGTERM/SIGINT signal handlers for emergency stop. If signal registration fails, it logs a warning but continues -- the safety system itself uses catch-log-degrade.

[FACT] `SafetyGuardrails.validate_code()` at line 112 raises `RuntimeError` when emergency stop is active (line 129-131) -- one of the few places where errors are raised rather than caught. Code validation failures are logged as incidents but do not raise.

[FACT] `CodeValidator` at `safety/code_validator.py:27` uses AST analysis for safety checks. It blocks dangerous modules (`os`, `subprocess`, `sys`, `shutil`, `eval`, `exec`, etc.) and dangerous patterns. This is a preventive layer, not a reactive error handler.

[FACT] `CodeValidator` pattern detection uses raw string matching `if pattern in code:` which matches inside comments and string literals. `# eval()` or `description = "do not eval("` would trigger a CRITICAL violation. [FACT: code_validator.py:288]

[FACT] `os` is on the validator's dangerous list but the RetryStrategy's `COMMON_IMPORTS` dict includes `'os': 'import os'`. Auto-fix can insert an `import os` that the validator would reject. [FACT: code_validator.py:36, executor.py:686]

[FACT] `getattr()` is flagged as CRITICAL by the AST call checker despite being a common safe pattern. Generated code using `getattr(obj, 'attr', default)` will fail validation even if usage is benign. [FACT: code_validator.py:338]

[FACT] `execute_protocol_code()` always validates safety via `CodeValidator`. The comment "F-21: removed validate_safety bypass" indicates a previous version had a way to skip validation that was deliberately removed. [FACT: executor.py:1039-1048]

---

## 6. Error Event Propagation

[FACT] The `core/events.py` file defines typed failure events: `WORKFLOW_FAILED`, `CYCLE_FAILED`, `TASK_FAILED`, `LLM_CALL_FAILED`, `CODE_FAILED` (lines 22-46). These are published via `EventBus` for CLI/API consumers.

[FACT] `AlertManager` at `monitoring/alerts.py:114` defines default alert rules for: `database_connection_failed` (CRITICAL, 60s cooldown), `high_api_failure_rate` (ERROR, 300s cooldown), `api_rate_limit_warning` (WARNING, 600s cooldown), `high_memory_usage` (WARNING, 300s cooldown). Alert conditions are evaluated in try/except -- a failing condition evaluator returns `False` rather than propagating (line 89-93).

---

## 7. Logging Infrastructure

[FACT] `core/logging.py` provides structured JSON logging with correlation IDs (`contextvars.ContextVar` at line 23). Log format is configurable between JSON and text. The `JSONFormatter` at line 34 produces machine-parseable logs with timestamp, level, logger, message, module, function, and line number.

[PATTERN] 549 `logger.error()` or `logger.warning()` calls across 101 files. Error logging is pervasive and consistent in format: `logger.error(f"Description: {e}")`.

---

## 8. Per-Module Error Handling Deep Dive

### 8a. `kosmos/core/llm.py` Error Handling

[FACT] `ClaudeClient.__init__` raises `ImportError` if `anthropic` not installed, `ValueError` if no API key. These are the only hard failures. [FACT: llm.py:154-165]

[FACT] `ClaudeClient.generate()` propagates API exceptions. Does not catch them. [FACT: llm.py:207-365]

[FACT] `ClaudeClient.generate_structured()` raises `ProviderAPIError` after exhausting retries. This is one of the few places that raises a custom exception rather than catching and degrading. [FACT: llm.py:480-486]

[FACT] `get_client()` catches config exceptions and falls back to `AnthropicProvider` with env-var API key. [FACT: llm.py:613-679]

[FACT] `get_provider()` raises `TypeError` if the singleton is a `ClaudeClient` instead of `LLMProvider`. [FACT: llm.py:682-706]

### 8b. `kosmos/execution/executor.py` Error Handling

[FACT] `CodeExecutor.execute()` returns `ExecutionResult(success=False)` rather than raising. This is a key architectural decision -- execution failures are data, not exceptions. [FACT: executor.py:237-376]

[FACT] `CodeExecutor.__init__` uses graceful degradation: logs warnings if Docker sandbox or R executor are unavailable, but does not raise. [FACT: executor.py:174-235]

[FACT] On Windows, the `ThreadPoolExecutor` timeout does not kill the executing thread. A hung computation continues consuming resources even after the timeout fires. [FACT: executor.py:621-630]

[FACT] The retry fix methods wrap entire code in try/except, making execution "succeed" with an error result dict. The experiment appears to "succeed" but `return_value` contains `{'status': 'failed'}`. [FACT: executor.py:869-877]

### 8c. `kosmos/execution/code_generator.py` Error Handling

[FACT] `ExperimentCodeGenerator.generate()` raises `ValueError` on syntax error (not `SyntaxError`). The `_validate_syntax` method wraps `SyntaxError` in `ValueError`, changing the exception type for callers. [FACT: code_generator.py:988-989]

[FACT] LLM client failure during `__init__` silently disables LLM generation. No exception is raised. If templates also don't match, only the basic fallback runs -- and the basic fallback lacks synthetic data support, meaning it will crash with NameError if `data_path` is not defined. [FACT: code_generator.py:762-778, 954-977]

[FACT] `_extract_code_from_response` has a weak heuristic: if the LLM response contains no code fences, it checks for "import", "def ", or "=" to decide if it's code. A natural language response containing "=" would be treated as code. [FACT: code_generator.py:907-924]

[FACT] All templates fall back to mock plan on ANY exception from the LLM. [FACT: plan_creator.py:194-198, plan_reviewer.py:161-162]

### 8d. `kosmos/safety/code_validator.py` Error Handling

[FACT] `validate()` runs 6 checks in sequence. If `_check_syntax()` fails (SyntaxError), `_check_dangerous_imports()` still runs with its own try/except and falls back to string matching. `_check_ast_calls()` returns on SyntaxError (defers to `_check_syntax` result). This means a syntax error does NOT prevent all other checks from running. [FACT: code_validator.py:159-231, 237, 252, 332]

[FACT] `_check_dangerous_imports()` AST-based import detection falls back to string matching on SyntaxError. This means partially-parseable code still gets import checking. [FACT: code_validator.py:247-281]

[FACT] Ethical guidelines `break` after first keyword match per guideline. Only one violation reported per guideline even if multiple keywords match. [FACT: code_validator.py:417]

### 8e. `kosmos/core/workflow.py` Error Handling

[FACT] `transition_to()` raises `ValueError` on invalid transition with allowed transitions listed in the message. This is strict -- no degradation, no catch-and-continue. [FACT: workflow.py:280-284]

[FACT] Transition logging is config-gated. The config import is wrapped in try/except, so if config is unavailable, transitions proceed silently (no log). [FACT: workflow.py:293-308]

### 8f. `kosmos/literature/base_client.py` Error Handling

[FACT] `_handle_api_error()` logs with `exc_info=True` for full traceback, then returns without re-raising. Comment explicitly says "Could add retry logic, circuit breaker, etc. here" but none is implemented. [FACT: base_client.py:221-233]

[FACT] `_validate_query()` returns `False` for empty/whitespace queries, `True` otherwise. Warns on queries > 1000 chars but does NOT truncate, despite log message claiming truncation. [FACT: base_client.py:235-250]

[FACT] `PaperMetadata` has no validation. Being a plain dataclass, invalid data is silently accepted. A `citation_count` of -999 or a `title` of `None` will not raise errors. [FACT: base_client.py:36]

### 8g. `kosmos/core/providers/base.py` Error Handling

[FACT] `LLMResponse` with empty content is falsy (`__bool__` returns `bool(self.content)`). Code like `if not response:` will incorrectly treat an empty LLM response as a failure even if the API call succeeded. [FACT: base.py:98-99]

[FACT] `_update_usage_stats` skips cost when `cost_usd` is exactly `0.0` (falsy). Free-tier API calls that report `cost_usd=0.0` will not accumulate, making cost tracking slightly inaccurate. [FACT: base.py:401]

[FACT] `generate_stream_async` has dead `if False: yield` after raise -- load-bearing dead code that makes it an async generator. Removing it causes TypeError at call sites. [FACT: base.py:360-363]

### 8h. `kosmos/orchestration/` Error Handling

[FACT] Both `PlanCreatorAgent` and `PlanReviewerAgent` call `anthropic_client.messages.create()` directly, bypassing the Kosmos LLMProvider layer. This means no caching, no cost tracking, no auto-model-selection, and no retry logic from the provider. [FACT: plan_creator.py:158-162, plan_reviewer.py:125-129]

[FACT] `PlanCreatorAgent.create_plan()` falls back to mock plan on ANY exception. The mock plan ensures structural requirements are met. [FACT: plan_creator.py:194-198]

[FACT] `PlanReviewerAgent.review_plan()` falls back to mock review on ANY exception. Mock review is intentionally optimistic (base 7.5 if structural requirements pass). [FACT: plan_reviewer.py:161-162, 316-357]

[FACT] `DelegationManager` raises `RuntimeError` at task execution time if the required agent is not in the `agents` dict. There is no validation at init time. [FACT: delegation.py:395-399]

[FACT] `NoveltyDetector.filter_redundant_tasks` uses copy-restore pattern. Copies Python lists but not numpy arrays deeply. Shallow copy should be safe since `index_past_tasks` extends rather than mutates. [FACT: novelty_detector.py:320-342]

---

## 9. No Centralized Exception Handling

[ABSENCE] There is no centralized exception handler, error boundary, or middleware pattern. Each module independently implements its own try/except. Confirmed by searching for patterns like `error_handler`, `exception_middleware`, `error_boundary` -- none found in `kosmos/kosmos/`.

---

## 10. BudgetExceededError: Raised But Not Caught

[FACT] `BudgetExceededError` is defined at `core/metrics.py:63` but searching for `except BudgetExceededError` or `except.*Budget` across the codebase finds no catch sites. This means budget overruns will propagate as unhandled exceptions to the top of the call stack, potentially crashing a research run. This may be intentional (hard budget limit) but it's undocumented.

---

## 11. Anthropic SDK Error Re-Wrapping

[FACT] `AnthropicProvider.generate()` at `core/providers/anthropic.py:340-342` catches all exceptions from the Anthropic SDK and wraps them in `ProviderAPIError`. This loses the original exception type for downstream handlers that might want to match on specific Anthropic error types. The `raw_error` field preserves the original but callers rarely check it.

---

## 12. Error Architecture Diagram

```
    Caller
      |
      v
  [Agent Layer]  --- catch Exception, log, return degraded result
      |               (e.g., research_director: error history + circuit breaker at 3 errors)
      |               27 except-Exception sites in research_director alone
      v
  [Orchestration Layer] --- retry with backoff, ProviderAPIError.is_recoverable() checks
      |                      (delegation: max 2 retries, exp backoff capped at 8s)
      |                      (plan creator/reviewer: fall back to mock on ANY exception)
      v
  [Core LLM Layer] --- tenacity retry + CircuitBreaker + ProviderAPIError
      |                  (async_llm: 3 attempts, exp backoff 1-30s, circuit opens at 5 failures)
      |                  (ClaudeClient: JSON parse retry, max_retries=2)
      v
  [Provider Layer] --- wraps SDK exceptions into ProviderAPIError
      |                 (anthropic.py: all errors -> ProviderAPIError, loses original type)
      v
  [External APIs]  --- Anthropic, PubMed, arXiv, Semantic Scholar
```

Each layer catches and handles errors independently. Errors generally do NOT propagate upward as exceptions -- they are converted to return values (None, empty list, error dict) at each boundary. The single exception is `BudgetExceededError` which propagates uncaught to the top.

---

## 13. Database Error Handling

[FACT] `kosmos/db/__init__.py:126-127` -- `get_session()` raises `RuntimeError("Database not initialized. Call init_database() first.")` if `_SessionLocal is None`. This is the only singleton that refuses to lazy-init -- a hard failure.

[FACT] `get_session()` context manager auto-commits on success, auto-rollbacks on failure, and always closes. Unlike most error handlers, this one RE-RAISES exceptions after rollback.

[FACT] CRUD operations in `operations.py` call `session.commit()` explicitly within each function AND the `get_session()` context manager also calls `session.commit()` on exit. Double commit is harmless but indicates the CRUD layer was designed to work both with and without the context manager. [FACT: operations.py:113, 187, 220, 328, 452, 501]

[FACT] Agents bypass the CRUD layer: directly construct SQLAlchemy model instances and call `session.add()` + `session.commit()` instead of using CRUD functions in `operations.py`. This bypasses validation logic (`_validate_json_dict`, `_validate_json_list`). [PATTERN: hypothesis_generator.py:474-492, experiment_designer.py:888-903]

[FACT] Neo4j operations use individual `self.graph.create()`, `self.graph.push()`, `self.graph.run()` calls without explicit transaction boundaries. Each operation is an implicit auto-commit transaction via py2neo. There are no `begin_transaction()` / `tx.commit()` patterns anywhere. [ABSENCE: graph.py]

[FACT] No cross-backend transactions exist. When data is written to multiple backends, each write is independent. A failure in the knowledge graph does not roll back the JSON artifact or SQLAlchemy write. [ABSENCE: no distributed transaction coordinator]
# Shared State

## Shared State Index

| State | Location | Mutated By | Risk |
|-------|----------|------------|------|
| `_default_client` (LLM singleton) | `core/llm.py:609` | `get_client()`, any caller with `reset=True` | Thread-safe (double-checked locking), but reset replaces for all threads |
| `_config` (Config singleton) | `config.py:1137` | `get_config()`, `cli/commands/run.py` mutates fields directly | Config singleton prevents reconfiguration; CLI mutates global state |
| `_engine` / `_SessionLocal` (DB) | `db/__init__.py:22-23` | `init_database()`, `init_from_config()` | Hard failure if not initialized; double-init swallowed by director |
| `_knowledge_graph` (Neo4j) | `knowledge/graph.py:1000` | `get_knowledge_graph()` | May auto-start Docker (120s blocking); falls back to disconnected |
| `_world_model` (World model) | `world_model/factory.py:52` | `get_world_model()` | **NOT thread-safe** (documented); falls back to InMemoryWorldModel |
| `_event_bus` (Event bus) | `core/event_bus.py:261` | `get_event_bus()` | Standalone, no config dependency |
| `_experiment_cache` (Cache) | `core/experiment_cache.py:743` | `get_experiment_cache()` | Thread-safe via `threading.RLock()` |
| `_cache_manager` | `core/cache_manager.py:38` | `__new__` singleton | Config-dependent |
| `_tracker` (Stage tracker) | `core/stage_tracker.py:249` | `get_stage_tracker()` | Config-dependent |
| `_metrics_collector` | `monitoring/metrics.py:448` | `get_metrics_collector()` | Config-dependent |
| `_alert_manager` | `monitoring/alerts.py:535` | `get_alert_manager()` | Config-dependent |
| `_registry` (Agent registry) | `agents/registry.py:522` | `get_registry()` | Dormant -- never used in main loop |
| `_literature_analyzer` | `agents/literature_analyzer.py:1069` | Singleton accessor | Config + LLM client dependent |
| `_reference_manager` | `literature/reference_manager.py:799` | Singleton accessor | Config-dependent |
| `_global_registry` (Templates) | `experiments/templates/base.py:635` | Auto-discovery on first call | Scans filesystem |
| `_vector_db` (ChromaDB) | `knowledge/vector_db.py:444` | `get_vector_db()` | Optional; returns empty results if missing |
| `ResearchPlan` (in-memory) | `core/workflow.py:57` | `ResearchDirectorAgent` only | Protected by async + threading locks; state can diverge from workflow |
| `ResearchWorkflow.current_state` | `core/workflow.py:166` | `transition_to()`, but also public attribute | Bypass of `transition_to()` causes silent state divergence |
| `_actions_this_iteration` | `research_director.py` (hasattr) | `decide_next_action()` | Lazily initialized via hasattr, not in __init__ |
| `NoveltyDetector` index | `novelty_detector.py` (in-memory) | `index_past_tasks()`, `filter_redundant_tasks()` | No persistence; lost on restart |
| Provider usage counters | `core/providers/base.py:190-193` | `_update_usage_stats()` on every generate() | Instance-level only; no cross-instance aggregation |
| `ClaudeClient` usage counters | `core/llm.py` | Every `generate()` / `generate_structured()` call | Singleton, so effectively global |
| `RetryStrategy.repair_stats` | `execution/executor.py:711` | `record_repair_attempt()` | Per-CodeExecutor instance; not persisted |
| `MemoryStore` | `core/memory.py:66` | Designed but **not wired** into any agent | Dead infrastructure |
| `FeedbackLoop` | `core/feedback.py:76` | Designed but **not wired** into any agent | Dead infrastructure |

---

## Full Shared State Descriptions

---

### 1. LLM Client Singleton (`_default_client`)

**Location**: `kosmos/core/llm.py:609` -- module-level `_default_client: Optional[Union[ClaudeClient, LLMProvider]] = None`

**Lifecycle**: Created on first call to `get_client()`. Protected by `_client_lock` (threading.Lock) with double-checked locking pattern: fast-path check outside the lock, then re-check inside. [FACT: llm.py:643-649]

**Type ambiguity**: The singleton holds either `ClaudeClient` OR `LLMProvider`. The two types have different interfaces (`generate()` vs provider-specific methods), so callers must know which type they received or use `get_provider()` which asserts the type. `get_provider()` raises `TypeError` if the singleton is a `ClaudeClient` instead of `LLMProvider`. [FACT: llm.py:609, 700-706]

**Mutation**: `reset=True` from any thread replaces the client for all threads. This is safe for single-replace but callers holding a reference to the old client will use a stale instance. [FACT: llm.py:643-649]

**Thread safety**: Double-checked locking is safe. The lock is `threading.Lock`, not `asyncio.Lock`, so it works in both sync and async contexts. [FACT: llm.py:610]

**Risk**: MEDIUM. The Union type means callers can get `ClaudeClient` or `LLMProvider` depending on config and `use_provider_system` flag. Code that assumes one type may fail at runtime with the other. [FACT: llm.py:609]

**45 importers reference this module** (27 Python source importers + docs/tests). It is the most-imported singleton in the codebase.

---

### 2. Config Singleton (`_config`)

**Location**: `kosmos/config.py:1137`

**Lifecycle**: Created on first call to `get_config()`. Reads `.env` via Pydantic's `SettingsConfigDict.env_file`. On first call, also runs `create_directories()` to create log dirs and ChromaDB dirs. [FACT: config.py:1140-1154]

**Critical constraint**: `KosmosConfig` validates provider API keys at construction time (lines 1024-1043). If `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` is missing, the config singleton itself fails to construct. This means `.env` must be in place before ANY module that transitively calls `get_config()`. [FACT: config.py:1024-1043]

**Mutation**: Once `get_config()` is called, changing environment variables has no effect unless `get_config(reload=True)` is explicitly called. No module does this automatically. [FACT: config.py]

**CLI mutation**: `cli/commands/run.py:136-137` directly mutates the config singleton: `config_obj.research.enabled_domains = [domain]`. CLI parameter handling has side effects on the global config, potentially affecting other singletons that read from config later. [FACT: run.py:136-137]

**Lazy import pattern to break cycles**: 5 instances of `from kosmos.config import get_config` inside function bodies (not at module level): `world_model/factory.py:110`, `db/__init__.py:160`, `core/llm.py:655`, `cli/commands/run.py:129`, `core/stage_tracker.py:254`. This prevents import-time circular dependencies. [PATTERN]

**Thread safety**: No explicit locking on the config singleton. Since it is read-mostly after initialization and Pydantic models are immutable by default, this is generally safe. However, the CLI mutation of nested fields (`config_obj.research.enabled_domains = [domain]`) is not thread-safe.

**Risk**: MEDIUM. The config gates everything downstream. Failure to construct means no LLM, no DB, no world model. The CLI mutation of the global singleton is a hidden side effect.

---

### 3. Database Engine / Session Factory (`_engine`, `_SessionLocal`)

**Location**: `kosmos/db/__init__.py:22-23` -- module-level `_engine = None`, `_SessionLocal = None`

**Lifecycle**: Created by `init_database()` which is called by `init_from_config()`. Unlike other singletons, `get_session()` does NOT auto-initialize -- it raises `RuntimeError("Database not initialized. Call init_database() first.")` if `_SessionLocal is None`. This is the only singleton in the codebase that refuses to lazy-init. [FACT: db/__init__.py:126-127]

**Who initializes**: `ResearchDirectorAgent.__init__()` at line 131 calls `init_from_config()` defensively, catching errors if already initialized. This makes the Research Director the de facto DB initializer. [FACT: research_director.py:131-139]

**Engine strategy**: SQLite uses no connection pooling with `check_same_thread=False`. PostgreSQL uses `QueuePool` with `pool_size=5`, `max_overflow=10`, `pool_timeout=30`, `pool_pre_ping=True`. [FACT: db/__init__.py:26-105]

**Auto-creates tables**: `Base.metadata.create_all(bind=_engine)` runs on every startup. [FACT: db/__init__.py:100]

**Transaction boundaries**: `get_session()` is a `@contextmanager` providing auto-commit on success, auto-rollback on failure, always close. All callers use `with get_session() as session:`. [FACT: db/__init__.py:108-137]

**Double-commit**: CRUD operations in `operations.py` call `session.commit()` explicitly AND the context manager also commits on exit. Harmless but indicates the CRUD layer was designed for dual usage. [PATTERN: operations.py:113, 187, 220, 328, 452, 501]

**Agents bypass CRUD layer**: Agent classes directly construct SQLAlchemy model instances via `session.add()` + `session.commit()` instead of using CRUD functions in `operations.py`. This bypasses validation logic (`_validate_json_dict`, `_validate_json_list`). [PATTERN: hypothesis_generator.py:474-492, experiment_designer.py:888-903]

**Error recovery**: Agents use graceful degradation: if `get_session()` raises, the agent logs a warning and continues with a generated UUID. Protocol/hypothesis objects remain valid without DB persistence. [FACT: experiment_designer.py:908-919]

**Double-init DB pattern**: `ResearchDirectorAgent.__init__` calls `init_from_config()` and catches `RuntimeError`. If two Research Directors are created, the second swallows the "already initialized" error. This works but is fragile. [FACT: initialization findings]

**Data model**: Six SQLAlchemy ORM models: `Experiment` (FK to hypotheses), `Hypothesis`, `Result` (FK to experiments), `Paper`, `AgentRecord`, `ResearchSession`. All use `String` primary keys (application-generated UUIDs). [FACT: db/models.py]

**Risk**: MEDIUM. Hard failure if not initialized. The double-init swallowing pattern is fragile. Agents bypassing the CRUD layer skip validation.

---

### 4. Knowledge Graph Singleton (`_knowledge_graph`)

**Location**: `kosmos/knowledge/graph.py:1000`

**Lifecycle**: Created on first call to `get_knowledge_graph()`. Connection via `py2neo.Graph` with auth tuple. Connection failure is **non-fatal**: sets `self._connected = False` and `self.graph = None`. Callers check `self.connected` property. [FACT: graph.py:78-99]

**Docker auto-start**: `_ensure_container_running()` runs `subprocess.run(["docker-compose", "up", "-d", "neo4j"])` with a 60-second timeout, then polls up to 30 times with 2-second sleeps (max 60s). Total potential blocking time: **120 seconds** during first `KnowledgeGraph()` construction. This runs during `get_knowledge_graph()` -> `get_world_model()` -> `ResearchDirectorAgent.__init__()`. A user starting their first research run could wait 2+ minutes at the constructor. [FACT: graph.py:118-172]

**Index management**: Creates 8 indexes on initialization using `CREATE INDEX ... IF NOT EXISTS` Cypher for Paper (id, doi, arxiv_id, pubmed_id), Author (name), Concept (name, domain), Method (name, category). [FACT: graph.py:173-200]

**Node/Relationship types**: Four node types: Paper, Concept, Method, Author. Five relationship types: CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO. Full CRUD for each with `merge=True` default for upsert. [FACT: graph.py:28-30]

**Transaction boundaries**: Individual `self.graph.create()`, `self.graph.push()`, `self.graph.run()` calls without explicit transaction boundaries. Each is an implicit auto-commit via py2neo. No `begin_transaction()` / `tx.commit()` anywhere. [ABSENCE: graph.py]

**Risk**: LOW-MEDIUM. Docker side effects in constructors are surprising. No explicit transactions means no atomicity guarantees for multi-step graph operations.

---

### 5. World Model Singleton (`_world_model`)

**Location**: `kosmos/world_model/factory.py:52`

**Lifecycle**: Created on first call to `get_world_model()`. Reads mode from config: `simple` mode creates `Neo4jWorldModel`, checks `connected` property, falls back to `InMemoryWorldModel` if Neo4j unavailable. `production` mode raises `NotImplementedError`. [FACT: factory.py:108-155]

**Thread safety**: **Explicitly documented as NOT thread-safe** (`factory.py:38`). The `_world_model` global has no lock, unlike `_default_client` which has `_client_lock`. [FACT: factory.py:38, initialization findings]

**Neo4j graceful degradation**: If `Neo4jWorldModel` cannot connect (`wm.graph.connected` is False), the factory silently falls back to `InMemoryWorldModel`. A warning is logged but no exception raised. Data does not persist with InMemoryWorldModel. [FACT: factory.py:124-131]

**Write-only from agents' perspective**: Only `ResearchDirectorAgent` writes to the world model. No other agent imports `world_model` or `get_world_model`. The knowledge graph is a write-only audit log. [ABSENCE: agent_communication.md]

**Three implementations**: `Neo4jWorldModel` (wraps `KnowledgeGraph` via Adapter), `InMemoryWorldModel` (dict-based for testing), `ArtifactStateManager` (JSON file-based, independent of WorldModelStorage interface). [FACT: simple.py, in_memory.py, artifacts.py]

**Data models**: Uses Python dataclasses (not SQLAlchemy): `Entity` (11 standard types, confidence scores, project namespacing, verification flags), `Relationship` (12 standard types, provenance metadata), `Annotation`. `to_dict()`/`from_dict()` for JSON import/export. [FACT: world_model/models.py]

**Risk**: HIGH. Not thread-safe. If concurrent access occurs during initialization, two different world model instances could be created, or a half-initialized instance could be returned.

---

### 6. ResearchPlan (In-Memory Shared State)

**Location**: `kosmos/core/workflow.py:57-95` -- Pydantic BaseModel instance held by `ResearchDirectorAgent`

**Lifecycle**: Created during `ResearchDirectorAgent.__init__()`. Lives for the duration of the research run. Stores hypothesis IDs, experiment queue IDs, result IDs, iteration count, convergence status, timestamps.

**Access control**: Only `ResearchDirectorAgent` reads/writes the `ResearchPlan`. It is not shared with sub-agents. Access is protected by `self._research_plan_lock` (asyncio.Lock) and `self._research_plan_lock_sync` (threading.RLock). [FACT: research_director.py:192-200]

**State duplication risk**: `ResearchPlan.current_state` and `ResearchWorkflow.current_state` can diverge if the workflow is modified without going through `transition_to()`. The sync happens only inside `transition_to()` at line 323-325. If any code modifies `workflow.current_state` directly (possible since it is a public attribute), the plan's state diverges silently. [FACT: workflow.py:323-325]

**ID-based tracking only**: Stores only string IDs, not actual objects. No knowledge of the database. All list operations use `if x not in list` for deduplication. For large pools, `get_untested_hypotheses()` is O(n*m) because `tested_hypotheses` is a list, not a set. [FACT: workflow.py:68-78, 149-151]

**`use_enum_values=True`**: Enum fields are stored as string values, not enum instances. `isinstance` checks against enum types fail after serialization round-trips. [FACT: workflow.py:48, 60]

**Mutation methods**: `add_hypothesis(id)`, `mark_tested(id)`, `mark_supported(id)`, `mark_rejected(id)`, `add_experiment(id)`, `mark_experiment_complete(id)`. All are append-only with deduplication. `mark_supported` and `mark_rejected` both call `mark_tested` internally. [FACT: workflow.py:100-136]

**The sync `_workflow_context()` context manager**: Yields `self.workflow` without any lock. Comment says "not used with async". But if sync code uses this while async code uses the async lock, there is no mutual exclusion between the two paths. [FACT: research_director.py:376-379]

**Risk**: MEDIUM. State duplication between plan and workflow is a consistency hazard. The O(n*m) performance of `get_untested_hypotheses()` could become a bottleneck with large hypothesis pools.

---

### 7. ResearchWorkflow.current_state (Public Attribute)

**Location**: `kosmos/core/workflow.py:166` -- `ResearchWorkflow` class

**Lifecycle**: Initialized to `WorkflowState.INITIALIZING`. Modified by `transition_to()` which validates against `ALLOWED_TRANSITIONS` and records `WorkflowTransition` objects in history.

**Mutation**: `transition_to()` is the sanctioned mutation path -- it validates, records history, and syncs `ResearchPlan.current_state`. **However**, `current_state` is a public attribute that can be written directly, bypassing all validation and sync. [FACT: workflow.py:319]

**State transitions**: ALLOWED_TRANSITIONS defines the adjacency list. `PAUSED` can resume to 6 different states (soft reset). `CONVERGED` can transition back to `GENERATING_HYPOTHESES` (not truly terminal). [FACT: workflow.py:175-227, 212-221]

**PAUSED has no memory**: There is no mechanism to remember which state was active before pausing. The caller must decide where to resume. [FACT: workflow.py:214-221]

**Risk**: MEDIUM. The public attribute bypass is a consistency hazard. The non-terminal CONVERGED state can surprise callers that assume convergence is final.

---

### 8. `_actions_this_iteration` Counter

**Location**: `kosmos/agents/research_director.py` -- dynamically created via `hasattr` check

**Lifecycle**: NOT initialized in `__init__`. Created lazily in `decide_next_action()` using `if not hasattr(self, '_actions_this_iteration')`. This is inconsistent with all other instance variables. [FACT: research_director.py:2451-2452]

**Purpose**: Infinite loop guard. `MAX_ACTIONS_PER_ITERATION = 50` (module constant). If the counter exceeds this, `decide_next_action()` forces `NextAction.CONVERGE`. [FACT: research_director.py:50, 2455-2461]

**Risk**: LOW. Works correctly but the `hasattr` pattern is surprising and inconsistent.

---

### 9. NoveltyDetector Index (In-Memory)

**Location**: `kosmos/orchestration/novelty_detector.py` -- `self.task_embeddings`, `self.task_texts`, `self.task_metadata`

**Lifecycle**: Empty at construction. Populated by `index_past_tasks()`. Lost on process restart -- no persistence.

**Mutation**: `index_past_tasks()` computes embeddings and appends to internal lists. `filter_redundant_tasks()` temporarily saves, indexes, checks, then restores the original (copy-restore pattern). [FACT: novelty_detector.py:320-342]

**Shallow copy concern**: `filter_redundant_tasks` copies Python lists but not numpy arrays deeply. The `copy()` on a list of numpy arrays produces a shallow copy, which should be safe since `index_past_tasks` extends (appends) rather than mutates, but is worth noting. [FACT: novelty_detector.py:320-342]

**Similarity threshold discrepancy**: `similar_tasks` list filters by hardcoded 0.6 threshold, even when the novelty threshold is set to 0.75. [FACT: novelty_detector.py:171]

**Task text format**: Uses `"{type}: {description}"` concatenation. Type is included in similarity comparison. [FACT: novelty_detector.py:100-102, 140-142]

**Risk**: LOW. In-memory only. Process restart loses all history. No thread safety issues since the detector is used within a single orchestration cycle.

---

### 10. Provider Usage Counters

**Location**: `kosmos/core/providers/base.py:190-193` -- instance attributes `total_input_tokens`, `total_output_tokens`, `total_cost_usd`, `request_count`

**Lifecycle**: Zeroed at `LLMProvider.__init__()`. Incremented by `_update_usage_stats()` after every generate() call. Reset by `reset_usage_stats()`.

**Instance-level only**: Token counts and cost are accumulated on the provider instance. There is no global/shared tracking across multiple provider instances. [FACT: base.py:190-193]

**Zero-cost bug**: `_update_usage_stats` skips cost when `cost_usd` is exactly `0.0` (falsy). Free-tier API calls reporting `cost_usd=0.0` will not accumulate, making cost tracking slightly inaccurate. [FACT: base.py:401]

**Risk**: LOW. Instance-level tracking is safe. The zero-cost bug is minor.

---

### 11. ClaudeClient Usage Counters

**Location**: `kosmos/core/llm.py` -- `ClaudeClient` instance attributes

**Lifecycle**: Initialized in `ClaudeClient.__init__()`. Mutated on every call (`_api_calls`, `_cache_hits`, `_cache_misses`, `_total_input_tokens`, `_total_output_tokens`, `_total_cost`, model selection stats). Since `ClaudeClient` is accessed via the singleton `get_client()`, these are effectively global counters.

**Cost estimation hardcode**: `get_usage_stats()` hardcodes `"claude-sonnet-4-5"` model name for cost lookup regardless of what model was actually used. [FACT: llm.py:519]

**CLI mode cost**: In CLI mode, cost is always $0.00. [FACT: llm.py:587-588]

**Risk**: LOW. Singleton means all code shares the same counters, which is the desired behavior for usage tracking.

---

### 12. RetryStrategy.repair_stats

**Location**: `kosmos/execution/executor.py:711` -- `self.repair_stats` dict

**Lifecycle**: Initialized in `RetryStrategy.__init__()`. Mutated by `record_repair_attempt()` which tracks per-error-type success/failure counts.

**Per-instance**: Each `CodeExecutor` creates its own `RetryStrategy` with its own `repair_stats`. The stats are not persisted or aggregated across executor instances.

**Risk**: LOW. Per-instance, not shared.

---

### 13. MemoryStore (Designed But Not Wired)

**Location**: `kosmos/core/memory.py:66-104`

**Purpose**: Designed for storing success/failure patterns, dead ends, and insights with experiment deduplication.

[ABSENCE] Searched for usage of `MemoryStore` in the agents directory and the research director. It is not imported or instantiated by any agent. The infrastructure exists but is not wired into the active research loop. This appears to be Phase 7 infrastructure that was designed but not integrated.

**Risk**: NONE (not used). But someone discovering it might assume it is active.

---

### 14. FeedbackLoop (Designed But Not Wired)

**Location**: `kosmos/core/feedback.py:76-105`

**Purpose**: Designed for learning from experimental results.

[ABSENCE] Same status as MemoryStore -- designed but not wired into any agent's active code path. No agent imports `FeedbackLoop`.

**Risk**: NONE (not used). Same confusion risk as MemoryStore.

---

### 15. Event Bus Singleton (`_event_bus`)

**Location**: `kosmos/core/event_bus.py:261`

**Lifecycle**: Standalone singleton with no config dependency. Created on first call to `get_event_bus()`.

**Purpose**: Pub/sub for typed events: `WORKFLOW_FAILED`, `CYCLE_FAILED`, `TASK_FAILED`, `LLM_CALL_FAILED`, `CODE_FAILED`. Used by CLI/API consumers. [FACT: events.py:22-46]

**Risk**: LOW. Standalone, no external dependencies.

---

### 16. Experiment Cache Singleton (`_experiment_cache`)

**Location**: `kosmos/core/experiment_cache.py:743`

**Lifecycle**: Uses **raw sqlite3** (not SQLAlchemy) for a dedicated cache database, completely independent of the main SQLAlchemy database. Creates its own schema with `experiments` and `cache_stats` tables. [FACT: experiment_cache.py:231, 240-298]

**Thread safety**: Via `threading.RLock()`. All public methods acquire the lock, serializing all cache operations. [FACT: experiment_cache.py:220]

**Connection pattern**: Every operation creates a new `sqlite3.connect()`, performs work, commits, then closes. No connection pooling, no persistent connections. Safe for SQLite but would be costly for server databases. [PATTERN: experiment_cache.py:349, 579, 604, 662]

**Error handling split**: `cache_experiment()` catches Exception and **re-raises** (write integrity). `get_cached_result()` catches Exception and **returns None** (read tolerance). [FACT: experiment_cache.py:391-446]

**Risk**: LOW. Thread-safe. Independent from main DB.

---

### 17. ChromaDB Vector Store (`_vector_db`)

**Location**: `kosmos/knowledge/vector_db.py:444`

**Lifecycle**: Module-level singleton via `get_vector_db()`. Supports `reset` parameter for testing. Optional dependency -- if ChromaDB not installed, `client=None` and all operations return empty results. [FACT: vector_db.py:444-477]

**Storage**: Uses `chromadb.PersistentClient` with filesystem persistence. Collections use `cosine` similarity metric. Documents stored as `"title [SEP] abstract"` with abstracts truncated to 1000 chars. [FACT: vector_db.py:79-84, 97-100, 419-440]

**Batch insertion**: `add_papers()` batch-inserts with `batch_size=100` chunks. No transaction management -- ChromaDB handles internally. [FACT: vector_db.py:129-182]

**Risk**: LOW. Optional, self-contained.

---

### 18. Dual Model System (Cross-Cutting Shared State)

[PATTERN] The codebase has two parallel data model systems, both representing the same research entities:

1. **SQLAlchemy ORM models** (`kosmos/db/models.py`) -- `Hypothesis`, `Experiment`, `Result`, etc. Used by agents for CRUD. String primary keys (application-generated UUIDs).
2. **Dataclass models** (`kosmos/world_model/models.py`) -- `Entity`, `Relationship`, `Annotation`. Used by world model for graph operations. Has factory methods (`from_hypothesis()`, `from_protocol()`, `from_result()`) to convert.

Agents like `ResearchDirectorAgent` write to BOTH: SQLAlchemy for structured queries, world model for graph traversal. There is no automatic synchronization between the two systems. Each persistence path has its own error handling (SQLAlchemy re-raises; world model catch-and-log). A failure in one does not affect the other. [FACT: research_director.py:388-562, db/models.py, world_model/models.py]

**Risk**: MEDIUM. Two representations of the same data can diverge. If a hypothesis is stored in SQLAlchemy but the world model write fails (silently caught), the graph is incomplete. No reconciliation mechanism exists.

---

### 19. ArtifactStateManager (File-Based State)

**Location**: `kosmos/world_model/artifacts.py:146-178`

**4-layer hybrid architecture**: Layer 1: JSON artifacts (always active, human-readable files). Layer 2: Knowledge graph (optional, indexes to world model). Layer 3: Vector store (stub, not implemented). Layer 4: Citation tracking (in JSON layer). [FACT: artifacts.py:146-178]

**Storage pattern**: Findings saved as `artifacts/cycle_{N}/task_{M}_finding.json`. Hypotheses as `artifacts/hypotheses/{hypothesis_id}.json`. Also cached in `_findings_cache` dict. [FACT: artifacts.py:199-275]

**Retrieval**: `get_finding()` checks in-memory cache first, falls back to filesystem glob `cycle_*/task_*_finding.json` and linear scan. No index -- O(n) lookup by finding_id. [FACT: artifacts.py:277-300]

**No cross-backend transactions**: Each write is independent. A failure in Layer 2 (graph) does not roll back Layer 1 (JSON). The `_index_finding_to_graph` method catches all exceptions and logs warnings. [ABSENCE: no distributed transaction coordinator]

**Used in research loop**: `workflow/research_loop.py:336-341` calls `self.state_manager.save_finding_artifact()` for each validated finding, making it the primary persistence layer for research results. [FACT: research_loop.py:336-341]

**Risk**: MEDIUM. O(n) lookup scales poorly. No atomicity across layers.

---

### 20. `_DEFAULT_CLAUDE_*_MODEL` Constants (Hidden Shared State)

**Location**: `kosmos/config.py:17-18`

```python
_DEFAULT_CLAUDE_SONNET_MODEL = "claude-sonnet-4-5"
_DEFAULT_CLAUDE_HAIKU_MODEL = "claude-haiku-4-5"
```

[PATTERN] These two underscore-prefixed "private" constants are imported by 7+ files: `core/providers/anthropic.py`, `core/providers/litellm_provider.py`, `core/llm.py`, `validation/scholar_eval.py`, `compression/compressor.py`, `orchestration/plan_reviewer.py`, `orchestration/plan_creator.py`, `models/hypothesis.py`, `models/experiment.py`, `models/domain.py`. They are effectively public API despite the underscore prefix. Renaming or removing them would break 7+ consumers with no warning. [FACT: hidden_coupling.md]

**Risk**: LOW. Constants, not mutable state. But the "private" naming is misleading.

---

### 21. The Flat Config Dict (Hidden Shared Contract)

[PATTERN] 3 places bridge structured config to flat dicts: `core/providers/factory.py:107-170`, `cli/commands/run.py:148-170`, and `core/llm.py:655-676`. Each manually extracts fields from Pydantic models into `dict[str, Any]`. There is no shared schema for these dicts, so each bridging point can drift independently.

The `flat_config` dict keys (e.g., `"max_iterations"`, `"budget_usd"`, `"data_path"`) are string-based. No schema validates that `run.py` passes the right keys or that the director reads the right ones. A typo in either file fails silently (the director's `self.config.get()` returns None for missing keys). [FACT: hidden_coupling.md]

**Risk**: MEDIUM. Silent failure on typos. No type safety on the bridging layer.

---

### 22. Initialization DAG (Ordering Constraints)

[PATTERN] The initialization has a strict ordering:

```
Level 0: .env file + environment variables
    |
Level 1: get_config() -- validates API keys, creates directories
    |
    +-- get_client() -- LLM provider from config
    +-- init_database() / init_from_config() -- SQLAlchemy engine
    +-- get_knowledge_graph() -- Neo4j (may auto-start Docker: 120s blocking)
    +-- get_stage_tracker() -- stage tracking from config
    |
Level 2:
    +-- get_world_model() -- depends on config + knowledge_graph, falls back to in-memory
    +-- ResearchDirectorAgent.__init__() -- depends on all of Level 1
```

**Critical**: Database must init before use (hard `RuntimeError`). Config validation gates everything. Neo4j Docker auto-start can block for 120 seconds. [FACT: initialization.md]

**Import safety**: `import kosmos` triggers module loads but NOT singleton construction. All singletons are guarded by `get_*()` factory functions. This is deliberate and safe. [ABSENCE: initialization.md]

**Provider registration at import time**: `core/providers/factory.py:216-217` calls `_register_builtin_providers()` at module level, importing `anthropic.py`, `openai.py`, `litellm_provider.py`. Each sets a `HAS_*` flag if the package is available. No crash if packages missing. [FACT: factory.py:216-217]

**Risk**: MEDIUM. The 120-second Docker blocking on first use is the most impactful ordering constraint. The hard DB init requirement means any code path that reaches `get_session()` before `init_database()` crashes.

---

### 23. Agent Communication Shared State (Hub-and-Spoke)

**Data flow**: The research director is the sole coordinator. Data between agents flows through three channels:

1. **SQLAlchemy Database** -- primary medium for persistent data exchange. All 5 agent types use `get_session()`. Write pattern: agent creates object, writes to DB, returns ID. Director reads it back for the next agent. [FACT: agent_communication.md]

2. **Knowledge Graph (World Model)** -- write-only audit log. Only ResearchDirectorAgent writes. No other agent reads. Creates entities and relationships: SPAWNED_BY, TESTS, PRODUCED_BY, SUPPORTS/REFUTES, REFINED_FROM. [FACT: research_director.py:242-255]

3. **ResearchPlan (In-Memory)** -- only the director reads/writes. Protected by async + threading locks. [FACT: workflow.py:57-95]

**Data passed to sub-agents**: `research_question` (string), `domain` (string), `config` (dict, shared from director), entity IDs for database lookups. [PATTERN: agent_communication.md]

**Data returned by sub-agents**: Pydantic model objects (`HypothesisGenerationResponse`, `ExperimentDesignResponse`, `ResultInterpretation`), from which the director extracts IDs and scalar fields. [PATTERN: agent_communication.md]

**No peer-to-peer**: Agents do not communicate directly during normal operation. The director mediates all data flow. [FACT: agent_communication.md]

**Risk**: LOW-MEDIUM. The hub-and-spoke model is simple and avoids distributed state issues. The main risk is the director as a single point of failure.

---

### 24. Concurrency Model (Locks and Shared Access)

**Director locks**: `_research_plan_lock`, `_strategy_stats_lock`, `_workflow_lock`, `_agent_registry_lock` (all `asyncio.Lock`), plus threading counterparts (`_research_plan_lock_sync` as RLock, `_strategy_stats_lock_sync` as Lock) for sync compatibility. [FACT: research_director.py:192-200]

**Optional concurrent execution**: `enable_concurrent_operations`, `max_parallel_hypotheses=3`, `max_concurrent_experiments=4`, backed by `ParallelExperimentExecutor` and `AsyncClaudeClient`. Default mode is sequential. Concurrency is opt-in via config with multiple fallback paths to sequential execution. [FACT: research_director.py:203-239]

**Concurrent hypothesis evaluation**: Up to `max_parallel_hypotheses` evaluated simultaneously via `asyncio.wait_for()` with 300-second timeout, falling back to sequential on failure. [FACT: research_director.py:2585-2619]

**Batch experiment execution**: Via `ParallelExperimentExecutor` when `enable_concurrent=True`. Sequential fallback calls `asyncio.get_event_loop().run_until_complete()` which raises `RuntimeError` if an event loop is already running. [FACT: research_director.py:2171-2174, 2631-2637]

**Risk**: MEDIUM. The dual async/threading lock strategy is complex. The sync `_workflow_context()` yields without any lock while async code uses `_workflow_lock`. The sequential fallback's `run_until_complete()` can crash if already in async context.
# Domain Glossary

| Term | Means Here | Defined In |
|------|------------|------------|
| `BaseAgent` | Abstract base class providing lifecycle management (CREATED->RUNNING->STOPPED), async message passing, state persistence, and health monitoring for all 6 Kosmos agent types | `kosmos/agents/base.py:97-111` |
| `AgentMessage` | Pydantic model serving as the wire format for all inter-agent communication; fields include `from_agent`, `to_agent`, `content`, `message_type`, `correlation_id`, `timestamp` | `kosmos/agents/base.py:44-84` |
| `AgentStatus` | Enum of agent lifecycle states: CREATED, STARTING, RUNNING, PAUSED, STOPPED, ERROR, IDLE, WORKING | `kosmos/agents/base.py` |
| `AgentRegistry` | Central registry that calls `agent.set_message_router()` on every registered agent to enable inter-agent message delivery | `kosmos/agents/registry.py:94` |
| `ResearchDirectorAgent` | Master orchestrator agent driving the full research cycle (hypothesize->design->execute->analyze->refine->iterate); inherits from `BaseAgent`; coordinates 6+ specialized agents | `kosmos/agents/research_director.py:1-12` |
| `AnthropicProvider` | Concrete `LLMProvider` implementation for Anthropic Claude with sync/async generation, streaming, structured JSON, caching, auto model selection, cost tracking, and CLI mode | `kosmos/core/providers/anthropic.py` |
| `ClaudeClient` | Backward compatibility alias for `AnthropicProvider`; also the legacy wrapper class in `llm.py` adding caching and auto model selection | `anthropic.py:881`, `llm.py:154` |
| CLI mode | An undocumented operational mode triggered when the API key consists entirely of the digit 9 (`api_key.replace('9','') == ''`); routes requests through Claude Code CLI; disables cost calculation and auto-model-selection | `anthropic.py:110`, `llm.py:179` |
| `LLMProvider` | Abstract base class defining the unified interface (`generate`, `generate_async`, `generate_with_messages`, `generate_structured`, `generate_stream`) that all LLM backends must implement | `kosmos/core/providers/base.py:170-410` |
| `LLMResponse` | Dataclass returned by all `generate()` calls; masquerades as `str` via 20+ delegated string methods but `isinstance(x, str)` returns False; losing metadata on any string method call | `kosmos/core/providers/base.py:57-154` |
| `Message` | Simple dataclass (`role`, `content`, `name`, `metadata`) used as input to `generate_with_messages()`; the multi-turn conversation format | `kosmos/core/providers/base.py:18-31` |
| `UsageStats` | Dataclass tracking token counts (`input_tokens`, `output_tokens`, `total_tokens`), cost, model, provider, and timestamp for a single LLM call | `kosmos/core/providers/base.py:35-54` |
| `ProviderAPIError` | Canonical exception for LLM provider failures; has `is_recoverable()` heuristic (explicit flag -> HTTP status -> message patterns) that controls retry behavior system-wide | `kosmos/core/providers/base.py:429-484` |
| `ModelComplexity` | Static utility class that scores prompt complexity (0-100) via token estimation and keyword matching, recommending "haiku" (score <30) or "sonnet" (all else); never recommends higher than Sonnet | `kosmos/core/llm.py:52-105` |
| `get_client()` | Thread-safe singleton accessor returning either `ClaudeClient` or `LLMProvider` depending on `use_provider_system` flag; the global entry point for all LLM access | `kosmos/core/llm.py:613-679` |
| `get_provider()` | Wrapper around `get_client(use_provider_system=True)` that asserts the result is an `LLMProvider`; raises `TypeError` if not | `kosmos/core/llm.py:682-706` |
| `PaperMetadata` | Stdlib `@dataclass` (NOT Pydantic) representing a paper across all literature sources; contains identifiers, metadata, citation counts, raw API data; no validation | `kosmos/literature/base_client.py:36` |
| `PaperSource` | Five-value `str` enum: `ARXIV`, `SEMANTIC_SCHOLAR`, `PUBMED`, `UNKNOWN`, `MANUAL`; identifies the origin of a paper | `kosmos/literature/base_client.py:17` |
| `Author` | Stdlib `@dataclass` with `name` (required), optional `affiliation`, `email`, `author_id` | `kosmos/literature/base_client.py:27` |
| `BaseLiteratureClient` | ABC that all literature API clients (arXiv, Semantic Scholar, PubMed) must inherit; defines `search()`, `get_paper_by_id()`, `get_paper_references()`, `get_paper_citations()` | `kosmos/literature/base_client.py:125` |
| `Hypothesis` | Core Pydantic model for a scientific hypothesis; contains statement, rationale, domain, status, four float scores (testability, novelty, confidence, priority), experiment suggestions, and evolution tracking | `kosmos/models/hypothesis.py:32` |
| `HypothesisStatus` | Six-value lifecycle enum: `GENERATED`, `UNDER_REVIEW`, `TESTING`, `SUPPORTED`, `REJECTED`, `INCONCLUSIVE` | `kosmos/models/hypothesis.py:22` |
| `ExperimentType` | Three-value enum (`COMPUTATIONAL`, `DATA_ANALYSIS`, `LITERATURE_SYNTHESIS`) defining what kind of experiment can test a hypothesis; defined in hypothesis.py despite the name, re-imported by experiment.py | `kosmos/models/hypothesis.py:15-19` |
| `PrioritizedHypothesis` | Wrapper adding composite priority scoring (novelty 30%, feasibility 25%, impact 25%, testability 20%) plus rank and rationale to a `Hypothesis` | `kosmos/models/hypothesis.py:299` |
| `NoveltyReport` | Pydantic model for detailed novelty analysis: similar work detection, max similarity score, prior art flag, summary | `kosmos/models/hypothesis.py:240` |
| `TestabilityReport` | Pydantic model for testability analysis: experiment suggestions, resource estimates, challenges, recommendation | `kosmos/models/hypothesis.py:265` |
| `ExperimentProtocol` | Central Pydantic model tying together hypothesis, steps, variables, control groups, statistical tests, resources, validation, and reproducibility metadata; the data contract for the experiment subsystem | `kosmos/models/experiment.py:329` |
| `ProtocolStep` | Pydantic model for a single experiment step with number, title, description, action, dependencies, expected outputs, and code hints; `validate_steps` silently sorts by step_number | `kosmos/models/experiment.py:138` |
| `Variable` / `VariableType` | Experiment variable model with type enum (`INDEPENDENT`, `DEPENDENT`, `CONTROL`, `CONFOUNDING`), name, description, and measurement info | `kosmos/models/experiment.py:42, 21` |
| `ControlGroup` | Pydantic model for control groups with defensive `coerce_sample_size` validator that converts LLM string output to int and clamps to `_MAX_SAMPLE_SIZE` (100,000) | `kosmos/models/experiment.py:81` |
| `StatisticalTestSpec` | Pydantic model specifying a statistical test with `parse_effect_size` validator that extracts floats from LLM text like `"Medium (Cohen's d = 0.5)"` | `kosmos/models/experiment.py:235` |
| `StatisticalTest` | Nine-value enum of common statistical tests (T_TEST, ANOVA, CHI_SQUARE, etc.) plus `CUSTOM` | `kosmos/models/experiment.py:29` |
| `_MAX_SAMPLE_SIZE` | Module-private constant (100,000) used as a hard ceiling in multiple validators; silently clamps sample sizes | `kosmos/models/experiment.py:19` |
| `ExperimentResult` | Central Pydantic result model combining status, raw/processed data, variable results, statistical tests, primary metrics, metadata, and timestamps; 27 importers | `kosmos/models/result.py:127-205` |
| `ResultStatus` | Five-value enum: `SUCCESS`, `FAILED`, `PARTIAL`, `TIMEOUT`, `ERROR` | `kosmos/models/result.py:16-22` |
| `StatisticalTestResult` | Pydantic model for one statistical test result with statistic, p-value (constrained to [0,1]), effect size, confidence intervals, significance at 3 alpha levels | `kosmos/models/result.py:61-103` |
| `VariableResult` | Pydantic model with summary statistics (mean, median, std, min, max, values, counts) for one variable | `kosmos/models/result.py:105-124` |
| `ExecutionMetadata` | Pydantic model capturing execution context: timestamps, system info, resource usage, sandbox/timeout flags | `kosmos/models/result.py:25-58` |
| `ResultExport` | Export wrapper supporting JSON, CSV (requires `pandas`), and Markdown formats; `export_markdown()` crashes on `None` stats | `kosmos/models/result.py:280-377` |
| `CodeTemplate` | Base class for experiment code templates; `matches(protocol)` determines if a template applies; `generate(protocol)` produces executable Python code | `kosmos/execution/code_generator.py:27-45` |
| `ExperimentCodeGenerator` | Hybrid code generator: template matching (5 templates) -> LLM fallback -> basic template; validates syntax; LLM client has double fallback (ClaudeClient -> LiteLLMProvider -> disabled) | `kosmos/execution/code_generator.py:741-833` |
| Synthetic data fallback | Pattern in all code templates (except basic fallback): `if 'data_path' in dir() and data_path:` tries real data, else generates synthetic data with `np.random.seed()` | `code_generator.py:112-130, etc.` |
| `CodeValidator` | Safety gate that runs 6 checks (syntax, dangerous imports, dangerous patterns, network, AST calls, ethical guidelines) on generated code; produces `SafetyReport`; gates ALL code execution | `kosmos/safety/code_validator.py` |
| `SafetyReport` | Pydantic model returned by `CodeValidator.validate()` with violations, warnings, risk level, and `passed` flag (True only if zero violations) | `kosmos/models/safety` |
| `DANGEROUS_MODULES` | List of blocked import modules (includes `os`, `subprocess`, `shutil`, etc.); any `import X` where X is in this list triggers CRITICAL violation | `kosmos/safety/code_validator.py:36` |
| `DANGEROUS_PATTERNS` | List of blocked code patterns (`eval(`, `exec(`, `__import__(`, etc.) checked via raw string matching (`if pattern in code:`); matches inside comments and strings | `kosmos/safety/code_validator.py:283-320` |
| Ethical guidelines | Keyword-based screening against configurable guidelines (JSON file or defaults); keywords like "harm", "email", "password" trigger violations; high false-positive risk | `kosmos/safety/code_validator.py:386-418` |
| `CodeExecutor` | Executes Python/R code with restricted builtins sandbox, timeout, profiling, determinism testing, and retry logic; return value extracted by convention from `results`/`result` variable | `kosmos/execution/executor.py:174-376` |
| `ExecutionResult` | Data container returned by `CodeExecutor.execute()` with `success`, `return_value`, `stdout`, `stderr`, `error`, `error_type`, `execution_time` | `kosmos/execution/executor.py:113-159` |
| `SAFE_BUILTINS` | Whitelist of ~80 safe Python builtins used when Docker sandbox unavailable; includes `hasattr` but NOT `getattr`/`setattr`/`delattr` | `kosmos/execution/executor.py:43-83` |
| `_ALLOWED_MODULES` | Set of ~30 scientific/stdlib modules permitted by the restricted import function | `kosmos/execution/executor.py:86-94` |
| `RetryStrategy` | Self-correcting code repair: dispatches to error-type-specific fixers (11 types); LLM repair only on attempts 1-2; most fixes wrap entire code in try/except masking the original error | `kosmos/execution/executor.py:699-825` |
| `execute_protocol_code()` | Convenience function always running `CodeValidator.validate()` before `CodeExecutor.execute()`; creates a fresh executor per call | `kosmos/execution/executor.py:1017-1066` |
| `ConvergenceDetector` | Evaluates stopping criteria (iteration limit, hypothesis exhaustion, novelty decline, diminishing returns) in priority order to decide when the research loop stops | `kosmos/core/convergence.py` |
| `StoppingDecision` | Return type of convergence checks with `should_stop` (bool), `reason` (StoppingReason), and `confidence` (float) | `kosmos/core/convergence.py` |
| `StoppingReason` | Enum of convergence reasons; `USER_REQUESTED` is used as sentinel for "no reason" when research continues | `kosmos/core/convergence.py` |
| `ConvergenceReport` | Final research summary model with statistics, supported/rejected hypotheses, summary text, and recommended next steps; has `to_markdown()` method | `kosmos/core/convergence.py` |
| `novelty_trend` | Unbounded list in `ConvergenceMetrics` that accumulates novelty scores on every `check_convergence` call; never truncated | `kosmos/core/convergence.py:562` |
| `min_experiments_before_convergence` | Config value (default 2) that can defer the iteration limit if too few experiments have completed | `kosmos/core/convergence.py:206` |
| `WorkflowState` | Nine-value enum of research workflow states: INITIALIZING, GENERATING_HYPOTHESES, DESIGNING_EXPERIMENTS, EXECUTING, ANALYZING, REFINING, CONVERGED, PAUSED, ERROR | `kosmos/core/workflow.py:18-29` |
| `NextAction` | Eight-value enum of research actions: GENERATE_HYPOTHESIS, DESIGN_EXPERIMENT, EXECUTE_EXPERIMENT, ANALYZE_RESULT, REFINE_HYPOTHESIS, CONVERGE, PAUSE, ERROR_RECOVERY | `kosmos/core/workflow.py:32-43` |
| `ResearchWorkflow` | State machine with transition validation against `ALLOWED_TRANSITIONS` dict and history tracking; `transition_to()` raises `ValueError` on invalid transition | `kosmos/core/workflow.py:166-416` |
| `ResearchPlan` | Pydantic model tracking the full research state: question, domain, hypothesis pool (IDs only), experiment queue (IDs), results (IDs), iteration count, convergence status | `kosmos/core/workflow.py:57-95` |
| `ALLOWED_TRANSITIONS` | Dict mapping each `WorkflowState` to its valid target states; notably `CONVERGED` can return to `GENERATING_HYPOTHESES` and `PAUSED` can resume to 6 states | `kosmos/core/workflow.py:170-230` |
| `KnowledgeGraph` | Neo4j-backed graph for scientific literature with CRUD on Paper/Concept/Method/Author nodes and CITES/USES_METHOD/DISCUSSES/AUTHORED/RELATED_TO relationships; auto-starts Docker container | `kosmos/knowledge/graph.py` |
| `get_knowledge_graph()` | Module-level singleton factory for `KnowledgeGraph`; first call may trigger Docker auto-start and up to 60s blocking | `kosmos/knowledge/graph.py:999-1038` |
| `PaperVectorDB` | ChromaDB wrapper for persistent vector search over papers using SPECTER embeddings (768-dim); cosine similarity; optional dependency with graceful degradation | `kosmos/knowledge/vector_db.py` |
| `get_vector_db()` | Module-level singleton factory for `PaperVectorDB`; not thread-safe; `reset=True` replaces for all callers | `kosmos/knowledge/vector_db.py:443-477` |
| SPECTER | Scientific paper embedding model (768-dim) used by `PaperVectorDB` for computing paper similarity; ~440MB download on first use | `kosmos/knowledge/embeddings.get_embedder()` |
| `[SEP]` | Separator token used in vector DB document text: `title [SEP] abstract`; downstream parsers must know this format | `kosmos/knowledge/vector_db.py:440` |
| `WorldModelStorage` | ABC defining 10 abstract methods for persistent knowledge graph operations; two implementations: `Neo4jWorldModel` (adapter over `KnowledgeGraph`) and `InMemoryWorldModel` (dict-based fallback) | `kosmos/world_model/interface.py:36-367` |
| `EntityManager` | Separate ABC adding `verify_entity`, `add_annotation`, `get_annotations` for entity curation (Phase 2); not part of `WorldModelStorage` | `kosmos/world_model/interface.py:370-433` |
| `ProvenanceTracker` | ABC for PROV-O tracking (Phase 4) with `record_derivation`, `get_provenance`; NOT implemented by any current class | `kosmos/world_model/interface.py:436-513` |
| `Entity` | Stdlib dataclass with 10 fields (type, properties, id, confidence, project, timestamps, verified, annotations); 11 valid types; factory methods `from_hypothesis()`, `from_protocol()`, `from_result()`, `from_research_question()` | `kosmos/world_model/models.py:72-458` |
| `Relationship` | Stdlib dataclass with 8 fields and 12 valid types including `SPAWNED_BY`, `TESTS`, `REFINED_FROM` for research workflow; `with_provenance()` classmethod | `kosmos/world_model/models.py:461-667` |
| `Neo4jWorldModel` | Adapter implementing `WorldModelStorage` + `EntityManager` by wrapping `KnowledgeGraph`; standard types go through optimized paths, research types use raw node creation | `kosmos/world_model/simple.py` |
| `InMemoryWorldModel` | Testing/fallback implementation using three dicts; `query_related_entities()` is O(R) linear scan; `close()` is a no-op | `kosmos/world_model/in_memory.py` |
| `get_world_model()` | Singleton factory: tries `Neo4jWorldModel`, falls back to `InMemoryWorldModel` with only a log warning; NOT thread-safe | `kosmos/world_model/factory.py:55-155` |
| `ArtifactStateManager` | Separate 4-layer hybrid system: JSON file artifacts, optional graph, optional vector store (stub), citation tracking; implements conflict detection (confirmation/conflict/pruning) | `kosmos/world_model/artifacts.py:146-727` |
| `UpdateType` | Three-value enum for world model updates: `CONFIRMATION`, `CONFLICT`, `PRUNING` | `kosmos/world_model/artifacts.py:37-47` |
| `Finding` | Dataclass with 23 fields including core data, validation results, provenance, and expert review status | `kosmos/world_model/artifacts.py:51-96` |
| `PlanCreatorAgent` | Generates 10-task research plans per cycle with adaptive exploration/exploitation ratios; uses raw Anthropic SDK (bypasses Kosmos provider); falls back to mock planning | `kosmos/orchestration/plan_creator.py` |
| `PlanReviewerAgent` | Validates plans on 5 dimensions (specificity, relevance, novelty, coverage, feasibility) scored 0-10 plus structural requirements; uses raw Anthropic SDK | `kosmos/orchestration/plan_reviewer.py` |
| `DelegationManager` | Executes approved plans by routing tasks to specialized agents in parallel batches (default 3); async-only; agents injected via constructor dict | `kosmos/orchestration/delegation.py` |
| `NoveltyDetector` | Prevents redundant research tasks by computing semantic similarity (sentence-transformers or Jaccard fallback) against an in-memory index of past tasks; threshold 0.75 | `kosmos/orchestration/novelty_detector.py` |
| Exploration/exploitation ratio | Hardcoded by cycle range in `PlanCreatorAgent`: cycles 1-7 = 70% exploration, 8-14 = 50%, 15-20 = 30%; no config override | `kosmos/orchestration/plan_creator.py:105-121` |
| `LogFormat` | Two-value enum: `JSON = "json"`, `TEXT = "text"`; used to select logging formatter | `kosmos/core/logging.py:28` |
| `JSONFormatter` | Formats log records as single-line JSON with standard fields plus optional correlation_id; no serialization guard (raises TypeError on non-serializable extras) | `kosmos/core/logging.py:34` |
| `TextFormatter` | Human-readable log formatter with ANSI colors; mutates `record.levelname` in place (shared-state mutation that can leak ANSI to other handlers) | `kosmos/core/logging.py:85` |
| `correlation_id` | Module-level `ContextVar` for request tracing across async boundaries; instantiated at import time but not imported by any other Kosmos module [ABSENCE] | `kosmos/core/logging.py:23-25` |
| `ExperimentLogger` | Stateful logger tracking experiment lifecycle events with timing; accumulates events in unbounded in-memory list | `kosmos/core/logging.py:242` |
| `setup_logging()` | Configures root logger; CLEARS ALL existing handlers on every call; creates rotating file handler (10MB, 5 backups); emits "Logging initialized" message | `kosmos/core/logging.py:133` |
| `model_to_dict` | Pydantic v1/v2 compatibility shim used throughout for serialization instead of standard `model_dump()` | `kosmos/utils/compat` |
| `get_config()` | Central configuration accessor; imported lazily in many modules to avoid circular imports; dependency chain: many modules -> config -> env vars/files | `kosmos/config` |
| `_DEFAULT_CLAUDE_SONNET_MODEL` | Config constant (`"claude-sonnet-4-5"`) imported at module scope by hypothesis.py and experiment.py, making config a hard dependency of data models | `kosmos/config:17` |
| `MAX_ACTIONS_PER_ITERATION` | Module constant (50) in research_director.py; if exceeded, `decide_next_action()` forces convergence as an infinite-loop guard | `kosmos/agents/research_director.py:50` |
| `MAX_CONSECUTIVE_ERRORS` | Module constant (3) in research_director.py; circuit breaker that transitions workflow to ERROR state after 3 consecutive failures | `kosmos/agents/research_director.py:45` |
| Issue #51 | Referenced fix: `FileNotFoundError` is terminal (no retry) because missing data files should trigger synthetic data generation in templates | `executor.py:726, code_generator.py` |
| Issue #76 | Revealed that message-based agent coordination silently failed; direct-call `_handle_*_action()` methods replaced `_send_to_*` methods as the working coordination mechanism | `research_director.py:1039-1979` |
| `StageOrchestratorAgent` | Google ADK-based agent in the reference codebase (NOT Kosmos core); feeds stages to an implementation loop with success criteria checking | `kosmos-reference/stage_orchestrator.py` |
## Configuration Surface

<!-- Every knob that changes runtime behavior. -->

### Architecture

[FACT] The entire configuration system is centralized in `kosmos/config.py` (1161 lines). It uses **Pydantic v2 `BaseSettings`** (from `pydantic_settings`) to define typed, validated configuration classes that auto-populate from environment variables and `.env` files. `config.py:1140`

[FACT] The entry point for configuration access is a module-level singleton: `get_config() -> KosmosConfig` at `config.py:1140`. It is a lazy singleton (`_config` global, line 1137) that creates the `KosmosConfig` instance on first access, with an optional `reload=True` parameter. A `reset_config()` function (line 1157) exists for testing. `config.py:1140`

### Configuration Loading Chain

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

[FACT] The `.env` file location is hardcoded in `KosmosConfig.model_config` at line 979: `env_file=str(Path(__file__).parent.parent / ".env")`. This resolves to the repository root. The same pattern appears in `LiteLLMConfig` at line 194. `config.py:979`

[FACT] `load_dotenv()` is called at module import time in `kosmos/cli/main.py:22`, before any config access. This means environment variables from `.env` are available when Pydantic `BaseSettings` reads them. `cli/main.py:22`

### Config Class Hierarchy

[FACT] `KosmosConfig` (line 922) composes 16 sub-configuration classes, all inheriting from `BaseSettings`. `config.py:922`

| Sub-Config Class     | Lines     | Env Alias Prefix         | Purpose                        |
|---------------------|-----------|--------------------------|--------------------------------|
| `ClaudeConfig`      | 29-84     | `ANTHROPIC_*`, `CLAUDE_*`| Anthropic/Claude LLM settings  |
| `OpenAIConfig`      | 91-140    | `OPENAI_*`               | OpenAI provider settings       |
| `LiteLLMConfig`     | 143-197   | `LITELLM_*`              | LiteLLM multi-provider config  |
| `ResearchConfig`    | 200-247   | `MAX_RESEARCH_*`, etc.   | Research workflow parameters   |
| `DatabaseConfig`    | 250-302   | `DATABASE_*`             | SQLAlchemy DB connection       |
| `RedisConfig`       | 305-362   | `REDIS_*`                | Redis cache settings           |
| `LoggingConfig`     | 365-432   | `LOG_*`, `DEBUG_*`, `STAGE_*` | Logging and debug config  |
| `LiteratureConfig`  | 435-489   | `SEMANTIC_SCHOLAR_*`, `PUBMED_*`, `LITERATURE_*` | Academic API config |
| `VectorDBConfig`    | 492-531   | `VECTOR_DB_*`, `CHROMA_*`, `PINECONE_*` | Vector database config |
| `Neo4jConfig`       | 534-570   | `NEO4J_*`                | Knowledge graph connection     |
| `SafetyConfig`      | 573-683   | `ENABLE_SAFETY_*`, `MAX_*`, etc. | Safety guardrails       |
| `PerformanceConfig` | 686-749   | `ENABLE_*`, `MAX_*`, `ASYNC_*` | Concurrency and caching  |
| `LocalModelConfig`  | 752-822   | `LOCAL_MODEL_*`          | Ollama/LM Studio tuning        |
| `MonitoringConfig`  | 825-840   | `ENABLE_USAGE_*`, `METRICS_*` | Metrics export settings  |
| `DevelopmentConfig` | 843-862   | `HOT_RELOAD`, `LOG_API_*`, `TEST_MODE` | Dev/test toggles  |
| `WorldModelConfig`  | 865-893   | `WORLD_MODEL_*`          | Knowledge graph persistence    |

[FACT] `ClaudeConfig` and `AnthropicConfig` are aliases (line 88: `AnthropicConfig = ClaudeConfig`). Both the `claude` and `anthropic` fields in `KosmosConfig` point to the same class but are conditionally instantiated. `config.py:88`

### Config Access Patterns

#### Pattern 1: Pydantic-validated access via `get_config()` (dominant)

[PATTERN] The CLI, health checks, and initialization code use `get_config()` to obtain the typed `KosmosConfig` singleton, then access nested fields like `config.research.max_iterations`. Observed in `cli/commands/run.py:132`, `cli/commands/config.py:209`, and `core/providers/factory.py:83`.

#### Pattern 2: Flat dict for agents (bridge layer)

[FACT] Agents (`BaseAgent` subclasses) receive a `config: Dict[str, Any]` in their constructor (base.py:117), stored as `self.config` (a plain dict, line 129). The CLI's `run.py:147-170` constructs a `flat_config` dict by manually extracting values from the nested `KosmosConfig` object. Agents then access config via `self.config.get("key", default)`. `base.py:117,129; run.py:147-170`

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

[FACT] The provider factory (`core/providers/factory.py:83-175`) bridges between `KosmosConfig` and the flat dict that each provider `__init__` expects. Each provider (`AnthropicProvider`, `OpenAIProvider`, `LiteLLMProvider`) takes a `config: Dict[str, Any]` and extracts fields with `.get()` with fallbacks to `os.environ.get()`. `factory.py:83-175`

### Validation

[FACT] Validation is primarily Pydantic-native, using:
1. **Field constraints**: `ge`, `le`, `Literal` types (e.g., `temperature: float = Field(ge=0.0, le=1.0)`)
2. **`@model_validator`** at three locations:
   - `VectorDBConfig.validate_pinecone_config` (line 521): validates Pinecone-specific fields when Pinecone is selected
   - `KosmosConfig.sync_litellm_env_vars` (line 985): manually syncs LITELLM_* env vars into nested config because Pydantic doesn't auto-propagate to nested models
   - `KosmosConfig.validate_provider_config` (line 1024): ensures API key is present for the selected provider
3. **`BeforeValidator(parse_comma_separated)`**: custom parser for comma-separated list fields (`enabled_domains`, `enabled_experiment_types`, `debug_modules`). `config.py:521,985,1024`

[FACT] No runtime config validation exists beyond Pydantic initialization. If environment variables change after `get_config()` is called, the singleton retains stale values unless `reload=True` is passed. `config.py:1140`

### Conditional Sub-Config Instantiation

[FACT] Three optional provider configs use conditional factory functions (lines 896-919):
- `_optional_openai_config()`: only creates `OpenAIConfig` if `OPENAI_API_KEY` is set
- `_optional_anthropic_config()`: only creates `AnthropicConfig` if `ANTHROPIC_API_KEY` is set
- `_optional_claude_config()`: same as above (backward compat alias)

This means `config.openai` is `None` when OpenAI is not configured, and code must null-check before access. `config.py:896-919`

### Provider Configuration

[FACT] `KosmosConfig.llm_provider` field at `config.py:953` accepts `Literal["anthropic", "openai", "litellm"]`, defaulting to `"anthropic"`. Set via `LLM_PROVIDER` environment variable. `config.py:953`

| Config Class | Env Prefix | Key Fields |
|---|---|---|
| `ClaudeConfig` (`config.py:29`) | `ANTHROPIC_*`, `CLAUDE_*` | api_key, model (default `claude-sonnet-4-5`), max_tokens, temperature, enable_cache, enable_auto_model_selection |
| `OpenAIConfig` (`config.py:91`) | `OPENAI_*` | api_key, model (default `gpt-4-turbo`), max_tokens, temperature, base_url, organization |
| `LiteLLMConfig` (`config.py:143`) | `LITELLM_*` | model (default `gpt-3.5-turbo`), api_key, api_base, max_tokens, temperature, timeout |
| `LocalModelConfig` (`config.py:752`) | `LOCAL_MODEL_*` | max_retries, strict_json, json_retry_with_hint, request_timeout, concurrent_requests, fallback_to_unstructured, circuit_breaker_threshold, circuit_breaker_reset_timeout |

[FACT] Validation at `config.py:1024-1042`: Anthropic and OpenAI require API keys; LiteLLM is lenient (local models like Ollama don't need keys). `config.py:1024-1042`

[FACT] Default models (from `config.py:17-18`):
- `_DEFAULT_CLAUDE_SONNET_MODEL = "claude-sonnet-4-5"`
- `_DEFAULT_CLAUDE_HAIKU_MODEL = "claude-haiku-4-5"` `config.py:17-18`

---

### Complete Environment Variable Inventory

#### REQUIRED -- LLM Provider (exactly one provider must be configured)

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LLM_PROVIDER` | env / `.env` | Provider selector: which LLM backend is used (`anthropic`, `openai`, or `litellm`) | `"anthropic"` |

[FACT] Environment variables are loaded via `python-dotenv` at CLI startup (`kosmos/cli/main.py:22`: `load_dotenv()`). The `.env` file is expected at the repository root. Pydantic `BaseSettings` in `kosmos/config.py` also reads from this file (line 979: `env_file=str(Path(__file__).parent.parent / ".env")`). `cli/main.py:22; config.py:979`

[FACT] An `.env.example` template (458 lines) documents all supported env vars with comments and defaults. The actual `.env` file is gitignored. `.env.example`

#### REQUIRED -- Anthropic (when LLM_PROVIDER=anthropic)

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ANTHROPIC_API_KEY` | env / `.env` | API key for Anthropic; also read directly in `core/llm.py:160`, `core/providers/anthropic.py:88`, `api/health.py:283`, `cli/main.py:255`, `agents/research_director.py:228`; `999...` triggers CLI proxy mode | *none (required)* |
| `CLAUDE_MODEL` | env / `.env` | Model identifier for Anthropic Claude | `"claude-sonnet-4-5"` |
| `CLAUDE_MAX_TOKENS` | env / `.env` | Max response tokens for Claude | `4096` |
| `CLAUDE_TEMPERATURE` | env / `.env` | Sampling temperature for Claude | `0.7` |
| `CLAUDE_ENABLE_CACHE` | env / `.env` | Prompt caching toggle for Claude | `true` |
| `CLAUDE_BASE_URL` | env / `.env` | Custom endpoint URL; also read in `core/providers/anthropic.py:107` | *none* |
| `CLAUDE_TIMEOUT` | env / `.env` | Request timeout in seconds | `120` |

[FACT] The AnthropicProvider has CLI mode detection (`anthropic.py:110`): `self.is_cli_mode = self.api_key.replace('9', '') == ''` -- an API key consisting entirely of 9s triggers "CLI mode" that routes through Claude Code proxy, disabling cost tracking. `anthropic.py:110`

#### REQUIRED -- OpenAI (when LLM_PROVIDER=openai)

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `OPENAI_API_KEY` | env / `.env` | OpenAI API key (or dummy for local); also read in `core/providers/openai.py:106` | *none (required)* |
| `OPENAI_MODEL` | env / `.env` | Model name for OpenAI | `"gpt-4-turbo"` |
| `OPENAI_MAX_TOKENS` | env / `.env` | Max response tokens for OpenAI | `4096` |
| `OPENAI_TEMPERATURE` | env / `.env` | Sampling temperature for OpenAI | `0.7` |
| `OPENAI_BASE_URL` | env / `.env` | Custom endpoint (Ollama, OpenRouter, etc.); also read in `core/providers/openai.py:116` | *none* |
| `OPENAI_ORGANIZATION` | env / `.env` | OpenAI org ID; also read in `core/providers/openai.py:117` | *none* |
| `OPENAI_TIMEOUT` | env / `.env` | Request timeout in seconds | `120` |

[FACT] OpenAI provider detects provider type from `base_url` (`openai.py:121-131`): localhost/ollama -> `provider_type = 'local'`, openrouter -> `provider_type = 'openrouter'`, together -> `provider_type = 'together'`, default -> `provider_type = 'compatible'`. `openai.py:121-131`

[FACT] Cost tracking only applies when `provider_type == 'openai'` (`openai.py:255`). Local models get `None` for cost. `openai.py:255`

#### REQUIRED -- LiteLLM (when LLM_PROVIDER=litellm)

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LITELLM_MODEL` | env / `.env` | Model in LiteLLM format (e.g., `ollama/llama3.1:8b`); also read in `core/providers/factory.py:164` | `"gpt-3.5-turbo"` |
| `LITELLM_API_KEY` | env / `.env` | API key (optional for local models); also read in `core/providers/factory.py:165` | *none* |
| `LITELLM_API_BASE` | env / `.env` | Custom base URL; also read in `core/providers/factory.py:166` | *none* |
| `LITELLM_MAX_TOKENS` | env / `.env` | Max response tokens; also read in `core/providers/factory.py:167` | `4096` |
| `LITELLM_TEMPERATURE` | env / `.env` | Sampling temperature; also read in `core/providers/factory.py:168` | `0.7` |
| `LITELLM_TIMEOUT` | env / `.env` | Request timeout in seconds; also read in `core/providers/factory.py:169` | `120` |

[FACT] LiteLLM provider has lazy import of `litellm` at `__init__` time (`litellm_provider.py:89-96`) -- package is optional. `litellm_provider.py:89-96`

[FACT] LiteLLM provider detects provider-type from model name prefix (`litellm_provider.py:127-142`): `ollama/`, `deepseek/`, `azure/`, `claude`, `gpt`. `litellm_provider.py:127-142`

[FACT] LiteLLM provider has Qwen model special handling (`litellm_provider.py:158-170`): automatically injects `"Do not use thinking mode"` system directive and enforces minimum 8192 max_tokens (`litellm_provider.py:205-220`). `litellm_provider.py:158-170,205-220`

[FACT] LiteLLM provider API key routing (`litellm_provider.py:108-114`): sets `litellm.anthropic_key`, `litellm.deepseek_key`, or `litellm.openai_key` based on model name. `litellm_provider.py:108-114`

#### OPTIONAL -- Research Configuration

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `MAX_RESEARCH_ITERATIONS` | env / `.env` | Max autonomous iterations in research workflow | `10` |
| `ENABLED_DOMAINS` | env / `.env` | Comma-separated scientific domains | `"biology,physics,chemistry,neuroscience"` |
| `ENABLED_EXPERIMENT_TYPES` | env / `.env` | Experiment type whitelist | `"computational,data_analysis,literature_synthesis"` |
| `MIN_NOVELTY_SCORE` | env / `.env` | Hypothesis novelty threshold | `0.6` |
| `ENABLE_AUTONOMOUS_ITERATION` | env / `.env` | Autonomous loop toggle | `true` |
| `RESEARCH_BUDGET_USD` | env / `.env` | API cost budget | `10.0` |
| `MAX_RUNTIME_HOURS` | env / `.env` | Maximum wall-clock hours | `12.0` |

#### OPTIONAL -- Database

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `DATABASE_URL` | env / `.env` | SQLAlchemy connection string | `"sqlite:///kosmos.db"` |
| `DATABASE_ECHO` | env / `.env` | SQL logging toggle | `false` |

#### OPTIONAL -- Redis Cache

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `REDIS_ENABLED` | env / `.env` | Redis toggle; also read directly in `api/health.py:226` | `false` |
| `REDIS_URL` | env / `.env` | Redis connection URL; also read directly in `api/health.py:231` | `"redis://localhost:6379/0"` |
| `REDIS_MAX_CONNECTIONS` | env / `.env` | Connection pool size | `50` |
| `REDIS_SOCKET_TIMEOUT` | env / `.env` | Socket timeout (seconds) | `5` |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | env / `.env` | Connect timeout | `5` |
| `REDIS_RETRY_ON_TIMEOUT` | env / `.env` | Retry behavior | `true` |
| `REDIS_DECODE_RESPONSES` | env / `.env` | UTF-8 decode toggle | `true` |
| `REDIS_DEFAULT_TTL_SECONDS` | env / `.env` | Cache TTL | `3600` |

#### OPTIONAL -- Logging

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LOG_LEVEL` | env / `.env` | Log severity level | `"INFO"` |
| `LOG_FORMAT` | env / `.env` | Output format: `json` or `text` | `"json"` |
| `LOG_FILE` | env / `.env` | Log file path | `"logs/kosmos.log"` |
| `DEBUG_MODE` | env / `.env` | Verbose debug output | `false` |
| `DEBUG_LEVEL` | env / `.env` | Granularity: 0=off, 1=critical path, 2=full trace, 3=data dumps | `0` |
| `DEBUG_MODULES` | env / `.env` | Comma-separated module filter | *none* |
| `LOG_LLM_CALLS` | env / `.env` | Log LLM request/response | `false` |
| `LOG_AGENT_MESSAGES` | env / `.env` | Log inter-agent messages | `false` |
| `LOG_WORKFLOW_TRANSITIONS` | env / `.env` | Log state machine events | `false` |
| `STAGE_TRACKING_ENABLED` | env / `.env` | JSON event stage tracking | `false` |
| `STAGE_TRACKING_FILE` | env / `.env` | Stage tracking output path | `"logs/stages.jsonl"` |

#### OPTIONAL -- Literature APIs

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `SEMANTIC_SCHOLAR_API_KEY` | env / `.env` | Semantic Scholar key (increases rate limits) | *none* |
| `PUBMED_API_KEY` | env / `.env` | PubMed NCBI key | *none* |
| `PUBMED_EMAIL` | env / `.env` | PubMed E-utilities email | *none* |
| `LITERATURE_CACHE_TTL_HOURS` | env / `.env` | Literature cache lifetime | `48` |
| `MAX_RESULTS_PER_QUERY` | env / `.env` | Search result limit | `100` |
| `PDF_DOWNLOAD_TIMEOUT` | env / `.env` | PDF fetch timeout | `30` |
| `LITERATURE_SEARCH_TIMEOUT` | env / `.env` | Combined search timeout | `90` |
| `LITERATURE_API_TIMEOUT` | env / `.env` | Per-API call timeout | `30` |

#### OPTIONAL -- Vector Database

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `VECTOR_DB_TYPE` | env / `.env` | Backend: `chromadb`, `pinecone`, `weaviate` | `"chromadb"` |
| `CHROMA_PERSIST_DIRECTORY` | env / `.env` | ChromaDB storage path | `".chroma_db"` |
| `PINECONE_API_KEY` | env / `.env` | Pinecone API key (required if type=pinecone) | *none* |
| `PINECONE_ENVIRONMENT` | env / `.env` | Pinecone environment (required if type=pinecone) | *none* |
| `PINECONE_INDEX_NAME` | env / `.env` | Pinecone index name | `"kosmos"` |

#### OPTIONAL -- Neo4j Knowledge Graph

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `NEO4J_URI` | env / `.env` | Connection URI; also read directly in `api/health.py:336` | `"bolt://localhost:7687"` |
| `NEO4J_USER` | env / `.env` | Username; also read directly in `api/health.py:337` | `"neo4j"` |
| `NEO4J_PASSWORD` | env / `.env` | Password; also read directly in `api/health.py:338` | `"kosmos-password"` |
| `NEO4J_DATABASE` | env / `.env` | Database name | `"neo4j"` |
| `NEO4J_MAX_CONNECTION_LIFETIME` | env / `.env` | Connection lifetime | `3600` |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | env / `.env` | Pool size | `50` |

#### OPTIONAL -- Safety

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_SAFETY_CHECKS` | env / `.env` | Safety check toggle | `true` |
| `MAX_EXPERIMENT_EXECUTION_TIME` | env / `.env` | Execution timeout (seconds) | `300` |
| `MAX_MEMORY_MB` | env / `.env` | Memory ceiling | `2048` |
| `MAX_CPU_CORES` | env / `.env` | CPU limit (None=unlimited) | *none* |
| `ENABLE_SANDBOXING` | env / `.env` | Docker sandbox toggle | `true` |
| `REQUIRE_HUMAN_APPROVAL` | env / `.env` | Human-in-the-loop gate | `false` |
| `ETHICAL_GUIDELINES_PATH` | env / `.env` | Path to ethics JSON | *none* |
| `ENABLE_RESULT_VERIFICATION` | env / `.env` | Result verification toggle | `true` |
| `OUTLIER_THRESHOLD` | env / `.env` | Z-score outlier threshold | `3.0` |
| `DEFAULT_RANDOM_SEED` | env / `.env` | Reproducibility seed | `42` |
| `CAPTURE_ENVIRONMENT` | env / `.env` | Environment snapshot toggle | `true` |
| `APPROVAL_MODE` | env / `.env` | Approval workflow mode | `"blocking"` |
| `AUTO_APPROVE_LOW_RISK` | env / `.env` | Auto-approve toggle | `true` |
| `NOTIFICATION_CHANNEL` | env / `.env` | Notification output | `"both"` |
| `NOTIFICATION_MIN_LEVEL` | env / `.env` | Minimum notification severity | `"info"` |
| `USE_RICH_FORMATTING` | env / `.env` | Rich console toggle | `true` |
| `INCIDENT_LOG_PATH` | env / `.env` | Incident log path | `"safety_incidents.jsonl"` |
| `AUDIT_LOG_PATH` | env / `.env` | Audit log path | `"human_review_audit.jsonl"` |

#### OPTIONAL -- Performance / Concurrency

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_RESULT_CACHING` | env / `.env` | Result cache toggle | `true` |
| `CACHE_TTL` | env / `.env` | Cache lifetime (seconds) | `3600` |
| `PARALLEL_EXPERIMENTS` | env / `.env` | Parallel experiment count (0=sequential) | `0` |
| `ENABLE_CONCURRENT_OPERATIONS` | env / `.env` | Concurrent research toggle | `false` |
| `MAX_PARALLEL_HYPOTHESES` | env / `.env` | Concurrent hypothesis evaluations | `3` |
| `MAX_CONCURRENT_EXPERIMENTS` | env / `.env` | Concurrent experiment limit | `10` |
| `MAX_CONCURRENT_LLM_CALLS` | env / `.env` | Concurrent API call limit | `5` |
| `LLM_RATE_LIMIT_PER_MINUTE` | env / `.env` | API rate limit | `50` |
| `ASYNC_BATCH_TIMEOUT` | env / `.env` | Batch operation timeout | `300` |

#### OPTIONAL -- Local Model Tuning

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `LOCAL_MODEL_MAX_RETRIES` | env / `.env` | Retry count for local models | `1` |
| `LOCAL_MODEL_STRICT_JSON` | env / `.env` | Strict JSON compliance | `false` |
| `LOCAL_MODEL_JSON_RETRY_HINT` | env / `.env` | Retry with formatting hint | `true` |
| `LOCAL_MODEL_REQUEST_TIMEOUT` | env / `.env` | Local model timeout | `120` |
| `LOCAL_MODEL_CONCURRENT_REQUESTS` | env / `.env` | Max concurrent local requests | `1` |
| `LOCAL_MODEL_FALLBACK_UNSTRUCTURED` | env / `.env` | Fallback to unstructured extraction | `true` |
| `LOCAL_MODEL_CB_THRESHOLD` | env / `.env` | Circuit breaker failure threshold | `3` |
| `LOCAL_MODEL_CB_RESET_TIMEOUT` | env / `.env` | Circuit breaker reset delay | `60` |

[ABSENCE] These `LocalModelConfig` settings are defined but not wired into the provider implementations. The LiteLLM and OpenAI providers do not read `LocalModelConfig`. This is configuration infrastructure that exists but is not yet consumed. `config.py:752-822`

#### OPTIONAL -- World Model

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `WORLD_MODEL_ENABLED` | env / `.env` | Knowledge graph toggle | `true` |
| `WORLD_MODEL_MODE` | env / `.env` | Storage mode: `simple` or `production` | `"simple"` |
| `WORLD_MODEL_PROJECT` | env / `.env` | Default project namespace | *none* |
| `WORLD_MODEL_AUTO_SAVE_INTERVAL` | env / `.env` | Auto-export interval | `300` |

#### OPTIONAL -- Monitoring

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ENABLE_USAGE_STATS` | env / `.env` | Usage stats toggle | `true` |
| `METRICS_EXPORT_INTERVAL` | env / `.env` | Export interval (seconds) | `60` |

#### OPTIONAL -- Development

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `HOT_RELOAD` | env / `.env` | Hot reload toggle | `false` |
| `LOG_API_REQUESTS` | env / `.env` | API request logging | `false` |
| `TEST_MODE` | env / `.env` | Test mock mode | `false` |

#### NOT MODELED IN PYDANTIC (read via raw os.getenv)

These env vars are consumed directly without Pydantic validation:

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `ALERT_EMAIL_ENABLED` | env (raw `os.getenv`) | Enable email alerts | `"false"` |
| `ALERT_EMAIL_FROM` | env (raw `os.getenv`) | Sender email | `"alerts@kosmos.ai"` |
| `ALERT_EMAIL_TO` | env (raw `os.getenv`) | Recipient email | `"admin@example.com"` |
| `SMTP_HOST` | env (raw `os.getenv`) | SMTP server | `"localhost"` |
| `SMTP_PORT` | env (raw `os.getenv`) | SMTP port | `"587"` |
| `SMTP_USER` | env (raw `os.getenv`) | SMTP username | *none* |
| `SMTP_PASSWORD` | env (raw `os.getenv`) | SMTP password | *none* |
| `ALERT_SLACK_ENABLED` | env (raw `os.getenv`) | Enable Slack alerts | `"false"` |
| `SLACK_WEBHOOK_URL` | env (raw `os.getenv`) | Slack webhook | *none* |
| `ALERT_PAGERDUTY_ENABLED` | env (raw `os.getenv`) | Enable PagerDuty | `"false"` |
| `PAGERDUTY_INTEGRATION_KEY` | env (raw `os.getenv`) | PagerDuty key | *none* |
| `KOSMOS_SKILLS_DIR` | env (raw `os.getenv`) | Custom skills directory | *none* |
| `EDITOR` | env (raw `os.getenv`) | Config file editor | `"nano"` |
| `ENABLE_PROFILING` | `.env.example` only, `k8s/configmap.yaml` | Profiling toggle | `"false"` |
| `PROFILING_MODE` | `.env.example` only, `k8s/configmap.yaml` | Profiling depth | `"light"` |
| `STORE_PROFILE_RESULTS` | `.env.example` only | Store profiling data | `"true"` |
| `PROFILE_STORAGE_DAYS` | `.env.example` only | Profile retention | `"30"` |
| `ENABLE_BOTTLENECK_DETECTION` | `.env.example` only | Bottleneck detection toggle | `"true"` |
| `BOTTLENECK_THRESHOLD_PERCENT` | `.env.example` only | Bottleneck threshold | `"10"` |

[FACT] **Alerting env vars are not modeled**: `ALERT_EMAIL_ENABLED`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_SLACK_ENABLED`, `SLACK_WEBHOOK_URL`, `ALERT_PAGERDUTY_ENABLED`, `PAGERDUTY_INTEGRATION_KEY` -- all in `monitoring/alerts.py` -- have no corresponding Pydantic config class. They are read raw from `os.getenv()`. `monitoring/alerts.py`

[FACT] **Profiling env vars are not modeled**: `ENABLE_PROFILING`, `PROFILING_MODE`, `STORE_PROFILE_RESULTS`, `PROFILE_STORAGE_DAYS`, `ENABLE_BOTTLENECK_DETECTION`, `BOTTLENECK_THRESHOLD_PERCENT` appear in `.env.example` and `k8s/configmap.yaml` but have no Pydantic model in `config.py`. The profiling system uses its own `ProfilingMode` enum in `core/profiling.py` but reads settings elsewhere. `config.py (absent); .env.example; k8s/configmap.yaml`

[FACT] **KOSMOS_SKILLS_DIR**: read directly in `agents/skill_loader.py:148` with no config model. `skill_loader.py:148`

[FACT] **EDITOR**: read directly in `cli/commands/config.py:313` with fallback to `nano`. `cli/commands/config.py:313`

#### DOCUMENTED BUT OPTIONAL (domain-specific API keys)

These appear in `.env.example` only, for optional integrations:

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `KEGG_API_KEY` | `.env.example` | KEGG biology database | *none* |
| `UNIPROT_API_KEY` | `.env.example` | UniProt protein database | *none* |
| `MATERIALS_PROJECT_API_KEY` | `.env.example` | Materials Project API | *none* |
| `NASA_API_KEY` | `.env.example` | NASA astronomy API | *none* |
| `DEEPSEEK_API_KEY` | `.env.example` | DeepSeek (used via LiteLLM, not read by Kosmos directly) | *none* |

#### LEGACY / BACKWARD COMPAT

| Config | Source | Affects | Default |
|--------|--------|---------|---------|
| `MAX_PARALLEL_HYPOTHESIS_EVALUATIONS` | `.env.example:406` only | Superseded by `MAX_PARALLEL_HYPOTHESES` | `3` |
| `ENABLE_CONCURRENT_RESULT_ANALYSIS` | `.env.example:407` only | Legacy concurrent toggle | `true` |

---

### Minimum Viable Environment

[FACT] To run Kosmos with the absolute minimum configuration, you need:

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

### Dual-Read Pattern

[PATTERN] Several env vars are read in two places -- once by Pydantic during config initialization and again directly by subsystems. This affects 5 variables: `ANTHROPIC_API_KEY`, `REDIS_ENABLED`, `REDIS_URL`, `NEO4J_URI/USER/PASSWORD`. The health check system (`api/health.py`) bypasses Pydantic entirely, reading these directly from `os.getenv()`. This creates a risk of inconsistency if values are modified programmatically in the config singleton but not in the actual environment.

---

### Nested Env Var Propagation Issue

[FACT] **Nested env var propagation issue**: The `sync_litellm_env_vars` model validator (line 985) exists specifically because Pydantic `BaseSettings` does not auto-propagate env vars from the parent `.env` file to nested `BaseSettings` submodels. This is a known Pydantic limitation, and only LiteLLM has this workaround. Other sub-configs may be similarly affected if they define their own `env_file`. `config.py:985`

---

### Kubernetes Surface

[FACT] A K8s ConfigMap (`k8s/configmap.yaml`) mirrors the `.env.example` structure for non-secret values. Secrets (`anthropic-api-key`, `postgres-password`, `neo4j-password`, optional `smtp-password`, `slack-webhook-url`, `pagerduty-key`) are in `k8s/secrets.yaml.template`. The deployment (`k8s/kosmos-deployment.yaml`) maps a subset of these into container env vars. `k8s/configmap.yaml; k8s/secrets.yaml.template; k8s/kosmos-deployment.yaml`

---

### Provider Abstraction Configuration

#### Factory and Registration

[FACT] A module-level `_PROVIDER_REGISTRY` dict maps string names to provider classes (`factory.py:16`). `factory.py:16`

[FACT] `_register_builtin_providers()` runs at import time (`factory.py:217`) and registers:
- `"anthropic"` and `"claude"` -> `AnthropicProvider`
- `"openai"` -> `OpenAIProvider`
- `"litellm"`, `"ollama"`, `"deepseek"`, `"lmstudio"` -> `LiteLLMProvider`

Each registration is wrapped in try/except ImportError -- providers are only available if their SDK package is installed. `factory.py:217`

[FACT] `get_provider_from_config()` at `factory.py:83-175` reads `kosmos_config.llm_provider` (defaults to `"anthropic"`) and extracts provider-specific config from the corresponding config section. Backward compat: if `anthropic` provider is selected, checks both `kosmos_config.claude` (old name) and `kosmos_config.anthropic` (new name) at `factory.py:108-132`. `factory.py:83-175`

#### Client Facade (llm.py)

[FACT] `get_client()` at `llm.py:613-679` is thread-safe (double-checked locking with `threading.Lock`) and returns a singleton. Its behavior:
1. If `use_provider_system=True` (default): calls `get_provider_from_config(config)` to get an `LLMProvider` instance
2. If that fails: falls back to creating an `AnthropicProvider` with env-var defaults (`llm.py:663-673`)
3. If `use_provider_system=False`: creates a legacy `ClaudeClient` instance. `llm.py:613-679`

[FACT] `get_provider()` at `llm.py:682-706` is the recommended accessor for new code. It calls `get_client(use_provider_system=True)` and asserts the result is an `LLMProvider` instance. `llm.py:682-706`

[FACT] `get_client()` is a singleton -- once initialized, the same provider instance serves all callers for the process lifetime. Call `get_client(reset=True)` to force re-initialization. `llm.py:613-679`

#### How Provider Switching Works

Set `LLM_PROVIDER=openai` (or `litellm`) in environment/.env. On next `get_client()` call, the factory instantiates the corresponding provider. All agents that use `get_client()` transparently get the new provider.

#### Inconsistencies in Provider Access

[FACT] Two components bypass the provider system:
1. **`core/domain_router.py:157`** -- creates `ClaudeClient()` directly, not `get_client()`. This will always use Anthropic regardless of `LLM_PROVIDER` setting. `domain_router.py:157`
2. **`execution/code_generator.py:764`** -- creates `ClaudeClient()` first, then falls back to LiteLLM. Also ignores the provider system. `code_generator.py:764`

[FACT] `research_director.py:222-238` initializes a separate `AsyncClaudeClient` for concurrent operations, directly using `os.getenv("ANTHROPIC_API_KEY")`. This is Anthropic-hardcoded and does not respect `LLM_PROVIDER` configuration. The async client has its own rate limiter and circuit breaker, independent of the main provider. `research_director.py:222-238`

[FACT] `kosmos/execution/code_generator.py:762-778` has its own fallback chain that bypasses `get_client()`:
1. Try `ClaudeClient()` directly (not via provider system)
2. On failure, try `LiteLLMProvider(config.get_active_provider_config())`
3. On failure, disable LLM generation entirely. This is the **only place** with a multi-provider fallback chain in the codebase. `code_generator.py:762-778`

---

### Token Counting and Cost Tracking Configuration

[FACT] Anthropic: token counts extracted from `response.usage.input_tokens` / `output_tokens` (API provides exact counts). `anthropic.py`

[FACT] OpenAI: extracted from `response.usage.prompt_tokens` / `completion_tokens`. Falls back to `len(text) // 4` estimate for local models without usage data (`openai.py:236-239`). `openai.py:236-239`

[FACT] LiteLLM: extracted from `response.usage` via getattr with 0 defaults (`litellm_provider.py:178-181`). `litellm_provider.py:178-181`

[FACT] Centralized cost tracking in `kosmos/core/pricing.py`. Single dict `MODEL_PRICING` maps model names to `(input_cost_per_M, output_cost_per_M)` tuples. Covers Anthropic Claude 3/3.5/4.5 families, OpenAI GPT-3.5/4/4o, DeepSeek, and Ollama (free). `pricing.py`

[FACT] `get_model_cost()` at `pricing.py:54-86` tries three strategies:
1. Exact model name match in `MODEL_PRICING`
2. Base name (strip `:8b` etc.) match
3. Family keyword match (`haiku`/`sonnet`/`opus` -> family pricing)
4. Default to `(0.0, 0.0)` if no match. `pricing.py:54-86`

[FACT] Each provider tracks cumulative usage in `LLMProvider._update_usage_stats()` at `base.py:391-402` (request_count, total_input/output_tokens, total_cost_usd). `base.py:391-402`

[FACT] Cost is skipped (set to `None` or `0.0`) in:
- AnthropicProvider CLI mode (`anthropic.py:300,609`)
- OpenAI non-official providers (`openai.py:255`). `anthropic.py:300,609; openai.py:255`

**Inconsistency**: OpenAI provider has its own hardcoded pricing table (`openai.py:575-613`) duplicating data from `pricing.py`. The Anthropic provider uses the centralized `get_model_cost()`. The LiteLLM provider also uses centralized pricing. `openai.py:575-613; pricing.py`

---

### Rate Limiting and Retry Configuration

#### Sync providers (Anthropic, OpenAI, LiteLLM)

[ABSENCE] None of the three sync provider implementations have built-in retry logic. They catch all exceptions and raise `ProviderAPIError`. Callers are expected to handle retries.

[FACT] The only sync retry is in `ClaudeClient.generate_structured()` (`llm.py:460-486`): a manual for-loop with `max_retries=2`, bypassing cache on retries. `llm.py:460-486`

#### Async path (async_llm.py)

[FACT] `AsyncClaudeClient` at `async_llm.py:269` has three resilience mechanisms:
1. **Rate limiter** (`async_llm.py:206-266`): Token-bucket algorithm with configurable `max_requests_per_minute` (default 50) and `max_concurrent` (default 5) via asyncio.Semaphore.
2. **Circuit breaker** (`async_llm.py:51-138`): Three states (CLOSED/OPEN/HALF_OPEN). Opens after 3 consecutive failures (`failure_threshold=3`), resets after 60 seconds. When open, requests are immediately rejected with `ProviderAPIError`.
3. **Retry with tenacity** (`async_llm.py:443-460`): If `tenacity` package is installed, applies exponential backoff (multiplier=1, min=2s, max=30s) with up to 3 attempts. Uses custom predicate (`should_retry`) that calls `is_recoverable_error()` to skip retrying non-recoverable errors (auth failures, JSON parse errors). `async_llm.py:51-138,206-266,443-460`

[FACT] The async client is **Anthropic-only** -- it directly wraps `AsyncAnthropic` and is not pluggable to other providers. `async_llm.py:269`

[FACT] Timeout: 120 seconds default, enforced via `asyncio.wait_for()` at `async_llm.py:474-477`. `async_llm.py:474-477`

#### LocalModelConfig resilience settings

[FACT] `config.py:752-822` defines tunable resilience for local models:
- `max_retries`: default 1 (lower than cloud)
- `circuit_breaker_threshold`: default 3
- `circuit_breaker_reset_timeout`: default 60s
- `concurrent_requests`: default 1 (VRAM-limited)
- `fallback_to_unstructured`: default True (on structured output failure, try free-text). `config.py:752-822`

---

### Event Bus Integration

[FACT] Only the **AnthropicProvider** emits LLM events, and only during streaming (`anthropic.py:698-770, 806-877`). Events are:
- `LLM_CALL_STARTED` -- at stream begin
- `LLM_TOKEN` -- for each text chunk
- `LLM_CALL_COMPLETED` -- at stream end with duration and token count
- `LLM_CALL_FAILED` -- on error. `anthropic.py:698-770,806-877`

[ABSENCE] Non-streaming `generate()` calls do not emit events. OpenAI and LiteLLM providers never emit events.

---

### Security Observations

1. [FACT] The `.env` file in the repo contains a real `DEEPSEEK_API_KEY` (`sk-925e...`) at line 16. This file is checked into git. `.env:16`
2. [FACT] `NEO4J_PASSWORD` has a hardcoded default `"kosmos-password"` in `config.py:549`, which means Neo4j will connect with a known password if no env var overrides it. `config.py:549`
3. [FACT] The K8s secrets template (`k8s/secrets.yaml.template`) correctly separates secrets from the ConfigMap, requiring base64-encoded values at deployment time. `k8s/secrets.yaml.template`
4. [FACT] `safety/reproducibility.py:208` filters environment captures to a safe whitelist: `PATH`, `PYTHONPATH`, `LANG`, `LC_ALL` -- no secrets leak into reproducibility snapshots. `safety/reproducibility.py:208`

---

### Deviations and Gaps Summary

1. [FACT] **Alerting env vars are not modeled** in Pydantic config. `monitoring/alerts.py`
2. [FACT] **Profiling env vars are not modeled** in Pydantic config. `.env.example; k8s/configmap.yaml`
3. [FACT] **KOSMOS_SKILLS_DIR** read directly with no config model. `agents/skill_loader.py:148`
4. [FACT] **EDITOR** read directly with fallback to `nano`. `cli/commands/config.py:313`
5. [FACT] **Nested env var propagation issue**: Only LiteLLM has the workaround; other sub-configs may be similarly affected. `config.py:985`
6. [FACT] **Two client systems coexist**: Legacy `ClaudeClient` (returns `str`) and `LLMProvider` (returns `LLMResponse`). Two components still use `ClaudeClient` directly. `domain_router.py:157; code_generator.py:764`
7. [FACT] **Async client is Anthropic-locked**: `AsyncClaudeClient` in `async_llm.py` wraps `AsyncAnthropic` directly, not pluggable to the provider abstraction. `async_llm.py:269`
8. [FACT] **Feature parity gap**: Caching, auto model selection, and event bus integration are Anthropic-only features, not part of the base provider interface. `anthropic.py`
9. [FACT] **Duplicate pricing**: OpenAI provider has hardcoded pricing alongside the centralized `pricing.py`. `openai.py:575-613`
10. [FACT] **Unused local model config**: `LocalModelConfig` settings defined but not wired into providers. `config.py:752-822`
11. [FACT] **No provider-level retry in sync path**: Sync providers have no built-in retry; only the async path has tenacity/circuit breaker. Callers must handle retries themselves. `anthropic.py; openai.py; litellm_provider.py`
12. [FACT] **Inconsistent `generate_structured()` JSON parsing**: Anthropic and OpenAI providers use `parse_json_response()` from `utils/json_parser.py`; LiteLLM does its own inline `json.loads()` with manual markdown stripping (`litellm_provider.py:448-468`). `litellm_provider.py:448-468`

---

### Total Count

- **Total unique env vars**: ~105 distinct environment variables
- **Modeled in Pydantic**: ~85 (validated with types, ranges, defaults)
- **Read directly via os.getenv**: ~17 (no type validation, string-only)
- **Documentation-only**: ~8 (appear in .env.example but not consumed in code)
## Conventions

<!-- Implicit rules as directives. Each cites evidence count. -->

### 1. Class Initialization

1. Always accept `agent_id`, `agent_type`, `config` as the base parameters for agent classes. Always call `super().__init__()` passing these parameters. Always extract config values via `self.config.get(key, default)` rather than requiring typed constructor params. Never pass config values as direct constructor arguments -- they go inside the `config` dict. [PATTERN: Observed in all 6 agent subclasses (HypothesisGeneratorAgent, ExperimentDesignerAgent, DataAnalystAgent, LiteratureAnalyzerAgent, ResearchDirectorAgent, StageOrchestrator) and BaseAgent itself]

   Canonical form (from `kosmos/agents/hypothesis_generator.py:62-88`):
   ```python
   def __init__(
       self,
       agent_id: Optional[str] = None,
       agent_type: Optional[str] = None,
       config: Optional[Dict[str, Any]] = None
   ):
       super().__init__(agent_id, agent_type or "HypothesisGeneratorAgent", config)
       self.num_hypotheses = self.config.get("num_hypotheses", 3)
       self.use_literature_context = self.config.get("use_literature_context", True)
   ```

   [FACT] `ResearchDirectorAgent` deviates by adding a mandatory positional-style parameter `research_question: str` before the standard triple. This is intentional: the research question is the agent's core identity, not a tunable configuration knob. `kosmos/agents/research_director.py:68-74`

   The 36 deviations flagged by X-Ray are predominantly:
   - **Parameterless `__init__(self)`**: Found in ~30 utility/singleton classes (EventBus, CacheManager, AgentRegistry, CodeGenerator subclasses, template classes). [FACT: grep found 30+ matches of `def __init__(self):`]. These are infrastructure classes, not domain agents -- the parameterless init is intentional because they have no configurable state or use module-level singletons.
   - **Pydantic model `__init__`**: BaseModel subclasses (Hypothesis, ExperimentResult, etc.) use Pydantic's generated `__init__` with typed Fields, not the `config dict` pattern. This is correct Pydantic usage, not a deviation.
   - **Plain dataclass `__init__`**: ~20 uses of `@dataclass` (PaperAnalysis, VerificationIssue, HypothesisLineage, etc.) in newer modules like `validation/`, `workflow/ensemble.py`, `world_model/models.py`. [FACT: grep found 20+ `@dataclass` occurrences]. These appear intentional for simpler data containers that don't need Pydantic validation.

   **Assessment**: The deviations are intentional, not oversights. The `config dict` pattern applies to configurable service classes; simpler containers correctly use Pydantic or dataclass.

### 2. Logging

2. Always declare `logger = logging.getLogger(__name__)` at module scope after imports. Never create loggers inside methods or classes. Never use `print()` for diagnostic output (use `logger.info/debug/warning/error` instead). [PATTERN: Found in 109 of 109 sampled source files via `logger = logging.getLogger(__name__)`]

   [FACT] One deviation in `kosmos/models/experiment.py:18` which uses `_experiment_logger = logging.getLogger(__name__)` with a prefixed name. This is intentional to avoid shadowing the `logger` name used by Pydantic validators in that module. `experiment.py:18`

### 3. Import Organization

3. Always use absolute imports from `kosmos.*` -- no relative imports (`from .module`). Always use `from kosmos.X import Y` style, not bare `import kosmos.X`. Type imports always come from `typing` as the first import group. [PATTERN: Consistent across all 15+ modules sampled]

   Import ordering must be:
   1. Module docstring
   2. Standard library imports (grouped)
   3. Third-party imports (pydantic, anthropic, numpy, etc.)
   4. Internal imports (`from kosmos.X import Y`)

### 4. Enum Style

4. Always define enums as `class X(str, Enum)` with lowercase string values so values are JSON-serializable strings. Never use bare `Enum` or integer-valued enums. [PATTERN: Found in 25+ enum definitions across the codebase]

   Canonical form (from `kosmos/agents/base.py:25-35`):
   ```python
   class AgentStatus(str, Enum):
       CREATED = "created"
       RUNNING = "running"
   ```

### 5. Singleton Pattern

5. Always provide both `get_X()` and `reset_X()` functions for singleton instances. Use a module-level `Optional` variable with a `get_X()` factory function. The `reset_X()` is critical for test isolation -- the conftest fixture `reset_singletons` calls all available reset functions. [PATTERN: Found in 15+ modules: config, llm, event_bus, cache_manager, metrics, registry, literature_analyzer, etc.] [FACT: tests/conftest.py:332-386]

   Canonical form:
   ```python
   _instance: Optional[MyClass] = None

   def get_instance(**kwargs) -> MyClass:
       global _instance
       if _instance is None:
           _instance = MyClass(**kwargs)
       return _instance

   def reset_instance():
       global _instance
       _instance = None
   ```

### 6. Docstrings

6. Always use Google-style docstrings with `Args:`, `Returns:`, and `Raises:` sections. Class docstrings should list capabilities. Always include inline `Example:` blocks for public methods. Private methods (`_method`) need only brief docstrings. [PATTERN: Consistent across all 6 agent classes, all model classes, all core modules sampled]

   Canonical form:
   ```python
   class MyAgent(BaseAgent):
       """
       One-line summary.

       Capabilities:
       - Capability 1
       - Capability 2

       Example:
           ```python
           agent = MyAgent(config={...})
           result = agent.do_thing()
           ```
       """
   ```

### 7. BaseAgent Subclassing Contract

7. Every agent MUST inherit from `BaseAgent` (from `kosmos.agents.base`), accept `(agent_id, agent_type, config)` in `__init__` and pass them to `super().__init__()`, override `execute(task)` with their main logic, set `self.status = AgentStatus.WORKING` at the start of `execute()`, set `self.status = AgentStatus.IDLE` in the `finally` block of `execute()`, and return a result dict (or `AgentMessage` for message-based agents). [PATTERN: All 5 agent subclasses examined follow this contract exactly] [FACT: kosmos/agents/base.py:97-528 defines the full contract]

### 8. The `execute()` Method Contract

8. Two `execute()` signatures coexist. Always follow the common internal structure: set `AgentStatus.WORKING` at entry, `AgentStatus.IDLE` in `finally`. Always dispatch on a `task_type` or `action` field from the input. Always catch exceptions, log them, and return an error response rather than raising. Always increment `self.tasks_completed` and `self.errors_encountered` appropriately. [PATTERN: This try/except/finally structure with status management appears in all 5 agent execute() methods]

   **Signature A** (dict-based -- used by DataAnalystAgent, LiteratureAnalyzerAgent):
   ```python
   def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
   ```
   [FACT: data_analyst.py:160, literature_analyzer.py:153]

   **Signature B** (message-based -- used by HypothesisGeneratorAgent, ExperimentDesignerAgent):
   ```python
   def execute(self, message: AgentMessage) -> AgentMessage:
   ```
   [FACT: hypothesis_generator.py:91, experiment_designer.py:109]

   **Note**: The base class declares `execute(self, task: Dict[str, Any]) -> Dict[str, Any]`. Signature B is technically a Liskov substitution violation, though it works because callers know which type of agent they are invoking. [FACT: base.py:485-497]

   Common internal structure for `execute()`:
   ```python
   def execute(self, task):
       self.status = AgentStatus.WORKING
       try:
           task_type = task.get("task_type") or task.get("action")
           if task_type == "X":
               ...
           elif task_type == "Y":
               ...
           else:
               raise ValueError(f"Unknown task type: {task_type}")
           return result
       except Exception as e:
           logger.error(f"Error: {e}")
           self.errors_encountered += 1
           return {"success": False, "error": str(e)}  # or AgentMessage with ERROR type
       finally:
           self.status = AgentStatus.IDLE
           self.tasks_completed += 1
   ```

### 9. Lifecycle Hooks

9. Override `_on_start()` only if the agent needs initialization beyond what `__init__` provides (e.g., opening connections, starting timers). Override `_on_stop()` for cleanup. Do NOT override `_on_pause()` / `_on_resume()` -- they are never called. [FACT: base.py:503-509 defines four hooks: `_on_start`, `_on_stop`, `_on_pause`, `_on_resume`]

   - `_on_start()` / `_on_stop()`: Called by `start()` / `stop()` respectively. Only `LiteratureAnalyzerAgent` overrides both to track runtime. [FACT: literature_analyzer.py:138-151]
   - `_on_pause()` / `_on_resume()`: Defined but never called by the base class -- `pause()` and `resume()` do NOT invoke these hooks. [FACT: base.py:189-206 -- no calls to `_on_pause()`/`_on_resume()`]. These are dead code.

### 10. Agent Component Initialization

10. Always acquire service dependencies in `__init__` using factory functions (`get_client()`, `get_knowledge_graph()`, etc.), not during `_on_start()`. Wrap optional dependencies in try/except to degrade gracefully. [PATTERN: All 5 agent subclasses follow this pattern] [FACT: literature_analyzer.py:109-115 wraps knowledge_graph init in try/except]

    ```python
    def __init__(self, ...):
        super().__init__(...)
        self.llm_client = get_client()            # LLM always acquired here
        self.literature_search = UnifiedLiteratureSearch()  # If needed
    ```

### 11. Agent Naming

11. Name agent classes as `{Descriptive Role}Agent` (e.g., `HypothesisGeneratorAgent`, `DataAnalystAgent`). Pass `agent_type or "ClassName"` to super. Never hardcode an agent_type that differs from the class name. [PATTERN: All 6 agents follow this pattern]

### 12. LLM Client Access

12. Always obtain the LLM client via `from kosmos.core.llm import get_client; self.llm_client = get_client()`. Never directly construct API calls. Always call `self.llm_client.generate()` or `self.llm_client.generate_structured()` for LLM interactions. [PATTERN: All 5 agents and 4 non-agent modules obtain their LLM client identically (observed in 9 files)]

    Observed in:
    1. `agents/research_director.py:128`
    2. `agents/hypothesis_generator.py:86`
    3. `agents/experiment_designer.py:104`
    4. `agents/literature_analyzer.py:107`
    5. `agents/data_analyst.py:153`
    6. `analysis/summarizer.py:108`
    7. `hypothesis/refiner.py:89`
    8. `hypothesis/prioritizer.py:83`
    9. `hypothesis/testability.py:58`

    [PATTERN] Agents call either `self.llm_client.generate()` or `self.llm_client.generate_structured()` -- never directly constructing API calls. This means provider switching via config works transparently for all agents.

### 13. Config Access in Agents

13. Always use `self.config.get("key", default)` for accessing configuration in agent code (the flat dict pattern), not the nested Pydantic `get_config()` singleton. [PATTERN: 53 occurrences of `self.config.get(` across 9 files (agents, core/convergence, core/feedback, core/memory, hypothesis/refiner)]

### 14. Test Structure

14. Always mirror source package structure under `tests/unit/`. Name test files `test_{source_module}.py`. [PATTERN: test file naming is always `test_{module_name}.py`, mirroring the source structure] [FACT: pytest.ini defines the full test configuration]

    Directory structure:
    ```
    tests/
      conftest.py          # Shared fixtures (session + function scope)
      unit/                # Fast tests, no external deps
        agents/            # One test file per agent
        core/              # One test file per core module
        ...                # Mirrors kosmos/ package structure
      integration/         # Tests requiring external services
        conftest.py        # Integration-specific fixtures
      e2e/                 # Full workflow tests
      fixtures/            # JSON/XML test data files
    ```

### 15. Test Class Organization

15. Always group related tests into a class with a descriptive `Test{Concern}` name. Always include a class docstring stating what is being tested. Always include `@pytest.mark.unit` or `@pytest.mark.integration` on each class or at module level. Test methods always start with `test_` and describe the scenario: `test_init_default`, `test_generate_hypotheses_success`, `test_empty_llm_response`. [PATTERN: All 5 test files examined group tests into classes by concern] [FACT: test_hypothesis_generator.py uses 7 test classes; test_convergence.py uses 4+ test classes]

    ```python
    class TestHypothesisGeneratorInit:
        """Test HypothesisGeneratorAgent initialization."""

    class TestHypothesisGeneration:
        """Test hypothesis generation with real Claude."""

    class TestHypothesisValidation:
        """Test hypothesis validation."""

    class TestDatabaseOperations:
        """Test database storage and retrieval (uses mocks)."""

    class TestEdgeCases:
        """Test edge cases and error handling."""
    ```

### 16. Test Markers and Skip Patterns

16. Always mark tests with appropriate tier (`unit`/`integration`/`e2e`). Always use `pytestmark` at module level for service-dependency skips. Never use `@pytest.mark.skip` without a `reason`. [PATTERN: All 3 agent test files examined use this exact pattern] [FACT: pytest.ini:26-41 defines all markers]

    Available markers: `unit`, `integration`, `e2e`, `slow`, `smoke`, `requires_api_key`, `requires_neo4j`, `requires_chromadb`, `requires_claude`.

    ```python
    pytestmark = [
        pytest.mark.requires_claude,
        pytest.mark.skipif(
            not os.getenv("ANTHROPIC_API_KEY"),
            reason="Requires ANTHROPIC_API_KEY for real LLM calls"
        )
    ]
    ```

### 17. Test Fixture Patterns

17. Always use `Mock()` from `unittest.mock`, not third-party mocking libraries. Always use `AsyncMock` for async methods (imported from `unittest.mock`). Always name mock fixtures `mock_{thing}` and real fixtures without the prefix. Always reset singletons in test fixtures -- the autouse `reset_singletons` handles most cases, but module-specific resets may be needed (e.g., `reset_event_bus()`). [FACT: conftest.py provides mock_llm_client, mock_anthropic_client, mock_knowledge_graph, mock_vector_db, mock_concept_extractor, mock_cache -- 6+ mock fixtures following identical pattern] [FACT: conftest.py:725-783 provides 4 real service fixtures] [FACT: test_event_bus.py:24-29]

    Fixtures follow a layered pattern:
    1. **Session-scoped** (`scope="session"`): File paths, loaded data (immutable across all tests).
    2. **Function-scoped** (default): Mutable objects like agents, temp dirs, mock clients.
    3. **Autouse**: `reset_singletons` (resets all module singletons after each test) and `cleanup_test_files`. [FACT: conftest.py:332-393]

    Mock fixture convention:
    ```python
    @pytest.fixture
    def mock_llm_client():
        mock = Mock()
        mock.generate.return_value = "Mocked Claude response"
        mock.generate_structured.return_value = {...}
        return mock
    ```

    Real service fixtures include skip logic:
    ```python
    @pytest.fixture
    def real_anthropic_client():
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("ANTHROPIC_API_KEY required")
        ...
    ```

### 18. Mocking Strategy

18. Use `@patch('kosmos.module.dependency')` for database and external service mocking. Use real API calls for LLM tests (marked with `requires_claude`). Always use `store_in_db=False` in tests that don't need database interaction. [PATTERN: Consistent across all agent test files]

    Two mocking approaches coexist intentionally:
    1. **Real Claude API calls** for LLM-dependent tests (marked `requires_claude`).
    2. **Mocked dependencies** for isolation of non-LLM logic (database, literature search, etc.).

    ```python
    # Real API call test
    def test_generate_hypotheses_success(self, hypothesis_agent):
        response = hypothesis_agent.generate_hypotheses(
            research_question="How does attention mechanism affect performance?",
            store_in_db=False
        )

    # Mocked dependency test
    @patch('kosmos.agents.hypothesis_generator.get_session')
    def test_store_hypothesis(self, mock_get_session, hypothesis_agent):
        mock_session = MagicMock()
        ...
    ```

### 19. Test Helper Functions

19. Define data-construction helpers as module-level functions (not in conftest.py) when they are specific to one test file. Use `unique_id()` to prevent test interference from cached data. [PATTERN: Found in 3 of 5 test files examined] [FACT: test_data_analyst.py:39-95 defines `unique_id()`, `make_metadata()`, `make_result()`]

    ```python
    def unique_id() -> str:
        """Generate unique ID for test isolation."""
        return uuid.uuid4().hex[:8]

    def make_result(p_value, effect_size, ...) -> ExperimentResult:
        """Helper to create experiment results with specific values."""
        ...
    ```

### 20. pytest.ini Configuration

20. Never add tests that run longer than 300 seconds. Always declare custom markers in pytest.ini before using them. [FACT: pytest.ini:1-69]

    Key settings:
    - `asyncio_mode = auto` -- async tests are auto-detected, no `@pytest.mark.asyncio` needed.
    - `--cov-fail-under=80` -- 80% minimum branch coverage enforced.
    - `--strict-markers` -- undefined markers cause errors.
    - `timeout = 300` -- 5-minute test timeout.
    - `log_file = tests/test_run.log` -- test run logs persisted.

### 21. Dual Model Pattern (Pydantic + SQLAlchemy)

21. Always define runtime models as Pydantic `BaseModel` with `Field(...)` validators. Always define DB models as SQLAlchemy with `Column()`. Perform conversion in the agent methods that touch the database (`_store_*`, `_load_*`). [PATTERN: Hypothesis, Experiment, and Result each have both Pydantic (in `kosmos/models/`) and SQLAlchemy (in `kosmos/db/models.py`) representations]

### 22. Pydantic Model Style

22. Always use `Field(...)` with `description=` for all fields. Use `field_validator` with `@classmethod` for custom validation. Use `ConfigDict(use_enum_values=False)` to preserve enum objects. Include `to_dict()` method for serialization. Score fields use `Field(None, ge=0.0, le=1.0)` bounds. [PATTERN: All Pydantic models in `kosmos/models/` follow identical conventions] [FACT: hypothesis.py:50-84, experiment.py:42-68, result.py:61-103]

### 23. Error Handling: Fail-Open / Degrade Gracefully

23. Always wrap optional dependency initialization in try/except. Log at WARNING level. Set the dependency to None and disable the feature flag. Never let an optional dependency failure prevent the agent from starting. [PATTERN: Found in all 5 agent classes and multiple core modules] [FACT: literature_analyzer.py:109-115]

    ```python
    try:
        self.knowledge_graph = get_knowledge_graph()
    except Exception as e:
        logger.warning(f"Knowledge graph unavailable: {e}")
        self.knowledge_graph = None
        self.use_knowledge_graph = False
    ```

### 24. Per-Item Error Handling in Loops

24. Never let one bad item crash a batch operation. Catch per-item, log the error, and continue processing remaining items. [PATTERN: Found in hypothesis_generator, experiment_designer, data_analyst] [FACT: hypothesis_generator.py:196-204]

    ```python
    for hyp in hypotheses:
        try:
            if self._validate_hypothesis(hyp):
                validated.append(hyp)
        except Exception as e:
            logger.error(f"Error validating hypothesis: {e}")
    ```

### 25. Provider Interface Compliance

25. All LLM providers must implement the `LLMProvider` ABC from `base.py:156`, which requires four abstract methods: `generate()`, `generate_async()`, `generate_with_messages()`, `generate_structured()`. Two optional methods (`generate_stream()`, `generate_stream_async()`) have default `NotImplementedError` implementations. [FACT: base.py:156,310,336]

### 26. Provider Data Types

26. Always use the three unified dataclasses (`Message`, `UsageStats`, `LLMResponse`) from `core/providers/base.py:17-155` for all provider I/O. `LLMResponse` implements 20+ string dunder and utility methods (`__str__`, `strip()`, `split()`, `startswith()`, etc. at `base.py:83-154`) making it a drop-in replacement for `str` in consumer code. This is a deliberate compatibility shim so agents that previously received raw strings from `ClaudeClient.generate()` work without modification. [FACT: base.py:17-155,83-154]

### 27. Provider Error Handling

27. Always use `ProviderAPIError` (from `base.py:417-484`) for provider errors. It has a `recoverable` flag and an `is_recoverable()` method that uses status code analysis (4xx minus 429 = non-recoverable) and message pattern matching (timeout/connection/rate_limit = recoverable, authentication/unauthorized = not). [FACT: base.py:417-484]

### 28. Provider Registration

28. All providers are registered via the module-level `_PROVIDER_REGISTRY` dict in `factory.py:16`. `_register_builtin_providers()` runs at import time (`factory.py:217`). Each registration is wrapped in try/except ImportError -- providers are only available if their SDK package is installed. [FACT: factory.py:16,217]

    Registered mappings:
    - `"anthropic"` and `"claude"` -> `AnthropicProvider`
    - `"openai"` -> `OpenAIProvider`
    - `"litellm"`, `"ollama"`, `"deepseek"`, `"lmstudio"` -> `LiteLLMProvider`

### 29. Backward Compatibility Aliases

29. Maintain backward compatibility aliases when renaming classes: `ClaudeClient = AnthropicProvider` (`anthropic.py:881`), `AnthropicConfig = ClaudeConfig` (`config.py:88`). When `anthropic` provider is selected, check both `kosmos_config.claude` (old name) and `kosmos_config.anthropic` (new name) at `factory.py:108-132`. [FACT: anthropic.py:881; config.py:88; factory.py:108-132]

### 30. Cost Tracking

30. Always use centralized `kosmos.core.pricing.get_model_cost()` for cost estimation, not hardcoded pricing. Track cumulative usage via `LLMProvider._update_usage_stats()` at `base.py:391-402`. Skip cost tracking (set to `None` or `0.0`) for CLI mode and local models. [FACT: pricing.py:54-86; base.py:391-402; anthropic.py:300,609; openai.py:255]

    **Known deviation**: OpenAI provider has its own hardcoded pricing table (`openai.py:575-613`) duplicating data from `pricing.py`. [FACT: openai.py:575-613]
## Gotchas

<!-- Counterintuitive behaviors with file:line evidence.
Ordered by bug-likelihood. All must be [FACT]. -->

### Critical Severity — Data Loss / Security / Silent Corruption

1. **`_reset_eval_state()` drops ALL database tables** — Each phase (2, 3, 4) calls `reset_database()` which does `Base.metadata.drop_all()`. If the evaluation DB is shared with production data, this destroys everything. The evaluation script does NOT create a separate database -- it uses whatever `config.database.normalized_url` points to. [FACT] (`scientific_evaluation.py:56-60`, `kosmos/db/__init__.py:200-201`)

2. **`run_tier1()` destructively deletes `kosmos.db` and `.kosmos_cache` before every run** — This destroys any prior application state on the machine for "clean evaluation." [FACT] (`run_persona_eval.py:186-190`)

3. **DEEPSEEK_API_KEY checked into git** — The `.env` file in the repo contains a real `DEEPSEEK_API_KEY` (`sk-925e...`) at line 16. This file is checked into git. [FACT] (`.env:16`)

4. **NEO4J_PASSWORD has insecure default** — `NEO4J_PASSWORD` has a hardcoded default `"kosmos-password"` in config.py, which means Neo4j will connect with a known password if no env var overrides it. [FACT] (`config.py:549`)

5. **Sandbox return value loss** — DockerSandbox extracts return values via stdout "RESULT:" prefix, but generated code stores results in local variable `results`. Non-sandbox path works correctly via `exec_locals.get('results')`. Sandbox may silently lose result data. [FACT] (`sandbox.py:442` vs `code_generator.py:187`)

6. **exec() fallback has no filesystem sandboxing** — When `use_sandbox=False` (default when Docker unavailable), code runs via `exec()` with only restricted builtins -- no filesystem isolation, network restrictions, or process isolation. The evaluation creates `CodeExecutor(max_retries=3)` without explicitly setting `use_sandbox`, so it defaults to True but silently falls back to unsandboxed. [FACT] (`executor.py:474-506`, `research_director.py:1540`, `executor.py:216-221`)

7. **exec() uses exec_globals with `__builtins__` exposed** — The `_prepare_globals()` method provides a curated set of globals, but `exec()` with globals that include `__builtins__` allows arbitrary code execution. The Docker sandbox provides isolation when enabled. [FACT] (`executor.py:617`, `executor.py:474-475`)

8. **Restricted builtins include `type` and `object`, enabling sandbox bypass** — `type` and `object` ARE included in restricted builtins, which can be used to bypass restrictions via `type.__getattribute__`. `hasattr` is included but NOT `getattr`/`setattr`/`delattr`. [FACT] (`executor.py:594-597`)

9. **Cypher injection possible via f-string interpolation** — `depth` and `max_hops` parameters are interpolated directly into Cypher queries via f-strings. Although typed as `int`, no validation prevents string injection if callers pass unexpected types. [FACT] (`graph.py:761`, `graph.py:917`)

10. **Docker health check hardcodes Neo4j credentials** — The subprocess health check command hardcodes `neo4j` / `kosmos-password`, which may differ from the actual config credentials passed to the constructor. [FACT] (`graph.py:155-156`)

### High Severity — Silent Degradation / Wrong Results

11. **Message routing is dead code at runtime** — The `AgentRegistry.register(director)` at run.py:182 sets up message routing, but all agents use direct calls (Issue #76 fix). The registry registration is cosmetic. [FACT] (`research_director.py:1391-1397 comments`, `registry.py:70-97`)

12. **AgentRegistry exists but is never called from active code** — `get_registry()` is available but the message bus infrastructure is dormant. [FACT] (`agents/registry.py:6-8`)

13. **`_send_to_convergence_detector()` deprecated but not removed** — Returns a dummy `AgentMessage`. If called, silently works but return value is meaningless. [FACT] (`research_director.py:1981-2003`)

14. **Message-based `_send_to_*` methods are dead code** — Direct-call `_handle_*_action()` methods are actually used (Issue #76). [FACT] (`research_director.py:1039-1219`)

15. **Convergence check passes empty `results=[]` to the detector** — In `_check_convergence_direct()`, the `results` list is always empty because it's never populated from DB. The detector relies on `research_plan` counts instead. [FACT] (`research_director.py:1237-1238`, `1267-1271`)

16. **Convergence `rollout_tracker.increment("literature")` is misleading** — The convergence action increments the "literature" rollout counter even though no literature search is performed. This inflates the literature rollout count reported in `get_research_status()`. [FACT] (`research_director.py:1350`)

17. **No aggregate error count check in `main()`** — main() does not compute an overall pass/fail status. It always returns 0 unless Phase 1 fails (returns 1). Phases 2-7 can all FAIL and the exit code is still 0. [FACT] (`scientific_evaluation.py:1342-1451`)

18. **Phase 4 fails hard without `--data-path`** — data_path is required for Phase 4, no default dataset exists. The result status is "FAIL" not "SKIP", meaning it counts against the overall pass rate even when no dataset is intentionally provided. [FACT] (`scientific_evaluation.py:580-585`)

19. **LLM enhancement is a no-op** — `_enhance_protocol_with_llm()` calls the LLM but never parses or applies the response to the protocol. Logs "applied" but returns protocol unchanged. Wastes API cost. [FACT] (`experiment_designer.py:714-717`)

20. **Phase 5 quality scoring uses keyword heuristics on plan preview text** — Quality is scored by searching for words like "specific", "measurable", "mechanism" in the first 500 chars of the plan. Fragile: a plan could be high quality without using these exact keywords, or low quality while mentioning them. [FACT] (`scientific_evaluation.py:741-747`)

21. **Phase 6 checks source code strings, not runtime behavior** — Rigor checks like "assumption_checking" look for the string "shapiro" in `inspect.getsource(code_generator_module)`. This verifies the code *template* contains the word, not that assumption checks are actually *executed* at runtime. [FACT] (`scientific_evaluation.py:831-833`, `870-875`)

22. **Round-trip data flow is lossy** — `write_meta_json` writes structured JSON, then `parse_tier1_results` re-extracts stats from the *markdown* report via regex, not from the original PhaseResult objects. If the markdown format changes, parsing breaks silently (returns 0/0/0.0). [FACT] (`run_persona_eval.py:244-249`)

23. **`run_phase2_tests.py` hardcodes machine-specific path** — `os.chdir("/mnt/c/python/Kosmos")` at module level will fail on any other machine. [FACT] (`run_phase2_tests.py:16`)

24. **Cache hits do NOT update usage stats** — `self.request_count` and `self.total_input_tokens` undercount when cache is active. The `get_usage_stats` method works around this by computing `total_requests_with_cache = self.request_count + self.cache_hits`. [FACT] (`anthropic.py:228-249`)

25. **`generate_async` does not call `_update_usage_stats`** — Async calls silently absent from running totals, inconsistent with the sync `generate` method. [FACT] (`anthropic.py:400-430`)

26. **`generate_stream` counts text chunks as "tokens"** — Actual token count is not available until the stream completes. The `completion_tokens` field in the emitted `LLM_CALL_COMPLETED` event is therefore wrong. [FACT] (`anthropic.py:731-732`)

27. **Cost estimation hardcodes model name** — `get_usage_stats()` hardcodes `"claude-sonnet-4-5"` model name for cost lookup regardless of what model was actually used. [FACT] (`llm.py:519`)

28. **PlanCreator and PlanReviewer bypass the provider layer entirely** — They call `anthropic_client.messages.create()` directly, meaning no caching, no cost tracking, no auto-model-selection, and no retry logic from the provider. [FACT] (`plan_creator.py:158-162`, `plan_reviewer.py:125-129`)

29. **`_update_usage_stats` skips cost when `cost_usd=0.0`** — Zero is falsy, so free-tier API calls that report `cost_usd=0.0` will not accumulate, making cost tracking slightly inaccurate. [FACT] (`base.py:401`)

30. **Two LLM client systems coexist** — Legacy `ClaudeClient` (returns `str`) and `LLMProvider` (returns `LLMResponse`) both exist. Two components (`domain_router.py:157`, `code_generator.py:764`) still use `ClaudeClient` directly and will always use Anthropic regardless of `LLM_PROVIDER` setting. [FACT] (`domain_router.py:157`; `code_generator.py:764`)

31. **Async client is Anthropic-locked** — `AsyncClaudeClient` in `async_llm.py` wraps `AsyncAnthropic` directly, not pluggable to the provider abstraction. Switching to OpenAI/LiteLLM leaves the async path still trying Anthropic. [FACT] (`async_llm.py:269`)

32. **ResearchDirector has hardcoded Anthropic async** — Initializes a separate `AsyncClaudeClient` using `os.getenv("ANTHROPIC_API_KEY")` directly, does not respect `LLM_PROVIDER` configuration, and has its own independent rate limiter and circuit breaker. [FACT] (`research_director.py:222-238`)

33. **Duplicate pricing tables** — OpenAI provider has its own hardcoded pricing table duplicating data from the centralized `pricing.py`. If prices change, both must be updated or costs will be misreported. [FACT] (`openai.py:575-613`)

34. **Non-idempotent counters on graph relationships** — `create_authored` increments `paper_count` every call regardless of merge. Calling it twice for the same pair produces `paper_count = 2` instead of 1. Same issue affects `create_discusses` (frequency) and `create_uses_method` (usage_count). [FACT] (`graph.py:615-616`, `659`, `703`)

35. **`ExperimentResult` construction uses placeholder timestamps** — Sets `start_time=_now, end_time=_now, duration_seconds=0.0` as placeholders. Analysis code relying on execution duration gets 0. [FACT] (`research_director.py:1704-1722`)

### Medium Severity — Unexpected Behavior / Fragile Patterns

36. **`get_session()` auto-commits on context exit** — Every `with get_session() as session:` block commits on normal exit, rollbacks on exception. Code that calls `session.add()` followed by explicit `session.commit()` double-commits -- the explicit commit succeeds, and the context manager commit is a no-op. [FACT] (`db/__init__.py:131-133`)

37. **Iteration increment happens only in REFINE_HYPOTHESIS handler** — If the loop skips refinement (e.g., goes directly to CONVERGE), iterations may not increment. The convergence action has its own increment path. [FACT] (`research_director.py:2704`, `research_director.py:1387`)

38. **`_actions_this_iteration` counter uses `hasattr` check for lazy initialization** — If the attribute doesn't exist on first call, it creates it via `self._actions_this_iteration = 0`. This is not initialized in `__init__`, inconsistent with all other instance variables. [FACT] (`research_director.py:2451-2453`)

39. **Budget enforcement imports `get_metrics` on every `decide_next_action()` call** — The import is inside the function body, re-imported each time. This fails silently if the metrics module is unavailable (ImportError caught). [FACT] (`research_director.py:2406-2425`)

40. **`_json_safe()` is a nested function recreated on every experiment execution call** — Handles numpy arrays, sklearn Pipelines, etc. Falls back to `str()` for unknown types, silently converting non-serializable objects to string representations. sklearn models, matplotlib figures, etc. lose all structured data when stored in DB. [FACT] (`research_director.py:1595-1613`)

41. **World model (Neo4j) failures are non-fatal** — All `_persist_*_to_graph()` methods catch exceptions and log warnings. Research continues without graph persistence. [FACT] (`research_director.py:435-436`, `474-475`, `523-524`)

42. **Neo4j failure degrades silently** — If Neo4j unavailable, `use_knowledge_graph` set to False and agent continues without graph features. No user-visible error. [FACT] (`literature_analyzer.py:114-116`)

43. **World model silently falls back to InMemoryWorldModel** — If Neo4j unavailable, only a log warning signals this. All data lost on restart. [FACT] (`factory.py:123-133`)

44. **`execute_with_data()` both prepends `data_path` as code AND passes it as `local_vars`** — Double injection for template compatibility. [FACT] (`executor.py:655-658`)

45. **Basic template lacks synthetic data** — The fallback `_generate_basic_template()` uses `pd.read_csv(data_path)` without synthetic fallback, unlike all other templates. Will crash without data. [FACT] (`code_generator.py:954-977`)

46. **FileNotFoundError is terminal in retry loop** — RetryStrategy returns None for FileNotFoundError, breaking the retry loop. Templates mitigate with synthetic data fallback, but the basic template does not. [FACT] (`executor.py:879-906`)

47. **Most retry fixes are try/except wrappers** — 8 of 11 error-type fixes simply wrap entire code in try/except, producing `results = {'error': ..., 'status': 'failed'}` rather than fixing the underlying issue. Callers must check `result.return_value` for `{'status': 'failed'}` in addition to `result.success`. [FACT] (`executor.py:869-1008`)

48. **Empty LLM protocol fallbacks** — If Claude returns empty steps or variables, designer silently generates minimal defaults (3 generic steps, 2 generic variables). These may not match the actual hypothesis domain. [FACT] (`experiment_designer.py:568-601`)

49. **Pattern detection uses `if pattern in code:` — matches inside comments and string literals** — `# eval()` or `description = "do not eval("` would trigger a CRITICAL violation. [FACT] (`code_validator.py:288`)

50. **Write-mode detection misses binary and append modes** — `open()` write-mode check misses `'wb'`, `'ab'`, `'r+'`, and variable-based modes. `open(f, 'wb')` passes check when `allow_file_read=True`. [FACT] (`code_validator.py:296-297`)

51. **`getattr()` flagged as CRITICAL** — Despite being a common safe pattern (`getattr(obj, 'attr', default)`), any generated code using `getattr` will fail validation. [FACT] (`code_validator.py:338`)

52. **Approval request truncates code to 500 chars** — Dangerous patterns beyond char 500 are not visible to the human reviewer. [FACT] (`code_validator.py:510`)

53. **Auto-fix can insert an import the validator rejects** — RetryStrategy's `COMMON_IMPORTS` includes `'os': 'import os'`, but `os` is on the `DANGEROUS_MODULES` list. [FACT] (`code_validator.py:36`, `executor.py:686`)

54. **Default ethical guideline keywords include common scientific words** — "harm", "email", "password", "survey" trigger false positives in legitimate scientific code. A bioinformatics experiment analyzing "harmful mutations" would trigger the "no_harm" guideline. [FACT] (`code_validator.py:118-119`)

55. **Code is parsed up to 3 separate times with `ast.parse()`** — A syntax error in `_check_syntax` does not prevent `_check_dangerous_imports` from also attempting to parse (it has its own try/except with string fallback). [FACT] (`code_validator.py:237`, `252`, `332`)

56. **`random_seed=0` silently replaced with 42** — Due to `or 42` pattern, zero is a valid seed but treated as falsy. [FACT] (`code_generator.py:89`)

57. **Template matching is order-dependent with no priority scoring** — The first match wins. If `GenericComputationalCodeTemplate` were registered before `TTestComparisonCodeTemplate`, t-test protocols would get generic analysis instead. [FACT] (`code_generator.py:787-793`)

58. **LLM client failure during `__init__` silently disables LLM generation** — No exception raised. If templates also don't match, only the basic fallback (which lacks synthetic data) runs. [FACT] (`code_generator.py:762-778`)

59. **`_extract_code_from_response` has weak heuristic** — If the LLM response contains no code fences, it checks for "import", "def ", or "=" to decide if it's code. A natural language response containing "=" would be treated as code. [FACT] (`code_generator.py:907-924`)

60. **Vague language check is warn-only** — `_validate_hypothesis()` detects vague words like "maybe", "might" but does NOT reject the hypothesis. Comment explicitly says "Don't fail, but warn." [FACT] (`hypothesis_generator.py:451-455`)

61. **NoveltyChecker import is guarded — fail-open design** — If `kosmos.hypothesis.novelty_checker` cannot be imported, ALL hypotheses pass without any novelty scoring. [FACT] (`hypothesis_generator.py:227-228`)

62. **Per-hypothesis novelty errors fail open** — If `check_novelty()` throws for a single hypothesis, that hypothesis is kept. Only successful checks can filter. [FACT] (`hypothesis_generator.py:223-224`)

63. **Literature context uses only top 5 papers** — Even though up to 10 papers may be fetched (max_papers_context=10), only first 5 are included in the LLM prompt. Abstracts truncated to 200 chars. [FACT] (`hypothesis_generator.py:346`)

64. **Novelty threshold inversion** — NoveltyChecker receives `similarity_threshold = 1.0 - self.min_novelty_score`. Default min_novelty_score=0.5, so similarity_threshold=0.5. This is lower than NoveltyChecker's own default of 0.75. [FACT] (`hypothesis_generator.py:211`)

65. **Different `execute()` signatures break Liskov substitution** — HypothesisGeneratorAgent.execute takes `AgentMessage` and returns `AgentMessage`. LiteratureAnalyzerAgent.execute takes `Dict` and returns `Dict`. Both inherit from `BaseAgent` with `(task: Dict) -> Dict` signature. Generic agent dispatch would break. [FACT] (`hypothesis_generator.py:91`, `literature_analyzer.py:153`, `base.py:485`)

66. **Literature search timeout collects partial results** — On timeout, already-completed source results are still included. A slow PubMed won't discard fast arXiv results. [FACT] (`unified_search.py:172-183`)

67. **LiteratureAnalyzerAgent is a singleton** — `get_literature_analyzer()` returns a global singleton. Can be reset with `reset=True`. [FACT] (`literature_analyzer.py:1050-1075`)

68. **ClaudeClient retries bypass cache** — On JSON parse failure, `generate_structured()` retries with `bypass_cache=True` to avoid getting the same bad response. [FACT] (`llm.py:466`)

69. **Citation graph on-demand build caps at 50 references + 50 citations** — Only first 50 references and 50 citations are added to Neo4j from Semantic Scholar. [FACT] (`literature_analyzer.py:821`, `838`)

70. **File cache TTL is 24 hours** — `_get_cached_analysis()` checks `time.time() - cached_at < 86400`. Stale cache entries silently return None (not deleted). [FACT] (`literature_analyzer.py:1019`)

71. **Novelty checker keyword fallback indexes papers into vector DB as side effect** — Enriches vector DB as byproduct of novelty checking. [FACT] (`novelty_checker.py:207-210`)

72. **`StoppingReason.USER_REQUESTED` used as sentinel for "no reason"** — When research continues, the reason is set to `USER_REQUESTED`. Code that filters on `reason == USER_REQUESTED` will get false positives from normal "continue" decisions. [FACT] (`convergence.py:271`)

73. **Flat novelty score triggers convergence stop** — The novelty decline check uses `>=` (i.e., `recent[i] >= recent[i+1]`), meaning a constant novelty score is also considered "declining." [FACT] (`convergence.py:424`)

74. **Convergence deferred indefinitely without experiments** — The iteration limit deferral depends on `min_experiments_before_convergence` (default 2). If no experiments ever complete, convergence is deferred indefinitely until other criteria or external safety caps intervene. [FACT] (`convergence.py:339`)

75. **`CONVERGED` can transition back to `GENERATING_HYPOTHESES`** — "Converged" is not truly terminal. Callers that assume convergence is final may be surprised. [FACT] (`workflow.py:212-213`)

76. **`PAUSED` can resume to almost any state but no mechanism remembers prior state** — 6 possible resume targets, but the caller must decide where to resume. [FACT] (`workflow.py:214-221`)

77. **`get_untested_hypotheses()` is O(n*m) due to list-based lookup** — `tested_hypotheses` is a list, not a set. The director calls this repeatedly in `decide_next_action()`. [FACT] (`workflow.py:149-151`)

78. **`use_enum_values=True` breaks `isinstance` checks** — Serialization/deserialization of `ResearchPlan` or `WorkflowTransition` returns enum fields as strings, not enum instances. `==` comparison works (because `WorkflowState` is a `str` enum) but `isinstance` checks against enum types fail. [FACT] (`workflow.py:48`, `60`)

79. **`ResearchPlan.current_state` synced only inside `transition_to()`** — If any code modifies `workflow.current_state` directly (a public attribute), the plan's state diverges silently. [FACT] (`workflow.py:323-325`)

### Medium Severity — Memory / Resource Issues

80. **BaseAgent sync `message_queue` list grows without bound** — Messages appended but never removed. Memory leak in long-running agents. [FACT] (`base.py:136-138`)

81. **`novelty_trend` list grows unboundedly** — Every `check_convergence()` call appends. Never truncated. [FACT] (`convergence.py:562`)

82. **`ExperimentLogger.events` list is unbounded** — No flush or rotation mechanism. [FACT] (`logging.py:271`)

83. **KnowledgeGraph auto-starts Docker container** — Can take 60+ seconds of blocking I/O. [FACT] (`graph.py:118-171`)

84. **Embedder init may trigger ~440MB model download** — During `PaperVectorDB.__init__`. [FACT] (`vector_db.py:103`)

85. **First-use sentence-transformer model download is ~90MB** — In novelty_detector. [FACT] (`novelty_detector.py:72-85`)

86. **`reset_knowledge_graph()` sets global to None without calling close** — Potential Neo4j connection leak. [FACT] (`graph.py:1034-1038`)

87. **`clear()` has no null guard on `self.client`** — Crashes if ChromaDB unavailable while all other methods gracefully degrade. [FACT] (`vector_db.py:370-371`)

88. **On Windows, ThreadPoolExecutor timeout does not kill executing thread** — Hung computation continues consuming resources after timeout. [FACT] (`executor.py:621-630`)

89. **Multiple `asyncio.wait_for(timeout=120)` calls with no aggregate timeout** — Each action step has 120-second timeout. With up to 60 actions in Phase 3, worst-case is 7200 seconds (2 hours) for Phase 3 alone. [FACT] (`scientific_evaluation.py:338-341`, `485-488`, `673-675`)

### Medium Severity — Blocking / Concurrency

90. **`_handle_error_with_recovery()` calls `time.sleep()` blocking the asyncio event loop** — Since `execute()` and all `_handle_*_action()` methods are async, this blocks the entire event loop thread during error backoff (2, 4, 8 seconds). [FACT] (`research_director.py:674`)

91. **Retry loop calls `time.sleep()` synchronously** — In async contexts this blocks the event loop. [FACT] (`executor.py:335`)

92. **Sequential fallback calls `asyncio.get_event_loop().run_until_complete()`** — Raises `RuntimeError` if an event loop is already running (e.g., during async execution). Only taken when concurrent execution is disabled. [FACT] (`research_director.py:2171-2174`)

93. **Sync `_workflow_context()` yields workflow without lock** — No mutual exclusion between sync and async paths. [FACT] (`research_director.py:376-379`)

94. **World model factory explicitly NOT thread-safe** — `_world_model` global has no lock. [FACT] (`factory.py:38`)

95. **PaperVectorDB singleton not thread-safe** — Concurrent calls during init could create multiple instances. [FACT] (`vector_db.py:443-477`)

96. **KnowledgeGraph singleton has no thread safety guarantees** — [FACT] (`graph.py:999-1038`)

97. **LLM singleton uses double-checked locking, but `reset=True` replaces client for ALL threads** — [FACT] (`llm.py:643-649`)

### Medium Severity — Type / Serialization Surprises

98. **`LLMResponse` with empty content is falsy** — `if not response:` incorrectly treats empty LLM response as failure even if the API call succeeded. [FACT] (`base.py:98-99`)

99. **`response.strip()` returns `str`, not `LLMResponse`** — After calling any string method, you lose `.usage`, `.model`, `.finish_reason` metadata. [FACT] (`base.py:107-108`)

100. **`if False: yield` in `generate_stream_async` is load-bearing dead code** — Removing it changes the function from an async generator to a plain coroutine, which breaks callers using `async for`. [FACT] (`base.py:360-363`)

101. **`ConfigDict(use_enum_values=False)` means `model_dump()` returns enum objects** — Must use `to_dict()` for string serialization. [FACT] (`hypothesis.py:156`)

102. **No `model_config` on `HypothesisGenerationResponse`** — Unlike `Hypothesis`, the response model does not set `use_enum_values=False`. Pydantic default behavior applies, which may differ between Pydantic v1 and v2. [FACT] (`hypothesis.py:199`)

103. **`ResultExport.export_markdown()` formats `Optional[float]` with `:.2f` without null check** — Raises `TypeError` on `None`. [FACT] (`result.py:349-353`)

104. **`export_csv()` lazy-imports `pandas`** — Only pandas dependency in models layer. Error surfaces only when CSV export is attempted. [FACT] (`result.py:293`)

105. **`to_dict()` is hand-written, not `model_dump()`** — The 100-line `to_dict()` method manually serializes every field. Adding a new field to the model without updating `to_dict()` means it silently disappears from serialization. [FACT] (`experiment.py:471-573`)

106. **`validate_steps` silently sorts steps by `step_number`** — Input order not preserved. Side effect hidden in a validator. [FACT] (`experiment.py:438`)

107. **`_MAX_SAMPLE_SIZE` is module-private but affects public API** — The 100,000 ceiling is not documented in field descriptions and silently clamps values. [FACT] (`experiment.py:19`, `120-124`)

108. **`ExperimentType` lives in hypothesis.py, not experiment.py** — Anyone looking in experiment.py will find only a re-import. This also means experiment.py cannot be imported without hypothesis.py loading. [FACT] (`experiment.py:14`)

109. **`re` imported at call time in `StatisticalTestSpec.parse_effect_size`** — Micro-performance hit on every validation call. [FACT] (`experiment.py:293`)

110. **LLM coercion validators log warnings at high volume** — `coerce_sample_size`, `coerce_protocol_sample_size`, and implicit coercion in `parse_effect_size` all use `_experiment_logger.warning()`. In high-throughput scenarios, these warnings can flood logs. [FACT] (`experiment.py:116-117`, `121-123`)

111. **`_DEFAULT_CLAUDE_SONNET_MODEL` imported at module scope in hypothesis.py** — Makes the entire config module a hard dependency of this data model. If config loading has side effects (env var reads, file I/O), those trigger on import. [FACT] (`hypothesis.py:13`)

### Lower Severity — Dead Code / Unused Features

112. **`register_message_handler()` stores handlers but `process_message()` does NOT dispatch to them** — Dead code unless subclasses explicitly use it. [FACT] (`base.py:406-415`)

113. **`_on_pause()` and `_on_resume()` hooks exist but are never called** — Overriding them has no effect. `pause()` and `resume()` do NOT invoke these hooks. [FACT] (`base.py:513-517`, `base.py:189-206`)

114. **`validate_statement` predictive-language check is dead code** — Never warns or fails. [FACT] (`hypothesis.py:101`)

115. **`DIMENSION_WEIGHTS` defined but not used** — Approval uses simple arithmetic mean. If someone adds weighted scoring, they may assume weights are already applied. [FACT] (`plan_reviewer.py:68-69`)

116. **`MemoryStore` and `FeedbackLoop` designed but not integrated** — Phase 7 infrastructure, not wired into any agent. [FACT] (`core/memory.py:66-104`, `core/feedback.py:76-105`)

117. **`LocalModelConfig` is dead configuration** — Settings like `max_retries`, `circuit_breaker_threshold` are defined but not wired into any provider implementation. Changing these values has no effect. [ABSENCE] (`config.py:752-822`)

118. **`start()` silently ignores duplicate calls** — If an agent is in ERROR state, you cannot restart it -- `start()` just warns and returns. [FACT] (`base.py:161-163`)

### Lower Severity — Configuration Surprises

119. **Singleton config goes stale** — No runtime config validation exists beyond Pydantic initialization. If environment variables change after `get_config()`, the singleton retains stale values unless `reload=True` is passed. [FACT] (`config.py:1140`)

120. **Dual-read inconsistency risk** — Several env vars (`ANTHROPIC_API_KEY`, `REDIS_ENABLED`, `REDIS_URL`, `NEO4J_URI/USER/PASSWORD`) are read in two places -- once by Pydantic during config initialization and again directly by subsystems. If values are modified in the config singleton but not in the actual environment, the two readings diverge. [PATTERN: 5 variables affected]

121. **Nested env var propagation** — Pydantic `BaseSettings` does not auto-propagate env vars to nested `BaseSettings` submodels. Only LiteLLM has the workaround (`sync_litellm_env_vars`). Other sub-configs may be similarly affected. [FACT] (`config.py:985`)

122. **`config.openai` can be None** — Three optional provider configs use conditional factory functions. Code must null-check before access. [FACT] (`config.py:896-919`)

123. **Alerting, profiling, and KOSMOS_SKILLS_DIR bypass Pydantic** — ~17 env vars are read via raw `os.getenv()` with no type validation. String-only, no Pydantic model. [FACT] (`monitoring/alerts.py`; `agents/skill_loader.py:148`)

124. **Flat config dict drift** — The agent layer uses a flat dict bridge (`flat_config`) constructed manually in `cli/commands/run.py:147-170`. If new config fields are added to `KosmosConfig` but not to `flat_config`, agents will not see them. [FACT] (`run.py:147-170`)

125. **CLI mode detection is fragile** — AnthropicProvider CLI mode is triggered by `self.api_key.replace('9', '') == ''` -- any API key consisting entirely of 9s activates CLI proxy mode. A single-character key of `"9"` triggers it. No minimum length check. [FACT] (`anthropic.py:110`, `llm.py:179`)

126. **Qwen model silent injection** — LiteLLM provider automatically injects `"Do not use thinking mode"` system directive for Qwen models and enforces minimum 8192 max_tokens. Happens silently. [FACT] (`litellm_provider.py:158-170`, `205-220`)

127. **Auto-model-selection silently disabled in CLI mode** — Even if config requests it, no warning logged. [FACT] (`anthropic.py:187`)

128. **`generate_structured` modifies system prompt by appending JSON instructions** — If the system prompt contains its own JSON formatting instructions, these will conflict. [FACT] (`anthropic.py:530`)

129. **`generate_with_messages()` uses `self.model` directly, ignoring `self.default_model`** — If the caller previously changed `self.model`, this persists. [FACT] (`llm.py:389`)

130. **`generate_structured()` appends schema to system prompt on every retry** — The system prompt is rebuilt from the original `system` param (so no duplication), but the schema instruction is always added even if the original prompt already contains JSON instructions. [FACT] (`llm.py:456`)

131. **Global `_default_client` is `Optional[Union[ClaudeClient, LLMProvider]]`** — Callers expecting one type may get the other depending on config and `use_provider_system` flag. [FACT] (`llm.py:609`)

### Lower Severity — Misleading API / Naming

132. **`_validate_query` says "truncating" but doesn't truncate** — The log message says "truncating to 1000" but the method returns `True` without modifying the query. Callers must do their own truncation. [FACT] (`base_client.py:248-250`)

133. **`_normalize_paper_metadata` is not enforced by ABC** — Missing `@abstractmethod` means a subclass can be instantiated without implementing it. The `NotImplementedError` only surfaces when the method is actually called. [FACT] (`base_client.py:255`)

134. **`PaperMetadata` has no validation** — Being a plain dataclass, it accepts any values for any field. A `citation_count` of -999 or a `title` of `None` will not raise errors. [FACT] (`base_client.py:78`)

135. **`_handle_api_error` swallows exceptions** — It logs but does not re-raise. Callers that need error propagation must handle it themselves. [FACT] (`base_client.py:229-233`)

136. **`raw_data` excluded from `to_dict()`** — Large API responses stored in `raw_data` are invisible to serialization but consume memory. [FACT] (`base_client.py:78`, `99-122`)

137. **`BudgetExceededError` defined but no catch sites exist** — Budget overruns propagate as unhandled exceptions, potentially crashing a research run. [FACT] (`core/metrics.py:63`)

138. **`_normalize_paper_metadata` raises `NotImplementedError` but NOT marked `@abstractmethod`** — Subclasses can instantiate without implementing it. [FACT] (`base_client.py:255`)

139. **DelegationManager raises `RuntimeError` at task execution time, not at init** — No validation at initialization that required agents are in the `agents` dict. [FACT] (`delegation.py:395-399`)

140. **`filter_redundant_tasks` shallow-copies numpy arrays** — `copy()` on a list of numpy arrays produces a shallow copy. Safe because `index_past_tasks` extends rather than mutates, but worth noting. [FACT] (`novelty_detector.py:320-342`)

141. **Target approval rate is a design goal, not enforced** — "~80% on first submission" is documented but the mock review path almost always approves structurally-valid plans. [FACT] (`__init__.py:25`)

### Lower Severity — Deprecated APIs

142. **`datetime.utcnow()` used for defaults** — Deprecated in Python 3.12+. Produces naive datetimes. [FACT] (`hypothesis.py:76-77`, `result.py:203`, `hypothesis.py:262`, `296`)

143. **`datetime.utcfromtimestamp` used** — Deprecated in Python 3.12+. Will emit deprecation warnings on newer Python versions. [FACT] (`logging.py:52`)

### Lower Severity — Provider Feature Parity

144. **No sync retry in providers** — None of the three sync provider implementations have built-in retry logic. They catch all exceptions and raise `ProviderAPIError`. Callers must handle retries. Only the async path has tenacity/circuit breaker. [ABSENCE] (`anthropic.py`; `openai.py`; `litellm_provider.py`)

145. **Feature parity gap across providers** — Caching, auto model selection, and event bus integration are Anthropic-only features, not part of the base provider interface. Switching providers loses these capabilities silently. [ABSENCE] (`openai.py`; `litellm_provider.py`)

146. **Event bus only fires during Anthropic streaming** — Only the AnthropicProvider emits LLM events. Non-streaming calls and other providers produce no events. Monitoring depending on these events will be blind to non-Anthropic-streaming activity. [ABSENCE] (non-streaming `generate()` calls; OpenAI; LiteLLM)

147. **Inconsistent JSON parsing in `generate_structured()`** — Anthropic and OpenAI use `parse_json_response()` from `utils/json_parser.py`; LiteLLM does inline `json.loads()` with manual markdown stripping. May produce different parsing behavior for edge cases. [FACT] (`litellm_provider.py:448-468`)

148. **OpenAI token counting is approximate for local models** — Falls back to `len(text) // 4` estimate when usage stats unavailable. [FACT] (`openai.py:236-239`)

### Lower Severity — Hidden Coupling

149. **`_DEFAULT_CLAUDE_SONNET_MODEL` and `_DEFAULT_CLAUDE_HAIKU_MODEL` are effectively public API** — Underscore-prefixed "private" constants imported by 7+ files. [FACT] (`config.py:17-18`)

150. **CLI directly mutates config singleton** — `config_obj.research.enabled_domains = [domain]` is a side effect on global config that affects other singletons. [FACT] (`cli/commands/run.py:136-137`)

151. **`sync_litellm_env_vars()` hardcoded `env_map` must stay in sync with `LiteLLMConfig` fields** — Adding a new field without updating the validator silently drops env var. [FACT] (`config.py:986-1022`)

152. **Async LLM client reads `ANTHROPIC_API_KEY` directly from `os.getenv()`** — Bypasses config system. Different auth path from sync `get_client()`. [FACT] (`research_director.py:228-239`)

153. **`code_generator` has its own fallback chain** — Bypasses `get_client()` entirely with its own multi-provider fallback: ClaudeClient -> LiteLLMProvider -> disable LLM. The only place with this pattern, may behave differently from other components. [FACT] (`code_generator.py:762-778`)

### Lower Severity — Logging / Output

154. **Handler wipe on re-init** — Calling `setup_logging()` a second time silently destroys all previously-configured handlers, including any added by libraries. [FACT] (`logging.py:179`)

155. **TextFormatter mutates shared LogRecord** — When colors are on, `record.levelname` is mutated in place. If the same record is processed by both a TextFormatter and a JSONFormatter (e.g., console + file), the JSON output will contain ANSI escape codes. [FACT] (`logging.py:128`)

156. **JSONFormatter has no serialization guard** — If `record.extra` contains non-JSON-serializable objects, `json.dumps` raises `TypeError` and the log line is lost. [FACT] (`logging.py:82`)

157. **Early exit on Phase 1 failure still writes a report** — If preflight fails, the report is generated with only Phase 1 results and written to disk before returning exit code 1. A partial report file exists even on total failure. [FACT] (`scientific_evaluation.py:1373-1380`)

158. **`scientific_evaluation.main()` is async but called via `subprocess.run()`** — `run_persona_eval.py` launches it as a subprocess. Async is handled internally via `asyncio.run()`. [FACT] (`scientific_evaluation.py:1342`, `1482`, `run_persona_eval.py:196`)

### Lower Severity — Comparison / Regex

159. **Check regex requires single-word names** — `r"\|\s*(\w+)\s*\|\s*(PASS|FAIL)\s*\|([^|]*)\|"` requires check names to be single words (`\w+`). Any check name containing hyphens, spaces, or dots will not be captured. In practice, `generate_report()` uses underscore-separated names which do match `\w+`. [FACT] (`compare_runs.py:66-67`, `scientific_evaluation.py:1259`)

160. **`compute_delta()` returns string `"N/A"` when either value is None** — Type annotation absent and consumers treat it as string alongside "+3" or "-1". [FACT] (`compare_runs.py:137-138`)

161. **Paper claims keyed by integer claim number** — If markdown report changes claim numbering between versions, the diff will show false changes. [FACT] (`compare_runs.py:118-119`)

162. **Quality score regex requires `phase\d+_` prefix** — Any quality dimension not following this naming convention will be silently excluded. [FACT] (`compare_runs.py:75`)

163. **`get_next_version()` splits on `_` and takes index 0** — If a directory name lacks `_` (e.g., plain `v001`), IndexError is caught and the directory is silently skipped. [FACT] (`run_persona_eval.py:79`)

164. **`compare_runs.py` is entirely self-contained** — Zero imports from the Kosmos application code. Only reads files and writes JSON. No database, no LLM, no network calls. [FACT] (`compare_runs.py`)

165. **`get_stats()` runs 9 separate Cypher queries** — 4 node counts + 5 relationship counts with no caching. Can be slow on large graphs. [FACT] (`graph.py:981`)

166. **`embeddings[i:batch_end].tolist()` assumes numpy array** — If `embeddings` is a Python list, the `.tolist()` call on a list slice is a no-op. In practice safe because `self.embedder.embed_papers()` returns numpy. Only breaks with manually-provided non-numpy embeddings. [FACT] (`vector_db.py:176`)

167. **If generated code does not assign to `results` or `result`, `return_value` is `None`** — Even on successful execution. [FACT] (`executor.py:516`)

168. **`CodeValidator` is re-exported from executor module** — `from kosmos.execution.executor import CodeValidator` works but is an indirect import path. [FACT] (`executor.py:663-664`)

169. **tenacity imported optionally in `core/async_llm.py`** — If missing, API calls silently run without retry protection. No warning logged. [FACT] (`core/async_llm.py:33-39`)

170. **PlanCreator and PlanReviewer fall back to mock results on ANY exception** — Any LLM failure silently produces deterministic mock tasks/optimistic scores. [FACT] (`plan_creator.py:194-198`, `plan_reviewer.py:161-162`)

171. **DB init failure logged as warning only** — Director continues without working database, causing cascading failures when handlers query DB. [FACT] (`research_director.py:131-139`)

172. **KnowledgeGraph connection failure silently swallowed** — `self.graph = None`. Callers that skip `self.connected` check get `AttributeError`. [FACT] (`graph.py:96-99`)

173. **Docker sandbox fallback is silent** — No error raised when Docker unavailable. If `use_sandbox=True` but Docker not installed, executor sets `use_sandbox = False` and continues with restricted builtins. [FACT] (`executor.py:216-220`)

174. **`is_recoverable()` pattern matching has order-dependent behavior** — "recoverable_patterns" check runs before "non_recoverable_patterns", so ambiguous error messages default to recoverable. [FACT] (`base.py:466-477`)

175. **`validate_primary_test` validator handles both dict and model instances** — Because Pydantic v2 field ordering means `statistical_tests` may arrive as raw dicts before model construction. Fragile if Pydantic changes validation ordering. [FACT] (`result.py:220-226`)

176. **`datetime.utcnow()` in `created_at` default** — `result.py:203` deprecated in Python 3.12+. [FACT] (`result.py:203`)
## Hazards — Do Not Read

| Pattern | Tokens | Why |
|---------|--------|-----|
| `kosmos/agents/registry.py` | ~1K | Dead code. Message bus infrastructure is dormant (Issue #76). All agents use direct calls. `get_registry()` available but never called from active code. [FACT: `registry.py:6-8`] |
| `research_director.py:1039-1219` | ~3K | Dead code. Message-based `_send_to_*` methods replaced by direct-call `_handle_*_action()` methods (Issue #76). [FACT: `research_director.py:1039-1219`] |
| `research_director.py:1981-2003` | ~0.5K | Dead code. `_send_to_convergence_detector()` deprecated but not removed. Returns dummy `AgentMessage`. [FACT: `research_director.py:1981-2003`] |
| `core/memory.py` | ~2K | Phase 7 infrastructure. `MemoryStore` designed but not integrated into any agent. [FACT: `core/memory.py:66-104`] |
| `core/feedback.py` | ~2K | Phase 7 infrastructure. `FeedbackLoop` designed but not integrated into any agent. [FACT: `core/feedback.py:76-105`] |
| `config.py:752-822` | ~2K | Dead configuration. `LocalModelConfig` settings (`max_retries`, `circuit_breaker_threshold`, etc.) defined but not wired into any provider. Changing values has no effect. [ABSENCE: `config.py:752-822`] |
| `agents/base.py:406-415` | ~0.3K | Dead code. `register_message_handler()` stores handlers but `process_message()` does NOT dispatch to them. [FACT: `base.py:406-415`] |
| `agents/base.py:189-206` | ~0.5K | Dead code. `_on_pause()` and `_on_resume()` hooks exist but `pause()`/`resume()` do NOT invoke them. Overriding has no effect. [FACT: `base.py:189-206`, `513-517`] |
| `hypothesis.py:101` | ~0.1K | Dead code. `validate_statement` predictive-language check never warns or fails. [FACT: `hypothesis.py:101`] |
| `plan_reviewer.py:68-69` | ~0.1K | Dead code. `DIMENSION_WEIGHTS` defined but not used. Approval uses simple arithmetic mean. [FACT: `plan_reviewer.py:68-69`] |
| `compare_runs.py` | ~4K | Self-contained utility. Zero imports from Kosmos application code. Only reads files (meta.json, EVALUATION_REPORT.md) and writes JSON. Will not teach you about the system. [FACT: `compare_runs.py`] |
| `run_phase2_tests.py` | ~5K | Machine-specific. Hardcodes `os.chdir("/mnt/c/python/Kosmos")` at module level. Will fail on any other machine. [FACT: `run_phase2_tests.py:16`] |
| `experiment_designer.py:714-717` | ~0.2K | No-op code. `_enhance_protocol_with_llm()` calls the LLM but never parses or applies the response. Logs "applied" but returns protocol unchanged. Wastes API cost only. [FACT: `experiment_designer.py:714-717`] |
| `openai.py:575-613` | ~1K | Duplicate data. Hardcoded pricing table duplicates centralized `pricing.py`. Read `pricing.py` instead for authoritative pricing. [FACT: `openai.py:575-613`] |
## Extension Points

| Task | Start Here | Also Touch | Watch Out |
|------|------------|------------|-----------|
| Add a new LLM provider | `kosmos/core/providers/base.py` (LLMProvider ABC) | `config.py` (provider config), `llm.py` (get_client factory), `pricing.py` (cost data) | Feature parity gap: caching, auto model selection, and event bus integration are Anthropic-only. Your new provider will lack these unless you add them. [ABSENCE: `openai.py`; `litellm_provider.py`]. Also: `generate_structured()` JSON parsing differs between providers -- Anthropic/OpenAI use `parse_json_response()`, LiteLLM does inline `json.loads()`. [FACT: `litellm_provider.py:448-468`]. No sync retry in any provider -- callers must handle retries. [ABSENCE] |
| Add a new agent type | `kosmos/agents/base.py` (BaseAgent ABC) | `kosmos/agents/__init__.py`, `cli/commands/run.py` (flat_config dict) | Two existing agents have `execute()` signatures incompatible with base class: `AgentMessage` instead of `Dict`. [FACT: `hypothesis_generator.py:91`; `experiment_designer.py:109`; `base.py:485-497`]. Also: `_on_pause()`/`_on_resume()` hooks are dead code -- do not rely on them. [FACT: `base.py:189-206`]. `message_queue` grows without bound in long-running agents. [FACT: `base.py:136-138`]. `start()` silently ignores duplicate calls and cannot restart from ERROR state. [FACT: `base.py:161-163`]. `register_message_handler()` stores handlers but `process_message()` does NOT dispatch to them. [FACT: `base.py:406-415`] |
| Add a new code template | `kosmos/execution/code_generator.py` (template classes) | `code_validator.py` (validation rules) | Template matching is order-dependent with no priority scoring -- first match wins. [FACT: `code_generator.py:787-793`]. Always include synthetic data fallback; the basic template lacks it and crashes without data. [FACT: `code_generator.py:954-977`]. `random_seed=0` is silently replaced with 42 due to `or 42`. [FACT: `code_generator.py:89`]. The `_extract_code_from_response` heuristic treats any text with "=" as code. [FACT: `code_generator.py:907-924`] |
| Add a new experiment type | `kosmos/models/experiment.py` (ExperimentProtocol) | `kosmos/models/hypothesis.py` (ExperimentType enum lives HERE, not experiment.py) | `ExperimentType` is defined in `hypothesis.py:14`, not `experiment.py`. `to_dict()` is hand-written -- new fields silently disappear from serialization. [FACT: `experiment.py:471-573`]. `validate_steps` silently reorders input by `step_number`. [FACT: `experiment.py:438`]. `_MAX_SAMPLE_SIZE` (100,000) silently clamps values. [FACT: `experiment.py:19`, `120-124`] |
| Add a new convergence criterion | `kosmos/core/convergence.py` | `research_director.py` (`_check_convergence_direct`) | `novelty_trend` grows unboundedly -- every `check_convergence` call appends, never truncated. [FACT: `convergence.py:562`]. Flat novelty score (>=) triggers "declining" stop. [FACT: `convergence.py:424`]. `StoppingReason.USER_REQUESTED` is reused as "no reason" sentinel for normal "continue" decisions. [FACT: `convergence.py:271`]. Convergence check passes empty `results=[]` -- detector relies on `research_plan` counts. [FACT: `research_director.py:1237-1238`] |
| Add a new workflow state | `kosmos/core/workflow.py` (WorkflowState enum, transitions) | `research_director.py` (decide_next_action dispatcher) | `CONVERGED` is NOT terminal -- it can transition back to `GENERATING_HYPOTHESES`. [FACT: `workflow.py:212-213`]. `PAUSED` can resume to 6 states but no mechanism remembers which was active before pausing. [FACT: `workflow.py:214-221`]. `use_enum_values=True` means serialized enums become strings -- `isinstance` checks fail. [FACT: `workflow.py:48`, `60`]. `current_state` synced only via `transition_to()` -- direct modification causes silent divergence. [FACT: `workflow.py:323-325`] |
| Add a new config field | `config.py` (KosmosConfig Pydantic model) | `cli/commands/run.py:147-170` (flat_config dict bridge), `sync_litellm_env_vars()` if LiteLLM-related | Flat config dict must be updated manually -- agents won't see new fields otherwise. [FACT: `run.py:147-170`]. Nested env var propagation does not work for nested BaseSettings submodels. [FACT: `config.py:985`]. ~17 env vars bypass Pydantic entirely via raw `os.getenv()`. [FACT: `monitoring/alerts.py`; `agents/skill_loader.py:148`]. Singleton goes stale unless `reload=True`. [FACT: `config.py:1140`]. Dual-read inconsistency: env vars read both by Pydantic init and directly by subsystems can diverge. [PATTERN: 5 variables affected] |
| Add a new literature source | `kosmos/literature/base_client.py` (BaseLiteratureClient ABC) | `unified_search.py` (multi-source orchestration), `literature_analyzer.py` (singleton agent) | `_validate_query` says "truncating" but doesn't. [FACT: `base_client.py:248-250`]. `_normalize_paper_metadata` is NOT enforced by ABC (`@abstractmethod` missing). [FACT: `base_client.py:255`]. `_handle_api_error` swallows exceptions. [FACT: `base_client.py:229-233`]. `PaperMetadata` has no validation -- accepts anything. [FACT: `base_client.py:78`]. Timeout collects partial results. [FACT: `unified_search.py:172-183`] |
| Add a Neo4j entity type | `kosmos/knowledge/graph.py` (KnowledgeGraph) | `world_model/factory.py` | Non-idempotent counters: relationship creation increments counts even with `merge=True`. [FACT: `graph.py:615-616`, `659`, `703`]. Connection failures silently swallowed -- `self.graph = None`. [FACT: `graph.py:96-99`]. Auto-starts Docker container (60+ seconds blocking I/O). [FACT: `graph.py:118-171`]. Singleton not thread-safe. [FACT: `graph.py:999-1038`]. `reset_knowledge_graph()` leaks connections (sets to None without calling close). [FACT: `graph.py:1034-1038`] |
| Add a new evaluation phase | `scientific_evaluation.py` | `run_persona_eval.py`, `compare_runs.py` (regex patterns) | `_reset_eval_state()` drops ALL database tables before each phase. [FACT: `scientific_evaluation.py:56-60`]. No aggregate timeout -- each action gets 120s, worst case 2 hours per phase. [FACT: `scientific_evaluation.py:338-341`]. `main()` always returns 0 unless Phase 1 fails. [FACT: `scientific_evaluation.py:1342-1451`]. Compare regex requires `phase\d+_` prefix for quality dimensions. [FACT: `compare_runs.py:75`]. Check regex requires `\w+` single-word names. [FACT: `compare_runs.py:66-67`] |
| Add a new safety check | `kosmos/safety/code_validator.py` | `executor.py` (RetryStrategy COMMON_IMPORTS) | Pattern detection uses `if pattern in code:` -- matches inside comments and string literals. [FACT: `code_validator.py:288`]. `getattr()` is already flagged as CRITICAL. [FACT: `code_validator.py:338`]. Write-mode detection misses `'wb'`, `'ab'`, `'r+'`. [FACT: `code_validator.py:296-297`]. Auto-fix can insert imports the validator rejects (`os`). [FACT: `code_validator.py:36`, `executor.py:686`]. Code parsed up to 3 times. [FACT: `code_validator.py:237`, `252`, `332`]. Approval truncates to 500 chars. [FACT: `code_validator.py:510`] |
| Add vector search features | `kosmos/knowledge/vector_db.py` | `novelty_checker.py` (uses vector DB as side effect) | `clear()` crashes if ChromaDB unavailable -- no null guard, unlike all other methods. [FACT: `vector_db.py:370-371`]. Singleton not thread-safe. [FACT: `vector_db.py:443-477`]. Init may trigger ~440MB model download. [FACT: `vector_db.py:103`]. `embeddings` slicing assumes numpy array. [FACT: `vector_db.py:176`] |
| Add logging/monitoring | `kosmos/core/logging.py` | `anthropic.py` (event bus) | Handler wipe: re-calling `setup_logging()` destroys all handlers. [FACT: `logging.py:179`]. TextFormatter mutates shared LogRecord -- ANSI in JSON output. [FACT: `logging.py:128`]. JSONFormatter has no serialization guard. [FACT: `logging.py:82`]. Events list unbounded. [FACT: `logging.py:271`]. Event bus fires ONLY during Anthropic streaming. [ABSENCE: non-streaming, OpenAI, LiteLLM] |
| Add database models | `kosmos/db/__init__.py` | `research_director.py` (session usage) | `get_session()` auto-commits on context exit. [FACT: `db/__init__.py:131-133`]. DB init failure logged as warning only -- director continues without DB, causing cascading failures. [FACT: `research_director.py:131-139`]. `_reset_eval_state()` drops ALL tables. [FACT: `scientific_evaluation.py:56-60`] |
| Add orchestration tasks | `kosmos/orchestration/delegation.py` | `plan_creator.py`, `plan_reviewer.py`, `novelty_detector.py` | DelegationManager raises `RuntimeError` at execution time if agent missing -- no init validation. [FACT: `delegation.py:395-399`]. PlanCreator/PlanReviewer bypass provider layer entirely. [FACT: `plan_creator.py:158-162`]. `filter_redundant_tasks` shallow-copies numpy arrays. [FACT: `novelty_detector.py:320-342`]. Mock review almost always approves. [FACT: `__init__.py:25`] |
## Reading Order

### Core Data Models (read first -- everything else references these)

1. `kosmos/models/hypothesis.py` — Hypothesis data model. Learn the `Hypothesis` Pydantic model, `ExperimentType` enum (lives HERE, not in experiment.py), and `HypothesisGenerationResponse`. Note `ConfigDict(use_enum_values=False)` means `model_dump()` returns enum objects, not strings. `_DEFAULT_CLAUDE_SONNET_MODEL` imported at module scope makes config a hard dependency. [FACT: `hypothesis.py:156`, `experiment.py:14`, `hypothesis.py:13`]

2. `kosmos/models/experiment.py` — ExperimentProtocol, StatisticalTestSpec, ExperimentStep. Depends on hypothesis.py for `ExperimentType`. Hand-written `to_dict()` (100 lines) means new fields silently vanish from serialization. `validate_steps` reorders input silently. [FACT: `experiment.py:471-573`, `experiment.py:438`]

3. `kosmos/models/result.py` — ExperimentResult, ResultExport. `export_markdown()` will TypeError on None optional fields. `export_csv()` lazy-imports pandas. `datetime.utcnow()` deprecated. [FACT: `result.py:349-353`, `result.py:293`, `result.py:203`]

### Core Infrastructure (read second -- agents and execution depend on these)

4. `kosmos/core/workflow.py` — ResearchWorkflow state machine and ResearchPlan. Learn the state transitions, especially that CONVERGED is not terminal (can return to GENERATING_HYPOTHESES). `current_state` synced only via `transition_to()`. `get_untested_hypotheses()` is O(n*m). `use_enum_values=True` breaks `isinstance` on enums. [FACT: `workflow.py:212-213`, `workflow.py:323-325`, `workflow.py:149-151`, `workflow.py:48`]

5. `config.py` — KosmosConfig Pydantic settings. Learn the config surface, env var patterns, and the dual-read inconsistency risk. Singleton goes stale without `reload=True`. ~17 env vars bypass Pydantic. `config.openai` can be None. NEO4J_PASSWORD defaults to `"kosmos-password"`. [FACT: `config.py:1140`, `config.py:896-919`, `config.py:549`]

6. `kosmos/core/providers/base.py` — LLMProvider ABC and LLMResponse. Learn the provider contract. `LLMResponse` with empty content is falsy. `response.strip()` returns `str`, losing metadata. `if False: yield` is load-bearing in `generate_stream_async`. `_update_usage_stats` skips cost at 0.0. `is_recoverable()` pattern matching is order-dependent. [FACT: `base.py:98-99`, `base.py:107-108`, `base.py:360-363`, `base.py:401`, `base.py:466-477`]

7. `kosmos/core/llm.py` — ClaudeClient (legacy) and get_client() factory. Learn the two coexisting client systems. CLI mode detection via all-9 key. Cost hardcodes "claude-sonnet-4-5". `_default_client` is `Union[ClaudeClient, LLMProvider]`. [FACT: `llm.py:179`, `llm.py:519`, `llm.py:609`]

8. `kosmos/core/providers/anthropic.py` — AnthropicProvider, primary LLM backend. Cache hits don't update usage stats. Async calls absent from totals. Stream counts chunks as tokens. Auto-model-selection silently disabled in CLI mode. `generate_structured` modifies system prompt. [FACT: `anthropic.py:228-249`, `anthropic.py:400-430`, `anthropic.py:731-732`, `anthropic.py:187`, `anthropic.py:530`]

9. `kosmos/db/__init__.py` — Database session management. Learn `get_session()` auto-commit on context exit. Understand the session lifecycle pattern. [FACT: `db/__init__.py:131-133`]

### Agent Layer (read third -- uses all of the above)

10. `kosmos/agents/base.py` — BaseAgent ABC, agent lifecycle, message handling. `message_queue` is an unbounded memory leak. `_on_pause()`/`_on_resume()` hooks are dead code. `register_message_handler()` stores handlers but dispatch is dead. `start()` cannot restart from ERROR. [FACT: `base.py:136-138`, `base.py:189-206`, `base.py:406-415`, `base.py:161-163`]

11. `kosmos/agents/research_director.py` — The central orchestrator (~3000 lines). Learn `execute()`, `decide_next_action()`, and the `_handle_*_action()` dispatch pattern. `_actions_this_iteration` lazily initialized via `hasattr`. `time.sleep()` blocks event loop. Hardcoded Anthropic async client bypasses config. DB init failure is warning-only. Message-based methods (lines 1039-1219) are dead code. [FACT: `research_director.py:2451-2453`, `research_director.py:674`, `research_director.py:228-239`, `research_director.py:131-139`, `research_director.py:1039-1219`]

### Execution Pipeline (read fourth -- called by research_director)

12. `kosmos/execution/code_generator.py` — Code generation from experiment protocols. Template matching is order-dependent. LLM client failure silently disables generation. Basic template lacks synthetic data. `random_seed=0` becomes 42. Own multi-provider fallback chain. [FACT: `code_generator.py:787-793`, `code_generator.py:762-778`, `code_generator.py:954-977`, `code_generator.py:89`]

13. `kosmos/execution/executor.py` — Code execution with sandbox/non-sandbox paths. Docker fallback is silent. `time.sleep()` in retry loop blocks event loop. Windows timeout doesn't kill threads. Restricted builtins allow sandbox bypass via `type`. If code doesn't assign to `results`, return_value is None. [FACT: `executor.py:216-220`, `executor.py:335`, `executor.py:621-630`, `executor.py:594-597`, `executor.py:516`]

14. `kosmos/safety/code_validator.py` — Code validation before execution. Pattern matching in string literals produces false positives. `getattr()` flagged CRITICAL. Write-mode detection incomplete. Approval truncates to 500 chars. [FACT: `code_validator.py:288`, `code_validator.py:338`, `code_validator.py:296-297`, `code_validator.py:510`]

15. `kosmos/execution/sandbox.py` — Docker sandbox isolation. Return values extracted via stdout "RESULT:" prefix -- mismatch with code that stores in local `results` variable. [FACT: `sandbox.py:442` vs `code_generator.py:187`]

### Hypothesis and Literature (read fifth -- the research content pipeline)

16. `kosmos/agents/hypothesis_generator.py` — Hypothesis generation with novelty filtering. NoveltyChecker import is guarded (fail-open). Vague language check warns but doesn't reject. Only top 5 papers used in prompt despite fetching up to 10. Novelty threshold inverted from NoveltyChecker default. `execute()` signature incompatible with base class. [FACT: `hypothesis_generator.py:227-228`, `hypothesis_generator.py:451-455`, `hypothesis_generator.py:346`, `hypothesis_generator.py:211`, `hypothesis_generator.py:91`]

17. `kosmos/literature/base_client.py` — Literature search client ABC. `_validate_query` lies about truncation. `_normalize_paper_metadata` missing `@abstractmethod`. `_handle_api_error` swallows exceptions. `PaperMetadata` has no validation. [FACT: `base_client.py:248-250`, `base_client.py:255`, `base_client.py:229-233`, `base_client.py:78`]

18. `kosmos/literature/unified_search.py` — Multi-source literature search. Timeout collects partial results (slow source doesn't discard fast results). [FACT: `unified_search.py:172-183`]

19. `kosmos/literature/literature_analyzer.py` — Singleton literature analysis agent. Neo4j failure silent. Citation graph caps at 50+50. File cache TTL 24 hours. [FACT: `literature_analyzer.py:114-116`, `literature_analyzer.py:821`, `literature_analyzer.py:1019`]

### Convergence and Orchestration (read sixth -- controls research loop termination)

20. `kosmos/core/convergence.py` — Convergence detection. `novelty_trend` unbounded. `USER_REQUESTED` reused as "no reason" sentinel. Flat novelty triggers stop. Deferred indefinitely without experiments. [FACT: `convergence.py:562`, `convergence.py:271`, `convergence.py:424`, `convergence.py:339`]

21. `kosmos/orchestration/delegation.py` — Task delegation to agents. RuntimeError at execution time if agent missing. [FACT: `delegation.py:395-399`]

22. `kosmos/orchestration/plan_creator.py` — Plan creation via direct Anthropic calls (bypasses provider layer). Falls back to mock results on ANY exception. [FACT: `plan_creator.py:158-162`, `plan_creator.py:194-198`]

23. `kosmos/orchestration/plan_reviewer.py` — Plan review. DIMENSION_WEIGHTS defined but unused. Falls back to mock on failure. [FACT: `plan_reviewer.py:68-69`, `plan_reviewer.py:161-162`]

### Knowledge Layer (read seventh -- persistence and graph storage)

24. `kosmos/knowledge/graph.py` — Neo4j KnowledgeGraph. Non-idempotent counters. Connection failure silently swallowed. Auto-starts Docker (60+ seconds). Cypher injection via f-strings. Hardcoded health check credentials. Singleton not thread-safe. reset leaks connections. 9 unached queries in get_stats(). [FACT: `graph.py:615-616`, `graph.py:96-99`, `graph.py:118-171`, `graph.py:761`, `graph.py:155-156`, `graph.py:999-1038`, `graph.py:1034-1038`, `graph.py:981`]

25. `kosmos/knowledge/vector_db.py` — ChromaDB vector database. `clear()` crashes without null guard. Singleton not thread-safe. Init triggers ~440MB download. [FACT: `vector_db.py:370-371`, `vector_db.py:443-477`, `vector_db.py:103`]

26. `kosmos/world_model/factory.py` — World model singleton factory. Explicitly NOT thread-safe. Falls back to InMemoryWorldModel silently (all data lost on restart). [FACT: `factory.py:38`, `factory.py:123-133`]

### CLI Entry Point (read eighth -- ties everything together)

27. `cli/commands/run.py` — CLI entry point for `kosmos run`. Constructs flat_config dict bridge manually. Directly mutates config singleton. Learn the initialization sequence. [FACT: `run.py:147-170`, `run.py:136-137`]

### Evaluation Infrastructure (read last or skip -- tooling, not core system)

28. `scientific_evaluation.py` — 7-phase evaluation pipeline. Drops all DB tables per phase. No aggregate pass/fail. Phase 4 requires --data-path. Phase 5/6 use keyword/source-string heuristics. 120s per-action timeout with no aggregate. [FACT: `scientific_evaluation.py:56-60`, `scientific_evaluation.py:1342-1451`, `scientific_evaluation.py:580-585`, `scientific_evaluation.py:741-747`, `scientific_evaluation.py:831-833`]

29. `kosmos/core/logging.py` — Logging setup. Handler wipe on re-init. TextFormatter mutates shared LogRecord. JSONFormatter no serialization guard. Events unbounded. [FACT: `logging.py:179`, `logging.py:128`, `logging.py:82`, `logging.py:271`]

30. `kosmos/orchestration/novelty_detector.py` — Task novelty detection. First-use triggers ~90MB model download. Shallow-copies numpy arrays. [FACT: `novelty_detector.py:72-85`, `novelty_detector.py:320-342`]

**Skip:** `kosmos/agents/registry.py` (dead code -- message bus infrastructure dormant since Issue #76, all agents use direct calls) [FACT: `registry.py:6-8`]

**Skip:** `core/memory.py`, `core/feedback.py` (Phase 7 infrastructure, not integrated into any agent) [FACT: `core/memory.py:66-104`, `core/feedback.py:76-105`]

**Skip:** `config.py:752-822` (LocalModelConfig -- dead configuration, not wired into any provider) [ABSENCE: `config.py:752-822`]

**Skip:** `research_director.py:1039-1219` (dead message-based `_send_to_*` methods, replaced by direct `_handle_*_action()` calls per Issue #76) [FACT: `research_director.py:1039-1219`]

**Skip:** `run_phase2_tests.py` (hardcodes `/mnt/c/python/Kosmos` -- machine-specific, will fail elsewhere) [FACT: `run_phase2_tests.py:16`]

**Skip:** `compare_runs.py` (self-contained file utility with zero Kosmos imports -- reads markdown, writes JSON, teaches nothing about the system) [FACT: `compare_runs.py`]

**Skip:** `experiment_designer.py:714-717` (`_enhance_protocol_with_llm()` is a no-op -- calls LLM, never applies response) [FACT: `experiment_designer.py:714-717`]

**Skip:** `openai.py:575-613` (duplicate pricing table -- read `pricing.py` instead) [FACT: `openai.py:575-613`]
## Gaps

- Testing conventions not deeply investigated — T5.3 produced limited findings on fixture patterns and mocking strategies
- Neo4j world model subsystem (T6.3) investigated but integration testing patterns unclear
- REST/HTTP API layer (20 API handlers per xray) not traced as a separate entry point — covered indirectly through agent communication patterns
- 249 test modules identified by xray but test coverage metrics not measured
- LiteLLM provider integration mentioned in configuration but not traced end-to-end (Anthropic and OpenAI were the primary traced providers)
- Deployment and infrastructure patterns not in scope (no Dockerfile/docker-compose investigation)

---

*Generated by deep_crawl agent. 32 tasks,
19 modules read, 5 traces verified.
Coverage: ~{DOC_TOKENS} tokens documenting ~2,455,608 token codebase. 391 findings from 32 investigation tasks.
Evidence: 318 [FACT], 53 [PATTERN], 20 [ABSENCE].*
