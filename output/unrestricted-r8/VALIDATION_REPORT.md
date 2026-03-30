# DEEP_ONBOARD.md Validation Report

> Codebase: Kosmos at /mnt/c/python/Kosmos
> Document: /tmp/deep_crawl/DEEP_ONBOARD.md (5,746 lines, ~61,869 words)
> Validated: 2026-03-29
> Validator: Phase 5 (VALIDATE)

---

## 5a. Standard Questions Test

### Q1. PURPOSE: What does this codebase do?
**Rating:** YES
**Answer:** Kosmos is an agent-based scientific research platform combining autonomous AI agents, workflow orchestration, and CLI tooling. It orchestrates multi-stage research workflows where AI agents generate hypotheses, design experiments, execute code in sandboxes, and evaluate results for scientific novelty and convergence.
**Source section:** Identity (lines 10-12)

### Q2. ENTRY: Where does a request/command enter the system?
**Rating:** YES
**Answer:** The primary entry point is the `kosmos run` CLI command at `kosmos/cli/commands/run.py:51` (the `run_research()` Typer function). Additional entry points include `scientific_evaluation.py:main()` (7-phase evaluation harness), `run_persona_eval.py:main()` (persona evaluation), and `compare_runs.py:main()` (run comparison). All are traced in detail with exact line references.
**Source section:** Critical Paths (Path 1 line 21, Path 2 line 326, Path 3 line 517, also Reading Order item 27)

### Q3. FLOW: What's the critical path from input to output?
**Rating:** YES
**Answer:** CLI args -> flat_config dict -> ResearchDirectorAgent(question, domain, config) -> state machine loop: decide_next_action() dispatches to handlers (GENERATE_HYPOTHESIS -> DESIGN_EXPERIMENT -> EXECUTE_EXPERIMENT -> ANALYZE_RESULT -> REFINE_HYPOTHESIS -> CONVERGE). Each handler orchestrates a specialized agent, writes to DB and Neo4j, and transitions the workflow state. Post-loop: DB read -> Rich display -> optional file export. The full data flow diagram is provided in the document.
**Source section:** Critical Paths Path 1 (lines 17-317), especially the Data Flow Diagram (lines 293-315)

### Q4. HAZARDS: What files should I never read?
**Rating:** YES
**Answer:** The Hazards section explicitly lists 14 patterns/files to avoid with token counts and reasons: `kosmos/agents/registry.py` (dead code), `research_director.py:1039-1219` (dead message-based methods), `core/memory.py` and `core/feedback.py` (Phase 7 unintegrated infrastructure), `config.py:752-822` (dead LocalModelConfig), `agents/base.py:406-415` (dead message handler registration), `compare_runs.py` (self-contained utility), `run_phase2_tests.py` (machine-specific), `experiment_designer.py:714-717` (no-op LLM enhancement), `openai.py:575-613` (duplicate pricing). The Reading Order section also includes explicit "Skip" entries for each of these.
**Source section:** Hazards -- Do Not Read (lines 5600-5617), Reading Order Skip entries (lines 5717-5731)

### Q5. ERRORS: What happens when the main operation fails?
**Rating:** YES
**Answer:** The dominant pattern is Catch-Log-Degrade (364 `except Exception as e:` sites across 102 files). ResearchDirectorAgent has error recovery with `MAX_CONSECUTIVE_ERRORS=3`, exponential backoff `[2, 4, 8]` seconds, and forced CONVERGE on repeated failures. Individual handler failures invoke `_handle_error_with_recovery()` which logs, increments the counter, and either retries from GENERATING_HYPOTHESES or forces convergence. Per-item error handling in loops prevents one bad item from crashing a batch. Code execution has self-correcting retry (up to 3 retries with code modification). DB session auto-rollbacks on exception. The document includes a full Error Architecture Diagram and per-module error deep dives for 8 modules.
**Source section:** Error Handling section (lines 3381-3727), particularly sections 2a (research director), 3a (code execution retry), 3e (research director error recovery)

### Q6. EXTERNAL: What external systems does this talk to?
**Rating:** YES
**Answer:** Anthropic Claude API (primary LLM), OpenAI API (alternative LLM), Google/LiteLLM (alternative providers), arXiv API (paper search), Semantic Scholar API (paper search + citations), PubMed API (paper search), SQLAlchemy/SQLite (primary DB), Neo4j (knowledge graph), ChromaDB (vector store for semantic search), SPECTER model (paper embeddings, ~440MB download), Docker (sandbox code execution), Redis (optional cache). The Configuration Surface section documents 60+ environment variables for these systems. A comprehensive environment variable inventory is provided.
**Source section:** Critical Path 4 External Dependencies table (lines 1022-1032), Configuration Surface (lines 4261-4831), Shared State Index (lines 3727-3756)

### Q7. STATE: What shared state exists that could cause bugs?
**Rating:** YES
**Answer:** 24 shared state items are documented with location, mutation, thread-safety analysis, and risk level. Key items: LLM Client Singleton (type ambiguity: ClaudeClient OR LLMProvider), Config Singleton (CLI mutates global state), DB Engine/Session Factory (hard failure if not initialized), World Model Singleton (NOT thread-safe, falls back to InMemoryWorldModel silently), ResearchPlan (can diverge from workflow.current_state), _actions_this_iteration (lazily initialized via hasattr). The Concurrency Model section details dual async/threading lock strategies and their risks.
**Source section:** Shared State Index (lines 3727-3756), Full Shared State Descriptions (lines 3759-4095), Concurrency Model (lines 4146-4156)

### Q8. TESTING: What are the testing conventions?
**Rating:** PARTIAL
**Answer:** Test structure mirrors source packages under `tests/unit/`. Files named `test_{module}.py`. Tests grouped into classes with `Test{Concern}` names and docstrings. Markers: `unit`, `integration`, `e2e`, `slow`, `smoke`, `requires_api_key`, `requires_neo4j`, `requires_chromadb`, `requires_claude`. Fixtures follow a layered pattern (session-scoped for immutable data, function-scoped for mutable, autouse for singleton resets). Two mocking approaches coexist: real Claude API calls for LLM tests, mocked dependencies for isolation. pytest.ini enforces 80% branch coverage, 300s timeout, strict markers. However, the document self-identifies testing conventions as a gap: "Testing conventions not deeply investigated -- T5.3 produced limited findings on fixture patterns and mocking strategies."
**Source section:** Conventions sections 14-20 (lines 5020-5151), Gaps section (line 5734)

### Q9. GOTCHAS: What are the 3 most counterintuitive things?
**Rating:** YES
**Answer:** The document provides 93+ numbered gotchas organized by severity. The top 3 most counterintuitive: (1) `_reset_eval_state()` drops ALL database tables before each evaluation phase -- if the evaluation DB is shared with production, this destroys everything (Gotcha #1). (2) Sandbox return value loss -- DockerSandbox extracts return values via stdout "RESULT:" prefix but generated code stores results in a local variable; the non-sandbox path works correctly but the sandbox path silently loses result data (Gotcha #5). (3) Message routing is dead code at runtime -- the entire AgentRegistry/message bus infrastructure was replaced by direct calls per Issue #76 but the dead code remains (Gotcha #11-14). Additional highly counterintuitive: `random_seed=0` silently becomes 42, LLM enhancement is a no-op that wastes API cost, CONVERGED is not a terminal state.
**Source section:** Gotchas section (lines 5216-5598), particularly Critical Severity (lines 5221-5242) and High Severity (lines 5243-5294)

### Q10. EXTENSION: If I need to add a new agent type, where do I start?
**Rating:** YES
**Answer:** Start at `kosmos/agents/base.py` (BaseAgent ABC). The Extension Points table says also touch `kosmos/agents/__init__.py` and `cli/commands/run.py` (flat_config dict). Watch out for: two existing agents have `execute()` signatures incompatible with the base class (AgentMessage instead of Dict); `_on_pause()`/`_on_resume()` hooks are dead code; `message_queue` grows without bound; `start()` cannot restart from ERROR state; `register_message_handler()` stores handlers but `process_message()` does NOT dispatch to them. The Conventions sections 7-13 detail the full BaseAgent subclassing contract, execute() method contract, lifecycle hooks, component initialization patterns, agent naming, LLM client access, and config access patterns.
**Source section:** Extension Points table (lines 5618-5636), Conventions sections 7-13 (lines 4937-5018)

---

## 5b. Spot-Check Verification

### Spot Check 1
**Claim:** "random_seed=0 silently replaced with 42 -- Due to `or 42` pattern, zero is a valid seed but treated as falsy." (code_generator.py:89)
**Actual code:** Line 89: `seed = getattr(protocol, 'random_seed', 42) or 42`
**Verdict:** CONFIRMED -- The `or 42` pattern means any falsy value (0, None, False, empty string) gets replaced with 42. A `random_seed=0` is a valid seed but would become 42.

### Spot Check 2
**Claim:** "MAX_CONSECUTIVE_ERRORS = 3 with exponential backoff [2, 4, 8] seconds." (research_director.py:44-46)
**Actual code:** Lines 44-46: `MAX_CONSECUTIVE_ERRORS = 3` and `ERROR_BACKOFF_SECONDS = [2, 4, 8]`
**Verdict:** CONFIRMED -- Exact match.

### Spot Check 3
**Claim:** "5 templates registered in priority order (code_generator.py:787-793): TTestComparisonCodeTemplate, CorrelationAnalysisCodeTemplate, LogLogScalingCodeTemplate, MLExperimentCodeTemplate, GenericComputationalCodeTemplate." (code_generator.py:787-793)
**Actual code:** Lines 787-793: `self.templates = [TTestComparisonCodeTemplate(), CorrelationAnalysisCodeTemplate(), LogLogScalingCodeTemplate(), MLExperimentCodeTemplate(), GenericComputationalCodeTemplate()]`
**Verdict:** CONFIRMED -- Order and classes match exactly.

### Spot Check 4
**Claim:** "Vague language check is warn-only -- `_validate_hypothesis()` detects vague words like 'maybe', 'might' but does NOT reject the hypothesis. Comment explicitly says 'Don't fail, but warn.'" (hypothesis_generator.py:451-455)
**Actual code:** Lines 450-455: `vague_words = ["maybe", "might", "perhaps", "possibly", "potentially", "somewhat"]` followed by `if any(word in hypothesis.statement.lower() for word in vague_words): logger.warning(...) # Don't fail, but warn  pass`
**Verdict:** CONFIRMED -- Exact match including the comment text.

### Spot Check 5
**Claim:** "DockerSandbox extracts return values via stdout 'RESULT:' prefix." (sandbox.py:442-448)
**Actual code:** Lines 442-448: `for line in stdout.split('\n'): if line.startswith('RESULT:'): try: result_str = line[7:].strip(); return json.loads(result_str)`
**Verdict:** CONFIRMED -- The sandbox looks for lines starting with "RESULT:" and parses JSON from them.

### Spot Check 6
**Claim:** "CONVERGED can transition back to GENERATING_HYPOTHESES." (workflow.py:212-213)
**Actual code:** Lines 211-213: `WorkflowState.CONVERGED: [WorkflowState.GENERATING_HYPOTHESES,  # Restart if new question]`
**Verdict:** CONFIRMED -- CONVERGED lists GENERATING_HYPOTHESES as an allowed transition target.

### Spot Check 7
**Claim:** "Both a legacy sync message_queue: List (line 136) and an _async_message_queue: asyncio.Queue (line 137) exist side-by-side." (base.py:136-138)
**Actual code:** Lines 136-137: `self.message_queue: List[AgentMessage] = []  # Legacy sync queue (for compatibility)` and `self._async_message_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()`
**Verdict:** CONFIRMED -- Both queues exist exactly as described, including the "Legacy sync queue" comment.

### Spot Check 8
**Claim:** "`_actions_this_iteration` counter uses hasattr check for lazy initialization." (research_director.py:2451-2453)
**Actual code:** Lines 2451-2453: `if not hasattr(self, '_actions_this_iteration'): self._actions_this_iteration = 0  self._actions_this_iteration += 1`
**Verdict:** CONFIRMED -- The hasattr lazy initialization pattern is exactly as described.

### Spot Check 9
**Claim:** "Return value extracted from exec_locals.get('results') or exec_locals.get('result')." (executor.py:516)
**Actual code:** Line 516: `return_value = exec_locals.get('results', exec_locals.get('result'))`
**Verdict:** CONFIRMED -- Exact match. Uses dict.get() fallback chain to check both variable names.

### Spot Check 10
**Claim:** "StoppingReason.USER_REQUESTED used as sentinel for 'no reason' -- when research continues, the reason is set to USER_REQUESTED." (convergence.py:271)
**Actual code:** Lines 270-272: `return StoppingDecision(should_stop=False, reason=StoppingReason.USER_REQUESTED,  # Placeholder`
**Verdict:** CONFIRMED -- USER_REQUESTED is used as a "Placeholder" (per the comment) when no stopping criteria are met and research continues.

**Spot Check Summary: 10/10 CONFIRMED. Zero inaccuracies found.**

---

## 5c. Redundancy Check

| Section | Literally Duplicated? | Notes |
|---------|----------------------|-------|
| Identity | No | Unique overview section |
| Critical Paths (5 paths) | No | Each path traces unique control flow. Path 2 references Path 1 patterns but traces different code (scientific_evaluation.py). Path 3 references Path 2 but traces the persona wrapper. Cross-references are explicit, not duplicated content. |
| Module Behavioral Index | MINOR OVERLAP | The Summary Table (lines 1471-1494) provides a condensed version of the Per-Module Detailed Descriptions (lines 1497-2535). This is intentional -- the table is a navigation aid, not redundant content. The detailed sections contain 5-10x more information per module. |
| Interface Index + Full Specifications | MINOR OVERLAP | The Interface Index table (lines 2536-2583) provides a quick lookup of class/function to module. The Full Specifications (lines 2586-3332) provide complete parameter-level API docs. Again, intentional summary-then-detail structure. |
| Hidden Coupling section | No | Unique analysis not present elsewhere |
| Error Handling | MINOR OVERLAP | The per-module error handling deep dives (section 8, lines 3588-3664) partially overlap with error handling notes in the Module Behavioral Index. However, the Error Handling section provides cross-cutting analysis (exception hierarchy, retry strategies, degradation patterns) not available in the per-module view. The overlap is at the specific-fact level, not section-level duplication. |
| Shared State | No | Unique cross-cutting analysis |
| Configuration Surface | No | Unique detailed config analysis |
| Conventions | No | Unique pattern documentation |
| Gotchas | MINOR OVERLAP | Some gotchas reference the same underlying facts documented in Module Behavioral Index or Critical Paths, but the Gotchas section presents them as actionable warnings with severity ratings. This is value-added reframing, not redundancy. |
| Hazards | No | Unique "avoid these" guidance |
| Extension Points | MINOR OVERLAP | References gotchas and module index entries, but synthesizes them into task-specific guidance. Not duplicated. |
| Reading Order | MINOR OVERLAP | References facts from module index but organizes them for sequential learning. Not duplicated. |
| Domain Glossary | MINOR OVERLAP | Contains brief definitions that overlap with module descriptions, but is structured as a lookup table, not a narrative duplicate. |
| Gaps | No | Unique self-assessment |

**Redundancy Verdict:** No section is literally duplicated from another. There is minor structural overlap between summary tables and their detailed counterparts (Module Index table vs. detailed descriptions, Interface Index vs. Full Specifications), but this is the standard summary-then-detail pattern, not content duplication. The Error Handling, Gotchas, and Extension Points sections reference facts from other sections but reframe them for different purposes (cross-cutting analysis, actionable warnings, task guidance). No content should be removed.

---

## 5d. Adversarial Simulation

**Task:** Add a new agent type with custom behavior

### Step 1: Implementation Plan (derived ONLY from DEEP_ONBOARD.md)

1. **Create the agent class file** at `kosmos/agents/my_new_agent.py`. Subclass `BaseAgent` from `kosmos/agents/base.py`. Constructor signature: `__init__(self, agent_id=None, agent_type=None, config=None)`. Initialize LLM client via `get_client()` (Convention 12). Access config via `self.config.get("key", default)` (Convention 13). Wrap optional dependency init in try/except with WARNING log (Convention 23). Override `execute(self, task: Dict[str, Any]) -> Dict[str, Any]` -- note the base class signature takes `Dict` and returns `Dict` (line 485), but two existing agents deviate (AgentMessage), so follow the base class signature for correctness.

2. **Register the agent** in `kosmos/agents/__init__.py` by adding the import and adding to `__all__`. If the agent needs to be invoked from CLI, also update `cli/commands/run.py:147-170` to include any new flat_config keys (Convention, Extension Points table).

3. **Implement the execute() method** following Convention 8. Set `self.status = AgentStatus.WORKING` at entry, wrap body in try/except, return result dict on success, return error dict on failure, set `self.status = AgentStatus.IDLE` in finally. Use `self.llm_client.generate()` or `generate_structured()` for LLM calls (Convention 12). Use per-item error handling in loops (Convention 24).

4. **Handle lifecycle correctly.** Do NOT rely on `_on_pause()`/`_on_resume()` hooks -- they are dead code (Gotcha from base.py:189-206). `start()` cannot restart from ERROR state. `message_queue` grows without bound, so for long-running agents consider periodic cleanup or use only the async queue.

5. **Test the agent** by creating `tests/unit/agents/test_my_new_agent.py`. Group tests into classes with `Test{Concern}` names (Convention 15). Mark with `@pytest.mark.unit`. Use `Mock()` from `unittest.mock` for dependencies (Convention 17). Use `store_in_db=False` for tests that don't need DB (Convention 18). Use `unique_id()` helper for test isolation (Convention 19).

### Step 2: Verification Against Actual Codebase

**Step 1 verification:** Read `kosmos/agents/base.py`. Confirmed: `BaseAgent.__init__` takes `(agent_id=None, agent_type=None, config=None)` at line 113-117. `execute()` signature is `(self, task: Dict[str, Any]) -> Dict[str, Any]` at line 485. `get_client()` is the standard LLM access pattern. The document correctly identifies the contract.

**Step 2 verification:** Read `kosmos/agents/__init__.py`. Confirmed: All existing agents are imported and listed in `__all__`. A new agent would need to be added here. The flat_config dict in `run.py` would need updating only if the new agent needs CLI-specific config keys.

**Step 3 verification:** Examined `hypothesis_generator.py` and `literature_analyzer.py` execute() methods. Confirmed: Both set status to WORKING at entry, have try/except/finally blocks, and reset to IDLE in finally. The document correctly notes the two incompatible signatures (AgentMessage vs Dict).

**Step 4 verification:** Read `base.py:189-206`. Confirmed: `pause()` and `resume()` do NOT call `_on_pause()` or `_on_resume()`. These hooks are indeed dead code. `start()` at line 161 checks `self.status != AgentStatus.CREATED` and returns with warning -- cannot restart from ERROR.

**Step 5 verification:** Examined test file patterns in the codebase. Confirmed: Tests mirror source structure under `tests/unit/`, use `Test{Concern}` class grouping, and follow the mocking conventions described.

**Score: PASS (5/5)** -- All five steps are correct and actionable. The plan derived from DEEP_ONBOARD.md alone is sufficient to successfully add a new agent type. The document correctly identifies all the pitfalls (dead lifecycle hooks, incompatible execute signatures, unbounded message queue, flat_config bridge).

---

## 5e. Caching Structure Verification

The document should present stable (rarely-changing) content before volatile (frequently-changing) content for optimal LLM context caching.

**Actual section order:**

1. Identity -- STABLE (project description rarely changes)
2. Critical Paths -- STABLE (architecture traces change only on major refactors)
3. Module Behavioral Index -- STABLE (module behaviors change with code)
4. Interface Index + Full Specifications -- STABLE (API signatures change infrequently)
5. Hidden Coupling -- STABLE (architectural observations)
6. Error Handling -- STABLE (error handling strategy)
7. Shared State Index -- SEMI-STABLE (shared state evolves with new singletons)
8. Configuration Surface -- SEMI-STABLE (env vars added periodically)
9. Domain Glossary -- STABLE (terminology rarely changes)
10. Conventions -- STABLE (conventions are slow to change)
11. Gotchas -- SEMI-VOLATILE (new gotchas discovered as code evolves)
12. Hazards -- SEMI-VOLATILE (dead code may be cleaned up)
13. Extension Points -- SEMI-STABLE (extension guidance changes with architecture)
14. Reading Order -- SEMI-STABLE (order changes if modules added/removed)
15. Gaps -- VOLATILE (gaps resolved over time)

**Verdict:** The document follows a reasonable stable-first ordering. The most stable content (Identity, Critical Paths, Module Index, Interfaces) comes first. Semi-stable cross-cutting analysis (Error Handling, Shared State, Configuration) is in the middle. More volatile advisory content (Gotchas, Hazards, Extension Points, Reading Order, Gaps) comes last. The Domain Glossary is placed between Configuration Surface and Conventions, which is acceptable -- it could arguably be earlier (it is stable reference material), but its current placement is not harmful.

**One improvement:** The Domain Glossary (lines 4157-4260) is currently embedded between the Concurrency Model subsection and the Configuration Surface section. Since it is stable reference content, it would be slightly better placed earlier (after the Interface Index), but this is a minor optimization, not a structural problem.

**Caching Structure Rating: PASS** -- Stable sections precede volatile sections.

---

## Summary

| Check | Result |
|-------|--------|
| Q1. PURPOSE | YES |
| Q2. ENTRY | YES |
| Q3. FLOW | YES |
| Q4. HAZARDS | YES |
| Q5. ERRORS | YES |
| Q6. EXTERNAL | YES |
| Q7. STATE | YES |
| Q8. TESTING | PARTIAL (self-identified gap) |
| Q9. GOTCHAS | YES |
| Q10. EXTENSION | YES |
| Standard Questions Score | 9/10 (9 YES, 1 PARTIAL) |
| Spot Checks | 10/10 CONFIRMED |
| Redundancy | CLEAN (no literal duplication) |
| Adversarial Simulation | PASS (5/5) |
| Caching Structure | PASS |

**Overall Assessment:** This is an exceptionally high-quality onboarding document. All 10 spot-checked factual claims were confirmed against the actual codebase. The only partial answer (Q8 Testing) is self-identified in the Gaps section. The document's 93+ gotchas with severity ratings, 14 hazard entries, 24 shared state items with risk assessments, and 14 extension point guides with specific watch-out warnings make it immediately actionable for an AI agent working in this codebase. The adversarial simulation (add a new agent type) produced a correct 5-step plan solely from the document, confirming it is sufficient for real development tasks.
