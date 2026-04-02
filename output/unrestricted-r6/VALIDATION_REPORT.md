# Validation Report: Kosmos DEEP_ONBOARD.md

> Validated: 2026-03-29
> Document: /tmp/deep_crawl/DEEP_ONBOARD.md (~38,658 tokens)
> Codebase: /mnt/c/python/kosmos (commit 3ff33c3)
> Validator: Phase 5 (VALIDATE)

---

## 5a. Standard Questions Test

### Q1. PURPOSE: What does this codebase do?
**Rating:** YES
**Answer:** Kosmos is an autonomous scientific research platform that orchestrates AI agents to conduct end-to-end research: generating hypotheses, designing experiments, generating and executing code in sandboxes, analyzing results, and iterating through a convergence-driven research loop. It is built on Python with Anthropic/OpenAI LLM providers, Neo4j knowledge graphs, ChromaDB vector storage, and SQLAlchemy persistence.
**Source section:** Identity (line 12)

### Q2. ENTRY: Where does a request/command enter the system?
**Rating:** YES
**Answer:** Primary CLI entry is `kosmos run` via `run_research()` in `kosmos/cli/commands/run.py:51`, which accepts a question, domain, max_iterations, budget, data_path, and streaming flags. Evaluation entries are `scientific_evaluation.py:main()` (7-phase evaluation pipeline) and `run_persona_eval.py:main()` (persona evaluation orchestration). A fourth entry is `compare_runs.py:main()` for regression detection.
**Source section:** Critical Paths (Paths 1, 10, 11, 12)

### Q3. FLOW: What's the critical path from input to output?
**Rating:** YES
**Answer:** CLI `kosmos run` -> `get_config()` -> `ResearchDirectorAgent.__init__()` (initializes LLM client, DB, world model, convergence detector) -> `generate_research_plan()` -> iterative loop: `decide_next_action()` (state machine) -> dispatch to handlers: hypothesis generation -> experiment design -> code execution -> result analysis -> refinement -> convergence check -> results assembly and display. The document traces 13 distinct paths in exhaustive detail with line numbers, branches, side effects, and failure modes.
**Source section:** Critical Paths (Paths 1-13, plus Shared Sub-Paths A and B)

### Q4. HAZARDS: What files should I never read?
**Rating:** YES
**Answer:** The document explicitly lists hazardous files in "Hazards -- Do Not Read" and "Skip" in the Reading Order: `kosmos-reference/` (500K+ token duplicate), generated evaluation reports in `runs/*/tier1/`, `evaluation/run_phase2_tests.py` (hardcodes machine path), `docs/archive/` (outdated), `.env` (contains leaked API key), dead code in `research_director.py:1039-1219`, `LocalModelConfig` (defined but unused), `artifacts.py` vector store Layer 3 (stub), and `*.pyc`/`__pycache__` directories.
**Source section:** Hazards -- Do Not Read, Reading Order (Skip table)

### Q5. ERRORS: What happens when the main operation fails?
**Rating:** YES
**Answer:** The dominant error handling pattern is catch-log-degrade: catch broad `Exception`, log via `logger.error()`, return a degraded result. Five distinct retry implementations exist with exponential backoff (code execution, task delegation, LLM API with circuit breaker, JSON parse retry, and research director error recovery with [2,4,8] second backoff and 3-error circuit breaker). `ProviderAPIError.is_recoverable()` is the central oracle for retry decisions. Errors do NOT propagate as exceptions -- they are converted to return values at each boundary. No centralized exception handler exists.
**Source section:** Error Handling Strategy, Gotchas (items 11, 13, 20, 44, 59, 60)

### Q6. EXTERNAL: What external systems does this talk to?
**Rating:** YES
**Answer:** Anthropic Claude API (primary LLM), OpenAI API (alternative provider), LiteLLM (multi-provider adapter), arXiv API, Semantic Scholar API, PubMed API (literature search), Neo4j (knowledge graph), ChromaDB (vector storage), SQLAlchemy/SQLite (persistence), Docker (code sandbox), Redis (optional cache), SMTP/Slack/PagerDuty (optional alerting). SPECTER model (~440MB) for paper embeddings.
**Source section:** Identity, Configuration Surface (LLM Provider, Literature API, Neo4j, Vector DB, Redis sections), Terminal Side Effects Summary

### Q7. STATE: What shared state exists that could cause bugs?
**Rating:** YES
**Answer:** The document catalogs 15+ module-level singletons (LLM client, DB engine, config, knowledge graph, world model, vector DB, event bus, experiment cache, cache manager, stage tracker, metrics collector, alert manager, agent registry, literature analyzer, reference manager, template registry). Key risks: `_default_client` can be either `ClaudeClient` or `LLMProvider` (two incompatible types), world model factory is NOT thread-safe, `_engine` is the only singleton that refuses lazy-init (raises RuntimeError), ResearchDirectorAgent has 7+ mutable state fields including workflow, research plan, lazy agent slots, error counters, and dual locking without mutual exclusion between async and sync paths.
**Source section:** Shared State (all subsections: Module-Level Singletons, ResearchDirectorAgent In-Memory State, BaseAgent In-Memory State, LLM Client Internal State, Executor/Validator State, NoveltyDetector, Database Singletons, Provider Registration, Dual Model System, Initialization DAG)

### Q8. TESTING: What are the testing conventions?
**Rating:** YES
**Answer:** Tests mirror source package structure under `tests/unit/`. Files named `test_{source_module}.py`. Tests grouped into `Test{Concern}` classes with docstrings. Markers: `@pytest.mark.unit`, `integration`, `e2e`, `slow`, `smoke`, `requires_api_key`, `requires_neo4j`, `requires_chromadb`, `requires_claude`. Uses `unittest.mock.Mock` (never third-party), `AsyncMock` for async methods. Singleton reset via `reset_singletons` autouse fixture. `store_in_db=False` for DB-independent tests. Key pytest.ini settings: `asyncio_mode=auto`, `--cov-fail-under=80`, `--strict-markers`, `timeout=300`.
**Source section:** Conventions (Testing Conventions, items 17-24)

### Q9. GOTCHAS: What are the 3 most counterintuitive things?
**Rating:** YES
**Answer:** The document lists 105 numbered gotchas. Top 3 most counterintuitive: (1) Sandbox return value silently lost -- DockerSandbox extracts results via "RESULT:" prefix in stdout, but all code templates store in a `results` local variable; sandbox path returns None, losing all data. (2) Auto-fix inserts forbidden imports -- `RetryStrategy.COMMON_IMPORTS` includes `os`, but `os` is on the DANGEROUS_MODULES list; auto-fix for NameError can insert an import the validator rejects. (3) LLM enhancement is a no-op -- `_enhance_protocol_with_llm()` calls the LLM but never applies the response; logs "enhancements applied" while burning API tokens for nothing.
**Source section:** Gotchas (items 1, 8, 14, plus 102 more)

### Q10. EXTENSION: If I need to add a new [primary entity], where do I start?
**Rating:** YES
**Answer:** The Extension Points section provides 8 task-specific guides with "Start Here", "Also Touch", and "Watch Out" columns for: adding a new agent, LLM provider, experiment type/code template, CLI command, research domain, knowledge storage backend, literature source, and database model. Each includes specific file paths, line numbers, and cross-references to relevant gotchas.
**Source section:** Extension Points (8-row table)

---

## 5a-bis. Coverage Breadth Test

| Metric | Target | Actual | Notes |
|--------|--------|--------|-------|
| Subsystems with >= 1 documented module | 100% | 16/22 (73%) | **BELOW TARGET.** Missing subsystems: `analysis`, `compression`, `hypothesis`, `oversight`, `utils`, `validation`. The `hypothesis` subsystem is partially covered via `hypothesis_generator.py` references in Critical Paths but has no Module Index entry for `kosmos/hypothesis/novelty_checker.py` itself. `analysis`, `compression`, `oversight`, `utils`, and `validation` are mentioned in the Gaps section but have zero module-level documentation. |
| Xray pillars in Module Index | 100% | 8/8 (100%) | All 8 pillar modules from the crawl plan (T3.1-T3.8) are present in the Module Behavioral Index: `logging.py`, `hypothesis.py`, `base_client.py`, `experiment.py`, `llm.py`, `result.py`, `workflow.py`, `research_director.py`. |
| Entry points with traces | 100% | 5/5 (100%) | All 5 crawl plan entry points (T1.1-T1.5) are traced: CLI run (Path 1), scientific evaluation (Path 10), persona evaluation (Path 11), hypothesis generation (Path 3), code generation/execution (Path 5). Additionally, 8 more paths are traced beyond the plan requirements. |
| Cross-cutting concerns from crawl plan | 100% | 6/6 (100%) | All 6 concerns covered: Error handling (dedicated section), Configuration surface (dedicated section, ~105 env vars), LLM provider abstraction (Key Interfaces, Convention 12-14), Agent communication (Key Interfaces, Communication Architecture Summary), Database/storage patterns (Shared State, Dual Model System section), Environment dependencies (Configuration Surface, Minimum Viable Environment). |
| Module Index entries vs core files | >= 25% | 19/119 (16%) | **BELOW TARGET.** The Module Behavioral Index documents 19 distinct modules out of ~119 core Python files. This is 16%, below the 25% target. However, the Critical Paths section references many additional modules not in the Index (e.g., `data_analyst.py`, `hypothesis_generator.py`, `experiment_designer.py`, `novelty_checker.py`, `unified_search.py`, `sandbox.py`, `config.py`), which partially compensates. |

**Gaps identified:**
1. Six subsystems (`analysis`, `compression`, `hypothesis`, `oversight`, `utils`, `validation`) have no module-level documentation.
2. Module Index coverage is at 16% vs 25% target. Adding entries for `config.py`, `hypothesis_generator.py`, `data_analyst.py`, and `experiment_designer.py` would close the gap.

---

## 5b. Spot-Check Verification

### Spot Check 1
**Claim:** "random_seed=0 silently replaced with 42 -- `getattr(protocol, 'random_seed', 42) or 42`. Zero is falsy" (`code_generator.py:89`)
**Actual code:** Line 89 reads `seed = getattr(protocol, 'random_seed', 42) or 42`. The `or 42` clause means that if `random_seed` is 0 (falsy), it becomes 42.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 2
**Claim:** "`if False: yield` in `generate_stream_async` is load-bearing dead code... removing it changes function from async generator to coroutine" (`base.py:360-363`)
**Actual code:** Lines 360-363 read: `raise NotImplementedError(...)` followed by `if False: yield`. Without the `yield`, Python would not treat the function as an async generator, breaking `async for` callers.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 3
**Claim:** "MAX_CONSECUTIVE_ERRORS = 3 with exponential backoff [2, 4, 8] seconds" (`research_director.py:44-46`)
**Actual code:** Lines 44-46 read: `MAX_CONSECUTIVE_ERRORS = 3`, `ERROR_BACKOFF_SECONDS = [2, 4, 8]`.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 4
**Claim:** "`_update_usage_stats` skips `cost_usd=0.0`: Falsy check means free-tier costs not accumulated" (`providers/base.py:401`)
**Actual code:** Line 401 reads: `if usage.cost_usd:` followed by `self.total_cost_usd += usage.cost_usd`. Since `0.0` is falsy in Python, a cost of exactly zero is skipped.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 5
**Claim:** "CLI mode detection: `self.api_key.replace('9', '') == ''` -- silently changes cost tracking" (`llm.py:179`)
**Actual code:** Line 179 reads: `self.is_cli_mode = self.api_key.replace('9', '') == ''`.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 6
**Claim:** "Cost estimation hardcodes model name: Uses `'claude-sonnet-4-5'` regardless of actual model" (`llm.py:519`)
**Actual code:** Line 519 reads: `cost_saved = get_model_cost("claude-sonnet-4-5", int(avg_input_tokens * self.cache_hits), int(avg_output_tokens * self.cache_hits))`. This hardcodes the model name.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 7
**Claim:** "CONVERGED is not terminal -- `CONVERGED -> GENERATING_HYPOTHESES` allowed" (`workflow.py:212-213`)
**Actual code:** Lines 211-212 read: `WorkflowState.CONVERGED: [WorkflowState.GENERATING_HYPOTHESES,  # Restart if new question]`.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 8
**Claim:** "`_actions_this_iteration` uses hasattr check for lazy initialization. Not initialized in __init__" (`research_director.py:2451-2453`)
**Actual code:** Lines 2451-2453 read: `if not hasattr(self, '_actions_this_iteration'): self._actions_this_iteration = 0` followed by `self._actions_this_iteration += 1`.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 9
**Claim:** "Vague language check ('maybe', 'might', etc.) warns but does NOT reject" (`hypothesis_generator.py:451-455`)
**Actual code:** Lines 450-455 read: `vague_words = ["maybe", "might", "perhaps", "possibly", "potentially", "somewhat"]`, followed by `if any(word in hypothesis.statement.lower() for word in vague_words): logger.warning(...)` then `# Don't fail, but warn` followed by `pass`, then `return True`.
**Verdict:** CONFIRMED
**Action:** none

### Spot Check 10
**Claim:** "`reset_database()` does `Base.metadata.drop_all()`. If evaluation DB is shared with production data, this destroys everything" (`db/__init__.py:200-201`)
**Actual code:** Lines 200-201 read: `Base.metadata.drop_all(bind=_engine)` followed by `Base.metadata.create_all(bind=_engine)`.
**Verdict:** CONFIRMED
**Action:** none

**Spot Check Summary:** 10/10 CONFIRMED. Zero inaccurate or stale claims found.

---

## 5c. Redundancy Check

### Section-by-Section Analysis

| Section | Redundancy Found? | Details |
|---------|-------------------|---------|
| Identity | No | Unique overview paragraph. Not duplicated elsewhere. |
| Critical Paths | No | Unique trace content. Shared Sub-Paths A and B are documented once and referenced from multiple paths -- this is efficient deduplication, not redundancy. |
| Module Behavioral Index | Partial | The summary table (lines 849-869) and the detailed descriptions (lines 873+) cover the same modules. However, the table provides a scannable overview while the descriptions provide depth -- this is intentional layered access, not literal duplication. |
| Key Interfaces | Partial | Method signatures overlap with Module Behavioral Index "Public API" subsections. However, the Key Interfaces section consolidates signatures into code blocks for quick reference, while the Module Index embeds them in behavioral context. The two serve different retrieval purposes (code reference vs. behavioral understanding). This is synthesis, not redundancy per the validation instructions. |
| Error Handling Strategy | No | Unique analysis of error patterns, retry strategies, and exception hierarchy. References to specific modules are contextual, not copied. |
| Shared State | No | Unique catalog of mutable state. Not duplicated from other sections. |
| Domain Glossary | Minimal | Some definitions overlap with Module Index descriptions (e.g., `LLMResponse` described in both base.py module entry and glossary). However, the glossary provides a flat lookup table while the Module Index embeds terms in behavioral context. Per validation instructions, this cross-referencing synthesis is the document's value, not redundancy. |
| Configuration Surface | No | Unique content. Not duplicated. |
| Conventions | No | Unique prescriptive content. |
| Gotchas | Partial | Some gotchas are also mentioned in Critical Paths or Module Index (e.g., Gotcha 1 about sandbox return value is also discussed in Critical Path 5). However, these are different treatments: Critical Paths describe the flow, Gotchas provide a flat list for scanning. The document intentionally cross-references with "(See Critical Path 5...)" to connect them without duplicating the full trace. |
| Hazards | No | Unique content. Some items overlap with Gotchas (e.g., leaked API key) but the Hazards section provides a distinct "do not read" directive format. |
| Extension Points | No | Unique prescriptive content. |
| Reading Order | No | Unique prescriptive content. |
| Gaps | No | Unique self-assessment. |

**Conclusion:** No content is literally duplicated between sections. Intentional cross-referencing and multi-perspective coverage (same module discussed in trace, module index, interfaces, and gotchas for different purposes) is present and valuable.

---

## 5d. Adversarial Simulation

**Domain task:** Add a new agent type with custom behavior

### Implementation Plan (derived solely from DEEP_ONBOARD.md)

**Step 1:** Create a new agent file `kosmos/agents/my_new_agent.py`. Subclass `BaseAgent` from `kosmos/agents/base.py`. Accept `(agent_id, agent_type, config)` in `__init__`, call `super().__init__()` passing these parameters. Extract config values via `self.config.get(key, default)` rather than requiring typed constructor params. (Source: Extension Points row 1, Convention 7)

**Step 2:** Implement `execute(self, task: Dict[str, Any]) -> Dict[str, Any]` following the dict-based signature (matching `DataAnalystAgent` and `LiteratureAnalyzerAgent`, not the `AgentMessage`-based variant). Set `self.status = AgentStatus.WORKING` at the start, set `self.status = AgentStatus.IDLE` in the `finally` block. Dispatch on `task.get("action")` or `task.get("task_type")`. Catch exceptions, log them, increment `self.errors_encountered`, and return an error dict rather than raising. (Source: Convention 7, Convention 8, Extension Points "Watch Out")

**Step 3:** Obtain LLM client via `from kosmos.core.llm import get_client; self.llm_client = get_client()` in `__init__`. Wrap optional dependencies in try/except to degrade gracefully. Never directly instantiate provider classes. (Source: Convention 12, Convention 15)

**Step 4:** Register the new agent in `kosmos/agents/research_director.py`: add a lazy-init slot (e.g., `self._my_new_agent = None`) following the pattern at lines 144-152. Add a new `_handle_my_new_action()` method following the direct-call pattern used by `_handle_generate_hypothesis_action()` et al. (lines 1391-1979). Do NOT use message-based `_send_to_*` methods (dead code per Issue #76). Also register in `kosmos/orchestration/delegation.py` agents dict if the agent should participate in plan execution. (Source: Extension Points row 1 "Also Touch", Communication Architecture Summary)

**Step 5:** Add unit tests in `tests/unit/agents/test_my_new_agent.py`. Mirror source structure. Use `@pytest.mark.unit` marker. Use `Mock()` from `unittest.mock` for dependencies. Use `store_in_db=False` where applicable. Reset singletons via the autouse `reset_singletons` fixture. (Source: Conventions 17-24)

### Verification Against Actual Codebase

**Step 1 verification:** Read `kosmos/agents/base.py:113-126` -- confirmed `BaseAgent.__init__` accepts `(agent_id, agent_type, config)` with the exact signature described. The document's guidance is correct.
**Rating:** CORRECT

**Step 2 verification:** Read `kosmos/agents/data_analyst.py:160-175` -- confirmed `execute(self, task: Dict[str, Any]) -> Dict[str, Any]` with `self.status = AgentStatus.WORKING` at start, dispatch on `task.get("action")`, try/except pattern. The document's guidance matches exactly.
**Rating:** CORRECT

**Step 3 verification:** The `get_client()` pattern is confirmed in the source. All 5 active agents use this pattern. The document correctly warns against direct instantiation (with documented violations for domain_router, code_generator, and research_director async client).
**Rating:** CORRECT

**Step 4 verification:** Read `kosmos/agents/research_director.py:144-152` -- confirmed lazy-init slots with `self._hypothesis_agent = None` etc. The `_handle_*_action()` methods at lines 1391-1979 follow the exact pattern described. The document's guidance about avoiding `_send_to_*` methods is correct (confirmed dead code at lines 1039-1219).
**Rating:** CORRECT

**Step 5 verification:** The testing conventions described in the document match the actual test structure at `/mnt/c/python/kosmos/tests/unit/agents/`. The markers and patterns described are accurate.
**Rating:** CORRECT

**Score:** **PASS (5/5 correct)**

---

## 5e. Caching Structure Verification

### Section Order Analysis

| Position | Section | Stability |
|----------|---------|-----------|
| 1 | Identity | STABLE -- rarely changes |
| 2 | Critical Paths | STABLE -- changes only with architectural changes |
| 3 | Module Behavioral Index | STABLE -- changes with module refactoring |
| 4 | Key Interfaces | STABLE -- changes with API changes |
| 5 | Error Handling Strategy | SEMI-STABLE -- changes with error pattern changes |
| 6 | Shared State | SEMI-STABLE -- changes with new singletons |
| 7 | Domain Glossary | STABLE -- changes with new concepts |
| 8 | Configuration Surface | SEMI-STABLE -- changes with new config |
| 9 | Conventions | STABLE -- rarely changes |
| 10 | Gotchas | VOLATILE -- grows with discoveries |
| 11 | Hazards | VOLATILE -- changes with new hazards |
| 12 | Extension Points | SEMI-STABLE -- changes with new extension types |
| 13 | Reading Order | STABLE -- rarely changes |
| 14 | Gaps | VOLATILE -- changes with investigation progress |

**Assessment:** PASS. Stable sections (Identity, Critical Paths, Module Index, Key Interfaces) are positioned first, before volatile sections (Gotchas, Hazards, Gaps). This ordering maximizes prompt cache prefix hits because the stable prefix will remain unchanged across document updates while the volatile tail changes.

---

## Summary

| Check | Result |
|-------|--------|
| Standard Questions (10) | 10/10 YES |
| Coverage: Subsystems documented | 16/22 (73%) -- BELOW 100% target |
| Coverage: Xray pillars | 8/8 (100%) |
| Coverage: Entry points traced | 5/5 (100%) |
| Coverage: Cross-cutting concerns | 6/6 (100%) |
| Coverage: Module Index vs core files | 19/119 (16%) -- BELOW 25% target |
| Spot Checks (10) | 10/10 CONFIRMED |
| Redundancy | No literal duplication found |
| Adversarial Simulation | PASS (5/5 correct) |
| Caching Structure | PASS (stable before volatile) |

### Overall Gaps

1. **Subsystem coverage gap:** Six subsystems (`analysis`, `compression`, `hypothesis`, `oversight`, `utils`, `validation`) lack module-level documentation. The `analysis` subsystem contains `statistics.py`, `summarizer.py`, and `visualization.py`; `oversight` contains human oversight mechanisms; `validation` contains scholarly evaluation and null model checking. These are noted in the Gaps section of the document itself.

2. **Module Index density gap:** 19 modules documented vs 119 core files (16%). Adding 11 more module entries (particularly `config.py`, `hypothesis_generator.py`, `data_analyst.py`, `experiment_designer.py`, `novelty_checker.py`, `hypothesis/refiner.py`, `unified_search.py`, `sandbox.py`, `db/operations.py`, `db/models.py`, `analysis/statistics.py`) would bring coverage to the 25% target.

3. **No inaccurate claims found.** All 10 spot-checked [FACT] claims were confirmed against the actual codebase. The document is factually reliable.

4. **Document is highly effective for onboarding.** All 10 standard questions are fully answerable. The adversarial simulation scored 5/5 -- an agent could implement a new agent type using only this document's guidance and produce correct code.
