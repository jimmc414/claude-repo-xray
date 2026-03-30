# Deep Crawl Validation Report: Kosmos

## 5a. Standard Questions Test

| # | Question | Answerable | Evidence |
|---|----------|-----------|---------|
| Q1 | PURPOSE: What does this codebase do? | **YES** | Identity section: autonomous AI scientist for scientific research |
| Q2 | ENTRY: Where does a request/command enter? | **YES** | Critical Paths: cli_entrypoint → main callback → run_research |
| Q3 | FLOW: Critical path from input to output? | **YES** | Full 10-phase trace with file:line at every hop |
| Q4 | HAZARDS: Files to avoid? | **YES** | Hazards section: kosmos-reference, kosmos-claude-scientific-skills, archived |
| Q5 | ERRORS: What happens when main op fails? | **YES** | Error Handling: log-and-return-default + 3-tier LLM resilience + agent backoff |
| Q6 | EXTERNAL: External systems? | **YES** | Storage Architecture: 5 storage technologies + LLM APIs |
| Q7 | STATE: Shared state causing bugs? | **YES** | Shared State table: 15+ singletons with thread-safety annotations |
| Q8 | TESTING: Testing conventions? | **YES** | Test Infrastructure section + Conventions #9 |
| Q9 | GOTCHAS: Top 3 counterintuitive things? | **YES** | 28 gotchas documented with file:line |
| Q10 | EXTENSION: How to add new entity? | **YES** | Extension Points table: 7 common tasks |

**Score: 10/10**

## 5a-bis. Coverage Breadth Test

| Metric | Target | Actual |
|--------|--------|--------|
| Subsystems with >= 1 documented module | 100% | 13/15 (87%) — missing orchestration, world_model detail |
| Xray pillars in Module Index | 100% | 10/10 (100%) |
| Entry points with traces | 100% | 5/5 (100%) |
| Cross-cutting concerns from crawl plan | 100% | 7/7 (100%) |
| Module Index entries vs core files | >= 25% | 28/~100 core files (28%) |

## 5b. Spot-Check Verification (10 Claims)

| # | Claim | File:Line | Verified |
|---|-------|-----------|----------|
| 1 | exec() fallback when Docker unavailable | executor.py:217-221 | YES — `logger.warning("Docker sandbox not available")` |
| 2 | CLI timeout 2hr at run.py:301 | run.py:301 | YES — `max_loop_duration = 7200` |
| 3 | MAX_ACTIONS_PER_ITERATION=50 | research_director.py:50 | YES — constant defined at line 50 |
| 4 | SAFE_BUILTINS at executor.py:43-83 | executor.py:43-83 | YES — restricted dict |
| 5 | get_config singleton at config.py:1140 | config.py:1140 | YES — `_config: Optional[KosmosConfig] = None` |
| 6 | DB init in global callback at main.py:145 | main.py:145 | YES — `init_from_config()` call |
| 7 | Message router None for unregistered agents | base.py:290 | YES — `if self._message_router:` guard |
| 8 | Dual message queues at base.py:136-137 | base.py:136-137 | YES — sync list + asyncio.Queue |
| 9 | LiteLLM always created at config.py:963 | config.py:963 | YES — `default_factory=LiteLLMConfig` |
| 10 | Circuit breaker 3 failures at async_llm.py:52 | async_llm.py:52 | YES — `failure_threshold=3` |

**Score: 10/10 verified**

## 5c. Redundancy Check

No literally duplicated content found between sections. Some overlap between Critical Paths trace and Module Index is intentional (different perspectives: flow vs. behavior).

## 5d. Adversarial Simulation

**Task:** "Add a new agent that performs literature review quality assessment"

**5-step plan using ONLY DEEP_ONBOARD.md:**

1. Create `kosmos/agents/literature_quality_agent.py` inheriting from `BaseAgent` (Convention #1: inherit BaseAgent, call super().__init__ with agent_id/agent_type/config)
2. Add config access via `self.config.get("key", default)` pattern (Convention #2: plain dict, never KosmosConfig directly). Get LLM client via `get_client()`.
3. Add handler method in `research_director.py` following the direct-call pattern (Convention #8): lazy-init with `if self._quality_agent is None: from kosmos.agents.literature_quality_agent import ...`
4. Add `AGENT_ROUTING` entry in `orchestration/delegation.py` mapping `literature_quality -> LiteratureQualityAgent`
5. Register in `agents/__init__.py`. Write tests in `tests/unit/agents/test_literature_quality_agent.py` using conftest singleton reset fixture.

**Verification:** Steps 1-2 follow agent class pattern (Convention #1-2). Step 3 follows Issue #76 direct-call pattern documented in Agent Communication section. Step 4 extends delegation (Extension Points table). Step 5 follows test conventions.

**Score: PASS (5/5)**

## 5e. Caching Structure Verification

Stable sections (Identity, Critical Paths, Module Index, Key Interfaces, Error Handling, Shared State, Domain Glossary, Config, Conventions) precede volatile sections (Gotchas, Hazards, Extension Points, Reading Order, Gaps). **PASS**

## Summary

| Check | Score |
|-------|-------|
| Standard Questions | 10/10 |
| Coverage Breadth | 87% subsystems, 100% pillars, 100% traces |
| Spot-Check | 10/10 verified |
| Redundancy | Clean |
| Adversarial | PASS (5/5) |
| Caching Structure | PASS |
