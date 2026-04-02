# Trace: `kosmos run` CLI Path

## Entry Point

```
kosmos (pip script)
  → kosmos.cli.main:cli_entrypoint (main.py:422)
```

[FACT] pyproject.toml:179 defines `kosmos = "kosmos.cli.main:cli_entrypoint"` as the console script entry point.

---

## Full Call Trace

### Phase 0: CLI Bootstrap

```
cli_entrypoint() (main.py:422)
  → app() — Typer app dispatches to registered commands
  → main() callback (main.py:98) — processes global flags (--verbose, --debug, --trace, --debug-level, --quiet)
    → setup_logging() (main.py:49) — configures file+console handlers
    → init_from_config() (db/__init__.py:140) — initializes DB from config
      → first_time_setup() — creates .env, runs alembic migrations
      → init_database() — creates SQLAlchemy engine + session factory
      [SIDE EFFECT: DB file/connection created] (db/__init__.py:178)
  → run_research() (commands/run.py:51) — registered as "run" command (main.py:404)
```

[FACT] `register_commands()` at main.py:397 imports `run` module and registers `run.run_research` as the `run` command (main.py:404).
[FACT] Database initialization happens in the `main()` callback (main.py:144), meaning it runs for every command, not just `run`.

**Branching**: If `--interactive` flag or no question provided, routes to `run_interactive_mode()` (run.py:87-99). Otherwise proceeds with direct CLI args.

**Data transformation**: CLI args → flat_config dict (run.py:148-170). Nested `KosmosConfig` is flattened to a dict with plain keys that agents expect.

### Phase 1: Director Construction

```
run_research() (run.py:51)
  → ResearchDirectorAgent.__init__() (research_director.py:68)
    → BaseAgent.__init__() — assigns agent_id, status=CREATED
    → _validate_domain() (research_director.py:262) — warns if domain not in enabled list
    → _load_skills() (research_director.py:279) — loads domain-specific prompt skills via SkillLoader
    → ResearchPlan() (workflow.py:57) — in-memory tracking: hypothesis_pool, experiment_queue, results, iteration_count
    → ResearchWorkflow() (workflow.py:166) — state machine, initial state=INITIALIZING
    → get_client() → ClaudeClient.__init__() (core/llm.py:108) — Anthropic API client
      [SIDE EFFECT: Anthropic HTTP client created] (llm.py:183)
    → init_from_config() (research_director.py:132) — ensures DB initialized (idempotent)
    → ConvergenceDetector() (research_director.py:168) — stopping criteria evaluator
    → [optional] ParallelExperimentExecutor() if concurrent enabled (research_director.py:210)
    → [optional] AsyncClaudeClient() if concurrent enabled (research_director.py:226)
    → get_world_model() (research_director.py:243) — Neo4j-backed or in-memory knowledge graph
      → Entity.from_research_question() — creates ResearchQuestion entity
      → wm.add_entity() — persists to knowledge graph
      [SIDE EFFECT: Knowledge graph entity created] (research_director.py:250)
  → get_registry().register(director) (run.py:181) — registers agent in global AgentRegistry
```

[FACT] The flat_config dict is passed as `config` to ResearchDirectorAgent (run.py:173-177). The director reads individual keys from it (e.g., `self.config.get("max_iterations", 10)` at research_director.py:104).
[FACT] World model initialization is wrapped in try/except and failure is non-fatal (research_director.py:252-254). If Neo4j is unavailable, `self.wm = None`.

### Phase 2: Research Start (First execute() Call)

```
asyncio.run(run_with_progress_async(director, ...)) (run.py:186)
  → await director.execute({"action": "start_research"}) (run.py:296)
    → execute() (research_director.py:2868)
      → generate_research_plan() (research_director.py:2349)
        → self.llm_client.generate(prompt) (research_director.py:2372)
          [SIDE EFFECT: Anthropic API call — LLM generates research plan text] (llm.py:207+)
        → self.research_plan.initial_strategy = response (research_director.py:2375)
      → self.start() (research_director.py:2885)
        → BaseAgent.start() (base.py:159) — status → STARTING → RUNNING
        → _on_start() (research_director.py:319)
          → workflow.transition_to(GENERATING_HYPOTHESES) (research_director.py:329)
      → decide_next_action() (research_director.py:2388)
        — returns NextAction.GENERATE_HYPOTHESIS (first call, no hypotheses yet)
      → _execute_next_action(GENERATE_HYPOTHESIS) (research_director.py:2550)
        → _do_execute_action(GENERATE_HYPOTHESIS) (research_director.py:2573)
          → _handle_generate_hypothesis_action() (research_director.py:1391)
```

[FACT] Budget enforcement is checked in `decide_next_action()` (research_director.py:2404-2422). If budget exceeded, transitions directly to CONVERGED.
[FACT] Runtime limit is checked in `decide_next_action()` (research_director.py:2428-2446). Max runtime defaults to 12 hours (research_director.py:105).
[FACT] Loop guard prevents infinite loops: MAX_ACTIONS_PER_ITERATION=50 (research_director.py:50, checked at research_director.py:2455).

### Phase 3: Hypothesis Generation

```
_handle_generate_hypothesis_action() (research_director.py:1391)
  → HypothesisGeneratorAgent.__init__() — lazy init (research_director.py:1403-1404)
  → agent.generate_hypotheses(question, num=3, domain, store_in_db=True) (research_director.py:1408)
    → _detect_domain() (hypothesis_generator.py:259) — auto-detect if not provided
    → _gather_literature_context() — UnifiedLiteratureSearch for context papers
      [SIDE EFFECT: External API calls to literature search services] (hypothesis_generator.py:183)
    → _generate_with_claude() (hypothesis_generator.py:187)
      → llm_client.generate(prompt) — LLM generates hypotheses
      [SIDE EFFECT: Anthropic API call] (hypothesis_generator.py:187)
    → _validate_hypothesis() for each (hypothesis_generator.py:198)
    → NoveltyChecker.check_novelty() (hypothesis_generator.py:213) — annotates novelty_score
    → _store_hypothesis() for each (hypothesis_generator.py:233)
      → session.add(DBHypothesis), session.commit() (hypothesis_generator.py:491-492)
      [SIDE EFFECT: DB writes — hypothesis rows committed] (hypothesis_generator.py:492)
  → research_plan.add_hypothesis(hyp_id) for each (research_director.py:1428-1429)
  → _persist_hypothesis_to_graph(hyp_id) for each (research_director.py:1432-1433)
    → wm.add_entity(Entity.from_hypothesis()) (research_director.py:409)
    → wm.add_relationship(SPAWNED_BY) (research_director.py:412-419)
    [SIDE EFFECT: Knowledge graph writes] (research_director.py:409-419)
  → workflow.transition_to(DESIGNING_EXPERIMENTS) (research_director.py:1444)
```

**Data transformation**: LLM text response → parsed Hypothesis Pydantic models → DBHypothesis ORM objects → hypothesis IDs stored in ResearchPlan.hypothesis_pool.

### Phase 4: Research Loop (CLI Driving Loop)

```
run_with_progress_async() loop (run.py:308-386)
  while iteration < max_iterations:
    → director.get_research_status() (research_director.py:2926) — snapshot for progress bars
    → check timeout (2hr max_loop_duration) (run.py:313-319)
    → check convergence (run.py:362-365)
    → await director.execute({"action": "step"}) (run.py:369)
      → execute() (research_director.py:2897)
        → decide_next_action() — state-machine-based routing
        → _execute_next_action(next_action)
    → await asyncio.sleep(0.05) (run.py:389) — UI update yield
```

[FACT] The CLI loop at run.py:308 has its own 2-hour timeout (`max_loop_duration = 7200`, run.py:301), separate from the director's 12-hour max_runtime_hours (research_director.py:105). The CLI timeout is the binding constraint.
[FACT] Iteration counter is driven by `status.get("iteration", iteration)` (run.py:374), which reads from the director's research_plan.iteration_count.

**Branching in `decide_next_action()` (research_director.py:2388)**:
- `GENERATING_HYPOTHESES` state → GENERATE_HYPOTHESIS
- `DESIGNING_EXPERIMENTS` state → DESIGN_EXPERIMENT (if untested hypotheses) or EXECUTE_EXPERIMENT (if queue non-empty) or ANALYZE_RESULT (if results exist) or CONVERGE
- `EXECUTING` state → EXECUTE_EXPERIMENT (if queue) or ANALYZE_RESULT (if results) or REFINE_HYPOTHESIS (fallback)
- `ANALYZING` state → ANALYZE_RESULT (if results) or EXECUTE_EXPERIMENT or REFINE_HYPOTHESIS
- `REFINING` state → REFINE_HYPOTHESIS (if tested) or GENERATE_HYPOTHESIS
- `CONVERGED` → CONVERGE
- `ERROR` → ERROR_RECOVERY

### Phase 5: Experiment Design

```
_handle_design_experiment_action(hypothesis_id) (research_director.py:1458)
  → ExperimentDesignerAgent.__init__() — lazy init (research_director.py:1469-1470)
  → agent.design_experiment(hypothesis_id, store_in_db=True) (research_director.py:1474)
    → _load_hypothesis(id) — loads from DB (experiment_designer.py:196)
    → _select_experiment_type() (experiment_designer.py:201)
    → _generate_from_template() or _generate_with_claude() (experiment_designer.py:206-218)
      [SIDE EFFECT: Anthropic API call if LLM generation] (experiment_designer.py:213)
    → _enhance_protocol_with_llm() if templates + LLM enabled (experiment_designer.py:222)
    → PowerAnalyzer — calculates required sample size (experiment_designer.py:226-260)
    → _validate_protocol() (experiment_designer.py:263)
    → _store_protocol() (experiment_designer.py:272)
      → session.add(DBExperiment), session.commit() (experiment_designer.py:902-903)
      [SIDE EFFECT: DB write — experiment row committed] (experiment_designer.py:903)
  → research_plan.add_experiment(protocol_id) (research_director.py:1492)
  → _persist_protocol_to_graph(protocol_id, hypothesis_id) (research_director.py:1496)
    → wm.add_entity(Entity.from_protocol()) (research_director.py:459)
    → wm.add_relationship(TESTS) (research_director.py:463-470)
    [SIDE EFFECT: Knowledge graph writes] (research_director.py:459-470)
  → workflow.transition_to(EXECUTING) (research_director.py:1507)
```

**Branching**: If concurrent mode enabled and multiple untested hypotheses, runs `evaluate_hypotheses_concurrently()` (research_director.py:2585-2616) using AsyncClaudeClient.

### Phase 6: Experiment Execution

```
_handle_execute_experiment_action(protocol_id) (research_director.py:1521)
  → ExperimentCodeGenerator.__init__(use_templates=True, use_llm=True) — lazy init (research_director.py:1538)
  → CodeExecutor.__init__(max_retries=3) — lazy init (research_director.py:1540)
  → DataProvider.__init__(default_data_dir=data_path) — lazy init (research_director.py:1542)
  → get_experiment(session, protocol_id) — loads protocol from DB (research_director.py:1552)
  → ExperimentProtocol.model_validate(protocol_data) — deserialize stored JSON (research_director.py:1559)
  → code_generator.generate(protocol) (research_director.py:1564)
    — template-based or LLM-based Python code generation
    [SIDE EFFECT: Anthropic API call if LLM generation] (code_generator.py:797+)
  → BRANCH: if data_path:
      code_executor.execute_with_data(code, data_path, retry_on_error=True) (research_director.py:1568)
    else:
      code_executor.execute(code, retry_on_error=True) (research_director.py:1572)
    → BRANCH: if sandbox available:
        _execute_in_sandbox() → DockerSandbox.execute() (executor.py:474-475)
        [SIDE EFFECT: Docker container created, code executed in sandbox] (executor.py:576)
      else:
        _execute_once() (executor.py:466)
          → _prepare_globals() — restricted builtins (executor.py:589-598)
          → _exec_with_timeout() — exec(code, ...) with SIGALRM/thread timeout (executor.py:600-630)
          [SIDE EFFECT: arbitrary Python code executed via exec()] (executor.py:617)
  → _json_safe(return_value) — sanitize numpy/sklearn objects for DB (research_director.py:1595-1613)
  → create_result(session, ...) (research_director.py:1622-1630)
    → session.add(Result), session.commit() (db/operations.py:366-367)
    [SIDE EFFECT: DB write — result row committed] (db/operations.py:367)
  → research_plan.add_result(result_id) (research_director.py:1641)
  → research_plan.mark_experiment_complete(protocol_id) (research_director.py:1642)
  → _persist_result_to_graph(result_id, protocol_id, hypothesis_id) (research_director.py:1646)
    → wm.add_entity(Entity.from_result()) (research_director.py:499)
    → wm.add_relationship(PRODUCED_BY) (research_director.py:503-510)
    → wm.add_relationship(TESTS) (research_director.py:513-518)
    [SIDE EFFECT: Knowledge graph writes] (research_director.py:499-518)
  → workflow.transition_to(ANALYZING) (research_director.py:1652)
```

[FACT] Code execution timeout defaults to 300 seconds (executor.py:184, constant DEFAULT_EXECUTION_TIMEOUT).
[FACT] Retry strategy up to 3 attempts with exponential backoff (executor.py:277-376). On error, `RetryStrategy.modify_code_for_retry()` can auto-fix 10+ error types (executor.py:667+).
[FACT] Restricted builtins are enforced (executor.py:589-598): SAFE_BUILTINS + restricted __import__ that blocks os.system, subprocess, etc.

**CRITICAL GOTCHA**: When sandbox is unavailable, code runs via `exec()` in the host process (executor.py:617). The restricted builtins mitigate but do not fully sandbox. [FACT: executor.py:217-221, fallback message logged as warning].

### Phase 7: Result Analysis

```
_handle_analyze_result_action(result_id) (research_director.py:1666)
  → DataAnalystAgent.__init__() — lazy init (research_director.py:1681)
  → get_result(session, result_id, with_experiment=True) — loads from DB (research_director.py:1691)
  → Builds ExperimentResult Pydantic model from DB fields (research_director.py:1704-1722)
  → Loads associated Hypothesis from DB if available (research_director.py:1725-1734)
  → data_analyst.interpret_results(result, hypothesis) (research_director.py:1737)
    → _extract_result_summary() (data_analyst.py:381)
    → _build_interpretation_prompt() (data_analyst.py:349)
    → llm_client.generate(prompt, system=..., temperature=0.3) (data_analyst.py:355)
      [SIDE EFFECT: Anthropic API call — LLM interprets results] (data_analyst.py:355)
    → _parse_interpretation_response() (data_analyst.py:366)
    → interpretation_history.append() (data_analyst.py:371)
  → research_plan.mark_supported/mark_rejected/mark_tested(hypothesis_id) (research_director.py:1762-1767)
  → _add_support_relationship(result_id, hypothesis_id, supports, confidence) (research_director.py:1771)
    → wm.add_relationship(SUPPORTS/REFUTES) (research_director.py:549-557)
    [SIDE EFFECT: Knowledge graph write — SUPPORTS or REFUTES edge] (research_director.py:557)
  → workflow.transition_to(REFINING) (research_director.py:1782)
```

**Data transformation**: DB Result row → ExperimentResult Pydantic model (manual reconstruction at research_director.py:1704-1722, NOT from a generic to_pydantic() method). This is fragile — fields must be manually kept in sync.

### Phase 8: Hypothesis Refinement

```
_handle_refine_hypothesis_action(hypothesis_id) (research_director.py:1796)
  → HypothesisRefiner.__init__() — lazy init (research_director.py:1817)
  → get_hypothesis(session, hypothesis_id, with_experiments=True) — loads from DB (research_director.py:1826)
  → Builds Hypothesis Pydantic model from DB fields (research_director.py:1831-1840)
  → Loads all results for hypothesis's experiments (research_director.py:1843-1872)
  → refiner.evaluate_hypothesis_status(hypothesis, latest_result, results_history) (research_director.py:1886)
    — Returns RetirementDecision enum: RETIRE, REFINE, SPAWN_VARIANT, or CONTINUE_TESTING
  → BRANCH on decision:
      RETIRE: refiner.retire_hypothesis() (research_director.py:1894)
      REFINE: refiner.refine_hypothesis() → stores refined hypothesis in DB (research_director.py:1901-1918)
        → db_create_hypothesis(session, ...) (research_director.py:1906)
        [SIDE EFFECT: DB write — new refined hypothesis row] (research_director.py:1906-1907)
      SPAWN_VARIANT: refiner.spawn_variant(num_variants=2) → stores variant hypotheses (research_director.py:1922-1941)
        → db_create_hypothesis() for each variant
        [SIDE EFFECT: DB writes — 1-2 new variant hypothesis rows] (research_director.py:1929-1930)
      CONTINUE_TESTING: no action (research_director.py:1944)
  → research_plan.add_hypothesis(hyp_id) for each refined/spawned (research_director.py:1954)
  → _persist_hypothesis_to_graph() for each (research_director.py:1958)
    [SIDE EFFECT: Knowledge graph writes]
  → research_plan.increment_iteration() (research_director.py:2704)
  → _actions_this_iteration = 0 (research_director.py:2706) — reset for next iteration
```

[FACT] Iteration increment happens ONLY after refinement phase completes (research_director.py:2700-2707), not after every action. One "iteration" = one full generate → design → execute → analyze → refine cycle.

### Phase 9: Convergence Check

```
_handle_convergence_action() (research_director.py:1334)
  → _apply_multiple_comparison_correction() (research_director.py:1343) — Bonferroni/BH correction
  → _check_convergence_direct() (research_director.py:1347)
    → ConvergenceDetector.evaluate() — checks mandatory + optional stopping criteria
  → BRANCH:
      decision.should_stop = True:
        research_plan.has_converged = True (research_director.py:1357)
        wm.add_annotation() — convergence annotation to knowledge graph (research_director.py:1364-1368)
        [SIDE EFFECT: Knowledge graph annotation]
        workflow.transition_to(CONVERGED) (research_director.py:1375)
        self.stop() (research_director.py:1381) — stops the agent
      decision.should_stop = False:
        research_plan.increment_iteration() (research_director.py:1387)
        _actions_this_iteration = 0 (research_director.py:1388) — continue to next iteration
```

### Phase 10: Results Collection and Output

```
run_with_progress_async() — after loop exits (run.py:400-464)
  → director.get_research_status() — final status snapshot (run.py:400)
  → get_session() — fetch hypothesis and experiment objects from DB (run.py:417-435)
    → get_hypothesis(session, h_id) for each in hypothesis_pool
    → get_experiment(session, e_id) for each in completed_experiments
  → Builds results dict with metrics (run.py:437-458)

run_research() — after async returns (run.py:195-212)
  → ResultsViewer.display_research_overview(results) (run.py:196) — Rich console output
  → ResultsViewer.display_hypotheses_table(results) (run.py:197) — Rich table
  → ResultsViewer.display_experiments_table(results) (run.py:198) — Rich table
  → ResultsViewer.display_metrics_summary(results) (run.py:200) — Rich metrics
  → BRANCH on --output flag (run.py:204-210):
      .json: viewer.export_to_json(results, output) (results_viewer.py:312)
        [SIDE EFFECT: JSON file write] (results_viewer.py:321)
      .md: viewer.export_to_markdown(results, output) (results_viewer.py:328)
        [SIDE EFFECT: Markdown file write] (results_viewer.py:336+)
```

---

## Complete Side Effect Inventory

| Side Effect | Location | Condition |
|---|---|---|
| **DB: SQLite/Postgres file/connection created** | db/__init__.py:178 | Always (on CLI startup) |
| **API: Anthropic LLM calls** | core/llm.py:207+ | Every generate_research_plan, generate_hypotheses, design_experiment, code_generate (LLM mode), interpret_results |
| **API: Literature search calls** | hypothesis_generator.py:183 | If use_literature_context=True (default) |
| **DB: Hypothesis rows committed** | hypothesis_generator.py:492, db/operations.py:113 | Each hypothesis generation + refinement + variant spawning |
| **DB: Experiment rows committed** | experiment_designer.py:903 | Each experiment design |
| **DB: Result rows committed** | db/operations.py:367 | Each experiment execution |
| **Code execution: exec() or Docker sandbox** | executor.py:617 or executor.py:576 | Each experiment execution |
| **Knowledge graph: Entity + Relationship writes** | research_director.py:409-419, 459-470, 499-518, 549-557 | Each hypothesis, protocol, result, support/refute edge (if wm initialized) |
| **Knowledge graph: Convergence annotation** | research_director.py:1364-1368 | On convergence (if wm initialized) |
| **File: JSON/Markdown export** | results_viewer.py:321 / 336+ | If --output flag provided |
| **Console: Rich progress display** | run.py:293 | Always |
| **File: Log file** | main.py:61 (log_dir / "kosmos.log") | Always |

---

## Gotchas

1. **[FACT] Two independent timeout mechanisms**: The CLI loop enforces a 2-hour max (run.py:301, `max_loop_duration = 7200`), while the director enforces a 12-hour max (research_director.py:105, `max_runtime_hours`). The CLI timeout binds first and will kill the loop without the director knowing.

2. **[FACT] exec() fallback when Docker unavailable**: If Docker sandbox is not available, experiment code runs via `exec()` in the host Python process with only restricted builtins as protection (executor.py:217-221). The warning is logged but execution proceeds.

3. **[FACT] Manual Pydantic model reconstruction**: In `_handle_analyze_result_action` (research_director.py:1704-1722) and `_handle_refine_hypothesis_action` (research_director.py:1831-1872), DB ORM objects are manually converted to Pydantic models field-by-field rather than using a generic conversion. Fields must be kept in sync manually.

4. **[FACT] Lazy agent initialization**: All sub-agents (HypothesisGeneratorAgent, ExperimentDesignerAgent, DataAnalystAgent, CodeExecutor, CodeGenerator, HypothesisRefiner) are lazily initialized on first use (e.g., research_director.py:1403-1404). They persist across iterations (no re-init per iteration), meaning internal state accumulates (e.g., DataAnalystAgent.interpretation_history).

5. **[FACT] Deprecated message routing still present**: The `process_message()` method (research_director.py:568) and `_send_to_convergence_detector()` (research_director.py:1981, marked DEPRECATED) still exist. All actual agent communication uses direct calls (Issue #76 fix), bypassing the message router entirely.

6. **[FACT] Config flattening lossy**: The flat_config dict at run.py:148-170 cherry-picks specific config fields. Any config key not explicitly listed is invisible to the director and its sub-agents.

7. **[FACT] Iteration counter sync gap**: The CLI reads iteration from `status.get("iteration", iteration)` at run.py:374, but the director only increments after the REFINE phase completes (research_director.py:2704). If the loop breaks mid-cycle, the CLI iteration and director iteration may disagree.

8. **[FACT] World model failure is silent**: If `get_world_model()` fails during director init (research_director.py:252-254), `self.wm = None` and all subsequent graph persistence calls silently return without error (guarded by `if not self.wm: return` checks throughout).

9. **[FACT] _json_safe sanitizes by stringifying unknowns**: The sanitization helper at research_director.py:1595-1613 converts any unrecognized object to `str(obj)`. This means complex objects (sklearn models, custom classes) become opaque strings in the DB rather than raising errors.

10. **[FACT] Concurrent mode requires explicit config + API key**: ParallelExperimentExecutor (research_director.py:209) and AsyncClaudeClient (research_director.py:226) only initialize if `enable_concurrent_operations=True` in config AND `ANTHROPIC_API_KEY` is set in the environment (research_director.py:229).
# Trace T02: CLI `kosmos config` Command and Configuration Loading Chain

## Trace Summary

Full request trace from the `kosmos` CLI entry point through `kosmos config` to configuration loading, provider selection, and environment variable resolution.

---

## 1. CLI Entry Point

**Entry**: `pyproject.toml:179` defines the console script:
```
kosmos = "kosmos.cli.main:cli_entrypoint"
```

**[FACT]** `cli_entrypoint()` at `kosmos/cli/main.py:422-436` wraps `app()` (the Typer app) with KeyboardInterrupt and general exception handling.

**[FACT]** `load_dotenv()` is called at module-import time (`kosmos/cli/main.py:22`), meaning `.env` file values are loaded into `os.environ` **before** any Typer command runs. This is the earliest config-relevant side effect in the entire CLI.

---

## 2. Global Callback (Runs Before Every Command)

**[FACT]** `main()` at `kosmos/cli/main.py:98-169` is registered as `@app.callback()`. It runs before **every** subcommand including `config`. It performs:

1. **Stores global options** in `ctx.obj` (verbose, debug, trace, debug_level, debug_modules, quiet) -- lines 123-129.
2. **Calls `setup_logging()`** (line 132) -- which, if `--trace` is set, calls `get_config()` to mutate logging flags (lines 76-83). This is a **side-channel config load** that occurs before any command body runs.
3. **Sets debug_modules** in config if `--debug-modules` provided (lines 135-140) -- another early `get_config()` call.
4. **Initializes database** via `kosmos.db.init_from_config()` (line 145) -- which internally calls `get_config()` a third time. Database init happens **on every CLI invocation**, not just commands that need it.

**[GOTCHA]** The database is initialized in the global callback, meaning even `kosmos config --show` triggers DB init. If the DB is misconfigured, the user sees a DB error before they can even view their config. The code does not `sys.exit()` on DB failure (line 164 comment: "Don't exit here"), so the command proceeds, but the error message is confusing for config-only operations.

---

## 3. Config Command Registration

**[FACT]** `register_commands()` at `kosmos/cli/main.py:397-415` imports `kosmos.cli.commands.config` and registers it:
```python
app.command(name="config")(config_cmd.manage_config)
```
This is called at module import time (line 419).

---

## 4. Config Command: `manage_config()`

**File**: `kosmos/cli/commands/config.py:25-80`

Five mutually non-exclusive options, all `bool = False`:
- `--show / -s` -- display current config (DEFAULT if no flags given, line 51)
- `--edit / -e` -- open `.env` in `$EDITOR`
- `--validate / -v` -- validate config
- `--reset` -- copy `.env.example` over `.env`
- `--path / -p` -- show config file locations

**[FACT]** If no flags are passed, `show` defaults to `True` (line 51). Multiple flags can be combined; they execute in order: path -> show -> validate -> edit -> reset.

### 4a. `display_config()` (lines 117-196)

Calls `get_config()` (line 126). Displays provider-specific tables:
- If `config.claude` is truthy: shows Claude model, CLI/API mode, max_tokens, temperature, cache.
- Elif `config.openai` is truthy: shows OpenAI model, max_tokens, temperature.
- **[ABSENCE]** LiteLLM config is NOT displayed by `display_config()` even though it's a supported provider. If `LLM_PROVIDER=litellm`, neither the `claude` nor `openai` blocks execute, and no LLM provider info is shown.
- Always shows: research config, database config.

### 4b. `validate_config()` (lines 199-291)

Checks:
- API key presence based on `os.getenv("LLM_PROVIDER", "anthropic")` (line 215).
- Model name against known defaults (but only for Claude; OpenAI always passes).
- Domains against hardcoded valid set: `{"biology", "neuroscience", "materials", "physics", "chemistry", "general"}`.
- Database file existence for SQLite.

**[GOTCHA]** Validation checks `os.getenv("LLM_PROVIDER")` separately from `config.llm_provider`. These could theoretically diverge if the config singleton was mutated after initialization. In practice they agree, but the dual-source pattern is fragile.

### 4c. `edit_config()` (lines 294-319)

Opens `.env` file in `$EDITOR` (defaults to `nano`). If no `.env` exists, creates one from `.env.example` or writes a minimal stub.

### 4d. `reset_config()` (lines 322-341)

Copies `.env.example` to `.env` with confirmation prompt. Does NOT call `reset_config()` from `kosmos.config` to invalidate the singleton.

**[GOTCHA]** After `kosmos config --reset`, the in-memory config singleton retains the OLD values until process restart. This only matters if `--reset` is combined with other flags like `--show` in the same invocation (they'd show stale data).

---

## 5. `get_config()` -- The Configuration Singleton

**File**: `kosmos/config.py:1140-1154`

```python
_config: Optional[KosmosConfig] = None

def get_config(reload: bool = False) -> KosmosConfig:
    global _config
    if _config is None or reload:
        _config = KosmosConfig()
        _config.create_directories()
    return _config
```

**[FACT]** Classic module-level singleton. First call constructs `KosmosConfig()` (a `pydantic_settings.BaseSettings` subclass), which triggers automatic env var resolution. Subsequent calls return the cached instance. `reload=True` forces reconstruction.

**[FACT]** `create_directories()` (line 1067-1076) is called on every fresh construction -- creates log directory and ChromaDB directory.

---

## 6. `KosmosConfig` -- Master Configuration Class

**File**: `kosmos/config.py:922-983`

### 6a. Environment Variable Loading

`KosmosConfig` uses `pydantic_settings.BaseSettings` with:
```python
model_config = SettingsConfigDict(
    env_file=str(Path(__file__).parent.parent / ".env"),  # <project_root>/.env
    env_file_encoding="utf-8",
    case_sensitive=False,
    extra="ignore"
)
```

**[FACT]** The `.env` file path is resolved relative to `kosmos/config.py`'s parent.parent, i.e., the project root (`/mnt/c/python/kosmos/.env`). This is line 979.

**Config precedence** (pydantic-settings default, highest wins first):
1. **Runtime environment variables** (`os.environ`)
2. **`.env` file** values (loaded by `pydantic-settings`, AND separately by `dotenv.load_dotenv()` in main.py:22)
3. **Field defaults** in the Pydantic model

**[GOTCHA]** There is a **double .env load**: `load_dotenv()` in `main.py:22` loads `.env` into `os.environ` at import time, and then `pydantic_settings` also reads the `.env` file when constructing `KosmosConfig`. In normal operation these agree, but if the `.env` file changes between import and first `get_config()` call, the behavior could be surprising.

### 6b. Provider Selection Field

```python
llm_provider: Literal["anthropic", "openai", "litellm"] = Field(
    default="anthropic",
    alias="LLM_PROVIDER"
)
```
**[FACT]** Line 953. Default is `"anthropic"`. Env var `LLM_PROVIDER` controls which provider is active. Only three values are valid.

### 6c. Component Configuration Sub-models

All sub-configs are constructed via `default_factory`:

| Field | Type | Factory | Notes |
|-------|------|---------|-------|
| `claude` | `Optional[ClaudeConfig]` | `_optional_claude_config()` | Only created if `ANTHROPIC_API_KEY` is set (line 914-919) |
| `anthropic` | `Optional[AnthropicConfig]` | `_optional_anthropic_config()` | Same class as ClaudeConfig (line 88). Only if `ANTHROPIC_API_KEY` set |
| `openai` | `Optional[OpenAIConfig]` | `_optional_openai_config()` | Only if `OPENAI_API_KEY` set |
| `litellm` | `Optional[LiteLLMConfig]` | `LiteLLMConfig()` | **Always created** (line 963) |
| `local_model` | `LocalModelConfig` | `LocalModelConfig()` | Always created |
| `research` | `ResearchConfig` | `ResearchConfig()` | Always created |
| `database` | `DatabaseConfig` | `DatabaseConfig()` | Always created |
| `redis` | `RedisConfig` | `RedisConfig()` | Always created |
| `logging` | `LoggingConfig` | `LoggingConfig()` | Always created |
| `literature` | `LiteratureConfig` | `LiteratureConfig()` | Always created |
| `vector_db` | `VectorDBConfig` | `VectorDBConfig()` | Always created |
| `neo4j` | `Neo4jConfig` | `Neo4jConfig()` | Always created |
| `safety` | `SafetyConfig` | `SafetyConfig()` | Always created |
| `performance` | `PerformanceConfig` | `PerformanceConfig()` | Always created |
| `monitoring` | `MonitoringConfig` | `MonitoringConfig()` | Always created |
| `development` | `DevelopmentConfig` | `DevelopmentConfig()` | Always created |
| `world_model` | `WorldModelConfig` | `WorldModelConfig()` | Always created |

**[GOTCHA]** `claude` and `anthropic` are **the same class** (`AnthropicConfig = ClaudeConfig`, line 88) but constructed independently. Both are `None` if `ANTHROPIC_API_KEY` is not set. Code that accesses `config.claude` vs `config.anthropic` may get different instances even though they'd have identical data.

### 6d. Model Validators (Post-Construction)

**Validator 1: `sync_litellm_env_vars`** (lines 986-1022)
Manually syncs `LITELLM_*` env vars into the nested `LiteLLMConfig` sub-model. This is necessary because pydantic-settings nested models don't automatically inherit env vars from the parent's `.env` file. Only overrides defaults, not values already set.

**Validator 2: `validate_provider_config`** (lines 1024-1042)
Enforces that the selected provider has its required API key:
- `LLM_PROVIDER=openai` requires `OPENAI_API_KEY` (or raises `ValueError`)
- `LLM_PROVIDER=anthropic` requires `ANTHROPIC_API_KEY` (or raises `ValueError`)
- `LLM_PROVIDER=litellm` -- **no validation** (line 1040-1041, comment: "local models don't need API keys")

**[GOTCHA]** If `LLM_PROVIDER=anthropic` (the default) and `ANTHROPIC_API_KEY` is not set, `KosmosConfig()` construction raises `ValueError`. This means `get_config()` fails, and the config command itself cannot display what IS configured. The error message is: "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic."

---

## 7. Sub-Config: ClaudeConfig (Anthropic Provider)

**File**: `kosmos/config.py:29-84`

| Field | Env Var | Default | Notes |
|-------|---------|---------|-------|
| `api_key` | `ANTHROPIC_API_KEY` | (required) | All-9s value = CLI mode |
| `model` | `CLAUDE_MODEL` | `"claude-sonnet-4-5"` | Line 17 |
| `max_tokens` | `CLAUDE_MAX_TOKENS` | `4096` | Range: 1-200000 |
| `temperature` | `CLAUDE_TEMPERATURE` | `0.7` | Range: 0.0-1.0 |
| `enable_cache` | `CLAUDE_ENABLE_CACHE` | `True` | Prompt caching |
| `base_url` | `CLAUDE_BASE_URL` | `None` | Custom API endpoint |
| `timeout` | `CLAUDE_TIMEOUT` | `120` | Range: 1-600 seconds |

**[FACT]** `is_cli_mode` property (line 80): `self.api_key.replace('9', '') == ''`. An API key consisting entirely of the digit 9 triggers CLI routing mode, where requests are proxied through the local Claude Code CLI instead of hitting the Anthropic API directly.

---

## 8. Sub-Config: OpenAIConfig

**File**: `kosmos/config.py:91-140`

| Field | Env Var | Default |
|-------|---------|---------|
| `api_key` | `OPENAI_API_KEY` | (required) |
| `model` | `OPENAI_MODEL` | `"gpt-4-turbo"` |
| `max_tokens` | `OPENAI_MAX_TOKENS` | `4096` |
| `temperature` | `OPENAI_TEMPERATURE` | `0.7` (range 0-2.0) |
| `base_url` | `OPENAI_BASE_URL` | `None` |
| `organization` | `OPENAI_ORGANIZATION` | `None` |
| `timeout` | `OPENAI_TIMEOUT` | `120` |

---

## 9. Sub-Config: LiteLLMConfig

**File**: `kosmos/config.py:143-197`

| Field | Env Var | Default |
|-------|---------|---------|
| `model` | `LITELLM_MODEL` | `"gpt-3.5-turbo"` |
| `api_key` | `LITELLM_API_KEY` | `None` |
| `api_base` | `LITELLM_API_BASE` | `None` |
| `max_tokens` | `LITELLM_MAX_TOKENS` | `4096` |
| `temperature` | `LITELLM_TEMPERATURE` | `0.7` |
| `timeout` | `LITELLM_TIMEOUT` | `120` |

**[FACT]** LiteLLMConfig has its own `SettingsConfigDict` with `env_file` pointing to the same `.env` (line 194), unlike other sub-configs which use `populate_by_name=True` only. This is a third env file read path.

---

## 10. Provider Selection at Runtime

### 10a. Factory Layer

**File**: `kosmos/core/providers/factory.py`

Two factory functions:
- `get_provider(provider_name, config_dict)` -- takes a string name + dict, looks up in `_PROVIDER_REGISTRY` (line 34-80).
- `get_provider_from_config(kosmos_config)` -- takes a `KosmosConfig` object, extracts provider name from `kosmos_config.llm_provider`, builds a config dict, then calls `get_provider()` (line 83-175).

### 10b. Auto-Registration

**[FACT]** `_register_builtin_providers()` (lines 189-217) runs at module import time. It registers:
- `"anthropic"` and `"claude"` (alias) -> `AnthropicProvider`
- `"openai"` -> `OpenAIProvider`
- `"litellm"`, `"ollama"`, `"deepseek"`, `"lmstudio"` (aliases) -> `LiteLLMProvider`

Each registration is wrapped in try/except ImportError, so missing packages silently skip.

### 10c. Provider Config Extraction in `get_provider_from_config()`

For `anthropic` provider (lines 107-132):
- First checks for `kosmos_config.claude` (backward compat)
- Then checks for `kosmos_config.anthropic` (new name)
- Extracts: `api_key`, `model`, `max_tokens`, `temperature`, `enable_cache`, `enable_auto_model_selection`, `base_url`

For `openai` provider (lines 134-146):
- Requires `kosmos_config.openai`
- Extracts: `api_key`, `model`, `max_tokens`, `temperature`, `base_url`, `organization`

For `litellm` provider (lines 148-170):
- Checks `kosmos_config.litellm` first
- **Falls back to raw `os.getenv()` calls** if litellm config is None (lines 162-170). This is a third precedence layer unique to LiteLLM.

---

## 11. Environment Variable Master List

### Required (depends on provider):

| Env Var | Required When | Used By |
|---------|---------------|---------|
| `ANTHROPIC_API_KEY` | `LLM_PROVIDER=anthropic` (default) | `ClaudeConfig`, `AnthropicProvider` |
| `OPENAI_API_KEY` | `LLM_PROVIDER=openai` | `OpenAIConfig`, `OpenAIProvider` |
| `LLM_PROVIDER` | Always (default: `"anthropic"`) | `KosmosConfig.llm_provider` |

### Optional LLM config:

| Env Var | Component | Default |
|---------|-----------|---------|
| `CLAUDE_MODEL` | ClaudeConfig | `claude-sonnet-4-5` |
| `CLAUDE_MAX_TOKENS` | ClaudeConfig | `4096` |
| `CLAUDE_TEMPERATURE` | ClaudeConfig | `0.7` |
| `CLAUDE_ENABLE_CACHE` | ClaudeConfig | `true` |
| `CLAUDE_BASE_URL` | ClaudeConfig + AnthropicProvider | `None` |
| `CLAUDE_TIMEOUT` | ClaudeConfig | `120` |
| `OPENAI_MODEL` | OpenAIConfig | `gpt-4-turbo` |
| `OPENAI_MAX_TOKENS` | OpenAIConfig | `4096` |
| `OPENAI_TEMPERATURE` | OpenAIConfig | `0.7` |
| `OPENAI_BASE_URL` | OpenAIConfig | `None` |
| `OPENAI_ORGANIZATION` | OpenAIConfig | `None` |
| `OPENAI_TIMEOUT` | OpenAIConfig | `120` |
| `LITELLM_MODEL` | LiteLLMConfig | `gpt-3.5-turbo` |
| `LITELLM_API_KEY` | LiteLLMConfig | `None` |
| `LITELLM_API_BASE` | LiteLLMConfig | `None` |
| `LITELLM_MAX_TOKENS` | LiteLLMConfig | `4096` |
| `LITELLM_TEMPERATURE` | LiteLLMConfig | `0.7` |
| `LITELLM_TIMEOUT` | LiteLLMConfig | `120` |
| `DATABASE_URL` | DatabaseConfig | `sqlite:///kosmos.db` |

(Full env var listing with 60+ variables in `.env.example`)

---

## 12. Full Request Trace Diagram

```
User runs: kosmos config --show

1. pyproject.toml:179
   kosmos = "kosmos.cli.main:cli_entrypoint"

2. kosmos/cli/main.py:22 (MODULE IMPORT TIME)
   load_dotenv()  --> reads .env into os.environ

3. kosmos/cli/main.py:419 (MODULE IMPORT TIME)
   register_commands() --> imports kosmos.cli.commands.config

4. kosmos/cli/main.py:422
   cli_entrypoint() --> app()

5. kosmos/cli/main.py:98 (GLOBAL CALLBACK - runs first)
   main(ctx, verbose, debug, trace, ...)
   |
   +-> setup_logging()  [main.py:132]
   |   +-> (if --trace) get_config() [main.py:77] --> KosmosConfig() singleton created
   |
   +-> (if --debug-modules) get_config() [main.py:137]
   |
   +-> init_from_config() [main.py:145]
       +-> get_config() [db/__init__.py:160] --> returns singleton
       +-> first_time_setup() --> creates .env if missing, runs migrations
       +-> init_database(config.database.normalized_url)

6. kosmos/cli/commands/config.py:25
   manage_config(show=True)
   |
   +-> (no flags given, so show defaults to True) [line 51]
   +-> display_config() [line 60]
       +-> get_config() [line 126] --> returns singleton
       +-> Displays claude OR openai tables (NOT litellm)
       +-> Displays research config
       +-> Displays database config

7. TERMINAL: Rich-formatted tables printed to stdout
```

---

## 13. Gotcha Summary

| # | Gotcha | Severity | File:Line |
|---|--------|----------|-----------|
| G1 | **DB init on every command**: Global callback initializes database even for `kosmos config --path`. Misconfigured DB shows error before config output. | Medium | `main.py:145` |
| G2 | **Double .env load**: `load_dotenv()` at import time AND pydantic-settings reads `.env` independently. Could diverge if file changes between the two reads. | Low | `main.py:22` + `config.py:979` |
| G3 | **LiteLLM not shown in `config --show`**: `display_config()` only has branches for `claude` and `openai`. LiteLLM users see no provider info. | Medium | `commands/config.py:129-155` |
| G4 | **Config singleton not invalidated after `--reset`**: `config --reset` copies `.env.example` to `.env` but doesn't call `reset_config()`. Same-invocation reads see stale data. | Low | `commands/config.py:322-341` |
| G5 | **`config.claude` and `config.anthropic` are independent instances**: Both are `Optional[ClaudeConfig]` (same class) but constructed separately. Mutations to one don't affect the other. | Medium | `config.py:960-961` |
| G6 | **No `ANTHROPIC_API_KEY` = config crash**: If `LLM_PROVIDER=anthropic` (default) and no API key, `get_config()` raises `ValueError`. `kosmos config --show` fails entirely. | High | `config.py:1033-1038` |
| G7 | **CLI mode detection via all-9s key**: `is_cli_mode` checks `api_key.replace('9', '') == ''`. This is a magic-value convention, not documented prominently. | Low | `config.py:82` |
| G8 | **LiteLLM env var sync is manual**: Nested pydantic-settings models don't auto-inherit parent `.env`. `sync_litellm_env_vars` validator manually patches this, but only for known fields. | Medium | `config.py:986-1022` |
| G9 | **Triple precedence for LiteLLM**: `get_provider_from_config()` falls back to raw `os.getenv()` if `kosmos_config.litellm` is None, creating a third config source not covered by pydantic validation. | Low | `providers/factory.py:162-170` |
| G10 | **Validation uses `os.getenv("LLM_PROVIDER")` separately from `config.llm_provider`**: `validate_config()` reads the env var directly instead of using the config object. | Low | `commands/config.py:215` |

---

## Evidence Quality

- All FACT claims verified by reading specific source lines.
- ABSENCE claim (G3: LiteLLM not shown) verified by reading full `display_config()` function.
- Pattern count: 3 providers (anthropic, openai, litellm) all follow the same BaseSettings sub-model pattern with env_var aliases.
# Trace 03: Scientific Evaluation Pipeline

## Source File
`evaluation/scientific_evaluation.py` (1489 lines)

## Entry Point
```
__main__ (line 1454) -> argparse -> asyncio.run(main(...)) -> sys.exit(exit_code)
```

CLI accepts: `--output-dir`, `--research-question`, `--domain`, `--data-path`, `--max-iterations`
[FACT] Lines 1454-1489.

## Data Structures

**PhaseResult** (line 88-108): Holds per-phase status (`PASS`/`PARTIAL`/`FAIL`/`SKIP`/`ERROR`), duration, details dict, checks list, optional error string. Each check has name, passed bool, detail string.

**EvaluationReport** (line 112-122): Accumulates `List[PhaseResult]` plus rigor_scores, paper_claims, quality_scores, summary. Populated by `add_phase()`.

## main() Orchestration (line 1342-1451)

`main()` is `async`. It runs 7 phases sequentially, accumulating into an `EvaluationReport`.

### Phase Execution Order

| Order | Function | Type | Depends On |
|-------|----------|------|------------|
| P1 | `run_phase1_preflight()` | sync | nothing |
| P2 | `run_phase2_smoke_test()` | async | P1 must PASS |
| P3 | `run_phase3_multi_iteration()` | async | nothing explicit |
| P4 | `run_phase4_dataset_test()` | async | --data-path arg |
| P5 | `assess_output_quality(p2, p3)` | sync | P2, P3 results |
| P6 | `run_phase6_rigor_scorecard()` | sync | nothing (introspection) |
| P7 | `run_phase7_paper_compliance(p2, p3, p4, p6)` | sync | P2, P3, P4, P6 results |

[FACT] Lines 1362-1422: phases called in this exact order.

### Early Abort
If P1 status is `FAIL`, `main()` writes a partial report and returns exit code 1. No further phases execute.
[FACT] Lines 1369-1381.

---

## Phase 1: Pre-flight Checks (line 138-251)

Synchronous. Four sub-checks:

### 1.1 Config validation (line 144-161)
- Calls `kosmos.config.get_config()` -> `KosmosConfig` singleton
  [FACT] `kosmos/config.py:1140` -- singleton via global `_config`.
- Checks `config.llm_provider`, and if litellm, checks `config.litellm.model`.
- On failure: sets status=FAIL, returns immediately.

### 1.2 LLM connectivity (line 169-192)
- Calls `kosmos.core.llm.get_client(reset=True)` -> creates LLM provider via `get_provider_from_config()`.
  [FACT] `kosmos/core/llm.py:613-672` -- thread-safe singleton with provider factory.
- Sends test prompt: `"Say hello in one word."`, max_tokens=50, temperature=0.0.
- Measures latency. On failure: status=FAIL, returns immediately.

### 1.3 Database initialization (line 195-208)
- Calls `kosmos.db.init_from_config()` -> runs `first_time_setup()`, creates engine, creates tables.
  [FACT] `kosmos/db/__init__.py:140-188`.
- Calls `get_session()` context manager to verify.
- Gracefully handles "already initialized" RuntimeError.

### 1.4 Type compatibility (line 210-243)
- Validates that LLM response object supports `.strip()`, `.lower()`, `in` operator, and `json.loads()`.
- Purpose: validates the LLMResponse type fix (described as "Phase 0 LLMResponse fix" at line 209).
- On AttributeError: status=FAIL.

### Terminal Side Effects: None. Returns `PhaseResult`.

---

## Phase 2: Single-Iteration E2E Smoke Test (line 258-413)

Async. Runs a full single-iteration research cycle.

### State Reset
Calls `_reset_eval_state()` (line 262), which resets 5 singletons for isolation:
1. `kosmos.db.reset_database()` -- drops and recreates all tables. [FACT] `kosmos/db/__init__.py:191-202`.
2. `kosmos.core.cache_manager.get_cache_manager().clear()` + `reset_cache_manager()`. [FACT] `kosmos/core/cache_manager.py:498-518`.
3. `kosmos.core.claude_cache.reset_claude_cache()` -- sets global to None. [FACT] `kosmos/core/claude_cache.py:401-404`.
4. `kosmos.agents.registry.get_registry().clear()`. [FACT] `kosmos/agents/registry.py:512-525`.
5. `kosmos.world_model.reset_world_model()`. [FACT] `kosmos/world_model/factory.py:158`.

### Director Construction (line 265-296)
- Creates `ResearchDirectorAgent` with flat config dict containing:
  - max_iterations=1, budget_usd=5.0, enable_concurrent_operations=False
  - Single-threaded: max_parallel_hypotheses=1, max_concurrent_experiments=1
- Default research question: "How does temperature affect enzyme catalytic rates?" (biology)
- If `data_path` provided, adds it to flat_config.

### Registration
Director registered with `AgentRegistry` singleton. [FACT] Line 300-302.

### Research Plan Generation (line 305-315)
- Calls `director.generate_research_plan()`.
  [FACT] `kosmos/agents/research_director.py:2349-2382`.
- This sends an LLM prompt asking for initial hypothesis directions, experiment strategy, success criteria.
- Response stored in `self.research_plan.initial_strategy`.

### Workflow Start (line 318-323)
- Calls `director.start()` -> `BaseAgent.start()` -> `ResearchDirectorAgent._on_start()`.
  [FACT] `kosmos/agents/base.py:159-175`, `kosmos/agents/research_director.py:319-332`.
- Transitions workflow state: `INITIALIZING` -> `GENERATING_HYPOTHESES`.

### Action Loop (line 326-360)
- Iterates up to `max_actions=20` times.
- Each iteration: `director.decide_next_action()` -> `director._execute_next_action(next_action)` with 120s timeout.
- `decide_next_action()` (line 2388) implements a state machine:
  - Checks budget (metrics.enforce_budget) [FACT] line 2404-2422.
  - Checks runtime limit [FACT] line 2427-2446.
  - Infinite loop guard: MAX_ACTIONS_PER_ITERATION=50 [FACT] line 2455-2461.
  - State-based routing: GENERATING_HYPOTHESES->GENERATE_HYPOTHESIS, DESIGNING_EXPERIMENTS->DESIGN_EXPERIMENT, etc.
- `_execute_next_action()` (line 2550) wraps `_do_execute_action()` with stage tracking.
- `_do_execute_action()` (line 2573) dispatches to handler methods.

### Action Dispatch Map
| NextAction | Handler | Key Module Called |
|---|---|---|
| GENERATE_HYPOTHESIS | `_handle_generate_hypothesis_action()` (line 1391) | `HypothesisGeneratorAgent.generate_hypotheses()` |
| DESIGN_EXPERIMENT | `_handle_design_experiment_action()` (line 1458) | `ExperimentDesignerAgent.design_experiment()` |
| EXECUTE_EXPERIMENT | `_handle_execute_experiment_action()` (line 1521) | `ExperimentCodeGenerator.generate()` + `CodeExecutor.execute()` |
| ANALYZE_RESULT | `_handle_analyze_result_action()` (line 1666) | `DataAnalystAgent.interpret_results()` |
| REFINE_HYPOTHESIS | `_handle_refine_hypothesis_action()` (line 1796) | `HypothesisRefiner.evaluate_hypothesis_status()` + `.refine_hypothesis()` |
| CONVERGE | `_handle_convergence_action()` (line 1334) | `ConvergenceDetector` (direct call pattern) |
| ERROR_RECOVERY | inline (line 2716-2728) | Transitions to GENERATING_HYPOTHESES |

[FACT] All line numbers verified from `kosmos/agents/research_director.py`.

### Workflow State Machine
```
INITIALIZING -> GENERATING_HYPOTHESES -> DESIGNING_EXPERIMENTS -> EXECUTING -> ANALYZING -> REFINING -> (loop or CONVERGED)
```
[FACT] `kosmos/core/workflow.py:18-29`.

### Loop Termination
Breaks on: `research_plan.has_converged`, `workflow.current_state == CONVERGED`, or max_actions reached.

### Post-loop Evaluation (line 362-400)
- Captures `director.get_research_status()` [FACT] line 2926-2952.
- Checks: hypotheses_generated > 0, workflow advanced past INITIALIZING, no AttributeErrors in action log.
- Captures LLM usage stats if available.

### Terminal Side Effects: None directly. Populates `PhaseResult.details["action_log"]` and `PhaseResult.details["final_status"]`.

---

## Phase 3: Multi-Iteration Full Loop (line 420-567)

Async. Same pattern as Phase 2 but with 3 iterations (configurable via `--max-iterations`).

### Key Differences from Phase 2
- `max_iterations=3` (or user-specified), `budget_usd=10.0`.
- Default question: "What is the relationship between substrate concentration and enzyme reaction velocity?"
- max_total_actions = max(60, configured_max * 10). [FACT] Line 469.
- Takes iteration snapshots at boundaries (line 500-504) via `director.get_research_status()`.
- Continues past errors (line 492-497) unless they are AttributeErrors.

### Additional Checks (line 520-556)
- `loop_completed`: always True if reached.
- `hypotheses_generated`: pool_size > 0.
- `experiments_executed`: experiments_completed > 0.
- `refinement_attempted`: checks if any phase value contains "refine" (case-insensitive). [FACT] Line 541.
- `convergence_not_premature`: validates bug C fix -- convergence at iteration <= 1 is flagged. [FACT] Line 549-555.

### Terminal Side Effects: None.

---

## Phase 4: Dataset Input Test (line 574-717)

Async. Tests data ingestion with user-provided dataset.

### Guard
Returns FAIL immediately if `data_path is None`. [FACT] Line 580-585.
Returns SKIP if path doesn't exist. [FACT] Line 590-594.

### Sub-checks
1. **Dataset existence** (line 596).
2. **Dataset readability** (line 599-611): Uses pandas `read_csv()` -- external dependency!
3. **DataProvider loading** (line 614-624): `kosmos.execution.data_provider.DataProvider.get_data(file_path=...)`.
   [FACT] `kosmos/execution/data_provider.py:280`.
4. **Director with data_path** (line 627-689): Creates a director with data_path in config, runs 10 steps.
5. **Multi-format support** (line 694-710): Introspects `DataProvider.get_data` source code for format strings (.tsv, .parquet, .json, .jsonl, .csv).

### Terminal Side Effects: None.

---

## Phase 5: Output Quality Assessment (line 724-809)

Synchronous. Grades output from Phase 2 and Phase 3. No live execution.

### Scoring Method
For each prior phase result (phase2, phase3):
- **Hypothesis quality** (line 736-755): keyword scan of plan text for specificity, mechanism, testability, novelty indicators. Heuristic score 1-10.
- **Experiment design** (line 757-767): checks if "design_experiment" was in phases_seen.
- **Code execution** (line 770-775): checks if "execute_experiment" was in phases_seen.
- **Analysis** (line 778-783): checks if "analyze_result" was in phases_seen.

### Terminal Side Effects: None.

---

## Phase 6: Scientific Rigor Scorecard (line 816-992)

Synchronous. Introspects code to verify 8 scientific rigor features.

### Feature Assessment (all via import + hasattr/inspect)

| # | Feature | Module Inspected | Check Method |
|---|---------|-----------------|--------------|
| 1 | Novelty checking | `kosmos.hypothesis.novelty_checker.NoveltyChecker` | hasattr `check_novelty` + grep in `HypothesisGeneratorAgent` source |
| 2 | Power analysis | `kosmos.experiments.statistical_power.PowerAnalyzer` | hasattr `ttest_sample_size`, `correlation_sample_size` + grep in `ExperimentDesignerAgent` source |
| 3 | Assumption checking | `kosmos.execution.code_generator` module source | grep for "shapiro", "levene" |
| 4 | Effect size randomization | `kosmos.execution.data_provider.SyntheticDataGenerator` source | grep for "randomize_effect_size" |
| 5 | Multi-format loading | `kosmos.execution.data_provider.DataProvider.get_data` source | grep for format strings |
| 6 | Convergence criteria | `kosmos.core.convergence.ConvergenceDetector` | hasattr `check_convergence` + grep in `ResearchDirectorAgent` source |
| 7 | Reproducibility | `kosmos.safety.reproducibility.ReproducibilityManager` | hasattr `set_seed` |
| 8 | Cost tracking | `kosmos.core.metrics.get_metrics()` | hasattr `enforce_budget` or `budget_enabled` |

[FACT] Lines 822-982. Each feature uses the same pattern: import class, check method existence, optionally inspect calling code to confirm wiring.

### Terminal Side Effects: None.

---

## Phase 7: Paper Compliance Gap Analysis (line 999-1213)

Synchronous. Evaluates 15 claims from arXiv:2511.02824v2.

### Input Dependencies
Takes results from P2, P3, P4, P6 as arguments. Does NOT re-run anything.

### Claim Evaluation Method
- Claims 1-3, 10-11: Derived from P3/P4 details (action counts, plan quality).
- Claims 4, 12-14: Import checks (WorldModel, ParallelExperimentExecutor, DockerSandbox, create_world_model factory).
- Claim 5: Hardcoded `BLOCKER` -- no benchmark dataset available. [FACT] Line 1063-1069.
- Claim 6: Import check for `LiteratureAnalyzerAgent`.
- Claims 7-9: From P6 rigor scores (novelty, power analysis, cost tracking).
- Claim 15: Import check for `ResultSummarizer`.

### Terminal Side Effects: None.

---

## Report Generation (line 1220-1335)

`generate_report(report: EvaluationReport) -> str` produces a markdown string.

### Output Structure
1. Title + metadata
2. Executive Summary: phases run, checks passed/total, total duration
3. Per-phase detail blocks with:
   - Check tables (name, PASS/FAIL, detail)
   - Phase-specific subsections (LLM info for P1, research status for P2/P3, quality scores for P5, rigor scorecard for P6, paper claims table for P7)
4. Limitations section (6 honest caveats about LLM quality, synthetic data, no benchmark, etc.)

---

## Terminal Side Effects (File Output)

### 1. Markdown Report
[FACT] Two write points:
- On P1 failure: `output_dir / "EVALUATION_REPORT.md"` or `evaluation/SCIENTIFIC_EVALUATION_REPORT.md` (line 1375-1379).
- Normal completion: same paths (line 1427-1432).
Uses `Path.write_text(report_text)`.

### 2. Log File
[FACT] Line 39-41, 47: `evaluation/logs/evaluation_YYYYMMDD_HHMMSS.log` created at module load time. Dual handler: file + stdout.

### 3. Database Side Effects
[FACT] `_reset_eval_state()` (line 54-81) drops and recreates all DB tables. Called at the start of phases 2, 3, and 4. This is destructive.

### 4. Stdout
All phases print progress to stdout. Final summary with check counts, duration, report path, log path, and per-phase status icons (OK/~~/XX). [FACT] Lines 1355-1451.

---

## Data Flow Between Phases

```
P1 (preflight) -> gate (FAIL = abort)
    |
P2 (smoke) -------> P5 (quality assessment)
    |                      ^
P3 (multi-iter) ----------/
    |                      |
P4 (dataset) -------------|--------> P7 (paper compliance)
    |                      |              ^
P6 (rigor scorecard) -----|-------------/
    |
    v
generate_report([P1..P7]) -> EVALUATION_REPORT.md
```

P5 consumes P2 + P3 results (hypothesis quality, phases_seen).
P7 consumes P2 + P3 + P4 + P6 results (cross-referencing all evidence).

---

## Gotchas

### G1: create_world_model ImportError (Known Bug)
[FACT] Line 1161: `from kosmos.world_model.factory import create_world_model` -- this name does not exist in the factory module. The factory exports `get_world_model` and `reset_world_model` only.
[FACT] Confirmed by `kosmos/world_model/__init__.py:157-158` which exports only those two names.
[PATTERN] This error appears in 10+ evaluation reports in `evaluation/personas/runs/`. Every run hits this.
**Impact**: Paper compliance claim 14 always falls through to the except branch and reports PARTIAL.

### G2: Destructive Database Reset
[FACT] `_reset_eval_state()` (line 54-61) calls `reset_database()` which runs `Base.metadata.drop_all()` + `create_all()`. This destroys all data in the configured database.
**Impact**: Running the evaluation against a production database would wipe it. No guard against this beyond the function name.

### G3: Phase 4 Requires Pandas (External Dependency)
[FACT] Line 600: `import pandas as pd`. Phase 4 will crash with ImportError if pandas is not installed. This is notable because the Kosmos core claims zero external dependencies for some paths, but evaluation depends on pandas.

### G4: 120-second Hardcoded Timeout per Action
[FACT] Lines 338-345, 484-490, 673-679: `asyncio.wait_for(..., timeout=120)`. Every single action in phases 2, 3, and 4 has a 120-second hard timeout. Complex LLM operations (especially with slow providers or large prompts) may routinely exceed this.

### G5: Phase 5 Quality Scoring is Purely Heuristic
[FACT] Lines 740-744: Quality assessment searches for literal keyword substrings ("specific", "measurable", "mechanism", etc.) in the plan preview text. These keywords come from the LLM-generated plan, not from any structured quality metric.

### G6: Convergence Claim 2 Always Reports PARTIAL
[FACT] Lines 1028-1036: Claim 2 ("~166 data analysis rollouts per run") hardcodes status as "PARTIAL" regardless of actual action count, because the eval only tests 3 iterations, not the full 10+ the paper describes.

### G7: Phase 2/3 Action Loop Asymmetry
[FACT] Phase 2 max_actions=20 (line 328), Phase 3 max_total_actions=max(60, configured_max*10) (line 469). Phase 2 may terminate prematurely for complex research questions that need more actions to complete a single iteration.

### G8: _reset_eval_state Exception Swallowing
[FACT] Lines 57-60, 64-67, 73-76: Each reset call is wrapped in try/except that silently swallows exceptions. If reset_database() fails, it falls back to init_from_config(), but if that also fails, the phase proceeds with potentially dirty state.

### G9: No JSON Output
[ABSENCE] Searched for `json.dump` in the evaluation file. Only `json.dumps` appears at line 504 for logging. The evaluation produces only a markdown report, never a machine-readable JSON output with the structured EvaluationReport data.
# Trace 04: Persona Evaluation Flow

## Entry Point

`evaluation/personas/run_persona_eval.py:main()` (line 258)

## Full Call Trace

### Step 1: Argument Parsing (line 259-278)

`main()` uses argparse to accept:
- `--persona` (required): persona name, e.g. `001_enzyme_kinetics_biologist`
- `--tier` (int, choices=[1], default=1): only Tier 1 is automated
- `--dry-run`: show commands without executing
- `--version`: override auto-increment version string

[FACT] `--tier` is constrained to `choices=[1]` at line 267 -- Tiers 2 and 3 are manual (Claude agent-driven), not orchestrated by this script.

### Step 2: Persona Loading (line 286)

```
persona = load_persona(args.persona)
```

`load_persona()` (line 36-61):
1. Imports PyYAML dynamically (line 38); hard-exits with `sys.exit(1)` if missing (line 40).
2. Constructs path: `DEFINITIONS_DIR / f"{persona_name}.yaml"` where `DEFINITIONS_DIR = evaluation/personas/definitions/` (line 29).
3. Reads YAML with `yaml.safe_load(f)` (line 52).
4. Validates three required top-level keys: `["persona", "research", "setup"]` (line 56). Missing key causes `sys.exit(1)`.
5. Returns the full parsed dict.

[FACT] Four persona definitions exist:
- `001_enzyme_kinetics_biologist.yaml` -- Dr. Sarah Chen, Computational Biologist, biology domain
- `002_perovskite_solar_cell_researcher.yaml` -- Dr. Elena Martinez, Materials Scientist, materials domain
- `003_genomics_researcher.yaml` -- Dr. Kenji Tanaka, Computational Genomics Researcher, genomics domain
- `004_climate_data_scientist.yaml` -- Dr. Amara Osei, Climate Data Scientist, physics domain

[PATTERN] All 4 personas share identical structure: `persona`, `research`, `setup`, `expectations`, `narrative` sections. All use `deepseek/deepseek-chat` via `litellm`, sqlite, no neo4j, no docker. All have `max_iterations: 3` and `budget_usd: 1.00`. (4/4 personas)

### Step 3: Versioning (line 294)

```
version = args.version or get_next_version(args.persona)
```

`get_next_version()` (line 64-84):
1. Looks in `runs/{persona_name}/` for directories matching `v*`.
2. Parses version numbers from directory names like `v001_20260207` via `int(dirname.split("_")[0][1:])` (line 79).
3. Returns next version: `f"v{max_ver + 1:03d}"`.

### Step 4: Run Directory Creation (line 298)

```
run_dir = create_run_directory(args.persona, version)
```

`create_run_directory()` (line 106-116):
Creates directory tree:
```
runs/{persona_name}/{version}_{YYYYMMDD}/
    tier1/artifacts/
    tier2/
    tier3/
```

### Step 5: Initial meta.json Write (line 307)

```
write_meta_json(run_dir, persona, version)
```

`write_meta_json()` (line 119-145) writes JSON containing:
- `persona_id`, `persona_name` from YAML
- `version`, `timestamp`, `model`, `provider` from YAML
- `kosmos_git_sha` via `get_git_sha()` (subprocess call to `git rev-parse HEAD`, line 87-96)
- `config_hash` via `compute_config_hash()` (SHA-256 of JSON-serialized persona dict, line 99-102)
- `tier1_completed: false`, `tier2_completed: false`, `tier3_completed: false`
- `checks_passed: 0`, `checks_total: 0`, `duration_seconds: 0.0`

### Step 6: Tier 1 Execution (line 310-327)

```
success = run_tier1(args.persona, persona, run_dir, dry_run=args.dry_run)
```

`run_tier1()` (line 148-230) does three things:

#### 6a. Invoke `scientific_evaluation.py` (line 150-230)

Builds subprocess command:
```
python evaluation/scientific_evaluation.py \
  --output-dir {run_dir}/tier1 \
  --research-question {research.question} \
  --domain {research.domain} \
  --data-path {evaluation/research.dataset} \
  --max-iterations {research.max_iterations}
```

[FACT] Before execution, it **destructively deletes** `kosmos.db` and `.kosmos_cache` at project root (lines 186-191) to ensure a clean evaluation state. This is a side effect that affects any running Kosmos instance.

Executes via `subprocess.run(cmd, cwd=PROJECT_ROOT)` (line 196) -- blocking, no timeout.

#### 6b. Invoke `run_phase2_tests.py` (line 202-221)

Builds a second subprocess command:
```
python evaluation/run_phase2_tests.py \
  --output-dir {run_dir}/tier1/artifacts/phase2_components \
  --research-question {research.question} \
  --domain {research.domain} \
  --data-path {evaluation/research.dataset}
```

Executes via `subprocess.run()` (line 219) -- again blocking, no timeout.

#### 6c. Copy eval log (line 223-228)

Copies the latest `evaluation/logs/evaluation_*.log` file to `{run_dir}/tier1/eval.log`.

### Step 7: Parse Tier 1 Results (line 317)

```
checks_passed, checks_total, duration = parse_tier1_results(run_dir)
```

`parse_tier1_results()` (line 233-255):
Reads `{run_dir}/tier1/EVALUATION_REPORT.md` and regex-parses:
- Check counts: `r"Checks passed.*?(\d+)/(\d+)"` or `r"(\d+)/(\d+)\s+checks?\s+passed"` (lines 244-249)
- Duration: `r"Duration.*?(\d+\.?\d*)\s*s"` (line 251)

### Step 8: Final meta.json Update (line 318-324)

Calls `write_meta_json()` again with actual results (`tier1_completed`, `checks_passed`, `checks_total`, `duration_seconds`).

### Step 9: Next Steps Output (line 329-356)

Prints instructions for manual Tier 2 and Tier 3, and if prior versions exist, prints the `compare_runs.py` command.

---

## scientific_evaluation.py Internal Flow (1489 lines)

`evaluation/scientific_evaluation.py:main()` (line 1342, async function)

Accepts: `output_dir`, `research_question`, `domain`, `data_path`, `max_iterations`.

### Phase 1: Pre-flight Checks (line 1364)
`run_phase1_preflight()` (line 138-250) -- synchronous
- 1.1 Config loads via `kosmos.config.get_config()`
- 1.2 LLM connectivity test via `kosmos.core.llm.get_client()` + `.generate()`
- 1.3 Database init via `kosmos.db.init_from_config()`
- 1.4 Type compatibility (`.strip()`, `.lower()`, `json.loads()` on LLM response)
- **BAIL-OUT**: If Phase 1 FAILs, writes partial report and returns exit code 1 (line 1369-1381).

### Phase 2: Single-Iteration E2E Smoke Test (line 1385)
`run_phase2_smoke_test()` (line 258-413) -- async
- Creates `ResearchDirectorAgent` with `max_iterations=1`
- Registers with `AgentRegistry`
- Generates research plan, starts workflow
- Loops up to 20 actions, each with 120s timeout via `asyncio.wait_for()`
- Checks: director_created, research_plan_generated, workflow_started, hypotheses_generated, workflow_advanced, no_attribute_errors

[FACT] `_reset_eval_state()` (line 54-81) is called at the start of each of phases 2, 3, and 4 to reset DB, cache, claude cache, agent registry, and world model.

### Phase 3: Multi-Iteration Full Loop (line 1392)
`run_phase3_multi_iteration()` (line 420-567) -- async
- Creates `ResearchDirectorAgent` with `max_iterations=3` (or persona override)
- Safety limit: `max(60, configured_max * 10)` total actions (line 469)
- Takes iteration snapshots at iteration boundaries
- Checks: loop_completed, hypotheses_generated, experiments_executed, refinement_attempted, convergence_not_premature

### Phase 4: Dataset Input Test (line 1399)
`run_phase4_dataset_test()` (line 574-717) -- async
- Requires `data_path` -- hard fails if None (line 580-585)
- Loads CSV with pandas, verifies `DataProvider.get_data()`, tests director with data_path
- Checks multi-format support via source code inspection of `DataProvider.get_data`
- Checks: dataset_exists, dataset_readable, data_provider_loads_csv, director_accepts_data_path, multi_format_support

### Phase 5: Output Quality Assessment (line 1406)
`assess_output_quality()` (line 724-809) -- synchronous
- Grades Phase 2 and Phase 3 outputs on: hypothesis_quality, experiment_design, code_execution, analysis
- Hypothesis quality scored heuristically via keyword search in research plan text (line 741-744)
- Score formula: `max(1, min(10, 3 + specificity*2 + mechanism*2 + testable*2 + novel*1))` (line 747)

### Phase 6: Scientific Rigor Scorecard (line 1413)
`run_phase6_rigor_scorecard()` (line 816-992) -- synchronous
- Scores 8 features via import + inspection: novelty_checking, power_analysis, assumption_checking, effect_size_randomization, multi_format_loading, convergence_criteria, reproducibility, cost_tracking
- Each feature: attempt import, check method existence, inspect source for wiring

### Phase 7: Paper Compliance Gap Analysis (line 1420)
`run_phase7_paper_compliance()` (line 999-1213) -- synchronous
- Evaluates 15 claims from arXiv:2511.02824v2
- Uses results from phases 2, 3, 4, 6
- Each claim scored: PASS, PARTIAL, FAIL, or BLOCKER

### Report Generation (line 1426)
`generate_report()` (line 1220-1335)
- Assembles Markdown from all `PhaseResult` objects
- Writes to `{output_dir}/EVALUATION_REPORT.md` or default `evaluation/SCIENTIFIC_EVALUATION_REPORT.md`
- Appends hard-coded "Limitations" section (line 1324-1332)

---

## run_phase2_tests.py Internal Flow (571 lines)

`evaluation/run_phase2_tests.py` -- standalone script, not async

Runs 6 component tests independently:
1. **2.1 Hypothesis Generation** (line 62): `HypothesisGeneratorAgent.generate_hypotheses()`
2. **2.2 Literature Search** (line 117): `UnifiedLiteratureSearch.search()`
3. **2.3 Experiment Design** (line 150): `ExperimentDesignerAgent.design_experiment()`
4. **2.4 Code Generation & Execution** (line 217): `TTestComparisonCodeTemplate.generate()` + `CodeExecutor.execute()`
5. **2.5 Data Analysis** (line 315): `DataAnalystAgent.interpret_results()` with mock data
6. **2.6 Convergence Detection** (line 412): `ConvergenceDetector.check_convergence()`

[FACT] Accepts `--research-question`, `--domain`, `--data-path` to use persona-specific parameters instead of hardcoded biology defaults (lines 498-517).

### Terminal Side Effects:
- Each test result written as `{output_dir}/{test_name}.json` (line 563-566)
- Combined results: `{output_dir}/all_components.json` (line 568-569)
- Default output: `evaluation/artifacts/phase2_components/` (line 560)

---

## compare_runs.py Flow (305 lines)

`evaluation/personas/compare_runs.py:main()` (line 248)

### Input:
- `--persona`: persona name
- `--v1`: baseline version directory name
- `--v2`: current version directory name
- `--output`: optional output path

### compare_runs() (line 148-245):
1. Loads `meta.json` from both run directories (line 160-161)
2. Parses `EVALUATION_REPORT.md` from both via `parse_evaluation_report()` (line 163-164)
3. Computes summary deltas for: checks_passed, checks_total, quality_score, rigor_score, paper_claims_pass
4. Categorizes individual checks as: improved, regressed, unchanged
5. Computes quality score deltas per dimension
6. Computes rigor score deltas per feature
7. Identifies paper claim status changes

### parse_evaluation_report() (line 36-132):
Regex-based Markdown parser extracting:
- Summary line: check counts, duration
- Check table: `| check_name | PASS/FAIL | detail |`
- Quality scores: `| phaseN_dim | N/10 | details |`
- Rigor scores: from rigor section only (avoids quality score overlap via `startswith("phase")` filter, line 103)
- Paper claims: `| N | claim | STATUS | detail |`
- Aggregate counts: `PASS=N, PARTIAL=N, FAIL=N, BLOCKER=N`

### Terminal Side Effects:
- Writes JSON to `runs/{persona}/regression/{v1}_vs_{v2}.json` (line 278) or `--output` path
- Prints summary table to stdout (lines 288-301)

---

## File Write Map (all terminal side effects)

| Script | File Written | Location |
|--------|-------------|----------|
| `run_persona_eval.py` | `meta.json` (2x: initial + final) | `runs/{persona}/{version}/meta.json` |
| `run_persona_eval.py` | tier directories | `runs/{persona}/{version}/tier{1,2,3}/` |
| `scientific_evaluation.py` | `EVALUATION_REPORT.md` | `{output_dir}/EVALUATION_REPORT.md` |
| `scientific_evaluation.py` | Log file | `evaluation/logs/evaluation_YYYYMMDD_HHMMSS.log` |
| `run_persona_eval.py` | Copied log | `{run_dir}/tier1/eval.log` |
| `run_phase2_tests.py` | Per-component JSON | `{output_dir}/{test_name}.json` (6 files) |
| `run_phase2_tests.py` | Combined JSON | `{output_dir}/all_components.json` |
| `compare_runs.py` | Regression JSON | `runs/{persona}/regression/{v1}_vs_{v2}.json` |
| `run_persona_eval.py` | **Deletes** `kosmos.db` | project root (line 187) |
| `run_persona_eval.py` | **Deletes** `.kosmos_cache/` | project root (line 190) |

---

## Gotchas

### Gotcha 1: Destructive DB/Cache Wipe
[FACT] `run_persona_eval.py:run_tier1()` lines 186-191 unconditionally delete `kosmos.db` and `.kosmos_cache/` from the project root before running. This destroys any existing Kosmos research state. There is no confirmation prompt and no backup.

### Gotcha 2: No Subprocess Timeout
[FACT] Both subprocess calls in `run_tier1()` (lines 196, 219) use `subprocess.run()` without a `timeout` parameter. If `scientific_evaluation.py` or `run_phase2_tests.py` hangs (e.g., LLM never responds), the persona eval hangs indefinitely.

### Gotcha 3: Hard `sys.exit(1)` on Missing YAML/Field
[FACT] `load_persona()` calls `sys.exit(1)` at lines 40 and 59 for missing file or missing field. This makes the function unusable from library code -- it cannot be called in a try/except since it terminates the process.

### Gotcha 4: PyYAML is a Runtime Dependency
[FACT] `load_persona()` line 38-40 does a dynamic `import yaml` with a hard exit if missing. PyYAML is not in stdlib, so this entire system fails without it, but the dependency is discovered only at runtime.

### Gotcha 5: Tier 1 Only -- Tiers 2/3 are Manual
[FACT] `--tier` at line 267 is `choices=[1]`. Tiers 2 (Technical Diagnostic) and 3 (Narrative) require a Claude agent to manually read artifacts and fill templates. The orchestrator only prints instructions (lines 334-341). Evidence: v001 for persona 001 has an empty `tier2/` directory but a populated `tier3/NARRATIVE.md`, indicating manual agent execution.

### Gotcha 6: Regex-Based Report Parsing is Fragile
[FACT] Both `parse_tier1_results()` (line 233-255) and `parse_evaluation_report()` (line 36-132) extract structured data from Markdown via regex. If the report format changes (e.g., wording of "Checks passed"), parsing silently returns zeros/empty dicts. No validation that parsing succeeded.

### Gotcha 7: Hardcoded `os.chdir` in Phase 2 Tests
[FACT] `run_phase2_tests.py` line 16 has `os.chdir("/mnt/c/python/Kosmos")` -- a hard-coded absolute path. This breaks on any machine with a different filesystem layout.

### Gotcha 8: Persona Setup Fields Not Used for LLM Config
[FACT] Persona YAML `setup.model` and `setup.provider` are recorded in `meta.json` (lines 129-130 of `run_persona_eval.py`) but are **never passed** to `scientific_evaluation.py` as CLI arguments. The evaluation uses whatever model is configured in `kosmos.config` (the system default), not the persona-specified model. The persona's model/provider fields are metadata-only.

### Gotcha 9: `expectations` Section Never Evaluated
[FACT] The persona YAML `expectations` block (e.g., `hypothesis_quality_minimum: 5`, `paper_claims_pass_minimum: 10`) is loaded but never referenced in `run_persona_eval.py` or `scientific_evaluation.py`. No code compares actual scores against these thresholds. They exist only as documentation.

### Gotcha 10: Version Parse Bug with Underscore-Free Names
[FACT] `get_next_version()` line 79 splits on `"_"` to parse version numbers: `int(dirname.split("_")[0][1:])`. If a directory name contains no underscore (e.g., `v001`), the split still works because `split("_")[0]` returns the whole string. But if the directory name is malformed (e.g., `v_extra`), it would try `int("v")` and silently skip via the `except` clause (line 83). Silent version number miscounting is possible.

---

## Evidence of Actual Runs

[FACT] 4 personas have run directories under `evaluation/personas/runs/`:
- `001_enzyme_kinetics_biologist`: 3 versions (v001-v003), 3 regression comparisons, tier3 narrative exists for v001
- `002_perovskite_solar_cell_researcher`: exists (structure not fully enumerated)
- `003_genomics_researcher`: exists
- `004_climate_data_scientist`: 7 versions (v001-v007), indicating heavy iteration

[FACT] Regression comparison `v001_vs_v002` for persona 001 shows: +1 check improved (`refinement_attempted`), quality score +0.04, rigor unchanged, zero paper claim changes. File: `runs/001_enzyme_kinetics_biologist/regression/v001_20260207_vs_v002_20260207.json`.

[FACT] All 4 persona datasets exist in `evaluation/data/`: `enzyme_kinetics_test.csv` (49 rows), `perovskite_solar_cell_test.csv`, `gene_expression_test.csv`, `climate_co2_temperature_test.csv`.
# Trace 05: E2E Smoke Test Execution Path

## Overview

Kosmos has **three distinct smoke test artifacts** at different layers:
1. **Template smoke test** (Claude Code skill): `.claude/skills/kosmos-e2e-testing/templates/smoke-test.py`
2. **Script smoke test** (standalone): `scripts/smoke_test.py`
3. **Pytest smoke test** (formal E2E): `tests/e2e/test_smoke.py`

Each exercises different parts of the system. This trace covers all three, with primary focus on the template smoke test as specified.

---

## 1. Template Smoke Test: `smoke-test.py:main()`

**File**: `.claude/skills/kosmos-e2e-testing/templates/smoke-test.py`

### Entry Point

```
main() [line 149]
  -> test_llm_client_initialization() [line 17]
  -> test_workflow_initialization() [line 32]
  -> test_provider_modules() [line 49]
  -> test_gap_modules() [line 74]
  -> test_database_operations() [line 124]
  -> asyncio.run(test_simple_llm_call()) [line 164-165]
```

[FACT] `main()` at line 149 runs 6 tests sequentially, collects boolean results into a list, prints a summary, and returns `passed == total`. Exit code is 0 on full pass, 1 on any failure (line 190).

### Test 1: LLM Client Initialization (line 17-28)

**Call chain**:
```
smoke-test.py:17  from kosmos.core.llm import get_client
smoke-test.py:23  client = get_client()
  -> kosmos/core/llm.py:613  get_client(reset=False, use_provider_system=True)
  -> kosmos/core/llm.py:654    from kosmos.config import get_config
  -> kosmos/core/llm.py:655    from kosmos.core.providers import get_provider_from_config
  -> kosmos/core/llm.py:657    config = get_config()
  -> kosmos/core/llm.py:658    _default_client = get_provider_from_config(config)
  -> kosmos/core/providers/factory.py:34  get_provider(provider_name, config)
       instantiates AnthropicProvider or OpenAIProvider based on config.llm_provider
```

**Fallback path** (line 662-673): If provider init fails, falls back to `AnthropicProvider` using `ANTHROPIC_API_KEY` from environment.

[FACT] `get_client()` at `kosmos/core/llm.py:613` is a singleton with thread-safe double-checked locking (line 646-649). The `_client_lock` is a `threading.Lock()` at line 610.

**GOTCHA**: [FACT] If `ANTHROPIC_API_KEY` is not set AND no `.env` file is configured with provider config, this test will fail with a `ValueError` from `ClaudeClient.__init__()` at `kosmos/core/llm.py:165`. The fallback at line 666 also requires `ANTHROPIC_API_KEY`.

### Test 2: Workflow Initialization (line 32-46)

**Call chain**:
```
smoke-test.py:36  from kosmos.workflow.research_loop import ResearchWorkflow
smoke-test.py:38  ResearchWorkflow(research_objective="Test objective", artifacts_dir="./test_artifacts")
  -> kosmos/workflow/research_loop.py:55  __init__()
     line 95:  self.context_compressor = ContextCompressor(anthropic_client=None)
       -> kosmos/compression/compressor.py (NotebookCompressor init, mock mode)
     line 99:  self.state_manager = ArtifactStateManager(artifacts_dir=artifacts_dir)
       -> kosmos/world_model/artifacts.py (creates JSON artifacts dir)
     line 106: self.skill_loader = SkillLoader()
       -> kosmos/agents/skill_loader.py (loads skill bundles, no external deps)
     line 110: self.scholar_eval = ScholarEvalValidator(anthropic_client=None)
       -> kosmos/validation/scholar_eval.py (mock mode, no LLM calls)
     line 114: self.plan_creator = PlanCreatorAgent(anthropic_client=None)
     line 115: self.plan_reviewer = PlanReviewerAgent(anthropic_client=None)
     line 133: self.delegation_manager = DelegationManager(agents={})
       (empty agents dict because anthropic_client is None, line 119)
     line 134: self.novelty_detector = NoveltyDetector()
```

[FACT] When `anthropic_client=None` (line 58), the `ResearchWorkflow.__init__` at line 119-131 skips wiring real agents into `DelegationManager`. The condition at line 119 is `if anthropic_client:`.

**GOTCHA**: [FACT] The `artifacts_dir` argument `"./test_artifacts"` at smoke-test.py:40 creates a directory relative to CWD. This is NOT cleaned up after the test.

### Test 3: Provider Modules (line 49-71)

**Call chain**:
```
smoke-test.py:55  from kosmos.core.providers import anthropic_provider
  -> kosmos/core/providers/anthropic.py
     line 14: from anthropic import Anthropic, AsyncAnthropic
smoke-test.py:60  from kosmos.core.providers import openai_provider
  -> kosmos/core/providers/openai.py
     line 13: from openai import OpenAI, AsyncOpenAI
```

[FACT] This test is **lenient**: it returns `True` even if zero providers load (line 71, comment "Not critical"). It only reports which providers are importable.

**GOTCHA**: [FACT] The import names `anthropic_provider` and `openai_provider` at lines 55, 60 are bare module names, but the actual files are `anthropic.py` and `openai.py` under `kosmos/core/providers/`. These imports work because `kosmos.core.providers` is a package, and `from kosmos.core.providers import anthropic_provider` resolves to the module. However, this depends on the `__init__.py` not shadowing these names.

### Test 4: Gap Modules (line 74-96)

**Import targets** (line 78-85):
```
gap1_context    -> kosmos.gaps.context_compression     [DOES NOT EXIST]
gap2_state      -> kosmos.gaps.state_management        [DOES NOT EXIST]
gap3_orchestration -> kosmos.gaps.orchestration         [DOES NOT EXIST]
gap4_execution  -> kosmos.execution.docker_sandbox      [maps to kosmos/execution/sandbox.py]
gap5_skill      -> kosmos.gaps.skill_loading            [DOES NOT EXIST]
gap6_validation -> kosmos.validation.scholar_eval       [EXISTS]
```

[FACT] There is NO `kosmos/gaps/` directory in the codebase. Confirmed by listing `kosmos/` subdirectories -- only these top-level packages exist: `agents, analysis, api, cli, compression, core, db, domains, execution, experiments, hypothesis, knowledge, literature, models, monitoring, orchestration, oversight, safety, utils, validation, workflow, world_model`.

[ABSENCE] `kosmos.gaps` package does not exist. 5 of 6 gap module paths in this test reference non-existent modules. Only `kosmos.validation.scholar_eval` (gap6) exists at the path given.

**GOTCHA**: [FACT] This test requires only 3 of 6 to pass (`return loaded >= 3` at line 96). Since only 1 module (`kosmos.validation.scholar_eval`) actually exists at the specified path, **this test will always fail** unless the threshold was lowered or module paths updated. The actual gap implementations live at:
- Gap 0: `kosmos.compression.compressor` (NOT `kosmos.gaps.context_compression`)
- Gap 1: `kosmos.world_model.artifacts` (NOT `kosmos.gaps.state_management`)
- Gap 2: `kosmos.orchestration` (NOT `kosmos.gaps.orchestration`)
- Gap 3: `kosmos.agents.skill_loader` (NOT `kosmos.gaps.skill_loading`)
- Gap 4: `kosmos.execution.docker_sandbox` might resolve to `kosmos/execution/sandbox.py` but as module name `docker_sandbox` probably fails
- Gap 5: `kosmos.validation.scholar_eval` (correct)

### Test 5: Database Operations (line 124-147)

**Call chain**:
```
smoke-test.py:131  db_path = os.path.join(PROJECT_ROOT, "kosmos.db")
smoke-test.py:133  if not os.path.exists(db_path): return True  [SKIP]
smoke-test.py:136  conn = sqlite3.connect(db_path)
smoke-test.py:138  cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
```

[FACT] This test uses stdlib `sqlite3` directly, bypassing Kosmos's own `kosmos.db` module. It checks for `kosmos.db` at the project root. Returns `True` even if DB is missing (line 133-134, "[SKIP]").

### Test 6: Simple LLM Call (async, line 99-121)

**Call chain**:
```
smoke-test.py:104  client = get_client()  [same singleton as Test 1]
smoke-test.py:112  response = await client.complete("Say 'test ok' and nothing else.")
```

[FACT] `client.complete()` is called but neither `ClaudeClient` nor `LLMProvider` have a `complete()` method. `ClaudeClient` has `generate()`, `generate_with_messages()`, and `generate_structured()`. The `LLMProvider` base at `kosmos/core/providers/base.py` defines abstract `generate()`. This call would raise `AttributeError`.

**GOTCHA**: [FACT] The `test_simple_llm_call()` at line 99 calls `client.complete()` which does not exist on any Kosmos LLM client class. The test catches all exceptions at line 119 and returns `True` (line 121), so it silently passes despite the API mismatch.

---

## 2. Script Smoke Test: `scripts/smoke_test.py:main()`

**File**: `scripts/smoke_test.py`

[FACT] This is a more thorough smoke test at line 200 that runs 7 test groups:
1. **Imports** (line 14): Tests 10 specific class imports from gap modules using correct paths
2. **Compression** (line 43): Exercises `NotebookCompressor._extract_statistics()` and `ContextCompressor.compress_cycle_results()`
3. **State Manager** (line 64): Creates `ArtifactStateManager` in tempdir, saves/retrieves a `Finding`
4. **Orchestration** (line 101): Tests `PlanCreatorAgent._create_mock_plan()`, `PlanReviewerAgent._meets_structural_requirements()`, `NoveltyDetector.check_task_novelty()`
5. **Validation** (line 136): Tests `ScholarEvalValidator.evaluate_finding()` with mock scoring
6. **Skill Loader** (line 182): Tests `SkillLoader(auto_discover=False)` initialization and bundle config
7. **Workflow** (line 161): Runs `ResearchWorkflow.run(num_cycles=1, tasks_per_cycle=5)` -- full cycle

[PATTERN] All 7 groups use the pattern: catch exceptions, print `[OK]`/`[FAIL]`/`[ERROR]`, return bool. (7/7 tests follow this pattern.)

### Key Difference from Template

The script smoke test uses **correct module paths**:
```python
# scripts/smoke_test.py line 19-29 (correct paths):
("kosmos.compression.compressor", "ContextCompressor")
("kosmos.world_model.artifacts", "ArtifactStateManager")
("kosmos.orchestration.plan_creator", "PlanCreatorAgent")
("kosmos.agents.skill_loader", "SkillLoader")
("kosmos.validation.scholar_eval", "ScholarEvalValidator")
("kosmos.workflow.research_loop", "ResearchWorkflow")
```

vs. the template smoke test (line 78-85) which uses non-existent `kosmos.gaps.*` paths.

---

## 3. Pytest Smoke Test: `tests/e2e/test_smoke.py`

**File**: `tests/e2e/test_smoke.py`

Marked with `pytest.mark.e2e` and `pytest.mark.smoke` at line 13.

### Test Methods

| Test | What It Exercises | External Deps |
|------|-------------------|---------------|
| `test_config_loads` (line 19) | `kosmos.config.get_config()` | `.env` file, env vars |
| `test_database_connection` (line 27) | `kosmos.db.init_database()`, `get_session()` | SQLite file |
| `test_neo4j_connection` (line 38) | `kosmos.world_model.factory.get_world_model()` | Neo4j (skipped if no `NEO4J_URI`) |
| `test_metrics_collector_initializes` (line 49) | `kosmos.core.metrics.MetricsCollector()` | None |
| `test_world_model_factory` (line 57) | `kosmos.world_model.in_memory.InMemoryWorldModel()` | None |
| `test_cli_help` (line 67) | `kosmos.cli.main.app` via `CliRunner` | `typer` package |

### conftest.py Infrastructure

[FACT] `tests/e2e/conftest.py` at line 17-19 loads `.env` from project root using `python-dotenv`.

[FACT] Skip decorators defined at lines 56-84:
- `requires_llm`: Skips if no `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- `requires_anthropic`: Skips if no `ANTHROPIC_API_KEY`
- `requires_neo4j`: Skips if no `NEO4J_URI`
- `requires_docker`: Skips if Docker daemon not running
- `requires_full_stack`: Skips if any of LLM+Neo4j+Docker missing

[FACT] `reset_singletons_e2e` fixture at line 321 is `autouse=True`, resets `MetricsCollector` and `WorldModel` singletons after each test.

---

## 4. E2E Runner: Full Gap Coverage

**File**: `.claude/skills/kosmos-e2e-testing/templates/e2e-runner.py`

[FACT] The e2e-runner at line 315 tests all 6 gaps:

| Gap | Test Function | Module Exercised | External Dep |
|-----|---------------|------------------|-------------|
| Full cycle | `test_full_research_cycle()` line 31 | `kosmos.workflow.research_loop.ResearchWorkflow.run()` | LLM provider |
| Gap 0 | `test_context_compression()` line 72 | `kosmos.compression.compressor.ContextCompressor` | None (mock) |
| Gap 1 | `test_state_management()` line 116 | `kosmos.world_model.artifacts.ArtifactStateManager` | Filesystem (tempdir) |
| Gap 2 | `test_plan_creator()` line 246 | `kosmos.orchestration.plan_creator.PlanCreatorAgent` | None (mock) |
| Gap 3 | `test_skill_loader()` line 284 | `kosmos.agents.skill_loader.SkillLoader` | None |
| Gap 4 | `test_code_execution()` line 157 | `kosmos.execution.production_executor.ProductionExecutor` | Docker daemon + kosmos-sandbox:latest |
| Gap 5 | `test_scholar_evaluation()` line 210 | `kosmos.validation.scholar_eval.ScholarEvalValidator` | None (mock) |

[FACT] The e2e-runner uses `provider_detector.detect_all()` at line 323 for infrastructure detection before running. It uses `recommend_test_tier()` at line 324 to report capabilities.

**GOTCHA**: [FACT] Gap 4 test at line 157 requires Docker with `kosmos-sandbox:latest` image. Without Docker, it catches the Docker error at line 203 and returns `True` (skip). The `ProductionExecutor` at `kosmos/execution/production_executor.py:33` imports `DockerManager`, `JupyterClient`, and `PackageResolver`.

---

## 5. Benchmark Template

**File**: `.claude/skills/kosmos-e2e-testing/templates/benchmark.py`

[FACT] At line 160, `main()` uses `provider_detector.detect_all()` to find available providers, then benchmarks each with 4 standardized prompts (lines 22-43). Calls `config_manager.switch_provider()` at line 59 to swap env vars per provider.

---

## 6. Skill Lib: Supporting Infrastructure

### provider_detector.py

[FACT] `detect_all()` at line 226 checks 11 infrastructure components:
- Ollama (HTTP to localhost:11434, line 17-25)
- Docker (subprocess `docker info`, line 43-53)
- Docker sandbox image (subprocess `docker images -q`, line 56-66)
- Neo4j (socket connect to bolt port, line 75-101)
- Redis (socket connect, line 104-128)
- ChromaDB (Python import, line 131-138)
- Semantic Scholar API key (env var, line 143)
- Python packages: arxiv, scipy, matplotlib, plotly, pandas, numpy, chromadb, neo4j, redis (line 146-172)

**GOTCHA**: [FACT] `check_ollama()` at line 17 has a 5-second HTTP timeout. `check_docker()` at line 43 has a 10-second subprocess timeout. These can block the test runner.

### config_manager.py

[FACT] `switch_provider()` at line 52 **mutates `os.environ`** by loading key-value pairs from `.env` config files under `configs/`. This is a global side effect that persists beyond the test.

### test_runner.py

[FACT] `run_tests()` at line 56 builds a `pytest` command and runs it via `subprocess.run()`. It maps test tiers to directory paths (line 22-53):
- sanity -> `tests/smoke/`
- smoke -> `tests/unit/` + `tests/smoke/`
- integration -> `tests/integration/`
- e2e -> `tests/e2e/`
- full -> `tests/`

---

## 7. Environment Variables & Setup Requirements

### Required for Template Smoke Test to Pass

| Requirement | Needed By | Consequence If Missing |
|-------------|-----------|----------------------|
| `ANTHROPIC_API_KEY` or provider config | Test 1 (LLM init) | FAIL: ValueError |
| `anthropic` pip package | Test 1, Test 3 | FAIL: ImportError |
| Project root in `sys.path` | All tests | FAIL: ImportError for kosmos |
| `kosmos.db` file (optional) | Test 5 | SKIP (returns True) |
| LLM provider accessible | Test 6 | SKIP (returns True) |

### Required for Full E2E Runner

| Requirement | Gap | Consequence If Missing |
|-------------|-----|----------------------|
| LLM provider (Ollama/API key) | Full cycle, Gap 2 | FAIL |
| Docker + kosmos-sandbox:latest | Gap 4 | SKIP |
| `NEO4J_URI` | Neo4j tests | SKIP |
| `REDIS_URL` | Redis tests | SKIP |
| `SEMANTIC_SCHOLAR_API_KEY` | Literature search | N/A (not in smoke) |
| `pydantic`, `pydantic-settings` | Config loading | FAIL |
| `typer` | CLI test | FAIL |
| `python-dotenv` | conftest.py | FAIL |

### Config Files

[FACT] Provider configs at `.claude/skills/kosmos-e2e-testing/configs/`:
- `local-fast.env`: Sets `LLM_PROVIDER=openai`, `OPENAI_BASE_URL=http://localhost:11434/v1`, `OPENAI_MODEL=qwen3:4b`
- `local-reasoning.env`: Same pattern with `deepseek-r1:8b`
- `anthropic.env`: Sets `ANTHROPIC_API_KEY`
- `openai.env`: Sets `OPENAI_API_KEY`
- `full.env`: All providers configured

---

## 8. Critical Gotchas Summary

1. **[FACT] Stale gap module paths**: Template smoke test `test_gap_modules()` at `smoke-test.py:74-96` references `kosmos.gaps.*` modules that do not exist. Only 1 of 6 paths resolves. Threshold of 3 means this test always fails. The script smoke test at `scripts/smoke_test.py` uses correct paths.

2. **[FACT] API mismatch**: Template smoke test `test_simple_llm_call()` at line 112 calls `client.complete()` which is not a method on `ClaudeClient` or `LLMProvider`. The method is `generate()`. Error is silently swallowed.

3. **[FACT] Global env mutation**: `config_manager.switch_provider()` at line 52 modifies `os.environ` permanently within the process. Tests that call this affect subsequent tests.

4. **[FACT] Singleton not reset**: `get_client()` at `kosmos/core/llm.py:613` returns a global singleton. Switching providers via env vars after first call has no effect unless `get_client(reset=True)` is called.

5. **[FACT] Docker timeout**: Provider detection (`provider_detector.py:43`) runs `docker info` with 10-second timeout. On systems where Docker is installed but daemon is stopped, this adds 10 seconds of blocking.

6. **[FACT] Artifact directory leak**: Template smoke test creates `./test_artifacts` at CWD-relative path (line 40) and never cleans it up.

7. **[FACT] Python 3.11+ incompatibility**: `provider_detector.py:189-195` explicitly warns that `arxiv` package fails on Python 3.11+ due to `sgmllib3k` dependency.

8. **[FACT] No `kosmos.gaps` package**: The entire `kosmos.gaps` namespace referenced in the template smoke test is an artifact of earlier design. The actual gap implementations are spread across `kosmos.compression`, `kosmos.world_model`, `kosmos.orchestration`, `kosmos.agents`, `kosmos.execution`, and `kosmos.validation`.

---

## 9. Kosmos Modules Exercised by E2E Tests (Combined)

[PATTERN] Across all 5 test templates plus the pytest smoke test, these kosmos modules are exercised (observed in 3+ test files):

| Module | Exercised By | Count |
|--------|-------------|-------|
| `kosmos.core.llm.get_client` | smoke-test, e2e-runner, benchmark | 3 |
| `kosmos.workflow.research_loop.ResearchWorkflow` | smoke-test, workflow-test, e2e-runner, scripts/smoke_test | 4 |
| `kosmos.config.get_config` / `get_settings` | sanity-test, test_smoke.py, scripts/smoke_test | 3 |
| `kosmos.validation.scholar_eval.ScholarEvalValidator` | e2e-runner, scripts/smoke_test, smoke-test (via gap) | 3 |
| `kosmos.compression.compressor.ContextCompressor` | e2e-runner, scripts/smoke_test | 2 |
| `kosmos.world_model.artifacts.ArtifactStateManager` | e2e-runner, scripts/smoke_test | 2 |
| `kosmos.orchestration.plan_creator.PlanCreatorAgent` | e2e-runner, scripts/smoke_test | 2 |
| `kosmos.agents.skill_loader.SkillLoader` | e2e-runner, scripts/smoke_test | 2 |
| `kosmos.execution.production_executor.ProductionExecutor` | e2e-runner | 1 |
| `kosmos.core.metrics.MetricsCollector` | test_smoke.py | 1 |
| `kosmos.cli.main.app` | test_smoke.py | 1 |
| `kosmos.db.init_database` | test_smoke.py | 1 |
# Module Deep Read: kosmos/execution/code_generator.py

**Risk**: 0.67 | **Lines**: 995 | **Churn**: high

## What It Does

Translates `ExperimentProtocol` Pydantic models into executable Python code strings via a three-tier fallback: template matching first, LLM generation second, a bare-minimum basic template third. The generated code is meant to be `exec()`'d by `CodeExecutor` in a sandbox (or locally), and must assign a `results` dict that downstream consumers (research_director) parse for p-values, effect sizes, and statistical test outputs.

## Non-Obvious Details

### Prompt construction (LLM path)

[FACT] `_create_code_generation_prompt()` (line 858-905) constructs a prompt by serializing protocol steps, variables, and statistical tests into a plain-text prompt. It does NOT use the `EXPERIMENT_DESIGNER` prompt template imported at line 20 -- that import is unused in the module. The prompt instructs the LLM to use `data_path` as a pre-existing variable, and explicitly says "Return ONLY the Python code, no explanations." There is no system prompt or temperature setting passed; those defaults come from whatever `self.llm_client.generate()` uses.

### Code extraction from LLM response

[FACT] `_extract_code_from_response()` (line 907-924) uses a naive string search for triple-backtick fences. It takes the first `\`\`\`python` block, or failing that the first `\`\`\`` block, or treats the entire response as code. If the LLM returns multiple code blocks, only the first is extracted. If the LLM includes text after the closing fence, it is silently dropped.

### Validation is syntax-only

[FACT] `_validate_syntax()` (line 981-989) calls `ast.parse(code)` and raises `ValueError` on failure. It does NOT check for unsafe operations, import safety, or whether `results` is actually assigned. The CodeValidator in `kosmos.safety.code_validator` is not invoked here -- that happens in the executor layer.

### Template ordering matters -- first match wins

[FACT] `_match_template()` (line 835-840) iterates `self.templates` in registration order and returns the first match. The template list at line 787-793 is ordered: TTest, Correlation, LogLog, ML, GenericComputational. The `GenericComputationalCodeTemplate` is a catch-all (matches both `COMPUTATIONAL` and `DATA_ANALYSIS`, line 559-564), so it will absorb any DATA_ANALYSIS or COMPUTATIONAL protocol that didn't match the three specific templates above it. LITERATURE_SYNTHESIS protocols fall through all templates and go to LLM or basic fallback.

### Generated code uses `'data_path' in dir()` as a probe

[PATTERN] All 4 specific templates (TTest line 113, Correlation line 246, LogLog line 383, ML line 476) and the generic template (line 593) check `if 'data_path' in dir() and data_path:` to decide whether to load from file or generate synthetic data. This means the code works in two modes: with real data (when the executor injects `data_path`) or with synthetic data as a fallback. The basic template (line 964) does NOT have this fallback -- it calls `pd.read_csv(data_path)` unconditionally, which will crash if `data_path` is not defined.

### `figure_path` is another injected variable

[PATTERN] All 5 templates check `if 'figure_path' in dir() and figure_path:` before generating figures. This variable is injected by the caller (research_director or executor), but the code_generator never validates or documents this contract explicitly.

### Synthetic data encodes specific statistical properties

[FACT] The TTest template (line 124) generates synthetic data where the experimental group's mean is offset by `effect_size` (defaulting to 0.0, meaning the null hypothesis is true by default). The Correlation template (line 258) generates data with r~0.89 (0.5x + noise(0,0.5)). The LogLog template (line 395) encodes an exponent of 0.75. These are not configurable beyond what the protocol carries.

### LLM client initialization has a two-stage fallback

[FACT] The constructor (line 761-778) tries `ClaudeClient()` first, and if that fails, falls back to `LiteLLMProvider` using the active provider config. If both fail, `use_llm` is silently set to False and template-only mode is used. This means code_generator can degrade gracefully but the caller has no way to know LLM was disabled except via logs.

## Blast Radius (What Breaks If You Change It)

1. **research_director.py** (line 1528, 1538, 1564): `_handle_execute_experiment_action()` calls `ExperimentCodeGenerator(use_templates=True, use_llm=True)` then `.generate(protocol)`. Changes to the `generate()` signature, return format, or the shape of the `results` dict will break experiment execution.

2. **executor.py** (line 653-660): `execute_with_data()` prepends `data_path = ...` to the generated code. If template code changes how it references `data_path`, the data loading contract breaks.

3. **Figure generation**: All templates import `kosmos.analysis.visualization.PublicationVisualizer` and `kosmos.execution.data_analysis.DataAnalyzer` in the generated code strings. If those APIs change, the generated code will fail at exec-time, not at generation-time.

4. **Test suite**: `tests/unit/execution/test_code_generator.py` (584 lines) tests template matching, code generation, LLM fallback, validation, and variable extraction. `tests/integration/test_figure_generation.py` tests individual templates. `tests/integration/test_execution_pipeline.py` and `tests/e2e/test_system_sanity.py` also import from this module.

5. **evaluation/**: `run_phase2_tests.py` (line 218) imports `TTestComparisonCodeTemplate` directly.

## Runtime Dependencies

| Dependency | Import Location | Purpose |
|---|---|---|
| `kosmos.models.experiment.ExperimentProtocol` | line 17 | Input type for all generation |
| `kosmos.models.experiment.ExperimentType` | line 17 | Template matching |
| `kosmos.models.hypothesis.Hypothesis` | line 18 | Imported but NOT used in module |
| `kosmos.core.llm.ClaudeClient` | line 19 | LLM generation (primary) |
| `kosmos.core.prompts.EXPERIMENT_DESIGNER` | line 20 | **Imported but NOT used** |
| `kosmos.core.providers.litellm_provider.LiteLLMProvider` | line 768 (lazy) | LLM fallback provider |
| `kosmos.config.get_config` | line 769 (lazy) | Config for LiteLLM fallback |
| `ast` (stdlib) | line 12 | Syntax validation |

**In generated code** (exec-time, not import-time):
- `pandas`, `numpy`, `scipy.stats` -- all templates
- `kosmos.execution.data_analysis.DataAnalyzer` -- TTest, Correlation, LogLog, Generic templates
- `kosmos.execution.data_analysis.DataCleaner` -- LogLog template only
- `kosmos.execution.ml_experiments.MLAnalyzer` -- ML template only
- `kosmos.analysis.visualization.PublicationVisualizer` -- all templates
- `sklearn.model_selection`, `sklearn.linear_model`, `sklearn.datasets` -- ML template only

## Public API

### Class: `ExperimentCodeGenerator`

#### `__init__(use_templates=True, use_llm=True, llm_enhance_templates=False, llm_client=None)`
- **Behavior**: Registers 5 code templates (if enabled), initializes LLM client with ClaudeClient -> LiteLLM -> disabled fallback chain.
- **Preconditions**: None strict; works with all flags False.
- **Side effects**: May instantiate `ClaudeClient()` or `LiteLLMProvider()`, which may read API keys or config. Logs warnings if LLM init fails.
- **Error behavior**: Catches all exceptions from LLM client init; degrades to template-only silently.

#### `generate(protocol: ExperimentProtocol) -> str`
- **Behavior**: Three-tier code generation: (1) template match, (2) LLM generation, (3) basic fallback. Always validates syntax via `ast.parse()` before returning.
- **Preconditions**: `protocol` must be a valid `ExperimentProtocol` with populated `experiment_type`. Variables and statistical_tests can be empty (defaults used).
- **Side effects**: If LLM path taken, makes a network call to Claude API or LiteLLM backend. Logs info/warning messages.
- **Error behavior**: LLM failures caught and logged; falls through to basic template. Syntax validation failure raises `ValueError`. Never returns None -- always produces some code string.

#### `save_code(code: str, file_path: str) -> None`
- **Behavior**: Writes code string to a file.
- **Preconditions**: `file_path` parent directory must exist.
- **Side effects**: Creates/overwrites file on disk.
- **Error behavior**: Propagates `IOError` from file write.

### Class: `CodeTemplate` (base)

#### `matches(protocol) -> bool`
- **Behavior**: Returns True if template handles this protocol type. Base implementation checks `experiment_type` equality.

#### `generate(protocol) -> str`
- **Behavior**: Produces Python code string. Base raises `NotImplementedError`.

### Template subclasses (all follow same pattern):

| Template | Matches When | Key Generated Imports |
|---|---|---|
| `TTestComparisonCodeTemplate` | DATA_ANALYSIS + t_test in statistical_tests | DataAnalyzer.ttest_comparison |
| `CorrelationAnalysisCodeTemplate` | DATA_ANALYSIS + correlation/regression in tests or name | DataAnalyzer.correlation_analysis |
| `LogLogScalingCodeTemplate` | name/description contains scaling/power law/log-log | DataAnalyzer.log_log_scaling_analysis |
| `MLExperimentCodeTemplate` | COMPUTATIONAL + ML keywords in name/description | MLAnalyzer.run_experiment |
| `GenericComputationalCodeTemplate` | COMPUTATIONAL or DATA_ANALYSIS (catch-all) | scipy.stats, scipy.optimize.curve_fit |

## Gotchas

1. **[FACT] Unused import**: `EXPERIMENT_DESIGNER` is imported at line 20 but never referenced anywhere in the module. The LLM prompt is constructed inline at line 875-903 without using this template. This could mislead someone into thinking the prompt template is being used.

2. **[FACT] Unused import**: `Hypothesis` is imported at line 18 but never used in any function or method.

3. **[FACT] Basic template crashes without data_path**: The `_generate_basic_template()` method (line 964) emits `pd.read_csv(data_path)` unconditionally without the `if 'data_path' in dir()` guard that all other templates use. If this fallback is triggered without executor-injected data_path, the generated code will NameError at runtime.

4. **[FACT] Template match order is load-bearing**: `GenericComputationalCodeTemplate.matches()` returns True for both COMPUTATIONAL and DATA_ANALYSIS (line 561-564). It is registered last (line 792). If someone reorders the template list or adds a new template after it, the generic will shadow it for those two experiment types.

5. **[FACT] Generated code uses `'figure_path' in dir()` pattern**: This Python anti-pattern (checking `dir()` instead of using function parameters) couples the generated code to specific variable names that the executor must inject. The contract is implicit and undocumented.

6. **[FACT] LLM code extraction is fragile**: `_extract_code_from_response()` (line 910-913) searches for the literal string `\`\`\`python` then finds the next `\`\`\``. If the LLM response contains nested code blocks or markdown formatting inside the code, the extraction will produce broken code. There is no retry or repair logic for this case.

7. **[FACT] No security validation in code_generator**: `_validate_syntax()` only checks `ast.parse()` (line 984). The LLM could generate code with `os.system()`, `subprocess.run()`, file deletion, or network access. Safety enforcement is deferred entirely to the executor/sandbox layer. If the executor's CodeValidator is bypassed, arbitrary code runs.

8. **[FACT] Effect size defaults to 0.0 in TTest template**: Line 93 sets `effect_size = 0.0` as default, meaning synthetic data encodes the null hypothesis (no difference between groups). This will produce non-significant p-values by design, which might confuse users expecting a demonstration of a significant result.
# Module Deep Read: `kosmos/safety/code_validator.py`

## What This Module Does

CodeValidator is a static analysis gate that validates LLM-generated Python code before execution, checking for dangerous imports, dangerous function calls, file/network access policy violations, dunder attribute access, and ethical research guideline compliance. It produces a SafetyReport that determines whether code is safe to execute, what risk level it carries, and whether human approval is required.

## Non-Obvious Behaviors

### What It Catches

- [FACT] **AST-level import detection with string-match fallback**: If code has a SyntaxError, `_check_dangerous_imports` (line 271-280) falls back from AST parsing to naive string matching (`if f"import {module}" in code`). This fallback is intentional resilience but uses less precise detection.
- [FACT] **Reflection/dunder access via AST**: `_check_ast_calls` (lines 322-375) catches `getattr()`, `setattr()`, `delattr()` calls and access to `__dict__`, `__class__`, `__builtins__`, `__subclasses__` via AST walking. This is the deepest layer of static analysis.
- [FACT] **Ethical keyword scanning combines code AND context**: `_check_ethical_guidelines` (lines 386-418) lowercases both the source code and the `context` dict (specifically `context['description']` or `context['hypothesis']`) and scans for keyword matches. This means ethical flags trigger from experiment metadata, not just code.
- [FACT] **File write mode detection is string-based**: Lines 296-297 check for write modes by looking for literal strings `'w'`, `'a'`, `'x'`, `mode='w'`, `mode="w"` anywhere in the entire code string, not scoped to the `open()` call. A comment containing `'w'` could trigger a false positive, or a variable-based mode (`mode=m`) would evade detection.

### What It Misses (Security-Relevant Gaps)

- [FACT] **No detection of `importlib` usage via already-imported modules**: The DANGEROUS_MODULES list (line 35) includes `'importlib'` as a string, but code like `import importlib; importlib.import_module('os')` is caught at the import level. However, if `importlib` were somehow already available in the execution namespace, calling `importlib.import_module()` would not be caught by `_check_dangerous_patterns`.
- [FACT] **`_check_dangerous_patterns` is pure string matching** (lines 283-320): It searches the entire code string for patterns like `'eval('`, `'exec('`. This means:
  - A variable named `my_eval(` would trigger a false positive.
  - Obfuscated calls like `e = eval; e(code)` or `getattr(builtins, 'eval')` — the `getattr` would be caught by `_check_ast_calls`, but splitting `eval` across variables would not.
  - String content like `"don't use eval("` in a docstring triggers false positives.
- [FACT] **`open(` pattern is substring-matched globally** (line 291): The check `if pattern in code` matches `open(` anywhere, including in comments, strings, or unrelated function names containing "open(" (e.g., `reopen(`).
- [FACT] **Network check is warning-only** (lines 377-384): `_check_network_operations` returns only warnings (string list), never violations. Network usage alone never blocks execution. The actual blocking comes from the import-level check catching `requests`, `urllib`, etc.
- [FACT] **No detection of `ctypes`, `cffi`, or `multiprocessing`**: These modules are absent from DANGEROUS_MODULES (lines 35-39). Code importing `ctypes` could call arbitrary C functions. `multiprocessing` could spawn processes.
- [FACT] **`pathlib` is not flagged**: `pathlib.Path.write_text()` or `pathlib.Path.unlink()` would bypass the file operation check entirely since only `open(` is pattern-matched.
- [ABSENCE] **No check for `breakpoint()`, `pdb`, or `code.interact()`**: Searched DANGEROUS_PATTERNS and DANGEROUS_MODULES; debugger access is not blocked.
- [ABSENCE] **No AST check for `ast.literal_eval` bypass or f-string injection**: Only literal string patterns are checked.

### Ethical Guideline System Nuances

- [FACT] The default guidelines (lines 109-157) use keyword-based validation only (`validation_method="keyword"`). The `EthicalGuideline` model (in `kosmos/models/safety.py:123`) supports `"llm"` and `"manual"` validation methods, but `_check_ethical_guidelines` (line 402) only implements `"keyword"`. Guidelines with other validation methods are silently skipped.
- [FACT] Ethical keyword matching is case-insensitive (line 395: `text_to_check = code.lower()`) and triggers on the first keyword match per guideline, then breaks (line 417: `break`). Only one violation per guideline is reported even if multiple keywords match.
- [FACT] Non-required guidelines (`required=False`, like the "environmental" guideline at line 149) are checked but never generate violations (line 406: `if guideline.required:`). They are effectively dead code in the current default set.

## Blast Radius: Who Calls This

### Direct Callers (Production Code)

1. **`kosmos/safety/guardrails.py:65`** [FACT]: `SafetyGuardrails.__init__` creates a `CodeValidator` instance and calls `self.code_validator.validate(code, context)` at line 134. This is the primary integration point. SafetyGuardrails adds emergency stop checks around validation.
2. **`kosmos/execution/executor.py:1040`** [FACT]: The `execute_protocol_code()` convenience function creates `CodeValidator(allow_file_read=True)` and validates before execution. Comment says "F-21: removed validate_safety bypass" -- meaning this was hardened to always validate.
3. **`kosmos/execution/executor.py:664`** [FACT]: Re-exports `CodeValidator` for backward compatibility (`from kosmos.safety.code_validator import CodeValidator  # noqa: F811,F401`).
4. **`kosmos/safety/__init__.py:3`** [FACT]: Re-exports `CodeValidator` as a public API.

### Indirect Callers

- `SafetyGuardrails.validate_code()` is called by any code that goes through the guardrails safety context.
- `execute_protocol_code()` is the convenience entry point for the execution pipeline.

### Test Coverage

- [FACT] **42 test instantiations** of `CodeValidator` in `tests/unit/safety/test_code_validator.py` (690 lines).
- [FACT] Additional tests in `tests/unit/execution/test_executor.py`, `tests/e2e/test_system_sanity.py`, and multiple requirement tests under `tests/requirements/`.

## Runtime Dependencies

| Dependency | Import Location | Purpose |
|------------|----------------|---------|
| `ast` (stdlib) | Lines 11, 251 | Python AST parsing for import/call analysis |
| `json` (stdlib) | Line 12 | Loading ethical guidelines from JSON files |
| `logging` (stdlib) | Line 13 | Logging validation results |
| `pathlib.Path` (stdlib) | Line 14 | Checking if guidelines file exists |
| `kosmos.models.safety` | Lines 17-19 | SafetyReport, SafetyViolation, ViolationType, RiskLevel, EthicalGuideline, ApprovalRequest, ApprovalStatus |
| `kosmos.utils.compat.model_to_dict` | Line 21 | Serializing Pydantic models to dicts (used in `create_approval_request`) |
| `kosmos.config.get_config` | Line 22 | Reading `config.safety.require_human_approval` in `requires_approval()` |
| `uuid` (stdlib) | Line 484 (lazy import) | Generating approval request IDs |

No external (pip) dependencies. All stdlib + kosmos internal.

## Public API: Function-by-Function

### `CodeValidator.__init__(ethical_guidelines_path, allow_file_read, allow_file_write, allow_network)`
- **Behavior**: Initializes validator with permission flags and loads ethical guidelines from file or defaults.
- **Preconditions**: None strict. `ethical_guidelines_path` can be None or a nonexistent path (falls back to defaults silently).
- **Side effects**: Reads a JSON file from disk if `ethical_guidelines_path` is provided and exists. Logs initialization info.
- **Error behavior**: If guidelines file fails to parse, catches exception, logs error, falls back to defaults. Never raises.

### `CodeValidator.validate(code, context) -> SafetyReport`
- **Behavior**: Runs 6 check stages in order: syntax, dangerous imports, dangerous patterns, network operations, AST call analysis, ethical guidelines. Assesses overall risk level. Returns SafetyReport.
- **Preconditions**: `code` must be a string. `context` is optional dict.
- **Side effects**: None (pure analysis). Logs the report summary.
- **Error behavior**: Individual checks are resilient -- syntax errors cause AST-based checks to degrade to string matching or skip. Never raises.
- **Return**: SafetyReport with `passed=True` only if zero violations. Risk level is the max severity of any violation.

### `CodeValidator.requires_approval(report) -> bool`
- **Behavior**: Checks config and report to decide if human approval is needed.
- **Preconditions**: `report` must be a SafetyReport. Calls `get_config()` at runtime.
- **Side effects**: Reads global config via `get_config()`.
- **Error behavior**: If config is misconfigured, `get_config()` may raise. Not handled here.
- **Return**: True if any of: config.safety.require_human_approval is True, risk is HIGH/CRITICAL, critical violations exist, or ethical violations exist.

### `CodeValidator.create_approval_request(code, report, context) -> ApprovalRequest`
- **Behavior**: Builds an ApprovalRequest object with a unique ID, violation descriptions, and truncated code (first 500 chars).
- **Preconditions**: `report` must be a SafetyReport (may have zero violations).
- **Side effects**: Imports `uuid` on first call (lazy import at line 484). Calls `model_to_dict(report)` which serializes the entire report into the request context.
- **Error behavior**: No explicit error handling. Could fail if `model_to_dict` raises on unusual report content.

### Private Methods (Internal API)

| Method | Lines | Behavior |
|--------|-------|----------|
| `_load_ethical_guidelines(path)` | 87-107 | Loads from JSON or returns defaults. Silent fallback on error. |
| `_get_default_ethical_guidelines()` | 109-157 | Returns 5 hardcoded guidelines: no_harm, privacy, informed_consent, animal_welfare, environmental. |
| `_check_syntax(code)` | 233-245 | Calls `ast.parse()`. Returns violation with line number on SyntaxError. |
| `_check_dangerous_imports(code)` | 247-281 | AST-walks for Import/ImportFrom nodes, checks against DANGEROUS_MODULES. Falls back to string match on SyntaxError. |
| `_check_dangerous_patterns(code)` | 283-320 | String-searches for dangerous patterns. Special-cases `open(` based on permission flags. Returns (violations, warnings) tuple. |
| `_check_ast_calls(code)` | 322-375 | AST-walks for dangerous function calls (getattr/setattr/delattr) and dunder attribute access. |
| `_check_network_operations(code)` | 377-384 | Case-insensitive string search for network keywords. Warnings only, never violations. |
| `_check_ethical_guidelines(code, context)` | 386-418 | Keyword matching against combined code+context text. Only processes `keyword` validation method. |
| `_assess_risk_level(violations)` | 421-434 | Returns max severity across all violations, or LOW if none. |

## Gotchas (Security-Relevant)

1. **[FACT, file:291-304] `open(` write-mode detection is globally string-matched**: `any(mode in code for mode in ["'w'", "'a'", ...])` searches the entire source. A comment `# don't use 'w' mode` would trigger a false violation. Conversely, `open(f, mode_var)` where `mode_var = 'w'` would evade detection.

2. **[FACT, file:271-280] SyntaxError fallback uses naive string matching**: When code has syntax errors, dangerous import detection falls back to `f"import {module}" in code`. This matches inside strings, comments, and multi-line contexts. Example: `s = "do not import os"` would trigger a violation during fallback.

3. **[FACT, file:35-39] Missing dangerous modules**: `ctypes`, `cffi`, `multiprocessing`, `threading`, `signal`, `atexit`, `gc`, `inspect`, and `code` are not in DANGEROUS_MODULES. These could be used for sandbox escape, arbitrary code execution, or resource manipulation.

4. **[FACT, file:322-375] `_check_ast_calls` catches `getattr`/`setattr`/`delattr` but the DANGEROUS_PATTERNS list (line 48-49) also string-matches `delattr(` and `setattr(`**: This creates duplicate detection -- AST check catches them as CRITICAL, and string check also catches them as CRITICAL. Both violations appear in the report.

5. **[FACT, file:402] Only `"keyword"` validation method is implemented**: The EthicalGuideline model supports `"llm"` and `"manual"` methods, but guidelines using those methods produce no violations and no warnings. A custom guidelines file specifying `validation_method: "llm"` would silently pass all ethical checks.

6. **[FACT, file:446-449] `requires_approval` calls `get_config()` at invocation time, not at init time**: This means the config can change between validation and approval checking. If config is modified at runtime, approval behavior changes without re-validation.

7. **[FACT, file:86-94 of executor.py] Defense in depth**: Even if CodeValidator misses something, the executor has a secondary defense: restricted builtins (SAFE_BUILTINS at executor.py:43-83) and a restricted `__import__` function (executor.py:97-110) that only allows scientific modules. The CodeValidator is the first gate; the executor's restricted namespace is the second.

## Relationship to Other Safety Modules

| Module | Relationship |
|--------|-------------|
| `guardrails.py` | Wraps CodeValidator; adds emergency stop, resource limits, incident logging |
| `verifier.py` | Independent: validates experiment *results* (post-execution), not code (pre-execution) |
| `reproducibility.py` | Independent: manages seeds and environment snapshots, no code validation |
| `models/safety.py` | Defines all data models: SafetyReport, SafetyViolation, RiskLevel, ViolationType, EthicalGuideline, ApprovalRequest |

## Architecture Summary

```
Code string + context
       |
       v
  CodeValidator.validate()
       |
       +-- _check_syntax           (ast.parse)
       +-- _check_dangerous_imports (AST walk -> string fallback)
       +-- _check_dangerous_patterns (string matching)
       +-- _check_network_operations (string matching, warnings only)
       +-- _check_ast_calls         (AST walk: reflection + dunders)
       +-- _check_ethical_guidelines (keyword matching code + context)
       +-- _assess_risk_level       (max severity)
       |
       v
  SafetyReport
       |
       +-- requires_approval() -> bool (config + risk + violations)
       +-- create_approval_request() -> ApprovalRequest
```
# Module Deep Read: kosmos/config.py

**File**: `/mnt/c/python/kosmos/kosmos/config.py` (1160 lines)
**Risk**: 0.96 (highest churn file in the codebase)
**Role**: Central configuration hub — every major subsystem depends on it

## What This Module Does

[FACT: file:1-6] Pydantic-Settings-based configuration management that loads all Kosmos settings from environment variables and `.env` files, validates them with type constraints, and exposes them as a singleton `KosmosConfig` instance via `get_config()`. Every subsystem in Kosmos (LLM providers, database, safety, research, literature, knowledge graph, caching, logging) obtains its settings through this single module.

## Configuration Hierarchy

[FACT: file:978-983] `KosmosConfig` uses `pydantic_settings.BaseSettings` with this load order:
1. **Environment variables** (highest priority)
2. **`.env` file** at `Path(__file__).parent.parent / ".env"` (i.e., project root)
3. **Field defaults** in each config class (lowest priority)

**Critical subtlety**: [FACT: file:978-983 vs file:84,140,247,...] Only `KosmosConfig` and `LiteLLMConfig` (file:192-197) declare `env_file` in their `SettingsConfigDict`. The 13 other sub-config classes (`ClaudeConfig`, `OpenAIConfig`, `ResearchConfig`, `DatabaseConfig`, etc.) only set `populate_by_name=True` — they rely on the parent `KosmosConfig` to inject values, NOT on their own `.env` file loading. This means instantiating a sub-config class directly (e.g., `ClaudeConfig()`) will only read environment variables, NOT the `.env` file.

## All Configuration Classes and Their Keys

### ClaudeConfig (alias: AnthropicConfig) — file:29-88
LLM provider settings for Anthropic Claude.

| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `ANTHROPIC_API_KEY` | `api_key` | **required** | — |
| `CLAUDE_MODEL` | `model` | `"claude-sonnet-4-5"` | — |
| `CLAUDE_MAX_TOKENS` | `max_tokens` | `4096` | 1-200000 |
| `CLAUDE_TEMPERATURE` | `temperature` | `0.7` | 0.0-1.0 |
| `CLAUDE_ENABLE_CACHE` | `enable_cache` | `True` | — |
| `CLAUDE_BASE_URL` | `base_url` | `None` | — |
| `CLAUDE_TIMEOUT` | `timeout` | `120` | 1-600 |

[FACT: file:88] `AnthropicConfig = ClaudeConfig` — a simple alias. Both names refer to the same class.

[FACT: file:79-82] `is_cli_mode` property: returns `True` when `api_key` is all 9s (`api_key.replace('9', '') == ''`). This is the "CLI mode" that routes to a local Claude Code CLI proxy instead of the Anthropic API. This is the default in `.env.example` (line 24: `ANTHROPIC_API_KEY=999999999999999999999999999999999999999999999999`).

### OpenAIConfig — file:91-140
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `OPENAI_API_KEY` | `api_key` | **required** | — |
| `OPENAI_MODEL` | `model` | `"gpt-4-turbo"` | — |
| `OPENAI_MAX_TOKENS` | `max_tokens` | `4096` | 1-128000 |
| `OPENAI_TEMPERATURE` | `temperature` | `0.7` | 0.0-2.0 |
| `OPENAI_BASE_URL` | `base_url` | `None` | — |
| `OPENAI_ORGANIZATION` | `organization` | `None` | — |
| `OPENAI_TIMEOUT` | `timeout` | `120` | 1-600 |

### LiteLLMConfig — file:143-197
Universal provider via LiteLLM (supports Ollama, DeepSeek, Azure, Bedrock, etc.).

| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `LITELLM_MODEL` | `model` | `"gpt-3.5-turbo"` | — |
| `LITELLM_API_KEY` | `api_key` | `None` | — |
| `LITELLM_API_BASE` | `api_base` | `None` | — |
| `LITELLM_MAX_TOKENS` | `max_tokens` | `4096` | 1-128000 |
| `LITELLM_TEMPERATURE` | `temperature` | `0.7` | 0.0-2.0 |
| `LITELLM_TIMEOUT` | `timeout` | `120` | 1-600 |

[FACT: file:192-197] This is the only sub-config besides `KosmosConfig` that declares its own `env_file` for `.env` loading.

### ResearchConfig — file:200-247
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `MAX_RESEARCH_ITERATIONS` | `max_iterations` | `10` | 1-100 |
| `ENABLED_DOMAINS` | `enabled_domains` | `["biology","physics","chemistry","neuroscience"]` | comma-separated |
| `ENABLED_EXPERIMENT_TYPES` | `enabled_experiment_types` | `["computational","data_analysis","literature_synthesis"]` | comma-separated |
| `MIN_NOVELTY_SCORE` | `min_novelty_score` | `0.6` | 0.0-1.0 |
| `ENABLE_AUTONOMOUS_ITERATION` | `enable_autonomous_iteration` | `True` | — |
| `RESEARCH_BUDGET_USD` | `budget_usd` | `10.0` | >= 0 |
| `MAX_RUNTIME_HOURS` | `max_runtime_hours` | `12.0` | 0.1-24.0 |

### DatabaseConfig — file:250-302
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `DATABASE_URL` | `url` | `"sqlite:///kosmos.db"` | — |
| `DATABASE_ECHO` | `echo` | `False` | — |

[FACT: file:264-300] `normalized_url` property converts relative SQLite paths to absolute paths based on `Path(__file__).parent.parent` (project root). This means `sqlite:///kosmos.db` becomes `sqlite:///abs/path/to/kosmos/kosmos.db`. The `is_sqlite` property checks if URL starts with "sqlite".

### RedisConfig — file:305-362
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `REDIS_URL` | `url` | `"redis://localhost:6379/0"` | — |
| `REDIS_ENABLED` | `enabled` | `False` | — |
| `REDIS_MAX_CONNECTIONS` | `max_connections` | `50` | 1-1000 |
| `REDIS_SOCKET_TIMEOUT` | `socket_timeout` | `5` | 1-60 |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `socket_connect_timeout` | `5` | 1-60 |
| `REDIS_RETRY_ON_TIMEOUT` | `retry_on_timeout` | `True` | — |
| `REDIS_DECODE_RESPONSES` | `decode_responses` | `True` | — |
| `REDIS_DEFAULT_TTL_SECONDS` | `default_ttl_seconds` | `3600` | 60-86400 |

### LoggingConfig — file:365-432
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `LOG_LEVEL` | `level` | `"INFO"` | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `LOG_FORMAT` | `format` | `"json"` | json/text |
| `LOG_FILE` | `file` | `"logs/kosmos.log"` | — |
| `DEBUG_MODE` | `debug_mode` | `False` | — |
| `DEBUG_LEVEL` | `debug_level` | `0` | 0/1/2/3 |
| `DEBUG_MODULES` | `debug_modules` | `None` | comma-separated |
| `LOG_LLM_CALLS` | `log_llm_calls` | `False` | — |
| `LOG_AGENT_MESSAGES` | `log_agent_messages` | `False` | — |
| `LOG_WORKFLOW_TRANSITIONS` | `log_workflow_transitions` | `False` | — |
| `STAGE_TRACKING_ENABLED` | `stage_tracking_enabled` | `False` | — |
| `STAGE_TRACKING_FILE` | `stage_tracking_file` | `"logs/stages.jsonl"` | — |

### LiteratureConfig — file:435-489
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `SEMANTIC_SCHOLAR_API_KEY` | `semantic_scholar_api_key` | `None` | — |
| `PUBMED_API_KEY` | `pubmed_api_key` | `None` | — |
| `PUBMED_EMAIL` | `pubmed_email` | `None` | — |
| `LITERATURE_CACHE_TTL_HOURS` | `cache_ttl_hours` | `48` | 1-168 |
| `MAX_RESULTS_PER_QUERY` | `max_results_per_query` | `100` | 1-1000 |
| `PDF_DOWNLOAD_TIMEOUT` | `pdf_download_timeout` | `30` | 5-120 |
| `LITERATURE_SEARCH_TIMEOUT` | `search_timeout` | `90` | 10-300 |
| `LITERATURE_API_TIMEOUT` | `api_timeout` | `30` | 5-120 |

### VectorDBConfig — file:492-531
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `VECTOR_DB_TYPE` | `type` | `"chromadb"` | chromadb/pinecone/weaviate |
| `CHROMA_PERSIST_DIRECTORY` | `chroma_persist_directory` | `".chroma_db"` | — |
| `PINECONE_API_KEY` | `pinecone_api_key` | `None` | — |
| `PINECONE_ENVIRONMENT` | `pinecone_environment` | `None` | — |
| `PINECONE_INDEX_NAME` | `pinecone_index_name` | `"kosmos"` | — |

[FACT: file:521-529] `validate_pinecone_config` model_validator: raises `ValueError` if `type == "pinecone"` but `PINECONE_API_KEY` or `PINECONE_ENVIRONMENT` is missing.

### Neo4jConfig — file:534-570
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `NEO4J_URI` | `uri` | `"bolt://localhost:7687"` | — |
| `NEO4J_USER` | `user` | `"neo4j"` | — |
| `NEO4J_PASSWORD` | `password` | `"kosmos-password"` | — |
| `NEO4J_DATABASE` | `database` | `"neo4j"` | — |
| `NEO4J_MAX_CONNECTION_LIFETIME` | `max_connection_lifetime` | `3600` | >= 60 |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | `max_connection_pool_size` | `50` | >= 1 |

### SafetyConfig — file:573-683
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `ENABLE_SAFETY_CHECKS` | `enable_safety_checks` | `True` | — |
| `MAX_EXPERIMENT_EXECUTION_TIME` | `max_experiment_execution_time` | `300` | >= 1 |
| `MAX_MEMORY_MB` | `max_memory_mb` | `2048` | >= 128 |
| `MAX_CPU_CORES` | `max_cpu_cores` | `None` | >= 0.1 |
| `ENABLE_SANDBOXING` | `enable_sandboxing` | `True` | — |
| `REQUIRE_HUMAN_APPROVAL` | `require_human_approval` | `False` | — |
| `ETHICAL_GUIDELINES_PATH` | `ethical_guidelines_path` | `None` | — |
| `ENABLE_RESULT_VERIFICATION` | `enable_result_verification` | `True` | — |
| `OUTLIER_THRESHOLD` | `outlier_threshold` | `3.0` | >= 1.0 |
| `DEFAULT_RANDOM_SEED` | `default_random_seed` | `42` | — |
| `CAPTURE_ENVIRONMENT` | `capture_environment` | `True` | — |
| `APPROVAL_MODE` | `approval_mode` | `"blocking"` | blocking/queue/automatic/disabled |
| `AUTO_APPROVE_LOW_RISK` | `auto_approve_low_risk` | `True` | — |
| `NOTIFICATION_CHANNEL` | `notification_channel` | `"both"` | console/log/both |
| `NOTIFICATION_MIN_LEVEL` | `notification_min_level` | `"info"` | debug/info/warning/error/critical |
| `USE_RICH_FORMATTING` | `use_rich_formatting` | `True` | — |
| `INCIDENT_LOG_PATH` | `incident_log_path` | `"safety_incidents.jsonl"` | — |
| `AUDIT_LOG_PATH` | `audit_log_path` | `"human_review_audit.jsonl"` | — |

### PerformanceConfig — file:686-749
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `ENABLE_RESULT_CACHING` | `enable_result_caching` | `True` | — |
| `CACHE_TTL` | `cache_ttl` | `3600` | >= 0 |
| `PARALLEL_EXPERIMENTS` | `parallel_experiments` | `0` | >= 0 |
| `ENABLE_CONCURRENT_OPERATIONS` | `enable_concurrent_operations` | `False` | — |
| `MAX_PARALLEL_HYPOTHESES` | `max_parallel_hypotheses` | `3` | 1-10 |
| `MAX_CONCURRENT_EXPERIMENTS` | `max_concurrent_experiments` | `10` | 1-16 |
| `MAX_CONCURRENT_LLM_CALLS` | `max_concurrent_llm_calls` | `5` | 1-20 |
| `LLM_RATE_LIMIT_PER_MINUTE` | `llm_rate_limit_per_minute` | `50` | 1-200 |
| `ASYNC_BATCH_TIMEOUT` | `async_batch_timeout` | `300` | 10-3600 |

### LocalModelConfig — file:752-822
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `LOCAL_MODEL_MAX_RETRIES` | `max_retries` | `1` | 0-5 |
| `LOCAL_MODEL_STRICT_JSON` | `strict_json` | `False` | — |
| `LOCAL_MODEL_JSON_RETRY_HINT` | `json_retry_with_hint` | `True` | — |
| `LOCAL_MODEL_REQUEST_TIMEOUT` | `request_timeout` | `120` | 30-600 |
| `LOCAL_MODEL_CONCURRENT_REQUESTS` | `concurrent_requests` | `1` | 1-4 |
| `LOCAL_MODEL_FALLBACK_UNSTRUCTURED` | `fallback_to_unstructured` | `True` | — |
| `LOCAL_MODEL_CB_THRESHOLD` | `circuit_breaker_threshold` | `3` | 1-10 |
| `LOCAL_MODEL_CB_RESET_TIMEOUT` | `circuit_breaker_reset_timeout` | `60` | 10-300 |

### MonitoringConfig — file:825-840
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `ENABLE_USAGE_STATS` | `enable_usage_stats` | `True` | — |
| `METRICS_EXPORT_INTERVAL` | `metrics_export_interval` | `60` | >= 0 |

### DevelopmentConfig — file:843-862
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `HOT_RELOAD` | `hot_reload` | `False` | — |
| `LOG_API_REQUESTS` | `log_api_requests` | `False` | — |
| `TEST_MODE` | `test_mode` | `False` | — |

### WorldModelConfig — file:865-893
| Env Var | Field | Default | Constraints |
|---------|-------|---------|-------------|
| `WORLD_MODEL_ENABLED` | `enabled` | `True` | — |
| `WORLD_MODEL_MODE` | `mode` | `"simple"` | simple/production |
| `WORLD_MODEL_PROJECT` | `project` | `None` | — |
| `WORLD_MODEL_AUTO_SAVE_INTERVAL` | `auto_save_interval` | `300` | >= 0 |

## KosmosConfig (Master Config) — file:922-983

[FACT: file:953-976] Composes all sub-configs as fields:
- `llm_provider`: `Literal["anthropic", "openai", "litellm"]`, default `"anthropic"`, env `LLM_PROVIDER`
- `claude`: `Optional[ClaudeConfig]` — created only if `ANTHROPIC_API_KEY` set
- `anthropic`: `Optional[AnthropicConfig]` — alias, also only if `ANTHROPIC_API_KEY` set
- `openai`: `Optional[OpenAIConfig]` — created only if `OPENAI_API_KEY` set
- `litellm`: `Optional[LiteLLMConfig]` — always created (default_factory=LiteLLMConfig)
- `local_model`: `LocalModelConfig` — always created
- All other sub-configs: always created with defaults

## Public Functions

### `get_config(reload: bool = False) -> KosmosConfig` — file:1140-1154
[FACT] Module-level singleton. First call constructs `KosmosConfig()` (triggering all Pydantic validation and .env loading), then calls `create_directories()`. Subsequent calls return the cached `_config`. Pass `reload=True` to reconstruct from current env state.

[FACT: file:1137] No thread lock — the `_config` global is unprotected. In concurrent startup, two threads could both see `_config is None` and race to construct it. In practice this is benign (both would produce identical configs) but it is technically a race.

### `reset_config()` — file:1157-1160
[FACT] Sets the module-level `_config = None`. Next `get_config()` call will reconstruct from scratch. Used in tests to isolate config state.

### `parse_comma_separated(v)` — file:20-26
[FACT] Pydantic `BeforeValidator` helper. Converts comma-separated strings (e.g., `"biology,physics"`) to `List[str]`. Returns `None` for empty/None input to let field defaults take over. Used by `ResearchConfig.enabled_domains`, `ResearchConfig.enabled_experiment_types`, and `LoggingConfig.debug_modules`.

### `KosmosConfig.get_active_model() -> str` — file:1045-1054
[FACT] Returns the model string for whichever `llm_provider` is active. Dispatches to `self.litellm.model`, `self.claude.model`, or `self.openai.model`.

### `KosmosConfig.get_active_provider_config() -> dict` — file:1056-1065
[FACT] Returns a dict with `model`, `api_key`, and optionally `api_base` for the active provider. Used by provider factory code.

### `KosmosConfig.create_directories()` — file:1067-1076
[FACT] Called automatically by `get_config()`. Creates `logs/` dir (from `logging.file`) and `.chroma_db/` dir (if vector_db.type is chromadb). Side effect on first config access.

### `KosmosConfig.validate_dependencies() -> List[str]` — file:1078-1101
[FACT] Returns list of missing dependency strings. Checks: `ANTHROPIC_API_KEY` if provider is anthropic, `OPENAI_API_KEY` if provider is openai, `PINECONE_API_KEY` if vector_db is pinecone.

### `KosmosConfig.to_dict() -> dict` — file:1103-1133
[FACT] Serializes config to dict using `model_to_dict()` (Pydantic v1/v2 compat wrapper from `kosmos/utils/compat.py`). Includes all sub-configs. OpenAI and Anthropic only included if non-None.

### `KosmosConfig.sync_litellm_env_vars()` model_validator — file:986-1022
[FACT] Post-construction fixup. Because nested `BaseSettings` sub-models don't pick up `.env` vars from the parent's env_file, this validator manually reads `LITELLM_*` env vars and injects them into the `LiteLLMConfig` instance when they still have default values. Performs type casting for int/float fields.

### `KosmosConfig.validate_provider_config()` model_validator — file:1024-1043
[FACT] Raises `ValueError` at config construction time if the selected `llm_provider` doesn't have its required API key set. Anthropic requires `ANTHROPIC_API_KEY`, OpenAI requires `OPENAI_API_KEY`. LiteLLM is lenient (local models don't need keys).

## Provider Configuration Details

[FACT: file:896-919] Three factory functions control optional provider instantiation:
- `_optional_openai_config()`: returns `OpenAIConfig()` only if `os.getenv("OPENAI_API_KEY")` is truthy
- `_optional_anthropic_config()`: returns `AnthropicConfig()` only if `os.getenv("ANTHROPIC_API_KEY")` is truthy
- `_optional_claude_config()`: same check, returns `ClaudeConfig()`

[FACT: file:960-961] Both `claude` and `anthropic` fields point to independently constructed instances of the same class (`ClaudeConfig` / `AnthropicConfig` are aliases). They are NOT the same object — changing one does not change the other.

## What's Non-Obvious

1. **[FACT: file:960-961] `claude` and `anthropic` are separate instances.** Despite `AnthropicConfig = ClaudeConfig`, the `KosmosConfig` has two separate fields with independent `default_factory` calls. Both check `ANTHROPIC_API_KEY` independently. Most code uses `config.claude.*`, not `config.anthropic.*`.

2. **[FACT: file:978-983 vs file:84] Sub-configs don't load `.env` on their own.** Only `KosmosConfig` and `LiteLLMConfig` have `env_file` in their `SettingsConfigDict`. If you instantiate `ClaudeConfig()` directly in a test, it will only see actual environment variables, not `.env` file values. The `sync_litellm_env_vars` validator (file:986-1022) exists specifically because this is a known problem for LiteLLM.

3. **[FACT: file:17-18] Model constants are module-level.** `_DEFAULT_CLAUDE_SONNET_MODEL = "claude-sonnet-4-5"` and `_DEFAULT_CLAUDE_HAIKU_MODEL = "claude-haiku-4-5"` are imported by `kosmos/cli/commands/config.py` (line 23). Changing these constants changes all default model references.

4. **[FACT: file:982] `case_sensitive=False` on KosmosConfig.** Environment variable matching is case-insensitive for the top-level config. This is the Pydantic-settings default override.

5. **[FACT: file:982] `extra="ignore"` on KosmosConfig.** Unknown env vars are silently ignored. No error if you typo an env var name.

6. **[FACT: file:20-26] Comma-separated list parsing uses `BeforeValidator`.** Environment vars like `ENABLED_DOMAINS=biology,physics` are parsed to lists via `parse_comma_separated`. This works, but the ge/le constraints in the `.env.example` comments reference a "24-168" range for `LITERATURE_CACHE_TTL_HOURS` while the actual validator says `ge=1` — the comment is stricter than the code.

## What Breaks If You Change It

**[PATTERN: 39 call sites in kosmos/ source]** `get_config()` is called from at least 39 distinct locations across the `kosmos/` package:
- `kosmos/core/providers/` (anthropic.py, openai.py, litellm_provider.py, factory.py, __init__.py) — 7 calls
- `kosmos/cli/` (main.py, utils.py, commands/run.py, commands/config.py) — 6 calls
- `kosmos/literature/` (unified_search.py, semantic_scholar.py, pubmed_client.py, pdf_extractor.py, arxiv_http_client.py, arxiv_client.py) — 7 calls
- `kosmos/knowledge/` (vector_db.py, graph.py, concept_extractor.py) — 3 calls
- `kosmos/core/` (llm.py, workflow.py, cache_manager.py, logging.py, domain_router.py, stage_tracker.py) — 6 calls
- `kosmos/safety/` (guardrails.py, code_validator.py) — 2 calls
- `kosmos/agents/base.py` — 2 calls
- `kosmos/world_model/factory.py` — 1 call
- `kosmos/execution/code_generator.py` — 1 call
- `kosmos/db/__init__.py` — 1 call
- `alembic/env.py` — 1 call
- `evaluation/scientific_evaluation.py` — 4 calls

**Consequences of changes:**
- Renaming a config field breaks every access site
- Changing a default value changes behavior across the entire system
- Adding a **required** field (no default) will crash `get_config()` if env var is not set
- The singleton means env var changes after first `get_config()` call are invisible unless `reload=True` or `reset_config()` is called first

## Gotchas

1. **[FACT: file:1137-1154] Singleton is NOT thread-safe.** No `threading.Lock`. Two threads calling `get_config()` simultaneously on first access can race. The result is benign (both create equivalent configs, one wins) but `create_directories()` could be called twice.

2. **[FACT: file:1153] `get_config()` has a side effect: `create_directories()`.** First call creates `logs/` and `.chroma_db/` directories on disk. This is unexpected for what looks like a pure config accessor.

3. **[FACT: file:896-919, 960-961] `claude` and `anthropic` are Optional.** If `ANTHROPIC_API_KEY` is not set and `llm_provider` is not `"anthropic"`, then `config.claude` is `None`. Code that does `config.claude.model` without a None check will crash. The `validate_provider_config` validator (file:1024-1043) only validates the *active* provider, so non-active providers can be None.

4. **[FACT: file:986-1022] LiteLLM env var sync is fragile.** The `sync_litellm_env_vars` validator hardcodes default values (`"gpt-3.5-turbo"`, `4096`, `0.7`, `120`) to detect "still at default". If the defaults in `LiteLLMConfig` are changed without updating this validator, env var overrides will silently fail.

5. **[FACT: file:79-82] CLI mode detection is purely string-based.** `api_key.replace('9', '') == ''` means any all-9s string of any length triggers CLI mode. The empty string also passes this check (but would fail Pydantic's required field validation first).

6. **[FACT: file:547-549] Default Neo4j password is hardcoded.** `NEO4J_PASSWORD` defaults to `"kosmos-password"`. This is a development convenience that could be a security issue in production.

7. **[FACT: file:14] Dependency on `kosmos.utils.compat.model_to_dict`.** The `to_dict()` method requires this Pydantic v1/v2 compatibility wrapper. If Pydantic is upgraded or downgraded, this is the shim that absorbs the breakage.

## Required Environment Variables

- **`ANTHROPIC_API_KEY`**: Required when `LLM_PROVIDER=anthropic` (the default). Without it, `config.claude` is `None` and `validate_provider_config` raises `ValueError`.
- **`OPENAI_API_KEY`**: Required when `LLM_PROVIDER=openai`. Without it, `config.openai` is `None` and validation fails.
- **No required vars for `LLM_PROVIDER=litellm`**: LiteLLM validation is lenient — local models (Ollama) don't need API keys.

All other environment variables have defaults and are optional.

## Missing Config Behavior

[FACT: file:1024-1043] If the required API key for the active provider is missing, `KosmosConfig()` construction raises `ValueError` during Pydantic validation. This means `get_config()` will throw on first call, and the application will not start. The error messages are clear:
- `"ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"`
- `"OPENAI_API_KEY is required when LLM_PROVIDER=openai"`
# Module Deep Read: kosmos/core/convergence.py

## What This Module Does

Decides when an autonomous research loop should stop by evaluating a prioritized set of mandatory and optional stopping criteria against running metrics (iteration count, hypothesis exhaustion, novelty trend, cost-per-discovery), and produces a final convergence report summarizing the research run.

## How It Decides When to Stop (Non-Obvious Details)

### Criterion evaluation order is deliberately not flat

`check_convergence()` (line 221) does NOT just iterate all criteria in one pass. The order is:

1. **Mandatory criteria *except* `iteration_limit`** are checked first (line 246-249). These are hard-stop conditions like `no_testable_hypotheses`.
2. **Optional (scientific) criteria** are checked next (line 255-259): `novelty_decline`, `diminishing_returns`.
3. **`iteration_limit`** is checked *last* among mandatory criteria (line 262-267).

[FACT: convergence.py:246-267] This ordering is intentional so that when both a scientific reason (e.g., novelty decline) and the iteration limit would fire on the same check, the scientific reason is reported as the stopping cause. This matters for reporting quality -- users see "novelty_decline" instead of a generic "iteration_limit".

### Iteration limit can be deferred

`check_iteration_limit()` (line 314) contains a deferral mechanism: even when `iteration_count >= max_iterations`, if fewer than `min_experiments_before_convergence` (default 2) experiments have completed AND testable work remains (untested hypotheses or queued experiments), the detector returns `should_stop=False` with `confidence=0.5` (line 339-356). This prevents premature stopping when the pipeline generated hypotheses but the execution phase barely ran. The docstring explicitly notes that hard caps (MAX_ACTIONS_PER_ITERATION=50, max_runtime_hours) still apply independently, preventing infinite loops.

[FACT: convergence.py:332-356]

### Novelty decline uses two OR'd conditions

`check_novelty_decline()` (line 398) fires if EITHER:
- All recent values in the window are below the threshold (default 0.3), OR
- The recent window shows a strictly monotonically declining trend (each value >= next).

[FACT: convergence.py:421-426] This means a flat series of 0.2, 0.2, 0.2, 0.2, 0.2 triggers the "all below threshold" condition even though it is not declining. A declining series of 0.9, 0.7, 0.5, 0.3, 0.1 triggers the "declining trend" condition even though early values are above threshold.

### novelty_decline_window is auto-clamped

At initialization (line 200-203), if no explicit window is configured, it defaults to `min(5, max(2, max_iters - 1))`. This ensures the window is at least 2 and at most 5, and never exceeds the iteration budget minus one.

[FACT: convergence.py:200-203]

### novelty_trend is append-only and grows per check_convergence call

`_update_metrics()` (line 562) appends the current novelty score to `self.metrics.novelty_trend` every time `check_convergence()` is called. Since the detector is long-lived within a research run, this list grows monotonically. The novelty decline check uses the tail of this list, so multiple calls within the same logical iteration could pollute the trend with duplicate values.

[FACT: convergence.py:562]

### Diminishing returns check requires non-None cost_per_discovery

`check_diminishing_returns()` (line 436) returns `should_stop=False` with `confidence=0.0` if `cost_per_discovery is None`. Cost per discovery is only computed when `significant_results > 0 AND total_cost > 0` (line 580-583). So this criterion is effectively dead until at least one supporting result exists and a cost has been reported.

[FACT: convergence.py:443-449, 580-583]

### The "continue" StoppingDecision uses USER_REQUESTED as a placeholder

When no criteria are met (line 270-276), the returned `StoppingDecision` has `reason=StoppingReason.USER_REQUESTED` and `should_stop=False`. This is explicitly called a "placeholder" in the comment. The enum lacks a dedicated "no_reason" or "continue" value.

[FACT: convergence.py:270-276]

## Blast Radius -- What Depends on Convergence Decisions

### Primary consumer: ResearchDirectorAgent

`research_director.py` (line 33) imports `ConvergenceDetector, StoppingDecision, StoppingReason`. The director:

1. Creates a `ConvergenceDetector` at init with config-driven thresholds (line 168-178).
2. Calls `_check_convergence_direct()` (line 1221) which invokes `check_convergence()`.
3. On `should_stop=True`: sets `research_plan.has_converged = True`, records `convergence_reason`, transitions workflow to `CONVERGED` state, annotates the knowledge graph, and calls `self.stop()` (line 1352-1381).
4. On `should_stop=False`: increments the iteration counter and continues (line 1382-1389).

[FACT: research_director.py:1334-1389]

**Critical note**: `_check_convergence_direct()` always passes `results=[]` (empty list) to `check_convergence()` (line 1237, 1269). This means the `ExperimentResult`-dependent metrics (discovery_rate, consistency_score, significant_results count) are always computed against zero results. The mandatory criteria (iteration_limit, no_testable_hypotheses) still work because they use `research_plan` data, but optional criteria that depend on results are severely hampered.

[FACT: research_director.py:1236-1271] -- hypotheses are loaded from DB but results are not.

### Secondary consumer: _should_check_convergence() gate

The director also duplicates convergence-related logic in `_should_check_convergence()` (line 2736), which mirrors the iteration-limit deferral logic from `ConvergenceDetector`. This duplication means changes to deferral policy must be synchronized in two places.

[FACT: research_director.py:2750-2763]

### Other consumers

- `evaluation/scientific_evaluation.py:930` -- instantiates a detector for evaluation harness.
- `evaluation/run_phase2_tests.py:413` -- phase 2 test runner.
- `tests/e2e/test_convergence.py` and `tests/unit/core/test_convergence.py` -- test suites.
- `tests/integration/test_end_to_end_research.py` -- multiple integration tests.
- `tests/integration/test_iterative_loop.py:618` -- loop integration test.
- `tests/e2e/conftest.py:159` -- e2e test fixture.

[FACT: grep across codebase, 10+ consuming files]

### Workflow state machine dependency

When convergence fires, the director transitions to `WorkflowState.CONVERGED` (line 1375-1378). Any downstream logic keyed on that state (report generation, cleanup, persistence) is indirectly triggered by convergence decisions.

## Runtime Dependencies

| Dependency | Import Location | What It Provides |
|---|---|---|
| `kosmos.core.workflow.ResearchPlan` | line 16 | `iteration_count`, `max_iterations`, `get_untested_hypotheses()`, `hypothesis_pool`, `tested_hypotheses`, `supported_hypotheses`, `rejected_hypotheses`, `experiment_queue`, `completed_experiments`, `has_converged`, `get_testability_rate()` |
| `kosmos.models.hypothesis.Hypothesis` | line 17 | `novelty_score` field used for trend computation |
| `kosmos.models.result.ExperimentResult` | line 18 | `supports_hypothesis` field used for discovery_rate and consistency |
| `kosmos.utils.compat.model_to_dict` | line 19 | Pydantic v1/v2 compatible dict export (used in `get_metrics_dict()`) |
| `pydantic.BaseModel, Field` | line 11 | All data models (`ConvergenceMetrics`, `StoppingDecision`, `ConvergenceReport`) |
| `numpy` | line 14 | Imported but **not used** in the module |
| `logging` | line 13 | Standard logger |

## Public API -- Behavioral Descriptions

### class ConvergenceDetector

**Constructor**: `__init__(mandatory_criteria, optional_criteria, config)`
- Preconditions: None required; all parameters have defaults.
- Side effects: Creates a fresh `ConvergenceMetrics` instance as `self.metrics`.
- Config keys: `novelty_decline_threshold` (float, default 0.3), `novelty_decline_window` (int, auto-clamped), `cost_per_discovery_threshold` (float, default 1000.0), `min_experiments_before_convergence` (int, default 2), `max_iterations` (int, default 10, used only for window clamping).

**`check_convergence(research_plan, hypotheses, results, total_cost) -> StoppingDecision`**
- The main entry point. Updates all internal metrics from the provided data, then evaluates criteria in the prioritized order described above.
- Preconditions: `research_plan` must have `iteration_count`, `max_iterations`, `get_untested_hypotheses()`, `experiment_queue`, `completed_experiments` populated.
- Side effects: Mutates `self.metrics` (appends to `novelty_trend`, updates all metric fields, updates `last_update` timestamp).
- Error behavior: No explicit exception handling; if a field is missing on inputs, standard Python AttributeError propagates.

**`check_iteration_limit(research_plan) -> StoppingDecision`**
- Returns stop=True when iteration_count >= max_iterations, UNLESS the deferral condition is met.
- Preconditions: `research_plan.iteration_count` and `research_plan.max_iterations` must be set.
- Side effects: None.

**`check_hypothesis_exhaustion(research_plan, hypotheses) -> StoppingDecision`**
- Returns stop=True when no untested hypotheses remain AND no experiments are queued.
- Note: The `hypotheses` parameter is accepted but not used -- all logic operates on `research_plan` methods.
- Side effects: None.

**`check_novelty_decline() -> StoppingDecision`**
- Uses internal `self.metrics.novelty_trend`. Requires at least `novelty_decline_window` data points.
- Side effects: None (reads from self.metrics which was updated by a prior `_update_metrics` call).

**`check_diminishing_returns() -> StoppingDecision`**
- Uses internal `self.metrics.cost_per_discovery`. Effectively no-ops until cost data is available.
- Side effects: None.

**`calculate_discovery_rate(results) -> float`**
- Ratio of results with `supports_hypothesis=True` to total results. Returns 0.0 for empty input.

**`calculate_novelty_decline(hypotheses) -> Tuple[float, bool]`**
- Extracts `novelty_score` from hypotheses, returns (latest_score, is_monotonically_declining_over_last_3).

**`calculate_saturation(research_plan) -> float`**
- Delegates to `research_plan.get_testability_rate()`.

**`calculate_consistency(results) -> float`**
- Same computation as discovery_rate (supports_hypothesis=True / total). Docstring says "replication rate" but implementation is identical to discovery_rate.

**`generate_convergence_report(research_plan, hypotheses, results, stopping_reason) -> ConvergenceReport`**
- Produces a final report with summary statistics, supported/rejected hypotheses, recommendations, and a markdown export.
- Side effects: Calls `_update_metrics()` one final time.

**`get_metrics() -> ConvergenceMetrics`** / **`get_metrics_dict() -> Dict`**
- Read-only accessors for the internal metrics state.

### class ConvergenceReport

**`to_markdown() -> str`**
- Renders the report as a markdown string with emoji status indicators, statistics tables, and recommendation lists.

### Enums and Data Classes

- `StoppingReason`: 6 values -- `ITERATION_LIMIT`, `NO_TESTABLE_HYPOTHESES`, `NOVELTY_DECLINE`, `DIMINISHING_RETURNS`, `ALL_HYPOTHESES_TESTED`, `USER_REQUESTED`.
- `ConvergenceMetrics`: Pydantic model tracking discovery, novelty, saturation, consistency, iteration, and cost metrics.
- `StoppingDecision`: Pydantic model with `should_stop`, `reason`, `is_mandatory`, `confidence`, `details`.

## Gotchas

1. **[FACT: research_director.py:1237,1269] results always empty in production**: `_check_convergence_direct()` passes `results=[]` to `check_convergence()`. This means `calculate_discovery_rate()`, `calculate_consistency()`, and cost_per_discovery are always 0/None. The diminishing_returns optional criterion can never fire because `significant_results` stays 0. Novelty decline CAN still fire because it reads `novelty_score` from the hypotheses list (which IS loaded from DB).

2. **[FACT: convergence.py:562] novelty_trend pollution**: Each call to `check_convergence()` appends to `novelty_trend`. If check_convergence is called multiple times per iteration (e.g., from retry logic or repeated convergence checks), the trend accumulates duplicate/near-duplicate values. The novelty_decline check's window then contains intra-iteration noise rather than inter-iteration signal.

3. **[FACT: convergence.py:538-543, 476-481] consistency == discovery_rate**: `calculate_consistency()` and `calculate_discovery_rate()` have identical implementations (count `supports_hypothesis=True` / total). The docstring claims consistency measures "replication rate" but no replication logic exists.

4. **[FACT: convergence.py:14] numpy imported but unused**: `import numpy as np` at line 14 is a dead import. No numpy calls exist in the module.

5. **[FACT: convergence.py:270-276, 301-308] StoppingReason.USER_REQUESTED used as placeholder**: Both the "no criteria met" path and the "unknown criterion" fallback return `USER_REQUESTED` as the reason, which is semantically incorrect in both cases. There is no `NONE` or `CONTINUE` enum value.

6. **[FACT: convergence.py:366-392, line 370 parameter] hypotheses parameter unused in check_hypothesis_exhaustion**: The `hypotheses: List[Hypothesis]` parameter is accepted but never referenced; all logic uses `research_plan.get_untested_hypotheses()` and `research_plan.experiment_queue`.

7. **[FACT: research_director.py:2750-2763 vs convergence.py:332-356] duplicated deferral logic**: The iteration-limit deferral logic (defer if few experiments completed and testable work remains) is implemented in both `ConvergenceDetector.check_iteration_limit()` and `ResearchDirectorAgent._should_check_convergence()`. These must be kept in sync manually; divergence would cause the gate to disagree with the detector.

8. **[FACT: convergence.py:67-68] datetime.utcnow() deprecation**: `ConvergenceMetrics` uses `datetime.utcnow()` for default timestamps. This is deprecated in Python 3.12+ in favor of `datetime.now(timezone.utc)`.

9. **[FACT: convergence.py:424] strictly monotonic decline check**: The "declining trend" check uses `>=` (i.e., `recent[i] >= recent[i+1]`), meaning a flat trend like [0.5, 0.5, 0.5, 0.5, 0.5] is considered "declining". This is a non-strict inequality that may cause unexpected early stopping on plateau novelty scores.

10. **[FACT: convergence.py:31] ALL_HYPOTHESES_TESTED never used internally**: The `StoppingReason.ALL_HYPOTHESES_TESTED` enum value is defined but no criterion check produces it. It could only appear if an external caller constructs a `StoppingDecision` manually.
# Module Deep Read: kosmos/execution/executor.py

## What This Module Does

`executor.py` is the legacy code execution engine that runs LLM-generated Python (and optionally R) experiment code with safety measures, output capture, retry logic, and optional Docker sandboxing. It is the primary execution path used by `research_director.py` and `parallel.py` to actually run scientific experiments.

## File Facts

- **Path**: `/mnt/c/python/kosmos/kosmos/execution/executor.py`
- **Size**: ~1067 lines
- **Risk**: 0.70 (high churn)
- **Key issue references**: F-16 (restricted builtins), F-17 (sandbox fallback), F-19 (timeout), F-21 (code validation), F-22 (deduplicated CodeValidator), Issue #51 (data path), Issue #54 (self-correcting retry), Issue #69 (R language support)

---

## Architecture: Two Execution Modes

The module has a critical fork at `_execute_once()` (line 466):

1. **Sandboxed mode** (`use_sandbox=True`): Delegates to `DockerSandbox` from `sandbox.py`. Code runs inside a Docker container with network disabled, read-only FS, all capabilities dropped, no-new-privileges. This is the intended production path.

2. **Unsandboxed mode** (`use_sandbox=False`): Runs code via Python `exec()` in the same process with restricted builtins and a restricted `__import__`. This is the fallback when Docker is unavailable.

[FACT] The sandbox fallback is silent and automatic -- if Docker SDK import fails at line 25, `SANDBOX_AVAILABLE` is set to `False`, and the constructor at line 216-221 silently downgrades to unsandboxed execution with only a `logger.warning`. There is no hard error.

---

## Security Boundaries

### Sandboxed Path (Docker)
[FACT] `sandbox.py` lines 258-277 configure the container with:
- `network_disabled: True` -- no network access
- `read_only: True` -- read-only root filesystem
- `cap_drop: ['ALL']` -- all Linux capabilities dropped
- `security_opt: ['no-new-privileges']` -- prevent privilege escalation
- `tmpfs` on `/tmp` (100m, noexec, nosuid) and `/home/sandbox/.local` (50m, noexec, nosuid)
- `mem_limit` (default 2g) and `nano_cpus` (default 2 cores)
- Container runs as non-root user `sandbox` (UID 1000, Dockerfile line 38)
- Code volume mounted read-only at `/workspace/code`; output mounted read-write at `/workspace/output`

### Unsandboxed Path (exec-based)
[FACT] `SAFE_BUILTINS` (lines 43-83) is the restricted builtins dictionary. It deliberately **excludes**:
- `open` -- no file I/O
- `getattr`, `setattr`, `delattr` -- no attribute manipulation
- `eval`, `exec`, `compile` -- no dynamic code generation
- `__import__` -- replaced with `_make_restricted_import()` (line 97-110)

[FACT] `_ALLOWED_MODULES` (lines 86-94) whitelists ~30 scientific/stdlib module families for import. Only top-level names are checked (e.g., `numpy` allows `numpy.linalg`).

### Gotcha: `type` and `hasattr` Are in SAFE_BUILTINS
[FACT] Lines 62-63: `type`, `hasattr`, `isinstance`, `issubclass` are all available. Combined with the fact that `type` is a metaclass constructor, sufficiently clever code could potentially construct new types. This is a known tradeoff -- these are needed for scientific code patterns.

### Gotcha: `super` and `object` Are in SAFE_BUILTINS
[FACT] Line 67: `super` and `object` are exposed. Combined with `type`, this allows class creation via `type('Foo', (object,), {...})`. The restricted `__import__` blocks most dangerous module access, but class construction is unrestricted.

### Gotcha: Unsandboxed Timeout on Windows Is Thread-Based, Not Process-Kill
[FACT] Lines 600-630: On Unix, timeout uses `signal.SIGALRM` (same-thread, reliable). On Windows, it uses `concurrent.futures.ThreadPoolExecutor`, which **cannot actually kill the running thread** -- it just stops waiting. The `exec()` call continues running in the background thread. A CPU-infinite-loop in generated code on Windows will consume resources indefinitely.

---

## Public Functions / Methods

### `CodeExecutor.__init__(...)`
- **Lines**: 174-235
- **Behavior**: Creates executor with retry strategy, optionally initializes Docker sandbox and R executor
- **Preconditions**: If `use_sandbox=True` and Docker SDK unavailable, silently falls back to unsandboxed
- **Side effects**: Creates `DockerSandbox` instance (which connects to Docker daemon and verifies/builds image)

### `CodeExecutor.execute(code, local_vars, retry_on_error, llm_client, language)`
- **Lines**: 237-376
- **Behavior**: Main execution entry point. Auto-detects language (Python vs R), then runs code with retry loop. On failure with `retry_on_error=True`, uses `RetryStrategy.modify_code_for_retry()` to attempt automated fixes, optionally using LLM for repair.
- **Preconditions**: Code must be syntactically valid (or CodeValidator catches it upstream)
- **Side effects**: `time.sleep()` between retries (exponential backoff). May call LLM for code repair.
- **Error behavior**: Returns `ExecutionResult(success=False)` with error details -- never raises
- **Return convention**: Looks for `results` or `result` variable in exec_locals (line 516)

### `CodeExecutor.execute_with_data(code, data_path, retry_on_error)`
- **Lines**: 632-660
- **Behavior**: Convenience wrapper that prepends `data_path = repr(path)` to code AND passes it as a local variable
- **Gotcha**: [FACT] Line 655 -- data_path is injected TWICE: once as prepended code text, once in `local_vars`. This is intentional (Issue #51 comment) to handle both template patterns.

### `CodeExecutor._execute_once(code, local_vars)`
- **Lines**: 466-553
- **Behavior**: Single execution attempt. Routes to sandbox or direct exec. Captures stdout/stderr. Optionally profiles execution.
- **Side effects**: When profiling is enabled, imports and runs `ExecutionProfiler` from `kosmos.core.profiling`
- **Return value extraction**: [FACT] Line 516 -- looks for `results` variable first, then `result` in exec_locals. Generated code must set one of these to pass data back.

### `CodeExecutor._execute_in_sandbox(code, local_vars)`
- **Lines**: 555-587
- **Behavior**: Prepares data file mounts from `local_vars['data_path']`, then calls `DockerSandbox.execute()`. Rewrites `data_path` in code to point to `/workspace/data/{filename}`.
- **Gotcha**: [FACT] Line 569 -- uses `os.path.basename(data_path)` to extract filename. If two different data files have the same basename, only one will be mounted (dict key collision).

### `CodeExecutor._prepare_globals()`
- **Lines**: 589-598
- **Behavior**: Builds restricted global namespace. Replaces `__builtins__` with `SAFE_BUILTINS` + restricted `__import__`.
- **Security**: This is the **only** security boundary in unsandboxed mode.

### `CodeExecutor._exec_with_timeout(code, exec_globals, exec_locals)`
- **Lines**: 600-630
- **Behavior**: Wraps `exec()` with timeout. Uses SIGALRM on Unix, ThreadPoolExecutor on Windows.
- **Gotcha**: See Windows timeout issue above.

### `CodeExecutor.execute_r(code, capture_results, output_dir)` and `_execute_r(code)`
- **Lines**: 378-464
- **Behavior**: Routes R code to `RExecutor`, converts `RExecutionResult` to `ExecutionResult`
- **Preconditions**: R executor must be available (`R_EXECUTOR_AVAILABLE`)
- **Graceful degradation**: Returns `ExecutionResult(success=False, error_type="RNotAvailable")` if R not installed

### `execute_protocol_code(code, data_path, max_retries, use_sandbox, sandbox_config)`
- **Lines**: 1017-1066
- **Behavior**: Top-level convenience function. **Always validates code with CodeValidator first** (F-21). Creates a fresh `CodeExecutor` per call.
- **Gotcha**: [FACT] Line 1040-1048 -- Validation failure returns a plain dict (not ExecutionResult), with different keys (`validation_errors` instead of `error`). Callers must handle both shapes.
- **Side effects**: Creates and discards a `CodeExecutor` (and potentially a `DockerSandbox`) per call. No container reuse.

### `CodeValidator` (re-exported from `kosmos.safety.code_validator`)
- **Line**: 663-664
- **Behavior**: AST-based static analysis checking for dangerous modules, patterns, and ethical guidelines
- [FACT] Line 663: `CodeValidator` is re-exported from `kosmos.safety.code_validator` with a comment "F-22: removed duplicate". There was previously a duplicate implementation in this file.

---

## RetryStrategy (Lines 667-1014)

### Behavior
Self-correcting execution retry with 10+ error-type-specific fix strategies plus optional LLM-based repair.

### Fix Strategies
| Error Type | Fix Strategy | Notes |
|---|---|---|
| `NameError` | Auto-imports from COMMON_IMPORTS dict (16 entries) | e.g., `pd` -> `import pandas as pd` |
| `KeyError` | Wraps in try/except, returns error dict | |
| `FileNotFoundError` | Returns `None` (terminal -- no retry) | Issue #51: synthetic data should be used instead |
| `TypeError` | Wraps in try/except | |
| `IndexError` | Wraps in try/except | |
| `AttributeError` | Wraps in try/except | |
| `ValueError` | Wraps in try/except | |
| `ZeroDivisionError` | Wraps in try/except | |
| `ImportError` | Wraps in try/except with module name | |
| `PermissionError` | Wraps in try/except | |
| `MemoryError` | Wraps in try/except | |
| LLM repair | Sends code + error + traceback to LLM | Only first 2 attempts |

### Gotcha: Most "Fixes" Just Wrap in try/except
[PATTERN] 9 of 11 fix methods (all except NameError auto-import and FileNotFoundError terminal) use the same pattern: wrap the entire code in `try: ... except: results = {'error': ..., 'status': 'failed'}`. This means the "fixed" code always "succeeds" (no exception) but returns a failure dict. The retry loop at line 284 checks `result.success` which will be `True` because exec didn't raise, but the return_value will be an error dict. Downstream consumers must check `result.return_value.get('status') == 'failed'`.

### Gotcha: LLM Repair Prompt Is Unrestricted
[FACT] Lines 835-848: The LLM repair prompt sends the full original code and traceback to the LLM and asks for "fixed Python code". The returned code is executed without re-validation through CodeValidator. A malicious or confused LLM response could introduce unsafe code.

---

## Runtime Dependencies

| Dependency | Required? | What Happens If Missing |
|---|---|---|
| Docker daemon + `docker` Python SDK | No | Falls back to exec-based unsandboxed mode (F-17) |
| `kosmos-sandbox:latest` Docker image | Only if sandbox used | `DockerSandbox.__init__` builds image from `docker/sandbox/Dockerfile` |
| `kosmos.safety.code_validator.CodeValidator` | Yes for `execute_protocol_code` | ImportError at module load |
| `kosmos.execution.r_executor.RExecutor` | No | R execution unavailable, graceful fallback |
| `kosmos.core.profiling.ExecutionProfiler` | No | Profiling silently disabled |
| `kosmos.safety.reproducibility.ReproducibilityManager` | No | Determinism check silently skipped |
| `kosmos.utils.compat.model_to_dict` | Yes | ImportError at module load (line 9) |

---

## Blast Radius: What Breaks If You Change This

1. **`research_director.py` line 1540**: `ResearchDirector._execute_experiment_direct()` creates a `CodeExecutor(max_retries=3)` -- the main agent execution path. Breaking the constructor or `execute()` stops all experiment execution.

2. **`parallel.py` line 290-298**: `_execute_single_task()` calls `execute_protocol_code()` -- the parallel batch execution path. Breaking the convenience function stops batch runs.

3. **`__init__.py`**: Exports `CodeExecutor`, `ExecutionResult`, `CodeValidator`, `RetryStrategy`, `execute_protocol_code` at package level. Renaming or removing any of these breaks downstream imports.

4. **Return value contract**: Generated code must assign to `results` or `result` variable. Changing `_execute_once()` line 516 to look for a different variable name would silently break all existing code templates in `code_generator.py`.

5. **`execute_protocol_code` return shape**: Returns a dict (not ExecutionResult) with different keys on validation failure vs execution failure. Callers in parallel.py rely on `.get('success')` and `.get('error')`.

---

## Relationship to Other Execution Files

| File | Role | Relationship |
|---|---|---|
| `sandbox.py` | Docker container lifecycle for single-shot execution | Called by executor.py `_execute_in_sandbox()` |
| `docker_manager.py` | Container pool management (async) | Used by `production_executor.py`, NOT by `executor.py` |
| `production_executor.py` | Newer async executor with container pooling | Parallel evolution -- does NOT use `executor.py` |
| `code_generator.py` | Generates Python code from experiment protocols | Output feeds into `executor.py` |
| `parallel.py` | Batch execution of multiple experiments | Calls `execute_protocol_code()` |
| `r_executor.py` | R language execution via Rscript or Docker | Called by executor.py for R code |
| `data_provider.py` | Provides data files for experiments | Used alongside executor by research_director |

[ABSENCE] `executor.py` and `production_executor.py` are separate evolution paths. `executor.py` is synchronous, creates fresh containers per call. `production_executor.py` is async, uses container pooling via `docker_manager.py`. They share the `kosmos-sandbox:latest` image but do not call each other.

---

## Summary of Gotchas

1. **Silent sandbox fallback** (line 216-221): If Docker SDK not installed, execution silently runs unsandboxed with only restricted builtins as protection. No hard failure, no config flag to require sandbox.

2. **Windows timeout is non-killing** (line 621-630): ThreadPoolExecutor cannot terminate the `exec()` thread. CPU-bound infinite loops continue consuming resources.

3. **LLM-repaired code bypasses validation** (line 778-788): Code fixed by LLM is executed without going through CodeValidator. Only `execute_protocol_code()` validates; direct `CodeExecutor.execute()` never validates.

4. **Retry "fixes" produce false successes** (pattern in 9 of 11 fix methods): Try/except wrappers make the execution "succeed" but return error dicts as the result value.

5. **Data path basename collision** (line 569): Multiple data files with same basename will overwrite each other in the sandbox mount.

6. **Return value convention is implicit** (line 516): Generated code must set `results` or `result` variable. No enforcement, no error if missing.

7. **`execute_protocol_code` has inconsistent return shape** (line 1043-1048 vs 1063): Validation failure returns dict with `validation_errors` key; execution result has `error` key.

8. **Fresh DockerSandbox per `execute_protocol_code` call** (line 1051-1055): No container reuse in the legacy path. Each call creates a new sandbox, verifies/builds image, runs, and tears down.
# Pillar Module Analysis: experiment.py, result.py, workflow.py

## 1. kosmos/models/experiment.py (30 importers)

### Behavior
[FACT: file:1-700] Defines Pydantic data models for experiment **design** -- the protocol, variables, control groups, statistical tests, and resource requirements. This is the runtime companion to the SQLAlchemy `db.models.Experiment` (which stores a flattened JSON blob in its `protocol` column). Every experiment protocol produced by the LLM passes through these models for validation before execution.

### Data Models and Enums

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `VariableType` (enum) | independent, dependent, control, confounding | [FACT: file:21-27] |
| `StatisticalTest` (enum) | t_test, anova, chi_square, correlation, regression, mann_whitney, kruskal_wallis, wilcoxon, custom | [FACT: file:29-39] |
| `Variable` | Single experiment variable | name, type, description (min 10 chars), values, fixed_value, unit, measurement_method |
| `ControlGroup` | Baseline condition | name, description (min 5 chars), variables dict, rationale (min 10 chars), sample_size (clamped to 100k) |
| `ProtocolStep` | One step in protocol | step_number (ge 1), title (min 3 chars, defaults to "Untitled Step"), action, requires_steps, code_template, library_imports |
| `ResourceRequirements` | Compute/cost budget | compute_hours, memory_gb, gpu_required, estimated_cost_usd, api_calls_estimated, required_libraries, can_parallelize |
| `StatisticalTestSpec` | Test specification | test_type, null_hypothesis, alpha (default 0.05), required_power (default 0.8), expected_effect_size (regex-parsed from LLM text) |
| `ValidationCheck` | Rigor check | check_type, severity (error/warning/info), status (passed/failed/pending), recommendation |
| `ExperimentProtocol` | **Central model** -- full protocol | id, name, hypothesis_id, experiment_type, domain, steps (min 1, sequential validation), variables dict, control_groups, statistical_tests, sample_size (clamped 100k), rigor_score (0-1), random_seed |
| `ExperimentDesignRequest` | Input to design agent | hypothesis_id, constraints (max_cost, max_duration, max_compute), require_control_group (default True), min_rigor_score (default 0.6) |
| `ExperimentDesignResponse` | Output from design agent | protocol, validation_passed, rigor_score, completeness_score, feasibility_assessment (High/Medium/Low) |
| `ValidationReport` | Rigor assessment | rigor_score, has_control_group, sample_size_adequate, power_analysis_performed, potential_biases, is_reproducible, severity_level |

### ExperimentType (imported from hypothesis.py)
[FACT: kosmos/models/hypothesis.py:15-20] Three values only: `COMPUTATIONAL`, `DATA_ANALYSIS`, `LITERATURE_SYNTHESIS`.

### Non-Obvious Behavior

**LLM output coercion** -- Multiple field_validators exist specifically to handle messy LLM output:
- [FACT: file:106-125] `ControlGroup.sample_size`: Coerces string to int, clamps to `_MAX_SAMPLE_SIZE` (100,000). Returns None on parse failure rather than raising.
- [FACT: file:265-273] `StatisticalTestSpec.groups`: Coerces comma-separated string to list.
- [FACT: file:283-299] `StatisticalTestSpec.expected_effect_size`: Regex-extracts a float from arbitrary LLM text like "Medium (Cohen's d = 0.5)".
- [FACT: file:176-182] `ProtocolStep.title`: If LLM returns empty/short string, silently replaces with "Untitled Step" instead of raising.
- [FACT: file:373-393] `ExperimentProtocol.sample_size`: Same coercion + clamp pattern as ControlGroup.

**Step ordering validation** -- [FACT: file:424-438] Steps must be numbered 1..N with no gaps or duplicates. Validator rejects non-sequential numbering and re-sorts by step_number. This means callers cannot use step 0 or skip numbers.

**Dual model pattern** -- The Pydantic `ExperimentProtocol` is the runtime model; it gets serialized via `to_dict()` [FACT: file:471-573] and stored in the SQLAlchemy `Experiment.protocol` JSON column [FACT: db/models.py:52]. Reconstruction happens via `ExperimentProtocol.model_validate(protocol_data)` [FACT: research_director.py:1559].

**ConfigDict** -- [FACT: file:575] `use_enum_values=False` -- enums are stored as enum members, not raw strings, in model instances.

### What Breaks If You Change It
- Renaming/removing fields on `ExperimentProtocol` breaks the `to_dict()` serializer (manual, not auto-generated), breaks DB protocol JSON reconstruction in research_director.py:1559, and breaks all 3 experiment templates + validator + code_generator.
- Changing step numbering validation breaks any template that produces non-1-indexed steps.
- Changing `_MAX_SAMPLE_SIZE` (100k) affects the clamp applied to both ControlGroup and ExperimentProtocol sample sizes.
- The `ExperimentType` enum is imported from `hypothesis.py`, not defined here -- adding experiment types requires editing hypothesis.py.


## 2. kosmos/models/result.py (27 importers)

### Behavior
[FACT: file:1-378] Defines Pydantic models for experiment **outcomes** -- execution metadata, statistical test results, per-variable summary statistics, and export formats. Like experiment.py, this is the runtime companion to the SQLAlchemy `db.models.Result`.

### Data Models and Enums

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `ResultStatus` (enum) | success, failed, partial, timeout, error | [FACT: file:16-22] |
| `ExecutionMetadata` | Execution environment record | start_time, end_time, duration_seconds, python_version, platform, memory_peak_mb, experiment_id, protocol_id, sandbox_used, timeout_occurred, errors list, data_source |
| `StatisticalTestResult` | One test's output | test_type, test_name, statistic, p_value (0-1), effect_size, confidence_interval dict, significant_0_05/0_01/0_001 booleans, significance_label, is_primary, sample_size, degrees_of_freedom, interpretation |
| `VariableResult` | Per-variable stats | variable_name, variable_type, mean, median, std, min, max, values list, n_samples, n_missing |
| `ExperimentResult` | **Central model** -- full result | id, experiment_id, protocol_id, hypothesis_id, status, raw_data dict, processed_data dict, variable_results, statistical_tests (unique names enforced), primary_test (cross-validated against test list), primary_p_value, primary_effect_size, supports_hypothesis, metadata (ExecutionMetadata), version, parent_result_id, stdout, stderr, generated_files, summary, interpretation, recommendations |
| `ResultExport` | Multi-format export | result, format (json/csv/markdown); has export_json(), export_csv(), export_markdown() methods |

### Non-Obvious Behavior

**Cross-field validation** -- [FACT: file:206-228] Two validators enforce referential integrity:
1. `statistical_tests` validator rejects duplicate test_names.
2. `primary_test` validator checks that the named test actually exists in the statistical_tests list. Uses `info.data` (Pydantic V2 raw dicts) with explicit dict/model handling.

**Serialization uses compat layer** -- [FACT: file:241-243] `to_dict()` delegates to `kosmos.utils.compat.model_to_dict()` which handles both Pydantic V1 (`.dict()`) and V2 (`.model_dump()`) APIs. This is the only model in the trio that uses the compat layer; experiment.py has a manual `to_dict()`.

**CSV export imports pandas** -- [FACT: file:292-310] `ResultExport.export_csv()` does a lazy `import pandas as pd` inside the method. This is a hidden runtime dependency not declared at module level. Will raise ImportError if pandas is missing.

**Version tracking** -- [FACT: file:183-184] Results have `version` (default 1, ge 1) and `parent_result_id` for re-runs, enabling result lineage tracking.

**Significance convenience** -- [FACT: file:259-263] `is_significant(alpha=0.05)` checks only `primary_p_value`, returning False if None. Does not check individual StatisticalTestResult entries.

### What Breaks If You Change It
- Renaming `test_name` on `StatisticalTestResult` breaks the cross-field validator on `ExperimentResult.primary_test` and the duplicate-name check.
- Changing `ResultStatus` enum values breaks the research_director's hardcoded `ResultStatus.SUCCESS` assignments [FACT: research_director.py:1708, 1856].
- The `ExperimentResult.to_dict()` path through `model_to_dict` means any Pydantic version migration must update the compat layer.
- The pandas dependency in `export_csv` will crash if pandas is not installed -- it is not in the core dependency list (kosmos is stdlib + pydantic for models).


## 3. kosmos/core/workflow.py (26 importers)

### Behavior
[FACT: file:1-417] Implements a state machine for the autonomous research lifecycle. Manages transitions between 9 workflow states, tracks hypothesis/experiment/result IDs, and enforces a directed graph of allowed transitions.

### State Machine

**WorkflowState enum** (9 states) [FACT: file:18-29]:
```
INITIALIZING -> GENERATING_HYPOTHESES -> DESIGNING_EXPERIMENTS -> EXECUTING
    -> ANALYZING -> REFINING -> (loop back or CONVERGED)
    Any state can reach PAUSED or ERROR
```

**NextAction enum** (8 actions) [FACT: file:32-43]:
generate_hypothesis, design_experiment, execute_experiment, analyze_result, refine_hypothesis, converge, pause, error_recovery

### Transition Rules (ALLOWED_TRANSITIONS)
[FACT: file:175-227] -- strict directed graph:

| From State | Allowed Targets |
|------------|----------------|
| INITIALIZING | GENERATING_HYPOTHESES, PAUSED, ERROR |
| GENERATING_HYPOTHESES | DESIGNING_EXPERIMENTS, CONVERGED, PAUSED, ERROR |
| DESIGNING_EXPERIMENTS | EXECUTING, GENERATING_HYPOTHESES (backtrack), PAUSED, ERROR |
| EXECUTING | ANALYZING, ERROR, PAUSED |
| ANALYZING | REFINING, DESIGNING_EXPERIMENTS (retest shortcut), PAUSED, ERROR |
| REFINING | GENERATING_HYPOTHESES (new hyps), DESIGNING_EXPERIMENTS (follow-up), CONVERGED, PAUSED, ERROR |
| CONVERGED | GENERATING_HYPOTHESES (restart) |
| PAUSED | any active state + ERROR (full resume) |
| ERROR | INITIALIZING (restart), GENERATING_HYPOTHESES (resume), PAUSED |

### ResearchPlan Model
[FACT: file:57-163] Tracks the full research session:
- `hypothesis_pool`, `tested_hypotheses`, `supported_hypotheses`, `rejected_hypotheses` -- all lists of ID strings, no duplicates enforced via `if X not in list` guards
- `experiment_queue`, `completed_experiments` -- protocol IDs
- `results` -- result IDs
- `iteration_count` / `max_iterations` (default 10) -- loop budget
- `has_converged`, `convergence_reason`
- Convenience methods: `get_untested_hypotheses()`, `get_testability_rate()`, `get_support_rate()`

### ResearchWorkflow Class
[FACT: file:166-416] The actual state machine:
- `transition_to()` validates against `ALLOWED_TRANSITIONS`, raises `ValueError` on illegal transitions
- Records `WorkflowTransition` objects with from_state, to_state, action, timestamp, metadata
- Syncs `research_plan.current_state` on every transition [FACT: file:323-325]
- `get_state_duration()` calculates time spent in a state from transition history
- `reset()` returns to INITIALIZING and clears history
- Optional debug logging of transitions controlled by `config.logging.log_workflow_transitions` [FACT: file:294-308]

### Non-Obvious Behavior

**No persistence** -- [FACT: file:166-244] ResearchWorkflow is entirely in-memory. Transition history is a Python list, not stored in DB. If the process crashes, all workflow state is lost. The ResearchPlan *is* persisted separately by the research_director, but the workflow object itself is ephemeral.

**EXECUTING has no self-loop** -- [FACT: file:191-194] From EXECUTING, you can only go to ANALYZING, ERROR, or PAUSED. You cannot run another experiment without first analyzing. This forces the analyze-then-decide loop.

**CONVERGED is mostly terminal** -- [FACT: file:211-213] Only exit from CONVERGED is back to GENERATING_HYPOTHESES (restart with new question). Cannot go to PAUSED or ERROR from CONVERGED.

**PAUSED is a universal resume point** -- [FACT: file:214-221] From PAUSED, you can transition to any active state (GENERATING through REFINING) plus ERROR. This makes pause/resume flexible.

**ERROR recovery is limited** -- [FACT: file:222-226] From ERROR, you can only restart (INITIALIZING), resume hypothesis generation, or pause. Cannot jump directly back to EXECUTING or ANALYZING.

**Duplicate prevention in ResearchPlan uses O(n) list scans** -- [PATTERN: 6 instances at file:101-103, 109, 113, 119, 124-125, 129, 134, 139] Every `add_*` and `mark_*` method does `if X not in list` which is O(n). For large hypothesis pools this could become slow, though in practice pools are small.


## 4. How workflow.py Connects Experiments and Results

The `ResearchDirector` agent (kosmos/agents/research_director.py) is the orchestrator that ties all three modules together:

1. **Hypothesis -> Experiment**: Director transitions workflow to `DESIGNING_EXPERIMENTS`, calls `ExperimentDesignerAgent`, which produces an `ExperimentProtocol`. The protocol is serialized via `to_dict()` and stored in `db.models.Experiment.protocol` JSON column. Director then transitions to `EXECUTING`. [FACT: research_director.py:1505-1510]

2. **Experiment -> Result**: Director's `_execute_experiment_direct()` loads the DB experiment, reconstructs `ExperimentProtocol` via `model_validate()`, generates code, executes it, extracts p_value/effect_size from return_value, and stores a `db.models.Result` via `create_result()`. A result_id is added to `research_plan.results`. [FACT: research_director.py:1531-1642]

3. **Result -> Analysis**: Director's `_analyze_result_direct()` transitions to `ANALYZING`, loads `db.models.Result`, constructs a minimal `ExperimentResult` Pydantic model (hardcoded `ResultStatus.SUCCESS`, placeholder `ExecutionMetadata` with current time), and passes it to `DataAnalystAgent.interpret_results()`. [FACT: research_director.py:1700-1722]

4. **Analysis -> Refinement**: Director transitions to `REFINING`, loads results for all experiments of a hypothesis, constructs `ExperimentResult` objects for each, and passes them to `HypothesisRefiner`. [FACT: research_director.py:1843-1859]

5. **Convergence**: After refinement, the `ConvergenceDetector` decides whether to loop or converge. Director transitions to `CONVERGED` or back to `GENERATING_HYPOTHESES`. [FACT: research_director.py:1023-1028, 1373-1378]

### Key Integration Pattern
The research_director always constructs `ExperimentResult` from DB fields with **hardcoded** `ResultStatus.SUCCESS` and **placeholder** `ExecutionMetadata` (start_time = end_time = now, duration = 0). [FACT: research_director.py:1704-1722, 1851-1859] This means the rich metadata fields on `ExecutionMetadata` (cpu_time, memory_peak, library_versions) are never populated in the director's analysis path. They exist for direct execution scenarios that bypass the director.


## 5. Gotchas

1. **[FACT: experiment.py:471-573]** `ExperimentProtocol.to_dict()` is a manual serializer (120+ lines of explicit field mapping). Adding a field to the model without updating `to_dict()` means it silently disappears from serialized output. The `ExperimentResult.to_dict()` uses compat auto-serialization and does not have this problem.

2. **[FACT: result.py:216-228]** `ExperimentResult.primary_test` validator accesses `info.data['statistical_tests']` which contains raw dicts during Pydantic V2 validation, not model instances. The code handles both dict and model access patterns, but this is fragile across Pydantic versions.

3. **[FACT: result.py:292-310]** `ResultExport.export_csv()` has a hidden `import pandas` inside the method body. Kosmos core is Pydantic-only for models; this pandas import will crash at runtime if pandas is not installed and someone calls `export_csv()`.

4. **[FACT: workflow.py:211-213]** CONVERGED state cannot transition to ERROR or PAUSED. If something goes wrong after convergence (e.g., during report generation), the workflow cannot represent that failure state.

5. **[FACT: research_director.py:1707-1708]** The director always sets `ResultStatus.SUCCESS` when constructing `ExperimentResult` for analysis, even when the actual execution may have had partial results or warnings. The real status from execution is not carried through to the Pydantic model.

6. **[FACT: experiment.py:14]** `ExperimentType` is imported from `kosmos.models.hypothesis`, creating a cross-model dependency. The experiment module cannot be imported without the hypothesis module.

7. **[FACT: workflow.py:101-103, 109, etc.]** ResearchPlan's duplicate prevention uses O(n) `in` checks on plain lists. If hypothesis_pool grows large, every `add_hypothesis()` call scans the entire list. In practice, pools are small (max_iterations defaults to 10), so this is unlikely to matter.
# Knowledge Module Deep Read: vector_db.py and graph.py

## Files Investigated

| File | Lines | Purpose |
|------|-------|---------|
| `kosmos/knowledge/vector_db.py` | 477 | ChromaDB vector database for paper embeddings |
| `kosmos/knowledge/graph.py` | 1038 | Neo4j knowledge graph for scientific literature |
| `kosmos/knowledge/embeddings.py` | 369 | SPECTER embedding generation (upstream dep) |
| `kosmos/knowledge/semantic_search.py` | 451 | High-level search combining APIs + vector DB |
| `kosmos/knowledge/__init__.py` | 113 | Package exports, all 8 modules re-exported |
| `kosmos/config.py` (lines 492-570) | -- | VectorDBConfig and Neo4jConfig definitions |

---

## Module: vector_db.py -- ChromaDB Vector Database

### Behavior (1-2 sentences)
Wraps ChromaDB's PersistentClient to store and retrieve scientific paper embeddings for semantic search. Papers are stored as `source:identifier` keyed documents with title+abstract text, metadata (year, domain, citation_count, identifiers), and SPECTER-generated 768-dim embeddings, searched via cosine similarity.

### Runtime Dependencies
- **chromadb** -- optional import with graceful degradation (line 19-27). [FACT: vector_db.py:19-27]
- **numpy** -- for embedding array manipulation
- **kosmos.knowledge.embeddings.get_embedder()** -- singleton SPECTER embedder, which itself requires `sentence-transformers` and downloads `allenai/specter` (~440MB). [FACT: embeddings.py:74]
- **kosmos.literature.base_client.PaperMetadata** -- the paper data class used throughout
- **kosmos.config.get_config()** -- reads `VectorDBConfig.chroma_persist_directory` (default: `.chroma_db`). [FACT: config.py:500-503]

### Non-Obvious Details

**Graceful degradation pattern**: When ChromaDB is not installed, `HAS_CHROMADB` is False. The constructor sets `self.client = None` and `self.collection = None` and returns early (line 62-67). However, only `add_papers()`, `search()`, and `count()` check `self.collection is None` before operating. The `get_paper()`, `delete_paper()`, `clear()`, and `get_stats()` methods do NOT check for None, meaning they will raise `AttributeError` if ChromaDB is missing. [FACT: vector_db.py:314-315, 337-338, 369-370, 362-365]

**Singleton pattern**: Module-level `_vector_db` global with `get_vector_db()` factory. The singleton does NOT re-parameterize -- once created, changing `collection_name` or `persist_directory` on subsequent calls is ignored unless `reset=True`. [FACT: vector_db.py:443-470]

**Embedding strategy**: Uses `allenai/specter` (768-dim) via `sentence-transformers`. Papers are embedded as `title [SEP] abstract` (SPECTER's recommended format). The embedder truncates abstracts to 400 words due to SPECTER's 512-token limit. [FACT: embeddings.py:317-322]

**Document storage format**: ChromaDB stores `title [SEP] abstract` as the document text (line 440), with abstract truncated to 1000 chars. Title truncated to 500 chars in metadata. [FACT: vector_db.py:403, 437-440]

**ID scheme**: Paper IDs are `{source.value}:{primary_identifier}` (e.g., `arxiv:2004.07180`). [FACT: vector_db.py:389]

**Cosine similarity space**: Collection created with `{"hnsw:space": "cosine"}`. Distance-to-similarity conversion is `1 - distance`. [FACT: vector_db.py:99, 239]

**Telemetry disabled**: ChromaDB anonymized telemetry is explicitly turned off. [FACT: vector_db.py:82]

**Batch insertion**: `add_papers()` batches at default 100 items per ChromaDB upsert. [FACT: vector_db.py:134, 172-179]

**Self-exclusion in similarity search**: `search_by_paper()` fetches `top_k + 1` results and filters out the query paper by ID. [FACT: vector_db.py:275]

### Public API

#### `PaperVectorDB.__init__(collection_name="papers", persist_directory=None, reset=False)`
- **Behavior**: Creates ChromaDB PersistentClient, gets-or-creates named collection, initializes SPECTER embedder.
- **Preconditions**: None hard; degrades gracefully if chromadb not installed.
- **Side effects**: Creates persist_directory on disk (mkdir with parents). If `reset=True`, deletes and recreates the collection.
- **Error behavior**: Logs warning if chromadb not available; sets client/collection to None.

#### `add_paper(paper, embedding=None)` / `add_papers(papers, embeddings=None, batch_size=100)`
- **Behavior**: Computes embeddings if not provided, inserts papers into ChromaDB in batches.
- **Preconditions**: Papers must be `PaperMetadata` instances. If collection is None, returns silently.
- **Side effects**: Writes to persistent ChromaDB. Calls `embedder.embed_papers()` if no pre-computed embeddings.
- **Error behavior**: Crashes (no try/except) if embeddings.tolist() fails or if ChromaDB write fails. ChromaDB uses `add` not `upsert` -- duplicate IDs will raise an error from ChromaDB.

#### `search(query, top_k=10, filters=None)`
- **Behavior**: Embeds query string, queries ChromaDB, returns results sorted by cosine similarity.
- **Preconditions**: Collection must exist. Filters use ChromaDB where-clause syntax.
- **Side effects**: None (read-only after embedding computation).
- **Error behavior**: Returns empty list if collection is None.
- **Returns**: List of dicts with `id`, `score` (0-1 cosine similarity), `metadata`, `document`.

#### `search_by_paper(paper, top_k=10, filters=None)`
- **Behavior**: Finds papers similar to a given paper using its embedding. Excludes self from results.
- **Preconditions**: Paper must have enough data to embed (title/abstract). Collection must not be None.
- **Side effects**: None.
- **Error behavior**: No null guard on `self.collection` -- will raise AttributeError if collection is None. [FACT: vector_db.py:273]

#### `get_paper(paper_id)` -> Optional[Dict]
- **Behavior**: Retrieves paper data by ChromaDB ID.
- **Error behavior**: Catches all exceptions, returns None. But no null check on `self.collection` -- AttributeError if chromadb missing. [FACT: vector_db.py:315]

#### `delete_paper(paper_id)`
- **Behavior**: Deletes paper from ChromaDB by ID.
- **Error behavior**: Catches exceptions, logs error. No null check on collection. [FACT: vector_db.py:338]

#### `count()` -> int
- **Behavior**: Returns number of documents in collection.
- **Error behavior**: Returns 0 if collection is None. [FACT: vector_db.py:350-352]

#### `get_stats()` -> Dict
- **Behavior**: Returns collection name, paper count, embedding dimension.
- **Error behavior**: Will crash if `self.embedder` is None (no guard). [FACT: vector_db.py:365]

#### `clear()`
- **Behavior**: Deletes and recreates the collection.
- **Error behavior**: No null check on `self.client` -- will crash if chromadb not available. [FACT: vector_db.py:370]

#### `get_vector_db(collection_name, persist_directory, reset)` (module-level)
- **Behavior**: Returns singleton `PaperVectorDB`. Creates new on first call or when `reset=True`.
- **Gotcha**: Parameters beyond `reset` are ignored after first creation.

#### `reset_vector_db()` (module-level)
- **Behavior**: Sets singleton to None. Next `get_vector_db()` call creates a fresh instance.

---

## Module: graph.py -- Neo4j Knowledge Graph

### Behavior (1-2 sentences)
Provides full CRUD operations for a Neo4j graph database with four node types (Paper, Concept, Method, Author) and five relationship types (CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO). Supports complex Cypher queries for citation networks, concept co-occurrence, paper similarity, and multi-hop graph traversal.

### Runtime Dependencies
- **py2neo** -- required (hard import, no graceful degradation). [FACT: graph.py:15]
- **Docker** -- optional; auto-starts `kosmos-neo4j` container via `docker-compose` if `auto_start_container=True`. [FACT: graph.py:126-171]
- **subprocess** -- for docker container management
- **kosmos.config.get_config()** -- reads `Neo4jConfig` (URI: `bolt://localhost:7687`, user: `neo4j`, password: `kosmos-password`, database: `neo4j`). [FACT: config.py:534-570]
- **kosmos.literature.base_client.PaperMetadata** -- paper data class

### Non-Obvious Details

**Connection failure is silent**: If Neo4j connection fails, `self.graph` is set to None and `self._connected` stays False. The constructor does NOT raise an exception. Callers must check `self.connected`. [FACT: graph.py:96-99] However, NONE of the CRUD or query methods check `self.connected` or `self.graph is None` before calling `self.graph.run()` / `self.node_matcher.match()`. Every method will raise `AttributeError: 'NoneType' object has no attribute 'run'` if Neo4j is down. [PATTERN: 40+ calls to self.graph.run/create/push/delete without null guard, observed across all CRUD and query methods]

**Docker auto-start**: Constructor tries to start `kosmos-neo4j` Docker container via `docker-compose up -d neo4j` with a 30-retry health check (2s intervals = up to 60s wait). Falls back gracefully if docker/docker-compose not found. [FACT: graph.py:118-171]

**Hardcoded password in health check**: The `_ensure_container_running` method uses hardcoded `kosmos-password` in the `cypher-shell` health check command (line 156), which may not match the configured password. [FACT: graph.py:156]

**Index creation on init**: Creates 8 indexes (paper id/doi/arxiv/pubmed, author name, concept name/domain, method name/category) using `IF NOT EXISTS` syntax. Only runs if connected. [FACT: graph.py:173-199]

**Paper lookup tries 4 identifier types**: `get_paper()` tries id, then DOI, then arXiv ID, then PubMed ID sequentially. This means 1-4 round trips per lookup. [FACT: graph.py:272-289]

**Counter increment bug in `create_authored()`**: `author["paper_count"]` is incremented by 1 every time `create_authored()` is called, even when `merge=True` and the relationship already exists. Idempotent calls will inflate the counter. [FACT: graph.py:614-616]

**Similar counter bug in `create_discusses()` and `create_uses_method()`**: `concept["frequency"]` and `method["usage_count"]` increment unconditionally, even on merge of existing relationships. [FACT: graph.py:659-660, 703-704]

**Cypher injection via f-string in `get_citations()`**: The `depth` parameter is interpolated directly into the Cypher query via f-string (line 761), not parameterized. Integer type provides some protection, but no explicit validation. [FACT: graph.py:761]

**Similarly in `find_related_papers()`**: The `max_hops` parameter is f-string interpolated into Cypher. [FACT: graph.py:917-918]

**Singleton pattern**: Module-level `_knowledge_graph` global with `get_knowledge_graph()` factory. Same re-parameterization caveat as vector_db. [FACT: graph.py:999-1031]

### Public API

#### `KnowledgeGraph.__init__(uri, user, password, database, auto_start_container=True, create_indexes=True)`
- **Behavior**: Connects to Neo4j via py2neo, optionally starts Docker container, creates indexes.
- **Preconditions**: Neo4j must be reachable (or auto_start_container must work).
- **Side effects**: May start Docker container. Creates database indexes. Sets `self._connected`.
- **Error behavior**: Catches connection errors silently. Sets `self.graph = None`, `self._connected = False`.

#### `create_paper(paper, merge=True)` -> Node
- **Behavior**: Creates or merges a Paper node. Stores id, title, abstract, year, citation_count, domain, identifiers.
- **Preconditions**: Must be connected (no guard).
- **Side effects**: Writes to Neo4j. On merge, updates existing node in place.

#### `get_paper(paper_id)` -> Optional[Node]
- **Behavior**: Looks up paper by id, DOI, arXiv ID, PubMed ID (in that order). Up to 4 queries.
- **Error behavior**: Will raise AttributeError if not connected.

#### `update_paper(paper_id, properties)` -> Optional[Node]
- **Behavior**: Updates properties on existing paper node.
- **Error behavior**: Returns None if paper not found. Crashes if not connected.

#### `delete_paper(paper_id)` -> bool
- **Behavior**: Deletes paper node and all its relationships (py2neo handles relationship cascade).
- **Error behavior**: Returns False if not found. Crashes if not connected.

#### `create_author(name, affiliation, h_index, merge=True)` -> Node
#### `create_concept(name, description, domain, merge=True)` -> Node
#### `create_method(name, description, category, merge=True)` -> Node
- **Behavior**: Create/merge Author, Concept, Method nodes respectively.
- **Error behavior**: Same crash-if-not-connected pattern.

#### Relationship Creation Methods
- `create_citation(citing_id, cited_id, merge=True)` -> CITES relationship
- `create_authored(author_name, paper_id, order, role, merge=True)` -> AUTHORED relationship
- `create_discusses(paper_id, concept_name, relevance_score, section, merge=True)` -> DISCUSSES relationship
- `create_uses_method(paper_id, method_name, confidence, context, merge=True)` -> USES_METHOD relationship
- `create_related_to(concept1, concept2, similarity, source, merge=True)` -> RELATED_TO relationship
- **All require both endpoint nodes to exist first** (return None if not found).
- **All have counter-increment side effects** (except `create_citation` and `create_related_to`).

#### Query Methods
- `get_citations(paper_id, depth=1)` -- variable-depth citation traversal
- `get_citing_papers(paper_id, limit=50)` -- reverse citation lookup
- `get_author_papers(author_name)` -- papers by author
- `get_concept_papers(concept_name, min_relevance=0.5, limit=50)` -- papers discussing concept
- `get_method_papers(method_name, limit=50)` -- papers using method
- `get_related_concepts(concept_name, min_similarity=0.5, limit=20)` -- concept similarity
- `find_related_papers(paper_id, max_hops=2, limit=20)` -- multi-hop paper discovery
- `get_concept_cooccurrence(concept_name, min_papers=2)` -- concept co-occurrence analysis
- **None have connection guards** -- all crash if Neo4j is unreachable.

#### `get_stats()` -> Dict
- **Behavior**: Counts all 4 node types and 5 relationship types (9 Cypher queries).
- **Error behavior**: Crashes if not connected.

#### `clear_graph()`
- **Behavior**: `MATCH (n) DETACH DELETE n` -- destroys all data.
- **Error behavior**: Crashes if not connected. No confirmation/safety check.

---

## Blast Radius Analysis

### Changing vector_db.py breaks:
- `kosmos/knowledge/semantic_search.py` -- SemanticLiteratureSearch uses `get_vector_db()` directly (line 56)
- `kosmos/knowledge/graph_builder.py` -- GraphBuilder uses `get_vector_db()` for semantic edges (line 16)
- `kosmos/hypothesis/novelty_checker.py` -- NoveltyChecker uses `get_vector_db()` for hypothesis similarity search (line 68)
- `kosmos/hypothesis/refiner.py` -- imports vector_db
- `kosmos/agents/literature_analyzer.py` -- uses vector_db
- `kosmos/world_model/factory.py` -- imports vector_db
- `kosmos/knowledge/__init__.py` -- re-exports PaperVectorDB, get_vector_db, reset_vector_db
- Tests: `tests/unit/knowledge/test_vector_db.py`, `tests/conftest.py`, `tests/integration/test_phase2_e2e.py`, `tests/integration/test_phase3_e2e.py`

**Total direct dependents: 10 production files + 4 test files**

### Changing graph.py breaks:
- `kosmos/knowledge/graph_builder.py` -- primary consumer, orchestrates all graph construction
- `kosmos/knowledge/graph_visualizer.py` -- reads graph for visualization
- `kosmos/literature/citations.py` -- uses graph for citation tracking
- `kosmos/world_model/simple.py` -- uses knowledge graph
- `kosmos/world_model/factory.py` -- imports knowledge graph
- `kosmos/agents/literature_analyzer.py` -- uses knowledge graph
- `kosmos/knowledge/__init__.py` -- re-exports KnowledgeGraph, get_knowledge_graph, reset_knowledge_graph
- Tests: `tests/unit/knowledge/test_graph.py`, `tests/conftest.py`, `tests/integration/test_phase2_e2e.py`, `tests/e2e/test_system_sanity.py`

**Total direct dependents: 8 production files + 4 test files**

---

## Gotchas

1. **[FACT: vector_db.py:315,338,370,365] Inconsistent null guards in PaperVectorDB**: `search()`, `add_papers()`, and `count()` check `self.collection is None`, but `get_paper()`, `delete_paper()`, `clear()`, `search_by_paper()`, and `get_stats()` do NOT. If ChromaDB is not installed, these methods crash with AttributeError.

2. **[FACT: graph.py:96-99 + pattern across all methods] KnowledgeGraph silently fails to connect but then crashes on use**: The constructor catches connection errors and sets `self.graph = None`, but no CRUD or query method checks `self.connected` before using `self.graph`. Every method will AttributeError if Neo4j was unreachable at init time.

3. **[FACT: graph.py:614-616, 659-660, 703-704] Counter inflation on idempotent calls**: `create_authored()`, `create_discusses()`, and `create_uses_method()` increment their respective counters (`paper_count`, `frequency`, `usage_count`) unconditionally, even when merging an already-existing relationship. Calling these methods multiple times for the same data will produce incorrect counts.

4. **[FACT: graph.py:156] Hardcoded password in Docker health check**: The `_ensure_container_running()` method hardcodes `kosmos-password` in the cypher-shell command, bypassing the configured password.

5. **[FACT: graph.py:761, 917-918] Cypher f-string interpolation**: `get_citations()` and `find_related_papers()` interpolate `depth`/`max_hops` into Cypher via f-string. While these are ints (providing some protection), they are not validated or parameterized.

6. **[FACT: vector_db.py:443-470, graph.py:999-1031] Singleton re-parameterization ignored**: Both `get_vector_db()` and `get_knowledge_graph()` ignore constructor parameters after the singleton is created unless `reset=True` is passed. Calling `get_vector_db(collection_name="other_collection")` after initial creation silently returns the original instance with the original collection.

7. **[FACT: vector_db.py:175] ChromaDB `add` not `upsert`**: `add_papers()` uses `self.collection.add()`, which will raise a ChromaDB error if a document with the same ID already exists. There is no deduplication before insertion.

8. **[FACT: graph.py:15] py2neo is a hard dependency**: Unlike chromadb (which degrades gracefully), `py2neo` is imported without try/except. If py2neo is not installed, importing `kosmos.knowledge.graph` crashes the entire knowledge module (since `__init__.py` imports it unconditionally at line 33-37).

9. **[FACT: embeddings.py:317-322, vector_db.py:437-440] Dual truncation of abstracts**: The embedder truncates abstracts to 400 words for SPECTER. The vector_db document storage separately truncates to 1000 chars. These are independent -- the stored document may differ from what was actually embedded.

10. **[FACT: graph.py:118-171] Docker auto-start blocks for up to 60 seconds**: `_ensure_container_running()` can block the calling thread for up to 60 seconds (30 retries * 2s sleep) waiting for Neo4j to start. This happens in `__init__`, so constructing a `KnowledgeGraph` can be very slow.
# Pillar #3: `kosmos/literature/base_client.py` -- Literature Search Abstraction

## What This Module Does

Defines the canonical data model (`PaperMetadata`, `Author`, `PaperSource`) and abstract base class (`BaseLiteratureClient`) for all literature API interactions in Kosmos. Every paper flowing through the system -- from search results to knowledge graph nodes to hypothesis inputs -- is represented as a `PaperMetadata` dataclass originating from this file. [FACT: base_client.py:1-269]

## Exported Symbols and Their Roles

| Symbol | Kind | Direct Importers (production) | Direct Importers (tests) |
|--------|------|-------------------------------|--------------------------|
| `PaperMetadata` | dataclass | 16 production files | 29 test import statements |
| `PaperSource` | str Enum | 8 production files | widespread in tests |
| `Author` | dataclass | 5 production files | used in tests |
| `BaseLiteratureClient` | ABC | 4 production files (the 4 client impls) | 0 |

Total unique importing files: 35 (confirmed via grep). [FACT: counted across kosmos/ and tests/]

## The Data Model (What Everything Depends On)

### `PaperSource` (line 17-23)
String enum with values: `ARXIV`, `SEMANTIC_SCHOLAR`, `PUBMED`, `UNKNOWN`, `MANUAL`. Used as the discriminator throughout the system to identify paper origin. [FACT: base_client.py:17-23]

### `Author` (line 26-33)
Dataclass with fields: `name` (required), `affiliation`, `email`, `author_id` (all optional). [FACT: base_client.py:26-33]

### `PaperMetadata` (line 35-122)
The universal paper representation. 20+ fields covering:

- **Identifiers**: `id` (required, source-specific), `doi`, `arxiv_id`, `pubmed_id` -- all optional cross-references. [FACT: base_client.py:44-48]
- **Core**: `title`, `abstract`, `authors` (List[Author]). [FACT: base_client.py:51-53]
- **Publication**: `publication_date` (datetime), `journal`, `venue`, `year`. [FACT: base_client.py:56-59]
- **Links**: `url`, `pdf_url`. [FACT: base_client.py:62-63]
- **Citation metrics**: `citation_count`, `reference_count`, `influential_citation_count` (all int, default 0). [FACT: base_client.py:66-68]
- **Taxonomy**: `fields` (research domains), `keywords`. [FACT: base_client.py:71-72]
- **Content**: `full_text` (optional, populated when PDF is downloaded). [FACT: base_client.py:75]
- **Debug**: `raw_data` (dict, stores original API response). [FACT: base_client.py:78]

**Non-obvious**: Mutable default fields (`authors`, `fields`, `keywords`) are handled via `__post_init__` that replaces `None` with empty lists. This avoids the classic mutable-default-in-dataclass bug. [FACT: base_client.py:80-87]

#### Key Properties

- `primary_identifier` (line 89-92): Returns first non-None of `doi > arxiv_id > pubmed_id > id`. This is the deduplication key used by `unified_search.py` and `reference_manager.py`.
- `author_names` (line 94-97): Convenience property returning `[a.name for a in self.authors]`.
- `to_dict()` (line 99-122): Serializes to dict for database storage. Note: `raw_data` and `full_text` are excluded from serialization at line 121 -- `full_text` IS included, but `raw_data` is NOT. [FACT: base_client.py:99-122]

**Gotcha**: `to_dict()` includes `full_text` (line 121) but omits `raw_data`. If you expect round-trip fidelity via `to_dict()`, raw API data is lost. [FACT: base_client.py:99-122]

## The Abstract Base Class: `BaseLiteratureClient`

### Constructor (line 133-143)
```python
def __init__(self, api_key: Optional[str] = None, cache_enabled: bool = True)
```
Stores `api_key`, `cache_enabled`, creates a child logger namespaced to the subclass. [FACT: base_client.py:133-143]

### Abstract Methods (MUST be implemented by subclasses)

| Method | Signature | Returns | Notes |
|--------|-----------|---------|-------|
| `search()` | `(query, max_results=10, fields=None, year_from=None, year_to=None, **kwargs)` | `List[PaperMetadata]` | Primary search interface |
| `get_paper_by_id()` | `(paper_id: str)` | `Optional[PaperMetadata]` | Single paper lookup |
| `get_paper_references()` | `(paper_id, max_refs=50)` | `List[PaperMetadata]` | Papers cited BY this paper |
| `get_paper_citations()` | `(paper_id, max_cites=50)` | `List[PaperMetadata]` | Papers that cite this paper |

[FACT: base_client.py:145-210]

### Concrete Helper Methods

**`get_source_name()`** (line 212-219): Derives source name from class name by stripping "Client" suffix. E.g., `ArxivClient` -> `"Arxiv"`. Used in error logging. [FACT: base_client.py:212-219]

**`_handle_api_error()`** (line 221-233): Logs error with `exc_info=True` (includes traceback). Comment on line 233 says "Could add retry logic, circuit breaker, etc. here" -- these are NOT implemented. All subclasses call this but it only logs; it does not re-raise, does not retry, does not circuit-break. [FACT: base_client.py:221-233]

**`_validate_query()`** (line 235-253): Returns False for empty/whitespace queries. Logs warning for queries > 1000 chars but still returns True (does NOT truncate despite the log message saying "truncating"). [FACT: base_client.py:235-253]

**Gotcha**: `_validate_query()` logs "truncating to 1000" at line 250 but does NOT actually truncate the query -- it returns True and the original query passes through unmodified. This is misleading. [FACT: base_client.py:248-253]

**`_normalize_paper_metadata()`** (line 255-268): Raises `NotImplementedError`. This is a quasi-abstract method -- not decorated with `@abstractmethod`, so Python won't enforce its implementation at instantiation time. However, it's never called by the base class itself. Each subclass implements its own conversion method with a different name (e.g., `_arxiv_to_metadata`, `_s2_to_metadata`, `_medline_to_metadata`). [FACT: base_client.py:255-268]

**Gotcha**: `_normalize_paper_metadata` is dead code. No subclass overrides it; they each define their own differently-named conversion methods. [FACT: confirmed by reading arxiv_client.py:333 (`_arxiv_to_metadata`), semantic_scholar.py:309 (`_s2_to_metadata`), pubmed_client.py:466 (`_medline_to_metadata`)]

## How Subclasses Extend It

There are exactly 4 concrete subclasses, all in `kosmos/literature/`:

### 1. `ArxivClient` (arxiv_client.py)
- Uses the `arxiv` Python package when available
- **Fallback pattern**: If `arxiv` package fails to import (Python 3.11+ sgmllib3k issue), silently delegates all calls to `ArxivHTTPClient`. [FACT: arxiv_client.py:16-26, 63-84]
- Rate limiting: 3s delay between requests (configured in `arxiv.Client`). [FACT: arxiv_client.py:96]
- `get_paper_references()` and `get_paper_citations()` return empty lists with a warning -- arXiv API doesn't provide citation data. [FACT: arxiv_client.py:263-299]
- Caching via `kosmos.literature.cache.get_cache()`.

### 2. `ArxivHTTPClient` (arxiv_http_client.py)
- Direct HTTP via `httpx` -- no `arxiv` package dependency. [FACT: arxiv_http_client.py:19, 105]
- Manual XML parsing of Atom 1.0 feed. [FACT: arxiv_http_client.py:13, 37-39]
- Explicit rate limiting: `time.sleep()` to enforce 3s between requests. [FACT: arxiv_http_client.py:121-135]
- Custom User-Agent: `"Kosmos-AI-Scientist/1.0"`. [FACT: arxiv_http_client.py:109]

### 3. `SemanticScholarClient` (semantic_scholar.py)
- Uses `semanticscholar` Python package. [FACT: semantic_scholar.py:9]
- API key optional but recommended (100 req/5min without, 5000 req/5min with). [FACT: semantic_scholar.py:40]
- **Actually implements** `get_paper_references()` and `get_paper_citations()` -- this is the citation data source. [FACT: semantic_scholar.py:219-307]
- Uses `islice()` to cap iteration on `PaginatedResults` to prevent infinite fetch. [FACT: semantic_scholar.py:140-141]
- Supports multiple ID formats: S2 hash, DOI, arXiv, PubMed prefixed IDs. [FACT: semantic_scholar.py:168-173]

### 4. `PubMedClient` (pubmed_client.py)
- Uses Biopython's `Entrez` utilities. [FACT: pubmed_client.py:7]
- **Explicit rate limiting**: Calculates minimum delay based on API key presence (3 req/s without key, 10 req/s with). Uses `time.sleep()`. [FACT: pubmed_client.py:56-58, 91-96]
- **Timeout protection**: Wraps all Entrez calls in `ThreadPoolExecutor` with configurable timeout. [FACT: pubmed_client.py:72-89]
- Batches efetch in groups of 100. [FACT: pubmed_client.py:443-446]
- Requires email address (NCBI policy). Falls back to `"kosmos@example.com"`. [FACT: pubmed_client.py:53]

### [PATTERN] Common Subclass Patterns (observed in all 4 clients):
1. Call `super().__init__(api_key, cache_enabled)` first
2. Load config via `get_config()` for `max_results`
3. Initialize `self.cache = get_cache() if cache_enabled else None`
4. Check cache before every API call, cache results after
5. Catch all exceptions in each method, call `self._handle_api_error()`, return empty list or None
6. Never re-raise exceptions -- all failures are silent (return `[]` or `None`)

## What Breaks If You Change It

### Changing `PaperMetadata` field names or types
- **16 production modules** directly import and construct/consume `PaperMetadata`. These span `kosmos/literature/`, `kosmos/knowledge/`, `kosmos/agents/`, `kosmos/hypothesis/`, `kosmos/world_model/`. [FACT: grep count]
- **29 test files** construct `PaperMetadata` instances in fixtures and assertions.
- The `to_dict()` output is used for database storage -- changing field names breaks persisted data.

### Changing `PaperSource` enum values
- Used as dict keys in `unified_search.py` (line 51). [FACT: unified_search.py:51]
- Used in conditionals throughout the knowledge and agent layers.

### Changing `BaseLiteratureClient` method signatures
- `UnifiedLiteratureSearch` calls `.search()` on all clients polymorphically. [FACT: unified_search.py:76+]
- Adding required parameters to abstract methods breaks all 4 subclasses.

### Changing `Author` dataclass
- `citations.py` and `reference_manager.py` construct `Author` instances. [FACT: citations.py:23, reference_manager.py:433]

## Runtime Dependencies

- **Python stdlib only** for base_client.py itself: `abc`, `typing`, `dataclasses`, `datetime`, `enum`, `logging`. [FACT: base_client.py:7-12]
- Subclass dependencies:
  - `ArxivClient`: `arxiv` package (optional, with fallback)
  - `ArxivHTTPClient`: `httpx`
  - `SemanticScholarClient`: `semanticscholar` package
  - `PubMedClient`: `biopython` (`Bio.Entrez`, `Bio.Medline`)
  - All: `kosmos.literature.cache`, `kosmos.config`
- **No API keys required for arXiv** (public API). Semantic Scholar and PubMed keys are optional but affect rate limits.

## Non-Obvious Behaviors

1. **Silent failure everywhere**: Every subclass catches all exceptions and returns empty results. A network outage produces zero papers with only a log message -- no exception propagates to callers. [PATTERN: observed in all 4 clients]

2. **`_validate_query` lying log message**: Says "truncating to 1000" but does not truncate. [FACT: base_client.py:250]

3. **`_normalize_paper_metadata` is dead code**: Never called, never overridden by its intended name. Each subclass uses a custom converter name. [FACT: confirmed in all 4 subclasses]

4. **ArxivClient silent delegation**: When `arxiv` package is unavailable, `ArxivClient` silently wraps `ArxivHTTPClient`. Callers never know which implementation is active. [FACT: arxiv_client.py:63-84]

5. **`__init__.py` is empty**: No re-exports. Every importer must use the full path `from kosmos.literature.base_client import ...`. [FACT: `__init__.py` contains zero code]

6. **Mutable defaults protected**: `PaperMetadata.__post_init__` replaces `None` authors/fields/keywords with fresh lists. This prevents the shared-mutable-default bug. [FACT: base_client.py:80-87]

7. **`primary_identifier` priority**: DOI > arXiv ID > PubMed ID > source ID. This ordering drives deduplication in unified search. If a paper has a DOI, that always wins. [FACT: base_client.py:91-92]

8. **Cache is disk-based pickle**: `LiteratureCache` in `cache.py` uses pickle files with 48h TTL default. Serializes `PaperMetadata` objects directly -- if you add non-picklable fields to `PaperMetadata`, the cache breaks silently. [FACT: cache.py:24-53]

## File Inventory: `kosmos/literature/`

| File | Lines | Role |
|------|-------|------|
| `base_client.py` | 269 | Data model + ABC (this analysis) |
| `arxiv_client.py` | 403 | arXiv via `arxiv` package (with HTTP fallback) |
| `arxiv_http_client.py` | ~550 | arXiv via direct HTTP/XML |
| `semantic_scholar.py` | 379 | Semantic Scholar via S2 package |
| `pubmed_client.py` | 525 | PubMed via Biopython Entrez |
| `unified_search.py` | ~500 | Parallel multi-source search + dedup |
| `cache.py` | ~280 | Disk-based pickle cache with TTL |
| `citations.py` | ~700 | Citation graph traversal |
| `reference_manager.py` | ~700 | Reference collection management |
| `pdf_extractor.py` | ~320 | PDF download + text extraction |
| `__init__.py` | 0 | Empty |
# Module Deep Read: kosmos/core/llm.py

## What This Module Does

Provides a unified LLM abstraction layer that routes all AI text-generation through either a legacy `ClaudeClient` (Anthropic-only, returns `str`) or a modern multi-provider system (`LLMProvider` subclasses returning `LLMResponse` objects). The module's `get_client()` singleton is the primary entry point for 10+ agent and analysis modules to obtain an LLM handle. [FACT: llm.py:613-679]

## What's Non-Obvious

1. **Two parallel type contracts coexist.** `ClaudeClient.generate()` returns `str` (llm.py:207-365). `LLMProvider.generate()` returns `LLMResponse` (base.py:197-224). Callers obtained via `get_client()` may receive either type depending on `use_provider_system` flag. Callers like `data_analyst.py:365` defensively check `hasattr(response, 'content')` to handle both. [FACT: llm.py:613 return type is `Union[ClaudeClient, LLMProvider]`; data_analyst.py:365]

2. **LLMResponse pretends to be a string.** The `LLMResponse` dataclass implements 25+ string methods (`strip`, `lower`, `split`, `__contains__`, `__len__`, `__iter__`, `__getitem__`, etc.) that delegate to `self.content`. This means code that treated the old `str` return from `ClaudeClient.generate()` works transparently with the new provider system -- `response.strip()` just works. But `isinstance(response, str)` is False, so explicit type checks break. [FACT: base.py:80-154]

3. **CLI mode detection is a string trick.** `self.is_cli_mode = self.api_key.replace('9', '') == ''` -- if the API key consists entirely of '9' characters, the client treats it as a proxy-to-CLI route. This applies to both `ClaudeClient` (llm.py:179) and `AnthropicProvider` (anthropic.py:110). Cost tracking returns $0 in CLI mode. [FACT: llm.py:179, anthropic.py:110, anthropic.py:609-612]

4. **Circular import between llm.py and anthropic.py.** `AnthropicProvider.generate()` does a deferred `from kosmos.core.llm import ModelComplexity` at line anthropic.py:189 for auto model selection. This is a runtime circular import (llm.py imports from providers.base, providers.anthropic imports from llm). Works because it's inside a function body, not at module level. [FACT: anthropic.py:189]

5. **The singleton has a double-checked locking pattern.** `get_client()` uses a fast path without lock (llm.py:643-644) followed by lock acquisition with re-check (llm.py:646-649). Thread-safe for initialization, but the returned client instance is shared and its mutable statistics counters (`total_input_tokens`, etc.) are NOT protected by locks. [FACT: llm.py:608-611, 640-679]

6. **generate_structured has a dual-parameter name gotcha.** `ClaudeClient.generate_structured()` accepts both `output_schema` and `schema` (llm.py:417-418). The `LLMProvider` abstract method uses only `schema` (base.py:283). Callers use both: `literature_analyzer.py:267` uses `output_schema=`, while `hypothesis_generator.py:380` uses `schema=`. Both work only because `ClaudeClient` aliases them. If the caller gets an `LLMProvider` instead (from the new provider system), `output_schema` is passed as `**kwargs` and silently ignored by `AnthropicProvider.generate_structured()` which only reads `schema`. [FACT: llm.py:417-418, base.py:283, anthropic.py:503-509, literature_analyzer.py:267, hypothesis_generator.py:380]

## Blast Radius (27 importers)

Confirmed direct importers of `kosmos.core.llm` in the source tree (excluding docs/tests):

| Module | What It Imports | How It Uses It |
|--------|----------------|----------------|
| research_director.py | `get_client` | `self.llm_client = get_client()` then `.generate()` |
| hypothesis_generator.py | `get_client` | `.generate()`, `.generate_structured(schema=...)` |
| experiment_designer.py | `get_client` | `.generate_structured()`, `.generate()` |
| literature_analyzer.py | `get_client` | `.generate_structured(output_schema=...)` |
| data_analyst.py | `get_client` | `.generate()` with defensive `.content` check |
| summarizer.py | `get_client` | `.generate()` |
| domain_router.py | `ClaudeClient` | Direct instantiation: `ClaudeClient()` |
| code_generator.py | `ClaudeClient` | Direct instantiation: `ClaudeClient()` |
| hypothesis/refiner.py | `get_client` | `.generate()` |
| hypothesis/testability.py | `get_client` | `.generate_structured()` |
| hypothesis/prioritizer.py | `get_client` | `.generate_structured()` |
| providers/anthropic.py | `ModelComplexity` | Deferred import for auto model selection |

[PATTERN: 10 of 12 source importers use `get_client()` to get the singleton. 2 modules (`domain_router.py`, `code_generator.py`) directly instantiate `ClaudeClient` -- these bypass the provider system entirely.]

**What breaks if you change it:**
- Changing `generate()` return type: all 10+ agent/analysis callers. Those using `.content` attribute access would break if it returned raw `str` again. Those treating it as `str` would break if `LLMResponse` lost its string delegation methods.
- Changing `get_client()` default: every agent and analysis module. Currently defaults to `use_provider_system=True`.
- Removing `ClaudeClient` from llm.py: `domain_router.py:13`, `code_generator.py:19` import it directly.
- Changing `generate_structured` parameter name from `schema` to only `output_schema`: `hypothesis_generator.py:380`, `experiment_designer.py:495`, `testability.py:479`, `prioritizer.py:329` all use `schema=`.
- Changing singleton threading: would affect multi-threaded agent orchestration scenarios.

## Runtime Dependencies

Beyond direct imports, the module depends on at runtime:

| Dependency | How | Why |
|------------|-----|-----|
| `anthropic` package | Optional import (llm.py:23-31) | Anthropic SDK for Claude API calls; prints warning if missing |
| `ANTHROPIC_API_KEY` env var | Read at init (llm.py:160) | Falls back to env if no `api_key` arg; ValueError if absent |
| `kosmos.config` | `_DEFAULT_CLAUDE_SONNET_MODEL`, `_DEFAULT_CLAUDE_HAIKU_MODEL` (llm.py:20) | Model name defaults; `get_config()` called inside `get_client()` (llm.py:655) |
| `kosmos.core.pricing` | `get_model_cost` (llm.py:21) | USD cost estimation for API mode |
| `kosmos.core.claude_cache` | `get_claude_cache()` (llm.py:33) | Response caching; itself depends on `kosmos.core.cache` + `kosmos.core.cache_manager` |
| `kosmos.core.utils.json_parser` | `parse_json_response` (llm.py:34) | Robust JSON extraction for `generate_structured` |
| `kosmos.core.providers.base` | `ProviderAPIError`, `LLMProvider` (llm.py:35-36) | Base types |
| `kosmos.core.providers` | `get_provider_from_config` (llm.py:656) | Deferred import in `get_client()` |
| `tenacity` (optional) | Used by `async_llm.py:35-44` | Exponential backoff retry; falls back to no-retry if missing |

## Public Functions and Methods

### Module-Level Functions

#### `get_client(reset=False, use_provider_system=True) -> Union[ClaudeClient, LLMProvider]`
[FACT: llm.py:613-679]

**Behavior:** Returns a thread-safe singleton LLM client. On first call (or `reset=True`), reads `kosmos.config.get_config()` to determine provider, instantiates via `get_provider_from_config()`. Falls back to `AnthropicProvider` with env-var config if config loading fails. If `use_provider_system=False`, creates a legacy `ClaudeClient` instead.

**Preconditions:** Either `ANTHROPIC_API_KEY` env var set, or `kosmos.config` properly configured with API key.

**Side effects:** Mutates module-global `_default_client`. Acquires `_client_lock` threading lock during initialization. Logs to `logger`.

**Error behavior:** If config loading fails AND env var is missing, raises `ValueError` from provider constructor. Does not catch exceptions from provider init -- they propagate to caller.

#### `get_provider() -> LLMProvider`
[FACT: llm.py:682-706]

**Behavior:** Wrapper around `get_client(use_provider_system=True)` that asserts the returned object is an `LLMProvider` instance.

**Preconditions:** Same as `get_client()`.

**Side effects:** Same as `get_client()`.

**Error behavior:** Raises `TypeError` if the singleton is somehow a `ClaudeClient` rather than `LLMProvider`. This is the recommended function for new code.

### ClaudeClient Class (Legacy)
[FACT: llm.py:108-605]

#### `__init__(api_key, model, max_tokens, temperature, enable_cache, enable_auto_model_selection)`

**Behavior:** Initializes Anthropic SDK client. Detects CLI vs API mode from key format. Optionally initializes cache via `get_claude_cache()`. Initializes usage counters to zero.

**Preconditions:** `anthropic` package installed (raises `ImportError` otherwise). API key provided or in env var (raises `ValueError` otherwise).

**Side effects:** Creates `Anthropic` SDK client. May initialize cache (creates/opens SQLite DB on first use). Logs to logger.

**Error behavior:** `ImportError` if no anthropic package. `ValueError` if no API key. Re-raises SDK init exceptions.

#### `generate(prompt, system, max_tokens, temperature, stop_sequences, bypass_cache, model_override) -> str`
[FACT: llm.py:207-365]

**Behavior:** Single-turn text generation. Checks cache first (if enabled), calls Anthropic messages API, caches result, returns plain string. Auto-selects model (haiku/sonnet) if `enable_auto_model_selection=True` and NOT in CLI mode.

**Preconditions:** Client initialized. `prompt` is non-empty string.

**Side effects:** Mutates `self.total_input_tokens`, `self.total_output_tokens`, `self.total_requests`, `self.cache_hits`, `self.cache_misses`, `self.haiku_requests`, `self.sonnet_requests`, `self.model_overrides`. Writes to cache DB on miss.

**Error behavior:** Catches all exceptions, logs error, re-raises. No retry logic -- retries are only in `async_llm.py`.

#### `generate_with_messages(messages, system, max_tokens, temperature) -> str`
[FACT: llm.py:367-408]

**Behavior:** Multi-turn generation. Takes list of `{"role": ..., "content": ...}` dicts. Does NOT use cache. Does NOT support auto model selection (always uses `self.model`).

**Preconditions:** `messages` is a non-empty list of dicts with `role` and `content` keys.

**Side effects:** Mutates token/request counters.

**Error behavior:** Catches all, logs, re-raises.

#### `generate_structured(prompt, output_schema|schema, system, max_tokens, temperature, max_retries) -> dict`
[FACT: llm.py:410-486]

**Behavior:** Appends JSON schema instructions to system prompt, calls `self.generate()`, parses response with `parse_json_response()`. Retries up to `max_retries` times (default 2) with `bypass_cache=True` on retries. Returns parsed dict.

**Preconditions:** Either `output_schema` or `schema` must be provided (raises `ValueError` otherwise).

**Side effects:** Same as `generate()` per attempt. Multiple API calls possible on parse failures.

**Error behavior:** On final parse failure, raises `ProviderAPIError` with `recoverable=False`. Note: uses lower temperature (0.3) by default for more deterministic JSON.

#### `get_usage_stats() -> dict`
[FACT: llm.py:488-578]

**Behavior:** Returns comprehensive stats dict including request counts, token counts, cache metrics, cost estimates, model selection breakdown.

**Side effects:** None (read-only).

**Error behavior:** Division-by-zero protected with conditional checks.

#### `reset_stats()`
[FACT: llm.py:596-605]

**Behavior:** Zeros all counters.

### ModelComplexity Class
[FACT: llm.py:41-105]

#### `ModelComplexity.estimate_complexity(prompt, system) -> dict`

**Behavior:** Static method. Heuristic scoring (0-100) based on token estimate (~4 chars/token) and keyword matches against 20 "complex" keywords. Returns dict with `complexity_score`, `recommendation` ("haiku" if <30, "sonnet" otherwise), and `reason`.

**Preconditions:** None.

**Side effects:** None (pure function).

**Error behavior:** Cannot fail (all arithmetic on string lengths).

**Gotcha:** The recommendation is never "opus" -- only "haiku" or "sonnet". High complexity (score >= 60) still recommends "sonnet", same as moderate (llm.py:93-94). [FACT: llm.py:88-94]

## Provider System (kosmos/core/providers/)

### Architecture

```
providers/
  base.py       - LLMProvider ABC, LLMResponse, UsageStats, Message, ProviderAPIError
  factory.py    - Registry pattern: register_provider(), get_provider(), get_provider_from_config()
  anthropic.py  - AnthropicProvider (also aliased as ClaudeClient at line 881)
  openai.py     - OpenAIProvider
  litellm_provider.py - LiteLLMProvider (100+ backends via litellm library)
  __init__.py   - Re-exports, auto-registers builtins on import
```

### Factory Registration
[FACT: factory.py:188-217]

Auto-registered on module import: `anthropic`, `claude` (alias), `openai`, `litellm`, `ollama` (alias), `deepseek` (alias), `lmstudio` (alias). All aliases for litellm point to `LiteLLMProvider`.

### AnthropicProvider (providers/anthropic.py)
[FACT: anthropic.py:36-881]

Near-duplicate of `ClaudeClient` in llm.py but returns `LLMResponse` instead of `str`. Key differences:
- Has `timeout` config parameter (default 120s) passed to API calls [FACT: anthropic.py:101, 279]
- Has `base_url` support for custom Anthropic endpoints [FACT: anthropic.py:107, 114-116]
- Has lazy-initialized `AsyncAnthropic` client [FACT: anthropic.py:344-359]
- Has sync and async streaming with event bus integration [FACT: anthropic.py:665-877]
- `generate_structured()` does NOT retry on parse failure (single attempt only, unlike ClaudeClient's `max_retries=2`) [FACT: anthropic.py:502-562 vs llm.py:460-476]
- Line 881: `ClaudeClient = AnthropicProvider` -- backward compatibility alias within the providers module (distinct from the `ClaudeClient` class in llm.py)

### OpenAIProvider (providers/openai.py)
[FACT: openai.py:32-643]

- Auto-detects provider type from base_url: `local`, `openrouter`, `together`, `compatible`, or `openai` [FACT: openai.py:121-131]
- Estimates tokens for local models without usage stats (~4 chars/token) [FACT: openai.py:615-626]
- No response caching (unlike AnthropicProvider) [ABSENCE: searched openai.py, no cache references]
- Hardcoded pricing for known OpenAI models only [FACT: openai.py:575-613]

### LiteLLMProvider (providers/litellm_provider.py)
[FACT: litellm_provider.py:40-592]

- Imports `litellm` lazily at init time [FACT: litellm_provider.py:89-96]
- Special handling for Qwen models: injects "no-think" directive into system prompt and enforces min 8192 max_tokens [FACT: litellm_provider.py:156-168, 205-220]
- No response caching [ABSENCE: searched litellm_provider.py, no cache references]
- `generate_structured()` does basic markdown code block stripping but no `parse_json_response` -- uses raw `json.loads()` [FACT: litellm_provider.py:448-468]

## async_llm.py (kosmos/core/async_llm.py)
[FACT: async_llm.py:1-759]

Standalone async client (`AsyncClaudeClient`) with production-grade resilience:
- **Circuit breaker** (3 consecutive failures -> OPEN state, 60s reset timeout) [FACT: async_llm.py:52-138]
- **Token-bucket rate limiter** (default 50 req/min, 5 concurrent) [FACT: async_llm.py:206-266]
- **Retry with exponential backoff** via tenacity (3 attempts, 2-30s waits) -- only if tenacity is installed [FACT: async_llm.py:440-470]
- **Smart retry filtering**: checks `is_recoverable_error()` to skip retrying auth/parse errors [FACT: async_llm.py:141-169]
- **Batch processing**: `batch_generate()` runs requests concurrently via `asyncio.gather()` [FACT: async_llm.py:533-586]
- Returns `str` (not `LLMResponse`) [FACT: async_llm.py:372, 517]
- Entirely separate from the provider system -- uses `AsyncAnthropic` directly, not through providers [FACT: async_llm.py:337]

## Gotchas

1. **[FACT: llm.py:417-418, anthropic.py:503-509] generate_structured parameter name mismatch.** `ClaudeClient.generate_structured()` accepts both `output_schema` and `schema`. `AnthropicProvider.generate_structured()` (and all `LLMProvider` subclasses) only accept `schema`. Callers using `output_schema=` (like `literature_analyzer.py:267`) work with `ClaudeClient` but the parameter gets silently swallowed as `**kwargs` if the client is an `AnthropicProvider`. This is a latent bug that manifests when the system transitions fully to the provider architecture.

2. **[FACT: llm.py:207 returns str, anthropic.py:141 returns LLMResponse] Return type divergence.** `ClaudeClient.generate()` returns `str`. `AnthropicProvider.generate()` returns `LLMResponse`. Code obtained via `get_client()` may get either depending on config and fallback paths. The `LLMResponse` string delegation (base.py:80-154) papers over most cases, but `isinstance(x, str)` checks, `json.loads(response)`, and string concatenation with f-strings can behave differently.

3. **[FACT: anthropic.py:502-562 vs llm.py:460-476] generate_structured retry behavior differs.** `ClaudeClient.generate_structured()` retries up to 2 times (3 total attempts) on JSON parse failure with cache bypass on retries. `AnthropicProvider.generate_structured()` does NOT retry -- single attempt, immediate raise on parse failure.

4. **[FACT: llm.py:251, anthropic.py:187] Auto model selection disabled in CLI mode.** Both `ClaudeClient` and `AnthropicProvider` skip auto model selection when `is_cli_mode=True`, even if `enable_auto_model_selection=True`. The condition is `elif self.enable_auto_model_selection and not self.is_cli_mode`. This means CLI-mode users always get the default model regardless of complexity.

5. **[FACT: llm.py:608-611] Shared mutable state without synchronization.** The singleton's usage counters (`total_input_tokens`, `total_requests`, etc.) are plain integers on a shared object. Thread-safe initialization via `_client_lock` does not protect concurrent increments during `generate()` calls. In multi-threaded scenarios, usage stats can lose increments.

6. **[FACT: llm.py:676, anthropic.py:881] Two different classes named ClaudeClient.** `llm.py` defines `ClaudeClient` as a standalone class (lines 108-605). `anthropic.py` line 881 creates `ClaudeClient = AnthropicProvider` as a backward-compat alias. Imports from different paths get different classes. `from kosmos.core.llm import ClaudeClient` gets the legacy one. `from kosmos.core.providers.anthropic import ClaudeClient` gets the provider one.

7. **[FACT: async_llm.py:337, async_llm.py:372] AsyncClaudeClient is isolated from the provider system.** It instantiates `AsyncAnthropic` directly, returns `str` not `LLMResponse`, and has its own retry/circuit-breaker/rate-limiter stack. Changes to the provider system do not affect async batch operations.

8. **[FACT: anthropic.py:698-770] Streaming emits events to a global event bus.** `AnthropicProvider.generate_stream()` tries to import `kosmos.core.events` and `kosmos.core.event_bus` for real-time token streaming events. If the event system is not available, streaming works silently without events. This creates an invisible coupling to the event system.

9. **[FACT: litellm_provider.py:156-168, 205-220] Qwen model special-casing.** LiteLLM provider injects "Do not use thinking mode" into system prompts for any model with "qwen" in its name, and enforces minimum 8192 max_tokens. This happens silently and will affect any Qwen model regardless of version.

10. **[FACT: llm.py:519, anthropic.py:597-612] Cost estimation hardcodes "claude-sonnet-4-5".** `ClaudeClient._estimate_cost()` and `get_usage_stats()` both pass the literal string `"claude-sonnet-4-5"` to `get_model_cost()` regardless of which model was actually used. If haiku was auto-selected, cost is still estimated at sonnet rates. The `AnthropicProvider._calculate_cost()` correctly passes the actual model name.
# Pillar Module: `kosmos/core/logging.py`

**Rank**: #1 architectural pillar (~111 direct `import logging` users across the codebase, plus indirect dependents via root logger configuration)

## What This Module Does

Provides the logging infrastructure for the entire Kosmos codebase: a JSON structured formatter for machine-parseable logs, a colored text formatter for terminal development, rotating file handlers, async-safe correlation ID tracing via `contextvars`, and an experiment lifecycle logger. Every module in the codebase that calls `logging.getLogger(__name__)` gets its output shaped by the formatters and handlers configured here.

## Public API -- Behavioral Descriptions

### `correlation_id: contextvars.ContextVar[Optional[str]]` (module-level)
- [FACT] file:line 23-25. A `ContextVar` with default `None`, keyed `'correlation_id'`.
- **Behavior**: Provides async-safe request tracing. When set, `JSONFormatter.format()` includes it in every JSON log record (line 62-64).
- **Preconditions**: Must be set via `.set()` before log calls to appear in output.
- **Side effects**: None on its own; purely a read target for `JSONFormatter`.
- **Gotcha**: The agents subsystem has its own `correlation_id` field on `AgentMessage` (kosmos/agents/base.py:65) which is NOT the same object. Those are message-level IDs, not the contextvars-based log tracing ID. No code in `kosmos/` actually calls `correlation_id.set()` on the logging module's ContextVar -- [ABSENCE] searched for `correlation_id.set` across kosmos/; only test files reference it. The feature is wired but appears unused in production code.

### `class LogFormat(str, Enum)` (line 28-31)
- **Behavior**: Two values: `JSON = "json"`, `TEXT = "text"`. Used as parameter to `setup_logging()`.
- **Preconditions**: None.
- **Side effects**: None (enum definition only).

### `class JSONFormatter(logging.Formatter)` (line 34-82)
- **Behavior**: Formats `logging.LogRecord` into a JSON string with fields: `timestamp`, `level`, `logger`, `message`, `module`, `function`, `line`.
- **Enrichment fields** (conditionally added):
  - `correlation_id` -- from the module-level `ContextVar` (line 62-64)
  - `workflow_id`, `cycle`, `task_id` -- from `hasattr(record, ...)` checks (line 71-76)
  - `exception` -- from `record.exc_info` (line 68-69)
  - `extra` -- from `hasattr(record, "extra")` (line 79-80)
- **Gotcha**: [FACT] line 52: Uses `datetime.utcfromtimestamp()` which is deprecated in Python 3.12+. Future Python versions may break this.
- **Gotcha**: [FACT] line 71-76: The `workflow_id`, `cycle`, `task_id` fields are checked via `hasattr` on the log record, but no code in `kosmos/` sets these attributes on log records. Searched for `record.workflow_id`, `record.cycle`, `record.task_id` assignments -- [ABSENCE]. This appears to be forward-wired infrastructure that is not yet used.

### `class TextFormatter(logging.Formatter)` (line 85-130)
- **Behavior**: ANSI-colored human-readable formatter. Colors: DEBUG=Cyan, INFO=Green, WARNING=Yellow, ERROR=Red, CRITICAL=Magenta.
- **Preconditions**: `use_colors=True` (default) AND `sys.stdout.isatty()` must both be true for colors to render. Otherwise plain text.
- **Side effects**: Mutates `record.levelname` in-place (line 128) to add ANSI codes. This is a standard logging pattern but means the same record object, if passed to multiple handlers, would have colored level names in all handlers.
- **Gotcha**: [FACT] line 128: The `record.levelname` mutation is permanent on the record object. If a second handler reads the same record after `TextFormatter`, it sees ANSI escape codes in the level name.

### `setup_logging(level, log_format, log_file, debug_mode) -> logging.Logger` (line 133-217)
- **Behavior**: Configures the Python root logger. Clears all existing handlers (line 179), attaches a stdout `StreamHandler`, and optionally a `RotatingFileHandler` (10MB max, 5 backups).
- **Preconditions**: Should be called once at startup. Calling it again clears all previously registered handlers.
- **Side effects**:
  - [FACT] line 179: `root_logger.handlers = []` -- destructively clears all existing handlers.
  - Creates log directory on disk if `log_file` is specified (line 197).
  - Emits an INFO log "Logging initialized" as first message (line 210).
- **Parameters**:
  - `level`: String log level name, uppercased via `getattr(logging, level.upper())` (line 176).
  - `log_format`: `LogFormat.JSON` (default) or `LogFormat.TEXT`.
  - `log_file`: If provided, creates rotating file handler.
  - `debug_mode`: Overrides level to DEBUG, sets console handler to DEBUG.
- **Return**: The root `logging.Logger` instance.

### `get_logger(name: str) -> logging.Logger` (line 220-239)
- **Behavior**: Thin wrapper around `logging.getLogger(name)`. Returns a child logger that inherits root logger's handlers/level.
- **Preconditions**: `setup_logging()` should have been called first, otherwise default logging config applies.
- **Side effects**: None beyond stdlib logger creation.

### `class ExperimentLogger` (line 242-380)
- **Behavior**: Domain-specific logger for tracking experiment lifecycle events. Wraps a stdlib logger (named `kosmos.experiment` by default) and accumulates structured events in memory.
- **Methods**:
  - `start()` -- records start timestamp, logs INFO.
  - `log_hypothesis(hypothesis)` -- appends event, logs INFO with hypothesis text.
  - `log_experiment_design(design)` -- appends event, logs INFO.
  - `log_execution_start()` -- appends event, logs INFO.
  - `log_result(result)` -- appends event with result dict, logs INFO.
  - `log_error(error)` -- appends event, logs ERROR.
  - `end(status)` -- records end timestamp, computes duration, logs INFO with summary.
  - `get_summary()` -- returns dict with experiment_id, timestamps, duration, event count, full event list.
- **Preconditions**: `start()` must be called before `end()` or duration computation returns 0 (line 353).
- **Side effects**: Accumulates events in `self.events: list[Dict]` (grows unbounded).
- **Gotcha**: [ABSENCE] `ExperimentLogger` is NOT imported or used anywhere in `kosmos/` source code outside its own file and tests. It exists as available infrastructure but has no production consumers.

### `configure_from_config()` (line 383-403)
- **Behavior**: Deferred-import bridge that reads logging config from `kosmos.config.get_config()` and calls `setup_logging()` with those values.
- **Preconditions**: `kosmos.config` must be importable and config must have `.logging.level`, `.logging.format`, `.logging.file`, `.logging.debug_mode` attributes.
- **Side effects**: Same as `setup_logging()`.
- **Gotcha**: [ABSENCE] Not called anywhere in kosmos/ source code. Only referenced in its own docstring. The CLI (kosmos/cli/main.py) has its own independent `setup_logging()` function (line 49) that uses `logging.basicConfig()` instead.

## Runtime Dependencies

- Python stdlib only: `contextvars`, `logging`, `logging.handlers`, `json`, `sys`, `datetime`, `pathlib`, `enum`, `typing`
- Deferred import (only in `configure_from_config`): `kosmos.config.get_config` (line 397)

No external packages required. Zero pip dependencies.

## What Breaks If You Change It

1. **All 111+ modules** use `import logging; logger = logging.getLogger(__name__)`. They depend on the root logger configuration set by `setup_logging()`. Changing handler setup, formatter output, or log levels affects every module's log output.

2. **JSON log consumers**: Any log aggregation, monitoring, or parsing system that reads JSON-formatted logs would break if `JSONFormatter`'s field names or structure changed. The fields `timestamp`, `level`, `logger`, `message`, `module`, `function`, `line` are the contract.

3. **CLI log pipeline**: `kosmos/cli/main.py` has its OWN `setup_logging()` (line 49) that uses `logging.basicConfig()` with a different format string (`%(asctime)s - %(name)s - %(levelname)s - %(message)s`). This means the CLI does NOT use `kosmos.core.logging.setup_logging()`. The two logging configurations could conflict if both are called.

4. **File rotation**: Changing the 10MB / 5 backup rotation policy affects disk usage for any deployment relying on the current behavior.

## How Other Modules Use It (Importer Patterns)

### Pattern 1: Standard `getLogger(__name__)` -- [PATTERN] 111 files
Every module does:
```python
import logging
logger = logging.getLogger(__name__)
```
Then uses `logger.info(...)`, `logger.debug(...)`, `logger.error(...)`, `logger.warning(...)`.
Examples: `kosmos/core/workflow.py:15`, `kosmos/agents/base.py:22`, `kosmos/execution/executor.py:21`, `kosmos/core/llm.py:38`, `kosmos/cli/main.py:12`.

### Pattern 2: Import-time logging for optional dependencies -- [PATTERN] 3+ files
```python
try:
    from kosmos.execution.sandbox import DockerSandbox
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False
    logger.warning("Docker sandbox not available.")
```
Example: `kosmos/execution/executor.py:24-29` (sandbox), line 32-37 (R executor). These log at import time, meaning the root logger must already be configured or the messages are lost.

### Pattern 3: CLI's independent setup -- [PATTERN] 1 file (critical path)
`kosmos/cli/main.py:49-93` defines its own `setup_logging()` that does NOT delegate to `kosmos.core.logging.setup_logging()`. It uses `logging.basicConfig()` with hardcoded format. This is the actual logging setup that runs when users invoke `kosmos` CLI commands.

### Pattern 4: Agent correlation IDs (parallel concept, different mechanism)
`kosmos/agents/base.py:65` and `kosmos/agents/registry.py:275` use `correlation_id` as a field name on `AgentMessage`, but this is a Pydantic model field, NOT the `contextvars.ContextVar` from `kosmos/core/logging.py`. The two are conceptually related but mechanically independent.

## Key Gotchas

1. **[FACT] CLI bypasses this module**: `kosmos/cli/main.py:49-93` has its own `setup_logging()` using `logging.basicConfig()`. The `kosmos.core.logging.setup_logging()` and `configure_from_config()` are never called in the main CLI path. This means `JSONFormatter`, `TextFormatter`, and the correlation ID feature are effectively unused in CLI-initiated runs.

2. **[FACT] `ExperimentLogger` has zero production consumers**: Defined at line 242, imported only in test files. No module in `kosmos/` instantiates it.

3. **[FACT] `configure_from_config()` has zero callers**: Defined at line 383, never invoked outside docstrings/tests.

4. **[FACT] `correlation_id` ContextVar is never `.set()` in production**: The wiring exists in `JSONFormatter` (line 62-64) but no kosmos source code sets the value.

5. **[FACT] `datetime.utcfromtimestamp()` at line 52**: Deprecated since Python 3.12. Will emit `DeprecationWarning` and may be removed in future Python versions.

6. **[FACT] `TextFormatter` mutates `record.levelname` at line 128**: If multiple handlers process the same record, subsequent handlers see ANSI codes in the level name.

7. **[FACT] `setup_logging()` clears all handlers at line 179**: `root_logger.handlers = []` is destructive. Any handler added by other code before `setup_logging()` runs (e.g., import-time `logger.warning()` calls in executor.py) would have already used default handlers, and those handlers get wiped.
# kosmos/models/ -- Core Data Models (Pillar #2)

## Directory Contents

| File | Lines | Purpose |
|------|-------|---------|
| `hypothesis.py` | 332 | Hypothesis lifecycle: generation, scoring, evolution tracking |
| `experiment.py` | 700 | Experiment design: protocols, variables, statistical tests, validation |
| `result.py` | 378 | Experiment results: statistical outcomes, execution metadata, export |
| `domain.py` | 392 | Scientific domain classification and routing |
| `safety.py` | 215 | Safety violations, approvals, emergency stops |
| `__init__.py` | 26 | Only re-exports domain.py models (not hypothesis/experiment/result) |

---

## Dual-Model Architecture

[FACT] Every core concept has TWO model representations:

1. **Pydantic models** in `kosmos/models/` -- runtime validation, LLM I/O, rich behavior
2. **SQLAlchemy models** in `kosmos/db/models.py` -- database persistence, relationships

These are NOT automatically synchronized. Conversion between them is manual via `to_dict()` methods on the Pydantic side and direct column mapping on the SQLAlchemy side. The DB models are simpler (fewer fields, no validators), while the Pydantic models carry the full field set with constraints.

---

## hypothesis.py -- The Most-Imported Model

**Behavior**: Represents a testable scientific hypothesis with lifecycle tracking, scoring (novelty/testability/confidence/priority), evolution lineage (parent-child refinement chains), and literature context. Serves as the central data object connecting generation, experimentation, and analysis.

### Import Count
- [FACT] 27 source files inside `kosmos/` import from `kosmos.models.hypothesis` (30 import statements; `research_director.py` has 4 separate import lines). File: grep across `kosmos/`.
- Additional ~25 importers in `tests/`, `evaluation/`, `docs/`, and `onboarding/`.

### Classes Defined

| Class | Role |
|-------|------|
| `ExperimentType(str, Enum)` | 3 values: `computational`, `data_analysis`, `literature_synthesis` |
| `HypothesisStatus(str, Enum)` | 6 values: `generated`, `under_review`, `testing`, `supported`, `rejected`, `inconclusive` |
| `Hypothesis(BaseModel)` | Core model -- 22 fields |
| `HypothesisGenerationRequest(BaseModel)` | Request envelope for hypothesis generation |
| `HypothesisGenerationResponse(BaseModel)` | Response envelope with list of hypotheses + quality metrics |
| `NoveltyReport(BaseModel)` | Detailed novelty analysis for a hypothesis |
| `TestabilityReport(BaseModel)` | Testability assessment with resource estimates |
| `PrioritizedHypothesis(BaseModel)` | Wrapper adding priority scoring with weighted components |

### Hypothesis Field Catalog

**Required fields** (no defaults):
- `research_question: str` -- the originating question
- `statement: str` -- min 10 chars, max 500 chars; validated to not end with `?`
- `rationale: str` -- min 20 chars; scientific justification
- `domain: str` -- free-text domain label (not the `ScientificDomain` enum)

**Status/lifecycle**:
- `status: HypothesisStatus` -- defaults to `GENERATED`
- `id: Optional[str]` -- defaults to `None` (set externally after creation)

**Scoring (all Optional[float], 0.0-1.0)**:
- `testability_score`, `novelty_score`, `confidence_score`, `priority_score`

**Experiment linkage**:
- `suggested_experiment_types: List[ExperimentType]` -- default empty
- `estimated_resources: Optional[Dict[str, Any]]` -- unstructured compute/time/cost

**Literature linkage**:
- `related_papers: List[str]` -- paper IDs used during generation
- `similar_work: List[str]` -- paper IDs found during novelty check
- `novelty_report: Optional[str]`

**Evolution tracking (Phase 7)**:
- `parent_hypothesis_id: Optional[str]` -- links to parent if refined/spawned
- `generation: int` -- defaults to 1; incremented for refinements
- `refinement_count: int` -- defaults to 0
- `evolution_history: List[Dict[str, Any]]` -- append-only log of refinement events

**Metadata**:
- `created_at: datetime` -- `datetime.utcnow` at instantiation
- `updated_at: datetime` -- `datetime.utcnow` at instantiation (NOT auto-updated)
- `generated_by: str` -- defaults to `"hypothesis_generator"`

### Validation Rules

[FACT: hypothesis.py:86-103] `validate_statement`:
- Rejects empty/whitespace-only statements
- Rejects statements ending with `?` (must be declarative, not interrogative)
- Checks for predictive words (`will`, `would`, `should`, `increases`, etc.) but does NOT reject if missing -- silent pass

[FACT: hypothesis.py:105-115] `validate_rationale`:
- Rejects empty/whitespace-only
- Enforces min 20 chars (redundant with Field min_length=20, but explicit)
- Both validators call `.strip()` on the return value

### Serialization

[FACT: hypothesis.py:117-142] `to_dict()` is a hand-rolled serializer, NOT `model_dump()`. It:
- Converts `status` to `.value` (string)
- Converts `suggested_experiment_types` list items to `.value`
- Converts `created_at`/`updated_at` to `.isoformat()`
- Returns all fields explicitly (no dynamic introspection)

[FACT: hypothesis.py:156] `model_config = ConfigDict(use_enum_values=False)` -- enums stay as enum objects in memory, NOT auto-coerced to strings. This matters because `.status` is an `HypothesisStatus` object, not a string, until `to_dict()` is called.

### Helper Methods

- `is_testable(threshold=0.3)` -- returns False if score is None
- `is_novel(threshold=0.5)` -- returns False if score is None

### PrioritizedHypothesis Weights

[FACT: hypothesis.py:315-319] Default priority weights:
```
novelty: 0.30, feasibility: 0.25, impact: 0.25, testability: 0.20
```
`update_hypothesis_priority()` mutates the wrapped hypothesis's `priority_score` and `updated_at`.

---

## experiment.py -- Experiment Protocol Design

**Behavior**: Defines the complete specification for designing and validating experiments that test hypotheses. Models the experimental method: variables, control groups, protocol steps, statistical tests, resource requirements, and scientific rigor validation.

### Import Count
- [FACT] 19 source files inside `kosmos/` import from `kosmos.models.experiment`.

### Key Classes

| Class | Role |
|-------|------|
| `VariableType(str, Enum)` | 4 values: `independent`, `dependent`, `control`, `confounding` |
| `StatisticalTest(str, Enum)` | 9 values including `CUSTOM` |
| `Variable(BaseModel)` | Experiment variable with type, values, units |
| `ControlGroup(BaseModel)` | Control group spec with variable settings and rationale |
| `ProtocolStep(BaseModel)` | Single step with ordering, dependencies, code hints |
| `ResourceRequirements(BaseModel)` | Compute, memory, GPU, cost, data, library requirements |
| `StatisticalTestSpec(BaseModel)` | Full statistical test specification with power analysis |
| `ValidationCheck(BaseModel)` | Rigor check (type, severity, status, recommendation) |
| `ExperimentProtocol(BaseModel)` | **The main model** -- complete experimental protocol |
| `ExperimentDesignRequest(BaseModel)` | Request envelope for experiment design |
| `ExperimentDesignResponse(BaseModel)` | Response with protocol + validation results |
| `ValidationReport(BaseModel)` | Comprehensive rigor assessment |

### ExperimentProtocol Key Fields

**Identity**: `id`, `name` (min 5 chars), `hypothesis_id` (required FK-like reference)
**Type**: `experiment_type: ExperimentType` (imported from hypothesis.py), `domain: str`
**Design**: `steps: List[ProtocolStep]` (min 1), `variables: Dict[str, Variable]`, `control_groups`, `statistical_tests`
**Statistical**: `sample_size` (max 100,000), `power_analysis_performed`
**Resources**: `resource_requirements: ResourceRequirements` (required, not optional)
**Rigor**: `validation_checks`, `rigor_score` (0-1)
**Reproducibility**: `random_seed`, `reproducibility_notes`

### LLM-Defensive Validators

[FACT: experiment.py:106-125] `ControlGroup.coerce_sample_size`: LLMs sometimes return sample_size as a string. This validator coerces strings to int, and clamps values exceeding `_MAX_SAMPLE_SIZE` (100,000) rather than rejecting them. Returns None if coercion fails.

[FACT: experiment.py:265-273] `StatisticalTestSpec.coerce_groups`: Coerces comma-separated string groups from LLM output to a proper list.

[FACT: experiment.py:283-299] `StatisticalTestSpec.parse_effect_size`: Extracts numeric values from free-text LLM responses like `"Medium (Cohen's d = 0.5)"` using regex.

[FACT: experiment.py:176-182] `ProtocolStep.ensure_title`: Replaces empty/too-short titles with `"Untitled Step"` instead of rejecting.

These are all `mode='before'` validators -- they run BEFORE Pydantic's type validation, specifically to handle messy LLM output.

### Step Ordering Validation

[FACT: experiment.py:424-438] `ExperimentProtocol.validate_steps`:
- Requires at least one step
- Validates step numbers are sequential 1..N with no gaps or duplicates
- Auto-sorts steps by `step_number` after validation

### Serialization

[FACT: experiment.py:471-573] `ExperimentProtocol.to_dict()` is a massive hand-rolled serializer (~100 lines) that manually converts every nested model. Does NOT use `model_dump()`.

[FACT: experiment.py:575] Same `ConfigDict(use_enum_values=False)` as hypothesis.

---

## result.py -- Experiment Results

**Behavior**: Captures the complete output of running an experiment: raw/processed data, statistical test results with significance levels, variable summary statistics, execution metadata (timing, system info, resource usage), and interpretation. Also provides multi-format export (JSON, CSV, Markdown).

### Import Count
- [FACT] 11 source files inside `kosmos/` import from `kosmos.models.result`.

### Key Classes

| Class | Role |
|-------|------|
| `ResultStatus(str, Enum)` | 5 values: `success`, `failed`, `partial`, `timeout`, `error` |
| `ExecutionMetadata(BaseModel)` | System info, timing, resource usage, IDs |
| `StatisticalTestResult(BaseModel)` | Individual test outcome with p-value, effect size, significance flags |
| `VariableResult(BaseModel)` | Per-variable summary stats (mean, median, std, min, max) |
| `ExperimentResult(BaseModel)` | **The main model** -- complete result with all above |
| `ResultExport(BaseModel)` | Multi-format exporter (JSON, CSV, Markdown) |

### ExperimentResult Key Fields

**Identity**: `id`, `experiment_id` (required), `protocol_id` (required), `hypothesis_id` (optional)
**Status**: `status: ResultStatus` (required)
**Data**: `raw_data: Dict`, `processed_data: Dict`
**Variables**: `variable_results: List[VariableResult]`
**Statistics**: `statistical_tests: List[StatisticalTestResult]`, `primary_test`, `primary_p_value`, `primary_effect_size`, `primary_ci_lower`, `primary_ci_upper`
**Verdict**: `supports_hypothesis: Optional[bool]`
**Execution**: `metadata: ExecutionMetadata` (required)
**Output**: `stdout`, `stderr`, `generated_files: List[str]`
**Interpretation**: `summary`, `interpretation`, `recommendations`

### Serialization Quirk

[FACT: result.py:241-243] `ExperimentResult.to_dict()` uses `kosmos.utils.compat.model_to_dict()` with `mode='json'` and `exclude_none=True`. This is DIFFERENT from hypothesis.py and experiment.py which use hand-rolled serializers. The compat helper tries `model_dump()` first (Pydantic v2), then falls back to `.dict()` (v1).

[FACT: result.py:245-257] Also provides `to_json()`, `from_dict()`, `from_json()` class methods -- hypothesis and experiment models do NOT have `from_dict()`/`from_json()`.

### Validation

[FACT: result.py:206-214] `validate_statistical_tests`: Rejects duplicate test names in the list.

[FACT: result.py:216-228] `validate_primary_test`: If `primary_test` is set, validates it exists in `statistical_tests`. Handles both dict and model instances in `info.data` (Pydantic v2 raw-dict behavior).

### StatisticalTestResult Significance Flags

[FACT: result.py:83-86] Three pre-computed boolean significance flags:
- `significant_0_05`, `significant_0_01`, `significant_0_001`
- Plus `significance_label` string (e.g., "**", "*", "ns")
- Plus `is_primary: bool` flag for primary test designation

### ResultExport CSV Dependency

[FACT: result.py:292-310] `ResultExport.export_csv()` imports `pandas` at runtime. This is the ONLY external dependency reference in the models package. It will crash with ImportError if pandas is not installed and CSV export is attempted.

---

## Relationships Between The Trio

```
Hypothesis  ──1:N──>  ExperimentProtocol  (via hypothesis_id string)
                            │
ExperimentProtocol  ──1:N──>  ExperimentResult  (via protocol_id + experiment_id strings)
                                     │
ExperimentResult  ──references──>  Hypothesis  (via hypothesis_id, optional)
```

- [FACT] All cross-references are string IDs, not object references. There are no Pydantic model fields that hold references to other Pydantic models (except `PrioritizedHypothesis.hypothesis: Hypothesis` and `HypothesisGenerationResponse.hypotheses: List[Hypothesis]`).
- [FACT: hypothesis.py:15-19] `ExperimentType` is defined in hypothesis.py but imported by experiment.py (line 14). This creates a one-way dependency: experiment.py depends on hypothesis.py, but NOT vice versa.
- [FACT] result.py imports from neither hypothesis.py nor experiment.py. It is fully independent at the import level. It references them only by string IDs.
- [FACT: db/models.py:49,68-69] In the DB layer, `Experiment.hypothesis_id` is a true ForeignKey to `hypotheses.id` with a SQLAlchemy relationship and cascade delete on results. The Pydantic models have no such enforcement.

---

## Gotchas

### 1. HypothesisStatus enum mismatch between Pydantic and DB
[FACT: hypothesis.py:22-29 vs db/models.py:31-37]
- Pydantic `HypothesisStatus` has 6 values: `generated`, `under_review`, `testing`, `supported`, `rejected`, `inconclusive`
- DB `HypothesisStatus` has 5 values: `generated`, `testing`, `supported`, `rejected`, `inconclusive`
- **`under_review` exists ONLY in the Pydantic model**. Setting a hypothesis to `under_review` and persisting it to the DB will fail or produce unexpected behavior. [FACT: grep confirms `under_review` appears in exactly 1 place in the entire codebase: hypothesis.py:25]

### 2. priority_score missing from DB model
[FACT: db/models.py:75-107] The DB `Hypothesis` model has `novelty_score`, `testability_score`, `confidence_score` but NOT `priority_score`. The Pydantic model has all four. Priority scores computed by `PrioritizedHypothesis` cannot be persisted via the DB model without schema migration.

### 3. updated_at is NOT auto-updating
[FACT: hypothesis.py:77] `updated_at` defaults to `datetime.utcnow` at object creation but is never automatically updated when fields change. Only `PrioritizedHypothesis.update_hypothesis_priority()` (line 331) manually sets it. The DB model has `onupdate=datetime.utcnow` but the Pydantic model does not.

### 4. Inconsistent datetime usage across models
[FACT: grep across kosmos/models/] hypothesis.py, experiment.py, and result.py use `datetime.utcnow` (deprecated in Python 3.12+). domain.py and safety.py use `datetime.now` (local time). These will produce different timestamps if compared across model boundaries in non-UTC timezones.

### 5. Inconsistent serialization strategies
[FACT] Three different serialization approaches in one package:
- `hypothesis.py` and `experiment.py`: hand-rolled `to_dict()` with explicit field mapping
- `result.py`: `model_to_dict()` via compat helper using `model_dump(mode='json', exclude_none=True)`
- `result.py` also has `to_json()`/`from_json()`/`from_dict()` class methods; the others don't

### 6. ExperimentType lives in hypothesis.py
[FACT: hypothesis.py:15-19] `ExperimentType` (computational, data_analysis, literature_synthesis) is defined in hypothesis.py but is conceptually an experiment concern. All 19 experiment.py importers also need to import from hypothesis.py (or get it re-exported through experiment.py line 14). If you move this enum, you break 27+ files.

### 7. __init__.py only exports domain models
[FACT: __init__.py:1-26] `kosmos/models/__init__.py` only re-exports `domain.py` classes. Hypothesis, Experiment, and Result models are NOT available via `from kosmos.models import Hypothesis`. All consumers must use the full module path (e.g., `from kosmos.models.hypothesis import Hypothesis`).

### 8. _MAX_SAMPLE_SIZE is module-level in experiment.py
[FACT: experiment.py:19] `_MAX_SAMPLE_SIZE = 100_000` is a module-level constant used by both `ControlGroup.coerce_sample_size` and `ExperimentProtocol.coerce_protocol_sample_size` and also as `le=_MAX_SAMPLE_SIZE` in `ExperimentProtocol.sample_size` Field constraint. Changing this value affects both soft clamping (validators) and hard rejection (Field constraint).

### 9. ResultExport.export_csv has runtime pandas dependency
[FACT: result.py:292] `import pandas as pd` inside method body. The project otherwise has no pandas requirement at the models layer. This will fail at runtime if pandas is not installed and someone calls `.export_csv()`.

### 10. No evolution_history in DB schema
[FACT: db/models.py:75-107] The DB Hypothesis model has no columns for `parent_hypothesis_id`, `generation`, `refinement_count`, or `evolution_history`. All Phase 7 evolution tracking fields exist only in the Pydantic model and are lost on DB persistence unless stored in a JSON column not shown in the schema.

---

## What Breaks If You Change These Models

**hypothesis.py** (27 importers in kosmos/, ~25 more in tests):
- Renaming/removing `Hypothesis` fields breaks: hypothesis_generator, experiment_designer, data_analyst, research_director, all 4 hypothesis/ sub-modules (refiner, prioritizer, novelty_checker, testability), convergence, memory, feedback, world_model, code_generator, summarizer, and all experiment templates
- Changing `ExperimentType` enum values breaks experiment.py and all 18 template/experiment importers
- Changing `HypothesisStatus` values breaks refiner, research_director, memory, feedback, convergence
- Changing `to_dict()` output keys breaks anything that deserializes hypothesis dicts (world_model, DB persistence paths)

**experiment.py** (19 importers):
- Changing `ExperimentProtocol` breaks: experiment_designer, experiment templates (8 files), validator, code_generator, result_collector, memory, research_director
- Changing `Variable`/`VariableType` breaks templates and code_generator
- Changing `StatisticalTestSpec` breaks validator and templates
- The LLM-defensive validators (coerce_sample_size, coerce_groups, parse_effect_size) protect against LLM output variance -- removing them will cause validation failures on real LLM-generated experiment designs

**result.py** (11 importers):
- Changing `ExperimentResult` breaks: result_collector, data_analyst, summarizer, visualization, research_director, verifier, refiner, convergence, memory, feedback
- Changing `ResultStatus` enum breaks: feedback, verifier, refiner, convergence
- Changing `StatisticalTestResult` breaks: visualization, data_analyst, result_collector
# Module Deep Read: kosmos/agents/research_director.py

## What This Module Does

[FACT: file:1-13] The ResearchDirectorAgent is the master orchestrator for Kosmos's autonomous research loop. It coordinates six specialized agents/utilities (hypothesis generator, experiment designer, code executor, data analyst, hypothesis refiner, convergence detector) through a state-machine-driven iteration cycle, deciding at each step what action to take next and delegating work accordingly.

It is the single entry point for running a full autonomous research session: given a research question and optional domain, it generates hypotheses, designs and executes experiments, analyzes results, refines hypotheses, and repeats until convergence criteria are met or resource limits are hit.

---

## Agent Lifecycle

### 1. Initialization (`__init__`, lines 68-260)

The constructor performs heavy setup:

- **[FACT: line 84-88]** Calls `super().__init__()` with `agent_type="ResearchDirector"`.
- **[FACT: lines 93-98]** Validates domain against `config["enabled_domains"]` (defaults: biology, physics, chemistry, neuroscience) and loads domain-specific skills via `SkillLoader`.
- **[FACT: lines 104-113]** Reads config for `max_iterations` (default 10), `max_runtime_hours` (default 12.0), mandatory stopping criteria (`["iteration_limit", "no_testable_hypotheses"]`), and optional stopping criteria (`["novelty_decline", "diminishing_returns"]`).
- **[FACT: lines 116-125]** Creates a `ResearchPlan` (Pydantic model, defined in `kosmos.core.workflow`) and a `ResearchWorkflow` state machine starting at `WorkflowState.INITIALIZING`.
- **[FACT: line 128]** Acquires an LLM client via `get_client()` for research planning prompts.
- **[FACT: lines 131-139]** Initializes the database via `init_from_config()`, silently swallowing "already initialized" errors.
- **[FACT: lines 142-151]** Creates agent registry dict and seven lazy-init agent slots (`_hypothesis_agent`, `_experiment_designer`, `_code_generator`, `_code_executor`, `_data_provider`, `_data_analyst`, `_hypothesis_refiner`), all initially `None`.
- **[FACT: lines 156-165]** Initializes strategy effectiveness stats for 4 strategies (hypothesis_generation, experiment_design, hypothesis_refinement, literature_review) and a `RolloutTracker`.
- **[FACT: lines 167-178]** Creates a `ConvergenceDetector` utility directly (not as a message-receiving agent).
- **[FACT: lines 192-200]** Creates both `asyncio.Lock` and `threading.RLock`/`Lock` for thread-safe access to research_plan, strategy_stats, workflow, and agent_registry. The async locks are for the async code path; threading locks are for backwards compatibility.
- **[FACT: lines 203-240]** If `enable_concurrent_operations` is configured: imports and initializes `ParallelExperimentExecutor` and `AsyncClaudeClient`.
- **[FACT: lines 242-255]** Initializes the world model (knowledge graph) and persists the research question as an `Entity`.

### 2. Start (`_on_start`, lines 319-332)

- Records `_start_time` for runtime tracking.
- Transitions workflow state from INITIALIZING to GENERATING_HYPOTHESES.

### 3. Execute Entry Point (`execute`, lines 2868-2909)

- `execute({"action": "start_research"})`: Generates initial research plan via LLM, calls `self.start()`, then enters the loop by calling `decide_next_action()` followed by `_execute_next_action()`.
- `execute({"action": "step"})`: Runs a single step of the research loop.
- `execute_sync()` (line 2911): Synchronous wrapper using `asyncio.run_coroutine_threadsafe` or `asyncio.run`.

### 4. Research Loop: decide_next_action -> _execute_next_action -> _do_execute_action

**[FACT: lines 2388-2548]** `decide_next_action()` is a deterministic decision tree based on workflow state:

```
Budget check -> Runtime check -> Loop guard (MAX_ACTIONS_PER_ITERATION=50)
  -> _should_check_convergence()
  -> State-based routing:
     GENERATING_HYPOTHESES -> GENERATE_HYPOTHESIS
     DESIGNING_EXPERIMENTS -> DESIGN_EXPERIMENT (or fallbacks)
     EXECUTING            -> EXECUTE_EXPERIMENT (or fallbacks)
     ANALYZING            -> ANALYZE_RESULT (or fallbacks)
     REFINING             -> REFINE_HYPOTHESIS (or GENERATE_HYPOTHESIS)
     CONVERGED            -> CONVERGE
     ERROR                -> ERROR_RECOVERY
```

**[FACT: lines 2550-2734]** `_execute_next_action()` wraps `_do_execute_action()` with stage tracking. `_do_execute_action()` dispatches to the appropriate `_handle_*_action()` method, each of which:
1. Lazy-initializes the relevant agent/utility.
2. Calls it directly (not via message passing -- Issue #76 fix).
3. On success: resets error streak, updates research plan (thread-safe), persists to knowledge graph, updates strategy stats.
4. On failure: calls `_handle_error_with_recovery()`.

### 5. Convergence and Stop

**[FACT: lines 1334-1389]** `_handle_convergence_action()`:
1. Applies Benjamini-Hochberg FDR multiple-comparison correction to recent p-values.
2. Calls `_check_convergence_direct()` which delegates to `self.convergence_detector.check_convergence()`.
3. If `should_stop`: sets `research_plan.has_converged = True`, annotates knowledge graph, transitions to `WorkflowState.CONVERGED`, calls `self.stop()`.
4. If not converged: increments iteration counter and resets `_actions_this_iteration`.

**[FACT: lines 2736-2786]** `_should_check_convergence()` is the pre-filter:
- Skips convergence during active states (DESIGNING, EXECUTING, ANALYZING).
- Checks iteration limit but defers if fewer than `min_experiments_before_convergence` completed and testable work remains.
- Returns True if no untested hypotheses AND no queued experiments.

---

## Non-Obvious Behaviors

### Stopping Criteria (Multiple Layers)
[FACT: lines 2404-2461] There are **four independent halt mechanisms**, checked in order at the top of `decide_next_action()`:
1. **Budget enforcement** -- imports `get_metrics()` and calls `enforce_budget()`. If `BudgetExceededError`, transitions to CONVERGED.
2. **Runtime limit** -- `_check_runtime_exceeded()` compares wall-clock time against `max_runtime_hours` (default 12h).
3. **Loop guard** -- `_actions_this_iteration` counter, capped at `MAX_ACTIONS_PER_ITERATION = 50` (Issue #51 infinite loop prevention). Forces convergence if exceeded.
4. **Convergence detector** -- the actual scientific stopping criteria (iteration limit, no testable hypotheses, novelty decline, diminishing returns).

### Strategy Selection (Unused in Main Loop)
[FACT: lines 2792-2835] `select_next_strategy()` exists and tracks success rates per strategy, but the main `decide_next_action()` uses a deterministic state-machine, not strategy selection. Strategy stats are updated but `select_next_strategy()` is never called by the orchestration loop itself. It appears to be an extension point.

### _actions_this_iteration Is Not Initialized in __init__
[FACT: lines 2451-2452] The `_actions_this_iteration` counter is lazily created via `hasattr()` check inside `decide_next_action()` rather than being set in `__init__`. This is safe but unconventional. It's reset to 0 in two places: after REFINE_HYPOTHESIS (line 2706) and after convergence not-yet-converged (line 1388).

### Message-Based vs Direct-Call Architecture (Dual Pattern)
[FACT: lines 984-2003] The codebase contains **both** message-based sending methods (`_send_to_hypothesis_generator`, `_send_to_experiment_designer`, etc., lines 1039-1219) **and** direct-call handler methods (`_handle_generate_hypothesis_action`, `_handle_design_experiment_action`, etc., lines 1391-1979). Issue #76 discovered that message-based calls silently failed because agents were never registered in the message router. The `_do_execute_action()` now uses direct calls exclusively. The old message-sending methods and response handlers still exist but are effectively dead code.

### Error Recovery Circuit Breaker
[FACT: lines 44-46, 599-684] After `MAX_CONSECUTIVE_ERRORS = 3` consecutive failures, the workflow transitions to ERROR state. Recoverable errors use exponential backoff (`[2, 4, 8]` seconds). `_reset_error_streak()` is called after every successful operation. Error recovery (line 2716-2728) resets the counter and transitions to GENERATING_HYPOTHESES.

### FDR Multiple Comparison Correction
[FACT: lines 1278-1332] Before checking convergence, `_apply_multiple_comparison_correction()` applies Benjamini-Hochberg FDR correction to p-values from recent results. This can retroactively make previously-significant results non-significant, which is logged but does NOT retroactively change hypothesis support/reject status in the research plan.

### World Model Persistence Is Optional
[FACT: lines 242-255, 396-397] All `_persist_*_to_graph()` methods guard with `if not self.wm: return`. If world model initialization fails (line 253), the agent continues without knowledge graph persistence.

### Async/Threading Dual-Lock Pattern
[FACT: lines 192-200] The module maintains **both** asyncio.Lock and threading.Lock/RLock for each protected resource. The sync locks are used in `_research_plan_context()`, `_strategy_stats_context()`, etc. for the direct-call code path, while async locks exist for potential future async context managers. The `_workflow_context()` (line 375-379) is notably a no-op -- it yields without acquiring any lock, just for API compatibility.

### Lazy Agent Initialization
[FACT: lines 1402-1404, 1469-1470, 1537-1543, 1679-1681, 1816-1817] All sub-agents are lazy-initialized on first use. This means the first call to each action handler is slower (agent construction), but avoids paying initialization cost for agents that might never be needed.

---

## What Breaks If You Change It (22 Importers, 0.83 Risk)

### Direct Code Importers (Python files that `from kosmos.agents.research_director import ...`):
- **`kosmos/__init__.py`** (line 18): Top-level package export. Changing the class name or removing the module breaks `import kosmos`.
- **`kosmos/cli/commands/run.py`** (line 128): The CLI `kosmos run` command. Changing constructor signature breaks CLI.
- **`kosmos/agents/__init__.py`** (line 20): Package re-export.
- **`evaluation/scientific_evaluation.py`** (4 import sites): Research evaluation harness.
- **Unit tests** (3 files): `test_research_director.py`, `test_research_director_loops.py`, `test_error_recovery.py`.
- **Integration tests** (5 files): `test_iterative_loop.py`, `test_end_to_end_research.py`, `test_concurrent_research.py`, `test_async_message_passing.py`, `test_world_model_persistence.py`.
- **E2E tests** (1 file): `test_full_research_workflow.py` (3 import sites).
- **Requirements tests** (8 files): orchestrator and performance requirement tests.

### High-Impact Change Risks:
1. **`decide_next_action()` return values**: Every handler calls this, and `_do_execute_action()` dispatches on `NextAction` enum values. Adding/removing enum members requires updating both.
2. **`ResearchPlan` interface**: `research_plan.add_hypothesis()`, `.get_untested_hypotheses()`, `.experiment_queue`, `.results`, `.mark_supported()` etc. are called pervasively. Changing these breaks the loop.
3. **Constructor signature**: `(research_question, domain, agent_id, config)` -- the CLI and evaluation harness pass these positionally.
4. **`get_research_status()` return dict**: Used by CLI and evaluation code for status display.

---

## Runtime Dependencies

### Direct Imports at Module Level (lines 15-41):
| Dependency | Purpose |
|---|---|
| `kosmos.agents.base.BaseAgent` | Parent class |
| `kosmos.utils.compat.model_to_dict` | Pydantic compat utility |
| `kosmos.core.rollout_tracker.RolloutTracker` | Tracks agent invocation counts |
| `kosmos.core.workflow.{ResearchWorkflow, ResearchPlan, WorkflowState, NextAction}` | State machine |
| `kosmos.core.convergence.{ConvergenceDetector, StoppingDecision, StoppingReason}` | Stopping criteria |
| `kosmos.core.llm.get_client` | LLM client factory |
| `kosmos.core.stage_tracker.get_stage_tracker` | Performance/stage tracking |
| `kosmos.models.hypothesis.{Hypothesis, HypothesisStatus}` | Hypothesis data model |
| `kosmos.world_model.{get_world_model, Entity, Relationship}` | Knowledge graph |
| `kosmos.db.{get_session}` | Database session factory |
| `kosmos.db.operations.{get_hypothesis, get_experiment, get_result}` | DB queries |
| `kosmos.agents.skill_loader.SkillLoader` | Domain skill loading |

### Lazy Imports (inside methods):
| Dependency | Where | Purpose |
|---|---|---|
| `kosmos.db.init_from_config` | `__init__` line 131 | DB initialization |
| `kosmos.agents.hypothesis_generator.HypothesisGeneratorAgent` | `_handle_generate_hypothesis_action` line 1399 | Hypothesis generation |
| `kosmos.agents.experiment_designer.ExperimentDesignerAgent` | `_handle_design_experiment_action` line 1465 | Experiment design |
| `kosmos.execution.code_generator.ExperimentCodeGenerator` | `_handle_execute_experiment_action` line 1528 | Code generation |
| `kosmos.execution.executor.CodeExecutor` | same, line 1529 | Code execution |
| `kosmos.execution.data_provider.DataProvider` | same, line 1530 | Data loading |
| `kosmos.agents.data_analyst.DataAnalystAgent` | `_handle_analyze_result_action` line 1673 | Result interpretation |
| `kosmos.hypothesis.refiner.HypothesisRefiner` | `_handle_refine_hypothesis_action` line 1805 | Hypothesis refinement |
| `kosmos.execution.statistics.StatisticalValidator` | `_apply_multiple_comparison_correction` line 1285 | FDR correction |
| `kosmos.core.async_llm.AsyncClaudeClient` | `__init__` line 226 | Concurrent LLM calls |
| `kosmos.execution.parallel.ParallelExperimentExecutor` | `__init__` line 212 | Parallel experiment execution |
| `kosmos.core.metrics.get_metrics` | `decide_next_action` line 2406 | Budget enforcement |
| `kosmos.world_model.models.Annotation` | `_handle_convergence_action` line 1363 | Graph annotations |

---

## Key Methods

| Method | Lines | Behavior |
|---|---|---|
| `__init__` | 68-260 | Heavy constructor: config, DB init, world model, locks, optional concurrency setup |
| `execute` | 2868-2909 | Async entry point: generates LLM plan, starts workflow, kicks first action |
| `execute_sync` | 2911-2920 | Sync wrapper for backwards compat |
| `decide_next_action` | 2388-2548 | Deterministic state-machine decision tree with budget/runtime/loop guards |
| `_execute_next_action` | 2550-2571 | Stage-tracked dispatch wrapper |
| `_do_execute_action` | 2573-2734 | Main dispatch: routes NextAction to handler, supports concurrent batches |
| `_handle_generate_hypothesis_action` | 1391-1456 | Lazy-inits HypothesisGeneratorAgent, calls generate_hypotheses(), updates plan/graph/stats |
| `_handle_design_experiment_action` | 1458-1519 | Lazy-inits ExperimentDesignerAgent, calls design_experiment(), updates plan |
| `_handle_execute_experiment_action` | 1521-1664 | Lazy-inits CodeGenerator+CodeExecutor+DataProvider, runs experiment, stores result in DB |
| `_handle_analyze_result_action` | 1666-1794 | Lazy-inits DataAnalystAgent, loads result from DB, interprets, updates hypothesis status |
| `_handle_refine_hypothesis_action` | 1796-1979 | Lazy-inits HypothesisRefiner, evaluates status, may RETIRE/REFINE/SPAWN_VARIANT |
| `_handle_convergence_action` | 1334-1389 | FDR correction, direct convergence check, may stop or increment iteration |
| `_handle_error_with_recovery` | 599-684 | Circuit breaker: counts consecutive errors, exponential backoff, transitions to ERROR after 3 |
| `_should_check_convergence` | 2736-2786 | Pre-filter: skips during active states, defers if min experiments not met |
| `_check_convergence_direct` | 1221-1276 | Loads hypotheses from DB, calls ConvergenceDetector.check_convergence() |
| `generate_research_plan` | 2349-2382 | LLM call to generate initial research strategy |
| `select_next_strategy` | 2792-2816 | Success-rate-based strategy selection (extension point, not called by main loop) |
| `get_research_status` | 2926-2952 | Returns comprehensive status dict for CLI/evaluation |
| `process_message` | 568-593 | Routes incoming messages by sender agent type (legacy, effectively dead code) |
| `_persist_hypothesis_to_graph` | 388-436 | Persists hypothesis entity + SPAWNED_BY relationship to knowledge graph |
| `_persist_protocol_to_graph` | 438-475 | Persists protocol entity + TESTS relationship |
| `_persist_result_to_graph` | 477-524 | Persists result entity + PRODUCED_BY + TESTS relationships |
| `_add_support_relationship` | 526-562 | Adds SUPPORTS or REFUTES relationship based on analysis |
| `execute_experiments_batch` | 2152-2204 | Parallel experiment execution via ParallelExperimentExecutor |
| `evaluate_hypotheses_concurrently` | 2206-2275 | Concurrent LLM hypothesis evaluation via AsyncClaudeClient |
| `analyze_results_concurrently` | 2277-2343 | Concurrent LLM result analysis via AsyncClaudeClient |

---

## Key Instance Variables

| Variable | Type | Role |
|---|---|---|
| `research_question` | str | The driving research question |
| `domain` | Optional[str] | Scientific domain (biology, physics, etc.) |
| `research_plan` | ResearchPlan | Central state: tracks all hypothesis/experiment/result IDs and iteration count |
| `workflow` | ResearchWorkflow | State machine (INITIALIZING -> GENERATING -> DESIGNING -> EXECUTING -> ANALYZING -> REFINING -> loop/CONVERGED) |
| `llm_client` | Claude client | For research plan generation and decision prompts |
| `convergence_detector` | ConvergenceDetector | Utility that evaluates stopping criteria |
| `agent_registry` | Dict[str, str] | Maps agent_type -> agent_id (for message routing, largely unused now) |
| `_hypothesis_agent` | Optional[HypothesisGeneratorAgent] | Lazy-init slot |
| `_experiment_designer` | Optional[ExperimentDesignerAgent] | Lazy-init slot |
| `_code_generator` | Optional[ExperimentCodeGenerator] | Lazy-init slot |
| `_code_executor` | Optional[CodeExecutor] | Lazy-init slot |
| `_data_provider` | Optional[DataProvider] | Lazy-init slot |
| `_data_analyst` | Optional[DataAnalystAgent] | Lazy-init slot |
| `_hypothesis_refiner` | Optional[HypothesisRefiner] | Lazy-init slot |
| `strategy_stats` | Dict[str, Dict] | Per-strategy success/attempt/cost tracking |
| `rollout_tracker` | RolloutTracker | Counts agent invocations by type |
| `iteration_history` | List[Dict] | Historical iteration data (declared but never populated) |
| `_consecutive_errors` | int | Circuit breaker counter |
| `_error_history` | List[Dict] | Full error log |
| `_start_time` | Optional[float] | Wall-clock start for runtime limit |
| `_actions_this_iteration` | int | Loop guard counter (lazy-init, not in __init__) |
| `wm` | Optional[WorldModel] | Knowledge graph, None if init fails |
| `question_entity_id` | Optional[str] | Research question entity in graph |
| `pending_requests` | Dict[str, Dict] | Message correlation tracking (legacy, for message-based pattern) |
| `parallel_executor` | Optional[ParallelExperimentExecutor] | For concurrent experiment execution |
| `async_llm_client` | Optional[AsyncClaudeClient] | For concurrent LLM calls |
| `skills` | Optional[str] | Domain-specific skill text injected into prompts |

---

## Gotchas

1. **[FACT: line 2451-2452] `_actions_this_iteration` lazy init**: This counter is created via `hasattr()` check in `decide_next_action()` instead of `__init__`. If any code path calls `_execute_next_action()` (which reads it via `getattr` on line 2560) before `decide_next_action()` is called, it will get 0 from `getattr` default. Not a crash bug, but could lead to the loop guard not working if the action dispatch path is entered without going through `decide_next_action()` first.

2. **[FACT: line 375-379] `_workflow_context()` acquires no lock**: Unlike `_research_plan_context()` (which uses `_research_plan_lock_sync`) and `_strategy_stats_context()` (which uses `_strategy_stats_lock_sync`), the `_workflow_context()` context manager just does `yield self.workflow` with no lock. All callers of `_workflow_context()` think they have exclusive access, but they do not. The workflow transitions inside `_handle_*_action()` methods are not thread-safe.

3. **[FACT: lines 984-993] Dead code: message-based response handlers**: The six `_handle_*_response()` methods (lines 704-997) and five `_send_to_*()` async methods (lines 1039-1219) are effectively dead code since Issue #76 switched to direct calls. They remain in the file, adding ~600 lines of code that could mislead readers.

4. **[FACT: line 181] `iteration_history` is never populated**: Declared as `List[Dict]` but no method ever appends to it. It's always empty.

5. **[FACT: line 674] Blocking sleep in async context**: `_handle_error_with_recovery()` calls `time.sleep(backoff_seconds)` on line 674, which blocks the event loop in an async context. This should be `await asyncio.sleep()` but the method is sync.

6. **[FACT: lines 228-237] ANTHROPIC_API_KEY used for AsyncClaudeClient**: The async LLM client initialization on line 229 reads `os.getenv("ANTHROPIC_API_KEY")` directly, unlike the main `get_client()` call which uses the config system. This could behave differently depending on environment setup, and conflicts with the Max OAuth pattern described in the user's global instructions.

7. **[FACT: line 2706] Iteration incremented unconditionally after REFINE_HYPOTHESIS**: In `_do_execute_action()`, after the REFINE_HYPOTHESIS handler completes, `research_plan.increment_iteration()` is called unconditionally (even if no refinement actually happened because `tested` was empty on line 2695). This means an empty refinement still advances the iteration counter.

8. **[FACT: lines 1310-1332] FDR correction logs but doesn't update DB**: When Benjamini-Hochberg correction makes results non-significant, it logs the change but doesn't update `supports_hypothesis` in the database or research plan. Downstream consumers see the original significance status.

9. **[FACT: line 568] `process_message` is sync, overriding an async base method**: `BaseAgent.process_message()` is defined as `async def` (line 382 of base.py), but `ResearchDirectorAgent.process_message()` (line 568) is `def` (sync). This means the async message processing path in `BaseAgent.receive_message()` (which `await`s `process_message()`) would fail if used with the director. This is masked because the direct-call pattern bypasses message passing entirely.
# Agent Communication -- Inter-Agent Messaging, Event Bus, Shared State, Orchestration

## 1. Two Parallel Communication Systems

Kosmos has two distinct communication architectures that coexist but serve different purposes:

### 1a. AgentMessage System (Direct Inter-Agent Messaging)

[FACT] `kosmos/agents/base.py:37-85` -- `AgentMessage` is a Pydantic model carrying `from_agent`, `to_agent`, `content` dict, `correlation_id` for request/response tracking, and `MessageType` enum (REQUEST, RESPONSE, NOTIFICATION, ERROR).

[FACT] `kosmos/agents/base.py:246-300` -- `BaseAgent.send_message()` is async. It constructs an `AgentMessage`, increments `messages_sent`, then calls `self._message_router(message)` if one has been set. The router is a callable (sync or async) injected from outside.

[FACT] `kosmos/agents/base.py:329-367` -- `BaseAgent.receive_message()` is async. It appends to both a legacy sync list (`self.message_queue`) and an `asyncio.Queue` (`self._async_message_queue`), then calls `self.process_message(message)`. On error, it auto-replies with a MessageType.ERROR.

[FACT] `kosmos/agents/base.py:417-433` -- `set_message_router()` accepts a sync or async callable. The `AgentRegistry` injects its `_route_message` method here at registration time.

### 1b. EventBus System (Streaming Pub/Sub)

[FACT] `kosmos/core/event_bus.py:28-258` -- `EventBus` is a type-filtered pub/sub system. Subscribers register callbacks optionally filtered by `EventType` and `process_id`. Supports both sync (`publish_sync`) and async (`publish`) publishing. Uses `threading.Lock` for thread safety.

[FACT] `kosmos/core/events.py:16-52` -- `EventType` defines 21 event types across 6 categories: workflow lifecycle (4), research cycles (3), tasks (4), LLM calls (4), code execution (5), and stage tracking (3).

[FACT] `kosmos/core/events.py:59-224` -- Six typed event dataclasses: `WorkflowEvent`, `CycleEvent`, `TaskEvent`, `LLMEvent`, `ExecutionEvent`, `StageEvent`. All inherit from `BaseEvent` which carries `type`, `timestamp`, `process_id`, `correlation_id`.

**Key distinction**: AgentMessage is for agent-to-agent work coordination (generate hypothesis, design experiment). EventBus is for observability/streaming (progress updates, LLM token streaming, stage tracking).

## 2. Agent Registry -- Message Router

[FACT] `kosmos/agents/registry.py:6-7` -- Comment at top: "Reserved for multi-agent message-passing architecture (future work). Not yet integrated into the main research loop."

[FACT] `kosmos/agents/registry.py:70-97` -- `AgentRegistry.register()` stores the agent in `_agents` dict, tracks by type, and calls `agent.set_message_router(self._route_message)` to wire up message delivery.

[FACT] `kosmos/agents/registry.py:230-254` -- `_route_message()` is async. It looks up the target agent by ID, calls `await to_agent.receive_message(message)`, and appends to message history (capped at 1000).

[FACT] `kosmos/agents/registry.py:338-382` -- `broadcast_message()` uses `asyncio.gather` to send to all targets concurrently. Can optionally filter by agent type.

[FACT] `kosmos/agents/registry.py:509-525` -- Singleton pattern via `get_registry()` global function.

## 3. The Direct-Call Pattern (Issue #76 -- Active Communication Pattern)

**This is the most important finding.** The message-passing system exists but is NOT used in the main research loop. Instead, agents communicate via direct method calls.

[FACT] `kosmos/agents/research_director.py:144` -- "Lazy-init agent slots for direct-call pattern (Issue #76 extension)"

[FACT] `kosmos/agents/research_director.py:167` -- "Convergence detector - direct call, not message-based (Issue #76 fix)"

[FACT] `kosmos/agents/research_director.py:1395-1456` -- `_handle_generate_hypothesis_action()` lazy-inits `HypothesisGeneratorAgent` and calls `generate_hypotheses()` directly. Log message at line 1406: "Generating hypotheses via direct call (bypassing message router)".

[FACT] `kosmos/agents/research_director.py:1462-1519` -- `_handle_design_experiment_action()` lazy-inits `ExperimentDesignerAgent` and calls `design_experiment()` directly.

[FACT] `kosmos/agents/research_director.py:1521-1577` -- `_handle_execute_experiment_action()` lazy-inits `ExperimentCodeGenerator`, `CodeExecutor`, and `DataProvider`, then calls them directly in sequence: generate code, execute code.

[FACT] `kosmos/agents/research_director.py:1670-1740` -- `_handle_analyze_result_action()` lazy-inits `DataAnalystAgent` and calls `interpret_results()` directly.

[PATTERN] All 5 agent interaction methods in the active code path use the direct-call pattern (hypothesis generation, experiment design, experiment execution, data analysis, hypothesis refinement). The `_send_to_*` async message methods (lines 1039-1219) still exist but are dead code in the Issue #76 flow.

**Why this happened**: [FACT] `kosmos/agents/research_director.py:1225` -- "Issue #76 fix: ConvergenceDetector is not an agent that can receive messages. We call it directly instead of using message passing which silently failed." The same fix was extended to all agents because agents are never registered with the `AgentRegistry` message router in the main loop.

## 4. Orchestration Layer -- DelegationManager (Second Research Loop)

There is a separate orchestration layer in `kosmos/orchestration/` that implements a DIFFERENT research loop.

[FACT] `kosmos/orchestration/__init__.py:16-21` -- Flow: "Context -> Plan Creator -> Novelty Check -> Plan Reviewer -> Delegation Manager -> State Manager -> loop"

[FACT] `kosmos/orchestration/delegation.py:72-95` -- `DelegationManager` has an `AGENT_ROUTING` dict mapping task types to agent classes: `data_analysis -> DataAnalystAgent`, `literature_review -> LiteratureAnalyzerAgent`, `hypothesis_generation -> HypothesisGeneratorAgent`, `experiment_design -> ExperimentDesignerAgent`.

[FACT] `kosmos/orchestration/delegation.py:126-194` -- `execute_plan()` creates task batches (configurable `max_parallel_tasks`, default 3), executes them via `asyncio.gather`, and handles retries (max 2 attempts with exponential backoff).

[FACT] `kosmos/orchestration/delegation.py:359-552` -- Task execution calls agents directly via their public methods (e.g., `agent.execute()`, `agent.generate_hypotheses()`, `agent.design_experiment()`). No message passing is used.

[FACT] `kosmos/workflow/research_loop.py:117-133` -- `ResearchWorkflow.__init__()` creates agent instances and passes them as a dict to `DelegationManager(agents=agents)`.

**Summary**: Both the ResearchDirector and the DelegationManager use direct method calls to agents. Neither uses the AgentRegistry message-passing system in production.

## 5. Workflow State Machine

[FACT] `kosmos/core/workflow.py:19-29` -- `WorkflowState` enum defines 9 states: INITIALIZING, GENERATING_HYPOTHESES, DESIGNING_EXPERIMENTS, EXECUTING, ANALYZING, REFINING, CONVERGED, PAUSED, ERROR.

[FACT] `kosmos/core/workflow.py:175-227` -- `ResearchWorkflow.ALLOWED_TRANSITIONS` dict defines legal state transitions as an adjacency list. Validates transitions and raises `ValueError` on illegal moves.

[FACT] `kosmos/core/workflow.py:57-164` -- `ResearchPlan` is a Pydantic model tracking hypothesis pools, experiment queues, results, and iteration counts. All state management is through list append/remove operations.

[FACT] `kosmos/agents/research_director.py:2388-2548` -- `decide_next_action()` is a deterministic decision tree that examines `workflow.current_state` and `research_plan` counts to return a `NextAction` enum. Guards include budget enforcement, runtime limit, and a loop guard (MAX_ACTIONS_PER_ITERATION = 50).

## 6. Shared State and Singletons

[PATTERN] The codebase uses singletons for all shared infrastructure (observed in 6+ modules):

| Singleton | File | Accessor |
|-----------|------|----------|
| EventBus | `core/event_bus.py:261-274` | `get_event_bus()` |
| AgentRegistry | `agents/registry.py:509-525` | `get_registry()` |
| StageTracker | `core/stage_tracker.py:248-249` | `get_stage_tracker()` |
| LLM Client | `core/llm.py:615,640` | `get_client()` |
| Config | `config.py:1142,1150` | `get_config()` |
| World Model | `world_model/factory.py:47,59` | `get_world_model()` |

## 7. Memory System (Per-Research-Run Shared State)

[FACT] `kosmos/core/memory.py:66-104` -- `MemoryStore` is NOT a singleton. It stores memories categorized as SUCCESS_PATTERNS, FAILURE_PATTERNS, DEAD_ENDS, INSIGHTS, and GENERAL. Memory entries are Pydantic models with importance scoring and access tracking.

[FACT] `kosmos/core/memory.py:388-479` -- Experiment deduplication via `is_duplicate_experiment()` uses MD5 hashing of hypothesis statements and protocol types.

[FACT] `kosmos/core/memory.py:298-348` -- `query_memory()` ranks results by `importance * (1 / days_since_creation)` -- a recency-weighted importance score.

## 8. Feedback Loop (Learning Signals)

[FACT] `kosmos/core/feedback.py:76-105` -- `FeedbackLoop` is NOT a singleton. It extracts success/failure patterns from experiment results and generates `FeedbackSignal` objects. These signals are intended to update hypothesis priorities, adapt experiment templates, and adjust strategy weights.

[FACT] `kosmos/core/feedback.py:403-465` -- `apply_feedback()` modifies hypothesis `confidence_score` directly on the hypothesis objects passed in. It does NOT use the message system or event bus.

## 9. EventBus Consumers

[FACT] Files that subscribe to the EventBus:
- `kosmos/cli/streaming.py:113-133` -- CLI streaming display subscribes to event bus for real-time output
- `kosmos/api/websocket.py` and `kosmos/api/streaming.py` -- API endpoints subscribe for WebSocket/SSE streaming
- `kosmos/core/stage_tracker.py:193-215` -- Bridges stage events to the EventBus via `publish_sync`

[FACT] `kosmos/core/providers/anthropic.py` -- The Anthropic provider publishes LLM events to the event bus.

[FACT] `kosmos/workflow/research_loop.py:149-150` -- The research loop gets the event bus and publishes workflow-level events.

## 10. Concurrency Controls

[FACT] `kosmos/agents/research_director.py:192-200` -- ResearchDirector uses BOTH async and threading locks:
- `asyncio.Lock`: `_research_plan_lock`, `_strategy_stats_lock`, `_workflow_lock`, `_agent_registry_lock`
- `threading.RLock`/`Lock`: `_research_plan_lock_sync`, `_strategy_stats_lock_sync`, `_workflow_lock_sync`

[FACT] `kosmos/core/event_bus.py:55-56` -- EventBus uses `asyncio.Lock` for async publish and `threading.Lock` for sync operations.

[FACT] `kosmos/core/llm.py:610,646` -- LLM client singleton creation uses `threading.Lock`.

## Gotchas

### Gotcha 1: Message-Passing System Is Dead Code in Main Loop
[FACT] `kosmos/agents/research_director.py:1039-1219` -- Five `_send_to_*` async methods exist (`_send_to_hypothesis_generator`, `_send_to_experiment_designer`, `_send_to_executor`, `_send_to_data_analyst`, `_send_to_hypothesis_refiner`). These build messages and call `self.send_message()`. But since agents are never registered with the AgentRegistry in the main execution flow, `self._message_router` is `None`, and messages are silently dropped (no error raised -- `send_message` at line 290 just skips the router if it's None). The Issue #76 direct-call methods completely bypass this system.

### Gotcha 2: Dual Message Queue Without Drain
[FACT] `kosmos/agents/base.py:136-137` -- `BaseAgent` maintains TWO message queues: `self.message_queue: List[AgentMessage]` (legacy sync) and `self._async_message_queue: asyncio.Queue` (async). Both are populated by `receive_message()` at lines 337-338, but nothing in the codebase drains `_async_message_queue` -- it grows unboundedly if messages are ever received.

### Gotcha 3: Duplicate Message History Storage
[FACT] `kosmos/agents/registry.py:250-253` -- `_route_message()` appends to `_message_history`. Line 307-309: `send_message()` ALSO appends to `_message_history`. Comment at line 308: "redundant with _route_message, but kept for direct sends". Every message routed through `send_message` is stored twice.

### Gotcha 4: Non-Reentrant asyncio.Lock Acknowledged But Not Fully Resolved
[FACT] `kosmos/agents/research_director.py:192` -- Comment: "asyncio.Lock is not reentrant, refactored to avoid nested acquisitions". However, the sync context managers at lines 362-379 use `threading.RLock` (reentrant), creating a mismatch: code that works with sync locks may deadlock if ported to async locks.

### Gotcha 5: EventBus Silently Drops Async Callbacks in Sync Context
[FACT] `kosmos/core/event_bus.py:177-186` -- `publish_sync()` skips async callbacks if there's no running event loop: `logger.debug(f"Skipping async callback {callback.__name__} - no event loop")`. If all subscribers are async but the publisher is sync, events are silently lost.

### Gotcha 6: Two Independent Research Loops
[FACT] `kosmos/agents/research_director.py` and `kosmos/workflow/research_loop.py` implement two separate orchestration patterns. The `ResearchDirectorAgent` uses the state machine + direct-call pattern. The `ResearchWorkflow` in `research_loop.py` uses Plan Creator -> Plan Reviewer -> Delegation Manager pattern. Both instantiate agent objects independently. It is not obvious from the code which is the canonical entry point.

## Architecture Summary

```
Active Communication Path (Issue #76 direct-call):

ResearchDirector.execute()
  -> decide_next_action()  [state machine decision tree]
  -> _execute_next_action()
     -> _handle_generate_hypothesis_action()
        -> HypothesisGeneratorAgent.generate_hypotheses()  [direct call]
     -> _handle_design_experiment_action()
        -> ExperimentDesignerAgent.design_experiment()  [direct call]
     -> _handle_execute_experiment_action()
        -> ExperimentCodeGenerator.generate() + CodeExecutor.execute()  [direct call]
     -> _handle_analyze_result_action()
        -> DataAnalystAgent.interpret_results()  [direct call]
     -> _handle_refine_hypothesis_action()
        -> HypothesisRefiner (utility class, not BaseAgent)

Observability Path (EventBus pub/sub):

StageTracker / LLM Provider / ResearchWorkflow
  -> EventBus.publish_sync() / publish()
     -> CLI StreamingDisplay [subscriber]
     -> API WebSocket/SSE endpoints [subscriber]

Dormant Path (AgentMessage system):
AgentRegistry.register() -> agent.set_message_router()
  -> agent.send_message() -> _route_message() -> target.receive_message()
  [Not used in active code -- agents never registered in main loop]
```
# Configuration Surface: Env Vars, Config Files, Provider Selection, Feature Flags

## 1. Configuration Architecture

### Central Config Module
[FACT] `kosmos/config.py` (lines 1-1157) is the single source of truth for validated configuration. It uses **Pydantic v2 `BaseSettings`** with `pydantic-settings`, which auto-loads from both environment variables and `.env` files.

[FACT] The master class `KosmosConfig` (config.py:922) composes 16 sub-config dataclasses:
- `ClaudeConfig` / `AnthropicConfig` (LLM - Anthropic)
- `OpenAIConfig` (LLM - OpenAI)
- `LiteLLMConfig` (LLM - multi-provider)
- `LocalModelConfig` (local model tuning)
- `ResearchConfig`
- `DatabaseConfig`
- `RedisConfig`
- `LoggingConfig`
- `LiteratureConfig`
- `VectorDBConfig`
- `Neo4jConfig`
- `SafetyConfig`
- `PerformanceConfig`
- `MonitoringConfig`
- `DevelopmentConfig`
- `WorldModelConfig`

### Singleton Access
[FACT] `get_config()` (config.py:1140) returns a singleton `KosmosConfig`. Pass `reload=True` to force re-read from environment. `reset_config()` exists to clear the singleton (used in tests).

### .env File Loading
[FACT] `KosmosConfig.model_config` (config.py:978-983) declares:
```python
env_file=str(Path(__file__).parent.parent / ".env")
```
This resolves to the repo root `.env`. Pydantic-settings reads this file automatically. The setting `case_sensitive=False` and `extra="ignore"` mean unrecognized env vars are silently dropped.

---

## 2. Config Files

| File | Purpose | Notes |
|------|---------|-------|
| `.env` | Primary configuration | Loaded by pydantic-settings automatically |
| `.env.example` | Template with all vars documented (458 lines) | Comprehensive; copy to `.env` to start |
| `.env.backup` | User backup of `.env` | Not gitignored; exists in repo |
| `alembic.ini` | DB migration config | `sqlalchemy.url` is overridden at runtime by Kosmos config |
| `docker-compose.yml` | Container orchestration | Injects env vars from `.env` via `${VAR}` syntax |
| `pyproject.toml` | Python project metadata | Build config, not runtime config |
| `pytest.ini` | Test runner config | Not runtime |

[ABSENCE] No `config.yaml`, `config.json`, or `settings.py` files exist. Configuration is purely env-var-driven.

---

## 3. Required Environment Variables

### Minimum to Run (Anthropic mode, the default)

| Variable | Required | Default | Source |
|----------|----------|---------|--------|
| `ANTHROPIC_API_KEY` | **Yes** (when `LLM_PROVIDER=anthropic`) | None | config.py:37-39 |
| `LLM_PROVIDER` | No | `"anthropic"` | config.py:953-957 |

[FACT] If `LLM_PROVIDER=anthropic` and `ANTHROPIC_API_KEY` is absent, `KosmosConfig` raises `ValueError` at validation time (config.py:1033-1038).

### Minimum to Run (OpenAI mode)

| Variable | Required | Default | Source |
|----------|----------|---------|--------|
| `OPENAI_API_KEY` | **Yes** (when `LLM_PROVIDER=openai`) | None | config.py:99-101 |
| `LLM_PROVIDER` | Must be `"openai"` | `"anthropic"` | config.py:953 |

### Minimum to Run (LiteLLM mode)

| Variable | Required | Default | Source |
|----------|----------|---------|--------|
| `LLM_PROVIDER` | Must be `"litellm"` | `"anthropic"` | config.py:953 |
| `LITELLM_MODEL` | No | `"gpt-3.5-turbo"` | config.py:155-158 |
| `LITELLM_API_KEY` | Only for cloud providers | None | config.py:160-163 |

[FACT] LiteLLM validation is intentionally lenient: local models (Ollama) don't need API keys. Validation only happens at runtime, not at config init (config.py:1039-1042).

---

## 4. Complete Environment Variable Catalog

### LLM Provider Selection
| Variable | Type | Default | Pydantic Alias | File:Line |
|----------|------|---------|----------------|-----------|
| `LLM_PROVIDER` | `Literal["anthropic","openai","litellm"]` | `"anthropic"` | `LLM_PROVIDER` | config.py:953 |

### Anthropic/Claude
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `ANTHROPIC_API_KEY` | `str` | None (required) | config.py:37 |
| `CLAUDE_MODEL` | `str` | `"claude-sonnet-4-5"` | config.py:41-44 |
| `CLAUDE_MAX_TOKENS` | `int` [1-200000] | `4096` | config.py:46-50 |
| `CLAUDE_TEMPERATURE` | `float` [0.0-1.0] | `0.7` | config.py:52-58 |
| `CLAUDE_ENABLE_CACHE` | `bool` | `True` | config.py:60-63 |
| `CLAUDE_BASE_URL` | `str?` | `None` | config.py:66-70 |
| `CLAUDE_TIMEOUT` | `int` [1-600] | `120` | config.py:71-77 |

### OpenAI
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `OPENAI_API_KEY` | `str` | None (required when selected) | config.py:99 |
| `OPENAI_MODEL` | `str` | `"gpt-4-turbo"` | config.py:103-106 |
| `OPENAI_MAX_TOKENS` | `int` [1-128000] | `4096` | config.py:108-113 |
| `OPENAI_TEMPERATURE` | `float` [0.0-2.0] | `0.7` | config.py:115-120 |
| `OPENAI_BASE_URL` | `str?` | `None` | config.py:122-125 |
| `OPENAI_ORGANIZATION` | `str?` | `None` | config.py:127-130 |
| `OPENAI_TIMEOUT` | `int` [1-600] | `120` | config.py:132-138 |

### LiteLLM
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `LITELLM_MODEL` | `str` | `"gpt-3.5-turbo"` | config.py:155 |
| `LITELLM_API_KEY` | `str?` | `None` | config.py:160 |
| `LITELLM_API_BASE` | `str?` | `None` | config.py:165 |
| `LITELLM_MAX_TOKENS` | `int` [1-128000] | `4096` | config.py:170 |
| `LITELLM_TEMPERATURE` | `float` [0.0-2.0] | `0.7` | config.py:177 |
| `LITELLM_TIMEOUT` | `int` [1-600] | `120` | config.py:184 |

### Local Model Tuning
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `LOCAL_MODEL_MAX_RETRIES` | `int` [0-5] | `1` | config.py:760-765 |
| `LOCAL_MODEL_STRICT_JSON` | `bool` | `False` | config.py:769-772 |
| `LOCAL_MODEL_JSON_RETRY_HINT` | `bool` | `True` | config.py:775-778 |
| `LOCAL_MODEL_REQUEST_TIMEOUT` | `int` [30-600] | `120` | config.py:782-787 |
| `LOCAL_MODEL_CONCURRENT_REQUESTS` | `int` [1-4] | `1` | config.py:790-794 |
| `LOCAL_MODEL_FALLBACK_UNSTRUCTURED` | `bool` | `True` | config.py:799-802 |
| `LOCAL_MODEL_CB_THRESHOLD` | `int` [1-10] | `3` | config.py:806-811 |
| `LOCAL_MODEL_CB_RESET_TIMEOUT` | `int` [10-300] | `60` | config.py:814-819 |

### Research
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `MAX_RESEARCH_ITERATIONS` | `int` [1-100] | `10` | config.py:203 |
| `ENABLED_DOMAINS` | comma-separated list | `biology,physics,chemistry,neuroscience` | config.py:210 |
| `ENABLED_EXPERIMENT_TYPES` | comma-separated list | `computational,data_analysis,literature_synthesis` | config.py:215 |
| `MIN_NOVELTY_SCORE` | `float` [0.0-1.0] | `0.6` | config.py:220 |
| `ENABLE_AUTONOMOUS_ITERATION` | `bool` | `True` | config.py:227 |
| `RESEARCH_BUDGET_USD` | `float` [>=0] | `10.0` | config.py:232 |
| `MAX_RUNTIME_HOURS` | `float` [0.1-24.0] | `12.0` | config.py:238 |

### Database
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `DATABASE_URL` | `str` | `"sqlite:///kosmos.db"` | config.py:253 |
| `DATABASE_ECHO` | `bool` | `False` | config.py:258 |

### Redis
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `REDIS_ENABLED` | `bool` | `False` | config.py:313 |
| `REDIS_URL` | `str` | `"redis://localhost:6379/0"` | config.py:308 |
| `REDIS_MAX_CONNECTIONS` | `int` [1-1000] | `50` | config.py:318 |
| `REDIS_SOCKET_TIMEOUT` | `int` [1-60] | `5` | config.py:325 |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `int` [1-60] | `5` | config.py:332 |
| `REDIS_RETRY_ON_TIMEOUT` | `bool` | `True` | config.py:339 |
| `REDIS_DECODE_RESPONSES` | `bool` | `True` | config.py:344 |
| `REDIS_DEFAULT_TTL_SECONDS` | `int` [60-86400] | `3600` | config.py:349 |

### Logging
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `LOG_LEVEL` | `Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]` | `"INFO"` | config.py:368 |
| `LOG_FORMAT` | `Literal["json","text"]` | `"json"` | config.py:373 |
| `LOG_FILE` | `str?` | `"logs/kosmos.log"` | config.py:378 |
| `DEBUG_MODE` | `bool` | `False` | config.py:383 |
| `DEBUG_LEVEL` | `Literal[0,1,2,3]` | `0` | config.py:390 |
| `DEBUG_MODULES` | comma-separated list? | `None` | config.py:396 |
| `LOG_LLM_CALLS` | `bool` | `False` | config.py:402 |
| `LOG_AGENT_MESSAGES` | `bool` | `False` | config.py:408 |
| `LOG_WORKFLOW_TRANSITIONS` | `bool` | `False` | config.py:414 |
| `STAGE_TRACKING_ENABLED` | `bool` | `False` | config.py:420 |
| `STAGE_TRACKING_FILE` | `str` | `"logs/stages.jsonl"` | config.py:426 |

### Literature APIs
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `SEMANTIC_SCHOLAR_API_KEY` | `str?` | `None` | config.py:438 |
| `PUBMED_API_KEY` | `str?` | `None` | config.py:443 |
| `PUBMED_EMAIL` | `str?` | `None` | config.py:448 |
| `LITERATURE_CACHE_TTL_HOURS` | `int` [1-168] | `48` | config.py:453 |
| `MAX_RESULTS_PER_QUERY` | `int` [1-1000] | `100` | config.py:460 |
| `PDF_DOWNLOAD_TIMEOUT` | `int` [5-120] | `30` | config.py:466 |
| `LITERATURE_SEARCH_TIMEOUT` | `int` [10-300] | `90` | config.py:474 |
| `LITERATURE_API_TIMEOUT` | `int` [5-120] | `30` | config.py:481 |

### Vector DB
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `VECTOR_DB_TYPE` | `Literal["chromadb","pinecone","weaviate"]` | `"chromadb"` | config.py:495 |
| `CHROMA_PERSIST_DIRECTORY` | `str` | `".chroma_db"` | config.py:500 |
| `PINECONE_API_KEY` | `str?` | `None` | config.py:505 |
| `PINECONE_ENVIRONMENT` | `str?` | `None` | config.py:510 |
| `PINECONE_INDEX_NAME` | `str?` | `"kosmos"` | config.py:515 |

### Neo4j
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `NEO4J_URI` | `str` | `"bolt://localhost:7687"` | config.py:537 |
| `NEO4J_USER` | `str` | `"neo4j"` | config.py:542 |
| `NEO4J_PASSWORD` | `str` | `"kosmos-password"` | config.py:547 |
| `NEO4J_DATABASE` | `str` | `"neo4j"` | config.py:552 |
| `NEO4J_MAX_CONNECTION_LIFETIME` | `int` [>=60] | `3600` | config.py:557 |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | `int` [>=1] | `50` | config.py:563 |

### Safety
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `ENABLE_SAFETY_CHECKS` | `bool` | `True` | config.py:576 |
| `MAX_EXPERIMENT_EXECUTION_TIME` | `int` [>=1] | `300` | config.py:581 |
| `MAX_MEMORY_MB` | `int` [>=128] | `2048` | config.py:587 |
| `MAX_CPU_CORES` | `float?` [>=0.1] | `None` | config.py:593 |
| `ENABLE_SANDBOXING` | `bool` | `True` | config.py:599 |
| `REQUIRE_HUMAN_APPROVAL` | `bool` | `False` | config.py:604 |
| `ETHICAL_GUIDELINES_PATH` | `str?` | `None` | config.py:611 |
| `ENABLE_RESULT_VERIFICATION` | `bool` | `True` | config.py:618 |
| `OUTLIER_THRESHOLD` | `float` [>=1.0] | `3.0` | config.py:623 |
| `DEFAULT_RANDOM_SEED` | `int` | `42` | config.py:631 |
| `CAPTURE_ENVIRONMENT` | `bool` | `True` | config.py:636 |
| `APPROVAL_MODE` | `Literal["blocking","queue","automatic","disabled"]` | `"blocking"` | config.py:643 |
| `AUTO_APPROVE_LOW_RISK` | `bool` | `True` | config.py:648 |
| `NOTIFICATION_CHANNEL` | `Literal["console","log","both"]` | `"both"` | config.py:655 |
| `NOTIFICATION_MIN_LEVEL` | `Literal["debug","info","warning","error","critical"]` | `"info"` | config.py:660 |
| `USE_RICH_FORMATTING` | `bool` | `True` | config.py:665 |
| `INCIDENT_LOG_PATH` | `str` | `"safety_incidents.jsonl"` | config.py:672 |
| `AUDIT_LOG_PATH` | `str` | `"human_review_audit.jsonl"` | config.py:677 |

### Performance / Concurrency
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `ENABLE_RESULT_CACHING` | `bool` | `True` | config.py:689 |
| `CACHE_TTL` | `int` [>=0] | `3600` | config.py:694 |
| `PARALLEL_EXPERIMENTS` | `int` [>=0] | `0` | config.py:700 |
| `ENABLE_CONCURRENT_OPERATIONS` | `bool` | `False` | config.py:708 |
| `MAX_PARALLEL_HYPOTHESES` | `int` [1-10] | `3` | config.py:713 |
| `MAX_CONCURRENT_EXPERIMENTS` | `int` [1-16] | `10` | config.py:720 |
| `MAX_CONCURRENT_LLM_CALLS` | `int` [1-20] | `5` | config.py:727 |
| `LLM_RATE_LIMIT_PER_MINUTE` | `int` [1-200] | `50` | config.py:734 |
| `ASYNC_BATCH_TIMEOUT` | `int` [10-3600] | `300` | config.py:741 |

### World Model
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `WORLD_MODEL_ENABLED` | `bool` | `True` | config.py:868 |
| `WORLD_MODEL_MODE` | `Literal["simple","production"]` | `"simple"` | config.py:874 |
| `WORLD_MODEL_PROJECT` | `str?` | `None` | config.py:880 |
| `WORLD_MODEL_AUTO_SAVE_INTERVAL` | `int` [>=0] | `300` | config.py:886 |

### Monitoring / Development
| Variable | Type | Default | File:Line |
|----------|------|---------|-----------|
| `ENABLE_USAGE_STATS` | `bool` | `True` | config.py:828 |
| `METRICS_EXPORT_INTERVAL` | `int` [>=0] | `60` | config.py:833 |
| `HOT_RELOAD` | `bool` | `False` | config.py:846 |
| `LOG_API_REQUESTS` | `bool` | `False` | config.py:851 |
| `TEST_MODE` | `bool` | `False` | config.py:856 |

### NOT in Pydantic Config (read directly from os.getenv)
| Variable | Used By | File:Line |
|----------|---------|-----------|
| `ALERT_EMAIL_ENABLED` | monitoring/alerts.py | alerts.py:362 |
| `ALERT_EMAIL_FROM` | monitoring/alerts.py | alerts.py:371 |
| `ALERT_EMAIL_TO` | monitoring/alerts.py | alerts.py:372 |
| `SMTP_HOST` | monitoring/alerts.py | alerts.py:390 |
| `SMTP_PORT` | monitoring/alerts.py | alerts.py:391 |
| `SMTP_USER` | monitoring/alerts.py | alerts.py:392 |
| `SMTP_PASSWORD` | monitoring/alerts.py | alerts.py:393 |
| `ALERT_SLACK_ENABLED` | monitoring/alerts.py | alerts.py:415 |
| `SLACK_WEBHOOK_URL` | monitoring/alerts.py | alerts.py:421 |
| `ALERT_PAGERDUTY_ENABLED` | monitoring/alerts.py | alerts.py:483 |
| `PAGERDUTY_INTEGRATION_KEY` | monitoring/alerts.py | alerts.py:493 |
| `KOSMOS_SKILLS_DIR` | agents/skill_loader.py | skill_loader.py:148 |
| `EDITOR` | cli/commands/config.py | config.py:313 |

---

## 5. Provider Selection Logic

### The Three-Provider Architecture
[FACT] The `LLM_PROVIDER` env var (config.py:953) is the top-level switch. Legal values: `"anthropic"`, `"openai"`, `"litellm"`. Default is `"anthropic"`.

### Selection Flow
1. `KosmosConfig` reads `LLM_PROVIDER` from env/.env
2. Conditional sub-configs are instantiated:
   - `ClaudeConfig` / `OpenAIConfig` are only created if their respective API keys are present (config.py:896-919, `_optional_*_config()` factories)
   - `LiteLLMConfig` is always created (config.py:963)
3. `validate_provider_config` (config.py:1024-1043) enforces: the selected provider must have its API key set (except LiteLLM, which is lenient for local models)
4. At runtime, `get_provider_from_config()` in `core/providers/factory.py:83` reads `llm_provider` from config and instantiates the corresponding provider class

### Provider Registry
[FACT] `factory.py:189-217` auto-registers providers at import time:
- `"anthropic"` and `"claude"` (alias) -> `AnthropicProvider`
- `"openai"` -> `OpenAIProvider`
- `"litellm"`, `"ollama"`, `"deepseek"`, `"lmstudio"` (aliases) -> `LiteLLMProvider`

Registration uses try/except to gracefully degrade if a provider's SDK package is not installed.

### CLI Mode (Special Case)
[FACT] When `ANTHROPIC_API_KEY` is set to all 9s (`999...`), the system enters "CLI mode" which routes API calls through a local Claude Code CLI proxy instead of the Anthropic API directly. Detected by `ClaudeConfig.is_cli_mode` (config.py:80-82): `self.api_key.replace('9', '') == ''`.

---

## 6. Feature Flags

[PATTERN] The system uses boolean env vars as feature flags. Observed in 11+ instances across config.py. Pattern is consistent: `ENABLE_X` or `X_ENABLED` booleans with `False` defaults for opt-in features.

### Key Feature Flags (all default OFF unless noted)
| Flag | Default | Controls |
|------|---------|----------|
| `ENABLE_CONCURRENT_OPERATIONS` | `False` | Parallel hypothesis eval + experiment execution |
| `REDIS_ENABLED` | `False` | Redis caching layer |
| `STAGE_TRACKING_ENABLED` | `False` | Real-time JSONL stage output |
| `ENABLE_PROFILING` (in .env.example, not in Pydantic) | `False` | Performance profiling |
| `ENABLE_SAFETY_CHECKS` | **`True`** | Code safety validation |
| `ENABLE_SANDBOXING` | **`True`** | Sandboxed code execution |
| `ENABLE_RESULT_VERIFICATION` | **`True`** | Result outlier checking |
| `ENABLE_RESULT_CACHING` | **`True`** | In-memory result caching |
| `ENABLE_AUTONOMOUS_ITERATION` | **`True`** | Auto-iterate research |
| `ENABLE_USAGE_STATS` | **`True`** | Usage statistics collection |
| `WORLD_MODEL_ENABLED` | **`True`** | Knowledge graph persistence |
| `DEBUG_MODE` | `False` | Verbose debug logging |
| `TEST_MODE` | `False` | Mock APIs instead of real ones |
| `HOT_RELOAD` | `False` | Dev-only hot reload |

---

## 7. Gotchas and Deviations

### Gotcha 1: Monitoring/Alerts Bypass the Config System Entirely
[FACT] `kosmos/monitoring/alerts.py` reads 11 env vars directly via `os.getenv()` (lines 362-549) without any corresponding Pydantic model. These variables (`ALERT_EMAIL_ENABLED`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_SLACK_ENABLED`, `SLACK_WEBHOOK_URL`, `ALERT_PAGERDUTY_ENABLED`, `PAGERDUTY_INTEGRATION_KEY`, `ALERT_EMAIL_FROM`, `ALERT_EMAIL_TO`) are invisible to `kosmos config --validate` and do not appear in `KosmosConfig.to_dict()`.

### Gotcha 2: Health Endpoint Bypasses Config
[FACT] `kosmos/api/health.py` (lines 226-338) reads `REDIS_ENABLED`, `REDIS_URL`, `ANTHROPIC_API_KEY`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` directly from `os.getenv()` instead of using `get_config()`. This means the health endpoint can report different values than the config singleton if env vars and `.env` file diverge.

### Gotcha 3: research_director Reads API Key Directly
[FACT] `kosmos/agents/research_director.py:228` reads `ANTHROPIC_API_KEY` directly from `os.getenv()` rather than from the config singleton when initializing `AsyncClaudeClient`. This bypasses the provider selection system and is hardcoded to Anthropic even when `LLM_PROVIDER=openai` or `LLM_PROVIDER=litellm`.

### Gotcha 4: Legacy ClaudeClient in core/llm.py
[FACT] `kosmos/core/llm.py:160` contains a legacy `ClaudeClient` class that reads `ANTHROPIC_API_KEY` directly from `os.environ.get()`, not via config. This class exists alongside the newer provider-based system and is maintained for backward compatibility. Code that uses `ClaudeClient` directly will not respect `LLM_PROVIDER` selection.

### Gotcha 5: LiteLLM Nested Config Requires Manual Sync
[FACT] config.py:986-1022 contains `sync_litellm_env_vars`, a model validator that manually copies `LITELLM_*` env vars into the nested `LiteLLMConfig` object. The comment explains: "Pydantic's nested BaseSettings submodels don't automatically pick up env vars from the parent's .env file." This means if a new `LITELLM_*` env var is added to `LiteLLMConfig`, it must also be added to the `env_map` dict in the sync validator, or it will silently use defaults.

### Gotcha 6: ENABLE_PROFILING Not in Pydantic
[FACT] `.env.example` documents `ENABLE_PROFILING` and `PROFILING_MODE` (lines 413-421), but neither appears in `config.py` as Pydantic fields. These are consumed directly by `kosmos/execution/executor.py:181-182` as constructor parameters, not via the config system.

### Gotcha 7: Default Model Mismatch Between .env.example and Config
[FACT] `.env.example:17` shows `CLAUDE_MODEL=claude-sonnet-4-5`. Meanwhile, `docker-compose.yml:17` uses `CLAUDE_MODEL=${CLAUDE_MODEL:-claude-3-5-sonnet-20241022}` as its default. These are different model identifiers. The Pydantic default in config.py:42 is `"claude-sonnet-4-5"` (the newer naming), matching `.env.example`.

### Gotcha 8: KOSMOS_SKILLS_DIR Not in Config
[FACT] `KOSMOS_SKILLS_DIR` (agents/skill_loader.py:148) is read directly from `os.environ` and not modeled in `KosmosConfig`. It controls where the skill loader finds scientific skill definitions.

---

## 8. Configuration Precedence

[FACT] Pydantic-settings precedence (highest wins):
1. **Environment variables** (actual `os.environ`)
2. **`.env` file** (loaded via `env_file` setting in `model_config`)
3. **Field defaults** (defined in each `Field()`)

[FACT] Within provider code, there is an additional fallback layer: providers read `config.get('key') or os.environ.get('KEY')` (e.g., anthropic.py:88, openai.py:106). This means a provider can pick up an env var even if the config dict passed to it has `None` for that key.

---

## 9. CLI Config Management

[FACT] `kosmos config --show` displays the current config via `get_config()` (cli/commands/config.py:117-196).
[FACT] `kosmos config --validate` checks API key presence, model validity, domain validity, and database existence (cli/commands/config.py:199-291).
[FACT] `kosmos config --edit` opens `.env` in `$EDITOR` (default: `nano`). If no `.env` exists, copies from `.env.example` (cli/commands/config.py:294-319).
[FACT] `kosmos config --reset` copies `.env.example` over `.env` (cli/commands/config.py:322-341).

[FACT] `get_config_value()` in `kosmos/cli/utils.py:277-299` provides dot-notation access to config fields (e.g., `get_config_value("claude.model")`), wrapping the `get_config()` singleton.
# Cross-Cutting Concern: Database and Storage Patterns

## Summary

Kosmos uses a **polyglot persistence architecture** with five distinct storage technologies, each serving a specialized role. The primary relational store is **SQLAlchemy/Alembic** over SQLite (dev) or PostgreSQL (prod). **Neo4j** powers the knowledge graph for scientific literature. **ChromaDB** provides vector storage for semantic search. **Redis** acts as an optional cache layer. A fifth, less obvious storage layer is **raw SQLite** used by the experiment cache independently of SQLAlchemy.

---

## 1. SQLAlchemy + PostgreSQL/SQLite (Primary Relational Store)

### Connection Management

[FACT] The database engine is a module-level singleton managed through global variables `_engine` and `_SessionLocal` in `kosmos/db/__init__.py:22-23`. The `init_database()` function (line 26) creates the engine and session factory.

[FACT] For SQLite, connection pooling is skipped and `check_same_thread=False` is passed (`kosmos/db/__init__.py:74-78`). For PostgreSQL, a `QueuePool` is used with `pool_pre_ping=True` for stale connection detection (line 81-89). Defaults: `pool_size=5`, `max_overflow=10`, `pool_timeout=30`.

[FACT] Sessions use a context manager pattern (`kosmos/db/__init__.py:108-137`). The `get_session()` function yields a session, commits on success, rolls back on exception, and always closes. This prevents session leaks.

### ORM Models

[FACT] Six SQLAlchemy models are defined in `kosmos/db/models.py`: `Experiment` (line 40), `Hypothesis` (line 75), `Result` (line 110), `Paper` (line 148), `AgentRecord` (line 189), `ResearchSession` (line 222). All use String primary keys (application-generated IDs, not auto-increment).

[FACT] Relationships: `Experiment.hypothesis` (many-to-one), `Hypothesis.experiments` (one-to-many), `Experiment.results` (one-to-many with cascade delete-orphan). `Result.experiment` (many-to-one). See `kosmos/db/models.py:68-69`.

[FACT] JSON columns are used extensively: `protocol`, `related_papers`, `data`, `statistical_tests`, `key_findings`, `figures`, `config`, `state_data`, `discoveries_made` across multiple models.

### CRUD Operations

[FACT] `kosmos/db/operations.py` provides full CRUD for all models. It uses `joinedload()` for eager loading to prevent N+1 queries (e.g., lines 135, 169-170). Input validation for JSON fields is done via `_validate_json_dict()` and `_validate_json_list()` helpers (lines 27-44).

[PATTERN] Every CRUD create function follows the same pattern: validate inputs, create ORM object, `session.add()`, `session.commit()`, `session.refresh()`, return object. Observed in `create_hypothesis` (line 87), `create_experiment` (line 198), `create_result` (line 339), `create_paper` (line 424), `create_agent_record` (line 486).

### Slow Query Logging

[FACT] Slow query detection is implemented via SQLAlchemy events in `kosmos/db/operations.py:51-80`. Uses `before_cursor_execute` to record start time and `after_cursor_execute` to measure duration. Default threshold: 100ms. Enabled by `init_database()` at `kosmos/db/__init__.py:94-97`.

### Configuration

[FACT] `DatabaseConfig` in `kosmos/config.py:250-302` defaults to `sqlite:///kosmos.db`. The `normalized_url` property (line 270) converts relative SQLite paths to absolute paths for consistent database location.

[FACT] In Docker production mode, the URL is `postgresql://kosmos:kosmos-dev-password@postgres:5432/kosmos` (`docker-compose.yml:18`).

### Database Consumers

[PATTERN] The `get_session()` context manager is used throughout the codebase in at least 10+ files. Major consumers include `kosmos/agents/research_director.py` (most heavy user with 15+ session blocks), `kosmos/agents/experiment_designer.py`, `kosmos/hypothesis/novelty_checker.py`, `kosmos/execution/result_collector.py`, `kosmos/cli/utils.py`.

---

## 2. Alembic Migrations

### Migration Chain

[FACT] Three migrations exist in `alembic/versions/`:
1. `2ec489a3eb6b_initial_schema.py` -- Creates 6 core tables (agents, hypotheses, papers, research_sessions, experiments, results). Created 2025-11-12.
2. `fb9e61f33cbf_add_performance_indexes.py` -- Adds 29 indexes across all 6 tables (single-column + composite). Created 2025-11-12.
3. `dc24ead48293_add_profiling_tables.py` -- Adds `execution_profiles` and `profiling_bottlenecks` tables with 11 indexes. Created 2025-11-12.

### Migration Infrastructure

[FACT] `alembic/env.py` reads the database URL from `kosmos.config.get_config()` (line 34), falling back to `alembic.ini` (line 37). Online migrations use `NullPool` (line 75) to avoid connection pool interference.

[FACT] `alembic.ini:19` has a fallback URL of `sqlite:///kosmos.db`.

### Automatic Migrations

[FACT] `kosmos/utils/setup.py:53-112` implements `run_database_migrations()` which automatically runs `alembic upgrade head` on startup. This is called by `init_from_config()` in `kosmos/db/__init__.py:168-170` via `first_time_setup()`.

[FACT] `kosmos/utils/setup.py:115-216` implements `validate_database_schema()` which checks for expected tables (8 total including `alembic_version`) and key indexes after migration.

### PostgreSQL Init Script

[FACT] `scripts/init_db.sql` configures PostgreSQL extensions (`uuid-ossp`, `pg_trgm`, `btree_gin`, `pg_stat_statements`) and tunes 20+ PostgreSQL settings for performance. This runs only on first container creation via Docker entrypoint.

---

## 3. Neo4j Knowledge Graph

### Connection Architecture

[FACT] `KnowledgeGraph` in `kosmos/knowledge/graph.py:24` connects via `py2neo` library. Connection parameters come from `config.neo4j` (line 69-72): default `bolt://localhost:7687`, user `neo4j`, password `kosmos-password`.

[FACT] Singleton access via `get_knowledge_graph()` at line 1003. The singleton is stored in module-level `_knowledge_graph` variable.

[FACT] Connection test: `self.graph.run("RETURN 1").data()` at line 88. On failure, `self.graph` is set to `None` and `self._connected = False` (line 98-99). Callers check `self.connected` property.

### Auto-Start Docker Container

[FACT] `_ensure_container_running()` at `kosmos/knowledge/graph.py:118-171` runs `docker ps --filter "name=kosmos-neo4j"` to check container status, then `docker-compose up -d neo4j` if needed. Waits up to 60 seconds (30 retries x 2s) for the container to become ready.

**Gotcha**: [FACT] The auto-start uses `subprocess.run()` with `timeout=60` for docker-compose (line 143) and `timeout=5` for health checks (line 153). If Docker is not installed, it catches `FileNotFoundError` at line 171 and proceeds silently.

### Schema and Indexes

[FACT] Node types: Paper, Concept, Method, Author (line 29). Relationship types: CITES, USES_METHOD, DISCUSSES, AUTHORED, RELATED_TO (line 30).

[FACT] Eight indexes created in `_create_indexes()` at line 173: on Paper.id, Paper.doi, Paper.arxiv_id, Paper.pubmed_id, Author.name, Concept.name, Concept.domain, Method.name, Method.category.

### Graph Operations

[FACT] Full CRUD for Paper (lines 204-329), Author (lines 333-401), Concept (lines 404-469), Method (lines 472-530). All support merge semantics (upsert pattern).

[FACT] Complex graph queries include: citation depth traversal (`get_citations`, line 749), reverse citation lookup (`get_citing_papers`, line 769), concept co-occurrence (`get_concept_cooccurrence`, line 936), and multi-hop related paper discovery (`find_related_papers`, line 898). Uses parameterized Cypher queries throughout.

### Configuration

[FACT] `Neo4jConfig` at `kosmos/config.py:534-570` includes `max_connection_lifetime=3600` and `max_connection_pool_size=50`. However, the `KnowledgeGraph` class does not pass these to `py2neo.Graph()` constructor -- only `uri`, `auth`, and `name` are passed (line 81-85).

**Gotcha**: [FACT] The Neo4j config defines `max_connection_pool_size` and `max_connection_lifetime` (config.py:557-568) but these are never used by `KnowledgeGraph.__init__()` (graph.py:81-85). The py2neo `Graph()` constructor does not receive pool settings.

### Optional Component

[FACT] In the health check (`kosmos/api/health.py:93-96`), Neo4j is explicitly marked optional -- its status does not affect the overall readiness check: "Don't mark as not ready if Neo4j is down (it's optional)".

[FACT] In the world model factory (`kosmos/world_model/factory.py:124-133`), if Neo4j is unavailable, the system falls back to `InMemoryWorldModel` with a warning that data will not persist.

---

## 4. ChromaDB Vector Database

### Architecture

[FACT] `PaperVectorDB` in `kosmos/knowledge/vector_db.py:30` uses `chromadb.PersistentClient` (line 79) with cosine similarity (`hnsw:space: cosine`, line 99).

[FACT] ChromaDB is an optional dependency -- import is wrapped in try/except with `HAS_CHROMADB` flag (lines 19-27). If not installed, the class gracefully degrades with `self.client = None`.

### Singleton Pattern

[FACT] `get_vector_db()` at line 447 provides singleton access via module-level `_vector_db`. Same pattern as Neo4j and other knowledge components.

### Embedding Pipeline

[FACT] On `add_papers()` (line 129), if embeddings are not pre-computed, the system calls `self.embedder.embed_papers()` (line 159). The embedder is initialized via `get_embedder()` from `kosmos.knowledge.embeddings`.

[FACT] Documents stored in ChromaDB consist of title + abstract joined by `[SEP]` token (line 440). Metadata includes source, title (truncated to 500 chars), year, citation_count, and domain (lines 401-417).

### Configuration

[FACT] `VectorDBConfig` at `kosmos/config.py:492-531` supports three backends: `chromadb` (default), `pinecone`, and `weaviate`. Only ChromaDB is implemented -- Pinecone config is validated but no implementation exists for it or Weaviate in the codebase.

[FACT] ChromaDB persist directory defaults to `.chroma_db` (config.py:501). In Docker, it's volume-mounted as `.chroma_db:/app/.chroma_db` (docker-compose.yml:30).

---

## 5. Redis Cache

### Role and Configuration

[FACT] Redis is disabled by default: `RedisConfig.enabled` defaults to `False` in `kosmos/config.py:316`. When enabled, it uses `redis://localhost:6379/0` (line 309).

[FACT] `RedisConfig` includes pool settings: `max_connections=50`, `socket_timeout=5`, `socket_connect_timeout=5`, `retry_on_timeout=True`, `default_ttl_seconds=3600` (lines 319-355).

### Actual Usage

[FACT] Redis is only checked in the health endpoint (`kosmos/api/health.py:226-272`). The health check creates an ad-hoc `redis.from_url()` connection with hardcoded timeouts (line 234-238), calls `client.ping()`, and reads `client.info()`.

[ABSENCE] The `CacheManager` (`kosmos/core/cache_manager.py`) does NOT use Redis. It uses in-memory (`InMemoryCache`), disk (`DiskCache`), and hybrid (`HybridCache`) caching -- all file/memory-based. Redis is not imported or referenced in this file.

**Gotcha**: [FACT] Despite Redis being configured with comprehensive settings in `RedisConfig` and deployed as a Docker service with health checks, it is only actually used in the health check endpoint. The application's caching layer (`CacheManager`, `ExperimentCache`) uses file-based and in-memory caches instead.

### Docker Deployment

[FACT] Redis container (`docker-compose.yml:98-133`) runs `redis:7-alpine` with `maxmemory 256mb`, `allkeys-lru` eviction, and AOF persistence enabled. Data persists in `./redis_data` volume.

---

## 6. Experiment Cache (Standalone SQLite)

### Independent Storage Layer

[FACT] `ExperimentCache` in `kosmos/core/experiment_cache.py:178` maintains its own SQLite database at `.kosmos_cache/experiments/experiments.db` (line 217), separate from the main SQLAlchemy database. Uses raw `sqlite3` module directly (no ORM).

[FACT] Thread safety via `threading.RLock()` (line 220). Every public method acquires the lock.

[FACT] Schema has two tables: `experiments` (with fingerprint-based dedup, embedding storage, and searchable text) and `cache_stats` (hit/miss tracking). Three indexes: `idx_fingerprint`, `idx_timestamp`, `idx_hypothesis` (lines 264-277).

[FACT] Similarity matching loads ALL experiments with embeddings into memory (`SELECT ... WHERE embedding IS NOT NULL`, line 474) and computes cosine similarity in Python (line 495-500). This is O(n) per search.

---

## 7. Docker Infrastructure

[FACT] `docker-compose.yml` defines four database services:
- **postgres** (lines 60-95): `postgres:15-alpine`, port 5432, `POSTGRES_DB=kosmos`, with health check via `pg_isready`
- **redis** (lines 98-133): `redis:7-alpine`, port 6379, 256MB max memory, LRU eviction
- **neo4j** (lines 136-180): `neo4j:5.14-community`, ports 7474 (HTTP) + 7687 (Bolt), APOC plugin, 512MB page cache + 1GB max heap
- **pgadmin** (lines 183-200): Dev-only PostgreSQL web admin on port 5050

[FACT] Service dependencies: kosmos-app depends on postgres + redis (healthy). Neo4j depends on postgres + redis (healthy). This creates a startup order: postgres -> redis -> neo4j -> kosmos-app.

[FACT] All data services use Docker compose profiles: `["dev", "prod"]`. The kosmos application is `["prod"]` only.

---

## 8. Singleton Patterns

[PATTERN] Nearly all storage components use a module-level singleton with `get_*()` / `reset_*()` factory functions. Observed in 6+ instances:
- `kosmos/db/__init__.py:22-23` -- `_engine`, `_SessionLocal`
- `kosmos/knowledge/graph.py:1000` -- `_knowledge_graph`
- `kosmos/knowledge/vector_db.py:444` -- `_vector_db`
- `kosmos/world_model/factory.py:52` -- `_world_model`
- `kosmos/core/experiment_cache.py:726` -- `_experiment_cache`
- `kosmos/core/cache_manager.py:38-39` -- `CacheManager._instance` (class-level)

**Gotcha**: [FACT] The world model factory (`kosmos/world_model/factory.py:37`) explicitly documents that the implementation "is NOT thread-safe". The factory, singleton pattern, and underlying `KnowledgeGraph` do not use locks. Only `ExperimentCache` and `CacheManager` have explicit thread safety.

---

## 9. Key Architectural Observations

### Data Flow Between Stores

The stores are largely independent, with the following data relationships:
- **SQLAlchemy** stores structured experiment/hypothesis/result lifecycle data
- **Neo4j** stores literature knowledge graph (papers, citations, concepts, methods)
- **ChromaDB** stores paper embeddings for semantic search
- **SQLite cache** stores experiment results for reuse detection
- The `Paper` entity exists in both SQLAlchemy (`papers` table) and Neo4j (`:Paper` nodes) with no explicit synchronization mechanism

### Resilience Characteristics

[FACT] Neo4j failure is tolerated -- the world model falls back to `InMemoryWorldModel` (`factory.py:126-130`).
[FACT] ChromaDB failure is tolerated -- `PaperVectorDB` checks `self.collection is None` before operations (e.g., `vector_db.py:167, 219`).
[FACT] Redis failure is tolerated -- it's opt-in and only used in health checks.
[FACT] SQLAlchemy failure is NOT tolerated -- `get_session()` raises `RuntimeError` if `_SessionLocal is None` (`db/__init__.py:127`), and no fallback exists.

### Gotchas Summary

1. **Neo4j pool settings ignored**: `Neo4jConfig.max_connection_pool_size` and `max_connection_lifetime` are defined but never passed to py2neo's `Graph()` constructor (`graph.py:81-85`).
2. **Redis configured but unused**: Full Redis config, Docker service, and health check exist, but the application caching layer does not use Redis at all.
3. **Paper entity duplication**: Papers exist in both SQLAlchemy and Neo4j with no sync mechanism.
4. **World model not thread-safe**: Documented in `factory.py:37` -- concurrent access to the knowledge graph could cause issues.
5. **Experiment cache O(n) similarity**: Similarity search loads all cached experiments into memory (`experiment_cache.py:474`) -- will degrade with scale.
6. **Hardcoded credentials in docker-compose**: Neo4j password (`kosmos-password`) and Postgres password (`kosmos-dev-password`) are hardcoded in `docker-compose.yml:23,69,144`.
7. **Two separate SQLite databases**: The main app uses SQLAlchemy-managed SQLite (`kosmos.db`), while the experiment cache uses raw sqlite3 (`.kosmos_cache/experiments/experiments.db`). These are completely independent.
# Environment Dependencies and Hidden Coupling

## 1. External Service Dependencies

Kosmos depends on up to **five external services** at runtime, though only one (an LLM API) is strictly required. The others degrade gracefully.

### Service Dependency Map

| Service | Required? | Default Mode | Docker Service | Failure Behavior |
|---------|-----------|--------------|----------------|------------------|
| **LLM API** (Anthropic/OpenAI/LiteLLM) | **Yes** | Anthropic API | N/A (external) | Fatal -- `ValueError` at config init |
| **SQLite / PostgreSQL** | **Yes** | SQLite file (`kosmos.db`) | `kosmos-postgres` (prod) | Fatal -- `RuntimeError` from `get_session()` |
| **Neo4j** | No | bolt://localhost:7687 | `kosmos-neo4j` | Falls back to `InMemoryWorldModel` (`world_model/factory.py:126`) |
| **ChromaDB** | No | Local persist (`.chroma_db/`) | Embedded (volume mount) | Skips vector search; `HAS_CHROMADB` flag guards all operations |
| **Redis** | No | Disabled | `kosmos-redis` | No impact -- only used in health endpoint, not in caching layer |
| **Docker** | No | N/A | N/A | Neo4j auto-start fails silently; sandbox execution unavailable |
| **R** | No | System `Rscript` | `kosmos-sandbox` (Dockerfile.r) | R code execution unavailable; Python execution unaffected |

### Docker Compose Service Topology

[FACT] `docker-compose.yml` defines a startup ordering chain: PostgreSQL -> Redis -> Neo4j -> kosmos-app. Neo4j depends on both postgres and redis being healthy before starting (`docker-compose.yml:163-167`). The kosmos app depends on postgres and redis (`docker-compose.yml:40-44`).

[FACT] Docker compose uses profiles: `dev` (postgres, redis, neo4j, pgadmin), `prod` (all services including the app). Running without a profile starts nothing.

---

## 2. Required Environment Variables (Minimum to Run)

### Scenario: Default Anthropic Mode

| Variable | Required | Purpose | File:Line |
|----------|----------|---------|-----------|
| `ANTHROPIC_API_KEY` | **Yes** | Authenticates to Anthropic API (or all-9s for CLI proxy mode) | `config.py:37-39` |

One variable. Everything else has defaults. This starts Kosmos with:
- SQLite database (`kosmos.db` in project root)
- Claude Sonnet 4.5 model
- In-memory caching (no Redis)
- No Neo4j knowledge graph persistence
- No vector search

### Scenario: OpenAI Mode

| Variable | Required | Purpose | File:Line |
|----------|----------|---------|-----------|
| `LLM_PROVIDER` | Yes (must be `"openai"`) | Selects provider | `config.py:953` |
| `OPENAI_API_KEY` | **Yes** | Authenticates to OpenAI or compatible endpoint | `config.py:99` |

### Scenario: LiteLLM Mode (local models like Ollama)

| Variable | Required | Purpose | File:Line |
|----------|----------|---------|-----------|
| `LLM_PROVIDER` | Yes (must be `"litellm"`) | Selects provider | `config.py:953` |
| `LITELLM_MODEL` | Recommended | Model identifier (e.g., `ollama/llama3.1:8b`) | `config.py:155` |
| `LITELLM_API_BASE` | For local models | e.g., `http://localhost:11434` | `config.py:165` |
| `LITELLM_API_KEY` | For cloud only | Not needed for Ollama | `config.py:160` |

[FACT] LiteLLM validation is intentionally lenient -- no API key check at config init time (`config.py:1039-1042`). Errors surface only at first LLM call.

---

## 3. Complete Environment Variable Catalog

### 3a. Variables Managed by Pydantic Config (via `KosmosConfig`)

These are validated at startup. Invalid values raise `ValidationError`.

#### LLM Provider Selection
| Variable | Type | Default | Pydantic Alias | config.py Line |
|----------|------|---------|----------------|----------------|
| `LLM_PROVIDER` | `Literal["anthropic","openai","litellm"]` | `"anthropic"` | `LLM_PROVIDER` | 953 |

#### Anthropic/Claude
| Variable | Type | Default | Required? | config.py Line |
|----------|------|---------|-----------|----------------|
| `ANTHROPIC_API_KEY` | `str` | None | When LLM_PROVIDER=anthropic | 37 |
| `CLAUDE_MODEL` | `str` | `"claude-sonnet-4-5"` | No | 41 |
| `CLAUDE_MAX_TOKENS` | `int` [1-200000] | `4096` | No | 46 |
| `CLAUDE_TEMPERATURE` | `float` [0.0-1.0] | `0.7` | No | 52 |
| `CLAUDE_ENABLE_CACHE` | `bool` | `True` | No | 60 |
| `CLAUDE_BASE_URL` | `str?` | `None` | No | 66 |
| `CLAUDE_TIMEOUT` | `int` [1-600] | `120` | No | 71 |

#### OpenAI
| Variable | Type | Default | Required? | config.py Line |
|----------|------|---------|-----------|----------------|
| `OPENAI_API_KEY` | `str` | None | When LLM_PROVIDER=openai | 99 |
| `OPENAI_MODEL` | `str` | `"gpt-4-turbo"` | No | 103 |
| `OPENAI_MAX_TOKENS` | `int` [1-128000] | `4096` | No | 108 |
| `OPENAI_TEMPERATURE` | `float` [0.0-2.0] | `0.7` | No | 115 |
| `OPENAI_BASE_URL` | `str?` | `None` | No | 122 |
| `OPENAI_ORGANIZATION` | `str?` | `None` | No | 127 |
| `OPENAI_TIMEOUT` | `int` [1-600] | `120` | No | 132 |

#### LiteLLM
| Variable | Type | Default | Required? | config.py Line |
|----------|------|---------|-----------|----------------|
| `LITELLM_MODEL` | `str` | `"gpt-3.5-turbo"` | No | 155 |
| `LITELLM_API_KEY` | `str?` | `None` | Cloud providers only | 160 |
| `LITELLM_API_BASE` | `str?` | `None` | Local providers | 165 |
| `LITELLM_MAX_TOKENS` | `int` [1-128000] | `4096` | No | 170 |
| `LITELLM_TEMPERATURE` | `float` [0.0-2.0] | `0.7` | No | 177 |
| `LITELLM_TIMEOUT` | `int` [1-600] | `120` | No | 184 |

#### Local Model Tuning
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `LOCAL_MODEL_MAX_RETRIES` | `int` [0-5] | `1` | 760 |
| `LOCAL_MODEL_STRICT_JSON` | `bool` | `False` | 769 |
| `LOCAL_MODEL_JSON_RETRY_HINT` | `bool` | `True` | 775 |
| `LOCAL_MODEL_REQUEST_TIMEOUT` | `int` [30-600] | `120` | 782 |
| `LOCAL_MODEL_CONCURRENT_REQUESTS` | `int` [1-4] | `1` | 790 |
| `LOCAL_MODEL_FALLBACK_UNSTRUCTURED` | `bool` | `True` | 799 |
| `LOCAL_MODEL_CB_THRESHOLD` | `int` [1-10] | `3` | 806 |
| `LOCAL_MODEL_CB_RESET_TIMEOUT` | `int` [10-300] | `60` | 814 |

#### Research
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `MAX_RESEARCH_ITERATIONS` | `int` [1-100] | `10` | 203 |
| `ENABLED_DOMAINS` | comma-list | `biology,physics,chemistry,neuroscience` | 210 |
| `ENABLED_EXPERIMENT_TYPES` | comma-list | `computational,data_analysis,literature_synthesis` | 215 |
| `MIN_NOVELTY_SCORE` | `float` [0.0-1.0] | `0.6` | 220 |
| `ENABLE_AUTONOMOUS_ITERATION` | `bool` | `True` | 227 |
| `RESEARCH_BUDGET_USD` | `float` [>=0] | `10.0` | 232 |
| `MAX_RUNTIME_HOURS` | `float` [0.1-24.0] | `12.0` | 238 |

#### Database
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `DATABASE_URL` | `str` | `"sqlite:///kosmos.db"` | 253 |
| `DATABASE_ECHO` | `bool` | `False` | 258 |

#### Redis
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `REDIS_ENABLED` | `bool` | `False` | 313 |
| `REDIS_URL` | `str` | `"redis://localhost:6379/0"` | 308 |
| `REDIS_MAX_CONNECTIONS` | `int` [1-1000] | `50` | 318 |
| `REDIS_SOCKET_TIMEOUT` | `int` [1-60] | `5` | 325 |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | `int` [1-60] | `5` | 332 |
| `REDIS_RETRY_ON_TIMEOUT` | `bool` | `True` | 339 |
| `REDIS_DECODE_RESPONSES` | `bool` | `True` | 344 |
| `REDIS_DEFAULT_TTL_SECONDS` | `int` [60-86400] | `3600` | 349 |

#### Logging
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `LOG_LEVEL` | `Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]` | `"INFO"` | 368 |
| `LOG_FORMAT` | `Literal["json","text"]` | `"json"` | 373 |
| `LOG_FILE` | `str?` | `"logs/kosmos.log"` | 378 |
| `DEBUG_MODE` | `bool` | `False` | 383 |
| `DEBUG_LEVEL` | `Literal[0,1,2,3]` | `0` | 390 |
| `DEBUG_MODULES` | comma-list? | `None` | 396 |
| `LOG_LLM_CALLS` | `bool` | `False` | 402 |
| `LOG_AGENT_MESSAGES` | `bool` | `False` | 408 |
| `LOG_WORKFLOW_TRANSITIONS` | `bool` | `False` | 414 |
| `STAGE_TRACKING_ENABLED` | `bool` | `False` | 420 |
| `STAGE_TRACKING_FILE` | `str` | `"logs/stages.jsonl"` | 426 |

#### Literature APIs
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `SEMANTIC_SCHOLAR_API_KEY` | `str?` | `None` | 438 |
| `PUBMED_API_KEY` | `str?` | `None` | 443 |
| `PUBMED_EMAIL` | `str?` | `None` | 448 |
| `LITERATURE_CACHE_TTL_HOURS` | `int` [1-168] | `48` | 453 |
| `MAX_RESULTS_PER_QUERY` | `int` [1-1000] | `100` | 460 |
| `PDF_DOWNLOAD_TIMEOUT` | `int` [5-120] | `30` | 466 |
| `LITERATURE_SEARCH_TIMEOUT` | `int` [10-300] | `90` | 474 |
| `LITERATURE_API_TIMEOUT` | `int` [5-120] | `30` | 481 |

#### Vector DB
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `VECTOR_DB_TYPE` | `Literal["chromadb","pinecone","weaviate"]` | `"chromadb"` | 495 |
| `CHROMA_PERSIST_DIRECTORY` | `str` | `".chroma_db"` | 500 |
| `PINECONE_API_KEY` | `str?` | `None` | 505 |
| `PINECONE_ENVIRONMENT` | `str?` | `None` | 510 |
| `PINECONE_INDEX_NAME` | `str?` | `"kosmos"` | 515 |

#### Neo4j
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `NEO4J_URI` | `str` | `"bolt://localhost:7687"` | 537 |
| `NEO4J_USER` | `str` | `"neo4j"` | 542 |
| `NEO4J_PASSWORD` | `str` | `"kosmos-password"` | 547 |
| `NEO4J_DATABASE` | `str` | `"neo4j"` | 552 |
| `NEO4J_MAX_CONNECTION_LIFETIME` | `int` [>=60] | `3600` | 557 |
| `NEO4J_MAX_CONNECTION_POOL_SIZE` | `int` [>=1] | `50` | 563 |

#### Safety
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `ENABLE_SAFETY_CHECKS` | `bool` | `True` | 576 |
| `MAX_EXPERIMENT_EXECUTION_TIME` | `int` [>=1] | `300` | 581 |
| `MAX_MEMORY_MB` | `int` [>=128] | `2048` | 587 |
| `MAX_CPU_CORES` | `float?` [>=0.1] | `None` | 593 |
| `ENABLE_SANDBOXING` | `bool` | `True` | 599 |
| `REQUIRE_HUMAN_APPROVAL` | `bool` | `False` | 604 |
| `ETHICAL_GUIDELINES_PATH` | `str?` | `None` | 611 |
| `ENABLE_RESULT_VERIFICATION` | `bool` | `True` | 618 |
| `OUTLIER_THRESHOLD` | `float` [>=1.0] | `3.0` | 623 |
| `DEFAULT_RANDOM_SEED` | `int` | `42` | 631 |
| `CAPTURE_ENVIRONMENT` | `bool` | `True` | 636 |
| `APPROVAL_MODE` | `Literal["blocking","queue","automatic","disabled"]` | `"blocking"` | 643 |
| `AUTO_APPROVE_LOW_RISK` | `bool` | `True` | 648 |
| `NOTIFICATION_CHANNEL` | `Literal["console","log","both"]` | `"both"` | 655 |
| `NOTIFICATION_MIN_LEVEL` | `Literal["debug","info","warning","error","critical"]` | `"info"` | 660 |
| `USE_RICH_FORMATTING` | `bool` | `True` | 665 |
| `INCIDENT_LOG_PATH` | `str` | `"safety_incidents.jsonl"` | 672 |
| `AUDIT_LOG_PATH` | `str` | `"human_review_audit.jsonl"` | 677 |

#### Performance / Concurrency
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `ENABLE_RESULT_CACHING` | `bool` | `True` | 689 |
| `CACHE_TTL` | `int` [>=0] | `3600` | 694 |
| `PARALLEL_EXPERIMENTS` | `int` [>=0] | `0` | 700 |
| `ENABLE_CONCURRENT_OPERATIONS` | `bool` | `False` | 708 |
| `MAX_PARALLEL_HYPOTHESES` | `int` [1-10] | `3` | 713 |
| `MAX_CONCURRENT_EXPERIMENTS` | `int` [1-16] | `10` | 720 |
| `MAX_CONCURRENT_LLM_CALLS` | `int` [1-20] | `5` | 727 |
| `LLM_RATE_LIMIT_PER_MINUTE` | `int` [1-200] | `50` | 734 |
| `ASYNC_BATCH_TIMEOUT` | `int` [10-3600] | `300` | 741 |

#### World Model
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `WORLD_MODEL_ENABLED` | `bool` | `True` | 868 |
| `WORLD_MODEL_MODE` | `Literal["simple","production"]` | `"simple"` | 874 |
| `WORLD_MODEL_PROJECT` | `str?` | `None` | 880 |
| `WORLD_MODEL_AUTO_SAVE_INTERVAL` | `int` [>=0] | `300` | 886 |

#### Monitoring / Development
| Variable | Type | Default | config.py Line |
|----------|------|---------|----------------|
| `ENABLE_USAGE_STATS` | `bool` | `True` | 828 |
| `METRICS_EXPORT_INTERVAL` | `int` [>=0] | `60` | 833 |
| `HOT_RELOAD` | `bool` | `False` | 846 |
| `LOG_API_REQUESTS` | `bool` | `False` | 851 |
| `TEST_MODE` | `bool` | `False` | 856 |

### 3b. Variables Read Directly from `os.getenv()` -- NOT in Pydantic Config

These bypass config validation entirely. They cannot be inspected via `kosmos config --show` or validated via `kosmos config --validate`. This is a significant hidden coupling surface.

#### Monitoring/Alerts (alerts.py:362-549)
| Variable | Purpose | Default | Required? |
|----------|---------|---------|-----------|
| `ALERT_EMAIL_ENABLED` | Enable email alerts | `"false"` | No |
| `ALERT_EMAIL_FROM` | Sender address | `"alerts@kosmos.ai"` | When email enabled |
| `ALERT_EMAIL_TO` | Recipient address | `"admin@example.com"` | When email enabled |
| `SMTP_HOST` | SMTP server host | `"localhost"` | When email enabled |
| `SMTP_PORT` | SMTP server port | `"587"` | When email enabled |
| `SMTP_USER` | SMTP username | `None` | Optional (no auth) |
| `SMTP_PASSWORD` | SMTP password | `None` | Optional (no auth) |
| `ALERT_SLACK_ENABLED` | Enable Slack alerts | `"false"` | No |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook | `None` | When Slack enabled |
| `ALERT_PAGERDUTY_ENABLED` | Enable PagerDuty alerts | `"false"` | No |
| `PAGERDUTY_INTEGRATION_KEY` | PagerDuty routing key | `None` | When PagerDuty enabled |

[FACT] All 11 of these are read via `os.getenv()` at `monitoring/alerts.py:362-549`. They are invisible to the config singleton. There are no corresponding Pydantic fields.

#### Health Endpoint (api/health.py:226-338)
| Variable | Purpose | Default |
|----------|---------|---------|
| `REDIS_ENABLED` | Check Redis health | `"false"` |
| `REDIS_URL` | Redis connection URL | `"redis://localhost:6379/0"` |
| `ANTHROPIC_API_KEY` | Verify API key presence | None |
| `NEO4J_URI` | Neo4j connection | `"bolt://localhost:7687"` |
| `NEO4J_USER` | Neo4j username | `"neo4j"` |
| `NEO4J_PASSWORD` | Neo4j password | None |

[FACT] The health endpoint reads these 6 variables directly from `os.getenv()` instead of using the config singleton (`api/health.py:226-338`). If the `.env` file and actual environment diverge, the health endpoint may report different values than what the application uses.

#### Agent and Skill Configuration
| Variable | Purpose | Default | File:Line |
|----------|---------|---------|-----------|
| `KOSMOS_SKILLS_DIR` | Override scientific skills directory path | None (auto-discover) | `agents/skill_loader.py:148` |
| `EDITOR` | Text editor for `kosmos config --edit` | `"nano"` | `cli/commands/config.py:313` |

#### Provider Fallback Layer
| Variable | Purpose | File:Line |
|----------|---------|-----------|
| `ANTHROPIC_API_KEY` | Fallback if config dict has None | `core/providers/anthropic.py:88` |
| `CLAUDE_BASE_URL` | Fallback custom endpoint | `core/providers/anthropic.py:107` |
| `OPENAI_API_KEY` | Fallback if config dict has None | `core/providers/openai.py:106` |
| `OPENAI_BASE_URL` | Fallback custom endpoint | `core/providers/openai.py:116` |
| `OPENAI_ORGANIZATION` | Fallback org ID | `core/providers/openai.py:117` |

[FACT] Provider classes read `config.get('key') or os.environ.get('KEY')`, creating a secondary fallback path. This means an env var can override a `None` config value even when the `.env` file does not set it.

#### Legacy LLM Client
| Variable | Purpose | File:Line |
|----------|---------|-----------|
| `ANTHROPIC_API_KEY` | Direct read bypassing config | `core/llm.py:160` |
| `ANTHROPIC_API_KEY` | Direct read for async LLM init | `agents/research_director.py:228` |

#### Docker Sandbox Environment
| Variable | Purpose | Set In |
|----------|---------|--------|
| `PYTHONUNBUFFERED` | Force unbuffered Python output | `docker/sandbox/docker-compose.yml:47` |
| `MPLBACKEND` | Matplotlib headless backend | `docker/sandbox/docker-compose.yml:48` |
| `OMP_NUM_THREADS` | OpenMP thread limit | `docker/sandbox/docker-compose.yml:49` |

[FACT] These are injected into the sandbox container only, not the host. Defined in `docker/sandbox/docker-compose.yml:45-49`.

### 3c. Variables in `.env.example` But NOT in Pydantic Config

[FACT] `.env.example` documents `ENABLE_PROFILING` and `PROFILING_MODE` (lines 413-421), but these have no corresponding Pydantic field in `config.py`. They are consumed as constructor parameters by `kosmos/execution/executor.py`, and referenced in the profile CLI command (`cli/commands/profile.py:171`).

[FACT] `.env.example` documents `MAX_PARALLEL_HYPOTHESIS_EVALUATIONS` and `ENABLE_CONCURRENT_RESULT_ANALYSIS` (lines 406-407), labeled as "Legacy settings (for backward compatibility)." These are not in the Pydantic config either.

[FACT] `.env.example` documents domain-specific API keys (`KEGG_API_KEY`, `UNIPROT_API_KEY`, `MATERIALS_PROJECT_API_KEY`, `NASA_API_KEY`) at lines 319-328. None of these appear as Pydantic fields or `os.getenv()` calls anywhere in the Python source. They are aspirational placeholders with no implementation.

---

## 4. Hidden Coupling: Runtime Dependencies Not Visible in Imports

### 4a. Dynamic Imports and Optional SDK Loading

[FACT] `core/providers/factory.py:188-217` -- Provider registration wraps each provider import in try/except:
```python
try:
    from kosmos.core.providers.anthropic import AnthropicProvider
    register_provider("anthropic", AnthropicProvider)
except ImportError:
    logger.warning("Anthropic provider not available")
```
This means the `anthropic`, `openai`, and `litellm` Python packages are optional at import time but required at runtime for their respective providers. No clear error until first use.

[FACT] `knowledge/vector_db.py:19-27` -- ChromaDB import is wrapped with `HAS_CHROMADB` flag:
```python
try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
```
All ChromaDB operations are guarded by this flag. If chromadb is not installed, vector search is silently disabled.

[FACT] `core/async_llm.py:19-21` -- Async Anthropic availability is tested similarly:
```python
try:
    from anthropic import AsyncAnthropic
    ASYNC_ANTHROPIC_AVAILABLE = True
except ImportError:
    ASYNC_ANTHROPIC_AVAILABLE = False
```

[FACT] `cli/main.py:270-298` -- The CLI `status` command dynamically checks for 10 optional packages via `importlib.import_module()`: `anthropic`, `openai`, `litellm`, `chromadb`, `neo4j`, `redis`, `pandas`, `numpy`, `scipy`, `matplotlib`.

### 4b. Subprocess Dependencies (External Executables)

[PATTERN] 4 modules invoke external executables via `subprocess.run()`:

| Module | External Executable | Purpose | Failure Mode |
|--------|-------------------|---------|--------------|
| `knowledge/graph.py:126-160` | `docker`, `docker-compose` | Auto-start Neo4j container | Silent fallback (FileNotFoundError caught) |
| `execution/r_executor.py:117-140` | `Rscript`, `R` | Execute R code | Returns `is_r_available() == False` |
| `safety/reproducibility.py:236` | `pip` (via `sys.executable -m pip`) | Capture installed packages | Warning logged, empty dict |
| `cli/commands/config.py:316` | `$EDITOR` (default `nano`) | Open .env for editing | Raw subprocess error |

[FACT] The Neo4j auto-start at `knowledge/graph.py:118-171` is the most aggressive coupling: it runs `docker-compose up -d neo4j` without user consent if the container is not running. It also hardcodes the password `kosmos-password` in the health check command (`graph.py:153`).

### 4c. Network Requests Not Behind Obvious Interfaces

[FACT] `monitoring/alerts.py:466` makes HTTP POST to Slack webhook URLs via `requests.post()`. The `requests` library is imported inside the handler function, not at module level.

[FACT] `monitoring/alerts.py:511` makes HTTP POST to `https://events.pagerduty.com/v2/enqueue` for PagerDuty alerts. Also imported inside the function.

[FACT] The sandbox Docker containers have `network_mode: none` (`docker/sandbox/docker-compose.yml:27`), preventing sandboxed code from making network calls. This is a deliberate security constraint.

---

## 5. Configuration Precedence and Conflict Surfaces

### Pydantic-Settings Precedence (Highest Wins)

1. **Actual environment variables** (`os.environ`)
2. **`.env` file** (loaded from repo root by `KosmosConfig.model_config`)
3. **Field defaults** (defined in each `Field()`)

### Docker-Compose Override Layer

[FACT] `docker-compose.yml` hardcodes certain values that override `.env`:
- `DATABASE_URL=postgresql://kosmos:kosmos-dev-password@postgres:5432/kosmos` (line 18)
- `REDIS_ENABLED=true` (line 19)
- `REDIS_URL=redis://redis:6379/0` (line 20)
- `NEO4J_URI=bolt://neo4j:7687` (line 21)

These use Docker hostnames (`postgres`, `redis`, `neo4j`) that only resolve inside the Docker network. Running the app outside Docker with these values will fail.

### Default Model Mismatch

[FACT] Three sources disagree on the default Claude model:
- `config.py:42` (Pydantic default): `"claude-sonnet-4-5"` (new naming convention)
- `.env.example:32`: `CLAUDE_MODEL=claude-sonnet-4-5` (matches Pydantic)
- `docker-compose.yml:17`: `CLAUDE_MODEL=${CLAUDE_MODEL:-claude-3-5-sonnet-20241022}` (old naming convention)

The Docker fallback uses the old model name, which may not resolve to the same model.

---

## 6. Gotchas and Traps

### Gotcha 1: Provider Bypass Points

[FACT] Three modules read `ANTHROPIC_API_KEY` directly from `os.getenv()`, bypassing the provider selection system entirely:
1. `core/llm.py:160` -- Legacy `ClaudeClient.__init__()`
2. `agents/research_director.py:228` -- Async LLM initialization
3. `api/health.py:283` -- Health endpoint API check

If you switch `LLM_PROVIDER=openai`, these still check for the Anthropic key. The research_director's async path will be disabled even though OpenAI is the active provider.

### Gotcha 2: LiteLLM Env Var Sync Trap

[FACT] `config.py:986-1022` manually syncs `LITELLM_*` environment variables into the nested `LiteLLMConfig` object because Pydantic's nested `BaseSettings` submodels do not auto-load from the parent's `.env` file. If a new `LITELLM_*` field is added to `LiteLLMConfig`, the developer must also add it to the `env_map` dict in `sync_litellm_env_vars`, or it will silently use its default.

### Gotcha 3: Redis Configured But Not Used

[FACT] Despite comprehensive Redis configuration (8 env vars), a Docker service, and a health check, the actual caching layer (`CacheManager` in `core/cache_manager.py`) does NOT use Redis. It uses in-memory and disk-based caches. Setting `REDIS_ENABLED=true` only affects the health endpoint display.

### Gotcha 4: Neo4j Pool Settings Ignored

[FACT] `Neo4jConfig` defines `max_connection_pool_size` and `max_connection_lifetime` (config.py:557-568) but `KnowledgeGraph.__init__()` never passes these to the `py2neo.Graph()` constructor (`graph.py:81-85`). The settings exist in config but have no effect.

### Gotcha 5: Hardcoded Credentials in Version Control

[FACT] `docker-compose.yml` contains hardcoded passwords:
- Postgres: `kosmos-dev-password` (line 23, 69)
- Neo4j: `kosmos-password` (line 22, 144)
- pgAdmin: `admin` (line 191)

[FACT] `knowledge/graph.py:153` hardcodes `kosmos-password` in a subprocess call to `cypher-shell`, independent of any configuration.

[FACT] `config.py:547` defaults `NEO4J_PASSWORD` to `"kosmos-password"` in the Pydantic field.

### Gotcha 6: Domain API Keys Are Placeholders

[FACT] `.env.example` documents 4 domain-specific API keys (`KEGG_API_KEY`, `UNIPROT_API_KEY`, `MATERIALS_PROJECT_API_KEY`, `NASA_API_KEY`). None of these are referenced anywhere in the Python source code. They are aspirational placeholders with no implementation.

### Gotcha 7: ENABLE_PROFILING Exists Outside Pydantic

[FACT] `ENABLE_PROFILING` and `PROFILING_MODE` are documented in `.env.example` (lines 413-421) but have no Pydantic fields. They are consumed by the execution layer directly and referenced in `cli/commands/profile.py:171`. This means `kosmos config --validate` cannot check them.

---

## 7. Docker Sandbox Execution Environment

[FACT] The sandbox at `docker/sandbox/` provides an isolated execution environment with:
- Network isolation (`network_mode: none`)
- Read-only filesystem (except `/tmp` and mounted volumes)
- Resource limits: 2 CPU cores, 2GB RAM
- Security: `no-new-privileges:true`
- Controlled environment: `PYTHONUNBUFFERED=1`, `MPLBACKEND=Agg`, `OMP_NUM_THREADS=2`

[FACT] A separate `docker/sandbox/Dockerfile.r` exists for R execution support, alongside the Python sandbox `docker/sandbox/Dockerfile`.

---

## 8. Summary: Minimal vs Full Environment

### Minimal (Local Development, SQLite, Anthropic API)
```bash
ANTHROPIC_API_KEY=sk-ant-api03-...  # or 999...9 for CLI proxy
```
Total required env vars: **1**

### Standard (Local Development, All Optional Services)
```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
DATABASE_URL=sqlite:///kosmos.db
NEO4J_URI=bolt://localhost:7687
NEO4J_PASSWORD=kosmos-password
REDIS_ENABLED=false
```
Total configured env vars: **~10** (most use defaults)

### Production (Docker Compose, Full Stack)
```bash
ANTHROPIC_API_KEY=sk-ant-api03-...
DATABASE_URL=postgresql://kosmos:kosmos-dev-password@postgres:5432/kosmos
REDIS_ENABLED=true
REDIS_URL=redis://redis:6379/0
NEO4J_URI=bolt://neo4j:7687
NEO4J_PASSWORD=kosmos-password
LOG_LEVEL=INFO
ENABLE_CONCURRENT_OPERATIONS=true
```
Total configured env vars: **~15-20**

### Total Unique Environment Variables Across Entire System: **~110**
- Pydantic-managed: ~85
- Direct `os.getenv()` reads: ~17
- Docker-only: ~3
- Placeholder (no implementation): ~4
# Cross-Cutting Concern: Error Handling Strategy

## Codebase Scope

Analyzed 121 Python files across the `kosmos/` package containing 627 total `except` clauses and 260 `raise` statements. The error handling strategy is **multi-layered and intentionally heterogeneous**, varying by subsystem based on failure criticality.

---

## 1. Custom Exception Hierarchy

[FACT] Kosmos defines 7 custom exception classes, each scoped to a specific subsystem:

| Exception Class | File:Line | Purpose |
|---|---|---|
| `ProviderAPIError` | `core/providers/base.py:417` | LLM provider failures; carries `recoverable` flag, `status_code`, `raw_error` |
| `BudgetExceededError` | `core/metrics.py:63` | Cost budget limit; carries `current_cost`, `limit`, `usage_percent` |
| `JSONParseError` | `core/utils/json_parser.py:21` | LLM response parsing; carries `original_text`, `attempts` count |
| `CacheError` | `core/cache.py:22` | Generic cache failures (thin wrapper, no extra fields) |
| `LiteratureCacheError` | `literature/cache.py:19` | Literature-specific cache failures (thin wrapper) |
| `PDFExtractionError` | `literature/pdf_extractor.py:22` | PDF processing failures (thin wrapper) |
| Placeholder stubs: `APIError`, `APITimeoutError`, `RateLimitError` | `core/async_llm.py:23-31` | Created when `anthropic` SDK not installed; prevents `isinstance()` false matches |

[PATTERN] Only `ProviderAPIError` and `BudgetExceededError` carry structured recovery metadata. The remaining 4 custom exceptions are thin `Exception` subclasses with `pass` bodies -- they exist for type-based dispatch but carry no extra context. (Observed in 4/7 custom exceptions.)

---

## 2. Dominant Strategy: Log-and-Return-Default

[PATTERN] The dominant error handling pattern (observed in 60+ instances across 30+ files) is:

```python
try:
    # operation
except Exception as e:
    logger.error(f"Description: {e}")
    return []  # or None, {}, 0, False
```

**Representative examples:**

- `hypothesis/novelty_checker.py:216-218` -- literature search failure returns `[]` [FACT]
- `hypothesis/novelty_checker.py:256-258` -- vector search failure returns `[]` [FACT]
- `core/experiment_cache.py:444-446` -- cache lookup failure returns `None` [FACT]
- `hypothesis/testability.py:488-490` -- LLM assessment failure returns `None` [FACT]
- `core/stage_tracker.py:112` -- stage tracking failure caught and logged [FACT]

**Rationale:** This strategy reflects Kosmos's architecture as an autonomous research loop. Most subsystems are non-critical enhancements (novelty checking, caching, visualization). A failure in one subsystem should not halt an entire multi-hour research cycle.

---

## 3. LLM/API Layer: Retry + Circuit Breaker

[FACT] The LLM communication layer (`core/async_llm.py`) implements a sophisticated 3-tier resilience stack:

### Tier 1: Tenacity-Based Retry (lines 440-470)
- Exponential backoff: `wait_exponential(multiplier=1, min=2, max=30)`
- Max 3 attempts: `stop_after_attempt(3)`
- Custom retry predicate: only retries "recoverable" errors
- Conditional: only active when `tenacity` package is installed

### Tier 2: Circuit Breaker (lines 51-129)
- 3 states: CLOSED (normal), OPEN (blocking), HALF_OPEN (testing)
- Opens after 3 consecutive failures (`failure_threshold=3`)
- Auto-resets after 60 seconds (`reset_timeout=60.0`)
- Raises `ProviderAPIError` with `recoverable=True` when open

### Tier 3: Recoverability Classification (lines 141-169)
- `is_recoverable_error()` classifies exceptions by type:
  - `RateLimitError` and `APITimeoutError`: always recoverable
  - `ProviderAPIError`: checks `.is_recoverable()` method
  - `APIError`: scans message for 'invalid', 'authentication', 'unauthorized', 'forbidden'
  - Unknown exceptions: default to recoverable

[FACT] `ProviderAPIError.is_recoverable()` at `core/providers/base.py:445-469` further classifies by HTTP status: 4xx (except 429) are non-recoverable; message patterns like 'timeout', 'rate_limit', '503' are recoverable.

---

## 4. Agent Layer: Backoff + State Machine

[FACT] `agents/research_director.py:44-47` defines the orchestration-level error recovery:

```python
MAX_CONSECUTIVE_ERRORS = 3
ERROR_BACKOFF_SECONDS = [2, 4, 8]  # Exponential backoff delays
```

[FACT] The `_handle_error()` method at line 600 implements:
1. Consecutive error counting and history recording
2. Exponential backoff with sleep (`time.sleep(backoff_seconds)`)
3. Circuit breaker: transitions to `WorkflowState.ERROR` after `MAX_CONSECUTIVE_ERRORS`
4. Recoverable/non-recoverable branching
5. After successful operations, `_reset_error_streak()` (line 686) clears the counter

This is **separate from** the LLM-layer circuit breaker -- the agent has its own error budget independent of API retry behavior.

---

## 5. Graceful Import Degradation

[PATTERN] 41 files use `try/except ImportError` to handle optional dependencies, with 7 files setting `*_AVAILABLE = False` flags. (Observed across all subsystems.)

**Notable instances:**
- `core/async_llm.py:17-44` -- `anthropic` SDK and `tenacity` both optional; creates placeholder exception classes when absent [FACT]
- `execution/executor.py:24-36` -- Docker sandbox and R executor both optional; falls back to restricted builtins [FACT]
- `core/providers/__init__.py:57-59` -- LiteLLM optional [FACT]
- `monitoring/metrics.py:18-19` -- Prometheus optional [FACT]

[PATTERN] The standard pattern is:
```python
try:
    from foo import Bar
    FOO_AVAILABLE = True
except ImportError:
    FOO_AVAILABLE = False
```
Then the feature check happens at initialization, not at call-time.

---

## 6. Swallowed Exceptions (Silent Failures)

[PATTERN] Found 30+ instances of `except Exception: pass` or `except Exception: continue` across 17 files. These are **not accidental** -- they cluster in specific contexts:

### Category A: Cleanup/Teardown (Justified)
- `execution/sandbox.py:214` -- temp directory cleanup [FACT]
- `execution/docker_manager.py:414` -- container cleanup [FACT]
- `execution/r_executor.py:358` -- R process cleanup [FACT]
- `execution/executor.py:535` -- process termination [FACT]

### Category B: Optional Diagnostics (Justified)
- `world_model/simple.py:926-938` -- Neo4j APOC/stats queries for health check [FACT]
- `api/health.py:374-394` -- health endpoint version/uptime detection [FACT]
- `agents/base.py:286-287, 351-352` -- optional config-driven message logging [FACT]

### Category C: Data Parsing in Loops (Debatable)
- `literature/unified_search.py:182-183, 279-280, 317-318` -- skips unparseable search results [FACT]
- `agents/research_director.py:1304-1305` -- skips unparseable p-values in FDR correction [FACT]

### Category D: Best-Effort Infrastructure (Debatable)
- `knowledge/vector_db.py:94-95` -- silent collection creation failure [FACT]
- `core/workflow.py:297-298` -- silent workflow state save failure [FACT]
- `execution/provenance.py:36-37` -- silent provenance recording failure [FACT]

**Gotcha:** Category D items are the riskiest. A silent failure in `core/workflow.py:297` means workflow state may not be persisted, but the system continues as if it were. A silent failure in `execution/provenance.py:36` means experiment provenance is silently lost -- undermining reproducibility claims.

---

## 7. Validation Layer: ValueError for Domain Constraints

[PATTERN] Pydantic-style model validators use `raise ValueError(...)` extensively -- 30+ instances across model files. These fire during object construction (Pydantic `@validator` and `__post_init__`).

**Key files:**
- `models/hypothesis.py:91-194` -- 6 validators (empty statement, question detection, rationale length, research question) [FACT]
- `models/experiment.py:75-189` -- 5 validators (empty description, field length) [FACT]
- `world_model/models.py:63-555` -- 8 validators (entity type, confidence range, annotation text, relationship type) [FACT]

[FACT] The `orchestration/delegation.py` file uses `raise RuntimeError(...)` at 6 locations (lines 397, 433, 471, 515, 546, 552) to signal missing agent dependencies. These are configuration errors, not runtime errors -- the messages include prescriptive fix instructions like "Pass agents={'data_analyst': DataAnalystAgent(), ...} at init."

---

## 8. Database Layer: Rollback-and-Reraise

[FACT] `db/__init__.py:130-137` implements the session context manager:
```python
session = _SessionLocal()
try:
    yield session
    session.commit()
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

This is the **only place** in the codebase that catches `Exception` without binding to a variable and re-raises. The pattern ensures transaction integrity while preserving the original exception chain.

---

## 9. JSON Parsing: Multi-Strategy Fallback

[FACT] `core/utils/json_parser.py:31-145` implements a 7-strategy fallback chain for parsing LLM JSON responses:
1. Direct `json.loads()`
2. Extract from `` ```json `` code blocks (closed)
3. Extract from unclosed `` ```json `` blocks (truncated responses)
4. Extract from generic `` ``` `` code blocks
5. Regex extraction of `{...}` objects
6. Clean common issues (trailing commas, single quotes) + retry
7. Combine cleaning with extracted objects

Each strategy catches `json.JSONDecodeError` specifically and falls through to the next. Only after all 7 strategies fail does it raise `JSONParseError` with the attempt count. This is the most defense-in-depth error handling in the codebase.

---

## 10. External API Layer: Tenacity Decorators

[FACT] `domains/neuroscience/apis.py` uses `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))` decorators on 7 API methods (lines 106, 174, 218, 319, 356, 537, 565). This is a **decorator-based** retry pattern -- distinct from the imperative retry in `core/async_llm.py`.

[ABSENCE] No other domain API files (`domains/biology/apis.py`, `domains/materials/apis.py`) use tenacity decorators. They catch `httpx.HTTPError` directly. This is an inconsistency between domain implementations.

---

## 11. Safety/Guardrails: Fail-Loud

[FACT] `safety/guardrails.py` uses `raise RuntimeError(...)` for emergency stop conditions (lines 129, 200). The safety context manager at line 330 re-raises all exceptions:
```python
try:
    yield
except Exception as e:
    if self.is_emergency_stop_active():
        logger.error(f"Execution interrupted by emergency stop: {e}")
        raise
    raise  # Re-raise ALL exceptions
```

This is deliberately the **opposite** of the log-and-continue pattern used elsewhere. Safety violations must never be silently swallowed.

[FACT] `oversight/human_review.py:214` raises `RuntimeError(f"Approval denied: {reason}")` when human review is rejected. This halts the pipeline -- by design, a denied approval is not a recoverable error.

---

## 12. Summary of Strategy by Subsystem

| Subsystem | Strategy | Exceptions Used |
|---|---|---|
| LLM/API (`core/async_llm`, `core/providers/`) | Retry + circuit breaker + recoverability classification | `ProviderAPIError`, `RateLimitError`, `APITimeoutError` |
| Agent orchestration (`agents/research_director`) | Backoff + consecutive-error circuit breaker + state machine | Standard `Exception` |
| Data models (`models/`) | Fail-fast validation at construction | `ValueError` |
| World model (`world_model/`) | Log-and-raise for mutations; log-and-return-empty for queries | `ValueError` |
| Execution (`execution/`) | Retry with self-correcting code repair | Standard `Exception` |
| Database (`db/`) | Rollback-and-reraise | Bare `Exception` |
| Safety (`safety/`) | Fail-loud: always raise | `RuntimeError` |
| Literature (`literature/`) | Log-and-return-empty for searches | `Exception` |
| Cache (`core/cache`, `core/experiment_cache`) | Log-and-return-None (cache miss) or log-and-raise (cache write) | `CacheError`, `Exception` |
| CLI (`cli/`) | Catch-and-display-user-message | `Exception`, `typer.Exit` |

---

## 13. Key Gotchas

1. **Silent provenance loss** [FACT]: `execution/provenance.py:36-37` swallows all exceptions during provenance recording. If provenance write fails, experiment results appear valid but are not reproducibility-tracked.

2. **Silent workflow state loss** [FACT]: `core/workflow.py:297-298` swallows exceptions during workflow state persistence. The in-memory state diverges from the persisted state without notification.

3. **Inconsistent domain retry** [FACT]: `domains/neuroscience/apis.py` uses `@retry` decorators; `domains/biology/apis.py` and `domains/materials/apis.py` do not. A network failure in biology/materials APIs will fail immediately while neuroscience retries 3 times.

4. **Double-layer circuit breakers** [FACT]: Both `core/async_llm.py:51` (LLM layer, threshold=3, timeout=60s) and `agents/research_director.py:45` (agent layer, threshold=3, backoff=[2,4,8]s) have independent circuit breakers. An LLM failure may trigger both circuit breakers, causing longer-than-expected recovery delays.

5. **Tenacity is optional** [FACT]: `core/async_llm.py:44` sets `TENACITY_AVAILABLE = False` if import fails. Without tenacity, the LLM layer makes single-shot API calls with no retry -- this fundamentally changes resilience behavior and is not surfaced to the user.

6. **Cache write raises, cache read returns None** [FACT]: `core/experiment_cache.py:391-393` raises on cache write failure but `core/experiment_cache.py:444-446` returns `None` on cache read failure. A caller that writes successfully but gets `None` on subsequent read will re-execute the experiment.

7. **`except (httpx.HTTPError, RetryError, Exception)`** [FACT]: `domains/biology/apis.py:93` catches `Exception` alongside specific types, making the specific catches dead code. The `Exception` catch subsumes both `httpx.HTTPError` and `RetryError`.
# Implicit Initialization Sequences and Startup Dependencies

## Summary

Kosmos has a multi-layered initialization chain with at least 8 singleton subsystems that are lazily initialized in a partially-ordered sequence. The system is forgiving of failures in optional subsystems (Neo4j, ChromaDB, Redis) but critically depends on config and database initialization succeeding. Initialization order is implicit -- there is no central bootstrap function -- and is instead driven by the first call to each `get_*()` singleton factory.

---

## 1. CLI Entry Point Initialization Sequence

[FACT] The startup sequence for `kosmos run` is defined across three files. It proceeds in this order:

### Phase 1: Module-Level Side Effects (on import)

1. **dotenv loading**: `kosmos/cli/main.py:22` calls `load_dotenv()` at module import time, before any function runs. This populates `os.environ` from the repo-root `.env` file.
2. **Rich traceback installation**: `kosmos/cli/main.py:35` calls `install_rich_traceback()` at import time.
3. **Typer app creation**: `kosmos/cli/main.py:39-45` creates the `app` Typer instance at import time.
4. **Command registration**: `kosmos/cli/main.py:419` calls `register_commands()` at import time, which imports all command modules (`run`, `status`, `history`, `cache`, `config`, `profile`, `graph`).
5. **Provider auto-registration**: When `kosmos.core.providers` is imported (transitively), `factory.py:217` calls `_register_builtin_providers()` at module scope, registering Anthropic, OpenAI, and LiteLLM providers.

### Phase 2: Typer Callback (runs before any command)

[FACT] `kosmos/cli/main.py:98-169` defines the `@app.callback()` which runs before every command. It performs:

6. **CLI logging setup**: `setup_logging()` (main.py:132) configures Python's `logging.basicConfig` with file + stream handlers.
7. **Config singleton (first access)**: If `--trace` is set, `get_config()` is called (main.py:77) to enable debug toggles. This triggers the **config singleton creation**.
8. **Database initialization**: `init_from_config()` (main.py:145-146) triggers three sub-steps:
   - a. `first_time_setup()` -> `ensure_env_file()` (copies `.env.example` to `.env` if missing)
   - b. `first_time_setup()` -> `run_database_migrations()` (runs `alembic upgrade head`)
   - c. `first_time_setup()` -> `validate_database_schema()` (checks tables and indexes)
   - d. `init_database()` (creates SQLAlchemy engine + session factory, creates tables via `Base.metadata.create_all`)
9. **Quiet mode**: If `--quiet`, suppresses Rich console output.

### Phase 3: `run_research` Command

[FACT] `kosmos/cli/commands/run.py:51-222` performs additional initialization:

10. **Config re-access**: `get_config()` (run.py:132) retrieves the existing singleton, mutates it with CLI overrides (domain, max_iterations, budget, cache).
11. **ResearchDirectorAgent creation** (run.py:173-177): This triggers a deep initialization cascade (see Section 2).
12. **AgentRegistry**: `get_registry()` (run.py:181) creates the singleton agent registry, then registers the director.
13. **Async execution**: `asyncio.run(run_with_progress_async(...))` (run.py:186) starts the async event loop.

---

## 2. ResearchDirectorAgent Initialization Cascade

[FACT] `ResearchDirectorAgent.__init__()` (research_director.py:68-259) is the heaviest initialization in the system. It triggers the following sub-initializations:

### 2a. Inherited from BaseAgent

[FACT] `BaseAgent.__init__()` (agents/base.py:113-153) creates the agent's message queue (`asyncio.Queue`), state data dict, and sets status to `CREATED`. Lightweight, no external dependencies.

### 2b. LLM Client Singleton

[FACT] `get_client()` (core/llm.py:613-679) is called at research_director.py:128. This:
- Acquires a threading lock (`_client_lock`)
- Calls `get_config()` (config must exist)
- Calls `get_provider_from_config(config)` which:
  - Reads `config.llm_provider` to select provider
  - Extracts provider-specific config (API key, model, etc.)
  - Calls `get_provider(name, config)` which looks up the provider class in `_PROVIDER_REGISTRY`
  - Instantiates the provider (e.g., `AnthropicProvider(config)`)
- On failure, falls back to creating `AnthropicProvider` with env vars directly

**Dependency**: Requires config singleton. If `ANTHROPIC_API_KEY` is missing and provider is anthropic, this will fail.

### 2c. Database Re-initialization (Defensive)

[FACT] research_director.py:131-139 calls `init_from_config()` again, wrapped in try/except. This is a defensive re-initialization in case the database was not already set up. If `init_database()` was already called, this runs through first_time_setup again but `Base.metadata.create_all` is idempotent.

### 2d. Convergence Detector

[FACT] `ConvergenceDetector` (research_director.py:168-178) is a pure logic object. No external dependencies. Initialized with mandatory/optional stopping criteria from config.

### 2e. ParallelExperimentExecutor (Conditional)

[FACT] research_director.py:209-219: If `enable_concurrent_operations=True`, lazily imports and creates `ParallelExperimentExecutor`. On ImportError, falls back to sequential mode.

### 2f. AsyncClaudeClient (Conditional)

[FACT] research_director.py:222-239: If concurrent operations enabled, creates `AsyncClaudeClient` using `os.getenv("ANTHROPIC_API_KEY")` directly -- **bypassing the config/provider system entirely**. This is hardcoded to Anthropic even if `LLM_PROVIDER=openai`.

### 2g. World Model Singleton (Heavy)

[FACT] research_director.py:242-255 calls `get_world_model()`. This triggers:

1. `get_config()` (lazy import inside factory.py:110 -- avoids circular dep)
2. Reads `config.world_model.mode` (default: `"simple"`)
3. Creates `Neo4jWorldModel()` which calls `get_knowledge_graph()` which:
   - a. Calls `get_config()` to read Neo4j URI/credentials
   - b. Calls `_ensure_container_running()` which shells out to `docker ps` and potentially `docker-compose up -d neo4j`, waiting up to 60 seconds
   - c. Creates `py2neo.Graph()` connection
   - d. Runs `RETURN 1` health check
   - e. Creates 8 Neo4j indexes
4. If Neo4j is unavailable, falls back to `InMemoryWorldModel()`

**Key**: This can block for up to 60 seconds if Docker container needs starting. If Docker is not installed, it gracefully degrades.

### 2h. Research Question Entity Persistence

[FACT] research_director.py:245-251: After world model init, creates an `Entity` for the research question and persists it to the knowledge graph via `wm.add_entity()`. On failure, sets `self.wm = None` and continues.

---

## 3. Complete Singleton Inventory

[PATTERN] Kosmos uses 10+ module-level singletons, all following the same pattern: `_instance = None` at module scope, `get_*()` factory that creates-on-first-call, `reset_*()` for testing. Observed in all cases below:

| Singleton | Location | Factory | Depends On | Thread-Safe |
|-----------|----------|---------|------------|-------------|
| `KosmosConfig` | config.py:1137 | `get_config()` | `.env` file, env vars | No |
| SQLAlchemy engine | db/__init__.py:22-23 | `init_database()` | Config | No |
| LLM Client | core/llm.py:608-609 | `get_client()` | Config, provider registry | Yes (threading.Lock) |
| `KnowledgeGraph` | knowledge/graph.py:1000 | `get_knowledge_graph()` | Config, Neo4j (optional) | No |
| `WorldModelStorage` | world_model/factory.py:52 | `get_world_model()` | Config, KnowledgeGraph | No (documented) |
| `PaperVectorDB` | knowledge/vector_db.py:444 | `get_vector_db()` | Config, ChromaDB (optional) | No |
| `ExperimentCache` | core/experiment_cache.py:726 | `get_experiment_cache()` | Filesystem | Yes (threading.RLock) |
| `CacheManager` | core/cache_manager.py:38-39 | `CacheManager()` (cls) | Config | Yes (threading.Lock) |
| `StageTracker` | core/stage_tracker.py:244 | `get_stage_tracker()` | Config (optional) | No |
| `AgentRegistry` | agents/registry.py:509 | `get_registry()` | None | No |
| Provider registry | core/providers/factory.py:16 | Module-level dict | Module import | No |

---

## 4. Initialization Dependency Graph

```
.env file (dotenv)
    |
    v
KosmosConfig (get_config)
    |
    +-------> DatabaseConfig.normalized_url
    |             |
    |             v
    |         first_time_setup()
    |             |-- ensure_env_file()
    |             |-- run_database_migrations() [alembic upgrade head]
    |             \-- validate_database_schema()
    |                     |
    |                     v
    |              init_database() [engine + session factory + create_all]
    |
    +-------> LLM Provider (get_client)
    |             |-- get_provider_from_config(config)
    |             |-- _PROVIDER_REGISTRY lookup
    |             \-- Provider class instantiation (needs API key)
    |
    +-------> Neo4jConfig
    |             |
    |             v
    |         KnowledgeGraph.__init__()
    |             |-- _ensure_container_running() [docker subprocess, up to 60s]
    |             |-- py2neo.Graph() connection
    |             \-- _create_indexes()
    |                     |
    |                     v
    |              WorldModel (get_world_model)
    |                  |-- Neo4jWorldModel (if connected)
    |                  \-- InMemoryWorldModel (fallback)
    |
    +-------> CacheManager (thread-safe singleton)
    |             \-- Creates InMemoryCache + DiskCache + HybridCache instances
    |
    \-------> StageTracker (get_stage_tracker)
                  \-- Reads config.logging.stage_tracking_enabled
```

---

## 5. Initialization Order Violations and Their Consequences

### 5a. Database Session Before init_database()

[FACT] `kosmos/db/__init__.py:126-127`: `get_session()` raises `RuntimeError("Database not initialized. Call init_database() first.")` if `_SessionLocal is None`. Any code that calls `get_session()` before the CLI callback's `init_from_config()` completes will crash.

**Mitigation**: ResearchDirectorAgent defensively calls `init_from_config()` again in its own `__init__` (research_director.py:131-139), but this is a band-aid, not a guarantee.

### 5b. Config Access Before .env Loading

[FACT] `load_dotenv()` happens at `cli/main.py:22` (module import time). If code is imported before `cli/main.py` (e.g., in tests or from a non-CLI entry point), `os.environ` will not contain `.env` values. Pydantic-settings has its own `.env` reading via `env_file` (config.py:979), but the `load_dotenv()` call at CLI level is redundant and can mask this.

**Impact**: For non-CLI usage (importing `kosmos` as a library), the `KosmosConfig` Pydantic model reads `.env` directly via its `env_file` setting. But `load_dotenv()` also injects vars into `os.environ`, and these take precedence. In CLI usage, both paths fire, but the CLI's `load_dotenv()` runs first. For library usage, only Pydantic's reading applies.

### 5c. Provider Registry Before Factory Import

[FACT] `_register_builtin_providers()` runs at `factory.py:217` when the module is imported. If provider SDK packages are not installed, their registration silently fails. If `get_provider()` is called with a name that failed registration, it raises `ProviderAPIError` with "Unknown provider".

**Impact**: Silent degradation. The `list_providers()` call will return fewer providers than expected, but there is no startup check that the configured provider was successfully registered.

### 5d. World Model Before Config

[FACT] `world_model/factory.py:109-110` uses lazy import `from kosmos.config import get_config` inside the function body, explicitly documented as "lazy import to avoid circular dependencies". This means `get_world_model()` will create the config singleton if it does not already exist.

**Impact**: This is safe but creates a hidden config initialization path that does not go through the CLI callback.

### 5e. KnowledgeGraph Before Docker

[FACT] `KnowledgeGraph.__init__()` (graph.py:76) calls `_ensure_container_running()` by default. This shells out to `docker` and `docker-compose`. If Docker is not installed, it catches `FileNotFoundError` (graph.py:170-171) and proceeds. If Docker is installed but the compose file is not present or the daemon is not running, it catches `CalledProcessError` (graph.py:167-169) and proceeds.

**Impact**: Up to 60 seconds of blocking during first initialization if Neo4j container needs to start. The user sees no progress indicator during this wait. No async variant exists.

---

## 6. Redundant / Defensive Re-initialization

[PATTERN] Multiple components defensively call `init_from_config()` or `get_config()` even though the CLI callback already does this. Observed in 3 locations:

1. **CLI callback** (main.py:145): Primary initialization site
2. **ResearchDirectorAgent.__init__** (research_director.py:131): Defensive re-init, catches errors
3. **`doctor` command** (main.py:320-331): Calls `get_session()` which requires prior `init_database()`

[FACT] `init_database()` is NOT idempotent in a strict sense: calling it twice creates a new engine and session factory, overwriting the globals (db/__init__.py:67). However, `Base.metadata.create_all()` is idempotent (does not fail if tables exist). The `first_time_setup()` wrapper is safe to call multiple times.

---

## 7. Package-Level Import Chains

### 7a. `kosmos/__init__.py` Import Chain

[FACT] `kosmos/__init__.py:17-18` imports two symbols at package level:
```python
from kosmos.config import get_config
from kosmos.agents.research_director import ResearchDirectorAgent
```

Importing `ResearchDirectorAgent` triggers a deep import chain:
- `agents/base.py` (asyncio, pydantic, uuid -- lightweight)
- `core/rollout_tracker.py`
- `core/workflow.py`
- `core/convergence.py`
- `core/llm.py` -> `core/providers/` -> triggers `_register_builtin_providers()`
- `core/stage_tracker.py`
- `models/hypothesis.py`
- `world_model/__init__.py` -> imports `factory.py`, `interface.py`, `models.py`, `artifacts.py`
- `db/__init__.py` -> imports `db/models.py` (SQLAlchemy models)
- `db/operations.py`
- `agents/skill_loader.py`

**Impact**: Simply importing `import kosmos` triggers provider registration and loads a significant portion of the codebase. No singletons are created (those are lazy), but module-level code in provider factory runs.

### 7b. `kosmos/knowledge/__init__.py` Import Chain

[FACT] `kosmos/knowledge/__init__.py` eagerly imports ALL knowledge components at package level: `PaperEmbedder`, `PaperVectorDB`, `KnowledgeGraph`, `ConceptExtractor`, `GraphBuilder`, `GraphVisualizer`, `DomainKnowledgeBase`. Each of these modules imports their dependencies (py2neo, chromadb, etc.) at module scope.

**Impact**: Importing `from kosmos.knowledge import KnowledgeGraph` also imports the embedder, vector DB, concept extractor, graph builder, and visualizer. This is heavy and can fail if optional packages (chromadb, py2neo) are not installed.

---

## 8. Circular Dependency Prevention

[FACT] Only two explicit circular-dependency mitigations exist in the codebase:
1. `world_model/factory.py:109`: `from kosmos.config import get_config` inside function body (documented)
2. `execution/figure_manager.py:133`: Lazy load visualizer to avoid circular imports

[ABSENCE] Searched for `# avoid circular`, `# circular`, `lazy.*import` across all Python files. Only these two instances found. The codebase generally avoids circular imports through architecture (config at root, agents at leaves) rather than explicit lazy imports.

---

## 9. Failure Modes During Initialization

| Component | Failure | Behavior | Evidence |
|-----------|---------|----------|----------|
| `.env` file missing | Config uses defaults + env vars | `ensure_env_file()` copies from `.env.example`; if that also missing, warns and continues. config.py:978-979 reads `.env` directly | setup.py:15-50 |
| `ANTHROPIC_API_KEY` missing | `KosmosConfig` raises `ValueError` during validation | Hard failure if `LLM_PROVIDER=anthropic` | config.py:1033-1038 |
| Database init fails | CLI callback catches exception, prints error, **does not exit** | Commands that need DB will fail later when calling `get_session()` | main.py:148-165 |
| Alembic not installed | Migration skipped, tables created by `create_all` instead | Tables created but no migration tracking | setup.py:105-108 |
| Neo4j unavailable | World model falls back to `InMemoryWorldModel` | Data does not persist across sessions | factory.py:124-131 |
| Docker not installed | Neo4j auto-start skipped silently | `FileNotFoundError` caught at graph.py:170-171 | graph.py:170-171 |
| ChromaDB not installed | `PaperVectorDB.client = None`, operations become no-ops | `HAS_CHROMADB` flag checked at vector_db.py:19-27 | vector_db.py:19-27 |
| Provider SDK missing | Provider not registered, `get_client()` may fail | Falls back to `AnthropicProvider` with env vars | llm.py:662-673 |
| Asyncio loop conflict | `asyncio.Queue()` in `BaseAgent.__init__` may warn | Queue created outside running loop; works when loop starts | base.py:137 |

---

## 10. Key Gotchas

### Gotcha 1: No Central Bootstrap

[ABSENCE] There is no single `bootstrap()` or `startup()` function that initializes all subsystems in order. Initialization is scattered across: CLI callback (main.py:98-169), command functions (run.py:127-177), agent constructors (research_director.py:68-259), and singleton factories. The order depends on the call path.

### Gotcha 2: Config Mutation After Creation

[FACT] The `run_research` command mutates the config singleton after creation (run.py:135-144): `config_obj.research.enabled_domains = [domain]`, `config_obj.research.max_iterations = max_iterations`. Any code that accessed config before these mutations sees the pre-mutation values. Since the config is a singleton, these mutations affect all subsequent readers.

### Gotcha 3: Dual Database Init

[FACT] The database is initialized both in the CLI callback (main.py:145) and defensively in `ResearchDirectorAgent.__init__` (research_director.py:131). The second call re-runs `first_time_setup()` and `init_database()`, which overwrites the global engine/session factory. This is wasteful but functionally harmless due to `create_all` idempotency.

### Gotcha 4: `load_dotenv()` Redundancy

[FACT] `.env` is loaded twice: once by `load_dotenv()` (main.py:22, injecting into `os.environ`) and once by Pydantic's `env_file` setting (config.py:979). The `load_dotenv()` call populates `os.environ`, and Pydantic-settings reads from `os.environ` first (higher precedence than `env_file`). This means the `load_dotenv()` call effectively wins, making Pydantic's `env_file` reading redundant when the CLI is used.

### Gotcha 5: AsyncClaudeClient Bypasses Provider System

[FACT] `research_director.py:228` reads `ANTHROPIC_API_KEY` directly from `os.getenv()` to create `AsyncClaudeClient`, completely bypassing the `LLM_PROVIDER` selection system and config singleton. This means concurrent LLM operations are always Anthropic-only, even if the user configured OpenAI or LiteLLM.

### Gotcha 6: 60-Second Silent Block

[FACT] `KnowledgeGraph._ensure_container_running()` (graph.py:118-171) can block for up to 60 seconds while waiting for the Neo4j Docker container. During `ResearchDirectorAgent.__init__`, this happens synchronously with no user feedback. The `--verbose` flag only affects Python logging, not this Docker wait.

### Gotcha 7: Thread Safety Inconsistency

[PATTERN] Of 10+ singletons, only 3 have thread-safe initialization: `get_client()` (threading.Lock), `CacheManager` (threading.Lock), `ExperimentCache` (threading.RLock). The remaining 7 (config, database, knowledge graph, world model, vector DB, stage tracker, agent registry) have no synchronization. In concurrent contexts (parallel experiment execution), simultaneous first access could cause race conditions.
# Cross-Cutting Concern: LLM Provider Integration

## Architecture Overview

Kosmos uses a **three-layer LLM abstraction** with a provider pattern, legacy compatibility shim, and a separate async path:

```
kosmos/core/llm.py                    -- Facade: get_client(), ClaudeClient (legacy), get_provider()
kosmos/core/providers/
  base.py                             -- Abstract LLMProvider + LLMResponse + UsageStats + ProviderAPIError
  factory.py                          -- Registry + factory: get_provider(), get_provider_from_config()
  anthropic.py                        -- AnthropicProvider (primary)
  openai.py                           -- OpenAIProvider (OpenAI + compatible endpoints)
  litellm_provider.py                 -- LiteLLMProvider (100+ backends via litellm library)
  __init__.py                         -- Re-exports
kosmos/core/async_llm.py              -- AsyncClaudeClient (Anthropic-only, independent class)
kosmos/core/pricing.py                -- Canonical cost table (MODEL_PRICING dict)
kosmos/core/claude_cache.py           -- Prompt-level response cache (ClaudeCache)
kosmos/config.py                      -- ClaudeConfig, OpenAIConfig, LiteLLMConfig, KosmosConfig.llm_provider
```

## Provider Abstraction

### Base Interface
[FACT] `LLMProvider` (abstract base class) at `kosmos/core/providers/base.py:156` defines the contract all providers implement:

| Method | Signature | Required |
|--------|-----------|----------|
| `generate()` | `(prompt, system, max_tokens, temperature, stop_sequences, **kwargs) -> LLMResponse` | Yes |
| `generate_async()` | Same args, returns coroutine | Yes |
| `generate_with_messages()` | `(messages: List[Message], ...) -> LLMResponse` | Yes |
| `generate_structured()` | `(prompt, schema, ...) -> Dict` | Yes |
| `generate_stream()` | `(prompt, ...) -> Iterator[str]` | No (raises NotImplementedError) |
| `generate_stream_async()` | `(prompt, ...) -> AsyncIterator[str]` | No (raises NotImplementedError) |
| `get_model_info()` | `() -> Dict` | Yes |
| `get_usage_stats()` | `() -> Dict` | No (has default impl) |

### LLMResponse String Compatibility
[FACT] `LLMResponse` at `base.py:58` is a dataclass with `.content: str`, `.usage: UsageStats`, `.model: str`. It implements ~20 string-protocol methods (`strip`, `lower`, `split`, `__contains__`, `__len__`, `__add__`, etc.) so callers that previously received raw `str` from the legacy `ClaudeClient.generate()` continue to work without code changes. This is the bridge between old code returning `str` and new code returning `LLMResponse`.

### Registered Providers

[FACT] `factory.py:188-217` auto-registers providers on import:

| Name | Class | Aliases |
|------|-------|---------|
| `anthropic` | `AnthropicProvider` | `claude` |
| `openai` | `OpenAIProvider` | -- |
| `litellm` | `LiteLLMProvider` | `ollama`, `deepseek`, `lmstudio` |

Registration is try/except guarded: missing SDK packages cause graceful skip, not crash.

## Client Lifecycle (Singleton)

### The get_client() Gateway
[FACT] `kosmos/core/llm.py:613` -- `get_client(reset=False, use_provider_system=True)` is the dominant entry point. It:

1. Returns a module-level singleton `_default_client` (thread-safe via `threading.Lock` with double-checked locking, line 646).
2. When `use_provider_system=True` (default): calls `get_provider_from_config(config)` which reads `KosmosConfig.llm_provider` and dispatches to the appropriate provider class.
3. Fallback chain on error: if config-based init fails, falls back to `AnthropicProvider` with env-var defaults (line 665).
4. When `use_provider_system=False`: creates a legacy `ClaudeClient` instance directly.

Return type is `Union[ClaudeClient, LLMProvider]`. A newer `get_provider()` (line 682) wraps `get_client()` and asserts the return is `LLMProvider`.

### Provider Selection via Config
[FACT] `kosmos/config.py:953` -- `KosmosConfig.llm_provider` is a `Literal["anthropic", "openai", "litellm"]` field, defaulting to `"anthropic"`, set via `LLM_PROVIDER` env var.

[FACT] `factory.py:83-175` -- `get_provider_from_config()` maps config to provider config dict:
- `anthropic`: reads `config.claude` (backward compat) or `config.anthropic`
- `openai`: reads `config.openai`
- `litellm`: reads `config.litellm` or falls back to `LITELLM_*` env vars

## Anthropic Provider (Primary)

[FACT] `AnthropicProvider` at `providers/anthropic.py:36` is the production workhorse. Key behaviors:

### Dual Mode: API vs CLI
- **API mode**: standard `sk-ant-` key, cost tracking enabled.
- **CLI mode**: API key is all 9s (`'999...999'.replace('9','') == ''`), detected at `anthropic.py:110`. Cost returns `$0.00`. Routes through Claude Code CLI proxy.

### Response Caching
- Uses `ClaudeCache` (via `get_claude_cache()` singleton) for content-hash-based caching.
- Cache key: SHA-256 of `{normalized_prompt, model, system, max_tokens, temperature, stop_sequences}`.
- Prompt normalization: whitespace compression, line-ending normalization.
- Bypass patterns: time-sensitive queries, random generation, "latest/newest" (regex-based).
- Cache hits return `LLMResponse` with `metadata={'cache_hit': True}`.
- Similarity-based matching is declared but disabled (`_find_similar_cached` returns `None`, `claude_cache.py:334`).

### Auto Model Selection
- When `enable_auto_model_selection=True`, `ModelComplexity.estimate_complexity()` (at `llm.py:41`) scores prompts 0-100 based on token count and keyword matches against a list of 20 complexity keywords.
- Score < 30 -> Haiku, >= 30 -> Sonnet.
- Only active in API mode (disabled in CLI mode).
- [GOTCHA] Despite the scoring system, the recommendation never returns anything other than "haiku" or "sonnet" -- there is no Opus tier. See `llm.py:88-93`: both `elif` branches return `"sonnet"`.

### Streaming + Event Bus
[FACT] `AnthropicProvider.generate_stream()` at `anthropic.py:665` and `generate_stream_async()` at `anthropic.py:772` emit `LLMEvent` instances to the event bus:
- `LLM_CALL_STARTED` before the API call
- `LLM_TOKEN` for each streamed chunk
- `LLM_CALL_COMPLETED` with total tokens and duration
- `LLM_CALL_FAILED` on error

This provides real-time observability into LLM calls for the monitoring subsystem.

### Async Client
[FACT] `AnthropicProvider` lazy-initializes `AsyncAnthropic` via a `@property` at `anthropic.py:344`. Same API key and base_url as sync client.

## OpenAI Provider

[FACT] `OpenAIProvider` at `providers/openai.py:32` supports:
- **OpenAI official** (`provider_type='openai'`)
- **Ollama/local** (detected via `localhost`/`127.0.0.1` in `base_url`, `provider_type='local'`)
- **OpenRouter** (detected via `openrouter` in URL)
- **Together AI** (detected via `together` in URL)

Key differences from Anthropic provider:
- No response caching (unlike AnthropicProvider).
- Token estimation fallback for local models without usage stats: `len(text) // 4`.
- Cost tracking only for `provider_type='openai'`.
- Hardcoded pricing table duplicated from `pricing.py` in `_calculate_cost()` and `get_model_info()` methods -- does NOT use the canonical `pricing.py` module.
- System prompt sent as first message (OpenAI convention), not as separate parameter.

## LiteLLM Provider

[FACT] `LiteLLMProvider` at `providers/litellm_provider.py:40` wraps the `litellm` library for 100+ backends. Key behaviors:
- Model format detection: `ollama/`, `deepseek/`, `azure/`, or keyword matching (`claude`, `gpt`).
- Uses canonical `pricing.py` via `get_model_cost()` for cost tracking.
- Qwen model workaround: adds "Do not use thinking mode" directive to system prompt and enforces min 8192 max_tokens (`_get_effective_max_tokens`, line 205).
- Simpler JSON parsing in `generate_structured()` -- just `json.loads()` with markdown fence stripping, no retry loop or `parse_json_response` utility.

## Async LLM (Separate Path)

[FACT] `AsyncClaudeClient` at `kosmos/core/async_llm.py:269` is a **standalone class** that does NOT inherit from `LLMProvider`. It wraps `AsyncAnthropic` directly with:
- **Rate limiter**: token-bucket pattern with configurable `max_requests_per_minute` (default 50) and `max_concurrent` (default 5) via semaphore + token bucket.
- **Circuit breaker**: 3-strike threshold, 60s reset timeout, half-open state with 1 test call.
- **Retry logic**: uses `tenacity` (optional) with exponential backoff (2-30s), 3 attempts max.
- **Recoverability classification**: `is_recoverable_error()` at line 141 checks error type and message patterns to decide retry-worthiness.
- **Batch processing**: `batch_generate()` and `concurrent_generate()` use `asyncio.gather()`.

[GOTCHA] `AsyncClaudeClient` is Anthropic-only. There is no async batch path for OpenAI or LiteLLM at this level, though both providers implement `generate_async()` individually.

## Token Management

### Default Models
[FACT] `kosmos/config.py:17-18`:
```python
_DEFAULT_CLAUDE_SONNET_MODEL = "claude-sonnet-4-5"
_DEFAULT_CLAUDE_HAIKU_MODEL = "claude-haiku-4-5"
```

### Default Parameters
- `max_tokens`: 4096 (all providers)
- `temperature`: 0.7 (all providers, except `generate_structured` uses 0.3)
- `timeout`: 120 seconds (Anthropic, OpenAI, LiteLLM)

### Pricing
[FACT] `kosmos/core/pricing.py:14` -- single canonical pricing table:

| Model | Input $/1M | Output $/1M |
|-------|-----------|-------------|
| claude-sonnet-4-5 | 3.00 | 15.00 |
| claude-haiku-4-5 | 1.00 | 5.00 |
| claude-opus-4-5 | 15.00 | 75.00 |
| gpt-4-turbo | 10.00 | 30.00 |
| gpt-4o | 5.00 | 15.00 |
| deepseek/deepseek-chat | 0.14 | 0.28 |
| ollama/* | 0.00 | 0.00 |

Fallback: family-keyword matching (`haiku`/`sonnet`/`opus` in model name).

## Dominant Strategy Across Subsystems

[PATTERN] The dominant pattern (observed in 10+ files) is:
```python
from kosmos.core.llm import get_client
self.llm_client = get_client()
response = self.llm_client.generate(prompt, max_tokens=N)
# or
result = self.llm_client.generate_structured(prompt, schema=schema)
```

Consumers: `hypothesis/testability.py`, `hypothesis/refiner.py`, `hypothesis/prioritizer.py`, `analysis/summarizer.py`, `agents/research_director.py`, `agents/literature_analyzer.py`, `agents/hypothesis_generator.py`, `agents/experiment_designer.py`, `agents/data_analyst.py`.

All use the singleton via `get_client()`. None construct providers directly. The client is treated as opaque -- callers do not check which provider is active.

## Deviations

### 1. Legacy ClaudeClient Still Exists
[FACT] `kosmos/core/llm.py:108` -- The original `ClaudeClient` class coexists with `AnthropicProvider`. It returns raw `str` from `generate()` while `AnthropicProvider` returns `LLMResponse`. The `get_client(use_provider_system=False)` path still creates a `ClaudeClient`. Additionally, `providers/anthropic.py:881` defines `ClaudeClient = AnthropicProvider` as a backward-compat alias, creating a name collision: `llm.ClaudeClient` (the real legacy class) vs `providers.anthropic.ClaudeClient` (the alias for the new provider).

### 2. Direct ClaudeClient Imports
[FACT] Two files bypass `get_client()` and import `ClaudeClient` directly:
- `kosmos/execution/code_generator.py:19` -- `from kosmos.core.llm import ClaudeClient`
- `kosmos/core/domain_router.py:13` -- `from kosmos.core.llm import ClaudeClient`

These import the legacy class, not the provider-system class. They would not benefit from provider switching via `LLM_PROVIDER` config.

### 3. OpenAI Provider Duplicates Pricing
[FACT] `providers/openai.py:575-612` hardcodes its own pricing table in `_calculate_cost()` and `get_model_info()` rather than using the canonical `kosmos/core/pricing.py`. If prices are updated in `pricing.py`, OpenAI costs will be stale.

### 4. LiteLLM Structured Output Lacks Retry
[FACT] `litellm_provider.py:407-468` -- `generate_structured()` uses bare `json.loads()` with markdown fence stripping. It does NOT use the shared `parse_json_response()` utility that Anthropic and OpenAI providers use, and has no retry loop on parse failure.

### 5. AsyncClaudeClient is Anthropic-Only
[FACT] `async_llm.py:269` -- The batch/concurrent async path with circuit breaker and rate limiter only works with Anthropic. Switching `LLM_PROVIDER` to OpenAI or LiteLLM does not give you the same resilience infrastructure for async batch operations.

### 6. No Connection Pooling or Client Reuse Strategy
[ABSENCE] Searched for connection pool, client pool, session reuse patterns. The sync `Anthropic()` and `OpenAI()` clients are created once per singleton lifetime. There is no explicit connection pooling, keep-alive management, or client refresh on token expiry.

## Gotchas for New Contributors

1. **ClaudeClient name collision**: `from kosmos.core.llm import ClaudeClient` gives you the legacy class (returns `str`). `from kosmos.core.providers.anthropic import ClaudeClient` gives you `AnthropicProvider` (returns `LLMResponse`). They have different return types.

2. **CLI mode detection**: The all-9s API key trick (`api_key.replace('9','') == ''`) appears in both `ClaudeClient.__init__` (llm.py:179) and `AnthropicProvider.__init__` (anthropic.py:110). This is a proxy routing convention, not standard Anthropic behavior.

3. **Cache is Anthropic-only**: `ClaudeCache` is only wired into `AnthropicProvider`. OpenAI and LiteLLM providers have no response caching.

4. **generate_structured retry semantics differ**: `ClaudeClient` (legacy) retries the entire API call up to `max_retries` times on JSON parse failure (`llm.py:460`). `AnthropicProvider` does NOT retry (`anthropic.py:547` raises immediately). `LiteLLMProvider` does NOT retry. Behavior depends on which client is active.

5. **LLMResponse vs str**: If you switch from legacy `ClaudeClient` to the provider system, `generate()` returns `LLMResponse` not `str`. Code doing `response.strip()` still works (string compat methods), but `isinstance(response, str)` returns `False`.
# Convention Deviations and Coupling Anomalies

## 1. Coupling Anomalies (from X-Ray co-modification analysis)

### 1.1 config.py <-> core/providers/anthropic.py (Score: 1.0, No Import Relationship)

**Assessment: Intentional indirect coupling**

[FACT] `kosmos/config.py` and `kosmos/core/providers/anthropic.py` are always co-modified (perfect 1.0 co-modification score) but anthropic.py does not import config.py at the top level. Instead:
- `anthropic.py:33` imports `_DEFAULT_CLAUDE_SONNET_MODEL` and `_DEFAULT_CLAUDE_HAIKU_MODEL` from `kosmos.config` (module-level constants, not the config class).
- `anthropic.py:174` and `anthropic.py:410` perform lazy imports of `get_config` inside methods.
- `anthropic.py:88` reads `ANTHROPIC_API_KEY` directly from `os.environ.get()`, bypassing the config singleton.

The coupling is real: any change to Anthropic-related config fields (model names, defaults, API key handling) requires a matching change in the provider. The indirection through lazy imports and env-var fallbacks is intentional for initialization-order safety but makes the dependency invisible to static analysis.

**Verdict**: Intentional. The provider is designed to work even if config is not yet initialized, using lazy imports and env-var fallbacks.

### 1.2 agents/experiment_designer.py <-> agents/research_director.py (Score: 0.8)

**Assessment: Intentional orchestrator-worker coupling**

[FACT] These files share no import relationship. `research_director.py` lazy-imports `ExperimentDesignerAgent` inside `_handle_design_experiment_action()` at line 1465, not at module level. `experiment_designer.py` has no reference to `research_director.py`.

The co-modification reflects the orchestrator-worker pattern: when the experiment design interface changes, the director's delegation code must update. This is architectural coupling, not a code smell.

**Verdict**: Intentional. Direct architectural dependency via the orchestration pattern.

### 1.3 agents/research_director.py <-> execution/code_generator.py (Score: 0.8)

**Assessment: Intentional orchestrator-executor coupling**

[FACT] `research_director.py` lazy-imports `ExperimentCodeGenerator` at line 1528 inside `_handle_execute_experiment_action()`. `code_generator.py` does not reference the director.

Same pattern as 1.2: the director delegates to the code generator, and changes to the generator's interface require updates to the director.

**Verdict**: Intentional.

### 1.4 agents/research_director.py <-> cli/commands/run.py (Score: 0.8)

**Assessment: Intentional entry-point coupling**

[FACT] `cli/commands/run.py:128` imports `ResearchDirectorAgent` to instantiate it from CLI arguments. Changes to the director's constructor signature (`research_question`, `domain`, `agent_id`, `config`) require updates in the CLI command.

**Verdict**: Intentional. CLI is the primary user-facing entry point for the director.

### 1.5 core/providers/anthropic.py <-> core/providers/openai.py (Score: 0.8)

**Assessment: Intentional parallel evolution**

[FACT] These two provider implementations share no import relationship. They both inherit from `LLMProvider` (base.py) and implement the same interface. Co-modification occurs because feature additions (new `generate_*` methods, usage tracking changes) must be applied to both providers simultaneously.

**Verdict**: Intentional. Both implement the same abstract interface and evolve in lockstep.

### 1.6 config.py <-> core/providers/litellm_provider.py (Score: 0.8)

**Assessment: Intentional, same pattern as 1.1**

[FACT] `litellm_provider.py:36` imports `_DEFAULT_CLAUDE_SONNET_MODEL` and `_DEFAULT_CLAUDE_HAIKU_MODEL` from `kosmos.config`. `litellm_provider.py:250` lazy-imports `get_config` inside a method. Changes to LiteLLM config fields in `config.py` require matching changes in the provider.

[FACT] Additionally, `config.py:986-1022` contains `sync_litellm_env_vars`, a special model validator that manually copies `LITELLM_*` env vars into `LiteLLMConfig`. This exists because nested Pydantic sub-configs don't auto-load from the parent's `.env` file. Adding a new `LITELLM_*` field requires updating both `LiteLLMConfig` and the sync validator's `env_map` dict.

**Verdict**: Intentional but fragile. The manual sync mechanism creates a maintenance trap.

---

## 2. Config System Bypass Deviations

### 2.1 monitoring/alerts.py: Complete Config System Bypass (11 env vars)

[FACT] `kosmos/monitoring/alerts.py` reads 11 environment variables via `os.getenv()` at lines 362-549:
- `ALERT_EMAIL_ENABLED` (line 362)
- `ALERT_EMAIL_FROM` (line 371)
- `ALERT_EMAIL_TO` (line 372)
- `SMTP_HOST` (line 390)
- `SMTP_PORT` (line 391)
- `SMTP_USER` (line 392)
- `SMTP_PASSWORD` (line 393)
- `ALERT_SLACK_ENABLED` (line 415)
- `SLACK_WEBHOOK_URL` (line 421)
- `ALERT_PAGERDUTY_ENABLED` (line 483)
- `PAGERDUTY_INTEGRATION_KEY` (line 493)

None of these appear in `KosmosConfig` or any Pydantic model. They are invisible to `kosmos config --validate` and `kosmos config --show`.

**Assessment**: Oversight. The monitoring module was likely added after the config system was established, and the developer did not integrate it. The 11 env vars should have corresponding `MonitoringAlertsConfig` fields.

### 2.2 api/health.py: Parallel Config Reading (6 env vars)

[FACT] `kosmos/api/health.py` reads 6 config values directly from `os.getenv()` at lines 226-338:
- `REDIS_ENABLED` (line 226)
- `REDIS_URL` (line 231)
- `ANTHROPIC_API_KEY` (line 283)
- `NEO4J_URI` (line 336)
- `NEO4J_USER` (line 337)
- `NEO4J_PASSWORD` (line 338)

All 6 have corresponding Pydantic config fields, but the health endpoint reads from environment directly instead of using `get_config()`. This means the health endpoint can report values that differ from the config singleton if env vars and `.env` file diverge.

**Assessment**: Oversight. The health endpoint should use `get_config()` for consistency.

### 2.3 research_director.py: Direct ANTHROPIC_API_KEY for AsyncClaudeClient

[FACT] `kosmos/agents/research_director.py:228` reads `os.getenv("ANTHROPIC_API_KEY")` directly when initializing `AsyncClaudeClient`. This bypasses both the config singleton and the provider selection system. When `LLM_PROVIDER=litellm` or `LLM_PROVIDER=openai`, the async client still attempts to use Anthropic.

**Assessment**: Oversight. The async client should respect `LLM_PROVIDER` selection, but `AsyncClaudeClient` is Anthropic-only (a separate deviation, see 3.5).

### 2.4 agents/skill_loader.py: KOSMOS_SKILLS_DIR Not in Config

[FACT] `kosmos/agents/skill_loader.py:148-149` reads `KOSMOS_SKILLS_DIR` from `os.environ` directly. This env var controls where scientific skill definitions are found but is not modeled in `KosmosConfig`.

**Assessment**: Intentional omission. Skills are a development/deployment concern, not a runtime configuration parameter. Low impact.

### 2.5 execution/executor.py: ENABLE_PROFILING Not in Config

[FACT] `CodeExecutor.__init__()` at `kosmos/execution/executor.py:181-182` accepts `enable_profiling` and `profiling_mode` as constructor parameters. These are documented in `.env.example` (lines 413-421) but have no corresponding Pydantic fields in `config.py`. They must be passed manually by the caller.

**Assessment**: Intentional gap. Profiling is constructor-injected, not config-driven, which is a legitimate design choice for optional debugging features. However, `.env.example` documenting them creates a false expectation that they work as env vars.

### 2.6 factory.py: LiteLLM Env Var Fallback

[FACT] `kosmos/core/providers/factory.py:161-170` has an explicit fallback branch that reads `LITELLM_*` env vars directly via `os.getenv()` when the config's `litellm` attribute is None. This duplicates default values hardcoded in the fallback (`'gpt-3.5-turbo'`, `'4096'`, `'0.7'`, `'120'`) that must stay in sync with `LiteLLMConfig` defaults.

**Assessment**: Intentional defensive coding, but creates a maintenance burden due to duplicated defaults.

---

## 3. Agent Pattern Deviations

### 3.1 Orchestration Agents Do Not Extend BaseAgent

[FACT] Five agents in `kosmos/agents/` extend `BaseAgent`: `ResearchDirectorAgent`, `ExperimentDesignerAgent`, `LiteratureAnalyzerAgent`, `HypothesisGeneratorAgent`, `DataAnalystAgent`.

[FACT] Two "agents" in `kosmos/orchestration/` do NOT extend `BaseAgent`:
- `PlanCreatorAgent` (`orchestration/plan_creator.py:70`) -- plain class
- `PlanReviewerAgent` (`orchestration/plan_reviewer.py:55`) -- plain class

These accept a raw `anthropic_client` in their constructor and manage their own model string, bypassing both the `get_client()` singleton and the `BaseAgent` lifecycle (no `agent_id`, no `status`, no message handling, no event bus integration).

**Assessment**: Intentional variation. These are part of the second research loop (`kosmos/orchestration/` / `kosmos/workflow/research_loop.py`), which was designed independently from the `agents/` subsystem. They are simpler task-specific wrappers, not full lifecycle agents.

### 3.2 Utility Classes Posing as Agents

[PATTERN] Three classes participate in the research loop alongside agents but are plain utility classes (no `BaseAgent` inheritance):
- `HypothesisRefiner` (`kosmos/hypothesis/refiner.py:62`) -- uses `get_client()` correctly
- `ConvergenceDetector` (`kosmos/core/convergence.py:172`) -- pure logic, no LLM
- `ExperimentCodeGenerator` (`kosmos/execution/code_generator.py:731`) -- see deviation 3.3

These are called directly by `ResearchDirectorAgent` via the Issue #76 direct-call pattern. This is intentional: they are stateless utility classes, not stateful agents.

**Assessment**: Intentional. The naming convention inconsistency (no "Agent" suffix) correctly signals their different nature.

### 3.3 ExperimentCodeGenerator Uses Legacy ClaudeClient

[FACT] `kosmos/execution/code_generator.py:19` imports `ClaudeClient` directly from `kosmos.core.llm`, bypassing the provider system. At line 764, it instantiates `ClaudeClient()` directly instead of using `get_client()`.

[FACT] It does have a fallback: if `ClaudeClient()` fails (lines 766-776), it tries `LiteLLMProvider` from `kosmos.core.providers.litellm_provider`. But this fallback creates the provider directly, not via the factory.

This is one of only two files in the codebase that import `ClaudeClient` directly (the other is `core/domain_router.py:13`).

**Assessment**: Oversight / legacy debt. This predates the provider system and was never migrated. It will not respect `LLM_PROVIDER=openai` configuration.

### 3.4 DomainRouter Uses Legacy ClaudeClient

[FACT] `kosmos/core/domain_router.py:13` imports `ClaudeClient` from `kosmos.core.llm`. Like `ExperimentCodeGenerator`, it uses the legacy class directly rather than the provider system.

**Assessment**: Oversight / legacy debt. Same issue as 3.3.

### 3.5 AsyncClaudeClient is Anthropic-Only

[FACT] `kosmos/core/async_llm.py:269` defines `AsyncClaudeClient` as a standalone class wrapping `AsyncAnthropic` directly. It does NOT inherit from `LLMProvider` and does NOT support OpenAI or LiteLLM backends.

When `ENABLE_CONCURRENT_OPERATIONS=True`, the `ResearchDirectorAgent` initializes this client at line 230. If `LLM_PROVIDER` is set to `openai` or `litellm`, the concurrent code path still uses Anthropic.

**Assessment**: Intentional limitation, but poorly documented. The concurrent/batch async path only works with Anthropic. No equivalent exists for other providers.

---

## 4. Name Collisions and Dual Implementations

### 4.1 Two ResearchPlan Classes

[FACT] `kosmos/core/workflow.py:57` defines `class ResearchPlan(BaseModel)` -- a Pydantic model tracking hypothesis pools, experiment queues, and iterations. Used by `ResearchDirectorAgent`.

[FACT] `kosmos/orchestration/plan_creator.py:53` defines `class ResearchPlan` -- a plain dataclass with `cycle`, `tasks`, `rationale`, `exploration_ratio`. Used by `PlanCreatorAgent`.

These are completely different classes with the same name. The first tracks research state; the second is a plan document.

**Assessment**: Oversight. The name collision creates confusion for new contributors. The orchestration version should be renamed (e.g., `CyclePlan` or `TaskPlan`).

### 4.2 Two ResearchWorkflow Classes

[FACT] `kosmos/core/workflow.py:166` defines `class ResearchWorkflow` -- a state machine with `WorkflowState` enum and `ALLOWED_TRANSITIONS`. Used by `ResearchDirectorAgent`.

[FACT] `kosmos/workflow/research_loop.py:30` defines `class ResearchWorkflow` -- an orchestration loop using `PlanCreatorAgent -> PlanReviewerAgent -> DelegationManager`. A completely different architecture.

**Assessment**: Oversight. Two files, two classes, same name, different purposes. This is the "Two Independent Research Loops" issue documented in the agent_communication findings.

### 4.3 ClaudeClient Name Collision

[FACT] `kosmos/core/llm.py:108` defines the original `ClaudeClient` class (returns raw `str` from `generate()`).

[FACT] `kosmos/core/providers/anthropic.py:881` defines `ClaudeClient = AnthropicProvider` as a backward-compat alias (returns `LLMResponse` from `generate()`).

`from kosmos.core.llm import ClaudeClient` gives the legacy class. `from kosmos.core.providers.anthropic import ClaudeClient` gives the new provider. They have different return types.

**Assessment**: Intentional compatibility shim, but a trap for new contributors who import from the wrong location.

---

## 5. LLM Provider Consistency Deviations

### 5.1 OpenAI Provider Duplicates Pricing Table

[FACT] `kosmos/core/providers/openai.py:575-612` hardcodes its own pricing in `_calculate_cost()` with comment "Pricing per million tokens (as of Nov 2024)". Meanwhile, `kosmos/core/pricing.py` has the canonical pricing table (updated "as of February 2026").

The OpenAI provider does NOT import or use `get_model_cost()` from `pricing.py`. This means:
- Prices are stale in the OpenAI provider (Nov 2024 vs Feb 2026)
- Pricing updates in `pricing.py` do not propagate to OpenAI cost calculations

[FACT] By contrast, `LiteLLMProvider` correctly uses `pricing.py` via `get_model_cost()`.

**Assessment**: Oversight. The canonical pricing module exists precisely to prevent this duplication.

### 5.2 LiteLLM generate_structured Lacks Retry and Shared Parser

[FACT] `kosmos/core/providers/litellm_provider.py:407-468` implements `generate_structured()` with bare `json.loads()` and markdown fence stripping. It does NOT use `parse_json_response()` from `kosmos/core/utils/json_parser.py` (which Anthropic and OpenAI providers use), and has no retry loop on parse failure.

**Assessment**: Oversight. The shared `parse_json_response` utility handles edge cases (nested code blocks, partial JSON) that bare `json.loads()` does not.

### 5.3 No Response Caching for OpenAI or LiteLLM

[FACT] `AnthropicProvider` integrates `ClaudeCache` for content-hash-based response caching. Neither `OpenAIProvider` nor `LiteLLMProvider` implements any caching.

**Assessment**: Intentional asymmetry. Caching was built for Anthropic first and never extended. This means switching from Anthropic to OpenAI increases API costs due to cache misses on repeated queries.

---

## 6. Async/Sync Convention Deviations

### 6.1 process_message Sync Override of Async Base Method

[FACT] `BaseAgent.process_message()` is defined as `async def` at `base.py:382`. `ResearchDirectorAgent.process_message()` overrides it as `def` (sync) at `research_director.py:568`.

If `BaseAgent.receive_message()` (which `await`s `process_message()`) is ever called on a `ResearchDirectorAgent`, it would fail because you cannot `await` a non-coroutine.

**Assessment**: Masked bug. Currently harmless because the direct-call pattern (Issue #76) bypasses message passing entirely. If message passing is ever reactivated, this will crash.

### 6.2 Blocking Sleep in Async Context

[FACT] `ResearchDirectorAgent._handle_error_with_recovery()` at line 674 calls `time.sleep(backoff_seconds)`, which blocks the event loop. The method is sync but is called from async `_do_execute_action()`.

**Assessment**: Oversight. Should use `await asyncio.sleep()` in an async context, but the method is currently sync, creating an impedance mismatch.

---

## 7. Dead Code / Unused Infrastructure

### 7.1 Message-Passing System (AgentMessage + AgentRegistry)

[PATTERN] The entire message-passing system exists but is dead code in the main research loop:
- 5 `_send_to_*` async methods in `research_director.py` (lines 1039-1219): ~180 lines
- 6 `_handle_*_response()` methods in `research_director.py` (lines 704-997): ~293 lines
- `AgentRegistry` (`agents/registry.py`): agents are never registered in the main execution flow
- `BaseAgent._async_message_queue`: populated but never drained

Total dead code: ~600+ lines in the research director alone, plus the entire registry infrastructure.

[FACT] `kosmos/agents/registry.py:6-7` explicitly acknowledges this: "Reserved for multi-agent message-passing architecture (future work). Not yet integrated into the main research loop."

**Assessment**: Intentional future-proofing. The dead code is documented but adds significant code mass that misleads new contributors.

### 7.2 iteration_history Never Populated

[FACT] `ResearchDirectorAgent.iteration_history` is declared at line 181 as `List[Dict]` but no method ever appends to it. It is always empty.

**Assessment**: Oversight. Declared but forgotten.

### 7.3 select_next_strategy Never Called by Main Loop

[FACT] `ResearchDirectorAgent.select_next_strategy()` at lines 2792-2816 tracks per-strategy success rates and selects the best strategy. Strategy stats are updated after each action, but `select_next_strategy()` itself is never called by `decide_next_action()`, which uses a deterministic state machine instead.

**Assessment**: Intentional extension point, but the tracking overhead runs without benefit.

---

## 8. Convention Deviation Summary

### Zero TODO/FIXME/HACK/XXX/WORKAROUND Markers

[ABSENCE] Searched all `.py` files under `kosmos/kosmos/` for `# TODO`, `# FIXME`, `# HACK`, `# XXX`, `# WORKAROUND`. Found zero matches. The codebase has no self-documented technical debt markers.

### Type Annotation Convention (class_init_typed_injection)

[PATTERN] 193 classes conform to the `class_init_typed_injection` convention (typed `__init__` parameters). 32+ classes violate it with `untyped_args`, but ALL violations are in `kosmos-claude-scientific-skills/` and `kosmos-reference/` directories (external skill definitions and templates), NOT in the core `kosmos/` package.

**Assessment**: The core package maintains consistent type annotation discipline. The skill/template directories follow a different (looser) convention appropriate for template code.

---

## Assessment Matrix

| # | Deviation | Assessment | Severity |
|---|-----------|------------|----------|
| 2.1 | alerts.py bypasses config (11 vars) | Oversight | Medium |
| 2.2 | health.py reads env directly (6 vars) | Oversight | Low |
| 2.3 | research_director reads API key directly | Oversight | Medium |
| 2.5 | ENABLE_PROFILING not in config | Intentional gap | Low |
| 3.1 | Orchestration agents skip BaseAgent | Intentional | Low |
| 3.3 | code_generator uses legacy ClaudeClient | Legacy debt | Medium |
| 3.4 | domain_router uses legacy ClaudeClient | Legacy debt | Medium |
| 3.5 | AsyncClaudeClient is Anthropic-only | Intentional limit | Medium |
| 4.1 | Two ResearchPlan classes | Oversight | High |
| 4.2 | Two ResearchWorkflow classes | Oversight | High |
| 4.3 | ClaudeClient name collision | Intentional shim | Medium |
| 5.1 | OpenAI duplicates pricing | Oversight | Medium |
| 5.2 | LiteLLM structured output lacks retry | Oversight | Low |
| 6.1 | Sync override of async process_message | Masked bug | Medium |
| 6.2 | Blocking sleep in async context | Oversight | Low |
| 7.1 | ~600 lines dead message-passing code | Intentional future-proofing | Low |
# Dominant Coding Conventions

## 1. Agent Class Pattern

### Structure Convention
[PATTERN: 5/5 agents] All agent classes follow an identical structural template:

```
class XAgent(BaseAgent):
    """Docstring with Capabilities list + Example block."""

    def __init__(self, agent_id=None, agent_type=None, config=None):
        super().__init__(agent_id, agent_type or "XAgent", config)
        # Read config via self.config.get("key", default)
        # Initialize components (LLM client, optional services)
        logger.info(f"Initialized XAgent {self.agent_id}")

    def execute(self, task) -> ...:
        self.status = AgentStatus.WORKING
        try:
            # dispatch on task_type/action
        except Exception as e:
            logger.error(...)
            self.status = AgentStatus.ERROR
        finally:
            self.status = AgentStatus.IDLE

    # Domain-specific public methods (generate_hypotheses, design_experiment, etc.)
    # Private helper methods prefixed with _
```

**Directives:**
- ALWAYS inherit from `BaseAgent` (kosmos/agents/base.py).
- ALWAYS call `super().__init__(agent_id, agent_type or "ClassName", config)` as the first line of `__init__`.
- ALWAYS read agent-specific config from `self.config.get("key", default)` -- the config dict is passed at construction, not from `get_config()`.
- ALWAYS acquire an LLM client via `self.llm_client = get_client()` from `kosmos.core.llm`.
- ALWAYS set `self.status = AgentStatus.WORKING` at the start of `execute()`, and `AgentStatus.IDLE` in the `finally` block.
- ALWAYS log initialization with `logger.info(f"Initialized {self.agent_type} {self.agent_id}")`.
- NEVER access the global `KosmosConfig` directly in agent constructors -- agents receive their config as a plain dict.

**Evidence:**
- [FACT] `HypothesisGeneratorAgent.__init__` (hypothesis_generator.py:62-89): `super().__init__(agent_id, agent_type or "HypothesisGeneratorAgent", config)`, then `self.num_hypotheses = self.config.get("num_hypotheses", 3)`, then `self.llm_client = get_client()`.
- [FACT] `DataAnalystAgent.__init__` (data_analyst.py:127-158): Same pattern, reads 7 config values via `self.config.get()`.
- [FACT] `ExperimentDesignerAgent.__init__` (experiment_designer.py:80-107): Same pattern, reads 5 config values.
- [FACT] `LiteratureAnalyzerAgent.__init__` (literature_analyzer.py:81-136): Same pattern, reads 7 config values, additionally initializes optional subsystems with try/except degradation.
- [FACT] `ResearchDirectorAgent.__init__` (research_director.py:68-260): Same base pattern but with extensive additional setup (DB init, world model, locks, concurrency support).

### Constructor Signature Convention
[PATTERN: 5/5 agents] All agent constructors accept exactly three optional parameters:
```python
def __init__(self, agent_id=None, agent_type=None, config=None)
```
- `agent_id`: UUID string, auto-generated by BaseAgent if None.
- `agent_type`: String label, defaults to class name.
- `config`: Plain dict (NOT a Pydantic model), defaults to empty dict.

### Docstring Convention
[PATTERN: 5/5 agents] All agent class docstrings follow this structure:
1. One-line summary
2. `Capabilities:` section with bullet list
3. `Example:` section with Python code block showing construction and basic usage

### execute() Return Type Deviation
[FACT] The `execute()` method has inconsistent signatures across agents:
- `HypothesisGeneratorAgent.execute()` and `ExperimentDesignerAgent.execute()` take `AgentMessage` and return `AgentMessage` (message-based pattern).
- `DataAnalystAgent.execute()` and `LiteratureAnalyzerAgent.execute()` take `Dict[str, Any]` and return `Dict[str, Any]` (dict-based pattern).
- `ResearchDirectorAgent.execute()` is `async def` and takes `Dict[str, Any]`.
- `BaseAgent.execute()` declares `task: Dict[str, Any]` and raises `NotImplementedError`.

This inconsistency means you cannot polymorphically call `execute()` across all agents with the same argument type. The message-based agents (HypothesisGenerator, ExperimentDesigner) are not called through `execute()` in the main loop anyway -- ResearchDirector calls their domain methods directly.

---

## 2. Config Access Patterns

### Pattern A: Singleton Config via `get_config()` (dominant for infrastructure modules)
[PATTERN: 41 call sites across 32 files] Infrastructure modules call `from kosmos.config import get_config` and access sub-config objects:
```python
from kosmos.config import get_config
config = get_config()
value = config.claude.model  # or config.research.max_iterations, etc.
```

**Directive:** ALWAYS use `get_config()` to access system-wide configuration in infrastructure code (providers, DB, literature clients, safety).

**Evidence:**
- [FACT] `kosmos/literature/unified_search.py:18`: `from kosmos.config import get_config` at module level.
- [FACT] `kosmos/safety/guardrails.py:27`: `from kosmos.config import get_config` at module level.
- [FACT] `kosmos/core/cache_manager.py:15`: `from kosmos.config import get_config` at module level.

### Pattern B: Deferred Config Import (for circular-dependency avoidance)
[PATTERN: 30+ files] Many modules import `get_config()` inside functions rather than at module level to avoid circular imports:
```python
def some_function():
    from kosmos.config import get_config
    config = get_config()
```

**Directive:** When `kosmos.config` would cause a circular import at module level, ALWAYS use deferred (in-function) import.

**Evidence:**
- [FACT] `kosmos/agents/base.py:276,342`: `from kosmos.config import get_config` inside `send_message()` and `receive_message()`, wrapped in try/except.
- [FACT] `kosmos/core/workflow.py:295`: `from kosmos.config import get_config` inside `_save_state()`.
- [FACT] `kosmos/db/__init__.py:151,160`: `from kosmos.config import get_config` inside `init_from_config()` and `get_engine()`.

### Pattern C: Plain Dict Config for Agents
[PATTERN: 5/5 agents] Agents receive config as a plain `Dict[str, Any]`, not via the Pydantic config system:
```python
agent = HypothesisGeneratorAgent(config={"num_hypotheses": 3})
# Inside agent: self.config.get("num_hypotheses", 3)
```

**Directive:** NEVER pass a `KosmosConfig` object directly to an agent constructor. ALWAYS pass a plain dict.

### Pattern D: Direct `os.getenv()` (deviation -- 3 known cases)
[FACT] Three subsystems bypass the config singleton entirely:
1. `kosmos/monitoring/alerts.py:362-549` -- 11 env vars via `os.getenv()` (SMTP, Slack, PagerDuty settings).
2. `kosmos/api/health.py:226-338` -- reads `REDIS_ENABLED`, `ANTHROPIC_API_KEY`, etc. directly.
3. `kosmos/agents/research_director.py:228` -- reads `ANTHROPIC_API_KEY` directly for `AsyncClaudeClient`.

**Directive:** NEVER add new `os.getenv()` calls for settings that belong in `KosmosConfig`. If you must read env vars directly (e.g., in a module that cannot import config), document the deviation.

---

## 3. Logging Convention

### Universal Logger Pattern
[PATTERN: 109/109 modules] Every Python module in `kosmos/` uses:
```python
import logging
logger = logging.getLogger(__name__)
```
This is the single most consistent convention in the codebase. There are zero exceptions.

**Directives:**
- ALWAYS use `import logging` + `logger = logging.getLogger(__name__)` at module level.
- ALWAYS use `logger.info()`, `logger.debug()`, `logger.warning()`, `logger.error()` -- never `print()` for operational output.
- ALWAYS include contextual identifiers in log messages (agent_id, hypothesis_id, experiment_id, etc.).
- NEVER use `kosmos.core.logging.get_logger()` -- despite its existence, all 109 modules use stdlib `logging.getLogger(__name__)` directly.

**Evidence:**
- [FACT] `kosmos/agents/base.py:16,22`: `import logging` + `logger = logging.getLogger(__name__)`.
- [FACT] `kosmos/core/llm.py:18,38`: Same pattern (line numbers from actual grep).
- [FACT] `kosmos/execution/executor.py:17`: Same pattern.
- [ABSENCE] Zero modules use `from kosmos.core.logging import get_logger` in production code.

### Log Level Usage Convention
[PATTERN: observed across 30+ files]
- `logger.info()`: Lifecycle events (agent start/stop), major operation milestones, result summaries.
- `logger.debug()`: Message routing, cache hits, semantic scoring details.
- `logger.warning()`: Degraded operation (optional component unavailable), validation soft failures, skipped items.
- `logger.error()`: Operation failures with `exc_info=True` for stack traces on important failures.

**Evidence:**
- [FACT] `hypothesis_generator.py:89`: `logger.info(f"Initialized HypothesisGeneratorAgent {self.agent_id}")` -- lifecycle.
- [FACT] `hypothesis_generator.py:178`: `logger.info(f"Auto-detected domain: {domain}")` -- milestone.
- [FACT] `hypothesis_generator.py:201`: `logger.warning(f"Hypothesis failed validation: ...")` -- soft failure.
- [FACT] `hypothesis_generator.py:129`: `logger.error(f"Error executing task: {e}", exc_info=True)` -- hard failure with stack.
- [FACT] `literature_analyzer.py:114`: `logger.warning(f"Knowledge graph unavailable: {e}")` -- degraded operation.

### f-string vs % formatting
[PATTERN: ~90% f-strings, ~10% %-style] The codebase predominantly uses f-strings in log messages. Some newer code (e.g., hypothesis_generator.py:218-219) uses %-style (`logger.info("Filtered ...", score, text)`), which is the technically correct approach for deferred formatting. Both styles coexist without enforcement.

---

## 4. Import Patterns

### Pattern 1: Absolute Package Imports (universal)
[PATTERN: all 109+ modules] All imports use absolute paths from the `kosmos` package root:
```python
from kosmos.agents.base import BaseAgent
from kosmos.core.llm import get_client
from kosmos.config import get_config
from kosmos.models.hypothesis import Hypothesis
from kosmos.db import get_session
```

**Directive:** ALWAYS use `from kosmos.X.Y import Z` absolute imports. NEVER use relative imports (`from .base import ...`).

**Evidence:**
- [FACT] `hypothesis_generator.py:14-28`: 7 absolute imports from `kosmos.agents.base`, `kosmos.core.llm`, `kosmos.utils.compat`, `kosmos.core.prompts`, `kosmos.models.hypothesis`, `kosmos.literature.*`, `kosmos.db.*`.
- [FACT] `data_analyst.py:14-17`: 4 absolute imports.
- [FACT] `experiment_designer.py:15-43`: 11 absolute imports.
- [ABSENCE] Zero relative imports found in any `kosmos/` module (searched for `from \.`).

### Pattern 2: stdlib imports first, then kosmos, then conditional
[PATTERN: 5/5 sampled files] Import ordering follows:
1. stdlib (`os`, `logging`, `json`, `uuid`, `time`, `typing`)
2. Third-party (`numpy`, `pydantic`)
3. `kosmos.*` package imports
4. Conditional/lazy imports inside functions

### Pattern 3: Graceful Import Degradation for Optional Dependencies
[PATTERN: 7 files with `_AVAILABLE = False` flags]
```python
try:
    from kosmos.execution.sandbox import DockerSandbox
    SANDBOX_AVAILABLE = True
except ImportError:
    SANDBOX_AVAILABLE = False
    logger.warning("Docker sandbox not available.")
```

Then feature checks happen at initialization, not at call-time.

**Directive:** For optional dependencies (Docker, tenacity, prometheus, R executor, profiling), ALWAYS use the `try/except ImportError` + `*_AVAILABLE` flag pattern. Check availability during `__init__`, not during every method call.

**Evidence:**
- [FACT] `execution/executor.py:24-36`: `SANDBOX_AVAILABLE` and `R_EXECUTOR_AVAILABLE` flags.
- [FACT] `core/async_llm.py:17-44`: `ASYNC_ANTHROPIC_AVAILABLE` and `TENACITY_AVAILABLE` flags.
- [FACT] `core/providers/__init__.py:57-59`: `_LITELLM_AVAILABLE` flag.

### Pattern 4: Lazy Imports to Break Cycles
[PATTERN: 30+ files] Heavy modules use deferred imports inside functions:
```python
def _handle_generate_hypothesis_action(self):
    from kosmos.agents.hypothesis_generator import HypothesisGeneratorAgent
    if self._hypothesis_agent is None:
        self._hypothesis_agent = HypothesisGeneratorAgent(...)
```

**Directive:** When importing a module would create a circular dependency at load time, use deferred (in-function) imports. This is especially common in `research_director.py` (12 deferred imports) and `config.py`.

---

## 5. Singleton / Factory Pattern

### The `get_X()` + `reset_X()` + Module-Level `_x` Convention
[PATTERN: 24 instances] Kosmos has a pervasive singleton pattern for service objects:

```python
_x: Optional[XType] = None

def get_x(reset: bool = False, **kwargs) -> XType:
    global _x
    if _x is None or reset:
        _x = XType(**kwargs)
    return _x

def reset_x():
    global _x
    _x = None
```

**Directives:**
- ALWAYS expose singletons as `get_thing()` functions (never as module-level instances directly).
- ALWAYS provide a `reset_thing()` function for test isolation.
- ALWAYS use the `reset=False` parameter on `get_thing()` for explicit re-creation.
- The conftest.py `reset_singletons` fixture calls all known `reset_*()` functions after each test.

**Evidence (24 singletons):**
| Module | Singleton | get_ | reset_ |
|--------|-----------|------|--------|
| `config.py` | `_config` | `get_config()` | `reset_config()` |
| `core/llm.py` | `_default_client` | `get_client()` | -- |
| `core/event_bus.py` | `_event_bus` | `get_event_bus()` | `reset_event_bus()` |
| `core/experiment_cache.py` | `_experiment_cache` | `get_experiment_cache()` | `reset_experiment_cache()` |
| `core/cache_manager.py` | `_cache_manager` | `get_cache_manager()` | `reset_cache_manager()` |
| `core/stage_tracker.py` | `_stage_tracker` | `get_stage_tracker()` | `reset_stage_tracker()` |
| `core/claude_cache.py` | `_claude_cache` | `get_claude_cache()` | `reset_claude_cache()` |
| `db/__init__.py` | `_engine, _SessionLocal` | `get_session()` | `reset_database()` |
| `agents/registry.py` | `_registry` | `get_registry()` | -- (via `reset=True`) |
| `agents/literature_analyzer.py` | `_literature_analyzer` | `get_literature_analyzer()` | `reset_literature_analyzer()` |
| `world_model/factory.py` | `_world_model` | `get_world_model()` | `reset_world_model()` |
| `knowledge/graph.py` | `_knowledge_graph` | `get_knowledge_graph()` | `reset_knowledge_graph()` |
| `knowledge/vector_db.py` | `_vector_db` | `get_vector_db()` | `reset_vector_db()` |
| `knowledge/embeddings.py` | `_embedder` | `get_embedder()` | `reset_embedder()` |
| `knowledge/concept_extractor.py` | `_concept_extractor` | `get_concept_extractor()` | `reset_concept_extractor()` |
| `knowledge/graph_builder.py` | -- | `get_graph_builder()` | `reset_graph_builder()` |
| `knowledge/graph_visualizer.py` | `_graph_visualizer` | `get_graph_visualizer()` | `reset_graph_visualizer()` |
| `literature/cache.py` | `_cache` | `get_cache()` | `reset_cache()` |
| `literature/pdf_extractor.py` | `_extractor` | `get_pdf_extractor()` | `reset_extractor()` |
| `literature/reference_manager.py` | `_reference_manager` | `get_reference_manager()` | `reset_reference_manager()` |
| `monitoring/metrics.py` | `_metrics_collector` | `get_metrics_collector()` | -- |
| `monitoring/alerts.py` | `_alert_manager` | `get_alert_manager()` | -- |
| `api/health.py` | `_health_checker` | `get_health_checker()` | -- |
| `core/metrics.py` | -- | `get_metrics()` | -- |

**Gotcha:** None of these singletons use thread locks. All are "first call wins" with potential for benign race conditions.

---

## 6. Test Patterns

### Test File Organization
[PATTERN: 3/3 sampled test files] Tests are organized as:
```
tests/
  conftest.py              # Shared fixtures, env loading, singleton reset, markers
  unit/
    agents/                # One file per agent: test_hypothesis_generator.py, etc.
    core/                  # One file per core module: test_llm.py, test_convergence.py
    ...                    # Mirrors kosmos/ package structure
  integration/             # Cross-module scenarios
  e2e/                     # Full workflow tests
```

### Test Class Convention
[PATTERN: 3/3 test files] Tests are grouped into classes by concern:
```python
class TestXInit:
    """Test initialization."""
    def test_init_default(self): ...
    def test_init_with_config(self): ...

class TestXFunctionality:
    """Test main functionality."""
    def test_happy_path(self): ...
    def test_edge_case(self): ...
```

### Module-Level Skip Markers
[PATTERN: 3/3 agent test files] Tests requiring real API calls use module-level `pytestmark`:
```python
pytestmark = [
    pytest.mark.requires_claude,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="Requires ANTHROPIC_API_KEY for real LLM calls"
    )
]
```

**Directives:**
- ALWAYS use `pytest.mark.requires_claude` (or `requires_api_key`, `requires_neo4j`, etc.) for tests needing external services.
- ALWAYS provide a `reason` string in `skipif`.
- Custom markers are registered in `conftest.py:pytest_configure()`.

### Fixture Convention
[PATTERN: 3/3 test files] Agent test files define local fixtures:
```python
@pytest.fixture
def hypothesis_agent():
    """Create agent for testing."""
    return HypothesisGeneratorAgent(config={...})
```
Shared fixtures (mock_llm_client, sample_papers, temp_dir) live in `tests/conftest.py`.

### Mock Strategy
[PATTERN: conftest.py + 3 test files] The test suite uses two approaches:
1. **Real API calls** for agent tests (marked with `requires_claude`).
2. **unittest.mock.Mock/MagicMock** for infrastructure (DB sessions, LLM clients, knowledge graph).

Shared mocks from conftest.py:
- `mock_llm_client`: `Mock()` with `.generate()` and `.generate_structured()` stubs.
- `mock_knowledge_graph`: `Mock()` with `.add_paper()`, `.get_citations()`, etc.
- `mock_vector_db`: `Mock()` with `.search()`, `.add_papers()`.
- `mock_env_vars`: Uses `monkeypatch.setenv()` for env var injection.

**Directive:** ALWAYS use `monkeypatch.setenv()` (not `os.environ` direct mutation) for env var testing.

### Singleton Reset in Tests
[FACT: conftest.py:332-386] An `autouse=True` fixture `reset_singletons` runs after every test. It imports all known `reset_*()` functions and calls them, ensuring no singleton state leaks between tests. If a `reset_*()` import fails, it is silently skipped.

**Directive:** When adding a new singleton module, ALWAYS add its `reset_*()` function to the `reset_singletons` fixture in `tests/conftest.py`.

### Helper Function Convention
[PATTERN: 2/3 test files] Test files define local helper functions for creating test data:
```python
def unique_id() -> str:
    """Generate unique ID for test isolation."""
    return uuid.uuid4().hex[:8]

def make_result(p_value, effect_size, ...) -> ExperimentResult:
    """Helper to create experiment results with specific values."""
```

---

## 7. Data Model Conventions

### Pydantic for Domain Models, Plain Classes for Agent Internals
[PATTERN: models/ vs agents/]
- `kosmos/models/*.py`: All domain models (Hypothesis, ExperimentProtocol, ExperimentResult, etc.) are Pydantic `BaseModel` subclasses with field validators.
- Agent-internal data classes (e.g., `ResultInterpretation` in data_analyst.py) are plain Python classes with `__init__` and `to_dict()`.
- Agent messages (`AgentMessage`, `AgentState`) are Pydantic models in `agents/base.py`.

**Directive:** Use Pydantic `BaseModel` for data that crosses module boundaries (passed between agents, stored in DB, serialized to JSON). Use plain classes for module-internal data structures.

### `to_dict()` Method Convention
[PATTERN: 10+ classes] Both Pydantic and non-Pydantic classes expose a `to_dict()` method for serialization. For Pydantic models, `model_to_dict()` from `kosmos/utils/compat.py` is used for v1/v2 compatibility.

---

## 8. Error Handling Conventions in Agent Code

### Log-and-Return-Default for Non-Critical Operations
[PATTERN: 60+ instances across 30+ files]
```python
try:
    result = self._gather_literature_context(question, domain)
except Exception as e:
    logger.error(f"Error gathering literature: {e}", exc_info=True)
    return []
```

**Directive:** For operations where failure should not halt the research loop (literature search, novelty scoring, caching, optional diagnostics), ALWAYS catch `Exception`, log it, and return an empty/default value.

### Fail-Loud for Safety-Critical Operations
[PATTERN: safety/guardrails.py, oversight/human_review.py]
```python
if self.is_emergency_stop_active():
    raise RuntimeError("Emergency stop active")
```

**Directive:** For safety violations, approval denials, and budget enforcement, ALWAYS raise immediately. NEVER swallow safety exceptions.

---

## 9. Async/Sync Dual-Interface Convention

[PATTERN: agents/base.py, agents/registry.py] The agents subsystem provides both async and sync versions of core methods:
```python
async def send_message(self, ...):    # Primary async method
def send_message_sync(self, ...):     # Backwards-compat wrapper
```
The sync wrapper uses `asyncio.get_running_loop()` + `run_coroutine_threadsafe()` if in async context, or `asyncio.run()` if not.

**Directive:** When adding new async methods to `BaseAgent` or `AgentRegistry`, ALWAYS provide a `_sync` wrapper using the established pattern. In practice, the main research loop uses direct (sync) calls, not message passing.

---

## 10. Notable Deviations from Conventions

1. **ResearchDirectorAgent bypasses agent config pattern for env vars**: [FACT: research_director.py:228] Reads `ANTHROPIC_API_KEY` directly from `os.getenv()` instead of using the config system, for `AsyncClaudeClient` initialization.

2. **CLI has its own logging setup**: [FACT: cli/main.py:49-93] The CLI defines its own `setup_logging()` using `logging.basicConfig()`, completely bypassing `kosmos.core.logging.setup_logging()` and `configure_from_config()`. This means JSON formatters, correlation IDs, and rotating file handlers are not used in CLI-initiated runs.

3. **monitoring/alerts.py bypasses config entirely**: [FACT: alerts.py:362-549] Reads 11 environment variables directly via `os.getenv()` with no Pydantic model.

4. **Inconsistent `execute()` signatures**: As documented in Section 1, agents do not agree on whether `execute()` takes `AgentMessage` or `Dict[str, Any]`.

5. **`ExperimentLogger` and `configure_from_config()` are dead code**: [ABSENCE: confirmed in logging.md] Both are defined in `kosmos/core/logging.py` but have zero callers in production code.

6. **`select_next_strategy()` is wired but never called**: [FACT: research_director.py:2792-2835] Strategy stats are updated but the strategy selection method is never invoked by the main loop.
